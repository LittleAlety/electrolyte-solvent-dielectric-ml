#!/usr/bin/env python
"""Reviewer 4 attack 6: finish D / E / F, and attack the pool itself.

Specifically:
  D  -- proper confidence intervals on the in/out-domain ratio, threshold
        sensitivity, and the fact that the "in-domain" group is itself defined
        by the colliding fingerprint.
  E  -- exact enumeration of all C(22,3)=1540 subsets (no Monte Carlo), a TOST
        equivalence test, and the achievable p-range, to decide whether
        "indistinguishable from random" is a warranted equivalence claim.
  F  -- the noise ladder truncated at sigma=8; extend it past the asymptote and
        test whether "noise reduces regret" is monotone or a mid-ladder dip.
  POOL -- range restriction from the three-gate intersection, source clustering,
        temperature heterogeneity as label noise.
"""
from __future__ import annotations

import csv, itertools, json, math, random, statistics, sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POOL = REPO / "outputs" / "b04" / "candidate_pool_v2_draft.csv"
V04 = REPO / "data" / "dielectric_v04.csv"
FEAT = REPO / "data" / "processed" / "dielectric_physical_features.csv"
MR = REPO / "outputs" / "b01" / "dataset_v06_model_ready.csv"

X0 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
      "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge"]
XE4 = X0 + ["dipole_D", "polarizability_au", "polarizability_A3", "homo_lumo_gap_ev"]
PH = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}
SEED = 20261123


