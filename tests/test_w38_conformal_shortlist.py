# Guards for the Week 38-A lane: the conformal screening shortlist.
#
# Week 38-A turns "abstain" from a black-and-white gate into a coverage-guaranteed
# shortlist.  The split is by COMPOUND (half calibration / half evaluation), which is
# what makes the coverage claim meaningful; a row-level split would put the same
# compound on both sides and void it.  H38a2 is a REGISTERED negative (the pooled
# precision at tau=30 / alpha=0.10 is 0.8125, below the 0.90 gate) and must stay
# registered instead of being re-tuned into a pass.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w38_conformal_shortlist_summary.json'
COVERAGE = ROOT / 'probes' / 'artifacts' / 'w38_conformal_coverage.csv'
SHORTLIST = ROOT / 'probes' / 'artifacts' / 'w38_conformal_shortlist.csv'
FIGURE = ROOT / 'probes' / 'artifacts' / 'w38_conformal_coverage.png'
REPORT = ROOT / 'reports' / 'w38_conformal_shortlist.md'


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_ledger_and_frozen_readings_untouched() -> None:
    payload = _summary()
    assert payload['task'] == 'week38_conformal_shortlist'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['frozen_readings_untouched'] == [0.4091179943351143, 0.4766400383507876]
    assert payload['inputs_unchanged'] is True


def test_verdict_pattern_is_seven_passes_and_one_registered_negative() -> None:
    payload = _summary()
    verdicts = payload['criteria']
    assert len(verdicts) == 8
    assert [item['id'] for item in verdicts] == ['H38a1', 'H38a2', 'H38a2b', 'H38a3',
                                                 'H38a4', 'H38a6', 'H38a7', 'H38a5']
    failed = {item['id'] for item in verdicts if item['verdict'] != '成立'}
    assert failed == {'H38a2'}
    assert payload['registered_negatives'] == ['H38a2']
    assert [item['verdict'] for item in verdicts].count('判否') == 1


def test_coverage_meets_target_within_slack() -> None:
    rows = list(csv.DictReader(COVERAGE.open(encoding='utf-8', newline='')))
    primary = [row for row in rows if row['representation'] == 'Physical']
    assert primary, 'primary representation missing'
    for alpha in ('0.05', '0.1', '0.2'):
        bucket = [float(row['coverage_rows']) for row in primary if row['alpha'] == alpha]
        assert bucket, alpha
        mean = sum(bucket) / len(bucket)
        assert mean >= (1.0 - float(alpha)) - 0.05


def test_split_is_by_compound_and_covers_the_pool() -> None:
    rows = list(csv.DictReader(COVERAGE.open(encoding='utf-8', newline='')))
    for row in rows:
        assert int(row['cal_compounds']) + int(row['eval_compounds']) == 98
        assert int(row['cal_compounds']) == int(row['eval_compounds'])
        assert int(row['cal_rows']) > 0 and int(row['eval_rows']) > 0


def test_shortlist_is_three_valued_and_covers_every_evaluation_compound() -> None:
    rows = list(csv.DictReader(SHORTLIST.open(encoding='utf-8', newline='')))
    assert rows
    for row in rows:
        total = int(row['n_recommend']) + int(row['n_undecided']) + int(row['n_exclude'])
        assert total == int(row['eval_compounds'])


def test_artifacts_and_report_exist() -> None:
    assert FIGURE.is_file() and FIGURE.stat().st_size > 0
    assert REPORT.is_file()
    assert 'H38a2 判否' in REPORT.read_text(encoding='utf-8')
