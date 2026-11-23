"""B100-12: family-gap expansion from the unselected static NBS 514 rows.

The qualified set has 257 molecules but seven families fall short of the PLAN B v6.0
stratification bands -- most severely carbonate, amide, sulfone and nitrile. The
research question is about cross-chemical-space generalisation, so a pool concentrated
in halocarbons and alcohols cannot answer it.

The repository holds one further admissible source that was never tapped: 636 NBS
Circular 514 transcription rows, of which only 392 were carried into the expansion
table. Of the remaining 244, exactly **117 carry no frequency footnote** -- i.e. they
fall under the same source-level STATIC definition already accepted for the other
392. That makes them a legitimate extension of the same Q2 evidence layer, not a
relaxation of standards.

This script identifies which of those rows are:

  * static by source definition (no frequency footnote)
  * precise enough to use (three or more significant figures)
  * resolvable to a structure (InChIKey + SMILES from the NBS structure cache)
  * NEW molecules, not already in the qualified set
  * neutral single molecules (the same filter as B100-11)

and reports their chemical families, so the gap can be filled deliberately rather
than by taking whatever happens to be available.

Output: outputs/b100/family_gap_candidates_b100.csv
        outputs/b100/family_gap_candidates_b100.json
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
GENERATOR = "build_b100_family_gap_candidates/1.0.0"

NBS_PARTS = [REPO_ROOT / "data" / "interim" / f"nbs514_organic_part{i}.csv"
             for i in range(1, 5)]
STRUCT_CACHE = REPO_ROOT / "data" / "interim" / "nbs514_structure_cache.json"
EXP_OBS = (REPO_ROOT / "data" / "processed"
           / "dielectric_pool_expansion_observations.csv")
QUALIFIED = OUT / "qualified_molecules_b100.csv"
PHASE = OUT / "phase_state_audit_b100.csv"
REGISTRY = OUT / "molecule_registry_b100.csv"
NEUTRAL = OUT / "neutral_filter_b100.csv"
FAMILY = OUT / "family_coverage_b100.json"

GOOD_QUALITY = {"three_figures", "four_figures"}

FAMILY_RULES = [
    ("sulfone_sulfoxide",
     ("[#16X4](=[OX1])(=[OX1])", "[#16X3](=[OX1])")),
    ("phosphate", ("[PX4](=O)",)),
    ("amide", ("[NX3][CX3](=[OX1])",)),
    ("nitrile", ("N#C",)),
    ("nitro", ("[$([NX3](=O)=O),$([N+](=O)[O-])]",)),
    ("carboxylic_acid", ("[CX3](=O)[OX2H1]",)),
    ("carbonate", ("[OX2][CX3](=O)[OX2]",)),
    ("ester", ("[CX3](=O)[OX2][#6]",)),
    ("ketone_aldehyde", ("[#6][CX3](=O)[#6]", "[CX3H1](=O)[#6]")),
    ("amine", ("[NX3;H2,H1,H0;!$(NC=O)]",)),
    ("alcohol_polyol", ("[OX2H]",)),
    ("ether", ("[OD2]([#6])[#6]",)),
    ("halocarbon", ("[CX4][F,Cl,Br,I]",)),
    ("aromatic", ("a",)),
]

METALS = {"Li", "Na", "K", "Rb", "Cs", "Mg", "Ca", "Sr", "Ba", "Al", "Ga",
          "In", "Sn", "Sb", "Tl", "Pb", "Bi", "Ti", "V", "Cr", "Mn", "Fe",
          "Co", "Ni", "Cu", "Zn", "Zr", "Mo", "Ag", "Cd", "Hg", "Pt", "Au"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    import io
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def classify(mol) -> tuple[str, str]:
    from rdkit import Chem
    if mol is None:
        return "UNCLASSIFIED", "NO_STRUCTURE"
    for atom in mol.GetAtoms():
        if atom.GetSymbol() in METALS:
            return "EXCLUDE_METAL", f"CONTAINS_METAL_{atom.GetSymbol()}"
    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
    if len(frags) > 1:
        ch = [Chem.GetFormalCharge(f) for f in frags]
        if any(c != 0 for c in ch):
            return "EXCLUDE_ION", f"SALT ({len(frags)} frags, charges={ch})"
        return "EXCLUDE_MIXTURE", f"MULTI_COMPONENT ({len(frags)} frags)"
    if Chem.GetFormalCharge(mol) != 0:
        return "EXCLUDE_ION", f"NET_CHARGED ({Chem.GetFormalCharge(mol)})"
    matched = []
    for fam, pats in FAMILY_RULES:
        for p in pats:
            patt = Chem.MolFromSmarts(p)
            if patt is not None and mol.HasSubstructMatch(patt):
                matched.append(fam)
                break
    if not matched:
        return "other_neutral_liquid", "NEUTRAL_NO_RULE"
    return matched[0], ";".join(matched)


def main() -> int:
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")

    for p in (EXP_OBS, STRUCT_CACHE):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2

    nbs: list[dict] = []
    for p in NBS_PARTS:
        if p.is_file():
            nbs.extend(load(p))
    cache = json.loads(STRUCT_CACHE.read_text(encoding="utf-8"))
    selected_ids = {(r.get("source_id") or "").strip()
                    for r in load(EXP_OBS)}

    known_keys = {(r.get("inchikey") or "").strip()
                  for r in load(QUALIFIED)}
    known_keys.discard("")
    # Dedup must be against EVERY molecule the project already knows about, not only
    # the qualified ones. Restricting it to the qualified set let through molecules
    # that were already present in the expansion table but had been excluded (e.g.
    # 1,2-dichloroethane and chlorobenzene reappeared as "new" candidates).
    for r in load(EXP_OBS):
        k = (r.get("inchikey") or "").strip()
        if k:
            known_keys.add(k)
    for r in load(NEUTRAL):
        k = (r.get("inchikey") or "").strip()
        if k:
            known_keys.add(k)
    for r in load(REPO_ROOT / "data" / "dielectric_v04.csv"):
        k = (r.get("inchikey") or "").strip()
        if k:
            known_keys.add(k)
    registry = {(r.get("inchikey") or "").strip(): r
                for r in load(REGISTRY)}
    phase = {(r.get("inchikey") or "").strip(): r for r in load(PHASE)}

    fam_doc = json.loads(FAMILY.read_text(encoding="utf-8")) \
        if FAMILY.is_file() else {}
    gaps = {b["family"]: b["gap_to_low"]
            for b in fam_doc.get("family_coverage", []) if b["gap_to_low"] > 0}

    # candidates: unselected, no frequency footnote, good precision
    candidates: list[dict] = []
    counts = Counter()
    for r in nbs:
        sid = (r.get("source_id") or "").strip()
        if sid in selected_ids:
            counts["already_selected"] += 1
            continue
        if (r.get("frequency_note") or "").strip():
            counts["has_frequency_footnote"] += 1
            continue
        quality = (r.get("source_quality") or "").strip()
        if quality not in GOOD_QUALITY:
            counts["low_precision"] += 1
            continue
        counts["static_and_precise"] += 1

        # resolve structure from the cache, keyed by name|formula
        name = (r.get("compound_name") or "").strip()
        formula = (r.get("formula") or "").strip()
        key = f"{name.lower()}|{formula}"
        rec = cache.get(key) if isinstance(cache, dict) else None
        if not rec and isinstance(cache, dict):
            # tolerate case differences in the name part
            for ck, cv in cache.items():
                if "|" in ck and ck.split("|")[1] == formula:
                    if ck.split("|")[0].lower() == name.lower():
                        rec = cv
                        break
        if not rec or rec.get("status") != "resolved":
            counts["structure_unresolved"] += 1
            continue
        ik = (rec.get("inchikey") or "").strip()
        smi = (rec.get("smiles") or "").strip()
        if not ik or not smi:
            counts["structure_incomplete"] += 1
            continue
        if ik in known_keys:
            counts["already_in_qualified_or_excluded"] += 1
            continue

        mol = Chem.MolFromSmiles(smi)
        family, detail = classify(mol)
        if family.startswith("EXCLUDE"):
            counts["not_neutral"] += 1
            counts[f"neutral_excl_{detail.split(' ')[0]}"] += 1
            continue

        t_k = r.get("T_K") or ""
        candidates.append({
            "source_id": sid,
            "nbs_name": name,
            "resolved_name": rec.get("resolved_name", ""),
            "inchikey": ik,
            "smiles": smi,
            "formula": formula,
            "dielectric": r.get("dielectric", ""),
            "T_K": t_k,
            "t_C": r.get("t_C", ""),
            "source_page": r.get("source_page", ""),
            "source_quality": quality,
            "references": r.get("references", ""),
            "frequency_note": "",
            "family": family,
            "matched_rules": detail,
            "fills_gap": "true" if family in gaps else "false",
            "gap_size": gaps.get(family, 0),
        })

    path = OUT / "family_gap_candidates_b100.csv"
    if candidates:
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(candidates[0].keys()))
            w.writeheader()
            for r in sorted(candidates,
                            key=lambda z: (z["fills_gap"] != "true", z["family"],
                                           z["resolved_name"])):
                w.writerow(r)

    by_family = Counter(c["family"] for c in candidates)
    gap_fill = Counter(c["family"] for c in candidates if c["fills_gap"] == "true")

    doc = {
        "schema": "b100.family_gap_candidates/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "why": (
            "B100 合格集 257 个分子但有 7 个家族低于 PLAN B v6.0 的分层区间. "
            "NBS 514 转录有 636 行, 只有 392 行进过扩展表; 其余 244 行中 117 行"
            "**不带频率脚注**, 因此与已接受的 392 行同属来源级静态定义 —— "
            "这是同一 Q2 证据层的合规延伸, 不是放宽标准."
        ),
        "screening_funnel": dict(counts),
        "n_candidates": len(candidates),
        "by_family": dict(by_family.most_common()),
        "gap_filling": {
            "gaps_before": gaps,
            "candidates_that_fill_a_gap": dict(gap_fill.most_common()),
            "n_gap_filling": sum(gap_fill.values()),
        },
        "admissibility_of_this_source": [
            "同属 NBS Circular 514 批判性汇编 (Q2)",
            "无频率脚注 => 来源级静态定义, 与已采纳的 392 行判据一致",
            "精度 >= 三位有效数字 (与已采纳子集同档或更严)",
            "结构经 PubChem 解析 (InChIKey + SMILES)",
            "已剔除离子/混合物/金属配合物",
            "按 InChIKey 去重, 不与现有 257 个重复",
        ],
        "what_is_NOT_done_yet": [
            "这些分子尚未通过相态检查 (需要熔点)",
            "尚未计算 xTB 特征",
            "尚未纳入合格集 —— 本脚本只识别候选",
        ],
        "inputs": {
            "nbs514_transcription": [{"path": str(p.relative_to(REPO_ROOT)),
                                     "rows": len(load(p))}
                                    for p in NBS_PARTS if p.is_file()],
            "structure_cache": {"sha256": sha256_file(STRUCT_CACHE),
                                "entries": len(cache)},
            "expansion_observations": {"sha256": sha256_file(EXP_OBS)},
        },
        "output": {"path": str(path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(path) if path.is_file() else None,
                   "rows": len(candidates)},
    }
    j_path = OUT / "family_gap_candidates_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"[B100-12] {j_path}")
    print(f"[B100-12] {path}")
    print(f"  funnel: {dict(counts)}")
    print(f"  candidates: {len(candidates)}")
    print(f"  gaps before: {gaps}")
    print(f"  gap-filling candidates: {dict(gap_fill.most_common())}")
    print()
    for c in candidates[:15]:
        print(f"    {c['resolved_name'][:32]:32s} {c['family']:18s} "
              f"eps={c['dielectric']:>7s} T={c['T_K']:>7s} "
              f"{'GAP' if c['fills_gap'] == 'true' else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
