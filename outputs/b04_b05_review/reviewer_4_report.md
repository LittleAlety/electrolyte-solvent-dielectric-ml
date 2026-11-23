# Reviewer 4 — Independent Adversarial Audit (Red Team)
**Project:** electrolyte-solvent-dielectric-ml · **Work packages:** B04 + B05 (with B07 cross-checks)
**Role:** one of four independent reviewers · mandate = try to break the reported conclusions
**Verdict summary:** 6 items · **0 PASS · 2 HOLD · 4 FAIL** · **0 of 6 claims survive**

All numbers below were produced by scripts in this directory against the shipped
artefacts; nothing in `outputs/b04`, `outputs/b05`, `outputs/b07` or `scripts/`
was modified. Reproduction fidelity is stated for every figure.

| Script | What it establishes |
|---|---|
| `r4_attack_01_mechanism.py` | reproduces E1/E4 bit-for-bit; locates the mechanism |
| `r4_attack_02_estimator.py` | λ × intercept grid, alternative learners, permutation nulls |
| `r4_attack_03_claimC.py` | claim C: fingerprint provenance, descriptor identity, error decomposition |
| `r4_attack_04_defg.py` | claims D, E, F, G + the pool |
| `r4_attack_05_nested.py` | nested CV (no test leakage), feature-block ablation, claim B |
| `r4_attack_06_final.py` | exact top-k enumeration, extended noise ladder, pool audit |
| `r4_write_decisions.py` | emits the decision CSV |

---

## 0. The single finding that reorganises everything else

**The ridge model has no intercept.** `ridge_fit` in
`scripts/b05/run_e1_structure_vs_electronic.py` (and the identical copies in
`run_e4_domain_generalization.py`, `run_e6_screening_decisions.py`,
`scripts/b07/run_b07_split_comparison.py`) solves

```
(Z'Z + λI) b = Z'y        on standardised Z, with NO intercept column
```

Every column of `Z` sums to zero on the training rows, therefore `Zb` has
training mean **exactly 0 for any `b`**. The estimator is *structurally
incapable* of representing the label mean.

Measured directly:

| quantity | value |
|---|---|
| mean in-sample fitted value (λ=0) | 9.6 × 10⁻⁹ |
| mean in-sample fitted value (λ=1) | 2.9 × 10⁻¹⁵ |
| mean label `ȳ` | **17.3155** |
| implied in-sample bias | **−17.3155** |
| `sklearn` Ridge(`fit_intercept=True`) mean fitted | 17.3155 (intercept 17.3155) |

Because **every label is positive** (ε ∈ [1.93, 44.0]), `mean|y| = mean(y) =
17.3155`. A predictor that emits ≈0 on strictly positive labels must score
≈`mean|y|`. That is not a coincidence, it is an identity:

| published MAE | value | \|MAE − mean\|y\|\| |
|---|---:|---:|
| E1 X0 | 17.4465 | 0.131 |
| E1 X0+X1 | 17.2867 | 0.029 |
| B07 LOMO | 17.2375 | 0.078 |
| B07 random-5-fold | 17.3192 | 0.004 |
| B07 LOFO | 17.2559 | 0.060 |

**All five independent published MAEs sit within 0.131 of `mean|y|`.** The
project's headline — "no descriptor system beats a constant baseline; MAE 17.4
vs 10.8" — is the arithmetic of a dropped intercept, not a measurement of
descriptor validity. The constant baseline is *better* precisely because it is
the only model in the comparison that is allowed to know the level.

Adding the training mean back (a one-line change, equivalent to
`fit_intercept=True`) revises every downstream number:

| model | published MAE | with intercept | vs constant 10.806 |
|---|---:|---:|---|
| E1 X0 (7 cols) | 17.4465 | **10.232** | beats |
| E1 X0+X1 (12 cols) | 17.2867 | **6.492** | beats |
| E4/B07 (11 cols) | 17.2375 | **6.788** | beats |

