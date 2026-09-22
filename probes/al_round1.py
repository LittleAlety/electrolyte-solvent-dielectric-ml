"""Round-1 active-learning candidate selection for electrolyte solvents."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import rdFingerprintGenerator
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.preprocessing import StandardScaler

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.standardize import MoleculeStandardizationError, standardize_molecule

SOURCE_COMMIT = "a5101e30c6975552d97e34f1e93461126715c862"
BATT_URL = (
    "https://raw.githubusercontent.com/Teoroo-CMC/Batt-SLM/"
    f"{SOURCE_COMMIT}/Batt-SLM/Batt-SLM.smi"
)
SOLVFUNC_URL = (
    "https://raw.githubusercontent.com/Teoroo-CMC/Batt-SLM/"
    f"{SOURCE_COMMIT}/CPI/SolvFunc-87.csv"
)
BATT_SHA256 = "c2ec78256ce6189366aebd9f7f0403e669c963e911cf51f7732083bce6374a1d"
BATT_SIZE = 1879361
SOLVFUNC_SHA256 = "1031abc49ee4f15d46211a519be6b5cdee3b68115e5e2f5141f7d155342ba493"
SEED = 42
FP_RADIUS = 2
FP_SIZE = 2048
BATCH_SIZE = 4096
LONGLIST_SIZE = 300
TOP30_SIZE = 30
MAX_FAMILY_QUOTA = 6
MODEL_CONFIG = (
    "StandardScaler + GaussianProcessRegressor; "
    "C(1)*RBF(length_scale=10)+WhiteKernel(noise_level=1); "
    "alpha=1e-6; normalize_y=True; n_restarts_optimizer=2; random_state=42"
)

HAZARD_SMARTS: dict[str, str | tuple[str, ...]] = {
    "peroxide": "[OX2,OX1][OX2,OX1]",
    "alpha_halo_ether": "[Cl,Br,I][CX4][OX2]",
    "halogen_oxygen": "[F,Cl,Br,I]-[OX2]",
    "thiocarbonyl": ("[CX3]=[SX1]", "[#6]=[#16]"),
    "s_s_bond": "[S,s]-[S,s]",
    "azide": "[NX2]=[NX2+]=[NX1-]",
    "isocyanate": "[NX2]=C=O",
    "acyl_halide": "[CX3](=O)[F,Cl,Br,I]",
    "sulfonyl_halide": "[SX4](=O)(=O)[F,Cl,Br,I]",
    "epoxide": "[OX2]1[CX4][CX4]1",
    "aldehyde": "[CX3H1](=O)[#6,#1]",
    "nitro": "[NX3+](=O)[O-]",
    "n_x_bond": "[N,n]-[F,Cl,Br,I]",
    "s_x_bond": "[S,s]-[F,Cl,Br,I]",
    "p_x_bond": "[P,p]-[F,Cl,Br,I]",
    "halogen_on_nitrile_carbon": "[NX1]#[CX2][F,Cl,Br,I]",
}
def _smarts_values(smarts: str | tuple[str, ...]) -> tuple[str, ...]:
    return (smarts,) if isinstance(smarts, str) else smarts


HAZARD_PATTERNS = {
    name: tuple(Chem.MolFromSmarts(pattern) for pattern in _smarts_values(smarts))
    for name, smarts in HAZARD_SMARTS.items()
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source(path: Path, expected_sha256: str, expected_size: int) -> None:
    if path.stat().st_size != expected_size:
        raise ValueError(
            f"size mismatch for {path}: {path.stat().st_size} != {expected_size}"
        )
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise ValueError(f"SHA256 mismatch for {path}: {actual}")


def classify_hazards(smiles: str) -> tuple[str, ...]:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError(f"cannot parse SMILES: {smiles!r}")
    return tuple(
        name
        for name, patterns in HAZARD_PATTERNS.items()
        if any(
            pattern is not None and molecule.HasSubstructMatch(pattern)
            for pattern in patterns
        )
    )


def classify_review_warnings(smiles: str) -> tuple[str, ...]:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError(f"cannot parse SMILES: {smiles!r}")
    polyhalogenated_carbons = 0
    for atom in molecule.GetAtoms():
        if atom.GetSymbol() not in {"F", "Cl", "Br", "I"}:
            continue
        if any(
            neighbor.GetSymbol() == "C"
            and neighbor.GetHybridization() == Chem.HybridizationType.SP3
            for neighbor in atom.GetNeighbors()
        ):
            polyhalogenated_carbons += 1
    return (
        ("polyhalogenated_alkyl",) if polyhalogenated_carbons >= 2 else ()
    )


def acquisition_score(std_percentile: float, novelty: float) -> float:
    return float(std_percentile) * float(novelty)


def _morgan_matrix(
    smiles_values: Sequence[str],
    *,
    binary: bool,
) -> np.ndarray:
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=FP_RADIUS,
        fpSize=FP_SIZE,
    )
    rows: list[np.ndarray] = []
    for smiles in smiles_values:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"cannot parse SMILES: {smiles!r}")
        rows.append(
            generator.GetFingerprintAsNumPy(molecule)
            if binary
            else generator.GetCountFingerprintAsNumPy(molecule)
        )
    return np.vstack(rows).astype(np.float32, copy=False)


def _tanimoto_similarities(
    fingerprints: np.ndarray,
    reference: np.ndarray,
) -> np.ndarray:
    fingerprints = np.asarray(fingerprints, dtype=float)
    reference = np.asarray(reference, dtype=float)
    intersection = fingerprints @ reference.T
    union = (
        fingerprints.sum(axis=1)[:, None]
        + reference.sum(axis=1)[None, :]
        - intersection
    )
    similarities = np.divide(
        intersection,
        union,
        out=np.zeros_like(intersection),
        where=union != 0,
    )
    return similarities


def _tanimoto_to_reference(
    fingerprints: np.ndarray,
    reference: np.ndarray,
) -> np.ndarray:
    return np.max(_tanimoto_similarities(fingerprints, reference), axis=1)


def _gpr_model() -> GaussianProcessRegressor:
    kernel = ConstantKernel(1.0) * RBF(length_scale=10.0) + WhiteKernel(
        noise_level=1.0
    )
    return GaussianProcessRegressor(
        kernel=kernel,
        alpha=1e-6,
        normalize_y=True,
        n_restarts_optimizer=2,
        random_state=SEED,
    )


def _load_solvfunc(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="cp1252", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    result = []
    for row in rows:
        smiles = row.get("SMILES", "").strip()
        if not smiles:
            continue
        standardized = standardize_molecule(smiles)
        result.append(
            {
                "smiles": standardized.smiles,
                "inchikey": standardized.inchikey,
                "name": row.get("Common Name") or row.get("IUPAC Name") or "",
                "category": row.get("Category") or "Unknown",
            }
        )
    return result


def select_top30(
    rows: Sequence[dict[str, object]],
    fingerprints: Mapping[str, np.ndarray],
    *,
    limit: int = TOP30_SIZE,
    max_per_family: int = MAX_FAMILY_QUOTA,
    initial_selected: Sequence[Mapping[str, object]] = (),
) -> list[dict[str, object]]:
    selected = [dict(row) for row in initial_selected]
    selected_ids = {str(row["candidate_id"]) for row in selected}
    remaining = {
        str(row["candidate_id"]): row
        for row in rows
        if str(row["candidate_id"]) not in selected_ids
    }
    family_counts: Counter[str] = Counter(
        str(row.get("family", "Unknown")) for row in selected
    )
    while remaining and len(selected) < limit:
        eligible = [
            row
            for row in remaining.values()
            if family_counts[str(row.get("family", "Unknown"))] < max_per_family
        ]
        if not eligible:
            break
        if not selected:
            chosen = max(
                eligible,
                key=lambda row: (
                    float(row["acquisition_score"]),
                    str(row["candidate_id"]),
                ),
            )
            diversity = float(chosen["acquisition_score"])
        else:
            ranked = []
            selected_ids = [str(row["candidate_id"]) for row in selected]
            for row in eligible:
                candidate_id = str(row["candidate_id"])
                if not selected_ids:
                    diversity = 1.0
                else:
                    diversity = 1.0 - max(
                        _pairwise_tanimoto(
                            fingerprints[candidate_id],
                            fingerprints[selected_id],
                        )
                        for selected_id in selected_ids
                    )
                ranked.append((diversity, float(row["acquisition_score"]), row))
            diversity, _, chosen = max(
                ranked,
                key=lambda item: (
                    item[0],
                    item[1],
                    str(item[2]["candidate_id"]),
                ),
            )
        selected_row = dict(chosen)
        selected_row["selection_order"] = len(selected) + 1
        selected_row["selection_step_score"] = diversity
        selected.append(selected_row)
        remaining.pop(str(chosen["candidate_id"]))
        family_counts[str(chosen.get("family", "Unknown"))] += 1
    return selected


def _quota_limited_pool(
    rows: Sequence[dict[str, object]],
    *,
    max_per_family: int,
) -> list[dict[str, object]]:
    ordered = sorted(
        rows,
        key=lambda row: (-float(row["acquisition_score"]), str(row["candidate_id"])),
    )
    family_counts: Counter[str] = Counter()
    pool: list[dict[str, object]] = []
    for row in ordered:
        family = str(row.get("family", "Unknown"))
        if family_counts[family] >= max_per_family:
            continue
        family_counts[family] += 1
        pool.append(row)
    return pool


def _pairwise_tanimoto(left: np.ndarray, right: np.ndarray) -> float:
    intersection = float(np.dot(left, right))
    union = float(np.sum(left) + np.sum(right) - intersection)
    return intersection / union if union else 0.0


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    fields: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _candidate_fields() -> tuple[str, ...]:
    return (
        "candidate_id",
        "smiles",
        "inchikey",
        "family",
        "nearest_solvfunc_name",
        "nearest_solvfunc_category",
        "max_tanimoto_solvfunc",
        "max_tanimoto_v01",
        "novelty",
        "tier",
        "predicted_dielectric",
        "posterior_std",
        "std_percentile",
        "acquisition_score",
        "cluster",
        "hazard_flags",
        "manual_review_warnings",
        "mp_c",
        "bp_c",
        "literature_doi",
        "availability_status",
        "decision_status",
        "source_commit",
        "model_input_sha256",
    )


def run_pipeline(
    *,
    batt_path: Path,
    solvfunc_path: Path,
    dielectric_path: Path,
    longlist_path: Path,
    top30_path: Path,
    summary_path: Path,
    plot_path: Path,
) -> dict[str, object]:
    verify_source(batt_path, BATT_SHA256, BATT_SIZE)
    verify_source(solvfunc_path, SOLVFUNC_SHA256, 20753)
    dielectric_rows = [
        row
        for row in csv.DictReader(
            dielectric_path.open(encoding="utf-8", newline="")
        )
    ]
    v01_keys = {row["inchikey"] for row in dielectric_rows}
    v01_smiles = [row["smiles"] for row in dielectric_rows]
    v01_binary = _morgan_matrix(v01_smiles, binary=True)
    solvfunc = _load_solvfunc(solvfunc_path)
    solvfunc_binary = _morgan_matrix(
        [row["smiles"] for row in solvfunc],
        binary=True,
    )

    RDLogger.DisableLog("rdApp.*")
    funnel = Counter()
    hazard_counts: Counter[str] = Counter()
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    with batt_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            funnel["parsed"] += 1
            raw_smiles = line.strip().split()[0]
            try:
                standardized = standardize_molecule(raw_smiles)
            except MoleculeStandardizationError:
                funnel["invalid_smiles"] += 1
                continue
            if standardized.inchikey in seen:
                funnel["duplicates"] += 1
                continue
            seen.add(standardized.inchikey)
            funnel["deduplicated"] += 1
            if standardized.inchikey in v01_keys:
                funnel["excluded_v01"] += 1
                continue
            hazards = classify_hazards(standardized.smiles)
            if hazards:
                funnel["hazard_excluded"] += 1
                hazard_counts.update(hazards)
                continue
            funnel["safe_candidates"] += 1
            candidates.append(
                {
                    "smiles": standardized.smiles,
                    "inchikey": standardized.inchikey,
                }
            )

    count_scaler = StandardScaler()
    v01_count = _morgan_matrix(v01_smiles, binary=False)
    count_scaler.fit(v01_count)
    target = np.asarray(
        [float(row["dielectric"]) for row in dielectric_rows],
        dtype=float,
    )
    gpr = _gpr_model()
    gpr.fit(count_scaler.transform(v01_count), target)

    enriched: list[dict[str, object]] = []
    for start in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[start : start + BATCH_SIZE]
        smiles = [row["smiles"] for row in batch]
        count = _morgan_matrix(smiles, binary=False)
        binary = _morgan_matrix(smiles, binary=True)
        prediction, std = gpr.predict(
            count_scaler.transform(count),
            return_std=True,
        )
        max_v01 = _tanimoto_to_reference(binary, v01_binary)
        solv_similarities = _tanimoto_similarities(binary, solvfunc_binary)
        for index, row in enumerate(batch):
            nearest_index = int(np.argmax(solv_similarities[index]))
            max_solvfunc = float(solv_similarities[index][nearest_index])
            tier = "A" if max_solvfunc >= 0.4 else "B" if max_solvfunc >= 0.3 else "C"
            nearest = solvfunc[nearest_index]
            enriched.append(
                {
                    "candidate_id": f"alr1:{start + index:06d}",
                    "smiles": row["smiles"],
                    "inchikey": row["inchikey"],
                    "family": nearest["category"],
                    "nearest_solvfunc_name": nearest["name"],
                    "nearest_solvfunc_category": nearest["category"],
                    "max_tanimoto_solvfunc": max_solvfunc,
                    "max_tanimoto_v01": float(max_v01[index]),
                    "novelty": 1.0 - float(max_v01[index]),
                    "tier": tier,
                    "predicted_dielectric": float(prediction[index]),
                    "posterior_std": float(std[index]),
                    "hazard_flags": "",
                    "manual_review_warnings": "|".join(
                        classify_review_warnings(str(row["smiles"]))
                    ),
                    "mp_c": "",
                    "bp_c": "",
                    "literature_doi": "",
                    "availability_status": "unknown",
                    "decision_status": "awaiting_manual_review",
                    "source_commit": SOURCE_COMMIT,
                    "model_input_sha256": canonical_text_sha256(dielectric_path),
                }
            )
        print(f"scored {min(start + BATCH_SIZE, len(candidates))}/{len(candidates)}")

    std_values = np.asarray(
        [float(row["posterior_std"]) for row in enriched],
        dtype=float,
    )
    order = np.argsort(std_values, kind="stable")
    percentile = np.zeros(len(std_values), dtype=float)
    denominator = max(len(std_values) - 1, 1)
    for rank, index in enumerate(order):
        percentile[index] = rank / denominator
    for index, row in enumerate(enriched):
        row["std_percentile"] = float(percentile[index])
        row["acquisition_score"] = acquisition_score(
            float(percentile[index]),
            float(row["novelty"]),
        )
        row["cluster"] = row["nearest_solvfunc_category"]

    tier_ab = [row for row in enriched if row["tier"] in {"A", "B"}]
    tier_c = [row for row in enriched if row["tier"] == "C"]
    longlist = sorted(
        tier_ab,
        key=lambda row: (-float(row["acquisition_score"]), str(row["candidate_id"])),
    )[:LONGLIST_SIZE]
    if len(longlist) < LONGLIST_SIZE:
        longlist.extend(
            sorted(
                tier_c,
                key=lambda row: (
                    -float(row["acquisition_score"]),
                    str(row["candidate_id"]),
                ),
            )[: LONGLIST_SIZE - len(longlist)]
        )
    longlist_fingerprints = {
        str(row["candidate_id"]): _morgan_matrix([str(row["smiles"])], binary=True)[0]
        for row in longlist
    }
    top30 = select_top30(longlist, longlist_fingerprints)
    tier_c_fill_count = 0
    if len(top30) < TOP30_SIZE:
        tier_c_pool = _quota_limited_pool(
            tier_c,
            max_per_family=MAX_FAMILY_QUOTA,
        )
        tier_c_fingerprints = {
            str(row["candidate_id"]): _morgan_matrix(
                [str(row["smiles"])],
                binary=True,
            )[0]
            for row in tier_c_pool
        }
        expanded = select_top30(
            tier_c_pool,
            {**longlist_fingerprints, **tier_c_fingerprints},
            initial_selected=top30,
        )
        tier_c_fill_count = len(expanded) - len(top30)
        top30 = expanded
    longlist_fields = _candidate_fields()
    top30_fields = (*longlist_fields, "selection_order", "selection_step_score")
    _write_csv(longlist_path, longlist, longlist_fields)
    _write_csv(top30_path, top30, top30_fields)

    family_counts = Counter(str(row["family"]) for row in top30)
    top30_tier_counts = Counter(str(row["tier"]) for row in top30)
    tier_counts = Counter(str(row["tier"]) for row in longlist)
    review_warning_counts: Counter[str] = Counter()
    for row in enriched:
        review_warning_counts.update(
            warning
            for warning in str(row["manual_review_warnings"]).split("|")
            if warning
        )
    summary = {
        "schema_version": 1,
        "source_commit": SOURCE_COMMIT,
        "batt_source": {
            "path": batt_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "url": BATT_URL,
            "sha256": BATT_SHA256,
            "size_bytes": BATT_SIZE,
        },
        "solvfunc_source": {
            "path": solvfunc_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "url": SOLVFUNC_URL,
            "sha256": SOLVFUNC_SHA256,
            "size_bytes": solvfunc_path.stat().st_size,
        },
        "dielectric_input_sha256": canonical_text_sha256(dielectric_path),
        "model_config": MODEL_CONFIG,
        "feature_config": "Morgan count fingerprint radius=2 fpSize=2048",
        "filter_rules": {
            "version": "al_round1_hazard_v4",
            "hazard_smarts": HAZARD_SMARTS,
        },
        "funnel": {
            "parsed": funnel["parsed"],
            "invalid_smiles": funnel["invalid_smiles"],
            "deduplicated": funnel["deduplicated"],
            "excluded_v01": funnel["excluded_v01"],
            "hazard_excluded": funnel["hazard_excluded"],
            "safe_candidates": funnel["safe_candidates"],
            "hazard_rule_counts": dict(sorted(hazard_counts.items())),
        },
        "candidate_scores": {
            "scored_candidates": len(enriched),
            "tier_counts": dict(Counter(row["tier"] for row in enriched)),
            "longlist_rows": len(longlist),
            "longlist_tier_counts": dict(tier_counts),
            "top30_rows": len(top30),
            "top30_family_counts": dict(family_counts),
            "top30_tier_counts": dict(top30_tier_counts),
            "tier_c_fill_count": tier_c_fill_count,
            "top30_shortfall": TOP30_SIZE - len(top30),
            "review_warning_counts": dict(review_warning_counts),
            "acquisition_formula": "std_percentile * novelty",
            "novelty_formula": "1 - max_binary_Morgan_Tanimoto_to_v01",
        },
        "selection": {
            "longlist_rule": (
                "Tier A/B by acquisition; fill from Tier C only if fewer than 300"
            ),
            "top30_rule": (
                "deterministic greedy MaxMin diversity with a hard family quota of "
                "6, seed 42; no all-remaining fallback"
            ),
            "tier_c_fill_rule": (
                "only after the A/B hard-quota selection is short; use the top 6 "
                "acquisition-ranked Tier C rows per family as continuation "
                "candidates, still under the hard quota"
            ),
            "family_quota": MAX_FAMILY_QUOTA,
            "family_quota_enforced": True,
            "seed": SEED,
        },
        "coverage_gap_note": (
            "The 308-solvent ECW coverage gap is unavailable and was not used as "
            "a candidate pool."
        ),
        "limitations": [
            "Predicted values are model outputs, not experimental measurements.",
            "Candidates are not confirmed to be liquid at room temperature or experimentally available.",
            "Melting point, boiling point, and literature DOI remain empty pending manual review.",
        ],
        "outputs": {
            "longlist_csv": longlist_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "top30_csv": top30_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "summary_json": summary_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "selection_plot": plot_path.relative_to(REPOSITORY_ROOT).as_posix(),
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_plot(longlist, top30, plot_path)
    return summary


def _write_plot(
    longlist: Sequence[Mapping[str, object]],
    top30: Sequence[Mapping[str, object]],
    path: Path,
) -> None:
    selected_ids = {row["candidate_id"] for row in top30}
    ordinary = [row for row in longlist if row["candidate_id"] not in selected_ids]
    figure, axis = plt.subplots(figsize=(8, 6))
    axis.scatter(
        [float(row["novelty"]) for row in ordinary],
        [float(row["posterior_std"]) for row in ordinary],
        s=15,
        alpha=0.35,
        label="longlist",
    )
    axis.scatter(
        [float(row["novelty"]) for row in top30],
        [float(row["posterior_std"]) for row in top30],
        s=35,
        alpha=0.9,
        label="Top30",
    )
    axis.set_xlabel("Novelty (1 - max Morgan Tanimoto to v01)")
    axis.set_ylabel("GPR posterior std")
    axis.set_title("AL Round-1 candidate selection")
    axis.legend()
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batt",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "external" / "Batt-SLM.smi",
    )
    parser.add_argument(
        "--solvfunc",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "external" / "SolvFunc-87.csv",
    )
    parser.add_argument(
        "--dielectric",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "dielectric_v01.csv",
    )
    parser.add_argument(
        "--longlist",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "al_round1_longlist.csv",
    )
    parser.add_argument(
        "--top30",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "round1_candidates.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPOSITORY_ROOT / "probes" / "al_round1_summary.json",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=(
            REPOSITORY_ROOT / "probes" / "artifacts" / "al_round1_selection.png"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = run_pipeline(
        batt_path=args.batt,
        solvfunc_path=args.solvfunc,
        dielectric_path=args.dielectric,
        longlist_path=args.longlist,
        top30_path=args.top30,
        summary_path=args.summary,
        plot_path=args.plot,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
