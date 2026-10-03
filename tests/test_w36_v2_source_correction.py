# Guards for the Week 36-E lane: the v1 / English line calibration sync.
#
# Week 35-B corrected "the oxidation axis is insensitive to the level" in the shipped v2
# draft, but not in the assembly sources under paper/_v2_*.md.  A rebuild would therefore
# resurrect the stale wording -- the same defect family as AF-12 (delivered bytes that the
# declared sources cannot reproduce).  Week 36-E answers README section 11 item 15 and lands
# the same four corrections on the sources.
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w36_v2_source_correction as probe

PREREG = ROOT / 'probes' / 'w36_v2_source_correction_prereg.json'
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w36_v2_source_correction_summary.json'
DRIFT = ROOT / 'probes' / 'artifacts' / 'w36_v2_drift_inventory.csv'
REPORT = ROOT / 'reports' / 'w36_v2_source_correction.md'

SHIPPED = ROOT / 'paper' / 'paper_zh_draft_v2.md'
SHIPPED_SHA = 'dfb3b282f8ccf76653d244a6a2c618d92a6e12003d012b81cca9f08dc9c6e78e'
V1_LINE = ROOT / 'paper' / 'paper_zh_draft.md'
ENGLISH_LINE = ROOT / 'paper' / 'full_draft.md'


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _prereg() -> dict:
    return json.loads(PREREG.read_text(encoding='utf-8'))


def _rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_lane_is_pre_registered_and_takes_no_shot() -> None:
    payload = _summary()
    assert payload['task'] == 'week36_v2_source_correction'
    assert int(payload['ledger']['main_scoreboard_shots_this_week']) == 0
    assert int(payload['ledger']['cumulative_main_scoreboard_attempts_after']) == 19
    prereg = _prereg()
    assert prereg['status'] == 'locked_before_run'
    assert prereg['locked_before_run'] is True
    assert payload['prereg']['sha256'] == probe.sha256_file(PREREG)


def test_item_15_answer_is_recorded() -> None:
    payload = _summary()
    audited = {row['line']: row for row in payload['audit']}
    assert set(audited) == {'v1 线', '英文线'}
    assert all(row['hit_count'] == 0 for row in audited.values())
    for path in (V1_LINE, ENGLISH_LINE):
        assert '不敏感' not in path.read_text(encoding='utf-8')


def test_four_corrections_land_on_the_assembly_sources() -> None:
    prereg = _prereg()
    payload = _summary()
    assert len(payload['corrections']) == 4
    assert all(row['state'] in ('已施加', '幂等（已施加）') for row in payload['corrections'])
    targets = {row['id']: row['path'] for row in payload['corrections']}
    assert targets['C1'] == 'paper/_v2_body_b.md'
    assert targets['C2'] == 'paper/_v2_body_b.md'
    assert targets['C3'] == 'paper/_v2_appendix.md'
    assert targets['C4'] == 'paper/_v2_concl.md'
    for item in prereg['corrections']:
        text = (ROOT / item['path']).read_text(encoding='utf-8')
        if item['id'] == 'C2':
            assert item['after_suffix'].strip() in text
        elif item['id'] == 'C4':
            for step in item['steps']:
                assert step['replace'] in text
        else:
            assert item['after_text'] in text
            assert item['before_text'] not in text


def test_shipped_draft_is_untouched() -> None:
    payload = _summary()
    assert probe.sha256_file(SHIPPED) == SHIPPED_SHA
    assert payload['shipped_draft']['sha256'] == SHIPPED_SHA
    assert payload['shipped_draft']['unchanged'] is True
    assert _prereg()['shipped_draft']['sha256_before'] == SHIPPED_SHA


def test_drift_is_registered_and_five_criteria_hold() -> None:
    payload = _summary()
    drift = _rows(DRIFT)
    assert len(drift) == payload['rebuild']['drift_blocks']
    assert len(drift) > 0
    assert {row['kind'] for row in drift} <= {'只有已发布稿有', '只有重建产物有', '两侧都改写'}
    verdicts = {item['id']: item['verdict'] for item in payload['criteria']}
    assert set(verdicts) == {'H36e1', 'H36e2', 'H36e3', 'H36e4', 'H36e5'}
    assert all(value == '成立' for value in verdicts.values())
    assert REPORT.is_file() and REPORT.stat().st_size > 0