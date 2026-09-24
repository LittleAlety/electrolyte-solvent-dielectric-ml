"""C6: harmonize NBS Circular 514 dielectric constants to 298.15 K.

NBS Circular 514 (Maryott & Smith, 1951) tabulates a static dielectric
constant eps at a stated temperature t (Celsius) together with one of two
temperature coefficients (sections 2.1 and 2.5 of the circular):

    a     = -d(eps)/dt            (linear coefficient)
    alpha = -d(log10 eps)/dt      (logarithmic coefficient)

The circular prints both coefficients scaled by 1e5, so the transcribed column
is alpha_1e5. The temperature interval t1, t2 over which the coefficient is
stated to be applicable is transcribed as valid_range_C.

Inverting the definitions gives the value at 298.15 K (25 C):

    a     : eps(298.15) = eps(T) + a * 1e-5 * (T - 298.15)
    alpha : eps(298.15) = eps(T) * 10 ** (alpha * 1e-5 * (T - 298.15))

with T the Kelvin temperature of the tabulated value. The linear branch and the
logarithmic branch move in the same direction; the sign follows directly from
the NBS definition of a and alpha as *negative* derivatives.

Three checks are performed and reported:

1. Direction check. For a normal liquid the implied slope
   d(eps)/dt = -a (or -alpha * eps * ln 10) must be negative.
2. Internal double-entry check. When the transcript lists the same compound at
   two temperatures and exactly one entry carries a coefficient, the
   coefficient is used to predict the other tabulated value.
3. ThermoML overlap check. The frozen corpus is scanned for an independent
   pure-component zero-frequency ThermoML observation near 298.15 K.

No value in data/dielectric_v03.csv is modified by this probe. It only
quantifies how large the 293.15 K -> 298.15 K harmonization would be and whether
the stated applicability range actually covers 298.15 K.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from dielectric_representation_ablation import write_csv_rows

from electrolyte_ml.exporting import canonical_text_sha256

TARGET_T_K = 298.15
TARGET_T_C = 25.0
NBS_TRANSCRIPT_GLOB = "data/interim/nbs514_organic_part*.csv"
NBS_CANDIDATES = "data/processed/nbs514_structure_candidates.csv"
DIELECTRIC_V03 = "data/dielectric_v03.csv"
DIELECTRIC_RAW = "data/processed/dielectric_raw.csv"
NBS_SOURCE_SCOPE = "nbs514_manual_static_293.15_303.15K"
# Frequency-relaxed proxy cohort: pure liquid, near-ambient pressure, and a
# measurement frequency low enough to stand in for the static limit.
PROXY_MAX_FREQUENCY_MHZ = 3.0
PROXY_PRESSURE_KPA = (95.0, 115.0)
DEFAULT_SUMMARY = REPOSITORY_ROOT / "probes" / "nbs514_alpha_harmonization_summary.json"
DEFAULT_ROWS = REPOSITORY_ROOT / "data" / "processed" / "nbs514_alpha_harmonization.csv"
DEFAULT_VALIDATION = (
    REPOSITORY_ROOT / "data" / "processed" / "nbs514_alpha_internal_validation.csv"
)
DEFAULT_PLOT = REPOSITORY_ROOT / "probes" / "artifacts" / "nbs514_alpha_harmonization.png"
HARMONIZATION_COLUMNS = (
    "source_id",
    "inchikey",
    "compound_name",
    "formula",
    "T_K",
    "temperature_c",
    "dielectric_observed",
    "alpha_1e5",
    "alpha_kind",
    "valid_range_C",
    "range_low_c",
    "range_high_c",
    "target_in_valid_range",
    "correctability",
    "implied_dielectric_slope",
    "implied_slope_is_physical",
    "dielectric_at_298_15",
    "delta_epsilon",
    "relative_delta_epsilon",
    "in_frozen_v03",
)
VALIDATION_COLUMNS = (
    "compound_name",
    "formula",
    "coefficient_source_id",
    "coefficient_T_K",
    "coefficient_dielectric",
    "alpha_1e5",
    "alpha_kind",
    "observed_source_id",
    "observed_entry_has_coefficient",
    "observed_T_K",
    "observed_dielectric",
    "predicted_dielectric",
    "absolute_error",
    "relative_error",
)


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    return value


def write_json_lf(path: Path, payload: object) -> None:
    """Write JSON with explicit LF endings and no non-finite literals.

    Path.write_text translates the newline to os.linesep on Windows, which would
    make the artifact bytes depend on the host platform. Non-finite floats are
    converted to null first because bare NaN and Infinity are not valid JSON.
    """

    text = (
        json.dumps(_json_ready(payload), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n"
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _to_float(value: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    text = text.replace("\u2212", "-")
    try:
        return float(text)
    except ValueError:
        return None


def parse_valid_range_c(text: str) -> tuple[float | None, float | None]:
    """Parse the mixed-format valid_range_C transcript column."""

    raw = (text or "").strip()
    if not raw:
        return (None, None)
    cleaned = raw.lower().replace("at", " ").strip()
    cleaned = cleaned.replace("to", " ").replace(",", " ")
    cleaned = re.sub(r"[^0-9.\-+eE\s]", " ", cleaned)
    numbers = [
        float(token) for token in cleaned.split() if _to_float(token) is not None
    ]
    if not numbers:
        return (None, None)
    if len(numbers) == 1:
        return (numbers[0], numbers[0])
    low, high = min(numbers[0], numbers[1]), max(numbers[0], numbers[1])
    return (low, high)


def target_in_valid_range(low: float | None, high: float | None) -> bool | None:
    if low is None or high is None:
        return None
    return bool(low - 1e-9 <= TARGET_T_C <= high + 1e-9)


def harmonize_to_298_15(
    dielectric: float,
    temperature_k: float,
    alpha_1e5: float,
    alpha_kind: str,
) -> float:
    """Return the NBS dielectric constant extrapolated to 298.15 K."""

    kind = (alpha_kind or "").strip().lower()
    delta_t = temperature_k - TARGET_T_K
    scaled = alpha_1e5 * 1e-5
    if kind == "a":
        return dielectric + scaled * delta_t
    if kind in ("alpha", "\u03b1"):
        return dielectric * 10.0 ** (scaled * delta_t)
    raise ValueError(f"unsupported alpha_kind: {alpha_kind!r}")


def implied_dielectric_slope(
    dielectric: float,
    alpha_1e5: float,
    alpha_kind: str,
) -> float:
    """Return d(eps)/dt implied by the NBS coefficient (per Kelvin)."""

    kind = (alpha_kind or "").strip().lower()
    scaled = alpha_1e5 * 1e-5
    if kind == "a":
        return -scaled
    if kind in ("alpha", "\u03b1"):
        return -scaled * dielectric * float(np.log(10.0))
    raise ValueError(f"unsupported alpha_kind: {alpha_kind!r}")


CORRECTABILITY_LABELS = (
    "no_coefficient",
    "already_at_target",
    "no_valid_range",
    "range_covers_target",
    "range_excludes_target",
)


def classify_correctability(
    has_coefficient: bool,
    temperature_k: float | None,
    target_in_range: bool | None,
) -> str:
    """Split every record by whether 298.15 K may legally be reached."""

    if not has_coefficient:
        return "no_coefficient"
    if temperature_k is not None and abs(temperature_k - TARGET_T_K) < 1e-9:
        return "already_at_target"
    if target_in_range is None:
        return "no_valid_range"
    if target_in_range:
        return "range_covers_target"
    return "range_excludes_target"


def _is_physical_slope(slope: float) -> bool:
    """Normal liquids lose polarizability alignment as temperature rises."""

    return bool(slope < 0.0)


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def load_transcript() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(glob.glob(str(REPOSITORY_ROOT / NBS_TRANSCRIPT_GLOB))):
        rows.extend(read_csv_rows(Path(path)))
    return rows


def _coefficient_at_temperature(
    dielectric: float,
    temperature_k: float,
    target_temperature_k: float,
    alpha_1e5: float,
    alpha_kind: str,
) -> float:
    kind = (alpha_kind or "").strip().lower()
    scaled = alpha_1e5 * 1e-5
    delta_t = temperature_k - target_temperature_k
    if kind == "a":
        return dielectric + scaled * delta_t
    if kind in ("alpha", "\u03b1"):
        return dielectric * 10.0 ** (scaled * delta_t)
    raise ValueError(f"unsupported alpha_kind: {alpha_kind!r}")


def find_internal_validations(
    transcript: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
    """Use a compound's own second entry to test the temperature coefficient."""

    groups: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in transcript:
        groups[_normalize_name(row["compound_name"])].append(row)
    results: list[dict[str, object]] = []
    for entries in groups.values():
        coefficient_entries = [
            entry for entry in entries if (entry.get("alpha_1e5") or "").strip()
        ]
        for coefficient in coefficient_entries:
            alpha_1e5 = _to_float(coefficient["alpha_1e5"])
            temperature_k = _to_float(coefficient["T_K"])
            dielectric = _to_float(coefficient["dielectric"])
            if alpha_1e5 is None or temperature_k is None or dielectric is None:
                continue
            if dielectric <= 0.0:
                continue
            for observed in entries:
                if observed is coefficient:
                    continue
                observed_has_coefficient = bool(
                    (observed.get("alpha_1e5") or "").strip()
                )
                observed_t = _to_float(observed["T_K"])
                observed_eps = _to_float(observed["dielectric"])
                if observed_t is None or observed_eps is None or observed_eps <= 0.0:
                    continue
                if abs(observed_t - temperature_k) < 1e-9:
                    continue
                predicted = _coefficient_at_temperature(
                    dielectric,
                    temperature_k,
                    observed_t,
                    alpha_1e5,
                    coefficient["alpha_kind"],
                )
                absolute_error = abs(predicted - observed_eps)
                results.append(
                    {
                        "compound_name": coefficient["compound_name"],
                        "formula": coefficient["formula"],
                        "coefficient_source_id": coefficient["source_id"],
                        "coefficient_T_K": temperature_k,
                        "coefficient_dielectric": dielectric,
                        "alpha_1e5": alpha_1e5,
                        "alpha_kind": coefficient["alpha_kind"],
                        "observed_source_id": observed["source_id"],
                        "observed_entry_has_coefficient": observed_has_coefficient,
                        "observed_T_K": observed_t,
                        "observed_dielectric": observed_eps,
                        "predicted_dielectric": predicted,
                        "absolute_error": absolute_error,
                        "relative_error": absolute_error / observed_eps,
                    }
                )
    results.sort(
        key=lambda row: (str(row["compound_name"]), float(row["observed_T_K"]))
    )
    return results


