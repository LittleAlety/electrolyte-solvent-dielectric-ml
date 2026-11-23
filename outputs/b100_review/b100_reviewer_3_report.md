# B100 review — Reviewer 3: code, statistics and reproducibility

Project: `electrolyte-solvent-dielectric-ml`, PLAN B v6.0.
Scope of this review: `scripts/b100/` (17 scripts, 7,565 lines incl. the B100 tests),
`outputs/b100/`, `tests/test_b100_*.py`. No existing file was modified; every artifact
below was produced under `outputs/b100_review/`.

Verdicts (`b100_reviewer_3.csv`):

| item | decision | evidence | recompute matched | code defect | leakage |
|---|---|---|---|---|---|
| `dataset_257` | **FAIL** | DOCUMENTED | true | true | false |
| `E1_blocks` | **PASS** | DOCUMENTED | true | true | false |
| `E4_LOFO` | **HOLD** | DOCUMENTED | true | true | false |
| `E6_screening` | **PASS** | DOCUMENTED | true | true | false |
| `H4` | **HOLD** | DOCUMENTED | true | true | false |
| `conformer_analysis` | **HOLD** | INFERRED | true | true | false |
| `ALL` (systemic) | **FAIL** | DOCUMENTED | true | true | false |

The single most important finding: **110 of the 257 "phase-verified liquid" molecules
were admitted on a melting point that the fetch script fabricated by reading the first
digits of the compound's own name** (`mp_C` = 1.0 °C for 85 of them). 100 of those 110
sit in the 221-molecule evaluation set. Every E1/E4/E6 number is computed on a sample in
which 45 % of the rows have no verified phase state.

---

## 1. How the recomputation was done

Everything was re-derived from the deliverables and, where possible, from the raw xTB
outputs — not by re-running the project's code:

| script | what it does |
|---|---|
| `outputs/b100_review/_r3_recompute_e1.py` | independent numpy ridge (closed form) with the identical nested protocol: outer LOO, inner 5-fold λ selection on the training fold, standardisation on the training fold, unpenalised intercept; identical fold seeds (`random.Random(20261123)`); plus 2,000-permutation nulls for three blocks |
| `outputs/b100_review/_r3_stats_recompute.py` | E6 exact probability by integer-knapsack enumeration of all C(221,10) subsets + independent 200 k Monte-Carlo; E4 LOFO for 4 families; H4 group table plus a real skill metric; conformer ensemble re-parsed from `data/interim/xtb_conformers_b100/*/conf*/xtb.out` |
| `outputs/b100_review/_r3_conformer_sensitivity.py` | Boltzmann-vs-unweighted comparison, threshold sensitivity of the "unreliable" split, non-polar inspection |
| `outputs/b100_review/_r3_sample_bias.py` | E1 protocol re-run on the largest set each block supports (257 for X0) to test whether the 221 set biases the conclusion |

Total compute ≈ 30 s. Full E1 (`run_b100_experiments.py`) was not re-run, so no existing
file was touched.

### 1.1 E1 reproduction — exact, all six blocks

| block | k | reported MAE | **my MAE** | reported R² | **my R²** | reported λ_med | **my λ_med** | reported cv_mae | **my cv_mae** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| X0_structure | 15 | 4.3992 | **4.3992** | 0.0958 | **0.0958** | 10.0 | **10.0** | 4.3557 | **4.3557** |
| X1_electronic | 3 | 4.3265 | **4.3265** | 0.1908 | **0.1908** | 100.0 | **100.0** | 4.3042 | **4.3042** |
| X0_plus_X1 | 18 | 3.6885 | **3.6885** | 0.2803 | **0.2803** | 100.0 | **100.0** | 3.6761 | **3.6761** |
| dipole_only | 1 | 4.3470 | **4.3470** | 0.1137 | **0.1137** | 0.01 | **0.01** | 4.3513 | **4.3513** |
| Xn_volume_normalised | 2 | 4.1030 | **4.1030** | 0.2961 | **0.2961** | 100.0 | **100.0** | 4.1241 | **4.1241** |
| X0_X1_Xn | 20 | 3.2999 | **3.2999** | 0.4770 | **0.4770** | 100.0 | **100.0** | 3.3513 | **3.3513** |

