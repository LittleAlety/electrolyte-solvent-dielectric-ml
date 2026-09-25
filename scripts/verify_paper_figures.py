"""Verify that every figure the manuscript cites exists and still re-derives.

The paper's figure section names, for each figure, the artifact that holds the
rendered file and a committed command that re-renders it. Nothing else in CI
checks that those paths exist, so a renamed artifact or a deleted script would
leave the manuscript citing a file that is not in the repository.

This verifier

* parses the figure section and requires consecutive numbering from 1;
* pins the expected artifact file of every figure number, so a figure cannot be
  pointed at an unrelated file that merely exists;
* requires each figure to cite at least one generating script and requires every
  cited artifact and script to exist;
* runs the figure probes that support ``--check`` so their committed summaries
  must still match the rosters and the conformal probe summary they draw.

Usage:
    python scripts/verify_paper_figures.py
    python scripts/verify_paper_figures.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

FIGURE_SECTION = REPOSITORY_ROOT / "paper" / "benchmark_and_figures.md"
EXPECTED_FIGURE_COUNT = 6

# Figure number -> the one artifact file that figure is allowed to render.
# Existence alone is too weak a check: an unrelated committed file would pass.
EXPECTED_FIGURE_ARTIFACTS = {
    1: "probes/artifacts/paper_fig1_dataset_growth.png",
    2: "probes/artifacts/v032_ablation.png",
    3: "probes/artifacts/domain_gap_parity.png",
    4: "probes/artifacts/paper_fig4_conformal_strata.png",
    5: "probes/artifacts/v032_target_scaffold.png",
    6: "probes/artifacts/nbs514_alpha_harmonization.png",
}

ARTIFACT_ROOT = "probes/artifacts/"

# Figures rendered by a dedicated probe, which CI re-runs via --check.
PROBE_CHECKS = (
    "probes/paper_figure_dataset_growth.py",
    "probes/paper_figure_conformal_strata.py",
)

ARTIFACT_RE = re.compile(r"Artifact:\s*`([^`]+)`")
SCRIPT_RE = re.compile(r"Script:\s*`python\s+([^\s`]+)")
FIGURE_RE = re.compile(r"^\*\*Figure\s+(\d+)\.", re.MULTILINE)


def parse_figure_section(text: str) -> list[dict]:
    """Return one record per figure in the order the section lists them."""
    matches = list(FIGURE_RE.finditer(text))
    figures = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end():end]
        figures.append(
            {
                "number": int(match.group(1)),
                "artifacts": ARTIFACT_RE.findall(block),
                "scripts": SCRIPT_RE.findall(block),
            }
        )
    return figures


def validate_figures(figures: list[dict], root: Path = REPOSITORY_ROOT) -> list[str]:
    """Return every problem with the parsed figure records; empty means valid."""

    errors: list[str] = []
    if len(figures) != EXPECTED_FIGURE_COUNT:
        errors.append(
            f"the figure section lists {len(figures)} figures, expected {EXPECTED_FIGURE_COUNT}"
        )

    numbers = [figure["number"] for figure in figures]
    if numbers != list(range(1, len(figures) + 1)):
        errors.append(f"figure numbering is {numbers}, expected consecutive from 1")

    for figure in figures:
        number = figure["number"]
        label = f"Figure {number}"
        expected_artifact = EXPECTED_FIGURE_ARTIFACTS.get(number)

        if expected_artifact is None:
            errors.append(f"{label}: no expected artifact is registered for this number")
        elif expected_artifact not in figure["artifacts"]:
            errors.append(
                f"{label}: must cite its registered artifact {expected_artifact}, "
                f"found {figure['artifacts'] or 'none'}"
            )

        if not figure["artifacts"]:
            errors.append(f"{label}: no Artifact path is cited")
        elif len(figure["artifacts"]) != 1:
            errors.append(
                f"{label}: exactly one Artifact path is expected, "
                f"found {len(figure['artifacts'])}"
            )
        for relative in figure["artifacts"]:
            if not relative.startswith(ARTIFACT_ROOT) or not relative.endswith(".png"):
                errors.append(
                    f"{label}: artifact must be a rendered file under {ARTIFACT_ROOT}: {relative}"
                )

        if not figure["scripts"]:
            errors.append(f"{label}: no generating Script command is cited")

        for relative in figure["artifacts"] + figure["scripts"]:
            if not (root / relative).is_file():
                errors.append(f"{label}: cited path does not exist: {relative}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args(argv)

    text = FIGURE_SECTION.read_text(encoding="utf-8-sig")
    figures = parse_figure_section(text)
    errors = validate_figures(figures)

    probe_results = []
    for relative in PROBE_CHECKS:
        completed = subprocess.run(
            [sys.executable, relative, "--check"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        probe_results.append(
            {
                "script": relative,
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
        )
        if completed.returncode != 0:
            errors.append(
                f"{relative} --check failed: "
                f"{(completed.stderr or completed.stdout).strip()}"
            )

    report = {
        "figure_count": len(figures),
        "figures": figures,
        "probe_checks": probe_results,
        "errors": errors,
    }
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
    else:
        for figure in figures:
            print(
                f"  Figure {figure['number']}: "
                + ", ".join(figure["artifacts"] + figure["scripts"])
            )
        for result in probe_results:
            print(f"  {result['script']} --check: {result['stdout']}")
        print(f"PASS: {len(figures)} figures are cited, present and reproducible")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
