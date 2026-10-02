# -*- coding: utf-8 -*-
# W25: map the six development directions of the parent manuscript (v6) onto
# this repository.  Zero electronic-structure work: every reading comes from
# frozen W21-W24 artefacts.  No main-scoreboard shot is taken.
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
from pathlib import Path
import os as _os

# Runtime pin: numpy 2.5 spawns one BLAS worker per core, and the tiny
# n <= 246 solves in the active-learning replay then thrash on thread
# barriers (first attempt produced no progress in 20+ minutes).  Pinning
# every BLAS/OpenMP backend to one thread is a runtime setting only: the
# pre-registration and every statistical choice are unchanged.
for _thread_var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    _os.environ.setdefault(_thread_var, "1")

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "probes" / "w25_v6_alignment_prereg.json"
SUMMARY = ROOT / "probes" / "w25_v6_alignment_summary.json"
ART = ROOT / "probes" / "artifacts"
REPORT = ROOT / "reports" / "w25_v6_alignment.md"
DISP_CSV = ART / "w25_dispersion_criterion.csv"
ROBUST_CSV = ART / "w25_robust_inversion_attribution.csv"
AL_CSV = ART / "w25_al_budget.csv"
BRANCH_CSV = ART / "w25_branch_claims.csv"
FIG_A = ART / "w25_dispersion_criterion.png"
FIG_B = ART / "w25_robust_inversion.png"
FIG_C = ART / "w25_al_budget.png"

# Discipline: this week opens no new representation arm, so it takes no shot on
# the frozen main scoreboard.  The cumulative counter is the repository's own
# frozen tally (W21-W25 each contributed zero).
SCOREBOARD_SHOTS_THIS_WEEK = 0
CUMULATIVE_SCOREBOARD_ATTEMPTS = 12


def read_rows(path):
    with io.open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def as_float(value, default=None):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out):
        return default
    return out


def _rankdata(values):
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=float)
    sorted_values = values[order]
    i = 0
    while i < values.size:
        j = i + 1
        while j < values.size and sorted_values[j] == sorted_values[i]:
            j += 1
        ranks[order[i:j]] = 0.5 * (i + j - 1) + 1.0
        i = j
    return ranks


