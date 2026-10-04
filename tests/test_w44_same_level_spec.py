# Guards for the Week 44 lane W44-C: the strict same_level spec and the in-repo candidate audit.
# strict same_level means all four attributes (functional / basis_set / phase / geometry_source)
# match plus an independent provenance; no in-repo layer matches the Batt target, the closest pair
# is QM9-vs-PubChemQC at attribute distance two, and near_same_level may only be declared when the
# functional and the phase both match.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w44_same_level_spec_summary.json'
SPEC = ART / 'w44_same_level_spec.json'
CANDIDATES = ART / 'w44_layer_candidates.csv'
REPORT = ROOT / 'reports' / 'w44_same_level_spec.md'
PROBE = ROOT / 'probes' / 'w44_same_level_spec.py'
PREREG = ROOT / 'probes' / 'w44_governance_wiring_prereg.json'

CRITERIA_IDS = ['H44c' + str(index) for index in range(1, 9)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
ATTRIBUTES = ['functional', 'basis_set', 'phase', 'geometry_source']


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w44_same_level_spec/summary@1'
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


def test_spec_attributes_frozen_in_order() -> None:
    payload = _summary()
    assert payload['spec_attributes'] == ATTRIBUTES


def test_no_strict_same_level_with_target() -> None:
    payload = _summary()
    assert payload['strict_same_level_with_target'] == 0
    assert payload['strict_pairs'] == []
    assert payload['target_layer'] == 'batt'
    assert payload['target_role'] == 'target'


def test_closest_pair_is_qm9_pubchemqc_at_distance_two() -> None:
    payload = _summary()
    assert payload['closest_pair'] == 'qm9-pubchemqc'
    assert payload['closest_distance'] == 2


def test_near_same_level_is_licensed_only() -> None:
    payload = _summary()
    assert sorted(payload['near_pairs']) == ['qm9-pubchemqc', 'xtb-expanded']
    assert payload['unlicensed_near'] == []
    for row in payload['pairs']:
        if row['near_same_level_eligible']:
            assert row['functional_match'] is True
            assert row['phase_match'] is True


def test_artifacts_exist_and_are_lf_only() -> None:
    for path in (SUMMARY, SPEC, CANDIDATES, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (CANDIDATES, REPORT, PROBE, PREREG):
        data = _bytes(path)
        assert not data.startswith(b'\xef\xbb\xbf'), path
        assert b'\r\n' not in data, path
    with CANDIDATES.open('r', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 6
    assert {row['layer'] for row in rows} >= {'batt', 'qm9', 'pubchemqc', 'xtb'}
