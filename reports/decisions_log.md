# Decisions Log

## 2026-09-22: Week 1 remains provisional

- Decision: use the `dielectric_viscosity_joint` path provisionally.
- Evidence: the live NIST fallback contains 205 XML files, 91 dielectric source
  documents, and 11,646 observations. Near 298.15 K +/- 5 K there are 124
  all-component zero-frequency compounds but only 100 pure-component gate
  compounds.
- Limitation: the complete 189 MB ThermoML 2020 archive remained unavailable.
  `handbook_gate_executed=false` and `decision_status=provisional`.
- Spot check: water, acetonitrile at 1 MHz, sulfolane, DMC, and methanol pass.
  Propylene carbonate is `not_found` against the current fallback and keeps the
  manual reference 64.9. Ethylene carbonate is a blocked temperature-gate guard
  because it is not treated as a liquid pure solvent near 298 K.

## 2026-09-22: The 308-solvent ECW target is unavailable

- DOI: `10.1002/adfm.202212342`.
- Crossref, OpenAlex, Unpaywall, and DataCite expose no open machine-readable
  dataset relationship.
- Wiley returns HTTP 403 with a Cloudflare challenge; the ANSTO record contains
  metadata only.
- Decision: `target_308_available=false`. No 308-row list was fabricated.
  `coverage_gap.csv` uses Chodera 2015 as an explicit historical fallback:
  246 rows and 45 unique InChIKeys.

## 2026-09-22: Viscosity source and limits

- Correct DOI: `10.1186/s13321-024-00820-5`.
- Chew supplement 2 contains 3,582 experimental rows and 957 unique canonical
  SMILES after RDKit standardization.
- Supplement 3 contains 650 model predictions for 50 solvents and is stored
  separately with `data_status=predicted`.
- The paper's 4,440-row source dataset is not fully public because the remaining
  records were withheld for copyright reasons.

## 2026-09-22: Dielectric-viscosity intersection

- Matching uses exact InChIKey and prefers pure-component dielectric rows.
- Near 298.15 K +/- 5 K, 62 InChIKeys have both properties somewhere in the two
  tables: 51 pure-component keys and 11 mixture-only keys.
- The <=5 K temperature rule leaves 46 temperature-paired InChIKeys and 456
  paired rows across 366 unique P1 dielectric rows.
- Every exported row is marked `pair_type=loose_join`,
  `model_ready=false`, and `not_training_ready`.
- Decision: use this intersection for coverage and exploration only. Before
  joint modeling, prefer a dual-label single table at matched temperatures or
  include an explicit temperature model.

## 2026-09-22: P2 failure diagnosed

- Batt-P30K SHA256:
  `587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d`.
- Dataset: 29,519 groups and 0 invalid SMILES.
- Morgan count fingerprint radius 2, 2048 bits, plus XGBoost.
- Unit: PiNN source/docs and Batt-SLM `params.yml` establish high-confidence
  atomic-unit semantics for the dipole target; HDF5 itself has no unit metadata.
  Final MAE/RMSE are `0.3601/0.4896 a.u.` or `0.9152/1.2444 D`.
- Dummy R2 is `-0.0000026`; MW+heavy-atom Ridge R2 is `0.00679`;
  Morgan+XGBoost R2 remains `0.56365`, below 0.8.
- The diagnostic independently retrains Morgan+XGBoost and audits it against the
  formal metrics. Maximum absolute differences are MAE `4.73e-8`,
  RMSE `7.47e-9`, and R2 `3.92e-9`, below the `1e-7` numerical tolerance.
- Only `4.24%` of targets are below `1 D`, so near-zero target compression is
  not the primary explanation for the R2 result.
- Decision: the pipeline is GREEN but the model gate is FAILED. The evidence
  supports insufficient 3D/conformational representation rather than a unit
  mismatch or simple code bug. Move next to Chemprop/D-MPNN or a 3D/GNN.

## 2026-09-23: Dielectric GPR is a weak starting baseline

- Input: `data/dielectric_v01.csv`, 100 unique P1 compound keys. The 45
  Chodera keys all overlap P1 and add no independent compounds.
- Fixed model: Morgan count fingerprint radius 2/2048 bits, StandardScaler,
  GaussianProcessRegressor with deterministic 80/20 split, seed 42.
- Final kernel: `2.16**2 * RBF(length_scale=42.4) + WhiteKernel(noise_level=0.278)`.
- Test metrics: MAE `11.5345014`, RMSE `21.0820913`, R2 `0.2312574`.
- Posterior uncertainty: mean std `18.3566`; 95% empirical coverage `19/20`.
- Decision: this is an active-learning starting point, not a finished model.
  The R2 gate fails, and no Week3/P4 work is started from this result.

## 2026-09-23: Dielectric baseline diagnostics

- Original 80/20 GPR metrics remain unchanged: MAE `11.5345`, RMSE `21.0821`,
  R2 `0.23126`.
- Same-split controls: Dummy R2 `-0.01811`; MW+heavy-atom Ridge R2 `0.03728`.
- Repeated 5-fold/10-repeat CV: MorganRBFGPR R2 `0.02295 +/- 0.68149`, showing
  weak and highly variable performance across folds.
- The fixed-test learning curve is noisy; the full 80-row training subset was
  best in this experiment.
- Descriptor augmentation quick test reaches R2 `0.38059`, MAE `10.1514`, and
  RMSE `18.9240`. This is evidence for a future representation upgrade, not a
  gate pass or finalized model.

## 2026-09-23: Chodera cross-check and high-temperature extension

- Chodera cross-check includes all 45 common InChIKeys. Median absolute median
  difference is `0.175`; maximum is `7.341` for N-methylacetamide.
- Nearest-temperature pairing uses observed pairs only, with no interpolation.
  Forty-four keys are near-isothermal, where temperature cannot explain the
  observed difference. One key has a `10.05 K` gap where temperature may
  contribute, but this is not proven without a temperature model.
- The high-temperature NIST window `313.15-323.15 K` contains 205 observations
  and 46 keys.
- Ethylene carbonate is added only as a manual literature point: `313.15 K`,
  `90.5`, `1 MHz`, DOI `10.1021/je050341y`, `<1.5% relative` uncertainty.
  It remains `frequency_dependent`, single-source, and absent from main v0.1.
- Decision: keep the main v0.1 table unchanged; the extension contains 47 keys
  and 206 observations as supplemental evidence.

## 2026-09-23: Dielectric kernel comparison

- Tanimoto-GPR, RBF-GPR, and XGBoost were evaluated on the same 10x5 repeated
  CV split.
- Mean R2: Tanimoto `0.04246 +/- 0.81976`, RBF `0.02295 +/- 0.68149`,
  XGBoost `0.03185 +/- 0.54243`.
- Tanimoto improves mean R2 over RBF by only `0.01950`, with the best MAE and
  RMSE among the three models.
- Decision: the modest improvement does not pass the `0.8` gate and does not
  justify further kernel hyperparameter tuning. Inspect fold-level failures
  and representation/data limits next.

## 2026-09-23: Viscosity strong baseline

- Input: 3,582 experimental viscosity rows and 957 unique InChIKeys.
- Target: `log10(viscosity_cP)`; features are Morgan count 2048 plus `T_K` and
  `1000/T_K`.
- Random-row XGBoost: MAE `0.06357`, RMSE `0.11868`, R2 `0.93689`; passes the
  log10(cP) MAE `0.15` gate.
- Group-holdout XGBoost: MAE `0.17477`, RMSE `0.24407`, R2 `0.74813`; fails
  the same gate.
- Decision: random-row success primarily reflects temperature interpolation
  within known molecules. The group-holdout result is the relevant limitation
  for screening unseen molecules; no tuning is performed this round.

## 2026-09-23: AL Round-1 shortlist

- Inputs are pinned to Batt-SLM commit
  `a5101e30c6975552d97e34f1e93461126715c862`; Batt-SLM SHA256 is
  `c2ec78256ce6189366aebd9f7f0403e669c963e911cf51f7732083bce6374a1d`.
- The 115,756-row pool yields 85,921 safe candidates after excluding 27 keys
  present in dielectric v0.1 and 29,808 structures matching the versioned
  `al_round1_hazard_v4` SMARTS rules. The thiocarbonyl flag uses both the
  ordinary `[CX3]=[SX1]` rule and the complete `[#6]=[#16]` motif; the real
  cumulated SMILES `C1=S=C=C2OCCOC=12` is excluded.
