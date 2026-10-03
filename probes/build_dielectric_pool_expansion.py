"""Build the Week 17 training-pool expansion table and its xTB feature block.

Two products, both under data/processed/:

* dielectric_pool_expansion_observations.csv -- the admitted near-room
  observations, one unified 16-column schema, one row per (compound, T_K);
* dielectric_pool_expansion_features.csv -- the frozen xTB physical columns for
  every compound in that table, copied from the released block where the
  compound already has a row and computed here where it does not.

The admission gates are the pre-registered ones.  They are applied here *and*
re-applied by dielectric_pool_expansion_benchmark.py, so a row that slips past
this builder still cannot reach the fit.

Tracks read (each may be absent; a missing track is reported, not invented):

* nbs514        -- built here from the NBS Circular 514 transcription
* pubchem_eps   -- data/raw/pubchem_eps/pugview_eps.csv
* open_data_eps -- data/raw/open_data_eps/eps_observations.csv
* reaxys        -- data/raw/reaxys_w17f/observations.csv

Run:
    .venv/Scripts/python.exe probes/build_dielectric_pool_expansion.py
    .venv/Scripts/python.exe probes/build_dielectric_pool_expansion.py --tracks-only
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
import numpy as np
from dielectric_lowfreq_gate_probe import (
    PRIMARY_FREQUENCY_CAP_MHZ,
    ROOM_TEMPERATURE_RANGE_K,
)
from dielectric_representation_ablation import PHYSICAL_COLUMNS, read_csv_rows
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

FROZEN_FEATURES_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
)
OBSERVATIONS_OUT = (
    REPOSITORY_ROOT / "data" / "processed" / "dielectric_pool_expansion_observations.csv"
)
FEATURES_OUT = REPOSITORY_ROOT / "data" / "processed" / "dielectric_pool_expansion_features.csv"
SUMMARY_OUT = REPOSITORY_ROOT / "probes" / "dielectric_pool_expansion_build_summary.json"

NBS_TRACK_DIR = REPOSITORY_ROOT / "data" / "raw" / "nbs514_expansion"
NBS_RESOLVED_PATH = NBS_TRACK_DIR / "resolved_all.json"
NBS_TRACK_PATH = NBS_TRACK_DIR / "expansion_observations.csv"
NBS514_URL = "https://nvlpubs.nist.gov/nistpubs/Legacy/circ/nbscircular514.pdf"
NBS514_DOI = "10.6028/nbs.circ.514"
NBS514_LICENSE = "public domain (US Government work, NIST Circular 514)"

PUBVIEW_PATH = REPOSITORY_ROOT / "data" / "raw" / "pubchem_eps" / "pugview_eps.csv"
OPEN_DATA_PATH = REPOSITORY_ROOT / "data" / "raw" / "open_data_eps" / "eps_observations.csv"
REAXYS_PATH = REPOSITORY_ROOT / "data" / "raw" / "reaxys_w17f" / "observations.csv"
REAXYS_SMILES_CACHE = REPOSITORY_ROOT / "data" / "raw" / "reaxys_w17f" / "_smiles_cache.json"

NBS514_PARTS = tuple(
    REPOSITORY_ROOT / "data" / "interim" / f"nbs514_organic_part{index}.csv"
    for index in (1, 2, 3, 4)
)

#: NBS rows print a frequency note exactly when the tabulated value is *not* the
#: static permittivity.  That reading is not invented here: of the NBS rows
#: already inside the released dataset every single one is flagged
#: `zero_frequency` and none carries a frequency note
#: (reports/nbs514_frequency_gate_audit.md).
NBS_QUALITY_ALLOWED = ("three_figures", "four_figures")
NBS_ELIGIBILITY_ALLOWED = ("candidate_near_room",)

UNIFIED_COLUMNS = (
    "inchikey",
    "name",
    "smiles",
    "T_K",
    "epsilon",
    "epsilon_unit",
    "frequency_mhz",
    "phase",
    "component_count",
    "expansion_track",
    "source_id",
    "source_url",
    "source_file",
    "source_file_sha256",
    "license",
    "retrieved_at_utc",
)

EPSILON_LOWER_EXCLUSIVE = 1.0
EPSILON_UPPER_INCLUSIVE = 200.0
XTB_SEED = 42


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _load_xtb_script() -> object:
    path = REPOSITORY_ROOT / "scripts" / "run_xtb_physical_features.py"
    spec = importlib.util.spec_from_file_location("xtb_physical_features_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_nbs_track() -> dict[str, object]:
    """Turn the NBS transcription plus the resolved structures into the unified schema."""

    if not NBS_RESOLVED_PATH.is_file():
        return {"status": "missing_resolved_structures", "path": str(NBS_RESOLVED_PATH)}
    resolved = json.loads(NBS_RESOLVED_PATH.read_text(encoding="utf-8"))
    low, high = ROOM_TEMPERATURE_RANGE_K
    retrieved = _utc_now()
    kept: list[dict[str, object]] = []
    dropped: dict[str, int] = defaultdict(int)
    rows_read = 0
    for part in NBS514_PARTS:
        if not part.is_file():
            continue
        part_sha = _sha256_bytes(part.read_bytes())
        for row in read_csv_rows(part):
            rows_read += 1
            source_id = str(row["source_id"])
            reasons: list[str] = []
            entry = resolved.get(source_id)
            if entry is None or str(entry.get("status")) != "resolved":
                reasons.append("structure_not_resolved")
            elif not bool(entry.get("formula_match")):
                reasons.append("formula_mismatch")
            if str(row.get("frequency_note", "")).strip():
                reasons.append("frequency_note_present")
            if str(row.get("source_quality")) not in NBS_QUALITY_ALLOWED:
                reasons.append("source_quality_below_three_figures")
            if str(row.get("eligibility_status")) not in NBS_ELIGIBILITY_ALLOWED:
                reasons.append("eligibility_status_is_not_candidate_near_room")
            try:
                t_k = float(row["T_K"])
            except (TypeError, ValueError):
                t_k = float("nan")
            if not (low <= t_k <= high):
                reasons.append("temperature_out_of_the_room_band")
            try:
                epsilon = float(row["dielectric"])
            except (TypeError, ValueError):
                epsilon = float("nan")
            if not (EPSILON_LOWER_EXCLUSIVE < epsilon <= EPSILON_UPPER_INCLUSIVE):
                reasons.append("epsilon_out_of_range")
            if not str(row.get("section", "")).strip().upper().startswith("C. ORGANIC"):
                reasons.append("not_in_the_organic_liquids_section")
            if reasons:
                dropped["rows_rejected"] += 1
                for reason in reasons:
                    dropped[reason] += 1
                continue
            assert entry is not None
            kept.append(
                {
                    "inchikey": str(entry["inchikey"]),
                    "name": str(row["compound_name"]),
                    "smiles": str(entry["smiles"]),
                    "T_K": f"{t_k:.2f}",
                    "epsilon": str(row["dielectric"]),
                    "epsilon_unit": "dimensionless",
                    "frequency_mhz": "",
                    "phase": "liquid",
                    "component_count": "1",
                    "expansion_track": "nbs514",
                    "source_id": source_id,
                    "source_url": NBS514_URL,
                    "source_file": portable_relative_path(part, root=REPOSITORY_ROOT),
                    "source_file_sha256": part_sha,
                    "license": NBS514_LICENSE,
                    "retrieved_at_utc": retrieved,
                }
            )
    write_csv_rows(NBS_TRACK_PATH, UNIFIED_COLUMNS, kept)
    return {
        "status": "built",
        "rows_read": rows_read,
        "rows_admitted": len(kept),
        "compounds_admitted": len({str(row["inchikey"]) for row in kept}),
        "dropout": {name: int(value) for name, value in sorted(dropped.items())},
        "output": portable_relative_path(NBS_TRACK_PATH, root=REPOSITORY_ROOT),
        "source_doi": NBS514_DOI,
    }


def _smiles_from_pubchem(inchikeys: Sequence[str]) -> dict[str, str]:
    """Resolve a SMILES for key-only tracks; cached so a re-run is offline."""

    import requests

    cache: dict[str, str] = {}
    if REAXYS_SMILES_CACHE.is_file():
        cache = json.loads(REAXYS_SMILES_CACHE.read_text(encoding="utf-8"))
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": "electrolyte-ml/0.0.0 (research)"})
    missing = [key for key in dict.fromkeys(inchikeys) if key not in cache]
    for index, key in enumerate(missing, start=1):
        url = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey/"
            + key
            + "/property/CanonicalSMILES/JSON"
        )
        try:
            response = session.get(url, timeout=30)
            payload = response.json() if response.status_code == 200 else {}
            props = payload.get("PropertyTable", {}).get("Properties", [])
            cache[key] = str(props[0]["CanonicalSMILES"]) if props else ""
        except Exception:
            cache[key] = ""
        if index % 25 == 0:
            time.sleep(0.2)
    REAXYS_SMILES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    write_json_stable(REAXYS_SMILES_CACHE, cache)
    return cache


def read_reaxys_track() -> list[dict[str, object]]:
    if not REAXYS_PATH.is_file():
        return []
    rows = read_csv_rows(REAXYS_PATH)
    wanted = {"dielectric constant", "relative permittivity", "permittivity"}
    epsilon_rows = [
        row for row in rows if str(row.get("property", "")).strip().lower() in wanted
    ]
    smiles = _smiles_from_pubchem([str(row["inchikey"]) for row in epsilon_rows])
    out: list[dict[str, object]] = []
    for row in epsilon_rows:
        key = str(row["inchikey"])
        out.append(
            {
                "inchikey": key,
                "name": str(row.get("substance", "")),
                "smiles": smiles.get(key, ""),
                "T_K": str(row.get("T_K", "")),
                "epsilon": str(row.get("value", "")),
                "epsilon_unit": "dimensionless",
                "frequency_mhz": "",
                "phase": "liquid",
                "component_count": "1",
                "expansion_track": "reaxys",
                "source_id": "reaxys:" + key,
                "source_url": "https://www.reaxys.com/",
                "source_file": portable_relative_path(REAXYS_PATH, root=REPOSITORY_ROOT),
                "source_file_sha256": canonical_text_sha256(REAXYS_PATH),
                "license": "Reaxys terms of use (local, not redistributed)",
                "retrieved_at_utc": _utc_now(),
            }
        )
    return out


def unify_tracks() -> tuple[list[dict[str, object]], dict[str, object]]:
    report: dict[str, object] = {}
    report["nbs514"] = build_nbs_track()

    tracks: list[dict[str, object]] = (
        list(read_csv_rows(NBS_TRACK_PATH)) if NBS_TRACK_PATH.is_file() else []
    )
    for name, path in (("pubchem_eps", PUBVIEW_PATH), ("open_data_eps", OPEN_DATA_PATH)):
        if not path.is_file():
            report[name] = {"status": "missing"}
            continue
        rows = read_csv_rows(path)
        for row in rows:
            row.setdefault("expansion_track", name)
        tracks.extend(rows)
        report[name] = {"status": "read", "rows": len(rows)}

    reaxys = read_reaxys_track()
    report["reaxys"] = {"status": "read" if reaxys else "missing", "rows": len(reaxys)}
    tracks.extend(reaxys)

    low, high = ROOM_TEMPERATURE_RANGE_K
    kept: list[dict[str, object]] = []
    dropped: dict[str, int] = defaultdict(int)
    seen: set[tuple[str, float]] = set()
    for row in tracks:
        reasons: list[str] = []
        key = str(row.get("inchikey", "")).strip()
        if not key:
            reasons.append("no_inchikey")
        try:
            t_k = float(str(row.get("T_K", "")).strip())
        except (TypeError, ValueError):
            t_k = float("nan")
            reasons.append("temperature_not_a_number")
        if not (low <= t_k <= high):
            reasons.append("temperature_out_of_the_room_band")
        try:
            epsilon = float(str(row.get("epsilon", "")).strip())
        except (TypeError, ValueError):
            epsilon = float("nan")
        if not (EPSILON_LOWER_EXCLUSIVE < epsilon <= EPSILON_UPPER_INCLUSIVE):
            reasons.append("epsilon_out_of_range")
        freq_text = str(row.get("frequency_mhz", "")).strip()
        if freq_text:
            try:
                if float(freq_text) > PRIMARY_FREQUENCY_CAP_MHZ:
                    reasons.append("frequency_above_the_primary_cap")
            except ValueError:
                reasons.append("frequency_not_a_number")
        if str(row.get("phase", "")).strip().lower() != "liquid":
            reasons.append("phase_is_not_liquid")
        try:
            if float(str(row.get("component_count", "")).strip()) != 1.0:
                reasons.append("not_a_pure_component")
        except ValueError:
            reasons.append("component_count_unknown")
        if not str(row.get("smiles", "")).strip():
            reasons.append("no_smiles")
        for column in ("source_url", "license", "source_file_sha256"):
            if not str(row.get(column, "")).strip():
                reasons.append("no_" + column)
        if not np.isnan(t_k) and (key, round(t_k, 2)) in seen:
            reasons.append("duplicate_within_the_expansion_block")
        if reasons:
            dropped["rows_rejected"] += 1
            for reason in reasons:
                dropped[reason] += 1
            continue
        seen.add((key, round(t_k, 2)))
        kept.append({column: str(row.get(column, "")) for column in UNIFIED_COLUMNS})

    kept.sort(key=lambda row: (str(row["inchikey"]), float(str(row["T_K"]))))
    write_csv_rows(OBSERVATIONS_OUT, UNIFIED_COLUMNS, kept)
    track_counts = {
        track: sum(1 for row in kept if str(row["expansion_track"]) == track)
        for track in sorted({str(row["expansion_track"]) for row in kept})
    }
    report["unified"] = {
        "rows_in": len(tracks),
        "rows_admitted": len(kept),
        "compounds_admitted": len({str(row["inchikey"]) for row in kept}),
        "dropout": {name: int(value) for name, value in sorted(dropped.items())},
        "tracks": track_counts,
        "output": portable_relative_path(OBSERVATIONS_OUT, root=REPOSITORY_ROOT),
        "output_sha256": canonical_text_sha256(OBSERVATIONS_OUT),
    }
    return kept, report


def _feature_task(payload: tuple[str, str, str]) -> dict[str, object]:
    inchikey, name, smiles = payload
    script = _load_xtb_script()
    xtb_executable = Path(script._resolve_xtb(None))  # type: ignore[attr-defined]
    work_dir = REPOSITORY_ROOT / "data" / "interim" / "xtb_features"
    source = {
        "inchikey": inchikey,
        "name": name,
        "smiles": smiles,
        "T_K": "298.15",
        "dielectric": "",
    }
    try:
        result = script.run_xtb(  # type: ignore[attr-defined]
            smiles=smiles,
            label=inchikey,
            xtb_executable=xtb_executable,
            work_dir=work_dir,
            seed=XTB_SEED,
            timeout_seconds=900,
        )
        row = script._feature_row(source, result)  # type: ignore[attr-defined]
    except Exception as error:
        row = script._error_feature_row(source, str(error))  # type: ignore[attr-defined]
    return dict(row)


def build_features(*, jobs: int) -> dict[str, object]:
    observations = read_csv_rows(OBSERVATIONS_OUT)
    wanted: dict[str, dict[str, str]] = {}
    for row in observations:
        wanted.setdefault(str(row["inchikey"]), row)

    frozen: dict[str, dict[str, str]] = {}
    if FROZEN_FEATURES_PATH.is_file():
        for row in read_csv_rows(FROZEN_FEATURES_PATH):
            if str(row.get("status", "")).strip() == "error":
                continue
            if any(not str(row.get(column, "")).strip() for column in PHYSICAL_COLUMNS):
                continue
            frozen[str(row["inchikey"])] = row

    reused = {key: frozen[key] for key in wanted if key in frozen}
    pending = [
        (key, str(row["name"]), str(row["smiles"]))
        for key, row in sorted(wanted.items())
        if key not in frozen
    ]
    print(
        f"features: {len(reused)} reused from the released block, {len(pending)} to compute",
        flush=True,
    )
    computed: list[dict[str, object]] = []
    if pending:
        with ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
            for index, row in enumerate(pool.map(_feature_task, pending, chunksize=2), start=1):
                computed.append(row)
                if index % 50 == 0:
                    print(f"  xTB features {index}/{len(pending)}", flush=True)

    script = _load_xtb_script()
    fields = script.FEATURE_FIELDS
    rows: list[dict[str, object]] = []
    for _key, row in sorted(reused.items()):
        rows.append({column: str(row.get(column, "")) for column in fields})
    for row in sorted(computed, key=lambda item: str(item["inchikey"])):
        rows.append({column: str(row.get(column, "")) for column in fields})
    write_csv_rows(FEATURES_OUT, fields, rows)
    ok = sum(1 for row in rows if str(row.get("status", "")) in {"ok", "cached"})
    return {
        "compounds_requested": len(wanted),
        "reused_from_the_released_block": len(reused),
        "computed_here": len(computed),
        "rows_written": len(rows),
        "rows_with_every_physical_column": ok,
        "output": portable_relative_path(FEATURES_OUT, root=REPOSITORY_ROOT),
        "output_sha256": canonical_text_sha256(FEATURES_OUT),
    }


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--tracks-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    kept, report = unify_tracks()
    print(
        "unified: {rows_admitted} rows / {compounds_admitted} compounds".format(
            **report["unified"]
        ),
        flush=True,
    )
    if not args.tracks_only:
        report["features"] = build_features(jobs=args.jobs)
    report["generated_at_utc"] = _utc_now()
    report["wall_seconds"] = time.perf_counter() - started
    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    write_json_stable(SUMMARY_OUT, report)
    print(json.dumps(report.get("features", {}), ensure_ascii=False, indent=1))
    print("summary: " + str(SUMMARY_OUT))
    return 0 if kept else 1


if __name__ == "__main__":
    raise SystemExit(main())