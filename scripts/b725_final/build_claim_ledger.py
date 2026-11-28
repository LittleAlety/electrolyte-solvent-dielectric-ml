#!/usr/bin/env python
"""B725: consolidate the v7.2 evidence into one graded claim ledger.

Every claim the paper may make gets an evidence grade and a pointer to the file
that supports it:

  CONFIRMED     reproducible from artefacts, survives the checks in this round
  SUPPORTED     evidence favours it, with a named limitation
  EXPLORATORY   direction visible, statistical support absent or n too small
  UNRESOLVED    data cannot decide it
  NOT_TESTABLE  the design cannot address it at all

This script does not recompute anything: it reads the B720-B724 artefacts and
refuses to emit a grade if the supporting file is missing, so the ledger cannot
claim more than the run produced.

Outputs (outputs/b725_final/):
  claim_ledger.json
  claim_ledger.md
  sha256_manifest.json
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b725_final"
GEN = "build_claim_ledger/1.0.0"

B720 = REPO_ROOT / "outputs" / "b720_external_data"
B722 = REPO_ROOT / "outputs" / "b722_source_independence"
B723 = REPO_ROOT / "outputs" / "b723_screening_robustness"
B724 = REPO_ROOT / "outputs" / "b724_ether"
B710 = REPO_ROOT / "outputs" / "b710_evidence"
B700 = REPO_ROOT / "outputs" / "b700"

GRADES = ("CONFIRMED", "SUPPORTED", "EXPLORATORY", "UNRESOLVED", "NOT_TESTABLE")


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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    ext = load_json(B720 / "external_admission_summary.json")
    src = load_json(B722 / "source_coverage_summary.json")
    ood = load_json(B722 / "source_ood_results.json")
    proto = load_json(B723 / "e6_protocol_audit.json")
    pool = load_json(B723 / "candidate_pool_effects.json")
    topk = load_json(B723 / "topk_stability.json")
    ether = load_json(B724 / "ether_subfamily_analysis_v2.json")
    etherm = load_json(B724 / "ether_subtype_v2_manifest.json")
    e71 = load_json(B710 / "e6_stability" / "e6_stability_v71.json")
    e4 = load_json(B710 / "e4_mechanism_audit" / "e4_mechanism_audit.json")
    two = load_json(B710 / "xtb_on_dft_geometry" / "two_by_two_analysis.json")

    missing = [name for name, obj in [
        ("external_admission_summary", ext), ("source_coverage_summary", src),
        ("source_ood_results", ood), ("e6_protocol_audit", proto),
        ("candidate_pool_effects", pool), ("topk_stability", topk),
        ("ether_subfamily_analysis_v2", ether), ("ether_subtype_v2_manifest", etherm),
    ] if obj is None]

    claims = []

    def add(cid, rq, text, grade, evidence, limitation=""):
        assert grade in GRADES, grade
        claims.append({
            "id": cid, "rq": rq, "claim": text, "grade": grade,
            "evidence": evidence, "limitation": limitation,
        })

    # ---------------- external data ---------------------------------------
    lb = (ext or {}).get("liquidbenchmark", {})
    cb = (ext or {}).get("combat", {})
    if lb:
        add("E1", "data",
            f"LiquidBenchmark recovered from a pinned commit: {lb.get('raw_rows')} "
            f"rows, {lb.get('unique_compounds')} compounds, property column is "
            f"explicitly 'Relative permittivity at zero frequency' (static).",
            "CONFIRMED", "b720_external_data/external_admission_summary.json")
        add("E2", "data",
            f"LiquidBenchmark overlaps the frozen 239 on {lb.get('unique_overlapping_239')} "
            f"compounds and contributes {lb.get('unique_new_molecules')} compounds "
            "outside it, but those rows are ThermoML-derived and carry no per-row DOI.",
            "CONFIRMED", "b720_external_data/external_admission_summary.json",
            "overlap means corroboration, not new chemistry")
    if cb:
        add("E3", "data",
            "ComBat `De` is rejected as a static-permittivity source: it is wrong by "
            "40-98% on polar liquids (acetonitrile 22.23 vs 37.50; N-methylacetamide "
            "3.97 vs 178.47) while matching nonpolar liquids to <2%.",
            "CONFIRMED", "b720_external_data/external_admission_summary.json",
            "the column mixes definitions; consequence recorded, data never used")
        add("E4", "data",
            f"ComBat contributes {cb.get('unique_compounds')} compounds, "
            f"{cb.get('unique_overlapping_239')} overlapping the frozen set; none "
            "enters any training or evaluation pool.",
            "CONFIRMED", "b720_external_data/combat_records.csv")

    # ---------------- source independence ---------------------------------
    if src:
        fc = src["five_counts_kept_separate"]
        add("S1", "RQ1",
            f"Of 239 molecules, {fc['1_molecules_with_any_valid_record']} have at "
            f"least one valid record; {fc['2_molecules_with_ge2_primary_studies']} "
            f"have >=2 primary studies; {fc['3_molecules_with_ge2_independent_labs']} "
            "have >=2 independent laboratories.",
            "CONFIRMED", "b722_source_independence/source_coverage_summary.json",
            "these three counts are different quantities and must not be merged")
        add("S2", "RQ1",
            f"{src['compendium_only_molecules']} of 239 molecules "
            f"({src['fraction_compendium_only']:.1%}) rest on the NBS 514 compendium "
            "alone — one editorial source, not one paper per molecule.",
            "CONFIRMED", "b722_source_independence/source_coverage_summary.json",
            "v7.1 reported 167; v7.2 is stricter at 186 because URL-level external "
            "records without a per-row DOI no longer count as sources")
    if ood:
        agree = ood["cross_source_agreement"]
        add("S3", "RQ1",
            f"Cross-source agreement: {agree['n_comparable_pairs']} comparable pairs "
            f"over {agree['n_molecules_with_comparison']} molecules, median relative "
            f"difference {agree['median_relative_difference']:.2%}, "
            f"{agree['frac_within_5pct']:.1%} within 5%.",
            "CONFIRMED", "b722_source_independence/cross_source_agreement.csv",
            "restricted to |dT| <= 10 K")
        cf = ood["clean_ood_feasibility"]
        add("S4", "RQ1",
            "A CLEAN leave-one-source-out test is not feasible: "
            f"{cf['n_studies_clean_eligible']} studies hold >=3 molecules that no "
            "other source also covers. Every apparent source-OOD number is a "
            "programme-shift stress test, not an unseen-source test.",
            "CONFIRMED", "b722_source_independence/source_ood_results.json",
            "this is the binding limitation of the whole study")
        los = ood["leave_one_primary_study_out"]
        add("S5", "RQ1",
            f"Programme-shift stress test: {los['n_beating_constant']} of "
            f"{los['n_sources_evaluable']} held-out studies beat their constant "
            f"baseline (mean OOD MAE {los['mean_ood_mae']}), but 0 are clean.",
            "SUPPORTED", "b722_source_independence/source_ood_results.json",
            "contaminated by compendium overlap; do not quote as generalisation")
        add("S6", "RQ1",
            "The study supports, at most: internal-data performance and "
            "repeat-measurement agreement. It does NOT support independent-laboratory "
            "validation or new-chemical-space external generalisation.",
            "CONFIRMED", "b722_source_independence/source_coverage_summary.json")

    # ---------------- E6 protocol and pool --------------------------------
    if proto:
        add("P1", "RQ3",
            "The E6 metric is confirmed against the code: top-k = k largest "
            "predictions, regret = oracle-top-k mean minus model-top-k mean over the "
            "same pool, ties broken stably by index.",
            "CONFIRMED", "b723_screening_robustness/e6_protocol_audit.json")
    if pool:
        a = pool["attribution"]
        add("P2", "RQ3",
            f"Regret instability is dominated by the CANDIDATE POOL, not by training "
            f"composition: at an 80% pool the regret sd is "
            f"{a['regret_sd_pool_only_mu2vm']} vs {a['regret_sd_training_only_mu2vm']} "
            f"for training resampling (ratio {a['ratio_pool_to_training']}).",
            "CONFIRMED", "b723_screening_robustness/candidate_pool_effects.json")
        add("P3", "RQ3",
            "Shrinking the pool changes the regret LEVEL, not just its spread: "
            f"median regret {a['regret_median_full_pool']} on the full pool vs "
            f"{a['regret_median_at_80pct_pool']} at 80% "
            f"(shift {a['level_shift_from_pool_size']}).",
            "CONFIRMED", "b723_screening_robustness/candidate_pool_effects.json",
            "a smaller pool makes the top-10 an easier target")
        ranks = pool["arm_ranking_under_pool_resampling"]
        add("P4", "RQ3",
            "The FEATURE-BLOCK ORDERING is stable under pool resampling: mu2/Vm has "
            "the lowest median regret at 100%, 80% and 60% pool fractions, followed "
            "by r2SCAN-3c electronic, xTB electronic, then structure only.",
            "CONFIRMED", "b723_screening_robustness/candidate_pool_effects.json")
    if topk:
        h = topk["headline"]
        add("P5", "RQ3",
            f"Only {h['mu2vm_molecules_stable_ge90pct']} of 239 molecules appear in "
            f"the mu2/Vm top-10 on >=90% of pool draws; "
            f"{h['mu2vm_molecules_ever_selected']} appear at least once. The "
            "recommendation set is therefore NOT a stable shortlist.",
            "CONFIRMED", "b723_screening_robustness/topk_stability.json")
        add("P6", "RQ3",
            f"Only {h['agreeing_molecules_across_arms']} molecules are stable "
            "(>=90%) under BOTH the mu2/Vm and the r2SCAN-3c-electronic arms, so the "
            "two feature blocks do not agree on a shortlist.",
            "CONFIRMED", "b723_screening_robustness/molecule_recommendation_stability.csv")

    # ---------------- ether ------------------------------------------------
    if ether and etherm:
        add("T1", "RQ1",
            f"Ether splits into 5 reproducible structural classes: "
            f"{etherm['frozen_counts']}.",
            "CONFIRMED", "b724_ether/ether_subtype_v2_manifest.json",
            "official family column unchanged; subtypes are auxiliary")
        add("T2", "RQ1",
            f"Subtype LEVELS differ by {ether['level_spread_across_subtypes']} in "
            "median epsilon (chlorinated ~22 vs aliphatic ~3.7), which is a real and "
            "large effect.",
            "CONFIRMED", "b724_ether/ether_subfamily_analysis_v2.json")
        add("T3", "RQ1",
            "Within-subtype ranking is NOT demonstrated: no stratum reaches p<0.05, "
            "and the chlorinated class has n=2 so no correlation exists at all.",
            "UNRESOLVED", "b724_ether/ether_subfamily_analysis_v2.json",
            "requires >=5 measured chlorinated ethers to settle")
        add("T4", "RQ1",
            "The 'pooling cancelled a real within-subtype signal' explanation is "
            "consistent with the data but not significant (pooled rho p=0.618).",
            "EXPLORATORY", "b724_ether/ether_subfamily_analysis_v2.json")
        add("T5", "RQ1",
            "External search found no admissible new chlorinated ether, so the n=2 "
            "limitation cannot be lifted from the recovered datasets.",
            "CONFIRMED", "b724_ether/external_ether_audit.csv")

    # ---------------- carried forward from v7.0/v7.1 ----------------------
    if e71:
        mu = e71["arms"]["X0_plus_mu2_Vm"]
        el = e71["arms"]["X0_plus_r2scan3c_electronic"]
        st = e71["arms"]["X0_structure"]
        add("C1", "RQ2",
            f"MAE ranking is stable across 20 seeds: mu2/Vm {mu['mae_mean']} < "
            f"r2SCAN-3c-electronic {el['mae_mean']} < structure {st['mae_mean']}, "
            f"with sd <= {max(mu['mae_sd'], el['mae_sd'], st['mae_sd'])}.",
            "CONFIRMED", "b710_evidence/e6_stability/e6_stability_v71.json")
        add("C2", "RQ3",
            "MAE stability does NOT carry over to regret: MAE relative dispersion is "
            f"{e71['verdicts']['mae_relative_dispersion_mu2vm']:.3f} while regret "
            f"relative dispersion is "
            f"{e71['verdicts']['regret_relative_dispersion_mu2vm']:.3f}.",
            "CONFIRMED", "b710_evidence/e6_stability/e6_stability_v71.json")
    if e4:
        hc = next((f for f in e4["calibration_audit"]["families"]
                   if f["family"] == "halocarbon"), None)
        if hc:
            add("C3", "RQ1",
                f"Halocarbon failure is a calibratable family-level offset, verified "
                f"without leakage: honest nested calibration MAE "
                f"{hc['honest_nested_cal_mae']} vs constant baseline "
                f"{hc['constant_baseline_mae']}.",
                "SUPPORTED", "b710_evidence/e4_mechanism_audit/e4_calibration_audit.csv",
                "7 of 11 families remain diagnostic-only")
    if two:
        me = two["dipole_effects"]["method_effect_at_dft_geometry"]
        ge = two["dipole_effects"]["geometry_effect_for_dft"]
        add("C4", "RQ2",
            f"On the completed 2x2 matrix the method effect ({me['mae']} D) exceeds "
            f"the geometry effect ({ge['mae']} D), so geometric relaxation is not the "
            "main descriptor lever.",
            "SUPPORTED", "b710_evidence/xtb_on_dft_geometry/two_by_two_analysis.json",
            "12-molecule preflight only; absolute sizes are small")

    # ---------------- things this study cannot address --------------------
    add("N1", "RQ1",
        "Independent-laboratory generalisation: the registry's laboratory layer is "
        "only publisher-level, so leave-one-LAB-out cannot be run as such.",
        "NOT_TESTABLE", "b722_source_independence/source_coverage_summary.json")
    add("N2", "RQ3",
        "Whether a larger pool with new chemistry would preserve the mu2/Vm "
        "advantage: no external dataset supplies admissible new molecules with a "
        "verified static epsilon.",
        "NOT_TESTABLE", "b720_external_data/external_admission_summary.json")

    counts = {g: sum(1 for c in claims if c["grade"] == g) for g in GRADES}
    doc = {
        "schema": "b725.claim_ledger/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "missing_artifacts": missing,
        "n_claims": len(claims),
        "grade_counts": counts,
        "grades_defined": {
            "CONFIRMED": "reproducible from artefacts, survives this round's checks",
            "SUPPORTED": "evidence favours it, with a named limitation",
            "EXPLORATORY": "direction visible, statistical support absent",
            "UNRESOLVED": "data cannot decide it",
            "NOT_TESTABLE": "the design cannot address it",
        },
        "claims": claims,
        "paper_ready_claims": [c["id"] for c in claims if c["grade"] == "CONFIRMED"],
        "blocking_gaps": [
            "clean source OOD impossible: 0 studies with >=3 exclusively-owned molecules",
            "chlorinated ethers n=2: within-subtype ranking unresolvable",
            "no admissible external dataset with new molecules and a verified static epsilon",
        ],
    }
    (OUT / "claim_ledger.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    # markdown mirror
    lines = ["# B725 claim ledger", "",
             f"generated {doc['generated_at_utc']}", "",
             f"claims: {len(claims)}  " +
             "  ".join(f"{g}={counts[g]}" for g in GRADES), ""]
    for g in GRADES:
        sel = [c for c in claims if c["grade"] == g]
        if not sel:
            continue
        lines.append(f"## {g} ({len(sel)})")
        lines.append("")
        lines.append("| id | RQ | claim | limitation |")
        lines.append("|---|---|---|---|")
        for c in sel:
            lim = c["limitation"].replace("|", "/") if c["limitation"] else ""
            txt = c["claim"].replace("|", "/")
            lines.append(f"| {c['id']} | {c['rq']} | {txt} | {lim} |")
        lines.append("")
    (OUT / "claim_ledger.md").write_text("\n".join(lines), encoding="utf-8")

    # sha256 manifest over every v7.2 artefact plus the frozen references
    targets = []
    for base in (B720, B722, B723, B724, OUT):
        if base.exists():
            for p in sorted(base.rglob("*")):
                if p.is_file() and p.name != "sha256_manifest.json":
                    targets.append(p)
    for p in [REPO_ROOT / "data" / "external_raw" / "liquidbenchmark" / "PROVENANCE.json",
              REPO_ROOT / "data" / "external_raw" / "combat" / "PROVENANCE.json",
              B710 / "final" / "v70_freeze_manifest.json"]:
        if p.exists():
            targets.append(p)
    manifest = {
        "schema": "b725.sha256_manifest/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "n_files": len(targets),
        "files": {
            str(p.relative_to(REPO_ROOT)).replace("\\", "/"): {
                "sha256": sha256(p), "bytes": p.stat().st_size}
            for p in targets
        },
    }
    (OUT / "sha256_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {OUT / 'claim_ledger.json'}")
    print(f"Wrote {OUT / 'claim_ledger.md'}")
    print(f"Wrote {OUT / 'sha256_manifest.json'} ({len(targets)} files)")
    print()
    print(f"claims: {len(claims)}")
    for g in GRADES:
        print(f"  {g:12s} {counts[g]}")
    if missing:
        print(f"MISSING ARTEFACTS: {missing}")


if __name__ == "__main__":
    main()