Nested CV — λ chosen **inside** each training fold, so the number is not
λ-tuned on the test molecule — gives 10.485 / 7.138 / 6.818. The finding does
not depend on any tuning choice.

> **Scope note, stated in the report's favour:** the correct fix is not
> "λ was too big". Across λ ∈ {0, 0.01, 0.1, 1, 10, 100} the intercept-free MAE
> moves only between 17.09 and 17.89, i.e. the −17.3 offset dominates any λ.
> So the mandate's hypothesis of over-regularisation is **rejected** as the
> cause; the cause is the missing intercept alone.

---

## 1. Claim C — *is it genuine descriptor blindness, or global-mean bias?*

> **Answer: global-mean bias. Claim C should be retracted, not reworded.**
> It fails on four independent grounds and the sign of the evidence reverses.

### 1.1 The premise is false at the modelling level

`Tanimoto = 1.000` comes from a **2048-bit Morgan radius-2 *presence*
fingerprint** (`GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)`). Presence
fingerprints are known to collide on homologous n-alkanes: with a fixed radius
2 the repeated `C–C–C` environments of a straight chain collapse onto the same
bits regardless of chain length. Verified across registrations:

| fingerprint | max NN similarity | molecules at 1.0 | pairs |
|---|---:|---:|---|
| Morgan-2 / 2048 (as used) | 1.0000 | 4 | nonane↔heptane, octane-dinitrile↔heptane-dinitrile |
| Morgan-3 / 2048 | 0.8667 | **0** | — |
| Morgan-4 / 2048 | 0.6842 | **0** | — |
| RDKit path / 2048 | 0.9286 | **0** | — |
| MACCS-166 | 1.0000 | 4 | same collisions |

Nonane is C₉H₂₀ with 9 heavy atoms; heptane is C₇H₁₆ with 7. They are not
"the same molecule" — the fingerprint simply does not encode chain length at
radius 2.

More importantly, **the fingerprint is not the model's input.** The model
consumes 11 continuous RDKit/xTB descriptors. For nonane vs heptane, **7 of the
11 differ by more than 1%**:

| descriptor | nonane | heptane | differs |
|---|---:|---:|---|
| heavy_atom_count | 9 | 7 | ✓ |
| molecular_volume_A3 | 162.048 | 128.656 | ✓ |
| molar_volume_m3_mol | 9.759e−5 | 7.748e−5 | ✓ |
| dipole_D | 0.040 | 0.053 | ✓ |
| polarizability_au | 110.17 | 86.83 | ✓ |
| polarizability_A3 | 16.325 | 12.867 | ✓ |
| homo_lumo_gap_ev | 12.908 | 13.117 | ✓ |

For the dinitrile pair, 6 of 11 differ. So "the descriptors cannot distinguish
them" does **not** follow from a bit-vector collision.

### 1.2 A genuinely blind model would be *forced* to emit equal predictions — this one exaggerates

If two rows shared a descriptor vector, the model must return one value `p`, and
the optimal error is `|yᵢ − yⱼ|/2`. Observed instead:

| pair | true ε | true gap | model predictions | predicted gap | irreducible error if blind |
|---|---:|---:|---|---:|---:|
| nonane / heptane | 1.98 / 1.93 | **0.050** | −20.596 / −14.929 | **5.667** | 0.025 |
| octane-DN / heptane-DN | 25.94 / 29.71 | 3.770 | 9.334 / 7.835 | 1.498 | 1.885 |

The model **exaggerates** the nonane/heptane difference by **113×**. A blind
model cannot exaggerate a difference it cannot see; a mis-levelled model can.
This single table is fatal to the "descriptor blindness" reading.

### 1.3 The 19.4791 is worse than using no descriptors at all

