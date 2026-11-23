# Reviewer 1 Report — Chemistry, Physics and Experimental-Condition Soundness

**Scope**: B04 candidate pool, B05 experiments E1 / E4 / E6
**Project**: electrolyte-solvent-dielectric-ml
**Reviewer**: 1 of 4 (independent)
**Posture**: adversarial re-derivation from the shipped artefacts and shipped code. No existing file was modified. All probes are reproducible under `outputs/b04_b05_review/`.

---

## 0. Bottom line

| item | decision | credible | overreach | one-line reason |
|---|---|---|---|---|
| `B04_candidate_pool` | **HOLD** | false | true | Chemistry is broadly sane, but 4/22 are measured at or below their melting point (incl. the pool's highest-ε molecule), the pool is not isothermal, and no canonical electrolyte solvent survives the gates. |
| `E1` | **FAIL** | false | true | The "worse than a constant baseline" result is a **missing-intercept bug**, not a physics boundary. With an intercept: MAE 17.29 → **6.50**, R² −1.29 → **+0.54**, p = **0.000**. |
| `E4` | **FAIL** | false | true | The "decisive" identical-fingerprint finding is **an ECFP collision plus global bias**: the offset alone explains **85.9 %** of the claimed error, and the model's own file shows the descriptors *are* different. |
| `E6` | **FAIL** | false | true | "Anti-correlated / predictions harmful" is contradicted by the experiment's own ρ = +0.755 and by its Top-3 beating random by +7.26 ε. The real mechanism is a **local tie-lottery**, and the effect is seed-fragile. |

The single most important consequence for the parent: **the pooled "descriptor validity boundary" narrative does not survive.** Three of the four reported headline conclusions invert under a corrected regression specification that uses the same features, the same 22 molecules, the same folds and the same seed.

---

## 1. Method

I did not audit prose against prose. I re-implemented the shipped ridge solvers byte-for-byte and confirmed exact reproduction of every published number before perturbing anything:

```
constant baseline    recomputed 10.806223   shipped 10.806223   ✓
X0 (7 feat)          recomputed 17.446507   shipped 17.446507   ✓
X0+X1 (11 feat)      recomputed 17.237530   shipped 17.237500   ✓   ← E6's model
X0+X1 (12 feat)      recomputed 17.286655   shipped 17.286655   ✓   ← E1/E4's model
```

Exact agreement to 6 decimal places is what licenses the causal claim in §3: because I reproduce the shipped number *exactly*, the difference induced by adding an intercept is attributable to the intercept and not to my reimplementation.

Probe scripts (all read-only against existing artefacts):

| file | question |
|---|---|
| `reviewer_1_analysis.py` | pool audit; E1 intercept refit; E4 fingerprint decomposition; E6 noise limit; Kirkwood g; mp screen |
| `reviewer_1_analysis2.py` | Clausius–Mossotti recoverability; permutation null with intercept; temperature spread |
| `reviewer_1_analysis3.py` | feature collinearity; ε ≥ 1 admissibility; real-V_m C–M; E6 selection probabilities |
| `reviewer_1_analysis4.py` | exact 11 vs 12 feature reproduction; repaired LOO; λ sweep; repaired screening |
| `reviewer_1_analysis5.py` | ECFP collision proof; bias decomposition; AD re-test; family-taxonomy defects |
| `reviewer_1_analysis6.py` | pool vs the project's **own** frozen liquid-window gate |
| `reviewer_1_analysis7.py` | Kirkwood–Fröhlich g; temperature confounding; ε ≥ 1 clipping |
| `reviewer_1_analysis8.py` | leave-one-family-out, shipped vs repaired |
| `reviewer_1_analysis9.py` | LOFO λ sensitivity; single-term Kirkwood baseline |
| `reviewer_1_analysis10.py` | noise ladder both specifications; local rank structure |
| `reviewer_1_analysis11.py` | noise-ladder seed robustness; clipped-model ladder |

---

## 2. B04 — is the 22-molecule pool chemically sensible? → **HOLD**

### 2.1 What is right

- 22 records / 22 distinct InChIKeys / 22 distinct names — no duplicates in the pool itself.
- **No salts, no gases, no ionic species**: `formal_charge = 0` for all 22, `heavy_atom_count` 4–15. This is a genuine advantage over the source dataset, which contains ionic liquids (`triethylpentylammonium bis(trifluoromethylsulfonyl)imide`, `ethanolammonium nitrate`).
- The classes do span a defensible dielectric range: alkane (ε ≈ 2) → carbonate (ε ≈ 3) → ester/amine (ε ≈ 6–7) → ketone/ether (ε ≈ 13–15) → alcohol/diol (ε ≈ 16–28) → nitrile (ε ≈ 26–30) → sulfone/imidazole (ε ≈ 40–44). ε spans 1.93–44.0, a 22.8× range.
- Single measurement per molecule, one source DOI per row, `merge_forbidden = true`, `AI_CONSENSUS_NOT_HUMAN_SIGNED` is honestly labelled.

### 2.2 What is physically wrong — the liquid-state premise

The pool asserts `condition_pair_valid = true` for all 22 rows. Cross-checking against the project's **own frozen gate** (`data/processed/liquid_window_gate_report.csv`, window −20…60 °C) gives **10 blocked / 8 pass / 4 unknown**. Comparing `T_K` to PubChem melting points in `liquid_window_features.csv`:

| molecule | measured at | mp | margin | verdict |
|---|---:|---:|---:|---|
| sulfolane | 25.0 °C | 27.8 °C | **−2.8 K** | solid at stated T |
| cyclohexanol | 25.0 °C | 25.9 °C | **−0.9 K** | solid at stated T |
| 2-amino-2-methylpropan-1-ol | 30.0 °C | 31 °C | **−1.0 K** | solid at stated T |
| N-(2-hydroxypropyl)-2-hydroxy-1-propanamine | 30.0 °C | 42 °C | **−12.0 K** | solid at stated T |
| diethanolamine | 30.0 °C | 27.9 °C | +2.1 K | marginal |
| acetic acid | 20.0 °C | 16.6 °C | +3.4 K | marginal |

This is not a curiosity. **Sulfolane is the single highest-ε molecule in the pool (44.0) and the E6 oracle rank-1** — the one molecule the model gets right. Its measurement temperature sits 2.8 K below its melting point, so either the ε is supercooled-liquid data, or the temperature label is wrong, or the ε is a solid/extrapolated value. In all three cases the row is not a clean liquid-ε observation at 298.15 K, and it is the most load-bearing row in E6.

Note the correct reading of the gate: `mp_above_T_low` is the gate's frozen windows semantics (a substance must stay liquid across the whole −20…60 °C working window), so a `blocked` verdict is broader than "solid at 298 K". I therefore report both the gate verdict and the direct T vs mp margin, and I do **not** claim all 10 blocked molecules are solid at their stated T. Only the 4 with negative margin are.

### 2.3 Three further condition defects

**(a) The pool is not isothermal.** Distinct `T_K`: 293.15, 298.0, 298.15, 298.2, 300.15, 303.15 — a 10 K spread. Worse, it is **confounded with chemistry, not random**: all five 303.15 K entries are amines/polyols (the high-ε class), and the single 293.15 K entry is acetic acid. With |dε/dT| ≈ 0.3–0.5 K⁻¹ for associated liquids, the 10 K spread maps to 3–5 ε units of pure temperature mismatch — **24–40 % of the target standard deviation (12.46)**.

**(b) Temperature is a measured variable that never enters the model.** X0/X1 contain no `T_K`, yet the Kirkwood/Debye orientational term is explicitly ∝ 1/T. This is a specification omission independent of the intercept bug.

**(c) No canonical electrolyte solvent survives the three gates.** Ethylene carbonate, propylene carbonate, DMSO, acetonitrile, THF, γ-butyrolactone and water are *all* excluded — mostly for `NO_CONTRIBUTING_MEASUREMENT;PAIR_NOT_VALID`, `PRESSURE_HETEROGENEOUS`, or `SYNTHETIC_PAIR`. The exclusion rules are defensible in themselves (EC's mp is 36.4 °C, so a 25 °C ε is not a liquid measurement), but the consequence is that "electrolyte solvent pool" is a misnomer: **the pool contains no solvent that anyone would actually use as an electrolyte solvent.** For a project whose framing is electrolyte solvents, this is a scope finding, not a data-quality nit.

### 2.4 Structural defect in the family taxonomy

Five of eleven families have n < 2 (`ester`, `tertiary_amine`, `imidazole`, `carboxylic_acid`, `ether`), so only 6 of 11 are testable. And the `unclassified` bucket (n = 4) mixes **the three alkanes (ε ≈ 2) with sulfolane (ε = 44)** — a 22.8× internal spread — because the SMARTS rule list (`FAMILY_RULES` in `run_e4_domain_generalization.py`) has **no alkane rule and no sulfone rule**. Holding that bucket out removes both polarity extremes at once, so train and test no longer share a chemical space by construction.

Also: diethanolamine is classed `primary_secondary_amine` while triethanolamine is `tertiary_amine`, although they differ by one N–CH₂CH₂OH. Chemically near-identical molecules are split across "families", which makes the leave-one-family-out estimate unstable by design.

---

## 3. E1 — is the failure physically credible? → **FAIL** (the premise is wrong)

### 3.1 The mechanism

`ridge_loo()` standardises features and fits `(Z'Z + λI)b = Z'y` with **no intercept column** and **no centring of y**. It then predicts at the standardised test point. The model is therefore forced through the origin of standardised-feature space, so the prediction is a *deviation*, not a *level*:

```
mean(y_pred) = +0.59  (X0)   and   +0.31  (X0+X1)      target mean = 17.32
bias         = −16.72 (X0)   and   −17.01 (X0+X1)
```

The model is not ignorant of chemistry; it is **un-centred**. One global offset explains 44 % (X0) and 63 % (X0+X1) of the reported MAE.

### 3.2 The repair — identical features, molecules, folds, seed

| model | shipped MAE | + intercept | Δ | shipped R² | + intercept R² |
|---|---:|---:|---:|---:|---:|
| X0 (7) | 17.4465 | **10.2435** | −7.20 | −1.820 | **−0.111** |
| X0+X1 (12) | 17.2867 | **6.5044** | −10.78 | −1.288 | **+0.540** |
| constant baseline | 10.8062 | 10.8062 | — | 0.000 | 0.000 |

Both models now **beat** the constant baseline. The report's headline ("0 of 2 models beat the baseline") becomes "2 of 2".

Permutation null, 500 shuffles, same code:

| model | observed MAE | null q05 | null median | p |
|---|---:|---:|---:|---:|
| X0 | 10.2435 | 9.7641 | 12.0459 | 0.104 |
| X0+X1 | **6.5044** | 9.8040 | 12.4991 | **0.000** |

Paired ΔMAE(X1−X0) = **−3.7392**, null q05 −1.5073, median +0.7308, q95 +1.9588, **p = 0.000**. The shipped report says the −0.16 delta is inside the null and therefore cannot be claimed; the correct delta is 23× larger and 22× outside the null q05.

λ-sensitivity of the repaired model (λ was hard-coded 1.0 and never disclosed as a choice): MAE 6.28 / 6.21 / 6.50 / 6.81 / 7.75 / 9.18 / 10.37 for λ = 0.1 / 0.3 / 1 / 3 / 10 / 30 / 100. The conclusion is robust over a **1000× range of λ**.

### 3.3 The unphysical outputs

ε ≥ 1 is a hard bound for a non-magnetic condensed phase (passivity / Kramers–Kronig). The shipped model:

- X0: **10/22 predictions < 1**, **8/22 negative**, min −10.82
- X0+X1: **11/22 < 1**, **11/22 negative**, min −20.89

A pure-physics clip at ε = 1, no fitting, lowers MAE 17.45 → 14.86 (X0) and 17.29 → 12.43 (X0+X1). **Half the reported error was a measure of unphysical output, not of chemical ignorance.**

### 3.4 On the physics argument in the prompt

The prompt invites the reading that it makes physical sense for structure+electronic descriptors to fail, because ε is collective (g-factor, H-bonding, density). I tested that directly and it is only half true.

ε *is* collective. Computing Kirkwood–Fröhlich g with literature V_m and ε∞ ≈ n_D²:

- Polar subset (μ ≥ 0.5 D, n = 19): **g = 0.44 … 6.51**, a 15× span. g < 1 (antiparallel) for acetic acid 0.44, N-methylaniline 0.56, sulfolane 0.68; g > 1.8 for 2-amino-2-methylpropan-1-ol 6.51, triethanolamine 2.74, diethanolamine 2.05, cyclohexanol 2.15. This is the same physical range as textbook values (acetone 1.3, ethanol 2.2, methanol 2.5, water 2.9). **g appears nowhere in X0/X1** — so formally the descriptors cannot contain the full collective physics.
- **But** the *leading* Kirkwood term μ²/V_m is a single-molecule quantity, and it alone gives **Spearman +0.822** with ε — *better* than the 12-descriptor ridge's +0.755. Clausius–Mossotti with real liquid molar volumes predicts the three alkanes to **0.077 MAE** (heptane 1.85 vs 1.93; nonane 1.90 vs 1.98; methylcyclohexane 1.94 vs 2.01).

So the honest physics statement is: **the descriptors carry the μ²/V_m part of ε and miss the g part.** That is a real and interesting boundary — but it is *not* what the report claims. The report claims the descriptors carry nothing. The experiment was simply unable to see the part that is there, because it was un-centred and unbounded. The measured failure (MAE 17) is not physically credible for descriptors containing polarizability and dipole; the repaired MAE (6.50) is.

### 3.5 Provenance defect

E1 used **12** features including `total_energy_hartree`; `feature_registry_v2.csv` and `model_input_manifest.json` both register **11** and omit it. The shipped 17.286655 reproduces exactly only with 12 features; 11 features give 17.2375 — which is E6's number. So E1 and E6 report "the same model" with different MAEs, and the registry does not describe what was run. Independently, two feature pairs are exactly redundant:

- `molar_volume_m3_mol / molecular_volume_A3` = 6.022141e−7 = **N_A exactly** (to 0 ppm) — so "molar volume" is a **van der Waals cavity sum packed to N_A**, *not* the bulk molar volume that Clausius–Mossotti and Kirkwood require. Its packing fraction is 0.53–0.68 (heptane vdW 77.5 vs real 146.6 cm³/mol). The registry calls this "the weakest bridge between molecule and condensed phase" — correct, and it is the wrong quantity for the physics being modelled.
- `polarizability_A3 / polarizability_au` = 0.148184 = 1 bohr³ in Å³, exactly. The same number is supplied twice.

Effective rank is therefore ~9, not 12, and `formal_charge` has zero variance (all 22 = 0) and contributes nothing.

---

## 4. E4 — is the identical-fingerprint finding meaningful? → **FAIL**

This is the highest-stakes error in the package, because `model_boundary_report.md` §4 and `b05_gate_status.json` both promote it to a *supported* conclusion ("误差源于描述符分辨力不足而非域外外推" / "cannot be fixed by more data of the same kind").

### 4.1 It is 2 pairs, not 4 cases

The 4 molecules are `nonane/heptane` and `heptanedinitrile/octanedinitrile` — **two distinct unordered pairs**, each counted twice (once from each end). The headline "4 molecules" implies four independent cases; there are two.

### 4.2 Tanimoto = 1.000 is a fingerprint collision, not descriptor degeneracy

Recomputing Morgan radius-2 (2048 bit):

```
heptane  CCCCCCC    onbits = [80, 294, 591, 794, 1057, 1143, 1444, 1911]
nonane   CCCCCCCCC  onbits = [80, 294, 591, 794, 1057, 1143, 1444, 1911]   (identical)
Tanimoto = 1.0000
```

Radius-2 Morgan environments in an unbranched alkane only encode *distance from a chain terminus up to 2 bonds*, so C7 and C9 are bit-identical. This is a well-known ECFP resolution limit.

The report's premise is: *"描述符无法区分二者, 模型只能给出相同的预测"* — **the descriptors cannot distinguish the pair, so the model can only give the same prediction.** That premise is falsified twice over:

1. **The model's descriptors are not identical.** `heavy_atom_count` 7 vs 9; `molecular_volume_A3` 128.66 vs 162.05; `molar_volume_m3_mol` 7.75e−5 vs 9.76e−5. Nothing the model consumes is degenerate.
2. **The model's predictions are not identical, in the report's own file.** `structural_distance_ood.csv` gives nonane **−20.5962** and heptane **−14.9293** — a **5.67-unit spread**. Under truly identical feature vectors the two LOO fits differ by one molecule out of 21 and could not produce that. The report's own numbers refute the report's own interpretation.

### 4.3 The error is global bias

Pooled mean residual over all 22 molecules = **−16.9384**. Subtract that single constant and the four "identical" errors collapse:

| molecule | ε | raw \|err\| | bias-removed \|err\| | repaired-LOO \|err\| |
|---|---:|---:|---:|---:|
| nonane | 1.98 | 22.58 | **5.64** | 4.53 |
| heptane | 1.93 | 16.86 | **0.08** | 1.19 |
| heptanedinitrile | 29.71 | 21.87 | **4.94** | 5.15 |
| octanedinitrile | 25.94 | 16.61 | **0.33** | 0.30 |

Mean 19.4791 → **2.7463**: the offset accounts for **85.9 %** of the claimed effect.

And the chemistry agrees with the repaired model, not with the report. Nonane ε = 1.98 and heptane ε = 1.93 differ by **0.05**. A sound model *should* predict them almost identically and be almost exactly right — which is what the intercepted model does (heptane off by 1.19, octanedinitrile by 0.30). The report reads a 16.86/22.58 error on a 0.05-ε difference as "descriptor blindness"; it is the signature of an un-centred predictor.

**Verdict on the question the prompt flags as mattering enormously: it is global bias, not descriptor failure.** The "descriptor blindness" conclusion is not merely overstated — it is inverted. The identical-fingerprint test, correctly analysed, is *evidence that the descriptors work* for the alkane pair.

### 4.4 The rest of E4 also moves

Leave-one-family-out, same folds, shipped vs repaired:

| family | n | shipped MAE | baseline | beats | repaired MAE | beats |
|---|---:|---:|---:|---|---:|---|
| primary_secondary_amine | 4 | 12.39 | 6.38 | no | 9.11 | no |
| unclassified | 4 | 20.98 | 18.72 | no | **2.59** | **yes** |
| alcohol | 3 | 17.01 | 5.90 | no | **1.61** | **yes** |
| carbonate | 2 | 15.61 | 15.77 | yes | **3.14** | **yes** |
| dinitrile | 2 | 18.03 | 11.56 | no | **1.78** | **yes** |
| ketone | 2 | 18.94 | 8.14 | no | **3.84** | **yes** |

"1 of 6 families beats the baseline" → **5 of 6**, robust across λ = 0.3…100 (`reviewer_1_analysis9.py`). The `unclassified` fold is the most dramatic: 20.98 → 2.59, because with an intercept the model correctly assigns ε ≈ 2 to the three alkanes and ε ≈ 39 to sulfolane instead of averaging them.

I want to be careful here in the *opposite* direction: **5 of 6 is itself not a strong result.** Each family has n_test = 2–4, so a single molecule moves a family's MAE by a factor of 2, and the count of families beating the baseline has a 0–6 range driven by 12 molecules. The honest reading is that **neither "1 of 6" nor "5 of 6" is resolvable at this n** — and the report's error was to treat "1 of 6" as a finding while applying no such caution.

### 4.5 What survives

The **negative** AD conclusion survives repair, and only it: in/out error ratio 1.045 (shipped) → **1.308** (repaired), still `NO_USEFUL_SEPARATION`, and Spearman(nn_tanimoto, |error|) ≈ −0.05 / +0.08 ≈ 0. But the correct causal reading is *not* "descriptors carry no transferable information". It is narrower and more mundane: **Morgan-2 Tanimoto on a 22-molecule pool dominated by short unbranched chains has almost no distance resolution** (15 of 22 molecules fall below 0.40; the three alkanes all collide at 1.0), so it cannot function as an AD metric for this pool. That is a statement about the AD metric, not about descriptor information content.

---

## 5. E6 — is the noise-ladder reversal physically explicable? → **FAIL** (as interpreted)

### 5.1 The measurements are fine; the interpretation is not

The arithmetic checks out: oracle Top-3 mean 37.83, model 24.45, pool mean 17.32, regret 13.38, P(random ≥ model) = 0.16, overlap 1/3, `insufficient_power` correctly declared. k = 3 is genuinely frozen, the baseline is genuinely predefined.

The verdict `REGRET_DECOUPLED_AND_ANTI_CORRELATED` and the text *"模型的点预测对筛选目标不仅无益，而且有害"* / *"是反相关"* are contradicted by the experiment's own table:

- **ρ(pred, true) = +0.755** — a strongly *positive* rank correlation. Anti-correlation would be negative.
- **Model Top-3 = 24.45 vs random 17.19** — the model beats random screening by **+7.26 ε units**. A "harmful" predictor does not beat random by 7 units on a 1.93–44 scale.

Both facts are printed in `e6_report.md` directly above the anti-correlation claim.

### 5.2 The actual mechanism: one correct extreme + an unresolved tie

Selection probabilities from 3000 draws (`reviewer_1_analysis3.py`):

| rank | molecule | true ε | P(sel) σ=0 | σ=4 | σ=8 | σ=16 |
|---:|---|---:|---:|---:|---:|---:|
| 1 | sulfolane | 44.00 | **1.00** | 0.99 | 0.84 | 0.54 |
| 2 | N-(2-hydroxypropyl)-…amine | 13.87 | 1.00 | 0.88 | 0.59 | 0.38 |
| 3 | 15-crown-5 | 15.48 | 1.00 | 0.60 | 0.42 | 0.30 |
| 4 | octanedinitrile | 25.94 | 0.00 | 0.17 | 0.23 | 0.22 |
| 5 | 1-methylimidazole | 39.78 | 0.00 | 0.11 | 0.18 | 0.21 |
| 6 | heptanedinitrile | 29.71 | 0.00 | 0.09 | 0.17 | 0.19 |

The model gets **the single most important pick right and never loses it** at the shipped noise levels. It then inverts ranks 2–6: ranks 2–3 have true ε 13.87 and 15.48 (both *below* the pool mean 17.32), while ranks 4–6 have true 25.94 / 39.78 / 29.71. **Mean of ranks 4–6 = 28.32 vs 27.94 for ranks 2–3** — ranks 4–6 are true-better by 8.4 units but were placed lower.

Why noise helps: the prediction gaps inside that band are **0.15–1.38 units**, while the model's own MAE is **17.29**. The ordering is unresolvable at the model's own error scale. Any perturbation large relative to 0.15–1.38 reshuffles the band, and 3 of those 4 candidates are better than the 15.48 currently in slot 3, so the Top-3 mean rises. This is a **lottery among near-tied candidates**, not the model pointing the wrong way.

### 5.3 Three signatures proving it is a lottery, not anti-correlation

**(a) Non-monotone response, with the correct asymptotic limit.** Extending the ladder:

| σ | 0 | 2 | 4 | 8 | 16 | 32 | 64 |
|---|---:|---:|---:|---:|---:|---:|---:|
| regret | 13.38 | 12.91 | 11.11 | **10.38** | 13.20 | 15.54 | 18.53 |

Regret has an **interior minimum** and rises at large σ toward the random-screening value (~20.6). If predictions were anti-correlated, large noise should keep *improving* regret toward — and past — random. It does the opposite: large noise destroys the one correct pick (sulfolane P(sel) 0.84 → 0.54) and regret climbs back. The shipped ladder stopped at σ = 8, exactly at the minimum, and read the descending limb as a trend.

**(b) Seed fragility under the feature set E1/E4 actually used.** 200 seeds, σ = 8 vs σ = 0:

```
11-feature model (as shipped in E6):  regret falls in 200/200 seeds (100%),  median Δ = −2.92
12-feature model (as used in E1/E4):  regret falls in  46/200 seeds ( 23%),  median Δ = −0.18
```

A physical claim about anti-correlation cannot hinge on whether `total_energy_hartree` is in the feature vector — a feature that E1's own manifest does not even register (§3.5).

**(c) The effect is smaller than one molecule moving.** The whole ladder spans Δregret = 2.82 units. One slot swap from rank-3 (15.48) to a better candidate (39.78) moves the Top-3 mean by (39.78 − 15.48)/3 = **8.10 units**. So over the entire ladder the selection changes by *less than one place*. At n = 22, k = 3, that is inside the Monte-Carlo/seed noise of the experiment itself.

### 5.4 What E6 can defensibly say

Only this: at n = 22 with k = 3, model MAE ≈ 17 and ε spanning 1.93–44, **Top-k ranking is unresolvable except at the single extreme**, the model *does* find that extreme, and P(random ≥ model) = 0.16 means no detectable screening value can be demonstrated at this sample size. That is a power statement, not a mechanism. The correct verdict is `UNDERPOWERED` / `LOCAL_TIE_UNRESOLVED`, not `REGRET_DECOUPLED_AND_ANTI_CORRELATED`.

Note also that under the repaired model the picture improves but does not rescue the experiment: regret 13.38 → 9.89, P(random ≥ model) 0.16 → 0.069 — still not significant at 0.05, still `insufficient_power`. E6's *conclusion of no demonstrated screening value* happens to survive; its *stated mechanism of anti-correlation* does not.

---

## 6. Which conclusions are physically defensible

### Defensible (keep)

1. **n = 22 cannot support confirmatory inference.** Correctly and repeatedly stated in E1, E4, E6 and `b05_gate_status.json`. This is the strongest methodological feature of the package.
2. **The X2/X3 tiers were never computed, and ε is a condensed-phase property.** `model_input_manifest.json` explicitly registers X2 (`conformer statistics`) and X3 (`condensed-phase independent physics`) as absent. Since ε is set by g and density, no complete-descriptor claim is possible. Physically correct and honestly disclosed.
3. **The pool is a feasibility set, not a training set** (B04 §"22 条不是数据集").
4. **Tanimoto cannot serve as an AD criterion for this pool.** Survivors §4.5 above; supported by in/out ratio 1.045 → 1.308 and Spearman ≈ 0.
5. **E6: no detectable screening value at n = 22** (P(random ≥ model) = 0.16). True, though for power reasons rather than mechanism.
6. **Provenance discipline**: `merge_forbidden`, frozen red lines, per-file SHA-256, AI consensus explicitly *not* human-signed. This is genuinely good practice and it is what made this review possible — I could reproduce every number exactly because the artefacts are hashed and the generator code is committed.

### Overreaching (withdraw or recompute)

1. ❌ **"Single-molecule structure+electronic descriptors exhibit no detectable predictive ability for liquid ε."** Inverted by the intercept repair (§3.2): MAE 6.50, R² +0.54, p = 0.000.
2. ❌ **"The descriptors cannot resolve chemically different liquids; this cannot be fixed by more data."** The package's most-emphasised conclusion. False: ECFP collision, not descriptor degeneracy; 85.9 % of the effect is global bias; the model predicts the "identical" pair differently in its own output file (§4).
3. ❌ **"Error is not out-of-domain extrapolation but descriptor resolution failure."** The dichotomy is a false one built on a mis-centred model. The third option the report never considers — *model specification* — is the correct one.
4. ❌ **"H3 supported, and more severely than expected: predictions are anti-correlated with the screening target."** Contradicted by ρ = +0.755 and by Top-3 beating random by +7.26 (§5).
5. ❌ **"Noise improves screening."** Seed-fragile (23 % of seeds under the E1/E4 feature set), non-monotone with an interior minimum, and smaller than one slot swap (§5.3).
6. ❌ **"ε is not learnable from molecular descriptors"** as a general statement — it is a statement about a 22-molecule, non-isothermal, partly non-liquid pool with an un-centred, unconstrained linear model.

### A framing correction for the parent

The package's narrative is *"the descriptors hit a validity boundary; this is not a tuning problem."* The evidence supports almost the opposite: this **was** a modelling problem (no intercept, no output bound, no temperature term, a duplicated and physically wrong volume feature, and an ECFP-based AD metric with no resolution), and once specified sanely, the same 12 descriptors on the same 22 molecules reach MAE 6.50 against a constant baseline of 10.81, with a permutation p of 0.000. A one-term analytic expression (μ²/V_m) already reaches ρ = +0.822. The real boundary that remains is narrower and more interesting: **descriptors capture the μ²/V_m term of Kirkwood but nothing of the collective correlation g**, and n = 22 cannot resolve much else.

---

## 7. Three most important chemistry / physics findings

### Finding 1 — The identical-fingerprint error is global bias, not descriptor failure (85.9 % of it)

This is the finding that matters most, because the prompt flags it correctly as decisive and the package promotes it to a headline "supported conclusion".

- **It is a fingerprint collision.** Morgan radius-2 gives heptane and nonane the *same 8 bits* `{80,294,591,794,1057,1143,1444,1911}` because unbranched-alkane environments only encode distance-from-terminus ≤ 2 bonds. Tanimoto 1.0 is an artefact of ECFP, and ECFP is *not* the model's input.
- **The model's descriptors are not degenerate**: heavy atoms 7 vs 9, molecular volume 128.66 vs 162.05 Å³.
- **The model's own output proves they are not**: nonane predicted −20.5962 vs heptane −14.9293, a 5.67-unit spread that is impossible under identical feature vectors. The report's premise ("the model can only give the same prediction") is refuted by the report's own CSV.
- **The error is a constant offset**: pooled residual −16.9384. Removing it takes the four errors from 22.58/16.86/21.87/16.61 to **5.64/0.08/4.94/0.33** — mean 19.48 → 2.75, i.e. **85.9 % of the claimed "descriptor blindness" is one un-centred intercept**.
- **The chemistry says the model should succeed here**: nonane and heptane differ by Δε = 0.05. A correct model predicts them nearly identically and nearly exactly — which the intercepted model does (off by 1.19 and 0.30). The reported 16.86/22.58 error on a 0.05-ε difference is a signature of mis-centring, not of chemical blindness.
- Also note it is **2 pairs, not 4 independent cases**.

### Finding 2 — ε ≥ 1 is a hard bound the model violated in half the pool, and the "failure" is mostly an intercept bug

- **10/22 and 11/22 predictions were below ε = 1** (8/22 and 11/22 *negative*) — for a non-magnetic liquid this violates passivity/Kramers–Kronig. The ridge had no intercept and no output constraint, so it emitted ε = −20.9.
- Clipping at ε = 1 alone, with zero fitting, lowers MAE 17.29 → 12.43.
- Adding the intercept: MAE 17.29 → **6.50**, R² −1.29 → **+0.54**, permutation p = **0.000**, ΔMAE(X1−X0) = −3.74 against null median +0.73.
- **The physics argument that ε is collective is only half right.** Kirkwood–Fröhlich g genuinely spans 0.44–6.51 across the 19 polar molecules (acetic acid 0.44 antiparallel dimer → AMP 6.51 H-bonded; textbook range) and g is absent from X0/X1. **But** the leading term μ²/V_m is single-molecule and achieves **ρ = +0.822** with ε — better than the 12-descriptor ridge's +0.755 — and Clausius–Mossotti with real molar volumes predicts the three alkanes to **0.077 MAE**. Also `molar_volume_m3_mol` is exactly `molecular_volume_A3 × N_A`, a vdW cavity sum (packing 0.53–0.68), not the bulk molar volume the theory requires; and `polarizability_A3 = polarizability_au × 0.148184` exactly. Effective rank ≈ 9, not 12. The correct boundary is "**descriptors get μ²/V_m but not g**" — much narrower than "descriptors are useless".

### Finding 3 — The noise-ladder "anti-correlation" is a non-monotone tie-lottery, and the flagship molecule is measured below its melting point

- **The reversal is a local tie, not global anti-correlation.** ρ(pred, true) = +0.755; model Top-3 beats random by **+7.26 ε**. The model nails rank 1 (sulfolane, P(sel) = 1.00 at σ = 0, still 0.84 at σ = 8) and then *inverts ranks 2–6*: ranks 2–3 are true 13.87/15.48 (below pool mean 17.32) while ranks 4–6 are true 25.94/39.78/29.71 (mean 28.32, true-better by 8.4). With within-band prediction gaps of 0.15–1.38 against a model MAE of 17.29, the ordering is simply unresolvable, so noise reshuffling the band raises the Top-3 mean. Regret is **non-monotone with an interior minimum**: 13.38 → 10.38 (σ = 8) → 13.20 (σ = 16) → 18.53 (σ = 64, random ≈ 20.6). The shipped ladder stopped at σ = 8, on the descending limb. And the effect is seed-fragile (23 % of seeds under the E1/E4 feature set) and smaller than **one** slot swap (Δregret 2.82 vs 8.10 per swap).
- **The load-bearing molecule is not a liquid at its stated temperature.** Sulfolane — ε = 44.0, the pool maximum, and the only oracle Top-3 molecule the model finds — is recorded at 298.15 K with mp = 27.8 °C (300.95 K), i.e. **−2.8 K below its melting point**. Cyclohexanol (−0.9 K), 2-amino-2-methylpropan-1-ol (−1.0 K) and N-(2-hydroxypropyl)-2-hydroxy-1-propanamine (−12.0 K) are likewise at or below mp. The project's **own** frozen liquid-window gate blocks 10 of these 22, and it was never applied at admission even though all 22 rows carry `condition_pair_valid = true`. Combined with a 10 K non-isothermal spread (24–40 % of target sd) and the absence of `T_K` from the model despite a 1/T term, the pool's condition metadata is not yet sound enough to carry confirmatory physics claims.

---

## 8. Recommended actions (for the parent)

1. **Withdraw** the "descriptor validity boundary" headline from `model_boundary_report.md` §0/§4/§9 and from `b05_gate_status.json` `supported_conclusions`. Three of its six items are falsified.
2. **Fix the specification and re-run E1/E4/E6** with: an intercept (or y-centring), standardisation fitted inside each fold only, an output constraint ε ≥ 1, `T_K` as a feature (or restrict to a single isothermal set), and the duplicate features (`molar_volume_m3_mol`, `polarizability_A3`) dropped or replaced with real bulk molar volume.
3. **Delete the identical-fingerprint paragraph** or rewrite it as: *"Morgan-2 collides on unbranched alkanes; this is an ECFP limitation, and the tabular descriptors in fact resolve the pair correctly once the model is centred."*
4. **Recompute E6's H3 verdict** with the extended noise ladder (σ up to 64) so the non-monotonicity is visible, and report the seed distribution rather than a single seed. Replace `REGRET_DECOUPLED_AND_ANTI_CORRELATED` with `UNDERPOWERED`.
5. **Apply the project's own liquid-window gate to the pool** and re-audit `condition_pair_valid`; resolve or exclude the 4 sub-melting-point rows, sulfolane first.
6. **Restore the missing feature-registry row** for `total_energy_hartree`, or drop the feature; document λ. E1 and E6 must not report "the same model" with different MAEs.
7. **Do not add more data yet.** With n = 22 the binding constraints are specification and condition metadata, not sample size. More molecules of the same kind on the same mis-specified model will reproduce the same conclusion.

---

## 9. Reproduction

```
cd "E:\Claude Code\电解质ML\电解质ML"
.venv\Scripts\python.exe outputs/b04_b05_review/reviewer_1_analysis.py      # A–F
.venv\Scripts\python.exe outputs/b04_b05_review/reviewer_1_analysis2.py     # G–J
.venv\Scripts\python.exe outputs/b04_b05_review/reviewer_1_analysis3.py     # K–N
.venv\Scripts\python.exe outputs/b04_b05_review/reviewer_1_analysis4.py     # exact repro
.venv\Scripts\python.exe outputs/b04_b05_review/reviewer_1_analysis5.py     # ECFP proof
.venv\Scripts\python.exe outputs/b04_b05_review/reviewer_1_analysis6.py     # liquid window
.venv\Scripts\python.exe outputs/b04_b05_review/reviewer_1_analysis7.py     # Kirkwood g
.venv\Scripts\python.exe outputs/b04_b05_review/reviewer_1_analysis8.py     # LOFO repair
.venv\Scripts\python.exe outputs/b04_b05_review/reviewer_1_analysis9.py     # lambda sweep
.venv\Scripts\python.exe outputs/b04_b05_review/reviewer_1_analysis10.py    # noise ladder
.venv\Scripts\python.exe outputs/b04_b05_review/reviewer_1_analysis11.py    # seed robustness
```

No file outside `outputs/b04_b05_review/` was created or modified. All source artefacts were opened read-only. Integrity of the evidence was verified rather than assumed: `_verify_hashes.py` re-computes SHA-256 for every `outputs` entry declared in the three manifests plus every hashed input that is present, and **13/13 verify** (E1 metrics / permutation_null / predictions / report; E4 leave_one_family_out / structural_distance_ood / source_ood / applicability_domain / report; E6 topk_regret / screening_reliability / rank_vs_error / report). So the numbers I dispute are the numbers that were published, not drift I introduced.

Note on the shared directory: other reviewers' artefacts (`reviewer_2_*`, `r4_attack_*`, `v3_*`, `verify_provenance*`) are present in `outputs/b04_b05_review/` and were produced concurrently and independently. I did not read or rely on them; this review was formed only from the shipped B04/B05 artefacts and the committed generator code, per the independent-review requirement.

