"""Exploratory diagnostic: which part of the expansion block actually helps?

This probe is **not** a scored attempt and nothing it prints may be promoted.
Its only job is to explain the pre-registered outcome: `plus_expansion_hybrid`
came out 0.0282 below `baseline_hybrid` at the full 362-row dose while the 25
percent dose came out 0.0868 *above* it.  That pattern says the block is not
uniformly harmful, so this script asks which subset carries the harm.

Every arm below shares the frozen scored rows and the frozen folds, so the
numbers are comparable to one another and to `paired_base`; none of them is a
promoted number and none may be written up as one.

Run:
    .venv/Scripts/python.exe probes/dielectric_pool_expansion_diagnostic.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "probes"))

import dielectric_coordination_block as v1
import dielectric_pool_expansion_benchmark as bn
import numpy as np
from dielectric_observations_grouped_benchmark import build_matrices

SUMMARY_OUT = REPOSITORY_ROOT / "probes" / "dielectric_pool_expansion_diagnostic.json"

POLAR_ATOMS = ("O", "N", "F", "S", "P", "Cl")


def has_polar_atom(smiles: str) -> bool:
    from rdkit import Chem

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return False
    return any(atom.GetSymbol() in POLAR_ATOMS for atom in molecule.GetAtoms())


def tanimoto_rank(
    scored_morgan: np.ndarray,
    candidate_morgan: np.ndarray,
) -> np.ndarray:
    """Max Tanimoto of every candidate row to the scored rows, on binarised counts."""

    left = (np.asarray(scored_morgan) > 0).astype(np.float64)
    right = (np.asarray(candidate_morgan) > 0).astype(np.float64)
    intersection = right @ left.T
    left_sizes = left.sum(axis=1)
    right_sizes = right.sum(axis=1)
    union = right_sizes[:, None] + left_sizes[None, :] - intersection
    with np.errstate(invalid="ignore", divide="ignore"):
        similarity = np.where(union > 0, intersection / union, 0.0)
    return similarity.max(axis=1)


def main() -> int:
    started = time.perf_counter()
    scoreboard = v1.build_scoreboard()
    base_rows = list(scoreboard["rows"])  # type: ignore[arg-type]
    base_scored = np.asarray(scoreboard["scored"], dtype=bool)
    blocked_keys = {
        (str(row["inchikey"]), round(float(str(row["T_K"])), 2)) for row in base_rows
    }
    scoring_compounds = {
        str(key) for key, flag in zip(scoreboard["groups"], base_scored, strict=True) if flag
    }
    expansion_rows, expansion_report = bn.load_expansion(
        observations_path=bn.EXPANSION_OBSERVATIONS_PATH,
        features_path=bn.EXPANSION_FEATURES_PATH,
        blocked_keys=blocked_keys,
        scoring_compounds=scoring_compounds,
    )
    print(f"expansion: {len(expansion_rows)} rows", flush=True)

    expansion_morgan, expansion_physical, expansion_target, expansion_temps, expansion_groups = (
        build_matrices(expansion_rows)
    )
    n_base = len(base_rows)
    n_expansion = len(expansion_rows)
    morgan = np.vstack([scoreboard["morgan"], expansion_morgan])
    physical = np.vstack([scoreboard["physical"], expansion_physical])
    target = np.concatenate([scoreboard["target"], expansion_target])
    temperatures = np.concatenate([scoreboard["temperatures"], expansion_temps])
    groups = list(scoreboard["groups"]) + list(expansion_groups)
    scored = np.concatenate([base_scored, np.zeros(n_expansion, dtype=bool)])
    expansion_mask = np.concatenate(
        [np.zeros(n_base, dtype=bool), np.ones(n_expansion, dtype=bool)]
    )

    base_target = np.asarray(scoreboard["target"], dtype=float)
    print(
        f"eps stats  scored: mean {base_target[base_scored].mean():.2f} p10 {np.percentile(base_target[base_scored], 10):.2f} median {np.median(base_target[base_scored]):.2f} p90 {np.percentile(base_target[base_scored], 90):.2f}"
    )
    print(
        f"eps stats    nbs: mean {expansion_target.mean():.2f} p10 {np.percentile(expansion_target, 10):.2f} median {np.median(expansion_target):.2f} p90 {np.percentile(expansion_target, 90):.2f}"
    )
    print(
        f"eps stats  table: mean {base_target.mean():.2f} median {np.median(base_target):.2f}"
    )

    similarity = tanimoto_rank(np.asarray(scoreboard["morgan"])[base_scored], expansion_morgan)
    polar = np.asarray(
        [has_polar_atom(str(row["smiles"])) for row in expansion_rows], dtype=bool
    )
    print(f"nbs rows with a polar atom: {int(polar.sum())}/{n_expansion}")

    order = np.argsort(-similarity)
    candidates: dict[str, np.ndarray] = {}
    candidates["nbs_all"] = expansion_mask.copy()
    candidates["nbs_polar"] = np.concatenate(
        [np.zeros(n_base, dtype=bool), polar]
    )
    for top in (90, 180, 270):
        take = np.zeros(n_expansion, dtype=bool)
        take[order[:top]] = True
        candidates[f"nbs_top{top}_tanimoto"] = np.concatenate(
            [np.zeros(n_base, dtype=bool), take]
        )
    full_table = np.ones(len(base_rows), dtype=bool)
    candidates["full_table"] = np.concatenate(
        [full_table, np.zeros(n_expansion, dtype=bool)]
    )
    candidates["full_table_plus_nbs_top90"] = np.concatenate(
        [
            full_table,
            np.isin(np.arange(n_expansion), order[:90]),
        ]
    )

    results: list[dict[str, object]] = []
    base_splits = bn.build_splits(groups, score_mask=scored, train_mask=scored)
    baseline = v1.evaluate_arm(
        "baseline",
        morgan=morgan,
        physical=physical,
        target=target,
        temperatures=temperatures,
        groups=groups,
        splits=base_splits,
        jobs=8,
    )
    baseline_r2 = bn.arm_r2(baseline["summary"])
    print(f"baseline R2 {baseline_r2:.6f}", flush=True)

    for name, mask in candidates.items():
        train_mask = scored | mask
        splits = bn.build_splits(groups, score_mask=scored, train_mask=train_mask)
        clock = time.perf_counter()
        arm = v1.evaluate_arm(
            name,
            morgan=morgan,
            physical=physical,
            target=target,
            temperatures=temperatures,
            groups=groups,
            splits=splits,
            jobs=8,
        )
        r2 = bn.arm_r2(arm["summary"])
        rows = int(mask.sum())
        compounds = len({str(groups[index]) for index in np.flatnonzero(mask)})
        results.append(
            {
                "arm": name,
                "rows": rows,
                "compounds": compounds,
                "r2": r2,
                "delta_r2_vs_baseline": r2 - baseline_r2,
                "seconds": time.perf_counter() - clock,
            }
        )
        print(
            f"{name:<28s} rows {rows:>5d}  R2 {r2:.6f}  delta {r2 - baseline_r2:+.6f}",
            flush=True,
        )

    payload = {
        "schema_version": 1,
        "status": "exploratory_not_promotable",
        "baseline_r2": baseline_r2,
        "expansion_report": expansion_report,
        "epsilon_stats": {
            "scored_mean": float(base_target[base_scored].mean()),
            "scored_median": float(np.median(base_target[base_scored])),
            "nbs_mean": float(expansion_target.mean()),
            "nbs_median": float(np.median(expansion_target)),
            "table_mean": float(base_target.mean()),
            "table_median": float(np.median(base_target)),
        },
        "nbs_rows_with_a_polar_atom": int(polar.sum()),
        "results": results,
        "wall_seconds": time.perf_counter() - started,
    }
    SUMMARY_OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print("summary: " + str(SUMMARY_OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())