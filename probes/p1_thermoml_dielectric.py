"""P1: inventory experimental dielectric constants in ThermoML.

The preferred input is a complete, checksum-pinned ThermoML archive. When the
NIST bulk archive is unavailable, the same extractor can scan a directory of
individually downloaded ThermoML XML documents.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from thermoml_io import (
    ThermoMLDocument,
    iter_thermoml_archive,
    parse_thermoml,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPLETE_ARCHIVE_URL = (
    "https://data.nist.gov/od/ds/mds2-2422/ThermoML.v2020-09-30.tgz"
)
COMPLETE_ARCHIVE_SHA256 = (
    "231161b5e443dc1ae0e5da8429d86a88474cb722016e5b790817bb31c58d7ec2"
)
FALLBACK_SOURCE_LIMITATION = (
    "Complete checksum-pinned 2020 ThermoML archive "
    "(ThermoML.v2020-09-30.tgz) was unavailable during this run. The bulk "
    "endpoint returned repeated HTTP 504 responses, and a 30 s header/range "
    "retry returned no bytes. The provisional result uses the live NIST API "
    "dielectric/permittivity query union as an individual-XML fallback, not the "
    "complete archive."
)


@dataclass(frozen=True, slots=True)
class DielectricObservation:
    source_file: str
    source_sha256: str
    doi: str
    title: str
    dataset_number: int
    property_name: str
    property_family: str
    value: Decimal
    unit: str
    expanded_uncertainty: Decimal | None
    standard_uncertainty: Decimal | None
    uncertainty_kind: str
    confidence_level: Decimal | None
    temperature_k: Decimal | None
    pressure_kpa: Decimal | None
    frequency_mhz: Decimal | None
    phase: str
    method: str
    component_count: int
    is_pure: bool
    components: tuple[dict[str, str], ...]
    primary_name: str
    primary_formula: str
    primary_inchi: str
    primary_inchi_key: str


def property_family(property_name: str) -> str:
    """Normalize the two dielectric property names found in the archive."""

    normalized = " ".join(property_name.casefold().split())
    if "relative permittivity at zero frequency" in normalized:
        return "zero_frequency"
    if "relative permittivity at" in normalized and "frequenc" in normalized:
        return "frequency_dependent"
    return ""


def classify_solvent_family(name: str) -> str:
    """Classify a compound label into broad electrolyte solvent families."""

    normalized = " ".join(name.casefold().replace("_", " ").split())
    if "carbonate" in normalized or normalized in {"ec", "pc", "dmc", "emc", "dec"}:
        return "carbonate"
    if any(
        term in normalized
        for term in (
            "ether",
            "glyme",
            "methoxy",
            "ethoxy",
            "dme",
            "thf",
            "dioxolane",
            "dioxane",
        )
    ):
        return "ether"
    if any(
        term in normalized
        for term in (
            "nitrile",
            "acetonitrile",
            "propionitrile",
            "butyronitrile",
            "succinonitrile",
            "glutaronitrile",
            "adiponitrile",
        )
    ):
        return "nitrile"
    if any(term in normalized for term in ("sulfone", "sulfolane", "sulfoxide", "dmso")):
        return "sulfone"
    return "other"


def decide_mainline(unique_compounds_near_298: int) -> str:
    if unique_compounds_near_298 >= 300:
        return "mainline_go"
    if unique_compounds_near_298 >= 100:
        return "dielectric_viscosity_joint"
    return "pivot_to_p3_or_p4"


def build_source_metadata(
    archives: Sequence[Path],
    *,
    raw_dir: Path,
) -> dict[str, object]:
    archive_available = bool(archives)
    return {
        "source_mode": "archive" if archive_available else "individual_xml_fallback",
        "fallback_query_census": not archive_available,
        "complete_archive_available": archive_available,
        "handbook_gate_executed": archive_available,
        "decision_status": "archive_verified" if archive_available else "provisional",
        "source_limitation": "" if archive_available else FALLBACK_SOURCE_LIMITATION,
        "complete_archive_url": COMPLETE_ARCHIVE_URL,
        "complete_archive_sha256": COMPLETE_ARCHIVE_SHA256,
        "archive_paths": [str(path) for path in archives],
        "raw_dir": str(raw_dir),
    }


def _measured_value(point, number: int):
    return next((value for value in point.variable_values if value.number == number), None)


def _condition_value(
    data_set,
    point,
    *,
    name_fragment: str,
) -> Decimal | None:
    variable_numbers = {
        variable.number
        for variable in data_set.variables
        if name_fragment in variable.name.casefold()
    }
    for value in point.variable_values:
        if value.number in variable_numbers:
            return value.value
    for constraint in data_set.constraints:
        if name_fragment in constraint.name.casefold() and constraint.value is not None:
            return constraint.value
    return None


def _uncertainty(property_value) -> tuple[Decimal | None, Decimal | None, str, Decimal | None]:
    for uncertainty in property_value.uncertainties:
        if uncertainty.expanded_value is not None:
            return (
                uncertainty.expanded_value,
                uncertainty.standard_value,
                uncertainty.kind,
                uncertainty.confidence_level,
            )
        if uncertainty.standard_value is not None:
            return (
                None,
                uncertainty.standard_value,
                uncertainty.kind,
                uncertainty.confidence_level,
            )
    return None, None, "", None


def _components(document: ThermoMLDocument, data_set) -> tuple[dict[str, str], ...]:
    components: list[dict[str, str]] = []
    for compound in document.system_compounds(data_set):
        components.append(
            {
                "name": compound.preferred_name,
                "formula": compound.formula or "",
                "standard_inchi": compound.standard_inchi or "",
                "standard_inchi_key": compound.standard_inchi_key or "",
                "cas_registry_number": compound.cas_registry_number or "",
            }
        )
    return tuple(components)


def extract_observations(
    documents: Iterable[ThermoMLDocument],
) -> list[DielectricObservation]:
    observations: list[DielectricObservation] = []
    for document in documents:
        for data_set in document.datasets:
            dielectric_properties = {
                prop.number: (prop, property_family(prop.name))
                for prop in data_set.properties
                if property_family(prop.name)
            }
            if not dielectric_properties:
                continue
            components = _components(document, data_set)
            primary = components[0] if components else {}
            for point in data_set.points:
                for property_value in point.property_values:
                    selected = dielectric_properties.get(property_value.number)
                    if selected is None:
                        continue
                    prop, family = selected
                    expanded, standard, kind, confidence = _uncertainty(property_value)
                    frequency = _condition_value(
                        data_set,
                        point,
                        name_fragment="frequency",
                    )
                    if family == "zero_frequency" and frequency is None:
                        frequency = Decimal(0)
                    observations.append(
                        DielectricObservation(
                            source_file=document.provenance.locator or "",
                            source_sha256=document.provenance.sha256,
                            doi=document.citation.normalized_doi or "",
                            title=document.citation.title or "",
                            dataset_number=data_set.number,
                            property_name=prop.name,
                            property_family=family,
                            value=property_value.value,
                            unit="",
                            expanded_uncertainty=expanded,
                            standard_uncertainty=standard,
                            uncertainty_kind=kind,
                            confidence_level=confidence,
                            temperature_k=_condition_value(
                                data_set,
                                point,
                                name_fragment="temperature",
                            ),
                            pressure_kpa=_condition_value(
                                data_set,
                                point,
                                name_fragment="pressure",
                            ),
                            frequency_mhz=frequency,
                            phase=prop.phase or (data_set.phases[0] if data_set.phases else ""),
                            method=prop.method or "",
                            component_count=len(components),
                            is_pure=len(components) == 1,
                            components=components,
                            primary_name=primary.get("name", ""),
                            primary_formula=primary.get("formula", ""),
                            primary_inchi=primary.get("standard_inchi", ""),
                            primary_inchi_key=primary.get("standard_inchi_key", ""),
                        )
                    )
    return observations


def _identity(component: dict[str, str]) -> str:
    for field in ("standard_inchi_key", "standard_inchi", "cas_registry_number"):
        if component[field]:
            return f"{field}:{component[field].upper()}"
    return f"name:{component['name'].casefold()}"


def _unique_components(
    observations: Iterable[DielectricObservation],
) -> dict[str, dict[str, str]]:
    return {
        _identity(component): component
        for observation in observations
        for component in observation.components
    }


def summarize_observations(
    observations: Sequence[DielectricObservation],
    *,
    temperature_center: Decimal = Decimal("298.15"),
    temperature_tolerance: Decimal = Decimal(5),
) -> dict[str, object]:
    by_family = Counter(observation.property_family for observation in observations)
    near_center = [
        observation
        for observation in observations
        if observation.temperature_k is not None
        and abs(observation.temperature_k - temperature_center) <= temperature_tolerance
    ]
    zero_near = [
        observation for observation in near_center if observation.property_family == "zero_frequency"
    ]
    zero_unique = {
        _identity(component)
        for observation in zero_near
        for component in observation.components
    }
    zero_unique_pure = {
        _identity(observation.components[0])
        for observation in zero_near
        if observation.is_pure and observation.components
    }
    near_unique = {
        _identity(component)
        for observation in near_center
        for component in observation.components
    }
    observation_families = Counter(
        classify_solvent_family(component["name"])
        for observation in observations
        for component in observation.components
    )
    unique_components = _unique_components(observations)
    unique_families = Counter(
        classify_solvent_family(component["name"])
        for component in unique_components.values()
    )
    zero_near_families = Counter(
        classify_solvent_family(component["name"])
        for component in _unique_components(zero_near).values()
    )
    pure_zero_near_components = {
        _identity(observation.components[0]): observation.components[0]
        for observation in zero_near
        if observation.is_pure and observation.components
    }
    pure_zero_near_families = Counter(
        classify_solvent_family(component["name"])
        for component in pure_zero_near_components.values()
    )
    target_families = ("carbonate", "ether", "nitrile", "sulfone")
    unique_source_documents = len({observation.source_sha256 for observation in observations})
    return {
        "observation_rows": len(observations),
        "source_documents_with_dielectric_rows": unique_source_documents,
        "property_family_counts": dict(sorted(by_family.items())),
        "temperature_center_k": str(temperature_center),
        "temperature_tolerance_k": str(temperature_tolerance),
        "observations_near_center": len(near_center),
        "unique_components_near_center": len(near_unique),
        "all_component_zero_frequency_components_near_center": len(zero_unique),
        "zero_frequency_observations_near_center": len(zero_near),
        "unique_zero_frequency_components_near_center": len(zero_unique),
        "pure_zero_frequency_components_near_center": len(zero_unique_pure),
        "component_observation_family_counts": dict(sorted(observation_families.items())),
        "unique_component_family_counts": dict(sorted(unique_families.items())),
        "zero_frequency_family_counts_near_center": dict(
            sorted(zero_near_families.items())
        ),
        "pure_zero_frequency_family_counts_near_center": dict(
            sorted(pure_zero_near_families.items())
        ),
        "target_family_components_near_center": sum(
            zero_near_families[family] for family in target_families
        ),
        "pure_target_family_components_near_center": sum(
            pure_zero_near_families[family] for family in target_families
        ),
        "mainline_gate_population": "pure_zero_frequency_components_near_center",
        "mainline_gate_component_count": len(zero_unique_pure),
        "mainline_decision": decide_mainline(len(zero_unique_pure)),
        "mainline_decision_basis": (
            "Counts unique pure components in zero-frequency dielectric "
            f"observations within {temperature_tolerance} K of {temperature_center} K. "
            "Mixture components remain in the all-component zero-frequency census "
            "but do not enter the gate."
        ),
    }


def _load_documents(raw_dir: Path | None, archives: Sequence[Path]) -> list[ThermoMLDocument]:
    documents: list[ThermoMLDocument] = []
    for archive in archives:
        documents.extend(iter_thermoml_archive(archive))
    if documents:
        return documents
    if raw_dir is None or not raw_dir.exists():
        return []
    return [parse_thermoml(path) for path in sorted(raw_dir.rglob("*.xml"))]


def _observation_record(observation: DielectricObservation) -> dict[str, str]:
    value = asdict(observation)
    value["components_json"] = json.dumps(
        value.pop("components"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return {
        key: "" if item is None else str(item)
        for key, item in value.items()
    }


def write_observations_csv(
    observations: Sequence[DielectricObservation],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(_observation_record(observations[0])) if observations else [
        "source_file",
        "source_sha256",
        "doi",
        "title",
        "dataset_number",
        "property_name",
        "property_family",
        "value",
        "unit",
        "expanded_uncertainty",
        "standard_uncertainty",
        "uncertainty_kind",
        "confidence_level",
        "temperature_k",
        "pressure_kpa",
        "frequency_mhz",
        "phase",
        "method",
        "component_count",
        "is_pure",
        "components_json",
        "primary_name",
        "primary_formula",
        "primary_inchi",
        "primary_inchi_key",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_observation_record(observation) for observation in observations)


def _quantile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise ValueError("quantile requires at least one value")
    ordered = sorted(values)
    index = fraction * (len(ordered) - 1)
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _robust_histogram_upper_bound(values: Sequence[float]) -> float:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return 1.0
    upper_bound = _quantile(finite, 0.995)
    return max(1.0, math.ceil(upper_bound / 10) * 10)


def write_eda_plots(
    observations: Sequence[DielectricObservation],
    summary: dict[str, object],
    plot_dir: Path,
) -> tuple[Path, Path]:
    plot_dir.mkdir(parents=True, exist_ok=True)
    zero = [
        float(observation.value)
        for observation in observations
        if observation.property_family == "zero_frequency"
    ]
    various = [
        float(observation.value)
        for observation in observations
        if observation.property_family == "frequency_dependent"
    ]
    temperatures = [
        float(observation.temperature_k)
        for observation in observations
        if observation.temperature_k is not None
    ]
    dielectric_values = zero + various
    dielectric_upper = _robust_histogram_upper_bound(dielectric_values)
    above_upper = sum(value > dielectric_upper for value in dielectric_values)

    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].hist(temperatures, bins=30, color="#2563eb", alpha=0.85)
    axes[0].axvspan(293.15, 303.15, color="#f59e0b", alpha=0.2, label="298.15 ± 5 K")
    axes[0].set_xlabel("Temperature (K)")
    axes[0].set_ylabel("Dielectric observations")
    axes[0].set_title("Temperature coverage")
    axes[0].legend()
    axes[1].hist(
        zero,
        bins=30,
        color="#16a34a",
        alpha=0.75,
        label="zero frequency",
        range=(0.0, dielectric_upper),
    )
    axes[1].hist(
        various,
        bins=30,
        color="#dc2626",
        alpha=0.55,
        label="frequency dependent",
        range=(0.0, dielectric_upper),
    )
    axes[1].set_xlim(0.0, dielectric_upper)
    axes[1].set_xlabel(
        "Relative permittivity "
        f"(99.5th-percentile cap {dielectric_upper:g}; "
        f"{above_upper} values above)"
    )
    axes[1].set_ylabel("Count")
    axes[1].set_title("Dielectric-value distribution")
    axes[1].legend()
    figure.tight_layout()
    distribution_path = plot_dir / "dielectric_distribution.png"
    figure.savefig(distribution_path, dpi=180)
    plt.close(figure)

    family_counts = summary["zero_frequency_family_counts_near_center"]
    assert isinstance(family_counts, dict)
    labels = list(family_counts)
    values = [int(family_counts[label]) for label in labels]
    figure, axis = plt.subplots(figsize=(7, 4.2))
    axis.bar(labels, values, color=["#2563eb", "#0f766e", "#f59e0b", "#dc2626", "#64748b"])
    axis.set_ylabel("Unique components")
    axis.set_title("Near-298 K zero-frequency solvent-family coverage")
    figure.tight_layout()
    family_path = plot_dir / "family_coverage.png"
    figure.savefig(family_path, dpi=180)
    plt.close(figure)
    return distribution_path, family_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        type=Path,
        action="append",
        default=[],
        help="Checksum-verified ThermoML tar archive. May be repeated.",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "raw" / "thermoml",
        help="Fallback directory of individual ThermoML XML files.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "dielectric_raw.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "p1_summary.json",
    )
    parser.add_argument(
        "--plot-dir",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "artifacts",
    )
    parser.add_argument("--temperature-center", type=Decimal, default=Decimal("298.15"))
    parser.add_argument("--temperature-tolerance", type=Decimal, default=Decimal(5))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    documents = _load_documents(args.raw_dir, args.archive)
    if not documents:
        raise SystemExit("No ThermoML documents found. Provide --archive or --raw-dir.")
    observations = extract_observations(documents)
    if not observations:
        raise SystemExit("No relative-permittivity observations found.")
    summary = summarize_observations(
        observations,
        temperature_center=args.temperature_center,
        temperature_tolerance=args.temperature_tolerance,
    )
    summary.update(
        {
            "document_count": len(documents),
            **build_source_metadata(args.archive, raw_dir=args.raw_dir),
        }
    )
    write_observations_csv(observations, args.csv)
    distribution_path, family_path = write_eda_plots(observations, summary, args.plot_dir)
    summary["outputs"] = {
        "dielectric_raw_csv": str(args.csv),
        "summary_json": str(args.summary),
        "dielectric_distribution_png": str(distribution_path),
        "family_coverage_png": str(family_path),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
