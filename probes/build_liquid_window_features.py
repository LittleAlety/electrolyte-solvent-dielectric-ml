"""Week-17 arm W17-5: promote the AD-1 liquid-window harvest into features + a hard gate.

AD-1 (``probes/pubchem_liquid_window_harvest.py``) harvested the melting point,
boiling point, flash point and density of the 314-key coverage set from PubChem
PUG-REST.  This builder turns that harvest into the funnel's two artefacts:

* ``data/processed/liquid_window_features.csv`` -- one row per InChIKey carrying
  the four properties, each with its own provenance (depositor, reference
  number, raw text, unit), a confidence tier and a ``has_*`` flag.
* ``data/processed/liquid_window_gate_report.csv`` -- one row per InChIKey with
  the hard-gate verdict, the trigger reason and the columns the verdict read.

The gate (window, rule, unknown policy, trigger-rate reporting) is frozen in
``probes/liquid_window_gate_prereg.json`` *before* this script ever runs.  The
thresholds are read back from that file rather than re-typed here, so the frozen
statement and the code cannot drift apart.

What the gate says
    A pure substance is a liquid strictly between its melting point and its
    boiling point.  For it to stay liquid across the working window it must not
    freeze at the cold end (``mp_C > T_low_C`` is a failure) and must not boil at
    the hot end (``bp_C < T_high_C`` is a failure).  Either clause alone evicts.
    A missing value is never defaulted to pass and never defaulted to evict: the
    key is labelled ``unknown`` and reported under both trigger-rate readings.

Discipline
    * Offline.  The only inputs are the cached harvest tables, the committed
      upstream summary and the identity map; ``network_calls`` is 0 by
      construction and there is no HTTP code in this module.
    * No averaging.  Where depositors disagree the primary value keeps its own
      provenance and the disagreement is recorded as a count plus a min/max
      range, never smeared into a mean.
    * No silent promotion.  Values stay ``source_kind="compilation"`` /
      ``quality_layer="filter_only"``: they screen and rank, they are not
      first-hand citable core values.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

IDENTITY_MAP_PATH = REPOSITORY_ROOT / "data" / "reference" / "identity_map.csv"
HARVEST_DIR = REPOSITORY_ROOT / "data" / "external" / "g1plus" / "pubchem" / "liquid_window"
SELECTED_PATH = HARVEST_DIR / "liquid_window_selected.csv"
VALUES_PATH = HARVEST_DIR / "liquid_window_values.csv"
UPSTREAM_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "pubchem_liquid_window_harvest_summary.json"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "liquid_window_gate_prereg.json"
FEATURES_PATH = REPOSITORY_ROOT / "data" / "processed" / "liquid_window_features.csv"
GATE_REPORT_PATH = REPOSITORY_ROOT / "data" / "processed" / "liquid_window_gate_report.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "liquid_window_gate_summary.json"

SOURCE_KIND = "compilation"
QUALITY_LAYER = "filter_only"

SMARTS_REFERENCE_TRIGGER_RATE = 0.33658536585365856
SMARTS_REFERENCE_SOURCE = "probes/applicability_domain_summary.json"
SMARTS_REFERENCE_RULE = "hbond_donor_count >= 1 => outside_associated_liquid"

EC_INCHIKEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"
EC_MELTING_POINT_C = 36.4

# The six frozen red-line artefacts this arm must leave byte-identical.
FROZEN_RED_LINES: dict[str, str] = {
    "data/dielectric_v03.csv": ("ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"),
    "data/processed/dielectric_observations_v11plus.csv": (
        "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9"
    ),
    "data/viscosity_v01.csv": ("12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26"),
    "probes/l3_stage1_pilot_pool.csv": (
        "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"
    ),
    "probes/l3_backvalidation_prereg.json": (
        "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98"
    ),
    "probes/dielectric_r2_levers_prereg.json": (
        "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa"
    ),
}


@dataclass(frozen=True, slots=True)
class PropertySpec:
    """How one harvested property becomes one block of feature columns."""

    name: str
    prefix: str
    value_column: str
    has_column: str
    unit_suffix: str
    tolerance: float
    relative_tolerance: bool = False


MELTING = PropertySpec("melting_point", "mp", "mp_C", "has_mp", "_C", 2.0)
BOILING = PropertySpec("boiling_point", "bp", "bp_C", "has_bp", "_C", 2.0)
FLASH = PropertySpec("flash_point", "flash_point", "flash_point_C", "has_flash_point", "_C", 2.0)
DENSITY = PropertySpec("density", "density", "density_g_cm3", "has_density", "", 0.02, True)
TEMPERATURE_SPECS: tuple[PropertySpec, ...] = (MELTING, BOILING, FLASH)
PROPERTY_SPECS: tuple[PropertySpec, ...] = (MELTING, BOILING, FLASH, DENSITY)

FEATURE_COLUMNS: tuple[str, ...] = (
    ("inchikey", "name", "pubchem_cid")
    + tuple(
        column
        for spec in PROPERTY_SPECS
        for column in (
            spec.value_column,
            f"{spec.prefix}_unit",
            f"{spec.prefix}_raw",
            f"{spec.prefix}_depositor",
            f"{spec.prefix}_reference_number",
            f"{spec.prefix}_selection_rule",
            f"{spec.prefix}_peer_reviewed",
            f"{spec.prefix}_confidence",
            f"{spec.prefix}_conflict",
            f"{spec.prefix}_n_values",
            f"{spec.prefix}_n_parsed",
            f"{spec.prefix}_alt_min{spec.unit_suffix}",
            f"{spec.prefix}_alt_max{spec.unit_suffix}",
            spec.has_column,
        )
    )
    + ("density_subtype", "density_is_absolute_g_cm3", "source_kind", "quality_layer")
)

GATE_COLUMNS: tuple[str, ...] = (
    "inchikey",
    "name",
    "pubchem_cid",
    "gate_decision",
    "trigger_reasons",
    "unknown_reason",
    "evidence_columns",
    "mp_C",
    "mp_C_depositor",
    "mp_C_confidence",
    "bp_C",
    "bp_C_depositor",
    "bp_C_confidence",
    "T_low_C",
    "T_high_C",
)


# --------------------------------------------------------------------------
# Small helpers.
# --------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: Sequence[Mapping[str, str]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _format_number(value: float | None) -> str:
    if value is None:
        return ""
    number = round(float(value), 4)
    if number == int(number):
        return str(int(number))
    return str(number)


def _as_float(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def load_prereg(path: Path) -> tuple[float, float, dict[str, object]]:
    """Read the frozen window from the prereg, refusing an unlocked file."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "locked_before_run":
        raise ValueError(f"prereg {path} is not locked_before_run: {payload.get('status')!r}")
    gate = payload["gate"]
    return float(gate["T_low_C"]), float(gate["T_high_C"]), payload


