"""Directed OpenAlex + Unpaywall sweep for open-access epsilon(T) leads (v1.x W13).

v1.0 ships a 246-compound static-permittivity dataset, but the v1.x plan wants a
temperature-resolved observation table. Most of that data is already on disk; this
probe covers the *online* remainder: primary open-access literature that reports the
static relative permittivity (epsilon) of battery solvents as a function of
temperature, for solvent families the local dataset does not already cover.

The sweep is deliberately conservative:

- OpenAlex is queried through ``title_and_abstract.search``. The anonymous
  full-text ``search`` endpoint is rate-limited far more aggressively, and a comma
  inside a filter value is rejected outright, so query terms are de-commaed and
  multi-word terms are quoted.
- Open-access status is decided by Unpaywall, not by OpenAlex: a work is kept only
  when Unpaywall reports ``is_oa is True``.
- The client is polite: a descriptive ``mailto``, a fixed sleep between calls, a
  small page cap, ``429`` backoff, and a hard request budget printed at the end.
- Nothing is invented. If DNS or the API fails, the failure is recorded verbatim in
  the summary JSON and in ``reports/g1plus_oa_sweep_round6.md``, and no candidate row
  is emitted for it.

The HTTP layer is injected through ``http_get`` so that query building, OA filtering
and row shaping are unit-testable with canned payloads and no network.

Outputs:
- ``data/processed/openalex_oa_candidates.csv``
- ``probes/openalex_unpaywall_sweep_summary.json``
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

OPENALEX_ENDPOINT = "https://api.openalex.org/works"
UNPAYWALL_ENDPOINT = "https://api.unpaywall.org/v2"
USER_AGENT = "electrolyte-ml-research/1.0 (W13 open-access dielectric sweep)"
DEFAULT_MAILTO = "codex@local"

DEFAULT_OUTPUT = REPOSITORY_ROOT / "data" / "processed" / "openalex_oa_candidates.csv"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "openalex_unpaywall_sweep_summary.json"

DEFAULT_LIMIT = 200
DEFAULT_PAGE_SIZE = 20
DEFAULT_SLEEP_SECONDS = 1.0
EARLIEST_YEAR = 2001
HTTP_TIMEOUT_SECONDS = 30
BACKOFF_SECONDS = (5.0, 15.0)
# OpenAlex answers a 429 with its own retry hint (a Retry-After header, or a
# "retryAfter": N field in the JSON body). Honour that hint up to this ceiling so a
# rate-limited query is retried when the server says it is ready, not on a guess.
MAX_BACKOFF_SECONDS = 45.0

# Local-coverage reference files: any solvent name appearing here is treated as
# already covered by v1.0, so a hit that only mentions those names is not a new lead.
KNOWN_NAME_SOURCES: tuple[Path, ...] = (
    REPOSITORY_ROOT / "data" / "dielectric_v03.csv",
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11.csv",
    REPOSITORY_ROOT / "data" / "processed" / "modern_battery_solvent_candidate_queue.csv",
)

MIN_NAME_MATCH_LENGTH = 6

DIELECTRIC_TERMS: tuple[str, ...] = ("dielectric", "permittivity")

# (label, terms). Terms must not contain commas: OpenAlex rejects a filter value with
# a comma, so "1,2-dimethoxyethane" is expressed as the comma-free "dimethoxyethane".
QUERY_TEMPLATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "glymes",
        (
            "glyme",
            "diglyme",
            "triglyme",
            "tetraglyme",
            "dimethoxyethane",
            "diethylene glycol dimethyl ether",
        ),
    ),
    (
        "dinitriles",
        (
            "adiponitrile",
            "glutaronitrile",
            "succinonitrile",
            "malononitrile",
            "dinitrile",
        ),
    ),
    (
        "fluorinated_ethers",
        (
            "fluoroether",
            "hydrofluoroether",
            "methyl nonafluorobutyl ether",
            "novec",
        ),
    ),
    (
        "fluorinated_alcohols",
        (
            "trifluoroethanol",
            "hexafluoroisopropanol",
            "fluorinated alcohol",
        ),
    ),
    (
        "sulfones",
        (
            "sulfolane",
            "dimethyl sulfone",
            "ethyl methyl sulfone",
            "sulfone",
        ),
    ),
    (
        "modern_carbonates_and_esters",
        (
            "ethyl methyl carbonate",
            "gamma-valerolactone",
            "gamma-butyrolactone",
            "trifluoroethyl methyl carbonate",
            "methyl trifluoroacetate",
            "propylene carbonate",
        ),
    ),
)
CANDIDATE_COLUMNS: tuple[str, ...] = (
    "doi",
    "openalex_id",
    "title",
    "publication_year",
    "type",
    "host_venue",
    "openalex_is_oa",
    "unpaywall_is_oa",
    "unpaywall_oa_status",
    "oa_url",
    "oa_host_type",
    "oa_version",
    "license",
    "journal_is_oa",
    "published_date",
    "query_label",
    "matched_known_names",
    "is_new_lead",
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "doi:", "https://dx.doi.org/")


@dataclass
class HttpResponse:
    """A transport-level result, so callers never touch ``requests`` directly."""

    status_code: int
    payload: dict[str, Any] | None = None
    error: str | None = None
    retry_after: float | None = None


@dataclass
class RequestBudget:
    """Hard cap on outbound HTTP calls, with a per-status tally."""

    limit: int
    used: int = 0
    statuses: Counter[int] = field(default_factory=Counter)

    def spend(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True

    def record(self, status_code: int) -> None:
        self.statuses[status_code] += 1

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


HttpGet = Callable[[str, Mapping[str, Any]], HttpResponse]


def sanitize_term(term: str) -> str:
    """Return a query term OpenAlex accepts inside a filter value."""

    return " ".join(term.replace(",", " ").split())


def quote_term(term: str) -> str:
    """Quote multi-word terms so they are searched as phrases."""

    return f'"{term}"' if " " in term else term


def build_query_expression(terms: Sequence[str]) -> str:
    """Build ``(dielectric OR permittivity) AND (t1 OR t2 OR ...)``."""

    cleaned = [sanitize_term(term) for term in terms]
    cleaned = [term for term in cleaned if term]
    if not cleaned:
        raise ValueError("a query needs at least one non-empty term")
    dielectric = " OR ".join(DIELECTRIC_TERMS)
    solvents = " OR ".join(quote_term(term) for term in cleaned)
    return f"({dielectric}) AND ({solvents})"


def build_openalex_filter(query: str, *, earliest_year: int = EARLIEST_YEAR) -> str:
    """Compose the OpenAlex filter string; no value may contain a comma."""

    return ",".join(
        (
            f"from_publication_date:{earliest_year}-01-01",
            "has_doi:true",
            f"title_and_abstract.search:{query}",
        )
    )


def build_openalex_params(
    query: str,
    *,
    page: int = 1,
    per_page: int = DEFAULT_PAGE_SIZE,
    mailto: str = DEFAULT_MAILTO,
    earliest_year: int = EARLIEST_YEAR,
) -> dict[str, Any]:
    return {
        "filter": build_openalex_filter(query, earliest_year=earliest_year),
        "per-page": per_page,
        "page": page,
        "mailto": mailto,
    }


def normalize_doi(value: str | None) -> str:
    """Lower-case a DOI and strip any resolver prefix."""

    if not value:
        return ""
    doi = value.strip()
    lowered = doi.lower()
    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            doi = doi[len(prefix) :]
            break
    return doi.strip().lower().strip("/")


def normalize_name(value: str) -> str:
    """Lower-case and reduce a name to space-separated alphanumeric tokens."""

    return _NON_ALNUM.sub(" ", value.lower()).strip()


def work_doi(work: Mapping[str, Any]) -> str:
    return normalize_doi(work.get("doi") if isinstance(work, Mapping) else None)


def work_is_openalex_oa(work: Mapping[str, Any]) -> bool:
    open_access = work.get("open_access")
    return bool(isinstance(open_access, Mapping) and open_access.get("is_oa"))


def work_venue(work: Mapping[str, Any]) -> str:
    primary = work.get("primary_location")
    if isinstance(primary, Mapping):
        source = primary.get("source")
        if isinstance(source, Mapping) and source.get("display_name"):
            return str(source["display_name"])
    return ""


def shape_openalex_work(work: Mapping[str, Any], query_label: str) -> dict[str, Any] | None:
    """Reduce one OpenAlex work to the fields the sweep needs, or None without a DOI."""

    doi = work_doi(work)
    if not doi:
        return None
    return {
        "doi": doi,
        "openalex_id": str(work.get("id", "")),
        "title": str(work.get("title") or ""),
        "publication_year": work.get("publication_year"),
        "type": str(work.get("type") or ""),
        "host_venue": work_venue(work),
        "openalex_is_oa": work_is_openalex_oa(work),
        "query_labels": [query_label],
    }


def unpaywall_oa_fields(payload: Any) -> dict[str, Any]:
    """Extract the OA decision and location fields from a Unpaywall payload."""

    empty = {
        "unpaywall_is_oa": False,
        "unpaywall_oa_status": "",
        "oa_url": "",
        "oa_host_type": "",
        "oa_version": "",
        "license": "",
        "journal_is_oa": False,
        "published_date": "",
    }
    if not isinstance(payload, Mapping):
        return empty
    best = payload.get("best_oa_location")
    best = best if isinstance(best, Mapping) else {}
    source = best.get("source")
    source = source if isinstance(source, Mapping) else {}
    oa_url = best.get("url_for_pdf") or best.get("url") or best.get("url_for_landing_page") or ""
    return {
        "unpaywall_is_oa": bool(payload.get("is_oa")),
        "unpaywall_oa_status": str(payload.get("oa_status") or ""),
        "oa_url": str(oa_url or ""),
        # `host_type` sits on the location itself; `source.type` is only a fallback.
        "oa_host_type": str(best.get("host_type") or source.get("type") or ""),
        "oa_version": str(best.get("version") or ""),
        "license": str(best.get("license") or ""),
        "journal_is_oa": bool(payload.get("journal_is_oa")),
        "published_date": str(payload.get("published_date") or ""),
    }


def match_known_names(
    title: str,
    known_names: Sequence[str],
    *,
    min_length: int = MIN_NAME_MATCH_LENGTH,
) -> tuple[str, ...]:
    """Return the local solvent names mentioned in ``title``.

    Matching is whole-token: ``octane`` does not match ``cyclooctane``. Short generic
    names (e.g. ``water``) are dropped by ``min_length`` to limit over-matching.
    """

    haystack = f" {normalize_name(title)} "
    hits = []
    for name in known_names:
        needle = normalize_name(name)
        if len(needle) >= min_length and f" {needle} " in haystack:
            hits.append(name)
    return tuple(sorted(set(hits)))


def is_new_lead(title: str, known_names: Sequence[str]) -> bool:
    return not match_known_names(title, known_names)


def shape_candidate_row(work: Mapping[str, Any], unpaywall: Mapping[str, Any]) -> dict[str, Any]:
    """Combine an OpenAlex work with its Unpaywall fields into a CSV row."""

    row = dict(work)
    row.update(unpaywall)
    return row


def load_known_local_names(sources: Sequence[Path] = KNOWN_NAME_SOURCES) -> tuple[str, ...]:
    """Union the ``name`` column of every local reference file that exists."""

    names: set[str] = set()
    for path in sources:
        if not path.is_file():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                name = (row.get("name") or "").strip()
                if name:
                    names.add(name)
    return tuple(sorted(names))

def parse_retry_after(value: Any) -> float | None:
    """Parse a ``Retry-After`` / ``retryAfter`` hint into seconds; None when unusable."""

    if value is None:
        return None
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def extract_retry_after(header_value: str | None, body_text: str | None) -> float | None:
    """Prefer the standard header, then fall back to OpenAlex's JSON ``retryAfter``."""

    from_header = parse_retry_after(header_value)
    if from_header is not None:
        return from_header
    if not body_text:
        return None
    try:
        payload = json.loads(body_text)
    except ValueError:
        return None
    if isinstance(payload, Mapping):
        return parse_retry_after(payload.get("retryAfter"))
    return None


