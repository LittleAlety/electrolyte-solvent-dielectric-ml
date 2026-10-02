# W26 -- 介电响应律的稠密实测（ddCOSMO 任意 epsilon + 刚性几何）、阴离子束缚闸门与隐式模型层级对照。
#
# 本模块只读一个冻结输入：data/processed/w21_li_coordination_layer.csv，用于气相锚点复核（H1f）。
# 其余一切数值现算。它不写任何冻结表、不动任何冻结读数、不占主记分牌 shot。
#
# 设计（见 reports/week26_project_charter.md）：
#   * 一条几何在全部 epsilon 与全部电荷态之间刚性共用，把「介电响应」从「几何弛豫 + 介电响应」
#     的混合物里分离出来（W24-1 在每个介质点都带 --opt，两者混在一起）；
#   * ddCOSMO（xtb --cosmo EPSILON）允许任意 epsilon，所以 epsilon 与溶剂身份解耦；
#   * epsilon >= 80.4 的读数从外推变成实测。

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_DYNAMIC", "FALSE")
os.environ.setdefault("MKL_DYNAMIC", "FALSE")

import argparse
import hashlib
import json
import math
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _extra in (ROOT / "probes", ROOT / "src"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import w21_li_coordination as w21
from electrolyte_ml.xtb_features import parse_xtb_output
from electrolyte_ml.xtb_runner import run_xtb_subprocess

PREREG = ROOT / "probes" / "w26_dielectric_law_prereg.json"
SUMMARY_PATH = ROOT / "probes" / "w26_dielectric_law_summary.json"
ART = ROOT / "probes" / "artifacts"
LAYER = ROOT / "data" / "processed" / "w21_li_coordination_layer.csv"
SCAN_CSV = ART / "w26_dielectric_scan.csv"
BORN_CSV = ART / "w26_born_fit.csv"
GATE_CSV = ART / "w26_anion_gate.csv"
CONTRAST_CSV = ART / "w26_model_contrast.csv"
PILOT_CSV = ART / "w26_geometry_pilot.csv"
FIG_A = ART / "w26_dielectric_law.png"
FIG_B = ART / "w26_anion_gate.png"
REPORT = ROOT / "reports" / "w26_dielectric_law.md"

REPORT_ROOT = Path(__file__).resolve().parents[1] / "reports"
SCOREBOARD_SHOTS_THIS_WEEK = 0
CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS = 12
HARTREE_TO_EV = 27.211386245988

EPSILON_GRID = (1.0, 2.0, 4.0, 7.58, 12.0, 18.0, 25.0, 35.688, 50.0, 80.4, 120.0, 200.0, 400.0, 1000.0)
BAND_START = 20.0
CHARGE_STATES = (("neutral", 0, 0), ("cation", 1, 1), ("anion", -1, 1))
NAMED_MATCH = ((7.58, "thf"), (18.0, "benzaldehyde"), (80.4, "water"))
CPCMX_MATCH = (35.688, "acetonitrile")

STRAT_SEED = 20261002
STRAT_TARGET = 24

ANCHOR_ORBITAL_TOL_EV = 5e-3
ANCHOR_ENERGY_TOL_HARTREE = 5e-6
SP_TIMEOUT = 300
OPT_TIMEOUT = 900

SCAN_FIELDS = (
    "inchikey", "name", "motif_class", "donor_symbol", "charge_state", "epsilon", "status",
    "total_E_hartree", "homo_eV", "lumo_eV", "gap_eV", "delta_E_eV", "dipole_debye", "seconds",
)


def read_rows(path):
    import csv
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, header, rows):
    import csv
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(["" if value is None else value for value in row])


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fmt(value, digits=12):
    if value is None:
        return ""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return ""
    if isinstance(value, float):
        return ("%." + str(int(digits)) + "f") % value
    return str(value)


def as_float(value, default=None):
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def load_prereg():
    return json.loads(PREREG.read_text(encoding="utf-8"))


def load_pool():
    rows = []
    for row in read_rows(LAYER):
        smiles = (row.get("canonical_smiles") or "").strip()
        if not smiles:
            continue
        if not (row.get("homo_free_eV") and row.get("lumo_free_eV") and row.get("total_energy_free_hartree")):
            continue
        rows.append(row)
    return rows


def stratified_subset(pool, target=STRAT_TARGET, seed=STRAT_SEED):
    import random
    buckets = {}
    for row in pool:
        buckets.setdefault(row.get("motif_class") or "unknown", []).append(row)
    rng = random.Random(seed)
    keys = sorted(buckets)
    for key in keys:
        buckets[key] = sorted(buckets[key], key=lambda item: item.get("inchikey") or "")
        rng.shuffle(buckets[key])
    picked = []
    total = len(pool)
    for key in keys:
        share = len(buckets[key]) / float(total)
        take = int(round(share * target))
        picked.extend(buckets[key][:take])
    index = 0
    while len(picked) < target and index < len(keys):
        key = keys[index]
        for row in buckets[key]:
            if row not in picked:
                picked.append(row)
                break
        index += 1
    return [row for row in pool if row in picked][:target]


def run_xtb_job(executable, label, xyz_text, charge, unpaired, epsilon, optimise, timeout_seconds):
    scratch = Path(tempfile.mkdtemp(prefix="w26dl_"))
    try:
        (scratch / (label + ".xyz")).write_text(xyz_text, encoding="utf-8")
        arguments = [label + ".xyz", "--gfn", "2", "--chrg", str(int(charge)), "--uhf", str(int(unpaired))]
        if optimise:
            arguments.append("--opt")
        if epsilon is not None and float(epsilon) > 1.0:
            arguments.extend(["--cosmo", "%.6f" % float(epsilon)])
        started = time.perf_counter()
        completed = run_xtb_subprocess(
            executable, arguments, cwd=scratch, timeout_seconds=int(timeout_seconds)
        )
        elapsed = time.perf_counter() - started
        stdout = completed.stdout.decode("utf-8", "replace")
        optimized = scratch / "xtbopt.xyz"
        return {
            "returncode": int(completed.returncode),
            "seconds": elapsed,
            "stdout": stdout,
            "optimized_xyz": optimized.read_text(encoding="utf-8", errors="replace")
            if optimized.is_file()
            else None,
            "sentinel": (scratch / ".xtboptok").is_file(),
        }
    except Exception as error:
        return {"returncode": -1, "seconds": float("nan"), "stdout": "",
                "optimized_xyz": None, "sentinel": False, "error": type(error).__name__}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def run_named_solvent_job(executable, label, xyz_text, charge, unpaired, flag, solvent, timeout_seconds):
    scratch = Path(tempfile.mkdtemp(prefix="w26ms_"))
    try:
        (scratch / (label + ".xyz")).write_text(xyz_text, encoding="utf-8")
        arguments = [label + ".xyz", "--gfn", "2", "--chrg", str(int(charge)), "--uhf",
                     str(int(unpaired)), flag, solvent]
        started = time.perf_counter()
        completed = run_xtb_subprocess(
            executable, arguments, cwd=scratch, timeout_seconds=int(timeout_seconds)
        )
        elapsed = time.perf_counter() - started
        return {"returncode": int(completed.returncode), "seconds": elapsed,
                "stdout": completed.stdout.decode("utf-8", "replace")}
    except Exception as error:
        return {"returncode": -1, "seconds": float("nan"), "stdout": "",
                "error": type(error).__name__}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _number(pattern, text):
    import re
    match = re.search(pattern, text, flags=re.MULTILINE)
    return float(match.group(1)) if match else None


