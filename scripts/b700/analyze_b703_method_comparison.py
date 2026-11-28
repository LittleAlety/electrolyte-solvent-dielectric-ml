#!/usr/bin/env python
"""B703: Fixed-geometry single-point method comparison.

Compare r2SCAN-3c vs xTB vs B3LYP on the SAME GFN2-xTB geometry.

Three electronic-structure methods, one geometry:
  1. GFN2-xTB on its own optimised geometry (v6.0, 239 molecules)
  2. ORCA r2SCAN-3c single-point on the SAME xTB geometry (v7.0 SP layer, 239)
  3. PySCF B3LYP/def2-SVP single-point on the SAME xTB geometry (v6.0, 235)

The question B703 answers: how much of the descriptor difference is due to the
electronic-structure method alone (geometry fixed)?

Output:
  outputs/b700/B703_method_comparison.csv
  outputs/b700/B703_method_comparison.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
B100 = REPO_ROOT / "outputs" / "b100" / "deliverables"
B100_DIR = REPO_ROOT / "outputs" / "b100"
GEN = "analyze_b703_method_comparison/1.0.0"

SP = OUT / "B701_DFT" / "production_239" / "parsed_sp.csv"
DFT_V60 = B100_DIR / "dft_descriptors_b100.csv"
XTB_V60 = B100 / "xtb_descriptors_b100.csv"


def fnum(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def load_csv(path: Path) -> list[dict]:
    import io
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


def main() -> None:
    sp = {r["inchikey"]: r for r in load_csv(SP)}
    xtb = {r["inchikey"]: r for r in load_csv(XTB_V60)}
    b3lyp = {r["inchikey"]: r for r in load_csv(DFT_V60)}

    rows = []
    for ik in sorted(sp):
        s = sp.get(ik, {})
        x = xtb.get(ik, {})
        b = b3lyp.get(ik, {})

        sp_dip = fnum(s.get("dipole_D"))
        sp_pol = fnum(s.get("polarizability_au"))
        sp_energy = fnum(s.get("total_energy_hartree"))
        xtb_dip = fnum(x.get("dipole_D"))
        xtb_pol = fnum(x.get("polarizability_au"))
        xtb_gap = fnum(x.get("homo_lumo_gap_ev"))
        xtb_energy = fnum(x.get("total_energy_hartree"))
        b3_dip = fnum(b.get("dft_dipole_D"))
        b3_gap = fnum(b.get("dft_homo_lumo_gap_ev"))
        b3_energy = fnum(b.get("dft_total_energy_hartree"))

        d_sp_xtb = (sp_dip - xtb_dip) if (sp_dip is not None and xtb_dip is not None) else None
        d_sp_b3 = (sp_dip - b3_dip) if (sp_dip is not None and b3_dip is not None) else None
        d_xtb_b3 = (xtb_dip - b3_dip) if (xtb_dip is not None and b3_dip is not None) else None

        # relative differences
        rel_sp_xtb = (d_sp_xtb / abs(xtb_dip)) if (d_sp_xtb is not None and xtb_dip and xtb_dip != 0) else None
        rel_sp_b3 = (d_sp_b3 / abs(b3_dip)) if (d_sp_b3 is not None and b3_dip and b3_dip != 0) else None

        rows.append({
            "inchikey": ik,
            "name": s.get("name", x.get("name", "")),
            "family": s.get("family", x.get("family", "")),
            "epsilon": s.get("epsilon", ""),
            "sp_dipole_D": sp_dip if sp_dip is not None else "",
            "xtb_dipole_D": xtb_dip if xtb_dip is not None else "",
            "b3lyp_dipole_D": b3_dip if b3_dip is not None else "",
            "sp_minus_xtb_dipole": d_sp_xtb if d_sp_xtb is not None else "",
            "sp_minus_b3lyp_dipole": d_sp_b3 if d_sp_b3 is not None else "",
            "xtb_minus_b3lyp_dipole": d_xtb_b3 if d_xtb_b3 is not None else "",
            "sp_minus_xtb_rel": rel_sp_xtb if rel_sp_xtb is not None else "",
            "sp_minus_b3lyp_rel": rel_sp_b3 if rel_sp_b3 is not None else "",
            "sp_polarizability_au": sp_pol if sp_pol is not None else "",
            "xtb_polarizability_au": xtb_pol if xtb_pol is not None else "",
            "sp_energy_hartree": sp_energy if sp_energy is not None else "",
            "xtb_energy_hartree": xtb_energy if xtb_energy is not None else "",
            "b3lyp_energy_hartree": b3_energy if b3_energy is not None else "",
            "sp_gap_ev": fnum(s.get("xtb_gap_ev")),
            "b3lyp_gap_ev": b3_gap if b3_gap is not None else "",
        })

    out_csv = OUT / "B703_method_comparison.csv"
    if rows:
        with out_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # Summary statistics
    with_sp = [r for r in rows if fnum(r.get("sp_dipole_D")) is not None]
    with_xtb = [r for r in rows if fnum(r.get("xtb_dipole_D")) is not None]
    with_b3 = [r for r in rows if fnum(r.get("b3lyp_dipole_D")) is not None]
    paired_all = [r for r in rows if fnum(r.get("sp_dipole_D")) is not None
                  and fnum(r.get("xtb_dipole_D")) is not None
                  and fnum(r.get("b3lyp_dipole_D")) is not None]

    def mean(xs):
        xs = [v for v in xs if v is not None]
        return sum(xs) / len(xs) if xs else None

    def mae(xs):
        xs = [abs(v) for v in xs if v is not None]
        return sum(xs) / len(xs) if xs else None

    summary = {
        "n_with_sp": len(with_sp),
        "n_with_xtb": len(with_xtb),
        "n_with_b3lyp": len(with_b3),
        "n_paired_all": len(paired_all),
        "dipole_sp_minus_xtb": {
            "mean": mean([fnum(r.get("sp_minus_xtb_dipole")) for r in paired_all]),
            "mae": mae([fnum(r.get("sp_minus_xtb_dipole")) for r in paired_all]),
            "mean_rel": mean([fnum(r.get("sp_minus_xtb_rel")) for r in paired_all]),
        },
        "dipole_sp_minus_b3lyp": {
            "mean": mean([fnum(r.get("sp_minus_b3lyp_dipole")) for r in paired_all]),
            "mae": mae([fnum(r.get("sp_minus_b3lyp_dipole")) for r in paired_all]),
            "mean_rel": mean([fnum(r.get("sp_minus_b3lyp_rel")) for r in paired_all]),
        },
        "dipole_xtb_minus_b3lyp": {
            "mean": mean([fnum(r.get("xtb_minus_b3lyp_dipole")) for r in paired_all]),
            "mae": mae([fnum(r.get("xtb_minus_b3lyp_dipole")) for r in paired_all]),
        },
        "family_dipole_shift": {},
    }
    # per-family shift
    for fam in sorted(set(r["family"] for r in paired_all)):
        fam_rows = [r for r in paired_all if r["family"] == fam]
        summary["family_dipole_shift"][fam] = {
            "n": len(fam_rows),
            "mean_sp_minus_xtb": mean([fnum(r.get("sp_minus_xtb_dipole")) for r in fam_rows]),
            "mae_sp_minus_xtb": mae([fnum(r.get("sp_minus_xtb_dipole")) for r in fam_rows]),
            "mean_sp_minus_b3lyp": mean([fnum(r.get("sp_minus_b3lyp_dipole")) for r in fam_rows]),
        }

    manifest = {
        "schema": "b700.b703_method_comparison/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "geometry": "GFN2-xTB optimised (fixed for all methods)",
        "methods": {
            "sp": "ORCA 6.1.1 r2SCAN-3c single-point",
            "xtb": "GFN2-xTB (v6.0)",
            "b3lyp": "PySCF B3LYP/def2-SVP (v6.0)",
        },
        "summary": summary,
        "input_hashes": {
            "parsed_sp_csv": hashlib.sha256(SP.read_bytes()).hexdigest(),
            "xtb_csv": hashlib.sha256(XTB_V60.read_bytes()).hexdigest(),
            "dft_v60_csv": hashlib.sha256(DFT_V60.read_bytes()).hexdigest(),
        },
        "caveat": "Fixed geometry isolates electronic-structure method differences. "
                  "The B3LYP column is from v6.0 (235 molecules); missing values are "
                  "molecules not covered by the v6.0 DFT layer.",
    }
    out_json = OUT / "B703_method_comparison.json"
    out_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out_csv}")
    print(f"Wrote {out_json}")
    print(f"Rows: {len(rows)}")
    print(f"Paired all methods: {len(paired_all)}")
    print(f"Summary: {json.dumps(summary, indent=2)}")


if __name__ == "__main__":
    main()
