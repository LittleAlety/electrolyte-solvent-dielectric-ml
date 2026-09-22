"""Verify SHA256SUMS manifests for the real Week 1 and Week 2 exports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.exporting import verify_export_manifest

DEFAULT_OUTPUT_DIRS = (
    Path(r"E:\Claude Code\电解质ML\成果输出\week1"),
    Path(r"E:\Claude Code\电解质ML\成果输出\week2"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        action="append",
        default=[],
        help="Export directory to verify. May be repeated.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    output_dirs = args.output_dir or list(DEFAULT_OUTPUT_DIRS)
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
