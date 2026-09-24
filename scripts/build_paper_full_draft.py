"""Assemble paper/full_draft.md from the five section drafts.

The section files in paper/ are the single source of truth for the manuscript.
paper/full_draft.md is generated from them and must never be edited by hand.

Usage:
    python scripts/build_paper_full_draft.py           # rebuild the draft
    python scripts/build_paper_full_draft.py --check   # fail if it is stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = REPOSITORY_ROOT / "paper"

SECTION_ORDER = (
    "abstract_and_intro.md",
    "methods_data_records.md",
    "technical_validation.md",
    "benchmark_and_figures.md",
    "code_and_data.md",
)
FULL_DRAFT_NAME = "full_draft.md"


def normalize_text(text: str) -> str:
    """Return LF-only text with no byte-order mark and no outer blank lines."""
    text = text.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip("\n")


def render_full_draft(paper_dir: Path = PAPER_DIR) -> str:
    """Return full_draft.md as assembled from the committed section drafts."""
    blocks: list[str] = []
    for name in SECTION_ORDER:
        path = paper_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"missing section draft: {path}")
        blocks.append(normalize_text(path.read_text(encoding="utf-8-sig")))
    return "\n\n".join(blocks) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-dir", type=Path, default=PAPER_DIR)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that full_draft.md matches the sections instead of writing it",
    )
    args = parser.parse_args(argv)

    expected = render_full_draft(args.paper_dir)
    target = args.paper_dir / FULL_DRAFT_NAME

    if args.check:
        if not target.is_file():
            print(f"{target} is missing; run scripts/build_paper_full_draft.py", file=sys.stderr)
            return 1
        actual = target.read_text(encoding="utf-8-sig")
        actual = actual.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
        if actual != expected:
            print(
                f"{target} is stale; run scripts/build_paper_full_draft.py",
                file=sys.stderr,
            )
            return 1
        print(f"{target} is up to date ({len(expected.splitlines())} lines)")
        return 0

    target.write_text(expected, encoding="utf-8", newline="\n")
    line_count = len(expected.splitlines())
    print(f"wrote {target} ({line_count} lines from {len(SECTION_ORDER)} sections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())