"""Frequency-gate probe: how much of the v1.x compound shortfall is a filter artefact?

Context
-------
scripts/build_dielectric_observations.py opened the *temperature* gate on the
local ThermoML cache but kept a hard property_family == "zero_frequency" filter.
That filter closes a second, quieter gate: every pure-liquid row carrying a
measurement frequency is dropped wholesale, and a set of liquid compounds
appears *only* in those rows. Their frequencies are not microwave numbers - they
sit at 1 kHz to 3 MHz, where the real part of the permittivity of a
non-relaxing liquid is its static value.

This probe asks three questions and answers them from the corpus:

1. which pure-liquid compounds have variable-frequency rows and no
   zero-frequency row at all, and what is their lowest frequency per
   (compound, temperature);
2. is there empirical support for a frequency ceiling below which eps'(f) can be
   treated as static - measured against this corpus rather than asserted;
3. how many compounds, rows and kelvin of coverage sit below that ceiling.

Why the control has to be built carefully
----------------------------------------
The obvious test - compare a low-frequency eps' against a static eps of the same
compound - is confounded here, and the corpus says so loudly: there is **not one**
(compound, temperature) pair in which the zero-frequency row and the
variable-frequency row come from the same DOI or the same source file. Every
comparison therefore mixes genuine frequency dispersion with the paper-to-paper
offset of the static value. The probe measures both against the *same*
per-(compound, temperature) cross-source consensus, so the frequency curve can be
read against the corpus' own cross-source noise floor instead of against zero.

Nothing is estimated. Every number in the summary is recomputed from
data/processed/dielectric_raw.csv; every candidate row keeps its provenance
columns. data/dielectric_v03.csv is read-only here and its digest is recorded so
drift is visible.

Outputs
-------
data/processed/dielectric_lowfreq_candidates.csv
probes/dielectric_lowfreq_gate_summary.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.pathing import portable_relative_path

#: Rows at or below this frequency are the primary gate. It is the classic
#: low-frequency-limit convention and it carries by far the widest control
#: sample in this corpus (see bias_check in the summary).
PRIMARY_FREQUENCY_CAP_MHZ = 1.0

#: A second, deliberately narrower tier. The 2-3 MHz rows look no worse than the
#: 1 MHz rows in the control, but that control rests on a handful of glycols, so
#: these rows are labelled rather than promoted to the primary tier.
EXTENDED_FREQUENCY_CAP_MHZ = 3.0

#: How close in temperature a static row has to be for a comparison.
TEMPERATURE_TOLERANCE_K = 0.2

#: Absolute relative deviation at or below this counts as an exact reproduction.
EXACT_MATCH_TOLERANCE = 0.0005

ROOM_TEMPERATURE_RANGE_K = (293.15, 303.15)
EXTENDED_TEMPERATURE_RANGE_K = (313.15, 323.15)
OUTSIDE_WINDOW_BAND = "outside_declared_window"

ATMOSPHERIC_PRESSURE_KPA = 101.325
ATMOSPHERIC_PRESSURE_TOLERANCE_KPA = 2.0

GATE_PRIMARY = "accepted_primary_lowfreq"
GATE_EXTENDED = "accepted_extended_lowfreq"
GATE_REJECTED = "rejected_highfreq"

FREQUENCY_BUCKETS: tuple[tuple[str, float], ...] = (
    ("<=0.01", 0.01),
    ("<=0.1", 0.1),
    ("<=1", 1.0),
    ("<=10", 10.0),
    (">10", math.inf),
)

CANDIDATE_FIELDS = (
    "inchikey",
    "name",
    "smiles",
    "T_K",
    "epsilon",
    "frequency_mhz",
    "epsilon_unit",
    "uncertainty_expanded",
    "uncertainty_standard",
    "uncertainty_kind",
    "confidence_level",
    "phase",
    "method",
    "property_family",
    "property_name",
    "pressure_kpa",
    "source_doi",
    "source_file",
    "source_file_sha256",
    "source_row_index",
    "dataset_number",
    "component_count",
    "in_roster",
    "model_ready",
    "roster_T_K",
    "roster_dielectric",
    "roster_temperature_delta_K",
    "deviation_vs_roster_static_percent",
    "temperature_band",
    "gate",
    "frequencies_at_temperature",
    "n_values_at_same_temperature",
    "near_atmospheric_pressure",
)

NOT_VERIFIED = (
    (
        "The frequency ceiling cannot be certified from this corpus alone: "
        "there are zero (compound, temperature) pairs whose static and "
        "variable-frequency rows come from the same source, so every control "
        "pair also carries a cross-source offset. Only the ceiling below which "
        "the deviations are indistinguishable from that offset is reported; "
        "pinning the true dispersion needs a single-source frequency sweep, "
        "which this cache does not contain."
    ),
    (
        "The 2-3 MHz tier rests on a small control sample (glycols plus "
        "propan-1-ol and heptane) and is labelled, not certified."
    ),
    (
        "Nothing in ThermoML separates a genuine low-frequency relaxation "
        "from electrode polarisation; both appear as a deviation and this "
        "corpus has no same-source pair with which to tell them apart."
    ),
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    """Write a CSV with LF line endings, as .gitattributes requires."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _format(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6g}"


