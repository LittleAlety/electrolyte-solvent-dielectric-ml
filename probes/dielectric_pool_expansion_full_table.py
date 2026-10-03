"""Shot 13: widen the training pool to every row of the released merged table.

Pre-registration: probes/dielectric_pool_expansion_prereg_v2.json
(status locked_before_run, 2026-09-27T07:05:00Z).  Shot 12 -- the NBS-514
block -- is reported as it stands and is not overwritten here.

The scored rows and the folds do not move.  What changes is that every row the
frozen loader already admits from
data/processed/dielectric_observations_v11plus.csv becomes training material,
which is a coverage/volume experiment inside one released source rather than an
import of foreign chemistry.  The leakage argument is structural: folds are
dealt over the compounds of score_mask alone, and masked_splits sends a row to
the training side only when its compound's fold differs from the scored fold.

Run:
    .venv/Scripts/python.exe probes/dielectric_pool_expansion_full_table.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
import itertools

import dielectric_coordination_block as v1
import dielectric_pool_expansion_benchmark as bn
import dielectric_xtb_full_table_migration as migration
import numpy as np
from dielectric_observations_grouped_benchmark import build_matrices
from dielectric_representation_ablation import read_csv_rows
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_pool_expansion_prereg_v2.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_pool_expansion_full_table_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_pool_expansion_full_table.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_pool_expansion_full_table"
COORDINATION_FEATURES_PATH = v1.ARTIFACTS_DIR / "dielectric_coordination_block_features.csv"
CONFORMER_FEATURES_PATH = (
    v1.ARTIFACTS_DIR / "dielectric_xtb_full_table_migration_conformers.csv"
)

BASELINE_R2_REFERENCE = 0.4091179943351143
HEADLINE_REFERENCE_R2 = 0.4766400383507876
REPRODUCTION_TOLERANCE = 1e-09
PRIMARY_TARGET_R2 = 0.60
PLACEBO_TOLERANCE = 0.0200
DOSE_LEVELS = (0.25, 0.50, 0.75, 1.00)

ARM_BASELINE = "baseline_hybrid"
ARM_FULL_HYBRID = "full_table_hybrid"
ARM_FULL_L4 = "full_table_lever4"
ARM_FULL_L4L8 = "full_table_lever4_lever8"
ARM_FULL_NBS_HYBRID = "full_table_plus_nbs_hybrid"
ARM_FULL_NBS_L4 = "full_table_plus_nbs_lever4"
ARM_PLACEBO = "full_table_label_placebo"

FITTED_ARMS = (
    ARM_BASELINE,
    ARM_FULL_HYBRID,
    ARM_FULL_L4,
    ARM_FULL_L4L8,
    ARM_FULL_NBS_HYBRID,
    ARM_FULL_NBS_L4,
    ARM_PLACEBO,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_of(path: Path) -> str:
    return canonical_text_sha256(path)


def build_summary(
    *,
    generated_at: str,
    prereg: Mapping[str, object],
    pool: Mapping[str, object],
    contract: Mapping[str, object],
    arms: Mapping[str, object],
    dose_rows: Sequence[Mapping[str, object]],
    telemetry: Mapping[str, object],
) -> dict[str, object]:
    baseline_r2 = bn.arm_r2(arms[ARM_BASELINE]["summary"])  # type: ignore[index]
    readings = {
        name: bn.arm_r2(arms[name]["summary"])  # type: ignore[index]
        for name in FITTED_ARMS
    }
    reproduction_gap = abs(baseline_r2 - BASELINE_R2_REFERENCE)
    reproduced = bool(reproduction_gap <= REPRODUCTION_TOLERANCE)
    co_primary_met = bool(
        readings[ARM_FULL_HYBRID] > PRIMARY_TARGET_R2
        and readings[ARM_FULL_L4L8] > PRIMARY_TARGET_R2
    )
    placebo_delta = readings[ARM_PLACEBO] - baseline_r2
    arm_a_pass = bool(placebo_delta <= PLACEBO_TOLERANCE)
    deltas = [float(row["delta_r2_vs_baseline"]) for row in dose_rows]
    arm_b_pass = bool(all(b >= a - 1e-09 for a, b in itertools.pairwise(deltas)))
    if co_primary_met and arm_a_pass and arm_b_pass:
        decision = "co_primaries_met_with_governance"
        decision_text = (
            "both co-primary arms clear 0.60 and both governance arms hold; the gain may be "
            "written up as observation-level information"
        )
    elif co_primary_met:
        decision = "co_primaries_met_governance_failed"
        decision_text = (
            "both co-primary arms clear 0.60 but Arm A or Arm B failed; the numbers are "
            "reported only as a data-volume effect"
        )
    else:
        decision = "co_primaries_missed"
        decision_text = (
            "at least one co-primary arm misses 0.60; the achieved numbers and the "
            "shortfall are reported as they stand"
        )
    return {
        "schema_version": 1,
        "task": "dielectric_pool_expansion_full_table",
        "week": "week17",
        "shot": 13,
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
                "representations": {
                    representation: float(block["summary"][representation]["r2"]["mean"])
                    for representation in sorted(block["summary"])
                },
                "seconds": block["seconds"],
                "leak": block["leak"],
            }
            for name, block in arms.items()
        },
        "dose_response": [dict(row) for row in dose_rows],
        "verdict": {
            "baseline_r2": baseline_r2,
            "baseline_r2_reference": BASELINE_R2_REFERENCE,
            "baseline_abs_gap": reproduction_gap,
            "baseline_reproduced": reproduced,
            "headline_reference_r2": HEADLINE_REFERENCE_R2,
            "co_primary_arms": [ARM_FULL_HYBRID, ARM_FULL_L4L8],
            "co_primary_values": {
                ARM_FULL_HYBRID: readings[ARM_FULL_HYBRID],
                ARM_FULL_L4L8: readings[ARM_FULL_L4L8],
            },
            "primary_target": PRIMARY_TARGET_R2,
            "co_primaries_met": co_primary_met,
            "shortfalls": {
                ARM_FULL_HYBRID: PRIMARY_TARGET_R2 - readings[ARM_FULL_HYBRID],
                ARM_FULL_L4L8: PRIMARY_TARGET_R2 - readings[ARM_FULL_L4L8],
            },
            "placebo_r2": readings[ARM_PLACEBO],
            "placebo_delta_r2": placebo_delta,
            "arm_a_pass": arm_a_pass,
            "arm_b_pass": arm_b_pass,
            "decision": decision,
            "decision_text": decision_text,
        },
        "telemetry": dict(telemetry),
        "honest_boundaries": [
            "the scoring pool is 457 rows but only 276 distinct (compound, temperature) pairs",
            ("the training-only rows come from the released table only, so this is a coverage "
            "and volume experiment inside one source, not new chemistry"),
            ("the dose curve is drawn from a single seeded permutation of training-only "
            "compounds, so each dose is one random subset rather than an average over subsets"),
            ("the frozen promoted headline stays 0.4766400383507876 until a promotion is "
            "written down deliberately"),
        ],
    }


def format_report(summary: Mapping[str, object]) -> list[str]:
    verdict = summary["verdict"]
    pool = summary["pool"]
    contract = summary["frozen_contract"]
    arms = summary["arms"]
    lines = [
        "# Shot 13: the full released table as training material",
        "",
        f"**Generated:** {summary['generated_at_utc']}",
        "",
        (f"**Pre-registration:** {summary['prereg']['path']} "
        f"({summary['prereg']['status']}, {summary['prereg']['locked_at_utc']}, "
        f"sha256 {summary['prereg']['sha256']})"),
        "",
        f"**Decision:** `{verdict['decision']}` -- {verdict['decision_text']}",
        "",
        "## 1. The frozen side",
        "",
        "| Quantity | Value |",
        "|---|---|",
        f"| Scored rows | {contract['scored_rows']} |",
        f"| Scored compounds | {contract['compounds_scored']} |",
        f"| Folds | {contract['folds']} ({contract['executed_repeats']} repeats x 5) |",
        (f"| Baseline reproduction | {verdict['baseline_r2']:.16f} vs "
        f"{verdict['baseline_r2_reference']:.16f} (abs {verdict['baseline_abs_gap']:.2e}) |"),
        "",
        "## 2. The widened training pool",
        "",
        "| Quantity | Value |",
        "|---|---|",
        f"| Admitted rows in the merged table | {pool['base_rows']} |",
        f"| ... training-only | {pool['training_only_rows']} |",
        f"| ... training-only compounds | {pool['training_only_compounds']} |",
        f"| NBS block rows (optional arm) | {pool['nbs_rows']} |",
        f"| NBS block compounds | {pool['nbs_compounds']} |",
        f"| Training rows per fold (mean) | {pool['train_rows_mean']} |",
        "",
        "## 3. Arms",
        "",
        "| Arm | Morgan+Physical R2 | Delta vs baseline |",
        "|---|---|---|",
    ]
    for name in FITTED_ARMS:
        block = arms[name]
        lines.append(f"| `{name}` | {block['r2']:.16f} | {block['delta_r2_vs_baseline']:+.6f} |")
    lines += [
        "",
        "## 4. Governance",
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
        (f"- Arm A (compound-level label placebo on the training-only block): delta "
        f"{verdict['placebo_delta_r2']:+.6f}, tolerance +{PLACEBO_TOLERANCE:.2f} -> "
        f"{'PASS' if verdict['arm_a_pass'] else 'FAIL'}"),
        f"- Arm B (monotone dose response): {'PASS' if verdict['arm_b_pass'] else 'FAIL'}",
        "",
        "## 5. Co-primary criterion",
        "",
        (f"- `{ARM_FULL_HYBRID}`: **{verdict['co_primary_values'][ARM_FULL_HYBRID]:.16f}** "
        f"(shortfall {verdict['shortfalls'][ARM_FULL_HYBRID]:+.6f})"),
        (f"- `{ARM_FULL_L4L8}`: **{verdict['co_primary_values'][ARM_FULL_L4L8]:.16f}** "
        f"(shortfall {verdict['shortfalls'][ARM_FULL_L4L8]:+.6f})"),
        f"- Bar: {verdict['primary_target']:.2f}; met: **{verdict['co_primaries_met']}**",
        f"- Frozen promoted headline for reference: {verdict['headline_reference_r2']:.16f}",
        "",
        "## 6. Honest boundaries",
        "",
    ]
    lines.extend("- " + str(item) for item in summary["honest_boundaries"])
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

    if not PREREG_PATH.is_file():
        print("MISSING " + str(PREREG_PATH))
        return 1
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if str(prereg.get("status")) != "locked_before_run":
        print("the pre-registration is not locked_before_run")
        return 1

    scoreboard = v1.build_scoreboard()
    contract = scoreboard["contract"]
    if not contract["matches_preregistration"]:
        print("the rebuilt scoreboard does not match the pre-registration")
        return 1
    base_rows = list(scoreboard["rows"])  # type: ignore[arg-type]
    base_scored = np.asarray(scoreboard["scored"], dtype=bool)
    n_base = len(base_rows)
    print(f"scoreboard: {contract['scored_rows']} rows / {contract['compounds_scored']} compounds")

    blocked_keys = {(str(r["inchikey"]), round(float(str(r["T_K"])), 2)) for r in base_rows}
    scoring_compounds = {
        str(k) for k, f in zip(scoreboard["groups"], base_scored, strict=True) if f
    }
    if bn.EXPANSION_OBSERVATIONS_PATH.is_file():
        expansion_rows, expansion_report = bn.load_expansion(
            observations_path=bn.EXPANSION_OBSERVATIONS_PATH,
            features_path=bn.EXPANSION_FEATURES_PATH,
            blocked_keys=blocked_keys,
            scoring_compounds=scoring_compounds,
        )
    else:
        expansion_rows, expansion_report = [], {"rows_admitted": 0, "compounds_admitted": 0}
    n_expansion = len(expansion_rows)
    print(
        f"nbs block: {expansion_report.get('rows_admitted')} rows / "
        f"{expansion_report.get('compounds_admitted')} compounds"
    )

    if expansion_rows:
        exp_morgan, exp_physical, exp_target, exp_temps, exp_groups = build_matrices(expansion_rows)
    else:
        exp_morgan = np.zeros((0, scoreboard["morgan"].shape[1]))
        exp_physical = np.zeros((0, scoreboard["physical"].shape[1]))
        exp_target = np.zeros(0)
        exp_temps = np.zeros(0)
        exp_groups = []
    morgan = np.vstack([scoreboard["morgan"], exp_morgan])
    physical = np.vstack([scoreboard["physical"], exp_physical])
    target = np.concatenate([scoreboard["target"], exp_target])
    temperatures = np.concatenate([scoreboard["temperatures"], exp_temps])
    groups = list(scoreboard["groups"]) + list(exp_groups)
    scored = np.concatenate([base_scored, np.zeros(n_expansion, dtype=bool)])
    extended_rows = base_rows + expansion_rows

    frozen_splits = list(scoreboard["splits"])  # type: ignore[arg-type]
    full_base = np.concatenate([np.ones(n_base, dtype=bool), np.zeros(n_expansion, dtype=bool)])
    everything = np.ones(n_base + n_expansion, dtype=bool)
    training_only = ~scored
    masks = {
        ARM_BASELINE: scored,
        ARM_FULL_HYBRID: full_base,
        ARM_FULL_L4: full_base,
        ARM_FULL_L4L8: full_base,
        ARM_FULL_NBS_HYBRID: everything,
        ARM_FULL_NBS_L4: everything,
        ARM_PLACEBO: full_base,
    }
    for name, mask in masks.items():
        splits = bn.build_splits(groups, score_mask=scored, train_mask=mask)
        if bn.fold_signature(splits) != bn.fold_signature(frozen_splits):
            print(f"{name}: the fold assignment moved; refusing to continue")
            return 1

    dipole_map = bn.dipole_map_from_conformer_rows(read_csv_rows(CONFORMER_FEATURES_PATH))
    physical_lever4, lever4_report = migration.build_physical_matrix_v04(
        extended_rows, dipole_map=dipole_map
    )
    coordination_rows = read_csv_rows(COORDINATION_FEATURES_PATH)
    coordination, coordination_report = v1.coordination_matrix(extended_rows, coordination_rows)
    physical_lever4_lever8 = np.hstack([physical_lever4, coordination])

    levers = {
        ARM_BASELINE: physical,
        ARM_FULL_HYBRID: physical,
        ARM_FULL_L4: physical_lever4,
        ARM_FULL_L4L8: physical_lever4_lever8,
        ARM_FULL_NBS_HYBRID: physical,
        ARM_FULL_NBS_L4: physical_lever4,
        ARM_PLACEBO: physical,
    }

    arms: dict[str, dict[str, object]] = {}
    placebo_target = bn.label_placebo_target(target, groups, training_only)
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
        mask = bn.dose_mask(groups, training_only, level=level)
        result = v1.evaluate_arm(
            f"dose_{round(level * 100):03d}",
            morgan=morgan,
            physical=physical,
            target=target,
            temperatures=temperatures,
            groups=groups,
            splits=bn.build_splits(groups, score_mask=scored, train_mask=scored | mask),
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

    per_fold = bn.build_splits(groups, score_mask=scored, train_mask=masks[ARM_FULL_HYBRID])
    pool_report = {
        "base_rows": n_base,
        "training_only_rows": int(training_only.sum()),
        "training_only_compounds": len({str(groups[i]) for i in np.flatnonzero(training_only)}),
        "nbs_rows": n_expansion,
        "nbs_compounds": int(expansion_report.get("compounds_admitted", 0)),
        "train_rows_mean": float(np.mean([item[2].size for item in per_fold])),
        "scored_rows": int(scored.sum()),
        "expansion_report": dict(expansion_report),
    }

    telemetry = {
        "started_at_utc": started_at_utc,
        "finished_at_utc": _utc_now(),
        "wall_seconds": time.perf_counter() - started,
        "jobs": jobs,
        "lever4": dict(lever4_report),
        "coordination_rows_with_the_block": coordination_report["rows_with_the_block"],
        "coordination_rows_total": len(extended_rows),
        "nbs_block_available": bool(expansion_rows),
    }
    summary = build_summary(
        generated_at=_utc_now(),
        prereg=prereg,
        pool=pool_report,
        contract=contract,
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
    print(f"co-primaries met: {verdict['co_primaries_met']}")
    print(f"decision: {verdict['decision']}")
    print(f"wall seconds {telemetry['wall_seconds']:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())