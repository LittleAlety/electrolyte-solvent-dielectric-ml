# B100 Review — Reviewer 1: Chemistry and Physics

**Scope:** independent chemistry/physics adjudication of the 257-molecule B100 dataset and experiments E1, E4, E6, H4, plus the conformer analysis.
**Reviewer:** 1 of 4 (independent). **Verdict file:** [`b100_reviewer_1.csv`](b100_reviewer_1.csv).
**Reproduction:** all numbers below were recomputed from the frozen CSVs with the workspace venv; nothing was taken on trust from the manifests. Scratch scripts `_r1_*.py` remain in this directory; no existing file was modified.

**Headline verdict:** all six items HOLD. The physics *mechanisms* in E1, E4 and the conformer work are sound; the *reported effect sizes and explanations* are not, and two headline numbers (E1 best-block R²=0.477, conformer 30/36) do not survive checking. The single most important correction: **the halocarbon "failure" is genuine, but the stated reason is false** — halocarbons are neither narrow-ε nor the lowest-ε family, and four other families fail worse while being reported as successes.

---

## 0. Summary table

| item | decision | evidence_grade | phys. credible | overreach | one-line reason |
|---|---|---|---|---|---|
| dataset_257 | HOLD | DOCUMENTED | true | true | Clean pure liquids, no salts/gases — but the family taxonomy is chemically wrong and none of the canonical electrolyte solvents are present |
| E1_blocks | HOLD | INFERRED | true | true | μ²/Vm > structural block reproduces (0.292 vs 0.118) and is textbook Kirkwood–Onsager; but α/Vm is a dead column and R²=0.477 does not reproduce |
| E4_halocarbon_failure | HOLD | DOCUMENTED | true | true | Real failure, wrong explanation: ε spans 2.24–10.19 (not "2–5"), mean 5.98 (not lowest), R²=−11…−18.5 |
| E6_screening | HOLD | DOCUMENTED | **false** | true | Regret 18.12 is 70% two molecules (HCN + glycerol); rank-1 pick tetranitromethane has true ε=2.52 |
| H4 | HOLD | INSUFFICIENT | true | true | Correctly self-labelled under-powered, but emits `supports_h4=true`, and both groups lose to their own constant baselines |
| conformer_analysis | HOLD | INFERRED | true | true | "30/36 >10% off Boltzmann" is actually 16/36; 30/36 is the *spread* criterion; ensembles are 6-point samples |

---

## 1. `dataset_257` — are these 257 chemically sensible pure liquids?

**Yes at the core, no at the edges. HOLD.**

*Integrity checks that pass:* 257 net-neutral molecules (all `formal_charge=0`), 0 duplicate InChIKeys, 0 duplicate SMILES, `phase_verified=true` for 257/257. The filters demonstrably fired: the ledger records 21 `SALT_SEPARATED_ION_PAIR`, 6 `MULTI_COMPONENT_MIXTURE (2 fragments)`, 14 `SOLID_OR_SUPERCOOLED_AT_STATED_T`, 5 `NOT_LIQUID_AT_STATED_T`. **No salts, no mixtures, no gases** (R-227ea and the other fluoropropanes were correctly excluded). Stereochemistry is respected: *meso*- and dl-2,3-dibromobutane are kept as separate liquids with different ε (6.245 vs 5.758) — physically correct.

*Spot-checked ε against known values — all consistent:* heptane 1.930, CCl₄ 2.238, 1,4-dioxane 2.228, mesitylene 2.279, 1,2-dibromoethane 4.78, nitromethane 35.87, nitrobenzene 34.82, glycerol 41.17 (at 303 K — they deliberately used the higher temperature, glycerol mp 18 °C), N-methylacetamide 178.47. Temperatures are chosen above melting points where needed (triethanolamine at 303.15 K, mp 21.6 °C). This is careful curation.

### 1.1 ε distribution — physically reasonable

| band | n | % |
|---|---:|---:|
| LOW ε<5 | 117 | 45.5 |
| MID 5–20 | 115 | 44.7 |
| HIGH ε≥20 | 25 | 9.7 |

