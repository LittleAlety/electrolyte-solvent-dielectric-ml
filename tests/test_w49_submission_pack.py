# Guards for Week 49: the submission-package landing.  The venue memo, the re-rendered journal
# docx, the cover letter, the reproducibility statement and the manifest must all exist; every
# figure must keep its original aspect ratio and stay inside the page box; the round-2 registration
# must be in README section 11; and no main-scoreboard shot may be taken.
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w49_submission_pack_summary.json'
CRITERIA_CSV = ART / 'w49_submission_pack_criteria.csv'
REPORT = ROOT / 'reports' / 'w49_submission_pack.md'
PREREG = ROOT / 'probes' / 'w49_submission_pack_prereg.json'
PROBE = ROOT / 'probes' / 'w49_submission_pack.py'
FORMAT_MAPPING = ROOT / 'reports' / 'w49_format_mapping.md'
COVER_LETTER = ROOT / 'reports' / 'w49_cover_letter.md'
REPRO = ROOT / 'reports' / 'w49_reproducibility_statement.md'
MANIFEST = ROOT / 'reports' / 'w49_submission_manifest.md'
README = ROOT / 'README.md'

CRITERIA_IDS = ['H49a1', 'H49a2', 'H49a3', 'H49b1', 'H49b2', 'H49b3', 'H49b4',
                'H49d1', 'H49d2', 'H49d3']
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_submission_package_four_pieces() -> None:
    payload = _summary()
    assert payload['default_venue'] == 'PCCP'
    assert payload['venue_overridable'] is True
    assert payload['docx']['exists'] is True
    for path in (FORMAT_MAPPING, COVER_LETTER, REPRO, MANIFEST, PROBE):
        assert path.is_file() and path.stat().st_size > 0


def test_docx_structure_and_figure_integrity() -> None:
    payload = _summary()
    docx = payload['docx']
    assert docx['paragraphs'] == 412 and docx['tables'] == 9 and docx['figures'] == 25
    assert docx['n_measured'] == 25
    assert docx['max_aspect_deviation'] < 1e-3
    assert docx['overflows'] == []


def test_reproducibility_statement_points_at_exports() -> None:
    text = REPRO.read_text(encoding='utf-8')
    for marker in ('成果输出/week47', 'SHA256SUMS', '92d47b8'):
        assert marker in text
    payload = _summary()
    assert all(payload['repro_markers'].values())


def test_round2_registered_and_invariants() -> None:
    readme = README.read_text(encoding='utf-8')
    assert '54. **新登记（W49）' in readme
    assert 'round-2' in readme
    payload = _summary()
    assert payload['invariants'] == {'registered_negatives': 9, 'cumulative_shots_max': 19,
                                     'frozen_outside_canon': 0}
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS
    assert payload['registered_negatives'] == []


def test_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 10
    assert payload['consistency_returncode'] == 0


def test_artifacts_and_prereg_exist() -> None:
    for path in (CRITERIA_CSV, REPORT, FORMAT_MAPPING):
        assert path.is_file() and path.stat().st_size > 0
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    assert prereg['status'] == 'locked_before_run'
    assert prereg['criteria'] == CRITERIA_IDS
    assert prereg['default_venue'] == 'PCCP'
    assert prereg['expected_docx'] == {'paragraphs': 412, 'tables': 9, 'figures': 25}
