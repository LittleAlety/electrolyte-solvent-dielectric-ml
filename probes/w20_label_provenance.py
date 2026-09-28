"""Week 20 -- W20-7: the three-tier label rule and a per-channel provenance sidecar.

This module fits no model, produces no reading and touches no frozen artefact.
It *unifies the scattered role columns* that already live inside the frozen
layer tables into one sidecar with a single vocabulary.  It invents no new
science: every value it emits is read from a table that already exists.

The normative sentence (registered verbatim, see LABEL_RULE_SENTENCE)
-------------------------------------------------------------------
A channel label must be same-source and same-level; a value from another
theoretical level may enter only after a cross-level calibration is performed
and its ``calibration_id`` is registered; if the calibration fails its gate the
whole column stays empty and is ``reference_only``; ML predicted values never
enter a pool; licence-restricted values never enter a pool.

The misconception this file corrects
-------------------------------------
DFT *is* the label in this repository.  The orbital channel primary source,
Batt-P30K, is ``wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)``; the second source,
PubChemQC, is ``B3LYP/6-31G*//PM6``; THEMol is a GFN2-xTB single point this
repository ran itself.  What is banned is not computed values but (1) ML/QSAR
predictions (``predicted_not_experimental``, circular), (2) mixing different
levels into one column without a registered calibration, and (3) restricted
licence values.

What the sidecar is
--------------------
One row per observed ``(channel, source_layer, role, calibration_id)``
combination across the frozen layer tables.  Columns are the seven the Week 20
charter names -- ``channel / role / reference_level / calibration_id /
source_doi / locator_table_figure / access_class`` -- plus ``source_layer``
(the row key, needed because one channel can draw on several layers) and
``n_rows`` (the coverage count).  The role vocabulary is closed and mapped, so
an existing spelling such as ``uncalibrated_reference`` or ``paired_anchor``
cannot enter the sidecar unmapped.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

REGISTRY_PATH = REPOSITORY_ROOT / "data" / "processed" / "four_core_key_registry.csv"
SIDECAR_PATH = REPOSITORY_ROOT / "data" / "processed" / "four_core_label_provenance_sidecar.csv"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w20_label_provenance_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_label_provenance_summary.json"

#: The closed role vocabulary of the sidecar.
ROLES = ("primary_reference", "calibrated_estimate", "reference_only", "feature_only")

#: Existing spellings mapped onto the closed vocabulary.  A spelling that is not
#: here and is not already a role is an error, not a silent pass-through.
ROLE_ALIASES: dict[str, str] = {
    "calibrated_estimate": "calibrated_estimate",
    "paired_anchor": "reference_only",
    "uncalibrated_reference": "reference_only",
    "reference_only": "reference_only",
    "primary_reference": "primary_reference",
    "feature_only": "feature_only",
}

ACCESS_CLASSES = ("open", "attribution_required", "noncommercial", "unknown")

#: Registered verbatim from the Week 20 charter, section W20-7.
LABEL_RULE_SENTENCE = (
    "一个通道的标签必须**同源同水平**；引入另一理论水平的值时必须先做跨水平标定并登记 `calibration_id`；"
    "**标定不过门则该列整列留空、只作 `reference_only`**；**ML 预测值永不入池**；**受限许可值永不入池**。"
)

#: The three reference levels, named, with the correction spelled out.
DFT_IS_THE_LABEL: dict[str, str] = {
    "orbitals_primary": "Batt-P30K = wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)",
    "orbitals_second": "PubChemQC = B3LYP/6-31G*//PM6",
    "orbitals_third": "THEMol = repository-run GFN2-xTB single point",
    "banned_1": "ML/QSAR predictions (predicted_not_experimental), circular",
    "banned_2": "different levels mixed into one column without a registered calibration",
    "banned_3": "licence-restricted values",
}

SIDECAR_COLUMNS = (
    "channel",
    "source_layer",
    "role",
    "reference_level",
    "calibration_id",
    "source_doi",
    "locator_table_figure",
    "access_class",
    "n_rows",
)


@dataclass(frozen=True)
class ProvenanceLayer:
    """One frozen layer table and how its rows map onto the sidecar."""

    channel: str
    layer: str
    path: str
    reference_level: str
    source_doi: str
    locator_table_figure: str
    access_class: str
    role: str | None = None
    role_column: str | None = None
    calibration_column: str | None = None
    filter_column: str | None = None
    filter_value: str | None = None
    has_column: str | None = None


LAYERS: tuple[ProvenanceLayer, ...] = (
    ProvenanceLayer(
        channel="orbitals",
        layer="batt_p30k_primary",
        path="data/processed/redox_merged.csv",
        reference_level="wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)",
        source_doi="10.1021/acsnano.6c06255",
        locator_table_figure="dataset-level (redox_merged.csv)",
        access_class="open",
        role="primary_reference",
        filter_column="source",
        filter_value="Batt-P30K",
    ),
    ProvenanceLayer(
        channel="orbitals",
        layer="pubchemqc_second_source",
        path="data/processed/orbital_second_source_layer.csv",
        reference_level="B3LYP/6-31G*//PM6 (gas phase)",
        source_doi="10.1021/acs.jcim.3c00899",
        locator_table_figure="per-row (orbital_second_source_layer.csv)",
        access_class="attribution_required",
        role_column="role",
        calibration_column="calibration_id",
    ),
    ProvenanceLayer(
        channel="orbitals",
        layer="themol_gfn2",
        path="data/processed/themol_orbital_layer.csv",
        reference_level=(
            "GFN2-xTB//B3LYP-D3(BJ)/DZVP (gas-phase single point on the DFT geometry)"
        ),
        source_doi="ByteDance-Seed/THEMol (Hessian subset)",
        locator_table_figure="per-row (themol_orbital_layer.csv)",
        access_class="noncommercial",
        role_column="role",
        calibration_column="calibration_id",
    ),
    ProvenanceLayer(
        channel="orbitals",
        layer="themol_gfn2_expanded",
        path="data/processed/themol_orbital_layer_expanded.csv",
        reference_level=(
            "GFN2-xTB//B3LYP-D3(BJ)/DZVP (gas-phase single point on the DFT geometry)"
        ),
        source_doi="ByteDance-Seed/THEMol (Hessian subset)",
        locator_table_figure="per-row (themol_orbital_layer_expanded.csv)",
        access_class="noncommercial",
        role_column="role",
        calibration_column="calibration_id",
    ),
    ProvenanceLayer(
        channel="redox_label",
        layer="rx392",
        path="data/processed/redox_merged.csv",
        reference_level=(
            "wB97X-V/def2-TZVPPD/SMD(epsilon=18.5) + redox_free_ener.py convention"
        ),
        source_doi="10.1021/acsnano.6c06255",
        locator_table_figure="dataset-level (redox_merged.csv)",
        access_class="open",
        role="primary_reference",
        filter_column="source",
        filter_value="RX-392",
    ),
    ProvenanceLayer(
        channel="dielectric",
        layer="dielectric_v04",
        path="data/dielectric_v04.csv",
        reference_level="experimental",
        source_doi="per-row (source_dois_all)",
        locator_table_figure="per-row (source_table / source_page)",
        access_class="unknown",
        role="primary_reference",
    ),
    ProvenanceLayer(
        channel="viscosity",
        layer="viscosity_v02",
        path="data/viscosity_v02.csv",
        reference_level="experimental",
        source_doi="per-row (source_doi)",
        locator_table_figure="per-row (thermoml_file:source_row_index)",
        access_class="open",
        role="primary_reference",
    ),
    ProvenanceLayer(
        channel="density",
        layer="density_v01",
        path="data/density_v01.csv",
        reference_level="experimental",
        source_doi="per-row (source_doi)",
        locator_table_figure="per-row (thermoml_file:source_row_index)",
        access_class="open",
        role="primary_reference",
    ),
    ProvenanceLayer(
        channel="liquid_window",
        layer="liquid_window_features",
        path="data/processed/liquid_window_features.csv",
        reference_level="PubChem depositor compilation (experimental)",
        source_doi="per-row (depositor / reference_number)",
        locator_table_figure="per-row (reference_number)",
        access_class="open",
        role="reference_only",
    ),
)

#: Column names that carry provenance inside the frozen layer tables.  Used only
#: to count how scattered the provenance was before this sidecar.
PROVENANCE_COLUMN_HINTS = (
    "role",
    "calibration_id",
    "source",
    "source_doi",
    "source_dois_all",
    "source_level",
    "source_license",
    "source_dataset",
    "source_scope",
    "source_table",
    "source_page",
    "source_kind",
    "source_priority",
    "source_url",
    "value_origin",
    "evidence_level",
    "method",
    "method_name",
    "status",
    "quality_layer",
    "redistribution_status",
    "redistribution_conditions",
    "license_url",
    "depositor",
    "reference_number",
    "selection_rule",
    "peer_reviewed",
    "confidence",
    "conflict",
    "thermoml_file",
    "source_row_index",
    "structure_resolution_source",
    "temperature_source",
)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), [dict(row) for row in reader]


def _mapped_role(spelling: str) -> str:
    mapped = ROLE_ALIASES.get(spelling)
    if mapped is None:
        raise ValueError(f"role spelling is not registered: {spelling!r}")
    return mapped


def _layer_rows(layer: ProvenanceLayer) -> list[dict[str, str]]:
    _, rows = read_csv(REPOSITORY_ROOT / layer.path)
    if layer.filter_column is not None:
        rows = [row for row in rows if row.get(layer.filter_column, "") == layer.filter_value]
    return rows


def sidecar_rows() -> list[dict[str, str]]:
    """One row per observed (channel, source_layer, role, calibration_id)."""

    out: list[dict[str, str]] = []
    for layer in LAYERS:
        rows = _layer_rows(layer)
        buckets: dict[tuple[str, str], int] = {}
        for row in rows:
            if layer.role is not None:
                role = layer.role
            else:
                assert layer.role_column is not None
                role = _mapped_role(str(row.get(layer.role_column, "")))
            calibration_id = ""
            if layer.calibration_column is not None:
                calibration_id = str(row.get(layer.calibration_column, "")).strip()
            key = (role, calibration_id)
            buckets[key] = buckets.get(key, 0) + 1
        for (role, calibration_id), count in sorted(buckets.items()):
            out.append(
                {
                    "channel": layer.channel,
                    "source_layer": layer.layer,
                    "role": role,
                    "reference_level": layer.reference_level,
                    "calibration_id": calibration_id,
                    "source_doi": layer.source_doi,
                    "locator_table_figure": layer.locator_table_figure,
                    "access_class": layer.access_class,
                    "n_rows": str(count),
                }
            )
    return out


def registry_coverage() -> dict[str, int]:
    """Populated registry cells per channel (the sidecar coverage target)."""

    _, rows = read_csv(REGISTRY_PATH)
    coverage = {channel: 0 for channel in (
        "dielectric",
        "viscosity",
        "orbitals",
        "redox_label",
        "density",
        "liquid_window",
    )}
    for row in rows:
        for channel in coverage:
            if str(row.get(f"has_{channel}", "")).strip().lower() == "true":
                coverage[channel] += 1
    return coverage


def scattered_provenance_columns() -> dict[str, Any]:
    """Count the provenance columns still scattered inside the frozen tables."""

    per_file: dict[str, list[str]] = {}
    seen: set[str] = set()
    for layer in LAYERS:
        key = layer.path
        if key in seen:
            continue
        seen.add(key)
        fieldnames, _ = read_csv(REPOSITORY_ROOT / key)
        hits = [
            name
            for name in fieldnames
            if any(hint in name for hint in PROVENANCE_COLUMN_HINTS)
        ]
        per_file[key] = hits
    return {
        "per_file": per_file,
        "files": len(per_file),
        "columns_total": sum(len(hits) for hits in per_file.values()),
    }


def plan() -> dict[str, Any]:
    return {
        "schema_version": "w20_label_provenance_plan_v0",
        "task": "week20_w20_7_label_provenance_sidecar",
        "status": "registered_no_model",
        "produces_reading": False,
        "promoted": False,
        "main_scoreboard_untouched": True,
        "scoreboard_attempts_delta": 0,
        "shot_number_taken": None,
        "roles": list(ROLES),
        "access_classes": list(ACCESS_CLASSES),
        "label_rule_sentence": LABEL_RULE_SENTENCE,
        "dft_is_the_label": dict(DFT_IS_THE_LABEL),
        "sidecar_columns": list(SIDECAR_COLUMNS),
        "sidecar": "data/processed/four_core_label_provenance_sidecar.csv",
        "unifies_existing_vocabulary_only": True,
    }


def run() -> dict[str, Any]:
    rows = sidecar_rows()
    coverage = registry_coverage()
    scattered = scattered_provenance_columns()
    role_tally: dict[str, int] = {role: 0 for role in ROLES}
    for row in rows:
        role_tally[row["role"]] += int(row["n_rows"])
    return {
        **plan(),
        "status": "executed_descriptive",
        "sidecar_rows": len(rows),
        "sidecar_columns": list(SIDECAR_COLUMNS),
        "role_tally": role_tally,
        "rows_by_channel": _rows_by_channel(rows),
        "registry_coverage": coverage,
        "registry_coverage_total": sum(coverage.values()),
        "scattered_provenance": scattered,
        "after_columns": len(SIDECAR_COLUMNS),
    }


def _rows_by_channel(rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for row in rows:
        tally[row["channel"]] = tally.get(row["channel"], 0) + int(row["n_rows"])
    return tally


def write_sidecar(path: Path = SIDECAR_PATH) -> Path:
    rows = sidecar_rows()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SIDECAR_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="print the pinned plan and exit")
    parser.add_argument("--write-sidecar", action="store_true", help="write the sidecar CSV")
    parser.add_argument("--sidecar", type=Path, default=SIDECAR_PATH)
    parser.add_argument("--write-summary", action="store_true", help="write the summary JSON")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.write_sidecar:
        write_sidecar(args.sidecar)
    summary = run()
    if args.write_summary:
        args.summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    raise SystemExit(main())
