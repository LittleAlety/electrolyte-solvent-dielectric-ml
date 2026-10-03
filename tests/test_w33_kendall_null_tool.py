# Guards for the Week 33-B exact Kendall tau_b null-distribution tool.
#
# Week 32-A fitted the resampling law of tau_b as a closed form.  Week 33-B supplies
# its exact small-sample counterpart: for n <= 12 the null distribution of Kendall
# tau_b (no ties) is the Mahonian inversion-count distribution, so p-values and
# critical values are exact rationals rather than a normal approximation.  These
# guards pin the arithmetic that a sign slip would silently destroy -- in particular
# the one-sided UPPER tail, which a first draft read off the lower tail and so
# returned -0.8 where n = 5 demands +0.8.
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w33_kendall_null_tool as tool

SUMMARY = ROOT / 'probes' / 'artifacts' / 'w33_kendall_null_summary.json'
TABLE = ROOT / 'probes' / 'artifacts' / 'w33_kendall_null_table.csv'
BUDGET = ROOT / 'probes' / 'artifacts' / 'w33_kendall_null_budget.csv'
FIGURE = ROOT / 'probes' / 'artifacts' / 'w33_kendall_null.png'
REPORT = ROOT / 'reports' / 'w33_kendall_null_tool.md'
RANK_JSON = ROOT / 'probes' / 'artifacts' / 'w32_rank_stability.json'

CORE_CHANNELS = {'dielectric', 'viscosity', 'orbital', 'redox'}


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def test_lane_is_a_tool_and_takes_no_shot() -> None:
    payload = _summary()
    assert payload['task'] == 'week33_kendall_null_tool'
    assert int(payload['ledger']['main_scoreboard_shots_this_week']) == 0
    assert int(payload['ledger']['cumulative_main_scoreboard_attempts_after']) == 19


def test_mahonian_counts_are_a_probability_distribution() -> None:
    for n in range(2, 13):
        counts = tool.mahonian_counts(n)
        assert len(counts) == n * (n - 1) // 2 + 1
        assert all(isinstance(value, int) for value in counts)
        assert sum(counts) == math.factorial(n)


