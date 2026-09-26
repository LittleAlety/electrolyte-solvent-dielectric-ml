"""Guards for the v2.0 Uni-Mol fine-tune probe specification.

The specification is a pre-registration, so these tests pin the things that make
it honest and auditable:

* it is locked before the run and claims no model reading of its own;
* every copied KPI hyper-parameter is attributed to KPI SI via the manual and
  never to a measurement of ours;
* the 10-conformer / 11-conformer source conflict is registered with both sides,
  with line numbers, and is left unresolved;
* the two conflicting claim lines really do say what the specification says
  they say (the manual snapshot is read back and searched);
* the knowledge controller is specified and the knowledge-vector column order is
  explicitly bound, with the lever-9 wrong-column defect named as the reason;
* the kill line names the 236-row pool, and the 236 table on disk really is the
  v1.0 frozen pool (row counts plus set equality against the four xTB feature
  failures);
* the evaluation protocol is the project standard and the KPI random 8:1:1
  split is barred;
* the scoreboard isolation rule keeps 0.4091179943351143 / 0.364 / 0.5332 /
  0.5454 apart;
* every verbatim quote is a real substring of the manual snapshot line it
  cites, and the MAE / R2 pair recorded for random_row and group_key reproduces
  from the disk summary;
* the six frozen red lines are intact, and the independent verifier passes;
* every deliverable is UTF-8, no BOM, LF only.
"""

from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import sys

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.verify_unimol_probe_spec import (
    MAIN_SCOREBOARD_R2,
    PILOT_POOL_PATH,
    SPEC_PATH,
    _collect_verbatim_citations,
    _declared_spec_digest,
    _normalise_for_verbatim,
    sha256_canonical_text,
    verify,
)

MANUAL_SNAPSHOT = REPOSITORY_ROOT / "tests" / "fixtures" / "manual_appendix_j_snapshot.md"
FROZEN_DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "unimol_probe_spec.md"
VERIFIER_PATH = REPOSITORY_ROOT / "probes" / "verify_unimol_probe_spec.py"
TEST_PATH = pathlib.Path(__file__).resolve()

REQUIRED_KPI_HYPERPARAMETERS = {
    "conformer_count": 10,
    "conformer_store": "LMDB",
    "optimizer": "Adam",
    "loss": "smooth MAE (smooth L1)",
    "batch_size": 32,
    "max_epochs": 500,
    "early_stop_patience": 20,
    "learning_rate": 1e-4,
    "lr_schedule": "polynomial decay",
}
KPI_SOURCE_LINE = 1651
CLAIM_11_LINES = (1452, 1470)
EXPECTED_COUNTS = {10, 11}


@pytest.fixture(scope="module")
def spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def snapshot_lines() -> list[str]:
    return MANUAL_SNAPSHOT.read_text(encoding="utf-8").splitlines()


