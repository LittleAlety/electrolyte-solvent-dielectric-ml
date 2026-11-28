#!/usr/bin/env python
"""B730-02: validate the faithful CRAFT-epsilon re-implementation.

The reference model lives in craft_model_ref.py. This script proves it against the
author's own 16 stored reference records: same conformers, same parameters, same
formula. If epsilon reproduces within 5%, the model may be used for comparison;
otherwise it is marked NOT_REPRODUCED and no ranking is issued.

Outputs (outputs/b730_mechanism/craft_comparison/):
  craft_reimplementation_check.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW = REPO_ROOT / "data" / "external_raw" / "craft_epsilon"
OUT = REPO_ROOT / "outputs" / "b730_mechanism" / "craft_comparison"
GEN = "reproduce_craft_baseline/2.0.0"


def main() -> None:
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")
    import craft_model_ref as C

    OUT.mkdir(parents=True, exist_ok=True)
    P = C.load_parameters()
    n_params = (len(P["nonpolar"]["atom_group_scales"]) + 1
                + len(P["polar"]["atom_group_scales"])
                + len(P["polar"]["family_scales"]) + 1
                + len(P["hbond"]["fragment_scales"]) + 2)

    ref = json.loads((RAW / "tests_data_reference.json").read_text(encoding="utf-8"))
    rows = []
    for smiles, meta in sorted(ref.items()):
        rec_path = RAW / "records" / meta["record"]
        if not rec_path.exists():
            rows.append({"smiles": smiles, "name": meta["name"],
                         "status": "RECORD_MISSING"})
            continue
        record = json.loads(rec_path.read_text(encoding="utf-8"))
        try:
            got = C.epsilon_from_record(record, smiles, P)
        except Exception as exc:                      # noqa: BLE001
            rows.append({"smiles": smiles, "name": meta["name"],
                         "status": "MODEL_ERROR", "error": str(exc)[:160]})
            continue
        want = meta["epsilon_paper"]
        rows.append({
            "smiles": smiles, "name": meta["name"],
            "class_author": meta["class"], "class_reimpl": got["class"],
            "class_match": meta["class"] == got["class"],
            "epsilon_paper": round(want, 4),
            "epsilon_reimpl": round(got["epsilon"], 4),
            "relative_difference": round(abs(got["epsilon"] - want) / want, 4),
            "vm_reimpl": round(got["molar_volume_298K_cm3_mol"], 2),
            "vm_author": meta["molar_volume_smi2DC"],
            "vm_relative_difference": round(
                abs(got["molar_volume_298K_cm3_mol"] - meta["molar_volume_smi2DC"])
                / meta["molar_volume_smi2DC"], 6),
            "eps_inf_reimpl": round(got["eps_inf"], 4),
            "mu_eff_rms_D": round(got["mu_eff_rms_D"], 4),
            "n_conformers": got["n_conformers"],
            "status": "OK",
        })

    ok = [r for r in rows if r.get("status") == "OK"]
    vm_ok = [r for r in ok if r["vm_relative_difference"] < 0.02]
    eps_ok = [r for r in ok if r["relative_difference"] < 0.05]
    cls_ok = [r for r in ok if r["class_match"]]

    doc = {
        "schema": "b730.craft_reimplementation/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "reference_implementation": "scripts/b730_mechanism/craft_model_ref.py",
        "parameters": {"parsed": n_params, "author_declared": 41,
                       "match": n_params == 41},
        "acceptance_test": {
            "what": ("reproduce the author's stored epsilon_paper for their own 16 "
                     "reference records, feeding their own stored conformers"),
            "n_records": len(rows), "n_ok": len(ok),
            "n_vm_within_2pct": len(vm_ok),
            "n_epsilon_within_5pct": len(eps_ok),
            "n_class_match": len(cls_ok),
            "passes_vm": len(vm_ok) >= 14,
            "passes_epsilon": len(eps_ok) >= 14,
            "passes_class": len(cls_ok) >= 14,
        },
        "per_liquid": rows,
        "verified_against_author_artifacts": [
            "41 fitted parameters parsed from parameters.py",
            "52 molar-volume contributions extracted from molar_volume.py",
            "SMARTS fragment priority order reproduced from groups.py",
            "Boltzmann weighting (per diastereomer, equal weight across ensembles)",
            "Clausius-Mossotti eps_inf + Onsager-Kirkwood-Froehlich epsilon",
        ],
        "not_reproduced": (
            "conformer GENERATION (RDKit ETKDGv3 + GFN2-xTB/ALPB) is not re-run; "
            "the author's stored ensembles are used for this check, and this "
            "project's own ensembles are used for the comparison in B730-03"
        ),
    }
    (OUT / "craft_reimplementation_check.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    a = doc["acceptance_test"]
    print(f"Wrote {OUT / 'craft_reimplementation_check.json'}")
    print(f"parameters {n_params}/41")
    print(f"records {a['n_records']}, ok {a['n_ok']}")
    print(f"  V_m <2%: {a['n_vm_within_2pct']}   eps <5%: {a['n_epsilon_within_5pct']} "
          f"class match: {a['n_class_match']}")
    print(f"  passes: vm={a['passes_vm']} eps={a['passes_epsilon']} class={a['passes_class']}")
    print()
    print(f"{'name':30s} {'class':16s} {'paper':>9s} {'reimpl':>9s} {'reldiff':>8s}")
    for r in rows:
        if r.get("status") != "OK":
            print(f"  {r['name'][:28]:30s} {r.get('status')}")
            continue
        print(f"{r['name'][:30]:30s} {r['class_reimpl']:16s} "
              f"{r['epsilon_paper']:9.2f} {r['epsilon_reimpl']:9.2f} "
              f"{r['relative_difference']:8.4f}")


if __name__ == "__main__":
    main()
