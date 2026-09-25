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
cross-check evidence; no subscription-restricted SpringerMaterials value enters
the public dataset. The two values taken from paywalled primary articles (FEC
78.4 and vinylene carbonate 126) are individual measurement facts, and their
source PDFs are kept outside the repository.

**Restricted-catalog-free corroboration (PC, EC).** Two of the compounds whose
only cross-check was the restricted catalog can be corroborated without it.
Nanbu et al. (2007, *Electrochemistry* 75(8) 607-610, open access) restates PC at
**64.92 at 25 C** and EC at **89.78 at 40 C**, and its reference 12 is Riddick,
Bunger & Sakano, *Organic Solvents: physical properties and methods of
purification*, 4th ed. (1986) - the compilation the restricted cross-check was
standing in for. The stored rows are 64.9 at 298.15 K (difference 0.02, 0.03%)
and 90.5 at 313.15 K (difference 0.72, 0.80%); both comparisons are
temperature-aligned, so neither needs a temperature correction. Two further open
papers (*Electrochemistry* 2013, 81(10) 817-819 and 820-822) reproduce the two
figures between them (PC in the first, PC and EC in the second), so neither rests
on a single transcription. This is agreement with a
compilation restatement and not an independent measurement, and it changes no
stored value; its role is to show that the restricted catalog was never the only
route to these two numbers. The remaining restricted targets, GVL and DME, are not
covered by this route. The J-STAGE access question is recorded in
reports/jstage_corroboration.md.

**NBS Circular 514 internal consistency.** All values sourced from NBS Circular
514 carry the original page number, entry figure quality, and selection rank.
For compounds with multiple NBS entries (different temperatures or purity
grades), the selection rank and figure quality determine the preferred record.

**Conflict exclusions (v0.3.3 conventions).** Nine rows carry a non-empty
conflict_status and six carry model_ready=false. Five of them are withheld from
model fitting through the curated exclusion list
(data/processed/dielectric_v03_exclusions.csv): FEC (primary 78.4 at 296.15 K,
107 read at compilation level in Ue et al. 2014, Table 2.3, with named primary
Hagiyama et al. 2008 still unread, with no open full text discoverable as of 2026-09-25 (the DOI resolves to Oxford University Press as a closed-access article, and J-STAGE returns 404 for both the article pattern and the journal root), and a 2007 downstream paper restating the
same 78.4 leg as 40 C that the primary table footnote "At 23 C." overrides), TEP (10, 13), TMP (10, 21.6), ethyl
isothiocyanate, whose NBS value
(19.5 at 294.15 K) and restricted cross-check value (29.7 at 293.2 K) differ by
10.2, and 3-methoxypropionitrile, whose 36.0 rests on a secondary compilation
awaiting primary confirmation. Methyl propionate (NBS 5.5 vs. review 6.2) and the two ECW-308
nitrile disagreements are recorded with their primary rows retained.

Two flagged rows need qualification. Vinylene carbonate now carries a primary
126 +/- 1.0 measurement at 25 C (Saadi & Lee 1966, Table 2; stored as 298.0 K)
with conflict_status=knovel_78_127_interval_contains_primary_value and
model_ready=false, and Flamme et al. 2017 repeats that same primary source
rather than corroborating it independently. Since
the v0.3.4 revision the modelling gate enforces that flag, so the row is
**withheld from every fit** and reported under `withheld_not_model_ready_names`
instead of being trained on. 3-Methoxypropionitrile also carries
model_ready=false and is additionally absent from the fitted set because it has
no GFN2-xTB physical-feature row. The frozen accounting for the v0.3.2 lineage
is 245 source rows = 236 fitted rows + 4 curated exclusions + 4 physical-feature
failures (three ionic liquids and iron pentacarbonyl) + 1 withheld
model_ready=false row (vinylene carbonate); for the v0.3.3 roster of 246 rows
the same split is 236 + 5 + 4 + 1.

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

**Coverage sensitivity under the `model_ready` gate.** The frozen Morgan,
Physical, and Hybrid representations were rerun under the identical fixed 10x5
protocol as each dataset expanded, and every version was rebuilt from pinned
inputs. The v0.3.4 re-derivation enforced the `model_ready` gate, which changed
both the fitted-row count and the values earlier drafts printed:

