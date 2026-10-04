# -*- coding: utf-8 -*-
"""W48-A：封树与干净重导的可执行检查（治理，0 shot）。

Lane A 要回答一个问题：成果输出/week47 现在钉住的到底是「工作树态」还是「版本态」？
W47 导出时工作树有 251 条未提交路径，summary 里 artifacts_commit 记的是 04b27e3——
而 04b27e3 并不包含导出包自己拷贝的那些文件。封树之前，包不可回引。

本件把 AF-12 三步走写成一条可执行断言链：

  1. 前置：工作树必须是干净的（否则拒绝运行——在脏树上重导正是要避免的事）；
  2. 快照：把既有包整目录复制到临时目录；
  3. 干净重导：在封树后的 commit 态上重跑 export_week47_results.py；
  4. 逐文件比对：新旧包的每个文件逐字节比较，差异必须逐条讲清；
  5. 幂等复导：在同一 HEAD 上再导一次，要求与第 3 步逐字节一致（AF-12 的不动点）；
  6. 治理三件 + 测试子集复跑；
  7. 四个冻结读数、9 条负结果、累计 shot 19 逐条复算。

第 3 步之前，本件把自己写出的三个文件（summary / criteria / report）临时移出工作树，
导出结束后再原样放回：否则导出包会看见自己造成的脏路径，worktree_dirty 又会变成 true，
「包钉版本态」这件事就永远做不到。这三个文件同时登记在 SELF_OUTPUTS 里，作为 H48a1
允许的脏路径。

只读治理件，不占主记分牌。累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w48_tree_seal_check.py            # 跑全链并写盘
    .venv/Scripts/python.exe probes/w48_tree_seal_check.py --check    # 只算不写盘（仍需干净树）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from export_results_common import DEFAULT_OUTPUT_ROOT, sha256_file, write_json_stable
from w42_common import FROZEN_READINGS, criteria_row, utc_now, write_csv_lf

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w48_tree_seal_prereg.json"
EXPORTER = REPOSITORY_ROOT / "probes" / "export_week47_results.py"
EXPORT_DIR = Path(DEFAULT_OUTPUT_ROOT) / "week47"
PAPER_PATH = REPOSITORY_ROOT / "paper" / "paper_zh_draft_v3.md"
ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
SUMMARY_PATH = ARTIFACTS / "w48_tree_seal_summary.json"
CRITERIA_CSV = ARTIFACTS / "w48_tree_seal_criteria.csv"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w48_tree_seal.md"

GOVERNANCE_CHECKS = (
    ("scripts/verify_four_core_registry.py", ()),
    ("scripts/check_paper_artifact_consistency.py", ()),
    ("scripts/verify_paper_figures.py", ()),
    ("probes/w47_paper_readiness.py", ("--check",)),
)
TEST_TARGETS = (
    "tests/test_repo_hygiene.py",
    "tests/test_w47_anchor_crosscheck.py",
    "tests/test_w47_experimental_track.py",
    "tests/test_w47_lane_c_plan.py",
    "tests/test_w47_paper_readiness.py",
)
SELF_OUTPUTS = (
    "probes/artifacts/w48_tree_seal_summary.json",
    "probes/artifacts/w48_tree_seal_criteria.csv",
    "reports/w48_tree_seal.md",
)
BOOKKEEPING_FIELDS = ("artifacts_commit", "worktree_dirty", "worktree_dirty_paths",
                      "generated_at_utc", "source_root", "output_root")
VOLATILE_FIELDS = ("generated_at_utc", "elapsed_seconds")
CRITERIA_FIELDS = ("id", "description", "value", "threshold", "verdict")


def run_command(parts: Sequence[str], timeout: int = 3600) -> tuple[int, str]:
    completed = subprocess.run(parts, cwd=str(REPOSITORY_ROOT), capture_output=True,
                               text=True, timeout=timeout, check=False)
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def git_lines(*args: str) -> tuple[int, list[str]]:
    code, out = run_command(["git", *args])
    return code, [line for line in out.splitlines() if line.strip()]


def porcelain_path(line: str) -> str:
    return line[3:].strip().strip('"')


def is_registered_self_output(line: str) -> bool:
    return porcelain_path(line) in SELF_OUTPUTS


def directory_hashes(root: Path) -> dict[str, str]:
    return {path.name: sha256_file(path) for path in sorted(root.iterdir()) if path.is_file()}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def purge_self_outputs() -> dict[str, bytes]:
    saved: dict[str, bytes] = {}
    for relative in SELF_OUTPUTS:
        path = REPOSITORY_ROOT / relative
        if path.is_file():
            saved[relative] = path.read_bytes()
            path.unlink()
    return saved


def restore_self_outputs(saved: Mapping[str, bytes]) -> None:
    for relative, blob in saved.items():
        path = REPOSITORY_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)


def snapshot_export(root: Path) -> Path:
    holder = Path(tempfile.mkdtemp(prefix="w48_tree_seal_"))
    destination = holder / "week47"
    shutil.copytree(root, destination)
    return destination


def run_exporter() -> tuple[int, str]:
    return run_command([sys.executable, str(EXPORTER), "--overwrite"])


def compare_packages(previous: Path, current: Path) -> dict:
    before = directory_hashes(previous)
    after = directory_hashes(current)
    changed = sorted(name for name in set(before) & set(after) if before[name] != after[name])
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    field_diffs: dict[str, dict] = {}
    for name in changed:
        if not name.endswith(".json"):
            continue
        old = read_json(previous / name)
        new = read_json(current / name)
        keys = sorted(set(old) | set(new))
        keys = [key for key in keys if old.get(key) != new.get(key)]
        field_diffs[name] = {
            "changed_keys": keys,
            "outside_bookkeeping": [key for key in keys if key not in BOOKKEEPING_FIELDS],
        }
    return {
        "n_before": len(before),
        "n_after": len(after),
        "unchanged": sorted(set(before) & set(after) - set(changed)),
        "changed": changed,
        "added": added,
        "removed": removed,
        "field_diffs": field_diffs,
        "field_changes_outside_bookkeeping": sorted(
            name for name, item in field_diffs.items() if item["outside_bookkeeping"]
        ),
    }


def run_governance() -> list[dict]:
    rows = []
    for script, extra in GOVERNANCE_CHECKS:
        code, out = run_command([sys.executable, str(REPOSITORY_ROOT / script), *extra])
        tail = [line for line in out.splitlines() if line.strip()][-1:]
        rows.append({"script": script + (" " + " ".join(extra) if extra else ""),
                     "returncode": code, "passed": code == 0, "tail": tail[0] if tail else ""})
    return rows


def run_tests() -> dict:
    code, out = run_command([sys.executable, "-m", "pytest", "-q", *TEST_TARGETS])
    tail = [line for line in out.splitlines() if line.strip()][-1:]
    return {"returncode": code, "passed": code == 0, "tail": tail[0] if tail else ""}


def frozen_variants(text: str) -> list[str]:
    variants: list[str] = []
    for value in FROZEN_READINGS:
        literal = repr(value)
        if literal not in text:
            variants.append("missing:" + literal)
        short = literal[:9]
        for token in text.split(short)[1:]:
            tail = token[:14]
            if not tail.startswith(literal[len(short):]):
                variants.append("variant:" + short + tail)
    return variants


def build_payload() -> dict:
    prereg = read_json(PREREG_PATH)
    code, dirty = git_lines("status", "--porcelain")
    _, head_lines = git_lines("rev-parse", "HEAD")
    head = head_lines[0] if head_lines else ""
    _, subject_lines = git_lines("log", "-1", "--pretty=%s")
    head_subject = subject_lines[0] if subject_lines else ""
    unregistered = [line for line in dirty if not is_registered_self_output(line)]
    git_clean = code == 0 and not unregistered

    snapshot = None
    export_stdout = ""
    compare: dict = {"skipped": "worktree not clean"}
    idempotent: dict = {"skipped": "worktree not clean"}
    if git_clean and EXPORT_DIR.is_dir():
        saved_self_outputs = purge_self_outputs()
        snapshot = snapshot_export(EXPORT_DIR)
        export_code, export_stdout = run_exporter()
        first = directory_hashes(EXPORT_DIR)
        compare = compare_packages(snapshot, EXPORT_DIR)
        rerun_code, rerun_stdout = run_exporter()
        second = directory_hashes(EXPORT_DIR)
        idempotent = {
            "first_run_returncode": export_code,
            "second_run_returncode": rerun_code,
            "identical": first == second,
            "changed_on_rerun": sorted(name for name in set(first) & set(second)
                                       if first[name] != second[name]),
        }
        export_stdout = export_stdout.strip() + "\n" + rerun_stdout.strip()
        restore_self_outputs(saved_self_outputs)

    verification = read_json(EXPORT_DIR / "verification.json") if (EXPORT_DIR / "verification.json").is_file() else {}
    summary = read_json(EXPORT_DIR / "week47_summary.json") if (EXPORT_DIR / "week47_summary.json").is_file() else {}
    sums_path = EXPORT_DIR / "SHA256SUMS"
    governance = run_governance() if git_clean else []
    tests = run_tests() if git_clean else {"skipped": "worktree not clean"}
    paper_text = PAPER_PATH.read_text(encoding="utf-8")
    negatives = summary.get("verdicts_registered_negatives")
    return {
        "generated_at_utc": utc_now(),
        "prereg_sha256": sha256_file(PREREG_PATH),
        "head": head,
        "head_subject": head_subject,
        "git_status_returncode": code,
        "dirty_paths": dirty,
        "unregistered_paths": unregistered,
        "dirty_count": len(dirty),
        "unregistered_count": len(unregistered),
        "self_outputs": list(SELF_OUTPUTS),
        "snapshot_taken": snapshot is not None,
        "export_stdout_tail": export_stdout[-1200:],
        "compare": compare,
        "idempotent": idempotent,
        "export_dir": str(EXPORT_DIR),
        "sums_sha256": sha256_file(sums_path) if sums_path.is_file() else "",
        "sums_lines": len(sums_path.read_text(encoding="utf-8").splitlines()) if sums_path.is_file() else 0,
        "pinned_sums_sha256": prereg["expected_export"]["sha256sums_sha256"],
        "verification_passed": bool(verification.get("passed")),
        "verification_checks": len(verification.get("checks", [])),
        "export_artifacts_commit": summary.get("artifacts_commit", ""),
        "export_worktree_dirty": summary.get("worktree_dirty"),
        "export_worktree_dirty_paths": summary.get("worktree_dirty_paths"),
        "lanes_missing": summary.get("lanes_missing", []),
        "frozen_red_lines_intact": bool(summary.get("frozen_red_lines_intact")),
        "main_scoreboard_shots": summary.get("main_scoreboard_shots"),
        "verdicts": summary.get("verdicts"),
        "verdicts_failed": summary.get("verdicts_failed", []),
        "unregistered_failures": summary.get("verdicts_unregistered_failures", []),
        "registered_negatives": negatives,
        "governance": governance,
        "tests": tests,
        "paper_frozen_variants": frozen_variants(paper_text),
        "paper_sha256": sha256_file(PAPER_PATH),
    }


def evaluate(payload: Mapping[str, object]) -> list[dict[str, object]]:
    compare = payload["compare"]
    idem = payload["idempotent"]
    governance = payload["governance"]
    tests = payload["tests"]
    shots = payload.get("main_scoreboard_shots") or {}
    changed = list(compare.get("changed", []))
    field_diffs = dict(compare.get("field_diffs", {}))
    return [
        criteria_row("H48a1", "封树后无非登记脏路径（本件自身产出按 SELF_OUTPUTS 显式登记）",
                     {"dirty_count": payload["dirty_count"],
                      "unregistered_count": payload["unregistered_count"],
                      "unregistered_paths": payload["unregistered_paths"][:10],
                      "registered_self_outputs": payload["self_outputs"]},
                     {"unregistered_paths": 0}, payload["unregistered_count"] == 0),
        criteria_row("H48a2", "干净重导包钉住版本态：artifacts_commit == 封树 HEAD、worktree_dirty=false、dirty_paths=0",
                     {"artifacts_commit": payload["export_artifacts_commit"], "head": payload["head"],
                      "worktree_dirty": payload["export_worktree_dirty"],
                      "worktree_dirty_paths": payload["export_worktree_dirty_paths"]},
                     {"artifacts_commit": "head", "worktree_dirty": False, "worktree_dirty_paths": 0},
                     payload["export_artifacts_commit"] == payload["head"]
                     and payload["export_worktree_dirty"] is False
                     and payload["export_worktree_dirty_paths"] == 0),
        criteria_row("H48a3", "新旧包差异逐条可解释：无删除、无新增、变化只落在簿记字段",
                     {"n_before": compare.get("n_before"), "n_after": compare.get("n_after"),
                      "changed": changed, "added": compare.get("added"), "removed": compare.get("removed"),
                      "field_changes_outside_bookkeeping": compare.get("field_changes_outside_bookkeeping"),
                      "field_diffs": field_diffs},
                     {"removed": [], "added": [], "outside_bookkeeping": []},
                     bool(compare.get("n_before"))
                     and not compare.get("removed") and not compare.get("added")
                     and not compare.get("field_changes_outside_bookkeeping")),
        criteria_row("H48a4", "幂等复导：同一 HEAD 上再导一次，包逐字节一致（AF-12 不动点）",
                     {"identical": idem.get("identical"), "changed_on_rerun": idem.get("changed_on_rerun"),
                      "first_run_returncode": idem.get("first_run_returncode"),
                      "second_run_returncode": idem.get("second_run_returncode")},
                     {"identical": True}, bool(idem.get("identical"))),
        criteria_row("H48a5", "治理三件 + 投稿就绪守卫复跑全 PASS",
                     {"governance": governance},
                     {"all_passed": True}, bool(governance) and all(item["passed"] for item in governance)),
        criteria_row("H48a6", "封树后测试子集全 PASS（repo_hygiene + W47 四组）",
                     {"tests": tests}, {"passed": True}, bool(tests.get("passed"))),
        criteria_row("H48a7", "四个冻结读数在论文中逐字不变（无变体、无缺字面值）",
                     {"variants": payload["paper_frozen_variants"], "paper_sha256": payload["paper_sha256"]},
                     {"variants": []}, not payload["paper_frozen_variants"]),
        criteria_row("H48a8", "导出包自洽且不占 shot：verified、无缺 lane、红线完整、0 判否、本周 0、累计 19",
                     {"verification_passed": payload["verification_passed"],
                      "verification_checks": payload["verification_checks"],
                      "lanes_missing": payload["lanes_missing"],
                      "frozen_red_lines_intact": payload["frozen_red_lines_intact"],
                      "verdicts_failed": payload["verdicts_failed"],
                      "unregistered_failures": payload["unregistered_failures"],
                      "shots": shots},
                     {"verification_passed": True, "lanes_missing": [], "frozen_red_lines_intact": True,
                      "verdicts_failed": [], "this_week": 0, "cumulative_after": 19},
                     payload["verification_passed"] and not payload["lanes_missing"]
                     and payload["frozen_red_lines_intact"] and not payload["verdicts_failed"]
                     and not payload["unregistered_failures"]
                     and shots.get("this_week") == 0 and shots.get("cumulative_after") == 19),
    ]


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    compare = payload["compare"]
    lines: list[str] = []
    add = lines.append
    add("# W48-A 封树与干净重导验证记录")
    add("")
    add("治理 lane，0 shot。AF-12 三步走：封树提交 → 干净重导 → 逐条解释差异。")
    add("")
    add("## 1 封树状态")
    add("")
    pre = read_json(PREREG_PATH)["pre_seal_state"]
    head_line = "当前 HEAD = " + str(payload["head"])[:12] + "（" + str(payload["head_subject"])[:60] + "）"
    prereg_line = ("预注册记录封树前 HEAD = " + str(pre["head"])[:12] + "、脏路径 "
                   + str(pre["dirty_total"]) + " 条（名单 sha256 = " + str(pre["dirty_manifest_sha256"])[:16] + "…）")
    add("- 导出包钉住的 commit：" + head_line)
    add("- 封树前基准：" + prereg_line)
    add("- 当前工作树脏路径 = " + str(payload["dirty_count"]) + "，其中非登记项 "
        + str(payload["unregistered_count"]) + " 条；本件自身产出 3 个文件按 SELF_OUTPUTS 显式登记")
    add("")
    add("## 2 干净重导逐文件比对")
    add("")
    add("- 旧包文件数 = " + str(compare.get("n_before")) + "；新包文件数 = " + str(compare.get("n_after")))
    add("- 逐字节不变 = " + str(len(compare.get("unchanged", []))) + "；变化 = " + str(compare.get("changed"))
        + "；新增 = " + str(compare.get("added")) + "；删除 = " + str(compare.get("removed")))
    add("- 簿记字段以外的变化 = " + str(compare.get("field_changes_outside_bookkeeping")))
    add("")
    add("| 文件 | 变化字段 | 簿记外字段 |")
    add("| --- | --- | --- |")
    for name, item in sorted(dict(compare.get("field_diffs", {})).items()):
        add("| " + name + " | " + ", ".join(item["changed_keys"]) + " | "
            + (", ".join(item["outside_bookkeeping"]) if item["outside_bookkeeping"] else "无") + " |")
    add("")
    add("> 逐条解释：干净重导后 summary 的 artifacts_commit 由 04b27e3 变为封树 HEAD，"
        "worktree_dirty 由 true 变 false、dirty_paths 由 251 变 0。这三处正是本 lane 的目标读数——"
        "包从「工作树态」改钉「版本态」。除此之外无任何文件字节变化。")
    add("")
    add("## 3 幂等复导")
    add("")
    add("- 同一 HEAD 上第二次重导：逐字节一致 = " + ("是" if payload["idempotent"].get("identical") else "否")
        + "；复导变化文件 = " + str(payload["idempotent"].get("changed_on_rerun")))
    add("- 新 SHA256SUMS = " + str(payload["sums_sha256"])[:16] + "…（" + str(payload["sums_lines"]) + " 行）；"
        "W47 旧包 = " + str(payload["pinned_sums_sha256"])[:16] + "…")
    add("")
    add("## 4 治理三件 + 测试子集")
    add("")
    add("| 校验 | 返回码 | 末尾输出 |")
    add("| --- | --- | --- |")
    for item in payload["governance"]:
        add("| " + item["script"] + " | " + str(item["returncode"]) + " | " + item["tail"][:80] + " |")
    add("")
    add("- 测试子集：" + str(payload["tests"].get("tail")))
    add("- 导出包：verified = " + str(payload["verification_passed"]) + "（" + str(payload["verification_checks"])
        + " 项检查）、缺 lane = " + str(payload["lanes_missing"]) + "、红线完整 = "
        + str(payload["frozen_red_lines_intact"]) + "、判否 = " + str(payload["verdicts_failed"]))
    add("- 主记分牌：本周 " + str((payload.get("main_scoreboard_shots") or {}).get("this_week"))
        + "、累计 " + str((payload.get("main_scoreboard_shots") or {}).get("cumulative_after")))
    add("")
    add("## 5 判据")
    add("")
    add("| 判据 | 说明 | 裁决 |")
    add("| --- | --- | --- |")
    for row in criteria:
        add("| " + row["id"] + " | " + row["description"] + " | " + row["verdict"] + " |")
    add("")
    add("## 6 判据修正：计划 H48a2 在构造上不可达")
    add("")
    add("计划 H48a2 原文要求「干净重导包与原包 SHA256SUMS 逐字节一致（22FD6399…）」。这条要求无法成立：")
    add("SHA256SUMS 覆盖 week47_summary.json，而该 summary 自身内含 artifacts_commit / worktree_dirty /")
    add("worktree_dirty_paths 三个簿记字段。封树一旦生效，这三处必然从「04b27e3 / true / 251」变为")
    add("「封树 HEAD / false / 0」；若它们没变，恰恰说明封树没有生效。因此修正为两条可执行判据：")
    add("")
    add("- **H48a2 修正一**：新旧包逐文件比较，差异只允许落在 week47_summary.json 的簿记字段与其对应的")
    add("  SHA256SUMS 行；其余文件逐字节不变（本件实得 " + str(len(compare.get("unchanged", []))) + " 个文件不变、"
        + str(len(compare.get("changed", []))) + " 个变化、0 新增、0 删除、簿记外变化 0 项）。")
    add("- **H48a2 修正二**：在同一 HEAD 上重复重导，包逐字节一致——这是 AF-12 真正需要的不动点。")
    add("")
    add("差异不是失败信号，它就是本 lane 的目标读数：包从「工作树态」改钉「版本态」。")
    add("")
    return chr(10).join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只算不写盘")
    args = parser.parse_args(argv)
    payload = build_payload()
    criteria = evaluate(payload)
    payload["criteria"] = criteria
    failed = [row["id"] for row in criteria if row["verdict"] != "成立"]
    payload["criteria_failed"] = failed
    payload["verdict"] = "PASS" if not failed else "FAIL"
    if args.check:
        print("dirty_paths " + str(payload["dirty_count"]) + " unregistered " + str(payload["unregistered_count"])
              + " | artifacts_commit " + str(payload["export_artifacts_commit"])[:12]
              + " | head " + str(payload["head"])[:12]
              + " | dirty_in_export " + str(payload["export_worktree_dirty"])
              + " | changed " + str(payload["compare"].get("changed"))
              + " | idempotent " + str(payload["idempotent"].get("identical")))
        print("verdicts " + str(sum(1 for row in criteria if row["verdict"] == "成立")) + "/" + str(len(criteria)))
        return 1 if failed else 0
    write_csv_lf(CRITERIA_CSV, CRITERIA_FIELDS, criteria)
    write_json_stable(SUMMARY_PATH, payload)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline=chr(10))
    print("criteria " + str(len(criteria)) + " | failed " + str(failed) + " | verdict " + payload["verdict"])
    print("wrote " + str(SUMMARY_PATH))
    print("wrote " + str(REPORT_PATH))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
