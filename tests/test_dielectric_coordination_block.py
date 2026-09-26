"""Guards for the lever-8 Li+ coordination block probe.

The probe appends five xTB-derived columns beside the frozen 13-column v03
physical block and re-runs the frozen main scoreboard in three arms (baseline,
plus the block, and a shuffled-target placebo). These tests pin everything that
must not drift: the pre-registration digest and its red lines, the reproduced
baseline, the frozen fold numbers, the placebo behaviour, the LF-only release
format of every artefact, and the fact that no frozen column or frozen file was
touched.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from probes.dielectric_coordination_block import (
    ARTIFACT_STEM,
    ARTIFACTS_DIR,
    BASELINE_R2,
    COORDINATION_COLUMNS,
    FEATURES_ARTIFACT,
    FROZEN_XTB_CACHE,
    HYBRID,
    KILL_DELTA,
    PASS_DELTA,
    PHYSICAL_COLUMNS,
    PLACEBO_TOLERANCE,
    PREREG_PATH,
    REPORT_PATH,
    REPRODUCTION_TOLERANCE,
    SCOREBOARD_COMPOUNDS,
    SCOREBOARD_ROWS,
    SUMMARY_PATH,
    XTB_BUDGET_SECONDS,
    XTB_WORK_ROOT,
    _same_as_released,
    build_scoreboard,
    cation_site_index,
    check_artifacts,
    format_report,
    frozen_solvent_references,
    internal_problems,
    resolve_solvent_run,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

FEATURE_TABLE = ARTIFACTS_DIR / (FEATURES_ARTIFACT + ".csv")
FOLD_TABLE = ARTIFACTS_DIR / (ARTIFACT_STEM + "_folds.csv")
PREDICTION_TABLE = ARTIFACTS_DIR / (ARTIFACT_STEM + "_predictions.csv")
REPEAT_TABLE = ARTIFACTS_DIR / (ARTIFACT_STEM + "_repeats.csv")

RELEASED_ARTIFACTS = (FEATURE_TABLE, FOLD_TABLE, PREDICTION_TABLE, REPEAT_TABLE)

#: A compound whose cached run is unambiguous, used for the resolver unit tests.
SINGLE_RUN_KEY = "AFBPFSWMIHJQDM-UHFFFAOYSA-N"

#: The nine compounds with no O and no N: the pre-registered site rule leaves
#: their block undefined rather than filling it.
NO_SITE_KEYS = (
    "BKIMMITUMNQMOS-UHFFFAOYSA-N",
    "FYIRUPZTYPILDH-UHFFFAOYSA-N",
    "IMNFDUFMRHMDMM-UHFFFAOYSA-N",
    "TVMXDCGIABBOFY-UHFFFAOYSA-N",
    "UAEPNZWRGJTJPN-UHFFFAOYSA-N",
    "WZLFPVPRZGTCKP-UHFFFAOYSA-N",
    "XDTMQSROBMDMFD-UHFFFAOYSA-N",
    "YFMFNYKEUDLDTL-UHFFFAOYSA-N",
    "YXFVVABEGXRONW-UHFFFAOYSA-N",
)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def feature_rows() -> list[dict[str, str]]:
    return read_rows(FEATURE_TABLE)


@pytest.fixture(scope="module")
def scoreboard() -> dict:
    return build_scoreboard()


# --------------------------------------------------------------------------- #
# release format
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", RELEASED_ARTIFACTS, ids=lambda path: path.name)
def test_released_csv_is_lf_only_and_carries_no_bom(path: Path) -> None:
    blob = path.read_bytes()
    assert b"\r\n" not in blob
    assert not blob.startswith(b"\xef\xbb\xbf")


def test_released_report_is_lf_only_and_carries_no_bom() -> None:
    blob = REPORT_PATH.read_bytes()
    assert b"\r\n" not in blob
    assert not blob.startswith(b"\xef\xbb\xbf")


def test_every_declared_output_exists(summary: dict) -> None:
    for name, relative in summary["outputs"].items():
        assert (REPOSITORY_ROOT / relative).is_file(), name


# --------------------------------------------------------------------------- #
# the frozen contract: pre-registration, red lines, untouched inputs
# --------------------------------------------------------------------------- #


def test_preregistration_digest_is_the_locked_one(summary: dict) -> None:
    recorded = summary["preregistration"]
    assert recorded["path"] == "probes/dielectric_coordination_block_prereg.json"
    assert recorded["sha256"] == sha256_of(PREREG_PATH)


def test_frozen_red_line_files_still_carry_their_preregistered_digests() -> None:
    locked = json.loads(PREREG_PATH.read_text(encoding="utf-8"))["frozen_red_lines_untouched"]
    assert locked, "the pre-registration must name its red lines"
    for entry in locked:
        relative, _, digest = entry.partition(" digest ")
        assert digest, entry
        assert sha256_of(REPOSITORY_ROOT / relative) == digest, relative


def test_the_read_inputs_are_untouched(summary: dict) -> None:
    inputs = summary["inputs"]
    for key in ("observations", "frozen_features", "new_features"):
        assert sha256_of(REPOSITORY_ROOT / inputs[key]) == inputs[key + "_sha256"], key


def test_the_probe_did_not_overwrite_the_frozen_feature_blocks(summary: dict) -> None:
    # The new block lives in its own file; neither frozen feature table moves.
    inputs = summary["inputs"]
    assert inputs["frozen_features"] == "data/processed/dielectric_physical_features_v03.csv"
    assert inputs["new_features"] == "data/processed/dielectric_physical_features_v11plus_new.csv"
    assert sha256_of(FEATURE_TABLE) == inputs["feature_table_sha256"]


def test_the_block_never_reuses_a_frozen_column_name() -> None:
    assert set(COORDINATION_COLUMNS).isdisjoint(PHYSICAL_COLUMNS)
    header = next(csv.reader(FEATURE_TABLE.open(encoding="utf-8", newline="")))
    assert list(COORDINATION_COLUMNS) == [
        column for column in header if column in set(COORDINATION_COLUMNS)
    ]
    for column in COORDINATION_COLUMNS:
        assert column not in PHYSICAL_COLUMNS


def test_internal_feature_table_consistency_is_clean(feature_rows: list[dict[str, str]]) -> None:
    assert internal_problems(feature_rows) == []


# --------------------------------------------------------------------------- #
# the frozen scoreboard and its fold numbers
# --------------------------------------------------------------------------- #


def test_scoreboard_is_the_frozen_457_rows_and_97_compounds(scoreboard: dict) -> None:
    contract = scoreboard["contract"]
    assert contract["scored_rows"] == SCOREBOARD_ROWS == 457
    assert contract["compounds_scored"] == SCOREBOARD_COMPOUNDS == 97
    assert contract["folds"] == 50
    assert contract["executed_repeats"] == 10
    assert contract["matches_preregistration"] is True
    assert contract["folds_with_a_straddling_compound"] == 0
    assert contract["scored_rows_outside_the_score_mask"] == 0


def test_summary_scoreboard_agrees_with_the_rebuilt_one(summary: dict, scoreboard: dict) -> None:
    assert summary["scoreboard"] == scoreboard["contract"]


def test_fold_table_is_the_frozen_split_not_a_new_one(scoreboard: dict) -> None:
    rows = read_rows(FOLD_TABLE)
    assert len(rows) == 50 * len(("Morgan", "Physical", "Morgan+Physical")) * 3
    splits = scoreboard["splits"]
    assert len(splits) == 50
    for row in rows:
        index = int(row["repeat"]) * 5 + int(row["fold"])
        repeat, fold, train_index, test_index = splits[index]
        assert (repeat, fold) == (int(row["repeat"]), int(row["fold"]))
        assert int(row["train_rows"]) == len(train_index)
        assert int(row["test_rows"]) == len(test_index)
    for arm in ("baseline", "plus_coordination_block", "placebo_shuffled_target"):
        sizes = {
            (row["repeat"], row["fold"], row["train_rows"], row["test_rows"])
            for row in rows
            if row["arm"] == arm and row["representation"] == "Morgan+Physical"
        }
        assert len(sizes) == 50


def test_repeat_table_covers_every_arm_and_representation() -> None:
    rows = read_rows(REPEAT_TABLE)
    assert len(rows) == 3 * 3 * 10
    assert {(row["arm"], row["representation"]) for row in rows} == {
        (arm, representation)
        for arm in ("baseline", "plus_coordination_block", "placebo_shuffled_target")
        for representation in ("Morgan", "Physical", "Morgan+Physical")
    }


def test_predictions_carry_the_scored_pool_only() -> None:
    rows = read_rows(PREDICTION_TABLE)
    # one row per (arm, representation, repeat, fold, scored row)
    assert len(rows) == 3 * 3 * 10 * SCOREBOARD_ROWS
    assert len({row["inchikey"] for row in rows}) == SCOREBOARD_COMPOUNDS
    folds = read_rows(FOLD_TABLE)
    fold_ids = {
        (row["arm"], row["representation"], row["repeat"], row["fold"]) for row in folds
    }
    prediction_ids = {
        (row["arm"], row["representation"], row["repeat"], row["fold"]) for row in rows
    }
    assert prediction_ids == fold_ids
    # every prediction row sits inside the test fold it was made in
    sizes = {(row["repeat"], row["fold"]): int(row["test_rows"]) for row in folds}
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        if row["arm"] == "baseline" and row["representation"] == "Morgan":
            key = (row["repeat"], row["fold"])
            counts[key] = counts.get(key, 0) + 1
    assert counts == sizes


# --------------------------------------------------------------------------- #
# the verdict
# --------------------------------------------------------------------------- #


def test_baseline_reproduction_guard(summary: dict) -> None:
    baseline = summary["arms"]["baseline"][HYBRID]["r2"]["mean"]
    assert abs(baseline - BASELINE_R2) <= REPRODUCTION_TOLERANCE
    verdict = summary["verdict"]
    assert verdict["baseline_reproduced"] is True
    assert verdict["integrity_ok"] is True
    assert verdict["baseline_abs_delta"] <= REPRODUCTION_TOLERANCE


def test_the_recorded_delta_is_the_arm_difference(summary: dict) -> None:
    arms = summary["arms"]
    baseline = arms["baseline"][HYBRID]["r2"]["mean"]
    plus = arms["plus_coordination_block"][HYBRID]["r2"]["mean"]
    assert abs((plus - baseline) - summary["verdict"]["delta_r2"]) <= 1e-12
    assert summary["verdict"]["primary_met"] is (summary["verdict"]["delta_r2"] >= PASS_DELTA)


def test_placebo_collapses_to_the_trivial_predictor(summary: dict) -> None:
    """A shuffled target must lose the signal, not keep it."""

    arms = summary["arms"]
    baseline = arms["baseline"][HYBRID]["r2"]["mean"]
    placebo = arms["placebo_shuffled_target"][HYBRID]["r2"]["mean"]
    # No lift: the placebo is at or below the mean predictor, and far below the
    # baseline. Anything else would mean the block was reading the target.
    assert placebo <= 0.02
    assert baseline - placebo > PASS_DELTA
    assert summary["placebo"]["r2"] == placebo
    assert summary["placebo"]["tolerance"] == PLACEBO_TOLERANCE


def test_the_placebo_clause_reading_is_recorded_not_reinterpreted(summary: dict) -> None:
    """The frozen clause is `|delta R2| <= 0.02` against the baseline arm.

    Read literally that inequality can only hold when the placebo keeps the
    baseline's signal, so it is unsatisfiable whenever the placebo collapses.
    The probe implements it literally, records `collapsed: False`, and therefore
    reports `dead` even though the pass bar itself was met. This test pins that
    state so the ambiguity cannot be quietly resolved after the fact.
    """

    baseline = summary["arms"]["baseline"][HYBRID]["r2"]["mean"]
    placebo = summary["arms"]["placebo_shuffled_target"][HYBRID]["r2"]["mean"]
    assert abs((placebo - baseline) - summary["placebo"]["delta_r2_vs_baseline"]) <= 1e-12
    assert summary["placebo"]["collapsed"] is (abs(placebo - baseline) <= PLACEBO_TOLERANCE)
    assert summary["placebo"]["collapsed"] is False
    assert summary["verdict"]["primary_met"] is True
    assert summary["verdict"]["mae_gt60_not_worse"] is True
    assert summary["verdict"]["decision"] == "dead"
    assert summary["verdict"]["kill_reasons"] == [
        "the placebo arm moved R2 by -0.4500, beyond +-0.0200"
    ]
    assert summary["verdict"]["delta_r2"] >= PASS_DELTA > KILL_DELTA
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "### Placebo reading (disclosure; no threshold was changed after the run)" in report


def test_report_on_disk_is_the_render_of_the_summary(summary: dict) -> None:
    assert REPORT_PATH.read_text(encoding="utf-8").splitlines() == format_report(summary)


def test_check_artifacts_reports_no_problem_when_the_scratch_is_present() -> None:
    if not XTB_WORK_ROOT.is_dir():
        pytest.skip("the xTB scratch root is not on this machine")
    assert check_artifacts(work_root=XTB_WORK_ROOT) == 0


# --------------------------------------------------------------------------- #
# the xTB budget
# --------------------------------------------------------------------------- #


def test_the_budget_was_not_exceeded_and_no_pilot_was_needed(summary: dict) -> None:
    xtb = summary["xtb"]
    assert xtb["within_budget"] is True
    assert xtb["budget_seconds"] == XTB_BUDGET_SECONDS
    # Every requested compound was attempted, so there is no pending remainder.
    assert xtb["compounds_requested"] == SCOREBOARD_COMPOUNDS
    assert xtb["compounds_ok"] + xtb["compounds_failed"] == xtb["compounds_requested"]
    assert xtb["status_counts"] == {"ok": 88, "undefined_no_hetero_site": 9}


def test_the_measured_cost_is_the_sum_of_the_per_compound_seconds(
    summary: dict, feature_rows: list[dict[str, str]]
) -> None:
    measured = sum(float(row["xtb_seconds"]) for row in feature_rows)
    assert abs(measured - summary["xtb"]["xtb_cpu_seconds"]) <= 0.05
    assert measured < XTB_BUDGET_SECONDS


# --------------------------------------------------------------------------- #
# the resolver, against the frozen cache
# --------------------------------------------------------------------------- #


def test_same_as_released_compares_through_the_released_serialization() -> None:
    # The frozen table writes `%.8g`, so `103.445901` is released as `103.4459`.
    # An absolute tolerance would call that a mismatch; the run identifier must not.
    assert _same_as_released(103.445901, 103.4459) is True
    assert abs(103.445901 - 103.4459) > 1e-09
    # A genuine disagreement in the eighth significant digit is still a mismatch.
    assert _same_as_released(103.44591, 103.4459) is False
    assert _same_as_released(1.915, 1.915) is True


def test_frozen_solvent_references_read_the_released_v03_table() -> None:
    references = frozen_solvent_references()
    assert len(references) >= 237
    reference = references[SINGLE_RUN_KEY]
    assert set(reference) == {"polarizability_au", "dipole_D", "total_energy_hartree"}
    assert reference["polarizability_au"] > 0


def test_resolve_solvent_run_identifies_one_cached_run() -> None:
    if not FROZEN_XTB_CACHE.is_dir():
        pytest.skip("the frozen xTB cache is not on this machine")
    reference = frozen_solvent_references()[SINGLE_RUN_KEY]
    resolved = resolve_solvent_run(SINGLE_RUN_KEY, reference)
    assert resolved["considered"] >= 1
    assert len(resolved["matches"]) == 1
    assert resolved["match_basis"] == "polarizability_au+dipole_D"
    assert resolved["run"] is not None
    # The relaxed energy comes from the same run and differs from the released
    # column, which the frozen parser takes from the pre-relaxation banner.
    assert resolved["relaxed_energy_hartree"] is not None


def test_every_resolved_run_is_matched_by_the_run_identifier(
    feature_rows: list[dict[str, str]],
) -> None:
    bases = {row["solvent_match_basis"] for row in feature_rows if row["status"] == "ok"}
    assert bases == {"polarizability_au+dipole_D"}
    assert all(int(row["solvent_run_matches"]) == 1 for row in feature_rows if row["status"] == "ok")


# --------------------------------------------------------------------------- #
# the undefined block
# --------------------------------------------------------------------------- #


def test_compounds_without_a_site_are_undefined_not_zero(
    feature_rows: list[dict[str, str]],
) -> None:
    by_key = {row["inchikey"]: row for row in feature_rows}
    assert set(NO_SITE_KEYS) <= set(by_key)
    for key in NO_SITE_KEYS:
        row = by_key[key]
        assert row["status"] == "undefined_no_hetero_site"
        assert row["error"]
        for column in COORDINATION_COLUMNS:
            assert row[column] == "", (key, column)


def test_the_undefined_rows_really_have_no_o_and_no_n(
    feature_rows: list[dict[str, str]],
) -> None:
    by_key = {row["inchikey"]: row for row in feature_rows}
    for key in NO_SITE_KEYS:
        assert cation_site_index(by_key[key]["smiles"]) is None
    # And a compound that does have a site is found by the same rule.
    assert cation_site_index("COCCOC") is not None


def test_the_undefined_rows_are_reported_in_the_summary(summary: dict) -> None:
    block = summary["coordination_block"]
    assert block["compounds_ok"] == 88
    assert block["compounds_failed"] == len(NO_SITE_KEYS)
    assert tuple(block["failed_keys"]) == NO_SITE_KEYS
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "pilot scale: no bounded pilot was needed" in report
    assert "pending list: empty" in report
