"""Ask the Materials Project whether it can source dielectric data for G1+.

The Materials Project was offered to this project as an alternative route once
the SpringerMaterials interactive view became unavailable. Before spending any
effort on it, the question that actually matters is a narrow one: does the
database hold these molecules at all?

It does carry dielectric information - the summary endpoint exposes `e_total`,
`e_ionic`, `e_electronic` and the refractive index `n` from DFPT - but the
collection is built from inorganic crystals. So this probe does two things:

- queries all 14 G1+ targets by molecular formula, and
- queries one positive control (SiO2) that must have entries, proving the
  endpoint, the key and the requested fields all work.

If the control returns entries and every target returns none, the conclusion is
about the collection's scope, not about a broken query. The API key lives in
`config/materials_project_key.txt`, which is git-ignored; the key is never printed
or written into the evidence. Raw responses are cached under
`data/external/g1plus/materials_project/` so a re-run costs no calls.
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

SUMMARY_ENDPOINT = "https://api.materialsproject.org/materials/summary/"
USER_AGENT = "electrolyte-ml-research/1.0 (local reproducibility probe)"
DEFAULT_KEY_FILE = REPOSITORY_ROOT / "config" / "materials_project_key.txt"
DEFAULT_CACHE = REPOSITORY_ROOT / "data" / "external" / "g1plus" / "materials_project"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "probes" / "g1plus_materials_project_evidence.json"

FIELDS = "material_id,formula_pretty,e_total,e_ionic,e_electronic,n"

KEY_PATTERN = re.compile(r"[A-Za-z0-9_\-]{32}")

# (dataset name, molecular formula)
TARGETS: tuple[tuple[str, str], ...] = (
    ("ethylene carbonate", "C3H4O3"),
    ("propylene carbonate", "C4H6O3"),
    ("vinylene carbonate", "C3H2O3"),
    ("fluoroethylene carbonate", "C3H3FO3"),
    ("gamma-valerolactone", "C5H8O2"),
    ("3-methoxypropionitrile", "C4H7NO"),
    ("adiponitrile", "C6H8N2"),
    ("glutaronitrile", "C5H6N2"),
    ("1,2-dimethoxyethane", "C4H10O2"),
    ("diglyme", "C6H14O3"),
    ("triglyme", "C8H18O4"),
    ("tetraglyme", "C10H22O5"),
    ("sulfolane", "C4H8O2S"),
    ("acetonitrile", "C2H3N"),
)

# A control that must return entries, so an empty target result can be read as
# "out of scope" rather than "query broken".
CONTROL: tuple[str, str] = ("silicon dioxide", "SiO2")


def load_api_key(key_file: Path) -> str:
    """Read the first key-shaped token from the git-ignored key file."""

    if not key_file.is_file():
        raise FileNotFoundError(
            f"no Materials Project key at {key_file}; save it there and retry"
        )
    for line in key_file.read_text(encoding="utf-8").splitlines():
        match = KEY_PATTERN.search(line)
        if match:
            return match.group(0)
    raise ValueError(f"no key-shaped token found in {key_file}")


def query_formula(
    formula: str,
    api_key: str,
    cache_dir: Path,
    *,
    refresh: bool = False,
    limit: int = 5,
) -> dict[str, object]:
    query = urllib.parse.urlencode(
        {"formula": formula, "_fields": FIELDS, "_limit": limit}
    )
    url = f"{SUMMARY_ENDPOINT}?{query}"
    safe = re.sub(r"[^A-Za-z0-9]+", "_", formula)
    cache_path = cache_dir / f"{safe}.json"
    marker = cache_path.with_suffix(cache_path.suffix + ".url")
    if (
        not refresh
        and cache_path.is_file()
        and marker.is_file()
        and marker.read_text(encoding="utf-8").strip() == url
    ):
        return json.loads(cache_path.read_text(encoding="utf-8"))

    request = urllib.request.Request(
        url, headers={"X-API-KEY": api_key, "User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    # The marker carries the exact query (endpoint, fields, limit, formula) so a
    # cached body can never be served for a different question.
    marker.write_text(url + "\n", encoding="utf-8")
    return payload


def probe_formula(
    name: str,
    formula: str,
    api_key: str,
    cache_dir: Path,
    *,
    refresh: bool = False,
    group: str = "target",
) -> dict[str, object]:
    record: dict[str, object] = {
        "name": name,
        "formula": formula,
        "group": group,
    }
    try:
        payload = query_formula(formula, api_key, cache_dir, refresh=refresh)
    except urllib.error.HTTPError as exc:
        if exc.code in {429, 500, 502, 503, 504}:
            # A rate limit or a server error is not evidence of absence. It must
            # abort the run rather than be summarised as "no entries".
            raise RuntimeError(
                f"transient HTTP {exc.code} for {formula}; rerun instead of "
                "recording an absence"
            ) from exc
        record.update({"status": f"http_{exc.code}", "total_doc": None})
        return record

    data = payload.get("data") or []
    record.update(
        {
            "status": "ok",
            "total_doc": (payload.get("meta") or {}).get("total_doc"),
            "returned": len(data),
            "with_dielectric_field": [
                entry.get("material_id")
                for entry in data
                if entry.get("e_total") is not None or entry.get("n") is not None
            ],
            "samples": data[:3],
        }
    )
    return record


def run(
    *,
    key_file: Path = DEFAULT_KEY_FILE,
    cache_dir: Path = DEFAULT_CACHE,
    output_path: Path = DEFAULT_OUTPUT,
    refresh: bool = False,
    sleep_seconds: float = 0.2,
) -> dict[str, object]:
    api_key = load_api_key(key_file)

    control = probe_formula(
        CONTROL[0], CONTROL[1], api_key, cache_dir, refresh=refresh, group="control"
    )
    if control.get("status") != "ok" or not control.get("total_doc"):
        # Without a *populated* control the empty target results prove nothing,
        # so the run must fail rather than emit a reassuring-looking artefact.
        # This covers both a failed control request and a control that
        # unexpectedly returns nothing.
        raise RuntimeError(
            "positive control is not populated "
            f"(status={control.get('status')!r}, total_doc={control.get('total_doc')!r}); "
            "fix the key/endpoint before reading any target result"
        )
    time.sleep(sleep_seconds)
    targets = [
        probe_formula(name, formula, api_key, cache_dir, refresh=refresh)
        for name, formula in TARGETS
    ]
    for _ in TARGETS:
        time.sleep(sleep_seconds)

    def is_ok(record: dict[str, object]) -> bool:
        return record.get("status") == "ok"

    def has_entries(record: dict[str, object]) -> bool:
        return is_ok(record) and bool(record.get("total_doc"))

    def is_confirmed_empty(record: dict[str, object]) -> bool:
        # Only a successful query that reported exactly zero documents may be
        # read as "this collection does not hold the substance". The comparison
        # is strict: an ok response with a missing meta block yields total_doc
        # None, and `not None` would wrongly promote it to a confirmed absence.
        return is_ok(record) and record.get("total_doc") == 0

    payload: dict[str, object] = {
        "schema_version": 1,
        "probe": "g1plus_materials_project",
        "source": "Materials Project API (https://api.materialsproject.org)",
        "retrieval": (
            "urllib with the caller's own X-API-KEY; the key is read from the "
            "git-ignored config/materials_project_key.txt and is never recorded "
            "here. Responses cached under data/external/g1plus/materials_project/"
        ),
        "method": {
            "endpoint": SUMMARY_ENDPOINT,
            "fields": FIELDS.split(","),
            "positive_control": CONTROL[0],
            "control_formula": CONTROL[1],
            "scope_question": (
                "the collection carries DFPT dielectric tensors, so an empty "
                "target result only matters if the control is populated"
            ),
        },
        "summary": {
            "control_status": control.get("status"),
            "control_has_entries": has_entries(control),
            "targets_with_entries": [
                record["name"] for record in targets if has_entries(record)
            ],
            "targets_confirmed_empty": [
                record["name"] for record in targets if is_confirmed_empty(record)
            ],
            "targets_inconclusive": [
                record["name"]
                for record in targets
                if not has_entries(record) and not is_confirmed_empty(record)
            ],
            "target_count": len(targets),
        },
        "records": [control, *targets],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # `.gitattributes` normalises this file to LF, so it must be written as LF: a
    # CRLF working copy would report a raw sha256 that no clean checkout has.
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.2)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = run(
        key_file=args.key_file,
        cache_dir=args.cache_dir,
        output_path=args.output,
        refresh=args.refresh,
        sleep_seconds=args.sleep,
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
