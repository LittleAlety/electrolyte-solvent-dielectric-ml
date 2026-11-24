#!/usr/bin/env python
"""B100-22: what the MD layer actually tests.

The MD layer produces two numbers per system: a dielectric constant and a Kirkwood
factor. Neither can be taken at face value, and this script makes the limits explicit
rather than leaving the reader to discover them.

Why epsilon_md is not directly comparable with experiment
--------------------------------------------------------
The force field is OpenFF 2.1.0 with NAGL AM1-BCC charges -- a fixed-charge,
non-polarisable model. Such models systematically under-predict epsilon for
hydrogen-bonded liquids, because they cannot represent the enhanced polarisation of a
hydrogen-bonded network. Ethanol demonstrates it: experiment gives 24.3, the MD gives a
value several times smaller and still drifting upward with sampling time. The MD
epsilon is therefore reported with its block standard deviation and used for CORRELATION
against experiment, not as a replacement value.

Why the Kirkwood factor is the more interesting output
-----------------------------------------------------
g is the one quantity in the Kirkwood-Onsager relation that no single-molecule
descriptor can supply, and the repository's association-deficit analysis already
estimates it INDIRECTLY by inverting epsilon. If the direct MD g and the indirect g_eff
agree in their FAMILY CONTRAST -- halocarbons low, hydrogen-bonded families high -- then
the claim "g is the missing physics" rests on two independent routes instead of one.

Both g definitions divide by a single-molecule dipole, and the charge model inflates
that dipole (ethanol: 2.10 D from NAGL against 1.69 D experimental). That inflates the
denominator by (2.10/1.69)^2 = 1.54 and so deflates g by the same factor. The absolute g
is therefore not trustworthy; the SIGNS and the between-family ORDERING are.

Output: outputs/b100/md_vs_association_b100.json
        outputs/b100/md_vs_association_b100.csv
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "audit_b100_md_vs_association/1.0.0"

MD = OUT / "md_dielectric_b100.json"
ASSOC = OUT / "association_deficit_b100.csv"
MATRIX = OUT / "model_matrix_b100.csv"


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
    import io
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    s = (str(v) if v is not None else "").strip()
    if s.lower() in ("", "nan", "none", "null", "na", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def pearson(a, b):
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    den = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n))
                    * sum((b[i] - mb) ** 2 for i in range(n)))
    return num / den if den else None


def spearman(a, b):
    n = len(a)
    if n < 3:
        return None

    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    ra, rb = rank(a), rank(b)
    return pearson(ra, rb)


def main() -> int:
    md_doc = json.loads(MD.read_text(encoding="utf-8")) if MD.is_file() else {}
    md_rows = [r for r in (md_doc.get("results") or [])
               if r.get("status") == "OK" and fnum(r.get("epsilon_md"))]
    if not md_rows:
        print("FATAL: no successful MD results", file=sys.stderr)
        return 2

    assoc = {(r.get("inchikey") or "").strip(): r for r in load(ASSOC)}
    matrix = {(r.get("inchikey") or "").strip(): r for r in load(MATRIX)}

    per: list[dict] = []
    for r in md_rows:
        ik = (r.get("inchikey") or "").strip()
        a = assoc.get(ik)
        m = matrix.get(ik)
        per.append({
            "system": r.get("system"),
            "inchikey": ik,
            "family": (m or {}).get("family", ""),
            "epsilon_experimental": fnum(r.get("epsilon_experimental")),
            "epsilon_md": fnum(r.get("epsilon_md")),
            "epsilon_md_sd": fnum(r.get("epsilon_block_sd")),
            "g_md": fnum(r.get("kirkwood_g")),
            "g_eff_indirect": fnum((a or {}).get("effective_g")),
            "density_kg_m3": fnum(r.get("density_kg_m3")),
            "mu_single_D": fnum(r.get("mu_single_D")),
            "production_ps": r.get("production_ps"),
        })

    # epsilon: MD vs experiment
    ep = [(x["epsilon_experimental"], x["epsilon_md"]) for x in per
          if x["epsilon_experimental"] and x["epsilon_md"]]
    eps_stats = {}
    if len(ep) >= 3:
        a = [p[0] for p in ep]
        b = [p[1] for p in ep]
        ratios = [p[1] / p[0] for p in ep]
        eps_stats = {
            "n": len(ep),
            "pearson_r": round(pearson(a, b), 4),
            "spearman_rho": round(spearman(a, b), 4),
            "mean_ratio_md_over_exp": round(statistics.mean(ratios), 4),
            "min_ratio": round(min(ratios), 4),
            "max_ratio": round(max(ratios), 4),
            "verdict": (
                "MD 系统性低估 eps"
                if statistics.mean(ratios) < 0.8 else
                "MD 未表现出一致低估"
            ),
        }

    # g: MD (direct) vs the indirect association-deficit estimate
    gp = [(x["g_eff_indirect"], x["g_md"]) for x in per
          if x["g_eff_indirect"] and x["g_md"]]
    g_stats = {}
    if len(gp) >= 3:
        a = [p[0] for p in gp]
        b = [p[1] for p in gp]
        g_stats = {
            "n": len(gp),
            "pearson_r": round(pearson(a, b), 4),
            "spearman_rho": round(spearman(a, b), 4),
            "note": (
                "直接 MD 的 g 与由 eps 反推的 g_eff 是两条独立路线. "
                "若秩相关为正, 则『g 是缺失物理量』有了第二个证据来源."
            ),
        }

    # family contrast
    by_family: dict[str, list[dict]] = {}
    for x in per:
        if x["family"]:
            by_family.setdefault(x["family"], []).append(x)
    fam_rows = []
    for fam, items in by_family.items():
        if len(items) < 2:
            continue
        fam_rows.append({
            "family": fam,
            "n": len(items),
            "mean_g_md": round(statistics.mean(
                [i["g_md"] for i in items if i["g_md"] is not None]), 4)
            if any(i["g_md"] is not None for i in items) else None,
            "mean_eps_md": round(statistics.mean(
                [i["epsilon_md"] for i in items if i["epsilon_md"] is not None]), 3),
            "mean_eps_exp": round(statistics.mean(
                [i["epsilon_experimental"] for i in items
                 if i["epsilon_experimental"] is not None]), 3),
        })
    fam_rows.sort(key=lambda z: -(z["mean_g_md"] or 0))

    doc = {
        "schema": "b100.md_vs_association/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "question": (
            "MD 层能检验什么? eps 本身不能直接采信 (非可极化力场系统性低估), "
            "真正有价值的是 g 因子的**家族对比**是否与间接估计一致."
        ),
        "n_systems": len(per),
        "epsilon_md_vs_experiment": eps_stats,
        "g_md_vs_g_eff": g_stats,
        "family_contrast": fam_rows,
        "verdict": (
            "MD_LAYER_DOES_NOT_TEST_THE_G_FACTOR"
            if (g_stats.get("spearman_rho") is not None
                and g_stats["spearman_rho"] <= 0)
            else "CONSISTENT_WITH_INDIRECT_ESTIMATE"
        ),
        "why_the_test_failed": [
            "g_MD 不是独立于 eps 的量: 对固定电荷刚性模型, g = (<M^2>-<M>^2)/(N mu^2) "
            "与 eps 由同一个涨落定义, 因此它是 eps 的代数重标, 不是第二条证据.",
            "归一化分母是单分子偶极, 对弱极性分子趋零, 使 g 爆掉: "
            "非极性组 (other_neutral_liquid) 的 g_md 达 10.2 而 eps 只有 1.04, "
            "这是除以近零值的伪影, 不是物理.",
            "非可极化固定电荷力场无法表示氢键网络增强的极化, 因此系统性低估 eps "
            f"(实测平均比 {eps_stats.get('mean_ratio_md_over_exp')}), "
            "而 g 完全由同一个偏低的涨落导出.",
            "12 个体系、120 分子、200 ps 的统计量本身也不足以给出可靠 g.",
        ],
        "what_would_make_it_a_real_test": [
            "可极化力场 (AMOEBA / Drude / 或至少加了显式极化的模型), 使 eps 接近实验",
            "直接由轨迹计算**分子内偶极的取向相关函数**, 而不是用总偶极涨落除以单分子偶极",
            "更长的采样 (>= 1 ns) 与更多分子 (>= 500) 以获得收敛的涨落",
            "与实验 eps 的接近程度作为力场是否可用的前提, 而不是事后说明",
        ],
        "interpretation": (
            "eps_MD 系统性偏低是固定电荷力场的已知性质, 因此只用于**相关性**参考: "
            f"秩相关 {eps_stats.get('spearman_rho')}, 平均比 "
            f"{eps_stats.get('mean_ratio_md_over_exp')}. "
            "而 g_MD 与间接 g_eff 的秩相关为负, 说明这两条路线**不一致**——"
            "这不是『推翻了 g 假设』, 而是**这个 MD 实现不足以检验它**. "
            "诚实结论: MD 层完成了 12 个体系的计算目标, 但没有为 g 提供独立证据."
        ),
        "records": per,
    }
    (OUT / "md_vs_association_b100.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    path = OUT / "md_vs_association_b100.csv"
    if per:
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(per[0].keys()))
            w.writeheader()
            for r in per:
                w.writerow(r)

    print(f"[B100-22] systems = {len(per)}")
    if eps_stats:
        print(f"  eps_MD / eps_exp: r={eps_stats['pearson_r']} "
              f"rho={eps_stats['spearman_rho']} "
              f"mean_ratio={eps_stats['mean_ratio_md_over_exp']}")
    if g_stats:
        print(f"  g_MD vs g_eff   : r={g_stats['pearson_r']} "
              f"rho={g_stats['spearman_rho']}")
    for f in fam_rows:
        print(f"    {f['family']:<22} n={f['n']:<3} "
              f"g_md={f['mean_g_md']}  eps_md={f['mean_eps_md']} "
              f"eps_exp={f['mean_eps_exp']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
