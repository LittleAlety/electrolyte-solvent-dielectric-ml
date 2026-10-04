# Guards for the Week 41 lane W41-D: the orbital-channel level declaration.
# Three layers (GFN2-xTB gas / B3LYP gas / wB97X-V+SMD) are registered on the same 241-row
# roster; pairwise rank transfer is measured and shown to be non-transitive on the common
# 48 compounds.  H41d8 registers the rejected claim that a single cross-level ranking prior
# can stand in for another layer.  External-layer numbers never enter the label pool.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w41_orbital_level_declaration_summary.json'
REGISTRY = ART / 'w41_orbital_level_registry.csv'
PAIRS = ART / 'w41_orbital_pair_matrix.csv'
HITS = ART / 'w41_orbital_batt_hits.csv'
DECLARATION = ART / 'w41_orbital_level_declaration.json'
FIGURE = ART / 'w41_orbital_level_declaration.png'
REPORT = ROOT / 'reports' / 'w41_orbital_level_declaration.md'
PROBE = ROOT / 'probes' / 'w41_orbital_level_declaration.py'
PREREG = ROOT / 'probes' / 'w41_governance_prereg.json'

CRITERIA_IDS = ['H41d' + str(index) for index in range(1, 12)]
REGISTERED_NEGATIVES = ['H41d8']
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
COVERAGE = {'roster': 241, 'xtb': 237, 'qm9': 103, 'batt': 73, 'triple': 48}
XTB_QM9_SPEARMAN = 0.8856281475401158
QM9_BATT_SPEARMAN = 0.8176735614281957
XTB_BATT_SPEARMAN = 0.33037146735776873
TRIPLE_XTB_BATT_SPEARMAN = 0.5384281372123317
CALIB_SLOPE = 2.0266971543817958
CALIB_INTERCEPT = -8.8728945529514


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w41_orbital_level_declaration/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_eleven_criteria_with_the_transfer_claim_registered_as_negative() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    verdicts = {item['id']: item['verdict'] for item in criteria}
    assert [key for key, value in verdicts.items() if value != '成立'] == REGISTERED_NEGATIVES
    assert verdicts['H41d8'] == '判否'
    assert payload['registered_negatives'] == REGISTERED_NEGATIVES


def test_coverage_matches_the_registered_anchors() -> None:
    payload = _summary()
    assert payload['coverage'] == COVERAGE


def test_pairwise_rank_transfer_reproduces_anchors() -> None:
    payload = _summary()
    by_key = {(item['pair'], item['subset']): item for item in payload['pairs']}
    assert abs(by_key[('xtb_qm9', 'available')]['spearman'] - XTB_QM9_SPEARMAN) < 1e-12
    assert abs(by_key[('qm9_batt', 'available')]['spearman'] - QM9_BATT_SPEARMAN) < 1e-12
    assert abs(by_key[('xtb_batt', 'available')]['spearman'] - XTB_BATT_SPEARMAN) < 1e-12
    assert abs(by_key[('xtb_batt', 'triple')]['spearman'] - TRIPLE_XTB_BATT_SPEARMAN) < 1e-12
    gap = (min(by_key[('xtb_qm9', 'triple')]['spearman'],
               by_key[('qm9_batt', 'triple')]['spearman'])
           - by_key[('xtb_batt', 'triple')]['spearman'])
    assert gap > 0.2


def test_declaration_is_cross_level_and_calibration_reproduces_w40() -> None:
    declaration = json.loads(DECLARATION.read_text(encoding='utf-8'))
    assert declaration['schema'] == 'w41_orbital_level_declaration/declaration@1'
    assert declaration['n_same_level_pairs'] == 0
    assert declaration['same_level_external_source_present'] is False
    assert declaration['statement']
    calib = declaration['calibration_xtb_on_qm9']
    assert abs(calib['slope'] - CALIB_SLOPE) < 1e-12
    assert abs(calib['intercept'] - CALIB_INTERCEPT) < 1e-11


def test_level_registry_has_three_layers_and_batt_hits_table() -> None:
    rows = _rows(REGISTRY)
    assert len(rows) == 3
    assert {row['level_id'] for row in rows} == {'batt_wb97xv_smd', 'themol_gfn2_gas',
                                                 'qm9_b3lyp_gas'}
    hits = _rows(HITS)
    assert len(hits) == COVERAGE['batt']
    pair_rows = _rows(PAIRS)
    assert len(pair_rows) == 6
    assert all(row['comparability'] == 'cross_level' for row in pair_rows)


def test_artifacts_and_report_exist_and_are_lf_only() -> None:
    for path in (SUMMARY, REGISTRY, PAIRS, HITS, DECLARATION, FIGURE, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (SUMMARY, REGISTRY, PAIRS, HITS, DECLARATION, REPORT, PROBE, PREREG):
        assert b'\r\n' not in path.read_bytes(), path
    assert FIGURE.stat().st_size > 5000