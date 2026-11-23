# Reviewer 3 — Code, Statistics and Reproducibility

**Project:** electrolyte-solvent-dielectric-ml
**Work packages:** B04 (candidate pool) + B05 (E1, E4, E6)
**Reviewer:** 3 of 4 (independent)
**Scope:** code audit, independent statistical recomputation, leakage audit, permutation
null audit, noise-ladder audit, identical-fingerprint verification, byte-level
reproducibility.

---

## 0. Bottom line

| Item | Decision | Why |
|---|---|---|
| B04_candidate_pool | **HOLD** | Membership correct and reproducible; two audit checks are no-ops and one field is hardcoded |
| E1 | **FAIL** | Headline "descriptors are useless" is an artefact of a **missing intercept**; correct null would reverse the reading |
| E4 | **HOLD** | Fingerprint arithmetic and leakage discipline sound; the *causal story* built on those 4 rows is refuted by my own recomputation |
| E6 | **FAIL** | The "noise improves screening → model is harmful" claim reads one branch of a **concave** curve |
| ALL | **FAIL** | One missing-intercept bug is copy-pasted across E1/E4/E6; reports not byte-reproducible; scripts rewritten mid-review |

The single most important finding: **every reported metric in B05 was computed with a
ridge regression that has no intercept.** It cannot reach the label mean (ε̄ = 17.32),
so it predicts inside a band around 0 while the response spans 1.93–44. This one defect
manufactures the project's entire negative-result narrative. The project's own later
`E1b` experiment independently reached the same diagnosis
(`abs_bias_over_mae = 1.0`, `CALIBRATION_FAILURE_NOT_INFORMATION_FAILURE`), but
**E1, E4 and the model boundary report never mention it** (verified: zero occurrences of
`E1b`, `intercept`, `calibration`, `bias` or `de-bias` in those three artefacts).

---

## 1. Did my recomputation match? — **YES, exactly**

Recomputed from `predictions_loo.csv` with numpy (independent of the project's linear
algebra). Constant-baseline MAE = **10.806223** (mean ε = 17.315455).

| Model | MAE | RMSE | bias | R² | manifest match |
|---|---:|---:|---:|---:|---|
| X0_structure_only | 17.446507 | 20.931398 | −16.720897 | −1.820290 | ✅ all 5 |
| X0_plus_X1_electronic | 17.286655 | 18.853363 | −17.009452 | −1.288099 | ✅ all 5 |

All statistics agree to < 5 × 10⁻⁶. **The arithmetic is not the problem — the
specification is.** This distinction matters: a reviewer who only checks arithmetic
would pass this work package.

E6 also reproduces exactly: n = 22, k = 3, oracle 37.83, model 24.45, pool 17.3155,
regret 13.38, regret/headroom 0.6522, overlap 1/3, Spearman +0.7549,
P(random ≥ model) = 0.16 (my independent 2000-draw resample: 0.16; 20 000 draws: 0.154).

---

## 2. The fatal defect: no intercept in the ridge

`scripts/b05/run_e1_structure_vs_electronic.py:139–150`

```python
Ztr, means, sds = _standardise(Xtr)     # X centred
b = _ridge_fit(Ztr, ytr, lam)           # y NEVER centred
x = [(X[hold][j] - means[j]) / sds[j] for j in range(len(means))]
preds.append(sum(x[j] * b[j] for j in range(len(b))))   # no + ybar
```

Standardising the features removes the need for an intercept **only if y is centred
too**. Here y is passed raw, so the fit is forced through the origin in standardised
space. The diagnostic signature is unmistakable in the delivered numbers:

* `mean_pred` = **0.5946** (X0) and **0.3060** (X0+X1) against `mean_true` = **17.3155**
* MAE 17.4465 is within **0.8 %** of the trivial "always predict 0" baseline 17.3155
* `bias ≈ −MAE` for both models (−16.72 vs 17.45; −17.01 vs 17.29) — every error has
  the same sign

Restoring the intercept with **identical features and identical λ = 1.0**:

| Configuration | MAE | RMSE | bias | R² | beats const (10.8062) |
|---|---:|---:|---:|---:|---|
| X0, no intercept *(delivered)* | 17.4465 | 20.9314 | −16.7209 | −1.8203 | **false** |
| X0, **with intercept** | **10.2435** | 13.1371 | +0.5946 | −0.1110 | **true** |
| X0+X1, no intercept *(delivered)* | 17.2867 | 18.8534 | −17.0095 | −1.2881 | **false** |
| X0+X1, **with intercept** | **6.5044** | 8.4565 | +0.3060 | **+0.5397** | **true** |

