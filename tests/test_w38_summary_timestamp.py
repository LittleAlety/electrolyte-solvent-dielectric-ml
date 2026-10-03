# Guards for the Week 38-E lane: a clean re-export must not dirty the worktree.
#
# README section 11 item 19: tracked summaries carry generated_at_utc / elapsed_seconds,
# so re-running a writer rewrote them even when every scientific field was identical -
# which invalidates the worktree_dirty / artifacts_commit coordinates AF-12 uses to
# identify delivered bytes.  write_json_stable keeps the on-disk bytes when only the
# volatile keys differ.  This test is the end-to-end guard: run the Week 37 export probe
# twice and assert the tracked summary still matches HEAD.
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'probes'))

from export_results_common import write_json_stable  # noqa: E402

SUMMARY = ROOT / 'probes' / 'artifacts' / 'w38_summary_timestamp_summary.json'
MIGRATED_PROBE = ROOT / 'probes' / 'w37_gate_admission_export.py'
MIGRATED_ARTIFACT = 'probes/artifacts/w37_gate_admission_export_summary.json'
E2E_RUNS = 2


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(['git', *args], cwd=str(ROOT), capture_output=True,
                          text=True, encoding='utf-8', errors='replace', check=False)


def test_volatile_only_rewrite_keeps_bytes(tmp_path: Path) -> None:
    target = tmp_path / 'summary.json'
    base = {'schema': 'x@1', 'value': 1.0, 'generated_at_utc': '2020-01-01T00:00:00Z',
            'elapsed_seconds': 1.0}
    assert write_json_stable(target, base) == 'written'
    first = target.read_bytes()
    assert write_json_stable(target, {**base, 'generated_at_utc': '2026-10-03T00:00:00Z',
                                      'elapsed_seconds': 9.9}) == 'unchanged'
    assert target.read_bytes() == first


def test_scientific_change_still_rewrites(tmp_path: Path) -> None:
    target = tmp_path / 'summary.json'
    base = {'schema': 'x@1', 'value': 1.0, 'generated_at_utc': '2020-01-01T00:00:00Z',
            'elapsed_seconds': 1.0}
    write_json_stable(target, base)
    assert write_json_stable(target, {**base, 'value': 2.0}) == 'written'
    assert json.loads(target.read_text(encoding='utf-8'))['value'] == 2.0


def test_summary_records_the_inventory_and_the_unit_checks() -> None:
    payload = json.loads(SUMMARY.read_text(encoding='utf-8'))
    assert payload['task'] == 'week38_summary_timestamp'
    assert payload['ledger']['main_scoreboard_shots_this_week'] == 0
    assert payload['ledger']['cumulative_main_scoreboard_attempts_after'] == 19
    assert payload['unit_checks']['volatile_only_keeps_bytes'] is True
    assert payload['unit_checks']['scientific_change_rewrites'] is True
    assert payload['unit_checks']['first_write_writes'] is True
    assert payload['inventory_counts']['total'] >= 1
    assert payload['inventory_counts']['migrated'] >= 1


def test_probe_exposes_six_criteria_and_no_failures() -> None:
    payload = json.loads(SUMMARY.read_text(encoding='utf-8'))
    verdicts = payload['criteria']
    assert [item['id'] for item in verdicts] == ['H38e1', 'H38e2', 'H38e3', 'H38e4',
                                                 'H38e5', 'H38e6']
    assert all(item['verdict'] == '成立' for item in verdicts)
    for item in verdicts:
        assert item['verdict'] in {'成立', '判否', '不可判定'}


def test_rerunning_the_week37_probe_leaves_the_tracked_summary_clean() -> None:
    for _ in range(E2E_RUNS):
        completed = subprocess.run([sys.executable, str(MIGRATED_PROBE)], cwd=str(ROOT),
                                   capture_output=True, text=True, encoding='utf-8',
                                   errors='replace', check=False)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    status = _git('status', '--porcelain', MIGRATED_ARTIFACT).stdout.strip()
    assert status == '', status
    diff = _git('diff', '--exit-code', '--', MIGRATED_ARTIFACT)
    assert diff.returncode == 0, diff.stdout
