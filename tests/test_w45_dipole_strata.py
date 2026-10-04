# Guards for the Week 45 lane W45-C: the stratified attribution of the ~0.39 D dipole bias.
# The mean bias reproduces the W42-C anchor exactly; the bias is not a constant shift but grows with
# the dipole magnitude (low tercile 0.060 D, high tercile 0.521 D), which favours the affine variant
# of the W43-B correction protocol over the pure shift variant.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w45_dipole_strata_summary.json'
STRATA_CSV = ART / 'w45_dipole_strata.csv'
FIGURE = ART / 'w45_dipole_strata.png'
REPORT = ROOT / 'reports' / 'w45_dipole_strata.md'
PROBE = ROOT / 'probes' / 'w45_dipole_strata.py'
PREREG = ROOT / 'probes' / 'w45_compute_prereg.json'

CRITERIA_IDS = ['H45c' + str(index) for index in range(1, 11)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
MEAN_ANCHOR = 0.39451165048543685


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w45_dipole_strata/summary@1'
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


def test_mean_bias_reproduces_the_anchor() -> None:
    payload = _summary()
    assert payload['overlap_rows'] >= 90
    assert abs(payload['mean_delta_D'] - MEAN_ANCHOR) < 1e-9
    lo, hi = payload['bootstrap_ci']
    assert lo > 0 and hi > lo
    assert payload['permutation_p'] <= 0.001
    assert payload['wilcoxon_p'] <= 0.001


def test_bias_grows_with_dipole_magnitude() -> None:
    payload = _summary()
    terciles = {row['stratum']: row for row in payload['strata_rows']
                if row['scope'] == 'dipole_tercile'}
    assert set(terciles) == {'low', 'mid', 'high'}
    assert all(row['n'] >= 20 for row in terciles.values())
    low = terciles['low']['median_delta_D']
    mid = terciles['mid']['median_delta_D']
    high = terciles['high']['median_delta_D']
    assert low <= mid <= high
    assert low <= 0.10
    assert high >= 0.30


def test_strata_are_all_positive_and_not_a_size_artifact() -> None:
    payload = _summary()
    per_stratum = [row for row in payload['strata_rows'] if row['scope'] != 'overall']
    assert all(row['median_delta_D'] > 0 for row in per_stratum)
    assert abs(payload['size_corr']) <= 0.5


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
    assert len(rows) >= 10
