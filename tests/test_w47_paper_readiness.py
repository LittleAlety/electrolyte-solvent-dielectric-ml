# Guards for Week 47 lane W47-D: the paper backfill + submission-readiness assessment.  The paper
# must carry the 13 new citations, the §3.32 section, the Abaei/Deng positioning update and the §4.6
# limitation update; it must have no appendix heading and every referenced figure must exist on disk.
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w47_paper_readiness_summary.json'
LEDGER_CSV = ART / 'w47_paper_readiness_ledger.csv'
REPORT = ROOT / 'reports' / 'w47_paper_readiness.md'
PREREG = ROOT / 'probes' / 'w47_paper_readiness_prereg.json'
PROBE = ROOT / 'probes' / 'w47_paper_readiness.py'
PAPER = ROOT / 'paper' / 'paper_zh_draft_v3.md'
DECISIONS = ROOT / 'reports' / 'decisions_log.md'
README = ROOT / 'README.md'

CRITERIA_IDS = ['H47d' + str(index) for index in range(1, 13)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
APPENDIX_HEADING = re.compile(r'^#{1,6}\s*附录', re.MULTILINE)


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w47_paper_readiness/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS
    assert payload['registered_negatives'] == []


def test_twelve_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 12


def test_thirteen_citations_present() -> None:
    payload = _summary()
    assert payload['n_citations_required'] == 13
    assert payload['n_citations_present'] == 13
    assert all(payload['citations'].values())
    paper = PAPER.read_text(encoding='utf-8')
    references = paper.split('## 参考文献', 1)[1]
    for label in ('Moshkovich', 'Borodin', 'Mozhzhukhina', 'Murdock', 'Timerghazin',
                  'Gunasekaran', 'Liu', 'Chen', 'Vydrov', 'Deng', 'Abaei'):
        assert label in references


def test_section_positioning_and_limitations() -> None:
    payload = _summary()
    assert payload['section_ok'] is True
    assert payload['positioning_ok'] is True
    assert payload['limitations_ok'] is True
    paper = PAPER.read_text(encoding='utf-8')
    assert '### 3.32' in paper
    sec12 = paper.split('### 1.2', 1)[1].split('### 1.3', 1)[0]
    assert 'Abaei' in sec12 and 'Deng' in sec12
    sec46 = paper.split('### 4.6', 1)[1].split('### 4.7', 1)[0]
    assert '还原锚点' in sec46 and 'round-2' in sec46


def test_no_appendix_and_figures_on_disk() -> None:
    payload = _summary()
    paper = PAPER.read_text(encoding='utf-8')
    assert APPENDIX_HEADING.findall(paper) == []
    assert payload['appendix_headings'] == []
    assert payload['missing_figures'] == []
    assert len(payload['figure_links']) >= 20
    for link in payload['figure_links']:
        assert (PAPER.parent / link).resolve().is_file()


def test_frozen_readings_and_governance_registered() -> None:
    payload = _summary()
    for reading in FROZEN_READINGS:
        assert str(reading) in PAPER.read_text(encoding='utf-8')
    for reading, variants in payload['frozen_variants'].items():
        assert variants == [reading]
    assert payload['decisions_log'] is True
    assert payload['readme_items'] is True
    assert payload['boundaries_declared'] is True
    assert '28.102' in DECISIONS.read_text(encoding='utf-8')
    readme = README.read_text(encoding='utf-8')
    for item in ('49. **新登记（W47）', '50. **新登记（W47）', '51. **新登记（W47）',
                 '52. **新登记（W47）'):
        assert item in readme


def test_submission_readiness_and_guards() -> None:
    payload = _summary()
    readiness = payload['readiness']
    assert readiness['gates_total'] == 10
    assert readiness['gates_passed'] == 10
    assert readiness['all_gates_passed'] is True
    assert readiness['verdict'] == 'conditional_go'
    assert len(readiness['blocking_items']) >= 4
    guard = payload['guard_snapshot']
    assert guard['refused_controls'] == 3
    assert guard['operational_all_admitted'] is True
    assert guard['metric_name_mutations'] == 0
    assert guard['frozen_reading_writes'] == 0
    assert guard['unregistered_promotions'] == 0
    assert guard['frozen_outside_canon'] == 0
    assert guard['registered_negatives'] == 9
    assert guard['cumulative_shots_max'] == 19
    assert payload['paper_sha256']


def test_artifacts_and_prereg_exist() -> None:
    for path in (LEDGER_CSV, REPORT, PROBE):
        assert path.is_file() and path.stat().st_size > 0
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    assert prereg['status'] == 'locked_before_run'
    assert len(prereg['required_citations']) == 13
    assert len(prereg['readiness_gates']) == 10
