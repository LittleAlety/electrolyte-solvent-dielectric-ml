from __future__ import annotations

import hashlib

import h5py
import numpy as np
import pytest

from probes.p2_battp30k_baseline import (
    CacheMismatchError,
    DatasetSchemaError,
    build_features,
    decode_smiles,
    dipole_magnitude,
    regression_metrics,
    train_test_indices,
)


def test_dipole_magnitude_uses_euclidean_norm() -> None:
    assert dipole_magnitude(np.array([3.0, 4.0, 0.0])) == 5.0


def test_decode_smiles_accepts_hdf5_bytes_and_strings() -> None:
    assert decode_smiles(b"CCO") == "CCO"
    assert decode_smiles("CCO") == "CCO"


def test_regression_metrics_report_perfect_prediction() -> None:
    target = np.array([1.0, 2.0, 3.0])

    metrics = regression_metrics(target, target)

    assert metrics["mae"] == 0.0
    assert metrics["rmse"] == 0.0
    assert metrics["r2"] == 1.0


def test_train_test_indices_are_deterministic_and_disjoint() -> None:
    first_train, first_test = train_test_indices(100, test_size=0.2, seed=7)
    second_train, second_test = train_test_indices(100, test_size=0.2, seed=7)

    np.testing.assert_array_equal(first_train, second_train)
    np.testing.assert_array_equal(first_test, second_test)
    assert len(first_test) == 20
    assert set(first_train).isdisjoint(set(first_test))


def _write_batt_fixture(
    path,
    molecules: list[tuple[str, bytes | str, tuple[float, float, float] | None]],
) -> None:
    with h5py.File(path, "w") as handle:
        for index, (key, smiles, dipole) in enumerate(molecules):
            group = handle.create_group(key)
            group.create_dataset(
                "smiles",
                data=np.asarray([smiles], dtype=h5py.string_dtype("utf-8")),
            )
            if dipole is not None:
                group.create_dataset("dipole", data=np.asarray(dipole, dtype=np.float32))


def test_build_features_writes_schema_and_honors_cache(tmp_path) -> None:
    h5_path = tmp_path / "Batt-P30K.h5"
    cache_path = tmp_path / "features.npz"
    _write_batt_fixture(
        h5_path,
        [
            ("CompMol0", "CCO", (1.0, 0.0, 0.0)),
            ("CompMol1", "CO", (0.0, 3.0, 4.0)),
        ],
    )

    rebuilt = build_features(h5_path, cache_path, rebuild_cache=False)
    cached = build_features(h5_path, cache_path, rebuild_cache=False)

    assert rebuilt.X.shape == (2, 2048)
    np.testing.assert_allclose(rebuilt.y, np.array([1.0, 5.0]))
    assert rebuilt.invalid_smiles_count == 0
    assert rebuilt.source_sha256 == hashlib.sha256(h5_path.read_bytes()).hexdigest()
    assert rebuilt.cache_status == "rebuilt"
    assert cached.cache_status == "cache_hit"


def test_build_features_rejects_cache_from_another_source(tmp_path) -> None:
    h5_path = tmp_path / "Batt-P30K.h5"
    cache_path = tmp_path / "features.npz"
    _write_batt_fixture(
        h5_path,
        [("CompMol0", "CCO", (1.0, 0.0, 0.0))],
    )
    build_features(h5_path, cache_path, rebuild_cache=False)
    _write_batt_fixture(
        h5_path,
        [
            ("CompMol0", "CCO", (1.0, 0.0, 0.0)),
            ("CompMol1", "CO", (0.0, 3.0, 4.0)),
        ],
    )

    with pytest.raises(CacheMismatchError, match="source SHA256"):
        build_features(h5_path, cache_path, rebuild_cache=False)

    rebuilt = build_features(h5_path, cache_path, rebuild_cache=True)
    assert rebuilt.cache_status == "rebuilt"
    assert rebuilt.X.shape[0] == 2


def test_build_features_counts_invalid_smiles(tmp_path) -> None:
    h5_path = tmp_path / "Batt-P30K.h5"
    cache_path = tmp_path / "features.npz"
    _write_batt_fixture(
        h5_path,
        [
            ("CompMol0", "CCO", (1.0, 0.0, 0.0)),
            ("CompMol1", "not-a-smiles", (1.0, 0.0, 0.0)),
        ],
    )

    bundle = build_features(h5_path, cache_path, rebuild_cache=False)

    assert bundle.X.shape[0] == 1
    assert bundle.invalid_smiles_count == 1
    np.testing.assert_array_equal(bundle.molecule_ids, np.array(["CompMol0"]))


def test_build_features_rejects_missing_dipole_dataset(tmp_path) -> None:
    h5_path = tmp_path / "Batt-P30K.h5"
    _write_batt_fixture(
        h5_path,
        [("CompMol0", "CCO", None)],
    )

    with pytest.raises(DatasetSchemaError, match="dipole"):
        build_features(h5_path, tmp_path / "features.npz", rebuild_cache=False)


def test_build_features_rejects_wrong_dipole_shape(tmp_path) -> None:
    h5_path = tmp_path / "Batt-P30K.h5"
    with h5py.File(h5_path, "w") as handle:
        group = handle.create_group("CompMol0")
        group.create_dataset(
            "smiles",
            data=np.asarray(["CCO"], dtype=h5py.string_dtype("utf-8")),
        )
        group.create_dataset("dipole", data=np.asarray([1.0, 2.0], dtype=np.float32))

    with pytest.raises(DatasetSchemaError, match="shape"):
        build_features(h5_path, tmp_path / "features.npz", rebuild_cache=False)