| molecule | y_true | published pred | published err | intercept-fixed pred | fixed err | **0-descriptor mean-predictor err** |
|---|---:|---:|---:|---:|---:|---:|
| nonane | 1.98 | −20.5962 | **22.5762** | −2.5505 | 4.5305 | 15.3355 |
| heptane | 1.93 | −14.9293 | **16.8593** | 3.1188 | 1.1888 | 15.3855 |
| octanedinitrile | 25.94 | 9.3336 | **16.6064** | 26.2383 | 0.2983 | 8.6245 |
| heptanedinitrile | 29.71 | 7.8354 | **21.8746** | 24.5606 | 5.1494 | 12.3945 |
| **MAE on the 4** | | | **19.4791** ✅ reproduces 19.4791 | | **2.7917** | **12.9350** |

* The published model is **1.506× worse** than a constant predictor that uses
  zero descriptors, and beats it on **0 of 4** molecules. Claiming this as
  evidence *about descriptors* when it is beaten by *no descriptors* is
  inverted reasoning.
* With the intercept restored, the same four molecules have MAE **2.792** vs
  12.935 for the mean predictor — better on **4/4**. Their error drops below
  the pool average (2.792 vs 7.676 for the other 18), and three of them become
  among the **best**-predicted molecules in the pool (octanedinitrile rank
  22/22 = lowest error, heptane 20/22, nonane 14/22). The published ranking had
  them as the *worst* group. **The sign of the evidence reverses.**
* A single scalar correction, fitted out-of-fold and carrying **no molecule
  information whatsoever**, removes **60.9%** of the reported 17.2375 LOO error
  (17.2375 → 6.7328). That bounds how much of the "decisive" evidence could
  possibly be descriptor content.

### 1.4 What remains, honestly

The defensible residual statement is weaker and differently signed: *at n=22 the
11 continuous descriptors do carry signal (dipole alone has Pearson r = 0.808
with ε), and the specific pairs cited as "blind" are in fact resolved by
volume, polarizability and heavy-atom count.* The report's sentence 「这是本轮
最重要的结论」 sits on a result whose direction was determined by a missing
intercept. **RETRACT.**

---

## 2. Claim A — "both E1 models are worse than a constant baseline"

**FALSE.** See §0. Under the published estimator the claim is arithmetically
true but meaningless (the model cannot reach the label level); with an
intercept it is false:

| model | MAE | vs constant 10.806 | p (5000 perms) |
|---|---:|---|---:|
| X0 (7 cols) | 10.232 | beats by 5.3% | 0.078 |
| X0+X1 (12 cols) | **6.492** | **beats by 39.9%** | **0.0004** |
| X1 only (5 cols) | 6.313 | beats by 41.6% | — |
| dipole only (1 col) | 6.447 | beats by 40.3% | 0.0004 |
| OLS, 12 cols | 7.140 | beats | — |
| RidgeCV (auto α) | 7.017 | beats | — |
| RandomForest-500 | 7.670 | beats | — |
| GBM | 8.078 | beats | — |
| kNN-3 | 7.020 | beats | — |

Every reasonable learner beats the constant baseline. The report's own
conclusion 「这不是调参问题」 is exactly the assertion falsified here — the
defect is not tuning, it is the estimator's inability to fit an intercept, and
one line of code reverses the answer. **RERUN_WITH_DIFFERENT_METHOD.**

## 3. Claim B — "electronic descriptors add no detectable value"

**FALSE**, and this is the claim the report most wants to be true (it underwrites
H2, "better electronic calculations do not necessarily help"). Reproduced
Δ = −0.1599 under the broken estimator. With the intercept:

| comparison | ΔMAE (X0+X1 − X0) | bootstrap 95% CI | X0+X1 better on |
|---|---:|---|---:|
| λ=1, intercept | **−3.740** | **[−7.32, −0.26]** | **15/22 molecules** |
| nested CV | −3.348 (10.485 → 7.138) | — | — |

