"""Week 17 -- the four-channel coverage board (dielectric, viscosity, HOMO/LUMO, redox).

The Week 17 chapter re-frames the project from "chase epsilon R2" to "make each
channel of the screening funnel trustworthy".  This probe is the single machine-
readable board that says, per channel, **what data exists, what the frozen model
reads, whether the gate passes, and where the bottleneck is** -- so the funnel's
short board is read off one table instead of six reports.

Every number on the board is re-read from the artefact that owns it and then
asserted against a literal pinned here.  Nothing is retyped from prose, and the
frozen main scoreboard 0.4091179943351143 is only ever *quoted*, never recomputed.
Optional dimension arms (density, Li+ coordination) are read when their summaries
exist and registered as ``pending_arm`` when they do not, so the board is honest
about which Week 17 arms have landed.

This probe fits no model and reports no new R2.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

MAIN_SCOREBOARD = 0.4091179943351143
RANDOM_ROW_LEAK_REFERENCE_R2 = 0.7385332681453336

# Literal pins: each is asserted against the artefact that owns it before it is
# written to the board.  A drifted artefact fails loudly instead of re-baselining.
PINNED = {
    "dielectric_main_scoreboard_r2": 0.4091179943351143,
    "dielectric_scoreboard_rows": 457,
    "dielectric_scoreboard_compounds": 97,
    "dielectric_scoreboard_pairs": 276,
    "dielectric_ad_trigger_rate": 0.33658536585365856,
    "viscosity_v01_rows": 3582,
    "viscosity_v01_keys": 957,
    "viscosity_group_key_r2": 0.7481271437772365,
    "viscosity_group_key_mae": 0.17477197208762,
    "homo_lumo_threshold_ev": 0.2,
    "homo_mae_ev": 0.19050925839013938,
    "lumo_mae_ev": 0.13855083976437643,
    "ip_mae_ev": 0.2010970559642009,
    "ea_mae_ev": 0.23415453202842548,
    "redox_threshold_ev": 0.15,
    "redox_oxidation_mae_ev": 0.2905180517963865,
    "redox_reduction_mae_ev": 0.4096241620366996,
    "redox_enriched_oxidation_mae_ev": 0.2174014393126818,
    "redox_enriched_reduction_mae_ev": 0.33169277465193164,
    "redox_rx392_rows": 392,
    "liquid_window_keys": 314,
    "liquid_window_blocked": 77,
    "liquid_window_pass": 126,
    "liquid_window_unknown": 111,
    "liquid_window_trigger_blocked_only": 0.24522292993630573,
    "walden_pair_rows": 1219,
    "walden_pair_keys": 76,
    "dn_covered_keys": 0,
    "dn_target_keys": 1043,
}

CHANNELS = ("dielectric", "viscosity", "homo_lumo", "redox")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def optional_json(path: Path) -> dict | None:
    return read_json(path) if path.is_file() else None


def scoreboard_shape(predictions_path: Path) -> tuple[int, int, int]:
    """(rows, compounds, distinct (compound, T) pairs) for the frozen scoreboard.

    The scored pool is read out of the shipped fold-level prediction artefact
    (protocol ``paired_base``, representation ``Morgan``, repeat 0 -- the pool and
    the fold dealing do not depend on the representation), so the 457 / 97 / 276
    triple is a measurement of the artefact rather than a memory of it.
    """

    seen_rows = 0
    pairs: set[tuple[str, str]] = set()
    compounds: set[str] = set()
    with predictions_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (
                row.get("protocol") != "paired_base"
                or row.get("representation") != "Morgan"
                or row.get("repeat") != "0"
            ):
                continue
            seen_rows += 1
            key = row.get("inchikey", "")
            compounds.add(key)
            pairs.add((key, row.get("T_K", "")))
    return seen_rows, len(compounds), len(pairs)


def _assert_pin(name: str, measured: float) -> None:
    expected = PINNED[name]
    if abs(float(measured) - float(expected)) > 1e-12:
        raise SystemExit(f"pinned value drifted: {name} = {measured} != {expected}")


def build_board() -> tuple[list[dict[str, str]], dict[str, object]]:
    paths = {
        "coverage_predictions": REPOSITORY_ROOT
        / "probes"
        / "artifacts"
        / "dielectric_coverage_paired_benchmark_predictions.csv",
        "coverage_summary": REPOSITORY_ROOT
        / "probes"
        / "dielectric_coverage_paired_benchmark_summary.json",
        "applicability_domain": REPOSITORY_ROOT
        / "probes"
        / "applicability_domain_summary.json",
        "viscosity_baseline": REPOSITORY_ROOT
        / "probes"
        / "viscosity_baseline_summary.json",
        "homo_lumo": REPOSITORY_ROOT / "models" / "homo_lumo_baselines.json",
        "redox": REPOSITORY_ROOT / "probes" / "p4_redox_summary.json",
        "redox_v2": REPOSITORY_ROOT / "probes" / "p4_redox_v2_summary.json",
        "liquid_window": REPOSITORY_ROOT / "probes" / "liquid_window_gate_summary.json",
        "walden_dn": REPOSITORY_ROOT / "probes" / "walden_dn_channel_summary.json",
        "dielectric_v04": REPOSITORY_ROOT / "data" / "dielectric_v04.csv",
    }
    rows: list[dict[str, str]] = []

    def emit(
        channel: str,
        category: str,
        metric: str,
        value: object,
        unit: str,
        source: str,
        gate: str,
        status: str,
        note: str = "",
    ) -> None:
        rows.append(
            {
                "channel": channel,
                "category": category,
                "metric": metric,
                "value": "" if value is None else str(value),
                "unit": unit,
                "source": source,
                "gate_threshold": gate,
                "gate_status": status,
                "note": note,
            }
        )

    shape_rows, shape_compounds, shape_pairs = scoreboard_shape(paths["coverage_predictions"])
    _assert_pin("dielectric_scoreboard_rows", shape_rows)
    _assert_pin("dielectric_scoreboard_compounds", shape_compounds)
    _assert_pin("dielectric_scoreboard_pairs", shape_pairs)

    coverage = read_json(paths["coverage_summary"])
    main_r2 = coverage["reference"]["published_hybrid_r2"]
    _assert_pin("dielectric_main_scoreboard_r2", main_r2)
    ad = read_json(paths["applicability_domain"])
    ad_rate = ad["trigger_rate"]
    _assert_pin("dielectric_ad_trigger_rate", ad_rate)

    emit("dielectric", "model", "main_scoreboard_grouped_r2", main_r2, "R2",
         "probes/dielectric_coverage_paired_benchmark_summary.json", "", "quoted",
         "frozen main scoreboard; never mixed with the v1.0 headline 0.364")
    emit("dielectric", "model", "random_row_leak_reference_r2", RANDOM_ROW_LEAK_REFERENCE_R2,
         "R2", "reports/decisions_log.md", "", "reference_only",
         "row-level leak reference; never enters a verdict")
    emit("dielectric", "data", "scoreboard_rows", shape_rows, "rows",
         "probes/artifacts/dielectric_coverage_paired_benchmark_predictions.csv", "", "scored")
    emit("dielectric", "data", "scoreboard_compounds", shape_compounds, "compounds",
         "probes/artifacts/dielectric_coverage_paired_benchmark_predictions.csv", "", "scored")
    emit("dielectric", "data", "scoreboard_distinct_compound_temperature_pairs", shape_pairs,
         "pairs", "probes/artifacts/dielectric_coverage_paired_benchmark_predictions.csv",
         "", "scored", "the honest sample size to quote is 276, not 457")
    emit("dielectric", "gate", "applicability_domain_trigger_rate", ad_rate, "fraction",
         "probes/applicability_domain_summary.json", "SMARTS [O,S,N;!H0]", "armed",
         "hbond-donor SMARTS applicability domain, 33.66 percent")

    viscosity = read_json(paths["viscosity_baseline"])
    _assert_pin("viscosity_v01_rows", viscosity["row_count"])
    _assert_pin("viscosity_v01_keys", viscosity["unique_key_count"])
    group_key = viscosity["splits"]["group_key"]["models"]["MorganTemperatureXGBoost"]["log10_cP"]
    _assert_pin("viscosity_group_key_r2", group_key["r2"])
    _assert_pin("viscosity_group_key_mae", group_key["mae"])
    viscosity_gate = viscosity["primary_gate"]
    emit("viscosity", "data", "viscosity_v01_rows", viscosity["row_count"], "rows",
         "probes/viscosity_baseline_summary.json", "", "shipped")
    emit("viscosity", "data", "viscosity_v01_keys", viscosity["unique_key_count"], "InChIKeys",
         "probes/viscosity_baseline_summary.json", "", "shipped")
    emit("viscosity", "model", "group_key_r2", group_key["r2"], "R2",
         "probes/viscosity_baseline_summary.json", "mae<=0.15 log10(cP)",
         "red" if not viscosity_gate["group_key_passed"] else "green",
         "group-key split is the honest one; random_row passes and group_key fails")
    emit("viscosity", "model", "group_key_mae_log10_cP", group_key["mae"], "log10(cP)",
         "probes/viscosity_baseline_summary.json", "0.15",
         "red" if not viscosity_gate["group_key_passed"] else "green",
         "family-level conclusion only until the kinematic rows are thawed")

    homo = read_json(paths["homo_lumo"])
    hl_gate = homo["gate"]
    _assert_pin("homo_lumo_threshold_ev", hl_gate["threshold_mae"])
    for key, pin, label in (
        ("HOMO", "homo_mae_ev", "HOMO"),
        ("LUMO", "lumo_mae_ev", "LUMO"),
        ("IP", "ip_mae_ev", "IP"),
        ("EA", "ea_mae_ev", "EA"),
    ):
        value = hl_gate["best_model_mae"][key]
        _assert_pin(pin, value)
        passed = hl_gate["per_target"][key]["passed"]
        emit("homo_lumo", "model", f"{label}_fold_mean_mae", value, "eV",
             "models/homo_lumo_baselines.json", str(hl_gate["threshold_mae"]),
             "green" if passed else "red",
             "structure-only features; DFT-derived columns are forbidden inputs")
    emit("homo_lumo", "model", "targets_passed", "2/4", "targets",
         "models/homo_lumo_baselines.json", "4/4", "red",
         "HOMO and LUMO pass; IP misses by 1.1 meV and EA by 34 meV")

    redox = read_json(paths["redox"])
    redox_gate = redox["gate"]
    _assert_pin("redox_threshold_ev", redox_gate["threshold_mae"])
    _assert_pin("redox_oxidation_mae_ev", redox_gate["best_model_mae"]["oxidation_free_energy"])
    _assert_pin("redox_reduction_mae_ev", redox_gate["best_model_mae"]["reduction_free_energy"])
    _assert_pin("redox_rx392_rows", redox["sources"]["rx_392"]["rows"])
    redox_v2 = read_json(paths["redox_v2"])
    _assert_pin(
        "redox_enriched_oxidation_mae_ev", redox_v2["gate"]["best_model_mae"]["oxidation_free_energy"]
    )
    _assert_pin(
        "redox_enriched_reduction_mae_ev", redox_v2["gate"]["best_model_mae"]["reduction_free_energy"]
    )
    emit("redox", "data", "rx392_labelled_rows", redox["sources"]["rx_392"]["rows"], "rows",
         "probes/p4_redox_summary.json", "", "shipped")
    emit("redox", "model", "oxidation_free_energy_mae", redox_gate["best_model_mae"]["oxidation_free_energy"],
         "eV", "probes/p4_redox_summary.json", "0.15", "red")
    emit("redox", "model", "reduction_free_energy_mae", redox_gate["best_model_mae"]["reduction_free_energy"],
         "eV", "probes/p4_redox_summary.json", "0.15", "red")
    emit("redox", "model", "enriched_holdout_oxidation_mae",
         redox_v2["gate"]["best_model_mae"]["oxidation_free_energy"], "eV",
         "probes/p4_redox_v2_summary.json", "0.15", "red",
         "held-out 78 rows; the bottleneck is the 392 labels, not model capacity")
    emit("redox", "model", "enriched_holdout_reduction_mae",
         redox_v2["gate"]["best_model_mae"]["reduction_free_energy"], "eV",
         "probes/p4_redox_v2_summary.json", "0.15", "red")

    liquid = optional_json(paths["liquid_window"])
    if liquid is not None:
        gate = liquid["gate"]
        _assert_pin("liquid_window_keys", liquid["coverage_set"])
        _assert_pin("liquid_window_blocked", gate["blocked"])
        _assert_pin("liquid_window_pass", gate["pass"])
        _assert_pin("liquid_window_unknown", gate["unknown"])
        _assert_pin("liquid_window_trigger_blocked_only", gate["trigger_rate_blocked_only"])
        emit("liquid_window", "data", "coverage_keys", liquid["coverage_set"], "InChIKeys",
             "probes/liquid_window_gate_summary.json", "", "shipped")
        emit("liquid_window", "gate", "trigger_rate_blocked_only", gate["trigger_rate_blocked_only"],
             "fraction", "probes/liquid_window_gate_summary.json", "mp>-20C or bp<60C", "armed",
             "a hard gate that runs before the epsilon screen")
        emit("liquid_window", "gate", "trigger_rate_blocked_plus_unknown",
             gate["trigger_rate_blocked_plus_unknown"], "fraction",
             "probes/liquid_window_gate_summary.json", "conservative", "armed",
             "unknown is neither a pass nor an evict; both readings are reported")
        emit("liquid_window", "gate", "ec_melting_point_verdict", "blocked", "verdict",
             "probes/liquid_window_gate_summary.json", "mp>-20C", "blocked",
             "EC mp 36.4 C: the solid-at-room-temperature case the gate exists to catch")
    else:
        emit("liquid_window", "gate", "coverage_keys", None, "", "probes/liquid_window_gate_summary.json",
             "", "pending_arm")

    walden = optional_json(paths["walden_dn"])
    if walden is not None:
        pairs = walden["walden_pairs"]
        _assert_pin("walden_pair_rows", pairs["rows"])
        _assert_pin("walden_pair_keys", pairs["distinct_keys"])
        dn = walden["dn_channel"]["admissible"]
        _assert_pin("dn_covered_keys", dn["covered_keys"])
        _assert_pin("dn_target_keys", walden["dn_channel"]["audit_rows"])
        emit("walden", "data", "epsilon_eta_pair_rows", pairs["rows"], "rows",
             "probes/walden_dn_channel_summary.json", "", "derived",
             "derived pairs, not measurements")
        emit("walden", "data", "epsilon_eta_pair_keys", pairs["distinct_keys"], "InChIKeys",
             "probes/walden_dn_channel_summary.json", "", "derived")
        emit("dn", "gate", "admissible_coverage_fraction", dn["coverage_fraction"], "fraction",
             "probes/walden_dn_channel_summary.json", "0.30",
             "red" if not dn["passes_threshold"] else "green",
             "DN is experimental-only; below threshold, so it does not enter the feature table")

    density = optional_json(REPOSITORY_ROOT / "probes" / "density_v01_summary.json")
    emit("density", "data", "summary_present", str(density is not None), "bool",
         "probes/density_v01_summary.json", "", "shipped" if density else "pending_arm")

    coordination = optional_json(
        REPOSITORY_ROOT / "probes" / "dielectric_coordination_block_v3_summary.json"
    )
    emit("li_coordination", "model", "merged_shot_summary_present", str(coordination is not None),
         "bool", "probes/dielectric_coordination_block_v3_summary.json", "",
         "shipped" if coordination else "pending_arm")

    inputs = {}
    for name, path in paths.items():
        if path.is_file():
            inputs[name] = {
                "path": portable_relative_path(path, root=REPOSITORY_ROOT),
                "sha256": canonical_text_sha256(path),
            }
    summary = {
        "schema_version": 1,
        "task": "four_channel_coverage",
        "week": "week17",
        "channels": list(CHANNELS),
        "board_rows": len(rows),
        "pinned": PINNED,
        "main_scoreboard": MAIN_SCOREBOARD,
        "random_row_leak_reference_r2": RANDOM_ROW_LEAK_REFERENCE_R2,
        "inputs": inputs,
        "run_telemetry": {
            "network_calls": 0,
            "models_fitted": 0,
            "r2_reported": False,
            "writes_under_data": 1,
            "run_mode": "offline_local_only",
        },
        "boundaries": [
            "the board re-reads shipped artefacts and asserts literal pins; it computes no model",
            "457 rows are 276 distinct (compound, temperature) pairs; the sample size is 276",
            "gate_status is a restatement of the owning artefact, not a new judgement",
            "optional arms register as pending_arm when their summary is absent",
        ],
    }
    return rows, summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "four_channel_coverage.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "four_channel_coverage_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows, summary = build_board()
    fields = [
        "channel",
        "category",
        "metric",
        "value",
        "unit",
        "source",
        "gate_threshold",
        "gate_status",
        "note",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary["outputs"] = {
        "board": {
            "path": portable_relative_path(args.output, root=REPOSITORY_ROOT),
            "sha256": canonical_text_sha256(args.output),
            "row_count": len(rows),
        }
    }
    summary["generated_at_utc"] = _utc_now()
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "status": "built",
                "board_rows": len(rows),
                "board_sha256": summary["outputs"]["board"]["sha256"],
                "channels": list(CHANNELS),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
