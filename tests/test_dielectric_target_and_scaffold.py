from __future__ import annotations

import numpy as np

from probes.dielectric_target_and_scaffold import (
    inverse_target,
    scaffold_folds,
    scaffold_group_keys,
    transform_target,
)


def test_log_target_transform_round_trips() -> None:
    target = np.asarray([1.1, 2.0, 10.0])
    transformed = transform_target(target, "log_epsilon_minus_one")

    restored = inverse_target(transformed, "log_epsilon_minus_one")

    assert np.allclose(restored, target)


def test_scaffold_folds_keep_each_scaffold_in_one_fold() -> None:
    scaffolds = ["a", "a", "b", "c", "d", "e", "f", "g", "h", "i"]

    folds = scaffold_folds(scaffolds, n_splits=3)

    memberships: dict[str, list[int]] = {}
    for fold_index, (_, test) in enumerate(folds):
        for row_index in test:
            memberships.setdefault(scaffolds[row_index], []).append(fold_index)
    assert all(len(set(values)) == 1 for values in memberships.values())
    assert sorted(index for _, test in folds for index in test) == list(
        range(len(scaffolds))
    )


def test_acyclic_molecules_are_grouped_by_ecfp_cluster() -> None:
    groups = scaffold_group_keys(["CC", "CC"])

    assert groups[0] == groups[1]
    assert groups[0].startswith("acyclic_cluster:")
