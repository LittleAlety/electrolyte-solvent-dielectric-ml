# Guards for the Week 44 lane W44-A: the layer-admission gate plus the repo-wide consumer audit.
# W43 scored every orbital layer; W44-A turns that table into a gate that raises PriorRefused for
# any layer whose verdict is not "admit".  Only PubChemQC passes; ccsd_t (unregistered), QM9 (defer)
# and Batt (the target layer) are all refused.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w44_prior_gate_summary.json'
CONSUMERS = ART / 'w44_prior_consumers.csv'
REFUSALS = ART / 'w44_prior_gate_refusals.csv'
GATE = ART / 'w44_prior_gate.json'
REPORT = ROOT / 'reports' / 'w44_prior_gate.md'
PROBE = ROOT / 'probes' / 'w44_prior_gate.py'
PREREG = ROOT / 'probes' / 'w44_governance_wiring_prereg.json'

CRITERIA_IDS = ['H44a' + str(index) for index in range(1, 9)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
VERDICTS = {'xtb': 'defer', 'qm9': 'defer', 'pubchemqc': 'admit', 'batt': 'reject'}


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w44_prior_gate/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_eight_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 8
    assert payload['registered_negatives'] == []


def test_only_pubchemqc_passes_the_gate() -> None:
    payload = _summary()
    assert payload['admission_verdicts'] == VERDICTS
    assert payload['positive_control'] == {'pubchemqc': 'admitted'}


def test_negative_controls_are_refused() -> None:
    payload = _summary()
    refusals = {row['layer']: row['verdict'] for row in payload['refusal_rows']}
    assert refusals == {'ccsd_t': 'refused', 'qm9': 'refused', 'batt': 'refused'}


def test_consumer_audit_has_no_undeclared_prior_use() -> None:
    payload = _summary()
    assert payload['scanned_files'] >= 300
    assert payload['undeclared_prior_uses'] == []
    for row in payload['consumer_rows']:
        assert row['gate_verdict'] in {'admitted', 'refused', 'not_applicable'}


def test_artifacts_exist_and_are_lf_only() -> None:
    for path in (SUMMARY, CONSUMERS, REFUSALS, GATE, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (CONSUMERS, REFUSALS, REPORT, PROBE, PREREG):
        data = _bytes(path)
        assert not data.startswith(b'\xef\xbb\xbf'), path
        assert b'\r\n' not in data, path
    assert len(_rows(CONSUMERS)) >= 1
