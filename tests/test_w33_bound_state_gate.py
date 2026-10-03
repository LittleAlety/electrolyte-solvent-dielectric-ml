# Guards for the Week 33-A bound-state gate lane (post hoc, no shot).
#
# The parent paper stopped at a diagnosis: the reduction-axis tau_b flips sign when the
# electronic-structure level moves (GFN2 +0.835 vs ORCA -0.602), and most gas-phase
# anions are not bound.  Week 33-A promotes state legality from a post hoc caveat to a
# front gate with an explicit refusal queue: geom AND homo AND ea, and a layer whose
# legal subset is smaller than five molecules refuses to report a number at all.
#
# The guards pin exactly that:
#
#   * the pre-registration is locked before the run and the recorded hash matches;
#   * the homo clause is exactly "anion HOMO < 0" and the ea clause exactly "EA > 0";
#   * refusal is not a missing value -- an undersized legal subset yields None, never 0;
#   * the three reproduction anchors hit bit for bit;
#   * the H33e prediction that failed is registered as failed, not rewritten.
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w33_bound_state_gate as probe

PREREG = ROOT / 'probes' / 'w33_bound_state_gate_prereg.json'
SUMMARY = probe.SUMMARY_PATH
GATES = probe.GATES_CSV
REFUSE = probe.REFUSE_CSV
READINGS = probe.READINGS_CSV
FIGURE = probe.FIGURE_PATH
REPORT = probe.REPORT_PATH

ANCHOR_GFN2 = 0.8354978354978355
ANCHOR_ORCA = -0.6017316017316018
ANCHOR_UNBOUND = 0.7642276422764228
CENSUS_ROWS = 246
HOMO_SIGNATURE_EV = 0.0  # probes/w23_redox_dscf.py::UNBOUND_HOMO_SIGNATURE_EV


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def _synthetic_pair(legal_count: int, total: int) -> tuple[list[dict], list[dict]]:
    census, orca = [], []
    for index in range(total):
        legal = index < legal_count
        key = 'SYNTH' + str(index).zfill(3)
        census.append({
            'inchikey': key, 'name': 'm' + str(index),
            'gas_neutral_lumo_eV': '-1.0',
            'gas_anion_status': 'ok',
            'anion_unbound_gas': 'no' if legal else 'yes',
            'gas_anion_homo_eV': '-0.5' if legal else '0.5',
            'ea_gas_eV': '0.5' if legal else '-0.5',
        })
        orca.append({
            'inchikey': key, 'name': 'm' + str(index),
            'p0_red_eV': '-1.0',
            'orca_gas_anion_status': 'ok',
            'orca_anion_unbound_gas': 'no' if legal else 'yes',
            'orca_gas_anion_homo_eV': '-0.5' if legal else '0.5',
            'orca_ea_gas_eV': '0.5' if legal else '-0.5',
            'orca_smd_acetonitrile_anion_status': 'ok',
            'orca_anion_unbound_smd_acetonitrile': 'no' if legal else 'yes',
            'orca_smd_acetonitrile_anion_homo_eV': '-0.5' if legal else '0.5',
            'orca_ea_smd_acetonitrile_eV': '0.5' if legal else '-0.5',
        })
    return census, orca


def test_lane_is_post_hoc_and_takes_no_shot() -> None:
    payload = _summary()
    assert payload['task'] == 'week33_bound_state_gate'
    assert int(payload['ledger']['main_scoreboard_shots_this_week']) == 0
    assert int(payload['ledger']['cumulative_main_scoreboard_attempts_after']) == 19


def test_preregistration_is_locked_and_hashed() -> None:
    payload = _summary()
    prereg = payload['preregistration']
    assert prereg['status'] == 'locked_before_run'
    assert int(prereg['revision']) == 1
    assert prereg['path'] == 'probes/w33_bound_state_gate_prereg.json'
    clauses = {item['id']: item for item in payload['gate']['clauses']}
    assert float(clauses['homo']['threshold_ev']) == HOMO_SIGNATURE_EV
    assert float(clauses['ea']['threshold_ev']) == 0.0
    assert hashlib.sha256(PREREG.read_bytes()).hexdigest() == prereg['sha256']


