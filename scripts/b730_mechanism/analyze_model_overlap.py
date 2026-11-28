#!/usr/bin/env python
"""B730-03: data overlap between CRAFT-epsilon and the frozen CORE239, plus a
fair-comparison attempt that is explicit about what CAN be compared.

Three overlap questions are answered separately, because they are different:
  DATABASE overlap  - do the two studies draw on the same archives?
  MOLECULE overlap  - which InChIKeys appear in both?
  SOURCE overlap    - do they cite the same PRIMARY measurements?

The CRAFT training set (1393 liquids) is NOT shipped: only 16 reference ensembles
are in the repository. So molecule overlap can only be measured against those 16,
and the honest statement is "5 of 16 reference liquids are in CORE239; the other
1380-odd training molecules cannot be checked".

Fair comparison: CRAFT's model needs per-atom charges, atomic dipoles and per-atom
polarizabilities from a GFN2-xTB/ALPB ensemble. This project has ORCA r2SCAN-3c
outputs without those arrays. So the full CRAFT model cannot be evaluated on our
conformers, and the comparison is limited to:

  * CRAFT on ITS OWN 16 reference molecules vs our models on the same molecules
    (n=5 actually overlapping -> reported but n is too small to rank)
  * the two model FORMS decomposed side by side (eps_inf route, orientation term)

Anything that would require the CRAFT ensemble arrays is marked NOT_COMPARABLE.

Outputs (outputs/b730_mechanism/craft_comparison/):
  craft_overlap_audit.json
  craft_fair_comparison.csv
"""

from __future__ import annotations

import csv
import io
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW = REPO_ROOT / "data" / "external_raw" / "craft_epsilon"
OUT = REPO_ROOT / "outputs" / "b730_mechanism" / "craft_comparison"
GEN = "analyze_model_overlap/1.0.0"

DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"
E4 = REPO_ROOT / "outputs" / "b700" / "B706_E4_lofo_predictions.csv"

