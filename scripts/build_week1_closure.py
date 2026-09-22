"""Build reproducible Week 1 closure tables from pinned local inputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import urllib.parse
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.standardize import (
    centipoise_to_pascal_second,
    standardize_molecule,
)

THERMOML_SOURCE_BATCH = "live NIST dielectric/permittivity API union"
CHODERA_FALLBACK_DOI = "arXiv:1506.00262"
CHEW_DOI = "10.1186/s13321-024-00820-5"
CHEW_SUPPLEMENT_2_URL = (
    "https://media.springernature.com/original/springer-static/esm/"
    "art%3A10.1186%2Fs13321-024-00820-5/MediaObjects/"
    "13321_2024_820_MOESM2_ESM.csv"
)
CHEW_SUPPLEMENT_3_URL = (
    "https://media.springernature.com/original/springer-static/esm/"
    "art%3A10.1186%2Fs13321-024-00820-5/MediaObjects/"
    "13321_2024_820_MOESM3_ESM.csv"
)
ECW_308_DOI = "10.1002/adfm.202212342"

SPOT_CHECK_COLUMNS = (
    "anchor_id",
    "name",
    "expected_value",
    "reference_value",
    "observed_value",
    "expected_temperature_K",
    "observed_temperature_K",
    "frequency_MHz",
    "tolerance",
    "delta",
    "status",
    "source_doi",
    "source_file",
    "sha256",
    "selection_rule",
    "gate_flags",
    "notes",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _relative_source_file(path: Path) -> str:
    try:
        return path.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return path.name


def _doi_from_thermoml_url(url: str) -> str:
    marker = "/ThermoML/"
    if marker not in url:
        return ""
    suffix = urllib.parse.unquote(url.split(marker, 1)[1])
    return suffix.removesuffix(".xml").strip("/")


def build_thermoml_manifest(
    raw_dir: Path,
    dielectric_row_counts: Mapping[str, int],
) -> list[dict[str, object]]:
    """Verify every XML sidecar and return a portable source manifest."""

    rows: list[dict[str, object]] = []
    for xml_path in sorted(raw_dir.glob("*.xml")):
        metadata_path = xml_path.with_name(xml_path.name + ".meta.json")
        if not metadata_path.is_file():
            raise ValueError(f"missing sidecar for {xml_path}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise TypeError(f"sidecar is not an object: {metadata_path}")

        actual_sha256 = sha256_file(xml_path)
        actual_size = xml_path.stat().st_size
        if metadata.get("sha256") != actual_sha256:
            raise ValueError(f"sidecar SHA256 mismatch for {xml_path}")
        if int(metadata.get("size_bytes", -1)) != actual_size:
            raise ValueError(f"sidecar size mismatch for {xml_path}")

        url = str(metadata.get("url", ""))
        rows.append(
            {
                "source_file": _relative_source_file(xml_path),
                "url": url,
                "doi": _doi_from_thermoml_url(url),
                "retrieved_at": str(metadata.get("retrieved_at", "")),
                "http_status": str(metadata.get("http_status", "")),
                "etag": str(metadata.get("etag", "")),
                "last_modified": str(metadata.get("last_modified", "")),
                "sha256": actual_sha256,
                "size_bytes": str(actual_size),
                "source_batch": THERMOML_SOURCE_BATCH,
                "dielectric_row_count": str(
                    int(dielectric_row_counts.get(actual_sha256, 0))
                ),
            }
        )
    return rows


def _component_names(row: Mapping[str, str]) -> list[str]:
    try:
        components = json.loads(str(row.get("components_json", "[]")))
    except json.JSONDecodeError:
        return []
    if not isinstance(components, list):
        return []
    return [
        str(component.get("name", "")).strip()
        for component in components
        if isinstance(component, dict)
    ]


def choose_spot_check_observation(
    rows: Sequence[dict[str, str]],
    *,
    aliases: Sequence[str],
    property_family: str,
    expected_temperature: float,
    expected_frequency: float,
) -> dict[str, str] | None:
    """Select a matching observation, preferring pure-component evidence."""

    normalized_aliases = {alias.casefold() for alias in aliases}
    candidates: list[tuple[int, dict[str, str]]] = []
    for row_index, row in enumerate(rows):
        names = {name.casefold() for name in _component_names(row)}
        if not names.intersection(normalized_aliases):
            continue
        if row.get("property_family", "") != property_family:
            continue
        try:
            temperature = float(row.get("temperature_k", ""))
            frequency = float(row.get("frequency_mhz", ""))
        except ValueError:
            continue
        if abs(temperature - expected_temperature) > 0.05:
            continue
        if abs(frequency - expected_frequency) > 1e-9:
            continue
        candidates.append((row_index, row))

    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            0 if item[1].get("is_pure") == "True" else 1,
            str(item[1].get("source_file", "")),
            item[0],
        ),
    )[1]


def _spot_check_row(
    *,
    anchor_id: str,
    name: str,
    expected_value: float,
    expected_temperature: float,
    frequency: float,
    tolerance: float,
    selection_rule: str,
    observation: dict[str, str] | None,
) -> dict[str, object]:
    if observation is None:
        return {
            "anchor_id": anchor_id,
            "name": name,
            "expected_value": expected_value,
            "reference_value": expected_value,
            "observed_value": "",
            "expected_temperature_K": expected_temperature,
            "observed_temperature_K": "",
            "frequency_MHz": frequency,
            "tolerance": tolerance,
            "delta": "",
            "status": "not_found",
            "source_doi": "",
            "source_file": "",
            "sha256": "",
            "selection_rule": selection_rule,
            "gate_flags": "not_found",
            "notes": "No matching NIST fallback observation. Manual reference retained.",
        }
    observed = float(observation["value"])
    delta = observed - expected_value
    source_file = Path(observation["source_file"]).name
    return {
        "anchor_id": anchor_id,
        "name": name,
        "expected_value": expected_value,
        "reference_value": expected_value,
        "observed_value": observed,
        "expected_temperature_K": expected_temperature,
        "observed_temperature_K": observation["temperature_k"],
        "frequency_MHz": frequency,
        "tolerance": tolerance,
        "delta": delta,
        "status": "pass" if abs(delta) <= tolerance else "fail",
        "source_doi": observation["doi"],
        "source_file": f"data/raw/thermoml/{source_file}",
        "sha256": observation["source_sha256"],
        "selection_rule": selection_rule,
        "gate_flags": (
            f"{observation['property_family']}|"
            f"{'pure_component' if observation.get('is_pure') == 'True' else 'mixture_only'}"
        ),
        "notes": "Value parsed directly from the pinned ThermoML XML.",
    }


def build_spot_check_rows(
    observations: Sequence[dict[str, str]],
) -> list[dict[str, object]]:
    anchors = (
        {
            "anchor_id": "water_297K",
            "name": "water",
            "aliases": ("water",),
            "property_family": "zero_frequency",
            "expected_value": 78.4,
            "expected_temperature": 297.15,
            "frequency": 0.0,
            "tolerance": 0.5,
            "selection_rule": (
                "Exact component name; zero-frequency; 297.15 K; prefer pure component."
            ),
        },
        {
            "anchor_id": "acetonitrile_298K_1MHz",
            "name": "acetonitrile",
            "aliases": ("acetonitrile",),
            "property_family": "frequency_dependent",
            "expected_value": 35.9,
            "expected_temperature": 298.15,
            "frequency": 1.0,
            "tolerance": 0.5,
            "selection_rule": (
                "Exact component name; frequency-dependent 1 MHz; 298.15 K; "
                "prefer pure component."
            ),
        },
        {
            "anchor_id": "sulfolane_303K",
            "name": "sulfolane",
            "aliases": ("sulfolane",),
            "property_family": "zero_frequency",
            "expected_value": 43.3,
            "expected_temperature": 303.15,
            "frequency": 0.0,
            "tolerance": 0.5,
            "selection_rule": (
                "Exact component name; zero-frequency; 303.15 K; prefer pure component."
            ),
        },
        {
            "anchor_id": "dmc_298K",
            "name": "dimethyl carbonate",
            "aliases": ("dimethyl carbonate", "dmc"),
            "property_family": "zero_frequency",
            "expected_value": 3.09,
            "expected_temperature": 298.15,
            "frequency": 0.0,
            "tolerance": 0.05,
            "selection_rule": (
                "Exact component name; zero-frequency; 298.15 K; prefer pure component."
            ),
        },
        {
            "anchor_id": "methanol_298K",
            "name": "methanol",
            "aliases": ("methanol",),
            "property_family": "zero_frequency",
            "expected_value": 32.6,
            "expected_temperature": 298.15,
            "frequency": 0.0,
            "tolerance": 0.2,
            "selection_rule": (
                "Exact component name; zero-frequency; 298.15 K; prefer pure component."
            ),
        },
        {
            "anchor_id": "propylene_carbonate_298K",
            "name": "propylene carbonate",
            "aliases": ("propylene carbonate", "pc"),
            "property_family": "zero_frequency",
            "expected_value": 64.9,
            "expected_temperature": 298.15,
            "frequency": 0.0,
            "tolerance": 0.5,
            "selection_rule": (
                "Exact component name; zero-frequency; 298.15 K; no manual row is fabricated."
            ),
        },
    )
    rows: list[dict[str, object]] = []
    for anchor in anchors:
        observation = choose_spot_check_observation(
            observations,
            aliases=anchor["aliases"],
            property_family=anchor["property_family"],
            expected_temperature=anchor["expected_temperature"],
            expected_frequency=anchor["frequency"],
        )
        rows.append(
            _spot_check_row(
                anchor_id=anchor["anchor_id"],
                name=anchor["name"],
                expected_value=anchor["expected_value"],
                expected_temperature=anchor["expected_temperature"],
                frequency=anchor["frequency"],
                tolerance=anchor["tolerance"],
                selection_rule=anchor["selection_rule"],
                observation=observation,
            )
        )

    rows.append(
        {
            "anchor_id": "ethylene_carbonate_temperature_guard",
            "name": "ethylene carbonate",
            "expected_value": "",
            "reference_value": "",
            "observed_value": "",
            "expected_temperature_K": "",
            "observed_temperature_K": "",
            "frequency_MHz": "",
            "tolerance": "",
            "delta": "",
            "status": "blocked_temperature_gate",
            "source_doi": "",
            "source_file": "",
            "sha256": "",
            "selection_rule": (
                "Do not accept EC as a liquid pure solvent near 298.15 K because its "
                "melting point is about 309.5 K."
            ),
            "gate_flags": "temperature_gate|exclude_liquid_298K",
            "notes": (
                "Guard row retained so the near-298 K liquid gate cannot silently admit EC."
            ),
        }
    )
    return rows


def build_coverage_gap_rows(
    chodera_rows: Sequence[dict[str, str]],
    viscosity_inchikeys: set[str],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    rows: list[dict[str, object]] = []
    unique_keys: set[str] = set()
    for index, source_row in enumerate(chodera_rows, start=1):
        smiles = source_row.get("smiles", "").strip()
        standardized = standardize_molecule(smiles)
        unique_keys.add(standardized.inchikey)
        viscosity_available = standardized.inchikey in viscosity_inchikeys
        missing_properties = "" if viscosity_available else "viscosity"
        rows.append(
            {
                "target_record_id": f"chodera2015:{index:04d}",
                "target_set": "chodera_2015_historical_fallback",
                "inchikey": standardized.inchikey,
                "smiles": standardized.smiles,
                "name": source_row.get("components", ""),
                "T_K": source_row.get("Temperature, K", ""),
                "dielectric_available": "true",
                "viscosity_available": str(viscosity_available).lower(),
                "missing_properties": missing_properties,
                "source_doi": CHODERA_FALLBACK_DOI,
                "gate_flags": (
                    "historical_fallback_target|target_308_unavailable|"
                    + ("experimental" if viscosity_available else "missing_viscosity")
                ),
            }
        )

    viscosity_overlap = unique_keys.intersection(viscosity_inchikeys)
    summary = {
        "target_308_available": False,
        "target_308_doi": ECW_308_DOI,
        "fallback_target_set": "chodera_2015_historical_fallback",
        "fallback_target_rows": len(rows),
        "fallback_unique_inchikeys": len(unique_keys),
        "fallback_unique_smiles": len({row["smiles"] for row in rows}),
        "fallback_dielectric_available_rows": len(rows),
        "fallback_viscosity_available_rows": sum(
            row["viscosity_available"] == "true" for row in rows
        ),
        "fallback_viscosity_overlap_inchikeys": len(viscosity_overlap),
        "target_308_investigation_evidence": [
            {
                "source": "Crossref",
                "url": f"https://api.crossref.org/works/{ECW_308_DOI}",
                "result": "No dataset relation or open component DOI found.",
            },
            {
                "source": "OpenAlex",
                "url": f"https://api.openalex.org/works/https://doi.org/{ECW_308_DOI}",
                "result": "is_oa=false; no repository full text.",
            },
            {
                "source": "Unpaywall",
                "url": (
                    "https://api.unpaywall.org/v2/"
                    f"{ECW_308_DOI}?email=codex%40openai.com"
                ),
                "result": "is_oa=false; no repository copy.",
            },
            {
                "source": "DataCite",
                "url": (
                    "https://api.datacite.org/dois?query="
                    "10.1002%2Fadfm.202212342&page%5Bsize%5D=20"
                ),
                "result": "No machine-readable dataset record found.",
            },
            {
                "source": "Wiley article page",
                "url": f"https://advanced.onlinelibrary.wiley.com/doi/{ECW_308_DOI}",
                "result": "HTTP 403 with Cloudflare challenge.",
            },
            {
                "source": "ANSTO repository",
                "url": "https://apo.ansto.gov.au/handle/10238/16701",
                "result": "Metadata only; no data attachment found.",
            },
        ],
        "limitation": (
            "The 308-solvent ECW target list is not openly available in a machine-readable "
            "form. Chodera 2015 is an explicit historical fallback, not a 308-row target."
        ),
    }
    return rows, summary


def build_viscosity_rows(
    source_rows: Sequence[dict[str, str]],
) -> tuple[list[dict[str, object]], set[str]]:
    rows: list[dict[str, object]] = []
    inchikeys: set[str] = set()
    for source_row in source_rows:
        standardized = standardize_molecule(source_row["CANON_SMILES"])
        inchikeys.add(standardized.inchikey)
        viscosity_cp = Decimal(source_row["Viscosity (cP)"])
        viscosity_pa_s = centipoise_to_pascal_second(viscosity_cp)
        rows.append(
            {
                "record_id": source_row["Index"],
                "name": source_row["Name"],
                "smiles": standardized.smiles,
                "inchikey": standardized.inchikey,
                "T_K": source_row["Temperature (K)"],
                "inverse_temperature_1_K": source_row["Inverse temperature (1/K)"],
                "viscosity_cP": source_row["Viscosity (cP)"],
                "viscosity_Pa_s": str(viscosity_pa_s),
                "log10_viscosity_cP": source_row["log(Viscosity)"],
                "md_density_g_cm3": source_row["MD_density"],
                "reference": source_row["Reference"],
                "source_doi": CHEW_DOI,
                "source_url": CHEW_SUPPLEMENT_2_URL,
                "data_status": "experimental",
                "gate_flags": "experimental",
            }
        )
    return rows, inchikeys


def build_viscosity_prediction_rows(
    source_rows: Sequence[dict[str, str]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source_row in source_rows:
        standardized = standardize_molecule(source_row["CANON_SMILES"])
        log_value = Decimal(source_row["EdgePool_log(Viscosity)_pred"])
        predicted_pa_s = (Decimal(10) ** log_value) * Decimal("0.001")
        rows.append(
            {
                "record_id": source_row["Index"],
                "solvent_name": source_row["Solvent Name"],
                "smiles": standardized.smiles,
                "inchikey": standardized.inchikey,
                "T_K": source_row["Temperature (K)"],
                "inverse_temperature_1_K": source_row["Inverse temperature (1/K)"],
                "predicted_log10_viscosity_cP": source_row[
                    "EdgePool_log(Viscosity)_pred"
                ],
                "predicted_viscosity_Pa_s": str(predicted_pa_s),
                "is_within_training": source_row["is_within_training"],
                "source_doi": CHEW_DOI,
                "source_url": CHEW_SUPPLEMENT_3_URL,
                "data_status": "predicted",
                "gate_flags": "predicted",
            }
        )
    return rows


def _experimental_viscosity_groups(
    rows: Sequence[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row["inchikey"])].append(row)
    return groups


def build_intersection(
    observations: Sequence[dict[str, str]],
    viscosity_rows: Sequence[dict[str, object]],
    *,
    temperature_center: float = 298.15,
    temperature_tolerance: float = 5.0,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    viscosity_groups = _experimental_viscosity_groups(viscosity_rows)
    dielectric_by_key: dict[str, list[tuple[int, dict[str, str], dict[str, Any]]]] = (
        defaultdict(list)
    )
    all_keys: set[str] = set()
    pure_keys: set[str] = set()

    for row_index, observation in enumerate(observations):
        if observation.get("property_family") != "zero_frequency":
            continue
        try:
            temperature = float(observation["temperature_k"])
        except ValueError:
            continue
        if abs(temperature - temperature_center) > temperature_tolerance:
            continue
        try:
            components = json.loads(observation["components_json"])
        except json.JSONDecodeError:
            continue
        if not isinstance(components, list):
            continue
        for component in components:
            if not isinstance(component, dict):
                continue
            inchikey = str(component.get("standard_inchi_key", "")).upper()
            if not inchikey:
                continue
            all_keys.add(inchikey)
            if observation.get("is_pure") == "True":
                pure_keys.add(inchikey)
            dielectric_by_key[inchikey].append((row_index, observation, component))

    matched_keys = set(dielectric_by_key).intersection(viscosity_groups)
    mixture_only_keys = matched_keys.difference(pure_keys)
    intersection_rows: list[dict[str, object]] = []
    unique_dielectric_rows: set[int] = set()

    for inchikey in sorted(matched_keys):
        candidates = dielectric_by_key[inchikey]
        pure_candidates = [
            candidate for candidate in candidates if candidate[1].get("is_pure") == "True"
        ]
        selected = pure_candidates or candidates
        for row_index, observation, component in selected:
            dielectric_temperature = float(observation["temperature_k"])
            viscosity = min(
                viscosity_groups[inchikey],
                key=lambda row: (
                    abs(float(row["T_K"]) - dielectric_temperature),
                    int(str(row["record_id"])),
                ),
            )
            viscosity_temperature = float(viscosity["T_K"])
            temperature_delta = viscosity_temperature - dielectric_temperature
            if abs(temperature_delta) > temperature_tolerance:
                continue
            is_pure = observation.get("is_pure") == "True"
            unique_dielectric_rows.add(row_index)
            intersection_rows.append(
                {
                    "pair_id": (
                        f"p1visc:{inchikey}:{row_index}:{viscosity['record_id']}"
                    ),
                    "inchikey": inchikey,
                    "smiles": viscosity["smiles"],
                    "name": component.get("name", ""),
                    "T_dielectric_K": observation["temperature_k"],
                    "T_viscosity_K": viscosity["T_K"],
                    "temperature_delta_K": temperature_delta,
                    "dielectric": observation["value"],
                    "viscosity_cP": viscosity["viscosity_cP"],
                    "viscosity_Pa_s": viscosity["viscosity_Pa_s"],
                    "dielectric_source_doi": observation["doi"],
                    "viscosity_source_doi": CHEW_DOI,
                    "dielectric_source_file": (
                        f"data/raw/thermoml/{Path(observation['source_file']).name}"
                    ),
                    "dielectric_sha256": observation["source_sha256"],
                    "p1_is_pure": str(is_pure).lower(),
                    "selection_tier": "pure_component" if is_pure else "mixture_only",
                    "pair_type": "loose_join",
                    "model_ready": "false",
                    "exact_temperature_match": str(
                        abs(temperature_delta) <= 1e-12
                    ).lower(),
                    "gate_flags": (
                        "experimental|temperature_delta_le_5K|"
                        + ("pure_component" if is_pure else "mixture_only")
                        + "|not_training_ready"
                    ),
                }
            )

    intersection_rows.sort(
        key=lambda row: (
            abs(float(row["temperature_delta_K"])),
            str(row["name"]).casefold(),
            str(row["pair_id"]),
        )
    )
    summary = {
        "temperature_center_K": temperature_center,
        "temperature_tolerance_K": temperature_tolerance,
        "p1_zero_frequency_near_center_rows": sum(
            observation.get("property_family") == "zero_frequency"
            and observation.get("temperature_k", "") != ""
            and abs(float(observation["temperature_k"]) - temperature_center)
            <= temperature_tolerance
            for observation in observations
        ),
        "p1_all_component_compound_level_intersection": len(matched_keys),
        "p1_pure_component_compound_level_intersection": len(matched_keys & pure_keys),
        "p1_mixture_only_compound_level_intersection": len(mixture_only_keys),
        "all_component_zero_frequency_keys_near_center": len(all_keys),
        "pure_component_zero_frequency_keys_near_center": len(pure_keys),
        "supplement_2_experimental_rows": len(viscosity_rows),
        "supplement_2_unique_inchikeys": len(viscosity_groups),
        "paired_row_unique_inchikeys": len(
            {str(row["inchikey"]) for row in intersection_rows}
        ),
        "paired_row_intersection_count": len(intersection_rows),
        "unique_p1_dielectric_rows_paired": len(unique_dielectric_rows),
        "max_abs_temperature_delta_K": max(
            (abs(float(row["temperature_delta_K"])) for row in intersection_rows),
            default=None,
        ),
        "model_ready": False,
        "pair_type": "loose_join",
        "interpretation": (
            "This table establishes coverage and supports exploratory joins. It is "
            "not a joint-training table because dielectric and viscosity temperatures "
            "are paired within a tolerance rather than observed as one exact row."
        ),
        "selection_strategy": (
            "Use pure-component P1 zero-frequency rows for an InChIKey when any exist; "
            "otherwise allow mixture-only rows. Pair every selected P1 row to the supp2 "
            "experimental viscosity row with minimum absolute temperature difference <=5 K."
        ),
        "loose_two_table_recommendation": (
            "Use the intersection for coverage and exploratory joins, but prefer a "
            "dual-label single table at matched temperatures (or a documented temperature "
            "model) before modeling dielectric and viscosity together."
        ),
        "source_notes": [
            "Only Chew supplement 2 is experimental viscosity.",
            (
                "Chew supplement 3 contains model predictions and is excluded from pairing."
            ),
            (
                "The public supplement has 3,582 experimental rows; the paper reports a "
                "4,440-row source dataset with the remainder withheld for copyright reasons."
            ),
        ],
    }
    return intersection_rows, summary


def _dielectric_row_counts(
    observations: Sequence[dict[str, str]],
) -> dict[str, int]:
    counts = Counter(observation["source_sha256"] for observation in observations)
    return dict(counts)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "raw" / "thermoml",
    )
    parser.add_argument(
        "--dielectric",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "dielectric_raw.csv",
    )
    parser.add_argument(
        "--chodera",
        type=Path,
        default=(
            REPOSITORY_ROOT / "data" / "external" / "chodera_2015_data_dielectric.csv"
        ),
    )
    parser.add_argument(
        "--viscosity",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "data"
            / "external"
            / "chew_2024_viscosity_supp_2.csv"
        ),
    )
    parser.add_argument(
        "--viscosity-predictions",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "data"
            / "external"
            / "chew_2024_viscosity_supp_3.csv"
        ),
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed",
    )
    parser.add_argument(
        "--p1-summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "p1_summary.json",
    )
    parser.add_argument(
        "--viscosity-summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "p3_viscosity_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    observations = read_csv_rows(args.dielectric)
    chodera_rows = read_csv_rows(args.chodera)
    viscosity_source_rows = read_csv_rows(args.viscosity)
    prediction_source_rows = read_csv_rows(args.viscosity_predictions)

    manifest = build_thermoml_manifest(
        args.raw_dir,
        _dielectric_row_counts(observations),
    )
    spot_check = build_spot_check_rows(observations)
    viscosity_rows, viscosity_inchikeys = build_viscosity_rows(viscosity_source_rows)
    prediction_rows = build_viscosity_prediction_rows(prediction_source_rows)
    coverage_rows, coverage_summary = build_coverage_gap_rows(
        chodera_rows,
        viscosity_inchikeys,
    )
    intersection_rows, intersection_summary = build_intersection(
        observations,
        viscosity_rows,
    )

    processed = args.processed_dir
    write_csv_rows(
        processed / "thermoml_source_manifest.csv",
        (
            "source_file",
            "url",
            "doi",
            "retrieved_at",
            "http_status",
            "etag",
            "last_modified",
            "sha256",
            "size_bytes",
            "source_batch",
            "dielectric_row_count",
        ),
        manifest,
    )
    write_csv_rows(processed / "p1_spot_check.csv", SPOT_CHECK_COLUMNS, spot_check)
    write_csv_rows(
        processed / "coverage_gap.csv",
        (
            "target_record_id",
            "target_set",
            "inchikey",
            "smiles",
            "name",
            "T_K",
            "dielectric_available",
            "viscosity_available",
            "missing_properties",
            "source_doi",
            "gate_flags",
        ),
        coverage_rows,
    )
    write_json(processed / "coverage_gap_summary.json", coverage_summary)
    write_csv_rows(
        processed / "viscosity_raw.csv",
        (
            "record_id",
            "name",
            "smiles",
            "inchikey",
            "T_K",
            "inverse_temperature_1_K",
            "viscosity_cP",
            "viscosity_Pa_s",
            "log10_viscosity_cP",
            "md_density_g_cm3",
            "reference",
            "source_doi",
            "source_url",
            "data_status",
            "gate_flags",
        ),
        viscosity_rows,
    )
    write_csv_rows(
        processed / "viscosity_predictions.csv",
        (
            "record_id",
            "solvent_name",
            "smiles",
            "inchikey",
            "T_K",
            "inverse_temperature_1_K",
            "predicted_log10_viscosity_cP",
            "predicted_viscosity_Pa_s",
            "is_within_training",
            "source_doi",
            "source_url",
            "data_status",
            "gate_flags",
        ),
        prediction_rows,
    )
    write_csv_rows(
        processed / "dielectric_viscosity_intersection.csv",
        (
            "pair_id",
            "inchikey",
            "smiles",
            "name",
            "T_dielectric_K",
            "T_viscosity_K",
            "temperature_delta_K",
            "dielectric",
            "viscosity_cP",
            "viscosity_Pa_s",
            "dielectric_source_doi",
            "viscosity_source_doi",
            "dielectric_source_file",
            "dielectric_sha256",
            "p1_is_pure",
            "selection_tier",
            "pair_type",
            "model_ready",
            "exact_temperature_match",
            "gate_flags",
        ),
        intersection_rows,
    )

    coverage_summary.update(
        {
            "manifest_rows": len(manifest),
            "manifest_dielectric_source_rows": sum(
                int(row["dielectric_row_count"]) > 0 for row in manifest
            ),
            "spot_check_rows": len(spot_check),
            "spot_check_pass_rows": sum(row["status"] == "pass" for row in spot_check),
            "spot_check_not_found_rows": sum(
                row["status"] == "not_found" for row in spot_check
            ),
            "viscosity_experimental_rows": len(viscosity_rows),
            "viscosity_prediction_rows": len(prediction_rows),
            "intersection_summary": intersection_summary,
        }
    )
    write_json(processed / "coverage_gap_summary.json", coverage_summary)
    write_json(args.viscosity_summary, intersection_summary)

    p1_summary = json.loads(args.p1_summary.read_text(encoding="utf-8"))
    p1_summary["week1_closure"] = {
        "thermoml_manifest_rows": len(manifest),
        "thermoml_sources_with_dielectric_rows": coverage_summary[
            "manifest_dielectric_source_rows"
        ],
        "spot_check_status_counts": dict(
            Counter(str(row["status"]) for row in spot_check)
        ),
        "target_308_available": False,
        "coverage_fallback_rows": len(coverage_rows),
        "viscosity_experimental_rows": len(viscosity_rows),
        "viscosity_prediction_rows": len(prediction_rows),
        "dielectric_viscosity_intersection_rows": len(intersection_rows),
        "dielectric_viscosity_compound_intersection": intersection_summary[
            "p1_all_component_compound_level_intersection"
        ],
        "decision_status": "provisional",
    }
    write_json(args.p1_summary, p1_summary)

    print(
        json.dumps(
            {
                "manifest_rows": len(manifest),
                "manifest_dielectric_source_rows": coverage_summary[
                    "manifest_dielectric_source_rows"
                ],
                "spot_check_rows": len(spot_check),
                "coverage_gap_rows": len(coverage_rows),
                "coverage_gap_unique_keys": coverage_summary[
                    "fallback_unique_inchikeys"
                ],
                "viscosity_experimental_rows": len(viscosity_rows),
                "viscosity_prediction_rows": len(prediction_rows),
                "intersection_rows": len(intersection_rows),
                "intersection_compound_keys": intersection_summary[
                    "p1_all_component_compound_level_intersection"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