ε range 1.890–178.47, median 5.230, mean 8.880, 90th percentile 19.60. The shape is the expected one for organic liquids: a large non-polar/polar-aprotic low band, a broad middle, and a sparse high tail. The high tail is, however, chemically narrow — nitro compounds, nitrate esters, polyols, nitriles — and contains one species (HCN) that is a liquid only below 25.6 °C. For an electrolyte application (which needs ε ≈ 20–65) a 9.7% high band dominated by nitramines and polyols is a real coverage weakness.

### 1.2 Four defects that matter

1. **Family taxonomy is chemically wrong, and it contaminates E4.** 12 of 21 "amine" molecules are not amines: nitromethane (35.87), nitrobenzene (34.82), nitroethane (28.04), 2-nitropropane (25.52), 1-nitropropane (23.24), o-/m-nitrotoluene (27.40/23.80), tetranitromethane (2.52), ethylene nitrate (28.30), ethyl nitrate (19.40), 1,2-propanediol dinitrate (26.80), 1,3-propanediol dinitrate (19.00), 3-chloro-1,2-propanediol dinitrate (17.50), nitroglycerin (19.30). Only 5 molecules are true amines, plus 3 aminoalcohols. N-methylacetamide (an amide, ε=178.47 — the dataset maximum) is filed as `alcohol_polyol`; 1-methylimidazole as `aromatic`. The "amine" family therefore spans ε = 2.5–35.9, which is why its E4 residual behaviour (R²=−1.5, MAE 9.0) is physically uninterpretable — it is not a chemical family.
2. **The dataset does not contain the solvents it is named for.** Water (ε 80.1), acetonitrile (36), DMSO (47), DMF (37), THF (7.6), γ-butyrolactone (42), ethylene carbonate (90), propylene carbonate (65), 1,2-dimethoxyethane (7.1) and sulfolane are all present in `exclusion_ledger_b100.csv` and every one is excluded, mostly by the blanket token `EXCLUDED_IN_V06` (174 occurrences) carried over from an earlier version. A dielectric dataset for *electrolyte solvents* that omits all ten canonical electrolyte solvents is not fit for the stated purpose, however clean its ε values are.
3. **Non-random descriptor loss.** 36/257 molecules have `polarizability_au = NaN` (and hence `alpha_over_Vm = NaN`) because they went through the `CACHED` xTB path rather than `EXISTING`. They are not random: they are the polar, high-ε, H-bonding molecules — including N-methylacetamide (178.47), 1-methylimidazole (39.78), hexanedinitrile (32.12), 2-aminoethanol (31.46), diethylene glycol (30.95), 2-acetylthiophene (29.19), triethanolamine (28.11), diethanolamine (24.69), triethylene glycol (23.07), 1,2-butanediol (22.14). Mean ε of the lost 36 is 16.68 versus 8.00 for the kept 221, and 10 of the 25 molecules with ε≥20 vanish. **Every model in E1/E4/E6/H4 is therefore fitted on a target-truncated subset that systematically drops the hardest cases.** This is a pipeline bug, not a scientific choice, and it is the single cheapest fix available to the project.
4. **No temperature normalisation.** Labels are pooled over 293.15–303.15 K (120 at 293.15, 81 at 298.15, 27 at 303.15, 29 at intermediate values — including one at 298.00 K, inconsistent formatting). For non-polar liquids dε/dT ≈ −0.002 K⁻¹ (negligible), but for H-bonded/polar liquids it is of order −0.3 to −0.5 K⁻¹, so a 10 K spread injects several ε units of label noise precisely in the high-ε group. The reports never quantify this floor.

---

## 2. `E1_blocks` — is μ²/Vm beating 15 structural features physically credible?

**The mechanism: yes, emphatically. The reported numbers: partly. HOLD, evidence INFERRED.**

### 2.1 The comparison reproduces

My independent re-implementation (standardise, nested-LOO ridge, 12-value λ grid, n = 221) gives:

| block | my R² | my MAE | reported R² | reported MAE |
|---|---:|---:|---:|---:|
| X0_structure (15) | 0.118 | 4.375 | 0.096 | 4.399 |
| X1_electronic (3) | 0.187 | 4.306 | 0.191 | 4.327 |
| Xn_volume-normalised (2) | **0.292** | 4.323 | **0.296** | 4.103 |
| X0+X1 (18) | 0.262 | 3.663 | 0.280 | 3.689 |
| X0+X1+Xn (20) | 0.300 | 3.999 | **0.477** | **3.300** |

