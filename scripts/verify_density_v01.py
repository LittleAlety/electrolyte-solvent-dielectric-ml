r"""独立核验 density_v01：把 probes/build_density_v01.py 的离线重算再跑一遍，逐项比对磁盘产物。

两条核查层（与预注册 reproducibility.check_tiers 对应）：
  tier 1（任何机器，零网络）：目录层用已提交 summary 的清单、数值层用已提交的
    data/density_v01.csv 与 data/processed/density_raw.csv，重算 summary / report / 两个 CSV，
    要求逐字节一致。
  tier 2（本机有 data/external/thermoml_api/density_kg_m3/ 与 data/raw/thermoml_density/ 原始缓存时）：
    从原始响应/原始 XML 字节重算目录层与数值层，并把结果钉在原始字节上。

用法：
    .\.venv\Scripts\python.exe scripts/verify_density_v01.py --check
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

from probes.build_density_v01 import (
    DEFAULT_CATALOG_CACHE,
    DEFAULT_DIELECTRIC,
    DEFAULT_IDENTITY_MAP,
    DEFAULT_KINEMATIC,
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
    parser = argparse.ArgumentParser(description="独立核验 density_v01。")
    parser.add_argument("--check", action="store_true", help="离线重算并逐字节比对（唯一模式）")
    parser.add_argument("--prereg", type=Path, default=DEFAULT_PREREG)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--catalog-cache", type=Path, default=DEFAULT_CATALOG_CACHE)
    parser.add_argument("--xml-cache", type=Path, default=DEFAULT_XML_CACHE)
    parser.add_argument("--dielectric", type=Path, default=DEFAULT_DIELECTRIC)
    parser.add_argument("--identity-map", type=Path, default=DEFAULT_IDENTITY_MAP)
    parser.add_argument("--kinematic", type=Path, default=DEFAULT_KINEMATIC)
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
        "data/density_v01.csv 与离线重算一致",
    )
    record(
        "raw_layer_matches_offline_recompute",
        args.raw.is_file() and read_text_raw(args.raw) == csv_text(RAW_COLUMNS, raw_rows),
        "data/processed/density_raw.csv 与离线重算一致",
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
    violations = guard_violations(prereg, report, summary)
    record("wording_guard", not violations, "口径守卫：" + ("通过" if not violations else str(violations[:3])))

    criterion_a = summary["criterion_a_catalog"]
    criterion_b = summary["criterion_b_values"]
    criterion_c = summary["criterion_c_unfreeze"]
    criterion_d = summary["criterion_d_honesty"]
    record("criterion_a", criterion_a["passed"], f"违反 {criterion_a['n_violations']}")
    record("criterion_b", criterion_b["passed"], f"违反 {criterion_b['n_violations']}")
    record("criterion_c", criterion_c["passed"], f"违反 {criterion_c['n_violations']}")
    record("criterion_d", criterion_d["passed"], f"违反 {criterion_d['n_violations']}")

    return {
        "passed": all(check["passed"] for check in checks),
        "value_layer_source": summary["run_provenance"]["value_layer_source"],
        "catalog_source": summary["run_provenance"]["cache"]["dataset_source"],
        "unfreeze_rows": criterion_c["unfreeze_rows"],
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = verify(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
