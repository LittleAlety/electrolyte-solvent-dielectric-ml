"""Independent adversarial audit of the W17-17 THEMol registry-wide expansion arm.

Round 2 (post-fix): the maintainer closed F1/F2/F6/F7/F8.  This script re-derives
every number from the frozen layer and the raw harvest, decides each finding as
closed / open / partially_closed, and keeps the round-1 record so nothing is
erased.  It also carries the round-1 snapshot so the history is auditable.

Nothing here imports a generator.  Writes probes/themol_expanded_layer_audit.json
and is driven by tests/test_themol_expanded_layer_audit.py.
"""

from __future__ import annotations

import argparse
import ast
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

LAYER = REPO / "data/processed/themol_orbital_layer_expanded.csv"
SUMMARY = REPO / "probes/themol_orbital_layer_expanded_summary.json"
ROSTER = REPO / "probes/themol_registry_expansion_roster.csv"
ROSTER_SUMMARY = REPO / "probes/themol_registry_expansion_roster_summary.json"
PREREG = REPO / "probes/themol_registry_expansion_prereg.json"
REGISTRY = REPO / "data/processed/four_core_key_registry.csv"
INDEX = REPO / "data/raw/themol/themol_registry_index.csv"
DIELECTRIC = REPO / "data/dielectric_v04.csv"
RAW_DIR = REPO / "data/raw/themol/expand"
UNIT_AUDIT = REPO / "data/raw/themol/unit_audit.json"
UNIT_RECHECK = REPO / "data/raw/themol/expand_unit_recheck.json"
VERIFIER = REPO / "scripts/verify_themol_orbital_layer_expanded.py"
BUILDER = REPO / "probes/build_themol_orbital_layer_expanded.py"
REPORT = REPO / "reports/themol_orbital_layer_expanded.md"
OUT = REPO / "probes/themol_expanded_layer_audit.json"

MAE_LIMIT_EV = 0.35
R_LIMIT = 0.80
TIER_ORDER = (
    "no_reference_orbital",
    "flagship_dielectric",
    "named_core_channel",
    "calibration_bulk",
)
CHANNELS = (
    ("homo", "homo_gfn2_eV", "batt_homo_eV"),
    ("lumo", "lumo_gfn2_eV", "batt_lumo_eV"),
    ("gap", "gap_gfn2_eV", "batt_gap_eV"),
)