def _rows(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_spec_is_locked_before_the_run(spec: dict) -> None:
    assert spec["schema_version"] == 1
    assert spec["status"] == "locked_before_run"
    assert spec["locked_at_utc"].endswith("Z")
    assert spec["lock_rule"]
    assert spec["task"] == "v2_0_unimol_finetune_probe_spec"


def test_this_round_runs_no_model_and_claims_no_r2(spec: dict) -> None:
    scope = spec["scope_of_this_round"]
    assert scope["this_round_runs_no_model"] is True
    assert scope["this_round_writes_only_the_spec"] is True
    assert scope["r2_claimed_this_round"] is False
    assert scope["shots_this_round"] == 0
    assert spec["discipline"]["no_model_run_this_round"]
    assert spec["discipline"]["no_r2_may_be_claimed"]
    assert spec["registered_uncertainties"]


def test_kpi_hyperparameters_are_attributed_not_measured(spec: dict) -> None:
    block = spec["hyperparameters_copied_from_kpi"]
    assert block["source"]["source_line"] == KPI_SOURCE_LINE
    assert block["source"]["path"] == "tests/fixtures/manual_appendix_j_snapshot.md"
    assert "RDKit 10 构象" in block["source"]["verbatim"]
    items = {item["name"]: item for item in block["items"]}
    for name, expected in REQUIRED_KPI_HYPERPARAMETERS.items():
        item = items[name]
        assert item["value"] == expected, name
        assert item["provenance_kind"] == "KPI_SI_via_manual", name
        assert item["our_measurement"] is False, name
    assert block["not_copied_from_kpi"]


def test_conformer_count_conflict_is_registered_and_left_unresolved(spec: dict) -> None:
    claims = spec["conformer_count_claims"]
    assert {claim["conformer_count"] for claim in claims} == EXPECTED_COUNTS
    for claim in claims:
        assert claim["source_path"] == "tests/fixtures/manual_appendix_j_snapshot.md"
        assert isinstance(claim["source_line"], int)
        assert claim["source_verbatim_fragment"]

    conflict = spec["conformer_count_conflict"]
    assert conflict["registered"] is True
    assert conflict["status"] == "unresolved"
    assert conflict["no_silent_resolution"] is True
    assert set(conflict["conflicting_claims"]) == {
        claim["id"] for claim in claims
    }
    explanations = conflict["candidate_explanations"]
    assert explanations
    for explanation in explanations:
        assert explanation["verified"] is False
        assert explanation["label"] == "未证实"
    combined = " ".join(explanation["text"] for explanation in explanations)
    assert "10" in combined and "11" in combined


def test_the_conflicting_claims_quote_the_manual_lines_verbatim(snapshot_lines: list[str]) -> None:
    """Read the manual snapshot back: the cited lines really carry the two counts."""

    for line_number in CLAIM_11_LINES:
        line = snapshot_lines[line_number - 1]
        assert "11 构象" in line, line_number
    ten_line = snapshot_lines[KPI_SOURCE_LINE - 1]
    assert "RDKit 10 构象" in ten_line


def test_knowledge_controller_purity_and_flow(spec: dict) -> None:
    controller = spec["knowledge_controller"]
    purity = controller["purity_controller"]
    assert "top-K" in purity["definition"]
    assert purity["k_source"] == "SHAP top-K"
    assert "per-fold train-side ranking" in purity["leak_rule"]
    flow = controller["flow_controller"]
    assert "可学习" in flow["definition"]
    assert controller["our_domain_knowledge_pool"]["size"] == 10
    assert len(controller["our_domain_knowledge_pool"]["members"]) == 10


def test_column_binding_is_explicit_and_cites_the_lever9_defect(spec: dict) -> None:
    binding = spec["column_binding_rule"]
    assert "显式绑定" in binding["statement_zh"]
    assert "不得让标签位置决定语义" in binding["statement_zh"]
    defect = binding["defect_this_rule_is_written_against"]
    assert defect["id"] == "lever9_permutation_importance_washed_the_wrong_columns"
    assert defect["severity"] == "P0"
    assert "permutation_importance" in defect["site"]
    assert len(binding["mandatory_assertions_before_any_fit"]) >= 3
    assert binding["forbidden"]
    evidence_lines = {item["source_line"] for item in defect["evidence"]}
    assert 1739 in evidence_lines
    assert 3791 in evidence_lines


def test_kill_line_names_236_and_stops_on_a_loss(spec: dict) -> None:
    kill = spec["kill_line"]
    assert kill["verbatim_zh"] == "236 样本打不过 hybrid XGBoost 即停，记负结果"
    assert kill["source"]["source_line"] == 1470
    assert "即停" in kill["action_on_fail"]
    assert "负结果" in kill["action_on_fail"]


def test_the_236_table_on_disk_is_the_v1_0_frozen_pool(spec: dict) -> None:
    verified = spec["kill_line"]["the_236_table_verified"]
    pilot = _rows(PILOT_POOL_PATH)
    assert len(pilot) == 236
    assert sha256_canonical_text(PILOT_POOL_PATH) == "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"

    dataset = _rows(FROZEN_DATASET)
    assert len(dataset) == 246
    model_ready = [row for row in dataset if row["model_ready"] == "true"]
    assert len(model_ready) == 240

    failed_keys = set(verified["four_failed_feature_keys"])
    assert len(failed_keys) == 4
    fitted_keys = {row["inchikey"] for row in model_ready} - failed_keys
    pilot_keys = {row["inchikey"] for row in pilot}
    assert len(fitted_keys) == 236
    assert pilot_keys == fitted_keys
    assert verified["identity_check"]["symmetric_difference_count"] == 0

    materializations = {item["id"] for item in verified["materializations"]}
    assert materializations == {"pilot_pool_csv", "derived_from_dielectric_v03"}


def test_the_236_comparator_is_not_the_457_scoreboard(spec: dict) -> None:
    comparator = spec["kill_line"]["comparator_hybrid_xgboost"]
    headline = comparator["headline_on_the_236_pool"]
    assert headline["r2"] == 0.3636
    assert headline["published_rounded"] == 0.364
    assert "0.4091179943351143" in comparator["must_not_be_confused_with"]
    assert comparator["params_source"]["source_line"] == 3585


def test_evaluation_protocol_is_the_project_standard(spec: dict) -> None:
    protocol = spec["evaluation_protocol"]
    assert protocol["project_standard"] is True
    assert protocol["observation_level"]["required"] is True
    assert protocol["splitter"] == {"kind": "GroupKFold", "group_key": "InChIKey", "required": True}
    assert protocol["per_fold_train_side_ranking"]["required"] is True
    assert protocol["group_overlap_assertion"]["expression"] == "group_overlap == 0"


def test_kpi_random_split_is_barred_and_random_row_is_leak_only(spec: dict) -> None:
    protocol = spec["evaluation_protocol"]
    barred = protocol["kpi_random_split_must_not_be_ported"]
    assert barred["required"] is True
    assert barred["kpi_scheme"] == "random 8:1:1 + 4-fold CV"
    assert protocol["random_row"]["role"] == "leak_reference_only"
    assert protocol["random_row"]["verdict_eligible"] is False


def test_scoreboard_isolation_keeps_the_pools_apart(spec: dict) -> None:
    isolation = spec["scoreboard_isolation"]
    main = isolation["main_scoreboard"]
    assert main["baseline_r2"] == MAIN_SCOREBOARD_R2
    assert (main["rows"], main["compounds"], main["folds"]) == (457, 97, 50)

    headline = isolation["secondary_scoreboard_v1_0_headline"]
    assert headline["r2_rounded"] == 0.364
    assert headline["rows"] == 236
    assert main["baseline_r2"] != headline["r2_rounded"]

    pooled = {item["value"]: item["pool_definition"] for item in isolation["pool_definition_required_for"]}
    assert 0.5332 in pooled and 0.5454 in pooled
    assert all(pooled[value] for value in (0.5332, 0.5454))
    assert isolation["forbidden_mixings"]


def test_inputs_record_verified_paths_and_to_be_built_items(spec: dict) -> None:
    inputs = spec["inputs"]
    kinds = {artifact["id"] for artifact in inputs["verified_conformer_artifacts"]}
    assert "frozen_single_conformer_scratch" in kinds
    assert "multi_conformer_scratch_v04" in kinds
    assert "conformer_accounting_artifact" in kinds
    assert "data/interim/xtb_features" == next(
        artifact["path"]
        for artifact in inputs["verified_conformer_artifacts"]
        if artifact["id"] == "frozen_single_conformer_scratch"
    )
    statuses = {item["id"]: item["status"] for item in inputs["to_be_built"]}
    assert statuses["conformer_lmdb_store"] == "待建"
    assert statuses["unimol_conformer_ensemble_10"] == "待建"
    assert inputs["not_found"]
    assert inputs["not_found"][0]["status"] == "未查到"


def test_conformer_scratch_counts_match_the_spec(spec: dict) -> None:
    for artifact in spec["inputs"]["verified_conformer_artifacts"]:
        if "compound_directories_measured" not in artifact:
            continue
        root = REPOSITORY_ROOT / artifact["path"]
        if not root.is_dir():
            pytest.skip(f"{artifact['path']} absent (git-ignored scratch tree)")
        compound_dirs = [entry for entry in root.iterdir() if entry.is_dir()]
        assert len(compound_dirs) == artifact["compound_directories_measured"]
        xyz = sum(len(list(entry.rglob("input.xyz"))) for entry in compound_dirs)
        assert xyz == artifact["input_xyz_files_measured"]


def test_frozen_red_lines_are_intact(spec: dict) -> None:
    red_lines = spec["frozen_red_lines"]
    assert red_lines["count"] == 6
    for item in red_lines["items"]:
        path = REPOSITORY_ROOT / item["path"]
        assert path.is_file(), item["path"]
        assert sha256_canonical_text(path) == item["sha256_canonical_text"], item["path"]


def test_deliverables_are_utf8_lf_without_bom() -> None:
    for path in (SPEC_PATH, REPORT_PATH, VERIFIER_PATH, TEST_PATH):
        raw = path.read_bytes()
        assert raw[:3] != b"\xef\xbb\xbf", path
        assert b"\r\n" not in raw, path
        raw.decode("utf-8")


def test_no_forbidden_file_was_written_this_round(spec: dict) -> None:
    untouchables = " ".join(spec["discipline"]["untouchables"])
    assert "decisions_log.md 不改" in untouchables
    assert "paper/* 不写" in untouchables
    assert "data/ 下不写任何文件" in untouchables
    assert "不引用或复用 Reaxys 受限数值" in untouchables


def test_independent_verifier_passes() -> None:
    report = verify()
    failed = [check for check in report["checks"] if not check["passed"]]
    assert not failed, [check["id"] for check in failed]
    assert report["verification_passed"] is True
    assert report["checks_total"] >= 33


def test_spec_digest_is_pinned_in_the_report() -> None:
    """The report must declare the digest of the spec bytes, as an equality.

    An earlier version of this test searched the whole report for the first 16
    hex characters of the digest.  That is defeated by the report body itself:
    section 4 documents a mutation run and prints that run's digest, so the
    substring was satisfied by the record of the mutation rather than by the
    header.  Comparing the declared header value to the computed digest cannot
    be satisfied that way.
    """

    digest = hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest()
    declared = _declared_spec_digest()
    assert declared, "the report does not declare a spec digest in its header"
    assert declared == digest


def test_every_manual_citation_is_verbatim_on_its_cited_line(spec: dict, snapshot_lines: list[str]) -> None:
    """Every quoted line must really occur on the line the spec attributes it to."""

    citations: list[dict] = []
    _collect_verbatim_citations(spec, citations)
    assert len(citations) >= 9
    failures = []
    for citation in citations:
        line_number = int(citation["source_line"])
        quoted = _normalise_for_verbatim(str(citation["verbatim"]))
        actual = _normalise_for_verbatim(snapshot_lines[line_number - 1])
        if quoted not in actual:
            failures.append((line_number, str(citation["verbatim"])[:60]))
    assert not failures, failures


def test_random_row_mae_and_r2_match_the_disk_summary(spec: dict) -> None:
    """0.93689 and 0.74813 are R2; the MAE pair is 0.064 and 0.175."""

    measured = spec["evaluation_protocol"]["random_row"]["measured_on_disk"]
    assert measured["metric"] == "log10_cP"
    summary = json.loads(
        (REPOSITORY_ROOT / "probes" / "viscosity_baseline_summary.json").read_text(encoding="utf-8")
    )
    for split in ("random_row", "group_key"):
        on_disk = summary["splits"][split]["models"]["MorganTemperatureXGBoost"]["log10_cP"]
        assert measured[split]["mae"] == on_disk["mae"]
        assert measured[split]["r2"] == on_disk["r2"]
        assert measured[split]["group_overlap"] == summary["splits"][split]["group_overlap"]
    assert round(measured["random_row"]["mae"], 3) == 0.064
    assert round(measured["group_key"]["mae"], 3) == 0.175
    assert round(measured["random_row"]["r2"], 5) == 0.93689
    assert round(measured["group_key"]["r2"], 5) == 0.74813
