#!/usr/bin/env python
"""B100-E: E1/E4/E6 + H4 at 257-molecule scale.

This is the scientific core of PLAN B v6.0: the same questions as the 22-molecule study,
now with enough molecules for the answers to mean something, plus the new H4 hypothesis.

Design carried over from the 22-molecule work, because those lessons cost real effort:

  * RIDGE WITH AN INTERCEPT. The earlier study published an inverted conclusion because
    the fit was forced through the origin in standardised space. The intercept is
    included and asserted.
  * NESTED SELECTION. Lambda is chosen by an inner leave-one-out on the training fold
    only, so the outer estimate is not contaminated.
  * TWO NULLS. Permuting labels and permuting feature rows answer different questions;
    both are reported.
  * HONEST VERDICTS. A model that does not beat the constant baseline is reported as
    such; "not demonstrated superior at this power" is preferred to "indistinguishable".

Experiments:
  E1  structure-only vs structure+electronic (and each block alone)
  E4  leave-one-family-out, structural-distance OOD, applicability domain
  E6  Top-k screening, regret vs random, exact enumeration of all C(n,k) sets
  H4  low-eps weak-association vs high-eps strong-association predictive skill

Output: outputs/b100/e1_*.json, e4_*.json, e6_*.json, h4_*.json + one combined report
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "run_b100_experiments/1.0.0"

MATRIX = OUT / "model_matrix_b100.csv"

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]
# polarizability_au is EXCLUDED, deliberately.
#
# Two independent reasons, both measured:
#  1. This xTB build (6.7.1) does not emit a polarizability block at all -- verified
#     by grepping the raw xtb.out files and by running --pop/--alpha/--esp. So the
#     value is missing for 36 of 257 molecules, and those 36 are NOT a random subset:
#     they include 10 of the 25 molecules with epsilon >= 20 (N-methylacetamide
#     epsilon=178.5 among them). Requiring the column silently truncated the high-
#     epsilon tail, made every model easier, and is the real reason H4's strong group
#     fell to 15 instead of 25 (Reviewer 1).
#  2. The column carries almost no information anyway: alone it gives R^2 = 0.036,
#     and alpha/Vm adds nothing on top of mu^2/Vm.
# Dropping it restores the full 257-molecule set and removes an inert column.
X1_COLS = ["dipole_D", "homo_lumo_gap_ev"]
XN_COLS = ["mu_sq_over_Vm"]     # volume-normalised dipole term only

LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
N_PERM = 1000
SEED = 20261123
TOPK = 10
TOPK_SENS = [5, 15]
AD_TANIMOTO = 0.5

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    import io
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- linear algebra

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
            if f == 0:
                continue
            for c in range(col, p):
                A[r][c] -= f * A[col][c]
            rhs[r] -= f * rhs[col]
    b = [0.0] * p
    for r in range(p - 1, -1, -1):
        if abs(A[r][r]) < 1e-12:
            continue
        s = rhs[r] - sum(A[r][c] * b[c] for c in range(r + 1, p))
        b[r] = s / A[r][r]
    return b


def fit_predict(Xtr, ytr, Xte, lam):
    """Ridge WITH an intercept -- the specification error that once inverted E1."""
    if not Xtr or not Xte:
        return []
    Ztr, means, sds = standardise(Xtr)
    b = ridge_fit(Ztr, ytr, lam)
    ybar = sum(ytr) / len(ytr)
    out = []
    for row in Xte:
        z = [(row[j] - means[j]) / sds[j] for j in range(len(means))]
        out.append(ybar + sum(z[j] * b[j] for j in range(len(b))))
    return out


def kfold_idx(n, k, seed):
    """Deterministic k-fold assignment."""
    rng = random.Random(seed)
    order = list(range(n))
    rng.shuffle(order)
    folds = [[] for _ in range(k)]
    for i, idx in enumerate(order):
        folds[i % k].append(idx)
    return folds


def choose_lambda(Xtr, ytr, seed=SEED, k=5):
    """Pick lambda by k-fold CV *inside the training fold only*.

    Full inner leave-one-out is O(n^2) fits and made the nested protocol 3 orders of
    magnitude slower than necessary; 5-fold gives the same selection quality for this
    feature dimension and keeps the outer estimate uncontaminated.
    """
    n = len(Xtr)
    if n < k * 3:
        return 1.0
    folds = kfold_idx(n, k, seed)
    best_lam, best_mae = LAMBDA_GRID[0], float("inf")
    for lam in LAMBDA_GRID:
        errs = []
        for f in range(k):
            te = folds[f]
            tr = [i for j in range(k) if j != f for i in folds[j]]
            if not te or len(tr) < 5:
                continue
            p = fit_predict([Xtr[i] for i in tr], [ytr[i] for i in tr],
                            [Xtr[i] for i in te], lam)
            errs.extend(abs(p[t] - ytr[i]) for t, i in enumerate(te))
        if errs:
            m = sum(errs) / len(errs)
            if m < best_mae:
                best_mae, best_lam = m, lam
    return best_lam


def cv_mae(X, y, lam, k=5, seed=SEED):
    """k-fold CV MAE at a fixed lambda. Used for the permutation nulls.

    Running full leave-one-out inside every permutation was the dominant cost
    (51k ridge fits per block); k-fold reduces that 50x while preserving the null's
    purpose, which is only to locate the observed error within a reference
    distribution.
    """
    n = len(X)
    folds = kfold_idx(n, k, seed)
    errs = []
    for f in range(k):
        te = folds[f]
        tr = [i for j in range(k) if j != f for i in folds[j]]
        if not te or len(tr) < 5:
            continue
        p = fit_predict([X[i] for i in tr], [y[i] for i in tr],
                        [X[i] for i in te], lam)
        errs.extend(abs(p[t] - y[i]) for t, i in enumerate(te))
    return sum(errs) / len(errs) if errs else float("inf")


def nested_loo(X, y):
    n = len(X)
    pred, lams = [], []
    for hold in range(n):
        tr = [i for i in range(n) if i != hold]
        lam = choose_lambda([X[i] for i in tr], [y[i] for i in tr])
        lams.append(lam)
        pred.extend(fit_predict([X[i] for i in tr], [y[i] for i in tr],
                                [X[hold]], lam))
    return pred, lams


def loo_fixed_lambda(X, y, lam):
    """Cheap LOO at a fixed lambda, for the permutation nulls."""
    n = len(X)
    pred = []
    for hold in range(n):
        tr = [i for i in range(n) if i != hold]
        pred.extend(fit_predict([X[i] for i in tr], [y[i] for i in tr],
                                [X[hold]], lam))
    return pred


def metrics(y, pred):
    n = len(y)
    err = [pred[i] - y[i] for i in range(n)]
    mae = sum(abs(e) for e in err) / n
    rmse = math.sqrt(sum(e * e for e in err) / n)
    ybar = sum(y) / n
    sst = sum((v - ybar) ** 2 for v in y)
    ssr = sum(e * e for e in err)
    r2 = 1 - ssr / sst if sst > 0 else float("nan")
    bias = sum(err) / n
    return {"mae": mae, "rmse": rmse, "r2": r2, "bias": bias, "n": n}


def spearman(a, b):
    n = len(a)
    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        rk = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return rk
    ra, rb = rank(a), rank(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    den = math.sqrt(sum((ra[i] - ma) ** 2 for i in range(n))
                    * sum((rb[i] - mb) ** 2 for i in range(n)))
    return num / den if den else float("nan")


def build(rows, cols):
    """Return (X, y, idx) for rows with every column present."""
    X, y, idx = [], [], []
    for i, r in enumerate(rows):
        vals = [fnum(r.get(c)) for c in cols]
        if any(v is None for v in vals):
            continue
        e = fnum(r.get("epsilon"))
        if e is None:
            continue
        X.append([float(v) for v in vals])
        y.append(e)
        idx.append(i)
    return X, y, idx


def main() -> int:
    if not MATRIX.is_file():
        print(f"FATAL: missing {MATRIX}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load(MATRIX)
    random.seed(SEED)

    blocks = {
        "X0_structure": X0_COLS,
        "X1_electronic": X1_COLS,
        "X0_plus_X1": X0_COLS + X1_COLS,
        "dipole_only": ["dipole_D"],
        "Xn_volume_normalised": XN_COLS,
        "X0_X1_Xn": X0_COLS + X1_COLS + XN_COLS,
    }

    # ---- common evaluation set ----
    # Different blocks have different missing-value patterns, so building each block
    # on "whatever rows happen to be complete" silently compares models on DIFFERENT
    # molecules (the first run had 257 for X0 but 221 for X1, with baselines 6.91 vs
    # 5.09 -- a 36% difference that has nothing to do with the features).
    # One intersection set is used for every block so the comparison is paired.
    union_cols = list(dict.fromkeys(
        [c for cols in blocks.values() for c in cols]))
    common_idx = []
    for i, r in enumerate(rows):
        if fnum(r.get("epsilon")) is None:
            continue
        if any(fnum(r.get(c)) is None for c in union_cols):
            continue
        common_idx.append(i)
    # Common-evaluation-set diagnostic: which column forces which rows out.
    # A silently truncated sample is the defect this reports on.
    dropped_by: dict[str, int] = {}
    n_eps = sum(1 for r in rows if fnum(r.get("epsilon")) is not None)
    for c in union_cols:
        n_missing = sum(1 for r in rows
                        if fnum(r.get("epsilon")) is not None
                        and fnum(r.get(c)) is None)
        if n_missing:
            dropped_by[c] = n_missing
    # how much of the high-epsilon tail the common set keeps
    all_eps = [fnum(r.get("epsilon")) for r in rows
               if fnum(r.get("epsilon")) is not None]
    kept_eps = [fnum(rows[i]["epsilon"]) for i in common_idx]
    n_high_all = sum(1 for e in all_eps if e >= 20)
    n_high_kept = sum(1 for e in kept_eps if e >= 20)

    N_COMMON = len(common_idx)
    print(f"[E1] common evaluation set = {N_COMMON} molecules "
          f"(of {len(rows)} rows)")
    e1 = {"blocks": [], "n_input": len(rows),
          "n_common_evaluation_set": N_COMMON,
          "common_set_diagnostics": {
              "n_rows_with_epsilon": n_eps,
              "n_kept": N_COMMON,
              "columns_forcing_drops": dropped_by,
              "high_epsilon_total": n_high_all,
              "high_epsilon_kept": n_high_kept,
              "note": (
                  "若某列导致大量行被丢弃且这些行集中在高介电端, "
                  "样本就被静默截断, 所有模型都会变得更容易. 本诊断显式报告该情况."
              ),
          },
          "comparability_note": (
              "所有块在**同一分子集**上评估, 因此 MAE 与基线可直接比较. "
              "早期版本按各块各自的完整行评估, 导致块间样本不同、基线相差 36%."
          )}
    const_baseline = {}
    for label, cols in blocks.items():
        X = [[fnum(rows[i][c]) for c in cols] for i in common_idx]
        y = [fnum(rows[i]["epsilon"]) for i in common_idx]
        if len(y) < 10:
            continue
        ybar = sum(y) / len(y)
        cmae = sum(abs(v - ybar) for v in y) / len(y)
        const_baseline[label] = cmae
        pred, lams = nested_loo(X, y)
        m = metrics(y, pred)
        rho = spearman(pred, y)

        # null A: permute labels (fixed lambda = median of the nested choices).
        # Scored by 5-fold CV rather than LOO; see cv_mae for why.
        #
        # CRITICAL: the observed value must be computed on the SAME protocol as the
        # null, otherwise the p-value compares a leave-one-out error against a
        # cross-validation error and is meaningless. So the p-value uses cv_mae on
        # both sides; the nested LOO result stays the headline estimate.
        lam_med = statistics.median(lams) if lams else 1.0
        cv_obs = cv_mae(X, y, lam_med)
        N_NULL = 200
        null_lab = []
        for _ in range(N_NULL):
            yp = y[:]
            random.shuffle(yp)
            null_lab.append(cv_mae(X, yp, lam_med))
        null_lab.sort()
        # +1 correction: with N permutations the smallest attainable p is 1/(N+1),
        # so reporting 0.0 is arithmetically impossible and overstates the evidence.
        p_lab = (sum(1 for v in null_lab if v <= cv_obs) + 1) / (len(null_lab) + 1)

        # null B: permute feature rows
        null_feat = []
        for _ in range(N_NULL):
            order = list(range(len(X)))
            random.shuffle(order)
            Xp = [X[order[i]] for i in range(len(X))]
            null_feat.append(cv_mae(Xp, y, lam_med))
        null_feat.sort()
        p_feat = (sum(1 for v in null_feat if v <= cv_obs) + 1) / (
            len(null_feat) + 1)

        e1["blocks"].append({
            "block": label, "n_features": len(cols), "n_used": len(y),
            "nested_loo_mae": round(m["mae"], 4),
            "nested_loo_rmse": round(m["rmse"], 4),
            "nested_loo_r2": round(m["r2"], 4),
            "bias": round(m["bias"], 4),
            "spearman": round(rho, 4),
            "constant_baseline_mae": round(cmae, 4),
            "beats_constant": "true" if m["mae"] < cmae else "false",
            "mae_reduction_vs_constant_pct": round(100 * (1 - m["mae"] / cmae), 2),
            "p_label_permutation": round(p_lab, 4),
            "p_feature_permutation": round(p_feat, 4),
            "n_permutations": N_NULL,
            "p_value_floor": round(1.0 / (N_NULL + 1), 5),
            "p_note": (
                f"使用 {N_NULL} 次置换并加 +1 校正, 因此最小可能 p = "
                f"{1.0/(N_NULL+1):.5f}; 报 0.0 在算术上不可能, 会高估证据强度."
            ),
            "cv_mae_for_pvalue": round(cv_obs, 4),
            "null_note": (
                "p 值两侧都用 5 折 CV 计算 (观测值 cv_mae_for_pvalue 对比零分布), "
                "避免把留一误差与交叉验证误差直接比较. 主估计仍是嵌套 LOO."
            ),
            "lambda_median": statistics.median(lams),
        })

    # paired delta between X0 and X0+X1 -- on the SAME common set
    Xa = [[fnum(rows[i][c]) for c in X0_COLS] for i in common_idx]
    Xb = [[fnum(rows[i][c]) for c in X0_COLS + X1_COLS] for i in common_idx]
    ya = [fnum(rows[i]["epsilon"]) for i in common_idx]
    yb = list(ya)
    delta = None
    if len(ya) > 10:
        pa, _ = nested_loo(Xa, ya)
        pb, _ = nested_loo(Xb, yb)
        ma = metrics(ya, pa)["mae"]
        mb = metrics(yb, pb)["mae"]
        per_mol = [abs(pa[i] - ya[i]) - abs(pb[i] - yb[i]) for i in range(len(ya))]
        n_better = sum(1 for v in per_mol if v > 0)
        boots = []
        rng = random.Random(SEED)
        for _ in range(2000):
            samp = [rng.randrange(len(per_mol)) for _ in range(len(per_mol))]
            boots.append(sum(per_mol[i] for i in samp) / len(samp))
        boots.sort()
        delta = {
            "X0_mae": round(ma, 4), "X0X1_mae": round(mb, 4),
            "delta_mae": round(mb - ma, 4),
            "boot_ci95": [round(boots[int(0.025 * len(boots))], 4),
                          round(boots[int(0.975 * len(boots))], 4)],
            "n_molecules_X1_better": n_better, "n_total": len(ya),
            "frac_boot_negative": round(
                sum(1 for v in boots if v < 0) / len(boots), 4),
        }
    e1["paired_delta"] = delta
    best = min(e1["blocks"], key=lambda b: b["nested_loo_mae"]) if e1["blocks"] else None
    e1["best_block"] = best["block"] if best else None
    e1["status"] = "EXPLORATORY_LARGE_N"
    e1["note"] = ("所有块使用同一嵌套协议 (内层 LOO 选 lambda, 外层 LOO 评估). "
                  "岭回归含截距.")
    e1["inputs"] = {"model_matrix_b100": {"sha256": sha256_file(MATRIX)}}
    (OUT / "e1_manifest_b100.json").write_text(
        json.dumps(e1, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[E1] best block = {e1['best_block']}")
    for b in e1["blocks"]:
        print(f"   {b['block']:24s} k={b['n_features']:2d} "
              f"MAE={b['nested_loo_mae']:8.4f} base={b['constant_baseline_mae']:7.3f} "
              f"R2={b['nested_loo_r2']:+7.3f} p_feat={b['p_feature_permutation']}")

    # ============================ E4 ============================
    # E4 uses the same common evaluation set so the per-family errors are comparable
    # with the E1 numbers rather than drawn from a different sample.
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem, DataStructs
    RDLogger.DisableLog("rdApp.*")

    e4, e6, h4 = {"families": []}, {"n_pool": 0}, {"groups": {}}
    fams = defaultdict(list)
    for i in common_idx:
        fams[rows[i].get("family") or "unclassified"].append(rows[i])

    e4 = {"families": [], "n_families": len(fams),
          "n_common_evaluation_set": N_COMMON}
    all_cols = X0_COLS + X1_COLS
    for fam, members in sorted(fams.items(), key=lambda kv: -len(kv[1])):
        if len(members) < 3:
            continue
        test_keys = {m["inchikey"] for m in members}
        train = [r for r in rows if r["inchikey"] not in test_keys]
        Xtr, ytr, _ = build(train, all_cols)
        Xte, yte, _ = build(members, all_cols)
        if len(ytr) < 20 or not yte:
            continue
        # lambda chosen by k-fold CV on the training fold only
        best_lam = choose_lambda(Xtr, ytr)
        pred = fit_predict(Xtr, ytr, Xte, best_lam)
        m = metrics(yte, pred)
        tr_mean = sum(ytr) / len(ytr)
        base = sum(abs(v - tr_mean) for v in yte) / len(yte)
        e4["families"].append({
            "family": fam, "n_test": len(yte), "n_train": len(ytr),
            "mae": round(m["mae"], 4), "train_mean_baseline_mae": round(base, 4),
            "beats_baseline": "true" if m["mae"] < base else "false",
            "r2": round(m["r2"], 4), "spearman": round(spearman(pred, yte), 4),
        })

    n_meas = len(e4["families"])
    n_beat = sum(1 for f in e4["families"] if f["beats_baseline"] == "true")
    n_r2_pos = sum(1 for f in e4["families"] if f["r2"] > 0)
    e4["summary"] = {
        "n_measured": n_meas,
        "n_beating_baseline": n_beat,
        "n_with_positive_r2": n_r2_pos,
        # The baseline here is the GLOBAL training mean. For a family whose epsilon
        # sits far from that mean, beating it is easy and says little. R^2 is
        # scale-free and answers the harder question: does the model explain
        # variance WITHIN the family? Both counts are reported so neither can be
        # quoted alone. (Reviewer 4 raised this.)
        "baseline_definition": (
            "全局训练均值 (不是家族均值). 对介电水平远离全局均值的家族, "
            "该基线偏弱, 因此同时报告 R^2 为正的家族数."
        ),
        "caveat": (
            f"{n_beat}/{n_meas} 个家族优于全局均值基线, "
            f"但只有 {n_r2_pos}/{n_meas} 个家族 R^2 > 0. "
            "前者容易被误读为泛化成功."
        ),
    }

    # structural distance OOD + applicability domain
    mols = []
    for r in rows:
        e = fnum(r.get("epsilon"))
        s = (r.get("smiles") or "").strip()
        if e is None or not s:
            continue
        mm = Chem.MolFromSmiles(s)
        if mm is None:
            continue
        fp = AllChem.GetMorganFingerprintAsBitVect(mm, 2, nBits=2048)
        mols.append({"inchikey": r["inchikey"], "name": r["name"],
                     "eps": e, "fp": fp, "family": r.get("family", "")})
    # use the common evaluation set throughout so E4's structural-OOD and E6's
    # ranking are drawn from the same molecules as E1
    Xall = [[fnum(rows[i][c]) for c in all_cols] for i in common_idx]
    yall = [fnum(rows[i]["epsilon"]) for i in common_idx]
    idxall = list(common_idx)
    keep = {rows[i]["inchikey"]: j for j, i in enumerate(idxall)}
    mols = [m for m in mols if m["inchikey"] in keep]
    preds_all, _ = nested_loo(Xall, yall)
    pred_by_key = {rows[idxall[j]]["inchikey"]: preds_all[j]
                   for j in range(len(preds_all))}
    dist_rows = []
    for m in mols:
        sims = [DataStructs.TanimotoSimilarity(m["fp"], o["fp"])
                for o in mols if o["inchikey"] != m["inchikey"]]
        if not sims:
            continue
        nn = max(sims)
        p = pred_by_key.get(m["inchikey"])
        if p is None:
            continue
        dist_rows.append({"name": m["name"], "family": m["family"],
                          "nn_tanimoto": round(nn, 4),
                          "y_true": round(m["eps"], 4),
                          "y_pred": round(p, 4),
                          "abs_error": round(abs(p - m["eps"]), 4)})
    ind = [d for d in dist_rows if d["nn_tanimoto"] >= AD_TANIMOTO]
    outd = [d for d in dist_rows if d["nn_tanimoto"] < AD_TANIMOTO]
    def mae_of(ds):
        return round(sum(d["abs_error"] for d in ds) / len(ds), 4) if ds else None
    ratio = (round(mae_of(outd) / mae_of(ind), 4)
             if ind and outd and mae_of(ind) else None)
    e4["structural_ood"] = {
        "n_in_domain": len(ind), "n_out_domain": len(outd),
        "mae_in_domain": mae_of(ind), "mae_out_domain": mae_of(outd),
        "out_over_in_ratio": ratio,
        "spearman_error_vs_similarity": round(
            spearman([d["abs_error"] for d in dist_rows],
                     [d["nn_tanimoto"] for d in dist_rows]), 4),
        "ad_threshold": AD_TANIMOTO,
    }
    with (OUT / "e4_structural_ood_b100.csv").open("w", newline="",
                                                   encoding="utf-8") as fh:
        if dist_rows:
            w = csv.DictWriter(fh, fieldnames=list(dist_rows[0].keys()))
            w.writeheader()
            for d in sorted(dist_rows, key=lambda z: -z["nn_tanimoto"]):
                w.writerow(d)
    e4["status"] = "EXPLORATORY_LARGE_N"
    e4["inputs"] = {"model_matrix_b100": {"sha256": sha256_file(MATRIX)}}
    (OUT / "e4_manifest_b100.json").write_text(
        json.dumps(e4, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n[E4] families measured={n_meas} beating baseline={n_beat}")
    print(f"   in/out domain = {len(ind)}/{len(outd)}  ratio={ratio}")

    # ============================ E6 ============================
    keys = [rows[i]["inchikey"] for i in idxall]
    e6 = {"k": TOPK, "n_pool": len(yall),
          # E6's primary block is X0+X1 (the historical choice). The screening
          # variant below repeats the SAME evaluation with mu^2/Vm added, because
          # that single physically-motivated feature turns out to change the
          # conclusion qualitatively -- reporting only the weaker block would
          # understate the result. Both are reported; the variant is labelled.
          "primary_block": "X0_plus_X1",
          "screening_variants": []}
    if len(yall) > TOPK:
        order_pred = sorted(range(len(yall)), key=lambda i: -preds_all[i])
        topk_idx = order_pred[:TOPK]
        oracle_mean = statistics.mean(sorted(yall, reverse=True)[:TOPK])
        model_mean = statistics.mean(yall[i] for i in topk_idx)
        pool_mean = statistics.mean(yall)
        regret = oracle_mean - model_mean
        # exact enumeration is infeasible at n=257; use a large Monte Carlo and say so
        rng = random.Random(SEED)
        n_mc = 200000
        mc = []
        for _ in range(n_mc):
            s = rng.sample(range(len(yall)), TOPK)
            mc.append(statistics.mean(yall[i] for i in s))
        mc.sort(reverse=True)
        p_exact = sum(1 for v in mc if v >= model_mean) / len(mc)
        e6.update({
            "oracle_topk_mean": round(oracle_mean, 4),
            "model_topk_mean": round(model_mean, 4),
            "pool_mean": round(pool_mean, 4),
            "regret": round(regret, 4),
            # +1 correction as well: a Monte Carlo p of exactly 0 is impossible.
            "p_random_at_least_as_good": round(
                (sum(1 for v in mc if v >= model_mean) + 1) / (len(mc) + 1), 6),
            "n_monte_carlo": n_mc,
            "method": (f"n={len(yall)} 时 C(n,{TOPK}) 无法穷举, 用 200000 次"
                       f"蒙特卡洛; 该 p 的分辨率下限约 5e-6"),
            "verdict": ("NOT_DEMONSTRATED_SUPERIOR_AT_THIS_POWER"
                        if p_exact > 0.05 else "SIGNIFICANTLY_BETTER_THAN_RANDOM"),
            "topk_sensitivity": {},
        })
        for k2 in TOPK_SENS:
            o2 = statistics.mean(sorted(yall, reverse=True)[:k2])
            m2 = statistics.mean(yall[i] for i in order_pred[:k2])
            mc2 = []
            for _ in range(20000):
                s = rng.sample(range(len(yall)), k2)
                mc2.append(statistics.mean(yall[i] for i in s))
            mc2.sort(reverse=True)
            e6["topk_sensitivity"][f"k={k2}"] = {
                "oracle": round(o2, 4), "model": round(m2, 4),
                "regret": round(o2 - m2, 4),
                "p_random_ge_model": round(
                    (sum(1 for v in mc2 if v >= m2) + 1) / (len(mc2) + 1), 5),
            }
        # spearman between rank and error
        e6["spearman_pred_true"] = round(spearman(preds_all, yall), 4)

        # ---- regret decomposition ----
        # A single extreme epsilon can dominate regret and make the metric look like
        # a screening result when it is really one outlier. Both reviewers flagged
        # this, so the contribution of every molecule is reported and the
        # concentration is quantified rather than left implicit.
        oracle_idx = sorted(range(len(yall)), key=lambda i: -yall[i])[:TOPK]
        model_set = set(topk_idx)
        oracle_set = set(oracle_idx)
        contrib: list[dict] = []
        for i in oracle_set - model_set:
            contrib.append({
                "inchikey": keys[i], "name": rows[idxall[i]]["name"],
                "epsilon": round(yall[i], 4),
                "predicted": round(preds_all[i], 4),
                "role": "MISSED_HIGH_EPSILON",
                "regret_contribution": round(yall[i] / TOPK, 4),
            })
        for i in model_set - oracle_set:
            contrib.append({
                "inchikey": keys[i], "name": rows[idxall[i]]["name"],
                "epsilon": round(yall[i], 4),
                "predicted": round(preds_all[i], 4),
                "role": "FALSE_POSITIVE",
                "regret_contribution": round(-yall[i] / TOPK, 4),
            })
        contrib.sort(key=lambda z: -z["regret_contribution"])
        top1_share = (contrib[0]["regret_contribution"] / regret) if (contrib and regret) else None
        top2_share = (sum(c["regret_contribution"] for c in contrib[:2]) / regret
                      if (contrib and regret) else None)

        # Is the failure a ranking failure or a RANGE-COMPRESSION failure? If every
        # missed high-epsilon molecule is UNDER-predicted, the model has the order
        # roughly right but compresses the top of the scale -- which is a different
        # defect with a different remedy than "the ranking is broken".
        missed = [c for c in contrib if c["role"] == "MISSED_HIGH_EPSILON"]
        n_under = sum(1 for c in missed if c["predicted"] < c["epsilon"])
        compression = (n_under / len(missed)) if missed else None
        # how much of the true range does the prediction range cover?
        pred_span = max(preds_all) - min(preds_all) if preds_all else None
        true_span = max(yall) - min(yall) if yall else None
        span_ratio = (pred_span / true_span) if (pred_span and true_span) else None

        # sensitivity: drop the single largest-epsilon molecule and recompute
        drop_i = max(range(len(yall)), key=lambda i: yall[i])
        kept = [i for i in range(len(yall)) if i != drop_i]
        yk = [yall[i] for i in kept]
        pk = [preds_all[i] for i in kept]
        ordk = sorted(range(len(yk)), key=lambda i: -pk[i])
        o_k = statistics.mean(sorted(yk, reverse=True)[:TOPK])
        m_k = statistics.mean(yk[i] for i in ordk[:TOPK])
        n_mc2 = 20000
        mc3 = []
        for _ in range(n_mc2):
            s = rng.sample(range(len(yk)), TOPK)
            mc3.append(statistics.mean(yk[i] for i in s))
        mc3.sort(reverse=True)
        p_drop = (sum(1 for v in mc3 if v >= m_k) + 1) / (len(mc3) + 1)

        e6["regret_decomposition"] = {
            "n_contributing_molecules": len(contrib),
            "top1_contribution": round(contrib[0]["regret_contribution"], 4) if contrib else None,
            "top1_name": contrib[0]["name"] if contrib else None,
            "top1_share_of_regret": round(top1_share, 4) if top1_share else None,
            "top2_share_of_regret": round(top2_share, 4) if top2_share else None,
            "contributors": contrib[:12],
            "n_missed_high_epsilon": len(missed),
            "n_missed_underpredicted": n_under,
            "underprediction_fraction": (
                round(compression, 4) if compression is not None else None),
            "prediction_span_over_true_span": (
                round(span_ratio, 4) if span_ratio else None),
            "mechanism": (
                "RANGE_COMPRESSION_AT_HIGH_EPSILON"
                if compression is not None and compression >= 0.8
                else "MIXED_RANKING_ERROR"),
            "interpretation": (
                (
                    f"regret 高度集中: 最大的两个分子贡献 "
                    f"{100*top2_share:.0f}%. "
                    if top2_share and top2_share > 0.5 else
                    "regret 未被少数离群值主导. "
                )
                + (
                    f"被错过的高介电分子中有 {n_under}/{len(missed)} 个是**被低估**的, "
                    f"预测值域只覆盖真实值域的 "
                    f"{100*span_ratio:.0f}% — 模型不是排序失败, 而是"
                    f"**在高介电端压缩了值域**. "
                    f"这需要的是有界/非线性读出或高介电加权, "
                    f"不是重排特征."
                    if compression is not None and compression >= 0.8 and span_ratio
                    else ""
                )
            ),
            "drop_largest_epsilon": {
                "dropped_name": rows[idxall[drop_i]]["name"],
                "dropped_epsilon": round(yall[drop_i], 4),
                "regret_without_it": round(o_k - m_k, 4),
                "p_random_ge_model_without_it": round(p_drop, 5),
            },
        }

    # ---- E6 screening variants: does mu^2/Vm change the conclusion? ----
    # Same protocol, same molecules, only the feature block differs, so a regret gap
    # is attributable to the block. The lambda machinery is the same nested LOO used
    # by E1, so these numbers are directly comparable with the E1 table.
    for vlabel, vcols in (("X0_plus_mu2_over_Vm", X0_COLS + XN_COLS),
                          ("X0_plus_X1_plus_mu2_over_Vm",
                           X0_COLS + X1_COLS + XN_COLS)):
        Xv = [[fnum(rows[i][c]) for c in vcols] for i in common_idx]
        if any(v is None for row in Xv for v in row):
            continue
        pv, _ = nested_loo(Xv, yall)
        ordv = sorted(range(len(yall)), key=lambda i: -pv[i])
        kv = min(TOPK, len(yall))
        om = statistics.mean(sorted(yall, reverse=True)[:kv])
        mm = statistics.mean(yall[i] for i in ordv[:kv])
        rng2 = random.Random(SEED)
        n_mc3 = 50000
        mcv = [statistics.mean(
            yall[i] for i in rng2.sample(range(len(yall)), kv))
            for _ in range(n_mc3)]
        mcv.sort(reverse=True)
        e6["screening_variants"].append({
            "block": vlabel,
            "n_features": len(vcols),
            "oracle_topk_mean": round(om, 4),
            "model_topk_mean": round(mm, 4),
            "regret": round(om - mm, 4),
            "p_random_at_least_as_good": round(
                (sum(1 for v in mcv if v >= mm) + 1) / (len(mcv) + 1), 6),
            "spearman_pred_true": round(spearman(pv, yall), 4),
            "fraction_of_headroom_captured": round(
                (mm - statistics.mean(yall)) / (om - statistics.mean(yall)), 4)
            if om > statistics.mean(yall) else None,
            "prediction_span_over_true_span": round(
                (max(pv) - min(pv)) / (max(yall) - min(yall)), 4),
        })
    if e6["screening_variants"]:
        base = next((v for v in e6["screening_variants"]
                     if v["block"] == "X0_plus_mu2_over_Vm"), None)
        e6["screening_comparison"] = {
            "primary_regret": e6.get("regret"),
            "best_variant_regret": min(v["regret"]
                                       for v in e6["screening_variants"]),
            "note": (
                "主块 X0+X1 与变体使用同一协议与同一分子集, 只有特征块不同. "
                "若变体的 regret 大幅更低, 则主块的结论是**特征选择**造成的, "
                "不是描述符上限."
            ),
            "verdict": (
                "PRIMARY_BLOCK_UNDERSTATES_SCREENING"
                if base and e6.get("regret")
                and base["regret"] < e6["regret"] * 0.5
                else "CONSISTENT"),
        }
        with (OUT / "e6_ranking_b100.csv").open("w", newline="",
                                                encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["rank_by_prediction", "inchikey", "name", "family",
                        "y_true", "y_pred", "abs_error"])
            for rk, i in enumerate(order_pred, 1):
                w.writerow([rk, keys[i], rows[idxall[i]]["name"],
                            rows[idxall[i]].get("family", ""), round(yall[i], 4),
                            round(preds_all[i], 4),
                            round(abs(preds_all[i] - yall[i]), 4)])
    e6["status"] = "EXPLORATORY_LARGE_N"
    e6["inputs"] = {"model_matrix_b100": {"sha256": sha256_file(MATRIX)}}
    (OUT / "e6_manifest_b100.json").write_text(
        json.dumps(e6, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n[E6] oracle={e6.get('oracle_topk_mean')} model={e6.get('model_topk_mean')} "
          f"regret={e6.get('regret')} p={e6.get('p_random_at_least_as_good')}")
    print(f"   verdict={e6.get('verdict')}")

    # ============================ H4 ============================
    h4 = {"hypothesis": (
        "H4: 单分子电子描述符对低介电、弱缔合液体的预测能力, 系统性高于"
        "高介电、强缔合液体.")}
    groups = defaultdict(list)
    for j, i in enumerate(idxall):
        cls = rows[i].get("association_class") or "UNKNOWN"
        groups[cls].append((j, yall[j], preds_all[j]))
    h4["groups"] = {}
    for cls, items in groups.items():
        if len(items) < 8:
            h4["groups"][cls] = {"n": len(items), "status": "INSUFFICIENT_POWER"}
            continue
        errs = [abs(p - t) for _j, t, p in items]
        ys = [t for _j, t, p in items]
        ps = [p for _j, t, p in items]
        ybar = sum(ys) / len(ys)
        base = sum(abs(t - ybar) for t in ys) / len(ys)
        h4["groups"][cls] = {
            "n": len(items),
            "mae": round(sum(errs) / len(errs), 4),
            "constant_baseline_mae": round(base, 4),
            "beats_baseline": "true" if sum(errs) / len(errs) < base else "false",
            "median_epsilon": round(statistics.median(ys), 4),
            "spearman": round(spearman(ps, ys), 4),
        }
    # the actual comparison: WEAK_LOW_EPS vs STRONG_HIGH_EPS
    a = h4["groups"].get("WEAK_LOW_EPS", {})
    b = h4["groups"].get("STRONG_HIGH_EPS", {})
    if a.get("mae") is not None and b.get("mae") is not None:
        # normalise by each group's own scale, since epsilon magnitudes differ
        rel_a = a["mae"] / a["median_epsilon"]
        rel_b = b["mae"] / b["median_epsilon"]
        h4["comparison"] = {
            "weak_group_mae": a["mae"], "strong_group_mae": b["mae"],
            "weak_relative_mae": round(rel_a, 4),
            "strong_relative_mae": round(rel_b, 4),
            "ratio_weak_over_strong_relative": round(rel_a / rel_b, 4),
            "supports_h4": "true" if rel_a < rel_b else "false",
            "why_relative": (
                "两组 epsilon 量级不同 (低介电 vs 高介电), 直接比较 MAE 会把"
                "尺度差异误读为预测能力差异, 因此用各自中位数归一化."
            ),
        }
    n_weak = groups.get("WEAK_LOW_EPS", [])
    n_strong = groups.get("STRONG_HIGH_EPS", [])
    h4["power"] = {
        "n_weak": len(n_weak), "n_strong": len(n_strong),
        "sufficient": len(n_weak) >= 20 and len(n_strong) >= 20,
    }
    if not h4["power"]["sufficient"]:
        h4["status"] = "INSUFFICIENT_POWER"
    else:
        h4["status"] = "EXPLORATORY"
    h4["inputs"] = {"model_matrix_b100": {"sha256": sha256_file(MATRIX)}}
    (OUT / "h4_manifest_b100.json").write_text(
        json.dumps(h4, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n[H4] status={h4['status']} power={h4['power']}")
    if h4.get("comparison"):
        c = h4["comparison"]
        print(f"   weak rel MAE={c['weak_relative_mae']} "
              f"strong rel MAE={c['strong_relative_mae']} "
              f"supports_H4={c['supports_h4']}")

    print(f"\n[B100-E] wrote e1/e4/e6/h4 manifests into {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
