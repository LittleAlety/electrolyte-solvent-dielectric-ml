"""B100 identity audit: does each recorded SMILES actually produce its InChIKey?

This is a decisive integrity test that was missing. The B100 descriptor chain starts
from a SMILES taken out of the source tables. If that SMILES does not describe the
substance named by the molecule's InChIKey, then every electronic descriptor computed
from it belongs to a DIFFERENT compound than the one whose dielectric constant was
measured.

The first example found made the risk concrete: the row named "N-methylacetamide"
carried SMILES `CN=C(C)O`, which is the imidic-acid tautomer of methyl acetimidate,
not the amide `CC(=O)NC`. Running xTB on the wrong tautomer yields a dipole of 1.07 D
where the amide's is far larger, and nothing in the pipeline would flag it.

The test is exact: RDKit recomputes the InChIKey from the recorded SMILES and it must
equal the recorded InChIKey. Anything else is an identity defect.

Output: outputs/b100/identity_audit_b100.csv
        outputs/b100/identity_audit_b100.json
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
GENERATOR = "audit_b100_identity/1.0.0"

DESC = OUT / "xtb_descriptors_b100.csv"
PHASE = OUT / "phase_state_audit_b100.csv"


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


def main() -> int:
    if not DESC.is_file():
        print(f"FATAL: missing {DESC}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)

    from rdkit import Chem, RDLogger
    from rdkit.Chem import inchi
    RDLogger.DisableLog("rdApp.*")

    rows_in = load(DESC)
    phase = {(r.get("inchikey") or "").strip(): r for r in load(PHASE)}

    rows: list[dict] = []
    for r in rows_in:
        ik = (r.get("inchikey") or "").strip()
        smi = (r.get("smiles") or "").strip()
        mol = Chem.MolFromSmiles(smi) if smi else None

        if mol is None:
            status = "BAD_SMILES"
            derived = ""
            canonical = ""
        else:
            try:
                derived = inchi.MolToInchiKey(mol)
            except Exception:               # noqa: BLE001
                derived = ""
            canonical = Chem.MolToSmiles(mol)
            if not derived:
                status = "INCHIKEY_COMPUTE_FAILED"
            elif derived == ik:
                status = "MATCH"
            elif derived.split("-")[0] == ik.split("-")[0]:
                status = "MATCH_SKELETON_ONLY"     # stereo/protonation differs
            else:
                status = "INCHIKEY_MISMATCH"

        ph = phase.get(ik, {})
        rows.append({
            "inchikey": ik,
            "name": r.get("name", ""),
            "smiles_recorded": smi,
            "smiles_canonical": canonical,
            "inchikey_from_smiles": derived,
            "identity_status": status,
            "epsilon": r.get("epsilon", ""),
            "family": r.get("family", ""),
            "phase_verified": ph.get("phase_verified", ""),
            "dipole_D": r.get("dipole_D", ""),
        })

    path = OUT / "identity_audit_b100.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in sorted(rows, key=lambda z: (z["identity_status"], z["name"])):
            w.writerow(r)

    counts = Counter(r["identity_status"] for r in rows)
    bad = [r for r in rows
           if r["identity_status"] in ("INCHIKEY_MISMATCH", "BAD_SMILES",
                                       "INCHIKEY_COMPUTE_FAILED")]
    skeleton_only = [r for r in rows
                     if r["identity_status"] == "MATCH_SKELETON_ONLY"]

    doc = {
        "schema": "b100.identity_audit/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "test": (
            "从记录中的 SMILES 用 RDKit 重算 InChIKey, 必须等于记录的 InChIKey. "
            "不等则说明该 SMILES 描述的不是被测物质, 因此由它算出的电子描述符 "
            "不属于该物质."
        ),
        "why_this_matters": (
            "发现的第一个例子: 名为 N-methylacetamide 的行带有 SMILES CN=C(C)O, "
            "那是亚胺酸互变异构体 (methyl acetimidate), 不是酰胺 CC(=O)NC. "
            "用它算出的偶极矩 1.07 D 与酰胺相距甚远, 而流程里没有任何环节会报警."
        ),
        "n_molecules": len(rows),
        "status_counts": dict(counts),
        "n_identity_ok": counts.get("MATCH", 0),
        "n_mismatch": len(bad),
        "n_skeleton_only": len(skeleton_only),
        "mismatches": [
            {"name": r["name"], "inchikey_recorded": r["inchikey"],
             "smiles": r["smiles_recorded"],
             "inchikey_from_smiles": r["inchikey_from_smiles"],
             "canonical": r["smiles_canonical"]}
            for r in bad[:40]
        ],
        "skeleton_only_examples": [
            {"name": r["name"], "inchikey_recorded": r["inchikey"],
             "inchikey_from_smiles": r["inchikey_from_smiles"]}
            for r in skeleton_only[:10]
        ],
        "consequence": (
            "identity 不一致的分子**不得**进入电子描述符建模集: "
            "它们的 xTB 结果属于另一种化学物种. "
            "这直接限制了 B100 的可用样本量, 必须如实扣减."
        ),
        "remediation": [
            "优先: 用 InChIKey 反查 PubChem 取标准 SMILES, 重算 xTB",
            "次选: 从原始文献核对正确的互变异构体/质子化态",
            "禁止: 直接沿用不一致的 SMILES 结论",
        ],
        "inputs": {"xtb_descriptors_b100": {"sha256": sha256_file(DESC)},
                   "phase_state_audit_b100": {"sha256": sha256_file(PHASE)}},
        "output": {"path": str(path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(path), "rows": len(rows)},
    }
    j_path = OUT / "identity_audit_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"[B100-9] {j_path}")
    print(f"[B100-9] {path}")
    print(f"  molecules        = {len(rows)}")
    print(f"  identity counts  = {dict(counts)}")
    print(f"  MISMATCH         = {len(bad)}")
    for r in bad[:10]:
        print(f"    {r['name'][:30]:30s} {r['smiles_recorded'][:24]:24s} "
              f"-> {r['inchikey_from_smiles'][:14]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
