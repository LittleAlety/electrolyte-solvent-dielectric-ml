"""Three splitters, one arm: does the ordering survive what the magnitude does not?

The R2/AUC gap is the whole story of this funnel, and until now it could not be
read off a single table: the fused scoreboard ships R2 only, and the one probe
that does ship AUC never ran a scaffold split.  This probe builds that table.

* random_row           the v1.0 row-level splitter, kept ONLY as a reference --
                       rows of one compound sit on both sides, so it is optimistic
                       by construction and may never be quoted as a headline.
* grouped              GroupKFold by InChIKey: the honest compound-holdout number.
* scaffold             Murcko scaffold holdout (ring scaffolds, Butina-clustered
                       acyclics), the most hostile of the three.
* grouped_single_row   one row per compound, control for the temperature expansion.

The first two and the control are re-derived with ZERO REFITS from the shipped
prediction rows; only the scaffold split is a new run, and it uses the frozen
fitter, the frozen feature blocks and the same 10x5 shape.  Nothing here
promotes a reading.

Run:
    .venv/Scripts/python.exe probes/dielectric_splitters_auc.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import dielectric_observations_grouped_benchmark as gb
import dielectric_target_and_scaffold as sc
import numpy as np
from dielectric_representation_ablation import REPRESENTATIONS, evaluate_repeat

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_splitters_auc_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_splitters_auc.md"
TABLE_PATH = ARTIFACTS_DIR / "dielectric_splitters_auc.csv"
SHIPPED_STEM = "dielectric_observations_benchmark"

TABLE_COLUMNS = (
    "protocol",
    "representation",
    "repeat",
    "rows",
    "r2",
    "r2_shipped",
    "abs_gap",
    "spearman",
    "auc_gt15",
    "auc_gt30",
)
REUSED_PROTOCOLS = ("random_row", "grouped", "grouped_single_row")
NEW_PROTOCOL = "scaffold"
PROTOCOL_ORDER = ("random_row", "grouped", NEW_PROTOCOL, "grouped_single_row")
PROTOCOL_NOTES = {
    "random_row": "行级随机（v1.0 参考划分器；同一化合物的行会同时落在两侧，天生乐观，绝不可当达标题）",
    "grouped": "化合物留出（GroupKFold by InChIKey）：唯一诚实口径",
    NEW_PROTOCOL: "骨架留出（Murcko 环骨架 + Butina 聚类无环簇）：三档里最苛刻",
    "grouped_single_row": "每化合物一行（温度扩表的对照臂）",
}
PRIMARY_PROTOCOL = "grouped"
PRIMARY_REPRESENTATION = "Morgan+Physical"
R2_TOLERANCE = 1e-09
SCAFFOLD_REPEAT_SEED_BASE = 2026
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-scaffold", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    return parser.parse_args(argv)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator=chr(10))
        writer.writeheader()
        writer.writerows(rows)


def rescore_shipped() -> list[dict[str, object]]:
    """Part A: zero-refit re-derivation of the three shipped protocols."""

    buckets: dict[tuple[str, str, int], dict[str, list[float]]] = {}
    for row in read_csv_rows(ARTIFACTS_DIR / (SHIPPED_STEM + "_predictions.csv")):
        key = (str(row["protocol"]), str(row["representation"]), int(row["repeat"]))
        bucket = buckets.setdefault(key, {"target": [], "prediction": []})
        bucket["target"].append(float(row["target"]))
        bucket["prediction"].append(float(row["prediction"]))
    shipped: dict[tuple[str, str, int], float] = {}
    for row in read_csv_rows(ARTIFACTS_DIR / (SHIPPED_STEM + "_repeats.csv")):
        key = (str(row["protocol"]), str(row["representation"]), int(row["repeat"]))
        shipped[key] = float(row["r2"])
    rows: list[dict[str, object]] = []
    for (protocol, representation, repeat), bucket in sorted(buckets.items()):
        target = np.asarray(bucket["target"], dtype=float)
        prediction = np.asarray(bucket["prediction"], dtype=float)
        metrics = evaluate_repeat(target, prediction)
        expected = shipped.get((protocol, representation, repeat))
        if expected is None:
            continue
        rows.append(
            {
                "protocol": protocol,
                "representation": representation,
                "repeat": int(repeat),
                "rows": int(target.size),
                "r2": float(metrics["r2"]),
                "r2_shipped": float(expected),
                "abs_gap": abs(float(metrics["r2"]) - float(expected)),
                "spearman": float(metrics["spearman"]),
                "auc_gt15": float(metrics["auc_gt15"]),
                "auc_gt30": float(metrics["auc_gt30"]),
            }
        )
    return rows


def scaffold_splits(scaffold_values: Sequence[str]) -> Iterator[tuple[int, int, np.ndarray, np.ndarray]]:
    for repeat in range(gb.N_REPEATS):
        for fold, (train, test) in enumerate(
            sc.scaffold_folds(
                scaffold_values,
                n_splits=gb.N_SPLITS,
                seed=SCAFFOLD_REPEAT_SEED_BASE + repeat,
            )
        ):
            yield repeat, fold, train, test


def run_scaffold() -> tuple[list[dict[str, object]], dict[str, object]]:
    """Part B: the one genuinely new run."""

    rows, _features, dropped = gb.load_table(gb.OBSERVATIONS_PATH, gb.FEATURES_PATH)
    morgan, physical, target, temperatures, groups = gb.build_matrices(rows)
    smiles_by_compound: dict[str, str] = {}
    for row in rows:
        smiles_by_compound.setdefault(str(row["inchikey"]), str(row["smiles"]))
    compounds = sorted(smiles_by_compound)
    keys = sc.scaffold_group_keys([smiles_by_compound[key] for key in compounds])
    scaffold_of_compound = dict(zip(compounds, keys, strict=True))
    scaffold_values = [scaffold_of_compound[str(group)] for group in groups]
    _fold_rows, _repeat_rows, prediction_rows, leak = gb.run_protocol(
        NEW_PROTOCOL,
        scaffold_splits(scaffold_values),
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
    )
    buckets: dict[tuple[str, str, int], dict[str, list[float]]] = {}
    for row in prediction_rows:
        key = (str(row["representation"]), int(row["repeat"]))
        bucket = buckets.setdefault(key, {"target": [], "prediction": []})
        bucket["target"].append(float(row["target"]))
        bucket["prediction"].append(float(row["prediction"]))
    table: list[dict[str, object]] = []
    for (representation, repeat), bucket in sorted(buckets.items()):
        target_array = np.asarray(bucket["target"], dtype=float)
        prediction_array = np.asarray(bucket["prediction"], dtype=float)
        metrics = evaluate_repeat(target_array, prediction_array)
        table.append(
            {
                "protocol": NEW_PROTOCOL,
                "representation": representation,
                "repeat": int(repeat),
                "rows": int(target_array.size),
                "r2": float(metrics["r2"]),
                "r2_shipped": float("nan"),
                "abs_gap": float("nan"),
                "spearman": float(metrics["spearman"]),
                "auc_gt15": float(metrics["auc_gt15"]),
                "auc_gt30": float(metrics["auc_gt30"]),
            }
        )
    meta = {
        "rows": len(rows),
        "compounds": len(smiles_by_compound),
        "scaffold_groups": len(set(scaffold_values)),
        "dropped": dropped,
        "leak": leak,
        "seeds": [SCAFFOLD_REPEAT_SEED_BASE + repeat for repeat in range(gb.N_REPEATS)],
    }
    return table, meta


def aggregate(rows: Sequence[Mapping[str, object]]) -> dict[str, dict[str, dict[str, float]]]:
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in rows:
        grouped.setdefault((str(row["protocol"]), str(row["representation"])), []).append(row)
    summary: dict[str, dict[str, dict[str, float]]] = {}
    for (protocol, representation), items in sorted(grouped.items()):
        summary.setdefault(protocol, {})[representation] = {
            metric: float(np.mean([float(item[metric]) for item in items]))
            for metric in ("r2", "spearman", "auc_gt15", "auc_gt30")
        }
        summary[protocol][representation]["repeats"] = float(len(items))
        summary[protocol][representation]["rows"] = float(items[0]["rows"])
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    started_at_utc = _utc_now()

    reused = rescore_shipped()
    reused = [row for row in reused if str(row["protocol"]) in REUSED_PROTOCOLS]
    gaps = [float(row["abs_gap"]) for row in reused]
    worst_gap = max(gaps) if gaps else 0.0
    if worst_gap > R2_TOLERANCE:
        print("a re-derived R2 disagrees with the shipped repeats table; refusing to write")
        return 1
    print(
        "reused: " + str(len(reused)) + " groups, max r2 gap " + format(worst_gap, ".2e"),
        flush=True,
    )

    scaffold_rows: list[dict[str, object]] = []
    scaffold_meta: dict[str, object] = {}
    if not args.skip_scaffold:
        clock = time.perf_counter()
        scaffold_rows, scaffold_meta = run_scaffold()
        print(
            "scaffold: " + str(len(scaffold_rows)) + " groups in "
            + format(time.perf_counter() - clock, ".1f") + "s",
            flush=True,
        )
        leak = scaffold_meta["leak"]
        assert isinstance(leak, Mapping)
        if int(leak["folds_with_a_straddling_compound"]) != 0:
            print("a compound straddled a scaffold fold; refusing to write")
            return 1

    table = reused + scaffold_rows
    summary_by_protocol = aggregate(table)

    summary: dict[str, object] = {
        "schema": "dielectric_splitters_auc/summary@1",
        "generated_at_utc": _utc_now(),
        "started_at_utc": started_at_utc,
        "finished_at_utc": _utc_now(),
        "wall_seconds": time.perf_counter() - started,
        "question": (
            "on one arm and one representation, what does the ordering metric keep while the "
            "magnitude metric collapses, and at which splitter does each of them break?"
        ),
        "frozen_side": {
            "fit_predict": "dielectric_representation_ablation.fit_predict_representation",
            "representations": list(REPRESENTATIONS),
            "n_splits": gb.N_SPLITS,
            "n_repeats": gb.N_REPEATS,
            "observations": portable_relative_path(gb.OBSERVATIONS_PATH, root=REPOSITORY_ROOT),
            "features": portable_relative_path(gb.FEATURES_PATH, root=REPOSITORY_ROOT),
        },
        "protocol_notes": PROTOCOL_NOTES,
        "protocol_order": list(PROTOCOL_ORDER),
        "primary": {"protocol": PRIMARY_PROTOCOL, "representation": PRIMARY_REPRESENTATION},
        "reused_from_shipped_predictions": list(REUSED_PROTOCOLS),
        "reused_max_r2_abs_gap": worst_gap,
        "new_run": scaffold_meta,
        "shipped_predictions_sha256": canonical_text_sha256(
            ARTIFACTS_DIR / (SHIPPED_STEM + "_predictions.csv")
        ),
        "by_protocol": summary_by_protocol,
        "promotion": {
            "promoted": False,
            "frozen_headline": FROZEN_HEADLINE,
            "frozen_baseline": FROZEN_BASELINE,
            "reason": (
                "random_row is a leak reference and grouped/scaffold are the honest numbers; "
                "this probe explains the R2/AUC gap and moves no frozen value"
            ),
        },
        "outputs": {
            "table": portable_relative_path(TABLE_PATH, root=REPOSITORY_ROOT),
            "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
            "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
        },
    }

    write_csv_rows(TABLE_PATH, TABLE_COLUMNS, table)
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )
    REPORT_PATH.write_text(format_report(summary), encoding="utf-8", newline=chr(10))
    print("wrote " + str(TABLE_PATH))
    print("wrote " + str(SUMMARY_PATH))
    print("wrote " + str(REPORT_PATH))
    return 0


def format_report(summary: Mapping[str, object]) -> str:
    by_protocol = summary["by_protocol"]
    assert isinstance(by_protocol, Mapping)
    lines: list[str] = []
    lines.append("# 三档划分 × 排序/量级：我们不是模型差，是量级学不会")
    lines.append("")
    lines.append("**同一个臂、同一个表示、同一套冻结超参**，只换划分器。")
    lines.append("R² 量的是量级，AUC/Spearman 量的是排序；这张表把两者的分岔摆在一起。")
    lines.append("")
    lines.append("## 主表（每个格子 = 10 个重复的均值）")
    lines.append("")
    lines.append("| 划分器 | 表示 | R² | Spearman | AUC>15 | AUC>30 |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    for protocol in summary["protocol_order"]:
        block = by_protocol.get(str(protocol))
        if not isinstance(block, Mapping):
            continue
        for representation in summary["frozen_side"]["representations"]:
            cell = block.get(str(representation))
            if not isinstance(cell, Mapping):
                continue
            lines.append(
                "| " + str(protocol) + " | " + str(representation) + " | "
                + format(float(cell["r2"]), "+.4f") + " | "
                + format(float(cell["spearman"]), "+.4f") + " | "
                + format(float(cell["auc_gt15"]), ".4f") + " | "
                + format(float(cell["auc_gt30"]), ".4f") + " |"
            )
    lines.append("")
    lines.append("## 划分器的性质（决定这个数能不能引用）")
    lines.append("")
    notes = summary["protocol_notes"]
    assert isinstance(notes, Mapping)
    for protocol in summary["protocol_order"]:
        lines.append("- `" + str(protocol) + "`：" + str(notes.get(str(protocol), "")))
    lines.append("")
    new_run = summary["new_run"]
    assert isinstance(new_run, Mapping)
    lines.append("## 池（决定这些数能不能和 ε 记分牌相减）")
    lines.append("")
    lines.append(
        "- 本表跑在**温度分辨观测表**上：" + str(new_run["rows"]) + " 行 / "
        + str(new_run["compounds"]) + " 化合物；骨架档切成 "
        + str(new_run["scaffold_groups"]) + " 个骨架族。"
    )
    lines.append(
        "- 这**不是** ε 主记分牌的 457 行 / 97 化合物；**两块池不得相减，也不得混比**。"
    )
    lines.append(
        "- ~random_row~ / ~grouped~ / ~grouped_single_row~ 三档零重拟合重算，最大 R² 偏差 "
        + format(float(summary["reused_max_r2_abs_gap"]), ".2e") + "；~scaffold~ 本轮新跑。"
    )
    lines.append("")
    lines.append("## 怎么读")
    lines.append("")
    lines.append("1. `random_row` 的 R² 与 AUC 双双最高，但同一化合物的行同时落在训练与测试两侧，")
    lines.append("   所以它是**泄漏参考**，只能用来量「泄漏能把 R² 抬多高」，**不得当达标题**。")
    lines.append("2. 换成化合物留出后，R² 大幅塌陷而 AUC 仍显著高于 0.5 ⇒ **排序学会了、量级没学会**。")
    lines.append("3. 骨架留出是最苛刻的一档：若它的 AUC 仍高于 0.5，说明排序能力**能跨骨架族**；")
    lines.append("   若它也塌到 0.5 附近，则本叙事被证否，必须照实登记。")
    lines.append("")
    lines.append("## 边界（不许省略）")
    lines.append("")
    lines.append(
        "1. `random_row` / `grouped` / `grouped_single_row` 三档是**从已随包的预测行零重拟合重算**的，"
        "最大 R² 偏差 " + format(float(summary["reused_max_r2_abs_gap"]), ".2e") + "；"
        "只有 `scaffold` 是本轮新跑。"
    )
    lines.append(
        "2. 冻结头条保持 " + repr(FROZEN_HEADLINE) + "，冻结基线保持 " + repr(FROZEN_BASELINE) + "。"
    )
    lines.append("3. 三档的 R² **不是同一个口径**，不得跨划分器相减后宣称任何提升。")
    lines.append("")
    return chr(10).join(lines) + chr(10)


if __name__ == "__main__":
    raise SystemExit(main())
