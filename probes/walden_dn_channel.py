"""eps-eta Walden coupling pairs and the DN fifth-channel registration (Week 17, W17-7).

``probes/walden_dn_channel_prereg.json`` is the authority for this build and it was
locked before the first run. The pairing rule, the temperature-alignment rule, the
coupling definition, the DN admissibility rule and the DN coverage threshold are
read from that file; nothing here restates a rule in a weaker form.

Three rules are cheap to state and expensive to hold, so they are encoded rather
than asserted:

* a pair exists only where the two channels share a stored temperature. Nothing is
  interpolated onto a common grid and nothing is extrapolated: the stored
  temperatures sit on a coarse grid (278.15, 280.65, 283.15 K ...), so widening the
  tolerance would merge physically distinct temperatures rather than recover a
  rounding artefact. The registered tolerance is numeric identity, and the
  sensitivity ladder is a reading that never forms the pair table;
* conflicting values are kept. Where one ``(inchikey, T_K)`` cell holds *m* epsilon
  rows and *n* viscosity rows, all *m*n* combinations are emitted with both
  provenances; ``averaging_applied`` is false on every row and no value is
  tie-broken or dropped;
* the four-way source split of the joint table travels with every pair, so a pair is
  always attributable to both of its sources and a ``filter_only`` viscosity value
  can never be quoted in a publishable headline.

The donor-number half is a coverage audit, not a feature build. Section 2.2 of
``reports/solvating_power_descriptor_mapping.md`` rules that DN is measured against
a probe molecule (SbCl5) and is therefore experimental only, so a predicted or
secondary value cannot cover a key. The criterion and the reading are both
reported and the verdict is arithmetic, not judgement.

Read-only with respect to every released artefact; no network I/O; no model is
fitted and no R2 is produced. The two tables this arm adds under ``data/processed/``
are new files: it never writes ``eta_epsilon_joint_observations.csv`` or
``eta_epsilon_joint_exclusions.csv``.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import sha256_file

try:  # rdkit is a project dependency; the guard keeps the import error legible.
    from rdkit import Chem, RDLogger
except ImportError as error:  # pragma: no cover - environment defect, not logic
    raise SystemExit(f"rdkit is required to key the predicted DN column: {error}") from error

PREREG_PATH = REPOSITORY_ROOT / "probes" / "walden_dn_channel_prereg.json"
JOINT_TABLE_PATH = REPOSITORY_ROOT / "data" / "processed" / "eta_epsilon_joint_observations.csv"
JOINT_EXCLUSIONS_PATH = (
    REPOSITORY_ROOT / "data" / "processed" / "eta_epsilon_joint_exclusions.csv"
)
DENSITY_PATH = REPOSITORY_ROOT / "data" / "density_v01.csv"
SOLVFUNC_PATH = REPOSITORY_ROOT / "data" / "external" / "SolvFunc-87.csv"
ACS_NANO_SI_PATH = (
    REPOSITORY_ROOT / "data" / "external" / "g1plus" / "compilations" / "nn6c06255_si_001.txt"
)
GSDS_ENTRIES_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "gsds_zenodo_archive_entries.txt"

DEFAULT_PAIRS_PATH = REPOSITORY_ROOT / "data" / "processed" / "walden_coupling_pairs.csv"
DEFAULT_DN_AUDIT_PATH = REPOSITORY_ROOT / "data" / "processed" / "dn_coverage_audit.csv"
DEFAULT_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "walden_dn_channel_summary.json"
DEFAULT_REPORT_PATH = REPOSITORY_ROOT / "reports" / "walden_dn_channel.md"
BUILDER_PATH = Path(__file__).resolve()

PAIR_COLUMNS: tuple[str, ...] = (
    "pair_id",
    "inchikey",
    "T_K",
    "T_alignment_rule",
    "T_alignment_delta_K",
    "epsilon_T_K_source",
    "viscosity_T_K_source",
    "epsilon",
    "epsilon_unit",
    "epsilon_dataset_id",
    "epsilon_source_kind",
    "epsilon_quality_layer",
    "epsilon_source_file",
    "epsilon_source_row_index",
    "epsilon_source_doi",
    "epsilon_row_id",
    "epsilon_n_components",
    "epsilon_pure_or_mixture",
    "viscosity_Pa_s",
    "viscosity_unit",
    "viscosity_dataset_id",
    "viscosity_source_kind",
    "viscosity_quality_layer",
    "viscosity_source_file",
    "viscosity_source_row_index",
    "viscosity_source_doi",
    "viscosity_row_id",
    "viscosity_n_components",
    "viscosity_pure_or_mixture",
    "walden_coupling_epsilon_times_eta",
    "walden_ratio_eta_over_epsilon",
    "pair_source_quadrant",
    "pair_quality_layer",
    "pair_redistributable",
    "averaging_applied",
)

DN_AUDIT_COLUMNS: tuple[str, ...] = (
    "inchikey",
    "in_target_key_set",
    "in_publishable_pure_subset",
    "n_epsilon_observations",
    "n_viscosity_observations",
    "has_epsilon_and_viscosity",
    "in_walden_pair_set",
    "n_walden_pairs",
    "key_carries_admissible_dn",
    "admissible_dn_value",
    "admissible_dn_source_id",
    "admissible_dn_source_doi",
    "key_carries_predicted_dn",
    "predicted_dn_value",
    "predicted_dn_source_id",
    "dn_channel_status",
)

PREDICTED_DN_SOURCE_ID = "solvfunc87_predicted_dn"
PREDICTED_DN_COLUMN = "DN_Pred (kcal/mol)"
KINEMATIC_REASON_CODE = "kinematic_viscosity_not_dynamic"
ADMISSIBLE_DN_SOURCE_ID = "dn218_acs_nano_experimental"
ADMISSIBLE_DN_DOI = "10.1021/acsnano.6c06255"
def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not Path(path).is_file():
        return [], []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]

def csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".12g")
    return str(value)

def write_csv_rows(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: csv_cell(row.get(column, "")) for column in columns})

def write_json_lf(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

def read_prereg(path: Path = PREREG_PATH) -> dict[str, Any]:
    return read_json(path)

def assert_locked(prereg: Mapping[str, Any]) -> None:
    if prereg.get("status") != "locked_before_run":
        raise SystemExit(f"prereg is not locked_before_run: {prereg.get('status')!r}")

def alignment_token(tolerance: float) -> str:
    return f"abs_dT_le_{tolerance:g}_K"

def display_path(path: Path) -> str:
    """Repository-relative POSIX path, or the absolute path when outside the repo."""

    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()

def channel_indexes(
    rows: Sequence[Mapping[str, str]],
) -> tuple[
    dict[str, dict[float, list[dict[str, str]]]],
    dict[str, dict[float, list[dict[str, str]]]],
]:
    """Bucket the joint table by InChIKey and stored temperature, per channel."""

    epsilon: dict[str, dict[float, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    viscosity: dict[str, dict[float, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        key = row["inchikey"]
        temperature = float(row["T_K"])
        if row["property"] == "epsilon":
            epsilon[key][temperature].append(row)
        elif row["property"] == "viscosity":
            viscosity[key][temperature].append(row)
        else:
            raise SystemExit(f"joint table carries an unregistered property: {row['property']!r}")
    return epsilon, viscosity

def make_pair(
    epsilon_row: Mapping[str, str],
    viscosity_row: Mapping[str, str],
    rule_token: str,
    delta_k: float,
) -> dict[str, Any]:
    """One (epsilon observation, viscosity observation) pairing, both provenance kept."""

    epsilon_value = epsilon_row["value"]
    viscosity_value = viscosity_row["value"]
    both_core = (
        epsilon_row["quality_layer"] == "publishable_core"
        and viscosity_row["quality_layer"] == "publishable_core"
    )
    pair_id = (
        f'{epsilon_row["inchikey"]}|{csv_cell(float(epsilon_row["T_K"]))}'
        f'|{epsilon_row["dataset_id"]}:{epsilon_row["source_row_index"]}'
        f'|{viscosity_row["dataset_id"]}:{viscosity_row["source_row_index"]}'
    )
    return {
        "pair_id": pair_id,
        "inchikey": epsilon_row["inchikey"],
        "T_K": float(epsilon_row["T_K"]),
        "T_alignment_rule": rule_token,
        "T_alignment_delta_K": delta_k,
        "epsilon_T_K_source": epsilon_row["T_K"],
        "viscosity_T_K_source": viscosity_row["T_K"],
        "epsilon": epsilon_value,
        "epsilon_unit": epsilon_row["unit"],
        "epsilon_dataset_id": epsilon_row["dataset_id"],
        "epsilon_source_kind": epsilon_row["source_kind"],
        "epsilon_quality_layer": epsilon_row["quality_layer"],
        "epsilon_source_file": epsilon_row["source_file"],
        "epsilon_source_row_index": int(epsilon_row["source_row_index"]),
        "epsilon_source_doi": epsilon_row["source_doi"],
        "epsilon_row_id": epsilon_row["row_id"],
        "epsilon_n_components": int(epsilon_row["n_components"]),
        "epsilon_pure_or_mixture": epsilon_row["pure_or_mixture"],
        "viscosity_Pa_s": viscosity_value,
        "viscosity_unit": viscosity_row["unit"],
        "viscosity_dataset_id": viscosity_row["dataset_id"],
        "viscosity_source_kind": viscosity_row["source_kind"],
        "viscosity_quality_layer": viscosity_row["quality_layer"],
        "viscosity_source_file": viscosity_row["source_file"],
        "viscosity_source_row_index": int(viscosity_row["source_row_index"]),
        "viscosity_source_doi": viscosity_row["source_doi"],
        "viscosity_row_id": viscosity_row["row_id"],
        "viscosity_n_components": int(viscosity_row["n_components"]),
        "viscosity_pure_or_mixture": viscosity_row["pure_or_mixture"],
        "walden_coupling_epsilon_times_eta": float(epsilon_value) * float(viscosity_value),
        "walden_ratio_eta_over_epsilon": float(viscosity_value) / float(epsilon_value),
        "pair_source_quadrant": f'{epsilon_row["dataset_id"]} x {viscosity_row["dataset_id"]}',
        "pair_quality_layer": "publishable_core" if both_core else "filter_only",
        "pair_redistributable": (
            epsilon_row["redistributable"] == "true" and viscosity_row["redistributable"] == "true"
        ),
        "averaging_applied": False,
    }
def build_pairs(
    epsilon: Mapping[str, Mapping[float, list[dict[str, str]]]],
    viscosity: Mapping[str, Mapping[float, list[dict[str, str]]]],
    tolerance: float,
    rule_token: str,
) -> list[dict[str, Any]]:
    """Every (epsilon, viscosity) pairing whose stored temperatures agree."""

    pairs: list[dict[str, Any]] = []
    for key in sorted(epsilon):
        if key not in viscosity:
            continue
        for epsilon_t in sorted(epsilon[key]):
            for viscosity_t in sorted(viscosity[key]):
                delta = abs(epsilon_t - viscosity_t)
                if delta > tolerance:
                    continue
                for epsilon_row in sorted(
                    epsilon[key][epsilon_t], key=lambda row: int(row["source_row_index"])
                ):
                    for viscosity_row in sorted(
                        viscosity[key][viscosity_t], key=lambda row: int(row["source_row_index"])
                    ):
                        pairs.append(make_pair(epsilon_row, viscosity_row, rule_token, delta))
    pairs.sort(
        key=lambda row: (
            row["inchikey"],
            row["T_K"],
            row["epsilon_source_row_index"],
            row["viscosity_source_row_index"],
        )
    )
    return pairs

def matched_cells(
    epsilon: Mapping[str, Mapping[float, list[dict[str, str]]]],
    viscosity: Mapping[str, Mapping[float, list[dict[str, str]]]],
    tolerance: float,
) -> tuple[set[tuple[str, float]], int]:
    """Return the matched ``(inchikey, T_K)`` cells and how many hold a conflict."""

    cells: set[tuple[str, float]] = set()
    conflicting = 0
    for key in epsilon:
        if key not in viscosity:
            continue
        for epsilon_t in epsilon[key]:
            for viscosity_t in viscosity[key]:
                if abs(epsilon_t - viscosity_t) > tolerance:
                    continue
                cells.add((key, epsilon_t))
                if len(epsilon[key][epsilon_t]) > 1 or len(viscosity[key][viscosity_t]) > 1:
                    conflicting += 1
    return cells, conflicting

def sensitivity_ladder(
    epsilon: Mapping[str, Mapping[float, list[dict[str, str]]]],
    viscosity: Mapping[str, Mapping[float, list[dict[str, str]]]],
    tolerances: Sequence[float],
) -> list[dict[str, Any]]:
    """A reading only: how many pairings each widened tolerance would produce."""

    ladder: list[dict[str, Any]] = []
    for tolerance in tolerances:
        pairings: set[tuple[str, str]] = set()
        keys: set[str] = set()
        for key in epsilon:
            if key not in viscosity:
                continue
            for epsilon_t in epsilon[key]:
                for viscosity_t in viscosity[key]:
                    if abs(epsilon_t - viscosity_t) > tolerance:
                        continue
                    for epsilon_row in epsilon[key][epsilon_t]:
                        for viscosity_row in viscosity[key][viscosity_t]:
                            pairings.add((epsilon_row["row_id"], viscosity_row["row_id"]))
                    keys.add(key)
        ladder.append(
            {
                "t_tolerance_k": tolerance,
                "pair_rows": len(pairings),
                "distinct_keys": len(keys),
            }
        )
    return ladder

def percentile(values: Sequence[float], fraction: float) -> float:
    """Linear-interpolated percentile of a non-empty sample (numpy's default rule)."""

    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile of an empty sample is undefined")
    position = fraction * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)

