"""ThermoML acquisition and parsing utilities.

The parser intentionally uses only the Python standard library. It keeps the
original ThermoML property names and values as strings so downstream code can
decide whether a scientific normalization is appropriate.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

THERMOML_NAMESPACE = "http://www.iupac.org/namespaces/ThermoML"
THERMOML_USER_AGENT = "electrolyte-ml/0.0.0 (+https://trc.nist.gov/ThermoML/)"

CSV_COLUMNS = (
    "source_file",
    "source_url",
    "source_sha256",
    "retrieved_at",
    "thermoml_version_major",
    "thermoml_version_minor",
    "doi",
    "title",
    "data_number",
    "component_count",
    "primary_compound_name",
    "primary_compound_formula",
    "primary_compound_inchi",
    "primary_compound_inchi_key",
    "components_json",
    "property_number",
    "property_name",
    "property_value",
    "property_unit",
    "property_value_digits",
    "property_uncertainty",
    "property_uncertainty_kind",
    "temperature_value",
    "temperature_unit",
    "frequency_value",
    "frequency_unit",
    "phase",
    "method_name",
    "is_dielectric",
    "dielectric_kind",
    "variables_json",
    "constraints_json",
    "source_row_index",
)


class ThermoMLError(ValueError):
    """Raised when a ThermoML document cannot be interpreted safely."""


class DownloadError(RuntimeError):
    """Raised when a source file cannot be downloaded or resumed safely."""


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of one download operation."""

    url: str
    destination: Path
    metadata_path: Path
    status: str
    sha256: str = ""
    size_bytes: int = 0


def utc_now_iso() -> str:
    """Return a second-resolution UTC timestamp with a trailing Z."""

    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local_name(child.tag) == name]


def _first_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _local_name(child.tag) == name:
            return child
    return None


def _first_descendant(element: ET.Element, name: str) -> ET.Element | None:
    for child in element.iter():
        if _local_name(child.tag) == name:
            return child
    return None


def _text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def _nested_text(element: ET.Element, *names: str) -> str:
    current: ET.Element | None = element
    for name in names:
        if current is None:
            return ""
        current = _first_child(current, name)
    return _text(current)


def _nested_descendant_text(element: ET.Element, *names: str) -> str:
    current: ET.Element | None = element
    for name in names:
        if current is None:
            return ""
        current = _first_descendant(current, name)
    return _text(current)


def _split_name_and_unit(raw_name: str) -> tuple[str, str]:
    """Split a ThermoML controlled name without changing the original name."""

    if "," not in raw_name:
        return raw_name, ""
    unit = raw_name.rsplit(",", 1)[1].strip()
    return raw_name, unit


def _property_unit(property_element: ET.Element, property_name: str) -> str:
    for descendant in property_element.iter():
        if _local_name(descendant.tag) in {
            "ePropUnit",
            "sOtherPropUnit",
            "PropertyUnit",
        }:
            explicit_unit = _text(descendant)
            if explicit_unit:
                return explicit_unit
    return _split_name_and_unit(property_name)[1]


def _variable_type_element(variable: ET.Element) -> ET.Element | None:
    variable_type = _first_descendant(variable, "VariableType")
    if variable_type is None:
        return None
    for child in variable_type:
        return child
    return None


def _variable_kind(type_tag: str, raw_type: str) -> str:
    lowered = raw_type.lower()
    if type_tag == "eTemperature" or "temperature" in lowered:
        return "temperature"
    if "frequency" in lowered:
        return "frequency"
    if type_tag == "eComponentComposition" or "fraction" in lowered:
        return "composition"
    return "other"


def _json_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _property_definitions(data_set: ET.Element) -> dict[str, dict[str, str]]:
    definitions: dict[str, dict[str, str]] = {}
    for index, property_element in enumerate(_children(data_set, "Property"), start=1):
        property_number = _text(_first_child(property_element, "nPropNumber")) or str(index)
        raw_name = _nested_descendant_text(property_element, "ePropName")
        definitions[property_number] = {
            "name": raw_name,
            "unit": _property_unit(property_element, raw_name),
            "phase": _nested_descendant_text(property_element, "ePropPhase"),
            "method_name": _nested_descendant_text(property_element, "sMethodName"),
            "uncertainty_kind": (
                "expanded_95"
                if _nested_descendant_text(
                    property_element, "nCombUncertLevOfConfid"
                )
                == "95"
                else "expanded_uncertainty"
            ),
        }
    return definitions


