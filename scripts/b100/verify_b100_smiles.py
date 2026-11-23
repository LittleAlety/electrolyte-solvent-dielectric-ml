"""B100-10: tautomer-sensitive SMILES verification against PubChem.

The InChIKey identity check (B100-9) returned ZERO mismatches, yet a real defect was
sitting in plain sight:

    name = "N-methylacetamide"
    SMILES recorded = CN=C(C)O      <- imidic acid (methyl acetimidate)
    correct amide   = CC(=O)NC

Both produce the SAME InChIKey, because standard InChI deliberately normalises mobile
hydrogens. So the InChIKey test cannot detect tautomer substitution -- and xTB computes
the electronic structure of whatever geometry the SMILES specifies. The recorded
imidate gave a dipole of 1.07 D; the amide's is several times larger. Every electronic
descriptor built on the wrong tautomer describes the wrong substance.

This script closes that hole:

  1. Ask PubChem for the authoritative CanonicalSMILES of each molecule (by InChIKey).
  2. Compare it with the SMILES used for the computation.
  3. Classify the difference:
       SAME              identical after canonicalisation
       STEREO_ONLY       same connectivity, differs only in stereo markers
       TAUTOMER_OR_FORM  connectivity differs -- the electronic structure computed
                         is NOT the recorded substance's
  4. Rows in the last class must be recomputed before their xTB values are used.

Output: outputs/b100/smiles_verification_b100.csv
        outputs/b100/smiles_verification_b100.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
CACHE = REPO_ROOT / "data" / "external" / "pubchem_smiles_b100"
GENERATOR = "verify_b100_smiles/1.0.0"

DESC = OUT / "xtb_descriptors_b100.csv"
PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
SLEEP_S = 0.22


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


def http_json(url: str):
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "plan-b-b100/1.0 (research)"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:                       # noqa: BLE001
        return 0, None


def fetch_canonical(inchikey: str) -> dict:
    cf = CACHE / f"{inchikey}.json"
    if cf.is_file():
        try:
            rec = json.loads(cf.read_text(encoding="utf-8"))
            if rec.get("checked"):
                return rec
        except Exception:                   # noqa: BLE001
            pass
    rec = {"inchikey": inchikey, "checked": True, "cid": None,
           "canonical_smiles": "", "connectivity_smiles": "",
           "iupac": "", "http_status": None}
    st, d = http_json(f"{PUBCHEM}/compound/inchikey/{inchikey}"
                      f"/property/SMILES,ConnectivitySMILES,IUPACName/JSON")
    rec["http_status"] = st
    if st == 200 and d:
        props = d.get("PropertyTable", {}).get("Properties", [])
        if props:
            p = props[0]
            rec["cid"] = p.get("CID")
            # PUG-REST returns the canonical SMILES under `SMILES`, and under
            # `ConnectivitySMILES` when the canonical form is requested. An earlier
            # version looked for `CanonicalSMILES`, which is the REQUEST name but not
            # the RESPONSE key -- so every row came back empty and the whole run was
            # mislabelled PUBCHEM_UNAVAILABLE.
            rec["canonical_smiles"] = (p.get("SMILES")
                                       or p.get("ConnectivitySMILES") or "")
            rec["connectivity_smiles"] = p.get("ConnectivitySMILES", "")
            rec["iupac"] = p.get("IUPACName", "")
    rec["checked"] = bool(rec["canonical_smiles"])
    cf.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8")
    return rec


def main() -> int:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if not DESC.is_file():
        print(f"FATAL: missing {DESC}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")

    rows_in = load(DESC)
    need = [r for r in rows_in
            if not (CACHE / f"{(r.get('inchikey') or '').strip()}.json").is_file()]
    if limit:
        need = need[:limit]
    print(f"[B100-10] molecules           : {len(rows_in)}")
    print(f"[B100-10] to query this run   : {len(need)}")

    for i, r in enumerate(need, 1):
        fetch_canonical((r.get("inchikey") or "").strip())
        if i % 25 == 0 or i == len(need):
            print(f"  {i}/{len(need)}")
        time.sleep(SLEEP_S)

    rows: list[dict] = []
    for r in rows_in:
        ik = (r.get("inchikey") or "").strip()
        recorded = (r.get("smiles") or "").strip()
        rec = {}
        cf = CACHE / f"{ik}.json"
        if cf.is_file():
            try:
                rec = json.loads(cf.read_text(encoding="utf-8"))
            except Exception:               # noqa: BLE001
                rec = {}
        pub = (rec.get("canonical_smiles") or "").strip()

        m_rec = Chem.MolFromSmiles(recorded) if recorded else None
        m_pub = Chem.MolFromSmiles(pub) if pub else None
        can_rec = Chem.MolToSmiles(m_rec) if m_rec else ""
        can_pub = Chem.MolToSmiles(m_pub) if m_pub else ""

        if not pub:
            verdict = "PUBCHEM_UNAVAILABLE"
        elif not m_pub:
            verdict = "PUBCHEM_SMILES_UNPARSABLE"
        elif can_rec == can_pub:
            verdict = "SAME"
        else:
            # same heavy-atom skeleton ignoring bond orders / H placement?
            def skeleton(m):
                if m is None:
                    return ""
                try:
                    mm = Chem.Mol(m)
                    Chem.RemoveStereochemistry(mm)
                    return Chem.MolToSmiles(mm, isomericSmiles=False,
                                            canonical=True)
                except Exception:           # noqa: BLE001
                    return ""
            if skeleton(m_rec) == skeleton(m_pub):
                verdict = "STEREO_ONLY"
            else:
                verdict = "TAUTOMER_OR_FORM"

        rows.append({
            "inchikey": ik,
            "name": r.get("name", ""),
            "smiles_used_for_xtb": recorded,
            "smiles_canonical_used": can_rec,
            "pubchem_canonical_smiles": can_pub,
            "pubchem_iupac": rec.get("iupac", ""),
            "pubchem_cid": rec.get("cid", ""),
            "verdict": verdict,
            "dipole_D": r.get("dipole_D", ""),
            "epsilon": r.get("epsilon", ""),
            "family": r.get("family", ""),
        })

    path = OUT / "smiles_verification_b100.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in sorted(rows, key=lambda z: (z["verdict"], z["name"])):
            w.writerow(r)

    counts = Counter(r["verdict"] for r in rows)
    bad = [r for r in rows if r["verdict"] == "TAUTOMER_OR_FORM"]
    stereo = [r for r in rows if r["verdict"] == "STEREO_ONLY"]
    unavailable = [r for r in rows
                   if r["verdict"] in ("PUBCHEM_UNAVAILABLE",
                                       "PUBCHEM_SMILES_UNPARSABLE")]

    doc = {
        "schema": "b100.smiles_verification/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "why_this_exists": (
            "B100-9 的 InChIKey 身份校验返回 0 个不匹配, 但 'N-methylacetamide' 行"
            "记录的 SMILES 是 CN=C(C)O (亚胺酸互变异构体) 而非酰胺 CC(=O)NC. "
            "标准 InChI 会归一化可移动氢, 因此两者 InChIKey 相同 —— "
            "InChIKey 校验在原理上无法发现互变异构体替换, 而 xTB 算的正是"
            "该 SMILES 对应的电子结构."
        ),
        "test": (
            "向 PubChem 按 InChIKey 查询权威 CanonicalSMILES, 与用于计算的 SMILES "
            "对比. 若连通性不同 (TAUTOMER_OR_FORM), 说明算出的电子描述符"
            "不属于记录的物质."
        ),
        "n_molecules": len(rows),
        "verdict_counts": dict(counts),
        "n_usable_after_check": counts.get("SAME", 0) + counts.get("STEREO_ONLY", 0),
        "n_tautomer_or_form_defect": len(bad),
        "n_stereo_only": len(stereo),
        "n_pubchem_unavailable": len(unavailable),
        "defects": [
            {"name": r["name"], "inchikey": r["inchikey"],
             "smiles_used": r["smiles_used_for_xtb"],
             "pubchem_smiles": r["pubchem_canonical_smiles"],
             "dipole_used": r["dipole_D"]}
            for r in bad[:50]
        ],
        "consequence": (
            f"{len(bad)} 个分子的 xTB 特征基于错误的互变异构体/质子化态, "
            "必须用 PubChem 权威 SMILES 重算后才能进入电子描述符建模集. "
            "在重算之前, 这些分子的电子描述符一律不得使用."
        ),
        "remediation": [
            "用 PubChem CanonicalSMILES 重写这些分子的输入几何",
            "用同一 GFN2-xTB 协议重算",
            "重算后重新运行本校验, 直到 TAUTOMER_OR_FORM 归零",
        ],
        "inputs": {"xtb_descriptors_b100": {"sha256": sha256_file(DESC)}},
        "output": {"path": str(path.relative_to(REPO_ROOT)),
                   "sha256": sha256_file(path), "rows": len(rows)},
    }
    j_path = OUT / "smiles_verification_b100.json"
    j_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"[B100-10] {j_path}")
    print(f"[B100-10] {path}")
    print(f"  verdicts = {dict(counts)}")
    print(f"  usable after check = {doc['n_usable_after_check']}/{len(rows)}")
    print(f"  TAUTOMER_OR_FORM defects = {len(bad)}")
    for r in bad[:12]:
        print(f"    {r['name'][:30]:30s} used={r['smiles_used_for_xtb'][:22]:22s} "
              f"pubchem={r['pubchem_canonical_smiles'][:22]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
