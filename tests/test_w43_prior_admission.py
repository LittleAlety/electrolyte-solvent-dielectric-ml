# Guards for the Week 43 lane W43-C: the external-layer prior-admission rule.
# A mechanical rule scores every orbital layer and admits only PubChemQC as a read-only
# ranking prior; QM9 defers on missing unit/structure metadata, xTB defers on weak rank
# agreement, and Batt is the target layer so it can never be a prior.  near_same_level is
# never silently promoted: the strict same_level count stays zero.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w43_prior_admission_summary.json'
ADMISSION = ART / 'w43_prior_admission.csv'
ADMISSION_JSON = ART / 'w43_prior_admission.json'
REPORT = ROOT / 'reports' / 'w43_prior_admission.md'
PROBE = ROOT / 'probes' / 'w43_prior_admission.py'
PREREG = ROOT / 'probes' / 'w43_protocol_prereg.json'

CRITERIA_IDS = ['H43c' + str(index) for index in range(1, 11)]
REGISTERED_NEGATIVES: list = []
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
VERDICTS = {'xtb': 'defer', 'qm9': 'defer', 'pubchemqc': 'admit', 'batt': 'reject'}
SPEARMAN = {'xtb': 0.32799580402320133, 'qm9': 0.8176735614281957,
            'pubchemqc': 0.7386459868154263, 'batt': 1.0}
COVERAGE = {'xtb': 237, 'qm9': 103, 'pubchemqc': 205, 'batt': 73}


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w43_prior_admission/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_ten_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 10
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_verdicts_and_scores() -> None:
    payload = _summary()
    assert payload['verdicts'] == VERDICTS
    rows = {row['layer']: row for row in payload['admission_rows']}
    for layer, value in SPEARMAN.items():
        assert abs(rows[layer]['spearman_vs_batt'] - value) < 1e-12
        assert rows[layer]['n_overlap_roster'] == COVERAGE[layer]
    assert rows['pubchemqc']['score'] >= 0.6
    assert rows['pubchemqc']['metadata_complete'] is True
    assert rows['qm9']['metadata_complete'] is False
    assert rows['batt']['verdict'] == 'reject'


def test_batt_is_never_a_prior() -> None:
    payload = _summary()
    rows = {row['layer']: row for row in payload['admission_rows']}
    assert rows['batt']['verdict'] == 'reject'
    assert '目标层' in rows['batt']['reason']
    assert 'batt' not in payload['counterfactual']['admitted_layers']


def test_near_same_level_is_not_auto_admitted() -> None:
    payload = _summary()
    pair = payload['same_level_pairs'][0]
    assert pair['pair'] == 'qm9-pubchemqc'
    assert pair['strict_same_level'] is False
    assert pair['admitted_as_prior'] is False


def test_admitted_layer_rank_agreement() -> None:
    payload = _summary()
    agreement = payload['counterfactual']['rank_agreement_with_batt']
    assert agreement == {'pubchemqc': SPEARMAN['pubchemqc']}
    assert all(value >= 0.5 for value in agreement.values())


def test_artifacts_are_lf_only() -> None:
    rows = _rows(ADMISSION)
    assert len(rows) == 4
    payload = json.loads(ADMISSION_JSON.read_text(encoding='utf-8'))
    assert payload['verdicts'] == VERDICTS
    for path in (SUMMARY, ADMISSION, ADMISSION_JSON, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (SUMMARY, ADMISSION, ADMISSION_JSON, REPORT, PROBE, PREREG):
        assert b'\r\n' not in path.read_bytes(), path
