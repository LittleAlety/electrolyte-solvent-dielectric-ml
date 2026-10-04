# Guards for the Week 43 lane W43-A: the layer-residual decomposition.
# The xTB-Batt pair is lifted from the 73-row roster to a 4668-row expanded layer; the
# residual is split into a same-method geometry shift and a same-functional basis shift.
# This lane quantifies the near_same_level residual; it never promotes it to strict
# same_level and never writes any external layer into labels or features.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w43_layer_residual_summary.json'
PAIRS = ART / 'w43_layer_residual_pairs.csv'
GEOMETRY = ART / 'w43_geometry_residual.csv'
BASIS = ART / 'w43_basis_residual.csv'
DESCRIPTORS = ART / 'w43_residual_descriptors.csv'
CLAUSE = ART / 'w43_applicability_clause.json'
FIGURE = ART / 'w43_layer_residual.png'
REPORT = ROOT / 'reports' / 'w43_layer_residual.md'
PROBE = ROOT / 'probes' / 'w43_layer_residual.py'
PREREG = ROOT / 'probes' / 'w43_protocol_prereg.json'

CRITERIA_IDS = ['H43a' + str(index) for index in range(1, 16)]
REGISTERED_NEGATIVES: list = []
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
COVERAGE = {'expanded_rows': 5117, 'expanded_xtb_batt': 4668,
            'expanded_xtb_pubchemqc': 208, 'expanded_in_roster': 142, 'roster_xtb_batt': 73}
EXPANDED_XTB_BATT_SPEARMAN = 0.5984785837315431
EXPANDED_XTB_BATT_KENDALL = 0.4243380128602942
ROSTER_XTB_BATT_SPEARMAN = 0.32799580402320133
GEOMETRY_N = 137
GEOMETRY_SPEARMAN = 0.991566636175257
GEOMETRY_MAE_EV = 0.15989343065693432
BASIS_MAE_EV = 0.1612343280021094
BASIS_COVERAGE_02 = 0.6893203883495146
ISOTONIC_CV_R2 = 0.40413466378707663
ISOTONIC_CV_SPEARMAN = 0.5994823471948241
AUC_CV = 0.7957433572045887


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w43_layer_residual/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_fifteen_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 15
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_coverage_anchors() -> None:
    assert _summary()['coverage'] == COVERAGE


def test_expanded_pair_is_optimistic_tail() -> None:
    rows = {(row['pair'], row['scope']): row for row in _summary()['pair_rows']}
    expanded = rows[('xtb-batt', 'expanded')]
    roster = rows[('xtb-batt', 'roster')]
    assert abs(expanded['spearman'] - EXPANDED_XTB_BATT_SPEARMAN) < 1e-12
    assert abs(expanded['kendall'] - EXPANDED_XTB_BATT_KENDALL) < 1e-12
    assert abs(roster['spearman'] - ROSTER_XTB_BATT_SPEARMAN) < 1e-12
    assert expanded['spearman'] - roster['spearman'] > 0.2


def test_geometry_residual_rank_preserving() -> None:
    geometry = _summary()['geometry']
    assert geometry['n'] == GEOMETRY_N
    assert abs(geometry['spearman'] - GEOMETRY_SPEARMAN) < 1e-12
    assert abs(geometry['mae_ev'] - GEOMETRY_MAE_EV) < 1e-12
    assert geometry['permutation_p']['p_value'] <= 0.01


def test_basis_residual_coverage_curve() -> None:
    basis = _summary()['basis']
    assert abs(basis['mean_abs_ev'] - BASIS_MAE_EV) < 1e-12
    assert abs(basis['coverage']['0.2'] - BASIS_COVERAGE_02) < 1e-12
    curve = basis['coverage']
    assert curve['0.1'] < curve['0.2'] < curve['0.3'] < curve['0.5'] < curve['1']


def test_isotonic_proxy_and_auc() -> None:
    payload = _summary()
    assert abs(payload['isotonic']['cv_r2'] - ISOTONIC_CV_R2) < 1e-12
    assert abs(payload['isotonic']['cv_spearman'] - ISOTONIC_CV_SPEARMAN) < 1e-12
    assert abs(payload['auc']['cv'] - AUC_CV) < 1e-12
    assert payload['isotonic']['in_sample_spearman'] > payload['pair_rows'][0]['spearman']


def test_clause_never_promotes_to_strict_same_level() -> None:
    clause = json.loads(CLAUSE.read_text(encoding='utf-8'))
    assert clause['clause_id'] == 'w43_applicability_clause_v1'
    assert clause['same_method_geometry']['verdict'] == 'rank_preserving'
    assert clause['near_same_level_basis']['verdict'] == 'usable_as_bound'
    assert clause['cross_method']['verdict'] == 'not_same_level'
    assert 'strict same_level' in ' '.join(clause['forbidden'])


def test_artifacts_are_lf_only() -> None:
    assert len(_rows(PAIRS)) == 3
    assert len(_rows(GEOMETRY)) >= 100
    assert len(_rows(BASIS)) == 103
    assert len(_rows(DESCRIPTORS)) >= 5
    for path in (SUMMARY, PAIRS, GEOMETRY, BASIS, DESCRIPTORS, CLAUSE, FIGURE, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (SUMMARY, PAIRS, GEOMETRY, BASIS, DESCRIPTORS, CLAUSE, REPORT, PROBE, PREREG):
        assert b'\r\n' not in path.read_bytes(), path
    assert FIGURE.stat().st_size > 5000
