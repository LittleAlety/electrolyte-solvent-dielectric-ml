"""Guards for the L3 back-validation stage-1 pilot (dielectric channel, EC/PC).

The pilot is an in-roster, dielectric-only dry run of the L3 funnel.  These
tests pin the things that make it honest and auditable:

* the pool digest and pool size, and the fact that the pool was frozen to disk
  before the scoring summary was written;
* the seven locked constants of ``probes/l3_backvalidation_prereg.json``;
* the exact readout convention behind C1 (top-20 by descending predicted
  epsilon, ties broken by InChIKey) and behind C2_solvent
  (``|delta log10 epsilon| <= 0.10`` against the pinned 90.5 / 64.9);
* that C3 and C2_additive are declared *not run*, not quietly implied;
* that the regression anchor still reproduces the frozen benchmark;
* that EC and PC left every training side while FEC and VC needed no such
  exclusion because they were never inside the frozen dielectric fit;
* that every artifact carries ``stage_1_pilot_not_a_verdict``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import pathlib

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_summary.json"
POOL_PATH = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_pool.csv"
DETAIL_PATH = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_detail.csv"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "l3_backvalidation_prereg.json"
FROZEN_TABLE = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
ANCHOR_SUMMARY = REPOSITORY_ROOT / "probes" / "v032_target_scaffold_summary.json"
ANCHOR_ABLATION = REPOSITORY_ROOT / "probes" / "v032_ablation_summary.json"
RESERVED_RUN_SUMMARY = REPOSITORY_ROOT / "probes" / "l3_backvalidation_run_summary.json"
REPORT = REPOSITORY_ROOT / "reports" / "l3_stage1_pilot.md"
DECISIONS_LOG = REPOSITORY_ROOT / "reports" / "decisions_log.md"
DECISIONS_LOG_SECTION = "## 2026-09-26 · Week 12 §17"

PILOT_LABEL = "stage_1_pilot_not_a_verdict"
POOL_SHA256 = "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"
POOL_ROWS = 236
MIN_SCORED_PER_LIST = 100

EC_INCHIKEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"
PC_INCHIKEY = "RUOJZAUFBMNUDX-UHFFFAOYSA-N"
FEC_INCHIKEY = "SBLRHMKNNHXPHG-UHFFFAOYSA-N"
VC_INCHIKEY = "VAYTZRYEBVHVLE-UHFFFAOYSA-N"
TRUTH_DIELECTRIC = {"EC": 90.5, "PC": 64.9}
TRUTH_T_K = {"EC": 313.15, "PC": 298.15}

K = 20
C2_TOLERANCE = 0.10
C2_ADDITIVE_TOLERANCE = 0.15
C3_PERMUTATION_SEED = 20260928
C3_MAX_CHAMPION_HITS = 1
LOCKED_CONSTANTS = {
    "C1_K": K,
    "C1_champions_required_in_top_k_total": 4,
    "C2_solvent_max_abs_delta_log10_epsilon": C2_TOLERANCE,
    "C2_additive_max_abs_delta_ev": C2_ADDITIVE_TOLERANCE,
    "C3_permutation_seed": C3_PERMUTATION_SEED,
    "C3_max_champion_hits": C3_MAX_CHAMPION_HITS,
    "min_scored_per_list": MIN_SCORED_PER_LIST,
}
ALLOWED_DOMAIN_FLAGS = {
    "inside_domain",
    "outside_associated_liquid",
    "outside_nonphysical",
}
ANCHOR_TOLERANCE = 1e-9


def _read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_rows(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _summary() -> dict:
    return _read_json(SUMMARY_PATH)


def _prereg() -> dict:
    return _read_json(PREREG_PATH)


def _decisions_section(heading: str) -> str:
    text = DECISIONS_LOG.read_text(encoding="utf-8")
    start = text.index(heading)
    tail = text[start + len(heading):]
    end = tail.find("\n## ")
    return tail if end == -1 else tail[:end]


def test_pool_digest_and_size_are_pinned_everywhere() -> None:
    digest = hashlib.sha256(POOL_PATH.read_bytes()).hexdigest()
    assert digest == POOL_SHA256
    summary = _summary()
    assert summary["pool"]["sha256"] == POOL_SHA256
    assert summary["pool"]["rows"] == POOL_ROWS
    assert summary["pool"]["size_by_list"] == {"solvent": POOL_ROWS}
    prereg_pool = _prereg()["pool_rule"]
    assert prereg_pool["pool_sha256"] == POOL_SHA256
    assert prereg_pool["pool_path"] == "probes/l3_stage1_pilot_pool.csv"
    assert prereg_pool["pool_size_by_list"] == {"solvent": POOL_ROWS}
    assert POOL_ROWS >= prereg_pool["min_scored_per_list"]
    assert len(_read_rows(POOL_PATH)) == POOL_ROWS


def test_pool_file_is_lf_only_so_the_digest_cannot_be_argued_about() -> None:
    raw = POOL_PATH.read_bytes()
    assert b"\r" not in raw
    canonical = hashlib.sha256(
        raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    ).hexdigest()
    assert canonical == hashlib.sha256(raw).hexdigest() == POOL_SHA256


def test_pool_was_frozen_before_the_scoring_summary_was_written() -> None:
    summary = _summary()
    assert summary["pool"]["frozen_before_scoring"] is True
    assert summary["pool_rule_runtime_fill"]["pool_frozen_before_scoring"] is True
    assert summary["summary_written_after_pool"] is True
    assert _prereg()["pool_rule"]["pool_frozen_before_scoring"] is True
    assert POOL_PATH.stat().st_mtime <= SUMMARY_PATH.stat().st_mtime


def test_pool_holds_the_two_solvent_champions_as_ordinary_members() -> None:
    rows = _read_rows(POOL_PATH)
    by_key = {row["inchikey"]: row for row in rows}
    champions = [row for row in rows if row["is_champion"] == "true"]
    assert sorted(row["inchikey"] for row in champions) == sorted([EC_INCHIKEY, PC_INCHIKEY])
    assert {row["champion_short"] for row in champions} == {"EC", "PC"}
    for inchikey in (EC_INCHIKEY, PC_INCHIKEY):
        row = by_key[inchikey]
        assert row["list"] == "solvent"
        assert row["model_ready"] == "true"
        assert row["pilot_label"] == PILOT_LABEL
    assert FEC_INCHIKEY not in by_key
    assert VC_INCHIKEY not in by_key


def test_additive_champions_are_declared_outside_the_pool_without_exclusion() -> None:
    declaration = _summary()["exclusion"]["additive_champions"]
    assert set(declaration) == {"FEC", "VC"}
    for short, inchikey in (("FEC", FEC_INCHIKEY), ("VC", VC_INCHIKEY)):
        entry = declaration[short]
        assert entry["inchikey"] == inchikey
        assert entry["model_ready"] is False
        assert entry["already_withheld_from_dielectric_fit"] is True
        assert entry["present_in_pool"] is False
        assert entry["extra_exclusion_needed"] is False
    assert "NOT four leave-one-outs" in _summary()["exclusion"]["asymmetry_statement"]


def test_ec_and_pc_left_every_training_side_of_every_fold() -> None:
    audit = _summary()["exclusion"]["audit"]
    assert audit["split_count"] == 50
    for short in ("EC", "PC"):
        entry = audit["per_champion"][short]
        assert entry["train_side_removals"] == 40
        assert entry["held_out_folds"] == 10
    assert audit["min_train_rows_after_exclusion"] == 186
    assert audit["max_train_rows_after_exclusion"] <= POOL_ROWS - 5


def test_temperature_check_is_read_off_the_frozen_table() -> None:
    frozen = {row["inchikey"]: row for row in _read_rows(FROZEN_TABLE)}
    temperature = _summary()["temperature_check"]
    for short, inchikey in (("EC", EC_INCHIKEY), ("PC", PC_INCHIKEY)):
        entry = temperature[short]
        assert float(frozen[inchikey]["T_K"]) == TRUTH_T_K[short]
        assert entry["prereg_truth_T_K"] == TRUTH_T_K[short]
        assert entry["frozen_table_T_K"] == TRUTH_T_K[short]
        assert entry["consistent"] is True


def test_the_seven_locked_constants_are_untouched() -> None:
    prereg = _prereg()
    criteria = prereg["criteria"]
    assert criteria["C1_recall_at_K"]["K"] == K
    assert criteria["C1_recall_at_K"]["champions_required_in_top_k_total"] == 4
    assert criteria["C2_magnitude_solvent"]["max_abs_delta_log10_epsilon"] == C2_TOLERANCE
    assert criteria["C2_additive"]["max_abs_delta_ev"] == C2_ADDITIVE_TOLERANCE
    assert criteria["C3_negative_control"]["permutation_seed"] == C3_PERMUTATION_SEED
    assert criteria["C3_negative_control"]["max_champion_hits"] == C3_MAX_CHAMPION_HITS
    assert prereg["pool_rule"]["min_scored_per_list"] == MIN_SCORED_PER_LIST
    assert criteria["pass_expression"] == "C1 and C2_solvent and C2_additive and C3"
    reported = _summary()["prereg"]["locked_constants_read_verbatim"]
    assert {key: reported[key] for key in LOCKED_CONSTANTS} == LOCKED_CONSTANTS
    assert reported["pass_expression"] == "C1 and C2_solvent and C2_additive and C3"

def test_pool_rule_amendment_2_adds_metadata_only() -> None:
    pool_rule = _prereg()["pool_rule"]
    amendment = pool_rule["amendment_2"]
    assert amendment["kind"] == "runtime_field_fill_only"
    assert amendment["locked_values_unchanged"] is True
    assert amendment["locked_values_touched"] == []
    assert pool_rule["amendment_1"]["locked_values_unchanged"] is True


def test_c1_readout_reproduces_the_locked_top_20_convention() -> None:
    rows = _read_rows(DETAIL_PATH)
    assert len(rows) == POOL_ROWS
    predicted = {row["inchikey"]: float(row["predicted_dielectric"]) for row in rows}
    expected_order = sorted(predicted, key=lambda key: (-predicted[key], key))
    reported = sorted(rows, key=lambda row: int(row["rank"]))
    assert [row["inchikey"] for row in reported] == expected_order
    assert sorted(int(row["rank"]) for row in rows) == list(range(1, POOL_ROWS + 1))
    top = [row for row in rows if row["in_top20"] == "true"]
    assert len(top) == K
    assert {row["inchikey"] for row in top} == set(expected_order[:K])
    assert all(int(row["rank"]) <= K for row in top)

    summary_c1 = _summary()["readings"]["C1_recall_at_K"]
    assert summary_c1["K"] == K
    assert summary_c1["top_k_inchikeys"] == expected_order[:K]
    ranks = summary_c1["champion_ranks_in_dielectric_solvent_list"]
    assert ranks == {
        short: int(next(row["rank"] for row in rows if row["champion_short"] == short))
        for short in ("EC", "PC")
    }
    hits = sum(1 for short in ("EC", "PC") if ranks[short] <= K)
    assert summary_c1["hits_in_dielectric_solvent_list"] == hits
    assert summary_c1["passed_in_this_channel"] is (hits == 2)
    assert summary_c1["not_a_verdict"] is True
    assert summary_c1["champions_required_total_prereg_four_channels"] == 4
    assert summary_c1["champions_required_here_dielectric_solvent_list"] == 2


def test_the_locked_readout_is_the_log_target_and_raw_is_only_diagnostic() -> None:
    summary = _summary()
    assert "log_epsilon_minus_one" in summary["readout_recipe"]["ranking_readout"]
    locked = summary["readouts"]["log_epsilon_minus_one"]
    diagnostic = summary["readouts"]["raw"]
    assert locked["role"] == "locked_readout"
    assert diagnostic["role"] == "diagnostic_only_not_the_locked_readout"
    assert locked["fold_aggregation"] == "mean_over_the_10_out_of_fold_repeat_predictions"
    assert locked["pool_size"] == POOL_ROWS
    assert diagnostic["pool_size"] == POOL_ROWS
    assert locked["target_mode"] != diagnostic["target_mode"]


def test_c2_solvent_readout_uses_the_locked_log10_ratio() -> None:
    rows = {
        row["champion_short"]: row
        for row in _read_rows(DETAIL_PATH)
        if row["champion_short"]
    }
    assert set(rows) == {"EC", "PC"}
    summary = _summary()["readings"]["C2_magnitude_solvent"]
    assert summary["max_abs_delta_log10_epsilon"] == C2_TOLERANCE
    for short in ("EC", "PC"):
        reported = summary["champions"][short]
        row = rows[short]
        predicted = float(row["predicted_dielectric"])
        truth = float(row["target_dielectric"])
        assert truth == TRUTH_DIELECTRIC[short] == reported["truth_dielectric"]
        assert math.isclose(
            reported["predicted_dielectric"], predicted, rel_tol=1e-11, abs_tol=1e-11
        )
        expected = abs(math.log10(predicted / truth))
        assert math.isclose(
            reported["abs_delta_log10"], expected, rel_tol=1e-12, abs_tol=1e-12
        )
        assert reported["within_tolerance"] is (expected <= C2_TOLERANCE)
        assert reported["domain_flag"] in ALLOWED_DOMAIN_FLAGS
        assert math.isclose(
            float(row["abs_delta_log10_vs_truth"]), expected, rel_tol=1e-12, abs_tol=1e-12
        )
    assert summary["passed_in_this_channel"] is all(
        summary["champions"][short]["within_tolerance"] for short in ("EC", "PC")
    )
    assert summary["not_a_verdict"] is True


def test_c3_and_c2_additive_are_declared_not_run() -> None:
    readings = _summary()["readings"]
    assert readings["C3_negative_control"]["status"] == "c3_not_run_stage_1_pilot"
    assert readings["C3_negative_control"]["permutation_seed_locked"] == C3_PERMUTATION_SEED
    assert readings["C3_negative_control"]["max_champion_hits_locked"] == C3_MAX_CHAMPION_HITS
    additive = readings["C2_additive"]
    assert additive["status"] == "not_run_stage_1_pilot_redox_channel_not_executed"
    assert additive["max_abs_delta_ev"] == C2_ADDITIVE_TOLERANCE
    assert "verdict" not in readings
    assert "pass" not in readings


def test_regression_anchor_reproduces_the_frozen_benchmark() -> None:
    anchor = _summary()["regression_anchor"]
    assert anchor["status"] == "aligned"
    assert anchor["max_abs_metric_diff"] <= ANCHOR_TOLERANCE
    assert anchor["row_values_compared"] == 6 * POOL_ROWS * 10
    assert anchor["row_value_mismatches"] == []
    assert anchor["no_champion_excluded_here"] is True
    frozen = _read_json(ANCHOR_SUMMARY)["summary"]["random_repeated_kfold"]
    ablation = _read_json(ANCHOR_ABLATION)["summary"]
    for target_mode in ("raw", "log_epsilon_minus_one"):
        for representation in ("Morgan", "Physical", "Morgan+Physical"):
            arm = anchor["arms"][f"{target_mode}::{representation}"]
            assert arm["aligned"] is True
            assert arm["max_abs_diff"] <= ANCHOR_TOLERANCE
            for metric, mine in arm["mine"].items():
                reference = frozen[target_mode][representation][metric]["mean"]
                assert abs(mine - reference) <= ANCHOR_TOLERANCE
                if target_mode == "raw":
                    other = ablation[representation][metric]["mean"]
                    assert (
                        abs(mine - other)
                        <= anchor["crosscheck_tolerance_abs"]
                        <= ANCHOR_TOLERANCE * 1000
                    )
                    assert arm["ablation_crosscheck"]["within_tolerance"] is True
            if target_mode == "raw":
                assert arm["ablation_crosscheck"]["reference"].endswith(
                    "v032_ablation_summary.json"
                )


def test_detail_csv_carries_the_required_columns_and_three_state_flags() -> None:
    header = DETAIL_PATH.read_text(encoding="utf-8").splitlines()[0].split(",")
    for column in (
        "inchikey",
        "predicted_dielectric",
        "domain_flag",
        "is_champion",
        "in_top20",
        "fold_aggregation",
        "rank",
        "pilot_label",
    ):
        assert column in header, f"detail CSV lost the {column!r} column"
    rows = _read_rows(DETAIL_PATH)
    assert len(rows) == POOL_ROWS
    assert {row["domain_flag"] for row in rows} <= ALLOWED_DOMAIN_FLAGS
    assert all(
        row["fold_aggregation"] == "mean_over_the_10_out_of_fold_repeat_predictions"
        for row in rows
    )
    assert all(row["n_repeats"] == "10" for row in rows)
    assert all(row["pilot_label"] == PILOT_LABEL for row in rows)
    assert sum(1 for row in rows if row["in_top20"] == "true") == K


def test_stage_1_pilot_label_is_on_every_artifact() -> None:
    for path in (SUMMARY_PATH, DETAIL_PATH, POOL_PATH, REPORT):
        assert PILOT_LABEL in path.read_text(encoding="utf-8"), (
            f"{path.name} lost the {PILOT_LABEL} label"
        )
    assert PILOT_LABEL in _decisions_section(DECISIONS_LOG_SECTION)
    assert _summary()["label"] == PILOT_LABEL
    report = REPORT.read_text(encoding="utf-8")
    assert "不是判决" in report


def test_the_pilot_cannot_be_read_as_the_l3_verdict() -> None:
    summary = _summary()
    assert summary["not_a_verdict"] is True
    assert summary["verdict_eligible"] is False
    assert _prereg()["stage_1_pilot"]["verdict_eligible"] is False
    assert summary["readings"]["C1_recall_at_K"]["not_a_verdict"] is True
    assert summary["readings"]["C2_magnitude_solvent"]["not_a_verdict"] is True
    assert not RESERVED_RUN_SUMMARY.exists()