RMSE and bias also match to 4 dp (e.g. X0 RMSE 9.3954, bias −0.1857). `n_common = 221`
and the constant baseline 5.0932 reproduce from the CSV. **The E1 numbers are correct.**

### 1.2 E4 reproduction — exact for 4 of 8 families

| family | n_train | n_test | reported MAE | **my MAE** | reported base | **my base** |
|---|---:|---:|---:|---:|---:|---:|
| halocarbon | 154 | 67 | 6.7778 | **6.7778** | 2.5306 | **2.5306** |
| ester | 200 | 21 | 3.8421 | **3.8421** | 3.2169 | **3.2169** |
| ether | 202 | 19 | 3.3734 | **3.3734** | 3.5497 | **3.5497** |
| ketone_aldehyde | 211 | 10 | 2.9647 | **2.9647** | 7.2045 | **7.2045** |

### 1.3 E6 reproduction — exact by enumeration

* model top-10 mean **20.9661**, oracle **39.0900**, pool mean **7.6095**, regret
  **18.1239** — all reproduce; my nested-LOO predictions agree with
  `e6_ranking_b100.csv`'s `y_pred` to **4.9 × 10⁻⁵** (CSV rounding).
* **Exact** P(mean of a random 10-subset ≥ 20.9661) = **221 261 548 929 500 /
  62 292 206 224 983 306 = 0.003552**, obtained by enumerating the coefficient
  polynomial of ∏(1 + z·x^sᵢ) over all C(221,10) = 6.2292 × 10¹⁶ subsets (the DP total
  equals `math.comb(221,10)` exactly, which validates the counter).
* Independent Monte-Carlo, different generator, 200 000 draws without replacement:
  **0.003680 ± 0.000135**.
* Reported **0.003575** (715/200 000) is **0.17 σ** from the exact value. **The E6
  p-value is correct.** 200 000 draws give a resolution of 5 × 10⁻⁶, as the manifest
  claims.

### 1.4 H4 and conformers

H4 group table reproduces exactly (WEAK n=159 MAE 2.5022 / baseline 1.8199;
INTERMEDIATE 47 / 3.0157 / 4.6647; STRONG 15 / 18.3716 / 12.1596). Conformer
`boltzmann_dipole` reproduces for **39/39** molecules from the cached `xtb.out` files
(max difference < 0.005 D).

---

## 2. Data leakage — direct answers

* **Is λ ever tuned on the test fold?** No. `choose_lambda`
  (`run_b100_experiments.py:168-194`) only ever sees rows passed as `Xtr`, and
  `nested_loo` (`:219-228`) passes exactly the 220 training rows. Numeric proof: my
  independent implementation, which cannot see the held-out row, reproduces every MAE
  and every per-fold λ. In E4, LOFO removes the *entire* family from training
  (`:457-459`) before λ is chosen (`:464`).
* **Is the scaler fitted on train only?** Yes. `fit_predict` (`:143-154`) computes
  means/sds from `Xtr` only (`standardise(Xtr)` at `:147`) and applies them to `Xte` at
  `:152`. Again proved by exact reproduction with a train-only implementation.
* **Does E6's Top-k use the same predictions as the LOO estimates?** Yes — and that is
  legitimate: `preds_all = nested_loo(Xall, yall)` (`:500`) are out-of-fold, then
  `order_pred` (`:551`) ranks them. My recomputation matches those predictions to
  4.9 × 10⁻⁵. No in-sample selection.
* **H4 is conditioned on the outcome.** `association_class` is built from `epsilon`
  itself (`build_b100_model_matrix.py:238-243`), so the two strata are truncations of
  the target. This is not train/test leakage but selection on *y*: it shrinks
  within-group variance by construction and mechanically favours the low band in any
  relative-error comparison.
