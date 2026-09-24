"""Probe the NIST Chemistry WebBook for dielectric-constant evidence.

Appendix J of the execution manual lists the NIST Chemistry WebBook as a free
tier-1 source for dielectric constants ("some substances carry a dielectric
constant and a refractive index"). The first G1+ pass queried the CAS pages of
the ten targets, got HTTP 200 for each, and found no dielectric field. That
negative is worth strengthening, because a target-only check cannot tell "the
WebBook does not model this property" apart from "this particular lookup did
not surface it". This probe re-runs the check so the negative is falsifiable:

1. Search by `Name=` and address each hit by its `ID=`, and record the status
   of an unsupported `InChIKey=` query form so the accepted surface is
   documented rather than assumed.
2. Gate every hit on identity - the compound page embeds its `inChIKey` in a
   JSON-LD block, so a hit is only accepted when that key equals the dataset
   key. A name collision can therefore never be filed as evidence.
3. Count `dielectric` / `permittivity` occurrences over the whole page.
4. Run the same test on positive controls (water, methanol, ethanol, acetone),
   whose dielectric constants are beyond dispute. If the controls are empty
   too, the negative is a property of the WebBook data model rather than a
   per-target lookup failure.

Raw responses are cached under data/external/g1plus/webbook/ (git-ignored) so
the JSON artefact can be regenerated without re-spending requests.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

CBOOK = "https://webbook.nist.gov/cgi/cbook.cgi"
USER_AGENT = "electrolyte-ml-research/1.0 (local reproducibility probe)"

DEFAULT_CACHE = REPOSITORY_ROOT / "data" / "external" / "g1plus" / "webbook"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "probes" / "g1plus_nist_webbook_evidence.json"

MAX_CANDIDATES = 8

# (dataset name, dataset InChIKey, role) - the same G1+ target set the PubChem
# probe uses, so the two tier-1 negatives can be read side by side.
TARGETS: tuple[tuple[str, str, str], ...] = (
    ("ethylene carbonate", "KMTRUDSVKNLOMY-UHFFFAOYSA-N", "retained primary 90.5 at 313.15 K"),
    ("propylene carbonate", "RUOJZAUFBMNUDX-UHFFFAOYSA-N", "retained primary 64.9 at 298.15 K"),
    ("vinylene carbonate", "VAYTZRYEBVHVLE-UHFFFAOYSA-N", "conflict_open: 126 vs 78-127"),
    ("fluoroethylene carbonate", "SBLRHMKNNHXPHG-UHFFFAOYSA-N", "conflict 78.4 / 102 / 107"),
    ("gamma-valerolactone", "GAEKPEKOJKCEMS-UHFFFAOYSA-N", "conflict 36.1 vs 32 (and 34)"),
    ("3-methoxypropionitrile", "OOWFYDWAMOKVSF-UHFFFAOYSA-N", "secondary compilation, no xTB row"),
    ("adiponitrile", "BTGRAWJCKBQKAO-UHFFFAOYSA-N", "G1+ target, no value yet"),
    ("glutaronitrile", "ZTOMUSMDRMJOTH-UHFFFAOYSA-N", "primary vs Duncan 2013 conflict"),
    ("1,2-dimethoxyethane", "XTHFKEDIFFGKHM-UHFFFAOYSA-N", "monoglyme"),
    ("diglyme", "SBZXBUIDTXKZTM-UHFFFAOYSA-N", "diglyme"),
    ("triglyme", "YFNKIDBQEZZDLK-UHFFFAOYSA-N", "triglyme"),
    ("tetraglyme", "ZUHZGEOKBKGPSW-UHFFFAOYSA-N", "tetraglyme"),
    ("sulfolane", "HXJUTPCZVOIRIF-UHFFFAOYSA-N", "cross-check anchor"),
    ("acetonitrile", "WEVYAHXRMPXWCK-UHFFFAOYSA-N", "cross-check anchor"),
)

# Substances whose dielectric constants are not in question. Used only to test
# whether the WebBook exposes the property at all; they are never added to the
# dataset.
CONTROLS: tuple[tuple[str, str, str], ...] = (
    ("water", "XLYOFNOQVPJJNP-UHFFFAOYSA-N", "positive control, epsilon 78.4 at 298 K"),
    ("methanol", "OKKJLVBELUTLKV-UHFFFAOYSA-N", "positive control, epsilon 32.7 at 298 K"),
    ("ethanol", "LFQSCWFLJHTTHZ-UHFFFAOYSA-N", "positive control, epsilon 24.5 at 298 K"),
    ("acetone", "CSCPPACGZOOCGX-UHFFFAOYSA-N", "positive control, epsilon 20.7 at 298 K"),
)

# Deliberately generous: the claim under test is a *negative*, so anything
# that could plausibly spell the property is counted. A hit on any of these
# would falsify the negative and force a closer read.
PROPERTY_PATTERNS: tuple[str, ...] = (
    "dielectric",
    "permittivity",
    "epsilon",
    "\u03b5",
)

INCHIKEY_IN_PAGE = re.compile(r'"inChIKey"\s*:\s*"([A-Z]{14}-[A-Z]{10}-[A-Z])"')
CAS_IN_PAGE = re.compile(r"CAS Registry Number:\s*</strong>\s*([0-9]{2,7}-[0-9]{2}-[0-9])")
CANDIDATE_ID = re.compile(r"cbook\.cgi\?ID=([A-Za-z0-9]+)")


def fetch(url: str, cache_path: Path, *, refresh: bool = False, attempts: int = 4) -> str:
    """Return the response body, caching it so re-runs cost no requests."""

    if cache_path.is_file() and not refresh:
        return cache_path.read_text(encoding="utf-8")
    last: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 400:
                raise
            last = exc
        except urllib.error.URLError as exc:
            last = exc
        else:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(body, encoding="utf-8")
            return body
        time.sleep(1.5 * (attempt + 1))
    raise last if last is not None else RuntimeError(f"unreachable: {url}")


def property_hits(html: str) -> dict[str, int]:
    """Count the named property over the entire page, not just its headings."""

    lowered = html.lower()
    return {name: lowered.count(name) for name in PROPERTY_PATTERNS}


def search_ids(name: str, cache_dir: Path, *, refresh: bool = False) -> list[str]:
    url = f"{CBOOK}?Name={urllib.parse.quote(name)}&Units=SI"
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    html = fetch(url, cache_dir / f"search_{slug}.html", refresh=refresh)
    seen: list[str] = []
    for candidate in CANDIDATE_ID.findall(html):
        if candidate not in seen:
            seen.append(candidate)
    return seen[:MAX_CANDIDATES]


def compound_page(cid: str, cache_dir: Path, *, refresh: bool = False) -> str:
    return fetch(
        f"{CBOOK}?ID={urllib.parse.quote(cid)}&Units=SI",
        cache_dir / f"compound_{cid}.html",
        refresh=refresh,
    )


def probe_compound(
    name: str,
    inchikey: str,
    role: str,
    cache_dir: Path,
    *,
    refresh: bool = False,
) -> dict[str, object]:
    record: dict[str, object] = {
        "name": name,
        "expected_inchikey": inchikey,
        "role": role,
    }
    try:
        candidates = search_ids(name, cache_dir, refresh=refresh)
    except urllib.error.HTTPError as exc:
        record.update({"status": f"search_http_{exc.code}", "candidate_ids": []})
        return record

    identity_checked: list[dict[str, object]] = []
    matched: str | None = None
    for cid in candidates:
        try:
            html = compound_page(cid, cache_dir, refresh=refresh)
        except urllib.error.HTTPError as exc:
            identity_checked.append({"id": cid, "status": f"http_{exc.code}"})
            continue
        found = INCHIKEY_IN_PAGE.search(html)
        page_key = found.group(1) if found else ""
        identity_checked.append({"id": cid, "page_inchikey": page_key})
        if page_key == inchikey:
            matched = cid
            break

    record["candidate_ids"] = candidates
    record["identity_checked"] = identity_checked
    if matched is None:
        record["status"] = "name_unresolved_or_identity_mismatch"
        record["page_inchikey"] = ""
        record["cas"] = ""
        record["property_hits"] = {name: 0 for name in PROPERTY_PATTERNS}
        return record

    html = compound_page(matched, cache_dir, refresh=refresh)
    cas = CAS_IN_PAGE.search(html)
    hits = property_hits(html)
    record.update(
        {
            "status": "resolved",
            "webbook_id": matched,
            "page_inchikey": inchikey,
            "cas": cas.group(1) if cas else "",
            "page_bytes": len(html),
            "property_hits": hits,
            "page_url": f"{CBOOK}?ID={matched}&Units=SI",
        }
    )
    return record


def probe_unsupported_query_form(
    inchikey: str, cache_dir: Path, *, refresh: bool = False
) -> dict[str, object]:
    """Record the status of a query form the site is not known to accept.

    A rejected response never reaches the body cache, so the status code itself
    is cached to keep re-runs at zero requests.
    """

    url = f"{CBOOK}?InChIKey={urllib.parse.quote(inchikey)}&Units=SI"
    status_cache = cache_dir / f"inchikey_form_{inchikey}.status.json"
    if status_cache.is_file() and not refresh:
        cached = json.loads(status_cache.read_text(encoding="utf-8"))
        return {"url": url, **cached}
    try:
        body = fetch(url, cache_dir / f"inchikey_form_{inchikey}.html", refresh=refresh)
    except urllib.error.HTTPError as exc:
        outcome: dict[str, object] = {"http_status": exc.code, "accepted": False}
    else:
        outcome = {"http_status": 200, "accepted": True, "body_bytes": len(body)}
    status_cache.parent.mkdir(parents=True, exist_ok=True)
    status_cache.write_text(
        json.dumps(outcome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"url": url, **outcome}


def run(
    *,
    cache_dir: Path = DEFAULT_CACHE,
    output_path: Path = DEFAULT_OUTPUT,
    refresh: bool = False,
    sleep_seconds: float = 0.2,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    for group, entries in (("target", TARGETS), ("control", CONTROLS)):
        for name, inchikey, role in entries:
            record = probe_compound(
                name, inchikey, role, cache_dir, refresh=refresh
            )
            record["group"] = group
            records.append(record)
            time.sleep(sleep_seconds)

    targets = [r for r in records if r["group"] == "target"]
    controls = [r for r in records if r["group"] == "control"]

    def with_facet(rows: list[dict[str, object]]) -> list[str]:
        return [str(r["name"]) for r in rows if any(int(v) for v in r["property_hits"].values())]

    payload: dict[str, object] = {
        "probe": "g1plus_nist_webbook",
        "source": "NIST Chemistry WebBook, SRD 69",
        "url": "https://webbook.nist.gov/chemistry/",
        "method": {
            "accepted_query_forms": ["Name=", "ID="],
            "unsupported_query_form": probe_unsupported_query_form(
                TARGETS[0][1], cache_dir, refresh=refresh
            ),
            "identity_gate": "page-embedded inChIKey must equal the dataset InChIKey",
            "property_test": "case-insensitive count of "
            + " / ".join(PROPERTY_PATTERNS)
            + " over the whole compound page",
            "positive_controls": [name for name, _, _ in CONTROLS],
        },
        "summary": {
            "target_count": len(targets),
            "control_count": len(controls),
            "targets_resolved": [
                str(r["name"]) for r in targets if r["status"] == "resolved"
            ],
            "targets_unresolved": [
                str(r["name"]) for r in targets if r["status"] != "resolved"
            ],
            "targets_with_dielectric_facet": with_facet(targets),
            "controls_with_dielectric_facet": with_facet(controls),
        },
        "records": records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # `.gitattributes` normalises this file to LF, so it must be written as LF:
    # a CRLF working copy would report a raw sha256 that no clean checkout has.
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.2)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = run(
        cache_dir=args.cache_dir,
        output_path=args.output,
        refresh=args.refresh,
        sleep_seconds=args.sleep,
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
