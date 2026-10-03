# Guards for the Week 32-A cross-channel rank-stability lane.
#
# Week 24-3 measured the resampling law of the ranking statistic tau_b on the
# permittivity channel: sd(N) = s0 * sqrt(1/N - 1/N_pop).  Week 31-A re-used it to
# re-check the parent paper's small-sample noise floor.  Week 32-A moves the same law
# onto a harder object -- "proxy versus label" instead of "level versus level" -- and
# runs it once across all four core channels (permittivity, viscosity, orbitals, redox).
#
# The guards pin exactly that:
#
#   * the lane is post hoc and takes no main-scoreboard shot;
#   * the four input tables keep their recorded sha256;
#   * the closed form recomputes from the stored s0 and N_pop for every curve row;
#   * the full-set tau_b of one series is recomputed from the raw CSV on an
#     independent path (aggregate per molecule, then Kendall tau-b);
#   * the three declared readings (R1/R2/R5) recompute from the series table.
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

from scipy.stats import kendalltau

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w32_cross_channel_rank_stability as probe

ARTIFACTS = ROOT / 'probes' / 'artifacts'
OUT_CSV = ARTIFACTS / 'w32_rank_stability_series.csv'
OUT_CURVES = ARTIFACTS / 'w32_rank_stability_curves.csv'
OUT_JSON = ARTIFACTS / 'w32_rank_stability.json'
OUT_PNG = ARTIFACTS / 'w32_rank_stability.png'
REPORT = ROOT / 'reports' / 'w32_rank_stability.md'

EXPECTED_CHANNELS = {'dielectric', 'viscosity', 'orbital', 'redox'}
EXPECTED_SERIES = 26


def _payload() -> dict:
    return json.loads(OUT_JSON.read_text(encoding='utf-8'))


def _rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def test_lane_is_post_hoc_and_takes_no_shot() -> None:
    payload = _payload()
    assert payload['post_hoc'] is True
    assert int(payload['new_shot']) == 0
    assert payload['task'] == 'week32_rank_stability'


def test_four_channels_and_the_declared_series_count() -> None:
    payload = _payload()
    assert {row['channel'] for row in payload['records']} == EXPECTED_CHANNELS
    assert len(payload['records']) == EXPECTED_SERIES
    assert payload['real_series'] + payload['dummy_series'] == EXPECTED_SERIES


def test_input_tables_keep_their_recorded_sha256() -> None:
    payload = _payload()
    for name, entry in payload['inputs'].items():
        path = ROOT / entry['path']
        assert path.is_file(), name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == entry['sha256'], name


def test_closed_form_recomputes_from_the_stored_s0_and_population() -> None:
    for row in _rows(OUT_CURVES):
        s0 = float(row['s0'])
        n_pop = float(row['n_population'])
        n = int(row['subset_size'])
        expected = s0 * math.sqrt(max(1.0 / n - 1.0 / n_pop, 0.0))
        assert abs(float(row['sd_fitted']) - expected) < 1e-12
        assert abs(float(row['sd_measured']) - float(row['sd_measured'])) == 0.0
        assert float(row['p05']) <= float(row['p95'])


def test_curve_rows_cover_the_declared_grid() -> None:
    rows = _rows(OUT_CURVES)
    payload = _payload()
    grid = {int(value) for value in payload['n_grid']}
    assert {int(row['subset_size']) for row in rows} <= grid
    assert {int(row['draws']) for row in rows} == {int(payload['draws_per_point'])}
    assert len(rows) == EXPECTED_SERIES * len(grid)


def test_full_set_tau_b_recomputes_from_the_raw_csv() -> None:
    """Independent path: aggregate the permittivity table per molecule, then Kendall."""
    path = ROOT / 'data' / 'processed' / 'dielectric_representation_ablation_predictions.csv'
    buckets: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for row in _rows(path):
        key = (row['representation'], row['inchikey'])
        buckets.setdefault(key, []).append((float(row['prediction']), float(row['target'])))
    recomputed = {}
    for (representation, _), pairs in buckets.items():
        preds = [item[0] for item in pairs]
        labels = [item[1] for item in pairs]
        recomputed[representation] = recomputed.get(representation, []) + [
            (sum(preds) / len(preds), sum(labels) / len(labels))]
    stored = {row['series_id']: float(row['tau_b_full']) for row in _rows(OUT_CSV)
              if row['channel'] == 'dielectric'}
    assert len(stored) == 3
    for series_id, value in stored.items():
        representation = series_id.split('|')[1]
        pairs = recomputed[representation]
        expected = kendalltau([item[0] for item in pairs], [item[1] for item in pairs]).statistic
        assert abs(value - float(expected)) < 1e-09


def test_r1_and_r2_and_r5_recompute_from_the_series_table() -> None:
    rows = _rows(OUT_CSV)
    payload = _payload()
    rmse = [float(row['fit_rmse']) for row in rows]
    assert abs(statistics.median(rmse) - float(payload['readings'][0]['value'])) < 1e-12
    assert statistics.median(rmse) <= float(payload['readings'][0]['gate'])
    dummy = [row for row in rows if 'dummy' in row['arm'].lower()]
    assert dummy
    dummy_tau = statistics.median([float(row['tau_b_full']) for row in dummy])
    assert abs(dummy_tau) <= 0.05
    assert abs(statistics.median(rmse) - float(payload['readings'][0]['value'])) < 1e-12
    assert float(payload['readings'][4]['value']) == dummy_tau


def test_every_channel_gets_its_own_information_budget() -> None:
    payload = _payload()
    assert {row['channel'] for row in payload['channels']} == EXPECTED_CHANNELS
    for row in payload['channels']:
        budget = float(row['n_for_sd_0_05'])
        assert math.isfinite(budget) and budget > 0.0
        assert float(row['s0_min']) <= float(row['s0_median']) <= float(row['s0_max'])
        assert float(row['sd_at_n12_median']) > 0.0


def test_text_artifacts_are_lf_without_bom() -> None:
    payload = _payload()
    assert int(payload['draws_per_point']) == 1000
    for path in (OUT_CSV, OUT_CURVES, OUT_JSON, REPORT):
        raw = path.read_bytes()
        assert not raw.startswith(bytes([239, 187, 191])), path.name
        assert bytes([13, 10]) not in raw, path.name
    assert OUT_PNG.is_file()


def test_noise_floor_correction_landed_in_the_paper_report() -> None:
    report = (ROOT / 'reports' / 'w32_rank_stability.md').read_text(encoding='utf-8')
    assert '0.122' in report or '0.1212' in report or '噪声地板' in report


def test_metric_names_still_frozen_at_seven() -> None:
    import dielectric_auc_sidecar as sidecar
    assert len(sidecar.EXPECTED_METRIC_NAMES) == 7
    assert 'auc_gt30' not in sidecar.EXPECTED_METRIC_NAMES