* **The conformer classification uses the outcome to set its denominator.** Molecules
  are removed from the reliability fraction when `|<μ>| < 0.30 D` **and**
  `|μ_single| < 0.30 D` (`run_b100_conformers.py:303-307`) — the classification is made
  from the same quantities being judged.
* One minor, non-material item: the λ used for the p-value is
  `statistics.median(lams)` (`:355`) over the 221 outer folds, so the p-value's λ has
  seen every molecule. It cannot move the headline MAE (λ is on a coarse grid and the
  median is 100 for most blocks) but it is technically one bit of information leakage
  into the null comparison.

---

## 3. Permutation-null audit

1. **Reporting `p = 0.0` is impossible and is the wrong claim.** `N_NULL = 200`
   (`:357`), the p is `count/N` with no +1 correction (`:364`, `:374`), so the smallest
   attainable non-zero value is 1/200 = **0.005**. All six blocks report
   `"p_label_permutation": 0.0` and `"p_feature_permutation": 0.0`. The correct
   statement is **p < 0.005** (or p < 1/201 with the correction) — not "p = 0".
   `tests/test_b100_experiments.py:94-95` only asserts `0.0 <= p <= 1.0`, so this
   passes CI.
2. **200 permutations is enough for the decision, not for the number.** I ran 2 000
   permutations for X0, Xn and X0+X1 (independent generator): the *minimum* null MAE is
   5.0044 (label) / 5.0262 (feature) for X0, 4.9455 / 4.9121 for Xn, 4.9777 / 4.9432
   for X0+X1, all far above the observed cv_mae (4.3557 / 4.1241 / 3.6761). So the
   evidence is strong: p < 0.0005. The defect is the reportable floor, not the
   conclusion.
3. **The two nulls are not independent evidence.** Permuting label rows and permuting
   feature rows, scored by the same 5-fold CV on the same fixed folds, are two views of
   one exchangeability null for the X–y pairing; both give identical p in every block.
   The module docstring (`:14-15`, "TWO NULLS … answer different questions") overstates
   what is being measured. A test that *would* answer a different question — e.g.
   permuting a block's features while keeping the other block intact — is not
   implemented.
4. **Undeclared, unused constant.** `N_PERM = 1000` (`:56`) is never used; the executed
   count (200) is a local variable (`:357`) that never reaches any manifest. A reader of
   `e1_manifest_b100.json` cannot learn the permutation count at all.
5. **Determinism is order-dependent.** The nulls consume the module-level
   `random.seed(SEED)` stream (`:300`, `:359-373`), so adding/removing a block changes
   the null draws of every later block. Reproducible only for a byte-identical execution
   path.

---

## 4. Conformer-analysis audit (`run_b100_conformers.py`)

**Boltzmann weighting: arithmetically correct, physically approximate.**
`boltzmann_weights` (`:201-208`) converts Hartree→eV, subtracts the minimum and
normalises — correct. My re-parse of the 40 cache directories reproduces every
`boltzmann_dipole` (39/39, max diff < 0.005 D). But the weights use *electronic* GFN2
total energies at 298.15 K with no Gibbs/entropy correction, on energy spans of
**0.044–0.268 eV** (median 0.103), i.e. only 1–6× the ~0.04 eV (1 kcal/mol) GFN2 error
bar. The median maximum weight is 0.509 against 0.167 for a uniform average, so the
weighting is doing real work, but "Boltzmann average" should be qualified as
"electronic-energy weighted".

**Is `single_conformer_dipole` really from a different geometry? Yes, for 13/39.**
It lies *outside* the ensemble's own `[dipole_min, dipole_max]` for 13 of 39 molecules;
7 are outside by more than 0.04 D:

| molecule | single | ensemble range | verdict |
|---|---:|---|---|
| Dibutyl sebacate | 4.842 | [0.381, 3.838] | UNRELIABLE |
| Tributylphosphate | 3.924 | [0.651, 3.568] | UNRELIABLE |
| Dibutyl phthalate | 3.977 | [0.699, 3.867] | UNRELIABLE |
| Nitroglycerin | 3.552 | [2.356, 3.061] | UNRELIABLE |
| 3-Bromo-4-ethoxyheptane | 4.084 | [4.224, 5.686] | UNRELIABLE |
| Amyl ether | 1.081 | [1.121, 1.549] | UNRELIABLE |
| 1-Bromooctadecane | 3.869 | [4.016, 4.300] | **RELIABLE** |

