# Guards for the Week 24-2 ORCA r2SCAN-3c arm (Axis A P_1 / P_2 at the DFT level).
#
# The arm exists to correct a false registration: two repository documents stated that
# ORCA is not in this toolchain.  A filesystem check falsifies that.  The first smoke
# test then exposed two real integration defects, both pinned here:
#
# 1. the Windows build of ORCA 6.1.1 writes its whole log to stdout and never creates
#    <label>.out, so a reader that only looked for .out saw "terminated=False" on all
#    six arms of a perfectly normal run;
# 2. ORCA 6 prints no HOMO / LUMO labels in the ORBITAL ENERGIES table and prints one
#    table per spin for open-shell runs, so the frontier must be read off occupancy.

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "src"))

import w24_2_orca_dft as m

PREREG = ROOT / "probes/w24_2_orca_dft_prereg.json"
SUMMARY = ROOT / "probes/w24_2_orca_dft_summary.json"
LAYER = ROOT / "data/processed/w24_2_orca_dft_layer.csv"
HARTREE_TO_EV = 27.211386245988
LIVE = LAYER.is_file() and SUMMARY.is_file()

SYNTHETIC_OUTPUT = chr(10).join([
    "                                 *****************",
    "                                 * O   R   C   A *",
    "                                 *****************",
    "",
    "----------------",
    "ORBITAL ENERGIES",
    "----------------",
    "",
    "",
    "  NO   OCC          E(Eh)            E(eV) ",
    "   0   2.0000     -19.004458      -517.1376 ",
    "   1   2.0000      -0.257316        -7.0019 ",
    "   2   0.0000       0.012623         0.3435 ",
    "",
    "*Only the first 10 virtual orbitals were printed.",
    "",
    "FINAL SINGLE POINT ENERGY     -343.552367356066",
    "Total Energy after SMD CDS correction =  -343.56884572",
    "Epsilon ....................  35.6880",
    "****ORCA TERMINATED NORMALLY****",
])


def test_frontier_is_read_from_occupancy_not_labels():
    homo, lumo = m.frontier_orbitals(SYNTHETIC_OUTPUT)
    assert homo == -7.0019
    assert lumo == 0.3435
    rows = m.orbital_rows(SYNTHETIC_OUTPUT)
    assert rows == [(0, 2.0, -517.1376), (1, 2.0, -7.0019), (2, 0.0, 0.3435)]
    assert m.frontier_orbitals("no orbital block here") == (None, None)


def test_parse_orca_reads_stdout_shape():
    payload = m.parse_orca(SYNTHETIC_OUTPUT)
    assert payload["terminated"] is True
    assert payload["final_sp_energy_hartree"] == -343.552367356066
    assert payload["smd_cds_total_hartree"] == -343.56884572
    assert payload["epsilon"] == 35.6880
    assert payload["homo_eV"] == -7.0019
    assert payload["lumo_eV"] == 0.3435


def test_the_runner_must_not_depend_on_a_dot_out_file():
    source = (ROOT / "probes/w24_2_orca_dft.py").read_text(encoding="utf-8")
    assert "stderr=subprocess.STDOUT" in source
    assert "completed.stdout.decode" in source
    assert "capture_output=True" not in source


def test_orca_input_blocks():
    xyz = chr(10).join(["3", "water", "O 0.0 0.0 0.0", "H 0.0 0.0 0.96", "H 0.0 0.9 0.3"])
    gas = m.orca_input(xyz, 0, 1, None, 4, 1200)
    assert "! r2SCAN-3c RIJCOSX TightSCF" in gas
    assert "%pal nprocs 4 end" in gas
    assert "%maxcore 1200" in gas
    assert "%cpcm" not in gas
    assert "* xyz 0 1" in gas
    assert gas.count("*") == 2
    smd = m.orca_input(xyz, -1, 2, "ACETONITRILE", 4, 1200)
    assert "CPCM(ACETONITRILE)" in smd
    assert "smd true" in smd
    assert "SMDsolvent" in smd
    assert "* xyz -1 2" in smd


