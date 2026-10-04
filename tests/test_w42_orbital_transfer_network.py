# Guards for the Week 42 lane W42-A: the four-layer orbital transfer network.
# PubChemQC (B3LYP/6-31G*//PM6 gas) joins the W41 three-layer network on the same 241-row
# roster.  Coverage, all 15 intersections, six pairwise rank transfers (with bootstrap CIs
# and permutation nulls) and the triangle non-transitivity closure are pinned here.
# QM9 and PubChemQC are declared near_same_level (same functional + phase, different basis
# and geometry); external-layer numbers never enter the label pool.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w42_orbital_transfer_network_summary.json'
REGISTRY = ART / 'w42_orbital_layer_registry.csv'
INTERSECTIONS = ART / 'w42_orbital_intersections.csv'
PAIRS = ART / 'w42_transfer_pairs.csv'
TRIANGLES = ART / 'w42_transfer_triangles.csv'
NEAR_LEVEL = ART / 'w42_near_same_level.json'
FIGURE = ART / 'w42_orbital_transfer_network.png'
REPORT = ROOT / 'reports' / 'w42_orbital_transfer_network.md'
PROBE = ROOT / 'probes' / 'w42_orbital_transfer_network.py'
PREREG = ROOT / 'probes' / 'w42_registry_transfer_prereg.json'

CRITERIA_IDS = ['H42a' + str(index) for index in range(1, 14)]
REGISTERED_NEGATIVES: list = []
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
COVERAGE = {'xtb': 237, 'qm9': 103, 'pubchemqc': 205, 'batt': 73, 'four_way': 48,
            'roster': 241}
PAIR_ANCHORS = {
    'xtb-qm9': 0.8855402832464961,
    'xtb-pubchemqc': 0.8824496277535964,
    'xtb-batt': 0.32799580402320133,
    'qm9-pubchemqc': 0.9823336400382101,
    'qm9-batt': 0.8176735614281957,
    'pubchemqc-batt': 0.7386459868154263,
}
NEAR_LEVEL_SPEARMAN = 0.9823336400382101
NEAR_LEVEL_MAE = 0.1612343280021094
MAX_TRIANGLE_GAP = 0.48967775740499436


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w42_orbital_transfer_network/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_thirteen_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 13
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_four_layer_coverage_and_four_way_intersection() -> None:
    payload = _summary()
    assert payload['coverage'] == COVERAGE
    rows = _rows(INTERSECTIONS)
    assert len(rows) == 15
    by_key = {row['combination']: int(row['n']) for row in rows}
    assert by_key['xtb+qm9+pubchemqc+batt'] == 48
    assert by_key['xtb'] == 237
    assert by_key['batt'] == 73


def test_six_pairwise_transfers_reproduce_anchors() -> None:
    payload = _summary()
    by_key = {(row['pair'], row['subset']): row for row in payload['pairs']}
    for pair, anchor in PAIR_ANCHORS.items():
        assert abs(by_key[(pair, 'full')]['spearman'] - anchor) < 1e-12, pair
    assert by_key[('xtb-batt', 'full')]['spearman'] < 0.60
    assert by_key[('qm9-pubchemqc', 'full')]['spearman'] > 0.95


def test_bootstrap_cis_and_permutation_nulls_exclude_zero() -> None:
    payload = _summary()
    full = [row for row in payload['pairs'] if row['subset'] == 'full']
    assert all(row['ci_lo'] > 0.0 for row in full)
    assert all(abs(row['perm_p']) < 0.01 for row in full)
    assert all(row['n'] >= 48 for row in full)


def test_transfer_is_not_transitive_on_the_xbt_batt_edge() -> None:
    payload = _summary()
    by_triangle = {row['triangle']: row for row in payload['triangles']}
    assert len(by_triangle) == 4
    assert abs(by_triangle['xtb-qm9-batt']['max_gap'] - MAX_TRIANGLE_GAP) < 1e-12
    assert by_triangle['xtb-qm9-batt']['broken_edge'] == 'xtb-batt'
    assert by_triangle['qm9-pubchemqc-batt']['max_gap'] < 0.10


def test_near_same_level_declaration_and_strict_count() -> None:
    payload = _summary()
    near = json.loads(NEAR_LEVEL.read_text(encoding='utf-8'))
    assert near['classification'] == 'near_same_level'
    assert abs(near['spearman'] - NEAR_LEVEL_SPEARMAN) < 1e-12
    assert abs(near['gap_mae_ev'] - NEAR_LEVEL_MAE) < 1e-12
    assert near['functional_a'] == near['functional_b'] == 'B3LYP'
    assert near['basis_a'] != near['basis_b']
    assert payload['strict_same_level_count'] == 0


def test_artifacts_and_report_exist_and_are_lf_only() -> None:
    for path in (SUMMARY, REGISTRY, INTERSECTIONS, PAIRS, TRIANGLES, NEAR_LEVEL, FIGURE,
                 REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (SUMMARY, REGISTRY, INTERSECTIONS, PAIRS, TRIANGLES, NEAR_LEVEL, REPORT,
                 PROBE, PREREG):
        assert b'\r\n' not in path.read_bytes(), path
    assert FIGURE.stat().st_size > 5000