- Acquisition is `std_percentile * novelty`; all 300 longlist rows are Tier A/B.
  Hard family quota 6 without an all-remaining fallback selected 20 A/B rows,
  then 10 Tier C rows were added as continuation candidates.
- The deterministic MaxMin Top 30 contains 6 Cyclic Carbonates, 6 Ethers,
  6 Formates, 5 Sulfones/Sulfoxides, 3 Ketones, 2 Nitriles, 1 Other Ester, and
  1 Linear Carbonate. Tiers are A 6, B 14, and C 10. Every family count is at
  most 6.
- Polyhalogenated alkyl structures that do not match a hard rule are retained
  with `manual_review_warnings=polyhalogenated_alkyl`: 10,602 safe candidates
  and 9 final Top 30 rows. The field `model_sha256` is renamed
  `model_input_sha256` to avoid implying that the hash is a serialized model
  artifact.

## 2026-09-23: P4 redox probes

- RX-392 is pinned at commit
  `a5101e30c6975552d97e34f1e93461126715c862`; its 392 rows use the upstream
  `DIELECTRIC=18` filter and 4.44 eV redox free-energy convention.
- The merged table contains 29,911 rows: 392 RX-392 rows with redox targets and
  29,519 Batt-P30K rows with source-native IP/EA/HOMO/LUMO/dipole only.
- Fixed held-out results: oxidation best MAE `0.2905 eV` and reduction best MAE
  `0.4096 eV`; the `0.15 eV` gate fails for both targets.
- Decision: retain the negative result. Scalar IP/EA models are substantially
  better than Morgan fingerprint GPR on this small RX-392 set, but no redox
  gate claim is made. The 308-solvent ECW target remains unavailable with zero
  fabricated rows.

## 2026-09-23: Milestone 2 and v0.2 expansion ceiling

- v0.1 remains at 100 unique compounds. `data/dielectric_v02.csv` was not
  created and the `>=200 compounds` acceptance item fails.
- NIST contributes 100 near-room pure zero-frequency compounds and 103
  all-temperature zero-frequency pure compounds.
- ChalkLab commit `681a946669feaf6ccc13ba6e1de760385c57ce73` has five pinned
  LFS archives totaling 411,920,425 bytes and 122,403 JSONLD entries. Its
  zero-frequency pure set has 103 keys, 100 v0.1 overlap, 3 all-temperature new
  keys, and 0 new near-room keys. Its broader component universe is 187.
- ChemDataExtractor has 60,804 records and 11,054 compounds but lacks an
  independent temperature field and is candidate discovery only. The 308 ECW
  dataset remains unavailable.
- Decision: v0.2 requires manual literature/handbook mining. AL longlist 300
  and Top30 are the starting queue, not validated training labels.

## 2026-09-23: Milestone 2 second-round source audit

- Landolt-Börnstein 2015 DOI `10.1007/978-3-662-48168-4` is a closed manual
  transcript candidate with at least 217 pure-substance chapter metadata
  records. Quantity may be sufficient, but row-level eligibility and rights
  handling are not yet established.
- Landolt-Börnstein IV/17, CRC Handbook Permittivity of Liquids, DDBST's
  no-data policy, the DTU fluorescence dataset, the binary-solvent QSPR
  Figshare item `10.6084/m9.figshare.2802712`, and the unlicensed GitHub
  binary-mixture repository do not provide an automatic pure-component v0.2
  path.
- Decision: keep the open-data automatic ceiling at 187, keep
  `data/dielectric_v02.csv` absent, and use
  `docs/week3/manual_dielectric_entry_schema.md` for future manual entries with
  explicit `closed_source` and `non_redistributable` markers.

## 2026-09-23: GPR diagnostics verifier tolerance

- DummyMean and SizeOnlyRidge metrics remain under the strict absolute
  tolerance `1e-12`.
- MorganRBFGPR fold/learning metrics use `rtol=1e-5`, `atol=1e-8`.
  Descriptor-GPR metrics and `r2_gain_over_morgan` use the same relative
  tolerance plus a real-scale absolute tolerance `atol=1e-5`.
- Split, configuration, input hash, descriptor, and non-GPR checks are not
  relaxed. No model artifact is regenerated by this verifier change.

## 2026-09-23: shared verifier numerical tolerance

- Added `electrolyte_ml.numerics.numerical_values_close` with explicit model
  families: GPR `rtol=1e-5, atol=1e-5`, Morgan GPR `1e-5/1e-8`, descriptor GPR
  `1e-5/1e-5`, XGBoost `1e-5/1e-5`, and strict `1e-12`.
- Kernel comparison uses the GPR profile for Tanimoto/RBF GPR metrics and the
  stricter XGBoost profile for XGBoost. AL Round-1 uses the GPR profile only for
  prediction, uncertainty, percentile, acquisition, and step-score fields;
  structural and identity fields remain strict. P4 does not retrain a GPR in
  its verifier, so its prediction-derived checks remain unchanged.

## 2026-09-23: kernel XGBoost single-thread reproducibility

- The kernel comparison builder and verifier now construct XGBoost with
  `tree_method="exact"` and `n_jobs=1`; the per-row and summary configuration
  strings record both values.
- Exact trees replace the histogram reduction that produced cross-platform
  drift, instead of further relaxing numerical checks.
- Regenerated XGBoost CV metrics are MAE `11.1547071`, RMSE `20.4628613`, and
  R2 `-0.0019521`. Two consecutive builder runs produced identical
  CSV/summary/plot hashes.
- Decision: keep all 30 as `awaiting_manual_review`. They are not confirmed as
  available, room-temperature liquids, or experimental dielectric references.
  The unavailable 308-solvent ECW list was not used as a candidate pool.

## 2026-09-23: dielectric v0.2 from NBS Circular 514

- Added 110 near-room pure-liquid compounds from NBS Circular 514
  `10.6028/nbs.circ.514`, a public US Government publication containing more
  than 800 evaluated liquids. The 100 v0.1 rows are unchanged.
- Retained only three- or four-figure estimates with no frequency footnote.
  Excluded known hazard motifs, reactive aliphatic halides, alkynes, vinyl
  heteroatom motifs, and hydrogen cyanide before ranking by SolvFunc similarity,
  polarity-related groups, and reduced size penalty.
- Structures were resolved through PubChem with CACTUS fallback, canonicalized
  with RDKit, formula-checked against the source row, and deduplicated by
  InChIKey.
- An independent 20-row PDF audit found one quality-label error: carbon
  disulfide `2.641` is four figures, not three. The label was corrected and all
  dependent artifacts were regenerated.
- Decision: `data/dielectric_v02.csv` now contains 210 unique compounds and
  passes the v0.2 verifier `8/8`.

## 2026-09-23: restricted SpringerMaterials cross-check

- Captured 25 Thermophysical Property datasets and 61 name-matched Interactive
  pure-substance datasets through the user's authenticated Edge session.
- The Interactive capture contains 3,263 rows, including 933 near-room rows.
- A ±5 K comparison matched 60 v0.2 compounds. Median absolute difference is
  `0.05`, p90 is `0.669`, and maximum is `10.2`.
- `Ethyl isothiocyanate` is the maximum outlier and is marked for manual source
  review; v0.2 remains unchanged until the conflict is resolved.
- Decision: keep raw and row-level restricted data under
  `data/restricted/springer_materials/`; only aggregate cross-check statistics
  enter public reports.

## 2026-09-23: Anchor cross-check across every in-repo source

- New `data/processed/anchor_crosscheck.csv` covers all seven v0.2 anchors
  against six in-repo evidence sources (`p1_spot_check`, `dielectric_v01`,
  `dielectric_v02`, `dielectric_v01_ext`, `chodera_crosscheck`,
  `nbs514_transcript`), 23 rows total: 13 `agree`, 3 `disagree`,
  6 `not_comparable`, 1 `no_data`.
- Comparability is decided before agreement. A 1 MHz datum is not scored
  against a static reference and a 293.15 K datum is not scored against a
  298.15 K one; such rows are `not_comparable`, which is evidence that the
  compound was measured rather than evidence about the reference value.
- Methanol is `promotion_blocked`. The p1 spot check (`32.72`) and the NBS 514
  transcription (`32.63`) both agree with the `32.6` reference at tolerance
  `0.2`, but the promoted v0.1 and v0.2 value `33.6` is off by `1.0` and the
  Chodera compilation gives `33.1`. The Week 1 spot check therefore passes while
  the promoted training value does not match the reference.
