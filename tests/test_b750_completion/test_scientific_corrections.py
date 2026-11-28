"""Scientific regression checks for the completion corrections."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts/b740_expansion" / f"{name}.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


validation = module("validate_new_orca_results")
mixture = module("reassess_mixture_clusters")
safe = module("run_safe_liquid_ablation")
transfer = module("run_electronic_transfer")
quadrupole = module("audit_quadrupole")
GOOD = "| 1> ! r2SCAN-3c Opt\n| 2> * xyzfile 0 1 geom.xyz\nSCF CONVERGED AFTER 12 CYCLES\nTHE OPTIMIZATION HAS CONVERGED\nORCA TERMINATED NORMALLY\n"
VALUES = {"dipole_D": 1.0, "polarizability_au": 10.0, "total_energy_hartree": -50.0}


def test_orca_accepts_required_evidence():
    assert validation.parse_validated(GOOD, VALUES)["status"] == "ACCEPTED"


@pytest.mark.parametrize(
    "marker",
    [
        "ORCA TERMINATED NORMALLY",
        "THE OPTIMIZATION HAS CONVERGED",
        "SCF CONVERGED AFTER",
        "r2SCAN-3c",
        "xyzfile 0 1",
    ],
)
def test_normal_exit_alone_is_not_sufficient(marker):
    assert validation.parse_validated(GOOD.replace(marker, ""), VALUES)["status"] == "REJECTED"


@pytest.mark.parametrize(
    "key,value",
    [
        ("dipole_D", float("nan")),
        ("dipole_D", -1),
        ("polarizability_au", 0),
        ("polarizability_au", float("inf")),
    ],
)
def test_invalid_properties_cannot_be_accepted(key, value):
    assert validation.parse_validated(GOOD, {**VALUES, key: value})["status"] == "REJECTED"


def test_missing_outputs_keep_all_67_in_denominator(tmp_path):
    manifest = ROOT / "outputs/b740_expansion/dft_expansion/package_opt/manifest.json"
    result = validation.run(manifest, tmp_path / "absent", tmp_path / "out")
    assert result["expected"] == result["not_recovered"] == 67
    assert result["accepted"] == 0 and not result["complete"]
    assert result["full_transfer_status"] == "BLOCKED_INCOMPLETE_RESULTS"


@pytest.mark.parametrize("epsilon", [1, 2, 20, 80, 178.47])
def test_cm_high_dielectric_round_trip(epsilon):
    assert mixture.cm_prediction(epsilon, epsilon, 0.5) == pytest.approx(epsilon)


@pytest.mark.parametrize("phi", [0, 1])
def test_cm_endpoints_restore_pure_reference(phi):
    assert mixture.cm_prediction(80, 2, phi) == pytest.approx(80 if phi else 2)


def test_cm_refuses_unphysical_fraction():
    assert mixture.cm_prediction(80, 2, 1.1) is None


def test_single_cluster_does_not_invent_interval():
    rows = [
        {"doi": "one", "ik1": "a", "ik2": "b", "association_class": c, "resid_vs_lichtenecker": v}
        for c, v in [("APROTIC_PAIR", 1), ("PROTIC_PRESENT", 2)]
    ]
    out = mixture.cluster_bootstrap(rows, "doi", repetitions=50)
    assert out["difference"]["ci95"] is None
    assert out["difference"]["undefined_replicates"] == 50


def test_cluster_draw_preserves_both_classes_and_is_reproducible():
    rows = [
        {"doi": str(i), "association_class": c, "resid_vs_lichtenecker": i + offset}
        for i in range(5)
        for c, offset in [("APROTIC_PAIR", 0), ("PROTIC_PRESENT", 2)]
    ]
    a = mixture.cluster_bootstrap(rows, "doi", repetitions=50)
    b = mixture.cluster_bootstrap(rows, "doi", repetitions=50)
    assert a == b
    assert a["difference"]["ci95"] == pytest.approx([2, 2])


@pytest.mark.parametrize(
    "name",
    ["lippert_mataga_delta_f", "apparent_gk", "epsilon", "homo_lumo_gap_ev_v7", "unreviewed"],
)
def test_predictive_feature_guard_fails_closed(name):
    with pytest.raises(ValueError):
        safe.guard_features([name])


def test_duplicate_features_refused():
    with pytest.raises(ValueError):
        safe.guard_features(["mw", "mw"])


def test_scaling_does_not_use_other_test_points():
    x = np.asarray([[0.0], [1.0], [2.0]])
    y = np.asarray([1.0, 2.0, 3.0])
    one = safe.ridge_predict(x, y, np.asarray([[3.0]]))[0]
    many = safe.ridge_predict(x, y, np.asarray([[3.0], [1e12]]))[0]
    assert one == pytest.approx(many)


@pytest.mark.parametrize(
    "row",
    [{"dipole_D": "nan", "polarizability_au": "1"}, {"dipole_D": "1", "polarizability_au": "-1"}],
)
def test_transfer_rejects_invalid_electronics(row):
    assert transfer.electronic_values(row) is None


def test_transfer_constant_baseline_uses_training_mean():
    result = transfer.score(np.asarray([100.0, 101.0]), np.asarray([0.0, 0.0]), 0.0)
    assert result["training_mean_baseline_mae"] == 100.5


def test_duplicate_transfer_identities_refused():
    with pytest.raises(ValueError):
        transfer.unique_by_identity([{"inchikey": "x"}, {"inchikey": "x"}], "test")


def test_quadrupole_mention_never_becomes_a_validated_tensor(tmp_path):
    p = tmp_path / "job.out"
    p.write_text("QUADRUPOLE MOMENT\nORCA TERMINATED NORMALLY")
    result = quadrupole.inspect_output(p, ROOT)
    assert result["n_quadrupole_mentions"] == 1
    assert result["admission"].startswith("AUDIT_ONLY")


def test_persisted_validation_counts_and_safe_feature_counts():
    d = ROOT / "outputs/b740_expansion/dft_expansion/results_opt/validation"
    counts = json.loads((d / "summary.json").read_text())
    assert counts["accepted"] + counts["rejected"] + counts["not_recovered"] == 67
    result = json.loads(
        (
            ROOT / "outputs/b750_completion/leakage_audit/safe_liquid_ablation_summary.json"
        ).read_text()
    )
    assert result["n_core"] == result["n_paired_panel"] + result["n_excluded"]
    for arm in ("base", "augmented"):
        assert result[arm]["n_features"] == len(result[arm]["features"])
        safe.guard_features(result[arm]["features"])


retry = module("prepare_failed_opt_retries")


def test_restart_geometry_preserves_atom_order():
    assert retry.xyz_symbols("2\ncomment\nC 0 0 0\nO 1 0 0\n") == ["C", "O"]


@pytest.mark.parametrize("text", ["2\ncomment\nC 0 0 0\n", "1\ncomment\nC nan 0 0\n"])
def test_restart_refuses_bad_geometry(text):
    with pytest.raises(ValueError):
        retry.xyz_symbols(text)


def test_fallback_results_keep_the_original_full_denominator(tmp_path):
    import csv
    import shutil

    descriptors = (
        ROOT
        / "outputs/b740_expansion/dft_expansion/results_opt/validation/new_molecule_descriptors.csv"
    )
    with descriptors.open(encoding="utf-8") as handle:
        accepted = next(csv.DictReader(handle))
    source = (
        ROOT
        / "outputs/b740_expansion/dft_expansion/results_opt_retry/jobs"
        / accepted["inchikey"]
        / "job.out"
    )
    if not source.is_file():
        source = (
            ROOT
            / "outputs/b740_expansion/dft_expansion/results_opt/jobs"
            / accepted["inchikey"]
            / "job.out"
        )
    target = tmp_path / "original" / accepted["inchikey"] / "job.out"
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    result = validation.run(
        ROOT / "outputs/b740_expansion/dft_expansion/package_opt/manifest.json",
        tmp_path / "retry",
        tmp_path / "out",
        tmp_path / "original",
    )
    assert result["expected"] == 67 and result["accepted"] == 1 and result["not_recovered"] == 66
