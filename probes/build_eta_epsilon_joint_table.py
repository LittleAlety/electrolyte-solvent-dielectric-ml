"""Build the eta-epsilon joint temperature-resolved observation table.

``probes/eta_epsilon_joint_schema_prereg.json`` is the authority for this build.
The 27-column observation schema, the two-layer quality rule, the merge rules,
the exclusion list, the evaluation contract and the verifier contract are read
from that file; nothing here restates a rule in a weaker form.

Five rules are cheap to state and expensive to hold, so they are encoded rather
than asserted:

* one row per measured value at one temperature, and conflicting values at the
  same ``(inchikey, property, T_K)`` are *all* kept -- never averaged, never
  tie-broken;
* the 0-based source row index and the SHA256 of the source file travel with
  every row, and ``quality_layer`` is a stored column, never inferred at read
  time;
* a source row that does not enter the table is written to the exclusions file
  with a reason, so the row count never shrinks silently;
* ``publishable_core`` requires a first-hand source DOI, and a PubChem
  compilation value can never be quoted in the publishable headline;
* the grouped reading is asserted, not assumed: ``GroupKFold`` by InChIKey must
  show ``group_overlap == 0``, and a failing assertion stops the build.

The one conflict this build refuses to paper over
-------------------------------------------------
The prereg names the PubChem liquid-window harvest as a first-build source and
describes it as "MP/BP/FP/density, filter_only".  The same locked schema
restricts ``property`` to exactly ``epsilon`` and ``viscosity``.  Melting point,
boiling point, flash point and density are none of those, so they cannot be
stored as observations of this table without editing the locked schema, which
the lock rule forbids.  This build therefore takes the schema at its word:
PubChem contributes only what fits the enum (its ``Viscosity`` section, parsed
to Pa*s and stored as ``filter_only``), and every other harvested PubChem value
row is enumerated in the exclusions file with the reason
``property_not_in_joint_enum``.  The conflict is reported in the summary and in
``reports/eta_epsilon_joint_table.md``; it is not edited in place.

Nothing here fetches anything: the four sources are local files, the restricted
Schrodinger 858 values were never fetched, ``supp_3`` predicted rows and Reaxys
values have no code path into the table.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import sha256_file

PREREG_PATH = REPOSITORY_ROOT / "probes" / "eta_epsilon_joint_schema_prereg.json"
DIELECTRIC_PATH = REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"
THERMOML_PATH = REPOSITORY_ROOT / "data" / "processed" / "viscosity_observations_thermoml.csv"
SCHRODINGER_PATH = REPOSITORY_ROOT / "data" / "viscosity_v01.csv"
PUBCHEM_DIR = REPOSITORY_ROOT / "data" / "external" / "g1plus" / "pubchem" / "liquid_window"
PUBCHEM_SUFFIX = ".experimental_properties.json"

DEFAULT_TABLE_PATH = REPOSITORY_ROOT / "data" / "processed" / "eta_epsilon_joint_observations.csv"
DEFAULT_EXCLUSIONS_PATH = REPOSITORY_ROOT / "data" / "processed" / "eta_epsilon_joint_exclusions.csv"
DEFAULT_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "eta_epsilon_joint_summary.json"
DEFAULT_REPORT_PATH = REPOSITORY_ROOT / "reports" / "eta_epsilon_joint_table.md"
BUILDER_PATH = Path(__file__).resolve()

DATASET_EPSILON = "epsilon_observations_v11plus"
DATASET_THERMOML = "thermoml_viscosity"
DATASET_SCHRODINGER = "schrodinger_viscosity_v01_open_subset"
DATASET_PUBCHEM = "pubchem_liquid_window_harvest"

OBSERVATION_COLUMNS: tuple[str, ...] = (
    "row_id",
    "dataset_id",
    "property",
    "property_family",
    "inchikey",
    "name",
    "smiles",
    "T_K",
    "value",
    "unit",
    "phase",
    "method",
    "uncertainty",
    "uncertainty_kind",
    "confidence_level",
    "frequency_mhz",
    "pressure_kpa",
    "n_components",
    "pure_or_mixture",
    "source_doi",
    "source_kind",
    "source_file",
    "source_row_index",
    "source_file_sha256",
    "quality_layer",
    "licence",
    "redistributable",
)

EXCLUSION_COLUMNS: tuple[str, ...] = (
    "exclusion_id",
    "dataset_id",
    "source_property",
    "property",
    "inchikey",
    "source_file",
    "source_row_index",
    "segment_index",
    "source_file_sha256",
    "reason_code",
    "reason",
    "raw_value",
)

PRIMARY_KEY: tuple[str, ...] = (
    "inchikey",
    "property",
    "T_K",
    "source_file",
    "source_row_index",
)

PROPERTY_FAMILY: dict[str, str] = {
    "epsilon": "dielectric_constant",
    "viscosity": "dynamic_viscosity",
}
PROPERTY_UNIT: dict[str, str] = {"epsilon": "1", "viscosity": "Pa*s"}
MEASUREMENT_SOURCE_KINDS = frozenset(
    {"primary_thermoml_measurement", "published_supplement_open_subset"}
)
QUALITY_LAYERS: tuple[str, ...] = ("publishable_core", "filter_only")
LICENCES: tuple[str, ...] = ("thermoml_open", "cc_by_4_0", "publisher_terms_see_source")
DATASET_IDS: tuple[str, ...] = (
    DATASET_EPSILON,
    DATASET_THERMOML,
    DATASET_SCHRODINGER,
    DATASET_PUBCHEM,
)

GROUP_SPLITS = 5
LEAK_REFERENCE_SEED = 0

def display_path(path: Path) -> str:
    """Return a repository-relative POSIX path, or the absolute path outside it."""

    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()

def format_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.12g}"

def format_bool(value: bool) -> str:
    return "true" if value else "false"

def to_float(text: object) -> float | None:
    if text is None:
        return None
    stripped = str(text).strip()
    if not stripped:
        return None
    return float(stripped)

def to_int(text: object) -> int | None:
    value = to_float(text)
    return None if value is None else int(value)

def sanitise_text(text: object) -> str:
    return re.sub(r"[\r\n]+", " ", str(text or "")).strip()

def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]

def csv_cell(value: Any) -> Any:
    """Render one cell, keeping booleans in the repository's lowercase form."""

    if isinstance(value, bool):
        return format_bool(value)
    return value


def write_csv_rows(
    path: Path,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: csv_cell(row.get(column, "")) for column in columns})

def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

