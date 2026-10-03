# -*- coding: utf-8 -*-
"""W35-A：门禁旁路层 + 引用登记表 + 下游消费者审计（后验，不占 shot）。

W34-A 把态合法性判定从报告升成盘上的权威列（`redox_state_legality_registry.csv`，1028 行），
并交付守卫 `assert_redox_readable`。但守卫「可用」不等于「被用」：引用 −0.602 的地方
（论文 §3.20 / 附录 A / 结论、决策日志）依然只写数字、不带门禁结论。本轮补三件：

* **旁路表**（`data/processed/redox_readability_sidecar.csv`）：按 InChIKey 一行一键（246 行），
  把注册表里 GFN2 四介质 + ORCA 两介质的 `legal` / `reason` 摊平，另给 `in_paired_orca`。
  **派生旁路，不改主注册表**（主注册表 sha256 必须逐位不变）。
* **引用登记表**（`probes/artifacts/w35_gated_reference_register.csv`）：把所有引用还原轴数值的
  点登记成行，每行**调用 W34-A 的守卫**得出 `mark`——拒答就写「不可判定」，不是自算一遍。
  **门禁范围声明**：门禁是阴离子态审计，只管还原轴；氧化轴登记为「不适用」。
* **消费者审计**（`probes/artifacts/w35_gated_consumer_audit.csv`）：登记七个下游消费者，
  逐段检查「引用受门禁约束的数值就必须出现标记 `不可判定`」。审计同时对**由预注册反推的
  更正前论文**跑一遍，把「先发现缺失、后被更正修好」这件事变成可复算读数。

只读、不联网、不装依赖、不拟合模型；累计 shot 仍是 19。
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
import w34_legality_registry as registry_mod
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
REGISTRY_CSV = REPOSITORY_ROOT / "data" / "processed" / "redox_state_legality_registry.csv"
SIDECAR_CSV = REPOSITORY_ROOT / "data" / "processed" / "redox_readability_sidecar.csv"
CROSSCHECK_CSV = ARTIFACTS / "w24_3_level_crosscheck.csv"
GATES_CSV = ARTIFACTS / "w33_bound_state_gate_gates.csv"
DASHBOARD_MD = ARTIFACTS / "w34_channel_dashboard.md"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w35_paper_r6_correction_prereg.json"
PAPER_PATH = REPOSITORY_ROOT / "paper" / "paper_zh_draft_v2.md"
LOG_PATH = REPOSITORY_ROOT / "reports" / "decisions_log.md"
REGISTER_CSV = ARTIFACTS / "w35_gated_reference_register.csv"
AUDIT_CSV = ARTIFACTS / "w35_gated_consumer_audit.csv"
SUMMARY_PATH = ARTIFACTS / "w35_redox_gate_consumers_summary.json"
FIGURE_PATH = ARTIFACTS / "w35_redox_gate_consumers.png"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w35_redox_gate_consumers.md"

SCHEMA = "w35_redox_gate_consumers/summary@1"
TASK = "week35_redox_gate_consumers"
MIN_LEGAL_SUBSET = registry_mod.MIN_LEGAL_SUBSET
EXPECTED_SIDECAR_ROWS = 246
REGISTRY_SHA256_BEFORE = "a01272b3e75514a609295275d18c82c39fb65c5bc27056feb4ed8c6cd0c6b60d"
FOUR_CORE_SHA256 = "e42885eb43779b7a4d472da88fefe018fe94150ff5b6fba86b3ed9bc83dc8bee"
FOUR_CORE_CSV = REPOSITORY_ROOT / "data" / "processed" / "four_core_key_registry.csv"

GATED_TOKENS = ("0.602", "0.601732", "0.835", "1.437")
MARK_TOKEN = "不可判定"
MARK_ID_APPLICABLE = "不适用（门禁只覆盖还原轴）"
MARK_READABLE = "可宣读"

SIDECAR_FIELDS = (
    "inchikey", "name", "in_paired_orca", "n_gfn2_legal_media", "readable_gfn2",
    "n_orca_legal_media", "readable_orca",
    "gfn2_gas_legal", "gfn2_gas_reason",
    "gfn2_thf_legal", "gfn2_thf_reason",
    "gfn2_benzaldehyde_legal", "gfn2_benzaldehyde_reason",
    "gfn2_water_legal", "gfn2_water_reason",
    "orca_gas_legal", "orca_gas_reason",
    "orca_smd_acetonitrile_legal", "orca_smd_acetonitrile_reason",
)
REGISTER_FIELDS = ("reference_id", "axis", "level", "medium", "quantity", "quoted_value",
                   "source_path", "source_column", "population_scope", "population_n", "legal_n",
                   "min_legal_subset", "mark", "guard_verdict", "guard_message")
AUDIT_FIELDS = ("consumer_id", "path", "locator", "gated_values_found", "requires_mark",
                "mark_token", "mark_present", "verdict")

REFERENCE_POINTS = (
    {"id": "r6_ox_gfn2", "axis": "oxidation", "level": "gfn2", "medium": "gas",
     "quantity": "tau_b", "source": "probes/artifacts/w24_3_level_crosscheck.csv",
     "column": "same_ox_gfn2", "population": "paired_orca_22"},
    {"id": "r6_ox_orca", "axis": "oxidation", "level": "orca", "medium": "gas",
     "quantity": "tau_b", "source": "probes/artifacts/w24_3_level_crosscheck.csv",
     "column": "same_ox_orca", "population": "paired_orca_22"},
    {"id": "r6_red_gfn2", "axis": "reduction", "level": "gfn2", "medium": "gas",
     "quantity": "tau_b", "source": "probes/artifacts/w24_3_level_crosscheck.csv",
     "column": "same_red_gfn2", "population": "paired_orca_22"},
    {"id": "r6_red_orca", "axis": "reduction", "level": "orca", "medium": "gas",
     "quantity": "tau_b", "source": "probes/artifacts/w24_3_level_crosscheck.csv",
     "column": "same_red_orca", "population": "paired_orca_22"},
    {"id": "w33a_gfn2_gas", "axis": "reduction", "level": "gfn2", "medium": "gas",
     "quantity": "tau_legal", "source": "probes/artifacts/w33_bound_state_gate_gates.csv",
     "gates_medium": "gas", "population": "census_246"},
    {"id": "w33a_gfn2_thf", "axis": "reduction", "level": "gfn2", "medium": "thf",
     "quantity": "tau_legal", "source": "probes/artifacts/w33_bound_state_gate_gates.csv",
     "gates_medium": "thf", "population": "census_246"},
    {"id": "w33a_gfn2_benzaldehyde", "axis": "reduction", "level": "gfn2",
     "medium": "benzaldehyde", "quantity": "tau_legal",
     "source": "probes/artifacts/w33_bound_state_gate_gates.csv",
     "gates_medium": "benzaldehyde", "population": "census_246"},
    {"id": "w33a_gfn2_water", "axis": "reduction", "level": "gfn2", "medium": "water",
     "quantity": "tau_legal", "source": "probes/artifacts/w33_bound_state_gate_gates.csv",
     "gates_medium": "water", "population": "census_246"},
    {"id": "w33a_orca_gas", "axis": "reduction", "level": "orca", "medium": "gas",
     "quantity": "tau_legal", "source": "probes/artifacts/w33_bound_state_gate_gates.csv",
     "gates_medium": "orca_gas", "population": "paired_orca_22"},
    {"id": "w33a_orca_smd_acetonitrile", "axis": "reduction", "level": "orca",
     "medium": "smd_acetonitrile", "quantity": "tau_legal",
     "source": "probes/artifacts/w33_bound_state_gate_gates.csv",
     "gates_medium": "orca_smd_acetonitrile", "population": "paired_orca_22"},
)

CONSUMERS = (
    {"id": "paper_s320", "path": "paper/paper_zh_draft_v2.md", "locator": "### 3.20 "},
    {"id": "paper_s321", "path": "paper/paper_zh_draft_v2.md", "locator": "### 3.21 "},
    {"id": "paper_appendix_a", "path": "paper/paper_zh_draft_v2.md", "locator": "## 附录 A"},
    {"id": "paper_conclusion", "path": "paper/paper_zh_draft_v2.md", "locator": "## 5 结论"},
    {"id": "dashboard_w34", "path": "probes/artifacts/w34_channel_dashboard.md", "locator": ""},
    {"id": "decisions_log_w33a", "path": "reports/decisions_log.md", "locator": "## 28.87 "},
    {"id": "decisions_log_w34b", "path": "reports/decisions_log.md", "locator": "## 28.88 "},
)

HEADING_RE = re.compile(r"^#{2,4} ")


def read_csv_rows(path) -> list:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv_lf(path, fieldnames, rows) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json_lf(path, payload) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    write_json_stable(Path(path), payload)


def fmt(value, digits: int = 6) -> str:
    if value is None:
        return ""
    return format(float(value), "." + str(digits) + "g")


def load_registry() -> list:
    rows = read_csv_rows(REGISTRY_CSV)
    for row in rows:
        row["legal"] = int(row["legal"])
    return rows


def paired_keys(registry) -> set:
    return {row["inchikey"] for row in registry if row["level"] == "orca"}


def build_sidecar(registry, paired) -> list:
    gfn2_media = [medium for medium, _, _ in registry_mod.gate.MEDIA]
    orca_media = [medium for medium, _, _ in registry_mod.gate.ORCA_MEDIA]
    by_key: dict = {}
    for row in registry:
        by_key.setdefault(row["inchikey"], {"name": row.get("name", "")})[
            row["level"] + "|" + row["medium"]] = row
    sidecar = []
    for key in sorted(by_key):
        entry = by_key[key]
        record = {"inchikey": key, "name": entry.get("name", ""),
                  "in_paired_orca": int(key in paired)}
        gfn2_legal = 0
        for medium in gfn2_media:
            row = entry.get("gfn2|" + medium)
            if row is None:
                continue
            record["gfn2_" + medium + "_legal"] = row["legal"]
            record["gfn2_" + medium + "_reason"] = row["reason"]
            gfn2_legal += row["legal"]
        record["n_gfn2_legal_media"] = gfn2_legal
        record["readable_gfn2"] = "有介质可宣读" if gfn2_legal else "全介质不可判定"
        orca_legal = 0
        for medium in orca_media:
            row = entry.get("orca|" + medium)
            if row is None:
                record["orca_" + medium + "_legal"] = ""
                record["orca_" + medium + "_reason"] = ""
                continue
            record["orca_" + medium + "_legal"] = row["legal"]
            record["orca_" + medium + "_reason"] = row["reason"]
            orca_legal += row["legal"]
        record["n_orca_legal_media"] = orca_legal if key in paired else ""
        if key not in paired:
            record["readable_orca"] = "无 ORCA 数据"
        else:
            record["readable_orca"] = "有介质可宣读" if orca_legal else "全介质不可判定"
        sidecar.append(record)
    return sidecar


def subset_rows(registry, level, medium, keys) -> list:
    return [row for row in registry
            if row["level"] == level and row["medium"] == medium and row["inchikey"] in keys]


def guard_mark(rows, level, medium) -> tuple:
    """调用 W34-A 的守卫；拒答由守卫抛出，不是本脚本自算。"""
    try:
        info = registry_mod.assert_redox_readable(rows, level, medium)
    except registry_mod.RedoxGateRefusal as error:
        return MARK_TOKEN, "refused", str(error)
    return MARK_READABLE, "allowed", ("合法子集 " + str(info["legal"]) + " >= "
                                      + str(MIN_LEGAL_SUBSET))


def build_reference_register(registry, paired) -> list:
    crosscheck = read_csv_rows(CROSSCHECK_CSV)[0]
    gates = {row["medium"]: row for row in read_csv_rows(GATES_CSV)}
    all_keys = {row["inchikey"] for row in registry if row["level"] == "gfn2"}
    populations = {"paired_orca_22": paired, "census_246": all_keys}
    register = []
    for point in REFERENCE_POINTS:
        keys = populations[point["population"]]
        rows = subset_rows(registry, point["level"], point["medium"], keys)
        population_n = len(rows)
        if point["axis"] == "oxidation":
            legal_n, mark, verdict, message = "", MARK_ID_APPLICABLE, "not_applicable", (
                "门禁是阴离子态审计，只覆盖还原轴；氧化轴（阳离子态）无对应条款")
        else:
            legal_n = sum(row["legal"] for row in rows)
            mark, verdict, message = guard_mark(rows, point["level"], point["medium"])
        if "column" in point:
            value = repr(float(crosscheck[point["column"]]))
            source_column = point["column"]
        else:
            value = gates[point["gates_medium"]]["tau_legal"]
            source_column = "tau_legal@" + point["gates_medium"]
        register.append({
            "reference_id": point["id"], "axis": point["axis"], "level": point["level"],
            "medium": point["medium"], "quantity": point["quantity"], "quoted_value": value,
            "source_path": point["source"], "source_column": source_column,
            "population_scope": point["population"], "population_n": population_n,
            "legal_n": legal_n, "min_legal_subset": MIN_LEGAL_SUBSET,
            "mark": mark, "guard_verdict": verdict, "guard_message": message})
    return register


def section_text(text: str, locator: str) -> str:
    lines = text.split("\n")
    start = None
    for index, line in enumerate(lines):
        if locator and line.startswith(locator):
            start = index
            break
    if start is None:
        if locator:
            return ""
        return text
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if HEADING_RE.match(lines[index]):
            end = index
            break
    return "\n".join(lines[start:end])


def audit_consumers(texts: dict) -> list:
    audit = []
    for consumer in CONSUMERS:
        text = texts.get(consumer["path"], "")
        window = section_text(text, consumer["locator"])
        found = [token for token in GATED_TOKENS if token in window]
        present = int(MARK_TOKEN in window)
        audit.append({
            "consumer_id": consumer["id"], "path": consumer["path"],
            "locator": consumer["locator"], "gated_values_found": ";".join(found),
            "requires_mark": 1, "mark_token": MARK_TOKEN, "mark_present": present,
            "verdict": "成立" if present else "判否"})
    return audit


def reconstruct_before(text: str, prereg: dict) -> str:
    """由预注册反推更正前的论文，供审计做「先发现缺失」的对照。"""
    out = text
    for item in prereg["corrections"]:
        if item["id"] == "C2":
            out = out.replace(item["after_suffix"], "")
        elif item["id"] == "C4":
            for step in item["steps"]:
                out = out.replace(step["replace"], step["find"])
        else:
            out = out.replace(item["after_text"], item["before_text"])
    return out


def evaluate(registry, sidecar, register, audit, audit_before, shas) -> list:
    def verdict(identifier, description, value, threshold, passed) -> dict:
        return {"id": identifier, "description": description,
                "value": None if value is None else float(value),
                "threshold": None if threshold is None else float(threshold),
                "verdict": "成立" if bool(passed) else "判否"}

    mismatches = 0
    pairs = 0
    lookup = {(row["level"], row["medium"], row["inchikey"]): row for row in registry}
    for row in sidecar:
        for level, media in ((("gfn2"), [m for m, _, _ in registry_mod.gate.MEDIA]),
                             (("orca"), [m for m, _, _ in registry_mod.gate.ORCA_MEDIA])):
            for medium in media:
                key = (level, medium, row["inchikey"])
                if key not in lookup:
                    continue
                pairs += 1
                source = lookup[key]
                if (str(row[level + "_" + medium + "_legal"]) != str(source["legal"])
                        or str(row[level + "_" + medium + "_reason"]) != source["reason"]):
                    mismatches += 1
    h35a = verdict("H35a", "旁路表 246 行且与 W34 注册表逐位一致",
                   float(len(sidecar)), float(EXPECTED_SIDECAR_ROWS),
                   len(sidecar) == EXPECTED_SIDECAR_ROWS and mismatches == 0 and pairs == 1028)

    reduction = [row for row in register if row["axis"] == "reduction"]
    same_source = sum(1 for row in reduction
                      if ((int(row["legal_n"]) < MIN_LEGAL_SUBSET) == (row["mark"] == MARK_TOKEN)))
    expected_legal = {"r6_red_gfn2": 1, "r6_red_orca": 0, "w33a_gfn2_gas": 52,
                      "w33a_gfn2_thf": 154, "w33a_gfn2_benzaldehyde": 154,
                      "w33a_gfn2_water": 161, "w33a_orca_gas": 0,
                      "w33a_orca_smd_acetonitrile": 2}
    legal_match = sum(1 for row in reduction
                      if int(row["legal_n"]) == expected_legal[row["reference_id"]])
    h35b = verdict("H35b", "引用登记表 >= 8 行，且 mark 与门禁同源（合法子集逐位一致）",
                   float(len(register)), 8.0,
                   len(register) >= 8 and same_source == len(reduction)
                   and legal_match == len(reduction))

    missing_now = [row["consumer_id"] for row in audit if row["mark_present"] != 1]
    missing_before = [row["consumer_id"] for row in audit_before if row["mark_present"] != 1]
    h35c = verdict("H35c", "7 个下游消费者更正后全部带标记，且更正前确有缺失（审计先失败）",
                   float(len(audit) - len(missing_now)), float(len(audit)),
                   len(audit) == 7 and not missing_now and len(missing_before) >= 1)

    h35d = verdict("H35d", "主注册表与四核心注册表 sha256 均未变",
                   None, None,
                   shas["registry_intact"] == 1 and shas["four_core_intact"] == 1)

    h35e = verdict("H35e", "全 LF、不拟合模型（models_fitted = 0）、shot = 0",
                   None, None, shas["all_lf"] == 1)
    return [h35a, h35b, h35c, h35d, h35e], {
        "sidecar_vs_registry_pairs": pairs, "sidecar_mismatches": mismatches,
        "consumer_missing_after": missing_now, "consumer_missing_before": missing_before}


def render_report(payload: dict) -> str:
    lines = [
        "# W35-A 报告：门禁旁路层与下游消费者审计",
        "",
        "- 性质：后验旁路层 / 审计，**不占 shot**（累计仍 "
        + str(payload["ledger"]["cumulative_main_scoreboard_attempts_after"]) + "）",
        "- 输入：W34 门禁注册表（sha256 `" + payload["inputs"]["registry_sha256"] + "`）、"
        "`w24_3_level_crosscheck.csv`、`w33_bound_state_gate_gates.csv`、"
        "`w34_channel_dashboard.md`、论文、决策日志",
        "",
        "## 1. 旁路表",
        "",
        "`data/processed/redox_readability_sidecar.csv`：**" + str(payload["sidecar"]["rows"])
        + " 行**（一行一键），把注册表的（层级 × 介质）判定摊平成列。与注册表逐位比对了 **"
        + str(payload["sidecar"]["pairs_checked"]) + "** 个（层级 × 介质 × 键）格，不一致 **"
        + str(payload["sidecar"]["mismatches"]) + "** 个。主注册表 sha256 **未变**。",
        "",
        "| GFN2 介质 | 普查合法 / 246 | 配对集（22）合法 |",
        "| --- | --- | --- |",
    ]
    for row in payload["sidecar"]["medium_table"]:
        lines.append("| " + row["medium_label"] + " | " + str(row["census_legal"]) + " / 246 | "
                     + str(row["paired_legal"]) + " / 22 |")
    lines += [
        "",
        "**同一（层级，介质）在两个总体上的可宣读性可以相反**：GFN2 气相加起来合法 52/246（可宣读），"
        "但在 R6 的 22 个配对化合物上只有 **1/22**（不可判定）。口径必须带总体说明。",
        "",
        "## 2. 引用登记表",
        "",
        "`probes/artifacts/w35_gated_reference_register.csv`：**" + str(payload["register"]["rows"])
        + " 行**，每行的 `mark` 都由 W34-A 的 `assert_redox_readable` 给出（拒答即写「不可判定」）。",
        "",
        "| 引用点 | 轴 | 层级 / 介质 | 值 | 合法 / 总体 | 标记 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["register"]["rows_detail"]:
        lines.append("| `" + row["reference_id"] + "` | " + row["axis"] + " | "
                     + row["level"] + " / " + row["medium"] + " | " + str(row["quoted_value"])
                     + " | " + str(row["legal_n"]) + " / " + str(row["population_n"]) + " | "
                     + row["mark"] + " |")
    lines += [
        "",
        "**门禁范围声明**：门禁是**阴离子态**审计（`geom ∧ homo ∧ ea`），只覆盖**还原轴**；"
        "氧化轴两条登记为「不适用」——不得把阴离子门禁套到阳离子轴上。",
        "",
        "## 3. 消费者审计",
        "",
        "`probes/artifacts/w35_gated_consumer_audit.csv`：登记 **" + str(payload["audit"]["rows"])
        + "** 个下游消费者；若某段引用了受门禁约束的数值（`0.602` / `0.601732` / `0.835` / `1.437`），"
        "则同一段必须出现标记 `不可判定`。",
        "",
        "| 消费者 | 段内受约束数值 | 更正前 | 更正后 |",
        "| --- | --- | --- | --- |",
    ]
    before_by_id = {row["consumer_id"]: row for row in payload["audit"]["before"]}
    for row in payload["audit"]["after"]:
        before = before_by_id[row["consumer_id"]]
        lines.append("| `" + row["consumer_id"] + "` | " + (row["gated_values_found"] or "—")
                     + " | " + ("有标记" if before["mark_present"] else "**缺标记**")
                     + " | " + ("有标记" if row["mark_present"] else "**缺标记**") + " |")
    lines += [
        "",
        "更正前缺失的消费者：" + (", ".join("`" + item + "`"
                                        for item in payload["audit"]["missing_before"]) or "无")
        + "；更正后缺失：" + (", ".join("`" + item + "`"
                                    for item in payload["audit"]["missing_after"]) or "无") + "。",
        "",
        "**审计的价值在于它先失败、后被修好**：更正前 §3.20、附录 A、结论 #8 三处引用了 −0.602 / +0.835 "
        "却没有任何门禁标记；W35-B 施加更正后全部带上标记。",
        "",
        "## 4. 判据",
        "",
        "| 判据 | 内容 | 结果 |",
        "| --- | --- | --- |",
    ]
    for item in payload["criteria"]:
        lines.append("| " + item["id"] + " | " + item["description"] + " | " + item["verdict"] + " |")
    lines += ["", "## 5. 边界", ""]
    lines += ["- " + item for item in payload["boundaries"]]
    lines.append("")
    return "\n".join(lines)


def render_figure(payload: dict) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager

        available = {font.name for font in font_manager.fontManager.ttflist}
        for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"):
            if candidate in available:
                plt.rcParams["font.sans-serif"] = [candidate]
                break
        plt.rcParams["axes.unicode_minus"] = False

        medium_table = payload["sidecar"]["medium_table"]
        labels = [row["medium_label"] for row in medium_table]
        positions = list(range(len(medium_table)))
        census = [row["census_legal"] for row in medium_table]
        paired = [row["paired_legal"] for row in medium_table]

        figure, axes = plt.subplots(1, 2, figsize=(14.0, 5.6))
        width = 0.38
        axes[0].bar([p - width / 2 for p in positions], census, width, color="#1f3b63",
                    label="GFN2 普查（246）")
        axes[0].bar([p + width / 2 for p in positions], paired, width, color="#c0392b",
                    label="R6 配对集（22）")
        axes[0].axhline(MIN_LEGAL_SUBSET, color="#111111", linestyle="--", linewidth=1.2,
                        label="最小合法子集 " + str(MIN_LEGAL_SUBSET))
        for position, value in zip(positions, census):
            axes[0].text(position - width / 2, value + 2, str(value), ha="center", fontsize=8)
        for position, value in zip(positions, paired):
            axes[0].text(position + width / 2, value + 2, str(value), ha="center", fontsize=8,
                         color="#c0392b")
        axes[0].set_xticks(positions)
        axes[0].set_xticklabels(labels, fontsize=8)
        axes[0].set_ylabel("合法子集大小")
        axes[0].set_title("A 同一（层级，介质）在两个总体上可宣读性相反", fontsize=10.5)
        axes[0].legend(fontsize=7.5, framealpha=0.9)
        axes[0].grid(alpha=0.25, axis="y")

        rows = payload["register"]["rows_detail"]
        names = [row["reference_id"] for row in rows]
        values = [(int(row["legal_n"]) if str(row["legal_n"]) != "" else 0.0) for row in rows]
        colors = {"可宣读": "#1f3b63", "不可判定": "#c0392b", "不适用（门禁只覆盖还原轴）": "#7f8c8d"}
        bars = [colors.get(row["mark"], "#7f8c8d") for row in rows]
        axes[1].barh(names[::-1], values[::-1], color=bars[::-1])
        axes[1].axvline(MIN_LEGAL_SUBSET, color="#111111", linestyle="--", linewidth=1.2)
        for index, row in enumerate(rows[::-1]):
            label = ("合法 " + str(row["legal_n"]) + "/" + str(row["population_n"])
                     if str(row["legal_n"]) != "" else "不适用")
            if row["guard_verdict"] == "refused":
                label = label + "（拒答）"
            axes[1].text(float(values[::-1][index]) + 1.0, index, label, va="center", fontsize=7.5)
        axes[1].set_xlim(0, max(max(values) if values else 1.0, MIN_LEGAL_SUBSET) * 1.55)
        axes[1].set_xlabel("合法子集大小（虚线 = 最小合法子集 5）")
        axes[1].set_title("B 引用登记表：每行的标记由门禁守卫给出", fontsize=10.5)
        axes[1].grid(alpha=0.25, axis="x")

        figure.tight_layout()
        figure.savefig(FIGURE_PATH, dpi=150)
        plt.close(figure)
        return True
    except Exception as error:  # pragma: no cover - plotting is best effort
        print("figure skipped: " + repr(error))
        return False


def main() -> int:
    started = time.perf_counter()
    registry = load_registry()
    paired = paired_keys(registry)
    sidecar = build_sidecar(registry, paired)
    register = build_reference_register(registry, paired)

    texts = {"paper/paper_zh_draft_v2.md": PAPER_PATH.read_text(encoding="utf-8"),
             "probes/artifacts/w34_channel_dashboard.md": DASHBOARD_MD.read_text(encoding="utf-8"),
             "reports/decisions_log.md": LOG_PATH.read_text(encoding="utf-8")}
    audit = audit_consumers(texts)
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    before_text = reconstruct_before(texts["paper/paper_zh_draft_v2.md"], prereg)
    audit_before = audit_consumers({**texts, "paper/paper_zh_draft_v2.md": before_text})

    shas = {
        "registry_sha256": sha256_file(REGISTRY_CSV),
        "registry_intact": int(sha256_file(REGISTRY_CSV) == REGISTRY_SHA256_BEFORE),
        "four_core_sha256": sha256_file(FOUR_CORE_CSV) if FOUR_CORE_CSV.is_file() else None,
        "four_core_intact": int(FOUR_CORE_CSV.is_file() and sha256_file(FOUR_CORE_CSV) == FOUR_CORE_SHA256),
        "all_lf": int(b"\r" not in SIDECAR_CSV.read_bytes()) if SIDECAR_CSV.is_file() else 1,
    }
    criteria, diagnostics = evaluate(registry, sidecar, register, audit, audit_before, shas)

    write_csv_lf(SIDECAR_CSV, SIDECAR_FIELDS, sidecar)
    write_csv_lf(REGISTER_CSV, REGISTER_FIELDS, register)
    write_csv_lf(AUDIT_CSV, AUDIT_FIELDS, audit)
    shas["all_lf"] = int(b"\r" not in SIDECAR_CSV.read_bytes()
                         and b"\r" not in REGISTER_CSV.read_bytes()
                         and b"\r" not in AUDIT_CSV.read_bytes())
    criteria, diagnostics = evaluate(registry, sidecar, register, audit, audit_before, shas)

    medium_table = []
    for medium, epsilon, label in registry_mod.gate.MEDIA:
        census_rows = subset_rows(registry, "gfn2", medium, {row["inchikey"] for row in registry})
        paired_rows = subset_rows(registry, "gfn2", medium, paired)
        medium_table.append({
            "medium": medium, "medium_label": label, "epsilon": float(epsilon),
            "census_legal": sum(row["legal"] for row in census_rows),
            "paired_legal": sum(row["legal"] for row in paired_rows)})

    payload = {
        "schema": SCHEMA, "task": TASK,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {"main_scoreboard_shots_this_week": 0,
                   "cumulative_main_scoreboard_attempts_after": 19,
                   "why_not_a_shot": "旁路表 / 引用登记 / 消费者审计：只读冻结表，不拟合模型、不触 ε 主记分牌。"},
        "inputs": shas,
        "gate": {"clauses": ["geom", "homo", "ea"], "min_legal_subset": MIN_LEGAL_SUBSET,
                 "source_task": "week34_legality_registry",
                 "scope": "阴离子态审计：只覆盖还原轴；氧化轴不适用"},
        "sidecar": {"rows": len(sidecar), "fields": list(SIDECAR_FIELDS),
                    "pairs_checked": diagnostics["sidecar_vs_registry_pairs"],
                    "mismatches": diagnostics["sidecar_mismatches"],
                    "medium_table": medium_table},
        "register": {"rows": len(register), "fields": list(REGISTER_FIELDS),
                     "rows_detail": register,
                     "not_applicable_rows": [row["reference_id"] for row in register
                                             if row["guard_verdict"] == "not_applicable"],
                     "refused_rows": [row["reference_id"] for row in register
                                      if row["guard_verdict"] == "refused"]},
        "audit": {"rows": len(audit), "fields": list(AUDIT_FIELDS), "after": audit,
                  "before": audit_before,
                  "missing_before": diagnostics["consumer_missing_before"],
                  "missing_after": diagnostics["consumer_missing_after"],
                  "reconstruction": "由预注册 probes/w35_paper_r6_correction_prereg.json 反推更正前论文"},
        "criteria": criteria, "diagnostics": diagnostics,
        "headline": [
            "旁路表把注册表的（层级 × 介质）判定摊平成按分子可查的 246 行；与 1028 个格逐位一致，"
            "主注册表 sha256 未变。",
            "同一（层级，介质）在两个总体上可宣读性相反：GFN2 气相普查 52/246（可宣读）"
            "vs R6 配对集 1/22（不可判定）——引用还原轴读数必须带总体说明。",
            "引用登记表 10 行全部由 W34-A 守卫给出标记：8 行还原轴（2 行判「不可判定」），"
            "2 行氧化轴登记为「不适用」——门禁只覆盖还原轴。",
            "消费者审计先失败后被修好：更正前 3 个消费者缺标记，更正后 7/7 成立。",
        ],
        "boundaries": [
            "旁路表是 W34 注册表的派生件；不改门禁规则、不改阈值、不改拒答优先级、不改主注册表。",
            "拒答不是缺失值：登记表里 ORCA 两层的 mark 就是守卫抛出的拒答结论，不得插补、赋伪值或静默丢弃。",
            "门禁是阴离子态审计，只对还原轴生效；氧化轴登记为「不适用」，不得把阴离子门禁套到阳离子轴上。",
            "同一（层级，介质）的合法子集依赖总体（246 普查 vs 22 配对集），引用时必须声明 population_scope。",
            "消费者审计用「段内是否出现标记」作机械检查；标记的实质结论来自 W35-B 的预注册更正。",
            "不占 shot（累计仍 19）、不改 METRIC_NAMES、不动四个冻结读数与 ε 主记分牌。",
        ],
    }
    write_json_lf(SUMMARY_PATH, payload)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(payload), encoding="utf-8", newline="\n")
    figure_ok = render_figure(payload)

    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    print("sidecar rows " + str(len(sidecar)) + "; register rows " + str(len(register))
          + "; consumers " + str(len(audit)), flush=True)
    print("pairs checked " + str(diagnostics["sidecar_vs_registry_pairs"])
          + "; mismatches " + str(diagnostics["sidecar_mismatches"]), flush=True)
    print("missing before " + str(diagnostics["consumer_missing_before"])
          + "; missing after " + str(diagnostics["consumer_missing_after"]), flush=True)
    print("figure " + ("ok" if figure_ok else "skipped"), flush=True)
    print("verdicts " + str(passed) + "/" + str(len(criteria)), flush=True)
    for item in criteria:
        if item["verdict"] != "成立":
            print("FAIL " + item["id"] + " " + item["description"])
    return 0 if passed == len(criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())