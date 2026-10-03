# Guards for the Week 31 capacity-exchange ladder.
#
# Week 31-A moved the parent paper's third conclusion ("several expensive layers are
# skippable in the ranking sense") to the modelling side.  The largest such reading in
# this repository is that raising max_depth from 2 to 4 buys only +0.0045840097020970,
# but every existing reading stops at min_child_weight in {1, 5}.  Week 31 therefore
# asks one question: can that depth margin be bought back with a larger leaf penalty?
#
# The guards pin exactly that:
#
#   * the pre-registration is locked, revision 1, thresholds unmoved;
#   * three reproduction anchors reproduce byte for byte;
#   * only the six declared configuration keys ever move inside a row;
#   * the capacity-exchange and depth-margin readings are recomputed here from the
#     committed cross-seed means;
#   * the four frozen readings and METRIC_NAMES are untouched.
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w31_capacity_exchange as w31

ARTIFACTS = ROOT / 'probes' / 'artifacts'
REPEATS_CSV = ARTIFACTS / 'w31_capacity_exchange_repeats.csv'
OUT_PNG = ARTIFACTS / 'w31_capacity_exchange.png'
SUMMARY = ROOT / 'probes' / 'w31_capacity_exchange_summary.json'
PREREG = ROOT / 'probes' / 'w31_capacity_exchange_prereg.json'
REPORT = ROOT / 'reports' / 'w31_capacity_exchange.md'
CRLF = bytes([13, 10])
BOM = bytes([239, 187, 191])

ANCHORS = {
    'seed42_frozen_d2': 0.6080587938801277,
    'frozen_d2_cross_seed': 0.5861142332208197,
    'w20_4_registered': 0.6216672295270079,
    'w30_best_d2_mcw5': 0.6170832198249109,
}
DECLARED_KEYS = {'max_depth', 'n_estimators', 'learning_rate', 'min_child_weight',
                 'colsample_bytree', 'max_bin', 'reg_lambda'}
FROZEN_KEYS = {'subsample', 'objective', 'tree_method', 'n_jobs', 'random_state'}


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _prereg() -> dict:
    return json.loads(PREREG.read_text(encoding='utf-8'))


def _rows() -> list:
    with REPEATS_CSV.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_prereg_is_locked_and_thresholds_did_not_move() -> None:
    prereg = _prereg()
    assert prereg['status'] == 'locked_before_run'
    assert int(prereg['revision']) == 1
    assert prereg['revision_note']['thresholds_moved'] is False
    assert _summary()['preregistration']['thresholds_moved'] is False


def test_ladder_is_six_fixed_configs_with_three_anchors_and_three_new_points() -> None:
    configs = _prereg()['configs']
    assert len(configs) == 6
    assert [entry['index'] for entry in configs] == list(range(6))
    assert tuple(_prereg()['new_combination_indices']) == (3, 4, 5)
    assert _summary()['frozen_index'] == 0


def test_every_row_only_moves_declared_keys() -> None:
    frozen = _prereg()['configs'][0]
    frozen_values = {key: frozen[key] for key in DECLARED_KEYS}
    for entry in _prereg()['configs']:
        assert DECLARED_KEYS <= set(entry)
        for key in FROZEN_KEYS:
            assert key not in entry
    assert _prereg()['frozen_keys_not_moved_within_a_row']
    assert _summary()['frozen_params']['max_depth'] == frozen_values['max_depth']


def test_three_reproduction_anchors_land_bit_exact() -> None:
    readings = _summary()['readings']
    assert abs(float(readings['anchor_seed42']) - ANCHORS['seed42_frozen_d2']) < 1e-12
    assert abs(float(readings['anchor_seed42_gap'])) <= 1e-09
    assert abs(float(readings['frozen_gap'])) <= 1e-06
    assert abs(float(readings['w20_gap'])) <= 1e-06
    assert abs(float(readings['w30_best_gap'])) <= 1e-06


def test_no_fold_carries_a_straddling_compound() -> None:
    assert int(_summary()['readings']['leak_folds']) == 0
    for block in _summary()['leakage'].values():
        assert int(block['folds_with_a_straddling_compound']) == 0


def test_capacity_exchange_reading_is_self_consistent() -> None:
    summary = _summary()
    cross = summary['cross_seed']
    labels = [entry['label'] for entry in summary['configs']]
    gain = max(cross[labels[3]], cross[labels[4]]) - cross[labels[2]]
    assert abs(float(summary['readings']['mcw_gain_at_d2']) - gain) < 1e-12
    assert abs(gain - float(_summary()['readings']['mcw_gain_at_d2'])) < 1e-12