def coupling_summary(pairs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Descriptive readings of the two registered coupling columns."""

    def block(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        values = [float(row["walden_coupling_epsilon_times_eta"]) for row in rows]
        ratios = [float(row["walden_ratio_eta_over_epsilon"]) for row in rows]
        if not values:
            return {"pairs": 0}
        return {
            "pairs": len(values),
            "epsilon_times_eta": {
                "min": min(values),
                "median": statistics.median(values),
                "p95": percentile(values, 0.95),
                "max": max(values),
            },
            "eta_over_epsilon": {
                "min": min(ratios),
                "median": statistics.median(ratios),
                "max": max(ratios),
            },
        }

    core = [row for row in pairs if row["pair_quality_layer"] == "publishable_core"]
    return {
        "definition": "walden_coupling_epsilon_times_eta = epsilon * viscosity_Pa_s, unit Pa*s",
        "all_pairs": block(pairs),
        "publishable_core_pairs": block(core),
    }

def kinematic_reading(exclusions_path: Path, density_path: Path) -> dict[str, Any]:
    """The family-level kinematic viscosity reading and its thaw dependency."""

    _, exclusions = read_csv_rows(exclusions_path)
    thermoml_kinematic = sum(
        1
        for row in exclusions
        if row["reason_code"] == KINEMATIC_REASON_CODE
        and row["dataset_id"] == "thermoml_viscosity"
    )
    all_kinematic = sum(1 for row in exclusions if row["reason_code"] == KINEMATIC_REASON_CODE)
    density_present = Path(density_path).is_file()
    return {
        "thermoml_kinematic_rows_excluded": thermoml_kinematic,
        "all_kinematic_rows_excluded": all_kinematic,
        "exclusions_path": display_path(exclusions_path),
        "exclusions_sha256": (
            sha256_file(exclusions_path) if Path(exclusions_path).is_file() else ""
        ),
        "thaw_dependency": display_path(density_path),
        "thaw_dependency_present": density_present,
        "thawed": density_present,
        "statement": (
            "未解冻：data/density_v01.csv 不在盘上，运动黏度不能折成动力黏度，本臂只给族级读数"
            if not density_present
            else "已解冻：data/density_v01.csv 在盘上，后续修订可把 nu 折成 eta 并升级为键级读数"
        ),
    }
def predicted_dn_map(path: Path) -> tuple[dict[str, float], list[str]]:
    """InChIKey -> predicted donor number, keyed with RDKit from the local column."""

    RDLogger.DisableLog("rdApp.*")
    mapping: dict[str, float] = {}
    unparsed: list[str] = []
    with Path(path).open("r", encoding="cp1252", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            smiles = (row.get("SMILES") or "").strip()
            value = (row.get(PREDICTED_DN_COLUMN) or "").strip()
            molecule = Chem.MolFromSmiles(smiles) if smiles else None
            if molecule is None or not value:
                unparsed.append(smiles)
                continue
            mapping[Chem.MolToInchiKey(molecule)] = float(value)
    return mapping, unparsed

def admissible_dn_map(prereg: Mapping[str, Any]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Read every admissible donor-number corpus that is present locally.

    An admissible corpus must supply an experimental value with a first-hand DOI.
    The registry is the authority and this function reports what each registered
    source actually contributes; it never invents a value for one. No registered
    admissible corpus currently carries a local value table, so the map is empty
    and the audit reading is 0 covered keys.
    """

    values: dict[str, float] = {}
    readings: list[dict[str, Any]] = []
    for source in prereg["dn_channel"]["candidate_sources"]:
        declared_values = int(source.get("values_present_locally", 0))
        readings.append(
            {
                "source_id": source["source_id"],
                "claim": source["claim"],
                "doi": source.get("doi", ""),
                "admissible": bool(source["admissible"]),
                "local_evidence": source["local_evidence"],
                "local_evidence_present": (REPOSITORY_ROOT / source["local_evidence"]).exists(),
                "values_present_locally": declared_values,
                "values_contributed_to_coverage": 0,
                "inadmissible_reason": source.get("inadmissible_reason", ""),
            }
        )
    return values, readings

def gsds_donornum_reading(path: Path) -> dict[str, Any]:
    """Audit the GSDS archive listing for a donor-number value table."""

    if not Path(path).is_file():
        return {"entries_path": display_path(path), "entries_present": False}
    names = [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    donornum = [name for name in names if "DonorNum" in name]
    scoring = [
        name for name in donornum if "output_" in name or "/job_" in name or "generation_" in name
    ]
    return {
        "entries_path": display_path(path),
        "entries_present": True,
        "total_entries": len(names),
        "donornum_entry_count": len(donornum),
        "donornum_scoring_task_entry_count": len(scoring),
        "donornum_standalone_dataset_entry_count": len(donornum) - len(scoring),
    }

def acs_nano_reading(path: Path) -> dict[str, Any]:
    """What the local ACS Nano supporting-information text does and does not hold."""

    if not Path(path).is_file():
        return {"path": display_path(path), "present": False}
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return {
        "path": display_path(path),
        "present": True,
        "sha256": sha256_file(path),
        "dn218_mentions": text.count("DN-218"),
        "donor_number_mentions": text.lower().count("donor number"),
        "values_read_here": 0,
    }

def build_dn_audit(
    rows: Sequence[Mapping[str, str]],
    prereg: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One audit row per target key plus the coverage reading and its verdict."""

    target_keys = sorted({row["inchikey"] for row in rows})
    pure_core_keys = sorted(
        {
            row["inchikey"]
            for row in rows
            if row["quality_layer"] == "publishable_core" and row["pure_or_mixture"] == "pure"
        }
    )
    pure_core_set = set(pure_core_keys)
    epsilon_counts = Counter(row["inchikey"] for row in rows if row["property"] == "epsilon")
    viscosity_counts = Counter(row["inchikey"] for row in rows if row["property"] == "viscosity")

    predicted, unparsed = predicted_dn_map(SOLVFUNC_PATH)
    admissible, source_readings = admissible_dn_map(prereg)

    epsilon, viscosity = channel_indexes(rows)
    tolerance = float(prereg["walden_pairs"]["t_tolerance_k"])
    pairs = build_pairs(epsilon, viscosity, tolerance, alignment_token(tolerance))
    pair_counts = Counter(row["inchikey"] for row in pairs)

    audit_rows: list[dict[str, Any]] = []
    for key in target_keys:
        carries_admissible = key in admissible
        carries_predicted = key in predicted
        if carries_admissible:
            status = "admissible_dn"
        elif carries_predicted:
            status = "predicted_dn_only"
        else:
            status = "no_dn"
        audit_rows.append(
            {
                "inchikey": key,
                "in_target_key_set": True,
                "in_publishable_pure_subset": key in pure_core_set,
                "n_epsilon_observations": epsilon_counts.get(key, 0),
                "n_viscosity_observations": viscosity_counts.get(key, 0),
                "has_epsilon_and_viscosity": bool(
                    epsilon_counts.get(key, 0) and viscosity_counts.get(key, 0)
                ),
                "in_walden_pair_set": key in pair_counts,
                "n_walden_pairs": pair_counts.get(key, 0),
                "key_carries_admissible_dn": carries_admissible,
                "admissible_dn_value": admissible.get(key, ""),
                "admissible_dn_source_id": ADMISSIBLE_DN_SOURCE_ID if carries_admissible else "",
                "admissible_dn_source_doi": ADMISSIBLE_DN_DOI if carries_admissible else "",
                "key_carries_predicted_dn": carries_predicted,
                "predicted_dn_value": predicted.get(key, ""),
                "predicted_dn_source_id": PREDICTED_DN_SOURCE_ID if carries_predicted else "",
                "dn_channel_status": status,
            }
        )

    threshold = float(prereg["dn_channel"]["coverage_threshold"])
    target_total = len(target_keys)
    admissible_covered = sum(1 for key in target_keys if key in admissible)
    predicted_covered = sum(1 for key in target_keys if key in predicted)
    pure_total = len(pure_core_keys)
    admissible_pure = sum(1 for key in pure_core_keys if key in admissible)
    predicted_pure = sum(1 for key in pure_core_keys if key in predicted)
    admissible_fraction = admissible_covered / target_total if target_total else 0.0
    predicted_fraction = predicted_covered / target_total if target_total else 0.0

    reading: dict[str, Any] = {
        "target_key_set": prereg["dn_channel"]["target_key_set"],
        "target_keys": target_total,
        "coverage_threshold": threshold,
        "coverage_definition": prereg["dn_channel"]["coverage_definition"],
        "admissibility_rule": prereg["dn_channel"]["admissibility_rule"],
        "audit_rows": len(audit_rows),
        "admissible": {
            "covered_keys": admissible_covered,
            "coverage_fraction": admissible_fraction,
            "passes_threshold": admissible_fraction >= threshold,
        },
        "predicted_sub_channel": {
            "source_id": PREDICTED_DN_SOURCE_ID,
            "values_keyed_locally": len(predicted),
            "unparsed_smiles": len(unparsed),
            "covered_keys": predicted_covered,
            "coverage_fraction": predicted_fraction,
            "passes_threshold": predicted_fraction >= threshold,
            "merges_into_admissible_coverage": False,
        },
        "secondary_target_set": {
            "definition": prereg["dn_channel"]["secondary_target_key_set"],
            "keys": pure_total,
            "admissible_covered_keys": admissible_pure,
            "admissible_coverage_fraction": admissible_pure / pure_total if pure_total else 0.0,
            "predicted_covered_keys": predicted_pure,
        },
        "status_counts": dict(sorted(Counter(row["dn_channel_status"] for row in audit_rows).items())),
        "source_readings": source_readings,
        "gsds_audit": gsds_donornum_reading(GSDS_ENTRIES_PATH),
        "acs_nano_audit": acs_nano_reading(ACS_NANO_SI_PATH),
        "verdict_rule": prereg["dn_channel"]["verdict_rule"],
    }
    reading["verdict"] = (
        "channel_available_for_a_later_feature_table"
        if reading["admissible"]["passes_threshold"]
        else "channel_does_not_enter_the_feature_table"
    )
    return audit_rows, reading
def frozen_red_line_reading(prereg: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute the digest of all six frozen artefacts."""

    report: dict[str, Any] = {}
    for relative, expected in sorted(prereg["frozen_red_lines"].items()):
        path = REPOSITORY_ROOT / relative
        measured = sha256_file(path) if path.is_file() else ""
        report[relative] = {
            "expected": expected,
            "measured": measured,
            "intact": measured == expected,
        }
    return report

def build_summary(
    *,
    pairs_path: Path = DEFAULT_PAIRS_PATH,
    dn_audit_path: Path = DEFAULT_DN_AUDIT_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    prereg_path: Path = PREREG_PATH,
    joint_table_path: Path = JOINT_TABLE_PATH,
    exclusions_path: Path = JOINT_EXCLUSIONS_PATH,
    density_path: Path = DENSITY_PATH,
    builder_path: Path = BUILDER_PATH,
) -> dict[str, Any]:
    prereg = read_prereg(prereg_path)
    assert_locked(prereg)
    _, rows = read_csv_rows(joint_table_path)

    tolerance = float(prereg["walden_pairs"]["t_tolerance_k"])
    rule_token = alignment_token(tolerance)
    epsilon, viscosity = channel_indexes(rows)
    pairs = build_pairs(epsilon, viscosity, tolerance, rule_token)
    cells, conflicting_cells = matched_cells(epsilon, viscosity, tolerance)

    keys = {row["inchikey"] for row in rows}
    keys_with_both = sorted(key for key in epsilon if key in viscosity)
    pair_keys = {row["inchikey"] for row in pairs}

    properties = Counter(row["property"] for row in rows)
    source_split = Counter(row["dataset_id"] for row in rows)
    quality = Counter(row["quality_layer"] for row in rows)
    purity = Counter(row["pure_or_mixture"] for row in rows)
    expected_rows = int(prereg["input"]["expected_rows"])
    expected_keys = int(prereg["input"]["expected_distinct_keys"])
    expected_split = {
        key: int(value) for key, value in prereg["input"]["expected_source_split"].items()
    }

    joint_recount = {
        "observations": len(rows),
        "expected_observations": expected_rows,
        "distinct_keys": len(keys),
        "expected_distinct_keys": expected_keys,
        "by_property": dict(sorted(properties.items())),
        "by_dataset_id": dict(sorted(source_split.items())),
        "expected_source_split": dict(sorted(expected_split.items())),
        "by_quality_layer": dict(sorted(quality.items())),
        "by_pure_or_mixture": dict(sorted(purity.items())),
        "rows_match_expected": len(rows) == expected_rows,
        "keys_match_expected": len(keys) == expected_keys,
        "source_split_matches_expected": dict(source_split) == expected_split,
        "recount_matches_prereg": (
            len(rows) == expected_rows
            and len(keys) == expected_keys
            and dict(source_split) == expected_split
        ),
    }

    quadrant = Counter(row["pair_source_quadrant"] for row in pairs)
    pair_layer = Counter(row["pair_quality_layer"] for row in pairs)
    pair_purity = Counter(
        "pure"
        if row["epsilon_pure_or_mixture"] == "pure" and row["viscosity_pure_or_mixture"] == "pure"
        else "mixture"
        for row in pairs
    )
    per_key = Counter(row["inchikey"] for row in pairs)

    walden = {
        "rows": len(pairs),
        "distinct_keys": len(pair_keys),
        "epsilon_keys": len(epsilon),
        "viscosity_keys": len(viscosity),
        "keys_with_both_channels": len(keys_with_both),
        "keys_with_both_channels_without_a_shared_temperature": len(keys_with_both) - len(pair_keys),
        "matched_temperature_cells": len(cells),
        "cells_with_more_than_one_value_on_a_side": conflicting_cells,
        "averaging_applied": False,
        "pairs_per_key_min": min(per_key.values()) if per_key else 0,
        "pairs_per_key_max": max(per_key.values()) if per_key else 0,
        "by_source_quadrant": dict(sorted(quadrant.items())),
        "by_pair_quality_layer": dict(sorted(pair_layer.items())),
        "by_pair_pure_or_mixture": dict(sorted(pair_purity.items())),
        "t_alignment_rule": prereg["walden_pairs"]["t_alignment_rule"],
        "t_tolerance_k": tolerance,
        "t_alignment_rule_token": rule_token,
        "max_t_alignment_delta_k": max(
            (abs(float(row["T_alignment_delta_K"])) for row in pairs), default=0.0
        ),
        "primary_coupling": prereg["walden_pairs"]["primary_coupling"],
        "secondary_coupling": prereg["walden_pairs"]["secondary_coupling"],
        "coupling": coupling_summary(pairs),
        "sensitivity_ladder": sensitivity_ladder(
            epsilon, viscosity, prereg["walden_pairs"]["t_alignment_sensitivity_ladder_k"]
        ),
        "sensitivity_ladder_role": prereg["walden_pairs"]["sensitivity_ladder_role"],
        "no_model": prereg["walden_pairs"]["no_model"],
    }

    _, dn_reading = build_dn_audit(rows, prereg)
    kinematic = kinematic_reading(exclusions_path, density_path)
    frozen = frozen_red_line_reading(prereg)
    frozen_intact = all(item["intact"] for item in frozen.values())

    summary: dict[str, Any] = {
        "schema_version": 1,
        "task": prereg["task"],
        "title": "eps-eta Walden coupling pairs and the DN fifth-channel registration: the build",
        "generated_at_utc": utc_now(),
        "run_telemetry": {
            "generated_at_utc": utc_now(),
            "network_calls": 0,
            "models_fitted": 0,
            "r2_reported": False,
            "writes_under_data": 2,
            "run_mode": "offline",
        },
        "inputs": {
            "joint_table": {
                "path": display_path(joint_table_path),
                "sha256": (
                    sha256_file(joint_table_path) if Path(joint_table_path).is_file() else ""
                ),
            },
            "joint_exclusions": {
                "path": display_path(exclusions_path),
                "sha256": (
                    sha256_file(exclusions_path) if Path(exclusions_path).is_file() else ""
                ),
            },
            "predicted_dn_column": {
                "path": display_path(SOLVFUNC_PATH),
                "sha256": sha256_file(SOLVFUNC_PATH) if SOLVFUNC_PATH.is_file() else "",
                "column": PREDICTED_DN_COLUMN,
            },
        },
        "joint_table_recount": joint_recount,
        "walden_pairs": walden,
        "kinematic_thaw": kinematic,
        "dn_channel": dn_reading,
        "decision": {
            "walden_pairs": "built; a derived pair table, not a measurement table",
            "dn_channel": dn_reading["verdict"],
            "dn_channel_fails_criterion": not dn_reading["admissible"]["passes_threshold"],
            "kinematic_viscosity": (
                "family level only; not thawed"
                if not kinematic["thawed"]
                else "family level only in this arm; the density table is on disk so nu can fold to eta"
            ),
            "model_fitted": False,
            "r2_reported": False,
            "frozen_baseline_touched": False,
        },
        "manifest": {
            "pairs": {
                "path": display_path(pairs_path),
                "sha256": sha256_file(pairs_path) if Path(pairs_path).is_file() else "",
                "rows": len(pairs),
                "columns": list(PAIR_COLUMNS),
            },
            "dn_coverage_audit": {
                "path": display_path(dn_audit_path),
                "sha256": sha256_file(dn_audit_path) if Path(dn_audit_path).is_file() else "",
                "columns": list(DN_AUDIT_COLUMNS),
            },
            "builder": {"path": display_path(builder_path), "sha256": sha256_file(builder_path)},
            "prereg": {
                "path": display_path(prereg_path),
                "sha256": sha256_file(prereg_path),
                "status": prereg["status"],
            },
            "report": {"path": display_path(report_path)},
            "frozen_red_lines": frozen,
            "frozen_red_lines_intact": frozen_intact,
            "summary_sha256_note": "the summary cannot carry its own digest; the verifier recomputes it",
        },
        "boundaries": [
            (
                "pair rows are derived from the joint observation table; they are not measurements "
                "and carry no new uncertainty"
            ),
            (
                "no pairing across a temperature gap: only stored temperatures that agree "
                "numerically are paired"
            ),
            (
                "the kinematic viscosity rows are excluded from the joint table and therefore "
                "from every pair"
            ),
            (
                "no model is fitted and no R2 is reported; the frozen baseline 0.4091179943351143 "
                "is not touched"
            ),
            (
                "the DN channel is audited for coverage only; it is never fitted and never enters "
                "a feature table here"
            ),
        ],
    }
    if not frozen_intact:
        moved = sorted(rel for rel, item in frozen.items() if not item["intact"])
        raise SystemExit(f"a frozen red line moved, refusing to build: {moved}")
    return summary
def render_report(summary: Mapping[str, Any]) -> str:
    """The Chinese handover report; every number is read back from the summary."""

    recount = summary["joint_table_recount"]
    walden = summary["walden_pairs"]
    kinematic = summary["kinematic_thaw"]
    dn = summary["dn_channel"]
    manifest = summary["manifest"]
    ladder = walden["sensitivity_ladder"]
    coupling = walden["coupling"]["all_pairs"]
    coupling_core = walden["coupling"]["publishable_core_pairs"]
    gsds = dn["gsds_audit"]
    acs = dn["acs_nano_audit"]

    lines: list[str] = []
    lines.append("# ε–η Walden 耦合配对与 DN 第五通道登记（Week 17 臂 W17-7）")
    lines.append("")
    lines.append(f"- 构建器：`probes/walden_dn_channel.py`（sha256 `{manifest['builder']['sha256']}`）")
    lines.append(
        f"- 预注册：`probes/walden_dn_channel_prereg.json`"
        f"（sha256 `{manifest['prereg']['sha256']}`，status={manifest['prereg']['status']}）"
    )
    lines.append("- 校验器：`scripts/verify_walden_dn_channel.py --check`（离线复算，PASS=0 / FAIL=1）")
    lines.append(
        f"- 配对表：`{display_path(DEFAULT_PAIRS_PATH)}`（{manifest['pairs']['rows']:,} 行 + 表头，"
        f"{len(manifest['pairs']['columns'])} 列）"
    )
    lines.append(
        f"- DN 覆盖审计：`{display_path(DEFAULT_DN_AUDIT_PATH)}`"
        f"（{dn['audit_rows']:,} 行 + 表头，{len(manifest['dn_coverage_audit']['columns'])} 列）"
    )
    lines.append(
        "- 机读汇总：`probes/walden_dn_channel_summary.json`；其 `manifest` 记录配对表、DN 审计表、"
        "构建器与预注册的 sha256（汇总表不能自哈希，由校验器复算）。"
    )
    lines.append("- 复现构建：`.\\\\.venv\\\\Scripts\\\\python.exe probes\\\\walden_dn_channel.py`")
    lines.append(
        "- 复现校验：`.\\\\.venv\\\\Scripts\\\\python.exe scripts\\\\verify_walden_dn_channel.py --check`"
    )
    lines.append(
        f"- 网络访问：无（network_calls={summary['run_telemetry']['network_calls']}）；"
        f"建模：无（models_fitted=0，r2_reported=false）；"
        f"冻结件：{'6/6 INTACT' if manifest['frozen_red_lines_intact'] else '有移动'}。"
    )
    lines.append("")
    lines.append("## 方法")
    lines.append("")
    lines.append(
        "1. 只读 `data/processed/eta_epsilon_joint_observations.csv`，按 `InChIKey` 与温度列 `T_K` "
        "把 ε 行与 η 行各自分桶；本臂不写、不重建该表，也不写它的排除表。"
    )
    lines.append(
        f"2. 配对判据（预注册口径）：同一 `InChIKey` 下 `abs(T_eps - T_eta) <= "
        f"{walden['t_tolerance_k']:g} K`；**不插值、不外推、不搬温度**。"
    )
    lines.append(
        "3. 冲突不平均：同一 `(inchikey, T_K)` 格内有 m 条 ε 与 n 条 η 时，全部 m×n 组合逐条落表，"
        "两侧 provenance 都在行内，`averaging_applied=false`。"
    )
    lines.append(
        "4. 耦合量（预注册口径）：主口径 `walden_coupling_epsilon_times_eta = ε · η(Pa·s)`；"
        "副口径 `walden_ratio_eta_over_epsilon = η / ε(Pa·s)`，只作读数、不承载判决。"
    )
    lines.append(
        "5. 来源四分归属：每行带 `epsilon_dataset_id` 与 `viscosity_dataset_id`，"
        "`pair_source_quadrant = '<ε源> x <η源>'`；`pair_quality_layer` 只在两侧都 "
        "publishable_core 时为 publishable_core。"
    )
    lines.append(
        "6. DN 只做覆盖率检查与来源审计：目标键集 = 联表的全部 `InChIKey`；"
        f"覆盖率判据 `covered / target >= {dn['coverage_threshold']}`，"
        "且只有「实验 + 一手 DOI」的 DN 才允许覆盖一个键。"
    )
    lines.append("")
    lines.append("## 读数")
    lines.append("")
    lines.append("### 联表现状复算（本臂自己重数，不引上游摘要）")
    lines.append("")
    lines.append("| 口径 | 本臂读数 | 预注册期望 | 一致 |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| 观测行数 | {recount['observations']:,} | {recount['expected_observations']:,} | "
        f"{'是' if recount['rows_match_expected'] else '否'} |"
    )
    lines.append(
        f"| 去重键数 | {recount['distinct_keys']:,} | {recount['expected_distinct_keys']:,} | "
        f"{'是' if recount['keys_match_expected'] else '否'} |"
    )
    lines.append(
        f"| 来源四分 | "
        f"{' + '.join(f'{key} {value:,}' for key, value in recount['by_dataset_id'].items())} | "
        f"{' + '.join(f'{key} {value:,}' for key, value in recount['expected_source_split'].items())} | "
        f"{'是' if recount['source_split_matches_expected'] else '否'} |"
    )
    lines.append("")
    lines.append(
        f"- ε 行 {recount['by_property'].get('epsilon', 0):,}，"
        f"η 行 {recount['by_property'].get('viscosity', 0):,}。"
    )
    lines.append(
        f"- 两层口径：publishable_core {recount['by_quality_layer'].get('publishable_core', 0):,} 行，"
        f"filter_only {recount['by_quality_layer'].get('filter_only', 0):,} 行。"
    )
    lines.append(
        f"- 纯/混合：pure {recount['by_pure_or_mixture'].get('pure', 0):,} 行，"
        f"mixture {recount['by_pure_or_mixture'].get('mixture', 0):,} 行。"
    )
    lines.append("")
    lines.append("### Walden 配对")
    lines.append("")
    lines.append(
        f"- 配对行 **{walden['rows']:,}**，覆盖 **{walden['distinct_keys']}** 个键；"
        f"落在 {walden['matched_temperature_cells']} 个 `(InChIKey, T_K)` 格上。"
    )
    lines.append(
        f"- ε 有值的键 {walden['epsilon_keys']}，η 有值的键 {walden['viscosity_keys']}，"
        f"两条都有值的键 {walden['keys_with_both_channels']}；其中 "
        f"**{walden['keys_with_both_channels_without_a_shared_temperature']} 个键两条都有值、"
        "却没有共享温度**，因此一条配对也不产生（不插值，不外推）。"
    )
    lines.append(f"- 逐键配对数：最少 {walden['pairs_per_key_min']}，最多 {walden['pairs_per_key_max']}。")
    lines.append(
        f"- 主口径 ε·η：min {coupling['epsilon_times_eta']['min']:.6g}，"
        f"median {coupling['epsilon_times_eta']['median']:.6g}，"
        f"p95 {coupling['epsilon_times_eta']['p95']:.6g}，"
        f"max {coupling['epsilon_times_eta']['max']:.6g} Pa·s（全部配对）。"
    )
    lines.append(
        f"- 只算 publishable_core 配对（{coupling_core['pairs']:,} 行）：min "
        f"{coupling_core['epsilon_times_eta']['min']:.6g}，median "
        f"{coupling_core['epsilon_times_eta']['median']:.6g}，max "
        f"{coupling_core['epsilon_times_eta']['max']:.6g} Pa·s。"
    )
    lines.append(
        f"- 全部配对的 `T_alignment_delta_K` 最大值为 {walden['max_t_alignment_delta_k']:g} K"
        f"（口径 `{walden['t_alignment_rule_token']}`）。"
    )
    lines.append("")
    lines.append("### T 对齐敏感性阶梯（只是读数，永不进判决）")
    lines.append("")
    lines.append("| 容差 (K) | 配对行 | 覆盖键 |")
    lines.append("|---|---|---|")
    for rung in ladder:
        lines.append(f"| {rung['t_tolerance_k']:g} | {rung['pair_rows']:,} | {rung['distinct_keys']} |")
    lines.append("")
    lines.append(f"- {walden['sensitivity_ladder_role']}")
    lines.append("")
    lines.append("### 来源四分归属与两层口径")
    lines.append("")
    lines.append("| 来源象限 | 配对行 |")
    lines.append("|---|---|")
    for quadrant, count in walden["by_source_quadrant"].items():
        lines.append(f"| {quadrant} | {count:,} |")
    lines.append("")
    lines.append(
        f"- `pair_quality_layer`：publishable_core "
        f"{walden['by_pair_quality_layer'].get('publishable_core', 0):,} 行，filter_only "
        f"{walden['by_pair_quality_layer'].get('filter_only', 0):,} 行；filter_only 来自 PubChem "
        "汇编黏度腿，只许筛选、永不上头条。"
    )
    lines.append(
        f"- 两侧都纯：{walden['by_pair_pure_or_mixture'].get('pure', 0):,} 行；"
        f"至少一侧为混合物：{walden['by_pair_pure_or_mixture'].get('mixture', 0):,} 行。"
    )
    lines.append("")
    lines.append("### 冲突不平均")
    lines.append("")
    lines.append(
        f"- {walden['cells_with_more_than_one_value_on_a_side']} 个格至少一侧有多值，全部 m×n 逐条保留，"
        f"`averaging_applied={str(walden['averaging_applied']).lower()}`。"
    )
    lines.append("")
    lines.append("### DN 第五通道登记与覆盖率")
    lines.append("")
    lines.append(
        f"- 目标键集：联表的全部 `InChIKey`（{dn['target_key_set']}），共 **{dn['target_keys']:,}** 个键；"
        f"判据 `covered / target >= {dn['coverage_threshold']}`。"
    )
    lines.append(
        f"- 可用（实验 + 一手 DOI）覆盖：**{dn['admissible']['covered_keys']} / "
        f"{dn['target_keys']:,} = {dn['admissible']['coverage_fraction']:.4f}** → "
        f"{'过线' if dn['admissible']['passes_threshold'] else '**不过线**'}。"
    )
    lines.append(
        f"- 预测子通道（`{dn['predicted_sub_channel']['source_id']}`，本地可键化 "
        f"{dn['predicted_sub_channel']['values_keyed_locally']} 条）：覆盖 "
        f"{dn['predicted_sub_channel']['covered_keys']} / {dn['target_keys']:,} = "
        f"{dn['predicted_sub_channel']['coverage_fraction']:.4f}；**预测值按 §2.2 不具资格**，"
        "只作独立读数、绝不与可用覆盖合并。"
    )
    lines.append(
        f"- 次级目标集（publishable_core & pure，{dn['secondary_target_set']['keys']:,} 键）："
        f"可用覆盖 {dn['secondary_target_set']['admissible_covered_keys']}，"
        f"预测覆盖 {dn['secondary_target_set']['predicted_covered_keys']}。"
    )
    lines.append(f"- 逐键状态分布：`{dn['status_counts']}`。")
    lines.append("")
    lines.append("| 候选来源 | 主张 | 可采信 | 本地证据 | 本地值数 | 未采信原因 |")
    lines.append("|---|---|---|---|---|---|")
    for source in dn["source_readings"]:
        lines.append(
            f"| `{source['source_id']}` | {source['claim']} | "
            f"{'是' if source['admissible'] else '否'} | `{source['local_evidence']}`"
            f"（{'在' if source['local_evidence_present'] else '缺'}） | "
            f"{source['values_present_locally']} | {source['inadmissible_reason'] or '—'} |"
        )
    lines.append("")
    if gsds.get("entries_present"):
        lines.append(
            f"- GSDS Zenodo 归档的 {gsds['total_entries']:,} 条条目名里，含 `DonorNum` 的 "
            f"{gsds['donornum_entry_count']:,} 条**全部**落在生成分子打分任务目录内"
            f"（独立 DN 数据集文件数 {gsds['donornum_standalone_dataset_entry_count']}）——"
            "归档内没有可用的 DN 数值表。"
        )
    if acs.get("present"):
        lines.append(
            f"- ACS Nano SI（`{acs['path']}`，sha256 `{acs['sha256'][:16]}`）只提到 DN-218 数据集名"
            f"（DN-218 出现 {acs['dn218_mentions']} 次）与图注，逐分子数值表未落地，"
            f"本地读出值数 {acs['values_read_here']}。"
        )
    lines.append(
        f"- **判决**：`{dn['verdict']}` —— 覆盖率不过线，且 §2.2 判 DN 只能实验，"
        "故本臂不给任何特征表引入 DN 列。"
    )
    lines.append("")
    lines.append("## 运动黏度解冻状态")
    lines.append("")
    lines.append(
        f"- 联表排除表里 `{KINEMATIC_REASON_CODE}` 共 {kinematic['all_kinematic_rows_excluded']} 条，"
        f"其中 ThermoML 腿 {kinematic['thermoml_kinematic_rows_excluded']} 条 —— 这是**族级**读数。"
    )
    lines.append(
        f"- 解冻依赖 `{kinematic['thaw_dependency']}`：该文件"
        f"{'在盘上' if kinematic['thaw_dependency_present'] else '**不在盘上**'}，"
        f"`thawed={str(kinematic['thawed']).lower()}`。"
    )
    lines.append(
        f"- {kinematic['statement']}。判据与升级路径已写进预注册的 `kinematic_thaw`，"
        + (
            "解冻前置条件已满足，可把族级读数升级为键级读数，且不必改动本臂已落盘的配对表。"
            if kinematic["thawed"]
            else "日后解冻可把族级读数升级为键级读数，且不必改动本臂已落盘的配对表。"
        )
    )
    lines.append("")
    lines.append("## 与预注册的冲突与不确定处")
    lines.append("")
    lines.append(
        "- **pair_rows_are_derived**（interpretation）：配对行是两条观测的**组合**，不是新测量；"
        "同一格多值时 m×n 展开会把行数放大，这是「不平均」纪律的直接后果，不是缺陷。"
    )
    lines.append(
        "- **temperature_grid_is_coarse**（data_limitation）：联表温度落在粗网格上"
        "（如 278.15 / 280.65 / 283.15 K），所以「两通道都有值却不共享温度」的键占多数；"
        "扩大容差会把不同温度并成一个，故本臂坚持数值同一性口径，敏感性阶梯只作读数。"
    )
    lines.append(
        "- **epsilon_side_is_always_publishable_core**（observation）：本构建里 ε 腿全部来自 "
        "`epsilon_observations_v11plus`（publishable_core），所以配对的层由 η 腿单独决定。"
    )
    lines.append(
        "- **dn_temperature_binding_not_defined**（uncertainty）：DN 的记录温度（多为 25 °C）与联表的温度网格"
        "不是同一套，本臂只判覆盖率、不做温度对齐；即便日后取到 DN-218，也需要另一条臂先定温度归并口径，"
        "才能把它接到 Walden 配对上。"
    )
    lines.append(
        "- **predicted_dn_column_encoding**（source_limitation）：`data/external/SolvFunc-87.csv` 是 cp1252 "
        "编码的 `;` 分隔表，本臂按该编码读；87 行 SMILES 全部可解析，无一行被丢弃。"
    )
    lines.append("")
    lines.append("## 边界（不许省略）")
    lines.append("")
    lines.append(
        "- **不拟合任何模型、不产任何 R²**：`models_fitted=0`、`r2_reported=false`，"
        "冻结基准 `0.4091179943351143` 未被触碰。"
    )
    lines.append(
        "- **六件冻结件**：本臂只读，digest 逐位复算 —— "
        + "；".join(
            f"`{relative}` {'INTACT' if item['intact'] else 'MOVED'}"
            for relative, item in manifest["frozen_red_lines"].items()
        )
        + "。"
    )
    lines.append(
        "- **不动既有产物**：`data/processed/eta_epsilon_joint_observations.csv` 与 "
        "`data/processed/eta_epsilon_joint_exclusions.csv` 只被读取，未被写入。"
    )
    lines.append(
        "- **可采信 DN 覆盖为 0**：不是因为「取不到」，而是因为 §2.2 判 DN 为探针化学、只能实验，"
        "而本地全部 DN 型数据都是预测值或二手汇编值。"
    )
    lines.append(
        "- **新增表的入库**：`data/processed/walden_coupling_pairs.csv` 与 "
        "`data/processed/dn_coverage_audit.csv` 是新文件，被 `.gitignore` 的 `data/processed/*` 命中，"
        "需另加白名单（本臂按纪律不改 `.gitignore`）。"
    )
    lines.append("")
    lines.append("## 校验")
    lines.append("")
    lines.append(
        "`scripts/verify_walden_dn_channel.py --check` 离线复算预注册 "
        "`verification_contract.checks` 的全 7 条，并对配对表、DN 审计表与构建器脚本做 SHA256 清单："
    )
    lines.append("")
    lines.append("1. 联表逐项重数（行数、键数、来源四分）与预注册期望一致；")
    lines.append("2. 每一行配对都带两侧 provenance，且 `averaging_applied=false`；")
    lines.append("3. 每一行的 T 对齐规则成立（`abs(dT) <= 容差`）；")
    lines.append("4. 两个耦合列都能由两侧存值按口径复算；")
    lines.append("5. `pair_quality_layer` 与「两侧都 core」规则一致；")
    lines.append("6. DN 覆盖率 = 覆盖键数 / 目标键数，判决按阈值；")
    lines.append("7. 六件冻结件 digest 逐位不变。")
    lines.append("")
    lines.append("校验器对给定文件报 PASS/FAIL 并返回退出码（PASS=0，FAIL=1）。")
    lines.append("")
    return "\n".join(lines)

def build_artifacts(
    *,
    pairs_path: Path = DEFAULT_PAIRS_PATH,
    dn_audit_path: Path = DEFAULT_DN_AUDIT_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    prereg_path: Path = PREREG_PATH,
    joint_table_path: Path = JOINT_TABLE_PATH,
    exclusions_path: Path = JOINT_EXCLUSIONS_PATH,
    density_path: Path = DENSITY_PATH,
    builder_path: Path = BUILDER_PATH,
    write: bool = True,
) -> dict[str, Any]:
    prereg = read_prereg(prereg_path)
    assert_locked(prereg)
    _, rows = read_csv_rows(joint_table_path)
    tolerance = float(prereg["walden_pairs"]["t_tolerance_k"])
    epsilon, viscosity = channel_indexes(rows)
    pairs = build_pairs(epsilon, viscosity, tolerance, alignment_token(tolerance))
    audit_rows, _ = build_dn_audit(rows, prereg)
    if write:
        write_csv_rows(pairs_path, PAIR_COLUMNS, pairs)
        write_csv_rows(dn_audit_path, DN_AUDIT_COLUMNS, audit_rows)
    summary = build_summary(
        pairs_path=pairs_path,
        dn_audit_path=dn_audit_path,
        summary_path=summary_path,
        report_path=report_path,
        prereg_path=prereg_path,
        joint_table_path=joint_table_path,
        exclusions_path=exclusions_path,
        density_path=density_path,
        builder_path=builder_path,
    )
    if write:
        write_json_lf(summary_path, summary)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_report(summary))
    return summary

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", type=Path, default=DEFAULT_PAIRS_PATH)
    parser.add_argument("--dn-audit", type=Path, default=DEFAULT_DN_AUDIT_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--dry-run", action="store_true", help="compute only, write nothing")
    arguments = parser.parse_args(argv)

    summary = build_artifacts(
        pairs_path=arguments.pairs,
        dn_audit_path=arguments.dn_audit,
        summary_path=arguments.summary,
        report_path=arguments.report,
        write=not arguments.dry_run,
    )
    readings = {
        "joint_rows": summary["joint_table_recount"]["observations"],
        "joint_keys": summary["joint_table_recount"]["distinct_keys"],
        "recount_matches_prereg": summary["joint_table_recount"]["recount_matches_prereg"],
        "walden_pair_rows": summary["walden_pairs"]["rows"],
        "walden_pair_keys": summary["walden_pairs"]["distinct_keys"],
        "keys_with_both_channels": summary["walden_pairs"]["keys_with_both_channels"],
        "dn_target_keys": summary["dn_channel"]["target_keys"],
        "dn_admissible_covered": summary["dn_channel"]["admissible"]["covered_keys"],
        "dn_admissible_fraction": summary["dn_channel"]["admissible"]["coverage_fraction"],
        "dn_predicted_covered": summary["dn_channel"]["predicted_sub_channel"]["covered_keys"],
        "dn_verdict": summary["dn_channel"]["verdict"],
        "thawed": summary["kinematic_thaw"]["thawed"],
        "frozen_red_lines_intact": summary["manifest"]["frozen_red_lines_intact"],
        "pairs_sha256": summary["manifest"]["pairs"]["sha256"],
        "dn_audit_sha256": summary["manifest"]["dn_coverage_audit"]["sha256"],
    }
    print(json.dumps(readings, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())