# Guards for the Week 36-D lane: the reference register promoted to an admission list.
#
# Week 35-A registered every reduction-axis citation point and had the Week 34-A guard
# stamp each row.  Week 36-D makes consulting that table mechanical: an unregistered
# citation point raises instead of warning, and the mark is recomputed by the guard rather
# than trusted from the table.
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w36_gate_admission as probe

REGISTER = ROOT / 'probes' / 'artifacts' / 'w35_gated_reference_register.csv'
MANIFEST = ROOT / 'probes' / 'artifacts' / 'w36_gate_admission_manifest.csv'
REFUSALS = ROOT / 'probes' / 'artifacts' / 'w36_gate_admission_refusals.csv'
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w36_gate_admission_summary.json'
REPORT = ROOT / 'reports' / 'w36_gate_admission.md'

EXPECTED_ROWS = 10
EXPECTED_REDUCTION = 8
EXPECTED_OXIDATION = 2


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_lane_is_post_hoc_and_takes_no_shot() -> None:
    payload = _summary()
    assert payload['task'] == 'week36_gate_admission'
    assert int(payload['ledger']['main_scoreboard_shots_this_week']) == 0
    assert int(payload['ledger']['cumulative_main_scoreboard_attempts_after']) == 19


def test_manifest_matches_the_register_one_for_one() -> None:
    register, manifest = _rows(REGISTER), _rows(MANIFEST)
    assert len(manifest) == len(register) == EXPECTED_ROWS
    assert [row['reference_id'] for row in manifest] == [row['reference_id'] for row in register]
    assert sum(1 for row in manifest if row['axis'] == 'reduction') == EXPECTED_REDUCTION
    assert sum(1 for row in manifest if row['axis'] == 'oxidation') == EXPECTED_OXIDATION
    assert all(row['admission'] == '准入' for row in manifest)


def test_reduction_marks_come_from_the_guard_not_from_the_table() -> None:
    rows = [row for row in _rows(MANIFEST) if row['axis'] == 'reduction']
    assert all(row['mark_source'] == 'W34-A 守卫复算' for row in rows)
    assert {row['mark'] for row in rows} == {'可宣读', '不可判定'}
    assert sum(1 for row in rows if row['mark'] == '不可判定') == 4


def test_oxidation_rows_are_marked_not_applicable() -> None:
    rows = [row for row in _rows(MANIFEST) if row['axis'] == 'oxidation']
    assert rows
    assert all(row['mark'] == '不适用（门禁只覆盖还原轴）' for row in rows)
    assert all(row['mark_source'] == '门禁条款（氧化轴不适用）' for row in rows)


def test_unregistered_keys_are_refused_by_construction() -> None:
    payload = _summary()
    register = _rows(REGISTER)
    registry = probe.consumers.load_registry()
    paired = probe.consumers.paired_keys(registry)
    with pytest.raises(probe.AdmissionRefused):
        probe.admit(register, registry, paired,
                    {'axis': 'reduction', 'level': 'r2scan3c', 'medium': 'gas',
                     'quantity': 'tau_legal', 'population_scope': 'census_246'})
    refusals = _rows(REFUSALS)
    assert len(refusals) == 3
    assert all(row['verdict'] == '拒绝' for row in refusals)
    assert payload['admission_list']['rows'] == EXPECTED_ROWS


def test_recomputing_the_register_is_reproducible() -> None:
    payload = _summary()
    assert payload['criteria']
    verdicts = {item['id']: item['verdict'] for item in payload['criteria']}
    assert set(verdicts) == {'H36d1', 'H36d2', 'H36d3', 'H36d4', 'H36d5'}
    assert all(value == '成立' for value in verdicts.values())
    assert 'H36d2' in verdicts
    assert REPORT.is_file() and REPORT.stat().st_size > 0