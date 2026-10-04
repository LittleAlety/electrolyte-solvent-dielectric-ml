# Guards for Week 48 lane W48-D: the section 4.6 debt closure.  Every registered README section 11
# debt (33/36/40/42/45/46/49-52 plus D2/D3 and dipole_transfer_v1) must have a corresponding
# sentence in section 4.6; the edit must land on the v3 line only (v2 bytes frozen) and the paper
# artifact consistency checker must still pass.
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w48_debt_closure_summary.json'
CRITERIA_CSV = ART / 'w48_debt_closure_criteria.csv'
REPORT = ROOT / 'reports' / 'w48_debt_closure.md'
PREREG = ROOT / 'probes' / 'w48_debt_closure_prereg.json'
PROBE = ROOT / 'probes' / 'w48_debt_closure.py'
PAPER = ROOT / 'paper' / 'paper_zh_draft_v3.md'
PAPER_V2 = ROOT / 'paper' / 'paper_zh_draft_v2.md'
README = ROOT / 'README.md'

CRITERIA_IDS = ['H48d1', 'H48d2', 'H48d3']
PAPER_V2_SHA256 = 'c7bc66296e18cd6384760a3b49014800662800f5141124365fccf31fdaf1b50f'
DEBT_MARKERS = ['strict same-level 独立源仍为 0', '§11-42', '§11-45', '§11-46',
                '§11-49', '§11-50', '§11-51', '§11-52 与 Ue 1997 还原侧',
                'D2 的 r2SCAN-3c 版本', 'D3（ddCOSMO 垂直 EA）',
                'dipole_transfer_v1']


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_section_46_covers_every_registered_debt() -> None:
    paper = PAPER.read_text(encoding='utf-8')
    sec46 = paper.split('### 4.6', 1)[1].split('### 4.7', 1)[0]
    for marker in DEBT_MARKERS:
        assert marker in sec46, marker
    payload = _summary()
    assert payload['missing'] == []
    assert payload['readme_boundary_missing'] == []
    assert len(payload['items']) == 11


def test_v3_only_and_consistency_pass() -> None:
    assert hashlib.sha256(PAPER_V2.read_bytes()).hexdigest() == PAPER_V2_SHA256
    payload = _summary()
    assert payload['paper_v2_unchanged'] is True
    assert payload['consistency_returncode'] == 0
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['registered_negatives'] == []


def test_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 3


def test_artifacts_and_prereg_exist() -> None:
    for path in (CRITERIA_CSV, REPORT, PROBE):
        assert path.is_file() and path.stat().st_size > 0
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    assert prereg['status'] == 'locked_before_run'
    assert prereg['criteria'] == CRITERIA_IDS
    assert prereg['frozen']['paper_v2_sha256'] == PAPER_V2_SHA256