Four of five blocks reproduce within 0.02 R². The claim "2 volume-normalised features beat 15 structural features" is therefore **real and not an artefact**.

### 2.2 Why it is expected, not surprising

The Kirkwood–Onsager relation for a non-associated liquid is

&nbsp;&nbsp;&nbsp;&nbsp;(ε−1)(2ε+1)/(9ε) = (N_A/3ε₀Vm)·(α + g·μ²/3kT)

so ε is a function of the **dipole number density ρμ²** and the **polarizability density ρα**, with μ entering **squared**. The structural block (heavy-atom count, mw, ring count, rotatable bonds, TPSA, …) can only reach those quantities indirectly, through size and shape. Two consequences fall straight out of the data:

* single-feature LOO: **μ²/Vm alone gives R²=0.238, Spearman 0.795**; `dipole_D` alone gives R²=0.113, Spearman 0.702. Squaring μ *is* the physics — that doubling is the whole effect.
* 15 structural features reach only 0.118, barely above the constant baseline's 5.09 MAE → 4.375. Molecular size is a weak proxy for packing density, and shape descriptors carry no information about the H-bond network.

So the correct reading is not "volume normalisation is a clever discovery" but "**the 2-feature block encodes the known dielectric law, and the 15-feature block does not.**" That is a legitimate and useful negative result about generic structural descriptors, and it is physically credible.

### 2.3 Where it overreaches

1. **α/Vm is not a working second feature.** Its coefficient of variation over the 221 molecules is only **7.5%** (range 1.61×10⁻³⁵ to 2.37×10⁻³⁵). Alone it gives R²=0.036 with Spearman **−0.108** against ε, and it is uncorrelated with μ²/Vm (r = −0.01). "μ²/Vm + α/Vm" is really *one* physical feature plus a near-constant column; the +0.054 R² gained over μ²/Vm alone behaves like a weak packing/density correction, not the polarizability term dielectric theory demands. The physical reason α/Vm is flat is itself diagnostic — see §2.4.
2. **R² = 0.477 does not reproduce.** With the protocol the manifest describes ("ridge with intercept, nested LOO, same 221 molecules") I get 0.300–0.308 (MAE 3.93–4.00 against the reported 3.30). A log-ε target yields 0.452 — close, but still not 0.477. The number is probably from an undocumented target transform. Until it is reproducible it should not be quoted as the project's best result; and it is the number used in the week-7 comparison table ("最佳 R² 0.477").
3. **"Vm" is not a liquid molar volume.** `molar_volume_m3_mol` = xTB molecular volume × N_A, i.e. a *gas-phase cavity volume*, not a density:

| liquid | xTB Vm (cm³/mol) | exp. Vm | ratio |
|---|---:|---:|---:|
| CCl₄ | 54.2 | 96.5 | 0.56 |
| heptane | 77.5 | 147.0 | 0.53 |
| 1,4-dioxane | 51.5 | 85.7 | 0.60 |
| nitromethane | 31.7 | 54.0 | 0.59 |
| bromoform | 53.3 | 87.2 | 0.61 |
| glycerol | 53.0 | 73.2 | 0.72 |

The factor is 0.53–0.72 and **family-dependent** (glycerol 0.72 vs heptane 0.53), so ρμ² is not truly volume-normalised and the residual family-dependence is a systematic error that travels straight into E4. It also makes the feature conformation-dependent for flexible molecules (a folded conformer has a smaller cavity), which couples the conformer problem (§6) into E1. No experimental density is used anywhere in the pipeline.
4. **Wrong target functional form.** The model regresses ε linearly. Dielectric theory says the response is the bounded Clausius–Mossotti function. A bounded target is not a luxury: the unbounded linear ridge emits ε = −16.63 (see E6) and ε = −11.94 for bromoform (see E4). Whatever the coefficient values, a model whose output space includes ε < 1 is physically inadmissible and should be constrained at the transform level.
5. **Unit inconsistency between the two "volume-normalised" features.** `alpha_over_Vm` = 4πε₀·α_SI/Vm (verified numerically: 4π·8.854e−12·α/Vm reproduces 2.0098e−35 for tetrachloroethane) whereas `mu_sq_over_Vm` = μ²_SI/Vm with no 4πε₀ (verified: μ=2.17 D → 9.83e−55 for bromoform). Per-feature standardisation absorbs the 10⁻¹⁰ offset for a ridge, so the fit is unaffected — but any physical interpretation of the two coefficients side by side is invalid.

