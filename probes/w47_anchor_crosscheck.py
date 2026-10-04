# -*- coding: utf-8 -*-
"""W47-A：计算锚点覆盖核算与氧化轴计算-实验交叉一致性（只读，0 shot）。

W47 计划把「还原轴该用哪个定义」升级为可执行判决，但取件核实（reports/w47_literature_verdict.md）
推翻了计划的 V1 归属：Borodin/Behl/Jow 2013 (JPCC) 是**纯氧化**论文（Table 1 计算氧化 16 行、
Table 3 实验氧化 26 行），全文无还原/EA 表；Borodin 2015 图 6/7/8 给的是 **Li+ 耦合还原**（计算）；
Moshkovich 2001 只有 PC 单溶剂。于是本 lane 执行两件事：

  * 覆盖核算：核心集 7 个溶剂上，计算氧化、实验氧化（单溶剂行）、计算还原、实验还原各算一遍成员表
    ⇒ 还原轨并集 2 < 5，**H47a2 拒答分支触发**，主判据不执行，降级为「不可判定 + 功效下限」。
  * 氧化轴交叉一致性（小样本敏感性读数）：n = 4 溶剂上计算 G4MP2 绝热氧化自由能（eps=20）对实验
    氧化电位，报 tau_b、Top-k 重叠、未解析占比三件套 + 精确单侧 p，附 bootstrap CI 与留一法。
    **只作敏感性读数，不写进摘要级结论。**

门禁过滤说明：W33 态合法性门禁按 InChIKey 在 gfn2/orca 层注册；本件转录表是外部 G4MP2 层、无
InChIKey，故门禁过滤**不适用**（过滤前后同一集合），此处显式登记而非静默跳过。

只读；不接主记分牌；累计 shot 仍 19。

Run:
    .venv/Scripts/python.exe probes/w47_anchor_crosscheck.py
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
from tools.taub_power import exact_rejection_rate, mde, power, required_n
from w33_kendall_null_tool import p_upper
from w42_common import (
    ARTIFACTS,
    FROZEN_READINGS,
    criteria_row,
    sha256_file,
    utc_now,
    write_csv_lf,
)

PREREG_PATH = REPOSITORY_ROOT / "probes" / "w47_anchor_prereg.json"
COMPUTED_OX_PATH = REPOSITORY_ROOT / "data" / "external" / "w47_borodin2013_table1_computed_oxidation.csv"
EXPERIMENTAL_OX_PATH = REPOSITORY_ROOT / "data" / "external" / "w47_borodin2013_table3_experimental_oxidation.csv"
REDUCTION_LI_PATH = REPOSITORY_ROOT / "data" / "external" / "w47_borodin2015_li_coupled_reduction.csv"
LEGALITY_REGISTRY_PATH = REPOSITORY_ROOT / "data" / "processed" / "redox_state_legality_registry.csv"
COVERAGE_CSV = ARTIFACTS / "w47_anchor_coverage.csv"
CROSSCHECK_CSV = ARTIFACTS / "w47_oxidation_crosscheck.csv"
SUMMARY_PATH = ARTIFACTS / "w47_anchor_crosscheck_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w47_anchor_crosscheck.md"

SCHEMA = "w47_anchor_crosscheck/summary@1"
TASK = "week47_anchor_crosscheck"
REGISTERED_NEGATIVES: tuple[str, ...] = ()

Z_RESOLVE = 1.96
PRIMARY_COLUMN = "dGa_eps20_V"
SENSITIVITY_COLUMNS = ("dEa_eps20_V", "dGa_eps1_V", "dEa_eps1_V")
COVERAGE_FIELDS = ("axis", "track", "solvent", "in_core_set", "present", "source_series", "evidence_table")
CROSSCHECK_FIELDS = (
    "solvent", "in_core_set", "rank_computed_primary", "rank_experimental",
    "computed_dGa_eps20_V", "computed_dEa_eps20_V", "computed_dGa_eps1_V", "computed_dEa_eps1_V",
    "experimental_V_vs_Li", "experimental_criterion_flag", "delta_primary_minus_experimental_V",
)
EVIDENCE_TABLE = {
    ("oxidation", "computed"): "data/external/w47_borodin2013_table1_computed_oxidation.csv",
    ("oxidation", "experimental"): "data/external/w47_borodin2013_table3_experimental_oxidation.csv",
    ("reduction", "computed"): "data/external/w47_borodin2015_li_coupled_reduction.csv",
    ("reduction", "experimental"): "data/external/w47_borodin2015_li_coupled_reduction.csv",
}
SERIES = {
    ("oxidation", "computed"): "Borodin2013_JPCC_Table1",
    ("oxidation", "experimental"): "Borodin2013_JPCC_Table3_single_solvent",
    ("reduction", "computed"): "Borodin2015_Nanotech_fig6_7_8",
    ("reduction", "experimental"): "Moshkovich2001_JES_pc_single_solvent",
}
LEVEL_DECLARATIONS = {
    "computed_oxidation": "cross_level_rank_only, not_same_level",
    "experimental_oxidation": "transcribed_as_tabulated__upstream_conversion_unaudited",
    "computed_reduction_li_coupled": "cross_level_rank_only, not_same_level",
}


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w47-A prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def as_float(value: object) -> float | None:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def kendall_tau_b(source: np.ndarray, target: np.ndarray) -> float:
    from scipy import stats

    if source.size < 2:
        return float("nan")
    return float(stats.kendalltau(source, target, variant="b").statistic)


def unresolved_share(source: np.ndarray, target: np.ndarray) -> float:
    """未解析对占比（z = 1.96）：|Delta target| < z * |Delta shift| / sqrt(2)（与 W46-A 同式）。"""
    n = int(source.size)
    if n < 2:
        return 0.0
    iu = np.triu_indices(n, 1)
    shift = target - source
    gap = np.abs(target[:, None] - target[None, :])[iu]
    spread = np.abs(shift[:, None] - shift[None, :])[iu]
    sigma = spread / math.sqrt(2.0)
    return float((gap < Z_RESOLVE * sigma).mean())


def topk_overlap(computed: np.ndarray, experimental: np.ndarray, labels: Sequence[str], k: int) -> dict[str, object]:
    order_c = [labels[i] for i in np.argsort(-computed, kind="stable")][:k]
    order_e = [labels[i] for i in np.argsort(-experimental, kind="stable")][:k]
    hit = len(set(order_c) & set(order_e))
    return {"k": int(k), "computed_top": order_c, "experimental_top": order_e,
            "overlap_count": hit, "overlap": (hit / k) if k else 0.0}


def bootstrap_tau_ci(primary: np.ndarray, experimental: np.ndarray, draws: int, seed: int,
                     alpha: float) -> dict[str, object]:
    """按分子重抽的 tau_b bootstrap；n = 4 时会有退化重抽（tau 未定义），逐次剔除并照实报数。"""
    rng = np.random.default_rng(seed)
    n = int(primary.size)
    reps: list[float] = []
    for _ in range(draws):
        pick = rng.integers(0, n, n)
        value = kendall_tau_b(primary[pick], experimental[pick])
        if math.isfinite(value):
            reps.append(value)
    arr = np.asarray(reps, dtype=float)
    return {
        "point": kendall_tau_b(primary, experimental),
        "draws": int(draws),
        "valid": int(arr.size),
        "invalid": int(draws - arr.size),
        "mean": float(arr.mean()) if arr.size else float("nan"),
        "sd": float(arr.std(ddof=1)) if arr.size > 1 else float("nan"),
        "lo": float(np.percentile(arr, 100 * alpha / 2)) if arr.size else float("nan"),
        "hi": float(np.percentile(arr, 100 * (1 - alpha / 2))) if arr.size else float("nan"),
    }

def table_pins(prereg: Mapping[str, object]) -> dict[str, object]:
    pins: dict[str, object] = {}
    for key, spec in dict(prereg["anchor_tables"]).items():
        path = REPOSITORY_ROOT / str(spec["path"])
        rows = len(read_rows(path)) if path.is_file() else -1
        digest = sha256_file(path) if path.is_file() else None
        pins[key] = {
            "path": str(spec["path"]),
            "expected_rows": int(spec["rows"]),
            "measured_rows": rows,
            "expected_sha256": str(spec["sha256"]),
            "measured_sha256": digest,
            "rows_match": rows == int(spec["rows"]),
            "sha256_match": digest == str(spec["sha256"]),
        }
    return pins


def coverage_rows(prereg: Mapping[str, object]) -> list[dict[str, object]]:
    core = [str(s) for s in prereg["core_set"]]
    computed_ox = {r["solvent"] for r in read_rows(COMPUTED_OX_PATH) if r.get("axis") == "oxidation"}
    computed_red = {r["solvent"] for r in read_rows(REDUCTION_LI_PATH)}
    exp_ox = {r["solvent"] for r in read_rows(EXPERIMENTAL_OX_PATH)
              if "/" not in r["solvent"] and r["solvent"] in core}
    exp_red = {str(s) for s in prereg["coverage_accounting"]["experimental_reduction_members"]}
    members = {
        ("oxidation", "computed"): computed_ox,
        ("oxidation", "experimental"): exp_ox,
        ("reduction", "computed"): computed_red,
        ("reduction", "experimental"): exp_red,
    }
    rows: list[dict[str, object]] = []
    for axis in ("oxidation", "reduction"):
        for track in ("computed", "experimental"):
            for solvent in core:
                rows.append({
                    "axis": axis, "track": track, "solvent": solvent, "in_core_set": "yes",
                    "present": "yes" if solvent in members[(axis, track)] else "no",
                    "source_series": SERIES[(axis, track)],
                    "evidence_table": EVIDENCE_TABLE[(axis, track)],
                })
    return rows


def coverage_summary(rows: Sequence[Mapping[str, object]], prereg: Mapping[str, object]) -> dict[str, object]:
    def members(axis: str, track: str) -> list[str]:
        return [str(r["solvent"]) for r in rows
                if r["axis"] == axis and r["track"] == track and r["present"] == "yes"]

    expected = dict(prereg["coverage_accounting"])
    computed_ox = members("oxidation", "computed")
    exp_ox = members("oxidation", "experimental")
    computed_red = members("reduction", "computed")
    exp_red = members("reduction", "experimental")
    union = sorted(set(computed_red) | set(exp_red))

    def same(left: Sequence[str], right: Sequence[object]) -> bool:
        return sorted(str(x) for x in left) == sorted(str(x) for x in right)

    agreement = {
        "computed_oxidation_members": same(computed_ox, expected["computed_oxidation_members"]),
        "experimental_oxidation_single_solvent_members":
            same(exp_ox, expected["experimental_oxidation_single_solvent_members"]),
        "computed_reduction_members": same(computed_red, expected["computed_reduction_members"]),
        "experimental_reduction_members": same(exp_red, expected["experimental_reduction_members"]),
        "reduction_tracks_union": same(union, expected["reduction_tracks_union"]),
    }
    min_core = int(expected["min_core_anchors"])
    return {
        "core_set": [str(s) for s in prereg["core_set"]],
        "core_set_size": len(prereg["core_set"]),
        "computed_oxidation_members": computed_ox,
        "experimental_oxidation_single_solvent_members": exp_ox,
        "computed_reduction_members": computed_red,
        "experimental_reduction_members": exp_red,
        "reduction_tracks_union": union,
        "reduction_union_size": len(union),
        "min_core_anchors": min_core,
        "refusal_fired": len(union) < min_core,
        "prereg_agreement": agreement,
        "prereg_all_agree": all(agreement.values()),
    }


def experimental_primary(prereg: Mapping[str, object]) -> dict[str, dict[str, object]]:
    core = [str(s) for s in prereg["core_set"]]
    indexed = list(enumerate(read_rows(EXPERIMENTAL_OX_PATH)))
    picks: dict[str, dict[str, object]] = {}
    for solvent in core:
        candidates = [(i, r) for i, r in indexed if r["solvent"] == solvent]
        if not candidates:
            continue
        primary = [(i, r) for i, r in candidates
                   if r["ref_in_paper"] == "ref53"
                   and abs((as_float(r["scan_rate_mV_s"]) or -1.0) - 5.0) < 1e-9
                   and abs((as_float(r["cutoff_mA_cm2"]) or -1.0) - 1.0) < 1e-9
                   and ("Et4NBF4" in r["electrolyte"] or "Bu4NBF4" in r["electrolyte"])]
        index, chosen = primary[0] if primary else candidates[0]
        if primary:
            flag = "criterion_primary_5mV_1mA_ref53"
        else:
            scan = as_float(chosen["scan_rate_mV_s"])
            cutoff = as_float(chosen["cutoff_mA_cm2"])
            flag = "criterion_secondary_%smV_%smA_%s" % (
                ("%g" % scan) if scan is not None else "na",
                ("%g" % cutoff) if cutoff is not None else "na",
                chosen["ref_in_paper"])
        picks[solvent] = {
            "row_index": index,
            "potential_V_vs_Li": as_float(chosen["potential_V_vs_Li"]),
            "criterion_flag": flag,
            "electrode": chosen["electrode"],
            "electrolyte": chosen["electrolyte"],
            "ref_in_paper": chosen["ref_in_paper"],
            "resolved_ref": chosen["resolved_ref"],
        }
    return picks


def gate_filter(labels: Sequence[str]) -> dict[str, object]:
    registry = read_rows(LEGALITY_REGISTRY_PATH)
    registry_levels = sorted({str(r["level"]) for r in registry})
    external_levels = {"G4MP2", "G4MP2//LC-wPBE"}
    applicable = bool(external_levels & set(registry_levels))
    return {
        "applicable": applicable,
        "registry_levels": registry_levels,
        "external_transcribed_levels": sorted(external_levels),
        "n_before": len(labels),
        "n_removed": 0 if not applicable else None,
        "n_after": len(labels) if not applicable else None,
        "reason": ("W33 态合法性门禁按 InChIKey 在 gfn2/orca 层注册；本件转录表是外部 G4MP2 层、"
                   "无 InChIKey，门禁过滤不适用（过滤前后同一集合），显式登记而非静默跳过。"),
    }


def oxidation_crosscheck(prereg: Mapping[str, object]) -> dict[str, object]:
    core = [str(s) for s in prereg["core_set"]]
    computed = {r["solvent"]: r for r in read_rows(COMPUTED_OX_PATH) if r["core_set"] == "yes"}
    exp_picks = experimental_primary(prereg)
    labels = [s for s in core if s in computed and s in exp_picks]
    primary = np.array([float(computed[s][PRIMARY_COLUMN]) for s in labels], dtype=float)
    experimental = np.array([float(exp_picks[s]["potential_V_vs_Li"]) for s in labels], dtype=float)
    computed_rank = {labels[int(x)]: int(position) for position, x in enumerate(np.argsort(-primary, kind="stable"))}
    experimental_rank = {labels[int(x)]: int(position) for position, x in enumerate(np.argsort(-experimental, kind="stable"))}

    rows: list[dict[str, object]] = []
    for i, solvent in enumerate(labels):
        rows.append({
            "solvent": solvent, "in_core_set": "yes",
            "rank_computed_primary": computed_rank[solvent],
            "rank_experimental": experimental_rank[solvent],
            "computed_dGa_eps20_V": float(computed[solvent]["dGa_eps20_V"]),
            "computed_dEa_eps20_V": float(computed[solvent]["dEa_eps20_V"]),
            "computed_dGa_eps1_V": float(computed[solvent]["dGa_eps1_V"]),
            "computed_dEa_eps1_V": float(computed[solvent]["dEa_eps1_V"]),
            "experimental_V_vs_Li": float(exp_picks[solvent]["potential_V_vs_Li"]),
            "experimental_criterion_flag": str(exp_picks[solvent]["criterion_flag"]),
            "delta_primary_minus_experimental_V": float(primary[i] - experimental[i]),
        })

    tau = kendall_tau_b(primary, experimental)
    gates = dict(prereg["gates"])
    draws = int(gates["bootstrap_draws"])
    seed = int(gates["bootstrap_seed"])
    alpha = 1.0 - float(gates["ci_level"])
    boot = bootstrap_tau_ci(primary, experimental, draws=draws, seed=seed, alpha=alpha)
    sensitivity = {
        column: {
            "tau_b_vs_experimental": kendall_tau_b(np.array([float(computed[s][column]) for s in labels]), experimental),
            "unresolved_share": unresolved_share(np.array([float(computed[s][column]) for s in labels]), experimental),
        }
        for column in SENSITIVITY_COLUMNS
    }
    leave_one_out = []
    for i, solvent in enumerate(labels):
        keep = [j for j in range(len(labels)) if j != i]
        keep = np.asarray(keep, dtype=int)
        leave_one_out.append({
            "dropped": solvent, "n": int(keep.size),
            "tau_b": kendall_tau_b(primary[keep], experimental[keep]),
            "unresolved_share": unresolved_share(primary[keep], experimental[keep]),
        })

    n = len(labels)
    return {
        "n": n,
        "labels": labels,
        "pairs": n * (n - 1) // 2,
        "primary_column": PRIMARY_COLUMN,
        "rows": rows,
        "tau_b": tau,
        "tau_b_swapped": kendall_tau_b(experimental, primary),
        "exact_p_upper": float(p_upper(n, tau)) if n >= 2 else float("nan"),
        "bootstrap": boot,
        "unresolved_share_primary_to_experimental": unresolved_share(primary, experimental),
        "unresolved_share_experimental_to_primary": unresolved_share(experimental, primary),
        "top_k": [topk_overlap(primary, experimental, labels, int(k))
                  for k in prereg["cross_consistency"]["top_k"]],
        "sensitivity": sensitivity,
        "leave_one_out": leave_one_out,
        "gate_filter": gate_filter(labels),
        "experimental_picks": {k: v for k, v in exp_picks.items() if k in labels},
        "small_sample_declaration": "n = 4、6 对；tau_b 必须与精确单侧 p 同报，禁止单独引用 tau_b。",
    }


def power_floor(n: int) -> dict[str, object]:
    return {
        "n": int(n),
        "mde": float(mde(n)),
        "exact_rejection_rate": float(exact_rejection_rate(n, 0.05)),
        "power_at_tau_0.4": float(power(n, 0.4)),
        "power_at_tau_0.6": float(power(n, 0.6)),
        "power_at_tau_0.8": float(power(n, 0.8)),
        "required_n_tau_0.6": required_n(0.6),
        "required_n_tau_0.8": required_n(0.8),
    }


def compute(prereg: Mapping[str, object]) -> dict[str, object]:
    rows = coverage_rows(prereg)
    coverage = coverage_summary(rows, prereg)
    crosscheck = oxidation_crosscheck(prereg)
    return {
        "coverage_rows": rows,
        "coverage": coverage,
        "crosscheck": crosscheck,
        "table_pins": table_pins(prereg),
        "level_declarations": dict(LEVEL_DECLARATIONS),
        "power_floor": power_floor(crosscheck["n"]),
        "main_judgment": {
            "status": "not_executed",
            "reason": "H47a2：核心集还原锚点并集 %d < %d，主判据（D2 tau_b >= 0.9 或 Delta tau_b(D2-D0) CI 整体 > 0）不执行，"
                      "降级为「不可判定 + 功效下限」，与 W33 ORCA 层先例同规格（不算失败）。"
                      % (coverage["reduction_union_size"], coverage["min_core_anchors"]),
        },
    }


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    coverage = payload["coverage"]
    crosscheck = payload["crosscheck"]
    pins = payload["table_pins"]
    declarations = payload["level_declarations"]
    floor = payload["power_floor"]
    top_k = crosscheck["top_k"]

    triple_reported = (crosscheck["tau_b"] == crosscheck["tau_b"] and top_k
                       and crosscheck["unresolved_share_primary_to_experimental"] ==
                       crosscheck["unresolved_share_primary_to_experimental"])
    gate = crosscheck["gate_filter"]
    gate_both_reported = (gate["n_before"] is not None and gate["applicable"] is False
                          and gate["n_after"] == gate["n_before"] and gate["n_removed"] == 0)
    pins_ok = all(bool(item["rows_match"]) and bool(item["sha256_match"]) for item in pins.values())
    declarations_ok = all("not_same_level" in str(v) or "unaudited" in str(v) for v in declarations.values())

    return [
        criteria_row("H47a1",
                     "主判据（D2 tau_b >= 0.9 或 Delta tau_b(D2-D0) CI 整体 > 0）按 H47a2 不执行，登记为不可判定（不判否）",
                     payload["main_judgment"], {"status": "not_executed"},
                     payload["main_judgment"]["status"] == "not_executed"),
        criteria_row("H47a2",
                     "拒答分支条件：核心集还原锚点（计算+实验并集）< min_core_anchors = 5",
                     {"reduction_tracks_union": coverage["reduction_tracks_union"],
                      "reduction_union_size": coverage["reduction_union_size"],
                      "min_core_anchors": coverage["min_core_anchors"]},
                     {"reduction_union_size_lt": 5},
                     bool(coverage["refusal_fired"]) and coverage["reduction_union_size"] < 5),
        criteria_row("H47a3",
                     "三件套同报（tau_b + Top-k 重叠 + 未解析占比 z=1.96），且门禁过滤前后各报一遍（本件过滤不适用，前后同一集合）",
                     {"tau_b": crosscheck["tau_b"], "top_k": top_k,
                      "unresolved_share": crosscheck["unresolved_share_primary_to_experimental"],
                      "gate_filter": gate},
                     {"triple": ["tau_b", "top_k", "unresolved_share"], "gate_before_after": "both"},
                     bool(triple_reported and gate_both_reported)),
        criteria_row("H47a4",
                     "层级纪律：三张转录表层级声明齐备，跨层只作 rank_only（不得声明 same_level）",
                     declarations, {"must_not_claim_same_level": True}, bool(declarations_ok)),
        criteria_row("H47a5",
                     "氧化轴计算-实验交叉一致性可复算：n = 4、精确单侧 p 与 tau_b 同报（禁止单独引用 tau_b）",
                     {"n": crosscheck["n"], "pairs": crosscheck["pairs"], "tau_b": crosscheck["tau_b"],
                      "exact_p_upper": crosscheck["exact_p_upper"], "bootstrap": crosscheck["bootstrap"]},
                     {"n": 4, "exact_p_required": True},
                     crosscheck["n"] == 4 and 0.0 <= float(crosscheck["exact_p_upper"]) <= 1.0),
        criteria_row("H47a6",
                     "覆盖核算与预注册逐项一致（五张成员表全等）",
                     coverage["prereg_agreement"], {"all_equal": True}, bool(coverage["prereg_all_agree"])),
        criteria_row("H47a7",
                     "table_pins：三张转录表行数 + sha256 与预注册逐位一致",
                     {k: {"rows": v["measured_rows"], "sha256": v["measured_sha256"]} for k, v in pins.items()},
                     {"rows_and_sha256": "all_match"}, bool(pins_ok)),
        criteria_row("H47a8",
                     "功效下限同报（n = 4 的 MDE / 精确拒绝率 / 所需锚点数），与 taub_power 工具逐位一致",
                     floor, {"n": 4, "mde_reported": True},
                     floor["n"] == 4 and 0.0 <= float(floor["exact_rejection_rate"]) <= 1.0
                     and bool(floor["required_n_tau_0.6"].get("reachable"))),
    ]


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    coverage = payload["coverage"]
    crosscheck = payload["crosscheck"]
    floor = payload["power_floor"]
    lines: list[str] = []
    add = lines.append
    add("# W47-A 计算锚点覆盖核算与氧化轴交叉一致性")
    add("")
    add("只读 lane，0 shot。取件核实推翻了 W47 计划的 V1 归属：Borodin 2013 是纯氧化论文（无还原/EA 表），")
    add("Borodin 2015 给的是 Li+ 耦合**计算**还原，Moshkovich 2001 只有 PC 单溶剂。据此本件不执行还原主判据，")
    add("改交一张覆盖核算表与一条氧化轴小样本交叉一致性读数。")
    add("")
    add("## 1 覆盖核算（核心集 7 溶剂）")
    add("")
    add("| 轴 | 轨 | 成员 | 覆盖 |")
    add("| --- | --- | --- | --- |")
    add("| 氧化 | 计算 | " + " / ".join(coverage["computed_oxidation_members"]) + " | "
        + str(len(coverage["computed_oxidation_members"])) + "/7 |")
    add("| 氧化 | 实验（单溶剂行） | " + " / ".join(coverage["experimental_oxidation_single_solvent_members"]) + " | "
        + str(len(coverage["experimental_oxidation_single_solvent_members"])) + "/7 |")
    add("| 还原 | 计算 | " + " / ".join(coverage["computed_reduction_members"]) + " | "
        + str(len(coverage["computed_reduction_members"])) + "/7 |")
    add("| 还原 | 实验 | " + " / ".join(coverage["experimental_reduction_members"]) + " | "
        + str(len(coverage["experimental_reduction_members"])) + "/7 |")
    add("")
    add("还原轨并集 = " + " / ".join(coverage["reduction_tracks_union"]) + "（"
        + str(coverage["reduction_union_size"]) + " < " + str(coverage["min_core_anchors"])
        + "）⇒ **H47a2 拒答分支触发**：" + payload["main_judgment"]["reason"])
    add("")
    add("## 2 氧化轴计算-实验交叉一致性（敏感性读数，n = " + str(crosscheck["n"]) + "）")
    add("")
    add("| 溶剂 | 计算 dGa(eps=20) | 实验 E_ox vs Li | 计算秩 | 实验秩 | 判据 |")
    add("| --- | --- | --- | --- | --- | --- |")
    for row in crosscheck["rows"]:
        add("| " + str(row["solvent"]) + " | " + ("%.2f" % row["computed_dGa_eps20_V"]) + " | "
            + ("%.2f" % row["experimental_V_vs_Li"]) + " | " + str(row["rank_computed_primary"] + 1) + " | "
            + str(row["rank_experimental"] + 1) + " | " + str(row["experimental_criterion_flag"]) + " |")
    add("")
    add("- tau_b = **" + ("%.4f" % crosscheck["tau_b"]) + "**；精确单侧 p = **"
        + ("%.4f" % crosscheck["exact_p_upper"]) + "**；bootstrap 95% CI = ["
        + ("%.4f" % crosscheck["bootstrap"]["lo"]) + ", " + ("%.4f" % crosscheck["bootstrap"]["hi"]) + "]。")
    add("- 未解析占比（z = 1.96，计算 -> 实验）= **"
        + ("%.4f" % crosscheck["unresolved_share_primary_to_experimental"]) + "**。")
    add("- Top-k 重叠：" + "，".join("k=%d -> %.2f" % (t["k"], t["overlap"]) for t in crosscheck["top_k"]) + "。")
    add("- 敏感性列 tau_b：" + "，".join(
        str(k) + " " + ("%.4f" % v["tau_b_vs_experimental"]) for k, v in crosscheck["sensitivity"].items()) + "。")
    add("- 留一法：" + "，".join(
        "去 " + str(item["dropped"]) + " " + ("%.4f" % item["tau_b"]) for item in crosscheck["leave_one_out"]) + "。")
    add("- 门禁过滤：" + str(crosscheck["gate_filter"]["reason"]))
    add("")
    add("## 3 功效下限（n = " + str(floor["n"]) + "）")
    add("")
    add("- MDE（80% 功效）= **" + ("%.4f" % floor["mde"]) + "**；精确拒绝率 = "
        + ("%.6f" % floor["exact_rejection_rate"]) + "。")
    add("- 功效：tau_true = 0.4 / 0.6 / 0.8 时 = " + ("%.4f" % floor["power_at_tau_0.4"]) + " / "
        + ("%.4f" % floor["power_at_tau_0.6"]) + " / " + ("%.4f" % floor["power_at_tau_0.8"]) + "。")
    add("- 达到 80% 功效所需锚点数：tau_true = 0.6 -> " + str(floor["required_n_tau_0.6"]["n_min"])
        + "；0.8 -> " + str(floor["required_n_tau_0.8"]["n_min"]) + "。")
    add("")
    add("## 4 table_pins")
    add("")
    add("| 表 | 行数 | sha256 命中 |")
    add("| --- | --- | --- |")
    for key, item in payload["table_pins"].items():
        add("| " + key + " | " + str(item["measured_rows"]) + " | "
            + ("是" if item["sha256_match"] else "否") + " |")
    add("")
    add("## 5 判据")
    add("")
    add("| id | 判据 | 值 | 阈 | 判决 |")
    add("| --- | --- | --- | --- | --- |")
    for row in criteria:
        add("| " + str(row["id"]) + " | " + str(row["description"]) + " | "
            + json.dumps(row["value"], ensure_ascii=False) + " | "
            + json.dumps(row["threshold"], ensure_ascii=False) + " | " + str(row["verdict"]) + " |")
    add("")
    add("**结论**：还原轴实验/计算锚点并集仍 < 5，主判据不可判定；氧化轴 n = 4 交叉一致性 tau_b = "
        + ("%.4f" % crosscheck["tau_b"]) + "（精确 p = " + ("%.4f" % crosscheck["exact_p_upper"])
        + "）**只作敏感性读数，不进判决、不写进摘要级结论**。0 shot（累计仍 19）。")
    add("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只算不写盘")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [PREREG_PATH, COMPUTED_OX_PATH, EXPERIMENTAL_OX_PATH, REDUCTION_LI_PATH, LEGALITY_REGISTRY_PATH]
    before = {str(path): sha256_file(path) for path in sources if path.is_file()}
    payload = compute(prereg)
    after = {str(path): sha256_file(path) for path in sources if path.is_file()}
    inputs_unchanged = before == after

    criteria = evaluate(payload, prereg)
    criteria.append(criteria_row(
        "H47a9", "输入（预注册 + 三张转录表 + 合法性注册表）sha256 未变",
        {"inputs_unchanged": inputs_unchanged}, {"unchanged": True}, inputs_unchanged))
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    if not args.check:
        write_csv_lf(COVERAGE_CSV, COVERAGE_FIELDS, payload["coverage_rows"])
        write_csv_lf(CROSSCHECK_CSV, CROSSCHECK_FIELDS, payload["crosscheck"]["rows"])
        summary = {
            "schema": SCHEMA,
            "task": TASK,
            "generated_at_utc": utc_now(),
            "elapsed_seconds": float(time.perf_counter() - started),
            "ledger": {
                "main_scoreboard_shots_this_week": 0,
                "cumulative_main_scoreboard_attempts_after": 19,
                "why_not_a_shot": "只读转录交叉核对：不拟合主记分牌臂、不新增特征列、不改 METRIC_NAMES、不动冻结读数。",
            },
            "inputs": before,
            "inputs_unchanged": inputs_unchanged,
            "frozen_readings_untouched": list(FROZEN_READINGS),
            "coverage": payload["coverage"],
            "main_judgment": payload["main_judgment"],
            "crosscheck": {k: v for k, v in payload["crosscheck"].items() if k != "rows"},
            "table_pins": payload["table_pins"],
            "level_declarations": payload["level_declarations"],
            "power_floor": payload["power_floor"],
            "criteria": criteria,
            "registered_negatives": list(REGISTERED_NEGATIVES),
            "headline": [
                "还原轨核心集覆盖并集 %d < 5 ⇒ H47a2 触发，主判据不可判定（不判否）。"
                % payload["coverage"]["reduction_union_size"],
                "氧化轴交叉一致性（n = %d）：tau_b = %.4f，精确单侧 p = %.4f，未解析 %.4f，Top-1 %.2f / Top-2 %.2f。"
                % (payload["crosscheck"]["n"], payload["crosscheck"]["tau_b"],
                   payload["crosscheck"]["exact_p_upper"],
                   payload["crosscheck"]["unresolved_share_primary_to_experimental"],
                   payload["crosscheck"]["top_k"][0]["overlap"], payload["crosscheck"]["top_k"][1]["overlap"]),
                "功效下限（n = %d）：MDE = %.4f，精确拒绝率 = %.6f。"
                % (payload["power_floor"]["n"], payload["power_floor"]["mde"],
                   payload["power_floor"]["exact_rejection_rate"]),
                "0 shot（累计仍 19）。",
            ],
        }
        write_json_stable(SUMMARY_PATH, summary)
        REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    print("coverage union %d < %d (refusal %s) | n %d | tau_b %.6f | exact_p %.6f | unresolved %.6f | pins %s"
          % (payload["coverage"]["reduction_union_size"], payload["coverage"]["min_core_anchors"],
             payload["coverage"]["refusal_fired"], payload["crosscheck"]["n"],
             payload["crosscheck"]["tau_b"], payload["crosscheck"]["exact_p_upper"],
             payload["crosscheck"]["unresolved_share_primary_to_experimental"],
             all(v["sha256_match"] and v["rows_match"] for v in payload["table_pins"].values())))
    print("verdicts %d/%d" % (len(criteria) - len(failed), len(criteria)))
    for item in failed:
        print("FAIL %s %s" % (item["id"], item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
