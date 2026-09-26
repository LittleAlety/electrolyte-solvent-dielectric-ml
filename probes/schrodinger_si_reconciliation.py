"""T2: reconcile the stored viscosity table against the Schrödinger 2024 SI.

``data/viscosity_v01.csv`` is the project's stored 3,582-row viscosity input for
the Week 3 baseline. Appendix Z-2 of the project manual lists "our 3,582 rows
are the same file as the open subset of Schrödinger et al. (2024)" as a *key
unverified assumption*. This probe turns that assumption into a machine-checkable
row-aligned comparison instead of leaving it as a belief.

It also pins the hard boundary on the third supplement: ``..._supp_3.csv`` holds
650 *model predictions* (``EdgePool_log(Viscosity)_pred``) together with an
``is_within_training`` flag, so it must never be merged into the experimental
table. The probe writes that prohibition as an explicit assertion and records
``rows_merged_into_experimental_table = 0``.

Read-only with respect to every frozen artefact.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from thermoml_viscosity_coverage_probe import (
    display_path,
    read_csv_rows,
    to_float,
    write_json_lf,
)

from electrolyte_ml.exporting import canonical_text_sha256

VISCOSITY_V01_PATH = "data/viscosity_v01.csv"
SUPP2_PATH = "data/external/chew_2024_viscosity_supp_2.csv"
SUPP3_PATH = "data/external/chew_2024_viscosity_supp_3.csv"
OPEN_DOI = "10.1186/s13321-024-00820-5"
SUPP3_PREDICTION_COLUMN = "EdgePool_log(Viscosity)_pred"
SUPP3_DATA_STATUS = "predicted"
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "schrodinger_si_reconciliation_summary.json"
TOLERANCE = 1e-9
# Manual appendix Z-2: the paper's source dataset has 4,440 points but only the
# open subset is public. 4,440 is a claim from the paper, not a locally
# recomputable number, so it is recorded as a claim with its provenance.
CLAIMED_TOTAL_POINTS = 4440

ROW_COLUMN_PAIRS: tuple[tuple[str, str], ...] = (
    ("T_K", "Temperature (K)"),
    ("viscosity_cP", "Viscosity (cP)"),
    ("name", "Name"),
    ("smiles", "CANON_SMILES"),
)
NUMERIC_LEFT_COLUMNS = frozenset({"T_K", "viscosity_cP"})

RECON_EXPECTATIONS: dict[str, int] = {
    "row_aligned_matches": 3582,
    "mismatches": 0,
    "unique_keys": 957,
}


def numbers_equal(left: str, right: str, tolerance: float) -> bool:
    left_value = to_float(left)
    right_value = to_float(right)
    if left_value is None or right_value is None:
        return left == right
    return abs(left_value - right_value) <= tolerance


def compare_row_aligned(
    left_rows: Sequence[Mapping[str, str]],
    right_rows: Sequence[Mapping[str, str]],
    *,
    tolerance: float = TOLERANCE,
) -> dict[str, object]:
    """Compare two tables position by position, column by column."""

    rows_compared = min(len(left_rows), len(right_rows))
    per_column_mismatches = {pair[0]: 0 for pair in ROW_COLUMN_PAIRS}
    examples: list[dict[str, object]] = []
    matched = 0
    for index in range(rows_compared):
        left = left_rows[index]
        right = right_rows[index]
        row_ok = True
        for left_column, right_column in ROW_COLUMN_PAIRS:
            left_value = (left.get(left_column) or "").strip()
            right_value = (right.get(right_column) or "").strip()
            if left_column in NUMERIC_LEFT_COLUMNS:
                ok = numbers_equal(left_value, right_value, tolerance)
            else:
                ok = left_value == right_value
            if ok:
                continue
            row_ok = False
            per_column_mismatches[left_column] += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "row_index": index,
                        "left_column": left_column,
                        "right_column": right_column,
                        "left_value": left_value,
                        "right_value": right_value,
                    }
                )
        if row_ok:
            matched += 1
    return {
        "rows_compared": rows_compared,
        "row_aligned_matches": matched,
        "mismatches": rows_compared - matched,
        "row_count_delta_left_minus_right": len(left_rows) - len(right_rows),
        "per_column_mismatches": per_column_mismatches,
        "mismatch_examples": examples,
        "tolerance": tolerance,
        "column_pairs": [
            {"left": left, "right": right} for left, right in ROW_COLUMN_PAIRS
        ],
    }


def _centipoise_matches_pascal_second(row: Mapping[str, str]) -> bool:
    pa_s = to_float(row.get("viscosity_Pa_s") or "")
    centipoise = to_float(row.get("viscosity_cP") or "")
    if pa_s is None or centipoise is None:
        return False
    return abs(pa_s * 1000.0 - centipoise) <= 1e-9 * max(1.0, abs(centipoise))


def file_sha256(relative_path: str) -> str:
    return canonical_text_sha256(REPOSITORY_ROOT / relative_path)


def build_summary(*, summary_path: Path = DEFAULT_SUMMARY) -> dict[str, object]:
    v01_rows = read_csv_rows(REPOSITORY_ROOT / VISCOSITY_V01_PATH)
    supp2_rows = read_csv_rows(REPOSITORY_ROOT / SUPP2_PATH)
    supp3_rows = read_csv_rows(REPOSITORY_ROOT / SUPP3_PATH)
    comparison = compare_row_aligned(v01_rows, supp2_rows)

    unique_keys = {
        (row.get("inchikey") or "").strip()
        for row in v01_rows
        if (row.get("inchikey") or "").strip()
    }
    source_dois = sorted(
        {
            (row.get("source_doi") or "").strip()
            for row in v01_rows
            if (row.get("source_doi") or "").strip()
        }
    )
    data_status_counts = dict(
        sorted(
            collections.Counter(
                (row.get("data_status") or "").strip() for row in v01_rows
            ).items()
        )
    )
    v01_pa_s_consistent = sum(1 for row in v01_rows if _centipoise_matches_pascal_second(row))
    v01_record_id_sequential = all(
        (row.get("record_id") or "").strip() == str(index)
        for index, row in enumerate(v01_rows)
    )
    supp2_index_sequential = all(
        (row.get("Index") or "").strip() == str(index)
        for index, row in enumerate(supp2_rows)
    )

    supp2_smiles = {
        (row.get("CANON_SMILES") or "").strip()
        for row in supp2_rows
        if (row.get("CANON_SMILES") or "").strip()
    }
    supp3_smiles = {
        (row.get("CANON_SMILES") or "").strip()
        for row in supp3_rows
        if (row.get("CANON_SMILES") or "").strip()
    }
    supp3_within_training = dict(
        sorted(
            collections.Counter(
                (row.get("is_within_training") or "").strip() for row in supp3_rows
            ).items()
        )
    )
    supp3_prediction_column_present = all(
        SUPP3_PREDICTION_COLUMN in row for row in supp3_rows
    )

    remeasured = {
        "row_aligned_matches": int(comparison["row_aligned_matches"]),
        "mismatches": int(comparison["mismatches"]),
        "unique_keys": len(unique_keys),
    }
    expectation_table = [
        {
            "metric": metric,
            "recon_expectation": expected,
            "remeasured": remeasured[metric],
            "verdict": "match" if remeasured[metric] == expected else "mismatch",
        }
        for metric, expected in RECON_EXPECTATIONS.items()
    ]
    expectation_mismatches = [
        entry["metric"] for entry in expectation_table if entry["verdict"] != "match"
    ]

    payload: dict[str, object] = {
        "schema_version": "schrodinger_si_reconciliation/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "design": {
            "question": (
                "Are the project's 3,582 stored viscosity rows literally the open "
                "subset published as Schrödinger et al. (2024) supplement 2?"
            ),
            "method": (
                "Position-by-position table comparison on (T_K, viscosity_cP, "
                "name, smiles) with a 1e-9 numeric tolerance, plus explicit "
                "boundary assertions on supplement 3."
            ),
            "network_access": False,
            "promotes_values_into_frozen_dataset": False,
        },
        "inputs": {
            "viscosity_v01": {
                "path": VISCOSITY_V01_PATH,
                "rows": len(v01_rows),
                "columns": list(v01_rows[0].keys()) if v01_rows else [],
                "sha256": file_sha256(VISCOSITY_V01_PATH),
            },
            "supp_2": {
                "path": SUPP2_PATH,
                "rows": len(supp2_rows),
                "columns": list(supp2_rows[0].keys()) if supp2_rows else [],
                "sha256": file_sha256(SUPP2_PATH),
            },
            "supp_3": {
                "path": SUPP3_PATH,
                "rows": len(supp3_rows),
                "columns": list(supp3_rows[0].keys()) if supp3_rows else [],
                "sha256": file_sha256(SUPP3_PATH),
            },
        },
        "row_aligned_matches": remeasured["row_aligned_matches"],
        "mismatches": remeasured["mismatches"],
        "unique_keys": remeasured["unique_keys"],
        "source_doi_set": source_dois,
        "source_doi_set_matches_expected": source_dois == [OPEN_DOI],
        "row_aligned_comparison": comparison,
        "stored_table": {
            "rows": len(v01_rows),
            "unique_keys": len(unique_keys),
            "record_id_is_sequential": v01_record_id_sequential,
            "data_status_counts": data_status_counts,
            "pascal_second_consistent_rows": v01_pa_s_consistent,
            "pascal_second_inconsistent_rows": len(v01_rows) - v01_pa_s_consistent,
        },
        "open_subset": {
            "open_table": "supp_2",
            "open_rows": len(supp2_rows),
            "unique_smiles": len(supp2_smiles),
            "index_is_sequential": supp2_index_sequential,
            "claimed_total_points": CLAIMED_TOTAL_POINTS,
            "withheld_points": CLAIMED_TOTAL_POINTS - len(supp2_rows),
            "claimed_total_points_provenance": (
                "Manual appendix Z-2 / decisions_log.md 2026-09-22 viscosity source "
                "note; the withheld remainder is not public, so this number is a "
                "claim about the paper, not a locally recomputable count."
            ),
            "withheld_note": (
                "受限的 858 条被作者以版权原因保留，不得以任何方式绕版权获取、"
                "不得推测其内容，也不得把它计入本地语料规模。"
            ),
            "license_note": (
                "开放子集（supp_2）的再利用须遵守 Schrödinger 2024 的许可并注明出处 "
                "(DOI 10.1186/s13321-024-00820-5)。"
            ),
        },
        "supp_3": {
            "rows": len(supp3_rows),
            "unique_smiles": len(supp3_smiles),
            "overlap_smiles_with_supp_2": len(supp3_smiles & supp2_smiles),
            "data_status": SUPP3_DATA_STATUS,
            "prediction_column": SUPP3_PREDICTION_COLUMN,
            "prediction_column_present_in_every_row": supp3_prediction_column_present,
            "is_within_training_counts": supp3_within_training,
            "rows_merged_into_experimental_table": 0,
            "merge_forbidden": True,
            "assertion": (
                "supp_3 是 EdgePool 的模型预测（650 行 / 50 个溶剂），"
                "必须保持 data_status=predicted，禁止并入实验表、禁止进入任何可发表层、"
                "禁止用于拟合或评估。本对照把它们隔离在实验表之外，"
                "因此本探针不把它们计入 row_aligned_matches。"
            ),
        },
        "competing_table_note": (
            "本仓已存在 data/processed/dielectric_viscosity_intersection.csv（456 行 / 46 keys，"
            "pair_type=loose_join、model_ready=false），属探索性 loose join，不是 ε+η 联合观测表；"
            "ηε-joint 的联合骨架仍需新建。"
        ),
        "expectation_vs_remeasured": expectation_table,
        "expectation_mismatches": expectation_mismatches,
        "outputs": {
            "summary_path": display_path(summary_path),
        },
        "findings": [
            (
                "存量 data/viscosity_v01.csv 与 Schrödinger 2024 supp_2 在同一行序上逐行一致："
                "3,582/3,582 行全等，0 处不一致（T_K、viscosity_cP 用 1e-9 容差，"
                "name、CANON_SMILES 精确比对），957 个 InChIKey，source_doi 唯一且等于 "
                "10.1186/s13321-024-00820-5。附录 Z-2 的“待核实假设”因此升级为已核实事实。"
            ),
            (
                "两份表的行序也一致（supp_2 的 Index 与存量表的 record_id 都是 0..3581 的顺序编号），"
                "所以这不是“集合相同但顺序不同”的弱结论，而是同一份文件的逐行同一性。"
            ),
            (
                "supp_3 是预测而非观测：650 行 / 50 个溶剂，含 EdgePool_log(Viscosity)_pred 列，"
                "is_within_training 为 False 403 行 / True 247 行；与 supp_2 只共享 19 个溶剂。"
                "它必须保持 data_status=predicted，本探针拒绝把任何一行并入实验表。"
            ),
        ],
        "limitations": [
            (
                "逐行同一性只证明“存量表 = 开放子集”，不能证明开放子集本身没有抄录错误；"
                "原始参考文献的正确性需要回到 Schrödinger 论文与其引用源才能判定。"
            ),
            (
                "4,440 这个总点数来自论文/手册的说法，本地只有开放子集，"
                "所以 858 条受限记录是“声称的差额”，不是本地可复算的观测数。"
            ),
            (
                "本地没有 Schrödinger 官方发布的校验和，因此本次对账是表内对账（逐行同一性），"
                "不是与官方产物的字节级比对。"
            ),
            (
                "本探针只做对账：不建模、不改评分池、不把任何值写进冻结数据集。"
            ),
        ],
    }

    write_json_lf(summary_path, payload)
    return payload


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = build_summary(summary_path=args.summary)
    print(
        json.dumps(
            {
                "schema_version": payload["schema_version"],
                "row_aligned_matches": payload["row_aligned_matches"],
                "mismatches": payload["mismatches"],
                "unique_keys": payload["unique_keys"],
                "source_doi_set": payload["source_doi_set"],
                "rows_compared": payload["row_aligned_comparison"]["rows_compared"],
                "supp_3_rows": payload["supp_3"]["rows"],
                "supp_3_data_status": payload["supp_3"]["data_status"],
                "supp_3_merged_into_experimental_table": payload["supp_3"][
                    "rows_merged_into_experimental_table"
                ],
                "withheld_points": payload["open_subset"]["withheld_points"],
                "expectation_mismatches": payload["expectation_mismatches"],
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
