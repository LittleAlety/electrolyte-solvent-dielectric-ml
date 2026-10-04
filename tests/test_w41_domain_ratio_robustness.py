# Guards for the Week 41 lane W41-B: the dual-reading robustness clause for the
# Onsager domain ratio.  Any future domain-ratio citation must carry both the
# bias-uncorrected and the dipole-bias-corrected value; the relative change
# (0.2059 > 0.10) forces "direction robust only".  H41b5 is the registered negative.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w41_domain_ratio_robustness_summary.json'
READINGS = ART / 'w41_domain_ratio_robustness.csv'
CLAUSE = ART / 'w41_domain_ratio_clause.json'
REPORT = ROOT / 'reports' / 'w41_domain_ratio_robustness.md'
PROBE = ROOT / 'probes' / 'w41_domain_ratio_robustness.py'
PREREG = ROOT / 'probes' / 'w41_governance_prereg.json'

CRITERIA_IDS = ['H41b' + str(index) for index in range(1, 11)]
REGISTERED_NEGATIVES = ['H41b5']
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
UNCORRECTED = 2.5817133416784355
CORRECTED = 3.1132529110752816
RELATIVE = 0.20588636267854554
HIGH_EPS_UNCORRECTED = 13.404447543209601
HIGH_EPS_CORRECTED = 17.31695976838166


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w41_domain_ratio_robustness/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_dual_reading_reproduces_w40c_anchors() -> None:
    payload = _summary()
    assert payload['ratio_uncorrected'] == UNCORRECTED
    assert abs(payload['ratio_corrected'] - CORRECTED) < 1e-12
    assert abs(payload['relative_change'] - RELATIVE) < 1e-15
    assert abs(payload['high_eps_ratio_uncorrected'] - HIGH_EPS_UNCORRECTED) < 1e-9
    assert abs(payload['high_eps_ratio_corrected'] - HIGH_EPS_CORRECTED) < 1e-9


def test_ten_criteria_with_the_magnitude_claim_registered_as_negative() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    verdicts = {item['id']: item['verdict'] for item in criteria}
    assert [key for key, value in verdicts.items() if value != '成立'] == REGISTERED_NEGATIVES
    assert verdicts['H41b5'] == '判否'
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_clause_carries_both_readings_and_is_not_magnitude_robust() -> None:
    clause = json.loads(CLAUSE.read_text(encoding='utf-8'))
    assert clause['schema'] == 'w41_domain_ratio_clause/clause@1'
    assert clause['uncorrected_ratio'] == UNCORRECTED
    assert abs(clause['corrected_ratio'] - CORRECTED) < 1e-12
    assert abs(clause['relative_change'] - RELATIVE) < 1e-15
    assert clause['magnitude_robust'] is False
    assert clause['direction_robust'] is True
    assert float(clause['gate']) == 0.10


def test_readings_table_has_two_scopes_and_two_readings_each() -> None:
    rows = _rows(READINGS)
    assert len(rows) == 4
    assert {row['scope'] for row in rows} == {'all_usable', 'high_eps_family'}
    assert {row['reading'] for row in rows} == {'uncorrected', 'corrected'}
    assert all(row['rel_change_vs_uncorrected'].strip() for row in rows
               if row['reading'] == 'corrected')


def test_artifacts_and_report_exist_and_are_lf_only() -> None:
    for path in (SUMMARY, READINGS, CLAUSE, REPORT, PROBE, PREREG):
        assert path.is_file(), path
        assert b'\r\n' not in path.read_bytes(), path