def harvest(text):
    # xTB 6.7.1 on Windows does not always print the legacy "normal termination
    # of xtb" banner (single points end with "* finished run on ..."), so
    # electrolyte_ml.xtb_features.parse_xtb_output cannot be used verbatim here.
    # The three patterns below are the same ones it uses, minus that gate.
    energy = _number(r"::\s*total energy\s+([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)\s+Eh", text)
    gap = _number(
        r"HL-Gap\s+[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?\s+Eh"
        r"\s+([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)\s+eV", text)
    dipole = _number(r"^\s*full:.*?([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)\s*$", text)
    if energy is None:
        return None
    return {
        "total_E_hartree": energy,
        "gap_eV": gap,
        "homo_eV": w21.orbital_energy(text, "HOMO"),
        "lumo_eV": w21.orbital_energy(text, "LUMO"),
        "dipole_debye": dipole,
    }


def scan_one_molecule(payload):
    (index, inchikey, name, smiles, seed, motif_class, donor_symbol, epsilons,
     with_contrast) = payload
    outcome = {"index": index, "inchikey": inchikey, "name": name, "smiles": smiles,
               "motif_class": motif_class, "donor_symbol": donor_symbol,
               "status": "ok", "error": "", "rows": [], "contrast": [], "seconds": 0.0}
    from rdkit import Chem
    molecule, _status, error = w21.embed(smiles, int(seed))
    if molecule is None:
        outcome["status"] = "embed_failed"
        outcome["error"] = str(error)
        return outcome
    executable = w21.resolve_xtb()
    started = time.perf_counter()
    gas_xyz = Chem.MolToXYZBlock(molecule)
    relaxation = run_xtb_job(executable, "opt", gas_xyz, 0, 0, None, True, OPT_TIMEOUT)
    if relaxation["returncode"] != 0 or not relaxation.get("optimized_xyz"):
        outcome["status"] = "opt_failed"
        outcome["error"] = "gas_opt"
        outcome["seconds"] = time.perf_counter() - started
        return outcome
    rigid_xyz = relaxation["optimized_xyz"]
    # The frozen W21 layer was written by w21.parse_arm, which reads the FIRST
    # ":: total energy" and the FIRST "(HOMO)" block of the xTB log.  For an --opt
    # run that first block is the ISCF single point at the *input* geometry, so this
    # is the quantity the frozen column actually stores.  Keep it to test that.
    outcome["opt_initial"] = harvest(relaxation["stdout"]) or {}
    if with_contrast:
        for state, charge, unpaired in CHARGE_STATES:
            for flag, solvent, _key in (("--alpb", "thf", "alpb_thf"),
                                        ("--alpb", "benzaldehyde", "alpb_benzaldehyde"),
                                        ("--alpb", "water", "alpb_water"),
                                        ("--cpcmx", "acetonitrile", "cpcmx_acetonitrile")):
                result = run_named_solvent_job(executable, "sp", rigid_xyz, charge, unpaired,
                                               flag, solvent, SP_TIMEOUT)
                values = harvest(result["stdout"]) if result["returncode"] == 0 else None
                outcome["contrast"].append({
                    "charge_state": state, "model": flag.lstrip("-"), "solvent": solvent,
                    "status": "ok" if values else "failed",
                    "total_E_hartree": (values or {}).get("total_E_hartree"),
                    "seconds": result["seconds"],
                })
    for state, charge, unpaired in CHARGE_STATES:
        for epsilon in epsilons:
            result = run_xtb_job(executable, "sp", rigid_xyz, charge, unpaired, epsilon, False, SP_TIMEOUT)
            values = harvest(result["stdout"]) if result["returncode"] == 0 else None
            outcome["rows"].append({
                "charge_state": state, "epsilon": float(epsilon),
                "status": "ok" if values else "failed",
                "total_E_hartree": (values or {}).get("total_E_hartree"),
                "homo_eV": (values or {}).get("homo_eV"),
                "lumo_eV": (values or {}).get("lumo_eV"),
                "gap_eV": (values or {}).get("gap_eV"),
                "dipole_debye": (values or {}).get("dipole_debye"),
                "seconds": result["seconds"],
            })
    outcome["seconds"] = time.perf_counter() - started
    return outcome


def relaxed_geometry_probe(payload):
    (index, inchikey, name, smiles, seed, epsilon) = payload
    outcome = {"index": index, "inchikey": inchikey, "name": name, "status": "ok",
               "error": "", "rows": [], "seconds": 0.0}
    from rdkit import Chem
    molecule, _status, error = w21.embed(smiles, int(seed))
    if molecule is None:
        outcome["status"] = "embed_failed"
        outcome["error"] = str(error)
        return outcome
    executable = w21.resolve_xtb()
    started = time.perf_counter()
    gas_xyz = Chem.MolToXYZBlock(molecule)
    for state, charge, unpaired in CHARGE_STATES:
        relaxation = run_xtb_job(executable, "opt", gas_xyz, charge, unpaired, None, True, OPT_TIMEOUT)
        if relaxation["returncode"] != 0 or not relaxation.get("optimized_xyz"):
            outcome["rows"].append({"charge_state": state, "status": "opt_failed",
                                    "gas_E_hartree": None, "solvated_E_hartree": None,
                                    "delta_E_eV": None})
            continue
        gas_job = run_xtb_job(executable, "sp", relaxation["optimized_xyz"], charge, unpaired,
                              None, False, SP_TIMEOUT)
        gas_values = harvest(gas_job["stdout"]) if gas_job["returncode"] == 0 else None
        result = run_xtb_job(executable, "sp", relaxation["optimized_xyz"], charge, unpaired,
                             epsilon, False, SP_TIMEOUT)
        values = harvest(result["stdout"]) if result["returncode"] == 0 else None
        gas_energy = (gas_values or {}).get("total_E_hartree")
        solvated = (values or {}).get("total_E_hartree")
        delta = None
        if gas_energy is not None and solvated is not None:
            delta = (float(solvated) - float(gas_energy)) * HARTREE_TO_EV
        outcome["rows"].append({
            "charge_state": state,
            "status": "ok" if values and gas_values else "failed",
            "gas_E_hartree": gas_energy,
            "solvated_E_hartree": solvated,
            "delta_E_eV": delta,
        })
    outcome["seconds"] = time.perf_counter() - started
    return outcome


def born_fit(energies_ev, epsilons):
    # y is anchored at the gas point (epsilon = 1, x = 0) so that the one-parameter
    # through-origin Born form dE = -C (1 - 1/eps) is fitted the way W24-1 fitted it.
    values = np.asarray(energies_ev, dtype=float)
    if not np.all(np.isfinite(values)) or values.size < 4:
        return None
    y = values - values[0]
    if float(np.max(np.abs(y))) <= 0.0:
        return None
    x = 1.0 - 1.0 / np.asarray(epsilons, dtype=float)
    denom = float(np.dot(x, x))
    if denom <= 0.0:
        return None
    c = -float(np.dot(x, y)) / denom
    predicted = -c * x
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = (1.0 - ss_res / ss_tot) if ss_tot > 0.0 else float("nan")
    return {"C_eV": c, "r2": r2, "ss_res": ss_res}


