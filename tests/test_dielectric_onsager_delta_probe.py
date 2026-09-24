from __future__ import annotations

import math

import numpy as np
import pytest
from rdkit import Chem

import probes.dielectric_onsager_delta_probe as probe
from electrolyte_ml.xtb_features import onsager_dielectric_estimate

AVOGADRO_PER_MOL = 6.02214076e23
DEBYE_TO_COULOMB_METRE = 3.335640951981521e-30
VACUUM_PERMITTIVITY_F_PER_M = 8.8541878128e-12
BOLTZMANN_CONSTANT_J_PER_K = 1.380649e-23


def _reference_onsager(
    dipole_debye: float,
    molar_volume_m3_mol: float,
    polarizability_A3: float,
    temperature_K: float,
) -> float:
    """Independent closed-form evaluation of the frozen Onsager equation."""
    alpha_density = (
        AVOGADRO_PER_MOL * polarizability_A3 * 1e-30 / (3.0 * molar_volume_m3_mol)
    )
    high_frequency = (1.0 + 2.0 * alpha_density) / (1.0 - alpha_density)
    reaction = (
        (dipole_debye**2 / molar_volume_m3_mol)
        * DEBYE_TO_COULOMB_METRE**2
        * AVOGADRO_PER_MOL
        / (9.0 * VACUUM_PERMITTIVITY_F_PER_M * BOLTZMANN_CONSTANT_J_PER_K * temperature_K)
    )
    linear = high_frequency + reaction * (high_frequency + 2.0) ** 2
    return (linear + math.sqrt(linear**2 + 8.0 * high_frequency**2)) / 4.0


def _row(name: str, smiles: str) -> dict[str, str]:
    molecule = Chem.MolFromSmiles(smiles)
    assert molecule is not None
    return {
        "name": name,
        "smiles": smiles,
        "heavy_atom_count": str(molecule.GetNumHeavyAtoms()),
    }


def test_onsager_four_parameter_matches_independent_reference() -> None:
    dipole, molar_volume, polarizability, temperature = 3.0, 8.0e-5, 10.0, 298.15
    expected = _reference_onsager(dipole, molar_volume, polarizability, temperature)
    assert onsager_dielectric_estimate(
        dipole, molar_volume, polarizability, temperature
    ) == pytest.approx(expected, rel=1e-12)
    # Recorded golden value for this four-parameter input point.
    assert onsager_dielectric_estimate(
        dipole, molar_volume, polarizability, temperature
    ) == pytest.approx(11.469425330435065, rel=1e-12)
    assert probe.ONSAGER_VERSION == "onsager_lorentz_lorenz_reaction_field_v1"
    assert set(probe.ONSAGER_INPUT_COLUMNS) == {
        "T_K",
        "dipole_D",
        "molar_volume_m3_mol",
        "polarizability_au",
        "polarizability_A3",
        "mu_sq_over_Vm",
        "alpha_over_Vm",
        "molecular_volume_A3",
    }


def test_onsager_parameters_are_the_polarizability_volume_and_molar_volume() -> None:
    """The fourth slot is T and the third slot is the A^3 polarizability volume."""
    temperature_sensitive = onsager_dielectric_estimate(3.0, 8.0e-5, 10.0, 293.15)
    assert temperature_sensitive != pytest.approx(onsager_dielectric_estimate(3.0, 8.0e-5, 10.0, 298.15))
    assert onsager_dielectric_estimate(3.0, 8.0e-5, 10.0, 293.15) > onsager_dielectric_estimate(
        3.0, 8.0e-5, 10.0, 298.15
    )
    # A molecular-volume style argument is not interchangeable with the molar volume.
    assert onsager_dielectric_estimate(3.0, 8.0e-5, 10.0, 298.15) != pytest.approx(
        onsager_dielectric_estimate(3.0, 1.1e-4, 10.0, 298.15)
    )


def test_onsager_breakdown_cross_checks_the_frozen_call() -> None:
    row = {
        "name": "probe-point",
        "dipole_D": "3.0",
        "molar_volume_m3_mol": "8.0e-5",
        "polarizability_A3": "10.0",
        "T_K": "298.15",
    }
    breakdown = probe.onsager_breakdown(row)
    assert set(breakdown) == {
        "alpha_density",
        "high_frequency_epsilon",
        "reaction_field_term",
        "onsager_epsilon",
    }
    assert breakdown["onsager_epsilon"] == pytest.approx(
        onsager_dielectric_estimate(3.0, 8.0e-5, 10.0, 298.15), rel=1e-12
    )
    assert breakdown["high_frequency_epsilon"] > 1.0
    assert 0.0 <= breakdown["alpha_density"] < 1.0


