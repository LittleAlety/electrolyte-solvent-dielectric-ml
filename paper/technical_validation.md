# Technical Validation

## Cross-source verification

Every dataset value passes at least one independent cross-check:

**Chodera et al. (2015) cross-check.** The v0.1 extraction shares 45 keys with
the extraction of Chodera et al. (2015, arXiv:1506.00262) from the same NIST TRC
archive. The median absolute deviation between the two extractions is 0.175
(maximum 7.341), which is larger than parser noise. Temperature does not explain
it: 44 of the 45 key pairs sit within 0.05 K of each other. The difference is
therefore reported as an unresolved disagreement between two extractions of the
same archive, not as a fidelity check that passed. The 45 shared keys are also
why the Chodera overlap is sometimes quoted as "45 records"; v0.1 itself holds
100 compounds.

**SpringerMaterials restricted cross-check.** The restricted SpringerMaterials
Interactive database (Landolt-Bornstein series) was queried against the v0.2
table and matched 60 compounds. The median absolute delta between the public and
restricted values is 0.05 (p90 0.67, maximum 10.2, the last being the ethyl
isothiocyanate conflict). SpringerMaterials values are used exclusively as
cross-check evidence; no subscription-restricted value enters the public
dataset.

**NBS Circular 514 internal consistency.** All values sourced from NBS Circular
514 carry the original page number, entry figure quality, and selection rank.
For compounds with multiple NBS entries (different temperatures or purity
grades), the selection rank and figure quality determine the preferred record.

**Conflict exclusions (v0.3.3 conventions).** Nine rows carry a non-empty
conflict_status and six carry model_ready=false. Four of them are withheld from
model fitting through the curated exclusion list
(data/processed/dielectric_v03_exclusions.csv): FEC (reported values 78.4, 102,
107), TEP (10, 13), TMP (10, 21.6), and ethyl isothiocyanate, whose NBS value
(19.5 at 294.15 K) and restricted cross-check value (29.7 at 293.2 K) differ by
10.2. Methyl propionate (NBS 5.5 vs. review 6.2) and the two ECW-308
nitrile disagreements are recorded with their primary rows retained.

Two flagged rows need qualification rather than a clean exclusion claim.
Vinylene carbonate (literature range 78-127; ECW-308 independently reports
126.00, but this study did not trace 126 to an original measurement) carries
model_ready=false and conflict_open but still reaches the feature table, because
`probes/dielectric_representation_ablation.py` filters on the exclusion list and
not on the model_ready column; its epsilon of 126 therefore remains inside the
237-row benchmark. Eight benchmark rows have epsilon > 60, and vinylene
carbonate accounts for about 17.8% of the total epsilon > 60 absolute error of
the hybrid model; dropping it would move that stratum MAE from 63.93 to 60.04.
That is material but not dominant, and the row is reported rather than removed.
3-Methoxypropionitrile carries model_ready=false and
awaiting_primary_confirmation and is absent from the fitted set because it has no
GFN2-xTB physical-feature row, not because of the flag. The operative filter is
metadata, not the model_ready column. The frozen accounting is 245 source rows
= 237 fitted rows + 4 curated exclusions + 4 physical-feature failures (three
ionic liquids and iron pentacarbonyl).

## Reproducibility

The dataset is built by deterministic, versioned scripts. Each version has an
independent verifier that re-derives every metric from the raw outputs.

**Build pipeline.**
`ash
# v0.1
python scripts/build_dataset_v01.py
python scripts/verify_dataset_v01.py    # passes 8/8 checks

# v0.2
python scripts/build_dielectric_v02.py
python scripts/verify_dielectric_v02.py # passes 9/9 checks

# v0.3
python scripts/build_dielectric_v03.py --minimum-additions 10
python scripts/verify_dielectric_v03.py # passes 7/7 checks, 246 rows

# v0.3.2 / v0.3.3
python scripts/verify_dielectric_v032.py # passes 7/7 checks, 245 rows
python scripts/verify_dielectric_v03.py  # v0.3.3 superset check, 246 rows
`

