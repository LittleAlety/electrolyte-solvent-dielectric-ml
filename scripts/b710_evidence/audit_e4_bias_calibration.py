#!/usr/bin/env python
"""B710-05: audit whether the E4 "bias correction" was legitimate.

v7.0 reported that halocarbon's MAE drops from 5.50 to 1.69 after removing the
family bias. That subtraction used the HELD-OUT family's own labels, so it is a
DIAGNOSTIC DECOMPOSITION, not a demonstrated calibration capability.

This script makes that distinction testable and quantifies the honest version:

  diagnostic      bias removed using the test family's own mean residual (v7.0)
  honest (nested)  the correction is estimated from a K-fold slice of the held-out
                   family only, then applied to the remaining slice
  zero-shot       no calibration at all (the real deployment case)

The nested version is the only one that can be called "calibration capability".
If it does not beat the constant baseline, the v7.0 halocarbon improvement was an
artifact of looking at the answer.

Also quantifies outlier influence for HCN and Triolein:
  - nearest-neighbour distance in standardised descriptor space vs the whole pool
  - how much each molecule alone contributes to its family MAE
  - whether dropping it changes the family-level verdict
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b710_evidence" / "e4_mechanism_audit"
GEN = "audit_e4_mechanism/1.0.0"
SEED = 20261125
K_CAL = 4          # folds for the honest nested calibration
N_REPEAT = 200     # repeated random fold assignments for stability

E4_CSV = REPO_ROOT / "outputs" / "b700" / "B706_E4_family_diagnostics.csv"
LOFO = REPO_ROOT / "outputs" / "b700" / "B706_E4_lofo_predictions.csv"
DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]
X_ELEC = ["dipole_D_v7", "homo_lumo_gap_ev_v7"]


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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    diag = {r["family"]: r for r in load_csv(E4_CSV)}
    lofo = load_csv(LOFO)
    desc = {r["inchikey"]: r for r in load_csv(DESC)}

    by_fam = defaultdict(list)
    for r in lofo:
        by_fam[r["family"]].append(r)

    # ---------------- honest calibration test -------------------------------
    cal_rows = []
    rng = random.Random(SEED)
    for fam, rows in sorted(by_fam.items()):
        y = [fnum(r["epsilon"]) for r in rows]
        p = [fnum(r["lofo_pred"]) for r in rows]
        pairs = [(a, b) for a, b in zip(y, p) if a is not None and b is not None]
        n = len(pairs)
        if n < 4:
            cal_rows.append({
                "family": fam, "n": n,
                "diagnostic_mae_demeaned": None,
                "honest_nested_cal_mae": None,
                "zero_shot_mae": None,
                "constant_baseline_mae": None,
                "honest_beats_constant": None,
                "verdict": "TOO_FEW_FOR_CALIBRATION_TEST",
            })
            continue
        yy = [q[0] for q in pairs]
        pp = [q[1] for q in pairs]
        resid = [pp[i] - yy[i] for i in range(n)]
        mae_zero = statistics.mean(abs(v) for v in resid)
        ybar = statistics.mean(yy)
        const = statistics.mean(abs(v - ybar) for v in yy)
        mae_diag = statistics.mean(abs(v - statistics.mean(resid)) for v in resid)

        # honest: K-fold within the held-out family; calibration offset comes only
        # from the other folds, applied to the fold being scored.
        mae_honest_runs = []
        for _ in range(N_REPEAT):
            idx = list(range(n))
            rng.shuffle(idx)
            folds = [idx[i::K_CAL] for i in range(K_CAL)]
            errs = []
            for f in range(K_CAL):
                te = folds[f]
                tr = [j for g in range(K_CAL) if g != f for j in folds[g]]
                if not tr or not te:
                    continue
                off = statistics.mean(resid[j] for j in tr)
                errs.extend(abs(resid[j] - off) for j in te)
            if errs:
                mae_honest_runs.append(statistics.mean(errs))
        mae_honest = statistics.mean(mae_honest_runs) if mae_honest_runs else None

        cal_rows.append({
            "family": fam, "n": n,
            "zero_shot_mae": round(mae_zero, 4),
            "diagnostic_mae_demeaned": round(mae_diag, 4),
            "honest_nested_cal_mae": round(mae_honest, 4) if mae_honest is not None else None,
            "constant_baseline_mae": round(const, 4),
            "honest_beats_constant": (bool(mae_honest < const) if mae_honest is not None else None),
            "diagnostic_beats_constant": bool(mae_diag < const),
            "verdict": (
                "CALIBRATION_CAPABILITY_SUPPORTED"
                if mae_honest is not None and mae_honest < const
                else "DIAGNOSTIC_ONLY_NOT_CALIBRATION"
            ),
        })

    # ---------------- outlier influence -------------------------------------
    # standardised descriptor space NN distance, pool = all 239
    pool = []
    for ik, d in desc.items():
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
        if ok:
            pool.append((ik, xs))
    means = [statistics.mean([p[1][j] for p in pool]) for j in range(len(pool[0][1]))]
    sds = [statistics.pstdev([p[1][j] for p in pool]) or 1.0 for j in range(len(pool[0][1]))]
    Z = {ik: [(xs[j] - means[j]) / sds[j] for j in range(len(xs))] for ik, xs in pool}

    def nn_dist(ik):
        if ik not in Z:
            return None
        z = Z[ik]
        best = float("inf")
        for other, zo in Z.items():
            if other == ik:
                continue
            dd = math.sqrt(sum((z[j] - zo[j]) ** 2 for j in range(len(z))))
            best = min(best, dd)
        return best

    # pool NN-distance distribution for a reference percentile
    all_nn = [nn_dist(ik) for ik in Z]
    all_nn = sorted(v for v in all_nn if v is not None)

    targets = []
    for fam, rows in by_fam.items():
        for r in rows:
            t = fnum(r["epsilon"])
            pr = fnum(r["lofo_pred"])
            if t is None or pr is None:
                continue
            targets.append((fam, r, abs(pr - t)))
    targets.sort(key=lambda x: -x[2])

    outlier_rows = []
    for fam, r, ae in targets[:8]:
        ik = r["inchikey"]
        dd = nn_dist(ik)
        pct = (sum(1 for v in all_nn if v <= dd) / len(all_nn) * 100) if (dd is not None and all_nn) else None
        fam_rows = by_fam[fam]
        ys = [fnum(x["epsilon"]) for x in fam_rows]
        ps = [fnum(x["lofo_pred"]) for x in fam_rows]
        prs = [(a, b) for a, b in zip(ys, ps) if a is not None and b is not None]
        errs = [abs(b - a) for a, b in prs]
        mae_all = statistics.mean(errs)
        mae_wo = statistics.mean(sorted(errs, reverse=True)[1:]) if len(errs) > 1 else None
        outlier_rows.append({
            "family": fam,
            "name": r["name"],
            "inchikey": ik,
            "epsilon_true": t if (t := fnum(r["epsilon"])) is not None else None,
            "epsilon_pred": fnum(r["lofo_pred"]),
            "abs_error": round(ae, 3),
            "family_mae_with": round(mae_all, 4),
            "family_mae_without": round(mae_wo, 4) if mae_wo is not None else None,
            "family_mae_share_of_this_point": round(ae / (mae_all * len(errs)), 4) if mae_all else None,
            "nn_distance_standardised": round(dd, 4) if dd is not None else None,
            "nn_percentile_in_pool": round(pct, 1) if pct is not None else None,
        })

    doc = {
        "schema": "b710.e4_mechanism_audit/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_repeat_calibration": N_REPEAT,
        "k_calibration_folds": K_CAL,
        "calibration_audit": {
            "method": (
                "diagnostic = subtract the held-out family's own mean residual "
                "(v7.0; uses test labels). honest = estimate the offset from K-1 folds "
                "of the held-out family and apply to the remaining fold, repeated "
                f"{N_REPEAT} times. Only 'honest' can be called calibration capability."
            ),
            "families": cal_rows,
            "n_calibration_supported": sum(1 for r in cal_rows
                                           if r["verdict"] == "CALIBRATION_CAPABILITY_SUPPORTED"),
            "n_diagnostic_only": sum(1 for r in cal_rows
                                     if r["verdict"] == "DIAGNOSTIC_ONLY_NOT_CALIBRATION"),
            "n_too_few": sum(1 for r in cal_rows
                             if r["verdict"] == "TOO_FEW_FOR_CALIBRATION_TEST"),
        },
        "outlier_influence": {
            "reference": "nearest-neighbour distance in standardised X0+electronic space over all 239",
            "top_abs_error_molecules": outlier_rows,
            "note": (
                "dropping a molecule is a SENSITIVITY DIAGNOSTIC only; every headline "
                "metric keeps all legal samples"
            ),
        },
    }
    (OUT / "e4_mechanism_audit.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    with (OUT / "e4_calibration_audit.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(cal_rows[0].keys()))
        w.writeheader()
        w.writerows(cal_rows)

    with (OUT / "e4_outlier_influence.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(outlier_rows[0].keys()))
        w.writeheader()
        w.writerows(outlier_rows)

    print(f"Wrote {OUT / 'e4_mechanism_audit.json'}")
    print(f"Wrote {OUT / 'e4_calibration_audit.csv'}")
    print(f"Wrote {OUT / 'e4_outlier_influence.csv'}")
    print()
    print(f"{'family':24s} {'n':>3s} {'zero':>7s} {'diag':>7s} {'honest':>7s} {'const':>7s} verdict")
    for r in cal_rows:
        h = f"{r['honest_nested_cal_mae']:7.3f}" if r["honest_nested_cal_mae"] is not None else "    n/a"
        z = f"{r['zero_shot_mae']:7.3f}" if r["zero_shot_mae"] is not None else "    n/a"
        d = f"{r['diagnostic_mae_demeaned']:7.3f}" if r["diagnostic_mae_demeaned"] is not None else "    n/a"
        c = f"{r['constant_baseline_mae']:7.3f}" if r["constant_baseline_mae"] is not None else "    n/a"
        print(f"{r['family']:24s} {r['n']:3d} {z} {d} {h} {c} {r['verdict']}")
    print()
    print("top absolute-error molecules:")
    for r in outlier_rows[:5]:
        print(f"  {r['family']:22s} {r['name'][:30]:30s} |err|={r['abs_error']:7.2f} "
              f"share={r['family_mae_share_of_this_point']} "
              f"NN pct={r['nn_percentile_in_pool']}")


if __name__ == "__main__":
    main()