def test_onsager_input_assertions_fail_on_violations() -> None:
    with pytest.raises(ValueError):
        onsager_dielectric_estimate(float("inf"), 8.0e-5, 10.0, 298.15)
    with pytest.raises(ValueError):
        onsager_dielectric_estimate(-1.0, 8.0e-5, 10.0, 298.15)
    with pytest.raises(ValueError):
        onsager_dielectric_estimate(3.0, 0.0, 10.0, 298.15)
    with pytest.raises(ValueError):
        onsager_dielectric_estimate(3.0, 8.0e-5, -1.0, 298.15)
    with pytest.raises(ValueError):
        onsager_dielectric_estimate(3.0, 8.0e-5, 10.0, 0.0)
    # Lorentz-Lorenz polarizability density must stay below one.
    with pytest.raises(ValueError):
        onsager_dielectric_estimate(3.0, 1.0e-5, 200.0, 298.15)
    with pytest.raises(ValueError):
        probe.onsager_breakdown(
            {
                "name": "dense",
                "dipole_D": "3.0",
                "molar_volume_m3_mol": "1.0e-5",
                "polarizability_A3": "200.0",
                "T_K": "298.15",
            }
        )


def test_delta_feature_sets_never_touch_the_onsager_closure() -> None:
    closure = set(probe.ONSAGER_INPUT_COLUMNS)
    assert not closure & set(probe.B_CORE_FEATURE_NAMES)
    morgan_names = probe.morgan_feature_names(2048)
    assert len(morgan_names) == 2048
    probe.assert_delta_features_exclude_onsager_inputs(list(probe.B_CORE_FEATURE_NAMES))
    probe.assert_delta_features_exclude_onsager_inputs(
        [*probe.B_CORE_FEATURE_NAMES, *morgan_names]
    )
    assert probe.closure_intersection(list(probe.B_CORE_FEATURE_NAMES)) == []
    leaky = [*probe.B_CORE_FEATURE_NAMES, *probe.ONSAGER_INPUT_COLUMNS]
    assert probe.closure_intersection(leaky) == sorted(probe.ONSAGER_INPUT_COLUMNS)
    with pytest.raises(ValueError):
        probe.assert_delta_features_exclude_onsager_inputs(
            [*probe.B_CORE_FEATURE_NAMES, "T_K"]
        )
    with pytest.raises(ValueError):
        probe.assert_delta_features_exclude_onsager_inputs(["dipole_D"])
    with pytest.raises(ValueError):
        probe.assert_delta_features_exclude_onsager_inputs(["molecular_volume_A3"])


def test_core_feature_names_cover_the_functional_groups() -> None:
    assert set(probe.FUNCTIONAL_GROUP_SMARTS) <= set(probe.B_CORE_FEATURE_NAMES)
    assert "hbond_donor_sites" in probe.B_CORE_FEATURE_NAMES
    assert probe.DONOR_SMARTS == "[O,S,N;!H0]"


def test_domain_labels_split_the_four_structural_domains() -> None:
    rows = [
        _row("water", "O"),
        _row("dmso", "CS(=O)(=O)C"),
        _row("acetamide", "CC(=O)N"),
        _row("ethylammonium nitrate", "CC[NH3+].[O-][N+](=O)[O-]"),
        _row("tetramethylammonium dicyanamide", "C[N+](C)(C)C.C(#N)[N-]C#N"),
        _row("betaine", "C[N+](C)(C)CC(=O)[O-]"),
    ]
    descriptors = probe.chemical_descriptor_rows(rows)
    domains = list(probe.domain_labels(descriptors))
    assert domains == [
        "assoc_only",
        "none",
        "assoc_only",
        "both",
        "ionic_only",
        "none",
    ]
    by_name = dict(zip((row["name"] for row in rows), descriptors, strict=True))
    # The donor count comes from SMARTS, so water is a donor even though the
    # frozen hbd column stores 0 for it.
    assert by_name["water"]["hbond_donor_sites"] == 1.0
    assert by_name["water"]["n_charged_fragments"] == 0.0
    assert by_name["ethylammonium nitrate"]["n_charged_fragments"] == 2.0
    assert by_name["ethylammonium nitrate"]["n_fragments"] == 2.0
    # A zwitterion is one neutral fragment, so it is flagged but not counted ionic.
    assert by_name["betaine"]["zwitterion_flag"] == 1.0
    assert by_name["betaine"]["n_charged_fragments"] == 0.0
    assert by_name["dmso"]["hbond_donor_sites"] == 0.0
    assert probe.domain_label(assoc=True, ionic=True) == "both"
    assert probe.domain_label(assoc=True, ionic=False) == "assoc_only"
    assert probe.domain_label(assoc=False, ionic=True) == "ionic_only"
    assert probe.domain_label(assoc=False, ionic=False) == "none"


