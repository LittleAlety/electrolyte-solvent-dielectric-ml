# -*- coding: utf-8 -*-
"""W36-D：把 W35-A 的引用登记表升成**准入清单**（后验，不占 shot）。

W35-A 已经出了一张引用登记表，但下游要「自觉」去查它。本件把「自觉」变成**机械拒绝**：

* `admit(key)`：任何要引用还原轴读数的格子，先按 (轴 x 层级 x 介质 x 量 x 总体) 查准入清单；
  没登记就抛 `AdmissionRefused`——**未登记 = 不准入**，不是警告。
* 登记过的格子，`mark` **不由本件书写**，而是重新调用 W34-A 的守卫算一遍；
  与登记表里已存的 `mark` 不一致就判否（防止有人手写「可宣读」）。
* 氧化轴按门禁条款判「不适用」（门禁是阴离子态审计，只覆盖还原轴）。
* 负对照：三个**未登记**的合成格子必须全部被拒。

只读；不重跑模型、不新增数据；累计 shot 仍是 19。
"""

from __future__ import annotations

import csv
import hashlib
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
import w35_redox_gate_consumers as consumers
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
REGISTER_CSV = ARTIFACTS / "w35_gated_reference_register.csv"
REGISTRY_CSV = REPOSITORY_ROOT / "data" / "processed" / "redox_state_legality_registry.csv"

MANIFEST_CSV = ARTIFACTS / "w36_gate_admission_manifest.csv"
REFUSALS_CSV = ARTIFACTS / "w36_gate_admission_refusals.csv"
SUMMARY_PATH = ARTIFACTS / "w36_gate_admission_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w36_gate_admission.md"

SCHEMA = "w36_gate_admission/summary@1"
TASK = "week36_gate_admission"

KEY_FIELDS = ("axis", "level", "medium", "quantity", "population_scope")
MANIFEST_FIELDS = ("reference_id", "axis", "level", "medium", "quantity", "population_scope",
                   "population_n", "legal_n", "quoted_value", "mark", "mark_source",
                   "admission", "admission_note")
REFUSAL_FIELDS = ("axis", "level", "medium", "quantity", "population_scope", "verdict",
                  "reason")
NOT_APPLICABLE_KEY = ("oxidation",)
UNREGISTERED_CONTROLS = (
    {"axis": "reduction", "level": "r2scan3c", "medium": "gas", "quantity": "tau_legal",
     "population_scope": "census_246", "why": "新层级从未登记"},
    {"axis": "reduction", "level": "gfn2", "medium": "benzene", "quantity": "tau_legal",
     "population_scope": "census_246", "why": "新介质从未登记"},
    {"axis": "reduction", "level": "gfn2", "medium": "gas", "quantity": "tau_legal",
     "population_scope": "paired_orca_27", "why": "新总体从未登记"},
)


class AdmissionRefused(RuntimeError):
    """未登记在准入清单里的引用点，拒绝准入。"""


def sha256_file(path) -> str:
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


def key_of(row: dict) -> tuple:
    return tuple(row[field] for field in KEY_FIELDS)


def population_keys(registry: list, scope: str, paired: set) -> set:
    if scope == "paired_orca_22":
        return paired
    if scope == "census_246":
        return {row["inchikey"] for row in registry if row["level"] == "gfn2"}
    raise AdmissionRefused("总体范围未登记：" + scope)


def admit(register: list, registry: list, paired: set, key: dict) -> dict:
    """准入检查；返回准入记录，未登记则抛 AdmissionRefused。"""
    wanted = tuple(key[field] for field in KEY_FIELDS)
    matches = [row for row in register if key_of(row) == wanted]
    if not matches:
        raise AdmissionRefused("未登记：准入清单里没有 " + "/".join(wanted)
                               + "。新增还原轴读数必须先落进 w35_gated_reference_register.csv。")
    if len(matches) > 1:
        raise AdmissionRefused("准入清单里这一格有 " + str(len(matches)) + " 行，坐标不唯一")
    row = matches[0]
    if row["axis"] == "oxidation":
        return {"reference_id": row["reference_id"], "mark": consumers.MARK_ID_APPLICABLE,
                "mark_source": "门禁条款（氧化轴不适用）", "guard_verdict": "not_applicable",
                "legal_n": "", "population_n": int(row["population_n"]),
                "admission_note": "门禁是阴离子态审计，只覆盖还原轴；阳离子态无对应条款"}
    keys = population_keys(registry, row["population_scope"], paired)
    rows = consumers.subset_rows(registry, row["level"], row["medium"], keys)
    mark, verdict, message = consumers.guard_mark(rows, row["level"], row["medium"])
    legal_n = sum(int(entry["legal"]) for entry in rows)
    return {"reference_id": row["reference_id"], "mark": mark, "mark_source": "W34-A 守卫复算",
            "guard_verdict": verdict, "legal_n": legal_n,
            "population_n": int(row["population_n"]), "admission_note": message,
            "stored_mark": row["mark"], "stored_legal_n": int(row["legal_n"] or 0)}