98.3% of bootstrap replicates are negative. The permutation nulls tell the same
story: X0+X1 reaches p = 0.0004 while X0 alone only reaches p = 0.078. Electronic
descriptors are the *entire* signal here, which makes physical sense — ε is a
polar-response property and `dipole_D` alone correlates r = 0.808 with it.

> Mandate item 5 (claim G) is related: the "no value" result is **not** an
> artefact of an unlucky feature set. But note `total_energy_hartree`, one of the
> five X1 columns, is *not* independent electronic information: it correlates
> **−0.957** with `heavy_atom_count` and **0.007** with ε. It is a molecular-size
> proxy. That is a real weakness in the X1 block design — but it does not
> rescue the report's conclusion, since dropping it (the 11-column E4 set) still
> yields MAE 6.788.

## 4. Claim D — "Tanimoto distance cannot serve as an applicability-domain criterion"

**FAIL.** Two separate problems.

**(a) The reported ratio is an offset artefact.** The published 1.045 is
computed on predictions shifted by −16.94. With the intercept restored and the
same threshold (0.40) the ratio becomes **1.398** with 95% bootstrap CI
[0.61, 4.53] — still not significant, but the point estimate moved 33% and the
in/out MAE gap widened from 0.76 to 2.12 ε units. The error-vs-similarity
Spearman moves from **−0.049** (published, "no signal") to **−0.505**, 95% CI
[−0.789, −0.107], i.e. a *significant negative* correlation: error really does
grow as structural distance grows. That is the opposite of the report's
「误差与结构距离无关」.

**(b) The claim is threshold- and registration-dependent, and was never
tuned — but the direction is consistent once corrected:**

| threshold (Morgan-2) | n_in / n_out | MAE_in | MAE_out | ratio | 95% CI | P(ratio>1) |
|---|---:|---:|---:|---:|---|---:|
| 0.30 | 13/9 | 5.125 | 9.191 | 1.793 | [0.95, 4.09] | 0.963 |
| **0.35** | 12/10 | 4.295 | 9.780 | **2.277** | **[1.15, 5.17]** | **0.992** |
| 0.40 (published) | 7/15 | 5.340 | 7.464 | 1.398 | [0.61, 4.53] | 0.783 |
| 0.45–0.55 | 4/18 | 2.792 | 7.676 | 2.750 | [1.38, 11.57] | 0.999 |

At the *better-powered* 0.35 threshold the domain separation is **significant**
(CI excludes 1). So the honest statement is "the 0.40 threshold is under-powered
and badly placed", not "Tanimoto cannot serve as an AD criterion".

**(c) The AD group is circular.** The 7 "in-domain" molecules are defined by the
same presence fingerprint that collides on n-alkanes, so 4 of the 7 are exactly
the Tanimoto = 1.0 collision set. "In domain" therefore selects near-duplicate
bit vectors, not chemically safe cases — which is precisely why the published
`≥ 0.40` split behaves so erratically. **DOWNGRADE + RERUN.**

## 5. Claim E — "Top-k screening is indistinguishable from random" (p = 0.16)

**HOLD.** The mandate's two worries are both testable and both come back
negative — but a different defect is real.

**Is 2000 permutations enough?** Yes, and it is unnecessary: there are only
**C(22,3) = 1540** distinct Top-3 sets, so the exact sampling distribution can be
enumerated. Doing so:

| statistic | value |
|---|---:|
| subsets with mean ≥ 24.45 | **242 / 1540** |
| exact one-sided p | **0.15714** |
| published MC value (2000 draws) | 0.160 ✅ |
| smallest achievable p | 0.00065 (oracle) |
| granularity | 1/1540 = 0.00065 |

So p = 0.16 is **not** a floor artefact and **not** a Monte-Carlo artefact. The
test genuinely can detect a perfect ranker (oracle subset → p = 0.00065).

**So what is wrong?** The wording. `p = 0.157` is a *non-rejection*; the report
converts it into the *equivalence* claim "indistinguishable from random". Those
are different statements and only the first is licensed. The point estimate
contradicts the second:

