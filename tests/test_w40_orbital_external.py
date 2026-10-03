# Guards for the Week 40 D lane: QM9 as a standing orbital external-control layer,
# plus the PubChemQC single-file feasibility assessment.
#
# W40-D is a post hoc lane.  It fits nothing and takes no main-scoreboard shot (the
# cumulative ledger stays at 19).  Its job is to make three things re-runnable:
#   1. the orbital control layer is pinned (103 / 241; Spearman 0.8856, Kendall 0.7114),
#   2. the two levels are provably NOT interchangeable (median |delta| 2.577 eV,
#      102 / 103 hits at >= 1 eV) and a linear calibration only removes ~36.8% of it,
#   3. the PubChemQC route is registered as blocked (H40d8) with the honest nuance
#      that the smallest shard is 536,126,834 B (< 1 GiB), so the blocker is
#      locatability (no CID index, PubChem unreachable), not single-file size.
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w40_orbital_external_summary.json'
CONTROL = ROOT / 'probes' / 'artifacts' / 'w40_orbital_external_control.csv'
CHANNELS = ROOT / 'probes' / 'artifacts' / 'w40_orbital_channels_update.csv'
CHANNELS_IN = ROOT / 'probes' / 'artifacts' / 'w38_recon_channels.csv'
FIGURE = ROOT / 'probes' / 'artifacts' / 'w40_orbital_external.png'
REPORT = ROOT / 'reports' / 'w40_orbital_external.md'
ROSTER = ROOT / 'data' / 'processed' / 'dielectric_physical_features_v03.csv'
QM9 = ROOT / 'data' / 'external' / 'qm9_dataset.csv'

ROSTER_SHA256 = 'b36d3439560e4381b7779565b9950eed379832e832b72ea6a3a010662ed24fa3'
QM9_SHA256 = '01d196218c78a0e29575ef8cf9ceb6d2f33fda9cddc3e4b5bd133e191fa2e053'
HARTREE_TO_EV = 27.211386245988

CRITERIA_IDS = ['H40d1', 'H40d2', 'H40d3', 'H40d4', 'H40d5', 'H40d6', 'H40d7',
                'H40d8', 'H40d9', 'H40d10']
REGISTERED_NEGATIVES = ['H40d8']
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]

MIN_SHARD_BYTES = 536126834
MIN_SHARD_PATH = 'data/b3lyp_pm6_chon500nosalt/train/121433757-121494125.json'


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _rows() -> list:
    with CONTROL.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def _channel_rows() -> list:
    with CHANNELS.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['task'] == 'week40_orbital_external'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_ten_criteria_with_the_pubchemqc_block_registered_as_negative() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    verdicts = {item['id']: item['verdict'] for item in criteria}
    assert [key for key, value in verdicts.items() if value != '成立'] == REGISTERED_NEGATIVES
    assert verdicts['H40d8'] == '判否'


def test_roster_denominator_and_hit_width() -> None:
    payload = _summary()
    assert payload['roster_total'] == 241
    assert payload['n_hits'] == 103


def test_qm9_layer_is_pinned_with_the_hartree_unit_declared() -> None:
    layer = _summary()['external_layer']
    assert layer['name'] == 'QM9'
    assert layer['file'] == 'data/external/qm9_dataset.csv'
    assert layer['sha256'] == QM9_SHA256
    assert layer['rows'] == 133885
    assert 'B3LYP' in layer['level_of_theory']
    assert 'CC BY 4.0' in layer['license']
    assert 'Hartree' in layer['unit']
    assert '27.211386245988' in layer['unit']
    assert layer['not_used_as'].startswith('外部对照层')
    assert layer['columns_used'] == ['inchi', 'homo', 'lumo', 'gap']
    assert sha256_file(QM9) == QM9_SHA256
    assert sha256_file(ROSTER) == ROSTER_SHA256


def test_orbital_ordering_readings_are_frozen() -> None:
    ordering = _summary()['orbital_ordering']
    assert ordering['spearman'] == pytest.approx(0.8856281475401158, rel=1e-12)
    assert ordering['kendall'] == pytest.approx(0.7114415223878093, rel=1e-12)
    assert ordering['pearson'] == pytest.approx(0.8409443563052813, rel=1e-9)
    assert ordering['median_ratio_xtb_over_qm9'] == 0.7057566422677529
    assert ordering['spearman'] >= 0.70
    assert ordering['kendall'] >= 0.50
    assert ordering['median_ratio_xtb_over_qm9'] < 1.0


def test_gap_delta_proves_the_two_levels_are_not_interchangeable() -> None:
    delta = _summary()['gap_delta']
    assert delta['raw_mae_ev'] == pytest.approx(2.5329444893682322, rel=1e-9)
    assert delta['median_abs_delta_ev'] == 2.577389731918365
    assert delta['median_abs_delta_ev'] >= 1.0
    assert delta['n_abs_delta_ge_1ev'] == 102
    assert delta['frac_abs_delta_ge_1ev'] == pytest.approx(102 / 103, rel=1e-12)


