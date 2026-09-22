"""Build the high-temperature dielectric extension with a single EC literature row."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path

from rdkit import Chem

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256

EC_INCHIKEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"
EC_SMILES = "O=C1OCC1"
EC_DOI = "10.1021/je050341y"
WINDOW_MIN_K = Decimal("313.15")
WINDOW_MAX_K = Decimal("323.15")

EXT_COLUMNS = (
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "dielectric",
    "frequency_MHz",
    "property_family",
    "uncertainty",
    "uncertainty_value",
    "uncertainty_kind",
    "confidence_level",
    "uncertainty_text",
    "uncertainty_relative_percent_max",
    "source_doi",
    "source_type",
    "source_file",
    "sha256",
    "n_observations",
    "gate_flags",
)
OBSERVATION_COLUMNS = (
    "observation_id",
    "dataset_source",
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "dielectric",
    "frequency_MHz",
    "property_family",
    "uncertainty_value",
    "uncertainty_kind",
    "confidence_level",
    "source_doi",
    "source_type",
    "source_file",
    "sha256",
    "selection_status",
    "gate_flags",
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _temperature_in_window(value: str) -> bool:
    try:
        temperature = Decimal(value)
    except (InvalidOperation, ValueError):
        return False
    return WINDOW_MIN_K <= temperature <= WINDOW_MAX_K


def _canonical_from_inchi(inchi: str, label: str) -> tuple[str, str]:
    molecule = Chem.MolFromInchi(inchi)
    if molecule is None:
        raise ValueError(f"cannot parse InChI for {label}: {inchi!r}")
    inchikey = Chem.MolToInchiKey(molecule)
    if not inchikey:
        raise ValueError(f"cannot derive InChIKey for {label}")
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True), inchikey


def _ec_row() -> dict[str, object]:
    return {
        "inchikey": EC_INCHIKEY,
        "smiles": EC_SMILES,
        "name": "ethylene carbonate",
        "T_K": "313.15",
        "dielectric": "90.5",
        "frequency_MHz": "1",
        "property_family": "frequency_dependent",
        "uncertainty": "",
        "uncertainty_value": "",
        "uncertainty_kind": "relative_upper_bound",
        "confidence_level": "",
        "uncertainty_text": "<1.5% relative",
        "uncertainty_relative_percent_max": "1.5",
        "source_doi": EC_DOI,
        "source_type": "literature_manual_entry",
        "source_file": (
            "Chernyak, J. Chem. Eng. Data 2006, 51(2), 416-418, "
            "Table 1, p416"
        ),
        "sha256": "",
        "n_observations": "1",
        "gate_flags": (
            "high_temperature_extension|literature_manual_entry|"
            "single_source|frequency_1mhz"
        ),
    }


def build_extension(
    raw_rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    selected: list[dict[str, object]] = []
    for row_index, row in enumerate(raw_rows, start=2):
        if row.get("property_family") != "zero_frequency":
            continue
        if row.get("is_pure") != "True":
            continue
        if not _temperature_in_window(row.get("temperature_k", "")):
            continue
        smiles, inchikey = _canonical_from_inchi(
            row.get("primary_inchi", ""),
            f"raw row {row_index}",
        )
        source_file = (
            "data/raw/thermoml/" + Path(row.get("source_file", "")).name
        )
        selected.append(
            {
                "observation_id": f"p1_ext:{row_index}",
                "dataset_source": "P1 ThermoML",
                "inchikey": inchikey,
                "smiles": smiles,
                "name": row.get("primary_name", ""),
                "T_K": row.get("temperature_k", ""),
                "dielectric": row.get("value", ""),
                "frequency_MHz": "0",
                "property_family": "zero_frequency",
                "uncertainty_value": (
                    row.get("expanded_uncertainty")
                    or row.get("standard_uncertainty")
                    or ""
                ),
                "uncertainty_kind": row.get("uncertainty_kind", ""),
                "confidence_level": row.get("confidence_level", ""),
                "source_doi": row.get("doi", ""),
                "source_type": "thermoml",
                "source_file": source_file,
                "sha256": row.get("source_sha256", ""),
                "selection_status": "high_temperature_extension",
                "gate_flags": (
                    "high_temperature_extension|zero_frequency|"
                    "pure_component|experimental"
                ),
            }
        )
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in selected:
        grouped[str(row["inchikey"])].append(row)
    compound_rows: list[dict[str, object]] = []
    for inchikey, rows in sorted(grouped.items()):
        values = [Decimal(str(row["dielectric"])) for row in rows]
        temperatures = [Decimal(str(row["T_K"])) for row in rows]
        compound_rows.append(
            {
                "inchikey": inchikey,
                "smiles": rows[0]["smiles"],
                "name": rows[0]["name"],
                "T_K": _text(_median(temperatures)),
                "dielectric": _text(_median(values)),
                "frequency_MHz": "0",
                "property_family": "zero_frequency",
                "uncertainty": "",
                "uncertainty_value": "",
                "uncertainty_kind": rows[0]["uncertainty_kind"],
                "confidence_level": rows[0]["confidence_level"],
                "uncertainty_text": "",
                "uncertainty_relative_percent_max": "",
                "source_doi": ";".join(
                    sorted({str(row["source_doi"]) for row in rows})
                ),
                "source_type": "thermoml",
                "source_file": ";".join(
                    sorted({str(row["source_file"]) for row in rows})
                ),
                "sha256": ";".join(
                    sorted({str(row["sha256"]) for row in rows})
                ),
                "n_observations": str(len(rows)),
                "gate_flags": (
                    "high_temperature_extension|zero_frequency|"
                    "pure_component|experimental"
                ),
            }
        )
    compound_rows.append(_ec_row())
    ec_observation = {
        "observation_id": "literature:chernyak_2006_table1_ec",
        "dataset_source": "Chernyak 2006",
        "inchikey": EC_INCHIKEY,
        "smiles": EC_SMILES,
        "name": "ethylene carbonate",
        "T_K": "313.15",
        "dielectric": "90.5",
        "frequency_MHz": "1",
        "property_family": "frequency_dependent",
        "uncertainty_value": "",
        "uncertainty_kind": "relative_upper_bound",
        "confidence_level": "",
        "source_doi": EC_DOI,
        "source_type": "literature_manual_entry",
        "source_file": (
            "Chernyak, J. Chem. Eng. Data 2006, 51(2), 416-418, "
            "Table 1, p416"
        ),
        "sha256": "",
        "selection_status": "literature_manual_entry",
        "gate_flags": (
            "high_temperature_extension|literature_manual_entry|"
            "single_source|frequency_1mhz"
        ),
    }
    observations = [*selected, ec_observation]
    summary = {
        "schema_version": 1,
        "row_counts": {
            "nist_observations": len(selected),
            "nist_keys": len(grouped),
            "ec_rows": 1,
            "total_keys": len(grouped) + 1,
            "observation_rows": len(observations),
        },
        "selection": {
            "window_K": [str(WINDOW_MIN_K), str(WINDOW_MAX_K)],
            "population": "P1 zero-frequency pure-component observations",
        },
        "ec_manual_entry": {
            "name": "ethylene carbonate",
            "inchikey": EC_INCHIKEY,
            "T_K": "313.15",
            "temperature_C": "40",
            "dielectric": "90.5",
            "frequency_MHz": "1",
            "property_family": "frequency_dependent",
            "source_doi": EC_DOI,
            "source": "Chernyak J. Chem. Eng. Data 2006 51(2) 416-418 Table 1 p416",
            "sample_purity": ">99.9 mass%",
            "instrument": "Agilent 4284A / 16452A",
            "uncertainty_text": "<1.5% relative",
            "uncertainty_relative_percent_max": "1.5",
            "frequency_note": "static dielectric constant by capacitance at 1 MHz",
        },
        "main_dielectric_v01_modified": False,
        "main_dielectric_v01_sha256": canonical_text_sha256(
            REPOSITORY_ROOT / "data" / "dielectric_v01.csv"
        ),
        "limitations": [
            "EC is a single-source 1 MHz manual literature point at 313.15 K.",
            "The EC value is not extrapolated to other temperatures.",
            "The high-temperature NIST extension uses median compound values.",
        ],
    }
    return compound_rows, observations, summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "dielectric_raw.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "dielectric_v01_ext.csv",
    )
    parser.add_argument(
        "--observations",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "data"
            / "processed"
            / "dielectric_v01_ext_observations.csv"
        ),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "dielectric_v01_ext_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows, observations, summary = build_extension(read_csv_rows(args.raw))
    write_csv(args.output, EXT_COLUMNS, rows)
    write_csv(args.observations, OBSERVATION_COLUMNS, observations)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