| quantity | value | percentile of all 1540 random Top-3 sets |
|---|---:|---:|
| oracle Top-3 mean | 37.83 | 99.94th |
| noise-σ8 Top-3 mean | 27.27 | 91.82nd |
| **model Top-3 mean** | **24.45** | **84.29th** |
| random expectation | 17.32 | 51.5th |

The model is better than **84.3%** of all possible random picks. One-sided
p(random ≥ model) = 0.157; one-sided p(model ≥ random) = **0.843**. With no
pre-specified equivalence margin and n = 22, "indistinguishable" must be
downgraded to "**not demonstrated superior at this power**".

**Additional E6 findings.**
* The Top-3 set is *identical* under the published and intercept-fixed models
  (sulfolane, N-(2-hydroxypropyl)-2-hydroxy-1-propanamine,
  1,4,7,10,13-pentaoxacyclopentadecane). Adding a constant is monotone, so E6's
  arithmetic is immune to the intercept bug — which is why this item is HOLD and
  not FAIL.
* But k = 3 uses **13.6%** of the pool and one rank swap moves regret by up to
  **8.10 ε units** (promoting 1-methylimidazole, true ε 39.78, would cut regret
  by 8.10). The reported effect is smaller than the sensitivity of its own
  metric. `INSUFFICIENT_POWER` is the right label and should be the only
  conclusion retained.

## 6. Claim F — "adding noise reduces regret, so predictions are harmful"

**FAIL — retract.** Reproduced the ladder exactly (σ = 0/0.5/1/2/4/8 → MAE
17.2375/17.2427/17.2488/17.2853/17.4348/17.9308; regret
13.38/13.38/13.38/12.898/10.933/10.561).

**(a) Not a seed artefact.** 60/60 seeds show regret falling at σ = 8 (mean
Δ = −2.99, sd 0.25) and 60/60 show recovery at σ = 64 (mean Δ = +4.67). The dip
is real. The mandate's robustness worry does not land.

**(b) But the ladder was truncated exactly at the minimum.** Extended:

| σ | 0 | 2 | 4 | 6 | **8** | 12 | 16 | 32 | 64 | 128 | 256 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| regret | 13.38 | 12.84 | 10.95 | 10.31 | **10.29** | 11.52 | 12.83 | 15.74 | 18.02 | 19.28 | 19.80 |

Regret rises monotonically back toward the pure-random asymptote
(37.83 − 17.32 = **20.51**). The same shape appears with the intercept fixed
(dip to 11.04 at σ = 8, back to 19.45 at σ = 128), so **the truncation artefact
is independent of the intercept bug**. "Noise reduces regret" is false as a
monotone claim; the report sampled only the dip.

**(c) The inference drawn from it is self-contradictory.** The gate file lists
「加入噪声反而改善 regret, 说明预测对筛选有害」 as a **supported conclusion** and
the verdict is `REGRET_DECOUPLED_AND_ANTI_CORRELATED`. This contradicts E6 *in
the same report*: the model's Top-3 sits at the **84.3rd percentile** of random
draws and p(model ≥ random) = 0.843. A ranker that beats 84% of random picks is
not "harmful". What the dip actually demonstrates is that the ranking is
**over-confident near the top** — it places 1-methylimidazole (true ε 39.78,
true rank 2) at predicted rank 5 and heptanedinitrile (29.71, rank 3) at rank 6,
so moderate noise sometimes promotes them. That is a rank-calibration defect,
not anti-correlation. The defensible residual claim is "ranking is imperfect and
moderate noise happens to help", which does not support H3's "more severe"
reading.

## 7. Claim G — "three splits give the same MAE, so leakage is not the issue"

**FALSE as stated, for three reasons.**

