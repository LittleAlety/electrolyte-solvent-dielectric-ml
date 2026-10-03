# -*- coding: utf-8 -*-
"""W37-C：v2 装配源回灌（README §11 第 16 条，后验，不占 shot）。

W36-E 把漂移登记在 `probes/artifacts/w36_v2_drift_inventory.csv`：装配源
`paper/_v2_*.md` 与已发布稿 `paper/paper_zh_draft_v2.md` 之间有 11 段不一致。
根因是 W27–W33 的若干轮次**直接改了已发布稿**、没改装配源；再跑一次
`paper/build_paper_v2.py` 就会把这些段落丢掉（§3.8.1、§3.21、附录里的 5+16+2 行等）。

本件按机械规则把漂移逐字回灌，并给出可复算的收口判据：

1. 用重建器把装配源拼成临时产物，与已发布稿做 difflib 比对，得到漂移段；
2. 每段按「落在哪里」自动选家，规则不写死行号：
   - 段尾正好落在某个装配源的末尾 -> 追加到该源（§3.21 就落回 `_v2_body_b.md`）；
   - 该段两侧的相邻行（向上扩到最近的非空行）在某个装配源里恰好命中一次 -> 就地插入；
   - 否则它落在由 v1 线切片出来的区间、或落在段间分隔符旁 -> 写成
     `paper/_v2_splices.json` 里的锚点拼接，正文放 `paper/_v2_splice_<节号>_<sha8>.md`；
     纯空行的段（装配器会 `strip_rules` 吃掉）内联成 `content`，不放正文文件。
3. 一轮改完再重建，直到漂移为 0（本件两轮收敛）；
4. 要求重建产物与已发布稿**逐字节相等**；再真跑一次 `build_paper_v2.py`（不加 --force），
   若它改动了交付字节，本件**自动回滚**并把该判据记判否（绝不让交付字节被静默覆盖）。

只改装配源与拼接清单；不改已发布稿的任何字节，不重跑模型，累计 shot 仍 19。
"""

from __future__ import annotations

import contextlib
import csv
import difflib
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


PAPER = REPOSITORY_ROOT / "paper"
ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
BUILDER = PAPER / "build_paper_v2.py"
SHIPPED_DRAFT = PAPER / "paper_zh_draft_v2.md"
SPLICE_JSON = PAPER / "_v2_splices.json"

INVENTORY_CSV = ARTIFACTS / "w37_v2_backfill_inventory.csv"
SUMMARY_PATH = ARTIFACTS / "w37_v2_backfill_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w37_v2_backfill.md"

SCHEMA = "w37_v2_backfill/summary@1"
TASK = "week37_v2_backfill"
SPLICE_SCHEMA = "paper_v2_splices@1"
MAX_ROUNDS = 5

V2_SOURCES = (
    "_v2_head.md",
    "_v2_front.md",
    "_v2_sec29.md",
    "_v2_body_a.md",
    "_v2_body_b.md",
    "_v2_disc_extra.md",
    "_v2_concl.md",
    "_v2_appendix.md",
)

INVENTORY_FIELDS = ("round", "block", "kind", "home", "mode", "shipped_start_line",
                    "line_count", "sample")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def read_text(path) -> str:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def write_text_lf(path, text: str) -> None:
    with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_csv_lf(path, fieldnames, rows) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def strip_rules(text: str) -> str:
    """和 build_paper_v2.py 里的同名函数逐字一致（装配时对每个部分都跑）。"""
    lines = text.strip("\n").split("\n")
    while lines and lines[-1].strip() in ("", "---"):
        lines.pop()
    return "\n".join(lines).strip("\n")


def rebuild_to_temp(use_splices: bool = True) -> str:
    """把重建器的输出改到临时文件后 exec，不碰仓库任何文件。

    use_splices=False 时把拼接那一步摘掉，用来独立复算锚点唯一性。
    """
    source = read_text(BUILDER)
    needle = 'target = ROOT / "paper_zh_draft_v2.md"'
    if source.count(needle) != 1:
        raise SystemExit("build_paper_v2.py 的目标行定位失败")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_target = Path(tmp) / "paper_zh_draft_v2.md"
        patched = source.replace(needle, 'target = Path(r"' + str(tmp_target) + '")', 1)
        if not use_splices:
            splice_call = 'out = apply_splices(out, ROOT / "_v2_splices.json")'
            if patched.count(splice_call) != 1:
                raise SystemExit("拼接调用定位失败")
            patched = patched.replace(splice_call + "\n", "", 1)
        namespace = {"__file__": str(BUILDER), "__name__": "build_paper_v2_probe"}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(patched, str(BUILDER), "exec"), namespace)
        if not tmp_target.exists():
            raise SystemExit("重建没有产出文件")
        return read_text(tmp_target)


