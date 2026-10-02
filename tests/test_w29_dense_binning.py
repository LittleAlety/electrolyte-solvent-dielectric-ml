# Guards for the Week 29 dense-block binning and column-sampling ladder.
#
# Week 28 moved max_depth / n_estimators / learning_rate and froze max_bin = 64,
# colsample_bytree = 0.8 and reg_lambda = 1.0 as "not moved".  Those three keys are
# capacity and regularisation knobs in the same sense as depth: 64 bins on a thirteen
# column dense float block means every split searches 63 candidate thresholds per
# feature, and colsample_bytree = 0.8 drops about three of the thirteen columns from
# every tree.  Week 29 is a fixed ladder over exactly those three keys, with the frozen
# depth / trees / learning rate held still.
#
# The guards pin what makes the readings citable:
#
#   * the pre-registration was locked before the production run and the summary quotes
#     its sha256;
#   * the frozen configuration is grid entry 0, so the anchor and the ladder share one
#     code path, and the anchor reproduces the frozen constants bit for bit;
#   * no configuration touches anything but the three declared keys;
#   * every fold is pooled once per repeat, with no selection anywhere;
#   * the shot ledger moves by exactly one and the four frozen readings do not.
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

import w29_dense_binning as w29

ARTIFACTS = ROOT / 'probes' / 'artifacts'
REPEATS_CSV = ARTIFACTS / 'w29_dense_binning_repeats.csv'
FIG = ARTIFACTS / 'w29_dense_binning.png'
PREREG = ROOT / 'probes' / 'w29_dense_binning_prereg.json'
SUMMARY = ROOT / 'probes' / 'w29_dense_binning_summary.json'
REPORT = ROOT / 'reports' / 'w29_dense_binning.md'
CRLF = bytes([13, 10])
BOM = bytes([239, 187, 191])

FROZEN_READINGS = (
    0.4091179943351143,
    0.4766400383507876,
    0.5861142332208197,
    0.6216672295270079,
)
CONFIG_LABELS = (
    'frozen_bin64_cs08_l1',
    'fine_bin128_cs08_l1',
    'fine_bin256_cs08_l1',
    'full_cols_bin64_cs10_l1',
    'loose_lambda_bin64_cs08_l01',
    'all_three_bin256_cs10_l01',
)
VERDICT_IDS = ('H29a', 'H29b', 'H29c', 'H29d', 'H29e', 'H29f')


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
    assert payload['bars'] == {'reproduction': 1e-09, 'w28_cross_check': 0.000001,
                               'gate_r2': 0.6, 'seeds_beating': 4}
    assert tuple(entry['label'] for entry in payload['configs']) == CONFIG_LABELS
    assert tuple(payload['criteria']) == VERDICT_IDS
    assert payload['seeds'] == list(w29.SEEDS)
    assert payload['shot_accounting']['lanes'] == 1
    assert payload['shot_accounting']['this_week'] == 1
    assert payload['shot_accounting']['cumulative_after'] == 16


def test_only_the_three_declared_keys_move() -> None:
    frozen = w29.params_for(w29.FROZEN_INDEX)
    for key, value in w29.XGB_PARAMS.items():
        assert frozen[key] == value
    assert frozen['random_state'] == 42
    declared = {'max_bin', 'colsample_bytree', 'reg_lambda'}
    for index in range(len(w29.CONFIGS)):
        params = w29.params_for(index)
        assert set(params) == set(w29.XGB_PARAMS) | {'random_state'}
        moved = {key for key in params
                 if key in w29.XGB_PARAMS and params[key] != w29.XGB_PARAMS[key]}
        assert moved <= declared, (index, moved)
        assert params['max_depth'] == w29.XGB_PARAMS['max_depth']
        assert params['n_estimators'] == w29.XGB_PARAMS['n_estimators']
        assert params['learning_rate'] == w29.XGB_PARAMS['learning_rate']
    seen = {(w29.CONFIGS[index][1]['max_bin'],
             w29.CONFIGS[index][1]['colsample_bytree'],
             w29.CONFIGS[index][1]['reg_lambda']) for index in range(len(w29.CONFIGS))}
    assert len(seen) == len(w29.CONFIGS)