def test_calibration_reproduces_w39_and_is_only_a_partial_fix() -> None:
    calibration = _summary()['calibration']
    assert calibration['matches_w39'] is True
    assert calibration['slope'] == pytest.approx(2.0266971543817958, rel=1e-12)
    assert calibration['intercept'] == pytest.approx(-8.872894552951406, rel=1e-9)
    assert calibration['in_sample_mae_ev'] == pytest.approx(1.575506335932728, rel=1e-9)
    assert calibration['loo_mae_ev'] == pytest.approx(1.601998190723187, rel=1e-9)
    assert calibration['loo_reduction'] == pytest.approx(0.3675352154587652, rel=1e-9)
    # A partial fix only: the calibration must not look like it solves the hierarchy gap.
    assert calibration['in_sample_reduction'] < 0.5
    assert calibration['loo_reduction'] < 0.5
    assert calibration['loo_reduction'] >= 1.0 / 3.0
    assert calibration['loo_mae_ev'] < _summary()['gap_delta']['raw_mae_ev']


def test_pubchemqc_recon_is_registered_with_the_smallest_shard_and_reasons() -> None:
    block = _summary()['pubchemqc_recon']
    assert block['evaluated'] is True
    assert block['roster_level_download_feasible'] is False
    assert block['min_shard_bytes'] == MIN_SHARD_BYTES
    assert block['min_shard_path'] == MIN_SHARD_PATH
    assert block['min_shard_cid_range'] == [121433757, 121494125]
    assert block['min_shard_under_1gib'] is True
    assert block['min_shard_bytes'] < (1 << 30)
    assert len(block['blocked_reasons']) >= 3
    assert any('PubChem' in reason for reason in block['blocked_reasons'])
    assert any('parquet' in reason for reason in block['blocked_reasons'])
    assert len(block['census']) == 9
    b3lyp_totals = [item['total_bytes'] for item in block['census']
                    if item['dataset'].endswith('pubchemqc-b3lyp')]
    assert sum(b3lyp_totals) == 7669431815893
    assert 'PubChem' in block['minimal_viable_alternative']


def test_channels_update_adds_w40_columns_to_the_pubchemqc_rows() -> None:
    with CHANNELS_IN.open('r', encoding='utf-8', newline='') as handle:
        before = list(csv.DictReader(handle))
    rows = _channel_rows()
    assert len(rows) == len(before)
    assert {row['channel_key'] for row in rows} == {row['channel_key'] for row in before}
    target = {row['channel_key']: row for row in rows
              if row['channel_key'] in ('molssiai_pubchemqc_b3lyp', 'molssiai_pubchemqc_pm6')}
    assert len(target) == 2
    for key, row in target.items():
        assert row['w40_verdict'] == '受阻（名册级）'
        assert int(row['min_shard_bytes']) > 0
        assert '索引' in row['w40_note'] or 'PubChem' in row['w40_note']
    assert int(target['molssiai_pubchemqc_b3lyp']['min_shard_bytes']) == MIN_SHARD_BYTES
    assert int(target['molssiai_pubchemqc_pm6']['min_shard_bytes']) == 1498874351
    others = [row for row in rows if row['channel_key'] not in target]
    assert all(row['w40_verdict'] == '' for row in others)


def test_control_rows_convert_hartree_to_ev_and_cover_every_hit() -> None:
    rows = _rows()
    assert len(rows) == 103
    assert all(len(row['inchikey']) == 27 for row in rows)
    for row in rows:
        homo_ha = float(row['qm9_homo_ha'])
        lumo_ha = float(row['qm9_lumo_ha'])
        gap_ev = float(row['qm9_gap_ev'])
        assert float(row['qm9_homo_ev']) == pytest.approx(homo_ha * HARTREE_TO_EV, rel=1e-12)
        assert float(row['qm9_lumo_ev']) == pytest.approx(lumo_ha * HARTREE_TO_EV, rel=1e-12)
        # gap = lumo - homo in Hartree; the stored digits round to <= 0.003 eV.
        assert gap_ev == pytest.approx((lumo_ha - homo_ha) * HARTREE_TO_EV, abs=3e-3)
        xtb_gap = float(row['xTB_gap_ev'])
        assert float(row['delta_gap_ev']) == pytest.approx(gap_ev - xtb_gap, rel=1e-12)
        assert float(row['abs_delta_gap_ev']) == pytest.approx(abs(gap_ev - xtb_gap), rel=1e-12)
    assert sum(1 for row in rows if float(row['abs_delta_gap_ev']) >= 1.0) == 102
    assert all(float(row['xTB_gap_ev']) > 0.0 for row in rows)


def test_probe_writes_its_summary_with_the_stable_writer() -> None:
    """AF-12 family: a replay must not dirty the tracked summary via its timestamps."""

    source = (ROOT / 'probes' / 'w40_orbital_external.py').read_text(encoding='utf-8')
    assert 'write_json_stable(SUMMARY_PATH, summary)' in source
    assert 'SUMMARY_PATH.write_text' not in source


def test_report_declares_the_control_layer_scope_and_cites_w39() -> None:
    text = REPORT.read_text(encoding='utf-8')
    assert '口径声明' in text
    assert '不得直接互换' in text
    assert 'Hartree' in text
    assert '103 / 241' in text
    assert 'H40d8' in text and '受阻' in text
    assert '1 GiB' in text
    assert 'PubChemQC' in text
    # W39 conclusions are cited, never re-claimed as new findings here.
    assert 'W39' in text and '只引用' in text
    assert '刚性 vs 柔性' in text


def test_figure_exists() -> None:
    assert FIGURE.is_file() and FIGURE.stat().st_size > 0
