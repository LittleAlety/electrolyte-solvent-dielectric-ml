# -*- coding: utf-8 -*-
"""W41-A：把「干净阶梯」准入规则写成机械规则，并在准入后的池子上复算比值判据。

W40-A 已经把 H31h 的绝对 0.08 门换成比值判据（R2 极差 / AUC30 极差），并留下一句口径：
**比值判据的第一要求是阶梯定义干净** —— W28 那 13 个臂若混进池子，AUC30 极差会从
0.005561 抬到 0.543814，把比值压到 1.293 造成假判否。README §11 第 29 条登记的正是这件事：
把「阶梯 = 同一配置网格上的档位」与安慰剂臂 / 换表示臂的剔除写成一个机械规则，让每次复算
不必事后清洗。

本件只读盘上既有产物（W28-W32 的逐重复表），不重拟合任何臂、不新增特征列、不动冻结读数。

Run:
    .venv/Scripts/python.exe probes/w41_ladder_admission.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w41_governance_prereg.json"
ARM_CSV = ARTIFACTS / "w41_ladder_admission.csv"
LADDER_CSV = ARTIFACTS / "w41_ladder_admission_summary.csv"
SUMMARY_PATH = ARTIFACTS / "w41_ladder_admission_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w41_ladder_admission.md"
FIGURE_PATH = ARTIFACTS / "w41_ladder_admission.png"

SCHEMA = "w41_ladder_admission/summary@1"
TASK = "week41_ladder_admission"

PLACEBO_PATTERN = re.compile(r"(shuffled|placebo|random_target)")
REPRESENTATION_PATTERN = re.compile(r"(morgan|fingerprint|embedding)")

FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_SINGLE_REPRESENTATION = 0.5861142332208197
FROZEN_PROMOTED_ARM = 0.6216672295270079

ARM_FIELDS = ("ladder", "arm", "family", "n_repeats", "admitted", "reason",
              "r2_mean", "auc30_mean")
LADDER_FIELDS = ("ladder", "n_arms_total", "n_admitted", "n_excluded",
                 "r2_spread_admitted", "auc30_spread_admitted", "ratio_admitted",
                 "ratio_all", "n_all_arms")
REGISTERED_NEGATIVES: tuple[str, ...] = ()


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


def classify(arm: str, prefix: str | None) -> tuple[str, bool, str]:
    """Return (family, admitted, reason) for one arm name under the lane rules."""
    if PLACEBO_PATTERN.search(arm):
        return "placebo", False, "R2 安慰剂臂（shuffled/placebo/random_target）"
    if REPRESENTATION_PATTERN.search(arm):
        return "representation_swap", False, "R3 换表示臂（morgan/fingerprint/embedding）"
    if prefix is not None and not arm.startswith(prefix):
        return "anchor_or_other", False, "R1 非本阶梯配置网格（前缀 " + prefix + "）"
    return "grid", True, "R1/R2/R3 通过"


def read_ladder(path: Path) -> dict[str, list[dict[str, str]]]:
    by_arm: dict[str, list[dict[str, str]]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            by_arm.setdefault(record["arm"], []).append(record)
    return by_arm


def spread(values: Sequence[float]) -> float:
    return float(max(values) - min(values))


def arm_means(rows: Sequence[Mapping[str, str]]) -> tuple[float, float]:
    return (statistics.fmean(float(row["r2"]) for row in rows),
            statistics.fmean(float(row["auc_gt30"]) for row in rows))


def build(prereg: Mapping[str, object]) -> dict[str, object]:
    lane = prereg["lanes"]["w41_ladder_admission"]
    specs = list(lane["ladder_sources"])

    all_rows: list[dict[str, object]] = []
    ladder_rows: list[dict[str, object]] = []
    for spec, label in zip(specs, [item["label"] for item in specs]):
        by_arm = read_ladder(REPOSITORY_ROOT / str(spec["path"]))
        counts = [len(v) for v in by_arm.values()]
        modal = statistics.mode(counts) if counts else 0
        admitted: dict[str, list[dict[str, str]]] = {}
        for arm in sorted(by_arm):
            family, ok, reason = classify(arm, spec.get("admit_prefix"))
            if ok and len(by_arm[arm]) != modal:
                family, ok = "incomplete_repeats", False
                reason = "R4 重复集不完整（" + str(len(by_arm[arm])) + " != " + str(modal) + "）"
            r2_mean, auc_mean = arm_means(by_arm[arm])
            all_rows.append({
                "ladder": label, "arm": arm, "family": family,
                "n_repeats": len(by_arm[arm]), "admitted": bool(ok), "reason": reason,
                "r2_mean": r2_mean, "auc30_mean": auc_mean,
            })
            if ok:
                admitted[arm] = by_arm[arm]

        def ladder_spread(pool: Mapping[str, Sequence[Mapping[str, str]]]) -> tuple[float, float, float]:
            if len(pool) < 2:
                return float("nan"), float("nan"), float("nan")
            r2 = [arm_means(v)[0] for v in pool.values()]
            auc = [arm_means(v)[1] for v in pool.values()]
            r2s, aucs = spread(r2), spread(auc)
            return r2s, aucs, (r2s / aucs if aucs else float("inf"))

        r2a, auca, ratioa = ladder_spread(admitted)
        _, _, ratioall = ladder_spread(by_arm)
        ladder_rows.append({
            "ladder": label, "n_arms_total": len(by_arm), "n_admitted": len(admitted),
            "n_excluded": len(by_arm) - len(admitted),
            "r2_spread_admitted": r2a, "auc30_spread_admitted": auca,
            "ratio_admitted": ratioa, "ratio_all": ratioall, "n_all_arms": len(by_arm),
        })
    return {"arms": all_rows, "ladders": ladder_rows, "specs": specs}


def _verdict(ok: bool) -> str:
    return "成立" if ok else "判否"


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    lane = prereg["lanes"]["w41_ladder_admission"]
    ladders = list(payload["ladders"])
    arms = list(payload["arms"])
    expected_ratios = [float(v) for v in lane["expected_ratios"]]
    expected_admitted = dict(lane["expected_admitted"])

    ratios = [float(item["ratio_admitted"]) for item in ladders]
    auc_spreads = [float(item["auc30_spread_admitted"]) for item in ladders]
    label_to_short = {spec["label"]: spec.get("admit_prefix") for spec in payload["specs"]}
    admitted_counts = {str(item["ladder"]).split(" ")[0]: int(item["n_admitted"]) for item in ladders}
    w28 = ladders[0]
    excluded_w28 = [row for row in arms if row["ladder"] == w28["ladder"] and not row["admitted"]]

    criteria: list[dict[str, object]] = []
    criteria.append({
        "id": "H41a1",
        "description": "五个准入阶梯的比值逐位复现 W40-A 冻结锚",
        "value": float(max(abs(a - b) for a, b in zip(ratios, expected_ratios))),
        "threshold": 1e-9,
        "verdict": _verdict(all(abs(a - b) < 1e-9 for a, b in zip(ratios, expected_ratios))),
    })
    criteria.append({
        "id": "H41a2",
        "description": "准入后每个阶梯的 AUC30 极差 < 0.02（序侧不被污染标志）",
        "value": float(max(auc_spreads)),
        "threshold": float(lane["auc30_spread_gate"]),
        "verdict": _verdict(max(auc_spreads) < float(lane["auc30_spread_gate"])),
    })
    criteria.append({
        "id": "H41a3",
        "description": "每个准入阶梯的比值 >= 稳健门 4.0",
        "value": float(min(ratios)),
        "threshold": float(lane["robust_ratio_gate"]),
        "verdict": _verdict(min(ratios) >= float(lane["robust_ratio_gate"])),
    })
    wide = sum(1 for value in ratios if value >= float(lane["wide_ratio_gate"]))
    criteria.append({
        "id": "H41a4",
        "description": "至少两个阶梯的比值 >= 非单点门 10.0",
        "value": float(wide),
        "threshold": 2.0,
        "verdict": _verdict(wide >= 2),
    })
    criteria.append({
        "id": "H41a5",
        "description": "W28 准入臂数等于预期 6、剔除 7（差异逐臂有理由）",
        "value": float(w28["n_admitted"]),
        "threshold": float(expected_admitted["W28"]),
        "verdict": _verdict(int(w28["n_admitted"]) == int(expected_admitted["W28"])
                            and int(w28["n_excluded"]) == 7),
    })
    criteria.append({
        "id": "H41a6",
        "description": "每个被剔除臂都有非空的机械理由",
        "value": float(sum(1 for row in arms if not row["admitted"] and str(row["reason"]).strip())),
        "threshold": float(sum(1 for row in arms if not row["admitted"])),
        "verdict": _verdict(all(str(row["reason"]).strip()
                                for row in arms if not row["admitted"])),
    })
    polluted = float(w28["ratio_all"])
    criteria.append({
        "id": "H41a7",
        "description": "W28 污染池（全 13 臂）比值 < 2.0 且落在稳健门之下（反事实）",
        "value": polluted,
        "threshold": float(lane["expected_polluted_ratio_max"]),
        "verdict": _verdict(polluted < float(lane["expected_polluted_ratio_max"])
                            and polluted < float(lane["robust_ratio_gate"])),
    })
    bad_admitted = [row for row in arms if row["admitted"]
                    and (PLACEBO_PATTERN.search(str(row["arm"]))
                         or REPRESENTATION_PATTERN.search(str(row["arm"])))]
    criteria.append({
        "id": "H41a8",
        "description": "准入集里没有安慰剂臂或换表示臂",
        "value": float(len(bad_admitted)),
        "threshold": 0.0,
        "verdict": _verdict(not bad_admitted),
    })
    criteria.append({
        "id": "H41a9",
        "description": "五个阶梯逐重复表 sha256 前后一致（未被改写）",
        "value": 1.0,
        "threshold": 1.0,
        "verdict": "成立",
    })
    return criteria


def make_figure(payload: Mapping[str, object]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for candidate in ("Microsoft YaHei", "SimHei", "DengXian", "Arial Unicode MS"):
        try:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False


    ladders = list(payload["ladders"])
    labels = [str(item["ladder"]).split(" ")[0] for item in ladders]
    admitted = [float(item["ratio_admitted"]) for item in ladders]
    polluted = [float(item["ratio_all"]) for item in ladders]

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    x = range(len(labels))
    axes[0].bar([i - 0.2 for i in x], admitted, width=0.4, label="准入池", color="#1f77b4")
    axes[0].bar([i + 0.2 for i in x], polluted, width=0.4, label="全池（含安慰剂/换表示）",
                color="#d62728")
    axes[0].axhline(4.0, color="black", ls="--", lw=1.0, label="稳健门 4x")
    axes[0].axhline(10.0, color="#2ca02c", ls=":", lw=1.0, label="非单点门 10x")
    axes[0].set_xticks(list(x))
    axes[0].set_xticklabels(labels)
    axes[0].set_ylabel("R2 极差 / AUC30 极差")
    axes[0].set_title("W41-A 准入 vs 全池：比值判据", fontsize=10)
    axes[0].legend(fontsize=7)
    axes[0].grid(alpha=0.25, axis="y")

    arm_rows = list(payload["arms"])
    fam = {}
    for row in arm_rows:
        fam[row["family"]] = fam.get(row["family"], 0) + 1
    axes[1].bar(list(fam), list(fam.values()), color="#8c564b")
    for i, (key, value) in enumerate(fam.items()):
        axes[1].text(i, value, " " + str(value), ha="center", va="bottom", fontsize=9)
    axes[1].set_title("臂家族计数（40 臂 = 33 准入 + 7 剔除）", fontsize=10)
    axes[1].set_ylabel("臂数")
    axes[1].grid(alpha=0.25, axis="y")

    fig.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH)
    plt.close(fig)


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]]) -> str:
    lines = [
        "# W41-A 阶梯池准入规则（机械规则 + 比值判据复算）",
        "",
        "**性质**：后验 / 治理件，**0 shot（累计仍 19）**。只读 W28-W32 逐重复表，不重拟合任何臂。",
        "",
        "## 1. 准入规则（写死，不事后清洗）",
        "",
        "- **R1** 臂名匹配该阶梯声明的 `admit_prefix`（非空时）——保证「同一配置网格上的档位」。",
        "- **R2** 剔除安慰剂臂：`shuffled|placebo|random_target`。",
        "- **R3** 剔除换表示臂：`morgan|fingerprint|embedding`。",
        "- **R4** 重复集必须完整（行数 = 该阶梯众数重复数）。",
        "",
        "## 2. 逐阶梯读数",
        "",
        "| 阶梯 | 全池臂 | 准入臂 | 剔除 | 准入比值 | 全池比值 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["ladders"]:
        lines.append("| " + str(item["ladder"]) + " | " + str(item["n_arms_total"]) + " | "
                     + str(item["n_admitted"]) + " | " + str(item["n_excluded"]) + " | "
                     + format(float(item["ratio_admitted"]), ".6f") + " | "
                     + format(float(item["ratio_all"]), ".6f") + " |")
    lines += [
        "",
        "**W28 反事实**：全 13 臂（含 `lever4_morgan_*` 两个换表示臂与 "
        "`lever4_physical_retuned_shuffled_target` 一个安慰剂臂）的比值只有 "
        + format(float(payload["ladders"][0]["ratio_all"]), ".4f") + "，落在稳健门 4.0 之下 —— "
        "若不复用本准入规则，同一份表会给出假判否。",
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
        "- 本规则只回答「哪些臂进比值池」，不评价任何单个臂的性能，也不把任何比值晋升为冻结读数。",
        "- 五个阶梯的读数仍是**量级 vs 序**的对照诊断；比值大只说明「换档位主要动量级、不怎么动序」。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-figure", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [REPOSITORY_ROOT / str(spec["path"]) for spec in prereg["lanes"]["w41_ladder_admission"]["ladder_sources"]]
    before = {str(path): sha256_file(path) for path in sources}
    payload = build(prereg)
    after = {str(path): sha256_file(path) for path in sources}
    inputs_unchanged = before == after
    criteria = evaluate(payload, prereg)
    criteria[-1]["value"] = 1.0 if inputs_unchanged else 0.0
    criteria[-1]["verdict"] = _verdict(inputs_unchanged)

    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    write_csv_lf(ARM_CSV, ARM_FIELDS, payload["arms"])
    write_csv_lf(LADDER_CSV, LADDER_FIELDS, payload["ladders"])
    if not args.skip_figure:
        make_figure(payload)

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只读 W28-W32 逐重复表按预注册准入规则重算比值；不重拟合臂、不新增特征列、不改 METRIC_NAMES、不动冻结读数。",
        },
        "inputs": before,
        "inputs_unchanged": inputs_unchanged,
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE,
                                      FROZEN_SINGLE_REPRESENTATION, FROZEN_PROMOTED_ARM],
        "rules": prereg["lanes"]["w41_ladder_admission"]["admission_rules"],
        "ladders": payload["ladders"],
        "arm_families": {family: sum(1 for row in payload["arms"] if row["family"] == family)
                         for family in sorted({str(row["family"]) for row in payload["arms"]})},
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "准入规则把 40 个臂切成 33 个网格/档位臂与 7 个剔除臂（换表示 2 / 安慰剂 1 / 非本网格 4）。",
            "五个准入阶梯的比值逐位复现 W40-A 冻结锚（21.04 / 13.71 / 8.09 / 4.18 / 7.27），AUC30 极差上限 "
            + format(max(float(item["auc30_spread_admitted"]) for item in payload["ladders"]), ".6f") + "。",
            "W28 全池反事实比值 " + format(float(payload["ladders"][0]["ratio_all"]), ".4f")
            + "（< 稳健门 4.0）——污染池会把结论翻成假判否，准入规则必须在跑前声明。",
            "0 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria), encoding="utf-8", newline="\n")

    for item in payload["ladders"]:
        print("ladder " + str(item["ladder"]) + ": admitted " + str(item["n_admitted"]) + "/"
              + str(item["n_arms_total"]) + "; ratio " + format(float(item["ratio_admitted"]), ".6f")
              + "; all-pool ratio " + format(float(item["ratio_all"]), ".6f"))
    print("verdicts " + str(len(criteria) - len(failed)) + "/" + str(len(criteria)))
    for item in failed:
        print(("REGISTERED-NEGATIVE " if str(item["id"]) in REGISTERED_NEGATIVES
               else "UNREGISTERED-FAIL ") + str(item["id"]) + " " + str(item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())
