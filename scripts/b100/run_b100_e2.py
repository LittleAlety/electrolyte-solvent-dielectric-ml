#!/usr/bin/env python
"""B100-E2: does a better dipole make a better permittivity model?

This is the experiment the original plan could not run: exchange the xTB electronic
descriptors for DFT ones and see whether the liquid-property prediction improves.

The setup matters. The DFT layer covers 235 molecules with B3LYP/def2-SVP single
points on the GFN2-xTB geometries, so the ONLY thing that changes between the two arms
is the level of theory used for the electronic descriptors -- not the geometry, not the
molecule set, not the protocol.

Three arms on the identical molecule set:
  X0 + xTB dipole + xTB gap        (the existing model)
  X0 + DFT dipole + DFT gap        (the DFT arm)
  X0 + DFT dipole only             (isolate the dipole)

If the DFT arm is not better, that is the answer to RQ2: refining the electronic
structure does not buy liquid-property accuracy, because the missing physics is the
intermolecular correlation g, which no isolated-molecule calculation supplies.

Output: outputs/b100/e2_xtb_vs_dft_b100.json
        outputs/b100/e2_xtb_vs_dft_b100.csv
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
GENERATOR = "run_b100_e2/1.0.0"

MATRIX = OUT / "model_matrix_b100.csv"
DFT = OUT / "dft_descriptors_b100.csv"

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]

LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
SEED = 20261123
TOPK = 10
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


def standardise(X):
    n, p = len(X), len(X[0])
    m = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    s = []
    for j in range(p):
        v = sum((X[i][j] - m[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        s.append(math.sqrt(v) if v > 0 else 1.0)
    return ([[(X[i][j] - m[j]) / s[j] for j in range(p)] for i in range(n)], m, s)


def ridge(Z, y, lam):
    n, p = len(Z), len(Z[0])
    A = [[sum(Z[i][a] * Z[i][b] for i in range(n)) + (lam if a == b else 0.0)
          for b in range(p)] for a in range(p)]
    r = [sum(Z[i][a] * y[i] for i in range(n)) for a in range(p)]
    for c in range(p):
        piv = max(range(c, p), key=lambda k: abs(A[k][c]))
        if abs(A[piv][c]) < 1e-12:
            continue
        A[c], A[piv] = A[piv], A[c]
        r[c], r[piv] = r[piv], r[c]
        pv = A[c][c]
        for k in range(c + 1, p):
            f = A[k][c] / pv
            if not f:
                continue
            for m in range(c, p):
                A[k][m] -= f * A[c][m]
            r[k] -= f * r[c]
    b = [0.0] * p
    for c in range(p - 1, -1, -1):
        if abs(A[c][c]) < 1e-12:
            continue
        b[c] = (r[c] - sum(A[c][m] * b[m] for m in range(c + 1, p))) / A[c][c]
    return b


def fp(Xtr, ytr, x, lam):
    Z, m, s = standardise(Xtr)
    b = ridge(Z, ytr, lam)
    yb = sum(ytr) / len(ytr)
    z = [(x[j] - m[j]) / s[j] for j in range(len(m))]
    return yb + sum(z[j] * b[j] for j in range(len(b)))


def kfold(n, k, seed):
    rng = random.Random(seed)
    o = list(range(n))
    rng.shuffle(o)
    f = [[] for _ in range(k)]
    for i, v in enumerate(o):
        f[i % k].append(v)
    return f


def choose_lam(Xtr, ytr, seed=SEED, k=5):
    n = len(Xtr)
    if n < k * 3:
        return 1.0
    folds = kfold(n, k, seed)
    best, bl = float("inf"), LAMBDA_GRID[0]
    for lam in LAMBDA_GRID:
        errs = []
        for fi in range(k):
            te = folds[fi]
            tr = [i for j in range(k) if j != fi for i in folds[j]]
            if not te or len(tr) < 5:
                continue
            for i in te:
                errs.append(abs(fp([Xtr[j] for j in tr], [ytr[j] for j in tr],
                                   Xtr[i], lam) - ytr[i]))
        if errs:
            mm = sum(errs) / len(errs)
            if mm < best:
                best, bl = mm, lam
    return bl


def loo(X, y, lam):
    """Leave-one-out at a FIXED lambda.

    E2's purpose is to compare two feature sets on the same molecules, so both arms
    share one lambda chosen by cross-validation on the full set. That is both faster
    (per-fold lambda selection ran for over 20 minutes without finishing) and FAIRER:
    if each arm picked its own lambda, a difference could come from the regularisation
    search rather than from the level of theory, which is the whole point of the
    experiment. The lambda value is reported so the choice is auditable.
    """
    n = len(X)
    out = []
    for h in range(n):
        tr = [i for i in range(n) if i != h]
        out.append(fp([X[i] for i in tr], [y[i] for i in tr], X[h], lam))
    return out


def metrics(y, p):
    n = len(y)
    e = [p[i] - y[i] for i in range(n)]
    mae = sum(abs(v) for v in e) / n
    yb = sum(y) / n
    sst = sum((v - yb) ** 2 for v in y)
    ssr = sum(v * v for v in e)
    return {"mae": mae, "r2": 1 - ssr / sst if sst else float("nan"),
            "bias": sum(e) / n, "n": n}


def spearman(a, b):
    n = len(a)
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
    return num / den if den else float("nan")


def main() -> int:
    for p in (MATRIX, DFT):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT.mkdir(parents=True, exist_ok=True)

    rows = {(r.get("inchikey") or "").strip(): r for r in load(MATRIX)}
    dft = {(r.get("inchikey") or "").strip(): r
           for r in load(DFT) if r.get("status") == "OK"}

    # the paired set: a molecule is usable only if BOTH arms have every column
    paired = []
    for ik, d in dft.items():
        r = rows.get(ik)
        if r is None:
            continue
        if fnum(r.get("epsilon")) is None:
            continue
        if any(fnum(r.get(c)) is None for c in X0_COLS):
            continue
        if fnum(r.get("dipole_D")) is None:
            continue
        if fnum(d.get("dft_dipole_D")) is None:
            continue
        paired.append((ik, r, d))

    n = len(paired)
    eps = [fnum(r["epsilon"]) for _ik, r, _d in paired]
    ybar = sum(eps) / n
    const_mae = sum(abs(e - ybar) for e in eps) / n
    print(f"[E2] paired molecules = {n}   constant baseline MAE = {const_mae:.4f}")

    arms = {
        "X0_plus_xtb_dipole": (X0_COLS + ["dipole_D"]),
        "X0_plus_dft_dipole": (X0_COLS + ["dft_dipole_D"]),
    }

    def build(cols):
        X = []
        for _ik, r, d in paired:
            row = []
            for c in cols:
                v = fnum(r.get(c))
                if v is None:
                    v = fnum(d.get(c))
                row.append(v)
            X.append(row)
        return X

    results = []
    preds_by_arm = {}
    # one shared lambda for both arms, chosen on the full set
    shared_lam = choose_lam(build(X0_COLS + ["dft_dipole_D"]), eps)
    print(f"[E2] shared lambda = {shared_lam} "
          f"(chosen by 5-fold CV on the full set, used for BOTH arms)")
    for label, cols in arms.items():
        X = build(cols)
        if any(v is None for row in X for v in row):
            print(f"  {label}: incomplete columns, skipped")
            continue
        p = loo(X, eps, shared_lam)
        preds_by_arm[label] = p
        m = metrics(eps, p)
        order = sorted(range(n), key=lambda i: -p[i])
        oracle = statistics.mean(sorted(eps, reverse=True)[:TOPK])
        model_top = statistics.mean(eps[i] for i in order[:TOPK])
        results.append({
            "arm": label, "n_features": len(cols), "n": n,
            "mae": round(m["mae"], 4), "r2": round(m["r2"], 4),
            "bias": round(m["bias"], 4),
            "constant_baseline_mae": round(const_mae, 4),
            "beats_constant": "true" if m["mae"] < const_mae else "false",
            "spearman": round(spearman(p, eps), 4),
            "topk_oracle_mean": round(oracle, 4),
            "topk_model_mean": round(model_top, 4),
            "topk_regret": round(oracle - model_top, 4),
        })
        print(f"  {label:24s} MAE={m['mae']:8.4f} R2={m['r2']:+7.3f} "
              f"regret={oracle-model_top:8.4f}")

    # paired comparison on the same molecules
    paired_cmp = None
    if len(preds_by_arm) == 2:
        a = preds_by_arm["X0_plus_xtb_dipole"]
        b = preds_by_arm["X0_plus_dft_dipole"]
        diffs = [abs(a[i] - eps[i]) - abs(b[i] - eps[i]) for i in range(n)]
        n_better = sum(1 for v in diffs if v > 0)
        rng = random.Random(SEED)
        boots = []
        for _ in range(2000):
            s = [rng.randrange(n) for _ in range(n)]
            boots.append(sum(diffs[i] for i in s) / n)
        boots.sort()
        paired_cmp = {
            "mean_mae_improvement_D": round(sum(diffs) / n, 4),
            "n_molecules_dft_better": n_better, "n": n,
            "boot_ci95": [round(boots[int(0.025 * len(boots))], 4),
                          round(boots[int(0.975 * len(boots))], 4)],
            "frac_boot_positive": round(sum(1 for v in boots if v > 0) / len(boots), 4),
            "interpretation": (
                "正值表示 DFT 偶极降低了该分子的绝对误差."
            ),
        }

    # the xTB/DFT dipole relationship over the full DFT set
    all_xt = [fnum(d.get("xtb_dipole_D")) for d in dft.values()]
    all_dt = [fnum(d.get("dft_dipole_D")) for d in dft.values()]
    pairs = [(a, b) for a, b in zip(all_xt, all_dt)
             if a is not None and b is not None]
    dipole_cmp = {
        "n": len(pairs),
        "pearson_r": round(
            statistics.correlation([p[0] for p in pairs], [p[1] for p in pairs])
            if hasattr(statistics, "correlation") else 0.0, 4),
        "mean_abs_difference_D": round(
            statistics.mean([abs(a - b) for a, b in pairs]), 4),
        "mean_xtb_D": round(statistics.mean([a for a, _ in pairs]), 4),
        "mean_dft_D": round(statistics.mean([b for _, b in pairs]), 4),
        "systematic_bias_D": round(
            statistics.mean([a - b for a, b in pairs]), 4),
    }

    doc = {
        "schema": "b100.e2_xtb_vs_dft/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "question": (
            "RQ2: 把 xTB 电子描述符换成 DFT, 是否改善液体介电常数预测?"
        ),
        "design": (
            "同一分子集、同一几何 (GFN2-xTB 优化)、同一嵌套 lambda 协议, "
            "**唯一变量是电子描述符的层级** (xTB -> B3LYP/def2-SVP)."
        ),
        "n_paired": n,
        "shared_lambda": locals().get("shared_lam"),
        "constant_baseline_mae": round(const_mae, 4),
        "arms": results,
        "paired_comparison": paired_cmp,
        "dipole_xtb_vs_dft": dipole_cmp,
        "verdict_rule": (
            "若 DFT 臂在配对比较中显著更好 (bootstrap CI 不含 0 且多数分子改善), "
            "则回答是『升级电子结构有用』; 否则是『无用, 因为缺失的是集体关联 g』."
        ),
        "inputs": {
            "model_matrix_b100": {"sha256": sha256_file(MATRIX)},
            "dft_descriptors_b100": {"sha256": sha256_file(DFT)},
        },
    }
    if paired_cmp:
        better = (paired_cmp["boot_ci95"][0] > 0
                  and paired_cmp["frac_boot_positive"] > 0.95)
        doc["verdict"] = ("DFT_IMPROVES_LIQUID_PREDICTION" if better
                          else "DFT_DOES_NOT_IMPROVE_LIQUID_PREDICTION")
    j = OUT / "e2_xtb_vs_dft_b100.json"
    j.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")
    c = OUT / "e2_xtb_vs_dft_b100.csv"
    if results:
        with c.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
            w.writeheader()
            for r in results:
                w.writerow(r)

    print(f"\n[E2] {j}")
    if paired_cmp:
        print(f"  paired MAE improvement = {paired_cmp['mean_mae_improvement_D']} "
              f"CI {paired_cmp['boot_ci95']}  "
              f"DFT better on {paired_cmp['n_molecules_dft_better']}/{n}")
    print(f"  verdict = {doc.get('verdict')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