Root cause: the modelling table's "single" geometry is
`EmbedMolecule(randomSeed=42)` + MMFF + `xtb --opt`
(`build_b100_xtb_coverage.py:118-126`), and **221 of the 257 dipoles are inherited from
the earlier expansion run** (`:403-425`, `source=EXISTING_UNIFIED_RUN`) with a different
provenance, whereas the ensemble is ETKDGv3 multi-embed with RMSD pruning
(`run_b100_conformers.py:132-135`). So part of the "single vs Boltzmann" deviation is a
*pipeline* difference, not conformer sampling — and 4 molecules are simultaneously
"outside the ensemble range" and labelled `SINGLE_CONFORMER_RELIABLE`, which is
internally inconsistent.

**The 0.30 D polar floor is defensible but unjustified, and the headline is threshold-
dependent.** The three molecules it removes are n-decane (0.0071 D), n-dodecane
(0.022 D), n-undecane (0.021 D) — all alkanes, so 0.30 D does exactly what it should
(and would have done so at 0.10 D). The problem is that neither `POLAR_FLOOR_D = 0.30`
(`:302`) nor `tol = 0.10` (`:290`) is justified anywhere and no sensitivity is run. Re-
scoring the delivered records:

| tol | floor | n_polar | unreliable | reliable |
|---:|---:|---:|---:|---:|
| 0.10 | 0.30 (as shipped) | 36 | **30** | 6 |
| 0.20 | 0.30 | 36 | 23 | 13 |
| 0.30 | 0.30 | 36 | 21 | 15 |
| 0.50 | 0.30 | 36 | 10 | 26 |
| 0.10 | 0.00 | 39 | 33 | 6 |
| 0.10 | 1.00 | 35 | 29 | 6 |

The qualitative conclusion survives (median relative spread 0.3227, median
single-vs-Boltzmann deviation 0.0786 → a 10 % tolerance is if anything generous), but
**"30/36" is a threshold artefact and should be reported as a range (21–33 depending on
tolerance) with the tolerance stated as a convention.**

**Latent bugs (not triggered by this dataset, so no number is wrong today):**
* `:329-330` `boltzmann_gap` — `sum(w[j] * gaps[j] …) / sum(w[:len(gaps)])` indexes the
  *unfiltered* weight list with a *filtered* gap list. If any conformer lacked a dipole
  or a gap, weights and values would be silently mis-paired. All 39 molecules happened
  to have both for every conformer (verified), so the output is correct by luck.
* `:323-328` `round(x, 4) if x else ""` — a legitimate 0.0 becomes an empty cell
  (`boltzmann_dipole`, `dipole_spread`, `dipole_relative_spread`,
  `single_vs_boltzmann_rel_dev`). Not triggered (no spread is exactly 0).
* Only 6 conformers per molecule for up to 8 rotatable bonds: the ensemble is not a
  converged thermodynamic average, so the reported spreads are lower bounds and 30/36
  is an underestimate.

---

## 5. Reproducibility

* **Deliverables are NOT byte-stable.** 14 JSON files (13 under `outputs/b100/` plus
  `outputs/b100/deliverables/b100_freeze_manifest.json:330`) and
  `B100_FINAL_REPORT.md:413` embed `datetime.now(timezone.utc)`. Worse, the freeze
  manifest hashes `B100_FINAL_REPORT.md`, which itself contains a timestamp, so the
  manifest's own `deliverables` block changes on every run. A "freeze manifest" that
  cannot be reproduced cannot detect drift or tampering — its stated purpose
  (`test_freeze_manifest_hashes_every_deliverable`) is only satisfied in the trivial
  sense that the hashes are internally current.