- Likely cause: seven rows attributed to pure methanol at 298.15 K from
  `10.1021/je060248p` span `32.72-39.25`, which is not physically plausible for
  a single pure solvent's static constant. If they are mixture points, the
  `is_pure` label is wrong and the v0.1 aggregate is biased high. Recorded as
  acquisition request `req004`.
- Benzene agrees from NBS 514 and v0.2 (`2.284` at 293.15 K). Its 45 NIST
  zero-frequency rows are all binary mixtures, so the near-room pure static
  value rests on a single source.
- Acetonitrile's 1 MHz datum (`35.88`) agrees, but the v0.2 NBS 514 entry
  (`37.5` static at 293.15 K) is `not_comparable` to a 1 MHz / 298.15 K
  reference. DMC and DEC agree from up to four sources; the DMC reference
  `3.09` sits `0.044` below both v0.1 and Chodera, at the edge of its `0.05`
  tolerance. EC rests on one manual source. PC is `no_data`, re-verified
  against every artifact.
- Decision: keep all 23 rows and choose no side. Methanol stays blocked pending
  `req004`.

## 2026-09-23: v0.2 provenance hash corrected and gate-flag drift closed

- `probes/dielectric_v02_summary.json` recorded
  `candidate_sha256=504b1ec2...` while the committed
  `data/processed/nbs514_structure_candidates.csv` hashes to `a787c39f...`.
  The candidate was regenerated after the build and committed without
  rebuilding the summary.
- The dataset itself is sound: rebuilding from the committed inputs reproduces
  `data/dielectric_v02.csv` byte for byte (hash `3f18e41a...`). Only the
  recorded input hash was stale. Rebuilding in place corrected the summary; the
  v0.2 table is unchanged.
- `nbs514_circular_514` was used by all 110 NBS rows but was absent from
  `GATE_FLAGS`. Nothing compared a dataset's flags against the enum, so the
  drift was invisible to every validator that tests membership in it.
- Registered `nbs514_circular_514` and `crosscheck_only`, added a gate-flag
  check to the v0.2 verifier, and added `tests/test_gate_flag_enum.py` as the
  regression guard. The verifier now reports `9/9`, and it is wired into CI,
  where it previously was not run at all.
- Decision: `closed_source` and `non_redistributable` stay out of `GATE_FLAGS`.
  They are dedicated columns in `docs/week3/manual_dielectric_entry_schema.md`,
  and duplicating them as flags would create a second source of truth for the
  same fact.

## 2026-09-23: Search-material intake and acquisition list

- `搜索资料` lives outside the repository and now carries
  `manifest/search_material_registry.csv` plus a root `SHA256SUMS`, written by
  `scripts/register_search_material.py`. The registrar refuses a root inside the
  repository, defaults every artifact to `closed_source=true`,
  `non_redistributable=true`, `redistribution_status=unclear`, and treats
  screenshots, PDFs and anything under a `public_metadata`/`preview` path as
  never-data. It is deliberately not wired into CI.
- `搜索资料/acquisition_requests.csv` lists four open items. Dataset coverage is
  already satisfied for benzene and acetonitrile by NBS 514; PC lacks only a
  traceable source, and EC is recorded as structurally blocked because its
  melting point near 309.5 K places it outside the near-room liquid window
  rather than as a search target.
- NBS Circular 514 redistribution remains `unclear` until a copyright
  determination is recorded in `data/processed/data_expansion_source_audit.csv`.

## 2026-09-23: Week 4 physical-feature representation ablation

- Completed GFN2-xTB physical features for 205 of 210 v0.2 compounds. Four
  calculations failed and one conflicting source value is excluded, so no
  missing physics was imputed.
- The fixed 10x5 repeated-CV comparison gives mean R2 `0.203` for Morgan,
  `0.283` for pure physical features, and `0.320` for a true 0.5/0.5
  Morgan+Physical prediction ensemble. Mean MAE is `7.654`, `7.238`, and
  `6.726`, respectively.
- Spearman correlation rises from `0.697` for Morgan to `0.830` for the
  ensemble. Pure physical features remain better at `epsilon > 30` AUC
  (`0.928` versus `0.915`).
- Decision: promote physics-informed features as the Week 5 direction. Do not
  claim a full-range model: the `epsilon > 60` stratum still has mean MAE
  `63.8-81.3`.
- Decision: reserve one controlled transformed-target experiment
  (`log(epsilon - 1)` or Onsager/Clausius-Mossotti linearization) before any
  additional data expansion. No target transform was selected post hoc in
  Week 4.
- Independent verifier `scripts/verify_dielectric_representation_ablation.py`
  reproduces all 150 fold metrics, 30 repeat metrics, and summary means from
  6,150 OOF predictions (`12/12` checks). Cold xTB timing is `0.134-0.235 s`
  per representative molecule.

## 2026-09-23: Week 5 target transform, scaffold holdout, and database recheck

- The pre-registered `log(epsilon - 1)` test is accepted only for the pure
  Physical representation under random CV: R2 `0.283 -> 0.303` and MAE
  `7.238 -> 6.066`. It is rejected for Morgan and raw-scale Morgan+Physical.
- A scaffold/cluster holdout now groups ring molecules by Murcko scaffold and
  acyclic molecules by ECFP4 Butina clusters, repeated over five balanced
  partitions. Physical with `log(epsilon - 1)` has the best mean R2
  (`0.267 +/- 0.014`) and MAE (`6.718 +/- 0.316`).
- Do not deploy a single target transform universally. Keep raw and transformed
  heads and choose by screening objective: raw-scale hybrid for R2, log
  Physical for MAE/ranking, and log hybrid for high-permittivity AUC.
- Database recheck finds no automatic path from 210 to 300-400 compounds.
  NBS Circular 514 has only four additional eligible records pending manual
  review; NIST/ChalkLab add no new near-room keys; Landolt remains manual;
  SpringerMaterials remains restricted cross-check data.
- Independent verifier `scripts/verify_dielectric_target_scaffold.py` passes
  `11/11`, reconstructs scaffold/cluster labels and folds independently from
  SMILES, and reproduces 90 metric rows plus 18,450 predictions.

## 2026-09-23: Week 6 density audit and applicability boundary

- ThermoML density observations within `10 K` of each row's target temperature
  replace the xTB-estimated molar volume for 66 of 205 successful physical-feature
  compounds. The remaining 139 rows explicitly retain `molar_volume_source =
  xtb_estimated`; they are not silently imputed with a near-room value.
- Experimental density is a feature-source upgrade, not a target correction. The
  resulting `mu_sq_over_Vm_experimental` column is stored separately from the
  original estimate so target-transform comparisons can be rerun without
  changing the experimental labels.
- **Superseded 2026-09-24** (see the applicability-domain entry at the end of
  this log). The first applicability rule flagged `HBD >= 1` and predicted
  dielectric `> 60` as `outside_associated_liquid`. It fired on only 30 of the
  6,150 OOF predictions and was circular; it is no longer in force.
- SpringerMaterials Interactive supplied restricted near-room evidence for 30
  modern-solvent candidates. Only candidate metadata and reference names enter
  public outputs; numeric values remain under `data/restricted/springer_materials/`
  and `public_trainable_value_count` stays zero.
- Decision: do not promote restricted values into v0.3. Build the public v0.3
  table only after independently resolving the original literature and its
  redistribution status.

## 2026-09-23: Public v0.3 increment and physical-feature freeze

- Added six nitriles from the publicly available Helambe et al. Pramana
  article and four remaining eligible NBS Circular 514 records. The resulting
  `data/dielectric_v03.csv` has 220 compounds and is reproducible from v0.2 plus
  ten public additions; the independent verifier passes `6/6`.
- This is not yet the 30-50 modern-solvent target. The remaining search queue
  stays explicit in `modern_battery_solvent_candidate_queue.csv`; no
  subscription-only numeric values were promoted into the public table.
- Experimental density replaced estimated molar volume for 66 of 205 physical
  feature rows. Under the same 10x5 folds, the density variant slightly reduced
  R2 for Physical raw/log and Hybrid raw/log, with no compensating MAE or AUC
  gain. Decision: freeze the original xTB `mu_sq_over_Vm` feature and retain the
  experimental-density comparison as a negative result.
- Added a small-data MLP probe with the same folds and `log(epsilon - 1)`
  target. Its best mean R2 is negative and the Go/Kill result is `no_go`;
  however, the Physical MLP reaches mean Spearman `0.884` versus `0.830` for
  the XGBoost hybrid. Decision: treat neural models as ranking diagnostics,
  not as a replacement for the frozen regression model.
