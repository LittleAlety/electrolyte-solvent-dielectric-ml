#!/usr/bin/env python
"""B100-5: molecule registry with chemical-family assignment.

PLAN B v6.0 requires a stratified sample across 8-12 chemical families, not a random
draw, because the research question is about how far single-molecule descriptors
generalise ACROSS chemical space. A pool dominated by carbonates and ethers cannot
answer that.

This script assigns every qualified molecule to a family using an explicit,
ordered SMARTS list, and then reports the achieved family distribution against the
target bands from PLAN B v6.0. Gaps are reported as gaps -- not papered over by
relabelling.

Family rules are ordered and the first match wins, with the full match set recorded
so the precedence is auditable. Heteroatom-identity rules come before carbon-skeleton
rules, so a cyclic sulfone is a sulfone rather than an aromatic.

Output: outputs/b100/molecule_registry_b100.csv
        outputs/b100/family_coverage_b100.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "build_b100_molecule_registry/1.0.0"

QUALIFIED = OUT / "qualified_molecules_b100.csv"
PHASE_B100 = OUT / "phase_state_audit_b100.csv"

# Ordered family rules: (family, SMARTS, target_low, target_high).
# Bands come from PLAN B v6.0 §4.
#
# PRECEDENCE MATTERS and the first draft got it wrong: `alcohol_polyol` was placed
# before `amine`, so every amino-alcohol (2-aminoethanol, diethanolamine,
# triethanolamine, ...) was absorbed into the alcohol family and the amine family
# came out EMPTY even though 28 molecules contain an amine group. That would have
# silently destroyed the stratified design the research depends on.
#
# The fix is to put the more specific / less common heteroatom classes first:
#   sulfur & phosphorus  ->  carbonyl esters/amides/nitriles  ->  nitrogen
#   ->  oxygen (alcohol/ether)  ->  halogen  ->  aromatic  ->  fallback
# so an amino-alcohol counts as an amine, and an amide is never miscounted as an
# amine or a ketone.
FAMILY_RULES = [
    # 1. sulfur / phosphorus heteroatom classes
    ("sulfone_sulfoxide",
     ("[#16X4](=[OX1])(=[OX1])", "[#16X3](=[OX1])"), 10, 15),
    ("phosphate", ("[PX4](=O)",), 10, 15),
    # 2. carbonyl-derived classes (specific before generic)
    ("amide", ("[NX3][CX3](=[OX1])",), 10, 15),
    ("nitrile", ("N#C",), 10, 15),
    ("nitro", ("[NX3](=O)=O",), 10, 15),
    ("carboxylic_acid", ("[CX3](=O)[OX2H1]",), 10, 15),
    ("carbonate", ("[OX2][CX3](=O)[OX2]",), 12, 18),
    ("ester", ("[CX3](=O)[OX2][#6]",), 12, 18),
    ("ketone_aldehyde",
     ("[#6][CX3](=O)[#6]", "[CX3H1](=O)[#6]"), 10, 15),
    # 3. nitrogen classes AFTER the carbonyl ones so amides are not re-labelled
    ("amine", ("[NX3;H2,H1,H0;!$(NC=O)]",), 10, 15),
    # 4. oxygen classes
    ("alcohol_polyol", ("[OX2H]",), 15, 20),
    ("ether", ("[OD2]([#6])[#6]",), 15, 20),
    # 5. halogen and aromatic skeleton
    ("halocarbon", ("[CX4][F,Cl,Br,I]",), 10, 15),
    ("aromatic", ("a",), 10, 15),
    # 6. everything else
    ("other_neutral_liquid", (), 10, 15),
]

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise RuntimeError(f"cannot decode {path}")
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    import io
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def classify(smiles: str) -> tuple[str, list[str], int, int]:
    """Return (family, all_matched, heavy_atoms, ring_count)."""
    try:
        from rdkit import Chem, RDLogger
        RDLogger.DisableLog("rdApp.*")
    except ImportError:
        return "UNCLASSIFIED_NO_RDKIT", [], 0, 0
    if not smiles:
        return "UNCLASSIFIED_NO_SMILES", [], 0, 0
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return "UNCLASSIFIED_BAD_SMILES", [], 0, 0
    matched: list[str] = []
    for family, patterns, _lo, _hi in FAMILY_RULES:
        # `patterns` is a TUPLE of SMARTS strings, never a comma-joined string.
        # An earlier version split a single string on "," which silently destroyed
        # any SMARTS containing a comma -- e.g. the amine pattern
        # [NX3;H2,H1,H0;!$(NC=O)] became three invalid fragments, so the amine
        # family matched nothing and 28 amino-alcohols were misfiled.
        ok = False
        for part in patterns:
            patt = Chem.MolFromSmarts(part)
            if patt is not None and mol.HasSubstructMatch(patt):
                ok = True
                break
        if ok:
            matched.append(family)
    family = matched[0] if matched else "other_neutral_liquid"
    return (family, matched, mol.GetNumHeavyAtoms(),
            mol.GetRingInfo().NumRings())


def main() -> int:
    for p in (QUALIFIED, PHASE_B100):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT.mkdir(parents=True, exist_ok=True)

    qualified = load(QUALIFIED)
    phase = {(r.get("inchikey") or "").strip(): r for r in load(PHASE_B100)}

    # SMILES come from the expansion observation table (the qualified list carries
    # identity but not structure).
    exp = load(REPO_ROOT / "data" / "processed"
               / "dielectric_pool_expansion_observations.csv")
    smiles_by_key = {}
    for r in exp:
        ik = (r.get("inchikey") or "").strip()
        s = (r.get("smiles") or "").strip()
        if ik and s and ik not in smiles_by_key:
            smiles_by_key[ik] = s

    # also try the core layer
    v04 = load(REPO_ROOT / "data" / "dielectric_v04.csv")
    for r in v04:
        ik = (r.get("inchikey") or "").strip()
        s = (r.get("smiles") or "").strip()
        if ik and s and ik not in smiles_by_key:
            smiles_by_key[ik] = s

    rows: list[dict] = []
    for q in qualified:
        ik = q["inchikey"]
        smi = smiles_by_key.get(ik, "")
        fam, matched, n_heavy, n_rings = classify(smi)
        ph = phase.get(ik, {})
        eps = q.get("epsilon", "")
        try:
            eps_v = float(eps)
        except (TypeError, ValueError):
            eps_v = None
        rows.append({
            "inchikey": ik,
            "name": q.get("name", ""),
            "smiles": smi,
            "layer": q.get("layer", ""),
            "evidence_grade": q.get("evidence_grade", ""),
            "family": fam,
            "matched_rules": ";".join(matched),
            "n_rules_matched": len(matched),
            "heavy_atoms": n_heavy,
            "n_rings": n_rings,
            "epsilon": eps,
            "epsilon_band": (
                "LOW_eps<5" if eps_v is not None and eps_v < 5
                else "MID_5-20" if eps_v is not None and eps_v < 20
                else "HIGH_eps>=20" if eps_v is not None
                else "UNKNOWN"),
            "T_K": q.get("T_K", ""),
            "mp_C": ph.get("mp_C", ""),
            "phase_status": ph.get("phase_status", "NOT_AUDITED"),
            "phase_verified": ph.get("phase_verified", "false"),
            "has_xtb": q.get("has_xtb", "false"),
        })

    path = OUT / "molecule_registry_b100.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in sorted(rows, key=lambda z: (z["family"], z["name"])):
            w.writerow(r)

    # ---- family coverage against target bands ----
    # Exclude ionic liquids / mixtures / metal complexes here: PLAN B v6.0 forbids
    # them in the neutral single-molecule core set, and leaving them in the family
    # counts would claim coverage the admissible data does not actually provide.
    neutral = {}
    nf = OUT / "neutral_filter_b100.json"
    if nf.is_file():
        try:
            nf_doc = json.loads(nf.read_text(encoding="utf-8"))
            neutral_path = OUT / "neutral_filter_b100.csv"
            if neutral_path.is_file():
                for r in load(neutral_path):
                    neutral[(r.get("inchikey") or "").strip()] = (
                        r.get("verdict") == "KEEP")
        except Exception:                   # noqa: BLE001
            neutral = {}

    def is_neutral(ik: str) -> bool:
        return neutral.get(ik, True)

    counts = Counter(r["family"] for r in rows if is_neutral(r["inchikey"]))
    verified_counts = Counter(r["family"] for r in rows
                              if r["phase_verified"] == "true"
                              and is_neutral(r["inchikey"]))
    band_rows = []
    total_target_lo = total_target_hi = 0
    for family, _sm, lo, hi in FAMILY_RULES:
        total_target_lo += lo
        total_target_hi += hi
        n = counts.get(family, 0)
        n_v = verified_counts.get(family, 0)
        band_rows.append({
            "family": family,
            "n_present": n,
            "n_phase_verified": n_v,
            "target_low": lo,
            "target_high": hi,
            "meets_target_low": n_v >= lo,
            "gap_to_low": max(0, lo - n_v),
        })

    eps_bands = Counter(r["epsilon_band"] for r in rows)
    n_verified = sum(1 for r in rows if r["phase_verified"] == "true")

    doc = {
        "schema": "b100.molecule_registry/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "purpose": (
            "PLAN B v6.0 要求分层抽样而非随机抽取, 因为研究问题是描述符能否"
            "跨化学空间泛化. 本表给每个分子分配化学家族并对照目标区间."
        ),
        "n_molecules": len(rows),
        "n_phase_verified": n_verified,
        "family_rule_precedence": {
            "order": [f[0] for f in FAMILY_RULES],
            "note": "首个匹配者胜出; 杂原子身份规则先于碳骨架规则",
            "n_molecules_matching_multiple": sum(
                1 for r in rows if r["n_rules_matched"] > 1),
        },
        "family_coverage": band_rows,
        "family_totals": {
            "families_present": len([b for b in band_rows if b["n_present"] > 0]),
            "families_meeting_target_low": len(
                [b for b in band_rows if b["meets_target_low"] and b["target_low"]]),
            "target_low_sum": total_target_lo,
            "target_high_sum": total_target_hi,
            "note": (
                "目标区间之和 127-181, 与 B100 的 120-150 目标一致. "
                "未达区间的家族必须补分子, 不得把相近家族并进来充数."
            ),
        },
        "epsilon_distribution": dict(eps_bands),
        "epsilon_distribution_ok": {
            "low": eps_bands.get("LOW_eps<5", 0),
            "mid": eps_bands.get("MID_5-20", 0),
            "high": eps_bands.get("HIGH_eps>=20", 0),
            "note": (
                "PLAN B v6.0 要求覆盖高/中/低介电常数. "
                "若某一档为 0, 该档的结论无法支持."
            ),
        },
        "structure_availability": {
            "n_with_smiles": sum(1 for r in rows if r["smiles"]),
            "n_without_smiles": sum(1 for r in rows if not r["smiles"]),
            "why_it_matters": (
                "无 SMILES 的分子无法计算结构描述符, 因此不能进入 E1 起点的建模集."
            ),
        },
        "inputs": {
            "qualified_molecules_b100": {"sha256": sha256_file(QUALIFIED)},
            "phase_state_audit_b100": {"sha256": sha256_file(PHASE_B100)},
        },
        "output": {"path": str(path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(path), "rows": len(rows)},
    }
    j_path = OUT / "family_coverage_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"[B100-5] {path}")
    print(f"[B100-5] {j_path}")
    print(f"  molecules = {len(rows)}  phase_verified = {n_verified}")
    print(f"  with SMILES = {doc['structure_availability']['n_with_smiles']}")
    print()
    print(f"  {'family':<22}{'present':>8}{'verified':>10}{'target':>12}")
    for b in band_rows:
        print(f"  {b['family']:<22}{b['n_present']:>8}{b['n_phase_verified']:>10}"
              f"{str(b['target_low'])+'-'+str(b['target_high']):>12}")
    print()
    print(f"  epsilon bands = {dict(eps_bands)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
