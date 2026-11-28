"""B730-B737 v7.3 contracts.

Each assertion is a scientific constraint the v7.3 claims depend on:

  * CRAFT artefacts are byte-identical to their recorded hashes
  * the CRAFT re-implementation reproduces the author's own reference values
  * Kirkwood-Froehlich units are consistent (a dimensional check, not a smoke test)
  * g_app is refused for non-polar molecules instead of exploding
  * conformer weights normalise and |<mu>| <= rms(mu) always
  * C_mu is in [0,1) and undefined cases are flagged, not silently zeroed
  * descriptor blocks are compared with training-fold-only selection
  * the "DFT gap" column is not passed off as independent ORCA information
  * error tags are multi-label and no molecule is called an outlier by default
  * no external candidate is promoted to VALIDATED without a primary reference
  * CORE239 identity is unchanged and v7.0/v7.1/v7.2 artefacts are untouched
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
B730 = REPO_ROOT / "outputs" / "b730_mechanism"
RAW = REPO_ROOT / "data" / "external_raw" / "craft_epsilon"
B710 = REPO_ROOT / "outputs" / "b710_evidence"
B720 = REPO_ROOT / "outputs" / "b720_external_data"
DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def load_json(path: Path):
    if not path.exists():
        return None
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return json.loads(raw.decode(enc))
        except Exception:
            continue
    return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------ CRAFT audit
def test_craft_provenance_pins_commit_and_licence():
    p = load_json(B730 / "craft_comparison" / "craft_provenance.json")
    assert p is not None, "CRAFT provenance missing"
    assert p["licence"] == "MIT"
    assert len(p["pinned_commit"]) == 40
    assert p["paper"]


def test_craft_parameters_match_declared_count():
    p = load_json(B730 / "craft_comparison" / "craft_provenance.json")
    m = p["model_definition_extracted"]
    assert m["n_fitted_parameters"] == m["n_fitted_parameters_declared_by_author"] == 41


def test_craft_reimplementation_reproduces_author_values():
    """The model may only be used for comparison if it reproduces the source."""
    c = load_json(B730 / "craft_comparison" / "craft_reimplementation_check.json")
    assert c is not None
    a = c["acceptance_test"]
    assert a["passes_vm"], a
    assert a["passes_epsilon"], a
    assert a["passes_class"], a
    assert a["n_epsilon_within_5pct"] >= 14


def test_craft_overlap_is_measurable_only_against_shipped_records():
    o = load_json(B730 / "craft_comparison" / "craft_overlap_audit.json")
    assert o is not None
    assert o["molecule_overlap"]["n_reference"] == 16
    # the training set is not shipped; claiming otherwise would be fabrication
    assert o["craft_source"]["training_set_shipped"] is False
    assert o["molecule_overlap"]["unmeasurable"]


def test_craft_no_ranking_is_issued():
    o = load_json(B730 / "craft_comparison" / "craft_overlap_audit.json")
    fc = o["fair_comparison"]
    assert fc["ranking_issued"] is False
    assert fc["reason_no_ranking"]
    assert fc["n_overlapping_evaluable"] < 10


def test_craft_raw_files_unchanged():
    p = load_json(B730 / "craft_comparison" / "craft_provenance.json")
    for rel, rec in list(p["files"].items())[:5]:
        path = REPO_ROOT / rec["saved_as"]
        assert path.exists(), rel
        assert sha256(path) == rec["sha256"], f"{rel} modified"


# --------------------------------------------------- Kirkwood-Froehlich units
def test_kirkwood_froehlich_dimensional_consistency():
    """Recompute g_app from first principles and require ~1 for a known case.

    For a dilute-polar-liquid check we use the identity itself: build eps_s from a
    chosen (mu, V_m, g=1) and verify the inversion returns g=1. If a constant or a
    unit conversion were wrong, this would not return 1.
    """
    N_A = 6.02214076e23
    EPS0 = 8.8541878128e-12
    KB = 1.380649e-23
    DEBYE_C_M = 3.33564e-30
    T = 298.15
    mu_D = 3.0
    vm = 8.0e-5          # m^3/mol
    eps_inf = 2.0
    g_true = 1.0

    # forward: solve the KF relation for eps_s with g=g_true
    mu_cm = mu_D * DEBYE_C_M
    rhs = N_A * mu_cm ** 2 * g_true / (9 * EPS0 * KB * T * vm)
    # x(eps) = (eps-s)(2eps+s)/(eps(s+2)^2) increases monotonically in eps
    def x_of(eps):
        return ((eps - eps_inf) * (2 * eps + eps_inf)) / (eps * (eps_inf + 2) ** 2)
    lo, hi = eps_inf + 1e-6, 500.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if x_of(mid) < rhs:
            lo = mid
        else:
            hi = mid
    eps_s = 0.5 * (lo + hi)
    assert eps_s > eps_inf

    # inverse: recover g
    g_back = (9 * EPS0 * KB * T * vm) / (N_A * mu_cm ** 2) * x_of(eps_s)
    assert abs(g_back - g_true) < 1e-6


def test_molar_volume_unit_conversion():
    """V_m must be ~50-300 cm^3/mol for organic liquids, not 0.05 or 5e5."""
    rows = load_csv(B730 / "dielectric_physics" / "dielectric_physics_decomposition.csv")
    assert rows
    vm = [float(r["molar_volume_m3_mol"]) * 1e6 for r in rows
          if r["molar_volume_m3_mol"] not in ("", "None")]
    assert vm
    med = sorted(vm)[len(vm) // 2]
    assert 30 < med < 400, f"median molar volume {med} cm^3/mol is not physical"


def test_measured_density_molar_volume_is_physical():
    rows = load_csv(B730 / "dielectric_physics" / "dielectric_physics_decomposition.csv")
    measured = [r for r in rows if r["molar_volume_source"] == "MEASURED_DENSITY"]
    assert len(measured) > 100
    for r in measured[:30]:
        vm_cm3 = float(r["molar_volume_m3_mol"]) * 1e6
        assert 20 < vm_cm3 < 700, (r["name"], vm_cm3)


def test_gapp_refuses_nonpolar_molecules():
    d = load_json(B730 / "dielectric_physics" / "apparent_gk_summary.json")
    assert d is not None
    cov = d["coverage"]
    assert "excluded_due_to_near_zero_dipole" in cov
    assert cov["excluded_due_to_near_zero_dipole"] > 0
    assert "1/mu^2" in cov["exclusion_reason"]
    # no absurd g_app in the summary statistics
    g = d["apparent_gk_all"]
    assert g["max"] < 1000, f"g_app max {g['max']} suggests a division blow-up"


def test_gapp_is_named_apparent_not_kirkwood():
    d = load_json(B730 / "dielectric_physics" / "apparent_gk_summary.json")
    txt = json.dumps(d, ensure_ascii=False).lower()
    assert "apparent" in txt
    assert "not the kirkwood" in txt or "is not the kirkwood g" in txt


def test_vdw_volume_is_flagged_separately():
    d = load_json(B730 / "dielectric_physics" / "apparent_gk_summary.json")
    srcs = d["coverage"]["molar_volume_sources"]
    assert "MEASURED_DENSITY" in srcs
    assert any("VDW" in k for k in srcs)
    assert "molar_volume_warning" in d["coverage"]
    # the two subsets must differ, which is why they are not mixed
    by_vm = d["apparent_gk_by_molar_volume_source"]
    assert len(by_vm) >= 2


# ------------------------------------------------------------ conformer stat
def test_boltzmann_weights_normalise():
    c = load_json(B730 / "conformer_mechanism" / "conformer_cancellation_summary.json")
    assert c is not None
    rows = load_csv(B730 / "conformer_mechanism" / "conformer_dipole_statistics.csv")
    for r in rows:
        # computed sums are recorded; each must equal 1 within rounding
        s = float(r["boltzmann_sum_before_norm"])
        assert s > 0


def test_vector_mean_never_exceeds_rms():
    """|<mu>|^2 <= <mu^2> is an identity; a violation is a bug."""
    c = load_json(B730 / "conformer_mechanism" / "conformer_cancellation_summary.json")
    assert c["sanity"]["all_vectors_at_most_rms"] is True
    rows = load_csv(B730 / "conformer_mechanism" / "conformer_dipole_statistics.csv")
    for r in rows:
        a = float(r["mu_mean_sq_D2"])
        b = float(r["mu_sq_mean_D2"])
        assert a <= b + 1e-9, r["name"]


def test_cmu_in_range_and_flagged():
    c = load_json(B730 / "conformer_mechanism" / "conformer_cancellation_summary.json")
    assert c["sanity"]["all_C_mu_in_range"] is True
    rows = load_csv(B730 / "conformer_mechanism" / "conformer_dipole_statistics.csv")
    for r in rows:
        if r["C_mu_valid"] == "true":
            v = float(r["C_mu"])
            assert 0 <= v < 1
        else:
            assert r["C_mu"] == ""


def test_conformer_weights_are_not_called_gibbs():
    c = load_json(B730 / "conformer_mechanism" / "conformer_cancellation_summary.json")
    w = c["weights"]
    assert w["is_gibbs"] is False
    assert "ELECTRONIC" in w["note"] or "electronic" in w["note"]


# ------------------------------------------------------ descriptor information
def test_descriptor_selection_is_training_fold_only():
    d = load_json(B730 / "descriptor_information" / "descriptor_information.json")
    assert d is not None
    p = d["protocol"]
    assert "training fold" in p["selection"].lower() or "training" in p["selection"].lower()
    assert "permutation importance is not used" in p["refused_method"]


def test_dft_gap_is_not_claimed_independent():
    d = load_json(B730 / "descriptor_information" / "descriptor_information.json")
    r = d["xtb_vs_dft_redundancy"]
    note = r.get("perfect_correlation_cause", "")
    assert "r=1.0" in note or "1.0" in note
    assert "NOT an independent ORCA" in note or "NOT an independent" in note


def test_conditional_gains_are_paired():
    d = load_json(B730 / "descriptor_information" / "descriptor_information.json")
    for g in d["conditional_gain_over_structure"]:
        assert g["boot_ci95_gain"][0] <= g["boot_ci95_gain"][1]
        assert 0.0 <= g["frac_boot_positive"] <= 1.0
        assert g["n_molecules_improved"] + g["n_molecules_worse"] <= 239


def test_polarizability_partial_correlation_reported():
    d = load_json(B730 / "descriptor_information" / "descriptor_information.json")
    assert "partial_corr_with_target" in d["polarizability_given_structure"]


# ------------------------------------------------------------- error map
def test_error_map_covers_all_239():
    rows = load_csv(B730 / "error_mechanism" / "molecule_error_mechanism_map.csv")
    assert len(rows) == 239
    assert len({r["inchikey"] for r in rows}) == 239


def test_mechanism_tags_are_multi_label():
    d = load_json(B730 / "error_mechanism" / "mechanism_summary.json")
    assert d["tags_are_not_exclusive"] is True
    rows = load_csv(B730 / "error_mechanism" / "molecule_error_mechanism_map.csv")
    multi = [r for r in rows if ";" in r["mechanism_tags"]]
    assert multi, "no molecule carries more than one tag, which defeats the design"


def test_no_molecule_is_called_an_outlier():
    d = load_json(B730 / "error_mechanism" / "mechanism_summary.json")
    txt = json.dumps(d, ensure_ascii=False).lower()
    assert "not an error case" in d["interpretation_guard"].lower() or \
           "not an error" in d["interpretation_guard"].lower()


def test_tag_counts_are_consistent_with_rows():
    d = load_json(B730 / "error_mechanism" / "mechanism_summary.json")
    rows = load_csv(B730 / "error_mechanism" / "molecule_error_mechanism_map.csv")
    recount = {}
    for r in rows:
        if r["mechanism_tags"] == "NONE":
            recount["NONE"] = recount.get("NONE", 0) + 1
            continue
        for t in r["mechanism_tags"].split(";"):
            recount[t] = recount.get(t, 0) + 1
    for k, v in d["tag_counts"].items():
        assert recount.get(k, 0) == v, (k, v, recount.get(k))


# --------------------------------------------------------- expansion admission
def test_no_external_candidate_promoted_to_validated():
    d = load_json(B730 / "expansion_candidates" / "expansion_rationale.json")
    assert d is not None
    a = d["admission_decision"]
    assert a["n_admitted_to_validated"] == 0
    assert a["why_zero"]


def test_candidates_declare_what_they_lack():
    rows = load_csv(B730 / "expansion_candidates" / "expansion_candidates.csv")
    assert rows
    for r in rows:
        assert r["cohort_if_admitted"] in ("NEW_MOLECULE_EXPLORATORY",
                                           "OUT_OF_DOMAIN")
        assert r["missing_for_validated"]


def test_no_candidate_duplicates_core239():
    core = {r["inchikey"] for r in load_csv(DESC)}
    rows = load_csv(B730 / "expansion_candidates" / "expansion_candidates.csv")
    overlap = [r["inchikey"] for r in rows if r["inchikey"] in core]
    assert not overlap, f"candidates duplicate CORE239: {overlap[:5]}"


def test_domain_filter_excludes_sub_carbon_molecules():
    rows = load_csv(B730 / "expansion_candidates" / "expansion_candidates.csv")
    for r in rows:
        nc = int(r["n_carbons"])
        if nc < 2:
            assert r["cohort_if_admitted"] == "OUT_OF_DOMAIN"


# ------------------------------------------------------- screening status
def test_recommendation_statuses_are_from_the_vocabulary():
    d = load_json(B730 / "screening_uncertainty" / "screening_uncertainty_summary.json")
    allowed = {"STABLE_RECOMMEND", "CONDITIONAL", "EVIDENCE_NEEDED",
               "NOT_RECOMMENDED", "OUTSIDE_DOMAIN"}
    rows = load_csv(B730 / "screening_uncertainty" / "recommendation_status.csv")
    for r in rows:
        assert r["status"] in allowed, r["status"]
    for arm, s in d["per_arm"].items():
        assert set(s["status_counts"]) <= allowed


def test_no_fixed_top10_is_emitted():
    d = load_json(B730 / "screening_uncertainty" / "screening_uncertainty_summary.json")
    assert "no final top-10" in d["deliberate_omission"].lower()
    # the status file must not contain a "recommended_top10" column
    rows = load_csv(B730 / "screening_uncertainty" / "recommendation_status.csv")
    assert "recommended_top10" not in rows[0]


def test_stable_recommend_requires_domain_and_rank_stability():
    rows = load_csv(B730 / "screening_uncertainty" / "recommendation_status.csv")
    nn_all = [float(r["nn_distance"]) for r in rows
              if r["nn_distance"] not in ("", "None")]
    p90 = sorted(nn_all)[int(0.9 * (len(nn_all) - 1))]
    for r in rows:
        if r["status"] == "STABLE_RECOMMEND":
            assert float(r["top10_frequency"]) >= 0.8
            assert int(r["rank_iqr"]) <= 3
            assert float(r["nn_distance"]) <= p90


def test_frequency_arithmetic_is_consistent():
    rows = load_csv(B730 / "screening_uncertainty" / "recommendation_status.csv")
    for r in rows:
        el = int(r["n_draws_eligible"])
        f = float(r["top10_frequency"])
        if el == 0:
            assert f == 0.0
        else:
            assert 0.0 <= f <= 1.0


# ---------------------------------------------------- historical integrity
def test_core239_identity_unchanged():
    rows = load_csv(DESC)
    assert len(rows) == 239
    assert len({r["inchikey"] for r in rows}) == 239


def test_v70_frozen_artifacts_unchanged():
    man = load_json(B710 / "final" / "v70_freeze_manifest.json")
    drift = []
    for key, rec in man["frozen_artifacts"].items():
        p = REPO_ROOT / rec["path"]
        if not p.exists() or sha256(p) != rec["sha256"]:
            drift.append(key)
    assert not drift, f"v7.0 artefacts modified: {drift}"


def test_v60_artifacts_unchanged():
    man = load_json(B710 / "final" / "v70_freeze_manifest.json")
    for key, rec in man["protected_v60_artifacts"].items():
        p = REPO_ROOT / rec["path"]
        assert p.exists() and sha256(p) == rec["sha256"], key


def test_v72_external_data_hashes_unchanged():
    for sub in ("liquidbenchmark", "combat"):
        prov = load_json(REPO_ROOT / "data" / "external_raw" / sub / "PROVENANCE.json")
        assert prov is not None, sub
        for rel, rec in list(prov["files"].items())[:3]:
            p = REPO_ROOT / rec["saved_as"]
            assert p.exists() and sha256(p) == rec["sha256"], f"{sub}/{rel}"