- Completed the Chemprop 2.1.0 D-MPNN baseline in an isolated environment
  because its NumPy<2 constraint conflicts with the project pin. With the same
  10x5 outer folds, mean R2 is `0.237`, MAE `7.887`, and Spearman `0.665`.
  Decision: retain Chemprop as the required benchmark row, but do not promote
  a neural model over the frozen XGBoost hybrid.

## 2026-09-23: v0.3 public coverage expansion

- Expanded `dielectric_v03.csv` from 220 to 243 rows using 23 additional public
  CC-BY/PMC review-table and article values. These cover EMC, DOL, THF,
  2-MeTHF, GVL, fluorinated ethers, phosphates, esters, difluorobenzene,
  chlorinated diluents, and related electrolyte solvents.
- Thirty additions are marked `model_ready=true`. FEC, TEP, and TMP are kept
  in the public table but marked `model_ready=false` because independent public
  sources disagree materially. `Ethyl isothiocyanate` remains excluded from
  model fitting because the NBS and restricted cross-check values differ by
  `10.2`.
- Rebuilt all 239 eligible physical-feature rows with GFN2-xTB. On the 235
  successfully featurized rows, Morgan+Physical mean R2 is `0.310` versus
  `0.320` on the 205-row v0.2 set; Physical R2 is `0.273` versus `0.283`.
  Decision: treat v0.3 expansion as a coverage and domain-relevance result,
  not as evidence of improved predictive accuracy.
  **Corrected 2026-09-24 (v0.3.4):** that rerun fitted vinylene carbonate,
  which the dataset already flagged `model_ready=false`. With the flag enforced
  as a gate the fitted set is 236 rows and the gate-fixed rerun gives hybrid
  R2 `0.364` (MAE `6.686`, Spearman `0.828`) against `0.320` on the
  205-row v0.2 set, with a controlled train-only delta of `+0.0059`
  (95% CI -0.002 to +0.013, p = 0.11). The coverage-not-accuracy decision
  stands and is now stronger; see the v0.3.4 entry below.

## 2026-09-24: applicability-domain veto re-derived (structural donor rule)

- The Appendix I veto required a trigger that does not read the model output.
  The prescribed Onsager variant (`HBD >= 1` and Onsager-estimated dielectric
  `> 60`) was wired into the production caller and measured. It is physically
  inverted: the reaction-field estimate is *low* for associated liquids
  (1.6-40 against measured 61-178, since the Kirkwood factor `g` is much
  greater than 1) and *high* for ionic liquids (82-153 against measured
  12-30). It covers **0 of the 150** rows whose measured permittivity exceeds
  60 and flags one low-permittivity ionic liquid (measured 23.3) instead.
- Decision: adopt a structural trigger. A compound with at least one
  hydrogen-bond donor site, counted from its SMILES with the SMARTS pattern
  `[O,S,N;!H0]`, is flagged `outside_associated_liquid`; a prediction below
  1.0 is flagged `outside_nonphysical`. This is model-independent and
  textbook, unlike RDKit `NumHDonors`, which is a drug-likeness heuristic and
  returns zero donors for water.
- Measured on the frozen 6,150 out-of-fold rows: trigger rate 33.66%
  (2,070/6,150); mean absolute error 11.51 outside versus 5.02 inside;
  measured-epsilon>60 coverage 150/150 (100%), against 5/150 for the original
  circular rule and 0/150 for the Onsager variant.
- Both rejected variants are recorded with their rules, row counts, MAE and
  reasons in `probes/applicability_domain_summary.json`. The write-up is
  `reports/applicability_domain_veto_fix.md`. No `dielectric`, `T_K` or
  `model_ready` value changes, so the datasets and the controlled benchmark
  are untouched.

## 2026-09-24: model_ready becomes a gate (v0.3.4)

- The paper claimed "5 withheld, 236 fitted rows", but no fitting script could
  produce that split. The feature tables carry no `model_ready` column, so the
  single fitting choke point `read_modelling_rows` filtered only on the curated
  exclusion list and on feature success. Vinylene carbonate (`model_ready=false`,
  `conflict_open`) was therefore fitted in every revision up to v0.3.3.
- Decision: `read_modelling_rows` reads `model_ready` from
  `data/dielectric_v03.csv` (join on InChIKey) and returns a three-way split --
  fitted, feature-failed, withheld. Withheld rows are returned rather than
  dropped, a source row without a roster entry raises `ValueError` because its
  status would be unknowable, and the accounting invariant is extended to
  `fitted + failed + withheld + excluded == source` with the exclusion list
  intersected against the source lineage.
- Frozen accounting: the v0.3.2 lineage is 245 source rows = 236 fitted + 4
  curated exclusions + 4 physical-feature failures + 1 withheld (vinylene
  carbonate); the v0.3.3 roster of 246 rows is 236 + 5 + 4 + 1, the fifth
  exclusion being 3-methoxypropionitrile, which had been implicitly out because
  it has no physical-feature row.
- The controlled benchmark was re-derived. The paired train-only PC/EC hybrid
  gain fell from `+0.0265` to `+0.0059` (95% CI -0.002 to +0.013, p = 0.11)
  and the Physical gain from `+0.0502` to `-0.0007`: the earlier effect was
  carried by the withheld row, since PC and EC are structural analogues of
  vinylene carbonate. Fold churn is 1224 of 2340 compound x repeat assignments
  (52.3%).
- The main 10x5 benchmark on 236 rows: Morgan R2 `0.240` / MAE `7.612` /
  Spearman `0.722`; Physical `0.342` / `7.098` / `0.802`; hybrid `0.364` /
  `6.686` / `0.828`. Scaffold/cluster holdout on the same 236 rows keeps
  Physical `log(epsilon-1)` as the best representation (R2 `0.276 +/- 0.044`,
  MAE `6.669 +/- 0.218`).
- No data value moved: `data/dielectric_v03.csv` sha256 stays
  `2cd58144deac6b3b4b88045de7f53564f1a9c95ff3cc9c06707d776f43e42a1b`. The
  v0.3.2 and v0.3.3 lineages now fit the *same* 236 rows and return identical
  metrics, so the row-wise v0.3 -> v0.3.2 "coverage gain" is fold churn plus the
  previously ungated row.
- Enforcement: `check_modelling_set_and_controlled_delta` and
  `check_coverage_sensitivity_table` in
  `scripts/check_paper_artifact_consistency.py` re-derive the fitted-row count,
  the paired delta and its CI, and the per-version coverage table from the
  committed artifacts; `tests/test_dielectric_representation_ablation.py` pins
  the three-way split and the withheld-versus-failed distinction. Write-up:
  `reports/v034_model_ready_gate.md`.

## 2026-09-24: 3-methoxypropionitrile provenance patch and the gamma-valerolactone ticket (v0.3.5)

- Scope: **provenance only**. No numeric dielectric value is added, removed or
  changed, so no benchmark metric moves; the fitted 236 rows and every published
  table are untouched by this revision.
- 3-methoxypropionitrile (`OOWFYDWAMOKVSF-UHFFFAOYSA-N`, dielectric 36.0 at
  298.15 K, `model_ready=false`) previously recorded only the closed primary
  (Perricone et al. 2013, DOI `10.1016/j.electacta.2013.01.084`) and the
  compiling review (ECW-308, DOI `10.1002/adfm.202212342`), and its note said
  the value could not be retrieved or confirmed. The same first author's
  **open-access** doctoral thesis (Perricone 2011, Universite de Grenoble, NNT
  `2011GRENI032`, HAL `tel-00630049`), Tableau 12 on page 65, states
  `epsilon_r = 36` for methoxypropionitrile.
- Decision: add `tel-00630049` to `source_dois_all` and rewrite the note to
  record exactly what the thesis does and does not establish. The thesis gives
  no temperature (ECW-308 asserts 25 C) and belongs to the same research line,
  so this is **document-level corroboration, not a second measurement**: the
  evidence level is unchanged and the row stays out of the model-ready set. The
  ECW-308 Table S3 stacked `25.00` warning is preserved in the same note - not
  averaged and not promoted.
- Implementation: two rows edited in
  `data/processed/dielectric_v03_provenance_patches.csv`. The patch layer is the
  only place this row's provenance is written, so a rebuild is the only
  propagation step.
- Frozen hash: `data/dielectric_v03.csv` moves from
  `2cd58144deac6b3b4b88045de7f53564f1a9c95ff3cc9c06707d776f43e42a1b` to
  `b99327766b7b7f7369f7a55bbb1067508fe138e0c344f25c9cffbdf205a2d74f`. The row
  count stays 246 and a field-by-field diff against the previous revision shows
  only the single 3-methoxypropionitrile row differs. Re-pinned in
  `tests/test_build_dielectric_v03.py`; `dataset_sha256` in
  `probes/dielectric_v03_representation_ablation_summary.json` and
  `probes/v032_ablation_summary.json` updated to match.