**Bottom line for E1:** the ordering claim is sound and physically motivated; the headline best-model R² is not reproducible, α/Vm is oversold, and the "volume normalisation" is not performed with liquid densities.

---

## 3. `E4_halocarbon_failure` — the key chemistry question

### 3.1 The brief's framing is factually wrong, twice

> "halocarbon (67 molecules) FAILS … because it is the lowest-ε family … if halocarbons all sit at ε≈2.1, then predicting their mean is trivially good"

Measured from `model_matrix_b100.csv` (the 221-molecule common set):

| family | n | mean ε | sd | min | median | max |
|---|---:|---:|---:|---:|---:|---:|
| other_neutral_liquid | 33 | **2.55** | 2.41 | 1.89 | — | 15.80 |
| carbonate | 1 | 2.83 | — | — | — | — |
| aromatic | 22 | 2.97 | 1.54 | 2.24 | — | 9.00 |
| carboxylic_acid | 2 | 4.30 | — | — | — | — |
| ether | 19 | 5.86 | 4.40 | 2.23 | — | 22.60 |
| **halocarbon** | **67** | **5.98** | **1.79** | **2.24** | **6.05** | **10.19** |
| ester | 21 | 6.83 | 5.15 | 3.11 | — | 27.80 |
| alcohol_polyol | 26 | 8.88 | 8.53 | 2.87 | — | 41.17 |
| amine | 17 | 20.47 | 10.31 | 2.52 | — | 35.87 |

* **Halocarbons are not the lowest-ε family.** Their mean (5.98) is 2.3× that of `other_neutral_liquid` (2.55) and above `aromatic` (2.97) and `carbonate` (2.83). The report's §2.1 statement "ε 多在 2–5" ("ε mostly 2–5") is false: quantiles are 2.24 / 3.76 / 4.67 / **6.05** / 7.07 / 8.19 / 10.19, i.e. only ~30% lie below 5 and 25% are ≥7.07.
* **Halocarbons are not a narrow band.** sd = 1.79 on a mean of 5.98 (CV 30%), spanning a 4.6× range. `aromatic` (sd 1.54) and `ketone_aldehyde` (sd 4.0) bracket it; `halocarbon` is one of the *more* variable families.
* **Low ε is not the driver.** The genuinely lowest-ε family, `other_neutral_liquid`, produces the *best relative* result in E4 (MAE 2.25 vs baseline 6.39).

### 3.2 So is the comparison unfair? No — and the failure is real

The `train_mean_baseline` is the correct *no-information* comparator: at prediction time you do not know the held-out family's mean, so the honest null is "predict the training mean". It is not a trivially low bar. For halocarbons:

| predictor | MAE |
|---|---:|
| training mean (~8.0) | **2.53** |
| oracle constant (= family mean) | 1.48 |
| B100 LOFO model | **6.78** (their run) / 4.44 (mine) |

The oracle constant shows the irreducible floor for *any* constant predictor is 1.48; the train-mean baseline sits at 1.7× that floor (it is penalised by an offset of ~2 ε units, not flattered by narrowness). The model is **2.7–4.6× the floor**, and R² = −11.1 (my reproduction) to −18.5 (their run) means it is *worse than predicting the family mean*. Under every baseline available, it fails.

And it fails in a chemically specific, unphysical way. My LOFO reproduction (best block, 67 held-out halocarbons):

* predictions span **[−11.94, +19.75]**, sd 6.81, bias only −0.19;
* ε = **−11.94 for bromoform** (true 4.39), **−8.35 for CCl₄** (true 2.24), **−9.54 for pentachloroethane**, +19.35 for 1,2-dibromoethane (true 4.78), +19.75 for dl-2,3-dibromobutane (true 5.76).

Since ε ≥ 1 by definition, this is **unconstrained linear extrapolation**, not a mean shift. And when only the physical block (μ²/Vm, α/Vm) is used, the model over-predicts the whole family by **+8.73** (predicted mean 14.71 vs true 5.98) — the clearest single diagnostic.

### 3.3 The actual physical mechanism