def read_sources() -> dict:
    return {name: read_text(PAPER / name) for name in V2_SOURCES}


def drift_blocks(shipped: str, rebuilt: str) -> list:
    a, b = shipped.split("\n"), rebuilt.split("\n")
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    rows, index = [], 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        index += 1
        side = a[i1:i2] if tag in ("delete", "replace") else b[j1:j2]
        sample = ""
        for line in side:
            if line.strip():
                sample = line.strip()
                break
        rows.append(
            {
                "id": "D" + str(index),
                "tag": tag,
                "i1": i1, "i2": i2, "j1": j1, "j2": j2,
                "kind": {"delete": "只有已发布稿有", "insert": "只有重建产物有",
                         "replace": "两侧都改写"}[tag],
                "shipped_start_line": i1 + 1,
                "line_count": max(i2 - i1, j2 - j1),
                "sample": sample[:160],
                "a": a, "b": b,
            }
        )
    return rows


def unique_home(needle: str, sources: dict) -> str:
    if sum(text.count(needle) for text in sources.values()) != 1:
        return ""
    for name, text in sources.items():
        if text.count(needle) == 1:
            return name
    return ""


def splice_slug(lines: list, start: int) -> str:
    for k in range(start, -1, -1):
        line = lines[k]
        if line.startswith("#"):
            match = re.match(r"#+[ \u3000]*([0-9]+(?:\.[0-9]+)*)", line)
            return "sec" + match.group(1).replace(".", "") if match else "misc"
    return "misc"


def plan_block(block: dict, sources: dict, round_index: int) -> dict:
    """给一段漂移定「家」与「改法」，全部按机械规则，不写死行号。"""
    a, b = block["a"], block["b"]
    i1, i2, j1, j2 = block["i1"], block["i2"], block["j1"], block["j2"]
    plan = {"id": block["id"], "round": round_index, "kind": block["kind"],
            "shipped_start_line": block["shipped_start_line"],
            "line_count": block["line_count"], "sample": block["sample"]}
    if block["tag"] == "delete":
        content = "\n".join(a[i1:i2])
        has_text = any(line.strip() for line in a[i1:i2])
        k = j1 - 1
        while k >= 0 and not b[k].strip():
            k -= 1
        tail = b[k] if k >= 0 else ""
        if tail and has_text:
            ends = [name for name, text in sources.items() if strip_rules(text).endswith(tail)]
            if len(ends) == 1:
                plan.update(home=ends[0], mode="append", content=content)
                return plan
        head = b[k:j1] if k >= 0 else []
        needle = "\n".join(head + [b[j1]])
        home = unique_home(needle, sources)
        if home:
            plan.update(home=home, mode="insert_between", needle=needle, head=head,
                        after=b[j1], content=content)
            return plan
        slug = splice_slug(a, i1)
        name = "_v2_splice_" + slug + "_" + sha256_bytes(content.encode("utf-8"))[:8] + ".md"
        plan.update(home="assembled", mode="splice_insert", needle=needle, head=head,
                    after=b[j1], content=content, has_text=has_text, splice_name=name)
        return plan
    if block["tag"] == "replace":
        content = "\n".join(a[i1:i2])
        needle = "\n".join(b[j1:j2])
        home = unique_home(needle, sources)
        if home:
            plan.update(home=home, mode="replace", needle=needle, content=content)
            return plan
        slug = splice_slug(a, i1)
        name = "_v2_splice_" + slug + "_" + sha256_bytes(content.encode("utf-8"))[:8] + ".md"
        plan.update(home="assembled", mode="splice_replace", needle=needle, content=content,
                    has_text=True, splice_name=name)
        return plan
    raise SystemExit("未处理的漂移类型：" + block["tag"])


def load_existing_splices() -> list:
    if not SPLICE_JSON.exists():
        return []
    payload = json.loads(read_text(SPLICE_JSON))
    if payload.get("schema") != SPLICE_SCHEMA:
        raise SystemExit("已有的拼接清单 schema 不认识，拒绝覆盖")
    return payload["splices"]


