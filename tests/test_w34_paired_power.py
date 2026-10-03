# Guards for the Week 34-B paired-bootstrap resolution audit.
#
# R6 is the only cross-level conclusion in the repository that never had a resolution
# reading: the six parent-paper rungs carry a sigma column and the four channels carry a
# resampling law, but R6 had just two point estimates.  W34-B re-derives the same four
# tau_b values (bit for bit), resamples the 22 paired compounds with a locked seed, and
# reports 95% intervals -- which is what turns "the oxidation axis barely moves" into
# "the oxidation-axis move is not resolvable at n = 22".
#
# The guards pin exactly that:
#
#   * the four reproduction anchors recompute on an independent scipy path;
#   * the bootstrap is exactly the registered size and seed, and its percentiles
#     reproduce the stored interval;
#   * cross-zero is reported as an interval property, not a p-value;
#   * the independent floor comes from the exact null, not from the fitted closed form;
#   * the lane is post hoc and takes no shot.
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from pathlib import Path

from scipy.stats import kendalltau

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w34_paired_power as probe
import w33_kendall_null_tool as nulltool

SUMMARY = ROOT / 'probes' / 'artifacts' / 'w34_paired_power_summary.json'
BOOTSTRAP = ROOT / 'probes' / 'artifacts' / 'w34_paired_power_bootstrap.csv'
TABLE = ROOT / 'probes' / 'artifacts' / 'w34_paired_power_table.csv'
FIGURE = ROOT / 'probes' / 'artifacts' / 'w34_paired_power.png'
REPORT = ROOT / 'reports' / 'w34_paired_power.md'
PREREG = ROOT / 'probes' / 'w34_paired_power_prereg.json'
CROSSCHECK = ROOT / 'probes' / 'artifacts' / 'w24_3_level_crosscheck.csv'

ANCHORS = {'same_ox_gfn2': 0.6969696969696969, 'same_ox_orca': 0.6536796536796536,
           'same_red_gfn2': 0.8354978354978355, 'same_red_orca': -0.6017316017316018}
POINT_MOVES = {'ox': -0.04329004329004327, 'red': -1.4372294372294374}
N_PAIRED = 22


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def _independent_anchors() -> dict:
    """Recompute the four tau_b on a direct scipy path, without the probe helper."""
    def load(path, encoding='utf-8-sig'):
        with path.open(encoding=encoding, newline='') as handle:
            return list(csv.DictReader(handle))
    census = {row['inchikey']: row for row in load(ROOT / 'data' / 'processed' / 'w23_redox_dscf_layer.csv')}
    orca = [row for row in load(ROOT / 'data' / 'processed' / 'w24_2_orca_dft_layer.csv')
            if row['inchikey'] in census
            and row['orca_ip_gas_eV'].strip() and row['orca_ea_gas_eV'].strip()]
    out = {}
    series = {
        'same_ox_gfn2': [(-float(census[row['inchikey']]['gas_neutral_homo_eV']),
                          float(census[row['inchikey']]['ip_gas_eV'])) for row in orca],
        'same_red_gfn2': [(-float(census[row['inchikey']]['gas_neutral_lumo_eV']),
                           float(census[row['inchikey']]['ea_gas_eV'])) for row in orca],
        'same_ox_orca': [(float(row['p0_ox_eV']), float(row['orca_ip_gas_eV'])) for row in orca],
        'same_red_orca': [(float(row['p0_red_eV']), float(row['orca_ea_gas_eV'])) for row in orca],
    }
    for name, pairs in series.items():
        values = [(float(x), float(y)) for x, y in pairs]
        out[name] = float(kendalltau([p[0] for p in values], [p[1] for p in values]).statistic)
    return out


def test_lane_is_post_hoc_and_takes_no_shot() -> None:
    payload = _summary()
    assert payload['task'] == 'week34_paired_power'
    assert int(payload['ledger']['main_scoreboard_shots_this_week']) == 0
    assert int(payload['ledger']['cumulative_main_scoreboard_attempts_after']) == 19


def test_preregistration_is_locked_and_hashed() -> None:
    payload = _summary()
    prereg = payload['preregistration']
    assert prereg['status'] == 'locked_before_run'
    assert int(prereg['revision']) == 1
    assert prereg['path'] == 'probes/w34_paired_power_prereg.json'
    assert hashlib.sha256(PREREG.read_bytes()).hexdigest() == prereg['sha256']
    locked = json.loads(PREREG.read_text(encoding='utf-8'))
    assert int(locked['design']['draws']) == int(payload['method']['draws'])
    assert int(locked['design']['seed']) == int(payload['method']['seed'])


def test_anchors_recompute_on_an_independent_path() -> None:
    measured = _independent_anchors()
    for name, expected in ANCHORS.items():
        assert abs(measured[name] - expected) <= 1e-12, name


