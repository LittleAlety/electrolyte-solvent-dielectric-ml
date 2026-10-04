# Guards for the Week 46 lane W46-D: the paper backfill + governance sync.
# The paper must carry the 7 new citations, the T1/T2 positioning paragraph, the three Gate-1
# wording revisions, and the new §3.31; the frozen readings must be byte-intact.
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w46_paper_governance_summary.json'
LEDGER_CSV = ART / 'w46_paper_governance_ledger.csv'
REPORT = ROOT / 'reports' / 'w46_paper_governance.md'
PREREG = ROOT / 'probes' / 'w46_paper_governance_prereg.json'
PROBE = ROOT / 'probes' / 'w46_paper_governance.py'
PAPER = ROOT / 'paper' / 'paper_zh_draft_v3.md'
DECISIONS = ROOT / 'reports' / 'decisions_log.md'
README = ROOT / 'README.md'

CRITERIA_IDS = ['H46d' + str(index) for index in range(1, 9)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w46_paper_governance/summary@1'
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


def test_citations_and_positioning() -> None:
    payload = _summary()
    assert all(payload['citations'].values())
    assert payload['positioning']['t1t2_paragraph'] is True
    assert payload['positioning']['first_rank_claim_unnegated'] is False


def test_gate1_wording_and_section() -> None:
    payload = _summary()
    assert all(payload['wording'].values())
    assert payload['section_3_31'] is True
    assert payload['decisions_log'] is True
    assert payload['readme_items'] is True


def test_frozen_readings_byte_intact() -> None:
    payload = _summary()
    paper = PAPER.read_text(encoding='utf-8')
    for reading in FROZEN_READINGS:
        assert str(reading) in paper
    for reading, variants in payload['frozen_variants'].items():
        assert variants == [reading]
    assert payload['paper_sha256']
    assert '28.101' in DECISIONS.read_text(encoding='utf-8')
    assert '45. **新登记（W46）' in README.read_text(encoding='utf-8')


def test_guard_snapshot_green() -> None:
    payload = _summary()
    snapshot = payload['guard_snapshot']
    assert snapshot['gate']['refused_controls'] == 3
    assert snapshot['static']['metric_name_mutations'] == 0
    assert snapshot['static']['frozen_reading_writes'] == 0
    assert snapshot['ledger']['frozen_outside_canon'] == 0
    assert snapshot['ledger']['cumulative_shots_max'] == 19
    assert snapshot['ledger']['registered_negatives'] == 9


def test_artifacts_and_prereg_exist() -> None:
    for path in (LEDGER_CSV, REPORT, PROBE, PAPER):
        assert path.is_file() and path.stat().st_size > 0
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    assert prereg['status'] == 'locked_before_run'
    assert len(prereg['required_citations']) == 7