So the report's central claim — *"both models are worse than the constant baseline;
the descriptors have learned nothing"* (`e1_report.md` §2) —
**inverts** once the intercept is present. Worse: it also reverses the *incremental
value* question. ΔMAE(X0 → X0+X1) without intercept is −0.16 (n.s.); with intercept it
is **−3.74 with R² going from −0.11 to +0.54**. The electronic descriptors may carry
real signal that the buggy model destroyed. The honest verdict is
**"inconclusive at n = 22"**, not "no signal".

λ was **never tuned on the test fold** (fixed at 1.0 at every call site), so this is a
**specification defect, not leakage**. `_standardise` is fitted on the **training fold
only** (lines 146–148) — verified at runtime: train-fold mean 7.619048 vs all-data
7.636364 for `heavy_atom_count`, so the scaler is genuinely fold-local. **No leakage
anywhere in E1.**

---

## 3. Permutation-null audit — the wrong null, and an unstable p-value

### 3a. Shuffling `y` is the wrong null for this question

The script shuffles `y` and refits (lines 252–261). The question being asked is
*"does this feature set explain variance?"* For that question the correct null
**permutes the features and keeps `y` fixed**. Shuffling `y` destroys the X–y
association, which is fine in principle — but combined with the missing intercept,
both the observation *and* every null replicate are pinned to E|y| ≈ 17.3, so the test
has almost no power to separate signal from noise. It is measuring jitter around the
trivial baseline, not explained variance.

Under a **feature-permutation** null (column-wise, y fixed):

| Feature set | observed R² | null R² median | p(R² ≥ obs) | p(MAE ≤ obs) |
|---|---:|---:|---:|---:|
| X0 | −1.8203 | −2.3628 | **0.048** | 0.078 |
| X0+X1 | −1.2881 | −2.9672 | **0.004** | **0.036** |

This is the **opposite reading** to the delivered report. With the correct null the
X0+X1 set is distinguishable from noise even in the broken no-intercept model; with
the intercept restored, X0+X1 achieves R² = +0.54.

### 3b. The reported p-values are not stable — they depend on loop order

`random.seed(SEED)` is called **once** (line 215) *before* the model loop, so the 500
shuffles for X0 consume the first 500 draws and X0+X1 gets draws 501–1000. Each model's
p-value therefore depends on which model is looped over first. Re-seeding per model:

| Seed | X0 p | X0+X1 p |
|---|---:|---:|
| 20261123 *(shared stream, delivered)* | 0.164 | **0.060** |
| 20261123 *(per-model reseed, order reversed)* | 0.164 | **0.042** |
| 1 / 42 / 7 / 2026 / 999 / 12345 | 0.132–0.166 | 0.034–0.060 |

X0+X1 straddles the 0.05 threshold the report quotes (`beats_null_at_0.05: false`).
A conclusion that flips across a stated significance boundary under a different RNG
call order is not a conclusion.

### 3c. No null for ΔMAE, though the report reasons about it

`e1_report.md` §4 compares |ΔMAE| = 0.159852 against the *marginal* null quantiles.
That is an invalid comparison — the marginal spread of each null says nothing about the
sampling distribution of their difference. I built the paired ΔMAE null (shuffle y,
compute MAE(X1) − MAE(X0) on the same shuffle):

```
observed ΔMAE = −0.159852 ; null median = +0.462171
null 5–95 %   = [−0.500641, +1.468522] ; p_two_sided = 0.824
```

ΔMAE = −0.16 is **indistinguishable from noise** (p = 0.82). The report's *conclusion*
here happens to be right, but by an invalid argument, and the report frames it as
"smaller than the null's internal scale" rather than "inside the ΔMAE null", which is
the actual reason.

### 3d. Dead code in the null loop

`r2s` is allocated (line 254), appended to (261) and sorted (263) — **never read**.
`y_all` (line 190) is computed and unused. `statistics` (line 44) is imported and
unused.

---

## 4. E6 noise ladder — seeded consistently, but the inference is backwards

### 4a. The RNG **is** consistent — the decrease is not a re-drawing artefact

`run_e6_screening_decisions.py:274` rebuilds `rr = random.Random(SEED)` **inside** the
σ loop, so every σ consumes the *same* uniform stream (common random numbers). I
reproduce the published ladder **exactly** (13.38, 13.38, 13.38, 12.8983, 10.933,
10.5613). So the sharp answer to "is the RNG seeded consistently across sigma levels?"
is **yes**, and the decrease is **not** an artefact of re-drawing noise.

