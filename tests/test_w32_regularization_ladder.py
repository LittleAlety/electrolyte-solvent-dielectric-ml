# Guards for the Week 32-B regularization ladder (shot 19).
#
# Week 29 and Week 30 both concluded that "regularization is carrying the load" without
# ever sweeping it: colsample_bytree had been read at the frozen 0.8 and at 1.0 (both
# drops), and subsample had never moved off 0.8.  Week 32-B therefore holds the W20-4
# registered arm fixed as the base and sweeps one column-sampling curve and one
# row-sampling curve, with four reproduction anchors proving the code path did not move.
#
# The guards pin exactly that:
#
#   * the pre-registration is locked before the run and no threshold moved;
#   * the four anchors reproduce bit for bit (including the seed-42 reading);
#   * the nine configurations only touch the eight declared keys;
#   * the ladder takes exactly one shot and the four frozen readings are untouched;
#   * the ordering criterion is the ratio form that the Week 31 report asked for.
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w32_regularization_ladder as ladder

PREREG = ROOT / 'probes' / 'w32_regularization_ladder_prereg.json'
SUMMARY = ROOT / 'probes' / 'w32_regularization_ladder_summary.json'
REPEATS = ROOT / 'probes' / 'artifacts' / 'w32_regularization_ladder_repeats.csv'
REPORT = ROOT / 'reports' / 'w32_regularization_ladder.md'

FROZEN_READINGS = {
    'frozen_baseline': 0.4091179943351143,
    'frozen_headline': 0.4766400383507876,
    'single_representation_cross_seed': 0.5861142332208197,
    'w20_4_promoted_arm': 0.6216672295270079,
}
DECLARED_KEYS = {'max_depth', 'n_estimators', 'learning_rate', 'min_child_weight',
                 'colsample_bytree', 'subsample', 'max_bin', 'reg_lambda'}


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _repeats() -> list[dict]:
    with REPEATS.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def test_prereg_is_locked_before_the_run() -> None:
    prereg = json.loads(PREREG.read_text(encoding='utf-8'))
    assert prereg['status'] == 'locked_before_run'
    assert int(prereg['revision']) == 1
    assert prereg['revision_note']['thresholds_moved'] is False
    assert [item['id'] for item in prereg['criteria']] == [
        'H32a', 'H32b', 'H32c', 'H32d', 'H32e', 'H32f', 'H32g', 'H32h', 'H32i', 'H32j']
    assert int(prereg['shots']['cumulative']) == 19


def test_the_probe_reuses_the_week31_fitting_path() -> None:
    import w31_capacity_exchange as w31
    assert ladder.ladder is w31
    assert ladder.ladder.CONFIGS is ladder.CONFIGS
    assert ladder.ladder.ARM_PREFIX == 'regularization_'


def test_nine_configs_touch_only_the_declared_keys() -> None:
    payload = _summary()
    labels = [entry['label'] for entry in payload['configs']]
    assert len(labels) == 9
    assert labels[:3] == ['anch_frozen_d2', 'anch_w20_4_registered_d4_mcw5',
                          'anch_w31_fixed_bin128_mcw7_d4']
    for entry in payload['configs']:
        assert set(entry['overrides']) <= DECLARED_KEYS, entry['label']
    frozen = {tuple(sorted(entry['overrides'].items())) for entry in payload['configs'][1:]}
    assert len(frozen) == 8


def test_four_reproduction_anchors_hit_bit_for_bit() -> None:
    readings = _summary()['readings']
    assert abs(float(readings['anchor_seed42_gap'])) <= 1e-09
    assert float(readings['anchor_seed42']) == 0.6080587938801277
    assert abs(float(readings['frozen_gap'])) <= 1e-06
    assert float(readings['frozen_mean']) == 0.5861142332208197
    assert abs(float(readings['registered_gap'])) <= 1e-06
    assert float(readings['registered_mean']) == 0.6216672295270079
    assert abs(float(readings['w31_fixed_gap'])) <= 1e-06
    assert float(readings['w31_fixed_mean']) == 0.6223892738254433


def test_no_fold_lets_a_compound_straddle() -> None:
    payload = _summary()
    assert int(payload['readings']['leak_folds']) == 0
    assert all(int(block['folds']) == 50 for block in payload['leakage'].values())
    assert all(int(block['max_straddling_compounds_in_a_fold']) == 0
               for block in payload['leakage'].values())


def test_ten_verdicts_and_the_ratio_form_of_the_ordering_criterion() -> None:
    payload = _summary()
    identifiers = [verdict['id'] for verdict in payload['verdicts']]
    assert identifiers == ['H32a', 'H32b', 'H32c', 'H32d', 'H32e',
                           'H32f', 'H32g', 'H32h', 'H32i', 'H32j']
    ordering = [verdict for verdict in payload['verdicts'] if verdict['id'] == 'H32i'][0]
    assert '比值' in ordering['description']
    assert abs(float(ordering['value']) - float(payload['readings']['auc_gt30_range'])) < 1e-12
    assert float(payload['readings']['range_ratio']) > 0.0


def test_repeats_table_is_five_seeds_by_nine_arms_by_ten_repeats() -> None:
    rows = _repeats()
    assert len(rows) == 5 * 9 * 10
    assert {int(row['seed']) for row in rows} == {42, 1234, 2026, 31337, 7}
    assert len({row['arm'] for row in rows}) == 9
    assert all(row['arm'].startswith('regularization_') for row in rows)
    assert {int(row['repeat']) for row in rows} == set(range(10))


def test_the_ladder_takes_one_shot_and_the_frozen_readings_do_not_move() -> None:
    payload = _summary()
    assert int(payload['main_scoreboard_attempts_delta']) == 1
    assert int(payload['cumulative_main_scoreboard_attempts']) == 19
    assert payload['pool'] == {'scoreboard_rows': 457, 'scoreboard_compounds': 97,
                               'training_mask': 'full_base'}
    assert int(payload['fit_seed']) == 42
    assert payload['seeds'] == [42, 1234, 2026, 31337, 7]


def test_both_regularization_curves_are_complete() -> None:
    readings = _summary()['readings']
    assert sorted(readings['colsample_curve']) == ['0.8', '0.9', '1.0']
    assert sorted(readings['subsample_curve']) == ['0.6', '0.7', '0.8', '0.9', '1.0']
    assert readings['colsample_curve']['0.8'] == readings['subsample_curve']['0.8']
    assert readings['colsample_gap_09'] == (readings['colsample_curve']['0.9']
                                            - readings['colsample_curve']['0.8'])
    assert float(readings['subsample_best_gain_vs_registered']) == (
        float(readings['subsample_best_mean']) - float(readings['registered_mean']))


def test_text_artifacts_are_lf_without_bom() -> None:
    for path in (SUMMARY, REPEATS, REPORT):
        raw = path.read_bytes()
        assert not raw.startswith(bytes([239, 187, 191])), path.name
        assert bytes([13, 10]) not in raw, path.name
    assert (ROOT / 'probes' / 'artifacts' / 'w32_regularization_ladder.png').is_file()


def test_frozen_readings_of_earlier_weeks_are_quoted_verbatim() -> None:
    prereg = json.loads(PREREG.read_text(encoding='utf-8'))
    assert prereg['frozen_before_run']['frozen_readings'] == FROZEN_READINGS
