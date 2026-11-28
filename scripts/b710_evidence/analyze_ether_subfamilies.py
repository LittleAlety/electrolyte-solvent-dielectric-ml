#!/usr/bin/env python
"""B710-04: does splitting ether explain the negative within-family rho?

The v7.0 finding was ether rho = -0.135, the only true ranking failure in E4.
This script tests the heterogeneity hypothesis WITHOUT touching the official
family label:

  H1  each subtype has a coherent internal structure-property relation
  H2  the two subtypes sit at opposite ends, so pooling them cancels the ranking

It reports the same E4 diagnostics per stratum (LOFO MAE/RMSE/bias/demeaned MAE/
Spearman/worst-point sensitivity), plus two things E4 did not do:

  * pooled-vs-stratified rho, with a permutation p for "is the pooled rho
    distinguishable from zero at this n"
  * a leave-one-out influence check: how much does any single molecule move rho

Because both subtypes are small, every inferential number is labelled
EXPLORATORY. n<5 gets descriptive statistics only.
"""

from __future__ import annotations

import csv
import io
import itertools
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b710_evidence" / "ether_subfamilies"
GEN = "analyze_ether_subfamilies/1.0.0"
SEED = 20261125
N_PERM = 10000
MIN_N_FOR_INFERENCE = 5

TABLE = OUT / "ether_subtype_table.csv"


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


def perm_p_rho(x, y, n_perm=N_PERM, seed=SEED):
    """Two-sided permutation p for Spearman rho against the zero null."""
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


def stratum_stats(rows, label):
    if not rows:
        return {"stratum": label, "n": 0}
    eps = [fnum(r["epsilon"]) for r in rows]
    pred = [fnum(r["lofo_pred"]) for r in rows]
    pairs = [(e, p) for e, p in zip(eps, pred) if e is not None and p is not None]
    if not pairs:
        return {"stratum": label, "n": len(rows)}
    e = [p[0] for p in pairs]
    p = [p[1] for p in pairs]
    n = len(e)
    err = [p[i] - e[i] for i in range(n)]
    bias = statistics.mean(err)
    mae = statistics.mean(abs(v) for v in err)
    rmse = math.sqrt(statistics.mean(v * v for v in err))
    mae_dm = statistics.mean(abs(v - bias) for v in err)
    ybar = statistics.mean(e)
    const = statistics.mean(abs(v - ybar) for v in e)
    sd = statistics.pstdev(e) if n > 1 else 0.0
    abs_err = [abs(v) for v in err]
    worst = max(range(n), key=lambda i: abs_err[i])
    err_wo = [err[i] for i in range(n) if i != worst]
    mae_wo = statistics.mean(abs(v) for v in err_wo) if err_wo else None

    rho, rho_p = (perm_p_rho(e, p) if n >= MIN_N_FOR_INFERENCE else (spearman(e, p), None))

    # leave-one-out influence on rho
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
        "epsilon_sd": round(sd, 4),
        "epsilon_min": round(min(e), 3),
        "epsilon_max": round(max(e), 3),
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "bias": round(bias, 4),
        "mae_demeaned": round(mae_dm, 4),
        "constant_baseline_mae": round(const, 4),
        "beats_constant": bool(mae < const),
        "beats_constant_after_offset": bool(mae_dm < const),
        "spearman": round(rho, 4) if rho is not None else None,
        "spearman_perm_p": round(rho_p, 4) if rho_p is not None else None,
        "spearman_loo_min": round(min(loo), 4) if loo else None,
        "spearman_loo_max": round(max(loo), 4) if loo else None,
        "worst_molecule": rows[worst]["name"] if worst < len(rows) else None,
        "worst_residual": round(err[worst], 4),
        "mae_excluding_worst1": round(mae_wo, 4) if mae_wo is not None else None,
        "inference_allowed": n >= MIN_N_FOR_INFERENCE,
    }


