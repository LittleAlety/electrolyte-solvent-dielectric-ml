from __future__ import annotations

import numpy as np

import probes.dielectric_ranking_head_probe as probe
from probes.dielectric_representation_ablation import read_modelling_rows
from probes.dielectric_target_and_scaffold import scaffold_group_keys


def test_frozen_primary_qid_counts_and_pair_capacity() -> None:
    rows, failed, withheld = read_modelling_rows(probe.FEATURES_PATH)
    qids = scaffold_group_keys([row["smiles"] for row in rows])

    assert len(rows) == 234
    assert len(failed) == 4
    assert len(withheld) == 1
    assert probe.qid_summary(qids) == {
        "qid_count": 111,
        "singleton_count": 76,
        "total_pair_capacity": 799,
    }


def test_group_splits_keep_each_qid_whole_and_cover_each_row_once() -> None:
    qid_values = [
        f"q{index}" for index in range(10) for _ in range(index % 3 + 1)
    ]

    splits = probe.build_group_splits(
        qid_values,
        n_splits=5,
        n_repeats=2,
        seed=42,
    )

    assert len(splits) == 10
    for split in splits:
        assert set(split.train_qids).isdisjoint(split.test_qids)
        test_qids = [qid_values[index] for index in split.test_indices]
        assert set(test_qids) == set(split.test_qids)
    for repeat in range(2):
        test_indices = np.concatenate(
            [split.test_indices for split in splits if split.repeat == repeat]
        )
        assert sorted(test_indices.tolist()) == list(range(len(qid_values)))


def test_both_heads_receive_identical_outer_indices(monkeypatch) -> None:
    calls: list[tuple[str, list[int], list[int], int]] = []

    def fake_regression(features, target, *, train_indices, test_indices, seed):
        calls.append(
            ("regression", train_indices.tolist(), test_indices.tolist(), seed)
        )
        return np.asarray([1.0, 2.0])

    def fake_rank(
        features,
        target,
        qid_codes,
        inchikeys,
        *,
        train_indices,
        test_indices,
        seed,
    ):
        calls.append(("rank", train_indices.tolist(), test_indices.tolist(), seed))
        return np.asarray([0.5, 1.5])

    monkeypatch.setattr(probe, "fit_regression_head", fake_regression)
    monkeypatch.setattr(probe, "fit_rank_pairwise_head", fake_rank)

    regression, rank = probe.fit_outer_heads(
        np.zeros((4, 2)),
        np.asarray([1.0, 2.0, 3.0, 4.0]),
        np.asarray([0, 0, 1, 1]),
        np.asarray(["a", "b", "c", "d"]),
        train_indices=np.asarray([0, 1]),
        test_indices=np.asarray([2, 3]),
        seed=77,
    )

    assert regression.tolist() == [1.0, 2.0]
    assert rank.tolist() == [0.5, 1.5]
    assert calls == [
        ("regression", [0, 1], [2, 3], 77),
        ("rank", [0, 1], [2, 3], 77),
    ]


def test_pairwise_accuracy_handles_reversals_and_predicted_ties() -> None:
    assert probe._pairwise_accuracy(
        np.asarray([1.0, 2.0, 3.0]),
        np.asarray([1.0, 2.0, 3.0]),
    ) == (3, 1.0)
    assert probe._pairwise_accuracy(
        np.asarray([1.0, 2.0, 3.0]),
        np.asarray([3.0, 2.0, 1.0]),
    ) == (3, 0.0)
    assert probe._pairwise_accuracy(
        np.asarray([1.0, 2.0]),
        np.asarray([5.0, 5.0]),
    ) == (1, 0.5)


def test_pairwise_accuracy_excludes_target_ties_and_macro_weights_queries() -> None:
    pair_count, accuracy = probe._pairwise_accuracy(
        np.asarray([1.0, 1.0, 2.0]),
        np.asarray([9.0, 0.0, 1.0]),
    )
    assert pair_count == 2
    assert accuracy == 0.5

    total_pairs, micro, macro = probe._pairwise_metrics(
        np.asarray([1.0, 2.0, 3.0, 1.0, 2.0]),
        np.asarray([1.0, 2.0, 3.0, 2.0, 1.0]),
        ["large", "large", "large", "small", "small"],
    )
    assert total_pairs == 4
    assert micro == 0.75
    assert macro == 0.5


def test_metric_boundaries_for_single_query_and_no_threshold_positive() -> None:
    single = probe.ranking_metrics(
        target=[2.0],
        raw_score=[1.0],
        group_values=["only"],
        calibrated_epsilon=[1.5],
    )
    assert single["n_comparable_pairs"] == 0
    assert np.isnan(single["macro_pairwise_accuracy"])
    assert np.isnan(single["global_spearman"])
    assert single["calibrated_mae"] == 0.5

    metrics = probe.ranking_metrics(
        target=[1.0, 2.0, 3.0],
        raw_score=[1.0, 2.0, 3.0],
        group_values=["q", "q", "q"],
        calibrated_epsilon=[1.0, 2.0, 3.0],
    )
    assert metrics["global_spearman"] == 1.0
    assert metrics["macro_pairwise_accuracy"] == 1.0
    assert np.isnan(metrics["auc_gt15"])
    assert np.isnan(metrics["auc_gt30"])
    assert metrics["calibrated_mae"] == 0.0


def test_rank_params_declare_pairwise_objective() -> None:
    assert probe.RANK_PARAMS["objective"] == "rank:pairwise"
    assert probe.RANK_PARAMS["lambdarank_pair_method"] == "mean"
