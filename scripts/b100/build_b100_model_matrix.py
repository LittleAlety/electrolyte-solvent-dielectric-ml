#!/usr/bin/env python
"""B100-13: build the modelling feature matrix for the 257-molecule set.

This assembles the X0/X1 descriptor layers required by PLAN B v6.0 §5, plus the two
volume-normalised quantities the plan calls out explicitly because they correspond to
the leading terms of the Kirkwood-Froehlich relation:

    mu^2 / V_m        the orientational (dipole) contribution
    alpha / V_m       the distortional (polarisability) contribution

Necessary caution, stated once and repeated in the manifest: these two quantities are
NOT a formula for the liquid permittivity. The Kirkwood g factor -- the intermolecular
orientational correlation -- is the decisive term in an associating liquid and is
absent from any single-molecule descriptor. That absence is the hypothesis under test,
not something this table can resolve.

X0 (RDKit, structural): composition, H-bond counts, TPSA, molecular volume,
molar volume, formal charge, ring count, rotatable bonds, Morgan fingerprint summary
X1 (GFN2-xTB, electronic): dipole, polarisability, HOMO-LUMO gap, total energy

Everything is joined on InChIKey so a molecule cannot acquire another's descriptors.

Output: outputs/b100/model_matrix_b100.csv
        outputs/b100/model_matrix_b100.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "build_b100_model_matrix/1.0.0"

XTAB = OUT / "xtb_descriptors_b100.csv"
PHASE = OUT / "phase_state_audit_b100.csv"
NEUTRAL = OUT / "neutral_filter_b100.csv"
REGISTRY = OUT / "molecule_registry_b100.csv"
EXP_FEAT = (REPO_ROOT / "data" / "processed"
            / "dielectric_pool_expansion_features.csv")

NA = 6.02214076e23
PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


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


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def rdkit_descriptors(smiles: str) -> dict:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        return {}
    mol_h = Chem.AddHs(mol)
    d = {
        "heavy_atom_count": mol.GetNumHeavyAtoms(),
        "n_rings": mol.GetRingInfo().NumRings(),
        "n_rotatable": rdMolDescriptors.CalcNumRotatableBonds(mol),
        "hbd": rdMolDescriptors.CalcNumHBD(mol),
        "hba": rdMolDescriptors.CalcNumHBA(mol),
        "tpsa_A2": round(Descriptors.TPSA(mol), 4),
        "formal_charge": Chem.GetFormalCharge(mol),
        "mw": round(Descriptors.MolWt(mol), 4),
        "fraction_csp3": round(rdMolDescriptors.CalcFractionCSP3(mol), 4),
        "n_aromatic_atoms": sum(1 for a in mol.GetAtoms() if a.GetIsAromatic()),
        "n_hetero": sum(1 for a in mol.GetAtoms()
                        if a.GetSymbol() not in ("C", "H")),
        "n_halogen": sum(1 for a in mol.GetAtoms()
                         if a.GetSymbol() in ("F", "Cl", "Br", "I")),
        "n_N": sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "N"),
        "n_O": sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "O"),
        "n_S": sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "S"),
    }
    # Morgan fingerprint summary: bit count and mean density carry most of the
    # structural information without exploding the feature count.
    try:
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        d["morgan2_nbits"] = int(fp.GetNumOnBits())
    except Exception:                       # noqa: BLE001
        d["morgan2_nbits"] = ""
    # 3D molecular volume from a single embedded conformer, matching the convention
    # already used in the expansion layer.
    try:
        if AllChem.EmbedMolecule(mol_h, randomSeed=42) == 0:
            from rdkit.Chem import AllChem as A2
            vol = A2.ComputeMolVolume(mol_h)
            d["molecular_volume_A3"] = round(vol, 4)
            d["molar_volume_m3_mol"] = vol * 1e-30 * NA
        else:
            d["molecular_volume_A3"] = ""
            d["molar_volume_m3_mol"] = ""
    except Exception:                       # noqa: BLE001
        d["molecular_volume_A3"] = ""
        d["molar_volume_m3_mol"] = ""
    return d


def main() -> int:
    for p in (XTAB, PHASE):
        if not p.is_file():
            print(f"FATAL: missing {p}", file=sys.stderr)
            return 2
    OUT.mkdir(parents=True, exist_ok=True)

    xtab = load(XTAB)
    phase = {(r.get("inchikey") or "").strip(): r for r in load(PHASE)}
    neutral = {(r.get("inchikey") or "").strip(): r for r in load(NEUTRAL)}
    registry = {(r.get("inchikey") or "").strip(): r for r in load(REGISTRY)}
    exp_feat = {(r.get("inchikey") or "").strip(): r
                for r in load(EXP_FEAT)}

    rows: list[dict] = []
    skipped: Counter = Counter()
    for r in xtab:
        ik = (r.get("inchikey") or "").strip()
        if not ik:
            skipped["no_inchikey"] += 1
            continue
        ph = phase.get(ik, {})
        if ph.get("phase_verified") != "true":
            skipped["not_phase_verified"] += 1
            continue
        nf = neutral.get(ik, {})
        if nf and nf.get("verdict") == "EXCLUDE":
            skipped["not_neutral"] += 1
            continue
        status = (r.get("status") or "").strip()
        if status not in ("EXISTING", "OK", "CACHED"):
            skipped["xtb_not_usable"] += 1
            continue

        smi = (r.get("smiles") or "").strip()
        d0 = rdkit_descriptors(smi)
        if not d0:
            skipped["rdkit_failed"] += 1
            continue

        dipole = fnum(r.get("dipole_D"))
        polar_au = fnum(r.get("polarizability_au"))
        gap = fnum(r.get("homo_lumo_gap_ev"))
        energy = fnum(r.get("total_energy_hartree"))
        if dipole is None:
            skipped["no_dipole"] += 1
            continue

        # molar volume: prefer the expansion table's value (already validated there),
        # else compute from the RDKit volume
        mv = fnum(exp_feat.get(ik, {}).get("molar_volume_m3_mol"))
        if mv is None:
            mv = d0.get("molar_volume_m3_mol") or None
        mol_vol = fnum(exp_feat.get(ik, {}).get("molecular_volume_A3"))
        if mol_vol is None:
            mol_vol = d0.get("molecular_volume_A3") or None

        # volume-normalised leading terms
        mu2_over_vm = mu2_over_vm_au = None
        alpha_over_vm = None
        if mv and mv > 0:
            # dipole in Debye -> C m ; 1 D = 3.33564e-30 C m
            mu_cm = dipole * 3.33564e-30
            mu2_over_vm = (mu_cm ** 2) / mv          # C^2 m / mol
            alpha_over_vm = (polar_au * 1.648777e-41) / mv if polar_au else None

        eps = fnum(r.get("epsilon")) or fnum(ph.get("epsilon"))
        t_k = fnum(r.get("T_K")) or fnum(ph.get("T_K"))

        row = {
            "inchikey": ik,
            "name": r.get("name", ""),
            "smiles": smi,
            "family": registry.get(ik, {}).get("family")
            or r.get("family", ""),
            "evidence_grade": r.get("evidence_grade", ""),
            "epsilon": eps if eps is not None else "",
            "T_K": t_k if t_k is not None else "",
            # ---- X0 structure ----
            **{k: v for k, v in d0.items()},
            "molecular_volume_A3": mol_vol if mol_vol is not None else "",
            "molar_volume_m3_mol": mv if mv is not None else "",
            # ---- X1 electronic ----
            "dipole_D": dipole,
            "polarizability_au": polar_au if polar_au is not None else "",
            "homo_lumo_gap_ev": gap if gap is not None else "",
            "total_energy_hartree": energy if energy is not None else "",
            # ---- volume-normalised leading terms ----
            "mu_sq_over_Vm": mu2_over_vm if mu2_over_vm is not None else "",
            "alpha_over_Vm": alpha_over_vm if alpha_over_vm is not None else "",
            # ---- association descriptors for H4 ----
            "is_protic": "true" if (d0.get("hbd") or 0) > 0 else "false",
            "has_strong_donor": "true" if (d0.get("hbd") or 0) > 0
            and (d0.get("n_O") or 0) + (d0.get("n_N") or 0) > 0 else "false",
        }
        # epsilon band for H4 stratification
        if eps is not None:
            row["epsilon_band"] = ("LOW_lt5" if eps < 5
                                   else "MID_5to20" if eps < 20 else "HIGH_ge20")
            row["association_class"] = (
                "WEAK_LOW_EPS" if (eps < 10 and (d0.get("hbd") or 0) == 0)
                else "STRONG_HIGH_EPS" if eps >= 20
                else "INTERMEDIATE")
        else:
            row["epsilon_band"] = "UNKNOWN"
            row["association_class"] = "UNKNOWN"
        rows.append(row)

    # completeness check on the columns E1 needs
    X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
               "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
               "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
               "n_hetero", "n_halogen", "n_N", "n_O", "n_S", "morgan2_nbits",
               "mw"]
    X1_COLS = ["dipole_D", "polarizability_au", "homo_lumo_gap_ev",
               "total_energy_hartree"]

    def present(cols):
        out = []
        for c in cols:
            n = sum(1 for r in rows if str(r.get(c, "")).strip() != "")
            out.append({"column": c, "n_present": n,
                        "coverage": round(n / max(len(rows), 1), 4)})
        return out

    path = OUT / "model_matrix_b100.csv"
    if rows:
        fields = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in sorted(rows, key=lambda z: z["name"]):
                w.writerow(r)

    fam_counts = Counter(r["family"] for r in rows)
    bands = Counter(r["epsilon_band"] for r in rows)
    assoc = Counter(r["association_class"] for r in rows)
    grades = Counter(r["evidence_grade"] for r in rows)

    doc = {
        "schema": "b100.model_matrix/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "n_molecules": len(rows),
        "skipped": dict(skipped),
        "layers": {
            "X0_structural": {"columns": X0_COLS, "source": "RDKit 2026.03",
                              "coverage": present(X0_COLS)},
            "X1_electronic": {"columns": X1_COLS,
                              "source": "GFN2-xTB (see xtb_coverage_b100.json)",
                              "coverage": present(X1_COLS)},
            "volume_normalised": {
                "columns": ["mu_sq_over_Vm", "alpha_over_Vm"],
                "coverage": present(["mu_sq_over_Vm", "alpha_over_Vm"]),
                "caveat": (
                    "mu^2/V_m 与 alpha/V_m 是 Kirkwood-Froehlich 关系的**前导项近似**, "
                    "不是液体介电常数的公式. 偶极关联因子 g 是缔合液体的决定性项, "
                    "不在任何单分子描述符中 —— 这一缺失正是 H4 要检验的对象."
                ),
            },
            "X2_dft": {"status": "NOT_AVAILABLE",
                       "reason": ("本机无 DFT 程序 (ORCA/Psi4 等). A 仓库的 "
                                  "r2SCAN-3c 计算提交到 HPC 集群运行, 本环境无"
                                  "集群访问. 需要授权与外部资源.")},
            "X3_conformer": {"status": "NOT_COMPUTED",
                             "note": "可用 xTB 做构象搜索, 尚未执行."},
            "X4_md": {"status": "NOT_COMPUTED",
                      "reason": "液相 MD 需要独立的 MD 引擎, 本环境未安装."},
        },
        "composition": {
            "by_family": dict(fam_counts.most_common()),
            "by_epsilon_band": dict(bands),
            "by_association_class": dict(assoc),
            "by_evidence_grade": dict(grades),
        },
        "h4_stratification_ready": {
            "low_eps_weak": assoc.get("WEAK_LOW_EPS", 0),
            "high_eps_strong": assoc.get("STRONG_HIGH_EPS", 0),
            "intermediate": assoc.get("INTERMEDIATE", 0),
            "note": (
                "H4 要求比较低介电弱缔合 vs 高介电强缔合液体的预测能力. "
                "两组的样本量决定该检验的功效; 若任一组过小必须报 INSUFFICIENT_POWER."
            ),
        },
        "inputs": {
            "xtb_descriptors_b100": {"sha256": sha256_file(XTAB)},
            "phase_state_audit_b100": {"sha256": sha256_file(PHASE)},
        },
        "output": {"path": str(path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(path) if path.is_file() else None,
                   "rows": len(rows)},
    }
    j_path = OUT / "model_matrix_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"[B100-13] {j_path}")
    print(f"[B100-13] {path}")
    print(f"  molecules          = {len(rows)}   skipped={dict(skipped)}")
    print(f"  epsilon bands      = {dict(bands)}")
    print(f"  association classes= {dict(assoc)}")
    print(f"  evidence grades    = {dict(grades)}")
    print(f"  families           = {len(fam_counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
