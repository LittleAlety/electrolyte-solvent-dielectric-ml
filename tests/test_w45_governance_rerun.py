# Guards for the Week 45 lane W45-D: the governance-rerun snapshot.  The three W44 guards
# (admission gate, per-round acceptance runner, AST static guard) plus the W43 ledger are re-run in
# one place, and the W45 lanes are checked to have taken zero main-scoreboard shots.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w45_governance_rerun_summary.json'
GUARDS_CSV = ART / 'w45_governance_rerun.csv'
REPORT = ROOT / 'reports' / 'w45_governance_rerun.md'
PROBE = ROOT / 'probes' / 'w45_governance_rerun.py'
PREREG = ROOT / 'probes' / 'w45_compute_prereg.json'

CRITERIA_IDS = ['H45d' + str(index) for index in range(1, 8)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
NEGATIVES = ['H38a2', 'H38b1', 'H39a7', 'H40a5', 'H40c10', 'H40c11', 'H40d8', 'H41b5', 'H41d8']


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w45_governance_rerun/summary@1'
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


def test_guards_are_green() -> None:
    payload = _summary()
    assert payload['refused_controls'] == 3
    assert payload['operational_prior_uses'] >= 1
    invariants = payload['invariants']
    assert invariants['registered_negatives_union'] == NEGATIVES
    assert invariants['negatives_stable'] is True
    assert invariants['frozen_outside_canon'] == 0
    assert invariants['frozen_readings_intact'] is True
    assert invariants['cumulative_shots_max'] == 19


def test_week45_took_no_shot() -> None:
    payload = _summary()
    shots = payload['week45_shots']
    assert len(shots) >= 3
    assert all(value == 0 for value in shots.values())


def test_artifacts_exist_and_are_lf_only() -> None:
    for path in (SUMMARY, GUARDS_CSV, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (GUARDS_CSV, REPORT, PROBE, PREREG):
        data = _bytes(path)
        assert not data.startswith(b'\xef\xbb\xbf'), path
        assert b'\r\n' not in data, path
    with GUARDS_CSV.open('r', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 15
