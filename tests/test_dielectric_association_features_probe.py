"""Guards for the lever-2 association blind-spot feature probe.

These tests pin what makes the lever auditable rather than self-serving:

* the six descriptors are recomputed here from SMILES and checked against
  hand-derived answers (methanol really does have one donor, glycol really does
  have a donor-acceptor pair inside three bonds);
* the six column names are the pre-registration's own list, read from the file
  rather than restated from memory;
* the judged thresholds are the literals frozen in the pre-registration, and the
  reference R2 is the published `paired_base` reading;
* the main scoreboard is re-derived from the frozen tables - 457 scored rows of
  97 compounds - instead of being trusted to the summary;
* the baseline arm reproduced the published number, and the verdict does not
  claim a pass that the pre-registered criterion would not grant;
* the report file is byte-identical to what the summary renders;
* every artifact is LF-only.
"""

from __future__ import annotations

import csv
import json
import pathlib
import sys

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import dielectric_association_features_probe as probe
import numpy as np
from dielectric_band_ablation import ROOM_BAND
from dielectric_coverage_paired_benchmark import (
    COVERAGE_PATH,
    ZERO_FREQUENCY_ORIGIN,
    load_coverage_table,
    merge_feature_blocks,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "dielectric_r2_levers_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_association_features_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "dielectric_association_features.md"
COVERAGE_SUMMARY_PATH = (
    REPOSITORY_ROOT / "probes" / "dielectric_coverage_paired_benchmark_summary.json"
)


@pytest.fixture(scope="module")
def prereg() -> dict:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def prereg_lever(prereg: dict) -> dict:
    blocks = [block for block in prereg["levers"] if block["id"] == probe.LEVER_ID]
    assert len(blocks) == 1
    return blocks[0]


@pytest.fixture(scope="module")
def summary() -> dict:
    assert SUMMARY_PATH.is_file(), "run probes/dielectric_association_features_probe.py first"
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def test_feature_names_are_the_preregistered_list(prereg_lever: dict) -> None:
    declared = prereg_lever["new_features"]
    for name in probe.ASSOCIATION_FEATURES:
        assert any(name.startswith(declared_name.split(" ")[0]) for declared_name in declared), name
    assert set(probe.ASSOCIATION_FEATURES) == {
        "hbond_donor_sites",
        "hbond_acceptor_sites",
        "donor_site_density",
        "acceptor_site_density",
        "intramolecular_hbond_competition",
        "donor_acceptor_pair_density",
    }


def test_methanol_counts_one_donor_and_one_acceptor() -> None:
    features = probe.association_features_for_smiles("CO")
    assert features is not None
    assert features["hbond_donor_sites"] == 1.0
    assert features["hbond_acceptor_sites"] == 1.0
    assert features["donor_site_density"] == pytest.approx(0.5)
    assert features["acceptor_site_density"] == pytest.approx(0.5)
    assert features["intramolecular_hbond_competition"] == 0.0
    assert features["donor_acceptor_pair_density"] == pytest.approx(0.25)


def test_glycol_has_one_competition_pair_and_glycerol_two() -> None:
    glycol = probe.association_features_for_smiles("OCCO")
    assert glycol is not None
    assert glycol["intramolecular_hbond_competition"] == 1.0
    glycerol = probe.association_features_for_smiles("OCC(O)CO")
    assert glycerol is not None
    assert glycerol["intramolecular_hbond_competition"] == 2.0


def test_a_non_associating_solvent_has_no_donor() -> None:
    features = probe.association_features_for_smiles("CCOC(=O)C")
    assert features is not None
    assert features["hbond_donor_sites"] == 0.0
    assert features["donor_acceptor_pair_density"] == 0.0


def test_unparsable_smiles_returns_none() -> None:
    assert probe.association_features_for_smiles("not a molecule") is None


def test_feature_block_counts_a_parse_failure_instead_of_hiding_it() -> None:
    matrix, report = probe.association_feature_block(["CO", "nonsense("])
    assert matrix.shape == (2, len(probe.ASSOCIATION_FEATURES))
    assert report["parse_failures"] == 1
    assert report["parse_failure_rows"] == [1]
    assert matrix[1].sum() == 0.0


def test_thresholds_are_the_preregistered_literals(prereg_lever: dict, prereg: dict) -> None:
    assert probe.PASS_DELTA_R2 == 0.0200
    assert probe.KILL_DELTA_R2 == 0.0050
    assert probe.CONTROL_COLLAPSE_TOLERANCE == 0.02
    assert "+0.0200" in prereg_lever["pass_criterion"]
    assert "+0.0050" in prereg_lever["kill_line"]
    assert "0.02" in prereg["control_arm"]["rule"]
    assert probe.REFERENCE_R2 == prereg["reference_reading_to_reproduce_first"]["expected"]
    assert (
        probe.REFERENCE_TOLERANCE
        == prereg["reference_reading_to_reproduce_first"]["tolerance"]
    )


def test_reference_r2_is_the_published_paired_base_reading() -> None:
    published = json.loads(COVERAGE_SUMMARY_PATH.read_text(encoding="utf-8"))
    value = published["fixed_pool_family"]["summary"]["paired_base"]["Morgan+Physical"]["r2"]["mean"]
    assert probe.REFERENCE_R2 == pytest.approx(float(value), abs=1e-15)
    for representation, expected in probe.REFERENCE_TRIPLE.items():
        mine = published["fixed_pool_family"]["summary"]["paired_base"][representation]["r2"]["mean"]
        assert expected == pytest.approx(float(mine), abs=1e-15)


def test_main_scoreboard_is_re_derived_from_the_frozen_tables() -> None:
    merged, _report = merge_feature_blocks()
    rows, _dropped = load_coverage_table(COVERAGE_PATH, merged)
    origin = np.asarray([str(row["observation_origin"]) for row in rows])
    band = np.asarray([str(row["temperature_band"]) for row in rows])
    score = (origin == ZERO_FREQUENCY_ORIGIN) & (band == ROOM_BAND)
    keys = np.asarray([str(row["inchikey"]) for row in rows])
    assert int(score.sum()) == probe.SCOREBOARD_ROWS == 457
    assert len(set(keys[score].tolist())) == probe.SCOREBOARD_COMPOUNDS == 97


def test_summary_declares_the_frozen_scoreboard(summary: dict, prereg: dict) -> None:
    scoreboard = summary["main_scoreboard"]
    declared = prereg["main_scoreboard"]
    assert scoreboard["rows_scored"] == declared["rows_scored"] == 457
    assert scoreboard["compounds_scored"] == declared["compounds_scored"] == 97
    assert scoreboard["n_splits"] == declared["n_splits"] == 5
    assert scoreboard["n_repeats"] == declared["n_repeats"] == 10
    assert scoreboard["seed"] == declared["seed"] == 42
    assert scoreboard["min_test_rows_per_fold"] == declared["min_test_rows_per_fold"] == 2
    assert scoreboard["folds_measured"] == scoreboard["full_run_folds"] == 50
    assert scoreboard["guards_passed"] is True


def test_baseline_arm_reproduced_the_published_r2(summary: dict) -> None:
    reproduced = summary["baseline_reproduces"]
    assert reproduced["published_r2"] == probe.REFERENCE_R2
    assert reproduced["abs_difference"] <= probe.REFERENCE_TOLERANCE
    assert reproduced["bit_exact"] is True
    assert summary["reference_triple"]["all_bit_exact"] is True


def test_all_arms_share_the_same_scored_folds(summary: dict) -> None:
    assert summary["shared_folds"]["scored_side_identical"] is True
    for arm in ("baseline", "lever", "control"):
        assert summary["arms"][arm]["audit"]["folds_with_a_straddling_compound"] == 0
        assert summary["arms"][arm]["audit"]["scored_rows_outside_the_score_mask"] == 0
        assert summary["arms"][arm]["meta"]["folds"] == 50


def read_csv_rows(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def scored_rows_by_fold(summary: dict, arm: str) -> dict[tuple[int, int], list[tuple[str, float]]]:
    """Every (compound, temperature) a fold scored, read from the artifact itself."""

    rows = read_csv_rows(REPOSITORY_ROOT / summary["outputs"]["predictions"])
    grouped: dict[tuple[int, int], list[tuple[str, float]]] = {}
    for row in rows:
        if row["protocol"] != arm or row["representation"] != "Morgan+Physical":
            continue
        key = (int(row["repeat"]), int(row["fold"]))
        grouped.setdefault(key, []).append((row["inchikey"], float(row["T_K"])))
    return {key: sorted(value) for key, value in grouped.items()}


def test_the_three_arms_score_the_identical_rows(summary: dict) -> None:
    """The shared-fold claim, checked row by row instead of taken on trust.

    A shared assignment means the scored side of every fold is the *same* set of
    rows in all three arms, so the signatures must be identical - not distinct.
    The claim is re-derived here from the prediction artifact rather than read
    off the summary flag.
    """

    arms = summary["shared_folds"]["arms"]
    baseline = scored_rows_by_fold(summary, arms[0])
    assert baseline and len(baseline) == 50
    for arm in arms[1:]:
        other = scored_rows_by_fold(summary, arm)
        assert set(other) == set(baseline)
        for key, rows in baseline.items():
            assert other[key] == rows, key



def test_control_arm_is_reported_with_every_reference(summary: dict) -> None:
    collapse = summary["control_collapse"]
    assert collapse["tolerance"] == probe.CONTROL_COLLAPSE_TOLERANCE
    assert collapse["trivial_floor_r2"] == pytest.approx(
        summary["readings"][probe.CONTROL_FLOOR_ARM]["DummyMean"]["r2"]["mean"], abs=1e-15
    )
    assert collapse["delta_over_the_floor"] == pytest.approx(
        collapse["control_r2"] - collapse["trivial_floor_r2"], abs=1e-15
    )
    assert collapse["collapsed"] == (
        collapse["delta_over_the_floor"] <= probe.CONTROL_COLLAPSE_TOLERANCE
    )
    assert collapse["literal_wording_is_satisfiable"] == (
        abs(collapse["delta_vs_the_real_label_baseline"]) <= probe.CONTROL_COLLAPSE_TOLERANCE
    )


def test_verdict_never_claims_more_than_the_criterion_grants(summary: dict) -> None:
    verdict = summary["verdict"]
    delta = verdict["delta_r2"]
    assert verdict["decision"] in {"pass", "dead", "sub_threshold", "unverified"}
    if verdict["decision"] == "pass":
        assert delta >= probe.PASS_DELTA_R2
        assert verdict["control_collapsed"] is True
        assert verdict["delta_mae_gt60"] <= 0.0
        assert verdict["carried_into_the_merge_arm"] is True
    if delta < probe.KILL_DELTA_R2:
        assert verdict["decision"] != "pass"
        assert verdict["carried_into_the_merge_arm"] is False
    assert verdict["control_collapse"]["tolerance"] == probe.CONTROL_COLLAPSE_TOLERANCE


def test_lever_delta_equals_the_two_rereadings(summary: dict) -> None:
    readings = summary["readings"]
    hybrid = "Morgan+Physical"
    delta = summary["delta"]["delta_r2"]
    assert delta == pytest.approx(
        readings[probe.LEVER_ARM][hybrid]["r2"]["mean"]
        - readings[probe.BASELINE_ARM][hybrid]["r2"]["mean"],
        abs=1e-15,
    )


def test_report_is_the_rendered_summary(summary: dict) -> None:
    rendered = "\n".join(probe.render_report(summary)) + "\n"
    assert REPORT_PATH.read_text(encoding="utf-8") == rendered


def test_shots_are_counted(summary: dict) -> None:
    assert summary["shots"]["this_lever"] == probe.SHOTS_THIS_LEVER == 1


def test_locked_criteria_come_from_the_preregistration(summary: dict, prereg_lever: dict) -> None:
    locked = summary["locked_criteria"]
    for key in ("pass_criterion", "secondary_criterion", "kill_line"):
        assert locked[key] == prereg_lever[key]
    assert summary["prereg"]["sha256"] == probe.canonical_text_sha256(PREREG_PATH)


def test_every_artifact_is_lf_only(summary: dict) -> None:
    outputs = summary["outputs"]
    for key, relative in outputs.items():
        if not str(relative).endswith(".csv"):
            continue
        raw = (REPOSITORY_ROOT / relative).read_bytes()
        assert b"\r\n" not in raw, key