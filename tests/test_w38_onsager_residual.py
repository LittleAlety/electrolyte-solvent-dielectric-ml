# Guards for the Week 38-C lane: the Kirkwood-Onsager residual diagnostic.
#
# The falsifiable prediction inherited from the mother paper and from GSDS is that the
# residual of the single-molecule description concentrates on self-associating protic
# liquids (g >> 1).  All primary criteria are median/rank based because the dipole
# column has known quality problems, and H38c5 (leave-top-5-out) exists precisely to
# prove the conclusion is not driven by those outliers.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w38_onsager_residual_summary.json'
COMPOUNDS = ROOT / 'probes' / 'artifacts' / 'w38_onsager_compounds.csv'
DOMAINS = ROOT / 'probes' / 'artifacts' / 'w38_onsager_domains.csv'
FIGURE = ROOT / 'probes' / 'artifacts' / 'w38_onsager_g.png'
REPORT = ROOT / 'reports' / 'w38_onsager_residual.md'


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['task'] == 'week38_onsager_residual'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == [0.4091179943351143, 0.4766400383507876]


def test_all_eight_criteria_pass() -> None:
    verdicts = _summary()['criteria']
    assert [item['id'] for item in verdicts] == ['H38c1', 'H38c2', 'H38c3', 'H38c4',
                                                 'H38c5', 'H38c6', 'H38c8', 'H38c7']
    assert all(item['verdict'] == '成立' for item in verdicts)


def test_domain_contrast_is_the_registered_value() -> None:
    domains = _summary()['domains']
    assert domains['A']['n'] == 159
    assert domains['B']['n'] == 68
    assert abs(float(domains['ratio_B_over_A']) - 2.501616) < 1e-5


def test_permutation_and_robustness() -> None:
    permutation = _summary()['permutation']
    assert permutation['n_permutations'] == 999
    assert abs(float(permutation['z']) - 4.0761) < 1e-3
    assert float(permutation['p_two_sided']) < 0.05
    leave_out = _summary()['robustness_leave_top_k_out']
    assert float(leave_out['5']) >= 1.5


def test_high_eps_family_is_bimodal_as_predicted() -> None:
    family = _summary()['high_eps_family']
    assert family['n'] == 8
    assert len(family['members']) == 8
    assert float(family['median_g_rel_hbd_ge_1']) > float(family['median_g_rel_hbd_eq_0'])
    assert float(family['ratio']) >= 2.0
    names = {member['name'] for member in family['members']}
    assert 'formamide' in names and 'N-methylacetamide' in names


def test_domain_rule_reliability_is_recorded() -> None:
    reliability = _summary()['domain_rule_reliability']
    assert reliability['n_paired'] == 237
    assert float(reliability['agreement']) == 1.0


def test_rank_is_gated_because_l_over_x_diverges_at_zero_dipole() -> None:
    summary = _summary()
    artifact = summary['ill_conditioned_unrestricted_top5']
    assert artifact
    assert min(float(item['dipole_D']) for item in artifact) < 0.06
    ranked = summary['ranked_by_g']
    assert float(ranked['min_dipole_D']) == 1.0
    assert len(ranked['members']) == 10
    assert float(ranked['top10_domain_B_share']) >= 0.8
    assert sum(1 for item in ranked['members'] if item['domain'] == 'B') >= 8


def test_caveat_and_artifacts_present() -> None:
    summary = _summary()
    assert summary['dipole_caveat_top5']
    rows = list(csv.DictReader(COMPOUNDS.open(encoding='utf-8', newline='')))
    assert len(rows) == 227
    assert {row['domain'] for row in rows} == {'A', 'B'}
    domain_rows = list(csv.DictReader(DOMAINS.open(encoding='utf-8', newline='')))
    assert len(domain_rows) == 2
    assert FIGURE.is_file() and FIGURE.stat().st_size > 0
    assert '边界' in REPORT.read_text(encoding='utf-8')
