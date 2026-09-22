"""Independently verify AL Round-1 source, filtering, scoring, and selection."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from electrolyte_ml.exporting import canonical_text_sha256
from electrolyte_ml.numerics import numerical_values_close
from electrolyte_ml.standardize import MoleculeStandardizationError, standardize_molecule

BATT_SHA256 = "c2ec78256ce6189366aebd9f7f0403e669c963e911cf51f7732083bce6374a1d"
BATT_SIZE = 1879361
SOLVFUNC_SHA256 = "1031abc49ee4f15d46211a519be6b5cdee3b68115e5e2f5141f7d155342ba493"
SOURCE_COMMIT = "a5101e30c6975552d97e34f1e93461126715c862"
SEED = 42
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


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_source_integrity(
    path: Path,
    *,
    expected_sha256: str,
    expected_size: int | None,
) -> Check:
    if not path.is_file():
        return Check("AL source", False, f"missing {path}")
    if expected_size is not None and path.stat().st_size != expected_size:
        return Check(
            "AL source",
            False,
            f"size mismatch for {path.name}: {path.stat().st_size} != {expected_size}",
        )
    actual = _sha256_file(path)
    if actual != expected_sha256:
        return Check(
            "AL source",
            False,
            f"SHA256 mismatch for {path.name}: {actual}",
        )
    return Check("AL source", True, f"{path.name} matches pinned source")


def check_filter_funnel(
    actual: Mapping[str, object],
    expected: Mapping[str, object],
) -> Check:
    for key in expected:
        if actual.get(key) != expected[key]:
            return Check(
                "AL filter funnel",
                False,
                f"{key} mismatch: {actual.get(key)} != {expected[key]}",
            )
    return Check("AL filter funnel", True, "filter funnel reproduced")


def check_selection_no_v01_leak(
    selected_keys: Sequence[str],
    v01_keys: Mapping[str, object],
) -> Check:
    leaked = sorted(set(selected_keys).intersection(v01_keys))
    if leaked:
        return Check(
            "AL selection leakage",
            False,
            f"v01 leak: {leaked[:5]}",
        )
    return Check("AL selection leakage", True, "no v01 key in selected candidates")


def check_family_quota(
    rows: Sequence[Mapping[str, object]],
    *,
    max_per_family: int = 6,
) -> Check:
    counts = Counter(str(row.get("family", "Unknown")) for row in rows)
    violations = {
        family: count for family, count in counts.items() if count > max_per_family
    }
    if violations:
        return Check(
            "AL family quota",
            False,
            f"family quota violation: {violations}",
        )
    return Check(
        "AL family quota",
        True,
        f"all families <= {max_per_family}",
    )


def check_hazard_contract(summary: Mapping[str, object]) -> Check:
    filter_rules = summary.get("filter_rules", {})
    actual_raw = (
        filter_rules.get("hazard_smarts", {})
        if isinstance(filter_rules, Mapping)
        else {}
    )
    actual = (
        {
            str(name): list(_smarts_values(value))
            for name, value in actual_raw.items()
        }
        if isinstance(actual_raw, Mapping)
        else {}
    )
    expected = {
        name: list(_smarts_values(value)) for name, value in HAZARD_SMARTS.items()
    }
    if actual != expected:
        return Check(
            "AL hazard contract",
            False,
            "hazard SMARTS do not match the verifier contract",
        )
    return Check(
        "AL hazard contract",
        True,
        f"{len(HAZARD_SMARTS)} hazard flags match",
    )


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


def _fingerprints(smiles_values: Sequence[str], *, binary: bool) -> np.ndarray:
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    values = []
    for smiles in smiles_values:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"cannot parse SMILES: {smiles!r}")
        values.append(
            generator.GetFingerprintAsNumPy(molecule)
            if binary
            else generator.GetCountFingerprintAsNumPy(molecule)
        )
    return np.vstack(values).astype(np.float32, copy=False)


def _similarity_matrix(candidate: np.ndarray, reference: np.ndarray) -> np.ndarray:
    candidate = candidate.astype(float)
    reference = reference.astype(float)
    intersection = candidate @ reference.T
    union = (
        candidate.sum(axis=1)[:, None]
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


def _max_similarity(candidate: np.ndarray, reference: np.ndarray) -> np.ndarray:
    return _similarity_matrix(candidate, reference).max(axis=1)


def _rebuild_scored_candidates(root: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    batt_path = root / "data" / "external" / "Batt-SLM.smi"
    solvfunc_path = root / "data" / "external" / "SolvFunc-87.csv"
    dielectric_path = root / "data" / "dielectric_v01.csv"
    dielectric = read_csv_rows(dielectric_path)
    v01_keys = {row["inchikey"] for row in dielectric}
    v01_binary = _fingerprints([row["smiles"] for row in dielectric], binary=True)
    with solvfunc_path.open(encoding="cp1252", newline="") as handle:
        solvfunc_rows = list(csv.DictReader(handle, delimiter=";"))
    solvfunc = [
        {
            "smiles": standardize_molecule(row["SMILES"]).smiles,
            "name": row.get("Common Name") or row.get("IUPAC Name") or "",
            "category": row.get("Category") or "Unknown",
        }
        for row in solvfunc_rows
    ]
    solvfunc_binary = _fingerprints(
        [row["smiles"] for row in solvfunc],
        binary=True,
    )
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    funnel = Counter()
    hazard_counts: Counter[str] = Counter()
    with batt_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            funnel["parsed"] += 1
            try:
                standardized = standardize_molecule(line.strip().split()[0])
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
                {"smiles": standardized.smiles, "inchikey": standardized.inchikey}
            )

    scaler = StandardScaler()
    v01_count = _fingerprints([row["smiles"] for row in dielectric], binary=False)
    scaler.fit(v01_count)
    kernel = ConstantKernel(1.0) * RBF(length_scale=10.0) + WhiteKernel(
        noise_level=1.0
    )
    model = GaussianProcessRegressor(
        kernel=kernel,
        alpha=1e-6,
        normalize_y=True,
        n_restarts_optimizer=2,
        random_state=42,
    )
    model.fit(
        scaler.transform(v01_count),
        np.asarray([float(row["dielectric"]) for row in dielectric]),
    )
    model_input_sha256 = canonical_text_sha256(
        root / "data" / "dielectric_v01.csv"
    )
    scored: list[dict[str, object]] = []
    batch_size = 4096
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start : start + batch_size]
        smiles = [row["smiles"] for row in batch]
        count = _fingerprints(smiles, binary=False)
        binary = _fingerprints(smiles, binary=True)
        prediction, std = model.predict(scaler.transform(count), return_std=True)
        max_v01 = _max_similarity(binary, v01_binary)
        solv_sim = _similarity_matrix(binary, solvfunc_binary)
        for index, row in enumerate(batch):
            nearest_index = int(np.argmax(solv_sim[index]))
            max_solvfunc = float(solv_sim[index][nearest_index])
            tier = "A" if max_solvfunc >= 0.4 else "B" if max_solvfunc >= 0.3 else "C"
            scored.append(
                {
                    "candidate_id": f"alr1:{start + index:06d}",
                    "smiles": row["smiles"],
                    "inchikey": row["inchikey"],
                    "family": solvfunc[nearest_index]["category"],
                    "nearest_solvfunc_name": solvfunc[nearest_index]["name"],
                    "nearest_solvfunc_category": solvfunc[nearest_index]["category"],
                    "max_tanimoto_solvfunc": max_solvfunc,
                    "max_tanimoto_v01": float(max_v01[index]),
                    "novelty": 1.0 - float(max_v01[index]),
                    "tier": tier,
                    "predicted_dielectric": float(prediction[index]),
                    "posterior_std": float(std[index]),
                    "hazard_flags": "",
                    "manual_review_warnings": "|".join(
                        classify_review_warnings(row["smiles"])
                    ),
                    "mp_c": "",
                    "bp_c": "",
                    "literature_doi": "",
                    "availability_status": "unknown",
                    "decision_status": "awaiting_manual_review",
                    "source_commit": SOURCE_COMMIT,
                    "model_input_sha256": model_input_sha256,
                }
            )
    std_values = np.asarray([row["posterior_std"] for row in scored], dtype=float)
    order = np.argsort(std_values, kind="stable")
    percentile = np.zeros(len(std_values), dtype=float)
    denominator = max(len(std_values) - 1, 1)
    for rank, index in enumerate(order):
        percentile[index] = rank / denominator
    for index, row in enumerate(scored):
        row["std_percentile"] = float(percentile[index])
        row["acquisition_score"] = float(percentile[index]) * float(row["novelty"])
        row["cluster"] = row["family"]
    return scored, {
        "funnel": dict(funnel),
        "hazard_rule_counts": dict(hazard_counts),
    }


def _pair_similarity(left: np.ndarray, right: np.ndarray) -> float:
    intersection = float(np.dot(left, right))
    union = float(left.sum() + right.sum() - intersection)
    return intersection / union if union else 0.0


def _select_top30(
    rows: Sequence[Mapping[str, object]],
    fingerprints: Mapping[str, np.ndarray],
    *,
    initial_selected: Sequence[Mapping[str, object]] = (),
) -> list[dict[str, object]]:
    selected = [dict(row) for row in initial_selected]
    selected_ids = {str(row["candidate_id"]) for row in selected}
    remaining = {
        str(row["candidate_id"]): dict(row)
        for row in rows
        if str(row["candidate_id"]) not in selected_ids
    }
    family_counts: Counter[str] = Counter(
        str(row["family"]) for row in selected
    )
    while remaining and len(selected) < 30:
        eligible = [
            row
            for row in remaining.values()
            if family_counts[str(row["family"])] < 6
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
            selected_ids = [str(row["candidate_id"]) for row in selected]
            ranked = []
            for row in eligible:
                candidate_id = str(row["candidate_id"])
                diversity = 1.0 - max(
                    _pair_similarity(
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
        family_counts[str(chosen["family"])] += 1
    return selected


def _quota_limited_pool(
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    ordered = sorted(
        rows,
        key=lambda row: (-float(row["acquisition_score"]), str(row["candidate_id"])),
    )
    family_counts: Counter[str] = Counter()
    pool: list[dict[str, object]] = []
    for row in ordered:
        family = str(row["family"])
        if family_counts[family] >= 6:
            continue
        family_counts[family] += 1
        pool.append(dict(row))
    return pool


def _compare_rows(
    actual_rows: Sequence[Mapping[str, str]],
    expected_rows: Sequence[Mapping[str, object]],
    *,
    key: str,
) -> Check:
    actual_by_key = {str(row[key]): row for row in actual_rows}
    expected_by_key = {str(row[key]): row for row in expected_rows}
    if set(actual_by_key) != set(expected_by_key):
        return Check("AL selection", False, f"{key} set mismatch")
    comparing_fields = {
        field for row in (*actual_rows, *expected_rows) for field in row
    }
    numeric_fields = {
        "acquisition_score",
        "max_tanimoto_solvfunc",
        "max_tanimoto_v01",
        "novelty",
        "posterior_std",
        "predicted_dielectric",
        "selection_order",
        "selection_step_score",
        "std_percentile",
    }
    gpr_derived_fields = {
        "acquisition_score",
        "posterior_std",
        "predicted_dielectric",
        "selection_step_score",
        "std_percentile",
    }
    for row_key, actual in actual_by_key.items():
        expected = expected_by_key[row_key]
        for field in sorted(comparing_fields):
            actual_value = actual.get(field)
            expected_value = expected.get(field)
            if field in numeric_fields:
                family = "gpr" if field in gpr_derived_fields else "strict"
                try:
                    matches = numerical_values_close(
                        actual_value,
                        expected_value,
                        model_family=family,
                    )
                except (TypeError, ValueError):
                    matches = False
                if not matches:
                    return Check("AL selection", False, f"{field} mismatch for {row_key}")
            elif actual_value != expected_value:
                return Check("AL selection", False, f"{field} mismatch for {row_key}")
    return Check("AL selection", True, "selection fields reproduced")


def run_checks(root: Path = ROOT) -> list[Check]:
    batt_path = root / "data" / "external" / "Batt-SLM.smi"
    solvfunc_path = root / "data" / "external" / "SolvFunc-87.csv"
    longlist_path = root / "data" / "processed" / "al_round1_longlist.csv"
    top30_path = root / "data" / "round1_candidates.csv"
    summary_path = root / "probes" / "al_round1_summary.json"
    plot_path = root / "probes" / "artifacts" / "al_round1_selection.png"
    required = (
        batt_path,
        solvfunc_path,
        longlist_path,
        top30_path,
        summary_path,
        plot_path,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return [Check("AL artifacts", False, f"missing: {missing}")]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    longlist_rows = read_csv_rows(longlist_path)
    top30_rows = read_csv_rows(top30_path)
    scored, audit = _rebuild_scored_candidates(root)
    checks = [
        check_source_integrity(
            batt_path,
            expected_sha256=BATT_SHA256,
            expected_size=BATT_SIZE,
        ),
        check_source_integrity(
            solvfunc_path,
            expected_sha256=SOLVFUNC_SHA256,
            expected_size=None,
        ),
        check_filter_funnel(
            summary["funnel"],
            {**audit["funnel"], "hazard_rule_counts": audit["hazard_rule_counts"]},
        ),
        check_hazard_contract(summary),
        Check(
            "AL counts",
            len(longlist_rows) in range(200, 501) and len(top30_rows) <= 30,
            f"longlist={len(longlist_rows)}, top30={len(top30_rows)}",
        ),
    ]
    v01_keys = {
        row["inchikey"]
        for row in read_csv_rows(root / "data" / "dielectric_v01.csv")
    }
    checks.append(
        check_selection_no_v01_leak(
            [row["inchikey"] for row in top30_rows],
            {key: True for key in v01_keys},
        )
    )
    checks.append(check_family_quota(top30_rows))
    expected_warning_counts: Counter[str] = Counter()
    for row in scored:
        expected_warning_counts.update(
            warning
            for warning in str(row["manual_review_warnings"]).split("|")
            if warning
        )
    checks.append(
        Check(
            "AL review warnings",
            summary["candidate_scores"].get("review_warning_counts")
            == dict(expected_warning_counts),
            "review warning counts reproduced",
        )
    )
    eligible = [row for row in scored if row["tier"] in {"A", "B"}]
    expected_longlist = sorted(
        eligible,
        key=lambda row: (-float(row["acquisition_score"]), str(row["candidate_id"])),
    )[:300]
    if len(expected_longlist) < 300:
        expected_longlist.extend(
            sorted(
                [row for row in scored if row["tier"] == "C"],
                key=lambda row: (-float(row["acquisition_score"]), str(row["candidate_id"])),
            )[: 300 - len(expected_longlist)]
        )
    checks.append(
        _compare_rows(
            longlist_rows,
            expected_longlist,
            key="candidate_id",
        )
    )
    fingerprints = {}
    for row in expected_longlist:
        fingerprints[row["candidate_id"]] = _fingerprints(
            [row["smiles"]],
            binary=True,
        )[0]
    expected_top30 = _select_top30(expected_longlist, fingerprints)
    if len(expected_top30) < 30:
        tier_c_pool = _quota_limited_pool(
            [row for row in scored if row["tier"] == "C"]
        )
        tier_c_fingerprints = {
            str(row["candidate_id"]): _fingerprints(
                [str(row["smiles"])],
                binary=True,
            )[0]
            for row in tier_c_pool
        }
        expected_top30 = _select_top30(
            tier_c_pool,
            {**fingerprints, **tier_c_fingerprints},
            initial_selected=expected_top30,
        )
    checks.append(
        _compare_rows(
            top30_rows,
            expected_top30,
            key="candidate_id",
        )
    )
    input_hash = summary.get("dielectric_input_sha256")
    if input_hash != canonical_text_sha256(root / "data" / "dielectric_v01.csv"):
        checks.append(Check("AL model input", False, "input hash mismatch"))
    else:
        checks.append(Check("AL model input", True, "input hash matches"))
    return checks


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    checks = run_checks(args.root)
    failures = [check for check in checks if not check.passed]
    output = stdout if stdout is not None else sys.stdout
    if args.json:
        print(
            json.dumps(
                {"passed": not failures, "checks": [asdict(check) for check in checks]},
                ensure_ascii=False,
                indent=2,
            ),
            file=output,
        )
    else:
        for check in checks:
            marker = "PASS" if check.passed else "FAIL"
            print(f"[{marker}] {check.name}: {check.detail}", file=output)
        print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed", file=output)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
