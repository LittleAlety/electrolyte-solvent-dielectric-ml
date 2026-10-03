"""W18-1: the multi-seed endpoint for the frozen main-scoreboard arms.

W17 scored every arm at the single frozen fold seed 42.  Shot 16 showed that the
0.6081 reading on one arm carried a favourable seed-42 draw (its five-seed mean is
0.586114), so a single-seed endpoint cannot separate a real effect from a lucky
fold assignment.  This lane changes no model and adds no information: it re-scores
the four frozen merge arms over a pre-locked five-seed set and defines the endpoint
as the cross-seed mean of the per-seed 10-repeat R2 means.

Nothing on the frozen side moves.  The scoreboard (457 scored rows / 97 compounds /
276 pairs), the splitter (GroupKFold by InChIKey, 10 repeats x 5 folds), the model
(the frozen v1.0 XGB hyper-parameters) and the read (the frozen 0.5 * (Morgan +
Physical) blend) are the ones that produced 0.4091179943351143.  Seed 42 has to
reproduce all four registered readings bit for bit, otherwise the probe refuses to
report anything else.

This lane promotes nothing: it can only remove seed variance from an endpoint
definition.  The frozen headline stays 0.4766400383507876 and the frozen baseline
stays 0.4091179943351143.

Run:
    .venv/Scripts/python.exe probes/dielectric_multiseed_endpoint.py --jobs 3
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
import dielectric_coordination_block as v1
import dielectric_xtb_full_table_migration as migration
import numpy as np
from dielectric_coordination_block_v3 import dipole_map_from_conformer_rows
from dielectric_observations_grouped_benchmark import METRIC_NAMES
from dielectric_representation_ablation import read_csv_rows
from dielectric_representation_seed_robustness import splits_for
from export_results_common import write_json_stable

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_multiseed_endpoint_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_multiseed_endpoint_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_multiseed_endpoint.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
REPEATS_PATH = ARTIFACTS_DIR / "dielectric_multiseed_endpoint_repeats.csv"

COORDINATION_FEATURES = ARTIFACTS_DIR / "dielectric_coordination_block_features.csv"
CONFORMER_FEATURES = ARTIFACTS_DIR / "dielectric_xtb_full_table_migration_conformers.csv"

SEEDS = (42, 1234, 2026, 31337, 7)
ANCHOR_SEED = 42
ANCHOR_TOLERANCE = 1e-09
HYBRID = "Morgan+Physical"
ARMS = ("baseline", "plus_lever4", "plus_lever8", "plus_both")
ARM_DESCRIPTIONS = {
    "baseline": "Morgan+Physical on the frozen physical block (13 columns)",
    "plus_lever4": "Morgan+Physical with the lever-4 conformer-average dipole migration",
    "plus_lever8": "Morgan+Physical plus the five-column Li+ coordination block",
    "plus_both": "Morgan+Physical plus lever 4 plus lever 8 (the promoted headline arm)",
}
SEED_42_ANCHORS = {
    "baseline": 0.4091179943351143,
    "plus_lever4": 0.4649564468823552,
    "plus_lever8": 0.4531768105508106,
    "plus_both": 0.4766400383507876,
}
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
REPEAT_COLUMNS_OUT = ("seed", "arm", "representation", "repeat", *METRIC_NAMES)


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--seeds", type=str, default=",".join(str(s) for s in SEEDS))
    return parser.parse_args(argv)


def build_design() -> dict[str, object]:
    """The frozen scoreboard and the four arm feature blocks."""

    scoreboard = v1.build_scoreboard()
    contract = scoreboard["contract"]
    if not contract["matches_preregistration"]:
        raise SystemExit("the rebuilt scoreboard does not match the pre-registration")
    coordination_rows = read_csv_rows(COORDINATION_FEATURES)
    matrix, block_report = v1.coordination_matrix(scoreboard["rows"], coordination_rows)
    conformer_rows = read_csv_rows(CONFORMER_FEATURES)
    dipole_map = dipole_map_from_conformer_rows(conformer_rows)
    physical_v04, lever4_report = migration.build_physical_matrix_v04(
        scoreboard["rows"], dipole_map=dipole_map
    )
    physical = np.asarray(scoreboard["physical"])
    with_lever8 = np.hstack([physical, matrix])
    with_both = np.hstack([np.asarray(physical_v04), matrix])
    return {
        "scoreboard": scoreboard,
        "features": {
            "baseline": physical,
            "plus_lever4": np.asarray(physical_v04),
            "plus_lever8": with_lever8,
            "plus_both": with_both,
        },
        "block_report": block_report,
        "lever4_report": lever4_report,
    }


def write_csv_rows(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    lines = [",".join(columns)]
    for row in rows:
        cells = []
        for column in columns:
            value = row.get(column, "")
            text = "" if value is None else str(value)
            if "," in text or chr(34) in text:
                text = chr(34) + text.replace(chr(34), chr(34) * 2) + chr(34)
            cells.append(text)
        lines.append(",".join(cells))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_json(path: Path, payload: object) -> None:
    write_json_stable(path, payload)


def format_report(summary: Mapping[str, object]) -> str:
    lines: list[str] = []
    lines.append("# W18-1 多种子均值端点升级（冻结主记分牌四臂）")
    lines.append("")
    lines.append("- 生成时间（UTC）：" + str(summary["generated_at_utc"]))
    lines.append("- 冻结侧：457 计分行 / 97 化合物 / 276 个 (化合物, T) 对；GroupKFold by InChIKey，5 折 x 10 重复；读 `Morgan+Physical`。")
    lines.append("- 种子集（跑前锁定）：" + ", ".join(str(s) for s in summary["contract"]["seeds"]))
    lines.append("- 本 lane **不换模型、不加信息**：只把端点从「seed 42 单次抽样」改成「跨种子均值」。")
    lines.append("")
    lines.append("## 端点表（每一行两数并列，永不互减）")
    lines.append("")
    lines.append("| 臂 | seed 42（单抽） | 跨种子均值 | sd | min | max | >0.60 的种子数 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in summary["endpoints"]:
        lines.append(
            "| `" + str(row["arm"]) + "` | " + format(float(row["seed_42"]), ".6f")
            + " | **" + format(float(row["cross_seed_mean"]), ".6f") + "** | "
            + format(float(row["cross_seed_sd"]), ".4f") + " | "
            + format(float(row["cross_seed_min"]), ".6f") + " | "
            + format(float(row["cross_seed_max"]), ".6f") + " | "
            + str(row["above_060_seeds"]) + "/" + str(len(summary["contract"]["seeds"])) + " |"
        )
    lines.append("")
    lines.append("## 锚点（seed 42 必须逐位复现）")
    lines.append("")
    for row in summary["anchors"]["rows"]:
        lines.append(
            "- `" + str(row["arm"]) + "`：期望 " + format(float(row["expected"]), ".16f")
            + "，实测 " + format(float(row["measured"]), ".16f")
            + "，|Δ| = " + format(float(row["abs_gap"]), ".2e")
            + (" ✅" if row["ok"] else " ❌")
        )
    lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append("- verdict = `" + str(summary["verdict"]) + "`")
    lines.append("- 跨种子均值最高臂 = `" + str(summary["best_arm"]["arm"]) + "` = "
                 + format(float(summary["best_arm"]["cross_seed_mean"]), ".6f")
                 + "（对照冻结头条 " + format(FROZEN_HEADLINE, ".16f") + "）")
    lines.append("- 目标 0.60 在跨种子端点下：**" + ("达到" if summary["target_met_cross_seed"] else "未达到") + "**")
    lines.append("- 本 lane `promoted = false`：它只改端点口径，**不提升任何读数**；冻结头条 0.4766400383507876 与冻结基线 0.4091179943351143 均未动。")
    lines.append("")
    lines.append("## 边界（不许省略）")
    lines.append("")
    lines.append("1. **跨种子均值与 seed 42 单抽是两种口径，永不互减**；本表两列并列就是为了让这一点无法被省略。")
    lines.append("2. 换种子**不改池**：只改哪些化合物被留出；跨种子差异里既有表示能力也有折难度。")
    lines.append("3. 本 lane **不是盲法确认**：seed 42 的读数在 W17 已公开。")
    lines.append("4. 四臂共用同一分折与同一打乱向量，**不是独立样本**。")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    started_at_utc = _utc_now()
    jobs = max(1, int(args.jobs))
    seeds = tuple(int(token) for token in str(args.seeds).split(",") if token.strip())
    if not seeds:
        print("no seeds requested")
        return 1
    if not PREREG_PATH.is_file():
        print("MISSING " + str(PREREG_PATH))
        return 1
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if str(prereg.get("status")) != "locked_before_run":
        print("the pre-registration is not locked_before_run")
        return 1

    design = build_design()
    scoreboard = design["scoreboard"]
    groups = [str(item) for item in scoreboard["groups"]]
    scored = np.asarray(scoreboard["scored"], dtype=bool)
    target = np.asarray(scoreboard["target"])
    temperatures = np.asarray(scoreboard["temperatures"])
    morgan = np.asarray(scoreboard["morgan"])
    features = design["features"]
    # The frozen v3 anchors (0.4091179943351143 and the three merge arms) train on
    # the 457 scored rows, not on the 2029-row full table: the full-table mask is the
    # shot-13 configuration, whose hybrid reads 0.530028742596643.  Using it here made
    # seed 42 print 0.530029 for `baseline` and would have failed the anchor check
    # after the whole sweep, so the mask is the scored one.
    train_mask = scored.copy()
    scored_compounds = len({group for group, flag in zip(groups, scored, strict=True) if flag})
    print(
        "pool: " + str(int(scored.sum())) + " scored rows / " + str(scored_compounds)
        + " scored compounds / seeds " + ", ".join(str(s) for s in seeds),
        flush=True,
    )

    per_seed: dict[int, dict[str, float]] = {}
    spreadsheet: list[dict[str, object]] = []
    leakage: dict[str, dict[str, int]] = {}
    for seed in seeds:
        splits = splits_for(seed, groups, scored, train_mask)
        for arm in ARMS:
            clock = time.perf_counter()
            result = v1.evaluate_arm(
                arm,
                morgan=morgan,
                physical=features[arm],
                target=target,
                temperatures=temperatures,
                groups=groups,
                splits=splits,
                jobs=jobs,
            )
            mean = float(result["summary"][HYBRID]["r2"]["mean"])
            per_seed.setdefault(int(seed), {})[arm] = mean
            for row in result["repeat_rows"]:
                spreadsheet.append({"seed": int(seed), **row})
            leakage[str(seed) + "/" + arm] = dict(result["leak"])
            print(
                "  seed " + str(seed) + " | " + arm + " | " + format(mean, ".6f")
                + "  (" + format(time.perf_counter() - clock, ".1f") + "s)",
                flush=True,
            )

    anchor_rows: list[dict[str, object]] = []
    anchors_reproduced = True
    if ANCHOR_SEED in per_seed:
        for arm in ARMS:
            measured = float(per_seed[ANCHOR_SEED][arm])
            expected = float(SEED_42_ANCHORS[arm])
            gap = abs(measured - expected)
            ok = gap <= ANCHOR_TOLERANCE
            anchors_reproduced = anchors_reproduced and ok
            anchor_rows.append(
                {"arm": arm, "expected": expected, "measured": measured,
                 "abs_gap": gap, "ok": bool(ok)}
            )
        if not anchors_reproduced:
            print("the seed-42 anchors did not reproduce; refusing to report anything else")
            return 1

    leak_clean = all(
        block["folds_with_a_straddling_compound"] == 0
        and block["max_straddling_compounds_in_a_fold"] == 0
        for block in leakage.values()
    )
    if not leak_clean:
        print("a scored compound straddled a fold; refusing to continue")
        return 1

    endpoints: list[dict[str, object]] = []
    for arm in ARMS:
        values = [float(per_seed[seed][arm]) for seed in seeds]
        endpoints.append(
            {
                "arm": arm,
                "description": ARM_DESCRIPTIONS[arm],
                "seed_42": float(per_seed[ANCHOR_SEED][arm]) if ANCHOR_SEED in per_seed else None,
                "seed_values": {str(seed): float(per_seed[seed][arm]) for seed in seeds},
                "cross_seed_mean": float(np.mean(values)),
                "cross_seed_sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                "cross_seed_min": float(np.min(values)),
                "cross_seed_max": float(np.max(values)),
                "above_060_seeds": int(sum(1 for value in values if value > 0.60)),
                "above_070_seeds": int(sum(1 for value in values if value > 0.70)),
            }
        )
    baseline_mean = float(next(row["cross_seed_mean"] for row in endpoints if row["arm"] == "baseline"))
    for row in endpoints:
        row["cross_seed_mean_minus_baseline"] = float(row["cross_seed_mean"]) - baseline_mean
    best = max(endpoints, key=lambda row: (float(row["cross_seed_mean"]), str(row["arm"])))
    target_met = bool(float(best["cross_seed_mean"]) > 0.60)

    summary: dict[str, object] = {
        "schema": "dielectric_multiseed_endpoint/summary@1",
        "generated_at_utc": _utc_now(),
        "started_at_utc": started_at_utc,
        "finished_at_utc": _utc_now(),
        "wall_seconds": time.perf_counter() - started,
        "jobs": jobs,
        "prereg": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": canonical_text_sha256(PREREG_PATH),
            "status": str(prereg.get("status")),
        },
        "contract": {
            "scoreboard": "457 scored rows / 97 compounds / 276 (compound, T) pairs",
            "n_splits": 5,
            "n_repeats": 10,
            "seeds": list(seeds),
            "anchor_seed": ANCHOR_SEED,
            "representation_read": HYBRID,
            "arms": list(ARMS),
        },
        "pool": {
            "scored_rows": int(scored.sum()),
            "scored_compounds": scored_compounds,
            "training_rows": int(train_mask.sum()),
            "coordination_block": design["block_report"],
            "lever4_block": design["lever4_report"],
        },
        "anchors": {"reproduced": bool(anchors_reproduced), "rows": anchor_rows,
                    "tolerance": ANCHOR_TOLERANCE},
        "leakage": {"clean": bool(leak_clean), "by_seed_arm": leakage},
        "endpoints": endpoints,
        "best_arm": {
            "arm": str(best["arm"]),
            "cross_seed_mean": float(best["cross_seed_mean"]),
            "seed_42": best["seed_42"],
        },
        "target_r2": 0.60,
        "target_met_cross_seed": target_met,
        "frozen_headline_unchanged_r2": FROZEN_HEADLINE,
        "frozen_baseline_unchanged_r2": FROZEN_BASELINE,
        "verdict": "endpoint_upgraded" if anchors_reproduced else "refused",
        "promotion": {
            "promoted": False,
            "frozen_headline": FROZEN_HEADLINE,
            "frozen_baseline": FROZEN_BASELINE,
            "reason": (
                "this lane only changes the endpoint definition from a single-seed draw "
                "to a pre-locked cross-seed mean; it fits no new model family and moves "
                "no frozen number"
            ),
        },
        "outputs": {
            "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
            "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
            "repeats": portable_relative_path(REPEATS_PATH, root=REPOSITORY_ROOT),
        },
    }

    write_json(SUMMARY_PATH, summary)
    write_csv_rows(REPEATS_PATH, REPEAT_COLUMNS_OUT, spreadsheet)
    REPORT_PATH.write_text(format_report(summary), encoding="utf-8", newline="\n")
    print("verdict=" + str(summary["verdict"]) + " best=" + str(best["arm"]) + " mean="
          + format(float(best["cross_seed_mean"]), ".6f"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
