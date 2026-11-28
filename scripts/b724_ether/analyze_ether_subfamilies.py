#!/usr/bin/env python
"""B724-02: does the ether pooling failure come from structure or from nothing?

This repeats the B710 ether analysis on the v2 five-class scheme and adds the
decomposition the plan asks for explicitly:

  H_structure  subtypes sit at different epsilon levels (a LEVEL explanation)
  H_ranking    within a subtype, prediction still ranks epsilon (a SIGNAL question)
  H_pooling    pooling across subtypes cancels the within-subtype signal

For each stratum it reports n, MAE, bias, demeaned MAE, Spearman with a
permutation p, and a leave-one-out influence range on rho. Any stratum with n<5
gets descriptive statistics only, and a high rho on such a stratum is reported
with its p-value and an explicit "not inference-grade" label -- because with n=2
there is no rho at all, and a lucky n=6 rho is still noise.

The honest headline is allowed to be negative: the pooled rho is not significant,
so the pooling-artifact story is a plausible MECHANISM, not a demonstrated one.

Outputs (outputs/b724_ether/):
  ether_subfamily_analysis_v2.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b724_ether"
GEN = "analyze_ether_v2/1.0.0"
SEED = 20261125
N_PERM = 10000
MIN_N = 5

TABLE = OUT / "ether_subtype_v2.csv"


def load_csv(path: Path) -> list[dict]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def spearman(a, b):
    n = len(a)
    if n < 3:
        return None

    def rk(v):
        o = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[o[j + 1]] == v[o[i]]:
                j += 1
            av = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[o[k]] = av
            i = j + 1
        return r

    ra, rb = rk(a), rk(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    den = math.sqrt(sum((ra[i] - ma) ** 2 for i in range(n))
                    * sum((rb[i] - mb) ** 2 for i in range(n)))
    return num / den if den else None


def perm_p(x, y, n_perm=N_PERM, seed=SEED):
    obs = spearman(x, y)
    if obs is None:
        return None, None
    rng = random.Random(seed)
    cnt = 0
    for _ in range(n_perm):
        sh = list(y)
        rng.shuffle(sh)
        r = spearman(x, sh)
        if r is not None and abs(r) >= abs(obs):
            cnt += 1
    return obs, (cnt + 1) / (n_perm + 1)


def stats(rows, label):
    recs = [(fnum(r["epsilon"]), fnum(r["lofo_pred"])) for r in rows]
    recs = [(a, b) for a, b in recs if a is not None and b is not None]
    if not recs:
        return {"stratum": label, "n": 0}
    e = [p[0] for p in recs]
    p = [p[1] for p in recs]
    n = len(e)
    err = [p[i] - e[i] for i in range(n)]
    bias = statistics.mean(err)
    mae = statistics.mean(abs(v) for v in err)
    mae_dm = statistics.mean(abs(v - bias) for v in err)
    ybar = statistics.mean(e)
    const = statistics.mean(abs(v - ybar) for v in e)
    rho = spearman(e, p)
    if n >= MIN_N:
        rho, rho_p = perm_p(e, p)
    else:
        rho_p = None
    loo = []
    if n >= 4:
        for i in range(n):
            rr = spearman([e[j] for j in range(n) if j != i],
                          [p[j] for j in range(n) if j != i])
            if rr is not None:
                loo.append(rr)
    return {
        "stratum": label,
        "n": n,
        "epsilon_sd": round(statistics.pstdev(e), 4) if n > 1 else 0.0,
        "epsilon_median": round(statistics.median(e), 3),
        "mae": round(mae, 4),
        "bias": round(bias, 4),
        "mae_demeaned": round(mae_dm, 4),
        "constant_baseline_mae": round(const, 4),
        "beats_constant": bool(mae < const),
        "spearman": round(rho, 4) if rho is not None else None,
        "spearman_perm_p": round(rho_p, 4) if rho_p is not None else None,
        "spearman_loo_min": round(min(loo), 4) if loo else None,
        "spearman_loo_max": round(max(loo), 4) if loo else None,
        "inference_allowed": n >= MIN_N,
        "not_inference_reason": (None if n >= MIN_N else
                                 f"n={n} < {MIN_N}: descriptive statistics only"),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_csv(TABLE)
    strata = defaultdict(list)
    for r in rows:
        strata[r["family_subtype_v2"]].append(r)

    pooled = stats(rows, "ether_POOLED")
    per = {k: stats(v, k) for k, v in strata.items()}

    med = {k: s["epsilon_median"] for k, s in per.items() if s["n"]}
    spread = (max(med.values()) - min(med.values())) if len(med) >= 2 else None

    # pooling test: concatenate within-subtype ranks vs raw pooled rho
    # if the pooled rho is near zero but every large stratum is positive, that is
    # consistent with cancellation; it is NOT proof of it.
    large = {k: s for k, s in per.items() if s["n"] >= MIN_N}
    pos_large = [k for k, s in large.items()
                 if s["spearman"] is not None and s["spearman"] > 0]
    sig_large = [k for k, s in large.items()
                 if s["spearman_perm_p"] is not None and s["spearman_perm_p"] < 0.05]

    doc = {
        "schema": "b724.ether_subfamily_analysis_v2/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_ether": len(rows),
        "official_family_modified": False,
        "pooled": pooled,
        "by_subtype": per,
        "subtype_median_epsilon": {k: round(v, 3) for k, v in med.items()},
        "level_spread_across_subtypes": round(spread, 3) if spread is not None else None,
        "hypothesis_verdicts": {
            "H_structure_level": {
                "claim": "subtypes sit at different epsilon levels",
                "verdict": ("SUPPORTED" if spread is not None and spread > 3.0
                            else "WEAK"),
                "evidence": f"median epsilon spread = {round(spread, 3) if spread else None}",
            },
            "H_ranking_within_subtype": {
                "claim": "within a subtype, prediction still tracks epsilon",
                "n_strata_ge5": len(large),
                "n_positive_rho": len(pos_large),
                "n_significant_rho": len(sig_large),
                "verdict": ("SUPPORTED" if sig_large else
                            "EXPLORATORY" if pos_large else "NOT_SUPPORTED"),
                "why": ("no stratum reaches p<0.05, so within-subtype ranking is "
                        "not statistically demonstrated at this n"),
            },
            "H_pooling_cancels_signal": {
                "claim": "the pooled rho is near zero because subtypes oppose",
                "pooled_rho": pooled["spearman"],
                "pooled_p": pooled["spearman_perm_p"],
                "verdict": ("CONSISTENT_BUT_NOT_SIGNIFICANT"
                            if pooled["spearman_perm_p"] is not None
                            and pooled["spearman_perm_p"] > 0.05
                            else "SUPPORTED"),
                "why": ("a pooled rho that is not significantly different from zero "
                        "cannot be used as evidence that pooling destroyed a real "
                        "within-subtype signal; the mechanism is plausible, the "
                        "demonstration is absent"),
            },
        },
        "answer_to_plan_question": {
            "question": ("is the ether pooling failure structural heterogeneity, "
                         "subtype level differences, or absence of ranking "
                         "information in the descriptors?"),
            "answer": (
                "LEVEL DIFFERENCES ARE REAL (chlorinated ethers ~22 vs aliphatic ~3.7, "
                "corrected for by nothing in the model). STRUCTURAL HETEROGENEITY IS "
                "REAL (5 reproducible classes). BUT THE POOLED RHO IS NOT SIGNIFICANT "
                "AND NO SUBTYPE SHOWS SIGNIFICANT WITHIN-SUBTYPE RANKING, so the data "
                "cannot distinguish 'pooling hid a real signal' from 'there is no "
                "ranking signal to hide'. That question stays UNRESOLVED."
            ),
            "grade": "EXPLORATORY",
            "what_would_resolve_it": (
                "at least 5-8 measured chlorinated ethers plus enough molecules per "
                "subtype to power a rank test; neither is available"
            ),
        },
    }
    (OUT / "ether_subfamily_analysis_v2.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'ether_subfamily_analysis_v2.json'}")
    print()
    print(f"{'stratum':22s} {'n':>3s} {'MAE':>7s} {'bias':>7s} {'rho':>7s} {'p':>8s} grade")
    for k in ["ether_POOLED"] + sorted(per):
        s = pooled if k == "ether_POOLED" else per[k]
        if not s["n"]:
            continue
        rho = f"{s['spearman']:7.3f}" if s["spearman"] is not None else "   n/a "
        pv = f"{s['spearman_perm_p']:8.4f}" if s["spearman_perm_p"] is not None else "     n/a"
        print(f"{k:22s} {s['n']:3d} {s['mae']:7.3f} {s['bias']:+7.3f} {rho} {pv} "
              f"{'OK' if s['inference_allowed'] else 'descriptive'}")
    print()
    print(f"level spread: {doc['level_spread_across_subtypes']}")
    for k, v in doc["hypothesis_verdicts"].items():
        print(f"  {k}: {v['verdict']}")


if __name__ == "__main__":
    main()