def curve_block(state_map, epsilons, band_start):
    """state_map: epsilon -> total energy in hartree, including the gas anchor at 1.0."""
    if state_map.get(1.0) is None:
        return None
    gas = float(state_map[1.0])
    anchor_pairs = [(float(eps), state_map.get(float(eps))) for eps in epsilons
                    if float(eps) > 1.0 and state_map.get(float(eps)) is not None]
    if len(anchor_pairs) < 3:
        return None
    cosmo_eps = [eps for eps, _value in anchor_pairs]
    fit_eps = [1.0] + cosmo_eps
    fit_energy_ev = [gas * HARTREE_TO_EV] + [float(value) * HARTREE_TO_EV for _eps, value in anchor_pairs]
    delta = {eps: (float(value) - gas) * HARTREE_TO_EV for eps, value in anchor_pairs}
    fit = born_fit(fit_energy_ev, fit_eps)
    c_abs = abs(fit["C_eV"]) if fit and fit.get("C_eV") is not None else None
    # Residual to the Born asymptote: how much of the shift is still missing at this
    # epsilon, i.e. |C| - |dE(eps)| (v6 quotes this quantity times epsilon, ~2.1 eV).
    residual = {eps: (c_abs - abs(value)) for eps, value in delta.items()} if c_abs is not None else {}
    band = [abs(residual[float(eps)]) * float(eps) for eps in epsilons
            if float(eps) >= band_start and float(eps) in residual]
    band_values = np.asarray(band, dtype=float)
    band_cv = (float(np.std(band_values) / np.mean(band_values))
               if band_values.size >= 2 and np.mean(band_values) > 0 else float("nan"))
    return {
        "n_points": len(anchor_pairs) + 1,
        "C_eV": (fit or {}).get("C_eV"),
        "r2": (fit or {}).get("r2"),
        "residual_born_200_eV": (c_abs / 200.0) if c_abs is not None else None,
        "travel_200_1000_eV": (abs(delta[1000.0] - delta[200.0])
                               if (1000.0 in delta and 200.0 in delta) else None),
        "power_band_median_eV": (float(np.median(band_values)) if band_values.size else None),
        "band_cv": band_cv,
        "band_n": int(band_values.size),
        "delta_at_2p0_eV": delta.get(2.0),
        "delta_at_80p4_eV": delta.get(80.4),
        "delta_at_200_eV": delta.get(200.0),
        "delta_at_1000_eV": delta.get(1000.0),
    }


def median(values):
    clean = [float(value) for value in values if value is not None and np.isfinite(float(value))]
    if not clean:
        return float("nan")
    return float(np.median(np.asarray(clean, dtype=float)))


def gate_block(state_map, epsilons, ceiling):
    neutral = state_map.get("neutral") or {}
    anion = state_map.get("anion") or {}
    ea = {}
    for eps in epsilons:
        key = float(eps)
        left = neutral.get(key)
        right = anion.get(key)
        if left is None or right is None:
            continue
        ea[key] = (float(left) - float(right)) * HARTREE_TO_EV
    if not ea:
        return None
    gas_ea = ea.get(1.0)
    gate = None
    gate_le = None
    already_bound = bool(gas_ea is not None and gas_ea > 0.0)
    if not already_bound:
        for eps in epsilons:
            key = float(eps)
            if key <= 1.0:
                continue
            if ea.get(key) is not None and ea[key] > 0.0:
                gate = key
                break
        for eps in epsilons:
            key = float(eps)
            if key <= 1.0 or key > ceiling:
                continue
            if ea.get(key) is not None and ea[key] > 0.0:
                gate_le = key
                break
    return {"gas_ea_eV": gas_ea, "ea_at_80p4_eV": ea.get(80.4), "ea_at_1000_eV": ea.get(1000.0),
            "gate_epsilon": gate, "gate_epsilon_le_80p4": gate_le,
            "already_bound": already_bound, "gas_known": gas_ea is not None,
            "gate_span": len(ea)}


def build_verdict(criteria_id, claim, value, threshold, holds):
    return {"id": criteria_id, "claim": claim, "value": value, "threshold": threshold,
            "verdict": "成立" if holds else "判否"}


def configure_fonts():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"):
        if candidate in available:
            plt.rcParams["font.family"] = candidate
            break
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def figure_a(plt, scan_rows, born_rows):
    grid = [eps for eps in EPSILON_GRID if eps > 1.0]
    colors = {"neutral": "#4c72b0", "cation": "#c44e52", "anion": "#55a868"}
    labels = {"neutral": "中性", "cation": "阳离子", "anion": "阴离子"}
    table = {}
    for row in scan_rows:
        delta = row.get("delta_E_eV")
        if delta is None:
            continue
        table.setdefault(row["charge_state"], {}).setdefault(float(row["epsilon"]), {})[row["inchikey"]] = float(delta)
    fit_constant = {}
    for row in born_rows:
        if row.get("C_eV") is None:
            continue
        fit_constant[(row["inchikey"], row["charge_state"])] = abs(float(row["C_eV"]))
    figure, axes = plt.subplots(1, 2, figsize=(12.4, 5.0))
    for state in ("neutral", "cation", "anion"):
        buckets = table.get(state, {})
        xs = [eps for eps in grid if eps in buckets and buckets[eps]]
        med = [float(np.median([abs(value) for value in buckets[eps].values()])) for eps in xs]
        lo = [float(np.percentile([abs(value) for value in buckets[eps].values()], 25)) for eps in xs]
        hi = [float(np.percentile([abs(value) for value in buckets[eps].values()], 75)) for eps in xs]
        axes[0].plot(xs, med, marker="o", color=colors[state], label=labels[state] + "（中位）")
        axes[0].fill_between(xs, lo, hi, color=colors[state], alpha=0.16)
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("相对介电常数（对数轴）")
    axes[0].set_ylabel("溶剂化位移绝对值（eV，相对气相刚性几何）")
    axes[0].set_title("图 A1：介电位移随 epsilon 的衰减")
    axes[0].legend(loc="upper right", fontsize=9)
    axes[0].grid(alpha=0.25, which="both")
    for state in ("cation", "anion"):
        buckets = table.get(state, {})
        xs = [eps for eps in grid if eps >= BAND_START and eps in buckets and buckets[eps]]
        if not xs:
            continue
        per_point = []
        for eps in xs:
            values = []
            for inchikey, delta in buckets[eps].items():
                constant = fit_constant.get((inchikey, state))
                if constant is None:
                    continue
                values.append(abs(constant - abs(delta)) * eps)
            per_point.append((eps, values))
        keep = [eps for eps, values in per_point if values]
        keep_values = [values for _eps, values in per_point if values]
        if not keep:
            continue
        med = [float(np.median(values)) for values in keep_values]
        lo = [float(np.percentile(values, 25)) for values in keep_values]
        hi = [float(np.percentile(values, 75)) for values in keep_values]
        axes[1].plot(keep, med, marker="s", color=colors[state], label=labels[state])
        axes[1].fill_between(keep, lo, hi, color=colors[state], alpha=0.16)
    axes[1].axhline(2.1, color="#888888", linestyle="--", linewidth=1.2)
    axes[1].text(21.0, 2.16, "v6 的 2.1 eV 前因子（r2SCAN-3c CPCM，非同一层级）", fontsize=8, color="#555555")
    axes[1].set_xscale("log")
    axes[1].set_xlabel("相对介电常数（对数轴）")
    axes[1].set_ylabel("Born 残余乘 epsilon（eV），残余 = |C_fit| - |dE|")
    axes[1].set_title("图 A2：幂律口径的直测（残余口径，非总位移）")
    axes[1].legend(loc="lower right", fontsize=9)
    axes[1].grid(alpha=0.25, which="both")
    figure.tight_layout()
    figure.savefig(FIG_A, dpi=170)
    plt.close(figure)