def test_inputs_keep_their_recorded_sha256() -> None:
    payload = _summary()
    assert len(payload['inputs']) == 3
    for entry in payload['inputs']:
        path = probe.REPOSITORY_ROOT / entry['path']
        assert path.is_file(), entry['path']
        assert probe.sha256_file(path) == entry['sha256']
        assert int(entry['rows']) == len(_rows(path))


def test_homo_clause_is_exactly_anion_homo_below_zero() -> None:
    rows = _rows(probe.REDOX_LAYER)
    assert len(rows) == CENSUS_ROWS
    for medium, _, _ in probe.MEDIA:
        for row in rows:
            flag = probe.census_gate(row, medium)
            raw = probe.as_float(row.get(medium + '_anion_homo_eV'))
            expected = str(row.get('anion_unbound_' + medium, '')).strip() == 'no'
            assert flag['homo'] == expected
            if raw is not None:
                assert flag['homo'] == (raw < HOMO_SIGNATURE_EV)


def test_ea_clause_is_exactly_positive_electron_affinity() -> None:
    rows = _rows(probe.REDOX_LAYER)
    for medium, _, _ in probe.MEDIA:
        for row in rows:
            flag = probe.census_gate(row, medium)
            raw = probe.as_float(row.get('ea_' + medium + '_eV'))
            if raw is not None:
                assert flag['ea'] == (raw > 0.0)


def test_legal_flag_is_the_conjunction_and_reason_follows_priority() -> None:
    rows = _rows(probe.REDOX_LAYER)
    for medium, _, _ in probe.MEDIA:
        for row in rows:
            flag = probe.census_gate(row, medium)
            assert flag['legal'] == (flag['geom'] and flag['homo'] and flag['ea'])
            if flag['legal']:
                assert flag['reason'] == ''
            elif not flag['geom']:
                assert flag['reason'] == 'geom'
            elif not flag['homo']:
                assert flag['reason'] == 'homo'
            else:
                assert flag['reason'] == 'ea'


def test_refusal_rule_returns_none_below_the_minimum_legal_subset() -> None:
    census, orca = _synthetic_pair(1, 3)
    refuse: list[dict] = []
    entries, _, _ = probe.analyse_orca(census, orca, refuse)
    for entry in entries:
        assert int(entry['legal']) == 1
        assert entry['tau_legal'] is None
        assert int(entry['tau_legal_rows']) == 0
        assert entry['verdict'] == '不可判定'
    assert len(refuse) == 2 * (3 - 1)


def test_refusal_rule_reports_a_number_once_the_subset_is_large_enough() -> None:
    census, orca = _synthetic_pair(6, 8)
    entries, _, _ = probe.analyse_orca(census, orca, [])
    for entry in entries:
        assert int(entry['legal']) == 6
        assert entry['tau_legal'] is not None
        assert int(entry['tau_legal_rows']) == 6
        assert entry['verdict'] == '可宣读'


def test_reproduction_anchors_hit_bit_for_bit() -> None:
    payload = _summary()
    anchors = {item['id']: item for item in payload['anchors']}
    assert set(anchors) == {'A1', 'A2', 'A3'}
    assert anchors['A1']['value'] == ANCHOR_GFN2
    assert anchors['A2']['value'] == ANCHOR_ORCA
    assert anchors['A3']['value'] == ANCHOR_UNBOUND
    for item in payload['anchors']:
        assert item['verdict'] == '成立'


def test_anchor_a3_recomputes_from_the_raw_census() -> None:
    rows = _rows(probe.REDOX_LAYER)
    share = sum(1 for row in rows
                if str(row.get('anion_unbound_gas', '')).strip() == 'yes') / len(rows)
    assert abs(share - ANCHOR_UNBOUND) <= 1e-12


