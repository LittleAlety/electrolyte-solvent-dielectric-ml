"""W23-2 -- Axis A P_1 first instantiation: GFN2-xTB dSCF ionisation energies and
electron affinities in the gas phase and under the same three-rung ALPB ladder
used by W23-1.

Why this arm exists
-------------------
Section 3 Axis A of the frozen framework lists P_1 ("gas-phase redox
thermodynamics") and the repository has never computed it: every IP/EA in the
four-core registry comes from an external reference layer.  P_1 is also the
carrier of the second half of the project's core data -- the oxidation/reduction
axis -- and it is the only axis where the semi-empirical level gives an
*absolute* quantity that can be compared with a published reference layer.

Two properties make this arm interesting rather than routine:

* gas-phase dSCF IP at GFN2 is strongly biased (methanol comes out at +
  15.5 eV against an experimental 10.8 eV), so the honest question is whether
  the *ordering* survives even though the magnitude does not;
* a gas-phase anion usually is not a bound state at all, and the sign of its
  highest occupied orbital is the signature of that.  The Week 22 review matrix
  registered (item A5) that "reduction-axis conclusions may only be carried by a
  layer that has a continuum" -- this arm tests that claim instead of asserting
  it.

Discipline
----------
No frozen reading moves, no main-scoreboard shot is taken, no Reaxys number is
used, and the reference layers (RX-392, Batt-P30K) are only ever compared
against -- never folded into a pool or a label.  The frozen closed-shell
argument builder is untouched: the open-shell states go through the sibling
function electrolyte_ml.xtb_runner.xtb_open_shell_arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _extra in (ROOT / "probes", ROOT / "src"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import w21_li_coordination as w21
from electrolyte_ml.xtb_runner import (
    run_xtb_subprocess,
    xtb_open_shell_arguments,
    xtb_optimisation_arguments,
)

PREREG = ROOT / "probes" / "w23_redox_dscf_prereg.json"
SUMMARY = ROOT / "probes" / "w23_redox_dscf_summary.json"
LAYER_CSV = ROOT / "data" / "processed" / "w23_redox_dscf_layer.csv"
MEDIUM_LAYER = ROOT / "data" / "processed" / "w23_orbital_medium_layer.csv"
REDOX_REFERENCE = ROOT / "data" / "processed" / "redox_merged.csv"
DELTA_CSV = ROOT / "probes" / "artifacts" / "w23_redox_dscf_delta_stats.csv"
MONO_CSV = ROOT / "probes" / "artifacts" / "w23_redox_dscf_monotonicity.csv"
KOOPMANS_CSV = ROOT / "probes" / "artifacts" / "w23_redox_dscf_koopmans.csv"
ANION_CSV = ROOT / "probes" / "artifacts" / "w23_redox_dscf_anion_bound_signature.csv"
RANK_CSV = ROOT / "probes" / "artifacts" / "w23_redox_dscf_rank_pairs.csv"
TOPK_CSV = ROOT / "probes" / "artifacts" / "w23_redox_dscf_topk.csv"
REFERENCE_CSV = ROOT / "probes" / "artifacts" / "w23_redox_dscf_reference_step.csv"
ANCHOR_CSV = ROOT / "probes" / "artifacts" / "w23_redox_dscf_neutral_anchor.csv"
RETRY_CSV = ROOT / "probes" / "artifacts" / "w23_redox_dscf_scf_retry_posthoc.csv"
QC_CSV = ROOT / "probes" / "artifacts" / "w23_redox_dscf_qc.csv"
REPORT = ROOT / "reports" / "w23_redox_dscf.md"

HARTREE_TO_EV = 27.211386245988
MEDIA = (
    ("gas", None, 1.0),
    ("thf", "thf", 7.58),
    ("benzaldehyde", "benzaldehyde", 18.0),
    ("water", "water", 80.4),
)
SOLVENT_MEDIA = tuple(item[0] for item in MEDIA if item[1])
STATES = (("neutral", 0, 0), ("cation", 1, 1), ("anion", -1, 1))
ARM_KEYS = tuple(medium + "_" + state for medium, _s, _e in MEDIA for state, _d, _u in STATES)
H1_THRESHOLD = 0.90
H2_THRESHOLD = 0.80
H3_THRESHOLD = 0.60
H4_GAS_THRESHOLD = 0.50
H4_GAP_THRESHOLD = 0.20
H5_OFFSET_EV = 1.0
H5_RHO = 0.60
H6_TOLERANCE_EV = 1e-6
UNBOUND_HOMO_SIGNATURE_EV = 0.0


def layer_fields():
    fields = [
        "inchikey", "name", "canonical_smiles", "row_index", "seed", "formal_charge",
        "charge_class",
    ]
    for arm in ARM_KEYS:
        fields += [arm + "_homo_eV", arm + "_lumo_eV", arm + "_gap_eV",
                   arm + "_total_E_hartree", arm + "_status"]
    for medium, _s, _e in MEDIA:
        fields += ["ip_" + medium + "_eV", "ea_" + medium + "_eV",
                   "ip_koopmans_offset_" + medium + "_eV",
                   "anion_unbound_" + medium]
    # The shift is only defined against the gas rung, and nothing in this arm
    # takes a vertical ionisation energy, so there is deliberately no
    # relaxation column: an always-empty declared column would be a reading
    # without evidence.
    for medium in SOLVENT_MEDIA:
        fields += ["d_ip_" + medium + "_eV", "d_ea_" + medium + "_eV"]
    fields += ["neutral_anchor_max_abs_delta_eV", "xtb_version", "ff_status",
               "seconds_total", "error"]
    return tuple(fields)


LAYER_FIELDS = layer_fields()


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fmt(value, digits=12):
    if value is None or value == "":
        return ""
    return ("%." + str(digits) + "g") % float(value)


def as_float(value):
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def run_arm(executable, label, xyz_text, charge, unpaired, solvent, timeout_seconds):
    """The Week 21 scratch discipline, with the spin state made explicit."""

    name = label + ".xyz"
    if unpaired:
        arguments = xtb_open_shell_arguments(name, formal_charge=charge,
                                             unpaired_electrons=unpaired)
    else:
        arguments = xtb_optimisation_arguments(name, formal_charge=charge)
    if solvent:
        arguments = list(arguments) + ["--alpb", solvent]
    scratch = Path(tempfile.mkdtemp(prefix="w23rx_"))
    try:
        (scratch / name).write_text(xyz_text, encoding="utf-8")
        started = time.perf_counter()
        completed = run_xtb_subprocess(executable, arguments, cwd=scratch,
                                       timeout_seconds=timeout_seconds)
        elapsed = time.perf_counter() - started
        optimized = scratch / "xtbopt.xyz"
        charges = scratch / "charges"
        return {
            "returncode": int(completed.returncode),
            "stdout": completed.stdout.decode("utf-8", "replace"),
            "optimized_xyz": optimized.read_text(encoding="utf-8", errors="replace")
            if optimized.is_file() else None,
            "charges_text": charges.read_text(encoding="utf-8", errors="replace")
            if charges.is_file() else None,
            "sentinel": (scratch / ".xtboptok").is_file(),
            "seconds": elapsed,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def parse_arm(result):
    parsed = w21.parse_arm(result)
    payload = {
        "status": parsed.get("status"),
        "homo_eV": parsed.get("homo_eV"),
        "lumo_eV": parsed.get("lumo_eV"),
        "gap_eV": parsed.get("gap_eV"),
        "total_E_hartree": parsed.get("total_energy_hartree"),
        "xtb_version": parsed.get("xtb_version"),
        "error": parsed.get("error") or "",
        "seconds": float(result.get("seconds") or 0.0),
    }
    return payload


def run_compound(payload):
    index, name, smiles, executable, timeout_seconds = payload
    from rdkit import Chem

    record = {
        "row_index": index,
        "name": name,
        "canonical_smiles": smiles,
        "arms": {},
        "error": "",
        "ff_status": "",
        "formal_charge": "",
        "seconds_total": 0.0,
    }
    molecule, ff_status, error = w21.embed(smiles, 42 + index)
    if molecule is None:
        record["error"] = error or "embed_failed"
        return record
    record["ff_status"] = ff_status
    net_charge = int(Chem.GetFormalCharge(molecule))
    record["formal_charge"] = net_charge
    xyz_text = Chem.MolToXYZBlock(molecule)
    for medium, solvent, _epsilon in MEDIA:
        for state, delta_q, unpaired in STATES:
            arm_key = medium + "_" + state
            label = "c%03d_%s_%s" % (index, medium, state)
            try:
                result = run_arm(executable, label, xyz_text, net_charge + delta_q,
                                 unpaired, solvent, timeout_seconds)
                record["arms"][arm_key] = parse_arm(result)
            except Exception as exc:  # noqa: BLE001 - the message is the evidence
                record["arms"][arm_key] = {
                    "status": "exception", "homo_eV": None, "lumo_eV": None, "gap_eV": None,
                    "total_E_hartree": None, "xtb_version": None,
                    "error": str(exc)[:200], "seconds": 0.0,
                }
    record["seconds_total"] = float(
        sum((arm.get("seconds") or 0.0) for arm in record["arms"].values())
    )
    return record


# --------------------------------------------------------------------------- #
# layer assembly
# --------------------------------------------------------------------------- #

def build_layer_rows(records, meta_rows, medium_layer):
    rows = []
    for record in sorted(records, key=lambda item: item.get("row_index", 0)):
        row = {field: "" for field in LAYER_FIELDS}
        index = int(record.get("row_index", 0))
        meta = meta_rows[index] if index < len(meta_rows) else {}
        row["inchikey"] = str(meta.get("molecule_id") or meta.get("inchikey") or "")
        row["name"] = record.get("name") or meta.get("name") or ""
        row["canonical_smiles"] = record.get("canonical_smiles") or ""
        row["row_index"] = index
        row["seed"] = 42 + index
        row["formal_charge"] = record.get("formal_charge", "")
        net = record.get("formal_charge")
        row["charge_class"] = (
            "neutral" if net == 0 else ("charged" if isinstance(net, int) else "")
        )
        row["ff_status"] = record.get("ff_status", "")
        row["error"] = record.get("error") or ""
        row["seconds_total"] = fmt(record.get("seconds_total") or 0.0, 8)
        arms = record.get("arms") or {}
        version = ""
        for arm_key in ARM_KEYS:
            payload = arms.get(arm_key) or {
                "status": "not_computed", "homo_eV": None, "lumo_eV": None, "gap_eV": None,
                "total_E_hartree": None,
            }
            row[arm_key + "_homo_eV"] = fmt(payload.get("homo_eV"))
            row[arm_key + "_lumo_eV"] = fmt(payload.get("lumo_eV"))
            row[arm_key + "_gap_eV"] = fmt(payload.get("gap_eV"))
            row[arm_key + "_total_E_hartree"] = fmt(payload.get("total_E_hartree"))
            row[arm_key + "_status"] = payload.get("status") or "not_computed"
            if payload.get("xtb_version"):
                version = payload["xtb_version"]
            if payload.get("error"):
                row["error"] = (row["error"] + " | " + str(payload["error"]))[:300].strip(" |")
        row["xtb_version"] = version
        for medium, _solvent, _epsilon in MEDIA:
            neutral = arms.get(medium + "_neutral") or {}
            cation = arms.get(medium + "_cation") or {}
            anion = arms.get(medium + "_anion") or {}
            e_neutral = as_float(neutral.get("total_E_hartree"))
            e_cation = as_float(cation.get("total_E_hartree"))
            e_anion = as_float(anion.get("total_E_hartree"))
            if neutral.get("status") == "ok" and cation.get("status") == "ok" \
                    and e_neutral is not None and e_cation is not None:
                row["ip_" + medium + "_eV"] = fmt((e_cation - e_neutral) * HARTREE_TO_EV)
            if neutral.get("status") == "ok" and anion.get("status") == "ok" \
                    and e_neutral is not None and e_anion is not None:
                row["ea_" + medium + "_eV"] = fmt((e_neutral - e_anion) * HARTREE_TO_EV)
            anion_homo = as_float(anion.get("homo_eV"))
            if anion.get("status") == "ok" and anion_homo is not None:
                row["anion_unbound_" + medium] = "yes" if anion_homo > UNBOUND_HOMO_SIGNATURE_EV else "no"
            koopmans = as_float(neutral.get("homo_eV"))
            ip_value = as_float(row["ip_" + medium + "_eV"])
            if koopmans is not None and ip_value is not None:
                row["ip_koopmans_offset_" + medium + "_eV"] = fmt(ip_value - (-koopmans))
            if medium == "gas":
                continue
            delta_ip = None
            delta_ea = None
            ip_gas = as_float(row["ip_gas_eV"])
            ea_gas = as_float(row["ea_gas_eV"])
            ip_here = as_float(row["ip_" + medium + "_eV"])
            ea_here = as_float(row["ea_" + medium + "_eV"])
            if ip_gas is not None and ip_here is not None:
                delta_ip = ip_here - ip_gas
                row["d_ip_" + medium + "_eV"] = fmt(delta_ip)
            if ea_gas is not None and ea_here is not None:
                delta_ea = ea_here - ea_gas
                row["d_ea_" + medium + "_eV"] = fmt(delta_ea)
        previous = medium_layer.get(row["inchikey"])
        anchor = []
        if previous:
            for medium, _solvent, _epsilon in MEDIA:
                for key in ("homo", "lumo", "gap"):
                    own = as_float(row[medium + "_neutral_" + key + "_eV"])
                    reference = as_float(previous.get("free_" + medium + "_" + key + "_eV")) \
                        if medium != "gas" else as_float(previous.get("gas_free_" + key + "_eV"))
                    if own is not None and reference is not None:
                        anchor.append(abs(own - reference))
        row["neutral_anchor_max_abs_delta_eV"] = fmt(max(anchor)) if anchor else ""
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# readings
# --------------------------------------------------------------------------- #

def subset(layer_rows, channel, medium, charge_class="neutral"):
    """Rows where the channel is defined in the given medium for the charge class."""

    need = {
        "ip": (medium + "_neutral_status", medium + "_cation_status"),
        "ea": (medium + "_neutral_status", medium + "_anion_status"),
    }[channel]
    column = channel + "_" + medium + "_eV"
    keep = []
    for row in layer_rows:
        if charge_class is not None and row["charge_class"] != charge_class:
            continue
        if any(row.get(item) != "ok" for item in need):
            continue
        if as_float(row[column]) is None:
            continue
        keep.append(row)
    return keep


def channel_stats(rows, channel, medium):
    values = np.array([as_float(row[channel + "_" + medium + "_eV"]) for row in rows], dtype=float)
    return {
        "n": int(values.size),
        "mean_eV": float(np.mean(values)),
        "sd_eV": float(np.std(values, ddof=1)) if values.size > 1 else float("nan"),
        "min_eV": float(np.min(values)),
        "max_eV": float(np.max(values)),
    }


def displacement(rows, channel, medium):
    column = "d_" + channel + "_" + medium + "_eV"
    values = np.array([as_float(row[column]) for row in rows], dtype=float)
    return {
        "n": int(values.size),
        "mean_eV": float(np.mean(values)) if values.size else float("nan"),
        "sd_eV": float(np.std(values, ddof=1)) if values.size > 1 else float("nan"),
        "share_negative": float(np.mean(values < 0)) if values.size else float("nan"),
        "share_positive": float(np.mean(values > 0)) if values.size else float("nan"),
    }


def h1_h2(ip_rows, ea_rows=None):
    """H1 is read off the IP-complete rows, H2 off the EA-complete rows.

    The two sets differ: an anion SCF that does not converge leaves the EA
    channel undefined while the IP channel is intact, and the other way round,
    so the two channels must not share one row list.
    """

    ea_rows = ip_rows if ea_rows is None else ea_rows
    payload = {}
    for channel, rows, expect_negative, threshold in (
        ("ip", ip_rows, True, H1_THRESHOLD),
        ("ea", ea_rows, False, H2_THRESHOLD),
    ):
        for medium in SOLVENT_MEDIA:
            item = displacement(rows, channel, medium)
            share = item["share_negative"] if expect_negative else item["share_positive"]
            payload[channel + "_" + medium] = {
                **item,
                "share_in_predicted_direction": share,
                "threshold": threshold,
                "holds": bool(item["n"] and share >= threshold),
            }
    return payload


def h3_monotonicity(rows):
    from scipy import stats

    flags = []
    for row in rows:
        series = [as_float(row["d_ip_" + medium + "_eV"]) for medium in SOLVENT_MEDIA]
        if any(value is None for value in series):
            continue
        flags.append(abs(series[0]) < abs(series[1]) < abs(series[2]))
    usable = len(flags)
    count = int(sum(flags))
    share = (count / usable) if usable else float("nan")
    p_value = (float(stats.binomtest(count, usable, 0.5, alternative="greater").pvalue)
               if usable else float("nan"))
    return {
        "n": usable,
        "strictly_increasing_count": count,
        "share": share,
        "binom_p_greater": p_value,
        "threshold": H3_THRESHOLD,
        "holds": bool(usable and share >= H3_THRESHOLD),
    }


def anion_signature(layer_rows, charge_class="neutral"):
    payload = {}
    for medium, _solvent, _epsilon in MEDIA:
        accepted = 0
        unbound = 0
        for row in layer_rows:
            if charge_class is not None and row["charge_class"] != charge_class:
                continue
            flag = str(row.get("anion_unbound_" + medium, "")).strip()
            if not flag:
                continue
            accepted += 1
            unbound += 1 if flag == "yes" else 0
        share = (unbound / accepted) if accepted else float("nan")
        payload[medium] = {"n": accepted, "unbound": unbound, "share": share}
    gas = payload["gas"]["share"]
    water = payload["water"]["share"]
    holds = bool(
        payload["gas"]["share"] == payload["gas"]["share"]
        and gas >= H4_GAS_THRESHOLD
        and (gas - water) >= H4_GAP_THRESHOLD
    )
    return {
        "by_medium": payload,
        "gas_share": gas,
        "water_share": water,
        "gas_minus_water": (gas - water) if (gas == gas and water == water) else float("nan"),
        "thresholds": {"gas_share": H4_GAS_THRESHOLD, "gap": H4_GAP_THRESHOLD},
        "holds": holds,
    }


def koopmans(layer_rows, charge_class="neutral"):
    from scipy import stats

    payload = {}
    for medium, _solvent, _epsilon in MEDIA:
        ip_pairs = []
        ea_pairs = []
        for row in layer_rows:
            if charge_class is not None and row["charge_class"] != charge_class:
                continue
            neutral_homo = as_float(row[medium + "_neutral_homo_eV"])
            neutral_lumo = as_float(row[medium + "_neutral_lumo_eV"])
            ip_value = as_float(row["ip_" + medium + "_eV"])
            ea_value = as_float(row["ea_" + medium + "_eV"])
            if neutral_homo is not None and ip_value is not None:
                ip_pairs.append((ip_value, -neutral_homo))
            if neutral_lumo is not None and ea_value is not None:
                ea_pairs.append((ea_value, -neutral_lumo))
        entry = {}
        for label, pairs in (("ip_vs_koopmans", ip_pairs), ("ea_vs_koopmans", ea_pairs)):
            if len(pairs) > 3:
                a = np.array([item[0] for item in pairs])
                b = np.array([item[1] for item in pairs])
                entry[label] = {
                    "n": len(pairs),
                    "spearman_rho": float(stats.spearmanr(a, b).statistic),
                    "pearson_r": float(stats.pearsonr(a, b).statistic),
                    "mean_offset_eV": float(np.mean(a - b)),
                    "mean_abs_offset_eV": float(np.mean(np.abs(a - b))),
                }
            else:
                entry[label] = {"n": len(pairs), "note": "not enough overlap"}
        payload[medium] = entry
    return payload


def rank_stability(layer_rows):
    payload = []
    for channel in ("ip", "ea"):
        for charge_class in ("neutral", "charged"):
            rows = None
            for medium, _solvent, _epsilon in MEDIA:
                current = subset(layer_rows, channel, medium, charge_class)
                keys = {row["inchikey"] for row in current}
                rows = keys if rows is None else (rows & keys)
            if not rows or len(rows) < 5:
                continue
            by_key = {row["inchikey"]: row for row in layer_rows}
            ordered = [by_key[key] for key in sorted(rows)]
            media = [item[0] for item in MEDIA]
            for i, left in enumerate(media):
                for right in media[i + 1:]:
                    x = np.array([as_float(row[channel + "_" + left + "_eV"]) for row in ordered], dtype=float)
                    y = np.array([as_float(row[channel + "_" + right + "_eV"]) for row in ordered], dtype=float)
                    metrics = w21.rank_metrics(x, y)
                    payload.append({
                        "channel": channel,
                        "charge_class": charge_class,
                        "left": left,
                        "right": right,
                        "n": int(x.size),
                        "spearman_rho": metrics["spearman_rho"],
                        "kendall_tau_b": metrics["kendall_tau_b"],
                        "pearson_r": metrics["pearson_r"],
                        "mean_signed_shift_eV": metrics["mean_signed_shift_eV"],
                        "mean_abs_shift_eV": metrics["mean_abs_shift_eV"],
                        "naive_inversions": metrics["naive_inversions"],
                        "f_naive_inversion": metrics["f_naive_inversion"],
                        "pairs": metrics["pairs"],
                        "topk_10": metrics["topk"]["k/N=10%"]["overlap"],
                        "topk_20": metrics["topk"]["k/N=20%"]["overlap"],
                        "topk_30": metrics["topk"]["k/N=30%"]["overlap"],
                    })
    return payload


def reference_step(layer_rows):
    from scipy import stats

    roster = {row["inchikey"] for row in w21.read_rows(w21.ROSTER)}
    by_key = {row["inchikey"]: row for row in layer_rows}
    selected = []
    if REDOX_REFERENCE.is_file():
        import csv as _csv

        with REDOX_REFERENCE.open(encoding="utf-8", newline="") as handle:
            for entry in _csv.DictReader(handle):
                if entry.get("source") != "RX-392":
                    continue
                key = str(entry.get("inchikey") or "")
                if key not in roster or key not in by_key:
                    continue
                reference_ip = as_float(entry.get("IP"))
                reference_ea = as_float(entry.get("EA"))
                if reference_ip is None:
                    continue
                selected.append((key, reference_ip, reference_ea, by_key[key]))
    payload = {"n": len(selected), "note": "RX-392 交集极薄；约定为自由能，本臂为能量差"}
    if len(selected) < 4:
        payload["usable"] = False
        return payload
    payload["usable"] = True
    reference_ip = np.array([item[1] for item in selected])
    reference_ea = np.array([item[2] for item in selected if item[2] is not None])
    for medium, _solvent, _epsilon in MEDIA:
        ours_ip = np.array([as_float(item[3]["ip_" + medium + "_eV"]) for item in selected], dtype=float)
        mask = ~np.isnan(ours_ip)
        if int(mask.sum()) > 3:
            payload["ip_" + medium] = {
                "n": int(mask.sum()),
                "spearman_rho": float(stats.spearmanr(ours_ip[mask], reference_ip[mask]).statistic),
                "pearson_r": float(stats.pearsonr(ours_ip[mask], reference_ip[mask]).statistic),
                "mean_signed_difference_eV": float(np.mean(ours_ip[mask] - reference_ip[mask])),
                "mean_abs_difference_eV": float(np.mean(np.abs(ours_ip[mask] - reference_ip[mask]))),
            }
    ea_rows = [item for item in selected if item[2] is not None]
    if ea_rows:
        ours_ea = np.array([as_float(item[3]["ea_water_eV"]) for item in ea_rows], dtype=float)
        mask = ~np.isnan(ours_ea)
        if int(mask.sum()) > 3:
            payload["ea_water"] = {
                "n": int(mask.sum()),
                "spearman_rho": float(stats.spearmanr(ours_ea[mask], reference_ea[mask]).statistic),
                "mean_signed_difference_eV": float(np.mean(ours_ea[mask] - reference_ea[mask])),
            }
    gas = payload.get("ip_gas", {})
    payload["H5_holds"] = bool(
        gas
        and abs(gas.get("mean_signed_difference_eV", 0.0)) >= H5_OFFSET_EV
        and gas.get("spearman_rho", 0.0) >= H5_RHO
    )
    payload["H5_thresholds"] = {"offset_eV": H5_OFFSET_EV, "rho": H5_RHO}
    return payload


def neutral_anchor(layer_rows):
    entries = []
    for row in layer_rows:
        value = as_float(row["neutral_anchor_max_abs_delta_eV"])
        if value is None:
            continue
        entries.append({"inchikey": row["inchikey"], "name": row["name"],
                        "max_abs_delta_eV": value})
    worst = max((item["max_abs_delta_eV"] for item in entries), default=None)
    return {
        "n_compounds_compared": len(entries),
        "max_abs_delta_eV": worst,
        "tolerance_eV": H6_TOLERANCE_EV,
        "holds": bool(entries) and worst is not None and worst <= H6_TOLERANCE_EV,
        "entries": entries,
    }


def count_failures(layer_rows):
    total = 0
    by_arm = Counter()
    for row in layer_rows:
        for arm_key in ARM_KEYS:
            status = row.get(arm_key + "_status")
            if status in ("ok", "not_computed", ""):
                continue
            total += 1
            by_arm[arm_key] += 1
    return {"total": total, "by_arm": dict(by_arm)}


def scf_retry_posthoc(executable, layer_rows, timeout_seconds, limit=None):
    from rdkit import Chem

    meta = w21.read_rows(w21.META)
    failures = []
    for row in layer_rows:
        for arm_key in ARM_KEYS:
            status = row.get(arm_key + "_status")
            if status in ("ok", "not_computed", ""):
                continue
            failures.append((row, arm_key))
    if limit is not None:
        failures = failures[:limit]
    entries = []
    for row, arm_key in failures:
        index = int(row["row_index"])
        meta_row = meta[index] if index < len(meta) else None
        entry = {"inchikey": row["inchikey"], "name": row["name"], "arm": arm_key,
                 "recovered": "no", "homo_eV": "", "lumo_eV": "", "total_E_hartree": "", "error": ""}
        if meta_row is None:
            entry["error"] = "meta row missing"
            entries.append(entry)
            continue
        molecule, _ff, error = w21.embed(meta_row["canonical_smiles"], 42 + index)
        if molecule is None:
            entry["error"] = error or "embed_failed"
            entries.append(entry)
            continue
        medium, state = arm_key.split("_", 1)
        solvent = dict((item[0], item[1]) for item in MEDIA).get(medium)
        unpaired = dict((item[0], item[2]) for item in STATES)[state]
        net = int(Chem.GetFormalCharge(molecule))
        try:
            result = run_arm(executable, "retry_%03d_%s" % (index, arm_key),
                             Chem.MolToXYZBlock(molecule), net + unpaired,
                             1 if unpaired else 0,
                             solvent, timeout_seconds)
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)[:200]
            entries.append(entry)
            continue
        parsed = parse_arm(result)
        if parsed["status"] == "ok":
            entry["recovered"] = "yes"
            entry["homo_eV"] = fmt(parsed["homo_eV"])
            entry["lumo_eV"] = fmt(parsed["lumo_eV"])
            entry["total_E_hartree"] = fmt(parsed["total_E_hartree"])
        else:
            entry["error"] = (parsed.get("error") or parsed["status"])[:200]
        entries.append(entry)
        print(json.dumps({"retry": arm_key, "name": row["name"],
                          "recovered": entry["recovered"]}, ensure_ascii=False), flush=True)
    return {
        "attempted": len(entries),
        "recovered": int(sum(1 for item in entries if item["recovered"] == "yes")),
        "entries": entries,
        "post_hoc": "not_preregistered",
    }


def build_summary(records, layer_rows, prereg, prereg_sha, elapsed, retry, generated_at):
    neutral_rows = [row for row in layer_rows if row["charge_class"] == "neutral"]
    charged_rows = [row for row in layer_rows if row["charge_class"] == "charged"]
    ip_rows = [row for row in neutral_rows
               if all(as_float(row["ip_" + medium + "_eV"]) is not None for medium, _s, _e in MEDIA)]
    ea_rows = [row for row in neutral_rows
               if all(as_float(row["ea_" + medium + "_eV"]) is not None for medium, _s, _e in MEDIA)]
    h12 = h1_h2(ip_rows, ea_rows)
    h3 = h3_monotonicity(ip_rows)
    h4 = anion_signature(layer_rows)
    h5 = reference_step(layer_rows)
    anchor = neutral_anchor(layer_rows)
    failures = count_failures(layer_rows)
    hypotheses = {
        "H1": {
            "verdict": "成立" if all(h12["ip_" + medium]["holds"] for medium in SOLVENT_MEDIA) else "判否",
            "by_medium": {medium: h12["ip_" + medium] for medium in SOLVENT_MEDIA},
        },
        "H2": {
            "verdict": "成立" if all(h12["ea_" + medium]["holds"] for medium in SOLVENT_MEDIA) else "判否",
            "by_medium": {medium: h12["ea_" + medium] for medium in SOLVENT_MEDIA},
        },
        "H3": {"verdict": "成立" if h3["holds"] else "判否"},
        "H4": {"verdict": "成立" if h4["holds"] else "判否"},
        "H5": {"verdict": "成立" if h5.get("H5_holds") else "判否"},
        "H6": {"verdict": "成立" if anchor["holds"] else "判否（本臂作废）"},
    }
    xtb_version = ""
    for row in layer_rows:
        if row.get("xtb_version"):
            xtb_version = row["xtb_version"]
            break
    actual_runs = int(sum(
        1 for row in layer_rows for arm_key in ARM_KEYS
        if row.get(arm_key + "_status") not in ("", "not_computed")
    ))
    charge_classes = Counter(row["charge_class"] for row in layer_rows)
    return {
        "schema_version": "w23_redox_dscf_summary@1",
        "task": "w23_redox_dscf",
        "generated_at_utc": generated_at,
        "prereg": {"path": "probes/w23_redox_dscf_prereg.json", "sha256": prereg_sha,
                   "status": prereg.get("status")},
        "inputs": prereg["inputs"],
        "pool": {
            "n_compounds": len(layer_rows),
            "arms_per_compound": len(ARM_KEYS),
            "arm_keys": list(ARM_KEYS),
            "planned_runs": int(prereg["arms"]["planned_runs"]),
            "actual_runs": actual_runs,
            "media": [{"key": item[0], "alpb_name": item[1], "epsilon": item[2]} for item in MEDIA],
            "execution": prereg["arms"]["execution"],
            "xtb_version": xtb_version,
            "charge_classes": dict(charge_classes),
            "n_charge_class_neutral": charge_classes.get("neutral", 0),
            "n_charge_class_charged": charge_classes.get("charged", 0),
            "n_ip_complete_neutral": len(ip_rows),
            "n_ea_complete_neutral": len(ea_rows),
            "matches_prereg": bool(len(layer_rows) == prereg["inputs"]["roster"]["rows"]),
        },
        "ip_ea_stats": {
            "ip": {medium: channel_stats(ip_rows, "ip", medium) for medium, _s, _e in MEDIA},
            "ea": {medium: channel_stats(ea_rows, "ea", medium) for medium, _s, _e in MEDIA},
        },
        "displacements": h12,
        "monotonicity": h3,
        "koopmans": koopmans(neutral_rows),
        "anion_signature": h4,
        "rank_rows": rank_stability(layer_rows),
        "reference_step": h5,
        "anchor": {key: value for key, value in anchor.items() if key != "entries"},
        "failures": failures,
        "retry": {key: value for key, value in retry.items() if key != "entries"},
        "hypotheses": hypotheses,
        "elapsed_seconds": elapsed,
        "main_scoreboard_attempts_delta": 0,
        "declared_limits": prereg["declared_limits"],
        "forbidden": prereg["forbidden"],
        "boundaries": [
            "半经验 GFN2-xTB --opt，不是 DFT 级",
            "绝热口径（三态各自优化）",
            "RX-392 交集只有 10 个化合物且为自由能约定",
            "净电荷非零化合物单独统计，不与中性分子混合",
            "四个冻结读数未动、主记分牌尝试 0 次",
        ],
    }


def write_delta_csv(h12):
    header = ["channel", "medium", "n", "mean_eV", "sd_eV", "share_negative", "share_positive",
              "share_in_predicted_direction", "threshold", "holds"]
    rows = []
    for channel in ("ip", "ea"):
        for medium in SOLVENT_MEDIA:
            item = h12[channel + "_" + medium]
            rows.append([channel, medium, item["n"], fmt(item["mean_eV"]), fmt(item["sd_eV"]),
                         fmt(item["share_negative"]), fmt(item["share_positive"]),
                         fmt(item["share_in_predicted_direction"]), item["threshold"],
                         str(item["holds"]).lower()])
    w21.write_csv(DELTA_CSV, header, rows)


def write_mono_csv(h3):
    header = ["channel", "n", "strictly_increasing_count", "share", "binom_p_greater",
              "threshold", "holds"]
    w21.write_csv(MONO_CSV, header, [["ip", h3["n"], h3["strictly_increasing_count"],
                                      fmt(h3["share"]), fmt(h3["binom_p_greater"]),
                                      h3["threshold"], str(h3["holds"]).lower()]])


def write_koopmans_csv(payload):
    header = ["medium", "comparison", "n", "spearman_rho", "pearson_r", "mean_offset_eV",
              "mean_abs_offset_eV"]
    rows = []
    for medium, _s, _e in MEDIA:
        for label in ("ip_vs_koopmans", "ea_vs_koopmans"):
            item = payload[medium][label]
            if "spearman_rho" not in item:
                continue
            rows.append([medium, label, item["n"], fmt(item["spearman_rho"]),
                         fmt(item["pearson_r"]), fmt(item["mean_offset_eV"]),
                         fmt(item["mean_abs_offset_eV"])])
    w21.write_csv(KOOPMANS_CSV, header, rows)


def write_anion_csv(h4):
    header = ["medium", "n", "unbound", "share"]
    rows = [[medium, item["n"], item["unbound"], fmt(item["share"])]
            for medium, item in h4["by_medium"].items()]
    w21.write_csv(ANION_CSV, header, rows)


def write_rank_csv(rank_rows):
    header = ["channel", "charge_class", "left", "right", "n", "spearman_rho", "kendall_tau_b",
              "pearson_r", "mean_signed_shift_eV", "mean_abs_shift_eV", "naive_inversions",
              "f_naive_inversion", "pairs", "topk_10", "topk_20", "topk_30"]
    w21.write_csv(RANK_CSV, header,
                  [[row[column] if isinstance(row[column], str) else fmt(row[column])
                    for column in header] for row in rank_rows])
    topk_header = ["channel", "charge_class", "left", "right", "n", "topk_10", "topk_20", "topk_30"]
    w21.write_csv(TOPK_CSV, topk_header,
                  [[row[column] if isinstance(row[column], str) else fmt(row[column])
                    for column in topk_header] for row in rank_rows])


def write_reference_csv(payload):
    header = ["comparison", "n", "spearman_rho", "pearson_r", "mean_signed_difference_eV",
              "mean_abs_difference_eV"]
    rows = []
    for key, item in payload.items():
        if not isinstance(item, dict) or "n" not in item:
            continue
        rows.append([key, item.get("n"), fmt(item.get("spearman_rho")),
                     fmt(item.get("pearson_r")), fmt(item.get("mean_signed_difference_eV")),
                     fmt(item.get("mean_abs_difference_eV"))])
    w21.write_csv(REFERENCE_CSV, header, rows)


def write_anchor_csv(anchor):
    header = ["inchikey", "name", "max_abs_delta_eV"]
    w21.write_csv(ANCHOR_CSV, header,
                  [[item["inchikey"], item["name"], fmt(item["max_abs_delta_eV"])]
                   for item in anchor["entries"]])


def write_retry_csv(retry):
    header = ["inchikey", "name", "arm", "recovered", "homo_eV", "lumo_eV", "total_E_hartree",
              "error"]
    w21.write_csv(RETRY_CSV, header,
                  [[item[column] for column in header] for item in retry["entries"]])


def write_qc_csv(layer_rows):
    header = ["medium", "neutral_ok", "cation_ok", "anion_ok", "anion_unbound_share"]
    rows = []
    for medium, _s, _e in MEDIA:
        counts = Counter(row[medium + "_" + state + "_status"] for row in layer_rows
                         for state in ("neutral", "cation", "anion"))
        flags = [row["anion_unbound_" + medium] for row in layer_rows
                 if row["anion_unbound_" + medium]]
        share = (flags.count("yes") / len(flags)) if flags else float("nan")
        rows.append([medium,
                     sum(1 for row in layer_rows if row[medium + "_neutral_status"] == "ok"),
                     sum(1 for row in layer_rows if row[medium + "_cation_status"] == "ok"),
                     sum(1 for row in layer_rows if row[medium + "_anion_status"] == "ok"),
                     fmt(share)])
    w21.write_csv(QC_CSV, header, rows)


def write_summary(summary):
    """Serialise the summary without the transient per-row payload.

    The layer rows are attached only so that write_artifacts can reach the
    per-compound QC table; they are already on disk as the layer CSV and must
    not be duplicated inside the JSON.
    """

    payload = {key: value for key, value in summary.items() if key != "layer_rows"}
    SUMMARY.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")


def write_artifacts(summary):
    write_delta_csv(summary["displacements"])
    write_mono_csv(summary["monotonicity"])
    write_koopmans_csv(summary["koopmans"])
    write_anion_csv(summary["anion_signature"])
    write_rank_csv(summary["rank_rows"])
    write_reference_csv(summary["reference_step"])
    write_anchor_csv({"entries": summary["anchor_entries"]})
    write_retry_csv({"entries": summary["retry_entries"]})
    write_qc_csv(summary["layer_rows"])


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join(["---"] * len(header)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def f3(value):
    if value is None or value == "":
        return "n/a"
    try:
        return "%.4f" % float(value)
    except (TypeError, ValueError):
        return "n/a"


def render_report(summary):
    pool = summary["pool"]
    stats = summary["ip_ea_stats"]
    lines = []
    lines.append("# W23-2 · Axis A P_1 首次实例化：GFN2-xTB dSCF 电离能/电子亲和能（气相 + 三档 ALPB）")
    lines.append("")
    lines.append("- **预注册**：probes/w23_redox_dscf_prereg.json（sha256 " + summary["prereg"]["sha256"][:16] + "…，status = locked_before_run）。")
    lines.append("- **池**：" + str(pool["n_compounds"]) + " 个化合物 x 12 臂 = **" + str(pool["planned_runs"]) + " 次 GFN2-xTB**（4 介质 x 3 电荷态）。")
    lines.append("- **层级**：GFN2-xTB 半经验 --opt，**绝热口径**（三态各自优化）；**不是 DFT 级**。")
    lines.append("- **纪律**：冻结的闭壳层参数构造器未改动（开壳层走新增的 xtb_open_shell_arguments）；不动冻结读数、主记分牌尝试 0 次、不引用 Reaxys 数值、参考层只作对照不入池。")
    lines.append("")
    lines.append("## 1. 池、执行与判据总览")
    lines.append("")
    lines.append(table(["项", "值"], [
        ["化合物数", pool["n_compounds"]],
        ["每化合物臂数", pool["arms_per_compound"]],
        ["计划/实际 xTB 次数", str(pool["planned_runs"]) + " / " + str(pool["actual_runs"])],
        ["介质", "、".join(item["key"] for item in pool["media"])],
        ["净电荷分类（中性 / 带电）", str(pool["n_charge_class_neutral"]) + " / " + str(pool["n_charge_class_charged"])],
        ["四介质 IP 齐全（中性分子）", pool["n_ip_complete_neutral"]],
        ["四介质 EA 齐全（中性分子）", pool["n_ea_complete_neutral"]],
        ["xtb 版本", pool["xtb_version"]],
        ["挂钟秒（本机）", "%.1f" % summary["elapsed_seconds"]],
    ]))
    lines.append("")
    lines.append(table(["假设", "判据", "读数", "判词"], [
        ["H1 溶剂化降低 IP（dIP < 0）", "三档均 >= 0.90",
         f3(min(summary["hypotheses"]["H1"]["by_medium"][m]["share_in_predicted_direction"] for m in SOLVENT_MEDIA)),
         summary["hypotheses"]["H1"]["verdict"]],
        ["H2 溶剂化提高 EA（dEA > 0）", "三档均 >= 0.80",
         f3(min(summary["hypotheses"]["H2"]["by_medium"][m]["share_in_predicted_direction"] for m in SOLVENT_MEDIA)),
         summary["hypotheses"]["H2"]["verdict"]],
        ["H3 |dIP| 随 eps 逐化合物递增", "占比 >= 0.60", f3(summary["monotonicity"]["share"]),
         summary["hypotheses"]["H3"]["verdict"]],
        ["H4 气相阴离子多数不束缚（A5）", "气相占比 >= 0.50 且 气相-水 >= 0.20",
         f3(summary["anion_signature"]["gas_share"]) + " -> " + f3(summary["anion_signature"]["water_share"]),
         summary["hypotheses"]["H4"]["verdict"]],
        ["H5 dSCF IP vs RX-392：量级偏而排序相关", "|偏差| >= 1.0 eV 且 rho >= 0.60",
         f3(summary["reference_step"].get("ip_gas", {}).get("mean_signed_difference_eV"))
         + " eV / rho "
         + f3(summary["reference_step"].get("ip_gas", {}).get("spearman_rho")),
         summary["hypotheses"]["H5"]["verdict"]],
        ["H6 中性臂回归锚（vs W23-1）", "max|d| <= 1e-6 eV", f3(summary["anchor"]["max_abs_delta_eV"]),
         summary["hypotheses"]["H6"]["verdict"]],
    ]))
    lines.append("")
    lines.append("## 2. H6 · 中性臂回归锚（与 W23-1 逐位比对）")
    lines.append("")
    lines.append("- 可比化合物 **" + str(summary["anchor"]["n_compounds_compared"]) + "** 个，最大绝对差 **" + f3(summary["anchor"]["max_abs_delta_eV"]) + " eV**（容差 1e-6）。")
    lines.append("- 判词：**" + summary["hypotheses"]["H6"]["verdict"] + "**。通过意味着 IP/EA 的两个新电荷态与中性态共享同一几何来源。")
    lines.append("")
    lines.append("## 3. R1 · IP / EA 的四介质分布（中性分子）")
    lines.append("")
    rows = []
    for medium, _s, _e in MEDIA:
        ip = stats["ip"][medium]
        ea = stats["ea"][medium]
        rows.append([medium, ip["n"], f3(ip["mean_eV"]), f3(ip["sd_eV"]), f3(ip["min_eV"]),
                     f3(ip["max_eV"]), f3(ea["mean_eV"]), f3(ea["sd_eV"]), f3(ea["min_eV"]),
                     f3(ea["max_eV"])])
    lines.append(table(["介质", "n_IP", "IP 均值", "IP sd", "IP min", "IP max",
                        "EA 均值", "EA sd", "EA min", "EA max"], rows))
    lines.append("")
    lines.append("单位 eV。**绝热口径**：三态各自 --opt；与任何垂直口径的历史数值不可混比。")
    lines.append("")
    lines.append("## 4. H1 / H2 · 溶剂化位移")
    lines.append("")
    rows = []
    for channel, label in (("ip", "dIP = IP(medium) - IP(gas)"), ("ea", "dEA = EA(medium) - EA(gas)")):
        for medium in SOLVENT_MEDIA:
            item = summary["displacements"][channel + "_" + medium]
            rows.append([label, medium, item["n"], f3(item["mean_eV"]), f3(item["sd_eV"]),
                         f3(item["share_negative"]), f3(item["share_positive"]),
                         f3(item["share_in_predicted_direction"]),
                         "成立" if item["holds"] else "**判否**"])
    lines.append(table(["通道", "介质", "n", "均值 (eV)", "sd (eV)", "占比<0", "占比>0",
                        "预注册方向占比", "判词"], rows))
    lines.append("")
    lines.append("## 5. H3 · |dIP| 随 eps 逐化合物单调递增")
    lines.append("")
    lines.append(table(["项", "值"], [
        ["n", summary["monotonicity"]["n"]],
        ["严格递增数", summary["monotonicity"]["strictly_increasing_count"]],
        ["占比", f3(summary["monotonicity"]["share"])],
        ["单侧符号检验 p", f3(summary["monotonicity"]["binom_p_greater"])],
        ["判词", summary["hypotheses"]["H3"]["verdict"]],
    ]))
    lines.append("")
    lines.append("## 6. R3 · Koopmans 对照（dSCF vs -eps_HOMO / -eps_LUMO）")
    lines.append("")
    rows = []
    for medium, _s, _e in MEDIA:
        entry = summary["koopmans"][medium]
        ip_entry = entry.get("ip_vs_koopmans", {})
        ea_entry = entry.get("ea_vs_koopmans", {})
        rows.append([medium, ip_entry.get("n"), f3(ip_entry.get("spearman_rho")),
                     f3(ip_entry.get("mean_offset_eV")), f3(ip_entry.get("mean_abs_offset_eV")),
                     ea_entry.get("n"), f3(ea_entry.get("spearman_rho")),
                     f3(ea_entry.get("mean_offset_eV"))])
    lines.append(table(["介质", "n_IP", "rho(IP,-HOMO)", "IP 平均偏差 (eV)", "IP 平均绝对偏差",
                        "n_EA", "rho(EA,-LUMO)", "EA 平均偏差 (eV)"], rows))
    lines.append("")
    lines.append("## 7. H4 · 阴离子束缚签名（W22 评审 A5 的可证伪形式）")
    lines.append("")
    rows = []
    for medium, _s, _e in MEDIA:
        item = summary["anion_signature"]["by_medium"][medium]
        rows.append([medium, item["n"], item["unbound"], f3(item["share"])])
    lines.append(table(["介质", "可判读数", "最高占据轨道能 > 0（不束缚）", "占比"], rows))
    lines.append("")
    lines.append("- 判词：**" + summary["hypotheses"]["H4"]["verdict"] + "**（气相 " + f3(summary["anion_signature"]["gas_share"]) + " → 水 " + f3(summary["anion_signature"]["water_share"]) + "，差 " + f3(summary["anion_signature"]["gas_minus_water"]) + "）。")
    lines.append("- 该判据只描述**占据轨道能符号**这一件事，不是束缚能的严格判据（半经验层没有弥散函数）。")
    lines.append("")
    lines.append("## 8. R5 · 排序稳定性（IP / EA 在介质之间）")
    lines.append("")
    rows = []
    for row in summary["rank_rows"]:
        rows.append([row["channel"], row["charge_class"], row["left"] + " -> " + row["right"],
                     row["n"], f3(row["spearman_rho"]), f3(row["kendall_tau_b"]),
                     f3(row["f_naive_inversion"]), f3(row["topk_10"])])
    lines.append(table(["通道", "电荷类", "对比", "n", "rho", "tau_b", "naive 换序率", "Top-10% 重叠"], rows))
    lines.append("")
    lines.append("## 9. R6 · RX-392 外部对照（极薄，n = " + str(summary["reference_step"]["n"]) + "）")
    lines.append("")
    if summary["reference_step"].get("usable"):
        rows = []
        for key in ("ip_gas", "ip_thf", "ip_benzaldehyde", "ip_water", "ea_water"):
            item = summary["reference_step"].get(key)
            if not isinstance(item, dict):
                continue
            rows.append([key, item.get("n"), f3(item.get("spearman_rho")),
                         f3(item.get("mean_signed_difference_eV")),
                         f3(item.get("mean_abs_difference_eV"))])
        lines.append(table(["对比", "n", "rho", "平均有符号差 (eV)", "平均绝对差 (eV)"], rows))
    else:
        lines.append("- 交集不足，无法给出对照读数。")
    lines.append("")
    lines.append("- **约定警告**：RX-392 的 IP/EA 出自自由能约定（redox_free_ener.py），本臂是**能量差**；两者之差含约定差，**不得**读成纯方法误差。")
    lines.append("")
    lines.append("## 10. R8 · 失败与重试登记")
    lines.append("")
    lines.append(table(["项", "值"], [
        ["失败臂（冻结协议）", summary["failures"]["total"]],
        ["重试尝试", summary["retry"]["attempted"]],
        ["重试恢复", summary["retry"]["recovered"]],
        ["重试性质", "post_hoc，不参与任何预注册读数"],
    ]))
    lines.append("")
    lines.append("## 11. 判词与边界")
    lines.append("")
    lines.append("- 框架 §3 Axis A P_1 由「未执行」推进到「**已实例化（半经验 --opt 绝热口径）**」；至此 Axis A 的三个槽位（P_0 / P_1 / P_2）在仓内全部有内容。")
    lines.append("- 本臂**不能**回答 §10.3（阈值决策误差）；也**不能**替代 DFT 级的 P_1。")
    lines.append("- 冻结名册的 " + str(pool["n_compounds"]) + " 条记录全部是净电荷为零的输入（离子液体以中性盐对形式入池），因此本臂的带电类统计为空；这与预注册「净电荷非零化合物单独统计」的规则一致，只是本轮该分支没有样本。")
    lines.append("- 全部读数只对 " + str(pool["n_compounds"]) + " 个冻结名册化合物成立。")
    lines.append("")
    lines.append("*W23-2 · 生成脚本 probes/w23_redox_dscf.py · 预注册 sha256 " + summary["prereg"]["sha256"] + " · 本周主记分牌尝试 0 次*")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--from-layer", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args(argv)

    if args.report_only:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        REPORT.write_text(render_report(summary), encoding="utf-8", newline="\n")
        print(json.dumps({"mode": "report_only", "report": str(REPORT)}, ensure_ascii=False))
        return 0

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("status") != "locked_before_run":
        raise SystemExit("pre-registration is not locked; refusing to run")
    prereg_sha = sha256_file(PREREG)

    if args.from_layer:
        layer_rows = w21.read_rows(LAYER_CSV)
        previous = json.loads(SUMMARY.read_text(encoding="utf-8"))
        summary = build_summary([], layer_rows, prereg, prereg_sha, previous["elapsed_seconds"],
                                {"attempted": previous["retry"]["attempted"],
                                 "recovered": previous["retry"]["recovered"],
                                 "post_hoc": "not_preregistered",
                                 "entries": previous.get("retry_entries", [])},
                                previous["generated_at_utc"])
        summary["anchor_entries"] = previous.get("anchor_entries", [])
        summary["retry_entries"] = previous.get("retry_entries", [])
        summary["layer_rows"] = layer_rows
        write_summary(summary)
        REPORT.write_text(render_report(summary), encoding="utf-8", newline="\n")
        print(json.dumps({"mode": "from_layer", "n": len(layer_rows), "report": str(REPORT)},
                         ensure_ascii=False))
        return 0

    meta_rows = w21.read_rows(w21.META)
    if args.limit is not None:
        meta_rows = meta_rows[:args.limit]
    medium_layer = {row["inchikey"]: row for row in w21.read_rows(MEDIUM_LAYER)}
    executable = str(w21.resolve_xtb())
    payloads = [(index, row["name"], row["canonical_smiles"], executable, args.timeout)
                for index, row in enumerate(meta_rows)]
    started = time.perf_counter()
    records = []
    workers = max(1, int(args.workers))
    if workers == 1:
        for payload in payloads:
            records.append(run_compound(payload))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for count, record in enumerate(pool.map(run_compound, payloads, chunksize=1), start=1):
                records.append(record)
                if count % 10 == 0 or count == len(payloads):
                    partial = build_layer_rows(records, meta_rows, medium_layer)
                    w21.write_csv(LAYER_CSV, LAYER_FIELDS,
                                  [[row[field] for field in LAYER_FIELDS] for row in partial])
                    so_far = time.perf_counter() - started
                    print(json.dumps({
                        "processed": count, "total": len(payloads), "last": record.get("name"),
                        "sec": round(so_far, 1),
                        "eta_sec": round(so_far / count * (len(payloads) - count), 1),
                    }, ensure_ascii=False), flush=True)
    layer_rows = build_layer_rows(records, meta_rows, medium_layer)
    w21.write_csv(LAYER_CSV, LAYER_FIELDS, [[row[field] for field in LAYER_FIELDS] for row in layer_rows])
    retry = scf_retry_posthoc(executable, layer_rows, args.timeout)
    elapsed = time.perf_counter() - started
    summary = build_summary(records, layer_rows, prereg, prereg_sha, elapsed, retry, utc_now())
    summary["anchor_entries"] = neutral_anchor(layer_rows)["entries"]
    summary["retry_entries"] = retry["entries"]
    summary["layer_rows"] = layer_rows
    write_artifacts(summary)
    write_summary(summary)
    REPORT.write_text(render_report(summary), encoding="utf-8", newline="\n")
    print(json.dumps({
        "summary": str(SUMMARY),
        "report": str(REPORT),
        "n_compounds": summary["pool"]["n_compounds"],
        "actual_runs": summary["pool"]["actual_runs"],
        "matches_prereg": summary["pool"]["matches_prereg"],
        "H1": summary["hypotheses"]["H1"]["verdict"],
        "H2": summary["hypotheses"]["H2"]["verdict"],
        "H3": summary["hypotheses"]["H3"]["verdict"],
        "H4": summary["hypotheses"]["H4"]["verdict"],
        "H5": summary["hypotheses"]["H5"]["verdict"],
        "H6": summary["hypotheses"]["H6"]["verdict"],
        "anchor_max_abs_delta_eV": summary["anchor"]["max_abs_delta_eV"],
        "ip_gas_mean_eV": summary["ip_ea_stats"]["ip"]["gas"]["mean_eV"],
        "ip_water_mean_eV": summary["ip_ea_stats"]["ip"]["water"]["mean_eV"],
        "ea_gas_mean_eV": summary["ip_ea_stats"]["ea"]["gas"]["mean_eV"],
        "ea_water_mean_eV": summary["ip_ea_stats"]["ea"]["water"]["mean_eV"],
        "anion_unbound_gas": summary["anion_signature"]["gas_share"],
        "anion_unbound_water": summary["anion_signature"]["water_share"],
        "reference_ip_gas": summary["reference_step"].get("ip_gas"),
        "elapsed_seconds": round(elapsed, 1),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
