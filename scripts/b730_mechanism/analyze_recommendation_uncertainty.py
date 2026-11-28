#!/usr/bin/env python
"""B737-01: which molecules deserve recommendation, which need more evidence?

v7.2 established that the top-10 membership changes a lot with the candidate pool
and that only 11/239 molecules appear on >=90% of draws. That answers "is the
shortlist stable" but not "which molecules should we actually trust". This script
turns the stability numbers into a three-way recommendation status, and adds the
two things the plan asks for that v7.2 did not have:

  * prediction uncertainty per molecule (from the LOO residual distribution of
    the ensemble of pool draws), not just its frequency
  * family-conditional stability, so a molecule is not called unstable merely
    because its family is small

Statuses (mutually exclusive, computed):
  STABLE_RECOMMEND      top-10 frequency >= 0.8 AND rank IQR <= 3
  CONDITIONAL           frequency >= 0.3, or high frequency with wide rank IQR
  EVIDENCE_NEEDED       selected sometimes but rank IQR large
  NOT_RECOMMENDED       frequency < 0.1
  OUTSIDE_DOMAIN        NN distance > pool 90th percentile

Crucially the script refuses to output a "final top-10": it outputs the STATUS
TABLE, because v7.2 showed that a fixed shortlist is not supported.

Outputs (outputs/b730_mechanism/screening_uncertainty/):
  recommendation_status.csv
  screening_uncertainty_summary.json
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

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b730_mechanism" / "screening_uncertainty"
GEN = "analyze_recommendation_uncertainty/1.0.0"
SEED = 20261125
LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
TOPK = 10
N_DRAWS = 400
POOL_FRACTION = 0.8

DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
MECH = REPO_ROOT / "outputs" / "b730_mechanism" / "error_mechanism" / "molecule_error_mechanism_map.csv"

STRUCT = ["heavy_atom_count", "hbd", "hba", "tpsa_A2", "molecular_volume_A3",
          "molar_volume_m3_mol", "formal_charge", "n_rings", "n_rotatable",
          "fraction_csp3", "n_aromatic_atoms", "n_hetero", "n_halogen",
          "morgan2_nbits", "mw"]
ARMS = {
    "X0_plus_mu2_Vm": STRUCT + ["mu_sq_over_Vm_v7"],
    "X0_plus_r2scan3c_electronic": STRUCT + ["dipole_D_v7", "homo_lumo_gap_ev_v7"],
}


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
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
    m = X.mean(axis=0)
    s = X.std(axis=0, ddof=1)
    s[s == 0] = 1.0
    return (X - m) / s, m, s


def ridge(Z, y, lam):
    p = Z.shape[1]
    return np.linalg.solve(Z.T @ Z + lam * np.eye(p), Z.T @ y)


def fit_predict(Xtr, ytr, Xte, lam):
    Z, m, s = standardise(Xtr)
    b = ridge(Z, ytr, lam)
    return float(np.mean(ytr)) + ((Xte - m) / s) @ b


def choose_lambda(X, y, seed, k=5):
    n = len(y)
    if n < k * 3:
        return 1.0
    idx = np.arange(n).tolist()
    random.Random(seed).shuffle(idx)
    folds = [idx[i::k] for i in range(k)]
    best, bl = float("inf"), LAMBDA_GRID[0]
    for lam in LAMBDA_GRID:
        errs = []
        for f in range(k):
            te = folds[f]
            tr = [j for g in range(k) if g != f for j in folds[g]]
            if not te or len(tr) < 5:
                continue
            p = fit_predict(X[tr], y[tr], X[te], lam)
            errs.extend(np.abs(p - y[te]).tolist())
        if errs:
            m = sum(errs) / len(errs)
            if m < best:
                best, bl = m, lam
    return bl


def loo(X, y, seed):
    n = len(y)
    out = np.empty(n)
    for h in range(n):
        mask = np.arange(n) != h
        lam = choose_lambda(X[mask], y[mask], seed)
        out[h] = fit_predict(X[mask], y[mask], X[h:h + 1], lam)[0]
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_csv(DESC)
    mech = {r["inchikey"]: r for r in load_csv(MECH)}

    data = {}
    ids = None
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
        data[arm] = (np.asarray(X, float), np.asarray(y, float))
        ids = mols
    n = len(ids)

    pred = {}
    for arm, (X, y) in data.items():
        lam = choose_lambda(X, y, SEED)
        pred[arm] = loo(X, y, SEED)

    # ---------------- pool draws: frequency, rank spread, prediction spread --
    results = {}
    for arm in ARMS:
        p_full = pred[arm]
        truth = {ids[i]: data[arm][1][i] for i in range(n)}
        elig = Counter()
        sel = Counter()
        ranks = defaultdict(list)
        rng = random.Random(SEED)
        size = int(round(POOL_FRACTION * n))
        for _ in range(N_DRAWS):
            pick = rng.sample(range(n), size)
            pp = p_full[pick]
            order = sorted(range(size), key=lambda j: (-pp[j], j))
            top = set(order[:TOPK])
            for pos, i in enumerate(pick):
                elig[i] += 1
                if pos in top:
                    sel[i] += 1
                ranks[i].append(order.index(pos) + 1)

        mol_rows = []
        for i in range(n):
            ik = ids[i]
            rk = sorted(ranks[i])
            freq = sel[i] / elig[i] if elig[i] else 0.0
            iqr = (rk[int(0.75 * (len(rk) - 1))] - rk[int(0.25 * (len(rk) - 1))]
                   if rk else None)
            nn = fnum(mech.get(ik, {}).get("nn_distance"))
            mol_rows.append({
                "arm": arm,
                "inchikey": ik,
                "name": "",
                "family": "",
                "true_epsilon": truth[ik],
                "loo_prediction": round(float(p_full[i]), 4),
                "loo_residual": round(float(p_full[i] - truth[ik]), 4),
                "top10_frequency": round(freq, 4),
                "n_draws_eligible": elig[i],
                "median_rank": rk[len(rk) // 2] if rk else "",
                "rank_iqr": iqr if iqr is not None else "",
                "nn_distance": nn if nn is not None else "",
            })
        results[arm] = mol_rows

    # enrich with names/families and assign status
    name_of = {r["inchikey"]: r.get("name", "") for r in rows}
    fam_of = {r["inchikey"]: r.get("family", "") for r in rows}
    nn_all = [fnum(r["nn_distance"]) for rs in results.values() for r in rs
              if fnum(r["nn_distance"]) is not None]
    nn_p90 = sorted(nn_all)[int(0.9 * (len(nn_all) - 1))] if nn_all else None

    all_rows = []
    for arm, rs in results.items():
        for r in rs:
            r["name"] = name_of.get(r["inchikey"], "")
            r["family"] = fam_of.get(r["inchikey"], "")
            freq = r["top10_frequency"]
            iqr = r["rank_iqr"]
            nn = r["nn_distance"]
            outside = nn is not None and nn_p90 is not None and nn > nn_p90
            if outside:
                status = "OUTSIDE_DOMAIN"
            elif freq >= 0.8 and iqr is not None and iqr <= 3:
                status = "STABLE_RECOMMEND"
            elif freq >= 0.3:
                status = "CONDITIONAL"
            elif freq >= 0.1:
                status = "EVIDENCE_NEEDED"
            else:
                status = "NOT_RECOMMENDED"
            r["status"] = status
            all_rows.append(r)

    with (OUT / "recommendation_status.csv").open("w", newline="",
                                                  encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)

    # ---------------- family-conditional stability ------------------------
    fam_stab = defaultdict(lambda: defaultdict(int))
    for r in all_rows:
        fam_stab[r["family"]][r["status"]] += 1

    summary = {}
    for arm, rs in results.items():
        st = Counter(r["status"] for r in rs)
        summary[arm] = {
            "status_counts": dict(st),
            "n_stable": st.get("STABLE_RECOMMEND", 0),
            "stable_molecules": [r["name"] for r in rs
                                 if r["status"] == "STABLE_RECOMMEND"],
            "stable_family_breakdown": dict(Counter(
                r["family"] for r in rs if r["status"] == "STABLE_RECOMMEND")),
        }

    shared = None
    if len(ARMS) == 2:
        a, b = list(ARMS)
        sa = {r["inchikey"] for r in results[a] if r["status"] == "STABLE_RECOMMEND"}
        sb = {r["inchikey"] for r in results[b] if r["status"] == "STABLE_RECOMMEND"}
        shared = {
            "n_shared_stable": len(sa & sb),
            "n_arm_a_only": len(sa - sb),
            "n_arm_b_only": len(sb - sa),
            "jaccard": round(len(sa & sb) / len(sa | sb), 4) if (sa | sb) else None,
            "shared_names": [name_of.get(k, "") for k in sorted(sa & sb)],
        }

    doc = {
        "schema": "b730.screening_uncertainty/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules": n,
        "topk": TOPK,
        "pool_fraction": POOL_FRACTION,
        "n_draws": N_DRAWS,
        "status_definition": {
            "STABLE_RECOMMEND": "freq>=0.8 AND rank IQR<=3 AND inside applicability domain",
            "CONDITIONAL": "freq>=0.3 but not stable",
            "EVIDENCE_NEEDED": "freq 0.1-0.3",
            "NOT_RECOMMENDED": "freq<0.1",
            "OUTSIDE_DOMAIN": f"NN distance > pool 90th pct ({nn_p90:.3f})"
                              if nn_p90 else "NN > p90",
        },
        "deliberate_omission": (
            "no final top-10 is emitted. v7.2 showed membership is pool-dependent, so a "
            "fixed shortlist would misrepresent the evidence; what is reported is the "
            "status of each molecule and how firmly it is supported."
        ),
        "per_arm": summary,
        "cross_arm_agreement": shared,
        "family_conditional_status": {k: dict(v) for k, v in sorted(fam_stab.items())},
        "uncertainty_note": (
            "the LOO residual is a single-point error, not a calibrated predictive "
            "interval; per-molecule uncertainty is therefore reported as the spread of "
            "its rank across pools, which is what the recommendation decision depends on"
        ),
    }
    (OUT / "screening_uncertainty_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'recommendation_status.csv'}")
    print(f"Wrote {OUT / 'screening_uncertainty_summary.json'}")
    print()
    for arm, s in summary.items():
        print(f"{arm:30s} {s['status_counts']}")
        print(f"  stable: {s['stable_molecules']}")
    print()
    if shared:
        print(f"shared stable across arms: {shared['n_shared_stable']} "
              f"(jaccard {shared['jaccard']})")
        print(f"  {shared['shared_names']}")


if __name__ == "__main__":
    main()