def test_criteria_verdicts_are_registered_including_the_failure() -> None:
    payload = _summary()
    verdicts = {item['id']: item['verdict'] for item in payload['criteria']}
    assert verdicts['H33e'] == '判否'
    for identifier in ('H33a', 'H33b', 'H33c', 'H33d', 'H33f'):
        assert verdicts[identifier] == '成立', identifier


def test_gates_csv_counts_are_consistent() -> None:
    rows = _rows(GATES)
    assert len(rows) == len(probe.MEDIA) + len(probe.ORCA_MEDIA)
    for row in rows:
        total = int(row['rows'])
        legal = int(row['legal'])
        assert legal == total - int(row['geom_fail']) - int(row['homo_refused']) - int(row['ea_refused'])
        assert abs(float(row['pass_rate']) - legal / total) < 1e-12
        assert abs(float(row['refusal_rate']) - (total - legal) / total) < 1e-12
        assert abs(float(row['pass_rate']) + float(row['refusal_rate']) - 1.0) < 1e-12
        if legal < probe.MIN_LEGAL_SUBSET:
            assert row['tau_legal'] == ''
            assert row['verdict'] == '不可判定'
        else:
            assert row['tau_legal'] != ''
            assert row['verdict'] == '可宣读'


def test_refuse_queue_accounts_for_every_non_legal_row() -> None:
    expected = sum(int(row['rows']) - int(row['legal']) for row in _rows(GATES))
    refuse = _rows(REFUSE)
    assert len(refuse) == expected
    assert {row['reason'] for row in refuse} <= {'geom', 'homo', 'ea'}
    assert all(row['name'] for row in refuse)


def test_gate_lowers_the_reduction_axis_tau_b_on_every_gfn2_medium() -> None:
    payload = _summary()
    assert len(payload['census']) == 4
    for entry in payload['census']:
        assert entry['tau_legal'] is not None
        assert float(entry['tau_legal']) < float(entry['tau_all'])


def test_orca_layers_are_declared_undecidable_not_imputed() -> None:
    payload = _summary()
    assert len(payload['orca']) == 2
    for entry in payload['orca']:
        assert int(entry['legal']) < probe.MIN_LEGAL_SUBSET
        assert entry['tau_legal'] is None
        assert int(entry['tau_legal_rows']) == 0
        assert entry['verdict'] == '不可判定'


def test_cross_table_partitions_the_paired_set() -> None:
    cross = _summary()['cross']
    parts = (cross['both_legal'] + cross['gfn2_only']
             + cross['orca_only'] + cross['neither'])
    assert parts == int(cross['n_paired'])
    assert abs(float(cross['inconsistent_share'])
               - cross['gfn2_only'] / cross['n_paired']) < 1e-12
    assert abs(float(cross['agreement_share'])
               - (cross['both_legal'] + cross['neither']) / cross['n_paired']) < 1e-12


def test_readings_csv_carries_the_undecidable_layers_as_blank() -> None:
    readings = {row['reading']: row['value'] for row in _rows(READINGS)}
    for key in ('orca_gas|tau_legal', 'orca_smd_acetonitrile|tau_legal'):
        assert key in readings
        assert readings[key] == ''
    assert float(readings['gas|tau_all']) == 0.8264295676429568


def test_text_artifacts_are_lf_without_bom() -> None:
    for path in (PREREG, SUMMARY, GATES, REFUSE, READINGS, REPORT):
        raw = path.read_bytes()
        assert not raw.startswith(bytes([239, 187, 191])), path.name
        assert bytes([13, 10]) not in raw, path.name
    assert FIGURE.is_file()
    assert FIGURE.stat().st_size > 0


def test_report_states_the_undecidable_verdict_explicitly() -> None:
    text = REPORT.read_text(encoding='utf-8')
    assert '不可判定' in text
    assert '拒答' in text