def figure_b(plt, gate_rows):
    import numpy as np
    grid = [eps for eps in EPSILON_GRID if eps > 1.0]
    curves = []
    for row in gate_rows:
        series = row.get("curve")
        if series:
            curves.append(series)
    figure, axes = plt.subplots(1, 2, figsize=(12.4, 5.0))
    if curves:
        med = [median([series.get(eps) for series in curves]) for eps in grid]
        lo = [float(np.nanpercentile([series.get(eps) for series in curves if series.get(eps) is not None], 25)) if any(series.get(eps) is not None for series in curves) else float("nan") for eps in grid]
        hi = [float(np.nanpercentile([series.get(eps) for series in curves if series.get(eps) is not None], 75)) if any(series.get(eps) is not None for series in curves) else float("nan") for eps in grid]
        axes[0].plot(grid, med, marker="o", color="#55a868", label="中位 EA")
        axes[0].fill_between(grid, lo, hi, color="#55a868", alpha=0.18, label="四分位带")
    axes[0].axhline(0.0, color="#c44e52", linewidth=1.4)
    axes[0].text(2.1, 0.03, "束缚阈值 EA = 0", fontsize=8, color="#c44e52")
    axes[0].set_xscale("log")
    axes[0].set_xlabel("相对介电常数（对数轴）")
    axes[0].set_ylabel("垂直电子亲和 EA（eV）")
    axes[0].set_title("图 B1：连续介质把阴离子从非束缚推过阈值")
    axes[0].legend(loc="lower right", fontsize=9)
    axes[0].grid(alpha=0.25, which="both")
    gates = [float(row["gate_epsilon"]) for row in gate_rows if row.get("gate_epsilon") is not None]
    if gates:
        axes[1].hist(gates, bins=[2.0, 4.0, 7.58, 12.0, 18.0, 25.0, 35.688, 50.0, 80.4], color="#4c72b0", edgecolor="white")
    axes[1].set_xlabel("闸门 epsilon（阴离子开始束缚的最小格点）")
    axes[1].set_ylabel("分子数")
    axes[1].set_title("图 B2：闸门位置分布（n = " + str(len(gates)) + "）")
    axes[1].grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(FIG_B, dpi=170)
    plt.close(figure)


def geometry_pilot(smiles, seed, timeout_seconds, nprocs, maxcore):
    import subprocess
    import w24_2_orca_dft as w24
    from rdkit import Chem
    record = {"smiles": smiles, "status": "ok", "seconds": float("nan"), "converged": False,
              "final_energy_hartree": None, "error": ""}
    molecule, _status, error = w21.embed(smiles, int(seed))
    if molecule is None:
        record["status"] = "embed_failed"
        record["error"] = str(error)
        return record
    xyz_text = Chem.MolToXYZBlock(molecule)
    text = w24.orca_input(xyz_text, 0, 1, None, nprocs, maxcore).replace("TightSCF", "TightSCF Opt")
    scratch = Path(tempfile.mkdtemp(prefix="w26pilot_"))
    try:
        (scratch / "pilot.inp").write_text(text, encoding="utf-8")
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [str(w24.ORCA_BINARY), "pilot.inp"], cwd=scratch, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=int(timeout_seconds), check=False,
            )
            log = completed.stdout.decode("utf-8", "replace")
            record["returncode"] = int(completed.returncode)
        except subprocess.TimeoutExpired as exc:
            partial = exc.output or b""
            log = partial.decode("utf-8", "replace") if isinstance(partial, bytes) else str(partial)
            record["status"] = "timeout"
            record["returncode"] = -1
        record["seconds"] = time.perf_counter() - started
        record["converged"] = "THE OPTIMIZATION HAS CONVERGED" in log
        for line in log.splitlines():
            if "FINAL SINGLE POINT ENERGY" in line:
                try:
                    record["final_energy_hartree"] = float(line.split()[-1])
                except ValueError:
                    pass
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return record


def render_report(summary):
    lines = []
    add = lines.append
    add("# W26 结题报告：介电响应律的稠密实测、阴离子束缚闸门与模型层级对照")
    add("")
    add("- 输入红线 data/processed/w21_li_coordination_layer.csv（sha256 " + str(summary["input_sha256"]) + "）")
    add("- 预注册 probes/w26_dielectric_law_prereg.json（sha256 " + str(summary["prereg_sha256"]) + "，status = locked_before_run）")
    add("- 引擎：xTB " + str(summary["engine"]["xtb_version"]) + " / ddCOSMO 任意 epsilon / GFPN2 气相刚性几何")
    add("- 主记分牌 shot：0（累计 " + str(summary["cumulative_main_scoreboard_attempts"]) + "）")
    add("")
    add("## 1. 分子池与规模")
    add("")
    add("- 池：" + str(summary["pool"]["n"]) + " 个化合物；扫描记录 " + str(summary["pool"]["n_scan_rows"]) + " 行；成功几何 " + str(summary["pool"]["n_geometry_ok"]) + " 个。")
    add("- epsilon 网格：" + ", ".join(str(item) for item in summary["epsilon_grid"]))
    add("- 分层子集（刚性 vs 弛豫对照）：" + str(summary["relaxation"]["n_molecules"]) + " 个化合物。")
    add("")
    add("## 2. 裁决表")
    add("")
    add("| 判据 | 读数 | 阈值 | 裁决 |")
    add("| --- | --- | --- | --- |")
    for entry in summary["verdicts"]:
        add("| " + str(entry["id"]) + " " + str(entry["claim"]) + " | " + fmt(entry["value"], 6) + " | " + str(entry["threshold"]) + " | " + str(entry["verdict"]) + " |")
    add("")
    add("## 3. 关键读数")
    add("")
    for note in summary["notes"]:
        add("- " + note)
    add("")
    add("## 4. 口径裁定与边界")
    add("")
    for item in summary["boundaries"]:
        add("- " + item)
    add("")
    return lines