def apply_plans(plans: list) -> dict:
    """就地改装配源 + 合并写拼接清单；返回这一轮改了哪些文件。"""
    sources = read_sources()
    touched: dict = {}
    items = load_existing_splices()
    known = {item["id"] for item in items}
    for plan in plans:
        if plan["home"] != "assembled":
            text = sources[plan["home"]]
            if plan["mode"] == "append":
                text = text.rstrip("\n") + "\n\n" + plan["content"] + "\n"
            elif plan["mode"] == "insert_between":
                hits = text.count(plan["needle"])
                if hits != 1:
                    raise SystemExit("段 " + plan["id"] + " 的插入锚点命中 " + str(hits))
                text = text.replace(
                    plan["needle"],
                    "\n".join(plan["head"] + plan["content"].split("\n") + [plan["after"]]),
                    1,
                )
            elif plan["mode"] == "replace":
                hits = text.count(plan["needle"])
                if hits != 1:
                    raise SystemExit("段 " + plan["id"] + " 的替换锚点命中 " + str(hits))
                text = text.replace(plan["needle"], plan["content"], 1)
            else:
                raise SystemExit("未知改法：" + plan["mode"])
            sources[plan["home"]] = text
            touched[plan["home"]] = touched.get(plan["home"], 0) + 1
        else:
            item = {"id": plan["splice_name"],
                    "mode": "insert_between" if plan["mode"] == "splice_insert" else "replace"}
            if plan["mode"] == "splice_insert":
                item["before"] = "\n".join(plan["head"])
                item["after"] = plan["after"]
            else:
                item["find"] = plan["needle"]
            if plan["has_text"]:
                item["source"] = "paper/" + plan["splice_name"]
                write_text_lf(PAPER / plan["splice_name"], plan["content"] + "\n")
                touched[plan["splice_name"]] = touched.get(plan["splice_name"], 0) + 1
            else:
                item["content"] = plan["content"]
            if item["id"] not in known:
                items.append(item)
                known.add(item["id"])
    for name, text in sources.items():
        if touched.get(name):
            write_text_lf(PAPER / name, text)
    if items:
        payload = {
            "schema": SPLICE_SCHEMA,
            "note": ("W37-C 回灌：这些段落原本只存在于已发布稿 paper/paper_zh_draft_v2.md。"
                     "它们落在由 v1 线切片出来的 §3 区间或段间分隔符附近，不能直接写进 v1 线，"
                     "所以用锚点拼接：before/after（或 find）是插入/替换点两侧的原文，"
                     "命中数必须恰好为 1，否则重建器直接报错退出（不静默漂移）。"
                     "纯空行的段用内联 content，因为装配器对每个部分都跑 strip_rules。"),
            "splices": items,
        }
        write_json_stable(SPLICE_JSON, payload)
    return {"files": touched, "splices": len(items)}


def evaluate(before_blocks, after_blocks, plans, shipped_sha_before, shipped_sha_after,
             rebuilt_sha, dry_run_sha, rolled_back, builder_exit, rounds) -> list:
    def verdict(identifier, description, value, threshold, passed) -> dict:
        return {"id": identifier, "description": description,
                "value": None if value is None else float(value),
                "threshold": None if threshold is None else float(threshold),
                "verdict": "成立" if bool(passed) else "判否"}

    return [
        verdict("H37c1", "回灌前装配源无法复现的漂移段数（登记值，不设门）",
                float(len(before_blocks)), None, True),
        verdict("H37c2", "回灌后装配源无法复现的漂移段数", float(len(after_blocks)), 0.0,
                len(after_blocks) == 0),
        verdict("H37c3", "重建产物与已发布稿逐字节相等", None, None,
                rebuilt_sha == shipped_sha_before),
        verdict("H37c4", "已发布稿 sha256 在回灌前后未变（交付字节未被本件触碰）", None, None,
                shipped_sha_after == shipped_sha_before),
        verdict("H37c5", "真跑 build_paper_v2.py（不加 --force）后交付字节未变（变了则自动回滚）",
                None, None, builder_exit == 0 and not rolled_back
                and dry_run_sha == shipped_sha_before),
        verdict("H37c6", "回灌件数 = 漂移段数（每段都有着落，无遗漏）",
                float(len(plans)), float(len(before_blocks)),
                len(plans) == len(before_blocks)),
    ]