| Dataset | Fitted rows | Morgan R2 | Physical R2 | Hybrid R2 |
|---|---|---|---|---|
| v0.2 | 205 | 0.2025 | 0.2829 | 0.3201 |
| v0.3, pre-gate (superseded) | 235 | 0.1898 | 0.2731 | 0.3099 |
| v0.3.2, pre-gate (superseded) | 237 | 0.2230 | 0.3538 | 0.3660 |
| **v0.3.3 / v0.3.2, gate enforced** | **236** | **0.2402** | **0.3422** | **0.3636** |

The two pre-gate rows are kept only as a record of what the earlier revisions
printed; both fitted vinylene carbonate, which the dataset flags
`model_ready=false`. With the gate enforced the v0.3 and v0.3.2 lineages share
the *same* 236-row modelling set (245 source rows = 236 fitted + 4 curated
exclusions + 4 physical-feature failures + 1 withheld; for the 246-row v0.3.3
roster the same split is 236 + 5 + 4 + 1), so their reruns agree to every
reported digit and the gate-fixed row replaces both.

These row-wise differences are not attributable to the two added compounds.
Enlarging the table from 234 to 236 fitted rows reshuffles `RepeatedKFold`:
1224 of 2340 compound x repeat fold assignments (52.3%) differ between the two
splits, so the pre-gate v0.3 -> v0.3.2 row mixes the data addition with a
different random partition.

To isolate the data contribution we ran a paired control
(`probes/v032_controlled_comparison.py`). The v0.3 fold assignment was frozen,
all 234 eligible v0.3 compounds kept their original folds in every repeat, and
propylene carbonate (epsilon 64.9) and ethylene carbonate (epsilon 90.5) were
appended to the **training folds only**, so both arms score exactly the same
held-out compounds:

| Representation | v0.3 R2 | + PC/EC (train only) | Paired delta | 95% CI | Paired p |
|---|---|---|---|---|---|
| Morgan | 0.2203 | 0.2191 | -0.0012 | [-0.006, +0.003] | 0.59 |
| Physical | 0.3201 | 0.3194 | -0.0007 | [-0.016, +0.014] | 0.92 |
| Morgan+Physical | 0.3456 | 0.3515 | **+0.0059** | [-0.002, +0.013] | 0.11 |

**The controlled gain does not survive the model_ready gate.** With vinylene
carbonate withheld from both arms, the paired hybrid delta falls from the
previously reported +0.0265 to **+0.0059**, with a 95% CI that spans zero
(p = 0.11), and the Physical delta falls from +0.0502 to -0.0007. The earlier
figures were carried by a single held-out row: propylene carbonate and ethylene
carbonate are structural analogues of vinylene carbonate, so appending them to
the training folds mostly improved the prediction of that one contested
compound. Hybrid MAE is slightly worse (+0.032, p = 0.30), RMSE slightly better
(-0.067, p = 0.10), and Spearman is significantly worse (-0.0085, p = 0.0028).
The honest reading is that PC/EC broaden coverage but do **not** deliver a
measurable accuracy gain on the v0.3 compounds.

**The added solvents stay outside the extrapolation range.** Training on all
234 v0.3 compounds (the gate-fixed frozen fold set) and predicting PC and EC as
external holdouts underestimates
both: the hybrid predicts 21.6 +/- 0.4 for PC (true 64.9) and 33.7 +/- 1.5 for
EC (true 90.5). Adding these two solvents improves interpolation among the
existing 234 compounds; it does not give the model extrapolation ability for
unseen high-permittivity carbonates. This limitation is consistent with the
applicability-domain rule recorded in the dataset.

**Leave-EC-out sensitivity.** A pre-registered report-only probe removed
ethylene carbonate (313.15 K, epsilon 90.5, extended_temperature) from the
training folds while keeping the other 235 compounds' frozen fold identifiers
unchanged. The baseline arm reproduced all 7,080 frozen prediction rows. The
hybrid R2 changed from 0.3494 to 0.3381 (paired delta -0.0112, 95% CI
[-0.0243, +0.0018], p = 0.083); MAE changed from 6.5065 to 6.4874 (p = 0.606)
and Spearman from 0.8263 to 0.8295 (p = 0.148). The within-representation
metric ranking was unchanged for Morgan, Physical and Morgan+Physical, and the
explicit family ranking across the three representations was likewise identical
in both arms for every metric. When EC was scored from the 235-row
leave-EC-out fits, the hybrid mean prediction was 41.6 against the stored 90.5
(rank percentile 98.7 among the 235 compounds);
the model recognises EC as an extreme target but compresses its magnitude.
This probe is disclosure only and cannot trigger a model switch, feature change
or dataset revision. It is distinct from the external holdout above: the
holdout trains on 234 v0.3 compounds, whereas this probe removes one row from
the 236-row modelling set.