**(a) The three schemes share the defect, so their agreement is not
informative.** Published: LOMO 17.2375 / random-5-fold 17.3192 / LOFO 17.2559
(spread 0.082). All three use the **same** no-intercept solver, so all three
carry the same −16.94 bias; the spread across schemes (0.082) is *smaller* than
the spread a pure-noise predictor produces in the same test (sd 0.115, ratio
0.71). Their agreement is dominated by the shared offset, not by shared
descriptor content. The inference "therefore the descriptors carry no signal"
is exactly backwards.

**(b) The claim does not survive the fix.** With an intercept restored:

| scheme | published | intercept-fixed |
|---|---:|---:|
| leave-one-molecule-out | 17.2375 | **6.780** |
| leave-one-family-out | 17.2559 | **6.315** |
| random 5-fold (mean of 200) | 17.3192 | **6.973** |
| constant baseline | 10.806 | 10.806 |

All three now beat the constant by ~36–42%. The report's stated conclusion
「因此不能宣称『用更严格的划分就能改善』—— 严格划分只会让数字更差」 is
falsified: the strictest scheme (LOFO) is the *best* one.

**(c) It is not the same model / same features as E1.** The mandate asks this
directly and the answer is **no**:

| experiment | columns | `total_energy_hartree` |
|---|---:|---|
| E1 X0 | 7 | excluded (structural only) |
| E1 X0+X1 | 12 | **included** |
| E4 / E6 / B07 | 11 | **dropped** |

So B07's "three splits agree" is a **third** feature set, neither of E1's two
models — while the B07 report cites agreement with E1 as corroboration. The
E1-consistent comparison across splits is not what was run.

## 8. Attacking the B04 pool

**22 distinct InChIKeys, no molecule-level duplicates, gates reproducible by
hash — that part holds.** But "22" carries far less independence than it
implies:

| issue | measurement |
|---|---|
| distinct DOIs | 16 |
| DOIs contributing exactly 1 molecule | 13 |
| **largest single source** | `10.1021/je600515j` → **5/22 = 22.7%** |
| rows pooling >1 contributing measurement | 7/22 |
| rows declaring `n_independent_experiments` | all = 1 |
| temperature set-points / span | 6 values over 10 K (293.15–303.15) |
| molecules measured at >1 T | **0** (T effect cannot be validated) |
| Spearman(ε, T) across the pool | +0.076 |
| pool as share of the 73-molecule model-ready universe | **30.1%** |
| pool ε mean / sd vs model-ready | 17.32 / 12.76 vs 23.49 / 26.11 |

Consequences:

1. **Source clustering is an unmeasured confound, not a caveat.** The one family
   that still fails under the fixed model — `primary_secondary_amine` — is
   **4 molecules, all 4 from `10.1021/je600515j`**. So both its failure and any
   success would be source-confounded. B07 correctly blocks source-cluster
   claims (1 cluster with ≥3 members out of 16) but then lets E4 draw
   family-level conclusions the source structure cannot support.
2. **Range restriction is severe.** 22/73 = 30.1%, with the pool ε sd (12.76)
   half the model-ready sd (26.11). Any conclusion is conditional on the AI-
   consensus gate, not on the chemistry.
3. **The 22 is not 22 independent observations** for the purposes of a
   permutation null: 22.7% of the pool is one paper, and 7 rows already
   aggregate multiple measurements. Label-permutation nulls assume exchangeability
   that the source structure violates.
4. **"22" is not a meaningful pool size for E6.** k = 3 uses 13.6% of it, and the
   metric moves by up to 8.10 ε units on a single rank swap — larger than the
   13.38 regret being reported.
5. **Temperature is label noise, not a covariate.** Six set-points over 10 K with
   no per-molecule replication. ε is strongly T-dependent for polar liquids, so
   this injects error of unquantified magnitude into the target while the model
   is asked to explain a 1.93–44.0 spread. B04 is right to refuse the word
   "training set"; the stronger correct statement is "not 22 independent samples".

---

## 9. Decisions