- Open ticket, **not** promoted in this revision: the Perricone 2011 thesis
  Tableau 8 (ref [87]) gives gamma-valerolactone `epsilon_r = 32` at 25 C
  against the dataset's `36.1` at 298.15 K from the iScience 2026 review table.
  Both sides are secondary documents, the gap is 12.7%, and neither is a traced
  primary measurement. Per the no-averaging / no-swapping discipline neither
  value is changed; the disagreement is recorded for primary review and is not
  written into the dataset `conflict_status` column. Evidence:
  `reports/g1plus_perricone_thesis_crosscheck.md`.
- Retrieval note: the HAL PDF sits behind an Anubis proof-of-work interstitial;
  it was fetched through the user's Microsoft Edge via Playwright
  (`chromium.launch(channel="msedge")`). The thesis is open access and is
  cached git-ignored under `data/external/g1plus/mopn/`; it is never
  redistributed.

## 2026-09-24: PubChem tier-1 audit and the acetonitrile / sulfolane cross-check notes (v0.3.6)

- Scope: provenance only. Two rows gain a cross-check note; no numeric value,
  temperature, evidence level or `model_ready` flag changes. Rows stay at 246 and
  the fitted 236 are untouched.
- The audit tested Appendix J's claim that PubChem's Experimental Properties
  section deposits Riddick dielectric data, naming ethylene carbonate. Each of 14
  targets was resolved **by InChIKey first** so a name collision cannot be
  recorded against the wrong substance. Every target matched the dataset key.
