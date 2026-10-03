# Guards for the Week 34-A legality registry / dashboard / gate guard lane.
#
# Week 33-A turned state legality into a front gate, but the verdict lived only inside a
# report and a summary: nothing on disk could stop a downstream reader from quoting a
# reduction-axis number measured on unbound states.  Week 34-A writes the verdict down as
# an authoritative table (one row per level x medium x molecule), ships a guard that
# raises instead of returning None, and pools the four channels into one dashboard.
#
# The guards pin exactly that:
#
#   * the registry has the declared shape and its legality column is a pure conjunction;
#   * the reason column follows the registered priority geom > homo > ea;
#   * the registry agrees with the Week 33-A gates table medium by medium;
#   * the guard refuses an undersized legal subset and reproduces the Week 33-A tau_b;
#   * the lane is post hoc, takes no shot, and leaves the four frozen readings alone.
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w34_legality_registry as probe

REGISTRY = ROOT / 'data' / 'processed' / 'redox_state_legality_registry.csv'
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w34_legality_registry_summary.json'
DASHBOARD_CSV = ROOT / 'probes' / 'artifacts' / 'w34_channel_dashboard.csv'
DASHBOARD_MD = ROOT / 'probes' / 'artifacts' / 'w34_channel_dashboard.md'
FIGURE = ROOT / 'probes' / 'artifacts' / 'w34_legality_registry.png'
REPORT = ROOT / 'reports' / 'w34_legality_registry.md'
GATES = ROOT / 'probes' / 'artifacts' / 'w33_bound_state_gate_gates.csv'

EXPECTED_ROWS = 1028
EXPECTED_GFN2_ROWS = 984
CHANNELS = {'dielectric', 'viscosity', 'orbital', 'redox'}
ANCHOR_TAU_LEGAL_GAS = 0.7450980392156863
ANCHOR_TAU_LEGAL_WATER = 0.8119565217391304


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def _registry() -> list[dict]:
    return _rows(REGISTRY)


def test_lane_is_post_hoc_and_takes_no_shot() -> None:
    payload = _summary()
    assert payload['task'] == 'week34_legality_registry'
    assert int(payload['ledger']['main_scoreboard_shots_this_week']) == 0
    assert int(payload['ledger']['cumulative_main_scoreboard_attempts_after']) == 19


def test_registry_has_the_declared_shape() -> None:
    rows = _registry()
    assert len(rows) == EXPECTED_ROWS
    assert sum(1 for row in rows if row['level'] == 'gfn2') == EXPECTED_GFN2_ROWS
    assert sum(1 for row in rows if row['level'] == 'orca') == EXPECTED_ROWS - EXPECTED_GFN2_ROWS
    assert {row['level'] for row in rows} == {'gfn2', 'orca'}
    assert len({row['inchikey'] for row in rows if row['level'] == 'gfn2'}) == 246


def test_legal_is_the_conjunction_and_reason_follows_priority() -> None:
    for row in _registry():
        geom = int(row['geom_ok'])
        homo = int(row['homo_bound'])
        ea = int(row['ea_positive'])
        legal = int(row['legal'])
        assert legal == int(bool(geom and homo and ea))
        if legal:
            assert row['reason'] == ''
        elif not geom:
            assert row['reason'] == 'geom'
        elif not homo:
            assert row['reason'] == 'homo'
        else:
            assert row['reason'] == 'ea'


def test_registry_agrees_with_the_week33_gates_table() -> None:
    registry = _registry()
    for entry in _rows(GATES):
        raw = str(entry['medium'])
        level = 'orca' if raw.startswith('orca_') else 'gfn2'
        medium = raw[5:] if level == 'orca' else raw
        legal = sum(int(row['legal']) for row in registry
                    if row['level'] == level and row['medium'] == medium)
        assert legal == int(entry['legal']), raw


def test_registry_rows_are_a_superset_of_the_gate_summary_reading() -> None:
    payload = _summary()
    register = {(entry['level'], entry['medium']): entry for entry in payload['register']}
    assert set(register) == {('gfn2', medium) for medium in ('gas', 'thf', 'benzaldehyde', 'water')} \
        | {('orca', medium) for medium in ('gas', 'smd_acetonitrile')}
    gas = register[('gfn2', 'gas')]
    assert gas['rows'] == 246 and gas['legal'] == 52
    orca_gas = register[('orca', 'gas')]
    assert orca_gas['legal'] == 0


