# Guards for Week 48 lane W48-C: the venue decision memo and the form-drift guard.  The memo must
# carry at least three candidates across the four comparison axes; the submission package itself
# (H48c2) is deferred until the venue is chosen, so it is recorded as deferred, not as a pass.
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w48_submission_pack_summary.json'
CRITERIA_CSV = ART / 'w48_submission_pack_criteria.csv'
REPORT = ROOT / 'reports' / 'w48_submission_pack.md'
MEMO = ROOT / 'reports' / 'w48_venue_memo.md'
PREREG = ROOT / 'probes' / 'w48_submission_pack_prereg.json'
PROBE = ROOT / 'probes' / 'w48_submission_pack.py'

CRITERIA_IDS = ['H48c1', 'H48c3', 'H48c4']
AXES = ['范围匹配', '审计叙事接受度', '周期', '版面／OA']


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_memo_has_candidates_and_axes() -> None:
    memo = MEMO.read_text(encoding='utf-8')
    for axis in AXES:
        assert axis in memo
    payload = _summary()
    assert payload['memo_exists'] is True
    assert len(payload['candidates_present']) >= 3
    assert payload['axes_present'] == AXES


def test_package_deferred_not_claimed_done() -> None:
    payload = _summary()
    assert 'H48c2' in payload['deferred_criteria']
    assert 'deferred' in payload['deferred_criteria']['H48c2']
    assert payload['pending_user_decisions']


def test_form_drift_guard_and_zero_shot() -> None:
    payload = _summary()
    assert payload['consistency_returncode'] == 0
    assert payload['readings_all_literal'] is True
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['registered_negatives'] == []


def test_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 3


def test_artifacts_and_prereg_exist() -> None:
    for path in (CRITERIA_CSV, REPORT, MEMO, PROBE):
        assert path.is_file() and path.stat().st_size > 0
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    assert prereg['status'] == 'locked_before_run'
    assert prereg['executable_criteria'] == CRITERIA_IDS
    assert 'H48c2' in prereg['deferred_criteria']
    assert prereg['frozen_readings'] == [0.4091179943351143, 0.4766400383507876,
                                         0.5861142332208197, 0.6216672295270079]
