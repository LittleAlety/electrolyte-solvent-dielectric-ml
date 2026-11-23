"""B100-11: neutral-single-molecule filter -- exclude salts and ionic liquids.

PLAN B v6.0 states the core dataset is for NEUTRAL, SINGLE-MOLECULE pure liquids:

    离子液体、混合物、金属配合物不混入中性单分子核心数据集

The first qualified set violated that rule. The `sulfone_sulfoxide` family turned out
to contain ten IONIC LIQUIDS -- imidazolium / pyrrolidinium / ammonium cations paired
with the bis(trifluoromethylsulfonyl)imide (TFSI) anion -- because the TFSI anion's
sulfonyl groups match a sulfone SMARTS, and the expansion table records these salts as
`component_count = 1`.

That is precisely the failure the hard rule exists to prevent: a row count standing in
for an admissible sample. An ionic liquid's static permittivity is dominated by ionic
screening, not by the molecular dipole that the descriptors describe, so including them
would corrupt the very relationship the study measures.

Detection here is structural, not name-based:

  * NET CHARGE. A molecule whose SMILES parses with a non-zero formal charge on any
    atom is an ion, not a neutral liquid.
  * SEPARATED ION PAIR. A SMILES containing two or more disconnected fragments where
    at least one is charged is a salt.
  * METAL ATOM. Metal-containing complexes are outside the scope by the same rule.

Output: outputs/b100/neutral_filter_b100.csv
        outputs/b100/neutral_filter_b100.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "audit_b100_neutral_filter/1.0.0"

DESC = OUT / "xtb_descriptors_b100.csv"
REGISTRY = OUT / "molecule_registry_b100.csv"
PHASE = OUT / "phase_state_audit_b100.csv"
QUALIFIED = OUT / "qualified_molecules_b100.csv"

# The neutral filter is an ADMISSION criterion, so it must run over the whole
# candidate set -- not only the molecules that happen to have a melting point.
# Pointing it at the 257 xTB rows hid ten ionic liquids: they lacked an mp, so the
# phase gate had removed them for the WRONG reason, and a later mp fetch would have
# silently readmitted them.
SOURCE_MODE = "candidate_set"

# Elements that make a system a metal complex rather than an organic liquid.
METALS = {
    "Li", "Na", "K", "Rb", "Cs", "Be", "Mg", "Ca", "Sr", "Ba",
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd",
    "Al", "Ga", "In", "Sn", "Sb", "Tl", "Pb", "Bi",
    "La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho",
    "Er", "Tm", "Yb", "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir",
    "Pt", "Au", "Hg",
}


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
    """Return (verdict, reason)."""
    from rdkit import Chem

    if mol is None:
        return "EXCLUDE", "UNPARSABLE_SMILES"

    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
    charges = [Chem.GetFormalCharge(f) for f in frags]
    net = sum(charges)

    # metal check first: a metal makes it a complex regardless of charge
    for atom in mol.GetAtoms():
        if atom.GetSymbol() in METALS:
            return "EXCLUDE", f"CONTAINS_METAL_{atom.GetSymbol()}"

    if len(frags) > 1:
        if any(c != 0 for c in charges):
            return "EXCLUDE", (
                f"SALT_SEPARATED_ION_PAIR ({len(frags)} fragments, "
                f"charges={charges})")
        return "EXCLUDE", f"MULTI_COMPONENT_MIXTURE ({len(frags)} fragments)"

    if net != 0:
        return "EXCLUDE", f"NET_CHARGED_ION (net={net})"

    # a single neutral fragment is what the study needs
    return "KEEP", "NEUTRAL_SINGLE_MOLECULE"


def main() -> int:
    if not DESC.is_file():
        print(f"FATAL: missing {DESC}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)

    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")

    desc = load(DESC)
    registry = {(r.get("inchikey") or "").strip(): r for r in load(REGISTRY)}
    phase = {(r.get("inchikey") or "").strip(): r for r in load(PHASE)}
    qualified = {(r.get("inchikey") or "").strip(): r
                 for r in load(QUALIFIED)}

    # iterate the full candidate set, taking SMILES from the registry (which covers
    # every candidate) and filling in descriptor values where they exist
    desc_by_key = {(r.get("inchikey") or "").strip(): r for r in desc}
    universe = sorted(set(registry) | set(qualified))

    rows: list[dict] = []
    for ik in universe:
        reg = registry.get(ik, {})
        q = qualified.get(ik, {})
        d = desc_by_key.get(ik, {})
        smi = (reg.get("smiles") or d.get("smiles")
               or q.get("smiles") or "").strip()
        mol = Chem.MolFromSmiles(smi) if smi else None
        verdict, reason = classify(mol)
        ph = phase.get(ik, {})
        rows.append({
            "inchikey": ik,
            "name": reg.get("name") or d.get("name") or q.get("name", ""),
            "smiles": smi,
            "family": reg.get("family") or d.get("family", ""),
            "epsilon": reg.get("epsilon") or d.get("epsilon")
            or q.get("epsilon", ""),
            "T_K": reg.get("T_K") or d.get("T_K") or q.get("T_K", ""),
            "phase_verified": ph.get("phase_verified", ""),
            "has_xtb": "true" if (d.get("dipole_D") or "").strip() else
                       (q.get("has_xtb", "")),
            "verdict": verdict,
            "exclusion_reason": reason if verdict == "EXCLUDE" else "",
            "n_fragments": len(Chem.GetMolFrags(mol, sanitizeFrags=False))
            if mol is not None else "",
            "net_charge": Chem.GetFormalCharge(mol) if mol is not None else "",
        })

    path = OUT / "neutral_filter_b100.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in sorted(rows, key=lambda z: (z["verdict"], z["name"])):
            w.writerow(r)

    counts = Counter(r["verdict"] for r in rows)
    reasons = Counter(r["exclusion_reason"].split(" ")[0]
                      for r in rows if r["verdict"] == "EXCLUDE")
    excluded = [r for r in rows if r["verdict"] == "EXCLUDE"]
    kept = [r for r in rows if r["verdict"] == "KEEP"]

    n_kept_phase_verified = sum(1 for r in kept
                                if r["phase_verified"] == "true")
    n_kept_with_xtb = sum(1 for r in kept
                          if r["has_xtb"] == "true")

    doc = {
        "schema": "b100.neutral_filter/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "rule": (
            "PLAN B v6.0: 离子液体、混合物、金属配合物不混入中性单分子核心数据集."
        ),
        "why_this_was_needed": (
            "首轮合格集把 10 个离子液体归入了 sulfone_sulfoxide 家族 —— "
            "它们是咪唑/吡咯烷/铵阳离子与 TFSI 阴离子组成的盐, 因为 TFSI 的"
            "磺酰基匹配了砜的 SMARTS, 而扩展表把这些盐记为 component_count=1. "
            "离子液体的静态介电常数由离子屏蔽主导, 不由描述符所刻画的分子偶极决定, "
            "纳入会破坏本研究要测的关系."
        ),
        "detection": [
            "单分子净电荷非零 -> 离子",
            "SMILES 含多个不连通片段且至少一个带电 -> 盐",
            "含金属原子 -> 配合物",
        ],
        "n_input": len(rows),
        "verdict_counts": dict(counts),
        "exclusion_reasons": dict(reasons),
        "result": {
            "n_neutral_single_molecule": len(kept),
            "n_excluded": len(excluded),
            "n_kept_and_phase_verified": n_kept_phase_verified,
            "n_kept_with_xtb": n_kept_with_xtb,
            "hard_threshold": 100,
            "meets_threshold": n_kept_phase_verified >= 100,
            "gap": max(0, 100 - n_kept_phase_verified),
        },
        "excluded_examples": [
            {"name": r["name"], "smiles": r["smiles"][:70],
             "reason": r["exclusion_reason"],
             "epsilon": r["epsilon"], "family": r["family"]}
            for r in excluded[:20]
        ],
        "impact_on_family_coverage": (
            "排除后 sulfone_sulfoxide 家族将归零, 因为其 10 个成员全是离子液体. "
            "该家族的覆盖缺口必须靠新增中性砜/亚砜分子填补, 不能保留离子液体凑数."
        ),
        "inputs": {"xtb_descriptors_b100": {"sha256": sha256_file(DESC)},
                   "molecule_registry_b100": {"sha256": sha256_file(REGISTRY)},
                   "phase_state_audit_b100": {"sha256": sha256_file(PHASE)}},
        "output": {"path": str(path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(path), "rows": len(rows)},
    }
    j_path = OUT / "neutral_filter_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"[B100-11] {j_path}")
    print(f"[B100-11] {path}")
    print(f"  input            = {len(rows)}")
    print(f"  verdicts         = {dict(counts)}")
    print(f"  exclusion reasons= {dict(reasons)}")
    print(f"  neutral & verified = {n_kept_phase_verified}  "
          f"(threshold 100: {n_kept_phase_verified >= 100})")
    print()
    print("  excluded examples:")
    for r in excluded[:12]:
        print(f"    {r['name'][:40]:40s} {r['exclusion_reason'][:44]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
