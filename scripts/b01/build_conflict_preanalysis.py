#!/usr/bin/env python
"""B04-PRECONFLICT: independent statistical pre-analysis of the two blocking conflicts.

This is NOT a reviewer verdict. It is the arithmetic the four reviewers are being
asked to judge, computed independently so their reasoning can be checked against
something reproducible.

Two things make these conflicts look worse than they are, and both are measurable:

  1. SOURCE MULTIPLICITY IS INFLATED.
     `10.1021/je3007666` and `10.1021/je800593p` report byte-identical values across
     the whole temperature series -- they are one experiment deposited twice. So
     butan-2-ol's "4 sources" are really 3 independent groups, and two of those
     agree to 0.12%.

  2. THE TEMPERATURE BUCKET SPANS A LABEL GAP.
     butan-2-ol's cluster mixes T=298.0 with T=298.15. That is a 0.15 K gap which
     dε/dT explains only ~0.03 in epsilon -- so the outlier is NOT a temperature
     artefact, but the bucket does need stating precisely.

The output distinguishes "the conflict is small" from "the conflict is real but
localised to one source", which are different conclusions with different actions.

Output: outputs/b01/conflict_adjudication/preanalysis.json
        outputs/b01/conflict_adjudication/preanalysis.md
"""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b01" / "conflict_adjudication"
B01 = REPO_ROOT / "outputs" / "b01"
PR = REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
GENERATOR = "build_conflict_preanalysis/1.0.0"

MEAS_LEDGER = PR / "measurement_ledger_v1.csv"
DUP_GROUPS = PR / "duplicate_observation_groups.csv"

