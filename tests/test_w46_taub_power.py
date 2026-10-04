# Guards for the Week 46 lane W46-C: the tau_b power toolbox (tools/taub_power.py).
# The tool is read-only; the probe pins its calibration, its pointwise agreement with the W33 exact
# null on n = 7, and the Gate-1 retrospective readings.
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w46_taub_power_summary.json'
TABLE_CSV = ART / 'w46_taub_power_table.csv'
MDE_CSV = ART / 'w46_taub_power_mde.csv'
RETRO_CSV = ART / 'w46_taub_power_retro.csv'
FLOOR_CSV = ART / 'w46_taub_power_floor.csv'
FIGURE = ART / 'w46_taub_power.png'
REPORT = ROOT / 'reports' / 'w46_taub_power.md'
PREREG = ROOT / 'probes' / 'w46_taub_power_prereg.json'
TOOL = ROOT / 'tools' / 'taub_power.py'
PROBE = ROOT / 'probes' / 'w46_taub_power.py'

CRITERIA_IDS = ['H46c' + str(index) for index in range(1, 11)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w46_taub_power/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS
    assert payload['registered_negatives'] == []


def test_ten_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 10


def test_calibration_and_floor_readings() -> None:
    payload = _summary()
    assert abs(payload['w33_check']['max_abs_delta']) <= 1e-12
    assert payload['w33_check']['points_checked'] == 22
    assert abs(payload['gate1']['alpha_effective_discrete'] - 0.034523809523809526) <= 1e-15
    assert abs(payload['gate1']['observed_exact_p_upper'] - 602.0 / 5040.0) <= 1e-15
    assert abs(payload['gate1']['critical_tau_continuous'] - 0.575091575091575) <= 1e-12


def test_retrospective_and_mde_reproducible() -> None:
    payload = _summary()
    retro = {row['tau_true']: row for row in payload['retro_rows']}
    assert abs(retro[0.4]['power_continuous'] - 0.23002645502645513) <= 1e-12
    assert abs(retro[0.6]['power_continuous'] - 0.6298992673992675) <= 1e-12
    assert abs(retro[0.8]['power_continuous'] - 1.0) <= 1e-12
    assert abs(retro[0.8]['prob_clear_threshold'] - 0.0809027777777778) <= 1e-12
    assert retro[0.4]['n_min_for_power'] == 17
    assert retro[0.6]['n_min_for_power'] == 8
    mde7 = [row for row in payload['mde_rows'] if row['n'] == 7][0]
    assert abs(mde7['mde'] - 0.6540558963871848) <= 1e-12


def test_prereg_locked_via_sha256() -> None:
    import hashlib
    payload = _summary()
    digest = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    assert payload['inputs'][str(PREREG)] == digest
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    assert prereg['status'] == 'locked_before_run'
    assert prereg['revision'] >= 2


def test_artifacts_and_figure_exist() -> None:
    for path in (TABLE_CSV, MDE_CSV, RETRO_CSV, FLOOR_CSV):
        assert path.is_file() and path.stat().st_size > 0
    raw = FIGURE.read_bytes()
    assert raw[:8] == PNG_MAGIC and len(raw) > 5000
    assert REPORT.is_file() and REPORT.stat().st_size > 0
    assert TOOL.is_file() and PROBE.is_file()