def temperature_band(temperature_k: float) -> str:
    """Label a temperature with the schema band it falls into, if any."""

    room_min, room_max = ROOM_TEMPERATURE_RANGE_K
    if room_min <= temperature_k <= room_max:
        return "room_temperature"
    extended_min, extended_max = EXTENDED_TEMPERATURE_RANGE_K
    if extended_min <= temperature_k <= extended_max:
        return "extended_temperature"
    return OUTSIDE_WINDOW_BAND


def is_pure(row: Mapping[str, str]) -> bool:
    return row.get("is_pure", "").strip().lower() == "true"


def is_liquid(row: Mapping[str, str]) -> bool:
    return row.get("phase", "").strip() == "Liquid"


def is_zero_frequency(row: Mapping[str, str]) -> bool:
    return row.get("property_family", "").strip() == "zero_frequency"


def frequency_value(row: Mapping[str, str]) -> float | None:
    return _float(row.get("frequency_mhz", ""))


def frequency_bucket(frequency_mhz: float) -> str:
    """Cumulative upper-bound bucket: (0, 0.01], (0.01, 0.1], ... , (10, inf)."""

    for label, upper in FREQUENCY_BUCKETS:
        if frequency_mhz <= upper:
            return label
    return FREQUENCY_BUCKETS[-1][0]


def classify_gate(frequency_mhz: float) -> str:
    """Label a row with the frequency gate it falls under."""

    if frequency_mhz <= PRIMARY_FREQUENCY_CAP_MHZ:
        return GATE_PRIMARY
    if frequency_mhz <= EXTENDED_FREQUENCY_CAP_MHZ:
        return GATE_EXTENDED
    return GATE_REJECTED


def group_by_compound(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, list[Mapping[str, str]]]:
    grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("primary_inchi_key", "")].append(row)
    return dict(grouped)


def lowest_frequency_rows(
    rows: Sequence[Mapping[str, str]],
) -> list[tuple[int, Mapping[str, str]]]:
    """Keep one row per (compound, temperature): the lowest-frequency one.

    Ties are broken by the raw row index so the output is deterministic.
    """

    best: dict[tuple[str, float], tuple[float, int, Mapping[str, str]]] = {}
    for index, row in enumerate(rows):
        key = row.get("primary_inchi_key", "")
        temperature = _float(row.get("temperature_k", ""))
        frequency = frequency_value(row)
        value = _float(row.get("value", ""))
        if temperature is None or frequency is None or value is None or value <= 0.0:
            continue
        slot = (key, round(temperature, 6))
        current = best.get(slot)
        if current is None or (frequency, index) < (current[0], current[1]):
            best[slot] = (frequency, index, row)
    return sorted(
        ((index, row) for _, index, row in best.values()),
        key=lambda item: (
            item[1].get("primary_inchi_key", ""),
            _float(item[1].get("temperature_k", "")) or 0.0,
            frequency_value(item[1]) or 0.0,
        ),
    )


