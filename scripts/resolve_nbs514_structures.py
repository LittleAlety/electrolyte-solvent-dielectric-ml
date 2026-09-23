"""Resolve NBS Circular 514 candidates to structures and rank v0.2 additions."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import unicodedata
import urllib.parse
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator, rdMolDescriptors

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NBS514_DOI = "10.6028/nbs.circ.514"
NBS514_URL = "https://nvlpubs.nist.gov/nistpubs/Legacy/circ/nbscircular514.pdf"
PUBCHEM_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CIR_URL = "https://cactus.nci.nih.gov/chemical/structure"
USER_AGENT = "electrolyte-ml/0.0.0 (+https://github.com/LittleAlety/electrolyte-solvent-dielectric-ml)"
HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
    }
)
QUALITY_RANK = {
    "four_figures": 2,
    "three_figures": 1,
}
GROUP_SMARTS = {
    "carbonate": "[CX3](=O)[OX2][#6]",
    "ester": "[CX3](=O)[OX2][#6]",
    "ketone": "[#6][CX3](=O)[#6]",
    "ether": "[OD2]([#6])[#6]",
    "alcohol": "[OX2H]",
    "nitrile": "[NX1]#[CX2]",
    "nitro": "[NX3+](=O)[O-]",
    "sulfoxide": "[#16X3](=O)",
    "sulfone": "[#16X4](=O)(=O)",
    "phosphate": "[PX4](=O)",
}
HAZARD_SMARTS = {
    "peroxide": "[OX2,OX1][OX2,OX1]",
    "alpha_halo_ether": "[Cl,Br,I][CX4][OX2]",
    "halogen_oxygen": "[F,Cl,Br,I]-[OX2]",
    "thiocarbonyl": "[CX3]=[SX1]",
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
}
HAZARD_PATTERNS = {
    name: Chem.MolFromSmarts(smarts) for name, smarts in HAZARD_SMARTS.items()
}
STABILITY_SMARTS = {
    "aliphatic_halogen": "[CX4][Cl,Br,I]",
    "alkyne": "[CX2]#[CX2]",
    "vinyl_hetero": "[CX3]=[CX3][O,S,N]",
    "hydrogen_cyanide": "[CH1]#[NX1]",
}
STABILITY_PATTERNS = {
    name: Chem.MolFromSmarts(smarts) for name, smarts in STABILITY_SMARTS.items()
}
OUTPUT_FIELDS = (
    "selection_rank",
    "selected_for_v02",
    "selection_eligible",
    "selection_exclusion",
    "source_id",
    "source_page",
    "compound_name",
    "formula",
    "dielectric",
    "t_C",
    "T_K",
    "source_quality",
    "alpha_1e5",
    "alpha_kind",
    "valid_range_C",
    "references",
    "frequency_note",
    "smiles",
    "inchikey",
    "molecular_formula",
    "formula_match",
    "resolution_source",
    "resolved_name",
    "max_tanimoto_solvfunc",
    "al_round1_hit",
    "carbon_count",
    "hetero_count",
    "polar_group_bonus",
    "hazard_flags",
    "stability_flags",
    "priority_score",
    "notes",
)


@dataclass(frozen=True, slots=True)
class ResolvedStructure:
    smiles: str
    inchikey: str
    molecular_formula: str
    resolution_source: str
    resolved_name: str


@dataclass(frozen=True, slots=True)
class Candidate:
    row: Mapping[str, str]
    structure: ResolvedStructure
    formula_match: bool
    max_tanimoto_solvfunc: float
    al_round1_hit: bool
    carbon_count: int
    hetero_count: int
    polar_group_bonus: int
    hazard_flags: str
    stability_flags: str
    selection_eligible: bool
    selection_exclusion: str
    priority_score: float


def read_csv_rows(
    path: Path,
    *,
    encoding: str = "utf-8",
) -> list[dict[str, str]]:
    with path.open(encoding=encoding, newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-")
    return re.sub(r"\s+", " ", value).strip()


def normalize_name_key(value: str) -> str:
    return normalize_text(value).casefold()


def name_variants(value: str) -> list[str]:
    """Return deterministic lookup variants without inventing a structure."""

    original = normalize_text(value)
    variants: list[str] = []

    def add(candidate: str) -> None:
        candidate = normalize_text(candidate).strip(" ,;:")
        if candidate and candidate not in variants:
            variants.append(candidate)

    add(original)
    parenthetical = re.findall(r"\(([^()]*)\)", original)
    without_parenthetical = re.sub(r"\s*\([^()]*\)", "", original)
    for item in parenthetical:
        add(item)
    add(without_parenthetical)

    seed_values = list(variants)
    dash_variants = {
        "alpha": "a",
        "beta": "b",
        "gamma": "g",
        "delta": "d",
    }
    for seed in seed_values:
        stripped = seed
        for prefix in (
            "dl-",
            "d-",
            "l-",
            "dl ",
            "d ",
            "l ",
            "racemic-",
            "erythro-",
            "threo-",
            "cis-",
            "trans-",
            "(+)-",
            "(-)-",
            "(+-)-",
        ):
            if stripped.casefold().startswith(prefix):
                stripped = stripped[len(prefix) :]
        add(stripped)
        for word, symbol in dash_variants.items():
            add(re.sub(rf"\b{word}\b", symbol, stripped, flags=re.IGNORECASE))
            add(re.sub(rf"\b{symbol}\b", word, stripped, flags=re.IGNORECASE))
    return variants


def _request_json(url: str, *, timeout: float, retries: int = 2) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = HTTP_SESSION.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as error:
            last_error = error
            status_code = error.response.status_code if error.response is not None else 0
            if status_code not in {429, 500, 502, 503, 504}:
                raise
            if attempt == retries:
                raise
            time.sleep(1.5 * (attempt + 1))
        except (requests.Timeout, requests.ConnectionError) as error:
            last_error = error
            if attempt == retries:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed: {last_error}")


def _structure_from_smiles(
    smiles: str,
    *,
    expected_formula: str,
    source: str,
    resolved_name: str,
) -> ResolvedStructure | None:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    inchikey = Chem.MolToInchiKey(molecule)
    if not inchikey:
        return None
    formula = rdMolDescriptors.CalcMolFormula(molecule)
    if expected_formula and formula != expected_formula:
        return None
    return ResolvedStructure(
        smiles=canonical,
        inchikey=inchikey,
        molecular_formula=formula,
        resolution_source=source,
        resolved_name=resolved_name,
    )


def _pubchem_lookup(
    lookup_name: str,
    *,
    expected_formula: str,
    timeout: float,
) -> ResolvedStructure | None:
    encoded = urllib.parse.quote(lookup_name, safe="")
    url = (
        f"{PUBCHEM_URL}/compound/name/{encoded}/property/"
        "SMILES,ConnectivitySMILES,InChIKey,MolecularFormula/JSON"
    )
    try:
        payload = _request_json(url, timeout=timeout)
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else 0
        if status_code == 404:
            return None
        raise
    properties = payload.get("PropertyTable", {}).get("Properties", [])
    if not isinstance(properties, list):
        return None
    shortest: ResolvedStructure | None = None
    for item in properties:
        if not isinstance(item, Mapping):
            continue
        smiles = str(
            item.get("SMILES")
            or item.get("ConnectivitySMILES")
            or item.get("CanonicalSMILES")
            or ""
        )
        if not smiles:
            continue
        structure = _structure_from_smiles(
            smiles,
            expected_formula=expected_formula,
            source="pubchem",
            resolved_name=lookup_name,
        )
        if structure is None:
            continue
        if shortest is None or len(structure.smiles) < len(shortest.smiles):
            shortest = structure
    return shortest


def _cir_lookup(
    lookup_name: str,
    *,
    expected_formula: str,
    timeout: float,
) -> ResolvedStructure | None:
    encoded = urllib.parse.quote(lookup_name, safe="")
    url = f"{CIR_URL}/{encoded}/smiles"
    try:
        response = HTTP_SESSION.get(url, timeout=timeout)
        response.raise_for_status()
        smiles = response.text.strip()
    except (requests.HTTPError, requests.RequestException):
        return None
    if "<" in smiles or "\n" in smiles:
        return None
    return _structure_from_smiles(
        smiles,
        expected_formula=expected_formula,
        source="cactus",
        resolved_name=lookup_name,
    )


def resolve_structure(
    name: str,
    *,
    expected_formula: str,
    cache: dict[str, dict[str, str]],
    timeout: float,
    pause_seconds: float,
) -> ResolvedStructure | None:
    for variant in name_variants(name):
        cache_key = f"{normalize_name_key(variant)}|{expected_formula}"
        cached = cache.get(cache_key)
        if cached is not None:
            if cached.get("status") == "resolved":
                return ResolvedStructure(
                    smiles=cached["smiles"],
                    inchikey=cached["inchikey"],
                    molecular_formula=cached["molecular_formula"],
                    resolution_source=cached["resolution_source"],
                    resolved_name=cached["resolved_name"],
                )
            continue
        structure: ResolvedStructure | None = None
        try:
            structure = _pubchem_lookup(
                variant,
                expected_formula=expected_formula,
                timeout=timeout,
            )
        except (requests.RequestException, json.JSONDecodeError):
            structure = None
        if structure is None:
            structure = _cir_lookup(
                variant,
                expected_formula=expected_formula,
                timeout=timeout,
            )
        if structure is None:
            cache[cache_key] = {"status": "not_found"}
        else:
            cache[cache_key] = {
                "status": "resolved",
                "smiles": structure.smiles,
                "inchikey": structure.inchikey,
                "molecular_formula": structure.molecular_formula,
                "resolution_source": structure.resolution_source,
                "resolved_name": structure.resolved_name,
            }
            return structure
        if pause_seconds:
            time.sleep(pause_seconds)
    return None


def _load_cache(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"cache is not a JSON object: {path}")
    return payload


def _write_cache(path: Path, cache: Mapping[str, Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _is_strict_room_temperature(row: Mapping[str, str]) -> bool:
    try:
        temperature_c = float(row["t_C"])
    except (KeyError, TypeError, ValueError):
        return False
    return 20 <= temperature_c <= 30 and row.get("source_quality") in QUALITY_RANK


def _merge_candidate_rows(paths: Iterable[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        for row in read_csv_rows(path):
            if _is_strict_room_temperature(row):
                rows.append(dict(row))
    return rows


def _deduplicate_rows_by_name(rows: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        key = normalize_name_key(row["compound_name"])
        grouped.setdefault(key, []).append(row)

    selected: list[dict[str, str]] = []
    for name_key in sorted(
        grouped,
        key=lambda key: min(
            int(row["source_page"]) for row in grouped[key]
        ),
    ):
        candidates = grouped[name_key]
        best = min(
            candidates,
            key=lambda row: (
                -QUALITY_RANK[str(row["source_quality"])],
                abs(float(row["T_K"]) - 298.15),
                row["source_id"],
            ),
        )
        selected.append(dict(best))
    return selected


def _morgan_binary(smiles: str):
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError(f"invalid SMILES: {smiles!r}")
    return rdFingerprintGenerator.GetMorganGenerator(
        radius=2,
        fpSize=2048,
    ).GetFingerprintAsNumPy(molecule)


def _tanimoto(left, right) -> float:
    import numpy as np

    intersection = float(np.dot(left, right))
    union = float(left.sum() + right.sum() - intersection)
    return 0.0 if union == 0 else intersection / union


def _solvfunc_fingerprints(path: Path) -> list[Any]:
    if not path.is_file():
        return []
    fingerprints = []
    for row in read_csv_rows(path, encoding="cp1252"):
        smiles = row.get("SMILES") or row.get("smiles") or ""
        try:
            fingerprints.append(_morgan_binary(smiles))
        except ValueError:
            continue
    return fingerprints


def _polar_group_bonus(molecule: Chem.Mol) -> int:
    matches = 0
    for smarts in GROUP_SMARTS.values():
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is not None and molecule.HasSubstructMatch(pattern):
            matches += 1
    return matches


def _hazard_flags(molecule: Chem.Mol) -> tuple[str, ...]:
    return tuple(
        name
        for name, pattern in HAZARD_PATTERNS.items()
        if pattern is not None and molecule.HasSubstructMatch(pattern)
    )


def _stability_flags(molecule: Chem.Mol) -> tuple[str, ...]:
    return tuple(
        name
        for name, pattern in STABILITY_PATTERNS.items()
        if pattern is not None and molecule.HasSubstructMatch(pattern)
    )


def _rank_candidate(
    row: Mapping[str, str],
    structure: ResolvedStructure,
    *,
    v01_keys: set[str],
    al_round1_keys: set[str],
    solvfunc_fingerprints: Sequence[Any],
) -> Candidate | None:
    if structure.inchikey in v01_keys:
        return None
    molecule = Chem.MolFromSmiles(structure.smiles)
    if molecule is None:
        return None
    try:
        temperature = float(row["T_K"])
        dielectric = float(row["dielectric"])
    except (KeyError, TypeError, ValueError):
        return None
    if not 293.15 <= temperature <= 303.15 or dielectric <= 0:
        return None
    fingerprint = _morgan_binary(structure.smiles)
    max_similarity = max(
        (_tanimoto(fingerprint, candidate) for candidate in solvfunc_fingerprints),
        default=0.0,
    )
    carbon_count = sum(
        atom.GetAtomicNum() == 6 for atom in molecule.GetAtoms()
    )
    hetero_count = sum(atom.GetAtomicNum() not in {1, 6} for atom in molecule.GetAtoms())
    group_bonus = _polar_group_bonus(molecule)
    hazard_flags = _hazard_flags(molecule)
    stability_flags = _stability_flags(molecule)
    exclusion_reasons: list[str] = []
    if str(row.get("frequency_note", "")).strip():
        exclusion_reasons.append("frequency_dependent")
    exclusion_reasons.extend(f"hazard:{name}" for name in hazard_flags)
    exclusion_reasons.extend(f"stability:{name}" for name in stability_flags)
    selection_eligible = not exclusion_reasons
    al_hit = structure.inchikey in al_round1_keys
    quality_bonus = QUALITY_RANK[str(row["source_quality"])]
    size_penalty = max(0, carbon_count - 12) * 0.35
    priority_score = (
        100.0 * float(al_hit)
        + 25.0 * max_similarity
        + 7.0 * group_bonus
        + 4.0 * quality_bonus
        + 0.5 * min(hetero_count, 8)
        - size_penalty
    )
    return Candidate(
        row=row,
        structure=structure,
        formula_match=structure.molecular_formula == row.get("formula", ""),
        max_tanimoto_solvfunc=max_similarity,
        al_round1_hit=al_hit,
        carbon_count=carbon_count,
        hetero_count=hetero_count,
        polar_group_bonus=group_bonus,
        hazard_flags="|".join(hazard_flags),
        stability_flags="|".join(stability_flags),
        selection_eligible=selection_eligible,
        selection_exclusion="|".join(exclusion_reasons),
        priority_score=priority_score,
    )


def _candidate_output_rows(
    candidates: Sequence[Candidate],
    *,
    target_new_compounds: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            not candidate.selection_eligible,
            -candidate.priority_score,
            candidate.row["source_id"],
        ),
    )
    eligible_rank = 0
    for candidate in ordered:
        if candidate.selection_eligible:
            eligible_rank += 1
        rank = eligible_rank if candidate.selection_eligible else 0
        row = candidate.row
        rows.append(
            {
                "selection_rank": "" if rank == 0 else str(rank),
                "selected_for_v02": str(
                    candidate.selection_eligible and rank <= target_new_compounds
                ).lower(),
                "selection_eligible": str(candidate.selection_eligible).lower(),
                "selection_exclusion": candidate.selection_exclusion,
                "source_id": row["source_id"],
                "source_page": row["source_page"],
                "compound_name": row["compound_name"],
                "formula": row["formula"],
                "dielectric": row["dielectric"],
                "t_C": row["t_C"],
                "T_K": row["T_K"],
                "source_quality": row["source_quality"],
                "alpha_1e5": row.get("alpha_1e5", ""),
                "alpha_kind": row.get("alpha_kind", ""),
                "valid_range_C": row.get("valid_range_C", ""),
                "references": row.get("references", ""),
                "frequency_note": row.get("frequency_note", ""),
                "smiles": candidate.structure.smiles,
                "inchikey": candidate.structure.inchikey,
                "molecular_formula": candidate.structure.molecular_formula,
                "formula_match": str(candidate.formula_match).lower(),
                "resolution_source": candidate.structure.resolution_source,
                "resolved_name": candidate.structure.resolved_name,
                "max_tanimoto_solvfunc": f"{candidate.max_tanimoto_solvfunc:.6f}",
                "al_round1_hit": str(candidate.al_round1_hit).lower(),
                "carbon_count": str(candidate.carbon_count),
                "hetero_count": str(candidate.hetero_count),
                "polar_group_bonus": str(candidate.polar_group_bonus),
                "hazard_flags": candidate.hazard_flags,
                "stability_flags": candidate.stability_flags,
                "priority_score": f"{candidate.priority_score:.6f}",
                "notes": (
                    f"nbs514_doi={NBS514_DOI};"
                    f"source_url={NBS514_URL};"
                    f"source_quality={row['source_quality']};"
                    f"formula_match={str(candidate.formula_match).lower()};"
                    "manual_transcription_review_required=true"
                ),
            }
        )
    return rows


def _parse_args() -> argparse.Namespace:
    data_dir = REPOSITORY_ROOT / "data"
    default_inputs = [
        data_dir / "interim" / "nbs514_organic_part1.csv",
        data_dir / "interim" / "nbs514_organic_part2.csv",
        data_dir / "interim" / "nbs514_organic_part3.csv",
        data_dir / "interim" / "nbs514_organic_part4.csv",
    ]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", dest="inputs")
    parser.add_argument(
        "--cache",
        type=Path,
        default=data_dir / "interim" / "nbs514_structure_cache.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=data_dir / "processed" / "nbs514_structure_candidates.csv",
    )
    parser.add_argument("--target-new-compounds", type=int, default=110)
    parser.add_argument("--max-names", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--pause-seconds", type=float, default=0.2)
    parser.set_defaults(inputs=default_inputs)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = _deduplicate_rows_by_name(_merge_candidate_rows(args.inputs))
    v01_rows = read_csv_rows(REPOSITORY_ROOT / "data" / "dielectric_v01.csv")
    v01_keys = {row["inchikey"] for row in v01_rows}
    v01_names = {normalize_name_key(row["name"]) for row in v01_rows}
    al_rows = read_csv_rows(
        REPOSITORY_ROOT / "data" / "processed" / "al_round1_longlist.csv"
    )
    al_round1_keys = {row["inchikey"] for row in al_rows}
    solvfunc_fingerprints = _solvfunc_fingerprints(
        REPOSITORY_ROOT / "data" / "external" / "SolvFunc-87.csv"
    )
    cache = _load_cache(args.cache)
    resolved: list[Candidate] = []
    seen_keys: set[str] = set()
    unresolved: list[str] = []
    skipped_v01_name = 0
    pending_rows = []
    for row in rows:
        if normalize_name_key(row["compound_name"]) in v01_names:
            skipped_v01_name += 1
            continue
        pending_rows.append(row)
    if args.max_names > 0:
        pending_rows = pending_rows[: args.max_names]
    for index, row in enumerate(pending_rows, start=1):
        structure = resolve_structure(
            row["compound_name"],
            expected_formula=row.get("formula", ""),
            cache=cache,
            timeout=args.timeout,
            pause_seconds=args.pause_seconds,
        )
        if structure is None:
            unresolved.append(row["compound_name"])
            continue
        if structure.inchikey in seen_keys:
            continue
        candidate = _rank_candidate(
            row,
            structure,
            v01_keys=v01_keys,
            al_round1_keys=al_round1_keys,
            solvfunc_fingerprints=solvfunc_fingerprints,
        )
        if candidate is None:
            continue
        seen_keys.add(structure.inchikey)
        resolved.append(candidate)
        if index % 10 == 0:
            print(
                json.dumps(
                    {
                        "processed_input_rows": index,
                        "resolved_unique": len(resolved),
                        "unresolved": len(unresolved),
                    }
                )
            )
    if len(resolved) < args.target_new_compounds:
        raise SystemExit(
            "fewer resolved new compounds than target: "
            f"{len(resolved)} < {args.target_new_compounds}"
        )
    output_rows = _candidate_output_rows(
        resolved,
        target_new_compounds=args.target_new_compounds,
    )
    write_csv_rows(args.output, OUTPUT_FIELDS, output_rows)
    _write_cache(args.cache, cache)
    selected = sum(row["selected_for_v02"] == "true" for row in output_rows)
    result = {
        "input_candidate_rows": len(rows),
        "skipped_v01_exact_name": skipped_v01_name,
        "resolved_unique_new_structures": len(resolved),
        "selected_for_v02": selected,
        "future_compounds_minimum": len(v01_rows) + selected,
        "unresolved_names": len(unresolved),
        "output": str(args.output),
        "cache": str(args.cache),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
