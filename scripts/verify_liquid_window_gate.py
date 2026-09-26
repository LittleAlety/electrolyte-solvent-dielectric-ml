"""Offline verifier for the Week-17 liquid-window feature table and hard gate.

Run with ``--check`` to recompute everything from the committed artefacts without
touching the network.  The gate rule below is re-implemented here from the frozen
prereg instead of imported from the builder, so a change to the builder's own
rule cannot hide behind a shared function: the two must agree row for row.

Exits 0 when every check passes and 1 otherwise, and always prints a JSON body
whose first key is ``verification_passed``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.build_liquid_window_features import (
    FEATURE_COLUMNS,
    FROZEN_RED_LINES,
    GATE_COLUMNS,
    PROPERTY_SPECS,
)

IDENTITY_MAP_PATH = REPOSITORY_ROOT / "data" / "reference" / "identity_map.csv"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "liquid_window_gate_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "liquid_window_gate_summary.json"
FEATURES_PATH = REPOSITORY_ROOT / "data" / "processed" / "liquid_window_features.csv"
GATE_REPORT_PATH = REPOSITORY_ROOT / "data" / "processed" / "liquid_window_gate_report.csv"
UPSTREAM_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "pubchem_liquid_window_harvest_summary.json"

EC_INCHIKEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"
EC_MELTING_POINT_C = 36.4
TEMPERATURE_FLOOR_C = -250.0
TEMPERATURE_CEILING_C = 600.0
EXPECTED_WINDOW_C = (-20.0, 60.0)
COVERAGE_SET_SIZE = 314

# property name -> (feature prefix, summary.coverage key)
COVERAGE_KEY_BY_PROPERTY: dict[str, tuple[str, str]] = {
    "melting_point": ("mp", "keys_with_melting_point"),
    "boiling_point": ("bp", "keys_with_boiling_point"),
    "flash_point": ("flash_point", "keys_with_flash_point"),
    "density": ("density", "keys_with_density"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def gate_verdict(
    mp_c: float | None,
    bp_c: float | None,
    *,
    t_low: float,
    t_high: float,
) -> tuple[str, list[str], str]:
    """Independent re-derivation of the frozen rule (prereg.gate.rule)."""

    reasons: list[str] = []
    if mp_c is not None and mp_c > t_low:
        reasons.append("mp_above_T_low")
    if bp_c is not None and bp_c < t_high:
        reasons.append("bp_below_T_high")
    if reasons:
        return "blocked", reasons, ""
    if mp_c is not None and bp_c is not None:
        return "pass", [], ""
    missing = [
        name for name, value in (("missing_mp", mp_c), ("missing_bp", bp_c)) if value is None
    ]
    return "unknown", [], ";".join(missing)


class Checker:
    def __init__(self) -> None:
        self.checks: list[dict[str, object]] = []

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append({"name": name, "passed": bool(passed), "detail": detail})


def run_checks() -> dict[str, object]:
    checker = Checker()

    for relative, expected in FROZEN_RED_LINES.items():
        measured = sha256_file(REPOSITORY_ROOT / relative)
        checker.add(
            f"frozen_red_line_intact:{relative}",
            measured == expected,
            f"expected {expected[:12]} got {measured[:12]}",
        )

    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    t_low = float(prereg["gate"]["T_low_C"])
    t_high = float(prereg["gate"]["T_high_C"])
    checker.add(
        "prereg_locked",
        prereg.get("status") == "locked_before_run",
        f"status={prereg.get('status')!r}",
    )
    checker.add(
        "prereg_window",
        (t_low, t_high) == EXPECTED_WINDOW_C,
        f"T_low={t_low} T_high={t_high}",
    )

    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    checker.add(
        "summary_prereg_digest_matches",
        summary["prereg"]["sha256"] == sha256_file(PREREG_PATH),
        f"{summary['prereg']['sha256'][:12]}",
    )
    telemetry = summary["run_telemetry"]
    checker.add(
        "telemetry_offline",
        telemetry["network_calls"] == 0 and telemetry["run_mode"] == "offline",
        f"network_calls={telemetry['network_calls']} run_mode={telemetry['run_mode']!r}",
    )

    identity = read_rows(IDENTITY_MAP_PATH)
    features = read_rows(FEATURES_PATH)
    gate_rows = read_rows(GATE_REPORT_PATH)

    feature_keys = [row["inchikey"] for row in features]
    checker.add(
        "features_one_row_per_identity_key",
        len(features) == len(identity) == len(set(feature_keys)) == COVERAGE_SET_SIZE,
        f"identity={len(identity)} features={len(features)} unique={len(set(feature_keys))}",
    )
    checker.add(
        "features_schema",
        tuple(features[0].keys()) == FEATURE_COLUMNS,
        f"{len(features[0])} columns",
    )
    checker.add(
        "gate_report_schema",
        tuple(gate_rows[0].keys()) == GATE_COLUMNS,
        f"{len(gate_rows[0])} columns",
    )
    checker.add(
        "gate_report_matches_feature_order",
        [row["inchikey"] for row in gate_rows] == feature_keys,
        "keys must match the feature table row for row",
    )

    for path in (FEATURES_PATH, GATE_REPORT_PATH):
        checker.add(f"lf_only:{path.name}", b"\r" not in path.read_bytes(), "no CR bytes")
    for label, path in (("features", FEATURES_PATH), ("gate_report", GATE_REPORT_PATH)):
        recorded = summary["outputs"][f"data/processed/{path.name}"]
        checker.add(
            f"output_digest_matches:{label}",
            recorded["sha256"] == sha256_file(path) and recorded["bytes"] == path.stat().st_size,
            f"{recorded['sha256'][:12]} / {recorded['bytes']} bytes",
        )

    # Coverage must agree with the committed upstream harvest summary.
    upstream = json.loads(UPSTREAM_SUMMARY_PATH.read_text(encoding="utf-8"))
    for property_name, (prefix, coverage_key) in COVERAGE_KEY_BY_PROPERTY.items():
        recomputed = sum(1 for row in features if row[f"has_{prefix}"] == "true")
        upstream_count = upstream["property_coverage"][property_name]["keys_with_parsed_value"]
        checker.add(
            f"coverage_vs_summary:{property_name}",
            recomputed == summary["coverage"][coverage_key],
            f"recomputed={recomputed} summary={summary['coverage'][coverage_key]}",
        )
        checker.add(
            f"coverage_vs_upstream:{property_name}",
            recomputed == upstream_count,
            f"recomputed={recomputed} upstream={upstream_count}",
        )
    for property_name in ("melting_point", "boiling_point", "flash_point"):
        prefix = COVERAGE_KEY_BY_PROPERTY[property_name][0]
        recomputed = sum(1 for row in features if row[f"has_{prefix}"] == "true")
        checker.add(
            f"upstream_keys_with_mp_bp_fp:{property_name}",
            recomputed == upstream["keys_with_mp_bp_fp"][property_name],
            f"recomputed={recomputed}",
        )
    all_three = sum(
        1
        for row in features
        if row["has_mp"] == "true" and row["has_bp"] == "true" and row["has_flash_point"] == "true"
    )
    checker.add(
        "upstream_keys_with_all_three_temperatures",
        all_three == upstream["keys_with_all_three_temperatures"],
        f"recomputed={all_three}",
    )

    # Re-derive the verdict for every key and compare to the committed report.
    mismatches: list[str] = []
    for feature_row, gate_row in zip(features, gate_rows):
        mp_c = as_float(feature_row["mp_C"])
        bp_c = as_float(feature_row["bp_C"])
        decision, reasons, unknown_reason = gate_verdict(mp_c, bp_c, t_low=t_low, t_high=t_high)
        if (
            gate_row["gate_decision"] != decision
            or gate_row["trigger_reasons"] != ";".join(reasons)
            or gate_row["unknown_reason"] != unknown_reason
        ):
            mismatches.append(feature_row["inchikey"])
        if decision == "pass" and (mp_c is None or bp_c is None):
            mismatches.append(f"{feature_row['inchikey']}:pass_with_missing_value")
        if decision == "blocked" and not reasons:
            mismatches.append(f"{feature_row['inchikey']}:blocked_without_reason")
        if gate_row["T_low_C"] != "-20" or gate_row["T_high_C"] != "60":
            mismatches.append(f"{feature_row['inchikey']}:window_column")
    checker.add(
        "gate_verdicts_recompute",
        not mismatches,
        f"{len(mismatches)} mismatches" + (f": {mismatches[:5]}" if mismatches else ""),
    )

    decisions: dict[str, int] = {"blocked": 0, "pass": 0, "unknown": 0}
    for row in gate_rows:
        decisions[row["gate_decision"]] = decisions.get(row["gate_decision"], 0) + 1
    total = len(gate_rows)
    blocked_only = decisions["blocked"] / total
    blocked_plus_unknown = (decisions["blocked"] + decisions["unknown"]) / total
    checker.add(
        "gate_counts_match_summary", decisions == summary["gate"]["decision_counts"], f"{decisions}"
    )
    checker.add(
        "trigger_rate_blocked_only",
        abs(blocked_only - summary["gate"]["trigger_rate_blocked_only"]) < 1e-12,
        f"{blocked_only:.6f}",
    )
    checker.add(
        "trigger_rate_blocked_plus_unknown",
        abs(blocked_plus_unknown - summary["gate"]["trigger_rate_blocked_plus_unknown"]) < 1e-12,
        f"{blocked_plus_unknown:.6f}",
    )
    checker.add(
        "unknown_has_a_missing_boundary",
        all(
            (as_float(row["mp_C"]) is None or as_float(row["bp_C"]) is None)
            for row in gate_rows
            if row["gate_decision"] == "unknown"
        ),
        "every unknown key is missing at least one boundary",
    )

    # Provenance and no-averaging discipline.
    provenance_errors: list[str] = []
    range_errors: list[str] = []
    for row in features:
        for spec in PROPERTY_SPECS:
            if row[spec.has_column] != "true":
                continue
            value = as_float(row[spec.value_column])
            if value is None:
                provenance_errors.append(f"{row['inchikey']}:{spec.name}:unparsable")
                continue
            if not (row[f"{spec.prefix}_depositor"] or row[f"{spec.prefix}_reference_number"]):
                provenance_errors.append(f"{row['inchikey']}:{spec.name}:no_provenance")
            if not row[f"{spec.prefix}_selection_rule"]:
                provenance_errors.append(f"{row['inchikey']}:{spec.name}:no_selection_rule")
            if row["source_kind"] != "compilation" or row["quality_layer"] != "filter_only":
                provenance_errors.append(f"{row['inchikey']}:{spec.name}:bad_layer")
            low = as_float(row[f"{spec.prefix}_alt_min{spec.unit_suffix}"])
            high = as_float(row[f"{spec.prefix}_alt_max{spec.unit_suffix}"])
            if low is None or high is None or not (low <= value <= high):
                range_errors.append(f"{row['inchikey']}:{spec.name}")
            if spec.name != "density" and not (
                TEMPERATURE_FLOOR_C <= value <= TEMPERATURE_CEILING_C
            ):
                range_errors.append(f"{row['inchikey']}:{spec.name}:out_of_range")
    checker.add(
        "every_value_carries_provenance",
        not provenance_errors,
        f"{len(provenance_errors)} errors"
        + (f": {provenance_errors[:5]}" if provenance_errors else ""),
    )
    checker.add(
        "primary_within_alternative_range",
        not range_errors,
        f"{len(range_errors)} errors" + (f": {range_errors[:5]}" if range_errors else ""),
    )

    # EC sanity anchor.
    ec_feature = next((row for row in features if row["inchikey"] == EC_INCHIKEY), None)
    ec_gate = next((row for row in gate_rows if row["inchikey"] == EC_INCHIKEY), None)
    checker.add(
        "EC_melting_point_is_36_4",
        ec_feature is not None and as_float(ec_feature["mp_C"]) == EC_MELTING_POINT_C,
        f"mp_C={ec_feature['mp_C'] if ec_feature else None}",
    )
    checker.add(
        "EC_gate_is_blocked_on_mp",
        ec_gate is not None
        and ec_gate["gate_decision"] == "blocked"
        and ec_gate["trigger_reasons"] == "mp_above_T_low",
        f"decision={ec_gate['gate_decision'] if ec_gate else None} "
        f"reasons={ec_gate['trigger_reasons'] if ec_gate else None}",
    )
    checker.add(
        "summary_EC_sanity_matches",
        summary["sanity_checks"]["EC_is_blocked"] is True
        and summary["sanity_checks"]["EC_gate_decision"] == "blocked",
        f"{summary['sanity_checks']['EC_gate_decision']}",
    )

    # The SMARTS same-population control, recomputed when RDKit is available.
    smarts = summary["trigger_rate_comparison"]["smarts_on_same_population"]
    if smarts.get("available"):
        try:
            from electrolyte_ml.applicability import count_hbond_donors

            outside = sum(1 for row in identity if count_hbond_donors(row["smiles"]) >= 1)
            checker.add(
                "smarts_same_population_recompute",
                outside == smarts["outside_associated_liquid"],
                f"recomputed={outside} summary={smarts['outside_associated_liquid']}",
            )
        except Exception as error:  # noqa: BLE001 - RDKit may be absent here
            checker.add(
                "smarts_same_population_recompute", False, f"{type(error).__name__}: {error}"
            )
    else:
        checker.add("smarts_same_population_recompute", True, "rdkit unavailable; skipped")

    passed = all(check["passed"] for check in checker.checks)
    failures = [check["name"] for check in checker.checks if not check["passed"]]
    return {
        "verification_passed": passed,
        "checks_run": len(checker.checks),
        "checks_failed": len(failures),
        "failures": failures,
        "checks": checker.checks,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="offline recompute of every committed artefact (also the default)",
    )
    parser.add_argument("--quiet", action="store_true", help="omit the per-check detail")
    arguments = parser.parse_args(argv)

    payload = run_checks()
    if arguments.quiet:
        payload = {key: value for key, value in payload.items() if key != "checks"}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
