# Guards for the Week 43 lane W43-B: the dipole-correction protocol preregistration.
# The ~0.39 D xTB -> B3LYP dipole offset is written as a locked protocol with three
# variants.  The correction itself stays UNAUTHORIZED: the lane only measures the offline
# impact on the W40-C domain table and never rewrites a label or feature column.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w43_dipole_protocol_summary.json'
PROTOCOL = ART / 'w43_dipole_protocol.json'
IMPACT = ART / 'w43_dipole_impact.csv'
REPORT = ROOT / 'reports' / 'w43_dipole_protocol.md'
PROBE = ROOT / 'probes' / 'w43_dipole_protocol.py'
PREREG = ROOT / 'probes' / 'w43_protocol_prereg.json'

CRITERIA_IDS = ['H43b' + str(index) for index in range(1, 13)]
REGISTERED_NEGATIVES: list = []
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
OVERLAP_N = 103
UNCORRECTED_RATIO = 2.5817134002985758
LEGACY_RATIO = 3.113252911075283
AFFINE_SLOPE = 0.7505560209207711
AFFINE_INTERCEPT = 0.16227395046765383
AFFINE_R2 = 0.6141809025552685
MAE_UNCORRECTED = 0.610309708737864
MAE_CORRECTED = 0.4604847987809531


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w43_dipole_protocol/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_twelve_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 12
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_protocol_is_registered_but_not_authorized() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding='utf-8'))
    assert protocol['protocol_id'] == 'dipole_transfer_v1'
    assert protocol['status'] == 'registered_not_authorized'
    assert '不执行' in protocol['authorization']
    assert set(protocol['variants']) == {'legacy', 'shift_mean', 'shift_median', 'affine'}


def test_affine_estimator_diagnostics() -> None:
    affine = _summary()['protocol']['affine_diagnostics']
    assert abs(affine['slope'] - AFFINE_SLOPE) < 1e-12
    assert abs(affine['intercept'] - AFFINE_INTERCEPT) < 1e-12
    assert abs(affine['r2'] - AFFINE_R2) < 1e-12
    assert abs(affine['mae_uncorrected'] - MAE_UNCORRECTED) < 1e-12
    assert abs(affine['mae_corrected'] - MAE_CORRECTED) < 1e-12
    assert affine['mae_corrected'] < affine['mae_uncorrected']


def test_loo_bias_ci_excludes_zero() -> None:
    loo = _summary()['protocol']['affine_diagnostics']['leave_one_out']
    assert loo['n'] == OVERLAP_N
    assert loo['zero_inside_ci'] is False
    assert 0.0 < loo['ci_lo'] < loo['ci_hi']


def test_legacy_variant_reproduces_domain_table() -> None:
    payload = _summary()
    assert payload['protocol']['legacy_reproduction_max_abs_D'] <= 1e-9
    assert abs(payload['uncorrected_ratio'] - UNCORRECTED_RATIO) < 1e-9


def test_offline_impact_is_same_tier() -> None:
    payload = _summary()
    rows = {row['variant']: row for row in payload['impact_rows']}
    assert abs(rows['legacy']['domain_ratio'] - LEGACY_RATIO) < 1e-9
    for name in ('legacy', 'shift_mean', 'shift_median', 'affine'):
        assert abs(rows[name]['delta_vs_uncorrected']) <= 1.0
    for name in ('legacy', 'shift_mean', 'shift_median'):
        assert rows[name]['applied_rows'] >= 200
    assert rows['legacy']['dropped_nonpositive'] <= 30


def test_artifacts_are_lf_only() -> None:
    assert len(_rows(IMPACT)) == 4
    for path in (SUMMARY, PROTOCOL, IMPACT, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (SUMMARY, PROTOCOL, IMPACT, REPORT, PROBE, PREREG):
        assert b'\r\n' not in path.read_bytes(), path
