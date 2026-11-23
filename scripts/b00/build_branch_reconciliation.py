#!/usr/bin/env python
"""B00-3: branch inventory and W49 commit reconciliation.

PLAN B B00 requires:
  1. confirm local W49
  2. confirm origin/main is W40
  3. inspect the 5 unpushed commits and their real diffs
  6. do NOT merge branches automatically

This script is strictly read-only against git. It never merges, checks out,
commits, pushes or releases. It answers one question the plan cares about most:
are the 5 unpushed commits a *divergence* from origin/main, or a *fast-forward*
continuation of it? That distinction decides whether "reconciling W49" is a
mechanical push or a real merge decision.

Outputs:
  outputs/b00/branch_inventory.csv
  outputs/b00/w49_commit_reconciliation.md
"""

from __future__ import annotations

import csv
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

GENERATOR = "build_branch_reconciliation/1.0.0"


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(REPO_ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    head_sha = git("rev-parse", "HEAD")
    origin_sha = git("rev-parse", "origin/main")
    merge_base = git("merge-base", "origin/main", "HEAD")

    # Divergence test. If merge-base == origin/main, the local branch is a pure
    # fast-forward ahead of origin: nothing on origin is missing locally.
    is_fast_forward = merge_base == origin_sha
    ahead = int(git("rev-list", "--count", f"origin/main..HEAD"))
    behind = int(git("rev-list", "--count", f"HEAD..origin/main"))

    # Per-commit inventory of the unpushed range.
    fmt = "%H%x1f%h%x1f%ad%x1f%an%x1f%s"
    log = git("log", f"--format={fmt}", "--date=iso-strict", "origin/main..HEAD")
    commits = []
    for line in log.splitlines():
        if not line.strip():
            continue
        full, short, date, author, subject = line.split("\x1f", 4)
        numstat = git("show", "--numstat", "--format=", full)
        files = ins = dels = 0
        for s in numstat.splitlines():
            cols = s.split("\t")
            if len(cols) == 3:
                files += 1
                ins += int(cols[0]) if cols[0].isdigit() else 0
                dels += int(cols[1]) if cols[1].isdigit() else 0
        # Which top-level areas does this commit touch?
        names = git("show", "--name-only", "--format=", full)
        areas: dict[str, int] = {}
        for n in names.splitlines():
            if not n.strip():
                continue
            top = n.replace("\\", "/").split("/")[0]
            areas[top] = areas.get(top, 0) + 1
        commits.append({
            "sha": full, "short": short, "date": date, "author": author,
            "subject": subject, "files_changed": files,
            "insertions": ins, "deletions": dels,
            "top_areas": dict(sorted(areas.items(), key=lambda kv: -kv[1])),
        })

    # Is W49 present locally, and does W40 correspond to origin/main's tip?
    w49_present = any("W49" in c["subject"] for c in commits)
    origin_subject = git("log", "-1", "--format=%s", "origin/main")
    head_subject = git("log", "-1", "--format=%s", "HEAD")

    # Branch inventory: every local + remote ref with its tip.
    branches_raw = git("branch", "-a", "--no-color", "-v")
    inventory = []
    for line in branches_raw.splitlines():
        line = line.strip()
        if not line:
            continue
        current = line.startswith("*")
        if current:
            line = line[1:].strip()
        parts = line.split()
        if len(parts) >= 2:
            inventory.append({
                "ref": parts[0],
                "tip_sha": parts[1],
                "ahead_behind": " ".join(parts[2:-1]) if len(parts) > 3 else "",
                "subject": parts[-1] if len(parts) > 2 else "",
                "is_current": current,
                "kind": "remote" if parts[0].startswith("remotes/") else "local",
            })

    tags_raw = git("tag", "-l", "--sort=-creatordate")
    tag_rows = []
    for t in tags_raw.splitlines():
        if not t.strip():
            continue
        try:
            sha = git("rev-list", "-n", "1", t)
            date = git("log", "-1", "--format=%ad", "--date=short", t)
        except RuntimeError:
            sha, date = "", ""
        tag_rows.append({"tag": t, "sha": sha, "date": date})

    # ---- write CSV inventory ----
    csv_path = OUT_DIR / "branch_inventory.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "kind", "ref", "tip_sha", "is_current", "ahead_behind", "subject",
        ])
        w.writeheader()
        for row in inventory:
            w.writerow({
                "kind": row["kind"], "ref": row["ref"],
                "tip_sha": row["tip_sha"], "is_current": row["is_current"],
                "ahead_behind": row["ahead_behind"], "subject": row["subject"],
            })

    # ---- write reconciliation markdown ----
    md = []
    md.append("# B00 W49 提交对账（w49_commit_reconciliation.md）\n")
    md.append(f"> 生成器 `{GENERATOR}` · {datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}\n")
    md.append("> 本文件只读 git。未执行 commit / push / merge / checkout / release。\n")

    md.append("\n## 一、结论先行\n")
    if is_fast_forward:
        md.append(
            f"**本地 `main` 是 `origin/main` 的纯快进（fast-forward）后继。**\n\n"
            f"- `merge-base(origin/main, HEAD)` = `{merge_base[:12]}`\n"
            f"- `origin/main`                  = `{origin_sha[:12]}`\n"
            f"- 两者相等 ⇒ origin 上没有任何本地缺失的提交（behind = {behind}）。\n\n"
            "因此「对账 W49」在技术上不是一次合并决策，而是一次 **推送决策**。"
            "本计划不授权推送，所以此处只登记状态，不推进。\n"
        )
    else:
        md.append(
            f"**本地与 origin/main 已分叉。** merge-base `{merge_base[:12]}` 不等于 "
            f"origin/main `{origin_sha[:12]}`，behind = {behind}。"
            "合并需要人工决策；本计划禁止自动合并。\n"
        )

    md.append("\n## 二、端点确认\n")
    md.append("| 项 | 值 | 判定 |\n|---|---|---|\n")
    md.append(f"| 本地 HEAD | `{head_sha[:12]}` — {head_subject} | "
              f"{'✅ W49 存在' if w49_present else '⚠️ 未见 W49'} |\n")
    md.append(f"| origin/main | `{origin_sha[:12]}` — {origin_subject} | "
              f"{'✅ W40 一致' if origin_subject.startswith('W40') else '⚠️ 非 W40 开头'} |\n")
    md.append(f"| ahead / behind | {ahead} / {behind} | "
              f"{'✅ 仅领先' if behind == 0 else '⚠️ 已分叉'} |\n")

    md.append("\n## 三、5 个未推送提交的实际差异\n")
    md.append("| # | 短 SHA | 日期 | 主题 | 文件 | +行 | −行 | 主要目录 |\n")
    md.append("|---|---|---|---|---|---|---|---|\n")
    for i, c in enumerate(commits, 1):
        areas = ", ".join(f"`{k}`×{v}" for k, v in list(c["top_areas"].items())[:4])
        md.append(f"| {i} | `{c['short']}` | {c['date'][:10]} | {c['subject'][:60]} | "
                  f"{c['files_changed']} | {c['insertions']} | {c['deletions']} | {areas} |\n")

    tot_files = sum(c["files_changed"] for c in commits)
    tot_ins = sum(c["insertions"] for c in commits)
    tot_del = sum(c["deletions"] for c in commits)
    md.append(f"\n合计：**{tot_files}** 文件、**+{tot_ins}** / **−{tot_del}** 行。\n")

    md.append("\n## 四、分支与标签清单\n")
    md.append("| 类型 | ref | tip | 当前 |\n|---|---|---|---|\n")
    for row in inventory:
        md.append(f"| {row['kind']} | `{row['ref']}` | `{row['tip_sha'][:12]}` | "
                  f"{'是' if row['is_current'] else ''} |\n")
    md.append("\n标签（按创建时间倒序）：\n\n")
    md.append("| 标签 | 提交 | 日期 |\n|---|---|---|\n")
    for t in tag_rows:
        md.append(f"| `{t['tag']}` | `{t['sha'][:12]}` | {t['date']} |\n")

    md.append("\n## 五、与 B00 要求的对应\n")
    md.append("| B00 要求 | 状态 | 依据 |\n|---|---|---|\n")
    md.append(f"| 1. 确认本地 W49 | {'✅' if w49_present else '❌'} | HEAD = `{head_sha[:12]}` |\n")
    md.append(f"| 2. 确认 origin/main 的 W40 | "
              f"{'✅' if origin_subject.startswith('W40') else '❌'} | "
              f"`{origin_sha[:12]}` — {origin_subject[:50]} |\n")
    md.append(f"| 3. 检查 5 个未推送提交及实际差异 | ✅ | 见§三，共 {len(commits)} 条 |\n")
    md.append("| 6. 不自动合并分支 | ✅ | 本脚本无 merge/checkout 调用路径 |\n")
    md.append("| 7. 不 commit / push / release | ✅ | 本脚本无写 git 调用路径 |\n")

    md_path = OUT_DIR / "w49_commit_reconciliation.md"
    md_text = "".join(md)
    # The markdown embeds a generated-at stamp; keep prior bytes when only that
    # line differs so a re-run does not dirty a tracked artifact.
    _prev = md_path.read_text(encoding="utf-8") if md_path.is_file() else None
    def _strip_stamp(t):
        return "\n".join(l for l in t.splitlines()
                         if not l.startswith("> 生成器 `"))
    if _prev is None or _strip_stamp(_prev) != _strip_stamp(md_text):
        md_path.write_text(md_text, encoding="utf-8")

    # Machine-readable companion so later rounds do not re-parse markdown.
    json_path = OUT_DIR / "w49_commit_reconciliation.json"
    _write_json_stable(json_path, {
        "schema": "b00.w49_reconciliation/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "head": {"sha": head_sha, "subject": head_subject},
        "origin_main": {"sha": origin_sha, "subject": origin_subject},
        "merge_base": merge_base,
        "is_fast_forward_of_origin": is_fast_forward,
        "ahead": ahead,
        "behind": behind,
        "w49_present_locally": w49_present,
        "origin_main_is_w40": origin_subject.startswith("W40"),
        "unpushed_commits": commits,
        "totals": {"files": tot_files, "insertions": tot_ins, "deletions": tot_del},
        "branches": inventory,
        "tags": tag_rows,
        "read_only_declaration": "no merge/checkout/commit/push/release performed",
    })

    print(f"[B00-3] {csv_path}  ({len(inventory)} refs)")
    print(f"[B00-3] {md_path}")
    print(f"[B00-3] {json_path}")
    print(f"  fast_forward_of_origin = {is_fast_forward}")
    print(f"  ahead/behind           = {ahead}/{behind}")
    print(f"  W49 local / W40 origin = {w49_present} / {origin_subject.startswith('W40')}")
    print(f"  unpushed commits       = {len(commits)}  (+{tot_ins}/-{tot_del} over {tot_files} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