def static_consensus(
    zero_rows_by_compound: Mapping[str, Sequence[Mapping[str, str]]],
    inchikey: str,
    temperature_k: float,
    tolerance_k: float = TEMPERATURE_TOLERANCE_K,
) -> tuple[float | None, int]:
    """Median of the cross-source static values at one temperature, plus its n."""

    candidates = [
        value
        for row in zero_rows_by_compound.get(inchikey, ())
        if (occurred := _float(row.get("temperature_k", ""))) is not None
        and abs(occurred - temperature_k) <= tolerance_k
        and (value := _float(row.get("value", ""))) is not None
        and value > 0.0
    ]
    if not candidates:
        return None, 0
    return statistics.median(candidates), len(candidates)


def relative_deviation(value: float | None, reference: float | None) -> float | None:
    """Signed (value - reference) / reference; None when either side is absent."""

    if value is None or reference is None or reference <= 0.0:
        return None
    return (value - reference) / reference


def quantile(values: Sequence[float], probability: float) -> float | None:
    """Upper nearest-rank quantile over an already-sorted sequence."""

    if not values:
        return None
    index = min(len(values) - 1, int(probability * len(values)))
    return values[index]


def summarize_values(values: Sequence[float]) -> dict[str, object]:
    ordered = sorted(values)
    if not ordered:
        return {"n": 0}
    return {
        "n": len(ordered),
        "median": statistics.median(ordered),
        "mean": statistics.fmean(ordered),
        "p75": quantile(ordered, 0.75),
        "p90": quantile(ordered, 0.90),
        "p95": quantile(ordered, 0.95),
        "max": ordered[-1],
    }


def _scaled_summary(stats: Mapping[str, object]) -> dict[str, object]:
    scaled: dict[str, object] = {"n": stats.get("n", 0)}
    for name in ("median", "mean", "p75", "p90", "p95", "max"):
        value = stats.get(name)
        scaled[f"{name}_percent"] = None if value is None else 100.0 * float(value)
    return scaled


def compute_noise_floor(
    zero_rows_by_compound: Mapping[str, Sequence[Mapping[str, str]]],
    tolerance_k: float = TEMPERATURE_TOLERANCE_K,
) -> dict[str, object]:
    """How far one lab's static value sits from the cross-source consensus.

    This is the yardstick the frequency curve is judged against: if low-frequency
    deviations are no larger than this, the corpus cannot distinguish them from a
    plain paper-to-paper offset.
    """

    deviations: list[float] = []
    for key in sorted(zero_rows_by_compound):
        for row in zero_rows_by_compound[key]:
            temperature = _float(row.get("temperature_k", ""))
            value = _float(row.get("value", ""))
            if temperature is None or value is None or value <= 0.0:
                continue
            consensus, sources = static_consensus(
                zero_rows_by_compound, key, temperature, tolerance_k
            )
            if consensus is None or sources < 2:
                continue
            deviation = relative_deviation(value, consensus)
            if deviation is not None:
                deviations.append(abs(deviation))
    return {
        "temperature_tolerance_k": tolerance_k,
        "statistic": (
            "absolute relative deviation of one static value from the "
            "cross-source consensus of its (compound, temperature) group"
        ),
        "requires_sources": 2,
        "comparisons": len(deviations),
        "absolute": _scaled_summary(summarize_values(deviations)),
    }


