#!/usr/bin/env python
"""B100-7: source-independence audit for the qualified set.

The readiness report says 257 molecules are phase-verified liquid. That clears the
hard threshold of 100, but a count is only as meaningful as the independence of the
observations behind it. Two questions must be answered before any "cross-source
generalisation" claim is made:

  1. HOW MANY INDEPENDENT SOURCES does the qualified set actually rest on?
     226 of the 257 come from the NBS Circular 514 compendium, which is ONE
     editorial source. Agreement within it is not independent corroboration.

  2. WHAT EVIDENCE GRADE does each molecule carry?
     Q1 = original measurement with per-measurement provenance (ThermoML path)
     Q2 = authoritative critical compilation (NBS 514), source-level conditions
     Q3 = incomplete conditions -- must not enter the confirmatory set

A dataset that is 88% Q2 from a single compendium can support a large-N *modelling*
study, but it cannot support the claim that results transfer across independent
measurement programmes. Stating that plainly is the point of this audit.

It also reports which qualified molecules appear in BOTH layers, because those are
the only ones whose epsilon is independently corroborated.

Output: outputs/b100/source_independence_b100.json
        outputs/b100/source_independence_b100.csv
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
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "audit_b100_source_independence/1.0.0"

PHASE = OUT / "phase_state_audit_b100.csv"
QUALIFIED = OUT / "qualified_molecules_b100.csv"
EXP_OBS = (REPO_ROOT / "data" / "processed"
           / "dielectric_pool_expansion_observations.csv")
V04 = REPO_ROOT / "data" / "dielectric_v04.csv"
LEDGER = (REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
          / "measurement_ledger_v1.csv")
CROSS_AGREE = OUT / "cross_source_agree_b100.csv"

MIN_INDEPENDENT_SOURCES_FOR_CLAIM = 3


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
    for p in (PHASE, QUALIFIED):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT.mkdir(parents=True, exist_ok=True)

    phase = load(PHASE)
    qualified = {(r.get("inchikey") or "").strip(): r for r in load(QUALIFIED)}
    exp = load(EXP_OBS)
    v04 = load(V04)
    ledger = load(LEDGER)
    agree = load(CROSS_AGREE)

    # ---- map each molecule to its originating documents ----
    exp_doc: dict[str, set[str]] = defaultdict(set)
    for r in exp:
        ik = (r.get("inchikey") or "").strip()
        sf = (r.get("source_file") or "").strip()
        if ik and sf:
            exp_doc[ik].add(sf)
    # NBS is one compendium; record that fact rather than pretending the four part
    # files are four independent sources.
    nbs_parts = sorted({f for s in exp_doc.values() for f in s})

    v04_doc: dict[str, set[str]] = defaultdict(set)
    for r in v04:
        ik = (r.get("inchikey") or "").strip()
        sr = (r.get("source_record_id") or "").strip()
        if ik and sr:
            v04_doc[ik].add(sr)

    ledger_doc: dict[str, set[str]] = defaultdict(set)
    for r in ledger:
        ik = (r.get("inchikey") or "").strip()
        sd = (r.get("source_document_id") or "").strip()
        if ik and sd:
            ledger_doc[ik].add(sd)

    # ---- per-molecule source independence ----
    # "Corroborated" must mean the two sources AGREE on epsilon, not merely that the
    # molecule appears in both. The previous version set the flag on presence alone
    # while the manifest described it as "且两者一致" -- a claim the code never tested.
    # (Reviewer 2 and 4 both caught this.)
    CROSS_TOL_K = 5.0
    CROSS_TOL_REL = 0.05

    def eps_of(r, key="dielectric"):
        v = (r.get(key) or "").strip()
        try:
            return float(v)
        except ValueError:
            return None

    def t_of(r, key="T_K"):
        v = (r.get(key) or "").strip()
        try:
            return float(v)
        except ValueError:
            return None

    nbs_eps: dict[str, list[tuple[float | None, float | None]]] = defaultdict(list)
    for r in exp:
        ik = (r.get("inchikey") or "").strip()
        if ik:
            nbs_eps[ik].append((eps_of(r, "epsilon"), t_of(r, "T_K")))
    core_eps: dict[str, list[tuple[float | None, float | None]]] = defaultdict(list)
    for r in ledger:
        ik = (r.get("inchikey") or "").strip()
        if ik:
            core_eps[ik].append((eps_of(r, "dielectric"), t_of(r, "temperature_K")))

    def agreement(ik: str) -> tuple[str, float | None]:
        """Return (status, relative_difference) for the best comparable pair."""
        best = None
        for a_eps, a_t in core_eps.get(ik, []):
            for b_eps, b_t in nbs_eps.get(ik, []):
                if a_eps is None or b_eps is None:
                    continue
                if a_t is None or b_t is None:
                    continue
                if abs(a_t - b_t) > CROSS_TOL_K:
                    continue
                rel = abs(a_eps - b_eps) / max(a_eps, b_eps)
                if best is None or rel < best:
                    best = rel
        if best is None:
            return "NO_COMPARABLE_PAIR", None
        return ("AGREE" if best <= CROSS_TOL_REL else "DISAGREE"), best

    rows: list[dict] = []
    for r in phase:
        if r.get("phase_verified") != "true":
            continue
        ik = (r.get("inchikey") or "").strip()
        q = qualified.get(ik, {})
        layer = r.get("layer", "")
        grade = r.get("evidence_grade", "")
        nbs_srcs = sorted(exp_doc.get(ik, set()))
        core_srcs = sorted(ledger_doc.get(ik, set()))
        in_both = bool(nbs_srcs) and bool(core_srcs)
        n_programmes = (1 if nbs_srcs else 0) + len(core_srcs)
        status, rel = agreement(ik) if in_both else ("SINGLE_SOURCE", None)
        rows.append({
            "inchikey": ik,
            "name": r.get("name", ""),
            "layer": layer,
            "evidence_grade": grade,
            "epsilon": r.get("epsilon", ""),
            "T_K": r.get("T_K", ""),
            "mp_C": r.get("mp_C", ""),
            "mp_source": r.get("mp_source", ""),
            "nbs_part_files": ";".join(nbs_srcs),
            "nbs_is_one_compendium": "true" if nbs_srcs else "false",
            "core_thermoml_documents": ";".join(core_srcs),
            "n_independent_programmes": n_programmes,
            # presence in both layers
            "in_both_layers": "true" if in_both else "false",
            # and whether the two actually agree on epsilon
            "cross_source_status": status,
            "cross_source_relative_difference": (
                round(rel, 4) if rel is not None else ""),
            "independently_corroborated": "true" if status == "AGREE" else "false",
            "has_xtb": q.get("has_xtb", "false"),
        })

    path = OUT / "source_independence_b100.csv"
    if rows:
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in sorted(rows, key=lambda z: (-int(z["n_independent_programmes"]),
                                                 z["name"])):
                w.writerow(r)

    by_grade = Counter(r["evidence_grade"] for r in rows)
    by_layer = Counter(r["layer"] for r in rows)
    n_corroborated = sum(1 for r in rows if r["independently_corroborated"] == "true")
    n_prog = Counter(r["n_independent_programmes"] for r in rows)
    n_with_xtb = sum(1 for r in rows if r["has_xtb"] == "true")

    # distinct core documents across the qualified set
    distinct_core_docs = {d for r in rows
                          for d in r["core_thermoml_documents"].split(";") if d}

    # A robustness claim needs >=3 independent programmes. Report the honest state.
    programmes = (len(distinct_core_docs)) + (1 if by_layer.get("nbs514_expansion")
                                              else 0)
    claim_permitted = programmes >= MIN_INDEPENDENT_SOURCES_FOR_CLAIM

    doc = {
        "schema": "b100.source_independence/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "question": (
            "257 个相态验证分子背后有多少个**独立测量来源**? "
            "数量门槛达标不等同于跨来源泛化的证据充分."
        ),
        "qualified_set": {
            "n_phase_verified": len(rows),
            "by_evidence_grade": dict(by_grade),
            "by_layer": dict(by_layer),
            "n_with_xtb": n_with_xtb,
        },
        "source_structure": {
            "nbs514_compendium": {
                "n_molecules": by_layer.get("nbs514_expansion", 0),
                "part_files": nbs_parts,
                "critical_point": (
                    "NBS Circular 514 是**单一编校来源** (Maryott & Smith, 1951). "
                    "四个 part 文件是同一汇编的分页, 不是四个独立来源. "
                    "因此这 "
                    f"{by_layer.get('nbs514_expansion', 0)} 个分子之间的一致性"
                    "**不构成独立复现**."
                ),
            },
            "core_thermoml": {
                "n_molecules": by_layer.get("core_thermoml", 0),
                "n_distinct_source_documents": len(distinct_core_docs),
                "critical_point": (
                    "核心层的每条测量有独立文档来源, 这才是 Q1 证据."
                ),
            },
            "independently_corroborated": {
                "n_molecules": n_corroborated,
                "definition": (
                    "同一分子在 NBS 汇编与 ThermoML 原始文献中都有 ε, "
                    f"温度相差 <= {CROSS_TOL_K} K, 且 ε 相对差 <= {CROSS_TOL_REL:.0%}. "
                    "**必须数值一致才算印证**, 仅『两层都出现』不算."
                ),
                "n_present_in_both_layers": sum(
                    1 for r in rows if r["in_both_layers"] == "true"),
                "n_disagree": sum(
                    1 for r in rows if r["cross_source_status"] == "DISAGREE"),
                "n_no_comparable_pair": sum(
                    1 for r in rows
                    if r["cross_source_status"] == "NO_COMPARABLE_PAIR"),
            },
        },
        "independence_distribution": {
            "n_independent_programmes_histogram": dict(sorted(n_prog.items())),
            "note": (
                "绝大多数分子只来自 1 个测量方案 (NBS 514). "
                "把它们当作互相独立的样本会高估统计功效."
            ),
        },
        "claim_permission": {
            "rule": (
                f"跨来源稳健性宣称需要 >= {MIN_INDEPENDENT_SOURCES_FOR_CLAIM} "
                "个独立测量方案"
            ),
            "n_independent_programmes_present": programmes,
            "claim_permitted": claim_permitted,
            "what_IS_supported": [
                "大样本单分子描述符建模 (257 个分子, 远超 100 门槛)",
                "化学空间内的插值预测能力评估",
                "分层家族留出验证 (LOFO)",
                "与核心层 31 个 Q1 分子的对照",
            ],
            "what_is_NOT_supported": [
                "「结果可跨独立测量方案复现」—— 88% 的分子同源于一份汇编",
                "「基于多来源的稳健性」—— 独立方案数不足",
                "把 NBS 内部一致性当作外部验证",
            ],
        },
        "consequence_for_plan": (
            "B100 的 100+ 分子门槛**可以满足**, 但满足它的是 Q2 为主的数据集. "
            "因此论文中必须区分两类结论: "
            "(a) 内部建模与描述符边界结论, 可用 257 个分子; "
            "(b) 跨来源泛化结论, 只能用 "
            f"{n_corroborated} 个被独立印证的分子 + 核心层 {by_layer.get('core_thermoml', 0)} 个 Q1 分子, "
            "且需明确标注样本量限制."
        ),
        "inputs": {
            "phase_state_audit_b100": {"sha256": sha256_file(PHASE)},
            "qualified_molecules_b100": {"sha256": sha256_file(QUALIFIED)},
            "expansion_observations": {"rows": len(exp)},
            "dielectric_v04": {"rows": len(v04)},
            "measurement_ledger_v1": {"rows": len(ledger)},
        },
        "output": {"path": str(path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(path), "rows": len(rows)},
    }
    j_path = OUT / "source_independence_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"[B100-7] {j_path}")
    print(f"[B100-7] {path}")
    print(f"  phase-verified          = {len(rows)}")
    print(f"  by grade                = {dict(by_grade)}")
    print(f"  by layer                = {dict(by_layer)}")
    print(f"  independently corroborated = {n_corroborated}")
    print(f"  independent programmes  = {programmes}")
    print(f"  CLAIM PERMITTED         = {claim_permitted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
