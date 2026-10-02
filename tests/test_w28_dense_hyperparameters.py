# Guards for the Week 28 dense-block hyperparameter retune.
#
# Week 27 priced the width penalty: appending the thirteen response columns to
# the dense lever-4 physical block cost 0.096956 in R2, while a row-shuffled
# block of the same width still cost 0.006099, above the 0.005 inert line.
# That residue cannot be information loss -- it is the fit reacting to width,
# and the frozen settings (max_depth 2 / 200 trees / lr 0.05 / max_bin 64)
# were chosen for a 2048-column sparse Morgan block.  Two shots run on the
# frozen pool in this one file:
#
#   * shot 1 -- nested retune: inside every outer fold the training rows are
#     split by compound into three inner folds, each grid entry is scored on
#     the pooled inner holdout, and the winner is refit on the whole outer
#     training set.  The outer test rows never take part in the choice.
#   * shot 2 -- fixed ladder: every grid entry is fit once on the same folds
#     with no selection at all, so whether a better fixed setting exists is
#     answered separately from whether the selector can find it.
#
# The guards pin what makes the two readings citable:
#
#   * the pre-registration was locked before the production run, the summary
#     quotes its sha256, and the smoke pilot moved no threshold;
#   * the seed-42 anchor and the five-seed endpoint reproduce the frozen
#     constants bit for bit, so this fold path is the frozen one;
#   * inner folds only ever touch training rows of their own outer fold;
#   * the ladder carries all six entries for every seed and repeat;
#   * the placebo only shuffles the training target, and the shot ledger
#     moves by exactly two.
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

import w28_dense_hyperparameters as w28

ARTIFACTS = ROOT / 'probes' / 'artifacts'
SELECTION_CSV = ARTIFACTS / 'w28_dense_hyperparameters_selection.csv'
REPEATS_CSV = ARTIFACTS / 'w28_dense_hyperparameters_repeats.csv'
FIG = ARTIFACTS / 'w28_dense_hyperparameters.png'
PREREG = ROOT / 'probes' / 'w28_dense_hyperparameters_prereg.json'
SUMMARY = ROOT / 'probes' / 'w28_dense_hyperparameters_summary.json'
REPORT = ROOT / 'reports' / 'w28_dense_hyperparameters.md'
CRLF = bytes([13, 10])
BOM = bytes([239, 187, 191])

FROZEN_READINGS = (
    0.4091179943351143,
    0.4766400383507876,
    0.5861142332208197,
    0.6216672295270079,
)
GRID_LABELS = (
    'frozen_d2_n200_lr05',
    'deep_d3_n200_lr05',
    'deep_d4_n200_lr05',
    'deep_d3_n400_lr05',
    'deep_d4_n400_lr05',
    'slow_d2_n400_lr02',
)
VERDICT_IDS = ('H28a', 'H28b', 'H28c', 'H28d', 'H28e', 'H28f',
               'H28g', 'H28h', 'H28i', 'H28j', 'H28k')
LADDER_ARMS = tuple(w28.LADDER_ARM_PREFIX + label for label in GRID_LABELS)
METRIC_COLUMNS = ('r2', 'mae', 'rmse', 'spearman', 'auc_gt15', 'auc_gt30',
                  'mae_lt20', 'mae_20_60', 'mae_gt60')


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
    assert payload['bars'] == {'reproduction': 1e-09,
                               'w27_cross_check': 0.000001,
                               'gate_r2': 0.6,
                               'placebo_ceiling': 0,
                               'deep_mode_seeds': 4,
                               'pass_depth': 2}
    assert tuple(entry['label'] for entry in payload['grid']) == GRID_LABELS
    assert len(payload['grid']) == len(w28.GRID)
    assert tuple(payload['criteria']) == VERDICT_IDS
    assert payload['seeds'] == list(w28.SEEDS)
    ledger = payload['shot_accounting']
    assert ledger['lanes'] == 2
    assert ledger['this_week'] == 2
    assert ledger['cumulative_after'] == 15


def test_the_frozen_red_lines_are_recorded_with_their_readings() -> None:
    payload = json.loads(PREREG.read_text(encoding='utf-8'))
    red_lines = ' '.join(payload['red_lines'])
    assert 'METRIC_NAMES' in red_lines
    for frozen in FROZEN_READINGS:
        assert repr(frozen) in red_lines
    assert '不读任何介电常数标签进特征' in red_lines
    assert '缺行不插补' in red_lines


def test_summary_quotes_the_prereg_bytes_and_the_frozen_grid() -> None:
    summary = _summary()
    assert summary['schema'] == w28.SCHEMA
    assert summary['task'] == w28.TASK
    assert summary['preregistration']['status'] == 'locked_before_run'
    assert summary['preregistration']['revision'] == 1
    assert summary['preregistration']['sha256'] == _digest(PREREG)
    assert summary['seeds'] == [42, 1234, 2026, 31337, 7]
    assert summary['fit_seed'] == 42
    assert summary['inner_splits'] == 3
    assert [entry['label'] for entry in summary['grid']] == list(GRID_LABELS)
    assert summary['frozen_params'] == w28.XGB_PARAMS


