# Guards for Week 47 lane W47-A: computed-anchor coverage accounting + the oxidation-axis
# computed-vs-experimental cross-consistency reading.  The anchor tables are byte-pinned and the
# H47a2 refusal branch must fire (reduction coverage union 2 < 5); the oxidation tau_b is only a
# sensitivity reading and must travel with its exact one-sided p.
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))

import w47_anchor_crosscheck as probe

ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w47_anchor_crosscheck_summary.json'
COVERAGE_CSV = ART / 'w47_anchor_coverage.csv'
CROSSCHECK_CSV = ART / 'w47_oxidation_crosscheck.csv'
REPORT = ROOT / 'reports' / 'w47_anchor_crosscheck.md'
PREREG = ROOT / 'probes' / 'w47_anchor_prereg.json'
PROBE = ROOT / 'probes' / 'w47_anchor_crosscheck.py'
TABLE1 = ROOT / 'data' / 'external' / 'w47_borodin2013_table1_computed_oxidation.csv'
TABLE3 = ROOT / 'data' / 'external' / 'w47_borodin2013_table3_experimental_oxidation.csv'
TABLE15 = ROOT / 'data' / 'external' / 'w47_borodin2015_li_coupled_reduction.csv'

CRITERIA_IDS = ['H47a' + str(index) for index in range(1, 10)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
TABLE_ROWS = {'computed_oxidation': 16, 'experimental_oxidation': 26,
              'computed_reduction_li_coupled': 8}


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w47_anchor_crosscheck/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS
    assert payload['registered_negatives'] == []


def test_nine_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 9


def test_anchor_tables_pinned_readonly() -> None:
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    for key, expected_rows in TABLE_ROWS.items():
        spec = prereg['anchor_tables'][key]
        path = ROOT / spec['path']
        assert path.is_file()
        assert probe.sha256_file(path) == spec['sha256']
        with path.open(encoding='utf-8-sig', newline='') as handle:
            assert len(list(csv.DictReader(handle))) == expected_rows
    payload = _summary()
    for pin in payload['table_pins'].values():
        assert pin['rows_match'] is True and pin['sha256_match'] is True


def test_refusal_branch_fires_on_real_coverage() -> None:
    payload = _summary()
    coverage = payload['coverage']
    assert coverage['reduction_tracks_union'] == ['EC', 'PC']
    assert coverage['reduction_union_size'] == 2
    assert coverage['min_core_anchors'] == 5
    assert coverage['refusal_fired'] is True
    assert coverage['prereg_all_agree'] is True
    assert payload['main_judgment']['status'] == 'not_executed'


def test_refusal_branch_unit_on_simulated_inputs() -> None:
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    # simulated coverage >= 5 => no refusal
    rich = [{'axis': 'reduction', 'track': 'experimental',
             'solvent': s, 'present': 'yes'} for s in ['EC', 'PC', 'EMC', 'MA', 'SL']]
    rich += [{'axis': 'reduction', 'track': 'computed', 'solvent': 'EC', 'present': 'yes'}]
    ok = probe.coverage_summary(rich, prereg)
    assert ok['reduction_union_size'] == 5
    assert ok['refusal_fired'] is False
    # simulated coverage < 5 => refusal
    thin = [{'axis': 'reduction', 'track': 'experimental', 'solvent': 'PC', 'present': 'yes'}]
    bad = probe.coverage_summary(thin, prereg)
    assert bad['reduction_union_size'] == 1
    assert bad['refusal_fired'] is True


def test_oxidation_crosscheck_small_sample() -> None:
    payload = _summary()
    cross = payload['crosscheck']
    assert cross['n'] == 4 and cross['pairs'] == 6
    assert abs(cross['tau_b'] - 0.6666666666666669) < 1e-12
    assert abs(cross['exact_p_upper'] - 0.16666666666666666) < 1e-12
    assert abs(cross['unresolved_share_primary_to_experimental'] - 1.0 / 3.0) < 1e-12
    tops = {item['k']: item['overlap'] for item in cross['top_k']}
    assert tops[1] == 1.0 and abs(tops[2] - 0.5) < 1e-12
    assert cross['gate_filter']['applicable'] is False
    assert cross['gate_filter']['n_before'] == cross['gate_filter']['n_after']
    assert cross['experimental_picks']['SL']['criterion_flag'].startswith('criterion_secondary')
    assert cross['experimental_picks']['EC']['potential_V_vs_Li'] == 6.2


def test_crosscheck_csv_and_report_on_disk() -> None:
    for path in (COVERAGE_CSV, CROSSCHECK_CSV, REPORT, PROBE):
        assert path.is_file() and path.stat().st_size > 0
    with COVERAGE_CSV.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 28  # 4 (axis x track) x 7 core solvents
    assert all(row['present'] in ('yes', 'no') for row in rows)
    with CROSSCHECK_CSV.open(encoding='utf-8', newline='') as handle:
        cross_rows = list(csv.DictReader(handle))
    assert [row['solvent'] for row in cross_rows] == ['EC', 'PC', 'EMC', 'SL']
