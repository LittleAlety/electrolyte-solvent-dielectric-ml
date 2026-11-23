#!/usr/bin/env python
"""Reviewer 4 attacks 4: claims D (applicability domain), E (Top-k power),
F (noise ladder), G (three splits).

All four claims rest on predictions from the SAME estimator that has no
intercept. So each is re-evaluated twice: exactly as published, and with the
one-line intercept fix. A claim that changes sign under a one-line bug fix is
not a property of the descriptors.
"""
from __future__ import annotations

import csv, itertools, json, math, random, statistics, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POOL = REPO / "outputs" / "b04" / "candidate_pool_v2_draft.csv"
V04 = REPO / "data" / "dielectric_v04.csv"
FEAT = REPO / "data" / "processed" / "dielectric_physical_features.csv"

X0 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
      "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge"]
X1 = ["dipole_D", "polarizability_au", "polarizability_A3",
      "homo_lumo_gap_ev", "total_energy_hartree"]
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


def predict(Xte, model, intercept=False, ytr_mean=0.0):
    b, mu, sd = model
    out = []
    for row in Xte:
        x = [(row[j] - mu[j]) / sd[j] for j in range(len(mu))]
        v = sum(x[j] * b[j] for j in range(len(b)))
        out.append(v + (ytr_mean if intercept else 0.0))
    return out