def _compound_registry(root: ET.Element) -> dict[str, dict[str, str]]:
    """Index root-level ThermoML compounds by their original registry number."""

    registry: dict[str, dict[str, str]] = {}
    for compound in _children(root, "Compound"):
        registry_number = _nested_descendant_text(compound, "RegNum", "nOrgNum")
        if not registry_number:
            continue
        common_names = [
            _text(element)
            for element in _children(compound, "sCommonName")
            if _text(element)
        ]
        registry[registry_number] = {
            "registry_number": registry_number,
            "common_name": common_names[0] if common_names else "",
            "all_common_names": _json_compact(common_names),
            "formula": _nested_descendant_text(compound, "sFormulaMolec"),
            "standard_inchi": _nested_descendant_text(compound, "sStandardInChI"),
            "standard_inchi_key": _nested_descendant_text(
                compound, "sStandardInChIKey"
            ),
            "cas_registry_number": _nested_descendant_text(
                compound, "sCASRegistryNum"
            ),
        }
    return registry


def _dataset_components(
    data_set: ET.Element,
    compound_registry: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    components: list[dict[str, str]] = []
    for component in _children(data_set, "Component"):
        registry_number = _nested_descendant_text(component, "RegNum", "nOrgNum")
        metadata = compound_registry.get(registry_number, {})
        components.append(
            {
                "registry_number": registry_number,
                "sample_number": _nested_descendant_text(component, "nSampleNm"),
                "common_name": metadata.get("common_name", ""),
                "formula": metadata.get("formula", ""),
                "standard_inchi": metadata.get("standard_inchi", ""),
                "standard_inchi_key": metadata.get("standard_inchi_key", ""),
                "cas_registry_number": metadata.get("cas_registry_number", ""),
            }
        )
    return components


def _constraint_definitions(
    data_set: ET.Element,
    compound_registry: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    constraints: list[dict[str, str]] = []
    for index, constraint in enumerate(_children(data_set, "Constraint"), start=1):
        constraint_type = _first_descendant(constraint, "ConstraintType")
        type_element = None
        if constraint_type is not None:
            for child in constraint_type:
                type_element = child
                break
        type_tag = _local_name(type_element.tag) if type_element is not None else ""
        raw_type = _text(type_element)
        _, unit = _split_name_and_unit(raw_type)
        registry_number = _nested_descendant_text(
            constraint, "ConstraintID", "RegNum", "nOrgNum"
        )
        constraints.append(
            {
                "number": (
                    _text(_first_child(constraint, "nConstraintNumber")) or str(index)
                ),
                "type_tag": type_tag,
                "raw_type": raw_type,
                "name": raw_type.rsplit(",", 1)[0] if "," in raw_type else raw_type,
                "unit": unit,
                "value": _text(_first_child(constraint, "nConstraintValue")),
                "digits": _text(_first_child(constraint, "nConstrDigits")),
                "kind": _variable_kind(type_tag, raw_type),
                "registry_number": registry_number,
                "component_name": compound_registry.get(registry_number, {}).get(
                    "common_name", ""
                ),
                "phase": _nested_descendant_text(
                    constraint, "ConstraintPhaseID", "eConstraintPhase"
                ),
            }
        )
    return constraints


def _variable_definitions(
    data_set: ET.Element,
    compound_registry: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    definitions: list[dict[str, str]] = []
    for index, variable in enumerate(_children(data_set, "Variable"), start=1):
        variable_number = _text(_first_child(variable, "nVarNumber")) or str(index)
        type_element = _variable_type_element(variable)
        type_tag = _local_name(type_element.tag) if type_element is not None else ""
        raw_type = _text(type_element)
        name, unit = _split_name_and_unit(raw_type)
        registry_number = _nested_descendant_text(
            variable, "VariableID", "RegNum", "nOrgNum"
        )
        definitions.append(
            {
            "number": variable_number,
            "type_tag": type_tag,
            "raw_type": raw_type,
            "name": name,
            "unit": unit,
            "kind": _variable_kind(type_tag, raw_type),
            "registry_number": registry_number,
            "component_name": compound_registry.get(registry_number, {}).get(
                "common_name", ""
            ),
            "phase": _nested_descendant_text(variable, "VarPhaseID", "eVarPhase"),
            }
        )
    return definitions


def _dielectric_kind(property_name: str, frequency_value: str) -> str:
    lowered = property_name.lower()
    if "imaginary part" in lowered:
        return "loss"
    if "zero frequency" in lowered or frequency_value == "0":
        return "static_or_zero_frequency"
    if "various frequencies" in lowered or frequency_value:
        return "frequency_dependent"
    return "dielectric_related"


def _is_dielectric_property(property_name: str) -> bool:
    lowered = property_name.lower()
    return "dielectric" in lowered or "permittivity" in lowered


def _variable_value(element: ET.Element) -> dict[str, str]:
    return {
        "number": _text(_first_child(element, "nVarNumber")),
        "value": _text(_first_child(element, "nVarValue")),
        "digits": _text(_first_child(element, "nVarDigits")),
    }


def _property_uncertainty(property_value: ET.Element) -> str:
    for descendant in property_value.iter():
        if _local_name(descendant.tag) in {
            "nCombExpandUncertValue",
            "nExpandUncertValue",
        }:
            value = _text(descendant)
            if value:
                return value
    return ""


def _parse_data_set(
    data_set: ET.Element,
    *,
    source_name: str,
    source_url: str,
    source_sha256: str,
    retrieved_at: str,
    version_major: str,
    version_minor: str,
    doi: str,
    title: str,
    row_offset: int,
    compound_registry: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    data_number = _text(_first_child(data_set, "nPureOrMixtureDataNumber"))
    data_phase = _nested_text(data_set, "PhaseID", "ePhase")
    properties = _property_definitions(data_set)
    variables = _variable_definitions(data_set, compound_registry)
    constraints = _constraint_definitions(data_set, compound_registry)
    constraints_json = _json_compact(constraints)
    components = _dataset_components(data_set, compound_registry)
    primary_component = components[0] if components else {}
    rows: list[dict[str, str]] = []

    for num_values in _children(data_set, "NumValues"):
        variable_values: dict[str, list[dict[str, str]]] = {}
        for element in _children(num_values, "VariableValue"):
            value = _variable_value(element)
            variable_values.setdefault(value["number"], []).append(value)

        variables_payload: list[dict[str, str]] = []
        for variable in variables:
            candidates = variable_values.get(variable["number"], [])
            value = candidates.pop(0) if candidates else {}
            variables_payload.append(
                {
                    **variable,
                    "value": value.get("value", ""),
                    "digits": value.get("digits", ""),
                }
            )
        variables_json = _json_compact(variables_payload)

        temperature_variable = next(
            (
                variable
                for variable in variables_payload
                if variable["kind"] == "temperature"
            ),
            None,
        )
        frequency_variable = next(
            (
                variable
                for variable in variables_payload
                if variable["kind"] == "frequency"
            ),
            None,
        )
        temperature_constraint = next(
            (
                constraint
                for constraint in constraints
                if constraint["kind"] == "temperature"
            ),
            None,
        )
        frequency_constraint = next(
            (
                constraint
                for constraint in constraints
                if constraint["kind"] == "frequency"
            ),
            None,
        )
        temperature_value = (
            temperature_variable["value"]
            if temperature_variable
            else temperature_constraint["value"]
            if temperature_constraint
            else ""
        )
        temperature_unit = (
            temperature_variable["unit"]
            if temperature_variable and temperature_value
            else temperature_constraint["unit"]
            if temperature_constraint and temperature_value
            else ""
        )
        frequency_value = (
            frequency_variable["value"]
            if frequency_variable
            else frequency_constraint["value"]
            if frequency_constraint
            else ""
        )
        frequency_unit = (
            frequency_variable["unit"]
            if frequency_variable and frequency_value
            else frequency_constraint["unit"]
            if frequency_constraint and frequency_value
            else ""
        )

        row_components = [dict(component) for component in components]
        for component in row_components:
            component["composition"] = []
        composition_by_registry = {
            component["registry_number"]: component for component in row_components
        }
        for variable in variables_payload:
            if variable["kind"] != "composition":
                continue
            component = composition_by_registry.get(variable["registry_number"])
            if component is None:
                continue
            component["composition"].append(
                {
                    "name": variable["name"],
                    "value": variable["value"],
                    "unit": variable["unit"],
                    "digits": variable["digits"],
                }
            )
        components_json = _json_compact(row_components)

        for property_value in _children(num_values, "PropertyValue"):
            property_number = _text(_first_child(property_value, "nPropNumber"))
            property_definition = properties.get(property_number, {})
            property_name = property_definition.get("name", "")
            is_dielectric = _is_dielectric_property(property_name)
            row = {
                "source_file": source_name,
                "source_url": source_url,
                "source_sha256": source_sha256,
                "retrieved_at": retrieved_at,
                "thermoml_version_major": version_major,
                "thermoml_version_minor": version_minor,
                "doi": doi,
                "title": title,
                "data_number": data_number,
                "component_count": str(len(components)),
                "primary_compound_name": primary_component.get("common_name", ""),
                "primary_compound_formula": primary_component.get("formula", ""),
                "primary_compound_inchi": primary_component.get(
                    "standard_inchi", ""
                ),
                "primary_compound_inchi_key": primary_component.get(
                    "standard_inchi_key", ""
                ),
                "components_json": components_json,
                "property_number": property_number,
                "property_name": property_name,
                "property_value": _text(_first_child(property_value, "nPropValue")),
                "property_unit": property_definition.get("unit", ""),
                "property_value_digits": _text(
                    _first_child(property_value, "nPropDigits")
                ),
                "property_uncertainty": _property_uncertainty(property_value),
                "property_uncertainty_kind": property_definition.get(
                    "uncertainty_kind", ""
                ),
                "temperature_value": temperature_value,
                "temperature_unit": temperature_unit,
                "frequency_value": frequency_value,
                "frequency_unit": frequency_unit,
                "phase": property_definition.get("phase") or data_phase,
                "method_name": property_definition.get("method_name", ""),
                "is_dielectric": "true" if is_dielectric else "false",
                "dielectric_kind": (
                    _dielectric_kind(property_name, frequency_value)
                    if is_dielectric
                    else ""
                ),
                "variables_json": variables_json,
                "constraints_json": constraints_json,
                "source_row_index": str(row_offset + len(rows)),
            }
            rows.append(row)
    return rows


def parse_thermoml_bytes(
    data: bytes,
    *,
    source_name: str = "",
    source_url: str = "",
    source_sha256: str = "",
    retrieved_at: str = "",
) -> list[dict[str, str]]:
    """Parse one ThermoML document into a stable row dictionary contract."""

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ThermoMLError(f"invalid XML: {exc}") from exc

    if _local_name(root.tag) != "DataReport":
        raise ThermoMLError(f"expected DataReport root, got {_local_name(root.tag)!r}")

    citation = _first_child(root, "Citation")
    doi = _text(_first_child(citation, "sDOI")) if citation is not None else ""
    title = _text(_first_child(citation, "sTitle")) if citation is not None else ""
    version_major = _nested_text(root, "Version", "nVersionMajor")
    version_minor = _nested_text(root, "Version", "nVersionMinor")
    compound_registry = _compound_registry(root)

    rows: list[dict[str, str]] = []
    for data_set in _children(root, "PureOrMixtureData"):
        rows.extend(
            _parse_data_set(
                data_set,
                source_name=source_name,
                source_url=source_url,
                source_sha256=source_sha256,
                retrieved_at=retrieved_at,
                version_major=version_major,
                version_minor=version_minor,
                doi=doi,
                title=title,
                row_offset=len(rows),
                compound_registry=compound_registry,
            )
        )
    return rows


def parse_thermoml_file(
    path: Path,
    *,
    source_url: str = "",
    source_sha256: str = "",
    retrieved_at: str = "",
) -> list[dict[str, str]]:
    """Parse a local ThermoML file."""

    return parse_thermoml_bytes(
        path.read_bytes(),
        source_name=path.name,
        source_url=source_url,
        source_sha256=source_sha256,
        retrieved_at=retrieved_at,
    )


def build_provenance(
    rows: Sequence[Mapping[str, str]],
    sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build machine-readable provenance for one normalized output batch."""

    return {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "row_count": len(rows),
        "columns": list(CSV_COLUMNS),
        "sources": list(sources),
    }


def _atomic_text_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def write_normalized_csv(
    rows: Iterable[Mapping[str, str]],
    path: Path,
    *,
    columns: Sequence[str] = CSV_COLUMNS,
) -> None:
    """Write rows using the fixed schema, including the header for empty data."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in columns})
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def write_provenance(path: Path, provenance: Mapping[str, Any]) -> None:
    _atomic_text_write(
        path,
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def read_download_metadata(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DownloadError(f"cannot read metadata {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DownloadError(f"metadata {path} is not a JSON object")
    return payload


def _valid_existing_download(
    url: str,
    destination: Path,
    metadata_path: Path,
) -> dict[str, Any] | None:
    if not destination.exists() or not metadata_path.exists():
        return None
    metadata = read_download_metadata(metadata_path)
    if metadata.get("url") != url:
        return None
    current_hash = sha256_file(destination)
    if metadata.get("sha256") != current_hash:
        return None
    return metadata


def _write_metadata(path: Path, metadata: Mapping[str, Any]) -> None:
    _atomic_text_write(
        path,
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def download_url(
    url: str,
    destination: Path,
    *,
    metadata_path: Path | None = None,
    resume: bool = True,
    dry_run: bool = False,
    force: bool = False,
    timeout: float = 60,
) -> DownloadResult:
    """Download a URL atomically, preserving resume data and provenance."""

    destination = Path(destination)
    metadata_path = metadata_path or destination.with_name(
        destination.name + ".meta.json"
    )

    if dry_run:
        status = (
            "skipped"
            if _valid_existing_download(url, destination, metadata_path)
            else "planned"
        )
        return DownloadResult(url, destination, metadata_path, status)

    if destination.exists() and not force:
        metadata = _valid_existing_download(url, destination, metadata_path)
        if metadata is not None:
            return DownloadResult(
                url,
                destination,
                metadata_path,
                "skipped",
                sha256=str(metadata.get("sha256", "")),
                size_bytes=int(metadata.get("size_bytes", destination.stat().st_size)),
            )
        raise DownloadError(
            f"refusing to overwrite {destination}; metadata is missing or invalid"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial_path = destination.with_name(destination.name + ".part")
    if not resume and partial_path.exists():
        partial_path.unlink()

    existing_size = partial_path.stat().st_size if partial_path.exists() else 0
    headers = {
        "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.1",
        "User-Agent": THERMOML_USER_AGENT,
    }
    if existing_size:
        headers["Range"] = f"bytes={existing_size}-"
    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_status = getattr(response, "status", response.getcode())
            resumed = bool(headers) and response_status == 206
            if headers and response_status == 206:
                content_range = response.headers.get("Content-Range", "")
                if not content_range.startswith(f"bytes {existing_size}-"):
                    raise DownloadError(
                        f"server returned an invalid Content-Range: {content_range!r}"
                    )
            if headers and response_status == 200:
                existing_size = 0

            mode = "ab" if resumed else "wb"
            with partial_path.open(mode) as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)

            etag = response.headers.get("ETag", "")
            last_modified = response.headers.get("Last-Modified", "")
    except (urllib.error.URLError, OSError) as exc:
        raise DownloadError(f"download failed for {url}: {exc}") from exc

    os.replace(partial_path, destination)
    digest = sha256_file(destination)
    size_bytes = destination.stat().st_size
    metadata = {
        "url": url,
        "retrieved_at": utc_now_iso(),
        "sha256": digest,
        "size_bytes": size_bytes,
        "http_status": response_status,
        "etag": etag,
        "last_modified": last_modified,
    }
    _write_metadata(metadata_path, metadata)
    return DownloadResult(
        url,
        destination,
        metadata_path,
        "resumed" if existing_size and response_status == 206 else "downloaded",
        sha256=digest,
        size_bytes=size_bytes,
    )
