# -*- coding: utf-8 -*-
"""W46-A：还原轴候选描述符族的预注册比较（主线 lane，0 shot）。

预注册锁死的候选族：D0 裸 LUMO / D1 门禁过滤绝热 EA / D2 Li+ 耦合还原位移 / D3 溶剂化垂直 EA。
把每个候选放进 (候选 × 层) 网格，按门禁合法子集给 τb 与未解析占比；合法子集 < 5 的单元格判
「不可判定」（不给数值、不插补）。

Lane B 收口：盘上同装置还原锚点数 = 0 < N_min = 5 ⇒ 按 H46a2 主判据不执行，本件产出降级为
「不可判定 + Lane C 功效下限」，与 W33 ORCA 层先例同规格登记（不算失败）。

只读；不接主记分牌；累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w46_reduction_family.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

from export_results_common import write_json_stable
from w42_common import (
    ARTIFACTS,
    FROZEN_READINGS,
    criteria_row,
    pick_cjk_font,
    sha256_file,
    utc_now,
    write_csv_lf,
)
from tools.taub_power import mde, power, required_n

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w46_reduction_family_prereg.json"
W23_PATH = REPOSITORY_ROOT / "data" / "processed" / "w23_redox_dscf_layer.csv"
W24_PATH = REPOSITORY_ROOT / "data" / "processed" / "w24_condition_redox_layer.csv"
W24_2_PATH = REPOSITORY_ROOT / "data" / "processed" / "w24_2_orca_dft_layer.csv"
REGISTRY_PATH = REPOSITORY_ROOT / "data" / "processed" / "redox_state_legality_registry.csv"
ANCHOR_SUMMARY = ARTIFACTS / "w46_reduction_anchor_recon_summary.json"
POWER_SUMMARY = ARTIFACTS / "w46_taub_power_summary.json"
CANDIDATES_CSV = ARTIFACTS / "w46_reduction_family_candidates.csv"
TAU_CSV = ARTIFACTS / "w46_reduction_family_tau.csv"
FIGURE_PATH = ARTIFACTS / "w46_reduction_family.png"
SUMMARY_PATH = ARTIFACTS / "w46_reduction_family_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w46_reduction_family.md"

SCHEMA = "w46_reduction_family/summary@1"
TASK = "week46_reduction_family"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

Z_RESOLVE = 1.96
CANDIDATE_FIELDS = ("candidate", "layer", "n_available", "n_legal", "status", "source_columns")
TAU_FIELDS = ("layer", "descriptor_a", "descriptor_b", "n", "tau_b", "unresolved")


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w46-A prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def as_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def kendall_tau_b(source: np.ndarray, target: np.ndarray) -> float:
    from scipy import stats

    return float(stats.kendalltau(source, target, variant="b").statistic)


def unresolved_share(source: np.ndarray, target: np.ndarray) -> float:
    """未解析对占比（z = 1.96）：|Delta target| < z * |Delta shift| / sqrt(2)。"""
    n = int(source.size)
    if n < 2:
        return 0.0
    iu = np.triu_indices(n, 1)
    shift = target - source
    gap = np.abs(target[:, None] - target[None, :])[iu]
    spread = np.abs(shift[:, None] - shift[None, :])[iu]
    sigma = spread / math.sqrt(2.0)
    return float((gap < Z_RESOLVE * sigma).mean())


def legal_sets() -> dict[tuple[str, str], set[str]]:
    sets: dict[tuple[str, str], set[str]] = {}
    for row in read_rows(REGISTRY_PATH):
        key = (row["level"], row["medium"])
        if str(row["legal"]).strip().lower() in ("true", "1", "yes"):
            sets.setdefault(key, set()).add(row["inchikey"])
    return sets


def coverage_grid(prereg: Mapping[str, object]) -> list[dict[str, object]]:
    legal = legal_sets()
    w23 = {row["inchikey"]: row for row in read_rows(W23_PATH)}
    w24 = {row["inchikey"]: row for row in read_rows(W24_PATH)}
    w24_2 = read_rows(W24_2_PATH)
    legal_gas_gfn2 = legal.get(("gfn2", "gas"), set())
    legal_gas_orca = legal.get(("orca", "gas"), set())
    legal_smd_orca = legal.get(("orca", "smd_acetonitrile"), set())
    min_legal = int(prereg["gates"]["min_legal_subset"])

    rows: list[dict[str, object]] = []

    def add(candidate: str, layer: str, available: int, n_legal: int, source: str) -> None:
        status = "computable" if n_legal >= min_legal else "不可判定"
        rows.append({"candidate": candidate, "layer": layer, "n_available": available,
                     "n_legal": n_legal, "status": status, "source_columns": source})

    add("D0", "r2SCAN-3c", len(w24_2), len(w24_2), "w24_2_orca_dft_layer.csv::orca_gas_neutral_lumo_eV")
    add("D1", "r2SCAN-3c", len(w24_2), len(legal_gas_orca),
        "w24_2_orca_dft_layer.csv::orca_ea_gas_eV + 门禁")
    add("D2", "r2SCAN-3c", 0, 0, "无（需新 ORCA 单点）")
    add("D3", "r2SCAN-3c", len(w24_2), len(legal_smd_orca),
        "w24_2_orca_dft_layer.csv::orca_ea_smd_acetonitrile_eV + 门禁")
    add("D0", "GFN2", len(w23), len(w23), "w23_redox_dscf_layer.csv::gas_neutral_lumo_eV")
    add("D1", "GFN2", len(w23), len(legal_gas_gfn2), "w23_redox_dscf_layer.csv::ea_gas_eV + 门禁")
    add("D2", "GFN2", len(w24), len(legal_gas_gfn2 & set(w24)),
        "w24_condition_redox_layer.csv::c1_gas_ea_eV - ea_gas_eV")
    add("D3", "GFN2", 0, 0, "无（ddCOSMO 未做）")
    return rows


def directional_tau(prereg: Mapping[str, object]) -> list[dict[str, object]]:
    legal = legal_sets().get(("gfn2", "gas"), set())
    w23 = {row["inchikey"]: row for row in read_rows(W23_PATH)}
    w24 = {row["inchikey"]: row for row in read_rows(W24_PATH)}
    min_legal = int(prereg["gates"]["min_legal_subset"])

    d0, d1, d2, keys = [], [], [], []
    for key in sorted(legal):
        row = w23.get(key)
        complex_row = w24.get(key)
        if row is None or complex_row is None:
            continue
        lumo = as_float(row.get("gas_neutral_lumo_eV"))
        ea = as_float(row.get("ea_gas_eV"))
        c1_ea = as_float(complex_row.get("c1_gas_ea_eV"))
        if lumo is None or ea is None or c1_ea is None:
            continue
        d0.append(-lumo)
        d1.append(ea)
        d2.append(c1_ea - ea)
        keys.append(key)

    if len(keys) < min_legal:
        return []

    arrays = {"D0": np.asarray(d0), "D1": np.asarray(d1), "D2": np.asarray(d2)}
    rows: list[dict[str, object]] = []
    for left in ("D0", "D1", "D2"):
        for right in ("D0", "D1", "D2"):
            if left >= right:
                continue
            rows.append({"layer": "GFN2", "descriptor_a": left, "descriptor_b": right,
                         "n": len(keys), "tau_b": kendall_tau_b(arrays[left], arrays[right]),
                         "unresolved": unresolved_share(arrays[left], arrays[right])})
    return rows


def power_floor() -> dict[str, object]:
    return {
        "n": 7,
        "mde_at_n7": mde(7, 0.05, 0.8),
        "power_tau04": power(7, 0.4, 0.05),
        "power_tau06": power(7, 0.6, 0.05),
        "power_tau08": power(7, 0.8, 0.05),
        "n_min_tau04": required_n(0.4, 0.05, 0.8)["n_min"],
        "n_min_tau06": required_n(0.6, 0.05, 0.8)["n_min"],
        "n_min_tau08": required_n(0.8, 0.05, 0.8)["n_min"],
    }


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    anchor = json.loads(ANCHOR_SUMMARY.read_text(encoding="utf-8-sig"))
    n_anchors = int(anchor["n_anchors"])
    n_pairs = int(anchor["n_pairs_effective"])
    min_anchors = int(prereg["gates"]["min_anchors"])

    grid = coverage_grid(prereg)
    tau_rows = directional_tau(prereg)
    floor = power_floor()
    refusal = n_anchors < min_anchors

    return {"grid": grid, "tau_rows": tau_rows, "floor": floor, "n_anchors": n_anchors,
            "n_pairs_effective": n_pairs, "min_anchors": min_anchors,
            "refusal_branch": refusal, "executed": not refusal,
            "verdict_main": "不可判定" if refusal else "已执行"}


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    power = json.loads(POWER_SUMMARY.read_text(encoding="utf-8-sig"))
    floor = payload["floor"]
    tol = 1e-12
    floor_matches = (
        abs(float(floor["mde_at_n7"]) - float(power["mde_rows"][2]["mde"])) <= tol
        and abs(float(floor["power_tau06"])
                - float(power["retro_rows"][1]["power_continuous"])) <= tol)

    tau_rows = payload["tau_rows"]
    grid = payload["grid"]
    unresolved_ok = bool(tau_rows) and all(
        row["unresolved"] is not None for row in tau_rows)
    directional_ok = len(tau_rows) >= 3 and all(int(row["n"]) >= int(prereg["gates"]["min_legal_subset"])
                                                 for row in tau_rows)

    layer_tags = {str(row["candidate"]): str(row["layer"]) for row in grid}
    discipline_ok = all(cid in layer_tags for cid in ("D0", "D1", "D2", "D3")) and all(
        row["status"] in ("computable", "不可判定") for row in grid)

    d3_status = [str(row["status"]) for row in grid if row["candidate"] == "D3"]
    d3_registered = all(status == "不可判定" for status in d3_status) and bool(d3_status)

    executed = bool(payload["executed"])
    refusal = bool(payload["refusal_branch"])
    verdict_text = str(payload["verdict_main"])
    undecidable_marked = verdict_text == "不可判定"

    return [
        criteria_row("H46a1", "主判据（D1/D2/D3 相对 D0 的 Delta tau_b CI 至少一个 > 0）按 H46a2 不执行，登记为不可判定（不判否）",
                     {"executed": executed, "verdict": verdict_text, "n_anchors": payload["n_anchors"]},
                     {"refusal_branch": "H46a2", "must_not_be_registered_as_negative": True},
                     (not executed) and undecidable_marked and refusal),
        criteria_row("H46a2", "拒答分支条件：锚点 < N_min = 5 且 n_pairs < 10",
                     {"n_anchors": payload["n_anchors"], "n_pairs_effective": payload["n_pairs_effective"],
                      "min_anchors": payload["min_anchors"]},
                     {"n_min": 5, "n_pairs_min": 10},
                     refusal and int(payload["n_pairs_effective"]) < 10),
        criteria_row("H46a3", "层级纪律核验：(候选 × 层) 网格四候选齐全，合法子集不足的格判不可判定，跨层只作对照",
                     {"grid": {str(row["candidate"]) + "@" + str(row["layer"]): row["status"]
                               for row in grid}},
                     {"same_layer_required": "r2SCAN-3c"}, discipline_ok),
        criteria_row("H46a4", "未解析对占比随 tau_b 同报（z = 1.96，二项口径）",
                     {"tau_rows": len(tau_rows),
                      "unresolved": [round(float(row["unresolved"]), 6) for row in tau_rows]},
                     {"unresolved_share_delta_max": prereg["gates"]["unresolved_share_delta_max"]},
                     unresolved_ok),
        criteria_row("H46a5", "功效下限表在位：n = 7 的 MDE 与功效与 Lane C 工具逐位一致（容差 1e-12）",
                     floor, {"lane_c_source": POWER_SUMMARY.name}, floor_matches),
        criteria_row("H46a6", "D3（ddCOSMO 溶剂化垂直 EA）未计算状态登记：需新 ORCA 单点，本轮不做",
                     {"D3_status": d3_status}, {"must_be_registered": True}, d3_registered),
        criteria_row("H46a7", "方向性读数可复算：GFN2 合法气相子集上 D0/D1/D2 两两 tau_b + 未解析占比",
                     {"pairs": [(row["descriptor_a"] + "-" + row["descriptor_b"]) for row in tau_rows],
                      "n": tau_rows[0]["n"] if tau_rows else 0},
                     {"min_legal_subset": prereg["gates"]["min_legal_subset"]}, directional_ok),
        criteria_row("H46a8", "输入（Lane A 预注册 + w23/w24/w24_2 + 合法性注册表 + Lane B/C 摘要）sha256 未变",
                     "before == after", True, True),
    ]


def render_figure(payload: Mapping[str, object], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    font = pick_cjk_font()
    if font:
        plt.rcParams["font.sans-serif"] = [font]
        plt.rcParams["axes.unicode_minus"] = False

    grid = payload["grid"]
    candidates = ("D0", "D1", "D2", "D3")
    layers = ("r2SCAN-3c", "GFN2")
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    width = 0.38
    positions = np.arange(len(candidates))
    for index, layer in enumerate(layers):
        values = []
        for candidate in candidates:
            cell = [row for row in grid if row["candidate"] == candidate and row["layer"] == layer]
            values.append(int(cell[0]["n_legal"]) if cell else 0)
        axes[0].bar(positions + (index - 0.5) * width, values, width, label=layer)
    axes[0].axhline(5, color="#c0504d", linestyle="--", linewidth=1.0)
    axes[0].set_xticks(positions)
    axes[0].set_xticklabels(candidates)
    axes[0].set_ylabel("门禁合法子集大小")
    axes[0].set_title("(候选 x 层) 合法子集：多处 < 5 判不可判定")
    axes[0].legend(fontsize=8)

    tau_rows = payload["tau_rows"]
    labels = [row["descriptor_a"] + "-" + row["descriptor_b"] for row in tau_rows]
    axes[1].bar(np.arange(len(tau_rows)) - 0.2, [float(row["tau_b"]) for row in tau_rows],
                0.4, label="tau_b")
    axes[1].bar(np.arange(len(tau_rows)) + 0.2, [float(row["unresolved"]) for row in tau_rows],
                0.4, label="未解析占比")
    axes[1].set_xticks(np.arange(len(tau_rows)))
    axes[1].set_xticklabels(labels)
    axes[1].set_title("GFN2 合法气相子集：方向性 tau_b 与未解析占比")
    axes[1].legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# W46-A 还原轴候选描述符族（不可判定 + 功效下限）")
    add("")
    add("只读主线 lane，0 shot。Lane B 收口：盘上同装置还原锚点 n_anchors = **"
        + str(payload["n_anchors"]) + "** < N_min = 5 ⇒ 主判据不执行，本件产出登记为**不可判定**"
        "（与 W33 ORCA 层先例同规格，不算失败）。")
    add("")
    add("## 1 (候选 × 层) 合法子集网格")
    add("")
    add("| 候选 | 层 | 可用 | 合法 | 状态 |")
    add("| --- | --- | --- | --- | --- |")
    for row in payload["grid"]:
        add("| " + str(row["candidate"]) + " | " + str(row["layer"]) + " | "
            + str(row["n_available"]) + " | " + str(row["n_legal"]) + " | " + str(row["status"]) + " |")
    add("")
    add("## 2 方向性读数（GFN2 合法气相子集）")
    add("")
    add("| 层 | A | B | n | tau_b | 未解析占比(z=1.96) |")
    add("| --- | --- | --- | --- | --- | --- |")
    for row in payload["tau_rows"]:
        add("| " + str(row["layer"]) + " | " + str(row["descriptor_a"]) + " | " + str(row["descriptor_b"])
            + " | " + str(row["n"]) + " | " + "%.4f" % float(row["tau_b"]) + " | "
            + "%.4f" % float(row["unresolved"]) + " |")
    add("")
    add("## 3 功效下限（Lane C）")
    add("")
    floor = payload["floor"]
    add("- Gate 1 的 n = 7：MDE = **" + "%.4f" % float(floor["mde_at_n7"]) + "**；"
        "功效 tau_true = 0.4 / 0.6 / 0.8 = **" + "%.4f" % float(floor["power_tau04"]) + " / "
        + "%.4f" % float(floor["power_tau06"]) + " / " + "%.4f" % float(floor["power_tau08"]) + "**。")
    add("- 达到 80% 功效所需锚点数：tau_true = 0.4 / 0.6 / 0.8 → **"
        + str(floor["n_min_tau04"]) + " / " + str(floor["n_min_tau06"]) + " / "
        + str(floor["n_min_tau08"]) + "**。")
    add("")
    add("![图 24 W46-A 合法子集与方向性读数](../probes/artifacts/w46_reduction_family.png)")
    add("")
    add("## 4 判据")
    add("")
    add("| id | 判据 | 值 | 阈 | 判决 |")
    add("| --- | --- | --- | --- | --- |")
    for row in criteria:
        add("| " + str(row["id"]) + " | " + str(row["description"]) + " | "
            + json.dumps(row["value"], ensure_ascii=False) + " | "
            + json.dumps(row["threshold"], ensure_ascii=False) + " | " + str(row["verdict"]) + " |")
    add("")
    add("> **不可判定**：锚点 0 < 5，主判据（Delta tau_b 的 bootstrap CI）不执行；方向性 tau_b 只作"
        "机制读法，不进判决。补足锚点的最小成本见 Lane C（tau_true = 0.6 需 n >= 8 个锚点）。")
    add("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只算不写盘")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [PREREG_PATH, W23_PATH, W24_PATH, W24_2_PATH, REGISTRY_PATH,
               ANCHOR_SUMMARY, POWER_SUMMARY]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria[-1] = criteria_row("H46a8", "输入（Lane A 预注册 + w23/w24/w24_2 + 合法性注册表 + Lane B/C 摘要）sha256 未变",
                                inputs_unchanged, True, bool(inputs_unchanged))
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(CANDIDATES_CSV, CANDIDATE_FIELDS, payload["grid"])
        write_csv_lf(TAU_CSV, TAU_FIELDS, payload["tau_rows"])
        render_figure(payload, FIGURE_PATH)
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只读描述符可行性计算与拒答登记，不拟合主记分牌臂、不新增特征列、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "coverage_grid": payload["grid"],
            "tau_rows": payload["tau_rows"],
            "power_floor": payload["floor"],
            "n_anchors": payload["n_anchors"],
            "n_pairs_effective": payload["n_pairs_effective"],
            "refusal_branch": payload["refusal_branch"],
            "main_judgment": payload["verdict_main"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "Lane B 锚点 = " + str(payload["n_anchors"]) + " < 5 ⇒ 主判据不可判定（不判否）。",
                "方向性：GFN2 合法气相子集 " + str(payload["tau_rows"][0]["n"] if payload["tau_rows"] else 0)
                + " 上 D0/D1/D2 两两 tau_b 与未解析占比已报。",
                "功效下限：n = 7 的 MDE = " + "%.4f" % float(payload["floor"]["mde_at_n7"]) + "；"
                "tau_true = 0.6 需 n >= " + str(payload["floor"]["n_min_tau06"]) + " 个锚点。",
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("anchors %d pairs %d refusal %s verdict %s | grid %s | tau_rows %d | mde7 %.4f"
          % (payload["n_anchors"], payload["n_pairs_effective"], payload["refusal_branch"],
             payload["verdict_main"], json.dumps({str(r["candidate"]) + "@" + str(r["layer"]): r["status"]
                                                  for r in payload["grid"]}),
             len(payload["tau_rows"]), float(payload["floor"]["mde_at_n7"])))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
