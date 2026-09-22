"""Export the important Week 1 probe and closure results."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.p1_thermoml_dielectric import _identity

DEFAULT_OUTPUT_DIR = Path(r"E:\Claude Code\电解质ML\成果输出\week1")


def build_week1_report(summary: Mapping[str, object]) -> str:
    family_counts = summary.get("zero_frequency_family_counts_near_center", {})
    closure = summary.get("week1_closure", {})
    if not isinstance(closure, Mapping):
        closure = {}
    decision_status = str(summary.get("decision_status", "provisional"))
    handbook_gate_executed = summary.get("handbook_gate_executed") is True
    gate_label = (
        "P1 provisional decision"
        if decision_status != "archive_verified"
        else "P1 archive-verified decision"
    )
    gate_execution = (
        "P1 handbook gate: EXECUTED"
        if handbook_gate_executed
        else "P1 handbook gate: NOT formally executed"
    )
    return f"""# Week 1 Probe Results

## P0

P0 gate: PASS

- RDKit parses ethylene carbonate `C1COC(=O)O1`.
- Morgan fingerprint generation succeeds.
- A molecular structure image is exported.

## P1 And Closure

- {gate_label}: `{summary.get("mainline_decision")}`.
- mainline_decision: `{summary.get("mainline_decision")}`.
- decision_status: `{decision_status}`.
- handbook_gate_executed: `{handbook_gate_executed}`.
- source_mode: `{summary.get("source_mode")}`.
- document_count: {summary.get("document_count")}.
- source_documents_with_dielectric_rows: {summary.get("source_documents_with_dielectric_rows")}.
- observation_rows: {summary.get("observation_rows")}.
- all-component zero-frequency compounds near 298 K: {summary.get("all_component_zero_frequency_components_near_center")}.
- pure-component gate compounds: {summary.get("pure_zero_frequency_components_near_center")}.
- target_family_components_near_center: {summary.get("target_family_components_near_center")}.
- family counts: `{json.dumps(family_counts, ensure_ascii=False)}`.
- source_limitation: {summary.get("source_limitation")}
- Week 1 closure summary: `{json.dumps(closure, ensure_ascii=False, sort_keys=True)}`.

{gate_execution}. The fallback source remains provisional, and mixture partners
are listed in the coverage census but do not enter the gate.
Five spot-check anchors pass, PC is recorded as `not_found`, and EC is blocked
by the temperature gate. The requested 308-solvent ECW target is unavailable;
Chodera 2015 is an explicit 246-row historical fallback. Experimental viscosity
and model predictions are stored separately. The compound-level InChIKey
intersection is 62 compounds; 46 keys form 456 temperature-paired loose-join
rows with `model_ready=false`.

## Files

