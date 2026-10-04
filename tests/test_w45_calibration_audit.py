# Guards for the Week 45 lane W45-A: the fidelity and leakage audit of the expanded layer's
# calibration columns.  calib_homo_eV is an exact single global affine map of homo_gfn2_eV, and it
# is the same map as the in-sample OLS fit of homo_gfn2 -> homo_batt, so the calibration fixes the
# level (MAE 1.2066 -> 0.3032 eV) but adds zero rank information.  calib_lumo_eV is not populated.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w45_calibration_audit_summary.json'
AUDIT_CSV = ART / 'w45_calibration_audit.csv'
AUDIT_JSON = ART / 'w45_calibration_audit.json'
REPORT = ROOT / 'reports' / 'w45_calibration_audit.md'
PROBE = ROOT / 'probes' / 'w45_calibration_audit.py'
PREREG = ROOT / 'probes' / 'w45_compute_prereg.json'

CRITERIA_IDS = ['H45a' + str(index) for index in range(1, 11)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
SLOPE = 0.8702565775077505
INTERCEPT = -0.20421040258262516


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w45_calibration_audit/summary@1'
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


def test_calibration_is_an_exact_global_affine() -> None:
    payload = _summary()
    assert payload['paired_rows'] >= 4600
    assert payload['calibrated_rows'] >= 400
    row = payload['audit_rows'][0]
    assert row['target'] == 'homo'
    assert abs(row['affine_slope'] - SLOPE) < 1e-12
    assert abs(row['affine_intercept'] - INTERCEPT) < 1e-12
    assert row['affine_max_abs_residual'] < 1e-9
    assert payload['calibrated_same_map_max_abs_residual'] < 1e-9


def test_calibration_only_fixes_the_level() -> None:
    payload = _summary()
    row = payload['audit_rows'][0]
    assert row['rank_invariance_delta'] < 1e-9
    assert abs(row['spearman_calib_batt'] - row['spearman_gfn2_batt']) < 1e-9
    assert row['mae_before_ev'] >= 1.0
    assert row['mae_after_ev'] <= 0.35
    assert row['mae_cv_ev'] <= 0.45
    assert row['leakage_gap_ev'] >= 0.0


def test_calibration_map_matches_the_batt_fit_and_only_covers_homo() -> None:
    payload = _summary()
    row = payload['audit_rows'][0]
    assert row['slope_delta'] < 1e-6
    assert row['intercept_delta'] < 1e-6
    assert row['mae_after_ev'] < row['mae_before_ev']
    homo_only = next(item for item in payload['criteria'] if item['id'] == 'H45a7')
    assert homo_only['verdict'] == '成立'
    assert homo_only['value']['calib_lumo_nonempty'] == 0
    assert homo_only['value']['calib_homo_nonempty'] >= 4000


def test_artifacts_exist_and_are_lf_only() -> None:
    for path in (SUMMARY, AUDIT_CSV, AUDIT_JSON, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (AUDIT_CSV, AUDIT_JSON, REPORT, PROBE, PREREG):
        data = _bytes(path)
        assert not data.startswith(b'\xef\xbb\xbf'), path
        assert b'\r\n' not in data, path
    with AUDIT_CSV.open('r', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 1
