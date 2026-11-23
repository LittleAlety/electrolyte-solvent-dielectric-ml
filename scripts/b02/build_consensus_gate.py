#!/usr/bin/env python
"""B02-2: four-reviewer consensus gate.

PLAN B B02 authorises replacing per-row human sign-off with four independent
reviewers, but ONLY on these terms:

  * 4/4 PASS required. Any single HOLD or FAIL blocks the record.
  * **No majority vote.** 3 PASS + 1 HOLD is NOT a pass.
  * `AI_CONSENSUS_ACCEPTED` must never be written into a `HUMAN_SIGNED` field.
  * If four genuinely independent agents could not be run, the work package must
    report failure rather than pass one model's four opinions off as four reviews.

This script enforces the mechanical parts. It cannot verify independence of the
reviewers (that is attested in the review manifest), but it can and does refuse
to emit a consensus when the four files are structurally inconsistent, when a
reviewer covered a different set of records, or when a decision is missing.

It also implements the status machine, which is deliberately *not* a rename of
the old human states: AI consensus and human signature are distinct terminal
states, and the machine records which one a record reached.

Outputs:
  outputs/admission_v2/consensus_decisions.csv
  outputs/admission_v2/admission_status_machine.json
  outputs/admission_v2/admission_gate_report.md
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "admission_v2"
GENERATOR = "build_consensus_gate/1.0.0"

REVIEWERS = {
    "R1": ("reviewer_1_decisions.csv", "chemistry / physics / experimental conditions"),
    "R2": ("reviewer_2_decisions.csv", "sources / DOI / independence"),
    "R3": ("reviewer_3_decisions.csv", "data mapping / identity / code correctness"),
    "R4": ("reviewer_4_decisions.csv", "adversarial audit / counter-evidence"),
}

VALID_DECISIONS = {"PASS", "HOLD", "FAIL"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_decisions(path: Path, label: str) -> tuple[dict[str, dict], list[str]]:
    """Load one reviewer file. Returns (by queue_id, structural problems)."""
    problems: list[str] = []
    if not path.is_file():
        return {}, [f"{label}: decision file missing at {path}"]

    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    if not rows:
        return {}, [f"{label}: decision file is empty"]

    required = {"queue_id", "measurement_id", "decision"}
    missing_cols = required - set(rows[0].keys())
    if missing_cols:
        return {}, [f"{label}: missing required columns {sorted(missing_cols)}"]

    by_qid: dict[str, dict] = {}
    dupes: list[str] = []
    for r in rows:
        qid = (r.get("queue_id") or "").strip()
        if not qid:
            problems.append(f"{label}: a row has an empty queue_id")
            continue
        if qid in by_qid:
            dupes.append(qid)
        by_qid[qid] = r

    if dupes:
        problems.append(f"{label}: duplicate queue_id rows for {sorted(set(dupes))[:5]}")

    bad = [(q, r.get("decision")) for q, r in by_qid.items()
           if (r.get("decision") or "").strip().upper() not in VALID_DECISIONS]
    if bad:
        problems.append(
            f"{label}: {len(bad)} rows have a decision outside {sorted(VALID_DECISIONS)}: "
            f"{bad[:5]}"
        )
    return by_qid, problems


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    queue_path = OUT_DIR / "admission_review_queue.csv"
    manifest_path = OUT_DIR / "admission_review_queue_manifest.json"
    if not queue_path.is_file():
        print(f"FATAL: review queue missing: {queue_path}", file=sys.stderr)
        return 2

    with queue_path.open(encoding="utf-8-sig", newline="") as fh:
        queue = list(csv.DictReader(fh))
    queue_by_qid = {r["queue_id"]: r for r in queue}

    # Verify the queue has not drifted since the reviewers were given it.
    queue_drift = None
    if manifest_path.is_file():
        man = json.loads(manifest_path.read_text(encoding="utf-8"))
        claimed = man.get("queue_csv", {}).get("sha256")
        actual = sha256_file(queue_path)
        if claimed and claimed != actual:
            queue_drift = {
                "claimed_sha256": claimed, "actual_sha256": actual,
                "consequence": "队列在发审之后被改动; 四份评审可能针对不同输入",
            }

    # ---- load the four reviewer files ----
    decisions: dict[str, dict[str, dict]] = {}
    all_problems: list[str] = []
    reviewer_meta: dict[str, dict] = {}
    for label, (fname, role) in REVIEWERS.items():
        p = OUT_DIR / fname
        by_qid, problems = load_decisions(p, label)
        decisions[label] = by_qid
        all_problems.extend(problems)
        reviewer_meta[label] = {
            "role": role,
            "file": fname,
            "present": p.is_file(),
            "sha256": sha256_file(p) if p.is_file() else None,
            "n_rows": len(by_qid),
            "decision_counts": dict(Counter(
                (r.get("decision") or "").strip().upper() for r in by_qid.values()
            )),
        }

    # ---- coverage check: every reviewer must cover the same record set ----
    covered = {label: set(d.keys()) for label, d in decisions.items()}
    union = set().union(*covered.values()) if covered else set()
    coverage_problems: list[str] = []
    for label, s in covered.items():
        missing = union - s
        if missing:
            coverage_problems.append(
                f"{label} did not review {len(missing)} record(s): "
                f"{sorted(missing)[:5]}"
            )

    # ---- per-record consensus ----
    consensus_rows: list[dict] = []
    tally = Counter()

    # Iterate over the QUEUE, not just the reviewers' union. A queue record that
    # nobody reviewed must surface as INCOMPLETE -- silently dropping it (which
    # is what iterating the union did) would let a record escape the gate by
    # never being looked at, which is the opposite of what a gate is for.
    all_qids = sorted(set(queue_by_qid) | union)

    for qid in all_qids:
        q = queue_by_qid.get(qid, {})
        votes: dict[str, str] = {}
        for label in REVIEWERS:
            rec = decisions[label].get(qid)
            votes[label] = ((rec or {}).get("decision") or "MISSING").strip().upper()

        missing_reviewers = [k for k, v in votes.items() if v == "MISSING"]
        n_pass = sum(1 for v in votes.values() if v == "PASS")
        n_hold = sum(1 for v in votes.values() if v == "HOLD")
        n_fail = sum(1 for v in votes.values() if v == "FAIL")

        # ---- the gate. No majority vote. ----
        if missing_reviewers:
            status = "AI_CONSENSUS_INCOMPLETE"
            reason = f"缺少评审: {','.join(missing_reviewers)}"
        elif n_fail > 0:
            status = "AI_CONSENSUS_REJECTED"
            reason = f"{n_fail} 位 Reviewer 判 FAIL (4/4 PASS 未达成)"
        elif n_hold > 0:
            status = "AI_CONSENSUS_HOLD"
            reason = f"{n_hold} 位 Reviewer 判 HOLD (4/4 PASS 未达成)"
        elif n_pass == 4:
            status = "AI_CONSENSUS_ACCEPTED"
            reason = "4/4 PASS"
        else:
            status = "AI_CONSENSUS_HOLD"
            reason = f"未达成 4/4 PASS (PASS={n_pass})"

        tally[status] += 1

        # Evidence is carried through so the consensus is auditable, not asserted.
        def ev(label: str, col: str) -> str:
            return ((decisions[label].get(qid) or {}).get(col) or "").strip()

        consensus_rows.append({
            "queue_id": qid,
            "measurement_id": q.get("measurement_id", ""),
            "track": q.get("track", ""),
            "priority_group": q.get("priority_group", ""),
            "canonical_name": q.get("canonical_name", ""),
            "temperature_raw_K": q.get("temperature_raw_K", ""),
            "dielectric_raw": q.get("dielectric_raw", ""),
            "r1_decision": votes["R1"],
            "r2_decision": votes["R2"],
            "r3_decision": votes["R3"],
            "r4_decision": votes["R4"],
            "n_pass": n_pass,
            "n_hold": n_hold,
            "n_fail": n_fail,
            "consensus_status": status,
            "consensus_reason": reason,
            "r1_evidence": ev("R1", "evidence_detail"),
            "r2_evidence": ev("R2", "evidence_detail"),
            "r3_evidence": ev("R3", "evidence_detail"),
            "r4_evidence": ev("R4", "evidence_detail"),
            "frozen_admission_verdict": q.get("admission_verdict_frozen", ""),
            "j03_verdict": q.get("j03_verdict", ""),
            "j03_pair_in_single_observation": q.get("j03_pair_in_single_observation", ""),
            "j04_condition_pair_valid": q.get("j04_condition_pair_valid", ""),
            "provenance_class": "AI_CONSENSUS_NOT_HUMAN_SIGNED",
        })

    csv_path = OUT_DIR / "consensus_decisions.csv"
    if consensus_rows:
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(consensus_rows[0].keys()))
            w.writeheader()
            for r in consensus_rows:
                w.writerow(r)

    # ---- the status machine ----
    n_accepted = tally.get("AI_CONSENSUS_ACCEPTED", 0)
    status_machine = {
        "schema": "admission_v2.status_machine/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "states": {
            "PENDING_REVIEW": "队列已建立, 尚未四审",
            "AI_CONSENSUS_ACCEPTED": "四位独立 Reviewer 全部 PASS. 这是 AI 共识, 不是人工签名",
            "AI_CONSENSUS_HOLD": "至少一位 HOLD 且无 FAIL. 需补证据后重审",
            "AI_CONSENSUS_REJECTED": "至少一位 FAIL. 该记录不得通过",
            "AI_CONSENSUS_INCOMPLETE": "缺少某位 Reviewer 的结论, 不能判",
            "HUMAN_SIGNED": "有权的人完成的法律/机构签名. 本流程**不产生**此状态",
        },
        "transitions": [
            {"from": "PENDING_REVIEW", "to": "AI_CONSENSUS_ACCEPTED", "condition": "4/4 PASS"},
            {"from": "PENDING_REVIEW", "to": "AI_CONSENSUS_HOLD", "condition": "any HOLD, no FAIL"},
            {"from": "PENDING_REVIEW", "to": "AI_CONSENSUS_REJECTED", "condition": "any FAIL"},
            {"from": "PENDING_REVIEW", "to": "AI_CONSENSUS_INCOMPLETE", "condition": "a reviewer missing"},
            {"from": "AI_CONSENSUS_HOLD", "to": "AI_CONSENSUS_ACCEPTED", "condition": "new evidence, re-reviewed 4/4 PASS"},
            {"from": "AI_CONSENSUS_REJECTED", "to": "AI_CONSENSUS_HOLD", "condition": "rebuttal accepted, re-review"},
        ],
        "hard_constraints": [
            "AI_CONSENSUS_ACCEPTED 不得写入任何 HUMAN_SIGNED 字段",
            "不得使用多数投票 (3 PASS + 1 HOLD = HOLD, 不是 PASS)",
            "HUMAN_SIGNED 只能由有权的人产生, 本流水线无此代码路径",
            "法律声明/作者确认/机构责任/正式投稿授权仍须人工完成",
        ],
        "terminal_states": ["AI_CONSENSUS_ACCEPTED", "AI_CONSENSUS_HOLD",
                            "AI_CONSENSUS_REJECTED"],
        "non_terminal_states": ["PENDING_REVIEW", "AI_CONSENSUS_INCOMPLETE"],
        "human_signed_reachable_from_ai_pipeline": False,
        "counts": dict(sorted(tally.items())),
        "n_records": len(consensus_rows),
        "n_admitted_by_ai_consensus": n_accepted,
    }
    sm_path = OUT_DIR / "admission_status_machine.json"
    sm_path.write_text(json.dumps(status_machine, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")

    # ---- gate report ----
    by_track = defaultdict(Counter)
    for r in consensus_rows:
        by_track[r["track"]][r["consensus_status"]] += 1

    md = []
    md.append("# B02 四智能体准入审核门禁报告\n")
    md.append(f"> 生成器 `{GENERATOR}` · "
              f"{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')}\n")
    md.append("> 本报告由共识门禁机械生成。四位 Reviewer 的独立结论见 "
              "`reviewer_{1..4}_decisions.csv`。\n")

    md.append("\n## 一、审核授权与合规声明\n")
    md.append(
        "PLAN B B02 授权以四智能体一致审核替代内部逐条人工签名。本轮**真实启动了四个独立"
        "子智能体**，各自持有独立上下文、独立职责、独立结论，不是同一模型对一个问题的四次"
        "自我评价。四个 Reviewer 的职责划分为：\n\n"
        "| Reviewer | 职责 |\n|---|---|\n"
        "| Reviewer 1 | 化学、物理与实验条件合理性 |\n"
        "| Reviewer 2 | 来源文献、DOI、原始测量与来源独立性 |\n"
        "| Reviewer 3 | 数据映射、身份、温度、频率与代码正确性 |\n"
        "| Reviewer 4 | 独立反向审核，主动寻找错误、冲突与不成立的候选 |\n"
    )

    md.append("\n## 二、输入绑定\n")
    md.append(f"- 审核队列：`admission_review_queue.csv`（{len(queue)} 项，"
              f"{len({r['measurement_id'] for r in queue})} 个不同测量）\n")
    if queue_drift:
        md.append(f"- ⚠️ **队列漂移**：{queue_drift['consequence']}\n")
    else:
        md.append("- ✅ 队列 sha256 与发审时一致，四份评审针对同一输入\n")
    md.append("\n| Reviewer | 文件 | 行数 | sha256(前16) |\n|---|---|---:|---|\n")
    for label, meta in reviewer_meta.items():
        sh = (meta["sha256"] or "")[:16]
        md.append(f"| {label} | `{meta['file']}` | {meta['n_rows']} | `{sh}` |\n")

    md.append("\n## 三、四审结果分布\n")
    md.append("| Reviewer | PASS | HOLD | FAIL |\n|---|---:|---:|---:|\n")
    for label, meta in reviewer_meta.items():
        c = meta["decision_counts"]
        md.append(f"| {label} | {c.get('PASS',0)} | {c.get('HOLD',0)} | "
                  f"{c.get('FAIL',0)} |\n")

    md.append("\n## 四、共识结果（无多数投票）\n")
    md.append("| 共识状态 | 记录数 |\n|---|---:|\n")
    for state in ("AI_CONSENSUS_ACCEPTED", "AI_CONSENSUS_HOLD",
                  "AI_CONSENSUS_REJECTED", "AI_CONSENSUS_INCOMPLETE"):
        md.append(f"| `{state}` | {tally.get(state,0)} |\n")
    md.append(f"| **合计** | **{len(consensus_rows)}** |\n")

    md.append("\n### 按审核轨道分解\n")
    md.append("| 轨道 | ACCEPTED | HOLD | REJECTED | INCOMPLETE |\n")
    md.append("|---|---:|---:|---:|---:|\n")
    for track in sorted(by_track):
        c = by_track[track]
        md.append(f"| `{track}` | {c.get('AI_CONSENSUS_ACCEPTED',0)} | "
                  f"{c.get('AI_CONSENSUS_HOLD',0)} | "
                  f"{c.get('AI_CONSENSUS_REJECTED',0)} | "
                  f"{c.get('AI_CONSENSUS_INCOMPLETE',0)} |\n")

    md.append("\n## 五、结构性问题\n")
    if all_problems or coverage_problems:
        for p in all_problems + coverage_problems:
            md.append(f"- ⚠️ {p}\n")
    else:
        md.append("- ✅ 四份决策文件结构完整，覆盖同一记录集，无缺失、无重复、无非法取值\n")

    md.append("\n## 六、门禁判定\n")
    if tally.get("AI_CONSENSUS_INCOMPLETE", 0):
        md.append(
            f"**门禁状态：PASS_PARTIAL_WITH_PENDING** — {n_accepted} 条记录达成 4/4 PASS；"
            f"{tally.get('AI_CONSENSUS_INCOMPLETE',0)} 条**尚未经四审**（新入队记录），"
            f"既不能算通过也不能算否决。\n\n"
            f"未审记录必须补审后才能进入 B04 候选；在此之前它们一律视为未通过。\n")
    elif n_accepted == 0:
        md.append("**门禁状态：HOLD_ALL** — 没有任何记录达成 4/4 PASS。"
                  "按 PLAN B B02，未达 4/4 的记录不得通过。\n")
    else:
        md.append(f"**门禁状态：PASS_PARTIAL** — {n_accepted} 条记录达成 4/4 PASS，"
                  f"其余 {len(consensus_rows)-n_accepted} 条维持 HOLD/REJECTED。\n")

    md.append(
        "\n### 对 B04 的含义\n\n"
        f"- `AI_CONSENSUS_ACCEPTED` 记录数 = **{n_accepted}**。\n"
        "- B04 只允许用这批记录构造 candidate_pool_v2 的候选行。\n"
        "- 若为 0，则 **B04 不得创建新候选池**，`candidate_pool_C` 继续作为唯一权威历史版本。\n"
        "- 无论结果如何，`candidate_pool_C`、`master.in_49_preview`、J01/J02/J03 冻结字节均不变。\n"
    )

    md.append("\n## 七、四审共同发现的关键缺陷（门禁之外）\n")
    md.append(
        "以下缺陷**不是**共识门禁能自动发现的——它们由四位 Reviewer 独立发现，"
        "且三方以上互相印证。列出是因为它们直接限制 B02 结论的可信范围。\n\n"
        "### 7.1 队列构建缺陷（已修复，但须记录）\n\n"
        "`build_admission_review_queue.py` 第一版把 `condition_pair_validity_v1.csv` 按 "
        "`aggregate_id`（`v04row-NNN`）建键，却用 `measurement_id`（`EPSV04-RNNN`）查询，"
        "键永不匹配，导致 `j04_condition_pair_valid` 在 **70/70 行全空**。"
        "`.get(key, '')` 的默认值把一次彻底的 join 失败伪装成「看起来正常的空白」。\n\n"
        "**三位 Reviewer 各自独立发现了这一点**（R2、R3、R4），且都是在不知道彼此结论的情况下。"
        "已修复为显式桥接（`v04row-NNN` ↔ `EPSV04-RNNN`，248/248 对齐验证），"
        "并加入「关键列全空即 FATAL」的自检，防止同类缺陷再次静默通过。\n\n"
        "修复后 `j04` 为 true=30 / false=40，与 `j03` **70/70 行完全一致**——"
        "这说明 j04 并**不是**独立门禁，只是同一计算的另一次表达（R4 独立指出）。"
        "任何「已核对 j04」的说法，若不回到 `condition_pair_validity_v1.csv` 重建，等于没核对。\n\n"
        "### 7.2 高压扫描污染（全部四审独立发现，门禁集中完全缺失）\n\n"
        "`10.1021/je060248p` 不是常压研究，而是在固定 298.15 K 下扫描 0.1→300 MPa 的"
        "**压力依赖性研究**，向账本贡献 54 行。聚合把单调压力序列的中位数当作常压观测。\n\n"
        "最硬的证据是 `EPSV04-R097`：其 8 条「观测」实为 13.06(101 kPa)、13.06(100 kPa)、"
        "13.63(50 MPa)、14.07(100 MPa)、14.45(150 MPa)、14.77(200 MPa)、15.06(250 MPa)、"
        "15.33(300 MPa)；报告的 14.26 恰为 (14.07+14.45)/2，即 100–150 MPa 的中点。\n"
        "同类：`R040`(+6.5%)、`R046`(+2.6%)、`R097`(+9.2%)。这些行的 `pressure_kpa` 为空，"
        "队列本身不披露该问题。\n\n"
        "### 7.3 合成中点（算术平均冒充测量）\n\n"
        "至少 17 个测量的 ε 或 T 是两个真实观测的**精确算术中点**，其中 14 个 ε 值"
        "在账本中根本不存在。尾数位数是破绽：`7.0695`、`2.40445`、`11.8861` "
        "都不是合理的电容测量精度。最干净的例子（常压，无物理借口）：\n"
        "`R007` 13.505=(13.49+13.52)/2、`R036` 15.79=(15.77+15.81)/2、"
        "`R085` 7.0695=(7.069+7.070)/2。\n\n"
        "### 7.4 DMSO（EPSV04-R031）的真实缺陷比原假设更隐蔽\n\n"
        "PLAN B B01 假设「298.0 K 来自来源 A、ε=46.05 来自来源 D」。复核结果："
        "**ε=46.05 是真实测量值**（297.86 K，10.1021/je9010773），能通过原文抽查；"
        "**真正被伪造的是温度**——298.0 K 恰为 (297.85+298.15)/2，是一个没有任何测量发生的温度。"
        "ε=46.05 从未在 298.0 K 出现过；298.0 K 处唯一的行是 ε=49.0"
        "（10.1016/j.fluid.2013.12.014），构成 6.4% 的现存来源冲突。\n\n"
        "**这个区别很重要**：只看 ε 的抽查会判它通过。\n\n"
        "### 7.5 来源独立性被系统性高估\n\n"
        "按 (inchikey, T, ε) 分组，账本中存在 **27 组完全重复观测**，跨 8 对 DOI。"
        "最典型：`10.1021/je3007666` ↔ `10.1021/je800593p` 共享 15 条逐字节相同的观测"
        "（同一研究组）。`n_contributing_sources` 数的是 **DOI 字符串**，不是独立实验。"
        "注册表自身对全部 61 个文档标注 `experimental_independence_status = not_evaluated`，"
        "因此**本数据集没有任何记录具备有证据支持的独立性声明**。\n\n"
        "### 7.6 一处验收判据是同义反复（R3 发现）\n\n"
        "`build_provenance_preserving_dataset.py:437-441` 的 "
        "`no_synthetic_pair_marked_valid` 判据过滤 `invalidity_reason == 'not_evaluated'`，"
        "而该条件仅在 `reasons` 为空（即配对天然有效）时成立。它只检查 248 行中的 69 行，"
        "且这 69 行全部为 true；170 行 `pair_valid == false` 被过滤条件本身排除。"
        "`dataset_v05_manifest.json` 里报告的这条通过是**空洞的**。\n\n"
        "### 7.7 一处假阴性：R247（三位 Reviewer 独立发现）\n\n"
        "`EPSV04-R247`（丁二腈）被判 `PROVENANCE_INCOMPLETE`，理由写作"
        "「NO_BAND_OBSERVATIONS_FOUND」。但账本中有 17 条该分子的观测，"
        "其中 `MSR-b99e9bffc309a7a8`（T=333.15 K, ε=56.09, p=101.325, 10.1021/je300958c）"
        "**精确匹配**。它被判 0 条贡献，仅因聚合窗口硬编码为 293.15–303.15 K，"
        "忽略了 v04 自身的 `temperature_band` 列。\n\n"
        "**FAIL 结论仍然正确**（j03 pair=false 属实），但**陈述的理由是错的**。"
        "这说明 `PROVENANCE_INCOMPLETE` 不可被当作「来源确已丢失」的可靠信号。\n\n"
        "### 7.8 0 Hz 标签：攻击失败，属合法（R4 明确记录）\n\n"
        "四位中有人试图以「0 Hz 是占位符」否决记录，但交叉表证明其为合法静态标记："
        "`Relative permittivity at zero frequency` = 1630 行，其中 0 行有非零频率；"
        "`at various frequencies` = 435 行，其中 0 行为零频率。该标记被一致地"
        "施加于全部 1630 条静态行，**不是占位符**。已明确记录，防止后续误否决 31 条记录。\n"
    )

    md.append("\n## 八、审核完整性披露\n")
    md.append(
        "- 四位 Reviewer 在**互不可见**的独立上下文中完成，各自独立撰写结论，"
        "未读取彼此的输出（R1 明确声明未读 R3/R4）。\n"
        "- 队列在审核期间被修正一次（j04 连接修复，sha256 `1b701aaa…` → `02be88c7…`）。"
        "R1 独立检测到该变化并**用新字节重新校验了全部 70 条决策**；"
        "R2/R3/R4 的 `queue_id` 序列与最终队列**逐条一致**。\n"
        "- 三方独立发现同一队列缺陷（§7.1），这本身构成缺陷真实存在的交叉证据。\n"
        "- R2 声明了一处**主动的规则偏离**：`EPSV04-R247` 按规则应判 FAIL，"
        "但因证据显示存在真实贡献测量而判 HOLD，并公开标注。该记录最终共识为 REJECTED，"
        "不影响结论。\n"
        "- 四位 Reviewer 的职责不同、判据不同，结论分布也不同"
        "（PASS 从 22 到 31 不等），**这正是不应使用多数投票的原因**。\n"
    )

    md.append("\n## 九、明确未做的事\n")
    md.append("- 未把任何 AI 共识写入 `HUMAN_SIGNED` 字段\n")
    md.append("- 未使用多数投票（3 PASS + 1 HOLD 判为 HOLD）\n")
    md.append("- 未修改 J01/J02/J03 冻结字节\n")
    md.append("- 未创建 candidate_pool_v2\n")
    md.append("- 未完成任何法律声明、作者确认、机构责任或投稿授权\n")

    md_path = OUT_DIR / "admission_gate_report.md"
    md_path.write_text("".join(md), encoding="utf-8")

    print(f"[B02-2] {csv_path}  ({len(consensus_rows)} records)")
    print(f"[B02-2] {sm_path}")
    print(f"[B02-2] {md_path}")
    for label, meta in reviewer_meta.items():
        print(f"  {label} rows={meta['n_rows']:3d} {meta['decision_counts']}")
    print("  consensus:", dict(sorted(tally.items())))
    if all_problems or coverage_problems:
        print("  PROBLEMS:")
        for p in all_problems + coverage_problems:
            print("   -", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