Halocarbons are **strongly polar but non-associated**. Their gas-phase dipoles are large (1-bromoalkanes ~4 D, 1,2-dibromoethane 5.09 D, 2,3-dibromobutane 5.95 D) and their molecular volumes are small (heavy halogens pack densely), so ρμ² is high. But in the neat liquid the dipoles adopt largely **antiparallel** orientations, giving a Kirkwood correlation factor g ≤ 1, while the training pool is dominated by alcohols/amides/nitroalkanes with g ≈ 2–3 from H-bonded chains. A single relation ε ≈ f(ρμ², ρα) cannot serve both regimes: it over-predicts the g<1 family and under-predicts the g≫1 family. This is the textbook reason why ε is not a single-molecule property, and E4 deserves credit for exhibiting it at n=67.

Incidentally, this also explains why α/Vm is flat across the dataset (§2.3): ρ·α is nearly constant because all liquids pack to a similar fraction of their cavity volume — the interesting variance is all in μ² and in g.

### 3.4 The overreach: halocarbon is not "the" failure boundary

"6/8 families beat the baseline" is technically true and scientifically misleading. Applying the R² criterion to the same LOFO runs:

| family | MAE (my repro) | R² (my repro) | beats train-mean baseline (their run) | reported as |
|---|---:|---:|:--:|---|
| ester | 2.49 | **+0.54** | no (3.84 vs 3.22) | ❌ FAIL |
| ether | 2.60 | **+0.26** | yes (3.37 vs 3.55) | ✅ PASS |
| ketone_aldehyde | 3.06 | **+0.08** | yes (2.96 vs 7.20) | ✅ PASS |
| alcohol_polyol | 5.83 | −0.29 | yes, by 1% (4.84 vs 4.90) | ✅ PASS |
| amine | 10.95 | −1.51 | yes (9.01 vs 14.77) | ✅ PASS |
| other_neutral_liquid | 4.74 | **−10.5** | yes (2.25 vs 6.39) | ✅ PASS |
| halocarbon | 4.44 | **−11.1** | no (6.78 vs 2.53) | ❌ FAIL |
| aromatic | 3.41 | **−20.0** | yes (4.65 vs 5.23) | ✅ PASS |

**Six of eight families have R² < 0, including four reported as successes. `aromatic` fails *worse* than `halocarbon` (R² −20.0 vs −11.1) yet passes.** The honest conclusion is not "one family fails at the ε boundary" but "**LOFO transfer collapses for most of this dataset; only ester, ether and (marginally) ketone_aldehyde transfer at all**", and the pass/fail criterion (MAE vs a train-mean constant, with no R² requirement) is too weak to detect that. The irony is that E4's negative result is *stronger* than advertised and is being reported in a way that understates it.

*Caveat on exact numbers:* my reproduction gives halocarbon MAE 4.44 / R² −11.1 versus their 6.78 / −18.5. The direction, sign of bias structure, and the ordering against other families are robust across both runs, but the absolute MAE differs by 1.5× and the manifest does not document enough of the fitting recipe (λ grid, standardisation, target transform) to settle it. The E4 numbers should be regenerated with the recipe pinned before any of them is quoted.

---

## 4. `E6_screening` — Top-10 regret 18.12

**The arithmetic is right; the inference is not. HOLD, physically_credible = false.**

I reproduced the metric exactly under two definitions: regret = oracle Top-10 mean (39.090) − model Top-10 mean (20.966) = 18.124, and the pointwise sum-over-ranks/10 also gives 18.12. k=5 and k=15 give 31.83 and 11.38, matching the manifest. So the statistic is not a computational artefact.

**It is, however, an outlier statistic.** Decomposing the 18.12:

| molecule | true ε | predicted | regret contribution |
|---|---:|---:|---:|
| Hydrocyanic acid | 114.90 | 14.84 | **10.01 (55%)** |
| glycerol | 41.17 | 13.88 | 2.73 (15%) |
| all remaining 8 | — | — | 5.38 (30%) |

**Two of 221 molecules carry 70% of the regret.** Worse, the true maximum ε in the whole dataset (N-methylacetamide, 178.47) is *not in the 221 evaluation set* because of the polarizability NaN bug — so the screen is being graded on a truncated tail and still misses the tail it is given. P(random ≥ model) = 0.0036 is a valid statement about those two outliers; it is not evidence that the ranker locates high-ε chemistry.