**Verifier scope.** Each verifier independently reconstructs the input hashes,
row counts, temperature bands, provenance distributions, and per-row gate
flags from the committed CSV. The SHA-256 of every input and output artifact
is recorded in the probe summary JSON files.

**Cross-platform CI.** All verifiers run in continuous integration (GitHub
Actions, Ubuntu 22.04, Windows Server 2022). The gate-flag enum test
(tests/test_gate_flag_enum.py) ensures that no undocumented flag enters the
dataset.

## Model benchmark sensitivity

The fixed 10x5 repeated cross-validation ensures that every model probe and
baseline is evaluated on identical train-test splits **within a dataset
version**. Growing a dataset reshuffles the split, so a row-wise comparison
across versions is a coverage result, not a controlled estimate of what the
added compounds contribute.

**v0.3.2 coverage sensitivity.** The frozen Morgan, Physical, and Hybrid
representations were rerun under the identical fixed 10x5 protocol as each
dataset expanded. Every version was rebuilt from pinned inputs and the v0.3
baseline was reproduced exactly (R2 0.3099):

| Dataset | Fitted rows | Morgan R2 | Physical R2 | Hybrid R2 |
|---|---|---|---|---|
| v0.2 | 205 | 0.2025 | 0.2829 | 0.3201 |
| v0.3 | 235 | 0.1898 | 0.2731 | 0.3099 |
| **v0.3.2** | **237** | **0.2230** | **0.3538** | **0.3660** |

These values are not attributable to the two added compounds. Enlarging the
table from 235 to 237 rows reshuffles `RepeatedKFold`: 1272 of 2350
compound x repeat fold assignments (54.1%) differ between the two splits, and
the evaluation-set target variance grows by 8.1%. The v0.3 -> v0.3.2 row above
therefore mixes the data addition with a different random partition.

To isolate the data contribution we ran a paired control
(`probes/v032_controlled_comparison.py`). The v0.3 fold assignment was frozen,
all 235 v0.3 compounds kept their original folds in every repeat, and
propylene carbonate (epsilon 64.9) and ethylene carbonate (epsilon 90.5) were
appended to the **training folds only**, so both arms score exactly the same
held-out compounds:

| Representation | v0.3 R2 | + PC/EC (train only) | Paired delta | 95% CI | Paired p |
|---|---|---|---|---|---|
| Morgan | 0.1898 | 0.1899 | +0.0001 | [-0.006, +0.006] | 0.97 |
| Physical | 0.2731 | 0.3233 | **+0.0502** | [+0.032, +0.068] | 1.3e-4 |
| Morgan+Physical | 0.3099 | 0.3364 | **+0.0265** | [+0.017, +0.036] | 1.3e-4 |

The controlled hybrid gain is **+0.027**, about half of the +0.056 implied by
the raw version-to-version comparison. The effect sits in the Physical
representation (+0.050) while the Morgan fingerprint representation is flat
(+0.0001) and its MAE and Spearman deteriorate (p = 0.006 and p = 0.008).
That is consistent with the stated mechanism: the carbonate dipole feature,
not fingerprint bits, separates high-permittivity cyclic carbonates. The
hybrid MAE improves only slightly (6.970 -> 6.906, p = 0.14) while RMSE
improves by 0.31 (p = 9.5e-5), so the addition is a real but moderate
generalization gain rather than a step change.

**The added solvents stay outside the extrapolation range.** Training on all
235 v0.3 compounds and predicting PC and EC as external holdouts underestimates
both: the hybrid predicts 29.8 +/- 1.1 for PC (true 64.9) and 50.3 +/- 2.2 for
EC (true 90.5). Adding these two solvents improves interpolation among the
existing 235 compounds; it does not give the model extrapolation ability for
unseen high-permittivity carbonates. This limitation is consistent with the
applicability-domain rule recorded in the dataset.