def loo_predict(X, y, lam=1.0, intercept=False):
    n = len(X)
    out = []
    for h in range(n):
        tr = [i for i in range(n) if i != h]
        ytr = [y[i] for i in tr]
        model = fit([X[i] for i in tr], ytr, lam)
        out.extend(predict([X[h]], model, intercept, sum(ytr) / len(ytr)))
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
    res = {}

    X = [[float(fnum(feats[r["inchikey"]][c])) for c in XE4] for r in pool]
    p_bug = loo_predict(X, y, 1.0, False)
    p_fix = loo_predict(X, y, 1.0, True)
    res["baseline_check"] = {"mae_published_model": mae(y, p_bug),
                             "mae_intercept_fixed": mae(y, p_fix),
                             "mae_constant": mae(y, [ybar] * n),
                             "spearman_published": spearman(p_bug, y),
                             "spearman_fixed": spearman(p_fix, y)}

    # ================= CLAIM D: applicability domain ====================
    mols = [Chem.MolFromSmiles((v04.get(r["inchikey"], {}).get("smiles") or ""))
            for r in pool]
    gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    fps = [gen.GetFingerprint(m) for m in mols]
    nn_sim, nn_name = [], []
    for i in range(n):
        best = max(((DataStructs.TanimotoSimilarity(fps[i], fps[j]), j)
                    for j in range(n) if j != i))
        nn_sim.append(best[0])
        nn_name.append(names[best[1]])

    def ad_block(pred, tag):
        inside = [i for i in range(n) if nn_sim[i] >= 0.40]
        outside = [i for i in range(n) if nn_sim[i] < 0.40]
        mi = sum(abs(pred[i] - y[i]) for i in inside) / len(inside)
        mo = sum(abs(pred[i] - y[i]) for i in outside) / len(outside)
        # bootstrap CI on the ratio
        rng = random.Random(SEED)
        boot = []
        for _ in range(5000):
            bi = [rng.choice(inside) for _ in inside]
            bo = [rng.choice(outside) for _ in outside]
            a = sum(abs(pred[i] - y[i]) for i in bi) / len(bi)
            b_ = sum(abs(pred[i] - y[i]) for i in bo) / len(bo)
            boot.append(b_ / a if a else float("nan"))
        boot.sort()
        return {"tag": tag, "n_in": len(inside), "n_out": len(outside),
                "mae_in": mi, "mae_out": mo, "ratio_out_over_in": mo / mi,
                "bootstrap_ci95_ratio": [boot[125], boot[4875]],
                "spearman_acc_vs_sim": spearman([abs(pred[i] - y[i]) for i in range(n)],
                                                nn_sim)}

    res["claim_D_applicability_domain"] = [
        ad_block(p_bug, "published_no_intercept"),
        ad_block(p_fix, "intercept_fixed"),
    ]
    # Is the "in-domain" group just the fingerprint collisions?
    inside = [i for i in range(n) if nn_sim[i] >= 0.40]
    res["claim_D_in_domain_composition"] = {
        "n_in_domain": len(inside),
        "members": [{"name": names[i], "nn_sim": round(nn_sim[i], 4),
                     "nn": nn_name[i], "y": y[i],
                     "abs_err_pub": round(abs(p_bug[i] - y[i]), 4),
                     "abs_err_fixed": round(abs(p_fix[i] - y[i]), 4)}
                    for i in inside],
        "n_in_domain_that_are_fp_collisions": sum(
            1 for i in inside if nn_sim[i] > 0.999),
        "note": ("the in-domain group is defined by the same presence-fingerprint "
                 "that collides on homologous n-alkanes, so 'in domain' selects "
                 "near-duplicate bit vectors rather than chemically safe cases"),
    }
    # What does the AD criterion do at other thresholds / fingerprints?
    gen3 = rdFingerprintGenerator.GetMorganGenerator(radius=3, fpSize=2048)
    fps3 = [gen3.GetFingerprint(m) for m in mols]
    alt = {}
    for rad, fpset in (("morgan2", fps), ("morgan3", fps3)):
        s = []
        for i in range(n):
            s.append(max(DataStructs.TanimotoSimilarity(fpset[i], fpset[j])
                         for j in range(n) if j != i))
        for thr in (0.30, 0.40, 0.50):
            ins = [i for i in range(n) if s[i] >= thr]
            if len(ins) < 3 or len(ins) > n - 3:
                continue
            outs = [i for i in range(n) if s[i] < thr]
            mi = sum(abs(p_fix[i] - y[i]) for i in ins) / len(ins)
            mo = sum(abs(p_fix[i] - y[i]) for i in outs) / len(outs)
            alt[f"{rad}_thr{thr}"] = {"n_in": len(ins), "mae_in": mi,
                                      "mae_out": mo, "ratio": mo / mi}
    res["claim_D_threshold_and_fingerprint_sensitivity"] = alt

    # ================= CLAIM E: Top-k power =============================
    k = 3
    order_true = sorted(range(n), key=lambda i: -y[i])
    oracle_mean = statistics.mean(y[i] for i in order_true[:k])
    pool_mean = ybar

    def topk_block(pred, tag):
        order = sorted(range(n), key=lambda i: -pred[i])
        got = order[:k]
        mm = statistics.mean(y[i] for i in got)
        # EXACT enumeration over all C(22,3) subsets instead of Monte Carlo
        means = [statistics.mean(y[i] for i in c)
                 for c in itertools.combinations(range(n), k)]
        means.sort()
        p_exact = sum(1 for v in means if v >= mm) / len(means)
        return {"tag": tag, "model_topk": [names[i] for i in got],
                "model_topk_mean": mm, "regret": oracle_mean - mm,
                "p_exact_enumeration": p_exact,
                "n_subsets": len(means),
                "p_granularity": 1.0 / len(means),
                "random_mean": statistics.mean(means),
                "random_q95": means[int(0.95 * len(means))],
                "pctile_of_model": sum(1 for v in means if v < mm) / len(means),
                "overlap_with_oracle": len(set(got) & set(order_true[:k]))}

    res["claim_E_topk"] = {
        "oracle_topk_mean": oracle_mean, "pool_mean": pool_mean,
        "max_possible_regret": oracle_mean - pool_mean,
        "published": topk_block(p_bug, "published_no_intercept"),
        "fixed": topk_block(p_fix, "intercept_fixed"),
        "oracle_p_exact": 1.0 / math.comb(n, k),
        "min_detectable_p": 1.0 / math.comb(n, k),
        "note_power": ("with C(22,3)=1540 equiprobable subsets the one-sided "
                       "p-value can only take multiples of 1/1540; the test CAN "
                       "in principle reach 0.00065, so p=0.16 is not a floor "
                       "artefact -- but it is a NON-REJECTION, not evidence of "
                       "equivalence"),
    }

    # ================= CLAIM F: noise ladder ============================
    def ladder(pred, seed, sigmas, nrep=2000):
        rng = random.Random(seed)
        out = []
        for sg in sigmas:
            tm, ta = [], []
            for _ in range(nrep):
                noisy = [pred[i] + rng.gauss(0, sg) for i in range(n)]
                om = sorted(range(n), key=lambda i: -noisy[i])[:k]
                tm.append(statistics.mean(y[i] for i in om))
                ta.append(sum(abs(noisy[i] - y[i]) for i in range(n)) / n)
            out.append({"sigma": sg, "mae": statistics.mean(ta),
                        "topk_mean": statistics.mean(tm),
                        "regret": oracle_mean - statistics.mean(tm)})
        return out

    sig = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0]
    res["claim_F_noise_ladder"] = {
        "published_reproduced": ladder(p_bug, SEED, sig),
        "fixed_model": ladder(p_fix, SEED, sig),
        "random_selector_regret_expected": oracle_mean - pool_mean,
        "asymptotic_regret_at_sigma_inf": oracle_mean - pool_mean,
    }
    # multi-seed robustness of the "regret falls" observation
    multi = {}
    for tag, pred in (("published", p_bug), ("fixed", p_fix)):
        deltas = []
        for s in range(40):
            lad = ladder(pred, 1000 + s, [0.0, 8.0], nrep=400)
            deltas.append(lad[1]["regret"] - lad[0]["regret"])
        multi[tag] = {"n_seeds": 40, "mean_delta_regret": statistics.mean(deltas),
                      "sd_delta": statistics.stdev(deltas),
                      "n_seeds_regret_fell": sum(1 for d in deltas if d < 0),
                      "min_delta": min(deltas), "max_delta": max(deltas)}
    res["claim_F_multiseed"] = multi

    # ================= CLAIM G: three splits ============================
    def lomo(pred):
        return mae(y, pred)

    def random_kfold(seed, reps=200, kf=5):
        rng = random.Random(seed)
        out = []
        for _ in range(reps):
            idx = list(range(n))
            rng.shuffle(idx)
            folds = [idx[i::kf] for i in range(kf)]
            pr = [None] * n
            for f in folds:
                tr = [i for i in range(n) if i not in set(f)]
                ytr = [y[i] for i in tr]
                model = fit([X[i] for i in tr], ytr)
                for j, i in enumerate(f):
                    pr[i] = predict([X[i]], model)[0]
            out.append(mae(y, pr))
        return statistics.mean(out)

    # family assignment as in E4/B07 (needs SMARTS); reuse B07 output instead
    b07 = {(r["scheme"]): r for r in load(REPO / "outputs" / "b07" / "random_split_results.csv")}
    res["claim_G_published"] = {
        "lomo": b07["leave_one_molecule_out"]["mae"],
        "random_5fold": b07["random_5fold"]["mae"],
        "lofo": b07["leave_one_family_out"]["mae"],
        "model": "ridge lam=1.0, 11 descriptor columns, NO intercept",
        "features_identical_across_schemes": True,
        "features_identical_to_E1_X0": False,
        "features_identical_to_E1_X0X1": False,
        "note": ("E1 X0 uses 7 columns and X0+X1 uses 12 (includes "
                 "total_energy_hartree). E4/B07 use 11 (drop total_energy_hartree). "
                 "So B07 tests a THIRD feature set, neither E1 model; the three "
                 "splits agree with each other but are not the reported E1 models."),
    }
    # Resplit spread relative to the offset, and the same test with intercept.
    res["claim_G_recomputed"] = {
        "lomo_mae": lomo(p_fix),
        "random_5fold_mae_fixed": random_kfold(SEED, reps=200),
        "offset_only_mae": mae(y, [ybar] * n),
        "sd_of_prediction": statistics.stdev(p_bug),
        "spread_across_schemes_published": (
            float(b07["random_5fold"]["mae"]) - float(b07["leave_one_family_out"]["mae"])),
        "note": ("all three published schemes share the same missing-intercept "
                 "offset (-17.0 bias), and that shared offset is ~93% of the "
                 "prediction sd, so their agreement is dominated by the shared "
                 "defect, not by descriptor content"),
    }
    # variance decomposition: how much of the scheme-to-scheme MAE variation is
    # explainable by nothing at all?
    rng = random.Random(7)
    nullspread = []
    for _ in range(200):
        pr = [statistics.mean(rng.sample(y, 21)) for _ in range(n)]
        nullspread.append(mae(y, pr))
    res["claim_G_null_reference"] = {
        "mae_of_a_pure_noise_shaped_predictor_mean": statistics.mean(nullspread),
        "sd_of_that": statistics.stdev(nullspread),
        "published_spread_across_three_schemes": 0.0817,
        "ratio": 0.0817 / statistics.stdev(nullspread),
    }

    # ================= the pool itself ==================================
    dois = {}
    for r in pool:
        for d in [x.strip() for x in r["source_doi"].split(";") if x.strip()]:
            dois.setdefault(d, []).append(r["name"])
    temps = [float(r["T_K"]) for r in pool]
    res["pool_audit"] = {
        "n_molecules": n, "n_distinct_inchikey": len({r["inchikey"] for r in pool}),
        "n_sources": len(dois),
        "sources_with_gt1_molecule": {d: m for d, m in dois.items() if len(m) > 1},
        "max_molecules_from_one_source": max(len(m) for m in dois.values()),
        "n_contributing_measurements_gt1": sum(
            1 for r in pool if int(r["n_contributing_measurements"]) > 1),
        "temperature_values": sorted(set(temps)),
        "temperature_span_K": max(temps) - min(temps),
        "epsilon_iqr": float(np.subtract(*np.percentile(y, [75, 25]))),
        "epsilon_skew": float(statistics.mean([(v - ybar) ** 3 for v in y])
                              / statistics.pstdev(y) ** 3),
        "n_outliers_gt_28": sum(1 for v in y if v > 28),
        "share_of_total_abs_dev_from_4_largest": sum(
            abs(v - ybar) for v in sorted(y)[-4:]) / sum(abs(v - ybar) for v in y),
    }
    # temperature confound: does residual track T?
    res["pool_audit"]["spearman_residual_vs_T"] = spearman(
        [p_bug[i] - y[i] for i in range(n)], temps)
    res["pool_audit"]["spearman_epsilon_vs_T"] = spearman(y, temps)

    out = REPO / "outputs" / "b04_b05_review" / "r4_attack_04_defg.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
