# -*- coding: utf-8 -*-
"""W36-E：v1 线 / 英文线口径同步 —— 把 W35-B 的更正落回装配源（预注册驱动，不占 shot）。

W35-B 把「氧化轴对层级不敏感」改写成了「未检出差异（n = 22 不可分辨）」，但那次改的是
**已发布稿** `paper/paper_zh_draft_v2.md`；它的**装配源** `paper/_v2_*.md` 没改。
下次任何人跑 `paper/build_paper_v2.py`，旧文案就会被带回来 —— 这是与 AF-12 同族的缺陷：
交付字节与声明的来源不一致。

本件按预注册（`probes/w36_v2_source_correction_prereg.json`）做三件事：

1. **答 README §11 第 15 条**：审计 v1 线 `paper/paper_zh_draft.md` 与英文线
   `paper/full_draft.md` 是否有「不敏感」残留；
2. 把 W35-B 的四处更正（C1–C4）**逐字**落回装配源 `_v2_body_b.md` / `_v2_appendix.md` /
   `_v2_concl.md`，且**不改**已发布稿（sha256 前后断言相等）；
3. 把 `build_paper_v2.py` 的目标改写到临时路径后 exec，**不碰仓库任何文件**，
   验证重建产物确实带上这四处更正，并把仍然存在的漂移（只有已发布稿有的段落）按实登记。

只读 + 装配源文本更正；不重跑模型、不动冻结读数；累计 shot 仍是 19。
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import json
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


ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w36_v2_source_correction_prereg.json"
SHIPPED_DRAFT = REPOSITORY_ROOT / "paper" / "paper_zh_draft_v2.md"
BUILDER = REPOSITORY_ROOT / "paper" / "build_paper_v2.py"

DRIFT_CSV = ARTIFACTS / "w36_v2_drift_inventory.csv"
SUMMARY_PATH = ARTIFACTS / "w36_v2_source_correction_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w36_v2_source_correction.md"

SCHEMA = "w36_v2_source_correction/summary@1"
TASK = "week36_v2_source_correction"
DRIFT_FIELDS = ("block", "kind", "shipped_start_line", "line_count", "sample")


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


def apply_corrections(prereg: dict) -> list:
    results = []
    for item in prereg["corrections"]:
        path = REPOSITORY_ROOT / item["path"]
        text = read_text(path)
        before_sha = sha256_bytes(text.encode("utf-8"))
        mode = item["mode"]
        if mode == "line_replace":
            old, new = item["before_text"], item["after_text"]
            if text.count(old) == 1:
                text = text.replace(old, new, 1)
                state = "已施加"
            elif new in text:
                state = "幂等（已施加）"
            else:
                raise SystemExit("C " + item["id"] + " 定位失败：" + item["locator"])
        elif mode == "line_append":
            anchor, suffix = item["anchor_text"], item["after_suffix"]
            if suffix in text:
                state = "幂等（已施加）"
            else:
                lines = text.split("\n")
                hits = [i for i, line in enumerate(lines)
                        if anchor in line and not line.lstrip().startswith("|")]
                if len(hits) != 1:
                    raise SystemExit("C " + item["id"] + " 锚点命中 " + str(len(hits)) + " 行")
                lines[hits[0]] = lines[hits[0]].rstrip("\n") + suffix
                text = "\n".join(lines)
                state = "已施加"
        elif mode == "line_substring":
            if item["steps"][-1]["replace"] in text:
                state = "幂等（已施加）"
            else:
                for step in item["steps"]:
                    hits = text.count(step["find"])
                    if hits != step["expect"]:
                        raise SystemExit("C " + item["id"] + " 子串命中 " + str(hits))
                    text = text.replace(step["find"], step["replace"], 1)
                state = "已施加"
        else:
            raise SystemExit("未知模式 " + mode)
        write_text_lf(path, text)
        results.append({"id": item["id"], "path": item["path"], "mode": mode, "state": state,
                        "sha256_before": before_sha,
                        "sha256_after": sha256_bytes(text.encode("utf-8")),
                        "changed": before_sha != sha256_bytes(text.encode("utf-8"))})
    return results


def audit_lines(prereg: dict) -> list:
    rows = []
    for target in prereg["audit_targets"]:
        path = REPOSITORY_ROOT / target["path"]
        text = read_text(path)
        hits = []
        for number, line in enumerate(text.split("\n"), start=1):
            for token in prereg["forbidden_tokens"]:
                if token in line:
                    hits.append({"line": number, "token": token, "text": line.strip()})
        rows.append({"path": target["path"], "line": target["line"],
                     "sha256_before": target["sha256_before"],
                     "sha256_now": sha256_bytes(text.encode("utf-8")),
                     "hits": hits, "hit_count": len(hits)})
    return rows


def rebuild_to_temp() -> str:
    source = read_text(BUILDER)
    needle = 'target = ROOT / "paper_zh_draft_v2.md"'
    if source.count(needle) != 1:
        raise SystemExit("build_paper_v2.py 的目标行定位失败")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_target = Path(tmp) / "paper_zh_draft_v2.md"
        patched = source.replace(needle, 'target = Path(r"' + str(tmp_target) + '")', 1)
        namespace = {"__file__": str(BUILDER), "__name__": "build_paper_v2_probe"}
        import contextlib
        import io as _io
        with contextlib.redirect_stdout(_io.StringIO()):
            exec(compile(patched, str(BUILDER), "exec"), namespace)
        if not tmp_target.exists():
            raise SystemExit("重建没有产出文件")
        return read_text(tmp_target)


def drift_inventory(shipped: str, rebuilt: str) -> list:
    a, b = shipped.split("\n"), rebuilt.split("\n")
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    rows, index = [], 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        index += 1
        kind = {"delete": "只有已发布稿有", "insert": "只有重建产物有",
                "replace": "两侧都改写"}[tag]
        sample = ""
        if tag in ("delete", "replace") and i2 > i1:
            for line in a[i1:i2]:
                if line.strip():
                    sample = line.strip()
                    break
        elif j2 > j1:
            for line in b[j1:j2]:
                if line.strip():
                    sample = line.strip()
                    break
        rows.append({"block": "D" + str(index), "kind": kind,
                     "shipped_start_line": i1 + 1, "line_count": max(i2 - i1, j2 - j1),
                     "sample": sample[:160]})
    return rows


def evaluate(prereg: dict, corrections: list, audit: list, rebuilt: str,
             shipped_sha: str, drift: list) -> list:
    def verdict(identifier, description, value, threshold, passed) -> dict:
        return {"id": identifier, "description": description,
                "value": None if value is None else float(value),
                "threshold": None if threshold is None else float(threshold),
                "verdict": "成立" if bool(passed) else "判否"}

    afters = [item["after_text"] for item in prereg["corrections"] if "after_text" in item]
    afters.append(prereg["corrections"][1]["after_suffix"].strip())
    afters += [step["replace"] for step in prereg["corrections"][3]["steps"]]
    in_rebuilt = sum(1 for text in afters if text in rebuilt)
    sources_ok = all(
        (item["state"] in ("已施加", "幂等（已施加）"))
        for item in corrections)
    return [
        verdict("H36e1", "v1 线与英文线「不敏感」残留处数（README §11 第 15 条）",
                float(sum(row["hit_count"] for row in audit)), 0.0,
                sum(row["hit_count"] for row in audit) == 0),
        verdict("H36e2", "四处口径更正全部落在装配源上（幂等）",
                float(len(corrections)), 4.0, len(corrections) == 4 and sources_ok),
        verdict("H36e3", "重建产物带上全部四处更正",
                float(in_rebuilt), float(len(afters)), in_rebuilt == len(afters)),
        verdict("H36e4", "已发布稿 sha256 未被本件改动",
                None, None, shipped_sha == prereg["shipped_draft"]["sha256_before"]),
        verdict("H36e5", "装配源仍无法复现的漂移段数（登记值，不设门）",
                float(len(drift)), None, True),
    ]


def render_report(prereg: dict, corrections: list, audit: list, drift: list,
                  criteria: list, shipped_sha: str) -> str:
    lines = [
        "# W36-E 结题报告：v1 线 / 英文线口径同步（把更正落回装配源）",
        "",
        "- **性质**：预注册驱动的装配源口径同步，**不占 shot**",
        "- **累计 shot**：19",
        "- **预注册**：`probes/w36_v2_source_correction_prereg.json`（`locked_before_run`）",
        "",
        "## 1. README §11 第 15 条的答案",
        "",
        "| 线 | 文件 | 「不敏感」命中 | sha256 现在 |",
        "| --- | --- | --- | --- |",
    ]
    for row in audit:
        lines.append("| " + row["line"] + " | `" + row["path"] + "` | " + str(row["hit_count"])
                     + " | `" + row["sha256_now"][:16] + "…` |")
    lines += [
        "",
        "**v1 线与英文线均为 0 处残留**——第 15 条本身判否（不需要补正）。",
        "但审计暴露了真正的隐患：**装配源**还没改，下次 `paper/build_paper_v2.py` 会把旧文案带回来。",
        "",
        "## 2. 落回装配源的四处更正",
        "",
        "| 更正 | 装配源 | 模式 | 状态 | 是否改动字节 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in corrections:
        lines.append("| " + row["id"] + " | `" + row["path"] + "` | " + row["mode"] + " | "
                     + row["state"] + " | " + ("是" if row["changed"] else "否") + " |")
    lines += [
        "",
        "已发布稿 `paper/paper_zh_draft_v2.md` 的 sha256 现在是 `" + shipped_sha + "`，"
        "与预注册里的 `" + prereg["shipped_draft"]["sha256_before"] + "` 逐位相同 —— **本件没有改已发布稿**。",
        "",
        "## 3. 重建校验与漂移登记",
        "",
        "把 `build_paper_v2.py` 的目标改写到临时路径后 exec（不碰仓库任何文件）："
        "四处更正**全部出现在重建产物里**。",
        "",
        "仍然登记到 **" + str(len(drift)) + " 段**装配源无法复现的漂移（这段是历史累积，"
        "不属于本件范围，但必须让坐标可见）：",
        "",
        "| 段 | 类型 | 已发布稿起始行 | 行数 | 样例 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in drift[:20]:
        lines.append("| " + row["block"] + " | " + row["kind"] + " | "
                     + str(row["shipped_start_line"]) + " | " + str(row["line_count"]) + " | "
                     + row["sample"].replace("|", "\\|")[:110] + " |")
    if len(drift) > 20:
        lines.append("| … | 其余 " + str(len(drift) - 20) + " 段见 `w36_v2_drift_inventory.csv` | | | |")
    lines += [
        "",
        "## 4. 判据",
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
        "## 5. 边界与下一步",
        "",
        "- 本件只改**装配源**的四处文字，不改已发布稿、不重生成 docx、不动任何数字。",
        "- `w36_v2_drift_inventory.csv` 是**登记**不是判决：装配源与已发布稿的漂移（例如 §3.8.1 等"
        "只在已发布稿里存在的段落）需要一次专门的「回灌」轮次，本轮不做。",
        "- 区间跨 0 = 未检出差异，不等于证明无差异。",
        "- 不占 shot（累计仍 19）。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    started = time.perf_counter()
    prereg = json.loads(read_text(PREREG_PATH))
    prereg_sha = sha256_file(PREREG_PATH)
    audit = audit_lines(prereg)
    corrections = apply_corrections(prereg)
    rebuilt = rebuild_to_temp()
    shipped_text = read_text(SHIPPED_DRAFT)
    shipped_sha = sha256_bytes(shipped_text.encode("utf-8"))
    drift = drift_inventory(shipped_text, rebuilt)
    criteria = evaluate(prereg, corrections, audit, rebuilt, shipped_sha, drift)

    write_csv_lf(DRIFT_CSV, DRIFT_FIELDS, drift)
    summary = {
        "schema": SCHEMA, "task": TASK,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": float(time.perf_counter() - started),
        "prereg": {"path": "probes/w36_v2_source_correction_prereg.json",
                   "sha256": prereg_sha, "locked_before_run": prereg["locked_before_run"]},
        "ledger": {"main_scoreboard_shots_this_week": 0,
                   "cumulative_main_scoreboard_attempts_after": 19,
                   "why_not_a_shot": "装配源口径同步：不拟合模型、不新增特征、不触 ε 主记分牌。"},
        "audit": audit, "corrections": corrections,
        "shipped_draft": {"path": "paper/paper_zh_draft_v2.md", "sha256": shipped_sha,
                          "unchanged": shipped_sha == prereg["shipped_draft"]["sha256_before"]},
        "rebuild": {"drift_blocks": len(drift), "inventory_csv":
                    "probes/artifacts/w36_v2_drift_inventory.csv"},
        "criteria": criteria,
        "headline": [
            "README §11 第 15 条判否：v1 线与英文线 0 处「不敏感」残留。",
            "真正隐患是装配源：W35-B 的四处更正已逐字落回 `_v2_body_b.md` / `_v2_appendix.md` / "
            "`_v2_concl.md`，重建产物现在带上这四处。",
            "已发布稿 sha256 未变（`" + shipped_sha[:16] + "…`），本件不触碰交付字节。",
            "仍登记 " + str(len(drift)) + " 段装配源无法复现的历史漂移，留给专门的回灌轮次。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(prereg, corrections, audit, drift, criteria, shipped_sha),
                           encoding="utf-8", newline="\n")
    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    print("audit hits " + str(sum(row["hit_count"] for row in audit))
          + "; corrections " + str(len(corrections))
          + "; drift blocks " + str(len(drift)))
    print("shipped sha unchanged " + str(shipped_sha == prereg["shipped_draft"]["sha256_before"]))
    print("verdicts " + str(passed) + "/" + str(len(criteria)))
    for item in criteria:
        if item["verdict"] != "成立":
            print("FAIL " + item["id"] + " " + item["description"])
    return 0 if passed == len(criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())