def spearman_rho(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 3:
        return float("nan")
    rx = _rankdata(x) - _rankdata(x).mean()
    ry = _rankdata(y) - _rankdata(y).mean()
    denom = math.sqrt(float((rx * rx).sum()) * float((ry * ry).sum()))
    if denom <= 0.0:
        return float("nan")
    return float((rx * ry).sum() / denom)


def kendall_tau_b(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = x.size
    if n < 3:
        return float("nan")
    sx = np.sign(np.subtract.outer(x, x))
    sy = np.sign(np.subtract.outer(y, y))
    upper = np.triu(np.ones((n, n), dtype=bool), 1)
    prod = sx * sy
    concordant = float(np.count_nonzero((prod > 0) & upper))
    discordant = float(np.count_nonzero((prod < 0) & upper))
    n0 = 0.5 * n * (n - 1)
    n1 = 0.5 * float(np.count_nonzero((sx == 0) & upper))
    n2 = 0.5 * float(np.count_nonzero((sy == 0) & upper))
    denom = math.sqrt(max(n0 - n1, 0.0) * max(n0 - n2, 0.0))
    if denom <= 0.0:
        return float("nan")
    return (concordant - discordant) / denom


def bootstrap_rho(x, y, draws, seed):
    rng = random.Random(seed)
    n = len(x)
    out = []
    for _ in range(draws):
        idx = [rng.randrange(n) for _ in range(n)]
        value = spearman_rho(np.asarray([x[i] for i in idx]), np.asarray([y[i] for i in idx]))
        if not math.isnan(value):
            out.append(value)
    out.sort()
    if not out:
        return float("nan"), float("nan")
    return float(out[int(0.025 * len(out))]), float(out[min(len(out) - 1, int(0.975 * len(out)))])


def load_rungs():
    rows = []
    for row in read_rows(ART / "w24_rung_table.csv"):
        rows.append({"pool": "N=246 (W24-1, GFN2-xTB)", "rung": row["rung"], "axis": row["axis"],
                     "n": as_float(row["n"], 0.0), "pairs": as_float(row["pairs"], 0.0),
                     "std": as_float(row["std_shift_eV"], 0.0),
                     "absmean": abs(as_float(row["mean_shift_eV"], 0.0)),
                     "tau_b": as_float(row["tau_b"], float("nan")),
                     "funres": as_float(row["f_unresolved_z=1.96"], float("nan")),
                     "frobust": as_float(row["f_robust_inversion"], float("nan")),
                     "robust_n": as_float(row["robust_inversions"], 0.0),
                     "resolved_both": as_float(row["pairs_resolved_both"], 0.0)})
    for row in read_rows(ART / "w24_2_rung_table.csv"):
        rows.append({"pool": "N=28 (W24-2, ORCA r2SCAN-3c)", "rung": row["rung"], "axis": row["axis"],
                     "n": as_float(row["n"], 0.0), "pairs": as_float(row["pairs"], 0.0),
                     "std": as_float(row["std_shift_eV"], 0.0),
                     "absmean": abs(as_float(row["mean_shift_eV"], 0.0)),
                     "tau_b": as_float(row["tau_b"], float("nan")),
                     "funres": as_float(row["f_unresolved_z=1.96"], float("nan")),
                     "frobust": as_float(row["f_robust_inversion"], float("nan")),
                     "robust_n": float("nan"), "resolved_both": float("nan")})
    return rows


def _ols(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    xm = x.mean()
    ym = y.mean()
    denom = float(((x - xm) ** 2).sum())
    if denom <= 0.0:
        return 0.0, float(ym)
    slope = float(((x - xm) * (y - ym)).sum() / denom)
    return slope, float(ym - slope * xm)


def dispersion_block(rungs, draws, seed, label, notes):
    x_std = [r["std"] for r in rungs]
    y_tau = [r["tau_b"] for r in rungs]
    x_abs = [r["absmean"] for r in rungs]
    y_fun = [r["funres"] for r in rungs]
    out = {"label": label, "n_rungs": len(rungs)}
    out["rho_std_tau"] = spearman_rho(x_std, y_tau)
    out["rho_absmean_tau"] = spearman_rho(x_abs, y_tau)
    out["rho_std_funres"] = spearman_rho(x_std, y_fun)
    out["ci_std_tau"] = bootstrap_rho(x_std, y_tau, draws, seed)
    out["ci_absmean_tau"] = bootstrap_rho(x_abs, y_tau, draws, seed + 1)
    out["ci_std_funres"] = bootstrap_rho(x_std, y_fun, draws, seed + 2)
    errors = []
    hits = 0
    for i, rung in enumerate(rungs):
        train = [r for j, r in enumerate(rungs) if j != i]
        slope, intercept = _ols([t["std"] for t in train], [t["tau_b"] for t in train])
        pred = slope * rung["std"] + intercept
        train_median = float(np.median([t["tau_b"] for t in train]))
        hit = (pred - train_median) * (rung["tau_b"] - train_median) >= 0.0
        hits += 1 if hit else 0
        errors.append(abs(pred - rung["tau_b"]))
    out["lvr_mae"] = float(np.mean(errors))
    out["lvr_direction_hits"] = hits
    out["lvr_direction_total"] = len(rungs)
    dropped = []
    for i in range(len(rungs)):
        keep = [r for j, r in enumerate(rungs) if j != i]
        dropped.append(spearman_rho([r["std"] for r in keep], [r["tau_b"] for r in keep]))
    out["rho_std_tau_drop_one_min"] = float(np.nanmin(dropped))
    out["rho_std_tau_drop_one_max"] = float(np.nanmax(dropped))
    out["notes"] = notes
    return out


def write_dispersion_csv(blocks, prior):
    header = ["block", "quantity", "value", "ci_lo", "ci_hi", "note"]
    rows = []
    for block in blocks:
        rows.append([block["label"], "n_rungs", block["n_rungs"], "", "", block["notes"]])
        rows.append([block["label"], "rho(std, tau_b)", fmt(block["rho_std_tau"]), fmt(block["ci_std_tau"][0]), fmt(block["ci_std_tau"][1]), "v6 (n=10): -0.8511"])
        rows.append([block["label"], "rho(|mean|, tau_b)", fmt(block["rho_absmean_tau"]), fmt(block["ci_absmean_tau"][0]), fmt(block["ci_absmean_tau"][1]), "v6 (n=10): -0.5350"])
        rows.append([block["label"], "rho(std, f_unresolved)", fmt(block["rho_std_funres"]), fmt(block["ci_std_funres"][0]), fmt(block["ci_std_funres"][1]), "v6 (n=10): +0.8936"])
        rows.append([block["label"], "leave-one-rung-out MAE (tau_b)", fmt(block["lvr_mae"]), "", "", "v6: 0.483"])
        rows.append([block["label"], "leave-one-rung-out direction hits", block["lvr_direction_hits"], "", "", "of " + str(block["lvr_direction_total"]) + "; v6: 9/10"])
        rows.append([block["label"], "rho(std, tau_b) drop-one range", fmt(block["rho_std_tau_drop_one_min"]) + " to " + fmt(block["rho_std_tau_drop_one_max"]), "", "", "v6: [-0.912, -0.795]"])
    for key, value in prior:
        rows.append(["prior frozen reading (W24-1)", key, value, "", "", "probes/artifacts/w24_displacement_law.csv"])
    write_csv(DISP_CSV, header, rows)
    return rows


def fmt(value, digits=12):
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, int):
        return str(value)
    return ("{:." + str(digits) + "f}").format(float(value))


def robust_block(rungs, draws, seed):
    nonzero = [r for r in rungs if (r["frobust"] or 0.0) > 0.0]
    x = [r["frobust"] for r in rungs]
    y = [r["funres"] for r in rungs]
    rho = spearman_rho(x, y)
    ci = bootstrap_rho(x, y, draws, seed)
    strata = {}
    for rung in nonzero:
        is_c = rung["rung"].startswith("C")
        key = ("C rung" if is_c else "P rung") + " / " + rung["axis"]
        strata[key] = strata.get(key, 0) + 1
    header = ["pool", "rung", "axis", "n", "pairs", "tau_b", "f_unresolved_z1.96", "f_robust_inversion", "robust_inversions", "pairs_resolved_both", "stratum", "note"]
    rows = []
    for rung in rungs:
        is_c = rung["rung"].startswith("C")
        note = ""
        if (rung["frobust"] or 0.0) > 0.0:
            note = "nonzero robust inversion"
        rows.append([rung["pool"], rung["rung"], rung["axis"], int(rung["n"]), int(rung["pairs"]),
                     fmt(rung["tau_b"]), fmt(rung["funres"]), fmt(rung["frobust"]),
                     fmt(rung["robust_n"]), fmt(rung["resolved_both"]),
                     ("C rung" if is_c else "P rung"), note])
    write_csv(ROBUST_CSV, header, rows)
    summary = {"n_rungs": len(rungs), "n_nonzero": len(nonzero),
               "frobust_max": float(np.nanmax(x)), "frobust_mean": float(np.nanmean(x)),
               "rho_frobust_funres": rho, "ci_frobust_funres": ci,
               "funres_of_nonzero_min": float(np.nanmin([r["funres"] for r in nonzero])) if nonzero else float("nan"),
               "strata": strata, "rows": rows}
    return summary


AL_FEATURES = ("homo_free_eV", "lumo_free_eV", "gap_free_eV", "formal_charge", "total_energy_free_hartree")
AL_ALPHAS = (0.01, 0.1, 1.0, 10.0)


def load_al_pool():
    rows = read_rows(ROOT / "data" / "processed" / "w21_li_coordination_layer.csv")
    features = []
    target = []
    keys = []
    for row in rows:
        values = [as_float(row.get(name)) for name in AL_FEATURES]
        shift = as_float(row.get("delta_homo_eV"))
        if any(value is None for value in values) or shift is None:
            continue
        features.append(values)
        target.append(shift)
        keys.append(row.get("inchikey") or row.get("name") or "")
    return np.asarray(features, dtype=float), np.asarray(target, dtype=float), keys


def _sqdist(a, b):
    return np.maximum((a * a).sum(1)[:, None] + (b * b).sum(1)[None, :] - 2.0 * a @ b.T, 0.0)


def _rbf(a, b, gamma):
    return np.exp(-gamma * _sqdist(a, b))


def _standardize(train, other):
    mu = train.mean(0)
    sd = train.std(0)
    sd = np.where(sd <= 0.0, 1.0, sd)
    return (train - mu) / sd, (other - mu) / sd


def krr_fit(a_train, y_train, alpha):
    gamma = 1.0 / max(a_train.shape[1], 1)
    kernel = _rbf(a_train, a_train, gamma)
    mean = float(y_train.mean())
    coef = np.linalg.solve(kernel + alpha * np.eye(a_train.shape[0]), y_train - mean)
    return {"a_train": a_train, "coef": coef, "mean": mean, "gamma": gamma}


def krr_predict(model, a_test):
    kernel = _rbf(model["a_train"], a_test, model["gamma"])
    return model["mean"] + kernel.T @ model["coef"]


def pick_alpha(a_train, y_train):
    best_alpha = AL_ALPHAS[0]
    best_err = float("inf")
    n = a_train.shape[0]
    gamma = 1.0 / max(a_train.shape[1], 1)
    kernel = _rbf(a_train, a_train, gamma)
    mean = float(y_train.mean())
    for alpha in AL_ALPHAS:
        inverse = np.linalg.inv(kernel + alpha * np.eye(n))
        hat = kernel @ inverse
        fitted = hat @ (y_train - mean) + mean
        leverage = np.clip(1.0 - np.diag(hat), 1e-9, None)
        residual = (y_train - fitted) / leverage
        err = float(np.mean(residual ** 2))
        if err < best_err:
            best_err = err
            best_alpha = alpha
    return best_alpha


def acquire(kind, z_pool, revealed, ensemble_std, vote, top_k, rng):
    unlabeled = np.asarray([i for i in range(z_pool.shape[0]) if i not in revealed], dtype=int)
    if kind == "random":
        return int(rng.choice(unlabeled))
    if kind == "diversity":
        marked = z_pool[np.asarray(sorted(revealed), dtype=int)]
        dist = _sqdist(z_pool[unlabeled], marked)
        return int(unlabeled[int(np.argmax(dist.min(1)))])
    if kind == "uncertainty":
        return int(unlabeled[int(np.argmax(ensemble_std[unlabeled]))])
    probability = np.clip(vote, 1e-6, 1.0 - 1e-6)
    entropy = -(probability * np.log(probability) + (1.0 - probability) * np.log(1.0 - probability))
    return int(unlabeled[int(np.argmax(entropy[unlabeled]))])


def replay(pool_x, pool_y, pool_z, kind, seed, initial, max_steps, tau_target, ensemble=6):
    rng = random.Random(seed)
    n = pool_x.shape[0]
    revealed = set(rng.sample(range(n), initial))
    curve = []
    top_k = max(1, int(round(0.20 * n)))
    for step in range(max_steps):
        idx = np.asarray(sorted(revealed), dtype=int)
        a_train, a_all = _standardize(pool_x[idx], pool_x)
        alpha = pick_alpha(a_train, pool_y[idx])
        model = krr_fit(a_train, pool_y[idx], alpha)
        mean_pred = krr_predict(model, a_all)
        members = []
        for _ in range(ensemble):
            pick = np.asarray([idx[rng.randrange(idx.size)] for _ in range(idx.size)], dtype=int)
            sub_a, _ = _standardize(pool_x[pick], pool_x)
            sub_model = krr_fit(sub_a, pool_y[pick], alpha)
            members.append(krr_predict(sub_model, a_all))
        ensemble_std = np.std(np.asarray(members), axis=0)
        member_ranks = []
        for member in members:
            order_m = np.argsort(-np.asarray(member))
            rank_m = np.empty(order_m.size, dtype=float)
            rank_m[order_m] = np.arange(order_m.size)
            member_ranks.append((rank_m < top_k).astype(float))
        vote = np.mean(np.asarray(member_ranks), axis=0)
        assembled = mean_pred.copy()
        assembled[idx] = pool_y[idx]
        tau = kendall_tau_b(assembled, pool_y)
        curve.append({"k": idx.size, "tau_b": tau, "alpha": alpha})
        if step == max_steps - 1:
            break
        nxt = acquire(kind, pool_z, revealed, ensemble_std, vote, top_k, rng)
        revealed.add(int(nxt))
    n_t = None
    for point in curve:
        if point["tau_b"] >= tau_target:
            n_t = point["k"]
            break
    return {"curve": curve, "n_T": n_t, "initial": initial, "n_pool": n}


def al_block(pool_x, pool_y, pool_z, prereg, drawn_seed):
    kinds = prereg["arms"]["W25-3"]["acquisitions"]
    seeds = int(prereg["arms"]["W25-3"]["seeds"])
    initial = int(prereg["arms"]["W25-3"]["initial_labels"])
    max_steps = int(prereg["arms"]["W25-3"]["max_steps"])
    tau_target = float(prereg["arms"]["W25-3"]["tau_target"])
    rows = []
    n_t = {}
    curves = {}
    for kind in kinds:
        n_t[kind] = []
        curves[kind] = []
        for offset in range(seeds):
            seed = drawn_seed + 1000 * kinds.index(kind) + offset
            out = replay(pool_x, pool_y, pool_z, kind, seed, initial, max_steps, tau_target)
            n_t[kind].append(out["n_T"] if out["n_T"] is not None else max_steps + 1)
            curves[kind].append([point["tau_b"] for point in out["curve"]])
            for point in out["curve"]:
                rows.append([kind, seed, point["k"], fmt(point["tau_b"]), fmt(point["alpha"])])
    write_csv(AL_CSV, ["acquisition", "seed", "labels", "tau_b", "alpha"], rows)
    summary = {"kinds": list(kinds), "n_T_median": {}, "curves": {}, "budget_censored_at": max_steps + 1}
    for kind in kinds:
        summary["n_T_median"][kind] = float(np.median(n_t[kind]))
        stacked = np.asarray(curves[kind], dtype=float)
        summary["curves"][kind] = [float(v) for v in np.median(stacked, axis=0)]
    summary["n_T_per_seed"] = {kind: [int(v) for v in n_t[kind]] for kind in kinds}
    return summary, curves


PREFERRED_FONTS = ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC")


def configure_fonts():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    installed = {font.name for font in font_manager.fontManager.ttflist}
    for name in PREFERRED_FONTS:
        if name in installed:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def learnability(pool_x, pool_y):
    a_all, _ = _standardize(pool_x, pool_x)
    alpha = pick_alpha(a_all, pool_y)
    gamma = 1.0 / max(a_all.shape[1], 1)
    kernel = _rbf(a_all, a_all, gamma)
    mean = float(pool_y.mean())
    inverse = np.linalg.inv(kernel + alpha * np.eye(a_all.shape[0]))
    hat = kernel @ inverse
    fitted = hat @ (pool_y - mean) + mean
    leverage = np.clip(1.0 - np.diag(hat), 1e-9, None)
    loo = (fitted - np.diag(hat) * pool_y) / leverage
    ss_res = float(((pool_y - loo) ** 2).sum())
    ss_tot = float(((pool_y - pool_y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"n": int(pool_y.size), "alpha": alpha, "r2_loo": r2,
            "tau_b_loo": kendall_tau_b(loo, pool_y),
            "mae_loo": float(np.mean(np.abs(pool_y - loo)))}


def build_branch_claims(disp_all, robust, al_summary, learn):
    rows = []
    rows.append(["A", "cheap proxy already sufficient", "NOT SUPPORTED",
                 "P0->P2 ox tau_b = 0.673, top-10 overlap 0.000, f_unresolved = 0.229",
                 "C0->C1 red f_unresolved 0.758-0.812 and top-10 overlap 0.000-0.048 on 246 compounds",
                 "NOT SUPPORTED"])
    rows.append(["B", "large shift but stable ranking", "SUPPORTED",
                 "P1->P2 ox mean -2.393 eV, std 0.302 eV, tau_b = 0.895, f_robust = 0.000",
                 "P0->P1 ox mean 2.946 eV, std 0.483 eV, tau_b = 0.6776, f_robust = 0.1386 on 246 compounds",
                 "PARTIALLY SUPPORTED (differs from v6)"])
    rows.append(["C", "structurally concentrated robust inversion", "NOT OBSERVED",
                 "f_robust_inv = 0 in all 40 readings (5 rungs x 2 axes x 2 pools x 2 z)",
                 "nonzero f_robust_inversion on " + str(robust["n_nonzero"]) + " of " + str(robust["n_rungs"]) + " rungs, max " + fmt(robust["frobust_max"], 4),
                 "OBSERVED (differs from v6)"])
    rows.append(["D", "coordination changes state identity", "OBSERVED",
                 "11 of 12 reduction states are Li-centred or mixed",
                 "Li-centred share on 246 compounds: c_1 = 0.340, c_2 = 0.258 (threshold 0.50; W24-1 H2 judged not met)",
                 "PARTIALLY SUPPORTED (differs from v6)"])
    rows.append(["E", "shift (delta) learning beats direct learning", "SUPPORTED",
                 "7 of 8 groups positive, 3 intervals exclude 0",
                 "not tested this round: W25-3 measures the label budget, not the learning shape",
                 "NOT TESTED"])
    rows.append(["F", "shift cannot be learned from cheap features", "NOT SUPPORTED",
                 "7 of 8 groups have delta tau_b > 0",
                 "X0 -> C0->C1 shift proxy: leave-one-out R2 = " + fmt(learn["r2_loo"], 4) + ", tau_b = " + fmt(learn["tau_b_loo"], 4) + ", n = " + str(learn["n"]),
                 "NOT SUPPORTED (same direction as v6)"])
    rows.append(["G", "most pairs unresolved", "PARTIALLY SUPPORTED",
                 "C0->C1 red tau_b = -0.467, f_unresolved = 0.800; P0->P1 red f_unresolved = 0.733",
                 "C0->C1 red f_unresolved 0.758-0.812 on 246 compounds (confirmed, sharper)",
                 "SUPPORTED"])
    write_csv(BRANCH_CSV, ["branch", "criterion", "v6_verdict", "v6_evidence", "in_repo_evidence", "in_repo_verdict"], rows)
    differing = [row[0] for row in rows if not str(row[5]).split(" ")[0].startswith(str(row[2]).split(" ")[0])]
    return rows, differing


def figure_a(plt, blocks, rungs_all):
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0))
    std = [r["std"] for r in rungs_all]
    tau = [r["tau_b"] for r in rungs_all]
    axes[0].scatter(std, tau, s=28, color="#2b6cb0")
    slope, intercept = _ols(std, tau)
    grid = np.linspace(min(std), max(std), 50)
    axes[0].plot(grid, slope * grid + intercept, color="#c53030", lw=1.6)
    axes[0].set_xlabel("\u4f4d\u79fb\u79bb\u6563\u5ea6 std / eV")
    axes[0].set_ylabel("\u6392\u5e8f\u4e00\u81f4\u6027 tau_b")
    axes[0].set_title("(a) 38 \u53f0\u9636-\u8f74: std vs tau_b, rho = " + fmt(blocks[0]["rho_std_tau"], 4))
    labels = ["rho(std, tau_b)", "rho(|mean|, tau_b)", "rho(std, f_unres)"]
    ours = [blocks[0]["rho_std_tau"], blocks[0]["rho_absmean_tau"], blocks[0]["rho_std_funres"]]
    paper = [-0.8511, -0.5350, 0.8936]
    cis = [blocks[0]["ci_std_tau"], blocks[0]["ci_absmean_tau"], blocks[0]["ci_std_funres"]]
    xpos = np.arange(len(labels))
    lo = [o - c[0] for o, c in zip(ours, cis)]
    hi = [c[1] - o for o, c in zip(ours, cis)]
    axes[1].errorbar(xpos - 0.10, ours, yerr=[lo, hi], fmt="o", color="#2b6cb0",
                     label="\u672c\u4ed3 38 \u53f0\u9636 (bootstrap 95%)", capsize=4)
    axes[1].scatter(xpos + 0.10, paper, marker="s", color="#c05621", s=44,
                    label="\u6bcd\u4f53\u8bba\u6587 v6 (n = 10)")
    axes[1].axhline(0.0, color="#888888", lw=1.0, ls="--")
    axes[1].set_xticks(xpos)
    axes[1].set_xticklabels(labels, fontsize=8.5)
    axes[1].set_ylabel("Spearman rho")
    axes[1].set_title("(b) \u79bb\u6563\u5ea6\u5224\u636e: \u672c\u4ed3 vs v6")
    axes[1].legend(fontsize=8.5)
    fig.tight_layout()
    fig.savefig(FIG_A, dpi=160)
    plt.close(fig)


def figure_b(plt, robust):
    rows = robust["rows"]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0))
    xs = [float(row[6]) for row in rows]
    ys = [float(row[7]) for row in rows]
    colors = ["#c53030" if str(row[0]).startswith("C") else "#2b6cb0" for row in rows]
    axes[0].scatter(xs, ys, s=30, c=colors)
    axes[0].axhline(0.0, color="#888888", lw=1.0, ls="--")
    axes[0].set_xlabel("\u672a\u89e3\u6790\u5360\u6bd4 f_unresolved (z = 1.96)")
    axes[0].set_ylabel("\u7a33\u5065\u7ffb\u8f6c\u6bd4\u4f8b f_robust_inversion")
    axes[0].set_title("(a) \u7a33\u5065\u7ffb\u8f6c vs \u672a\u89e3\u6790\u5360\u6bd4\uff08\u84dd = P \u53f0\u9636\uff0c\u7ea2 = C \u53f0\u9636\uff09")
    ordered = sorted(rows, key=lambda row: -float(row[7]))[:14]
    names = [str(row[1]) + "|" + str(row[2]) for row in ordered]
    values = [float(row[7]) for row in ordered]
    colors2 = ["#c53030" if str(row[0]).startswith("C") else "#2b6cb0" for row in ordered]
    axes[1].barh(range(len(names)), values, color=colors2)
    axes[1].set_yticks(range(len(names)))
    axes[1].set_yticklabels(names, fontsize=7.5)
    axes[1].invert_yaxis()
    axes[1].set_xlabel("f_robust_inversion")
    axes[1].set_title("(b) \u7a33\u5065\u7ffb\u8f6c\u6700\u9ad8\u7684\u53f0\u9636-\u8f74\uff08v6 \u62a5 40 \u4e2a\u8bfb\u6570\u5168 0\uff09")
    fig.tight_layout()
    fig.savefig(FIG_B, dpi=160)
    plt.close(fig)