N_A = 6.02214076e23
EPS0 = 8.8541878128e-12
KB = 1.380649e-23
DEBYE = 1e-21 / 299792458.0
AU_TO_A3 = 0.14818471
T_K = 298.15


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def fnum(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def main() -> None:
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")
    import craft_model_ref as C

    OUT.mkdir(parents=True, exist_ok=True)
    desc = {r["inchikey"]: r for r in load_csv(DESC)}
    lofo = {r["inchikey"]: r for r in load_csv(E4)}
    ref = json.loads((RAW / "tests_data_reference.json").read_text(encoding="utf-8"))
    P = C.load_parameters()

    # ---------------- molecule overlap -----------------------------------
    overlap_rows = []
    for smiles, meta in sorted(ref.items()):
        mol = Chem.MolFromSmiles(smiles)
        ik = Chem.MolToInchiKey(mol) if mol else None
        in_core = ik in desc if ik else False
        frozen_eps = fnum(desc.get(ik, {}).get("epsilon")) if in_core else None
        overlap_rows.append({
            "smiles": smiles,
            "name": meta["name"],
            "inchikey": ik or "",
            "craft_class": meta["class"],
            "craft_epsilon_paper": meta["epsilon_paper"],
            "in_core239": in_core,
            "core_epsilon": frozen_eps if frozen_eps is not None else "",
            "label_agreement": (round(abs(meta["epsilon_paper"] - frozen_eps)
                                      / frozen_eps, 4)
                                if frozen_eps else ""),
        })
    n_overlap = sum(1 for r in overlap_rows if r["in_core239"])

    # ---------------- model-form comparison on the overlapping set --------
    cmp_rows = []
    for r in overlap_rows:
        if not r["in_core239"]:
            continue
        ik = r["inchikey"]
        d = desc[ik]
        mu = fnum(d.get("dipole_D_v7"))
        alpha = fnum(d.get("polarizability_au_v7"))
        vm_m3 = fnum(d.get("molar_volume_m3_mol"))
        eps = fnum(d.get("epsilon"))
        if not (mu and alpha and vm_m3 and eps):
            continue
        rec_path = RAW / "records" / next(
            (m["record"] for s, m in ref.items() if s == r["smiles"]), "")
        craft = None
        if rec_path.exists():
            try:
                craft = C.epsilon_from_record(
                    json.loads(rec_path.read_text(encoding="utf-8")),
                    r["smiles"], P)
            except Exception:                       # noqa: BLE001
                craft = None
        vm_cm3 = vm_m3 * 1e6
        x = min(4 * math.pi / 3 * N_A * alpha * AU_TO_A3 * 1e-24 / vm_cm3, 0.99)
        eps_inf_ours = (1 + 2 * x) / (1 - x)
        cmp_rows.append({
            "inchikey": ik,
            "name": d.get("name", ""),
            "epsilon_true": eps,
            "craft_on_author_ensemble": round(craft["epsilon"], 4) if craft else "",
            "craft_eps_inf": round(craft["eps_inf"], 4) if craft else "",
            "craft_vm_cm3": round(craft["molar_volume_298K_cm3_mol"], 3) if craft else "",
            "craft_mu_eff_D": round(craft["mu_eff_rms_D"], 4) if craft else "",
            "our_epsilon_inf_from_alpha": round(eps_inf_ours, 4),
            "our_mu_D": mu,
            "our_vm_cm3": round(vm_cm3, 3),
            "our_alpha_A3": round(alpha * AU_TO_A3, 3),
            "vm_difference_cm3": (round(vm_cm3 - craft["molar_volume_298K_cm3_mol"], 3)
                                  if craft else ""),
            "eps_inf_difference": (round(eps_inf_ours - craft["eps_inf"], 4)
                                   if craft else ""),
            "lofo_residual_our_model": fnum(lofo.get(ik, {}).get("resid")) or "",
        })

    if cmp_rows:
        with (OUT / "craft_fair_comparison.csv").open("w", newline="",
                                                      encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(cmp_rows[0].keys()))
            w.writeheader()
            w.writerows(cmp_rows)

    # ---------------- what cannot be compared ----------------------------
    doc = {
        "schema": "b730.craft_overlap/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "craft_source": {
            "repository": "https://github.com/simonmb/craft-epsilon",
            "pinned_commit": "65fa0fb0a55838a656769ed717d41d52f1516c4a",
            "licence": "MIT",
            "training_set_size_claimed": 1393,
            "training_set_shipped": False,
            "reference_records_shipped": len(ref),
        },
        "database_overlap": {
            "status": "UNRESOLVED",
            "why": ("CRAFT does not ship its training table, so which archives it "
                    "drew on cannot be verified from the artefact. The paper text is "
                    "the only source for that claim, and a claim is not a dataset."),
        },
        "molecule_overlap": {
            "measurable_against": "the 16 shipped reference molecules only",
            "n_reference": len(ref),
            "n_in_core239": n_overlap,
            "fraction_of_reference_in_core": round(n_overlap / len(ref), 4),
            "molecules": [r["name"] for r in overlap_rows if r["in_core239"]],
            "unmeasurable": (
                "the remaining ~1380 training molecules are not shipped, so the true "
                "molecule overlap between CRAFT's training set and CORE239 is "
                "UNKNOWN. Any statement that the two datasets are 'largely disjoint' "
                "or 'largely overlapping' would be unfounded."
            ),
        },
        "source_overlap": {
            "status": "NOT_TESTABLE",
            "why": ("primary references are not shipped per molecule; CRAFT reports "
                    "only aggregate fits, so whether the same original measurements "
                    "back both studies cannot be determined."),
        },
        "fair_comparison": {
            "possible": "model FORM decomposition on the overlapping molecules",
            "n_overlapping_evaluable": len(cmp_rows),
            "cannot_do": [
                "run CRAFT on OUR conformer ensembles: CRAFT needs per-atom charges, "
                "atomic dipoles and per-atom polarizabilities from a GFN2-xTB/ALPB "
                "ensemble; ORCA r2SCAN-3c outputs do not carry those arrays",
                "compare CRAFT's published CV metrics with our MAE: different molecule "
                "sets, different labels, different splits. Marked NOT_COMPARABLE.",
                "claim CRAFT beats us or vice versa on a common benchmark: n=%d is far "
                "too small to rank two models" % len(cmp_rows),
            ],
            "rows": cmp_rows,
            "ranking_issued": False,
            "reason_no_ranking": (
                "with n<10 overlapping molecules and different label sources, any "
                "ranking would be noise. The comparison reports physics (eps_inf "
                "route, molar volume, effective dipole) rather than accuracy."
            ),
        },
        "what_craft_adds_physically": [
            "an explicit Clausius-Mossotti eps_inf from the molecular polarizability",
            "per-atom-group scaling of polarizability (3-21 fitted scales)",
            "polar-group-resolved dipole vectors instead of one total dipole",
            "a group-contribution molar volume (Bouteloup & Mathieu) rather than a "
            "computed cavity volume",
            "conformer ensembles with Boltzmann averaging of BOTH alpha and mu",
        ],
        "what_this_project_has_that_craft_does_not": [
            "explicit r2SCAN-3c electronic structure for every molecule in the queue",
            "a family-resolved error decomposition with measured failure mechanisms",
            "source-independence accounting at the primary-study level",
            "candidate-pool sensitivity of the screening metric",
        ],
    }
    (OUT / "craft_overlap_audit.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'craft_overlap_audit.json'}")
    if cmp_rows:
        print(f"Wrote {OUT / 'craft_fair_comparison.csv'}")
    print()
    print(f"reference molecules: {len(ref)}, in CORE239: {n_overlap}")
    print(f"overlapping & evaluable: {len(cmp_rows)}")
    print()
    if cmp_rows:
        print(f"{'name':26s} {'eps_true':>8s} {'craft_eps':>9s} {'eps_inf_us':>10s} "
              f"{'eps_inf_craft':>12s} {'dVm':>8s}")
        for r in cmp_rows:
            print(f"{r['name'][:26]:26s} {r['epsilon_true']:8.2f} "
                  f"{str(r['craft_on_author_ensemble']):>9s} "
                  f"{r['our_epsilon_inf_from_alpha']:10.3f} "
                  f"{str(r['craft_eps_inf']):>12s} {str(r['vm_difference_cm3']):>8s}")
    print()
    print("ranking issued:", doc["fair_comparison"]["ranking_issued"])


if __name__ == "__main__":
    main()
