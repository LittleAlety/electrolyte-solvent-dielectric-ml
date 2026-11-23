# B100 — Reviewer 4: Independent Adversarial Audit (red team)

**Scope.** Attack claims A–H of PLAN B v6.0 as stated to the review panel, using only the frozen artefacts in
`outputs/b100/` and my own independent re-implementation of the protocol. I did not modify any existing file;
everything below is in `outputs/b100_review/`.

**Bottom line.** Eight claims, eight verdicts: **1 PASS, 6 HOLD, 1 FAIL.** One claim should be retracted
(claim D's causal explanation and its "6/8 families generalise"), one should be reported as a range rather than a
point value (claim G), and three headline numbers (R² 0.477, R² 0.296, p = 0.0036) are arithmetically correct but
measure something much weaker than the prose implies (band separation, one physical term, family/motif recognition).

| # | Claim | Decision | Survives | Action |
|---|---|---|---|---|
| A | 221 molecules, best R² 0.477 / MAE 3.30 vs 5.09 | HOLD | false | DOWNGRADE_CLAIM |
| B | μ²/Vm + α/Vm (2 feat, R² 0.296) beat 15 structural (0.096) | HOLD | false | DOWNGRADE_CLAIM |
| C | Dipole ≈ whole electronic block; α and gap add nothing | **PASS** | true | ACCEPT_AS_IS |
| D | 6/8 families generalise; halocarbon fails because it is lowest-ε | **FAIL** | false | RETRACT_CLAIM |
| E | Applicability domain effective, out/in MAE ratio 2.23 | HOLD | true | DOWNGRADE_CLAIM |
| F | Top-k screening significantly better than random, p = 0.0036 | HOLD | false | DOWNGRADE_CLAIM |
| G | 30/36 polar flexible molecules have unreliable single-conformer dipoles | HOLD | true | DOWNGRADE_CLAIM |
| H | Dataset supports a 100+ molecule study; hard gates met | HOLD | true | DOWNGRADE_CLAIM |

---

## 0. Reproduction first

Before attacking, I verified that I can reproduce every published number with an independent implementation
(NumPy ridge with intercept, standardisation inside the training fold, 5-fold inner CV over the same λ grid,
outer leave-one-out). All six E1 blocks reproduce to 4 decimals, and so do E4, E6 and the conformer counts:

| Block | Published MAE / R² | My MAE / R² |
|---|---|---|
| X0_structure (15) | 4.3992 / 0.0958 | 4.3992 / 0.0958 |
| X1_electronic (3) | 4.3265 / 0.1908 | 4.3265 / 0.1908 |
| X0_plus_X1 (18) | 3.6885 / 0.2803 | — (not needed for the attacks) |
| dipole_only (1) | 4.3470 / 0.1137 | 4.3470 / 0.1137 |
| Xn_volume_normalised (2) | 4.1030 / 0.2961 | 4.1030 / 0.2961 |
| X0_X1_Xn (20) | 3.2999 / 0.4770 | 3.2999 / 0.4770 |
| E4 halocarbon | 6.7778 / −18.4656 | 6.7778 / −18.4656 |
| E6 p(random ≥ model) | 0.003575 | 0.003605 (400 k MC) |
| AD ratio @0.5 | 2.2289 | 2.2289 |

So nothing below is a "your code is broken" finding. The attacks are about **what the numbers mean**.

Method files: `_lib.py`, `attack_ABC.py`, `attack_D.py`, `attack_EF.py`, `attack_GH.py`, `attack_extra.py`,
`attack_family.py`, `attack_labels.py`; raw outputs in `attack_*.json`.

---

## 1. Claim A — the 0.477 R² is low/high separation, not prediction

**Attack.** Decompose the label variance into between-band and within-band parts, then ask what the model does
*inside* each band.

- 221 molecules split by ε: **106 below 5, 100 between 5 and 20, 15 above 20**.
- Variance decomposition: SS_total 21 575, **SS_between-bands 12 595 = 58.4%**. The best model's R² is **0.477** —
  *below* the between-band share. That is only possible because its within-band skill is negative.
- Within-band, using the model's own LOO predictions:

| Band | n | ε mean (sd) | Model MAE | Band-constant MAE | R² within | Bias |
|---|---:|---:|---:|---:|---:|---:|
| LOW (<5) | 106 | 3.09 (1.01) | 2.472 | **0.894** | **−12.89** | +1.32 |
| MID (5–20) | 100 | 8.46 (3.82) | 2.543 | 2.796 | +0.20 | +0.75 |
| HIGH (>20) | 15 | 33.89 (23.03) | 14.199 | **12.160** | **−0.16** | −14.20 |

In the band holding **48% of the molecules** the model is 2.8× worse than "say the band mean"; in the high-ε band
it is worse than "say 33.9 for everything". Only the middle band shows skill (R² 0.20, ρ 0.62). An oracle
3-band-mean predictor scores **MAE 2.519, R² 0.584**, i.e. *better than the 20-feature model* — the model does not
even recover the full band separation.

**The headline is not even stable.**
- Drop one molecule (hydrocyanic acid, ε = 114.9): **R² 0.603, MAE 2.63** (from 0.477 / 3.30).
- Winsorise at the 95th percentile (11 molecules capped at 23.8): **R² 0.637, MAE 2.37**.
- ε ≥ 20 subset: R² −0.16, MAE 14.20. Halocarbon subset: R² −2.61. ε < 5 subset: R² −14.4.
- On log ε the same model gets **R² 0.72** — the raw-ε R² is a scale-sensitive statistic, not a measure of
  "predicting ε well".

**Absolute scale.** MAE 3.30 is 43% of the mean ε (7.61) and **64% of the median ε (5.13)**.

**Selection bias in the 221.** All 36 molecules outside the common set are missing `polarizability_au`. They are
systematically high-ε: mean 16.68 (median 6.83, max 178.47) vs 7.61 kept; 27.8% vs 6.8% have ε ≥ 20. The
"221-molecule" study is a 221-molecule study of the *easier* 86%.

**Verdict: HOLD, claim does not survive as worded, DOWNGRADE.** Report R² 0.477 *and* the band decomposition, the
winsorised value, and the within-band MAE table. "Predicts εr well" is not supported; "separates low-ε from
high-ε molecules and predicts within the 5–20 band" is.

---

## 2. Claim B — the 2-vs-15 comparison is unfair twice over

**Attack 1: the 15 columns are not 15 features.**
- `formal_charge` is constant (one unique value, 0) — a dead column.
- `molar_volume_m3_mol` and `molecular_volume_A3` correlate **0.9999999996** — an exact duplicate.
- `morgan2_nbits` is an ECFP bit count; `mw` correlates 0.74 with heavy-atom count.
So 12 real, mutually correlated features, fed to a ridge that shrinks 15 coefficients — which is why the block
under-performs its **own best 2-column subset**:

| Structural feature set | k | MAE | R² |
|---|---:|---:|---:|
| all X0 (as published) | 15 | 4.3992 | 0.0958 |
| X0 with the two junk columns removed | 13 | 4.3944 | 0.1157 |
| best pair: `tpsa_A2 + molecular_volume_A3` (searched all 105 pairs) | 2 | 4.211 | **0.1955** |
| second best: `heavy_atom_count + tpsa_A2` | 2 | 4.227 | 0.1924 |

The 0.096 is a ridge-dilution artefact, not the ceiling of structural descriptors. The honest contrast is
0.296 (or 0.236) vs 0.196, not 0.296 vs 0.096.

**Attack 2: one of the two winning features does all the work; the other is inert.**

| Feature(s) | k | MAE | R² | rank corr |
|---|---:|---:|---:|---:|
| `mu_sq_over_Vm` alone | 1 | **3.935** | 0.236 | 0.787 |
| `alpha_over_Vm` alone | 1 | 5.198 | 0.0147 | **−0.064** |
| μ²/Vm + α/Vm (published winner) | 2 | 4.103 | 0.296 | 0.669 |
| `1/molar_volume` alone | 1 | 4.678 | 0.244 | 0.379 |
| `{dipole², 1/Vm}` unconstrained | 2 | 4.182 | **0.363** | 0.639 |

Adding α/Vm to μ²/Vm **worsens MAE** (3.935 → 4.103; paired Δ 0.168, 95% CI −0.13…+0.47, worse in 87% of bootstrap
resamples) while *improving* R² — a pure shrinkage artefact. And the product form is not special: splitting it into
`{dipole², 1/Vm}` gives R² 0.363 with 2 features, better than the "Kirkwood" pair.

**Verdict: HOLD, does not survive as worded, DOWNGRADE.** Correct statement: "μ²/Vm alone (R² 0.236, MAE 3.94)
beats the 12 real structural descriptors (R² 0.096, MAE 4.40), but not their best 2-column subset (R² 0.196), and
the α/Vm term contributes nothing." This finding also *contradicts* claim C's partner claim in the report — see §3.

---

## 3. Claim C — dipole sufficiency: **this one survives**

**Attack.** Paired bootstrap on per-molecule absolute errors, 221 molecules, 5 000 resamples.

| Comparison | ΔMAE (95% CI) | dipole better |
|---|---|---:|
| dipole only vs electronic 3-feature block | +0.020 (−0.281…+0.316) | 121/221 |
| dipole vs dipole+gap | +0.009 (−0.032…+0.049) | 134/221 |
| dipole vs dipole+alpha | −0.075 (−0.385…+0.225) | 93/221 |
| (dipole+μ²/Vm) vs +alpha | −0.058 (−0.30…+0.17) | 106/221 |
| (dipole+μ²/Vm) vs +gap | −0.006 (−0.034…+0.021) | 132/221 |

Every confidence interval contains zero; the signs say polarisability makes things marginally *worse* and the gap
is pure noise. Individually: α alone R² 0.068, gap alone R² 0.025, α/Vm alone R² 0.015 with ρ = −0.06.

**Caveat kept (not a failure):** the electronic *block* has a much higher R² (0.191 vs 0.114) at the same MAE, because
three features shrink the extreme predictions of the 15 high-ε molecules. So the claim is true on MAE/RMSE and
false if quoted as "same R²". Report MAE.

**Verdict: PASS, ACCEPT_AS_IS** (with the MAE-vs-R² wording fix). This is the only claim in the package that I
attacked hard and could not break.

---

## 4. Claim D — the halocarbon question: **failure real, explanation false**

This is the claim the panel asked me to settle. There are two separate questions.

### 4.1 Is the halocarbon baseline unfair because the family is narrow?

Partly — but not in a way that excuses the model.

The e4 "baseline" is the **global leave-one-family-out training mean** (ε̄_train = 8.32), evaluated on the 67
halocarbon test molecules (mean 5.98). It reproduces exactly: MAE 2.5306. Because the family is narrow (sd 1.79,
CV 0.30, IQR 2.45), the absolute MAE of any constant is small, so 2.53 is a low number; that is the genuine
narrowness effect. But the *correct* trivial competitors on the same 67 molecules are lower still, and the model
loses to them by 4.5–7.5×. Narrowness makes a level error maximally visible; it does not manufacture the failure.

| Predictor | MAE | R² | Notes |
|---|---:|---:|---|
| Global train mean (published baseline) | 2.531 | — | ε̄ = 8.32 |
| Oracle family mean (in-sample) | 1.477 | — | best constant |
| Nested family mean (leave-one-out) | 1.500 | — | honest constant, no leakage |
| In-family 2-feature LOO (`n_rotatable + n_halogen`) | **0.895** | — | a chemist's rule of thumb |
| In-family 18-feature LOO | **0.850** | **0.510** | halocarbon ε is learnable |
| **Transfer model (published)** | **6.778** | **−18.47** | bias +3.10, pred sd 8.05 |

The transfer model is **4.5× worse than a constant** and **7.5× worse than a 2-feature in-family rule**. Only 6/67
predictions are within 20% relative error (median relative error 119%), and 50/67 are over-predicted. On this
evidence the failure is real, and the "narrow family" does not excuse it.

### 4.2 But the *stated cause* is factually wrong, and R² is an artefact

The report explains the failure as: *"halocarbons are the lowest-dielectric family (ε mostly 2–5) … the ε of low-ε
weakly-associating families barely varies with molecular structure."* All three sub-claims are false:

| Family | ε mean | ε sd | ε min–max | CV |
|---|---:|---:|---:|---:|
| other_neutral_liquid (alkanes/alkenes) | **2.55** | 2.41 | 1.89–15.8 | 0.94 |
| aromatic | **2.97** | 1.54 | 2.24–9.0 | 0.52 |
| ether | 5.86 | 4.40 | 2.23–22.6 | 0.75 |
| **halocarbon** | **5.98** | **1.79** | **2.24–10.19** | **0.30** |
| ester | 6.83 | 5.15 | 3.11–27.8 | 0.75 |
| alcohol_polyol | 8.88 | 8.53 | 2.87–41.2 | 0.96 |
| ketone_aldehyde | 14.49 | 4.04 | 9.07–22.3 | 0.28 |
| "amine" (actually nitro/nitrate) | 20.47 | 10.31 | 2.52–35.9 | 0.50 |

- Halocarbon is the **third-lowest** family, not the lowest; its mean is 5.98, not ≈2; only **22/67** are below 5.
- Its ε spans **2.24–10.19** and is predictable in-family with **R² 0.51 / MAE 0.85** — it does vary with structure.
- R² = −18.5 is a narrow-variance artefact: with sd 1.79 and MAE 6.78 no model can have a positive R². R² is the
  wrong metric for this family; MAE is the right one, and MAE still damns the model.

### 4.3 What actually explains it: a dipole-to-ε mismatch, not "low ε"

The mechanism is visible in the family means. Halocarbons carry **essentially the same mean dipole as ketones
(3.45 D vs 3.48 D) at 2.4× lower ε (5.98 vs 14.49)**. They also have high polarisability (103.8 au) like alkanes
(111.6) and aromatics (105.6), while the high-ε families have *low* polarisability (amines 75.2, nitriles 55.1).
The model's dominant term is μ²/Vm, so the family where μ is high but ε is low is precisely where it must
over-predict — bias +3.10. The lowest-ε family (alkanes, μ 0.19 D, ε 2.55) is *well* calibrated (bias −0.21)
because its dipole is near zero. So "low ε" is not the driver; the driver is a family whose ε is low **relative to
its dipole and polarisability**, which no additive single-molecule model can know.

### 4.4 And the model is not information-free — it is miscalibrated

An oracle 2-parameter recalibration (slope + intercept, fitted on the test family — optimistic, but diagnostic) of
the *same* predictions gives **MAE 1.233**, better than the 1.48 family constant; a mean shift alone gives 5.51. So
the transfer model carries real rank information (Spearman 0.568) and fails on **absolute scale**: predicted sd
8.05 against a true sd of 1.79, bias +3.10, λ pinned at the top of the grid (10). This is a calibration/level
failure, not a "descriptors are useless for halocarbons" failure.

### 4.5 "6/8 families generalise" is a weak-baseline artefact

The e4 baseline is the global train mean, which is far from every low-ε family's mean, so *any* model that predicts
"low" beats it. Against an honest nested family-mean constant:

| Family | Model MAE | Nested family-mean MAE | Beats honest constant? | R² |
|---|---:|---:|---|---:|
| alcohol_polyol | 4.845 | 5.835 | **yes** | −0.09 |
| ketone_aldehyde | 2.965 | 3.697 | **yes** | +0.02 |
| ether | 3.373 | 2.618 | no | −0.16 |
| ester | 3.842 | 2.854 | no | +0.14 |
| other_neutral_liquid | 2.249 | 0.951 | no | −2.52 |
| aromatic | 4.647 | 0.949 | no | −9.54 |
| amine (nitro/nitrate) | 9.007 | 8.690 | no | −0.18 |
| halocarbon | 6.778 | 1.500 | no | −18.47 |

**2/8, not 6/8** — and **6/8 families have negative R²**. The "6/8" headline counts as a success a model that
over-predicts the aromatic family (mean ε 2.97) by **+4.65 on average** (MAE 4.65), simply because the global
train mean it is compared against is 8.32.

### 4.6 A separate dataset defect that invalidates the family table

The RDKit amine SMARTS matches nitro nitrogen. Of the 21 "amine" family members, **14 are nitro compounds**,
**6 are nitrate esters** (overlap), and only **7 are actual amines/anilines** (2-(dimethylamino)ethanol,
2-aminoethanol, three anilines, diethanolamine, triethanolamine). The "amine" row (ε mean 21.4) is really a
nitro/nitrate row. Worse, `b100_stage1_readiness.json` states the **nitro family has zero molecules and must be
added**, while 14 nitro compounds are already in the dataset under the wrong label. Per-family statements in D
(and the "12 families covered" statement in H) are therefore not trustworthy as written.

**Verdict: FAIL, RETRACT.** The failure itself stands; the explanation and the 6/8 generalisation count do not.

### 4.7 Direct answer to the panel's question

> **Is the halocarbon failure real or a narrow-ε-baseline artefact?**

**Both, in different senses.**
1. **The failure is real.** 6.78 MAE vs 1.50 for a nested family constant and 0.90 for a 2-feature in-family rule;
   bias +3.10; predicted sd 8.05 vs true 1.79; only 6/67 within 20%.
2. **It is not caused by low ε.** Halocarbon is the 3rd-lowest family (5.98), it spans 2.24–10.19, it is learnable
   in-family (R² 0.51), and the lowest-ε family (alkanes, 2.55, μ 0.19 D) is the *best*-calibrated one (bias −0.21).
   The real driver is a dipole-to-ε mismatch: halocarbon μ 3.45 D ≈ ketones 3.48 D while ε is 2.4× lower.
3. **R² = −18.5 is a narrow-variance artefact**, and the model does carry cross-family signal (oracle recalibration
   MAE 1.23 < 1.48 constant). So the correct diagnosis is **scale miscalibration of an additive linear model
   transferred outside its chemical domain**, not "ε barely varies with structure".

---

## 5. Claim E — the AD ratio is robust but "effective" is not

**Attack 1: threshold sensitivity.** The 0.5 cutoff was chosen post hoc, so sweep it (bootstrap CI of the ratio):

| Tanimoto | n in/out | MAE in | MAE out | Ratio | 95% CI | Median-error ratio |
|---|---:|---:|---:|---:|---|---:|
| 0.30 | 213/8 | 3.149 | 18.060 | 5.74 | 1.42–13.61 | 3.39 |
| 0.40 | 197/24 | 2.970 | 9.588 | 3.23 | 1.25–6.57 | 1.38 |
| **0.50** | **151/70** | **2.655** | **5.918** | **2.23** | **1.32–3.59** | **1.28** |
| 0.60 | 82/139 | 2.052 | 4.654 | 2.27 | 1.55–3.26 | 1.90 |
| 0.70 | 55/166 | 1.760 | 4.327 | 2.46 | 1.72–3.59 | 1.95 |
| 0.80 | 37/184 | 1.635 | 4.102 | 2.51 | 1.77–3.69 | 1.86 |

The ratio is **numerically robust** (never below 2.2, never below 1 on any reasonable threshold), so the 0.5 choice
is not what produced it. That part of the claim survives.

**Attack 2: is it a shift in typical error or a tail?** At 0.5 the *median* error ratio is only **1.28** (1.93 vs
2.46). The mean ratio of 2.23 is produced by a handful of large failures, not by a broad degradation.

**Attack 3: is the domain a proxy for ε?** Out-of-domain molecules have higher ε (mean 9.92 vs 6.54), but the
partial Spearman of error vs similarity controlling for ε is −0.261 (raw −0.276), so similarity carries some
independent signal. However, stratifying by ε collapses the effect where it matters for the middle of the
distribution: [0,5) ratio 1.64, **[5,10) 1.08**, [10,20) 2.13, [20,∞) 2.38.

**Attack 4: does it help the decision the project cares about?** No. At ε ≥ 20 (n = 15) the in-domain MAE is
**10.58** — being "in domain" does not make a prediction usable — and **8 of those 15 molecules are declared
out-of-domain**, i.e. the AD discards exactly the high-ε molecules a screening campaign is looking for. In-domain
membership is also dominated by near-duplicate homologous series (48/67 halocarbons are in-domain), so the low
in-domain MAE partly measures "the nearest neighbour is a homologue".

**Verdict: HOLD, survives numerically, DOWNGRADE the word "effective".** Report the median ratio (1.28), the
ε-stratified ratios, the two families where it reverses (halocarbon 0.89, aromatic 0.99), and the fact that the
threshold has never been validated against a held-out calibration or a decision outcome.

---

## 6. Claim F — p = 0.0036 is real and measures the wrong thing

The panel asked me to attack this hardest. I did, in five ways.

### 6.1 What the model actually finds

| Metric | Value |
|---|---:|
| Headroom captured | **42.4%** (13.36 of 31.48) |
| Oracle top-10 overlap | **4/10** |
| Recall of top-10% (22 molecules) | **8/22 = 36%** |
| Recall of top-20% (44 molecules) | **8/44 = 18%** |
| NDCG@10 | 0.366 |
| Molecules with ε ≥ 20 found in top-10 | 4/15 |
| Missed entirely: ε = 114.9 (HCN) | predicted rank **19** |
| Missed entirely: glycerol ε = 41.2 | predicted rank **24** |
| **Model's #1 pick** | **tetranitromethane, ε = 2.52, predicted 24.15 → rank 177 of 221** |

True ranks of the ten picks: **177, 17, 5, 9, 18, 22, 90, 4, 3, 16**. Two picks are outside the top 25% of the
pool, one is the 177th-best molecule, and two of the three most valuable molecules in the pool are not selected.

### 6.2 Is p driven by a few easy molecules?

No — it is remarkably robust to removing extreme labels. Dropping the 1/2/3/5 highest-ε molecules leaves
p < 1 × 10⁻⁵ (my MC resolution) and *raises* headroom captured to 60–66% (because the oracle collapses faster than the model). So the
p-value is not an extreme-value artefact. **But the "42.6% of headroom" headline is**: remove one molecule
(ε = 114.9) and headroom captured becomes 60%. The two sentences in the report — p = 0.0036 and "only 42.6% of
headroom" — are of very different robustness.

### 6.3 Is p driven by family/motif recognition?

Yes. The top-10 is **9 nitro/nitrate compounds + acetic acid** (tetranitromethane, nitroglycerin, ethylene nitrate,
two propanediol dinitrates, chloropropanediol dinitrate, nitrobenzene, nitromethane, ethyl nitrate, acetic acid).
A **family-matched null** — draw 9 molecules at random from the same family and 1 from the acid family — gives
mean 18.86 and **p = 0.249**. Within the family the model's picks are indistinguishable from random. The 0.0036
is the probability that a random 10-subset happens to contain 9 nitro compounds; it is a motif detector, not an
ε ranker.

### 6.4 Would a trivial rule do as well?

Better. Same pool, same k, same labels:

| Ranker | Top-10 mean ε | p(random ≥) | NDCG@10 | Overlap with model's picks |
|---|---:|---:|---:|---:|
| μ²/Vm (1 feature) | **26.88** | **2.0e-5** | 0.505 | 2/10 |
| 1/MW (1 feature) | 26.07 | 4.5e-5 | 0.747 | 2/10 |
| 1/molar volume (1 feature) | 25.56 | 6.5e-5 | **0.764** | 2/10 |
| `n_halogen` ascending (1 feature) | 21.77 | 1.9e-3 | 0.378 | **9/10** |
| tpsa | 19.62 | 8.5e-3 | 0.348 | 6/10 |
| **20-feature ridge model** | **20.97** | **3.6e-3** | **0.366** | — |

A **single** descriptor beats the 20-feature model on every screening metric, by 55–180× in p. And 9 of the
model's 10 picks are reproduced by "sort by halogen count ascending": the model's screening behaviour is
essentially "not a halocarbon, and lots of nitrate oxygens".

### 6.5 k-sensitivity

k = 5: model 19.18, headroom 26.7%, p = 0.0245. k = 15: model 22.51, headroom 56.7%, p < 1e-5. The claim is
strongest at the k the report did not pre-register for the headline (k = 15) and weakest at k = 5.

**Verdict: HOLD, claim survives arithmetically, does not survive as evidence of screening skill.** Recommended
wording: *"The model selects a high-ε functional-group class (nitro/nitrate) far better than chance (p = 0.0036),
but it captures only 42% of headroom, finds 4/10 of the true top-10, misses the two best molecules, ranks the
177th-best molecule first, is no better than a family-matched null (p = 0.25), and is beaten by ranking on a single
descriptor already in the model (μ²/Vm, p = 2e-5)."*

---

## 7. Claim G — 30/36 is threshold- and metric-dependent

| Criterion | Count / 36 | % |
|---|---:|---:|
| rel spread > 5% OR rel dev > 5% | 36 | 100% |
| **rel spread > 10% OR rel dev > 10% (published)** | **30** | **83%** |
| rel spread > 15% OR rel dev > 15% | 23 | 64% |
| rel spread > 20% OR rel dev > 20% | 23 | 64% |
| rel spread > 30% OR rel dev > 30% | 21 | 58% |
| single-conformer-vs-Boltzmann dev > 10% only | 16 | 44% |

The published 30/36 is driven almost entirely by the **max−min spread across up to 6 conformers** (all 30 flagged by
spread; only 16 by the deviation of the single conformer from the Boltzmann average, whose **median is 7.9%**). The
spread statistic answers "are the conformers different?" — for a flexible molecule the answer is trivially yes. The
statistic that matters for the model is the single-vs-average deviation, and by that metric 16/36 = 44% exceed
10% and 25/36 = 69% exceed 5%.

**Scope.** The sample is the 40 most flexible molecules (n_rotatable ≥ 6) — 40 of the 48 such molecules, i.e.
**18.7% of the 257**. "30/36 polar flexible molecules" is correct only for that flexibility tail; it must not be
read as a dataset-wide rate.

**Consequence, quantified.** With the fitted ε ~ μ²/Vm slope, a 33% dipole spread maps to ~1.6 ε units of noise at
the median molecule; the 7.9% median deviation maps to ~0.4. Against a model MAE of 3.30, conformer noise is a
real but secondary contributor to the headline error budget.

**Verdict: HOLD, conclusion survives (indeed holds at 5%), number should be a range (64–100%) with its scope.**

---

## 8. Claim H — the gates are honestly met; the inferential claims are thinner

**Attacks that failed (the gate handling is honest):**
- **Identity/count:** 257 unique InChIKeys, no duplicate names.
- **Label provenance:** all **257/257** labels match a ledger row exactly in *both* ε and T — no interpolation, no
  untraceable label.
- **Temperature:** all 257 measurements lie in **293.15–303.15 K**, 81 at 298.15, max deviation **5.0 K**. Empirically
  (30 molecules with temperature series) median fractional dε/dT = **−0.462%/K**, so 5 K ≈ **2.3% ≈ 0.21 ε units** —
  negligible against MAE 3.30. The panel's temperature worry does not land.
- **Frequency:** 238 NBS-514 rows carry no per-measurement frequency, but this is documented as source-level static
  definition, and the 127 transcription rows with 360–500 MHz footnotes were excluded at source. The 20 ThermoML rows
  report 0.01–3 MHz; at 3 MHz nitrobenzene gives 34.78 vs the static label 34.82 (0.1%). Only **one** label
  (2,2,4-trimethylpentane) is sourced from a non-zero-frequency row (0.05 MHz). The panel's frequency worry is
  documented and small.
- **Phase:** 35 molecules with unknown melting point were **excluded**, not defaulted to liquid; 14 solid/supercooled
  and 27 ionic/mixture were also excluded. This is the honest direction.
- **Label noise:** 31 molecules have repeated measurements near 298 K; median relative range **2.5%**, p90 10.3%,
  13% above 10% — small compared with MAE 3.30, so the model's error is not label noise.

**Attacks that landed:**
- **226/257 records come from one compilation (NBS Circular 514), only 18 independently corroborated.** The effective
  independent N for any cross-source claim is 18, not 257. The reports say this, but the "100+ molecule study"
  headline reads as if 257 independent measurements existed.
- **14% attrition with bias.** The 36 molecules dropped from the 221-molecule analysis set (missing polarizability)
  are systematically high-ε: mean 16.68 vs 7.61; 27.8% vs 6.8% above ε = 20; max 178.47. The analysis set is the
  easier 86% of the dataset.
- **High-ε support is 15 molecules** (ε > 20 in the common set), which is why H4 is `INSUFFICIENT_POWER`.
- **Family stratification is partly fictional** (§4.6): nitro is reported as a missing family while 14 nitro
  compounds sit in the "amine" family. Four families have < 10 members (carboxylic acid 4, nitrile 3, carbonate 2,
  phosphate 1).

**Verdict: HOLD, gate arithmetic survives, DOWNGRADE the framing.** Recommended wording: *"257 records admitted,
221 analysable, 18 independently corroborated, 15 in the high-ε stratum; the dataset supports a large-N descriptive
study, not yet a predictive one."*

---

## 9. Claims that should be downgraded or retracted (summary)

| Action | Claim | Why |
|---|---|---|
| **RETRACT** | D — "halocarbon failure because it is the lowest-ε family; ε barely varies with structure" | Halocarbon is 3rd-lowest (ε 5.98, range 2.24–10.19, CV 0.30); in-family R² 0.51, MAE 0.85. The real cause is scale miscalibration (bias +3.10, pred sd 8.05 vs true 1.79; oracle recalibration MAE 1.23). |
| **RETRACT** | D — "6/8 families beat the baseline / cross-family generalisation works" | 6/8 have negative R²; only 2/8 beat a nested family-mean constant. The baseline is the global train mean, which is trivially far from low-ε families. |
| **RETRACT** (readiness report) | "nitro family has 0 molecules; must be added" | 14 nitro compounds are present, mislabelled as "amine" (RDKit amine SMARTS matches nitro N). |
| **DOWNGRADE** | A — "predicts εr well, R² 0.477" | R² < between-band variance share (0.584); within-band skill negative in 2/3 bands; R² 0.603–0.637 after one molecule is dropped/winsorised; log-target R² 0.72; MAE is 64% of the median ε. |
| **DOWNGRADE** | B — "2 features (μ²/Vm + α/Vm) beat 15 structural" | 15 → 12 real features; best 2-column structural subset reaches 0.196; α/Vm is inert (R² 0.015, MAE worsens); {dipole², 1/Vm} reaches 0.363. |
| **DOWNGRADE** | F — "significantly better than random, p = 0.0036" | Family-matched null p = 0.249; 3 single descriptors beat the model (p 2e-5 to 6.5e-5); #1 pick is the 177th-best molecule; 42.4% headroom, 4/10 overlap. |
| **DOWNGRADE** | G — "30/36 unreliable" | Range 64–100% over defensible thresholds; 44% by the deviation metric; scope = 18.7% of the dataset. |
| **DOWNGRADE** | E — "AD is now effective" | Ratio robust but median ratio 1.28, reversed in 2/8 families, in-domain ε ≥ 20 MAE 10.58, 8/15 high-ε molecules are out-of-domain; no decision-level validation. |
| **KEEP** | C | Survives paired bootstrap; only the MAE-vs-R² wording needs fixing. |

## 10. Cross-claim inconsistencies the panel should resolve

1. **B vs C.** B attributes half of its winning 2-feature block to α/Vm; C says polarisability adds nothing. My
   numbers side with C (α/Vm alone R² 0.015, ρ = −0.06; adding it worsens MAE). B should be restated as a
   one-feature μ²/Vm result.
2. **D vs H.** H claims 12 families of coverage; D's family table contains a mislabelled nitro/nitrate "amine" family
   and four families with < 10 members. The family stratification should be recomputed before any per-family claim
   is made.
3. **E vs F.** The AD is offered as the explanation for why the model errs, but the molecules the AD rejects are
   disproportionately the high-ε ones the screening claim depends on; the two claims are in tension.
4. **Report vs its own data.** `B100_FINAL_REPORT.md` says "卤代烃是最低的介电家族（ε 多在 2–5）" and "ε 本身几乎不随
   分子结构变化"; the data say mean 5.98 with 22/67 below 5, two lower families, and in-family R² 0.51. The report text should be regenerated from the
   data, not carried over from an earlier draft.

## 11. Limitations of this audit

- My oracle-recalibration test (slope + intercept on the test family) is deliberately optimistic; it is a diagnostic
  of information content, not a deployable model. A nested recalibration would raise the halocarbon MAE above 1.23.
- The nested family-mean baseline uses the family labels, which a transfer model is not given; it is the right
  comparison for "does this family-level transfer beat knowing the family", but a model that cannot use family
  identity could be excused for losing to it. The force of the 2/8 result is that the *published* baseline is even
  weaker, and the report's "6/8" counts against that weaker baseline.
- The family-matched null conditions on the model's own family composition; it answers "is the model better than
  random *within* the families it picked", which is the relevant screening question, not "could it have picked a
  better family".
- Monte-Carlo p-values use 400 k draws (resolution ~3e-6) and are seeded; the k = 10 p agrees with the published
  200 k value to 3 × 10⁻⁵.
- I did not re-run xTB; all descriptor-side attacks assume `model_matrix_b100.csv` is a correct record of the
  computations (its SHA-256 matches the manifests).

## 12. Files

| File | Content |
|---|---|
| `b100_reviewer_4.csv` | 8-row verdict table (required deliverable) |
| `b100_reviewer_4_report.md` | this report |
| `_lib.py` (identical copy kept as `_r4_lib.py` to avoid collisions with sibling reviewers) | independent ridge / nested-LOO re-implementation |
| `attack_ABC.py`, `attack_D.py`, `attack_EF.py`, `attack_GH.py`, `attack_extra.py`, `attack_family.py`, `attack_labels.py` | attack scripts |
| `attack_ABC.json`, `attack_D.json`, `attack_EF.json`, `attack_GH.json`, `attack_extra.json`, `family_taxonomy.json`, `attack_labels.json` | machine-readable results |
| `build_csv.py` | CSV generator |
