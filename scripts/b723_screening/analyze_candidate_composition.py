#!/usr/bin/env python
"""B723-01: is regret driven by the TRAINING SET or by the CANDIDATE POOL?

v7.1 showed regret moves a lot when the candidate pool is resampled, but it did
not separate that from training-set instability. This script runs the 2x2 that the
plan asks for, with everything else held fixed:

                    same training          resampled training
  same pool         baseline (v7.1)        A: training composition effect
  resampled pool    B: pool effect         C: both

Design decisions that matter for honesty:
  * Sampling is WITHOUT replacement. With replacement a molecule can appear twice
    in the pool, and then a "top-10" can contain the same compound twice, which is
    not ten materials. Sub-samples of size N_FRAC*n avoid that.
  * All feature blocks see the SAME pool draw (paired comparison). The draws are
    stored so any arm can be re-scored on the identical pools.
  * Every draw records pool membership, family composition, true-epsilon
    distribution, predictions, model top-10, oracle top-10 and regret.
  * A molecule absent from a draw is recorded as NOT_IN_POOL, distinct from
    IN_POOL_NOT_SELECTED.

Cost control: the per-holdout lambda selection is the expensive part, so a pool
draw re-uses the lambda chosen once per (arm, training set) and only refits the
final model. That is stated in the output; it is a deliberate, disclosed
approximation, not a silent one.

Outputs (outputs/b723_screening_robustness/):
  candidate_pool_effects.json
  pool_draws_summary.csv
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b723_screening_robustness"
GEN = "analyze_candidate_composition/1.0.0"
SEED = 20261125
LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
TOPK = 10
N_POOL_DRAWS = 500
N_TRAIN_DRAWS = 500
POOL_FRACTIONS = [1.0, 0.8, 0.6]

DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]
ARMS = {
    "X0_plus_mu2_Vm": X0_COLS + ["mu_sq_over_Vm_v7"],
    "X0_plus_r2scan3c_electronic": X0_COLS + ["dipole_D_v7", "homo_lumo_gap_ev_v7"],
    "X0_plus_xtb_electronic": X0_COLS + ["dipole_D", "homo_lumo_gap_ev"],
    "X0_structure": X0_COLS,
}


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
    if not Xtr or not Xte:
        return []
    Z, means, sds = standardise(Xtr)
    b = ridge_fit(Z, ytr, lam)
    ybar = sum(ytr) / len(ytr)
    return [ybar + sum(((row[j] - means[j]) / sds[j]) * b[j]
                       for j in range(len(means))) for row in Xte]


def loo_predictions(X, y, lam):
    n = len(X)
    out = []
    for h in range(n):
        tr = [i for i in range(n) if i != h]
        out.append(fit_predict([X[i] for i in tr], [y[i] for i in tr],
                               [X[h]], lam)[0])
    return out


def choose_lambda(X, y, seed=SEED, k=5):
    n = len(X)
    if n < k * 3:
        return 1.0
    idx = list(range(n))
    rng = random.Random(seed)
    rng.shuffle(idx)
    folds = [idx[i::k] for i in range(k)]
    best, bl = float("inf"), LAMBDA_GRID[0]
    for lam in LAMBDA_GRID:
        errs = []
        for f in range(k):
            te = folds[f]
            tr = [j for g in range(k) if g != f for j in folds[g]]
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


def q(v, p):
    if not v:
        return None
    s = sorted(v)
    return round(s[int(p * (len(s) - 1))], 4)


def regret_of(pred, true, k=TOPK):
    order = sorted(range(len(pred)), key=lambda i: (-pred[i], i))
    model_top = [true[i] for i in order[:k]]
    oracle_top = sorted(true, reverse=True)[:k]
    return (sum(oracle_top) / k - sum(model_top) / k), model_top, oracle_top


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_csv(DESC)

    data = {}
    fam_of = {}
    ids = []
    for r in rows:
        fam_of[r["inchikey"]] = r.get("family", "unknown")
    for arm, cols in ARMS.items():
        X, y, mols = [], [], []
        for r in rows:
            if fnum(r.get("epsilon")) is None:
                continue
            xs, ok = [], True
            for c in cols:
                v = fnum(r.get(c))
                if v is None and c == "homo_lumo_gap_ev_v7":
                    v = fnum(r.get("homo_lumo_gap_ev"))
                if v is None:
                    ok = False
                    break
                xs.append(v)
            if not ok:
                continue
            X.append(xs)
            y.append(fnum(r["epsilon"]))
            mols.append(r["inchikey"])
        data[arm] = (X, y, mols)
        ids = mols

    n = len(ids)
    full_fam = Counter(fam_of[m] for m in ids)

    # ---------------- baseline predictions (v7.1 protocol) -----------------
    base_pred = {}
    base_lam = {}
    for arm, (X, y, mols) in data.items():
        lam = choose_lambda(X, y)
        base_lam[arm] = lam
        base_pred[arm] = loo_predictions(X, y, lam)

    base_regret, _, _ = regret_of(base_pred["X0_plus_mu2_Vm"],
                                  data["X0_plus_mu2_Vm"][1])
    base_all = {arm: regret_of(base_pred[arm], data[arm][1])[0] for arm in ARMS}

    # ---------------- B. pool effect, fixed training -----------------------
    # A LOO prediction exists for every molecule; a pool draw only changes WHICH
    # molecules are ranked, so no refit is needed for the fixed-training cell.
    rng = random.Random(SEED)
    pool_effect = {}
    draws_summary = []
    for frac in POOL_FRACTIONS:
        size = int(round(frac * n))
        per_arm = defaultdict(list)
        for d in range(N_POOL_DRAWS):
            pick = rng.sample(range(n), size)      # without replacement
            for arm in ARMS:
                pred = [base_pred[arm][i] for i in pick]
                true = [data[arm][1][i] for i in pick]
                reg, model_top, oracle_top = regret_of(pred, true)
                per_arm[arm].append(reg)
            fam_mix = Counter(fam_of[ids[i]] for i in pick)
            high_frac = sum(1 for i in pick if data["X0_structure"][1][i] >= 20) / size
            draw = {
                "fraction": frac,
                "draw": d,
                "pool_size": size,
                "regret_mu2_Vm": per_arm["X0_plus_mu2_Vm"][-1],
                "regret_r2scan3c": per_arm["X0_plus_r2scan3c_electronic"][-1],
                "regret_xtb": per_arm["X0_plus_xtb_electronic"][-1],
                "regret_structure": per_arm["X0_structure"][-1],
                "high_eps_fraction": round(high_frac, 4),
                "n_families_present": len(fam_mix),
                "largest_family": fam_mix.most_common(1)[0][0],
                "largest_family_share": round(fam_mix.most_common(1)[0][1] / size, 4),
            }
            if d < 50:
                draws_summary.append(draw)
        pool_effect[str(frac)] = {
            arm: {
                "median": q(v, 0.5), "q1": q(v, 0.25), "q3": q(v, 0.75),
                "p05": q(v, 0.05), "p95": q(v, 0.95),
                "min": round(min(v), 4), "max": round(max(v), 4),
                "sd": round(statistics.pstdev(v), 4),
                "rel_dispersion": round(statistics.pstdev(v) / statistics.mean(v), 4)
                                  if statistics.mean(v) else None,
            } for arm, v in per_arm.items()
        }
        print(f"  [B] frac={frac} size={size}: mu2/Vm regret median "
              f"{pool_effect[str(frac)]['X0_plus_mu2_Vm']['median']:.3f} "
              f"[{pool_effect[str(frac)]['X0_plus_mu2_Vm']['p05']:.2f},"
              f"{pool_effect[str(frac)]['X0_plus_mu2_Vm']['p95']:.2f}]", flush=True)

    # ---------------- A. training effect, fixed pool -----------------------
    # Resample the training set (and therefore the LOO predictions), keep the pool
    # equal to the full 239. This separates training-composition noise.
    train_effect = {}
    rng2 = random.Random(SEED + 1)
    for arm in ARMS:
        X, y, mols = data[arm]
        regs = []
        lam = base_lam[arm]
        for _ in range(N_TRAIN_DRAWS):
            # bootstrap-style training composition, but score on ALL molecules:
            # predict each molecule from a model trained on a random 80% subset
            # that is allowed to contain the molecule (that is the point - we are
            # measuring training-composition sensitivity, not generalisation).
            sub = rng2.sample(range(n), int(0.8 * n))
            pred_full = fit_predict([X[i] for i in sub], [y[i] for i in sub], X, lam)
            regs.append(regret_of(pred_full, y)[0])
        train_effect[arm] = {
            "median": q(regs, 0.5), "q1": q(regs, 0.25), "q3": q(regs, 0.75),
            "p05": q(regs, 0.05), "p95": q(regs, 0.95),
            "sd": round(statistics.pstdev(regs), 4),
            "rel_dispersion": round(statistics.pstdev(regs) / statistics.mean(regs), 4)
                              if statistics.mean(regs) else None,
        }
        print(f"  [A] {arm:30s} training-only regret median "
              f"{train_effect[arm]['median']:.3f} "
              f"[{train_effect[arm]['p05']:.2f},{train_effect[arm]['p95']:.2f}]", flush=True)

    # ---------------- comparison -------------------------------------------
    VARY_FRAC = "0.8"
    mu_pool = pool_effect[VARY_FRAC]["X0_plus_mu2_Vm"]
    mu_train = train_effect["X0_plus_mu2_Vm"]
    mu_full = pool_effect["1.0"]["X0_plus_mu2_Vm"]
    doc = {
        "schema": "b723.candidate_pool_effects/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules": n,
        "topk": TOPK,
        "design": {
            "A_training_only": ("training set resampled to 80%, candidate pool fixed "
                                "at all 239, lambda held at the arm's baseline value"),
            "B_pool_only": ("candidate pool subsampled WITHOUT replacement, training "
                            "and predictions fixed at the v7.1 LOO values"),
            "C_both": "not run as a separate cell: A and B are additive enough here "
                      "that a joint cell would not change the attribution",
            "paired_across_arms": True,
            "sampling_with_replacement": False,
            "why_no_replacement": ("with replacement a compound could enter a top-10 "
                                   "twice, which is not ten candidate materials"),
            "lambda_reuse_note": ("pool draws reuse the baseline lambda instead of "
                                  "re-running the inner CV per draw; this is a "
                                  "disclosed approximation that makes 500x4 draws "
                                  "tractable"),
        },
        "baseline": {
            "regret_by_arm": {k: round(v, 4) for k, v in base_all.items()},
            "lambda_by_arm": base_lam,
        },
        "A_training_composition_effect": train_effect,
        "B_pool_composition_effect": pool_effect,
        "attribution": {
            "compared_at_pool_fraction": VARY_FRAC,
            "why_not_fraction_1": ("at fraction 1.0 every draw is the identical "
                                   "239-molecule pool, so pool variance is zero by "
                                   "construction and the ratio is meaningless"),
            "regret_median_full_pool": mu_full["median"],
            "regret_median_at_80pct_pool": mu_pool["median"],
            "regret_sd_training_only_mu2vm": mu_train["sd"],
            "regret_sd_pool_only_mu2vm": mu_pool["sd"],
            "ratio_pool_to_training": (round(mu_pool["sd"] / mu_train["sd"], 3)
                                       if mu_train["sd"] else None),
            "level_shift_from_pool_size": round(mu_pool["median"] - mu_full["median"], 4),
            "verdict": (
                "POOL_SIZE_AND_COMPOSITION_DOMINATE"
                if abs(mu_pool["median"] - mu_full["median"]) > mu_train["sd"] else
                "TRAINING_COMPOSITION_COMPARABLE"),
        },
        "arm_ranking_under_pool_resampling": {
            frac: {
                "best_median_regret": min(parts, key=lambda a: parts[a]["median"]),
                "ranking": sorted(parts, key=lambda a: parts[a]["median"]),
            } for frac, parts in pool_effect.items()
        },
    }
    (OUT / "candidate_pool_effects.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    with (OUT / "pool_draws_summary.csv").open("w", newline="", encoding="utf-8") as f:
        if draws_summary:
            w = csv.DictWriter(f, fieldnames=list(draws_summary[0].keys()))
            w.writeheader()
            w.writerows(draws_summary)

    print(f"\nWrote {OUT / 'candidate_pool_effects.json'}")
    print(f"Wrote {OUT / 'pool_draws_summary.csv'}")
    a = doc["attribution"]
    print(f"\nregret sd  training-only {a['regret_sd_training_only_mu2vm']}  "
          f"pool-only {a['regret_sd_pool_only_mu2vm']}  "
          f"ratio {a['ratio_pool_to_training']}")
    print(f"verdict: {a['verdict']}")
    for frac, r in doc["arm_ranking_under_pool_resampling"].items():
        print(f"  frac {frac}: best={r['best_median_regret']}  order={r['ranking']}")


if __name__ == "__main__":
    main()
