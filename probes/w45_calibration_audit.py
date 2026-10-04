# -*- coding: utf-8 -*-
"""W45-A：扩展层标定列的保真与泄漏审计（计算 lane，0 shot）。

W43 落下的扩展层有一列 calib_homo_eV / calib_lumo_eV（calibration_id =
themol_gfn2_to_batt_2fold_v2_registry_wide），从未被审计过。本件只读审计三件事：
  * 变换类：calib 是不是 homo_gfn2 / lumo_gfn2 的**精确一元仿射**（残差上限）？
  * 归因：这条仿射与「homo_gfn2 -> batt_homo」的 in-sample OLS 是否同一个映射？
    仿射保序 => calib 相对 Batt 的秩一致 == 原始 gfn2 相对 Batt 的秩一致 => 只补电平不补序。
  * 泄漏：在 5 折（按 InChIKey 哈希分折）上复拟合同一变换，比较 out-of-sample 与 in-sample MAE
    （泄漏缺口），并把 449 行 calibrated_estimate（无 Batt 双端）是否套用同一映射一并报出。

只读；不改 calib 列、不改标签或特征列；累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w45_calibration_audit.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
from scipy import stats

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from export_results_common import write_json_stable
from w42_common import (
    ARTIFACTS,
    FROZEN_READINGS,
    criteria_row,
    sha256_file,
    utc_now,
    write_csv_lf,
)
from w45_common import (
    EXPANDED_CSV,
    affine_fit,
    calibrated_rows,
    kfold_by_key,
    max_abs_residual,
    paired_rows,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w45_compute_prereg.json"
AUDIT_CSV = ARTIFACTS / "w45_calibration_audit.csv"
AUDIT_JSON = ARTIFACTS / "w45_calibration_audit.json"
SUMMARY_PATH = ARTIFACTS / "w45_calibration_audit_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w45_calibration_audit.md"

SCHEMA = "w45_calibration_audit/summary@1"
TASK = "week45_calibration_audit"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

TARGETS = {
    "homo": ("homo_gfn2_eV", "batt_homo_eV", "calib_homo_eV"),
    "lumo": ("lumo_gfn2_eV", "batt_lumo_eV", "calib_lumo_eV"),
}
AUDIT_FIELDS = ("target", "n", "affine_slope", "affine_intercept", "affine_max_abs_residual",
                "batt_fit_slope", "batt_fit_intercept", "slope_delta", "intercept_delta",
                "spearman_gfn2_batt", "spearman_calib_batt", "rank_invariance_delta",
                "mae_before_ev", "mae_after_ev", "mae_cv_ev", "leakage_gap_ev")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w45 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def _audit_target(rows: Sequence[Mapping[str, object]], columns: Sequence[str],
                  folds: int, seed: int) -> dict[str, object]:
    gfn2_column, batt_column, calib_column = columns
    rows = [row for row in rows
            if all(isinstance(row.get(column), float) for column in columns)]
    x = np.asarray([float(row[gfn2_column]) for row in rows], dtype=float)
    y = np.asarray([float(row[batt_column]) for row in rows], dtype=float)
    c = np.asarray([float(row[calib_column]) for row in rows], dtype=float)
    keys = [str(row["inchikey"]) for row in rows]

    slope, intercept, residual = affine_fit(x, c)
    batt_slope, batt_intercept, _ = affine_fit(x, y)

    spearman_raw = float(stats.spearmanr(x, y).statistic)
    spearman_calib = float(stats.spearmanr(c, y).statistic)

    mae_before = float(np.mean(np.abs(x - y)))
    mae_after = float(np.mean(np.abs(c - y)))

    assignment = kfold_by_key(keys, folds, seed)
    out_of_sample: list[float] = []
    in_sample: list[float] = []
    for fold in range(folds):
        train = [i for i, value in enumerate(assignment) if value != fold]
        test = [i for i, value in enumerate(assignment) if value == fold]
        if not train or not test:
            continue
        fold_slope, fold_intercept, _ = affine_fit(x[train], y[train])
        predict_test = fold_slope * x[test] + fold_intercept
        predict_train = fold_slope * x[train] + fold_intercept
        out_of_sample.extend(np.abs(predict_test - y[test]).tolist())
        in_sample.extend(np.abs(predict_train - y[train]).tolist())
    mae_cv = float(np.mean(out_of_sample))
    mae_insample_fold = float(np.mean(in_sample))

    return {
        "n": int(len(rows)),
        "affine_slope": slope,
        "affine_intercept": intercept,
        "affine_max_abs_residual": residual,
        "batt_fit_slope": batt_slope,
        "batt_fit_intercept": batt_intercept,
        "slope_delta": abs(slope - batt_slope),
        "intercept_delta": abs(intercept - batt_intercept),
        "spearman_gfn2_batt": spearman_raw,
        "spearman_calib_batt": spearman_calib,
        "rank_invariance_delta": abs(spearman_calib - spearman_raw),
        "mae_before_ev": mae_before,
        "mae_after_ev": mae_after,
        "mae_cv_ev": mae_cv,
        "leakage_gap_ev": mae_cv - mae_insample_fold,
    }


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    lane = prereg["lanes"]["w45_calibration_audit"]
    folds = int(lane["cv_folds"])
    seed = int(lane["cv_seed"])
    paired = paired_rows()
    calibrated = calibrated_rows()

    rows: list[dict[str, object]] = []
    coverage: dict[str, int] = {}
    for target in lane["targets"]:
        columns = TARGETS[str(target)]
        coverage[str(target)] = sum(1 for row in paired
                                    if isinstance(row.get(columns[2]), float))
        if coverage[str(target)] == 0:
            continue
        record = _audit_target(paired, columns, folds, seed)
        record["target"] = str(target)
        rows.append(record)

    # 449 行 calibrated_estimate 是否套用同一映射（homo）
    ce_x = np.asarray([float(row["homo_gfn2_eV"]) for row in calibrated], dtype=float)
    ce_c = np.asarray([float(row["calib_homo_eV"]) for row in calibrated], dtype=float)
    homo = next(row for row in rows if row["target"] == "homo")
    ce_residual = max_abs_residual(ce_x, ce_c, float(homo["affine_slope"]),
                                   float(homo["affine_intercept"]))
    ce_fit_slope, ce_fit_intercept, _ = affine_fit(ce_x, ce_c) if len(calibrated) > 2 else (float("nan"),) * 3

    return {
        "paired_rows": len(paired),
        "calibrated_rows": len(calibrated),
        "calibration_coverage": coverage,
        "rows": rows,
        "calibrated_same_map_max_abs_residual": ce_residual,
        "calibrated_own_fit_slope": float(ce_fit_slope),
        "calibrated_own_fit_intercept": float(ce_fit_intercept),
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    gates = prereg["lanes"]["w45_calibration_audit"]["gates"]
    by_target = {str(row["target"]): row for row in payload["rows"]}
    homo = by_target["homo"]
    tol = float(gates["affine_max_abs_residual_max"])
    map_tol = float(gates["map_matches_batt_fit_tol"])
    rank_tol = float(gates["rank_invariance_tol"])
    return [
        criteria_row("H45a1", "paired_anchor 行数 >= 4600（双端 gap 齐备）",
                     payload["paired_rows"], int(gates["paired_rows_min"]),
                     int(payload["paired_rows"]) >= int(gates["paired_rows_min"])),
        criteria_row("H45a2", "calibrated_estimate 行数 >= 400",
                     payload["calibrated_rows"], int(gates["calibrated_rows_min"]),
                     int(payload["calibrated_rows"]) >= int(gates["calibrated_rows_min"])),
        criteria_row("H45a3", "calib_homo 是 homo_gfn2 的精确一元仿射（残差上限 <= 1e-9）",
                     homo["affine_max_abs_residual"], tol,
                     float(homo["affine_max_abs_residual"]) <= tol),
        criteria_row("H45a4", "该仿射与 homo_gfn2->homo_batt 的 in-sample OLS 同一映射",
                     {"slope_delta": homo["slope_delta"], "intercept_delta": homo["intercept_delta"]},
                     {"tolerance": map_tol},
                     float(homo["slope_delta"]) <= map_tol and float(homo["intercept_delta"]) <= map_tol),
        criteria_row("H45a5", "仿射保序：rho(calib_homo,batt) == rho(homo_gfn2,batt)",
                     {"spearman_gfn2_batt": homo["spearman_gfn2_batt"],
                      "spearman_calib_batt": homo["spearman_calib_batt"],
                      "delta": homo["rank_invariance_delta"]},
                     {"tolerance": rank_tol},
                     float(homo["rank_invariance_delta"]) <= rank_tol),
        criteria_row("H45a6", "标定只补电平：homo MAE 从 >= 1.0 降到 <= 0.35 eV",
                     {"before": homo["mae_before_ev"], "after": homo["mae_after_ev"]},
                     {"before_min": gates["homo_mae_before_min"], "after_max": gates["homo_mae_after_max"]},
                     float(homo["mae_before_ev"]) >= float(gates["homo_mae_before_min"])
                     and float(homo["mae_after_ev"]) <= float(gates["homo_mae_after_max"])),
        criteria_row("H45a7", "标定只覆盖 homo：calib_lumo 在 paired 行上非空计数 = 0（登记为已知边界）",
                     {"calib_homo_nonempty": payload["calibration_coverage"].get("homo"),
                      "calib_lumo_nonempty": payload["calibration_coverage"].get("lumo")},
                     {"calib_lumo_nonempty": 0},
                     int(payload["calibration_coverage"].get("lumo", -1)) == 0),
        criteria_row("H45a8", "449 行 calibrated_estimate 套用同一映射（残差上限 <= 1e-9）",
                     payload["calibrated_same_map_max_abs_residual"], tol,
                     float(payload["calibrated_same_map_max_abs_residual"]) <= tol),
        criteria_row("H45a9", "5 折 out-of-sample 复拟合 MAE <= 0.45 eV 且泄漏缺口 >= 0",
                     {"cv_mae": homo["mae_cv_ev"], "leakage_gap": homo["leakage_gap_ev"]},
                     {"cv_mae_max": gates["cv_mae_after_max_ev"], "leakage_gap_min": gates["leakage_gap_min"]},
                     float(homo["mae_cv_ev"]) <= float(gates["cv_mae_after_max_ev"])
                     and float(homo["leakage_gap_ev"]) >= float(gates["leakage_gap_min"])),
        criteria_row("H45a10", "输入（扩展层 + prereg）sha256 未变", "before == after", True, True),
    ]


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "# W45-A 扩展层标定列的保真与泄漏审计",
        "",
        "只读计算 lane；0 shot。问题：calib_* 是不是 in-sample 仿射、补电平还是补序、泄漏多大。",
        "",
        "## 1 标定映射",
        "",
        "| target | n | slope | intercept | 残差上限 | batt-fit slope | batt-fit intercept |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append("| " + str(row["target"]) + " | " + str(row["n"]) + " | "
                     + repr(row["affine_slope"]) + " | " + repr(row["affine_intercept"]) + " | "
                     + repr(row["affine_max_abs_residual"]) + " | " + repr(row["batt_fit_slope"]) + " | "
                     + repr(row["batt_fit_intercept"]) + " |")
    lines += [
        "",
        "## 2 保序与电平",
        "",
        "| target | rho(gfn2,batt) | rho(calib,batt) | 差 | MAE 前 | MAE 后 | CV MAE | 泄漏缺口 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append("| " + str(row["target"]) + " | " + repr(row["spearman_gfn2_batt"]) + " | "
                     + repr(row["spearman_calib_batt"]) + " | " + repr(row["rank_invariance_delta"]) + " | "
                     + repr(row["mae_before_ev"]) + " | " + repr(row["mae_after_ev"]) + " | "
                     + repr(row["mae_cv_ev"]) + " | " + repr(row["leakage_gap_ev"]) + " |")
    lines += [
        "",
        "- 449 行 calibrated_estimate 套用同一映射的残差上限： "
        + repr(payload["calibrated_same_map_max_abs_residual"]) + "。",
        "",
        "## 3 判据",
        "",
        "| 判据 | 描述 | 读数 | 阈值 | 结论 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in criteria:
        value = item["value"]
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        threshold = item["threshold"]
        ttext = json.dumps(threshold, ensure_ascii=False) if isinstance(threshold, (dict, list)) else str(threshold)
        lines.append("| " + str(item["id"]) + " | " + str(item["description"]) + " | " + text
                     + " | " + ttext + " | " + str(item["verdict"]) + " |")
    lines += [
        "",
        "## 4 边界",
        "",
        "- 只读：不改 calib 列、不改标签或特征列。",
        "- 结论：该标定列是 2 参数 in-sample 仿射；仿射保序，因此它对 Batt 的秩一致与原始 gfn2 完全相同，只补电平不补序。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只跑判据并以退出码表示结果")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [PREREG_PATH, EXPANDED_CSV]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria[-1] = criteria_row("H45a10", "输入（扩展层 + prereg）sha256 未变",
                                inputs_unchanged, True, bool(inputs_unchanged))
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(AUDIT_CSV, AUDIT_FIELDS, payload["rows"])
        write_json_stable(AUDIT_JSON, {
            "paired_rows": payload["paired_rows"],
            "calibrated_rows": payload["calibrated_rows"],
            "rows": payload["rows"],
            "calibrated_same_map_max_abs_residual": payload["calibrated_same_map_max_abs_residual"],
        })
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只读审计扩展层标定列，不拟合主记分牌臂、不加特征列、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "paired_rows": payload["paired_rows"],
            "calibrated_rows": payload["calibrated_rows"],
            "audit_rows": payload["rows"],
            "calibrated_same_map_max_abs_residual": payload["calibrated_same_map_max_abs_residual"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "calib_homo 是 homo_gfn2 的精确一元仿射（残差 " + repr(payload["rows"][0]["affine_max_abs_residual"]) + "），"
                + "且与 homo_gfn2->homo_batt 的 in-sample OLS 同一映射。",
                "仿射保序：rho(calib,batt) == rho(gfn2,batt)（差 "
                + repr(payload["rows"][0]["rank_invariance_delta"]) + "）=> 只补电平不补序。",
                "homo MAE " + repr(payload["rows"][0]["mae_before_ev"]) + " -> "
                + repr(payload["rows"][0]["mae_after_ev"]) + " eV；5 折 CV MAE "
                + repr(payload["rows"][0]["mae_cv_ev"]) + " eV。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("paired %d calibrated %d" % (payload["paired_rows"], payload["calibrated_rows"]))
    for row in payload["rows"]:
        print("%s slope %r intercept %r resid %r rankdelta %r mae %r->%r cv %r"
              % (row["target"], row["affine_slope"], row["affine_intercept"],
                 row["affine_max_abs_residual"], row["rank_invariance_delta"],
                 row["mae_before_ev"], row["mae_after_ev"], row["mae_cv_ev"]))
    print("ce same-map max abs residual %r" % payload["calibrated_same_map_max_abs_residual"])
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
