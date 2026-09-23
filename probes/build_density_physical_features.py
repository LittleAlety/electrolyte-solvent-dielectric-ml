"""Replace estimated molar volume with ThermoML experimental density where available."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from rdkit import Chem
from rdkit.Chem import Descriptors

from electrolyte_ml.pathing import portable_relative_path
from electrolyte_ml.thermoml import parse_thermoml_file

MAX_DENSITY_TEMPERATURE_DELTA_K = 10.0


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


def collect_density_observations(raw_dir: Path) -> dict[str, list[dict[str, object]]]:
    by_key: dict[str, list[dict[str, object]]] = defaultdict(list)
    for path in sorted(raw_dir.glob("*.xml")):
        for row in parse_thermoml_file(path):
            if "density" not in row.get("property_name", "").lower():
                continue
            if row.get("component_count") != "1":
                continue
            if row.get("phase") not in {"", "Liquid"}:
                continue
            inchikey = row.get("primary_compound_inchi_key", "")
            if not inchikey:
                continue
            try:
                density = float(row.get("property_value", ""))
                temperature = float(row.get("temperature_value", ""))
            except ValueError:
                continue
            unit = row.get("property_unit", "").replace(" ", "").lower()
            if unit not in {"kg/m3", "kg/m^3"} or density <= 0:
                continue
            by_key[inchikey].append(
                {
                    "density_kg_m3": density,
                    "temperature_K": temperature,
                    "source_file": row.get("source_file", ""),
                    "source_doi": row.get("doi", ""),
                    "source_title": row.get("title", ""),
                    "source_property_number": row.get("property_number", ""),
                    "property_uncertainty": row.get("property_uncertainty", ""),
                    "property_value_digits": row.get("property_value_digits", ""),
                }
            )
    return dict(by_key)


def select_density(
    observations: Sequence[Mapping[str, object]],
    target_temperature: float,
    *,
    max_delta: float = MAX_DENSITY_TEMPERATURE_DELTA_K,
) -> dict[str, object] | None:
    candidates = [
        dict(observation)
        for observation in observations
        if abs(float(observation["temperature_K"]) - target_temperature) <= max_delta
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda observation: (
            abs(float(observation["temperature_K"]) - target_temperature),
            -int(observation.get("property_value_digits") or 0),
            str(observation.get("source_file", "")),
        ),
    )


def experimental_molar_volume(smiles: str, density_kg_m3: float) -> float:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError(f"cannot parse SMILES: {smiles!r}")
    molecular_weight_g_mol = float(Descriptors.MolWt(molecule))
    return molecular_weight_g_mol / 1000.0 / density_kg_m3


def run(
    *,
    source_path: Path,
    physical_path: Path,
    raw_dir: Path,
    output_path: Path,
    summary_path: Path,
) -> dict[str, object]:
    source_rows = {row["inchikey"]: row for row in read_csv_rows(source_path)}
    physical_rows = read_csv_rows(physical_path)
    density_by_key = collect_density_observations(raw_dir)
    output_rows: list[dict[str, object]] = []
    matched = 0
    missing: list[str] = []
    for row in physical_rows:
        if row["status"] == "error":
            continue
        inchikey = row["inchikey"]
        source_row = source_rows[inchikey]
        target_temperature = float(row["T_K"])
        selected = select_density(
            density_by_key.get(inchikey, []),
            target_temperature,
        )
        output = dict(row)
        if selected is None:
            missing.append(row["name"])
            output.update(
                {
                    "density_kg_m3": "",
                    "density_temperature_K": "",
                    "density_delta_T_K": "",
                    "density_source_doi": "",
                    "density_source_file": "",
                    "experimental_molar_volume_m3_mol": "",
                    "molar_volume_source": "xtb_estimated",
                    "mu_sq_over_Vm_experimental": "",
                }
            )
        else:
            density = float(selected["density_kg_m3"])
            molar_volume = experimental_molar_volume(
                source_row["smiles"],
                density,
            )
            output.update(
                {
                    "density_kg_m3": f"{density:.12g}",
                    "density_temperature_K": (
                        f"{float(selected['temperature_K']):.12g}"
                    ),
                    "density_delta_T_K": (
                        f"{abs(float(selected['temperature_K']) - target_temperature):.12g}"
                    ),
                    "density_source_doi": selected["source_doi"],
                    "density_source_file": selected["source_file"],
                    "experimental_molar_volume_m3_mol": f"{molar_volume:.12g}",
                    "molar_volume_source": "thermoml_experimental_density",
                    "mu_sq_over_Vm_experimental": (
                        f"{float(row['dipole_D']) ** 2 / molar_volume:.12g}"
                    ),
                }
            )
            matched += 1
        output_rows.append(output)
    fieldnames = list(output_rows[0]) if output_rows else []
    write_csv_rows(output_path, fieldnames, output_rows)
    summary = {
        "schema_version": 1,
        "source_path": portable_relative_path(source_path, root=REPOSITORY_ROOT),
        "physical_features_path": portable_relative_path(
            physical_path,
            root=REPOSITORY_ROOT,
        ),
        "raw_thermoml_dir": portable_relative_path(raw_dir, root=REPOSITORY_ROOT),
        "successful_compound_count": len(output_rows),
        "experimental_density_count": matched,
        "fallback_xtb_volume_count": len(missing),
        "fallback_compounds": missing,
        "max_density_temperature_delta_K": MAX_DENSITY_TEMPERATURE_DELTA_K,
        "output": portable_relative_path(output_path, root=REPOSITORY_ROOT),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "dielectric_v02.csv",
    )
    parser.add_argument(
        "--physical",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_physical_features.csv",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "raw" / "thermoml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT
        / "data"
        / "processed"
        / "dielectric_physical_features_density.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "density_feature_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = run(
        source_path=args.source,
        physical_path=args.physical,
        raw_dir=args.raw_dir,
        output_path=args.output,
        summary_path=args.summary,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
