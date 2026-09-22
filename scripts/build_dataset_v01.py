"""Build the reproducible dielectric/viscosity dataset v0.1 tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from rdkit import Chem

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.standardize import centipoise_to_pascal_second, standardize_molecule

P1_SCOPE = "p1_thermoml_zero_frequency_pure_293.15_303.15K"
CHODERA_SCOPE = "chodera_2015_historical_dielectric_crosscheck"
VISCOSITY_SCOPE = "chew_2024_supp2_experimental_viscosity"
P1_MIN_T_K = Decimal("293.15")
P1_MAX_T_K = Decimal("303.15")
CHODERA_DOI = "arXiv:1506.00262"
CHEW_DOI = "10.1186/s13321-024-00820-5"

DIELECTRIC_COLUMNS = (
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "dielectric",
    "uncertainty",
    "uncertainty_value",
    "uncertainty_kind",
    "confidence_level",
    "uncertainty_json",
    "source_doi",
    "source_dois_all",
    "n_observations",
    "n_historical_observations",
    "source_scope",
    "crosscheck_available",
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
    "uncertainty_value",
    "uncertainty_kind",
    "confidence_level",
    "source_doi",
    "source_file",
    "source_sha256",
    "source_size_bytes",
    "in_selection_window",
    "selection_status",
    "source_scope",
    "gate_flags",
)
VISCOSITY_COLUMNS = (
    "record_id",
    "inchikey",
    "smiles",
    "name",
    "T_K",
    "viscosity_Pa_s",
    "density",
    "density_status",
    "viscosity_cP",
    "source_doi",
    "n_observations",
    "source_scope",
    "data_status",
    "gate_flags",
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
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _decimal_text(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)


def _median(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ValueError("median requires at least one value")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _canonical_from_inchi(inchi: str, expected_key: str, label: str) -> tuple[str, str]:
    molecule = Chem.MolFromInchi(inchi)
    if molecule is None:
        raise ValueError(f"cannot parse InChI for {label}: {inchi!r}")
    inchikey = Chem.MolToInchiKey(molecule)
    if not inchikey:
        raise ValueError(f"cannot derive InChIKey for {label}")
    if expected_key and inchikey != expected_key:
        raise ValueError(
            f"InChIKey mismatch for {label}: source={expected_key}, parsed={inchikey}"
        )
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True), inchikey


def _temperature_in_window(value: str) -> bool:
    try:
        temperature = Decimal(value)
    except (InvalidOperation, ValueError):
        return False
    return P1_MIN_T_K <= temperature <= P1_MAX_T_K


def build_p1_observations(
    p1_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    for row_index, row in enumerate(p1_rows, start=2):
        if row.get("property_family") != "zero_frequency":
            continue
        if row.get("is_pure") != "True":
            continue
        if not _temperature_in_window(row.get("temperature_k", "")):
            continue
        smiles, inchikey = _canonical_from_inchi(
            row.get("primary_inchi", ""),
            row.get("primary_inchi_key", ""),
            f"P1 row {row_index}",
        )
        uncertainty = row.get("expanded_uncertainty") or row.get("standard_uncertainty") or ""
        observations.append(
            {
                "observation_id": f"p1_dielectric:{row_index}",
                "dataset_source": "P1 ThermoML",
                "inchikey": inchikey,
                "smiles": smiles,
                "name": row.get("primary_name", ""),
                "T_K": row.get("temperature_k", ""),
                "dielectric": row.get("value", ""),
                "uncertainty_value": uncertainty,
                "uncertainty_kind": row.get("uncertainty_kind", ""),
                "confidence_level": row.get("confidence_level", ""),
                "source_doi": row.get("doi", ""),
                "source_file": (
                    "data/raw/thermoml/" + Path(row.get("source_file", "")).name
                ),
                "source_sha256": row.get("source_sha256", ""),
                "source_size_bytes": (
                    str(Path(row.get("source_file", "")).stat().st_size)
                    if Path(row.get("source_file", "")).is_file()
                    else ""
                ),
                "in_selection_window": "true",
                "selection_status": "primary",
                "source_scope": P1_SCOPE,
                "gate_flags": "zero_frequency|pure_component|experimental",
            }
        )
    return observations


def build_chodera_observations(
    chodera_rows: Sequence[Mapping[str, str]],
    *,
    source_path: Path,
) -> list[dict[str, object]]:
    source_sha256 = sha256_file(source_path)
    observations: list[dict[str, object]] = []
    for row_index, row in enumerate(chodera_rows, start=2):
        smiles = row.get("smiles", "")
        standardized = standardize_molecule(smiles)
        temperature = row.get("Temperature, K", "")
        observations.append(
            {
                "observation_id": f"chodera_2015:{row_index}",
                "dataset_source": "Chodera 2015",
                "inchikey": standardized.inchikey,
                "smiles": standardized.smiles,
                "name": row.get("components", ""),
                "T_K": temperature,
                "dielectric": row.get("Relative permittivity at zero frequency", ""),
                "uncertainty_value": "",
                "uncertainty_kind": "",
                "confidence_level": "",
                "source_doi": CHODERA_DOI,
                "source_file": "data/external/chodera_2015_data_dielectric.csv",
                "source_sha256": source_sha256,
                "source_size_bytes": str(source_path.stat().st_size),
                "in_selection_window": str(
                    _temperature_in_window(temperature)
                ).lower(),
                "selection_status": "historical_crosscheck_only",
                "source_scope": CHODERA_SCOPE,
                "gate_flags": "historical_fallback_target|experimental",
            }
        )
    return observations


def _uncertainty_summary(
    observations: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    signatures = sorted(
        {
            (
                str(row["uncertainty_value"]),
                str(row["uncertainty_kind"]),
                str(row["confidence_level"]),
            )
            for row in observations
            if row["uncertainty_value"] not in {"", None}
        }
    )
    if not signatures:
        return {
            "uncertainty": "",
            "uncertainty_value": "",
            "uncertainty_kind": "",
            "confidence_level": "",
            "uncertainty_json": "[]",
        }
    kinds = {signature[1] for signature in signatures}
    confidences = {signature[2] for signature in signatures}
    if len(kinds) == 1 and len(confidences) == 1:
        values = [
            Decimal(str(row["uncertainty_value"]))
            for row in observations
            if row["uncertainty_value"] not in {"", None}
        ]
        representative = _median(values)
        kind = next(iter(kinds))
        confidence = next(iter(confidences))
    else:
        representative = None
        kind = "mixed"
        confidence = ""
    return {
        "uncertainty": "" if representative is None else _decimal_text(representative),
        "uncertainty_value": (
            "" if representative is None else _decimal_text(representative)
        ),
        "uncertainty_kind": kind,
        "confidence_level": confidence,
        "uncertainty_json": json.dumps(
            [
                {
                    "value": value,
                    "kind": kind_value,
                    "confidence_level": confidence_value,
                }
                for value, kind_value, confidence_value in signatures
            ],
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def build_dielectric_compound_rows(
    p1_observations: Sequence[Mapping[str, object]],
    chodera_observations: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    p1_by_key: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    chodera_by_key: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in p1_observations:
        p1_by_key[str(row["inchikey"])].append(row)
    for row in chodera_observations:
        chodera_by_key[str(row["inchikey"])].append(row)

    compound_rows: list[dict[str, object]] = []
    for inchikey, observations in sorted(p1_by_key.items()):
        values = [Decimal(str(row["dielectric"])) for row in observations]
        temperatures = [Decimal(str(row["T_K"])) for row in observations]
        names = [str(row["name"]) for row in observations]
        name_counts = Counter(names)
        name = min(names, key=lambda value: (-name_counts[value], value))
        p1_dois = sorted({str(row["source_doi"]) for row in observations if row["source_doi"]})
        historical = chodera_by_key.get(inchikey, [])
        all_dois = list(p1_dois)
        if historical:
            all_dois.append(CHODERA_DOI)
        uncertainty = _uncertainty_summary(observations)
        compound_rows.append(
            {
                "inchikey": inchikey,
                "smiles": observations[0]["smiles"],
                "name": name,
                "T_K": _decimal_text(_median(temperatures)),
                "dielectric": _decimal_text(_median(values)),
                **uncertainty,
                "source_doi": ";".join(p1_dois),
                "source_dois_all": ";".join(sorted(set(all_dois))),
                "n_observations": str(len(observations)),
                "n_historical_observations": str(len(historical)),
                "source_scope": (
                    f"{P1_SCOPE};{CHODERA_SCOPE}" if historical else P1_SCOPE
                ),
                "crosscheck_available": str(bool(historical)).lower(),
                "gate_flags": (
                    "zero_frequency|pure_component|experimental"
                    + ("|historical_fallback_target" if historical else "")
                ),
            }
        )
    return compound_rows


def build_viscosity_rows(
    viscosity_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in viscosity_rows:
        standardized = standardize_molecule(row["CANON_SMILES"])
        viscosity_pa_s = centipoise_to_pascal_second(row["Viscosity (cP)"])
        rows.append(
            {
                "record_id": row["Index"],
                "inchikey": standardized.inchikey,
                "smiles": standardized.smiles,
                "name": row["Name"],
                "T_K": row["Temperature (K)"],
                "viscosity_Pa_s": _decimal_text(viscosity_pa_s),
                "density": "",
                "density_status": "not_available",
                "viscosity_cP": row["Viscosity (cP)"],
                "source_doi": CHEW_DOI,
                "n_observations": "1",
                "source_scope": VISCOSITY_SCOPE,
                "data_status": "experimental",
                "gate_flags": "experimental",
            }
        )
    return rows


def _range(values: Sequence[Decimal]) -> dict[str, object]:
    return {
        "min": _decimal_text(min(values)) if values else None,
        "max": _decimal_text(max(values)) if values else None,
    }


def build_dataset_outputs(
    *,
    p1_path: Path,
    chodera_path: Path,
    viscosity_path: Path,
    predicted_viscosity_path: Path,
    intersection_summary_path: Path,
) -> dict[str, Any]:
    p1_source_rows = read_csv_rows(p1_path)
    chodera_source_rows = read_csv_rows(chodera_path)
    viscosity_source_rows = read_csv_rows(viscosity_path)
    predicted_rows = read_csv_rows(predicted_viscosity_path)

    p1_observations = build_p1_observations(p1_source_rows)
    chodera_observations = build_chodera_observations(
        chodera_source_rows,
        source_path=chodera_path,
    )
    dielectric_rows = build_dielectric_compound_rows(
        p1_observations,
        chodera_observations,
    )
    viscosity_rows = build_viscosity_rows(viscosity_source_rows)

    p1_keys = {str(row["inchikey"]) for row in p1_observations}
    chodera_keys = {str(row["inchikey"]) for row in chodera_observations}
    overlap_keys = p1_keys.intersection(chodera_keys)
    union_keys = p1_keys.union(chodera_keys)
    intersection_summary = json.loads(
        intersection_summary_path.read_text(encoding="utf-8")
    )

    p1_temperatures = [Decimal(str(row["T_K"])) for row in p1_observations]
    chodera_temperatures = [Decimal(str(row["T_K"])) for row in chodera_observations]
    viscosity_temperatures = [Decimal(str(row["T_K"])) for row in viscosity_rows]
    summary = {
        "schema_version": 1,
        "row_counts": {
            "dielectric_compound_rows": len(dielectric_rows),
            "dielectric_compound_unique_inchikeys": len(p1_keys),
            "dielectric_observation_rows": (
                len(p1_observations) + len(chodera_observations)
            ),
            "p1_observation_rows": len(p1_observations),
            "chodera_observation_rows": len(chodera_observations),
            "viscosity_rows": len(viscosity_rows),
            "viscosity_unique_inchikeys": len(
                {str(row["inchikey"]) for row in viscosity_rows}
            ),
        },
        "temperature_ranges_K": {
            "p1": _range(p1_temperatures),
            "chodera": _range(chodera_temperatures),
            "viscosity": _range(viscosity_temperatures),
        },
        "source_counts": {
            "p1_source_documents": len(
                {str(row["source_sha256"]) for row in p1_observations}
            ),
            "p1_source_dois": len(
                {str(row["source_doi"]) for row in p1_observations}
            ),
            "chodera_source_rows": len(chodera_source_rows),
            "viscosity_reference_strings": len(
                {str(row.get("Reference", "")) for row in viscosity_source_rows}
            ),
        },
        "overlap": {
            "p1_keys": len(p1_keys),
            "chodera_keys": len(chodera_keys),
            "overlap_keys": len(overlap_keys),
            "union_key_count": len(union_keys),
            "chodera_adds_unique_keys": len(chodera_keys - p1_keys),
            "union_is_not_145": len(overlap_keys) == len(chodera_keys),
            "chodera_role": "historical_crosscheck_only",
        },
        "dielectric_rules": {
            "window_K": [str(P1_MIN_T_K), str(P1_MAX_T_K)],
            "population": "P1 zero-frequency pure-component observations",
            "compound_value": "median dielectric in the selection window",
            "temperature": "median observation temperature",
            "ec_in_compound_level": any(
                str(row["name"]).casefold() == "ethylene carbonate"
                for row in dielectric_rows
            ),
        },
        "viscosity": {
            "fraction": "experimental only",
            "conversion": "viscosity_Pa_s = viscosity_cP * 1e-3",
            "predicted_rows_excluded": len(predicted_rows),
            "predicted_source_scope": "chew_2024_supp3_prediction",
            "md_density_used_as_density": False,
            "density_status": "not_available",
        },
        "intersection": {
            "rows_not_used": int(
                intersection_summary.get("paired_row_intersection_count", 0)
            ),
            "model_ready": bool(intersection_summary.get("model_ready", False)),
            "usage": "not_used_for_dataset_v01_training",
        },
        "limitations": [
            "Chodera 2015 does not increase the independent molecule count in v0.1.",
            "The 45 Chodera keys all overlap the 100 P1 keys; the union is 100, not 145.",
            "Chew supplement 3 predictions are excluded from experimental viscosity.",
            "MD density fields are excluded because they are not experimental density.",
        ],
    }
    return {
        "dielectric_compound_rows": dielectric_rows,
        "dielectric_observation_rows": p1_observations + chodera_observations,
        "viscosity_rows": viscosity_rows,
        "summary": summary,
    }


def write_dataset_outputs(
    outputs: Mapping[str, Any],
    *,
    dielectric_path: Path,
    viscosity_path: Path,
    observations_path: Path,
    summary_path: Path,
) -> None:
    write_csv_rows(dielectric_path, DIELECTRIC_COLUMNS, outputs["dielectric_compound_rows"])
    write_csv_rows(viscosity_path, VISCOSITY_COLUMNS, outputs["viscosity_rows"])
    write_csv_rows(
        observations_path,
        OBSERVATION_COLUMNS,
        outputs["dielectric_observation_rows"],
    )
    write_json(summary_path, outputs["summary"])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--p1",
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
        "--predicted-viscosity",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "data"
            / "external"
            / "chew_2024_viscosity_supp_3.csv"
        ),
    )
    parser.add_argument(
        "--intersection-summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "p3_viscosity_summary.json",
    )
    parser.add_argument(
        "--dielectric-output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "dielectric_v01.csv",
    )
    parser.add_argument(
        "--viscosity-output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "viscosity_v01.csv",
    )
    parser.add_argument(
        "--observations-output",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "data"
            / "processed"
            / "dielectric_v01_observations.csv"
        ),
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "dataset_v01_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    outputs = build_dataset_outputs(
        p1_path=args.p1,
        chodera_path=args.chodera,
        viscosity_path=args.viscosity,
        predicted_viscosity_path=args.predicted_viscosity,
        intersection_summary_path=args.intersection_summary,
    )
    write_dataset_outputs(
        outputs,
        dielectric_path=args.dielectric_output,
        viscosity_path=args.viscosity_output,
        observations_path=args.observations_output,
        summary_path=args.summary_output,
    )
    print(json.dumps(outputs["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
