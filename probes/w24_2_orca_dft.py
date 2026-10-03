# W24-2 -- Axis A P_1 / P_2 at the DFT level: ORCA 6.1.1 r2SCAN-3c three-state
# vertical dSCF (gas + CPCM/SMD acetonitrile), replicated on the parent paper core set.
#
# Why this arm exists
# ------------------
# W23-2 and W24-1 instantiated P_1 only at the GFN2-xTB semi-empirical level, so this
# repository ladder and the parent paper ladder live on different rungs: signs and
# structure could be compared, numbers could not.  The repository documents
# (reports/w21_framework_slot_map.md line 48, reports/week23_2_project_charter.md line 65)
# that ORCA is "not in this repository toolchain".  A filesystem check falsifies that
# registration: E:/ORCA/orca_6_1_1/orca.exe is present, licensed, and terminates
# normally on r2SCAN-3c.  Section 2.3 of the paper says every dSCF result is taken from
# three-state SINGLE POINT calculations, i.e. P_1/P_2 are vertical quantities on the
# shared GFN2 geometry G1 -- no Opt/Freq is needed, which is what makes a DFT-level
# instantiation affordable at all.
#
# Discipline: no frozen reading moves, no main-scoreboard shot (cumulative 12), no
# Reaxys number, and the W24-1 xTB layer is only read, never modified.

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _extra in (ROOT / "probes", ROOT / "src"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import w21_li_coordination as w21
import w24_condition_redox as w24
from electrolyte_ml.xtb_runner import run_xtb_subprocess, xtb_optimisation_arguments

HB = Path("E:/Claude Code/电解液溶剂-HB/电解液溶剂HB-Code")
CORE_SET = HB / "data" / "metadata" / "core_set.csv"
GAS_ANCHORS = HB / "data" / "anchors" / "gas_phase_anchors.csv"
SOLUTION_ANCHORS = HB / "data" / "anchors" / "solution_redox_anchors.csv"
ORCA_BINARY = Path("E:/ORCA/orca_6_1_1/orca.exe")

PREREG = ROOT / "probes" / "w24_2_orca_dft_prereg.json"
SUMMARY = ROOT / "probes" / "w24_2_orca_dft_summary.json"
LAYER_CSV = ROOT / "data" / "processed" / "w24_2_orca_dft_layer.csv"
ARTIFACTS = ROOT / "probes" / "artifacts"
REPORT = ROOT / "reports" / "w24_2_orca_dft.md"
ROSTER = ROOT / "data" / "processed" / "w21_chemical_space_metadata.csv"

HARTREE_TO_EV = 27.211386245988
XTBMEDIA = (("gas", None, 1.0),)
ORCA_MEDIA = (("gas", None), ("smd_acetonitrile", "ACETONITRILE"))
ORCA_STATES = (("neutral", 0, 1), ("cation", 1, 2), ("anion", -1, 2))
ORCA_ARM_KEYS = tuple(medium + "_" + state for medium, _s in ORCA_MEDIA for state, _q, _m in ORCA_STATES)
XT_ARM_KEYS = tuple("gfn2_gas_" + state for state, _q, _m in ORCA_STATES)
SMD_EPSILON = 35.6880
ANCHOR_MAE_P1_MAX_EV = 0.60
ANCHOR_P0PRIME_MIN_EV = 2.0
TAU_DECOUPLE_SLACK = 0.15
BRIDGE_RHO_MIN = 0.80
CONVENTION_TAU_SLACK = 0.10
UNBOUND_SHARE_MIN = 0.80
TOPK_RULES = w24.TOPK_RULES



def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now():
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat()


def resolve_orca():
    if not ORCA_BINARY.is_file():
        raise SystemExit("ORCA not found at " + str(ORCA_BINARY))
    return ORCA_BINARY


def inchi_key(smiles):
    from rdkit import Chem
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None
    return Chem.MolToInchiKey(molecule)


def build_molecule_list():
    """The union of the paper core set and the gas-phase anchor species."""

    entries = {}
    core_rows = w21.read_rows(CORE_SET)
    for row in core_rows:
        key = inchi_key(row.get("smiles") or "")
        if not key:
            continue
        entries[key] = {"inchikey": key, "canonical_smiles": row.get("smiles"),
                        "name": row.get("name"), "mol_id": row.get("mol_id"),
                        "roles": ["core"], "anchor_ip_eV": None, "anchor_kind": ""}
    anchor_rows = w21.read_rows(GAS_ANCHORS)
    seen = {}
    for row in anchor_rows:
        if (row.get("property") or "").strip() != "IP":
            continue
        value = w24.as_float(row.get("value_eV"))
        if value is None:
            continue
        kind = (row.get("method") or "").strip()
        key = inchi_key(row.get("smiles") or "")
        if not key:
            continue
        rank = 0 if kind == "exp" else 1
        previous = seen.get(key)
        if previous is None or rank < previous[0]:
            seen[key] = (rank, value, kind, row.get("species"), row.get("smiles"))
    for key, (rank, value, kind, species, smiles) in sorted(seen.items()):
        entry = entries.get(key)
        if entry is None:
            entry = {"inchikey": key, "canonical_smiles": smiles, "name": species,
                     "mol_id": "ANCHOR_" + (species or key[:8]), "roles": [],
                     "anchor_ip_eV": None, "anchor_kind": ""}
            entries[key] = entry
        entry["roles"].append("anchor")
        entry["anchor_ip_eV"] = value
        entry["anchor_kind"] = kind
    ordered = [entries[key] for key in sorted(entries)]
    for index, entry in enumerate(ordered):
        entry["row_index"] = index
        entry["seed"] = 42 + index
        entry["roles"] = sorted(set(entry["roles"]))
    return ordered


def vertical_arguments(input_name, charge, unpaired):
    """The frozen GFN2 command line without --opt: the vertical single point."""

    return [input_name, "--gfn", "2", "--chrg", str(charge), "--uhf", str(unpaired)]


def run_xtb_job(executable, label, xyz_text, charge, unpaired, timeout_seconds,
                optimise):
    scratch = Path(tempfile.mkdtemp(prefix="w242x_"))
    try:
        (scratch / (label + ".xyz")).write_text(xyz_text, encoding="utf-8")
        if optimise:
            arguments = xtb_optimisation_arguments(label + ".xyz", formal_charge=charge)
        else:
            arguments = vertical_arguments(label + ".xyz", charge, unpaired)
        started = time.perf_counter()
        completed = run_xtb_subprocess(executable, arguments, cwd=scratch,
                                       timeout_seconds=timeout_seconds)
        elapsed = time.perf_counter() - started
        text = completed.stdout.decode("utf-8", "replace")
        stderr_text = completed.stderr.decode("utf-8", "replace")
        optimized = scratch / "xtbopt.xyz"
        # w21.parse_arm treats the .xtboptok sentinel file as the "this run really finished"
        # flag, but xTB only writes that file for an OPTIMISATION.  A vertical single point
        # has no optimised geometry to certify, so its sentinel is the normal-termination
        # banner instead.  Without this the 3 x GFN2 vertical arms were all misread as
        # xtb_failed even though the energies were sitting in stdout.
        # This xTB build writes the science log to stdout but the banner itself to
        # stderr, so the banner has to be searched in both streams.
        banner = "normal termination of xtb"
        if optimise:
            sentinel = (scratch / ".xtboptok").is_file()
        else:
            sentinel = (int(completed.returncode) == 0
                        and (banner in text or banner in stderr_text))
        return {
            "returncode": int(completed.returncode),
            "stdout": text,
            "optimized_xyz": optimized.read_text(encoding="utf-8", errors="replace")
                              if optimized.is_file() else None,
            "charges_text": (scratch / "charges").read_text(encoding="utf-8", errors="replace")
                            if (scratch / "charges").is_file() else None,
            "sentinel": sentinel,
            "seconds": elapsed,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def orca_input(xyz_text, charge, multiplicity, solvent, nprocs, maxcore):
    lines = ["! r2SCAN-3c RIJCOSX TightSCF"]
    if solvent:
        lines[0] = lines[0] + " CPCM(" + solvent + ")"
    lines.append("%%pal nprocs %d end" % int(nprocs))
    lines.append("%%maxcore %d" % int(maxcore))
    if solvent:
        lines.append("%cpcm")
        lines.append("  smd true")
        lines.append("  SMDsolvent " + chr(34) + solvent + chr(34))
        lines.append("end")
    body = xyz_text.rstrip().splitlines()
    lines.append("* xyz %d %d" % (int(charge), int(multiplicity)))
    for line in body[2:]:
        lines.append(line)
    lines.append("*")
    return chr(10).join(lines) + chr(10)


def run_orca_job(label, xyz_text, charge, multiplicity, solvent, nprocs, maxcore,
                 timeout_seconds):
    scratch = Path(tempfile.mkdtemp(prefix="w242o_"))
    try:
        (scratch / (label + ".inp")).write_text(
            orca_input(xyz_text, charge, multiplicity, solvent, nprocs, maxcore),
            encoding="utf-8",
        )
        started = time.perf_counter()
        import subprocess
        timed_out = False
        try:
            completed = subprocess.run(
                [str(ORCA_BINARY), label + ".inp"], cwd=scratch, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=timeout_seconds, check=False,
            )
            text = completed.stdout.decode("utf-8", "replace")
            returncode = int(completed.returncode)
        except subprocess.TimeoutExpired as exc:
            # A hung MPI job must not take the whole arm down: keep the partial log,
            # mark it, and let the caller decide whether to retry serially.
            timed_out = True
            partial = exc.output or b""
            if isinstance(partial, str):
                text = partial
            else:
                text = partial.decode("utf-8", "replace")
            returncode = -1
        elapsed = time.perf_counter() - started
        # The Windows build of ORCA 6.1.1 writes its whole log to stdout and only
        # creates side files (.gbw, .property.txt, .bibtex).  A .out file appears
        # only for some job types, so stdout is the primary source and .out the fallback.
        output = scratch / (label + ".out")
        if output.is_file():
            file_text = output.read_text(encoding="utf-8", errors="replace")
            if file_text.strip():
                text = file_text
        return {"returncode": returncode, "stdout": text, "seconds": elapsed,
                "timed_out": timed_out}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


ORBITAL_HEADER = re.compile(r"^\s*NO\s+OCC\s+E\(Eh\)\s+E\(eV\)\s*$")
ORBITAL_ROW = re.compile(r"^\s*(\d+)\s+([0-9]*\.[0-9]+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")


def orbital_rows(text):
    """Every (index, occupancy, energy_eV) row of every ORBITAL ENERGIES table.

    ORCA 6 does not tag the frontier orbitals with HOMO / LUMO labels, and an
    unrestricted run prints one table per spin, so the frontier is read off the
    occupancy column instead -- which is what a vertical dSCF needs anyway.
    """

    rows = []
    collecting = False
    for line in text.splitlines():
        if ORBITAL_HEADER.match(line):
            collecting = True
            continue
        if not collecting:
            continue
        match = ORBITAL_ROW.match(line)
        if match:
            rows.append((int(match.group(1)), float(match.group(2)), float(match.group(4))))
            continue
        if line.strip():
            collecting = False
    return rows


def frontier_orbitals(text):
    rows = orbital_rows(text)
    if not rows:
        return None, None
    occupied = [item for item in rows if item[1] > 0.5]
    virtual = [item for item in rows if item[1] <= 0.5]
    homo = max(occupied, key=lambda item: item[2])[2] if occupied else None
    lumo = min(virtual, key=lambda item: item[2])[2] if virtual else None
    return homo, lumo

def parse_orca(text):
    payload = {"terminated": "ORCA TERMINATED NORMALLY" in text,
               "final_sp_energy_hartree": None, "smd_cds_total_hartree": None,
               "epsilon": None, "homo_eV": None, "lumo_eV": None,
               "scf_converged": "SCF CONVERGED" in text or "SUCCESS" in text,
               "n_scf_cycles": None}
    final = re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", text)
    if final:
        payload["final_sp_energy_hartree"] = float(final[-1])
    cds = re.findall(r"Total Energy after SMD CDS correction\s*=\s*(-?\d+\.\d+)", text)
    if cds:
        payload["smd_cds_total_hartree"] = float(cds[-1])
    eps = re.findall(r"Epsilon\s+\.{2,}\s+(-?\d+\.\d+)", text)
    if eps:
        payload["epsilon"] = float(eps[-1])
    payload["homo_eV"], payload["lumo_eV"] = frontier_orbitals(text)
    cycles = re.findall(r"SCF ITERATIONS\s*\n?-+\s*\n?\s*ITER\s+Energy", text)
    payload["n_scf_cycles"] = len(cycles) if cycles else None
    return payload



def repair_record(payload):
    """Recompute the three GFN2 vertical single points of one molecule.

    The ORCA jobs of this arm are expensive and were all fine; only the cheap xTB
    vertical arms were mis-parsed.  This re-derives the G1 geometry (a few seconds)
    and re-runs the three vertical points so the expensive half is never repeated.
    """

    index, entry, xtb_executable, timeout_seconds = payload
    from rdkit import Chem

    molecule, _ff_status, error = w21.embed(entry["canonical_smiles"], entry["seed"])
    if molecule is None:
        return {"row_index": index, "repaired": False, "reason": error or "embed_failed"}
    net = int(Chem.GetFormalCharge(molecule))
    start_xyz = Chem.MolToXYZBlock(molecule)
    optimized = run_xtb_job(xtb_executable, "repair_g1_%03d" % index, start_xyz, net, 0,
                            timeout_seconds, True)
    g1 = w21.parse_arm(optimized)
    geometry = optimized.get("optimized_xyz") if g1.get("status") == "ok" else None
    if not geometry:
        geometry = start_xyz
    gfn2 = {}
    for state, delta_q, unpaired in ORCA_STATES:
        result = run_xtb_job(xtb_executable, "repair_sp_%03d_%s" % (index, state), geometry,
                             net + delta_q, unpaired, timeout_seconds, False)
        gfn2[state] = w21.parse_arm(result)
    return {"row_index": index, "repaired": True, "g1": g1, "gfn2": gfn2}


def run_repair(records_by_index, entries, xtb_executable, workers, timeout_seconds):
    by_index = {int(entry["row_index"]): entry for entry in entries}
    payloads = [(index, by_index[index], xtb_executable, timeout_seconds)
                for index in sorted(records_by_index) if index in by_index]
    if not payloads:
        return 0
    repaired = 0
    if workers == 1:
        results = [repair_record(payload) for payload in payloads]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool_executor:
            results = list(pool_executor.map(repair_record, payloads, chunksize=1))
    for patch in results:
        if not patch.get("repaired"):
            continue
        record = records_by_index[patch["row_index"]]
        record["g1"] = patch["g1"]
        record["gfn2"] = patch["gfn2"]
        repaired += 1
    return repaired


def rewrite_checkpoint(path, records_by_index):
    tmp = Path(str(path) + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", encoding="utf-8", newline=chr(10)) as handle:
        for index in sorted(records_by_index):
            handle.write(json.dumps(records_by_index[index], ensure_ascii=False) + chr(10))
    tmp.replace(path)

def run_molecule(payload):
    index, entry, xtb_executable, orca_nprocs, maxcore, timeout_seconds = payload
    from rdkit import Chem

    record = {
        "row_index": index, "name": entry.get("name"), "mol_id": entry.get("mol_id"),
        "canonical_smiles": entry.get("canonical_smiles"), "inchikey": entry.get("inchikey"),
        "roles": ",".join(entry.get("roles") or []), "seed": entry.get("seed"),
        "heavy_atoms": "", "ff_status": "", "error": "", "seconds_total": 0.0,
        "g1": {}, "gfn2": {}, "orca": {},
    }
    molecule, ff_status, error = w21.embed(entry["canonical_smiles"], entry["seed"])
    if molecule is None:
        record["error"] = error or "embed_failed"
        return record
    record["ff_status"] = ff_status
    record["heavy_atoms"] = int(molecule.GetNumHeavyAtoms())
    net = int(Chem.GetFormalCharge(molecule))
    start_xyz = Chem.MolToXYZBlock(molecule)
    total = 0.0

    optimized = run_xtb_job(xtb_executable, "g1_%03d" % index, start_xyz, net, 0,
                            timeout_seconds, True)
    total += float(optimized.get("seconds") or 0.0)
    g1 = w21.parse_arm(optimized)
    record["g1"] = g1
    geometry = optimized.get("optimized_xyz") if g1.get("status") == "ok" else None
    if not geometry:
        geometry = start_xyz
        record["error"] = (record["error"] + " | g1_opt_failed_used_embedded_geometry").strip(" |")

    for state, delta_q, unpaired in ORCA_STATES:
        result = run_xtb_job(xtb_executable, "sp_%03d_%s" % (index, state), geometry,
                             net + delta_q, unpaired, timeout_seconds, False)
        total += float(result.get("seconds") or 0.0)
        record["gfn2"][state] = w21.parse_arm(result)

    for medium, solvent in ORCA_MEDIA:
        for state, delta_q, unpaired in ORCA_STATES:
            label = "o%03d_%s_%s" % (index, medium, state)
            try:
                result = run_orca_job(label, geometry, net + delta_q, unpaired, solvent,
                                      orca_nprocs, maxcore, timeout_seconds)
                parsed = parse_orca(result["stdout"])
                parsed["timed_out"] = bool(result.get("timed_out"))
                parsed["status"] = "ok" if parsed["terminated"] else "orca_failed"
                parsed["seconds"] = float(result.get("seconds") or 0.0)
                total += parsed["seconds"]
            except Exception as exc:  # noqa: BLE001 - the message is the evidence
                parsed = {"terminated": False, "final_sp_energy_hartree": None,
                          "smd_cds_total_hartree": None, "epsilon": None, "homo_eV": None,
                          "lumo_eV": None, "scf_converged": False, "n_scf_cycles": None,
                          "status": "exception", "seconds": 0.0, "error": str(exc)[:200]}
            if parsed.get("status") != "ok" and orca_nprocs > 1:
                # Fallback: the same job with a single MPI process.  A parallel r2SCAN-3c
                # CPCM job can deadlock on this host (observed: four MPI ranks idle with
                # ~17 s of CPU after six minutes of work), and the serial form does not.
                try:
                    retry = run_orca_job(label + "_serial", geometry, net + delta_q, unpaired,
                                         solvent, 1, maxcore, timeout_seconds)
                    retry_parsed = parse_orca(retry["stdout"])
                    retry_parsed["timed_out"] = bool(retry.get("timed_out"))
                    retry_parsed["status"] = ("ok" if retry_parsed["terminated"]
                                              else "orca_failed")
                    retry_parsed["seconds"] = float(retry.get("seconds") or 0.0)
                    retry_parsed["serial_retry"] = True
                    total += retry_parsed["seconds"]
                    parsed["serial_retry"] = True
                    parsed["serial_retry_status"] = retry_parsed["status"]
                    if retry_parsed["status"] == "ok":
                        parsed = retry_parsed
                except Exception as exc:  # noqa: BLE001 - the message is the evidence
                    parsed["serial_retry"] = True
                    parsed["serial_retry_status"] = "exception"
                    parsed["serial_retry_error"] = str(exc)[:200]
            record["orca"][medium + "_" + state] = parsed
    record["seconds_total"] = total
    return record


def layer_fields():
    fields = ["mol_id", "name", "canonical_smiles", "inchikey", "roles", "row_index",
              "seed", "heavy_atoms", "ff_status", "anchor_ip_eV", "anchor_kind",
              "gfn2_g1_status", "gfn2_g1_E_hartree", "gfn2_g1_homo_eV", "gfn2_g1_lumo_eV",
              "gfn2_g1_gap_eV"]
    for state, _q, _m in ORCA_STATES:
        fields += ["gfn2_gas_" + state + "_E_hartree", "gfn2_gas_" + state + "_homo_eV",
                   "gfn2_gas_" + state + "_lumo_eV", "gfn2_gas_" + state + "_status"]
    fields += ["gfn2_ip_gas_eV", "gfn2_ea_gas_eV", "p0_ox_eV", "p0_red_eV"]
    for arm in ORCA_ARM_KEYS:
        fields += ["orca_" + arm + "_E_hartree", "orca_" + arm + "_E_cds_hartree",
                   "orca_" + arm + "_homo_eV", "orca_" + arm + "_lumo_eV",
                   "orca_" + arm + "_epsilon", "orca_" + arm + "_terminated",
                   "orca_" + arm + "_status", "orca_" + arm + "_seconds"]
    for medium, _solvent in ORCA_MEDIA:
        fields += ["orca_ip_" + medium + "_eV", "orca_ea_" + medium + "_eV",
                   "orca_ip_cds_" + medium + "_eV", "orca_ea_cds_" + medium + "_eV",
                   "orca_anion_unbound_" + medium]
    fields += ["seconds_total", "error"]
    return fields


LAYER_FIELDS = layer_fields()


def build_layer_rows(records, entries):
    by_index = {int(entry["row_index"]): entry for entry in entries}
    rows = []
    for record in sorted(records, key=lambda item: item.get("row_index", 0)):
        row = {field: "" for field in LAYER_FIELDS}
        index = int(record.get("row_index", 0))
        entry = by_index.get(index, {})
        row["mol_id"] = record.get("mol_id") or entry.get("mol_id") or ""
        row["name"] = record.get("name") or entry.get("name") or ""
        row["canonical_smiles"] = record.get("canonical_smiles") or entry.get("canonical_smiles") or ""
        row["inchikey"] = record.get("inchikey") or entry.get("inchikey") or ""
        row["roles"] = record.get("roles") or ",".join(entry.get("roles") or [])
        row["row_index"] = index
        row["seed"] = record.get("seed") or entry.get("seed") or ""
        row["heavy_atoms"] = record.get("heavy_atoms", "")
        row["ff_status"] = record.get("ff_status", "")
        row["anchor_ip_eV"] = w24.fmt(entry.get("anchor_ip_eV"))
        row["anchor_kind"] = entry.get("anchor_kind") or ""
        row["error"] = record.get("error") or ""
        row["seconds_total"] = w24.fmt(record.get("seconds_total") or 0.0, 6)
        g1 = record.get("g1") or {}
        row["gfn2_g1_status"] = g1.get("status") or "not_computed"
        row["gfn2_g1_E_hartree"] = w24.fmt(g1.get("total_energy_hartree"))
        row["gfn2_g1_homo_eV"] = w24.fmt(g1.get("homo_eV"))
        row["gfn2_g1_lumo_eV"] = w24.fmt(g1.get("lumo_eV"))
        row["gfn2_g1_gap_eV"] = w24.fmt(g1.get("gap_eV"))
        gfn2 = record.get("gfn2") or {}
        for state, _q, _m in ORCA_STATES:
            payload = gfn2.get(state) or {}
            prefix = "gfn2_gas_" + state + "_"
            row[prefix + "E_hartree"] = w24.fmt(payload.get("total_energy_hartree"))
            row[prefix + "homo_eV"] = w24.fmt(payload.get("homo_eV"))
            row[prefix + "lumo_eV"] = w24.fmt(payload.get("lumo_eV"))
            row[prefix + "status"] = payload.get("status") or "not_computed"
        neutral_e = w24.as_float(row["gfn2_gas_neutral_E_hartree"])
        cation_e = w24.as_float(row["gfn2_gas_cation_E_hartree"])
        anion_e = w24.as_float(row["gfn2_gas_anion_E_hartree"])
        if neutral_e is not None and cation_e is not None:
            row["gfn2_ip_gas_eV"] = w24.fmt((cation_e - neutral_e) * HARTREE_TO_EV)
        if neutral_e is not None and anion_e is not None:
            row["gfn2_ea_gas_eV"] = w24.fmt((neutral_e - anion_e) * HARTREE_TO_EV)
        homo = w24.as_float(row["gfn2_g1_homo_eV"])
        lumo = w24.as_float(row["gfn2_g1_lumo_eV"])
        if homo is not None:
            row["p0_ox_eV"] = w24.fmt(-homo)
        if lumo is not None:
            row["p0_red_eV"] = w24.fmt(lumo)
        orca = record.get("orca") or {}
        for arm in ORCA_ARM_KEYS:
            payload = orca.get(arm) or {}
            prefix = "orca_" + arm + "_"
            row[prefix + "E_hartree"] = w24.fmt(payload.get("final_sp_energy_hartree"))
            row[prefix + "E_cds_hartree"] = w24.fmt(payload.get("smd_cds_total_hartree"))
            row[prefix + "homo_eV"] = w24.fmt(payload.get("homo_eV"))
            row[prefix + "lumo_eV"] = w24.fmt(payload.get("lumo_eV"))
            row[prefix + "epsilon"] = w24.fmt(payload.get("epsilon"))
            row[prefix + "terminated"] = str(bool(payload.get("terminated")))
            row[prefix + "status"] = payload.get("status") or "not_computed"
            row[prefix + "seconds"] = w24.fmt(payload.get("seconds"), 4)
        for medium, _solvent in ORCA_MEDIA:
            n_e = w24.as_float(row["orca_" + medium + "_neutral_E_hartree"])
            c_e = w24.as_float(row["orca_" + medium + "_cation_E_hartree"])
            a_e = w24.as_float(row["orca_" + medium + "_anion_E_hartree"])
            if n_e is not None and c_e is not None:
                row["orca_ip_" + medium + "_eV"] = w24.fmt((c_e - n_e) * HARTREE_TO_EV)
            if n_e is not None and a_e is not None:
                row["orca_ea_" + medium + "_eV"] = w24.fmt((n_e - a_e) * HARTREE_TO_EV)
            n_c = w24.as_float(row["orca_" + medium + "_neutral_E_cds_hartree"])
            c_c = w24.as_float(row["orca_" + medium + "_cation_E_cds_hartree"])
            a_c = w24.as_float(row["orca_" + medium + "_anion_E_cds_hartree"])
            if n_c is not None and c_c is not None:
                row["orca_ip_cds_" + medium + "_eV"] = w24.fmt((c_c - n_c) * HARTREE_TO_EV)
            if n_c is not None and a_c is not None:
                row["orca_ea_cds_" + medium + "_eV"] = w24.fmt((n_c - a_c) * HARTREE_TO_EV)
            anion_homo = w24.as_float(row["orca_" + medium + "_anion_homo_eV"])
            if anion_homo is not None:
                row["orca_anion_unbound_" + medium] = "yes" if anion_homo > 0.0 else "no"
        rows.append(row)
    return rows



ANCHOR_LAYERS = (("P0_koopmans", "p0_ox_eV"), ("P0prime_gfn2_dscf", "gfn2_ip_gas_eV"),
                 ("P1_r2scan3c_gas", "orca_ip_gas_eV"))


def anchor_analysis(rows):
    from scipy import stats

    table = {}
    for label, key in ANCHOR_LAYERS:
        pairs = []
        for row in rows:
            anchor = w24.as_float(row.get("anchor_ip_eV"))
            value = w24.as_float(row.get(key))
            if anchor is None or value is None:
                continue
            pairs.append((anchor, value, row.get("name")))
        if len(pairs) < 3:
            table[label] = {"n": len(pairs), "insufficient": True}
            continue
        anchor = np.asarray([item[0] for item in pairs], dtype=float)
        value = np.asarray([item[1] for item in pairs], dtype=float)
        error = value - anchor
        table[label] = {
            "n": len(pairs), "insufficient": False,
            "mae_eV": float(np.mean(np.abs(error))),
            "bias_eV": float(np.mean(error)),
            "max_abs_error_eV": float(np.max(np.abs(error))),
            "tau_b": float(stats.kendalltau(anchor, value, variant="b").statistic),
            "spearman_rho": float(stats.spearmanr(anchor, value).statistic),
            "members": [item[2] for item in pairs],
        }
    return table


def rung_set(rows, ox_source, ox_target, red_source, red_target, name, description, paper):
    out = []
    for axis, source_key, target_key in (("ox", ox_source, ox_target),
                                         ("red", red_source, red_target)):
        source, target, keys = pair_arrays_rows(rows, source_key, target_key)
        if source.size < 5:
            out.append({"rung": name, "axis": axis, "description": description, "n": int(source.size),
                        "insufficient": True, "maps_to_paper": paper})
            continue
        metrics = w24.rung_metrics(source, target)
        boot = w24.bootstrap_rung(source, target, 2000, 20261002)
        metrics["tau_b_ci"] = boot["tau_b"]
        metrics["spearman_rho_ci"] = boot["spearman_rho"]
        metrics.update({"rung": name, "axis": axis, "description": description,
                        "maps_to_paper": paper, "insufficient": False})
        out.append(metrics)
    return out


def axis_value(row, key):
    """Read an axis column; a leading minus means "negate" (e.g. -EA for the red axis)."""

    if key.startswith("-"):
        value = w24.as_float(row.get(key[1:]))
        return None if value is None else -value
    return w24.as_float(row.get(key))


def pair_arrays_rows(rows, source_key, target_key):
    source, target, keys = [], [], []
    for row in rows:
        left = axis_value(row, source_key)
        right = axis_value(row, target_key)
        if left is None or right is None:
            continue
        source.append(left)
        target.append(right)
        keys.append(row.get("inchikey") or row.get("name"))
    return np.asarray(source, dtype=float), np.asarray(target, dtype=float), keys


def bridge_analysis(rows):
    from scipy import stats

    pairs = []
    for row in rows:
        xtb_value = w24.as_float(row.get("gfn2_ip_gas_eV"))
        dft_value = w24.as_float(row.get("orca_ip_gas_eV"))
        if xtb_value is None or dft_value is None:
            continue
        pairs.append((xtb_value, dft_value, row.get("name")))
    if len(pairs) < 3:
        return {"n": len(pairs), "verdict": "no_data"}
    xtb_values = np.asarray([item[0] for item in pairs], dtype=float)
    dft_values = np.asarray([item[1] for item in pairs], dtype=float)
    offset = dft_values - xtb_values
    rho = float(stats.spearmanr(xtb_values, dft_values).statistic)
    tau = float(stats.kendalltau(xtb_values, dft_values, variant="b").statistic)
    return {
        "n": len(pairs),
        "members": [item[2] for item in pairs],
        "rho": rho, "tau_b": tau,
        "offset_mean_eV": float(np.mean(offset)),
        "offset_sd_eV": float(np.std(offset, ddof=1)),
        "offset_min_eV": float(np.min(offset)),
        "offset_max_eV": float(np.max(offset)),
        "rho_threshold": BRIDGE_RHO_MIN,
        "verdict": "成立" if rho >= BRIDGE_RHO_MIN else "判否",
    }


RUNG_SPECS = (
    ("P0->P0prime", "method: Koopmans -> GFN2 vertical dSCF (gas)",
     "p0_ox_eV", "gfn2_ip_gas_eV", "p0_red_eV", "-gfn2_ea_gas_eV", "P0->P0prime"),
    ("P0->P1", "method: GFN2 Koopmans -> r2SCAN-3c vertical dSCF (gas)",
     "p0_ox_eV", "orca_ip_gas_eV", "p0_red_eV", "-orca_ea_gas_eV", "P0->P1"),
    ("P1->P2", "environment: gas -> CPCM/SMD acetonitrile (r2SCAN-3c)",
     "orca_ip_gas_eV", "orca_ip_smd_acetonitrile_eV", "-orca_ea_gas_eV",
     "-orca_ea_smd_acetonitrile_eV", "P1->P2"),
    ("P0->P1_cds", "method, SMD-CDS energy convention",
     "p0_ox_eV", "orca_ip_gas_eV", "p0_red_eV", "-orca_ea_gas_eV", "P0->P1"),
    ("P1->P2_cds", "environment, SMD-CDS energy convention",
     "orca_ip_gas_eV", "orca_ip_cds_smd_acetonitrile_eV", "-orca_ea_gas_eV",
     "-orca_ea_cds_smd_acetonitrile_eV", "P1->P2"),
)


def build_rungs(rows):
    out = []
    for name, description, ox_source, ox_target, red_source, red_target, paper in RUNG_SPECS:
        out += rung_set(rows, ox_source, ox_target, red_source, red_target, name, description, paper)
    return out


def find_rung(rungs, name, axis):
    for entry in rungs:
        if entry["rung"] == name and entry["axis"] == axis and not entry.get("insufficient"):
            return entry
    return None



def build_summary(records, rows, entries, prereg, prereg_sha, elapsed, generated_at):
    anchors = anchor_analysis(rows)
    rungs = build_rungs(rows)
    bridge = bridge_analysis(rows)

    unbound = {"n": 0, "yes": 0}
    for row in rows:
        flag = row.get("orca_anion_unbound_gas")
        if flag in ("yes", "no"):
            unbound["n"] += 1
            unbound["yes"] += 1 if flag == "yes" else 0
    unbound["share"] = (unbound["yes"] / unbound["n"]) if unbound["n"] else 0.0

    p0 = anchors.get("P0_koopmans") or {}
    p0p = anchors.get("P0prime_gfn2_dscf") or {}
    p1 = anchors.get("P1_r2scan3c_gas") or {}
    o1 = {"statement": "reproduce paper Table 1: P1 MAE ~ 0.25 eV",
          "mae_eV": p1.get("mae_eV"), "threshold_eV": ANCHOR_MAE_P1_MAX_EV, "n": p1.get("n"),
          "verdict": "成立" if (p1.get("mae_eV") is not None
                             and p1["mae_eV"] <= ANCHOR_MAE_P1_MAX_EV) else "判否"}
    ok2 = (p0.get("mae_eV") is not None and p0p.get("mae_eV") is not None
           and p0["mae_eV"] < p0p["mae_eV"] and p0p["mae_eV"] >= ANCHOR_P0PRIME_MIN_EV)
    o2 = {"statement": "P0 MAE < P0prime MAE and P0prime MAE >= 2.0 eV",
          "mae_P0_eV": p0.get("mae_eV"), "mae_P0prime_eV": p0p.get("mae_eV"),
          "verdict": "成立" if ok2 else "判否"}
    ok3 = (p0p.get("tau_b") is not None and p1.get("tau_b") is not None
           and p0p["tau_b"] >= p1["tau_b"] - TAU_DECOUPLE_SLACK)
    o3 = {"statement": "value error and ranking error decouple: tau(P0prime) >= tau(P1) - 0.15",
          "tau_P0prime": p0p.get("tau_b"), "tau_P1": p1.get("tau_b"),
          "verdict": "成立" if ok3 else "判否"}
    r_p01_ox = find_rung(rungs, "P0->P1", "ox")
    r_p01_red = find_rung(rungs, "P0->P1", "red")
    ok4 = (r_p01_ox and r_p01_red and r_p01_ox["mean_shift_eV"] < 0
           and r_p01_red["mean_shift_eV"] > 0)
    o4 = {"statement": "P0->P1: ox shift negative, red shift positive",
          "ox_mean_eV": (r_p01_ox or {}).get("mean_shift_eV"),
          "red_mean_eV": (r_p01_red or {}).get("mean_shift_eV"),
          "paper": {"ox": -1.5496, "red": 7.5919},
          "verdict": "成立" if ok4 else "判否"}
    r_p12_ox = find_rung(rungs, "P1->P2", "ox")
    r_p12_red = find_rung(rungs, "P1->P2", "red")
    ok5 = (r_p12_ox and r_p12_red and r_p12_ox["mean_shift_eV"] < 0
           and r_p12_red["mean_shift_eV"] < 0 and r_p01_ox
           and r_p12_ox["tau_b"] > r_p01_ox["tau_b"])
    o5 = {"statement": "P1->P2: both shifts negative and tau(P1->P2 ox) > tau(P0->P1 ox)",
          "ox_mean_eV": (r_p12_ox or {}).get("mean_shift_eV"),
          "red_mean_eV": (r_p12_red or {}).get("mean_shift_eV"),
          "tau_ox_environment": (r_p12_ox or {}).get("tau_b"),
          "tau_ox_method": (r_p01_ox or {}).get("tau_b"),
          "paper": {"ox": -2.3934, "red": -2.1731},
          "verdict": "成立" if ok5 else "判否"}
    o6 = {"statement": "gas-phase anion unbound is the majority signature",
          "n": unbound["n"], "yes": unbound["yes"], "share": unbound["share"],
          "threshold": UNBOUND_SHARE_MIN,
          "paper": "18/18", "verdict": "成立" if unbound["share"] >= UNBOUND_SHARE_MIN else "判否"}
    o7 = dict(bridge)
    o7["statement"] = ("xTB GFN2 vertical dSCF IP ranks like the ORCA r2SCAN-3c IP (Spearman rho >= " + str(BRIDGE_RHO_MIN) + ")")
    o8_entries = {}
    ok8 = True
    for axis in ("ox", "red"):
        a = find_rung(rungs, "P1->P2", axis)
        b = find_rung(rungs, "P1->P2_cds", axis)
        if a is None or b is None:
            ok8 = False
            o8_entries[axis] = None
            continue
        delta = abs(a["tau_b"] - b["tau_b"])
        o8_entries[axis] = {"tau_primary": a["tau_b"], "tau_cds": b["tau_b"], "abs_delta": delta}
        if delta > CONVENTION_TAU_SLACK:
            ok8 = False
    o8 = {"statement": "energy convention (SMD CDS) does not move tau by more than 0.10",
          "entries": o8_entries, "threshold": CONVENTION_TAU_SLACK,
          "verdict": "成立" if ok8 else "判否"}

    orca_arms = [arm for arm in ORCA_ARM_KEYS]
    ok_arms = 0
    bad_arms = 0
    eps_values = []
    for row in rows:
        for arm in orca_arms:
            if row.get("orca_" + arm + "_status") == "ok":
                ok_arms += 1
            else:
                bad_arms += 1
            value = w24.as_float(row.get("orca_" + arm + "_epsilon"))
            if value is not None:
                eps_values.append(value)
    pool = {
        "n_molecules": len(rows),
        "n_core": sum(1 for row in rows if "core" in (row.get("roles") or "")),
        "n_anchor": sum(1 for row in rows if "anchor" in (row.get("roles") or "")),
        "orca_jobs_planned": len(rows) * len(orca_arms),
        "orca_jobs_ok": ok_arms,
        "orca_jobs_bad": bad_arms,
        "epsilon_observed": sorted(set(eps_values))[:5],
        "elapsed_seconds": round(float(elapsed), 1),
        "generated_at_utc": generated_at,
    }
    return {
        "schema_version": "w24_2_orca_dft_summary@1",
        "task": prereg["task"], "title": prereg["title"],
        "prereg_sha256": prereg_sha,
        "orca_binary": str(ORCA_BINARY),
        "pool": pool, "anchors": anchors, "rungs": rungs, "bridge": bridge,
        "unbound_anion": unbound,
        "orca_arm_qc": {"ok": ok_arms, "bad": bad_arms,
                        "per_arm": {arm: sum(1 for row in rows
                                              if row.get("orca_" + arm + "_status") == "ok")
                                     for arm in orca_arms}},
        "hypotheses": {"O1": o1, "O2": o2, "O3": o3, "O4": o4, "O5": o5,
                       "O6": o6, "O7": o7, "O8": o8},
        "declared_limits": prereg["declared_limits"],
    }


RUNG_CSV_FIELDS = ["rung", "axis", "description", "maps_to_paper", "n", "pairs",
                   "mean_shift_eV", "std_shift_eV", "mean_abs_shift_eV",
                   "tau_b", "tau_b_lo", "tau_b_hi", "spearman_rho", "spearman_lo",
                   "spearman_hi", "f_unresolved_z=1", "f_unresolved_z=1.96",
                   "f_robust_inversion", "topk10_overlap", "topk20_overlap",
                   "topk30_overlap"]


def fx(value, digits=12):
    if value is None:
        return "n/a"
    return w24.fmt(value, digits)


def topk_overlap(entry, fraction):
    for label, share in TOPK_RULES:
        if abs(float(share) - float(fraction)) < 1e-9:
            payload = (entry.get("topk") or {}).get(label)
            return None if not payload else payload.get("overlap")
    return None


def rung_rows(summary):
    rows = []
    for entry in summary["rungs"]:
        if entry.get("insufficient"):
            rows.append([entry["rung"], entry["axis"], entry.get("description", ""),
                         entry.get("maps_to_paper") or "", entry.get("n", 0)]
                        + [""] * (len(RUNG_CSV_FIELDS) - 5))
            continue
        boot = entry.get("tau_b_ci") or {}
        boot_rho = entry.get("spearman_rho_ci") or {}
        overlaps = [topk_overlap(entry, share) for _label, share in TOPK_RULES]
        rows.append([
            entry["rung"], entry["axis"], entry["description"], entry.get("maps_to_paper") or "",
            entry["n"], entry["pairs"],
            fx(entry["mean_shift_eV"]), fx(entry["std_shift_eV"]), fx(entry["mean_abs_shift_eV"]),
            fx(entry["tau_b"]), fx(boot.get("lo")), fx(boot.get("hi")),
            fx(entry["spearman_rho"]), fx(boot_rho.get("lo")), fx(boot_rho.get("hi")),
            fx(entry["f_unresolved_z=1"]), fx(entry["f_unresolved_z=1.96"]),
            fx(entry["f_robust_inversion"]),
            fx(overlaps[0]), fx(overlaps[1]), fx(overlaps[2]),
        ])
    return rows


PAPER_ANCHORS = (("P0_koopmans", 1.377, 0.6061), ("P0prime_gfn2_dscf", 4.481, 0.9111),
                 ("P1_r2scan3c_gas", 0.251, 0.727))


def write_artifacts(summary, rows):
    from collections import Counter

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    w21.write_csv(ARTIFACTS / "w24_2_rung_table.csv", list(RUNG_CSV_FIELDS), rung_rows(summary))

    anchor_rows = []
    for label, _key in ANCHOR_LAYERS:
        entry = summary["anchors"].get(label) or {}
        if entry.get("insufficient"):
            anchor_rows.append([label, entry.get("n", 0), "", "", "", "", ""])
            continue
        anchor_rows.append([label, entry["n"], fx(entry["mae_eV"]), fx(entry["bias_eV"]),
                            fx(entry["max_abs_error_eV"]), fx(entry["tau_b"]),
                            fx(entry["spearman_rho"])])
    w21.write_csv(ARTIFACTS / "w24_2_anchor_table.csv",
                  ["layer", "n", "mae_eV", "bias_eV", "max_abs_error_eV", "tau_b",
                   "spearman_rho"], anchor_rows)
    w21.write_csv(ARTIFACTS / "w24_2_anchor_paper_reference.csv",
                  ["layer", "paper_mae_eV", "paper_tau_b"],
                  [[label, paper_mae, paper_tau] for label, paper_mae, paper_tau in PAPER_ANCHORS])

    rung_sign_rows = []
    for name in sorted({entry["rung"] for entry in summary["rungs"]}):
        for axis in ("ox", "red"):
            entry = find_rung(summary["rungs"], name, axis)
            paper = (PAPER_RUNG_SIGNS.get(name) or {}).get(axis)
            rung_sign_rows.append([name, axis, fx((entry or {}).get("mean_shift_eV")),
                                   fx((entry or {}).get("tau_b")), fx(paper)])
    w21.write_csv(ARTIFACTS / "w24_2_rung_vs_paper.csv",
                  ["rung", "axis", "our_mean_shift_eV", "our_tau_b", "paper_mean_shift_eV"],
                  rung_sign_rows)

    bridge = summary["bridge"]
    w21.write_csv(ARTIFACTS / "w24_2_bridge.csv", ["quantity", "value"],
                  [["n", bridge.get("n")], ["rho", fx(bridge.get("rho"))],
                   ["tau_b", fx(bridge.get("tau_b"))],
                   ["offset_mean_eV", fx(bridge.get("offset_mean_eV"))],
                   ["offset_sd_eV", fx(bridge.get("offset_sd_eV"))],
                   ["offset_min_eV", fx(bridge.get("offset_min_eV"))],
                   ["offset_max_eV", fx(bridge.get("offset_max_eV"))],
                   ["rho_threshold", bridge.get("rho_threshold")],
                   ["verdict", bridge.get("verdict")]])

    unbound = summary["unbound_anion"]
    w21.write_csv(ARTIFACTS / "w24_2_unbound_anion.csv",
                  ["medium", "n", "yes", "share", "threshold", "verdict"],
                  [["gas", unbound["n"], unbound["yes"], fx(unbound["share"]),
                    UNBOUND_SHARE_MIN,
                    "成立" if unbound["share"] >= UNBOUND_SHARE_MIN else "判否"]])

    w21.write_csv(ARTIFACTS / "w24_2_hypotheses.csv",
                  ["id", "statement", "verdict", "detail"],
                  [[key, value.get("statement"), value.get("verdict"),
                    json.dumps({k: v for k, v in value.items()
                                if k not in ("statement", "verdict")}, ensure_ascii=False)]
                   for key, value in summary["hypotheses"].items()])

    qc_rows = []
    for arm in ORCA_ARM_KEYS:
        counts = Counter((row.get("orca_" + arm + "_status") or "missing") for row in rows)
        epsilons = [w24.as_float(row.get("orca_" + arm + "_epsilon")) for row in rows]
        epsilons = [value for value in epsilons if value is not None]
        seconds = [w24.as_float(row.get("orca_" + arm + "_seconds")) for row in rows]
        seconds = [value for value in seconds if value is not None]
        qc_rows.append([arm, counts.get("ok", 0), counts.get("orca_failed", 0),
                        counts.get("exception", 0), counts.get("not_computed", 0), len(rows),
                        fx(min(epsilons)) if epsilons else "",
                        fx(max(epsilons)) if epsilons else "",
                        fx(sum(seconds) / len(seconds), 3) if seconds else "",
                        fx(max(seconds), 3) if seconds else ""])
    w21.write_csv(ARTIFACTS / "w24_2_qc.csv",
                  ["arm", "ok", "orca_failed", "exception", "not_computed", "n_rows",
                   "epsilon_min", "epsilon_max", "seconds_mean", "seconds_max"], qc_rows)


PAPER_RUNG_SIGNS = {"P0->P1": {"ox": -1.5496, "red": 7.5919},
                    "P1->P2": {"ox": -2.3934, "red": -2.1731}}


def render_report(summary):
    h = summary["hypotheses"]
    pool = summary["pool"]
    lines = []

    def add(text=""):
        lines.append(text)

    add("# W24-2 · Axis A 的 P_1 / P_2 DFT 级首次实例化（ORCA 6.1.1 r2SCAN-3c）")
    add()
    add("- 任务：`" + str(summary["task"]) + "` ｜ 预注册 sha256：`" + str(summary["prereg_sha256"]) + "`")
    add("- ORCA：`" + str(summary["orca_binary"]) + "`（6.1.1 / r2SCAN-3c / def2-mTZVPP / RIJCOSX / TightSCF）")
    add("- 几何：G1 = GFN2-xTB 优化几何；P_1 与 P_2 均为**垂直**三态 ΔSCF 单点（母体论文 2.3 口径），不做 Opt+Freq")
    add("- 规模：分子 " + str(pool["n_molecules"]) + " 个（核心集 " + str(pool["n_core"])
        + " ｜ 气相锚点 " + str(pool["n_anchor"]) + "）；ORCA 作业 " + str(pool["orca_jobs_planned"])
        + " 个，成功 " + str(pool["orca_jobs_ok"]) + "，失败 " + str(pool["orca_jobs_bad"]))
    add("- 记分牌纪律：本次**不取主记分牌 shot**（W24 计 0，历史累计 12），冻结读数不动")
    add()
    add("## 1. 假设裁决")
    add()
    add("| 编号 | 陈述 | 裁决 |")
    add("|---|---|---|")
    for key in ("O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8"):
        entry = h.get(key) or {}
        add("| " + key + " | " + str(entry.get("statement")) + " | **" + str(entry.get("verdict")) + "** |")
    add()
    add("### 关键读数")
    add()
    o1 = h.get("O1") or {}
    o2 = h.get("O2") or {}
    o3 = h.get("O3") or {}
    o4 = h.get("O4") or {}
    o5 = h.get("O5") or {}
    o6 = h.get("O6") or {}
    o7 = h.get("O7") or {}
    o8 = h.get("O8") or {}
    add("- O1：MAE(P1) = " + fx(o1.get("mae_eV"), 3) + " eV（阈值 " + str(o1.get("threshold_eV")) + "，论文 0.251）")
    add("- O2：MAE(P0) = " + fx(o2.get("mae_P0_eV"), 3) + " eV，MAE(P0prime) = " + fx(o2.get("mae_P0prime_eV"), 3) + " eV（论文 1.377 / 4.481）")
    add("- O3：tau(P0prime) = " + fx(o3.get("tau_P0prime"), 4) + "，tau(P1) = " + fx(o3.get("tau_P1"), 4) + "（论文 0.911 / 0.727）")
    add("- O4：P0->P1 氧化位移 " + fx(o4.get("ox_mean_eV"), 4) + " eV，还原位移 " + fx(o4.get("red_mean_eV"), 4) + " eV（论文 -1.5496 / +7.5919）")
    add("- O5：P1->P2 氧化位移 " + fx(o5.get("ox_mean_eV"), 4) + " eV，还原位移 " + fx(o5.get("red_mean_eV"), 4) + " eV；tau_ox(环境) = " + fx(o5.get("tau_ox_environment"), 4) + " vs tau_ox(方法) = " + fx(o5.get("tau_ox_method"), 4) + "（论文 -2.3934 / -2.1731）")
    add("- O6：气相阴离子不束缚 " + str(o6.get("yes")) + "/" + str(o6.get("n")) + " = " + fx(o6.get("share"), 4) + "（论文 18/18）")
    add("- O7：xTB-DFT 桥 n = " + str(o7.get("n")) + "，rho = " + fx(o7.get("rho"), 4) + "，tau_b = " + fx(o7.get("tau_b"), 4) + "，偏移 " + fx(o7.get("offset_mean_eV"), 4) + " ± " + fx(o7.get("offset_sd_eV"), 4) + " eV")
    add("- O8：SMD-CDS 能量约定对 tau 的最大改动 " + fx(max([abs(v["abs_delta"]) for v in (o8.get("entries") or {}).values() if v] or [None]) if any((o8.get("entries") or {}).values()) else None, 4) + "（阈值 " + str(o8.get("threshold")) + "）")
    add()
    add("## 2. 锚点复现（论文 Table 1，气相锚点）")
    add()
    add("| 层 | n | MAE (eV) | 偏置 (eV) | max abs err (eV) | tau_b | 论文 MAE | 论文 tau_b |")
    add("|---|---|---|---|---|---|---|---|")
    for label, paper_mae, paper_tau in PAPER_ANCHORS:
        entry = summary["anchors"].get(label) or {}
        if entry.get("insufficient"):
            add("| `" + label + "` | " + str(entry.get("n", 0)) + " | n/a | n/a | n/a | n/a | " + fx(paper_mae, 3) + " | " + str(paper_tau) + " |")
            continue
        add("| `" + label + "` | " + str(entry["n"]) + " | " + fx(entry["mae_eV"], 3)
            + " | " + fx(entry["bias_eV"], 3) + " | " + fx(entry["max_abs_error_eV"], 3)
            + " | " + fx(entry["tau_b"], 4) + " | " + fx(paper_mae, 3) + " | " + str(paper_tau) + " |")
    add()
    add("## 3. 台阶表（方法台阶 P0 -> P0prime -> P1，环境台阶 P1 -> P2）")
    add()
    add("| 台阶 | 轴 | n | 配对 | mean shift (eV) | std (eV) | tau_b | tau 95% CI | f_unresolved(1.96) | top10% | 论文 |")
    add("|---|---|---|---|---|---|---|---|---|---|---|")
    for entry in summary["rungs"]:
        paper = (PAPER_RUNG_SIGNS.get(entry["rung"]) or {}).get(entry["axis"])
        if entry.get("insufficient"):
            add("| `" + entry["rung"] + "` | " + entry["axis"] + " | " + str(entry.get("n", 0))
                + " | n/a | n/a | n/a | n/a | n/a | n/a | n/a | " + fx(paper) + " |")
            continue
        boot = entry.get("tau_b_ci") or {}
        ci = "[" + fx(boot.get("lo"), 3) + ", " + fx(boot.get("hi"), 3) + "]"
        add("| `" + entry["rung"] + "` | " + entry["axis"] + " | " + str(entry["n"])
            + " | " + str(entry["pairs"]) + " | " + fx(entry["mean_shift_eV"], 4)
            + " | " + fx(entry["std_shift_eV"], 4) + " | " + fx(entry["tau_b"], 4)
            + " | " + ci + " | " + fx(entry["f_unresolved_z=1.96"], 4)
            + " | " + fx(topk_overlap(entry, 0.10), 4) + " | " + fx(paper) + " |")
    add()
    add("## 4. 阴离子不束缚签名（O6）")
    add()
    unbound = summary["unbound_anion"]
    add("- 气相阴离子 HOMO > 0 的分子：" + str(unbound["yes"]) + " / " + str(unbound["n"])
        + "（占比 " + fx(unbound["share"], 4) + "，阈值 " + str(UNBOUND_SHARE_MIN) + "）")
    add()
    add("## 5. xTB -> DFT 尺度桥（O7）")
    add()
    bridge = summary["bridge"]
    add("- 交集分子 n = " + str(bridge.get("n")) + "，Spearman rho = " + fx(bridge.get("rho"), 4)
        + "（阈值 " + str(BRIDGE_RHO_MIN) + "），Kendall tau_b = " + fx(bridge.get("tau_b"), 4))
    add("- DFT - xTB 的电离能偏移：" + fx(bridge.get("offset_mean_eV"), 4) + " ± "
        + fx(bridge.get("offset_sd_eV"), 4) + " eV（区间 " + fx(bridge.get("offset_min_eV"), 4)
        + " ~ " + fx(bridge.get("offset_max_eV"), 4) + " eV）")
    add()
    add("## 6. 逐臂 QC")
    add()
    add("| 臂 | 成功 | ORCA 失败 | 异常 | 未计算 | epsilon 观测 | 单作业均值 (s) | 单作业最大 (s) |")
    add("|---|---|---|---|---|---|---|---|")
    per_arm = (summary.get("orca_arm_qc") or {}).get("per_arm") or {}
    n_mol = int(pool["n_molecules"])
    for arm in ORCA_ARM_KEYS:
        ok = int(per_arm.get(arm, 0))
        # epsilon is an SMD read-back; a gas-phase arm has no implicit solvent, so the
        # pool-level value must not be printed as if that arm had produced it.
        epsilon = (str(pool["epsilon_observed"]) if arm.startswith("smd_")
                   else "n/a（气相臂）")
        add("| `" + arm + "` | " + str(ok) + " | " + str(n_mol - ok)
            + " | n/a | n/a | " + epsilon + " | n/a | n/a |")
    add()
    add("## 7. 声明限制（照抄预注册）")
    add()
    for item in summary.get("declared_limits") or []:
        add("- " + str(item))
    add()
    add("## 8. 复现命令")
    add()
    add("```powershell")
    add(".\\.venv\\Scripts\\python.exe probes\\w24_2_orca_dft.py --workers 2 --nprocs 8")
    add(".\\.venv\\Scripts\\python.exe probes\\w24_2_orca_dft.py --from-layer")
    add(".\\.venv\\Scripts\\python.exe probes\\w24_2_orca_dft.py --report-only")
    add("```")
    add()
    add("- 挂钟：" + str(pool.get("elapsed_seconds")) + " s ｜ 生成时间（UTC）：" + str(pool.get("generated_at_utc")))
    add()
    return chr(10).join(lines) + chr(10)


def record_checkpoint_path():
    return ARTIFACTS / "w24_2_orca_records.jsonl"


def load_checkpoint(path):
    records = {}
    if not path.is_file():
        return records
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            index = payload.get("row_index")
            if index is None:
                continue
            records[int(index)] = payload
    return records


def append_checkpoint(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline=chr(10)) as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + chr(10))


def estimated_cost(smiles):
    from rdkit import Chem
    molecule = Chem.MolFromSmiles(smiles)
    return 0 if molecule is None else int(molecule.GetNumHeavyAtoms())


def dispatch_order(entries):
    """Heaviest first: the six ORCA jobs of a big molecule are the long poles."""

    return sorted(range(len(entries)),
                  key=lambda index: (-estimated_cost(entries[index]["canonical_smiles"]), index))


def main(argv=None):
    parser = argparse.ArgumentParser(description="W24-2 ORCA r2SCAN-3c three-state vertical dSCF")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--nprocs", type=int, default=8)
    parser.add_argument("--maxcore", type=int, default=3000)
    parser.add_argument("--timeout", type=int, default=14400)
    parser.add_argument("--from-layer", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--no-checkpoint", action="store_true")
    parser.add_argument("--repair-gfn2", action="store_true")
    args = parser.parse_args(argv)

    if args.report_only:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        rows = w21.read_rows(LAYER_CSV)
        write_artifacts(summary, rows)
        REPORT.write_text(render_report(summary), encoding="utf-8", newline=chr(10))
        print(json.dumps({"mode": "report_only", "report": str(REPORT)}, ensure_ascii=False))
        return 0

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("status") != "locked_before_run":
        raise SystemExit("pre-registration is not locked; refusing to run")
    prereg_sha = sha256_file(PREREG)
    entries = build_molecule_list()
    if args.limit is not None:
        entries = entries[:args.limit]
    resolve_orca()
    xtb_executable = str(w21.resolve_xtb())

    if args.from_layer:
        rows = w21.read_rows(LAYER_CSV)
        previous = json.loads(SUMMARY.read_text(encoding="utf-8"))
        summary = build_summary([], rows, entries, prereg, prereg_sha,
                                previous["pool"]["elapsed_seconds"],
                                previous["pool"]["generated_at_utc"])
        write_artifacts(summary, rows)
        SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + chr(10),
                           encoding="utf-8", newline=chr(10))
        REPORT.write_text(render_report(summary), encoding="utf-8", newline=chr(10))
        print(json.dumps({"mode": "from_layer", "n": len(rows)}, ensure_ascii=False))
        return 0

    if args.repair_gfn2:
        workers = max(1, int(args.workers))
        records_by_index = load_checkpoint(record_checkpoint_path())
        repaired = run_repair(records_by_index, entries, xtb_executable, workers, args.timeout)
        rewrite_checkpoint(record_checkpoint_path(), records_by_index)
        # The repaired GFN2 columns have to land in the persisted layer too, otherwise
        # --from-layer keeps reading the stale layer that the failed run wrote.
        repaired_rows = build_layer_rows(list(records_by_index.values()), entries)
        w21.write_csv(LAYER_CSV, LAYER_FIELDS,
                      [[row[field] for field in LAYER_FIELDS] for row in repaired_rows])
        print(json.dumps({"mode": "repair_gfn2", "records": len(records_by_index),
                          "repaired": repaired, "layer_rows": len(repaired_rows)},
                         ensure_ascii=False), flush=True)
        return 0

    workers = max(1, int(args.workers))
    if workers * int(args.nprocs) > 16:
        raise SystemExit("workers * nprocs must not exceed the 16 logical cores of this host")
    total = len(entries)
    order = dispatch_order(entries)
    checkpoint = record_checkpoint_path()
    reused = {} if args.no_checkpoint else load_checkpoint(checkpoint)
    payloads = [(index, entries[index], xtb_executable, int(args.nprocs), int(args.maxcore),
                 args.timeout) for index in order if index not in reused]
    started = time.perf_counter()
    records = list(reused.values())
    skipped = len(records)
    if skipped:
        print(json.dumps({"mode": "resume", "reused": skipped, "remaining": len(payloads),
                          "checkpoint": str(checkpoint)}, ensure_ascii=False), flush=True)

    def snapshot():
        partial = build_layer_rows(records, entries)
        w21.write_csv(LAYER_CSV, LAYER_FIELDS,
                      [[row[field] for field in LAYER_FIELDS] for row in partial])
        return partial

    def announce(last_name):
        so_far = time.perf_counter() - started
        finished = len(records) - skipped
        eta = (so_far / finished * (total - len(records))) if finished else 0.0
        print(json.dumps({"processed": len(records), "total": total, "last": last_name,
                          "sec": round(so_far, 1), "eta_sec": round(eta, 1)},
                         ensure_ascii=False), flush=True)

    def keep(record):
        records.append(record)
        if not args.no_checkpoint:
            append_checkpoint(checkpoint, record)

    if workers == 1:
        for payload in payloads:
            record = run_molecule(payload)
            keep(record)
            snapshot()
            announce(record.get("name"))
    elif payloads:
        with ProcessPoolExecutor(max_workers=workers) as pool_executor:
            futures = [pool_executor.submit(run_molecule, payload) for payload in payloads]
            for future in as_completed(futures):
                record = future.result()
                keep(record)
                snapshot()
                announce(record.get("name"))
    rows = snapshot()
    elapsed = time.perf_counter() - started
    summary = build_summary(records, rows, entries, prereg, prereg_sha, elapsed, utc_now())
    summary["pool"]["checkpoint"] = {"path": str(checkpoint), "reused_records": skipped,
                                     "disabled": bool(args.no_checkpoint)}
    write_artifacts(summary, rows)
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + chr(10),
                       encoding="utf-8", newline=chr(10))
    REPORT.write_text(render_report(summary), encoding="utf-8", newline=chr(10))
    print(json.dumps({
        "summary": str(SUMMARY), "report": str(REPORT),
        "n_molecules": summary["pool"]["n_molecules"],
        "orca_jobs_ok": summary["pool"]["orca_jobs_ok"],
        "orca_jobs_bad": summary["pool"]["orca_jobs_bad"],
        "O1": summary["hypotheses"]["O1"]["verdict"],
        "O2": summary["hypotheses"]["O2"]["verdict"],
        "O3": summary["hypotheses"]["O3"]["verdict"],
        "O4": summary["hypotheses"]["O4"]["verdict"],
        "O5": summary["hypotheses"]["O5"]["verdict"],
        "O6": summary["hypotheses"]["O6"]["verdict"],
        "O7": summary["hypotheses"]["O7"]["verdict"],
        "O8": summary["hypotheses"]["O8"]["verdict"],
        "elapsed_seconds": round(elapsed, 1),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
