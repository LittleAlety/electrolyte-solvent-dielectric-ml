r"""独立核验 viscosity_v02：把 probes/build_viscosity_v02.py 的离线重算再跑一遍，逐项比对磁盘产物。

两条核查层（与预注册 reproducibility.check_tiers 对应）：
  tier 1（任何机器，零网络）：目录层用已提交 summary 的清单、数值层用已提交的
    data/viscosity_v02.csv 与 data/processed/viscosity_v02_raw.csv，重算 summary / report / 两个 CSV，
    要求逐字节一致。
  tier 2（本机有 data/external/thermoml_api/ 与 data/raw/thermoml_viscosity_pa_s/ 原始缓存时）：
    从原始响应/原始 XML 字节重算目录层与数值层，并把结果钉在原始字节上。

用法：
    .\.venv\Scripts\python.exe scripts/verify_viscosity_v02.py --check
输出：一行 JSON（passed / checks），退出码 0 表示全部通过。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.build_viscosity_v02 import (
    DEFAULT_CATALOG_CACHE,
    DEFAULT_DENSITY,
    DEFAULT_LOCAL_COVERAGE,
    DEFAULT_LOCAL_OBS,
    DEFAULT_PREREG,
    DEFAULT_RAW,
    DEFAULT_REPORT,
    DEFAULT_SUMMARY,
    DEFAULT_TABLE,
    DEFAULT_XML_CACHE,
    RAW_COLUMNS,
    TABLE_COLUMNS,
    compose,
    csv_text,
    guard_violations,
    read_text_raw,
    sha256_file,
    stable_view,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="独立核验 viscosity_v02。")
    parser.add_argument("--check", action="store_true", help="离线重算并逐字节比对（唯一模式）")
    parser.add_argument("--prereg", type=Path, default=DEFAULT_PREREG)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--catalog-cache", type=Path, default=DEFAULT_CATALOG_CACHE)
    parser.add_argument("--xml-cache", type=Path, default=DEFAULT_XML_CACHE)
    parser.add_argument("--density", type=Path, default=DEFAULT_DENSITY)
    parser.add_argument("--local-obs", type=Path, default=DEFAULT_LOCAL_OBS)
    parser.add_argument("--local-coverage", type=Path, default=DEFAULT_LOCAL_COVERAGE)
    return parser


def verify(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    if not args.summary.is_file():
        record("summary_exists", False, f"缺 summary：{args.summary}")
        return {"passed": False, "checks": checks}

    disk = json.loads(args.summary.read_text(encoding="utf-8"))
    prereg = json.loads(args.prereg.read_text(encoding="utf-8"))
    record(
        "prereg_sha256_pinned",
        sha256_file(args.prereg) == disk["prereg"]["sha256"],
        "预注册 sha256 与 summary 记录一致",
    )
    record(
        "prereg_locked_before_run",
        prereg["status"] == "locked_before_run" and prereg["locked_at_utc"].endswith("Z"),
        "预注册在跑前冻结",
    )

    summary, report, table_rows, raw_rows = compose(
        args,
        online=False,
        refresh=False,
        generated_at=str(disk.get("generated_at_utc")),
    )

    record(
        "summary_matches_offline_recompute",
        stable_view(summary) == stable_view(disk),
        "summary 与离线重算的稳定字段逐字段一致",
    )
    record(
        "report_is_the_render_of_the_summary",
        args.report.is_file() and read_text_raw(args.report) == report,
        "report 等于 render_report(summary)",
    )
    record(
        "table_matches_offline_recompute",
        args.table.is_file() and read_text_raw(args.table) == csv_text(TABLE_COLUMNS, table_rows),
        "data/viscosity_v02.csv 与离线重算一致",
    )
    record(
        "raw_layer_matches_offline_recompute",
        args.raw.is_file() and read_text_raw(args.raw) == csv_text(RAW_COLUMNS, raw_rows),
        "data/processed/viscosity_v02_raw.csv 与离线重算一致",
    )
    record(
        "no_cr_bytes_in_text_artifacts",
        all(
            b"\r" not in path.read_bytes()
            for path in (args.prereg, args.summary, args.report, args.table, args.raw)
            if path.is_file()
        ),
        "prereg/summary/report/两个 CSV 均为 LF",
    )
    record(
        "frozen_viscosity_v01_untouched",
        sha256_file(REPOSITORY_ROOT / "data" / "viscosity_v01.csv")
        == "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26",
        "data/viscosity_v01.csv digest 仍为 12dfa03f…（冻结件未被改动）",
    )
    violations = guard_violations(prereg, report, summary)
    record(
        "wording_guard",
        not violations,
        "口径守卫：" + ("通过" if not violations else str(violations[:3])),
    )

    criterion_a = summary["criterion_a_online_slice"]
    criterion_b = summary["criterion_b_local_subset"]
    criterion_c = summary["criterion_c_unit_honesty"]
    criterion_d = summary["criterion_d_basis_honesty"]
    unfreeze = summary["criterion_c_unfreeze"]
    reconcile = summary["criterion_e_row_reconciliation"]
    audit = summary["group_overlap_audit"]
    record("criterion_a", criterion_a["passed"], f"违反 {criterion_a['n_violations']}")
    record("criterion_b", criterion_b["passed"], f"违反 {criterion_b['n_violations']}")
    record("criterion_c", criterion_c["passed"], f"违反 {criterion_c['n_violations']}")
    record("criterion_d", criterion_d["passed"], f"违反 {criterion_d['n_violations']}")
    record(
        "row_reconciliation_complete",
        reconcile["unmatched_local_rows"] == 0,
        f"本地 Pa*s 行 {reconcile['local_rows']} 行全部命中在线收割",
    )
    record(
        "unfreeze_reported",
        unfreeze["nearest_rows"] == unfreeze["converted_rows"] == unfreeze["local_rows"],
        f"本地运动黏度 {unfreeze['local_rows']} 行全部反解（入主表 {unfreeze['pooled_rows']}）",
    )
    record(
        "group_overlap_zero",
        audit["max_group_overlap"] == 0 and audit["assertion_passed"] is True,
        f"GroupKFold by InChIKey max_group_overlap = {audit['max_group_overlap']}",
    )

    return {
        "passed": all(check["passed"] for check in checks),
        "value_layer_source": summary["run_provenance"]["value_layer_source"],
        "catalog_source": summary["run_provenance"]["cache"]["dataset_source"],
        "unfreeze_rows": unfreeze["nearest_rows"],
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = verify(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
