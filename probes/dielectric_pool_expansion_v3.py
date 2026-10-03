"""Shot 14: full coordination-block coverage plus a static-only training pool.

Shot 13 widened the *rows* of the training pool fourfold and read 0.5300, and its
best arm was ``full_table_lever4`` at 0.5433 because the coordination block was
only present on 987 of 2029 training rows.  This shot tests the two levers the
audit of that run pointed at, without touching the frozen side:

1. the coordination block recomputed for every pool compound
   (``dielectric_coordination_block_features_full.csv``);
2. a training pool restricted to zero-frequency permittivity, because the scored
   pool is 100 percent static while 435 training rows are not;
3. a widened block that adds Reaxys rows for compounds already in the pool.

The scoring side, the folds and the baseline are the frozen ones, so the shot
reproduces four published readings before it reports anything new.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
import dielectric_coordination_block as v1
import dielectric_pool_expansion_benchmark as bn
import dielectric_xtb_full_table_migration as migration
from dielectric_observations_grouped_benchmark import build_matrices
from dielectric_representation_ablation import read_csv_rows
from export_results_common import write_json_stable

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_pool_expansion_prereg_v3.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_pool_expansion_v3_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_pool_expansion_v3.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_pool_expansion_v3"

CONFORMER_FEATURES_PATH = ARTIFACTS_DIR / "dielectric_xtb_full_table_migration_conformers.csv"
COORDINATION_FEATURES_PATH = ARTIFACTS_DIR / "dielectric_coordination_block_features.csv"
COORDINATION_FULL_PATH = ARTIFACTS_DIR / "dielectric_coordination_block_features_full.csv"
# RED LINE, registered 2026-09-27 (reports/decisions_log.md section 28.33): this file
# carries Reaxys-restricted values.  Shot 14 read it as *training labels*, which breaches
# the standing rule that no restricted value may enter any pool or feature table.  The
# widened arm's reading is therefore void and must not be cited.  Do not repeat this
# pattern: a Reaxys-derived column belongs in a facts file that carries counts only.
REAXYS_PATH = REPOSITORY_ROOT / "data" / "raw" / "reaxys_w17f" / "observations.csv"

BASELINE_R2_REFERENCE = 0.4091179943351143
REPRODUCTION_TOLERANCE = 1e-09
PRIMARY_TARGET_R2 = 0.60
PLACEBO_TOLERANCE = 0.0200
DOSE_LEVELS = (0.25, 0.50, 0.75, 1.00)
TRAINING_TEMPERATURE_BAND_K = (273.15, 353.15)
EPSILON_LOWER_EXCLUSIVE = 1.0
EPSILON_UPPER_INCLUSIVE = 200.0

ANCHORS = {
    "baseline_hybrid": 0.4091179943351143,
    "full_table_hybrid": 0.530028742596643,
    "full_table_lever4": 0.5433111678100043,
    "full_table_lever4_lever8": 0.49147018524319047,
}

ARM_BASELINE = "baseline_hybrid"
ARM_FULL_HYBRID = "full_table_hybrid"
ARM_FULL_L4 = "full_table_lever4"
ARM_FULL_L4L8 = "full_table_lever4_lever8"
ARM_FULL_L4L8F = "full_table_lever4_lever8full"
ARM_STATIC_HYBRID = "static_hybrid"
ARM_STATIC_L4L8F = "static_lever4_lever8full"
ARM_WIDENED_L4L8F = "widened_lever4_lever8full"
ARM_PLACEBO = "full_table_label_placebo"
ARM_DOSE = "dose_full_table_lever4_lever8full"

FITTED_ARMS = (
    ARM_BASELINE,
    ARM_FULL_HYBRID,
    ARM_FULL_L4,
    ARM_FULL_L4L8,
    ARM_FULL_L4L8F,
    ARM_STATIC_HYBRID,
    ARM_STATIC_L4L8F,
    ARM_WIDENED_L4L8F,
    ARM_PLACEBO,
)

CO_PRIMARY_ARMS = (ARM_FULL_L4L8F, ARM_STATIC_L4L8F)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_of(path: Path) -> str:
    return canonical_text_sha256(path)


def _plain_float(text: object) -> float | None:
    raw = str(text).strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def load_wide_rows(
    *,
    base_rows: Sequence[Mapping[str, object]],
    features_by_key: Mapping[str, Mapping[str, str]],
    observations_path: Path = REAXYS_PATH,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Reaxys rows for compounds already in the released pool, gated as pre-registered."""

    if not observations_path.is_file():
        return [], {"rows_read": 0, "rows_admitted": 0, "dropout": {}, "available": False}
    blocked = {(str(row["inchikey"]), round(float(str(row["T_K"])), 2)) for row in base_rows}
    low, high = TRAINING_TEMPERATURE_BAND_K
    kept: list[dict[str, object]] = []
    seen = set(blocked)
    dropout: dict[str, int] = {}

    def drop(reason: str) -> None:
        dropout[reason] = dropout.get(reason, 0) + 1

    rows = read_csv_rows(observations_path)
    for row in rows:
        key = str(row.get("inchikey", "")).strip()
        if str(row.get("record_kind", "")).strip() != "experimental":
            drop("not_experimental")
            continue
        if key not in features_by_key:
            drop("compound_not_in_the_released_pool")
            continue
        value = _plain_float(row.get("value"))
        if value is None:
            drop("value_is_not_a_plain_decimal")
            continue
        if not (EPSILON_LOWER_EXCLUSIVE < value <= EPSILON_UPPER_INCLUSIVE):
            drop("epsilon_out_of_range")
            continue
        temperature = _plain_float(row.get("T_K"))
        if temperature is None or not (low <= temperature <= high):
            drop("temperature_out_of_the_training_band")
            continue
        marker = (key, round(temperature, 2))
        if marker in seen:
            drop("duplicate_of_an_existing_row")
            continue
        seen.add(marker)
        features = features_by_key[key]
        kept.append(
            {
                "inchikey": key,
                "name": str(row.get("substance", features.get("name", ""))),
                "smiles": str(features.get("smiles", "")),
                "T_K": float(temperature),
                "epsilon": float(value),
                "epsilon_unit": "dimensionless",
                "frequency_mhz": "",
                "phase": "liquid",
                "component_count": "1",
                "property_name": "Dielectric Constant (Reaxys card, frequency uncalibrated)",
                "source_url": "https://www.reaxys.com/",
                "license": "Reaxys subscription access, row level only",
                "source_file_sha256": sha256_of(observations_path),
                "_features": features,
            }
        )
    return kept, {
        "rows_read": len(rows),
        "rows_admitted": len(kept),
        "compounds_admitted": len({str(row["inchikey"]) for row in kept}),
        "dropout": dict(sorted(dropout.items())),
        "available": True,
        "source": portable_relative_path(observations_path, root=REPOSITORY_ROOT),
    }