def test_summary_quotes_the_prereg_bytes_and_the_frozen_configuration() -> None:
    summary = _summary()
    assert summary['schema'] == w29.SCHEMA
    assert summary['task'] == w29.TASK
    assert summary['preregistration']['status'] == 'locked_before_run'
    assert summary['preregistration']['revision'] == 1
    assert summary['preregistration']['sha256'] == _digest(PREREG)
    assert summary['seeds'] == [42, 1234, 2026, 31337, 7]
    assert summary['fit_seed'] == 42
    assert summary['frozen_index'] == 0
    assert summary['frozen_params'] == w29.XGB_PARAMS
    assert [entry['label'] for entry in summary['configs']] == list(CONFIG_LABELS)


def test_the_anchor_and_the_week_28_cross_check_hold() -> None:
    readings = _summary()['readings']
    assert readings['anchor_seed42'] == pytest.approx(0.6080587938801277, abs=1e-09)
    assert readings['anchor_seed42_gap'] is not None
    assert readings['anchor_seed42_gap'] <= w29.REPRODUCTION_TOLERANCE
    assert readings['frozen_label'] == CONFIG_LABELS[0]
    assert readings['frozen_mean'] == pytest.approx(0.5861142332208197, abs=1e-06)
    assert readings['w28_gap'] <= w29.W28_CROSS_CHECK_TOLERANCE
    assert readings['w28_expected'] == 0.5861142332208197


def test_the_shot_ledger_moves_by_exactly_one() -> None:
    summary = _summary()
    assert summary['main_scoreboard_attempts_delta'] == 1
    assert summary['cumulative_main_scoreboard_attempts'] == 16
    assert w29.SCOREBOARD_SHOTS_THIS_WEEK == 1
    assert w29.CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS == 16
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
    assert set(rows[0]) == {'seed', 'arm', 'repeat', *w29.METRIC_COLUMNS}
    assert set(w29.METRIC_COLUMNS) == set(w29.w28.METRIC_COLUMNS)
    expected = {w29.ARM_PREFIX + label for label in CONFIG_LABELS}
    assert {row['arm'] for row in rows} == expected
    for label in CONFIG_LABELS:
        block = [row for row in rows if row['arm'] == w29.ARM_PREFIX + label]
        assert len(block) == 5 * 10, label
        assert {row['seed'] for row in block} == {'42', '1234', '2026', '31337', '7'}
        assert {row['repeat'] for row in block} == {str(index) for index in range(10)}
        for row in block:
            float(row['r2'])
            float(row['mae'])
    payload = REPEATS_CSV.read_bytes()
    assert not payload.startswith(BOM)
    assert CRLF not in payload


def test_the_best_entry_is_the_reported_one_and_the_margins_are_consistent() -> None:
    summary = _summary()
    cross = summary['cross_seed']
    assert set(cross) == set(CONFIG_LABELS)
    best = max(cross, key=lambda label: cross[label])
    assert summary['best_config'] == best
    readings = summary['readings']
    assert readings['best_mean'] == pytest.approx(cross[best], abs=1e-12)
    assert readings['best_delta'] == pytest.approx(
        cross[best] - cross[CONFIG_LABELS[0]], abs=1e-12)
    frozen = CONFIG_LABELS[0]
    beating = [seed for seed, block in summary['per_seed'].items()
               if block[best] > block[frozen]]
    assert readings['seeds_beating_frozen'] == len(beating)


def test_the_pool_is_the_frozen_one_and_no_feature_was_added() -> None:
    summary = _summary()
    assert summary['pool']['rows'] == 2391
    assert summary['pool']['scored_rows'] == 457
    assert summary['pool']['scored_compounds'] == 97
    assert summary['pool']['matches_preregistration'] is True
    assert w29.SCOREBOARD_ROWS == 457
    assert w29.SCOREBOARD_COMPOUNDS == 97
    assert all(len(w29.CONFIGS[index][1]) == 3 for index in range(len(w29.CONFIGS)))


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
    assert '阶梯' in text
    assert 'max_bin' in text
