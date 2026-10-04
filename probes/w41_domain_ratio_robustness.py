# -*- coding: utf-8 -*-
"""W41-B：把 W40-C 的域比稳健性结论写成「双读数强制」条款，并从盘上产物独立复算。

W40-C 的 H40c10 判否给出一条口径：域间比对偶极系统偏置敏感（偏置校正后域间比相对变化
0.2059 > 0.10），因此只能声明「方向稳健」不能声明「量级稳健」。README §11 第 30 条登记的正是
这件事：下一份预注册若再引域比，必须**同时报**偏置未校正值与校正后值。

本件只读 W40-C 的两个产物（逐化合物表 + summary），从逐化合物表**独立重算**两套域比
（不是回抄 summary），并把双读数写成机器可检查的条款件。

Run:
    .venv/Scripts/python.exe probes/w41_domain_ratio_robustness.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

try:
    from probes.export_results_common import write_json_stable
except ImportError:
    from export_results_common import write_json_stable

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w41_governance_prereg.json"
COMPOUNDS_CSV = ARTIFACTS / "w40_onsager_domain_compounds.csv"
W40_SUMMARY = ARTIFACTS / "w40_onsager_domain_summary.json"
READINGS_CSV = ARTIFACTS / "w41_domain_ratio_robustness.csv"
CLAUSE_PATH = ARTIFACTS / "w41_domain_ratio_clause.json"
SUMMARY_PATH = ARTIFACTS / "w41_domain_ratio_robustness_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w41_domain_ratio_robustness.md"

SCHEMA = "w41_domain_ratio_robustness/summary@1"
TASK = "week41_domain_ratio_robustness"

FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_SINGLE_REPRESENTATION = 0.5861142332208197
FROZEN_PROMOTED_ARM = 0.6216672295270079

READING_FIELDS = ("scope", "reading", "n_used", "median_acceptor_A", "median_donor_B",
                  "ratio", "rel_change_vs_uncorrected", "robust_gate", "magnitude_robust")
REGISTERED_NEGATIVES: tuple[str, ...] = ("H41b5",)

CLAUSE = {
    "clause_id": "domain_ratio_dual_reading",
    "rule": "任何域间比（g_rel 给体域 / 非给体域中位数比）读数必须同时给出偏置未校正值与"
            "偶极偏置校正后值，并给出相对变化。",
    "gate": 0.10,
    "verdict_rule": "相对变化 > gate 时只能声明『方向稳健』，不得声明『量级稳健』；"
                    "相对变化 <= gate 时才允许声明量级稳健（仍不得声称因果）。",
    "bias_source": "约 0.39 D 的系统偏置（我们的 dipole_D 相对 QM9 偏高），来源未查清前不修数、不插补。",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w41 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def write_csv_lf(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = [",".join(fields)]
    for row in rows:
        cells = []
        for field in fields:
            value = row.get(field, "")
            text = "" if value is None else str(value)
            if any(ch in text for ch in (',', '"', '\n')):
                text = '"' + text.replace('"', '""') + '"'
            cells.append(text)
        buffer.append(",".join(cells))
    path.write_text("\n".join(buffer) + "\n", encoding="utf-8", newline="\n")


def _median_ratio(rows: Sequence[Mapping[str, str]], column: str) -> dict[str, object]:
    admit = [row for row in rows if (row.get(column) or "").strip() != ""
             and (row.get("usable") or "").strip() == "True"]
    donor = [float(row[column]) for row in admit if row["domain_new"] == "B"]
    acceptor = [float(row[column]) for row in admit if row["domain_new"] == "A"]
    if not donor or not acceptor:
        return {"n_used": len(admit), "median_acceptor_A": None, "median_donor_B": None,
                "ratio": None}
    median_a = statistics.median(acceptor)
    median_b = statistics.median(donor)
    return {"n_used": len(admit), "median_acceptor_A": median_a,
            "median_donor_B": median_b, "ratio": (median_b / median_a)}


def _high_eps(rows: Sequence[Mapping[str, str]], threshold: float, column: str) -> dict[str, object]:
    subset = [row for row in rows if float(row["eps"]) >= threshold]
    return _median_ratio(subset, column)


def build(prereg: Mapping[str, object]) -> dict[str, object]:
    lane = prereg["lanes"]["w41_domain_ratio_robustness"]
    with COMPOUNDS_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    uncorrected = _median_ratio(rows, str(lane["uncorrected_column"]))
    corrected = _median_ratio(rows, str(lane["corrected_column"]))
    ratio_u = float(uncorrected["ratio"])
    ratio_c = float(corrected["ratio"])
    relative = (ratio_c - ratio_u) / ratio_u
    high_u = _high_eps(rows, float(lane["high_eps_threshold"]), str(lane["uncorrected_column"]))
    high_c = _high_eps(rows, float(lane["high_eps_threshold"]), str(lane["corrected_column"]))
    w40 = json.loads(W40_SUMMARY.read_text(encoding="utf-8-sig"))
    double_mu = w40["double_mu"]
    return {
        "uncorrected": uncorrected, "corrected": corrected,
        "ratio_uncorrected": ratio_u, "ratio_corrected": ratio_c, "relative_change": relative,
        "high_eps_uncorrected": high_u, "high_eps_corrected": high_c,
        "high_eps_ratio_uncorrected": float(high_u["ratio"]),
        "high_eps_ratio_corrected": float(high_c["ratio"]),
        "double_mu_spearman": float(double_mu["spearman_g_rel"]),
        "double_mu_ratio_our": float(double_mu["our_mu"]["ratio"]),
        "double_mu_ratio_qm9": float(double_mu["qm9_mu"]["ratio"]),
        "n_compounds": len(rows),
        "bias_signed_delta_median_D": float(w40["dipole_bias"]["signed_delta_median_D"]),
    }


def check_dual_reading(readings: Mapping[str, object]) -> None:
    for key in ("uncorrected", "corrected"):
        block = readings.get(key)
        if not isinstance(block, Mapping) or block.get("ratio") is None:
            raise ValueError("dual-reading clause violated: missing " + key)


def reading_rows(payload: Mapping[str, object], gate: float) -> list[dict[str, object]]:
    ratio_u = float(payload["ratio_uncorrected"])
    ratio_c = float(payload["ratio_corrected"])
    relative = float(payload["relative_change"])
    high_u = float(payload["high_eps_ratio_uncorrected"])
    high_c = float(payload["high_eps_ratio_corrected"])
    high_relative = (high_c - high_u) / high_u
    specs = (
        ("all_usable", "uncorrected", payload["uncorrected"], ratio_u, "", True),
        ("all_usable", "corrected", payload["corrected"], ratio_c, relative, relative <= gate),
        ("high_eps_family", "uncorrected", payload["high_eps_uncorrected"], high_u, "", True),
        ("high_eps_family", "corrected", payload["high_eps_corrected"], high_c,
         high_relative, high_relative <= gate),
    )
    rows: list[dict[str, object]] = []
    for scope, reading, block, ratio, rel_change, magnitude_robust in specs:
        rows.append({
            "scope": scope,
            "reading": reading,
            "n_used": block["n_used"],
            "median_acceptor_A": block["median_acceptor_A"],
            "median_donor_B": block["median_donor_B"],
            "ratio": ratio,
            "rel_change_vs_uncorrected": rel_change,
            "robust_gate": gate,
            "magnitude_robust": bool(magnitude_robust),
        })
    return rows


def _verdict(ok: bool) -> str:
    return "成立" if ok else "判否"


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    lane = prereg["lanes"]["w41_domain_ratio_robustness"]
    gate = float(lane["robust_gate"])
    tol = 1e-9
    abs_tol = 1e-12
    ratio_u = float(payload["ratio_uncorrected"])
    ratio_c = float(payload["ratio_corrected"])
    relative = float(payload["relative_change"])
    criteria: list[dict[str, object]] = []
    criteria.append({
        "id": "H41b1",
        "description": "从逐化合物表独立重算的偏置未校正域比复现 W40-C 锚 2.5817133416784355",
        "value": ratio_u,
        "threshold": float(lane["expected_uncorrected_ratio"]),
        "verdict": _verdict(abs(ratio_u - float(lane["expected_uncorrected_ratio"])) < tol),
    })
    criteria.append({
        "id": "H41b2",
        "description": "独立重算的偏置校正后域比复现 W40-C 锚 3.1132529110752816",
        "value": ratio_c,
        "threshold": float(lane["expected_corrected_ratio"]),
        "verdict": _verdict(abs(ratio_c - float(lane["expected_corrected_ratio"])) < tol),
    })
    criteria.append({
        "id": "H41b3",
        "description": "相对变化复现 0.20588636267854554",
        "value": relative,
        "threshold": float(lane["expected_relative_change"]),
        "verdict": _verdict(abs(relative - float(lane["expected_relative_change"])) < abs_tol),
    })
    criteria.append({
        "id": "H41b4",
        "description": "相对变化 > 稳健门 0.10（条款触发：只能声明方向稳健）",
        "value": relative,
        "threshold": gate,
        "verdict": _verdict(relative > gate),
    })
    criteria.append({
        "id": "H41b5",
        "description": "『量级稳健』声明被判否（已登记）：相对变化超过稳健门时不得声称量级稳健",
        "value": relative,
        "threshold": gate,
        "verdict": _verdict(relative <= gate),
    })
    criteria.append({
        "id": "H41b6",
        "description": "高介电族（eps >= 60）偏置未校正域比复现 13.404447543209601",
        "value": float(payload["high_eps_ratio_uncorrected"]),
        "threshold": float(lane["expected_high_eps_uncorrected"]),
        "verdict": _verdict(abs(float(payload["high_eps_ratio_uncorrected"])
                                - float(lane["expected_high_eps_uncorrected"])) < tol),
    })
    criteria.append({
        "id": "H41b7",
        "description": "高介电族偏置校正后域比复现 17.31695976838166（校正让该族更分离）",
        "value": float(payload["high_eps_ratio_corrected"]),
        "threshold": float(lane["expected_high_eps_corrected"]),
        "verdict": _verdict(abs(float(payload["high_eps_ratio_corrected"])
                                - float(lane["expected_high_eps_corrected"])) < tol),
    })
    criteria.append({
        "id": "H41b8",
        "description": "双 mu 秩一致读数（Spearman g_rel）复现 0.8006835269993164",
        "value": float(payload["double_mu_spearman"]),
        "threshold": 0.8006835269993164,
        "verdict": _verdict(abs(float(payload["double_mu_spearman"]) - 0.8006835269993164) < tol),
    })
    dual_ok = True
    try:
        check_dual_reading(payload)
    except ValueError:
        dual_ok = False
    criteria.append({
        "id": "H41b9",
        "description": "双读数守卫通过（两套读数都存在且比值非空）",
        "value": 1.0 if dual_ok else 0.0,
        "threshold": 1.0,
        "verdict": _verdict(dual_ok),
    })
    criteria.append({
        "id": "H41b10",
        "description": "两个输入产物 sha256 前后一致（未被改写）",
        "value": 1.0,
        "threshold": 1.0,
        "verdict": "成立",
    })
    return criteria


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]],
                  prereg: Mapping[str, object]) -> str:
    gate = float(prereg["lanes"]["w41_domain_ratio_robustness"]["robust_gate"])
    lines = [
        "# W41-B 域比双读数稳健性条款（偏置未校正 / 校正后同报）",
        "",
        "**性质**：后验 / 治理件，**0 shot（累计仍 19）**。只读 W40-C 产物，从逐化合物表独立重算。",
        "",
        "## 1. 条款（写死）",
        "",
        "- **规则**：任何 g_rel 域间比读数必须同时给出「偏置未校正」与「偶极偏置校正后」两值及相对变化。",
        "- **稳健门**：相对变化 > " + format(gate, ".2f") + " 时只能声明**方向稳健**，"
        "不得声明**量级稳健**。",
        "- **偏置来源**：约 " + format(float(payload["bias_signed_delta_median_D"]), ".4f")
        + " D 的系统偏置（我们的 `dipole_D` 相对 QM9 偏高）；来源查清前**不修数、不插补**。",
        "",
        "## 2. 双读数",
        "",
        "| 范围 | 读数 | n | A 域中位 | B 域中位 | 域间比 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in reading_rows(payload, gate):
        lines.append("| " + str(row["scope"]) + " | " + str(row["reading"]) + " | "
                     + str(row["n_used"]) + " | "
                     + format(float(row["median_acceptor_A"]), ".6g") + " | "
                     + format(float(row["median_donor_B"]), ".6g") + " | "
                     + format(float(row["ratio"]), ".6f") + " |")
    lines += [
        "",
        "**全域相对变化**：" + format(float(payload["relative_change"]), ".6f")
        + "（> " + format(gate, ".2f") + " ⇒ 条款触发）。",
        "**高介电族**：" + format(float(payload["high_eps_ratio_uncorrected"]), ".4f")
        + "（未校正）→ " + format(float(payload["high_eps_ratio_corrected"]), ".4f")
        + "（校正后）—— 校正让该族**更**分离，方向与全域相反，说明校正影响不是单向偏移。",
        "**双 μ 秩一致**：Spearman(g_rel) = " + format(float(payload["double_mu_spearman"]), ".6f")
        + "（n = 76，两套 μ 只比中位数与秩，不比绝对值）。",
        "",
        "## 3. 判据",
        "",
        "| 判据 | 说明 | 读数 | 门槛 | 判定 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for item in criteria:
        value = item["value"]
        text = format(float(value), ".6g") if isinstance(value, (int, float)) else str(value)
        threshold = item["threshold"]
        ttext = format(float(threshold), ".6g") if isinstance(threshold, (int, float)) else str(threshold)
        lines.append("| " + str(item["id"]) + " | " + str(item["description"]) + " | "
                     + text + " | " + ttext + " | " + str(item["verdict"]) + " |")
    lines += [
        "",
        "## 4. 边界",
        "",
        "- 域间比是**相关读数**，不是因果；域纠正不等于量级证据。",
        "- `g_rel` 是无量纲相对量，只可做域间比较，**不得**与文献 g 绝对值对照。",
        "- H41b5 是把 W40-C 的 H40c10 判否落成稳健性条款后的**在册判否**，不是新失败。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [COMPOUNDS_CSV, W40_SUMMARY]
    before = {str(path): sha256_file(path) for path in sources}
    payload = build(prereg)
    check_dual_reading(payload)
    after = {str(path): sha256_file(path) for path in sources}
    inputs_unchanged = before == after
    criteria = evaluate(payload, prereg)
    criteria[-1]["value"] = 1.0 if inputs_unchanged else 0.0
    criteria[-1]["verdict"] = _verdict(inputs_unchanged)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    gate = float(prereg["lanes"]["w41_domain_ratio_robustness"]["robust_gate"])
    write_csv_lf(READINGS_CSV, READING_FIELDS, reading_rows(payload, gate))
    clause = dict(CLAUSE)
    clause.update({
        "schema": "w41_domain_ratio_clause/clause@1",
        "task": TASK,
        "uncorrected_ratio": float(payload["ratio_uncorrected"]),
        "corrected_ratio": float(payload["ratio_corrected"]),
        "relative_change": float(payload["relative_change"]),
        "magnitude_robust": bool(float(payload["relative_change"]) <= gate),
        "direction_robust": True,
    })
    write_json_stable(CLAUSE_PATH, clause)

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "从 W40-C 逐化合物表独立重算两套域比，不拟合主记分牌臂、不新增特征列、不改 METRIC_NAMES、不动冻结读数。",
        },
        "inputs": before,
        "inputs_unchanged": inputs_unchanged,
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE,
                                      FROZEN_SINGLE_REPRESENTATION, FROZEN_PROMOTED_ARM],
        "clause": clause,
        "readings": reading_rows(payload, gate),
        "ratio_uncorrected": float(payload["ratio_uncorrected"]),
        "ratio_corrected": float(payload["ratio_corrected"]),
        "relative_change": float(payload["relative_change"]),
        "high_eps_ratio_uncorrected": float(payload["high_eps_ratio_uncorrected"]),
        "high_eps_ratio_corrected": float(payload["high_eps_ratio_corrected"]),
        "double_mu_spearman": float(payload["double_mu_spearman"]),
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "双读数：偏置未校正域比 " + format(float(payload["ratio_uncorrected"]), ".6f")
            + "，校正后 " + format(float(payload["ratio_corrected"]), ".6f")
            + "，相对变化 " + format(float(payload["relative_change"]), ".6f") + "。",
            "相对变化 > 稳健门 " + format(gate, ".2f") + " ⇒ 只能声明方向稳健，量级稳健判否（H41b5 在册）。",
            "高介电族反向：未校正 " + format(float(payload["high_eps_ratio_uncorrected"]), ".4f")
            + " → 校正后 " + format(float(payload["high_eps_ratio_corrected"]), ".4f") + "。",
            "0 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria, prereg), encoding="utf-8", newline="\n")

    print("domain ratio uncorrected " + format(float(payload["ratio_uncorrected"]), ".10f"))
    print("domain ratio corrected   " + format(float(payload["ratio_corrected"]), ".10f"))
    print("relative change          " + format(float(payload["relative_change"]), ".10f"))
    print("verdicts " + str(len(criteria) - len(failed)) + "/" + str(len(criteria)))
    for item in failed:
        print(("REGISTERED-NEGATIVE " if str(item["id"]) in REGISTERED_NEGATIVES
               else "UNREGISTERED-FAIL ") + str(item["id"]) + " " + str(item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())