def compute_bias_check(
    freq_rows: Sequence[Mapping[str, str]],
    zero_rows_by_compound: Mapping[str, Sequence[Mapping[str, str]]],
    tolerance_k: float = TEMPERATURE_TOLERANCE_K,
    worst_offender_limit: int = 10,
) -> dict[str, object]:
    """Compare eps'(f) with the cross-source static consensus of one (compound, T)."""

    per_frequency: dict[float, list[float]] = defaultdict(list)
    per_frequency_compounds: dict[float, set[str]] = defaultdict(set)
    per_bucket: dict[str, list[float]] = defaultdict(list)
    per_bucket_compounds: dict[str, set[str]] = defaultdict(set)
    exact_frequency: Counter = Counter()
    worst: list[tuple[float, Mapping[str, str], float, int]] = []
    pairs = 0
    same_source_pairs = 0
    compounds: set[str] = set()

    for row in freq_rows:
        key = row.get("primary_inchi_key", "")
        temperature = _float(row.get("temperature_k", ""))
        value = _float(row.get("value", ""))
        frequency = frequency_value(row)
        if temperature is None or value is None or frequency is None:
            continue
        consensus, sources = static_consensus(
            zero_rows_by_compound, key, temperature, tolerance_k
        )
        if consensus is None:
            continue
        deviation = relative_deviation(value, consensus)
        if deviation is None:
            continue
        pairs += 1
        compounds.add(key)
        if any(
            source.get("doi", "") == row.get("doi", "")
            and source.get("source_file", "") == row.get("source_file", "")
            for source in zero_rows_by_compound.get(key, ())
        ):
            same_source_pairs += 1
        magnitude = abs(deviation)
        per_frequency[frequency].append(deviation)
        per_frequency_compounds[frequency].add(key)
        bucket = frequency_bucket(frequency)
        per_bucket[bucket].append(deviation)
        per_bucket_compounds[bucket].add(key)
        if magnitude <= EXACT_MATCH_TOLERANCE:
            exact_frequency[frequency] += 1
        worst.append((magnitude, row, consensus, sources))

    def _frequency_entry(frequency: float) -> dict[str, object]:
        signed = per_frequency[frequency]
        magnitudes = [abs(item) for item in signed]
        return {
            "frequency_mhz": frequency,
            "pairs": len(signed),
            "compounds": len(per_frequency_compounds[frequency]),
            "exact_matches": exact_frequency[frequency],
            "exact_match_rate": (
                exact_frequency[frequency] / len(signed) if signed else None
            ),
            "signed": _scaled_summary(summarize_values(signed)),
            "absolute": _scaled_summary(summarize_values(magnitudes)),
            "positive_deviations": sum(1 for item in signed if item > 0.0),
        }

    def _bucket_entry(label: str) -> dict[str, object]:
        signed = per_bucket[label]
        magnitudes = [abs(item) for item in signed]
        exact = sum(1 for item in magnitudes if item <= EXACT_MATCH_TOLERANCE)
        return {
            "bucket": label,
            "pairs": len(signed),
            "compounds": len(per_bucket_compounds[label]),
            "exact_matches": exact,
            "exact_match_rate": exact / len(signed) if signed else None,
            "signed": _scaled_summary(summarize_values(signed)),
            "absolute": _scaled_summary(summarize_values(magnitudes)),
            "positive_deviations": sum(1 for item in signed if item > 0.0),
        }

    worst.sort(key=lambda item: (-item[0], item[1].get("primary_inchi_key", "")))
    return {
        "temperature_tolerance_k": tolerance_k,
        "matched_pairs": pairs,
        "distinct_compounds": len(compounds),
        "same_source_pairs": same_source_pairs,
        "per_frequency": [_frequency_entry(item) for item in sorted(per_frequency)],
        "buckets": [_bucket_entry(label) for label, _ in FREQUENCY_BUCKETS],
        "worst_offenders": [
            {
                "inchikey": row.get("primary_inchi_key", ""),
                "name": row.get("primary_name", ""),
                "frequency_mhz": frequency_value(row),
                "T_K": _float(row.get("temperature_k", "")),
                "epsilon": _float(row.get("value", "")),
                "static_consensus": consensus,
                "static_consensus_sources": sources,
                "absolute_deviation_percent": 100.0 * magnitude,
                "source_doi": row.get("doi", ""),
            }
            for magnitude, row, consensus, sources in worst[:worst_offender_limit]
        ],
    }


