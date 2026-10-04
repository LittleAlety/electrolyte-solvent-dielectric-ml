# Guards for the Week 44 lane W44-B: the per-round acceptance runner.
# It reuses the W43-D ledger invariants and scans every 成果输出/week*/week*_summary.json for
# five acceptance fields, so a week that silently ships a missing lane or a broken red line
# becomes mechanically visible instead of a matter of trust.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w44_acceptance_runner_summary.json'
MATRIX = ART / 'w44_acceptance_matrix.csv'
RECORD = ART / 'w44_acceptance_record.json'
REPORT = ROOT / 'reports' / 'w44_acceptance_runner.md'
PROBE = ROOT / 'probes' / 'w44_acceptance_runner.py'
PREREG = ROOT / 'probes' / 'w44_governance_wiring_prereg.json'

CRITERIA_IDS = ['H44b' + str(index) for index in range(1, 8)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w44_acceptance_runner/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_seven_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 7
    assert payload['registered_negatives'] == []


def test_weeks_scanned_and_failures() -> None:
    payload = _summary()
    assert payload['weeks_scanned'] >= 40
    assert payload['declared_weeks'] >= 30
    assert payload['failing_weeks'] == []


def test_recent_weeks_all_pass() -> None:
    payload = _summary()
    assert len(payload['recent_weeks']) == 5
    assert 'week43' in payload['recent_weeks']
    assert payload['recent_all_pass'] is True


def test_ledger_invariants_hold() -> None:
    payload = _summary()
    assert payload['invariants_hold'] is True
    invariants = payload['invariants']
    assert invariants['negatives_stable'] is True
    assert invariants['frozen_readings_intact'] is True


def test_artifacts_exist_and_are_lf_only() -> None:
    for path in (SUMMARY, MATRIX, RECORD, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (MATRIX, REPORT, PROBE, PREREG):
        data = _bytes(path)
        assert not data.startswith(b'\xef\xbb\xbf'), path
        assert b'\r\n' not in data, path
    with MATRIX.open('r', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 40
