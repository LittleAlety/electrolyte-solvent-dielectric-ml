# Guards for the Week 36-B/C lane: the channel noise floor on the display layer, and the
# multi-fidelity criterion built on it.
#
# Week 32-A measured a noise floor s0 per channel and a minimum information budget; Week
# 34-A pooled them into a dashboard.  Week 36-B hangs that floor beside every
# ``*_repeats.csv`` (without touching a frozen byte), and Week 36-C turns the fidelity gap
# into an explicit selection criterion for low-fidelity proxies.
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w33_kendall_null_tool as null_tool
import w36_channel_noise_floor as probe

FLOOR = ROOT / 'probes' / 'artifacts' / 'w36_channel_noise_floor.csv'
DISPLAY = ROOT / 'probes' / 'artifacts' / 'w36_repeats_display_layer.csv'
DASHBOARD_V2 = ROOT / 'probes' / 'artifacts' / 'w36_channel_dashboard_v2.csv'
CRITERION = ROOT / 'probes' / 'artifacts' / 'w36_fidelity_criterion.csv'
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w36_channel_noise_floor_summary.json'
REPORT = ROOT / 'reports' / 'w36_channel_noise_floor.md'
BUDGET = ROOT / 'probes' / 'artifacts' / 'w33_kendall_null_budget.csv'

S0 = {'dielectric': 0.4737006221811013, 'viscosity': 0.4903265381347203,
      'orbital': 0.5828062566882567, 'redox': 0.3694640022140437}
W32_SPEARMAN = 0.8058119658119658


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_lane_is_post_hoc_and_takes_no_shot() -> None:
    payload = _summary()
    assert payload['task'] == 'week36_channel_noise_floor'
    assert int(payload['ledger']['main_scoreboard_shots_this_week']) == 0
    assert int(payload['ledger']['cumulative_main_scoreboard_attempts_after']) == 19


def test_floor_covers_four_channels_with_the_published_s0() -> None:
    rows = {row['channel']: row for row in _rows(FLOOR)}
    assert set(rows) == set(S0)
    for channel, value in S0.items():
        assert float(rows[channel]['s0']) == value
        assert rows[channel]['display_note']


def test_required_n_matches_the_exact_null_budget() -> None:
    published = {(row['channel'], float(row['target'])): float(row['required_n'])
                 for row in _rows(BUDGET)}
    worst = 0.0
    for row in _rows(FLOOR):
        for target in probe.TARGETS:
            column = 'req_n_dtau_' + format(target, '.2f')
            recomputed = 1.0 / ((target / (null_tool.POWER_FACTOR * float(row['s0']))) ** 2
                                + 1.0 / float(row['n_population']))
            worst = max(worst, abs(recomputed - published[(row['channel'], target)]))
            assert float(row[column]) == published[(row['channel'], target)]
    assert worst <= 1e-9


def test_display_layer_maps_repeats_files_without_touching_them() -> None:
    payload = _summary()
    rows = _rows(DISPLAY)
    mapped = [row for row in rows if row['channel']]
    unmapped = [row for row in rows if not row['channel']]
    assert len(mapped) == payload['display_layer']['mapped']
    assert len(mapped) >= 40
    assert len(unmapped) == payload['display_layer']['unmapped']
    assert all(row['display_note'] == probe.UNMAPPED_NOTE for row in unmapped)
    assert payload['display_layer']['frozen_repeats_intact'] is True
    assert all(row['display_note'] for row in mapped)


def test_dashboard_v2_extends_the_frozen_dashboard() -> None:
    v1 = _rows(ROOT / 'probes' / 'artifacts' / 'w34_channel_dashboard.csv')
    v2 = _rows(DASHBOARD_V2)
    assert [row['channel'] for row in v2] == [row['channel'] for row in v1]
    for before, after in zip(v1, v2):
        assert after['s0'] == before['s0']
        assert after['min_n_for_sd_0_05'] == before['min_n_for_sd_0_05']
        assert float(after['req_n_dtau_0.10']) > 0.0


def test_fidelity_criterion_holds_on_every_channel() -> None:
    payload = _summary()
    law = payload['fidelity_law']
    assert abs(law['spearman'] - W32_SPEARMAN) < 1e-12
    assert law['series'] == 26
    assert 0.0 < law['r2'] < 1.0
    rows = _rows(CRITERION)
    assert len(rows) == 4
    assert all(row['agrees'] == '1' for row in rows)
    errors = [float(row['rel_error']) for row in rows]
    assert statistics.median(errors) <= probe.CRITERION_MEDIAN_REL_ERROR_GATE


def test_eight_criteria_hold_and_the_report_exists() -> None:
    payload = _summary()
    verdicts = {item['id']: item['verdict'] for item in payload['criteria']}
    assert set(verdicts) == {'H36b1', 'H36b2', 'H36b3', 'H36b4',
                             'H36c1', 'H36c2', 'H36c3', 'H36c4'}
    assert all(value == '成立' for value in verdicts.values())
    assert REPORT.is_file() and REPORT.stat().st_size > 0