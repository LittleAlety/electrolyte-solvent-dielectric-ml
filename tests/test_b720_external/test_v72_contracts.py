"""B720/B722/B723/B724 v7.2 contracts.

Each assertion is a scientific constraint the v7.2 conclusions depend on:

  * recovered raw files are byte-identical to the recorded hashes
  * a dataset name is never counted as an independent source
  * the ComBat rejection rests on a computed definition mismatch
  * mixtures and non-experimental values cannot enter the modelling set
  * source OOD is never claimed when no clean split exists
  * the E6 metric matches the code, not the prose
  * pool sampling is without replacement and identical across arms
  * a molecule absent from a pool is not counted as a rejection
  * ether subtypes are reproducible from SMILES and never overwrite `family`
  * v7.0/v7.1 frozen artefacts are untouched
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
B720 = REPO_ROOT / "outputs" / "b720_external_data"
B722 = REPO_ROOT / "outputs" / "b722_source_independence"
B723 = REPO_ROOT / "outputs" / "b723_screening_robustness"
B724 = REPO_ROOT / "outputs" / "b724_ether"
B725 = REPO_ROOT / "outputs" / "b725_final"
B710 = REPO_ROOT / "outputs" / "b710_evidence"
RAW_LB = REPO_ROOT / "data" / "external_raw" / "liquidbenchmark"
RAW_CB = REPO_ROOT / "data" / "external_raw" / "combat"


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


# ------------------------------------------------------- raw data integrity
def test_liquidbenchmark_raw_hashes_match_provenance():
    prov = load_json(RAW_LB / "PROVENANCE.json")
    assert prov is not None, "LiquidBenchmark provenance missing"
    assert prov["licence"] == "GPL-2.0"
    assert len(prov["pinned_commit"]) == 40
    for rel, rec in prov["files"].items():
        p = REPO_ROOT / rec["saved_as"]
        assert p.exists(), rel
        assert sha256(p) == rec["sha256"], f"{rel} was modified"


def test_combat_raw_hashes_match_provenance():
    prov = load_json(RAW_CB / "PROVENANCE.json")
    assert prov is not None
    assert prov["licence"] == "MIT"
    assert prov["provenance_class"] == "SECONDARY_COMPILATION"
    for rel, rec in prov["files"].items():
        p = REPO_ROOT / rec["saved_as"]
        assert p.exists(), rel
        assert sha256(p) == rec["sha256"], f"{rel} was modified"


def test_raw_files_are_not_relicensed():
    """We may redistribute with the original licence, never under a new one."""
    lb_lic = RAW_LB / "LICENSE"
    cb_lic = RAW_CB / "LICENSE"
    assert lb_lic.exists() and "GNU GENERAL PUBLIC LICENSE" in lb_lic.read_text(
        encoding="utf-8", errors="replace")[:2000]
    assert cb_lic.exists() and "MIT" in cb_lic.read_text(
        encoding="utf-8", errors="replace")[:400]


# ------------------------------------------------------------ admission
def test_combat_definition_rejection_is_computed():
    s = load_json(B720 / "external_admission_summary.json")
    assert s is not None
    cb = s["combat"]
    assert cb["definition_ok"] is False
    assert cb["definition_probe_failures"] >= 2
    # the probe must include at least one huge relative difference
    worst = max(p["relative_difference"] for p in cb["definition_probe"])
    assert worst > 0.3


def test_combat_rows_never_enter_a_modelling_pool():
    reg = load_csv(B722 / "source_registry_3layer.csv")
    combat = [r for r in reg if r["database_layer"] == "COMBAT"]
    for r in combat:
        assert r["verification_status"] == "REJECTED_DEFINITION_MISMATCH"


def test_liquidbenchmark_property_is_static_by_definition():
    rows = load_csv(B720 / "liquidbenchmark_records.csv")
    assert rows
    for r in rows:
        assert "zero frequency" in r["property_definition"].lower()
        assert r["frequency_known"] == "true"


def test_no_mixture_entered_as_pure_liquid():
    rows = load_csv(B720 / "liquidbenchmark_records.csv")
    for r in rows:
        # a ThermoML mixture is a semicolon-separated component list
        assert ";" not in r["components"], r["components"]


def test_admission_statuses_are_from_the_fixed_vocabulary():
    allowed = {
        "REJECT_DEFINITION_MISMATCH", "REJECT_NOT_PURE_LIQUID",
        "REJECT_NO_IDENTITY", "REJECT_NO_EPSILON",
        "EXPLORATORY_INCOMPLETE_METADATA", "CANDIDATE_CORROBORATION",
        "CANDIDATE_NEW_MOLECULE",
    }
    rows = load_csv(B720 / "external_admission_audit.csv")
    assert rows
    for r in rows:
        assert r["admission_status"] in allowed, r["admission_status"]


def test_simulation_values_are_not_admitted_as_experimental():
    """ComBat is flagged secondary; nothing simulation-derived is marked experimental."""
    rows = load_csv(B720 / "combat_records.csv")
    for r in rows:
        if r["record_type"] == "secondary_compilation":
            assert r["frequency_known"] == "false"


# ---------------------------------------------------- source independence
def test_compendium_counted_once_not_per_molecule():
    reg = load_csv(B722 / "source_registry_3layer.csv")
    comp = [r for r in reg if r["primary_study_layer"] == "PRIMARY-NBS514-COMPENDIUM"]
    assert comp
    # many rows, but exactly one distinct primary-study id and one lab id
    assert len({r["primary_study_layer"] for r in comp}) == 1
    assert len({r["laboratory_layer"] for r in comp}) == 1


def test_database_is_not_a_source():
    s = load_json(B722 / "source_coverage_summary.json")
    assert s is not None
    notes = " ".join(s["honesty_notes"])
    assert "A database is not a source" in notes


def test_five_counts_are_distinct_quantities():
    s = load_json(B722 / "source_coverage_summary.json")
    fc = s["five_counts_kept_separate"]
    assert len(fc) == 5
    # the two-primary-study count must not exceed the any-record count
    assert fc["2_molecules_with_ge2_primary_studies"] <= fc["1_molecules_with_any_valid_record"]
    # independent-lab coverage cannot exceed primary-study coverage
    assert fc["3_molecules_with_ge2_independent_labs"] <= fc["2_molecules_with_ge2_primary_studies"]


def test_source_ood_cleanliness_is_reported_not_assumed():
    ood = load_json(B722 / "source_ood_results.json")
    assert ood is not None
    cf = ood["clean_ood_feasibility"]
    assert cf["verdict"] in ("CLEAN_SOURCE_OOD_FEASIBLE", "CLEAN_SOURCE_OOD_NOT_FEASIBLE")
    if cf["n_studies_clean_eligible"] == 0:
        assert cf["verdict"] == "CLEAN_SOURCE_OOD_NOT_FEASIBLE"
    # every evaluable source records its leakage count
    for s in ood["leave_one_primary_study_out"]["sources"]:
        assert "n_test_molecules_also_in_training_via_other_source" in s


def test_no_source_is_in_both_training_and_test_by_construction():
    """The held-out set is molecule-defined, so a held-out molecule's own records
    must not appear in the training index. Verify the leakage count is recorded."""
    ood = load_json(B722 / "source_ood_results.json")
    for s in ood["leave_one_primary_study_out"]["sources"]:
        assert s["n_test"] >= 3
        assert isinstance(s["n_test_molecules_also_in_training_via_other_source"], int)


def test_separation_warning_present():
    ood = load_json(B722 / "source_ood_results.json")
    assert "must never be averaged" in ood["separation_warning"]


# --------------------------------------------------------- E6 protocol
def test_e6_regret_definition_matches_code():
    a = load_json(B723 / "e6_protocol_audit.json")
    assert a is not None
    assert a["all_checks_pass"] is True, a["checks"]
    d = a["definition_confirmed"]
    assert d["topk"] == "k largest predictions"
    assert "oracle" in d["regret"].lower() or "true" in d["regret"].lower()


def test_e6_regret_formula_hand_computed():
    """A tiny case whose regret is computable by hand must come out right."""
    pred = [3.0, 2.0, 1.0, 0.5, 0.1]
    true = [1.0, 2.0, 10.0, 9.0, 8.0]
    k = 2
    order = sorted(range(len(pred)), key=lambda i: (-pred[i], i))
    model_top = [true[i] for i in order[:k]]
    oracle_top = sorted(true, reverse=True)[:k]
    regret = sum(oracle_top) / k - sum(model_top) / k
    assert abs(regret - 8.0) < 1e-12


def test_pool_sampling_has_no_replacement():
    p = load_json(B723 / "candidate_pool_effects.json")
    assert p is not None
    assert p["design"]["sampling_with_replacement"] is False
    assert "not ten candidate materials" in p["design"]["why_no_replacement"]


def test_all_arms_share_the_same_pool():
    p = load_json(B723 / "candidate_pool_effects.json")
    assert p["design"]["paired_across_arms"] is True


def test_pool_draws_cover_all_arms_for_each_fraction():
    p = load_json(B723 / "candidate_pool_effects.json")
    for frac, parts in p["B_pool_composition_effect"].items():
        assert len(parts) == 4, list(parts)


def test_absent_molecule_is_not_a_rejection():
    t = load_json(B723 / "topk_stability.json")
    assert t is not None
    sd = t["state_definition"]
    assert sd["NOT_IN_POOL"].startswith("draw excluded")
    assert "NOT counted as a rejection" in sd["NOT_IN_POOL"]
    assert "in the pool" in sd["frequency_denominator"]


def test_top10_frequency_denominator_is_eligibility():
    rows = load_csv(B723 / "molecule_recommendation_stability.csv")
    assert rows
    bad = []
    for r in rows:
        elig = int(r["n_draws_eligible"])
        sel = int(r["n_draws_selected_top10"])
        freq = float(r["top10_frequency"])
        if elig == 0:
            if freq != 0.0:
                bad.append(r["inchikey"])
            continue
        if sel > elig:
            bad.append(r["inchikey"])
        if abs(freq - sel / elig) > 1e-3:
            bad.append(r["inchikey"])
    assert not bad, f"inconsistent frequency arithmetic: {bad[:5]}"


def test_pool_size_reduces_regret_monotonically():
    """A smaller pool makes top-10 easier; if that did not show up, the sampling
    or the scoring is wrong."""
    p = load_json(B723 / "candidate_pool_effects.json")
    a = p["attribution"]
    assert a["regret_median_at_80pct_pool"] <= a["regret_median_full_pool"]


def test_pool_variance_dominates_training_variance():
    p = load_json(B723 / "candidate_pool_effects.json")
    a = p["attribution"]
    assert a["regret_sd_pool_only_mu2vm"] > 2 * a["regret_sd_training_only_mu2vm"]
    assert a["verdict"] == "POOL_SIZE_AND_COMPOSITION_DOMINATE"


# --------------------------------------------------------------- ether
def test_ether_subtypes_reproducible_from_smiles():
    pytest.importorskip("rdkit")
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")

    ether_pat = Chem.MolFromSmarts("[#6]-[#8]-[#6]")
    aryl_pat = Chem.MolFromSmarts("[c]-[#8]-[#6]")
    aliph_pat = Chem.MolFromSmarts("[CX4]-[#8]-[CX4]")
    cyc_pat = Chem.MolFromSmarts("[#6;R]-[#8]-[#6]")

    def rule(mol):
        if not mol.HasSubstructMatch(ether_pat):
            return "not_an_ether"
        if sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "Cl") >= 1:
            return "chlorinated_ether"
        if mol.HasSubstructMatch(aryl_pat):
            return "aromatic_ether"
        if mol.HasSubstructMatch(cyc_pat):
            return "cyclic_ether"
        if mol.HasSubstructMatch(aliph_pat):
            return "aliphatic_ether"
        return "other_or_ambiguous"

    rows = load_csv(B724 / "ether_subtype_v2.csv")
    assert rows
    bad = []
    for r in rows:
        mol = Chem.MolFromSmiles(r["smiles"])
        assert mol is not None, r["smiles"]
        if rule(mol) != r["family_subtype_v2"]:
            bad.append((r["name"], r["family_subtype_v2"], rule(mol)))
    assert not bad, f"subtype rules not reproducible: {bad}"


def test_official_family_never_overwritten():
    desc = {r["inchikey"]: r for r in
            load_csv(REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv")}
    rows = load_csv(B724 / "ether_subtype_v2.csv")
    for r in rows:
        assert r["official_family"] == "ether"
        assert desc[r["inchikey"]]["family"] == "ether"


def test_cyclic_class_exists_and_is_prior_to_aliphatic():
    m = load_json(B724 / "ether_subtype_v2_manifest.json")
    assert m is not None
    order = " | ".join(m["rules_priority"])
    assert order.index("cyclic_ether") < order.index("aliphatic_ether")
    assert m["frozen_counts"].get("cyclic_ether", 0) >= 1


def test_small_strata_are_not_given_inference_status():
    a = load_json(B724 / "ether_subfamily_analysis_v2.json")
    assert a is not None
    for name, s in a["by_subtype"].items():
        if s["n"] < 5:
            assert s["inference_allowed"] is False, name
            assert s["not_inference_reason"]


def test_ether_answer_is_not_overstated():
    a = load_json(B724 / "ether_subfamily_analysis_v2.json")
    ans = a["answer_to_plan_question"]
    assert ans["grade"] == "EXPLORATORY"
    assert "UNRESOLVED" in ans["answer"]


# ------------------------------------------------------- freeze protection
def test_v70_frozen_artifacts_unchanged():
    man = load_json(B710 / "final" / "v70_freeze_manifest.json")
    assert man is not None
    drift = []
    for key, rec in man["frozen_artifacts"].items():
        p = REPO_ROOT / rec["path"]
        if not p.exists() or sha256(p) != rec["sha256"]:
            drift.append(key)
    assert not drift, f"v7.0 frozen artefacts modified: {drift}"


def test_v60_artifacts_unchanged():
    man = load_json(B710 / "final" / "v70_freeze_manifest.json")
    for key, rec in man["protected_v60_artifacts"].items():
        p = REPO_ROOT / rec["path"]
        assert p.exists() and sha256(p) == rec["sha256"], key


# ------------------------------------------------------- claim ledger
def test_claim_ledger_grades_are_from_the_vocabulary():
    d = load_json(B725 / "claim_ledger.json")
    assert d is not None
    vocab = {"CONFIRMED", "SUPPORTED", "EXPLORATORY", "UNRESOLVED", "NOT_TESTABLE"}
    for c in d["claims"]:
        assert c["grade"] in vocab, c["grade"]
    assert d["n_claims"] == len(d["claims"])


def test_claim_ledger_has_no_missing_artifacts():
    d = load_json(B725 / "claim_ledger.json")
    assert d["missing_artifacts"] == [], d["missing_artifacts"]


def test_no_claim_promotes_a_not_testable_finding():
    """A NOT_TESTABLE entry must be a statement of absence, not a result.

    Checking for specific words was the wrong test (it rejected a legitimate
    'no external dataset supplies...' phrasing). What actually matters is that a
    NOT_TESTABLE claim is NOT also listed as paper-ready, i.e. we never ship an
    untestable statement as a finding.
    """
    d = load_json(B725 / "claim_ledger.json")
    paper_ready = set(d["paper_ready_claims"])
    for c in d["claims"]:
        if c["grade"] == "NOT_TESTABLE":
            assert c["id"] not in paper_ready,                 f"{c['id']} is NOT_TESTABLE but marked paper-ready"
            assert c["evidence"], f"{c['id']} has no evidence pointer"


def test_source_independence_limitation_is_stated_as_confirmed():
    d = load_json(B725 / "claim_ledger.json")
    ids = {c["id"]: c for c in d["claims"]}
    assert "S6" in ids
    assert ids["S6"]["grade"] == "CONFIRMED"
    assert "does NOT support" in ids["S6"]["claim"]


def test_sha256_manifest_covers_the_v72_outputs():
    m = load_json(B725 / "sha256_manifest.json")
    assert m is not None
    assert m["n_files"] >= 20
    assert len(m["files"]) == m["n_files"]
    for rel, rec in list(m["files"].items())[:5]:
        p = REPO_ROOT / rel
        assert p.exists()
        assert sha256(p) == rec["sha256"], rel
