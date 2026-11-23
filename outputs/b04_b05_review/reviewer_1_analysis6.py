#!/usr/bin/env python
"""Reviewer 1 probe 6: check the 22-molecule pool against the project's OWN
frozen liquid-window gate (data/processed/liquid_window_gate_report.csv)."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT / "outputs/b04/candidate_pool_v2_draft.csv"
GATE = ROOT / "data/processed/liquid_window_gate_report.csv"
FEAT = ROOT / "data/processed/liquid_window_features.csv"


def load(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    pool = load(POOL)
    gate = {r["inchikey"]: r for r in load(GATE)}
    feat = {r["inchikey"]: r for r in load(FEAT)}

    print("=" * 78)
    print("S. POOL vs THE PROJECT'S OWN LIQUID-WINDOW GATE")
    print("   gate window: T_low_C=-20 .. T_high_C=60  (frozen, liquid_window_gate)")
    print(f"\n  {'name':38s} {'T_K':>7s} {'T_C':>7s} {'gate':>8s} {'mp_C':>8s}  reasons")
    npass = nblock = nmiss = nunk = 0
    bad = []
    for r in pool:
        ik = r["inchikey"]
        g = gate.get(ik)
        T = float(r["T_K"])
        Tc = T - 273.15
        if g is None:
            nmiss += 1
            print(f"  {r['name'][:38]:38s} {T:7.2f} {Tc:7.1f} {'ABSENT':>8s} {'-':>8s}")
            continue
        d = g["gate_decision"]
        mp = g.get("mp_C", "")
        rs = g.get("trigger_reasons", "")
        if d == "pass":
            npass += 1
        elif d == "blocked":
            nblock += 1
            bad.append((r["name"], Tc, mp, rs))
        else:
            nunk += 1
        print(f"  {r['name'][:38]:38s} {T:7.2f} {Tc:7.1f} {d:>8s} {mp:>8s}  {rs}")
    print(f"\n  pass={npass}  blocked={nblock}  unknown={nunk}  absent={nmiss}  total=22")
    if bad:
        print("\n  BLOCKED BY THE PROJECT'S OWN GATE:")
        for nm, Tc, mp, rs in bad:
            print(f"    {nm:38s} measured at {Tc:7.1f} C ; mp={mp} C ; {rs}")

    print("\n" + "=" * 78)
    print("T. MELTING POINT vs MEASUREMENT TEMPERATURE, all 22 (PubChem-sourced)")
    print(f"\n  {'name':38s} {'T_C':>7s} {'mp_C':>9s} {'T-mp_K':>9s}  state")
    issues = []
    for r in pool:
        f = feat.get(r["inchikey"])
        if not f or f.get("has_mp") != "true":
            print(f"  {r['name'][:38]:38s} {'?':>7s} {'no mp':>9s}")
            continue
        mp = float(f["mp_C"])
        Tc = float(r["T_K"]) - 273.15
        margin = float(r["T_K"]) - (mp + 273.15)
        state = "LIQUID" if margin > 15 else ("MARGINAL" if margin > 0 else "SOLID!!!")
        if margin <= 15:
            issues.append((r["name"], Tc, mp, margin))
        print(f"  {r['name'][:38]:38s} {Tc:7.1f} {mp:9.1f} {margin:+9.1f}  {state}")
    print("\n  measured at/below or <15 K above the melting point:")
    for nm, Tc, mp, m in issues:
        print(f"    {nm:40s} T={Tc:6.1f} C  mp={mp:6.1f} C  margin={m:+6.1f} K")


if __name__ == "__main__":
    main()