- `p0_ec_molecule.png`: P0 molecule structure.
- `00_sanity_check.ipynb`: P0 notebook.
- `dielectric_raw.csv`: P1 dielectric observations.
- `p1_summary.json`: P1 and closure machine-readable summary.
- `thermoml_source_manifest.csv`: verified source provenance.
- `p1_spot_check.csv`: anchor checks and EC guard.
- `coverage_gap.csv` and `coverage_gap_summary.json`: 308 gap evidence.
- `viscosity_raw.csv`: 3,582 experimental rows.
- `viscosity_predictions.csv`: 650 predicted rows.
- `dielectric_viscosity_intersection.csv`: 46 paired keys and 456 rows.
- `p3_viscosity_summary.json`: intersection method and counts.
- `decisions_log.md`: provisional decisions and negative results.
- `data_schema.md`: unified property schema and units.
- `dielectric_distribution.png` and `family_coverage.png`: P1 EDA.
"""


def write_unique_compounds_csv(
    observations_path: Path,
    output_path: Path,
    *,
    temperature_center: Decimal = Decimal("298.15"),
    temperature_tolerance: Decimal = Decimal(5),
) -> None:
    unique: dict[str, dict[str, object]] = {}
    with observations_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["property_family"] != "zero_frequency":
                continue
            temperature_text = row.get("temperature_k", "")
            if not temperature_text:
                continue
            temperature = Decimal(temperature_text)
            if abs(temperature - temperature_center) > temperature_tolerance:
                continue
            components = json.loads(row["components_json"])
            for component in components:
                identity = _identity(component)
                record = unique.setdefault(
                    identity,
                    {
                        "identity": identity,
                        "name": component["name"],
                        "formula": component["formula"],
                        "standard_inchi_key": component["standard_inchi_key"],
                        "cas_registry_number": component["cas_registry_number"],
                        "observations_near_298": 0,
                        "appears_in_pure_component_dataset": False,
                    },
                )
                record["observations_near_298"] = int(record["observations_near_298"]) + 1
                if row.get("is_pure") == "True":
                    record["appears_in_pure_component_dataset"] = True

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "identity",
        "name",
        "formula",
        "standard_inchi_key",
        "cas_registry_number",
        "observations_near_298",
        "appears_in_pure_component_dataset",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            sorted(unique.values(), key=lambda record: str(record["name"]).casefold())
        )


def export_week1_results(output_dir: Path) -> None:
    summary_path = REPOSITORY_ROOT / "probes" / "p1_summary.json"
    observations_path = REPOSITORY_ROOT / "data" / "processed" / "dielectric_raw.csv"
    artifacts_dir = REPOSITORY_ROOT / "probes" / "artifacts"
    processed_dir = REPOSITORY_ROOT / "data" / "processed"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    output_dir.mkdir(parents=True, exist_ok=True)
    copies = {
        artifacts_dir / "p0_ec_molecule.png": output_dir / "p0_ec_molecule.png",
        observations_path: output_dir / "dielectric_raw.csv",
        processed_dir / "thermoml_source_manifest.csv": output_dir
        / "thermoml_source_manifest.csv",
        processed_dir / "p1_spot_check.csv": output_dir / "p1_spot_check.csv",
        processed_dir / "coverage_gap.csv": output_dir / "coverage_gap.csv",
        processed_dir / "coverage_gap_summary.json": output_dir
        / "coverage_gap_summary.json",
        processed_dir / "viscosity_raw.csv": output_dir / "viscosity_raw.csv",
        processed_dir / "viscosity_predictions.csv": output_dir
        / "viscosity_predictions.csv",
        processed_dir / "dielectric_viscosity_intersection.csv": output_dir
        / "dielectric_viscosity_intersection.csv",
        REPOSITORY_ROOT / "probes" / "p3_viscosity_summary.json": output_dir
        / "p3_viscosity_summary.json",
        REPOSITORY_ROOT / "reports" / "decisions_log.md": output_dir
        / "decisions_log.md",
        REPOSITORY_ROOT / "docs" / "week1" / "data_schema.md": output_dir
        / "data_schema.md",
        artifacts_dir / "dielectric_distribution.png": output_dir
        / "dielectric_distribution.png",
        artifacts_dir / "family_coverage.png": output_dir / "family_coverage.png",
        REPOSITORY_ROOT / "notebooks" / "00_sanity_check.ipynb": output_dir
        / "00_sanity_check.ipynb",
        REPOSITORY_ROOT / "probes" / "p1_eda.ipynb": output_dir / "p1_eda.ipynb",
    }
    for source, destination in copies.items():
        shutil.copy2(source, destination)

    summary["outputs"] = {
        "dielectric_raw_csv": "dielectric_raw.csv",
        "summary_json": "p1_summary.json",
        "dielectric_distribution_png": "dielectric_distribution.png",
        "family_coverage_png": "family_coverage.png",
    }
    (output_dir / "p1_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_unique_compounds_csv(
        observations_path,
        output_dir / "zero_frequency_near_298_compounds.csv",
    )
    (output_dir / "week1_report.md").write_text(
        build_week1_report(summary),
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    export_week1_results(args.output_dir)
    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
