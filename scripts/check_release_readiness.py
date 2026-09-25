"""Refuse to ship v1.0 while any placeholder survives in the manuscript.

`paper/submission_checklist.md` requires the Zenodo DOI to be captured *before*
the v1.0 tag: a tag made first produces a release that no DOI points at, and the
manuscript then has to be edited a second time. This gate is the mechanical half
of that rule.

It fails while:

  * a placeholder such as `[TODO: ...]`, `[repository]` or `zenodo.[XXXXX]`
    survives in a shipped manuscript file;
  * the release line still calls the release a candidate instead of v1.0;
  * the DOI line is not a real Zenodo DOI;
  * the repository line is not a real GitHub URL.

It is deliberately *not* part of `verify_paper()`: before the release the
placeholders are correct, so the everyday consistency gate must stay green while
this one stays red. Run it as the last step before `git tag -a v1.0`.
Placeholders written inside inline code spans document the convention rather
than ship a value, so they are ignored.

Usage:
    python scripts/check_release_readiness.py
    python scripts/check_release_readiness.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.build_paper_full_draft import PAPER_DIR, SECTION_ORDER

#: Manuscript files that carry values into the release. `full_draft.md` is
#: generated from the section files, and its staleness is already guarded by
#: `scripts/check_paper_artifact_consistency.py`, so it is not scanned twice.
SHIPPED_FILES = (*SECTION_ORDER, "outline.md", "cover_letter.md")

PLACEHOLDERS = (
    (re.compile(r"\[TODO:[^\]]*\]"), "unresolved TODO placeholder"),
    (re.compile(r"\[XXXXX\]"), "unresolved Zenodo DOI placeholder"),
    (re.compile(r"\[repository(?:-name)?\]"), "unresolved repository URL placeholder"),
)

INLINE_CODE = re.compile(r"`[^`]*`")

ZENODO_DOI = re.compile(r"https://doi\.org/10\.5281/zenodo\.\d+")
GITHUB_REPOSITORY = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+")
RELEASED_VERSION = re.compile(r"v1\.0\b")


def _without_inline_code(line: str) -> str:
    """Drop documented placeholders from a line of prose."""
    return INLINE_CODE.sub("", line)


def _field(text: str, label: str) -> str | None:
    prefix = f"**{label}:**"
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def check_release_readiness(paper_dir: Path = PAPER_DIR) -> list[str]:
    errors: list[str] = []
    for name in SHIPPED_FILES:
        path = paper_dir / name
        if not path.is_file():
            errors.append(f"{name}: missing manuscript file")
            continue
        text = path.read_text(encoding="utf-8-sig")
        for lineno, line in enumerate(text.splitlines(), 1):
            candidate = _without_inline_code(line)
            for pattern, hint in PLACEHOLDERS:
                match = pattern.search(candidate)
                if match:
                    errors.append(f"{name}:{lineno}: {hint} ({match.group(0)})")

    code_and_data = paper_dir / "code_and_data.md"
    if code_and_data.is_file():
        text = code_and_data.read_text(encoding="utf-8-sig")
        release = _field(text, "Release") or ""
        if "candidate" in release.lower():
            errors.append(
                "code_and_data.md: the release line still calls the release a "
                "candidate; the tag exists only after the DOI does"
            )
        if not RELEASED_VERSION.match(release):
            errors.append(
                "code_and_data.md: the release line does not start with v1.0 "
                f"(found {release!r})"
            )
        if not ZENODO_DOI.fullmatch(_field(text, "DOI") or ""):
            errors.append("code_and_data.md: the DOI line is not a real Zenodo DOI")
        if not GITHUB_REPOSITORY.fullmatch(_field(text, "Repository") or ""):
            errors.append("code_and_data.md: the repository line is not a real GitHub URL")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-dir", type=Path, default=PAPER_DIR)
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args(argv)

    errors = check_release_readiness(args.paper_dir)
    if args.json:
        print(json.dumps({"ready": not errors, "errors": errors}, indent=2))
    elif errors:
        print("release is not ready:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print(
            "see paper/submission_checklist.md section C for the required order",
            file=sys.stderr,
        )
    else:
        print("release is ready: no placeholders, v1.0 tagged, real Zenodo DOI")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
