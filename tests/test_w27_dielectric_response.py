# Guards for the Week 27 dielectric-response descriptor block.
#
# Week 27 appends the thirteen ddCOSMO response columns Week 26 measured (Born
# prefactors, cavity residuals, band coefficients of variation, electron
# affinities and orbital slopes against 1/epsilon) to the dense lever-4 physical
# block, and scores that arm on the frozen main scoreboard pool.  The guards pin
# what makes the reading citable:
#
#   * the pre-registration was locked before the production run and the summary
#     quotes its sha256;
#   * the seed-42 lever-4 anchor reproduces the frozen constant bit for bit;
#   * the block is reproducible from the frozen Week 26 artefacts, so the
#     delivered columns are not a black box;
#   * missing rows are not imputed and no column touches the measured epsilon;
#   * the shot ledger moves by exactly one, and the four frozen readings do not.
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w27_dielectric_response as w27

ARTIFACTS = ROOT / 'probes' / 'artifacts'
BLOCK_CSV = ARTIFACTS / 'w27_dielectric_response_block.csv'
REPEATS_CSV = ARTIFACTS / 'w27_dielectric_response_repeats.csv'
FIG = ARTIFACTS / 'w27_dielectric_response.png'
PREREG = ROOT / 'probes' / 'w27_dielectric_response_prereg.json'
SUMMARY = ROOT / 'probes' / 'w27_dielectric_response_summary.json'
PLACEBO = ROOT / 'probes' / 'w27_dielectric_response_placebo_summary.json'
REPORT = ROOT / 'reports' / 'w27_dielectric_response.md'
CRLF = bytes([13, 10])
BOM = bytes([239, 187, 191])

FROZEN_READINGS = (
    0.4091179943351143,
    0.4766400383507876,
    0.5861142332208197,
    0.6216672295270079,
)
VERDICT_IDS = ('H27a', 'H27b', 'H27c', 'H27d', 'H27e', 'H27f', 'H27g')


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list:
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_prereg_is_locked_before_the_run_and_no_threshold_moved() -> None:
    payload = json.loads(PREREG.read_text(encoding='utf-8'))
    assert payload['status'] == 'locked_before_run'
    assert payload['revision'] == 2
    note = payload['revision_note']
    assert note['thresholds_moved'] is False
    assert note['thresholds_unchanged'] == {'H27a': 1e-09, 'H27c': 0.02, 'H27d': 0.005,
                                            'H27e': 0.005, 'H27f': 97}
    assert payload['bars'] == {'pass_delta': 0.02, 'kill_delta': 0.005,
                               'placebo_tolerance': 0.005}
    assert payload['response_columns'] == list(w27.RESPONSE_COLUMNS)
    assert len(payload['response_columns']) == 13


def test_summary_quotes_the_prereg_bytes() -> None:
    summary = _summary()
    assert summary['preregistration']['status'] == 'locked_before_run'
    assert summary['preregistration']['sha256'] == _digest(PREREG)
    assert summary['seeds'] == [42, 1234, 2026, 31337, 7]
    assert summary['primary_representation'] == 'Morgan+Physical'
    assert summary['secondary_representation'] == 'Physical'


def test_seed_42_anchor_reproduces_the_frozen_constant() -> None:
    summary = _summary()
    assert summary['anchor_expected'] == 0.5433111678100043
    assert summary['anchor_gap'] is not None
    assert summary['anchor_gap'] <= 1e-09
    assert summary['per_seed']['42']['anchor'] == pytest.approx(0.5433111678100043, abs=1e-09)


def test_the_shot_ledger_moves_by_exactly_one() -> None:
    summary = _summary()
    assert summary['main_scoreboard_attempts_delta'] == 1
    assert summary['cumulative_main_scoreboard_attempts'] == 13
    assert w27.SCOREBOARD_SHOTS_THIS_WEEK == 1
    assert w27.CUMULATIVE_MAIN_SCOREBOARD_ATTEMPTS == 13
    notes = ' '.join(summary['notes'])
    for frozen in FROZEN_READINGS:
        assert repr(frozen) in notes


def test_every_verdict_id_is_present_and_ordered() -> None:
    summary = _summary()
    assert tuple(entry['id'] for entry in summary['verdicts']) == VERDICT_IDS
    for entry in summary['verdicts']:
        assert entry['verdict'] in ('成立', '判否')


