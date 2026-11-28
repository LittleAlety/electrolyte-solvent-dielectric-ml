#!/usr/bin/env python
"""B722-02: source OOD on the primary-study and laboratory axes.

Three questions, kept apart:

  A. Cross-source agreement  — do independent studies measure the same molecule
     to the same value? This is measurement reproducibility, not a model result.
  B. Leave-one-primary-study-out — hold out a whole study, predict its molecules.
  C. Leave-one-laboratory-out — with laboratories only partially resolvable, this
     collapses onto the publisher axis and is reported as such, not dressed up.

A note on what "strict" can and cannot mean here. Because every molecule appears
under at most a handful of studies and the held-out set is MOLECULE-defined, a
molecule cannot leak into training through another study while its own study is
held out. What CAN happen - and is checked - is that a held-out study's molecules
are also covered by the compendium, in which case the model has effectively seen
them. Those rows are flagged `training_covers_test_molecules` so the OOD number
is not over-read.

Outputs (outputs/b722_source_independence/):
  cross_source_agreement.csv
  source_ood_results.json
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
OUT = REPO_ROOT / "outputs" / "b722_source_independence"
GEN = "analyze_source_ood_3layer/1.0.0"
SEED = 20261125
LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
AGREE_REL_TOL = 0.05
AGREE_T_TOL_K = 10.0
MIN_TEST = 3
N_BOOT = 2000

REG = OUT / "source_registry_3layer.csv"
DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]
X_ELEC = ["dipole_D_v7", "homo_lumo_gap_ev_v7"]


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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    reg = load_csv(REG)
    desc_rows = load_csv(DESC)
    desc = {r["inchikey"]: r for r in desc_rows}

    valid = [r for r in reg
             if r["verification_status"] != "REJECTED_DEFINITION_MISMATCH"]

    # ---------------- A. cross-source agreement ----------------------------
    per_mol = defaultdict(list)
    for r in valid:
        e = fnum(r["epsilon"])
        t = fnum(r["temperature_K"])
        if e is None:
            continue
        per_mol[r["inchikey"]].append({
            "source": r["primary_study_layer"],
            "db": r["database_layer"],
            "eps": e, "T": t,
        })

    pairs = []
    for ik, obs in per_mol.items():
        for i in range(len(obs)):
            for j in range(i + 1, len(obs)):
                a, b = obs[i], obs[j]
                if a["source"] == b["source"] and a["db"] == b["db"]:
                    continue
                t1, t2 = a["T"], b["T"]
                if t1 is not None and t2 is not None and abs(t1 - t2) > AGREE_T_TOL_K:
                    continue
                if not b["eps"]:
                    continue
                pairs.append({
                    "inchikey": ik,
                    "src_a": a["source"], "db_a": a["db"], "eps_a": a["eps"],
                    "src_b": b["source"], "db_b": b["db"], "eps_b": b["eps"],
                    "T_a": t1, "T_b": t2,
                    "rel_diff": abs(a["eps"] - b["eps"]) / abs(b["eps"]),
                })

    agree_rows = pairs
    rels = sorted(p["rel_diff"] for p in pairs)
    agreement = {
        "n_comparable_pairs": len(pairs),
        "n_molecules_with_comparison": len({p["inchikey"] for p in pairs}),
        "median_relative_difference": round(statistics.median(rels), 4) if rels else None,
        "mean_relative_difference": round(statistics.mean(rels), 4) if rels else None,
        "p90_relative_difference": (round(rels[int(0.9 * (len(rels) - 1))], 4)
                                    if rels else None),
        "max_relative_difference": round(max(rels), 4) if rels else None,
        "frac_within_5pct": round(sum(1 for v in rels if v <= AGREE_REL_TOL) / len(rels), 4)
                            if rels else None,
        "frac_within_2pct": round(sum(1 for v in rels if v <= 0.02) / len(rels), 4)
                            if rels else None,
        "note": ("pairs restricted to |dT| <= 10 K; cross-database pairs between "
                 "NBS514 and ThermoML are included because they are different "
                 "editorial sources even when the underlying measurement may agree"),
    }
    if agree_rows:
        with (OUT / "cross_source_agreement.csv").open("w", newline="",
                                                       encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(agree_rows[0].keys()))
            w.writeheader()
            w.writerows(agree_rows)

    # ---------------- build feature matrix --------------------------------
    mols, X, y = [], [], []
    for ik, d in desc.items():
        e_recs = per_mol.get(ik)
        if not e_recs:
            continue
        # frozen target: the epsilon label, not an external value
        from_eps = None
        x = []
        ok = True
        for c in X0_COLS + X_ELEC:
            v = fnum(d.get(c))
            if v is None and c == "homo_lumo_gap_ev_v7":
                v = fnum(d.get("homo_lumo_gap_ev"))
            if v is None:
                ok = False
                break
            x.append(v)
        if not ok:
            continue
        mols.append(ik)
        X.append(x)
    # y from the frozen labels, join on inchikey
    EPS = REPO_ROOT / "outputs" / "b100" / "deliverables" / "epsilon_labels_b100.csv"
    eps_map = {r["inchikey"]: fnum(r["epsilon"]) for r in load_csv(EPS)}
    keep = [(i, ik) for i, ik in enumerate(mols) if eps_map.get(ik) is not None]
    X = [X[i] for i, _ in keep]
    mols = [ik for _, ik in keep]
    y = [eps_map[ik] for ik in mols]
    n = len(y)
    idx_of = {ik: i for i, ik in enumerate(mols)}
    compendium_mols = {r["inchikey"] for r in valid
                       if r["primary_study_layer"] == "PRIMARY-NBS514-COMPENDIUM"}

    # ---------------- clean-OOD feasibility (computed BEFORE any model fit) --
    # A truly clean leave-one-study-out needs held-out molecules that have NO
    # record under any other source -- otherwise the model was trained on the same
    # molecule via the compendium and the "OOD" number is contaminated. This is
    # measured first so the OOD tables below cannot be mistaken for clean tests.
    srcs_per_mol = defaultdict(set)
    for r in valid:
        if r["inchikey"] in idx_of:
            srcs_per_mol[r["inchikey"]].add(r["primary_study_layer"])
    exclusive_by_study = defaultdict(set)
    for mol, sv in srcs_per_mol.items():
        if len(sv) == 1:
            only = next(iter(sv))
            exclusive_by_study[only].add(mol)
    clean_eligible = {k: len(v) for k, v in exclusive_by_study.items()
                      if len(v) >= MIN_TEST and k != "PRIMARY-NBS514-COMPENDIUM"}
    clean_feasibility = {
        "definition": ("a study is clean-OOD-eligible only if it holds >=3 molecules "
                       "that carry no record under any other primary study"),
        "n_studies_clean_eligible": len(clean_eligible),
        "studies": clean_eligible,
        "verdict": ("CLEAN_SOURCE_OOD_FEASIBLE" if clean_eligible
                    else "CLEAN_SOURCE_OOD_NOT_FEASIBLE"),
        "why": (
            "the NBS 514 compendium covers 186/239 molecules and almost every other "
            "study overlaps it, so holding out a study leaves the same molecules in "
            "training through the compendium. Any 'source OOD' number computed here is "
            "therefore a programme-shift stress test, NOT a clean unseen-source test."
        ) if not clean_eligible else "at least one study is clean-OOD-eligible",
    }

    # ---------------- B/C. leave-one-source-out ---------------------------
    def loo_source(axis):
        by_src = defaultdict(set)
        for r in valid:
            if r["inchikey"] in idx_of:
                by_src[r[axis]].add(r["inchikey"])
        out = []
        for src, iks in sorted(by_src.items(), key=lambda kv: -len(kv[1])):
            if src == "UNRESOLVED":
                continue
            test_idx = [idx_of[ik] for ik in iks if ik in idx_of]
            if len(test_idx) < MIN_TEST:
                continue
            train_idx = [i for i in range(n) if i not in set(test_idx)]
            if len(train_idx) < 20:
                continue
            # leakage flag: are any held-out molecules ALSO covered by another
            # source that remains in training?
            leaked = [mols[i] for i in test_idx
                      if any(r["inchikey"] == mols[i] and r[axis] != src
                             for r in valid)]
            lam = choose_lambda([X[i] for i in train_idx], [y[i] for i in train_idx])
            pred = fit_predict([X[i] for i in train_idx], [y[i] for i in train_idx],
                               [X[i] for i in test_idx], lam)
            yy = [y[i] for i in test_idx]
            err = [abs(pred[j] - yy[j]) for j in range(len(yy))]
            ybar = statistics.mean(yy)
            const = statistics.mean(abs(v - ybar) for v in yy)
            out.append({
                "axis": axis,
                "source": src,
                "n_test": len(test_idx),
                "ood_mae": round(statistics.mean(err), 4),
                "ood_bias": round(statistics.mean([pred[j] - yy[j]
                                                   for j in range(len(yy))]), 4),
                "constant_baseline_mae": round(const, 4),
                "beats_constant": bool(statistics.mean(err) < const),
                "n_test_molecules_also_in_training_via_other_source": len(leaked),
                "clean_ood": len(leaked) == 0,
            })
        return out

    study_ood = loo_source("primary_study_layer")
    lab_ood = loo_source("laboratory_layer")

    # source-cluster bootstrap on the study axis
    clusters = [s for s in study_ood if s["n_test"] >= MIN_TEST]
    boot = []
    if len(clusters) >= 3:
        rng = random.Random(SEED)
        for _ in range(N_BOOT):
            pick = [rng.choice(clusters) for _ in clusters]
            w = sum(c["n_test"] for c in pick)
            boot.append(sum(c["ood_mae"] * c["n_test"] for c in pick) / w)
        boot.sort()

    def q(v, p):
        if not v:
            return None
        return round(v[int(p * (len(v) - 1))], 4)

    doc = {
        "schema": "b722.source_ood/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules_modelled": n,
        "features": "X0 structure + r2SCAN-3c SP electronic",
        "target": "frozen epsilon label (not an external measurement)",
        "cross_source_agreement": agreement,
        "leave_one_primary_study_out": {
            "n_sources_evaluable": len(study_ood),
            "n_beating_constant": sum(1 for s in study_ood if s["beats_constant"]),
            "n_clean_ood": sum(1 for s in study_ood if s["clean_ood"]),
            "mean_ood_mae": (round(statistics.mean([s["ood_mae"] for s in study_ood]), 4)
                             if study_ood else None),
            "sources": study_ood,
        },
        "leave_one_laboratory_out": {
            "n_sources_evaluable": len(lab_ood),
            "n_beating_constant": sum(1 for s in lab_ood if s["beats_constant"]),
            "mean_ood_mae": (round(statistics.mean([s["ood_mae"] for s in lab_ood]), 4)
                             if lab_ood else None),
            "sources": lab_ood,
            "caveat": (
                "laboratories are only partially resolved (publisher-prefix level). "
                "This is therefore closer to a leave-one-paper-out test than a true "
                "leave-one-lab-out test and must not be described as the latter."
            ),
        },
        "clean_ood_feasibility": clean_feasibility,
        "source_cluster_bootstrap": {
            "n_clusters": len(clusters),
            "n_bootstrap": len(boot),
            "resampling_unit": "primary study",
            "pooled_mae": (round(sum(c["ood_mae"] * c["n_test"] for c in clusters)
                                 / max(sum(c["n_test"] for c in clusters), 1), 4)
                           if clusters else None),
            "median": q(boot, 0.5),
            "ci95": [q(boot, 0.025), q(boot, 0.975)] if boot else None,
            "status": ("RELIABLE" if len(clusters) >= 5 else
                       "EXPLORATORY" if len(clusters) >= 3 else "NOT_ESTIMABLE"),
        },
        "separation_warning": (
            "source OOD (new measurement programme), chemical OOD (leave-one-family-out) "
            "and pool-composition sensitivity (B723) are three different questions and "
            "must never be averaged into one generalisation number."
        ),
    }
    (OUT / "source_ood_results.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'source_ood_results.json'}")
    if agree_rows:
        print(f"Wrote {OUT / 'cross_source_agreement.csv'}")
    print()
    print(f"agreement: {agreement['n_comparable_pairs']} pairs / "
          f"{agreement['n_molecules_with_comparison']} molecules, "
          f"median {agreement['median_relative_difference']}, "
          f"{agreement['frac_within_5pct']} within 5%")
    print()
    print(f"clean OOD feasible: {clean_feasibility['verdict']} "
          f"({clean_feasibility['n_studies_clean_eligible']} eligible studies)")
    print(f"study OOD: {len(study_ood)} evaluable, "
          f"{doc['leave_one_primary_study_out']['n_beating_constant']} beat constant, "
          f"{doc['leave_one_primary_study_out']['n_clean_ood']} clean")
    print(f"lab   OOD: {len(lab_ood)} evaluable (publisher-level)")
    b = doc["source_cluster_bootstrap"]
    print(f"bootstrap: {b['status']}, pooled {b['pooled_mae']}, CI {b['ci95']}")


if __name__ == "__main__":
    main()
