"""Shot 15: a high-permittivity anchor block the released pool never had.

Shot 14 falsified the coordination-coverage lever, the static-only training pool
and the Reaxys widening at once.  The one mechanism it did not touch is the one
the residual analysis points at: the scored pool is 457 static rows whose squared
error is dominated by a handful of very polar liquids (N-methylacetamide 178,
formamide 106, water 87), and the fold that tests one of them removes *every* row
of that compound from training at the same time, so a tree model has no training
label above its own range to interpolate from.

``data/processed/dielectric_anchor_observations.csv`` holds five compounds the
released pool does not contain, from the W17-23 open-data harvest, with the xTB
physical block recomputed for them by the pinned-thread runner.  This shot asks
the narrow question: does a permanent high-permittivity anchor move the frozen
readout?
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

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_anchor_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_anchor_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_anchor.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_anchor"

ANCHOR_OBSERVATIONS_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_anchor_observations.csv"
ANCHOR_FEATURES_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_anchor_features.csv"
CONFORMER_FEATURES_PATH = ARTIFACTS_DIR / "dielectric_xtb_full_table_migration_conformers.csv"

BASELINE_R2_REFERENCE = 0.4091179943351143
FULL_TABLE_LEVER4_REFERENCE = 0.5433111678100043
REPRODUCTION_TOLERANCE = 1e-09
PRIMARY_TARGET_R2 = 0.60
PLACEBO_TOLERANCE = 0.0200
DOSE_LEVELS = (0.25, 0.50, 0.75, 1.00)

ANCHORS = {
    "baseline_hybrid": BASELINE_R2_REFERENCE,
    "full_table_lever4": FULL_TABLE_LEVER4_REFERENCE,
}

ARM_BASELINE = "baseline_hybrid"
ARM_FULL_L4 = "full_table_lever4"
ARM_ANCHOR_HYBRID = "anchors_hybrid"
ARM_ANCHOR_L4 = "anchors_lever4"
ARM_PLACEBO = "anchors_label_placebo"
ARM_DOSE = "dose_anchors_lever4"

FITTED_ARMS = (ARM_BASELINE, ARM_FULL_L4, ARM_ANCHOR_HYBRID, ARM_ANCHOR_L4, ARM_PLACEBO)
CO_PRIMARY_ARMS = (ARM_ANCHOR_L4,)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_of(path: Path) -> str:
    return canonical_text_sha256(path)


def load_anchors(
    *,
    base_rows: Sequence[Mapping[str, object]],
    observations_path: Path = ANCHOR_OBSERVATIONS_PATH,
    features_path: Path = ANCHOR_FEATURES_PATH,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Anchor rows with their xTB block attached, one row per (compound, T_K)."""

    if not observations_path.is_file() or not features_path.is_file():
        return [], {"available": False, "rows_admitted": 0}
    features: dict[str, dict[str, str]] = {}
    for row in read_csv_rows(features_path):
        if str(row.get("status", "")).strip() == "error":
            continue
        if any(not str(row.get(column, "")).strip() for column in v1.PHYSICAL_COLUMNS):
            continue
        features[str(row["inchikey"])] = row
    blocked = {(str(row["inchikey"]), round(float(str(row["T_K"])), 2)) for row in base_rows}
    kept: list[dict[str, object]] = []
    dropout: dict[str, int] = {}
    for row in read_csv_rows(observations_path):
        key = str(row["inchikey"])
        marker = (key, round(float(str(row["T_K"])), 2))
        if marker in blocked:
            dropout["duplicate_of_a_released_row"] = dropout.get("duplicate_of_a_released_row", 0) + 1
            continue
        if key not in features:
            dropout["no_xtb_features"] = dropout.get("no_xtb_features", 0) + 1
            continue
        kept.append({**row, "_features": features[key]})
    return kept, {
        "available": True,
        "rows_admitted": len(kept),
        "compounds_admitted": len({str(row["inchikey"]) for row in kept}),
        "features_available": len(features),
        "dropout": dict(sorted(dropout.items())),
    }


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
    if co_primary_met and arm_a_pass and arm_b_pass:
        decision = "co_primaries_met_with_governance"
    elif co_primary_met:
        decision = "co_primaries_met_governance_failed"
    else:
        decision = "primary_missed"
    return {
        "schema_version": 1,
        "task": "dielectric_anchor",
        "week": "week17",
        "shot": 15,
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
            "baseline_abs_gap": abs(baseline_r2 - BASELINE_R2_REFERENCE),
            "reproduction_anchors": anchors,
            "anchors_reproduced": bool(all(item["reproduced"] for item in anchors.values())),
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
            "decision_text": "the anchor arm misses 0.60" if not co_primary_met else "the anchor arm clears 0.60",
        },
        "telemetry": dict(telemetry),
        "honest_boundaries": [
            "the anchor block is five compounds and five rows; it is an anchor, not a widening",
            "the scored pool is unchanged at 457 rows / 97 compounds",
            "no reading here may be subtracted from a reading measured on another pool definition",
        ],
    }