**The chemistry of the top-k is qualitatively wrong, not marginally wrong:**

* **Rank-1 pick: tetranitromethane, predicted 24.15, true 2.52 — an absolute error of 21.63, the worst single error in the set.** This is not bad luck, it is a category error: C(NO₂)₄ is a pseudo-tetrahedral molecule whose four nitro groups cancel, so it has essentially **no net dipole** and ε = 2.52 despite having the largest nitro-group count in the dataset. It is the exact counterexample to the rule the model has learned ("NO₂ ⇒ polar ⇒ high ε").
* The predicted Top-10 is 9 nitro/nitrate/amine species plus acetic acid (true 6.15, predicted 17.48). No carbonate, ether, ester, sulfone or nitrile appears. For electrolyte design the screen surfaces **explosives and nitroalkanes**, which is the opposite of useful.
* **Nine predictions are unphysical (min −16.63 < 1)**, and the model's global maximum prediction is 24.15 while the truth reaches 114.90. The ranker can order the dataset but cannot place the high-ε tail: perfect Spearman would still leave regret ≈ 39.09 − (model top-10 mean). Spearman 0.776 is fine; top-k regret is what a screening claim stands on, and 18.12 is a 2.8× lift over a pool mean of 7.61 that is bought almost entirely by "contains a nitro group".

To their credit, the report says this itself in §3.2 ("显著优于随机 ≠ 足够好用于实际筛选", 42.6% of headroom captured). The overreach is in the headline framing, not in the caveat. **Verdict: statistically significant, chemically uninterpretable as a screening capability.**

---

## 5. `H4` — INSUFFICIENT_POWER

**HOLD, evidence INSUFFICIENT.** The self-label is correct and the direction is physically plausible; the file contradicts itself and the measurement cannot support the hypothesis.

* `status = INSUFFICIENT_POWER` and `power.sufficient = false` are correctly set, yet `comparison.supports_h4 = "true"` is emitted in the same JSON. A HOLD/INSUFFICIENT verdict must not also assert support.
* **Both groups lose to their own constant baselines**: weak group MAE 2.502 vs baseline 1.820; strong group MAE 18.372 vs baseline 12.160. The comparison is between two failures (relative MAE 0.570 vs 0.671, ratio 0.850) with no confidence interval and no p-value. Note this also undercuts the weak-group half of the hypothesis: the "easy" group is worse than a constant predictor, so "weak association is easier to predict" is not demonstrated either.
* n_strong = 15 < the pre-registered 20. The direction is nevertheless physically expected: for g ≈ 1 non-associated liquids ε follows ρμ² smoothly, while for H-bonded liquids ε is governed by the many-body g factor that no single-molecule descriptor contains. That is a mechanism argument, not the measured 0.85 ratio.
* **The power deficit is partly self-inflicted.** The 10 excluded ε≥20 molecules listed in §1.2.3 would take the strong group from 15 to 25 — i.e. past the pre-registered threshold — with a pipeline fix and no new data. H4 was declared under-powered while the data needed to power it was sitting in the registry with a NaN polarizability.

---

## 6. `conformer_analysis` — is 30/36 believable?

**Direction believable, number wrong, ensemble not converged. HOLD, evidence INFERRED.**

### 6.1 The headline does not match its own CSV

| criterion | count |
|---|---:|
| polar flexible molecules analysed | 36 |
| conformational dipole **spread** (max−min)/mean > 10% | **30** |
| single conformer **>10% off the Boltzmann average** (`single_vs_boltzmann_rel_dev`) | **16** |
| both | 16 |

The verdict `SINGLE_CONFORMER_UNRELIABLE` is assigned by the **spread** rule, not the deviation rule — confirmed on the borderline pair: 1-bromopentadecane (spread 0.1282 → UNRELIABLE) vs 1-bromohexadecane (spread 0.0918 → RELIABLE). **14 of the 30 flagged molecules have a single-vs-Boltzmann deviation ≤ 10%** (median over all 36 = 0.075). So "30/36 polar flexible molecules have single-conformer dipoles >10% off the Boltzmann average" is a **misstatement of the project's own metric**: the correct statements are "30/36 show >10% conformational spread" and "16/36 have single-conformer dipoles >10% off the Boltzmann average." No report section documents this analysis at all — `B100_EXPERIMENTS_REPORT.md` still lists the conformer layer as "executable but not done".

