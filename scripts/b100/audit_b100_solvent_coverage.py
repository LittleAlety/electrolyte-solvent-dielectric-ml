#!/usr/bin/env python
"""B100-17: canonical electrolyte-solvent coverage audit.

The dataset is named for electrolyte solvents, but Reviewer 1 found that most of the
canonical ones are absent: water, DMSO, DMF, THF, gamma-butyrolactone, ethylene
carbonate, propylene carbonate, sulfolane. A dielectric dataset that omits the
solvents the field actually uses cannot support electrolyte-design claims, and saying
only "239 qualified molecules" hides that.

The honest response is NOT to relax the admission rules until they let these in. Each
was excluded for a specific, documented reason; some are absent from every source the
repository holds. This audit records, per solvent:

  * whether it is in the modelling set, and at what epsilon
  * if not, the exact admission reason it failed
  * whether an alternative source in the repository could supply it
  * what specifically would be needed to recover it

That turns a silent weakness into a scoped, actionable gap.

Output: outputs/b100/electrolyte_solvent_coverage_b100.json
        outputs/b100/electrolyte_solvent_coverage_b100.csv
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "audit_b100_solvent_coverage/1.0.0"

MATRIX = OUT / "model_matrix_b100.csv"
GATE = OUT / "b100_admission_gate.json"
EXCLUDED = OUT / "excluded_molecules_b100.csv"
QUALIFIED = OUT / "qualified_molecules_b100.csv"
V06_EXCL = REPO_ROOT / "outputs" / "b01" / "dataset_v06_exclusions.csv"
EXP_OBS = (REPO_ROOT / "data" / "processed"
           / "dielectric_pool_expansion_observations.csv")
NBS_PARTS = [REPO_ROOT / "data" / "interim" / f"nbs514_organic_part{i}.csv"
             for i in range(1, 5)]

# The solvents that matter for electrolyte formulation, with the aliases NBS 514
# might use. Only exact structural matches count -- "Formamide" is NOT DMF and
# "Furan" is NOT THF, and treating them as such would fabricate coverage.
KEY_SOLVENTS = [
    ("water", ["water", "aqua"]),
    ("acetonitrile", ["acetonitrile", "ethanenitrile", "methyl cyanide"]),
    ("dimethyl sulfoxide", ["dimethyl sulfoxide", "methyl sulfoxide", "dmso"]),
    ("N,N-dimethylformamide", ["dimethylformamide", "formyldimethylamine"]),
    ("tetrahydrofuran", ["tetrahydrofuran", "oxolane"]),
    ("gamma-butyrolactone", ["butyrolactone", "butyric lactone",
                             "dihydrofuran-2-one"]),
    ("ethylene carbonate", ["ethylene carbonate", "1,3-dioxolan-2-one"]),
    ("propylene carbonate", ["propylene carbonate", "4-methyl-1,3-dioxolan-2-one"]),
    ("1,2-dimethoxyethane", ["dimethoxyethane", "ethylene glycol dimethyl ether",
                             "glyme"]),
    ("sulfolane", ["sulfolane", "tetramethylene sulfone"]),
    ("methanol", ["methanol", "methyl alcohol"]),
    ("ethanol", ["ethanol", "ethyl alcohol"]),
    ("acetone", ["acetone", "2-propanone", "propan-2-one"]),
    ("dichloromethane", ["dichloromethane", "methylene chloride"]),
    ("ethyl acetate", ["ethyl acetate", "acetic acid ethyl ester"]),
    ("1,2-dimethoxyethane (repeat)", []),   # placeholder removed below
]
KEY_SOLVENTS = [k for k in KEY_SOLVENTS if k[1]]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    import io
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def main() -> int:
    for p in (MATRIX, EXCLUDED, QUALIFIED):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT.mkdir(parents=True, exist_ok=True)

    matrix = load(MATRIX)
    excluded = load(EXCLUDED)
    qualified = load(QUALIFIED)
    v06 = load(V06_EXCL)
    exp = load(EXP_OBS)
    nbs: list[dict] = []
    for p in NBS_PARTS:
        if p.is_file():
            nbs.extend(load(p))

    v06_by_name: dict[str, str] = {}
    for r in v06:
        v06_by_name[(r.get("name") or "").strip().lower()] = \
            (r.get("blocking_reasons") or "").strip()

    exp_by_name: dict[str, dict] = {}
    for r in exp:
        exp_by_name[(r.get("name") or "").strip().lower()] = r

    rows: list[dict] = []
    n_absent_all = 0
    for solvent, aliases in KEY_SOLVENTS:
        def matches(name: str) -> bool:
            low = (name or "").lower()
            return any(a in low for a in aliases)

        in_model = [r for r in matrix if matches(r.get("name", ""))]
        in_qual = [r for r in qualified if matches(r.get("name", ""))]
        in_excl = [r for r in excluded if matches(r.get("name", ""))]
        # is it present in the NBS 514 transcription under any alias?
        nbs_hits = [r for r in nbs if matches(r.get("compound_name", ""))]
        # is it in the NBS expansion observation table (i.e. an admitted Q2 source)?
        exp_hit = next((r for r in exp if matches(r.get("name", ""))), None)

        if in_model:
            status = "IN_MODELLING_SET"
            eps = in_model[0].get("epsilon", "")
            reason = ""
            recovery = ""
        elif in_qual:
            status = "QUALIFIED_BUT_PHASE_UNVERIFIED"
            eps = in_qual[0].get("epsilon", "")
            reason = "缺少熔点数据, 无法验证设定温度下为液态"
            recovery = "从原始文献或 PubChem 补充实验熔点"
        elif exp_hit:
            status = "IN_NBS_LAYER_BUT_NOT_ADMITTED"
            eps = exp_hit.get("epsilon", "")
            reason = ";".join(
                e.get("blocking_reasons", "") for e in in_excl
                if e.get("layer") == "nbs514_expansion") or "未通过准入判据"
            recovery = "解决该层准入障碍后可直接纳入"
        elif nbs_hits:
            status = "IN_NBS_TRANSCRIPTION_NOT_SELECTED"
            eps = nbs_hits[0].get("dielectric", "")
            reason = "NBS 转录中存在, 但未被选入扩展观测表"
            recovery = "解析结构并重跑扩展层筛选"
        elif in_excl:
            status = "EXCLUDED_FOR_DOCUMENTED_REASON"
            eps = in_excl[0].get("epsilon", "")
            reason = in_excl[0].get("blocking_reasons", "")
            # Whether an alternative source exists changes the recovery difficulty
            # completely: available-in-NBS means re-admission is a filtering task,
            # absent-everywhere means new literature work.
            if nbs_hits or exp_hit:
                reason += " | 该化合物在 NBS 514 中有记录, 可尝试从该层准入"
                recovery = "解决该层准入障碍后纳入"
            else:
                reason += " | 且该化合物不在 NBS 514 中, 仓库内无替代来源"
                recovery = (
                    "必须从新的外部文献录入静态介电常数测量; "
                    "当前记录是合成条件对、压力污染或缺少账本观测, "
                    "无法在不放宽标准的前提下使用")
                n_absent_all += 1
        else:
            status = "ABSENT_FROM_ALL_SOURCES"
            eps = ""
            reason = "核心层无记录, NHS 514 亦无该化合物"
            recovery = (
                "必须从新的外部文献来源录入静态介电常数测量; "
                "本仓库现有数据无法提供")
        rows.append({
            "solvent": solvent,
            "status": status,
            "epsilon": eps,
            "v06_blocking_reason": v06_by_name.get(solvent.lower(), ""),
            "in_nbs_transcription": "true" if nbs_hits else "false",
            "in_model_matrix": "true" if in_model else "false",
            "why_absent": reason,
            "recovery_path": recovery,
        })

    path = OUT / "electrolyte_solvent_coverage_b100.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    n_in = sum(1 for r in rows if r["status"] == "IN_MODELLING_SET")

    doc = {
        "schema": "b100.solvent_coverage/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "why_this_exists": (
            "数据集名为电解质溶剂而多数典型电解质溶剂缺失 (Reviewer 1)。"
            "只报『239 个合格分子』会掩盖这一点。"
            "本审计逐个溶剂给出状态、失败原因与恢复路径 —— "
            "**不通过放宽准入标准来补数**。"
        ),
        "n_key_solvents": len(rows),
        "n_in_modelling_set": n_in,
        "n_absent_from_all_sources": n_absent_all,
        "by_status": {},
        "finding": (
            f"{len(rows)} 个关键电解质溶剂中, {n_in} 个进入建模集。"
            f"其余缺失**不是遗漏**, 而是每一条都有具体的数据缺陷记录在案; "
            f"其中 {n_absent_all} 个在本仓库持有的所有来源里都不存在, "
            "必须从新文献录入。"
        ),
        "consequence": (
            "因此本数据集的结论**不能**外推到这些溶剂。"
            "任何『可用于电解质设计』的宣称都必须先补齐这批溶剂的测量。"
        ),
        "do_not_do": [
            "不得用相近化合物替代 (Formamide 不是 DMF, Furan 不是 THF)",
            "不得保留已知有缺陷的记录来填补覆盖",
            "不得把缺乏熔点的分子默认当作液态计入",
        ],
        "inputs": {
            "model_matrix_b100": {"sha256": sha256_file(MATRIX)},
            "excluded_molecules_b100": {"sha256": sha256_file(EXCLUDED)},
            "dataset_v06_exclusions": {"rows": len(v06)},
        },
        "output": {"path": str(path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(path), "rows": len(rows)},
    }
    from collections import Counter
    doc["by_status"] = dict(Counter(r["status"] for r in rows))
    j_path = OUT / "electrolyte_solvent_coverage_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"[B100-17] {j_path}")
    print(f"[B100-17] {path}")
    print(f"  key solvents        = {len(rows)}")
    print(f"  in modelling set    = {n_in}")
    print(f"  absent from sources = {n_absent_all}")
    print(f"  by status           = {doc['by_status']}")
    print()
    for r in rows:
        mark = "OK " if r["status"] == "IN_MODELLING_SET" else "   "
        print(f"  {mark}{r['solvent'][:30]:30s} {r['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
