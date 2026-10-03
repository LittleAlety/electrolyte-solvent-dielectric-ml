# Guards for the Week 39 lane: QM9 as the third orbital / dipole external layer.
#
# W39 is a post hoc audit lane.  It fits nothing and takes no main-scoreboard shot
# (the cumulative ledger stays at 19).  Its job is to make three claims re-runnable:
#   1. the roster hit count against QM9 is measured (103 / 241),
#   2. the xTB-vs-B3LYP gap relation is pinned (ordering aligns, the scale is
#      systematically compressed to ~0.706x),
#   3. the W38-C dipole quality doubt is confirmed independently and split into a
#      ~0.4 D systematic offset plus a few extreme samples -- which is exactly why
#      H39a7 ("conformer freedom is the main driver") is a registered negative.
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w39_qm9_crosscheck_summary.json'
OVERLAP = ROOT / 'probes' / 'artifacts' / 'w39_qm9_overlap.csv'
FIGURE = ROOT / 'probes' / 'artifacts' / 'w39_qm9_alignment.png'
REPORT = ROOT / 'reports' / 'w39_qm9_crosscheck.md'
ROSTER = ROOT / 'data' / 'processed' / 'dielectric_physical_features_v03.csv'
QM9 = ROOT / 'data' / 'external' / 'qm9_dataset.csv'

ROSTER_SHA256 = 'b36d3439560e4381b7779565b9950eed379832e832b72ea6a3a010662ed24fa3'
QM9_SHA256 = '01d196218c78a0e29575ef8cf9ceb6d2f33fda9cddc3e4b5bd133e191fa2e053'

CRITERIA_IDS = ['H39a1', 'H39a2', 'H39a3', 'H39a4', 'H39a5', 'H39a6', 'H39a7',
                'H39a8', 'H39a9', 'H39a10']
REGISTERED_NEGATIVES = ['H39a7']
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows() -> list:
    with OVERLAP.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['task'] == 'week39_qm9_crosscheck'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_ten_criteria_with_the_conformer_hypothesis_registered_as_negative() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    verdicts = {item['id']: item['verdict'] for item in criteria}
    assert [key for key, value in verdicts.items() if value != '成立'] == REGISTERED_NEGATIVES
    assert verdicts['H39a7'] == '判否'


def test_roster_denominator_and_hit_width() -> None:
    payload = _summary()
    assert payload['roster_total'] == 241
    assert payload['n_hits'] == 103


def test_qm9_layer_is_pinned_and_licensed_for_reuse() -> None:
    layer = _summary()['external_layer']
    assert layer['name'] == 'QM9'
    assert layer['file'] == 'data/external/qm9_dataset.csv'
    assert layer['sha256'] == QM9_SHA256
    assert layer['rows'] == 133885
    assert layer['level_of_theory'] == 'B3LYP/6-31G(2df,p)'
    assert 'CC BY 4.0' in layer['license']
    assert layer['not_used_as'].startswith('不作为标签或特征')
    assert sha256_file(QM9) == QM9_SHA256
    assert sha256_file(ROSTER) == ROSTER_SHA256


def test_gap_alignment_readings_are_frozen() -> None:
    alignment = _summary()['alignment']
    assert alignment['pearson'] == 0.8409443563052813
    assert alignment['spearman'] == 0.8856281475401158
    assert alignment['median_ratio_xtb_over_qm9'] == 0.7057566422677529
    assert alignment['mae_ev'] == 2.5329444893682322
    assert alignment['r2'] == 0.7071874104017035
    assert 0.50 <= alignment['median_ratio_xtb_over_qm9'] <= 1.00
    assert alignment['median_qm9_ev'] > alignment['median_xtb_ev']


def test_dipole_audit_readings_are_frozen() -> None:
    audit = _summary()['dipole_audit']
    assert audit['pearson'] == 0.7836969456079745
    assert audit['spearman'] == 0.8022056197352332
    assert audit['mae_D'] == 0.6103097087378639
    assert audit['n'] == 103
    assert audit['n_abs_delta_ge_1D'] == 13
    assert audit['n_agreeing'] == 90
    assert audit['median_signed_delta_D'] < 0
    assert audit['median_signed_delta_agreeing_D'] == -0.3914000000000001


def test_rigidity_split_does_not_support_the_conformer_hypothesis() -> None:
    rigidity = _summary()['rigidity_split']
    assert rigidity['n_rigid'] == 48
    assert rigidity['n_flexible'] == 55
    assert rigidity['median_abs_delta_rigid_D'] == 0.44415000000000004
    assert rigidity['median_abs_delta_flexible_D'] == 0.4205000000000001
    assert rigidity['median_abs_delta_rigid_D'] >= rigidity['median_abs_delta_flexible_D']
    assert rigidity['n_rigid_flagged'] == 5
    names = {item['name'] for item in rigidity['rigid_flagged']}
    assert 'formamide' in names
    assert 'N-methylacetamide' in names


def test_domain_ratio_is_robust_to_the_mu_source() -> None:
    ratio = _summary()['domain_ratio']
    assert ratio['our_mu']['ratio'] == 2.980102137419939
    assert ratio['qm9_mu']['ratio'] == 3.04586016142653
    assert ratio['our_mu']['ratio'] >= 1.5
    assert ratio['qm9_mu']['ratio'] >= 1.5
    assert ratio['our_mu']['n_donor'] == 29
    assert ratio['qm9_mu']['n_donor'] == 29


def test_overlap_rows_cover_every_hit() -> None:
    rows = _rows()
    assert len(rows) == 103
    assert all(len(row['inchikey']) == 27 for row in rows)
    assert sum(1 for row in rows if row['rigid'] == 'True') == 48
    assert all(float(row['xtb_gap_ev']) > 0.0 for row in rows)
    assert all(float(row['qm9_gap_ev']) > 0.0 for row in rows)


def test_figure_and_report_exist() -> None:
    assert FIGURE.is_file() and FIGURE.stat().st_size > 0
    assert REPORT.is_file()
    text = REPORT.read_text(encoding='utf-8')
    assert 'W39-A' in text and 'W39-B' in text and 'W39-C' in text
    assert 'H39a7' in text and '判否' in text
    assert '103 / 241' in text