### 6.2 The 10% threshold — is it too strict?

Not in the abstract, but it is **not calibrated to any error budget**, and in one respect it is too strict:

* 1-bromoalkanes are flagged for a 0.28–0.50 D shift on a ~4 D dipole (7–13%) caused purely by C–Br bond-direction changes on a flexible chain. These are **rotamer noise on a chain-end dipole**, not distinct chemical conformers, yet the 10% cut splits chemically near-identical molecules into "reliable" (1-bromohexadecane, 9.2%) and "unreliable" (1-bromopentadecane, 12.8%) — an arbitrary partition of a continuum.
* Conversely the threshold is too *lenient* in the sense that it ignores amplification. Since ε−1 ∝ ρμ², a 10% dipole error becomes a ~20% error in (ε−1). But at the model's own accuracy (LOW-band MAE ≈ 2.5 at ε ≈ 4, i.e. 60%) that 20% is buried: 20% of (ε−1) at ε = 4 is ~0.6 in ε, four times smaller than the model's own error. **So for most molecules the conformer effect it measures is smaller than the noise it is meant to explain, and for the few where it is large (dibutyl sebacate 179%, dibutyl phthalate 84%, dibutyl/diethyl sebacate, triethylene glycol 0→4.08 D) the effect is real and should be the headline instead of a flat 30/36 count.**
* Relative deviation on a near-zero dipole is meaningless (n-decane 0.0071 D → "155% off"); the 3 non-polar molecules were correctly separated as `NONPOLAR_CONFORMATION_INSENSITIVE`. Good handling of a subtle trap.

### 6.3 The "Boltzmann average" is a 6-point Monte Carlo draw

**37 of 40 molecules were run with exactly 6 conformers**, regardless of flexibility:

| n_rotatable | 3^n conformational states | fraction sampled by 6 |
|---:|---:|---:|
| 7 | 2.2×10³ | 2.7×10⁻³ |
| 10 | 5.9×10⁴ | 1.0×10⁻⁴ |
| 14 | 4.8×10⁶ | 1.3×10⁻⁶ |
| 23 (dioctyl sebacate) | 9.4×10¹⁰ | 6.4×10⁻¹¹ |
| 30 (tetratriacontadiene) | 2.1×10¹⁴ | 2.9×10⁻¹⁴ |
| 50 (triolein) | 7.2×10²³ | failed (1 conformer found → NOT_ANALYSED) |

With a median energy range of 0.105 eV ≈ 4 kT, all six conformers carry appreciable Boltzmann weight, so the average is a **6-sample estimate with large variance that cannot locate the global minimum** — for dibutyl sebacate the found dipoles range 0.70–3.87 D, and it is essentially certain that deeper minima were never visited. `n_conformers_converged = 6` refers to SCF convergence, not sampling convergence, and the fixed `n_conformers_found = 6` across 37 molecules is the signature of a hard cap, not of a converged search.

**Crediting the direction:** under-sampling can only *underestimate* the conformational spread, so "single-conformer dipoles are unreliable for flexible polar molecules" is conservative and survives. The claim that needs retiring is the precise count, and the analysis should be described as a **lower bound on conformational sensitivity from a six-point probe**, not as a Boltzmann ensemble.

### 6.4 Coverage

40 of 257 molecules (15.6%), of which 13 halocarbons and 10 esters; **zero aromatic, ketone, nitrile or carbonate molecules** were analysed although aromatics include polar flexible species. The finding therefore says nothing about 217 molecules, including most of the high-ε tail.

---

## 7. Which conclusions are physically defensible?