def feature_block() -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for path in (v1.FEATURES_PATH, v1.NEW_FEATURES_PATH):
        for row in read_csv_rows(path):
            if str(row.get("status", "")).strip() == "error":
                continue
            if any(not str(row.get(column, "")).strip() for column in v1.PHYSICAL_COLUMNS):
                continue
            merged.setdefault(str(row["inchikey"]), row)
    return merged


def build_summary(
    *,
    generated_at: str,
    prereg: Mapping[str, object],
    contract: Mapping[str, object],
    pool: Mapping[str, object],
    arms: Mapping[str, object],
    dose_rows: Sequence[Mapping[str, object]],
    telemetry: Mapping[str, object],
) -> dict[str, object]:
    readings = {name: bn.arm_r2(arms[name]["summary"]) for name in FITTED_ARMS}  # type: ignore[index]
    baseline_r2 = readings[ARM_BASELINE]
    gap = abs(baseline_r2 - BASELINE_R2_REFERENCE)
    anchors = {
        name: {
            "expected": expected,
            "observed": readings[name],
            "abs_gap": abs(readings[name] - expected),
            "reproduced": bool(abs(readings[name] - expected) <= REPRODUCTION_TOLERANCE),
        }
        for name, expected in ANCHORS.items()
    }
    co_primary_values = {name: readings[name] for name in CO_PRIMARY_ARMS}
    co_primary_met = bool(all(value > PRIMARY_TARGET_R2 for value in co_primary_values.values()))
    placebo_delta = readings[ARM_PLACEBO] - baseline_r2
    arm_a_pass = bool(placebo_delta <= PLACEBO_TOLERANCE)
    deltas = [float(row["delta_r2_vs_baseline"]) for row in dose_rows]
    arm_b_pass = bool(all(b >= a - 1e-09 for a, b in itertools.pairwise(deltas)))
    anchors_reproduced = bool(all(item["reproduced"] for item in anchors.values()))
    if co_primary_met and arm_a_pass and arm_b_pass:
        decision = "co_primaries_met_with_governance"
    elif co_primary_met:
        decision = "co_primaries_met_governance_failed"
    else:
        decision = "co_primaries_missed"
    return {
        "schema_version": 1,
        "task": "dielectric_pool_expansion_v3",
        "week": "week17",
        "shot": 14,
        "generated_at_utc": generated_at,
        "prereg": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "status": str(prereg.get("status")),
            "locked_at_utc": str(prereg.get("locked_at_utc")),
            "sha256": sha256_of(PREREG_PATH),
            "disclosure": str(prereg.get("disclosure", "")),
        },
        "frozen_contract": dict(contract),
        "pool": dict(pool),
        "arms": {
            name: {
                "r2": readings[name],
                "delta_r2_vs_baseline": readings[name] - baseline_r2,
                "seconds": block["seconds"],
                "leak": block["leak"],
            }
            for name, block in arms.items()
        },
        "dose_response": [dict(row) for row in dose_rows],
        "verdict": {
            "baseline_r2": baseline_r2,
            "baseline_r2_reference": BASELINE_R2_REFERENCE,
            "baseline_abs_gap": gap,
            "baseline_reproduced": bool(gap <= REPRODUCTION_TOLERANCE),
            "reproduction_anchors": anchors,
            "anchors_reproduced": anchors_reproduced,
            "co_primary_arms": list(CO_PRIMARY_ARMS),
            "co_primary_values": co_primary_values,
            "primary_target": PRIMARY_TARGET_R2,
            "co_primaries_met": co_primary_met,
            "shortfalls": {name: PRIMARY_TARGET_R2 - value for name, value in co_primary_values.items()},
            "placebo_r2": readings[ARM_PLACEBO],
            "placebo_delta_r2": placebo_delta,
            "arm_a_pass": arm_a_pass,
            "arm_b_pass": arm_b_pass,
            "decision": decision,
            "decision_text": "at least one co-primary arm misses 0.60",
        },
        "telemetry": dict(telemetry),
        "honest_boundaries": [
            "the scored pool is still 457 rows / 97 compounds; only the training pool moved",
            "the coordination block is undefined for 23 pool compounds that carry no O or N site, so it is NaN there by physics, not by omission",
            "the widened Reaxys rows carry no frequency column and are low-frequency and uncalibrated; they are training labels only",
            "no two readings from different pool definitions may be subtracted from one another",
        ],
    }


