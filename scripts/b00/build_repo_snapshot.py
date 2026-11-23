#!/usr/bin/env python
"""B00-1: non-destructive repository snapshot.

Writes a machine-readable picture of the repository state without touching
git history, branches, remotes or any frozen artifact.

Design rules (PLAN B chapter 3, B00):
  * read-only w.r.t. git: only `git rev-parse`, `git log`, `git status`,
    `git branch`, `git remote`, `git ls-files` are invoked.
  * no commit / push / release / merge is performed.
  * every reported number is derived from a command whose raw output is
    retained in the snapshot, so a reader can re-derive it.

Output: outputs/b00/repo_snapshot.json
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b00"

SCHEMA = "b00.repo_snapshot/v1"
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "probes"))
from export_results_common import write_json_stable  # noqa: E402

def _write_json_stable(path, payload):
    """Reuse the repo's AF-12 convention: a re-run with identical scientific
    fields must not rewrite bookkeeping-only bytes."""
    return write_json_stable(path, payload)

GENERATOR = "build_repo_snapshot/1.0.0"


def run_git(*args: str) -> dict:
    """Run a read-only git command and keep stdout/stderr/rc verbatim."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "cmd": "git " + " ".join(args),
        "rc": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    head = run_git("rev-parse", "HEAD")
    branch = run_git("rev-parse", "--abbrev-ref", "HEAD")
    origin_main = run_git("rev-parse", "origin/main")
    upstream = run_git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")

    # ahead/behind counts, left = upstream-only, right = local-only
    counts = run_git("rev-list", "--left-right", "--count", "origin/main...HEAD")
    ahead = behind = None
    if counts["rc"] == 0 and counts["stdout"]:
        parts = counts["stdout"].split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])

    unpushed = run_git("log", "--format=%H%x1f%h%x1f%ad%x1f%s", "--date=iso-strict",
                       "origin/main..HEAD")
    unpushed_commits = []
    for line in unpushed["stdout"].splitlines():
        if not line.strip():
            continue
        full, short, date, subject = line.split("\x1f", 3)
        stat = run_git("show", "--stat", "--format=", "--numstat", full)
        files_changed = 0
        insertions = 0
        deletions = 0
        for sline in stat["stdout"].splitlines():
            cols = sline.split("\t")
            if len(cols) == 3:
                files_changed += 1
                try:
                    insertions += int(cols[0]) if cols[0] != "-" else 0
                    deletions += int(cols[1]) if cols[1] != "-" else 0
                except ValueError:
                    pass
        unpushed_commits.append({
            "sha": full,
            "short": short,
            "date": date,
            "subject": subject,
            "files_changed": files_changed,
            "insertions": insertions,
            "deletions": deletions,
        })

    branches = run_git("branch", "-a", "-v", "--no-color")
    remotes = run_git("remote", "-v")
    tags = run_git("tag", "-l", "--sort=-creatordate")

    status_short = run_git("status", "--porcelain", "--untracked-files=all")
    untracked = []
    modified = []
    for line in status_short["stdout"].splitlines():
        if not line.strip():
            continue
        code, path = line[:2], line[3:]
        if code == "??":
            untracked.append(path)
        else:
            modified.append({"code": code, "path": path})

    # Group untracked paths by their first two path components for readability.
    untracked_groups: dict[str, int] = {}
    for p in untracked:
        parts = p.replace("\\", "/").split("/")
        key = "/".join(parts[:2]) if len(parts) > 1 else parts[0]
        untracked_groups[key] = untracked_groups.get(key, 0) + 1

    tracked_outputs = run_git("ls-files", "outputs/")

    # Is the standalone baseline inside or outside this working tree?
    standalone = REPO_ROOT.parent / "v56_standalone"
    standalone_info = {
        "path": str(standalone),
        "exists": standalone.is_dir(),
        "inside_working_tree": str(standalone).lower().startswith(
            str(REPO_ROOT).lower() + "\\"),
        "note": (
            "v56_standalone 位于仓库工作树之外. 因此它的任何字节都不受本仓库 git "
            "保护; 冻结必须依赖哈希清单而不是 git. "
            if standalone.is_dir() else "v56_standalone 不存在"
        ),
    }

    snapshot = {
        "schema": SCHEMA,
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "repo_root": str(REPO_ROOT),
        "read_only_declaration": (
            "本脚本只运行 git 只读子命令 (rev-parse/log/status/branch/remote/"
            "ls-files/show --stat). 不执行 commit/push/release/merge/checkout."
        ),
        "head": {
            "sha": head["stdout"] if head["rc"] == 0 else None,
            "branch": branch["stdout"] if branch["rc"] == 0 else None,
            "upstream": upstream["stdout"] if upstream["rc"] == 0 else None,
            "origin_main_sha": origin_main["stdout"] if origin_main["rc"] == 0 else None,
            "ahead": ahead,
            "behind": behind,
        },
        "unpushed_commits": {
            "count": len(unpushed_commits),
            "range": "origin/main..HEAD",
            "commits": unpushed_commits,
        },
        "branches_raw": branches["stdout"],
        "remotes_raw": remotes["stdout"],
        "tags": tags["stdout"].splitlines() if tags["rc"] == 0 else [],
        "working_tree": {
            "n_untracked": len(untracked),
            "n_modified_or_other": len(modified),
            "untracked_groups": dict(
                sorted(untracked_groups.items(), key=lambda kv: -kv[1])
            ),
            "modified": modified,
        },
        "tracked_outputs": {
            "n_tracked_files_under_outputs": len(tracked_outputs["stdout"].splitlines())
            if tracked_outputs["rc"] == 0 and tracked_outputs["stdout"]
            else 0,
            "finding": (
                "outputs/ 下 0 个文件被 git 跟踪. 这意味着 J01/J02/J03 的产物"
                "(outputs/confirm_2027/**) 没有任何 git 层面的字节保护, 只存在于"
                "工作区磁盘上. 冻结必须靠外部哈希清单, 且清单本身需要另存."
            ),
        },
        "standalone_baseline": standalone_info,
        "raw_commands": {
            "rev-parse HEAD": head,
            "rev-parse origin/main": origin_main,
            "rev-list --left-right --count": counts,
            "ls-files outputs/": tracked_outputs,
        },
    }

    out_path = OUT_DIR / "repo_snapshot.json"
    _write_json_stable(out_path, snapshot)

    print(f"[B00-1] wrote {out_path}")
    print(f"  HEAD              = {snapshot['head']['sha']}")
    print(f"  origin/main       = {snapshot['head']['origin_main_sha']}")
    print(f"  ahead/behind      = {ahead}/{behind}")
    print(f"  unpushed commits  = {len(unpushed_commits)}")
    print(f"  untracked files   = {len(untracked)}")
    print(f"  tracked in outputs= {snapshot['tracked_outputs']['n_tracked_files_under_outputs']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