def test_functional_group_counts_follow_the_smarts_patterns() -> None:
    rows = [
        _row("diglyme", "COCCOCCOC"),
        _row("adiponitrile", "N#CCCCCC#N"),
        _row("ethylene carbonate", "C1COC(=O)O1"),
        _row("propylene carbonate", "CC1COC(=O)O1"),
    ]
    descriptors = probe.chemical_descriptor_rows(rows)
    by_name = dict(zip((row["name"] for row in rows), descriptors, strict=True))
    assert by_name["diglyme"]["n_ether"] == 3.0
    assert by_name["adiponitrile"]["n_nitrile"] == 2.0
    assert by_name["ethylene carbonate"]["n_carbonate"] == 1.0
    assert by_name["ethylene carbonate"]["n_ring"] == 1.0
    assert by_name["propylene carbonate"]["n_carbonate"] == 1.0
    assert by_name["propylene carbonate"]["n_ring"] == 1.0


def test_chemical_descriptors_assert_the_frozen_heavy_atom_count() -> None:
    row = _row("water", "O")
    row["heavy_atom_count"] = "99"
    with pytest.raises(ValueError, match="heavy atom count"):
        probe.chemical_descriptor_rows([row])
    bad = _row("broken", "O")
    bad["smiles"] = "this-is-not-a-smiles"
    with pytest.raises(ValueError, match="cannot parse SMILES"):
        probe.chemical_descriptor_rows([bad])


def test_core_feature_matrix_requires_finite_values() -> None:
    row = _row("water", "O")
    row.update({"hba": "1", "tpsa_A2": "25.3", "formal_charge": "0"})
    matrix = probe.core_feature_matrix([row])
    assert matrix.shape == (1, len(probe.B_CORE_FEATURE_NAMES))
    assert np.isfinite(matrix).all()
    row["tpsa_A2"] = "not-a-number"
    with pytest.raises(ValueError):
        probe.core_feature_matrix([row])


def test_residual_targets_round_trip_through_both_back_transforms() -> None:
    onsager = np.array([2.0, 5.0, 40.0])
    target = np.array([3.5, 55.0, 90.0])
    delta_raw, delta_log = probe.residual_targets(target, onsager)
    assert np.allclose(delta_raw, target - onsager)
    assert np.allclose(delta_log, np.log(target - 1.0) - np.log(onsager - 1.0))
    assert np.allclose(probe.invert_delta_raw(onsager, delta_raw), target)
    assert np.allclose(probe.invert_delta_log(onsager, delta_log), target)
    # Both back transforms clip at the physical floor of one.
    assert np.allclose(probe.invert_delta_raw(np.array([1.2]), np.array([-5.0])), [1.0])
    assert np.allclose(probe.invert_delta_log(np.array([1.2]), np.array([-50.0])), [1.0])
    with pytest.raises(ValueError):
        probe.residual_targets(np.array([0.5]), np.array([2.0]))
    with pytest.raises(ValueError):
        probe.residual_targets(np.array([2.0]), np.array([1.0]))
    with pytest.raises(ValueError):
        probe.invert_delta_log(np.array([1.0]), np.array([0.0]))


