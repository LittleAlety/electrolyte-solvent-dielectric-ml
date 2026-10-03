# Guards for the Week 40 lane W40-A: the three registered criteria reforms.
#
# W40-A is a post hoc reform lane.  It refits nothing and takes no main-scoreboard
# shot (the cumulative ledger stays at 19).  It re-reads three already-registered
# "criteria reform" items that W37/W38 had left unexecuted:
#   #20  H38a2 -- invert "fix alpha, measure precision" into "largest alpha that
#        still holds precision >= 0.90" (tau=30 => alpha* = 0.06, 10 recommends);
#   #21  H38b1 -- replace the absolute |delta eps| >= 30 gate with a self-normalised
#        decile ratio plus a fingerprint blind-spot count;
#   #1   H31h  -- replace the absolute 0.08 scale gate with a parametric
#        (R2 spread / AUC30 spread) ratio, tested on five clean ladders.
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w40_criteria_reform_summary.json'
INVERSION = ART / 'w40_conformal_inversion.csv'
BINS = ART / 'w40_similarity_bins.csv'
RATIO = ART / 'w40_ladder_ratio.csv'
FIGURE = ART / 'w40_criteria_reform.png'
REPORT = ROOT / 'reports' / 'w40_criteria_reform.md'
PROBE = ROOT / 'probes' / 'w40_criteria_reform.py'
ROSTER = ROOT / 'data' / 'processed' / 'dielectric_physical_features_v03.csv'

ROSTER_SHA256 = 'b36d3439560e4381b7779565b9950eed379832e832b72ea6a3a010662ed24fa3'
PREDICTIONS_SHA256 = '1051249acfafa936b3479ce713cb9e4b06c58c121e9b24ee2ee3d8431118c197'

CRITERIA_IDS = ['H40a' + str(index) for index in range(1, 15)]
REGISTERED_NEGATIVES = ['H40a5']
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
LADDER_LABELS = ['W28 稠密超参阶梯（仅 grid_fixed 网格臂）',
                 'W29 分箱阶梯', 'W30 组合/交互阶梯', 'W31 容量交换阶梯',
                 'W32 正则化阶梯']
LADDER_RATIOS = [21.044061513567584, 13.712270713223267, 8.092207259070127,
                 4.178785477997323, 7.272893976113999]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w40_criteria_reform/summary@1'
    assert payload['task'] == 'week40_criteria_reform'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_fourteen_criteria_with_the_tau15_boundary_registered_as_negative() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    verdicts = {item['id']: item['verdict'] for item in criteria}
    assert [key for key, value in verdicts.items() if value != '成立'] == REGISTERED_NEGATIVES
    assert verdicts['H40a5'] == '判否'
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_budget_inversion_anchor_matches_the_w38_registered_reading() -> None:
    inv30 = _summary()['reforms']['conformal_inversion']['tau30']
    assert inv30['representation'] == 'Physical'
    assert inv30['precision_at_alpha_0p05'] == 1.0
    assert inv30['shortlist_at_alpha_0p05'] == 6
    assert inv30['alpha_star'] == 0.06
    assert inv30['precision_at_star'] == 0.9
    assert inv30['shortlist_at_star'] == 10
    assert inv30['precision_at_alpha_0p20'] == 0.7941176470588235
    assert inv30['shortlist_at_alpha_0p20'] == 34


def test_tau15_has_no_budget_that_holds_the_precision_gate() -> None:
    inv15 = _summary()['reforms']['conformal_inversion']['tau15']
    assert inv15['alpha_star'] is None
    assert inv15['precision_at_star'] is None
    assert inv15['shortlist_at_star'] == 0
    assert inv15['precision_at_alpha_0p05'] == 0.7916666666666666
    assert inv15['shortlist_at_alpha_0p05'] == 24
    assert inv15['precision_at_alpha_0p20'] == 0.7477477477477478


def test_grid_contains_the_registered_anchor_points() -> None:
    grid = _summary()['reforms']['conformal_inversion']['grid']
    assert 0.05 in grid and 0.10 in grid and 0.20 in grid
    assert len(grid) == 16
    assert grid == sorted(grid)


