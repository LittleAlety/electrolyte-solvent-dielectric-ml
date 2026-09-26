"""Lever 9 of the Week 14 R2 programme: the knowledge purity sweep.

A knowledge-data dual-driven framework published for rechargeable-electrolyte
molecular properties (Gao et al., Angew. Chem. Int. Ed. 2025, 64, e202416506,
DOI 10.1002/anie.202416506) reports a shape of failure that matches ours from
the opposite direction. Their own measurement is that embedding all 64
knowledge dimensions is *worse* than embedding the twenty (MP), twenty (BP) or
ten (FP) most important ones, and their stated mechanism is that less relevant
knowledge adds learning burden. Lever 2 of this programme appended six
association descriptors in one block and the grouped R2 fell by 0.0119; lever 3
fell by 0.1054. If the paper's mechanism is what killed lever 2, then the fix
is not different chemistry but a purity sweep: rank the candidate knowledge
inside the training side of every fold, then concatenate only the top k.

The pre-registration is `probes/dielectric_knowledge_purity_sweep_prereg.json`,
locked before this script was written. Its criteria are read from that file by
the test suite rather than restated from memory here::

    pass : the best k gains at least +0.0200 grouped R2 against the baseline
           arm re-run in this same script, positive in at least 8 of the 10
           repeats, with the placebo arm collapsed
    kill : every k stays below +0.0050 -> dead, reported as dead
    shape: the delta-R2 against k curve is itself a deliverable; the paper's
           mechanism predicts an interior peak, and a monotone decrease is a
           result that contradicts the mechanism and must be reported as such

Where this probe is deliberately *stricter* than the paper
---------------------------------------------------------

The paper ranks its knowledge dimensions on the whole dataset and then trains.
That is a leak: the ranking has seen the held-out rows. Here the ranking is
recomputed inside every training fold, on that fold' s training rows only, and
the ranking row scope is recorded per fold so a test can prove no test-fold row
ever entered it (see `assert_ranking_scope`).

The main scoreboard - 457 scored rows of 97 compounds, GroupKFold by InChIKey,
5 folds x 10 repeats, seed 42, min_test_rows_per_fold 2 - is not re-implemented
here. The scored mask, the fold dealing, the model specification and the metric
aggregation are all imported from the published probes:

* `dielectric_coverage_paired_benchmark` - feature blocks, the coverage loader,
  the scored mask recipe (`thermoml_zero_frequency` AND `room_temperature`);
* `dielectric_room_window_paired.masked_splits` - the paired fold dealing;
* `dielectric_band_ablation.drop_thin_folds` / `effective_repeats`;
* `dielectric_observations_grouped_benchmark.run_protocol` - the frozen XGBoost
  hybrid (`Morgan+Physical`, `XGB_PARAMS`), the per-fold metrics, the repeat
  aggregation;
* `dielectric_representation_ablation.fit_predict_representation` - the frozen
  hybrid definition reused verbatim by the purity loop.

The probe is read-only with respect to every frozen artefact. It writes only
`probes/dielectric_knowledge_purity_sweep_summary.json`,
`probes/artifacts/dielectric_knowledge_purity_sweep_*.csv` and
`reports/dielectric_knowledge_purity_sweep.md`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import numpy as np
from dielectric_band_ablation import (
    MIN_TEST_ROWS_PER_FOLD,
    ROOM_BAND,
    drop_thin_folds,
    effective_repeats,
)
from dielectric_coverage_paired_benchmark import (
    COVERAGE_PATH,
    ZERO_FREQUENCY_ORIGIN,
    load_coverage_table,
    merge_feature_blocks,
)
from dielectric_observations_grouped_benchmark import (
    FOLD_COLUMNS,
    METRIC_NAMES,
    PREDICTION_COLUMNS,
    build_matrices,
    run_protocol,
    summarize_repeats,
    write_csv_rows,
)
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    SEED,
    XGB_PARAMS,
    evaluate_repeat,
    fit_predict_representation,
    read_csv_rows,
)
from dielectric_room_window_paired import (
    HYBRID,
    audit_masks,
    fold_signature,
    masked_splits,
    scored_fold_signature,
)
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors
from xgboost import XGBRegressor

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_knowledge_purity_sweep_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_knowledge_purity_sweep_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_knowledge_purity_sweep.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_knowledge_purity_sweep"
LEVER_PATH = Path(__file__).resolve()

TASK_ID = "week14_lever9_knowledge_purity_sweep"
BASELINE_ARM = "paired_base"
FROZEN_ARM = "frozen_block_reference"
PLACEBO_FROZEN_ARM = "placebo_frozen_block_reference"

#: The ten members of the knowledge pool, in the order the pre-registration
#: fixed them. The order is also the deterministic tie-break for the ranking.
KNOWLEDGE_POOL = (
    "donor_count",
    "acceptor_count",
    "has_1_donor",
    "has_2_donors",
    "has_3plus_donors",
    "donor_acceptor_pair_density",
    "ring_count",
    "double_bond_count",
    "rotatable_bond_count",
    "heteroatom_over_carbon",
)
#: The k grid frozen in the pre-registration. Four points, four shots.
K_GRID = (2, 4, 6, 10)
SHOTS_THIS_LEVER = 4
#: Number of independent column shuffles averaged into one importance score.
IMPORTANCE_SHUFFLES = 3

#: The published `paired_base` hybrid R2 this script has to reproduce first.
REFERENCE_R2 = 0.4091179943351143
REFERENCE_TOLERANCE = 1e-9
#: The same three readings for the two single representations, pinned so a
#: drift in the fold dealing cannot hide behind the hybrid alone.
REFERENCE_TRIPLE = {
    "Morgan": 0.06487386371009436,
    "Morgan+Physical": REFERENCE_R2,
    "Physical": 0.2531659995294713,
}

PASS_DELTA_R2 = 0.02
KILL_DELTA_R2 = 0.005
MIN_POSITIVE_REPEATS = 8
PLACEBO_COLLAPSE_TOLERANCE = 0.02
PLACEBO_SEED_OFFSET = 1

SCOREBOARD_ROWS = 457
SCOREBOARD_COMPOUNDS = 97
SCOREBOARD_SPLITS = N_SPLITS

#: Donor sites (heteroatom-hydrogen) and acceptor heteroatoms, matching the
#: SMARTS the association probe used, plus the two 2-3 bond donor~acceptor
#: motifs whose de-duplicated atom-pair count becomes the pair density.
DONOR_SMARTS = "[$([O;H1,H2]),$([N;H1,H2,H3]),$([S;H1])]"
ACCEPTOR_SMARTS = "[$([O;H0,H1]),$([N;H0,H1,H2]),$([S;H0,H1])]"
PAIR_PATTERNS = (
    DONOR_SMARTS + "~*~" + ACCEPTOR_SMARTS,
    DONOR_SMARTS + "~*~*~" + ACCEPTOR_SMARTS,
)
_DONOR_QUERY = Chem.MolFromSmarts(DONOR_SMARTS)
_ACCEPTOR_QUERY = Chem.MolFromSmarts(ACCEPTOR_SMARTS)
_PAIR_QUERIES = tuple(Chem.MolFromSmarts(pattern) for pattern in PAIR_PATTERNS)
#: Elements that count as a heteroatom for `heteroatom_over_carbon`.
_CARBON_ATOMIC_NUMBER = 6
_HYDROGEN_ATOMIC_NUMBER = 1

class RankingLeakError(RuntimeError):
    """Raised when an importance ranking touches a test-fold row."""


def _use_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def knowledge_features_for_smiles(smiles: str) -> dict[str, float] | None:
    """Compute the ten knowledge members from a SMILES string, or None.

    Every member is RDKit-computable, so the sweep can never be blocked by cost
    or by data coverage. The counts are the linear signals the paper reports as
    saturating; the three `has_*_donor` dummies are the shape the paper's SHAP
    rules actually describe (one, two and three donors score +65.6 / +56.0 /
    +35.4 K, and a fourth donor adds nothing).
    """

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    donor_matches = mol.GetSubstructMatches(_DONOR_QUERY)
    acceptor_matches = mol.GetSubstructMatches(_ACCEPTOR_QUERY)
    donor_count = len(donor_matches)
    pair_atoms: set[tuple[int, int]] = set()
    for query in _PAIR_QUERIES:
        for match in mol.GetSubstructMatches(query):
            atoms = tuple(sorted({match[0], match[-1]}))
            pair_atoms.add(atoms)
    heavy = sum(
        1
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() != _HYDROGEN_ATOMIC_NUMBER
    )
    carbon = sum(
        1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == _CARBON_ATOMIC_NUMBER
    )
    hetero = heavy - carbon
    double_bonds = sum(
        1 for bond in mol.GetBonds() if bond.GetBondType() == Chem.BondType.DOUBLE
    )
    return {
        "donor_count": float(donor_count),
        "acceptor_count": float(len(acceptor_matches)),
        "has_1_donor": 1.0 if donor_count == 1 else 0.0,
        "has_2_donors": 1.0 if donor_count == 2 else 0.0,
        "has_3plus_donors": 1.0 if donor_count >= 3 else 0.0,
        "donor_acceptor_pair_density": float(len(pair_atoms)) / float(max(heavy, 1)),
        "ring_count": float(rdMolDescriptors.CalcNumRings(mol)),
        "double_bond_count": float(double_bonds),
        "rotatable_bond_count": float(rdMolDescriptors.CalcNumRotatableBonds(mol)),
        "heteroatom_over_carbon": float(hetero) / float(max(carbon, 1)),
    }


def knowledge_feature_block(
    smiles_values: Sequence[str],
) -> tuple[np.ndarray, dict[str, object]]:
    """Build the (rows x 10) knowledge matrix and its audit report."""

    rows: list[list[float]] = []
    failures: list[str] = []
    for smiles in smiles_values:
        features = knowledge_features_for_smiles(str(smiles))
        if features is None:
            failures.append(str(smiles))
            rows.append([float("nan")] * len(KNOWLEDGE_POOL))
            continue
        rows.append([features[name] for name in KNOWLEDGE_POOL])
    matrix = np.asarray(rows, dtype=np.float64)
    if failures:
        raise ValueError(
            "the knowledge pool cannot be computed for every row: "
            f"{len(failures)} unparsable SMILES"
        )
    if not np.isfinite(matrix).all():
        raise ValueError("the knowledge matrix contains non-finite values")
    return matrix, {
        "members": list(KNOWLEDGE_POOL),
        "rule": "every member is computed from the row SMILES with RDKit; no xTB rerun",
        "rows": int(matrix.shape[0]),
        "unparsable_smiles": len(failures),
        "column_stats": {
            name: {
                "min": float(matrix[:, position].min()),
                "max": float(matrix[:, position].max()),
                "mean": float(matrix[:, position].mean()),
            }
            for position, name in enumerate(KNOWLEDGE_POOL)
        },
    }


def permutation_importance(
    model: XGBRegressor,
    features: np.ndarray,
    target: np.ndarray,
    *,
    columns: Sequence[str],
    importance_rows: np.ndarray,
    shuffles: int = IMPORTANCE_SHUFFLES,
    seed: int = SEED,
) -> list[tuple[str, float]]:
    """Column-shuffle permutation importance measured on `importance_rows` only.

    The caller passes the fold' s training rows. Nothing here can reach a
    test-fold row, because the row scope is an explicit argument and the only
    data touched is `features[importance_rows]` / `target[importance_rows]`.
    Ties keep the pre-registered pool order, so the ranking is a pure function
    of the inputs and cannot move with a set iteration order.
    """

    rows = np.asarray(importance_rows, dtype=int)
    if rows.size == 0:
        raise ValueError("permutation importance needs at least one row")
    reference = features[rows]
    labels = np.asarray(target, dtype=float)[rows]
    base_mse = float(np.mean((model.predict(reference) - labels) ** 2))
    scores: list[tuple[str, float]] = []
    for position, name in enumerate(columns):
        drops: list[float] = []
        for shuffle in range(shuffles):
            rng = np.random.default_rng([seed, position, shuffle])
            permuted = reference.copy()
            permuted[:, position] = permuted[rng.permutation(permuted.shape[0]), position]
            mse = float(np.mean((model.predict(permuted) - labels) ** 2))
            drops.append(mse - base_mse)
        scores.append((name, float(np.mean(drops))))
    order = {name: index for index, name in enumerate(columns)}
    return sorted(scores, key=lambda item: (-item[1], order.get(item[0], len(columns))))


def assert_ranking_scope(
    *,
    importance_rows: Sequence[int],
    train_index: Sequence[int],
    test_index: Sequence[int],
    context: str = "",
) -> None:
    """Fail if an importance ranking used a row outside the training fold.

    This is the leak guard of the whole lever. The paper ranks its knowledge on
    the full dataset; a ranking computed with any test-fold row in view is the
    forbidden variant, and it is detected here rather than promised in prose.
    """

    rows = np.asarray([int(index) for index in importance_rows], dtype=int)
    train = np.asarray([int(index) for index in train_index], dtype=int)
    test = np.asarray([int(index) for index in test_index], dtype=int)
    overlap = np.intersect1d(rows, test)
    if overlap.size:
        raise RankingLeakError(
            f"{context}: the knowledge ranking touched {overlap.size} test-fold row(s): "
            f"{overlap[:5].tolist()}"
        )
    outside = rows[~np.isin(rows, train)]
    if outside.size:
        raise RankingLeakError(
            f"{context}: the knowledge ranking touched {outside.size} row(s) outside the "
            f"training fold: {outside[:5].tolist()}"
        )


def leaky_ranking_scope(train_index: Sequence[int], test_index: Sequence[int]) -> np.ndarray:
    """The forbidden scope, built only so the guard can be shown to fire.

    This helper exists for `tests/test_dielectric_knowledge_purity_sweep.py`,
    which constructs a ranking that has seen the test fold and asserts that
    `assert_ranking_scope` rejects it. The scoring pipeline never calls it: the
    pipeline passes `train_index` straight to `permutation_importance`.
    """

    return np.concatenate(
        [
            np.asarray([int(index) for index in train_index], dtype=int),
            np.asarray([int(index) for index in test_index], dtype=int),
        ]
    )


def scoreboard_splits(
    groups: Sequence[str],
    *,
    score_mask: Sequence[bool],
    train_mask: Sequence[bool],
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> tuple[list[tuple[int, int, np.ndarray, np.ndarray]], int, str]:
    """Deal the frozen main-scoreboard folds, once, for every arm to share.

    `masked_splits` deals them over the scored compounds; `drop_thin_folds`
    applies the pre-registered 2-row floor; `effective_repeats` shrinks the
    repeat count only when the compound count cannot fill the requested folds.
    """

    group_array = np.asarray(groups)
    score = np.asarray(score_mask, dtype=bool)
    train = np.asarray(train_mask, dtype=bool)
    compound_count = int(np.unique(group_array[score]).size)
    repeats, note = effective_repeats(compound_count, n_splits=n_splits, requested=n_repeats)
    if repeats == 0:
        raise ValueError(f"no repeat can fill {n_splits} grouped folds from {compound_count} compounds")
    splits = list(
        drop_thin_folds(
            masked_splits(
                groups,
                score_mask=score,
                train_mask=train,
                n_splits=n_splits,
                n_repeats=repeats,
                seed=seed,
            ),
            min_test_rows=MIN_TEST_ROWS_PER_FOLD,
        )
    )
    if not splits:
        raise ValueError("no fold survived the thin-fold filter")
    audit = audit_masks(groups, score_mask=score, train_mask=train, splits=splits)
    if audit["scored_rows_outside_the_score_mask"]:
        raise ValueError("a scored row sits outside the score mask")
    if audit["folds_with_a_straddling_compound"]:
        raise ValueError("a compound straddles the fold boundary")
    return splits, repeats, note

def _fold_row(
    name: str,
    *,
    repeat: int,
    fold: int,
    train_index: np.ndarray,
    test_index: np.ndarray,
    groups: Sequence[str],
    target: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, object]:
    group_array = np.asarray(groups)
    metrics = evaluate_repeat(target[test_index], prediction)
    return {
        "protocol": name,
        "representation": HYBRID,
        "repeat": repeat,
        "fold": fold,
        "train_rows": int(train_index.size),
        "test_rows": int(test_index.size),
        "train_compounds": int(np.unique(group_array[train_index]).size),
        "test_compounds": int(np.unique(group_array[test_index]).size),
        **{metric: metrics[metric] for metric in ("mae", "rmse", "r2", "spearman")},
    }


def _repeat_rows_from(
    name: str,
    buckets: Mapping[int, tuple[np.ndarray, np.ndarray]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for repeat in sorted(buckets):
        labels, predictions = buckets[repeat]
        metrics = evaluate_repeat(labels, predictions)
        rows.append(
            {
                "protocol": name,
                "representation": HYBRID,
                "repeat": int(repeat),
                **{metric: metrics[metric] for metric in METRIC_NAMES},
            }
        )
    return rows


def run_frozen_reference(
    name: str,
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    groups: Sequence[str],
    seed: int = SEED,
) -> dict[str, object]:
    """Score the frozen 13-column block alone, through the lever' s own loop.

    `run_protocol` already scores this arm as `paired_base`; this second pass
    through the purity loop exists so the loop can be shown to be faithful -
    the two readings must agree to machine precision - before any top-k result
    from the loop is believed.
    """

    fold_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    buckets: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for repeat, fold, train_index, test_index in splits:
        prediction, _ = fit_predict_representation(
            HYBRID,
            morgan=morgan,
            physical=physical,
            target=target,
            train_indices=train_index,
            test_indices=test_index,
            seed=seed,
        )
        fold_rows.append(
            _fold_row(
                name,
                repeat=repeat,
                fold=fold,
                train_index=train_index,
                test_index=test_index,
                groups=groups,
                target=target,
                prediction=prediction,
            )
        )
        bucket = buckets.setdefault(repeat, (np.zeros(0), np.zeros(0)))
        buckets[repeat] = (
            np.concatenate([bucket[0], target[test_index]]),
            np.concatenate([bucket[1], prediction]),
        )
        for row_index, value in zip(test_index, prediction, strict=True):
            prediction_rows.append(
                {
                    "protocol": name,
                    "representation": HYBRID,
                    "repeat": repeat,
                    "fold": fold,
                    "inchikey": groups[int(row_index)],
                    "T_K": float(temperatures[int(row_index)]),
                    "target": float(target[int(row_index)]),
                    "prediction": float(value),
                }
            )
    repeat_rows = _repeat_rows_from(name, buckets)
    return {
        "arm": name,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "summary": summarize_repeats(repeat_rows)[name],
    }


def run_purity_arm(
    name: str,
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    morgan: np.ndarray,
    frozen_physical: np.ndarray,
    knowledge: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    groups: Sequence[str],
    k_grid: Sequence[int] = K_GRID,
    seed: int = SEED,
    shuffles: int = IMPORTANCE_SHUFFLES,
) -> dict[str, object]:
    """Rank the knowledge pool inside each training fold, then score every k.

    One model is fitted per fold on the frozen block plus the full pool; its
    column-shuffle importance is measured on that fold' s training rows alone
    (the leak guard runs on every fold, not just in the tests); the members are
    ordered by that importance; and each k in the grid is then scored by
    re-fitting the frozen hybrid on the frozen block plus the top k members.
    """

    arm = {k: f"{name}_k{k}" for k in k_grid}
    fold_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    importance_rows: list[dict[str, object]] = []
    buckets: dict[str, dict[int, tuple[np.ndarray, np.ndarray]]] = {
        arm_name: {} for arm_name in arm.values()
    }
    full = np.hstack([frozen_physical, knowledge])
    position_of = {member: index for index, member in enumerate(KNOWLEDGE_POOL)}
    for repeat, fold, train_index, test_index in splits:
        model = XGBRegressor(**XGB_PARAMS, random_state=seed)
        model.fit(full[train_index], target[train_index])
        ranked = permutation_importance(
            model,
            full,
            target,
            columns=KNOWLEDGE_POOL,
            importance_rows=train_index,
            shuffles=shuffles,
            seed=seed,
        )
        assert_ranking_scope(
            importance_rows=train_index,
            train_index=train_index,
            test_index=test_index,
            context=f"{name!r} repeat {repeat} fold {fold}",
        )
        order = [member for member, _score in ranked]
        for rank, (member, score) in enumerate(ranked, start=1):
            importance_rows.append(
                {
                    "protocol": name,
                    "repeat": repeat,
                    "fold": fold,
                    "rank": rank,
                    "member": member,
                    "importance": float(score),
                    "ranked_in_top_3": 1 if rank <= 3 else 0,
                    "ranking_rows": int(train_index.size),
                    "test_rows_visible_to_ranking": 0,
                }
            )
        labels = np.asarray(target, dtype=float)
        for k in k_grid:
            chosen = order[: int(k)]
            columns = [position_of[member] for member in chosen]
            physical_k = np.hstack([frozen_physical, knowledge[:, columns]])
            prediction, _ = fit_predict_representation(
                HYBRID,
                morgan=morgan,
                physical=physical_k,
                target=target,
                train_indices=train_index,
                test_indices=test_index,
                seed=seed,
            )
            fold_rows.append(
                _fold_row(
                    arm[int(k)],
                    repeat=repeat,
                    fold=fold,
                    train_index=train_index,
                    test_index=test_index,
                    groups=groups,
                    target=labels,
                    prediction=prediction,
                )
            )
            bucket = buckets[arm[int(k)]].setdefault(repeat, (np.zeros(0), np.zeros(0)))
            buckets[arm[int(k)]][repeat] = (
                np.concatenate([bucket[0], labels[test_index]]),
                np.concatenate([bucket[1], prediction]),
            )
            for row_index, value in zip(test_index, prediction, strict=True):
                prediction_rows.append(
                    {
                        "protocol": arm[int(k)],
                        "representation": HYBRID,
                        "repeat": repeat,
                        "fold": fold,
                        "inchikey": groups[int(row_index)],
                        "T_K": float(temperatures[int(row_index)]),
                        "target": float(labels[int(row_index)]),
                        "prediction": float(value),
                    }
                )
    repeat_rows: list[dict[str, object]] = []
    summaries: dict[str, dict[str, dict]] = {}
    for k in k_grid:
        arm_name = arm[int(k)]
        rows = _repeat_rows_from(arm_name, buckets[arm_name])
        repeat_rows.extend(rows)
        summaries[arm_name] = summarize_repeats(rows)[arm_name]
    return {
        "arm": name,
        "arm_by_k": arm,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "importance_rows": importance_rows,
        "summary_by_arm": summaries,
    }


def fold_mean_floor(
    name: str,
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    target: np.ndarray,
) -> dict[str, object]:
    """The no-information floor: the training-fold mean, on the identical folds.

    Lever 2 established that a shuffled-label arm cannot be measured against a
    real-label baseline - it is unsatisfiable by construction - so the collapse
    test is taken against this floor, computed here on whatever label vector the
    caller passes (the real one, or the permuted one).
    """

    labels = np.asarray(target, dtype=float)
    fold_rows: list[dict[str, object]] = []
    buckets: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for repeat, fold, train_index, test_index in splits:
        prediction = np.full(test_index.size, float(np.mean(labels[train_index])))
        metrics = evaluate_repeat(labels[test_index], prediction)
        fold_rows.append(
            {
                "protocol": name,
                "representation": HYBRID,
                "repeat": repeat,
                "fold": fold,
                "train_rows": int(train_index.size),
                "test_rows": int(test_index.size),
                "train_compounds": 0,
                "test_compounds": 0,
                **{metric: metrics[metric] for metric in ("mae", "rmse", "r2", "spearman")},
            }
        )
        bucket = buckets.setdefault(repeat, (np.zeros(0), np.zeros(0)))
        buckets[repeat] = (
            np.concatenate([bucket[0], labels[test_index]]),
            np.concatenate([bucket[1], prediction]),
        )
    repeat_rows = _repeat_rows_from(name, buckets)
    return {
        "arm": name,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "summary": summarize_repeats(repeat_rows)[name],
    }


def shuffled_target(target: np.ndarray, *, seed: int) -> tuple[np.ndarray, list[int]]:
    """Permute the labels over the whole row pool for the placebo arm."""

    values = np.asarray(target, dtype=float)
    order = np.random.default_rng(seed).permutation(values.size)
    return values[order], [int(index) for index in order]


def per_repeat_r2(
    repeat_rows: Sequence[Mapping[str, object]],
    arm: str,
    *,
    representation: str = HYBRID,
) -> dict[int, float]:
    """Read the per-repeat R2 of one arm, keyed by repeat index.

    The paired sign test needs the ten repeat readings side by side, which the
    aggregated summary does not carry, so they are read from the repeat rows.
    """

    values = {
        int(str(row["repeat"])): float(str(row["r2"]))
        for row in repeat_rows
        if str(row["protocol"]) == arm and str(row["representation"]) == representation
    }
    if not values:
        raise ValueError(f"{arm}: the repeat rows carry no r2 for this arm")
    return values


def verify_reference_triple(
    readings: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    arm: str,
) -> dict[str, object]:
    """Compare the re-run baseline against the published `paired_base` readings."""

    per_representation: dict[str, object] = {}
    for representation, expected in sorted(REFERENCE_TRIPLE.items()):
        mine = float(readings[arm][representation]["r2"]["mean"])
        difference = abs(mine - expected)
        per_representation[representation] = {
            "expected": expected,
            "reproduced": mine,
            "abs_difference": difference,
            "bit_exact": difference <= REFERENCE_TOLERANCE,
        }
    hybrid = per_representation[HYBRID]
    return {
        "arm": arm,
        "representations": per_representation,
        "reproduced_r2": hybrid["reproduced"],  # type: ignore[index]
        "published_r2": REFERENCE_R2,
        "abs_difference": hybrid["abs_difference"],  # type: ignore[index]
        "tolerance": REFERENCE_TOLERANCE,
        "verified": bool(hybrid["bit_exact"]),  # type: ignore[index]
    }


def classify_curve(
    deltas: Mapping[int, float],
    *,
    k_grid: Sequence[int] = K_GRID,
) -> dict[str, object]:
    """Name the shape of the delta-R2 against k curve.

    The paper's law is that more embedded knowledge lowers accuracy, which makes
    the curve peak somewhere strictly inside the grid: too few dimensions loses
    signal, too many adds learning burden. The classification below is
    mechanical and `contradicts_mechanism` is exactly `not interior_peak`, so
    neither a monotone increase nor a monotone decrease can be quietly
    relabelled as a peak.

    What a contradiction here does *not* mean: the grid stops at k=10, which is
    the whole ten-member pool, so the sweep has a hard ceiling and a peak beyond
    the grid cannot be excluded. A monotone increase falsifies the *decline
    branch* of the paper's law, not the existence of an optimum k.
    """

    keys = [int(k) for k in k_grid]
    values = [float(deltas[k]) for k in keys]
    best_position = int(np.argmax(values))
    monotone_decreasing = all(values[i] >= values[i + 1] for i in range(len(values) - 1))
    monotone_increasing = all(values[i] <= values[i + 1] for i in range(len(values) - 1))
    interior = 0 < best_position < len(values) - 1
    if monotone_decreasing:
        shape = "monotone_decreasing"
    elif monotone_increasing:
        shape = "monotone_increasing"
    elif interior:
        shape = "interior_peak"
    elif best_position == 0:
        shape = "edge_peak_low_k"
    else:
        shape = "edge_peak_high_k"
    if interior:
        neighbours = (values[best_position - 1], values[best_position + 1])
        strictly_higher = all(values[best_position] > neighbour for neighbour in neighbours)
    else:
        strictly_higher = False
    if not interior:
        if monotone_decreasing:
            mechanism_reading = "no_interior_peak_monotone_decrease"
        elif monotone_increasing:
            mechanism_reading = "no_interior_peak_monotone_increase"
        else:
            mechanism_reading = "no_interior_peak_edge_peak"
    elif strictly_higher:
        mechanism_reading = "interior_peak"
    else:
        mechanism_reading = "interior_peak_not_strictly_above_both_neighbours"
    contradicts = not interior
    return {
        "k_grid": keys,
        "delta_r2_by_k": {str(k): float(deltas[k]) for k in keys},
        "best_k": keys[best_position],
        "best_delta_r2": float(values[best_position]),
        "best_delta_is_positive": bool(values[best_position] > 0.0),
        "shape": shape,
        "monotone_decreasing": bool(monotone_decreasing),
        "monotone_increasing": bool(monotone_increasing),
        "interior_peak": bool(interior),
        "interior_peak_is_strict": bool(strictly_higher),
        "paper_mechanism_prediction": (
            "an interior peak: a small k loses signal, a large k adds learning burden"
        ),
        "contradicts_mechanism": bool(contradicts),
        "mechanism_reading": mechanism_reading,
        "contradiction_explanation": (
            "the paper's law that more embedded knowledge lowers accuracy predicts an interior "
            "peak; inside the frozen grid the curve has none, so that law is not reproduced. "
            "What is falsified is the decline branch, not the existence of an optimum: the grid "
            "caps at k=10, which is the whole knowledge pool, so a peak beyond the grid cannot "
            "be excluded"
            if contradicts
            else "the observed curve peaks strictly inside the grid, as the paper's law predicts"
        ),
    }


def importance_stability(
    importance_rows: Sequence[Mapping[str, object]],
    *,
    top_k: int = 3,
) -> dict[str, object]:
    """How much the per-fold importance ranking moves across the 50 folds."""

    per_fold: dict[tuple[int, int], list[tuple[int, str]]] = defaultdict(list)
    for row in importance_rows:
        key = (int(str(row["repeat"])), int(str(row["fold"])))
        per_fold[key].append((int(str(row["rank"])), str(row["member"])))
    top_sets: list[tuple[str, ...]] = []
    for key in sorted(per_fold):
        ordered = [member for _rank, member in sorted(per_fold[key])]
        top_sets.append(tuple(ordered[:top_k]))
    distinct: dict[tuple[str, ...], int] = {}
    for entry in top_sets:
        distinct[entry] = distinct.get(entry, 0) + 1
    changes = sum(1 for before, after in pairwise(top_sets) if before != after)
    by_member: dict[str, dict[str, object]] = {}
    for member in KNOWLEDGE_POOL:
        ranks = [
            int(str(row["rank"])) for row in importance_rows if str(row["member"]) == member
        ]
        scores = [
            float(str(row["importance"])) for row in importance_rows if str(row["member"]) == member
        ]
        by_member[member] = {
            "folds": len(ranks),
            "mean_rank": float(np.mean(ranks)),
            "median_rank": float(np.median(ranks)),
            "min_rank": int(np.min(ranks)),
            "max_rank": int(np.max(ranks)),
            "top_3_folds": int(sum(1 for rank in ranks if rank <= top_k)),
            "mean_importance": float(np.mean(scores)),
        }
    most_common = max(distinct.items(), key=lambda item: (item[1], item[0]))
    always_present = sorted(
        member
        for member in KNOWLEDGE_POOL
        if by_member[member]["top_3_folds"] == len(top_sets)  # type: ignore[operator]
    )
    return {
        "folds": len(top_sets),
        "top_k": int(top_k),
        "distinct_top_k_sets": len(distinct),
        "top_k_set_counts": {"|".join(entry): count for entry, count in sorted(distinct.items())},
        "modal_top_k_set": list(most_common[0]),
        "modal_top_k_set_count": int(most_common[1]),
        "changes_between_consecutive_folds": int(changes),
        "members_in_every_top_k_set": always_present,
        "per_member": by_member,
    }


def placebo_collapse_readout(
    *,
    placebo_best_r2: float,
    placebo_floor_r2: float,
    placebo_best_delta_r2: float,
    real_baseline_r2: float,
    real_best_k: int,
) -> dict[str, object]:
    """Decide whether the shuffled-label arm collapsed.

    Two readings are taken from the pre-registered `|delta R2| <= 0.02`: the
    lever-2 precedent (the shuffled-label arm must not beat the no-information
    floor on the identical permuted labels) and the within-pipeline contrast
    (the same top-k pipeline on shuffled labels must not manufacture a delta).
    Both must hold; neither threshold is widened.
    """

    over_the_floor = float(placebo_best_r2) - float(placebo_floor_r2)
    return {
        "placebo_r2_at_best_real_k": float(placebo_best_r2),
        "placebo_floor_r2": float(placebo_floor_r2),
        "placebo_floor_definition": (
            "the training-fold-mean predictor scored on the identical folds and the "
            "identical permuted label vector as the placebo arm"
        ),
        "delta_over_the_floor": float(over_the_floor),
        "placebo_within_pipeline_delta_r2": float(placebo_best_delta_r2),
        "abs_placebo_within_pipeline_delta_r2": abs(float(placebo_best_delta_r2)),
        "real_baseline_r2": float(real_baseline_r2),
        "delta_vs_the_real_label_baseline": float(placebo_best_r2) - float(real_baseline_r2),
        "best_real_k": int(real_best_k),
        "tolerance": PLACEBO_COLLAPSE_TOLERANCE,
        "floor_rule_holds": bool(over_the_floor <= PLACEBO_COLLAPSE_TOLERANCE),
        "within_pipeline_rule_holds": bool(
            abs(float(placebo_best_delta_r2)) <= PLACEBO_COLLAPSE_TOLERANCE
        ),
        "collapsed": bool(
            over_the_floor <= PLACEBO_COLLAPSE_TOLERANCE
            and abs(float(placebo_best_delta_r2)) <= PLACEBO_COLLAPSE_TOLERANCE
        ),
        "wording_note": (
            "the pre-registration names no reference for the collapse delta; against the "
            "real-label baseline the test is unsatisfiable by construction, so the floor "
            "reading is primary and the within-pipeline reading is reported beside it"
        ),
    }


def build_verdict(
    *,
    baseline_verified: bool,
    reproduced_r2: float,
    curve: Mapping[str, object],
    positive_repeats: int,
    repeats_total: int,
    placebo_collapse: Mapping[str, object],
) -> dict[str, object]:
    """Apply the pre-registered criteria in the order they were frozen.

    The kill line is checked before the pass line is celebrated, the placebo arm
    is checked before any delta is quoted, and a sweep whose baseline arm did not
    reproduce is stamped unverified with no delta at all.
    """

    best_k = int(curve["best_k"])
    best_delta = float(curve["best_delta_r2"])
    all_deltas = {int(k): float(v) for k, v in curve["delta_r2_by_k"].items()}  # type: ignore[union-attr]
    collapsed = bool(placebo_collapse["collapsed"])
    reasons: list[str] = []
    if not baseline_verified:
        decision = "unverified"
        reasons.append(
            f"the baseline arm reproduced {reproduced_r2!r} against the published "
            f"{REFERENCE_R2!r}; no delta from this lever may be quoted"
        )
    elif not collapsed:
        decision = "dead"
        reasons.append(
            "the shuffled-label placebo did not collapse "
            f"(over the floor {float(placebo_collapse['delta_over_the_floor']):+.4f}, "
            f"within the pipeline {float(placebo_collapse['placebo_within_pipeline_delta_r2']):+.4f})"
        )
    elif best_delta >= PASS_DELTA_R2:
        if positive_repeats >= MIN_POSITIVE_REPEATS:
            decision = "pass"
            reasons.append(
                f"k={best_k} gained {best_delta:+.4f} grouped R2 against the re-run baseline, "
                f"positive in {positive_repeats} of {repeats_total} repeats, placebo collapsed"
            )
        else:
            decision = "dead"
            reasons.append(
                f"k={best_k} gained {best_delta:+.4f} but only {positive_repeats} of "
                f"{repeats_total} repeats were positive, below the pre-registered "
                f"{MIN_POSITIVE_REPEATS}: a lift carried by a minority of repeats is not a lift"
            )
    elif all(delta < KILL_DELTA_R2 for delta in all_deltas.values()):
        decision = "dead"
        reasons.append(
            "every k stayed below the "
            f"+{KILL_DELTA_R2} kill line: {all_deltas}"
        )
    else:
        decision = "sub_threshold"
        reasons.append(
            f"k={best_k} moved grouped R2 by {best_delta:+.4f}: above the kill line "
            f"+{KILL_DELTA_R2} but below the pass line +{PASS_DELTA_R2}"
        )
    if bool(curve["contradicts_mechanism"]) and decision != "unverified":
        reasons.append(
            f"the delta-R2 curve is `{curve['shape']}` with no interior peak "
            f"(`{curve['mechanism_reading']}`): the paper's law that more embedded knowledge "
            "lowers accuracy is not reproduced inside the frozen grid, and the contradiction is "
            "reported as such rather than filed as a non-result"
        )
    return {
        "decision": decision,
        "reasons": reasons,
        "criteria_applied": {
            "pass_criterion": (
                f"the best k reaches a grouped R2 delta of at least +{PASS_DELTA_R2}, positive "
                f"in at least {MIN_POSITIVE_REPEATS} of {repeats_total} repeats, placebo collapsed"
            ),
            "kill_line": f"every k stays below +{KILL_DELTA_R2} -> dead",
            "placebo_rule": (
                "the shuffled-label arm must not beat the no-information floor on the identical "
                f"permuted labels by more than {PLACEBO_COLLAPSE_TOLERANCE}, and the same top-k "
                f"pipeline on shuffled labels must not manufacture a delta beyond "
                f"{PLACEBO_COLLAPSE_TOLERANCE}"
            ),
            "single_repeat_rule": "a pass carried by a single repeat is not a pass",
        },
        "best_k": best_k,
        "best_delta_r2": best_delta,
        "positive_repeats": int(positive_repeats),
        "repeats_total": int(repeats_total),
        "placebo_collapsed": collapsed,
        "delta_r2_by_k": {str(k): value for k, value in sorted(all_deltas.items())},
        "carried_into_the_merge_arm": decision == "pass",
    }


def delta_curve(
    *,
    readings: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    baseline_arm: str,
    arm_by_k: Mapping[int, str],
) -> dict[int, float]:
    """The k -> delta-R2 curve, delta taken against the re-run baseline arm."""

    base = float(readings[baseline_arm][HYBRID]["r2"]["mean"])
    return {
        int(k): float(readings[arm][HYBRID]["r2"]["mean"]) - base
        for k, arm in sorted(arm_by_k.items())
    }

def build_summary(
    *,
    seed: int,
    n_repeats: int,
    executed_repeats: int,
    repeat_note: str,
    k_grid: Sequence[int],
    baseline_arm: str,
    frozen_arm: str,
    purity_arm_by_k: Mapping[int, str],
    readings: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    reference: Mapping[str, object],
    loop_check: Mapping[str, object],
    curve: Mapping[str, object],
    per_repeat_deltas: Mapping[int, Mapping[int, float]],
    positive_repeats: Mapping[int, int],
    stability: Mapping[str, object],
    placebo: Mapping[str, object],
    floors: Mapping[str, object],
    verdict: Mapping[str, object],
    guards: Mapping[str, object],
    fold_deal: Mapping[str, object],
    pool_report: Mapping[str, object],
    feature_report: Mapping[str, object],
    coverage_dropped: Mapping[str, int],
    inputs: Mapping[str, object],
    generated_at: str,
) -> dict[str, object]:
    prereg_payload = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    prereg = {
        "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
        "sha256": canonical_text_sha256(PREREG_PATH),
        "status": prereg_payload["status"],
        "locked_at_utc": prereg_payload["locked_at_utc"],
        "lock_rule": prereg_payload["lock_rule"],
        "thresholds": {
            "pass_delta_r2": PASS_DELTA_R2,
            "kill_delta_r2": KILL_DELTA_R2,
            "min_positive_repeats": MIN_POSITIVE_REPEATS,
            "placebo_collapse_tolerance": PLACEBO_COLLAPSE_TOLERANCE,
        },
        "k_grid": list(prereg_payload["purity_controller"]["k_grid"]),
        "pass_criterion": prereg_payload["pass_criterion"],
        "kill_line": prereg_payload["kill_line"],
        "shape_finding_to_report": prereg_payload["shape_finding_to_report"],
        "leak_rule": prereg_payload["purity_controller"]["leak_rule"],
        "flow_controller": prereg_payload["purity_controller"]["flow_controller"],
        "knowledge_pool_members": list(prereg_payload["knowledge_pool"]["members"]),
        "shots_registered_up_front": prereg_payload["shots_policy"]["shots_registered_up_front"],
        "forbidden": list(prereg_payload["forbidden"]),
        "frozen_red_lines_untouched": list(prereg_payload["frozen_red_lines_untouched"]),
    }
    pool_members_match = tuple(prereg["knowledge_pool_members"]) == KNOWLEDGE_POOL
    if not pool_members_match:
        raise ValueError(
            "the knowledge pool in the pre-registration moved: "
            f"{prereg['knowledge_pool_members']} != {list(KNOWLEDGE_POOL)}"
        )
    return {
        "schema_version": 1,
        "task": TASK_ID,
        "title": (
            "Lever 9: knowledge purity sweep with per-fold importance ranking, motivated by "
            "Angew. Chem. Int. Ed. 2025, 64, e202416506"
        ),
        "generated_at_utc": generated_at,
        "prereg": prereg,
        "main_scoreboard": {
            "rows_scored": int(guards["scored_rows_value"]),
            "compounds_scored": int(guards["scored_compounds_value"]),
            "splits": int(fold_deal["splits"]),
            "n_splits": int(N_SPLITS),
            "repeats_requested": int(n_repeats),
            "repeats_executed": int(executed_repeats),
            "seed": int(seed),
            "splitter": "GroupKFold by InChIKey (masked_splits)",
            "min_test_rows_per_fold": MIN_TEST_ROWS_PER_FOLD,
            "model": "XGBRegressor with XGB_PARAMS, frozen hyper-parameters",
            "objective": XGB_PARAMS["objective"],
            "baseline_to_reproduce": REFERENCE_R2,
            "tolerance": REFERENCE_TOLERANCE,
            "folds_frozen": True,
            "guards_passed": bool(all(bool(value) for value in guards["checks"].values())),  # type: ignore[union-attr]
            "guards": dict(guards["checks"]),  # type: ignore[arg-type]
            "guard_details": dict(guards),
            "fold_deal": dict(fold_deal),
        },
        "baseline_reproduces": dict(reference),
        "loop_faithfulness": dict(loop_check),
        "knowledge_pool": dict(pool_report),
        "purity_controller": {
            "definition": (
                "inside each training fold, fit the frozen model on the fold's training rows "
                "using the frozen 13-column physical block plus the full knowledge pool, rank the "
                "pool members by permutation importance measured on the fold's own training rows "
                "only, then re-fit using only the top k members alongside the frozen block"
            ),
            "k_grid": [int(k) for k in k_grid],
            "importance_definition": (
                "column-shuffle permutation importance: mean increase in training-row MSE after "
                f"shuffling one member's column, averaged over {IMPORTANCE_SHUFFLES} independent "
                "shuffles, ties broken by the pre-registered pool order"
            ),
            "importance_rows": "the fold's training rows, and nothing else",
            "flow_controller_implemented": False,
            "flow_controller_boundary": (
                "the paper also learns how much of the selected knowledge to blend in; this probe "
                "does not. It is a stated boundary, not an achieved feature."
            ),
        },
        "arms": {
            "baseline": baseline_arm,
            "frozen_reference": frozen_arm,
            "purity": {str(k): arm for k, arm in sorted(purity_arm_by_k.items())},
            "placebo": dict(placebo["arms"]),  # type: ignore[arg-type]
            "floors": {name: float(block["r2"]["mean"]) for name, block in floors.items()},  # type: ignore[index]
        },
        "readings": {arm: dict(block) for arm, block in readings.items()},
        "delta_r2_by_k": {str(k): float(v) for k, v in curve["delta_r2_by_k"].items()},  # type: ignore[union-attr]
        "per_repeat_delta_r2": {
            str(k): {str(repeat): float(value) for repeat, value in sorted(block.items())}
            for k, block in sorted(per_repeat_deltas.items())
        },
        "positive_repeats_by_k": {str(k): int(v) for k, v in sorted(positive_repeats.items())},
        "curve": dict(curve),
        "importance_stability": dict(stability),
        "placebo": dict(placebo),
        "verdict": dict(verdict),
        "shots": {
            "count": SHOTS_THIS_LEVER,
            "k_grid": [int(k) for k in k_grid],
            "rule": (
                "each k in the grid is one scored attempt at the main scoreboard and counts as a "
                "shot; the baseline re-run is the reference, not a shot"
            ),
            "declared_up_front": True,
            "all_k_reported": True,
        },
        "honest_boundaries": [
            (
                "The flow controller is not implemented. The paper learns how much of the selected "
                "knowledge to blend in; this probe ranks and truncates only. That is a stated "
                "boundary, not an achieved feature."
            ),
            (
                "The paper's absolute R2 of 0.97-0.99 is measured on melting, boiling and flash "
                "points, which are atomic-count-dominated phase-change temperatures. Our target is "
                "the collective dielectric response. Their numbers are not portable to us and are "
                "never quoted as a bar."
            ),
            (
                "0.5332 and 0.5454 may only be quoted with their pool definitions (a 147-compound "
                "training pool against a 97-compound fixed scoring pool). The v1.0 headline 0.364 "
                "lives on the frozen 236-compound pool and is a different scoreboard from the "
                f"{SCOREBOARD_ROWS}-row fixed pool this probe scores."
            ),
            (
                "The knowledge ranking is recomputed inside every training fold, so this probe is "
                "stricter than the paper, whose ranking is computed on the whole dataset before "
                "training. The stricter version can only differ from theirs by being less leaky."
            ),
            (
                "What is falsified by a curve without an interior peak is the paper's law that "
                "more embedded knowledge lowers accuracy, not the existence of an optimum k. The "
                "frozen k grid stops at k=10, which is the entire ten-member pool, so the sweep "
                "has a hard ceiling: a peak living beyond the grid cannot be excluded. The honest "
                "reading is 'no interior peak inside the frozen grid', never 'the optimum is the "
                "full pool'."
            ),
        ],
        "inputs": dict(inputs),
        "coverage_loader_dropped": dict(coverage_dropped),
        "feature_blocks": dict(feature_report),
    }

def render_report(summary: Mapping[str, object]) -> list[str]:
    """Render the markdown report straight from the summary, no second source."""

    scoreboard = summary["main_scoreboard"]
    verdict = summary["verdict"]
    curve = summary["curve"]
    stability = summary["importance_stability"]
    placebo = summary["placebo"]
    collapse = placebo["collapse"]
    pool = summary["knowledge_pool"]
    lines: list[str] = []
    lines.append("# Lever 9: knowledge purity sweep (per-fold importance ranking)")
    lines.append("")
    lines.append(
        "Motivation: Angew. Chem. Int. Ed. 2025, 64, e202416506 (DOI "
        "10.1002/anie.202416506) reports that embedding all 64 knowledge dimensions is worse "
        "than embedding the top 20 / 20 / 10, because less relevant knowledge adds learning "
        "burden. Lever 2 of this programme appended six association descriptors at once and "
        "the grouped R2 fell by 0.0119. This probe tests the resulting hypothesis directly."
    )
    lines.append("")
    lines.append("## 1 Baseline reproduction")
    lines.append("")
    baseline = summary["baseline_reproduces"]
    lines.append(f"- arm: `{baseline['arm']}` re-run inside this script")
    lines.append(f"- reproduced hybrid R2: `{baseline['reproduced_r2']!r}`")
    lines.append(f"- published hybrid R2: `{baseline['published_r2']!r}`")
    lines.append(
        f"- absolute difference: `{baseline['abs_difference']!r}` against a tolerance of "
        f"`{baseline['tolerance']!r}` -> verified `{baseline['verified']}`"
    )
    for representation, block in sorted(baseline["representations"].items()):
        lines.append(
            f"- `{representation}`: reproduced `{block['reproduced']!r}` vs expected "
            f"`{block['expected']!r}` (bit exact `{block['bit_exact']}`)"
        )
    loop = summary["loop_faithfulness"]
    lines.append(
        f"- purity loop vs `run_protocol` on the identical frozen block: "
        f"`{loop['frozen_block_reference_r2']!r}` vs `{loop['run_protocol_baseline_r2']!r}`, "
        f"abs difference `{loop['abs_difference']!r}` -> agrees `{loop['agrees']}`"
    )
    lines.append(
        f"- scoreboard guards: `{scoreboard['guards_passed']}` "
        f"({scoreboard['rows_scored']} rows / {scoreboard['compounds_scored']} compounds / "
        f"{scoreboard['splits']} splits / seed {scoreboard['seed']})"
    )
    lines.append("")
    lines.append("## 2 The purity curve: delta-R2 against k")
    lines.append("")
    lines.append("| k | grouped R2 | delta R2 | positive repeats |")
    lines.append("| --- | --- | --- | --- |")
    for k in curve["k_grid"]:
        key = str(k)
        lines.append(
            f"| {k} | `{summary['readings'][summary['arms']['purity'][key]][HYBRID]['r2']['mean']!r}` "
            f"| `{curve['delta_r2_by_k'][key]:+.4f}` "
            f"| {summary['positive_repeats_by_k'][key]} / "
            f"{scoreboard['repeats_executed']} |"
        )
    lines.append(
        f"- best k: `{curve['best_k']}` at delta R2 `{curve['best_delta_r2']:+.4f}` "
        f"(positive `{curve['best_delta_is_positive']}`)"
    )
    lines.append(f"- curve shape: `{curve['shape']}`")
    lines.append(f"- monotone decreasing: `{curve['monotone_decreasing']}`")
    lines.append(f"- monotone increasing: `{curve['monotone_increasing']}`")
    lines.append(f"- interior peak: `{curve['interior_peak']}` (strict `{curve['interior_peak_is_strict']}`)")
    lines.append(
        f"- mechanism reading: `{curve['mechanism_reading']}` -> contradicts the paper's "
        f"interior-peak law `{curve['contradicts_mechanism']}` (= `not interior_peak`); "
        f"{curve['contradiction_explanation']}"
    )
    lines.append("")
    lines.append("Per-repeat signs:")
    lines.append("")
    for k in curve["k_grid"]:
        block = summary["per_repeat_delta_r2"][str(k)]
        signs = "".join("+" if float(v) > 0 else "-" for v in block.values())
        lines.append(f"- k={k}: `{signs}` (repeat 0..{len(block) - 1}) -> {summary['positive_repeats_by_k'][str(k)]} positive")
    lines.append("")
    lines.append("## 3 Importance stability across folds")
    lines.append("")
    lines.append(f"- folds ranked: `{stability['folds']}`")
    lines.append(f"- distinct top-3 sets: `{stability['distinct_top_k_sets']}`")
    lines.append(
        f"- modal top-3 set: `{stability['modal_top_k_set']}` in "
        f"`{stability['modal_top_k_set_count']}` folds"
    )
    lines.append(f"- changes between consecutive folds: `{stability['changes_between_consecutive_folds']}`")
    lines.append(f"- members in every top-3 set: `{stability['members_in_every_top_k_set']}`")
    lines.append("")
    lines.append("| member | mean rank | median rank | top-3 folds | mean importance |")
    lines.append("| --- | --- | --- | --- | --- |")
    for member, block in sorted(stability["per_member"].items(), key=lambda item: item[1]["mean_rank"]):
        lines.append(
            f"| `{member}` | {block['mean_rank']:.2f} | {block['median_rank']:.1f} | "
            f"{block['top_3_folds']} | {block['mean_importance']:+.5f} |"
        )
    lines.append("")
    lines.append("## 4 Placebo arm")
    lines.append("")
    lines.append(f"- placebo curve: `{placebo['curve']['shape']}`, best k `{placebo['curve']['best_k']}`")
    lines.append(f"- placebo delta by k: `{placebo['curve']['delta_r2_by_k']}`")
    lines.append(f"- R2 at the best real k: `{collapse['placebo_r2_at_best_real_k']!r}`")
    lines.append(f"- no-information floor on the identical permuted labels: `{collapse['placebo_floor_r2']!r}`")
    lines.append(f"- delta over the floor: `{collapse['delta_over_the_floor']:+.4f}`")
    lines.append(
        f"- within-pipeline delta on shuffled labels: "
        f"`{collapse['placebo_within_pipeline_delta_r2']:+.4f}`"
    )
    lines.append(f"- collapsed: `{collapse['collapsed']}`")
    lines.append("")
    lines.append("## 5 Verdict")
    lines.append("")
    lines.append(f"- decision: `{verdict['decision']}`")
    for reason in verdict["reasons"]:
        lines.append(f"- {reason}")
    lines.append(f"- shots: `{summary['shots']['count']}` declared up front; every k is reported")
    lines.append("")
    lines.append("## 6 Knowledge pool")
    lines.append("")
    lines.append(f"- members ({len(pool['members'])}): `{pool['members']}`")
    lines.append(f"- {pool['rule']}")
    lines.append("")
    lines.append("## 7 Honest boundaries")
    lines.append("")
    for boundary in summary["honest_boundaries"]:
        lines.append(f"- {boundary}")
    lines.append("")
    lines.append("## 8 Reproduction")
    lines.append("")
    lines.append("```")
    lines.append(".venv/Scripts/python.exe probes/dielectric_knowledge_purity_sweep.py")
    lines.append("```")
    lines.append("")
    inputs = summary["inputs"]
    lines.append(f"- coverage table: `{inputs['coverage_table']}` sha256 `{inputs['coverage_table_sha256']}`")
    lines.append(f"- probe script: `{inputs['lever_script']}` sha256 `{inputs['lever_script_sha256']}`")
    lines.append(f"- pre-registration: `{summary['prereg']['path']}` sha256 `{summary['prereg']['sha256']}`")
    for name, path in summary["outputs"].items():  # type: ignore[union-attr]
        lines.append(f"- output `{name}`: `{path}`")
    return lines


IMPORTANCE_COLUMNS = (
    "protocol",
    "repeat",
    "fold",
    "rank",
    "member",
    "importance",
    "ranked_in_top_3",
    "ranking_rows",
    "test_rows_visible_to_ranking",
)


def write_artifacts(
    artifacts_dir: Path,
    stem: str,
    *,
    fold_rows: Sequence[Mapping[str, object]],
    repeat_rows: Sequence[Mapping[str, object]],
    prediction_rows: Sequence[Mapping[str, object]],
    importance_rows: Sequence[Mapping[str, object]],
) -> dict[str, Path]:
    outputs = {
        "folds": artifacts_dir / f"{stem}_folds.csv",
        "repeats": artifacts_dir / f"{stem}_repeats.csv",
        "predictions": artifacts_dir / f"{stem}_predictions.csv",
        "importance": artifacts_dir / f"{stem}_importance.csv",
    }
    write_csv_rows(outputs["folds"], FOLD_COLUMNS, fold_rows)
    write_csv_rows(outputs["repeats"], ("protocol", "representation", "repeat", *METRIC_NAMES), repeat_rows)
    write_csv_rows(outputs["predictions"], PREDICTION_COLUMNS, prediction_rows)
    write_csv_rows(outputs["importance"], IMPORTANCE_COLUMNS, importance_rows)
    return outputs


def run_check(
    summary_path: Path,
    report_path: Path,
    artifacts_dir: Path,
    stem: str = ARTIFACT_STEM,
) -> dict[str, bool]:
    """Recompute every derived field from the stored raw readings and compare.

    Nothing is re-fitted. The check re-derives the curve classification, the
    per-repeat deltas and signs, the placebo collapse, the verdict and the
    importance stability from the summary and the on-disk CSVs, and it
    re-renders the report. It also compares the script digest recorded in the
    summary against the script that is on disk right now, which is exactly what
    catches an artifact set that was written by an older revision of the probe.
    """

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["lever_script_sha256"] = (
        summary["inputs"]["lever_script_sha256"] == canonical_text_sha256(LEVER_PATH)
    )
    curve_schema = ("mechanism_reading", "contradicts_mechanism", "interior_peak", "shape")
    checks["summary_carries_the_curve_schema"] = all(
        key in summary["curve"] for key in curve_schema
    ) and all(key in summary["placebo"]["curve"] for key in curve_schema)
    deltas = {int(k): float(v) for k, v in summary["delta_r2_by_k"].items()}
    checks["curve"] = (
        classify_curve(deltas, k_grid=tuple(sorted(deltas))) == summary["curve"]
    )
    placebo_deltas = {
        int(k): float(v) for k, v in summary["placebo"]["delta_r2_by_k"].items()
    }
    checks["placebo_curve"] = (
        classify_curve(placebo_deltas, k_grid=tuple(sorted(placebo_deltas)))
        == summary["placebo"]["curve"]
    )
    repeat_rows = read_csv_rows(artifacts_dir / f"{stem}_repeats.csv")
    baseline = per_repeat_r2(repeat_rows, str(summary["arms"]["baseline"]))
    for key, arm in summary["arms"]["purity"].items():
        arm_repeats = per_repeat_r2(repeat_rows, str(arm))
        rebuilt = {
            str(repeat): arm_repeats[repeat] - baseline[repeat] for repeat in sorted(baseline)
        }
        checks[f"per_repeat_delta_r2[{key}]"] = rebuilt == summary["per_repeat_delta_r2"][key]
        checks[f"positive_repeats_by_k[{key}]"] = (
            sum(1 for value in rebuilt.values() if value > 0)
            == summary["positive_repeats_by_k"][key]
        )
    best_key = str(summary["curve"]["best_k"])
    collapse_rebuilt = placebo_collapse_readout(
        placebo_best_r2=float(
            summary["readings"][summary["placebo"]["arms"]["purity"][best_key]][HYBRID]["r2"]["mean"]
        ),
        placebo_floor_r2=float(
            summary["readings"][summary["placebo"]["arms"]["floor"]][HYBRID]["r2"]["mean"]
        ),
        placebo_best_delta_r2=float(placebo_deltas[int(best_key)]),
        real_baseline_r2=float(
            summary["readings"][summary["arms"]["baseline"]][HYBRID]["r2"]["mean"]
        ),
        real_best_k=int(summary["curve"]["best_k"]),
    )
    checks["placebo_collapse"] = collapse_rebuilt == summary["placebo"]["collapse"]
    checks["verdict"] = build_verdict(
        baseline_verified=bool(summary["baseline_reproduces"]["verified"]),
        reproduced_r2=float(summary["baseline_reproduces"]["reproduced_r2"]),
        curve=summary["curve"],
        positive_repeats=int(summary["positive_repeats_by_k"][best_key]),
        repeats_total=len(summary["per_repeat_delta_r2"][best_key]),
        placebo_collapse=summary["placebo"]["collapse"],
    ) == summary["verdict"]
    checks["importance_stability"] = (
        importance_stability(
            read_csv_rows(artifacts_dir / f"{stem}_importance.csv"), top_k=3
        )
        == summary["importance_stability"]
    )
    try:
        rendered = "\n".join(render_report(summary)) + "\n"
        checks["report_matches_the_summary"] = (
            report_path.read_text(encoding="utf-8") == rendered
        )
    except (KeyError, TypeError):
        # A summary written by an older revision can be missing a key the
        # renderer needs. That is a failure of this check, not an exception.
        checks["report_matches_the_summary"] = False
    checks["guards_passed"] = bool(summary["main_scoreboard"]["guards_passed"])
    checks["curve_contradiction_is_the_complement_of_the_interior_peak"] = bool(
        summary["curve"]["contradicts_mechanism"]
    ) is (not bool(summary["curve"]["interior_peak"]))
    checks["placebo_contradiction_is_the_complement_of_the_interior_peak"] = bool(
        summary["placebo"]["curve"]["contradicts_mechanism"]
    ) is (not bool(summary["placebo"]["curve"]["interior_peak"]))
    return checks


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=N_REPEATS, help="grouped repeats")
    parser.add_argument("--seed", type=int, default=SEED, help="fold-dealing seed")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-derive every field from the stored artifacts and compare; fits nothing",
    )
    return parser.parse_args(argv)

def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _use_utf8_stdout()
    if args.check:
        checks = run_check(Path(args.summary), Path(args.report), Path(args.artifacts_dir))
        print("=== lever 9 --check: derived fields recomputed from the artifacts ===")
        for name, ok in checks.items():
            print(f"{'OK  ' if ok else 'FAIL'} {name}")
        failed = [name for name, ok in checks.items() if not ok]
        print(f"{len(checks) - len(failed)}/{len(checks)} checks passed")
        return 1 if failed else 0
    seed = int(args.seed)
    n_repeats = int(args.repeats)
    k_grid = K_GRID
    full_run = n_repeats == N_REPEATS and seed == SEED

    merged, feature_report = merge_feature_blocks()
    coverage_rows, coverage_dropped = load_coverage_table(COVERAGE_PATH, merged)
    morgan, physical, target, temperatures, groups = build_matrices(coverage_rows)
    origin = np.asarray([str(row["observation_origin"]) for row in coverage_rows])
    band = np.asarray([str(row["temperature_band"]) for row in coverage_rows])
    fixed_score = (origin == ZERO_FREQUENCY_ORIGIN) & (band == ROOM_BAND)

    smiles_values = [str(row["smiles"]) for row in coverage_rows]
    knowledge, pool_report = knowledge_feature_block(smiles_values)

    splits, executed_repeats, repeat_note = scoreboard_splits(
        groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    redeal, _, _ = scoreboard_splits(
        groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    fold_deal = {
        "splits": len(splits),
        "signature_sha256": hashlib.sha256(repr(fold_signature(splits)).encode("utf-8")).hexdigest(),
        "scored_signature_sha256": hashlib.sha256(
            repr(scored_fold_signature(splits)).encode("utf-8")
        ).hexdigest(),
        "reproduced_by_a_second_deal": bool(fold_signature(redeal) == fold_signature(splits)),
        "executed_repeats": int(executed_repeats),
        "note": repeat_note,
    }

    baseline_fold, baseline_repeat, baseline_prediction, baseline_leak = run_protocol(
        BASELINE_ARM,
        iter(splits),
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
    )
    baseline_summary = summarize_repeats(baseline_repeat)

    frozen = run_frozen_reference(
        FROZEN_ARM,
        splits,
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
        seed=seed,
    )
    purity = run_purity_arm(
        "purity",
        splits,
        morgan=morgan,
        frozen_physical=physical,
        knowledge=knowledge,
        target=target,
        temperatures=temperatures,
        groups=groups,
        k_grid=k_grid,
        seed=seed,
    )

    placebo_target, placebo_order = shuffled_target(target, seed=seed + PLACEBO_SEED_OFFSET)
    placebo_frozen = run_frozen_reference(
        PLACEBO_FROZEN_ARM,
        splits,
        morgan=morgan,
        physical=physical,
        target=placebo_target,
        temperatures=temperatures,
        groups=groups,
        seed=seed,
    )
    placebo_purity = run_purity_arm(
        "placebo_purity",
        splits,
        morgan=morgan,
        frozen_physical=physical,
        knowledge=knowledge,
        target=placebo_target,
        temperatures=temperatures,
        groups=groups,
        k_grid=k_grid,
        seed=seed,
    )
    real_floor = fold_mean_floor("dummy_mean_reference", splits, target=target)
    placebo_floor = fold_mean_floor("placebo_dummy_mean_floor", splits, target=placebo_target)

    readings: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    readings.update(baseline_summary)
    readings[FROZEN_ARM] = frozen["summary"]  # type: ignore[assignment]
    readings.update(purity["summary_by_arm"])  # type: ignore[arg-type]
    readings[PLACEBO_FROZEN_ARM] = placebo_frozen["summary"]  # type: ignore[assignment]
    readings.update(placebo_purity["summary_by_arm"])  # type: ignore[arg-type]
    readings[str(real_floor["arm"])] = real_floor["summary"]  # type: ignore[assignment]
    readings[str(placebo_floor["arm"])] = placebo_floor["summary"]  # type: ignore[assignment]

    reference = verify_reference_triple(readings, BASELINE_ARM)
    frozen_r2 = float(readings[FROZEN_ARM][HYBRID]["r2"]["mean"])
    baseline_r2 = float(readings[BASELINE_ARM][HYBRID]["r2"]["mean"])
    loop_check = {
        "frozen_block_reference_r2": frozen_r2,
        "run_protocol_baseline_r2": baseline_r2,
        "abs_difference": abs(frozen_r2 - baseline_r2),
        "agrees": abs(frozen_r2 - baseline_r2) <= 1e-12,
        "why": (
            "the purity loop has to reproduce run_protocol on the identical frozen block before "
            "any top-k reading that comes out of the loop is believed"
        ),
    }

    arm_by_k = {int(k): str(name) for k, name in purity["arm_by_k"].items()}  # type: ignore[union-attr]
    deltas = delta_curve(readings=readings, baseline_arm=BASELINE_ARM, arm_by_k=arm_by_k)
    baseline_repeats = per_repeat_r2(baseline_repeat, BASELINE_ARM)
    per_repeat_deltas: dict[int, dict[int, float]] = {}
    positive_repeats: dict[int, int] = {}
    for k, arm in sorted(arm_by_k.items()):
        arm_repeats = per_repeat_r2(purity["repeat_rows"], arm)  # type: ignore[arg-type]
        block = {
            repeat: arm_repeats[repeat] - baseline_repeats[repeat]
            for repeat in sorted(baseline_repeats)
        }
        per_repeat_deltas[k] = block
        positive_repeats[k] = sum(1 for value in block.values() if value > 0)
    curve = classify_curve(deltas, k_grid=k_grid)
    stability = importance_stability(purity["importance_rows"], top_k=3)  # type: ignore[arg-type]

    placebo_arm_by_k = {
        int(k): str(name) for k, name in placebo_purity["arm_by_k"].items()  # type: ignore[union-attr]
    }
    placebo_deltas = delta_curve(
        readings=readings, baseline_arm=PLACEBO_FROZEN_ARM, arm_by_k=placebo_arm_by_k
    )
    placebo_curve = classify_curve(placebo_deltas, k_grid=k_grid)
    best_k = int(curve["best_k"])
    placebo_collapse = placebo_collapse_readout(
        placebo_best_r2=float(readings[placebo_arm_by_k[best_k]][HYBRID]["r2"]["mean"]),
        placebo_floor_r2=float(readings[str(placebo_floor["arm"])][HYBRID]["r2"]["mean"]),
        placebo_best_delta_r2=float(placebo_deltas[best_k]),
        real_baseline_r2=baseline_r2,
        real_best_k=best_k,
    )
    placebo_block = {
        "seed": int(seed + PLACEBO_SEED_OFFSET),
        "permutation_sha256": hashlib.sha256(
            ",".join(str(index) for index in placebo_order).encode("utf-8")
        ).hexdigest(),
        "arms": {
            "frozen_reference": PLACEBO_FROZEN_ARM,
            "purity": {str(k): arm for k, arm in sorted(placebo_arm_by_k.items())},
            "floor": str(placebo_floor["arm"]),
        },
        "delta_r2_by_k": {str(k): float(value) for k, value in sorted(placebo_deltas.items())},
        "curve": placebo_curve,
        "collapse": placebo_collapse,
        "why": (
            "the same top-k pipeline on shuffled labels must manufacture nothing; it is the "
            "placebo that separates a real purity effect from the pipeline's own variance"
        ),
    }

    verdict = build_verdict(
        baseline_verified=bool(reference["verified"]),
        reproduced_r2=float(reference["reproduced_r2"]),
        curve=curve,
        positive_repeats=positive_repeats[best_k],
        repeats_total=len(per_repeat_deltas[best_k]),
        placebo_collapse=placebo_collapse,
    )

    scored_rows_value = int(fixed_score.sum())
    scored_compounds_value = len(set(np.asarray(groups)[fixed_score].tolist()))
    importance_leak_free = all(
        int(str(row["test_rows_visible_to_ranking"])) == 0
        for row in purity["importance_rows"]  # type: ignore[union-attr]
    )
    checks: dict[str, bool] = {
        "scored_rows": scored_rows_value == SCOREBOARD_ROWS,
        "scored_compounds": scored_compounds_value == SCOREBOARD_COMPOUNDS,
        "splits_per_repeat": len(splits) == N_SPLITS * executed_repeats,
        "k_grid_is_the_frozen_grid": tuple(k_grid) == K_GRID,
        "shots_is_the_frozen_count": SHOTS_THIS_LEVER == len(K_GRID),
        "fold_deal_reproduced": bool(fold_deal["reproduced_by_a_second_deal"]),
        "loop_matches_run_protocol": bool(loop_check["agrees"]),
        "ranking_never_saw_a_test_row": bool(importance_leak_free),
        "run_protocol_reported_no_straddling_compound": bool(
            int(baseline_leak["folds_with_a_straddling_compound"]) == 0
        ),
    }
    if full_run:
        checks["reference_verified"] = bool(reference["verified"])
    guards = {
        "checks": checks,
        "scored_rows_value": scored_rows_value,
        "scored_compounds_value": scored_compounds_value,
        "full_run_configuration": bool(full_run),
        "importance_rows_scope": "the fold's training rows only, checked on every fold",
    }

    inputs = {
        "coverage_table": portable_relative_path(COVERAGE_PATH, root=REPOSITORY_ROOT),
        "coverage_table_sha256": canonical_text_sha256(COVERAGE_PATH),
        "rows_loaded": len(coverage_rows),
        "scored_rows": scored_rows_value,
        "scored_compounds": scored_compounds_value,
        "lever_script": portable_relative_path(LEVER_PATH, root=REPOSITORY_ROOT),
        "lever_script_sha256": canonical_text_sha256(LEVER_PATH),
        "prereg_path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
        "prereg_sha256": canonical_text_sha256(PREREG_PATH),
    }
    summary = build_summary(
        seed=seed,
        n_repeats=n_repeats,
        executed_repeats=executed_repeats,
        repeat_note=repeat_note,
        k_grid=k_grid,
        baseline_arm=BASELINE_ARM,
        frozen_arm=FROZEN_ARM,
        purity_arm_by_k=arm_by_k,
        readings=readings,
        reference=reference,
        loop_check=loop_check,
        curve=curve,
        per_repeat_deltas=per_repeat_deltas,
        positive_repeats=positive_repeats,
        stability=stability,
        placebo=placebo_block,
        floors={
            str(real_floor["arm"]): readings[str(real_floor["arm"])][HYBRID],
            str(placebo_floor["arm"]): readings[str(placebo_floor["arm"])][HYBRID],
        },
        verdict=verdict,
        guards=guards,
        fold_deal=fold_deal,
        pool_report=pool_report,
        feature_report=feature_report,
        coverage_dropped=coverage_dropped,
        inputs=inputs,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    outputs = write_artifacts(
        Path(args.artifacts_dir),
        ARTIFACT_STEM,
        fold_rows=[
            *baseline_fold,
            *frozen["fold_rows"],  # type: ignore[misc]
            *purity["fold_rows"],  # type: ignore[misc]
            *placebo_frozen["fold_rows"],  # type: ignore[misc]
            *placebo_purity["fold_rows"],  # type: ignore[misc]
            *real_floor["fold_rows"],  # type: ignore[misc]
            *placebo_floor["fold_rows"],  # type: ignore[misc]
        ],
        repeat_rows=[
            *baseline_repeat,
            *frozen["repeat_rows"],  # type: ignore[misc]
            *purity["repeat_rows"],  # type: ignore[misc]
            *placebo_frozen["repeat_rows"],  # type: ignore[misc]
            *placebo_purity["repeat_rows"],  # type: ignore[misc]
            *real_floor["repeat_rows"],  # type: ignore[misc]
            *placebo_floor["repeat_rows"],  # type: ignore[misc]
        ],
        prediction_rows=[
            *baseline_prediction,
            *frozen["prediction_rows"],  # type: ignore[misc]
            *purity["prediction_rows"],  # type: ignore[misc]
            *placebo_frozen["prediction_rows"],  # type: ignore[misc]
            *placebo_purity["prediction_rows"],  # type: ignore[misc]
        ],
        importance_rows=purity["importance_rows"],  # type: ignore[arg-type]
    )
    summary["outputs"] = {
        "summary": portable_relative_path(Path(args.summary), root=REPOSITORY_ROOT),
        "report": portable_relative_path(Path(args.report), root=REPOSITORY_ROOT),
        **{
            name: portable_relative_path(path, root=REPOSITORY_ROOT)
            for name, path in outputs.items()
        },
    }
    if not summary["main_scoreboard"]["guards_passed"]:
        raise ValueError(f"the main scoreboard moved: {summary['main_scoreboard']['guards']}")

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "\n".join(render_report(summary)) + "\n", encoding="utf-8", newline="\n"
    )

    print("=== lever 9: knowledge purity sweep ===")
    print(f"baseline reproduced R2 : {reference['reproduced_r2']!r}")
    print(f"published R2           : {REFERENCE_R2!r}")
    print(f"loop vs run_protocol   : {loop_check['abs_difference']!r} (agrees {loop_check['agrees']})")
    for k in curve["k_grid"]:
        key = str(k)
        print(
            f"k={k:<2d} delta R2          : {curve['delta_r2_by_k'][key]:+.6f} "
            f"({positive_repeats[k]}/{len(per_repeat_deltas[k])} positive)"
        )
    print(f"curve shape            : {curve['shape']}")
    print(f"placebo collapsed      : {placebo_collapse['collapsed']}")
    print(f"decision               : {verdict['decision']}")
    print()
    print("summary : " + str(summary["outputs"]["summary"]))
    print("report  : " + str(summary["outputs"]["report"]))
    for name, path in outputs.items():
        print(f"{name:12s}: {portable_relative_path(path, root=REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())