### Defensible as reported
1. **No salts, no mixtures, no gases; the 257 are net-neutral, phase-verified, chemically sensible pure organic liquids** with literature-consistent ε (spot-checked across all bands).
2. **The ε distribution is physically sensible** (1.89–178.47, median 5.23; 117/115/25 across low/mid/high bands).
3. **Dipole-density features outperform generic structural descriptors.** μ²/Vm R²=0.292 vs X0 R²=0.118 reproduces, and is the textbook Kirkwood–Onsager scaling. The negative result about 15 structural descriptors is solid and useful.
4. **Cross-family generalisation of a single-molecule descriptor model fails.** This is the project's most valuable finding — it is just larger and differently located than reported.
5. **Single-conformer dipoles are unreliable for flexible polar molecules** (direction, conservatively).
6. **H4 is under-powered** (correct self-label; n_strong=15 < 20).
7. **Top-k screening is not yet usable** (the report's own §3.2 concession).

### Overreach — must be corrected before this is published
1. **"Halocarbons are the lowest-ε / narrow 2–5 band family" is false** (mean 5.98, sd 1.79, median 6.05, max 10.19; three families are lower). The failure is real; the explanation is wrong and should be replaced by the g-factor/association argument (§3.3).
2. **"6/8 families beat the baseline" conceals 6/8 negative R².** `aromatic` (R² −20.0) fails worse than `halocarbon` (−11.1) yet is reported as passing. Re-frame as "LOFO collapses for most families; only ester/ether/ketone transfer".
3. **E1 best R² = 0.477 does not reproduce** (0.300–0.308 under the documented protocol; 0.452 with a log target). Retire or re-derive it, and re-check the week-7 "0.540 vs 0.477 相当" comparison that depends on it.
4. **α/Vm should not be presented as a co-equal volume-normalised feature** (CV 7.5%, R²=0.036 alone, Spearman −0.11).
5. **"Volume-normalised" is a misnomer** — Vm is a gas-phase xTB cavity volume 0.53–0.72× the true liquid molar volume, family-dependent; no experimental density is used.
6. **"30/36 single-conformer dipoles >10% off the Boltzmann average" misstates the CSV** — that number is 16/36; 30/36 is the spread rule. And "Boltzmann average" over six conformers is not an ensemble.
7. **E6 "significantly better than random" is not a screening result.** 70% of the regret is two molecules, φ=178.47 is excluded, the rank-1 pick is off by 21.6 ε units, and 9 predictions are ε < 1.
8. **`supports_h4 = "true"` contradicts `status = INSUFFICIENT_POWER`** in the same file and should be removed.

### Missing evidence that limits every conclusion
* **The 36-molecule polarizability NaN loss** truncates the ε≥20 tail by 10/25 molecules, biases every fit toward easier targets, and is the reason H4 is under-powered. Fix first; it is free.
* **No DFT** (`dft_descriptors_b100.csv` is an empty file with 0 rows, so `fig3_xtb_vs_dft` is vacuous; the report correctly says DFT is unavailable in this environment — so X1 is xTB-only and the "electronic" block is really an xTB block).
* **No MD** (`md_dielectric_b100.csv` cannot provide a liquid-phase check on g, which is exactly the missing variable for the halocarbon problem).
* **No temperature normalisation** across 293–303 K.
* **No experimental densities**, so ρμ² and ρα are not the true liquid-state quantities.
* **No Clausius–Mossotti / Onsager target transform**, which is both the physically correct form and the natural way to keep ε ≥ 1.

---

## 8. Recommended fixes, in priority order

1. **Repair the 36 NaN polarizabilities** (`CACHED` path) — restores n=257, the ε≥20 tail (25 not 15), and may resolve H4's power problem without new data.
2. **Replace ε as the regression target** with a bounded transform (Clausius–Mossotti or log) so predictions cannot be < 1, and re-run E1/E4/E6.
3. **Fix the family taxonomy** (separate nitro/nitrate from amine; amide from alcohol_polyol) before any family-level claim is made; the "amine" family is chemically incoherent.
4. **Adopt R² (or MAE vs the family-mean oracle) as the E4 pass criterion**, and re-state the result as "transfer fails for most families".
5. **Re-derive and pin the E1 recipe** until 0.477 either reproduces or is replaced.
6. **E6:** report the regret decomposition (per-molecule contribution), state that the result rests on two outliers, and evaluate on a pool that includes the high-ε tail and plausible electrolyte chemistries.
7. **Conformers:** re-label the metric, raise the conformer budget for molecules with >10 rotatable bonds (or report spread as a lower bound), and map the dipole deviation into an ε error budget.
8. **Add the canonical electrolyte solvents** (water, ACN, DMSO, DMF, THF, GBL, EC, PC, DME) back into the dataset — the exclusions are inherited (`EXCLUDED_IN_V06`), not justified.

---

*All claims above are traceable to `outputs/b100/` CSVs/JSONs and to the reproduction scripts `_r1_*.py` in this directory. No existing file was modified.*
