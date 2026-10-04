# Guards for the Week 44 lane W44-D: the AST static shot / frozen-reading guard.
# It parses every .py under probes/ scripts/ src/ and asserts the frozen registry still carries the
# seven shipped metrics, that no frozen reading ever appears on the left of an assignment, and that
# no exporter flips promoted to True without registering it.
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'probes' / 'artifacts'
SUMMARY = ART / 'w44_static_shot_guard_summary.json'
MANIFEST = ART / 'w44_static_shot_guard_manifest.csv'
REPORT = ROOT / 'reports' / 'w44_static_shot_guard.md'
PROBE = ROOT / 'probes' / 'w44_static_shot_guard.py'
PREREG = ROOT / 'probes' / 'w44_governance_wiring_prereg.json'

CRITERIA_IDS = ['H44d' + str(index) for index in range(1, 9)]
FROZEN_READINGS = [0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
                   0.6216672295270079]
FROZEN_METRIC_NAMES = ['r2', 'mae', 'rmse', 'spearman', 'mae_lt20', 'mae_20_60', 'mae_gt60']
LEGACY = ['probes/dielectric_compound_coverage_curve.py', 'probes/l3_stage1_pilot.py',
          'probes/v032_controlled_comparison.py']


def _summary() -> dict:
    return json.loads(SUMMARY.read_text(encoding='utf-8'))


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_ledger_and_inputs_untouched() -> None:
    payload = _summary()
    assert payload['schema'] == 'w44_static_shot_guard/summary@1'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['inputs_unchanged'] is True
    assert payload['frozen_readings_untouched'] == FROZEN_READINGS


def test_eight_criteria_all_hold() -> None:
    payload = _summary()
    criteria = payload['criteria']
    assert [item['id'] for item in criteria] == CRITERIA_IDS
    assert [item['verdict'] for item in criteria] == ['成立'] * 8
    assert payload['registered_negatives'] == []


def test_scan_scale() -> None:
    payload = _summary()
    assert payload['files_scanned'] >= 200
    assert payload['files_parsed'] == payload['files_scanned']
    assert payload['parse_errors'] == []
    assert payload['ast_nodes'] > 1000000


def test_frozen_registry_is_intact() -> None:
    payload = _summary()
    assert payload['frozen_metric_names'] == FROZEN_METRIC_NAMES
    assert payload['registry_definitions_checked'] == 2
    assert sorted(payload['registry_statuses']) == ['EXPECTED_METRIC_NAMES:frozen', 'METRIC_NAMES:frozen']
    assert payload['metric_name_mutations'] == []
    assert sorted(payload['legacy_local_metric_names']) == sorted(LEGACY)


def test_no_frozen_reading_is_written() -> None:
    payload = _summary()
    assert payload['frozen_reading_writes'] == []
    assert payload['frozen_reading_reads'] >= 4


def test_no_unregistered_promotion() -> None:
    payload = _summary()
    assert payload['promoted_true_rows'] == []
    assert payload['unregistered_promotions'] == []


def test_artifacts_exist_and_are_lf_only() -> None:
    for path in (SUMMARY, MANIFEST, REPORT, PROBE, PREREG):
        assert path.is_file(), path
    for path in (MANIFEST, REPORT, PROBE, PREREG):
        data = _bytes(path)
        assert not data.startswith(b'\xef\xbb\xbf'), path
        assert b'\r\n' not in data, path
    with MANIFEST.open('r', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 200
