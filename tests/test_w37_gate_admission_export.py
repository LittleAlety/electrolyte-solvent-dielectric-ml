# Guards for the Week 37-B lane: redox admission wired into the export chain.
#
# Week 36-D built the admission list but nothing failed at export time if a reduction-axis
# citation went unregistered.  Week 37-B adds scripts/check_redox_admission.py (a mechanical
# checker over the paper appendix index) and wires it into tests/test_repo_hygiene.py, which
# every weekly exporter already names in its VERIFIERS tuple.
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / 'scripts' / 'check_redox_admission.py'
PROBE = ROOT / 'probes' / 'w37_gate_admission_export.py'
SITES = ROOT / 'probes' / 'artifacts' / 'w37_gate_admission_export_sites.csv'
SUMMARY = ROOT / 'probes' / 'artifacts' / 'w37_gate_admission_export_summary.json'
REPORT = ROOT / 'reports' / 'w37_gate_admission_export.md'
OXIDATION_MARK = '不适用（门禁只覆盖还原轴）'


def _run(argv: list) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=str(ROOT), capture_output=True, encoding='utf-8')


def test_checker_passes_and_prints_json() -> None:
    completed = _run([sys.executable, str(CHECKER)])
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload['passed'] is True
    assert payload['sites'] >= 6
    assert payload['unregistered'] == []
    assert payload['mark_mismatch'] == []


def test_probe_passes_all_criteria() -> None:
    completed = _run([sys.executable, str(PROBE)])
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(SUMMARY.read_text(encoding='utf-8'))
    assert payload['task'] == 'week37_gate_admission_export'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['promoted'] is False
    verdicts = {item['id']: item['verdict'] for item in payload['criteria']}
    assert set(verdicts) == {'H37b1', 'H37b2', 'H37b3', 'H37b4', 'H37b5'}
    assert all(value == '成立' for value in verdicts.values())
    assert REPORT.is_file() and REPORT.stat().st_size > 0


def test_sites_cover_both_axes_from_the_paper_index() -> None:
    with SITES.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 6
    assert {row['axis'] for row in rows} == {'reduction', 'oxidation'}
    assert all(row['admission'] == '准入' for row in rows)
    assert all(row['mark'] for row in rows)
    reduction = [row for row in rows if row['axis'] == 'reduction']
    assert reduction and all(row['mark'] in {'可宣读', '不可判定'} for row in reduction)
    oxidation = [row for row in rows if row['axis'] == 'oxidation']
    assert oxidation and all(row['mark'] == OXIDATION_MARK for row in oxidation)


def test_negative_control_refuses_a_deregistered_citation() -> None:
    payload = json.loads(SUMMARY.read_text(encoding='utf-8'))
    assert payload['negative_control'] == {
        'intact_copies_exit_zero': 1,
        'deleted_row_exit_nonzero': 1,
        'renamed_key_exit_nonzero': 1,
    }
    assert payload['inputs_unchanged'] is True


def test_w37_artifacts_are_lf_without_bom() -> None:
    for path in (CHECKER, PROBE, SITES, SUMMARY, REPORT):
        raw = path.read_bytes()
        assert raw, path
        assert not raw.startswith(b'\xef\xbb\xbf'), path
        assert b'\r\n' not in raw, path
