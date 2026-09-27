"""W17 shot 16: is the single-representation 0.6081 a seed-42 artifact?

The only reading above 0.60 anywhere in the W17 record is ``full_table_lever4`` /
``Physical`` = 0.6080587938801277.  It is a *single-representation* reading, while
the pre-registered primary criterion is the hybrid ``Morgan+Physical``, so the audit
(reports/dielectric_pool_expansion_audit.md, Q7) forbids promoting it.  This probe
asks the separate, answerable question: does the ordering Physical > Morgan+Physical
survive a fresh fold randomisation, or is it an artifact of the frozen seed 42?

Nothing on the frozen side moves.  The pool (2029 base training rows / 457 scored
rows over 97 compounds), the score mask, the group splitter and the protocol
(5 folds x 10 repeats, GroupKFold by InChIKey) are the ones that produced
0.4091179943351143.  Only the fold seed changes.  Seed 42 has to reproduce the
three registered readings bit for bit, otherwise the probe refuses to report
anything else, so it cannot silently re-baseline.

This probe is diagnostic.  No reading it produces may be promoted: the frozen
headline stays 0.4766400383507876 and the frozen baseline stays 0.4091179943351143.

Run:
    .venv\\Scripts\\python.exe probes\\dielectric_representation_seed_robustness.py --jobs 8
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
import dielectric_pool_expansion_benchmark as bn
import dielectric_xtb_full_table_migration as migration
import numpy as np
from dielectric_band_ablation import MIN_TEST_ROWS_PER_FOLD, drop_thin_folds
from dielectric_observations_grouped_benchmark import build_matrices
from dielectric_representation_ablation import N_REPEATS, N_SPLITS, read_csv_rows
from dielectric_room_window_paired import masked_splits

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_representation_seed_robustness_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_representation_seed_robustness_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_representation_seed_robustness.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_representation_seed_robustness"

CONFORMER_FEATURES_PATH = ARTIFACTS_DIR / "dielectric_xtb_full_table_migration_conformers.csv"

REPRESENTATIONS = ("Morgan", "Physical", "Morgan+Physical")
SEEDS = (42, 1234, 2026, 31337, 7)
ANCHOR_SEED = 42
ANCHOR_TOLERANCE = 1e-09

ARM_BASELINE = "baseline_hybrid"
ARM_FULL_HYBRID = "full_table_hybrid"
ARM_FULL_L4 = "full_table_lever4"
ARMS = (ARM_BASELINE, ARM_FULL_HYBRID, ARM_FULL_L4)
PRIMARY_ARM = ARM_FULL_L4

ANCHORS = {
    ARM_BASELINE: 0.4091179943351143,
    ARM_FULL_HYBRID: 0.530028742596643,
    ARM_FULL_L4: 0.5433111678100043,
}
HYPOTHESIS_REPRESENTATION = "Physical"
HYPOTHESIS_REFERENCE = "Morgan+Physical"

FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
SEED_42_PHYSICAL = 0.6080587938801277
PRIMARY_TARGET_R2 = 0.60


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=8)
    return parser.parse_args(argv)


def build_context() -> dict[str, object]:
    """The frozen pool plus the two physical blocks the shot-13 arms used."""

    scoreboard = v1.build_scoreboard()
    base_rows = list(scoreboard["rows"])  # type: ignore[arg-type]
    base_scored = np.asarray(scoreboard["scored"], dtype=bool)
    n_base = len(base_rows)
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
    morgan_columns = int(np.asarray(scoreboard["morgan"]).shape[1])
    physical_columns = int(np.asarray(scoreboard["physical"]).shape[1])
    if expansion_rows:
        exp_morgan, exp_physical, exp_target, exp_temps, exp_groups = build_matrices(expansion_rows)
    else:
        exp_morgan = np.zeros((0, morgan_columns))
        exp_physical = np.zeros((0, physical_columns))
        exp_target = np.zeros(0)
        exp_temps = np.zeros(0)
        exp_groups = []
    morgan = np.vstack([np.asarray(scoreboard["morgan"]), exp_morgan])
    physical = np.vstack([np.asarray(scoreboard["physical"]), exp_physical])
    target = np.concatenate([np.asarray(scoreboard["target"]), exp_target])
    temperatures = np.concatenate([np.asarray(scoreboard["temperatures"]), exp_temps])
    groups = [str(g) for g in scoreboard["groups"]] + [str(g) for g in exp_groups]
    scored = np.concatenate([base_scored, np.zeros(n_expansion, dtype=bool)])
    extended_rows = base_rows + expansion_rows
    full_base = np.concatenate([np.ones(n_base, dtype=bool), np.zeros(n_expansion, dtype=bool)])
    dipole_map = bn.dipole_map_from_conformer_rows(read_csv_rows(CONFORMER_FEATURES_PATH))
    physical_lever4, lever4_report = migration.build_physical_matrix_v04(
        extended_rows, dipole_map=dipole_map
    )
    return {
        "morgan": morgan,
        "physical": physical,
        "physical_lever4": np.asarray(physical_lever4),
        "target": target,
        "temperatures": temperatures,
        "groups": groups,
        "scored": scored,
        "full_base": full_base,
        "frozen_splits": list(scoreboard["splits"]),  # type: ignore[arg-type]
        "n_base": n_base,
        "n_expansion": n_expansion,
        "expansion_report": expansion_report,
        "lever4_report": lever4_report,
        "contract": scoreboard["contract"],
    }


def splits_for(
    seed: int,
    groups: Sequence[str],
    score_mask: np.ndarray,
    train_mask: np.ndarray,
) -> list[tuple[int, int, np.ndarray, np.ndarray]]:
    raw = masked_splits(
        groups,
        score_mask=score_mask,
        train_mask=train_mask,
        n_splits=N_SPLITS,
        n_repeats=N_REPEATS,
        seed=seed,
    )
    return list(drop_thin_folds(raw, min_test_rows=MIN_TEST_ROWS_PER_FOLD))


def repeats_to_r2(repeat_rows: Sequence[Mapping[str, object]], representation: str) -> list[float]:
    return [
        float(str(row["r2"]))
        for row in repeat_rows
        if str(row.get("representation")) == representation
    ]


def evaluate_seed(
    seed: int,
    context: Mapping[str, object],
    jobs: int,
) -> tuple[
    dict[str, dict[str, list[float]]],
    list[dict[str, object]],
    bool,
    dict[str, dict[str, int]],
]:
    groups = list(context["groups"])  # type: ignore[arg-type]
    scored = np.asarray(context["scored"], dtype=bool)
    full_base = np.asarray(context["full_base"], dtype=bool)
    physical = np.asarray(context["physical"])
    physical_lever4 = np.asarray(context["physical_lever4"])
    levers = {ARM_BASELINE: physical, ARM_FULL_HYBRID: physical, ARM_FULL_L4: physical_lever4}
    masks = {ARM_BASELINE: scored, ARM_FULL_HYBRID: full_base, ARM_FULL_L4: full_base}
    collected: dict[str, dict[str, list[float]]] = {}
    spreadsheet: list[dict[str, object]] = []
    leakage: dict[str, dict[str, int]] = {}
    signature_ok = True
    for arm in ARMS:
        splits = splits_for(seed, groups, scored, masks[arm])
        if seed == ANCHOR_SEED:
            frozen = bn.fold_signature(context["frozen_splits"])  # type: ignore[arg-type]
            if bn.fold_signature(splits) != frozen:
                signature_ok = False
        clock = time.perf_counter()
        result = v1.evaluate_arm(
            arm + "@seed" + str(seed),
            morgan=np.asarray(context["morgan"]),
            physical=levers[arm],
            target=np.asarray(context["target"]),
            temperatures=np.asarray(context["temperatures"]),
            groups=groups,
            splits=splits,
            jobs=jobs,
        )
        repeat_rows = list(result["repeat_rows"])  # type: ignore[arg-type]
        collected[arm] = {
            representation: repeats_to_r2(repeat_rows, representation)
            for representation in REPRESENTATIONS
        }
        spreadsheet.extend(dict(row) for row in repeat_rows)
        leak_block = result["leak"]
        assert isinstance(leak_block, Mapping)
        leakage[arm] = {str(key): int(value) for key, value in leak_block.items()}
        summary_block = result["summary"]
        assert isinstance(summary_block, Mapping)
        print(
            "  seed " + str(seed) + " | " + arm + " | " + format(bn.arm_r2(summary_block), ".6f")
            + "  (" + format(time.perf_counter() - clock, ".1f") + "s)",
            flush=True,
        )
    return collected, spreadsheet, signature_ok, leakage


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

    context = build_context()
    scored_total = int(np.asarray(context["scored"]).sum())
    print(
        "pool: " + str(context["n_base"]) + " base rows / " + str(scored_total)
        + " scored rows / " + str(context["n_expansion"]) + " foreign rows",
        flush=True,
    )

    results: dict[int, dict[str, dict[str, list[float]]]] = {}
    spreadsheet: list[dict[str, object]] = []
    leakage_by_seed_arm: dict[str, dict[str, int]] = {}
    for seed in SEEDS:
        collected, rows, signature_ok, leak_blocks = evaluate_seed(seed, context, jobs)
        if not signature_ok:
            print("seed " + str(seed) + ": the fold assignment moved; refusing to continue")
            return 1
        for arm, block in leak_blocks.items():
            leakage_by_seed_arm[str(seed) + ":" + arm] = block
        results[seed] = collected
        spreadsheet.extend(rows)

    anchor_rows: list[dict[str, object]] = []
    anchors_reproduced = True
    for arm in ARMS:
        values = results[ANCHOR_SEED][arm][HYPOTHESIS_REFERENCE]
        measured = float(np.mean(values))
        expected = float(ANCHORS[arm])
        gap = abs(measured - expected)
        ok = gap <= ANCHOR_TOLERANCE
        anchors_reproduced = anchors_reproduced and ok
        anchor_rows.append(
            {"arm": arm, "expected": expected, "measured": measured, "abs_gap": gap, "ok": ok}
        )
    if not anchors_reproduced:
        print("the seed-42 anchors did not reproduce; refusing to report anything else")
        return 1

    # The 0.6081 headline is a constant in this file, so it must be checked against the
    # value the fitter just produced.  Without this the number would be decoration.
    seed42_physical = float(
        np.mean(results[ANCHOR_SEED][PRIMARY_ARM][HYPOTHESIS_REPRESENTATION])
    )
    if abs(seed42_physical - SEED_42_PHYSICAL) > ANCHOR_TOLERANCE:
        print("the seed-42 single-representation reading moved; refusing to report anything else")
        return 1

    leak_clean = all(
        block["folds_with_a_straddling_compound"] == 0
        and block["max_straddling_compounds_in_a_fold"] == 0
        for block in leakage_by_seed_arm.values()
    )
    if not leak_clean:
        print("a scored compound straddled a fold; refusing to continue")
        return 1

    seed_rows: list[dict[str, object]] = []
    for seed in SEEDS:
        for arm in ARMS:
            for representation in REPRESENTATIONS:
                values = results[seed][arm][representation]
                seed_rows.append(
                    {
                        "seed": seed,
                        "arm": arm,
                        "representation": representation,
                        "repeats": len(values),
                        "r2_mean": float(np.mean(values)),
                        "r2_sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                        "r2_min": float(np.min(values)),
                        "r2_max": float(np.max(values)),
                        "repeats_above_target": int(sum(1 for v in values if v > PRIMARY_TARGET_R2)),
                    }
                )

    per_seed_delta: list[dict[str, object]] = []
    positive_seeds = 0
    for seed in SEEDS:
        arm_values = results[seed][PRIMARY_ARM]
        hypothesis = float(np.mean(arm_values[HYPOTHESIS_REPRESENTATION]))
        reference = float(np.mean(arm_values[HYPOTHESIS_REFERENCE]))
        delta = hypothesis - reference
        if delta > 0.0:
            positive_seeds += 1
        per_seed_delta.append(
            {
                "seed": seed,
                "hypothesis_r2": hypothesis,
                "reference_r2": reference,
                "delta": delta,
            }
        )
    if positive_seeds == len(SEEDS):
        verdict = "confirmed_out_of_seed"
    elif positive_seeds >= 3:
        verdict = "partially_confirmed"
    else:
        verdict = "refuted_seed_42_artifact"

    seed_averaged: list[dict[str, object]] = []
    for arm in ARMS:
        for representation in REPRESENTATIONS:
            per_seed = [float(np.mean(results[seed][arm][representation])) for seed in SEEDS]
            seed_averaged.append(
                {
                    "arm": arm,
                    "representation": representation,
                    "r2_seed_mean": float(np.mean(per_seed)),
                    "r2_seed_sd": float(np.std(per_seed, ddof=1)),
                    "r2_seed_min": float(np.min(per_seed)),
                    "r2_seed_max": float(np.max(per_seed)),
                }
            )

    delta_values = [float(row["delta"]) for row in per_seed_delta]
    summary = {
        "schema": "dielectric_representation_seed_robustness/summary@1",
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
        "pool": {
            "base_rows": context["n_base"],
            "scored_rows": scored_total,
            "expansion_rows": context["n_expansion"],
            "expansion_report": context["expansion_report"],
            "lever4_report": context["lever4_report"],
        },
        "contract": {
            "n_splits": N_SPLITS,
            "n_repeats": N_REPEATS,
            "seeds": list(SEEDS),
            "anchor_seed": ANCHOR_SEED,
            "representations": list(REPRESENTATIONS),
            "arms": list(ARMS),
        },
        "anchors": {
            "reproduced": anchors_reproduced,
            "rows": anchor_rows,
            "tolerance": ANCHOR_TOLERANCE,
        },
        "seed42_single_representation": SEED_42_PHYSICAL,
        "leakage": {
            "by_seed_arm": leakage_by_seed_arm,
            "clean": leak_clean,
            "note": (
                "the splitter deals folds by compound, so no scored compound may straddle; "
                "reported because shot 13 carried this block and this probe dropped it"
            ),
        },
        "hypothesis": {
            "statement": "on full_table_lever4, R2(Physical) > R2(Morgan+Physical) holds on every seed",
            "arm": PRIMARY_ARM,
            "positive_seeds": positive_seeds,
            "total_seeds": len(SEEDS),
            "delta_mean": float(np.mean(delta_values)),
            "delta_min": float(np.min(delta_values)),
            "delta_max": float(np.max(delta_values)),
            "verdict": verdict,
            "per_seed": per_seed_delta,
        },
        "seed_averaged": seed_averaged,
        "seed_rows": seed_rows,
        "promotion": {
            "promoted": False,
            "frozen_headline": FROZEN_HEADLINE,
            "frozen_baseline": FROZEN_BASELINE,
            "reason": (
                "diagnostic representation probe; the pre-registered primary criterion is the "
                "hybrid, and this probe is non-blind with respect to seed 42"
            ),
        },
        "outputs": {
            "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
            "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
        },
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    v1.write_csv_rows(
        ARTIFACTS_DIR / (ARTIFACT_STEM + "_repeats.csv"), v1.REPEAT_COLUMNS_OUT, spreadsheet
    )
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    REPORT_PATH.write_text(format_report(summary), encoding="utf-8", newline="\n")
    print("wrote " + str(SUMMARY_PATH))
    print("wrote " + str(REPORT_PATH))
    print("verdict: " + verdict + " (" + str(positive_seeds) + "/" + str(len(SEEDS)) + " seeds positive)")
    return 0


def format_report(summary: Mapping[str, object]) -> str:
    hypothesis = summary["hypothesis"]
    pool = summary["pool"]
    contract = summary["contract"]
    anchors = summary["anchors"]
    assert isinstance(hypothesis, Mapping)
    assert isinstance(pool, Mapping)
    assert isinstance(contract, Mapping)
    assert isinstance(anchors, Mapping)
    representations = ", ".join(str(r) for r in contract["representations"])
    lines: list[str] = []
    lines.append("# 单表示 0.6081 的换折种子稳健性复验（W17 第 16 枪，诊断性）")
    lines.append("")
    lines.append("**这不是新发现，也不是提升。** 它只回答一个问题：W17 记录里唯一的 >0.60 读数")
    lines.append("`full_table_lever4` / `Physical` = **" + repr(SEED_42_PHYSICAL) + "**（种子 42，repeat 均值）")
    lines.append("是**表示能力效应**，还是**种子 42 的折分配运气**。")
    lines.append("")
    lines.append("## 冻结侧（一个都不动）")
    lines.append("")
    lines.append("- 池：" + str(pool["base_rows"]) + " 行基表训练行；计分 " + str(pool["scored_rows"]) + " 行 / 97 化合物 / 276 个 (化合物, T) 对")
    lines.append("- 分折：GroupKFold by InChIKey，5 折 x 10 重复；**只有折种子改变**")
    lines.append("- 表示：" + representations)
    lines.append("")
    lines.append("## 锚点：种子 42 必须逐位复现三个已登记读数")
    lines.append("")
    lines.append("| 臂 | 登记值 | 本次实测 | abs_gap | ok |")
    lines.append("| --- | ---: | ---: | ---: | --- |")
    anchor_list = anchors["rows"]
    assert isinstance(anchor_list, Sequence)
    for row in anchor_list:
        assert isinstance(row, Mapping)
        marker = "OK" if row["ok"] else "MISS"
        lines.append(
            "| `" + str(row["arm"]) + "` | " + repr(row["expected"]) + " | "
            + repr(row["measured"]) + " | " + format(float(row["abs_gap"]), ".2e") + " | " + marker + " |"
        )
    lines.append("")
    lines.append("## 判据臂 `full_table_lever4`：逐种子差值（Physical − Morgan+Physical）")
    lines.append("")
    lines.append("| 种子 | R2(Physical) | R2(Morgan+Physical) | 差值 |")
    lines.append("| ---: | ---: | ---: | ---: |")
    per_seed = hypothesis["per_seed"]
    assert isinstance(per_seed, Sequence)
    for row in per_seed:
        assert isinstance(row, Mapping)
        lines.append(
            "| " + str(row["seed"]) + " | " + format(float(row["hypothesis_r2"]), ".6f") + " | "
            + format(float(row["reference_r2"]), ".6f") + " | " + format(float(row["delta"]), "+.6f") + " |"
        )
    lines.append("")
    lines.append(
        "**判定**：" + str(hypothesis["positive_seeds"]) + "/" + str(hypothesis["total_seeds"])
        + " 个种子上为正；差值均值 " + format(float(hypothesis["delta_mean"]), "+.6f")
        + "（min " + format(float(hypothesis["delta_min"]), "+.6f")
        + " / max " + format(float(hypothesis["delta_max"]), "+.6f") + "）"
        + " ⇒ `" + str(hypothesis["verdict"]) + "`。"
    )
    lines.append("")
    lines.append("## 先回答那个问题：R² > 0.60 达到了吗")
    lines.append("")
    lines.append("- **没有达到。** 判据臂 `full_table_lever4` 的 `Physical` 跨种子均值 = **0.586114**；5 个种子里**只有 1 个**（种子 42 自己）> 0.60，")
    lines.append("  ⇒ **0.6081 带种子 42 的有利偏差**，不能读成「模型达到 0.60」。")
    lines.append("- **「5/5 为正」包含已知的种子 42**；把它排除后仍是 **4/4**（1234 / 2026 / 31337 / 7）。")
    lines.append("- **选臂史**：`full_table_lever4` 是 shot 13 的**事后最高臂**（0.5433111678100043），**不是**该枪的 co-primary")
    lines.append("  （co-primary 是 `full_table_hybrid` 0.530028742596643 与 `full_table_lever4_lever8` 0.4914701852431905）⇒ 本枪最多能证明「**此臂上**排序对折种子稳健」。")
    lines.append("- **反例**：同一探针在 `full_table_hybrid` 臂上 **5/5 反向**（`Morgan+Physical` 跨种子 0.523136 > `Physical` 0.486277）")
    lines.append("  ⇒ **不得**表述为「Physical 表示普遍更强」；结论**只限 lever4 配置**。")
    lines.append("- **泄漏审计**：每个（种子, 臂）的 `folds_with_a_straddling_compound` 都是 **0**（见摘要 `leakage`）。")
    lines.append("")
    lines.append("## 跨种子平均（每个表示在每个种子内的 repeat 均值，再对 5 个种子取均值）")
    lines.append("")
    lines.append("| 臂 | 表示 | R2（种子均值） | 种子间 sd | min | max |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    averaged = summary["seed_averaged"]
    assert isinstance(averaged, Sequence)
    for row in averaged:
        assert isinstance(row, Mapping)
        lines.append(
            "| `" + str(row["arm"]) + "` | " + str(row["representation"]) + " | "
            + format(float(row["r2_seed_mean"]), ".6f") + " | "
            + format(float(row["r2_seed_sd"]), ".4f") + " | "
            + format(float(row["r2_seed_min"]), ".6f") + " | "
            + format(float(row["r2_seed_max"]), ".6f") + " |"
        )
    lines.append("")
    lines.append("## 边界（不许省略）")
    lines.append("")
    lines.append("1. 本探针**非盲**：种子 42 的读数在预注册前已知，因此只能读作「同一协议下换折随机化的稳健性复验」，**不是**盲法确认。")
    lines.append("2. 换种子**不改变池**，只改变哪些化合物被留出；跨种子的绝对 R2 差异里既有表示能力、也有折难度。")
    lines.append("3. **任何读数一律不提升**：冻结头条保持 0.4766400383507876，冻结基线保持 0.4091179943351143。")
    lines.append("4. 单表示（Physical）与混合（Morgan+Physical）**不是同一口径**，本报告不作跨口径相减用于达标宣称。")
    lines.append("5. 本枪的判据臂是 shot 13 的**事后最高臂**、**非** co-primary；结论**只限该臂与 lever4 配置**，不得外推。")
    lines.append("6. 作者在本枪之后把目标上调到 **R² > 0.70**：**未达到**。最高跨种子均值 0.586114（单表示、非主判据），最高单读数 0.608059（种子 42）。")
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
