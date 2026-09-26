r"""独立核验 four_core_key_registry：把 probes/build_four_core_registry.py 的离线重算再跑一遍，
并用**另一条代码路径**（不经 compose 的建表函数，直接从源表重算）核对几处关键读数。

核验层（零网络，全部输入都是仓内已提交文件）：
  1. 预注册 sha256 与 locked_before_run；
  2. 五个源表**重新哈希**后与 summary / 预注册逐位一致；
  3. summary / report / 注册表 CSV 与离线重算逐字节一致；
  4. 每通道键数、四通道全齐的三种口径、Kirkwood-Frohlich 相关系数，用独立公式重算并比对；
  5. 三件产物字节里没有 CR；口径守卫（无性能断言用词、带齐描述性与非判决标注）。

用法：
    .\.venv\Scripts\python.exe scripts/verify_four_core_registry.py --check
输出：一行 JSON（passed / checks），退出码 0 表示全部通过。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.build_four_core_registry import (
    CHANNEL_SPECS,
    DEFAULT_PREREG,
    DEFAULT_REPORT,
    DEFAULT_SUMMARY,
    DEFAULT_TABLE,
    TABLE_COLUMNS,
    ChannelSpec,
    InputDriftError,
    compose,
    csv_text,
    guard_violations,
    kirkwood_factor,
    read_text_raw,
    sha256_of,
    stable_view,
)

LIQUID_WINDOW_TABLE = "data/processed/liquid_window_features.csv"


def sha256_streamed(path: Path) -> str:
    """独立于 build 侧的 sha256_of：分块读取，避免一次性把大表读进内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_table(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def numeric(text: Any) -> float | None:
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def keys_with_numeric(spec: ChannelSpec) -> set[str]:
    """只按「某个取值列里至少有一个有限数值」定义通道键集，独立于 build 侧的分组逻辑。"""
    keys: set[str] = set()
    for row in read_table(REPOSITORY_ROOT / spec.source):
        key = (row.get("inchikey") or "").strip()
        if not key:
            continue
        if any(numeric(row.get(column)) is not None for column in spec.value_columns):
            keys.add(key)
    return keys


def table_key_set(path: Path) -> set[str]:
    return {
        (row.get("inchikey") or "").strip()
        for row in read_table(path)
        if (row.get("inchikey") or "").strip()
    }


def pearson_sum_form(xs: list[float], ys: list[float]) -> float | None:
    """和式公式（与 build 侧的均值中心化公式数值路径不同，用于交叉验证）。"""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xx = sum(value * value for value in xs)
    sum_yy = sum(value * value for value in ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys, strict=True))
    denominator = math.sqrt((n * sum_xx - sum_x * sum_x) * (n * sum_yy - sum_y * sum_y))
    if denominator <= 0.0:
        return None
    return (n * sum_xy - sum_x * sum_y) / denominator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="独立核验 four_core_key_registry。")
    parser.add_argument("--check", action="store_true", help="离线重算并逐字节比对（唯一模式）")
    parser.add_argument("--prereg", type=Path, default=DEFAULT_PREREG)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def verify(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    if not args.summary.is_file():
        record("summary_exists", False, "缺 summary：" + str(args.summary))
        return {"passed": False, "checks": checks}

    disk = json.loads(args.summary.read_text(encoding="utf-8"))
    prereg = json.loads(args.prereg.read_text(encoding="utf-8"))

    record(
        "prereg_sha256_pinned",
        sha256_streamed(args.prereg) == str(disk["prereg"]["sha256"]),
        "预注册 sha256 与 summary 记录一致",
    )
    record(
        "prereg_locked_before_run",
        prereg["status"] == "locked_before_run",
        "预注册在跑前冻结（status = " + str(prereg["status"]) + "）",
    )

    drifted: list[str] = []
    for item in disk["inputs"]:
        actual = sha256_streamed(REPOSITORY_ROOT / str(item["path"]))
        if actual != str(item["sha256"]) or actual != str(item["pinned_sha256"]):
            drifted.append(str(item["path"]))
    record(
        "inputs_rehashed",
        not drifted,
        "五个源表重新哈希（分块）后与 summary 与预注册三处一致"
        + ("；漂移：" + ", ".join(drifted) if drifted else ""),
    )

    try:
        summary, report, rows = compose(args, generated_at=str(disk.get("generated_at_utc")))
    except InputDriftError as error:
        record("offline_recompute", False, "离线重算被输入漂移拦下：" + str(error))
        return {"passed": False, "checks": checks}

    record(
        "summary_matches_offline_recompute",
        stable_view(summary) == stable_view(disk),
        "summary 与离线重算的稳定字段逐字段一致（generated_at_utc 除外）",
    )
    record(
        "report_is_the_render_of_the_summary",
        args.report.is_file() and read_text_raw(args.report) == report,
        "reports/four_core_registry.md 与离线重算出的报告逐字一致",
    )
    record(
        "table_matches_offline_recompute",
        args.table.is_file() and read_text_raw(args.table) == csv_text(TABLE_COLUMNS, rows),
        "data/processed/four_core_key_registry.csv 与离线重算一致",
    )

    key_sets = {spec.name: keys_with_numeric(spec) for spec in CHANNEL_SPECS}
    independent_counts = {name: len(keys) for name, keys in key_sets.items()}
    claimed_counts = {
        str(item["channel"]): int(item["contract_keys"])
        for item in disk["criterion_c_per_channel"]["readings"]
    }
    record(
        "channel_key_counts_recomputed",
        independent_counts == claimed_counts,
        "每通道键数用独立路径从源表重算："
        + json.dumps(independent_counts, ensure_ascii=False)
        + " vs summary "
        + json.dumps(claimed_counts, ensure_ascii=False),
    )

    has_true = {
        spec.name: sum(1 for row in rows if row[spec.has_column] == "true")
        for spec in CHANNEL_SPECS
    }
    record(
        "registry_has_flags_match_source",
        has_true == independent_counts,
        "注册表 has_* = true 的键数与该通道源表键数一致："
        + json.dumps(has_true, ensure_ascii=False),
    )

    table_keys = table_key_set(REPOSITORY_ROOT / LIQUID_WINDOW_TABLE)
    quartets = disk["coverage_quartets"]
    recomputed_quartets = {
        "prereg_core_four": len(
            key_sets["dielectric"]
            & key_sets["viscosity"]
            & key_sets["orbitals"]
            & key_sets["redox_label"]
        ),
        "with_liquid_window_data": len(
            key_sets["dielectric"]
            & key_sets["viscosity"]
            & key_sets["orbitals"]
            & key_sets["liquid_window"]
        ),
        "with_liquid_window_table_keys": len(
            key_sets["dielectric"] & key_sets["viscosity"] & key_sets["orbitals"] & table_keys
        ),
    }
    claimed_quartets = {name: int(quartets[name]["keys"]) for name in quartets}
    record(
        "quartet_counts_recomputed",
        recomputed_quartets == claimed_quartets,
        "四通道全齐的三种口径独立重算：" + json.dumps(recomputed_quartets, ensure_ascii=False),
    )

    reconciliation = disk["liquid_window_reconciliation"]
    record(
        "liquid_window_empty_rows_recomputed",
        int(reconciliation["table_keys"]) == len(table_keys)
        and int(reconciliation["keys_with_any_numeric"]) == len(key_sets["liquid_window"])
        and int(reconciliation["keys_with_all_four_columns_empty"])
        == len(table_keys - key_sets["liquid_window"]),
        "液相窗口表键 "
        + str(len(table_keys))
        + "、有数值 "
        + str(len(key_sets["liquid_window"]))
        + "、四列全空 "
        + str(len(table_keys - key_sets["liquid_window"])),
    )

    xs: list[float] = []
    ys: list[float] = []
    for row in rows:
        if row["has_dielectric"] != "true":
            continue
        epsilon = numeric(row["dielectric"])
        dipole_debye = numeric(row["dipole_D"])
        if epsilon is None or dipole_debye is None or epsilon <= 0.0:
            continue
        xs.append(dipole_debye * dipole_debye)
        ys.append(kirkwood_factor(epsilon))
    independent_r = pearson_sum_form(xs, ys)
    claimed_r = disk["descriptive_relation"]["pearson_kirkwood_vs_dipole_sq"]
    record(
        "kirkwood_pearson_recomputed",
        independent_r is not None
        and abs(independent_r - float(claimed_r)) < 1e-9
        and len(xs) == int(disk["descriptive_relation"]["n_pairs"]),
        "和式公式 r = "
        + repr(independent_r)
        + " vs summary "
        + repr(claimed_r)
        + "（n = "
        + str(len(xs))
        + "，容差 1e-9）",
    )

    record(
        "no_cr_bytes_in_text_artifacts",
        all(
            b"\r" not in path.read_bytes()
            for path in (args.prereg, args.summary, args.report, args.table)
            if path.is_file()
        ),
        "预注册 / summary / report / 注册表 CSV 均为 LF",
    )

    report_text = read_text_raw(args.report) if args.report.is_file() else ""
    violations = guard_violations(prereg, report_text, disk)
    record(
        "wording_guard",
        not violations,
        "口径守卫：" + ("通过" if not violations else str(violations[:3])),
    )

    criterion_keys = (
        "criterion_a_inputs",
        "criterion_b_schema",
        "criterion_c_per_channel",
        "criterion_d_no_model",
        "criterion_e_descriptive",
        "criterion_f_lf",
    )
    record(
        "criteria_a_to_f_passed",
        all(bool(disk[key]["passed"]) for key in criterion_keys) and disk["verdict"] == "PASS",
        "判据 A-F 全 PASS 且 verdict = " + str(disk["verdict"]),
    )
    criterion_d = disk["criterion_d_no_model"]
    record(
        "no_model_no_scoreboard",
        int(criterion_d["models_fitted"]) == 0
        and criterion_d["r2_reported"] is False
        and int(criterion_d["main_scoreboard_attempts"]) == 0,
        "models_fitted = 0 / r2_reported = false / 主记分牌 0 次",
    )
    record(
        "registry_sha256_available",
        len(str(sha256_of(args.table))) == 64,
        "注册表 sha256 = " + sha256_of(args.table),
    )

    return {"passed": all(check["passed"] for check in checks), "checks": checks}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = verify(args)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