### 4b. The real artefact is the sampled range

Regret is **concave** in σ with an interior minimum. Extending the ladder (20 000
trials per point):

| σ | 0 | 2 | 4 | **6** | 8 | 10 | 12 | 16 | 24 | 32 | ∞ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| regret | 13.38 | 12.87 | 10.96 | **10.23** | 10.35 | 10.89 | 11.53 | 12.78 | 14.66 | 15.85 | **20.51** |

The script samples σ ∈ {0, 0.5, 1, 2, 4, 8} — it **stops on the descending branch**.
As σ → ∞ the ranking degrades to uniform random and regret returns to
**20.5145** (oracle 37.83 − pool mean 17.3155). Therefore:

> The model at σ = 0 (regret **13.38**) is already **substantially better than random
> screening** (20.51). Adding noise first *helps* (returning the blown-up, negatively
> skewed predictions toward the mean) and then *hurts*. The "U" is the signature of a
> **badly calibrated predictor being shrunk toward the prior** — textbook regression to
> the mean — **not** evidence that "the model's ranking is anti-correlated with the
> screening target".

### 4c. The verdict label is unsupported by the script's own statistic

`h3_supported: "true"`, `verdict: "REGRET_DECOUPLED_AND_ANTI_CORRELATED"`
(`e6_manifest.json`). But the same manifest reports
`spearman_pred_vs_true: +0.7549` — a **positive** rank correlation. The model ranks
molecules *correctly*; it is biased **low** (bias −16.94). "Anti-correlated" is
contradicted by the script's own number, and `model_boundary_report.md` propagates it
into "prediction is *harmful* for screening", which then becomes a "supported
conclusion" in `b05_gate_status.json`.

### 4d. Further E6 defects

* **D13** — the ladder's MAE is computed against the **noisy** predictions
  (lines 281–282), not the un-noised model, so "MAE rises while regret falls" compares
  a corrupted predictor's error to a rank statistic of *the same corruption*. The
  honest comparison is bias-corrected MAE vs regret.
* **D14** — `regret_monotone_down` (line 302) is evaluated only over the sampled grid
  with a `≤ + 1e-9` tolerance; it can be `true` purely because the grid never crosses
  the minimum. It cannot detect its own counterexample (and is false on a finer grid).
* The `COUPLED` branch (line 337) is unreachable given the `if`/`elif` ordering.
* E6's `X_COLS` (11 features) silently omits `total_energy_hartree`, which E1's X1
  includes (12 features). Undocumented feature-set divergence.

**Verdict:** the frozen-k rule and predefined baseline are genuinely respected, and
P(random ≥ model) = 0.16 correctly reports that the model is not *significantly* better
than random at n = 22. But the H3 conclusion — the report's headline in this section —
is an artefact of truncating a concave curve. **FAIL.**

---

## 5. E4 identical-fingerprint claim — arithmetic verifies, interpretation does not

### 5a. Independent RDKit verification: **confirmed**

I recomputed Morgan fingerprints (radius 2, 2048 bits) for all 22 molecules and all
231 pairs. Exactly **2 pairs** reach Tanimoto = 1.0, touching **4 molecules**:

| Pair | Tanimoto | y_true | Δy | heavy atoms | molecular_volume_A3 |
|---|---:|---:|---:|---|---|
| octanedinitrile / heptanedinitrile | 1.000000 | 25.94 / 29.71 | 3.77 | 10 / 9 | 147.784 / 131.408 |
| nonane / heptane | 1.000000 | 1.98 / 1.93 | 0.05 | 9 / 7 | 162.048 / 128.656 |

This matches the delivered `structural_distance_ood.csv` rows EPSV04-R008/R012/R034/R045
(`nn_tanimoto = 1.0`) and the manifest's `n_pairs_with_identical_fingerprint: 4`.
Published `abs_error` values reproduce exactly: 22.5762, 16.6064, 16.8593, 21.8746.

### 5b. Leakage check on `abs_error`: **PASSES**

`run_e4_domain_generalization.py:313–318` builds `tr = [j for j in range(n) if j != i]`
and calls `fit_predict` on that training set to predict `mols[i]`. **No molecule is ever
in its own training set.** Leave-one-family-out is equally clean: `hold = set(idx)` is
the whole family, and `n_train + test_n = 22` holds on every measured row (verified).

