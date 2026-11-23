#!/usr/bin/env python
"""B05-8: feature quality audit -- are the 12 descriptors really 12?

Reviewers 3 and 4 (B04+B05) raised six concrete defects about the feature set. Four
of them are measurable facts about the data, and they all point the same way: the
nominal feature count overstates the *effective* information content.

  1. UNREGISTERED FEATURE
     E1 fits 12 columns including `total_energy_hartree`, but the registry lists
     only 11. So the manifest does not describe what the model actually consumed.

  2. EXACT COLLINEARITY
     `polarizability_au` and `polarizability_A3` are the same number in two units
     (ratio 1:0.148184). Feeding both is feeding one column twice.

  3. DERIVED MASQUERADING AS INDEPENDENT
     `molar_volume_m3_mol` equals `molecular_volume_A3 * N_A` exactly. It is not an
     independent measurement of bulk molar volume -- it is the van der Waals cavity
     sum restated. Its physical meaning is therefore NOT "how much space a mole of
     liquid occupies".

  4. INCONSISTENT FEATURE SETS ACROSS EXPERIMENTS
     E1 used 12 columns; E4/E6/B07 use 11 (they drop total_energy). Cross-experiment
     comparison therefore silently compares different models.

This script measures all four and reports the *effective* rank of the design
matrix, which is the number that should be quoted instead of "12 features".

Output: outputs/b05/feature_quality_audit.csv
        outputs/b05/feature_quality_audit.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b05"
GENERATOR = "audit_feature_quality/1.0.0"

POOL = REPO_ROOT / "outputs" / "b04" / "candidate_pool_v2_draft.csv"
FEATURES = REPO_ROOT / "data" / "processed" / "dielectric_physical_features.csv"
REGISTRY = OUT_DIR / "feature_registry_v2.csv"

ALL_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
            "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
            "dipole_D", "polarizability_au", "polarizability_A3",
            "homo_lumo_gap_ev", "total_energy_hartree"]
E1_COLS = ALL_COLS                     # E1 fits all 12
E4_E6_COLS = [c for c in ALL_COLS if c != "total_energy_hartree"]   # 11

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}
NA = 6.02214076e23


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


def pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    den = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n))
                    * sum((b[i] - mb) ** 2 for i in range(n)))
    return num / den if den else float("nan")


def matrix_rank(M, tol=1e-9):
    """Rank of a matrix via Gaussian elimination with partial pivoting."""
    A = [row[:] for row in M]
    rows, cols = len(A), len(A[0])
    rank = 0
    for col in range(cols):
        piv = max(range(rank, rows), key=lambda r: abs(A[r][col]), default=None)
        if piv is None or abs(A[piv][col]) < tol:
            continue
        A[rank], A[piv] = A[piv], A[rank]
        pv = A[rank][col]
        for c in range(col, cols):
            A[rank][c] /= pv
        for r in range(rows):
            if r != rank and abs(A[r][col]) > tol:
                f = A[r][col]
                for c in range(col, cols):
                    A[r][c] -= f * A[rank][c]
        rank += 1
        if rank == rows:
            break
    return rank


def main() -> int:
    for p in (POOL, FEATURES, REGISTRY):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pool = load(POOL)
    feats = {r["inchikey"]: r for r in load(FEATURES)}
    registry = {(r.get("feature") or "").strip() for r in load(REGISTRY)}

    # assemble the 22x12 matrix in pool order
    rows = []
    for r in pool:
        f = feats.get(r["inchikey"], {})
        vals = [fnum(f.get(c)) for c in ALL_COLS]
        if any(v is None for v in vals):
            continue
        rows.append(vals)
    n = len(rows)

    # ---- (1) registry coverage ----
    unregistered = [c for c in ALL_COLS if c not in registry]
    registry_only = sorted(registry - set(ALL_COLS))

    # ---- (2) pairwise collinearity ----
    pair_rows = []
    for i in range(len(ALL_COLS)):
        for j in range(i + 1, len(ALL_COLS)):
            a = [rows[k][i] for k in range(n)]
            b = [rows[k][j] for k in range(n)]
            r = pearson(a, b)
            if abs(r) >= 0.99:
                pair_rows.append({
                    "feature_a": ALL_COLS[i],
                    "feature_b": ALL_COLS[j],
                    "pearson_r": round(r, 12),
                    "verdict": "EXACTLY_COLLINEAR" if abs(r) > 0.999999 else "NEARLY_COLLINEAR",
                })

    # ---- (3) molar volume identity ----
    identity_rows = []
    ratios = []
    for r in pool:
        f = feats.get(r["inchikey"], {})
        v = fnum(f.get("molecular_volume_A3"))
        m = fnum(f.get("molar_volume_m3_mol"))
        if v and m:
            ratios.append(m / (v * 1e-30 * NA))
    if ratios:
        # The CSV stores values to limited precision, so an exact algebraic
        # identity shows up as a tiny spread rather than bit-equality. Judge it on
        # relative deviation (< 1e-6), not on absolute equality, and say so.
        spread = max(ratios) - min(ratios)
        holds = spread < 1e-6
        identity_rows.append({
            "identity": "molar_volume_m3_mol == molecular_volume_A3 * N_A",
            "n_checked": len(ratios),
            "ratio_min": round(min(ratios), 12),
            "ratio_max": round(max(ratios), 12),
            "relative_spread": round(spread, 12),
            "holds_exactly": "true" if holds else "false",
            "tolerance_note": (
                "判据用相对偏差 < 1e-6 而非按位相等: CSV 存储精度有限, "
                "代数恒等式会表现为极小的抖动而非完全相等."
            ),
            "consequence": (
                "molar_volume_m3_mol 不是独立的体相摩尔体积测量, "
                "而是 vdW 腔体积求和的重述. 把它解释为『一摩尔液体占据的体积』是错的."
            ),
        })

    # ---- (4) effective rank ----
    def rank_of(cols):
        idx = [ALL_COLS.index(c) for c in cols]
        M = [[rows[k][i] for i in idx] for k in range(n)]
        return matrix_rank(M, tol=1e-9)

    rank_12 = rank_of(ALL_COLS)
    rank_11 = rank_of(E4_E6_COLS)

    # ---- writes ----
    qa_rows = []
    for c in ALL_COLS:
        vals = [rows[k][ALL_COLS.index(c)] for k in range(n)]
        qa_rows.append({
            "feature": c,
            "in_registry": "true" if c in registry else "false",
            "used_by_E1": "true",
            "used_by_E4_E6": "true" if c in E4_E6_COLS else "false",
            "n": len(vals),
            "min": round(min(vals), 6),
            "max": round(max(vals), 6),
            "sd": round(statistics.pstdev(vals), 6),
        })
    qa_path = OUT_DIR / "feature_quality_audit.csv"
    with qa_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(qa_rows[0].keys()))
        w.writeheader()
        for r in qa_rows:
            w.writerow(r)

    doc = {
        "schema": "b05.feature_quality/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "why_this_exists": (
            "Reviewer 3 与 Reviewer 4 (B04+B05) 指出『12 个特征』这个说法"
            "高估了有效信息量. 本审计量化四个具体问题."
        ),
        "n_molecules": n,
        "defect_1_unregistered_feature": {
            "unregistered": unregistered,
            "registry_only": registry_only,
            "consequence": (
                "E1 实际拟合 "
                f"{len(E1_COLS)} 列, 而注册表只列 {len(registry)} 项. "
                "manifest 没有描述模型真正消费的特征集合."
            ),
        },
        "defect_2_exact_collinearity": {
            "pairs": pair_rows,
            "consequence": (
                "完全共线的两列等价于重复投喂同一信息; 岭回归会把它平分, "
                "但『特征数』因此虚高."
            ),
        },
        "defect_3_derived_feature_disguised": {
            "identities": identity_rows,
        },
        "defect_4_inconsistent_feature_sets": {
            "E1_columns": E1_COLS,
            "E4_E6_B07_columns": E4_E6_COLS,
            "difference": sorted(set(E1_COLS) - set(E4_E6_COLS)),
            "consequence": (
                "E1 用 12 列而 E4/E6/B07 用 11 列. "
                "跨实验比较因此在比较不同的模型, 但报告读起来像是同一个."
            ),
        },
        "effective_rank": {
            "nominal_columns_E1": len(E1_COLS),
            "rank_of_E1_matrix": rank_12,
            "nominal_columns_E4_E6": len(E4_E6_COLS),
            "rank_of_E4_E6_matrix": rank_11,
            "interpretation": (
                f"名义 {len(E1_COLS)} 列的设计矩阵实际秩为 {rank_12}. "
                "因此『12 维特征』应改为『秩 "
                f"{rank_12} 的特征块』, 否则会高估信息量."
            ),
        },
        "inputs": {
            "candidate_pool_v2_draft": {"sha256": sha256_file(POOL), "rows": len(pool)},
            "dielectric_physical_features": {"sha256": sha256_file(FEATURES)},
            "feature_registry_v2": {"sha256": sha256_file(REGISTRY)},
        },
        "output": {"path": str(qa_path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(qa_path), "rows": len(qa_rows)},
    }
    json_path = OUT_DIR / "feature_quality_audit.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"[B05-8] {json_path}")
    print(f"[B05-8] {qa_path}")
    print(f"  n molecules = {n}")
    print(f"  unregistered features = {unregistered}")
    print(f"  collinear pairs = {len(pair_rows)}")
    for p in pair_rows:
        print(f"    {p['feature_a']} ~ {p['feature_b']}: r={p['pearson_r']} ({p['verdict']})")
    print(f"  molar volume identity holds = "
          f"{identity_rows[0]['holds_exactly'] if identity_rows else 'n/a'}")
    print(f"  EFFECTIVE RANK: {rank_12} (nominal {len(E1_COLS)}), "
          f"{rank_11} (nominal {len(E4_E6_COLS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