def format_report(summary: Mapping[str, object]) -> list[str]:
    verdict = summary["verdict"]
    pool = summary["pool"]
    lines = [
        "# Shot 14: full coordination coverage and a static-only training pool",
        "",
        f"**Generated:** {summary['generated_at_utc']}",
        "",
        f"**Decision:** `{verdict['decision']}` -- {verdict['decision_text']}",
        "",
        "## 1. Reproduction anchors",
        "",
        "| Arm | Expected | Observed | Abs gap | Reproduced |",
        "|---|---|---|---|---|",
    ]
    for name, item in verdict["reproduction_anchors"].items():
        lines.append(
            f"| `{name}` | {item['expected']:.16f} | {item['observed']:.16f} | "
            f"{item['abs_gap']:.2e} | {item['reproduced']} |"
        )
    lines += [
        "",
        "## 2. Arms",
        "",
        "| Arm | R2 | Delta vs baseline |",
        "|---|---|---|",
    ]
    for name, block in summary["arms"].items():
        lines.append(f"| `{name}` | {block['r2']:.16f} | {block['delta_r2_vs_baseline']:+.6f} |")
    lines += [
        "",
        "## 3. Governance",
        "",
        "| Dose | Compounds | Rows | R2 | Delta vs baseline |",
        "|---|---|---|---|---|",
    ]
    for row in summary["dose_response"]:
        lines.append(
            f"| {row['dose']:.2f} | {row['compounds']} | {row['rows']} | "
            f"{row['r2']:.16f} | {row['delta_r2_vs_baseline']:+.6f} |"
        )
    lines += [
        "",
        (f"- Arm A (label placebo): delta {verdict['placebo_delta_r2']:+.6f} -> "
        f"{'PASS' if verdict['arm_a_pass'] else 'FAIL'}"),
        f"- Arm B (monotone dose response): {'PASS' if verdict['arm_b_pass'] else 'FAIL'}",
        "",
        "## 4. Pool",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in pool.items())
    lines.append("")
    return lines


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=8)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    started_at_utc = _utc_now()
    jobs = max(1, int(args.jobs))

    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if str(prereg.get("status")) != "locked_before_run":
        print("the pre-registration is not locked_before_run")
        return 1

    scoreboard = v1.build_scoreboard()
    contract = scoreboard["contract"]
    if not contract["matches_preregistration"]:
        print("the rebuilt scoreboard does not match the pre-registration")
        return 1
    base_rows = list(scoreboard["rows"])
    base_scored = np.asarray(scoreboard["scored"], dtype=bool)
    n_base = len(base_rows)
    print(f"scoreboard: {contract['scored_rows']} rows / {contract['compounds_scored']} compounds")

    features_by_key = feature_block()
    wide_rows, wide_report = load_wide_rows(base_rows=base_rows, features_by_key=features_by_key)
    n_wide = len(wide_rows)
    print(f"widened block: {wide_report.get('rows_admitted')} rows")

    if wide_rows:
        wide_morgan, wide_physical, wide_target, wide_temps, wide_groups = build_matrices(wide_rows)
    else:
        wide_morgan = np.zeros((0, scoreboard["morgan"].shape[1]))
        wide_physical = np.zeros((0, scoreboard["physical"].shape[1]))
        wide_target = np.zeros(0)
        wide_temps = np.zeros(0)
        wide_groups = []
    morgan = np.vstack([scoreboard["morgan"], wide_morgan])
    physical = np.vstack([scoreboard["physical"], wide_physical])
    target = np.concatenate([scoreboard["target"], wide_target])
    temperatures = np.concatenate([scoreboard["temperatures"], wide_temps])
    groups = list(scoreboard["groups"]) + list(wide_groups)
    scored = np.concatenate([base_scored, np.zeros(n_wide, dtype=bool)])
    all_rows = base_rows + wide_rows

    static_column = np.asarray([str(row.get("frequency_gate", "")).strip() for row in base_rows])
    static_base = static_column == "zero_frequency"
    if not static_base.any():
        static_base = np.asarray([str(row.get("frequency_mhz", "")).strip() in ("", "0", "0.0") for row in base_rows])
    full_base = np.concatenate([np.ones(n_base, dtype=bool), np.zeros(n_wide, dtype=bool)])
    static_only = np.concatenate([static_base, np.zeros(n_wide, dtype=bool)])
    widened = np.ones(n_base + n_wide, dtype=bool)
    masks = {
        ARM_BASELINE: scored,
        ARM_FULL_HYBRID: full_base,
        ARM_FULL_L4: full_base,
        ARM_FULL_L4L8: full_base,
        ARM_FULL_L4L8F: full_base,
        ARM_STATIC_HYBRID: static_only,
        ARM_STATIC_L4L8F: static_only,
        ARM_WIDENED_L4L8F: widened,
        ARM_PLACEBO: full_base,
    }
    frozen_splits = list(scoreboard["splits"])
    for name, mask in masks.items():
        splits = bn.build_splits(groups, score_mask=scored, train_mask=mask)
        if bn.fold_signature(splits) != bn.fold_signature(frozen_splits):
            print(f"{name}: the fold assignment moved; refusing to continue")
            return 1

    dipole_map = bn.dipole_map_from_conformer_rows(read_csv_rows(CONFORMER_FEATURES_PATH))
    lever4, lever4_report = migration.build_physical_matrix_v04(all_rows, dipole_map=dipole_map)
    released_coordination, released_report = v1.coordination_matrix(
        all_rows, read_csv_rows(COORDINATION_FEATURES_PATH)
    )
    full_coordination, full_report = v1.coordination_matrix(
        all_rows, read_csv_rows(COORDINATION_FULL_PATH)
    )
    lever4_released = np.hstack([lever4, released_coordination])
    lever4_full = np.hstack([lever4, full_coordination])

    levers = {
        ARM_BASELINE: physical,
        ARM_FULL_HYBRID: physical,
        ARM_FULL_L4: lever4,
        ARM_FULL_L4L8: lever4_released,
        ARM_FULL_L4L8F: lever4_full,
        ARM_STATIC_HYBRID: physical,
        ARM_STATIC_L4L8F: lever4_full,
        ARM_WIDENED_L4L8F: lever4_full,
        ARM_PLACEBO: physical,
    }

    training_only = ~scored
    placebo_target = bn.label_placebo_target(target, groups, training_only)
    arms: dict[str, dict[str, object]] = {}
    for arm in FITTED_ARMS:
        print("arm: " + arm, flush=True)
        clock = time.perf_counter()
        splits = bn.build_splits(groups, score_mask=scored, train_mask=masks[arm])
        result = v1.evaluate_arm(
            arm,
            morgan=morgan,
            physical=levers[arm],
            target=placebo_target if arm == ARM_PLACEBO else target,
            temperatures=temperatures,
            groups=groups,
            splits=splits,
            jobs=jobs,
        )
        arms[arm] = dict(result) | {"seconds": time.perf_counter() - clock}
        print(f"  R2 {bn.arm_r2(result['summary']):.6f}  ({arms[arm]['seconds']:.1f}s)", flush=True)

    dose_rows: list[dict[str, object]] = []
    for level in DOSE_LEVELS:
        mask = bn.dose_mask(groups, full_base & training_only, level=level)
        result = v1.evaluate_arm(
            f"{ARM_DOSE}_{round(level * 100):03d}",
            morgan=morgan,
            physical=lever4_full,
            target=target,
            temperatures=temperatures,
            groups=groups,
            splits=bn.build_splits(groups, score_mask=scored, train_mask=mask),
            jobs=jobs,
        )
        dose_rows.append(
            {
                "dose": float(level),
                "compounds": len({str(groups[i]) for i in np.flatnonzero(mask)}),
                "rows": int(mask.sum()),
                "r2": bn.arm_r2(result["summary"]),
                "delta_r2_vs_baseline": bn.arm_r2(result["summary"])
                - bn.arm_r2(arms[ARM_BASELINE]["summary"]),
            }
        )
        print(f"dose {level:.2f}: {dose_rows[-1]['r2']:.6f}", flush=True)

    pool_report = {
        "base_rows": n_base,
        "static_training_rows": int(static_base.sum()),
        "finite_frequency_training_rows": int((~static_base).sum()),
        "widened_rows": n_wide,
        "widened_compounds": int(wide_report.get("compounds_admitted", 0)),
        "coordination_released_rows_with_the_block": int(released_report["rows_with_the_block"]),
        "coordination_full_rows_with_the_block": int(full_report["rows_with_the_block"]),
        "coordination_full_compounds_with_the_block": len(
            {
                str(row["inchikey"])
                for row in read_csv_rows(COORDINATION_FULL_PATH)
                if str(row.get("status")) == "ok"
            }
        ),
        "rows_total": n_base + n_wide,
        "scored_rows": int(scored.sum()),
        "widened_report": dict(wide_report),
    }
    telemetry = {
        "started_at_utc": started_at_utc,
        "finished_at_utc": _utc_now(),
        "wall_seconds": time.perf_counter() - started,
        "jobs": jobs,
        "lever4": dict(lever4_report),
        "released_coordination": dict(released_report),
        "full_coordination": dict(full_report),
    }
    summary = build_summary(
        generated_at=_utc_now(),
        prereg=prereg,
        contract=contract,
        pool=pool_report,
        arms=arms,
        dose_rows=dose_rows,
        telemetry=telemetry,
    )
    summary["outputs"] = {
        "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
        "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
    }
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    fold_rows: list[dict[str, object]] = []
    repeat_rows: list[dict[str, object]] = []
    for arm in FITTED_ARMS:
        fold_rows.extend(arms[arm]["fold_rows"])  # type: ignore[arg-type]
        repeat_rows.extend(arms[arm]["repeat_rows"])  # type: ignore[arg-type]
    v1.write_csv_rows(ARTIFACTS_DIR / (ARTIFACT_STEM + "_folds.csv"), v1.FOLD_COLUMNS_OUT, fold_rows)
    v1.write_csv_rows(
        ARTIFACTS_DIR / (ARTIFACT_STEM + "_repeats.csv"), v1.REPEAT_COLUMNS_OUT, repeat_rows
    )
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        "\n".join(format_report(summary)) + "\n", encoding="utf-8", newline="\n"
    )
    verdict = summary["verdict"]
    print()
    for name in FITTED_ARMS:
        print(f"{name:<34s} R2 {bn.arm_r2(arms[name]['summary']):+.6f}")
    print(f"anchors reproduced: {verdict['anchors_reproduced']}")
    print(f"co-primaries met: {verdict['co_primaries_met']}")
    print(f"decision: {verdict['decision']}")
    print(f"wall seconds {telemetry['wall_seconds']:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