def test_structured_offset_uses_domain_medians_with_a_global_fallback() -> None:
    delta = np.array([1.0, 2.0, 3.0, 10.0, 12.0, -8.0])
    domains = ["none", "none", "none", "assoc_only", "assoc_only", "ionic_only"]
    offsets, fallback_domains = probe.structured_offset(delta, domains)
    assert offsets["none"] == pytest.approx(2.0)
    assert offsets["assoc_only"] == pytest.approx(11.0)
    assert offsets["ionic_only"] == pytest.approx(-8.0)
    assert offsets["both"] == pytest.approx(float(np.median(delta)))
    assert fallback_domains == ["both"]
    prediction = probe.structured_offset_predictions(
        np.array([5.0, 5.0]), ["both", "none"], offsets
    )
    assert np.allclose(prediction, [5.0 + float(np.median(delta)), 7.0])
    with pytest.raises(ValueError):
        probe.structured_offset(np.array([]), [])
    with pytest.raises(ValueError):
        probe.structured_offset(np.array([1.0, 2.0]), ["none"])


def test_split_metrics_covers_every_declared_metric_key() -> None:
    target = np.array([1.8, 5.0, 30.0, 78.0, 120.0])
    prediction = np.array([2.0, 4.0, 31.0, 30.0, 130.0])
    onsager = np.array([2.1, 3.0, 40.0, 20.0, 60.0])
    assoc = np.array([False, True, True, True, False])
    ionic = np.array([False, False, False, False, True])
    metrics = probe.split_metrics(
        target=target,
        prediction=prediction,
        onsager=onsager,
        assoc=assoc,
        ionic=ionic,
    )
    assert set(metrics) == set(probe.METRIC_KEYS)
    assert metrics["n_test"] == 5.0
    assert metrics["n_gt60"] == 2.0
    assert metrics["mae"] == pytest.approx(float(np.abs(target - prediction).mean()))
    assert metrics["mae_gt60"] == pytest.approx(29.0)
    # bias is mean(observed - predicted), so positive means under-prediction.
    assert metrics["bias_assoc"] == pytest.approx(float((target - prediction)[assoc].mean()))
    assert metrics["bias_ionic"] == pytest.approx(-10.0)
    assert probe.target_stratum(19.9) == "lt20"
    assert probe.target_stratum(20.0) == "20_60"
    assert probe.target_stratum(60.0) == "20_60"
    assert probe.target_stratum(60.1) == "gt60"


def test_bootstrap_components_resolve_the_expected_row_masks() -> None:
    target = np.array([10.0, 30.0, 80.0])
    prediction = target - np.array([1.0, 2.0, 5.0])
    assoc = np.array([False, True, True])
    ionic = np.array([False, False, True])
    values, mask = probe.bootstrap_component(
        "mae_assoc", target=target, prediction=prediction, assoc=assoc, ionic=ionic
    )
    assert mask.tolist() == [False, True, True]
    assert values.tolist() == [1.0, 2.0, 5.0]
    values, mask = probe.bootstrap_component(
        "bias_ionic", target=target, prediction=prediction, assoc=assoc, ionic=ionic
    )
    assert mask.tolist() == [False, False, True]
    assert values.tolist() == [1.0, 2.0, 5.0]
    values, mask = probe.bootstrap_component(
        "mae_gt60", target=target, prediction=prediction, assoc=assoc, ionic=ionic
    )
    assert mask.tolist() == [False, False, True]
    values, mask = probe.bootstrap_component(
        "mae_none", target=target, prediction=prediction, assoc=assoc, ionic=ionic
    )
    assert mask.tolist() == [True, False, False]
    values, mask = probe.bootstrap_component(
        "mae", target=target, prediction=prediction, assoc=assoc, ionic=ionic
    )
    assert mask.tolist() == [True, True, True]
    with pytest.raises(ValueError):
        probe.bootstrap_component(
            "rmse", target=target, prediction=prediction, assoc=assoc, ionic=ionic
        )


