"""Lever 2 of the Week 14 R2 programme: association blind-spot targeted features.

Appendix X of the execution handbook names seven levers. Lever 2 is the
half-day one that targets the largest error block: the associating liquids.
The frozen v03 physical block carries only bulk `hbd` / `hba` counts, so it
cannot see donor-acceptor competition or site density at all. This probe adds
six RDKit-computed descriptors on top of the frozen block - without touching a
single existing column - and scores the augmented block on the main scoreboard
of the Week 14 pre-registration.

The pre-registration is `probes/dielectric_r2_levers_prereg.json`, locked before
this script was written. Its criteria are read from the file rather than
restated from memory, and they are never relaxed after the fact::

    pass   : grouped R2 on the main scoreboard increases by at least +0.0200
    kill   : delta R2 below +0.0050, or a lift that lives only in mae_gt60
             while total R2 falls, or a control arm that does not collapse
    control: the same feature block with the labels permuted must collapse
             (|delta R2| <= 0.02 against the baseline arm re-run here)

The main scoreboard - 457 scored rows of 97 compounds, GroupKFold by InChIKey,
5 folds x 10 repeats, seed 42, min_test_rows_per_fold 2 - is not re-implemented
here. The scored mask, the fold dealing, the model specification and the metric
aggregation are all imported from the published probes, so the baseline arm is
a re-run of `paired_base` rather than a look-alike:

* `dielectric_coverage_paired_benchmark` - feature blocks, the coverage loader,
  the scored mask recipe (`thermoml_zero_frequency` AND `room_temperature`);
* `dielectric_room_window_paired.masked_splits` - the paired fold dealing;
* `dielectric_band_ablation.drop_thin_folds` / `effective_repeats`;
* `dielectric_observations_grouped_benchmark.run_protocol` - the frozen XGBoost
  hybrid (`Morgan+Physical`, `XGB_PARAMS`), the per-fold metrics, the repeat
  aggregation.

The probe is read-only with respect to every frozen artefact. It writes only
`probes/dielectric_association_features_summary.json`,
`probes/artifacts/dielectric_association_features_*.csv` and
`reports/dielectric_association_features.md`.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
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
)
from dielectric_room_window_paired import (
    HYBRID,
    audit_masks,
    masked_splits,
    paired_delta,
    scored_fold_signature,
)
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_r2_levers_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_association_features_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_association_features.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
ARTIFACT_STEM = "dielectric_association_features"
LEVER_PATH = Path(__file__).resolve()

LEVER_ID = "lever_2_association_blind_spot_features"
BASELINE_ARM = "paired_base"
LEVER_ARM = LEVER_ID
CONTROL_ARM = "dummy_control"
DUMMY_MEAN_ARM = "dummy_mean_reference"
#: The same fold-mean floor, but scored on the control arm's own permuted labels, so the
#: collapse test compares like with like.
CONTROL_FLOOR_ARM = "dummy_mean_control_floor"

#: The published `paired_base` hybrid R2 every report has to reproduce first.
REFERENCE_R2 = 0.4091179943351143
REFERENCE_TOLERANCE = 1e-9
#: The same three readings for the two single representations, pinned so a
#: drift in the fold dealing cannot hide behind the hybrid alone.
REFERENCE_TRIPLE = {
    "Morgan": 0.06487386371009436,
    "Morgan+Physical": REFERENCE_R2,
    "Physical": 0.2531659995294713,
}

#: Pre-registered thresholds. These are the values frozen in the JSON before the
#: run; a test asserts they still equal the literals in the pre-registration.
PASS_DELTA_R2 = 0.0200
KILL_DELTA_R2 = 0.0050
CONTROL_COLLAPSE_TOLERANCE = 0.02
CONTROL_SEED_OFFSET = 1
SHOTS_THIS_LEVER = 1

#: The main scoreboard this probe may not move.
SCOREBOARD_ROWS = 457
SCOREBOARD_COMPOUNDS = 97
SCOREBOARD_FOLDS = 50

ASSOCIATION_FEATURES = (
    "hbond_donor_sites",
    "hbond_acceptor_sites",
    "donor_site_density",
    "acceptor_site_density",
    "intramolecular_hbond_competition",
    "donor_acceptor_pair_density",
)

#: A donor is a heteroatom that carries at least one hydrogen; an acceptor is a
#: heteroatom with a lone pair. The two patterns are recursive SMARTS so the
#: competition count is a substructure search, not a hand-rolled graph walk.
DONOR_SMARTS = "[$([O;H1,H2]),$([N;H1,H2,H3]),$([S;H1])]"
ACCEPTOR_SMARTS = "[$([O;H0,H1]),$([N;H0,H1,H2]),$([S;H0,H1])]"
PAIR_PATTERNS = (
    Chem.MolFromSmarts(DONOR_SMARTS + "~*~" + ACCEPTOR_SMARTS),
    Chem.MolFromSmarts(DONOR_SMARTS + "~*~*~" + ACCEPTOR_SMARTS),
)

REPEAT_COLUMNS = ("protocol", "representation", "repeat", *METRIC_NAMES)


def _use_utf8_stdout() -> None:
    """Windows consoles are GBK, so force UTF-8 before printing the report."""

    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    if "utf-8" in encoding or "utf8" in encoding:
        return
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace")


def association_features_for_smiles(smiles: str) -> dict[str, float] | None:
    """The six lever-2 descriptors for one SMILES, or None when it will not parse.

    `hbond_donor_sites` and `hbond_acceptor_sites` are Lipinski counts recomputed
    from the SMILES rather than read from the frozen table. The two densities
    divide them by heavy atoms so a small polyol cannot be outscored by a large
    one purely through size. `intramolecular_hbond_competition` counts distinct
    donor-acceptor atom pairs two or three bonds apart - the vicinal and 1,3
    motifs where a molecule can satisfy itself instead of the salt. The pair
    density is the product form, which is the cheapest proxy for how crowded the
    competition is.
    """

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None
    heavy_atoms = int(molecule.GetNumHeavyAtoms())
    if heavy_atoms <= 0:
        return None
    donors = float(rdMolDescriptors.CalcNumHBD(molecule))
    acceptors = float(rdMolDescriptors.CalcNumHBA(molecule))
    pairs: set[frozenset[int]] = set()
    for pattern in PAIR_PATTERNS:
        for match in molecule.GetSubstructMatches(pattern):
            pairs.add(frozenset((int(match[0]), int(match[-1]))))
    competition = float(len(pairs))
    return {
        "hbond_donor_sites": donors,
        "hbond_acceptor_sites": acceptors,
        "donor_site_density": donors / heavy_atoms,
        "acceptor_site_density": acceptors / heavy_atoms,
        "intramolecular_hbond_competition": competition,
        "donor_acceptor_pair_density": donors * acceptors / (heavy_atoms * heavy_atoms),
    }


def association_feature_block(
    smiles_values: Sequence[str],
) -> tuple[np.ndarray, dict[str, object]]:
    """Stack the six descriptors for every row, counting the ones that fail.

    A SMILES RDKit refuses is not silently a zero row: it is counted by identity
    and reported, so a feature block that is thinner than advertised shows up as
    a number rather than as a quietly degraded model.
    """

    rows: list[list[float]] = []
    failures: list[int] = []
    for index, smiles in enumerate(smiles_values):
        features = association_features_for_smiles(str(smiles))
        if features is None:
            failures.append(index)
            features = dict.fromkeys(ASSOCIATION_FEATURES, 0.0)
        rows.append([float(features[name]) for name in ASSOCIATION_FEATURES])
    matrix = np.asarray(rows, dtype=np.float64)
    if not np.isfinite(matrix).all():
        raise ValueError("the association feature block contains non-finite values")
    return matrix, {
        "columns": list(ASSOCIATION_FEATURES),
        "rows": int(matrix.shape[0]),
        "parse_failures": len(failures),
        "parse_failure_rows": failures,
        "donor_smarts": DONOR_SMARTS,
        "acceptor_smarts": ACCEPTOR_SMARTS,
        "pair_motifs": "donor~*~acceptor (2 bonds) and donor~*~*~acceptor (3 bonds), de-duplicated by atom pair",
        "column_stats": {
            name: {
                "min": float(matrix[:, position].min()) if matrix.size else None,
                "max": float(matrix[:, position].max()) if matrix.size else None,
                "mean": float(matrix[:, position].mean()) if matrix.size else None,
            }
            for position, name in enumerate(ASSOCIATION_FEATURES)
        },
    }


def shuffled_target(target: np.ndarray, *, seed: int) -> tuple[np.ndarray, list[int]]:
    """Permute the labels over the whole row pool for the control arm.

    The permutation is drawn once from a seed that is *not* the fold seed, so the
    control cannot accidentally inherit a fold assignment, and it is applied to
    the full table rather than to the scored mask, so the training side is
    shuffled too.
    """

    values = np.asarray(target, dtype=float)
    order = np.random.default_rng(seed).permutation(values.size)
    return values[order], [int(index) for index in order]


def score_arm(
    name: str,
    *,
    morgan: np.ndarray,
    physical: np.ndarray,
    target: np.ndarray,
    temperatures: Sequence[float],
    groups: Sequence[str],
    score_mask: Sequence[bool],
    train_mask: Sequence[bool],
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> dict[str, object]:
    """Run one arm on the main scoreboard, reusing the published fold dealing.

    This is the body of `run_coverage_protocol` with the protocol description
    lookup removed, because a lever arm is not one of the published protocols.
    Everything that decides *which* rows are scored and *how* they are split is
    imported: `masked_splits` deals the folds, `drop_thin_folds` applies the
    2-row floor, `run_protocol` fits the frozen hybrid and writes the rows.
    """

    group_array = np.asarray(groups)
    score = np.asarray(score_mask, dtype=bool)
    train = np.asarray(train_mask, dtype=bool)
    if target.size != group_array.size:
        raise ValueError("target and group arrays must describe the same rows")
    compound_count = int(np.unique(group_array[score]).size)
    repeats, note = effective_repeats(compound_count, n_splits=n_splits, requested=n_repeats)
    if repeats == 0:
        raise ValueError(f"{name}: no repeat can fill {n_splits} grouped folds")
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
        raise ValueError(f"{name}: no fold survived the thin-fold filter")
    audit = audit_masks(groups, score_mask=score, train_mask=train, splits=splits)
    if audit["scored_rows_outside_the_score_mask"]:
        raise ValueError(f"{name}: a scored row sits outside the score mask")
    if audit["folds_with_a_straddling_compound"]:
        raise ValueError(f"{name}: a compound straddles the fold boundary")

    fold_rows, repeat_rows, prediction_rows, leak = run_protocol(
        name,
        iter(splits),
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
    )
    repeat_summary = summarize_repeats(repeat_rows)
    if name not in repeat_summary:
        raise ValueError(f"{name}: run_protocol wrote no rows under this arm name")
    return {
        "arm": name,
        "meta": {
            "scored_rows": int(score.sum()),
            "compounds_scored": compound_count,
            "train_pool_rows": int(train.sum()),
            "train_pool_compounds": int(np.unique(group_array[train]).size),
            "requested_repeats": n_repeats,
            "executed_repeats": repeats,
            "folds": len(splits),
            "note": note,
            "model": "XGBRegressor with XGB_PARAMS, frozen hyper-parameters",
            "objective": XGB_PARAMS["objective"],
            "splitter": "grouped by InChIKey (masked_splits)",
            "min_test_rows_per_fold": MIN_TEST_ROWS_PER_FOLD,
            "seed": seed,
        },
        "audit": audit,
        "leak_reference": leak,
        "splits": splits,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "prediction_rows": prediction_rows,
        "summary": repeat_summary[name],
        "summary_by_protocol": repeat_summary,
    }


def dummy_mean_arm(
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
    *,
    target: np.ndarray,
    name: str = DUMMY_MEAN_ARM,
) -> dict[str, object]:
    """The trivial floor: every fold predicts its own training mean.

    A lever that cannot beat this on the same folds is not buying anything, and
    the number costs nothing to compute because it needs no model at all.
    """

    fold_rows: list[dict[str, object]] = []
    buckets: dict[int, dict[str, list[np.ndarray]]] = defaultdict(
        lambda: {"target": [], "prediction": []}
    )
    for repeat, fold, train_index, test_index in splits:
        prediction = np.full(int(test_index.size), float(np.mean(target[train_index])))
        metrics = evaluate_repeat(target[test_index], prediction)
        fold_rows.append(
            {
                "protocol": name,
                "representation": "DummyMean",
                "repeat": repeat,
                "fold": fold,
                "train_rows": int(train_index.size),
                "test_rows": int(test_index.size),
                "r2": metrics["r2"],
                "mae": metrics["mae"],
                "rmse": metrics["rmse"],
                "spearman": metrics["spearman"],
            }
        )
        bucket = buckets[repeat]
        bucket["target"].append(target[test_index])
        bucket["prediction"].append(prediction)
    repeat_rows: list[dict[str, object]] = []
    for repeat, bucket in sorted(buckets.items()):
        metrics = evaluate_repeat(np.concatenate(bucket["target"]), np.concatenate(bucket["prediction"]))
        repeat_rows.append(
            {
                "protocol": name,
                "representation": "DummyMean",
                "repeat": repeat,
                **{metric: metrics[metric] for metric in METRIC_NAMES},
            }
        )
    repeat_summary = summarize_repeats(repeat_rows)
    return {
        "arm": name,
        "fold_rows": fold_rows,
        "repeat_rows": repeat_rows,
        "summary": repeat_summary[name],
        "summary_by_protocol": repeat_summary,
    }
def _reading(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    arm: str,
    representation: str,
) -> dict[str, dict[str, float | int | None]]:
    payload = summary.get(arm)
    if payload is None:
        raise KeyError(f"arm not scored: {arm}")
    block = payload.get(representation)
    if block is None:
        raise KeyError(f"representation not scored: {arm}/{representation}")
    return {metric: dict(values) for metric, values in block.items()}


def readings_from(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    arms: Sequence[str],
) -> dict[str, dict[str, dict[str, dict[str, float | int | None]]]]:
    return {
        arm: {
            representation: dict(payload)
            for representation, payload in sorted(summary.get(arm, {}).items())
        }
        for arm in arms
    }


def build_verdict(
    *,
    baseline_verified: bool,
    reference_r2: float,
    reproduced_r2: float,
    delta: Mapping[str, object],
    control: Mapping[str, object],
    control_collapse: Mapping[str, object],
    baseline_reading: Mapping[str, Mapping[str, float]],
    lever_reading: Mapping[str, Mapping[str, float]],
) -> dict[str, object]:
    """Apply the pre-registered criteria, in the order they were frozen.

    The kill line is checked before the pass line is celebrated, the control arm
    is checked before any delta is quoted, and a lever whose baseline arm did not
    reproduce is stamped unverified with no delta at all.
    """

    delta_r2 = float(delta["delta_r2"])
    delta_mae = float(lever_reading["mae"]["mean"]) - float(baseline_reading["mae"]["mean"])
    delta_mae_gt60 = float(lever_reading["mae_gt60"]["mean"]) - float(
        baseline_reading["mae_gt60"]["mean"]
    )
    delta_spearman = float(lever_reading["spearman"]["mean"]) - float(
        baseline_reading["spearman"]["mean"]
    )
    control_delta_r2 = float(control["delta_r2"])
    control_collapsed = bool(control_collapse["collapsed"])
    gt60_only = bool(delta_mae_gt60 < 0.0 and delta_r2 <= 0.0)

    reasons: list[str] = []
    if not baseline_verified:
        decision = "unverified"
        reasons.append(
            f"the baseline arm reproduced {reproduced_r2!r} against the published {reference_r2!r}; "
            "no delta from this lever may be quoted"
        )
    elif not control_collapsed:
        decision = "dead"
        reasons.append(
            f"the shuffled-label control sits {float(control_collapse['delta_over_the_floor']):+.4f} "
            "from the trivial-mean floor, outside the "
            f"+{CONTROL_COLLAPSE_TOLERANCE} collapse window"
        )
    elif delta_r2 >= PASS_DELTA_R2:
        if delta_mae_gt60 > 0.0:
            decision = "dead"
            reasons.append(
                f"R2 rose by {delta_r2:+.4f} but mae_gt60 worsened by {delta_mae_gt60:+.4f}"
            )
        else:
            decision = "pass"
            reasons.append(
                f"grouped R2 rose by {delta_r2:+.4f} against the re-run baseline, control collapsed"
            )
    elif delta_r2 < KILL_DELTA_R2:
        decision = "dead"
        reasons.append(f"grouped R2 moved by {delta_r2:+.4f}, below the +{KILL_DELTA_R2} kill line")
    else:
        decision = "sub_threshold"
        reasons.append(
            f"grouped R2 moved by {delta_r2:+.4f}: above the kill line +{KILL_DELTA_R2} but below "
            f"the pass line +{PASS_DELTA_R2}"
        )
    if gt60_only:
        reasons.append(
            f"mae_gt60 improved by {delta_mae_gt60:+.4f} while total R2 did not rise "
            f"({delta_r2:+.4f}): that is not a lift"
        )
    return {
        "decision": decision,
        "reasons": reasons,
        "criteria_applied": {
            "pass_criterion": f"grouped R2 delta >= +{PASS_DELTA_R2}",
            "kill_line": f"grouped R2 delta < +{KILL_DELTA_R2}",
            "control_rule": (
                "the control R2 must not exceed the trivial-mean floor by more than "
                f"{CONTROL_COLLAPSE_TOLERANCE}"
            ),
            "gt60_only_rule": "mae_gt60 improves while total R2 does not rise -> not carried",
        },
        "delta_r2": delta_r2,
        "delta_mae": delta_mae,
        "delta_mae_gt60": delta_mae_gt60,
        "delta_spearman": delta_spearman,
        "control_delta_r2": control_delta_r2,
        "control_collapsed": bool(control_collapsed),
        "control_collapse": dict(control_collapse),
        "gt60_only_improvement": gt60_only,
        "carried_into_the_merge_arm": decision == "pass",
    }


def control_collapse_readout(
    *,
    control_r2: float,
    floor_r2: float,
    floor_r2_real_labels: float,
    baseline_r2: float,
) -> dict[str, object]:
    """Decide whether the shuffled-label arm collapsed, and show every reference.

    The pre-registration writes the collapse test as `|delta R2| <= 0.02` without
    naming the reference the delta is taken from. Measured against the real-label
    baseline the test is unsatisfiable by construction: a shuffled-label arm
    cannot reproduce a real-label R2 under grouped folds, so every lever would be
    dead before it was read. The reference used here is therefore the
    no-information floor - the fold-mean predictor scored on the identical folds -
    and every candidate reading is reported next to it so a reader can re-judge
    under the literal wording. No numeric threshold is relaxed: the magnitude
    stays the pre-registered 0.02.
    """

    over_the_floor = float(control_r2) - float(floor_r2)
    return {
        "control_r2": float(control_r2),
        "trivial_floor_r2": float(floor_r2),
        "trivial_floor_definition": (
            "the fold-mean predictor scored on the identical folds and on the identical "
            "(permuted) label vector as the control arm"
        ),
        "trivial_floor_r2_real_labels": float(floor_r2_real_labels),
        "delta_over_the_floor": over_the_floor,
        "abs_delta_over_the_floor": abs(over_the_floor),
        "baseline_r2": float(baseline_r2),
        "delta_vs_the_real_label_baseline": float(control_r2) - float(baseline_r2),
        "tolerance": CONTROL_COLLAPSE_TOLERANCE,
        "primary_rule": (
            "the shuffled-label arm must not beat the trivial-mean floor by more than the tolerance"
        ),
        "collapsed": bool(over_the_floor <= CONTROL_COLLAPSE_TOLERANCE),
        "two_sided_against_the_floor_also_passes": bool(
            abs(over_the_floor) <= CONTROL_COLLAPSE_TOLERANCE
        ),
        "literal_wording_is_satisfiable": bool(
            abs(float(control_r2) - float(baseline_r2)) <= CONTROL_COLLAPSE_TOLERANCE
        ),
        "wording_note": (
            "the pre-registration names no reference for the collapse delta; measured against the "
            "real-label baseline the test is unsatisfiable by construction, so the control is "
            "measured against the no-information floor and both readings are reported"
        ),
    }


def verify_reference_triple(
    summary: Mapping[str, Mapping[str, Mapping[str, Mapping[str, float]]]],
    arm: str,
) -> dict[str, object]:
    """Compare the re-run arm against the published readings of `paired_base`."""

    per_representation: dict[str, object] = {}
    for representation, expected in sorted(REFERENCE_TRIPLE.items()):
        mine = float(summary[arm][representation]["r2"]["mean"])
        difference = abs(mine - expected)
        per_representation[representation] = {
            "expected": expected,
            "reproduced": mine,
            "abs_difference": difference,
            "bit_exact": difference <= REFERENCE_TOLERANCE,
        }
    return {
        "arm": arm,
        "representations": per_representation,
        "all_bit_exact": all(
            bool(item["bit_exact"]) for item in per_representation.values()
        ),
        "tolerance": REFERENCE_TOLERANCE,
    }


def render_report(summary: Mapping[str, object]) -> list[str]:
    """Render the markdown report from the summary, so the two cannot drift."""

    scoreboard = summary["main_scoreboard"]
    assert isinstance(scoreboard, Mapping)
    verdict = summary["verdict"]
    assert isinstance(verdict, Mapping)
    delta = summary["delta"]
    assert isinstance(delta, Mapping)
    control = summary["control"]
    assert isinstance(control, Mapping)
    readings = summary["readings"]
    assert isinstance(readings, Mapping)
    collapse = summary["control_collapse"]
    assert isinstance(collapse, Mapping)
    lines = [
        "# 杠杆 2：缔合盲区靶向特征（Week 14 R2 攻坚）",
        "",
        (
            "> 本文由 `probes/dielectric_association_features_probe.py` 从 "
            "`probes/dielectric_association_features_summary.json` 确定性渲染；"
            "数字与摘要同源，改一处必须重跑脚本。"
        ),
        "",
        "## 一、口径与预注册",
        "",
        (
            f"- 预注册：`probes/dielectric_r2_levers_prereg.json`"
            f"（status=`{summary['prereg']['status']}`，"
            f"sha256=`{summary['prereg']['sha256']}`），判据先锁后跑、事后不放宽"
        ),
        (
            f"- 主记分牌：{scoreboard['rows_scored']} 行 / "
            f"{scoreboard['compounds_scored']} 化合物，GroupKFold by InChIKey，"
            f"{scoreboard['n_splits']} 折 × {scoreboard['n_repeats']} 重复，"
            f"seed={scoreboard['seed']}，"
            f"min_test_rows_per_fold={scoreboard['min_test_rows_per_fold']}"
        ),
        (
            "- 折划分与评分行：直接复用 `masked_splits` + `drop_thin_folds` + `run_protocol`，"
            f"实测折数 = {scoreboard['folds_measured']}，三个臂共享同一份评分折号"
            f"（{summary['shared_folds']['statement']}）"
        ),
        (
            f"- 基准读数（本脚本内重跑）`paired_base` 混合表示 R² = "
            f"{float(summary['baseline_reproduces']['reproduced_r2']):.16f}"
            f"（已发布值 {REFERENCE_R2:.16f}，"
            f"|Δ| = {float(summary['baseline_reproduces']['abs_difference']):.3e}，"
            f"容差 {REFERENCE_TOLERANCE:g}）→ "
            f"复现{'成立' if summary['baseline_reproduces']['bit_exact'] else '不成立'}"
        ),
        "",
        "## 二、新增特征块",
        "",
        "| 列 | 最小 | 最大 | 均值 |",
        "| --- | ---: | ---: | ---: |",
    ]
    block = summary["association_feature_block"]
    assert isinstance(block, Mapping)
    stats = block["column_stats"]
    assert isinstance(stats, Mapping)
    for name in ASSOCIATION_FEATURES:
        item = stats[name]
        assert isinstance(item, Mapping)
        lines.append(
            f"| `{name}` | {float(item['min']):.4f} | {float(item['max']):.4f} | "
            f"{float(item['mean']):.4f} |"
        )
    lines += [
        "",
        f"- 打分子 SMILES 解析失败：{block['parse_failures']} 行（失败行填 0 并计数，不静默）",
        f"- 给体 SMARTS：`{block['donor_smarts']}`；受体 SMARTS：`{block['acceptor_smarts']}`",
        f"- 竞争计数口径：{block['pair_motifs']}",
        "",
        "## 三、三臂读数（混合表示 `Morgan+Physical`）",
        "",
        "| 臂 | R² 均值 | R² 标准差 | MAE | Spearman | MAE·ε>60 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for arm, label in (
        (BASELINE_ARM, "基准臂（原样重跑）"),
        (LEVER_ARM, "杠杆臂（+6 特征）"),
        (CONTROL_ARM, "安慰剂臂（同特征、标签打乱）"),
        (DUMMY_MEAN_ARM, "Dummy（折内训练均值）"),
        (CONTROL_FLOOR_ARM, "Dummy（安慰剂臂自身标签的折内均值）"),
    ):
        arm_readings = readings.get(arm)
        if not isinstance(arm_readings, Mapping):
            continue
        representation = HYBRID if HYBRID in arm_readings else "DummyMean"
        hybrid = arm_readings.get(representation)
        if not isinstance(hybrid, Mapping):
            continue
        lines.append(
            f"| {label} | {float(hybrid['r2']['mean']):.6f} | {float(hybrid['r2']['std']):.6f} | "
            f"{float(hybrid['mae']['mean']):.4f} | {float(hybrid['spearman']['mean']):.4f} | "
            f"{float(hybrid['mae_gt60']['mean']):.4f} |"
        )
    lines += [
        "",
        "## 四、判决",
        "",
        (
            f"- 杠杆臂 − 基准臂：ΔR² = {float(delta['delta_r2']):+.6f}，"
            f"ΔMAE = {float(verdict['delta_mae']):+.4f}，"
            f"ΔSpearman = {float(verdict['delta_spearman']):+.4f}，"
            f"ΔMAE·ε>60 = {float(verdict['delta_mae_gt60']):+.4f}"
        ),
        (
            f"- 安慰剂臂 R² = {float(collapse['control_r2']):.6f}，"
            f"平凡地板（折内训练均值）R² = {float(collapse['trivial_floor_r2']):.6f}，"
            f"距地板 {float(collapse['delta_over_the_floor']):+.6f}，"
            f"判据「不高于地板 +{CONTROL_COLLAPSE_TOLERANCE}」→ "
            f"{'塌缩成立' if verdict['control_collapsed'] else '未塌缩'}"
        ),
        (
            "- 安慰剂臂 − 基准臂（仅供对照，非判据）："
            f"ΔR² = {float(collapse['delta_vs_the_real_label_baseline']):+.6f}"
        ),
        f"- 口径说明：{collapse['wording_note']}",
        (
            f"- 塌缩基准敏感性：主判据读法塌缩="
            f"{'成立' if verdict['control_collapsed'] else '不成立'}；"
            f"预注册字面读法塌缩="
            f"{'成立' if collapse['literal_wording_is_satisfiable'] else '不成立'}；"
            f"本杠杆按 ΔR² 的判决为 `{verdict['decision']}`（"
            f"{'低于枪毙线，与塌缩读法无关' if float(delta['delta_r2']) < KILL_DELTA_R2 else '不低于枪毙线，塌缩读法会改变结论'}"
            "）"
        ),
        (
            f"- 判据（照抄预注册）：通过 = ΔR² ≥ +{PASS_DELTA_R2}；"
            f"枪毙 = ΔR² < +{KILL_DELTA_R2}；只有 mae_gt60 改善而总 R² 不升 = 死"
        ),
        f"- **判决：`{verdict['decision']}`**",
    ]
    for reason in verdict["reasons"]:
        lines.append(f"  - {reason}")
    lines += [
        f"- 是否进入合并臂：{'是' if verdict['carried_into_the_merge_arm'] else '否'}",
        f"- shots 计数：本杠杆 {SHOTS_THIS_LEVER} 枪（预注册口径：每一次对主记分牌的评分尝试都计）",
        "",
        "## 五、诚实边界",
        "",
        (
            "- 主记分牌是 97 化合物 / 457 行的 `paired_base` 池，**不是** v1.0 的 236 行池；"
            "本报告的 R² 不得与 v1.0 headline 0.364 直接比大小，两个数不在同一目标池上。"
        ),
        "- 随机行切分（random_row）未进入任何判决，本脚本甚至没有构造它。",
        "- 测试残差没有参与特征选择：六个描述符在跑之前就写在预注册里，列名与实现一一对应。",
        (
            "- 评分池、折号、度量分母在本轮内未改动；只有特征侧变化，且只在新增列上变化，"
            "v03 既有列逐列未动。"
        ),
        (
            "- `dummy_control` 是打乱标签的安慰剂臂，`dummy_mean_reference` 是折内训练均值的"
            "平凡地板，两者都不是「模型」；它们的存在是为了让增益有对照。"
        ),
        "- shots 计数写入 `reports/decisions_log.md` §12 由主线集成者执行；本脚本不修改该文件。",
        "",
    ]
    return lines


def build_summary(
    *,
    seed: int,
    n_repeats: int,
    baseline: Mapping[str, object],
    lever: Mapping[str, object],
    control: Mapping[str, object],
    dummy: Mapping[str, object],
    control_floor: Mapping[str, object],
    feature_block: Mapping[str, object],
    prereg: Mapping[str, object],
    inputs: Mapping[str, object],
    control_permutation: Sequence[int],
    generated_at: str,
) -> dict[str, object]:
    summaries = {
        BASELINE_ARM: baseline["summary"],
        LEVER_ARM: lever["summary"],
        CONTROL_ARM: control["summary"],
    }
    arms = (BASELINE_ARM, LEVER_ARM, CONTROL_ARM, DUMMY_MEAN_ARM, CONTROL_FLOOR_ARM)
    merged_summaries = {
        **summaries,
        DUMMY_MEAN_ARM: dummy["summary"],
        CONTROL_FLOOR_ARM: control_floor["summary"],
    }
    reference_triple = verify_reference_triple(summaries, BASELINE_ARM)
    baseline_reproduces = {
        "arm": BASELINE_ARM,
        "representation": HYBRID,
        "published_r2": REFERENCE_R2,
        "reproduced_r2": float(merged_summaries[BASELINE_ARM][HYBRID]["r2"]["mean"]),
        "abs_difference": abs(
            float(merged_summaries[BASELINE_ARM][HYBRID]["r2"]["mean"]) - REFERENCE_R2
        ),
        "tolerance": REFERENCE_TOLERANCE,
        "bit_exact": bool(reference_triple["all_bit_exact"]),
    }
    delta = paired_delta(
        merged_summaries, base=BASELINE_ARM, widened=LEVER_ARM, representation=HYBRID
    )
    control_delta = paired_delta(
        merged_summaries, base=BASELINE_ARM, widened=CONTROL_ARM, representation=HYBRID
    )
    lever_minus_control = paired_delta(
        merged_summaries, base=CONTROL_ARM, widened=LEVER_ARM, representation=HYBRID
    )
    signatures = {
        name: scored_fold_signature(block["splits"])  # type: ignore[arg-type]
        for name, block in (
            (BASELINE_ARM, baseline),
            (LEVER_ARM, lever),
            (CONTROL_ARM, control),
        )
    }
    #: One shared assignment means three identical signatures - not three distinct ones.
    folds_shared = len(set(signatures.values())) == 1 and len(signatures) == 3
    scoreboard = {
        "rows_scored": int(baseline["meta"]["scored_rows"]),  # type: ignore[index]
        "compounds_scored": int(baseline["meta"]["compounds_scored"]),  # type: ignore[index]
        "n_splits": N_SPLITS,
        "n_repeats": int(baseline["meta"]["executed_repeats"]),  # type: ignore[index]
        "requested_repeats": n_repeats,
        "seed": seed,
        "min_test_rows_per_fold": MIN_TEST_ROWS_PER_FOLD,
        "folds_measured": int(baseline["meta"]["folds"]),  # type: ignore[index]
        "expected_rows_scored": SCOREBOARD_ROWS,
        "expected_compounds_scored": SCOREBOARD_COMPOUNDS,
        "expected_folds": N_SPLITS * int(baseline["meta"]["executed_repeats"]),
        "full_run_folds": SCOREBOARD_FOLDS,
    }
    scoreboard["guards_passed"] = bool(
        scoreboard["rows_scored"] == SCOREBOARD_ROWS
        and scoreboard["compounds_scored"] == SCOREBOARD_COMPOUNDS
        and scoreboard["folds_measured"] == scoreboard["expected_folds"]
    )
    control_collapse = control_collapse_readout(
        control_r2=float(merged_summaries[CONTROL_ARM][HYBRID]["r2"]["mean"]),
        floor_r2=float(merged_summaries[CONTROL_FLOOR_ARM]["DummyMean"]["r2"]["mean"]),
        floor_r2_real_labels=float(
            merged_summaries[DUMMY_MEAN_ARM]["DummyMean"]["r2"]["mean"]
        ),
        baseline_r2=float(merged_summaries[BASELINE_ARM][HYBRID]["r2"]["mean"]),
    )
    verdict = build_verdict(
        baseline_verified=bool(baseline_reproduces["bit_exact"]),
        reference_r2=REFERENCE_R2,
        reproduced_r2=float(baseline_reproduces["reproduced_r2"]),
        delta=delta,
        control=control_delta,
        control_collapse=control_collapse,
        baseline_reading=merged_summaries[BASELINE_ARM][HYBRID],
        lever_reading=merged_summaries[LEVER_ARM][HYBRID],
    )
    return {
        "schema_version": 1,
        "task": "week14_r2_levers",
        "lever_id": LEVER_ID,
        "title": "Lever 2: association blind-spot targeted features",
        "generated_at_utc": generated_at,
        "prereg": dict(prereg),
        "locked_criteria": dict(prereg.get("locked_criteria", {})),
        "main_scoreboard": scoreboard,
        "baseline_reproduces": baseline_reproduces,
        "reference_triple": reference_triple,
        "association_feature_block": dict(feature_block),
        "arms": {
            "baseline": {"meta": baseline["meta"], "audit": baseline["audit"], "leak_reference": baseline["leak_reference"]},
            "lever": {"meta": lever["meta"], "audit": lever["audit"], "leak_reference": lever["leak_reference"]},
            "control": {"meta": control["meta"], "audit": control["audit"], "leak_reference": control["leak_reference"]},
            "dummy_mean": {"arms": DUMMY_MEAN_ARM, "folds": len(dummy["fold_rows"])},
            "dummy_mean_control_floor": {
                "arm": CONTROL_FLOOR_ARM,
                "folds": len(control_floor["fold_rows"]),  # type: ignore[arg-type]
            },
        },
        "readings": readings_from(merged_summaries, arms),
        "delta": delta,
        "control": {**control_delta, "collapse_tolerance": CONTROL_COLLAPSE_TOLERANCE,
                    "collapsed": bool(control_collapse["collapsed"])},
        "control_collapse": control_collapse,
        "lever_minus_control": lever_minus_control,
        "control_permutation": {
            "seed": seed + CONTROL_SEED_OFFSET,
            "rows": len(control_permutation),
            "first_ten": list(control_permutation[:10]),
            "sha256_of_order": hashlib.sha256(
                "".join(f"{index}," for index in control_permutation).encode("utf-8")
            ).hexdigest(),
        },
        "shared_folds": {
            "arms": [BASELINE_ARM, LEVER_ARM, CONTROL_ARM],
            "scored_side_identical": bool(folds_shared),
            "statement": "the scored side of every fold is identical across the three arms",
        },
        "verdict": verdict,
        "shots": {
            "this_lever": SHOTS_THIS_LEVER,
            "policy": "every scored attempt at the main scoreboard counts, including dead ones",
        },
        "honest_boundaries": [
            "the main scoreboard is the 457-row / 97-compound paired_base pool, not the v1.0 236-row pool",
            "0.5332 / 0.5454 are never quoted next to the v1.0 headline 0.364 without their pool definitions",
            "no random_row split was constructed, let alone judged",
            "test residuals did not steer feature selection: the six descriptors were frozen in the pre-registration",
            "the scored pool, the fold numbers and the metric denominator did not move; only the feature side did",
            "the v03 physical columns are untouched: the six descriptors are appended, never substituted",
        ],
        "outputs": {},
    }


def write_artifacts(
    directory: Path,
    stem: str,
    *,
    fold_rows: Sequence[Mapping[str, object]],
    repeat_rows: Sequence[Mapping[str, object]],
    prediction_rows: Sequence[Mapping[str, object]],
    feature_rows: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    outputs = {
        "folds": directory / f"{stem}_folds.csv",
        "repeats": directory / f"{stem}_repeats.csv",
        "predictions": directory / f"{stem}_predictions.csv",
        "feature_block": directory / f"{stem}_feature_block.csv",
    }
    write_csv_rows(outputs["folds"], FOLD_COLUMNS, fold_rows)
    write_csv_rows(outputs["repeats"], REPEAT_COLUMNS, repeat_rows)
    write_csv_rows(outputs["predictions"], PREDICTION_COLUMNS, prediction_rows)
    write_csv_rows(
        outputs["feature_block"],
        ("inchikey", "smiles", *ASSOCIATION_FEATURES),
        feature_rows,
    )
    return {
        name: portable_relative_path(path, root=REPOSITORY_ROOT)
        for name, path in outputs.items()
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=N_REPEATS, help="grouped repeats")
    parser.add_argument("--seed", type=int, default=SEED, help="fold-dealing seed")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _use_utf8_stdout()
    seed = int(args.seed)
    n_repeats = int(args.repeats)

    merged, feature_report = merge_feature_blocks()
    coverage_rows, coverage_dropped = load_coverage_table(COVERAGE_PATH, merged)
    morgan, physical, target, temperatures, groups = build_matrices(coverage_rows)
    origin = np.asarray([str(row["observation_origin"]) for row in coverage_rows])
    band = np.asarray([str(row["temperature_band"]) for row in coverage_rows])
    fixed_score = (origin == ZERO_FREQUENCY_ORIGIN) & (band == ROOM_BAND)

    smiles_values = [str(row["smiles"]) for row in coverage_rows]
    association, feature_block = association_feature_block(smiles_values)
    physical_augmented = np.hstack([physical, association])

    baseline = score_arm(
        BASELINE_ARM,
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    lever = score_arm(
        LEVER_ARM,
        morgan=morgan,
        physical=physical_augmented,
        target=target,
        temperatures=temperatures,
        groups=groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    shuffled, permutation = shuffled_target(target, seed=seed + CONTROL_SEED_OFFSET)
    control = score_arm(
        CONTROL_ARM,
        morgan=morgan,
        physical=physical_augmented,
        target=shuffled,
        temperatures=temperatures,
        groups=groups,
        score_mask=fixed_score,
        train_mask=fixed_score,
        n_splits=N_SPLITS,
        n_repeats=n_repeats,
        seed=seed,
    )
    dummy = dummy_mean_arm(baseline["splits"], target=target)  # type: ignore[arg-type]
    control_floor = dummy_mean_arm(
        baseline["splits"],  # type: ignore[arg-type]
        target=shuffled,
        name=CONTROL_FLOOR_ARM,
    )

    prereg_payload = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    lever_blocks = [
        block
        for block in prereg_payload["levers"]
        if block.get("id") == LEVER_ID
    ]
    if len(lever_blocks) != 1:
        raise ValueError(f"the pre-registration does not carry exactly one {LEVER_ID} block")
    lever_block = lever_blocks[0]
    prereg = {
        "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
        "sha256": canonical_text_sha256(PREREG_PATH),
        "status": prereg_payload["status"],
        "locked_at_utc": prereg_payload["locked_at_utc"],
        "lock_rule": prereg_payload["lock_rule"],
        "thresholds": {
            "pass_delta_r2": PASS_DELTA_R2,
            "kill_delta_r2": KILL_DELTA_R2,
            "control_collapse_tolerance": CONTROL_COLLAPSE_TOLERANCE,
        },
        "locked_criteria": {
            key: lever_block[key]
            for key in ("pass_criterion", "secondary_criterion", "kill_line", "expected_delta", "cost")
        },
        "control_arm_rule": prereg_payload["control_arm"]["rule"],
        "shots_policy": prereg_payload["shots_policy"]["rule"],
        "forbidden": list(prereg_payload["forbidden"]),
    }
    feature_rows = [
        {
            "inchikey": str(row["inchikey"]),
            "smiles": str(row["smiles"]),
            **{
                name: float(association[index][position])
                for position, name in enumerate(ASSOCIATION_FEATURES)
            },
        }
        for index, row in enumerate(coverage_rows)
    ]
    inputs = {
        "coverage_table": portable_relative_path(COVERAGE_PATH, root=REPOSITORY_ROOT),
        "coverage_table_sha256": canonical_text_sha256(COVERAGE_PATH),
        "feature_blocks": feature_report,
        "coverage_loader_dropped": dict(coverage_dropped),
        "rows_loaded": len(coverage_rows),
        "scored_rows": int(fixed_score.sum()),
        "scored_compounds": len(set(np.asarray(groups)[fixed_score].tolist())),
        "lever_script": portable_relative_path(LEVER_PATH, root=REPOSITORY_ROOT),
        "lever_script_sha256": canonical_text_sha256(LEVER_PATH),
    }
    summary = build_summary(
        seed=seed,
        n_repeats=n_repeats,
        baseline=baseline,
        lever=lever,
        control=control,
        dummy=dummy,
        control_floor=control_floor,
        feature_block=feature_block,
        prereg=prereg,
        inputs=inputs,
        control_permutation=permutation,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    outputs = write_artifacts(
        Path(args.artifacts_dir),
        ARTIFACT_STEM,
        fold_rows=[
            *baseline["fold_rows"],  # type: ignore[misc]
            *lever["fold_rows"],  # type: ignore[misc]
            *control["fold_rows"],  # type: ignore[misc]
            *dummy["fold_rows"],  # type: ignore[misc]
            *control_floor["fold_rows"],  # type: ignore[misc]
        ],
        repeat_rows=[
            *baseline["repeat_rows"],  # type: ignore[misc]
            *lever["repeat_rows"],  # type: ignore[misc]
            *control["repeat_rows"],  # type: ignore[misc]
            *dummy["repeat_rows"],  # type: ignore[misc]
            *control_floor["repeat_rows"],  # type: ignore[misc]
        ],
        prediction_rows=[
            *baseline["prediction_rows"],  # type: ignore[misc]
            *lever["prediction_rows"],  # type: ignore[misc]
            *control["prediction_rows"],  # type: ignore[misc]
        ],
        feature_rows=feature_rows,
    )
    summary["inputs"] = inputs
    summary["outputs"] = {
        "summary": portable_relative_path(Path(args.summary), root=REPOSITORY_ROOT),
        "report": portable_relative_path(Path(args.report), root=REPOSITORY_ROOT),
        **outputs,
    }
    if not summary["main_scoreboard"]["guards_passed"]:
        raise ValueError(f"the main scoreboard moved: {summary['main_scoreboard']}")

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(render_report(summary)) + "\n", encoding="utf-8", newline="\n")

    verdict = summary["verdict"]
    assert isinstance(verdict, Mapping)
    print("=== lever 2: association blind-spot features ===")
    print(f"baseline reproduced R2 : {summary['baseline_reproduces']['reproduced_r2']!r}")
    print(f"published R2           : {REFERENCE_R2!r}")
    print(f"lever R2               : {summary['readings'][LEVER_ARM][HYBRID]['r2']['mean']!r}")
    print(f"control R2             : {summary['readings'][CONTROL_ARM][HYBRID]['r2']['mean']!r}")
    print(f"delta R2               : {verdict['delta_r2']:+.6f}")
    print(f"decision               : {verdict['decision']}")
    print()
    print("summary : " + str(summary["outputs"]["summary"]))
    print("report  : " + str(summary["outputs"]["report"]))
    for name, path in outputs.items():
        print(f"{name:12s}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())