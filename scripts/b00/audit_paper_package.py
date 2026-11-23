#!/usr/bin/env python
"""B00-4: audit the v1.3 independent paper package.

PLAN B chapter 2 says the v1.3 package must not be overwritten, and B08 says the
v1.3 paper advances independently. Before anything can be built on it we need to
know exactly which bytes constitute "v1.3", and which paper files on disk are
NOT part of it.

The important structural fact this script establishes: `v1.3` is a **git tag**,
not a directory. So the package is defined by the tree reachable from that tag,
and everything added to paper/ afterwards (the v2/v3 drafts) is post-tag work
that must never be mistaken for the archived package.

Read-only: no paper file is written.

Outputs:
  outputs/b00/paper_v13_inventory.csv
  outputs/b00/paper_v13_inventory.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b00"
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "probes"))
from export_results_common import write_json_stable  # noqa: E402

def _write_json_stable(path, payload):
    """Reuse the repo's AF-12 convention: a re-run with identical scientific
    fields must not rewrite bookkeeping-only bytes."""
    return write_json_stable(path, payload)

GENERATOR = "audit_paper_package/1.0.0"

TAG = "v1.3"


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(REPO_ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def blob_sha(path_in_repo: str) -> str:
    """sha256 of the bytes as stored at TAG (git blob content, not working tree)."""
    proc = subprocess.run(
        ["git", "show", f"{TAG}:{path_in_repo}"], cwd=str(REPO_ROOT),
        capture_output=True,
    )
    if proc.returncode != 0:
        return ""
    return hashlib.sha256(proc.stdout).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tag_sha = git("rev-list", "-n", "1", TAG).strip()
    tag_date = git("log", "-1", "--format=%ad", "--date=iso-strict", TAG).strip()
    tag_subject = git("log", "-1", "--format=%s", TAG).strip()

    # Every file in the tagged tree (the archived package is the whole tree,
    # but paper/ is what the plan names).
    all_tagged = [p for p in git("ls-tree", "-r", "--name-only", TAG).splitlines() if p.strip()]
    paper_tagged = [p for p in all_tagged if p.startswith("paper/")]

    # The data file the release notes pin by digest.
    pinned = {}
    rel_notes = REPO_ROOT / "paper" / "release_notes_v1.3.md"
    if rel_notes.is_file():
        text = rel_notes.read_text(encoding="utf-8", errors="replace")
        for token in text.replace("`", " ").split():
            t = token.strip(".,;()")
            if len(t) == 64 and all(c in "0123456789abcdef" for c in t):
                pinned.setdefault("sha256_tokens_in_release_notes", []).append(t)

    rows = []
    for p in paper_tagged:
        rel = p[len("paper/"):]
        wpath = REPO_ROOT / p
        on_disk = wpath.is_file()
        rows.append({
            "path_in_package": p,
            "filename": rel,
            "in_tag_v13": True,
            "present_in_worktree": on_disk,
            "tag_blob_sha256": blob_sha(p),
            "worktree_sha256": sha256_file(wpath) if on_disk else "",
            "worktree_bytes": wpath.stat().st_size if on_disk else 0,
            "matches_tag": (blob_sha(p) == sha256_file(wpath)) if on_disk else False,
            "package_role": "archived_v13",
        })

    # Paper files on disk that are NOT in the v1.3 tag: post-tag drafts.
    paper_dir = REPO_ROOT / "paper"
    tagged_set = set(paper_tagged)
    extra = []
    if paper_dir.is_dir():
        for wpath in sorted(paper_dir.rglob("*")):
            if not wpath.is_file():
                continue
            rel = wpath.relative_to(REPO_ROOT).as_posix()
            if rel in tagged_set:
                continue
            if "__pycache__" in rel:
                continue
            extra.append({
                "path_in_package": rel,
                "filename": wpath.relative_to(paper_dir).as_posix(),
                "in_tag_v13": False,
                "present_in_worktree": True,
                "tag_blob_sha256": "",
                "worktree_sha256": sha256_file(wpath),
                "worktree_bytes": wpath.stat().st_size,
                "matches_tag": False,
                "package_role": "post_v13_worktree_only",
            })

    all_rows = rows + extra

    csv_path = OUT_DIR / "paper_v13_inventory.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "package_role", "path_in_package", "filename", "in_tag_v13",
            "present_in_worktree", "worktree_bytes", "matches_tag",
            "tag_blob_sha256", "worktree_sha256",
        ])
        w.writeheader()
        for r in all_rows:
            w.writerow(r)

    n_tagged = len(rows)
    n_drift = sum(1 for r in rows if r["present_in_worktree"] and not r["matches_tag"])
    n_missing = sum(1 for r in rows if not r["present_in_worktree"])

    doc = {
        "schema": "b00.paper_v13_inventory/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "package_identity": {
            "kind": "git_tag",
            "tag": TAG,
            "tag_commit": tag_sha,
            "tag_date": tag_date,
            "tag_subject": tag_subject,
            "note": (
                "v1.3 是 git 标签, 不是目录. 因此'v1.3 投稿包'= 该标签可达树中的 "
                "paper/ 文件集合. 之后加到 paper/ 的 v2/v3 草稿不在包内, "
                "任何把它们当包内容的做法都会改变包的身份."
            ),
        },
        "counts": {
            "n_files_in_tagged_tree": len(all_tagged),
            "n_paper_files_in_v13": n_tagged,
            "n_paper_files_worktree_only": len(extra),
            "n_tagged_files_missing_from_worktree": n_missing,
            "n_tagged_files_byte_drifted_in_worktree": n_drift,
        },
        "release_notes_pinned_digests": pinned,
        "tagged_paper_files": rows,
        "worktree_only_paper_files": extra,
        "read_only_declaration": "no paper file written; only git show / read",
    }
    json_path = OUT_DIR / "paper_v13_inventory.json"
    _write_json_stable(json_path, doc)

    print(f"[B00-4] {csv_path}  ({len(all_rows)} rows)")
    print(f"[B00-4] {json_path}")
    print(f"  tag v1.3 -> {tag_sha[:12]} ({tag_date[:10]})")
    print(f"  paper files in v1.3      = {n_tagged}")
    print(f"  paper files worktree-only= {len(extra)}")
    print(f"  tagged missing on disk   = {n_missing}")
    print(f"  tagged byte-drifted      = {n_drift}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