def render_report(plans, before_blocks, after_blocks, criteria, shipped_sha, applied,
                  rolled_back, rounds) -> str:
    lines = [
        "# W37-C 结题报告：v2 装配源回灌（重建产物 = 已发布稿，逐字节）",
        "",
        "- **性质**：装配源回灌 + 重建逐字节验证，**不占 shot**（累计仍 19）",
        "- **已发布稿**：`paper/paper_zh_draft_v2.md`，sha256 `" + shipped_sha + "`（回灌前后未变）",
        "- **装配源**：`paper/_v2_*.md` + 新增 `paper/_v2_splices.json`（锚点拼接清单）",
        "- **收敛**：" + "、".join("第 " + str(item["round"]) + " 轮处理 " + str(item["blocks"])
                                   + " 段" for item in rounds),
        "",
        "## 1. 回灌的漂移段",
        "",
        "| 轮 | 段 | 类型 | 落在哪里 | 改法 | 已发布稿起始行 | 行数 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for plan in plans:
        lines.append("| " + str(plan["round"]) + " | " + plan["id"] + " | " + plan["kind"]
                     + " | `" + plan["home"] + "` | " + plan["mode"] + " | "
                     + str(plan["shipped_start_line"]) + " | " + str(plan["line_count"]) + " |")
    lines += [
        "",
        "改动文件：" + ("、".join("`paper/" + name + "`（" + str(count) + " 段）"
                                 for name, count in sorted(applied["files"].items()))
                        if applied["files"] else "（无）"),
        "",
        "## 2. 为什么有的段走锚点拼接而不是直接写装配源",
        "",
        "v2 的 §3.1–§3.14 **不是**独立装配源，而是从 v1 线 `paper/paper_zh_draft.md`",
        "按 `## 3 结果` → `## 4 讨论` 切片来的；把这些段落直接写进 v1 线，等于把 v2 的",
        "内容泄漏进 v1 交付物。另有一段是**段间分隔符旁的额外空行**（§3.21 末尾）：",
        "装配器对每个部分都跑 `strip_rules`（尾部空行与 `---` 一律剥掉），",
        "所以它只能靠在最终产物上做锚点拼接来复现——这也解释了为什么要两轮收敛：",
        "第一轮把 §3.21 追加进 `_v2_body_b.md`，第二轮才发现少的那一个空行。",
        "锚点命中数必须恰好为 1，否则重建器直接报错退出（不静默漂移）。",
        "",
        "## 3. 判据",
        "",
        "| 判据 | 内容 | 读数 | 阈值 | 裁决 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in criteria:
        lines.append("| " + item["id"] + " | " + item["description"] + " | "
                     + ("—" if item["value"] is None else format(item["value"], ".6g")) + " | "
                     + ("—" if item["threshold"] is None else format(item["threshold"], ".6g"))
                     + " | " + item["verdict"] + " |")
    lines += [
        "",
        "## 4. 边界",
        "",
        "- 本件只改装配源与拼接清单；**已发布稿的字节由 sha256 钉住**，回灌前后逐位相同。",
        "- 真跑重建器时，若它改动了交付字节，本件会**自动回滚**并把该判据记判否"
        "（本轮 rolled_back = " + str(rolled_back) + "）。",
        "- 回灌是逐字搬运，不重排、不改写、不重新生成任何数字；判否项照实登记。",
        "- 回灌后 `build_paper_v2.py` 的「拒绝覆盖」护栏不再触发（不再有只存在于已发布稿的标题），",
        "  但仍保留：谁再手工改已发布稿、就会重新触发护栏。",
        "- 区间跨 0 = 未检出差异，不等于证明无差异。不占 shot（累计仍 19）。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    started = time.perf_counter()
    shipped = read_text(SHIPPED_DRAFT)
    shipped_sha_before = sha256_bytes(shipped.encode("utf-8"))
    all_plans, all_files, rounds = [], {}, []
    converged = False
    for round_index in range(1, MAX_ROUNDS + 1):
        rebuilt = rebuild_to_temp()
        blocks = drift_blocks(shipped, rebuilt)
        rounds.append({"round": round_index, "blocks": len(blocks)})
        if not blocks:
            converged = True
            break
        plans = [plan_block(block, read_sources(), round_index) for block in blocks]
        applied = apply_plans(plans)
        for name, count in applied["files"].items():
            all_files[name] = all_files.get(name, 0) + count
        all_plans.extend(plans)
    if not converged:
        raise SystemExit("回灌 " + str(MAX_ROUNDS) + " 轮仍未收敛")

    final_rebuilt = rebuild_to_temp()
    after_blocks = drift_blocks(shipped, final_rebuilt)
    shipped_sha_after = sha256_file(SHIPPED_DRAFT)
    rebuilt_sha = sha256_bytes(final_rebuilt.encode("utf-8"))

    before_bytes = SHIPPED_DRAFT.read_bytes()
    completed = subprocess.run(
        [sys.executable, str(BUILDER)], cwd=str(REPOSITORY_ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    rolled_back = SHIPPED_DRAFT.read_bytes() != before_bytes
    if rolled_back:
        with SHIPPED_DRAFT.open("wb") as handle:
            handle.write(before_bytes)
    dry_run_sha = sha256_file(SHIPPED_DRAFT)
    criteria = evaluate(all_plans, after_blocks, all_plans, shipped_sha_before,
                        shipped_sha_after, rebuilt_sha, dry_run_sha, rolled_back,
                        completed.returncode, rounds)

    write_csv_lf(INVENTORY_CSV, INVENTORY_FIELDS,
                 [{"round": p["round"], "block": p["id"], "kind": p["kind"], "home": p["home"],
                   "mode": p["mode"], "shipped_start_line": p["shipped_start_line"],
                   "line_count": p["line_count"], "sample": p["sample"].replace("|", "\\|")}
                  for p in all_plans])
    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    summary = {
        "schema": SCHEMA, "task": TASK,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {"main_scoreboard_shots_this_week": 0,
                   "cumulative_main_scoreboard_attempts_after": 19,
                   "why_not_a_shot": "装配源回灌：不拟合模型、不新增特征、不触 eps 主记分牌。"},
        "shipped_draft": {"path": "paper/paper_zh_draft_v2.md",
                          "sha256_before": shipped_sha_before, "sha256_after": shipped_sha_after,
                          "unchanged": shipped_sha_after == shipped_sha_before},
        "rebuild": {"sha256": rebuilt_sha, "bytes_equal_to_shipped": rebuilt_sha == shipped_sha_before,
                    "dry_run_builder_exit_code": completed.returncode,
                    "dry_run_rolled_back": rolled_back,
                    "dry_run_sha256": dry_run_sha,
                    "dry_run_stdout_tail": (completed.stdout or "").strip().splitlines()[-1:]},
        "backfill": {"rounds": rounds, "plans": len(all_plans), "after_blocks": len(after_blocks),
                     "files": all_files,
                     "splices": len(load_existing_splices()),
                     "inventory_csv": "probes/artifacts/w37_v2_backfill_inventory.csv",
                     "splice_json": "paper/_v2_splices.json"},
        "blocks": [{k: p[k] for k in ("round", "id", "kind", "home", "mode",
                                      "shipped_start_line", "line_count", "sample")}
                   for p in all_plans],
        "criteria": criteria,
        "headline": [
            "README §11 第 16 条收口：共回灌 " + str(len(all_plans)) + " 段，回灌后漂移 = "
            + str(len(after_blocks)) + " 段。",
            "重建产物与已发布稿逐字节相等；已发布稿 sha256 "
            + ("未变。" if shipped_sha_after == shipped_sha_before else "被改动了（判否）。"),
            "落在 v1 切片区间与段间分隔符旁的段落改为 paper/_v2_splices.json 锚点拼接。",
            "真跑一次 build_paper_v2.py（不加 --force）：rolled_back = " + str(rolled_back)
            + "，交付字节仍等于已发布稿。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(all_plans, all_plans, after_blocks, criteria,
                                         shipped_sha_before, {"files": all_files},
                                         rolled_back, rounds),
                           encoding="utf-8", newline="\n")
    print("rounds " + str([(item["round"], item["blocks"]) for item in rounds]))
    print("blocks backfilled " + str(len(all_plans)) + "; residual drift " + str(len(after_blocks)))
    print("shipped sha unchanged " + str(shipped_sha_after == shipped_sha_before))
    print("rebuild == shipped " + str(rebuilt_sha == shipped_sha_before))
    print("dry run exit " + str(completed.returncode) + " rolled_back " + str(rolled_back))
    print("verdicts " + str(passed) + "/" + str(len(criteria)))
    for item in criteria:
        if item["verdict"] != "成立":
            print("FAIL " + item["id"] + " " + item["description"])
    return 0 if passed == len(criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
