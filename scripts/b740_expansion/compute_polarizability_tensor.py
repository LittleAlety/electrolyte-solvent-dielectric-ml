#!/usr/bin/env python
"""B742-01: polarizability tensor, eigenvalues and anisotropy from ORCA output.

v7.0-v7.3 used only the ISOTROPIC polarizability (one number per molecule). The
ORCA outputs already contain the full 3x3 static polarizability tensor and its
diagonalised eigenvalues, which were never extracted. That is the cheapest
unexploited physical information in the project: the anisotropy tells you how
directional the electron cloud is, which matters for orientational correlation in
a liquid, while the isotropic value alone cannot.

Standard definitions, units = atomic units (bohr^3) as printed by ORCA:

    alpha_bar = (a1 + a2 + a3) / 3
    Delta_alpha = sqrt( 1/2 [ (a1-a2)^2 + (a2-a3)^2 + (a3-a1)^2 ] )

CONVENTION GUARD: ORCA prints the tensor in the molecular frame it chose, so the
six off-diagonal components are NOT comparable between molecules without an
alignment step. The three EIGENVALUES are frame-independent and are what this
script uses for any cross-molecule statement. Raw components are stored for audit
only and every output says so.

Outputs (outputs/b740_expansion/molecular_descriptors/):
  polarizability_tensor.csv
  polarizability_anisotropy_summary.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b740_expansion" / "molecular_descriptors"
GEN = "compute_polarizability_tensor/1.0.0"

OPT_RES = REPO_ROOT / "outputs" / "b700" / "B701_DFT" / "production_239" / "results_opt"
SP_RES = REPO_ROOT / "outputs" / "b700" / "B701_DFT" / "production_239" / "results_sp"
DESC = REPO_ROOT / "outputs" / "b700" / "orca_r2scan3c_descriptors.csv"

AU_TO_A3 = 0.14818471

# The tensor block ORCA prints after a Polar run:
#   STATIC POLARIZABILITY TENSOR (Dipole/Dipole)
#   ... The raw cartesian tensor (atomic units): <3 rows of 3 floats>
#   diagonalized tensor: <3 floats>
#   ...
#   Isotropic polarizability : <float>
RE_TENSOR_BLOCK = re.compile(
    r"STATIC POLARIZABILITY TENSOR[^\n]*\n(.*?)(?:Polarizability tensor calculation done|\Z)",
    re.S)
RE_RAW = re.compile(
    r"The raw cartesian tensor \(atomic units\):\s*\n"
    r"\s*([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s*\n"
    r"\s*([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s*\n"
    r"\s*([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)")
RE_EIG = re.compile(r"diagonalized tensor:\s*\n\s*([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)"
                    r"\s+([-+]?\d+\.\d+)")
RE_ISO = re.compile(r"Isotropic polarizability\s*:\s*([-+]?\d+\.\d+)")


def load_csv(path: Path) -> list[dict]:
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


def anisotropy(a1, a2, a3):
    """Delta_alpha per the standard traceless-anisotropy definition."""
    return math.sqrt(0.5 * ((a1 - a2) ** 2 + (a2 - a3) ** 2 + (a3 - a1) ** 2))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    desc = {r["inchikey"]: r for r in load_csv(DESC)}

    rows = []
    missing = []
    for base, tag in ((OPT_RES, "opt"), (SP_RES, "sp")):
        # the two fetch batches landed with different nesting: results_opt/ holds
        # <inchikey>/job.out directly, results_sp/ holds jobs/<inchikey>/job.out.
        # Probe both so neither layer is silently skipped (the first run reported
        # "opt 0" because it only looked at base/"jobs").
        jobs = base / "jobs" if (base / "jobs").is_dir() else base
        if not jobs.is_dir():
            continue
        for d in sorted(p for p in jobs.iterdir() if p.is_dir()):
            f = d / "job.out"
            if not f.exists():
                continue
            txt = f.read_text(encoding="utf-8", errors="replace")
            blk = RE_TENSOR_BLOCK.search(txt)
            if not blk:
                missing.append((d.name, tag, "no tensor block"))
                continue
            body = blk.group(1)
            raw = RE_RAW.search(body)
            eig = RE_EIG.search(body)
            iso = RE_ISO.search(body)
            if not (raw and eig and iso):
                missing.append((d.name, tag, "incomplete tensor block"))
                continue
            comp = [float(raw.group(i)) for i in range(1, 10)]
            e = sorted(float(eig.group(i)) for i in range(1, 4))
            iso_v = float(iso.group(1))
            # consistency: the isotropic value must equal the eigenvalue mean
            iso_from_eig = sum(e) / 3.0
            rows.append({
                "inchikey": d.name,
                "name": desc.get(d.name, {}).get("name", ""),
                "family": desc.get(d.name, {}).get("family", ""),
                "layer": tag,
                "epsilon": desc.get(d.name, {}).get("epsilon", ""),
                "alpha_xx": comp[0], "alpha_xy": comp[1], "alpha_xz": comp[2],
                "alpha_yx": comp[3], "alpha_yy": comp[4], "alpha_yz": comp[5],
                "alpha_zx": comp[6], "alpha_zy": comp[7], "alpha_zz": comp[8],
                "alpha_iso_orca": iso_v,
                "alpha_iso_from_eigs": round(iso_from_eig, 5),
                "iso_consistency_abs_diff": round(abs(iso_v - iso_from_eig), 6),
                "eig_1": e[0], "eig_2": e[1], "eig_3": e[2],
                "alpha_bar_au": round(iso_from_eig, 5),
                "alpha_bar_A3": round(iso_from_eig * AU_TO_A3, 5),
                "delta_alpha_au": round(anisotropy(*e), 5),
                "delta_alpha_A3": round(anisotropy(*e) * AU_TO_A3, 5),
                "anisotropy_ratio": round(anisotropy(*e) / iso_from_eig, 5)
                                    if iso_from_eig else "",
                "tensor_symmetric": bool(
                    abs(comp[1] - comp[3]) < 1e-4 and abs(comp[2] - comp[6]) < 1e-4
                    and abs(comp[5] - comp[7]) < 1e-4),
            })

    out_csv = OUT / "polarizability_tensor.csv"
    if rows:
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    by_layer = Counter((r["inchikey"], r["layer"]) for r in rows)
    dup = [k for k, v in by_layer.items() if v > 1]
    max_iso_diff = max((r["iso_consistency_abs_diff"] for r in rows), default=None)
    n_sym = sum(1 for r in rows if r["tensor_symmetric"])

    by_fam = {}
    for r in rows:
        if r["layer"] != "opt":
            continue
        by_fam.setdefault(r["family"], []).append(r["anisotropy_ratio"])

    def stats(v):
        v = [x for x in v if x not in ("", None)]
        if not v:
            return {"n": 0}
        s = sorted(v)
        return {"n": len(s), "median": round(statistics.median(s), 4),
                "min": round(s[0], 4), "max": round(s[-1], 4)}

    doc = {
        "schema": "b740.polarizability_tensor/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "units": {
            "raw_components": "bohr^3 (atomic units, as printed by ORCA)",
            "converted_columns": f"A^3 via AU_TO_A3 = {AU_TO_A3}",
        },
        "definitions": {
            "alpha_bar": "(eig1+eig2+eig3)/3",
            "delta_alpha": "sqrt(0.5*((a1-a2)^2+(a2-a3)^2+(a3-a1)^2))",
            "anisotropy_ratio": "delta_alpha / alpha_bar (dimensionless)",
        },
        "convention_guard": (
            "ORCA prints the tensor in its own molecular frame, so the six "
            "off-diagonal components are NOT comparable across molecules without "
            "alignment. Only the three eigenvalues are frame-independent; every "
            "cross-molecule statement uses them, and the raw components are stored "
            "for audit only."
        ),
        "n_records": len(rows),
        "n_molecules_opt": len({r["inchikey"] for r in rows if r["layer"] == "opt"}),
        "n_molecules_sp": len({r["inchikey"] for r in rows if r["layer"] == "sp"}),
        "sanity": {
            "max_iso_vs_eigenmean_abs_diff": max_iso_diff,
            "n_tensor_symmetric": n_sym,
            "n_records": len(rows),
            "duplicate_molecule_layer_pairs": len(dup),
        },
        "anisotropy_ratio_by_family_opt": {
            k: stats(v) for k, v in sorted(by_fam.items()) if len(v) >= 3},
        "extraction_failures": missing[:20],
        "n_extraction_failures": len(missing),
    }
    (OUT / "polarizability_anisotropy_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {OUT / 'polarizability_anisotropy_summary.json'}")
    print(f"records: {len(rows)} (opt {doc['n_molecules_opt']}, sp {doc['n_molecules_sp']})")
    print(f"sanity: {doc['sanity']}")
    print(f"extraction failures: {len(missing)}")
    print()
    print(f"{'family':24s} {'n':>4s} {'median Delta/alpha_bar':>22s}")
    for k, v in sorted(doc["anisotropy_ratio_by_family_opt"].items(),
                       key=lambda kv: -kv[1]["median"]):
        print(f"  {k:22s} {v['n']:4d} {v['median']:22.4f}")


if __name__ == "__main__":
    main()
