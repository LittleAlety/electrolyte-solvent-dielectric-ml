"""Resume collection, strict validation and descriptive analyses without new submissions."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts/b740_expansion"
BASE = ROOT / "outputs/b740_expansion/dft_expansion"


def verify_and_report():
    tests = [
        "tests/test_b700_orca",
        "tests/test_b710_evidence",
        "tests/test_b720_external",
        "tests/test_b730_mechanism",
        "tests/test_b740_expansion",
        "tests/test_b750_completion",
    ]
    pytest_command = [sys.executable, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider"]
    result = subprocess.run(pytest_command, cwd=ROOT, capture_output=True, text=True, check=False)
    match = re.search(r"(\d+) passed", result.stdout)
    scripts = [
        "collect_remote_orca.py",
        "diagnose_orca_failures.py",
        "validate_new_orca_results.py",
        "run_electronic_transfer.py",
        "run_safe_liquid_ablation.py",
        "reassess_mixture_clusters.py",
        "audit_quadrupole.py",
        "prepare_failed_opt_retries.py",
        "complete_plan.py",
        "build_completion_report.py",
    ]
    ruff_command = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        *[str(SCRIPTS / name) for name in scripts],
        "tests/test_b750_completion",
    ]
    lint = subprocess.run(ruff_command, cwd=ROOT, capture_output=True, text=True, check=False)
    verification = {
        "schema": "b750.verification/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "pytest": {
            "command": pytest_command,
            "exit_code": result.returncode,
            "passed": int(match.group(1)) if match else 0,
            "output": result.stdout,
            "stderr": result.stderr,
        },
        "ruff": {
            "command": ruff_command,
            "exit_code": lint.returncode,
            "status": "PASSED" if lint.returncode == 0 else "FAILED",
            "output": lint.stdout,
            "stderr": lint.stderr,
        },
    }
    output = ROOT / "outputs/b750_completion"
    output.mkdir(parents=True, exist_ok=True)
    (output / "verification.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
    print(result.stdout)
    print(lint.stdout)
    if result.returncode or lint.returncode:
        raise RuntimeError("Completion verification failed; report not rebuilt")
    subprocess.run(
        [sys.executable, str(SCRIPTS / "build_completion_report.py")], cwd=ROOT, check=True
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--key", type=Path)
    parser.add_argument("--known-hosts", type=Path)
    args = parser.parse_args()
    if args.verify_only:
        if args.collect:
            parser.error("--verify-only cannot be combined with --collect")
        verify_and_report()
        return
    if args.collect and (not args.key or not args.known_hosts):
        parser.error("--collect requires --key and --known-hosts")

    def run(name, *parameters):
        subprocess.run(
            [sys.executable, str(SCRIPTS / name), *map(str, parameters)], cwd=ROOT, check=True
        )

    if args.collect:
        run("collect_remote_orca.py", "--key", args.key, "--known-hosts", args.known_hosts)
        receipt = ROOT / "outputs/b750_completion/retry_opt/submission_record.json"
        if receipt.exists():
            record = json.loads(receipt.read_text())
            run(
                "collect_remote_orca.py",
                "--key",
                args.key,
                "--known-hosts",
                args.known_hosts,
                "--remote-dir",
                record["remote_dir"],
                "--output-dir",
                BASE / "results_opt_retry",
            )
    primary = BASE / "results_opt_retry/jobs"
    if primary.is_dir():
        run(
            "validate_new_orca_results.py",
            "--jobs-dir",
            primary,
            "--fallback-jobs-dir",
            BASE / "results_opt/jobs",
        )
    else:
        run("validate_new_orca_results.py")
    run("run_electronic_transfer.py")
    run("run_safe_liquid_ablation.py")
    run("run_safe_liquid_ablation.py", "--include-new")
    run("reassess_mixture_clusters.py")
    verify_and_report()
    status = json.loads((BASE / "results_opt/validation/summary.json").read_text())
    print(
        json.dumps(
            {
                "complete": status["complete"],
                "accepted": status["accepted"],
                "expected": 67,
                "remaining": 67 - status["accepted"],
                "note": "Scientific evidence gaps remain explicit; this command submits no jobs.",
            }
        )
    )


if __name__ == "__main__":
    main()
