"""ThermoML acquisition and parsing utilities.

The parser intentionally uses only the Python standard library. It keeps the
original ThermoML property names and values as strings so downstream code can
decide whether a scientific normalization is appropriate.
"""

from __future__ import annotations

import csv
import errno
import hashlib
import http.client
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if os.name == "nt":
    import msvcrt
else:
    import fcntl

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
    "property_uncertainty_confidence_level",
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
PROVENANCE_SCHEMA_VERSION = 2


class ThermoMLError(ValueError):
    """Raised when a ThermoML document cannot be interpreted safely."""


class DownloadError(RuntimeError):
    """Raised when a source file cannot be downloaded or resumed safely."""


class _ResumeRejected(RuntimeError):
    """Internal signal to discard a partial and retry with a full download."""


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
            "uncertainty_confidence_level": (
                _nested_descendant_text(
                    property_element, "nCombUncertLevOfConfid"
                )
                or _nested_descendant_text(property_element, "nUncertLevOfConfid")
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


def _property_uncertainty(
    property_value: ET.Element,
    default_confidence_level: str,
) -> tuple[str, str, str]:
    standard_value = ""
    expanded_value = ""
    confidence_level = ""
    for descendant in property_value.iter():
        tag = _local_name(descendant.tag)
        value = _text(descendant)
        if not value:
            continue
        if tag in {"nCombStdUncertValue", "nStdUncertValue"} and not standard_value:
            standard_value = value
        elif tag in {"nCombExpandUncertValue", "nExpandUncertValue"} and not expanded_value:
            expanded_value = value
        elif tag in {"nCombUncertLevOfConfid", "nUncertLevOfConfid"}:
            confidence_level = value

    if expanded_value:
        return (
            expanded_value,
            "expanded",
            confidence_level or default_confidence_level,
        )
    if standard_value:
        return standard_value, "standard", ""
    return "", "", ""


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
            (
                property_uncertainty,
                property_uncertainty_kind,
                property_uncertainty_confidence_level,
            ) = _property_uncertainty(
                property_value,
                property_definition.get("uncertainty_confidence_level", ""),
            )
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
                "property_uncertainty": property_uncertainty,
                "property_uncertainty_kind": property_uncertainty_kind,
                "property_uncertainty_confidence_level": (
                    property_uncertainty_confidence_level
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
        "schema_version": PROVENANCE_SCHEMA_VERSION,
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


def _read_resume_metadata(path: Path, url: str) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(metadata, dict) or metadata.get("url") != url:
        return {}
    return metadata


def _resume_validator(metadata: Mapping[str, Any]) -> str:
    etag = str(metadata.get("etag", ""))
    if etag and not etag.startswith("W/"):
        return etag
    return str(metadata.get("last_modified", ""))


def _parse_content_range(value: str, expected_start: int) -> tuple[int, int]:
    invalid_message = f"server returned an invalid Content-Range: {value!r}"
    if not value.startswith("bytes "):
        raise DownloadError(invalid_message)
    try:
        byte_range, total_text = value.removeprefix("bytes ").split("/", 1)
        start_text, end_text = byte_range.split("-", 1)
        start = int(start_text)
        end = int(end_text)
        total = int(total_text)
    except (ValueError, TypeError) as exc:
        raise DownloadError(invalid_message) from exc
    if start != expected_start or end < start or end >= total:
        raise DownloadError(invalid_message)
    return total, end - start + 1


def _content_length(headers: Mapping[str, str]) -> int:
    try:
        value = int(headers.get("Content-Length", ""))
    except (TypeError, ValueError):
        return 0
    return max(value, 0)


def _clear_partial_state(partial_path: Path, metadata_path: Path) -> None:
    partial_path.unlink(missing_ok=True)
    metadata_path.unlink(missing_ok=True)


def _partial_state_matches(partial_path: Path, metadata: Mapping[str, Any]) -> bool:
    if not partial_path.is_file():
        return False
    try:
        expected_size = int(metadata.get("size_bytes", -1))
        expected_sha256 = str(metadata.get("sha256", ""))
    except (TypeError, ValueError):
        return False
    if expected_size != partial_path.stat().st_size or not expected_sha256:
        return False
    return expected_sha256 == sha256_file(partial_path)


_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[Path, threading.Lock] = {}


def _try_os_lock(descriptor: int) -> bool:
    try:
        if os.name == "nt":
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
            return False
        raise
    return True


def _release_os_lock(descriptor: int) -> None:
    try:
        if os.name == "nt":
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError:
        return


@contextmanager
def _destination_lock(lock_path: Path, *, timeout: float) -> Iterator[None]:
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DownloadError(
            f"cannot create lock directory {lock_path.parent}: {exc}"
        ) from exc

    deadline = time.monotonic() + timeout
    with _THREAD_LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(lock_path, threading.Lock())
    if not thread_lock.acquire(timeout=max(0, deadline - time.monotonic())):
        raise DownloadError(f"timed out waiting for thread lock {lock_path}")

    descriptor: int | None = None
    locked = False
    try:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            if os.name == "nt" and os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
        except OSError as exc:
            raise DownloadError(f"cannot open lock {lock_path}: {exc}") from exc

        while not locked:
            try:
                locked = _try_os_lock(descriptor)
            except OSError as exc:
                raise DownloadError(f"cannot lock {lock_path}: {exc}") from exc
            if locked:
                break
            if time.monotonic() >= deadline:
                raise DownloadError(f"timed out waiting for lock {lock_path}")
            time.sleep(0.05)

        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(
                descriptor,
                f"pid={os.getpid()} acquired_at={utc_now_iso()}\n".encode(),
            )
        except OSError as exc:
            raise DownloadError(f"cannot write lock owner {lock_path}: {exc}") from exc

        yield
    finally:
        if descriptor is not None:
            if locked:
                _release_os_lock(descriptor)
            os.close(descriptor)
        thread_lock.release()


destination_lock = _destination_lock


def download_url(
    url: str,
    destination: Path,
    *,
    metadata_path: Path | None = None,
    resume: bool = True,
    dry_run: bool = False,
    force: bool = False,
    timeout: float = 60,
    prepare_destination: Callable[[Path], Path] | None = None,
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

    lock_path = destination.with_name(destination.name + ".lock")
    with _destination_lock(lock_path, timeout=timeout):
        if prepare_destination is not None:
            destination = Path(prepare_destination(destination))
        return _download_url_locked(
            url,
            destination,
            metadata_path=metadata_path,
            resume=resume,
            force=force,
            timeout=timeout,
        )


def _download_url_locked(
    url: str,
    destination: Path,
    *,
    metadata_path: Path,
    resume: bool,
    force: bool,
    timeout: float,
) -> DownloadResult:
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
    partial_metadata_path = partial_path.with_name(partial_path.name + ".meta.json")
    generation = uuid.uuid4().hex
    if not resume:
        _clear_partial_state(partial_path, partial_metadata_path)

    existing_size = partial_path.stat().st_size if partial_path.exists() else 0
    resume_metadata = _read_resume_metadata(partial_metadata_path, url)
    if existing_size and not _partial_state_matches(partial_path, resume_metadata):
        _clear_partial_state(partial_path, partial_metadata_path)
        existing_size = 0
        resume_metadata = {}
    elif not existing_size:
        partial_metadata_path.unlink(missing_ok=True)
        resume_metadata = {}

    resume_validator = _resume_validator(resume_metadata)
    try:
        resume_total_size = int(resume_metadata.get("total_size", 0))
    except (TypeError, ValueError):
        resume_total_size = 0
    resume_requested = bool(existing_size and resume_validator and resume_total_size)
    headers = {
        "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.1",
        "User-Agent": THERMOML_USER_AGENT,
    }
    if resume_requested:
        headers["Range"] = f"bytes={existing_size}-"
        headers["If-Range"] = resume_validator
    request = urllib.request.Request(url, headers=headers)
    etag = ""
    last_modified = ""

    try:
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code != 416 or not resume_requested:
                raise
            exc.close()
            _clear_partial_state(partial_path, partial_metadata_path)
            existing_size = 0
            resume_requested = False
            headers.pop("Range", None)
            headers.pop("If-Range", None)
            response = urllib.request.urlopen(
                urllib.request.Request(url, headers=headers),
                timeout=timeout,
            )

        with response:
            response_status = getattr(response, "status", response.getcode())
            resumed = resume_requested and response_status == 206
            range_length = 0
            if resumed:
                response_total, range_length = _parse_content_range(
                    response.headers.get("Content-Range", ""),
                    existing_size,
                )
                if response_total != resume_total_size:
                    raise DownloadError(
                        "server returned a different total size while resuming: "
                        f"{response_total} != {resume_total_size}"
                    )
                response_total_size = response_total
            elif response_status == 200:
                if resume_requested:
                    _clear_partial_state(partial_path, partial_metadata_path)
                existing_size = 0
                resume_requested = False
                response_total_size = _content_length(response.headers)
            else:
                raise DownloadError(
                    f"server returned unexpected HTTP {response_status} for {url}"
                )

            response_etag = response.headers.get("ETag", "")
            response_last_modified = response.headers.get("Last-Modified", "")
            stored_etag = str(resume_metadata.get("etag", ""))
            stored_last_modified = str(resume_metadata.get("last_modified", ""))
            if (
                resumed
                and resume_validator == stored_etag
                and response_etag
                and response_etag != stored_etag
            ):
                raise _ResumeRejected(
                    "server changed the ETag in a resumed response: "
                    f"{response_etag!r} != {stored_etag!r}"
                )
            if (
                resumed
                and resume_validator == stored_last_modified
                and response_last_modified
                and response_last_modified != stored_last_modified
            ):
                raise _ResumeRejected(
                    "server changed the Last-Modified value in a resumed response: "
                    f"{response_last_modified!r} != {stored_last_modified!r}"
                )
            etag = response_etag or (stored_etag if resumed else "")
            last_modified = response_last_modified or (
                stored_last_modified if resumed else ""
            )

            descriptor, temporary_name = tempfile.mkstemp(
                dir=destination.parent,
                prefix=f".{partial_path.name}.{generation}.",
                suffix=".tmp",
            )
            response_path = Path(temporary_name)
            try:
                bytes_written = 0
                with os.fdopen(descriptor, "wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        bytes_written += len(chunk)

                if resumed and bytes_written != range_length:
                    raise DownloadError(
                        "server returned an incomplete resumed response: "
                        f"{bytes_written} != {range_length} bytes"
                    )
                if response_total_size and (
                    bytes_written + existing_size != response_total_size
                ):
                    raise DownloadError(
                        "server returned a response with the wrong total size: "
                        f"{bytes_written + existing_size} != {response_total_size}"
                    )

                if resumed:
                    with partial_path.open("ab") as handle, response_path.open("rb") as source:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            handle.write(chunk)
                    if (
                        response_total_size
                        and partial_path.stat().st_size != response_total_size
                    ):
                        raise DownloadError(
                            "resumed partial has the wrong final size: "
                            f"{partial_path.stat().st_size} != {response_total_size}"
                        )
                else:
                    if response_total_size and bytes_written != response_total_size:
                        raise DownloadError(
                            "server returned an incomplete full response: "
                            f"{bytes_written} != {response_total_size} bytes"
                        )
                    os.replace(response_path, partial_path)
            finally:
                if response_path.exists():
                    response_path.unlink()

            partial_size = partial_path.stat().st_size
            partial_digest = sha256_file(partial_path)
            _write_metadata(
                partial_metadata_path,
                {
                    "url": url,
                    "generation": generation,
                    "etag": etag,
                    "last_modified": last_modified,
                    "total_size": response_total_size,
                    "size_bytes": partial_size,
                    "sha256": partial_digest,
                },
            )
    except _ResumeRejected:
        _clear_partial_state(partial_path, partial_metadata_path)
        return _download_url_locked(
            url,
            destination,
            metadata_path=metadata_path,
            resume=False,
            force=force,
            timeout=timeout,
        )
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        raise DownloadError(f"download failed for {url}: {exc}") from exc

    # Recovery boundary: a crash after this rename and before metadata_path is
    # written leaves a destination without a valid sidecar. The next run refuses
    # to overwrite it, so recovery requires inspecting or removing that destination.
    os.replace(partial_path, destination)
    partial_metadata_path.unlink(missing_ok=True)
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
        "generation": generation,
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
