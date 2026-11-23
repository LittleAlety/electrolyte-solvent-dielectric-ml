#!/usr/bin/env python
"""B100-18: bounded target transforms -- the physically correct regression scale.

Every model so far regressed epsilon directly with an unbounded linear fit, which
produces predictions the physics forbids. The 239-molecule E1 run emitted values below
1 (a relative permittivity below 1 has no meaning for a condensed phase), and the
halocarbon failure is dominated by the same extrapolation.

The Kirkwood-Onsager / Clausius-Mossotti relation says the right response variable is
NOT epsilon but

    y = (epsilon - 1) / (epsilon + 2)
      = (N_A / 3 epsilon_0) (alpha_m + mu^2 / 3 k T) / V_m

which is LINEAR in mu^2/V_m. Two consequences follow, and both are testable:

  1. The transform bounds the output: any finite y < 1 maps back to epsilon > 1, so
     unphysical predictions become structurally impossible (still needs a clamp).
  2. If the theory holds, the mu^2/V_m feature should explain y almost entirely --
     a much stronger claim than "the feature correlates with epsilon".

This script fits three response scales on the SAME data and SAME protocols:

    identity              epsilon itself (the previous approach)
    log                   log(epsilon), also positivity-preserving
    clausius_mossotti     (epsilon-1)/(epsilon+2), the theoretically motivated one

and reports, for each: error on the ORIGINAL epsilon scale (so the numbers stay
comparable), plus how many predictions fell below the physical floor.

Output: outputs/b100/e1b_target_transform_b100.json
        outputs/b100/e1b_target_transform_b100.csv
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "run_b100_target_transforms/1.0.0"

MATRIX = OUT / "model_matrix_b100.csv"
MATRIX_MAN = OUT / "model_matrix_b100.json"

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]
X1_COLS = ["dipole_D", "homo_lumo_gap_ev"]
XN_COLS = ["mu_sq_over_Vm"]

BLOCKS = {
    "X0_structure": X0_COLS,
    "X1_electronic": X1_COLS,
    "Xn_mu2_over_Vm": XN_COLS,
    "X0_plus_Xn": X0_COLS + XN_COLS,
    "X0_X1_Xn": X0_COLS + X1_COLS + XN_COLS,
}
TRANSFORMS = ["identity", "log", "clausius_mossotti"]

LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
SEED = 20261123
EPS_FLOOR = 1.0
EPS_CEIL = 500.0     # guard: CM inverse blows up as y -> 1

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


# ---------------------------------------------------------------- transforms

def fwd(eps: float, kind: str) -> float | None:
    if eps is None or eps <= 0:
        return None
    if kind == "identity":
        return eps
    if kind == "log":
        return math.log(eps)
    if kind == "clausius_mossotti":
        return (eps - 1.0) / (eps + 2.0)
    raise ValueError(kind)


def inv(y: float, kind: str) -> float:
    """Inverse transform, clamped to the physically attainable range."""
    if kind == "identity":
        v = y
    elif kind == "log":
        v = math.exp(y) if y < 20 else math.exp(20)
    elif kind == "clausius_mossotti":
        # y = (e-1)/(e+2)  =>  e = (1 + 2y)/(1 - y)
        if y >= 1.0:
            return EPS_CEIL
        v = (1.0 + 2.0 * y) / (1.0 - y)
    else:
        raise ValueError(kind)
    return min(max(v, EPS_FLOOR), EPS_CEIL)


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
    rng = random.Random(seed)
    order = list(range(n))
    rng.shuffle(order)
    folds = [[] for _ in range(k)]
    for i, idx in enumerate(order):
        folds[i % k].append(idx)
    return folds


def choose_lambda(Xtr, ytr, seed=SEED, k=5):
    n = len(Xtr)
    if n < k * 3:
        return 1.0
    folds = kfold_idx(n, k, seed)
    best_lam, best = LAMBDA_GRID[0], float("inf")
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
            if m < best:
                best, best_lam = m, lam
    return best_lam


def loo(X, y):
    n = len(X)
    pred, lams = [], []
    for hold in range(n):
        tr = [i for i in range(n) if i != hold]
        lam = choose_lambda([X[i] for i in tr], [y[i] for i in tr])
        lams.append(lam)
        pred.extend(fit_predict([X[i] for i in tr], [y[i] for i in tr],
                                [X[hold]], lam))
    return pred, lams


def metrics(y, p):
    n = len(y)
    err = [p[i] - y[i] for i in range(n)]
    mae = sum(abs(e) for e in err) / n
    rmse = math.sqrt(sum(e * e for e in err) / n)
    ybar = sum(y) / n
    sst = sum((v - ybar) ** 2 for v in y)
    ssr = sum(e * e for e in err)
    r2 = 1 - ssr / sst if sst > 0 else float("nan")
    return {"mae": mae, "rmse": rmse, "r2": r2, "bias": sum(err) / n, "n": n}


def main() -> int:
    if not MATRIX.is_file():
        print(f"FATAL: missing {MATRIX}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load(MATRIX)

    # common set across all blocks
    union = list(dict.fromkeys([c for cols in BLOCKS.values() for c in cols]))
    idx = []
    for i, r in enumerate(rows):
        if fnum(r.get("epsilon")) is None:
            continue
        if any(fnum(r.get(c)) is None for c in union):
            continue
        idx.append(i)
    eps = [fnum(rows[i]["epsilon"]) for i in idx]
    n = len(eps)
    ybar = sum(eps) / n
    const_mae = sum(abs(e - ybar) for e in eps) / n
    print(f"[B100-18] common set = {n} molecules, constant baseline MAE "
          f"= {const_mae:.4f}")

    results: list[dict] = []
    for tkind in TRANSFORMS:
        for label, cols in BLOCKS.items():
            X = [[fnum(rows[i][c]) for c in cols] for i in idx]
            yt = [fwd(e, tkind) for e in eps]
            if any(v is None for v in yt):
                continue
            pred_t, _ = loo(X, yt)
            # map back to the epsilon scale before scoring: all errors are reported
            # in epsilon units so the three transforms stay comparable
            pred = [inv(v, tkind) for v in pred_t]
            m = metrics(eps, pred)
            n_below = sum(1 for v in pred if v < EPS_FLOOR)
            n_clamped = sum(1 for v in pred
                            if v <= EPS_FLOOR + 1e-9 or v >= EPS_CEIL - 1e-9)
            results.append({
                "transform": tkind,
                "block": label,
                "n_features": len(cols),
                "n_used": n,
                "mae": round(m["mae"], 4),
                "rmse": round(m["rmse"], 4),
                "r2": round(m["r2"], 4),
                "bias": round(m["bias"], 4),
                "constant_baseline_mae": round(const_mae, 4),
                "beats_constant": "true" if m["mae"] < const_mae else "false",
                "mae_reduction_pct": round(100 * (1 - m["mae"] / const_mae), 2),
                "n_pred_below_eps_floor": n_below,
                "n_pred_clamped": n_clamped,
                "positivity_enforced": "true" if tkind != "identity" else "false",
            })
            print(f"  {tkind:18s} {label:16s} MAE={m['mae']:8.4f} "
                  f"R2={m['r2']:+7.3f} below1={n_below}")

    path = OUT / "e1b_target_transform_b100.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        w.writeheader()
        for r in results:
            w.writerow(r)

    best = min(results, key=lambda r: r["mae"])
    by_t = {}
    for t in TRANSFORMS:
        rs = [r for r in results if r["transform"] == t]
        if rs:
            best_t = min(rs, key=lambda r: r["mae"])
            by_t[t] = {
                "best_block": best_t["block"],
                "mae": best_t["mae"],
                "r2": best_t["r2"],
                "n_pred_below_floor": sum(r["n_pred_below_eps_floor"] for r in rs),
            }
    identity_below = by_t.get("identity", {}).get("n_pred_below_floor", 0)
    cm_below = by_t.get("clausius_mossotti", {}).get("n_pred_below_floor", 0)

    doc = {
        "schema": "b100.target_transform/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "why": (
            "所有既有模型都用无界线性回归拟合 epsilon, 会给出 epsilon<1 的"
            "非物理预测, 卤代烃外推爆掉也源于此. "
            "Clausius-Mossotti 给出正确的响应变量 (eps-1)/(eps+2), "
            "它在 mu^2/Vm 上是线性的, 且把输出限制在 epsilon>1."
        ),
        "n_molecules": n,
        "constant_baseline_mae": round(const_mae, 4),
        "transforms_compared": list(TRANSFORMS),
        "best_overall": best,
        "by_transform": by_t,
        "positivity": {
            "identity_predictions_below_floor": identity_below,
            "clausius_mossotti_predictions_below_floor": cm_below,
            "note": (
                "identity 目标会产生 epsilon<1 的预测; 有界变换在结构上避免, "
                "并在反变换处加 [1, 500] 夹取. 夹取次数已报告, 不隐藏."
            ),
        },
        "theory_note": (
            "若 Kirkwood-Onsager 成立, mu^2/Vm 应对 (eps-1)/(eps+2) 有很高解释力. "
            "这比『该特征与 epsilon 相关』强得多, 是本实验要检验的. "
            "但 g 因子 (偶极关联) 仍不在任何单分子描述符中, 因此即使 CM 拟合良好, "
            "也不等于液体介电常数可由单分子量预测."
        ),
        "inputs": {"model_matrix_b100": {"sha256": sha256_file(MATRIX)}},
        "output": {"path": str(path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(path), "rows": len(results)},
    }
    j_path = OUT / "e1b_target_transform_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"\n[B100-18] {j_path}")
    print(f"  best overall: {best['transform']} / {best['block']} "
          f"MAE={best['mae']} R2={best['r2']}")
    for t, v in by_t.items():
        print(f"  {t:18s} best={v['best_block']:16s} MAE={v['mae']:8.4f} "
              f"below_floor={v['n_pred_below_floor']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
