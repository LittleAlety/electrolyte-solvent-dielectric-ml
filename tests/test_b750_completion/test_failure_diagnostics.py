"""Check claims against the retained remote evidence, without network access."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def audit():
    return json.loads(
        (ROOT / "outputs/b750_completion/failure_diagnostics/failure_diagnostics.json").read_text(
            encoding="utf-8"
        )
    )


def test_each_geometry_failure_has_explicit_step_limit_evidence():
    failed = [r for r in audit()["rows"] if r["diagnosis"] == "GEOMETRY_NOT_CONVERGED_NORMAL_EXIT"]
    assert len(failed) == 21
    for row in failed:
        assert row["normal"] and not row["optimization_converged"]
        assert row["last_geometry_cycle"] == max(50, 3 * row["n_atoms"])
        assert any("maximum number" in e["text"] for e in row["evidence"])


def test_unstarted_jobs_are_distinct_from_interrupted_output():
    rows = audit()["rows"]
    not_started = [r for r in rows if r["diagnosis"] == "NOT_STARTED_NO_OUTPUT"]
    interrupted = [r for r in rows if r["diagnosis"] == "INTERRUPTED_OUTPUT"]
    assert len(not_started) == 7 and all(
        not r["output_exists"] and r["array_task"] == 1 for r in not_started
    )
    assert (
        len(interrupted) == 1 and interrupted[0]["output_exists"] and not interrupted[0]["normal"]
    )


def test_full_denominator_and_retry_outcome_are_not_hidden():
    rows = audit()["rows"]
    assert len(rows) == len({r["inchikey"] for r in rows}) == 67
    assert sum(r["latest_status"] == "ACCEPTED" for r in rows) == 38
    assert sum(r["retried"] and r["latest_status"] == "ACCEPTED" for r in rows) == 5
    assert sum(r["latest_status"] != "ACCEPTED" for r in rows) == 29
