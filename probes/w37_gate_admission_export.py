# -*- coding: utf-8 -*-
"""W37-B 探针：把还原轴准入清单接进交付/导出链路（README §11 第 18 条）。

* 真表运行 scripts/check_redox_admission.py，收集论文侧引用点；
* 合成违规自检：把 register/registry/manifest 的副本写到临时目录，删掉一行 / 改一个
  key，断言校验器 exit != 0；对未改动副本断言 exit == 0（绝不改仓库里的真表）；
* 落盘 sites.csv / summary.json / md 报告，并给出判据 H37b1..H37b5。

只读真表；0 shot（累计 19）；不拟合模型；不改任何已交付字节。
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "scripts"
PROBES = REPOSITORY_ROOT / "probes"
ARTIFACTS = PROBES / "artifacts"
REPORTS = REPOSITORY_ROOT / "reports"
CHECKER = SCRIPTS / "check_redox_admission.py"

REGISTER = ARTIFACTS / "w35_gated_reference_register.csv"
REGISTRY = REPOSITORY_ROOT / "data" / "processed" / "redox_state_legality_registry.csv"
MANIFEST = ARTIFACTS / "w36_gate_admission_manifest.csv"
PAPER = REPOSITORY_ROOT / "paper" / "paper_zh_draft_v2.md"

SITES_CSV = ARTIFACTS / "w37_gate_admission_export_sites.csv"
SUMMARY_PATH = ARTIFACTS / "w37_gate_admission_export_summary.json"
REPORT_PATH = REPORTS / "w37_gate_admission_export.md"

SCHEMA = "w37_gate_admission_export/summary@1"
TASK = "week37_gate_admission_export"
SITE_FIELDS = ("paper_line", "section", "row_label", "axis", "matched_reference_id",
               "admission", "mark", "note")
NEGATIVE_REFERENCE_ID = "r6_red_gfn2"
SHOTS_THIS_WEEK = 0
NEW_FILES = (CHECKER, Path(__file__).resolve(), SITES_CSV, SUMMARY_PATH, REPORT_PATH)


def sha256_file(path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_rows(path) -> list:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_lf(path, fieldnames, rows) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json_lf(path, payload) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8", newline="\n")


def run_checker(register=REGISTER, registry=REGISTRY, manifest=MANIFEST, paper=PAPER):
    completed = subprocess.run(
        [sys.executable, str(CHECKER), "--register", str(register), "--registry", str(registry),
         "--manifest", str(manifest), "--paper", str(paper)],
        cwd=str(REPOSITORY_ROOT), capture_output=True, encoding="utf-8")
    stdout = (completed.stdout or "").strip()
    payload = json.loads(stdout.splitlines()[-1]) if stdout else {}
    return completed.returncode, payload


def synthetic_violations() -> dict:
    """在临时目录复现「引用点没登记 -> 校验器拒绝」。"""
    outcomes = {}
    tmp = Path(tempfile.mkdtemp(prefix="w37_gate_admission_"))
    try:
        register_copy = tmp / "register.csv"
        registry_copy = tmp / "registry.csv"
        manifest_copy = tmp / "manifest.csv"
        shutil.copyfile(REGISTER, register_copy)
        shutil.copyfile(REGISTRY, registry_copy)
        shutil.copyfile(MANIFEST, manifest_copy)

        returncode, _ = run_checker(register_copy, registry_copy, manifest_copy)
        outcomes["intact_copies_exit_zero"] = int(returncode == 0)

        rows = read_rows(REGISTER)
        fields = list(rows[0].keys())
        kept = [row for row in rows if row["reference_id"] != NEGATIVE_REFERENCE_ID]
        write_csv_lf(register_copy, fields, kept)
        returncode, payload = run_checker(register_copy, registry_copy, manifest_copy)
        refused = any(item["kind"] == "unregistered" for item in payload.get("violations", []))
        outcomes["deleted_row_exit_nonzero"] = int(returncode != 0 and refused)

        rows = read_rows(REGISTER)
        for row in rows:
            if row["reference_id"] == NEGATIVE_REFERENCE_ID:
                row["reference_id"] = NEGATIVE_REFERENCE_ID + "_renamed"
        write_csv_lf(register_copy, fields, rows)
        returncode, _ = run_checker(register_copy, registry_copy, manifest_copy)
        outcomes["renamed_key_exit_nonzero"] = int(returncode != 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return outcomes


def has_lf_no_bom(path) -> bool:
    path = Path(path)
    if not path.is_file():
        return False
    raw = path.read_bytes()
    return not raw.startswith(b"\xef\xbb\xbf") and b"\r\n" not in raw


def render_report(payload, sites) -> str:
    lines = [
        "# W37-B 报告：还原轴准入清单接进交付/导出链路",
        "",
        "- **性质**：治理件 / 后验接线（只读真表与论文），**不占 shot**",
        "- **累计 shot**：" + str(payload["ledger"]["cumulative_main_scoreboard_attempts_after"]),
        "- **回答**：README §11 第 18 条「准入清单接进交付 manifest（W36-D 已备件，未接线）」",
        "",
        "## 1. 接线方式",
        "",
        "scripts/check_redox_admission.py 机械解析论文附录 A/B/C 的表格行，把其中出现的",
        "登记读数（quoted_value 三位有效数字）与「合法子集/总体」分数绑到",
        "probes/artifacts/w35_gated_reference_register.csv，逐点调用 W36-D 的 admit()：",
        "",
        "1. 绑不到登记行 -> unregistered 违规；",
        "2. admit() 抛 AdmissionRefused -> refused 违规；",
        "3. 还原轴的 mark 由 W34-A 守卫复算，与登记值不一致 -> mark_mismatch 违规（禁止手写标记）；",
        "4. 氧化轴引用点按既有约定标「不适用（门禁只覆盖还原轴）」。",
        "",
        "全部通过 -> stdout 打印一行 JSON 且 exit 0；任一违规 -> 打印 JSON 且 exit 1。",
        "",
        "## 2. 判据",
        "",
        "| 判据 | 说明 | value | threshold | 裁决 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in payload["criteria"]:
        lines.append("| " + item["id"] + " | " + item["description"] + " | "
                     + ("" if item["value"] is None else str(item["value"])) + " | "
                     + ("" if item["threshold"] is None else str(item["threshold"])) + " | "
                     + item["verdict"] + " |")
    lines += [
        "",
        "## 3. 论文侧引用点清单",
        "",
        "| 论文行 | 附录 | 表格行 | 轴 | 登记行 | 准入 | 标记 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for site in sites:
        lines.append("| " + str(site["paper_line"]) + " | 附录 " + site["appendix"] + " | "
                     + site["row_label"] + " | " + site["axis"] + " | "
                     + site["matched_reference_id"] + " | " + site["admission"] + " | "
                     + site["mark"] + " |")
    lines += [
        "",
        "## 4. 合成违规自检",
        "",
        "把 register/registry/manifest 的副本写到临时目录后：",
        "",
        "- 未改动副本 -> 校验器 exit 0（无假阳性）；",
        "- 删掉被引用的登记行 " + NEGATIVE_REFERENCE_ID + " -> 校验器 exit != 0（报 unregistered）；",
        "- 把该行 reference_id 改名 -> 校验器 exit != 0。",
        "",
        "**仓库里的真表未被改动**（前后 sha256 相等，见 summary 的 inputs）。",
        "",
        "## 5. 为什么接在 test_repo_hygiene 而不是改历史导出器",
        "",
        "tests/test_repo_hygiene.py 已被各周导出器的 VERIFIERS 列表引用（如 Week 14–20、",
        "Week 25–27 的 run_verifiers）。在这些导出器的验证块里追加一个测试函数，等于把准入",
        "检查**自动接进导出阶段的验证块**：任何人在导出时都会连带走这一关。",
        "",
        "反过来，去改历史周的导出脚本会改动已交付字节、破坏已交付包的回归测试（AF-12 同族",
        "风险：交付字节一变，artifacts_commit 就无法标识原交付）。因此只**在 test_repo_hygiene",
        "末尾追加**一个 subprocess 测试，调用 scripts/check_redox_admission.py 并断言 exit 0。",
        "",
        "## 6. 边界",
        "",
    ]
    for item in payload["boundaries"]:
        lines.append("- " + item)
    lines += [
        "- 不改任何已交付字节；不 commit。",
        "",
    ]
    return "\n".join(lines)


def evaluate(real_returncode, payload, negatives, inputs_unchanged, lf_ok) -> list:
    def verdict(identifier, description, value, threshold, passed) -> dict:
        return {"id": identifier, "description": description,
                "value": None if value is None else float(value),
                "threshold": None if threshold is None else float(threshold),
                "verdict": "成立" if bool(passed) else "判否"}

    unregistered = payload.get("unregistered", [])
    mark_mismatch = payload.get("mark_mismatch", [])
    empty_mark = [item for item in payload.get("violations", []) if item["kind"] == "empty_mark"]
    reduction = int(payload.get("reduction_sites", 0))
    negative_ok = sum(int(value) for value in negatives.values())
    return [
        verdict("H37b1", "校验器在真表上 exit 0 且输出 JSON passed=true",
                1.0 if (real_returncode == 0 and payload.get("passed")) else 0.0, 1.0,
                real_returncode == 0 and payload.get("passed") is True),
        verdict("H37b2", "论文侧引用点 >= 6 且全部找到登记行（未登记 0）",
                float(payload.get("sites", 0)), 6.0,
                int(payload.get("sites", 0)) >= 6 and not unregistered),
        verdict("H37b3", "还原轴引用点全部由 W34-A 守卫复算（mark 非空、与登记值零不一致）；氧化轴标「不适用」",
                float(reduction), 5.0,
                reduction >= 5 and not mark_mismatch and not empty_mark
                and payload.get("oxidation_marks") == ["不适用（门禁只覆盖还原轴）"]),
        verdict("H37b4", "合成违规自检：删行/改名 -> exit != 0，未改动副本 -> exit == 0",
                float(negative_ok), float(len(negatives)),
                negative_ok == len(negatives) and len(negatives) == 3),
        verdict("H37b5", "0 shot（累计 19）、全 LF / 无 BOM、不改任何已交付字节",
                0.0, 0.0,
                SHOTS_THIS_WEEK == 0 and inputs_unchanged and lf_ok),
    ]


def main() -> int:
    started = time.perf_counter()
    before = {str(path): sha256_file(path) for path in (REGISTER, REGISTRY, MANIFEST, PAPER)}

    real_returncode, payload = run_checker()
    negatives = synthetic_violations()

    after = {str(path): sha256_file(path) for path in (REGISTER, REGISTRY, MANIFEST, PAPER)}
    inputs_unchanged = before == after and payload.get("passed") is True

    sites = payload.get("sites_detail", [])
    write_csv_lf(SITES_CSV, SITE_FIELDS, [
        {"paper_line": site["paper_line"], "section": "附录 " + site["appendix"],
         "row_label": site["row_label"], "axis": site["axis"],
         "matched_reference_id": site["matched_reference_id"], "admission": site["admission"],
         "mark": site["mark"], "note": site["note"]} for site in sites])

    lf_ok = all(has_lf_no_bom(path) for path in NEW_FILES if Path(path).is_file())
    criteria = evaluate(real_returncode, payload, negatives, inputs_unchanged, lf_ok)

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {"main_scoreboard_shots_this_week": 0,
                   "cumulative_main_scoreboard_attempts_after": 19,
                   "why_not_a_shot": "治理件：只读真表与论文，不拟合模型、不触 ε 主记分牌。"},
        "promoted": False,
        "checker": {"path": "scripts/check_redox_admission.py",
                    "returncode": real_returncode, "passed": bool(payload.get("passed"))},
        "sites": {"rows": int(payload.get("sites", 0)),
                  "reduction": int(payload.get("reduction_sites", 0)),
                  "oxidation": int(payload.get("oxidation_sites", 0)),
                  "paper_rows": int(payload.get("paper_rows", 0)),
                  "detail": sites},
        "violations": payload.get("violations", []),
        "negative_control": negatives,
        "inputs": payload.get("inputs", {}),
        "inputs_unchanged": bool(inputs_unchanged),
        "criteria": criteria,
        "headline": [
            "把 W36-D 的准入件接进交付/导出链路：论文附录的还原轴引用点在导出阶段机械校验。",
            "论文附录 A 的 2 个表格行绑出 " + str(payload.get("sites", 0)) + " 个引用点（还原 "
            + str(payload.get("reduction_sites", 0)) + " / 氧化 " + str(payload.get("oxidation_sites", 0))
            + "），mark 全部由 W34-A 守卫复算。",
            "合成违规自检：删掉/改名被引用的登记行后校验器 exit != 0。",
            "不占 shot（累计仍 19）；不改任何已交付字节。",
        ],
        "boundaries": payload.get("boundaries", []) + [
            "promoted=False：本轮不晋升任何端点、不改冻结读数。",
            "只允许新建 4 个产物 + 追加 1 个测试；不 commit。",
        ],
    }
    write_json_lf(SUMMARY_PATH, summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ledger = summary["ledger"]
    REPORT_PATH.write_text(render_report({**payload, "criteria": criteria, "ledger": ledger}, sites),
                           encoding="utf-8", newline="\n")

    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    print("checker rc " + str(real_returncode) + "; sites " + str(payload.get("sites", 0))
          + " (reduction " + str(payload.get("reduction_sites", 0))
          + " / oxidation " + str(payload.get("oxidation_sites", 0)) + ")", flush=True)
    print("negative control " + json.dumps(negatives, ensure_ascii=False), flush=True)
    print("verdicts " + str(passed) + "/" + str(len(criteria)), flush=True)
    for item in criteria:
        if item["verdict"] != "成立":
            print("FAIL " + item["id"] + " " + item["description"])
    return 0 if passed == len(criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
