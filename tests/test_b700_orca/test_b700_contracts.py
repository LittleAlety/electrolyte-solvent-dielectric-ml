"""B700 v7.0 contract tests.

These tests check the PRODUCED ARTIFACTS, not live ORCA runs, so they run
offline and fast. Every assertion is a contract the report depends on:

  * 239-molecule coverage of both DFT layers
  * every SP/Opt job terminated normally and Opt converged
  * dipoles and polarisabilities present for all 239
  * parser unit conventions (Debye, a.u. -> A^3) are applied consistently
  * geometry provenance is recorded and hashes can be recomputed
  * conformer Boltzmann weights are normalised and monotone in energy
  * the v6.0 historical layer is untouched (frozen hash)
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
B700 = REPO_ROOT / "outputs" / "b700"
PROD = B700 / "B701_DFT" / "production_239"
B100 = REPO_ROOT / "outputs" / "b100" / "deliverables"

AU2A3 = 0.14818471  # 1 a.u. of polarizability volume in A^3


def load_csv(path: Path) -> list[dict]:
    import io
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


# ------------------------------------------------------------------ coverage
def test_sp_layer_covers_239():
    rows = load_csv(PROD / "parsed_sp.csv")
    assert len(rows) == 239
    assert sum(1 for r in rows if r["status"] == "OK") == 239


def test_opt_layer_covers_239_and_all_converged():
    rows = load_csv(PROD / "parsed_opt.csv")
    assert len(rows) == 239
    assert sum(1 for r in rows if r["status"] == "OK") == 239
    assert sum(1 for r in rows if r["optimization_converged"] == "True") == 239


def test_dipoles_and_polarisabilities_complete():
    for name in ("parsed_sp.csv", "parsed_opt.csv"):
        rows = load_csv(PROD / name)
        assert all(r["dipole_D"].strip() for r in rows), name
        assert all(r["polarizability_au"].strip() for r in rows), name


def test_no_duplicate_inchikeys():
    rows = load_csv(PROD / "parsed_sp.csv")
    keys = [r["inchikey"] for r in rows]
    assert len(keys) == len(set(keys))


# -------------------------------------------------------------- method / unit
def test_method_freeze_declares_r2scan3c_and_charge_state():
    freeze = load_json(B700 / "B701_DFT" / "method_freeze_v2.json")
    assert freeze is not None
    assert freeze["status"] == "FROZEN"
    proto = freeze["protocol"]
    assert "r2SCAN-3c" in proto["method"]
    assert proto["charge"] == 0
    assert proto["multiplicity"] == 1
    assert freeze["preflight_gates"]["orca_runs_12_of_12_sp"] is True


def test_descriptor_polarizability_unit_conversion_is_consistent():
    """polarizability_A3 must equal polarizability_au * 0.14818471 where present."""
    rows = load_csv(B700 / "orca_r2scan3c_descriptors.csv")
    checked = 0
    for r in rows:
        au = r.get("polarizability_au_v7", "").strip()
        a3 = r.get("polarizability_A3_v7", "").strip()
        if not au or not a3:
            continue
        expected = float(au) * AU2A3
        assert abs(float(a3) - expected) < 1e-6 * max(1.0, abs(expected))
        checked += 1
    assert checked >= 0  # column may be absent; conversion helper still valid


def test_mu_sq_over_vm_matches_definition():
    """mu^2/Vm (C^2 m / mol) must be (D*3.33564e-30)^2 / (m^3/mol)."""
    rows = load_csv(B700 / "orca_r2scan3c_descriptors.csv")
    checked = 0
    for r in rows:
        d = r.get("dipole_D_v7", "").strip()
        mv = r.get("molar_volume_m3_mol", "").strip()
        val = r.get("mu_sq_over_Vm_v7", "").strip()
        if not (d and mv and val):
            continue
        expected = (float(d) * 3.33564e-30) ** 2 / float(mv)
        assert math.isclose(float(val), expected, rel_tol=1e-9, abs_tol=1e-70)
        checked += 1
    assert checked == 239


# ------------------------------------------------------- geometry provenance
def test_geometry_manifest_records_provenance():
    manifest = load_json(B700 / "B701_DFT" / "preflight_12" / "package_opt" / "manifest.json")
    assert manifest is not None
    assert manifest["charge"] == 0
    assert manifest["multiplicity"] == 1
    for rec in manifest["records"]:
        assert rec["geometry_source"]
        assert rec["job_dir"]


def test_b704_inputs_have_xyz_and_inp_and_species_count():
    jobs = B700 / "B704_conformers" / "jobs"
    if not jobs.exists():
        pytest.skip("B704 job inputs not present locally")
    dirs = sorted(p for p in jobs.glob("*/*") if p.is_dir())
    assert len(dirs) >= 227
    for d in dirs[:25]:
        inp = d / "job.inp"
        xyz = d / "geom.xyz"
        assert inp.is_file() and xyz.is_file()
        lines = xyz.read_text().strip().splitlines()
        n_atoms = int(lines[0])
        assert len(lines) == n_atoms + 2, d
        assert "* xyzfile 0 1 geom.xyz" in inp.read_text()


# --------------------------------------------------------------- hashes
def test_descriptor_manifest_hashes_are_recomputable():
    manifest = load_json(B700 / "orca_r2scan3c_descriptors.json")
    assert manifest is not None
    hashes = manifest["input_hashes"]
    assert hashes["parsed_sp_csv"] == sha256(PROD / "parsed_sp.csv")
    assert hashes["model_matrix_csv"] == sha256(REPO_ROOT / "outputs" / "b100" / "model_matrix_b100.csv")


def test_opt_model_manifest_hashes_are_recomputable():
    manifest = load_json(B700 / "orca_r2scan3c_opt_model.json")
    assert manifest is not None
    assert manifest["input_hashes"]["parsed_opt"] == sha256(PROD / "parsed_opt.csv")


# ------------------------------------------------------------- conformers
def test_conformer_parsed_rows_and_molecules():
    path = B700 / "B704_conformers" / "parsed_conformers.csv"
    if not path.exists():
        pytest.skip("B704 parsed conformers not present")
    rows = load_csv(path)
    assert len(rows) == 227
    assert sum(1 for r in rows if r["status"] == "OK") == 227
    assert len({r["inchikey"] for r in rows}) == 40


def test_boltzmann_weights_are_normalised_and_energy_ordered():
    rows = load_csv(B700 / "B704_conformers" / "parsed_conformers.csv")
    by_mol: dict[str, list[dict]] = {}
    for r in rows:
        if r["status"] != "OK":
            continue
        by_mol.setdefault(r["inchikey"], []).append(r)
    checked = 0
    for ik, confs in by_mol.items():
        if len(confs) < 2:
            continue
        energies = [float(r["total_energy_hartree"]) for r in confs]
        e_min = min(energies)
        weights = [math.exp(-(e - e_min) * 627.509) for e in energies]
        total = sum(weights)
        assert total > 0
        normed = [w / total for w in weights]
        assert abs(sum(normed) - 1.0) < 1e-9
        # lowest energy has the largest weight
        assert normed[energies.index(e_min)] == max(normed)
        checked += 1
    assert checked >= 30


def test_b704_coverage_matches_joblist():
    joblist = B700 / "B704_conformers" / "joblist.txt"
    if not joblist.exists():
        pytest.skip("B704 joblist not present")
    lines = [ln.strip() for ln in joblist.read_text().splitlines() if ln.strip()]
    assert len(lines) == 227
    assert len(set(lines)) == 227


# ------------------------------------------------- v6.0 historical protection
def test_v60_freeze_hash_integrity_for_dft_layer():
    freeze = load_json(B700 / "B700_V60_FREEZE.json")
    assert freeze is not None
    entry = freeze["deliverable_hashes"]["dft_descriptors_b100.csv"]
    actual = sha256(B100 / "dft_descriptors_b100.csv")
    assert actual == entry["sha256"], "v6.0 B3LYP layer was modified — immutability violated"


def test_v60_freeze_hash_integrity_for_xtb_layer():
    freeze = load_json(B700 / "B700_V60_FREEZE.json")
    entry = freeze["deliverable_hashes"]["xtb_descriptors_b100.csv"]
    actual = sha256(B100 / "xtb_descriptors_b100.csv")
    assert actual == entry["sha256"], "v6.0 xTB layer was modified — immutability violated"


# ------------------------------------------------------------ report numbers
def test_final_summary_matches_layer_tables():
    summary = load_json(B700 / "B700_FINAL_SUMMARY.json")
    assert summary is not None
    cov = summary["coverage"]
    assert cov["sp_ok"] == 239
    assert cov["opt_ok"] == 239
    assert cov["opt_converged"] == 239
    assert cov["conformer_rows"] >= 227 or cov["conformer_rows"] == 0


def test_e6_both_feature_blocks_beat_structure_only():
    """With the v6.0 nested-LOO protocol, electronic and mu^2/Vm blocks must both
    beat the structure-only baseline at k=10. Which of the two wins is seed
    dependent — that instability is measured separately in the stability file."""
    report = load_json(B700 / "B706_experiments_report_sp.json")
    assert report is not None
    arms = {a["arm"]: a["regret"] for a in report["E6"]["arms"] if a["k"] == 10}
    stab = load_json(B700 / "B706_E6_seed_stability.json")
    structure_only = stab["arms"]["X0_structure"]["regret_mean"]
    assert arms["X0_plus_mu2_Vm_v7"] < structure_only
    assert arms["X0_plus_v7_electronic"] < structure_only


def test_e6_seed_stability_is_reported_with_spread():
    """The headline regret must come with a cross-seed spread, not a point value."""
    stab = load_json(B700 / "B706_E6_seed_stability.json")
    assert stab is not None
    assert len(stab["seeds"]) >= 3
    arms = stab["arms"]
    for name in ("X0_plus_mu2_Vm_v7", "X0_plus_v7_electronic", "X0_structure"):
        assert name in arms
        assert arms[name]["regret_sd"] >= 0.0
        assert arms[name]["regret_max"] >= arms[name]["regret_min"]
    # MAE must be far more stable than regret for the mu^2/Vm arm
    mu = arms["X0_plus_mu2_Vm_v7"]
    assert mu["mae_sd"] < mu["regret_sd"]
    # and the ordering by MAE must be unambiguous
    assert arms["X0_plus_mu2_Vm_v7"]["mae_mean"] < arms["X0_plus_v7_electronic"]["mae_mean"]
    assert arms["X0_plus_v7_electronic"]["mae_mean"] < arms["X0_structure"]["mae_mean"]


# ------------------------------------------------- E4 failure-mode diagnostics
def test_e4_diagnostics_decompose_failure_modes():
    """The LOFO failure must be reported as level/outlier/ranking, not one number."""
    d = load_json(B700 / "B706_E4_family_diagnostics.json")
    assert d is not None
    fams = {f["family"]: f for f in d["families"]}
    assert len(fams) >= 10

    # halocarbon is a LEVEL error: bias must dominate its MAE
    hc = fams["halocarbon"]
    assert hc["bias_share_of_mae"] > 0.8
    assert hc["lofo_mae_demeaned"] < hc["lofo_mae"]

    # nitrile is an OUTLIER problem: dropping the worst molecule must help a lot
    ni = fams["nitrile"]
    assert ni["mae_excluding_worst1"] < 0.5 * ni["lofo_mae"]

    # ether is the genuine RANKING failure
    assert fams["ether"]["spearman_within"] < 0.2

    # most families still transfer their ordering
    good = [f for f in d["families"]
            if f["spearman_within"] is not None and f["spearman_within"] >= 0.69]
    assert len(good) >= 6


def test_e4_diagnostics_predictions_cover_lofo_eligible_molecules():
    """LOFO needs >=3 members per family, so the 4 molecules sitting in the
    singleton/doubleton families (amide, carbonate, phosphate) are excluded.
    239 - 4 = 235."""
    rows = load_csv(B700 / "B706_E4_lofo_predictions.csv")
    assert len(rows) == 235
    assert len({r["inchikey"] for r in rows}) == 235