def format_report(summary: Mapping[str, object]) -> list[str]:
    verdict = summary["verdict"]
    lines = [
        "# Shot 15: a high-permittivity anchor block",
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
            f"| `{name}` | {item['expected']:.16f} | {item['observed']:.16f} | {item['abs_gap']:.2e} | {item['reproduced']} |"
        )
    lines += ["", "## 2. Arms", "", "| Arm | R2 | Delta vs baseline |", "|---|---|---|"]
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
            f"| {row['dose']:.2f} | {row['compounds']} | {row['rows']} | {row['r2']:.16f} | {row['delta_r2_vs_baseline']:+.6f} |"
        )
    lines += [
        "",
        f"- Arm A (label placebo): delta {verdict['placebo_delta_r2']:+.6f} -> {'PASS' if verdict['arm_a_pass'] else 'FAIL'}",
        f"- Arm B (monotone dose response): {'PASS' if verdict['arm_b_pass'] else 'FAIL'}",
        "",
    ]
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

    anchor_rows, anchor_report = load_anchors(base_rows=base_rows)
    n_anchor = len(anchor_rows)
    print(f"anchor block: {anchor_report.get('rows_admitted')} rows / {anchor_report.get('compounds_admitted')} compounds")

    if anchor_rows:
        anchor_morgan, anchor_physical, anchor_target, anchor_temps, anchor_groups = build_matrices(anchor_rows)
    else:
        anchor_morgan = np.zeros((0, scoreboard["morgan"].shape[1]))
        anchor_physical = np.zeros((0, scoreboard["physical"].shape[1]))
        anchor_target = np.zeros(0)
        anchor_temps = np.zeros(0)
        anchor_groups = []
    morgan = np.vstack([scoreboard["morgan"], anchor_morgan])
    physical = np.vstack([scoreboard["physical"], anchor_physical])
    target = np.concatenate([scoreboard["target"], anchor_target])
    temperatures = np.concatenate([scoreboard["temperatures"], anchor_temps])
    groups = list(scoreboard["groups"]) + list(anchor_groups)
    scored = np.concatenate([base_scored, np.zeros(n_anchor, dtype=bool)])
    all_rows = base_rows + anchor_rows

    full_base = np.concatenate([np.ones(n_base, dtype=bool), np.zeros(n_anchor, dtype=bool)])
    with_anchors = np.ones(n_base + n_anchor, dtype=bool)
    masks = {
        ARM_BASELINE: scored,
        ARM_FULL_L4: full_base,
        ARM_ANCHOR_HYBRID: with_anchors,
        ARM_ANCHOR_L4: with_anchors,
        ARM_PLACEBO: with_anchors,
    }
    frozen_splits = list(scoreboard["splits"])
    for name, mask in masks.items():
        splits = bn.build_splits(groups, score_mask=scored, train_mask=mask)
        if bn.fold_signature(splits) != bn.fold_signature(frozen_splits):
            print(f"{name}: the fold assignment moved; refusing to continue")
            return 1

    dipole_map = bn.dipole_map_from_conformer_rows(read_csv_rows(CONFORMER_FEATURES_PATH))
    lever4, lever4_report = migration.build_physical_matrix_v04(all_rows, dipole_map=dipole_map)
    levers = {
        ARM_BASELINE: physical,
        ARM_FULL_L4: lever4,
        ARM_ANCHOR_HYBRID: physical,
        ARM_ANCHOR_L4: lever4,
        ARM_PLACEBO: physical,
    }

    training_only = ~scored
    placebo_target = bn.label_placebo_target(target, groups, training_only)
    arms: dict[str, dict[str, object]] = {}
    for arm in FITTED_ARMS:
        print("arm: " + arm, flush=True)
        clock = time.perf_counter()
        result = v1.evaluate_arm(
            arm,
            morgan=morgan,
            physical=levers[arm],
            target=placebo_target if arm == ARM_PLACEBO else target,
            temperatures=temperatures,
            groups=groups,
            splits=bn.build_splits(groups, score_mask=scored, train_mask=masks[arm]),
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
            physical=lever4,
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
        "anchor_rows": n_anchor,
        "anchor_compounds": int(anchor_report.get("compounds_admitted", 0)),
        "anchor_report": dict(anchor_report),
        "rows_total": n_base + n_anchor,
        "scored_rows": int(scored.sum()),
    }
    telemetry = {
        "started_at_utc": started_at_utc,
        "finished_at_utc": _utc_now(),
        "wall_seconds": time.perf_counter() - started,
        "jobs": jobs,
        "lever4": dict(lever4_report),
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
    v1.write_csv_rows(ARTIFACTS_DIR / (ARTIFACT_STEM + "_repeats.csv"), v1.REPEAT_COLUMNS_OUT, repeat_rows)
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(format_report(summary)) + "\n", encoding="utf-8", newline="\n")
    verdict = summary["verdict"]
    print()
    for name in FITTED_ARMS:
        print(f"{name:<34s} R2 {bn.arm_r2(arms[name]['summary']):+.6f}")
    print(f"anchors reproduced: {verdict['anchors_reproduced']}")
    print(f"primary met: {verdict['co_primaries_met']}")
    print(f"decision: {verdict['decision']}")
    print(f"wall seconds {telemetry['wall_seconds']:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
