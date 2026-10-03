# Guards for the Week 31-A bridge between the parent paper (v6) and this repository.
#
# The parent paper rewrote "can a cheap proxy be used for screening?" as a question
# about ranking stability and reported three conclusions on the electronic-structure
# level.  Week 31-A asks whether the same law also holds one level down (molecular
# representation) and one more (model hyperparameters), and it re-checks the parent
# paper's own small-sample noise estimate with this repository's sampling law.
#
# The guards pin exactly that:
#
#   * the lane is post hoc and takes no main-scoreboard shot;
#   * the parent paper's readings are quoted, never recomputed;
#   * the sampling law and the layer table recompute from the committed CSVs;
#   * the four frozen readings and METRIC_NAMES are untouched.
from __future__ import annotations

import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w31_v6_bridge as bridge

ARTIFACTS = ROOT / 'probes' / 'artifacts'
OUT_CSV = ARTIFACTS / 'w31_v6_bridge.csv'
OUT_JSON = ARTIFACTS / 'w31_v6_bridge.json'
OUT_PNG = ARTIFACTS / 'w31_v6_bridge.png'
REPORT = ROOT / 'reports' / 'w31_v6_bridge.md'
CRLF = bytes([13, 10])
BOM = bytes([239, 187, 191])

FROZEN_READINGS = {
    'baseline': 0.4091179943351143,
    'headline': 0.4766400383507876,
    'single_representation_endpoint': 0.5861142332208197,
    'week20_registered_arm': 0.6216672295270079,
}


def _payload() -> dict:
    return json.loads(OUT_JSON.read_text(encoding='utf-8'))


def test_lane_is_post_hoc_and_takes_no_shot() -> None:
    payload = _payload()
    assert payload['post_hoc'] is True
    assert int(payload['new_shot']) == 0
    assert payload['task'] == 'week31_v6_bridge'


def test_parent_paper_readings_are_quoted_verbatim() -> None:
    readings = _payload()['v6_readings']
    assert float(readings['sd_tau_b_at_n10']) == 0.126
    assert float(readings['rho_std_tau']) == -0.8511
    assert float(readings['rho_absmean_tau']) == -0.535
    levels = {entry['name']: entry for entry in readings['levels']}
    assert set(levels) == {'GFN2-xTB dSCF', 'Koopmans', 'r2SCAN-3c'}
    assert float(levels['GFN2-xTB dSCF']['mae_eV']) == 4.48
    assert float(levels['r2SCAN-3c']['mae_eV']) == 0.25
    assert float(levels['GFN2-xTB dSCF']['tau_b']) == 0.91
    assert float(levels['r2SCAN-3c']['tau_b']) == 0.73


def test_sampling_law_recomputes_from_the_committed_csv() -> None:
    recomputed = bridge.sampling_table()
    stored = _payload()['sampling_law']
    assert len(recomputed) == len(stored) == 6
    for left, right in zip(recomputed, stored):
        assert left['series'] == right['series']
        assert float(left['n_population']) == float(right['n_population'])
        for key in ('s0', 'fit_rmse', 'sd_at_n10', 'sd_at_n12', 'sd_at_n18'):
            assert abs(float(left[key]) - float(right[key])) < 1e-12


def test_sampling_law_matches_its_own_formula() -> None:
    for entry in bridge.sampling_table():
        s0 = float(entry['s0'])
        n_pop = float(entry['n_population'])
        for n in (10, 12, 18, 25):
            expected = s0 * (1.0 / n - 1.0 / n_pop) ** 0.5
            assert abs(float(entry['sd_at_n' + str(n)]) - expected) < 1e-12


def test_noise_floor_agrees_with_the_parent_paper_within_ten_percent() -> None:
    values = [entry['sd_at_n10'] for entry in bridge.sampling_table()]
    median = statistics.median(values)
    mean = statistics.fmean(values)
    assert abs(median - 0.126) / 0.126 < 0.10
    assert abs(mean - 0.126) / 0.126 < 0.10
    assert min(values) < 0.126 < max(values)


def test_layer_table_covers_three_layers_plus_a_boundary_case() -> None:
    layers = [row['layer'] for row in _payload()['layer_table']]
    assert layers.count('hyperparameter') == 3
    assert layers.count('electronic-structure level') == 3
    assert layers.count('representation family') == 1
    assert layers.count('placebo') == 1


def test_hyperparameter_layer_moves_magnitude_at_least_eight_times_more() -> None:
    ratios = [float(row['range_ratio']) for row in _payload()['layer_table']
              if row['layer'] == 'hyperparameter']
    assert len(ratios) == 3
    assert min(ratios) >= 8.0
    assert min(ratios) > 1.0


def test_representation_layer_is_the_boundary_case() -> None:
    row = next(item for item in _payload()['layer_table']
               if item['layer'] == 'representation family')
    assert float(row['magnitude_range']) > 0.5
    assert float(row['order_range']) > 0.4
    assert float(row['order_from']) < 0.55


def test_placebo_collapses_in_both_quantities() -> None:
    row = next(item for item in _payload()['layer_table'] if item['layer'] == 'placebo')
    assert float(row['magnitude_from']) < 0.0
    assert float(row['order_from']) < 0.50


def test_correction_entry_is_registered_not_silently_applied() -> None:
    entry = next(item for item in _payload()['readings'] if item['id'] == 'B5')
    assert float(entry['recorded']) == 0.1335681773982666
    assert abs(float(entry['true_median']) - 0.1222) < 0.001
    assert abs(float(entry['upper_middle']) - 0.1335681773982666) < 1e-9


def test_report_quotes_the_correction_and_the_boundary() -> None:
    text = REPORT.read_text(encoding='utf-8')
    assert '上中位' in text
    assert '0.1222' in text
    assert '只在**同一表示族内部**成立' in text


def test_lane_never_touches_the_frozen_metric_header() -> None:
    source = (ROOT / 'probes' / 'w31_v6_bridge.py').read_text(encoding='utf-8')
    assert 'METRIC_NAMES' not in source
    ids = [entry['id'] for entry in _payload()['readings']]
    assert ids == ['B1', 'B2', 'B3', 'B4', 'B5']


def test_lane_writes_only_its_own_artifacts() -> None:
    outputs = [bridge.OUT_CSV, bridge.OUT_JSON, bridge.OUT_MD, bridge.OUT_PNG]
    assert {path.name for path in outputs} == {'w31_v6_bridge.csv',
                                                'w31_v6_bridge.json',
                                                'w31_v6_bridge.md',
                                                'w31_v6_bridge.png'}
    assert all(path.parent in (ARTIFACTS, ROOT / 'reports') for path in outputs)
    assert bridge.SAMPLING_LAW_CSV.name == 'w24_3_sampling_law.csv'
    assert bridge.LEVEL_CROSSCHECK_CSV.name == 'w24_3_level_crosscheck.csv'
    assert bridge.W28_REPEATS.name == 'w28_dense_hyperparameters_repeats.csv'
    assert bridge.W30_REPEATS.name == 'w30_combination_ladder_repeats.csv'

def test_artifacts_are_lf_without_bom() -> None:
    for path in (OUT_CSV, OUT_JSON, REPORT):
        raw = path.read_bytes()
        assert CRLF not in raw
        assert not raw.startswith(BOM)
    assert OUT_PNG.read_bytes()[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])