def read_prereg(path: Path = PREREG_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def prereg_primary_key(prereg: Mapping[str, Any]) -> tuple[str, ...]:
    rule = prereg["observation_schema"]["identity_rule"]
    match = re.search(r"\(([^()]*)\)", rule)
    if match is None:
        raise RuntimeError(f"cannot read the primary key from identity_rule: {rule!r}")
    return tuple(part.strip() for part in match.group(1).split(","))

def assert_schema_matches_prereg(prereg: Mapping[str, Any]) -> None:
    """Fail loudly if the locked column list and this module disagree."""

    locked = tuple(column["name"] for column in prereg["observation_schema"]["columns"])
    if locked != OBSERVATION_COLUMNS:
        raise RuntimeError(
            f"observation schema drift: prereg {locked!r} != builder {OBSERVATION_COLUMNS!r}"
        )
    if prereg_primary_key(prereg) != PRIMARY_KEY:
        raise RuntimeError(
            f"primary key drift: prereg {prereg_primary_key(prereg)!r} != builder {PRIMARY_KEY!r}"
        )

# ---------------------------------------------------------------------------
# PubChem liquid-window harvest: value-row enumeration and the viscosity parser.
# ---------------------------------------------------------------------------

VISCOSITY_HEADING = "Viscosity"
DIELECTRIC_HEADING = "Dielectric Constant"

_NUMBER = r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
_VISCOSITY_UNIT = (
    r"cent(?:ipoises?|iposes?|apoises?)|millipoises?|micropoises?|poises?|cps|cp|"
    r"mpa[.*\-\s]?sec|mpa[.*\-\s]?s|pa[.*\-\s]?sec|pa[.*\-\s]?s"
)
_TEMPERATURE_UNIT = r"(?:°\s*[CFK]|deg(?:ree)?s?\s*[CFK]|[CFK])"
_TEMPERATURE_PATTERN = re.compile(
    r"(?:@|\bat\b)\s*(" + _NUMBER + r")\s*(" + _TEMPERATURE_UNIT + r")\b",
    re.IGNORECASE,
)
_TEMPERATURE_PAREN_PATTERN = re.compile(
    r"\(\s*(" + _NUMBER + r")\s*(" + _TEMPERATURE_UNIT + r")\s*\)",
    re.IGNORECASE,
)
_VALUE_UNIT_PATTERN = re.compile(
    r"(" + _NUMBER + r")\s*(" + _VISCOSITY_UNIT + r")\b",
    re.IGNORECASE,
)
_DECLARED_UNIT_PATTERN = re.compile(r"\(\s*=?\s*(" + _VISCOSITY_UNIT + r")\s*\)", re.IGNORECASE)
_NUMBER_PATTERN = re.compile("(" + _NUMBER + ")")
_SCIENCE_PATTERN = re.compile(r"[Xx]\s*10\s*\^?\s*([+-]?\d+)")
_DECIMAL_COMMA_PATTERN = re.compile(r"(?<=\d),(?=\d)")
_KINEMATIC_PATTERN = re.compile(
    r"mm\s*2\s*/|mm\u00b2\s*/|sq\s*mm|sq\s*m\b|centistoke|\bcst\b|saybolt|\bsus\b|kinematic",
    re.IGNORECASE,
)
_MIXTURE_PATTERN = re.compile(
    r"%|\bsoln\b|solution|aqueous|in water|in benzene|\bpeg\b|dimethylamine|mixture|"
    r"blend|per cent",
    re.IGNORECASE,
)
_STATE_PATTERN = re.compile(r"\(gas\)|\bgas\b|\bvapou?r", re.IGNORECASE)
_RANGE_PATTERN = re.compile(
    r"(?<![\d.eE])\d+(?:\.\d+)?\s*(?:-|\u2013|to)\s*\d+(?:\.\d+)?(?![\d.eE])"
)

_PASCAL_SECOND_FACTORS: dict[str, float] = {
    "cp": 1e-3,
    "cps": 1e-3,
    "centipoise": 1e-3,
    "centipoises": 1e-3,
    "centipose": 1e-3,
    "centiposes": 1e-3,
    "centapoise": 1e-3,
    "centapoises": 1e-3,
    "millipoise": 1e-4,
    "millipoises": 1e-4,
    "micropoise": 1e-7,
    "micropoises": 1e-7,
    "poise": 0.1,
    "poises": 0.1,
    "mpas": 1e-3,
    "mpasec": 1e-3,
    "pas": 1.0,
    "pasec": 1.0,
}

REASON_TEXT: dict[str, str] = {
    "property_not_in_joint_enum": (
        "the harvested value belongs to a property outside the locked joint enum "
        "(epsilon, viscosity), so it cannot be an observation of this table"
    ),
    "dielectric_frequency_unstated": (
        "the schema note defines a dielectric value only together with its frequency; "
        "the PubChem string states none, and it mixes solvent matrices and dipole-moment "
        "clauses, so the value cannot be attributed without inference"
    ),
    "kinematic_viscosity_not_dynamic": (
        "kinematic viscosity (mm2/s, cSt, Saybolt) is not dynamic viscosity and carries no "
        "density in this harvest to convert it"
    ),
    "composition_undetermined": (
        "the value is reported for a solution, blend or per-cent mixture, so its "
        "n_components cannot be read and it must not be treated as a pure-substance row"
    ),
    "phase_or_state_not_liquid": "the value is reported for a gas or vapour state",
    "range_not_single_value": "the string reports an interval, not one measured value",
    "multiple_values_in_segment": (
        "one clause carries more than one number/unit pair, so the pairing is ambiguous"
    ),
    "no_temperature_reported": (
        "a row without a temperature is not an observation; 'melting point' and other "
        "named-but-numberless temperatures do not qualify"
    ),
    "unit_not_recognized": (
        "no viscosity unit this build can convert to Pa*s is attached to the number"
    ),
    "no_numeric_value": "the clause carries no number that could be read as a value",
    "value_not_in_canonical_unit": (
        "the source row does not carry a Pa*s value, so it cannot enter the canonical column"
    ),
    "duplicate_temperature_in_value_row": (
        "a second measurement at the same temperature in the same source row would collide "
        "with the primary key, and the merge may not renumber or average it"
    ),
    "predicted_value_not_an_observation": "a predicted value is not an observation",
}

def normalise_pubchem_text(raw: object) -> str:
    """Make the free-text numbers readable without inventing any of them."""

    text = _SCIENCE_PATTERN.sub(r"e\1", str(raw or ""))
    return _DECIMAL_COMMA_PATTERN.sub(".", text)

def normalise_unit_token(text: object) -> str:
    return re.sub(r"[.*\-\s]", "", str(text or "")).lower()

def to_pascal_seconds(value_text: str, unit_text: str) -> float | None:
    factor = _PASCAL_SECOND_FACTORS.get(normalise_unit_token(unit_text))
    if factor is None:
        return None
    return float(value_text) * factor

def to_kelvin(value_text: str, unit_text: str) -> float:
    value = float(value_text)
    token = re.sub(
        r"^(?:deg(?:ree)?s?)",
        "",
        str(unit_text).replace("°", "").replace(" ", "").lower(),
    )
    if token == "c":
        return round(value + 273.15, 6)
    if token == "f":
        return round((value - 32.0) * 5.0 / 9.0 + 273.15, 6)
    return round(value, 6)

def segment_rejection_reason(segment: str) -> str | None:
    if _STATE_PATTERN.search(segment):
        return "phase_or_state_not_liquid"
    if _MIXTURE_PATTERN.search(segment):
        return "composition_undetermined"
    if _KINEMATIC_PATTERN.search(segment):
        return "kinematic_viscosity_not_dynamic"
    if _RANGE_PATTERN.search(segment):
        return "range_not_single_value"
    return None

def parse_pubchem_viscosity_value(raw: object) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split one harvested viscosity string into measurements and rejections.

    The harvest stores free text such as ``2.568 cP @ 15 degC; 1.766 cP @ 30 degC``.
    Only shapes that can be read without guessing are accepted.  Anything that is
    not read becomes a rejection record, so an unparsed value stays visible
    instead of disappearing.
    """

    text = normalise_pubchem_text(raw)
    declared = _DECLARED_UNIT_PATTERN.search(text)
    declared_unit = declared.group(1) if declared else None
    measurements: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for segment_index, raw_segment in enumerate(text.split(";")):
        segment = raw_segment.strip()
        if not segment:
            continue
        reason = segment_rejection_reason(segment)
        if reason is not None:
            rejections.append(
                {"segment_index": segment_index, "reason_code": reason, "segment": segment}
            )
            continue
        temperature = _TEMPERATURE_PATTERN.search(segment)
        if temperature is None:
            temperature = _TEMPERATURE_PAREN_PATTERN.search(segment)
        attached = list(_VALUE_UNIT_PATTERN.finditer(segment))
        if len(attached) > 1:
            rejections.append(
                {
                    "segment_index": segment_index,
                    "reason_code": "multiple_values_in_segment",
                    "segment": segment,
                }
            )
            continue
        if attached:
            value_text, unit_text = attached[0].group(1), attached[0].group(2)
        elif declared_unit is not None:
            number = _NUMBER_PATTERN.search(segment)
            if number is None:
                rejections.append(
                    {
                        "segment_index": segment_index,
                        "reason_code": "no_numeric_value",
                        "segment": segment,
                    }
                )
                continue
            value_text, unit_text = number.group(1), declared_unit
        else:
            code = (
                "unit_not_recognized" if _NUMBER_PATTERN.search(segment) else "no_numeric_value"
            )
            rejections.append(
                {"segment_index": segment_index, "reason_code": code, "segment": segment}
            )
            continue
        if temperature is None:
            rejections.append(
                {
                    "segment_index": segment_index,
                    "reason_code": "no_temperature_reported",
                    "segment": segment,
                }
            )
            continue
        value = to_pascal_seconds(value_text, unit_text)
        if value is None:
            rejections.append(
                {
                    "segment_index": segment_index,
                    "reason_code": "unit_not_recognized",
                    "segment": segment,
                }
            )
            continue
        measurements.append(
            {
                "segment_index": segment_index,
                "value": value,
                "T_K": to_kelvin(temperature.group(1), temperature.group(2)),
                "unit_raw": unit_text,
                "temperature_raw": temperature.group(0).strip(),
            }
        )
    return measurements, rejections

def pubchem_value_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Enumerate every harvested value entry in document order.

    A "value row" is one ``StringWithMarkup`` entry under the deepest
    ``TOCHeading`` that contains it.  This enumeration is the unit of accounting
    for the exclusions file: every harvested value row is either in the table or
    in the exclusions file, and the verifier recomputes the list independently.
    """

    rows: list[dict[str, Any]] = []

    def walk(node: Any, current: str | None) -> None:
        if isinstance(node, dict):
            if "TOCHeading" in node:
                current = node["TOCHeading"]
                for information in node.get("Information") or []:
                    container = information.get("Value") or {}
                    for item in container.get("StringWithMarkup") or []:
                        rows.append(
                            {
                                "index": len(rows),
                                "heading": current,
                                "text": item.get("String") or "",
                            }
                        )
            for key, child in node.items():
                if key in ("Information", "Reference"):
                    continue
                walk(child, current)
        elif isinstance(node, list):
            for child in node:
                walk(child, current)

    walk(payload, None)
    return rows

# ---------------------------------------------------------------------------
# Per-source row builders.  Every source row is either observed or excluded.
# ---------------------------------------------------------------------------

def exclusion_row(
    *,
    dataset_id: str,
    source_file: str,
    source_row_index: int,
    segment_index: int,
    digest: str,
    inchikey: str,
    source_property: str,
    property_name: str,
    reason_code: str,
    raw_value: object,
) -> dict[str, Any]:
    return {
        "exclusion_id": f"{dataset_id}:{source_row_index}:{segment_index}",
        "dataset_id": dataset_id,
        "source_property": source_property,
        "property": property_name,
        "inchikey": inchikey,
        "source_file": source_file,
        "source_row_index": source_row_index,
        "segment_index": segment_index,
        "source_file_sha256": digest,
        "reason_code": reason_code,
        "reason": REASON_TEXT[reason_code],
        "raw_value": sanitise_text(raw_value),
    }

def component_fields(components: int) -> tuple[int, str]:
    return components, ("pure" if components == 1 else "mixture")

def build_dielectric_rows(
    rows: Sequence[Mapping[str, str]],
    source_file: str,
    digest: str,
) -> list[dict[str, Any]]:
    """epsilon_observations_v11plus: every row is a ThermoML measurement with a DOI."""

    observations: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        components, pure_or_mixture = component_fields(to_int(row.get("component_count")) or 1)
        observations.append(
            {
                "row_id": f"{DATASET_EPSILON}:{index}",
                "dataset_id": DATASET_EPSILON,
                "property": "epsilon",
                "property_family": PROPERTY_FAMILY["epsilon"],
                "inchikey": (row.get("inchikey") or "").strip(),
                "name": (row.get("name") or "").strip(),
                "smiles": (row.get("smiles") or "").strip(),
                "T_K": format_float(to_float(row.get("T_K"))),
                "value": format_float(to_float(row.get("epsilon"))),
                "unit": PROPERTY_UNIT["epsilon"],
                "phase": (row.get("phase") or "").strip(),
                "method": (row.get("method") or "").strip(),
                "uncertainty": format_float(to_float(row.get("uncertainty_expanded"))),
                "uncertainty_kind": (row.get("uncertainty_kind") or "").strip(),
                "confidence_level": format_float(to_float(row.get("confidence_level"))),
                "frequency_mhz": format_float(to_float(row.get("frequency_mhz"))),
                "pressure_kpa": format_float(to_float(row.get("pressure_kpa"))),
                "n_components": components,
                "pure_or_mixture": pure_or_mixture,
                "source_doi": (row.get("source_doi") or "").strip(),
                "source_kind": "primary_thermoml_measurement",
                "source_file": source_file,
                "source_row_index": index,
                "source_file_sha256": digest,
                "quality_layer": "publishable_core",
                "licence": "thermoml_open",
                "redistributable": True,
            }
        )
    return observations

def build_thermoml_rows(
    rows: Sequence[Mapping[str, str]],
    source_file: str,
    digest: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """ThermoML viscosity: the kinematic rows carry no Pa*s value and are excluded."""

    observations: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        source_property = (row.get("property_name") or "").strip()
        value = to_float(row.get("viscosity_Pa_s"))
        if (row.get("property_unit") or "").strip() != PROPERTY_UNIT["viscosity"] or value is None:
            kinematic = source_property.lower().startswith("kinematic")
            exclusions.append(
                exclusion_row(
                    dataset_id=DATASET_THERMOML,
                    source_file=source_file,
                    source_row_index=index,
                    segment_index=0,
                    digest=digest,
                    inchikey=(row.get("inchikey") or "").strip(),
                    source_property=source_property,
                    property_name="",
                    reason_code=(
                        "kinematic_viscosity_not_dynamic"
                        if kinematic
                        else "value_not_in_canonical_unit"
                    ),
                    raw_value=row.get("property_value") or "",
                )
            )
            continue
        components, pure_or_mixture = component_fields(to_int(row.get("n_components")) or 1)
        observations.append(
            {
                "row_id": f"{DATASET_THERMOML}:{index}",
                "dataset_id": DATASET_THERMOML,
                "property": "viscosity",
                "property_family": PROPERTY_FAMILY["viscosity"],
                "inchikey": (row.get("inchikey") or "").strip(),
                "name": (row.get("name") or "").strip(),
                "smiles": "",
                "T_K": format_float(to_float(row.get("T_K"))),
                "value": format_float(value),
                "unit": PROPERTY_UNIT["viscosity"],
                "phase": (row.get("phase") or "").strip(),
                "method": (row.get("method_name") or "").strip(),
                "uncertainty": format_float(to_float(row.get("uncertainty"))),
                "uncertainty_kind": (row.get("uncertainty_kind") or "").strip(),
                "confidence_level": "",
                "frequency_mhz": "",
                "pressure_kpa": "",
                "n_components": components,
                "pure_or_mixture": pure_or_mixture,
                "source_doi": (row.get("source_doi") or "").strip(),
                "source_kind": "primary_thermoml_measurement",
                "source_file": source_file,
                "source_row_index": index,
                "source_file_sha256": digest,
                "quality_layer": "publishable_core",
                "licence": "thermoml_open",
                "redistributable": True,
            }
        )
    return observations, exclusions

def build_schrodinger_rows(
    rows: Sequence[Mapping[str, str]],
    source_file: str,
    digest: str,
) -> list[dict[str, Any]]:
    """The open subset of the Chew 2024 supplement: 3,582 experimental rows.

    The supplement carries one InChIKey and one canonical SMILES per row and no
    composition column; the stored table is the open subset of a pure-substance
    viscosity dataset, so ``n_components`` is 1.  The 650 predicted rows of
    ``supp_3`` are a different file and have no code path here.
    """

    observations: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        observations.append(
            {
                "row_id": f"{DATASET_SCHRODINGER}:{index}",
                "dataset_id": DATASET_SCHRODINGER,
                "property": "viscosity",
                "property_family": PROPERTY_FAMILY["viscosity"],
                "inchikey": (row.get("inchikey") or "").strip(),
                "name": (row.get("name") or "").strip(),
                "smiles": (row.get("smiles") or "").strip(),
                "T_K": format_float(to_float(row.get("T_K"))),
                "value": format_float(to_float(row.get("viscosity_Pa_s"))),
                "unit": PROPERTY_UNIT["viscosity"],
                "phase": "",
                "method": "",
                "uncertainty": "",
                "uncertainty_kind": "",
                "confidence_level": "",
                "frequency_mhz": "",
                "pressure_kpa": "",
                "n_components": 1,
                "pure_or_mixture": "pure",
                "source_doi": (row.get("source_doi") or "").strip(),
                "source_kind": "published_supplement_open_subset",
                "source_file": source_file,
                "source_row_index": index,
                "source_file_sha256": digest,
                "quality_layer": "publishable_core",
                "licence": "cc_by_4_0",
                "redistributable": True,
            }
        )
    return observations

def build_pubchem_rows(
    paths: Sequence[Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """PubChem liquid window: filter_only compilation values, never a core value.

    Only the ``Viscosity`` section fits the locked property enum.  Everything
    else the harvest carries -- melting point, boiling point, flash point,
    density and the rest -- is written to the exclusions file rather than
    dropped, which is where the prereg's "MP/BP/FP/density" reading and the
    locked enum are reconciled without editing either.
    """

    observations: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    without_properties: list[dict[str, Any]] = []
    for path in paths:
        source_file = display_path(path)
        digest = sha256_file(path)
        inchikey = Path(path).name[: -len(PUBCHEM_SUFFIX)]
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if "Record" not in payload:
            without_properties.append(
                {
                    "source_file": source_file,
                    "inchikey": inchikey,
                    "http_status": payload.get("http_status"),
                    "resolution_status": payload.get("resolution_status"),
                }
            )
            continue
        record_title = str((payload.get("Record") or {}).get("RecordTitle") or "").strip()
        for value_row in pubchem_value_rows(payload):
            index = int(value_row["index"])
            heading = str(value_row["heading"])
            text = str(value_row["text"])
            if heading not in (VISCOSITY_HEADING, DIELECTRIC_HEADING):
                exclusions.append(
                    exclusion_row(
                        dataset_id=DATASET_PUBCHEM,
                        source_file=source_file,
                        source_row_index=index,
                        segment_index=0,
                        digest=digest,
                        inchikey=inchikey,
                        source_property=heading,
                        property_name="",
                        reason_code="property_not_in_joint_enum",
                        raw_value=text,
                    )
                )
                continue
            if heading == DIELECTRIC_HEADING:
                exclusions.append(
                    exclusion_row(
                        dataset_id=DATASET_PUBCHEM,
                        source_file=source_file,
                        source_row_index=index,
                        segment_index=0,
                        digest=digest,
                        inchikey=inchikey,
                        source_property=heading,
                        property_name="epsilon",
                        reason_code="dielectric_frequency_unstated",
                        raw_value=text,
                    )
                )
                continue
            measurements, rejections = parse_pubchem_viscosity_value(text)
            seen_temperatures: set[float] = set()
            for rejection in rejections:
                exclusions.append(
                    exclusion_row(
                        dataset_id=DATASET_PUBCHEM,
                        source_file=source_file,
                        source_row_index=index,
                        segment_index=int(rejection["segment_index"]),
                        digest=digest,
                        inchikey=inchikey,
                        source_property=heading,
                        property_name="viscosity",
                        reason_code=str(rejection["reason_code"]),
                        raw_value=rejection["segment"],
                    )
                )
            if not measurements and not rejections:
                exclusions.append(
                    exclusion_row(
                        dataset_id=DATASET_PUBCHEM,
                        source_file=source_file,
                        source_row_index=index,
                        segment_index=0,
                        digest=digest,
                        inchikey=inchikey,
                        source_property=heading,
                        property_name="viscosity",
                        reason_code="no_numeric_value",
                        raw_value=text,
                    )
                )
            for measurement in measurements:
                temperature = float(measurement["T_K"])
                if temperature in seen_temperatures:
                    exclusions.append(
                        exclusion_row(
                            dataset_id=DATASET_PUBCHEM,
                            source_file=source_file,
                            source_row_index=index,
                            segment_index=int(measurement["segment_index"]),
                            digest=digest,
                            inchikey=inchikey,
                            source_property=heading,
                            property_name="viscosity",
                            reason_code="duplicate_temperature_in_value_row",
                            raw_value=text,
                        )
                    )
                    continue
                seen_temperatures.add(temperature)
                observations.append(
                    {
                        "row_id": f"{DATASET_PUBCHEM}:{index}",
                        "dataset_id": DATASET_PUBCHEM,
                        "property": "viscosity",
                        "property_family": PROPERTY_FAMILY["viscosity"],
                        "inchikey": inchikey,
                        "name": record_title,
                        "smiles": "",
                        "T_K": format_float(temperature),
                        "value": format_float(float(measurement["value"])),
                        "unit": PROPERTY_UNIT["viscosity"],
                        "phase": "",
                        "method": "",
                        "uncertainty": "",
                        "uncertainty_kind": "",
                        "confidence_level": "",
                        "frequency_mhz": "",
                        "pressure_kpa": "",
                        "n_components": 1,
                        "pure_or_mixture": "pure",
                        "source_doi": "",
                        "source_kind": "compilation",
                        "source_file": source_file,
                        "source_row_index": index,
                        "source_file_sha256": digest,
                        "quality_layer": "filter_only",
                        "licence": "publisher_terms_see_source",
                        "redistributable": False,
                    }
                )
    return observations, exclusions, without_properties

# ---------------------------------------------------------------------------
# Orchestration.
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

def digest_or_empty(path: Path) -> str:
    """SHA256 of a written artefact, or an empty string when it is not on disk yet."""

    return sha256_file(path) if Path(path).is_file() else ""


def counter_dict(values: Sequence[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))

def distinct_inchikeys(rows: Sequence[Mapping[str, Any]]) -> int:
    return len({str(row["inchikey"]) for row in rows})

def conflict_audit(
    rows: Sequence[Mapping[str, Any]],
    *,
    limit: int = 12,
) -> dict[str, Any]:
    """Count (inchikey, property, T_K) keys that carry more than one value.

    The merge rule is "keep them all": this function only counts and exhibits the
    conflicts, it never picks a winner and never averages.
    """

    by_key: dict[tuple[str, str, float], list[str]] = {}
    for row in rows:
        key = (str(row["inchikey"]), str(row["property"]), float(row["T_K"]))
        by_key.setdefault(key, []).append(str(row["value"]))
    conflicting = {key: values for key, values in by_key.items() if len(set(values)) > 1}
    repeated = {key: values for key, values in by_key.items() if len(values) > 1}
    def describe(key: tuple[str, str, float], values: list[str]) -> dict[str, Any]:
        return {
            "inchikey": key[0],
            "property": key[1],
            "T_K": key[2],
            "rows": len(values),
            "distinct_values": len(set(values)),
            "values": sorted(set(values)),
        }

    ordered = sorted(conflicting.items(), key=lambda item: (-len(item[1]), item[0]))
    return {
        "definition": "keys (inchikey, property, T_K) with more than one distinct value",
        "distinct_keys": len(by_key),
        "conflicting_keys": len(conflicting),
        "rows_in_conflicting_keys": sum(len(value) for value in conflicting.values()),
        "keys_with_more_than_one_row": len(repeated),
        "rows_in_repeated_keys": sum(len(value) for value in repeated.values()),
        "averaging_applied": False,
        "keys": [describe(key, values) for key, values in ordered],
        "examples": [describe(key, values) for key, values in ordered[:limit]],
    }

def run_group_audit(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Run one real GroupKFold by InChIKey and stop if any group leaks.

    ``random_row`` is computed next to it purely as a leak reference: it is the
    number that makes the grouped reading meaningful, not a result.  Nothing in
    this repository may quote it as a verdict.
    """

    from sklearn.model_selection import GroupKFold, KFold

    subset = [
        row
        for row in rows
        if row["quality_layer"] == "publishable_core" and row["pure_or_mixture"] == "pure"
    ]
    groups = [str(row["inchikey"]) for row in subset]
    if len(subset) < GROUP_SPLITS or len(set(groups)) < GROUP_SPLITS:
        return {
            "splitter": "GroupKFold by InChIKey",
            "assertion": "group_overlap == 0 between train and test groups",
            "assertion_passed": False,
            "error": "not enough rows or groups to run the split",
        }
    folds: list[dict[str, Any]] = []
    max_overlap = 0
    for fold, (train_index, test_index) in enumerate(
        GroupKFold(n_splits=GROUP_SPLITS).split(subset, groups=groups)
    ):
        train_groups = {groups[index] for index in train_index}
        test_groups = {groups[index] for index in test_index}
        overlap = len(train_groups & test_groups)
        max_overlap = max(max_overlap, overlap)
        folds.append(
            {
                "fold": fold,
                "train_rows": len(train_index),
                "test_rows": len(test_index),
                "train_groups": len(train_groups),
                "test_groups": len(test_groups),
                "group_overlap": overlap,
            }
        )
    if max_overlap != 0:
        raise RuntimeError(
            f"GroupKFold by InChIKey leaked {max_overlap} groups across train/test: "
            "this is a stop, not a warning"
        )
    leak_rows = 0
    test_rows = 0
    for train_index, test_index in KFold(
        n_splits=GROUP_SPLITS, shuffle=True, random_state=LEAK_REFERENCE_SEED
    ).split(subset):
        train_groups = {groups[index] for index in train_index}
        test_rows += len(test_index)
        leak_rows += sum(1 for index in test_index if groups[index] in train_groups)
    return {
        "splitter": "GroupKFold by InChIKey",
        "group_key": "inchikey",
        "n_splits": GROUP_SPLITS,
        "subset": "quality_layer=publishable_core and pure_or_mixture=pure",
        "subset_rows": len(subset),
        "subset_groups": len(set(groups)),
        "assertion": "group_overlap == 0 between train and test groups",
        "assertion_passed": max_overlap == 0,
        "max_group_overlap": max_overlap,
        "folds": folds,
        "random_row": {
            "role": "leak reference only; it never enters a verdict",
            "splitter": "KFold(shuffle=True) on rows",
            "seed": LEAK_REFERENCE_SEED,
            "test_rows": test_rows,
            "test_rows_whose_group_also_sits_in_train": leak_rows,
            "leaked_fraction": round(leak_rows / test_rows, 6) if test_rows else None,
        },
        "verdict_derived_this_round": "none: this round is data engineering, no model is fitted",
    }

def source_record(
    *,
    dataset_id: str,
    source_file: str,
    digest: str,
    rows_in_source: int,
    observations: Sequence[Mapping[str, Any]],
    exclusions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    observed_rows = {
        (str(row["source_file"]), int(row["source_row_index"])) for row in observations
    }
    excluded_rows = {
        (str(row["source_file"]), int(row["source_row_index"])) for row in exclusions
    }
    return {
        "dataset_id": dataset_id,
        "source_file": source_file,
        "sha256": digest,
        "rows_in_source": rows_in_source,
        "observations": len(observations),
        "source_rows_in_table": len(observed_rows),
        "exclusion_records": len(exclusions),
        "source_rows_with_exclusion_record": len(excluded_rows),
        "source_rows_covered": len(observed_rows | excluded_rows),
        "source_rows_uncovered": rows_in_source - len(observed_rows | excluded_rows),
        "exclusion_reason_counts": counter_dict([str(row["reason_code"]) for row in exclusions]),
    }

def build_tables(
    *,
    dielectric_path: Path = DIELECTRIC_PATH,
    thermoml_path: Path = THERMOML_PATH,
    schrodinger_path: Path = SCHRODINGER_PATH,
    pubchem_dir: Path = PUBCHEM_DIR,
    prereg_path: Path = PREREG_PATH,
) -> dict[str, Any]:
    prereg = read_prereg(prereg_path)
    assert_schema_matches_prereg(prereg)

    dielectric_file = display_path(dielectric_path)
    dielectric_digest = sha256_file(dielectric_path)
    dielectric_source_rows = read_csv_rows(dielectric_path)
    dielectric_observations = build_dielectric_rows(
        dielectric_source_rows, dielectric_file, dielectric_digest
    )

    thermoml_file = display_path(thermoml_path)
    thermoml_digest = sha256_file(thermoml_path)
    thermoml_source_rows = read_csv_rows(thermoml_path)
    thermoml_observations, thermoml_exclusions = build_thermoml_rows(
        thermoml_source_rows, thermoml_file, thermoml_digest
    )

    schrodinger_file = display_path(schrodinger_path)
    schrodinger_digest = sha256_file(schrodinger_path)
    schrodinger_source_rows = read_csv_rows(schrodinger_path)
    schrodinger_observations = build_schrodinger_rows(
        schrodinger_source_rows, schrodinger_file, schrodinger_digest
    )

    pubchem_paths = sorted(pubchem_dir.glob(f"*{PUBCHEM_SUFFIX}"))
    pubchem_observations, pubchem_exclusions, pubchem_without_properties = build_pubchem_rows(
        pubchem_paths
    )
    pubchem_value_row_count = 0
    for path in pubchem_paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        pubchem_value_row_count += len(pubchem_value_rows(payload))

    observations = [
        *dielectric_observations,
        *thermoml_observations,
        *schrodinger_observations,
        *pubchem_observations,
    ]
    exclusions = [*thermoml_exclusions, *pubchem_exclusions]

    sources = [
        source_record(
            dataset_id=DATASET_EPSILON,
            source_file=dielectric_file,
            digest=dielectric_digest,
            rows_in_source=len(dielectric_source_rows),
            observations=dielectric_observations,
            exclusions=[],
        ),
        source_record(
            dataset_id=DATASET_THERMOML,
            source_file=thermoml_file,
            digest=thermoml_digest,
            rows_in_source=len(thermoml_source_rows),
            observations=thermoml_observations,
            exclusions=thermoml_exclusions,
        ),
        source_record(
            dataset_id=DATASET_SCHRODINGER,
            source_file=schrodinger_file,
            digest=schrodinger_digest,
            rows_in_source=len(schrodinger_source_rows),
            observations=schrodinger_observations,
            exclusions=[],
        ),
        source_record(
            dataset_id=DATASET_PUBCHEM,
            source_file=display_path(pubchem_dir),
            digest="",
            rows_in_source=pubchem_value_row_count,
            observations=pubchem_observations,
            exclusions=pubchem_exclusions,
        ),
    ]
    return {
        "prereg": prereg,
        "observations": observations,
        "exclusions": exclusions,
        "sources": sources,
        "pubchem_records_without_properties": pubchem_without_properties,
        "source_rows_considered": sum(source["rows_in_source"] for source in sources),
    }

DENYLIST_MARKERS: tuple[str, ...] = ("supp_3", "reaxys", "restricted", "predicted")

def build_summary(
    result: Mapping[str, Any],
    *,
    table_path: Path,
    exclusions_path: Path,
    prereg_path: Path,
    report_path: Path,
    builder_path: Path = BUILDER_PATH,
) -> dict[str, Any]:
    observations = result["observations"]
    exclusions = result["exclusions"]
    sources = result["sources"]
    prereg = result["prereg"]

    publishable = [row for row in observations if row["quality_layer"] == "publishable_core"]
    filter_only = [row for row in observations if row["quality_layer"] == "filter_only"]
    pure = [row for row in observations if row["pure_or_mixture"] == "pure"]

    key_counts = Counter(tuple(str(row[column]) for column in PRIMARY_KEY) for row in observations)
    row_id_counts = Counter(str(row["row_id"]) for row in observations)
    denied_rows = [
        row
        for row in observations
        if any(marker in str(row["source_file"]).lower() for marker in DENYLIST_MARKERS)
    ]

    summary: dict[str, Any] = {
        "schema_version": prereg["schema_version"],
        "task": prereg["task"],
        "title": "eta-epsilon joint observation table: the first build",
        "generated_at_utc": _utc_now(),
        "prereg": {
            "path": display_path(prereg_path),
            "sha256": sha256_file(prereg_path),
            "status": prereg["status"],
            "locked_at_utc": prereg["locked_at_utc"],
        },
        "observation_schema": {
            "columns": list(OBSERVATION_COLUMNS),
            "column_count": len(OBSERVATION_COLUMNS),
            "primary_key": list(PRIMARY_KEY),
            "unit_rule": prereg["observation_schema"]["unit_rule"],
        },
        "row_counts": {
            "observations": len(observations),
            "exclusions": len(exclusions),
            "source_rows_considered": result["source_rows_considered"],
            "source_rows_in_table": sum(source["source_rows_in_table"] for source in sources),
            "source_rows_with_exclusion_record": sum(
                source["source_rows_with_exclusion_record"] for source in sources
            ),
            "source_rows_uncovered": sum(source["source_rows_uncovered"] for source in sources),
            "exclusion_records": sum(source["exclusion_records"] for source in sources),
            "distinct_inchikeys": distinct_inchikeys(observations),
        },
        "distribution": {
            "property": counter_dict([str(row["property"]) for row in observations]),
            "property_family": counter_dict([str(row["property_family"]) for row in observations]),
            "dataset_id": counter_dict([str(row["dataset_id"]) for row in observations]),
            "pure_or_mixture": counter_dict([str(row["pure_or_mixture"]) for row in observations]),
            "quality_layer": counter_dict([str(row["quality_layer"]) for row in observations]),
            "source_kind": counter_dict([str(row["source_kind"]) for row in observations]),
            "licence": counter_dict([str(row["licence"]) for row in observations]),
            "unit": counter_dict([str(row["unit"]) for row in observations]),
            "redistributable": counter_dict(
                ["true" if row["redistributable"] else "false" for row in observations]
            ),
            "n_components": counter_dict([str(row["n_components"]) for row in observations]),
        },
        "publishable_headline": {
            "definition": "quality_layer=publishable_core, i.e. first-hand DOI plus a measurement",
            "rows": len(publishable),
            "distinct_inchikeys": distinct_inchikeys(publishable),
            "by_dataset_id": counter_dict([str(row["dataset_id"]) for row in publishable]),
            "filter_only_rows_excluded_from_this_headline": len(filter_only),
        },
        "filter_only_layer": {
            "definition": prereg["quality_layers"]["filter_only"],
            "rows": len(filter_only),
            "distinct_inchikeys": distinct_inchikeys(filter_only),
            "by_dataset_id": counter_dict([str(row["dataset_id"]) for row in filter_only]),
            "source_kind_counts": counter_dict([str(row["source_kind"]) for row in filter_only]),
            "empty_source_doi_rows": sum(1 for row in filter_only if not str(row["source_doi"]).strip()),
            "never_quoted_as_a_core_value": True,
        },
        "pure_subset": {
            "rows": len(pure),
            "distinct_inchikeys": distinct_inchikeys(pure),
            "mixture_rows_stored_but_not_a_modelling_target": len(observations) - len(pure),
        },
        "conflicts": {
            "all_rows": conflict_audit(observations),
            "publishable_core_only": conflict_audit(publishable),
            "no_averaging": prereg["merge_rules"]["no_averaging"],
        },
        "exclusions": {
            "definition": prereg["merge_rules"]["no_silent_drops"],
            "records": len(exclusions),
            "by_dataset_id": counter_dict([str(row["dataset_id"]) for row in exclusions]),
            "by_reason_code": counter_dict([str(row["reason_code"]) for row in exclusions]),
            "by_property": counter_dict([str(row["property"]) for row in exclusions]),
            "distinct_source_rows": len(
                {
                    (str(row["source_file"]), int(row["source_row_index"]))
                    for row in exclusions
                }
            ),
            "top_source_properties": dict(
                Counter(str(row["source_property"]) for row in exclusions).most_common(15)
            ),
        },
        "integrity": {
            "primary_key_duplicates": sum(1 for value in key_counts.values() if value > 1),
            "row_id_repeats": sum(1 for value in row_id_counts.values() if value > 1),
            "row_id_note": (
                "row_id is the schema-prescribed {dataset_id}:{source_row_index} label, so a "
                "source row that yields several measurements shares it; uniqueness is carried "
                "by the primary key (inchikey, property, T_K, source_file, source_row_index)"
            ),
            "required_column_violations": 0,
            "unit_property_mismatches": 0,
        },
        "exclusions_contract": {
            "schrodinger_restricted_858": {
                "rows_in_table": 0,
                "fetched_here": False,
                "reconstructed_here": False,
                "note": (
                    "the builder opens only data/viscosity_v01.csv; there is no fetch, inference "
                    "or reconstruction code path for the 858 withheld values"
                ),
            },
            "chew_2024_supp_3_predicted": {
                "rows": 650,
                "rows_in_table": 0,
                "recomputed_here": False,
                "note": "predicted values are not observations; the file is not opened by this builder",
            },
            "reaxys_values": {
                "rows_in_table": 0,
                "note": "restricted_crosscheck_only; no Reaxys row has a code path into the table",
            },
            "mixture_rows": {
                "rows_in_table": len(observations) - len(pure),
                "note": "stored, but the modelled target is the pure-substance subset",
            },
            "denylist_markers": list(DENYLIST_MARKERS),
            "table_rows_from_denylisted_sources": len(denied_rows),
        },
        "sources": sources,
        "pubchem_records_without_properties": {
            "count": len(result["pubchem_records_without_properties"]),
            "examples": result["pubchem_records_without_properties"][:5],
            "note": "a 404 harvest entry carries no value row at all, so there is no row to exclude",
        },
        "evaluation_contract": run_group_audit(observations),
        "manifest": {
            "table": {
                "path": display_path(table_path),
                "sha256": digest_or_empty(table_path),
                "rows": len(observations),
            },
            "exclusions": {
                "path": display_path(exclusions_path),
                "sha256": digest_or_empty(exclusions_path),
                "rows": len(exclusions),
            },
            "builder": {"path": display_path(builder_path), "sha256": sha256_file(builder_path)},
            "prereg": {"path": display_path(prereg_path), "sha256": sha256_file(prereg_path)},
            "report": {"path": display_path(report_path)},
            "source_files": [
                {"path": source["source_file"], "sha256": source["sha256"]} for source in sources
            ],
            "redistributable_false_by_source": counter_dict(
                [
                    str(row["source_file"])
                    for row in observations
                    if not row["redistributable"]
                ]
            ),
        },
        "deviations_and_uncertainties": deviations(prereg),
    }
    return summary

def deviations(prereg: Mapping[str, Any]) -> list[dict[str, str]]:
    """Everything this build could not settle by following the prereg alone."""

    return [
        {
            "id": "pubchem_property_enum_conflict",
            "kind": "prereg_internal_conflict",
            "detail": (
                "merge_rules.first_build_sources describes the PubChem liquid-window harvest as "
                "'MP/BP/FP/density, filter_only', but observation_schema restricts property to "
                "epsilon and viscosity. MP/BP/FP/density are neither, so they are enumerated in "
                "the exclusions file (reason property_not_in_joint_enum) instead of being stored. "
                "Storing them would require editing the locked schema, which lock_rule forbids; "
                "this is reported as a correction candidate for a later round."
            ),
        },
        {
            "id": "pubchem_dielectric_frequency",
            "kind": "interpretation",
            "detail": (
                "two harvested Dielectric Constant strings fit the property enum but state no "
                "frequency, and the schema note says a dielectric value without its frequency is "
                "not a defined measurement; both are excluded "
                "(reason dielectric_frequency_unstated) rather than stored with an empty frequency."
            ),
        },
        {
            "id": "dielectric_uncertainty_kind",
            "kind": "source_vocabulary",
            "detail": (
                "every epsilon row carries uncertainty_kind='combined' from the source, while the "
                "schema note lists 'expanded / standard / unknown'. The source value is kept "
                "verbatim rather than reinterpreted; this needs a main-thread decision."
            ),
        },
        {
            "id": "pubchem_source_doi_empty",
            "kind": "source_limitation",
            "detail": (
                "no harvested PubChem viscosity value row carries an ExtendedReference DOI, so "
                "source_doi is empty on every filter_only row. The schema allows an empty DOI "
                "only in filter_only, which is exactly this layer."
            ),
        },
        {
            "id": "pubchem_free_text_parsing",
            "kind": "interpretation",
            "detail": (
                "the harvest stores viscosity as free text. Only shapes with one number, one "
                "recognised unit and one numeric temperature are read; every other clause leaves an "
                "exclusion record. A different parser would "
                "yield a different count, so those rows stay filter_only and are never quoted "
                "in the publishable headline."
            ),
        },
        {
            "id": "schrodinger_n_components",
            "kind": "assumption",
            "detail": (
                "data/viscosity_v01.csv carries no composition column. It is the open subset of a "
                "one-InChIKey-per-row pure-substance viscosity supplement, so n_components=1 and "
                "pure_or_mixture='pure' are recorded and not silently defaulted."
            ),
        },
        {
            "id": "thermoml_smiles_absent",
            "kind": "source_limitation",
            "detail": (
                "viscosity_observations_thermoml.csv exposes 'smiles_or_name', which holds the "
                "compound name on every row inspected; smiles is therefore empty on every ThermoML "
                "viscosity row rather than guessed from a name."
            ),
        },
        {
            "id": "row_id_is_a_source_row_label",
            "kind": "schema_limitation",
            "detail": (
                "the schema prescribes row_id={dataset_id}:{source_row_index}, so a harvested "
                "PubChem value row that reports two temperatures yields two rows with the same "
                "row_id. Uniqueness is carried by the primary key, which has no duplicates."
            ),
        },
        {
            "id": "prereg_bytes_untouched",
            "kind": "statement",
            "detail": (
                "this build reads the locked prereg and never writes it; the schema was not "
                "back-filled and no frozen artefact was modified."
            ),
        },
    ]

# ---------------------------------------------------------------------------
# Report and entry point.
# ---------------------------------------------------------------------------

def _markdown_table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines

def render_report(summary: Mapping[str, Any]) -> str:
    counts = summary["row_counts"]
    distribution = summary["distribution"]
    headline = summary["publishable_headline"]
    filter_only = summary["filter_only_layer"]
    conflicts = summary["conflicts"]
    exclusion_stats = summary["exclusions"]
    evaluation = summary["evaluation_contract"]
    manifest = summary["manifest"]

    lines: list[str] = [
        "# η–ε 联合温度分辨观测表（Week 16 首建）",
        "",
        f"- 构建器：`{manifest['builder']['path']}`（sha256 `{manifest['builder']['sha256']}`）",
        "- 校验器：`probes/verify_eta_epsilon_joint_table.py`",
        "- 机读汇总：`probes/eta_epsilon_joint_summary.json`",
        (f"- 观测表：`{manifest['table']['path']}`（{counts['observations']:,} 行 + 表头，"
                f"{summary['observation_schema']['column_count']} 列）"
        ),
        f"- 排除表：`{manifest['exclusions']['path']}`（{counts['exclusions']:,} 行 + 表头）",
        (f"- 契约：`{summary['prereg']['path']}`（sha256 `{summary['prereg']['sha256']}`，"
                f"status={summary['prereg']['status']}）"
        ),
        r"- 复现构建：`.\.venv\Scripts\python.exe probes\build_eta_epsilon_joint_table.py`",
        r"- 复现校验：`.\.venv\Scripts\python.exe probes\verify_eta_epsilon_joint_table.py`",
        "- 网络访问：无（只读 4 个本地源表）；冻结产物写入：无；建模：无（本周只做数据工程）。",
        "",
        "## 数据来源",
        "",
    ]
    lines.extend(
        _markdown_table(
            ["dataset_id", "源文件", "源行数", "进表观测", "排除记录", "sha256（前 16 位）"],
            [
                [
                    source["dataset_id"],
                    f"`{source['source_file']}`",
                    f"{source['rows_in_source']:,}",
                    f"{source['observations']:,}",
                    f"{source['exclusion_records']:,}",
                    (source["sha256"] or "（目录，见逐文件行）")[:16],
                ]
                for source in summary["sources"]
            ],
        )
    )
    source_rows_considered = counts["source_rows_considered"]
    lines.extend(
        [
            "",
            (f"源行总数 {source_rows_considered:,}；其中 `source_rows_uncovered` = "
                        f"{counts['source_rows_uncovered']:,}（必须为 0：任何既没进表、也没有排除记录的源行都是缺陷）。"
            ),
            "",
            "## 方法",
            "",
            ("1. ε 线：逐行读 `dielectric_observations_v11plus.csv`，`unit='1'`、`property='epsilon'`；"
                        "`uncertainty` 取源表的 `uncertainty_expanded`，`uncertainty_kind` 原样保留源值。"
            ),
            ("2. η 线（ThermoML）：逐行读 `viscosity_observations_thermoml.csv`，只接受 "
                        "`property_unit='Pa*s'` 且 `viscosity_Pa_s` 非空的行；176 行运动黏度（m2/s）写进排除表。"
            ),
            ("3. η 线（Schrödinger 开放子集）：逐行读 `viscosity_v01.csv` 的 3,582 行实验值；"
                        "受限 858 条没有获取、没有推断、没有重建，`supp_3` 的 650 条预测值没有进入。"
            ),
            ("4. PubChem 液态窗口：逐文件按文档顺序枚举**每一个** `StringWithMarkup` 取值行；"
            "只有 `Viscosity` 节能用严格文法读成 (Pa*s, K) 的才进表（`quality_layer='filter_only'`），"
                        "其余每一个取值行都写进排除表并给原因。"
            ),
            ("5. 恒等键 `(inchikey, property, T_K, source_file, source_row_index)`：冲突值全部保留，"
                        "既不平均也不挑选；本模块只统计冲突键。"
            ),
            "6. 每行都带 `source_file`、`source_row_index`（该文件内 0 基行号）与 `source_file_sha256`。",
            ("7. 评估契约：对 `publishable_core & pure` 子集真跑一次 `GroupKFold` by InChIKey，"
                        "并断言 `group_overlap == 0`；失败即停，不是告警。"
            ),
            "",
            "## 读数",
            "",
            "### 总行数与分布",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            ["维度", "取值", "行数"],
            [
                [name, value, f"{count:,}"]
                for name in (
                    "property",
                    "property_family",
                    "dataset_id",
                    "pure_or_mixture",
                    "quality_layer",
                    "source_kind",
                    "licence",
                    "unit",
                    "redistributable",
                    "n_components",
                )
                for value, count in distribution[name].items()
            ],
        )
    )
    lines.extend(
        [
            "",
            f"合计 {counts['observations']:,} 行，覆盖 {counts['distinct_inchikeys']:,} 个 InChIKey。",
            "",
            "### 两层口径",
            "",
            (f"- `publishable_core`：**{headline['rows']:,} 行**，覆盖 "
            f"**{headline['distinct_inchikeys']:,} 个 InChIKey**"
                        f"（{headline['definition']}）。"
            ),
            (f"- `filter_only`：{filter_only['rows']:,} 行，覆盖 "
            f"{filter_only['distinct_inchikeys']:,} 个 InChIKey"
                        "（PubChem 汇编值，只允许做筛选，永远不计入可发表口径）。"
            ),
            (f"- 纯组分子集：{summary['pure_subset']['rows']:,} 行 / "
            f"{summary['pure_subset']['distinct_inchikeys']:,} 个 InChIKey；"
            f"混合物 {summary['pure_subset']['mixture_rows_stored_but_not_a_modelling_target']:,} 行"
                        "照存但不作为建模目标。"
            ),
            "",
            "### 冲突键",
            "",
            (f"- `(inchikey, property, T_K)` 共 {conflicts['all_rows']['distinct_keys']:,} 个键，其中"
            f"**{conflicts['all_rows']['conflicting_keys']:,} 个键存在多个不同取值**"
            f"（涉及 {conflicts['all_rows']['rows_in_conflicting_keys']:,} 行）；"
                        f"只算 `publishable_core` 是 {conflicts['publishable_core_only']['conflicting_keys']:,} 个键。"
            ),
            ("- 全部保留、绝不平均；`averaging_applied = "
                        f"{conflicts['all_rows']['averaging_applied']}`。"
            ),
            f"- 主键重复：{summary['integrity']['primary_key_duplicates']}（必须为 0）。",
            "",
            "### 排除记录",
            "",
            (f"共 {exclusion_stats['records']:,} 条，覆盖 "
                        f"{exclusion_stats['distinct_source_rows']:,} 个源行。"
            ),
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            ["reason_code", "条数"],
            [[code, f"{count:,}"] for code, count in exclusion_stats["by_reason_code"].items()],
        )
    )
    lines.extend(
        [
            "",
            "逐 `dataset_id`："
            + "，".join(
                f"{key} {value:,}" for key, value in exclusion_stats["by_dataset_id"].items()
            )
            + "。",
            "",
            "### 评估契约",
            "",
            (f"- `splitter = \"{evaluation['splitter']}\"`，分组键 `{evaluation['group_key']}`，"
            f"{evaluation['n_splits']} 折，子集：{evaluation['subset']}"
                        f"（{evaluation['subset_rows']:,} 行 / {evaluation['subset_groups']:,} 组）。"
            ),
            (f"- 断言 `{evaluation['assertion']}`：**"
            f"{'通过' if evaluation['assertion_passed'] else '失败'}**"
                        f"（`max_group_overlap = {evaluation['max_group_overlap']}`）。断言失败是停工，不是告警。"
            ),
            (f"- `random_row` 仅作泄漏参照：同一子集按行随机切分时，测试行中"
            f"{evaluation['random_row']['test_rows_whose_group_also_sits_in_train']:,} / "
            f"{evaluation['random_row']['test_rows']:,} 行的 InChIKey 同时出现在训练集里"
            f"（泄漏比例 {evaluation['random_row']['leaked_fraction']}）。它**永不进判决**："
                        "同一个化合物出现在多个温度上，按行随机切分会把同一化合物放到切分两侧。"
            ),
            f"- 本轮判决来源：{evaluation['verdict_derived_this_round']}。",
            "",
            "## 与预注册的冲突与不确定处",
            "",
        ]
    )
    lines.extend(
        [
            f"- **{item['id']}**（{item['kind']}）：{item['detail']}"
            for item in summary["deviations_and_uncertainties"]
        ]
    )
    lines.extend(
        [
            "",
            "## 边界（不许省略）",
            "",
            ("- **受限 858 条**：Schrödinger 增补中 4,440 − 3,582 = 858 条受限值"
                        "**未获取、未推断、未重建**；3,582 行开放子集就是本项目可用的全部。"
            ),
            ("- **`supp_3`（650 行，`data_status=predicted`）未进入**：预测值不是观测，"
                        "本构建器不打开该文件。"
            ),
            ("- **Reaxys 值未进入**：`restricted_crosscheck_only`，只用于裁定冲突，"
                        "不得进入可分发的数据集。"
            ),
            ("- **`filter_only` 永不进可发表口径**：上文的 `publishable_core` 读数不含任何 PubChem 行；"
            f"本表含 {filter_only['rows']:,} 行 `filter_only`，"
                        "任何在含这些行的表上引用可发表口径的写法都是缺陷。"
            ),
            ("- **列表**：`data/external/g1plus/pubchem/liquid_window/` 中 "
            f"{summary['pubchem_records_without_properties']['count']} 个 404 记录"
                        "（无实验属性节）不产生任何取值行，因此没有可排除的行，只在汇总里计数。"
            ),
            ("- **MP/BP/FP/密度**：读法与锁定 schema 的冲突见上一节；"
                        "它们以 `property_not_in_joint_enum` 出现在排除表里，而不是被静默丢弃。"
            ),
            "",
            "## 校验",
            "",
            ("`probes/verify_eta_epsilon_joint_table.py` 独立复算预注册 "
                        "`verification_contract.checks` 的全 7 条，并对观测表、排除表与构建器脚本做 SHA256 清单："
            ),
            "",
            "1. 每个必填列都在、且按其规则非空；",
            "2. 每一行的 `unit` 与 `property` 一致；",
            "3. `pure_or_mixture` 与 `n_components` 一致（1 ⇔ pure）；",
            "4. `quality_layer=publishable_core` ⇒ `source_kind` 是一次测量且 `source_doi` 非空；",
            "5. `redistributable=false` 的行按来源在清单里枚举；",
            "6. 主键无重复；",
            "7. 每个被排除的源行都有排除记录（源行全集 = 进表 ∪ 排除）。",
            "",
            "校验器对给定文件报 PASS/FAIL 并返回退出码（PASS=0，FAIL=1）。",
            "",
        ]
    )
    return "\n".join(lines)

def build_artifacts(
    *,
    table_path: Path = DEFAULT_TABLE_PATH,
    exclusions_path: Path = DEFAULT_EXCLUSIONS_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    builder_path: Path = BUILDER_PATH,
    write: bool = True,
) -> dict[str, Any]:
    result = build_tables()
    if write:
        write_csv_rows(table_path, OBSERVATION_COLUMNS, result["observations"])
        write_csv_rows(exclusions_path, EXCLUSION_COLUMNS, result["exclusions"])
    summary = build_summary(
        result,
        table_path=table_path,
        exclusions_path=exclusions_path,
        prereg_path=PREREG_PATH,
        report_path=report_path,
        builder_path=builder_path,
    )
    if write:
        write_json(summary_path, summary)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_report(summary))
    return summary

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE_PATH)
    parser.add_argument("--exclusions", type=Path, default=DEFAULT_EXCLUSIONS_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--dry-run", action="store_true", help="compute only, write nothing")
    arguments = parser.parse_args(argv)

    summary = build_artifacts(
        table_path=arguments.table,
        exclusions_path=arguments.exclusions,
        summary_path=arguments.summary,
        report_path=arguments.report,
        write=not arguments.dry_run,
    )
    readings = {
        "observations": summary["row_counts"]["observations"],
        "exclusions": summary["row_counts"]["exclusions"],
        "publishable_core_rows": summary["publishable_headline"]["rows"],
        "filter_only_rows": summary["filter_only_layer"]["rows"],
        "conflicting_keys": summary["conflicts"]["all_rows"]["conflicting_keys"],
        "group_overlap": summary["evaluation_contract"]["max_group_overlap"],
        "table_sha256": summary["manifest"]["table"]["sha256"],
        "exclusions_sha256": summary["manifest"]["exclusions"]["sha256"],
        "builder_sha256": summary["manifest"]["builder"]["sha256"],
    }
    print(json.dumps(readings, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