def test_tau_of_inversions_matches_the_kendall_identity() -> None:
    for n in (5, 7, 12):
        assert tool.tau_from_inversions(0, n) == 1.0
        assert abs(tool.tau_from_inversions(n * (n - 1) // 2, n) + 1.0) < 1e-15
        assert abs(tool.tau_from_inversions(1, n) - (1.0 - 4.0 / (n * (n - 1)))) < 1e-15


def test_exact_sd_matches_the_closed_formula() -> None:
    for n in range(5, 13):
        expected = math.sqrt(2.0 * (2 * n + 5) / (9.0 * n * (n - 1)))
        assert abs(tool.exact_sd(n) - expected) < 1e-15


def test_upper_tail_p_values_are_exact_rationals() -> None:
    assert tool.p_upper(7, 0.90) == Fraction(1, 720)
    assert tool.p_upper(5, 1.0) == Fraction(1, 120)
    assert tool.p_upper(5, 0.8) == Fraction(5, 120)
    assert tool.p_upper(7, 0.90) <= tool.p_upper(7, 0.80)


def test_critical_tau_is_the_upper_tail_not_the_lower_tail() -> None:
    assert tool.critical_tau(5, 0.05) == 0.8
    assert tool.critical_tau(7, 0.05) > 0.0
    assert abs(tool.critical_tau(7, 0.05) - 0.6190476190476191) < 1e-12
    assert abs(tool.critical_tau(7, 0.01) - 0.8095238095238095) < 1e-12
    assert tool.critical_tau(7, 0.001) == 1.0
    assert math.isnan(tool.critical_tau(5, 0.001))


def test_critical_tau_is_monotone_in_alpha_and_in_n() -> None:
    assert tool.critical_tau(7, 0.01) >= tool.critical_tau(7, 0.05)
    for alpha in (0.05, 0.01):
        values = [tool.critical_tau(n, alpha) for n in range(5, 13)]
        assert all(values[i] >= values[i + 1] - 1e-12 for i in range(len(values) - 1))


def test_three_tool_criteria_all_hold() -> None:
    payload = _summary()
    verdicts = {item['id']: item['verdict'] for item in payload['criteria']}
    assert verdicts == {'H33g': '成立', 'H33h': '成立', 'H33i': '成立'}


def test_anchor_reading_is_reproduced() -> None:
    payload = _summary()
    assert int(payload['anchor']['n']) == 7
    assert abs(float(payload['anchor']['tau']) - 0.90) < 1e-15
    assert abs(float(payload['anchor']['p_upper']) - 1.0 / 720.0) < 1e-15
    assert float(tool.p_upper(7, 0.90)) == float(payload['anchor']['p_upper'])


def test_table_rows_recompute_from_the_functions() -> None:
    rows = _rows(TABLE)
    assert [int(row['n']) for row in rows] == list(tool.N_GRID)
    for row in rows:
        n = int(row['n'])
        sd = tool.exact_sd(n)
        assert abs(float(row['sd_exact']) - sd) < 1e-12
        assert abs(float(row['sd_times_sqrt_n']) - sd * math.sqrt(n)) < 1e-12
        assert abs(float(row['median_tau_step']) - 2.0 / (n * (n - 1))) < 1e-12
        for alpha in tool.ALPHAS:
            key = 'critical_tau_alpha_' + str(alpha).replace('.', '_')
            expected = tool.critical_tau(n, alpha)
            if math.isnan(expected):
                assert math.isnan(float(row[key]))
            else:
                assert abs(float(row[key]) - expected) < 1e-9


def test_scaling_spread_reading_matches_the_stored_table() -> None:
    payload = _summary()
    scales = [row['sd_times_sqrt_n'] for row in payload['table']]
    median = sorted(scales)[len(scales) // 2]
    spread = (max(scales) - min(scales)) / median
    reading = next(item for item in payload['criteria'] if item['id'] == 'H33g')
    assert abs(spread - float(reading['value'])) < 1e-12
    assert spread <= float(reading['threshold'])


def test_budget_rows_come_from_the_w32_channel_table() -> None:
    rank = json.loads(RANK_JSON.read_text(encoding='utf-8'))
    s0 = {row['channel']: float(row['s0_median']) for row in rank['channels']}
    n_pop = {row['channel']: float(row['n_population_median']) for row in rank['channels']}
    rows = _rows(BUDGET)
    assert rows
    for row in rows:
        channel = row['channel']
        assert abs(float(row['s0']) - s0[channel]) < 1e-12
        assert abs(float(row['n_population']) - n_pop[channel]) < 1e-12
        value, reachable = tool.required_n(s0[channel], n_pop[channel], float(row['target']))
        assert abs(float(row['required_n']) - value) < 1e-6
        assert (row['reachable'].strip() == 'True') == reachable


def test_channel_table_covers_the_four_core_channels() -> None:
    payload = _summary()
    assert set(payload['channels']) == CORE_CHANNELS
    for entry in payload['channels'].values():
        assert float(entry['n_population']) > 0.0
        assert 0.0 < float(entry['s0']) < 1.0


def test_summary_pins_the_w32_rank_input_hash() -> None:
    payload = _summary()
    entry = payload['inputs'][0]
    assert entry['path'] == 'probes/artifacts/w32_rank_stability.json'
    assert hashlib.sha256(RANK_JSON.read_bytes()).hexdigest() == entry['sha256']


def test_cli_query_mode_answers_from_the_exact_distribution(capsys) -> None:
    assert tool.main(['--n', '7', '--tau', '0.9', '--json']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert int(payload['n']) == 7
    assert abs(float(payload['p_upper']) - 1.0 / 720.0) < 1e-15
    assert abs(float(payload['critical_tau']['0.05']) - 0.6190476190476191) < 1e-12


def test_cli_channel_query_uses_the_w32_budget(capsys) -> None:
    assert tool.main(['--channel', 'dielectric', '--target', '0.10', '--json']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['budget']['channel'] == 'dielectric'
    assert float(payload['budget']['required_n']) > 0.0
    assert bool(payload['budget']['reachable']) is True


def test_text_artifacts_are_lf_without_bom() -> None:
    for path in (TABLE, BUDGET, SUMMARY, REPORT):
        raw = path.read_bytes()
        assert not raw.startswith(bytes([239, 187, 191])), path.name
        assert bytes([13, 10]) not in raw, path.name
    assert FIGURE.is_file()
    assert FIGURE.stat().st_size > 0


def test_metric_names_still_frozen_at_seven() -> None:
    import dielectric_auc_sidecar as sidecar
    assert len(sidecar.EXPECTED_METRIC_NAMES) == 7
    assert 'auc_gt30' not in sidecar.EXPECTED_METRIC_NAMES