**Domain-gap external test.** The frozen v0.2 model (trained on 205 classic
organic compounds) was applied to 29 new v0.3 battery-relevant solvents as an
external validation set. The Hybrid model achieves R2=0.286 and Spearman=0.590,
compared to its v0.2 cross-validation R2 of 0.320. The reduction is driven by
systematic underestimation of high-permittivity battery solvents (e.g.,
gamma-valerolactone: true 36.1, predicted 13.3; NMP: true 32.2, predicted
15.7), confirming that the v0.3 expansion captures genuinely novel chemical
space that the classic-organic model cannot interpolate.

## Physical-feature ablation

Under fixed 10x5 cross-validation:

| Representation | R2 (raw) | MAE (raw) | Spearman | AUC (eps > 30) |
|---|---|---|---|---|
| Morgan (ECFP4 count) | 0.223 | 8.22 | 0.689 | 0.826 |
| Physical (13-dim) | 0.354 | 7.50 | 0.801 | 0.936 |
| Morgan+Physical (hybrid) | **0.366** | **7.13** | **0.814** | **0.929** |

(All values are the v0.3.2 237-row benchmark; the v0.2 205-row reference
values remain 0.203 / 0.283 / 0.320 for the corresponding representations.)

The log(epsilon - 1) target improves the Physical representation on MAE
(7.50 to 6.53) and Spearman (0.801 to 0.883) while leaving R2 slightly lower
(0.354 to 0.338); it does not transfer to the hybrid (R2 0.315).

**Scaffold/cluster holdout (v0.3.2, 237 rows).** Physical with
log(epsilon - 1) has the best mean R2 (0.299 +/- 0.018) and MAE
(7.103 +/- 0.168) under structure-based holdout, confirming that physical
features generalize better to novel scaffolds than fingerprint-based
representations (probes/v032_target_scaffold_summary.json).

## Experimental-density test

For 66 of 205 compounds, ThermoML density observations within 10 K replace the
xTB-estimated molar volume. The density variant does not improve any metric on
this subset (R2 deltas: -0.001 to -0.005 across all representations and
targets). We retain the xTB-estimated molar volume and report experimental
density as a documented negative result.

## Neural-network probes

**MLP (pre-registered probe).** A single-hidden-layer MLP (64 neurons, ReLU,
Adam, log(epsilon-1) target) was trained on the same 10x5 folds of the 205-row
v0.2 feature table, not on the v0.3.2 fold set. Its best representation
(Physical) achieves Spearman 0.884 (higher than the XGBoost hybrid 0.830 on that
same 205-row table) but mean R2 = -0.172. A pre-registered linear calibration
probe (intercept + slope fitted within each training fold and applied to test
predictions) did not recover positive R2 (calibrated R2 = -0.309). The
negative R2 is therefore not merely a scale-offset issue; the MLP probe is a
true negative result regardless of its ranking strength. This closes the
neural-network line for v1.0; deeper architectures (pre-training on Batt-P30K,
multi-task dielectric-viscosity models) are deferred to N3/N4.

**Chemprop D-MPNN (baseline).** Chemprop 2.1.0 with BondMessagePassing and
MeanAggregation, 50 epochs on the same 205-row v0.2 outer folds, achieves mean
R2 = 0.237 and Spearman = 0.665. Against the like-for-like 205-row XGBoost
reference the R2 exceeds Morgan (0.237 vs. 0.203) but the Spearman is lower
(0.665 vs. 0.697 for Morgan and 0.821 for Physical), reinforcing the narrative
that graph representations carry fingerprint-level information while physical
features provide the ranking signal. Neither neural baseline was recomputed on
the v0.3.2 237-row folds.

# Limitations

