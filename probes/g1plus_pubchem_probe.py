"""Probe PubChem for dielectric-constant evidence on the G1+ target set.

Appendix J of the execution manual ranks PubChem as a tier-1 free source and
states that its Experimental Properties section deposits Riddick handbook
dielectric data, naming ethylene carbonate as the worked example. This probe
tests that claim compound by compound instead of assuming it, and records what
each record actually contains:

- standard_values    - entries that state a dielectric *number* ("dielectric
                       constant: 43.3", "dielectric constant = 42.0 at 0 C, ...").
                       These are the only values that can be cited from PubChem
                       itself, and the number is parsed out rather than assumed
                       from the presence of the word.
- narrative_hits     - strings that mention the dielectric constant without
                       attaching a number. The ethylene carbonate page is the
                       worked case: it cites Riddick for a purification step
                       performed *in order to* measure the dielectric constant,
                       which is not a dielectric value and must never be filed
                       as one.
- springer_links     - SpringerMaterials Properties entries. PubChem stores only
                       a deep link there, so the number itself lives behind the
                       SpringerMaterials login rather than in PubChem.
- riddick_references - references citing Riddick et al., with the count so a
                       record that carries the handbook for some other property
                       is not mistaken for a dielectric source.

Every compound is resolved by InChIKey, so a name collision can never be
recorded as evidence for the wrong substance; the name lookup is kept only as a
cross-check on whether the obvious name page is the same record. Raw responses
are cached under data/external/g1plus/pubchem/ (git-ignored) so the JSON
artefact is reproducible without re-spending calls.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

PUG_REST = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUG_VIEW = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound"
USER_AGENT = "electrolyte-ml-research/1.0 (local reproducibility probe)"

DEFAULT_CACHE = REPOSITORY_ROOT / "data" / "external" / "g1plus" / "pubchem"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "probes" / "g1plus_pubchem_evidence.json"

# (dataset name, dataset InChIKey, role)
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


DIELECTRIC_CLAUSE = re.compile(
    r"dielectric\s+constant\s*[:=]\s*([^;]*)", re.IGNORECASE
)
# A clause such as "42.0 at 0 C, 38.8 at 20 C" states values and their
# temperatures together, and a clause may also carry a frequency note. The
# segments are parsed one at a time and each segment must be consumed whole, so
# a scanning regex cannot mistake a trailing "298 K" or "1 kHz" for a second
# dielectric constant.
VALUE_SEGMENT = re.compile(
    r"^\s*(?P<value>\d+(?:\.\d+)?)"
    r"(?:\s*(?:at|@)\s*(?P<temperature>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>\u00b0?\s*(?:deg(?:rees?)?)?\s*[CKF]))?"
    r"\s*(?:\((?P<note>[^()]*)\))?\s*\.?\s*$"
)
SPRINGER_HEADING = "springermaterials"


def _cache_is_current(url: str, cache_path: Path) -> bool:
    """A cached body is only trusted when it records the URL it came from."""

    marker = cache_path.with_suffix(cache_path.suffix + ".url")
    if not cache_path.is_file() or not marker.is_file():
        return False
    return marker.read_text(encoding="utf-8").strip() == url


def _drop_cache(cache_path: Path) -> None:
    for candidate in (cache_path, cache_path.with_suffix(cache_path.suffix + ".url")):
        if candidate.is_file():
            candidate.unlink()


def fetch(url: str, cache_path: Path, *, refresh: bool = False, attempts: int = 4) -> str:
    """Return the response body, caching it so re-runs cost no calls.

    The cache carries the URL it was retrieved from, so a stale or mis-keyed
    file cannot be served as evidence for a different request.
    """

    if not refresh and _cache_is_current(url, cache_path):
        return cache_path.read_text(encoding="utf-8")
    last: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code in {404, 400}:
                _drop_cache(cache_path)
                raise
            last = exc
        except urllib.error.URLError as exc:
            last = exc
        else:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(body, encoding="utf-8")
            cache_path.with_suffix(cache_path.suffix + ".url").write_text(
                url + "\n", encoding="utf-8"
            )
            return body
        time.sleep(1.5 * (attempt + 1))
    raise last if last is not None else RuntimeError(f"unreachable: {url}")


def resolve_cid(field: str, value: str, cache_dir: Path, *, refresh: bool = False) -> str | None:
    slug = urllib.parse.quote(value, safe="")
    try:
        text = fetch(
            f"{PUG_REST}/compound/{field}/{slug}/cids/TXT",
            cache_dir / f"{field}_{slug}.cids.txt",
            refresh=refresh,
        )
    except urllib.error.HTTPError as exc:
        # Only a 404 means the record does not exist. A 429 or 5xx is a
        # transient failure and must never be filed as an absence.
        if exc.code == 404:
            return None
        raise
    cids = [line.strip() for line in text.splitlines() if line.strip()]
    return cids[0] if cids else None


def resolve_inchikey(cid: str, cache_dir: Path, *, refresh: bool = False) -> str:
    try:
        return fetch(
            f"{PUG_REST}/compound/cid/{cid}/property/InChIKey/TXT",
            cache_dir / f"cid{cid}.inchikey.txt",
            refresh=refresh,
        ).strip()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return ""
        raise


def iter_sections(node: object):
    """Yield every Section dict anywhere in a PUG-View record."""

    if isinstance(node, Mapping):
        if "TOCHeading" in node:
            yield node
        for value in node.values():
            yield from iter_sections(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_sections(value)


def _strings(node: object) -> list[str]:
    found: list[str] = []

    def walk(item: object) -> None:
        if isinstance(item, Mapping):
            for key, value in item.items():
                if key == "String" and isinstance(value, str):
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    walk(node)
    return found


def _measurement_from_segment(segment: str) -> dict[str, object] | None:
    """Parse one comma-separated segment of a dielectric clause.

    Returns `None` when the segment is not exactly a value with an optional,
    explicitly unit-bearing temperature and an optional parenthetical note. A
    segment that fails this test is never guessed at: the caller records it for
    human review instead.
    """

    match = VALUE_SEGMENT.match(segment)
    if match is None:
        return None
    unit = (match.group("unit") or "").replace(" ", "").replace("\u00b0", "")
    unit = unit.replace("degrees", "C").replace("degree", "C").replace("deg", "C")
    temperature = (
        float(match.group("temperature")) if match.group("temperature") else None
    )
    return {
        "value": float(match.group("value")),
        "temperature": temperature,
        "temperature_unit": unit or None,
        # Only a Celsius source fills temperature_C; a kelvin reading is kept as
        # kelvin rather than silently converted.
        "temperature_C": temperature if unit == "C" else None,
        "note": (match.group("note") or "").strip(),
    }


def _dielectric_mentions(section: Mapping[str, object]) -> list[dict[str, object]]:
    """Split dielectric strings in this section into values and mere mentions.

    A string only counts as a value when it reads `dielectric constant <sep>
    <number>`. PubChem also uses the phrase in prose (purification routines
    performed *for* a dielectric study) and as a bare SpringerMaterials heading,
    and neither carries a measurable number. Report them, but never as values.
    """

    mentions: list[dict[str, object]] = []
    information = section.get("Information", [])
    entries = information if isinstance(information, list) else [information]
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        value = entry.get("Value")
        for text in _strings(value):
            if "dielectric" not in text.lower():
                continue
            clause = DIELECTRIC_CLAUSE.search(text)
            measurements: list[dict[str, object]] = []
            unparsed: list[str] = []
            if clause:
                for segment in re.split(r"[,;]", clause.group(1)):
                    if not segment.strip():
                        continue
                    measurement = _measurement_from_segment(segment)
                    if measurement is not None:
                        measurements.append(measurement)
                    elif any(character.isdigit() for character in segment):
                        unparsed.append(segment.strip())
            references = entry.get("Reference", [])
            mentions.append(
                {
                    "section": section.get("TOCHeading", ""),
                    "string": text,
                    "clause": clause.group(1).strip() if clause else "",
                    "measurements": measurements,
                    "values": [item["value"] for item in measurements],
                    "unparsed_segments": unparsed,
                    "references": [
                        str(reference)
                        for reference in (
                            references if isinstance(references, list) else [references]
                        )
                    ],
                }
            )
    return mentions

def _springer_links(section: Mapping[str, object]) -> dict[str, dict[str, str]]:
    """Map substance id -> link for the dielectric facet of this section."""

    links: dict[str, dict[str, str]] = {}

    def walk(node: object) -> None:
        if isinstance(node, Mapping):
            url = node.get("URL")
            facet = node.get("String")
            if isinstance(url, str) and "materials.springer.com" in url:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
                property_facet = (query.get("propertyFacet") or [""])[0]
                substance_id = (query.get("substanceId") or [""])[0]
                if "dielectric" in property_facet.lower() and substance_id:
                    links[substance_id] = {
                        "property": facet if isinstance(facet, str) else "",
                        "property_facet": property_facet,
                        "substance_id": substance_id,
                        "url": url,
                    }
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(section)
    return links


def _riddick_references(section: Mapping[str, object]) -> list[str]:
    refs: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key in {"Reference", "Citation"} and isinstance(value, str):
                    if "Riddick" in value:
                        refs.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(section)
    return refs


def probe_target(
    name: str,
    inchikey: str,
    role: str,
    cache_dir: Path,
    *,
    refresh: bool = False,
) -> dict[str, object]:
    record: dict[str, object] = {
        "name": name,
        "dataset_inchikey": inchikey,
        "dataset_role": role,
    }
    cid = resolve_cid("inchikey", inchikey, cache_dir, refresh=refresh)
    record["cid"] = cid
    if cid is None:
        record["status"] = "inchikey_not_in_pubchem"
        return record

    resolved = resolve_inchikey(cid, cache_dir, refresh=refresh)
    record["pubchem_inchikey"] = resolved
    record["identification_ok"] = resolved == inchikey
    name_cid = resolve_cid("name", name, cache_dir, refresh=refresh)
    record["name_lookup_cid"] = name_cid
    record["name_lookup_agrees"] = name_cid == cid

    if resolved != inchikey:
        # An unidentified record is not evidence about this substance, so it
        # must not be allowed to contribute a value or a link.
        record.update(
            {
                "status": "identity_unconfirmed",
                "standard_values": [],
                "standard_value_count": 0,
                "narrative_hits": [],
                "narrative_hit_count": 0,
                "unparsed_clauses": [],
                "unparsed_clause_count": 0,
                "springer_dielectric_links": [],
            }
        )
        return record

    try:
        payload = json.loads(
            fetch(
                f"{PUG_VIEW}/{cid}/JSON",
                cache_dir / f"cid{cid}.view.json",
                refresh=refresh,
            )
        )
    except urllib.error.HTTPError as exc:
        record["status"] = f"pug_view_error_{exc.code}"
        return record

    standard_values: list[dict[str, object]] = []
    narrative_hits: list[dict[str, object]] = []
    unparsed_clauses: list[dict[str, object]] = []
    springer: dict[str, dict[str, str]] = {}
    for section in iter_sections(payload):
        heading = str(section.get("TOCHeading", ""))
        is_springer = SPRINGER_HEADING in heading.lower().replace(" ", "")
        if is_springer:
            springer.update(_springer_links(section))
        else:
            for mention in _dielectric_mentions(section):
                if mention["unparsed_segments"]:
                    unparsed_clauses.append(mention)
                elif mention["values"]:
                    standard_values.append(mention)
                else:
                    narrative_hits.append(mention)
    # `iter_sections` yields nested sections as well as their parents, so walking
    # each yielded section would count a nested citation once per ancestor. Walk
    # the payload exactly once instead.
    riddick = _riddick_references(payload)

    record.update(
        {
            "status": "ok",
            "standard_values": standard_values,
            "standard_value_count": len(standard_values),
            "narrative_hits": narrative_hits,
            "narrative_hit_count": len(narrative_hits),
            "unparsed_clauses": unparsed_clauses,
            "unparsed_clause_count": len(unparsed_clauses),
            "springer_dielectric_links": [springer[key] for key in sorted(springer)],
            "riddick_reference_occurrences": len(riddick),  # over the whole payload, once
            "riddick_distinct_references": sorted(set(riddick)),
        }
    )
    return record


def run(
    *,
    targets: tuple[tuple[str, str, str], ...] = TARGETS,
    cache_dir: Path = DEFAULT_CACHE,
    output_path: Path = DEFAULT_OUTPUT,
    refresh: bool = False,
    sleep_seconds: float = 0.2,
) -> dict[str, object]:
    records = []
    for name, inchikey, role in targets:
        records.append(probe_target(name, inchikey, role, cache_dir, refresh=refresh))
        time.sleep(sleep_seconds)

    payload = {
        "schema_version": 2,
        "probe": "pubchem_dielectric_tier1",
        "source": "PubChem PUG-REST + PUG-View (https://pubchem.ncbi.nlm.nih.gov)",
        "retrieval": (
            "urllib with a descriptive User-Agent; responses cached under "
            "data/external/g1plus/pubchem/"
        ),
        "target_count": len(records),
        "summary": {
            "with_standard_dielectric_value": [
                r["name"] for r in records if r.get("standard_value_count")
            ],
            "with_springer_materials_dielectric_link": [
                r["name"] for r in records if r.get("springer_dielectric_links")
            ],
            "with_narrative_mention_only": [
                r["name"] for r in records if r.get("narrative_hit_count")
            ],
            "with_unparsed_numeric_clause": [
                r["name"] for r in records if r.get("unparsed_clause_count")
            ],
            "without_any_dielectric_evidence": [
                r["name"]
                for r in records
                if r.get("status") == "ok"
                and not r.get("standard_value_count")
                and not r.get("narrative_hit_count")
                and not r.get("unparsed_clause_count")
                and not r.get("springer_dielectric_links")
            ],
            "records_not_ok": [
                {"name": r["name"], "status": r.get("status")}
                for r in records
                if r.get("status") != "ok"
            ],
            "not_in_pubchem": [
                r["name"] for r in records if r.get("status") == "inchikey_not_in_pubchem"
            ],
            "identification_failures": [
                r["name"] for r in records if r.get("identification_ok") is False
            ],
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
