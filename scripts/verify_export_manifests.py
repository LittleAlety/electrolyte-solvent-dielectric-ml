"""Verify SHA256SUMS manifests for default or explicitly selected exports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import verify_export_manifest

DEFAULT_OUTPUT_ROOT = REPOSITORY_ROOT.parent / "成果输出"

# The newest week the project has exported.  This used to be a hardcoded
# ``range(1, 11)`` under a docstring that promised "all week output
# directories", so weeks 11-13 (and then 14) were silently skipped by the default run while
# still reporting success.  Bump this when a new week is exported.
LATEST_WEEK = 14
WEEK_DIRECTORIES = tuple(f"week{week}" for week in range(1, LATEST_WEEK + 1))


def default_output_dirs(output_root: Path) -> tuple[Path, ...]:
    """Return every conventional week output directory without requiring them."""

    return tuple(output_root / week for week in WEEK_DIRECTORIES)


def select_output_dirs(
    *,
    output_root: Path,
    explicit_output_dirs: tuple[Path, ...] = (),
    allow_missing: bool = False,
) -> tuple[Path, ...]:
    """Select explicit directories or every conventional week directory."""

    if explicit_output_dirs:
        selected = explicit_output_dirs
    else:
        selected = default_output_dirs(output_root)
    if allow_missing:
        selected = tuple(output_dir for output_dir in selected if output_dir.is_dir())
    if not selected:
        raise ValueError("no output directories selected")
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        action="append",
        default=[],
        help="Export directory to verify. May be repeated.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root containing conventional week1-week{LATEST_WEEK} output directories.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Skip missing selected directories instead of reporting them as errors.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        output_dirs = select_output_dirs(
            output_root=args.output_root,
            explicit_output_dirs=tuple(args.output_dir),
            allow_missing=args.allow_missing,
        )
    except ValueError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "passed": False,
                        "error": str(exc),
                        "results": {},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"[FAIL] {exc}")
        return 2
    results = {
        str(output_dir): verify_export_manifest(output_dir) for output_dir in output_dirs
    }
    if args.json:
        print(
            json.dumps(
                {
                    "passed": all(not errors for errors in results.values()),
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for output_dir, errors in results.items():
            if errors:
                print(f"[FAIL] {output_dir}")
                for error in errors:
                    print(f"  {error}")
            else:
                print(f"[PASS] {output_dir}")
    return 0 if all(not errors for errors in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
