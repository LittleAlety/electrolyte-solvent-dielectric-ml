# Guards for the Week 37-A lane: endpoint equality must go through endpoint_of() + tolerance.
#
# Week 36-A registered "endpoint equality tolerance = 1e-12" as rule R5 on disk, but nothing
# stopped a later author from writing a bitwise endpoint comparison such as
# `if value == 0.5861142332208197:`.  Week 37-A turns that rule into a machine guard: the
# tolerance is read back from the registry R5 row, and an AST scan of the repository flags
# runtime bitwise comparisons against high-precision literals and the four frozen readings.
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'src'))

import w36_endpoint_rule as w36
import w37_endpoint_tolerance_guard as probe

CRITERIA_IDS = ['H37a1', 'H37a2', 'H37a3', 'H37a4', 'H37a5']


def _sites() -> list[dict]:
    with probe.SITES_CSV.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def _summary() -> dict:
    return json.loads(probe.SUMMARY_PATH.read_text(encoding='utf-8'))


def test_registry_r5_tolerance_matches_w36_declaration() -> None:
    assert probe.read_registry_tolerance() == w36.ENDPOINT_TOLERANCE == 1e-12
    assert probe.endpoints_equal(1.0, 1.0 + 1e-13) is True
    assert probe.endpoints_equal(1.0, 1.0 + 1e-9) is False
    assert probe.endpoint_of is w36.endpoint_of


def test_scan_finds_zero_forbidden_sites() -> None:
    scan = probe.scan_repository()
    forbidden = [site for site in scan['sites'] if site['disposition'] == '禁止']
    assert forbidden == []
    assert scan['files_scanned'] > 0
    assert set(scan['root_file_counts']) == set(probe.SCAN_ROOTS)
    assert all(scan['root_file_counts'][root] > 0 for root in probe.SCAN_ROOTS)


def test_synthetic_violation_is_caught() -> None:
    caught = [site for site in probe.scan_source(probe.SYNTHETIC_VIOLATION, '<synthetic_violation>')
              if site['disposition'] == '禁止']
    assert len(caught) >= 1
    assert caught[0]['kind'] == 'frozen_eq'


def test_synthetic_string_violation_is_caught() -> None:
    code = "if name == '0.1111222233334444':\n    pass\n"
    caught = [site for site in probe.scan_source(code, '<synthetic_str>')
              if site['disposition'] == '禁止']
    assert len(caught) == 1
    assert caught[0]['kind'] == 'high_precision_str_eq'


def test_legal_tolerance_usage_is_not_flagged() -> None:
    sites = probe.scan_source(probe.SYNTHETIC_LEGAL, '<synthetic_legal>')
    assert sites == []
    assert [s for s in sites if s['disposition'] == '禁止'] == []


def test_artifacts_are_lf_without_bom_and_parseable() -> None:
    for path in (probe.SITES_CSV, probe.SUMMARY_PATH, probe.REPORT_PATH):
        raw = path.read_bytes()
        assert not raw.startswith(b'\xef\xbb\xbf'), path
        assert b'\r' not in raw, path
        raw.decode('utf-8')
    rows = _sites()
    assert rows and list(rows[0]) == list(probe.SITE_FIELDS)
    for row in rows:
        assert row['disposition'] in ('允许', '禁止')
        if row['disposition'] == '允许':
            assert row['reason'].strip()
    assert '端点判等容差' in probe.REPORT_PATH.read_text(encoding='utf-8')


def test_summary_records_no_shot_and_zero_forbidden() -> None:
    payload = _summary()
    assert payload['task'] == 'week37_endpoint_tolerance_guard'
    assert payload['promoted'] is False
    assert int(payload['ledger']['main_scoreboard_shots_this_week']) == 0
    assert int(payload['ledger']['cumulative_main_scoreboard_attempts_after']) == 19
    assert payload['sites']['forbidden'] == 0
    assert payload['endpoint_tolerance'] == w36.ENDPOINT_TOLERANCE == 1e-12
    assert any('字面量' in boundary for boundary in payload['boundaries'])
    assert [item['id'] for item in payload['criteria']] == CRITERIA_IDS
    assert all(item['verdict'] == '成立' for item in payload['criteria'])
    reuse = payload['reuse_diagnostic']
    assert reuse['available'] is True
    assert reuse['bitwise_equal'] is False
    assert reuse['endpoints_equal'] is True