def compute_roster_check(
    freq_rows: Sequence[Mapping[str, str]],
    roster_index: Mapping[str, Mapping[str, str]],
    tolerance_k: float = TEMPERATURE_TOLERANCE_K,
) -> dict[str, object]:
    """Compare eps'(f) with the frozen roster static target, banded by |dT|."""

    per_frequency: dict[float, list[float]] = defaultdict(list)
    matched_per_frequency: dict[float, list[float]] = defaultdict(list)
    matched_compounds: set[str] = set()
    matched = 0
    compared = 0
    for row in freq_rows:
        key = row.get("primary_inchi_key", "")
        member = roster_index.get(key)
        if member is None:
            continue
        value = _float(row.get("value", ""))
        roster_value = _float(member.get("dielectric", ""))
        frequency = frequency_value(row)
        if value is None or roster_value is None or frequency is None:
            continue
        deviation = relative_deviation(value, roster_value)
        if deviation is None:
            continue
        compared += 1
        per_frequency[frequency].append(deviation)
        temperature = _float(row.get("temperature_k", ""))
        roster_temperature = _float(member.get("T_K", ""))
        if (
            temperature is not None
            and roster_temperature is not None
            and abs(temperature - roster_temperature) <= tolerance_k
        ):
            matched += 1
            matched_compounds.add(key)
            matched_per_frequency[frequency].append(deviation)
    return {
        "roster_rows": len(roster_index),
        "comparisons": compared,
        "temperature_matched_comparisons": matched,
        "temperature_matched_compounds": len(matched_compounds),
        "per_frequency": [
            {
                "frequency_mhz": frequency,
                "comparisons": len(per_frequency[frequency]),
                "temperature_matched": len(matched_per_frequency[frequency]),
                "absolute_all": _scaled_summary(
                    summarize_values([abs(item) for item in per_frequency[frequency]])
                ),
                "absolute_temperature_matched": _scaled_summary(
                    summarize_values(
                        [abs(item) for item in matched_per_frequency[frequency]]
                    )
                ),
            }
            for frequency in sorted(per_frequency)
        ],
    }


