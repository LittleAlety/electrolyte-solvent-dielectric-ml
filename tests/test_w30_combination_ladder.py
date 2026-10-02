# Guards for the Week 30 combination / interaction ladder.
#
# By Week 29 all four capacity keys had their own single-key reading, and the four
# side arms inside the Week 20-4 grid sit within 0.0033 of each other -- inside seed
# noise.  What had never been run is a combination.  Week 30 therefore does not
# re-price single keys; it fits six fixed configurations once each on the frozen folds
# and carries three reproduction anchors so the whole code path is checked against
# Weeks 20, 28 and 29 before anything is reported.
#
# The guards pin what makes the readings citable:
#
#   * the pre-registration was locked before the production run, no threshold moved,
#     and the summary quotes its sha256;
#   * the three anchors reproduce the frozen constants to tolerance;
#   * every configuration only overrides the seven declared ladder columns, so
#     subsample / objective / tree_method / n_jobs can never drift;
#   * every fold is pooled once per repeat, with no selection anywhere;
#   * the shot ledger moves by exactly one, to seventeen.
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w30_combination_ladder as w30

ARTIFACTS = ROOT / 'probes' / 'artifacts'
REPEATS_CSV = ARTIFACTS / 'w30_combination_ladder_repeats.csv'
FIG = ARTIFACTS / 'w30_combination_ladder.png'
PREREG = ROOT / 'probes' / 'w30_combination_ladder_prereg.json'
SUMMARY = ROOT / 'probes' / 'w30_combination_ladder_summary.json'
REPORT = ROOT / 'reports' / 'w30_combination_ladder.md'
CRLF = bytes([13, 10])
BOM = bytes([239, 187, 191])

CONFIG_LABELS = (
    'frozen_d2',
    'w29_bin128_d2',
    'w20_4_registered_d4',
    'bin128_mcw5_d2',
    'bin128_n400_lr02_d2',
    'd4_mcw5_bin128_l200',
)
NEW_LABELS = ('bin128_mcw5_d2', 'bin128_n400_lr02_d2', 'd4_mcw5_bin128_l200')
VERDICT_IDS = tuple('H30' + letter for letter in 'abcdefghi')


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list:
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_prereg_is_locked_before_the_run_and_no_threshold_moved() -> None:
    payload = json.loads(PREREG.read_text(encoding='utf-8'))
    assert payload['status'] == 'locked_before_run'
    assert payload['revision'] == 1
    assert payload['smoke_pilot_evidence']['thresholds_moved'] is False
    assert payload['revision_note']['thresholds_moved'] is False
    assert payload['bars'] == {'reproduction': 1e-09, 'cross_check': 0.000001,
                               'gate_r2': 0.6, 'seeds_beating': 4, 'ceiling_slack': 0.005}
    assert tuple(entry['label'] for entry in payload['configs']) == CONFIG_LABELS
    assert tuple(payload['criteria']) == VERDICT_IDS
    assert payload['new_combination_indices'] == [3, 4, 5]
    assert payload['seeds'] == list(w30.SEEDS)
    assert payload['shot_accounting']['lanes'] == 1
    assert payload['shot_accounting']['this_week'] == 1
    assert payload['shot_accounting']['cumulative_after'] == 17


def test_only_the_declared_ladder_columns_ever_move() -> None:
    assert w30.LADDER_COLUMNS == ('max_depth', 'n_estimators', 'learning_rate',
                                 'min_child_weight', 'colsample_bytree', 'max_bin',
                                 'reg_lambda')
    for index in range(len(w30.CONFIGS)):
        overrides = w30.CONFIGS[index][1]
        assert set(overrides) <= set(w30.LADDER_COLUMNS), index
        assert set(overrides) == set(w30.LADDER_COLUMNS), index
        assert overrides['colsample_bytree'] == 0.8, index
        params = w30.params_for(index)
        assert set(params) == set(w30.XGB_PARAMS) | {'min_child_weight', 'random_state'}
        assert params['random_state'] == 42
        for key in ('subsample', 'objective', 'tree_method', 'n_jobs'):
            assert params[key] == w30.XGB_PARAMS[key], (index, key)
    frozen = w30.params_for(w30.FROZEN_INDEX)
    for key, value in w30.XGB_PARAMS.items():
        assert frozen[key] == value
    assert frozen['min_child_weight'] == 1


def test_summary_quotes_the_prereg_bytes_and_the_frozen_configuration() -> None:
    summary = _summary()
    assert summary['schema'] == w30.SCHEMA
    assert summary['task'] == w30.TASK
    assert summary['preregistration']['status'] == 'locked_before_run'
    assert summary['preregistration']['revision'] == 1
    assert summary['preregistration']['sha256'] == _digest(PREREG)
    assert summary['seeds'] == [42, 1234, 2026, 31337, 7]
    assert summary['fit_seed'] == 42
    assert summary['frozen_index'] == 0
    assert summary['frozen_params'] == w30.XGB_PARAMS
    assert [entry['label'] for entry in summary['configs']] == list(CONFIG_LABELS)
    assert summary['new_combination_indices'] == [3, 4, 5]


