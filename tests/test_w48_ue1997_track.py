# Guards for Week 48 lane W48-B: the Ue 1997 source-retrieval adjudication and the
# explicit downgrade of the reduction-side debt.  The probe must land the disposition in
# the frozen tri-state, keep the W47 frozen preregs byte-identical, keep 0 shots, record
# the DOI correction (10.1149/1.1837585 -> 10.1149/1.1837882) and write the downgrade
# wording into README section 11.
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w48_ue1997_summary.json'
LEDGER_CSV = ART / 'w48_ue1997_ledger.csv'
CRITERIA_CSV = ART / 'w48_ue1997_criteria.csv'
REPORT = ROOT / 'reports' / 'w48_ue1997.md'
PREREG = ROOT / 'probes' / 'w48_ue1997_prereg.json'
PROBE = ROOT / 'probes' / 'w48_ue1997_track.py'
README = ROOT / 'README.md'

CRITERIA_IDS = ['H48b1', 'H48b2', 'H48b3', 'H48b4']
VOCABULARY = ('transcribed_and_adjudicated', 'no_reduction_side', 'not_available')
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
FROZEN_PREREGS = {
    'probes/w47_anchor_prereg.json':
        'd06537f3153a507d6ed3501fc023350a8ed43c51f01ec5698622edcb0dad2e95',
    'probes/w47_experimental_track_prereg.json':
        '55b1c1e4cef7471639a99b60c7dbfd7e7a0ef14db351f9c9f08fe45658472673',
}


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_disposition_landed_in_tristate() -> None:
    payload = _summary()
    assert payload['schema'] == 'w48_ue1997/summary@1'
    assert payload['disposition'] in VOCABULARY
    assert payload['disposition'] != 'pending_source_retrieval'
    assert payload['still_pending'] is False
    assert payload['main_criterion_executed'] is False
    assert payload['disposition_in_vocabulary'] is True


def test_zero_shot_and_frozen_preregs_untouched() -> None:
    payload = _summary()
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS
    assert payload['registered_negatives'] == []
    for rel, digest in FROZEN_PREREGS.items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == digest
    assert payload['frozen_prereg_unchanged'] is True


def test_doi_correction_recorded() -> None:
    payload = _summary()
    doi = payload['doi_correction']
    assert doi['planned_doi'] == '10.1149/1.1837585'
    assert doi['correct_doi'] == '10.1149/1.1837882'
    ledger = LEDGER_CSV.read_text(encoding='utf-8')
    assert '10.1149/1.1837585' in ledger and '10.1149/1.1837882' in ledger
    assert 'ue1997_doi' in ledger and 'ue1997_reduction_side' in ledger


def test_readme_downgrade_wording() -> None:
    readme = README.read_text(encoding='utf-8')
    for marker in ('Ue 1997', 'not_available', '10.1149/1.1837882', 'round-2'):
        assert marker in readme
    payload = _summary()
    assert payload['readme_markers_ok'] is True
    assert payload['readme_markers'] == {'Ue 1997': True, 'not_available': True,
                                         '10.1149/1.1837882': True, 'round-2': True}


def test_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 4


def test_artifacts_and_prereg_exist() -> None:
    for path in (LEDGER_CSV, CRITERIA_CSV, REPORT, PROBE):
        assert path.is_file() and path.stat().st_size > 0
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    assert prereg['status'] == 'locked_before_run'
    assert prereg['criteria'] == CRITERIA_IDS
    assert set(prereg['branches']) == {'B1_has_reduction_side', 'B2_no_reduction_side',
                                       'B3_not_available'}
    assert prereg['honesty_clause']['mde_n4'] == 0.982638888888889
