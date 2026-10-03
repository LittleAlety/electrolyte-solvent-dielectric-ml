# Guards for the Week 38-B lane: structure is not function.
#
# The fingerprint-blind finding (Tanimoto >= 0.99 yet up to 13.25 in epsilon) is the
# mechanism candidate behind "the ECFP block is net harmful under lever 4": a
# representation that maps a 7x dielectric ratio onto one vector can only add noise.
# H38b1 is a REGISTERED negative (no pair with Tanimoto >= 0.80 reaches |delta eps| >= 30;
# the observed ceiling is 25.98) and must stay registered.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w38_structure_function_summary.json'
NN = ROOT / 'probes' / 'artifacts' / 'w38_structure_nn.csv'
PAIRS = ROOT / 'probes' / 'artifacts' / 'w38_structure_pairs.csv'
FIGURE = ROOT / 'probes' / 'artifacts' / 'w38_structure_function.png'
REPORT = ROOT / 'reports' / 'w38_structure_function.md'


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['task'] == 'week38_structure_function'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True


def test_verdict_pattern_is_six_passes_and_one_registered_negative() -> None:
    payload = _summary()
    verdicts = payload['criteria']
    assert [item['id'] for item in verdicts] == ['H38b1', 'H38b2', 'H38b3', 'H38b4',
                                                 'H38b6', 'H38b7', 'H38b5']
    assert {item['id'] for item in verdicts if item['verdict'] != '成立'} == {'H38b1'}
    assert payload['registered_negatives'] == ['H38b1']


def test_structure_only_baseline_is_weak() -> None:
    payload = _summary()['structure_only_baseline']
    assert abs(float(payload['nn_r2']) - 0.2502679) < 1e-5
    assert float(payload['nn_r2']) < 0.50


def test_fingerprint_blind_pairs_are_recorded() -> None:
    two_way = _summary()['two_way_search']
    assert two_way['n_compounds'] == 241
    assert two_way['n_blind'] == 26
    assert two_way['n_blind_differ'] == 4
    assert abs(float(two_way['max_blind_delta']) - 13.25) < 0.01
    assert two_way['n_look_alike_differ'] == 0


def test_permutation_pins_similarity_as_weak_but_real() -> None:
    permutation = _summary()['permutation']
    assert permutation['n_permutations'] == 999
    assert abs(float(permutation['observed_spearman']) + 0.060708) < 1e-5
    assert abs(float(permutation['z'])) >= 2.0


def test_blind_pairs_land_in_the_pairs_csv() -> None:
    rows = list(csv.DictReader(PAIRS.open(encoding='utf-8', newline='')))
    blind = [row for row in rows if row['kind'] == 'fingerprint_blind']
    assert blind
    assert max(float(row['abs_delta_eps']) for row in blind) >= 13.2
    assert FIGURE.is_file() and FIGURE.stat().st_size > 0
    assert '指纹盲区' in REPORT.read_text(encoding='utf-8')