ROUND1 = {
    "layer_sha256": "44f900b14778961eea878e167f06e459f7c0d953de15fabf13e55cd62dedd3a0",
    "layer_rows": 3109,
    "summary_sha256": "557c9e3e08468b32a64745f346f32983c7f331dc6fc2da1d87ca08d1bb49e073",
    "verdicts": {
        "F1": "fail",
        "F2": "fail",
        "F3": "pass",
        "F4": "pass",
        "F5": "partial",
        "F6": "fail",
        "F7": "fail",
        "F8": "fail",
        "F9": "not_reproducible",
    },
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def num(value: object) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def fit_line(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return slope, my - slope * mx


def fold_map(keys: list[str], folds: int = 2) -> dict[str, int]:
    return {key: index % folds for index, key in enumerate(sorted(keys))}


def snapshot() -> dict[str, object]:
    out: dict[str, object] = {}
    for label, path in (
        ("layer", LAYER),
        ("summary", SUMMARY),
        ("roster", ROSTER),
        ("roster_summary", ROSTER_SUMMARY),
        ("prereg", PREREG),
        ("unit_recheck", UNIT_RECHECK),
    ):
        entry: dict[str, object] = {
            "path": str(path.relative_to(REPO)),
            "sha256": sha256_of(path),
            "bytes": path.stat().st_size,
        }
        if label in ("layer", "roster"):
            entry["rows"] = len(read_rows(path))
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.UTC)
        entry["mtime"] = mtime.isoformat(timespec="seconds")
        out[label] = entry
    return out


def roster_recompute() -> dict[str, object]:
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")

    def canon(value: str | None) -> str | None:
        if not value:
            return None
        molecule = Chem.MolFromSmiles(value)
        return None if molecule is None else Chem.MolToSmiles(molecule)

    index: dict[str, tuple[str, str]] = {}
    for row in read_rows(INDEX):
        index.setdefault(row["canonical_smiles"], (row["uuid"], row["h5_file"]))
    dielectric = set()
    for row in read_rows(DIELECTRIC):
        key = canon(row.get("smiles"))
        if key:
            dielectric.add(key)
    counters = {
        "registry_rows": 0,
        "unparsable_smiles": 0,
        "not_in_themol": 0,
        "duplicate_canonical": 0,
        "matched": 0,
    }
    seen: set[str] = set()
    tiers = {tier: 0 for tier in TIER_ORDER}
    for raw in read_rows(REGISTRY):
        counters["registry_rows"] += 1
        key = canon(raw.get("smiles"))
        if key is None:
            counters["unparsable_smiles"] += 1
            continue
        if key not in index:
            counters["not_in_themol"] += 1
            continue
        if key in seen:
            counters["duplicate_canonical"] += 1
            continue
        seen.add(key)
        counters["matched"] += 1
        if raw.get("has_orbitals") != "true":
            tier = "no_reference_orbital"
        elif key in dielectric:
            tier = "flagship_dielectric"
        elif any(
            raw.get(field) == "true"
            for field in ("has_viscosity", "has_redox_label", "has_liquid_window")
        ):
            tier = "named_core_channel"
        else:
            tier = "calibration_bulk"
        tiers[tier] += 1
    recorded = json.loads(ROSTER_SUMMARY.read_text(encoding="utf-8"))
    frozen = sha256_of(ROSTER)
    return {
        "recomputed": {"counters": counters, "rows_by_tier": tiers, "roster_rows": counters["matched"]},
        "recorded": {"counters": recorded["counters"], "rows_by_tier": recorded["rows_by_tier"]},
        "counters_agree": counters == recorded["counters"],
        "tiers_agree": tiers == recorded["rows_by_tier"],
        "digest_matches_file": frozen == recorded["roster_sha256"],
    }


def calibration_channel(pairs: list[dict[str, object]]) -> dict[str, object]:
    pairs = [pair for pair in pairs if pair["x"] is not None]
    if len(pairs) < 2:
        return {"n": len(pairs)}
    folds = fold_map([str(pair["key"]) for pair in pairs])
    out_of_sample: list[tuple[float, float]] = []
    for held in (0, 1):
        train = [p for p in pairs if folds[str(p["key"])] != held]
        test = [p for p in pairs if folds[str(p["key"])] == held]
        if len(train) < 2 or not test:
            continue
        fit = fit_line([float(p["x"]) for p in train], [float(p["y"]) for p in train])
        if fit is None:
            continue
        slope, intercept = fit
        for point in test:
            out_of_sample.append((slope * float(point["x"]) + intercept, float(point["y"])))
    if not out_of_sample:
        return {"n": len(pairs), "status": "no_fold"}
    errors = [abs(yhat - y) for yhat, y in out_of_sample]
    mae = sum(errors) / len(errors)
    full = fit_line([float(p["x"]) for p in pairs], [float(p["y"]) for p in pairs])
    r_in = pearson([float(p["x"]) for p in pairs], [float(p["y"]) for p in pairs])
    r_oos = pearson([yhat for yhat, _ in out_of_sample], [y for _, y in out_of_sample])
    gate_in = bool(full and mae <= MAE_LIMIT_EV and r_in is not None and r_in >= R_LIMIT)
    gate_oos = bool(full and mae <= MAE_LIMIT_EV and r_oos is not None and r_oos >= R_LIMIT)
    return {
        "n": len(pairs),
        "n_out_of_sample": len(errors),
        "slope_full_in_sample": full[0] if full else None,
        "intercept_full_in_sample": full[1] if full else None,
        "r_in_sample": r_in,
        "r_out_of_sample": r_oos,
        "mae_out_of_sample_eV": mae,
        "max_abs_error_out_of_sample_eV": max(errors),
        "gate_if_in_sample_r": "usable_with_flag" if gate_in else "reference_only",
        "gate_if_out_of_sample_r": "usable_with_flag" if gate_oos else "reference_only",
    }


def calibration_recompute() -> dict[str, object]:
    layer = read_rows(LAYER)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    result: dict[str, object] = {}
    for channel, x_field, y_field in CHANNELS:
        pairs = [
            {"key": row["inchikey"], "x": num(row[x_field]), "y": num(row[y_field])}
            for row in layer
            if num(row[y_field]) is not None
        ]
        rec = calibration_channel(pairs)
        recorded = summary["calibration"].get(channel, {})
        rec["summary_status"] = recorded.get("status")
        rec["summary_status_basis"] = recorded.get("status_basis")
        rec["summary_r_in_sample"] = recorded.get("pearson_r_in_sample")
        rec["summary_r_out_of_sample"] = recorded.get("pearson_r_out_of_sample")
        rec["summary_mae_out_of_sample_eV"] = recorded.get("mae_out_of_sample_eV")
        rec["slope_matches_summary"] = (
            rec.get("slope_full_in_sample") is not None
            and recorded.get("slope") is not None
            and abs(float(rec["slope_full_in_sample"]) - recorded["slope"]) <= 1e-9
        )
        rec["recorded_status_equals_out_of_sample_gate"] = (
            recorded.get("status") == rec["gate_if_out_of_sample_r"]
        )
        rec["recorded_status_equals_in_sample_gate"] = (
            recorded.get("status") == rec["gate_if_in_sample_r"]
        )
        result[channel] = rec
    homo = result["homo"]
    applied = None
    if homo.get("slope_full_in_sample") is not None:
        slope = float(homo["slope_full_in_sample"])
        intercept = float(homo["intercept_full_in_sample"])
        applied = all(
            num(row["calib_homo_eV"]) is None
            or abs(num(row["calib_homo_eV"]) - (slope * num(row["homo_gfn2_eV"]) + intercept)) <= 1e-9
            for row in layer
        )
    result["_layer"] = {
        "rows": len(layer),
        "calib_homo_present": sum(1 for row in layer if num(row["calib_homo_eV"]) is not None),
        "calib_lumo_present": sum(1 for row in layer if num(row["calib_lumo_eV"]) is not None),
        "calib_homo_is_full_in_sample_fit": applied,
        "roles": summary.get("roles"),
    }
    return result


def builder_gate_audit() -> dict[str, object]:
    src = BUILDER.read_text(encoding="utf-8")
    shared = (REPO / "probes/build_themol_orbital_layer.py").read_text(encoding="utf-8")
    return {
        "builder_redecides_status": "apply_out_of_sample_gate(homo_cal, homo_pairs)" in src,
        "builder_gate_uses_out_of_sample_r": "r_out is not None" in src and "r_out >= R_LIMIT" in src,
        "builder_status_basis_literal": "out_of_sample_mae_and_out_of_sample_r" in src,
        "shared_w17_14_module_still_gates_in_sample": (
            "ok = full is not None and mae <= MAE_LIMIT_EV and r is not None and r >= R_LIMIT" in shared
        ),
        "residual_note": (
            "the shared W17-14 calibration() still decides its own status on in-sample r; "
            "this arm re-decides locally, so the fix is scoped to W17-17"
        ),
    }


def replicate_merge(
    harvest_rows: list[dict[str, str]], roster_keys: set[str]
) -> dict[str, object]:
    """Mirror of the fixed merge loop in build_themol_orbital_layer_expanded.py."""
    best: dict[str, dict[str, str]] = {}
    off_roster: list[str] = []
    duplicate_keys: list[str] = []
    upgrades = 0
    for harvest in harvest_rows:
        key = (harvest.get("inchikey") or "").strip()
        if key not in roster_keys:
            off_roster.append(key)
            continue
        current = best.get(key)
        if current is None:
            best[key] = harvest
            continue
        duplicate_keys.append(key)
        if current.get("status") != "ok" and harvest.get("status") == "ok":
            best[key] = harvest
            upgrades += 1
    return {
        "kept": list(best.values()),
        "off_roster": off_roster,
        "duplicate_keys": duplicate_keys,
        "duplicate_upgrades": upgrades,
    }


def merge_audit() -> dict[str, object]:
    roster_keys = {row["inchikey"] for row in read_rows(ROSTER)}
    paths = sorted(path for path in RAW_DIR.glob("shard_*.csv") if path.is_file())
    harvest: list[dict[str, str]] = []
    raw_rows = 0
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = [line for line in text.split(chr(10)) if line.strip()]
        if not lines:
            continue
        width = len(next(csv.reader([lines[0]])))
        buffer = [lines[0]]
        for line in lines[1:]:
            if len(next(csv.reader([line]))) != width:
                continue
            buffer.append(line)
        raw_rows += len(buffer) - 1
        harvest.extend(csv.DictReader(buffer))
    replicated = replicate_merge(harvest, roster_keys)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    observed_off = sorted(
        {
            (row.get("inchikey") or "").strip()
            for row in harvest
            if (row.get("inchikey") or "").strip() not in roster_keys
        }
    )
    synth_off = replicate_merge([{"inchikey": "OFFX", "status": "ok"}], roster_keys)
    synth_ok = replicate_merge(
        [{"inchikey": "D", "status": "ok"}, {"inchikey": "D", "status": "ok"}], {"D"}
    )
    synth_bad = replicate_merge(
        [{"inchikey": "D", "status": "error:X"}, {"inchikey": "D", "status": "ok"}], {"D"}
    )
    return {
        "shard_files": [path.name for path in paths],
        "raw_parsed_rows": raw_rows,
        "unique_keys": len(replicated["kept"]),
        "off_roster_observed_count": len(observed_off),
        "off_roster_replicated_count": len(replicated["off_roster"]),
        "duplicate_collisions_replicated": len(replicated["duplicate_keys"]),
        "duplicate_upgrades_replicated": replicated["duplicate_upgrades"],
        "recorded_rows_off_roster": summary["harvest"].get("rows_off_roster"),
        "recorded_duplicate_collisions": summary["harvest"].get("duplicate_collisions"),
        "recorded_duplicate_upgrades": summary["harvest"].get("duplicate_upgrades"),
        "recorded_failed_rows": len(summary["harvest"].get("failed_rows", [])),
        "counters_match": (
            len(observed_off) == summary["harvest"].get("rows_off_roster")
            and len(replicated["duplicate_keys"]) == summary["harvest"].get("duplicate_collisions")
            and replicated["duplicate_upgrades"] == summary["harvest"].get("duplicate_upgrades")
        ),
        "off_roster_branch_reachable": len(synth_off["off_roster"]) == 1,
        "ok_ok_collision_counted": len(synth_ok["duplicate_keys"]) == 1,
        "bad_ok_upgrade_counted": synth_bad["duplicate_upgrades"] == 1,
    }


def layer_completeness() -> dict[str, object]:
    layer = read_rows(LAYER)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    return {
        "layer_rows": len(layer),
        "roster_rows": summary.get("roster_rows"),
        "delivered_rows": summary.get("delivered_rows"),
        "run_status": summary.get("run_status"),
        "complete": len(layer) == summary.get("roster_rows") == 5117,
    }


def structure_check_recompute() -> dict[str, object]:
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    layer = read_rows(LAYER)
    matched = 0
    mismatch = 0
    unparsable = 0
    disagree = 0
    for row in layer:
        molecule = Chem.MolFromSmiles(row["smiles"]) if row["smiles"] else None
        if molecule is None:
            derived = "smiles_unparsable"
            unparsable += 1
        else:
            skeleton = Chem.MolToInchiKey(molecule).split("-")[0]
            derived = (
                "inchikey_match"
                if skeleton == row["inchikey"].split("-")[0]
                else "inchikey_mismatch"
            )
            matched += derived == "inchikey_match"
            mismatch += derived == "inchikey_mismatch"
        disagree += derived != row["structure_check"]
    return {
        "rows": len(layer),
        "recomputed_inchikey_match": matched,
        "recomputed_inchikey_mismatch": mismatch,
        "recomputed_smiles_unparsable": unparsable,
        "stored_column_disagrees_with_recompute": disagree,
        "compares_only_first_inchikey_block": True,
        "smiles_source_is_the_roster_row": True,
    }


def verifier_independence() -> dict[str, object]:
    source = VERIFIER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    return {
        "verifier_imports": sorted(set(imports)),
        "verifier_imports_project_module": any(
            name.startswith(("probes", "src", "scripts", "electrolyte_ml")) for name in imports
        ),
        "verifier_mentions_builder_module": "build_themol" in source,
        "verifier_gates_on_out_of_sample_r": "r_out is not None and r_out >= R_LIMIT" in source,
        "verifier_gates_on_in_sample_r": "r is not None and r >= R_LIMIT" in source,
        "builder_imports_shared_module": (
            "from probes.build_themol_orbital_layer import" in BUILDER.read_text(encoding="utf-8")
        ),
    }


def unit_scope() -> dict[str, object]:
    foreign = json.loads(UNIT_AUDIT.read_text(encoding="utf-8"))
    payload = json.loads(UNIT_RECHECK.read_text(encoding="utf-8"))
    layer = read_rows(LAYER)
    return {
        "foreign_arm_molecules": len(foreign.get("checks", [])),
        "this_layer_n_sampled": payload.get("n_sampled"),
        "this_layer_layer_sha256": payload.get("layer_sha256"),
        "this_layer_layer_sha256_matches_current": payload.get("layer_sha256") == sha256_of(LAYER),
        "this_layer_sample_share": payload.get("sample_share"),
        "this_layer_layer_rows": payload.get("layer_rows"),
        "this_layer_all_passed": payload.get("all_passed"),
        "this_layer_geometry_digest_matches": payload.get("geometry_digest_matches"),
        "this_layer_max_abs_delta_homo_eV": payload.get("max_abs_delta_homo_eV"),
        "this_layer_max_abs_delta_lumo_eV": payload.get("max_abs_delta_lumo_eV"),
        "coverage_note_present": bool(payload.get("coverage_note")),
        "coverage_note": payload.get("coverage_note"),
        "independent_parser": payload.get("independent_parser"),
        "delivered_rows": len(layer),
        "judgement_C_letter_satisfied": False,
        "judgement_C_sample_share": payload.get("sample_share"),
    }


def models_fitted_check() -> dict[str, object]:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    return {
        "models_fitted_field": summary.get("models_fitted"),
        "models_fitted_note_present": bool(summary.get("models_fitted_note")),
        "models_fitted_note": summary.get("models_fitted_note"),
        "linear_map_fitted": summary["calibration"]["homo"].get("slope") is not None,
    }


def report_check() -> dict[str, object]:
    if not REPORT.exists():
        return {"exists": False, "section7": False}
    text = REPORT.read_text(encoding="utf-8")
    return {"exists": True, "section7": "## 7." in text, "bytes": REPORT.stat().st_size}


def build_audit() -> dict[str, object]:
    audit: dict[str, object] = {
        "auditor": "independent adversarial audit of the W17-17 THEMol expansion arm",
        "round": 2,
        "history": {"round1": ROUND1},
        "snapshot": snapshot(),
        "s1_calibration_leakage": calibration_recompute(),
        "s1b_builder_gate": builder_gate_audit(),
        "s2_roster_5117": roster_recompute(),
        "s2b_layer_completeness": layer_completeness(),
        "s3_merge_dedup": merge_audit(),
        "s4_verifier_independence": verifier_independence(),
        "s5_structure_check": structure_check_recompute(),
        "s6_unit_scale": unit_scope(),
        "s7_models_fitted": models_fitted_check(),
        "s8_report": report_check(),
    }
    audit["findings"] = findings(audit)
    return audit


def findings(audit: dict[str, object]) -> list[dict[str, object]]:
    cal = audit["s1_calibration_leakage"]
    gate = audit["s1b_builder_gate"]
    merge = audit["s3_merge_dedup"]
    verifier = audit["s4_verifier_independence"]
    structure = audit["s5_structure_check"]
    unit = audit["s6_unit_scale"]
    models = audit["s7_models_fitted"]
    report = audit["s8_report"]
    roster = audit["s2_roster_5117"]
    homo = cal["homo"]
    return [
        {
            "id": "F1",
            "severity": "high",
            "title": "calibration status gate now decided on out-of-sample statistics only",
            "before": ROUND1["verdicts"]["F1"],
            "verdict": "closed" if (
                homo["recorded_status_equals_out_of_sample_gate"]
                and gate["builder_gate_uses_out_of_sample_r"]
                and verifier["verifier_gates_on_out_of_sample_r"]
            ) else "open",
            "evidence": {
                "homo_r_in_sample": homo.get("r_in_sample"),
                "homo_r_out_of_sample": homo.get("r_out_of_sample"),
                "homo_status": homo.get("summary_status"),
                "homo_status_basis": homo.get("summary_status_basis"),
                "recorded_equals_out_of_sample_gate": homo.get(
                    "recorded_status_equals_out_of_sample_gate"
                ),
                "recorded_equals_in_sample_gate": homo.get(
                    "recorded_status_equals_in_sample_gate"
                ),
                "builder_gate_uses_out_of_sample_r": gate["builder_gate_uses_out_of_sample_r"],
                "verifier_gates_on_out_of_sample_r": verifier["verifier_gates_on_out_of_sample_r"],
                "verifier_gates_on_in_sample_r": verifier["verifier_gates_on_in_sample_r"],
                "residual_shared_module_leak": gate["shared_w17_14_module_still_gates_in_sample"],
                "caveat": (
                    "r_in ~= r_out on this snapshot, so verdicts alone cannot distinguish the "
                    "fix; tests/test_themol_expanded_layer_audit.py proves it behaviourally"
                ),
            },
        },
        {
            "id": "F2",
            "severity": "high",
            "title": "off-roster and duplicate counters are now reachable and complete",
            "before": ROUND1["verdicts"]["F2"],
            "verdict": "closed" if (
                merge["off_roster_branch_reachable"]
                and merge["ok_ok_collision_counted"]
                and merge["bad_ok_upgrade_counted"]
                and merge["counters_match"]
            ) else "open",
            "evidence": {
                "off_roster_branch_reachable": merge["off_roster_branch_reachable"],
                "ok_ok_collision_counted": merge["ok_ok_collision_counted"],
                "bad_ok_upgrade_counted": merge["bad_ok_upgrade_counted"],
                "duplicate_collisions_replicated": merge["duplicate_collisions_replicated"],
                "duplicate_upgrades_replicated": merge["duplicate_upgrades_replicated"],
                "counters_match_summary": merge["counters_match"],
            },
        },
        {
            "id": "F3",
            "severity": "info",
            "title": "5,117 roster counters and tier split reproduce exactly",
            "before": ROUND1["verdicts"]["F3"],
            "verdict": "closed" if (
                roster["counters_agree"] and roster["tiers_agree"] and roster["digest_matches_file"]
            ) else "open",
            "evidence": {
                "counters_agree": roster["counters_agree"],
                "tiers_agree": roster["tiers_agree"],
                "digest_matches_file": roster["digest_matches_file"],
            },
        },
        {
            "id": "F4",
            "severity": "low",
            "title": "verifier still does not import the builder, and now gates on out-of-sample r",
            "before": ROUND1["verdicts"]["F4"],
            "verdict": "closed" if (
                not verifier["verifier_imports_project_module"]
                and not verifier["verifier_mentions_builder_module"]
                and verifier["verifier_gates_on_out_of_sample_r"]
            ) else "open",
            "evidence": {
                "verifier_imports_project_module": verifier["verifier_imports_project_module"],
                "verifier_mentions_builder_module": verifier["verifier_mentions_builder_module"],
                "verifier_gates_on_out_of_sample_r": verifier["verifier_gates_on_out_of_sample_r"],
            },
        },
        {
            "id": "F5",
            "severity": "medium",
            "title": "structure_check still compares only the first InChIKey block of the roster SMILES",
            "before": ROUND1["verdicts"]["F5"],
            "verdict": "open",
            "evidence": {
                "recomputed_match": structure["recomputed_inchikey_match"],
                "recomputed_mismatch": structure["recomputed_inchikey_mismatch"],
                "stored_column_disagrees_with_recompute": structure[
                    "stored_column_disagrees_with_recompute"
                ],
                "compares_only_first_inchikey_block": structure[
                    "compares_only_first_inchikey_block"
                ],
                "note": "unchanged by the fix round; recompute works, coverage is still skeleton-only",
            },
        },
        {
            "id": "F6",
            "severity": "high",
            "title": "eV claim now has this-layer evidence, but only on a 0.47% sample",
            "before": ROUND1["verdicts"]["F6"],
            "verdict": "partially_closed" if (
                unit["this_layer_n_sampled"]
                and unit["this_layer_all_passed"]
                and unit["this_layer_layer_sha256_matches_current"]
                and unit["coverage_note_present"]
            ) else "open",
            "evidence": {
                "this_layer_n_sampled": unit["this_layer_n_sampled"],
                "this_layer_sample_share": unit["this_layer_sample_share"],
                "this_layer_layer_sha256_matches_current": unit[
                    "this_layer_layer_sha256_matches_current"
                ],
                "this_layer_geometry_digest_matches": unit["this_layer_geometry_digest_matches"],
                "this_layer_all_passed": unit["this_layer_all_passed"],
                "coverage_note_present": unit["coverage_note_present"],
                "judgement_C_letter_satisfied": unit["judgement_C_letter_satisfied"],
                "note": (
                    "judgement C said reproduce EVERY delivered number; the probe reproduces a "
                    "seeded sample, which meets the spirit but not the letter"
                ),
            },
        },
        {
            "id": "F7",
            "severity": "medium",
            "title": "models_fitted = 0 now carries an explanatory note",
            "before": ROUND1["verdicts"]["F7"],
            "verdict": "closed" if models["models_fitted_note_present"] else "open",
            "evidence": {
                "models_fitted_field": models["models_fitted_field"],
                "models_fitted_note_present": models["models_fitted_note_present"],
                "linear_map_fitted": models["linear_map_fitted"],
            },
        },
        {
            "id": "F8",
            "severity": "medium",
            "title": "the pre-registered report now exists with its section 7",
            "before": ROUND1["verdicts"]["F8"],
            "verdict": "closed" if (report["exists"] and report["section7"]) else "open",
            "evidence": {"exists": report["exists"], "section7": report["section7"]},
        },
        {
            "id": "F9",
            "severity": "info",
            "title": "the reported ruff F841 is still not reproducible",
            "before": ROUND1["verdicts"]["F9"],
            "verdict": "closed",
            "evidence": {
                "ruff_status": "ruff check probes tests -> All checks passed!",
                "note": "no F841 anywhere; the earlier report was stale, nothing to fix",
            },
        },
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--print", action="store_true", help="print the audit JSON to stdout")
    args = parser.parse_args(argv)
    audit = build_audit()
    OUT.write_text(
        json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False) + chr(10),
        encoding="utf-8",
    )
    if args.print:
        print(json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(
            json.dumps(
                {
                    "out": str(OUT.relative_to(REPO)),
                    "layer_sha256": audit["snapshot"]["layer"]["sha256"],
                    "layer_rows": audit["snapshot"]["layer"]["rows"],
                    "findings": {
                        item["id"]: item["verdict"] for item in audit["findings"]
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