def main() -> None:
    rows = load_csv(TABLE)
    if not rows:
        print(f"FATAL: missing {TABLE}")
        return

    strata = defaultdict(list)
    for r in rows:
        strata[r["family_subtype_v1"]].append(r)

    pooled = stratum_stats(rows, "ether_POOLED_original")

    # Does the pooled rho differ from the stratified ones?
    per = {k: stratum_stats(v, k) for k, v in strata.items()}

    # H2 test: subtype medians differ?
    med = {}
    for k, v in strata.items():
        e = [fnum(r["epsilon"]) for r in v]
        e = [x for x in e if x is not None]
        if e:
            med[k] = statistics.median(e)

    # Within-subtype direction consistency: sign of slope of pred vs eps
    direction = {}
    for k, v in strata.items():
        e = [fnum(r["epsilon"]) for r in v]
        p = [fnum(r["lofo_pred"]) for r in v]
        pairs = [(a, b) for a, b in zip(e, p) if a is not None and b is not None]
        if len(pairs) >= 3:
            rr = spearman([q[0] for q in pairs], [q[1] for q in pairs])
            direction[k] = ("POSITIVE" if rr and rr > 0 else
                            "NEGATIVE" if rr and rr < 0 else "FLAT")

    doc = {
        "schema": "b710.ether_subfamily_analysis/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "official_family_modified": False,
        "original_family": "ether (unchanged in all frozen tables)",
        "n_ether": len(rows),
        "pooled": pooled,
        "by_subtype": per,
        "subtype_median_epsilon": {k: round(v, 3) for k, v in med.items()},
        "within_subtype_rho_direction": direction,
        "hypothesis_tests": {
            "H1_internal_coherence": {
                "verdict": ("SUPPORTED" if all(
                    per[k]["spearman"] is not None and per[k]["spearman"] > 0
                    for k in per if per[k]["n"] >= 4) else "MIXED"),
                "detail": "each subtype's pred-vs-epsilon rho; positive = coherent within stratum",
            },
            "H2_opposite_ends": {
                "verdict": ("SUPPORTED" if len(med) >= 2
                            and (max(med.values()) - min(med.values())) > 3.0 else "WEAK"),
                "detail": f"subtype median epsilon spread = "
                          f"{round(max(med.values()) - min(med.values()), 3) if len(med) >= 2 else None}",
            },
        },
        "influence": {
            "pooled_rho_loo_range": [pooled["spearman_loo_min"], pooled["spearman_loo_max"]],
            "note": "a single molecule moving pooled rho outside [-0.2,0.2] means the "
                    "pooled correlation is not a stable statistic at this n",
        },
        "evidence_grade": ("EXPLORATORY" if min(per[k]["n"] for k in per) < MIN_N_FOR_INFERENCE
                           else "SUPPORTED"),
        "caveat": (
            "chlorinated_ether has n=2. No Spearman value is meaningful there; only the "
            "epsilon level (21-22.6 vs predicted ~3.7) is reportable. Splitting ether "
            "therefore EXPLAINS the pooling artifact but does not license a subtype-level "
            "generalisation claim."
        ),
    }
    (OUT / "ether_subfamily_analysis.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'ether_subfamily_analysis.json'}")
    print()
    print(f"{'stratum':24s} {'n':>3s} {'MAE':>7s} {'bias':>7s} {'const':>7s} {'rho':>7s} {'p':>7s} {'grades':>6s}")
    for k in ["ether_POOLED_original"] + list(per.keys()):
        s = pooled if k == "ether_POOLED_original" else per[k]
        rho_s = f"{s['spearman']:7.3f}" if s["spearman"] is not None else "   n/a "
        p_s = f"{s['spearman_perm_p']:7.4f}" if s["spearman_perm_p"] is not None else "   n/a "
        print(f"{k:24s} {s['n']:3d} {s['mae']:7.3f} {s['bias']:+7.3f} "
              f"{s['constant_baseline_mae']:7.3f} {rho_s} {p_s} "
              f"{'YES' if s['inference_allowed'] else 'no':>6s}")
    print()
    print("median eps by subtype:", {k: round(v, 2) for k, v in med.items()})
    print("within-subtype direction:", direction)
    print("H1:", doc["hypothesis_tests"]["H1_internal_coherence"]["verdict"],
          "| H2:", doc["hypothesis_tests"]["H2_opposite_ends"]["verdict"])


if __name__ == "__main__":
    main()