def test_preregistration_is_locked_and_hashed():
    payload = json.loads(PREREG.read_text(encoding="utf-8"))
    assert payload["status"] == "locked_before_run"
    digest = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    assert digest == "ecc63190d2c6d8e385aadb6916fa607130a0e0b66b27636192edcf509edc9228"


def test_six_arms_and_two_media():
    assert len(m.ORCA_MEDIA) == 2
    assert len(m.ORCA_STATES) == 3
    assert m.ORCA_ARM_KEYS == ("gas_neutral", "gas_cation", "gas_anion",
                              "smd_acetonitrile_neutral", "smd_acetonitrile_cation",
                              "smd_acetonitrile_anion")
    states = dict((state, (charge, mult)) for state, charge, mult in m.ORCA_STATES)
    assert states["neutral"] == (0, 1)
    assert states["cation"] == (1, 2)
    assert states["anion"] == (-1, 2)


def test_the_molecule_pool_is_the_paper_core_set_union_the_anchors():
    entries = m.build_molecule_list()
    assert len(entries) == 28
    assert sum(1 for entry in entries if "core" in entry["roles"]) == 18
    assert sum(1 for entry in entries if "anchor" in entry["roles"]) == 22
    keys = [entry["inchikey"] for entry in entries]
    assert len(set(keys)) == len(keys)
    assert all(entry["row_index"] == index for index, entry in enumerate(entries))


def _record(index):
    record = {
        "row_index": index, "name": "X", "mol_id": "M", "canonical_smiles": "C",
        "inchikey": "KEY", "roles": "core", "seed": 42, "heavy_atoms": 1,
        "ff_status": "ok", "error": "", "seconds_total": 1.0,
        "g1": {"status": "ok", "total_energy_hartree": -1.0, "homo_eV": -10.0,
               "lumo_eV": 1.0, "gap_eV": 11.0},
        "gfn2": {
            "neutral": {"status": "ok", "total_energy_hartree": -1.0,
                        "homo_eV": -10.0, "lumo_eV": 1.0, "gap_eV": 11.0},
            "cation": {"status": "ok", "total_energy_hartree": -0.6,
                       "homo_eV": -14.0, "lumo_eV": -1.0, "gap_eV": 13.0},
            "anion": {"status": "ok", "total_energy_hartree": -1.1,
                      "homo_eV": -0.5, "lumo_eV": 2.0, "gap_eV": 2.5},
        },
        "orca": {},
    }
    for arm in m.ORCA_ARM_KEYS:
        record["orca"][arm] = {"status": "ok", "terminated": True,
                               "final_sp_energy_hartree": -100.0,
                               "smd_cds_total_hartree": -100.1,
                               "epsilon": 35.688, "homo_eV": -5.0,
                               "lumo_eV": 1.0, "seconds": 1.0}
    record["orca"]["gas_cation"]["final_sp_energy_hartree"] = -99.5
    record["orca"]["gas_anion"]["final_sp_energy_hartree"] = -99.7
    record["orca"]["gas_anion"]["homo_eV"] = 0.3
    record["orca"]["smd_acetonitrile_cation"]["final_sp_energy_hartree"] = -99.4
    record["orca"]["smd_acetonitrile_anion"]["final_sp_energy_hartree"] = -99.9
    record["orca"]["smd_acetonitrile_anion"]["homo_eV"] = -1.2
    return record


def test_layer_row_derives_ip_ea_and_the_unbound_signature():
    entries = [{"row_index": 0, "mol_id": "M", "name": "X", "canonical_smiles": "C",
                "roles": ["core"], "seed": 42, "inchikey": "KEY",
                "anchor_ip_eV": 10.0, "anchor_kind": "exp"}]
    rows = m.build_layer_rows([_record(0)], entries)
    assert len(rows) == 1
    row = rows[0]
    assert abs(float(row["orca_ip_gas_eV"]) - 0.5 * HARTREE_TO_EV) < 1e-6
    assert abs(float(row["orca_ea_gas_eV"]) - (-0.3 * HARTREE_TO_EV)) < 1e-6
    assert row["orca_anion_unbound_gas"] == "yes"
    assert row["orca_anion_unbound_smd_acetonitrile"] == "no"
    assert abs(float(row["gfn2_ip_gas_eV"]) - 0.4 * HARTREE_TO_EV) < 1e-6
    assert abs(float(row["p0_ox_eV"]) - 10.0) < 1e-6
    assert set(row) == set(m.LAYER_FIELDS)


