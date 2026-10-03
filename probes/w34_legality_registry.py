# -*- coding: utf-8 -*-
"""W34-A：还原轴态合法性注册表 + 四通道看板 + 门禁守卫（后验，不占 shot）。

W33-A 把态合法性做成了**前置门禁**，但判定只活在报告与 summary 里：下游若想引用
还原轴读数，盘上没有任何产物能强制它先过门禁。本轮把三件事补齐：

* **注册表**：对每个（层级 x 介质 x 分子）态落盘 `geom_ok / homo_bound / ea_positive /
  legal / reason`，共 246x4（GFN2）+ 22x2（ORCA 配对）= 1028 行；
* **守卫**：`assert_redox_readable` / `redox_reading` —— 合法子集 < 5 时**抛异常**
  （拒答），不返回 None 让调用方静默插补；
* **看板**：把 W32-A 的 s0 / N_pop / 最小信息预算、W33-A 的门禁状态并成一张跨通道入口表。

只读、不联网、不装依赖、不拟合模型；累计 shot 仍是 19。
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
import w24_3_posthoc as posthoc
import w33_bound_state_gate as gate
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


REDOX_LAYER = REPOSITORY_ROOT / "data" / "processed" / "w23_redox_dscf_layer.csv"
ORCA_LAYER = REPOSITORY_ROOT / "data" / "processed" / "w24_2_orca_dft_layer.csv"
GATE_SUMMARY = REPOSITORY_ROOT / "probes" / "artifacts" / "w33_bound_state_gate_summary.json"
GATE_GATES_CSV = REPOSITORY_ROOT / "probes" / "artifacts" / "w33_bound_state_gate_gates.csv"
RANK_JSON = REPOSITORY_ROOT / "probes" / "artifacts" / "w32_rank_stability.json"
NULL_BUDGET_CSV = REPOSITORY_ROOT / "probes" / "artifacts" / "w33_kendall_null_budget.csv"

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
REGISTRY_CSV = REPOSITORY_ROOT / "data" / "processed" / "redox_state_legality_registry.csv"
SUMMARY_PATH = ARTIFACTS / "w34_legality_registry_summary.json"
DASHBOARD_CSV = ARTIFACTS / "w34_channel_dashboard.csv"
DASHBOARD_MD = ARTIFACTS / "w34_channel_dashboard.md"
FIGURE_PATH = ARTIFACTS / "w34_legality_registry.png"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w34_legality_registry.md"

SCHEMA = "w34_legality_registry/summary@1"
TASK = "week34_legality_registry"
MIN_LEGAL_SUBSET = gate.MIN_LEGAL_SUBSET
KOOPMANS_COLUMN = gate.KOOPMANS_COLUMN
BUDGET_TARGET = 0.05

REGISTRY_FIELDS = ("level", "medium", "medium_label", "epsilon", "inchikey", "name",
                   "geom_ok", "homo_bound", "ea_positive", "legal", "reason",
                   "anion_homo_eV", "ea_eV")
DASHBOARD_FIELDS = ("channel", "label", "s0", "n_population", "sd_at_n12",
                    "min_n_for_sd_0_05", "gate_applies", "gate_status", "decidability", "note")
CHANNELS = ("dielectric", "viscosity", "orbital", "redox")

EXPECTED_INPUTS = {
    "data/processed/w23_redox_dscf_layer.csv":
        "d24d4c5a0937bbf971afb5d52f15038505f58e47d43c4ed8ebe44a07910d1b9f",
    "data/processed/w24_2_orca_dft_layer.csv":
        "c48a541d1a831f073cfd87810510f89c934a6f645a869880886518e1acc03246",
    "probes/artifacts/w33_bound_state_gate_summary.json":
        "c5519c719086d705b92d82c325a21bccd864376272babbed7530781685803f6d",
    "probes/artifacts/w33_bound_state_gate_gates.csv":
        "130a6f627c785b8f981d1e9246909a3fd663a2916643654a5e62fc0d7efc0542",
    "probes/artifacts/w32_rank_stability.json":
        "106983b41e84808b331043927df3aba9afc9addcebdf985d9845d4330e2e8e95",
    "probes/artifacts/w33_kendall_null_budget.csv":
        None,
}

# W33-A 的 τ_b 复现锚（同一函数、同一对列），守卫必须逐位给出同一个数。
ANCHOR_TAU_LEGAL_GAS = 0.7450980392156863
ANCHOR_TAU_LEGAL_WATER = 0.8119565217391304


class RedoxGateRefusal(RuntimeError):
    """合法子集不足，该（层级，介质）的还原轴读数不可宣读。"""


def read_rows(path) -> list:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def paired_orca_rows(census_rows, orca_rows) -> list:
    census = {row["inchikey"] for row in census_rows}
    return [row for row in orca_rows if row.get("inchikey") in census]


def build_registry(census_rows, orca_rows) -> list:
    rows = []
    for medium, epsilon, label in gate.MEDIA:
        for row in census_rows:
            flag = gate.census_gate(row, medium)
            rows.append({
                "level": "gfn2", "medium": medium, "medium_label": label,
                "epsilon": float(epsilon), "inchikey": row.get("inchikey", ""),
                "name": row.get("name", ""),
                "geom_ok": int(flag["geom"]), "homo_bound": int(flag["homo"]),
                "ea_positive": int(flag["ea"]), "legal": int(flag["legal"]),
                "reason": flag["reason"],
                "anion_homo_eV": row.get(medium + "_anion_homo_eV", ""),
                "ea_eV": row.get("ea_" + medium + "_eV", "")})
    for medium, epsilon, label in gate.ORCA_MEDIA:
        for row in paired_orca_rows(census_rows, orca_rows):
            flag = gate.orca_gate(row, medium)
            rows.append({
                "level": "orca", "medium": medium, "medium_label": label,
                "epsilon": float(epsilon), "inchikey": row.get("inchikey", ""),
                "name": row.get("name", ""),
                "geom_ok": int(flag["geom"]), "homo_bound": int(flag["homo"]),
                "ea_positive": int(flag["ea"]), "legal": int(flag["legal"]),
                "reason": flag["reason"],
                "anion_homo_eV": row.get("orca_" + medium + "_anion_homo_eV", ""),
                "ea_eV": row.get("orca_ea_" + medium + "_eV", "")})
    return rows


def medium_rows(registry, level, medium) -> list:
    return [row for row in registry if row["level"] == level and row["medium"] == medium]


def assert_redox_readable(registry, level, medium, min_legal: int = MIN_LEGAL_SUBSET) -> dict:
    """门禁守卫：合法子集 < min_legal 时抛 RedoxGateRefusal，绝不返回 None。"""
    rows = medium_rows(registry, level, medium)
    if not rows:
        raise RedoxGateRefusal("注册表里没有 level=" + level + " medium=" + medium)
    legal = sum(int(row["legal"]) for row in rows)
    if legal < min_legal:
        reasons = {}
        for row in rows:
            reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
        raise RedoxGateRefusal(
            level + "/" + medium + " 合法子集 " + str(legal) + " < " + str(min_legal)
            + "：不可判定（拒答；拒答不是缺失值，不得插补）。拒答构成 " + json.dumps(reasons, ensure_ascii=False))
    return {"level": level, "medium": medium, "rows": len(rows), "legal": legal}


def redox_reading(census_rows, orca_rows, level, medium) -> dict:
    """先过门禁、再算读数；两者是同一次调用，调用方无法绕过。"""
    registry = build_registry(census_rows, orca_rows)
    assert_redox_readable(registry, level, medium)
    if level == "gfn2":
        source = gate.KOOPMANS_COLUMN
        pairs = [(gate.negated(row, source), gate.as_float(row.get("ea_" + medium + "_eV")))
                 for row in census_rows
                 if gate.census_gate(row, medium)["legal"]]
    else:
        pairs = [(gate.as_float(row["p0_red_eV"]),
                  gate.as_float(row.get("orca_ea_" + medium + "_eV")))
                 for row in paired_orca_rows(census_rows, orca_rows)
                 if gate.orca_gate(row, medium)["legal"]]
    value, used = posthoc.kendall_tau_b(pairs)
    return {"level": level, "medium": medium, "legal": len(pairs),
            "tau_b": float(value), "rows": int(used), "verdict": "可宣读"}


def build_dashboard(registry, rank, budget_rows) -> list:
    budgets = {row["channel"]: float(row["required_n"]) for row in budget_rows
               if abs(float(row["target"]) - BUDGET_TARGET) < 1e-12}
    rows = []
    for entry in rank["channels"]:
        channel = entry["channel"]
        if channel not in CHANNELS:
            continue
        s0 = float(entry["s0_median"])
        n_pop = float(entry["n_population_median"])
        sd12 = s0 * pow(max(1.0 / 12.0 - 1.0 / n_pop, 0.0), 0.5)
        if channel == "redox":
            gas = medium_rows(registry, "gfn2", "gas")
            orca_gas = medium_rows(registry, "orca", "gas")
            legal = sum(int(row["legal"]) for row in gas)
            orca_legal = sum(int(row["legal"]) for row in orca_gas)
            applies = True
            status = ("GFN2 气相合法 " + str(legal) + "/" + str(len(gas))
                      + "；ORCA 气相合法 " + str(orca_legal) + "/" + str(len(orca_gas)))
            decidability = "GFN2 可宣读；ORCA 不可判定"
            note = "读数前必须调用 assert_redox_readable / redox_reading"
        else:
            applies = False
            status = "无门禁"
            decidability = "可宣读"
            note = "该通道无态合法性条款"
        rows.append({
            "channel": channel, "label": entry["label"], "s0": s0, "n_population": n_pop,
            "sd_at_n12": sd12, "min_n_for_sd_0_05": budgets.get(channel, ""),
            "gate_applies": int(applies), "gate_status": status,
            "decidability": decidability, "note": note})
    return rows


def evaluate(census_rows, orca_rows, registry, dashboard, gates_rows) -> list:
    def verdict(identifier, description, value, threshold, passed):
        return {"id": identifier, "description": description,
                "value": None if value is None else float(value),
                "threshold": None if threshold is None else float(threshold),
                "verdict": "成立" if bool(passed) else "判否"}

    expected_rows = len(gate.MEDIA) * len(census_rows) + len(gate.ORCA_MEDIA) * len(
        paired_orca_rows(census_rows, orca_rows))
    checks = [verdict(
        "H34a", "注册表规模：GFN2 四介质 x 246 + ORCA 两介质 x 22",
        len(registry), float(expected_rows), len(registry) == expected_rows)]

    mismatches = []
    for entry in gates_rows:
        level = "orca" if str(entry["medium"]).startswith("orca_") else "gfn2"
        medium = str(entry["medium"])[5:] if level == "orca" else str(entry["medium"])
        legal = sum(int(row["legal"]) for row in medium_rows(registry, level, medium))
        if legal != int(entry["legal"]):
            mismatches.append(entry["medium"])
    checks.append(verdict(
        "H34b", "注册表 legal 与 W33-A gates.csv 逐条一致（不一致的介质数）",
        float(len(mismatches)), 0.0, not mismatches))

    priority_ok = True
    for row in registry:
        geom, homo, ea, legal = (int(row["geom_ok"]), int(row["homo_bound"]),
                                 int(row["ea_positive"]), int(row["legal"]))
        if legal == 1:
            priority_ok = priority_ok and row["reason"] == ""
        elif not geom:
            priority_ok = priority_ok and row["reason"] == "geom"
        elif not homo:
            priority_ok = priority_ok and row["reason"] == "homo"
        else:
            priority_ok = priority_ok and row["reason"] == "ea"
        priority_ok = priority_ok and legal == int(geom and homo and ea)
    checks.append(verdict("H34c", "reason 优先级（geom > homo > ea）与 legal 合取一致",
                          0.0, 0.0, priority_ok))

    refused, allowed, tau_ok = False, False, False
    try:
        assert_redox_readable(registry, "orca", "gas")
    except RedoxGateRefusal:
        refused = True
    gas = redox_reading(census_rows, orca_rows, "gfn2", "gas")
    allowed = gas["legal"] == 52
    tau_ok = abs(gas["tau_b"] - ANCHOR_TAU_LEGAL_GAS) <= 1e-12
    water = redox_reading(census_rows, orca_rows, "gfn2", "water")
    tau_ok = tau_ok and abs(water["tau_b"] - ANCHOR_TAU_LEGAL_WATER) <= 1e-12
    checks.append(verdict("H34d", "守卫行为：ORCA 气相抛拒答 / GFN2 气相放行且 τ_b 复现 W33-A",
                          1.0 if (refused and allowed and tau_ok) else 0.0, 1.0,
                          refused and allowed and tau_ok))

    channels = {row["channel"] for row in dashboard}
    redox_rows = [row for row in dashboard if row["channel"] == "redox"]
    dashboard_ok = (channels == set(CHANNELS) and len(redox_rows) == 1
                    and redox_rows[0]["gate_applies"] == 1
                    and str(redox_rows[0]["gate_status"]).startswith("GFN2 气相合法"))
    checks.append(verdict("H34e", "看板四通道齐备且 redox 行带门禁状态", 0.0, 0.0, dashboard_ok))
    return checks


def write_csv(path, fieldnames, rows) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def dump_json(path, payload) -> None:
    write_json_stable(Path(path), payload)


def fmt(value, digits=6) -> str:
    if value is None or value == "":
        return "——"
    return format(float(value), "." + str(digits) + "f")


def format_dashboard_md(dashboard, checks) -> str:
    lines = []
    add = lines.append
    add("# W34 四通道看板（由 `probes/w34_legality_registry.py` 生成）")
    add("")
    add("| 通道 | s0（中位） | N_pop | sd@N=12 | 使 sd <= 0.05 所需 N | 门禁 | 可否宣读 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for row in dashboard:
        add("| " + str(row["label"]) + " | " + fmt(row["s0"], 4) + " | "
            + fmt(row["n_population"], 0) + " | " + fmt(row["sd_at_n12"], 6) + " | "
            + (fmt(row["min_n_for_sd_0_05"], 1) if row["min_n_for_sd_0_05"] != "" else "——")
            + " | " + ("是" if int(row["gate_applies"]) else "否") + " | "
            + str(row["decidability"]) + " |")
    add("")
    add("门禁状态（redox）：" + str(next(row["gate_status"] for row in dashboard
                                          if row["channel"] == "redox")))
    add("")
    add("判据：" + "、".join(item["id"] + " " + item["verdict"] for item in checks))
    return "\n".join(lines) + "\n"


def format_report(payload) -> str:
    lines = []
    add = lines.append
    add("# W34-A：还原轴态合法性注册表 + 四通道看板 + 门禁守卫")
    add("")
    add("**性质**：后验注册表/看板（只读四张冻结表）。**不占主记分牌 shot**（累计仍 "
        + str(payload["ledger"]["cumulative_main_scoreboard_attempts_after"])
        + "）；不重跑 xTB / ORCA、不拟合模型、不联网。")
    add("")
    add("## 0. 一句话")
    add("")
    for line in payload["headline"]:
        add("- " + line)
    add("")
    add("## 1. 注册表（`data/processed/redox_state_legality_registry.csv`）")
    add("")
    add("| 层级 | 介质 | eps | 行数 | 合法 | 因几何 | 因不束缚 | 因 EA 非正 |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for entry in payload["register"]:
        add("| " + entry["level"] + " | " + entry["medium_label"] + " | "
            + fmt(entry["epsilon"], 1) + " | " + str(entry["rows"]) + " | "
            + str(entry["legal"]) + " | " + str(entry["geom_fail"]) + " | "
            + str(entry["homo_refused"]) + " | " + str(entry["ea_refused"]) + " |")
    add("")
    add("- 关键不变量：`legal == geom_ok AND homo_bound AND ea_positive`；`reason` 按 geom > homo > ea 取首个失败条款。")
    add("- 拒答不是缺失值：拒答 = 「在本层不可宣读」的明确结论，不得插补、不得赋伪值、不得静默丢弃。")
    add("")
    add("## 2. 门禁守卫")
    add("")
    add("```python")
    add("from w34_legality_registry import redox_reading, RedoxGateRefusal")
    add("reading = redox_reading(census_rows, orca_rows, 'gfn2', 'gas')   # 合法 52 >= 5 -> 返回读数")
    add("redox_reading(census_rows, orca_rows, 'orca', 'gas')             # 合法 0 < 5 -> raise RedoxGateRefusal")
    add("```")
    add("")
    add("- 守卫与读数在**同一次调用**里，调用方无法绕过门禁；拒答时抛异常，不返回 None。")
    add("- 复现锚：`gfn2/gas` 合法子集 τ_b = " + fmt(ANCHOR_TAU_LEGAL_GAS, 13)
        + "、`gfn2/water` = " + fmt(ANCHOR_TAU_LEGAL_WATER, 13) + "（与 W33-A 逐位一致）。")
    add("")
    add("## 3. 四通道看板")
    add("")
    add("| 通道 | s0 | N_pop | sd@N=12 | 所需 N（sd<=0.05） | 门禁 | 可否宣读 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for row in payload["dashboard"]:
        add("| " + str(row["label"]) + " | " + fmt(row["s0"], 4) + " | "
            + fmt(row["n_population"], 0) + " | " + fmt(row["sd_at_n12"], 6) + " | "
            + (fmt(row["min_n_for_sd_0_05"], 1) if row["min_n_for_sd_0_05"] != "" else "——")
            + " | " + ("是" if int(row["gate_applies"]) else "否") + " | "
            + str(row["decidability"]) + " |")
    add("")
    add("## 4. 判据（H34a–H34e）")
    add("")
    for item in payload["criteria"]:
        add("- **" + item["id"] + " " + item["verdict"] + "**：" + item["description"]
            + "（读数 " + fmt(item["value"]) + " 对阈值 " + fmt(item["threshold"]) + "）。")
    add("")
    add("## 5. 口径与边界")
    add("")
    for line in payload["boundaries"]:
        add("- " + line)
    add("")
    add("## 6. 产物与复算")
    add("")
    add("- `probes/w34_legality_registry.py`、`data/processed/redox_state_legality_registry.csv`、"
        "`probes/artifacts/w34_legality_registry_summary.json`、`probes/artifacts/w34_channel_dashboard.csv`、"
        "`probes/artifacts/w34_channel_dashboard.md`、`probes/artifacts/w34_legality_registry.png`、"
        "`reports/w34_legality_registry.md`")
    add("- 复算：`python probes\\w34_legality_registry.py`（零网络、零新算力，约数秒）。")
    return "\n".join(lines) + "\n"


def render_figure(payload) -> bool:
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

        entries = payload["register"]
        labels = [entry["level"].upper() + "\n" + entry["medium_label"] for entry in entries]
        positions = list(range(len(entries)))
        legal = [entry["legal"] / entry["rows"] for entry in entries]
        homo = [entry["homo_refused"] / entry["rows"] for entry in entries]
        ea_ref = [entry["ea_refused"] / entry["rows"] for entry in entries]
        geom = [entry["geom_fail"] / entry["rows"] for entry in entries]

        figure, axes = plt.subplots(1, 2, figsize=(14.0, 5.4))
        axes[0].bar(positions, legal, color="#1f3b63", label="合法（可宣读）")
        axes[0].bar(positions, homo, bottom=legal, color="#c0392b", label="拒答：阴离子不束缚")
        axes[0].bar(positions, ea_ref, bottom=[a + b for a, b in zip(legal, homo)],
                    color="#e67e22", label="拒答：EA 非正")
        axes[0].bar(positions, geom, bottom=[a + b + c for a, b, c in zip(legal, homo, ea_ref)],
                    color="#7f8c8d", label="拒答：几何/SCF 失败")
        for position, entry in zip(positions, entries):
            axes[0].text(position, entry["legal"] / entry["rows"] / 2,
                         str(entry["legal"]), ha="center", va="center", fontsize=7.5, color="white")
        axes[0].set_xticks(positions)
        axes[0].set_xticklabels(labels, fontsize=7)
        axes[0].set_ylim(0, 1.0)
        axes[0].set_ylabel("占比")
        axes[0].set_title("A 态合法性注册表：合法集 / 三类拒答（含 ORCA 配对层）", fontsize=10.5)
        axes[0].legend(fontsize=7, loc="lower left", framealpha=0.9)
        axes[0].grid(alpha=0.25, axis="y")

        dash = payload["dashboard"]
        names = [row["label"] for row in dash]
        budgets = [float(row["min_n_for_sd_0_05"]) for row in dash]
        colors = ["#c0392b" if int(row["gate_applies"]) else "#1f3b63" for row in dash]
        axes[1].barh(names, budgets, color=colors)
        for index, row in enumerate(dash):
            axes[1].text(float(row["min_n_for_sd_0_05"]) * 1.02, index,
                         "s0=" + fmt(row["s0"], 3), va="center", fontsize=8)
        axes[1].set_xlabel("使 sd <= 0.05 所需 N（W33-B 预算）")
        axes[1].set_title("B 四通道最小信息预算（红 = 该通道有态合法性门禁）", fontsize=10.5)
        axes[1].grid(alpha=0.25, axis="x")
        axes[1].set_xlim(0, max(budgets) * 1.25)

        figure.tight_layout()
        figure.savefig(FIGURE_PATH, dpi=150)
        plt.close(figure)
        return True
    except Exception as error:  # pragma: no cover - plotting is best effort
        print("figure skipped: " + repr(error))
        return False


def main() -> int:
    started = time.perf_counter()
    inputs = []
    for relative, expected in EXPECTED_INPUTS.items():
        path = REPOSITORY_ROOT / relative
        measured = sha256_file(path) if path.is_file() else None
        if expected is not None and measured != expected:
            print("input moved: " + relative)
            return 1
        inputs.append({"path": relative, "sha256": measured, "pinned": expected is not None})

    census_rows = read_rows(REDOX_LAYER)
    orca_rows = read_rows(ORCA_LAYER)
    gates_rows = read_rows(GATE_GATES_CSV)
    rank = json.loads(RANK_JSON.read_text(encoding="utf-8"))
    budget_rows = read_rows(NULL_BUDGET_CSV)

    registry = build_registry(census_rows, orca_rows)
    dashboard = build_dashboard(registry, rank, budget_rows)
    checks = evaluate(census_rows, orca_rows, registry, dashboard, gates_rows)

    register = []
    for level, media in (("gfn2", gate.MEDIA), ("orca", gate.ORCA_MEDIA)):
        for medium, epsilon, label in media:
            rows = medium_rows(registry, level, medium)
            register.append({
                "level": level, "medium": medium, "medium_label": label, "epsilon": float(epsilon),
                "rows": len(rows), "legal": sum(int(row["legal"]) for row in rows),
                "geom_fail": sum(1 for row in rows if not int(row["geom_ok"])),
                "homo_refused": sum(1 for row in rows
                                    if int(row["geom_ok"]) and not int(row["homo_bound"])),
                "ea_refused": sum(1 for row in rows if int(row["geom_ok"]) and int(row["homo_bound"])
                                  and not int(row["ea_positive"]))})

    gas = next(entry for entry in register if entry["level"] == "gfn2" and entry["medium"] == "gas")
    redox_dash = next(row for row in dashboard if row["channel"] == "redox")
    headline = [
        "**门禁从报告里的表升成盘上的权威列**：注册表 " + str(len(registry)) + " 行 = GFN2 "
        + str(len(gate.MEDIA)) + " x " + str(len(census_rows)) + " + ORCA 配对 "
        + str(len(gate.ORCA_MEDIA)) + " x " + str(len(paired_orca_rows(census_rows, orca_rows))) + "。",
        "**守卫与读数在同一次调用**：`redox_reading` 先过门禁再算 τ_b，合法 < 5 抛 `RedoxGateRefusal`，"
        "不返回 None —— 下游无法绕过门禁，也无法把拒答当缺失值插补。",
        "**看板把四通道并成一张入口表**：介电 s0 = " + fmt(dash_s0(dashboard, "dielectric"), 4)
        + "、黏度 " + fmt(dash_s0(dashboard, "viscosity"), 4)
        + "、轨道 " + fmt(dash_s0(dashboard, "orbital"), 4)
        + "、氧化还原 " + fmt(dash_s0(dashboard, "redox"), 4) + "；只有氧化还原通道带门禁（"
        + str(redox_dash["gate_status"]) + "）。",
        "**气相合法率仍是那 21.1%**（" + str(gas["legal"]) + "/" + str(gas["rows"])
        + "）：门禁不是新算力，它只是把 W33-A 的判定钉在盘上，让「还原轴必须先在定义域内」成为可执行约束。",
    ]

    payload = {
        "schema": SCHEMA, "task": TASK,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {"main_scoreboard_shots_this_week": 0,
                   "cumulative_main_scoreboard_attempts_after": 19,
                   "why_not_a_shot": "注册表/看板/守卫：把既有判定固化为产物，不拟合模型、不触 ε 主记分牌。"},
        "inputs": inputs,
        "gate": {"clauses": ["geom", "homo", "ea"], "min_legal_subset": MIN_LEGAL_SUBSET,
                 "source_task": "week33_bound_state_gate"},
        "register": register, "dashboard": dashboard, "criteria": checks, "headline": headline,
        "anchors": {"gfn2_gas_tau_legal": ANCHOR_TAU_LEGAL_GAS,
                    "gfn2_water_tau_legal": ANCHOR_TAU_LEGAL_WATER},
        "boundaries": [
            "注册表逐位派生自冻结表与 W33-A 预注册门禁；不改门禁规则、不改阈值、不改拒答优先级。",
            "拒答不是缺失值：守卫抛错是「在本层不可宣读」的明确结论，不得插补、不得赋伪值、不得静默丢弃。",
            "跨层级只在配对集上比裁决一致性，不把两层数值结果混在同一张记分牌上。",
            "不改 METRIC_NAMES、不新增特征列、不动四个冻结读数与 ε 主记分牌。",
            "本件是后验注册表/看板，不占 shot、不得当作预注册结论引用。",
        ],
    }

    write_csv(REGISTRY_CSV, REGISTRY_FIELDS, registry)
    write_csv(DASHBOARD_CSV, DASHBOARD_FIELDS, dashboard)
    DASHBOARD_MD.write_text(format_dashboard_md(dashboard, checks), encoding="utf-8", newline="\n")
    dump_json(SUMMARY_PATH, payload)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(format_report(payload), encoding="utf-8", newline="\n")
    figure_ok = render_figure(payload)

    passed = sum(1 for item in checks if item["verdict"] == "成立")
    print("registry rows " + str(len(registry)) + " (gfn2 " + str(len(registry) - len(gate.ORCA_MEDIA) * len(paired_orca_rows(census_rows, orca_rows))) + ")", flush=True)
    print("dashboard " + " | ".join(row["channel"] + " s0=" + fmt(row["s0"], 4) for row in dashboard), flush=True)
    print("wrote " + str(REGISTRY_CSV.relative_to(REPOSITORY_ROOT)).replace("\\", "/"), flush=True)
    print("figure " + ("ok" if figure_ok else "skipped"), flush=True)
    print("verdicts " + str(passed) + "/" + str(len(checks)), flush=True)
    return 0


def dash_s0(dashboard, channel):
    return next(row["s0"] for row in dashboard if row["channel"] == channel)


if __name__ == "__main__":
    raise SystemExit(main())