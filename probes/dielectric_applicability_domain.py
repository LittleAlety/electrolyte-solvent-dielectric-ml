"""Week 18 lane B: the applicability-domain scoreboard for the frozen epsilon headline arm.

The frozen headline is ``plus_both`` on the main scoreboard: 457 rows, 97 compounds,
276 (compound, T) pairs, GroupKFold by InChIKey, 5 folds x 10 repeats, R2
0.4766400383507876.  That number is the global reading and it is not replaced here.
This arm adds a second, pre-registered scoreboard on the same pool and the same arm:
the in-domain reading.

Why a domain at all: the verified census says seven compounds carry 48.0% of the
scoreboard label variance and all seven are self-associating protic liquids
(N-methylacetamide 178.47, formamide 106.14, 2-hydroxyethylammonium lactate 85.60,
water 80.00, ethanolammonium nitrate 60.90, triethanolamine lactate 59.70,
2-hydroxyethylammonium acetate 58.30).  None is an electrolyte-solvent candidate in
the sense this screen cares about, and under GroupKFold they leave the training side
whole, so the training labels stop around the 44th percentile of the test labels.
Declaring them out of domain is a claim about scope, not a way to move the headline.

Two rules are frozen before the first run and both are reported side by side:

* ``D1`` polar protic, feature only: NumHDonors >= 1 and TPSA >= 20 A^2, read from the
  frozen SMILES, labels never touched;
* ``D2`` the training-side p95 classifier: inside each fold the training labels are
  cut at their p95 and a logistic regression on the frozen physical block scores the
  test compounds;
* ``D3`` is a diagnostic roster, not a rule: the seven verified high-permittivity keys.

The seed-42 global reading must reproduce 0.4766400383507876 to 1e-9 or the run
raises and no in-domain number is reported at all.  Nothing here is promoted.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import dielectric_coordination_block as v1
import dielectric_coordination_block_v3 as v3
import dielectric_xtb_full_table_migration as migration
import numpy as np
from dielectric_band_ablation import MIN_TEST_ROWS_PER_FOLD, drop_thin_folds
from dielectric_representation_ablation import (
    N_REPEATS,
    N_SPLITS,
    evaluate_repeat,
)
from dielectric_room_window_paired import HYBRID, masked_splits
from rdkit import Chem
from rdkit.Chem import Descriptors
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

TASK_ID = "week18_w18b_dielectric_applicability_domain"

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_applicability_domain_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_applicability_domain_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_applicability_domain.md"
ARTIFACTS_DIR = REPOSITORY_ROOT / "probes" / "artifacts"
REPEATS_PATH = ARTIFACTS_DIR / "dielectric_applicability_domain_repeats.csv"
COORDINATION_FEATURES = ARTIFACTS_DIR / "dielectric_coordination_block_features.csv"
CONFORMER_FEATURES = ARTIFACTS_DIR / "dielectric_xtb_full_table_migration_conformers.csv"
V3_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_v3_summary.json"

HEADLINE_R2 = 0.4766400383507876
REPRODUCTION_TOLERANCE = 1e-09
ARM_HEADLINE = "plus_both"
ARM_PLACEBO = "placebo_shuffled_target"
ARM_FLOOR = "no_information_floor"
REPRESENTATION = HYBRID
SEEDS = (42, 1234, 2026, 31337, 7)
FROZEN_SEED = 42

D1_MIN_HBD = 1
D1_MIN_TPSA = 20.0
D2_QUANTILE = 95.0
D2_PROBABILITY = 0.5
D2_LOGISTIC_C = 1.0
D2_LOGISTIC_MAX_ITER = 1000
D3_KEYS = (
    "OHLUUHNLEMFGTQ-UHFFFAOYSA-N",
    "ZHNUHDYFZUAESO-UHFFFAOYSA-N",
    "NEQXUPRFDXNNTA-UHFFFAOYSA-N",
    "XLYOFNOQVPJJNP-UHFFFAOYSA-N",
    "LZJIBRSVPKKOSI-UHFFFAOYSA-O",
    "RJQQOKKINHMXIM-UHFFFAOYSA-N",
    "VVLAIYIMMFWRFW-UHFFFAOYSA-N",
)

RULE_ORDER = ("global", "D1", "D2", "D3")
SCOPE_ORDER = ("all", "in_domain", "out_of_domain")

READING_COLUMNS = (
    "seed",
    "arm",
    "rule",
    "scope",
    "rows_mean",
    "compounds_mean",
    "r2_mean",
    "r2_std",
    "mae_mean",
    "spearman_mean",
    "repeats_used",
)


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mean_std(values: Sequence[float]) -> tuple[float | None, float | None]:
    finite = np.asarray([float(value) for value in values], dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return None, None
    if finite.size == 1:
        return float(finite[0]), 0.0
    return float(finite.mean()), float(finite.std(ddof=1))


def build_base() -> tuple[dict[str, object], np.ndarray, dict[str, object]]:
    """The frozen pool plus the two feature blocks that make up the headline arm."""

    scoreboard = v1.build_scoreboard()
    contract = scoreboard["contract"]
    if not contract["matches_preregistration"]:
        raise RuntimeError("the rebuilt scoreboard does not match the pre-registration")
    coordination_rows = v1.read_csv_rows(COORDINATION_FEATURES)
    matrix, block_report = v1.coordination_matrix(scoreboard["rows"], coordination_rows)
    conformer_rows = v1.read_csv_rows(CONFORMER_FEATURES)
    dipole_map = v3.dipole_map_from_conformer_rows(conformer_rows)
    physical_v04, lever4_report = migration.build_physical_matrix_v04(
        scoreboard["rows"], dipole_map=dipole_map
    )
    with_both = np.hstack([physical_v04, matrix])
    reports: dict[str, object] = {
        "contract": dict(contract),
        "coordination_block": dict(block_report),
        "lever4_block": dict(lever4_report),
        "with_both_columns": int(with_both.shape[1]),
    }
    return scoreboard, with_both, reports


def splits_for_seed(scoreboard: Mapping[str, object], seed: int) -> list[tuple[int, int, np.ndarray, np.ndarray]]:
    """The frozen fold protocol with only the seed changed."""

    groups = [str(key) for key in scoreboard["groups"]]
    scored = scoreboard["scored"]
    return list(
        drop_thin_folds(
            masked_splits(
                groups,
                score_mask=scored,
                train_mask=scored,
                n_splits=N_SPLITS,
                n_repeats=N_REPEATS,
                seed=seed,
            ),
            min_test_rows=MIN_TEST_ROWS_PER_FOLD,
        )
    )


def d1_out_of_domain(scoreboard: Mapping[str, object]) -> dict[str, bool]:
    """Rule D1: polar protic, from the frozen SMILES alone.  No label is read."""

    flags: dict[str, bool] = {}
    for row, is_scored in zip(scoreboard["rows"], scoreboard["scored"], strict=True):
        if not bool(is_scored):
            continue
        key = str(row["inchikey"])
        if key in flags:
            continue
        molecule = Chem.MolFromSmiles(str(row["smiles"]))
        if molecule is None:
            raise RuntimeError("unparsable SMILES in the frozen pool: " + key)
        flags[key] = bool(
            Descriptors.NumHDonors(molecule) >= D1_MIN_HBD
            and Descriptors.TPSA(molecule) >= D1_MIN_TPSA
        )
    return flags


def d2_out_of_domain(
    scoreboard: Mapping[str, object],
    splits: Sequence[tuple[int, int, np.ndarray, np.ndarray]],
) -> tuple[dict[tuple[int, str], float], int]:
    """Rule D2: the training-side p95 classifier, fitted inside every fold."""

    groups = np.asarray([str(key) for key in scoreboard["groups"]])
    target = np.asarray(scoreboard["target"], dtype=float)
    physical = np.asarray(scoreboard["physical"], dtype=float)
    probabilities: dict[tuple[int, str], float] = {}
    fallback_folds = 0
    for repeat, _fold, train_index, test_index in splits:
        train = np.asarray(train_index)
        test = np.asarray(test_index)
        threshold = float(np.percentile(target[train], D2_QUANTILE))
        labels = (target[train] > threshold).astype(int)
        if labels.min() == labels.max():
            fallback_folds += 1
            for key in groups[test]:
                probabilities[(int(repeat), str(key))] = 0.0
            continue
        scaler = StandardScaler().fit(physical[train])
        model = LogisticRegression(
            C=D2_LOGISTIC_C, solver="lbfgs", max_iter=D2_LOGISTIC_MAX_ITER
        ).fit(scaler.transform(physical[train]), labels)
        scored = model.predict_proba(scaler.transform(physical[test]))[:, 1]
        per_compound: dict[str, list[float]] = {}
        for key, value in zip(groups[test], scored, strict=True):
            per_compound.setdefault(str(key), []).append(float(value))
        for key, values in per_compound.items():
            probabilities[(int(repeat), key)] = float(np.mean(values))
    return probabilities, fallback_folds


def repeat_buckets(
    prediction_rows: Sequence[Mapping[str, object]],
) -> dict[int, dict[str, np.ndarray]]:
    """Pool every fold of a repeat into one test set, exactly like the frozen reading."""

    raw: dict[int, dict[str, list]] = {}
    for row in prediction_rows:
        if str(row["representation"]) != REPRESENTATION:
            continue
        bucket = raw.setdefault(
            int(row["repeat"]), {"target": [], "prediction": [], "inchikey": []}
        )
        bucket["target"].append(float(row["target"]))
        bucket["prediction"].append(float(row["prediction"]))
        bucket["inchikey"].append(str(row["inchikey"]))
    return {
        repeat: {name: np.asarray(values) for name, values in bucket.items()}
        for repeat, bucket in sorted(raw.items())
    }


def scope_reading(
    buckets: Mapping[int, Mapping[str, np.ndarray]],
    keeps: Callable[[int, str], bool],
) -> dict[str, object]:
    """One (rule, scope) cell: pool per repeat, score, then average over repeats."""

    r2_values: list[float] = []
    mae_values: list[float] = []
    spearman_values: list[float] = []
    row_counts: list[int] = []
    compound_counts: list[int] = []
    for repeat, bucket in sorted(buckets.items()):
        keys = bucket["inchikey"]
        keep = np.asarray([bool(keeps(int(repeat), str(key))) for key in keys], dtype=bool)
        row_counts.append(int(keep.sum()))
        compound_counts.append(int(np.unique(keys[keep]).size))
        if int(keep.sum()) < 3:
            continue
        metrics = evaluate_repeat(bucket["target"][keep], bucket["prediction"][keep])
        r2_values.append(float(metrics["r2"]))
        mae_values.append(float(metrics["mae"]))
        spearman_values.append(float(metrics["spearman"]))
    r2_mean, r2_std = _mean_std(r2_values)
    mae_mean, _mae_std = _mean_std(mae_values)
    spearman_mean, _spearman_std = _mean_std(spearman_values)
    return {
        "rows_mean": float(np.mean(row_counts)) if row_counts else 0.0,
        "compounds_mean": float(np.mean(compound_counts)) if compound_counts else 0.0,
        "r2_mean": r2_mean,
        "r2_std": r2_std,
        "mae_mean": mae_mean,
        "spearman_mean": spearman_mean,
        "repeats_used": len(r2_values),
    }


def run_seed(
    seed: int,
    *,
    scoreboard: Mapping[str, object],
    with_both: np.ndarray,
    d1_flags: Mapping[str, bool],
) -> dict[str, object]:
    """One seed: the headline arm, the placebo, the floor, and every scope reading."""

    started = time.perf_counter()
    groups = [str(key) for key in scoreboard["groups"]]
    target = np.asarray(scoreboard["target"], dtype=float)
    temperatures = np.asarray(scoreboard["temperatures"], dtype=float)
    morgan = np.asarray(scoreboard["morgan"])
    scored = np.asarray(scoreboard["scored"], dtype=bool)
    splits = splits_for_seed(scoreboard, seed)
    headline = v1.evaluate_arm(
        ARM_HEADLINE,
        morgan=morgan,
        physical=with_both,
        target=target,
        temperatures=temperatures,
        groups=groups,
        splits=splits,
        jobs=1,
    )
    shuffled = v1.shuffled_target(target, scored)
    placebo = v1.evaluate_arm(
        ARM_PLACEBO,
        morgan=morgan,
        physical=with_both,
        target=shuffled,
        temperatures=temperatures,
        groups=groups,
        splits=splits,
        jobs=1,
    )
    floor = v3.fold_mean_floor(
        ARM_FLOOR,
        target=shuffled,
        temperatures=temperatures,
        groups=groups,
        splits=splits,
    )
    buckets = repeat_buckets(headline["prediction_rows"])
    d2_flags, fallback_folds = d2_out_of_domain(scoreboard, splits)
    keeps = {
        "global": lambda repeat, key: True,
        "D1": lambda repeat, key: not bool(d1_flags.get(key, False)),
        "D2": lambda repeat, key: d2_flags.get((repeat, key), 0.0) < D2_PROBABILITY,
        "D3": lambda repeat, key: key not in set(D3_KEYS),
    }
    rules: dict[str, object] = {}
    for rule in RULE_ORDER:
        if rule == "global":
            cell = scope_reading(buckets, keeps[rule])
            rules[rule] = {
                "all": cell,
                "in_domain": cell,
                "out_of_domain": {
                    "rows_mean": 0.0,
                    "compounds_mean": 0.0,
                    "r2_mean": None,
                    "r2_std": None,
                    "mae_mean": None,
                    "spearman_mean": None,
                    "repeats_used": 0,
                },
            }
            continue
        inside = scope_reading(buckets, keeps[rule])
        outside = scope_reading(buckets, lambda repeat, key, k=keeps[rule]: not k(repeat, key))
        rules[rule] = {"all": None, "in_domain": inside, "out_of_domain": outside}
    placebo_global = scope_reading(repeat_buckets(placebo["prediction_rows"]), keeps["global"])
    floor_rows = floor["repeat_rows"]
    floor_r2, floor_std = _mean_std([float(row["r2"]) for row in floor_rows])
    flagged = sorted({key for (repeat, key), value in d2_flags.items() if value >= D2_PROBABILITY})
    return {
        "seed": int(seed),
        "wall_seconds": time.perf_counter() - started,
        "folds": len(splits),
        "rules": rules,
        "placebo": {"global": placebo_global, "r2_mean": placebo_global["r2_mean"]},
        "floor": {"r2_mean": floor_r2, "r2_std": floor_std},
        "d1_out_of_domain_compounds": sorted(key for key, flag in d1_flags.items() if flag),
        "d2_out_of_domain_compounds": flagged,
        "d2_fallback_folds": int(fallback_folds),
        "headline_leak": dict(headline["leak"]),
        "seed_summary_r2": float(headline["summary"][REPRESENTATION]["r2"]["mean"]),
    }


def build_summary(
    *,
    per_seed: Sequence[Mapping[str, object]],
    base_reports: Mapping[str, object],
    d1_flags: Mapping[str, bool],
    telemetry: Mapping[str, object],
) -> dict[str, object]:
    frozen_seed = next(item for item in per_seed if int(item["seed"]) == FROZEN_SEED)
    observed = float(frozen_seed["rules"]["global"]["all"]["r2_mean"])
    reproduction = {
        "published_r2": HEADLINE_R2,
        "observed_r2": observed,
        "abs_delta": abs(observed - HEADLINE_R2),
        "tolerance": REPRODUCTION_TOLERANCE,
        "reproduced": abs(observed - HEADLINE_R2) <= REPRODUCTION_TOLERANCE,
        "seed": FROZEN_SEED,
        "arm": ARM_HEADLINE,
        "representation": REPRESENTATION,
    }
    if not reproduction["reproduced"]:
        raise RuntimeError(
            "the frozen headline did not reproduce; no in-domain number may be reported"
        )
    endpoint: dict[str, object] = {}
    for rule in RULE_ORDER:
        cells: dict[str, object] = {}
        scopes = ("all",) if rule == "global" else ("in_domain", "out_of_domain")
        for scope in scopes:
            values = [
                item["rules"][rule][scope]["r2_mean"]
                for item in per_seed
                if item["rules"][rule][scope] is not None
            ]
            numeric = [float(value) for value in values if value is not None]
            mean, std = _mean_std(numeric)
            mae_values = [
                float(item["rules"][rule][scope]["mae_mean"])
                for item in per_seed
                if item["rules"][rule][scope] is not None
                and item["rules"][rule][scope]["mae_mean"] is not None
            ]
            mae_mean, _mae_std = _mean_std(mae_values)
            rows_mean = float(
                np.mean([item["rules"][rule][scope]["rows_mean"] for item in per_seed])
            )
            compounds_mean = float(
                np.mean([item["rules"][rule][scope]["compounds_mean"] for item in per_seed])
            )
            cells[scope] = {
                "r2_mean": mean,
                "r2_std": std,
                "mae_mean": mae_mean,
                "rows_mean": rows_mean,
                "compounds_mean": compounds_mean,
                "seeds_used": len(numeric),
            }
        endpoint[rule] = cells
    placebo_values = [float(item["placebo"]["r2_mean"]) for item in per_seed]
    floor_values = [float(item["floor"]["r2_mean"]) for item in per_seed]
    placebo_mean, placebo_std = _mean_std(placebo_values)
    floor_mean, floor_std = _mean_std(floor_values)
    global_endpoint = float(endpoint["global"]["all"]["r2_mean"])
    gain_d1 = None
    if endpoint["D1"]["in_domain"]["r2_mean"] is not None:
        gain_d1 = float(endpoint["D1"]["in_domain"]["r2_mean"]) - global_endpoint
    gain_d3 = None
    if endpoint["D3"]["in_domain"]["r2_mean"] is not None:
        gain_d3 = float(endpoint["D3"]["in_domain"]["r2_mean"]) - global_endpoint
    return {
        "schema_version": 1,
        "task": TASK_ID,
        "generated_at_utc": _utc_now(),
        "preregistration": {
            "path": portable_relative_path(PREREG_PATH, root=REPOSITORY_ROOT),
            "sha256": canonical_text_sha256(PREREG_PATH),
            "status": "locked_before_run",
        },
        "base": dict(base_reports),
        "reproduction_check": reproduction,
        "seeds": [int(item["seed"]) for item in per_seed],
        "domain_rules": {
            "D1": {
                "id": "polar_protic",
                "definition": "NumHDonors(SMILES) >= 1 and TPSA(SMILES) >= 20.0",
                "out_of_domain_compounds": sorted(
                    key for key, flag in d1_flags.items() if flag
                ),
                "in_domain_compounds": sorted(
                    key for key, flag in d1_flags.items() if not flag
                ),
            },
            "D2": {
                "id": "train_p95_classifier",
                "definition": (
                    "per fold: cut the training labels at their p95, fit "
                    "LogisticRegression(C=1.0, lbfgs, max_iter=1000) on the standardised "
                    "frozen physical block, average the test rows per compound, "
                    "out of domain at probability >= 0.5"
                ),
                "roster_per_seed": {
                    str(item["seed"]): item["d2_out_of_domain_compounds"] for item in per_seed
                },
                "fallback_folds_per_seed": {
                    str(item["seed"]): item["d2_fallback_folds"] for item in per_seed
                },
            },
            "D3": {
                "id": "verified_high_eps_roster",
                "keys": list(D3_KEYS),
                "role": "diagnostic roster, never the pre-registered rule",
            },
        },
        "per_seed": [dict(item) for item in per_seed],
        "endpoint": dict(endpoint),
        "headline_vs_in_domain": {
            "global_endpoint_r2": global_endpoint,
            "D1_in_domain_r2": endpoint["D1"]["in_domain"]["r2_mean"],
            "D1_gain": gain_d1,
            "D2_in_domain_r2": endpoint["D2"]["in_domain"]["r2_mean"],
            "D3_in_domain_r2": endpoint["D3"]["in_domain"]["r2_mean"],
            "D3_gain": gain_d3,
            "never_a_headline": "域内数是范围声明下的第二块记分牌，不得替换或提升为主记分牌读数。",
        },
        "placebo": {
            "r2_mean": placebo_mean,
            "r2_std": placebo_std,
            "floor_r2_mean": floor_mean,
            "floor_r2_std": floor_std,
            "over_the_floor": (
                None if placebo_mean is None or floor_mean is None else placebo_mean - floor_mean
            ),
        },
        "verdict": "domain_split_reported",
        "promoted": False,
        "honest_boundaries": [
            "全域读数照报：plus_both 在 457/97/276 上的跨种子均值就是主记分牌读数，域内数不替换它。",
            "域内数不得当作达标题；本枪 promoted 恒为 false。",
            "种子集跑前锁定；多种子只消种子方差，不改折结构与超参。",
            "D3 依赖标签幅度，只是诊断件，不是可部署的域规则。",
            "D1 是宽口径的质子性极性类（含全部醇），该族的尾部才是高 ε 自缔合液体；名册全量报出。",
            "安慰剂洗牌在 v1 里钉死为 seed 42，逐字复用；地板是训练折均值。",
            "本枪不动任何冻结数字：0.4766400383507876 只被复现，不被改写；0.4091179943351143 不在本记分牌上。",
        ],
        "telemetry": dict(telemetry),
    }


def reading_rows(per_seed: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in per_seed:
        cell = item["rules"]["global"]["all"]
        rows.append(
            {
                "seed": item["seed"],
                "arm": ARM_HEADLINE,
                "rule": "global",
                "scope": "all",
                "rows_mean": cell["rows_mean"],
                "compounds_mean": cell["compounds_mean"],
                "r2_mean": cell["r2_mean"],
                "r2_std": cell["r2_std"],
                "mae_mean": cell["mae_mean"],
                "spearman_mean": cell["spearman_mean"],
                "repeats_used": cell["repeats_used"],
            }
        )
        for rule in ("D1", "D2", "D3"):
            for scope in ("in_domain", "out_of_domain"):
                cell = item["rules"][rule][scope]
                rows.append(
                    {
                        "seed": item["seed"],
                        "arm": ARM_HEADLINE,
                        "rule": rule,
                        "scope": scope,
                        "rows_mean": cell["rows_mean"],
                        "compounds_mean": cell["compounds_mean"],
                        "r2_mean": "" if cell["r2_mean"] is None else cell["r2_mean"],
                        "r2_std": "" if cell["r2_std"] is None else cell["r2_std"],
                        "mae_mean": "" if cell["mae_mean"] is None else cell["mae_mean"],
                        "spearman_mean": (
                            "" if cell["spearman_mean"] is None else cell["spearman_mean"]
                        ),
                        "repeats_used": cell["repeats_used"],
                    }
                )
        placebo = item["placebo"]["global"]
        rows.append(
            {
                "seed": item["seed"],
                "arm": ARM_PLACEBO,
                "rule": "global",
                "scope": "all",
                "rows_mean": placebo["rows_mean"],
                "compounds_mean": placebo["compounds_mean"],
                "r2_mean": placebo["r2_mean"],
                "r2_std": placebo["r2_std"],
                "mae_mean": placebo["mae_mean"],
                "spearman_mean": placebo["spearman_mean"],
                "repeats_used": placebo["repeats_used"],
            }
        )
    return rows


def endpoint_rows(summary: Mapping[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    endpoint = summary["endpoint"]
    for rule in RULE_ORDER:
        scopes = ("all",) if rule == "global" else ("in_domain", "out_of_domain")
        for scope in scopes:
            cell = endpoint[rule][scope]
            rows.append(
                {
                    "seed": "endpoint",
                    "arm": ARM_HEADLINE,
                    "rule": rule,
                    "scope": scope,
                    "rows_mean": cell["rows_mean"],
                    "compounds_mean": cell["compounds_mean"],
                    "r2_mean": "" if cell["r2_mean"] is None else cell["r2_mean"],
                    "r2_std": "" if cell["r2_std"] is None else cell["r2_std"],
                    "mae_mean": "" if cell["mae_mean"] is None else cell["mae_mean"],
                    "spearman_mean": "",
                    "repeats_used": cell["seeds_used"],
                }
            )
    placebo = summary["placebo"]
    rows.append(
        {
            "seed": "endpoint",
            "arm": ARM_PLACEBO,
            "rule": "global",
            "scope": "all",
            "rows_mean": "",
            "compounds_mean": "",
            "r2_mean": placebo["r2_mean"],
            "r2_std": placebo["r2_std"],
            "mae_mean": "",
            "spearman_mean": "",
            "repeats_used": len(summary["seeds"]),
        }
    )
    return rows


def _fmt(value: object, digits: int = 6) -> str:
    if value is None or value == "":
        return "-"
    return ("{:." + str(digits) + "f}").format(float(value))


def format_report(summary: Mapping[str, object]) -> list[str]:
    endpoint = summary["endpoint"]
    reproduction = summary["reproduction_check"]
    placebo = summary["placebo"]
    compare = summary["headline_vs_in_domain"]
    d1 = summary["domain_rules"]["D1"]
    d2 = summary["domain_rules"]["D2"]
    lines = [
        "# ε 分域记分牌（W18-B）",
        "",
        "冻结头条是 plus_both（Morgan+Physical + lever4 + lever8）在 457 行 / 97 化合物 / 276 个（化合物，T）对上的读数",
        "`0.4766400383507876`。本枪不改它，只在同一池、同一臂上并列报第二块记分牌：域内读数。",
        "",
        "## 复现（先决条件）",
        "",
        "- seed 42 全域 R2：{}（发布 {}，偏差 {:.2e}，容差 {:.0e}）".format(
            _fmt(reproduction["observed_r2"], 16),
            _fmt(reproduction["published_r2"], 16),
            reproduction["abs_delta"],
            reproduction["tolerance"],
        ),
        "- 复现成立：{}；不成立则整枪抛错、不报任何域内数字。".format(reproduction["reproduced"]),
        "",
        "## 跨种子端点（种子集 42, 1234, 2026, 31337, 7 跑前锁定）",
        "",
        "| 规则 | 口径 | 行（均值） | 化合物（均值） | R2 均值 | R2 跨种子 sd | MAE 均值 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    labels = {"global": "全域（无域声明）", "D1": "D1 极性质子性（特征规则）", "D2": "D2 训练侧 p95 分类器", "D3": "D3 已核实高 ε 名册（诊断）"}
    scope_labels = {"all": "全域", "in_domain": "域内", "out_of_domain": "域外"}
    for rule in RULE_ORDER:
        scopes = ("all",) if rule == "global" else ("in_domain", "out_of_domain")
        for scope in scopes:
            cell = endpoint[rule][scope]
            lines.append(
                "| {} | {} | {} | {} | {} | {} | {} |".format(
                    labels[rule],
                    scope_labels[scope],
                    _fmt(cell["rows_mean"], 1),
                    _fmt(cell["compounds_mean"], 1),
                    _fmt(cell["r2_mean"]),
                    _fmt(cell["r2_std"]),
                    _fmt(cell["mae_mean"], 3),
                )
            )
    lines.extend([
        "",
        "## 域声明与全域数的关系",
        "",
        "- 全域跨种子端点 R2：{}".format(_fmt(compare["global_endpoint_r2"])),
        "- D1 域内 R2：{}（对全域 {}）".format(_fmt(compare["D1_in_domain_r2"]), _fmt(compare["D1_gain"])),
        "- D3 域内 R2：{}（对全域 {}）".format(_fmt(compare["D3_in_domain_r2"]), _fmt(compare["D3_gain"])),
        "- 域内数不得当作达标题：{}".format(compare["never_a_headline"]),
        "",
        "## 安慰剂",
        "",
        "- 洗牌标签臂跨种子 R2 均值：{}（sd {}）；地板（训练折均值）：{}；过地板 {}".format(
            _fmt(placebo["r2_mean"]),
            _fmt(placebo["r2_std"]),
            _fmt(placebo["floor_r2_mean"]),
            _fmt(placebo["over_the_floor"]),
        ),
        "",
        "## 域外名册（全量报出）",
        "",
        "- D1（特征规则）域外化合物 {} 个：{}".format(len(d1["out_of_domain_compounds"]), ", ".join(d1["out_of_domain_compounds"])),
        "- D1 域内化合物 {} 个".format(len(d1["in_domain_compounds"])),
        "- D2 逐种子域外名册（化合物数）：{}".format(
            ", ".join(
                f"{seed}:{len(roster)}"
                for seed, roster in sorted(d2["roster_per_seed"].items())
            )
        ),
        "- D2 fallback 折数（训练标签只有一类）：{}".format(d2["fallback_folds_per_seed"]),
        "- D3 诊断名册：{}".format(", ".join(summary["domain_rules"]["D3"]["keys"])),
        "",
        "## 诚实边界",
        "",
    ])
    lines.extend("- " + str(item) for item in summary["honest_boundaries"])
    prereg = summary["preregistration"]
    telemetry = summary["telemetry"]
    lines.extend([
        "",
        "## 产物",
        "",
        "- 脚本：probes/dielectric_applicability_domain.py",
        "- 预注册：{}（sha256 {}）".format(prereg["path"], prereg["sha256"]),
        "- 读数表：probes/artifacts/dielectric_applicability_domain_repeats.csv",
        "- 摘要：probes/dielectric_applicability_domain_summary.json",
        "- 墙钟：{:.1f} s，jobs {}".format(telemetry["wall_seconds"], telemetry["jobs"]),
        "",
    ])
    return lines


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=None, help="run one seed only (diagnostics)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    jobs = max(1, int(args.jobs))
    for path in (PREREG_PATH, COORDINATION_FEATURES, CONFORMER_FEATURES, V3_SUMMARY_PATH):
        if not path.is_file():
            print("MISSING " + str(path))
            return 1
    started = time.perf_counter()
    scoreboard, with_both, base_reports = build_base()
    d1_flags = d1_out_of_domain(scoreboard)
    seeds = (int(args.seed),) if args.seed is not None else SEEDS
    print("pool: {} rows / {} compounds / {} folds".format(
        base_reports["contract"]["scored_rows"],
        base_reports["contract"]["compounds_scored"],
        base_reports["contract"]["folds"],
    ), flush=True)
    print(f"D1 out of domain: {sum(1 for flag in d1_flags.values() if flag)} of {len(d1_flags)} compounds", flush=True)
    if jobs <= 1 or len(seeds) == 1:
        per_seed = [
            run_seed(seed, scoreboard=scoreboard, with_both=with_both, d1_flags=d1_flags)
            for seed in seeds
        ]
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [
                pool.submit(
                    run_seed,
                    seed,
                    scoreboard=scoreboard,
                    with_both=with_both,
                    d1_flags=d1_flags,
                )
                for seed in seeds
            ]
            per_seed = [future.result() for future in futures]
    per_seed = sorted(per_seed, key=lambda item: int(item["seed"]))
    for item in per_seed:
        print("seed {:>6d}  global R2 {:+.6f}  D1 in {}  D2 in {}  D3 in {}  {:.1f}s".format(
            item["seed"],
            float(item["rules"]["global"]["all"]["r2_mean"]),
            _fmt(item["rules"]["D1"]["in_domain"]["r2_mean"]),
            _fmt(item["rules"]["D2"]["in_domain"]["r2_mean"]),
            _fmt(item["rules"]["D3"]["in_domain"]["r2_mean"]),
            item["wall_seconds"],
        ), flush=True)
    telemetry = {
        "wall_seconds": time.perf_counter() - started,
        "jobs": jobs,
        "python": platform.python_version(),
        "platform": sys.platform,
        "seeds": [int(item["seed"]) for item in per_seed],
        "network_used": False,
        "xtb_executed": False,
    }
    summary = build_summary(
        per_seed=per_seed,
        base_reports=base_reports,
        d1_flags=d1_flags,
        telemetry=telemetry,
    )
    summary["outputs"] = {
        "summary": portable_relative_path(SUMMARY_PATH, root=REPOSITORY_ROOT),
        "report": portable_relative_path(REPORT_PATH, root=REPOSITORY_ROOT),
        "repeats": portable_relative_path(REPEATS_PATH, root=REPOSITORY_ROOT),
    }
    csv_rows = [*reading_rows(per_seed), *endpoint_rows(summary)]
    v1.write_csv_rows(REPEATS_PATH, READING_COLUMNS, csv_rows)
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    REPORT_PATH.write_text(
        "\n".join(format_report(summary)) + "\n", encoding="utf-8", newline="\n"
    )
    print()
    print("endpoint global R2   : {:.16f}".format(float(summary["endpoint"]["global"]["all"]["r2_mean"])))
    print("endpoint D1 in-domain: {}".format(_fmt(summary["endpoint"]["D1"]["in_domain"]["r2_mean"])))
    print("endpoint D3 in-domain: {}".format(_fmt(summary["endpoint"]["D3"]["in_domain"]["r2_mean"])))
    print("placebo R2           : {}".format(_fmt(summary["placebo"]["r2_mean"])))
    print("wall seconds         : {:.1f}".format(telemetry["wall_seconds"]))
    print("summary : " + str(summary["outputs"]["summary"]))
    print("report  : " + str(summary["outputs"]["report"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