def build_candidate_rows(
    liquid_freq_rows: Sequence[Mapping[str, str]],
    liquid_zero_keys: set[str],
    roster_index: Mapping[str, Mapping[str, str]],
) -> tuple[list[dict[str, str]], Counter]:
    """Rows for compounds with no static observation, lowest frequency per temperature."""

    dropped: Counter = Counter()
    grouped = group_by_compound(liquid_freq_rows)
    selected: list[tuple[int, Mapping[str, str]]] = []
    for key, rows in sorted(grouped.items()):
        if key in liquid_zero_keys:
            dropped["compound_has_zero_frequency_row"] += len(rows)
            continue
        selected.extend(lowest_frequency_rows(rows))

    rows_at_temperature: Counter = Counter()
    frequencies_at_temperature: dict[tuple[str, float], set[float]] = defaultdict(set)
    for row in liquid_freq_rows:
        key = row.get("primary_inchi_key", "")
        temperature = _float(row.get("temperature_k", ""))
        frequency = frequency_value(row)
        if temperature is None or frequency is None:
            continue
        slot = (key, round(temperature, 6))
        rows_at_temperature[slot] += 1
        frequencies_at_temperature[slot].add(frequency)

    candidates: list[dict[str, str]] = []
    for index, row in selected:
        key = row.get("primary_inchi_key", "")
        temperature = _float(row.get("temperature_k", ""))
        frequency = frequency_value(row)
        value = _float(row.get("value", ""))
        if temperature is None or frequency is None or value is None:
            continue
        member = roster_index.get(key)
        roster_temperature = _float((member or {}).get("T_K", ""))
        roster_value = _float((member or {}).get("dielectric", ""))
        delta = (
            abs(temperature - roster_temperature)
            if roster_temperature is not None
            else None
        )
        deviation = (
            relative_deviation(value, roster_value)
            if delta is not None and delta <= TEMPERATURE_TOLERANCE_K
            else None
        )
        pressure = _float(row.get("pressure_kpa", ""))
        slot = (key, round(temperature, 6))
        candidates.append(
            {
                "inchikey": key,
                "name": (member or {}).get("name", row.get("primary_name", "")),
                "smiles": (member or {}).get("smiles", ""),
                "T_K": _format(temperature),
                "epsilon": _format(value),
                "frequency_mhz": _format(frequency),
                "epsilon_unit": row.get("unit", ""),
                "uncertainty_expanded": row.get("expanded_uncertainty", ""),
                "uncertainty_standard": row.get("standard_uncertainty", ""),
                "uncertainty_kind": row.get("uncertainty_kind", ""),
                "confidence_level": row.get("confidence_level", ""),
                "phase": row.get("phase", ""),
                "method": row.get("method", ""),
                "property_family": row.get("property_family", ""),
                "property_name": row.get("property_name", ""),
                "pressure_kpa": row.get("pressure_kpa", ""),
                "source_doi": row.get("doi", ""),
                "source_file": portable_relative_path(
                    row.get("source_file", ""), root=REPOSITORY_ROOT
                ),
                "source_file_sha256": row.get("source_sha256", ""),
                "source_row_index": str(index),
                "dataset_number": row.get("dataset_number", ""),
                "component_count": row.get("component_count", ""),
                "in_roster": "true" if member else "false",
                "model_ready": (member or {}).get("model_ready", ""),
                "roster_T_K": (member or {}).get("T_K", ""),
                "roster_dielectric": (member or {}).get("dielectric", ""),
                "roster_temperature_delta_K": _format(delta),
                "deviation_vs_roster_static_percent": (
                    "" if deviation is None else f"{100.0 * deviation:.4f}"
                ),
                "temperature_band": temperature_band(temperature),
                "gate": classify_gate(frequency),
                "frequencies_at_temperature": ";".join(
                    _format(item) for item in sorted(frequencies_at_temperature[slot])
                ),
                "n_values_at_same_temperature": str(rows_at_temperature[slot]),
                "near_atmospheric_pressure": (
                    "unknown"
                    if pressure is None
                    else (
                        "true"
                        if abs(pressure - ATMOSPHERIC_PRESSURE_KPA)
                        <= ATMOSPHERIC_PRESSURE_TOLERANCE_KPA
                        else "false"
                    )
                ),
            }
        )
    candidates.sort(key=lambda item: (item["inchikey"], float(item["T_K"])))
    return candidates, dropped


def summarize_candidates(
    candidate_rows: Sequence[Mapping[str, str]],
    roster_index: Mapping[str, Mapping[str, str]],
) -> dict[str, object]:
    gates = Counter(row["gate"] for row in candidate_rows)
    compounds = {row["inchikey"] for row in candidate_rows}
    accepted = [row for row in candidate_rows if row["gate"] != GATE_REJECTED]
    accepted_compounds = {row["inchikey"] for row in accepted}
    new_compounds = sorted(key for key in accepted_compounds if key not in roster_index)
    temperatures = [float(row["T_K"]) for row in candidate_rows]
    accepted_temperatures = [float(row["T_K"]) for row in accepted]
    names = {row["inchikey"]: row["name"] for row in candidate_rows}
    return {
        "rows": len(candidate_rows),
        "compounds": len(compounds),
        "rows_by_gate": dict(sorted(gates.items())),
        "accepted_rows": len(accepted),
        "accepted_compounds": len(accepted_compounds),
        "accepted_new_compounds": len(new_compounds),
        "accepted_new_compound_names": [names.get(key, "") for key in new_compounds],
        "accepted_in_roster_compounds": len(accepted_compounds) - len(new_compounds),
        "temperature_k": {
            "min": min(temperatures) if temperatures else None,
            "max": max(temperatures) if temperatures else None,
        },
        "accepted_temperature_k": {
            "min": min(accepted_temperatures) if accepted_temperatures else None,
            "max": max(accepted_temperatures) if accepted_temperatures else None,
        },
        "accepted_rows_near_atmospheric_pressure": sum(
            1 for row in accepted if row["near_atmospheric_pressure"] == "true"
        ),
        "band_counts": dict(
            sorted(Counter(row["temperature_band"] for row in accepted).items())
        ),
    }


