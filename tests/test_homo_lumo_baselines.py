"""Guards for the L3 exit-2 HOMO/LUMO/IP/EA baselines (manual appendix Q-2)."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pytest
from sklearn.dummy import DummyRegressor

import probes.homo_lumo_baselines as module
from probes.homo_lumo_baselines import (
    CV_REPEATS,
    CV_SEED,
    CV_SPLITS,
    DESCRIPTOR_NAMES,
    FORBIDDEN_FEATURE_INPUTS,
    GATE_MAE_THRESHOLD,
    GATE_UNIT,
    MORGAN_FP_SIZE,
    MORGAN_RADIUS,
    SCREEN_COMBINATIONS,
    TARGET_ORDER,
    CacheMismatchError,
    ChampionLeakError,
    MeanDummyModel,
    assert_champions_absent,
    assert_structure_only_features,
    build_feature_bundle,
    build_model,
    build_pool,
    champion_key_map,
    cv_folds,
    exclude_champions,
    feature_config,
    id_block_sha256,
    load_target_models,
    pool_sha256,
    predict_smiles,
    score_smiles_file,
    select_main_configurations,
)
from probes.p2_battp30k_baseline import _model as p2_model

ROOT = Path(__file__).resolve().parents[1]
H5_PATH = ROOT / module.H5_RELATIVE_PATH
BASELINES_PATH = ROOT / module.BASELINES_RELATIVE_PATH
SUMMARY_PATH = ROOT / module.SUMMARY_RELATIVE_PATH
FOLD_CSV_PATH = ROOT / module.FOLD_CSV_RELATIVE_PATH
PREREG_PATH = ROOT / module.PREREG_RELATIVE_PATH
P4_SUMMARY_PATH = ROOT / module.P4_SUMMARY_RELATIVE_PATH

EXPECTED_CHAMPIONS = {
    "KMTRUDSVKNLOMY-UHFFFAOYSA-N",
    "RUOJZAUFBMNUDX-UHFFFAOYSA-N",
    "SBLRHMKNNHXPHG-UHFFFAOYSA-N",
    "VAYTZRYEBVHVLE-UHFFFAOYSA-N",
}
EXPECTED_H5_SHA256 = "587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d"
EXPECTED_DIELECTRIC_SHA256 = (
    "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def payload() -> dict:
    assert BASELINES_PATH.exists(), (
        f"missing {BASELINES_PATH}; run `python probes/homo_lumo_baselines.py` first"
    )
    return json.loads(BASELINES_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def summary() -> dict:
    assert SUMMARY_PATH.exists(), (
        f"missing {SUMMARY_PATH}; run `python probes/homo_lumo_baselines.py` first"
    )
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def prereg() -> dict:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bundle() -> module.FeatureBundle:
    return build_feature_bundle(H5_PATH, ROOT / module.CACHE_RELATIVE_PATH)


@pytest.fixture(scope="module")
def fold_rows() -> list[dict[str, str]]:
    assert FOLD_CSV_PATH.exists(), f"missing {FOLD_CSV_PATH}"
    with FOLD_CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# --- sealed inputs -----------------------------------------------------------------


def test_batt_p30k_digest_matches_the_prereg_snapshot(prereg: dict) -> None:
    pinned = prereg["inputs_pinned"][module.H5_RELATIVE_PATH]["sha256"]
    assert pinned == EXPECTED_H5_SHA256
    assert _sha256(H5_PATH) == EXPECTED_H5_SHA256


def test_frozen_dielectric_table_digest_is_unchanged(prereg: dict) -> None:
    frozen = prereg["frozen_table"]
    assert frozen["sha256"] == EXPECTED_DIELECTRIC_SHA256
    assert _sha256(ROOT / frozen["path"]) == EXPECTED_DIELECTRIC_SHA256


def test_prereg_champions_are_the_four_expected_molecules(prereg: dict) -> None:
    champions = champion_key_map(prereg)
    assert set(champions) == EXPECTED_CHAMPIONS
    assert set(champions.values()) == {"EC", "PC", "FEC", "VC"}


def test_recorded_exclusion_rule_matches_the_live_prereg(prereg: dict, payload: dict) -> None:
    recorded = payload["exclusion"]
    assert recorded["level"] == "L1"
    assert recorded["rule"] == prereg["exclusion_levels"][0]
    live = {
        entry["inchikey"]
        for entry in (
            list(prereg["champion_set"]["solvent_list"])
            + list(prereg["champion_set"]["additive_list"])
        )
    }
    assert live == EXPECTED_CHAMPIONS
    assert {entry["inchikey"] for entry in recorded["champions"]} == live


def test_cv_protocol_matches_the_preregistered_fold_and_seed_scheme(
    prereg: dict,
    summary: dict,
) -> None:
    scheme = prereg["fold_and_seed"]
    assert scheme["fold_scheme"] == (
        "RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)"
    )
    assert scheme["seed_scheme"] == "42 + global RepeatedKFold split index"
    cv = summary["cv_protocol"]
    assert cv["splitter"] == "RepeatedKFold"
    assert (cv["n_splits"], cv["n_repeats"], cv["random_state"]) == (CV_SPLITS, 10, 42)
    assert cv["seed_rule"] == "42 + global fold index (repeat * n_splits + fold)"
    assert cv["n_folds"] == CV_SPLITS * CV_REPEATS == 50


# --- L1 exclusion ------------------------------------------------------------------


def test_pool_excludes_champions_and_matches_the_recorded_counts(
    bundle: module.FeatureBundle,
    payload: dict,
    summary: dict,
) -> None:
    champions = frozenset(EXPECTED_CHAMPIONS)
    pool = build_pool(bundle, champions)
    assert len(pool) == bundle.source_group_count - 4
    assert not set(bundle.inchikeys[pool].tolist()) & champions
    digest = pool_sha256(bundle, pool)
    assert digest == payload["exclusion"]["pool_sha256"]
    assert digest == summary["pool_sha256"]
    assert payload["exclusion"]["pool_rows_after_exclusion"] == len(pool)


def test_champion_in_training_rows_raises_an_l1_violation() -> None:
    champion = "SBLRHMKNNHXPHG-UHFFFAOYSA-N"
    inchikeys = np.asarray([champion, "AAAAAAAAAAAAAA-UHFFFAOYSA-N"], dtype=str)
    train = np.asarray([0, 1], dtype=np.int64)
    with pytest.raises(ChampionLeakError):
        assert_champions_absent(inchikeys[train], frozenset({champion}), context="unit test")
    kept = exclude_champions(train, inchikeys, frozenset({champion}))
    np.testing.assert_array_equal(kept, np.asarray([1]))
    assert_champions_absent(inchikeys[kept], frozenset({champion}), context="unit test")


def test_every_formal_fold_trains_without_a_champion(
    bundle: module.FeatureBundle,
    fold_rows: list[dict[str, str]],
) -> None:
    champions = frozenset(EXPECTED_CHAMPIONS)
    pool = build_pool(bundle, champions)
    pool_ids = bundle.molecule_ids[pool]
    pool_inchikeys = bundle.inchikeys[pool]
    folds = cv_folds(len(pool), repeats=CV_REPEATS, seed=CV_SEED)
    main_rows = [
        row for row in fold_rows if not row["model"].endswith(":dummy_mean")
    ]
    assert len(main_rows) == len(folds) * len(TARGET_ORDER)
    for spec in folds:
        train = exclude_champions(spec.train, pool_inchikeys, champions)
        assert_champions_absent(pool_inchikeys[train], champions, context=spec.label)
        assert not np.intersect1d(train, spec.test).size
    recorded = {
        (int(row["repeat"]), int(row["fold"]), row["model"].split(":")[0]): row["train_sha"]
        for row in main_rows
    }
    for spec in folds:
        train = exclude_champions(spec.train, pool_inchikeys, champions)
        expected = id_block_sha256(pool_ids[train].tolist())
        for target in TARGET_ORDER:
            assert recorded[(spec.repeat, spec.fold, target)] == expected


def test_cv_folds_follow_the_seeded_repeated_kfold_contract(
    bundle: module.FeatureBundle,
) -> None:
    champions = frozenset(EXPECTED_CHAMPIONS)
    pool = build_pool(bundle, champions)
    folds = cv_folds(len(pool), repeats=CV_REPEATS, seed=CV_SEED)
    assert len(folds) == CV_SPLITS * CV_REPEATS == 50
    for index, spec in enumerate(folds):
        assert spec.index == index
        assert spec.seed == CV_SEED + index
        assert spec.repeat == index // CV_SPLITS
        assert spec.fold == index % CV_SPLITS
        assert not np.intersect1d(spec.train, spec.test).size
        assert len(spec.train) + len(spec.test) == len(pool)
    first_repeat = [np.sort(spec.test) for spec in folds[:CV_SPLITS]]
    assert len({tuple(values.tolist()) for values in first_repeat}) == CV_SPLITS
    second_repeat = [np.sort(spec.test) for spec in folds[CV_SPLITS : 2 * CV_SPLITS]]
    assert not {tuple(values.tolist()) for values in first_repeat} & {
        tuple(values.tolist()) for values in second_repeat
    }


# --- fold records and the Dummy control ---------------------------------------------


def test_fold_csv_has_the_declared_columns_and_lf_line_endings() -> None:
    raw = FOLD_CSV_PATH.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")
    header = raw.decode("utf-8").splitlines()[0]
    assert header == (
        "model,seed,repeat,fold,n_train,n_test,train_sha,test_sha,mae,rmse,r2"
    )


def test_dummy_control_shares_the_identical_folds(
    fold_rows: list[dict[str, str]],
) -> None:
    by_target: dict[str, dict[tuple[int, int], dict[str, dict[str, str]]]] = {}
    for row in fold_rows:
        target, model = row["model"].split(":", 1)
        key = (int(row["repeat"]), int(row["fold"]))
        by_target.setdefault(target, {}).setdefault(key, {})[model] = row
    assert set(by_target) == set(TARGET_ORDER)
    for target, folds in by_target.items():
        for key, models in folds.items():
            assert "dummy_mean" in models
            assert len(models) == 2
            dummy = models["dummy_mean"]
            mains = [row for name, row in models.items() if name != "dummy_mean"]
            assert len(mains) == 1
            main = mains[0]
            assert dummy["n_train"] == main["n_train"]
            assert dummy["n_test"] == main["n_test"]
            assert dummy["train_sha"] == main["train_sha"]
            assert dummy["test_sha"] == main["test_sha"]
            assert dummy["seed"] == main["seed"]
            assert float(dummy["mae"]) > float(main["mae"]), target


def test_dummy_model_reproduces_sklearn_mean_dummy() -> None:
    features = np.zeros((6, 3))
    target = np.asarray([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    ours = MeanDummyModel().fit(features, target).predict(np.zeros((4, 3)))
    theirs = DummyRegressor(strategy="mean").fit(features, target).predict(features)
    np.testing.assert_allclose(ours, theirs[:4])


# --- features ----------------------------------------------------------------------


def test_feature_config_is_structure_only() -> None:
    assert assert_structure_only_features() is None
    config = feature_config()
    assert config["fingerprint"]["kind"] == "morgan_count"
    assert config["fingerprint"]["radius"] == MORGAN_RADIUS == 2
    assert config["fingerprint"]["fp_size"] == MORGAN_FP_SIZE == 2048
    assert config["h5_datasets_read_for_features"] == ["smiles"]
    assert tuple(config["descriptors"]["names"]) == DESCRIPTOR_NAMES
    forbidden = {token.lower() for token in FORBIDDEN_FEATURE_INPUTS}
    assert {"gap", "homo", "lumo", "ip", "ea", "dipole"} <= forbidden
    declared = {name.lower() for name in config["descriptors"]["names"]}
    assert not declared & forbidden
    assert module.FEATURE_VARIANTS["morgan_only"].n_features == 2048
    assert module.FEATURE_VARIANTS["morgan_plus_2d"].n_features == 2048 + len(
        DESCRIPTOR_NAMES
    )


def test_poisoned_label_datasets_cannot_change_the_features(tmp_path: Path) -> None:
    molecules = [("CompMol0", b"CCO"), ("CompMol1", b"C1COC(=O)O1")]

    def build(name: str, labels: dict[str, float]) -> np.ndarray:
        path = tmp_path / f"{name}.h5"
        with h5py.File(path, "w") as handle:
            for key, smiles in molecules:
                group = handle.create_group(key)
                group.create_dataset("smiles", data=np.asarray([smiles]))
                for dataset in ("homo", "lumo", "ip", "ea"):
                    group.create_dataset(
                        dataset, data=np.asarray([labels[dataset]], dtype=np.float32)
                    )
        bundle = build_feature_bundle(path, tmp_path / f"{name}.npz")
        variant = module.FEATURE_VARIANTS["morgan_plus_2d"]
        return bundle.matrix(variant)

    original = build("original", {"homo": -9.0, "lumo": 1.0, "ip": 7.0, "ea": 0.5})
    poisoned = build(
        "poisoned",
        {"homo": -99.0, "lumo": 99.0, "ip": -99.0, "ea": 99.0},
    )
    np.testing.assert_array_equal(original, poisoned)


def test_feature_cache_rejects_a_mismatched_source_or_schema(tmp_path: Path) -> None:
    path = tmp_path / "tiny.h5"
    with h5py.File(path, "w") as handle:
        group = handle.create_group("CompMol0")
        group.create_dataset("smiles", data=np.asarray([b"CCO"]))
        for dataset in ("homo", "lumo", "ip", "ea"):
            group.create_dataset(dataset, data=np.asarray([1.0], dtype=np.float32))
    cache = tmp_path / "tiny.npz"
    build_feature_bundle(path, cache)
    other = tmp_path / "other.h5"
    with h5py.File(other, "w") as handle:
        group = handle.create_group("CompMol0")
        group.create_dataset("smiles", data=np.asarray([b"CCN"]))
        for dataset in ("homo", "lumo", "ip", "ea"):
            group.create_dataset(dataset, data=np.asarray([1.0], dtype=np.float32))
    with pytest.raises(CacheMismatchError):
        build_feature_bundle(other, cache)
    with np.load(cache, allow_pickle=False) as cached:
        payload = {name: cached[name] for name in cached.files}
    payload["schema_version"] = np.asarray(module.FEATURE_SCHEMA_VERSION + 1, dtype=np.int32)
    np.savez_compressed(cache, **payload)
    with pytest.raises(CacheMismatchError):
        build_feature_bundle(path, cache)


def test_p2_hyperparameter_parity_for_the_p2_variant() -> None:
    ours = build_model("p2_xgboost", 42).get_params()
    theirs = p2_model(seed=42).get_params()
    for key in ("n_estimators", "max_depth", "learning_rate", "subsample"):
        assert ours[key] == theirs[key]
    assert ours["colsample_bytree"] == theirs["colsample_bytree"]
    assert ours["reg_lambda"] == theirs["reg_lambda"]
    assert ours["objective"] == theirs["objective"]
    assert ours["tree_method"] == theirs["tree_method"]
    assert ours["random_state"] == theirs["random_state"] == 42


# --- selection rule ----------------------------------------------------------------


def test_selection_rule_was_executed_and_covers_every_declared_configuration(
    summary: dict,
) -> None:
    records = summary["screening_records"]
    declared = {f"{feature}+{model}" for feature, model in SCREEN_COMBINATIONS}
    for target in TARGET_ORDER:
        seen = {row["config_id"] for row in records if row["target"] == target}
        assert seen == declared
    assert summary["selection_rule"] == module.SELECTION_RULE
    recomputed = select_main_configurations(
        {"records": records, "dummy": summary["screening_dummy"]}
    )
    for target in TARGET_ORDER:
        assert summary["selections"][target]["config_id"] == recomputed[target]["config_id"]
        assert summary["selections"][target]["rule"] == module.SELECTION_RULE
        assert summary["selections"][target]["beat_dummy"] is True


# --- gate and scoring entry point --------------------------------------------------


def test_gate_reads_the_declared_threshold_and_both_scopes(
    payload: dict,
    summary: dict,
) -> None:
    gate = payload["gate"]
    assert gate["threshold_mae"] == GATE_MAE_THRESHOLD == 0.2
    assert gate["unit"] == GATE_UNIT == "eV"
    assert set(gate["per_target"]) == set(TARGET_ORDER)
    for target in TARGET_ORDER:
        entry = gate["per_target"][target]
        assert entry["threshold_mae"] == 0.2
        assert entry["unit"] == "eV"
        assert entry["passed"] is bool(entry["best_model_mae"] < 0.2)
        assert entry["best_model_mae"] == gate["best_model_mae"][target]
    assert gate["passed"] is all(
        gate["per_target"][target]["passed"] for target in TARGET_ORDER
    )
    assert gate["targets_total"] == 4
    assert gate["targets_passed"] == sum(
        gate["per_target"][target]["passed"] for target in TARGET_ORDER
    )
    assert set(gate["criterion_scopes"]) == {"per_target", "all_four"}
    assert gate == summary["gate"]


def test_unit_block_is_present_and_points_at_the_live_p4_summary(payload: dict) -> None:
    unit = payload["unit"]
    assert unit["unit"] == "eV"
    assert unit["source"] == module.P4_SUMMARY_RELATIVE_PATH
    assert unit["source_sha256"] == _sha256(P4_SUMMARY_PATH)
    assert unit["hdf5_metadata_declares_unit"] is False


def test_model_artifacts_load_and_match_their_recorded_digests(payload: dict) -> None:
    models = load_target_models(payload, ROOT)
    assert set(models) == set(TARGET_ORDER)
    for target in TARGET_ORDER:
        artifact = payload["targets"][target]["model"]["artifact"]
        path = ROOT / artifact["path"]
        assert path.exists()
        assert _sha256(path) == artifact["sha256"]
        assert payload["targets"][target]["training_pool_sha256"] == payload[
            "exclusion"
        ]["pool_sha256"]


def test_score_smiles_round_trip_matches_in_process_predictions(
    payload: dict,
    tmp_path: Path,
) -> None:
    smiles_values = ["C1COC(=O)O1", "CC1COC(=O)O1", "O=C1OC=CO1", "COC"]
    smiles_path = tmp_path / "query.smi"
    smiles_path.write_text("\n".join(smiles_values) + "\n", encoding="utf-8")
    output_path = tmp_path / "scores.csv"
    rows = score_smiles_file(smiles_path, BASELINES_PATH, output_path)
    assert output_path.read_bytes().endswith(b"\n")
    assert b"\r\n" not in output_path.read_bytes()
    models = load_target_models(payload, ROOT)
    in_process = predict_smiles(smiles_values, payload, models)
    for index, _ in enumerate(smiles_values):
        for target in TARGET_ORDER:
            assert rows[index][f"{target}_eV"] == f"{in_process[target][index]:.6f}"
        gap = float(rows[index]["gap_eV"])
        assert gap == pytest.approx(
            float(rows[index]["LUMO_eV"]) - float(rows[index]["HOMO_eV"]),
            abs=2e-6,
        )
    with output_path.open("r", encoding="utf-8", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert len(written) == len(smiles_values)
    assert written[0]["smiles"] == smiles_values[0]


def test_champion_scores_cover_the_four_prereg_champions(payload: dict) -> None:
    scores = payload["champion_scores"]
    assert {entry["inchikey"] for entry in scores} == EXPECTED_CHAMPIONS
    assert {entry["short"] for entry in scores} == {"EC", "PC", "FEC", "VC"}
    for entry in scores:
        for target in TARGET_ORDER:
            assert np.isfinite(float(entry[f"{target}_eV"]))


def test_formal_cv_reports_coverage_and_beats_dummy(summary: dict) -> None:
    for target in TARGET_ORDER:
        block = summary["formal_cv"][target]
        assert block["n_folds"] == 50
        assert block["oof_rows_covered"] == summary["pool_rows"]
        assert block["oof_repeats_per_row"] == CV_REPEATS
        assert block["fold_mae_mean"] < block["dummy_fold_mae_mean"]