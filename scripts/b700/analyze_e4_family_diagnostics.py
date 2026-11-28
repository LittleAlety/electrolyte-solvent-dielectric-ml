#!/usr/bin/env python
"""B706-E4b: decompose the leave-one-family-out failure.

The v7.0 LOFO result is that 7 of 11 families are worse than their own constant
baseline. That single number hides three very different failure modes:

  (a) LEVEL error   - the model is off by a family-wide offset (fixable with one
                      calibration number per new family);
  (b) SPREAD error  - the model gets the level right but scrambles the ordering
                      inside the family (not fixable by calibration);
  (c) NOISE         - the family is internally homogeneous, so its constant
                      baseline is already near-optimal and no transfer can beat it.

This script separates them per family and reports, for each:

  mae              leave-one-family-out MAE
  bias             mean signed error (level error)
  mae_demeaned     MAE after removing the family-mean error (= spread error)
  spearman         within-family rank correlation
  r2_within        within-family R^2
  baseline_mae     family constant baseline MAE
  eps_sd           family internal standard deviation of epsilon

Then it tests a cheap calibration: give the model ONE number per held-out family
(the mean residual, which in practice would come from a handful of measured
solvents in that family) and re-score. If mae_demeaned << mae, the information
transfers and only the level is wrong.

Output: outputs/b700/B706_E4_family_diagnostics.json + .csv
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
OUT = REPO_ROOT / "outputs" / "b700"
GEN = "analyze_e4_family_diagnostics/1.0.0"
SEED = 20261124
LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]
X1_V7_COLS = ["dipole_D_v7", "homo_lumo_gap_ev_v7"]


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


def standardise(X):
    n, p = len(X), len(X[0])
    means = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    sds = []
    for j in range(p):
        var = sum((X[i][j] - means[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        sds.append(math.sqrt(var) if var > 0 else 1.0)
    return ([[(X[i][j] - means[j]) / sds[j] for j in range(p)] for i in range(n)],
            means, sds)


def ridge_fit(Z, y, lam):
    n, p = len(Z), len(Z[0])
    A = [[sum(Z[i][a] * Z[i][b] for i in range(n)) + (lam if a == b else 0.0)
          for b in range(p)] for a in range(p)]
    rhs = [sum(Z[i][a] * y[i] for i in range(n)) for a in range(p)]
    for col in range(p):
        piv = max(range(col, p), key=lambda r: abs(A[r][col]))
        if abs(A[piv][col]) < 1e-12:
            continue
        A[col], A[piv] = A[piv], A[col]
        rhs[col], rhs[piv] = rhs[piv], rhs[col]
        pv = A[col][col]
        for r in range(col + 1, p):
            f = A[r][col] / pv
            for c in range(col, p):
                A[r][c] -= f * A[col][c]
            rhs[r] -= f * rhs[col]
    x = [0.0] * p
    for r in range(p - 1, -1, -1):
        s = rhs[r] - sum(A[r][c] * x[c] for c in range(r + 1, p))
        if abs(A[r][r]) > 1e-12:
            x[r] = s / A[r][r]
    return x


def fit_predict(Xtr, ytr, Xte, lam):
    Z, means, sds = standardise(Xtr)
    b = ridge_fit(Z, ytr, lam)
    ybar = sum(ytr) / len(ytr)
    return [ybar + sum(((row[j] - means[j]) / sds[j]) * b[j]
                       for j in range(len(means))) for row in Xte]


def choose_lambda(X, y, seed=SEED, k=5):
    n = len(X)
    if n < k * 3:
        return 1.0
    idx = list(range(n))
    rng = random.Random(seed)
    rng.shuffle(idx)
    folds = [[] for _ in range(k)]
    for i, v in enumerate(idx):
        folds[i % k].append(v)
    best, bl = float("inf"), LAMBDA_GRID[0]
    for lam in LAMBDA_GRID:
        errs = []
        for f in range(k):
            te = folds[f]
            tr = [i for j in range(k) if j != f for i in folds[j]]
            if not te or len(tr) < 5:
                continue
            p = fit_predict([X[i] for i in tr], [y[i] for i in tr],
                            [X[i] for i in te], lam)
            errs.extend(abs(p[t] - y[te[t]]) for t in range(len(te)))
        if errs:
            m = sum(errs) / len(errs)
            if m < best:
                best, bl = m, lam
    return bl


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


def main() -> None:
    rows = load_csv(OUT / "orca_r2scan3c_descriptors.csv")
    usable = []
    for r in rows:
        if fnum(r.get("epsilon")) is None:
            continue
        xs = []
        ok = True
        for c in X0_COLS + X1_V7_COLS:
            v = fnum(r.get(c))
            if v is None and c == "homo_lumo_gap_ev_v7":
                v = fnum(r.get("homo_lumo_gap_ev"))
            if v is None:
                ok = False
                break
            xs.append(v)
        if not ok:
            continue
        usable.append({
            "inchikey": r["inchikey"],
            "name": r.get("name", ""),
            "family": r.get("family", "unknown"),
            "epsilon": fnum(r["epsilon"]),
            "x": xs,
        })

    n = len(usable)
    eps = [u["epsilon"] for u in usable]
    fam_idx = defaultdict(list)
    for i, u in enumerate(usable):
        fam_idx[u["family"]].append(i)

    families = []
    detail = []
    for fam, idxs in sorted(fam_idx.items()):
        if len(idxs) < 3:
            continue
        test = set(idxs)
        train = [i for i in range(n) if i not in test]
        Xtr = [usable[i]["x"] for i in train]
        ytr = [eps[i] for i in train]
        lam = choose_lambda(Xtr, ytr)
        pred = fit_predict(Xtr, ytr, [usable[i]["x"] for i in idxs], lam)
        y = [eps[i] for i in idxs]

        err = [pred[j] - y[j] for j in range(len(y))]
        bias = statistics.mean(err)
        mae = statistics.mean(abs(e) for e in err)
        mae_dm = statistics.mean(abs(e - bias) for e in err)
        ybar = statistics.mean(y)
        const_mae = statistics.mean(abs(v - ybar) for v in y)
        sd = statistics.pstdev(y) if len(y) > 1 else 0.0
        rho = spearman(pred, y)
        # within-family R^2 against the family mean
        sst = sum((v - ybar) ** 2 for v in y)
        sse = sum((pred[j] - y[j]) ** 2 for j in range(len(y)))
        r2 = 1 - sse / sst if sst > 0 else None
        # offset-only recalibration (family mean residual)
        cal_mae = mae_dm

        # robustness: how much does the single worst molecule drive MAE?
        abs_res = [abs(e) for e in err]
        worst = max(range(len(abs_res)), key=lambda j: abs_res[j])
        err_wo = [err[j] for j in range(len(err)) if j != worst]
        mae_excl_worst = statistics.mean(abs(e) for e in err_wo) if err_wo else None
        # extrapolation flag: residual bigger than 3x the family's own epsilon sd
        outlier_ids = [usable[idxs[j]]["inchikey"] for j in range(len(err))
                       if sd > 0 and abs_res[j] > 3 * sd]

        families.append({
            "family": fam,
            "n": len(idxs),
            "eps_mean": round(ybar, 3),
            "eps_sd": round(sd, 3),
            "eps_range": round(max(y) - min(y), 3),
            "lofo_mae": round(mae, 4),
            "lofo_bias": round(bias, 4),
            "lofo_mae_demeaned": round(mae_dm, 4),
            "baseline_mae": round(const_mae, 4),
            "beats_baseline": bool(mae < const_mae),
            "beats_baseline_after_offset": bool(cal_mae < const_mae),
            "spearman_within": round(rho, 4) if rho is not None else None,
            "r2_within": round(r2, 4) if r2 is not None else None,
            "bias_share_of_mae": round(abs(bias) / mae, 4) if mae > 0 else None,
            "mae_excluding_worst1": round(mae_excl_worst, 4) if mae_excl_worst is not None else None,
            "worst_molecule": usable[idxs[worst]]["name"],
            "worst_residual": round(err[worst], 4),
            "n_extrapolation_outliers": len(outlier_ids),
            "extrapolation_outliers": "; ".join(usable[idxs[j]]["name"]
                                                for j in range(len(err))
                                                if sd > 0 and abs_res[j] > 3 * sd),
        })
        for j, i in enumerate(idxs):
            detail.append({
                "inchikey": usable[i]["inchikey"],
                "name": usable[i]["name"],
                "family": fam,
                "epsilon": y[j],
                "lofo_pred": round(pred[j], 4),
                "resid": round(err[j], 4),
            })

    # summary
    n_beats = sum(1 for f in families if f["beats_baseline"])
    n_beats_cal = sum(1 for f in families if f["beats_baseline_after_offset"])
    bias_shares = [f["bias_share_of_mae"] for f in families
                   if f["bias_share_of_mae"] is not None]
    rhos = [f["spearman_within"] for f in families if f["spearman_within"] is not None]

    doc = {
        "schema": "b700.e4_family_diagnostics/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules": n,
        "n_families": len(families),
        "protocol": (
            "Leave-one-family-out: fit on all other families (lambda by 5-fold CV "
            "on the training families), predict the held-out family. Descriptors: "
            "X0 structure + r2SCAN-3c SP electronic (dipole, gap)."
        ),
        "families": families,
        "summary": {
            "n_families_beating_baseline": n_beats,
            "n_families_beating_baseline_after_offset_calibration": n_beats_cal,
            "median_bias_share_of_mae": round(statistics.median(bias_shares), 4) if bias_shares else None,
            "median_spearman_within": round(statistics.median(rhos), 4) if rhos else None,
            "interpretation": (
                "bias_share_of_mae 大 = 主要是整体平移误差（一次校准可修）；"
                "mae_demeaned 仍高 = 排序被破坏（校准修不了）；"
                "eps_sd 小 = 族内本来就均匀，常数基线已接近最优，任何迁移都难以超过它。"
            ),
        },
    }

    json_path = OUT / "B706_E4_family_diagnostics.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = OUT / "B706_E4_family_diagnostics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(families[0].keys()))
        w.writeheader()
        w.writerows(families)

    detail_path = OUT / "B706_E4_lofo_predictions.csv"
    with detail_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(detail[0].keys()))
        w.writeheader()
        w.writerows(detail)

    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {detail_path}")
    print(f"\n{'family':24s} {'n':>3s} {'eps_sd':>7s} {'MAE':>7s} {'bias':>7s} "
          f"{'MAE_dm':>7s} {'base':>7s} {'rho':>6s} {'bias%':>6s}")
    for f in families:
        print(f"{f['family']:24s} {f['n']:3d} {f['eps_sd']:7.3f} {f['lofo_mae']:7.3f} "
              f"{f['lofo_bias']:+7.3f} {f['lofo_mae_demeaned']:7.3f} {f['baseline_mae']:7.3f} "
              f"{(f['spearman_within'] if f['spearman_within'] is not None else float('nan')):6.3f} "
              f"{(f['bias_share_of_mae'] or 0):6.3f}")
    print(f"\nbeats baseline: {n_beats}/{len(families)}; "
          f"after offset calibration: {n_beats_cal}/{len(families)}")


if __name__ == "__main__":
    main()