def frequency_inventory(pure_rows: Sequence[Mapping[str, str]]) -> dict[str, object]:
    pure_liquid = [row for row in pure_rows if is_liquid(row)]
    liquid_zero = [row for row in pure_liquid if is_zero_frequency(row)]
    liquid_freq = [row for row in pure_liquid if not is_zero_frequency(row)]
    zero_keys = {row["primary_inchi_key"] for row in liquid_zero}
    freq_keys = {row["primary_inchi_key"] for row in liquid_freq}
    all_phase_freq = [row for row in pure_rows if not is_zero_frequency(row)]
    all_phase_freq_keys = {row["primary_inchi_key"] for row in all_phase_freq}
    non_liquid_only = all_phase_freq_keys - freq_keys - zero_keys
    histogram: Counter = Counter()
    for row in liquid_freq:
        histogram[_format(frequency_value(row))] += 1
    return {
        "pure_rows": len(pure_rows),
        "pure_compounds": len({row["primary_inchi_key"] for row in pure_rows}),
        "liquid_zero_frequency_rows": len(liquid_zero),
        "liquid_zero_frequency_compounds": len(zero_keys),
        "liquid_frequency_dependent_rows": len(liquid_freq),
        "liquid_frequency_dependent_compounds": len(freq_keys),
        "both_compounds": len(zero_keys & freq_keys),
        "frequency_only_compounds": len(freq_keys - zero_keys),
        "non_liquid_frequency_only_compounds": sorted(non_liquid_only),
        "non_liquid_frequency_only_rows": sum(
            1 for row in all_phase_freq if row["primary_inchi_key"] in non_liquid_only
        ),
        "frequency_value_histogram": {
            key: count for key, count in sorted(histogram.items()) if key
        },
    }


