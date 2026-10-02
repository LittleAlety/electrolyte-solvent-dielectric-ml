# Guards for the Week 30-A ordering-versus-magnitude decomposition.
#
# The repository headline diagnosis is "the ordering was learned, the magnitude was
# not".  Week 30-A turns that sentence into a controlled within-family comparison at
# zero cost: the Week 28 and Week 29 ladders re-fit the same thirteen-column dense
# block on the same folds with the same five seeds and move nothing but
# hyperparameters, so if hyperparameters buy magnitude and not ordering then inside a
# ladder R-squared must move far more than Spearman / AUC.
#
# The reading is deliberately post hoc, and the guards pin exactly that:
#
#   * it occupies no main-scoreboard shot and says so in the summary;
#   * it reads two committed per-repeat CSVs and their sha256 digests are quoted;
#   * the aggregation is reproducible here from those CSVs alone;
#   * it never touches the four frozen readings or METRIC_NAMES.
from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w30_ordering_magnitude as w30a

ARTIFACTS = ROOT / 'probes' / 'artifacts'
OUT_CSV = ARTIFACTS / 'w30_ordering_magnitude.csv'
FIG = ARTIFACTS / 'w30_ordering_magnitude.png'
SUMMARY = ROOT / 'probes' / 'w30_ordering_magnitude_summary.json'
REPORT = ROOT / 'reports' / 'w30_ordering_magnitude.md'
CRLF = bytes([13, 10])
BOM = bytes([239, 187, 191])

FROZEN_READINGS = {
    'baseline': 0.4091179943351143,
    'headline': 0.4766400383507876,
    'single_representation_endpoint': 0.5861142332208197,
    'week20_registered_arm': 0.6216672295270079,
}
VERDICT_IDS = tuple('P' + str(index) for index in range(1, 12))


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list:
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def _recompute(path: Path) -> dict:
    """Cross-seed mean per arm, recomputed from the raw per-repeat table."""

    by_arm_seed: dict = {}
    with path.open(encoding='utf-8', newline='') as handle:
        for row in csv.DictReader(handle):
            by_arm_seed.setdefault(row['arm'], {}).setdefault(row['seed'], []).append(row)
    table = {}
    for arm, per_seed in by_arm_seed.items():
        entry = {}
        for metric in w30a.METRICS:
            values = [statistics.fmean(float(row[metric]) for row in rows)
                      for rows in per_seed.values()]
            entry[metric + '_mean'] = float(np.mean(values))
        table[arm] = entry
    return table


def test_the_reading_is_post_hoc_and_occupies_no_shot() -> None:
    summary = _summary()
    assert summary['schema'] == w30a.SCHEMA
    assert summary['task'] == w30a.TASK
    assert summary['post_hoc'] is True
    assert summary['occupies_main_scoreboard_shot'] is False
    assert summary['main_scoreboard_attempts_delta'] == 0
    assert summary['cumulative_main_scoreboard_attempts'] == 16


def test_the_inputs_are_quoted_bit_for_bit() -> None:
    inputs = _summary()['inputs']
    assert inputs['w28_repeats']['sha256'] == _digest(w30a.W28_REPEATS)
    assert inputs['w29_repeats']['sha256'] == _digest(w30a.W29_REPEATS)
    assert inputs['w28_repeats']['path'].endswith('w28_dense_hyperparameters_repeats.csv')
    assert inputs['w29_repeats']['path'].endswith('w29_dense_binning_repeats.csv')


def test_every_criterion_is_present_and_none_is_falsified() -> None:
    verdicts = _summary()['verdicts']
    assert tuple(entry['id'] for entry in verdicts) == VERDICT_IDS
    for entry in verdicts:
        assert entry['verdict'] == '成立', (entry['id'], entry['verdict'])
        assert entry['description']


def test_hyperparameters_move_magnitude_far_more_than_ordering() -> None:
    blocks = {block['week']: block for block in _summary()['ladders']}
    assert set(blocks) == {'W28', 'W29'}
    for week, block in blocks.items():
        spread = block['spread']
        assert spread['r2_mean'] > 0.05, week
        assert spread['auc_gt30_mean'] < 0.01, week
        assert spread['spearman_mean'] < 0.025, week
        assert block['ratio_r2_over_auc30'] > 5.0, week
        assert block['arms'] == 6, week
        assert block['family'] == 'physical_dense_13col'


def test_the_sparse_block_fails_on_ordering_and_recovers_only_there() -> None:
    readings = {row['arm']: row for row in _summary()['readings']}
    frozen = readings['lever4_morgan_frozen']
    retuned = readings['lever4_morgan_retuned']
    assert frozen['r2_mean'] < 0.10
    assert frozen['auc_gt30_mean'] < 0.70
    assert retuned['r2_mean'] < 0.10
    assert retuned['auc_gt30_mean'] - frozen['auc_gt30_mean'] > 0.15


def test_the_frozen_readings_are_only_quoted_never_moved() -> None:
    assert _summary()['frozen_readings'] == FROZEN_READINGS
    assert w30a.METRICS == ('r2', 'spearman', 'auc_gt15', 'auc_gt30')


def test_the_aggregation_is_reproducible_from_the_committed_tables() -> None:
    summary = _summary()
    recomputed = {'W28': _recompute(w30a.W28_REPEATS), 'W29': _recompute(w30a.W29_REPEATS)}
    for row in summary['readings']:
        for metric in w30a.METRICS:
            expected = recomputed[row['week']][row['arm']][metric + '_mean']
            assert row[metric + '_mean'] == pytest.approx(expected, abs=1e-12), row['arm']


def test_the_output_table_lists_every_ladder_entry_and_context_arm() -> None:
    rows = _rows(OUT_CSV)
    assert len(rows) == 12 + 6
    assert {row['group'] for row in rows} == {'ladder', 'context'}
    assert {row['week'] for row in rows} == {'W28', 'W29'}
    ladder = [row for row in rows if row['group'] == 'ladder']
    for week, prefix in (('W28', 'grid_fixed_'), ('W29', 'binning_')):
        block = [row for row in ladder if row['week'] == week]
        assert len(block) == 6, week
        assert all(row['arm'].startswith(prefix) for row in block), week
    payload = OUT_CSV.read_bytes()
    assert not payload.startswith(BOM)
    assert CRLF not in payload


def test_figure_and_report_are_written_and_state_the_level_of_the_reading() -> None:
    assert FIG.is_file()
    assert FIG.stat().st_size > 20000
    assert FIG.read_bytes()[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
    assert _summary()['figures']['main'] == FIG.name
    text = REPORT.read_text(encoding='utf-8')
    assert '后验读数' in text
    assert '不占主记分牌 shot' in text
    assert '0.60' in text
    assert 'Morgan' in text