def test_the_red_axis_negates_ea():
    row = {"orca_ea_gas_eV": "-8.16"}
    assert m.axis_value(row, "-orca_ea_gas_eV") == 8.16
    assert m.axis_value(row, "orca_ea_gas_eV") == -8.16
    assert m.axis_value({"orca_ea_gas_eV": ""}, "-orca_ea_gas_eV") is None


def test_frozen_readings_are_not_restated_here():
    source = (ROOT / "probes/w24_2_orca_dft.py").read_text(encoding="utf-8")
    for frozen in ("0.4091179943351143", "0.4766400383507876",
                   "0.5861142332208197", "0.6216672295270079"):
        assert frozen not in source


def test_live_run_if_present():
    if not LIVE:
        return
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    pool = summary["pool"]
    assert pool["n_molecules"] == 28
    assert pool["orca_jobs_planned"] == 168
    # The arm does not promise a zero-failure run.  Nitrogen dioxide is a stable
    # radical, so the pre-registered closed-shell multiplicity for the neutral state
    # is impossible for it and ORCA rejects the input (odd multiplicity, 23 electrons).
    # What must hold is that the ledger closes and every failure is attributable.
    assert pool["orca_jobs_ok"] + pool["orca_jobs_bad"] == pool["orca_jobs_planned"]
    records = [json.loads(line) for line in
               (ROOT / "probes/artifacts/w24_2_orca_records.jsonl").read_text(
                   encoding="utf-8").splitlines() if line.strip()]
    failed = {}
    for record in records:
        bad = [arm for arm, payload in (record.get("orca") or {}).items()
               if payload.get("status") != "ok"]
        if bad:
            failed[record.get("name")] = len(bad)
    assert sum(failed.values()) == pool["orca_jobs_bad"]
    assert failed == {"nitrogen dioxide": 6}
    assert 35.688 in pool["epsilon_observed"]
    for key, entry in summary["hypotheses"].items():
        assert entry["verdict"] in ("成立", "判否", "部分成立", "no_data"), key
    bridge = summary["bridge"]
    assert bridge["n"] >= 17
    assert -1.0 <= bridge["rho"] <= 1.0
    assert bridge["n"] == pool["n_molecules"] - 1


def test_vertical_sentinel_accepts_the_banner_on_stderr(monkeypatch):
    # This xTB build prints the science log to stdout but the termination banner to
    # stderr.  The vertical arms have no .xtboptok to fall back on, so a stdout-only
    # sentinel marked all 84 of them failed while their energies sat in the log.
    class Finished:
        returncode = 0
        stdout = b"some science log"
        stderr = b"normal termination of xtb\n"

    monkeypatch.setattr(m, "run_xtb_subprocess", lambda *a, **k: Finished())
    payload = "3\nx\nO 0 0 0\nH 0 1 0\nLi 0 0 2\n"
    vertical = m.run_xtb_job("xtb.exe", "probe", payload, 1, 0, 60, False)
    assert vertical["sentinel"] is True

    class Failed:
        returncode = 1
        stdout = b"some science log"
        stderr = b""

    monkeypatch.setattr(m, "run_xtb_subprocess", lambda *a, **k: Failed())
    assert m.run_xtb_job("xtb.exe", "probe", payload, 1, 0, 60, False)["sentinel"] is False


def test_repair_mode_binds_its_workers_and_returns():
    # The repair branch read `workers` before it was bound and then fell through into
    # the full ORCA stage, so a repair would have re-run the 168 DFT jobs.  Both are
    # silent until the first real repair, so pin the shape of the branch.
    source = (ROOT / "probes/w24_2_orca_dft.py").read_text(encoding="utf-8")
    head = source.index("if args.repair_gfn2:")
    body = source[head:head + 1400]
    assert "workers = max(1, int(args.workers))" in body
    assert body.index("workers = max(1, int(args.workers))") < body.index("run_repair(")
    assert "return 0" in body

