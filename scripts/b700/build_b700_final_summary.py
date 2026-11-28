#!/usr/bin/env python
"""Consolidate every B700 evidence object into one machine-readable summary.

Reads the parsed layers, the B703 comparisons and the B706 experiment reports,
and emits outputs/b700/B700_FINAL_SUMMARY.json with the numbers the final report
is allowed to quote. No number in the report should come from anywhere else.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b700"
B701 = OUT / "B701_DFT" / "production_239"
GEN = "build_b700_final_summary/1.0.0"


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


def load_json(path: Path):
    if not path.exists():
        return None
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return json.loads(raw.decode(enc))
        except Exception:
            continue
    return None


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def main() -> None:
    sp = load_csv(B701 / "parsed_sp.csv")
    opt = load_csv(B701 / "parsed_opt.csv")
    desc = load_csv(OUT / "orca_r2scan3c_descriptors.csv")
    b703 = load_json(OUT / "B703_method_comparison.json")
    b703m = load_json(OUT / "B703_full_matrix.json")
    b706_sp = load_json(OUT / "B706_experiments_report_sp.json")
    b706_opt = load_json(OUT / "B706_experiments_report_opt.json")
    e3 = load_json(OUT / "B706_E3_conformer.json")

    conf_csv = OUT / "B704_conformers" / "parsed_conformers.csv"
    conf = load_csv(conf_csv) if conf_csv.exists() else []
    e6_stab = load_json(OUT / "B706_E6_seed_stability.json")
    e4_diag = load_json(OUT / "B706_E4_family_diagnostics.json")

    summary = {
        "schema": "b700.final_summary/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "program": "ORCA 6.1.1",
        "method": "r2SCAN-3c",
        "coverage": {
            "sp_rows": len(sp),
            "sp_ok": sum(1 for r in sp if r.get("status") == "OK"),
            "sp_with_dipole": sum(1 for r in sp if r.get("dipole_D") not in ("", None)),
            "sp_with_polarizability": sum(1 for r in sp if r.get("polarizability_au") not in ("", None)),
            "opt_rows": len(opt),
            "opt_ok": sum(1 for r in opt if r.get("status") == "OK"),
            "opt_converged": sum(1 for r in opt if r.get("optimization_converged") == "True"),
            "descriptor_rows": len(desc),
            "conformer_rows": len(conf),
            "conformer_molecules": len({r["inchikey"] for r in conf}),
        },
        "B703_fixed_geometry": (b703 or {}).get("summary"),
        "B703_full_matrix": (b703m or {}).get("summary"),
        "B706_sp": {
            "n": (b706_sp or {}).get("n_molecules"),
            "constant_baseline_mae": (b706_sp or {}).get("constant_baseline_mae"),
            "E1": (b706_sp or {}).get("E1"),
            "E2": (b706_sp or {}).get("E2"),
            "E4_family": (b706_sp or {}).get("E4", {}).get("family_loo"),
            "E6": (b706_sp or {}).get("E6"),
        },
        "B706_opt": {
            "n": (b706_opt or {}).get("n_molecules"),
            "constant_baseline_mae": (b706_opt or {}).get("constant_baseline_mae"),
            "E1": (b706_opt or {}).get("E1"),
            "E2": (b706_opt or {}).get("E2"),
            "E4_family": (b706_opt or {}).get("E4", {}).get("family_loo"),
            "E6": (b706_opt or {}).get("E6"),
        },
        "B706_E3_conformer": e3,
        "B706_E6_seed_stability": (e6_stab or {}).get("arms"),
        "B706_E4_family_diagnostics": (e4_diag or {}).get("families"),
        "input_hashes": {
            "parsed_sp": sha(B701 / "parsed_sp.csv"),
            "parsed_opt": sha(B701 / "parsed_opt.csv"),
            "descriptors": sha(OUT / "orca_r2scan3c_descriptors.csv"),
            "opt_model": sha(OUT / "orca_r2scan3c_opt_model.csv"),
        },
    }

    path = OUT / "B700_FINAL_SUMMARY.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {path}")
    print(json.dumps(summary["coverage"], indent=2))


if __name__ == "__main__":
    main()