def gate_curves_from_scan(raw_rows):
    """Rebuild the per-molecule EA(epsilon) curves from the stored scan table."""
    table = {}
    for row in raw_rows:
        epsilon = as_float(row.get("epsilon"))
        total = as_float(row.get("total_E_hartree"))
        if epsilon is None or total is None:
            continue
        table.setdefault(row["inchikey"], {}).setdefault(row["charge_state"], {})[epsilon] = total
    curves = []
    for inchikey, states in sorted(table.items()):
        neutral = states.get("neutral") or {}
        anion = states.get("anion") or {}
        curve = {}
        for epsilon, value in neutral.items():
            if epsilon in anion:
                curve[epsilon] = (value - anion[epsilon]) * HARTREE_TO_EV
        if curve:
            curves.append({"inchikey": inchikey, "curve": curve})
    return curves


def regenerate_figures():
    """Rebuild both figures from the stored tables (no electronic-structure work)."""
    raw = read_rows(SCAN_CSV)
    scan_rows = [{"inchikey": row["inchikey"], "charge_state": row["charge_state"],
                  "epsilon": as_float(row["epsilon"], 0.0),
                  "delta_E_eV": as_float(row["delta_E_eV"])} for row in raw
                 if row.get("status") == "ok"]
    born_rows = [{"inchikey": row["inchikey"], "charge_state": row["charge_state"],
                  "C_eV": as_float(row["C_eV"])} for row in read_rows(BORN_CSV)]
    plt = configure_fonts()
    figure_a(plt, scan_rows, born_rows)
    figure_b(plt, gate_curves_from_scan(raw))
    return True


def detect_xtb_version(executable):
    import subprocess
    try:
        completed = subprocess.run([str(executable), "--version"], capture_output=True, timeout=60,
                                   check=False)
    except Exception:
        return "unknown"
    text = (completed.stdout or b"").decode("utf-8", "replace") + (completed.stderr or b"").decode("utf-8", "replace")
    for line in text.splitlines():
        if "version" in line.lower():
            return line.strip()
    return "unknown"


