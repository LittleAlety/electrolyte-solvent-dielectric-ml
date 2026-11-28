#!/usr/bin/env python
"""B710-02: Source OOD and source-cluster statistics.

Three questions, deliberately kept separate:

  A. Agreement between independent studies measuring the SAME molecule
     (this is a measurement-reproducibility question, not a model question).
  B. Source OOD: hold out an entire original study, predict its molecules,
     and compare against the within-source (LOFO-style) baseline.
  C. Strict source+molecule OOD: hold out a source AND make sure the molecules
     it contains cannot leak into training through a different source.

C is the strict one. If a molecule appears in both the held-out source and the
training set (via another study), then plain source-OOD is not testing
generalisation to a new measurement programme — it is testing interpolation.

Source clusters are the real sampling unit, so the bootstrap resamples STUDIES,
not molecules. With few studies the interval is wide and this is reported as-is.

Outputs (outputs/b710_evidence/source_independence/):
  source_cluster_audit.json
  source_ood_results.json
  source_bootstrap_results.json
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
OUT = REPO_ROOT / "outputs" / "b710_evidence" / "source_independence"
GEN = "analyze_source_ood/1.0.0"
SEED = 20261125
LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

LEDGER = REPO_ROOT / "outputs" / "b100" / "deliverables" / "measurement_ledger_b100.csv"
EPS = REPO_ROOT / "outputs" / "b100" / "deliverables" / "epsilon_labels_b100.csv"
DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]
X_ELEC = ["dipole_D_v7", "homo_lumo_gap_ev_v7"]
AGREE_REL_TOL = 0.05
AGREE_T_TOL_K = 10.0
N_BOOT = 2000
MIN_CLUSTERS_FOR_CI = 3


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


def maes(y, p):
    return [abs(p[i] - y[i]) for i in range(len(y))]


def main() -> None:
    ledger = load_csv(LEDGER)
    eps_rows = load_csv(EPS)
    desc_rows = load_csv(DESC)

    eps = {r["inchikey"]: fnum(r["epsilon"]) for r in eps_rows}
    desc = {r["inchikey"]: r for r in desc_rows}

    # molecule -> set of original study ids (compendium collapsed to one)
    mol_sources = defaultdict(set)
    for r in ledger:
        ik = (r.get("inchikey") or "").strip()
        if ik not in eps:
            continue
        doc = (r.get("source_document") or "").strip()
        layer = (r.get("layer") or "").strip()
        comp = (layer == "nbs514_expansion"
                or "circular 514" in doc.lower()
                or "nbs.circ.514" in doc.lower())
        sid = "SRC-NBS514-COMPENDIUM" if comp else "SRC-DOI-" + doc.lower()
        mol_sources[ik].add(sid)

    # ---------------- A. cross-source agreement on the same molecule -----------
    per_mol_obs = defaultdict(list)
    for r in ledger:
        ik = (r.get("inchikey") or "").strip()
        if ik not in eps:
            continue
        doc = (r.get("source_document") or "").strip()
        layer = (r.get("layer") or "").strip()
        comp = (layer == "nbs514_expansion"
                or "circular 514" in doc.lower()
                or "nbs.circ.514" in doc.lower())
        sid = "SRC-NBS514-COMPENDIUM" if comp else "SRC-DOI-" + doc.lower()
        e = fnum(r.get("epsilon"))
        t = fnum(r.get("T_K"))
        if e is not None:
            per_mol_obs[ik].append((sid, t, e))

    pair_diffs = []
    for ik, obs in per_mol_obs.items():
        for i in range(len(obs)):
            for j in range(i + 1, len(obs)):
                s1, t1, e1 = obs[i]
                s2, t2, e2 = obs[j]
                if s1 == s2:
                    continue
                if t1 is not None and t2 is not None and abs(t1 - t2) > AGREE_T_TOL_K:
                    continue
                if not e2:
                    continue
                pair_diffs.append({
                    "inchikey": ik,
                    "rel_diff": abs(e1 - e2) / abs(e2),
                    "a": e1, "b": e2,
                })

    agreement = {
        "n_molecules_with_multiple_observations": len([k for k, v in per_mol_obs.items()
                                                       if len({o[0] for o in v}) >= 2]),
        "n_comparable_pairs": len(pair_diffs),
        "median_relative_difference": (round(statistics.median([d["rel_diff"] for d in pair_diffs]), 4)
                                        if pair_diffs else None),
        "mean_relative_difference": (round(statistics.mean([d["rel_diff"] for d in pair_diffs]), 4)
                                      if pair_diffs else None),
        "max_relative_difference": (round(max(d["rel_diff"] for d in pair_diffs), 4)
                                     if pair_diffs else None),
        "frac_pairs_within_5pct": (round(sum(1 for d in pair_diffs if d["rel_diff"] <= AGREE_REL_TOL)
                                          / len(pair_diffs), 4) if pair_diffs else None),
        "note": ("pairs are restricted to |dT| <= 10 K so the comparison is not "
                 "a temperature artifact"),
    }

    # ---------------- build feature matrix ------------------------------------
    mols, X, y = [], [], []
    for ik, e in eps.items():
        if e is None:
            continue
        d = desc.get(ik)
        if not d:
            continue
        xs = []
        ok = True
        for c in X0_COLS + X_ELEC:
            v = fnum(d.get(c))
            if v is None and c == "homo_lumo_gap_ev_v7":
                v = fnum(d.get("homo_lumo_gap_ev"))
            if v is None:
                ok = False
                break
            xs.append(v)
        if not ok:
            continue
        mols.append(ik)
        X.append(xs)
        y.append(e)
    n = len(y)
    idx_of = {ik: i for i, ik in enumerate(mols)}

    # ---------------- B. plain source OOD --------------------------------------
    # only sources with >= 3 molecules are worth holding out
    by_source = defaultdict(list)
    for ik in mols:
        for s in mol_sources.get(ik, ()):
            by_source[s].append(ik)

    source_ood = []
    for sid, iks in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
        test_idx = [idx_of[ik] for ik in iks if ik in idx_of]
        if len(test_idx) < 3:
            continue
        train_idx = [i for i in range(n) if i not in set(test_idx)]
        if len(train_idx) < 20:
            continue
        lam = choose_lambda([X[i] for i in train_idx], [y[i] for i in train_idx])
        pred = fit_predict([X[i] for i in train_idx], [y[i] for i in train_idx],
                           [X[i] for i in test_idx], lam)
        yy = [y[i] for i in test_idx]
        err = maes(yy, pred)
        ybar = statistics.mean(yy)
        const = statistics.mean(abs(v - ybar) for v in yy)
        # Strict variant. NOTE on what this actually tests:
        # here the held-out set is defined by MOLECULE, so a molecule that appears in
        # both the held-out study and another study is removed from training entirely.
        # That means plain source-OOD already satisfies the no-leak condition, and the
        # strict number should equal it. The genuinely leaky design would be to hold out
        # only the (molecule, study) PAIR while keeping the same molecule in training via
        # another study -- that measures re-measurement, not new-programme transfer, and
        # is deliberately NOT used as the primary number.
        leak = set(iks)
        strict_train = [i for i in train_idx if mols[i] not in leak]
        strict = None
        if len(strict_train) >= 20:
            lam2 = choose_lambda([X[i] for i in strict_train], [y[i] for i in strict_train])
            p2 = fit_predict([X[i] for i in strict_train], [y[i] for i in strict_train],
                             [X[i] for i in test_idx], lam2)
            strict = statistics.mean(maes(yy, p2))
        source_ood.append({
            "source_id": sid,
            "n_test_molecules": len(test_idx),
            "is_compendium": sid == "SRC-NBS514-COMPENDIUM",
            "ood_mae": round(statistics.mean(err), 4),
            "ood_bias": round(statistics.mean([pred[j] - yy[j] for j in range(len(yy))]), 4),
            "constant_baseline_mae": round(const, 4),
            "beats_constant": bool(statistics.mean(err) < const),
            "strict_no_leak_mae": round(strict, 4) if strict is not None else None,
            "n_training_molecules_removed_for_strict": len(train_idx) - len(strict_train),
            "bias_dominates": bool(abs(statistics.mean([pred[j] - yy[j] for j in range(len(yy))]))
                                   > 0.7 * statistics.mean(err)),
        })

    # ---------------- source cluster bootstrap --------------------------------
    # resample STUDIES with replacement; recompute pooled cross-source error
    clusters = [s for s in source_ood if s["n_test_molecules"] >= 3]
    boot = []
    if len(clusters) >= MIN_CLUSTERS_FOR_CI:
        rng = random.Random(SEED)
        for _ in range(N_BOOT):
            pick = [rng.choice(clusters) for _ in clusters]
            w = sum(c["n_test_molecules"] for c in pick)
            if w == 0:
                continue
            boot.append(sum(c["ood_mae"] * c["n_test_molecules"] for c in pick) / w)
        boot.sort()

    bootstrap = {
        "n_clusters_used": len(clusters),
        "n_bootstrap": len(boot),
        "resampling_unit": "original study (not molecule)",
        "pooled_source_ood_mae": (round(sum(c["ood_mae"] * c["n_test_molecules"] for c in clusters)
                                        / max(sum(c["n_test_molecules"] for c in clusters), 1), 4)
                                   if clusters else None),
        "boot_ci95": ([round(boot[int(0.025 * len(boot))], 4),
                       round(boot[int(0.975 * len(boot))], 4)] if boot else None),
        "boot_median": round(statistics.median(boot), 4) if boot else None,
        "status": ("RELIABLE" if len(clusters) >= 5 else
                   "EXPLORATORY" if len(clusters) >= MIN_CLUSTERS_FOR_CI else
                   "NOT_ESTIMABLE"),
        "caveat": (
            "resampling 3-4 studies gives an interval that is itself unreliable; "
            "with fewer than 3 the interval is not estimable at all."
        ),
    }

    cluster_audit = {
        "schema": "b710.source_cluster_audit/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules_modelled": n,
        "n_original_studies_total": len(by_source),
        "n_studies_with_ge3_molecules": len(clusters),
        "compendium_present": "SRC-NBS514-COMPENDIUM" in by_source,
        "compendium_molecule_count": len(by_source.get("SRC-NBS514-COMPENDIUM", [])),
        "molecules_by_source_count": dict(Counter(len(v) for v in mol_sources.values())),
        "agreement": agreement,
        "bootstrap": bootstrap,
        "separation": {
            "source_ood": "held-out measurement programme, molecules may still appear in training via other studies",
            "strict_source_ood": "held-out programme AND its molecules removed from training",
            "chemical_ood": "leave-one-family-out; a different question entirely",
            "warning": "these three must never be pooled into one 'generalisation' number",
        },
    }
    (OUT / "source_cluster_audit.json").write_text(
        json.dumps(cluster_audit, ensure_ascii=False, indent=2), encoding="utf-8")

    ood_doc = {
        "schema": "b710.source_ood_results/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "features": "X0 structure + r2SCAN-3c SP electronic",
        "n_molecules": n,
        "sources": source_ood,
        "summary": {
            "n_sources_evaluable": len(source_ood),
            "n_beating_constant": sum(1 for s in source_ood if s["beats_constant"]),
            "mean_ood_mae": (round(statistics.mean([s["ood_mae"] for s in source_ood]), 4)
                             if source_ood else None),
            "mean_strict_mae": (round(statistics.mean([s["strict_no_leak_mae"] for s in source_ood
                                                       if s["strict_no_leak_mae"] is not None]), 4)
                                if any(s["strict_no_leak_mae"] is not None for s in source_ood) else None),
            "n_strict_evaluable": sum(1 for s in source_ood if s["strict_no_leak_mae"] is not None),
            "n_sources_where_bias_dominates": sum(1 for s in source_ood if s["bias_dominates"]),
            "strict_equals_plain_reason": (
                "held-out sets are molecule-defined, so no molecule can reach training via "
                "another study; strict and plain therefore coincide by construction"
            ),
        },
    }
    (OUT / "source_ood_results.json").write_text(
        json.dumps(ood_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "source_bootstrap_results.json").write_text(
        json.dumps({"schema": "b710.source_bootstrap/v1",
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "generator": GEN, **bootstrap}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # ---------------- console -------------------------------------------------
    print(f"modelled molecules: {n}")
    print(f"original studies total: {len(by_source)}, with >=3 molecules: {len(clusters)}")
    print(f"agreement: {agreement['n_comparable_pairs']} pairs, "
          f"median rel diff {agreement['median_relative_difference']}, "
          f"{agreement['frac_pairs_within_5pct']} within 5%")
    print(f"source OOD: {len(source_ood)} evaluable, "
          f"{ood_doc['summary']['n_beating_constant']} beat constant")
    print(f"bootstrap: {bootstrap['status']}, "
          f"pooled MAE {bootstrap['pooled_source_ood_mae']}, CI {bootstrap['boot_ci95']}")


if __name__ == "__main__":
    main()