def next_backoff_delay(
    response: HttpResponse, attempt: int, sleep_seconds: float
) -> float:
    """The polite wait before retrying a 429.

    The fixed schedule is a floor, so a server hint is always respected when it is
    longer, and capped so a bogus hint cannot stall the sweep.
    """

    scheduled = BACKOFF_SECONDS[attempt] if attempt < len(BACKOFF_SECONDS) else sleep_seconds
    if response.retry_after is None:
        return scheduled
    return min(max(response.retry_after, scheduled), MAX_BACKOFF_SECONDS)


def default_http_get(url: str, params: Mapping[str, Any]) -> HttpResponse:
    """Real transport. Only this function touches the network."""

    try:
        response = requests.get(
            url,
            params=dict(params),
            headers={"User-Agent": USER_AGENT},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:  # DNS failure, timeout, refused, ...
        return HttpResponse(0, None, f"{type(exc).__name__}: {exc}")
    if response.status_code != 200:
        retry_after = extract_retry_after(
            response.headers.get("Retry-After"), response.text[:1000]
        )
        return HttpResponse(response.status_code, None, response.text[:300], retry_after)
    try:
        payload = response.json()
    except ValueError as exc:
        return HttpResponse(response.status_code, None, f"invalid JSON: {exc}")
    return HttpResponse(200, payload, None)


def http_get_with_backoff(
    url: str,
    params: Mapping[str, Any],
    *,
    http_get: HttpGet,
    budget: RequestBudget,
    sleeper: Callable[[float], None],
    sleep_seconds: float,
) -> HttpResponse:
    """One logical request: spend budget, sleep politely, retry ``429`` a few times."""

    response = HttpResponse(0, None, "request budget exhausted before the call")
    for attempt in range(len(BACKOFF_SECONDS) + 1):
        if not budget.spend():
            return HttpResponse(0, None, "request budget exhausted")
        response = http_get(url, params)
        budget.record(response.status_code)
        if response.status_code != 429:
            return response
        if attempt < len(BACKOFF_SECONDS):
            sleeper(next_backoff_delay(response, attempt, sleep_seconds))
    sleeper(sleep_seconds)
    return response


def sweep_openalex(
    label: str,
    terms: Sequence[str],
    *,
    http_get: HttpGet,
    budget: RequestBudget,
    mailto: str,
    per_page: int,
    sleep_seconds: float,
    sleeper: Callable[[float], None],
    earliest_year: int = EARLIEST_YEAR,
    page: int = 1,
) -> dict[str, Any]:
    """Run one query against OpenAlex and return the shaped works plus diagnostics."""

    query = build_query_expression(terms)
    params = build_openalex_params(
        query, page=page, per_page=per_page, mailto=mailto, earliest_year=earliest_year
    )
    record: dict[str, Any] = {
        "label": label,
        "terms": list(terms),
        "query": query,
        "openalex_filter": params["filter"],
        "openalex_url": OPENALEX_ENDPOINT,
        "per_page": per_page,
        "total_count": None,
        "works_returned": 0,
        "works": [],
        "status": None,
        "error": None,
    }
    if budget.remaining <= 0:
        record["error"] = "request budget exhausted before the OpenAlex query"
        return record

    response = http_get_with_backoff(
        OPENALEX_ENDPOINT,
        params,
        http_get=http_get,
        budget=budget,
        sleeper=sleeper,
        sleep_seconds=sleep_seconds,
    )
    record["status"] = response.status_code
    record["error"] = response.error
    sleeper(sleep_seconds)
    if response.status_code != 200 or not isinstance(response.payload, Mapping):
        return record

    meta = response.payload.get("meta")
    if isinstance(meta, Mapping):
        record["total_count"] = meta.get("count")
    results = response.payload.get("results")
    if not isinstance(results, list):
        record["error"] = "OpenAlex payload had no 'results' list"
        return record

    shaped = []
    for work in results:
        if isinstance(work, Mapping):
            row = shape_openalex_work(work, label)
            if row is not None:
                shaped.append(row)
    record["works"] = shaped
    record["works_returned"] = len(results)
    return record


def sweep_unpaywall(
    dois: Sequence[str],
    *,
    http_get: HttpGet,
    budget: RequestBudget,
    mailto: str,
    sleep_seconds: float,
    sleeper: Callable[[float], None],
) -> dict[str, Any]:
    """Resolve open-access status for each DOI through Unpaywall."""

    resolved: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for doi in dois:
        if budget.remaining <= 0:
            unresolved.append(doi)
            continue
        url = f"{UNPAYWALL_ENDPOINT}/{doi}"
        response = http_get_with_backoff(
            url,
            {"email": mailto},
            http_get=http_get,
            budget=budget,
            sleeper=sleeper,
            sleep_seconds=sleep_seconds,
        )
        if response.status_code == 200 and isinstance(response.payload, Mapping):
            resolved[doi] = unpaywall_oa_fields(response.payload)
        else:
            unresolved.append(doi)
            failures.append(
                {
                    "stage": "unpaywall",
                    "doi": doi,
                    "status": response.status_code,
                    "error": response.error,
                }
            )
    return {"resolved": resolved, "unresolved": unresolved, "failures": failures}


def run_sweep(
    *,
    output: Path = DEFAULT_OUTPUT,
    summary_path: Path = DEFAULT_SUMMARY,
    limit: int = DEFAULT_LIMIT,
    mailto: str = DEFAULT_MAILTO,
    page_size: int = DEFAULT_PAGE_SIZE,
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
    earliest_year: int = EARLIEST_YEAR,
    http_get: HttpGet = default_http_get,
    sleeper: Callable[[float], None] = time.sleep,
    known_names: Sequence[str] | None = None,
    queries: Sequence[tuple[str, Sequence[str]]] = QUERY_TEMPLATES,
) -> dict[str, Any]:
    """Run the whole sweep and write the CSV + summary JSON."""

    if known_names is None:
        known_names = load_known_local_names()
    budget = RequestBudget(limit=limit)
    queries_run: list[dict[str, Any]] = []
    merged: dict[str, dict[str, Any]] = {}
    doi_order: list[str] = []

    for label, terms in queries:
        record = sweep_openalex(
            label,
            terms,
            http_get=http_get,
            budget=budget,
            mailto=mailto,
            per_page=page_size,
            sleep_seconds=sleep_seconds,
            sleeper=sleeper,
            earliest_year=earliest_year,
        )
        queries_run.append(record)
        for work in record["works"]:
            doi = work["doi"]
            if doi in merged:
                labels = merged[doi]["query_labels"]
                if label not in labels:
                    labels.append(label)
                continue
            merged[doi] = work
            doi_order.append(doi)

    openalex_is_oa = sum(1 for work in merged.values() if work["openalex_is_oa"])

    resolution = sweep_unpaywall(
        doi_order,
        http_get=http_get,
        budget=budget,
        mailto=mailto,
        sleep_seconds=sleep_seconds,
        sleeper=sleeper,
    )

    candidates: list[dict[str, Any]] = []
    for doi in doi_order:
        fields = resolution["resolved"].get(doi)
        if not fields or not fields["unpaywall_is_oa"]:
            continue
        work = merged[doi]
        matched = match_known_names(work["title"], known_names)
        row = shape_candidate_row(work, fields)
        row["query_label"] = ";".join(work["query_labels"])
        row["matched_known_names"] = ";".join(matched)
        row["is_new_lead"] = not matched
        candidates.append(row)

    candidates.sort(key=lambda row: (row["publication_year"] or 0, row["doi"]), reverse=True)

    failures: list[dict[str, Any]] = list(resolution["failures"])
    for record in queries_run:
        if record["error"] and not record["works"]:
            failures.append(
                {
                    "stage": "openalex",
                    "label": record["label"],
                    "query": record["query"],
                    "status": record["status"],
                    "error": record["error"],
                }
            )

    summary: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mailto": mailto,
        "page_size": page_size,
        "earliest_year": earliest_year,
        "request_budget": limit,
        "requests_used": budget.used,
        "http_status_counts": {str(code): count for code, count in sorted(budget.statuses.items())},
        "queries": [
            {key: value for key, value in record.items() if key != "works"} for record in queries_run
        ],
        "works_collected": len(merged),
        "openalex_is_oa_works": openalex_is_oa,
        "unpaywall_resolved": len(resolution["resolved"]),
        "unpaywall_unresolved": resolution["unresolved"],
        "oa_candidates": len(candidates),
        "new_leads": sum(1 for row in candidates if row["is_new_lead"]),
        "known_name_universe": len(known_names),
        "candidates": candidates,
        "failures": failures,
        "caveats": [
            (
                "OpenAlex 'title_and_abstract.search' only indexes titles/abstracts; a paper "
                "that reports epsilon(T) without those words is invisible to this sweep."
            ),
            "Unpaywall is the OA gate, so a genuinely open paper Unpaywall mislabels is dropped.",
            (
                "An OA hit is a *lead*, not verified epsilon(T) data: the value must still be "
                "read from the full text and cross-checked before it enters any observation "
                "table."
            ),
            (
                "is_new_lead is a title-token match against local solvent names; short generic "
                "names are filtered by a minimum length, so the flag is a triage aid, not proof "
                "of novelty."
            ),
        ],
    }

    write_outputs(summary, output=output, summary_path=summary_path)
    return summary


def write_outputs(
    summary: Mapping[str, Any],
    *,
    output: Path = DEFAULT_OUTPUT,
    summary_path: Path = DEFAULT_SUMMARY,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(CANDIDATE_COLUMNS), extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        for row in summary["candidates"]:
            writer.writerow(row)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="hard HTTP request budget")
    parser.add_argument("--mailto", default=DEFAULT_MAILTO, help="polite contact address")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_sweep(
        output=args.output,
        summary_path=args.summary,
        limit=args.limit,
        mailto=args.mailto,
        page_size=args.page_size,
        sleep_seconds=args.sleep,
    )
    print(f"queries run: {len(summary['queries'])}")
    print(f"works collected: {summary['works_collected']}")
    print(f"OA candidates: {summary['oa_candidates']} (new leads: {summary['new_leads']})")
    print(f"failures recorded: {len(summary['failures'])}")
    print(f"requests used: {summary['requests_used']}/{summary['request_budget']}")
    print(f"wrote {args.output}")
    print(f"wrote {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())