def test_guard_refuses_an_undersized_legal_subset() -> None:
    rows = _registry()
    try:
        probe.assert_redox_readable(rows, 'orca', 'gas')
    except probe.RedoxGateRefusal as error:
        assert '不可判定' in str(error)
    else:
        raise AssertionError('the guard must refuse the ORCA gas layer')


def test_guard_allows_a_large_enough_legal_subset() -> None:
    rows = _registry()
    reading = probe.assert_redox_readable(rows, 'gfn2', 'gas')
    assert reading['legal'] == 52
    assert reading['rows'] == 246


def test_reading_reproduces_the_week33_tau_b_anchors() -> None:
    census_rows = probe.read_rows(probe.REDOX_LAYER)
    orca_rows = probe.read_rows(probe.ORCA_LAYER)
    gas = probe.redox_reading(census_rows, orca_rows, 'gfn2', 'gas')
    water = probe.redox_reading(census_rows, orca_rows, 'gfn2', 'water')
    assert gas['legal'] == 52 and gas['rows'] == 52
    assert water['legal'] == 161
    assert abs(gas['tau_b'] - ANCHOR_TAU_LEGAL_GAS) <= 1e-12
    assert abs(water['tau_b'] - ANCHOR_TAU_LEGAL_WATER) <= 1e-12


def test_reading_refuses_instead_of_returning_none() -> None:
    census_rows = probe.read_rows(probe.REDOX_LAYER)
    orca_rows = probe.read_rows(probe.ORCA_LAYER)
    try:
        probe.redox_reading(census_rows, orca_rows, 'orca', 'gas')
    except probe.RedoxGateRefusal:
        pass
    else:
        raise AssertionError('redox_reading must raise, never return None')


def test_dashboard_covers_the_four_channels() -> None:
    rows = _rows(DASHBOARD_CSV)
    assert {row['channel'] for row in rows} == CHANNELS
    redox = [row for row in rows if row['channel'] == 'redox']
    assert len(redox) == 1
    assert redox[0]['gate_applies'] == '1'
    assert redox[0]['gate_status'].startswith('GFN2 气相合法')
    for row in rows:
        assert float(row['n_population']) > 0.0
        assert float(row['sd_at_n12']) > 0.0
        assert float(row['min_n_for_sd_0_05']) > 0.0


def test_dashboard_sd_matches_the_closed_form() -> None:
    for row in _rows(DASHBOARD_CSV):
        s0 = float(row['s0'])
        n_pop = float(row['n_population'])
        expected = s0 * (1.0 / 12.0 - 1.0 / n_pop) ** 0.5
        assert abs(float(row['sd_at_n12']) - expected) < 1e-12


def test_all_criteria_hold() -> None:
    payload = _summary()
    verdicts = {item['id']: item['verdict'] for item in payload['criteria']}
    assert verdicts == {'H34a': '成立', 'H34b': '成立', 'H34c': '成立',
                        'H34d': '成立', 'H34e': '成立'}


def test_inputs_keep_their_recorded_sha256() -> None:
    for entry in _summary()['inputs']:
        path = ROOT / entry['path']
        assert path.is_file(), entry['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']


def test_text_artifacts_are_lf_without_bom() -> None:
    for path in (REGISTRY, SUMMARY, DASHBOARD_CSV, DASHBOARD_MD, REPORT):
        raw = path.read_bytes()
        assert not raw.startswith(bytes([239, 187, 191])), path.name
        assert bytes([13, 10]) not in raw, path.name
    assert FIGURE.is_file()
    assert FIGURE.stat().st_size > 0


def test_metric_names_still_frozen_at_seven() -> None:
    import dielectric_auc_sidecar as sidecar
    assert len(sidecar.EXPECTED_METRIC_NAMES) == 7
    assert 'auc_gt30' not in sidecar.EXPECTED_METRIC_NAMES