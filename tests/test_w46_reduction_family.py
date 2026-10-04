# Guards for the Week 46 lane W46-A: the reduction-axis descriptor family under the refusal branch.
# With zero same-rig anchors the main judgement is not executed; the output must register
# "不可判定" together with the Lane-C power floor, and the layer-discipline grid must be explicit.
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w46_reduction_family_summary.json'
CANDIDATES_CSV = ART / 'w46_reduction_family_candidates.csv'
TAU_CSV = ART / 'w46_reduction_family_tau.csv'
FIGURE = ART / 'w46_reduction_family.png'
REPORT = ROOT / 'reports' / 'w46_reduction_family.md'
PREREG = ROOT / 'probes' / 'w46_reduction_family_prereg.json'
PROBE = ROOT / 'probes' / 'w46_reduction_family.py'

CRITERIA_IDS = ['H46a' + str(index) for index in range(1, 9)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w46_reduction_family/summary@1'
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


def test_refusal_branch_and_undecidable() -> None:
    payload = _summary()
    assert payload['refusal_branch'] is True
    assert payload['main_judgment'] == '不可判定'
    assert payload['n_anchors'] == 0
    report = REPORT.read_text(encoding='utf-8')
    assert '不可判定' in report
    assert '功效下限' in report


def test_coverage_grid_marks_illegal_cells() -> None:
    payload = _summary()
    grid = {(row['candidate'], row['layer']): row for row in payload['coverage_grid']}
    assert grid[('D1', 'r2SCAN-3c')]['n_legal'] == 0
    assert grid[('D1', 'r2SCAN-3c')]['status'] == '不可判定'
    assert grid[('D3', 'r2SCAN-3c')]['n_legal'] < 5
    assert grid[('D3', 'GFN2')]['status'] == '不可判定'
    assert grid[('D2', 'GFN2')]['status'] == 'computable'


def test_directional_tau_with_unresolved_share() -> None:
    payload = _summary()
    rows = payload['tau_rows']
    assert len(rows) == 3
    assert all(row['n'] >= 5 for row in rows)
    assert all(0.0 <= row['unresolved'] <= 1.0 for row in rows)
    lookup = {(row['descriptor_a'], row['descriptor_b']): row for row in rows}
    assert abs(lookup[('D0', 'D1')]['tau_b'] - 0.7393617021276596) <= 1e-12
    assert abs(lookup[('D0', 'D1')]['unresolved'] - 0.3980496453900709) <= 1e-12


def test_power_floor_matches_lane_c() -> None:
    payload = _summary()
    floor = payload['power_floor']
    assert abs(floor['mde_at_n7'] - 0.6540558963871848) <= 1e-12
    assert floor['n_min_tau06'] == 8
    assert floor['n_min_tau04'] == 17


def test_artifacts_and_prereg_exist() -> None:
    for path in (CANDIDATES_CSV, TAU_CSV, REPORT, PROBE):
        assert path.is_file() and path.stat().st_size > 0
    raw = FIGURE.read_bytes()
    assert raw[:8] == PNG_MAGIC and len(raw) > 5000
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    assert prereg['status'] == 'locked_before_run'
    assert prereg['declared_layer'] == 'r2SCAN-3c'
