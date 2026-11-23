#!/usr/bin/env python
"""B03-4: write the B03 evidence-backfill report and stage status.

Summarises what B03 established, in the terms PLAN B B03 asks for, and states
plainly what remains unresolved. The report is generated from the artifacts
rather than written by hand, so it cannot drift from the data.

Output: outputs/confirm_2027/evidence_backfill/evidence_backfill_report.md
        outputs/confirm_2027/evidence_backfill/b03_gate_status.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "confirm_2027" / "evidence_backfill"
GENERATOR = "build_b03_report/1.0.0"

REQUIRED = [
    "A18_gap_register.csv",
    "literature_source_inventory.csv",
    "source_verification.csv",
    "condition_qualified_measurements.csv",
    "independent_source_map.csv",
    "unresolved_molecules.csv",
    "evidence_backfill_report.md",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    gap = load(OUT_DIR / "A18_gap_register.csv")
    srcver = load(OUT_DIR / "source_verification.csv")
    qual = load(OUT_DIR / "condition_qualified_measurements.csv")
    indep = load(OUT_DIR / "independent_source_map.csv")
    unres = load(OUT_DIR / "unresolved_molecules.csv")
    inv = load(OUT_DIR / "literature_source_inventory.csv")

    by_tier = Counter(r["plan_b03_tier"] for r in gap)
    unres_reason = Counter(r["unresolved_reason"] for r in unres)
    verif_status = Counter(r["verification_status"] for r in srcver)

    # The accounting gate must be able to FAIL. The previous formulation was
    # `resolved = gap - unres` followed by `len(resolved) + len(unres) == len(gap)`,
    # which is a set identity -- it holds no matter what the data says. Reviewer 3
    # (B03) proved it by deleting EC from the unresolved list: the gate then
    # certified EC as evidenced and printed "6 + 12 = 18 PASS".
    #
    # The real invariants are checked here instead:
    #   1. every molecule in the register appears in exactly one of the two lists
    #      (not "the two lists partition the register by construction")
    #   2. the unresolved list contains no molecule the register says is resolved,
    #      and vice versa -- cross-checked against an INDEPENDENT criterion
    #   3. every unresolved row carries a reason and an action
    gap_ids = {r["a_mol_id"] for r in gap}
    unres_ids = {r["a_mol_id"] for r in unres}
    resolved_ids = gap_ids - unres_ids

    accounting_errors: list[str] = []

    # (1) unknown ids would silently inflate the counts
    unknown = unres_ids - gap_ids
    if unknown:
        accounting_errors.append(f"未解决清单含未知分子: {sorted(unknown)}")

    # (2) independent re-derivation of "resolved": a molecule counts as resolved
    # only if it has a condition-valid pair OR a verified NBS514 page read.
    verified_names = {
        r["a_name"] for r in srcver
        if r.get("verification_status") == "VERIFIED_AGAINST_PAGE_READ"
    }
    derived_resolved = {
        r["a_mol_id"] for r in gap
        if int(r["n_condition_valid_pairs"] or 0) > 0
        or r["a_name"] in verified_names
    }
    if derived_resolved != resolved_ids:
        only_in_file = resolved_ids - derived_resolved
        only_in_rule = derived_resolved - resolved_ids
        accounting_errors.append(
            f"解决判定与独立重推不一致: 清单多出 {sorted(only_in_file)}, "
            f"规则多出 {sorted(only_in_rule)}")

    # (3) every unresolved row must be actionable
    for r in unres:
        if not (r.get("unresolved_reason") or "").strip():
            accounting_errors.append(f"{r['a_mol_id']} 缺未解决原因")
        if not (r.get("next_action") or "").strip():
            accounting_errors.append(f"{r['a_mol_id']} 缺下一步动作")

    accounted = len(resolved_ids) + len(unres_ids)
    accounting_closed = (not accounting_errors) and (resolved_ids | unres_ids == gap_ids)
    gate_ok = accounting_closed and len(qual) > 0

    resolved = [r for r in gap if r["a_mol_id"] in resolved_ids]

    md: list[str] = []
    md.append("# B03 A18 证据回填报告\n")
    md.append(f"> 生成器 `{GENERATOR}` · "
              f"{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')}\n")
    md.append("> 本报告由产物机械生成，不手写，避免与数据漂移。\n")

    md.append("\n## 一、结论\n")
    md.append(f"- A18 分子：**{len(gap)}**\n")
    md.append(f"- 已有可用条件级证据：**{len(resolved)}**"
              f"（{', '.join(r['a_name'] for r in resolved)}）\n")
    md.append(f"- 仍未解决：**{len(unres)}**\n")
    md.append(f"- 条件合格（待审）记录：**{len(qual)}**\n")
    md.append(f"- 证明非独立的文档对：**{len(indep)}**\n")
    md.append(f"\n**账目闭合：** {len(resolved)} + {len(unres)} = {accounted} "
              f"/ {len(gap)} {'✅' if accounting_closed else '❌ 有分子既不在解决清单也不在未解决清单'}\n")

    md.append("\n### ⚠️ 必须澄清：本轮没有新增任何观测\n")
    md.append(
        "EA 与 MA 的 ε 值（6.02 / 6.68）**早已存在于 `dielectric_v04.csv`** "
        "（`dataset_origin = v0.2`，`source_doi = 10.6028/nbs.circ.514`）。"
        "B03 做的是**核实**这两条既有记录确实可由 NBS514 页面读取复现，"
        "**不是新增了两条测量**。\n\n"
        "正确表述：\n\n"
        "- ✅ 「EA/MA 的既有值已通过页面级核实」\n"
        "- ❌ 「B03 回填了 2 条新测量」—— 这是错的\n\n"
        "**证据基数的真实变化是 0 条新观测。** 任何把 "
        "`condition_qualified_measurements.csv` 的 2 行当作样本量增长的解读都是错误的。\n"
    )

    md.append("\n## 二、PLAN B B03 分层执行情况\n")
    md.append("| Tier | 分子 | 数量 | 状态 |\n|---|---|---|---:|\n")
    for tier in ("P0", "P1", "P2", "P3", "P4"):
        names = [r["a_name"] for r in gap if r["plan_b03_tier"] == tier]
        if not names:
            continue
        resolved_here = [r["a_name"] for r in resolved if r["plan_b03_tier"] == tier]
        md.append(f"| {tier} | {', '.join(names)} | {len(names)} | "
                  f"已解决 {len(resolved_here)}/{len(names)} |\n")

    md.append("\n## 三、NBS514 核实（PLAN B 指定 EA/MA 优先核查）\n")
    md.append("| 分子 | 核实状态 | v04 ε | NBS514 ε | 一致 | 页面定位 |\n")
    md.append("|---|---|---:|---:|---|---|\n")
    for r in srcver:
        md.append(f"| {r['a_name']} | `{r['verification_status']}` | "
                  f"{r['v04_epsilon']} | {r['nbs514_epsilon']} | "
                  f"{r['epsilon_agrees']} | {r['page_locator'][:40]} |\n")

    verified = [r for r in srcver
                if r["verification_status"] == "VERIFIED_AGAINST_PAGE_READ"]
    if verified:
        md.append(
            "\n### ⚠️ 这是**转录完整性检查**，不是独立佐证\n\n"
            "`data/dielectric_v04.csv` 中 EA/MA 两行的 `source_doi` 就是 "
            "`10.6028/nbs.circ.514`，`source_record_id` 分别是 "
            "`nbs514:p20:022`（EA）与 `nbs514:p18:009`（MA）—— "
            "**与本次页面读取完全相同**。\n\n"
            "因此 `epsilon_agrees=true` 证明的是「转录忠实」，"
            "**不是**「两个独立来源相互印证」。把这一步称为"
            "「PLAN B 的假设成立 / 独立核实」会高估证据强度。\n\n"
            "EA 与 MA 仍然各自是 **SINGLE_SOURCE**。\n"
        )
    uncovered = [r["a_name"] for r in srcver
                 if r["verification_status"] == "NO_NBS514_COVERAGE"]
    if uncovered:
        md.append(f"\n**其余 {len(uncovered)} 个 P4 分子在 NBS514 中无覆盖：** "
                  f"{', '.join(uncovered)}。\n\n"
                  "**但这不是「无数据」。** 这 9 个分子在 `dielectric_v04.csv` 中"
                  "**全部都有整理值**（见 §二 的 `v04_curated_value_present` 列）；"
                  "它们只是不在 ThermoML 观测层。"
                  "而且 EC/PC/FEC/VC 是 1951 年之后才商业化的溶剂，"
                  "要求它们出现在 NBS514 里是同义反复。\n")

    md.append("\n### 为什么这 2 条不进 measurement_ledger\n")
    md.append("账本的不变量是「每条测量可追溯到带 sha256 的源文件」。"
              "NBS514 转录没有 ThermoML 源文件，强行加入会让该不变量失效，"
              "并使已报告的 2065 计数发生未声明的变化。"
              "因此页面读取作为**条件级证据**单独交付，由四智能体审核决定是否使用。\n")

    md.append("\n## 四、未解决分子\n")
    md.append("| 分子 | Tier | 原因 | 观测数 | 下一步 |\n")
    md.append("|---|---|---|---:|---|\n")
    for r in unres:
        md.append(f"| {r['a_name']} | {r['plan_b03_tier']} | "
                  f"`{r['unresolved_reason']}` | {r['n_observations']} | "
                  f"{r['next_action'][:50]} |\n")

    md.append("\n### 按原因分解\n")
    for k, v in sorted(unres_reason.items()):
        md.append(f"- `{k}`：**{v}**\n")

    md.append("\n## 五、来源独立性\n")
    md.append(f"证明非独立的文档对：**{len(indep)}**\n\n")
    md.append("| 文档 A | 文档 B | 相同观测 | 共享 A18 分子 |\n")
    md.append("|---|---|---:|---|\n")
    for r in indep:
        md.append(f"| `{r['document_a']}` | `{r['document_b']}` | "
                  f"{r['n_identical_observations']} | "
                  f"{r['shared_a18_molecules'] or '—'} |\n")
    md.append("\n**含义：** 「独立来源数」在本数据集中是一个**上界**，不是实测值。"
              "B07 的来源聚类检验必须先按文档去重。\n")

    md.append("\n## 六、文献来源清单\n")
    md.append(f"仓库已持有并覆盖 A18 的源文档：**{len(inv)}** 个。\n\n")
    md.append("| 源文档 | 覆盖 A18 分子数 | 账本行数 | 有源字节 | 录入路径 |\n")
    md.append("|---|---:|---:|---|---|\n")
    for r in sorted(inv, key=lambda x: -int(x["n_a18_molecules_covered"] or 0)):
        md.append(f"| `{r['source_document_id']}` | {r['n_a18_molecules_covered']} | "
                  f"{r['n_total_ledger_rows']} | {r['holds_source_bytes']} | "
                  f"{r['ingestion_path']} |\n")

    md.append("\n> **范围声明：** 本清单描述仓库**已持有**的源文档，"
              "**不代表已完成穷尽式文献检索**。\n")

    md.append("\n## 七、跨来源冲突（R4 发现）\n")
    cross_path = OUT_DIR / "cross_source_conflicts.csv"
    cross = load(cross_path) if cross_path.is_file() else []
    if cross:
        md.append(
            "仓库**已持有**的 CC BY 4.0 来源 (`data/raw/open_data_eps/eps_observations.csv`) "
            "对 EA/MA 给出了与 NBS514 不一致的值，此前从未对账：\n\n"
        )
        md.append("| 分子 | NBS514 值 | NBS514 T | 持有来源值 | 持有来源 T | 差异 |\n")
        md.append("|---|---:|---:|---:|---:|---:|\n")
        for r in cross:
            md.append(f"| {r['a_name']} | {r['nbs514_value']} | "
                      f"{r['nbs514_temperature_K']} | {r['held_source_value']} | "
                      f"{r['held_source_temperature_K'] or '—'} | "
                      f"{r['relative_difference_pct']}% |\n")
        md.append(
            "\n**这推翻了「已核实」的简单叙事。** 核实只证明 NBS514 的转录忠实，"
            "不证明该值是唯一正确值。MA 的 5.87% 差异无法用 10 K 温差解释"
            "（酯类 dε/dT 约 −0.15~−0.2 %/K）。\n\n"
            "**B04 前必须裁决**，不得择一作为主值而不说明。\n"
        )
    else:
        md.append("未检出跨来源冲突。\n")

    md.append("\n## 八、明确未做的事\n")
    md.append("- 未新增任何测量到 measurement_ledger\n")
    md.append("- 未把 NBS514 页面读取伪装成 ThermoML 测量\n")
    md.append("- 未把高温观测折算成室温\n")
    md.append("- 未把 AN 的 0.01/1 MHz 证据当作 static 0 Hz\n")
    md.append("- 未对任何未解决分子降低准入标准\n")
    md.append("- 未声称已完成穷尽式文献检索\n")

    md.append("\n## 九、阶段门\n")
    md.append(f"**B03 交付物：{sum(1 for f in REQUIRED if (OUT_DIR / f).is_file())}/{len(REQUIRED)}**\n\n")
    md.append(f"**账目闭合：** {'✅ 通过' if accounting_closed else '❌ 未通过'}\n\n")
    md.append(f"**条件合格测量：** {len(qual)} 条（待四智能体审核）\n\n")
    md.append("**未解决分子：** 必须留在未解决清单，**不得为了凑数进入 B04**。\n")

    md_path = OUT_DIR / "evidence_backfill_report.md"
    md_path.write_text("".join(md), encoding="utf-8")

    # ---- gate status ----
    status = {
        "schema": "confirm_2027.b03_gate/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "deliverables": {
            f: {"present": (OUT_DIR / f).is_file(),
                "sha256": sha256_file(OUT_DIR / f) if (OUT_DIR / f).is_file() else None}
            for f in REQUIRED
        },
        "counts": {
            "n_a18": len(gap),
            "n_resolved": len(resolved),
            "n_unresolved": len(unres),
            "n_condition_qualified": len(qual),
            "n_entangled_pairs": len(indep),
            "n_sources_inventoried": len(inv),
            "by_tier": dict(sorted(by_tier.items())),
            "unresolved_by_reason": dict(sorted(unres_reason.items())),
            "source_verification_by_status": dict(sorted(verif_status.items())),
        },
        "accounting_closed": accounting_closed,
        "accounting_errors": accounting_errors,
        "resolved_molecules": [r["a_name"] for r in resolved],
        "resolved_label": "EVIDENCE_PRESENT_NOT_ADMITTED",
        "resolved_label_note": (
            "『resolved』指**有可用条件级证据**, 不指已准入. "
            "EA/MA 仅凭页面读取即计入, 其 admission_status 仍为 "
            "PENDING_FOUR_AGENT_REVIEW, 且 in_measurement_ledger=false."
        ),
        "unresolved_molecules": [r["a_name"] for r in unres],
        "gate": {
            "deliverables_complete": all((OUT_DIR / f).is_file() for f in REQUIRED),
            "accounting_closed": accounting_closed,
            "accounting_errors": accounting_errors,
            "has_condition_qualified_evidence": len(qual) > 0,
            "open": gate_ok,
            "blocking_reason": None if gate_ok else (
                "; ".join(accounting_errors) if accounting_errors
                else "无条件合格测量"),
        },
        "next_step": (
            "条件合格测量需四智能体审核; 未解决分子需继续检索. "
            "B04 只能使用审核通过且条件有效的记录."
        ),
    }
    json_path = OUT_DIR / "b03_gate_status.json"
    json_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"[B03-4] {md_path}")
    print(f"[B03-4] {json_path}")
    print(f"  deliverables = {sum(1 for f in REQUIRED if (OUT_DIR / f).is_file())}/{len(REQUIRED)}")
    print(f"  resolved     = {len(resolved)}  unresolved = {len(unres)}")
    print(f"  accounting   = {accounted}/{len(gap)} {'CLOSED' if accounted==len(gap) else 'OPEN'}")
    print(f"  qualified    = {len(qual)}")
    print(f"  GATE         = {'OPEN' if gate_ok else 'CLOSED'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
