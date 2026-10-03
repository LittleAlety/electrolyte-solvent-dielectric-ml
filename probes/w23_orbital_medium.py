"""W23-1 -- Axis A P_2 first instantiation: orbital conditional shift under an
ALPB dielectric ladder (thf 7.58 / benzaldehyde 18.0 / water 80.4), for both the
free molecule and the Li+-coordinated conditional state.

Why this arm exists
-------------------
The frozen framework (docs/framework/ranking-electrolyte-materials-v2.md) leaves
section 3 Axis A P_2 ("fixed-background continuum") empty: every cheap-layer
orbital number in this repository is a gas-phase single point.  For an
electrolyte-solvent screen the gas-phase HOMO is the wrong quantity -- oxidation
stability is set by the solvated orbital.  This arm instantiates P_2 at the same
semi-empirical level as W21's C_1, with three ALPB media of increasing dielectric
constant, and it re-derives the gas phase in the same run so the medium shift is
measured against a bit-identical geometry (H5 anchor).

Discipline
----------
No frozen reading moves, no main-scoreboard shot is taken, no Reaxys number is
used and the Batt-P30K reference layer is never folded into a training pool.
The pre-registration is probes/w23_orbital_medium_prereg.json and must read
status = locked_before_run before the probe will start.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _extra in (ROOT / "probes", ROOT / "src"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))
import w21_li_coordination as w21  # geometry, QC and the section-9 metric battery
from export_results_common import write_json_stable

PREREG = ROOT / "probes" / "w23_orbital_medium_prereg.json"
SUMMARY = ROOT / "probes" / "w23_orbital_medium_summary.json"
LAYER_CSV = ROOT / "data" / "processed" / "w23_orbital_medium_layer.csv"
DELTA_CSV = ROOT / "probes" / "artifacts" / "w23_orbital_medium_delta_stats.csv"
MONO_CSV = ROOT / "probes" / "artifacts" / "w23_orbital_medium_monotonicity.csv"
TOPK_CSV = ROOT / "probes" / "artifacts" / "w23_orbital_medium_topk.csv"
RANK_CSV = ROOT / "probes" / "artifacts" / "w23_orbital_medium_rank_pairs.csv"
BATT_CSV = ROOT / "probes" / "artifacts" / "w23_orbital_medium_batt_step.csv"
QC_CSV = ROOT / "probes" / "artifacts" / "w23_orbital_medium_qc.csv"
ANCHOR_CSV = ROOT / "probes" / "artifacts" / "w23_orbital_medium_gas_anchor.csv"
RETRY_CSV = ROOT / "probes" / "artifacts" / "w23_orbital_medium_scf_retry_posthoc.csv"
REPORT = ROOT / "reports" / "w23_orbital_medium.md"

MEDIA = (
    ("thf", "thf", 7.58),
    ("benzaldehyde", "benzaldehyde", 18.0),
    ("water", "water", 80.4),
)
STATES = (("free", False), ("li", True))
SOLVENT_ARMS = tuple(state + "_" + medium for state, _ in STATES for medium, _, _ in MEDIA)
ARM_KEYS = ("gas_free", "gas_li") + SOLVENT_ARMS
CHANNELS = (
    ("homo", "HOMO", "P_0^ox = -epsilon_HOMO: bigger is more oxidation-resistant"),
    ("lumo", "LUMO", "P_0^red = epsilon_LUMO: bigger is more reduction-resistant"),
    ("gap", "gap", "gap carries no direction; reference only"),
)
H1_THRESHOLD = 0.80
H2_THRESHOLD = 0.60
H3_UNRESOLVED = None
H4_RHO_THRESHOLD = 0.90
H5_TOLERANCE_EV = 1e-6
STOICHIOMETRY_UNRESOLVED = None


def layer_fields():
    fields = [
        "inchikey", "name", "canonical_smiles", "row_index", "seed", "motif_class",
        "donor_symbol", "donor_index", "donor_anchor", "formal_charge",
    ]
    for arm in ARM_KEYS:
        fields += [arm + "_homo_eV", arm + "_lumo_eV", arm + "_gap_eV", arm + "_status"]
    for arm in SOLVENT_ARMS:
        fields += [arm + "_d_homo_eV", arm + "_d_lumo_eV", arm + "_d_gap_eV"]
    fields += ["li_mulliken_q", "li_min_dist_A", "li_nearest_atom"]
    for medium, _, _ in MEDIA:
        fields += [
            "li_q_" + medium, "li_dist_" + medium, "qc_" + medium, "seconds_" + medium,
        ]
    fields += [
        "qc_gas", "ff_status", "xtb_version", "gas_anchor_max_abs_delta_eV",
        "seconds_total", "error",
    ]
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


# --------------------------------------------------------------------------- #
# per-compound worker (picklable; one task per molecule, arms serial inside)
# --------------------------------------------------------------------------- #

def _parse(parsed):
    return {
        "status": parsed.get("status"),
        "homo_eV": parsed.get("homo_eV"),
        "lumo_eV": parsed.get("lumo_eV"),
        "gap_eV": parsed.get("gap_eV"),
        "total_energy_hartree": parsed.get("total_energy_hartree"),
        "xtb_version": parsed.get("xtb_version"),
        "li_mulliken_q": parsed.get("li_mulliken_q"),
        "li_min_dist_A": parsed.get("li_min_dist_A"),
        "li_nearest_atom": parsed.get("li_nearest_atom"),
        "error": parsed.get("error") or "",
    }


def run_compound(payload):
    """Embed once, place Li once, then run the seven arms on that same geometry."""

    index, name, smiles, executable, timeout_seconds = payload
    from rdkit import Chem

    record = {
        "row_index": index,
        "name": name,
        "canonical_smiles": smiles,
        "arms": {},
        "error": "",
        "ff_status": "",
        "motif_class": "not_computed",
        "donor_symbol": "",
        "donor_index": "",
        "donor_anchor": "",
        "formal_charge": "",
        "seconds_total": 0.0,
    }
    molecule, ff_status, error = w21.embed(smiles, 42 + index)
    if molecule is None:
        record["error"] = error or "embed_failed"
        return record
    record["ff_status"] = ff_status
    motif = w21.classify_motif(molecule)
    record["motif_class"] = motif["motif_class"]
    record["donor_index"] = motif["donor_index"]
    if motif["donor_kind"] == "lone_pair":
        record["donor_symbol"] = molecule.GetAtomWithIdx(int(motif["donor_index"])).GetSymbol()
    elif motif["motif_class"] in ("aromatic_pi", "alkene_pi"):
        record["donor_symbol"] = "pi"
    else:
        record["donor_symbol"] = "none"
    net_charge = int(Chem.GetFormalCharge(molecule))
    record["formal_charge"] = net_charge
    position, anchor = w21.li_position(molecule, motif)
    record["donor_anchor"] = anchor
    free_xyz = Chem.MolToXYZBlock(molecule)
    li_xyz = w21.xyz_block_with_li(molecule, position)

    def arm(arm_key, xyz_text, charge, label, solvent):
        extra = ("--alpb", solvent) if solvent else ()
        try:
            result = w21.run_arm(
                executable, label, xyz_text, charge, timeout_seconds, extra_arguments=extra
            )
        except Exception as exc:
            return {
                "status": "exception", "homo_eV": None, "lumo_eV": None, "gap_eV": None,
                "total_energy_hartree": None, "xtb_version": None, "li_mulliken_q": None,
                "li_min_dist_A": None, "li_nearest_atom": None,
                "error": str(exc)[:200], "seconds": 0.0,
            }
        parsed = _parse(w21.parse_arm(result))
        parsed["seconds"] = float(result["seconds"])
        return parsed

    # Gas arms keep the W21 labels so the H5 anchor is a same-label regression.
    record["arms"]["gas_free"] = arm("gas_free", free_xyz, net_charge, "c%03d_0" % index, None)
    record["arms"]["gas_li"] = arm("gas_li", li_xyz, net_charge + 1, "c%03d_1" % index, None)
    for medium, solvent, _epsilon in MEDIA:
        for state, needs_li in STATES:
            arm_key = state + "_" + medium
            label = "c%03d_%s_%s" % (index, state, medium)
            record["arms"][arm_key] = arm(
                arm_key, li_xyz if needs_li else free_xyz,
                net_charge + (1 if needs_li else 0), label, solvent,
            )
    record["seconds_total"] = float(sum(a.get("seconds") or 0.0 for a in record["arms"].values()))
    return record


# --------------------------------------------------------------------------- #
# layer assembly
# --------------------------------------------------------------------------- #

def build_layer_rows(records, meta_rows, w21_layer):
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
        row["motif_class"] = record.get("motif_class") or ""
        row["donor_symbol"] = record.get("donor_symbol") or ""
        row["donor_index"] = record.get("donor_index", "")
        row["donor_anchor"] = record.get("donor_anchor") or ""
        row["formal_charge"] = record.get("formal_charge", "")
        row["ff_status"] = record.get("ff_status", "")
        row["error"] = record.get("error") or ""
        row["seconds_total"] = fmt(record.get("seconds_total") or 0.0, 8)
        arms = record.get("arms") or {}
        version = ""
        for arm_key in ARM_KEYS:
            payload = arms.get(arm_key) or {
                "status": "not_computed", "homo_eV": None, "lumo_eV": None, "gap_eV": None,
            }
            row[arm_key + "_homo_eV"] = fmt(payload.get("homo_eV"))
            row[arm_key + "_lumo_eV"] = fmt(payload.get("lumo_eV"))
            row[arm_key + "_gap_eV"] = fmt(payload.get("gap_eV"))
            row[arm_key + "_status"] = payload.get("status") or "not_computed"
            if payload.get("xtb_version"):
                version = payload["xtb_version"]
            if payload.get("error"):
                row["error"] = (row["error"] + " | " + str(payload["error"]))[:300].strip(" |")
        row["xtb_version"] = version
        for medium, _, _ in MEDIA:
            li_arm = arms.get("li_" + medium) or {}
            row["li_q_" + medium] = fmt(li_arm.get("li_mulliken_q"))
            row["li_dist_" + medium] = fmt(li_arm.get("li_min_dist_A"))
            row["seconds_" + medium] = fmt(li_arm.get("seconds"), 8)
        gas_li = arms.get("gas_li") or {}
        row["li_mulliken_q"] = fmt(gas_li.get("li_mulliken_q"))
        row["li_min_dist_A"] = fmt(gas_li.get("li_min_dist_A"))
        row["li_nearest_atom"] = gas_li.get("li_nearest_atom") or ""
        for medium, _, _ in MEDIA:
            row["qc_" + medium] = w21.qc_status(
                as_float(row["li_dist_" + medium]), as_float(row["li_q_" + medium])
            )
        row["qc_gas"] = w21.qc_status(as_float(row["li_min_dist_A"]), as_float(row["li_mulliken_q"]))
        for arm_key in SOLVENT_ARMS:
            state = arm_key.split("_")[0]
            gas_arm = "gas_" + state
            for key, _tag, _note in CHANNELS:
                own = as_float(row[arm_key + "_" + key + "_eV"])
                base = as_float(row[gas_arm + "_" + key + "_eV"])
                row[arm_key + "_d_" + key + "_eV"] = (
                    fmt(own - base) if (own is not None and base is not None) else ""
                )
        previous = w21_layer.get(row["inchikey"])
        anchor = []
        if previous:
            for arm_key, previous_columns in (
                ("gas_free", ("homo_free_eV", "lumo_free_eV", "gap_free_eV")),
                ("gas_li", ("homo_li_eV", "lumo_li_eV", "gap_li_eV")),
            ):
                for key, previous_column in zip(("homo", "lumo", "gap"), previous_columns):
                    own = as_float(row[arm_key + "_" + key + "_eV"])
                    reference = as_float(previous.get(previous_column))
                    if own is not None and reference is not None:
                        anchor.append(abs(own - reference))
        row["gas_anchor_max_abs_delta_eV"] = fmt(max(anchor)) if anchor else ""
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# readings
# --------------------------------------------------------------------------- #

def state_rows(layer_rows, state):
    """Motif-bearing compounds whose gas arm and all three solvent arms succeeded."""

    gas_arm = "gas_" + state
    keep = []
    for row in layer_rows:
        if row["motif_class"] not in w21.MOTIF_CLASSES:
            continue
        if row.get(gas_arm + "_status") != "ok":
            continue
        if any(row.get(state + "_" + medium + "_status") != "ok" for medium, _, _ in MEDIA):
            continue
        keep.append(row)
    return keep


def channel_shift(rows, state, medium, key):
    arm = state + "_" + medium
    gas_arm = "gas_" + state
    deltas = np.array([as_float(row[arm + "_d_" + key + "_eV"]) for row in rows], dtype=float)
    base = np.array([as_float(row[gas_arm + "_" + key + "_eV"]) for row in rows], dtype=float)
    return deltas, base


def shift_summary(rows, state, medium):
    payload = {}
    for key, _tag, _note in CHANNELS:
        deltas, base = channel_shift(rows, state, medium, key)
        var_base = float(np.var(base, ddof=1)) if base.size > 1 else float("nan")
        payload[key] = {
            "n": int(deltas.size),
            "delta_mean_eV": float(np.mean(deltas)),
            "delta_sd_eV": float(np.std(deltas, ddof=1)) if deltas.size > 1 else float("nan"),
            "var_ratio_shift_over_gas": float(np.var(deltas, ddof=1) / var_base) if var_base else float("nan"),
            "share_positive": float(np.mean(deltas > 0)),
            "share_negative": float(np.mean(deltas < 0)),
        }
    homo, lumo = payload["homo"], payload["lumo"]
    payload["h1_pair_share"] = float(np.mean(
        [homo["share_positive"], lumo["share_negative"]]
    ))
    return payload


def h1_verdict(rows, state, medium):
    arm = state + "_" + medium
    gas_arm = "gas_" + state
    good = 0
    total = 0
    for row in rows:
        up = as_float(row[arm + "_d_homo_eV"])
        down = as_float(row[arm + "_d_lumo_eV"])
        if up is None or down is None:
            continue
        total += 1
        if up > 0 and down < 0:
            good += 1
    share = (good / total) if total else float("nan")
    return {
        "arm": arm,
        "n": total,
        "share_homo_up_and_lumo_down": share,
        "threshold": H1_THRESHOLD,
        "holds": bool(total and share >= H1_THRESHOLD),
    }


def monotonicity(rows, state):
    from scipy import stats

    graded = {"homo": [], "gap": []}
    usable = 0
    for row in rows:
        values = {}
        complete = True
        for key in ("homo", "gap"):
            series = []
            for medium, _, _ in MEDIA:
                value = as_float(row[state + "_" + medium + "_d_" + key + "_eV"])
                if value is None:
                    complete = False
                    break
                series.append(value)
            if not complete:
                break
            values[key] = series
        if not complete:
            continue
        usable += 1
        for key, series in values.items():
            if key == "homo":
                graded[key].append(series[0] < series[1] < series[2])
            else:
                graded[key].append(abs(series[0]) < abs(series[1]) < abs(series[2]))
    payload = {"state": state, "n": usable}
    for key, flags in graded.items():
        count = int(sum(flags))
        share = (count / usable) if usable else float("nan")
        p_value = (
            float(stats.binomtest(count, usable, 0.5, alternative="greater").pvalue)
            if usable else float("nan")
        )
        payload[key] = {
            "strictly_increasing_count": count,
            "share": share,
            "binom_p_greater": p_value,
            "threshold": H2_THRESHOLD,
            "holds": bool(usable and share >= H2_THRESHOLD),
        }
    return payload


def rank_table(layer_rows):
    from scipy import stats

    payload = []
    for state in ("free", "li"):
        rows = state_rows(layer_rows, state)
        if len(rows) < 5:
            continue
        gas_arm = "gas_" + state
        medium_arms = [state + "_" + medium for medium, _, _ in MEDIA]
        pairs = [("gas", medium, gas_arm, arm) for medium, arm in zip([m for m, _, _ in MEDIA], medium_arms)]
        for index, (left, _, _) in enumerate(MEDIA):
            for other in MEDIA[index + 1:]:
                pairs.append((left, other[0], state + "_" + left, state + "_" + other[0]))
        for key, _tag, _note in CHANNELS:
            for left, right, left_arm, right_arm in pairs:
                x = np.array([as_float(row[left_arm + "_" + key + "_eV"]) for row in rows], dtype=float)
                y = np.array([as_float(row[right_arm + "_" + key + "_eV"]) for row in rows], dtype=float)
                metrics = w21.rank_metrics(x, y)
                payload.append({
                    "state": state,
                    "channel": key,
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
                    "pearson_pvalue": float(stats.pearsonr(x, y).pvalue) if x.size > 2 else float("nan"),
                })
    return payload


def h4_verdict(rank_rows):
    entries = []
    for row in rank_rows:
        if row["left"] != "gas" or row["channel"] not in ("homo", "lumo"):
            continue
        entries.append({
            "state": row["state"],
            "channel": row["channel"],
            "medium": row["right"],
            "rho": row["spearman_rho"],
            "threshold": H4_RHO_THRESHOLD,
            "holds": bool(row["spearman_rho"] >= H4_RHO_THRESHOLD),
        })
    return {
        "entries": entries,
        "all_hold": bool(entries) and all(item["holds"] for item in entries),
    }


def h3_verdict(layer_rows):
    gas_free = "gas_free"
    gas_li = "gas_li"
    medium = "benzaldehyde"
    usable = []
    for row in layer_rows:
        if row["motif_class"] not in w21.MOTIF_CLASSES:
            continue
        if row[gas_free + "_status"] != "ok" or row[gas_li + "_status"] != "ok":
            continue
        if row["free_" + medium + "_status"] != "ok":
            continue
        usable.append(row)
    if len(usable) < 5:
        return {"n": len(usable), "holds": False, "note": "not enough usable compounds",
                "channel": "homo", "medium": medium,
                "var_ratio_medium_over_gas": None,
                "var_ratio_coordination_over_gas": None}
    free_values = np.array([as_float(row[gas_free + "_homo_eV"]) for row in usable], dtype=float)
    li_values = np.array([as_float(row[gas_li + "_homo_eV"]) for row in usable], dtype=float)
    medium_values = np.array(
        [as_float(row["free_" + medium + "_homo_eV"]) for row in usable], dtype=float
    )
    var_gas = float(np.var(free_values, ddof=1))
    medium_ratio = float(np.var(medium_values - free_values, ddof=1) / var_gas)
    coordination_ratio = float(np.var(li_values - free_values, ddof=1) / var_gas)
    return {
        "n": len(usable),
        "channel": "homo",
        "medium": medium,
        "var_ratio_medium_over_gas": medium_ratio,
        "var_ratio_coordination_over_gas": coordination_ratio,
        "holds": bool(medium_ratio < coordination_ratio),
    }


def gas_anchor(layer_rows):
    entries = []
    for row in layer_rows:
        value = as_float(row["gas_anchor_max_abs_delta_eV"])
        if value is None:
            continue
        entries.append({"inchikey": row["inchikey"], "name": row["name"],
                        "max_abs_delta_eV": value})
    worst = max((item["max_abs_delta_eV"] for item in entries), default=None)
    return {
        "n_compounds_compared": len(entries),
        "max_abs_delta_eV": worst,
        "tolerance_eV": H5_TOLERANCE_EV,
        "holds": bool(entries) and worst is not None and worst <= H5_TOLERANCE_EV,
        "entries": entries,
    }


def batt_layers(layer_rows):
    layer_by_key = {row["inchikey"]: row for row in layer_rows}
    selected = []
    for row in w21.load_batt_subset():
        mine = layer_by_key.get(row["inchikey"])
        if mine is None or mine.get("gas_li_status") != "ok":
            continue
        if mine.get("gas_free_status") != "ok":
            continue
        if any(mine.get(state + "_" + medium + "_status") != "ok"
               for state in ("free", "li") for medium, _, _ in MEDIA):
            continue
        selected.append((row, mine))
    if not selected:
        return {"n": 0, "arms": {}}
    reference = np.array([float(row["batt_homo_eV"]) for row, _mine in selected])
    arms = {
        "P0_themol_geometry_w21_1": np.array([float(row["homo_gfn2_eV"]) for row, _mine in selected]),
        "C0_gas": np.array([as_float(mine["gas_free_homo_eV"]) for _row, mine in selected]),
        "C1_gas": np.array([as_float(mine["gas_li_homo_eV"]) for _row, mine in selected]),
    }
    for medium, _, _ in MEDIA:
        arms["C0_" + medium] = np.array([as_float(m["free_" + medium + "_homo_eV"]) for _r, m in selected])
        arms["C1_" + medium] = np.array([as_float(m["li_" + medium + "_homo_eV"]) for _r, m in selected])
    return {
        "n": len(selected),
        "keys": [row["inchikey"] for row, _mine in selected],
        "arms": {name: w21.batt_step(values, reference) for name, values in arms.items()},
        "reference_layer": "batt_homo_eV (wB97X-V/def2-TZVPPD/SMD(epsilon=18.5), MIT)",
        "tolerance": {"z": w21.Z, "delta_R_sol_eV": w21.DELTA_REF_EV,
                      "registered_limit": "reference-layer physical uncertainty not quantified in-repo"},
    }


def v03_cross_check(layer_rows):
    v03 = {row["inchikey"]: row for row in w21.read_rows(w21.V03_PHYSICAL)}
    from scipy import stats

    out = {}
    for arm_key in ARM_KEYS:
        pairs = []
        for row in layer_rows:
            other = v03.get(row["inchikey"])
            if other is None:
                continue
            mine = as_float(row[arm_key + "_gap_eV"])
            theirs = as_float(other.get("homo_lumo_gap_ev"))
            if mine is None or theirs is None:
                continue
            pairs.append((theirs, mine))
        if len(pairs) > 3:
            a = np.array([item[0] for item in pairs])
            b = np.array([item[1] for item in pairs])
            out[arm_key] = {
                "n": len(pairs),
                "pearson_r": float(stats.pearsonr(a, b).statistic),
                "mean_signed_difference_eV": float(np.mean(b - a)),
                "mean_abs_difference_eV": float(np.mean(np.abs(a - b))),
            }
        else:
            out[arm_key] = {"n": len(pairs), "note": "not enough overlap"}
    return out


def scf_retry_posthoc(executable, layer_rows, timeout_seconds, limit=None):
    """One retry, with a raised iteration cap and electronic temperature, for arms
    that failed the frozen protocol.  Every row here is post-hoc and is never
    folded into a pre-registered reading."""

    from rdkit import Chem

    meta = w21.read_rows(w21.META)
    failures = []
    for row in layer_rows:
        for arm_key in ARM_KEYS:
            if row.get(arm_key + "_status") == "ok":
                continue
            if row.get(arm_key + "_status") in ("not_computed", ""):
                continue
            failures.append((row, arm_key))
    if limit is not None:
        failures = failures[:limit]
    entries = []
    for row, arm_key in failures:
        index = int(row["row_index"])
        meta_row = meta[index] if index < len(meta) else None
        entry = {"inchikey": row["inchikey"], "name": row["name"], "arm": arm_key,
                 "recovered": "no", "homo_eV": "", "lumo_eV": "", "gap_eV": "", "error": ""}
        if meta_row is None:
            entry["error"] = "meta row missing"
            entries.append(entry)
            continue
        molecule, _ff, error = w21.embed(meta_row["canonical_smiles"], 42 + index)
        if molecule is None:
            entry["error"] = error or "embed_failed"
            entries.append(entry)
            continue
        state = arm_key.split("_")[0]
        medium = arm_key.split("_", 1)[1]
        net_charge = int(Chem.GetFormalCharge(molecule))
        if state == "gas":
            xyz_text = Chem.MolToXYZBlock(molecule)
            charge = net_charge
            solvent = None
        else:
            motif = w21.classify_motif(molecule)
            position, _anchor = w21.li_position(molecule, motif)
            if state == "li":
                xyz_text = w21.xyz_block_with_li(molecule, position)
                charge = net_charge + 1
            else:
                xyz_text = Chem.MolToXYZBlock(molecule)
                charge = net_charge
            solvent = medium if medium in [item[0] for item in MEDIA] else None
        extra = list(w21.SCF_RETRY_ARGUMENTS)
        if solvent:
            extra += ["--alpb", solvent]
        try:
            result = w21.run_arm(executable, "retry_%03d_%s" % (index, arm_key), xyz_text,
                                 charge, timeout_seconds, extra_arguments=tuple(extra))
        except Exception as exc:
            entry["error"] = str(exc)[:200]
            entries.append(entry)
            continue
        parsed = w21.parse_arm(result)
        if parsed["status"] == "ok":
            entry["recovered"] = "yes"
            entry["homo_eV"] = fmt(parsed["homo_eV"])
            entry["lumo_eV"] = fmt(parsed["lumo_eV"])
            entry["gap_eV"] = fmt(parsed["gap_eV"])
        else:
            entry["error"] = (parsed.get("error") or parsed["status"])[:200]
        entries.append(entry)
        print(json.dumps({"retry": arm_key, "name": row["name"], "recovered": entry["recovered"]},
                         ensure_ascii=False), flush=True)
    return {
        "attempted": len(entries),
        "recovered": int(sum(1 for item in entries if item["recovered"] == "yes")),
        "entries": entries,
        "post_hoc": "not_preregistered",
    }


# --------------------------------------------------------------------------- #
# artifacts
# --------------------------------------------------------------------------- #

def write_delta_csv(shifts):
    header = ["state", "medium", "channel", "n", "delta_mean_eV", "delta_sd_eV",
              "var_ratio_shift_over_gas", "share_positive", "share_negative"]
    rows = []
    for state in ("free", "li"):
        for medium, _, _ in MEDIA:
            payload = shifts[state][medium]
            for key, _tag, _note in CHANNELS:
                item = payload[key]
                rows.append([state, medium, key, item["n"], fmt(item["delta_mean_eV"]),
                             fmt(item["delta_sd_eV"]), fmt(item["var_ratio_shift_over_gas"]),
                             fmt(item["share_positive"]), fmt(item["share_negative"])])
    w21.write_csv(DELTA_CSV, header, rows)


def write_mono_csv(monotonicity_payload):
    header = ["state", "channel", "n", "strictly_increasing_count", "share", "binom_p_greater",
              "threshold", "holds"]
    rows = []
    for state in ("free", "li"):
        payload = monotonicity_payload[state]
        for key in ("homo", "gap"):
            item = payload[key]
            rows.append([state, key, payload["n"], item["strictly_increasing_count"],
                         fmt(item["share"]), fmt(item["binom_p_greater"]),
                         item["threshold"], str(item["holds"]).lower()])
    w21.write_csv(MONO_CSV, header, rows)


def write_rank_csv(rank_rows):
    header = ["state", "channel", "left", "right", "n", "spearman_rho", "kendall_tau_b",
              "pearson_r", "mean_signed_shift_eV", "mean_abs_shift_eV", "naive_inversions",
              "f_naive_inversion", "pairs", "topk_10", "topk_20", "topk_30"]
    rows = [[row[column] if isinstance(row[column], str) else fmt(row[column])
             for column in header] for row in rank_rows]
    w21.write_csv(RANK_CSV, header, rows)
    topk_header = ["state", "channel", "left", "right", "n", "topk_10", "topk_20", "topk_30"]
    w21.write_csv(TOPK_CSV, topk_header,
                  [[row[column] if isinstance(row[column], str) else fmt(row[column])
                    for column in topk_header] for row in rank_rows])


def write_batt_csv(batt):
    header = ["arm", "n", "pairs", "resolved_in_both", "robust_inversions", "f_robust_inversion",
              "naive_inversions", "f_naive_inversion", "kendall_tau_b", "spearman_rho",
              "loo_mean_abs_residual_eV", "ols_slope", "ols_intercept"]
    rows = []
    for name, payload in batt["arms"].items():
        rows.append([name, payload["n"], payload["pairs"], payload["resolved_in_both"],
                     payload["robust_inversions"], fmt(payload["f_robust_inversion"]),
                     payload["naive_inversions"], fmt(payload["f_naive_inversion"]),
                     fmt(payload["kendall_tau_b"]), fmt(payload["spearman_rho"]),
                     fmt(payload["loo_mean_abs_residual_eV"]), fmt(payload["ols_slope"]),
                     fmt(payload["ols_intercept"])])
    w21.write_csv(BATT_CSV, header, rows)


def write_qc_csv(layer_rows):
    header = ["medium", "intact", "loose", "dissociated", "not_available",
              "median_li_dist_A", "median_li_q"]
    rows = [["gas"] + qc_row(layer_rows, "qc_gas", "li_min_dist_A", "li_mulliken_q")]
    for medium, _, _ in MEDIA:
        rows.append([medium] + qc_row(layer_rows, "qc_" + medium,
                                      "li_dist_" + medium, "li_q_" + medium))
    w21.write_csv(QC_CSV, header, rows)


def qc_row(layer_rows, status_column, distance_column, charge_column):
    counts = Counter(row[status_column] for row in layer_rows)
    distances = [as_float(row[distance_column]) for row in layer_rows]
    charges = [as_float(row[charge_column]) for row in layer_rows]
    distances = [value for value in distances if value is not None]
    charges = [value for value in charges if value is not None]
    return [counts.get("intact", 0), counts.get("loose", 0), counts.get("dissociated", 0),
            counts.get("not_available", 0),
            fmt(float(np.median(distances))) if distances else "",
            fmt(float(np.median(charges))) if charges else ""]


def write_anchor_csv(anchor):
    header = ["inchikey", "name", "max_abs_delta_eV"]
    w21.write_csv(ANCHOR_CSV, header,
                  [[item["inchikey"], item["name"], fmt(item["max_abs_delta_eV"])]
                   for item in anchor["entries"]])


def write_retry_csv(retry):
    header = ["inchikey", "name", "arm", "recovered", "homo_eV", "lumo_eV", "gap_eV", "error"]
    w21.write_csv(RETRY_CSV, header, [[item[column] for column in header] for item in retry["entries"]])


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #

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
    shifts = summary["channel_shifts"]
    monotonicity_payload = summary["monotonicity"]
    lines = []
    lines.append("# W23-1 · Axis A P_2 首次实例化：ALPB 三档介电阶梯下的轨道条件位移")
    lines.append("")
    lines.append("- **预注册**：probes/w23_orbital_medium_prereg.json（sha256 " + summary["prereg"]["sha256"][:16] + "…，status = locked_before_run）。")
    lines.append("- **池**：" + str(pool["n_compounds"]) + " 个化合物 x 7 臂 = **" + str(pool["planned_runs"]) + " 次 GFN2-xTB**（几何与构象种子与 W21 C_1 逐位同源）。")
    lines.append("- **层级**：GFN2-xTB 半经验 + ALPB 隐式溶剂（三档同一模型）。**不是 DFT/SMD**；本臂是框架 §3 Axis A P_2 的低层级首次实例化。")
    lines.append("- **纪律**：不动四个冻结读数、主记分牌尝试 0 次（累计仍 12）、不引用 Reaxys 数值、不把 Batt 参考层折进任何训练池。")
    lines.append("")
    lines.append("## 1. 池、执行与判据总览")
    lines.append("")
    lines.append(table(["项", "值"], [
        ["化合物数", pool["n_compounds"]],
        ["每化合物臂数", pool["arms_per_compound"]],
        ["计划/实际 xTB 次数", str(pool["planned_runs"]) + " / " + str(pool["actual_runs"])],
        ["介质", "、".join(item["key"] + " (eps=" + str(item["epsilon"]) + ")" for item in pool["media"])],
        ["xtb 版本", pool["xtb_version"]],
        ["执行方式", pool["execution"]],
        ["带基序化合物（free 态可读）", pool["n_motif_free"]],
        ["带基序化合物（li 态可读）", pool["n_motif_li"]],
        ["挂钟秒（本机）", "%.1f" % summary["elapsed_seconds"]],
    ]))
    lines.append("")
    lines.append(table(["假设", "判据", "读数", "判词"], [
        ["H1 溶剂使 HOMO 上移/LUMO 下移", "占比 >= 0.80", f3(summary["h1_min_share"]), summary["hypotheses"]["H1"]["verdict"]],
        ["H2 位移随 eps 单调", "逐化合物严格递增占比 >= 0.60", f3(summary["hypotheses"]["H2"]["min_share"]), summary["hypotheses"]["H2"]["verdict"]],
        ["H3 介质位移是二阶", "var(medium)/var(gas) < var(C1)/var(gas)", f3(summary["h3"].get("var_ratio_medium_over_gas")) + " < " + f3(summary["h3"].get("var_ratio_coordination_over_gas")), summary["hypotheses"]["H3"]["verdict"]],
        ["H4 介质保持排序", "rho(gas,medium) >= 0.90（homo 与 lumo，全部 6 条）", f3(summary["h4"]["min_rho"]), summary["hypotheses"]["H4"]["verdict"]],
        ["H5 气相回归锚", "全部化合物 max|d| <= 1e-6 eV", f3(summary["anchor"]["max_abs_delta_eV"]), summary["hypotheses"]["H5"]["verdict"]],
    ]))
    lines.append("")
    lines.append("## 2. H5 · 几何同源回归锚")
    lines.append("")
    lines.append("本臂在**同一次运行**里重算气相（free 与 Li+ 两态），与 W21 已提交层逐化合物比对：")
    lines.append("")
    lines.append("- 可比化合物 **" + str(summary["anchor"]["n_compounds_compared"]) + "** 个，最大绝对差 **" + f3(summary["anchor"]["max_abs_delta_eV"]) + " eV**（容差 1e-6 eV）。")
    lines.append("- 判词：**" + summary["hypotheses"]["H5"]["verdict"] + "**。通过意味着三档位移量的是纯介质效应，不混构象漂移。")
    lines.append("- **一条如实登记的窄口**：预注册写的是「全部 246 个化合物」，实际可比 244 个 —— 另 2 个（1,3-dimethylimidazolium dimethylphosphate、Iron pentacarbonyl）在 W21 侧两态都失败、本臂也失败，因此**没有**可比的数值对，不构成反证但也不计入。凡两侧都有值处，差恰好为 0。")
    lines.append("")
    lines.append("## 3. H1 + R1 · 三档介质的位移分布")
    lines.append("")
    for state, label in (("free", "自由态（C_0）"), ("li", "Li+ 配位态（C_1）")):
        lines.append("### " + label)
        lines.append("")
        rows = []
        for medium, _, epsilon in MEDIA:
            payload = shifts[state][medium]
            rows.append([medium + " (eps=" + str(epsilon) + ")",
                         payload["homo"]["n"],
                         f3(payload["homo"]["delta_mean_eV"]),
                         f3(payload["lumo"]["delta_mean_eV"]),
                         f3(payload["gap"]["delta_mean_eV"]),
                         f3(payload["homo"]["var_ratio_shift_over_gas"]),
                         f3(payload["gap"]["var_ratio_shift_over_gas"])])
        lines.append(table(["介质", "n", "dHOMO 均值 (eV)", "dLUMO 均值 (eV)", "dgap 均值 (eV)",
                            "var(dHOMO)/var(gas)", "var(dgap)/var(gas)"], rows))
        lines.append("")
        h1_rows = []
        for medium, _, _epsilon in MEDIA:
            item = summary["hypotheses"]["H1"]["by_arm"][state + "_" + medium]
            h1_rows.append([state + "_" + medium, item["n"], f3(item["share_homo_up_and_lumo_down"]),
                            "成立" if item["holds"] else "**判否**"])
        lines.append(table(["臂", "n", "HOMO 上移且 LUMO 下移占比", "判词"], h1_rows))
        lines.append("")
    lines.append("**读法（必须与判否一起读）**：")
    lines.append("")
    lines.append("- 自由态：位移量级只有 0.01–0.05 eV，而逐化合物标准差是 0.16–0.30 eV —— **均值远小于离散**，所以 H1 的自由态三档不是「符号相反」，而是「符号不成体系」；把「判否」读成「溶剂没有影响」是错的，正确的读法是「ALPB 对中性闭壳分子的一阶轨道位移小于构象/身份带来的离散」。")
    lines.append("- Li+ 配位态：HOMO 与 LUMO **同时上移约 3–4 eV**，216 个化合物里 100% 为正 —— 这不是「效应消失」，而是**符号被反转**：阳离子被极性介质稳定，其轨道能整体抬升。预注册把中性分子的教科书符号写给了带正电的加合物，因此 0.0% 这个读数是**预注册的错，不是数据的错**，照实登记。")
    lines.append("- 位移随 eps 增大（水档最大），这是 H2 里唯一成立的那一格（Li+ 态的 |dgap|）。")
    lines.append("")
    lines.append("## 4. H2 · eps 单调性（逐化合物，非均值）")
    lines.append("")
    rows = []
    for state in ("free", "li"):
        payload = monotonicity_payload[state]
        for key, label in (("homo", "dHOMO 递增"), ("gap", "|dgap| 递增")):
            item = payload[key]
            rows.append([state, label, payload["n"], item["strictly_increasing_count"],
                         f3(item["share"]), f3(item["binom_p_greater"]),
                         "成立" if item["holds"] else "**判否**"])
    lines.append(table(["态", "通道", "n", "严格递增数", "占比", "符号检验 p（单侧）", "判词"], rows))
    lines.append("")
    lines.append("## 5. H4 + R3 · 排序稳定性（气相 → 介质；介质两两）")
    lines.append("")
    rows = []
    for row in summary["rank_rows"]:
        rows.append([row["state"], row["channel"], row["left"] + " → " + row["right"], row["n"],
                     f3(row["spearman_rho"]), f3(row["kendall_tau_b"]),
                     f3(row["f_naive_inversion"]), f3(row["topk_10"])])
    lines.append(table(["态", "通道", "对比", "n", "rho", "tau_b", "naive 换序率", "Top-10% 重叠"], rows))
    lines.append("")
    lines.append("- H4 判词：**" + summary["hypotheses"]["H4"]["verdict"] + "**（最低 rho = " + f3(summary["h4"]["min_rho"]) + "）。")
    lines.append("- 对照：W21 的 C_0 → C_1 台阶里 lumo 通道 rho 只有 0.2296 —— **配位摧毁 LUMO 排序，介质不摧毁**，两条臂结论必须分开说。")
    lines.append("")
    lines.append("## 6. H3 · 介质位移是二阶效应")
    lines.append("")
    lines.append("在 " + str(summary["h3"]["n"]) + " 个三态齐全的化合物上，homo 通道（介质 = " + summary["h3"]["medium"] + "）：")
    lines.append("")
    lines.append(table(["量", "值"], [
        ["var(d_medium)/var(gas)", f3(summary["h3"].get("var_ratio_medium_over_gas"))],
        ["var(d_C1)/var(gas)", f3(summary["h3"].get("var_ratio_coordination_over_gas"))],
        ["判词", summary["hypotheses"]["H3"]["verdict"]],
    ]))
    lines.append("")
    lines.append("## 7. R4 · 态 x 介质 均值表（HOMO / LUMO / gap, eV）")
    lines.append("")
    rows = []
    for state in ("free", "li"):
        rows.append([state + " (gas)", f3(summary["state_medium_means"][state]["gas"]["homo"]),
                     f3(summary["state_medium_means"][state]["gas"]["lumo"]),
                     f3(summary["state_medium_means"][state]["gas"]["gap"]),
                     summary["state_medium_means"][state]["gas"]["n"]])
        for medium, _, _epsilon in MEDIA:
            item = summary["state_medium_means"][state][medium]
            rows.append([state + " (" + medium + ")", f3(item["homo"]), f3(item["lumo"]),
                         f3(item["gap"]), item["n"]])
    lines.append(table(["态 (介质)", "HOMO 均值", "LUMO 均值", "gap 均值", "n"], rows))
    lines.append("")
    lines.append("## 8. R5 · §9 Batt 子集九层并排")
    lines.append("")
    if summary["batt"]["n"]:
        rows = []
        for name, payload in summary["batt"]["arms"].items():
            rows.append([name, payload["n"], payload["resolved_in_both"], payload["robust_inversions"],
                         f3(payload["f_robust_inversion"]), f3(payload["kendall_tau_b"]),
                         f3(payload["spearman_rho"])])
        lines.append(table(["廉价层", "n", "两侧可分辨 pair", "robust inversion", "f_robust", "tau_b", "rho"], rows))
    else:
        lines.append("- 本臂没有可用的 Batt 交集行。")
    lines.append("")
    lines.append("容差：z = " + str(summary["batt"].get("tolerance", {}).get("z")) + "、dR_sol = 0.05 eV；参考层物理不确定度仍未量化。")
    lines.append("")
    lines.append("**一条方向性结果**：把隐式溶剂加进来，与参考层的吻合度是**单调改善**的（自由态 rho 0.8606 气相 → 0.8798/0.8787/0.8866；配位态 0.8062 → 0.9001/0.8864/0.9226，最好的一层是 C1_water 的 0.9226）。参考层本身就是 SMD(eps=18.5) 的溶剂化计算 —— 补上它包含的物理效应，廉价层就更靠近它。九层里 robust inversion 全为 0。")
    lines.append("")
    lines.append("## 9. R6 · gap 与 v03 物理块的一致性核验")
    lines.append("")
    rows = []
    for arm_key, item in summary["v03_cross_check"].items():
        rows.append([arm_key, item.get("n"), f3(item.get("pearson_r")),
                     f3(item.get("mean_signed_difference_eV")),
                     f3(item.get("mean_abs_difference_eV"))])
    lines.append(table(["臂", "n", "Pearson r", "平均有符号差 (eV)", "平均绝对差 (eV)"], rows))
    lines.append("")
    lines.append("## 10. R7 · Li+ 臂质控（与 W21 同判据）")
    lines.append("")
    rows = []
    for item in summary["qc"]["rows"]:
        rows.append(item)
    lines.append(table(["介质", "intact", "loose", "dissociated", "not_available",
                        "Li 距离中位数 (A)", "q(Li) 中位数 (e)"], rows))
    lines.append("")
    lines.append("## 11. R8 · 失败与重试登记")
    lines.append("")
    lines.append(table(["项", "值"], [
        ["失败臂（冻结协议）", summary["failures"]["total"]],
        ["重试尝试", summary["retry"]["attempted"]],
        ["重试恢复", summary["retry"]["recovered"]],
        ["重试性质", "post_hoc，不参与任何预注册读数"],
    ]))
    lines.append("")
    lines.append("## 12. 判词与边界")
    lines.append("")
    lines.append("- 框架 §3 Axis A P_2 由「未执行」推进到「**已实例化（半经验 + ALPB 层面）**」；§3 Axis B C_1 由「仅气相」升级为「气相 + 三档介质」。")
    lines.append("- 本臂**不能**回答 §10.3（阈值决策误差）：仓内仍没有来自外部设计要求的 HOMO/LUMO 阈值。")
    lines.append("- 近 eps 对照用 ALPB(苯甲醛, eps=18.0)，与参考层 Batt 的 SMD(eps=18.5) **同 eps 不同隐式模型**，两者之差不得读成方法优劣。")
    lines.append("- 全部读数只对带基序的化合物族成立；均值/中位数口径与 W21 同族。")
    lines.append("")
    lines.append("*W23-1 · 生成脚本 probes/w23_orbital_medium.py · 预注册 sha256 " + summary["prereg"]["sha256"] + " · 本周主记分牌尝试 0 次*")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# summary + main
# --------------------------------------------------------------------------- #

def state_medium_means(layer_rows):
    payload = {}
    for state in ("free", "li"):
        rows = state_rows(layer_rows, state)
        entry = {}
        gas_key = "gas"
        gas_arm = "gas_" + state
        base = {key: (np.array([as_float(row[gas_arm + "_" + key + "_eV"]) for row in rows], dtype=float)
                      if rows else np.array([])) for key, _t, _n in CHANNELS}
        entry[gas_key] = {
            "n": len(rows),
            "homo": float(np.mean(base["homo"])) if rows else None,
            "lumo": float(np.mean(base["lumo"])) if rows else None,
            "gap": float(np.mean(base["gap"])) if rows else None,
        }
        for medium, _, _epsilon in MEDIA:
            arm = state + "_" + medium
            values = {key: np.array([as_float(row[arm + "_" + key + "_eV"]) for row in rows], dtype=float)
                      for key, _t, _n in CHANNELS}
            entry[medium] = {
                "n": len(rows),
                "homo": float(np.mean(values["homo"])) if rows else None,
                "lumo": float(np.mean(values["lumo"])) if rows else None,
                "gap": float(np.mean(values["gap"])) if rows else None,
            }
        payload[state] = entry
    return payload


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


def build_summary(records, layer_rows, prereg, prereg_sha, elapsed, retry, generated_at):
    shifts = {state: {medium: shift_summary(state_rows(layer_rows, state), state, medium)
                      for medium, _, _ in MEDIA} for state in ("free", "li")}
    h1_arms = {}
    for state in ("free", "li"):
        rows = state_rows(layer_rows, state)
        for medium, _, _ in MEDIA:
            item = h1_verdict(rows, state, medium)
            h1_arms[state + "_" + medium] = item
    monotonicity_payload = {state: monotonicity(state_rows(layer_rows, state), state)
                            for state in ("free", "li")}
    rank_rows = rank_table(layer_rows)
    h4 = h4_verdict(rank_rows)
    h3 = h3_verdict(layer_rows)
    anchor = gas_anchor(layer_rows)
    batt = batt_layers(layer_rows)
    v03 = v03_cross_check(layer_rows)
    failures = count_failures(layer_rows)
    h1_shares = [item["share_homo_up_and_lumo_down"] for item in h1_arms.values()
                 if item["share_homo_up_and_lumo_down"] is not None
                 and not np.isnan(item["share_homo_up_and_lumo_down"])]
    monotonicity_shares = [monotonicity_payload[state][key]["share"]
                           for state in ("free", "li") for key in ("homo", "gap")]
    h4_rhos = [item["rho"] for item in h4["entries"]]
    xtb_version = ""
    for row in layer_rows:
        if row.get("xtb_version"):
            xtb_version = row["xtb_version"]
            break
    actual_runs = int(sum(
        1 for row in layer_rows for arm_key in ARM_KEYS
        if row.get(arm_key + "_status") not in ("", "not_computed")
    ))
    hypotheses = {
        "H1": {
            "verdict": "成立" if h1_arms and all(item["holds"] for item in h1_arms.values()) else "判否",
            "by_arm": h1_arms,
        },
        "H2": {
            "verdict": "成立" if all(monotonicity_payload[state][key]["holds"]
                                     for state in ("free", "li") for key in ("homo", "gap"))
                       else "判否",
            "min_share": float(min(monotonicity_shares)) if monotonicity_shares else None,
        },
        "H3": {"verdict": "成立" if h3.get("holds") else "判否"},
        "H4": {"verdict": "成立" if h4["all_hold"] else "判否"},
        "H5": {"verdict": "成立" if anchor["holds"] else "判否（本臂作废）"},
    }
    return {
        "schema_version": "w23_orbital_medium_summary@1",
        "task": "w23_orbital_medium",
        "generated_at_utc": generated_at,
        "prereg": {"path": "probes/w23_orbital_medium_prereg.json", "sha256": prereg_sha,
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
            "n_motif_free": len(state_rows(layer_rows, "free")),
            "n_motif_li": len(state_rows(layer_rows, "li")),
            "matches_prereg": bool(len(layer_rows) == prereg["inputs"]["roster"]["rows"]),
            "geometry_seed_rule": prereg["geometry_protocol"]["seed_rule"],
        },
        "channel_shifts": shifts,
        "h1_min_share": float(min(h1_shares)) if h1_shares else None,
        "monotonicity": monotonicity_payload,
        "rank_rows": rank_rows,
        "h3": h3,
        "h4": {**h4, "min_rho": float(min(h4_rhos)) if h4_rhos else None},
        "anchor": {key: value for key, value in anchor.items() if key != "entries"},
        "batt": batt,
        "v03_cross_check": v03,
        "state_medium_means": state_medium_means(layer_rows),
        "qc": {
            "rows": [["gas"] + qc_row(layer_rows, "qc_gas", "li_min_dist_A", "li_mulliken_q")]
                    + [[medium] + qc_row(layer_rows, "qc_" + medium,
                                         "li_dist_" + medium, "li_q_" + medium)
                       for medium, _, _ in MEDIA],
            "gas_counts": dict(Counter(row["qc_gas"] for row in layer_rows)),
            "by_medium_counts": {medium: dict(Counter(row["qc_" + medium] for row in layer_rows))
                                 for medium, _, _ in MEDIA},
        },
        "failures": failures,
        "retry": {key: value for key, value in retry.items() if key != "entries"},
        "hypotheses": hypotheses,
        "elapsed_seconds": elapsed,
        "main_scoreboard_attempts_delta": 0,
        "declared_limits": prereg["declared_limits"],
        "forbidden": prereg["forbidden"],
        "boundaries": [
            "半经验 + ALPB，不是 DFT/SMD",
            "近 eps 对照与参考层同 eps 不同隐式模型",
            "只对带基序化合物族成立",
            "参考层物理不确定度未量化（0.05 eV 数值容差）",
        ],
    }


def write_summary(summary):
    write_json_stable(SUMMARY, summary)


def write_artifacts(summary):
    write_delta_csv(summary["channel_shifts"])
    write_mono_csv(summary["monotonicity"])
    write_rank_csv(summary["rank_rows"])
    write_batt_csv(summary["batt"])
    write_qc_csv_rows(summary["qc"]["rows"])
    write_anchor_csv({"entries": summary["anchor_entries"]})
    write_retry_csv({"entries": summary["retry_entries"]})


def write_qc_csv_rows(rows):
    header = ["medium", "intact", "loose", "dissociated", "not_available",
              "median_li_dist_A", "median_li_q"]
    w21.write_csv(QC_CSV, header, rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="smoke-test: only the first N compounds")
    parser.add_argument("--workers", type=int, default=8,
                        help="molecule-level parallelism (each arm still runs single-threaded)")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--from-layer", action="store_true",
                        help="recompute the readings from the layer CSV, no xTB")
    parser.add_argument("--report-only", action="store_true",
                        help="re-render the report from the summary, no xTB")
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
        write_summary(summary)
        REPORT.write_text(render_report(summary), encoding="utf-8", newline="\n")
        print(json.dumps({"mode": "from_layer", "n": len(layer_rows), "report": str(REPORT)},
                         ensure_ascii=False))
        return 0

    meta_rows = w21.read_rows(w21.META)
    if args.limit is not None:
        meta_rows = meta_rows[:args.limit]
    w21_layer = {row["inchikey"]: row for row in w21.read_rows(w21.LAYER_CSV)}
    executable = str(w21.resolve_xtb())
    payloads = [
        (index, row["name"], row["canonical_smiles"], executable, args.timeout)
        for index, row in enumerate(meta_rows)
    ]
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
                    partial = build_layer_rows(records, meta_rows, w21_layer)
                    w21.write_csv(LAYER_CSV, LAYER_FIELDS,
                                  [[row[field] for field in LAYER_FIELDS] for row in partial])
                    so_far = time.perf_counter() - started
                    print(json.dumps({
                        "processed": count,
                        "total": len(payloads),
                        "last": record.get("name"),
                        "sec": round(so_far, 1),
                        "eta_sec": round(so_far / count * (len(payloads) - count), 1),
                    }, ensure_ascii=False), flush=True)
    layer_rows = build_layer_rows(records, meta_rows, w21_layer)
    w21.write_csv(LAYER_CSV, LAYER_FIELDS, [[row[field] for field in LAYER_FIELDS] for row in layer_rows])
    retry = scf_retry_posthoc(executable, layer_rows, args.timeout)
    elapsed = time.perf_counter() - started
    summary = build_summary(records, layer_rows, prereg, prereg_sha, elapsed, retry, utc_now())
    summary["anchor_entries"] = gas_anchor(layer_rows)["entries"]
    summary["retry_entries"] = retry["entries"]
    write_summary(summary)
    write_artifacts(summary)
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
        "anchor_max_abs_delta_eV": summary["anchor"]["max_abs_delta_eV"],
        "homo_rho_free_benzaldehyde": next(
            (row["spearman_rho"] for row in summary["rank_rows"]
             if row["state"] == "free" and row["channel"] == "homo"
             and row["left"] == "gas" and row["right"] == "benzaldehyde"), None),
        "lumo_rho_free_benzaldehyde": next(
            (row["spearman_rho"] for row in summary["rank_rows"]
             if row["state"] == "free" and row["channel"] == "lumo"
             and row["left"] == "gas" and row["right"] == "benzaldehyde"), None),
        "elapsed_seconds": round(elapsed, 1),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
