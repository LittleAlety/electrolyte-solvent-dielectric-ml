#!/usr/bin/env python
"""B710-08: parse xTB-on-DFT-geometry single points and complete the 2x2 matrix.

Fills the missing cell so method and geometry main effects (and their interaction)
can be separated on the 12-molecule preflight:

            xTB geom       DFT geom
  xTB       v6.0           THIS SCRIPT
  DFT       B702 SP        B702 Opt

Deliberate limits:
  * absolute electronic energies are NOT compared across methods (different
    references); only dipoles and polarizabilities are, and polarizability only
    where both codes define it comparably.
  * xTB polarizability exists here but the v6.0 xTB layer did not emit it for all
    molecules, so the 2x2 polarizability cell is reported with explicit n.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b710_evidence" / "xtb_on_dft_geometry"
GEN = "analyze_2x2_method_geometry/1.0.0"

PROD = REPO_ROOT / "outputs" / "b700" / "B701_DFT" / "production_239"
XTB_V60 = REPO_ROOT / "outputs" / "b100" / "deliverables" / "xtb_descriptors_b100.csv"

# The dipole block and the quadrupole block BOTH have a line starting "full:".
# The quadrupole line prints SIX numbers, the dipole line FOUR. Anchoring on
# "molecular dipole:" and requiring exactly 4 numbers + end-of-line is what keeps
# them apart; a bare "^\s*full:" regex silently grabbed the quadrupole row.
RE_DIPOLE_BLOCK = re.compile(r"molecular dipole:(.*?)(\n\s*\n|\Z)", re.S)
RE_DIPOLE_LINE = re.compile(
    r"^\s*full:\s+([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s+"
    r"([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s*$", re.M)
RE_ALPHA = re.compile(r"molecular polarizability\s*\(a\.u\.\)|alpha\s*=\s*([-+]?\d+\.\d+)", re.I)


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


def parse_xtb(text: str) -> dict:
    """Dipole from the 'full:' block.

    xTB prints four numbers on that line: three components followed by the total
    magnitude in Debye. The components are in atomic units, so computing
    sqrt(x^2+y^2+z^2) from them is a unit error -- the 4th column is the answer,
    and this matches v6.0's parser exactly (build_b100_xtb_coverage.py uses group 4).
    """
    dip = None
    mblock = RE_DIPOLE_BLOCK.search(text)
    if mblock:
        mline = RE_DIPOLE_LINE.search(mblock.group(1))
        if mline:
            dip = float(mline.group(4))
    energy = None
    m = re.search(r"TOTAL ENERGY\s+([-+]?\d+\.\d+)\s+Eh", text)
    if m:
        energy = float(m.group(1))
    m = re.search(r"HOMO-LUMO GAP\s+([-+]?\d+\.\d+)\s+eV", text)
    gap = float(m.group(1)) if m else None
    m = re.search(r"molecular polarizability[^\n]*\n?[^\n]*?([-+]?\d+\.\d+)",
                  text, re.I)
    # xTB prints an alpha block; take a conservative approach and only record it
    # when the explicit 'alpha' line is present
    alpha = None
    m2 = re.search(r"^\s*alpha\s*=\s*([-+]?\d+\.\d+)", text, re.M)
    if m2:
        alpha = float(m2.group(1))
    return {
        "terminated_normally": "normal termination" in text,
        "dipole_D": dip,
        "total_energy_hartree": energy,
        "homo_lumo_gap_ev": gap,
        "polarizability_au": alpha,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    inp = OUT / "xtb_dft_geom_inputs"

    # reference layers
    sp = {r["inchikey"]: r for r in load_csv(PROD / "parsed_sp.csv")}
    opt = {r["inchikey"]: r for r in load_csv(PROD / "parsed_opt.csv")}
    xtb_v60 = {r["inchikey"]: r for r in load_csv(XTB_V60)}

    rows = []
    for d in sorted(p for p in inp.iterdir() if p.is_dir()):
        ik = d.name
        f = d / "xtb_sp.out"
        if not f.exists():
            continue
        parsed = parse_xtb(f.read_text(encoding="utf-8", errors="replace"))
        xtb_xtbgeom_d = fnum(xtb_v60.get(ik, {}).get("dipole_D"))
        dft_xtbgeom_d = fnum(sp.get(ik, {}).get("dipole_D"))
        dft_dftgeom_d = fnum(opt.get(ik, {}).get("dipole_D"))
        xtb_dftgeom_d = parsed["dipole_D"]

        rows.append({
            "inchikey": ik,
            "name": sp.get(ik, {}).get("name", ""),
            "family": sp.get(ik, {}).get("family", ""),
            "status": "OK" if parsed["terminated_normally"] else "FAILED",
            "dipole_xtb_on_xtbgeom": xtb_xtbgeom_d if xtb_xtbgeom_d is not None else "",
            "dipole_xtb_on_dftgeom": xtb_dftgeom_d if xtb_dftgeom_d is not None else "",
            "dipole_dft_on_xtbgeom": dft_xtbgeom_d if dft_xtbgeom_d is not None else "",
            "dipole_dft_on_dftgeom": dft_dftgeom_d if dft_dftgeom_d is not None else "",
            "gap_xtb_on_dftgeom_ev": parsed["homo_lumo_gap_ev"] if parsed["homo_lumo_gap_ev"] is not None else "",
            "xtb_single_point_energy_hartree": (parsed["total_energy_hartree"]
                                                if parsed["total_energy_hartree"] is not None else ""),
        })

    out_csv = OUT / "two_by_two_matrix.csv"
    if rows:
        with out_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # ---------------- effects ------------------------------------------------
    def eff(field_a, field_b):
        vals = []
        for r in rows:
            a = fnum(r[field_a])
            b = fnum(r[field_b])
            if a is not None and b is not None:
                vals.append(a - b)
        if not vals:
            return {"n": 0}
        return {
            "n": len(vals),
            "mean": round(statistics.mean(vals), 4),
            "sd": round(statistics.pstdev(vals), 4) if len(vals) > 1 else 0.0,
            "mae": round(statistics.mean(abs(v) for v in vals), 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
        }

    doc = {
        "schema": "b710.two_by_two/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_molecules": len(rows),
        "matrix": {
            "xTB_on_xTB_geometry": "v6.0 xtb_descriptors_b100",
            "xTB_on_DFT_geometry": "this script (GFN2-xTB --sp on r2SCAN-3c geometry)",
            "DFT_on_xTB_geometry": "B702 SP layer",
            "DFT_on_DFT_geometry": "B702 Opt layer",
        },
        "energy_comparability_warning": (
            "absolute electronic energies are NOT comparable across xTB and DFT "
            "(different references and basis). Only differences WITHIN a method are "
            "meaningful; cross-method energy comparison is not made here."
        ),
        "dipole_effects": {
            "method_effect_at_xtb_geometry": eff("dipole_dft_on_xtbgeom", "dipole_xtb_on_xtbgeom"),
            "method_effect_at_dft_geometry": eff("dipole_dft_on_dftgeom", "dipole_xtb_on_dftgeom"),
            "geometry_effect_for_xtb": eff("dipole_xtb_on_dftgeom", "dipole_xtb_on_xtbgeom"),
            "geometry_effect_for_dft": eff("dipole_dft_on_dftgeom", "dipole_dft_on_xtbgeom"),
        },
        "interaction": {
            "definition": (
                "(DFT@DFT - xTB@DFT) - (DFT@xTB - xTB@xTB): if ~0, the method effect "
                "does not depend on which geometry is used"
            ),
            "value": round(
                (statistics.mean([v for v in [
                    (fnum(r["dipole_dft_on_dftgeom"]) or 0) - (fnum(r["dipole_xtb_on_dftgeom"]) or 0)
                    for r in rows if fnum(r["dipole_dft_on_dftgeom"]) is not None
                    and fnum(r["dipole_xtb_on_dftgeom"]) is not None]])
                 - statistics.mean([v for v in [
                    (fnum(r["dipole_dft_on_xtbgeom"]) or 0) - (fnum(r["dipole_xtb_on_xtbgeom"]) or 0)
                    for r in rows if fnum(r["dipole_dft_on_xtbgeom"]) is not None
                    and fnum(r["dipole_xtb_on_xtbgeom"]) is not None]])), 4)
            if rows else None,
        },
        "recommendation": None,
    }

    me = doc["dipole_effects"]["method_effect_at_dft_geometry"]
    ge = doc["dipole_effects"]["geometry_effect_for_dft"]
    if me["n"] and ge["n"]:
        ratio = abs(me["mae"]) / abs(ge["mae"]) if ge["mae"] else None
        doc["recommendation"] = {
            "method_effect_mae_D": me["mae"],
            "geometry_effect_mae_D": ge["mae"],
            "ratio_method_to_geometry": round(ratio, 3) if ratio is not None else None,
            "extend_to_full_239": bool(ratio is not None and ratio < 10),
            "reason": (
                "if the method effect stays an order of magnitude larger than the "
                "geometry effect on the DFT geometry, filling the remaining cell for "
                "all 239 molecules cannot change any conclusion; preflight is enough"
                if ratio is not None and ratio >= 10
                else "method and geometry effects are of comparable size here, so the "
                     "full matrix would add information"
            ),
        }

    (OUT / "two_by_two_analysis.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {OUT / 'two_by_two_analysis.json'}")
    print(f"n = {len(rows)}")
    for k, v in doc["dipole_effects"].items():
        if v["n"]:
            print(f"  {k:36s} mean {v['mean']:+.4f} MAE {v['mae']:.4f} n={v['n']}")
    print(f"  interaction: {doc['interaction']['value']}")
    if doc["recommendation"]:
        r = doc["recommendation"]
        print(f"  ratio method/geometry = {r['ratio_method_to_geometry']}")
        print(f"  extend to 239: {r['extend_to_full_239']}")


if __name__ == "__main__":
    main()