def test_the_anchor_and_the_five_seed_endpoint_reproduce_the_frozen_constants() -> None:
    readings = _summary()['readings']
    assert readings['anchor_seed42'] == pytest.approx(w28.FROZEN_SINGLE_REPRESENTATION,
                                                      abs=1e-09)
    assert readings['anchor_seed42_gap'] is not None
    assert readings['anchor_seed42_gap'] <= w28.REPRODUCTION_TOLERANCE
    assert readings['frozen_mean'] == pytest.approx(w28.FROZEN_CROSS_SEED, abs=1e-09)
    assert readings['anchor_cross_seed_gap'] is not None
    assert readings['anchor_cross_seed_gap'] <= w28.REPRODUCTION_TOLERANCE
    per_seed = _summary()['per_seed']
    assert per_seed['42']['frozen'] == pytest.approx(0.6080587938801277, abs=1e-09)
    assert set(per_seed) == {'42', '1234', '2026', '31337', '7'}


def test_the_frozen_entry_is_the_shallow_one_the_grid_is_meant_to_beat() -> None:
    assert w28.FROZEN_INDEX == 0
    assert w28.DEPTHS_IN_GRID[0] == w28.PASS_DEPTH_BAR == 2
    frozen = w28.params_for(w28.FROZEN_INDEX)
    for key, value in w28.GRID[0][1].items():
        assert frozen[key] == value
    assert frozen['random_state'] == 42
    for index in range(1, len(w28.GRID)):
        moved = w28.params_for(index)
        assert {key: moved[key] for key in w28.GRID[0][1]} != w28.GRID[0][1]
    assert w28.DEPTHS_IN_GRID[1:] == (3, 4, 3, 4, 2)


def test_the_shot_ledger_moves_by_exactly_two() -> None:
    summary = _summary()
    assert summary['main_scoreboard_attempts_delta'] == 2
    assert summary['cumulative_main_scoreboard_attempts'] == 15
    assert w28.SCOREBOARD_SHOTS_THIS_WEEK == 2
    assert w28.CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS == 15
    notes = ' '.join(summary['notes'])
    for frozen in FROZEN_READINGS:
        assert repr(frozen) in notes


def test_every_verdict_id_is_present_and_ordered() -> None:
    verdicts = _summary()['verdicts']
    assert tuple(entry['id'] for entry in verdicts) == VERDICT_IDS
    for entry in verdicts:
        assert entry['verdict'] in ('成立', '判否')
        assert entry['description']


def test_the_leakage_audit_is_clean_on_every_seed_and_arm() -> None:
    leakage = _summary()['leakage']
    assert len(leakage) >= 20
    for key, block in leakage.items():
        assert block['folds'] in (5, 50), key
        assert block['folds_with_a_straddling_compound'] == 0, key
        assert block['max_straddling_compounds_in_a_fold'] == 0, key
    assert _summary()['readings']['leak_folds'] == 0


def test_the_selection_table_covers_every_selection_arm() -> None:
    rows = _rows(SELECTION_CSV)
    retuned = [row for row in rows if row['arm'] == w28.ARM_RETUNED]
    placebo = [row for row in rows if row['arm'] == w28.ARM_PLACEBO]
    response = [row for row in rows if row['arm'] == w28.ARM_RESPONSE_RETUNED]
    morgan = [row for row in rows if row['arm'] == w28.ARM_MORGAN_CONTROL]
    assert len(retuned) == 5 * 10 * 5
    assert len(response) == 5 * 10 * 5
    assert len(placebo) == 1 * 10 * 5
    assert len(morgan) == 1 * 5
    assert len(rows) == len(retuned) + len(response) + len(placebo) + len(morgan)
    assert {row['arm'] for row in rows} == {w28.ARM_RETUNED, w28.ARM_RESPONSE_RETUNED,
                                            w28.ARM_PLACEBO, w28.ARM_MORGAN_CONTROL}
    for row in rows:
        index = int(row['selected_index'])
        assert 0 <= index < len(w28.GRID)
        assert row['selected_label'] == w28.grid_label(index)
        assert int(row['selected_max_depth']) == w28.GRID[index][1]['max_depth']
        assert int(row['selected_n_estimators']) == w28.GRID[index][1]['n_estimators']
        assert float(row['selected_learning_rate']) == pytest.approx(
            w28.GRID[index][1]['learning_rate'])
        assert int(row['train_rows']) > 0
        assert int(row['test_rows']) > 0
        assert float(row['inner_best_r2']) >= float(row['inner_frozen_r2']) - 1e-12
    assert {row['seed'] for row in retuned} == {'42', '1234', '2026', '31337', '7'}
    assert {row['fold'] for row in retuned} == {str(index) for index in range(5)}
    assert {row['repeat'] for row in retuned} == {str(index) for index in range(10)}
    payload = SELECTION_CSV.read_bytes()
    assert not payload.startswith(BOM)
    assert CRLF not in payload