def test_full_set_tau_matches_the_probe_and_the_crosscheck_csv() -> None:
    payload = _summary()
    measured = _independent_anchors()
    for name, expected in ANCHORS.items():
        series = {'same_ox_gfn2': 'gfn2_ox', 'same_ox_orca': 'orca_ox',
                  'same_red_gfn2': 'gfn2_red', 'same_red_orca': 'orca_red'}[name]
        assert abs(float(payload['full_set_tau'][series]) - expected) <= 1e-12
        assert abs(float(payload['full_set_tau'][series]) - measured[name]) <= 1e-12
    crosscheck = _rows(CROSSCHECK)[0]
    assert abs(float(crosscheck['same_red_gfn2']) - ANCHORS['same_red_gfn2']) <= 1e-12
    assert abs(float(crosscheck['red_move']) - POINT_MOVES['red']) <= 1e-12


def test_point_moves_reproduce_the_crosscheck_csv() -> None:
    payload = _summary()
    for axis, move in POINT_MOVES.items():
        item = payload['table'][axis]
        assert abs(float(item['delta']) - move) <= 1e-12, axis
        assert abs(float(item['delta']) - (float(item['tau_orca']) - float(item['tau_gfn2']))) <= 1e-12


def test_bootstrap_is_the_registered_size_and_its_percentiles_reproduce_the_interval() -> None:
    payload = _summary()
    draws = int(payload['method']['draws'])
    rows = _rows(BOOTSTRAP)
    assert len(rows) == draws
    assert [int(row['draw']) for row in rows] == list(range(draws))
    ox = sorted(float(row['delta_ox']) for row in rows)
    red = sorted(float(row['delta_red']) for row in rows)
    for axis, values in (('ox', ox), ('red', red)):
        item = payload['table'][axis]
        # percentile with linear interpolation, the same convention numpy uses
        def percentile(sorted_values, q):
            if len(sorted_values) == 1:
                return sorted_values[0]
            position = (len(sorted_values) - 1) * q
            lower = math.floor(position)
            upper = math.ceil(position)
            if lower == upper:
                return sorted_values[int(position)]
            return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (position - lower)
        low = percentile(values, 0.025)
        high = percentile(values, 0.975)
        assert abs(low - float(item['ci_low'])) < 5e-3, axis
        assert abs(high - float(item['ci_high'])) < 5e-3, axis


def test_cross_zero_is_an_interval_property() -> None:
    payload = _summary()
    ox = payload['table']['ox']
    red = payload['table']['red']
    assert bool(ox['crosses_zero']) == (float(ox['ci_low']) <= 0.0 <= float(ox['ci_high']))
    assert bool(red['crosses_zero']) == (float(red['ci_low']) <= 0.0 <= float(red['ci_high']))
    assert ox['crosses_zero'] is True
    assert red['crosses_zero'] is False
    assert float(red['ci_high']) < 0.0
    assert float(ox['half_width']) == (float(ox['ci_high']) - float(ox['ci_low'])) / 2.0


def test_independent_floor_comes_from_the_exact_null() -> None:
    payload = _summary()
    expected = math.sqrt(2.0) * nulltool.exact_sd(N_PAIRED)
    assert abs(float(payload['method']['independent_floor']) - expected) < 1e-12
    assert abs(float(payload['method']['exact_sd_n']) - nulltool.exact_sd(N_PAIRED)) < 1e-12
    ratio = float(payload['table']['ox']['half_width']) / expected
    assert abs(float(payload['method']['half_width_ratio_ox']) - ratio) < 1e-12
    assert ratio < 1.0


def test_gate_overlay_matches_week33() -> None:
    payload = _summary()
    gate = payload['gate']
    assert int(gate['n_paired']) == N_PAIRED
    assert int(gate['gfn2_gas_legal']) == 1
    assert int(gate['orca_gas_legal']) == 0


def test_all_criteria_hold() -> None:
    payload = _summary()
    verdicts = {item['id']: item['verdict'] for item in payload['criteria']}
    assert verdicts == {'H34f': '成立', 'H34g': '成立', 'H34h': '成立',
                        'H34i': '成立', 'H34j': '成立'}


def test_inputs_keep_their_recorded_sha256() -> None:
    for entry in _summary()['inputs']:
        path = ROOT / entry['path']
        assert path.is_file(), entry['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']


def test_text_artifacts_are_lf_without_bom() -> None:
    for path in (SUMMARY, BOOTSTRAP, TABLE, REPORT):
        raw = path.read_bytes()
        assert not raw.startswith(bytes([239, 187, 191])), path.name
        assert bytes([13, 10]) not in raw, path.name
    assert FIGURE.is_file()
    assert FIGURE.stat().st_size > 0


def test_report_states_the_unresolved_reading() -> None:
    text = REPORT.read_text(encoding='utf-8')
    assert '不可分辨' in text or '未检出差异' in text
    assert '跨 0' in text or '跨 0' in text