* **The numeric content IS reproducible.** Byte-stable in practice:
  `e1/e4/e6/h4_manifest_b100.json` (no timestamp), every CSV, and the numeric content of
  the PNGs. My independent re-implementation reproduced E1 and E4 exactly, the E6
  p-value to 0.6 % relative (exact value within 0.17 σ of the 200 k MC estimate), and
  every conformer Boltzmann average. Seeds are fixed where it matters
  (`SEED = 20261123`); the RDKit embedding seed is 42.
* **`xtb_seconds` in the deliverable `xtb_descriptors_b100.csv` is wall-clock** and
  differs for the 17 newly computed rows if recomputed — a second, smaller source of
  non-stability.
* **The permutation/MC counts are not recorded**, so a re-run with different `N_NULL`
  would produce a different p without any artifact saying so.

---

## 6. Code defects (file:line)

### Blocking

1. **`fetch_pubchem_mp_b100.py:147-163` — fabricated melting points.** After the
   unit-tagged branches fail, the parser accepts *any* number in [-150, 400] from *any*
   free-text field. PUG-View/HSDB descriptions start with the compound name, so 110
   molecules got `mp_C` = 1.0 (85), 2.0 (18), 3.0 (6), −1.0 (1) °C and the note
   `ASSUMED_C: 1,2,3-tribromopropane is a bromohydrocarbon…`. A plausibility window is
   not a unit, and "first number in a sentence" is not a melting point.
2. **`audit_b100_phase_state.py:121-126, :157` — the assumption is laundered into
   evidence.** The fetched value takes precedence over the gate value,
   `phase_verified = (status == "LIQUID_AT_STATED_T")` and the 1–3 °C values always
   satisfy `mp < T − tol`; `mp_note` (the only field that says ASSUMED) is **not
   propagated** into `phase_state_audit_b100.csv` (columns list has `mp_source` only).
   The manifest's own note says "缺熔点数据的分子**不得默认当作液态**" — which is
   exactly what happens to these 110.
3. **`build_b100_molecule_registry.py:61` — nitro SMARTS can never match.** RDKit
   represents nitro as `[N+](=O)[O-]`, so `[NX3](=O)=O` fails for nitrobenzene,
   nitromethane, nitropropane, ethyl nitrate and nitroglycerin (all verified directly).
   Consequence: `nitro` family = 0, and the amine rule
   `[NX3;H2,H1,H0;!$(NC=O)]` captures the nitro nitrogen, so **16 nitro/nitrate
   molecules are counted as "amine"** and the family that "meets its target" is a
   chimera. `tests/test_b100_defects.py:62-77` reuses the same SMARTS, so CI cannot see
   it.

### Serious but non-blocking

4. **`run_b100_experiments.py:364, :374` — p-values of exactly 0.0** from 200
   permutations with no +1 correction. Also `:386-387` writes `round(p, 4)`, which
   further hides the floor.
5. **`run_b100_experiments.py:56` — `N_PERM = 1000` is dead code**; the real count
   (`:357 N_NULL = 200`) is never persisted.
6. **`run_b100_experiments.py:11-13, :428` — documentation contradicts the code**: both
   the module docstring and `e1["note"]` claim inner **leave-one-out** λ selection;
   `choose_lambda` runs inner **5-fold** (`:168-194`).
7. **`run_b100_experiments.py:317-325` — the common set is complete-case across all
   blocks**, so a single missing column (`polarizability_au`) removes 36 molecules whose
   mean ε is 16.68 vs 7.61 for the retained 221 (max 178.5 vs 114.9; only 15 of the 25
   molecules with ε ≥ 20 survive). Not disclosed
   anywhere. Mitigation measured: X0 on all 257 gives MAE 5.6502 vs baseline 6.9083
   (−18.2 %), so the qualitative E1 claim is robust; but the common set is 45 % the 257
   set's high-ε tail short.