**Domain-gap external test.** The frozen v0.2 model (trained on 205 classic
organic compounds) was applied to 29 new v0.3 battery-relevant solvents as an
external validation set. The Hybrid model achieves R2=0.286 and Spearman=0.590,
compared to its v0.2 cross-validation R2 of 0.320. The reduction is driven by
systematic underestimation of high-permittivity battery solvents (e.g.,
gamma-valerolactone: true 36.1, predicted 13.3; NMP: true 32.2, predicted
15.7), confirming that the v0.3 expansion captures genuinely novel chemical
space that the classic-organic model cannot interpolate.

**A third boundary.** The carbonate holdout above and this domain-gap test are the
same failure mode seen from two directions: non-associated polar aprotic solvents in
the epsilon 32-90 range (the cyclic carbonates, and the lactam NMP) are
underpredicted by a factor of two to three, even when the model ranks them in the
upper third of the set. It is a third boundary of the candidate model, distinct from
the association blind spot, which the structural donor rule handles (33.66% trigger
rate covering all 150 rows above epsilon 60), and from scaffold extrapolation (best
R2 0.276): the training distribution does carry unassociated polar aprotic solvents,
but only up to epsilon about 46 (acetonitrile 37.5, DMF 36.6, gamma-butyrolactone
42.0, sulfolane 44.0, DMSO 46.1), so the epsilon 60-90 carbonate tail has no
unassociated near neighbour to interpolate from.

## Physical-feature ablation

The gate-fixed raw-target ablation is the v0.3.3 row of the main benchmark
table in `paper/benchmark_and_figures.md`: Morgan R2 0.240 / MAE 7.612 /
Spearman 0.722, Physical 0.342 / 7.098 / 0.802, and the equal-weight hybrid
0.364 / 6.686 / 0.828, on 236 fitted rows. The v0.2 205-row reference values
remain 0.203 / 0.283 / 0.320 for the corresponding representations.

The log(epsilon - 1) target improves the Physical representation on MAE
(7.10 to 6.37) and Spearman (0.802 to 0.880) while leaving R2 lower
(0.342 to 0.290); it does not transfer to the hybrid (R2 0.293).

**Scaffold/cluster holdout (v0.3.3, 236 rows).** Physical with
log(epsilon - 1) has the best mean R2 (0.276 +/- 0.044) and MAE
(6.669 +/- 0.218) under structure-based holdout, confirming that physical
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
the v0.3.2 236-row folds.

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
curated exclusion list because the competing 107 is available only through the Ue et al. 2014 compilation (Table 2.3), while its named primary source (Hagiyama et al. 2008) remains unread; the
stored value is now a primary 78.4 at 296.15 K (Kobayashi et al. 2003, Table 2)
and the previously stored 102 was its flash point. 3-Methoxypropionitrile rests
on the
ECW-308 secondary compilation (36.0 at 298.15 K): Tier-0 checks of all 242 local
ThermoML dielectric files and all 636 transcribed NBS Circular 514 organic rows
returned no observation, the cited primary source (Perricone et al. 2013) is
closed access, and no independent primary measurement is available for this
solvent. The glyme diethers and dinitriles that earlier drafts listed as
absent are in fact present in the dataset under their IUPAC names (diglyme =
2,5,8-trioxanonane, and so on) and are now documented explicitly. The remaining
items constitute explicit targets for the v1.1 revision. Contributions from the
community via the GitHub repository are welcome.

**The model_ready flag is now a gate.** Until v0.3.4 the modelling pipeline
filtered only on the physical-feature status column and on the curated exclusion
list, so vinylene carbonate was flagged `model_ready=false` and `conflict_open`
yet still fitted. `read_modelling_rows` now withholds every row whose dataset
record is not `model_ready=true`, returns those rows to the caller instead of
dropping them, and the accounting invariant counts them explicitly. The fitted
set fell from 237 to 236 rows and the controlled PC/EC gain fell from +0.0265 to
+0.0059 (p = 0.11) as a direct consequence -- the earlier value was driven by
the withheld row. Methyl propionate is `conflict_open` but `model_ready=true`
and remains fitted.

**Neural architectures.** Graph neural networks and transformer-based models
were not systematically explored beyond the single-probe MLP and Chemprop
D-MPNN baseline. Pre-training on the Batt-P30K DFT dataset (N3) and
multi-task learning across dielectric and viscosity properties (N4) are
identified as the natural next steps, reserved for future work to avoid scope
creep before the v1.0 freeze.
