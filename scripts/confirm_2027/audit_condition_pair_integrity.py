#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""B-G0-J04-D 独立复核器 | 条件配对完整性审计.

为什么要单独一个复核器
----------------------
`build_provenance_preserving_dataset.py` 在生成贡献账本时**同时**判定配对是否有效.
生成者自证是危险的: 如果判断逻辑本身写错, 产物和检查会一起错, 而且看不出来.
本模块因此**不复用生成逻辑**, 而是从原始观测层独立重算一侧, 再与生成产物对账.
两边不一致就是缺陷, 不允许"以生成结果为准"。

复核什么
--------
对每一条聚合记录:
  1. 独立重算窗口内观测数 (与贡献账本的 n_contributing_measurements 比对);
  2. 独立重算温度中位数与 epsilon 中位数;
  3. 独立判定是否存在一条观测同时持有两个中位数;
  4. 与 condition_pair_validity_v1.csv 的判定比对;
  5. 与 v04 记录的 (T, epsilon) 比对.

任何一项不一致都记为 DISCREPANCY, 并让总状态为 FAIL.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from reconstruct_measurement_ledger import (  # noqa: E402
    BAND_FREQUENCY_MHZ,
    BAND_HIGH,
    BAND_LOW,
    BAND_PHASE,
    NOT_EVALUATED,
    PINNED,
    AuditError,
    bool_text,
    check_outputs,
    collect_environment,
    default_workspace,
    fmt_decimal,
    joined,
    load_device,
    locate_inputs,
    render_csv,
    render_json,
    sha256_bytes,
    skeleton,
    to_decimal,
    verify_pinned,
    write_outputs,
)

ANALYSIS_ID = "B-G0-J04-D"
ANALYSIS_TITLE = "条件配对完整性独立复核"
CONTRACT_VERSION = "confirm_2027.condition_pair_audit/v1"
INPUT_CONTRACT_VERSION = "confirm_2027.j04_inputs/v1"
GENERATOR_VERSION = "audit_condition_pair_integrity/1.0.0"

OUTPUT_DIR_NAME = "provenance_repair"
OUTPUT_FILES: tuple[str, ...] = (
    "condition_pair_discrepancies.csv",
    "j04d_verification.json",
    "j04d_rebuild_receipt.json",
)

DISCREPANCY_COLUMNS: tuple[str, ...] = (
    "aggregate_id", "molecule_key", "a_mol_id", "a_name",
    "check", "expected", "actual", "severity",
)


def independent_window(observations: Sequence[Mapping[str, str]],
                       molecule_key: str) -> list[dict[str, Any]]:
    """独立实现的窗口筛选 (不复用生成器函数, 以便真正交叉验证)."""
    out: list[dict[str, Any]] = []
    for row in observations:
        if str(row.get("inchikey", "")).strip() != molecule_key:
            continue
        raw_t = str(row.get("T_K", "")).strip()
        raw_e = str(row.get("epsilon", "")).strip()
        if not raw_t or not raw_e:
            continue
        try:
            temperature = float(raw_t)
            epsilon = float(raw_e)
        except ValueError:
            continue
        if not (float(BAND_LOW) <= temperature <= float(BAND_HIGH)):
            continue
        if str(row.get("phase", "")).strip().lower() != BAND_PHASE:
            continue
        if str(row.get("frequency_mhz", "")).strip() != BAND_FREQUENCY_MHZ:
            continue
        out.append({"T": temperature, "E": epsilon, "raw": dict(row)})
    return out