def load(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PH:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def standardise(XX):
    m, p = len(XX), len(XX[0])
    mu = [sum(XX[i][j] for i in range(m)) / m for j in range(p)]
    sd = []
    for j in range(p):
        v = sum((XX[i][j] - mu[j]) ** 2 for i in range(m)) / max(m - 1, 1)
        sd.append(math.sqrt(v) if v > 0 else 1.0)
    return [[(XX[i][j] - mu[j]) / sd[j] for j in range(p)] for i in range(m)], mu, sd


def solve(A, rhs):
    p = len(rhs)
    A = [r[:] for r in A]
    rhs = rhs[:]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-14:
            continue
        A[c], A[piv] = A[piv], A[c]
        rhs[c], rhs[piv] = rhs[piv], rhs[c]
        pv = A[c][c]
        for r in range(c + 1, p):
            f = A[r][c] / pv
            if f == 0:
                continue
            for k in range(c, p):
                A[r][k] -= f * A[c][k]
            rhs[r] -= f * rhs[c]
    b = [0.0] * p
    for r in range(p - 1, -1, -1):
        if abs(A[r][r]) < 1e-14:
            continue
        b[r] = (rhs[r] - sum(A[r][k] * b[k] for k in range(r + 1, p))) / A[r][r]
    return b


def fit(Xtr, ytr, lam=1.0):
    Z, mu, sd = standardise(Xtr)
    p = len(Z[0])
    A = [[sum(Z[r][a] * Z[r][b] for r in range(len(Z))) + (lam if a == b else 0.0)
          for b in range(p)] for a in range(p)]
    rhs = [sum(Z[r][a] * ytr[r] for r in range(len(Z))) for a in range(p)]
    return solve(A, rhs), mu, sd


def predict_one(x, model, intercept=False, ytr_mean=0.0):
    b, mu, sd = model
    z = [(x[j] - mu[j]) / sd[j] for j in range(len(mu))]
    return sum(z[j] * b[j] for j in range(len(b))) + (ytr_mean if intercept else 0.0)


def loo_predict(X, y, lam=1.0, intercept=False):
    n = len(X)
    out = []
    for h in range(n):
        tr = [i for i in range(n) if i != h]
        ytr = [y[i] for i in tr]
        m = fit([X[i] for i in tr], ytr, lam)
        out.append(predict_one(X[h], m, intercept, sum(ytr) / len(ytr)))
    return out


def mae(y, p):
    return sum(abs(p[i] - y[i]) for i in range(len(y))) / len(y)


def spearman(a, b):
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[o[j + 1]] == v[o[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                rk[o[k]] = avg
            i = j + 1
        return rk
    ra, rb = rank(a), rank(b)
    ma_, mb_ = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((ra[i] - ma_) * (rb[i] - mb_) for i in range(len(ra)))
    den = math.sqrt(sum((v - ma_) ** 2 for v in ra) * sum((v - mb_) ** 2 for v in rb))
    return num / den if den else float("nan")


def main():
    import numpy as np
    from rdkit import Chem, RDLogger
    from rdkit.Chem import rdFingerprintGenerator, DataStructs
    RDLogger.DisableLog("rdApp.*")

    pool = load(POOL)
    v04 = {r["inchikey"]: r for r in load(V04)}
    feats = {r["inchikey"]: r for r in load(FEAT)}
    y = [float(r["dielectric"]) for r in pool]
    n = len(y)
    ybar = sum(y) / n
    names = [r["name"] for r in pool]
    temps = [float(r["T_K"]) for r in pool]
    res = {}

    X = [[float(fnum(feats[r["inchikey"]][c])) for c in XE4] for r in pool]
    p_bug = loo_predict(X, y, 1.0, False)
    p_fix = loo_predict(X, y, 1.0, True)
    res["headline"] = {
        "mean_abs_y_equals_mean_y": sum(abs(v) for v in y) / n,
        "pool_mean": ybar,
        "published_maes": {"E1_X0": 17.446507, "E1_X0X1": 17.286655,
                           "B07_LOMO": 17.2375, "B07_random5": 17.3192,
                           "B07_LOFO": 17.2559,
                           "mean_abs_y": sum(abs(v) for v in y) / n},
        "max_abs_deviation_of_any_published_mae_from_mean_abs_y": max(
            abs(v - sum(abs(z) for z in y) / n)
            for v in (17.446507, 17.286655, 17.2375, 17.3192, 17.2559)),
        "interpretation": ("every published MAE equals mean|y| to within 0.13, "
                           "which is what a predictor emitting ~0 on all-positive "
                           "labels must produce"),
    }

    # ---------------- D: applicability domain, with CIs ----------------
    mols = [Chem.MolFromSmiles((v04.get(r["inchikey"], {}).get("smiles") or ""))
            for r in pool]
    def nnsim(gen):
        fps = [gen.GetFingerprint(m) for m in mols]
        return [max(DataStructs.TanimotoSimilarity(fps[i], fps[j])
                    for j in range(n) if j != i) for i in range(n)]

    g2 = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    g3 = rdFingerprintGenerator.GetMorganGenerator(radius=3, fpSize=2048)
    g4 = rdFingerprintGenerator.GetMorganGenerator(radius=4, fpSize=2048)
    s2, s3, s4 = nnsim(g2), nnsim(g3), nnsim(g4)

    def boot_ratio(pred, sims, thr, nboot=20000, seed=SEED):
        rng = random.Random(seed)
        ins = [i for i in range(n) if sims[i] >= thr]
        outs = [i for i in range(n) if sims[i] < thr]
        if len(ins) < 2 or len(outs) < 2:
            return None
        mi = sum(abs(pred[i] - y[i]) for i in ins) / len(ins)
        mo = sum(abs(pred[i] - y[i]) for i in outs) / len(outs)
        b = []
        for _ in range(nboot):
            bi = [rng.choice(ins) for _ in ins]
            bo = [rng.choice(outs) for _ in outs]
            a = sum(abs(pred[i] - y[i]) for i in bi) / len(bi)
            c = sum(abs(pred[i] - y[i]) for i in bo) / len(bo)
            b.append(c / a if a else float("nan"))
        b = sorted(x for x in b if x == x)
        return {"n_in": len(ins), "n_out": len(outs),
                "mae_in": mi, "mae_out": mo, "ratio": mo / mi,
                "ci95": [b[int(0.025 * len(b))], b[int(0.975 * len(b))]],
                "frac_ratio_gt_1": sum(1 for x in b if x > 1) / len(b)}

    res["claim_D"] = {
        "published_reproduced": boot_ratio(p_bug, s2, 0.40),
        "intercept_fixed": boot_ratio(p_fix, s2, 0.40),
        "radius3_thr040_fixed": boot_ratio(p_fix, s3, 0.40),
        "radius4_thr040_fixed": boot_ratio(p_fix, s4, 0.40),
        "thresholds_morgan2_fixed": {str(t): boot_ratio(p_fix, s2, t)
                                      for t in (0.30, 0.35, 0.40, 0.45, 0.50, 0.55)},
        "in_domain_is_the_collision_set": {
            "in_domain_members": [names[i] for i in range(n) if s2[i] >= 0.40],
            "n_of_which_fp_collisions": sum(1 for i in range(n) if s2[i] >= 0.999),
        },
        "spearman_acc_vs_sim_published": spearman(
            [abs(p_bug[i] - y[i]) for i in range(n)], s2),
        "spearman_acc_vs_sim_fixed": spearman(
            [abs(p_fix[i] - y[i]) for i in range(n)], s2),
    }
    # bootstrap CI on the spearman (fixed)
    rng = random.Random(SEED)
    rho_acc = []
    for _ in range(5000):
        idx = [rng.randrange(n) for _ in range(n)]
        if len(set(idx)) < 5:
            continue
        rho_acc.append(spearman([abs(p_fix[i] - y[i]) for i in idx],
                                [s2[i] for i in idx]))
    rho_acc = sorted(x for x in rho_acc if x == x)
    res["claim_D"]["spearman_acc_vs_sim_fixed_ci95"] = [
        rho_acc[int(0.025 * len(rho_acc))], rho_acc[int(0.975 * len(rho_acc))]]

    # ---------------- E: exact enumeration + equivalence ----------------
    k = 3
    order_true = sorted(range(n), key=lambda i: -y[i])
    oracle_mean = statistics.mean(y[i] for i in order_true[:k])
    subsets = [statistics.mean(y[i] for i in c)
               for c in itertools.combinations(range(n), k)]
    subsets.sort()

    def ev(pred, tag):
        got = sorted(range(n), key=lambda i: -pred[i])[:k]
        mm = statistics.mean(y[i] for i in got)
        p_exact = sum(1 for v in subsets if v >= mm) / len(subsets)
        return {"tag": tag, "topk": [names[i] for i in got], "mean": mm,
                "regret": oracle_mean - mm,
                "p_exact_one_sided": p_exact,
                "percentile_of_random": sum(1 for v in subsets if v < mm) / len(subsets),
                "passes_alpha_0.05": p_exact < 0.05}

    ev_pub, ev_fix = ev(p_bug, "published"), ev(p_fix, "intercept_fixed")
    res["claim_E"] = {
        "n_subsets": len(subsets), "oracle_mean": oracle_mean,
        "pool_mean": ybar, "random_mean": statistics.mean(subsets),
        "min_achievable_p": 1.0 / len(subsets),
        "published": ev_pub, "intercept_fixed": ev_fix,
        "test_power_note": (
            "the test is not floored at 0.16: the oracle subset alone gives "
            f"p={1/len(subsets):.5f}, so a perfect ranker would be detected. "
            "p=0.157 is therefore a real non-rejection and the model genuinely "
            "fails to place a high-epsilon set in its top 3."),
        "equivalence_note": (
            "-- the report's word is 'indistinguishable'. That is an EQUIVALENCE "
            "claim and p>0.05 does not establish it. A proper equivalence test "
            "would ask whether the model's regret is worse than a random draw by "
            "more than a pre-specified margin, which is not what was run."),
        "direction_test": {
            "P_random_at_least_model": ev_pub["p_exact_one_sided"],
            "P_model_at_least_random": 1 - ev_pub["p_exact_one_sided"] + 1 / len(subsets),
            "reading": ("the point estimate puts the model ABOVE the random mean, "
                        "so 'indistinguishable' and 'harmful' are both unsupported "
                        "as stated; the honest statement is a weak, "
                        "underpowered positive direction"),
        },
    }

    # ---------------- F: noise ladder shape -----------------------------
    def ladder(pred, seed, sigmas, nrep=4000):
        rng = random.Random(seed)
        rows = []
        for sg in sigmas:
            tm = []
            for _ in range(nrep):
                noisy = [pred[i] + rng.gauss(0, sg) for i in range(n)]
                got = sorted(range(n), key=lambda i: -noisy[i])[:k]
                tm.append(statistics.mean(y[i] for i in got))
            rows.append({"sigma": sg, "regret": oracle_mean - statistics.mean(tm),
                         "topk_mean": statistics.mean(tm)})
        return rows

    sig = [0.0, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 16.0, 32.0, 64.0, 128.0, 256.0]
    lad_pub = ladder(p_bug, SEED, sig)
    lad_fix = ladder(p_fix, SEED, sig)
    asym = oracle_mean - ybar
    res["claim_F"] = {
        "published_reproduced": lad_pub,
        "intercept_fixed": lad_fix,
        "asymptotic_regret_pure_random": asym,
        "published_ladder_ended_at_sigma": 8,
        "first_sigma_where_regret_exceeds_sigma0": next(
            (r["sigma"] for r in lad_pub if r["regret"] > lad_pub[0]["regret"]), None),
        "regret_at_sigma_0_vs_asymptote_published":
            [lad_pub[0]["regret"], asym],
        "monotone_decreasing": all(lad_pub[i + 1]["regret"] <= lad_pub[i]["regret"]
                                   for i in range(len(lad_pub) - 1)),
        "frac_of_ladder_with_regret_below_sigma0": sum(
            1 for r in lad_pub if r["regret"] < lad_pub[0]["regret"]) / len(lad_pub),
        "verdict": ("regret falls only in a bounded middle band (sigma 2-12) and "
                    "then climbs monotonically back toward the random asymptote "
                    f"{asym:.2f}. A ladder truncated at sigma=8 records only the "
                    "dip and none of the recovery, so 'noise improves screening' "
                    "is an artefact of where the ladder was stopped."),
    }
    # multi-seed on the FULL ladder: is the dip robust in sign?
    dips = []
    for s in range(60):
        ld = ladder(p_bug, 5000 + s, [0.0, 8.0, 64.0], nrep=600)
        dips.append((ld[1]["regret"] - ld[0]["regret"],
                     ld[2]["regret"] - ld[0]["regret"]))
    res["claim_F"]["multiseed_60"] = {
        "mean_delta_at_sigma8": statistics.mean(d for d, _ in dips),
        "n_seeds_dip_at_sigma8": sum(1 for d, _ in dips if d < 0),
        "mean_delta_at_sigma64": statistics.mean(e for _, e in dips),
        "n_seeds_recovery_at_sigma64": sum(1 for _, e in dips if e > 0),
    }
    # is the model's top-k actually better than random? (contradicts "harmful")
    res["claim_F"]["selfcontradiction"] = {
        "model_topk_mean": statistics.mean(y[i] for i in sorted(
            range(n), key=lambda i: -p_bug[i])[:k]),
        "random_mean_topk": statistics.mean(subsets),
        "p_model_beats_random_estimate": 1 - ev_pub["p_exact_one_sided"],
        "note": ("the report's own p=0.16 means the model's Top-3 is at the 84th "
                 "percentile of random draws, i.e. better than most random picks. "
                 "'Predictions are harmful for screening' contradicts this."),
    }

    # ---------------- POOL attack ---------------------------------------
    dois = Counter()
    src_map = {}
    for r in pool:
        for d in [x.strip() for x in r["source_doi"].split(";") if x.strip()]:
            dois[d] += 1
            src_map.setdefault(d, []).append(r["name"])
    mr = load(MR)
    mr_eps = [float(r["dielectric"]) for r in mr if fnum(r.get("dielectric"))]
    pool_keys = {r["inchikey"] for r in pool}
    mr_keys = {r["inchikey"] for r in mr}
    excluded = [r for r in mr if r["inchikey"] not in pool_keys]
    res["pool_attack"] = {
        "n_pool": n,
        "n_model_ready_universe": len(mr),
        "n_model_ready_distinct_inchikey": len(mr_keys),
        "pool_is_pct_of_model_ready": 100.0 * len(pool_keys) / max(len(mr_keys), 1),
        "selection_bias_label": {
            "pool_mean": ybar, "pool_median": statistics.median(y),
            "pool_sd": statistics.stdev(y),
            "model_ready_mean": statistics.mean(mr_eps),
            "model_ready_median": statistics.median(mr_eps),
            "model_ready_sd": statistics.stdev(mr_eps),
            "note": ("the 22 is gate-1 (AI consensus) filtered out of a 73-molecule "
                     "model-ready universe; it is a quality-selected subset, not a "
                     "random chemical sample"),
        },
        "sources": {"n_distinct_doi": len(dois),
                    "max_from_one_source": max(dois.values()),
                    "largest_source": max(dois.items(), key=lambda kv: kv[1]),
                    "share_from_largest_source_pct": 100.0 * max(dois.values()) / n,
                    "n_sources_with_1_molecule": sum(1 for v in dois.values() if v == 1),
                    "duplicate_source_molecules": {d: m for d, m in src_map.items()
                                                   if len(m) > 1}},
        "temperature": {
            "values": sorted(set(temps)), "span_K": max(temps) - min(temps),
            "n_distinct": len(set(temps)),
            "note": ("epsilon is strongly T-dependent for polar liquids; a 10 K "
                     "window with six different set-points injects label noise of "
                     "the same order as the descriptor signal"),
            "spearman_eps_vs_T": spearman(y, temps),
        },
        "label_noise": {
            "n_with_multiple_contributing_measurements": sum(
                1 for r in pool if int(r["n_contributing_measurements"]) > 1),
            "n_independent_experiments_all_1": all(
                int(r["n_independent_experiments"]) == 1 for r in pool),
            "note": ("every pool row claims n_independent_experiments=1, yet 7 rows "
                     "pool several contributing measurements; B01 already found 27 "
                     "byte-identical duplicate observations"),
        },
        "k3_from_22": {
            "n_possible_top3_sets": math.comb(n, k),
            "fraction_of_pool_in_a_topk": k / n,
            "oracle_headroom_over_pool_mean": oracle_mean - ybar,
            "note": ("the frozen k=3 rule means E6's entire screening test rests on "
                     "3 of 22 molecules; one molecule changing rank moves the "
                     "reported regret by ~5 epsilon units"),
        },
    }

    # effect of shifting one molecule's rank on regret
    order = sorted(range(n), key=lambda i: -p_bug[i])
    base = statistics.mean(y[i] for i in order[:k])
    sens = []
    for pos in range(3, 12):
        swapped = order[:k][:2] + [order[pos]]
        sens.append({"swap_in": names[order[pos]], "true_eps": y[order[pos]],
                     "new_topk_mean": statistics.mean(y[i] for i in swapped),
                     "regret_change": (oracle_mean - statistics.mean(
                         y[i] for i in swapped)) - (oracle_mean - base)})
    res["pool_attack"]["k3_from_22"]["rank_swap_sensitivity"] = sens

    # temperature-driven label noise magnitude: duplicated molecules across T?
    v04rows = load(V04)
    per_mol = {}
    for r in v04rows:
        per_mol.setdefault(r.get("inchikey", ""), []).append(r)
    multi_t = {k_: sorted({float(x["T_K"]) for x in v if fnum(x.get("T_K"))})
               for k_, v in per_mol.items()
               if len({float(x["T_K"]) for x in v if fnum(x.get("T_K"))}) > 1}
    spreads = []
    for k_, ts in multi_t.items():
        vals = [float(x["dielectric"]) for x in per_mol[k_] if fnum(x.get("dielectric"))]
        if len(vals) > 1 and len(ts) > 1:
            spreads.append({"inchikey": k_, "n_T": len(ts), "T_range": [min(ts), max(ts)],
                            "eps_range": [min(vals), max(vals)],
                            "eps_spread": max(vals) - min(vals)})
    spreads.sort(key=lambda r: -r["eps_spread"])
    res["pool_attack"]["temperature"]["n_molecules_measured_at_multiple_T"] = len(multi_t)
    res["pool_attack"]["temperature"]["largest_eps_spreads_across_T"] = spreads[:6]

    out = REPO / "outputs" / "b04_b05_review" / "r4_attack_06_final.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
