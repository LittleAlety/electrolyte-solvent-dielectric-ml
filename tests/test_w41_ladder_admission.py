# Guards for the Week 41 lane W41-A: the mechanical "clean ladder" admission gate.
#
# W41-A turns the W40-A caveat into a pre-registered rule: a ladder is only the set of
# arms on one config grid, and placebo / representation-swap / non-grid arms are excluded
# by name pattern (R1-R4).  On the admitted pools the ratio criterion reproduces the
# W40-A anchors bit-for-bit; on the polluted W28 pool (13 arms) the ratio collapses to
# 1.293416 and would read as a false negative.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w41_ladder_admission_summary.json'
ARMS = ART / 'w41_ladder_admission.csv'
LADDERS = ART / 'w41_ladder_admission_summary.csv'
FIGURE = ART / 'w41_ladder_admission.png'
REPORT = ROOT / 'reports' / 'w41_ladder_admission.md'
PROBE = ROOT / 'probes' / 'w41_ladder_admission.py'
PREREG = ROOT / 'probes' / 'w41_governance_prereg.json'

CRITERIA_IDS = ['H41a' + str(index) for index in range(1, 10)]
REGISTERED_NEGATIVES = []
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
LADDER_RATIOS = [21.044061513567584, 13.712270713223267, 8.092207259070127,
                 4.178785477997323, 7.272893976113999]
ADMITTED = [6, 6, 6, 6, 9]


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w41_ladder_admission/summary@1'
    assert payload['task'] == 'week41_ladder_admission'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_nine_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert all(item['verdict'] == '成立' for item in criteria)
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_admission_rule_excludes_placebo_and_representation_arms() -> None:
    payload = _summary()
    ladders = payload['ladders']
    assert [int(item['n_admitted']) for item in ladders] == ADMITTED
    assert int(ladders[0]['n_arms_total']) == 13
    assert int(ladders[0]['n_excluded']) == 7
    rows = _rows(ARMS)
    excluded = [row for row in rows if row['admitted'] == 'False']
    assert all(row['reason'].strip() for row in excluded)
    assert not [row for row in rows if row['admitted'] == 'True'
                and ('morgan' in row['arm'] or 'shuffled' in row['arm']
                     or 'placebo' in row['arm'])]


def test_clean_ladder_ratios_reproduce_w40a_anchors() -> None:
    payload = _summary()
    ratios = [float(item['ratio_admitted']) for item in payload['ladders']]
    assert ratios == LADDER_RATIOS
    assert max(float(item['auc30_spread_admitted']) for item in payload['ladders']) < 0.02


def test_polluted_w28_pool_would_read_as_false_negative() -> None:
    payload = _summary()
    polluted = float(payload['ladders'][0]['ratio_all'])
    assert abs(polluted - 1.293416) < 1e-5
    assert polluted < 4.0


def test_artifacts_and_report_exist_and_are_lf_only() -> None:
    for path in (SUMMARY, ARMS, LADDERS, FIGURE, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (SUMMARY, ARMS, LADDERS, REPORT, PROBE, PREREG):
        assert b'\r\n' not in path.read_bytes(), path
    assert FIGURE.stat().st_size > 5000


def test_prereg_is_locked_before_run() -> None:
    payload = json.loads(PREREG.read_text(encoding='utf-8'))
    assert payload['status'] == 'locked_before_run'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0