# --------------------------------------------------------------------------
# Feature construction.
# --------------------------------------------------------------------------


def load_selected(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    return {(row["inchikey"], row["property"]): row for row in read_csv_rows(path)}


def group_parsed_values(
    path: Path,
) -> dict[tuple[str, str], list[float]]:
    grouped: dict[tuple[str, str], list[float]] = {}
    for row in read_csv_rows(path):
        value = _as_float(row["value_numeric"])
        if value is None:
            continue
        grouped.setdefault((row["inchikey"], row["property"]), []).append(value)
    return grouped


def group_row_counts(path: Path) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for row in read_csv_rows(path):
        key = (row["inchikey"], row["property"])
        counts[key] = counts.get(key, 0) + 1
    return counts


def confidence_and_spread(
    values: Sequence[float],
    *,
    primary_peer_reviewed: bool,
    spec: PropertySpec,
) -> tuple[str, bool, float | None, float | None]:
    """Confidence tier, conflict flag and the range of parsed alternatives.

    Agreement (two or more parsed values within tolerance) corroborates a
    peer-reviewed primary and raises it to ``high``.  A wider spread is a
    ``conflict`` and is reported separately; it never rewrites the primary.
    """

    if not values:
        return "absent", False, None, None
    ordered = sorted(values)
    low, high = ordered[0], ordered[-1]
    if spec.relative_tolerance:
        midpoint = abs((low + high) / 2.0)
        spread = abs(high - low) / midpoint if midpoint else abs(high - low)
    else:
        spread = abs(high - low)
    agrees = len(ordered) >= 2 and spread <= spec.tolerance
    conflict = len(ordered) >= 2 and spread > spec.tolerance
    if primary_peer_reviewed and agrees:
        tier = "high"
    elif primary_peer_reviewed:
        tier = "medium"
    else:
        tier = "low"
    return tier, conflict, low, high


def build_feature_row(
    target: Mapping[str, str],
    selected: Mapping[tuple[str, str], dict[str, str]],
    parsed: Mapping[tuple[str, str], list[float]],
    row_counts: Mapping[tuple[str, str], int],
) -> dict[str, str]:
    inchikey = target["inchikey"]
    row: dict[str, str] = {
        "inchikey": inchikey,
        "name": target["name"],
        "pubchem_cid": target["pubchem_cid"],
        "source_kind": SOURCE_KIND,
        "quality_layer": QUALITY_LAYER,
    }
    for spec in PROPERTY_SPECS:
        key = (inchikey, spec.name)
        primary_row = selected.get(key)
        values = parsed.get(key, [])
        row[f"{spec.prefix}_n_values"] = str(row_counts.get(key, 0))
        row[f"{spec.prefix}_n_parsed"] = str(len(values))
        row[f"{spec.prefix}_alt_min{spec.unit_suffix}"] = ""
        row[f"{spec.prefix}_alt_max{spec.unit_suffix}"] = ""
        if primary_row is None:
            row[spec.value_column] = ""
            row[f"{spec.prefix}_unit"] = ""
            row[f"{spec.prefix}_raw"] = ""
            row[f"{spec.prefix}_depositor"] = ""
            row[f"{spec.prefix}_reference_number"] = ""
            row[f"{spec.prefix}_selection_rule"] = ""
            row[f"{spec.prefix}_peer_reviewed"] = ""
            row[f"{spec.prefix}_confidence"] = "absent"
            row[f"{spec.prefix}_conflict"] = "false"
            row[spec.has_column] = "false"
        else:
            peer_reviewed = primary_row["peer_reviewed"] == "true"
            tier, conflict, low, high = confidence_and_spread(
                values, primary_peer_reviewed=peer_reviewed, spec=spec
            )
            row[spec.value_column] = primary_row["value_numeric"]
            row[f"{spec.prefix}_unit"] = primary_row["unit"]
            row[f"{spec.prefix}_raw"] = primary_row["value_raw"]
            row[f"{spec.prefix}_depositor"] = primary_row["depositor"]
            row[f"{spec.prefix}_reference_number"] = primary_row["reference_number"]
            row[f"{spec.prefix}_selection_rule"] = primary_row["selection_rule"]
            row[f"{spec.prefix}_peer_reviewed"] = primary_row["peer_reviewed"]
            row[f"{spec.prefix}_confidence"] = tier
            row[f"{spec.prefix}_conflict"] = "true" if conflict else "false"
            row[f"{spec.prefix}_alt_min{spec.unit_suffix}"] = _format_number(low)
            row[f"{spec.prefix}_alt_max{spec.unit_suffix}"] = _format_number(high)
            row[spec.has_column] = "true"
        if spec is DENSITY:
            row["density_subtype"] = primary_row["subtype"] if primary_row else ""
            row["density_is_absolute_g_cm3"] = (
                "true"
                if primary_row is not None and primary_row["subtype"] == "absolute"
                else "false"
            )
    return row


def build_gate_row(
    feature_row: Mapping[str, str],
    *,
    t_low: float,
    t_high: float,
) -> dict[str, str]:
    mp_c = _as_float(feature_row["mp_C"])
    bp_c = _as_float(feature_row["bp_C"])
    reasons: list[str] = []
    if mp_c is not None and mp_c > t_low:
        reasons.append("mp_above_T_low")
    if bp_c is not None and bp_c < t_high:
        reasons.append("bp_below_T_high")
    if reasons:
        decision = "blocked"
        unknown_reason = ""
    elif mp_c is not None and bp_c is not None:
        decision = "pass"
        unknown_reason = ""
    else:
        decision = "unknown"
        missing = []
        if mp_c is None:
            missing.append("missing_mp")
        if bp_c is None:
            missing.append("missing_bp")
        unknown_reason = ";".join(missing)
    evidence = [column for column, value in (("mp_C", mp_c), ("bp_C", bp_c)) if value is not None]
    return {
        "inchikey": feature_row["inchikey"],
        "name": feature_row["name"],
        "pubchem_cid": feature_row["pubchem_cid"],
        "gate_decision": decision,
        "trigger_reasons": ";".join(reasons),
        "unknown_reason": unknown_reason,
        "evidence_columns": ";".join(evidence),
        "mp_C": feature_row["mp_C"],
        "mp_C_depositor": feature_row["mp_depositor"],
        "mp_C_confidence": feature_row["mp_confidence"],
        "bp_C": feature_row["bp_C"],
        "bp_C_depositor": feature_row["bp_depositor"],
        "bp_C_confidence": feature_row["bp_confidence"],
        "T_low_C": _format_number(t_low),
        "T_high_C": _format_number(t_high),
    }


def smarts_trigger_on_population(
    targets: Sequence[Mapping[str, str]],
) -> dict[str, object]:
    """Recompute the applicability-domain SMARTS gate on the same keys.

    A same-population comparison so the two gates are not only contrasted
    against the historical 33.66% row-level figure.  Returns an ``available``
    false payload if RDKit is absent rather than guessing.
    """

    try:
        from electrolyte_ml.applicability import count_hbond_donors
    except Exception as error:  # noqa: BLE001 - RDKit may be absent here
        return {"available": False, "reason": f"{type(error).__name__}: {error}"}
    inside = 0
    outside = 0
    unresolved: list[str] = []
    for target in targets:
        try:
            donors = count_hbond_donors(target["smiles"])
        except Exception:  # noqa: BLE001 - an unparsable SMILES is data, not a crash
            unresolved.append(target["inchikey"])
            continue
        if donors >= 1:
            outside += 1
        else:
            inside += 1
    total = inside + outside
    return {
        "available": True,
        "rule": SMARTS_REFERENCE_RULE,
        "keys": len(targets),
        "resolved": total,
        "inside_domain": inside,
        "outside_associated_liquid": outside,
        "trigger_rate_on_resolved": (outside / total) if total else None,
        "unresolved": len(unresolved),
        "unresolved_keys": unresolved,
    }


def _counter(values: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _file_fingerprint(path: Path) -> dict[str, object]:
    return {"bytes": path.stat().st_size, "sha256": sha256_file(path)}


def check_frozen_red_lines() -> dict[str, dict[str, object]]:
    report: dict[str, dict[str, object]] = {}
    for relative, expected in FROZEN_RED_LINES.items():
        path = REPOSITORY_ROOT / relative
        measured = sha256_file(path)
        report[relative] = {
            "expected": expected,
            "measured": measured,
            "intact": measured == expected,
        }
    return report


# --------------------------------------------------------------------------
# Summary.
# --------------------------------------------------------------------------


def build_summary(
    *,
    targets: Sequence[Mapping[str, str]],
    features: Sequence[Mapping[str, str]],
    gate_rows: Sequence[Mapping[str, str]],
    prereg: Mapping[str, object],
    t_low: float,
    t_high: float,
    upstream_summary: Mapping[str, object],
    smarts: Mapping[str, object],
    generated_at: str,
) -> dict[str, object]:
    property_coverage = {}
    confidence_counts = {}
    for spec in PROPERTY_SPECS:
        keys_with_value = sum(1 for row in features if row[spec.has_column] == "true")
        property_coverage[spec.name] = {
            "value_column": spec.value_column,
            "keys_total": len(features),
            "keys_with_value": keys_with_value,
            "keys_without_value": len(features) - keys_with_value,
        }
        confidence_counts[spec.name] = _counter(
            [row[f"{spec.prefix}_confidence"] for row in features]
        )

    def _keys_with(prefix: str) -> int:
        return sum(1 for row in features if row[f"has_{prefix}"] == "true")

    decisions = _counter([row["gate_decision"] for row in gate_rows])
    blocked = decisions.get("blocked", 0)
    passed = decisions.get("pass", 0)
    unknown = decisions.get("unknown", 0)
    total = len(gate_rows)
    reason_counts = _counter(
        [reason for row in gate_rows for reason in row["trigger_reasons"].split(";") if reason]
    )
    unknown_counts = _counter([row["unknown_reason"] for row in gate_rows if row["unknown_reason"]])
    blocked_only = (blocked / total) if total else None
    blocked_plus_unknown = ((blocked + unknown) / total) if total else None
    ratio = (
        blocked_plus_unknown / SMARTS_REFERENCE_TRIGGER_RATE
        if blocked_plus_unknown is not None and SMARTS_REFERENCE_TRIGGER_RATE
        else None
    )

    all_temperatures = sum(
        1
        for row in features
        if row["has_mp"] == "true" and row["has_bp"] == "true" and row["has_flash_point"] == "true"
    )
    any_liquid_window_value = sum(
        1 for row in features if any(row[spec.has_column] == "true" for spec in PROPERTY_SPECS)
    )
    ec_row = next((row for row in gate_rows if row["inchikey"] == EC_INCHIKEY), None)

    return {
        "schema_version": 1,
        "task": "week17_liquid_window_gate",
        "arm": "W17-5",
        "run_telemetry": {
            "generated_at_utc": generated_at,
            "network_calls": 0,
            "models_fitted": 0,
            "r2_reported": False,
            "writes_under_data": 2,
            "run_mode": "offline",
        },
        "prereg": {
            "path": "probes/liquid_window_gate_prereg.json",
            "sha256": sha256_file(PREREG_PATH),
            "status": prereg["status"],
            "T_low_C": t_low,
            "T_high_C": t_high,
            "rule": prereg["gate"]["rule"],
            "unknown_policy": prereg["gate"]["unknown_policy"],
        },
        "inputs": {
            "data/reference/identity_map.csv": _file_fingerprint(IDENTITY_MAP_PATH),
            "data/external/g1plus/pubchem/liquid_window/liquid_window_selected.csv": (
                _file_fingerprint(SELECTED_PATH)
            ),
            "data/external/g1plus/pubchem/liquid_window/liquid_window_values.csv": (
                _file_fingerprint(VALUES_PATH)
            ),
            "probes/pubchem_liquid_window_harvest_summary.json": _file_fingerprint(
                UPSTREAM_SUMMARY_PATH
            ),
        },
        "coverage_set": len(features),
        "coverage": {
            "keys_with_melting_point": _keys_with("mp"),
            "keys_with_boiling_point": _keys_with("bp"),
            "keys_with_flash_point": _keys_with("flash_point"),
            "keys_with_density": _keys_with("density"),
            "keys_with_density_absolute": sum(
                1 for row in features if row["density_is_absolute_g_cm3"] == "true"
            ),
            "keys_with_any_liquid_window_value": any_liquid_window_value,
            "keys_with_no_liquid_window_value": len(features) - any_liquid_window_value,
            "keys_with_all_three_temperatures": all_temperatures,
        },
        "upstream_agreement": {
            "upstream_network_calls": upstream_summary.get("network_calls"),
            "upstream_keys_with_all_three_temperatures": upstream_summary.get(
                "keys_with_all_three_temperatures"
            ),
            "upstream_keys_with_mp_bp_fp": upstream_summary.get("keys_with_mp_bp_fp"),
            "builder_keys_with_all_three_temperatures": all_temperatures,
        },
        "property_coverage": property_coverage,
        "confidence_counts": confidence_counts,
        "gate": {
            "T_low_C": t_low,
            "T_high_C": t_high,
            "rule": prereg["gate"]["rule"],
            "population": "the 314-key coverage set (data/reference/identity_map.csv)",
            "decision_counts": decisions,
            "blocked_reason_counts": reason_counts,
            "unknown_reason_counts": unknown_counts,
            "trigger_rate_blocked_only": blocked_only,
            "trigger_rate_blocked_plus_unknown": blocked_plus_unknown,
            "blocked": blocked,
            "pass": passed,
            "unknown": unknown,
            "total": total,
        },
        "trigger_rate_comparison": {
            "smarts_reference_rate": SMARTS_REFERENCE_TRIGGER_RATE,
            "smarts_reference_source": SMARTS_REFERENCE_SOURCE,
            "smarts_reference_note": (
                "row-level rate on the 6,150 out-of-fold model rows; a different "
                "population from the 314 unique candidate keys here"
            ),
            "liquid_window_blocked_only": blocked_only,
            "liquid_window_blocked_plus_unknown": blocked_plus_unknown,
            "ratio_blocked_plus_unknown_over_smarts": ratio,
            "within_an_order_of_magnitude": (ratio is not None and (1 / 10.0) <= ratio <= 10.0),
            "smarts_on_same_population": dict(smarts),
        },
        "sanity_checks": {
            "EC_inchikey": EC_INCHIKEY,
            "EC_melting_point_C": EC_MELTING_POINT_C,
            "EC_gate_decision": ec_row["gate_decision"] if ec_row else None,
            "EC_trigger_reasons": ec_row["trigger_reasons"] if ec_row else None,
            "EC_mp_C_in_features": next(
                (row["mp_C"] for row in features if row["inchikey"] == EC_INCHIKEY), None
            ),
            "EC_is_blocked": bool(ec_row is not None and ec_row["gate_decision"] == "blocked"),
            "reaxys_lesson": (
                "EC mp 36.4 degC means 25 degC is not liquid; any temperature label "
                "must be cross-checked against the compound's liquid window"
            ),
        },
        "frozen_red_lines": check_frozen_red_lines(),
        "outputs": {
            "data/processed/liquid_window_features.csv": {
                "rows": len(features),
                **_file_fingerprint(FEATURES_PATH),
            },
            "data/processed/liquid_window_gate_report.csv": {
                "rows": len(gate_rows),
                **_file_fingerprint(GATE_REPORT_PATH),
            },
        },
        "caveats": [
            (
                "The gate judges a *pure* candidate compound.  A co-solvent that is "
                "solid or volatile on its own can still be useful in a blend; the "
                "gate is the funnel's pure-component unit and blend engineering is "
                "downstream."
            ),
            (
                "Unknown is neither a pass nor an evict.  Both trigger-rate readings "
                "are reported so the reader can see the cost of the missing values."
            ),
            (
                "Values are depot compilations (source_kind=compilation, "
                "quality_layer=filter_only); they screen and rank but are not "
                "first-hand citable core values."
            ),
        ],
    }


# --------------------------------------------------------------------------
# Entry point.
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--identity-map", type=Path, default=IDENTITY_MAP_PATH)
    parser.add_argument("--selected", type=Path, default=SELECTED_PATH)
    parser.add_argument("--values", type=Path, default=VALUES_PATH)
    parser.add_argument("--prereg", type=Path, default=PREREG_PATH)
    parser.add_argument("--upstream-summary", type=Path, default=UPSTREAM_SUMMARY_PATH)
    parser.add_argument("--features", type=Path, default=FEATURES_PATH)
    parser.add_argument("--gate-report", type=Path, default=GATE_REPORT_PATH)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)

    t_low, t_high, prereg = load_prereg(arguments.prereg)
    targets = read_csv_rows(arguments.identity_map)
    selected = load_selected(arguments.selected)
    parsed = group_parsed_values(arguments.values)
    row_counts = group_row_counts(arguments.values)

    features = [build_feature_row(target, selected, parsed, row_counts) for target in targets]
    gate_rows = [build_gate_row(row, t_low=t_low, t_high=t_high) for row in features]

    upstream = json.loads(arguments.upstream_summary.read_text(encoding="utf-8"))
    smarts = smarts_trigger_on_population(targets)
    generated_at = _utc_now()

    if not arguments.dry_run:
        write_rows(arguments.features, features, FEATURE_COLUMNS)
        write_rows(arguments.gate_report, gate_rows, GATE_COLUMNS)

    summary = build_summary(
        targets=targets,
        features=features,
        gate_rows=gate_rows,
        prereg=prereg,
        t_low=t_low,
        t_high=t_high,
        upstream_summary=upstream,
        smarts=smarts,
        generated_at=generated_at,
    )
    if not arguments.dry_run:
        arguments.summary.parent.mkdir(parents=True, exist_ok=True)
        with open(arguments.summary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    print(json.dumps(summary["gate"], ensure_ascii=False, indent=2, sort_keys=True))
    print(
        json.dumps(
            {
                "coverage": summary["coverage"],
                "EC": summary["sanity_checks"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
