# Guards for the Week 45 lane W45-B: the stratified residual audit of the 4668-row xTB-Batt pair.
# The overall rho reproduces the W43 anchor exactly; the rank agreement is homogeneous across the
# three tiers but degrades with heavy-atom count (0.811 -> 0.731 -> 0.481), and the ~6.99 eV level
# shift means outliers must be judged on the de-medianed robust scale, not an absolute threshold.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w45_stratified_residual_summary.json'
STRATA_CSV = ART / 'w45_stratified_residual.csv'
FIGURE = ART / 'w45_stratified_residual.png'
REPORT = ROOT / 'reports' / 'w45_stratified_residual.md'
PROBE = ROOT / 'probes' / 'w45_stratified_residual.py'
PREREG = ROOT / 'probes' / 'w45_compute_prereg.json'

CRITERIA_IDS = ['H45b' + str(index) for index in range(1, 11)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
OVERALL_RHO = 0.5984785837315431


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w45_stratified_residual/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_ten_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 10
    assert payload['registered_negatives'] == []


def test_overall_spearman_reproduces_the_anchor() -> None:
    payload = _summary()
    assert payload['paired_rows'] >= 4600
    rows = {row['stratum']: row for row in payload['strata_rows']}
    assert abs(rows['all']['spearman'] - OVERALL_RHO) < 1e-12
    assert payload['bootstrap']['lo'] >= 0.5
    assert payload['permutation']['p_value'] <= 0.001


def test_tier_strata_are_homogeneous() -> None:
    payload = _summary()
    tiers = {row['stratum']: row for row in payload['strata_rows'] if row['scope'] == 'tier'}
    assert set(tiers) == {'calibration_bulk', 'named_core_channel', 'flagship_dielectric'}
    assert all(row['n'] >= 40 for row in tiers.values())
    bulk = tiers['calibration_bulk']['spearman']
    assert all(abs(row['spearman'] - bulk) <= 0.15 for row in tiers.values())


def test_rank_agreement_degrades_with_size() -> None:
    payload = _summary()
    bins = [row for row in payload['strata_rows'] if row['scope'] == 'atom_bin']
    assert [row['stratum'] for row in bins] == ['5-12', '13-17', '18-40']
    assert all(row['n'] >= 100 for row in bins)
    assert all(row['spearman'] >= 0.4 for row in bins)
    assert bins[0]['spearman'] > bins[-1]['spearman']


def test_robust_outlier_scale() -> None:
    payload = _summary()
    rows = {row['stratum']: row for row in payload['strata_rows']}
    assert payload['delta_median_ev'] > 6.0
    assert rows['all']['robust_scale_ev'] <= 1.0
    assert rows['all']['heavy_tail_fraction'] <= 0.20


def test_artifacts_exist_and_figure_renders() -> None:
    for path in (SUMMARY, STRATA_CSV, FIGURE, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (STRATA_CSV, REPORT, PROBE, PREREG):
        data = _bytes(path)
        assert not data.startswith(b'\xef\xbb\xbf'), path
        assert b'\r\n' not in data, path
    assert FIGURE.stat().st_size > 5000
    assert _bytes(FIGURE)[:8] == b'\x89PNG\r\n\x1a\n'
    with STRATA_CSV.open('r', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 7