def test_relative_similarity_readings_are_frozen() -> None:
    similarity = _summary()['reforms']['similarity_relative']
    assert similarity['n_compounds'] == 241
    assert similarity['n_pairs'] == 28920
    assert similarity['global_median_abs_delta_eps'] == 9.88
    assert similarity['top_bin_median'] == 6.44
    assert similarity['bottom_bin_median'] == 9.19
    assert similarity['top_bin_ratio'] == 0.6518218623481781
    assert similarity['top_bin_p'] == 0.0
    assert similarity['n_blind'] == 26
    assert similarity['n_blind_big'] == 4
    assert similarity['max_blind_delta'] == 13.252
    assert similarity['top_bin_ratio'] <= 0.80
    assert similarity['bottom_bin_median'] > similarity['top_bin_median']


def test_ladder_ratio_is_measured_on_five_clean_ladders() -> None:
    ladder = _summary()['reforms']['ladder_ratio']
    assert [item['ladder'] for item in ladder] == LADDER_LABELS
    assert [item['ratio'] for item in ladder] == LADDER_RATIOS
    assert [item['n_arms'] for item in ladder] == [6, 6, 6, 6, 9]
    assert all(item['auc30_spread'] < 0.02 for item in ladder)
    assert min(item['ratio'] for item in ladder) >= 4.0
    assert sum(1 for item in ladder if item['ratio'] >= 10.0) >= 2


def test_w28_ladder_drops_the_placebo_and_representation_arms() -> None:
    """The W28 table mixes a placebo arm and lever4_* arms into the grid.

    Left unfiltered its AUC30 spread is 0.5438 rather than 0.0056, which would
    poison the ratio reading.
    """

    with (ART / 'w28_dense_hyperparameters_repeats.csv').open(encoding='utf-8',
                                                              newline='') as handle:
        arms = {row['arm'] for row in csv.DictReader(handle)}
    assert any(arm.startswith('grid_fixed_') for arm in arms)
    assert any(not arm.startswith('grid_fixed_') for arm in arms)
    source = PROBE.read_text(encoding='utf-8')
    assert '"grid_fixed_"' in source


def test_input_sha256s_are_the_frozen_ones() -> None:
    payload = _summary()
    inputs = payload['inputs']
    roster_key = str(ROSTER)
    assert inputs[roster_key] == ROSTER_SHA256
    assert sha256_file(ROSTER) == ROSTER_SHA256
    predictions = [value for key, value in inputs.items()
                   if key.endswith('dielectric_observations_benchmark_predictions.csv')]
    assert predictions == [PREDICTIONS_SHA256]
    assert len(inputs) == 7


def test_probe_reads_only_existing_artifacts_and_writes_stably() -> None:
    source = PROBE.read_text(encoding='utf-8')
    assert 'write_json_stable(SUMMARY_PATH, summary)' in source
    assert 'SUMMARY_PATH.write_text' not in source
    assert 'w29_dense_binning_repeats.csv' in source


def test_artifacts_and_report_exist() -> None:
    assert FIGURE.is_file() and FIGURE.stat().st_size > 0
    assert REPORT.is_file()
    text = REPORT.read_text(encoding='utf-8')
    assert 'H40a5' in text and '判否' in text
    assert '0.6518' in text or '0.651822' in text
    assert '21.04' in text
    assert text.endswith('\n')


def test_csv_artifacts_have_the_expected_shape() -> None:
    inversion = _rows(INVERSION)
    assert len(inversion) == 64
    assert {row['representation'] for row in inversion} == {'Physical', 'Morgan+Physical'}
    assert {float(row['tau']) for row in inversion} == {15.0, 30.0}
    bins = _rows(BINS)
    assert len(bins) == 10
    assert [int(row['bin']) for row in bins] == list(range(1, 11))
    ratio = _rows(RATIO)
    assert len(ratio) == 5
    assert all(float(row['auc30_spread']) < 0.02 for row in ratio)
