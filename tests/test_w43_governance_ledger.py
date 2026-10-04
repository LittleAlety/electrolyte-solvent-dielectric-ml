# Guards for the Week 43 lane W43-D: the repo-level governance ledger guard.
# Every probes/**/*.json is scanned as a ledger.  The registered-negative union must equal
# the known nine, no summary may carry a frozen reading outside the canonical four, and the
# cumulative main-scoreboard shot count must be monotone and capped at 19.  This lane only
# reads JSON: it writes no summary, label, or feature column.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w43_governance_ledger_summary.json'
LEDGER_CSV = ART / 'w43_governance_ledger.csv'
LEDGER_JSON = ART / 'w43_governance_ledger.json'
REPORT = ROOT / 'reports' / 'w43_governance_ledger.md'
PROBE = ROOT / 'probes' / 'w43_governance_ledger.py'
PREREG = ROOT / 'probes' / 'w43_protocol_prereg.json'

CRITERIA_IDS = ['H43d' + str(index) for index in range(1, 9)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
EXPECTED_NEGATIVES = ['H38a2', 'H38b1', 'H39a7', 'H40a5', 'H40c10', 'H40c11', 'H40d8',
                      'H41b5', 'H41d8']
SHOTS_CEILING = 19


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w43_governance_ledger/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_eight_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 8


def test_registered_negatives_are_stable() -> None:
    payload = _summary()
    assert payload['registered_negatives'] == EXPECTED_NEGATIVES
    assert payload['invariants']['registered_negatives_union'] == EXPECTED_NEGATIVES
    assert payload['invariants']['negatives_stable'] is True


def test_frozen_readings_never_move() -> None:
    invariants = _summary()['invariants']
    assert invariants['frozen_outside_canon'] == 0
    assert invariants['frozen_readings_intact'] is True
    canon = json.loads(LEDGER_JSON.read_text(encoding='utf-8'))['frozen_readings_canon']
    assert canon == sorted(FROZEN_READINGS)


def test_shot_ledger_is_monotone_and_capped() -> None:
    invariants = _summary()['invariants']
    assert invariants['shots_monotone_nondecreasing'] is True
    assert invariants['cumulative_shots_max'] <= SHOTS_CEILING
    assert invariants['shots_ceiling'] == SHOTS_CEILING
    assert invariants['ledger_entries'] >= 37


def test_week43_lanes_took_no_shot() -> None:
    invariants = _summary()['invariants']
    assert invariants['week43_summaries'] >= 3
    assert invariants['week43_shots_all_zero'] is True


def test_scanned_ledger_rows_are_lf_only() -> None:
    rows = _rows(LEDGER_CSV)
    assert len(rows) >= 300
    assert _summary()['invariants']['summaries_scanned'] == len(rows)
    for path in (SUMMARY, LEDGER_CSV, LEDGER_JSON, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (SUMMARY, LEDGER_CSV, LEDGER_JSON, REPORT, PROBE, PREREG):
        assert b'\r\n' not in path.read_bytes(), path
