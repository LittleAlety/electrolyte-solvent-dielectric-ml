#!/usr/bin/env python
"""B706-E3: single conformer vs Boltzmann-weighted multi-conformer dipole.

Question (RQ3): does conformer averaging improve the dielectric prediction,
or is a single optimised conformer enough?

Scope note: only the 39 multi-conformer molecules have DFT conformer data, so
this is a subset analysis. Its job is to measure the SIZE of the conformer
effect, not to re-estimate the full 239-molecule model.

Inputs:
  outputs/b700/B704_conformers/B704_conformer_analysis.csv
  outputs/b700/orca_r2scan3c_descriptors.csv

Output:
  outputs/b700/B706_E3_conformer.json
  outputs/b700/B706_E3_conformer.csv
"""

from __future__ import annotations

import csv
import json
import math
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
CONF = OUT / "B704_conformers"
GEN = "run_b706_e3_conformer/1.0.0"

SEED = 20261124
LAMBDA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

X0_COLS = ["heavy_atom_count", "hbd", "hba", "tpsa_A2",
           "molecular_volume_A3", "molar_volume_m3_mol", "formal_charge",
           "n_rings", "n_rotatable", "fraction_csp3", "n_aromatic_atoms",
           "n_hetero", "n_halogen", "morgan2_nbits", "mw"]


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


def fnum(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def pearson(a, b):
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    den = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n))
                    * sum((b[i] - mb) ** 2 for i in range(n)))
    return num / den if den else None


def main() -> None:
    conf_path = CONF / "B704_conformer_analysis.csv"
    desc_path = OUT / "orca_r2scan3c_descriptors.csv"
    if not conf_path.exists():
        print(f"FATAL: missing {conf_path}")
        return

    conf = load_csv(conf_path)
    desc = {r["inchikey"]: r for r in load_csv(desc_path)}

    rows = []
    for c in conf:
        ik = c["inchikey"]
        d = desc.get(ik, {})
        eps = fnum(c.get("epsilon"))
        single = fnum(c.get("single_dipole_D"))
        boltz = fnum(c.get("boltzmann_dipole_D"))
        if eps is None or single is None or boltz is None:
            continue
        # structure features from the descriptor table
        feats = [fnum(d.get(k)) for k in X0_COLS]
        if any(v is None for v in feats):
            continue
        rows.append({
            "inchikey": ik,
            "name": c.get("name", ""),
            "family": c.get("family", ""),
            "epsilon": eps,
            "single_dipole_D": single,
            "boltzmann_dipole_D": boltz,
            "dipole_spread_D": fnum(c.get("dipole_spread_D")) or 0.0,
            "features": feats,
        })

    n = len(rows)
    if n < 5:
        print(f"only {n} usable rows, skipping model comparison")
        return

    eps = [r["epsilon"] for r in rows]
    single = [r["single_dipole_D"] for r in rows]
    boltz = [r["boltzmann_dipole_D"] for r in rows]
    spread = [r["dipole_spread_D"] for r in rows]

    # correlations with the target
    r_single = pearson(single, eps)
    r_boltz = pearson(boltz, eps)
    r_single_boltz = pearson(single, boltz)

    # relative deviation of single from Boltzmann
    rel = [abs(s - b) / abs(b) if b else None for s, b in zip(single, boltz)]
    rel = [v for v in rel if v is not None]

    summary = {
        "n_molecules": n,
        "families": sorted({r["family"] for r in rows}),
        "dipole_spread_D": {
            "mean": statistics.mean(spread),
            "median": statistics.median(spread),
            "max": max(spread),
        },
        "pearson_single_vs_epsilon": round(r_single, 4) if r_single is not None else None,
        "pearson_boltzmann_vs_epsilon": round(r_boltz, 4) if r_boltz is not None else None,
        "pearson_single_vs_boltzmann": round(r_single_boltz, 4) if r_single_boltz is not None else None,
        "single_vs_boltzmann_rel_dev": {
            "mean": round(statistics.mean(rel), 4) if rel else None,
            "median": round(statistics.median(rel), 4) if rel else None,
            "max": round(max(rel), 4) if rel else None,
        },
        "verdict": (
            "CONFORMER_AVERAGING_MATTERS" if rel and statistics.mean(rel) > 0.10
            else "CONFORMER_AVERAGING_MARGINAL"
        ),
        "caveat": (
            "39-molecule subset: multi-conformer evidence, not a full-model estimate. "
            "Dipoles are gas-phase; liquid-phase conformer populations will differ."
        ),
    }

    out_json = OUT / "B706_E3_conformer.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    rows_csv = OUT / "B706_E3_conformer.csv"
    with rows_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["inchikey", "name", "family", "epsilon",
                                          "single_dipole_D", "boltzmann_dipole_D",
                                          "dipole_spread_D"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in w.fieldnames})

    print(f"Wrote {out_json}")
    print(f"Wrote {rows_csv}")
    print(f"n = {n}")
    print(f"dipole spread: mean={summary['dipole_spread_D']['mean']:.3f} D "
          f"max={summary['dipole_spread_D']['max']:.3f} D")
    print(f"pearson(single, eps)   = {summary['pearson_single_vs_epsilon']}")
    print(f"pearson(boltzmann, eps)= {summary['pearson_boltzmann_vs_epsilon']}")
    print(f"single vs boltzmann relative deviation: mean={summary['single_vs_boltzmann_rel_dev']['mean']} "
          f"max={summary['single_vs_boltzmann_rel_dev']['max']}")
    print(f"verdict: {summary['verdict']}")


if __name__ == "__main__":
    main()
