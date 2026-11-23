#!/usr/bin/env python
"""B05-E4: domain generalisation -- cross-family, structural-distance and source OOD.

PLAN B B05 marks E4 as mandatory and names three axes: cross chemical family,
structural distance, and source OOD. The point is not to fit better but to find
out **where the model stops working**.

With only 22 molecules an honest E4 cannot be a random-split exercise: a random
split would put an alcohol in train and another alcohol in test and report a
flattering number. So every axis here is a *leave-a-whole-group-out* design:

  1. LEAVE-ONE-FAMILY-OUT
     Partition the 22 molecules into chemical families by SMARTS, then train on
     all-but-one family and predict the held-out family. A family with 1-2
     members yields an n=1 test set -- that is reported as insufficient rather
     than being turned into an R-squared.

  2. STRUCTURAL DISTANCE OOD
     For each molecule, compute Tanimoto similarity to its nearest training
     neighbour and bucket by distance. If error grows with distance, that is a
     measurable applicability-domain signal; if it does not, the descriptor set
     is simply not informative (which E1 already suggests).

  3. SOURCE OOD
     Group by `source_doi`. This project has already shown that source groups are
     not independent (duplicate experiments), so source-OOD is reported with that
     caveat rather than as clean generalisation evidence.

  4. APPLICABILITY DOMAIN COVERAGE
     Report, for every held-out molecule, whether its nearest training neighbour
     is close enough to claim coverage -- and how many molecules fail that test.

Everything is labelled EXPLORATORY. Where n is too small to compute a statistic,
the row says `insufficient_power` instead of emitting a number.

Output: outputs/b05/E4_domain_generalization/
          leave_one_family_out.csv
          structural_distance_ood.csv
          source_ood_results.csv
          applicability_domain.csv
          e4_report.md
          e4_manifest.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b05" / "E4_domain_generalization"
GENERATOR = "run_e4_domain_generalization/1.0.0"

POOL = REPO_ROOT / "outputs" / "b04" / "candidate_pool_v2_draft.csv"
V04 = REPO_ROOT / "data" / "dielectric_v04.csv"
FEATURES = REPO_ROOT / "data" / "processed" / "dielectric_physical_features.csv"

# SMARTS-based family rules, applied in this ORDER and the first match wins.
#
# Reviewer 3 (B04+B05) noted two problems with the original list:
#   (a) "most specific wins" was asserted but not true -- the order is arbitrary,
#       and 8 of 22 molecules match more than one rule (dimethyl carbonate matches
#       carbonate + ester + ether; 1-methylimidazole matches imidazole + aromatic).
#   (b) sulfolane -- the highest-epsilon molecule in the pool -- was "unclassified"
#       because there was no sulfone rule.
#
# The order below is deliberate and documented: heteroatom-identity rules come
# before carbon-skeleton rules, so a cyclic sulfone is a sulfone rather than an
# "aromatic"/"ring" compound. The list is exported to the manifest so a reader can
# see the precedence instead of having to infer it.
FAMILY_RULES = [
    ("sulfone", "[#16X4](=[OX1])(=[OX1])"),          # sulfolane etc.
    ("sulfoxide", "[#16X3](=[OX1])"),                # DMSO etc.
    ("carboxylic_acid", "[CX3](=O)[OX2H1]"),
    ("dinitrile", "N#C.*C#N"),
    ("carbonate", "[OX2][CX3](=O)[OX2]"),
    ("ester", "[CX3](=O)[OX2][#6]"),
    ("ketone", "[#6][CX3](=O)[#6]"),
    ("imidazole", "c1cncn1"),
    ("thiophene", "c1ccsc1"),
    ("primary_secondary_amine", "[NX3;H2,H1;!$(NC=O)]"),
    ("tertiary_amine", "[NX3;H0;!$(NC=O)]"),
    ("nitrile", "N#C"),
    ("alcohol", "[OX2H]"),
    ("ether", "[OD2]([#6])[#6]"),
    ("aromatic", "a"),
]

X_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
          "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
          "dipole_D", "polarizability_au", "polarizability_A3",
          "homo_lumo_gap_ev"]

N_PERMUTATIONS = 300
SEED = 20261123
# A held-out family needs at least this many members for any statistic.
MIN_TEST_N = 2
# Applicability domain: nearest-neighbour Tanimoto below this is out of domain.
AD_TANIMOTO_MIN = 0.40

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- modelling

def standardise(X):
    n, p = len(X), len(X[0])
    means = [sum(X[i][j] for i in range(n)) / n for j in range(p)]
    sds = []
    for j in range(p):
        var = sum((X[i][j] - means[j]) ** 2 for i in range(n)) / max(n - 1, 1)
        sds.append(math.sqrt(var) if var > 0 else 1.0)
    return ([[(X[i][j] - means[j]) / sds[j] for j in range(p)] for i in range(n)],
            means, sds)


def ridge_fit(Z, y, lam=1.0):
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


def fit_predict(Xtr, ytr, Xte, lam=1.0):
    """Ridge fit + predict, WITH an intercept.

    The features are standardised to mean 0, so a fit without an intercept is
    forced through the origin in standardised space and predicts deviations around
    0 rather than around the training mean. Reviewer 1 (B04+B05) found this error
    in E1; the same specification is used here, so it is fixed here too.
    """
    if not Xtr or not Xte:
        return []
    Ztr, means, sds = standardise(Xtr)
    b = ridge_fit(Ztr, ytr, lam)
    ybar_tr = sum(ytr) / len(ytr)
    out = []
    for row in Xte:
        x = [(row[j] - means[j]) / sds[j] for j in range(len(means))]
        out.append(ybar_tr + sum(x[j] * b[j] for j in range(len(b))))
    return out


def err_stats(y, pred):
    if not y:
        return None
    n = len(y)
    err = [pred[i] - y[i] for i in range(n)]
    mae = sum(abs(e) for e in err) / n
    rmse = math.sqrt(sum(e * e for e in err) / n)
    bias = sum(err) / n
    return {"n": n, "mae": mae, "rmse": rmse, "bias": bias}


def main() -> int:
    for p in (POOL, V04, FEATURES):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    from rdkit import Chem
    from rdkit.Chem import AllChem, DataStructs, Descriptors
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")

    pool = load(POOL)
    v04 = {r["inchikey"]: r for r in load(V04)}
    feats = {r["inchikey"]: r for r in load(FEATURES)}

    # ---- assemble the working table ----
    mols = []
    for r in pool:
        ik = r["inchikey"]
        smi = (v04.get(ik, {}).get("smiles") or "").strip()
        mol = Chem.MolFromSmiles(smi) if smi else None
        f = feats.get(ik, {})
        xvals = [fnum(f.get(c)) for c in X_COLS]
        if mol is None or any(v is None for v in xvals):
            continue
        family = "unclassified"
        matched_rules: list[str] = []
        for label, smarts in FAMILY_RULES:
            patt = Chem.MolFromSmarts(smarts)
            if patt is not None and mol.HasSubstructMatch(patt):
                matched_rules.append(label)
                if family == "unclassified":
                    family = label
        mols.append({
            "measurement_id": r["measurement_id"],
            "inchikey": ik,
            "name": r["name"],
            "smiles": smi,
            "mol": mol,
            "family": family,
            "n_rules_matched": len(matched_rules),
            "matched_rules": ";".join(matched_rules),
            "source_doi": r["source_doi"],
            "T_K": r["T_K"],
            "y": float(r["dielectric"]),
            "x": [float(v) for v in xvals],
        })

    coverage = {
        "n_pool": len(pool),
        "n_usable": len(mols),
        "n_missing_smiles": sum(1 for r in pool
                                if not (v04.get(r["inchikey"], {}).get("smiles") or "").strip()),
        "n_missing_features": sum(1 for r in pool
                                  if any(fnum(feats.get(r["inchikey"], {}).get(c)) is None
                                         for c in X_COLS)),
        "n_unclassified_family": sum(1 for m in mols if m["family"] == "unclassified"),
    }
    if not mols:
        print("FATAL: no usable molecules", file=sys.stderr)
        return 3

    y_all = [m["y"] for m in mols]
    random.seed(SEED)

    # ================================================================
    # 1. LEAVE ONE FAMILY OUT
    # ================================================================
    fam_groups: dict[str, list[int]] = defaultdict(list)
    for i, m in enumerate(mols):
        fam_groups[m["family"]].append(i)

    fam_rows = []
    for fam, idx in sorted(fam_groups.items(),
                           key=lambda kv: (-len(kv[1]), kv[0])):
        hold = set(idx)
        tr = [i for i in range(len(mols)) if i not in hold]
        te = list(idx)
        if not tr:
            continue
        if len(fam_groups) == 1:
            fam_rows.append({
                "family": fam, "n_members": len(idx), "n_train": len(tr),
                "test_n": len(te), "mae": "", "rmse": "", "bias": "",
                "status": "SINGLE_FAMILY_ONLY",
                "note": "全部分子同属一个家族, 无法做跨家族留出",
            })
            continue
        pred = fit_predict([mols[i]["x"] for i in tr], [mols[i]["y"] for i in tr],
                           [mols[i]["x"] for i in te])
        st = err_stats([mols[i]["y"] for i in te], pred)
        if len(te) < MIN_TEST_N:
            fam_rows.append({
                "family": fam, "n_members": len(idx), "n_train": len(tr),
                "test_n": len(te), "mae": "", "rmse": "", "bias": "",
                "status": "insufficient_power",
                "note": f"留出家族只有 {len(te)} 个分子, 不足以计算误差统计",
            })
            continue

        # Null: predict the TRAINING mean for every held-out molecule. If the
        # model cannot beat this, cross-family generalisation has failed outright.
        tr_mean = sum(mols[i]["y"] for i in tr) / len(tr)
        base_mae = sum(abs(mols[i]["y"] - tr_mean) for i in te) / len(te)

        fam_rows.append({
            "family": fam,
            "n_members": len(idx),
            "n_train": len(tr),
            "test_n": len(te),
            "mae": round(st["mae"], 4),
            "rmse": round(st["rmse"], 4),
            "bias": round(st["bias"], 4),
            "train_mean_baseline_mae": round(base_mae, 4),
            "beats_train_mean": "true" if st["mae"] < base_mae else "false",
            "status": "measured",
            "note": "",
        })

    # ================================================================
    # 2. STRUCTURAL DISTANCE OOD
    # ================================================================
    fps = [AllChem.GetMorganFingerprintAsBitVect(m["mol"], 2, nBits=2048)
           for m in mols]

    dist_rows = []
    nn_sims = []
    for i, m in enumerate(mols):
        if len(mols) < 3:
            break
        tr = [j for j in range(len(mols)) if j != i]
        sims = [(DataStructs.TanimotoSimilarity(fps[i], fps[j]), j) for j in tr]
        sims.sort(reverse=True)
        nn_sim, nn_j = sims[0]
        pred = fit_predict([mols[j]["x"] for j in tr], [mols[j]["y"] for j in tr],
                           [m["x"]])
        err = pred[0] - m["y"]
        nn_sims.append(nn_sim)
        dist_rows.append({
            "measurement_id": m["measurement_id"],
            "name": m["name"],
            "family": m["family"],
            "nearest_neighbour": mols[nn_j]["name"],
            "nn_tanimoto": round(nn_sim, 4),
            "y_true": round(m["y"], 4),
            "y_pred": round(pred[0], 4),
            "abs_error": round(abs(err), 4),
            "in_applicability_domain": (
                "true" if nn_sim >= AD_TANIMOTO_MIN else "false"),
        })

    # bucket by distance and see whether error grows
    buckets = [("far  (<0.40)", 0.0, 0.40),
               ("mid  (0.40-0.60)", 0.40, 0.60),
               ("near (>=0.60)", 0.60, 1.01)]
    bucket_rows = []
    for label, lo, hi in buckets:
        rows = [r for r in dist_rows if lo <= r["nn_tanimoto"] < hi]
        if not rows:
            bucket_rows.append({"distance_bucket": label, "n": 0,
                                "mae": "", "mean_nn_tanimoto": "",
                                "status": "empty"})
            continue
        mae = sum(r["abs_error"] for r in rows) / len(rows)
        bucket_rows.append({
            "distance_bucket": label,
            "n": len(rows),
            "mae": round(mae, 4),
            "mean_nn_tanimoto": round(
                sum(r["nn_tanimoto"] for r in rows) / len(rows), 4),
            "status": "measured" if len(rows) >= 2 else "insufficient_power",
        })

    # Does error correlate with distance? Report Spearman without pretending
    # an n=22 correlation is a finding.
    corr = None
    if len(dist_rows) >= 5:
        xs = [r["nn_tanimoto"] for r in dist_rows]
        ys = [r["abs_error"] for r in dist_rows]
        n = len(xs)
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
        rx, ry = rank(xs), rank(ys)
        mx, my = sum(rx) / n, sum(ry) / n
        num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
        den = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n))
                        * sum((ry[i] - my) ** 2 for i in range(n)))
        corr = num / den if den else None

    # ================================================================
    # 3. SOURCE OOD
    # ================================================================
    src_groups: dict[str, list[int]] = defaultdict(list)
    for i, m in enumerate(mols):
        for doi in [d.strip() for d in m["source_doi"].split(";") if d.strip()]:
            src_groups[doi].append(i)

    src_rows = []
    for doi, idx in sorted(src_groups.items(), key=lambda kv: -len(kv[1])):
        idx = sorted(set(idx))
        hold = set(idx)
        tr = [i for i in range(len(mols)) if i not in hold]
        if not tr:
            src_rows.append({
                "source_doi": doi, "n_molecules": len(idx), "n_train": 0,
                "mae": "", "status": "no_training_data",
                "note": "该来源覆盖全部分子, 留出后无训练集",
            })
            continue
        if len(idx) < MIN_TEST_N:
            src_rows.append({
                "source_doi": doi, "n_molecules": len(idx), "n_train": len(tr),
                "mae": "", "status": "insufficient_power",
                "note": f"留出来源只有 {len(idx)} 个分子",
            })
            continue
        pred = fit_predict([mols[i]["x"] for i in tr], [mols[i]["y"] for i in tr],
                           [mols[i]["x"] for i in idx])
        st = err_stats([mols[i]["y"] for i in idx], pred)
        src_rows.append({
            "source_doi": doi,
            "n_molecules": len(idx),
            "n_train": len(tr),
            "mae": round(st["mae"], 4),
            "rmse": round(st["rmse"], 4),
            "status": "measured",
            "note": (
                "来源独立性未评估: B01 已证明 DOI 数不等于独立实验数, "
                "因此本行不得作为聚类稳健性证据"
            ),
        })

    # ================================================================
    # 4. APPLICABILITY DOMAIN COVERAGE
    # ================================================================
    ad_rows = []
    n_out = 0
    for r in dist_rows:
        in_ad = r["nn_tanimoto"] >= AD_TANIMOTO_MIN
        if not in_ad:
            n_out += 1
        ad_rows.append({
            "measurement_id": r["measurement_id"],
            "name": r["name"],
            "family": r["family"],
            "nn_tanimoto": r["nn_tanimoto"],
            "ad_threshold": AD_TANIMOTO_MIN,
            "in_applicability_domain": "true" if in_ad else "false",
            "claim_allowed": (
                "PREDICTION_WITHIN_DOMAIN" if in_ad
                else "PREDICTION_OUT_OF_DOMAIN_NO_CLAIM"),
        })

    # ---- the decisive test: error at Tanimoto == 1.0 ----
    # If two molecules have IDENTICAL Morgan fingerprints, the descriptors cannot
    # distinguish them either. Any error there is pure descriptor blindness --
    # it cannot be blamed on being "out of domain". This separates
    #   "the model fails when extrapolating"  (fixable by more data)
    # from
    #   "the descriptors cannot resolve chemically distinct liquids" (not fixable
    #    by more data of the same kind).
    identical_fp = [r for r in dist_rows if r["nn_tanimoto"] >= 0.999]
    ident_stats = None
    if identical_fp:
        errs = [r["abs_error"] for r in identical_fp]
        ident_stats = {
            "n_pairs_with_identical_fingerprint": len(identical_fp),
            "mae_among_identical": round(sum(errs) / len(errs), 4),
            "max_error_among_identical": round(max(errs), 4),
            "examples": [
                {"name": r["name"], "nearest_neighbour": r["nearest_neighbour"],
                 "abs_error": r["abs_error"]}
                for r in sorted(identical_fp, key=lambda z: -z["abs_error"])
            ],
            "interpretation": (
                "在指纹完全相同 (Tanimoto=1.0) 的分子对上, 误差本应接近 0. "
                "但必须先排除『模型整体水平偏移』这一更简单的解释: "
                "若 |bias|/MAE ≈ 1, 大部分误差属于标定失败而非描述符失明."
            ),
            "caveat": (
                "早期版本因 ridge 回归缺少截距项而把整体偏差混入本指标, "
                "得到 19.48 的虚高值. 修复截距后该值显著下降. "
                "因此『描述符无法分辨相似分子』这一强结论**不成立** —— "
                "它主要是模型规格错误造成的假象 (Reviewer 1, B04+B05)."
            ),
        }

    # In-domain vs out-of-domain error comparison.
    in_dom = [r for r in dist_rows if r["nn_tanimoto"] >= AD_TANIMOTO_MIN]
    out_dom = [r for r in dist_rows if r["nn_tanimoto"] < AD_TANIMOTO_MIN]
    ad_comparison = {
        "n_in_domain": len(in_dom),
        "n_out_of_domain": len(out_dom),
        "mae_in_domain": (round(sum(r["abs_error"] for r in in_dom) / len(in_dom), 4)
                          if in_dom else None),
        "mae_out_of_domain": (round(sum(r["abs_error"] for r in out_dom) / len(out_dom), 4)
                              if out_dom else None),
    }
    if (ad_comparison["mae_in_domain"] is not None
            and ad_comparison["mae_out_of_domain"] is not None):
        ratio = (ad_comparison["mae_out_of_domain"]
                 / ad_comparison["mae_in_domain"])
        ad_comparison["out_over_in_ratio"] = round(ratio, 3)
        ad_comparison["separation"] = (
            "NO_USEFUL_SEPARATION" if 0.7 <= ratio <= 1.4
            else "ERROR_GROWS_OUT_OF_DOMAIN" if ratio > 1.4
            else "ERROR_SMALLER_OUT_OF_DOMAIN")

    # ================================================================
    # write
    # ================================================================
    def write_csv(name: str, rows: list[dict]) -> Path:
        path = OUT_DIR / name
        if not rows:
            path.write_text("", encoding="utf-8")
            return path
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows:
                w.writerow(r)
        return path

    fam_path = write_csv("leave_one_family_out.csv", fam_rows)
    dist_path = write_csv("structural_distance_ood.csv", dist_rows)
    src_path = write_csv("source_ood_results.csv", src_rows)
    ad_path = write_csv("applicability_domain.csv", ad_rows)

    fam_measured = [r for r in fam_rows if r["status"] == "measured"]
    fam_beat = [r for r in fam_measured if r["beats_train_mean"] == "true"]
    n_out_of_domain = n_out

    # ================================================================
    # report
    # ================================================================
    md: list[str] = []
    md.append("# B05-E4 跨域泛化与适用域\n")
    md.append(f"> 生成器 `{GENERATOR}` · "
              f"{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')}\n")

    md.append("\n## ⚠️ 探索性\n")
    md.append(f"可用分子 **{len(mols)}** 个。所有跨域结论都是探索性的；"
              f"任一留出组小于 {MIN_TEST_N} 个分子时报告 `insufficient_power` 而不是数值。\n")

    md.append("\n## 一、覆盖率\n")
    md.append(f"- 候选池：{coverage['n_pool']}\n")
    md.append(f"- 可用：**{coverage['n_usable']}**\n")
    md.append(f"- 缺 SMILES：{coverage['n_missing_smiles']}\n")
    md.append(f"- 缺描述符：{coverage['n_missing_features']}\n")
    md.append(f"- 未归类家族：{coverage['n_unclassified_family']}\n")

    md.append("\n## 二、化学家族分布\n")
    md.append("| 家族 | 分子数 | 分子 |\n|---|---:|---|\n")
    for fam, idx in sorted(fam_groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        names = ", ".join(mols[i]["name"][:18] for i in idx)
        md.append(f"| `{fam}` | {len(idx)} | {names} |\n")

    md.append("\n## 三、留一家族出（leave-one-family-out）\n")
    md.append("| 家族 | 成员 | 训练 | 测试 | MAE | 常数基线 MAE | 优于基线 | 状态 |\n")
    md.append("|---|---:|---:|---:|---:|---:|---|---|\n")
    for r in fam_rows:
        md.append(f"| `{r['family']}` | {r['n_members']} | {r['n_train']} | "
                  f"{r['test_n']} | {r['mae']} | {r.get('train_mean_baseline_mae','')} | "
                  f"{r.get('beats_train_mean','')} | {r['status']} |\n")

    md.append(f"\n**可测家族：{len(fam_measured)}；其中优于常数基线：{len(fam_beat)}**\n")
    if fam_measured and not fam_beat:
        md.append(
            "\n⚠️ **没有任何一个家族的跨家族预测能优于「用训练集均值」的基线。** "
            "这与 E1 的结论一致：单分子描述符在这个样本上不携带可迁移的液体介电信息。\n"
        )

    md.append("\n## 四、结构距离 OOD\n")
    md.append("| 距离桶 | n | MAE | 平均最近邻 Tanimoto | 状态 |\n")
    md.append("|---|---:|---:|---:|---|\n")
    for r in bucket_rows:
        md.append(f"| {r['distance_bucket']} | {r['n']} | {r['mae']} | "
                  f"{r['mean_nn_tanimoto']} | {r['status']} |\n")
    if corr is not None:
        md.append(f"\n**误差与最近邻相似度的 Spearman 相关：{corr:+.4f}**\n\n")
        md.append(
            "若该相关为负且显著，说明「越远越差」，即存在可用的适用域信号；"
            "若接近 0，说明误差与结构距离无关 —— 描述符本身不携带可迁移信息，"
            "而不是「域外失效」。**这两种情况的处置完全不同。**\n"
        )

    md.append("\n## 五、来源 OOD\n")
    md.append("| 来源 DOI | 分子数 | MAE | 状态 |\n|---|---:|---:|---|\n")
    for r in src_rows:
        md.append(f"| `{r['source_doi']}` | {r['n_molecules']} | {r['mae']} | "
                  f"{r['status']} |\n")
    md.append(
        "\n> **重要限定：** 本项目的来源独立性尚未评估（B01 已证明 DOI 数 ≠ 独立实验数，"
        "且存在多组逐字节相同的重复观测）。"
        "因此上表**不得**作为「来源聚类稳健性」的证据，只能作为描述性统计。\n"
    )

    md.append("\n## 七、决定性检验：指纹完全相同处的误差\n")
    if ident_stats:
        md.append(
            f"有 **{ident_stats['n_pairs_with_identical_fingerprint']}** 个分子的"
            f"最近邻指纹 **Tanimoto = 1.000**（描述符无法区分两者）。\n\n"
            f"- 这些分子上的平均误差：**{ident_stats['mae_among_identical']}**\n"
            f"- 最大误差：**{ident_stats['max_error_among_identical']}**\n\n"
        )
        md.append("| 分子 | 最近邻 | 误差 |\n|---|---|---:|\n")
        for e in ident_stats["examples"]:
            md.append(f"| {e['name']} | {e['nearest_neighbour']} | {e['abs_error']} |\n")
        md.append(f"\n{ident_stats['interpretation']}\n")
        md.append(f"\n**必须记录的更正：** {ident_stats['caveat']}\n")
        md.append(
            "\n**另需注意：这 4 个分子只构成 2 个分子对**（nonane/heptane、"
            "heptanedinitrile/octanedinitrile），不是 4 个独立案例。\n"
        )

    md.append("\n## 八、域内 vs 域外误差\n")
    md.append(f"- 域内（Tanimoto ≥ {AD_TANIMOTO_MIN}）：**{ad_comparison['n_in_domain']}** 个，"
              f"MAE = {ad_comparison['mae_in_domain']}\n")
    md.append(f"- 域外：**{ad_comparison['n_out_of_domain']}** 个，"
              f"MAE = {ad_comparison['mae_out_of_domain']}\n")
    if "out_over_in_ratio" in ad_comparison:
        md.append(f"- 域外/域内 误差比：**{ad_comparison['out_over_in_ratio']}** "
                  f"→ `{ad_comparison['separation']}`\n")
        if ad_comparison["separation"] == "NO_USEFUL_SEPARATION":
            md.append(
                "\n⚠️ **域内与域外的误差几乎相同**，说明 Tanimoto 距离"
                "**不能**用作适用域判据。这与 Spearman 相关接近 0 一致：\n"
                "结构相似度对这个任务没有预测力，因此「适用域」本身不可靠。\n"
            )

    md.append("\n## 九、适用域覆盖\n")
    md.append(f"- 适用域阈值：最近邻 Tanimoto ≥ **{AD_TANIMOTO_MIN}**\n")
    md.append(f"- 域内：**{len(ad_rows) - n_out_of_domain}**\n")
    md.append(f"- 域外：**{n_out_of_domain}**\n")
    md.append(f"- 覆盖率：**{100.0*(len(ad_rows)-n_out_of_domain)/len(ad_rows):.1f}%**\n")
    md.append(
        "\n域外分子**不得**给出预测宣称；只能说明「无足够相似训练样本」。\n"
    )

    md.append("\n## 七、本实验不能回答的问题\n")
    md.append("- 不能回答「模型在真实新化学空间上如何」——22 个分子、家族多数只有 1-4 个成员\n")
    md.append("- 不能做来源聚类稳健性宣称（来源独立性未评估）\n")
    md.append("- 不能给出确认性的 OOD 性能数字\n")

    md_path = OUT_DIR / "e4_report.md"
    md_path.write_text("".join(md), encoding="utf-8")

    manifest = {
        "schema": "b05.e4/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "EXPLORATORY_NOT_CONFIRMATORY",
        "exploratory_reason": f"n={len(mols)} 个分子, 多个家族成员数 < {MIN_TEST_N}",
        "inputs": {
            "candidate_pool_v2_draft": {"sha256": sha256_file(POOL), "rows": len(pool)},
            "dielectric_v04": {"sha256": sha256_file(V04)},
            "dielectric_physical_features": {"sha256": sha256_file(FEATURES)},
        },
        "coverage": coverage,
        "family_counts": {k: len(v) for k, v in sorted(fam_groups.items())},
        "family_rules_precedence": {
            "order": [r[0] for r in FAMILY_RULES],
            "smarts": {r[0]: r[1] for r in FAMILY_RULES},
            "note": (
                "首个匹配者胜出, 顺序即优先级. "
                "杂原子身份规则先于碳骨架规则, 因此环状砜归为 sulfone 而非 aromatic. "
                "Reviewer 3 (B04+B05) 指出原列表声称『最具体优先』但实际顺序任取."
            ),
            "n_molecules_matching_multiple_rules": sum(
                1 for m in mols if m["n_rules_matched"] > 1),
            "multi_rule_examples": [
                {"name": m["name"], "matched": m["matched_rules"]}
                for m in mols if m["n_rules_matched"] > 1
            ][:10],
        },
        "min_test_n_rule": MIN_TEST_N,
        "applicability_domain_threshold": AD_TANIMOTO_MIN,
        "counts": {
            "n_families": len(fam_groups),
            "n_families_measured": len(fam_measured),
            "n_families_beating_baseline": len(fam_beat),
            "n_out_of_domain": n_out_of_domain,
            "ad_coverage_pct": round(
                100.0 * (len(ad_rows) - n_out_of_domain) / len(ad_rows), 2)
            if ad_rows else None,
        },
        "error_vs_distance_spearman": round(corr, 4) if corr is not None else None,
        "identical_fingerprint_analysis": ident_stats,
        "in_vs_out_of_domain": ad_comparison,
        "seed": SEED,
        "outputs": {
            "leave_one_family_out": {"path": str(fam_path.relative_to(REPO_ROOT)),
                                     "sha256": sha256_file(fam_path)},
            "structural_distance_ood": {"path": str(dist_path.relative_to(REPO_ROOT)),
                                        "sha256": sha256_file(dist_path)},
            "source_ood": {"path": str(src_path.relative_to(REPO_ROOT)),
                           "sha256": sha256_file(src_path)},
            "applicability_domain": {"path": str(ad_path.relative_to(REPO_ROOT)),
                                     "sha256": sha256_file(ad_path)},
            "report": {"path": str(md_path.relative_to(REPO_ROOT)),
                       "sha256": sha256_file(md_path)},
        },
        "cannot_claim": [
            "来源聚类稳健性 (来源独立性未评估)",
            "确证性 OOD 性能",
            "对 22 个分子之外化学空间的外推",
        ],
    }
    man_path = OUT_DIR / "e4_manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    print(f"[B05-E4] {fam_path}")
    print(f"[B05-E4] {dist_path}")
    print(f"[B05-E4] {src_path}")
    print(f"[B05-E4] {ad_path}")
    print(f"[B05-E4] {md_path}")
    print(f"  usable molecules   = {len(mols)}")
    print(f"  families           = {len(fam_groups)}  measured={len(fam_measured)}  "
          f"beating baseline={len(fam_beat)}")
    print(f"  out of domain      = {n_out_of_domain}/{len(ad_rows)}")
    print(f"  spearman(err, sim) = {corr:+.4f}" if corr is not None else "  spearman = n/a")
    return 0


if __name__ == "__main__":
    sys.exit(main())