**Dataset size.** The current dataset (246 compounds) is small by deep-learning
standards. The limiting factor is the scarcity of public, traceable, static
dielectric constant measurements for pure organic liquids at near-room
temperature. The dataset's value proposition rests on quality, provenance
transparency, and cross-source verification rather than row count. The
companion viscosity dataset (3,582 rows from Schrodinger et al. 2024) and the
Batt-P30K DFT dataset (29,519 molecules) provide alternative entry points for
data-hungry architectures.

**Single-temperature coverage.** Most v0.3 additions are at a single near-room
temperature (298.15 K assumed for review-table values). Multi-temperature
observations (available for some NBS and ThermoML records) are stored as
separate rows but are too sparse to support temperature-dependent modeling.
A future revision could prioritize temperature series for key solvents.

**Conformer averaging.** The GFN2-xTB dipole moment is computed for the
lowest-energy conformer only. Conformer-aware averaging (Boltzmann-weighted
dipole across the conformational ensemble) could improve the physical-feature
quality for flexible molecules at modest computational cost.

**Associated liquids.** Compounds that carry at least one hydrogen-bond donor
site, counted from the structure with the SMARTS pattern `[O,S,N;!H0]` and
never from the model output, are flagged as outside the model's applicability
domain. The rule triggers on 2,070 of the 6,150 out-of-fold rows (33.66%):
mean absolute error is 11.51 outside the domain against 5.02 inside, and it
covers all 150 rows whose measured permittivity exceeds 60. A model-independent
variant that thresholds an Onsager-estimated static dielectric at 60 was
implemented, wired into the production caller, and then rejected: the
reaction-field estimate is *low* for associated liquids (1.6-40 estimated
against measured 61-178, because the Kirkwood correlation factor `g` is much
greater than 1) and *high* for ionic liquids (82-153 estimated against measured
12-30), so it covered 0 of those 150 rows. Both rejected variants are recorded
with their numbers in `probes/applicability_domain_summary.json`. Kirkwood
correlation effects in these systems require multi-body or explicit-solvent
descriptions that are beyond the scope of the current candidate model.

**Known data gaps.** FEC (fluoroethylene carbonate) is withheld through the
curated exclusion list because reported values (78.4, 102, 107) disagree;
ECW-308 supports 78.4, but no primary source was independently retrieved and
102/107 remain unresolved. 3-Methoxypropionitrile rests on the
ECW-308 secondary compilation (36.0 at 298.15 K): Tier-0 checks of all 242 local
ThermoML dielectric files and all 636 transcribed NBS Circular 514 organic rows
returned no observation, and the cited primary source (Perricone et al. 2013) is
closed access. The glyme diethers and dinitriles that earlier drafts listed as
absent are in fact present in the dataset under their IUPAC names (diglyme =
2,5,8-trioxanonane, and so on) and are now documented explicitly. The remaining
items constitute explicit targets for the v1.1 revision. Contributions from the
community via the GitHub repository are welcome.

**The model_ready flag is advisory, not a gate.** The modelling pipeline filters
on the physical-feature status column and on the curated exclusion list; nothing
in it reads model_ready. Vinylene carbonate is therefore flagged
model_ready=false and conflict_open yet remains fitted, and so does methyl
propionate (conflict_open, model_ready=true). Two consequences are reported
rather than hidden: the 237-row benchmark contains one row the table itself marks
as unresolved, and 3-methoxypropionitrile is absent only because it never
received a physical-feature row. Closing the flag gap changes the fitted set and
invalidates the +0.0265 paired control, so it is recorded here as an open
decision instead of being applied silently.

**Neural architectures.** Graph neural networks and transformer-based models
were not systematically explored beyond the single-probe MLP and Chemprop
D-MPNN baseline. Pre-training on the Batt-P30K DFT dataset (N3) and
multi-task learning across dielectric and viscosity properties (N4) are
identified as the natural next steps, reserved for future work to avoid scope
creep before the v1.0 freeze.
