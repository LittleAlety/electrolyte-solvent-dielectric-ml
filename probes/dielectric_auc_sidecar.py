"""Ship the two AUC columns the scoreboard computes but drops -- zero refits.

dielectric_representation_ablation.evaluate_repeat returns auc_gt15 and auc_gt30
for every repeat.  METRIC_NAMES, which drives the grouped benchmark's
REPEAT_COLUMNS_OUT, carries only seven metrics, so every scoreboard repeats CSV
silently drops both columns and the only AUC on the books lives in ranking_head
and the two representation-ablation probes.

AUC is a function of (target, prediction) alone, and the prediction rows ARE
shipped, so the columns can be restored without a single refit and without
touching one frozen byte: this probe recomputes them from the shipped
*_predictions.csv tables, writes a sidecar CSV, and re-derives the shipped R2
from the very same rows.  If the re-derived R2 disagrees with the shipped
repeats CSV, the probe refuses to write -- that would mean the rows on disk are
not the rows the scoreboard was built from.

Nothing here fits a model, opens the network, or promotes a reading.

Run:
    .venv/Scripts/python.exe probes/dielectric_auc_sidecar.py
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
import numpy as np
from dielectric_observations_grouped_benchmark import METRIC_NAMES
from dielectric_representation_ablation import evaluate_repeat
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_auc_sidecar_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_auc_sidecar.md"
SIDECAR_PATH = ARTIFACTS_DIR / "dielectric_auc_sidecar.csv"

EXPECTED_METRIC_NAMES = (
    "r2",
    "mae",
    "rmse",
    "spearman",
    "mae_lt20",
    "mae_20_60",
    "mae_gt60",
)
ADDED_COLUMNS = ("auc_gt15", "auc_gt30")
EXTENDED_METRIC_NAMES = (*EXPECTED_METRIC_NAMES, *ADDED_COLUMNS)
SIDECAR_COLUMNS = (
    "source",
    "key",
    "representation",
    "repeat",
    "rows",
    "r2",
    "r2_shipped",
    "abs_gap",
    "spearman",
    *ADDED_COLUMNS,
)

# (artifact stem, the column that names the arm/protocol)
SOURCES = (
    ("dielectric_coordination_block_v3", "arm"),
    ("dielectric_observations_benchmark", "protocol"),
    ("dielectric_room_window_paired", "protocol"),
    ("dielectric_coverage_paired_benchmark", "protocol"),
    ("dielectric_band_ablation", "protocol"),
)

R2_TOLERANCE = 1e-09
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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


def rescore_source(
    stem: str, key_column: str
) -> tuple[list[dict[str, object]], dict[str, int]]:
    """Re-derive every metric from the shipped rows, with no refit."""

    predictions_path = ARTIFACTS_DIR / (stem + "_predictions.csv")
    repeats_path = ARTIFACTS_DIR / (stem + "_repeats.csv")
    if not predictions_path.is_file() or not repeats_path.is_file():
        raise SystemExit("missing shipped table for " + stem)
    buckets: dict[tuple[str, str, int], dict[str, list[float]]] = {}
    for row in read_csv_rows(predictions_path):
        key = (str(row[key_column]), str(row["representation"]), int(row["repeat"]))
        bucket = buckets.setdefault(key, {"target": [], "prediction": []})
        bucket["target"].append(float(row["target"]))
        bucket["prediction"].append(float(row["prediction"]))
    shipped: dict[tuple[str, str, int], float] = {}
    for row in read_csv_rows(repeats_path):
        shipped[(str(row[key_column]), str(row["representation"]), int(row["repeat"]))] = float(
            row["r2"]
        )
    rows: list[dict[str, object]] = []
    missing = 0
    for (key, representation, repeat), bucket in sorted(buckets.items()):
        target = np.asarray(bucket["target"], dtype=float)
        prediction = np.asarray(bucket["prediction"], dtype=float)
        metrics = evaluate_repeat(target, prediction)
        expected = shipped.get((key, representation, repeat))
        if expected is None:
            missing += 1
            continue
        rows.append(
            {
                "source": stem,
                "key": key,
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
    counts = {
        "prediction_rows": sum(len(bucket["target"]) for bucket in buckets.values()),
        "scored_groups": len(buckets),
        "sidecar_rows": len(rows),
        "groups_without_a_shipped_r2": missing,
    }
    return rows, counts


def main(argv: Sequence[str] | None = None) -> int:
    parse_args(argv)
    started = time.perf_counter()
    started_at_utc = _utc_now()

    if tuple(METRIC_NAMES) != EXPECTED_METRIC_NAMES:
        print("METRIC_NAMES moved; this probe no longer describes the shipped schema")
        return 1

    spreadsheet: list[dict[str, object]] = []
    sources: dict[str, dict[str, object]] = {}
    for stem, key_column in SOURCES:
        rows, counts = rescore_source(stem, key_column)
        spreadsheet.extend(rows)
        gaps = [float(row["abs_gap"]) for row in rows]
        sources[stem] = {
            "key_column": key_column,
            "predictions": portable_relative_path(
                ARTIFACTS_DIR / (stem + "_predictions.csv"), root=REPOSITORY_ROOT
            ),
            "repeats": portable_relative_path(
                ARTIFACTS_DIR / (stem + "_repeats.csv"), root=REPOSITORY_ROOT
            ),
            "repeats_sha256": canonical_text_sha256(ARTIFACTS_DIR / (stem + "_repeats.csv")),
            "counts": counts,
            "max_r2_abs_gap": max(gaps) if gaps else 0.0,
            "auc_gt15_mean": float(np.mean([float(row["auc_gt15"]) for row in rows]))
            if rows
            else float("nan"),
            "auc_gt30_mean": float(np.mean([float(row["auc_gt30"]) for row in rows]))
            if rows
            else float("nan"),
        }
        print(
            "  " + stem + ": " + str(counts["sidecar_rows"]) + " groups, max r2 gap "
            + format(float(sources[stem]["max_r2_abs_gap"]), ".2e"),
            flush=True,
        )

    worst_gap = max(
        (float(block["max_r2_abs_gap"]) for block in sources.values()), default=0.0
    )
    if worst_gap > R2_TOLERANCE:
        print("a re-derived R2 disagrees with the shipped repeats table; refusing to write")
        return 1

    summary: dict[str, object] = {
        "schema": "dielectric_auc_sidecar/summary@1",
        "generated_at_utc": _utc_now(),
        "started_at_utc": started_at_utc,
        "finished_at_utc": _utc_now(),
        "wall_seconds": time.perf_counter() - started,
        "why": (
            "evaluate_repeat computes auc_gt15 and auc_gt30 but METRIC_NAMES -- which drives "
            "REPEAT_COLUMNS_OUT -- carries only seven metrics, so every scoreboard repeats "
            "CSV drops both columns; the prediction rows are shipped, so the columns can be "
            "restored offline with zero refits and zero edits to any frozen byte"
        ),
        "metric_names_shipped": list(EXPECTED_METRIC_NAMES),
        "metric_names_extended": list(EXTENDED_METRIC_NAMES),
        "r2_tolerance": R2_TOLERANCE,
        "worst_r2_abs_gap": worst_gap,
        "sources": sources,
        "frozen_repeats_untouched": {
            "note": (
                "the sha256 of every shipped repeats CSV is recorded here and re-checked by "
                "the guard test; this probe writes a new file and never rewrites one"
            )
        },
        "promotion": {
            "promoted": False,
            "frozen_headline": FROZEN_HEADLINE,
            "frozen_baseline": FROZEN_BASELINE,
            "reason": (
                "AUC is a second reading of already-shipped rows, not a new fit; it explains "
                "the R2/AUC gap but moves no frozen number"
            ),
        },
        "outputs": {
            "sidecar": portable_relative_path(SIDECAR_PATH, root=REPOSITORY_ROOT),
            "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
            "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
        },
    }

    write_csv_rows(SIDECAR_PATH, SIDECAR_COLUMNS, spreadsheet)
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(format_report(summary), encoding="utf-8", newline=chr(10))
    print("wrote " + str(SIDECAR_PATH))
    print("wrote " + str(SUMMARY_PATH))
    print("wrote " + str(REPORT_PATH))
    print("worst r2 abs gap: " + format(worst_gap, ".2e"))
    return 0


def format_report(summary: Mapping[str, object]) -> str:
    sources = summary["sources"]
    assert isinstance(sources, Mapping)
    lines: list[str] = []
    lines.append("# 把主链路丢掉的 AUC 补回来（零重拟合，不动任何冻结字节）")
    lines.append("")
    lines.append("**这不是新模型、也不是新读数。** `evaluate_repeat` 一直在算 `auc_gt15` / `auc_gt30`，")
    lines.append("但 `METRIC_NAMES`（它驱动 `REPEAT_COLUMNS_OUT`）只有 7 个指标，")
    lines.append("所以每个记分牌的 repeats CSV 都把这两列丢了；预测行本身**是随包发的**，")
    lines.append("AUC 只依赖 `(target, prediction)`，因此可以**离线重算**。")
    lines.append("")
    lines.append("## 口径")
    lines.append("")
    lines.append(
        "- 随包指标列：" + ", ".join(str(name) for name in summary["metric_names_shipped"])
    )
    lines.append("- 侧车补列：auc_gt15, auc_gt30")
    lines.append("- **不修改 `METRIC_NAMES`**：改它会改被锁 CSV 的表头与字节。本探针只**新建**文件。")
    lines.append("- 诚实性检查：用同一批预测行重新求出的 R² 必须与随包 repeats CSV **逐位一致**，")
    lines.append(
        "  容差 " + format(float(summary["r2_tolerance"]), ".0e") + "，否则拒绝写出。"
    )
    lines.append("")
    lines.append("## 各源（重新求出的 R² 与随包值之差）")
    lines.append("")
    lines.append("| 源 | key 列 | 打分组数 | 预测行 | 最大 R² 差 | AUC>15 均值 | AUC>30 均值 |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for stem, block in sources.items():
        assert isinstance(block, Mapping)
        counts = block["counts"]
        assert isinstance(counts, Mapping)
        lines.append(
            "| " + str(stem) + " | " + str(block["key_column"]) + " | "
            + str(counts["sidecar_rows"]) + " | " + str(counts["prediction_rows"]) + " | "
            + format(float(block["max_r2_abs_gap"]), ".2e") + " | "
            + format(float(block["auc_gt15_mean"]), ".4f") + " | "
            + format(float(block["auc_gt30_mean"]), ".4f") + " |"
        )
    lines.append("")
    lines.append("## 边界（不许省略）")
    lines.append("")
    lines.append("1. AUC 是**已经随包的行**的第二种读法，不是新拟合；它解释 R² 与 AUC 的差距，**不动任何冻结数**。")
    lines.append(
        "2. 冻结头条保持 " + repr(0.4766400383507876) + "，冻结基线保持 "
        + repr(0.4091179943351143) + "。"
    )
    lines.append("3. 每个随包 repeats CSV 的 sha256 已记录在摘要里，并由守护测试复核。")
    lines.append("")
    return chr(10).join(lines) + chr(10)


if __name__ == "__main__":
    raise SystemExit(main())