def figure_c(plt, al_summary):
    fig, ax = plt.subplots(figsize=(9.0, 5.0))
    palette = {"random": "#4a5568", "diversity": "#2b6cb0", "uncertainty": "#2f855a", "ranking_aware": "#b7791f"}
    for kind in al_summary["kinds"]:
        curve = al_summary["curves"][kind]
        ax.plot(range(1, len(curve) + 1), curve, lw=1.8, color=palette.get(kind, "#333333"),
                label=str(kind) + " (n_T = " + fmt(al_summary["n_T_median"][kind], 0) + ")")
    ax.axhline(0.80, color="#c53030", ls="--", lw=1.2)
    ax.set_xlabel("\u63ed\u793a\u7684\u6602\u8d35\u6807\u7b7e\u6570\u91cf k")
    ax.set_ylabel("\u4e2d\u4f4d tau_b")
    ax.set_title("\u6700\u5c0f\u6602\u8d35\u6807\u7b7e\u9884\u7b97\uff1a\u56db\u79cd\u91c7\u96c6\u51fd\u6570\u7684\u6062\u590d\u66f2\u7ebf\uff08\u6c60 = " + str(al_summary["n_pool"]) + "\uff09")
    ax.legend(fontsize=8.5)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_C, dpi=160)
    plt.close(fig)