### 5c. But the causal claim is refuted twice

The report asserts (`e4_report.md` §7, propagated into `model_boundary_report.md` as
*"本轮最重要的结论"* — the most important conclusion of this round):

> "指纹完全相同处的误差…不是域外外推失败，而是描述符本身无法分辨化学上不同的液体。
> 这类误差不能靠增加同类数据解决。"
> *(the error at Tanimoto = 1.0 is descriptor blindness, not extrapolation failure;
> it cannot be fixed with more data of the same kind)*

Two independent refutations:

1. **The error is the missing-intercept blow-up, not blindness.** Re-running the same
   4 rows with an intercept: MAE falls from **19.48 → 2.79**, max error **22.58 → 5.15**
   (heptanedinitrile 21.87 → 5.15; nonane 22.58 → 4.53; heptane 16.86 → 1.19;
   octanedinitrile 16.61 → **0.30**). So the error *is* largely fixable — and was fixed
   by a one-line estimator change.
2. **The premiss is false.** The claim requires the descriptors to be indistinguishable.
   They are not: only the *2048-bit fingerprint* collides. `molecular_volume_A3` is
   147.784 vs 131.408 (dinitriles) and 162.048 vs 128.656 (alkanes); `heavy_atom_count`
   is 10 vs 9 and 9 vs 7. I verified `feature_vector_identical = False` for both pairs.
   The descriptors *can* distinguish these molecules — the fingerprint cannot.

The project's own `e1b_manifest.json` already records
`"E4_identical_fingerprint": "NEEDS_RESTATEMENT: 那些误差主要由外推爆炸驱动, 不是描述符无法区分相似分子"`.
**E4 was never restated.** Hold, not fail, because the fingerprint computation, the
`abs_error` arithmetic and the leakage discipline are all correct — the defect is the
conclusion drawn from them.

### 5d. Additional E4 defects

* **D9** — the `unclassified` family (4 of 22 molecules, including sulfolane — a
  sulfone with no SMARTS rule in `FAMILY_RULES`, lines 68–82) is a *rule gap*, not a
  chemical result. Also 13 of 22 molecules match several rules (dimethyl carbonate
  matches `carbonate`, `ester` **and** `ether`), so the "most specific wins" comment is
  misleading — the ordering is arbitrary, and family-error differences (12.8–21.3) that
  the boundary report calls "H1 partially supported" partly measure rule assignment.
* **D10** — the Spearman block (lines 363–381) recomputes on 4-dp-rounded values from
  `dist_rows` rather than raw errors; `statistics` (line 52) is imported and unused;
  `y_all` (line 245) is unused.

---

## 6. B04 candidate pool

Membership **verifies**: accepted = 22 (22 distinct IDs), model_ready = 73, intersection
= 22, `accepted & ready & ¬excluded` = 22, pool = 22 rows / 22 InChIKeys. Exclusion
audit is complete (73 − 22 + 175 = **226** rows, no duplicate IDs, no missing
ready-but-not-accepted rows). No label circularity: `dielectric` is carried through but
never used as a selection filter.

**Defect D1 — gate 3 is a no-op and the report mislabels it.** `ready ∩ excluded = 0`,
so gate 3 removes zero rows. The pool is really a **two**-gate intersection, and the
claim of "three independent gates" (the manifest's `declaration` and the review's §2)
overstates it. Compounding this, `build_candidate_pool_v2.py:319` prints the gate-3
row's "通过数" as `{len(ready)}` = 73 — the **gate-2 count under a gate-3 label** — a
number that cannot fail because it is not measuring the exclusion set at all.

**Defect D2 — the temperature-band test cannot fail.** All 22 pool values
(293.15, 298, 298.15, 298.2, 300.15, 303.15) lie inside [293.15, 303.15], so
`n_pool_rows_outside = 0` **by construction**. The rule "B04 要求 293.15 与 303.15 边界
闭区间必须测试" is satisfied vacuously: no boundary case exists in the pool to test.

**Defect D3 — hardcoded provenance field.** `b02_four_of_four` is written as the literal
string `"true"` (line 102) rather than derived from `n_pass`/`consensus_status`. It
happens to be correct today (`n_pass = 4` for all 22) but it is a constant assertion,
not a computed check, so it would silently survive a regression.

HOLD: pool membership and lineage are correct and reproducible; the defects are all in
the *supporting audit claims*, which overstate the rigour of the construction.

---

## 7. Reproducibility — numbers deterministic, files not