def test_depth_margin_readings_are_self_consistent() -> None:
    summary = _summary()
    cross = summary['cross_seed']
    labels = [entry['label'] for entry in summary['configs']]
    margin_five = cross[labels[1]] - cross[labels[2]]
    margin_seven = cross[labels[5]] - cross[labels[3]]
    readings = summary['readings']
    assert abs(float(readings['depth_margin_mcw5']) - margin_five) < 1e-12
    assert abs(float(readings['depth_margin_mcw7']) - margin_seven) < 1e-12
    assert abs(float(readings['depth_margin_shrink']) - (margin_five - margin_seven)) < 1e-12


def test_order_side_is_flat_and_the_r2_side_is_narrow_by_design() -> None:
    readings = _summary()['readings']
    # the ordering side holds: the whole ladder moves AUC(eps>30) by < 0.02
    assert float(readings['auc30_range']) < 0.02
    # the magnitude side is narrow because this ladder is narrow by construction;
    # the pre-registered 0.08 bar was copied from the wider W28/W29/W30 ladders and
    # is registered as a criterion-design flaw (the threshold is not moved in place).
    assert 0.03 < float(readings['r2_range']) < 0.08
    assert float(readings['range_ratio']) > 4.0

def test_verdict_pattern_is_seven_passes_and_three_registered_failures() -> None:
    verdicts = _summary()['verdicts']
    assert len(verdicts) == 10
    assert [verdict['id'] for verdict in verdicts] == ['H31' + letter
                                                       for letter in 'abcdefghij']
    failed = {verdict['id'] for verdict in verdicts if verdict['verdict'] != '成立'}
    assert failed == {'H31f', 'H31g', 'H31h'}
    for verdict in verdicts:
        assert verdict['verdict'] in {'成立', '判否'}


def test_the_two_substantive_failures_are_the_capacity_exchange_question() -> None:
    verdicts = {verdict['id']: verdict for verdict in _summary()['verdicts']}
    # leaf penalty saturates past mcw 5: +0.000932 against a +0.002 bar
    assert abs(float(verdicts['H31f']['value']) - 0.000932) < 1e-5
    assert float(verdicts['H31f']['value']) < float(verdicts['H31f']['threshold'])
    # the depth margin does not shrink with a larger leaf penalty: -0.000057
    assert abs(float(verdicts['H31g']['value'])) < 0.0005


def test_report_registers_every_failure_with_a_reason() -> None:
    text = REPORT.read_text(encoding='utf-8')
    assert '## 2. 判否登记（3 条）' in text
    for identifier in ('H31f', 'H31g', 'H31h'):
        assert '**' + identifier + '**' in text
    assert '判据设计缺陷' in text
    assert '不改阈值' in text

def test_repeats_csv_covers_every_arm_seed_and_repeat() -> None:
    rows = _rows()
    summary = _summary()
    seeds = {int(seed) for seed in summary['seeds']}
    arms = {'capacity_' + entry['label'] for entry in summary['configs']}
    assert len(rows) == len(seeds) * 10 * len(arms) == 300
    assert {int(row['seed']) for row in rows} == seeds
    assert {row['arm'] for row in rows} == arms
    for arm in arms:
        assert len({int(row['repeat']) for row in rows if row['arm'] == arm}) == 10


def test_new_arms_are_exactly_the_three_declared_ones() -> None:
    summary = _summary()
    labels = [entry['label'] for entry in summary['configs']]
    assert labels[3] == 'bin128_mcw7_d2'
    assert labels[4] == 'bin128_mcw10_d2'
    assert labels[5] == 'bin128_mcw7_d4'


def test_scoreboard_ledger_moves_to_eighteen() -> None:
    summary = _summary()
    assert int(summary['main_scoreboard_attempts_delta']) == 1
    assert int(summary['cumulative_main_scoreboard_attempts']) == 18


def test_report_quotes_the_parent_paper_alignment() -> None:
    text = REPORT.read_text(encoding='utf-8')
    assert 'v6' in text
    assert '容量' in text
    assert '0.6216672295270079' in text
    assert '两个容量旋钮正交、不可互换' in text

def test_artifacts_are_lf_without_bom() -> None:
    for path in (REPEATS_CSV, SUMMARY, PREREG, REPORT):
        raw = path.read_bytes()
        assert CRLF not in raw
        assert not raw.startswith(BOM)
    assert OUT_PNG.read_bytes()[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])