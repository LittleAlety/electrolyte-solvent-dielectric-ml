# Guards for Week 47 lane W47-C: the D2 (r2SCAN-3c) + D3 (ddCOSMO) protocol freeze and the ORCA
# compute-debt registration.  The nitrile triad must be complete (3 solvents x 3 checks), no value
# may be fabricated without ORCA, and dipole_transfer_v1 must stay registered_not_authorized.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w47_lane_c_summary.json'
PLAN_CSV = ART / 'w47_lane_c_plan.csv'
REPORT = ROOT / 'reports' / 'w47_lane_c_plan.md'
PREREG = ROOT / 'probes' / 'w47_orca_rerun_prereg.json'
PROBE = ROOT / 'probes' / 'w47_lane_c_plan.py'

CRITERIA_IDS = ['H47c' + str(index) for index in range(1, 10)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
NITRILE_SOLVENTS = ['GN', 'MPN', 'BC']
NITRILE_ITEMS = ['somo_spatial_extent', 'dipole_bound_state_test', 'legality_registry_entry']


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w47_orca_rerun/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS
    assert payload['registered_negatives'] == []


def test_nine_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 9


def test_protocol_groups_complete() -> None:
    payload = _summary()
    assert payload['groups'] == {'d2_r2scan3c': 6, 'd3_ddcosmo': 4, 'nitrile_check': 9,
                                 'rerun': 1, 'external': 1}
    assert payload['n_items'] == 21
    assert payload['conformer_report_required'] is True


def test_nitrile_triad_complete() -> None:
    payload = _summary()
    pairs = {tuple(pair) for pair in payload['nitrile_pairs']}
    expected = {(s, i) for s in NITRILE_SOLVENTS for i in NITRILE_ITEMS}
    assert pairs == expected
    assert payload['nitrile_complete'] is True
    with PLAN_CSV.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    nitrile = [row for row in rows if row['group'] == 'nitrile_check']
    assert len(nitrile) == 9
    assert {row['target'] for row in nitrile} == set(NITRILE_SOLVENTS)


def test_no_fabricated_values_without_orca() -> None:
    payload = _summary()
    assert payload['orca_available'] is False
    assert payload['compute_status']['status'] == 'pending_orca_compute'
    with PLAN_CSV.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert all(row['status'] in ('pending_orca_compute', 'pending_after_orca_compute',
                                 'registered_not_authorized') for row in rows)
    dipole = [row for row in rows if row['item_id'] == 'dipole_transfer_v1']
    assert len(dipole) == 1
    assert dipole[0]['status'] == 'registered_not_authorized'


def test_estimate_is_reproducible() -> None:
    payload = _summary()
    estimate = payload['estimate']
    assert estimate['d2_r2scan3c']['value'] == 7 * 2 * 3
    assert estimate['d3_ddcosmo']['value'] == 7 * 4
    assert estimate['nitrile_check']['value'] == 3 * 2
    assert estimate['total'] == 76
    assert '估算' in estimate['disclaimer']


def test_artifacts_and_prereg_exist() -> None:
    for path in (PLAN_CSV, REPORT, PROBE):
        assert path.is_file() and path.stat().st_size > 0
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    assert prereg['status'] == 'locked_before_run'
    assert prereg['compute_status']['orca_available'] is False
    assert prereg['gates']['nitrile_items_required'] == 3