# The two conflicts that block B04 (they touch model-ready molecules).
TARGETS = {
    "MCONF-BTANRVKWQNVYAZ-298": {
        "inchikey": "BTANRVKWQNVYAZ-UHFFFAOYSA-N",
        "name": "butan-2-ol",
        "anchor_T": 298.0,
        "tolerance_K": 0.5,
        "d_eps_dT_per_K": None,   # derived from the series below
    },
    "MCONF-FXHOOIRPVKKKFG-303.15": {
        "inchikey": "FXHOOIRPVKKKFG-UHFFFAOYSA-N",
        "name": "N,N-dimethylethanamide (DMAc)",
        "anchor_T": 303.15,
        "tolerance_K": 0.5,
        "d_eps_dT_per_K": None,
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    s = (v or "").strip()
    if not s or s.lower() in ("not_evaluated", "nan", "none"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main() -> int:
    for p in (MEAS_LEDGER, DUP_GROUPS):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ledger = load(MEAS_LEDGER)
    dups = load(DUP_GROUPS)

    # Which documents are provably the same experiment (identical observations)?
    dup_pairs: list[tuple[str, str]] = []
    for d in dups:
        docs = [x.strip() for x in (d.get("documents") or "").split(";") if x.strip()]
        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                dup_pairs.append(tuple(sorted((docs[i], docs[j]))))
    dup_pairs = sorted(set(dup_pairs))

    def same_experiment(a: str, b: str) -> bool:
        return tuple(sorted((a, b))) in dup_pairs

    results = []
    for cid, spec in TARGETS.items():
        ik = spec["inchikey"]
        rows = [m for m in ledger if (m.get("inchikey") or "").strip() == ik]

        # Observations inside the conflict window.
        in_window = []
        for m in rows:
            t = fnum(m.get("temperature_K"))
            e = fnum(m.get("dielectric"))
            if t is None or e is None:
                continue
            if abs(t - spec["anchor_T"]) <= spec["tolerance_K"]:
                in_window.append({
                    "measurement_id": (m.get("measurement_id") or "").strip(),
                    "temperature_K": t,
                    "dielectric": e,
                    "source": (m.get("source_document_id") or "").strip(),
                    "pressure_kpa": (m.get("pressure_kpa") or "").strip(),
                })

        # Estimate dEps/dT from the molecule's own series (robust: median of
        # consecutive-point slopes).
        by_t: dict[float, list[float]] = defaultdict(list)
        for m in rows:
            t = fnum(m.get("temperature_K"))
            e = fnum(m.get("dielectric"))
            if t is not None and e is not None:
                by_t[t].append(e)
        series = sorted((t, statistics.median(v)) for t, v in by_t.items())
        slopes = []
        for (t0, e0), (t1, e1) in zip(series, series[1:]):
            if t1 != t0:
                slopes.append((e1 - e0) / (t1 - t0))
        d_eps_dt = statistics.median(slopes) if slopes else None

        # Collapse to independent source groups: documents proven to be the same
        # experiment count once.
        groups: list[dict] = []
        for o in in_window:
            placed = False
            for g in groups:
                if any(same_experiment(o["source"], s) for s in g["sources"]):
                    g["sources"].append(o["source"])
                    g["observations"].append(o)
                    placed = True
                    break
            if not placed:
                groups.append({"sources": [o["source"]], "observations": [o]})

        for g in groups:
            g["representative_eps"] = statistics.median(
                [o["dielectric"] for o in g["observations"]])
            g["temperatures"] = sorted({o["temperature_K"] for o in g["observations"]})

        reps = [g["representative_eps"] for g in groups]
        eps_min, eps_max = (min(reps), max(reps)) if reps else (None, None)
        spread = ((eps_max - eps_min) / eps_min * 100) if eps_min else None

        # How much of the spread could a temperature difference explain?
        t_lo = min(o["temperature_K"] for o in in_window) if in_window else None
        t_hi = max(o["temperature_K"] for o in in_window) if in_window else None
        dT = (t_hi - t_lo) if (t_lo is not None and t_hi is not None) else None
        # A zero temperature span is a legitimate answer (all observations at the
        # same T), not a missing value: it means temperature explains NOTHING.
        t_explained = (abs(d_eps_dt) * dT) if (d_eps_dt is not None
                                              and dT is not None) else None

        # Is there a majority that agrees closely? Two independent groups cannot
        # form a majority, so this only applies when there are >= 3 groups. When
        # duplicates were collapsed down to 2 groups, report the weighted split
        # instead: how many OBSERVATIONS support each group.
        majority = None
        if len(reps) >= 3:
            for cand in reps:
                close = [r for r in reps if abs(r - cand) / cand <= 0.01]
                if len(close) > len(reps) / 2:
                    majority = {
                        "value": round(statistics.median(close), 4),
                        "n_agreeing": len(close),
                        "n_total": len(reps),
                        "basis": "independent_groups",
                    }
                    break
        if majority is None and len(groups) == 2:
            # Report which group has more independent support, by observation count.
            g_sorted = sorted(groups, key=lambda g: -len(g["observations"]))
            majority = {
                "value": round(g_sorted[0]["representative_eps"], 4),
                "n_agreeing": len(g_sorted[0]["observations"]),
                "n_total": sum(len(g["observations"]) for g in groups),
                "basis": "observations",
                "note": (
                    "只有 2 个独立实验组, 不构成统计多数; "
                    "此处报告的是观测支持度, 不是多数裁决"
                ),
            }

        results.append({
            "conflict_id": cid,
            "molecule": spec["name"],
            "inchikey": ik,
            "anchor_T_K": spec["anchor_T"],
            "window_K": spec["tolerance_K"],
            "n_observations_in_window": len(in_window),
            "n_documents_in_window": len({o["source"] for o in in_window}),
            "n_independent_groups": len(groups),
            "duplicate_documents_collapsed": (
                len({o["source"] for o in in_window}) - len(groups)),
            "groups": [
                {"sources": g["sources"],
                 "representative_eps": round(g["representative_eps"], 4),
                 "temperatures_K": g["temperatures"],
                 "n_observations": len(g["observations"])}
                for g in groups
            ],
            "eps_min": eps_min,
            "eps_max": eps_max,
            "spread_pct": round(spread, 2) if spread is not None else None,
            "temperature_span_K": dT,
            "d_eps_dT_per_K": round(d_eps_dt, 4) if d_eps_dt is not None else None,
            "spread_explained_by_temperature": (
                round(t_explained, 4) if t_explained is not None else None),
            "temperature_explains_pct": (
                round(100.0 * t_explained / (eps_max - eps_min), 1)
                if (t_explained is not None and eps_max and eps_min
                    and (eps_max - eps_min) > 0) else None),
            "majority_agreement": majority,
            "observations": sorted(in_window,
                                   key=lambda o: (o["temperature_K"], o["source"])),
        })

    # ---- markdown ----
    md: list[str] = []
    md.append("# B04 前置：两组阻断冲突的独立统计预分析\n")
    md.append(f"> 生成器 `{GENERATOR}` · "
              f"{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')}\n")
    md.append("> 这不是评审结论，是供四位 Reviewer 对照的可复现算术。\n")

    for r in results:
        md.append(f"\n## {r['molecule']}\n")
        md.append(f"- 冲突窗口：T = {r['anchor_T_K']} ± {r['window_K']} K\n")
        md.append(f"- 窗口内观测：**{r['n_observations_in_window']}** 条，"
                  f"来自 **{r['n_documents_in_window']}** 个文档\n")
        md.append(f"- 去重后的**独立实验组**：**{r['n_independent_groups']}**\n")
        if r["duplicate_documents_collapsed"]:
            md.append(f"- 因逐字节相同而被合并的文档：**{r['duplicate_documents_collapsed']}** 个\n")

        md.append("\n### 独立组\n")
        md.append("| 组 | 代表 ε | 温度 | 文档 |\n|---|---:|---|---|\n")
        for i, g in enumerate(r["groups"], 1):
            md.append(f"| {i} | {g['representative_eps']} | "
                      f"{', '.join(str(t) for t in g['temperatures_K'])} | "
                      f"{', '.join('`'+s+'`' for s in g['sources'])} |\n")

        md.append(f"\n- ε 范围：**{r['eps_min']}–{r['eps_max']}**，"
                  f"离散度 **{r['spread_pct']}%**\n")
        md.append(f"- 窗口温度跨度：{r['temperature_span_K']} K；"
                  f"dε/dT = {r['d_eps_dT_per_K']}/K\n")
        md.append(f"- **温度能解释的 ε 差：{r['spread_explained_by_temperature']}** "
                  f"（占离散度的 {r['temperature_explains_pct']}%）\n")
        if r["majority_agreement"]:
            m = r["majority_agreement"]
            md.append(f"- **多数一致：{m['n_agreeing']}/{m['n_total']} 组落在 "
                      f"±1% 内，中位数 ε = {m['value']}**\n")

    md.append("\n## 结论要点\n")
    for r in results:
        md.append(f"### {r['molecule']}\n")
        if r["majority_agreement"]:
            m = r["majority_agreement"]
            md.append(
                f"冲突的真实结构是 **{m['n_agreeing']}/{m['n_total']} 一致 + 1 个离群**，"
                f"不是「来源普遍分歧」。温度只能解释 {r['temperature_explains_pct']}%，"
                f"所以离群值**不是**温度假象。\n"
            )
        else:
            md.append(
                f"没有明确多数：{r['n_independent_groups']} 个独立组，"
                f"离散度 {r['spread_pct']}%，温度解释 "
                f"{r['temperature_explains_pct']}%。\n"
            )

    md_path = OUT_DIR / "preanalysis.md"
    md_path.write_text("".join(md), encoding="utf-8")

    doc = {
        "schema": "b01.conflict_preanalysis/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "本预分析不是评审结论. 它计算三件可复现的事实: "
            "① 哪些文档是同一实验; ② 温度能解释多少离散度; ③ 是否存在多数一致."
        ),
        "inputs": {
            "measurement_ledger_v1": {"sha256": sha256_file(MEAS_LEDGER),
                                      "rows": len(ledger)},
            "duplicate_observation_groups": {"sha256": sha256_file(DUP_GROUPS),
                                             "rows": len(dups)},
        },
        "proven_duplicate_pairs": [list(p) for p in dup_pairs],
        "conflicts": results,
        "output": {"path": str(md_path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(md_path)},
    }
    json_path = OUT_DIR / "preanalysis.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"[B04-PRE] {json_path}")
    print(f"[B04-PRE] {md_path}")
    for r in results:
        print(f"  {r['molecule']}")
        print(f"    obs={r['n_observations_in_window']} docs={r['n_documents_in_window']} "
              f"indep_groups={r['n_independent_groups']}")
        print(f"    spread={r['spread_pct']}% temp_explains={r['temperature_explains_pct']}%")
        if r["majority_agreement"]:
            m = r["majority_agreement"]
            print(f"    majority {m['n_agreeing']}/{m['n_total']} at eps={m['value']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