I ran the full B04 + B05 chain **twice** from identical inputs (all scripts exit 0).

* **All 14 numeric CSV outputs are byte-identical** across runs —
  `candidate_pool_v2_draft.csv`, `candidate_exclusion_audit.csv`,
  `temperature_vocabulary_mapping.json`, `feature_registry_v2.csv`, `metrics.csv`,
  `permutation_null.csv`, `predictions_loo.csv`, `leave_one_family_out.csv`,
  `structural_distance_ood.csv`, `source_ood_results.csv`, `applicability_domain.csv`,
  `topk_regret.csv`, `screening_reliability.csv`, `rank_vs_error.csv`.
  The statistics are fully deterministic (all RNG seeded). ✅
* **11 files differ**, and every difference is confined to `generated_at_utc`
  timestamps and the SHA-256 fields derived from timestamped files. Diffing with
  timestamp lines filtered out leaves **zero** residual differences.

So the pipeline is deterministic in substance but **not byte-reproducible as a file
set**. This matters for the manifests: `e1_manifest.json`, `e4_manifest.json`,
`e6_manifest.json` and `b05_gate_status.json` each embed a SHA-256 over a report that
contains its own generation timestamp, so **the hash chain cannot be used as a
content-addressed integrity check** — re-running a clean pipeline always changes those
hashes. A manifest that can never re-verify is not an integrity guarantee.

**Provenance drift during review (S3).** While this review was running, all five B05
scripts were rewritten in place and `outputs/b05` regenerated:

| Script | lines (audited → now) | change |
|---|---|---|
| `run_e1_structure_vs_electronic.py` | 462 → 499 | added intercept |
| `run_e4_domain_generalization.py` | 702 → 714 | added intercept |
| `run_e6_screening_decisions.py` | 503 → 544 | added intercept |
| `build_model_boundary_report.py` | 279 → 314 | — |
| `build_candidate_pool_v2.py` | 363 → 415 | — |

Consequence: delivered E1 metrics changed from MAE 17.4465 / 17.2867 with
`beats_constant_baseline = false` to **10.2435 / 6.5044 with `true`**, and E4's
identical-fingerprint MAE fell from 19.48 to 2.79 — *exactly the corrections my
independent recomputation predicted*. No script carries a version bump or changelog
distinguishing the two states, and `E1b` (the experiment that triggered the rewrite) is
still **not wired into the gate**. My audited snapshot is frozen at
`outputs/b04_b05_review/as_delivered/`.

---

## 8. Other systemic defects

* **S4 — feature-registry traceability is broken.** `feature_registry_v2.csv` registers
  **11** features and is certified as the traceability spine, but E1 actually fits
  **12** (it adds `total_energy_hartree`, which is *not* in the registry) while E4/E6
  fit **11**. The same nominal "X1 electronic" tier therefore means different things in
  different experiments, and the registry cannot reproduce E1's `n_features = 12`.
* **S5 — exact collinearity.** `polarizability_au` and `polarizability_A3` are an exact
  scalar multiple (ratio 0.1481847374–0.1481847517; Pearson **r = 0.9999999999999951**).
  X1 carries one redundant column, inflating p and destabilising the ridge at n = 22.
* **S6 — the "no drift" guarantee is false where it matters.**
  `build_model_boundary_report.py:56` claims the report is "mechanically generated from
  the manifests, so it cannot drift from the numbers", yet it **hardcodes** the
  sentences carrying the scientific conclusion: the family MAE range "12.8–21.3"
  (line 205), "MAE only drops 0.16" (line 207), and the H2/H3 verdicts. None are
  derived from manifest values, so exactly the claims that must not drift are the ones
  that can.
* **S7 — a check that can never fail.** `build_model_boundary_report.py:234` sets
  `required_deliverables["model_boundary_report.md"] = True` as a literal instead of
  testing the path.
* **S1 — the shared bug.** The identical no-intercept ridge is copy-pasted into E1,
  E4, E6 and E1b. Three experiment reports build a "no information" narrative on one
  coding error. `b05_gate_status.json` reports `gate_open: true` throughout.
* No silent `try/except` swallowing: all five scripts contain at most one `try` block
  (the `float()` parse in `fnum`), which correctly returns `None` on failure. The 9
  `.get(key, default)` calls in B04 are for optional provenance columns, not failed
  joins — I verified every required join resolves (`accepted & ready = 22`, no pool
  InChIKey missing from the feature table).

---

## 9. What each experiment can actually support

