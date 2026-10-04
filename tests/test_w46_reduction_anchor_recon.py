# Guards for the Week 46 lane W46-B: the reduction-anchor reconnaissance + admission ledger.
# Every scanned candidate item must carry a verdict from the locked vocabulary; computed series are
# never admissible as experimental anchors, and the empty result is registered explicitly.
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w46_reduction_anchor_recon_summary.json'
CANDIDATES_CSV = ART / 'w46_reduction_anchor_candidates.csv'
LEDGER_CSV = ART / 'w46_reduction_anchor_ledger.csv'
REPORT = ROOT / 'reports' / 'w46_reduction_anchor_recon.md'
PREREG = ROOT / 'probes' / 'w46_reduction_anchor_recon_prereg.json'
PROBE = ROOT / 'probes' / 'w46_reduction_anchor_recon.py'

CRITERIA_IDS = ['H46b' + str(index) for index in range(1, 11)]
VOCABULARY = ['hit_interactive_anchor', 'rejected_license', 'rejected_criterion_mismatch',
              'rejected_rig_mismatch', 'rejected_computed_only', 'not_available_on_disk',
              'environment_blocked']
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w46_reduction_anchor_recon/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS
    assert payload['registered_negatives'] == []


def test_ten_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 10


def test_every_candidate_has_a_registered_verdict() -> None:
    payload = _summary()
    candidates = [row for row in payload['ledger_rows']
                  if row['kind'] in ('column', 'named_control')]
    assert len(candidates) > 0
    assert all(row['verdict'] in VOCABULARY for row in candidates)
    computed = [row for row in candidates if row['layer'] in ('batt', 'qm9', 'pubchemqc', 'xtb')]
    assert computed and all(row['verdict'] == 'rejected_computed_only' for row in computed)


def test_empty_result_registered_and_refusal_triggers() -> None:
    payload = _summary()
    assert payload['n_anchors'] == 0
    assert payload['n_pairs_effective'] == 0
    assert payload['refusal_branch'] is True
    assert any(row['verdict'] == 'not_available_on_disk' for row in payload['ledger_rows'])


def test_layer_admission_only_pubchemqc() -> None:
    payload = _summary()
    admitted = sorted(row['layer'] for row in payload['layer_rows'] if row['verdict'] == 'admitted')
    assert admitted == ['pubchemqc']
    assert all(row['verdict'] == 'refused' for row in payload['layer_rows']
               if row['registered_verdict'] == 'unregistered')


def test_anchor_tables_pinned_readonly() -> None:
    payload = _summary()
    pins = {Path(pin['path']).name: pin for pin in payload['table_pins']}
    assert set(pins) == {'w46_reduction_anchor_candidates.csv', 'w46_reduction_anchor_ledger.csv'}
    for name, expected_rows in (
        ('w46_reduction_anchor_candidates.csv',
         len(payload['column_rows']) + len(payload['named_rows'])),
        ('w46_reduction_anchor_ledger.csv', len(payload['ledger_rows'])),
    ):
        pin = pins[name]
        path = ART / name
        assert path.is_file() and path.stat().st_size > 0
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pin['sha256']
        with path.open(encoding='utf-8', newline='') as handle:
            rows = sum(1 for _ in csv.DictReader(handle))
        assert rows == pin['rows'] == expected_rows


def test_artifacts_and_prereg_exist() -> None:
    for path in (CANDIDATES_CSV, LEDGER_CSV, REPORT, PROBE):
        assert path.is_file() and path.stat().st_size > 0
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    assert prereg['status'] == 'locked_before_run'
    assert prereg['gates']['n_pairs_effective_formula'] == 'n_pairs_effective = C(n_anchors, 2)'