- Result: **no target carries a dielectric value that PubChem attributes to
  Riddick.** Ethylene carbonate cites Riddick, Bunger & Sakano, *Techniques of
  Chemistry 4th ed., Vol. II, Organic Solvents*, 1985, p. 989 - but inside a
  *purification* procedure ("purified ethylene carbonate for dielectric constant
  and dipole moment studies"), not as the source of a number. The manual's
  wording is corrected in `reports/g1plus_pubchem_findings.md`.
- Two citable numbers were found, both from other compilations: sulfolane 43.3
  with no temperature (Kirk-Othmer 4th ed., Vol. 23, p. 135, 1995), and
  acetonitrile 38.8 at 20 C (Merck Index, Royal Society of Chemistry 2013, p. 14)
  plus 42.0 / 38.8 / 26.2 at 0 / 20 / 81.6 C (DeVito, Nitriles, Kirk-Othmer 2007
  posting). PubChem also supplies every one of these as a link rather than a
  value.
- Decision: record both as cross-checks and change nothing else. The
  acetonitrile note records that the retained 37.5 is at 293.15 K, which is also
  20 C, so PubChem's 38.8 disagrees by 3.5% at matched temperature; NBS Circular
  514 is the stronger evidence class, so no average is formed. The sulfolane note
  records that 43.3 brackets the retained 44 at 298.15 K and the Perricone 2011
  thesis's 43 at 30 C.
- Nine of the fourteen records expose a **SpringerMaterials Properties** entry
  for the dielectric constant as a deep link, not a value. The substance ids are
  recorded in `probes/g1plus_pubchem_evidence.json` so the restricted-database
  round becomes a lookup. Propylene carbonate, vinylene carbonate,
  fluoroethylene carbonate, gamma-valerolactone and 3-methoxypropionitrile carry
  no such pointer, so the tier-3/tier-4 ladder is still required for exactly
  those five.
- Implementation: two `notes` rows added to
  `data/processed/dielectric_v03_provenance_patches.csv`; rebuild is the only
  propagation step. A field-by-field diff against the previous revision shows
  only the acetonitrile and sulfolane `notes` fields differ.
- Frozen hash: `data/dielectric_v03.csv` moves from
  `b99327766b7b7f7369f7a55bbb1067508fe138e0c344f25c9cffbdf205a2d74f` to
  `f5256d164c814030a4b986db6c878f1d64edb2b4f91cf39af3a75ffeaeac853c`, re-pinned
  in `tests/test_build_dielectric_v03.py` and in the two benchmark summaries.
- Budget: 56 PubChem calls for the first pass, inside the 500/hour ceiling; the
  cache makes every re-run spend zero calls and rewrite the evidence JSON byte
  for byte.
- Still open after this round: the FEC 78.4/102/107 spread, the VC 126 vs 78-127
  conflict, the gamma-valerolactone 36.1 vs 32 (thesis also gives 34) conflict,
  and MOPN's missing GFN2-xTB feature row. Write-up:
  `reports/g1plus_pubchem_findings.md`.

## 2026-09-24: tier-1 closeout - the WebBook structural negative and the adversarial repair of the PubChem evidence

- **NIST Chemistry WebBook (second half of tier 1): no dielectric evidence on the surface
  this probe could reach, so it is not usable as a source here.**
  Appendix J's parenthetical that the WebBook holds dielectric constants for some
  substances is not supported on any surface this probe could reach. All 14 G1+ targets were queried through the `Name=` /
  `ID=` forms and gated on the `inChIKey` embedded in each compound page: 13 of
  the 14 resolved to a page whose key matches the dataset, and **none of the 14
  exposes a dielectric or permittivity facet**. Fluoroethylene carbonate is absent from the WebBook entirely (CAS
  114435-02-8 answers "Registry Number Not Found" - that CAS response comes from the
  **first** tier-1 pass and its raw cache, not from this probe, which simply finds no
  candidate for the name; the two checks are recorded separately).
- The negative is not a lookup failure: the same test was run on four positive
  controls (water, methanol, ethanol, acetone) whose dielectric constants are not in
  dispute, and **all four are equally empty**. Water, methanol, ethanol and acetone are
  the strongest expected positives for a surface that carries this property, so their
  emptiness is a strong indication rather than a formal proof. **Scope:** the claim covers the compound
  pages reached through `Name=` / `ID=` (18 records, tested against dielectric,
  permittivity, epsilon and the symbol ε). It is not a claim that no WebBook entry
  point, sub-page or JavaScript panel anywhere could ever carry such a quantity, and a
  later review round narrowed the wording to say exactly that. Evidence:
  `probes/g1plus_nist_webbook_evidence.json`, write-up
  `reports/g1plus_nist_webbook_findings.md`. Opened with plain `urllib` HTTPS; no
  browser session or login is involved.
- No dataset impact. Nothing is added, moved or reclassified, so
  `data/dielectric_v03.csv` stays at
  `f5256d164c814030a4b986db6c878f1d64edb2b4f91cf39af3a75ffeaeac853c`.
- **Adversarial review round (two read-only reviewers, baseline `71295e2`):
  fail, then repaired.** Both reviewers independently returned FAIL on the same
  P1, and the finding was correct:
  1. The PubChem evidence JSON counted **any** string containing "dielectric" as a
     standard value, so nine compounds were filed under
     `with_standard_dielectric_value` when only two of them state a number. Of the
     seven spurious entries, six carry nothing but a SpringerMaterials *link* and
     one (ethylene carbonate) carries nothing but the *purification* sentence. The
     prose in the report contradicted the machine-readable summary. Fixed by
     parsing a number out of a `dielectric constant <sep> <value>` clause:
     `with_standard_dielectric_value` is now exactly `[sulfolane, acetonitrile]`,
     `with_narrative_mention_only` is `[ethylene carbonate]`, and
     `without_any_dielectric_evidence` is the expected five.
  2. Repairing (1) introduced a second defect that the same scrutiny caught: the
     first parser read every number in the clause as a dielectric value, so
     acetonitrile's `42.0 at 0 C, 38.8 at 20 C, 26.2 at 81.6 C` was filed as six
     values including the three temperatures. Values and temperatures are now
     stored separately as `measurements: [{value, temperature_C}]`.
  3. The ethylene carbonate citation read "p. 98"; the cached response says
     `p. 989` (with a second citation at p. 990), and the quoted text says "dry
     ethyl ether", not "dry ether". Both corrected; the quote is now verbatim.
  4. Only a 404 may mean "absent". A 429 or 5xx used to be swallowed into
     `inchikey_not_in_pubchem` or an empty identity, so a rate-limit could have
     been filed as a substance that does not exist. Transient codes now raise.
  5. Cached responses carry the URL they came from, so a stale or mis-keyed file
     can no longer be served as evidence for a different request, and a 400/404
     drops the stale cache instead of refreshing around it.
  6. `riddick_reference_count` was an occurrence count that read like a
     distinct-reference count (ethylene carbonate showed 42 occurrences of 2
     distinct pages). Split into `riddick_reference_occurrences` and
     `riddick_distinct_references`. A later audit showed the 42 was itself
     wrong: `iter_sections` yields nested sections, so each citation was counted
     once per ancestor. The count is now taken by walking the payload exactly
     once and is **20 occurrences of 2 distinct pages** (p. 989 and p. 990, ten
     each), covered by a regression test.
  7. `reports/agent_workflow.md` still paired the v0.3.6 hash with "30 patches /
     490 passed" while the artefact records 32 patches and the suite runs 521.
- Export repair: `probes/export_week7_results.py` did not carry any of this
  round's evidence and hard-coded the version label `0.3.3 (v0.3.4 candidate)`.
  Six new source/destination entries are now in `ARTIFACTS` (two findings
  reports, two probe scripts, two evidence JSONs). The label reads `0.3.6` with an
  explicit note that the 246-row set was frozen at v0.3.3, that v0.3.4 fixed the
  `model_ready` fitting gate and that v0.3.5-v0.3.6 revised provenance - no
  dielectric value moved in any of them. `SHA256SUMS` now takes an explicit `\n`,
  as do the week 4-5 and week 6 manifest writers, so every manifest and every
  committed JSON is byte-stable across platforms.
- Regression cover: `tests/test_g1plus_tier1_probes.py` pins the PubChem
  value/narrative/link split, the value-versus-temperature separation and the
  WebBook identity gate on synthetic cached pages, so all of it runs offline.
- Budget: 53 WebBook requests, then 56 PubChem requests to re-verify the whole
  target set under the corrected cache rule. Both passes are inside the 500/hour
  ceiling and both re-run at zero requests, byte-identically.
- **Artifact hashes after the newline repair.** Both evidence JSONs are written
  with an explicit LF because `.gitattributes` normalises `*.json` to LF - a CRLF
  working copy would report a raw sha256 that no clean checkout reproduces.
  `probes/g1plus_pubchem_evidence.json` is
  `9f180a5941fe2fa2eebf067343436c60d6c119894a047787b5ef46977b849c83` and
  `probes/g1plus_nist_webbook_evidence.json` is
  `ff56c4f16cec86fd5328dc147c964d57c1b25afb7c0c92411ef3c95885d1fdd4`, each
  verified LF-only (0 CRLF).
- **Second adversarial round (same two reviewers, repair verification): fail
  again, then repaired.** The reviewers confirmed the repair and found four more
  real defects, two of them introduced or exposed by the repair itself:
  1. The two evidence JSONs were written with a default `write_text`, so on
     Windows they carried CRLF while `.gitattributes` forces `*.json` to LF. Every
     SHA256 the reports pinned was therefore a working-copy hash that no clean
     checkout reproduces. Both writers now take `newline="\n"` and both artefacts
     were regenerated LF-only (0 CRLF).
  2. The hardened clause parser still scanned within a segment, so
     `"32.2 at 298 K"` was read as two values and `"78.4 at 25 C (1 kHz)"` was read
     as `[78.4, 1.0]`. Segments are now parsed whole: a value must be consumed
     exactly, with an optional unit-bearing temperature and an optional
     parenthetical note. A kelvin reading stays kelvin rather than being silently
     converted, and any numeric segment the parser cannot consume whole is
     recorded under `unparsed_clauses` for human review instead of being guessed
     at. Adding that flag immediately paid for itself - it caught a real parse
     failure on acetonitrile's sentence-final period before the artefact shipped.
  3. The `SHA256SUMS` newline fix had only been applied to the week 7 / week 8
     writer; the week 4-5 and week 6 exporters still wrote CRLF manifests, and CI
     runs them on Linux where the difference never shows. Both fixed.
  4. Two prose claims were wrong: the patch layer covers **17** distinct
     InChIKeys, not 15 (32 patch rows over 17 compounds), and this entry itself
     said "four artefacts" where the exporter gained six entries. Both corrected,
     as was an over-broad `dataset_version_note` that described v0.3.4 as a
     provenance-only revision when it actually fixed the `model_ready` gate.
- Final evidence hashes after the newline repair:
  `probes/g1plus_pubchem_evidence.json` =
  `9f180a5941fe2fa2eebf067343436c60d6c119894a047787b5ef46977b849c83` (LF-only,
  `with_standard_dielectric_value` exactly `[sulfolane, acetonitrile]`, zero
  unparsed clauses) and `probes/g1plus_nist_webbook_evidence.json` =
  `ff56c4f16cec86fd5328dc147c964d57c1b25afb7c0c92411ef3c95885d1fdd4` (LF-only).
  `tests/test_g1plus_tier1_probes.py` started this round with 17 offline assertions
(now 18). A further,
  separate round added `tests/test_g1plus_materials_project_probe.py` (6 assertions
initially, now 14) after
  the Materials Project evaluation below, taking the full suite to **553 passed** (further regression tests cover the Riddick occurrence fix and the Materials Project error and cache paths).
- Still open, unchanged: the FEC 78.4/102/107 spread, the VC 126 vs 78-127
  conflict, the gamma-valerolactone 36.1 vs 32 (thesis also 34) conflict, MOPN's
  missing GFN2-xTB row, and the tier-3/tier-4 print and subscription sources.

## 2026-09-24: Materials Project out of scope, CatalystHub unverified

- Both sources were offered as alternatives after the SpringerMaterials interactive view
  became unavailable. "The site would not open" is not a finding about what a database
  holds, so each was checked on its own terms rather than assumed.
- **Materials Project: closed as out of scope.** The API works with the stored key and the
  collection does carry dielectric information - the summary endpoint exposes `e_total`,
  `e_ionic`, `e_electronic` and `n` from DFPT - but it is built from inorganic crystals.
  A positive control (SiO2) returns 322 matching documents with populated `e_total`/`n`,
  while **all 14 G1+ targets return `total_doc = 0`** by molecular formula. The populated
  control is what makes the empty result readable: the key, the endpoint and the field names
  all work, so the negative is about the scope of the collection. Its dielectric tensors are
  computed for solid crystals, which is a different quantity in a different phase from the
  experimental liquid permittivity this dataset records, so no value is imported even if a
  molecular crystal of one of these compounds ever appears.
- **CatalystHub: unverified, not empty.** The key stays in the git-ignored
  `config/catalysthub_key.txt`, but no documented endpoint could be reached: `catalysthub.ai`
  and `www.catalysthub.ai` resolve and then time out over HTTPS, `api.catalysthub.ai` does
  not resolve, and `catalysthub.org` is a different site whose certificate fails validation.
  This is recorded as inaccessible rather than as "no such data", because only the former has
  been demonstrated.
- No dataset impact: `data/dielectric_v03.csv` stays at
  `f5256d164c814030a4b986db6c878f1d64edb2b4f91cf39af3a75ffeaeac853c`.
- Evidence: `probes/g1plus_materials_project_evidence.json` (sha256
  `9f8837b152d6546a904a48364f106897ffa72019f39a74b78ff135b8ef60137a`, LF-only, and asserted
  free of the API key by `tests/test_g1plus_materials_project_probe.py`), write-up
  `reports/g1plus_materials_project_findings.md`.
- Budget: 15 Materials Project API calls (1 control + 14 targets); re-runs cost 0 calls. The
  CatalystHub probing was 5 DNS/HTTPS attempts, not API usage.
- Still open: tier 3-4 for PC / VC / FEC / GVL / MOPN (print Riddick 4th ed., CRC
  "Permittivity of Liquids", Reaxys / SciFinder-n / DIPPR 801), plus the existing FEC, VC and
  GVL conflict tickets.

## 2026-09-24: ECW-308 全表重抽与引文链闭环 (v0.3.7)

- **范围。** 上一轮 tier-2 只按目标分子逐行读了 ECW-308 的 SI，留下两个口子：SI 的
  "Refs." 列是方括号编号，"Hall et al." 无法核验；以及缺少全表交叉验证。本轮把
  Supporting Information 的 Table S3 全部 308 行结构化（本地零 API 调用）。
- **方法。** 纯文本 dump 不可用，原因是可复现的：行是流式的、第 279 行行号没有句点、
  第 167 行行号与名称粘连、部分条目上下堆叠两个数值。改用 pypdf 坐标文本流：列归属由
  表头 x 坐标决定的"介电带"（486.3-559.7 pt）判定，行号必须等于期望的下一个序号
  （1..308），单元格归属于基线在其上方 0-20 pt 的行块。
- **锚点回归 11/11。** v0.3.6 手工读出的 11 个值全部命中，并固化为测试用例
  （`tests/test_g1plus_ecw308_extract.py`，33 项，离线）。抽取覆盖：87 value / 204
  blank / 11 missing / 6 stacked，行号序列完整到达 308，另解出 54 条完整参考文献。
- **引文链闭环。** [3] Hall 2018 JES 165 A2365、[16] Flamme 2017 Green Chem 19 1828、
  [34] Duncan 2013 JES 160 A838、[36] Perricone 2013 Electrochim. Acta 93 1、
  [40] Huang 2019 Adv. Mater. 31 1808393、[42] Deng 2020 Energy Storage Mater. 32 425。
  **VC 的 126.00 引 [3, 16]，即 Hall 2018 + Flamme 2017，不是 Saadi & Lee 1966** ——
  既有 VC 付费墙冲突项属于另一条证据线，不应合并。
- **腈类冲突的根因被解释。** ADN/GLN/PMN 三条 ECW-308 值全部只引 [34] Duncan 2013；
  上一轮对 Duncan 接受稿的核验已确认该表只印整数 30/37/89 且无温度、频率与不确定度。
  ECW-308 的两位小数是二次汇编制造的精度，与数据集一手值（JCED）之间的 5.8-6.9% 差异
  是**来源等级差异**，不是两条独立实验的对立。数据集保留一手值的取舍得到支持。
- **身份门控。** 交叉核对要求分子式一致**且**名称身份成立（去括号全名相同，或命中
  显式同义词表）。只有分子式相同的行记为 `formula_only_candidate`，不计入冲突。这条
  规则排除了初版两个假阳性：甲酸甲酯↔乙酸、甲基丙基碳酸酯↔碳酸二乙酯。
  最终 16 条通过门控：5 条 ≤1%、6 条 ≤5%、5 条分歧。
  **（v0.3.8 修订）** 这组计数基于首版抽取器；对抗审查随后发现两个 Critical 缺陷
  （裸整数回退让表头与化学式下标抢占行号、公式窗口无下界导致 26 行公式丢失），修复后
  权威计数为 **24 条门控：8 条 ≤1%、10 条 ≤5%、6 条分歧**，见 v0.3.8 条目；第二轮审查
  再修三处身份门控缺口与两类抽取缺陷后，**权威计数改为 27 条：11 条 ≤1%、10 条 ≤5%、
  6 条分歧**，见 v0.3.9 条目。
- **FEC 维持开放。** 78.4（引 Deng 2020）vs 数据集 102（开放综述表），−23.1%；两侧
  原文本轮均未取得，不收敛，既有 `public_values_78.4_102_107` 票据不变。
- **未改动数据集。** `data/dielectric_v03.csv` 仍为
  `f5256d164c814030a4b986db6c878f1d64edb2b4f91cf39af3a75ffeaeac853c`；本次是交叉核对，
  没有写入任何介电数值或 `conflict_status`。
- **证据。** `probes/g1plus_ecw308_evidence.json` 与
  `probes/g1plus_ecw308_crosscheck.json`，两份均为纯 LF；**（v0.3.8 修订）** 此处原记的
  `ac890473…` / `a1bed4df…` 两个哈希已随缺陷修复失效，现行哈希见 v0.3.8 条目。
  写于 `reports/g1plus_ecw308_crosscheck.md`。源 SI PDF 哈希固定在脚本内，不匹配即中止。
- **预算。** 0 次外部 API 调用（全部基于已落地的 SI PDF）；`--check` 可验证可复现性。
- **仍然开放。** PC / VC / FEC / GVL / MOPN 的 tier 3-4 实体书与机构库路径；FEC、VC、
  GVL 冲突票据。

## 2026-09-24: 引文链补全、Perricone 论文取证与 GVL 冲突更正 (v0.3.8)

- **ECW-308 编号补上 DOI 与文献类型。** [2] `10.1149/1.2083323`、[3]
  `10.1149/2.1351810jes`、[16] `10.1039/c7gc00252a`、[34] `10.1149/2.088306jes`、
  [36] `10.1016/j.electacta.2013.01.084`、[40] `10.1002/adma.201808393`、[42]
  `10.1016/j.ensm.2020.07.018`。
- **重要限定（防止越界引用）**：[16] Flamme 2017、[40] Huang 2019、[42] Deng 2020 是
  **综述**，不是原始测量。因此 ECW-308 链闭合的是"值 → 引文"，**未**闭合"值 → 一手测量"；
  VC / FEC / diglyme / triglyme 的一手上游仍是开放项。此限定已写入
  `reports/g1plus_ecw308_crosscheck.md`。
- **Perricone 2011 论文全文已取得**（HAL `tel-00630049`，214 页，2,829,426 bytes，
  HTTP 200 application/pdf）。命令行取件经 Anubis 工作量证明后放行（该文件本身是
  openAccess，不是绕过付费墙）；上一轮 tier3"无法读取 PDF 文本"的结论由此取代。
  下载物只留在系统临时目录，未入仓库。
- **MOPN 溯源前移**：论文 Tableau 4（PDF p.41/印刷 p.28，表头 `εr à 25°C`）、
  Tableau 12（PDF p.78）、Tableau 14（PDF p.90）三处均为 **36 @25 °C**。论文只写整数
  **36**，故**不得**据此把它"确认成 36.00"；三张表都是文献汇编表（Tableau 4 引 [43]），
  证据等级仍为二次汇编。MOPN 仍因缺 GFN2-xTB 特征行而 `model_ready=false`。
- **GVL 冲突描述更正（重要）**：手册里"论文内部 36.1 vs 32/34"的说法不成立。论文全文
  检索 `36.1`/`36,1` **无命中**；论文内部实际是 **34 vs 32**（Tableau 4 与 Tableau 14
  给 34、Tableau 8 给 32）。**36.1 来自数据集自引的开放综述表**（Sun et al. 2026,
  *iScience*, `10.1016/j.isci.2026.115778`, Table 3），其一手测量上游未回溯。
  因此这是**跨文献冲突**而非论文内部矛盾；GVL 的 36.1 仍未获任何一手支撑，票据保持开放，
  不适合当作已裁决。
- **tetraglyme 取得独立一手值**：7.816 @298.15 K、**1 MHz**、Agilent 16452A 液池 +
  4294A 阻抗分析仪，来源 arXiv:2402.05989 Table 1（PDF p.16；方法见 p.4）。与数据集
  ThermoML 值 7.798 @298.15 K 相差 **+0.23%**，并补上数据集缺失的频率条件。
  **保留意见**：agent 把该表归到 DOI `10.1016/j.tca.2012.10.024`，但 arXiv↔DOI 的对应
  关系本轮未复核，故在复核前不得写入 `source_doi`。
- **醚/腈族其余项**：diglyme/triglyme 的一手候选 `10.1016/j.jct.2010.09.008` 为 closed；
  adiponitrile 候选 `10.1149/1.3023084` 被 Radware 拦截；glutaronitrile 的 NRC 开放稿
  返回 **HTTP 410**。Europe PMC 检索端点本轮 **HTTP 500**，按纪律记 **blocked 而非
  not_found**。
- **未改动数据集**：MOPN 的 provenance note 属 notes 级变更，会改动
  `data/dielectric_v03.csv` 哈希并牵动多处固定哈希，故留作**独立的 provenance patch**
  （同 v0.3.5/v0.3.6 的做法）；tetraglyme 值待 DOI 复核；GVL 冲突未裁决。数据集哈希仍为
  `f5256d164c814030a4b986db6c878f1d64edb2b4f91cf39af3a75ffeaeac853c`。
- **请求预算（诚实记录）**：Kierkegaard 59/80 未超支；Ramanujan **≥87 次 HTTP + 约 12 次
  文档导航（约 99）**，**超出 80 次预算**，失败/阻断至少 16 次。已取得的题录均经 DOI
  元数据匹配，但下一轮应把预算门控做在工具层而非提示层。
- **写于** `reports/g1plus_perricone2011_thesis_and_gvl.md`。
- **对抗审查（skill: adversarial-review-optimize）与两处 Critical 修复。** 只读审查员用
  独立的 pypdf 扫描（不复用被测解析函数）把 v0.3.7 判为 **FAIL**，抓到两个真缺陷：
  1. `row_starts()` 的裸整数回退过宽——表头 `Category 1` 的 `1` 抢占了第 1 行（第 1 行
     实际丢失），化学式下标 `3/4/9` 抢占了第 3/4/9 行；
  2. `_formula_for()` 的 35 pt 固定窗口没有下界，把**下一行的名称**拼进公式，26 个有值的
     行被误判为 `ecw_no_formula`（Acetonitrile、Diglyme、VC、2-Butanone 全部中招）。
  修法：裸整数回退**钉死到第 279 行**（`BARE_INDEX_ROWS`）；公式窗口改以**下一行行标签为
  下界**。修正后第 1 行恢复 `Formamide`（CH3NO），第 3/4/9 行恢复
  `Dimethyl acetamide`/`N-methylacetamide`/`Urea`，第 38 行恢复公式 `C2H3N`。
- **更正后的权威计数（v0.3.8）。** 无公式行 26 → **4**；门控比较 16 → **24**
  （8 条 ≤1%、10 条 ≤5%、**6 条分歧**）。新增的一致项包括 **VC 126.00 = 126（0%）**、
  Diglyme 7.40 vs 7.3815（+0.3%）、DMF、ACN、1,3-dioxolane、2-butanone；新增的分歧项是
  **i-butyl acetate 5.00 vs 5.29（−5.5%）**。
- **报告笔误一并更正**：首版引文作用表把 Acetonitrile 挂在 `[2]`，实测第 38 行 Refs. 是
  `[34]`；"一致（8 条）"与随后列出的 11 条自相矛盾，现已按 JSON summary 重算。
- **测试强度补强**：锚点断言由"字符串包含"改为**精确相等 + 数值比较**（原断言连
  `137.00` 都能通过），并新增第 1/3/4/9/38/96/163 行的身份回归、以及"游离裸整数不得开行"
  与"公式窗口必须被下一行截断"两项回归测试；测试数 33 → 36。
- **v0.3.8 证据哈希**：evidence `ad1d54346a889926ecca86859248ec4bd37d8afa3a2a0c57de3206e59698ab3d`、
  crosscheck `869c12790b3644bf9ae5ccbbb30bbac31cbe87424a6ea9be4dda9901c5d08326`，均纯 LF。
  **（v0.3.9 已取代）** 这两份哈希随第二轮抽取修复失效，现行哈希见 v0.3.9 条目。


## 2026-09-24: 第二轮对抗审查收口与抽取精度修复 (v0.3.9)

- **审查结论。** 第二轮只读审查员在 v0.3.8 上判 **FAIL（1 Important + 2 Minor，无
  Critical）**。重要项是身份门控不完整：至少还有三条**同一 CID**的同物异名没有进同义词表，
  于是 `matched=24 / formula_only=20` 只是机械计数，不是完整门控。两条次要项分别是第
  279 行名称粘连了行号，以及"无公式"状态里混着两行**公式印在页首**的条目。
- **三条同物异名已补**（PubChem PUG-REST 同 CID 核验）：`n-Butyl acetate`→CID 31272、
  `Dimethyl ketone`→CID 180、`N-methylpyrrolidinone`→CID 13387。三者由
  `formula_only_candidate` 升为 ≤1% 一致（5.00 vs 5.01、20.50 vs 20.7、32.00 vs 32.2）。
- **抽取精度修复（用户要求"数据爬取更准确"，故按根因修而不是改计数）。** 逐行 diff（定义见下）
  证明：有公式的行 **267 → 308**（**+41 由无到有，0 丢失、0 改错**）；**130 行名称**发生变化，
  净增 **2004** 字符（Σ(len(new)−len(old))，含净增 **172** 个印刷连字符）；**除 `name`/`formula`
  外无任何字段变化**。
  1. **固定深度分不开两种行距。** SI 多数页行距 24.6 pt（公式在标签下方 12.1 pt），名称换行的页
     48.7 pt（公式在 36.3 pt）。任何固定 dy 窗口要么读不到、要么把邻行卷进来。改为**取消 dy
     窗口**：公式按**印刷行**聚类，下界是**下一行行标签**。代码里已不保留任何 `FORMULA_*_DY`
     常量（第三轮审查指出旧描述与实现不符，已按实现更正）。第 88/89 行（DFEME/TFEME）恢复
     公式，同类共 +41 行。
  2. **名称续行。** 名称按印刷行拼接，直到公式行为止；续行必须起于名称列（x≤250）。第 88 行由
     `1,1 - Difluoro 2 (2` 还原为完整名称。**第三轮审查发现**此处最初"续行上一律拒绝纯数字
     token"过宽，会把位次号当邻列数值删掉；现只拒绝**带小数点的数值**，第 207 行
     `octane - 3 - one`、第 235 行 `3 - Methoxysulfolane (MESL)`、第 246 行
     `ethyl 2 - methylsulfonylethyl carbonate` 三处已与 PDF 一致。
  3. **跨页条目。** 块边界由"同页 dy 窗口"改为**文档序 `(page, -y)`**，于是印在下一页
     最上方的公式可读：第 43 行（MOPN）恢复 **C4H7NO**、第 116 行恢复 **C5H10O2**，
     `ecw_no_formula` 由 4 → **0**（状态保留为安全网）。
  4. **去重规则。** 旧规则"文本是已拼接串的子串就丢弃"把位次号当重复：`91.` 之后的
     `1` 被删，`Methyl` 之后的 `Me`（2-MeTHF）也被删。现只丢弃**同一坐标**的重复
     token，并对多字符块做词边界判断。
- **修订后的权威计数。** 门控比较 **27 条：11 条 ≤1%、10 条 ≤5%、6 条分歧**；
  `formula_only_candidate` **19**、`dataset_miss` 41、`ecw_no_formula` 0、
  `ambiguous_formula` 0。第 43 行（MOPN）新的状态是 `formula_only_candidate` 而非匹配：
  SI 只印 `Methoxypropionitrile` 没有位次号，而数据集是 `3-methoxypropionitrile`，
  2-位异构体是另一个分子，故**不得**仅凭分子式判等。这条是新增的显式回归测试。
- **未改动数据集。** `data/dielectric_v03.csv` 仍为
  `f5256d164c814030a4b986db6c878f1d64edb2b4f91cf39af3a75ffeaeac853c`。本轮只动交叉
  核对器与它的证据文件。
- **第三轮独立审查（Einstein，只读）。** 对 v0.3.9 判 **FAIL：2 Important + 1 Minor**，三条全部
  成立并已修：(1) 报告的 `+21 / 112 / 66` 三个数字与逐行 diff 不符（实为 +41 行公式、130 行名称、
  净增 172 连字符），且报告声称的"45 pt 上界"在代码里根本不存在；(2) 续行上一律拒绝纯数字 token
  会删掉合法位次号（第 207/235/246 行）；(3) 报告末尾仍固定 v0.3.8 的旧哈希。审查同时确认：
  summary 自洽、第 43/116 行跨页公式成立、三条同物异名 CID 成立、数据集哈希未变、测试与 ruff
  全绿、`--check` 复现为真、两份 JSON 纯 LF。修后门控计数不变（仍是 27 条）。
- **v0.3.9 证据哈希**（第三轮修复后）：evidence `e1425d392cbd3c2390089a75a4168c25bf50100dd2ec456146773f2fb90cd434`、
  crosscheck `35066bc2797c7f0f450f830188917af159fe71d6c11f0bf4df568b7c57ff6366`，均纯 LF。
- **测试强度。** `tests/test_g1plus_ecw308_extract.py` 由 36 项扩到 **48 项**（新增：跨页公式、
  换行行距、名称续行、位次号在续行上存活、小数数值单元格被拒、第 279 行裸标签、三条同物
  异名、以及"没有位次号就只能当候选"）。全仓 `pytest` **601 passed**，`ruff` 干净，抽取器
  `--check` 复现为真。
- **仍然开放（未静默关闭）。** VC `conflict_open`（Saadi & Lee 付费墙，且与 ECW-308 是
  不同证据线）；FEC 78.4/102/107；GVL 36.1 vs 32/34（跨文献）；MOPN 仍 `model_ready=false`
  （无 GFN2-xTB 特征行）；tetraglyme 7.816 的 arXiv↔DOI 对应关系待复核；tier 3-4
  （Riddick 4th ed. 纸质、CRC "Permittivity of Liquids"、Reaxys/SciFinder-n、DIPPR 801）仍受阻。
- **预算。** 本轮 0 次外部 API 调用（全部本地重算）；三条同物异名核验沿用上一轮已取回的
  PubChem 结果。