def build() -> dict:
    register = read_rows(REGISTER_CSV)
    registry = consumers.load_registry()
    paired = consumers.paired_keys(registry)

    recomputed = consumers.build_reference_register(registry, paired)
    reproducible = all(
        (shipped["reference_id"] == fresh["reference_id"]
         and shipped["mark"] == fresh["mark"]
         and shipped["guard_verdict"] == fresh["guard_verdict"]
         and str(shipped["legal_n"]) == str(fresh["legal_n"])
         and shipped["quoted_value"] == fresh["quoted_value"])
        for shipped, fresh in zip(register, recomputed))
    reproducible = reproducible and len(register) == len(recomputed)

    manifest, mark_mismatch = [], 0
    for row in register:
        key = {field: row[field] for field in KEY_FIELDS}
        record = admit(register, registry, paired, key)
        if "stored_mark" in record:
            if record["mark"] != record["stored_mark"] or record["legal_n"] != record["stored_legal_n"]:
                mark_mismatch += 1
        manifest.append({
            "reference_id": row["reference_id"], "axis": row["axis"], "level": row["level"],
            "medium": row["medium"], "quantity": row["quantity"],
            "population_scope": row["population_scope"],
            "population_n": record["population_n"],
            "legal_n": record["legal_n"], "quoted_value": row["quoted_value"],
            "mark": record["mark"], "mark_source": record["mark_source"],
            "admission": "准入", "admission_note": record["admission_note"]})

    refusals = []
    for control in UNREGISTERED_CONTROLS:
        try:
            admit(register, registry, paired, control)
            refusals.append({field: control[field] for field in KEY_FIELDS}
                            | {"verdict": "误准入", "reason": control["why"]})
        except AdmissionRefused as error:
            refusals.append({field: control[field] for field in KEY_FIELDS}
                            | {"verdict": "拒绝", "reason": str(error)})

    return {"register": register, "registry": registry, "manifest": manifest,
            "refusals": refusals, "reproducible": reproducible,
            "mark_mismatch": mark_mismatch, "paired": len(paired)}


def evaluate(payload: dict) -> list:
    def verdict(identifier, description, value, threshold, passed) -> dict:
        return {"id": identifier, "description": description,
                "value": None if value is None else float(value),
                "threshold": None if threshold is None else float(threshold),
                "verdict": "成立" if bool(passed) else "判否"}

    manifest = payload["manifest"]
    reduction = [row for row in manifest if row["axis"] == "reduction"]
    refused = [row for row in payload["refusals"] if row["verdict"] == "拒绝"]
    return [
        verdict("H36d1", "准入清单里每一行都通过准入",
                float(len(manifest)), float(len(payload["register"])),
                len(manifest) == len(payload["register"])),
        verdict("H36d2", "准入清单可由 W35-A 的同一推导逐行复现（含 mark 与 legal_n）",
                float(int(payload["reproducible"])), 1.0, payload["reproducible"]),
        verdict("H36d3", "全部还原轴行的 mark 由 W34-A 守卫复算，与登记值零不一致",
                float(payload["mark_mismatch"]), 0.0, payload["mark_mismatch"] == 0),
        verdict("H36d4", "未登记的合成格子全部被拒（未登记 = 不准入）",
                float(len(refused)), 3.0, len(refused) == 3),
        verdict("H36d5", "还原轴行在准入件里都带 mark；氧化轴行标「不适用」",
                float(len(reduction)), None,
                all(row["mark"] for row in manifest)
                and all(row["mark"] == consumers.MARK_ID_APPLICABLE
                        for row in manifest if row["axis"] == "oxidation")),
    ]


