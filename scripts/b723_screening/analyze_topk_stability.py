#!/usr/bin/env python
"""B723-02: molecule-level Top-k recommendation stability.

A single regret number hides which compounds the model keeps recommending. This
builds the per-molecule table the plan asks for, and is explicit about the four
mutually exclusive states a molecule can be in on a given draw:

  NOT_IN_POOL          the draw did not include it (absence is NOT a rejection)
  IN_POOL_NOT_SELECTED included, not in the model's top-k
  TOPK_MODEL           in the model's top-k
  TOPK_ORACLE          in the true top-k (may also be TOPK_MODEL)

Reporting frequency over draws that EXCLUDE the molecule from the pool would
understate the selection rate, so the denominator is always "draws where the
molecule was in the pool". A separate column reports how often it was eligible.

Outputs (outputs/b723_screening_robustness/):
  molecule_recommendation_stability.csv
  topk_stability.json
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
GEN = "analyze_topk_stability/1.0.0"
SEED = 20261125
LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
TOPK = 10
N_DRAWS = 500
POOL_FRACTION = 0.8

DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]
ARMS = {
    "X0_plus_mu2_Vm": X0_COLS + ["mu_sq_over_Vm_v7"],
    "X0_plus_r2scan3c_electronic": X0_COLS + ["dipole_D_v7", "homo_lumo_gap_ev_v7"],
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
    return [fit_predict([X[i] for i in range(n) if i != h],
                        [y[i] for i in range(n) if i != h], [X[h]], lam)[0]
            for h in range(n)]


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


def rank_of(pred, i):
    """1-based rank, ties broken by index (stable)."""
    order = sorted(range(len(pred)), key=lambda j: (-pred[j], j))
    return order.index(i) + 1


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_csv(DESC)

    data, fam_of, truth = {}, {}, {}
    ids = []
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
            fam_of.setdefault(r["inchikey"], r.get("family", "unknown"))
            truth[r["inchikey"]] = fnum(r["epsilon"])
        data[arm] = (X, y, mols)
        ids = mols

    n = len(ids)

    # baseline LOO predictions per arm
    pred = {}
    for arm, (X, y, mols) in data.items():
        lam = choose_lambda(X, y)
        pred[arm] = loo_predictions(X, y, lam)

    results = {}
    for arm in ARMS:
        p_full = pred[arm]
        # states per molecule across pool draws
        eligible = Counter()
        selected = Counter()
        oracle_sel = Counter()
        ranks = defaultdict(list)
        rng = random.Random(SEED)
        size = int(round(POOL_FRACTION * n))
        for _ in range(N_DRAWS):
            pick = rng.sample(range(n), size)
            pp = [p_full[i] for i in pick]
            tt = [truth[ids[i]] for i in pick]
            order = sorted(range(size), key=lambda j: (-pp[j], j))
            model_top = set(order[:TOPK])
            oracle_top = set(sorted(range(size), key=lambda j: -tt[j])[:TOPK])
            for pos, i in enumerate(pick):
                eligible[i] += 1
                if pos in model_top:
                    selected[i] += 1
                if pos in oracle_top:
                    oracle_sel[i] += 1
                ranks[i].append(rank_of(pp, pos))

        mol_rows = []
        for i in range(n):
            ik = ids[i]
            n_elig = eligible[i]
            sel_rate = selected[i] / n_elig if n_elig else 0.0
            rk = ranks[i]
            rk_sorted = sorted(rk)
            mol_rows.append({
                "inchikey": ik,
                "name": "",
                "family": fam_of[ik],
                "true_epsilon": truth[ik],
                "prediction": round(p_full[i], 4),
                "n_draws_eligible": n_elig,
                "n_draws_selected_top10": selected[i],
                "top10_frequency": round(sel_rate, 4),
                "n_draws_in_oracle_top10": oracle_sel[i],
                "mean_rank": round(statistics.mean(rk), 2) if rk else "",
                "median_rank": rk_sorted[len(rk_sorted) // 2] if rk else "",
                "rank_iqr": (rk_sorted[int(0.75 * (len(rk_sorted) - 1))]
                             - rk_sorted[int(0.25 * (len(rk_sorted) - 1))]
                             if rk else ""),
                "state_when_absent": "NOT_IN_POOL",
            })
        mol_rows.sort(key=lambda r: -r["top10_frequency"])
        results[arm] = {
            "n_draws": N_DRAWS,
            "pool_fraction": POOL_FRACTION,
            "n_always_eligible": sum(1 for r in mol_rows if r["n_draws_eligible"] == N_DRAWS),
            "n_molecules_ever_selected": sum(1 for r in mol_rows
                                             if r["n_draws_selected_top10"] > 0),
            "top10_frequency_ge_0.5": sum(1 for r in mol_rows
                                          if r["top10_frequency"] >= 0.5),
            "top10_frequency_ge_0.9": sum(1 for r in mol_rows
                                          if r["top10_frequency"] >= 0.9),
            "mean_top10_frequency": round(statistics.mean(
                [r["top10_frequency"] for r in mol_rows]), 4),
            "molecules": mol_rows,
        }

    # combined CSV across arms (the plan asks for one molecule-level table)
    out_rows = []
    for arm, res in results.items():
        for r in res["molecules"]:
            out_rows.append({"arm": arm, **r})
    with (OUT / "molecule_recommendation_stability.csv").open(
            "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # stability summary
    summary = {
        "schema": "b723.topk_stability/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules": n,
        "topk": TOPK,
        "pool_fraction": POOL_FRACTION,
        "n_draws": N_DRAWS,
        "sampling": "without replacement",
        "state_definition": {
            "NOT_IN_POOL": "draw excluded the molecule; NOT counted as a rejection",
            "IN_POOL_NOT_SELECTED": "in pool, outside the model top-10",
            "TOPK_MODEL": "in the model top-10",
            "TOPK_ORACLE": "in the true top-10",
            "frequency_denominator": "draws in which the molecule was in the pool",
        },
        "arms": {
            arm: {k: v for k, v in res.items() if k != "molecules"}
            for arm, res in results.items()
        },
        "headline": {},
    }

    mu = results["X0_plus_mu2_Vm"]
    el = results["X0_plus_r2scan3c_electronic"]
    stable_mu = [r for r in mu["molecules"] if r["top10_frequency"] >= 0.9]
    stable_el = [r for r in el["molecules"] if r["top10_frequency"] >= 0.9]
    summary["headline"] = {
        "mu2vm_molecules_ever_selected": mu["n_molecules_ever_selected"],
        "mu2vm_molecules_stable_ge90pct": len(stable_mu),
        "electronic_molecules_ever_selected": el["n_molecules_ever_selected"],
        "electronic_molecules_stable_ge90pct": len(stable_el),
        "interpretation": (
            f"only {len(stable_mu)} of {n} molecules appear in the mu2/Vm top-10 on "
            f">=90% of draws; {mu['n_molecules_ever_selected']} appear at least once. "
            "A recommendation list that changes membership this much cannot be used "
            "as a stable shortlist without further evidence."
        ),
        "agreeing_molecules_across_arms": len(
            {r["inchikey"] for r in stable_mu} & {r["inchikey"] for r in stable_el}),
    }

    (OUT / "topk_stability.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'molecule_recommendation_stability.csv'}")
    print(f"Wrote {OUT / 'topk_stability.json'}")
    print()
    for arm, res in results.items():
        print(f"{arm:30s} ever_selected={res['n_molecules_ever_selected']:3d}  "
              f"freq>=0.5: {res['top10_frequency_ge_0.5']:3d}  "
              f"freq>=0.9: {res['top10_frequency_ge_0.9']:3d}  "
              f"mean_freq={res['mean_top10_frequency']:.4f}")
    print()
    print("headline:", json.dumps(summary["headline"], indent=2)[:600])


if __name__ == "__main__":
    main()
