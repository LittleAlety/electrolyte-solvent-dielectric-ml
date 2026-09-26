"""Week 15 执行员 C：epsilon hybrid 的逐折训练侧 SHAP 排序产物守卫。

本探针存在的原因：AB-6 的最优特征位次是用「列随机置换重要度」测出来的，而
那份表被查出有标签缺陷（洗的是 23 列矩阵的前 10 列，却挂着知识池成员的名字）。
这些测试钉住四件一旦悄悄坏掉就会误导阅读的事——冻结 R2 没有复现、折派发漂移、
某次排序看见了测试折的行、报告与摘要不再逐字节一致——外加 LF-only、脚本摘要
与两条独立重要度口径的对照读数。
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256, sha256_file
from probes.dielectric_hybrid_shap import (
    AB6_TOP_THREE,
    AGREEMENT_CONSISTENT,
    AGREEMENT_PARTIAL,
    ARM_HYBRID,
    ARM_KNOWLEDGE,
    ARM_PERMUTATION,
    COVERAGE_TABLE_SHA256,
    FROZEN_V03_PATH,
    FROZEN_V03_SHA256,
    HONEST_BOUNDARIES,
    HYBRID_MIXING_WEIGHT,
    IMPORTANCE_IMPL,
    NOT_CLAIMED,
    PHYSICAL_COLUMNS,
    REFERENCE_R2,
    REFERENCE_TOLERANCE,
    SHAP_RELATIVE_TOLERANCE,
    SUMMARY_PATH,
    TASK_ID,
    RankingLeakError,
    ShapAdditivityError,
    assert_shap_ranking_scope,
    feature_column_order_sha256,
    hybrid_feature_names,
    knowledge_feature_names,
    leaky_shap_scope,
    render_report,
    shap_contributions,
)
from probes.dielectric_knowledge_purity_sweep import KNOWLEDGE_POOL
from probes.dielectric_representation_ablation import FP_SIZE, N_REPEATS, N_SPLITS, SEED, XGB_PARAMS
from probes.dielectric_representation_ablation import (
    PHYSICAL_COLUMNS as ABLATION_PHYSICAL_COLUMNS,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "probes" / "dielectric_hybrid_shap.py"
IMPORTANCE_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "dielectric_hybrid_shap_importance.csv"
STABILITY_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "dielectric_hybrid_shap_rank_stability.csv"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_hybrid_shap.md"
LEVER9_IMPORTANCE_PATH = (
    REPOSITORY_ROOT / "probes" / "artifacts" / "dielectric_knowledge_purity_sweep_importance.csv"
)
FOLD_COUNT = N_SPLITS * N_REPEATS
HYBRID_FEATURE_COUNT = FP_SIZE + len(PHYSICAL_COLUMNS)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _raw(path: Path) -> bytes:
    return path.read_bytes()


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def importance_rows() -> list[dict[str, str]]:
    return _rows(IMPORTANCE_PATH)


@pytest.fixture(scope="module")
def stability_rows() -> list[dict[str, str]]:
    return _rows(STABILITY_PATH)


def test_task_identity_and_the_frozen_inputs_are_untouched(summary):
    assert summary["task"] == TASK_ID == "week15_modelling_hybrid_shap"
    assert summary["schema_version"] == 1
    assert sha256_file(FROZEN_V03_PATH) == FROZEN_V03_SHA256
    assert sha256_file(REPOSITORY_ROOT / summary["inputs"]["coverage_table"]) == COVERAGE_TABLE_SHA256
    assert summary["inputs"]["frozen_dataset_verified"] is True
    assert summary["inputs"]["coverage_table_verified"] is True


def test_the_summary_was_written_by_the_script_that_is_on_disk(summary):
    assert summary["inputs"]["script_sha256"] == canonical_text_sha256(SCRIPT_PATH)
    assert summary["inputs"]["lever9_reference_summary_sha256"] == canonical_text_sha256(
        REPOSITORY_ROOT / summary["inputs"]["lever9_reference_summary"]
    )
    assert summary["inputs"]["lever9_reference_importance_sha256"] == sha256_file(
        LEVER9_IMPORTANCE_PATH
    )


def test_seed_folds_and_importance_implementation_are_pinned(summary):
    assert summary["seed"] == SEED == 42
    assert summary["repeats"] == N_REPEATS == 10
    assert summary["repeats_requested"] == 10
    assert summary["folds"] == N_SPLITS == 5
    assert summary["repeats_x_folds"] == FOLD_COUNT == 50
    assert summary["importance_impl"] == IMPORTANCE_IMPL == "xgboost_pred_contribs"
    assert "shap" not in IMPORTANCE_IMPL
    assert summary["leak_guard"]["folds_checked"] == FOLD_COUNT * 3
    assert summary["arms"][ARM_HYBRID]["fits"] == FOLD_COUNT * 2
    assert summary["arms"][ARM_KNOWLEDGE]["fits"] == FOLD_COUNT


def test_the_fold_dealing_is_the_frozen_main_scoreboard(summary):
    deal = summary["fold_deal"]
    assert deal["splits"] == FOLD_COUNT
    assert deal["executed_repeats"] == N_REPEATS
    assert deal["seed"] == SEED
    assert deal["reproduced_by_a_second_deal"] is True
    assert deal["signature_sha256"] == (
        "864b3a531e404d49c3399bae1426c49abce79f1fab812f5ae8ed15f676bb86be"
    )
    assert deal["signature_sha256"] == summary["comparison_to_ab6"]["reference"][
        "fold_deal_signature_sha256"
    ]
    assert len(deal["per_fold"]) == FOLD_COUNT
    assert {(row["repeat"], row["fold"]) for row in deal["per_fold"]} == {
        (repeat, fold) for repeat in range(N_REPEATS) for fold in range(N_SPLITS)
    }
    for row in deal["per_fold"]:
        assert row["test_rows"] >= 2
        assert row["train_rows"] + row["test_rows"] == summary["inputs"]["scored_rows"]


def test_the_baseline_reproduces_to_the_frozen_tolerance(summary):
    baseline = summary["baseline_reproduces"]
    assert baseline["reference_r2"] == REFERENCE_R2
    assert baseline["tolerance"] == REFERENCE_TOLERANCE
    assert baseline["abs_difference"] <= REFERENCE_TOLERANCE
    assert baseline["verified"] is True
    assert summary["readings"]["Morgan+Physical"]["r2"]["mean"] == pytest.approx(
        REFERENCE_R2, abs=REFERENCE_TOLERANCE
    )
    faithful = summary["fold_fit_matches_the_frozen_function"]
    assert faithful["identical"] is True
    assert faithful["folds_compared"] == FOLD_COUNT
    assert faithful["max_abs_difference"] == 0.0


# --------------------------------------------------------------------------- #
# 泄漏守卫
# --------------------------------------------------------------------------- #


def test_no_test_row_ever_entered_a_ranking(summary, importance_rows):
    assert summary["test_rows_visible_to_ranking"] == 0
    guard = summary["leak_guard"]
    assert guard["name"] == "assert_shap_ranking_scope"
    assert guard["inherits"] == "probes.dielectric_knowledge_purity_sweep.assert_ranking_scope"
    assert guard["error_type"] == RankingLeakError.__name__
    assert guard["runs_in_every_fold"] is True
    assert guard["test_rows_visible_to_ranking"] == 0
    assert guard["max_test_rows_visible_to_ranking"] == 0
    assert len(guard["records"]) == FOLD_COUNT * 3
    assert len(summary["permutation_reference"]["guard_records"]) == FOLD_COUNT
    assert {(row["repeat"], row["fold"]) for row in guard["records"]} == {
        (repeat, fold) for repeat in range(N_REPEATS) for fold in range(N_SPLITS)
    }
    for row in guard["records"]:
        assert row["test_rows_visible_to_ranking"] == 0
        assert row["ranking_rows"] > 0
        assert row["ranking_compounds"] > 0
    assert {row["test_rows_visible_to_ranking"] for row in importance_rows} == {"0"}


def test_the_ranked_scope_is_exactly_the_training_fold(summary, importance_rows):
    per_fold = {(row["repeat"], row["fold"]): row for row in summary["fold_deal"]["per_fold"]}
    seen: set[tuple[str, int, int]] = set()
    for row in importance_rows:
        key = (row["arm"], int(row["repeat"]), int(row["fold"]))
        if key in seen:
            continue
        seen.add(key)
        deal = per_fold[(int(row["repeat"]), int(row["fold"]))]
        assert int(row["ranking_rows"]) == deal["train_rows"], key
        assert int(row["ranking_compounds"]) == deal["train_compounds"], key
    assert len(seen) == FOLD_COUNT * 2


def test_the_guard_accepts_the_training_fold_and_fires_on_the_forbidden_scope():
    train = [0, 1, 2, 3]
    test = [4, 5]
    groups = ["a", "a", "b", "b", "c", "c"]
    record = assert_shap_ranking_scope(
        importance_rows=train, train_index=train, test_index=test, groups=groups, context="unit"
    )
    assert record == {"ranking_rows": 4, "ranking_compounds": 2, "test_rows_visible_to_ranking": 0}

    with pytest.raises(RankingLeakError):
        assert_shap_ranking_scope(
            importance_rows=leaky_shap_scope(train, test),
            train_index=train,
            test_index=test,
            groups=groups,
            context="unit",
        )
    with pytest.raises(RankingLeakError):
        assert_shap_ranking_scope(
            importance_rows=[1, 2],
            train_index=train,
            test_index=test,
            groups=groups,
            context="unit",
        )


def test_the_group_clause_fires_when_a_compound_is_shared():
    groups = ["a", "b", "c", "d", "a", "b"]
    train = [0, 1, 2, 3]
    with pytest.raises(RankingLeakError):
        assert_shap_ranking_scope(
            importance_rows=train,
            train_index=train,
            test_index=[4, 5],
            groups=groups,
            context="unit",
        )


# --------------------------------------------------------------------------- #
# 特征列序
# --------------------------------------------------------------------------- #


def test_hybrid_columns_are_morgan_bits_then_the_physical_block(summary):
    names = hybrid_feature_names()
    assert len(names) == HYBRID_FEATURE_COUNT == 2061
    assert names[:FP_SIZE] == tuple(f"morgan_bit_{index:04d}" for index in range(FP_SIZE))
    assert names[FP_SIZE:] == tuple(PHYSICAL_COLUMNS)
    assert tuple(PHYSICAL_COLUMNS) == tuple(ABLATION_PHYSICAL_COLUMNS)
    assert "T_K" in PHYSICAL_COLUMNS
    assert summary["feature_count"] == 2061
    assert summary["feature_columns"]["hybrid"] == list(names)
    assert summary["feature_column_order_sha256"] == feature_column_order_sha256(names)
    assert summary["knowledge_feature_count"] == 10
    assert summary["feature_columns"]["knowledge"] == list(KNOWLEDGE_POOL)
    assert summary["knowledge_column_order_sha256"] == feature_column_order_sha256(
        knowledge_feature_names()
    )


def test_the_hybrid_is_a_weighted_model_average_not_a_concatenation(summary):
    assert HYBRID_MIXING_WEIGHT == 0.5
    role = summary["arms"][ARM_HYBRID]["role"]
    assert "0.5" in role
    assert summary["clipped_test_predictions"] == 0
    assert summary["arms"][ARM_HYBRID]["feature_columns"] == 2061
    assert sorted(summary["arms"]) == sorted([ARM_HYBRID, ARM_KNOWLEDGE, ARM_PERMUTATION])


# --------------------------------------------------------------------------- #
# 重要度读数（每折训练侧内部）
# --------------------------------------------------------------------------- #


def test_every_fold_ranks_every_column_exactly_once(summary, importance_rows):
    counts: dict[tuple[str, int, int], list[int]] = {}
    for row in importance_rows:
        key = (row["arm"], int(row["repeat"]), int(row["fold"]))
        counts.setdefault(key, []).append(int(row["rank"]))
    expected = ((ARM_HYBRID, 2061), (ARM_KNOWLEDGE, 10))
    assert {key[0] for key in counts} == {arm for arm, _ in expected}
    for arm, size in expected:
        keys = [key for key in counts if key[0] == arm]
        assert len(keys) == FOLD_COUNT
        for key in keys:
            assert sorted(counts[key]) == list(range(1, size + 1)), key
    assert len(importance_rows) == FOLD_COUNT * 2061 + FOLD_COUNT * 10
    permutation = summary["permutation_reference"]
    assert permutation["arm"] == ARM_PERMUTATION
    assert permutation["shuffles"] == 3
    assert [list(entry) for entry in permutation["fold_order"]] == [
        [repeat, fold] for repeat in range(N_REPEATS) for fold in range(N_SPLITS)
    ]


def test_top_flags_match_the_rank_and_the_fold_feature_count(importance_rows):
    for row in importance_rows:
        rank = int(row["rank"])
        assert int(row["ranked_in_top_3"]) == int(rank <= 3)
        assert int(row["ranked_in_top_10"]) == int(rank <= 10)
        assert int(row["fold_feature_count"]) == (2061 if row["arm"] == ARM_HYBRID else 10)
        assert float(row["shap_additivity_rel_residual"]) <= SHAP_RELATIVE_TOLERANCE
        assert float(row["importance_mean_abs"]) >= 0.0
        assert float(row["importance_share"]) >= 0.0


def test_the_stability_csv_is_the_other_side_of_the_same_run(summary, stability_rows):
    assert len(stability_rows) == 2061 + 10
    for arm, size in ((ARM_HYBRID, 2061), (ARM_KNOWLEDGE, 10)):
        block = [row for row in stability_rows if row["arm"] == arm]
        assert len(block) == size
        expected_name = hybrid_feature_names() if arm == ARM_HYBRID else knowledge_feature_names()
        assert {row["feature"] for row in block} == set(expected_name)
        for row in block:
            assert int(row["folds_ranked"]) == FOLD_COUNT
            assert int(row["repeats"]) == N_REPEATS
            assert int(row["top_3_folds"]) <= int(row["top_10_folds"]) <= int(row["top_20_folds"])
            assert float(row["top_10_hit_rate"]) == pytest.approx(int(row["top_10_folds"]) / 50)
    overview = summary["rank_stability"][ARM_HYBRID]
    assert overview["features"] == 2061
    assert overview["folds_per_feature"] == FOLD_COUNT
    assert overview["stable_features"] + overview["unstable_features"] == 2061
    assert overview["features_never_used_by_any_tree"] == 1880


def test_top10_tables_are_ordered_by_mean_importance(summary):
    top10 = summary["top10_features"]
    assert [row["rank"] for row in top10] == list(range(1, 11))
    assert [row["feature"] for row in top10] == summary["comparison_to_ab6"]["hybrid_side"]["top_10"]
    imports = [float(row["mean_importance"]) for row in top10]
    assert imports == sorted(imports, reverse=True)
    assert top10[0]["feature"] == "mu_sq_over_Vm"
    assert top10[0]["feature_kind"] == "physical"
    knowledge = summary["knowledge_top10"]
    assert [row["feature"] for row in knowledge] == [
        str(row["feature"])
        for row in sorted(knowledge, key=lambda entry: -float(entry["mean_importance"]))
    ]
    assert knowledge[0]["feature"] == "donor_acceptor_pair_density"


def test_family_shares_are_reported(summary):
    totals = summary["kind_totals"]
    assert set(totals) == {"morgan_bit", "physical"}
    assert totals["morgan_bit"]["features"] == 2048
    assert totals["physical"]["features"] == 13
    share = (
        totals["morgan_bit"]["mean_importance_share"] + totals["physical"]["mean_importance_share"]
    )
    assert share == pytest.approx(1.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# 与附录 AB-6 的对照
# --------------------------------------------------------------------------- #


def test_ab6_comparison_readings_and_verdict(summary):
    comparison = summary["comparison_to_ab6"]
    readings = comparison["readings"]
    assert set(readings) == {
        "shap_vs_quoted_lever9",
        "shap_vs_corrected_permutation",
        "quoted_lever9_vs_corrected_permutation",
    }
    for name, block in readings.items():
        assert block["folds"] == FOLD_COUNT, name
        assert 0 <= block["exact_top_3_set_matches"] <= FOLD_COUNT, name
        assert block["exact_match_rate"] == pytest.approx(
            block["exact_top_3_set_matches"] / FOLD_COUNT
        )
        expected = (
            "consistent"
            if block["exact_match_rate"] >= AGREEMENT_CONSISTENT
            else "partially_consistent"
            if block["exact_match_rate"] >= AGREEMENT_PARTIAL
            else "inconsistent"
        )
        assert block["verdict"] == expected, name
    assert comparison["verdict"] == readings["shap_vs_quoted_lever9"]["verdict"]
    assert (
        summary["verdict"]["ab6_agreement_vs_quoted_lever9"]
        == readings["shap_vs_quoted_lever9"]["verdict"]
    )
    comparability = comparison["feature_level_comparability"]
    assert comparability["ab6_top_three_is_inside_the_hybrid_feature_space"] is False
    assert tuple(comparability["ab6_top_three"]) == AB6_TOP_THREE


def test_the_quoted_lever9_table_is_reproduced_to_zero(summary):
    defect = summary["comparison_to_ab6"]["reference_defect"]
    evidence = defect["evidence"]
    replication = evidence["replication"]
    assert evidence["top_3_sets_reproduced_folds"] == FOLD_COUNT
    assert evidence["top_3_sets_compared_folds"] == FOLD_COUNT
    assert replication["verified"] is True
    assert replication["max_abs_difference_vs_stored_lever9"] == 0.0
    assert replication["ranks_identical"] == replication["cells_compared"] == 500
    assert evidence["positional_identity"]["max_abs_difference"] == 0.0
    assert evidence["positional_identity"]["verified"] is True
    assert evidence["corrected_call_differs"]["max_abs_difference"] > 0.0
    assert summary["verdict"]["reference_defect_verified"] is True


def test_the_defect_labels_point_at_the_first_ten_physical_columns(summary):
    defect = summary["comparison_to_ab6"]["reference_defect"]
    mapping = defect["label_to_column_actually_shuffled"]
    assert list(mapping) == list(KNOWLEDGE_POOL)
    assert list(mapping.values()) == list(PHYSICAL_COLUMNS)[:10]
    assert defect["id"] == "lever9_permutation_importance_shuffled_the_first_ten_columns"
    assert "前 10 列" in defect["claim"]
    assert "杠杆 9" in defect["action_required_outside_this_write_set"]


def test_ab6_top_three_statuses_and_the_secondary_criterion(summary):
    comparison = summary["comparison_to_ab6"]
    statuses = comparison["top_three_status"]
    assert set(statuses) == set(AB6_TOP_THREE)
    for member, block in statuses.items():
        assert block["status"] in {"reproduced", "weakened", "lost"}, member
        assert 0 <= block["shap_top_3_folds"] <= FOLD_COUNT
        assert 0 <= block["corrected_permutation_top_3_folds"] <= FOLD_COUNT
        assert 0 <= block["quoted_lever9_top_3_folds"] <= FOLD_COUNT
    assert statuses["donor_acceptor_pair_density"]["status"] == "reproduced"
    assert statuses["heteroatom_over_carbon"]["status"] == "weakened"
    assert statuses["ring_count"]["status"] == "lost"
    assert statuses["ring_count"]["shap_top_3_folds"] == 0
    counts = comparison["counts_rank_last"]
    assert counts["rule"]
    assert set(counts["members"]) == {"donor_count", "acceptor_count"}
    assert any(holds is False for holds in counts["holds"].values())
    for member, block in comparison["per_member"].items():
        assert block["column_actually_shuffled_behind_the_quoted_label"] in PHYSICAL_COLUMNS, member


# --------------------------------------------------------------------------- #
# SHAP 加性校验
# --------------------------------------------------------------------------- #


def test_additivity_residuals_are_relative_and_within_tolerance(summary):
    additivity = summary["shap_additivity"]
    assert additivity["tolerance"] == SHAP_RELATIVE_TOLERANCE == 1e-5
    assert additivity["fits_checked"] == FOLD_COUNT * 3
    assert additivity["verified"] is True
    assert additivity["max_relative_residual_hybrid_arm"] <= SHAP_RELATIVE_TOLERANCE
    assert additivity["max_relative_residual_knowledge_arm"] <= SHAP_RELATIVE_TOLERANCE
    assert additivity["max_absolute_residual_hybrid_arm"] > 1e-9
    assert "max(|margin|, 1)" in additivity["residual_definition"]


def test_shap_contributions_drop_the_bias_column_and_check_the_rebuild():
    rng = np.random.default_rng(SEED)
    features = rng.normal(size=(24, 5))
    target = features @ np.array([1.0, -2.0, 0.5, 0.0, 3.0]) + rng.normal(scale=0.1, size=24)
    model = XGBRegressor(**XGB_PARAMS, random_state=SEED)
    model.fit(features, target)
    contributions, info = shap_contributions(model, features, list(range(6)))
    assert contributions.shape == (6, 5)
    assert info["max_relative_residual"] <= SHAP_RELATIVE_TOLERANCE
    assert info["tolerance"] == SHAP_RELATIVE_TOLERANCE
    with pytest.raises(ShapAdditivityError):
        shap_contributions(model, features, list(range(6)), tolerance=-1.0)
    with pytest.raises(ValueError):
        shap_contributions(model, features, [])


# --------------------------------------------------------------------------- #
# 诚实边界与产物卫生
# --------------------------------------------------------------------------- #


def test_honest_boundaries_and_not_claimed_are_the_module_constants(summary):
    assert list(summary["honest_boundaries"]) == list(HONEST_BOUNDARIES)
    assert list(summary["not_claimed"]) == list(NOT_CLAIMED)
    joined = "\n".join(summary["honest_boundaries"])
    assert "不是因果" in joined
    assert "单精度" in joined
    assert "0.0" in joined
    assert "不声称" in "\n".join(summary["not_claimed"])


def test_the_report_is_rendered_from_the_summary_byte_for_byte(summary):
    rendered = "\n".join(render_report(summary)) + "\n"
    assert _raw(REPORT_PATH).decode("utf-8") == rendered
    assert "## 五、边界（不许省略）" in rendered
    assert "特征重要度不是因果" in rendered
    assert "\u0060.5\u0060" not in rendered
    assert "\u00600.5\u0060" in rendered


def test_the_artifacts_are_lf_only_and_carry_no_bom():
    for path in (IMPORTANCE_PATH, STABILITY_PATH, SUMMARY_PATH, REPORT_PATH):
        raw = _raw(path)
        assert raw.startswith(b"\xef\xbb\xbf") is False, path
        assert b"\r\n" not in raw, path
        assert raw.endswith(b"\n"), path


def test_the_check_mode_recomputes_everything_and_passes():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--check"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "23/23 checks passed" in completed.stdout
    for name in (
        "no_test_row_ever_entered_a_ranking",
        "reference_defect_replication_is_zero",
        "report_matches_the_summary",
        "honest_boundaries_present",
    ):
        assert "OK   " + name in completed.stdout