def analyze(
    raw_rows: Sequence[Mapping[str, str]],
    roster_rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Return the candidate rows plus the full evidence summary."""

    roster_index = {row["inchikey"]: row for row in roster_rows}
    pure_rows = [row for row in raw_rows if is_pure(row)]
    liquid_zero = [
        row for row in pure_rows if is_liquid(row) and is_zero_frequency(row)
    ]
    liquid_freq = [
        row for row in pure_rows if is_liquid(row) and not is_zero_frequency(row)
    ]
    zero_keys = {row["primary_inchi_key"] for row in liquid_zero}
    zero_by_compound = group_by_compound(liquid_zero)

    candidate_rows, dropped = build_candidate_rows(liquid_freq, zero_keys, roster_index)
    candidates = summarize_candidates(candidate_rows, roster_index)
    bias_check = compute_bias_check(liquid_freq, zero_by_compound)
    bias_check["noise_floor"] = compute_noise_floor(zero_by_compound)

    summary: dict[str, object] = {
        "gate_decision": {
            "primary_cap_mhz": PRIMARY_FREQUENCY_CAP_MHZ,
            "extended_cap_mhz": EXTENDED_FREQUENCY_CAP_MHZ,
            "primary_basis": (
                "Widest control sample in the corpus plus the classic "
                "low-frequency-limit convention; see bias_check for the numbers."
            ),
            "extended_basis": (
                "2-3 MHz rows are labelled rather than promoted: their control "
                "sample is small and comes from a single glycol family."
            ),
        },
        "frequency_inventory": frequency_inventory(pure_rows),
        "bias_check": bias_check,
        "roster_check": compute_roster_check(liquid_freq, roster_index),
        "candidates": candidates,
        "dropped_frequency_rows": dict(sorted(dropped.items())),
        "not_verified": list(NOT_VERIFIED),
    }
    return candidate_rows, summary


def build_summary_document(
    summary: Mapping[str, object],
    *,
    raw_path: Path,
    roster_path: Path,
    candidate_path: Path,
) -> dict[str, object]:
    document: dict[str, object] = dict(summary)
    document["inputs"] = {
        "raw": portable_relative_path(raw_path, root=REPOSITORY_ROOT),
        "raw_sha256": canonical_text_sha256(raw_path) if raw_path.is_file() else "",
        "raw_rows": len(read_csv_rows(raw_path)) if raw_path.is_file() else 0,
        "roster": portable_relative_path(roster_path, root=REPOSITORY_ROOT),
        "roster_sha256": (
            canonical_text_sha256(roster_path) if roster_path.is_file() else ""
        ),
        "roster_rows": len(read_csv_rows(roster_path)) if roster_path.is_file() else 0,
        "candidates": portable_relative_path(candidate_path, root=REPOSITORY_ROOT),
    }
    document["candidate_table_notes"] = {
        "gate": (
            "accepted_primary_lowfreq holds frequency_mhz <= "
            f"{PRIMARY_FREQUENCY_CAP_MHZ:g}; accepted_extended_lowfreq holds "
            f"{PRIMARY_FREQUENCY_CAP_MHZ:g} < frequency_mhz <= "
            f"{EXTENDED_FREQUENCY_CAP_MHZ:g}; rejected_highfreq holds everything "
            "above the extended cap."
        ),
        "epsilon": (
            "Real part of the relative permittivity, taken at the frequency in "
            "frequency_mhz. It is not a modelled static value."
        ),
        "deviation_vs_roster_static_percent": (
            "Signed: 100 * (epsilon - roster_dielectric) / roster_dielectric, "
            "written only where |T_K - roster_T_K| <= "
            f"{TEMPERATURE_TOLERANCE_K:g} K and the compound is in the roster."
        ),
        "n_values_at_same_temperature": (
            "How many variable-frequency rows the corpus holds for this "
            "(compound, temperature); >1 means replicates or a pressure series "
            "were collapsed to the single lowest-frequency row."
        ),
        "near_atmospheric_pressure": (
            "true when |pressure_kpa - 101.325| <= 2, false otherwise, unknown "
            "when the source reports no pressure."
        ),
    }
    document["frozen_roster_digest_unchanged"] = (
        document["inputs"]["roster_sha256"]
        == "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
    )
    return document


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    data_dir = REPOSITORY_ROOT / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw", type=Path, default=data_dir / "processed" / "dielectric_raw.csv"
    )
    parser.add_argument("--roster", type=Path, default=data_dir / "dielectric_v03.csv")
    parser.add_argument(
        "--output",
        type=Path,
        default=data_dir / "processed" / "dielectric_lowfreq_candidates.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_lowfreq_gate_summary.json",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "")
    if encoding != "utf8" and hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    args = _parse_args(argv)
    raw_rows = read_csv_rows(args.raw)
    roster_rows = read_csv_rows(args.roster)
    candidate_rows, summary = analyze(raw_rows, roster_rows)
    write_csv_rows(args.output, CANDIDATE_FIELDS, candidate_rows)
    document = build_summary_document(
        summary, raw_path=args.raw, roster_path=args.roster, candidate_path=args.output
    )
    write_json(args.summary, document)

    inventory = document["frequency_inventory"]
    candidates = document["candidates"]
    bias = document["bias_check"]
    print(f"wrote {portable_relative_path(args.output, root=REPOSITORY_ROOT)}")
    print(
        f"  pure liquid : {inventory['liquid_zero_frequency_compounds']} static + "
        f"{inventory['liquid_frequency_dependent_compounds']} frequency-resolved"
    )
    print(
        f"  bias pairs  : {bias['matched_pairs']} "
        f"(same-source {bias['same_source_pairs']})"
    )
    print(
        f"  candidates  : {candidates['rows']} rows / "
        f"{candidates['compounds']} compounds"
    )
    print(
        f"  accepted    : {candidates['accepted_rows']} rows / "
        f"{candidates['accepted_compounds']} compounds "
        f"({candidates['accepted_new_compounds']} new to the roster)"
    )
    print(f"  gates       : {candidates['rows_by_gate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
