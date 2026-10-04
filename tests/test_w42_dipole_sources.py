# Guards for the Week 42 lane W42-C: the three-source dipole decomposition.
# The roster xTB dipole is contrasted with the QM9 and PubChemQC B3LYP gas-phase dipoles.
# The two B3LYP sources agree to ~0.03 D while both sit ~0.4-0.5 D below our xTB value,
# which localises the systematic offset to the method layer.  This lane only attributes
# the offset: no value is corrected or imputed.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w42_dipole_sources_summary.json'
PAIRS = ART / 'w42_dipole_sources.csv'
BLAND = ART / 'w42_bland_altman.csv'
ATTRIBUTION = ART / 'w42_dipole_attribution.json'
FIGURE = ART / 'w42_dipole_sources.png'
REPORT = ROOT / 'reports' / 'w42_dipole_sources.md'
PROBE = ROOT / 'probes' / 'w42_dipole_sources.py'
PREREG = ROOT / 'probes' / 'w42_registry_transfer_prereg.json'

CRITERIA_IDS = ['H42c' + str(index) for index in range(1, 12)]
REGISTERED_NEGATIVES: list = []
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
COVERAGE = {'our': 237, 'qm9': 103, 'pubchemqc': 205, 'three_way': 103}
BIAS_OUR_QM9 = 0.39451165048543685
BIAS_OUR_PC = 0.5129548195121951
BIAS_QM9_PC = -0.03411484466019416
MAE_QM9_PC = 0.20780222330097092
ATTRIBUTION_R2 = 0.6515206141468827
LOCALIZATION_RATIO = 0.7690962936279764


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w42_dipole_sources/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_eleven_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 11
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_three_source_coverage() -> None:
    payload = _summary()
    assert payload['coverage'] == COVERAGE


def test_pairwise_bias_anchors() -> None:
    payload = _summary()
    rows = {row['pair']: row for row in payload['pair_rows']}
    assert abs(rows['our-qm9']['bias_a_minus_b'] - BIAS_OUR_QM9) < 1e-12
    assert abs(rows['our-pubchemqc']['bias_a_minus_b'] - BIAS_OUR_PC) < 1e-12
    assert abs(rows['qm9-pubchemqc']['bias_a_minus_b'] - BIAS_QM9_PC) < 1e-12
    assert abs(rows['qm9-pubchemqc']['mae'] - MAE_QM9_PC) < 1e-12
    assert rows['our-pubchemqc']['mae'] >= rows['our-qm9']['mae']


def test_attribution_r2_and_localization() -> None:
    payload = _summary()
    assert abs(payload['attribution']['r2'] - ATTRIBUTION_R2) < 1e-12
    assert abs(payload['localization_ratio'] - LOCALIZATION_RATIO) < 1e-12
    assert payload['sign_consistent'] is True
    assert payload['attribution']['coef_pubchemqc'] > payload['attribution']['coef_qm9']


def test_bland_altman_limits_and_bootstrap_cis() -> None:
    payload = _summary()
    rows = {row['pair']: row for row in payload['bland_rows']}
    assert rows['our-qm9']['zero_inside_ci'] is False
    assert rows['qm9-pubchemqc']['zero_inside_ci'] is True
    for row in rows.values():
        assert row['loa_lo'] < row['bias'] < row['loa_hi']
        assert 0.9 <= row['within_loa'] <= 1.0


def test_attribution_json_and_artifacts_are_lf_only() -> None:
    attribution = json.loads(ATTRIBUTION.read_text(encoding='utf-8'))
    assert attribution['design'] == 'our = a*QM9 + b*PubChemQC + c'
    assert '归因' in attribution['note']
    assert len(_rows(PAIRS)) == 3
    assert len(_rows(BLAND)) == 3
    for path in (SUMMARY, PAIRS, BLAND, ATTRIBUTION, FIGURE, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (SUMMARY, PAIRS, BLAND, ATTRIBUTION, REPORT, PROBE, PREREG):
        assert b'\r\n' not in path.read_bytes(), path
    assert FIGURE.stat().st_size > 5000
