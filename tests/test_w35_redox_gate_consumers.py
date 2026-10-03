# Guards for the Week 35-A lane: the gate bypass layer and the consumer audit.
#
# Week 34-A shipped a guard (assert_redox_readable) and an authoritative registry, but
# nothing forced a downstream reader to call them: the paper, the appendix and the
# decision log quoted -0.602 / +0.835 with no gate verdict attached.  Week 35-A adds a
# per-molecule bypass table, registers every reduction-axis reference point and evaluates
# its mark *through the Week 34-A guard*, and audits seven downstream consumers.
#
# The guards pin:
#
#   * the bypass table is a pure derivative of the Week 34 registry (digit for digit);
#   * the registry sha256 and the four-core registry sha256 are untouched;
#   * every registered mark is what the Week 34-A guard returns, including the refusals;
#   * the oxidation-axis rows are registered as out of scope, not as readable;
#   * the consumer audit fails on the reconstructed pre-correction paper and passes now;
#   * the lane is post hoc, takes no shot, and writes LF without a BOM.
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w34_legality_registry as registry_mod
import w35_redox_gate_consumers as probe

REGISTRY = ROOT / 'data' / 'processed' / 'redox_state_legality_registry.csv'
SIDECAR = ROOT / 'data' / 'processed' / 'redox_readability_sidecar.csv'
REGISTER = ROOT / 'probes' / 'artifacts' / 'w35_gated_reference_register.csv'
AUDIT = ROOT / 'probes' / 'artifacts' / 'w35_gated_consumer_audit.csv'
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w35_redox_gate_consumers_summary.json'
REPORT = ROOT / 'reports' / 'w35_redox_gate_consumers.md'
FIGURE = ROOT / 'probes' / 'artifacts' / 'w35_redox_gate_consumers.png'
PREREG = ROOT / 'probes' / 'w35_paper_r6_correction_prereg.json'
PAPER = ROOT / 'paper' / 'paper_zh_draft_v2.md'

REGISTRY_SHA256 = 'a01272b3e75514a609295275d18c82c39fb65c5bc27056feb4ed8c6cd0c6b60d'
FOUR_CORE_SHA256 = 'e42885eb43779b7a4d472da88fefe018fe94150ff5b6fba86b3ed9bc83dc8bee'
EXPECTED_SIDECAR_ROWS = 246
EXPECTED_REFERENCE_ROWS = 10
EXPECTED_CONSUMERS = 7


def _rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_lane_is_post_hoc_and_takes_no_shot() -> None:
    payload = _summary()
    assert payload['task'] == 'week35_redox_gate_consumers'
    assert int(payload['ledger']['main_scoreboard_shots_this_week']) == 0
    assert int(payload['ledger']['cumulative_main_scoreboard_attempts_after']) == 19
    assert payload['gate']['scope'].startswith('阴离子态审计')


def test_sidecar_is_one_row_per_key_and_a_pure_derivative() -> None:
    registry = _rows(REGISTRY)
    sidecar = _rows(SIDECAR)
    assert len(sidecar) == EXPECTED_SIDECAR_ROWS
    assert len({row['inchikey'] for row in sidecar}) == EXPECTED_SIDECAR_ROWS
    keyed = {(row['level'], row['medium'], row['inchikey']): row for row in registry}
    compared = 0
    for row in sidecar:
        for level, field in (('gfn2', 'gfn2'), ('orca', 'orca')):
            for medium in [name for name, _, _ in registry_mod.gate.MEDIA
                           if level == 'gfn2'] + [name for name, _, _ in registry_mod.gate.ORCA_MEDIA
                                                  if level == 'orca']:
                source = keyed.get((level, medium, row['inchikey']))
                if source is None:
                    continue
                compared += 1
                assert str(row[field + '_' + medium + '_legal']) == str(source['legal'])
                assert row[field + '_' + medium + '_reason'] == source['reason']
    assert compared == EXPECTED_SIDECAR_ROWS * 4 + 22 * 2


def test_sidecar_marks_who_is_in_the_paired_set() -> None:
    registry = _rows(REGISTRY)
    paired = {row['inchikey'] for row in registry if row['level'] == 'orca'}
    assert len(paired) == 22
    sidecar = {row['inchikey']: row for row in _rows(SIDECAR)}
    assert sum(int(row['in_paired_orca']) for row in sidecar.values()) == 22
    for key, row in sidecar.items():
        if key in paired:
            assert row['readable_orca'] in ('有介质可宣读', '全介质不可判定')
        else:
            assert row['readable_orca'] == '无 ORCA 数据'
            assert row['n_orca_legal_media'] == ''


def test_frozen_inputs_are_untouched() -> None:
    assert hashlib.sha256(REGISTRY.read_bytes()).hexdigest() == REGISTRY_SHA256
    four_core = ROOT / 'data' / 'processed' / 'four_core_key_registry.csv'
    assert hashlib.sha256(four_core.read_bytes()).hexdigest() == FOUR_CORE_SHA256


