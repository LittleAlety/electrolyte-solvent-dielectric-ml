"""Gate the v1.0 release and the submission that follows it.

Zenodo's GitHub integration archives a **GitHub release**, so the DOI cannot
exist before the release is created: the tag/release inevitably precedes the DOI
and the repository gets the DOI in a backfill commit. This gate is therefore
phased instead of pretending the DOI can be known up front.

```
python scripts/check_release_readiness.py                     # pre-release (default)
python scripts/check_release_readiness.py --phase released    # after the DOI backfill
python scripts/check_release_readiness.py --phase submission  # before emailing the journal
```

What each phase enforces:

* every phase - no placeholder survives in a shipped manuscript file
  (`[TODO: ...]`, `[repository]` or `[repository-name]`), the release line names
  v1.0 instead of a candidate, and the repository line is a real GitHub URL;
* pre-release - the DOI line is a real Zenodo DOI **or** an explicit `pending`
  marker, because the release that mints it does not exist yet;
* released - the DOI line is a real Zenodo DOI;
* submission - the released checks plus a cover letter with no `[TODO: ...]`.

It is deliberately *not* part of `verify_paper()`: before the release the pending
DOI is the correct state, so the everyday consistency gate must stay green while
this one is still red. Placeholders written inside inline code spans document the
convention rather than ship a value, so they are ignored.
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
MANUSCRIPT_FILES = (*SECTION_ORDER, "outline.md")

#: The cover letter is not part of the archived release; it is sent with the
#: submission, so its placeholders only matter in the submission phase.
SUBMISSION_FILES = ("cover_letter.md",)

PHASES = ("pre-release", "released", "submission")

PLACEHOLDERS = (
    (re.compile(r"\[TODO:[^\]]*\]"), "unresolved TODO placeholder"),
    (re.compile(r"\[XXXXX\]"), "unresolved Zenodo DOI placeholder"),
    (re.compile(r"\[repository(?:-name)?\]"), "unresolved repository URL placeholder"),
)

INLINE_CODE = re.compile(r"`[^`]*`")

ZENODO_DOI = re.compile(r"https://doi\.org/10\.5281/zenodo\.\d+")
GITHUB_REPOSITORY = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+")
RELEASED_VERSION = re.compile(r"v1\.0\b")
PENDING_DOI = re.compile(r"pending\b", re.IGNORECASE)


def _without_inline_code(line: str) -> str:
    """Drop documented placeholders from a line of prose."""
    return INLINE_CODE.sub("", line)


def _field(text: str, label: str) -> str | None:
    prefix = f"**{label}:**"
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def check_release_readiness(paper_dir: Path = PAPER_DIR, phase: str = "pre-release") -> list[str]:
    if phase not in PHASES:
        raise ValueError(f"unknown phase {phase!r}; expected one of {', '.join(PHASES)}")
    errors: list[str] = []
    names = MANUSCRIPT_FILES + (SUBMISSION_FILES if phase == "submission" else ())
    for name in names:
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
                "code_and_data.md: the release line still calls the release a candidate"
            )
        if not RELEASED_VERSION.match(release):
            errors.append(
                "code_and_data.md: the release line does not start with v1.0 "
                f"(found {release!r})"
            )
        doi = _field(text, "DOI") or ""
        if phase == "pre-release":
            if not (ZENODO_DOI.fullmatch(doi) or PENDING_DOI.match(doi)):
                errors.append(
                    "code_and_data.md: the DOI line must be a real Zenodo DOI or an "
                    f"explicit 'pending' marker (found {doi!r})"
                )
        elif not ZENODO_DOI.fullmatch(doi):
            errors.append("code_and_data.md: the DOI line is not a real Zenodo DOI")
        if not GITHUB_REPOSITORY.fullmatch(_field(text, "Repository") or ""):
            errors.append("code_and_data.md: the repository line is not a real GitHub URL")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-dir", type=Path, default=PAPER_DIR)
    parser.add_argument("--phase", choices=PHASES, default="pre-release")
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args(argv)

    errors = check_release_readiness(args.paper_dir, args.phase)
    if args.json:
        print(json.dumps({"phase": args.phase, "ready": not errors, "errors": errors}, indent=2))
    elif errors:
        print(f"{args.phase}: release is not ready:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print("see paper/submission_checklist.md section C for the required order", file=sys.stderr)
    else:
        print(f"{args.phase}: ready ({'no placeholders' if args.phase != 'pre-release' else 'no placeholders, DOI pending as expected'})")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