def test_cluster_bootstrap_delta_suppresses_tiny_domains_and_flags_identical_arms() -> None:
    rows = 24
    target = np.linspace(2.0, 20.0, rows)
    prediction = target.copy()
    assoc = np.zeros(rows, dtype=bool)
    ionic = np.zeros(rows, dtype=bool)
    assoc[4:] = True
    clusters = np.array([f"cluster:{index // 6}" for index in range(rows)], dtype=object)
    oof = np.vstack([prediction] * 2)
    result = probe.cluster_bootstrap_delta(
        baseline=oof,
        challenger=oof,
        target=target,
        clusters=clusters,
        assoc=assoc,
        ionic=ionic,
        metric="mae_assoc",
        n_resamples=50,
        seed=probe.SEED,
    )
    assert result["metric"] == "mae_assoc"
    assert result["point"] == pytest.approx(0.0)
    assert result["ci95"] == pytest.approx([0.0, 0.0])
    assert result["n_rows"] == 20
    assert result["n_clusters"] == 4
    tiny = probe.cluster_bootstrap_delta(
        baseline=oof,
        challenger=oof,
        target=target,
        clusters=clusters,
        assoc=assoc,
        ionic=ionic,
        metric="mae_gt60",
        n_resamples=50,
        seed=probe.SEED,
    )
    assert tiny["n_rows"] == 0
    assert tiny["ci95"] is None


def test_failure_classifier_orders_the_failure_types() -> None:
    assert (
        probe.classify_failure(
            target_value=80.0, prediction=float("nan"), assoc_flag=True, ionic_flag=False
        )
        == "nonphysical_prediction"
    )
    assert (
        probe.classify_failure(
            target_value=80.0, prediction=1.0, assoc_flag=True, ionic_flag=False
        )
        == "nonphysical_prediction"
    )
    assert (
        probe.classify_failure(
            target_value=80.0, prediction=40.0, assoc_flag=True, ionic_flag=False
        )
        == "high_epsilon_miss"
    )
    assert (
        probe.classify_failure(
            target_value=40.0, prediction=10.0, assoc_flag=True, ionic_flag=False
        )
        == "assoc_underprediction"
    )
    assert (
        probe.classify_failure(
            target_value=5.0, prediction=40.0, assoc_flag=False, ionic_flag=True
        )
        == "ionic_overprediction"
    )
    assert (
        probe.classify_failure(
            target_value=5.0, prediction=4.0, assoc_flag=False, ionic_flag=False
        )
        is None
    )


def test_gate_evaluation_requires_every_pre_registered_gate() -> None:
    def arm(mae: float, assoc: float, ionic: float, gt60: float, gt60_rho: float) -> dict:
        return {
            "mae": mae,
            "mae_assoc": assoc,
            "mae_ionic": ionic,
            "mae_gt60": gt60,
            "spearman_gt60": gt60_rho,
        }

    metrics = {
        "O0_onsager": arm(10.0, 16.0, 40.0, 90.0, -0.8),
        "O1_structured_offset": arm(9.0, 14.0, 39.0, 85.0, 0.0),
        "D0_delta_core": arm(8.0, 12.0, 30.0, 70.0, -0.7),
        "D1_delta_core_morgan": arm(9.5, 15.0, 40.0, 95.0, -0.9),
        "D2_delta_log": arm(11.0, 17.0, 30.0, 70.0, -0.7),
    }
    gates = probe.evaluate_gates(overall_metrics=metrics)
    assert gates["per_arm"]["D0_delta_core"]["passed"] is True
    assert gates["per_arm"]["D1_delta_core_morgan"]["passed"] is False
    assert "c_high_permittivity_improved" in gates["per_arm"]["D1_delta_core_morgan"][
        "failed_gates"
    ]
    assert gates["per_arm"]["D2_delta_log"]["passed"] is False
    assert gates["headline_arm"] == "D0_delta_core"
    assert gates["passed"] is True


def test_the_summary_binds_its_dataset_digest_to_the_working_tree() -> None:
    """The Onsager summary names the dataset it consumed; re-bind that pairing.

    ``scripts/verify_v032_benchmarks.py`` re-binds the v0.3.2 and v0.3.3 lineage
    summaries but does not cover this one, so the pairing is asserted here.  A
    provenance revision that moves the digest without re-deriving this summary
    would otherwise go unnoticed.
    """

    import hashlib
    import json

    from electrolyte_ml.exporting import canonical_text_sha256

    summary = json.loads(
        (probe.REPOSITORY_ROOT / "probes" / "dielectric_onsager_delta_summary.json")
        .read_text(encoding="utf-8")
    )
    dataset = probe.REPOSITORY_ROOT / summary["dataset_path"]
    recorded = summary["dataset_sha256"]
    assert recorded in {
        hashlib.sha256(dataset.read_bytes()).hexdigest(),
        canonical_text_sha256(dataset),
    }