def test_registered_marks_come_from_the_week34_guard() -> None:
    registry = _rows(REGISTRY)
    paired = {row['inchikey'] for row in registry if row['level'] == 'orca'}
    all_keys = {row['inchikey'] for row in registry if row['level'] == 'gfn2'}
    population = {'paired_orca_22': paired, 'census_246': all_keys}
    register = _rows(REGISTER)
    assert len(register) == EXPECTED_REFERENCE_ROWS
    assert {row['reference_id'] for row in register} == {
        'r6_ox_gfn2', 'r6_ox_orca', 'r6_red_gfn2', 'r6_red_orca',
        'w33a_gfn2_gas', 'w33a_gfn2_thf', 'w33a_gfn2_benzaldehyde', 'w33a_gfn2_water',
        'w33a_orca_gas', 'w33a_orca_smd_acetonitrile'}
    checked = 0
    for row in register:
        keys = population[row['population_scope']]
        subset = [item for item in registry
                  if item['level'] == row['level'] and item['medium'] == row['medium']
                  and item['inchikey'] in keys]
        assert len(subset) == int(row['population_n'])
        if row['axis'] == 'oxidation':
            assert row['mark'] == probe.MARK_ID_APPLICABLE
            assert row['guard_verdict'] == 'not_applicable'
            assert row['legal_n'] == ''
            continue
        checked += 1
        legal = sum(int(item['legal']) for item in subset)
        assert legal == int(row['legal_n'])
        try:
            info = registry_mod.assert_redox_readable(subset, row['level'], row['medium'])
        except registry_mod.RedoxGateRefusal:
            assert row['mark'] == probe.MARK_TOKEN
            assert row['guard_verdict'] == 'refused'
            # A refused gate reading has no value; an R6 point keeps its historical
            # value and carries the mark, which is the whole point of the register.
            if row['quantity'] == 'tau_legal':
                assert row['quoted_value'] == ''
            else:
                assert row['quoted_value'] != ''
        else:
            assert row['mark'] == probe.MARK_READABLE
            assert row['guard_verdict'] == 'allowed'
            assert int(info['legal']) == legal
    assert checked == 8


def test_the_r6_reduction_anchors_are_refused_and_oxidation_is_out_of_scope() -> None:
    register = {row['reference_id']: row for row in _rows(REGISTER)}
    assert register['r6_red_gfn2']['legal_n'] == '1'
    assert register['r6_red_gfn2']['mark'] == probe.MARK_TOKEN
    assert register['r6_red_orca']['legal_n'] == '0'
    assert register['r6_red_orca']['mark'] == probe.MARK_TOKEN
    assert register['r6_red_orca']['quoted_value'] == '-0.6017316017316018'
    assert register['r6_ox_gfn2']['quoted_value'] == '0.6969696969696969'
    assert register['w33a_gfn2_gas']['legal_n'] == '52'
    assert register['w33a_gfn2_gas']['mark'] == probe.MARK_READABLE
    assert register['w33a_orca_gas']['quoted_value'] == ''
    assert register['w33a_orca_smd_acetonitrile']['mark'] == probe.MARK_TOKEN


def test_the_same_cell_is_readable_on_the_census_and_refused_on_the_paired_set() -> None:
    """The population scope has to be quoted with the reading."""
    registry = _rows(REGISTRY)
    paired = {row['inchikey'] for row in registry if row['level'] == 'orca'}
    census_gas = [row for row in registry if row['level'] == 'gfn2' and row['medium'] == 'gas']
    paired_gas = [row for row in census_gas if row['inchikey'] in paired]
    assert registry_mod.assert_redox_readable(census_gas, 'gfn2', 'gas')['legal'] == 52
    with pytest.raises(registry_mod.RedoxGateRefusal):
        registry_mod.assert_redox_readable(paired_gas, 'gfn2', 'gas')


def test_consumer_audit_passes_now_and_failed_before() -> None:
    payload = _summary()
    audit = _rows(AUDIT)
    assert len(audit) == EXPECTED_CONSUMERS
    assert all(int(row['mark_present']) == 1 for row in audit)
    assert all(row['verdict'] == '成立' for row in audit)
    assert payload['audit']['missing_after'] == []
    assert set(payload['audit']['missing_before']) == {
        'paper_s320', 'paper_appendix_a', 'paper_conclusion'}

    prereg = json.loads(PREREG.read_text(encoding='utf-8'))
    paper = PAPER.read_text(encoding='utf-8')
    before = probe.reconstruct_before(paper, prereg)
    texts = {path: (ROOT / path).read_text(encoding='utf-8')
             for path in {item['path'] for item in probe.CONSUMERS}}
    texts['paper/paper_zh_draft_v2.md'] = before
    audit_before = probe.audit_consumers(texts)
    missing = [row['consumer_id'] for row in audit_before if row['mark_present'] != 1]
    assert missing == payload['audit']['missing_before']


def test_five_criteria_hold_and_artifacts_are_lf() -> None:
    payload = _summary()
    verdicts = {item['id']: item['verdict'] for item in payload['criteria']}
    assert set(verdicts) == {'H35a', 'H35b', 'H35c', 'H35d', 'H35e'}
    assert all(value == '成立' for value in verdicts.values())
    for path in (SIDECAR, REGISTER, AUDIT, SUMMARY, REPORT):
        payload_bytes = path.read_bytes()
        assert b'\r' not in payload_bytes
        assert not payload_bytes.startswith(b'\xef\xbb\xbf')
    assert int(payload['sidecar']['mismatches']) == 0
    assert FIGURE.is_file() and FIGURE.stat().st_size > 0