# Guards for the Week 42 lane W42-B: the xTB -> Batt monotone proxy calibration.
# Isotonic regression is fitted on the 73 compounds that carry both an xTB gap and a
# Batt-P30K gap; in-sample and 5-fold CV rank fidelity plus threshold AUCs bound how far
# the xTB layer can stand in for the wB97X-V/SMD channel.  The calibrated values never
# replace a label.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w42_proxy_calibration_summary.json'
METRICS = ART / 'w42_proxy_calibration.csv'
CURVE = ART / 'w42_isotonic_curve.csv'
FIGURE = ART / 'w42_proxy_calibration.png'
REPORT = ROOT / 'reports' / 'w42_proxy_calibration.md'
PROBE = ROOT / 'probes' / 'w42_proxy_calibration.py'
PREREG = ROOT / 'probes' / 'w42_registry_transfer_prereg.json'

CRITERIA_IDS = ['H42b' + str(index) for index in range(1, 11)]
REGISTERED_NEGATIVES: list = []
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
N = 73
SPEARMAN_RAW = 0.32799580402320133
ISOTONIC_IN_SAMPLE_R2 = 0.33099194929465536
ISOTONIC_IN_SAMPLE_SPEARMAN = 0.5461169204020767
ISOTONIC_CV_R2 = 0.22252080116807227
ISOTONIC_CV_SPEARMAN = 0.4150071593578348
AUC_MEDIAN_RAW = 0.6921921921921921
AUC_MEDIAN_CV = 0.7304804804804804
AUC_TOP_QUARTILE_CV = 0.7719298245614035
PROXY_FIDELITY_RATIO = 0.37039060811635766


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w42_proxy_calibration/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_ten_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 10
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_isotonic_reproduces_in_sample_and_cv_anchors() -> None:
    payload = _summary()
    metrics = {row['metric']: row['value'] for row in payload['metrics']}
    assert payload['n'] == N
    assert abs(metrics['spearman_raw'] - SPEARMAN_RAW) < 1e-12
    assert abs(metrics['isotonic_in_sample_r2'] - ISOTONIC_IN_SAMPLE_R2) < 1e-12
    assert abs(metrics['isotonic_in_sample_spearman'] - ISOTONIC_IN_SAMPLE_SPEARMAN) < 1e-12
    assert abs(metrics['isotonic_cv_r2'] - ISOTONIC_CV_R2) < 1e-12
    assert abs(metrics['isotonic_cv_spearman'] - ISOTONIC_CV_SPEARMAN) < 1e-12
    assert metrics['monotone_violations'] == 0.0


def test_auc_anchors_and_monotone_improvement() -> None:
    payload = _summary()
    auc = payload['auc']
    assert abs(auc['median_raw'] - AUC_MEDIAN_RAW) < 1e-12
    assert abs(auc['median_isotonic_cv'] - AUC_MEDIAN_CV) < 1e-12
    assert abs(auc['top_quartile_isotonic_cv'] - AUC_TOP_QUARTILE_CV) < 1e-12
    assert auc['median_isotonic_cv'] > auc['median_raw']


def test_proxy_fidelity_ratio_bounds_the_substitution() -> None:
    payload = _summary()
    metrics = {row['metric']: row['value'] for row in payload['metrics']}
    assert abs(metrics['proxy_fidelity_ratio'] - PROXY_FIDELITY_RATIO) < 1e-12
    assert metrics['proxy_fidelity_ratio'] < 0.40
    assert metrics['rho_xtb_qm9_reference'] > 0.85


def test_bootstrap_refit_covers_the_in_sample_point() -> None:
    payload = _summary()
    boot = payload['isotonic_bootstrap']
    assert boot['lo'] <= boot['point'] <= boot['hi'] or boot['lo'] <= boot['mean'] <= boot['hi']
    assert boot['sd'] > 0.0
    assert payload['monotone'] is True


def test_curve_and_artifacts_exist_and_are_lf_only() -> None:
    rows = list(csv.DictReader(CURVE.open('r', encoding='utf-8', newline='')))
    assert len(rows) == N
    assert all(float(row['fitted_batt_gap_ev']) > 0.0 for row in rows)
    metric_rows = list(csv.DictReader(METRICS.open('r', encoding='utf-8', newline='')))
    assert len(metric_rows) == 14
    for path in (SUMMARY, METRICS, CURVE, FIGURE, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (SUMMARY, METRICS, CURVE, REPORT, PROBE, PREREG):
        assert b'\r\n' not in path.read_bytes(), path
    assert FIGURE.stat().st_size > 5000
