# Guards for the Week 36-A lane: the main scoreboard endpoint rule written down.
#
# The endpoint ("five locked seeds, averaged over folds, then over seeds") lived only in
# report prose for nineteen shots.  Week 36-A turns it into an on-disk rule table plus an
# executable endpoint recomputer, and the recomputation exposed something the prose hid:
# the published endpoints differ from a freshly averaged one by up to two ulp, so endpoint
# equality has to be a tolerance (1e-12), never a string comparison.
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

import w36_endpoint_rule as probe

RULES = ROOT / 'data' / 'processed' / 'w36_endpoint_rule_registry.csv'
CONFORMANCE = ROOT / 'probes' / 'artifacts' / 'w36_endpoint_conformance.csv'
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w36_endpoint_rule_summary.json'
REPORT = ROOT / 'reports' / 'w36_endpoint_rule.md'

PUBLISHED_EXPECTED = 26
INELIGIBLE_ARM = 'lever4_physical_retuned_shuffled_target'


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_lane_is_post_hoc_and_takes_no_shot() -> None:
    payload = _summary()
    assert payload['task'] == 'week36_endpoint_rule'
    assert int(payload['ledger']['main_scoreboard_shots_this_week']) == 0
    assert int(payload['ledger']['cumulative_main_scoreboard_attempts_after']) == 19


def test_rule_table_has_seven_clauses() -> None:
    rows = _rows(RULES)
    assert [row['rule_id'] for row in rows] == ['R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7']
    assert rows[1]['value'] == '42,1234,2026,31337,7'
    assert rows[2]['value'] == '10'
    assert rows[4]['value'] == '1e-12'
    assert 'max_bin=128' in rows[3]['value']


def test_endpoint_recomputer_refuses_a_drifted_seed_set() -> None:
    assert probe.REPEATS_PER_SEED == 10
    assert probe.ENDPOINT_TOLERANCE == 1e-12
    rows = [{'arm': 'a', 'seed': str(seed), 'r2': '0.5'} for seed in (42, 1234, 2026)]
    with pytest.raises(probe.SeedSetDriftError):
        probe.endpoint_of(rows, 'a')


def test_endpoint_recomputer_refuses_a_drifted_fold_count() -> None:
    rows = [{'arm': 'a', 'seed': str(seed), 'r2': '0.5'} for seed in probe.LOCKED_SEEDS]
    with pytest.raises(probe.SeedSetDriftError):
        probe.endpoint_of(rows, 'a')


def test_every_published_endpoint_reproduces_within_tolerance() -> None:
    rows = _rows(CONFORMANCE)
    checked = [row for row in rows if row['verdict'] in ('成立', '判否')]
    assert len(checked) == PUBLISHED_EXPECTED
    assert all(row['verdict'] == '成立' for row in checked)
    assert max(abs(float(row['abs_diff'])) for row in checked) <= probe.ENDPOINT_TOLERANCE
    # The whole point of clause R5: equality is a tolerance, not a string match.
    assert any(float(row['abs_diff']) > 0.0 for row in checked)


def test_ineligible_arms_are_labelled_and_carry_no_published_value() -> None:
    rows = _rows(CONFORMANCE)
    ineligible = [row for row in rows if row['verdict'].startswith('不适用')]
    assert len(ineligible) == 3
    assert all(row['table'].endswith('w28_dense_hyperparameters_repeats.csv')
               for row in ineligible)
    assert any(row['arm'] == INELIGIBLE_ARM for row in ineligible)
    assert all(row['endpoint_published'] == '' for row in ineligible)
    assert all(int(row['n_seeds']) == 5 for row in rows if row['n_seeds'] != '')


def test_four_frozen_readings_are_recorded_unchanged() -> None:
    payload = _summary()
    readings = probe.FROZEN_READINGS
    assert readings['frozen_baseline'] == 0.4091179943351143
    assert readings['frozen_headline'] == 0.4766400383507876
    assert readings['single_representation_cross_seed'] == 0.5861142332208197
    assert readings['w20_4_promoted_arm'] == 0.6216672295270079
    assert payload['frozen_readings'] == readings
    assert set(payload['frozen_readings']) == {
        'frozen_baseline', 'frozen_headline',
        'single_representation_cross_seed', 'w20_4_promoted_arm'}


def test_inputs_are_pinned_and_the_report_exists() -> None:
    payload = _summary()
    assert len(payload['inputs']) == 6
    for relative, digest in payload['inputs'].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
    verdicts = {item['id']: item['verdict'] for item in payload['criteria']}
    assert set(verdicts) == {'H36a1', 'H36a2', 'H36a3', 'H36a4', 'H36a5'}
    assert all(value == '成立' for value in verdicts.values())
    assert REPORT.is_file() and REPORT.stat().st_size > 0