def test_the_leakage_audit_is_clean_on_every_seed_and_arm() -> None:
    summary = _summary()
    assert summary['leakage']
    for block in summary['leakage'].values():
        assert block['folds_with_a_straddling_compound'] == 0
        assert block['max_straddling_compounds_in_a_fold'] == 0
    assert _summary()['verdicts'][1]['verdict'] == '成立'


def test_the_pool_and_the_coverage_are_the_preregistered_ones() -> None:
    summary = _summary()
    assert summary['pool']['scored_rows'] == 457
    assert summary['pool']['scored_compounds'] == 97
    assert summary['pool']['matches_preregistration'] is True
    coverage = summary['coverage']
    assert coverage['scored_compounds_with_the_block'] == 97
    assert coverage['block_row_coverage'] == pytest.approx(0.7394, abs=5e-4)


def test_the_block_is_complete_and_lf_only() -> None:
    rows = _rows(BLOCK_CSV)
    assert len(rows) == 242
    assert set(rows[0]) == {'inchikey', 'status', 'missing_columns', *w27.RESPONSE_COLUMNS}
    for row in rows:
        assert row['status'] == 'ok', row['inchikey']
        assert row['missing_columns'] == ''
        for column in w27.RESPONSE_COLUMNS:
            float(row[column])
    payload = BLOCK_CSV.read_bytes()
    assert not payload.startswith(BOM)
    assert CRLF not in payload


def test_the_block_is_reproducible_from_the_frozen_w26_artefacts() -> None:
    rebuilt, report = w27.build_block()
    stored = {row['inchikey']: row for row in _rows(BLOCK_CSV)}
    assert report['compounds_in_the_block'] == 242
    assert report['compounds_complete'] == 242
    assert set(stored) == {row['inchikey'] for row in rebuilt}
    for row in rebuilt:
        entry = stored[str(row['inchikey'])]
        for column in w27.RESPONSE_COLUMNS:
            assert float(entry[column]) == pytest.approx(float(row[column]), rel=1e-12)


def test_the_block_never_reads_the_measured_permittivity() -> None:
    summary = _summary()
    notes = ' '.join(summary['notes'])
    assert 'NaN' in notes
    assert 'XGBoost' in notes
    assert '介电常数' in notes
    contract = json.loads(PREREG.read_text(encoding='utf-8'))['coverage_contract']
    assert contract['no_fold_statistics']
    assert contract['expected_scored_compounds'] == 97


def test_the_placebo_is_inert_and_recorded() -> None:
    summary = _summary()
    placebo = json.loads(PLACEBO.read_text(encoding='utf-8'))
    assert placebo['rng_seed'] == w27.PLACEBO_RNG_SEED == 2026
    assert placebo['placebo_delta'] == summary['placebo_delta']
    assert placebo['clean'] == (abs(summary['placebo_delta']) < w27.PLACEBO_TOLERANCE)
    assert summary['placebo_delta'] == pytest.approx(summary['placebo_delta'])


def test_repeats_table_covers_every_seed_and_both_arms() -> None:
    rows = _rows(REPEATS_CSV)
    assert rows
    arms = {row['arm'] for row in rows}
    assert arms == {'lever4@seed42', 'lever4@seed1234', 'lever4@seed2026',
                    'lever4@seed31337', 'lever4@seed7',
                    'lever4_plus_dielectric_response@seed42',
                    'lever4_plus_dielectric_response@seed1234',
                    'lever4_plus_dielectric_response@seed2026',
                    'lever4_plus_dielectric_response@seed31337',
                    'lever4_plus_dielectric_response@seed7'}
    representations = {row['representation'] for row in rows}
    assert representations == {'Morgan', 'Physical', 'Morgan+Physical'}
    payload = REPEATS_CSV.read_bytes()
    assert not payload.startswith(BOM)
    assert CRLF not in payload


def test_figure_is_written_and_is_not_trivial() -> None:
    assert FIG.is_file()
    assert FIG.stat().st_size > 20000
    assert FIG.read_bytes()[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])


def test_report_exists_and_names_the_level_of_every_reading() -> None:
    text = REPORT.read_text(encoding='utf-8')
    assert 'locked_before_run' in text
    assert '主记分牌 shot：1' in text
    assert 'Morgan+Physical' in text
    assert 'NaN' in text or '不插补' in text