def test_the_ladder_carries_every_grid_entry_on_every_seed() -> None:
    summary = _summary()
    rows = _rows(REPEATS_CSV)
    ladder = [row for row in rows if row['arm'].startswith(w28.LADDER_ARM_PREFIX)]
    assert {row['arm'] for row in ladder} == set(LADDER_ARMS)
    assert len(ladder) == len(GRID_LABELS) * 5 * 10
    entries = summary['ladder']['entries']
    assert tuple(entries) == GRID_LABELS
    assert set(summary['ladder']['per_seed']) == {'42', '1234', '2026', '31337', '7'}
    for seed, block in summary['ladder']['per_seed'].items():
        assert tuple(block) == GRID_LABELS, seed
    assert summary['ladder']['best_entry'] in GRID_LABELS
    assert summary['ladder']['best_mean'] is not None


def test_the_placebo_only_shuffles_the_training_target() -> None:
    assert w28.PLACEBO_RNG_SEED == 2026
    assert tuple(w28.PLACEBO_SEEDS) == (42,)
    payload = json.loads(PREREG.read_text(encoding='utf-8'))['placebo']
    assert payload['rng_seed'] == 2026
    assert payload['seeds'] == [42]
    assert '只打乱外层折内的训练靶值' in payload['scope']
    rows = [row for row in _rows(REPEATS_CSV) if row['arm'] == w28.ARM_PLACEBO]
    assert len(rows) == 10
    assert {row['seed'] for row in rows} == {'42'}
    assert all(float(row['r2']) <= 0.0 for row in rows)
    summary = _summary()
    pooled = [float(row['r2']) for row in rows]
    assert summary['readings']['placebo_mean'] == pytest.approx(
        sum(pooled) / len(pooled), abs=1e-12)


def test_the_control_representation_runs_the_same_procedure() -> None:
    summary = _summary()
    assert summary['readings']['control_mean'] is not None
    assert summary['readings']['control_frozen_mean'] is not None
    assert summary['readings']['control_delta'] == pytest.approx(
        summary['readings']['control_mean'] - summary['readings']['control_frozen_mean'],
        abs=1e-12)
    rows = _rows(REPEATS_CSV)
    frozen = [row for row in rows if row['arm'] == w28.ARM_MORGAN_FROZEN]
    retuned = [row for row in rows if row['arm'] == w28.ARM_MORGAN_CONTROL]
    assert len(frozen) == len(retuned) == 1
    assert frozen[0]['seed'] == retuned[0]['seed'] == '42'
    assert frozen[0]['repeat'] == retuned[0]['repeat'] == '0'


def test_repeats_table_is_lf_only_and_covers_four_arms_per_seed() -> None:
    rows = _rows(REPEATS_CSV)
    assert set(rows[0]) == {'seed', 'arm', 'repeat', *METRIC_COLUMNS}
    assert set(METRIC_COLUMNS) == set(w28.METRIC_COLUMNS)
    for arm in (w28.ARM_FROZEN, w28.ARM_RETUNED, w28.ARM_RESPONSE_FROZEN,
                w28.ARM_RESPONSE_RETUNED):
        block = [row for row in rows if row['arm'] == arm]
        assert len(block) == 5 * 10, arm
        assert {row['seed'] for row in block} == {'42', '1234', '2026', '31337', '7'}
    payload = REPEATS_CSV.read_bytes()
    assert not payload.startswith(BOM)
    assert CRLF not in payload


def test_the_pool_and_the_response_block_are_the_frozen_ones() -> None:
    summary = _summary()
    assert summary['pool']['rows'] == 2391
    assert summary['pool']['scored_rows'] == 457
    assert summary['pool']['scored_compounds'] == 97
    assert summary['pool']['matches_preregistration'] is True
    assert summary['block']['compounds_in_the_block'] == 242
    assert summary['block']['compounds_complete'] == 242
    readings = summary['readings']
    assert readings['w27_expected'] == w28.W27_PHYSICAL_BLOCK_MEAN
    assert readings['w27_gap'] == pytest.approx(
        abs(readings['response_frozen_mean'] - w28.W27_PHYSICAL_BLOCK_MEAN), abs=1e-12)
    assert w28.INNER_SPLITS == 3
    assert w28.GATE_R2 == 0.6


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
    assert '主记分牌 shot：2' in text
    assert '0.5861142332208197' in text
    assert '0.60' in text
    for frozen in FROZEN_READINGS:
        assert repr(frozen) in text
    assert '内层' in text
    assert '阶梯' in text
