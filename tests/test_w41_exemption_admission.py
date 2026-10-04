# Guards for the Week 41 lane W41-C: the mechanical admission rules for EXEMPT_WRITERS.
# Each of the 22 registered owners must fall into at least one of the three categories by
# source evidence, no registered owner may contain write_json_stable, and the three policy
# rules must be emitted.  The mechanical evidence corrects W40's hand grouping: the real
# pinned-and-append overlap is pubchem_identity_layer.py, not the owner W40 named.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w41_exemption_admission_summary.json'
ADMISSION = ART / 'w41_exemption_admission.csv'
POLICY = ART / 'w41_exemption_policy.json'
REPORT = ROOT / 'reports' / 'w41_exemption_admission.md'
PROBE = ROOT / 'probes' / 'w41_exemption_admission.py'
PREREG = ROOT / 'probes' / 'w41_governance_prereg.json'

CRITERIA_IDS = ['H41c' + str(index) for index in range(1, 11)]
REGISTERED_NEGATIVES = []
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
EXPECTED_COUNTS = {'pinned_bytes': 16, 'append_log': 4, 'strict_json': 3}
OVERLAP = 'probes/pubchem_identity_layer.py'


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w41_exemption_admission/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_ten_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert all(item['verdict'] == '成立' for item in criteria)
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_twenty_two_owners_and_mechanical_category_counts() -> None:
    payload = _summary()
    assert int(payload['n_owners']) == 22
    assert payload['counts'] == EXPECTED_COUNTS
    assert payload['overlap_pinned_append'] == [OVERLAP]


def test_every_owner_admitted_and_no_registered_owner_uses_stable_writer() -> None:
    rows = _rows(ADMISSION)
    assert len(rows) == 22
    assert all(row['admitted'] == 'True' for row in rows)
    assert all(row['has_stable_helper'] == 'False' for row in rows)
    assert all(int(row['n_categories']) >= 1 for row in rows)
    assert all(int(row['reason_len']) >= 6 for row in rows)


def test_policy_file_has_three_rules_and_known_cost() -> None:
    policy = json.loads(POLICY.read_text(encoding='utf-8'))
    assert policy['schema'] == 'w41_exemption_policy/policy@1'
    assert len(policy['policy_rules']) == 3
    assert policy['counts'] == EXPECTED_COUNTS
    assert 'known_cost' in policy
    assert policy['w40_hand_grouping_correction']


def test_artifacts_and_report_exist_and_are_lf_only() -> None:
    for path in (SUMMARY, ADMISSION, POLICY, REPORT, PROBE, PREREG):
        assert path.is_file(), path
        assert b'\r\n' not in path.read_bytes(), path