8. **`run_b100_experiments.py:455-461 — 4 of 12 families silently dropped** by the size
   filters; the summary reports "8" without naming the 4.
9. **`run_b100_experiments.py:644-655` — H4 uses MAE/median_ε as "predictive skill".**
   Both groups are worse than their own constant baseline (skill −0.375 and −0.511), so
   `supports_h4 = true` is an artefact of the normaliser. `:659-664` already knows the
   power is insufficient yet the comparison is emitted.
10. **`run_b100_experiments.py:557, :573, :583-591` — E6 documentation errors**: the
    comment and the `method` string say n = 257 (it is 221), and the k = 15 sensitivity
    p is written as `0.0` from 20 000 draws when the floor is 5 × 10⁻⁵.
11. **`run_b100_experiments.py:122, :136-137` — dead singularity guards in `ridge_fit`.**
    With λ ≥ 0.01 and standardised columns the diagonal is never < 1e-12, so the
    `continue` branches are unreachable; a genuinely singular system would be silently
    skipped rather than raised.
12. **`run_b100_conformers.py:329-330` — weight/value misalignment in `boltzmann_gap`**
    (see §4).
13. **`run_b100_conformers.py:323-328` — falsy-zero bug** turns 0.0 into `""`.
14. **`run_b100_conformers.py:147, :175` and `build_b100_model_matrix.py:122, :135` —
    silent `except: pass`.** MMFF non-convergence and fingerprint/volume failures are
    dropped; the volume failure would silently empty an X0 column (it would then be
    caught by `build()` dropping rows, changing the sample without a message).
15. **`verify_b100_smiles.py:88-91, :101, :165, :190` and
    `fetch_pubchem_mp_b100.py:81-84` — network failure is indistinguishable from "no
    data"** (both return status 0 / `None`; 70 lookup rows carry an empty
    `http_status`). A transient outage silently shrinks the verified set instead of
    failing the run.
16. **`build_b100_deliverables.py:130` — `"phase_verified": "true"` is hard-coded** for
    all 257 registry rows instead of joined from the phase table. The value happens to be
    right (the matrix already filtered on it), but the deliverable is an assertion, not
    evidence.
17. **`build_b100_deliverables.py:419-422` — the hard-gate "达标" column is a literal
    `✅`.** It cannot show failure. The row is also labelled "独立合格分子" (independent
    qualified molecules) and counts 257, while `source_independence_b100.json` says only
    **18** molecules are independently corroborated.
18. **`build_b100_xtb_coverage.py:406` — `"protocol": PROTOCOL_ID` is stamped on 221
    rows that were inherited from an earlier run**, and `:499-503` justifies it with
    "identical command and same binary". The cache manifests do record the executable
    path and `xtb_version 6.7.1pre`, but **not the argument list**, so the claim is
    unverifiable from the artifacts.
19. **`build_b100_figures.py:162` — the panel title "epsilon bands (all three
    populated)" is hard-coded** and cannot be false.

### Test guards that cannot fail

20. `tests/test_b100_experiments.py:88-95` only asserts `0 ≤ p ≤ 1` — passes with
    `p = 0.0`. `:157-164` only asserts that the H4 comparison *has* the keys
    `weak_relative_mae`/`strong_relative_mae`, not that the metric means anything.
21. `tests/test_b100_defects.py:62-77` rebuilds the amine SMARTS from the
    implementation, so a rule that misclassifies nitro groups passes.
22. `tests/test_b100_deliverables.py:80-88` asserts `achieved_qualified >= 100` — it
    would catch a numeric shortfall but not the fabricated phase evidence behind the
    number.
23. No test anywhere reads `ASSUMED` / `mp_note` (`grep -r ASSUMED tests/` → nothing).

---

## 7. Claims that should be downgraded

| claim (where) | problem | defensible statement |
|---|---|---|
| "257 phase-verified liquid molecules" (freeze manifest `hard_gates.achieved_qualified`, report §0) | 110 of the 257 rest on a fabricated `mp_C` of 1–3 °C | 147 phase-verified; 110 unverified (must be downgraded to `UNKNOWN_NO_MP`). Gate ≥ 100 still met, margin 47 |
| "独立合格分子 … 257 ✅" (report §0) | "independent" counts molecules from one compendium; 18 are independently corroborated | "257 molecules, 18 independently corroborated; independence gate not met at 257" |
| "p_label_permutation = 0.0 / p_feature_permutation = 0.0" (e1 manifest, all blocks) | impossible value from 200 permutations, no +1 | "p < 0.005 (200 permutations)" or re-run and report "p < 0.0005" |
| "P(随机≥模型) … k=15 0.0" (e6 manifest, report §4) | floor is 5 × 10⁻⁵ with 20 000 draws | "p < 5 × 10⁻⁵" |
| "6/8 families beat baseline" (report §3) | counting successes is not a test; P(X ≥ 6 \| n=8, p=0.5) = 0.145 | "6 of 8 measurable families beat their train-mean baseline (sign test p = 0.145, not significant); 4 families unmeasurable" |
| "amine family: MAE 9.01 vs base 14.77, beats" (e4 manifest) | the family is 16 nitro/nitrate molecules mislabelled by a SMARTS that cannot match | "nitro/nitrate-rich group (n=17): MAE 9.01 vs 14.77" — and fix the SMARTS |
| "supports_h4 = true" (h4 manifest, report §5) | both groups are worse than a constant (skill −0.375, −0.511); strata are defined on the target; n_strong = 15 | "INSUFFICIENT_POWER; direction not evaluable" |
| "30/36 polar molecules unreliable" (report §5/§6, freeze manifest) | 21–33 depending on the tolerance; 13/39 single values are not even ensemble members | "21–33 of 36 depending on tolerance; at the code's own 10 % convention, 30/36; the single geometry is from a different embedding pipeline" |
| "统一 xTB 覆盖 257 ✅" (report §0) | 221/257 descriptors inherited; protocol asserted, argument list unrecorded | "257 rows carry GFN2-xTB values; 36 computed in this pass, 221 inherited from the unified expansion run (protocol identity asserted, not verified)" |
| "E1 finding 2: polarizability and the gap have no independent contribution" (report §2) | inferred from dipole-only MAE ≈ X1 MAE (4.347 vs 4.327); no per-feature test | "dipole alone matches the 3-feature electronic block (4.347 vs 4.327); no ablation was run" |

---

## 8. What I could not verify (limits of this review)

* I did not re-run `run_b100_experiments.py` (≈10 min) or the xTB pipeline; recomputation
  was done on the written predictions and the cached raw xTB outputs, which is why the
  match to 4 dp is strong evidence rather than a re-execution.
* Whether the 110 ASSUMED-melting-point molecules are *actually* liquid at the stated
  temperature is not knowable from the repository; it requires the original NBS/HSDB
  pages. Their ε labels may be fine — the *certification* is not.
* The `epsilon` values themselves (NBS 514 transcription) were out of my remit; I only
  checked that they reproduce and that their distribution is not truncated by the
  analysis set.
* I did not audit `build_b100_asset_inventory.py`, `build_b100_family_gap_candidates.py`
  or `audit_b100_identity.py` beyond a pattern scan for swallowed exceptions and dead
  `.get()` defaults (nothing new beyond items 14–15).

## 9. Artifacts produced

| file | content |
|---|---|
| `outputs/b100_review/b100_reviewer_3.csv` | required CSV, 7 rows |
| `outputs/b100_review/b100_reviewer_3_report.md` | this report |
| `outputs/b100_review/_r3_recompute_e1.py` / `_r3_e1_recompute.json` | E1 + permutation nulls |
| `outputs/b100_review/_r3_stats_recompute.py` / `_r3_stats_recompute.json` | E4 / E6 exact / H4 / conformers |
| `outputs/b100_review/_r3_conformer_sensitivity.py` / `_r3_conformer_sensitivity.json` | threshold sensitivity |
| `outputs/b100_review/_r3_sample_bias.py` / `_r3_sample_bias.json` | 221-vs-257 sample-bias test |
| `outputs/b100_review/_r3_write_csv.py` | CSV emitter |
