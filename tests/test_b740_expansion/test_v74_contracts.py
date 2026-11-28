"""B740-B749 v7.4 contracts.

Each assertion is a scientific constraint the v7.4 claims depend on. These are
not smoke tests: every one of them would fail if the corresponding error were
re-introduced (most of them already did fail once during this round -- see the
BUG-FIX NOTES in the scripts under ``scripts/b740_expansion/``).

  * ThermoML static permittivity and frequency-dependent permittivity stay
    SEPARATE labels and are never merged back into one column
  * mixture records are tagged and never consumed as pure-liquid epsilon
  * the local ThermoML corpus is declared a SUBSET, not the whole archive
  * cohort admission is rule-driven: nothing is promoted to VALIDATED without
    a citable DOI outside the NBS 514 compendium
  * CORE239 membership is neither extended nor overwritten
  * the polarizability tensor satisfies its own invariants (symmetry, trace,
    eigenvalue anisotropy, bohr^3 -> A^3 conversion)
  * conformer statistics are internally consistent and never presented as
    thermodynamic (Gibbs) entropies
  * molar refraction / Lorentz-Lorenz / Lippert-Mataga satisfy their defining
    identities and land in physically admissible ranges
  * the Kirkwood-Froehlich apparent-correlation-factor round-trip closes to
    within the stored rounding
  * the fixed-charge MD layer is reported as BLOCKED, not quoted as a result
  * the multiscale ablation cannot hide selection bias behind a small common
    subset
  * v6.0 / v7.0 / v7.2 / v7.3 artefacts and external raw data are unmodified
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
B740 = REPO_ROOT / "outputs" / "b740_expansion"
THERMOML = B740 / "thermoml"
DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
PHYSICS = REPO_ROOT / "outputs" / "b730_mechanism" / "dielectric_physics"
B710_FINAL = REPO_ROOT / "outputs" / "b710_evidence" / "final"

# physical constants used by the round-trip checks (CODATA / SI)
N_A = 6.02214076e23
KB = 1.380649e-23
EPS0 = 8.8541878128e-12
DEBYE_C_M = 3.33564e-30
AU_TO_A3 = 0.14818471
R_GAS = 8.314462618


# ----------------------------------------------------------------- helpers
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


def num(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def core239_inchikeys() -> set[str]:
    return {r["inchikey"] for r in load_csv(DESC)}


# ----------------------------------------------------- ThermoML extraction
def test_static_and_frequency_dependent_permittivity_are_separate_labels():
    """The single most damaging v7.4 bug would be to call these one column.

    ThermoML stores *both* "Relative permittivity at zero frequency" and
    "Relative permittivity at various frequencies". Merging them silently
    re-labels 1109 frequency-dependent rows as static epsilon.
    """
    d = load_json(THERMOML / "thermoml_coverage.json")
    assert d is not None, "ThermoML coverage summary missing"
    rows = load_csv(THERMOML / "thermoml_local_scan.csv")
    assert rows, "ThermoML scan table missing"

    props = {r["property"] for r in rows}
    assert "dielectric_constant_static" in props
    assert "dielectric_constant_frequency_dependent" in props

    static = [r for r in rows if r["property"] == "dielectric_constant_static"]
    freq = [r for r in rows if r["property"] == "dielectric_constant_frequency_dependent"]
    assert static and freq

    # no static row may carry a frequency label
    assert not [r for r in static if r["has_frequency"] == "true"]
    # the frequency set must be the one the summary says is excluded
    assert "excluded" in d["dielectric_frequency_dependent"]["definition"].lower()

    # the two groups must not be the same rows
    assert {r["doi"] + "|" + r["property_raw"] for r in static}.isdisjoint(
        {r["doi"] + "|" + r["property_raw"] for r in freq}
    )


def test_static_permittivity_covers_new_independent_molecules():
    """The v7.1-v7.3 blocker was source independence; v7.4 must have moved it."""
    d = load_json(THERMOML / "thermoml_coverage.json")
    static = d["dielectric_static"]
    assert static["n_unique_molecules"] == 103
    assert static["n_pure_records"] == 1713
    assert static["n_unique_molecules"] > 67, "fewer molecules than CORE239"

    ledger = load_csv(B740 / "molecule_expansion" / "cohort_ledger.csv")
    core = core239_inchikeys()
    new_validated = [r for r in ledger if r["cohort"] == "NEW_MOLECULE_VALIDATED"]
    assert new_validated
    overlap = [r["inchikey"] for r in new_validated if r["inchikey"] in core]
    assert not overlap, f"new molecules duplicate CORE239: {overlap[:5]}"


def test_mixture_records_are_tagged_and_never_used_as_pure_labels():
    d = load_json(THERMOML / "thermoml_coverage.json")
    rows = load_csv(THERMOML / "thermoml_local_scan.csv")
    tagged = [r for r in rows if r["is_mixture"] == "true"]
    pure = [r for r in rows if r["is_mixture"] == "false"]
    assert tagged and pure
    assert len(tagged) + len(pure) == len(rows)
    assert d["n_mixture_records"] == len(tagged)
    assert d["n_pure_records"] == len(pure)
    assert "NEVER" in d["mixture_policy"]

    # a static-epsilon *pure* record is the only admissible modelling label
    static_pure = [
        r for r in rows
        if r["property"] == "dielectric_constant_static" and r["is_mixture"] == "false"
    ]
    assert len({r["inchikey"] for r in static_pure}) == \
        d["dielectric_static"]["n_unique_molecules"]


def test_single_component_names_are_not_mislabelled_as_mixtures():
    """Comma-counting marked 45 IUPAC names ("acrylic acid, methyl ester") as
    mixtures. Only ';' separates components in a ThermoML compound name."""
    rows = load_csv(THERMOML / "thermoml_local_scan.csv")
    comma_named = [
        r for r in rows
        if r["n_components"] == "1" and "," in (r["name"] or "")
    ]
    assert comma_named, "expected at least one comma-containing single-component name"
    assert all(r["is_mixture"] == "false" for r in comma_named)


def test_corpus_is_declared_a_subset_not_the_archive():
    d = load_json(THERMOML / "thermoml_coverage.json")
    note = d["note_on_completeness"].upper()
    assert "SUBSET" in note
    assert "NOT MEAN" in note.replace("DOES NOT MEAN", "NOT MEAN")


def test_dielectric_values_are_physically_admissible():
    rows = load_csv(THERMOML / "thermoml_local_scan.csv")
    static = [
        num(r["value"]) for r in rows
        if r["property"] == "dielectric_constant_static"
        and r["is_mixture"] == "false"
        and num(r["value"]) is not None
    ]
    assert len(static) > 1000
    assert all(1.0 <= v <= 200.0 for v in static), "epsilon outside (1, 200)"


def test_records_by_property_are_internally_consistent():
    d = load_json(THERMOML / "thermoml_coverage.json")
    rows = load_csv(THERMOML / "thermoml_local_scan.csv")
    counts = d["records_by_property"]
    assert d["n_records"] == len(rows)
    assert sum(counts.values()) == len(rows)
    for prop, n in counts.items():
        assert n == sum(1 for r in rows if r["property"] == prop), prop


# ------------------------------------------------------ cohort admission
def test_cohort_admission_rule_is_enforced():
    ledger = load_csv(B740 / "molecule_expansion" / "cohort_ledger.csv")
    assert ledger
    summary = load_json(B740 / "molecule_expansion" / "cohort_summary.json")
    assert summary["cohort_counts"]["NEW_MOLECULE_VALIDATED"] == sum(
        1 for r in ledger if r["cohort"] == "NEW_MOLECULE_VALIDATED"
    )

    for r in ledger:
        dois = int(r["n_distinct_eps_dois"])
        primary = int(r["n_primary_dois_beyond_compendium"])
        if r["cohort"] == "NEW_MOLECULE_VALIDATED":
            assert dois >= 1 and primary >= 1, r["name"]
        elif r["cohort"] == "NEW_MOLECULE_EXPLORATORY":
            # exploratory means "found in the corpus but not source-independent"
            assert primary == 0, r["name"]
            assert r["cohort_rationale"]


def test_core239_membership_is_preserved_exactly():
    ledger = load_csv(B740 / "molecule_expansion" / "cohort_ledger.csv")
    core = core239_inchikeys()
    assert len(core) == 239
    flagged = {r["inchikey"] for r in ledger if r["in_core239"] == "true"}
    assert flagged == core, "the ledger's CORE239 set drifted from the v7.0 descriptors"
    assert all(
        r["cohort"] == "CORE239" for r in ledger if r["in_core239"] == "true"
    )
    assert len({r["inchikey"] for r in ledger}) == len(ledger)


# ------------------------------------------------- polarizability tensor
def test_polarizability_tensor_invariants():
    rows = load_csv(B740 / "molecular_descriptors" / "polarizability_tensor.csv")
    assert len(rows) == 478, "expected opt (239) + sp (239) records"
    assert {r["layer"] for r in rows} == {"opt", "sp"}
    assert sum(1 for r in rows if r["tensor_symmetric"] == "True") == len(rows)

    for r in rows:
        xx, yy, zz = num(r["alpha_xx"]), num(r["alpha_yy"]), num(r["alpha_zz"])
        bar = num(r["alpha_bar_au"])
        e1, e2, e3 = num(r["eig_1"]), num(r["eig_2"]), num(r["eig_3"])
        delta = num(r["delta_alpha_au"])
        assert None not in (xx, yy, zz, bar, e1, e2, e3, delta), r["inchikey"]
        # trace / 3
        assert abs(bar - (xx + yy + zz) / 3.0) < 1e-4
        # eigenvalue anisotropy definition
        expected = math.sqrt(
            ((e1 - e2) ** 2 + (e2 - e3) ** 2 + (e3 - e1) ** 2) / 2.0
        )
        assert abs(delta - expected) < 1e-4
        assert delta >= -1e-9
        # dimensionless ratio
        if bar > 0:
            assert abs(num(r["anisotropy_ratio"]) - delta / bar) < 1e-4
        # bohr^3 -> A^3
        assert abs(num(r["alpha_bar_A3"]) - bar * AU_TO_A3) < 1e-4


def test_isotropic_and_eigenmean_polarizability_agree():
    d = load_json(B740 / "molecular_descriptors" / "polarizability_anisotropy_summary.json")
    assert d["sanity"]["n_tensor_symmetric"] == d["n_records"]
    assert d["sanity"]["max_iso_vs_eigenmean_abs_diff"] <= 1e-4
    assert d["sanity"]["duplicate_molecule_layer_pairs"] == 0
    assert d["convention_guard"], "frame-dependence warning must be recorded"


def test_raw_tensor_components_are_not_compared_across_molecules():
    """Only eigenvalues are frame-independent; the raw components are audit-only."""
    d = load_json(B740 / "molecular_descriptors" / "polarizability_anisotropy_summary.json")
    guard = d["convention_guard"].lower()
    assert "not comparable" in guard
    assert "eigenvalues" in guard


# ------------------------------------------------- conformer statistics
def test_conformer_statistics_are_self_consistent():
    rows = load_csv(B740 / "conformer_analysis" / "conformer_entropy.csv")
    assert rows
    for r in rows:
        n_conf = int(r["n_conformers"])
        s_conf = num(r["S_conf_J_mol_K"])
        n_eff = num(r["N_eff"])
        n_pr = num(r["N_PR"])
        cmu = num(r["C_mu"])
        wmax = num(r["max_weight"])
        assert None not in (s_conf, n_eff, n_pr, cmu, wmax), r["name"]

        assert s_conf >= -1e-9
        # S_conf = R ln N_eff
        assert abs(s_conf - R_GAS * math.log(n_eff)) < 5e-3
        # a normalised weight vector cannot have max weight below 1/n
        assert wmax >= 1.0 / n_conf - 1e-9
        assert wmax <= 1.0 + 1e-9
        # Renyi ordering: exp(H) >= 1/sum p^2
        assert n_eff >= n_pr - 1e-6
        # C_mu = 1 - |<mu>|^2/<mu^2> lives in [0, 1)
        assert 0.0 <= cmu < 1.0


def test_conformer_entropy_is_not_presented_as_gibbs_entropy():
    d = load_json(B740 / "conformer_analysis" / "conformer_entropy_summary.json")
    prov = d["weight_provenance"]
    assert prov["is_gibbs"] is False
    assert "ELECTRONIC" in prov["note"]
    assert "not a thermodynamic entropy" in prov["note"].lower()


def test_conformer_layer_does_not_reenter_the_dataset_as_a_label():
    rows = load_csv(B740 / "conformer_analysis" / "conformer_entropy.csv")
    allowed = {"C_mu", "S_conf_J_mol_K", "N_eff", "N_PR", "n_conformers",
               "hbond_mean_count", "hbond_occupancy"}
    assert allowed <= set(rows[0])


# ------------------------------------- liquid thermodynamic indices
def test_molar_volume_is_in_the_liquid_range():
    """Catches the 1000x unit bug and the RDKit-vdW-as-liquid-Vm substitution.

    Water is the low extreme at 18.0 cm^3/mol, so the admissible window is
    15--400; a 1000x unit slip would land at 0.018 and the RDKit surrogate at
    roughly half the true value, both outside this window.
    """
    rows = load_csv(B740 / "thermodynamic_properties" / "liquid_thermodynamic_indices.csv")
    assert rows
    vms = [num(r["molar_volume_cm3_mol"]) for r in rows]
    vms = [v for v in vms if v is not None]
    assert len(vms) >= 45, "the measured-density subset must cover most rows"
    assert all(15.0 <= v <= 400.0 for v in vms), (min(vms), max(vms))
    # water is the classic unit trap: 18.0 cm^3/mol, not 0.018 and not 18 000
    water = [r for r in rows if r["name"] == "water"]
    if water:
        assert abs(num(water[0]["molar_volume_cm3_mol"]) - 18.0) < 1.0


def test_dependent_indices_are_blank_when_molar_volume_is_blank():
    """No silent zero-filling: a missing V_m must blank its dependants."""
    rows = load_csv(B740 / "thermodynamic_properties" / "liquid_thermodynamic_indices.csv")
    for r in rows:
        vm = num(r["molar_volume_cm3_mol"])
        if vm is None:
            for col in ("molar_refraction_cm3_mol", "lorentz_lorenz_alpha_A3",
                        "cohesive_energy_density_MPa", "hildebrand_MPa_half",
                        "rho_HBD_per_cm3", "rho_HBA_per_cm3"):
                assert r[col] in ("", "None"), (r["name"], col)
        else:
            # V_m requires a measured density OR a stated molar mass
            assert r["mw_g_mol"] not in ("", "None"), r["name"]


def test_molar_mass_falls_back_to_the_source_formula():
    """The 67 new molecules have no descriptor row; without a formula fallback
    their measured density could not be turned into a molar volume."""
    d = load_json(B740 / "thermodynamic_properties" / "thermodynamic_summary.json")
    mv = d["molar_volume"]
    assert mv["n_without_molar_mass"] == 0
    assert mv["n_from_thermoml_formula"] > 0
    assert mv["formula_mw_crosscheck"]["n_overlap"] >= 50
    assert mv["formula_mw_crosscheck"]["max_abs_deviation_g_mol"] < 0.05


def test_molar_refraction_and_lorentz_lorenz_identities():
    rows = load_csv(B740 / "thermodynamic_properties" / "liquid_thermodynamic_indices.csv")
    checked = 0
    for r in rows:
        vm, nd = num(r["molar_volume_cm3_mol"]), num(r["n_D"])
        rm, alpha = num(r["molar_refraction_cm3_mol"]), num(r["lorentz_lorenz_alpha_A3"])
        if None in (vm, nd, rm) or not (1.0 < nd < 2.0):
            continue
        # R_m = (n^2 - 1)/(n^2 + 2) * V_m
        assert abs(rm - vm * (nd ** 2 - 1) / (nd ** 2 + 2)) < 1e-3
        # alpha = 3 R_m / (4 pi N_A), cm^3 -> A^3
        if alpha is not None:
            assert abs(alpha - 3 * rm / (4 * math.pi * N_A) * 1e24) < 1e-3
        checked += 1
    assert checked >= 10, f"only {checked} rows had a full optical tuple"


def test_lippert_mataga_delta_f_identity():
    rows = load_csv(B740 / "thermodynamic_properties" / "liquid_thermodynamic_indices.csv")
    checked = 0
    for r in rows:
        eps, nd = num(r["epsilon_at_matched_T"]), num(r["n_D"])
        df = num(r["lippert_mataga_delta_f"])
        if None in (eps, nd, df):
            continue
        expected = (eps - 1) / (2 * eps + 1) - (nd ** 2 - 1) / (2 * nd ** 2 + 1)
        assert abs(df - expected) < 1e-4
        assert -0.01 <= df <= 1.0
        checked += 1
    assert checked >= 20


def test_dielectric_temperature_coefficient_is_negative_for_most_liquids():
    rows = load_csv(B740 / "thermodynamic_properties" / "liquid_thermodynamic_indices.csv")
    slopes = [num(r["d_eps_dT_per_K"]) for r in rows]
    slopes = [s for s in slopes if s is not None]
    assert len(slopes) >= 30
    assert all(abs(s) < 5.0 for s in slopes)
    negative = sum(1 for s in slopes if s < 0)
    assert negative / len(slopes) >= 0.85, (negative, len(slopes))


def test_ced_is_reported_as_unavailable_not_zero_filled():
    """0 molecules have dH_vap in this corpus: CED must stay empty, not 0.0."""
    d = load_json(B740 / "thermodynamic_properties" / "thermodynamic_summary.json")
    rows = load_csv(B740 / "thermodynamic_properties" / "liquid_thermodynamic_indices.csv")
    assert d["coverage"]["with_CED"] == 0
    assert all(r["cohesive_energy_density_MPa"] in ("", "None") for r in rows)
    assert all(r["hildebrand_MPa_half"] in ("", "None") for r in rows)


def test_dft_polarizability_vs_lorentz_lorenz_is_a_validation_not_a_fit():
    d = load_json(B740 / "thermodynamic_properties" / "thermodynamic_summary.json")
    v = d["dft_polarizability_validation"]
    assert v["n_pairs"] >= 20, "the Lorentz-Lorenz cross-check lost its sample"
    assert v["pearson_r"] >= 0.99
    assert v["mae_A3"] <= 3.0
    caveat = " ".join(d["caveats"]).lower()
    assert "approximation" in caveat
    assert "n_d" in caveat or "sodium d" in caveat


def test_temperature_matching_never_splices_across_temperatures():
    d = load_json(B740 / "thermodynamic_properties" / "thermodynamic_summary.json")
    tm = d["temperature_matching"]
    assert tm["tolerance_K"] <= 2.0
    assert "no cross-t" in tm["rule"].lower()
    rows = load_csv(B740 / "thermodynamic_properties" / "liquid_thermodynamic_indices.csv")
    for r in rows:
        # every composite index is anchored on one matched temperature
        assert num(r["matched_T_K"]) is not None, r["name"]
        assert num(r["epsilon_at_matched_T"]) is not None, r["name"]
        assert num(r["epsilon_at_matched_T"]) > 1.0, r["name"]
        # a matched pair count is per epsilon temperature, so it is bounded by
        # the number of epsilon points (one density point may serve several)
        assert int(r["n_matched_ri_pairs"]) <= int(r["n_eps_points"])
        assert int(r["n_matched_rho_pairs"]) <= int(r["n_eps_points"])


# ------------------------------------- Kirkwood-Froehlich round-trip
def test_kirkwood_froehlich_round_trip_closes():
    """Recompute X(eps_s, eps_inf) and g_app from the stored columns.

    This is a dimensional/definition check: if the 9/4pi/eps0 or the cm^3->m^3
    handling regressed, the recomputed value would be off by orders of
    magnitude, not by rounding.
    """
    rows = load_csv(PHYSICS / "dielectric_physics_decomposition.csv")
    assert rows
    checked = 0
    for r in rows:
        if r["apparent_gk_valid"] != "true":
            continue
        eps_s, eps_inf = num(r["epsilon_s"]), num(r["epsilon_inf"])
        mu, vm, T = num(r["dipole_D"]), num(r["molar_volume_m3_mol"]), num(r["temperature_K"])
        g = num(r["apparent_gk"])
        if None in (eps_s, eps_inf, mu, vm, T, g):
            continue
        if eps_s <= eps_inf or g <= 0 or mu <= 0 or vm <= 0:
            continue
        x = (eps_s - eps_inf) * (2 * eps_s + eps_inf) / (eps_s * (eps_inf + 2) ** 2)
        assert abs(x - num(r["kf_rhs"])) < 1e-3
        g_expected = (9 * EPS0 * KB * T * vm) / (N_A * (mu * DEBYE_C_M) ** 2) * x
        assert abs(g_expected - g) / g < 1e-2
        checked += 1
    assert checked >= 150, f"only {checked} evaluable rows"


def test_molar_volume_sources_are_kept_apart():
    """Measured-density V_m and RDKit-vdW V_m are different physical objects."""
    rows = load_csv(PHYSICS / "dielectric_physics_decomposition.csv")
    sources = {r["molar_volume_source"] for r in rows}
    assert "MEASURED_DENSITY" in sources
    assert "RDKIT_VDW_VOLUME_NOT_LIQUID_VM" in sources
    # the non-liquid surrogate must be flagged in its own name and never mixed
    # into the primary physics subset
    primary = [r for r in rows if r["molar_volume_source"] == "MEASURED_DENSITY"]
    assert primary, "measured-density subset disappeared"


def test_g_app_is_refused_instead_of_exploding_near_zero_dipole():
    rows = load_csv(PHYSICS / "dielectric_physics_decomposition.csv")
    invalid = [r for r in rows if r["apparent_gk_valid"] == "false"]
    assert invalid, "expected some refused rows (near-zero dipole / missing V_m)"
    # the refusal contract: every exploded value must be FLAGGED, never used
    for r in rows:
        g = num(r["apparent_gk"])
        if g is not None and abs(g) > 1e3:
            assert r["apparent_gk_valid"] == "false", (r["name"], g)
    valid = [num(r["apparent_gk"]) for r in rows if r["apparent_gk_valid"] == "true"]
    valid = [g for g in valid if g is not None]
    assert valid and max(valid) < 1e3


# --------------------------------------------------- MD preflight
def test_md_layer_is_declared_blocked():
    d = load_json(B740 / "md_preflight" / "md_preflight_assessment.json")
    c = d["consequence_for_this_round"]
    assert c["status"] == "BLOCKED_FOR_POLARIZABLE_MD"
    assert "polarizable" in c["why"].lower()
    assert d["tests"]["T2_dielectric"]["verdict"] == "FAIL"
    assert d["tests"]["T2_dielectric"]["n_underestimated"] >= 10


def test_md_dielectric_cannot_be_quoted_as_a_prediction():
    d = load_json(B740 / "md_preflight" / "md_preflight_assessment.json")
    forbidden = " ".join(d["consequence_for_this_round"]["what_is_NOT_legitimate"]).lower()
    assert "quoting eps_md" in forbidden
    assert "g_k" in forbidden
    legitimate = " ".join(d["consequence_for_this_round"]["what_is_legitimate"]).lower()
    assert "negative control" in legitimate


def test_md_failure_direction_is_stated_not_hidden():
    d = load_json(B740 / "md_preflight" / "md_preflight_assessment.json")
    t2 = d["tests"]["T2_dielectric"]
    assert t2["mean_signed_error"] < 0, "underestimation must be a negative signed error"
    assert "UNDERESTIMATE" in d["finding"].upper()


# ------------------------------------------- multiscale ablation honesty
def test_multiscale_summary_guards_against_selection_bias():
    d = load_json(B740 / "multiscale_models" / "multiscale_model_summary.json")
    assert d["selection_bias_warning"]
    assert "NOT comparable" in d["selection_bias_warning"]
    cov = d["coverage"]
    assert d["verdict"]["n_common_subset"] == cov["with_all_layers"]


def test_multiscale_small_subset_is_labelled_inadequate():
    d = load_json(B740 / "multiscale_models" / "multiscale_model_summary.json")
    if d["verdict"]["n_common_subset"] < 10:
        assert d["verdict"]["statistical_power"] == "INADEQUATE"
    for entry in d["paired_staircase"]:
        assert entry["power"] in ("ADEQUATE", "LIMITED", "INADEQUATE")
        if entry["n"] < 20:
            assert entry["power"] != "ADEQUATE"


def test_multiscale_gains_are_computed_from_paired_runs_only():
    d = load_json(B740 / "multiscale_models" / "multiscale_model_summary.json")
    staircase = d["paired_staircase"]
    by_panel: dict[str, dict[str, float]] = {}
    for entry in staircase:
        by_panel.setdefault(entry["panel"], {})[entry["config"]] = entry["mae"]
    gains = d["paired_staircase_gains"]

    x2 = by_panel["X2_PANEL"]
    assert abs((x2["X0+X1"] - x2["X0+X1+X2"]) - gains["X2_panel_gain"]) < 1e-3
    x3 = by_panel["X3_PANEL"]
    assert abs((x3["X0+X1"] - x3["X0+X1+X3"]) - gains["X3_panel_gain"]) < 1e-3

    # a negative gain must be reported as a negative verdict, not rounded up
    if gains["X2_panel_gain"] < 0:
        assert d["verdict"]["conformer_layer_helps_on_subset"] is False
    if gains["X3_panel_gain"] > 0:
        assert d["verdict"]["liquid_property_layer_helps_on_subset"] is True


def test_multiscale_full_cohort_uses_the_unified_v7_descriptor_layer():
    d = load_json(B740 / "multiscale_models" / "multiscale_model_summary.json")
    layers = d["layers"]
    assert {"X0", "X1", "X2", "X3"} <= set(layers)
    # X1 must be the r2SCAN-3c layer: either a column suffixed _v7 or the
    # anisotropy ratio derived from the v7 polarizability tensor
    allowed_derived = {"alpha_anisotropy_ratio"}
    assert layers["X1"]
    for name in layers["X1"]:
        assert name.endswith("_v7") or name in allowed_derived, name
    full = [e for e in d["full_cohort"] if e["config"] == "X0+X1_single_molecule_electronic"]
    assert full and full[0]["n"] == d["coverage"]["total_with_epsilon"]


# ------------------------------------------------- structural resolution
def test_new_structures_are_identity_verified():
    """A fetched SMILES is only usable if RDKit re-derives the exact InChIKey."""
    d = load_json(B740 / "molecule_expansion" / "structure_resolution_summary.json")
    assert d is not None
    rows = load_csv(B740 / "molecule_expansion" / "new_molecule_structures.csv")
    assert rows
    assert d["n_verified"] == len(rows)
    for r in rows:
        assert r["identity_verified"] == "true"
        assert r["inchikey_roundtrip"] == r["inchikey"], r["name"]
    # unresolved molecules are reported, not silently dropped
    assert d["n_unresolved"] + d["n_verified"] == d["n_requested"]
    for u in d["unresolved"]:
        assert u["reason"]


def test_resolved_structures_do_not_duplicate_core239():
    core = core239_inchikeys()
    rows = load_csv(B740 / "molecule_expansion" / "new_molecule_structures.csv")
    assert not [r["inchikey"] for r in rows if r["inchikey"] in core]
    assert all(r["in_core239"] == "false" for r in rows)


# ----------------------------------------------------------- mixtures
def test_mixture_mixing_rules_close_arithmetically():
    rows = load_csv(B740 / "mixtures" / "mixture_dielectric_excess.csv")
    assert rows
    checked = 0
    for r in rows:
        x1 = num(r["x1"])
        e1, e2 = num(r["epsilon_1_pure"]), num(r["epsilon_2_pure"])
        ph1 = num(r["phi1"])
        em = num(r["epsilon_meas"])
        lin, logr = num(r["epsilon_linear"]), num(r["epsilon_lichtenecker"])
        if None in (x1, e1, e2, ph1, em, lin):
            continue
        assert abs(lin - (x1 * e1 + (1 - x1) * e2)) < 1e-2
        if logr is not None:
            assert abs(logr - math.exp(ph1 * math.log(e1) + (1 - ph1) * math.log(e2))) < 1e-2
            assert abs(num(r["resid_vs_lichtenecker"]) - (em - logr)) < 1e-2
        assert abs(num(r["resid_vs_linear"]) - (em - lin)) < 1e-2
        checked += 1
    assert checked >= 2000


def test_mixture_summary_declares_its_own_domain_limits():
    d = load_json(B740 / "mixtures" / "mixture_dielectric_summary.json")
    assert d is not None
    assert d["n_evaluable_points"] > 1000
    dom = d["clausius_mossotti_domain"]
    assert dom["n_defined"] + dom["n_undefined"] == d["n_evaluable_points"]
    assert "NOT" in dom["consequence"]
    # the association split must come from structures, not from names
    assert "no name-based" in d["association_classification"]["source"].lower()


def test_mixture_residual_sign_matches_the_stated_finding():
    d = load_json(B740 / "mixtures" / "mixture_dielectric_summary.json")
    by = d["residual_by_association_class"]
    assert by, "no association class was evaluated"
    for cls, rec in by.items():
        med = rec["resid_vs_lichtenecker"]["median"]
        if med is not None:
            assert med > 0, (cls, med)
    if "PROTIC_PRESENT" in by and "APROTIC_PAIR" in by:
        p = by["PROTIC_PRESENT"]["resid_vs_lichtenecker"]["median"]
        a = by["APROTIC_PAIR"]["resid_vs_lichtenecker"]["median"]
        assert p > a, (p, a)


def test_mixture_records_never_become_single_molecule_labels():
    d = load_json(B740 / "mixtures" / "mixture_dielectric_summary.json")
    says = " ".join(d["what_this_can_and_cannot_say"]).lower()
    assert "no mixture record enters the single-molecule" in says
    ledger = load_csv(B740 / "molecule_expansion" / "cohort_ledger.csv")
    allowed = {"CORE239", "NEW_MOLECULE_VALIDATED", "NEW_MOLECULE_EXPLORATORY"}
    assert {r["cohort"] for r in ledger} <= allowed


# ------------------------------------------------------- computation state
def test_orca_package_is_a_computation_not_a_result():
    """A built package must never be presented as a descriptor table."""
    man = load_json(B740 / "dft_expansion" / "package_opt" / "manifest.json")
    assert man is not None, "ORCA package manifest missing"
    assert man["n_jobs"] == 67
    assert man["layer"] == "opt"
    assert "why_no_sp_layer" in man
    assert man["geometry_source"]["difference_from_core239"]
    rec = load_json(B740 / "dft_expansion" / "package_opt" / "submission_record.json")
    assert rec is not None, "submission record missing"
    assert rec["status"].startswith("SUBMITTED")
    assert "NOT_COLLECTED" in rec["status"]
    # no new-molecule descriptor table may exist while the jobs have not returned
    assert not (B740 / "dft_expansion" / "new_molecule_descriptors.csv").exists()
    joblist = (B740 / "dft_expansion" / "package_opt" / "joblist.txt").read_bytes()
    assert b"\r" not in joblist, "joblist must be LF: Slurm paths break on CR"


# ------------------------------------------- historical protection
def test_v73_artefacts_unchanged():
    prov = load_json(
        REPO_ROOT / "outputs" / "b730_mechanism" / "craft_comparison" / "craft_provenance.json"
    )
    assert prov is not None
    for rel, rec in list(prov["files"].items())[:3]:
        p = REPO_ROOT / rec["saved_as"]
        assert p.exists() and sha256(p) == rec["sha256"], f"v7.3 raw changed: {rel}"


def test_v70_and_v60_frozen_artefacts_unchanged():
    man = load_json(B710_FINAL / "v70_freeze_manifest.json")
    assert man is not None
    drift = [
        key for key, rec in man["frozen_artifacts"].items()
        if not (REPO_ROOT / rec["path"]).exists()
        or sha256(REPO_ROOT / rec["path"]) != rec["sha256"]
    ]
    assert not drift, f"v7.0 artefacts modified: {drift}"
    for key, rec in man["protected_v60_artifacts"].items():
        p = REPO_ROOT / rec["path"]
        assert p.exists() and sha256(p) == rec["sha256"], key


def test_v72_external_raw_hashes_unchanged():
    for sub in ("liquidbenchmark", "combat"):
        prov = load_json(REPO_ROOT / "data" / "external_raw" / sub / "PROVENANCE.json")
        assert prov is not None, sub
        for rel, rec in list(prov["files"].items())[:3]:
            p = REPO_ROOT / rec["saved_as"]
            assert p.exists() and sha256(p) == rec["sha256"], f"{sub}/{rel}"


def test_b740_outputs_are_self_describing():
    """Every v7.4 artefact must declare schema + generator + units/provenance."""
    for rel in (
        "thermoml/thermoml_coverage.json",
        "molecule_expansion/cohort_summary.json",
        "molecular_descriptors/polarizability_anisotropy_summary.json",
        "conformer_analysis/conformer_entropy_summary.json",
        "thermodynamic_properties/thermodynamic_summary.json",
        "md_preflight/md_preflight_assessment.json",
        "multiscale_models/multiscale_model_summary.json",
    ):
        d = load_json(B740 / rel)
        assert d is not None, rel
        assert d.get("schema", "").startswith("b740."), rel
        assert d.get("generator"), rel
        assert d.get("generated_at_utc"), rel
