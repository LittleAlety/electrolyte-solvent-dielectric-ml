from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _workflow() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_ci_runs_environment_check_in_independent_full_install_job() -> None:
    jobs = _workflow()["jobs"]
    environment_jobs = [
        job
        for job in jobs.values()
        if any(
            "scripts/check_environment.py" in str(step.get("run", ""))
            for step in job.get("steps", [])
        )
    ]

    assert len(environment_jobs) == 1
    environment_job = environment_jobs[0]
    assert "needs" not in environment_job
    assert environment_job["timeout-minutes"] >= 15
    install_commands = [
        str(step.get("run", ""))
        for step in environment_job["steps"]
        if "pip install" in str(step.get("run", ""))
    ]
    assert any('pip install -e ".[dev]"' in command for command in install_commands)


def test_ci_keeps_a_lightweight_lint_and_test_job() -> None:
    jobs = _workflow()["jobs"]

    assert any(
        any("ruff check" in str(step.get("run", "")) for step in job.get("steps", []))
        and any("pytest" in str(step.get("run", "")) for step in job.get("steps", []))
        for job in jobs.values()
    )


def test_ci_runs_dataset_v01_verifier() -> None:
    workflow = _workflow()
    commands = [
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]

    assert any("scripts/verify_dataset_v01.py" in command for command in commands)


def test_ci_runs_dielectric_gpr_verifier() -> None:
    workflow = _workflow()
    commands = [
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]

    assert any(
        "scripts/verify_dielectric_gpr_baseline.py" in command
        for command in commands
    )


def test_ci_runs_dielectric_baseline_diagnostics_verifier() -> None:
    workflow = _workflow()
    commands = [
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]

    assert any(
        "scripts/verify_dielectric_baseline_diagnostics.py" in command
        for command in commands
    )


def test_ci_runs_week3_verifiers() -> None:
    workflow = _workflow()
    commands = [
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]

    assert any("scripts/verify_chodera_crosscheck.py" in command for command in commands)
    assert any(
        "scripts/verify_dielectric_v01_ext.py" in command for command in commands
    )
    assert any(
        "scripts/verify_dielectric_kernel_comparison.py" in command
        for command in commands
    )
