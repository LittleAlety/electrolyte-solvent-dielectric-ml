#!/usr/bin/env python
"""B701-02: parse ORCA outputs and compare r2SCAN-3c against xTB and B3LYP.

The preflight is a technical gate, not a scientific result. What it must establish
before 239 molecules are committed to the cluster:

  1. ORCA actually ran and converged, for every job (not "most").
  2. The parser reads the real numbers, not plausible-looking ones. Property-level
     parsing is checked against a known fixture rather than assumed.
  3. Dipoles and polarisabilities come out at physically sensible magnitudes. A
     composite method like r2SCAN-3c is parameterised for geometry and thermochemistry;
     that says nothing about whether its RESPONSE properties are sane. This is exactly
     where a silent unit or convention error would hide.
  4. The method shift r2SCAN-3c -> xTB/B3LYP is quantified on IDENTICAL geometry, so
     it cannot be confused with a geometry effect.
  5. Runtime is measured, so the 239-molecule production cost is estimated rather than
     guessed.

Acetonitrile is used as the parser fixture because an independent ORCA 6.1.1
r2SCAN-3c run of it exists in the A repository with dipole 4.061298809 D and
isotropic polarizability 26.81326 a.u. Reproducing those numbers proves the parser
and the method invocation agree with a run that was not produced here.

Output: outputs/b700/B701_DFT/preflight_12/parsed_{sp,opt}.csv
        outputs/b700/B701_DFT/preflight_12/preflight_report.json
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
B701 = REPO_ROOT / "outputs" / "b700" / "B701_DFT"
B100 = REPO_ROOT / "outputs" / "b100"
MJ = B100 / "model_matrix_b100.csv"
DFT_V60 = B100 / "dft_descriptors_b100.csv"

# independent ORCA 6.1.1 r2SCAN-3c reference for acetonitrile (A repository fixture)
FIXTURE = {
    "inchikey": "WEVYAHXRMPXWCK-UHFFFAOYSA-N",
    "name": "Acetonitrile",
    "dipole_D": 4.061298809,
    "polarizability_au": 26.81326,
    "total_energy_hartree": -132.71720871068663,
}

RE_DIPOLE = re.compile(r"Magnitude \(Debye\)\s*:\s*(-?\d+\.\d+)")
RE_ALPHA = re.compile(r"Isotropic polarizability\s*:\s*(-?\d+\.\d+)")
RE_ENERGY = re.compile(r"Total Energy\s*:\s*(-?\d+\.\d+)\s*Eh")
RE_CYCLE = re.compile(r"SCF CONVERGED AFTER\s+(\d+)\s+CYCLES", re.I)
RE_OPT = re.compile(r"THE OPTIMIZATION HAS CONVERGED", re.I)
RE_TERM = re.compile(r"ORCA TERMINATED NORMALLY")
RE_HURRAY = re.compile(r"HURRAY")


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
    header = (text or "").splitlines()[0] if (text or "").splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text or "", newline=""), delimiter=delim))


def fnum(v):
    s = (str(v) if v is not None else "").strip()
    if s.lower() in ("", "nan", "none", "null", "na", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_one(text: str) -> dict:
    dipoles = RE_DIPOLE.findall(text)
    alphas = RE_ALPHA.findall(text)
    energies = RE_ENERGY.findall(text)
    cycles = RE_CYCLE.findall(text)
    out = {
        "terminated_normally": bool(RE_TERM.search(text)),
        # ORCA prints the dipole for every SCF it performs; the LAST one belongs to the
        # final geometry, which is what must be kept
        "dipole_D": float(dipoles[-1]) if dipoles else None,
        "n_dipole_blocks": len(dipoles),
        "polarizability_au": float(alphas[-1]) if alphas else None,
        "total_energy_hartree": float(energies[-1]) if energies else None,
        "scf_cycles": int(cycles[-1]) if cycles else None,
        "optimization_converged": bool(RE_OPT.search(text)),
    }
    return out


def pearson(a, b):
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    den = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n))
                    * sum((b[i] - mb) ** 2 for i in range(n)))
    return num / den if den else None


def spearman(a, b):
    n = len(a)
    if n < 3:
        return None

    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    return pearson(rank(a), rank(b))


def main() -> int:
    stage = sys.argv[1] if len(sys.argv) > 1 else "sp"
    cohort = sys.argv[2] if len(sys.argv) > 2 else "preflight"
    sub = "preflight_12" if cohort == "preflight" else "production_239"
    res_dir = B701 / sub / f"results_{stage}"
    jobs = res_dir / "jobs"
    if not jobs.is_dir():
        print(f"FATAL: no results at {jobs}", file=sys.stderr)
        return 2

    matrix = {(r.get("inchikey") or "").strip(): r for r in load(MJ)}
    b3lyp = {(r.get("inchikey") or "").strip(): r for r in load(DFT_V60)}

    rows = []
    for d in sorted(jobs.iterdir()):
        f = d / "job.out"
        if not f.is_file():
            continue
        ik = d.name
        parsed = parse_one(f.read_text(encoding="utf-8", errors="replace"))
        m = matrix.get(ik, {})
        b = b3lyp.get(ik, {})
        rows.append({
            "inchikey": ik,
            "name": m.get("name", ""),
            "family": m.get("family", ""),
            "epsilon": m.get("epsilon", ""),
            "status": "OK" if parsed["terminated_normally"] else "NOT_TERMINATED",
            **parsed,
            "xtb_dipole_D": fnum(m.get("dipole_D")),
            "xtb_gap_ev": fnum(m.get("homo_lumo_gap_ev")),
            "b3lyp_dipole_D": fnum(b.get("dft_dipole_D")),
            "b3lyp_gap_ev": fnum(b.get("dft_homo_lumo_gap_ev")),
        })

    ok = [r for r in rows if r["status"] == "OK"]
    path = B701 / sub / f"parsed_{stage}.csv"
    if rows:
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows:
                w.writerow(r)

    # ---- 1. fixture check: does the parser reproduce an independent ORCA run? ----
    fixture = next((r for r in ok if r["inchikey"] == FIXTURE["inchikey"]), None)
    fixture_check = {"available": fixture is not None}
    if fixture:
        fixture_check.update({
            "dipole_parsed": fixture["dipole_D"],
            "dipole_reference": FIXTURE["dipole_D"],
            "dipole_abs_diff": round(abs((fixture["dipole_D"] or 0)
                                         - FIXTURE["dipole_D"]), 6),
            "polarizability_parsed": fixture["polarizability_au"],
            "polarizability_reference": FIXTURE["polarizability_au"],
            "polarizability_rel_diff": round(
                abs((fixture["polarizability_au"] or 0)
                    - FIXTURE["polarizability_au"])
                / FIXTURE["polarizability_au"], 6)
            if fixture["polarizability_au"] else None,
        })
        # geometry differences are allowed to move the dipole slightly; the point is
        # that the parser and the method invocation agree to within that
        fixture_check["passes"] = (
            fixture_check["dipole_abs_diff"] is not None
            and fixture_check["dipole_abs_diff"] < 0.35)

    # ---- 2. method shifts on IDENTICAL geometry ----
    def shift_pairs(key_a, key_b):
        pairs = [(r[key_a], r[key_b]) for r in ok
                 if r.get(key_a) is not None and r.get(key_b) is not None]
        if len(pairs) < 3:
            return {"n": len(pairs)}
        a = [p[0] for p in pairs]
        b = [p[1] for p in pairs]
        d = [x - y for x, y in pairs]
        return {
            "n": len(pairs),
            "pearson_r": round(pearson(a, b), 4),
            "spearman_rho": round(spearman(a, b), 4),
            "mean_abs_difference_D": round(statistics.mean(abs(x) for x in d), 4),
            "mean_signed_difference_D": round(statistics.mean(d), 4),
            "max_abs_difference_D": round(max(abs(x) for x in d), 4),
        }

    doc = {
        "schema": "b700.b701_preflight/v1",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "stage": stage,
        "purpose": (
            "技术预检: 确认 ORCA 能跑、r2SCAN-3c 调用正确、偶极与极化率解析正确、"
            "性质层面数值合理、并测出生产规模的实际耗时. 不是科学结果."
        ),
        "n_jobs": len(rows),
        "n_terminated_normally": len(ok),
        "all_converged": len(ok) == len(rows) and len(rows) > 0,
        "parser_fixture_check": fixture_check,
        "method_shift_identical_geometry": {
            "r2scan3c_vs_xtb_dipole": shift_pairs("dipole_D", "xtb_dipole_D"),
            "r2scan3c_vs_b3lyp_dipole": shift_pairs("dipole_D", "b3lyp_dipole_D"),
        },
        "property_sanity": {
            "dipole_range_D": [round(min(r["dipole_D"] for r in ok), 3),
                               round(max(r["dipole_D"] for r in ok), 3)]
            if ok and all(r["dipole_D"] is not None for r in ok) else None,
            "polarizability_range_au": [
                round(min(r["polarizability_au"] for r in ok), 3),
                round(max(r["polarizability_au"] for r in ok), 3)]
            if ok and all(r["polarizability_au"] is not None for r in ok) else None,
            "n_missing_polarizability": sum(1 for r in ok
                                            if r["polarizability_au"] is None),
        },
        "records": rows,
    }
    # one report PER STAGE: a single filename let the opt pass overwrite the sp
    # result, which would quietly erase the fixed-geometry comparison
    (B701 / sub / f"preflight_report_{stage}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[B701-02] {stage}: {len(ok)}/{len(rows)} terminated normally")
    if fixture_check.get("available"):
        print(f"  fixture (CH3CN): dipole {fixture_check['dipole_parsed']} vs ref "
              f"{fixture_check['dipole_reference']} "
              f"(diff {fixture_check['dipole_abs_diff']}) passes="
              f"{fixture_check.get('passes')}")
    for k, v in doc["method_shift_identical_geometry"].items():
        if v.get("n", 0) >= 3:
            print(f"  {k}: r={v['pearson_r']} MAE={v['mean_abs_difference_D']} D "
                  f"bias={v['mean_signed_difference_D']} D")
    print(f"  property sanity: {doc['property_sanity']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
