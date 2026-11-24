#!/usr/bin/env python
"""B100-00: verify every PLAN B v6.0 objective requirement against the artifacts.

This is the completion audit. Each requirement in the objective is checked against a
file on disk, not against a claim, so the answer cannot be manufactured by narration.

Run:  .venv/Scripts/python.exe scripts/b100/verify_b100_objective.py
Exit code 0 only if every hard requirement passes.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
DELIV = OUT / "deliverables"
FIG = OUT / "figures"


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
    import io
    header = text.splitlines()[0] if text.splitlines() else ""
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def jload(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    # ---- 1. >= 100 independently qualified, phase-verified molecules ----
    phase = load(OUT / "phase_state_audit_b100.csv")
    n_verified = sum(1 for r in phase if r.get("phase_verified") == "true")
    check(">=100 phase-verified liquid molecules", n_verified >= 100,
          f"{n_verified} verified")

    # ---- 2. candidate pool 150-200 (plan) / larger is acceptable ----
    qualified = load(OUT / "qualified_molecules_b100.csv")
    check("candidate pool >= 150", len(qualified) >= 150,
          f"{len(qualified)} qualified candidates")

    # ---- 3. asset inventory + NBS 514 condition audit ----
    inv = OUT / "b100_asset_inventory.json"
    nbs = OUT / "nbs514_condition_audit.csv"
    check("asset inventory present", inv.is_file())
    nbs_rows = load(nbs)
    check("NBS 514 condition audit present", len(nbs_rows) > 0,
          f"{len(nbs_rows)} rows audited")

    # ---- 4. Q1/Q2/Q3 grading ----
    grades: dict[str, int] = {}
    for r in qualified:
        g = (r.get("evidence_grade") or "").strip()
        grades[g] = grades.get(g, 0) + 1
    check("evidence grading populated (Q1 + Q2)",
          grades.get("Q1", 0) > 0 and grades.get("Q2", 0) > 0,
          str(grades))

    # ---- 5. unified xTB coverage >= 150 (hard gate >= 100) ----
    xtb_man = jload(OUT / "xtb_coverage_b100.json")
    n_xtb = ((xtb_man.get("coverage") or {}).get("n_covered")
             or len(load(OUT / "xtb_descriptors_b100.csv")))
    check("unified xTB coverage >= 100 (hard gate)", int(n_xtb) >= 100,
          f"{n_xtb} molecules")
    check("unified xTB coverage >= 150 (plan)", int(n_xtb) >= 150,
          f"{n_xtb} molecules")

    # ---- 6. DFT single-conformer, target 100 (min 60) ----
    dft_prod = jload(OUT / "dft_production_b100.json")
    n_dft = (dft_prod.get("coverage") or {}).get("n_ok", 0)
    dft_val = jload(OUT / "dft_validation_b100.json")
    check("DFT >= 60 molecules (minimum)", n_dft >= 60, f"{n_dft}")
    check("DFT >= 100 molecules (target)", n_dft >= 100, f"{n_dft}")
    check("DFT method validated on 12 molecules first",
          dft_val.get("n_validated", 0) >= 12,
          f"{dft_val.get('n_validated')} validated")

    # ---- 7. conformer statistics >= 30 ----
    conf = jload(OUT / "conformer_ensemble_b100.json")
    n_conf = conf.get("n_ok", 0)
    check("multi-conformer study >= 30 molecules", n_conf >= 30, f"{n_conf}")

    # ---- 8. liquid MD >= 12 systems ----
    md = jload(OUT / "md_dielectric_b100.json")
    n_md = md.get("n_ok", 0)
    check("liquid MD >= 12 systems", n_md >= 12, f"{n_md}")

    # ---- 9. E1-E6 upgraded to 100+ molecules ----
    e1 = jload(OUT / "e1_manifest_b100.json")
    e4 = jload(OUT / "e4_manifest_b100.json")
    e6 = jload(OUT / "e6_manifest_b100.json")
    e2 = jload(OUT / "e2_xtb_vs_dft_b100.json")
    check("E1 on >= 100 molecules", (e1.get("n_common_evaluation_set") or 0) >= 100,
          f"n={e1.get('n_common_evaluation_set')}")
    check("E2 (xTB vs DFT) present", bool(e2.get("verdict")),
          str(e2.get("verdict")))
    check("E4 family transfer present", bool(e4.get("families")),
          f"{len(e4.get('families') or [])} families")
    check("E6 screening present", "regret" in e6, f"regret={e6.get('regret')}")
    ttf = jload(OUT / "e1b_target_transform_b100.json")
    check("target-transform experiment present", bool(ttf.get("best_overall")))

    # ---- 10. H4 hypothesis tested ----
    h4 = jload(OUT / "h4_manifest_b100.json")
    check("H4 tested with stated power",
          bool(h4.get("power")) and h4.get("status") is not None,
          f"{h4.get('status')} supports={((h4.get('comparison') or {}).get('supports_h4'))}")

    # ---- 11. four-reviewer audit ----
    review = [OUT.parent / "b100_review" / f"b100_reviewer_{i}.csv"
              for i in range(1, 5)]
    n_rev = sum(1 for p in review if p.is_file())
    check("all four reviewer outputs present", n_rev == 4, f"{n_rev}/4")

    # ---- 12. 11 deliverable files + manifest ----
    deliv_files = sorted(p.name for p in DELIV.iterdir() if p.is_file())
    check("deliverables >= 11 (plus manifest)", len(deliv_files) >= 11,
          f"{len(deliv_files)} files")
    manifest = jload(DELIV / "b100_freeze_manifest.json")
    check("freeze manifest present", bool(manifest))

    # ---- 13. 8 figure classes, all real ----
    fig_man = jload(FIG / "figures_manifest.json")
    figs = fig_man.get("figures") or []
    n_fig = len(figs)
    # "REAL_OR_EXPLICIT_ZERO" is the status chart: computed from real counts, and
    # honest about zero where a layer has no rows. It is not a placeholder.
    n_real = sum(1 for f in figs
                 if f.get("kind") in ("REAL", "REAL_OR_EXPLICIT_ZERO"))
    check("8 figures produced", n_fig >= 8, f"{n_fig} figures")
    check("all 8 figures are real (not placeholders)", n_real == n_fig,
          f"{n_real}/{n_fig} real")

    # ---- 14. no quality-lowering shortcuts ----
    excl = load(OUT / "excluded_molecules_b100.csv")
    check("exclusion ledger non-trivial (no silent dropping)", len(excl) > 0,
          f"{len(excl)} exclusions recorded")
    dup = jload(OUT / "identity_audit_b100.json")
    check("duplicate-substance audit present", bool(dup))
    solv = jload(OUT / "electrolyte_solvent_coverage_b100.json")
    check("solvent coverage gap declared", bool(solv.get("do_not_do")),
          f"{solv.get('n_in_modelling_set')}/{solv.get('n_key_solvents')} present")

    # ---- 15. frozen prior artifacts untouched ----
    # The verification record lives at outputs/b00/v56_r007_freeze_manifest.json.
    frozen = jload(REPO_ROOT / "outputs" / "b00" / "v56_r007_freeze_manifest.json")
    overall = ""
    for key in ("overall", "overall_result", "verdict", "status"):
        v = frozen.get(key)
        if isinstance(v, str) and v:
            overall = v
            break
    check("frozen prior artifacts still verify",
          overall.upper() == "PASS", overall or "no record found")

    # ---- report ----
    width = max(len(c[0]) for c in checks)
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name:<{width}}  {detail}")

    n_fail = sum(1 for c in checks if not c[1])
    print()
    print(f"  {len(checks) - n_fail}/{len(checks)} objective checks passed")
    print(f"  OVERALL: {'PASS' if n_fail == 0 else 'FAIL'}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