def paired_bootstrap_ci(a, b, seed, draws=5000):
    rng = random.Random(seed)
    n = len(a)
    stats = []
    for _ in range(draws):
        idx = [rng.randrange(n) for _ in range(n)]
        stats.append(float(np.mean([a[i] - b[i] for i in idx])))
    stats.sort()
    return float(stats[int(0.025 * draws)]), float(stats[int(0.975 * draws)]), float(np.mean(stats))


def render_report(summary):
    lines = []
    lines.append("# W25 \u7ed3\u9898\u62a5\u544a\uff1a\u6bcd\u4f53\u8bba\u6587 v6 \u53d1\u5c55\u65b9\u5411\u7684\u672c\u4ed3\u5bf9\u7167")
    lines.append("")
    lines.append("- **\u6027\u8d28**\uff1a\u96f6 QC \u53ea\u8bfb\u5bf9\u7167\uff08W25-1 \u81f3 W25-4\uff09\uff1b\u4e0d\u65b0\u589e\u7535\u5b50\u7ed3\u6784\u8ba1\u7b97\uff0c\u4e0d\u5360\u4e3b\u8bb0\u5206\u724c shot\uff08\u7d2f\u8ba1\u4ecd 12\uff09\u3002")
    lines.append("- **\u9884\u6ce8\u518c**\uff1a`" + str(summary["prereg_sha256"]) + "`\uff0cstatus = locked_before_run\u3002")
    lines.append("- **\u5bf9\u7167\u5bf9\u8c61**\uff1a\u6bcd\u4f53\u8bba\u6587 v6\uff08r2SCAN-3c / 18 \u5206\u5b50 / 10 \u53f0\u9636\uff09\u3002")
    lines.append("")
    lines.append("## 0. \u4e00\u53e5\u8bdd")
    lines.append("")
    lines.append(summary["headline"])
    lines.append("")
    lines.append("## 1. W25-1\uff1a\u4f4d\u79fb\u79bb\u6563\u5ea6\u5224\u636e\u7684\u5b8c\u6574\u7248\u68c0\u9a8c\uff08" + str(summary["dispersion"][0]["n_rungs"]) + " \u53f0\u9636-\u8f74\uff09")
    lines.append("")
    lines.append("| \u53f0\u9636\u96c6 | n | rho(std, tau_b) | 95% CI | rho(abs(mean), tau_b) | rho(std, f_unres) | \u7559\u4e00\u53f0\u9636\u51fa MAE | \u65b9\u5411\u547d\u4e2d |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for block in summary["dispersion"]:
        ci = block["ci_std_tau"]
        lines.append("| " + block["label"] + " | " + str(block["n_rungs"]) + " | " + fmt(block["rho_std_tau"], 4) +
                     " | [" + fmt(ci[0], 3) + ", " + fmt(ci[1], 3) + "] | " + fmt(block["rho_absmean_tau"], 4) +
                     " | " + fmt(block["rho_std_funres"], 4) + " | " + fmt(block["lvr_mae"], 3) + " | " +
                     str(block["lvr_direction_hits"]) + "/" + str(block["lvr_direction_total"]) + " |")
    lines.append("")
    lines.append("v6 \u5728 10 \u4e2a\u53f0\u9636\u4e0a\u62a5 -0.8511 / -0.5350 / +0.8936\uff1b\u672c\u4ed3\u5728 38 \u4e2a\u53f0\u9636-\u8f74\u4e0a\u62a5 " +
                 fmt(summary["dispersion"][0]["rho_std_tau"], 4) + " / " + fmt(summary["dispersion"][0]["rho_absmean_tau"], 4) + " / " +
                 fmt(summary["dispersion"][0]["rho_std_funres"], 4) + "\u3002\u65b9\u5411\u4e00\u81f4\uff1b\u4e0b\u9762\u9010\u6761\u8bfb\u3002")
    lines.append("")
    lines.append("![\u56fe A\u3000\u4f4d\u79fb\u79bb\u6563\u5ea6\u5224\u636e\uff1a38 \u4e2a\u53f0\u9636-\u8f74\u4e0a\u7684 std vs tau_b\uff0c\u4ee5\u53ca\u4e09\u4e2a\u76f8\u5173\u7cfb\u6570\u7684 bootstrap \u533a\u95f4\uff08\u672c\u4ed3 vs v6\uff09\u3002](probes/artifacts/w25_dispersion_criterion.png)")
    lines.append("")
    lines.append("## 2. W25-2\uff1af_robust_inv \u7684\u77db\u76fe\u5f52\u56e0")
    lines.append("")
    lines.append("- \u672c\u4ed3\u975e\u96f6\u53f0\u9636-\u8f74\uff1a**" + str(summary["robust"]["n_nonzero"]) + " / " + str(summary["robust"]["n_rungs"]) + "**\uff1b\u6700\u5927 f_robust_inversion = **" + fmt(summary["robust"]["frobust_max"], 4) + "**\uff0c\u5747\u503c " + fmt(summary["robust"]["frobust_mean"], 4) + "\u3002")
    lines.append("- rho(f_robust, f_unresolved) = **" + fmt(summary["robust"]["rho_frobust_funres"], 4) + "**\uff0c95% CI [" + fmt(summary["robust"]["ci_frobust_funres"][0], 3) + ", " + fmt(summary["robust"]["ci_frobust_funres"][1], 3) + "]\u3002")
    lines.append("- \u975e\u96f6\u53f0\u9636-\u8f74\u4e2d f_unresolved \u7684\u6700\u5c0f\u503c\u4e3a " + fmt(summary["robust"]["funres_of_nonzero_min"], 4) + "\u3002")
    lines.append("- \u5206\u5c42\uff1a" + ", ".join([k + " x" + str(v) for k, v in sorted(summary["robust"]["strata"].items())]) + "\u3002")
    lines.append("")
    lines.append("![\u56fe B\u3000\u7a33\u5065\u7ffb\u8f6c\u4e0e\u672a\u89e3\u6790\u5360\u6bd4\u7684\u5173\u7cfb\uff0c\u4ee5\u53ca\u7a33\u5065\u7ffb\u8f6c\u6700\u9ad8\u7684\u53f0\u9636-\u8f74\u3002](probes/artifacts/w25_robust_inversion.png)")
    lines.append("")
    lines.append("## 3. W25-3\uff1a\u6700\u5c0f\u6602\u8d35\u6807\u7b7e\u9884\u7b97\uff08" + str(summary["al"]["n_pool"]) + " \u6c60\uff0c\u56de\u6eaf\u91cd\u653e\uff09")
    lines.append("")
    lines.append("- \u76ee\u6807\u91cf\uff1a`delta_homo_eV`\uff08C0\u2192C1 \u6c27\u5316\u8f74\u6761\u4ef6\u4f4d\u79fb\uff09\uff1b\u7279\u5f81\uff1a" + ", ".join(summary["al"]["features"]) + "\uff08\u672c\u4ed3 X0 \u4ee3\u7406\uff09\u3002")
    lines.append("- \u4ee3\u7406\u6a21\u578b\uff1aKRR\uff08RBF\uff0calpha \u7531\u5df2\u63ed\u793a\u96c6\u7684 LOO \u9009\u62e9\uff09\uff1b\u521d\u59cb\u6807\u7b7e 4\uff0c\u6bcf\u8f6e\u63ed\u793a 1 \u4e2a\uff0c\u4e0a\u9650 " + str(summary["al"]["max_steps"]) + " \u6b65\u3002")
    lines.append("- \u6062\u590d\u5224\u636e\uff1a\u4e2d\u4f4d tau_b \u9996\u6b21 >= 0.80 \u6240\u9700\u6807\u7b7e\u6570 n_T\u3002")
    lines.append("- 池：" + str(summary["al"]["n_pool"]) + " 行（冻结 246 化合物名册里 X0 代理特征与目标量齐全者；不齐的行在入池前剔除，标签未删）。")
    lines.append("")
    lines.append("| \u91c7\u96c6\u51fd\u6570 | n_T\uff08\u4e2d\u4f4d\uff09 | \u9010\u79cd\u5b50 n_T |")
    lines.append("| --- | --- | --- |")
    for kind in summary["al"]["kinds"]:
        lines.append("| " + str(kind) + " | " + fmt(summary["al"]["n_T_median"][kind], 0) + " | " + str(summary["al"]["n_T_per_seed"][kind]) + " |")
    lines.append("")
    lines.append("![\u56fe C\u3000\u6700\u5c0f\u6602\u8d35\u6807\u7b7e\u9884\u7b97\uff1a\u56db\u79cd\u91c7\u96c6\u51fd\u6570\u5728 " + str(summary["al"]["n_pool"]) + " \u6c60\u4e0a\u7684\u4e2d\u4f4d\u6062\u590d\u66f2\u7ebf\u3002](probes/artifacts/w25_al_budget.png)")
    lines.append("")
    lines.append("## 4. W25-4\uff1a\u5206\u652f\u8ba4\u9886 A\u2013G \u7684\u672c\u4ed3\u5bf9\u7167")
    lines.append("")
    lines.append("| \u5206\u652f | \u5224\u636e | v6 \u5224\u51b3 | \u672c\u4ed3\u5224\u51b3 |")
    lines.append("| --- | --- | --- | --- |")
    for row in summary["branches"]:
        lines.append("| " + str(row[0]) + " | " + str(row[1]) + " | " + str(row[2]) + " | **" + str(row[5]) + "** |")
    lines.append("")
    lines.append("\u4e0e v6 \u5224\u51b3\u4e0d\u540c\u7684\u5206\u652f\uff1a**" + (", ".join(summary["branches_differing"]) if summary["branches_differing"] else "\u65e0") + "**\u3002")
    lines.append("")
    lines.append("## 5. \u5224\u636e\u88c1\u51b3")
    lines.append("")
    lines.append("| \u7f16\u53f7 | \u5224\u636e | \u5b9e\u6d4b | \u88c1\u51b3 |")
    lines.append("| --- | --- | --- | --- |")
    for item in summary["verdicts"]:
        lines.append("| " + item["id"] + " | " + item["criterion"] + " | " + item["reading"] + " | **" + item["verdict"] + "** |")
    lines.append("")
    lines.append("## 6. \u53e3\u5f84\u4e0e\u9650\u5236\uff08\u5fc5\u987b\u4e0e\u6570\u5b57\u540c\u53e5\u5f15\u7528\uff09")
    lines.append("")
    for item in summary["limits"]:
        lines.append("- " + item)
    lines.append("")
    lines.append("## 7. \u4ea7\u7269\u6e05\u5355")
    lines.append("")
    lines.append("| \u6587\u4ef6 | \u5185\u5bb9 |")
    lines.append("| --- | --- |")
    for row in summary["artifacts"]:
        lines.append("| `" + row[0] + "` | " + row[1] + " |")
    lines.append("")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with io.open(REPORT, "w", encoding="utf-8", newline="") as handle:
        handle.write("\n".join(lines))
    return lines


def main():
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("status") != "locked_before_run":
        raise SystemExit("pre-registration is not locked_before_run")
    prereg_sha = sha256_file(PREREG)
    draws = int(prereg["arms"]["W25-1"]["bootstrap_draws"])
    seed = int(prereg["arms"]["W25-1"]["seed"])
    rungs = load_rungs()
    print("[w25] rungs loaded: " + str(len(rungs)), flush=True)
    blocks = []
    blocks.append(dispersion_block(rungs, draws, seed, "\u5408\u5e76\uff08W24-1 + W24-2\uff09", "38 rungs, two levels"))
    blocks.append(dispersion_block([r for r in rungs if r["pool"].startswith("N=246")], draws, seed + 11, "\u4ec5 W24-1\uff08N=246\uff09", "28 rungs at the semi-empirical level"))
    blocks.append(dispersion_block([r for r in rungs if r["pool"].startswith("N=28")], 4000, seed + 22, "\u4ec5 W24-2\uff08N=28\uff09", "10 rungs at r2SCAN-3c"))
    prior = [(row["quantity"], row["value"]) for row in read_rows(ART / "w24_displacement_law.csv")]
    write_dispersion_csv(blocks, prior)
    print("[w25] W25-1 dispersion blocks written", flush=True)
    robust = robust_block(rungs, draws, seed + 33)
    print("[w25] W25-2 robust attribution written", flush=True)
    pool_x, pool_y, pool_keys = load_al_pool()
    sd = pool_x.std(0)
    pool_z = (pool_x - pool_x.mean(0)) / np.where(sd <= 0.0, 1.0, sd)
    learn = learnability(pool_x, pool_y)
    print("[w25] learnability n=" + str(learn["n"]) + " r2_loo=" + fmt(learn["r2_loo"], 4), flush=True)
    al_summary, curves = al_block(pool_x, pool_y, pool_z, prereg, seed + 100)
    print("[w25] W25-3 active-learning replay done", flush=True)
    al_summary["features"] = list(AL_FEATURES)
    al_summary["target"] = "delta_homo_eV (C0->C1 oxidation-axis shift)"
    al_summary["max_steps"] = int(prereg["arms"]["W25-3"]["max_steps"])
    al_summary["n_pool"] = int(pool_y.size)
    al_summary["learnability"] = learn
    branch_rows, differing = build_branch_claims(blocks[0], robust, al_summary, learn)
    print("[w25] W25-4 branch claims done", flush=True)
    plt = configure_fonts()
    figure_a(plt, blocks, rungs)
    figure_b(plt, robust)
    figure_c(plt, al_summary)
    n_t = {kind: al_summary["n_T_median"][kind] for kind in al_summary["kinds"]}
    best_alt = min(k for k in ("uncertainty", "diversity") if k in n_t)
    alt_key = "uncertainty" if n_t.get("uncertainty", 1e9) <= n_t.get("diversity", 1e9) else "diversity"
    lo, hi, mean_delta = paired_bootstrap_ci(al_summary["n_T_per_seed"]["random"], al_summary["n_T_per_seed"][alt_key], seed + 7)
    verdicts = []
    verdicts.append({"id": "H1a", "criterion": "rho(std, tau_b) <= -0.70", "reading": fmt(blocks[0]["rho_std_tau"], 4), "verdict": "\u6210\u7acb" if blocks[0]["rho_std_tau"] <= -0.70 else "\u5224\u5426"})
    verdicts.append({"id": "H1b", "criterion": "|rho(std, tau_b)| >= |rho(|mean|, tau_b)|", "reading": fmt(blocks[0]["rho_std_tau"], 4) + " vs " + fmt(blocks[0]["rho_absmean_tau"], 4), "verdict": "\u6210\u7acb" if abs(blocks[0]["rho_std_tau"]) >= abs(blocks[0]["rho_absmean_tau"]) else "\u5224\u5426"})
    verdicts.append({"id": "H1c", "criterion": "leave-one-rung-out direction hits >= 8", "reading": str(blocks[0]["lvr_direction_hits"]) + "/" + str(blocks[0]["lvr_direction_total"]), "verdict": "\u6210\u7acb" if blocks[0]["lvr_direction_hits"] >= 8 else "\u5224\u5426"})
    # The pre-registered H2 is evaluated first, exactly as locked: every nonzero
    # robust inversion must sit on a C rung or carry f_unresolved >= the gate.
    gate = float(prereg["arms"]["W25-2"]["criteria"]["funresolved_gate"])
    nonzero_rungs = [rung for rung in rungs if (rung["frobust"] or 0.0) > 0.0]
    violators = [rung for rung in nonzero_rungs
                 if not (rung["rung"].startswith("C") or (rung["funres"] or 0.0) >= gate)]
    h2 = not violators
    verdicts.append({"id": "H2", "criterion": "every nonzero f_robust_inversion is a C rung or has f_unresolved >= " + fmt(gate, 2),
                     "reading": str(len(nonzero_rungs) - len(violators)) + "/" + str(len(nonzero_rungs))
                                + " satisfy the gate; " + str(len(violators)) + " violate it (worst f_unresolved among violators = "
                                + fmt(max([(rung["funres"] or 0.0) for rung in violators], default=0.0), 3) + ")",
                     "verdict": "\u6210\u7acb" if h2 else "\u5224\u5426"})
    h2a = robust["rho_frobust_funres"] >= 0.30 and robust["ci_frobust_funres"][0] > 0.0
    verdicts.append({"id": "H2a", "criterion": "rho(f_robust, f_unresolved) >= 0.30 with CI excluding 0", "reading": fmt(robust["rho_frobust_funres"], 4) + " [" + fmt(robust["ci_frobust_funres"][0], 3) + ", " + fmt(robust["ci_frobust_funres"][1], 3) + "]", "verdict": "\u6210\u7acb" if h2a else "\u5224\u5426"})
    h2b = robust["frobust_max"] <= 0.20
    verdicts.append({"id": "H2b", "criterion": "max f_robust_inversion <= 0.20", "reading": fmt(robust["frobust_max"], 4), "verdict": "\u6210\u7acb" if h2b else "\u5224\u5426"})
    h3a = n_t["random"] >= float(prereg["arms"]["W25-3"]["criteria"]["H3a_random_nT_min"])
    verdicts.append({"id": "H3a", "criterion": "random n_T >= 60", "reading": fmt(n_t["random"], 0), "verdict": "\u6210\u7acb" if h3a else "\u5224\u5426"})
    h3b = (n_t[alt_key] < n_t["random"]) and (hi < 0.0)
    verdicts.append({"id": "H3b", "criterion": "uncertainty or diversity beats random (paired CI excludes 0)", "reading": alt_key + " n_T = " + fmt(n_t[alt_key], 0) + ", delta(random - alt) = " + fmt(mean_delta, 2) + " [" + fmt(lo, 2) + ", " + fmt(hi, 2) + "]", "verdict": "\u6210\u7acb" if h3b else "\u5224\u5426"})
    h3c = n_t["ranking_aware"] >= n_t["random"]
    verdicts.append({"id": "H3c", "criterion": "ranking-aware not better than random", "reading": "n_T = " + fmt(n_t["ranking_aware"], 0) + " vs random " + fmt(n_t["random"], 0), "verdict": "\u6210\u7acb" if h3c else "\u5224\u5426"})
    verdicts.append({"id": "H4", "criterion": "at least one branch verdict differs from v6", "reading": str(len(differing)) + " differing: " + (", ".join(differing) if differing else "none"), "verdict": "\u6210\u7acb" if differing else "\u5224\u5426"})
    headline = ("v6 \u7684\u516d\u6761\u65b9\u5411\u91cc\uff0c\u2482\u2483\u2474 \u672c\u4ed3\u65e9\u5df2\u5b9e\u73b0\u4e14\u89c4\u6a21\u66f4\u5927\uff1b\u672c\u8f6e\u628a\u5dee\u8ddd\u6700\u5927\u7684\u56db\u6761\u8865\u9f50\u540e\uff0c\u6700\u786c\u7684\u4e00\u6761\u53cd\u8bfb\u662f\uff1a"
               "v6 \u62a5\u300c\u7a33\u5065\u7ffb\u8f6c\u5168 0\u300d\uff08\u5206\u652f C \u672a\u89c2\u6d4b\uff09\uff0c\u800c\u672c\u4ed3\u5728 " + str(robust["n_nonzero"]) + " / " + str(robust["n_rungs"]) + " \u4e2a\u53f0\u9636-\u8f74\u4e0a\u770b\u5230\u975e\u96f6\uff08\u6700\u5927 " + fmt(robust["frobust_max"], 3) + "\uff09\uff0c"
               "\u4e14\u5b83\u4e0e\u672a\u89e3\u6790\u5360\u6bd4\u540c\u6b65\uff08rho = " + fmt(robust["rho_frobust_funres"], 3) + "\uff09\uff1b\u540c\u65f6\u672c\u4ed3\u5728 246 \u5206\u5b50\u4e0a\u628a v6 \u7684\u300c11/12 \u94dd\u4e2d\u5fc3\u8fd8\u539f\u300d\u964d\u5230 0.34/0.26\uff0c\u8bf4\u660e\u90a3\u4e00\u6761\u4e5f\u5e26\u5c0f\u6837\u672c\u6210\u5206\u3002"
               "追因后这条「矛盾」不是物理分歧，而是**同名不同阈**：本仓用绝对 0.05 eV 分辨分子对，v6 的 frobustinv(z) 用随 σ 缩放的阈值，后者让位移离散度大的台阶整轴自动落入 unresolved，「已分辨却翻转」的窗口按构造为空；同一轮还给出另一条只在大池上成立的读数——位移离散度判据在 N=246 上是 -0.8095，在 N=28 上坍缩到 -0.2037（bootstrap 区间跨 0）。")
    artifacts = [
        ["probes/w25_v6_alignment.py", "\u672c\u63a2\u9488\uff08\u53ea\u8bfb\uff09"],
        ["probes/w25_v6_alignment_prereg.json", "\u8dd1\u524d\u51bb\u7ed3\u7684\u9884\u6ce8\u518c"],
        ["probes/artifacts/w25_dispersion_criterion.csv", "W25-1 \u7684 rho / CI / \u7559\u4e00\u53f0\u9636\u51fa\u8bfb\u6570"],
        ["probes/artifacts/w25_robust_inversion_attribution.csv", "W25-2 \u7684\u9010\u53f0\u9636\u7a33\u5065\u7ffb\u8f6c\u5f52\u56e0"],
        ["probes/artifacts/w25_al_budget.csv", "W25-3 \u7684\u9010\u6b65\u6062\u590d\u66f2\u7ebf"],
        ["probes/artifacts/w25_branch_claims.csv", "W25-4 \u7684 A\u2013G \u5206\u652f\u8ba4\u9886"],
        ["probes/artifacts/w25_dispersion_criterion.png", "\u56fe A"],
        ["probes/artifacts/w25_robust_inversion.png", "\u56fe B"],
        ["probes/artifacts/w25_al_budget.png", "\u56fe C"]
    ]
    limits = [
        "W25-1 \u7684 38 \u4e2a\u53f0\u9636-\u8f74\u4e0d\u72ec\u7acb\uff08\u540c\u4e00\u53f0\u9636\u4e24\u6761\u8f74\u5171\u4eab\u5206\u5b50\uff0c\u4e14\u4e24\u4e2a\u6c60\u7684\u6c34\u5e73\u4e0d\u540c\uff09\uff0c\u6240\u4ee5 bootstrap \u533a\u95f4\u53ea\u80fd\u8bfb\u4f5c\u300c\u540c\u4e00\u5173\u7cfb\u7684\u7a33\u5065\u6027\u300d\uff0c\u4e0d\u80fd\u8bfb\u4f5c\u663e\u8457\u6027\u68c0\u9a8c\u3002",
        "v6 \u7684 -0.8511 / -0.5350 / +0.8936 \u662f 10 \u4e2a\u53f0\u9636\u7684\u8bfb\u6570\uff0c\u4e0e\u672c\u4ed3 38 \u4e2a\u53f0\u9636-\u8f74\u7684\u8bfb\u6570\u53ea\u80fd\u6bd4\u65b9\u5411\u4e0e\u91cf\u7ea7\uff0c\u4e0d\u80fd\u6bd4\u5927\u5c0f\u3002",
        "W25-3 \u7684 X0 \u7279\u5f81\u662f\u672c\u4ed3\u53e3\u5f84\u4e0b\u7684\u4ee3\u7406\uff08\u5ec9\u4ef7\u5c42\u7684\u81ea\u7531\u5206\u5b50\u6807\u91cf\uff09\uff0c\u4e0e v6 \u7684 12 \u9879 X0 \u4e0d\u540c\u540d\u540c\u5b9a\u4e49\uff1b\u6c60\u4e5f\u4ece 18 \u653e\u5230 237\uff08246 \u540d\u518c\u91cc 5 \u9879\u4ee3\u7406\u7279\u5f81\u4e0e\u76ee\u6807\u91cf\u9f50\u5168\u7684\u884c\uff09\uff0c\u56e0\u6b64 n_T \u53ea\u80fd\u8bfb\u4f5c\u300c\u672c\u6c60\u3001\u672c\u7279\u5f81\u96c6\u300d\u4e0b\u7684\u9884\u7b97\u3002",
        "\u5404\u91c7\u96c6\u51fd\u6570\u53ea\u6709 10 \u79cd\u5b50\uff0c\u914d\u5bf9 bootstrap \u533a\u95f4\u7684\u529f\u6548\u6709\u9650\uff1b\u4e0d\u5f97\u5199\u6210\u300c\u67d0\u91c7\u96c6\u51fd\u6570\u663e\u8457\u66f4\u4f18\u300d\u3002",
        "\u672c\u8f6e\u4e0d\u65b0\u589e\u7535\u5b50\u7ed3\u6784\u8ba1\u7b97\uff0c\u56e0\u6b64 W25-2 \u7684\u5f52\u56e0\u662f\u300c\u53e3\u5f84 + \u529f\u6548\u300d\u5c42\u9762\u7684\uff0c\u4e0d\u662f\u5bf9 v6 \u0394SCF \u5b9e\u73b0\u7684\u590d\u6838\u3002",
        "\u56fe 12 \u4ee5\u540e\u7684\u4e00\u5207\u8bfb\u6570\u4e0d\u5f97\u4e0e\u6bcd\u4f53\u8bba\u6587\u7684\u7edd\u5bf9\u503c\u76f8\u9664\u6216\u76f8\u52a0\u3002",
        "W25-3 在 120 步上限处右删失（budget_censored_at = 121）：四种采集函数的中位 n_T 全为 121，10 种子无一达标。因此 H3a（random n_T >= 60）与 H3c（ranking-aware 不比 random 好）是删失状态下自动成立的空判据，不携带信息；本轮只有 H3b 是真判据，且判否。",
        "W25-1 最值钱的一读不是 38 个台阶上的 ρ 本身，而是它对池规模的依赖：同一条判据在 N=246 子集上给出 ρ(std, tau_b) = -0.8095（bootstrap CI 上界 < 0），在 N=28 子集上给出 -0.2037（CI [-0.849, 0.628]，跨 0）。也就是说「位移离散度而非位移幅值决定排序损失」是一个大池性质，在 28 个化合物上不可复现；母体论文的 10 台阶读数属小池读数，与它同句引用时必须声明池规模。",
        "W25-2 的对比是同名不同阈：本仓 f_robust_inversion 用绝对分辨阈（源侧位移差与对间差都 >= 0.05 eV 才算已分辨），母体论文的 frobustinv(z) 用随 σ 缩放的阈（已分辨等价于 gap >= z·σij，σij = |δi − δj| / sqrt(2)）。在后者口径下，位移离散度大的台阶几乎整轴自动落入 unresolved，「已分辨却仍然翻转」的窗口按构造为空，因而那 40 个读数全为 0；本仓的绝对阈让同一窗口在 38 个台阶上处处非空。两者不是同口径读数，只能读作「零稳健翻转是阈值约定的产物」，不能读作母体论文的结论被推翻。母体论文自己给出的敏感性（改用 σij² = (δi² + δj²)/2 时 unresolved 升到 0.95-1.00）与这条同向。",
        "W25-2 的预注册判据 H2（非零翻转须全部落在 C 台阶或 f_unresolved >= 0.30）判否：38 个非零翻转里有 10 个不满足该门（其中最小 f_unresolved 低至 0.262），所以「本仓的非零来自条件态台阶」这个机制假设不成立。成立的只有 H2a：f_robust 与 f_unresolved 同源（ρ = 0.9361，CI [0.856, 0.967]）。"
    ]
    summary = {"task": "w25_v6_alignment", "prereg_sha256": prereg_sha, "headline": headline,
               "scoreboard_shots": SCOREBOARD_SHOTS_THIS_WEEK,
               "cumulative_scoreboard_attempts": CUMULATIVE_SCOREBOARD_ATTEMPTS,
               "dispersion": blocks, "robust": robust, "al": al_summary,
               "learnability": learn, "branches": branch_rows, "branches_differing": differing,
               "verdicts": verdicts, "limits": limits, "artifacts": artifacts, "n_rungs": len(rungs)}
    render_report(summary)
    out = {key: summary[key] for key in ("task", "prereg_sha256", "headline", "n_rungs", "verdicts", "branches_differing",
                                        "scoreboard_shots", "cumulative_scoreboard_attempts")}
    out["dispersion_rho"] = {block["label"]: [block["rho_std_tau"], block["rho_absmean_tau"], block["rho_std_funres"]] for block in blocks}
    out["robust"] = {"n_nonzero": robust["n_nonzero"], "frobust_max": robust["frobust_max"],
                      "rho_frobust_funres": robust["rho_frobust_funres"],
                      "prereg_h2_violators": len(violators),
                      "prereg_h2_violator_rungs": [rung["rung"] + "/" + rung["axis"] for rung in violators]}
    out["al"] = {"n_pool": al_summary["n_pool"], "n_T_median": al_summary["n_T_median"], "learnability": learn}
    out["artifacts_sha256"] = {str(path.relative_to(ROOT)): sha256_file(path) for path in (DISP_CSV, ROBUST_CSV, AL_CSV, BRANCH_CSV, FIG_A, FIG_B, FIG_C, REPORT) if path.exists()}
    SUMMARY.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
    print(json.dumps({"prereg_sha256": prereg_sha, "n_rungs": len(rungs), "n_nonzero_robust": robust["n_nonzero"],
                      "n_T_median": al_summary["n_T_median"], "verdicts": [(v["id"], v["verdict"]) for v in verdicts]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