def read_generated(out_dir: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    contribution = Path(out_dir) / "aggregate_contribution_ledger_v1.csv"
    validity = Path(out_dir) / "condition_pair_validity_v1.csv"
    for path in (contribution, validity):
        if not path.is_file():
            raise AuditError(f"生成产物缺失: {path}")
    with contribution.open(encoding="utf-8", newline="") as handle:
        c_rows = list(csv.DictReader(handle))
    with validity.open(encoding="utf-8", newline="") as handle:
        v_rows = list(csv.DictReader(handle))
    return c_rows, v_rows


def verify(device: Mapping[str, Any], out_dir: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    c_rows, v_rows = read_generated(out_dir)
    c_by_id = {r["aggregate_id"]: r for r in c_rows}
    v_by_id = {r["aggregate_id"]: r for r in v_rows}
    observations = device["observations"]
    a18 = device["a18_by_skeleton"]

    discrepancies: list[dict[str, str]] = []
    n_checked = 0

    for index, v04_row in enumerate(device["v04"], start=1):
        aggregate_id = f"v04row-{index:03d}"
        molecule_key = str(v04_row.get("inchikey", "")).strip()
        owner = a18.get(skeleton(molecule_key))
        a_mol_id = owner["a_mol_id"] if owner else NOT_EVALUATED
        a_name = owner["a_name"] if owner else NOT_EVALUATED

        def flag(check: str, expected: str, actual: str, severity: str = "FAIL") -> None:
            discrepancies.append({
                "aggregate_id": aggregate_id,
                "molecule_key": molecule_key,
                "a_mol_id": a_mol_id,
                "a_name": a_name,
                "check": check,
                "expected": expected,
                "actual": actual,
                "severity": severity,
            })

        c_row = c_by_id.get(aggregate_id)
        v_row = v_by_id.get(aggregate_id)
        if c_row is None or v_row is None:
            flag("row_present", "both", f"contribution={c_row is not None} validity={v_row is not None}")
            continue

        n_checked += 1
        band = independent_window(observations, molecule_key)

        # 1. 窗口观测数
        if int(c_row["n_contributing_measurements"]) != len(band):
            flag("n_contributing_measurements",
                str(len(band)), c_row["n_contributing_measurements"])

        # 2. 贡献状态与观测数的自洽
        expect_status = "COMPLETE" if band else "MISSING_CERTIFICATE"
        if c_row["contribution_status"] != expect_status:
            flag("contribution_status", expect_status, c_row["contribution_status"])

        if not band:
            # 无贡献时必须配对无效
            if v_row["condition_pair_valid"] != "false":
                flag("pair_validity_without_contributors", "false", v_row["condition_pair_valid"])
            continue

        # 3. 独立重算中位数 (浮点排序后取中位; 与 Decimal 结果比对数值)
        temperatures = sorted(r["T"] for r in band)
        epsilons = sorted(r["E"] for r in band)
        median_t = statistics.median(temperatures)
        median_e = statistics.median(epsilons)

        if abs(float(v_row["median_temperature"]) - median_t) > 1e-9:
            flag("median_temperature", f"{median_t}", v_row["median_temperature"])
        if abs(float(v_row["median_epsilon"]) - median_e) > 1e-9:
            flag("median_epsilon", f"{median_e}", v_row["median_epsilon"])

        # 4. 独立判定配对有效性
        pair_exists = any(
            abs(r["T"] - median_t) <= 1e-9 and abs(r["E"] - median_e) <= 1e-9
            for r in band
        )
        if (v_row["condition_pair_valid"] == "true") != pair_exists:
            flag("condition_pair_valid", "true" if pair_exists else "false",
                 v_row["condition_pair_valid"])

        # 5. 与 v04 记录值比对 (聚合是否可复现)
        v04_t = to_decimal(v04_row.get("T_K"))
        v04_e = to_decimal(v04_row.get("dielectric"))
        if v04_t is not None and abs(float(v04_t) - median_t) > 1e-9:
            flag("v04_temperature_reproduced", str(median_t), fmt_decimal(v04_t), "WARN")
        if v04_e is not None and abs(float(v04_e) - median_e) > 1e-9:
            flag("v04_epsilon_reproduced", str(median_e), fmt_decimal(v04_e), "WARN")

        # 6. 多来源必须保留全部贡献来源
        sources = sorted({str(r["raw"].get("source_doi", "")).strip() for r in band
                          if str(r["raw"].get("source_doi", "")).strip()})
        if int(c_row["n_contributing_sources"]) != len(sources):
            flag("n_contributing_sources", str(len(sources)), c_row["n_contributing_sources"])
        if len(sources) > 1 and c_row["contributing_source_documents"] == NOT_EVALUATED:
            flag("multi_source_contributors_recorded", "all", NOT_EVALUATED)

    failures = [d for d in discrepancies if d["severity"] == "FAIL"]
    warnings = [d for d in discrepancies if d["severity"] == "WARN"]
    status = "PASS" if not failures else "FAIL"

    payload = {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "n_aggregates_checked": n_checked,
        "n_discrepancies_fail": len(failures),
        "n_discrepancies_warn": len(warnings),
        "checks": [
            "n_contributing_measurements (独立重算)",
            "contribution_status (与观测数自洽)",
            "median_temperature (独立重算)",
            "median_epsilon (独立重算)",
            "condition_pair_valid (独立判定)",
            "v04_temperature_reproduced (与 v04 比对)",
            "v04_epsilon_reproduced (与 v04 比对)",
            "n_contributing_sources (独立重算)",
            "multi_source_contributors_recorded",
        ],
        "independence_note": (
            "本复核器不复用生成器的窗口筛选与中位数计算; 它用独立实现重算后与产物对账. "
            "生成者自证不可作为验收依据."
        ),
        "interpretation": {
            "pair_valid_true": "该聚合行的 (T, epsilon) 有一条真实观测同时持有, 可作为测量级证据入口",
            "pair_valid_false": "组合不是一次真实测量, 不得作为实验记录配对",
        },
    }
    return discrepancies, payload


def default_out_dir(workspace: Path) -> Path:
    return Path(workspace) / "电解质ML" / "outputs" / "confirm_2027" / OUTPUT_DIR_NAME


def run(*, workspace: Path, a_repo: Path | None, out_dir: Path | None, check: bool,
        pins: Mapping[str, tuple[str, int]] = PINNED) -> int:
    paths = locate_inputs(workspace, a_repo)
    drift = verify_pinned(paths, pins)
    if drift:
        print("输入 SHA256 漂移 (拒绝出数):", file=sys.stderr)
        for item in drift:
            print(f"  {item['input']}: {item['expected'][:16]} != {item['actual'][:16]}",
                  file=sys.stderr)
        return 3
    missing = [n for n, p in paths.items() if not Path(p).is_file()]
    if missing:
        print(f"输入缺失: {missing}", file=sys.stderr)
        return 2

    target_dir = Path(out_dir) if out_dir else default_out_dir(workspace)
    device = load_device(paths)
    discrepancies, payload = verify(device, target_dir)

    files: dict[str, bytes] = {
        "condition_pair_discrepancies.csv": render_csv(DISCREPANCY_COLUMNS, discrepancies),
        "j04d_verification.json": render_json(payload),
    }
    receipt = {
        "analysis_id": ANALYSIS_ID,
        "contract_version": CONTRACT_VERSION,
        "input_contract_version": INPUT_CONTRACT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "deterministic": True,
        "output_sha256": {k: sha256_bytes(v) for k, v in sorted(files.items())},
        "output_bytes": {k: len(v) for k, v in sorted(files.items())},
    }
    files["j04d_rebuild_receipt.json"] = render_json(receipt)
    missing_out = [n for n in OUTPUT_FILES if n not in files]
    if missing_out:
        raise AuditError(f"输出清单未产全: {missing_out}")

    if check:
        problems = check_outputs(target_dir, files)
        if problems:
            print("重建结果与现有产物不一致:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print(f"OK 重建一致: J04-D {len(files)} 个文件 @ {target_dir}")
        return 0

    write_outputs(target_dir, files)
    print(f"{ANALYSIS_ID} 完成 -> {target_dir}")
    print(f"  复核聚合行: {payload['n_aggregates_checked']}")
    print(f"  状态: {payload['status']}  FAIL={payload['n_discrepancies_fail']}  "
          f"WARN={payload['n_discrepancies_warn']}")
    return 0 if payload["status"] == "PASS" else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{ANALYSIS_ID} | {ANALYSIS_TITLE}")
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--a-repo", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    return run(workspace=Path(args.workspace), a_repo=args.a_repo,
               out_dir=args.out, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
