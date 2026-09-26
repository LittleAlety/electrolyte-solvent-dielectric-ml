"""Independent verifier for the v2.0 Uni-Mol fine-tune probe specification.

The specification probes/unimol_probe_spec_prereg.json is a pre-registration, so
the point of this module is not to trust it but to re-derive, from the
repository bytes, every claim it makes that can be re-derived:

1. the six frozen red lines still hash to the digests the manual pins;
2. the 236 table exists in both materialisations the spec names, its row counts
   hold, and the two compound sets are equal once the four multi-fragment xTB
   feature failures are removed;
3. the existing xTB conformer scratch trees still hold the counts the spec
   recorded (git-ignored directories: reported as SKIP, and never as PASS, when
   they are absent, e.g. on a fresh clone);
4. the conformer-count conflict is registered with both claims and no silent
   resolution;
5. every copied KPI hyper-parameter carries KPI_SI_via_manual provenance and
   our_measurement == false;
6. the evaluation protocol is the project standard (observation level,
   GroupKFold by InChIKey, per-fold train-side ranking, group_overlap == 0) and
   the KPI random 8:1:1 split is explicitly barred;
7. the scoreboard isolation rule keeps 0.4091179943351143 / 0.364 / 0.5332 /
   0.5454 apart, each with its pool definition;
8. the deliverables are UTF-8, no BOM, LF only;
9. every verbatim quote in the spec is a real substring of the manual snapshot
   line it cites (markdown emphasis and quote style are not content; every digit
   and every CJK character must match), and every cited line is inside the file;
10. the MAE / R2 pair recorded for random_row and group_key reproduces from
   probes/viscosity_baseline_summary.json, and the digest the report declares in
   its header equals the spec bytes on disk.

Usage::

    python probes/verify_unimol_probe_spec.py --check

Exit code 0 means PASS, 1 means FAIL.  Nothing here writes to the repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

SPEC_PATH = REPOSITORY_ROOT / "probes" / "unimol_probe_spec_prereg.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "unimol_probe_spec.md"
TEST_PATH = REPOSITORY_ROOT / "tests" / "test_unimol_probe_spec.py"

PILOT_POOL_PATH = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_pool.csv"
FROZEN_DATASET_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
PILOT_POOL_SHA256 = "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"

SPEC_DELIVERABLES = (SPEC_PATH, REPORT_PATH, TEST_PATH, Path(__file__).resolve())

REQUIRED_KPI_HYPERPARAMETERS: dict[str, Any] = {
    "conformer_count": 10,
    "conformer_store": "LMDB",
    "optimizer": "Adam",
    "batch_size": 32,
    "max_epochs": 500,
    "early_stop_patience": 20,
    "learning_rate": 1e-4,
}

MAIN_SCOREBOARD_R2 = 0.4091179943351143
MAIN_SCOREBOARD_ROWS = 457
MAIN_SCOREBOARD_COMPOUNDS = 97
HEADLINE_236_R2 = 0.364
POOL_DEFINITION_VALUES = (0.5332, 0.5454)
KPI_HYPERPARAMETER_SOURCE_LINE = 1517
LEVER9_DEFECT_ID = "lever9_permutation_importance_washed_the_wrong_columns"


def sha256_canonical_text(path: Path) -> str:
    """SHA-256 of UTF-8 text after normalising CRLF/CR to LF (repo convention)."""

    text = path.read_text(encoding="utf-8")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# Verbatim comparison: markdown emphasis and quote style are not content, so they
# are folded away before the substring test.  Every digit and every CJK character
# still has to match exactly.
_VERBATIM_IGNORED = (
    "*",
    "~",
    chr(96),
    chr(34),
    chr(39),
    chr(0x300C),
    chr(0x300D),
    chr(0x201C),
    chr(0x201D),
)


def _normalise_for_verbatim(text: str) -> str:
    for character in _VERBATIM_IGNORED:
        text = text.replace(character, "")
    return re.sub(r"\s+", "", text)


def _collect_verbatim_citations(node: Any, out: list[Mapping[str, Any]]) -> None:
    """Collect every evidence record that quotes a manual line."""

    if isinstance(node, Mapping):
        if "verbatim" in node and node.get("source_line") is not None:
            out.append(node)
        for value in node.values():
            _collect_verbatim_citations(value, out)
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        for value in node:
            _collect_verbatim_citations(value, out)


def _declared_spec_digest() -> str:
    """Read the digest the report declares in its own header."""

    text = REPORT_PATH.read_text(encoding="utf-8")
    match = re.search(r"规格 sha256[^0-9a-f]*([0-9a-f]{64})", text)
    return match.group(1) if match else ""


def _count_compound_dirs(root: Path) -> tuple[int, int, dict[str, int]]:
    """Return (compound_directories, input_xyz_files, conformers_per_compound)."""

    compound_dirs = [entry for entry in root.iterdir() if entry.is_dir()]
    xyz_total = 0
    histogram: Counter[str] = Counter()
    for compound in compound_dirs:
        found = len(list(compound.rglob("input.xyz")))
        xyz_total += found
        histogram[str(found)] += 1
    return len(compound_dirs), xyz_total, dict(sorted(histogram.items()))


def _artifact_by_id(spec: Mapping[str, Any], artifact_id: str) -> Mapping[str, Any] | None:
    for artifact in spec["inputs"]["verified_conformer_artifacts"]:
        if artifact.get("id") == artifact_id:
            return artifact
    return None


def verify(spec_path: Path = SPEC_PATH) -> dict[str, Any]:
    """Run every check and return a machine-readable report."""

    checks: list[dict[str, Any]] = []

    def record(check_id: str, contract: str, passed: bool, detail: Any = "") -> None:
        checks.append(
            {"id": check_id, "contract": contract, "passed": bool(passed), "detail": detail}
        )

    def skipped(check_id: str, contract: str, detail: Any = "") -> None:
        checks.append(
            {
                "id": check_id,
                "contract": contract,
                "passed": True,
                "skipped": True,
                "detail": detail,
            }
        )

    spec = _read_json(spec_path)

    locked_at = str(spec.get("locked_at_utc", ""))
    lock_ok = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", locked_at))
    if lock_ok:
        datetime.strptime(locked_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    record(
        "lock",
        "locked_at_utc is an ISO-8601 UTC stamp and status is locked_before_run",
        spec.get("schema_version") == 1
        and spec.get("status") == "locked_before_run"
        and lock_ok,
        {
            "schema_version": spec.get("schema_version"),
            "status": spec.get("status"),
            "locked_at_utc": locked_at,
        },
    )

    scope = spec.get("scope_of_this_round", {})
    record(
        "scope_no_model",
        "this round runs no model and claims no R2",
        scope.get("this_round_runs_no_model") is True
        and scope.get("r2_claimed_this_round") is False
        and scope.get("shots_this_round") == 0,
        {
            "this_round_runs_no_model": scope.get("this_round_runs_no_model"),
            "r2_claimed_this_round": scope.get("r2_claimed_this_round"),
            "shots_this_round": scope.get("shots_this_round"),
        },
    )

    missing = [
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in SPEC_DELIVERABLES
        if not path.is_file()
    ]
    record(
        "deliverables",
        "spec, report, test and verifier all exist on disk",
        not missing,
        {"missing": missing},
    )

    red_lines = spec.get("frozen_red_lines", {}).get("items", [])
    record(
        "red_line_count",
        "six frozen red lines are declared",
        spec.get("frozen_red_lines", {}).get("count") == 6 and len(red_lines) == 6,
        {"count": spec.get("frozen_red_lines", {}).get("count"), "items": len(red_lines)},
    )
    red_line_failures: list[str] = []
    for item in red_lines:
        relative = str(item.get("path", ""))
        target = REPOSITORY_ROOT / relative
        if not target.is_file():
            red_line_failures.append(relative + ": missing")
            continue
        actual = sha256_canonical_text(target)
        expected = str(item.get("sha256_canonical_text"))
        if actual != expected:
            red_line_failures.append(relative + ": " + actual + " != " + expected)
    record(
        "red_lines_intact",
        "every frozen red line digest reproduces byte-for-byte",
        not red_line_failures,
        {"failures": red_line_failures},
    )

    pilot_rows = _csv_rows(PILOT_POOL_PATH)
    dataset_rows = _csv_rows(FROZEN_DATASET_PATH)
    model_ready = [row for row in dataset_rows if row.get("model_ready") == "true"]
    failed_keys = set(spec["kill_line"]["the_236_table_verified"]["four_failed_feature_keys"])
    fitted_keys = {row["inchikey"] for row in model_ready} - failed_keys
    pilot_keys = {row["inchikey"] for row in pilot_rows}

    record(
        "pilot_pool_rows",
        "probes/l3_stage1_pilot_pool.csv still holds 236 data rows",
        len(pilot_rows) == 236,
        {"rows": len(pilot_rows)},
    )
    record(
        "pilot_pool_digest",
        "the pilot pool digest matches the frozen red-line value",
        sha256_canonical_text(PILOT_POOL_PATH) == PILOT_POOL_SHA256,
        sha256_canonical_text(PILOT_POOL_PATH)[:24],
    )
    record(
        "dataset_rows",
        "data/dielectric_v03.csv still holds 246 rows",
        len(dataset_rows) == 246,
        {"rows": len(dataset_rows)},
    )
    record(
        "model_ready_rows",
        "240 rows carry model_ready=true",
        len(model_ready) == 240,
        {"model_ready": len(model_ready)},
    )
    record(
        "fit_set_arithmetic",
        "240 model_ready rows minus 4 feature failures equals 236",
        len(model_ready) - len(failed_keys) == 236,
        {"model_ready": len(model_ready), "failures": len(failed_keys)},
    )
    record(
        "fit_set_identity",
        "the pilot pool keys equal the 236 fitted keys exactly",
        pilot_keys == fitted_keys,
        {"symmetric_difference": len(pilot_keys ^ fitted_keys)},
    )

    for artifact_id in (
        "frozen_single_conformer_scratch",
        "v11plus_new_conformer_scratch",
        "multi_conformer_scratch_v04",
    ):
        artifact = _artifact_by_id(spec, artifact_id)
        if artifact is None:
            record("artifact_" + artifact_id, artifact_id + " is declared", False, "absent")
            continue
        root = REPOSITORY_ROOT / str(artifact["path"])
        if not root.is_dir():
            skipped(
                "artifact_" + artifact_id,
                artifact_id + " counts reproduce (directory absent -> SKIP)",
                {"path": str(artifact["path"])},
            )
            continue
        dirs, xyz_total, histogram = _count_compound_dirs(root)
        expected_histogram = artifact.get(
            "conformers_per_compound_histogram_measured", histogram
        )
        unchanged = (
            dirs == artifact.get("compound_directories_measured")
            and xyz_total == artifact.get("input_xyz_files_measured")
            and histogram == expected_histogram
        )
        record(
            "artifact_" + artifact_id,
            artifact_id + " counts still match the spec",
            unchanged,
            {
                "dirs": dirs,
                "input_xyz": xyz_total,
                "histogram": histogram,
                "spec_dirs": artifact.get("compound_directories_measured"),
                "spec_input_xyz": artifact.get("input_xyz_files_measured"),
            },
        )

    accounting = _artifact_by_id(spec, "conformer_accounting_artifact")
    if accounting is not None:
        accounting_path = REPOSITORY_ROOT / str(accounting["path"])
        if not accounting_path.is_file():
            record(
                "artifact_conformer_accounting",
                "conformer accounting CSV exists",
                False,
                str(accounting["path"]),
            )
        else:
            rows = _csv_rows(accounting_path)
            record(
                "artifact_conformer_accounting",
                "the tracked conformer accounting CSV still holds 276 rows",
                len(rows) == 276,
                {"rows": len(rows)},
            )

    claims = spec.get("conformer_count_claims", [])
    counts = {claim.get("conformer_count") for claim in claims}
    claims_well_formed = all(
        claim.get("source_path") and isinstance(claim.get("source_line"), int)
        for claim in claims
    )
    record(
        "conflict_both_claims",
        "both the 10-conformer and the 11-conformer claims are registered with sources",
        counts == {10, 11} and claims_well_formed and len(claims) >= 2,
        {"counts": sorted(counts), "claims": len(claims), "sourced": claims_well_formed},
    )

    conflict = spec.get("conformer_count_conflict", {})
    explanations = conflict.get("candidate_explanations", [])
    none_verified = all(item.get("verified") is False for item in explanations) and bool(
        explanations
    )
    labels_flagged = all(item.get("label") == "未证实" for item in explanations)
    record(
        "conflict_unresolved",
        "conflict left unresolved, no silent pick, every explanation unverified",
        conflict.get("registered") is True
        and conflict.get("status") == "unresolved"
        and conflict.get("no_silent_resolution") is True
        and none_verified
        and labels_flagged,
        {
            "status": conflict.get("status"),
            "no_silent_resolution": conflict.get("no_silent_resolution"),
            "explanations": len(explanations),
            "labels_flagged": labels_flagged,
        },
    )
    ten_plus_one = any(
        "10" in str(item.get("text", "")) and "11" in str(item.get("text", ""))
        for item in explanations
    )
    record(
        "conflict_explanation_registered",
        "the 10 RDKit + 1 xTB reading is registered and marked unverified",
        ten_plus_one,
    )

    items = {
        item.get("name"): item for item in spec["hyperparameters_copied_from_kpi"]["items"]
    }
    provenance_failures: list[str] = []
    for name, expected in REQUIRED_KPI_HYPERPARAMETERS.items():
        item = items.get(name)
        if item is None:
            provenance_failures.append(name + ": absent")
            continue
        if item.get("provenance_kind") != "KPI_SI_via_manual":
            provenance_failures.append(name + ": provenance=" + str(item.get("provenance_kind")))
        if item.get("our_measurement") is not False:
            provenance_failures.append(
                name + ": our_measurement=" + str(item.get("our_measurement"))
            )
        if item.get("value") != expected:
            provenance_failures.append(
                name + ": value=" + str(item.get("value")) + " != " + str(expected)
            )
    record(
        "kpi_hyperparameter_provenance",
        "every copied KPI hyper-parameter is attributed to KPI SI, never to us",
        not provenance_failures,
        {"failures": provenance_failures},
    )
    record(
        "kpi_source_pinned",
        "the KPI hyper-parameter source line is pinned in the manual snapshot",
        spec["hyperparameters_copied_from_kpi"]["source"]["source_line"]
        == KPI_HYPERPARAMETER_SOURCE_LINE,
        spec["hyperparameters_copied_from_kpi"]["source"]["source_line"],
    )

    protocol = spec.get("evaluation_protocol", {})
    record(
        "protocol_project_standard",
        "observation level + GroupKFold by InChIKey + per-fold train-side ranking",
        protocol.get("project_standard") is True
        and protocol.get("observation_level", {}).get("required") is True
        and protocol.get("splitter", {}).get("kind") == "GroupKFold"
        and protocol.get("splitter", {}).get("group_key") == "InChIKey"
        and protocol.get("per_fold_train_side_ranking", {}).get("required") is True,
        {"splitter": protocol.get("splitter")},
    )
    record(
        "protocol_group_overlap",
        "the group_overlap == 0 assertion is required",
        protocol.get("group_overlap_assertion", {}).get("expression") == "group_overlap == 0",
        protocol.get("group_overlap_assertion", {}).get("expression"),
    )
    record(
        "protocol_kpi_split_barred",
        "the KPI random 8:1:1 split is barred and random_row never enters a verdict",
        protocol.get("kpi_random_split_must_not_be_ported", {}).get("required") is True
        and protocol.get("random_row", {}).get("verdict_eligible") is False
        and protocol.get("random_row", {}).get("role") == "leak_reference_only",
        {
            "kpi_random_split_barred": protocol.get(
                "kpi_random_split_must_not_be_ported", {}
            ).get("required"),
            "random_row_role": protocol.get("random_row", {}).get("role"),
        },
    )

    isolation = spec.get("scoreboard_isolation", {})
    main = isolation.get("main_scoreboard", {})
    headline = isolation.get("secondary_scoreboard_v1_0_headline", {})
    record(
        "scoreboard_main",
        "the main scoreboard baseline is 0.4091179943351143 on 457 rows / 97 compounds",
        main.get("baseline_r2") == MAIN_SCOREBOARD_R2
        and main.get("rows") == MAIN_SCOREBOARD_ROWS
        and main.get("compounds") == MAIN_SCOREBOARD_COMPOUNDS,
        {
            "baseline_r2": main.get("baseline_r2"),
            "rows": main.get("rows"),
            "compounds": main.get("compounds"),
        },
    )
    record(
        "scoreboard_headline_separated",
        "the v1.0 headline 0.364 lives on the 236 pool and is never mixed with the 457 pool",
        headline.get("r2_rounded") == HEADLINE_236_R2
        and headline.get("rows") == 236
        and bool(isolation.get("forbidden_mixings")),
        {"r2_rounded": headline.get("r2_rounded"), "rows": headline.get("rows")},
    )
    pooled = {
        item.get("value"): item.get("pool_definition")
        for item in isolation.get("pool_definition_required_for", [])
    }
    record(
        "scoreboard_pool_definitions",
        "0.5332 and 0.5454 may only be quoted with their pool definitions",
        all(pooled.get(value) for value in POOL_DEFINITION_VALUES),
        {str(key): bool(value) for key, value in pooled.items()},
    )

    controller = spec.get("knowledge_controller", {})
    record(
        "knowledge_controller",
        "the purity controller (SHAP top-K) and the flow controller are both specified",
        "top-K" in str(controller.get("purity_controller", {}).get("definition", ""))
        and bool(controller.get("flow_controller", {}).get("definition")),
        {
            "purity": controller.get("purity_controller", {}).get("definition"),
            "flow": controller.get("flow_controller", {}).get("definition"),
        },
    )
    binding = spec.get("column_binding_rule", {})
    record(
        "column_binding",
        "the knowledge vector column order must be explicitly bound to labels",
        "显式绑定" in str(binding.get("statement_zh", ""))
        and binding.get("defect_this_rule_is_written_against", {}).get("id") == LEVER9_DEFECT_ID
        and len(binding.get("mandatory_assertions_before_any_fit", [])) >= 3,
        {
            "statement": binding.get("statement_zh"),
            "defect": binding.get("defect_this_rule_is_written_against", {}).get("id"),
        },
    )

    kill = spec.get("kill_line", {})
    record(
        "kill_line",
        "the kill line names the 236-row pool and stops on a loss to hybrid XGBoost",
        "236" in str(kill.get("verbatim_zh", ""))
        and "hybrid XGBoost" in str(kill.get("verbatim_zh", ""))
        and "236" in str(kill.get("the_236_table_verified", {}).get("answer", "")),
        {"verbatim_zh": kill.get("verbatim_zh")},
    )

    hygiene_failures: list[str] = []
    for path in SPEC_DELIVERABLES:
        if not path.is_file():
            continue
        raw = path.read_bytes()
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        if raw[:3] == b"\xef\xbb\xbf":
            hygiene_failures.append(relative + ": BOM")
        crlf = raw.count(b"\r\n")
        if crlf:
            hygiene_failures.append(relative + ": CRLF x" + str(crlf))
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            hygiene_failures.append(relative + ": not UTF-8")
    record(
        "file_hygiene",
        "deliverables are UTF-8, no BOM, LF only",
        not hygiene_failures,
        {"failures": hygiene_failures},
    )

    snapshot_path = REPOSITORY_ROOT / "tests" / "fixtures" / "manual_appendix_j_snapshot.md"
    snapshot_lines = snapshot_path.read_text(encoding="utf-8").split(chr(10))
    citations: list[Mapping[str, Any]] = []
    _collect_verbatim_citations(spec, citations)
    out_of_range = [
        int(citation["source_line"])
        for citation in citations
        if not 0 < int(citation["source_line"]) <= len(snapshot_lines)
    ]
    record(
        "manual_citations_in_range",
        "every citation that names a manual snapshot line resolves inside that file",
        not out_of_range,
        {"snapshot_lines": len(snapshot_lines), "out_of_range": out_of_range},
    )
    citation_failures = []
    for citation in citations:
        line_number = int(citation["source_line"])
        if not 0 < line_number <= len(snapshot_lines):
            continue
        expected = _normalise_for_verbatim(str(citation["verbatim"]))
        actual = _normalise_for_verbatim(snapshot_lines[line_number - 1])
        if expected not in actual:
            citation_failures.append(
                "line " + str(line_number) + ": " + str(citation["verbatim"])[:60]
            )
    record(
        "manual_citations_verbatim",
        "every verbatim quote is a real substring of the snapshot line it cites",
        not citation_failures,
        {"citations": len(citations), "failures": citation_failures},
    )

    measured = spec.get("evaluation_protocol", {}).get("random_row", {}).get("measured_on_disk", {})
    viscosity_summary = _read_json(REPOSITORY_ROOT / "probes" / "viscosity_baseline_summary.json")
    metric_failures = []
    for split in ("random_row", "group_key"):
        recorded = measured.get(split)
        if not isinstance(recorded, Mapping):
            metric_failures.append(split + ": not recorded")
            continue
        on_disk = viscosity_summary["splits"][split]["models"]["MorganTemperatureXGBoost"][
            str(measured.get("metric", "log10_cP"))
        ]
        for key in ("mae", "r2"):
            if float(recorded[key]) != float(on_disk[key]):
                metric_failures.append(split + "." + key)
    record(
        "random_row_mae_r2_from_disk",
        "the MAE and R2 recorded for random_row / group_key reproduce from the viscosity summary",
        not metric_failures,
        {"failures": metric_failures},
    )

    declared_digest = _declared_spec_digest()
    actual_digest = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    record(
        "report_declares_spec_digest",
        "the digest the report declares in its header equals the spec bytes on disk",
        declared_digest == actual_digest,
        {"declared": declared_digest, "actual": actual_digest},
    )

    failed = [check for check in checks if not check["passed"]]
    return {
        "task": "verify_unimol_probe_spec",
        "spec": {
            "path": spec_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
        },
        "verification_passed": not failed,
        "checks_total": len(checks),
        "checks_failed": len(failed),
        "checks_skipped": len([check for check in checks if check.get("skipped")]),
        "failures": [check["id"] for check in failed],
        "checks": checks,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: print the check table and return 0 for PASS, 1 for FAIL."""

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-derive every repository fact and compare it to the spec",
    )
    parser.add_argument("--spec", type=Path, default=SPEC_PATH)
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    arguments = parser.parse_args(argv)

    report = verify(spec_path=arguments.spec)
    if arguments.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for check in report["checks"]:
            if check.get("skipped"):
                marker = "SKIP"
            else:
                marker = "PASS" if check["passed"] else "FAIL"
            detail = "" if check["passed"] else "  " + str(check["detail"])
            print("[" + marker + "] " + check["id"] + "  " + check["contract"] + detail)
        passed = report["checks_total"] - report["checks_failed"]
        print(
            "checks=" + str(report["checks_total"])
            + " passed=" + str(passed)
            + " skipped=" + str(report["checks_skipped"])
            + " failed=" + str(report["checks_failed"])
        )
        print("spec sha256=" + report["spec"]["sha256"])
        state = "PASS" if report["verification_passed"] else "FAIL"
        print(state + ": " + str(report["failures"]))
    return 0 if report["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