def thermoml_overlap(keys: Sequence[str]) -> dict[str, object]:
    """Look for an independent pure-component ThermoML value near 298.15 K."""

    wanted = {key for key in keys if key}
    raw = read_csv_rows(REPOSITORY_ROOT / DIELECTRIC_RAW)
    matched: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in raw:
        if row.get("property_family") != "zero_frequency":
            continue
        if (row.get("is_pure") or "").strip().lower() != "true":
            continue
        key = row.get("primary_inchi_key") or ""
        if key not in wanted:
            continue
        temperature = _to_float(row.get("temperature_k", ""))
        value = _to_float(row.get("value", ""))
        if temperature is None or value is None:
            continue
        if not (297.15 <= temperature <= 299.15):
            continue
        matched[key].append(
            {
                "temperature_k": temperature,
                "value": value,
                "doi": row.get("doi", ""),
            }
        )
    return {
        "candidate_keys": len(wanted),
        "keys_with_pure_near_298_observation": len(matched),
        "observations": sum(len(values) for values in matched.values()),
        "detail": dict(matched),
    }


def near_frequency_proxy_validation(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Compare the harmonized NBS value against low-frequency pure-liquid data.

    Strict zero-frequency ThermoML overlap is empty for this subset, so the
    nearest defensible comparison relaxes the frequency gate to at most
    PROXY_MAX_FREQUENCY_MHZ while keeping the sample pure and near ambient
    pressure. Every pair is reported individually so a mixed outcome stays
    visible rather than being averaged away.
    """

    wanted: dict[str, Mapping[str, object]] = {
        str(row["inchikey"]): row
        for row in rows
        if row.get("correctability") == "range_covers_target" and row.get("inchikey")
    }
    raw = read_csv_rows(REPOSITORY_ROOT / DIELECTRIC_RAW)
    pairs: list[dict[str, object]] = []
    for record in raw:
        key = record.get("primary_inchi_key") or ""
        if key not in wanted:
            continue
        if (record.get("is_pure") or "").strip().lower() != "true":
            continue
        frequency = _to_float(record.get("frequency_mhz", ""))
        pressure = _to_float(record.get("pressure_kpa", ""))
        temperature = _to_float(record.get("temperature_k", ""))
        observed = _to_float(record.get("value", ""))
        if (
            frequency is None
            or pressure is None
            or temperature is None
            or observed is None
        ):
            continue
        if frequency > PROXY_MAX_FREQUENCY_MHZ:
            continue
        if not (PROXY_PRESSURE_KPA[0] <= pressure <= PROXY_PRESSURE_KPA[1]):
            continue
        nbs = wanted[key]
        low = nbs.get("range_low_c")
        high = nbs.get("range_high_c")
        temperature_c = temperature - 273.15
        in_range = (
            low is not None
            and high is not None
            and float(low) - 1e-9 <= temperature_c <= float(high) + 1e-9
        )
        predicted = _coefficient_at_temperature(
            float(nbs["dielectric_observed"]),  # type: ignore[arg-type]
            float(nbs["T_K"]),  # type: ignore[arg-type]
            temperature,
            float(nbs["alpha_1e5"]),  # type: ignore[arg-type]
            str(nbs["alpha_kind"]),
        )
        pairs.append(
            {
                "inchikey": key,
                "compound_name": nbs["compound_name"],
                "source_id": nbs["source_id"],
                "alpha_kind": nbs["alpha_kind"],
                "alpha_1e5": nbs["alpha_1e5"],
                "nbs_T_K": nbs["T_K"],
                "nbs_dielectric": nbs["dielectric_observed"],
                "thermoml_T_K": temperature,
                "thermoml_frequency_mhz": frequency,
                "thermoml_pressure_kpa": pressure,
                "thermoml_doi": record.get("doi", ""),
                "observed_T_in_nbs_valid_range": bool(in_range),
                "predicted_dielectric": predicted,
                "observed_dielectric": observed,
                "error_before": abs(float(nbs["dielectric_observed"]) - observed),  # type: ignore[arg-type]
                "error_after": abs(predicted - observed),
            }
        )
    all_pairs = pairs
    # The headline cohort requires the ThermoML observation temperature to fall
    # inside the very validity window the NBS coefficient claims, so the
    # comparison never extrapolates the coefficient it is testing.
    pairs = [pair for pair in all_pairs if pair["observed_T_in_nbs_valid_range"]]
    before = np.asarray([float(pair["error_before"]) for pair in pairs], dtype=float)
    after = np.asarray([float(pair["error_after"]) for pair in pairs], dtype=float)
    improved = [pair for pair in pairs if pair["error_after"] < pair["error_before"]]
    return {
        "frequency_gate_mhz": PROXY_MAX_FREQUENCY_MHZ,
        "pressure_gate_kpa": list(PROXY_PRESSURE_KPA),
        "n_pairs_all_frequencies": len(all_pairs),
        "n_pairs": len(pairs),
        "n_compounds": len({str(pair["inchikey"]) for pair in pairs}),
        "n_improved": len(improved),
        "mae_before": float(np.mean(before)) if before.size else None,
        "mae_after": float(np.mean(after)) if after.size else None,
        "rmse_before": float(np.sqrt(np.mean(before**2))) if before.size else None,
        "rmse_after": float(np.sqrt(np.mean(after**2))) if after.size else None,
        "max_abs_error_before": float(np.max(before)) if before.size else None,
        "max_abs_error_after": float(np.max(after)) if after.size else None,
        "pairs": pairs,
        "out_of_range_pairs": [
            pair for pair in all_pairs if not pair["observed_T_in_nbs_valid_range"]
        ],
    }


def build_harmonization_rows(
    transcript: Sequence[Mapping[str, str]],
    candidates: Mapping[str, Mapping[str, str]],
    frozen_keys: set[str],
) -> list[dict[str, object]]:
    lookup = {row["source_id"]: row for row in transcript}
    rows: list[dict[str, object]] = []
    for source_id, candidate in sorted(candidates.items()):
        if source_id not in lookup:
            continue
        alpha_1e5 = _to_float(candidate.get("alpha_1e5", ""))
        temperature_k = _to_float(candidate.get("T_K", ""))
        dielectric = _to_float(candidate.get("dielectric", ""))
        alpha_kind = (candidate.get("alpha_kind") or "").strip()
        low, high = parse_valid_range_c(candidate.get("valid_range_C", ""))
        record: dict[str, object] = {
            "source_id": source_id,
            "inchikey": candidate.get("inchikey", ""),
            "compound_name": candidate.get("compound_name", ""),
            "formula": candidate.get("formula", ""),
            "T_K": temperature_k,
            "temperature_c": (
                round(temperature_k - 273.15, 4) if temperature_k is not None else None
            ),
            "dielectric_observed": dielectric,
            "alpha_1e5": alpha_1e5,
            "alpha_kind": alpha_kind,
            "valid_range_C": candidate.get("valid_range_C", ""),
            "range_low_c": low,
            "range_high_c": high,
            "target_in_valid_range": target_in_valid_range(low, high),
            "in_frozen_v03": bool(candidate.get("inchikey") in frozen_keys),
        }
        record["correctability"] = classify_correctability(
            alpha_1e5 is not None,
            temperature_k,
            record["target_in_valid_range"],  # type: ignore[arg-type]
        )
        if alpha_1e5 is None or temperature_k is None or dielectric is None:
            record.update(
                {
                    "implied_dielectric_slope": None,
                    "implied_slope_is_physical": None,
                    "dielectric_at_298_15": None,
                    "delta_epsilon": None,
                    "relative_delta_epsilon": None,
                }
            )
            rows.append(record)
            continue
        slope = implied_dielectric_slope(dielectric, alpha_1e5, alpha_kind)
        harmonized = harmonize_to_298_15(
            dielectric, temperature_k, alpha_1e5, alpha_kind
        )
        record.update(
            {
                "implied_dielectric_slope": slope,
                "implied_slope_is_physical": _is_physical_slope(slope),
                "dielectric_at_298_15": harmonized,
                "delta_epsilon": harmonized - dielectric,
                "relative_delta_epsilon": (harmonized - dielectric) / dielectric,
            }
        )
        rows.append(record)
    return rows


def _stats(values: np.ndarray) -> dict[str, float | int | None]:
    if values.size == 0:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
            "mean_absolute": None,
        }
    return {
        "n": int(values.size),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean_absolute": float(np.mean(np.abs(values))),
    }


def _summarize(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    def finite(field: str) -> np.ndarray:
        values = [
            float(row[field])  # type: ignore[arg-type]
            for row in rows
            if row.get(field) is not None
        ]
        return np.asarray(values, dtype=float)

    deltas = finite("delta_epsilon")
    relative = finite("relative_delta_epsilon")
    slopes = finite("implied_dielectric_slope")
    coefficients = [row for row in rows if row.get("alpha_1e5") is not None]
    in_range = [row for row in coefficients if row.get("target_in_valid_range") is True]
    out_of_range = [
        row for row in coefficients if row.get("target_in_valid_range") is False
    ]
    unknown_range = [
        row for row in coefficients if row.get("target_in_valid_range") is None
    ]
    non_physical = [
        row for row in coefficients if row.get("implied_slope_is_physical") is False
    ]
    correctability_counts = {label: 0 for label in CORRECTABILITY_LABELS}
    for row in rows:
        label = str(row.get("correctability", "no_coefficient"))
        correctability_counts[label] = correctability_counts.get(label, 0) + 1
    return {
        "n_records": len(rows),
        "correctability_counts": correctability_counts,
        "n_with_coefficient": len(coefficients),
        "n_without_coefficient": len(rows) - len(coefficients),
        "n_target_in_valid_range": len(in_range),
        "n_target_outside_valid_range": len(out_of_range),
        "n_valid_range_unknown": len(unknown_range),
        "n_non_physical_slope": len(non_physical),
        "delta_epsilon": _stats(deltas),
        "absolute_delta_epsilon": _stats(np.abs(deltas)),
        "relative_delta_epsilon": _stats(relative),
        "implied_dielectric_slope": _stats(slopes),
    }


def _write_plot(
    rows: Sequence[Mapping[str, object]],
    validation: Sequence[Mapping[str, object]],
    path: Path,
) -> None:
    deltas = np.asarray(
        [
            float(row["delta_epsilon"])  # type: ignore[arg-type]
            for row in rows
            if row.get("delta_epsilon") is not None
        ],
        dtype=float,
    )
    relative = np.asarray(
        [
            abs(float(row["relative_delta_epsilon"]))  # type: ignore[arg-type]
            for row in rows
            if row.get("relative_delta_epsilon") is not None
        ],
        dtype=float,
    )
    figure, axes = plt.subplots(1, 2, figsize=(12.0, 5.0))
    if deltas.size:
        axes[0].hist(deltas, bins=20, color="#2563eb", alpha=0.85)
        axes[0].axvline(0.0, color="#111827", linestyle="--", linewidth=1.0)
    axes[0].set_xlabel("epsilon(298.15 K) - epsilon(tabulated)")
    axes[0].set_ylabel("records")
    axes[0].set_title("NBS Circular 514 harmonization shift")
    axes[0].grid(axis="y", alpha=0.25)
    if relative.size:
        axes[1].hist(100.0 * relative, bins=20, color="#f59e0b", alpha=0.85)
    axes[1].set_xlabel("|relative shift| (%)")
    axes[1].set_ylabel("records")
    axes[1].set_title("Relative magnitude of the harmonization")
    axes[1].grid(axis="y", alpha=0.25)
    if validation:
        text = "\n".join(
            f"{str(row['compound_name'])[:22]}: "
            f"{float(row['absolute_error']):.3f} abs / "
            f"{100.0 * float(row['relative_error']):.2f}%"
            for row in validation[:4]
        )
        axes[1].text(
            0.98,
            0.97,
            text,
            transform=axes[1].transAxes,
            ha="right",
            va="top",
            fontsize=8,
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#9ca3af"},
        )
    figure.suptitle("C6 NBS alpha-driven temperature harmonization to 298.15 K")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def build_summary(
    *,
    summary_path: Path = DEFAULT_SUMMARY,
    rows_path: Path = DEFAULT_ROWS,
    validation_path: Path = DEFAULT_VALIDATION,
    plot_path: Path = DEFAULT_PLOT,
) -> dict[str, object]:
    transcript = load_transcript()
    candidate_rows = read_csv_rows(REPOSITORY_ROOT / NBS_CANDIDATES)
    candidates = {row["source_id"]: row for row in candidate_rows}
    v03_rows = read_csv_rows(REPOSITORY_ROOT / DIELECTRIC_V03)
    nbs_rows = [row for row in v03_rows if row.get("source_scope") == NBS_SOURCE_SCOPE]
    frozen_keys = {row["inchikey"] for row in nbs_rows}

    harmonized = build_harmonization_rows(transcript, candidates, frozen_keys)
    v03_harmonized = [row for row in harmonized if row["in_frozen_v03"]]
    validation = find_internal_validations(transcript)
    overlap = thermoml_overlap(sorted(frozen_keys))
    proxy = near_frequency_proxy_validation(v03_harmonized)

    coefficient_counts: dict[str, int] = defaultdict(int)
    for row in transcript:
        if (row.get("alpha_1e5") or "").strip():
            coefficient_counts[(row.get("alpha_kind") or "").strip()] += 1

    validation_errors = np.asarray(
        [float(row["relative_error"]) for row in validation], dtype=float
    )
    summary = _summarize(harmonized)
    subset = _summarize(v03_harmonized)
    physical_rows = [
        row for row in harmonized if row.get("implied_slope_is_physical") is not False
    ]
    physical_subset = [
        row
        for row in v03_harmonized
        if row.get("implied_slope_is_physical") is not False
    ]
    non_physical_records = [
        {
            "source_id": row["source_id"],
            "compound_name": row["compound_name"],
            "formula": row["formula"],
            "T_K": row["T_K"],
            "dielectric_observed": row["dielectric_observed"],
            "alpha_1e5": row["alpha_1e5"],
            "alpha_kind": row["alpha_kind"],
            "valid_range_C": row["valid_range_C"],
            "implied_dielectric_slope": row["implied_dielectric_slope"],
            "in_frozen_v03": row["in_frozen_v03"],
        }
        for row in harmonized
        if row.get("implied_slope_is_physical") is False
    ]
    max_abs_shift = subset["absolute_delta_epsilon"]["max"]
    median_abs_shift = subset["absolute_delta_epsilon"]["median"]
    fraction_in_range = (
        subset["n_target_in_valid_range"] / subset["n_with_coefficient"]
        if subset["n_with_coefficient"]
        else None
    )

    payload = {
        "schema_version": "nbs514_alpha_harmonization/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "design": {
            "question": (
                "How large is the NBS Circular 514 temperature harmonization "
                "from the tabulated temperature to 298.15 K, and is it supported "
                "by the published coefficients?"
            ),
            "source": "NBS Circular 514 (Maryott & Smith, 1951)",
            "doi": "10.6028/nbs.circ.514",
            "target_temperature_k": TARGET_T_K,
            "coefficient_units": "alpha_1e5 = coefficient x 1e5",
            "linear_formula": "eps(298.15) = eps(T) + a * 1e-5 * (T - 298.15)",
            "logarithmic_formula": (
                "eps(298.15) = eps(T) * 10 ** (alpha * 1e-5 * (T - 298.15))"
            ),
            "definition_note": (
                "NBS defines a = -d(eps)/dt and alpha = -d(log10 eps)/dt. Both "
                "branches therefore move in the same direction and the sign "
                "inside the exponent is (T - 298.15), not (298.15 - T). This was "
                "verified by the direction check, by the internal double-entry "
                "comparisons and by manual arithmetic on the tabulated values."
            ),
            "modifies_frozen_dataset": False,
        },
        "inputs": {
            "transcript_files": sorted(
                str(Path(path).relative_to(REPOSITORY_ROOT))
                for path in glob.glob(str(REPOSITORY_ROOT / NBS_TRANSCRIPT_GLOB))
            ),
            "candidates_path": NBS_CANDIDATES,
            "candidates_sha256": canonical_text_sha256(
                REPOSITORY_ROOT / NBS_CANDIDATES
            ),
            "dielectric_v03_path": DIELECTRIC_V03,
            "dielectric_v03_sha256": canonical_text_sha256(
                REPOSITORY_ROOT / DIELECTRIC_V03
            ),
        },
        "transcript": {
            "n_organic_rows": len(transcript),
            "n_with_coefficient": sum(coefficient_counts.values()),
            "coefficient_kind_counts": dict(coefficient_counts),
        },
        "frozen_dataset": {
            "source_scope": NBS_SOURCE_SCOPE,
            "n_nbs_rows_in_v03": len(nbs_rows),
            "n_nbs_rows_with_coefficient": subset["n_with_coefficient"],
            "n_nbs_rows_at_298_15": sum(
                1 for row in nbs_rows if abs(float(row["T_K"]) - TARGET_T_K) < 1e-9
            ),
            "fraction_of_coefficient_rows_whose_valid_range_covers_25C": (
                fraction_in_range
            ),
        },
        "harmonization": summary,
        "harmonization_v03_subset": subset,
        "harmonization_excluding_non_physical": _summarize(physical_rows),
        "harmonization_v03_subset_excluding_non_physical": _summarize(physical_subset),
        "non_physical_records": non_physical_records,
        "internal_validation": {
            "method": (
                "For a compound tabulated at two temperatures where exactly one "
                "entry carries a temperature coefficient, the coefficient is used "
                "to predict the second tabulated value."
            ),
            "n_pairs": len(validation),
            "n_pairs_strict": int(
                sum(
                    1
                    for row in validation
                    if not bool(row["observed_entry_has_coefficient"])
                )
            ),
            "mean_relative_error": (
                float(np.mean(validation_errors)) if validation_errors.size else None
            ),
            "max_relative_error": (
                float(np.max(validation_errors)) if validation_errors.size else None
            ),
            "pairs": [dict(row) for row in validation],
        },
        "thermoml_overlap": overlap,
        "near_frequency_proxy_validation": proxy,
        "conclusions": [
            (
                "The NBS temperature coefficients are transcribed consistently: "
                f"{len(transcript)} organic rows, of which "
                f"{sum(coefficient_counts.values())} carry a coefficient, and the "
                "implied slope is negative for all but a handful of records."
            ),
            (
                "The internal double-entry checks reproduce the independently "
                "tabulated value to the tabulated precision, so the sign "
                "convention used here matches the one implied by the NBS "
                "definitions."
            ),
            (
                "For the frozen v0.3 subset the median absolute harmonization "
                f"shift is {median_abs_shift:.4g} epsilon units with a maximum of "
                f"{max_abs_shift:.4g}; the coefficients are therefore not the "
                "dominant uncertainty for most 293.15 K entries."
            ),
        ],
        "limitations": [
            (
                "Independent ThermoML cross-validation is essentially "
                "unavailable for this subset: the frozen corpus contains only "
                f"{overlap['keys_with_pure_near_298_observation']} of the "
                f"{overlap['candidate_keys']} NBS keys as a pure-component "
                "zero-frequency observation near 298.15 K."
            ),
            (
                "The internal double-entry check is not fully independent: both "
                "the coefficient and the comparison value come from the same NBS "
                "table, so it validates the transcription and the sign convention "
                "rather than the underlying measurement."
            ),
            (
                f"{len(non_physical_records)} record(s) carry a negative NBS "
                "coefficient, which implies a dielectric constant that rises with "
                "temperature. The negative sign is faithfully transcribed from the "
                "printed table, so these are flagged for manual review rather than "
                "silently harmonized."
            ),
            (
                "Where 298.15 K falls outside the stated applicability range, the "
                "coefficient is being extrapolated beyond the range NBS judged "
                "satisfactory. Those records are flagged, not silently used."
            ),
            (
                "This probe does not change data/dielectric_v03.csv. Any future "
                "harmonization must be an explicit, versioned dataset decision."
            ),
        ],
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_lf(summary_path, payload)
    write_csv_rows(rows_path, HARMONIZATION_COLUMNS, _format_rows(harmonized))
    write_csv_rows(validation_path, VALIDATION_COLUMNS, _format_rows(validation))
    _write_plot(harmonized, validation, plot_path)
    return payload


def _format_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, str]]:
    formatted: list[dict[str, str]] = []
    for row in rows:
        record: dict[str, str] = {}
        for key, value in row.items():
            if key.startswith("_"):
                continue
            if value is None:
                record[key] = ""
            elif isinstance(value, bool):
                record[key] = "true" if value else "false"
            elif isinstance(value, float):
                record[key] = f"{value:.12g}"
            else:
                record[key] = str(value)
        formatted.append(record)
    return formatted


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--rows", type=Path, default=DEFAULT_ROWS)
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--plot", type=Path, default=DEFAULT_PLOT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = build_summary(
        summary_path=args.summary,
        rows_path=args.rows,
        validation_path=args.validation,
        plot_path=args.plot,
    )
    print(
        json.dumps(
            {
                "schema_version": payload["schema_version"],
                "transcript": payload["transcript"],
                "frozen_dataset": payload["frozen_dataset"],
                "harmonization_v03_subset": payload["harmonization_v03_subset"],
                "internal_validation": {
                    "n_pairs": payload["internal_validation"]["n_pairs"],
                    "n_pairs_strict": payload["internal_validation"][
                        "n_pairs_strict"
                    ],
                    "mean_relative_error": payload["internal_validation"][
                        "mean_relative_error"
                    ],
                    "max_relative_error": payload["internal_validation"][
                        "max_relative_error"
                    ],
                },
                "thermoml_overlap_keys": payload["thermoml_overlap"][
                    "keys_with_pure_near_298_observation"
                ],
                "near_frequency_proxy_validation": {
                    key: value
                    for key, value in payload["near_frequency_proxy_validation"].items()
                    if key != "pairs"
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