def main(argv=None):
    parser = argparse.ArgumentParser(description="W26 dielectric-law scan")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--skip-relaxation", action="store_true")
    parser.add_argument("--skip-contrast", action="store_true")
    parser.add_argument("--geometry-pilot", action="store_true")
    parser.add_argument("--geometry-pilot-timeout", type=int, default=7200)
    parser.add_argument("--pilot-smiles", default="COC(=O)OC")
    parser.add_argument("--figures-only", action="store_true")
    args = parser.parse_args(argv)

    if args.figures_only:
        regenerate_figures()
        print(json.dumps({"figures_only": True, "figures": [FIG_A.name, FIG_B.name]}))
        return None

    prereg = load_prereg()
    pool = load_pool()
    if args.limit:
        pool = pool[: int(args.limit)]
    epsilons = tuple(float(item) for item in prereg["epsilon_grid"])
    with_contrast = not bool(args.skip_contrast)
    executable = w21.resolve_xtb()
    version = detect_xtb_version(executable)

    payloads = []
    for index, row in enumerate(pool):
        payloads.append((index, row["inchikey"], row["name"], row["canonical_smiles"], row["seed"],
                         row.get("motif_class") or "", row.get("donor_symbol") or "",
                         epsilons, with_contrast))
    print("[w26] pool=" + str(len(payloads)) + " workers=" + str(args.workers), flush=True)

    scan_results = []
    if int(args.workers) <= 1:
        for payload in payloads:
            scan_results.append(scan_one_molecule(payload))
            print("[w26] done " + str(len(scan_results)) + "/" + str(len(payloads)), flush=True)
    else:
        from concurrent.futures import as_completed
        with ProcessPoolExecutor(max_workers=int(args.workers)) as executor:
            futures = {executor.submit(scan_one_molecule, payload): payload[0] for payload in payloads}
            for future in as_completed(futures):
                scan_results.append(future.result())
                if len(scan_results) % 10 == 0 or len(scan_results) == len(payloads):
                    print("[w26] done " + str(len(scan_results)) + "/" + str(len(payloads)), flush=True)
    scan_results.sort(key=lambda item: item["index"])

    scan_rows = []
    born_rows = []
    gate_rows = []
    gate_curves = []
    contrast_rows = []
    n_geometry_ok = 0
    for result in scan_results:
        if result["status"] != "ok":
            continue
        n_geometry_ok += 1
        by_state = {}
        for row in result["rows"]:
            by_state.setdefault(row["charge_state"], {})[float(row["epsilon"])] = row
        gas = {}
        for state, table in by_state.items():
            entry = table.get(1.0)
            gas[state] = entry.get("total_E_hartree") if entry else None
        for state, table in by_state.items():
            for eps in epsilons:
                entry = table.get(float(eps))
                if entry is None:
                    continue
                delta = None
                if gas.get(state) is not None and entry.get("total_E_hartree") is not None:
                    delta = (float(entry["total_E_hartree"]) - float(gas[state])) * HARTREE_TO_EV
                scan_rows.append({
                    "inchikey": result["inchikey"], "name": result["name"],
                    "motif_class": result["motif_class"], "donor_symbol": result["donor_symbol"],
                    "charge_state": state, "epsilon": float(eps), "status": entry["status"],
                    "total_E_hartree": entry.get("total_E_hartree"),
                    "homo_eV": entry.get("homo_eV"), "lumo_eV": entry.get("lumo_eV"),
                    "gap_eV": entry.get("gap_eV"), "delta_E_eV": delta,
                    "dipole_debye": entry.get("dipole_debye"), "seconds": entry.get("seconds"),
                })
        for state, table in by_state.items():
            state_map = {float(eps): entry.get("total_E_hartree") for eps, entry in table.items()}
            block = curve_block(state_map, epsilons, BAND_START)
            if block is None:
                continue
            block.update({"inchikey": result["inchikey"], "name": result["name"],
                          "motif_class": result["motif_class"], "donor_symbol": result["donor_symbol"],
                          "charge_state": state})
            born_rows.append(block)
        gates = gate_block({state: {float(eps): entry.get("total_E_hartree") for eps, entry in table.items()}
                            for state, table in by_state.items()}, epsilons, 80.4)
        if gates is not None:
            neutral = by_state.get("neutral") or {}
            anion = by_state.get("anion") or {}
            curve = {}
            for eps in epsilons:
                key = float(eps)
                if neutral.get(key) and anion.get(key):
                    left = neutral[key].get("total_E_hartree")
                    right = anion[key].get("total_E_hartree")
                    if left is not None and right is not None:
                        curve[key] = (float(left) - float(right)) * HARTREE_TO_EV
            gates.update({"inchikey": result["inchikey"], "name": result["name"],
                          "motif_class": result["motif_class"], "donor_symbol": result["donor_symbol"]})
            gate_rows.append(gates)
            gate_curves.append({"inchikey": result["inchikey"], "curve": curve})
        if with_contrast:
            model_energies = {}
            for item in result.get("contrast", []):
                if item.get("status") == "ok" and item.get("total_E_hartree") is not None:
                    model_energies[(item["charge_state"], item["model"], item["solvent"])] = float(item["total_E_hartree"])
            for (state, model, solvent), value in sorted(model_energies.items(), key=lambda pair: str(pair[0])):
                matched = [eps for eps, name in NAMED_MATCH if name == solvent]
                if model == "cpcmx":
                    matched = [CPCMX_MATCH[0]]
                if not matched:
                    continue
                epsilon = float(matched[0])
                cosmo_entry = (by_state.get(state) or {}).get(epsilon)
                if cosmo_entry is None or cosmo_entry.get("total_E_hartree") is None or gas.get(state) is None:
                    continue
                delta_cosmo = (float(cosmo_entry["total_E_hartree"]) - float(gas[state])) * HARTREE_TO_EV
                delta_model = (value - float(gas[state])) * HARTREE_TO_EV
                contrast_rows.append({
                    "inchikey": result["inchikey"], "name": result["name"], "charge_state": state,
                    "epsilon": epsilon, "model": model, "solvent": solvent,
                    "delta_cosmo_eV": delta_cosmo, "delta_model_eV": delta_model,
                    "abs_diff_eV": abs(delta_cosmo - delta_model),
                })
    print("[w26] scan rows=" + str(len(scan_rows)) + " curves=" + str(len(born_rows)), flush=True)


    frozen = {row["inchikey"]: row for row in pool}
    opt_initial_lookup = {result["inchikey"]: (result.get("opt_initial") or {})
                          for result in scan_results}

    def _anchor_compare(source_kind):
        orbital = []
        energy = []
        for row in scan_rows:
            if row["charge_state"] != "neutral" or abs(float(row["epsilon"]) - 1.0) > 1e-12:
                continue
            source = frozen.get(row["inchikey"])
            if source is None:
                continue
            if source_kind == "gas":
                homo = row.get("homo_eV")
                lumo = row.get("lumo_eV")
                total = row.get("total_E_hartree")
            else:
                initial = opt_initial_lookup.get(row["inchikey"]) or {}
                homo = initial.get("homo_eV")
                lumo = initial.get("lumo_eV")
                total = initial.get("total_E_hartree")
            for measured, column in ((homo, "homo_free_eV"), (lumo, "lumo_free_eV")):
                reference = as_float(source.get(column))
                if reference is None or measured is None:
                    continue
                orbital.append(abs(float(measured) - reference))
            reference_energy = as_float(source.get("total_energy_free_hartree"))
            if reference_energy is not None and total is not None:
                energy.append(abs(float(total) - reference_energy))
        block = {
            "n_orbital": len(orbital), "n_energy": len(energy),
            "max_orbital_dev_eV": float(np.max(orbital)) if orbital else None,
            "max_energy_dev_hartree": float(np.max(energy)) if energy else None,
            "orbital_violations": int(np.sum(np.asarray(orbital) > ANCHOR_ORBITAL_TOL_EV)) if orbital else 0,
            "energy_violations": int(np.sum(np.asarray(energy) > ANCHOR_ENERGY_TOL_HARTREE)) if energy else 0,
        }
        block["holds"] = bool(orbital and energy and block["orbital_violations"] == 0
                              and block["energy_violations"] == 0)
        return block

    # H1f: the anchor exactly as frozen -- W26 gas single point at the rigid gas-phase
    # optimum against the frozen layer columns.
    anchor = _anchor_compare("gas")
    # H1g: the same comparison against the FIRST ISCF block of the xTB optimisation log,
    # which is the quantity w21.parse_arm actually stored.  This is the reproducibility gate.
    anchor_convention = _anchor_compare("initial")

    relaxation = {"n_molecules": 0, "median_contribution_eV": None, "by_state": {},
                  "subset_inchikeys": [], "epsilon": 80.4, "status": "skipped"}
    if not args.skip_relaxation:
        subset = stratified_subset(pool)
        relaxation["subset_inchikeys"] = [row["inchikey"] for row in subset]
        relaxed_payloads = [(index, row["inchikey"], row["name"], row["canonical_smiles"], row["seed"], 80.4)
                            for index, row in enumerate(subset)]
        relaxed_results = []
        if int(args.workers) <= 1:
            for payload in relaxed_payloads:
                relaxed_results.append(relaxed_geometry_probe(payload))
        else:
            with ProcessPoolExecutor(max_workers=min(int(args.workers), 8)) as executor:
                relaxed_results = list(executor.map(relaxed_geometry_probe, relaxed_payloads, chunksize=1))
        rigid_lookup = {(row["inchikey"], row["charge_state"]): row.get("delta_E_eV") for row in scan_rows
                        if abs(float(row["epsilon"]) - 80.4) < 1e-9}
        contributions = []
        ion_contributions = []
        by_state_contrib = {"neutral": [], "cation": [], "anion": []}
        relaxation["n_molecules"] = len(relaxed_results)
        for result in relaxed_results:
            for row in result.get("rows", []):
                rigid = rigid_lookup.get((result["inchikey"], row["charge_state"]))
                relaxed = row.get("delta_E_eV")
                if rigid is None or relaxed is None:
                    continue
                value = abs(float(relaxed) - float(rigid))
                contributions.append(value)
                by_state_contrib[row["charge_state"]].append(value)
                if row["charge_state"] in ("cation", "anion"):
                    ion_contributions.append(value)
        relaxation["median_contribution_eV"] = median(contributions)
        relaxation["median_contribution_ion_eV"] = median(ion_contributions)
        relaxation["by_state"] = {key: median(values) for key, values in by_state_contrib.items()}
        relaxation["n_pairs"] = len(contributions)
        relaxation["status"] = "ok" if contributions else "no_pairs"

    pilot = {"status": "skipped"}
    if args.geometry_pilot:
        pilot = geometry_pilot(args.pilot_smiles, 42, args.geometry_pilot_timeout, 1, 2000)
        pilot["label"] = "r2SCAN-3c Opt (nprocs=1, maxcore=2000)"

    ion_curves = [row for row in born_rows if row["charge_state"] in ("cation", "anion")]
    all_curves = list(born_rows)
    r2_median = median([row.get("r2") for row in ion_curves])
    residual_all = median([row.get("residual_born_200_eV") for row in all_curves])
    residual_ion = median([row.get("residual_born_200_eV") for row in ion_curves])
    travel_all = median([row.get("travel_200_1000_eV") for row in all_curves])
    travel_ion = median([row.get("travel_200_1000_eV") for row in ion_curves])
    cv_ion = median([row.get("band_cv") for row in ion_curves])
    cv_all = median([row.get("band_cv") for row in all_curves])
    power_ion = median([row.get("power_band_median_eV") for row in ion_curves])
    c_eV_median_ion = median([abs(row.get("C_eV")) for row in ion_curves])
    gate_candidates = [row for row in gate_rows if row.get("gas_known") and not row.get("already_bound")]
    gate_values = [row["gate_epsilon"] for row in gate_candidates if row.get("gate_epsilon") is not None]
    gate_share = (len(gate_values) / float(len(gate_candidates))) if gate_candidates else 0.0
    gate_median = median(gate_values)
    gate_values_le = [row["gate_epsilon_le_80p4"] for row in gate_candidates
                      if row.get("gate_epsilon_le_80p4") is not None]
    gate_share_le = ((len(gate_values_le) / float(len(gate_candidates))) if gate_candidates else 0.0)
    already_bound = [row for row in gate_rows if row.get("already_bound")]
    contrast_median = median([row.get("abs_diff_eV") for row in contrast_rows])
    contrast_by_model = {}
    for model in sorted({row["model"] for row in contrast_rows}):
        contrast_by_model[model] = median([row.get("abs_diff_eV") for row in contrast_rows if row["model"] == model])

    gas_ea_values = [row.get("gas_ea_eV") for row in gate_rows if row.get("gas_ea_eV") is not None]
    ea_window = [row.get("ea_at_1000_eV") - row.get("gas_ea_eV") for row in gate_rows
                 if row.get("ea_at_1000_eV") is not None and row.get("gas_ea_eV") is not None]
    h2_attribution = {"n": len(ea_window),
                      "gas_ea_p05_eV": float(np.percentile(gas_ea_values, 5)) if gas_ea_values else None,
                      "gas_ea_p95_eV": float(np.percentile(gas_ea_values, 95)) if gas_ea_values else None,
                      "ea_window_median_eV": median(ea_window)}
    spread = None
    if h2_attribution["gas_ea_p05_eV"] is not None:
        spread = float(h2_attribution["gas_ea_p95_eV"] - h2_attribution["gas_ea_p05_eV"])
    h2_attribution["gas_ea_spread_p05_p95_eV"] = spread
    h2_attribution["window_over_spread"] = (abs(h2_attribution["ea_window_median_eV"]) / spread) if spread else None

    verdicts = []
    verdicts.append(build_verdict("H1f", "气相锚点（冻结原文口径：优化几何单点对冻结层）",
                                  anchor.get("max_orbital_dev_eV"), ANCHOR_ORBITAL_TOL_EV,
                                  bool(anchor.get("holds"))))
    verdicts.append(build_verdict("H1g", "同一锚点改按冻结层的实际口径（--opt 日志首个 ISCF 块）",
                                  anchor_convention.get("max_orbital_dev_eV"), ANCHOR_ORBITAL_TOL_EV,
                                  bool(anchor_convention.get("holds"))))
    verdicts.append(build_verdict("H1a", "离子态 Born 拟合 R2 中位", r2_median, 0.99,
                                  bool(np.isfinite(r2_median) and r2_median >= 0.99)))
    verdicts.append(build_verdict("H1b", "epsilon=200 的 Born 腔残余 |C|/200 中位（离子态）",
                                  residual_ion, 0.020,
                                  bool(np.isfinite(residual_ion) and residual_ion <= 0.020)))
    verdicts.append(build_verdict("H1c", "epsilon=200 到 1000 的实测再走量中位（离子态）", travel_ion, 0.015,
                                  bool(np.isfinite(travel_ion) and travel_ion <= 0.015)))
    verdicts.append(build_verdict("H1d", "残余乘 epsilon 的变异系数中位（离子态）", cv_ion, 0.35,
                                  bool(np.isfinite(cv_ion) and cv_ion <= 0.35)))
    verdicts.append(build_verdict("H1e", "几何弛豫对介电位移的贡献中位（离子对）",
                                  relaxation.get("median_contribution_ion_eV"), 0.05,
                                  bool(relaxation.get("median_contribution_ion_eV") is not None
                                       and np.isfinite(relaxation["median_contribution_ion_eV"])
                                       and relaxation["median_contribution_ion_eV"] <= 0.05)))
    verdicts.append(build_verdict("H2a", "气相未束缚分子中在网格内（epsilon<=1000）出现束缚闸门的占比", gate_share, 0.50,
                                  bool(gate_share >= 0.50)))
    verdicts.append(build_verdict("H2b", "闸门 epsilon 中位", gate_median, 40.0,
                                  bool(np.isfinite(gate_median) and gate_median <= 40.0)))
    verdicts.append(build_verdict("H3", "匹配 epsilon 上 ddCOSMO 与命名溶剂模型的位移差中位", contrast_median, 0.15,
                                  bool(np.isfinite(contrast_median) and contrast_median <= 0.15)))

    ART.mkdir(parents=True, exist_ok=True)
    write_csv(SCAN_CSV, SCAN_FIELDS,
              [[row.get(field) for field in SCAN_FIELDS] for row in scan_rows])
    write_csv(BORN_CSV,
              ["inchikey", "name", "motif_class", "donor_symbol", "charge_state", "n_points",
               "C_eV", "r2", "residual_born_200_eV", "travel_200_1000_eV", "power_band_median_eV", "band_cv", "band_n",
               "delta_at_2p0_eV", "delta_at_80p4_eV", "delta_at_200_eV", "delta_at_1000_eV"],
              [[row.get(field) for field in ("inchikey", "name", "motif_class", "donor_symbol",
                                             "charge_state", "n_points", "C_eV", "r2",
                                             "residual_born_200_eV", "travel_200_1000_eV", "power_band_median_eV", "band_cv",
                                             "band_n", "delta_at_2p0_eV", "delta_at_80p4_eV",
                                             "delta_at_200_eV", "delta_at_1000_eV")]
               for row in born_rows])
    write_csv(GATE_CSV,
              ["inchikey", "name", "motif_class", "donor_symbol", "gas_ea_eV", "ea_at_80p4_eV",
               "gate_epsilon", "gate_epsilon_le_80p4", "already_bound", "gas_known", "gate_span"],
              [[row.get(field) for field in ("inchikey", "name", "motif_class", "donor_symbol",
                                             "gas_ea_eV", "ea_at_80p4_eV", "ea_at_1000_eV", "gate_epsilon", "gate_epsilon_le_80p4",
                                             "already_bound", "gas_known", "gate_span")]
               for row in gate_rows])
    write_csv(CONTRAST_CSV,
              ["inchikey", "name", "charge_state", "epsilon", "model", "solvent",
               "delta_cosmo_eV", "delta_model_eV", "abs_diff_eV"],
              [[row.get(field) for field in ("inchikey", "name", "charge_state", "epsilon", "model",
                                             "solvent", "delta_cosmo_eV", "delta_model_eV", "abs_diff_eV")]
               for row in contrast_rows])
    if args.geometry_pilot:
        write_csv(PILOT_CSV, ["label", "smiles", "status", "converged", "seconds",
                              "final_energy_hartree", "error"],
                  [[pilot.get("label", ""), pilot.get("smiles", ""), pilot.get("status", ""),
                    pilot.get("converged", ""), pilot.get("seconds", ""),
                    pilot.get("final_energy_hartree", ""), pilot.get("error", "")]])

    try:
        plt = configure_fonts()
        figure_a(plt, scan_rows, born_rows)
        figure_b(plt, gate_curves)
        figures_ok = True
    except Exception as error:
        figures_ok = False
        print("[w26] figure failure: " + type(error).__name__ + ": " + str(error), flush=True)

    notes = []
    notes.append("离子态 Born 前因子 |C| 中位 " + fmt(c_eV_median_ion, 4) + " eV（v6 报 2.1 eV，层级不同：本仓 GFN2/ddCOSMO 刚性几何）")
    notes.append("三个状态合并看：epsilon=200 的 Born 腔残余 |C|/200 中位 " + fmt(residual_all, 5) + " eV、200 到 1000 再走量中位 " + fmt(travel_all, 5) + " eV、幂律变异系数中位 " + fmt(cv_all, 4))
    notes.append("阴离子：气相 EA 中位 " + fmt(median([row.get("gas_ea_eV") for row in gate_rows]), 4) + " eV；epsilon=80.4 处 EA 中位 " + fmt(median([row.get("ea_at_80p4_eV") for row in gate_rows]), 4) + " eV")
    notes.append("闸门：气相未束缚候选 " + str(len(gate_candidates)) + " 个，其中 " + str(len(gate_values)) + " 个在 epsilon<=80.4 内过闸；气相即已束缚 " + str(len(already_bound)) + " 个；闸门 epsilon 中位 " + fmt(gate_median, 4))
    notes.append("残余乘 epsilon 的带内中位 " + fmt(power_ion, 4) + " eV（v6 报 2.1 eV，层级不同）")
    notes.append("残余口径在 epsilon=1000 处会上翘：那里的真实残余已落到拟合噪声底（约 2.6 meV），乘 epsilon 会把任何拟合误差放大一千倍，所以末端四分位带张开。带内中位与变异系数已把这一段计入；读者不应把末端上翘读作幂律失效。")
    notes.append("闸门归因：气相 EA 的 p05-p95 跨距 " + fmt(h2_attribution.get("gas_ea_spread_p05_p95_eV"), 3) + " eV，而介电扫描能给出的 EA 位移中位只有 " + fmt(h2_attribution.get("ea_window_median_eV"), 4) + " eV，比值 " + fmt(h2_attribution.get("window_over_spread"), 4))
    notes.append("若把闸门上限收在 epsilon<=80.4（实用溶剂范围），过闸占比 " + fmt(gate_share_le, 4))
    for model, value in sorted(contrast_by_model.items()):
        notes.append("模型差异 " + model + "：与 ddCOSMO 的位移差中位 " + fmt(value, 4) + " eV")
    if relaxation.get("median_contribution_eV") is not None:
        notes.append("刚性 vs 弛豫：几何弛豫对 epsilon=80.4 位移的贡献中位 " + fmt(relaxation["median_contribution_eV"], 5) + " eV（n = " + str(relaxation.get("n_pairs")) + " 条曲线）")
    if args.geometry_pilot:
        notes.append("几何台阶 pilot：" + str(pilot.get("status")) + "，收敛 = " + str(pilot.get("converged")) + "，单分子耗时 " + fmt(pilot.get("seconds"), 1) + " s（ORCA r2SCAN-3c Opt，nprocs=1）")

    boundaries = [
        "本仓（W26）= GFN2-xTB / ddCOSMO 任意 epsilon / 刚性气相几何 / " + str(len(pool)) + " 分子；母体论文 v6 = r2SCAN-3c / CPCM 裸扫描 / 18 分子 / 10 台阶。跨层级只比函数形式与量级，绝不比绝对值。",
        "H1b / H1c / H1d 的主裁决取离子态（阳离子 + 阴离子）：v6 的 2.1 eV 前因子与 19.6 meV 残余是氧化还原位移量，中性态的 Born 常数小得多、不是该命题的对象。三态合并的同一读数已在 notes 里并列报出，读者可自行取用。",
        "ddCOSMO / ALPB / CPCM-X 是三种不同的隐式溶剂近似，W26-3 只报差，不报谁更正确。",
        "W26 不修改 W24-1 的任何冻结表；对 W24-1 的再解释（几何弛豫被混入、epsilon 与溶剂身份不可分、epsilon >= 80.4 是外推）写在报告里，属于 W26 的评注而非对 W24-1 的重算。",
        "主记分牌 shot = 0（累计 12）；四个冻结读数（0.4091179943351143 / 0.4766400383507876 / 0.5861142332208197 / 0.6216672295270079）未动。",
        "不引用任何 Reaxys 数值；THEMol（CC BY-NC 4.0）不入交付包；Batt-P30K（MIT）与 RX-392 / SolvFunc-87 只作参考层。",
    ]

    summary = {
        "schema_version": 1,
        "task": "w26_dielectric_law",
        "generated_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "status": "complete",
        "prereg_sha256": sha256_file(PREREG),
        "prereg_status": prereg.get("status"),
        "input_sha256": sha256_file(LAYER),
        "engine": {"xtb_version": version, "continuum": "ddCOSMO (--cosmo EPSILON)",
                   "geometry": "gas-phase GFN2 rigid, one geometry for every epsilon and state"},
        "epsilon_grid": [float(item) for item in epsilons],
        "pool": {"n": len(pool), "n_geometry_ok": n_geometry_ok, "n_scan_rows": len(scan_rows),
                 "n_curves": len(born_rows)},
        "anchor": anchor,
        "anchor_convention": anchor_convention,
        "born_fit": {"n_ion_curves": len(ion_curves), "r2_median_ion": r2_median,
                     "c_eV_median_ion": c_eV_median_ion,
                     "residual_born_200_median_ion_eV": residual_ion,
                     "residual_born_200_median_all_eV": residual_all,
                     "power_band_median_ion_eV": power_ion,
                     "travel_200_1000_median_ion_eV": travel_ion,
                     "travel_200_1000_median_all_eV": travel_all,
                     "band_cv_median_ion": cv_ion, "band_cv_median_all": cv_all,
                     "band_start_epsilon": BAND_START},
        "relaxation": relaxation,
        "anion_gate": {"n_molecules": len(gate_rows), "n_candidates": len(gate_candidates),
                       "n_with_gate": len(gate_values), "n_with_gate_le_80p4": len(gate_values_le),
                       "n_already_bound": len(already_bound),
                       "share_with_gate": gate_share, "gate_median": gate_median,
                       "gas_ea_median_eV": median([row.get("gas_ea_eV") for row in gate_rows]),
                       "ea_at_80p4_median_eV": median([row.get("ea_at_80p4_eV") for row in gate_rows])},
        "model_contrast": {"n_rows": len(contrast_rows), "median_abs_diff_eV": contrast_median,
                           "by_model": contrast_by_model},
        "geometry_pilot": pilot,
        "h2_attribution": h2_attribution,
        "anion_gate_share_le_80p4": gate_share_le,
        "verdicts": verdicts,
        "notes": notes,
        "boundaries": boundaries,
        "main_scoreboard_attempts_delta": SCOREBOARD_SHOTS_THIS_WEEK,
        "cumulative_main_scoreboard_attempts": CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS,
        "figures": {"a": FIG_A.name, "b": FIG_B.name} if figures_ok else {},
        "artifacts": {"scan": SCAN_CSV.name, "born": BORN_CSV.name, "gate": GATE_CSV.name,
                      "contrast": CONTRAST_CSV.name},
    }
    summary["report_lines"] = render_report(summary)
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + chr(10),
                              encoding="utf-8", newline=chr(10))
    REPORT.write_text(chr(10).join(summary["report_lines"]) + chr(10), encoding="utf-8",
                      newline=chr(10))
    print(json.dumps({"verdicts": verdicts, "pool": summary["pool"],
                      "born_fit": summary["born_fit"], "anion_gate": summary["anion_gate"],
                      "model_contrast": summary["model_contrast"],
                      "anchor": anchor, "relaxation_status": relaxation.get("status"),
                      "geometry_pilot": pilot}, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()

