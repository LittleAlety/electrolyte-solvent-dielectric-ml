# Guards for Week 47 lane W47-B: the experimental reduction-track item-by-item ledger.  Every item
# must carry a verdict from the locked vocabulary and a non-empty condition_flag; computed series are
# never admissible as experimental anchors, and the empty coverage is registered explicitly.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w47_experimental_track_summary.json'
LEDGER_CSV = ART / 'w47_experimental_ledger.csv'
REPORT = ROOT / 'reports' / 'w47_experimental_track.md'
PREREG = ROOT / 'probes' / 'w47_experimental_track_prereg.json'
PROBE = ROOT / 'probes' / 'w47_experimental_track.py'

CRITERIA_IDS = ['H47b' + str(index) for index in range(1, 9)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
VERDICT_VOCABULARY = ['mechanism_evidence_only', 'anchor_candidate_pending_source',
                      'not_available_on_disk', 'rejected_license', 'rejected_criterion_mismatch',
                      'rejected_computed_only', 'not_evaluable_condition_differs']
FLAG_VOCABULARY = ['CONDITION_DIFFERS_LI_DEPOSITION', 'CONDITION_MATCH_UNVERIFIED',
                   'NOT_APPLICABLE_SINGLE_SOLVENT']


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w47_experimental_track/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS
    assert payload['registered_negatives'] == []


def test_eight_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 8


def test_every_item_has_verdict_and_condition_flag() -> None:
    payload = _summary()
    assert payload['n_items'] == 9
    with LEDGER_CSV.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 9
    assert all(row['condition_flag'].strip() for row in rows)
    assert all(row['verdict'] in VERDICT_VOCABULARY for row in rows)
    assert all(row['condition_flag'] in FLAG_VOCABULARY for row in rows)
    assert set(payload['verdicts_used']).issubset(set(VERDICT_VOCABULARY))
    assert set(payload['flags_used']).issubset(set(FLAG_VOCABULARY))


def test_moshkovich_reclassified_not_an_anchor() -> None:
    payload = _summary()
    assert payload['sensitivity_only_object'] == 'moshkovich2001'
    with LEDGER_CSV.open(encoding='utf-8', newline='') as handle:
        rows = {row['item_id']: row for row in csv.DictReader(handle)}
    assert rows['moshkovich2001']['verdict'] == 'mechanism_evidence_only'
    assert rows['moshkovich2001']['condition_flag'] == 'CONDITION_DIFFERS_LI_DEPOSITION'


def test_experimental_track_not_evaluable() -> None:
    payload = _summary()
    assert payload['experimental_reduction_members'] == ['PC']
    assert payload['evaluable'] is False
    assert payload['experimental_track_verdict'] == 'not_evaluable_condition_differs'


def test_computed_series_rejected_and_offdisk_registered() -> None:
    payload = _summary()
    assert len(payload['rejected_computed_only_items']) >= 2
    assert 'borodin2013_table1' in payload['rejected_computed_only_items']
    assert 'borodin2015_fig6_7_8' in payload['rejected_computed_only_items']
    assert len(payload['not_available_items']) >= 1
    assert payload['open_item']['status'] == 'pending_source_retrieval'


def test_artifacts_and_prereg_exist() -> None:
    for path in (LEDGER_CSV, REPORT, PROBE):
        assert path.is_file() and path.stat().st_size > 0
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    assert prereg['status'] == 'locked_before_run'
    assert set(prereg['verdict_vocabulary']) == set(VERDICT_VOCABULARY)
    assert set(prereg['condition_registration']['values']) == set(FLAG_VOCABULARY)