def test_the_three_reproduction_anchors_hold_to_tolerance() -> None:
    readings = _summary()['readings']
    assert readings['anchor_seed42'] == pytest.approx(0.6080587938801277, abs=1e-09)
    assert readings['anchor_seed42_gap'] <= w30.REPRODUCTION_TOLERANCE
    assert readings['frozen_mean'] == pytest.approx(0.5861142332208197, abs=1e-06)
    assert readings['frozen_gap'] <= w30.CROSS_CHECK_TOLERANCE
    assert readings['w29_mean'] == pytest.approx(0.6031674542995844, abs=1e-06)
    assert readings['w29_gap'] <= w30.CROSS_CHECK_TOLERANCE
    assert readings['w20_mean'] == pytest.approx(0.6216672295270079, abs=1e-06)
    assert readings['w20_gap'] <= w30.CROSS_CHECK_TOLERANCE
    assert readings['w29_expected'] == 0.6031674542995844
    assert readings['w20_expected'] == 0.6216672295270079


def test_the_shot_ledger_moves_by_exactly_one_to_seventeen() -> None:
    summary = _summary()
    assert summary['main_scoreboard_attempts_delta'] == 1
    assert summary['cumulative_main_scoreboard_attempts'] == 17
    assert w30.SCOREBOARD_SHOTS_THIS_WEEK == 1
    assert w30.CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS == 17
    notes = ' '.join(summary['notes'])
    assert '0.5861142332208197' in notes
    assert '0.6216672295270079' in notes


def test_every_verdict_id_is_present_and_ordered() -> None:
    verdicts = _summary()['verdicts']
    assert tuple(entry['id'] for entry in verdicts) == VERDICT_IDS
    for entry in verdicts:
        assert entry['verdict'] in ('成立', '判否')
        assert entry['description']


def test_the_leakage_audit_is_clean_on_every_seed() -> None:
    leakage = _summary()['leakage']
    assert set(leakage) == {'42', '1234', '2026', '31337', '7'}
    for key, block in leakage.items():
        assert block['folds'] == 50, key
        assert block['folds_with_a_straddling_compound'] == 0, key
        assert block['max_straddling_compounds_in_a_fold'] == 0, key
    assert _summary()['readings']['leak_folds'] == 0


def test_repeats_table_carries_every_configuration_on_every_seed() -> None:
    rows = _rows(REPEATS_CSV)
    assert set(rows[0]) == {'seed', 'arm', 'repeat', *w30.METRIC_COLUMNS}
    assert 'auc_gt15' in w30.METRIC_COLUMNS
    assert 'auc_gt30' in w30.METRIC_COLUMNS
    assert set(w30.METRIC_COLUMNS) == set(w30.w28.METRIC_COLUMNS)
    expected = {w30.ARM_PREFIX + label for label in CONFIG_LABELS}
    assert {row['arm'] for row in rows} == expected
    for label in CONFIG_LABELS:
        block = [row for row in rows if row['arm'] == w30.ARM_PREFIX + label]
        assert len(block) == 5 * 10, label
        assert {row['seed'] for row in block} == {'42', '1234', '2026', '31337', '7'}
        assert {row['repeat'] for row in block} == {str(index) for index in range(10)}
        for row in block:
            float(row['r2'])
            float(row['auc_gt30'])
    payload = REPEATS_CSV.read_bytes()
    assert not payload.startswith(BOM)
    assert CRLF not in payload


def test_the_best_new_combination_is_the_reported_one_and_margins_are_consistent() -> None:
    summary = _summary()
    cross = summary['cross_seed']
    assert set(cross) == set(CONFIG_LABELS)
    best_new = max(NEW_LABELS, key=lambda label: cross[label])
    readings = summary['readings']
    assert readings['best_new_label'] == best_new
    assert readings['best_new_mean'] == pytest.approx(cross[best_new], abs=1e-12)
    assert readings['best_new_delta'] == pytest.approx(
        cross[best_new] - cross[CONFIG_LABELS[1]], abs=1e-12)
    best_all = max(CONFIG_LABELS, key=lambda label: cross[label])
    assert readings['global_best_label'] == best_all
    assert readings['ceiling_delta'] == pytest.approx(
        cross[best_all] - w30.W20_4_REGISTERED, abs=1e-12)
    beating = [seed for seed, block in summary['per_seed'].items()
               if block[best_new] > block[CONFIG_LABELS[1]]]
    assert readings['seeds_beating_w29'] == len(beating)


def test_the_pool_is_the_frozen_one_and_no_feature_was_added() -> None:
    summary = _summary()
    assert summary['pool']['rows'] == 2391
    assert summary['pool']['scored_rows'] == 457
    assert summary['pool']['scored_compounds'] == 97
    assert summary['pool']['matches_preregistration'] is True
    assert w30.SCOREBOARD_ROWS == 457
    assert w30.SCOREBOARD_COMPOUNDS == 97


def test_figure_is_written_and_is_not_trivial() -> None:
    assert FIG.is_file()
    assert FIG.stat().st_size > 20000
    assert FIG.read_bytes()[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
    summary = _summary()
    assert summary['figures']['main'] == FIG.name
    assert summary['figures']['written'] is True


def test_report_exists_and_names_the_level_of_every_reading() -> None:
    text = REPORT.read_text(encoding='utf-8')
    assert 'locked_before_run' in text
    assert '主记分牌 shot：1' in text
    assert '0.60' in text
    assert '组合' in text
    assert 'max_bin' in text