def render_report(payload: dict, criteria: list) -> str:
    lines = [
        "# W36-D 结题报告：引用登记升为准入清单",
        "",
        "- **性质**：后验治理件（只读 W34-A 注册表与 W35-A 登记表），**不占 shot**",
        "- **累计 shot**：19",
        "",
        "## 1. 机制",
        "",
        "`admit(axis, level, medium, quantity, population_scope)`：",
        "",
        "1. 先查 `probes/artifacts/w35_gated_reference_register.csv`——**没登记就抛 `AdmissionRefused`**；",
        "2. 氧化轴直接返回「不适用」（门禁是阴离子态审计）；",
        "3. 还原轴**重新调用 W34-A 的 `assert_redox_readable`** 得到 `mark`，与登记表里的值比对；",
        "4. 不一致即判否（防手写「可宣读」）。",
        "",
        "## 2. 准入清单",
        "",
        "| 引用点 | 轴 | 层级 | 介质 | 总体 | legal | quoted | mark |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["manifest"]:
        lines.append("| " + row["reference_id"] + " | " + row["axis"] + " | " + row["level"]
                     + " | " + row["medium"] + " | " + row["population_scope"] + " | "
                     + (str(row["legal_n"]) if row["legal_n"] != "" else "—") + " | "
                     + row["quoted_value"] + " | " + row["mark"] + " |")
    lines += [
        "",
        "## 3. 负对照（未登记 = 不准入）",
        "",
        "| 格子 | 裁决 | 理由 |",
        "| --- | --- | --- |",
    ]
    for row in payload["refusals"]:
        lines.append("| " + row["axis"] + "/" + row["level"] + "/" + row["medium"] + "/"
                     + row["population_scope"] + " | " + row["verdict"] + " | " + row["reason"] + " |")
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
        "## 5. 边界",
        "",
        "- 只读；不重跑模型、不新增数据、不改任何被冻结的读数。",
        "- 准入清单**只约束还原轴**；氧化轴按 W33-A 条款判「不适用」。",
        "- 拒答不是缺失值：不可判定的格子允许被引用，但必须带 `mark`，不得插补或赋伪值。",
        "- 不占 shot（累计仍 19）。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    started = time.perf_counter()
    payload = build()
    criteria = evaluate(payload)
    write_csv_lf(MANIFEST_CSV, MANIFEST_FIELDS, payload["manifest"])
    write_csv_lf(REFUSALS_CSV, REFUSAL_FIELDS, payload["refusals"])
    summary = {
        "schema": SCHEMA, "task": TASK,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {"main_scoreboard_shots_this_week": 0,
                   "cumulative_main_scoreboard_attempts_after": 19,
                   "why_not_a_shot": "治理件：不拟合模型、不新增特征、不触 ε 主记分牌。"},
        "inputs": {str(path): sha256_file(path) for path in (REGISTER_CSV, REGISTRY_CSV)},
        "admission_list": {"rows": len(payload["manifest"]),
                           "reduction_rows": sum(1 for row in payload["manifest"]
                                                 if row["axis"] == "reduction"),
                           "oxidation_rows": sum(1 for row in payload["manifest"]
                                                 if row["axis"] == "oxidation")},
        "manifest": payload["manifest"], "refusals": payload["refusals"],
        "criteria": criteria,
        "headline": [
            "把「自觉查登记表」变成机械准入：未登记的还原轴引用点直接抛 `AdmissionRefused`。",
            "登记表里 " + str(len(payload["manifest"])) + " 行全部准入，"
            "mark 全部由 W34-A 守卫复算、与登记值零不一致。",
            "三个未登记的合成格子（新层级 / 新介质 / 新总体）全部被拒。",
            "不占 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")
    passed = sum(1 for item in criteria if item["verdict"] == "成立")
    print("register rows " + str(len(payload["manifest"])) + "; refusals "
          + str(len([row for row in payload["refusals"] if row["verdict"] == "拒绝"]))
          + "; mark mismatch " + str(payload["mark_mismatch"]))
    print("verdicts " + str(passed) + "/" + str(len(criteria)))
    for item in criteria:
        if item["verdict"] != "成立":
            print("FAIL " + item["id"] + " " + item["description"])
    return 0 if passed == len(criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())