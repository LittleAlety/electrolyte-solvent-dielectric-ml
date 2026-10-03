# Guards for the Week 35-B lane: the pre-registration driven R6 wording correction.
#
# Week 34-B gave the cross-level contrast a resolution reading: the oxidation-axis
# Delta tau interval crosses zero, so "the oxidation axis is insensitive to the level"
# has to become "no difference detected at n = 22".  Week 35-B writes that correction
# down as a locked pre-registration and applies it to the paper through a probe, so the
# change is reproducible rather than hand-typed.
#
# The guards pin:
#
#   * the pre-registration is locked and its evidence matches the frozen Week 34-B
#     artifact digit for digit (the probe may not soften the intervals);
#   * the four corrections are present in the shipped paper;
#   * the original numbers survive in place -- the correction adds notes, it does not
#     rewrite the readings;
#   * applying the corrections to the shipped paper is a no-op (idempotent);
#   * the lane is post hoc, takes no shot, and the paper is LF.
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w35_paper_r6_correction as probe

PREREG = ROOT / 'probes' / 'w35_paper_r6_correction_prereg.json'
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w35_paper_r6_correction_summary.json'
REPORT = ROOT / 'reports' / 'w35_paper_r6_correction.md'
PAPER = ROOT / 'paper' / 'paper_zh_draft_v2.md'
POWER = ROOT / 'probes' / 'artifacts' / 'w34_paired_power_summary.json'

PRE_CORRECTION_SHA256 = '8984fb6b6523fd6a372b20396dff301366922646d79ad6cda2ecde93e1f70a28'
POST_CORRECTION_SHA256 = 'dfb3b282f8ccf76653d244a6a2c618d92a6e12003d012b81cca9f08dc9c6e78e'

#: W40 的 v1.4 改稿（新增 §3.22–§3.28、摘要与附录）让论文的**交付字节合法移动了一次**。
#: `POST_CORRECTION_SHA256` 是 W35 当时那一版的历史记录，**不得回改**；当前字节改钉到 v1.4,
#: 并要求两者不同（哪天又相等，说明有人把 v1.4 回滚了，守卫会红）。
V1_4_SHA256 = '778d1e08a727220bb16ca064586953224a8602a1b73c78ea1e54687619e66c55'
OX_CI_LOW = -0.19819819819819823
OX_CI_HIGH = 0.09090909090909094
RED_CI_LOW = -1.7037037037037035
RED_CI_HIGH = -1.0818181818181818


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _prereg() -> dict:
    return json.loads(PREREG.read_text(encoding='utf-8'))


def _paper() -> str:
    return PAPER.read_text(encoding='utf-8')


def test_lane_is_post_hoc_and_takes_no_shot() -> None:
    payload = _summary()
    assert payload['task'] == 'week35_paper_r6_correction'
    assert int(payload['ledger']['main_scoreboard_shots_this_week']) == 0
    assert int(payload['ledger']['cumulative_main_scoreboard_attempts_after']) == 19


def test_prereg_is_locked_and_recorded() -> None:
    payload = _summary()
    prereg = _prereg()
    assert prereg['status'] == 'locked_before_run'
    assert prereg['locked_before_run'] is True
    assert len(prereg['corrections']) == 4
    assert payload['prereg']['status'] == 'locked_before_run'
    assert payload['prereg']['locked_before_run'] is True
    assert payload['prereg']['sha256'] == probe.sha256_bytes(PREREG.read_bytes())


def test_prereg_evidence_matches_the_frozen_paired_power_artifact() -> None:
    """The intervals in the correction must be the Week 34-B intervals."""
    prereg = _prereg()
    artifact = json.loads(POWER.read_text(encoding='utf-8'))
    table = artifact['table']
    assert prereg['evidence']['oxidation']['ci_low'] == table['ox']['ci_low']
    assert prereg['evidence']['oxidation']['ci_high'] == table['ox']['ci_high']
    assert prereg['evidence']['oxidation']['crosses_zero'] is True
    assert prereg['evidence']['reduction']['ci_low'] == table['red']['ci_low']
    assert prereg['evidence']['reduction']['ci_high'] == table['red']['ci_high']
    assert prereg['evidence']['reduction']['crosses_zero'] is False
    assert artifact['gate']['gfn2_gas_legal'] == 1
    assert artifact['gate']['orca_gas_legal'] == 0
    assert prereg['evidence']['oxidation']['ci_low'] == OX_CI_LOW
    assert prereg['evidence']['oxidation']['ci_high'] == OX_CI_HIGH
    assert prereg['evidence']['reduction']['ci_low'] == RED_CI_LOW
    assert prereg['evidence']['reduction']['ci_high'] == RED_CI_HIGH


def test_every_correction_is_present_in_the_shipped_paper() -> None:
    paper = _paper()
    prereg = _prereg()
    for item in prereg['corrections']:
        if item['id'] == 'C2':
            assert item['after_suffix'].strip() in paper
        elif item['id'] == 'C4':
            for step in item['steps']:
                assert step['replace'] in paper
        else:
            assert item['after_text'] in paper
            assert item['before_text'] not in paper


def test_original_numbers_survive_in_place() -> None:
    paper = _paper()
    prereg = _prereg()
    for token in prereg['invariants']['preserved_numbers']:
        assert token in paper, token
    assert '−0.467' in paper
    assert '0.6969696969696969' not in paper  # the table keeps its rounded 0.697
    assert '| **GFN2-xTB**（本仓普查层） | 0.697 | **+0.835** |' in paper


def test_applying_the_corrections_again_is_a_no_op() -> None:
    paper = _paper()
    prereg = _prereg()
    again, records = probe.apply_corrections(prereg, paper)
    assert again == paper
    assert len(records) == 4


def test_paper_is_lf_and_the_recorded_hashes_agree() -> None:
    payload = _summary()
    payload_bytes = PAPER.read_bytes()
    assert b'\r' not in payload_bytes
    assert probe.sha256_bytes(payload_bytes) == V1_4_SHA256
    assert V1_4_SHA256 != POST_CORRECTION_SHA256
    assert payload['paper']['sha256_before'] == PRE_CORRECTION_SHA256
    assert payload['paper']['sha256_after'] == POST_CORRECTION_SHA256
    assert int(payload['paper']['lines_after']) > int(payload['paper']['lines_before']) - 1


def test_five_criteria_hold_and_the_report_exists() -> None:
    payload = _summary()
    verdicts = {item['id']: item['verdict'] for item in payload['criteria']}
    assert set(verdicts) == {'H35f', 'H35g', 'H35h', 'H35i', 'H35j'}
    assert all(value == '成立' for value in verdicts.values())
    assert int(payload['invariants']['no_carriage_return']) == 1
    assert payload['invariants']['numbers_all_non_decreasing'] is True
    assert payload['invariants']['frozen_readings_unchanged'] is True
    assert REPORT.is_file() and REPORT.stat().st_size > 0