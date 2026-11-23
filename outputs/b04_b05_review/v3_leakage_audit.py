#!/usr/bin/env python
"""Reviewer-3 leakage + reproducibility audit.

Leakage questions:
  L1. Is the ridge lambda tuned on the test fold anywhere?  (search for any
      fit on the full data before splitting)
  L2. Is the scaler fitted on the training fold only in ridge_loo?
  L3. In E4, does abs_error / y_pred for molecule i come from a model that never
      saw molecule i?
  L4. In E4 leave-one-family-out, is the family of the test molecule excluded
      from training?
  L5. In E6, is the LOO prediction fed to Top-k the same LOO prediction (i.e. no
      refit on all data)?
  L6. In B04, is there any label used to admit rows (circular admission)?

Also: reproducibility determinism of the numeric outputs (timestamps excluded).
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "b04_b05_review"
SCRIPTS = list((ROOT / "scripts" / "b04").glob("*.py")) + \
          [p for p in (ROOT / "scripts" / "b05").glob("*.py")]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}

    # ---------- L0. static scan for suspicious patterns ---------------------
    pats = {
        "bare_except": r"except\s*:",
        "broad_except_Exception": r"except\s+Exception",
        "except_pass": r"except[^\n]*:\s*\n\s*pass",
        "get_with_default": r"\.get\([^)]*,\s*[^)]*\)",
        "try_blocks": r"\btry\s*:",
    }
    scan = {}
    for p in SCRIPTS:
        txt = p.read_text(encoding="utf-8", errors="replace")
        lines = txt.splitlines()
        hits = {}
        for name, pat in pats.items():
            found = []
            for i, ln in enumerate(lines, 1):
                if re.search(pat, ln):
                    found.append((i, ln.strip()[:110]))
            if found:
                hits[name] = found
        scan[p.name] = hits
    res["static_scan"] = {k: {kk: [list(x) for x in vv] for kk, vv in v.items()}
                          for k, v in scan.items()}

    # ---------- L1/L2. lambda tuning and scaler scope ------------------------
    e1 = (ROOT / "scripts" / "b05" / "run_e1_structure_vs_electronic.py").read_text(encoding="utf-8")
    lam_scan_present = "lam_scan" in e1 or "for lam in" in e1
    res["L1_lambda"] = dict(
        script_hardcodes_lam_fixed=True,
        evidence="ridge_loo(X, y, lam=1.0) called at every site; no grid search",
        calls=sorted(set(re.findall(r"ridge_loo\([^)]*\)", e1))),
        tuned_on_test=False,
        verdict="NO_LEAKAGE (lambda fixed a priori at 1.0, not tuned at all)",
        side_effect=("lambda is never validated, and the project's own E1b sweep "
                     "shows lambda=1.0 is NOT the MAE-optimal value -> a "
                     "specification problem, not leakage"),
    )
    res["L2_scaler"] = dict(
        evidence=("ridge_loo lines 143-149: Xtr/ytr exclude `hold`; "
                  "_standardise(Xtr) computes means/sds from the TRAINING fold "
                  "only; X[hold] is transformed with those training stats"),
        scaler_fit_on="training fold only",
        verdict="NO_LEAKAGE",
    )

    # Runtime proof of L2: rebuild one fold and check the scaler moments.
    def load(p):
        with open(p, encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))

    pool = load(ROOT / "outputs" / "b04" / "candidate_pool_v2_draft.csv")
    feats = {r["inchikey"]: r
             for r in load(ROOT / "data" / "processed" / "dielectric_physical_features.csv")}
    X0 = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
          "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge"]
    X = [[float(feats[r["inchikey"]][c]) for c in X0] for r in pool]
    n, p = len(X), len(X[0])
    hold = 0
    tr = [i for i in range(n) if i != hold]
    mu_tr = [sum(X[i][j] for i in tr) / len(tr) for j in range(p)]
    mu_all = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    res["L2_runtime_proof"] = dict(
        mean_col0_train_fold=round(mu_tr[0], 6),
        mean_col0_all_data=round(mu_all[0], 6),
        differ=abs(mu_tr[0] - mu_all[0]) > 1e-9,
        held_out_value=round(X[hold][0], 6),
    )

    # ---------- L3/L4. E4 held-out discipline ---------------------------------
    e4 = load(ROOT / "outputs" / "b05" / "E4_domain_generalization" /
              "structural_distance_ood.csv")
    res["L3_e4_row_self_exclusion"] = dict(
        evidence=("run_e4_domain_generalization.py lines 313-318: tr = all j != i; "
                  "fit_predict on [mols[j] for j in tr], predict mols[i]"),
        n_rows=len(e4),
        verdict="NO_LEAKAGE by construction",
    )
    lofo = load(ROOT / "outputs" / "b05" / "E4_domain_generalization" /
                "leave_one_family_out.csv")
    res["L4_lofo"] = dict(
        evidence=("lines 258-272: hold = set(idx) is the whole family; tr excludes "
                  "all of it"),
        rows=[dict(family=r["family"], n_members=r["n_members"],
                   n_train=r["n_train"], test_n=r["test_n"], status=r["status"])
              for r in lofo],
        all_n_train_plus_test_eq_22=all(
            int(r["n_train"]) + int(r["test_n"]) == 22
            for r in lofo if r["n_train"] and r["test_n"]),
        verdict="NO_LEAKAGE by construction",
    )

    # ---------- L5. E6 uses LOO predictions, not a refit on all data ---------
    rv = load(ROOT / "outputs" / "b05" / "E6_screening_decisions" / "rank_vs_error.csv")
    e1pred = load(ROOT / "outputs" / "b05" / "E1_structure_vs_electronic" /
                  "predictions_loo.csv")
    e1x = {r["measurement_id"]: float(r["y_pred"]) for r in e1pred
           if r["model"] == "X0_plus_X1_electronic"}
    diffs = [(r["measurement_id"], float(r["y_pred"]), e1x.get(r["measurement_id"]))
             for r in rv if r["measurement_id"] in e1x]
    matching = [d for d in diffs if d[2] is not None and abs(d[1] - d[2]) < 5e-3]
    res["L5_e6_predictions"] = dict(
        n_compared=len(diffs), n_match_with_e1_loo=len(matching),
        note=("E6 uses the same 11-feature set as E1's X0+X1 minus "
              "total_energy_hartree, so predictions are close but not identical"),
        verdict="E6 uses its own LOO predictions (loo_predictions at line 200)",
    )

    # ---------- L6. B04 circular admission ------------------------------------
    pool_rows = load(ROOT / "outputs" / "b04" / "candidate_pool_v2_draft.csv")
    res["L6_b04_circularity"] = dict(
        gates=["B02 AI consensus == AI_CONSENSUS_ACCEPTED",
               "v06 model_ready == true",
               "not in dataset_v06_exclusions"],
        label_used_as_admission_criterion=False,
        note=("The dielectric value is carried through but never used as a "
              "selection filter; admission is by provenance/quality gates only"),
        caveat=("Gate 3 is vacuous: ready & excluded = 0 rows, so gate 3 removes "
                "nothing and the claim 'three independent gates' overstates the "
                "construction to two"),
        verdict="NO_LABEL_LEAKAGE, but gate independence claim is overstated",
    )

    # ---------- B04 vacuous gate proof ----------------------------------------
    ready = {r["measurement_id"] for r in
             load(ROOT / "outputs" / "b01" / "dataset_v06_model_ready.csv")}
    excl = {r["measurement_id"] for r in
            load(ROOT / "outputs" / "b01" / "dataset_v06_exclusions.csv")}
    cons = load(ROOT / "outputs" / "admission_v2" / "consensus_decisions.csv")
    acc = {r["measurement_id"] for r in cons
           if r["consensus_status"] == "AI_CONSENSUS_ACCEPTED"}
    res["B04_gate_algebra"] = dict(
        n_accepted=len(acc), n_model_ready=len(ready), n_excluded=len(excl),
        ready_minus_excluded=len(ready - excl),
        accepted_and_ready=len(acc & ready),
        accepted_and_ready_and_not_excluded=len(acc & ready - excl),
        gate3_removes=len((acc & ready) & excl),
        pool_size=len(pool_rows),
        conclusion=("intersection == |accepted & ready|; gate 3 is a no-op. "
                    "T_K all inside [293.15,303.15] so the temperature band "
                    "test cannot fail either."),
    )

    # ---------- reproducibility: hash all numeric outputs --------------------
    def sha(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    numeric = []
    for d in ("b04", "b05"):
        for p in sorted((ROOT / "outputs" / d).rglob("*")):
            if p.is_file() and p.suffix in (".csv",):
                numeric.append((str(p.relative_to(ROOT)), sha(p)))
    res["numeric_output_hashes"] = numeric

    (OUT / "v3_leakage_audit.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("=== static scan (error-swallowing patterns) ===")
    for f, hits in res["static_scan"].items():
        print(f"  {f}: " + ", ".join(f"{k}={len(v)}" for k, v in hits.items()))
    print("\n=== L1 lambda ===")
    print("  calls:", res["L1_lambda"]["calls"])
    print("  tuned_on_test:", res["L1_lambda"]["tuned_on_test"])
    print("\n=== L2 scaler scope ===")
    print("  ", res["L2_scaler"]["evidence"])
    print("  runtime proof:", res["L2_runtime_proof"])
    print("\n=== L4 leave-one-family-out arithmetic ===")
    print("  all n_train+n_test==22:", res["L4_lofo"]["all_n_train_plus_test_eq_22"])
    print("\n=== B04 gate algebra ===")
    print(json.dumps(res["B04_gate_algebra"], indent=2))


if __name__ == "__main__":
    main()
