"""Build the high-permittivity anchor block: seven compounds the pool never had.

Shot 14 falsified three levers at once (coordination coverage, a static-only
training pool, and extra Reaxys rows for compounds already in the pool), so the
only mechanism left with a causal story is an *anchor in the high-permittivity
regime*: the scored pool is 457 static rows whose squared error is dominated by a
handful of very polar liquids (N-methylacetamide 178, formamide 106, water 87),
and in the fold that tests one of them every row of that compound leaves the
training set at once, so a tree model has nothing above its training range to
interpolate from.

This builder turns the W17-23 open-data harvest into two artifacts:

* ``dielectric_anchor_observations.csv`` -- the unified 16-column schema, one row
  per (compound, T_K), restricted to compounds the released pool does not have;
* ``dielectric_anchor_features.csv``     -- the frozen xTB physical columns for
  those compounds, computed here through the same pinned-thread runner the
  released block used.

Run:
    .venv/Scripts/python.exe probes/build_dielectric_anchor_blocks.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
import build_dielectric_pool_expansion as builder
import dielectric_coordination_block as v1
from dielectric_representation_ablation import read_csv_rows
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

SOURCE_PATH = REPOSITORY_ROOT / "data" / "raw" / "open_data_eps2" / "observations.csv"
OBSERVATIONS_OUT = REPOSITORY_ROOT / "data" / "processed" / "dielectric_anchor_observations.csv"
FEATURES_OUT = REPOSITORY_ROOT / "data" / "processed" / "dielectric_anchor_features.csv"
SUMMARY_OUT = REPOSITORY_ROOT / "probes" / "dielectric_anchor_build_summary.json"

TRAINING_TEMPERATURE_BAND_K = (273.15, 353.15)
EPSILON_LOWER_EXCLUSIVE = 1.0
EPSILON_UPPER_INCLUSIVE = 200.0
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
    "source_url",
    "license",
    "source_file_sha256",
    "anchor_track",
    "property_name",
)


def _plain_float(text: object) -> float | None:
    raw = str(text).strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def pool_keys() -> set[str]:
    return {str(row["inchikey"]) for row in v1.build_scoreboard()["rows"]}  # type: ignore[index]


def select_rows() -> tuple[list[dict[str, str]], dict[str, int]]:
    blocked = pool_keys()
    low, high = TRAINING_TEMPERATURE_BAND_K
    kept: list[dict[str, str]] = []
    seen: set[tuple[str, float]] = set()
    dropout: dict[str, int] = {}

    def drop(reason: str) -> None:
        dropout[reason] = dropout.get(reason, 0) + 1

    if not SOURCE_PATH.is_file():
        return [], {"source_missing": 1}
    digest = canonical_text_sha256(SOURCE_PATH)
    for row in read_csv_rows(SOURCE_PATH):
        key = str(row.get("inchikey", "")).strip()
        if not key:
            drop("no_inchikey")
            continue
        if key in blocked:
            drop("compound_is_already_in_the_released_pool")
            continue
        smiles = str(row.get("smiles", "")).strip()
        if not smiles:
            drop("no_smiles")
            continue
        value = _plain_float(row.get("epsilon"))
        if value is None or not (EPSILON_LOWER_EXCLUSIVE < value <= EPSILON_UPPER_INCLUSIVE):
            drop("epsilon_out_of_range")
            continue
        temperature = _plain_float(row.get("t_k"))
        if temperature is None or not (low <= temperature <= high):
            drop("temperature_out_of_the_training_band")
            continue
        if str(row.get("phase", "")).strip().lower() != "liquid":
            drop("phase_is_not_liquid")
            continue
        if _plain_float(row.get("component_count")) != 1.0:
            drop("not_a_pure_component")
            continue
        missing = [
            column
            for column in ("source_url", "license", "source_sha256")
            if not str(row.get(column, "")).strip()
        ]
        if missing:
            for column in missing:
                drop("no_" + column)
            continue
        marker = (key, round(temperature, 2))
        if marker in seen:
            drop("duplicate_within_the_anchor_block")
            continue
        seen.add(marker)
        kept.append(
            {
                "inchikey": key,
                "name": str(row.get("name", "")),
                "smiles": smiles,
                "T_K": f"{temperature:.6g}",
                "epsilon": f"{value:.6g}",
                "epsilon_unit": str(row.get("epsilon_unit", "") or "dimensionless"),
                "frequency_mhz": str(row.get("frequency_mhz", "")),
                "phase": "liquid",
                "component_count": "1",
                "source_url": str(row.get("source_url", "")),
                "license": str(row.get("license", "")),
                "source_file_sha256": digest,
                "anchor_track": "open_data_eps2",
                "property_name": "Relative permittivity (open-data harvest W17-23)",
            }
        )
    return kept, dropout


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args(argv)
    started = time.perf_counter()

    kept, dropout = select_rows()
    v1.write_csv_rows(OBSERVATIONS_OUT, UNIFIED_COLUMNS, kept)
    wanted = {str(row["inchikey"]): row for row in kept}
    print(f"anchor rows {len(kept)} / compounds {len(wanted)}", flush=True)

    payloads = [(key, str(row["name"]), str(row["smiles"])) for key, row in sorted(wanted.items())]
    rows: list[dict[str, object]] = []
    if payloads:
        with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            rows = [dict(item) for item in pool.map(builder._feature_task, payloads, chunksize=1)]
    fields = list(builder._load_xtb_script().FEATURE_FIELDS)  # type: ignore[attr-defined]
    v1.write_csv_rows(FEATURES_OUT, tuple(fields), rows)
    ok = sum(1 for row in rows if str(row.get("status")) == "ok")
    payload = {
        "schema_version": 1,
        "task": "dielectric_anchor_blocks",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": portable_relative_path(SOURCE_PATH, root=REPOSITORY_ROOT),
        "rows_admitted": len(kept),
        "compounds_admitted": len(wanted),
        "features_ok": ok,
        "dropout": dict(sorted(dropout.items())),
        "observations": portable_relative_path(OBSERVATIONS_OUT, root=REPOSITORY_ROOT),
        "features": portable_relative_path(FEATURES_OUT, root=REPOSITORY_ROOT),
        "wall_seconds": time.perf_counter() - started,
    }
    write_json_stable(SUMMARY_OUT, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return 0 if kept else 1


if __name__ == "__main__":
    raise SystemExit(main())
