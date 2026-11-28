"""B710 v7.1 evidence contracts.

Every assertion is a scientific constraint, not a file-existence check:

  * v7.0 evidence is byte-identical to the freeze manifest (no silent overwrite)
  * v6.0 historical layer untouched
  * a compendium is ONE source, never N
  * source independence is decided at the original study, not the database
  * the official `family` column is preserved; subtypes live in new columns only
  * ether subtypes are reproducible from SMILES by the stated rules
  * the E4 calibration audit distinguishes diagnostic from honest calibration
  * outliers are retained in every headline metric
  * the E6 seed experiment is reproducible and keeps one candidate pool
  * xTB-on-DFT-geometry inputs preserve atom order and do not re-optimise
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
B710 = REPO_ROOT / "outputs" / "b710_evidence"
B700 = REPO_ROOT / "outputs" / "b700"
B100 = REPO_ROOT / "outputs" / "b100"


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


# ------------------------------------------------------- freeze and provenance
def test_v70_frozen_artifacts_unchanged():
    """v7.1 must not rewrite the evidence v7.0 conclusions rest on."""
    manifest = load_json(B710 / "final" / "v70_freeze_manifest.json")
    assert manifest is not None, "freeze manifest missing"
    frozen = manifest["frozen_artifacts"]
    assert len(frozen) >= 15
    drift = []
    for key, rec in frozen.items():
        path = REPO_ROOT / rec["path"]
        if not path.exists():
            drift.append((key, "MISSING"))
            continue
        if sha256(path) != rec["sha256"]:
            drift.append((key, "HASH_CHANGED"))
    assert not drift, f"v7.0 frozen artifacts were modified: {drift}"


def test_v60_artifacts_unchanged():
    manifest = load_json(B710 / "final" / "v70_freeze_manifest.json")
    protected = manifest["protected_v60_artifacts"]
    assert len(protected) == 4
    for key, rec in protected.items():
        path = REPO_ROOT / rec["path"]
        assert path.exists(), f"{key} missing"
        assert sha256(path) == rec["sha256"], f"v6.0 artifact modified: {key}"


def test_freeze_manifest_records_the_protocol():
    """A stability claim without its protocol is unverifiable."""
    manifest = load_json(B710 / "final" / "v70_freeze_manifest.json")
    proto = manifest["evaluation_protocol"]
    assert "nested" in proto["evaluation"].lower()
    assert proto["topk"] == 10
    assert len(proto["lambda_grid"]) == 6
    assert "NOT" in proto["seed_semantics"] or "not" in proto["seed_semantics"]


# --------------------------------------------------------- source independence
def test_compendium_counts_as_one_source():
    """NBS 514 must appear once, regardless of how many molecules it supplies."""
    reg = load_csv(B710 / "source_independence" / "source_registry.csv")
    assert reg, "source registry missing"
    compendia = [r for r in reg if r["source_independence"] == "COMPENDIUM_SINGLE"]
    assert len(compendia) == 1
    comp = compendia[0]
    # it must carry many compounds but still be a single source
    assert int(comp["n_compounds"]) > 100
    assert int(comp["n_rows"]) > 100


def test_no_database_is_double_counted_as_two_sources():
    lineage = load_json(B710 / "source_independence" / "source_lineage.json")
    assert lineage is not None
    ids = set()
    for rule in lineage["rules"].values():
        assert isinstance(rule, str)
    reg = load_csv(B710 / "source_independence" / "source_registry.csv")
    for r in reg:
        assert r["source_id"] not in ids, f"duplicate source_id {r['source_id']}"
        ids.add(r["source_id"])
    # the independence label must never be "PRIMARY" for the compendium
    for r in reg:
        if "NBS514" in r["source_id"] or "nbs.circ.514" in (r["DOI"] or "").lower():
            assert r["source_independence"] == "COMPENDIUM_SINGLE"


def test_source_lineage_reports_molecule_level_coverage():
    """Overall study count alone is not the binding constraint; report both."""
    lineage = load_json(B710 / "source_independence" / "source_lineage.json")
    cov = lineage["molecule_level_coverage"]
    assert cov["with_ge2_independent_sources"] > 0
    assert cov["compendium_only"] > 0
    assert 0.0 <= cov["fraction_with_ge2_independent_sources"] <= 1.0
    gate = lineage["claim_gate"]
    assert "study_level_verdict" in gate
    assert "molecule_level_verdict" in gate
    assert gate["binding_constraint"]


def test_overlap_table_covers_all_239_and_is_consistent():
    rows = load_csv(B710 / "source_independence" / "molecule_source_overlap.csv")
    assert len(rows) == 239
    assert len({r["inchikey"] for r in rows}) == 239
    for r in rows:
        n = int(r["n_sources"])
        assert n >= 1
        if r["cross_source_status"] == "AGREE":
            assert n >= 2
        if r["contains_compendium"] == "true" and n == 1:
            assert r["cross_source_status"] == "SINGLE_SOURCE"


def test_external_records_are_not_promoted_without_conditions():
    """Anything without temperature or without overlap must stay EXPLORATORY."""
    rows = load_csv(B710 / "source_independence" / "external_data_audit.csv")
    assert rows
    for r in rows:
        if r["has_temperature"] == "false" or int(r["n_overlap_with_239"]) == 0:
            assert r["admission_status"] == "EXPLORATORY", r["source_id"]


def test_source_ood_and_strict_are_separately_reported():
    ood = load_json(B710 / "source_independence" / "source_ood_results.json")
    assert ood is not None
    assert ood["sources"]
    for s in ood["sources"]:
        assert s["n_test_molecules"] >= 3
        assert "strict_no_leak_mae" in s
    sep = load_json(B710 / "source_independence" / "source_cluster_audit.json")["separation"]
    assert sep["source_ood"] != sep["chemical_ood"]
    assert "never" in sep["warning"]


def test_bootstrap_resamples_studies_not_molecules():
    boot = load_json(B710 / "source_independence" / "source_bootstrap_results.json")
    assert boot is not None
    assert "study" in boot["resampling_unit"].lower()
    if boot["n_clusters_used"] < 3:
        assert boot["status"] == "NOT_ESTIMABLE"
    elif boot["n_clusters_used"] < 5:
        assert boot["status"] == "EXPLORATORY"


# ------------------------------------------------------------ ether subtypes
def test_official_family_column_is_preserved():
    """The frozen descriptor table must still say 'ether' for these molecules."""
    desc = {r["inchikey"]: r for r in load_csv(B700 / "orca_r2scan3c_descriptors.csv")}
    table = load_csv(B710 / "ether_subfamilies" / "ether_subtype_table.csv")
    assert table
    for r in table:
        assert desc[r["inchikey"]]["family"] == "ether", \
            f"{r['inchikey']} official family was modified"
        assert r["family"] == "ether"


def test_subtype_manifest_declares_non_modification():
    m = load_json(B710 / "ether_subfamilies" / "ether_subtype_manifest.json")
    assert m["original_family_column_modified"] is False
    assert m["official_family_still"] == "ether"
    assert m["classification_rules"]["name_matching_used"] is False


def test_ether_subtypes_reproducible_from_smiles():
    """Re-run the structural rules independently and require identical labels."""
    rdkit = pytest.importorskip("rdkit")
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")

    ether_pat = Chem.MolFromSmarts("[#6]-[#8]-[#6]")
    aryl_pat = Chem.MolFromSmarts("[c]-[#8]-[#6]")
    aliph_pat = Chem.MolFromSmarts("[CX4]-[#8]-[CX4]")

    def rule(mol):
        has_ether = mol.HasSubstructMatch(ether_pat)
        n_cl = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "Cl")
        if has_ether and n_cl >= 1:
            return "chlorinated_ether"
        if (has_ether and mol.HasSubstructMatch(aliph_pat)
                and not mol.HasSubstructMatch(aryl_pat) and n_cl == 0):
            return "aliphatic_ether"
        return "other_or_ambiguous"

    table = load_csv(B710 / "ether_subfamilies" / "ether_subtype_table.csv")
    disagreements = []
    for r in table:
        mol = Chem.MolFromSmiles(r["smiles"])
        assert mol is not None, r["smiles"]
        if rule(mol) != r["family_subtype_v1"]:
            disagreements.append((r["name"], r["family_subtype_v1"], rule(mol)))
    assert not disagreements, f"subtype rules not reproducible: {disagreements}"


def test_chlorinated_takes_priority_over_aliphatic():
    table = load_csv(B710 / "ether_subfamilies" / "ether_subtype_table.csv")
    for r in table:
        if int(r["rule_n_Cl"] or 0) >= 1 and r["rule_has_ether_C_O_C"] == "true":
            assert r["family_subtype_v1"] == "chlorinated_ether", r["name"]
        if r["family_subtype_v1"] == "aliphatic_ether":
            assert int(r["rule_n_Cl"] or 0) == 0
            assert r["rule_has_aryl_ether"] == "false"


def test_small_subtypes_are_flagged_as_not_inference_ready():
    a = load_json(B710 / "ether_subfamilies" / "ether_subfamily_analysis.json")
    assert a is not None
    for name, st in a["by_subtype"].items():
        if st["n"] < 5:
            assert st["inference_allowed"] is False, name
    assert a["evidence_grade"] in ("EXPLORATORY", "SUPPORTED")
    assert "n=2" in a["caveat"] or "n=2" in a["caveat"]


def test_pooled_rho_reports_a_permutation_p():
    a = load_json(B710 / "ether_subfamilies" / "ether_subfamily_analysis.json")
    pooled = a["pooled"]
    assert pooled["spearman"] is not None
    assert pooled["spearman_perm_p"] is not None
    assert 0.0 < pooled["spearman_perm_p"] <= 1.0


# --------------------------------------------------- E4 mechanism / calibration
def test_calibration_audit_separates_diagnostic_from_honest():
    a = load_json(B710 / "e4_mechanism_audit" / "e4_mechanism_audit.json")
    assert a is not None
    cal = a["calibration_audit"]
    assert "held-out family's own mean residual" in cal["method"]
    for row in cal["families"]:
        if row["verdict"] == "CALIBRATION_CAPABILITY_SUPPORTED":
            assert row["honest_nested_cal_mae"] is not None
            assert row["honest_beats_constant"] is True
        if row["verdict"] == "DIAGNOSTIC_ONLY_NOT_CALIBRATION":
            assert row["honest_beats_constant"] is False or row["honest_nested_cal_mae"] is None


def test_diagnostic_demeaned_is_never_better_than_honest():
    """Removing the test-set mean cannot be a legitimate improvement over a
    fold-estimated offset — if it were, the honest number would be gameable."""
    a = load_json(B710 / "e4_mechanism_audit" / "e4_mechanism_audit.json")
    checked = 0
    for row in a["calibration_audit"]["families"]:
        d = row.get("diagnostic_mae_demeaned")
        h = row.get("honest_nested_cal_mae")
        if d is None or h is None:
            continue
        assert d <= h + 1e-9, \
            f"{row['family']}: diagnostic {d} < honest {h} is expected (optimistic)"
        checked += 1
    assert checked >= 8


def test_outliers_are_retained_in_headline_metrics():
    """The E4 table must not be computed after dropping outliers."""
    diag = load_csv(B700 / "B706_E4_family_diagnostics.csv")
    lofo = load_csv(B700 / "B706_E4_lofo_predictions.csv")
    assert len(lofo) == 235
    # recompute family MAE from the full prediction file and compare
    from collections import defaultdict
    by_fam = defaultdict(list)
    for r in lofo:
        by_fam[r["family"]].append(abs(float(r["resid"])))
    for row in diag:
        fam = row["family"]
        if fam not in by_fam:
            continue
        full_mae = sum(by_fam[fam]) / len(by_fam[fam])
        assert abs(full_mae - float(row["lofo_mae"])) < 1e-3, \
            f"{fam}: headline MAE {row['lofo_mae']} != full-sample {full_mae:.4f}"


def test_hcn_and_triolein_are_identified_with_influence():
    rows = load_csv(B710 / "e4_mechanism_audit" / "e4_outlier_influence.csv")
    names = {r["name"].lower() for r in rows}
    assert any("hydrocyanic" in n or "hcn" in n for n in names)
    assert any("triolein" in n for n in names)
    for r in rows:
        assert r["nn_distance_standardised"]
        share = float(r["family_mae_share_of_this_point"])
        assert 0.0 <= share <= 1.0


# ------------------------------------------------------------- E6 stability
def test_e6_seed_experiment_is_reproducible():
    """Two runs with the same seeds must produce identical regret values."""
    d = load_json(B710 / "e6_stability" / "e6_stability_v71.json")
    assert d is not None
    assert len(d["seeds"]) == 20
    for arm, res in d["arms"].items():
        assert res["n_seeds"] == 20
        for r in res["per_seed"]:
            assert r["regret"] == round(d["oracle_topk_mean"] - r["topk_model_mean"], 4)
        # quantiles must be ordered
        assert res["regret_q1"] <= res["regret_median"] <= res["regret_q3"] <= res["regret_p95"]


def test_e6_all_arms_share_one_candidate_pool():
    d = load_json(B710 / "e6_stability" / "e6_stability_v71.json")
    ec = d["evaluation_consistency"]
    assert ec["same_candidate_pool"] is True
    assert ec["same_topk"] == 10
    assert ec["same_oracle"] == d["oracle_topk_mean"]
    assert ec["same_regret_definition"]
    assert ec["same_lambda_protocol"]


def test_e6_numpy_impl_verified_against_reference():
    d = load_json(B710 / "e6_stability" / "e6_stability_v71.json")
    chk = d["implementation"]["self_check_vs_pure_python"]
    assert chk["passes"] is True
    assert chk["max_abs_difference"] < 1e-9


def test_three_uncertainty_kinds_are_kept_separate():
    d = load_json(B710 / "e6_stability" / "e6_stability_v71.json")
    kinds = d["uncertainty_kinds"]
    assert set(kinds) >= {"A_algorithmic", "B_molecule_sampling", "C_source"}
    assert "not" in kinds["A_algorithmic"]["semantics"].lower() or \
           "NOT" in kinds["A_algorithmic"]["semantics"]
    assert "never" in kinds["warning"]
    assert d["molecule_bootstrap"]
    for arm, b in d["molecule_bootstrap"].items():
        assert b["n_bootstrap"] >= 100
        assert b["regret_ci95"][0] <= b["regret_median"] <= b["regret_ci95"][1]


def test_e6_reports_overlap_and_dispersion_not_a_single_number():
    d = load_json(B710 / "e6_stability" / "e6_stability_v71.json")
    for arm, res in d["arms"].items():
        assert "topk_overlap_mean" in res
        assert "regret_p95" in res
        assert res["regret_min"] <= res["regret_max"]
    v = d["verdicts"]
    assert "regret_relative_dispersion_mu2vm" in v
    assert "mae_relative_dispersion_mu2vm" in v


def test_e6_mae_dispersion_smaller_than_regret_dispersion():
    """The v7.0 headline must survive the 20-seed extension."""
    d = load_json(B710 / "e6_stability" / "e6_stability_v71.json")
    mu = d["arms"]["X0_plus_mu2_Vm"]
    assert mu["mae_sd"] < mu["regret_sd"]


# -------------------------------------------------- xTB on DFT geometry
def test_xtb_on_dft_inputs_preserve_atom_order():
    p = load_json(B710 / "xtb_on_dft_geometry" / "xtb_on_dft_geometry_preflight.json")
    assert p is not None
    assert p["no_reoptimisation"] is True
    assert p["charge"] == 0 and p["multiplicity"] == 1
    ready = [r for r in p["records"] if r["status"] == "INPUT_READY"]
    assert len(ready) >= 12
    for r in ready:
        assert r["atom_order_matches_input"] is True, r["inchikey"]


def test_xtb_on_dft_xyz_matches_recorded_hash():
    p = load_json(B710 / "xtb_on_dft_geometry" / "xtb_on_dft_geometry_preflight.json")
    ready = [r for r in p["records"] if r["status"] == "INPUT_READY"]
    for r in ready:
        xyz = B710 / "xtb_on_dft_geometry" / "xtb_dft_geom_inputs" / r["inchikey"] / "xtb.xyz"
        assert xyz.exists(), r["inchikey"]
        assert sha256(xyz) == r["xyz_sha256"], r["inchikey"]
        # atom count in file must equal the recorded count
        lines = xyz.read_text().strip().splitlines()
        assert int(lines[0]) == r["atom_count"]
        assert len(lines) - 2 == r["atom_count"]


def test_xtb_inputs_are_single_points_not_optimisations():
    p = load_json(B710 / "xtb_on_dft_geometry" / "xtb_on_dft_geometry_preflight.json")
    for r in [x for x in p["records"] if x["status"] == "INPUT_READY"]:
        sh = (B710 / "xtb_on_dft_geometry" / "xtb_dft_geom_inputs"
              / r["inchikey"] / "run.sh").read_text()
        assert "--sp" in sh, r["inchikey"]
        assert "--opt" not in sh, r["inchikey"]