| Claim in the delivered report | My verdict |
|---|---|
| "Both models are worse than the constant baseline" | **False** — artefact of no intercept; with intercept both beat it |
| "Electronic descriptors add no incremental value (ΔMAE −0.16)" | **Unsupported** — the ΔMAE null gives p = 0.82, and with the intercept ΔMAE is −3.74 with R² 0.54 |
| "Neither feature set beats the label-shuffle null (p > 0.05)" | **Unstable** — p straddles 0.05 by RNG order; under the *correct* feature null, X0+X1 gives p = 0.004 |
| "Identical fingerprint ⇒ descriptor blindness, unfixable" | **False** — error drops 19.48 → 2.79 with an intercept, and the feature vectors are not identical |
| "Tanimoto cannot serve as an applicability-domain criterion" | **Weakened** — holds in the broken model; must be retested with the intercept |
| "Model Top-k is indistinguishable from random (p = 0.16)" | **Supported** — but only as "not significantly better", not as "harmful" |
| "H3 supported and worse than expected (noise improves regret)" | **False** — regression to the mean on a concave curve; Spearman is +0.75, not anti-correlated |

---

## 10. Required fixes before B05 can pass

1. **Add an intercept** (centre `y` on the training-fold mean) in all four scripts;
   rerun E1/E4/E6. *(Already done mid-review — but see 2.)*
2. **Version and re-freeze.** Record the estimator change explicitly; the delivered and
   corrected states must not both be called "E1". Add an `estimator_version` field to
   each manifest, and wire `E1b` into `b05_gate_status.json` (currently orphaned).
3. **Replace the y-shuffle null with a feature-permutation null** for the
   "explains variance" question, and add a **paired ΔMAE null**.
4. **Per-model RNG** (`random.Random(SEED)` inside the model loop) so p-values do not
   depend on loop order; report the seed-sweep range.
5. **Extend the E6 noise ladder to σ ≥ 32** and report the σ → ∞ limit; delete the
   `ANTI_CORRELATED` verdict, which contradicts the reported Spearman of +0.75.
6. **Restate E4 §7** and remove the "most important conclusion" framing.
7. **Separate timestamps from the hash chain** so manifests can re-verify: hash only
   the data outputs, or put timestamps outside the hashed artefact.
8. **Fix B04**: drop the vacuous gate-3 and temperature-band claims (or make them
   non-vacuous), derive `b02_four_of_four` from `n_pass`, and correct the mislabelled
   gate-3 count at line 319.
9. **Register `total_energy_hartree`** or remove it; drop one of the two collinear
   polarizability columns.
10. **De-hardcode** the H1/H2/H3 sentences in the boundary report so the "cannot drift"
    claim is true, and fix the always-true deliverable check.

---

## Appendix — files and method

All work is confined to `outputs/b04_b05_review/`; **no existing file was modified**.
`outputs/b04` and `outputs/b05` were backed up before the reproducibility runs and
restored afterwards, verified byte-identical (`diff -rq` clean). The audited
(as-delivered) state is preserved at `outputs/b04_b05_review/as_delivered/`.

| File | Contents |
|---|---|
| `reviewer_3_decisions.csv` | The 4 required rows + `ALL` |
| `reviewer_3_report.md` | This report |
| `v3_verify_stats.py` → `v3_stats_recompute.json` | Independent MAE/RMSE/bias/R², intercept variants, λ sweep |
| `v3_audit_e1_null.py` → `v3_e1_null_audit.json` | y-shuffle vs feature-permutation null, ΔMAE null, RNG-order test |
| `v3_audit_e6.py` → `v3_e6_audit.json` | Regret/Spearman/p recompute, ladder replay, σ → ∞ limit |
| `v3_verify_e4.py` → `v3_e4_verify.json` | All-pairs Morgan Tanimoto, intercept refutation, family-rule audit |
| `v3_leakage_audit.py` → `v3_leakage_audit.json` | λ-tuning, scaler scope, E4 self-exclusion, B04 gate algebra |
| `v3_repro.sh`, `diff_run1_run2.txt`, `diff_orig_run1.txt` | Two-run reproducibility harness and diffs |

Environment: `.venv/Scripts/python.exe` (Python 3.12.14, rdkit 2026.03.6,
numpy 2.5.3, pandas 3.0.6). All linear algebra re-derivations were done with
`numpy.linalg.solve` as an independent cross-check against the project's hand-rolled
Gaussian elimination; the two agree to < 1e-9 on every configuration.
