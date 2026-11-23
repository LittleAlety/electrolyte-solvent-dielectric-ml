#!/usr/bin/env python
"""Write reviewer_1_decisions.csv (validated CSV, exact column order)."""
from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent / "reviewer_1_decisions.csv"

ROWS = [
    {
        "item": "B04_candidate_pool",
        "decision": "HOLD",
        "evidence_grade": "DOCUMENTED",
        "physically_credible": "false",
        "overreach_found": "true",
        "evidence_detail": (
            "Chemistry is mostly sane: 22 distinct neutral organic liquids, no salt/gas/ion "
            "(formal_charge = 0 for all 22), eps span 1.93-44.0, classes span alkane/alcohol/diol/"
            "amine/polyol/carbonate/nitrile/ketone/sulfone/imidazole/ether/ester/carboxylic acid. "
            "But the liquid-state premise fails. Cross-checking the 22 T_K against the project's OWN "
            "frozen liquid-window gate (data/processed/liquid_window_gate_report.csv) gives 10 blocked "
            "/ 8 pass / 4 unknown. Comparing T_K to PubChem mp (liquid_window_features.csv): "
            "sulfolane mp 27.8 C measured at 25.0 C (-2.8 K BELOW mp), cyclohexanol mp 25.93 C at "
            "25.0 C (-0.9 K), 2-amino-2-methylpropan-1-ol mp 31 C at 30 C (-1.0 K), "
            "N-(2-hydroxypropyl)-2-hydroxy-1-propanamine mp 42 C at 30 C (-12 K) -> 4 molecules are "
            "solid/supercooled at their stated T, and the highest-eps molecule in the pool (sulfolane, "
            "eps=44, the E6 oracle rank-1) is one of them. Secondary defect: the pool is NOT isothermal "
            "(293.15-303.15 K, 10 K spread) and T_K is not a model input even though the Kirkwood/Debye "
            "term is explicit in 1/T; at |deps/dT| = 0.3-0.5/K that is 3-5 eps units = 24-40% of the "
            "target sd of 12.46. Third: no canonical electrolyte solvent survives the three gates "
            "(EC, PC, DMSO, acetonitrile, THF, GBL, water all excluded for pair/conflict/provenance "
            "reasons), so 'electrolyte solvent pool' is a misnomer - this is a general organic-liquid "
            "set. Fourth: 5 of 11 families have n<2, and 'unclassified' (n=4) mixes the 3 alkanes "
            "(eps~2) with sulfolane (eps=44), a 22.8x internal spread. The pool is usable as an "
            "exploratory feasibility set (as b04 itself says: 'a feasibility set, not a training set'), "
            "but the per-row condition_pair_valid=true is not physically true for those 4 molecules "
            "and the liquid-window gate was never applied at admission. HOLD for phase-state re-audit "
            "and isothermal restriction before any further modelling."
        ),
    },
    {
        "item": "E1",
        "decision": "FAIL",
        "evidence_grade": "DOCUMENTED",
        "physically_credible": "false",
        "overreach_found": "true",
        "evidence_detail": (
            "The headline ('both models worse than a constant baseline, MAE 17.45/17.29 vs 10.81, "
            "descriptors learn nothing, this is the descriptor validity boundary') is FALSIFIED by a "
            "single specification error, exactly reproducible from the shipped code "
            "(run_e1_structure_vs_electronic.py:139-150 ridge_loo). The ridge is fitted on standardised "
            "features with NO INTERCEPT, i.e. forced through the origin, and then applied to the "
            "standardised test point - so the prediction is a deviation around 0, not around ybar. "
            "Consequence: mean(y_pred) = +0.59 (X0) and +0.31 (X0+X1) against a target mean of 17.32; "
            "bias = -16.72 / -17.01. Adding the intercept, same 22 molecules, same LOO, same lambda=1: "
            "X0 MAE 17.4465 -> 10.2435 (beats the 10.8062 constant baseline), X0+X1 MAE 17.2867 -> "
            "6.5044, R2 -1.288 -> +0.540. Permutation null (500 shuffles, same code): X0+X1 observed "
            "6.5044 against null q05 = 9.8040, p = 0.000; paired delta-MAE = -3.7392 against null "
            "median +0.7308, p = 0.000. So the report's own 'incremental value' verdict is inverted: it "
            "states 0 models beat the baseline and that the -0.16 delta is inside the null, whereas the "
            "correct values are 2/2 beating the baseline and a delta 5x the null q05. The claim 'this is "
            "not a tuning problem' mislabels a model-specification bug as a physics boundary. The "
            "reported numbers are also physically impossible: 10/22 (X0) and 11/22 (X0+X1) predictions "
            "are BELOW eps=1 and 8/22 and 11/22 are NEGATIVE, violating passivity/Kramers-Kronig for a "
            "non-magnetic liquid; a pure physics clip at eps=1 alone lowers MAE 17.29 -> 12.43. Finally "
            "a provenance defect: E1 actually used 12 features (including total_energy_hartree) while "
            "feature_registry_v2.csv and model_input_manifest.json both register only 11; the 12-feature "
            "model reproduces the shipped 17.286655 to 6 dp, the 11-feature one gives 17.2375. The "
            "taken-as-given premise of this review ('it makes physical sense that structure+electronic "
            "fails this badly') is itself wrong: eps is collective, but the leading Kirkwood term "
            "mu^2/V_m is a single-molecule quantity and it alone reaches Spearman +0.822 with eps, "
            "versus +0.755 for the 12-descriptor ridge. The information was present; the experiment "
            "could not see it. FAIL - must not be cited as evidence of a descriptor-validity boundary."
        ),
    },
    {
        "item": "E4",
        "decision": "FAIL",
        "evidence_grade": "DOCUMENTED",
        "physically_credible": "false",
        "overreach_found": "true",
        "evidence_detail": (
            "The 'decisive evidence' (4 molecules with nearest-neighbour Tanimoto = 1.000 yet mean "
            "|error| 19.48, therefore the descriptors cannot resolve chemically different liquids and "
            "this cannot be fixed with more data) is wrong on three independent grounds. (1) It is 4 "
            "molecules from only 2 distinct pairs - nonane/heptane and heptanedinitrile/"
            "octanedinitrile - not 4 independent cases. (2) Tanimoto = 1.000 is a Morgan radius-2 "
            "fingerprint collision, not descriptor degeneracy: recomputing ECFP4, heptane and nonane "
            "both yield exactly 8 identical bits {80,294,591,794,1057,1143,1444,1911}, because unbranched "
            "alkane environments only encode distance-from-terminus up to 2 bonds. The descriptors the "
            "model actually consumes are clearly different: heavy_atom_count 7 vs 9, "
            "molecular_volume_A3 128.66 vs 162.05, molar_volume 7.75e-5 vs 9.76e-5 m3/mol. The report's "
            "premise that 'the model can only give the same prediction' is falsified by its own file: "
            "the LOO ridge predicts nonane -20.5962 and heptane -14.9293, a 5.67-unit spread that is "
            "mathematically impossible under identical feature vectors. (3) The error is global bias, "
            "not descriptor blindness: the pooled mean residual over all 22 molecules is -16.9384, and "
            "subtracting that single constant reduces the 4 'identical' errors from 22.58/16.86/21.87/"
            "16.61 to 5.64/0.08/4.94/0.33, i.e. the offset explains 85.9% of the claimed effect "
            "(mean |err| 19.4791 -> 2.7463). Under a correctly intercepted LOO ridge the same four are "
            "4.53/1.19/5.15/0.30. The chemistry also argues against the report: nonane and heptane have "
            "eps 1.98 and 1.93 (differ by 0.05), so a sound model SHOULD predict them almost identically "
            "and be almost exactly right - which the repaired model is. Secondary defects: the "
            "applicability-domain sample is 7 in / 15 out and the '1 of 6 families beats baseline' is a "
            "count over 12 molecules with n_test = 2-4, so it has a 0-6 range and is not resolvable; "
            "with an intercept the same folds give 5 of 6 (unclassified 20.98 -> 2.59, alcohol 17.01 -> "
            "1.61, dinitrile 18.03 -> 1.78, ketone 18.94 -> 3.84, carbonate 15.61 -> 3.14), robust across "
            "lambda 0.3-100. The one E4 conclusion that survives repair is the negative one: the AD "
            "out/in error ratio 1.045 -> 1.308 is still 'no useful separation', so Tanimoto is still not "
            "a usable AD criterion - but that is a statement about ECFP for alkanes, not about "
            "descriptor information content. The 'decisive' claim is propagated verbatim into "
            "model_boundary_report.md section 4/6 and b05_gate_status.json as a supported conclusion. "
            "Must be withdrawn and recomputed with an intercept."
        ),
    },
    {
        "item": "E6",
        "decision": "FAIL",
        "evidence_grade": "DOCUMENTED",
        "physically_credible": "false",
        "overreach_found": "true",
        "evidence_detail": (
            "The measurements are internally consistent (oracle Top-3 eps 37.83, model Top-3 24.45, "
            "pool mean 17.32, regret 13.38, P(random >= model) = 0.16, overlap 1/3, "
            "insufficient_power label correct). The stated mechanism is not. The verdict "
            "REGRET_DECOUPLED_AND_ANTI_CORRELATED and the claim that predictions are 'harmful' "
            "('noise is only offsetting the bias', 'anti-correlated') is flatly contradicted by the "
            "experiment's own Spearman(pred, true) = +0.755 and by its own top-3: model 24.45 vs random "
            "17.19, i.e. +7.26 eps units BETTER than random. Physically, a predictor with rho = +0.755 "
            "cannot be anti-correlated with the target. The real mechanism is a local inversion plus an "
            "unresolved tie. The model's rank 1 is sulfolane (true 44.0, the oracle rank 1) and it is "
            "selected with probability 1.00 at sigma=0, 0.99 at sigma=4, 0.84 at sigma=8 - it is never "
            "lost at the shipped noise levels. Ranks 2-3 are true 13.87 and 15.48 (both below the pool "
            "mean) while ranks 4-6 are true 25.94, 39.78, 29.71 (mean 28.32 vs 27.94 for ranks 2-3, i.e. "
            "ranks 4-6 are true-BETTER by 8.4 units but the model put them lower). Because the "
            "prediction gaps inside that band are 0.15-1.38 units while the model's own MAE is 17.29, "
            "the ordering within the band is noise-resolvable only by chance; any perturbation that is "
            "large relative to 0.15-1.38 reshuffles ranks 4/5/6 upward and 3 of those 4 happen to be "
            "better than 15.48, so the Top-3 mean rises. Signed evidence that this is a tie-lottery and "
            "not anti-correlation: the ladder is NON-MONOTONE - regret 13.38 (sigma 0) -> 10.38 "
            "(sigma 8) -> 13.20 (sigma 16) -> 18.53 (sigma 64, random baseline ~20.6). Large noise "
            "destroys the one correct pick and regret climbs back, which is exactly the opposite of "
            "anti-correlation. The effect is also not robust: with the 12-feature model actually used in "
            "E1 and E4, regret(sigma=8) < regret(sigma=0) in only 46/200 seeds (23%, median delta "
            "-0.18); the 11-feature version used in E6 holds 200/200, so the entire finding hinges on "
            "total_energy_hartree, a feature E1's own manifest does not register. Magnitude check: total "
            "regret span across the whole ladder is 2.82 units, while one slot swap from rank-3 (15.48) "
            "to a better candidate (39.78) moves the Top-3 mean by (39.78-15.48)/3 = 8.10 units. The "
            "reported 'noise improves screening' is therefore less than one molecule changing place. "
            "The defensible physics is narrow: at n=22, k=3, with eps spanning 1.93-44.0 and model MAE "
            "~17, Top-k ranking is unresolvable except at the single extreme, and the model does find "
            "that extreme. H3 is not supported in the direction claimed; the correct verdict is "
            "UNDERPOWERED / LOCAL_TIE, not ANTI_CORRELATED."
        ),
    },
]

FIELDS = ["item", "decision", "evidence_grade", "physically_credible",
          "overreach_found", "evidence_detail"]

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=FIELDS, quoting=csv.QUOTE_MINIMAL)
    w.writeheader()
    for r in ROWS:
        assert set(r) == set(FIELDS), r.keys()
        assert r["decision"] in {"PASS", "HOLD", "FAIL"}
        assert r["evidence_grade"] in {"DOCUMENTED", "INFERRED", "INSUFFICIENT"}
        w.writerow(r)

print(f"wrote {OUT} ({len(ROWS)} rows)")
print("---")
for r in ROWS:
    print(f"{r['item']:22s} {r['decision']:5s} {r['evidence_grade']:11s} "
          f"credible={r['physically_credible']:5s} overreach={r['overreach_found']:5s} "
          f"chars={len(r['evidence_detail'])}")
print("---")
# round-trip validation
with OUT.open(encoding="utf-8") as fh:
    back = list(csv.DictReader(fh))
print("round-trip rows:", len(back), "columns:", list(back[0].keys()))
assert len(back) == 4
assert list(back[0].keys()) == FIELDS
print("columns match exactly; CSV valid")