| item | decision | grade | claim survives | action |
|---|---|---|---|---|
| `B04_candidate_pool` | **HOLD** | DOCUMENTED | false | DOWNGRADE_CLAIM |
| `E1` | **FAIL** | DOCUMENTED | false | RERUN_WITH_DIFFERENT_METHOD |
| `E4` | **FAIL** | DOCUMENTED | false | RERUN_WITH_DIFFERENT_METHOD |
| `E6` | **HOLD** | DOCUMENTED | false | DOWNGRADE_CLAIM |
| `claim_C_identical_fingerprint` | **FAIL** | DOCUMENTED | false | RETRACT_CLAIM |
| `claim_F_noise_ladder` | **FAIL** | INFERRED | false | RETRACT_CLAIM |

### Claims that should be downgraded (not per se wrong)

- "E1/E4 are EXPLORATORY" — correct and should be **strengthened**: they are
  exploratory *and* computed with a defective estimator.
- "Source-cluster robustness is not claimable" — correct, and the reason should
  be extended to family-level statements (see §8.1).
- "E6 is INSUFFICIENT_POWER" — correct, and should be the *only* E6 conclusion
  retained.

### Claims that should be retracted outright

1. **Claim C** (§1) — the report's flagship 「最重要的结论」. Direction reverses.
2. **Claim F** (§6) — "predictions are harmful for screening". Contradicts E6's
   own percentile and relies on a ladder truncated at its minimum.
3. **Claim G** (§7) — "leakage is not the issue". Shared defect, not shared
   signal; reversed by the fix; and not the same features as E1.
4. **Claim A** (§2) — "both models worse than a constant baseline".
5. **Claim B** (§3) — "electronic descriptors add no detectable value".
6. **Claim D** (§4) — "Tanimoto cannot serve as an AD criterion".
7. **H3's "more severe than expected" reading** (§6c) — no basis.

### Net effect on the programme

The report's *direction* ("single-molecule descriptors hit an evidence
boundary; n=22 cannot support confirmatory claims") is defensible and survives
on sample-size grounds alone. But its *evidentiary path* does not: the
headline negative result is an implementation defect, and the strongest
substantive finding in the whole package — that electronic descriptors provide a
large, permutation-significant, bootstrap-robust improvement (ΔMAE −3.74,
p = 0.0004) — is currently reported as its opposite. The report must be
re-derived, not merely annotated.

---

## 10. Reproducibility

```
E:\Claude Code\电解质ML\电解质ML\.venv\Scripts\python.exe \
  outputs\b04_b05_review\r4_attack_01_mechanism.py
... 02_estimator.py ... 03_claimC.py ... 04_defg.py ... 05_nested.py ... 06_final.py
E:\...\.venv\Scripts\python.exe outputs\b04_b05_review\r4_write_decisions.py
```

Fidelity of reproduction against published artefacts:

| quantity | reproduced | published | \|Δ\| |
|---|---:|---:|---:|
| E1 X0 MAE | 17.446507 | 17.446507 | <1e-6 |
| E1 X0+X1 MAE | 17.286655 | 17.286655 | <1e-6 |
| E1 X0+X1 bias | −17.009452 | −17.009452 | <1e-6 |
| E4 LOO MAE | 17.237530 | 17.2375 | 3.0e-5 |
| E4 bias | −16.938456 | −16.9385 | 4.4e-5 |
| claim-C 4-molecule MAE | 19.479125 | 19.4791 | 2.5e-5 |
| E6 top-k p (MC 2000) | 0.160 | 0.16 | 0 |
| noise ladder σ=8 regret | 10.561 | 10.561 | <1e-3 |

Intermediate JSON: `r4_attack_01_mechanism.json`, `r4_attack_02_estimator.json`,
`r4_attack_03_claimC.json`, `r4_attack_04_defg.json`, `r4_attack_05_nested.json`,
`r4_attack_06_final.json`.
