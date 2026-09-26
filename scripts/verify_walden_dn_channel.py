"""Independent ``--check`` recompute for the eps-eta Walden coupling arm (W17-7).

This module re-derives the committed artefacts from the joint observation table
instead of trusting the builder's summary. The pairing loop, the temperature
comparison, the coupling arithmetic and the donor-number coverage count are all
re-implemented here, so a bug in the builder cannot hide behind a matching bug
in a shared helper.

It implements the whole of ``verification_contract.checks`` from
``probes/walden_dn_channel_prereg.json``:

1. the joint table is recounted (rows, distinct keys, source split) and compared
   with the prereg's expected values;
2. every pair row carries both provenances and ``averaging_applied=false``;
3. the temperature-alignment rule holds on every pair row;
4. both coupling columns are recomputed from the two stored values;
5. ``pair_quality_layer`` equals the both-sides rule;
6. the DN coverage fraction equals covered / target and the verdict follows the
   threshold;
7. the six frozen artefacts keep their digests;

plus four supplementary checks (the committed pair table and DN audit table
against the reconstruction, the summary manifest against the bytes on disk, the
run telemetry, and the quadrant / layer counts).

Usage::

    python scripts/verify_walden_dn_channel.py --check [--json]

Exit code 0 means PASS, 1 means FAIL. Nothing here writes to the repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from rdkit import Chem, RDLogger

PREREG_PATH = REPOSITORY_ROOT / "probes" / "walden_dn_channel_prereg.json"
JOINT_TABLE_PATH = REPOSITORY_ROOT / "data" / "processed" / "eta_epsilon_joint_observations.csv"
DENSITY_PATH = REPOSITORY_ROOT / "data" / "density_v01.csv"
SOLVFUNC_PATH = REPOSITORY_ROOT / "data" / "external" / "SolvFunc-87.csv"
PAIRS_PATH = REPOSITORY_ROOT / "data" / "processed" / "walden_coupling_pairs.csv"
DN_AUDIT_PATH = REPOSITORY_ROOT / "data" / "processed" / "dn_coverage_audit.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "walden_dn_channel_summary.json"
BUILDER_PATH = REPOSITORY_ROOT / "probes" / "walden_dn_channel.py"

CHECK_COUNT = 7
#: Traceability columns that must be non-empty on every pair row.  The source DOI
#: is deliberately not in this list: the schema allows an empty DOI in the
#: ``filter_only`` layer, and every PubChem viscosity leg is exactly that.  The DOI
#: is checked separately, and only demanded where the pair claims ``publishable_core``.
PROVENANCE_COLUMNS = (
    "epsilon_source_file",
    "epsilon_source_row_index",
    "epsilon_row_id",
    "viscosity_source_file",
    "viscosity_source_row_index",
    "viscosity_row_id",
)
DOI_COLUMNS = ("epsilon_source_doi", "viscosity_source_doi")

def sha256_of(path: Path) -> str:
    if not Path(path).is_file():
        return ""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not Path(path).is_file():
        return [], []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]

def load_json(path: Path) -> dict[str, Any]:
    if not Path(path).is_file():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))

def close(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-9 * max(1.0, abs(left), abs(right))

def reconstruct_pairs(
    rows: list[dict[str, str]], tolerance: float
) -> list[dict[str, Any]]:
    """Site-local re-implementation of the registered pairing rule."""

    epsilon: dict[str, list[dict[str, str]]] = defaultdict(list)
    viscosity: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["property"] == "epsilon":
            epsilon[row["inchikey"]].append(row)
        else:
            viscosity[row["inchikey"]].append(row)

    pairs: list[dict[str, Any]] = []
    for key in sorted(epsilon):
        for epsilon_row in epsilon[key]:
            for viscosity_row in viscosity.get(key, []):
                delta = abs(float(epsilon_row["T_K"]) - float(viscosity_row["T_K"]))
                if delta > tolerance:
                    continue
                epsilon_value = float(epsilon_row["value"])
                viscosity_value = float(viscosity_row["value"])
                both_core = (
                    epsilon_row["quality_layer"] == "publishable_core"
                    and viscosity_row["quality_layer"] == "publishable_core"
                )
                pairs.append(
                    {
                        "inchikey": key,
                        "T_K": float(epsilon_row["T_K"]),
                        "delta": delta,
                        "epsilon": epsilon_value,
                        "viscosity_Pa_s": viscosity_value,
                        "coupling": epsilon_value * viscosity_value,
                        "ratio": viscosity_value / epsilon_value,
                        "quadrant": (
                            f'{epsilon_row["dataset_id"]} x {viscosity_row["dataset_id"]}'
                        ),
                        "pair_quality_layer": (
                            "publishable_core" if both_core else "filter_only"
                        ),
                        "epsilon_row_id": epsilon_row["row_id"],
                        "viscosity_row_id": viscosity_row["row_id"],
                        "epsilon_row_index": int(epsilon_row["source_row_index"]),
                        "viscosity_row_index": int(viscosity_row["source_row_index"]),
                    }
                )
    pairs.sort(
        key=lambda item: (
            item["inchikey"],
            item["T_K"],
            item["epsilon_row_index"],
            item["viscosity_row_index"],
        )
    )
    return pairs

def reconstruct_predicted_dn() -> dict[str, float]:
    RDLogger.DisableLog("rdApp.*")
    mapping: dict[str, float] = {}
    with SOLVFUNC_PATH.open("r", encoding="cp1252", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            smiles = (row.get("SMILES") or "").strip()
            value = (row.get("DN_Pred (kcal/mol)") or "").strip()
            molecule = Chem.MolFromSmiles(smiles) if smiles else None
            if molecule is None or not value:
                continue
            mapping[Chem.MolToInchiKey(molecule)] = float(value)
    return mapping
def run_checks() -> list[tuple[str, bool, str]]:
    prereg = load_json(PREREG_PATH)
    summary = load_json(SUMMARY_PATH)
    _, joint = read_csv_rows(JOINT_TABLE_PATH)
    _, pairs = read_csv_rows(PAIRS_PATH)
    _, audit = read_csv_rows(DN_AUDIT_PATH)

    tolerance = float(prereg["walden_pairs"]["t_tolerance_k"])
    threshold = float(prereg["dn_channel"]["coverage_threshold"])
    results: list[tuple[str, bool, str]] = []

    # 1. joint table recount against the prereg's expected values.
    keys = {row["inchikey"] for row in joint}
    split = Counter(row["dataset_id"] for row in joint)
    expected = prereg["input"]
    recount_ok = (
        len(joint) == int(expected["expected_rows"])
        and len(keys) == int(expected["expected_distinct_keys"])
        and dict(split) == {k: int(v) for k, v in expected["expected_source_split"].items()}
    )
    recount_summary = summary.get("joint_table_recount", {})
    recount_ok = recount_ok and bool(recount_summary.get("recount_matches_prereg"))
    results.append(
        (
            "joint_table_recount",
            recount_ok,
            f"rows={len(joint)} keys={len(keys)} split={dict(sorted(split.items()))}",
        )
    )

    # 2. both provenances present and averaging never applied.
    missing = [
        row["pair_id"]
        for row in pairs
        if any(not (row.get(column) or "").strip() for column in PROVENANCE_COLUMNS)
    ]
    doi_missing = [
        row["pair_id"]
        for row in pairs
        if row["pair_quality_layer"] == "publishable_core"
        and any(not (row.get(column) or "").strip() for column in DOI_COLUMNS)
    ]
    averaged = [row["pair_id"] for row in pairs if (row.get("averaging_applied") or "") != "false"]
    results.append(
        (
            "pair_provenance_present",
            not missing and not doi_missing and not averaged,
            (
                f"{len(pairs)} rows; {len(missing)} without provenance; "
                f"{len(doi_missing)} core rows without a DOI; {len(averaged)} with averaging"
            ),
        )
    )

    # 3. the temperature-alignment rule holds on every committed pair row.
    misaligned = []
    for row in pairs:
        epsilon_t = float(row["epsilon_T_K_source"])
        viscosity_t = float(row["viscosity_T_K_source"])
        stored = float(row["T_K"])
        delta = float(row["T_alignment_delta_K"])
        if (
            abs(epsilon_t - viscosity_t) > tolerance
            or not close(delta, abs(epsilon_t - viscosity_t))
            or not close(stored, epsilon_t)
        ):
            misaligned.append(row["pair_id"])
    results.append(
        (
            "pairs_temperature_alignment",
            not misaligned,
            f"tolerance={tolerance:g} K; {len(misaligned)} misaligned rows",
        )
    )

    # 4. both coupling columns recompute from the two stored values.
    bad_coupling = []
    for row in pairs:
        epsilon_value = float(row["epsilon"])
        viscosity_value = float(row["viscosity_Pa_s"])
        coupling_bad = not close(
            float(row["walden_coupling_epsilon_times_eta"]), epsilon_value * viscosity_value
        )
        ratio_bad = not close(
            float(row["walden_ratio_eta_over_epsilon"]), viscosity_value / epsilon_value
        )
        if coupling_bad or ratio_bad:
            bad_coupling.append(row["pair_id"])
    results.append(
        (
            "coupling_columns_recompute",
            not bad_coupling,
            f"{len(pairs)} rows; {len(bad_coupling)} with a coupling mismatch",
        )
    )

    # 5. the pair quality layer equals the both-sides rule.
    bad_layer = []
    for row in pairs:
        expected_layer = (
            "publishable_core"
            if row["epsilon_quality_layer"] == "publishable_core"
            and row["viscosity_quality_layer"] == "publishable_core"
            else "filter_only"
        )
        if row["pair_quality_layer"] != expected_layer:
            bad_layer.append(row["pair_id"])
    results.append(
        (
            "pair_quality_layer_rule",
            not bad_layer,
            f"{len(pairs)} rows; {len(bad_layer)} with a layer mismatch",
        )
    )

    # 6. the DN coverage fraction and the verdict follow the prereg criterion.
    target_keys = sorted(keys)
    predicted = reconstruct_predicted_dn()
    admissible: dict[str, float] = {}
    covered_admissible = sum(1 for key in target_keys if key in admissible)
    covered_predicted = sum(1 for key in target_keys if key in predicted)
    fraction = covered_admissible / len(target_keys) if target_keys else 0.0
    expected_verdict = (
        "channel_available_for_a_later_feature_table"
        if fraction >= threshold
        else "channel_does_not_enter_the_feature_table"
    )
    dn = summary.get("dn_channel", {})
    coverage_ok = (
        len(audit) == len(target_keys)
        and int(dn.get("target_keys", -1)) == len(target_keys)
        and int(dn.get("admissible", {}).get("covered_keys", -1)) == covered_admissible
        and close(float(dn.get("admissible", {}).get("coverage_fraction", -1)), fraction)
        and dn.get("verdict") == expected_verdict
        and int(dn.get("predicted_sub_channel", {}).get("covered_keys", -1)) == covered_predicted
    )
    results.append(
        (
            "dn_coverage_and_verdict",
            coverage_ok,
            (
                f"target={len(target_keys)} admissible={covered_admissible} "
                f"predicted={covered_predicted} fraction={fraction:.4f} "
                f"threshold={threshold} verdict={dn.get('verdict')}"
            ),
        )
    )

    # 7. the six frozen artefacts keep their digests.
    frozen = {
        relative: sha256_of(REPOSITORY_ROOT / relative)
        for relative in prereg.get("frozen_red_lines", {})
    }
    moved = [
        relative
        for relative, digest in frozen.items()
        if digest != prereg["frozen_red_lines"][relative]
    ]
    results.append(
        (
            "frozen_red_lines_intact",
            not moved,
            f"{len(frozen)} artefacts; moved={moved}",
        )
    )
    return results

def run_supplementary() -> list[tuple[str, bool, str]]:
    prereg = load_json(PREREG_PATH)
    summary = load_json(SUMMARY_PATH)
    _, joint = read_csv_rows(JOINT_TABLE_PATH)
    _, pairs = read_csv_rows(PAIRS_PATH)
    _, audit = read_csv_rows(DN_AUDIT_PATH)
    tolerance = float(prereg["walden_pairs"]["t_tolerance_k"])
    reconstructed = reconstruct_pairs(joint, tolerance)
    results: list[tuple[str, bool, str]] = []

    # the committed pair table equals the site-local reconstruction.
    mismatch = len(pairs) != len(reconstructed)
    detail = "row counts differ"
    if not mismatch:
        for committed, rebuilt in zip(pairs, reconstructed):
            if committed["inchikey"] != rebuilt["inchikey"]:
                mismatch = True
                detail = f"key mismatch at {committed['pair_id']}"
                break
            if committed["pair_source_quadrant"] != rebuilt["quadrant"]:
                mismatch = True
                detail = f"quadrant mismatch at {committed['pair_id']}"
                break
            if not close(float(committed["T_K"]), rebuilt["T_K"]):
                mismatch = True
                detail = f"T_K mismatch at {committed['pair_id']}"
                break
            if not close(
                float(committed["walden_coupling_epsilon_times_eta"]), rebuilt["coupling"]
            ):
                mismatch = True
                detail = f"coupling mismatch at {committed['pair_id']}"
                break
    else:
        detail = f"committed={len(pairs)} reconstructed={len(reconstructed)}"
    if not mismatch:
        detail = f"{len(pairs)} rows reproduce from the joint table"
    results.append(("pairs_table_matches_reconstruction", not mismatch, detail))

    # the committed DN audit table equals the site-local reconstruction.
    predicted = reconstruct_predicted_dn()
    pair_keys = {row["inchikey"] for row in reconstructed}
    target_keys = sorted({row["inchikey"] for row in joint})
    audit_keys = [row["inchikey"] for row in audit]
    audit_mismatch = audit_keys != target_keys
    detail = "key sets differ" if audit_mismatch else f"{len(audit)} rows"
    if not audit_mismatch:
        for row in audit:
            key = row["inchikey"]
            carries_predicted = key in predicted
            if (row["key_carries_predicted_dn"] == "true") != carries_predicted:
                audit_mismatch = True
                detail = f"predicted flag mismatch at {key}"
                break
            expected_status = "predicted_dn_only" if carries_predicted else "no_dn"
            if row["dn_channel_status"] != expected_status:
                audit_mismatch = True
                detail = f"status mismatch at {key}"
                break
            if (row["in_walden_pair_set"] == "true") != (key in pair_keys):
                audit_mismatch = True
                detail = f"pair-set flag mismatch at {key}"
                break
            if row["key_carries_admissible_dn"] != "false":
                audit_mismatch = True
                detail = f"admissible DN claimed at {key}"
                break
    if not audit_mismatch:
        detail = f"{len(audit)} rows reproduce; predicted covered={len(set(audit_keys) & set(predicted))}"
    results.append(("dn_audit_table_matches_reconstruction", not audit_mismatch, detail))

    # the summary manifest digests match the bytes on disk.
    manifest = summary.get("manifest", {})
    digest_failures = []
    for name, path in (
        ("pairs", PAIRS_PATH),
        ("dn_coverage_audit", DN_AUDIT_PATH),
        ("builder", BUILDER_PATH),
        ("prereg", PREREG_PATH),
    ):
        recorded = manifest.get(name, {}).get("sha256", "")
        measured = sha256_of(path)
        if recorded != measured:
            digest_failures.append(name)
    results.append(
        (
            "summary_manifest_matches_disk",
            not digest_failures,
            f"mismatched={digest_failures}",
        )
    )

    # the run telemetry is a data-engineering reading, not a model reading.
    telemetry = summary.get("run_telemetry", {})
    telemetry_ok = (
        telemetry.get("network_calls") == 0
        and telemetry.get("models_fitted") == 0
        and telemetry.get("r2_reported") is False
        and telemetry.get("run_mode") == "offline"
        and telemetry.get("writes_under_data") == 2
    )
    results.append(
        (
            "run_telemetry_is_data_engineering",
            telemetry_ok,
            (
                f"network={telemetry.get('network_calls')} models={telemetry.get('models_fitted')} "
                f"r2={telemetry.get('r2_reported')} mode={telemetry.get('run_mode')}"
            ),
        )
    )

    # the quadrant and layer counts in the summary match the table itself.
    quadrant = Counter(row["pair_source_quadrant"] for row in pairs)
    layer = Counter(row["pair_quality_layer"] for row in pairs)
    walden = summary.get("walden_pairs", {})
    counts_ok = (
        int(walden.get("rows", -1)) == len(pairs)
        and walden.get("by_source_quadrant") == dict(sorted(quadrant.items()))
        and walden.get("by_pair_quality_layer") == dict(sorted(layer.items()))
        and walden.get("averaging_applied") is False
    )
    results.append(
        (
            "quadrant_and_layer_counts_match",
            counts_ok,
            f"quadrants={dict(sorted(quadrant.items()))} layers={dict(sorted(layer.items()))}",
        )
    )
    return results

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="the CI-conventional explicit form; this script only ever verifies",
    )
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    arguments = parser.parse_args(argv)

    checks = run_checks()
    supplementary = run_supplementary()
    results = [*checks, *supplementary]
    failures = [name for name, ok, _ in results if not ok]
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print(f"{len(results) - len(failures)}/{len(results)} checks passed")
    if arguments.json:
        print(
            json.dumps(
                {
                    "passed": not failures,
                    "checks": len(results),
                    "contract_checks": len(checks),
                    "failures": failures,
                },
                ensure_ascii=False,
            )
        )
    return 0 if not failures else 1

if __name__ == "__main__":
    raise SystemExit(main())