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
  record exactly what the thesis does and does not establish. The thesis was
  read as giving no temperature (ECW-308 asserts 25 C) - **（v0.3.10 已更正：
  论文 Tableau 4 与 Tableau 14 明示 25 °C，见下方 v0.3.10 条目）**. It belongs
  to the same research line, so this is **document-level corroboration, not a
  second measurement**: the
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
  Tableau 12（PDF p.78，**无温度列**）、Tableau 14（PDF p.90，**25 °C**）三处均为 **36**（温度由 Tableau 4/14 明示；v0.3.10 更正）。论文只写整数
  **36**，故**不得**据此把它"确认成 36.00"；三张表都是文献汇编表（Tableau 4 引 [43]），
  证据等级仍为二次汇编。MOPN 仍 `model_ready=false`——**（v0.3.10 更正：直接原因是 exclusion 表的“待一次来源确认”，缺 GFN2-xTB 特征行是另一套机制）**。
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
  （待一次来源确认的 exclusion，外加缺 GFN2-xTB 特征行）；tetraglyme 7.816 的 arXiv↔DOI 对应关系待复核；tier 3-4
  （Riddick 4th ed. 纸质、CRC "Permittivity of Liquids"、Reaxys/SciFinder-n、DIPPR 801）仍受阻。
- **预算。** 本轮 0 次外部 API 调用（全部本地重算）；三条同物异名核验沿用上一轮已取回的
  PubChem 结果。
## 2026-09-24（续）：第四轮审查收口 + DC-200/Zenodo 清单核对

- **第四轮独立审查（Einstein，只读）。** 对 `fd60fbf` 判 **FAIL：仅 1 Minor（纯文档）**，
  无 Critical/Important。该条成立并已修：`reports/agent_workflow.md` 第 331 行仍写 “45 pt cap”，
  与同文件第 346 行及代码自相矛盾。现改为“按印刷行聚类（2.5 pt），块边界是下一行行标签，
  无 dy 窗口”，与实现一致。
- **该轮确认通过的部分。** 308 行名称用原始 pypdf token 独立重建：逐字不一致 0、规范化后
  不一致 0；三处哈希与报告固定值一致且纯 LF；`matched 27 = 11 + 10 + 6` 自洽；SI PDF 与数据集
  哈希未变；历史 `matched` 16→24→27 与 export 说明相符；48 项抽取测试、全仓 601 项、ruff、
  `--check` 全绿。
- **DC-200 / Zenodo：把“端点不可达”升级为“清单已核对”。** 首轮探测因 `zenodo.org` DNS
  不可达而无法列出配套记录清单。本次把主机名钉到已解析 IP（`137.138.52.235`）后复核：
  `10.5281/zenodo.21061161` 与 `21061162` 是同一记录（DOI `10.5281/zenodo.21061162`），
  清单为**单个** `GSDS_Prior_Finetune.zip`（4,746,199,417 字节，md5
  `f1736827b1a9f31e85587ca2eae913a7`），描述为 fine-tuning 结果与最终 generators。
  **无逐分子 DC-200 表**，故 10 个目标的 `dc200` 仍全部 `found=false`：结论不变，依据变强。
- **预算。** 该复核为 3 次未认证 HTTP GET（无 API key、不计费），已记入
  `probes/g1plus_tier2_evidence.json` 的 `request_accounting.follow_up_zenodo_manifest_check`。
- **新增开放项。** `www.zenodo.org` 可解析、`zenodo.org` 不可解析，本环境需钉 IP 才能访问
  Zenodo API；不影响结论，但后续任何 Zenodo 复核需同法。
## 2026-09-24（续二）：第五轮审查对 DC-200/Zenodo 证据的收口

- **第五轮独立审查（Einstein，只读）。** 对 `a351304`（第四轮修复）判 **PASS**；对 `7271367`
  （DC-200/Zenodo 证据）判 **FAIL：1 Important + 1 Minor**，两条均成立。Zenodo API 元数据、
  清单（1 个文件、4,746,199,417 字节、md5 `f1736827b1a9f31e85587ca2eae913a7`）、301/302/200
  跳转、10/10 `dc200` 为 `found=false` 全部被独立复现。
- **Important：可用性结论强于证据。** `reports/g1plus_tier2_findings.md` 与
  `reports/v033_provenance_upgrade.md` 曾写成“该 200 分子表未随可访问论文资产发布 / asset not
  published / remains unpublished”。但我们只核对了**清单**，没有下载、更没有解包那个 4.75 GB 的
  `GSDS_Prior_Finetune.zip`，因此只能说“在已取得的论文资产与已核对清单的记录中没有逐分子表”，
  不能断言包内没有该表，也不能断言该资产未发布。三处措辞已按此收紧。
- **Minor：请求记账自相矛盾。** `request_accounting.counting_note` 原写“reaching 39 之后不再有
  请求”，却又新增 3 次 follow-up GET（若 budget=40 为累计则 39+3=42 超预算）。现已把 39/40 明确
  限定为**原始 tier-2 探测运行**，follow-up 单列为独立运行、不占该预算；并向被报告的逐次审计日志
  `data/external/g1plus/compilations/_request_log.jsonl` 补写 R1-R3 三行（该文件被 .gitignore 忽略，
  仅作本地审计）。
- **仍然开放。** 4.75 GB 归档内部内容未核（未下载）；DC-200 逐分子表仍**未定位**，不是“不存在”。
- **预算。** 本轮修复 0 次外部 API 调用。

## 2026-09-24（续三）：MOPN 温度取证更正 + DC-200 归因收紧 (v0.3.10)

- **触发。** 用户要求“数据爬取更准确”，主线程据此逐字重读本地缓存的 Perricone 2011 论文抽取
  文本，发现 v0.3.5 的一条结论有事实错误；同时派两个只读 agent 分别独立复核该结论与
  DC-200 的归因。
- **Important（已修）：MOPN 的“论文未给温度”是错的。**
  `data/dielectric_v03.csv` 中 `OOWFYDWAMOKVSF-UHFFFAOYSA-N`（3-甲氧基丙腈）的 notes 原写
  “The thesis states no temperature”，该判断来自**只读了 Tableau 12**。原文逐字复核结果是：
  **Tableau 4**（印刷页 28）介电列表头为 `εr à 25°C`，MOPN 行为
  `Méthoxypropionitrile [43] - 57 165 66 1,1 36`，无逐格温度覆盖；
  **Tableau 14**（印刷页 77，转置矩阵）属性行为 `Constante diélectrique à 25°C`，`MP` 列 = 36；
  **Tableau 12**（印刷页 65）确无温度列——旧结论只对这一张表成立。Tableau 14 同行其余三格可
  锚定列对齐：sulfolane 43(30 °C)、PC 64,4、EC 90。因此温度改为 **25 °C**；**证据等级仍为
  二次汇编**（该论文与 2013 年论文同属一条研究线，不是第二次测量），`model_ready=false` 的
  **直接**原因是 exclusion 表的“待一次来源确认”（`data/processed/dielectric_v03_exclusions.csv`），
  **不是**缺特征行——缺特征行是**独立前置条件**（MOPN 根本不在特征表里，**不属于** `failed_physical_feature_*`
  桶，该桶只统计已存在且 `status=error` 的行），但它同样是真实阻塞项。这与
  `reports/g1plus_perricone2011_thesis_and_gvl.md` 第三节早已记录的 Tableau 4/14 表头一致——
  那份报告本来就是对的，是 v0.3.5 的 notes 与 probe 与之矛盾。
- **同步修复的产物（6 处）。** `data/processed/dielectric_v03_provenance_patches.csv` 第 21 行
  notes（就地改写，非追加）、`probes/g1plus_mopn_thesis_evidence.json`
  （`temperature_stated_in_source`、`evidence_level`、`model_ready`，并新增 `correction` 字段）、
  `probes/g1plus_perricone_thesis_crosscheck.json`（verdict 改为
  `value_and_temperature_corroborated`，并记录 Tableau 14 给出 GVL=34、使该论文自相矛盾更明确）、
  `reports/g1plus_mopn_thesis_findings.md`（原 “What is still missing / The temperature” 一节重写为
  “The temperature (corrected in v0.3.10)”）、`reports/g1plus_perricone_thesis_crosscheck.md`
  （交叉核对表 MOPN 行与表列覆盖范围）、`probes/export_week7_results.py`
  （`tier3_finding` 与 `open_items` 文案）。
- **Important（已修）：DC-200 的归因站不住脚。** 仓库两处（`probes/g1plus_tier2_evidence.json` 的
  `paper_text`、`reports/g1plus_tier2_findings.md` 第 4 条）把 DC-200 的组装来源写成
  “He et al. 2025 (`10.1063/5.0267184`) 与 MNSOL 2012”。只读 agent（Mendel，3 次 HTTP）核验：
  该 DOI 是 He et al., *J. Chem. Phys.* 2025, 162, 194706，研究**纳米限域下 EC 基二元混合体系**
  的**分子动力学**论文、闭源，**不是** 200 溶剂实验汇编；且在 GSDS 全文 XML 中该 DOI **只出现在
  参考文献列表**（ref82，紧邻 ref83 = MNSOL 2012），正文出现 **0** 次。全文
  `ref-type="bibr"` 的 xref 数为 **0**（PMC 转换丢弃了全部角标），ACS 原文返回 HTTP 403，故该句
  实际引文**不可判定**。两处措辞已收紧为“不可判定”，并明确 ref82 不应被表述为 DC-200 的
  实验数据来源；**“SI / GitHub / Zenodo 已核对清单中均无逐分子 DC-200 表”这一结论一字未弱化**，
  4.75 GB 归档未解包的限制保留。
- **附带的取证口径澄清。** `probes/g1plus_mopn_thesis_evidence.json` 的
  `extracted_text_sha256` 记录的是 **LF 归一化后的文本内容哈希**（`dc2272fe…`）；工作区
  `.txt` 因 Windows 换行存为 CRLF，其原始字节哈希是 `d48e684c…`，两者并不矛盾。probe 已新增
  `extracted_text_sha256_convention` 写明该口径。
- **哈希与连带钉点。** `data/dielectric_v03.csv` 由 `f5256d164c814030a4b986db6c878f1d64edb2b4f91cf39af3a75ffeaeac853c` 变为 `57387b98f899c6c0eff12716cc5b754f65d2ee0edd5523330af049ddded26fab`（仅 1 行
  notes 变化）。已同步：`probes/dielectric_v03_summary.json`（构建脚本重写）、
  `probes/v032_ablation_summary.json`、`probes/dielectric_v03_representation_ablation_summary.json`、
  `tests/test_build_dielectric_v03.py`、`tests/test_verify_v032_benchmarks.py`、
  `reports/agent_workflow.md`、`reports/v033_provenance_upgrade.md`、
  `reports/week7_dataset_expansion_and_freeze.md`、`reports/g1plus_materials_project_findings.md`、
  `reports/g1plus_perricone2011_thesis_and_gvl.md`。`reports/decisions_log.md` 内历史版本章节（v0.3.6-v0.3.9）的旧哈希按惯例**原样保留**、不逐处加注，其取代关系由本节统一声明；其余报告文件中作为“现行钉点”出现的旧哈希已就地标注“已被 v0.3.10 取代”。
- **未变的部分（复核过，不是假设）。** 两个 ablation 的 236 行拟合集、27 项 summary 均值与标准差、
  `model_ready` 门控、conflict 状态均未变；`scripts/verify_v032_benchmarks.py` 重跑后仅两个
  `dataset_sha256` 钉点失配，其余 24 项（含 “all 27 summary means and standard deviations
  reproduced”）全部通过——这正是“只改 notes”的机器证据。
- **对抗性审查（第六轮，独立只读审查员）。** 对本次未提交 diff 判 **FAIL：1 Important + 3 Minor，无 Critical**，
  四条全部成立并已修：(1) **Important**——我把 `model_ready=false` 的“唯一理由”写成缺 GFN2 特征行，
  但机制上直接原因是 exclusion 表的“待一次来源确认”（`scripts/build_dielectric_v03.py` 只依据
  exclusion 集合设 `model_ready=false`，见 `reports/v034_model_ready_gate.md`），缺特征是独立前置条件
  （其归因在第七轮被进一步纠正）；现已在 notes、两个 probe、两份报告、测试与本节统一改正为“两个独立阻塞项”。
  (2) `probes/export_week7_results.py` 的 `dataset_version` 仍写 0.3.9，已升为 0.3.10 并补版本说明。
  (3) 本节原称历史条目旧哈希“就地标注”，与 `decisions_log` 内 6 处未加注的事实不符，已按实际改写。
  (4) MOPN 的两个 probe 字段此前无回归测试，已新增
  `test_mopn_thesis_probes_record_the_corrected_temperature`。审查员同时独立复核通过：数据集字段级 diff
  （246 行仅 1 行 `notes` 变）、现行哈希钉点、Perricone 三处原文（含字符偏移）、以及 DC-200 收紧未削弱结论。
- **第七轮复审（同一位独立只读审查员）。** 仍判 **FAIL：2 Important + 2 Minor**，四条全部成立并已修：
  (1) 我把缺特征行归入 `failed_physical_feature_*`，但该桶只统计**已存在于特征表且 `status=error`**
  的行（`probes/dielectric_representation_ablation.py` 的 `successful/failed` 划分），而 MOPN **根本不在**
  `data/processed/dielectric_physical_features_v03.csv` 里，故它是**独立前置条件、不属于该桶**；
  已在 notes / 两个 probe / 报告 / 测试中改正。
  (2) `reports/v034_model_ready_gate.md` 与 `reports/agent_workflow.md` 各有一处把 `f5256d…` 称作
  "the current revision"，已更新为当前值 `57387b98…`。
  (3) 新增的 `extracted_text_sha256_convention` 断言原本只查键是否存在，已加强为对 CRLF/LF 口径与
  两个哈希值的实质性断言。
  (4) 测试里 `assert "failed_physical_feature_*" in notes` 固化了错误归因，已随第 (1) 条改写。
- **仍然开放（未静默关闭）。** VC `conflict_open`（Saadi & Lee 1966 付费墙）；FEC
  78.4/102/107；GVL 36.1 vs 32/34（同一论文 Tableau 8=32、Tableau 14=34，跨文献未裁决）；
  tetraglyme 7.816 的 arXiv↔DOI 对应关系待复核；tier 3-4（Riddick 4th ed.、CRC
  “Permittivity of Liquids”、Reaxys/SciFinder-n、DIPPR 801）仍受阻；DC-200 逐分子表仍未定位；
  4.75 GB `GSDS_Prior_Finetune.zip` 未下载未解包。
- **预算。** 本轮外部调用共 3 次（Crossref 1 / OpenAlex 1 / ACS 403 探测 1），其余全部为本地
  重算，远低于每小时 500 次上限。

## 2026-09-24（续四）：附录 I/J 名册对账——三种 glyme 与戊二腈是假阴性，不是缺口

- **决定。** 不再把「diglyme/triglyme/tetraglyme 与 glutaronitrile 缺席」当作补录任务或
  v1.0 冻结理由；同时确认附录 I §A 的另外三条（PC、EC、MOPN 缺席）是**真缺口且已闭合**。
- **触发原因。** 附录 I §A 第 1 条把五个分子列为"三版本全部缺席"，但附录 J 的回执（第 0 梯队）
  又写明三种 glyme 在本地 ThermoML 里有 298.15 K 观测。同一份手册内部自相矛盾，且在派发任务前
  我用俗名（"glyme"）检索名册时也复现了同一个假阴性，因此决定用 InChIKey 口径整条重算。
- **证据（可复算）。** 新探针 `probes/manual_appendix_reconciliation.py` 对
  v0.1 / v0.2 / v0.3.1 / v0.3.2 / v0.3 五个冻结版本按 InChIKey 重算 6 条子断言：
  - 成立且已闭合 4 条：PC（v0.1–v0.3.1 缺席，v0.3.2 加入）、EC（同上）、
    `extended_temperature` 扩展带（v0.3.1 为 0 行 → v0.3.2 起 1 行）、MOPN（v0.3.2 前缺席，
    v0.3 加入且维持 `model_ready=false`）；
  - **假阴性 2 条**：三种 glyme 与 glutaronitrile（adiponitrile 同理）**自 v0.1 起就在库**。
    库内存储名为 `2,5,8-trioxanonane` / `2,5,8,11-tetraoxadodecane` /
    `2,5,8,11,14-pentaoxapentadecane` / `hexanedinitrile` / `pentanedinitrile`，
    与文献俗名**零 token 重叠**，故任何按俗名或按错误 InChIKey 的检索都必然落空。
  - 同类错误此前已发生过一次：`probes/g1plus_tier0_evidence.json` 的
    `method.incorrect_prior_keys_not_used` 记录过 triglyme 的错键 `YFNKIDBQEZHQBU-…`
    与 tetraglyme 的错键 `LNWVAMHESCFODF-…`。错键检索与俗名检索的失败模式完全相同，
    都会给出一个自信的"缺席"。
- **产物。** `reports/manual_appendix_reconciliation.md`、
  `probes/manual_appendix_reconciliation.json`（schema `manual_appendix_reconciliation/v1`）、
  `data/reference/dielectric_molecule_aliases.csv`（23 分子 / 87 别名，含存储名、文献俗名、
  缩写与系统同义词）、`tests/test_manual_appendix_reconciliation.py`（13 项）。
- **防复发装置（这是本条的主要价值）。** 注册表以**数据集为权威**校验存储名；探针逐分子报告
  "按俗名检索是否会命中"，并给出恰好 5 个 token 不相交的分子；回归测试在三类回归上失败：
  任何 glyme/dinitrile 离开任一版本、注册表与存储名漂移、**或工作手册重新出现被推翻的断言**。
  最后一条已实际生效：测试先在手册上判 FAIL（第 336 行三处过期句），修正手册后才转绿。
- **手册同步。** `执行手册_探针与周计划.md` 第 336/337/357 行已就地更正（保留原判文字 +
  `【已对账更正】` 标记）：① 三种 glyme 与 glutaronitrile 假阴性；② 适用域修复的原拟方案
  （Onsager ε>60 + HBD≥1）**已被实测否决**（ε>60 覆盖率 0/150），实际采用结构给体判据；
  ③ 两项一票否决均已闭合，冻结前真正的剩余项改为 VC/FEC/MOPN 与 tier 3–4 权限阻断。
  备份 `执行手册_探针与周计划.md.bak-20260924-recon`。
- **未变的部分（复核过，不是假设）。** 无任何 `dielectric`、`T_K`、`evidence_level`、
  `model_ready`、`conflict_status` 或数据集字节变化；`data/dielectric_v03.csv` 仍为
  246 行 × 38 列，canonical SHA-256 仍为
  `57387b98f899c6c0eff12716cc5b754f65d2ee0edd5523330af049ddded26fab`。
  这是溯源与 QA 更正，不是数据修订。
- **诚实边界。** `name_search_would_miss` 是注册别名上的**有界词法**启发式：仅当俗名为存储名
  字符串的子串，或双方共享一个 ≥4 字符且**不在通用词禁用表**（methyl/carbonate/sulfone 等）中的 token 时，
  才判为可检索；未注册俗名时记 `null`（无法判断），不默认为 miss。它对底层测量正确性不发言。
- **预算。** 本轮外部调用 **0 次**（全部为本地重算），未触碰每小时 500 次上限。

## 2026-09-24（续五）：G1+ 第二轮爬取——三条"新增值"全部被本地核实否决

- **决定。** 本轮三个只读 agent 的爬取结果**一条都不入库**：三条看似新增的静态值各自因
  不同原因不成立，另有两条经核实只是佐证。数据集保持 246 行不变。
- **并行编排与预算。** 三个只读 agent（Kant = VC/FEC；Averroes = 砜/亚砜/氢氟醚；
  Aquinas = 腈/碳酸酯/氟化酯）共 **39 次外部 HTTP 调用**（12/15/12），远低于每小时 500 次上限；
  两次 OpenAlex 返回 429，未做重试风暴。**所有 agent 声称的引文在采纳前都回到本地缓存复核过。**
- **被否决的三条（每条都会以不同方式污染数据集）。**
  1. **isobutyronitrile 20.4 @ 297.15 K（NBS 514 p20:009）**——转写行同时带
     `f=3.6x10^8 cycles/sec`（360 MHz 频散区）。**真正起作用的规则是 NBS 导入规则，不是全项目
     zero-frequency 契约**：`scripts/resolve_nbs514_structures.py` 对任何非空 `frequency_note` 记
     `frequency_dependent` 排除，`scripts/build_dielectric_v02.py` 拒绝导入此类行；而 schema 本身
     允许**显式论证的 `static_low_frequency`**（EC 的 1 MHz 测量即由此进主表，见
     `docs/week3/manual_dielectric_entry_schema.md`）。实测：**127/127 带微波频率标注的转写行
     全部不在数据集中**，而数据集内 **110 条** NBS 继承行带 `zero_frequency` 门旗；同页
     `p20:008` butyronitrile 正是先例（未采用 20.3 @ 294.15 K，改用独立 primary 22.0 @ 298.15 K）。
     产物 `probes/nbs514_frequency_gate_audit.json` / `reports/nbs514_frequency_gate_audit.md`。
  2. **methyl trifluoromethyl ether 9.28 @ 302.8 K（ThermoML `10.1021/je7000446`）**——
     本地 XML 显示，**9.28 系列所属的 compound 1 是 `C2H3F3` / `UJPMYEOUBPIPHQ-UHFFFAOYSA-N` /
     "1,1,1-trifluoroethane, CFC 143A, Freon 143a, R-143a"**，即不含氧的 HFC，与标题所称的醚
     （HFE 143a 应含氧）不是同一物质；且记录自述条件为 **1.5–31.6 MPa、303–383 K**，近 303 K 的
     14 行压力从 1.6 MPa（9.28）到 30.7 MPa（10.51），**没有任何常压值**。身份与条件各自独立致命；
     数据集没有压力列，压缩液测量不是常压静态介电常数。同一 XML 另有 **compound 2 = `C3H3F5O` /
     `GCDWNCOAODIANN-UHFFFAOYSA-N`（methyl pentafluoroethyl ether）**，但 9.28 系列不属于它。
     身份冲突在**上游 NIST 沉积**，本地抽取器
     忠实转写了它。`modern:024` 维持 restricted-only。
  3. **其余 19 个候选（succinonitrile、cyclopentanecarbonitrile、7 个砜/亚砜、10 个氢氟醚）**——
     本预算内未找到开放一次来源，**全部保留具名 primary 线索**（Nakazawa 2001、Marchionni 1999、
     Casteel 1974、Kolosnitsyn 1991、Egorov 1978、Markarian 2011 等），**一条都没有写成"无数据"**。
- **两条佐证（不构成数据变更）。** ① propanenitrile：NBS 514 `p17:014` = 27.2 @ 293.15 K，
  与库内同一 record_id 的行完全一致（但 NBS 未列 Vuks，不能证明同一次测量）；
  ② FEC 78.40 段：ECW-308 补充材料第 5879 行逐字复核为
  `C3H3FO3 17.30 210.00/249.50 4.10 78.40 5.00 130.00 [16, 42]`，其上游 relay 现已具名
  （[16] Flamme 等、[42] Deng 等 `Energy Storage Materials`），但上游表格仍未取得，故该段仍是汇编转引。
- **仍未闭环（未静默关闭）。** VC 维持 `conflict_open`：1966 摘要只有"已测量"而无数值、温度、
  表号与位数，Semantic Scholar 标记 PDF 为 CLOSED，NBS 514 未收录该物质——属**出版商访问阻断**，
  不是"查无此值"，也未升级为 primary。FEC 维持 `model_ready=false`：78.4/107 两段已有具名 relay，
  102 段被 agent 报为转引 Xie et al. 2023（`10.1002/anie.202216934`）**但未经本地缓存复核**，
  且无证据表明其为原始测量；三个值条件不明或各自名义 25 °C，不构成同条件比较。
- **产物。** `probes/g1plus_crawl_round2_evidence.json`、
  `reports/g1plus_crawl_round2_findings.md`、`reports/nbs514_frequency_gate_audit.md`、
  `probes/nbs514_frequency_gate_audit.py`、`tests/test_g1plus_crawl_round2.py`、
  `tests/test_nbs514_frequency_gate_audit.py`。
- **未变的部分（复核过，不是假设）。** 数据集仍 246 行 × 38 列，canonical SHA-256 仍为
  `57387b98f899c6c0eff12716cc5b754f65d2ee0edd5523330af049ddded26fab`；
  无任何数值、温度、证据等级、`model_ready` 门控或冲突状态变化。本轮的产出是**裁定**：
  三条各自会以"频散测量 / 错配化合物 / 压缩液条件"污染数据集，现已连理由一起留档。
- **审查收口。** 本轮提交包经对抗式复审（Hubble）两轮检查：首轮 4 Important + 4 Minor
  全部修复；差异复审 **PASS（Critical 0 / Important 0）**。收口门禁为全量 `pytest` **640 passed**、
  `ruff check .` **All checks passed**；数据集 canonical SHA-256 仍为
  `57387b98f899c6c0eff12716cc5b754f65d2ee0edd5523330af049ddded26fab`。

## 2026-09-24（续六）：Week 8 分析封版——C1/C2/C4/C6 四探针 + Tier-0 独立复核

- **决定。** 附录 B 的 Week 8 封版清单 C1/C2/C4/C6 四项全部完成并各自封版；
  C5（xTB ALPB 溶剂相 μ）按手册原议继续搁置。四项都**没有改动** `data/dielectric_v03.csv`：
  canonical SHA-256 仍为 `57387b98f899c6c0eff12716cc5b754f65d2ee0edd5523330af049ddded26fab`（246 行 × 38 列）。
- **编排与预算。** 本轮的并行结构是「3 个只读审查 + 2 个独立写集实现 + 主线程唯一数据写者」：
  Hilbert（C1 审计）、Hume（C2/C4 审计）、Mencius（C6 审计）三名只读；
  Jason（C2 实现）与 Galileo（C4 实现）写集互不重叠；主线程负责 C1、C6、Tier-0 复核与全部合并。
  **本轮外部 HTTP 调用 0 次**（NBS PDF 早已缓存并核对过 SHA-256），远低于每小时 500 次上限。
- **C1 分裂共形——第一版方法学错误，已推翻重做。** 初版把不同 fold 的 OOF 残差池化成一个全局分位数，
  **不是标准分裂共形**：每个 `(repeat, fold)` 来自不同训练集与不同 XGBoost seed，跨 fold 残差不满足交换性。
  修正后的协议：每个随机 split 对全部 234 个化合物做一次**全局**校准/测试划分（角色只由 `seed + split_id` 决定，
  跨 representation/arm/repeat 保持一致），再在**每个冻结 fold 内部**单独估分位数、单独测覆盖，**绝不跨格池化**。
  规则 `k = ceil((m+1)*0.9)`，`m >= 9` 才有限。结果：六个系列边际覆盖 **0.9138–0.9156**（名义 0.90），
  无穷区间率 **全 0**，平均区间宽 38.4–45.4。
  **必须保留的负结果**：`ε > 60` 分层（仅 5 个化合物）条件覆盖崩到 **0.015–0.257**（归一化后 0.18–0.51）。
  边际覆盖合格 ≠ 条件覆盖合格，此点写入 JSON 的 `honest_boundary` 并由回归测试锁定。
- **C2 rank:pairwise——干净负结果。** qid 用仓库既有的 Murcko/Butina 结构分组规则（只读 SMILES），
  234 行 → **111 qid、76 单例、799 对 query 内 pair**；负对照 `qid=InChIKey` 时 234 个 query 全单例、
  50/50 个 split 的 rank 输出为常数分，训练目标完全退化。主实验在 qid 层跑 5×10×42，
  两个头使用**完全相同**的 train/test 行索引。10-repeat 均值：macro pairwise accuracy
  **0.7314（rank） vs 0.8011（回归）**、global Spearman **0.7062 vs 0.7888**、
  等校准 isotonic 后 MAE **8.61 vs 7.37**。配对差值 CI：Spearman `[-0.1462, -0.0187]`（不含 0，回归更好）、
  校准 MAE `[+0.4512, +2.2081]`（不含 0，rank 更差）。判定 `no_established_rank_pairwise_advantage`；
  筛选继续用回归头排序。另修正审计口误：50 个 split 的**全局**最低 pair capacity 是 **173**，不是 277。
- **C4 Onsager 残差 delta——机理层 go，但不升级为预测器。** 四参数原函数
  `onsager_dielectric_estimate(mu, Vm, alpha, T)`；`delta = ε - g`；特征分闭包 A（Onsager 输入）
  与 B_core，断言 `A ∩ delta_features = ∅`，D3_leaky 作为显式泄漏诊断。O0 复现审计值
  （总体 MAE 10.49、给体 16.66 / bias +13.84、离子 41.22 / bias −34.25）。
  headline D1 在**点估计**上过全部预注册闸门（总体 8.54 < O1 9.41；给体 12.14 < 16.66；
  离子 34.13 ≤ 41.22；ε>60 的 MAE 87.02 → 75.96），但**仍打不过直接 Morgan+Physical 回归（8.54 vs 6.36）**，
  且对 O1 的优势 CI 含 0（`[-1.744, +0.011]`）。因此
  `learned_delta_layer_confirmed = true`（仅机理披露）、`onsager_promoted_to_standalone_predictor = false`。
  保留负结果：ε>60 域 Onsager 命中 **0/5**（五个化合物全部严重低估，stratum bias +69.96）；
  D3_leaky（7.22）点估计胜过所有确认臂，说明部分增益来自重复使用物理输入而非缔合修正。
- **C6 NBS 温度调和——符号被实证纠正。** 从 NBS Circular 514 原 PDF（印刷页 III–IV，
  SHA-256 `cb3fa923…`）确认 `a = -dε/dt`、`alpha = -d log10(ε)/dt`，两分支**同向**，
  指数取值必须是 `(T - 298.15)`。**此前工作笔记里对数分支的符号是写反的**，并被
  `tests/test_nbs514_alpha_harmonization_probe.py` 的手算锚点锁死。
  内证三点：① 同表双温度对照 4 对，平均相对误差 **0.21%**、最大 0.56%（另一符号约定会差 2–5%，差一个数量级）；
  ② 188 条带系数行中 182 条隐含斜率 `dε/dt < 0`（正常液体应如此）；③ 严格 zero-frequency 同结构 ThermoML
  对照 **0 条**。可修正性分解与 Mencius 独立审计**逐项一致**：110 条 NBS 行 = 68 无系数 + 17 已在 298.15 K +
  **15 严格可修正** + 10 有效温区不含 25 °C。严格可修正行的中位位移仅 **0.011**、均值 0.248（最大 2.5），
  即温度窗是真实但**次要**的限制。另标记 2 条负系数记录（三氟乙酸 `a=-0.5`、丁酸 `a=-0.0023`）：
  原表即为负号，属**忠实转录**，单独标记待人工复核、不静默调和。
  放宽到「纯液 + 近常压 + 频率 ≤ 3 MHz + 观测落在 NBS 有效温区内」得 18 对代理对照（5 个化合物）：
  MAE 0.375 → 0.232、RMSE 0.733 → 0.368，但仅 6/18 单独改善，按**混合风险信号**报告，不写成验证通过。
- **Tier-0 独立复核（本地 ThermoML 覆盖）。** 用 242 份 XML 的**独立文本 grep** + 抽取表组件级重数，
  复核「PC/EC 本地无介电数据」这一承重结论。结果：PC **26 份 XML 提及但 0 份含任何 permittivity/dielectric 措辞**、
  抽取表 0 行；EC 11/0/0；VC 与 FEC 完全不在本地语料；MOPN 1 份无介电措辞。
  反面：diglyme **9 条纯组分**、triglyme **15 条**、tetraglyme **11 条**、adiponitrile **31 条**、
  glutaronitrile **31 条**——这些「升级」根本不需要新爬取，本来就在缓存里。
  因此把此前的措辞从「未找到」收窄为更准确、也更强的表述：**PC/EC 只作为非介电研究的混合物组分出现，
  再爬同一语料不会有帮助**。同时修正一处口径错误：adiponitrile 的正确 InChIKey 是
  `BTGRAWJCKBQKAO-UHFFFAOYSA-N`（此前临时 grep 用的 `BTGRAWLCACVEDO-…` 是错的，会伪造出第二次"缺失"）。
- **未变的部分（复核过，不是假设）。** `data/dielectric_v03.csv` 仍 246 行 × 38 列、canonical SHA-256 未变；
  无任何数值、温度、证据等级、`model_ready` 门控或冲突状态变化。vc/FEC/MOPN 的 v1.0 闸门**仍未闭环**，
  本轮没有、也不应擅自打 tag。
- **产物。** 探针 `probes/dielectric_split_conformal_probe.py`、`probes/dielectric_ranking_head_probe.py`、
  `probes/dielectric_onsager_delta_probe.py`、`probes/nbs514_alpha_harmonization_probe.py`、
  `probes/thermoml_local_coverage_probe.py`；报告 `reports/week8_c1_split_conformal.md`、
  `reports/week8_c2_ranking_head.md`、`reports/week8_c4_onsager_delta.md`、
  `reports/week8_c6_nbs_alpha_harmonization.md`、`reports/thermoml_local_coverage_audit.md`；
  测试 `tests/test_dielectric_split_conformal_probe.py`（13）、`tests/test_dielectric_ranking_head_probe.py`（7）、
  `tests/test_dielectric_onsager_delta_probe.py`（17）、`tests/test_nbs514_alpha_harmonization_probe.py`（20）、
  `tests/test_thermoml_local_coverage_probe.py`（6）。
- **导出。** `probes/export_week8_results.py` 的 `ARTIFACTS` 与 `week8_summary.json` 已登记
  `c1_split_conformal` / `c2_ranking_head` / `c4_onsager_delta` / `c6_nbs_alpha_harmonization` /
  `thermoml_local_coverage` 五个摘要块；新增的 `data/processed` CSV 已加入 `.gitignore` 白名单。

## 2026-09-24（续七）：Week 8 对抗复审收口（I1/I2/I3）+ G1+ 第三轮爬取

### A. 对抗复审（Boyle，只读）的三项 Important 修复

复审判定：**无 Critical，3 项 Important，2 项 Minor**。Important 全部修复，Minor 全部修掉，未扩张范围。

- **I1（口径冲突）C1 的 repeat 级 t 区间被误当作置信区间。** 该区间是十个 repeat 均值的
  mean +/- t_{0.975,9} * s / sqrt(10)，而 repeat 复用同一批 234 个化合物、并非独立样本，
  同一份 summary 里又写着 repeat_treated_as_independent = false。修复：字段从 `coverage.ci95`
  改名为 `coverage.repeat_dispersion_interval`，`_aggregate` 补文档字符串，summary 新增
  `repeat_dispersion_interval_note` 明示「描述性离散度，不是抽样置信区间，抽样区间需要化合物级
  bootstrap 且本探针不做此声明」，报告表头由「95% CI (repeat level)」改为「Repeat dispersion
  (descriptive)」并加一段说明。**点估计与覆盖度数值一个都没变。**
- **I2（非法 JSON）`probes/dielectric_ranking_head_summary.json` 含裸 `NaN`，严格 JSON 解析器拒收。**
  修复：五个新探针各自新增 `_json_ready`（非有限浮点递归转 `null`）与 `write_json_lf`，写盘统一走
  `allow_nan=False`。修复后**全部 62 份 JSON 产物严格解析通过**。C2 里新出现的 58 个 `null`
  全部落在退化负对照（`inchikey_singleton_negative_control` 37 个 + `results.negative_control_arm_results`
  21 个），即每个 InChIKey 都是单例、rank 输出常数分、Spearman 与 pairwise 指标**在数学上未定义**的
  那一格；主口径 `scaffold_butina_qid` 一个 `null` 也没有。这属于「未定义」而非「缺失」，不是把数字抹掉。
- **I3（成果包陈旧）Week8 输出包仍是旧版，且有 4 个被 summary 引用的 CSV 未登记。**
  修复：`probes/export_week8_results.py` 的 ARTIFACTS 补入
  `dielectric_ranking_head_predictions.csv`、`dielectric_ranking_head_qid_audit.csv`、
  `dielectric_onsager_delta_predictions.csv`、`dielectric_onsager_delta_failure_cases.csv`，
  并把导出的 `coverage_ci95` 键同步改名为 `coverage_repeat_dispersion_interval`。
- **Minor 1**：`tests/test_dielectric_split_conformal_probe.py` 里 `assert not np.any(first & ~first)`
  是恒真断言。改为按文档化的规则独立重推期望掩码（`np.random.default_rng(1234).permutation(234)[:117]`）
  并显式校验两个角色构成划分。
- **Minor 2**：`reports/week8_c6_nbs_alpha_harmonization.md` 把 ThermoML 重叠扫描范围误写为
  「ten target keys」，改为「**110 frozen NBS keys**（不只是 10 个 G1+ 目标分子）」。

**超出复审清单的一项自纠：**本轮五个新探针原先都用 `Path.write_text` 落盘，在 Windows 上会被翻译成
CRLF，而仓库 `.gitattributes` 规定 `*.json text eol=lf`、旧证据文件也都是纯 LF。同一脚本在 Linux 上会产出
不同字节，属于跨平台不可复现。修复：五个探针统一改走 `write_json_lf`（显式 `newline=""`）。
重生成后五份 summary 的 CRLF 计数全部为 0。

**重生成后的数值复核（均与封版一致）：**C1 六系列边际覆盖 0.9138-0.9156、无限区间率 0；
C4 O0 = 10.488 / O1 = 9.411 / R0 = 6.357 / D1 = 8.539 / D2 = 12.851 / D3_leaky = 7.220，decision 仍为 go（仅残差层）；
C6 与 Tier-0 结论不变。五个证据产物重生成后 `data/dielectric_v03.csv` 仍为 246 行、
SHA-256 `57387b98f899c6c0eff12716cc5b754f65d2ee0edd5523330af049ddded26fab`。

### B. G1+ 第三轮爬取：三张开放票据（三名只读研究者 + 主线程本地复核）

证据 `probes/g1plus_crawl_round3_evidence.json`，写于 `reports/g1plus_crawl_round3_findings.md`。
**本轮没有新增任何可入数据集的原始测量值，数据集一个字节未动。**

- **FEC：存量 102 是闪点，量纲错误（本轮最重要发现）。** Luo et al. 2021（Adv. Sci. 8, 2101051，
  DOI 10.1002/advs.202101051）同一行的列序为 Tm / Tb / 粘度 / **Dielectric constant eps** /
  **Flash point Tf** / 密度 = 20 / 210 / 3.33 / **78.4** / **102** / 1.45 —— 78.4 在介电列，102 在闪点列。
  ECW-308 Table S3 自己给的是 78.40（主线程在本地缓存第 5876-5879 行复核），Deng et al. 2020 全文已读且
  **不含 78.4**，Ue et al. 2014 Table 2.3 给 107（汇编）。结论：冲突单应改述为「78.4 vs 107 双腿，102 属量纲错误」，
  且两条腿都是名义 25 °C、无频率的二次来源，不得解释成温度或频率依赖。
- **VC：126（整数，名义 25 °C）在两张互不相同的综述级表格里都被印为整数，但两表独立性未确立，且仍无原始测量。** Hall et al. 2018 的
  表是 **Table II**（更正此前 Table I 的记法），Vali et al. 2016 开放论文 Table I 的 VC 行给 126 并在表注写明
  25 °C；Souid et al. 2025 的「126 at 298 K」其 [29] 就是 Vali 2016，属**转述而非独立确认**；
  Saadi & Lee 1966（DOI 10.1039/j29660000005）正文仍被 Cloudflare 拦截。票保持 conflict_open，不升级。
- **MOPN：36 追到具名 1994 主来源候选，且存量精度被高估。** 主线程在本地论文缓存中独立复核到
  Tableau 4 表头确为 `eps_r à 25°C`、MP 行为 `Méthoxypropionitrile [43] - 57 165 66 1,1 36`，
  Figure 10 与 Tableau 12 同值，正文亦写 `eps_r = 36`；参考文献 **[43] = Ue, Ida & Mori, J. Electrochem. Soc.
  141(11) 2989-2996 (1994)**，DOI 10.1149/1.2059270，正文写法 Ue et al. [43, 51] 已确认。第二条独立综述级
  确认来自 Yen et al. 2022（Electrochim. Acta 411, 141105）。Ue 1994 本体 blocked（OpenAlex OA=False）。
  另外：所有可读来源印的都是两位有效数字的整数 **36**，存量 **36.0 的位数没有来源支持**。

**FEC 的 102 为什么不当场改：**`dielectric` 属 `PROVENANCE_PATCH_PROTECTED_FIELDS`，且
`data/dielectric_v03.csv` 被约 25 份报告、探针摘要与 5 个测试硬钉哈希；改写它要同步重建数据集、
更新全部钉点并重跑基准，属于一次**新的数据修订**，不应在分析封版的同时静默进行。
证据文件的 `pending_patch_rows` 已写好下一条修订应原样采用的两行 patch（conflict_status 与 notes）。

**请求预算（如实记账）：**Chandrasekhar 77 次、Boole 40 次、Dalton 55 次，合计 **172 次**；
用户硬上限 500 次/小时**未被接近**，主线程外部调用 0 次。但**两名研究者突破了主线程设定的 40 次/人子上限**，
这一偏差按事实记录，不写成合规。所有 blocked 路径都具名到具体文献与具体失败原因，「查无此值」与
「权限阻断」严格区分，本轮没有任何一条写成「无数据」。

### C. 本轮验证

`pytest -q` **703 passed**；`ruff check .` **All checks passed**；五个新探针产物重生成后 62 份 JSON 全部严格解析通过。
五个新增测试文件（C1-共13 / C2-共7 / C4-共17 / C6-共20 / Tier-0-共6）合计 63 项全过。

### D. 二次对抗复审（同一 reviewer）的 1 项 Important 与 2 项 Minor

首次修复后把**精确 diff** 交回同一位只读 reviewer（Boyle）复审。结论：**0 Critical、1 Important、2 Minor**；
修复项 1-7 全部 pass（C1 口径、C2 严格 JSON、Week8 输出包与 4 个 CSV、C1 测试可失败性、C6 措辞、五探针 LF 自纠、数据集冻结哈希），
第 8 项（本轮新增的 round-3 证据）为 partial。三项已修：

- **Important：VC 的「两个独立综述表」是过强断言。** 证据只能证明 Hall 2018 与 Vali 2016 是两张**互不相同**的
  综述级表格；两表的 VC 行都没有逐值引注，而已知的原始测量（Saadi & Lee 1966）不可读，所以两表**可能都在转引同一原始值**，
  独立性无法确立。修复：证据文件的 verdict/claim/consequence 与报告、手册一并由 independent 降级为
  distinct + independence not established，finding_id 同步改名。
- **Important：未复核来源的披露不完整。** 原先 local_recheck.not_rechecked 只列了 7 个来源，漏掉 Hall 2018、Yen 2022、
  Ue 1994、Knovel。修复：**每一条 evidence 行**新增 recheck_status（coordinator / agent_only / blocked）并补 recheck_status_legend，
  not_rechecked 扩到 11 条。现状：17 条引文中 coordinator 6、agent_only 7、blocked 4；无一条缺标注。
- **Minor：C1 报告表格被说明段落切断。** 插入的说明段落把 GFM 表头与数据行分成了两个块。修复：说明段落移到数据表之后。
- **Minor：C4 的 JSON writer 与其余四个探针契约不一致。** C4 沿用既有 json_safe 而非 _json_ready，且 json.dumps 未显式写
  allow_nan=False。修复：显式补上 allow_nan=False（json_safe 已把非有限浮点转 None，语义未变，仅统一契约）。
以上四项修完后再交同一位 reviewer 复审，发现**唯一一处未收口的 Important**：全仓 6 处旧文本把
**ECW-308 的 VC 126** 描述为 independent / independently，而 ECW-308 自己的 source_refs 就含 [3] Hall 2018，
两者不构成独立确认。已逐处修正（paper/full_draft.md 两处、paper/methods_data_records.md、paper/technical_validation.md、
reports/v033_provenance_upgrade.md、probes/g1plus_tier2_evidence.json 各一处），按 reviewer 的更严格建议写作
「ECW-308 includes Hall et al. 2018 among its source refs, so independence from Hall is not established」，
而不是断言「确定转引」（因为 ECW-308 同时引 [3] 与 [16]）。**只改 provenance 措辞，不动任何数字或结论。**

第四轮复审最终判定：**0 Critical、0 未解决 Important**；三项旧断言（independently reports 126 / independent compilation
reproduces 126 / independently reproduces the contested）在仓库与两个输出包中均为 0 命中。同一轮 reviewer 还**收回**了它上一轮
关于「Tableau 4 表头未明写 25 °C」的提示——经其复核缓存文本第 1364-1365 行确为 `εr à 25°C`，原表述无误。

**最终验证（第四轮后重跑）**：`pytest -q` **703 passed**；`ruff check .` All checks passed；
`check_paper_artifact_consistency.py` 报 paper drafts agree with the frozen artifacts；
`verify_dielectric_v03.py` 报 output_sha256 = 57387b98…（规范数据集未变）；
week7 输出包 59 个文件、week8 输出包 63 个文件，SHA256SUMS 均 missing/extra/mismatch = 0。

## 2026-09-25（续八）v0.3.11：FEC 量纲错误落地 + G1+ 第四轮爬取

### A. v0.3.11：FEC 的 102 被正式改写为「闪点，非介电常数」

第三轮留下的 `pending_patch_rows` 已原样落地为一次**独立数据修订**：

- `conflict_status`：`public_values_78.4_102_107` → `stored_value_102_is_flash_point_not_permittivity`
- `notes`：**原地合并**，不是新增第二行。`apply_provenance_patches` 对同一 `(inchikey, field)` 有唯一性约束，
  因此已有的 FEC notes 行被改写为「102 是闪点 + 78.4/107 两条腿 + 两腿都没有可读原始测量 + 不做平均、不改值」，
  上一轮的 ECW-308 与 Hall 2018 / Ue 2014 转述证据全部保留在合并后的文本里。

**受保护字段一律未动**：`dielectric` 仍为 102、`T_K` 仍为 298.15、`model_ready` 仍为 `false`。
逐格比对（对 `git show HEAD:data/dielectric_v03.csv`）确认：**246 行、行序、38 列全部不变，只有 FEC 的 2 个单元格变化**。

| 项目 | 值 |
|---|---|
| 新规范哈希 | `765fd8e04270f3e277681d6ae8e6200bfcc77c8841a89ebe0f8a3a70bc646b60` |
| 旧规范哈希 | `57387b98f899c6c0eff12716cc5b754f65d2ee0edd5523330af049ddded26fab` |
| patch 行数 | 33（原 32 + 新增 conflict_status 1 行；notes 为原地改写） |
| 行 × 列 | 246 × 38 |

**钉点同步策略（重要，避免把历史写成现状）**：8 个探针摘要 + 5 个测试常量 + 报告中「当前值」性质的表述全部重钉到新哈希；
`f5256d16…`、`2cd58144…` 以及「superseded by v0.3.10」「later re-pinned by v0.3.10」这类**明确的历史叙述一律保留**。
两个爬取证据 JSON（round2 / round3）重钉的同时新增 `canonical_sha256_revision_note` 字段，
说明「重新钉定是 v0.3.11 造成的，该轮爬取本身没有改任何单元格」，避免与文件内「本轮未改动」的陈述互相矛盾。

**重跑 vs 重钉**：三个轻量探针（`nbs514_frequency_gate_audit`、`manual_appendix_reconciliation`、
`nbs514_alpha_harmonization_probe`）**重跑重生成**；三个 ML 摘要（`v032_ablation_summary`、
`dielectric_v03_representation_ablation_summary`、`dielectric_onsager_delta_summary`）按仓库既有 re-pin 惯例
只重钉 `dataset_sha256`——其输入特征表未变，FEC 又是 `model_ready=false` 的被扣留行，
`verify_v032_benchmarks.py` 的 27 项检查覆盖的是其中**两个** lineage 摘要（v0.3.2 与 v0.3.3），可独立证明这两个钉点正确；**它不覆盖 Onsager 摘要**，Onsager 的 `dataset_path` / `dataset_sha256` 配对改由本轮新增的绑定测试（`tests/test_dielectric_onsager_delta_probe.py`）覆盖。

**顺手修复的 LF 问题**：`probes/dielectric_v03_representation_ablation_summary.json` 与
`probes/v032_ablation_summary.json` 的工作区副本为 CRLF（git 归一化后提交为 LF），已统一为纯 LF。

**本轮验证**：`pytest -q` **712 passed**；`ruff check .` All checks passed；7 个 verifier 全通过，
其中 `verify_dielectric_v03.py` 报 output_sha256 = `765fd8e0…646b60`。

### B. G1+ 第四轮爬取：三名只读研究者（本轮改动数据集 0 个单元格）

证据 `probes/g1plus_crawl_round4_evidence.json`，报告 `reports/g1plus_crawl_round4_findings.md`，
回归测试 `tests/test_g1plus_crawl_round4.py`（8 项，使本轮每条关键断言都可被机器证伪）。

#### B1. 最重要的发现：此前「本地 ThermoML 未命中」读的是局部子集（用户的怀疑成立）

`data/processed/thermoml_normalized.csv` **不是全语料抽取结果**——它自己的 provenance 就写着
`raw_file_count: 5`、`row_count: 625`、`filter: dielectric_only`。独立重解析全部 **242 个本地 XML**：
91 个文件带结构化介电观测，共 **11,646** 条介电 `PropertyValue`，其中**归一化表漏掉 11,021 条**，
且**反向差异为 0**（91 个来源里 87 个在归一化表中完全无匹配）。

**但必须分开说**：被追踪的逐条抽取 `data/processed/dielectric_raw.csv` 是**完整**的——
独立重解析与它按 `DOI + data_number + property_name + value + temperature + InChIKey` 多重集比对
**11,646 / 11,646 完全一致**（唯一差异是零频 `frequency` 字段写作 `'0'` 与空串）。
所以这是**辅助文件的文档缺陷**，不是被追踪抽取的缺陷，两者不能混为一谈。

十个目标分子的 XML 级回答：diglyme 9、triglyme 15、tetraglyme 11、己二腈 31、戊二腈 31 条纯液体观测
（全部已由现有 DOI 代表）；PC、EC、MOPN、VC、FEC 为 **0**，且这是按精确 InChIKey / CAS / 别名得到的结论，
不是「归一化表未命中」。**THF / NMP 的假阴性风险同时被排除并精确化**：THF 精确命中 9 个 XML、
NMP 7 个，均无结构化介电属性；但纯文本子串检索不安全（`tetrahydrofuran` 会误命中 `2-tetrahydrofurylmethanol`）。

补录 backlog 全部被现有闸门挡在门外：A 类新分子零频 33 条（18-crown-6、butanedinitrile，均在近室温带**之上**）、
B 类高压 145 条（dimethyl ether，2,200–29,400 kPa）、变频候选 550 + 344 条。
附带发现：`data/raw/thermoml_archive/ThermoML.v2020-09-30.tgz` 首 8 字节为全零、**不是 gzip magic**、
非零字节仅 8,359,677（4.41%），**不可用**，本地 242 个 XML 才是有效证据基础。

#### B2. DC-200：数据集确实存在，但成员没有公开

论文锁定为 Zhang et al., ACS Nano 2026，PMC13422007，DOI `10.1021/acsnano.6c06255`。原文明确
「200 aprotic samples measured experimentally at room temperature」，即 **DC-200 是实验值**；
论文里计算的是辅助建模用的偶极矩，不是计算介电常数。但 PMC Associated Data 只挂 SI PDF，
SI 里 `DC-200` 出现 13 次**全部是正文或图注**，没有成员表、没有逐行数值、也没有逐行温度（只有 `"room temperature"`）。

SI PDF 经 AWS 开放镜像取得（5,244,112 字节，SHA-256 `E6AFBAF9…C077BA57`），
与仓库既有缓存 `data/external/g1plus/compilations/nn6c06255_si_001.pdf` **逐字节一致**，
主线程据此在独立副本上重导了「13 处全是图注」的复核。作者 GitHub 递归 207 个对象（`truncated=false`）无 DC-200；
Figshare 33005827 只有同一份 SI。ref 82 = He et al. 2025（`10.1063/5.0267184`，closed）、ref 83 = MNSOL 2012（92 个溶剂），
论文未给选出 200 条的规则，**无法唯一重建名单**。

**结论：与本地 246 行的交集 = UNKNOWN，不是 0。** 这一条已写成回归测试，防止后续被美化成「无重叠」。

#### B3. 四篇未闭环主源：题录全部确证，数值全部仍被挡；并发现一处**标识符错配**

四篇的题录均经 Crossref / OpenAlex / Semantic Scholar 确证。开放途径全部失败（OUP 403、RSC 403、
Springer 303 跳转身份认证、HAL `numFound=0`、Google Books / Internet Archive / NDL 无响应、Europe PMC 四篇 `hitCount=0`）。

**关键更正**：DOI `10.1039/j29660000005` 的题名是
*Physicochemical studies of some cyclic carbonates. Part V. The alkaline hydrolysis of vinylene carbonate*——
**这是一篇碳酸亚乙烯酯（VC）论文，不是己二腈/戊二腈论文**；按作者 Saadi + 1966 + 腈类/介电检索也不存在这样一篇。
工作数据集里己二腈 30、戊二腈 37 实际追到的是 Duncan 2013。
→ 该阻塞票据必须改名或换标识符，澄清之前**不得**写成「己二腈的原始测量」。

另两条边界更正：**Ue 2014 Table 2.3** 的 FEC = 107 腿本轮仍未读到，仓库早先的转录
`… (FEC) 106 1.50 107 4.1 -13.30 1.45` 是**此前的人工观察**，不得当作本轮新读到的证据；
**Flamme 2017** 在链条中承载的是 PC 64.9 / EC 89 / VC 黏度，并未被确立为 FEC 78.4 的原始测量，读到表前不得升级。

#### B4. 请求预算（如实记账）

| agent | 目标 | 请求数 | 40 次子上限 | 是否突破 |
|---|---|---:|---:|---|
| Volta | ThermoML 本地完整性复核 | 0（纯本地） | 40 | 否 |
| Dirac | DC-200 抓取 | 35 | 40 | 否 |
| Banach | 四篇未闭环主源 | 33 | 40 | 否 |
| **合计** | | **68** | | |

用户 500 次/小时硬上限**未被接近**；主线程外部调用 0 次；无 429 重试风暴。
**这是第一轮每个 agent 都守住了 40 次/人子上限**（此前第三轮有两名突破）。所有 blocked 路径都具名到
具体文献与具体 HTTP 状态，「查无此值」与「权限阻断」严格区分，本轮没有任何一条写成「无数据」。

### C. 收尾

- 成果包重导：week7 **57 个复制工件、目录共 60 个文件**；week8 **66 个复制工件、目录共 69 个文件**（其中 7 个在 `paper/` 下）。两个导出器各自报 `verification_passed: true`；`verify_export_manifests.py` **默认**只检查 week1–week6；显式传入 `--output-dir` 后 week7 与 week8 同样 PASS（本轮已实测）。
  week8 本次补入了此前遗漏的 **第三轮**爬取产物（报告 + 证据），以及第四轮的报告、证据与回归测试。
- 执行手册附录 J-补记的「待办 5（FEC 数据集修订）」已在本轮结清，新增第四轮补记。
- 仍未闭环（按优先级）：温度带决策（33 条 A 类）、压力闸门（145 条）、频率闸门（894 条）、
  Saadi 1966 标识符更正、Ue 1994、Hagiyama 2008、Flamme 2017、DC-200 成员表（需向作者索取）。

### D. 对抗复审（同一 reviewer）的 4 项 Important 与 2 项 Minor

把精确 diff 交给只读 reviewer（Euclid）复审。结论：**0 Critical、4 Important、2 Minor**。
四项 Important 全部已修（主线程是唯一写者，串行修改）：

1. **week7 交付包仍自称 v0.3.10，并把已解决的 FEC 冲突列为 open item。** 生成物同时含 `dataset_version: "0.3.10"`
   与新哈希，`open_items` 仍写「78.4 / 102 / 107 unresolved」。
   → 修复：`dataset_version` 改 `0.3.11`，`dataset_version_note` 追加 v0.3.11 一句，open item 改写为
   「102 是闪点，存活的两条腿为 78.4 vs 107 且都无原始测量」。同类陈述在 `reports/week7_dataset_expansion_and_freeze.md`、
   `reports/g1_data_gate_review.md`、`reports/v033_provenance_upgrade.md`（3 处）一并更正，避免同一交付包里自相矛盾。
2. **`reports/manual_appendix_reconciliation.md` 直接否认了实际发生的 `conflict_status` 变化。** 原文写
   "No ... conflict status ... moved"。
   → 修复：改为「本探针自身未改任何数据」，并明写「规范哈希在撰写时为 `57387b98…`，v0.3.11 修订后为 `765fd8e0…`，
   该修订只改了 FEC 的 `conflict_status` 与 `notes`」。
3. **第三轮报告仍把 FEC 修订列为未落地。**
   → 修复：给该节加「以下为本轮当时的历史状态，修订已于 v0.3.11 落地」封闭标记，
   并把「仍未闭环」第 5 项改为已结清；同时把「conflict_status 保持原样」限定为「本轮当时」。
4. **「27 项检查可独立证明三个 ML 钉点」的覆盖范围不成立。** `verify_v032_benchmarks.py` 的 `LINEAGES`
   只含 v0.3.2 与 v0.3.3 两个摘要，**不含 Onsager**。
   → 修复：把这句限定为两个摘要；并为本轮新增 Onsager 的独立绑定测试
   （`tests/test_dielectric_onsager_delta_probe.py` 断言 `dataset_path` / `dataset_sha256` 与工作区一致），
   使三个钉点都各自有机器校验，而不是只靠声明。

两项 Minor 也一并修：**①** Duncan 归属措辞把「ECW-308 的争议值 30/37」与「数据集存储的 32.12/34.6
（来自 `10.1021/je300958c`）」混为一谈，已在报告与证据 JSON 中分开表述；
**②** 成果包文件数口径含混，已改为「week7 = 57 个复制工件 / 目录共 60 个文件；week8 = 66 个复制工件 / 目录共 69 个文件
（其中 7 个在 `paper/` 下）」，并注明 `verify_export_manifests.py` 只覆盖 week1–week6。

修复后重跑：`pytest -q` **712 passed**（新增 Onsager 绑定测试 1 项）；`ruff check .` All checks passed；
7 个 verifier 全通过；两个成果包重导并各自自校验通过。

## 2026-09-25（续九）：两条介电腿在原始测量层面闭死 + G1+ 第五轮爬取

- Decision: 把 FEC 78.4 与碳酸亚乙烯酯 126 两条腿**从"有线索"升级为"已读到原始测量"**，
  但**本轮不改任何数据单元格**；两条更正各自写成字段级补丁进入 backlog，
  留给独立的 v0.3.12 修订轮落地。语料来源：Kobayashi 2003 与 Saadi & Lee 1966 两份原文 PDF。
- Evidence（FEC 78.4）: Kobayashi, Inoguchi, Iida, Tanioka, Kumase & Fukai,
  *J. Fluorine Chem.* **120**(2), 105-110 (2003), DOI `10.1016/S0022-1139(02)00317-2`，
  Table 2 第三条数据行逐字 `210  17.3  1497  4.1e  78.4e  1.04e  Our data`。
  介电值带脚注 e，Table 2 脚注 **e = "At 23 °C."**；脚注 b 明写
  "Physical properties are cited from ref. [11,12] **except our data**"，该行 Ref 列即 "Our data"。
  同一行 mp 17.3 / bp 210 / 黏度 4.1 / ε 78.4 与 Flamme 2017 Table 1 entry 21 的 FEC 四项完全一致，
  构成由 Flamme 到 Kobayashi 的锁定。
- Evidence（VC 126）: Saadi & Lee, *J. Chem. Soc. B*, 1966, pp. 5-6, DOI `10.1039/j29660000005`。
  实验部分给出 **E (25°) = 126 ± 1.0**（电池以苯、甲醇、水标定）；Table 2
  "Physical properties of some cyclic carbonates at 25°" 列 Vinylene carbonate ε = 126、μ = 4.45 D。
  同表旁证：PC 61.0（25 °C）、EC 95.3（40 °C）、氯代 EC 62.0（40 °C）、水 78.5。
  数据集存的 126 本来就是对的，缺的是它的"身份"。
- Correction（给第四轮补下一层，非撤回）: 第四轮写的是"Flamme 2017 未被确立为 FEC 78.4 的原始测量"，
  这句本身**没有错、也未撤回**——Flamme 确实不是原始测量，第四轮只是没拿到全文。
  本轮 Ampere 从 HZDR 机构库取得全文，**补下了一层**：正文写 `εr=89.8 for EC and 78.4 for FEC, Table 1, entries 20 and 21`，
  Table 1 entry 21 逐字 `17.3 210 4.1 78.4 4.70 1.50 (70.70) 5.0 6.6 (Pt) [36],[42]`。
  另修正一处下标错误：Crossref `reference.key` 相对方括号编号有 **+3 偏移**，
  校正后 `[42]` = Kobayashi 2003（第四轮按数组下标直读会错解为 Sasaki 2010 / Wang 2010）。
  正确表述分两层：**Flamme 是承载者（第四轮未确立，本轮确立），Flamme 不是原始测量。**
  另 note：Kobayashi 表化合物名为结构图，文本层抽不出字，78.4 归属 FEC 靠与 Flamme entry 21 的
  mp 17.3 / bp 210 / 黏度 4.1 / ε 78.4 指纹匹配 + entry 编号锚定，不是行内文字标签。
- Identifier（Saadi 定案）: 原文与已登录 Reaxys 双向确认 DOI `10.1039/j29660000005`
  是**碳酸亚乙烯酯**论文，Reaxys 里该引用挂在 vinylene carbonate 行（CAS 872-36-6，RN 105683）的
  "Dielectric Constant - 1" 分类下。仓库此前把它当己二腈/戊二腈票据是仓库的错，标识符本身无误。
  该 Reaxys 记录六个数值列**全为空**，只有 Reference 有值——索引知道有人测过，但不给数。
- Decision（同源 vs 独立）: 受限互证必须区分"同源确认"与"独立互证"。
  己二腈、戊二腈的受限记录引用与数据集行**同一个 DOI** `10.1021/je300958c` → 同源确认（只证明抄写正确）；
  四甘醇二甲醚、四氢呋喃、NMP 为独立互证；二甘醇二甲醚混合。
  计数 `same_source_confirmation 2 / independent_sources_only 3 / mixed 1 / no_capture 10`。
- Decision（压力闸门）: 生成器实现 90–110 kPa 常压窗口。NMP 的 Uosaki 1996 是 100 kPa–250 MPa 压力序列，
  保留 5 条窗口内近室温行、**排除 5 条加压行**；没有任何加压值进入比较。
- Negative（三个数据源）: Materials Project 对液体实验介电常数**不适用**（SiO₂ 对照 200/total_doc 322 证明 key 有效，
  EC/PC/乙腈均 total_doc 0；其介电量是晶体计算值）。NIST WebBook 53 个缓存页全文检索介电词汇 **0 命中**，
  水/甲醇/乙醇/丙酮正对照同样为 0。CatalystHub 三个入口测试两个超时，相似域名身份未确认，密钥未外发。
- Boundary（受限源）: SpringerMaterials 与上海有机所数据库**当前都打不开**（用户确认），
  本轮**没有从这两处取得任何新抓取**；涉及这两处的受限陈述都是对 2026-09-23 已有磁盘抓取的重读。
  但本轮**确实新增了受限材料**（Kobayashi 2003、Saadi & Lee 1966、Reaxys 抓取、Flamme 2017 HZDR 副本），
  清单见证据文件 `new_restricted_materials_this_round`。
  上海有机所那次会话返回"无此用户名"错误页，不是已登录态，故一次查询都没发。
- Dataset impact: **changed_fields = []**，`data/dielectric_v03.csv` 仍 246 行、
  sha256 `765fd8e04270f3e277681d6ae8e6200bfcc77c8841a89ebe0f8a3a70bc646b60`。
  不就地改的原因：该哈希被约 20 个探针、报告与测试写死，改一格必须连带重跑，
  属于独立的数据修订轮。两条补丁已逐字段写进证据文件 backlog：
  **FEC** `dielectric 102 -> 78.4`、`T_K 298.15 -> 296.15`、`evidence_level -> primary`、
  `source_quality -> primary_experimental`、`temperature_source -> reported`、
  `source_doi -> 10.1016/S0022-1139(02)00317-2`、`source_table -> Table 2`、`notes` 按原始测量重写，`model_ready` 保持 false
  （78.4 vs 107 未解，且动它会改变冻结的拟合子集）；
  **VC** 数值不动，改 `evidence_level -> primary`、`source_quality -> primary_experimental`、
  `temperature_source -> reported`、`source_doi -> 10.1039/j29660000005`、`source_table -> Table 2`、
  `uncertainty_kind -> reported` + `uncertainty_value 1.0`、`notes` 按原始测量重写，并重写 `conflict_status`
  （Knovel 78–127 是包含原始值的低信息量区间，不是竞争点值）；许可字段需按付费原始源重新推导。
- Request budget: Tesla 40 / Peirce 40 / Ampere 40 / Pasteur 10 = **130**，
  四个 agent 均未突破 40 次/人子上限，用户 500 次/小时上限未被接近；主线程未发出计量 API 调用。
- Artifacts: `probes/g1plus_round5_crosscheck.py`（受限互证生成器，可复跑）、
  `probes/g1plus_round5_crosscheck_summary.json`、`probes/g1plus_crawl_round5_evidence.json`、
  `reports/g1plus_crawl_round5_findings.md`、`tests/test_g1plus_crawl_round5.py`（12 项断言全通过）。
  两份 PDF 与 Reaxys 抓取留在 git-ignored 的 `data/restricted/{kobayashi2003,saadi1966,reaxys}/`。
- Still open: FEC 107 腿（Hagiyama 2008 OUP 403；Ue 2014 章节 Springer 身份认证）、
  MOPN 介电值（Ue 1994 IOPscience 付费页；Reaxys 已确认无该分类）、受限目录 4 个未取值目标
  （需 SpringerMaterials 恢复可达）、v0.3.12 数据修订落地、温度带决策、DC-200 成员表。

## 2026-09-25（续十）v0.3.12：两条 primary 值落地 + 哈希钉点全量重跑

把第五轮 backlog 里的两条字段级补丁原样落地为一次**独立数据修订**。本轮唯一的写者是主线程；
两个只读审计 agent（Godel 审 paper/、Hegel 审 reports/ 与手册快照）只产出清单，不写文件，
避免并行写冲突。

### A. 改了什么

| 行 | 字段 | 旧 | 新 |
|---|---|---|---|
| FEC | `dielectric` | 102（实为闪点） | **78.4**（Kobayashi 2003 Table 2，脚注 e = "At 23 °C."） |
| FEC | `T_K` | 298.15 | **296.15**（23 °C） |
| FEC | `source_doi` / `source_url` / `source_citation` / `source_table` | `10.1002/cssc.202402091` 等 | `10.1016/S0022-1139(02)00317-2` / Table 2 / Kobayashi et al. (2003) J. Fluorine Chem. 120(2) 105-110 |
| FEC | `source_quality` / `evidence_level` / `temperature_source` | open_access_review_table / review | **primary_experimental / primary / reported** |
| FEC | `conflict_status` | stored_value_102_is_flash_point_not_permittivity | `primary_78.4_landed_107_leg_unread` |
| VC | `source_doi` / `source_url` / `source_citation` / `source_table` | `10.1002/cssc.202402091` 等 | `10.1039/j29660000005` / Table 2 / Saadi & Lee (1966) J. Chem. Soc. B 5-6 |
| VC | `uncertainty_value` / `uncertainty_kind` | 空 | **1.0 / reported** |
| VC | `source_quality` / `evidence_level` / `temperature_source` | open_access_review_table / review | **primary_experimental / primary / reported** |
| VC | `conflict_status` | conflict_open | `knovel_78_127_interval_contains_primary_value` |

**受保护字段**：VC 的 `dielectric` 仍 126、`T_K` 仍 298.0；两行 `model_ready` 均保持 `false`。
行数仍 246、列数仍 38。`data/processed/dielectric_v03_exclusions.csv` 的 FEC 行改写为
`competing_107_leg_unread` / `exclude_from_model_pending_107_leg_review`（5 行、InChIKey 集合不变）。

### B. 三个致命约束（决定了实现路径）

1. `apply_provenance_patches()` 要求补丁 `value` 非空 → **不能用补丁清空字段**；而
   `review_license_errors()` 会把「license 仍非空 + DOI 不在开放许可白名单」判为
   `unsupported review source_doi` 并直接 `ValueError`。
   → 解法：**就地改 base review 行**（`modern_solvent_public_review_observations.csv`），
   既不走补丁通道，也不移表。
2. `scripts/verify_v032_benchmarks.py` 硬性要求 `withheld_not_model_ready_count == 1` 且名单恰为
   `["vinylene carbonate"]` → **VC 不能移出 review 表**（该表才有 `model_ready` 列）；
   移表会让 VC 从 withheld 变成 excluded，verifier 立即失败。
3. license 四列的唯一可行组合：`source_quality=primary_experimental` + `source_license=''` +
   `license_url=''` + `redistribution_conditions=''` + `redistribution_status=allowed`，
   与既有 PC/EC primary 行完全同形。

### C. 钉点

| 项目 | 值 |
|---|---|
| 新规范哈希 | `1b285fe852c13a99e26cc94e85ffab389857351cd4fca36aed0ccf3f40d22456` |
| 旧规范哈希（v0.3.11） | `765fd8e04270f3e277681d6ae8e6200bfcc77c8841a89ebe0f8a3a70bc646b60` |
| 行 × 列 | 246 × 38 |
| `model_ready=true` 行 | 240，**与 HEAD 逐字节一致**（`FROZEN BENCHMARK VIOLATIONS: []`） |
| 变化行 | 仅 FEC 与 VC |
| 补丁文件 | 33 → **30** 行（删掉 3 条已被就地值取代的补丁） |
| evidence_counts | primary 15→17、open_access_review_table 21→20、open_access_article_text 1→0、secondary_compilation_unverified 1、v0.2 208 |

**重跑而不是重钉**：三个轻量探针（`nbs514_frequency_gate_audit`、`manual_appendix_reconciliation`、
`nbs514_alpha_harmonization_probe`）重跑重生成；三个 ML 摘要
（`v032_ablation_summary`、`dielectric_v03_representation_ablation_summary`、`dielectric_onsager_delta_summary`）
也**全部真正重跑**——其 diff 只有 `dataset_sha256` / `exclusions_sha256` / `generated_at` 三处，
**所有指标、折与预测逐字节未变**。这正是「FEC 与 VC 都不参与拟合」的独立证明，
比上一轮的「重钉 + 声明」更强。4 个静态证据 JSON 重钉 `canonical_sha256` 并改写
`canonical_sha256_revision_note`；6 个测试常量、报告与论文侧叙述同步。

### D. 只读对抗复审（agent 集群）

- **Godel（paper/）** 逐行列出因 v0.3.12 变成事实错误的语句；已按最小替换落地，
  并**保留**两处明确的历史叙述：`paper/methods_data_records.md` 的 v0.3.1 小节、
  `paper/technical_validation.md:268` 的 "Until v0.3.4 ... yet still fitted"。
- **Hegel（reports/ 与手册快照）** 把 17 处旧哈希分类：7 处判为「当前值」必须重钉，
  10 处判为历史必须保留；并证明 `tests/fixtures/manual_appendix_j_snapshot.md` 与外部手册
  「附录 J-补记三」的派生快照逐字节一致（fixture sha256 `531083aa…38ad4e`）。
- **主线程驳回 Godel 的一项建议**：`paper/abstract_and_intro.md:14` 的 "four rows" 与 exclusion 文件的
  5 行**不矛盾**——v0.3.2 lineage 的 `probes/v032_ablation_summary.json` 记录 `source_count=245`、
  `excluded_count=4`、`exclusion_file_count=5`，MOPN 不在 v0.3.2 roster 内所以落在 `excluded_not_in_source`，
  **不改**。（该 artifact 必须用 `--source data/dielectric_v032.csv` 复跑；第一次用错 `--source` 时它被写成
  246/5/[]，已由只读复审员 Nash 证伪并回滚复跑——见 §H。）

### E. 有意做的语义修复

- 论文原写 "no subscription-only numeric values were promoted into the public dataset"，v0.3.12 后按字面已假。
  已限定为 `no subscription-restricted SpringerMaterials value`，并明写 FEC 78.4 与 VC 126 是**付费原始文献里的
  单个测量事实**、源 PDF 存入 git-ignored 的 `data/restricted/` 且不随数据集再分发。
- 原写 "ECW-308 independently supports 78.4" 已改：ECW-308 → Flamme 2017 → Kobayashi 2003 是**同源链**，
  不是独立互证（VC 的 Flamme 2017 entry 26 同理，引用的是同一篇 Saadi & Lee 1966）。
- VC 的 `paper/methods_data_records.md` 段落原本还写「pipeline 只认 exclusion list 不认 `model_ready`」，
  该陈述在 v0.3.4 后即已漂移，本轮一并修正为 gate 已扣留。

### F. 本轮验证

`pytest -q` **726 passed**（新增 `SHIPPED_REVIEW_DOIS` 与 `REVIEW_LICENSE_METADATA_UNDER_TEST` 拆分的回归测试）；
`ruff check .` All checks passed；7 个 verifier 全通过，`verify_dielectric_v03.py` 报
output_sha256 = `1b285fe8…22456`；week7 / week8 成果包已重导并各自自校验通过
（`verify_export_manifests.py` 默认只覆盖 week1–week6，week7/8 必须显式给 `--output-dir` 才会被它校验）。

### G. Still open

FEC 107 腿（Hagiyama 2008 OUP 403；Ue 2014 Springer 认证墙）、MOPN 的 primary 确认与 GFN2-xTB 特征行、

### H. 提交前的只读对抗复审（Nash）与一处 Critical 回滚

把全部 staged 文件的完整 diff 交给一名只读复审员（Nash），要求逐条证伪。结论：**1 Critical、3 Important、4 Minor**。

**Critical（已修）**：`probes/v032_ablation_summary.json` 的 v0.3.2 lineage 第一次复跑时误用了
`--source data/dielectric_v03.csv`（246 行）而不是 `data/dielectric_v032.csv`（245 行），
导致 `source_count 245→246`、`excluded_count 4→5`、`excluded_not_in_source [MOPN]→[]`，
即 v0.3.2 与 v0.3.3 两个 lineage 的记录被写成完全重合。
`verify_v032_benchmarks.py`（只校验 digest、withheld 名单与指标）与
`check_paper_artifact_consistency.py`（只校验会计恒等式 236+5+4+1=246）**都不会拦住它**，两条都实测 PASS。
→ 修复：用正确的 `--source data/dielectric_v032.csv` 重跑该 lineage，`source_count=245`、`excluded_count=4`、
`excluded_not_in_source=['OOWFYDWAMOKVSF-UHFFFAOYSA-N']` 已恢复；该文件的 staged diff 回到**只有**
`dataset_sha256` 与 `exclusions_sha256` 两行。**这是一次真实的可复现性缺口，不是措辞问题。**

**Important（已修）**：三份跨版本维护的报告里仍有被 v0.3.12 证伪的现在时陈述——
`reports/week8_benchmark_freeze.md`（"VC remains conflict_open"、"neither leg has a readable primary measurement"）、
`reports/g1_data_gate_review.md`（"stored 102"、"78.4 (ECW-308)"、"neither has a readable primary measurement"）、
`reports/v033_provenance_upgrade.md`（78.4/107 两腿、VC 的 CC BY-NC 许可、以及「Saadi 全文仍需读到」）。
三者都会被 `export_week7/week8_results.py` 复制进交付包，不一起修就会让交付包自相矛盾。

**Minor（已修）**：`reports/g1plus_crawl_round5_findings.md` 的「仍未闭环」第 4 项补上结清标记；
本记录 §D 原先引用的 `excluded_count=4` 一度被上述 Critical 污染，已改为引用 `source_count=245` 的 v0.3.2 lineage；
§F 关于 `verify_export_manifests.py` 的覆盖范围已限定为 week1–week6 + 显式 `--output-dir`。

**留档的 4 条「未能证伪但存疑」**：① `v032_ablation_summary.json` 原先不记录 `source_path`，lineage 输入无法自证（已于续十一修复）；
② Kobayashi Table 2 的 FEC 行归属靠 mp/bp/η/ε 四值指纹与 Flamme entry 21 对齐，不是行内文字标签；
③ `paper/code_and_data.md` 的 "Two rows need explicit qualification" 只点名了 MOPN（已于续十一改为逐行点名）；
④ VC 存 `T_K=298.0` 而源文写 25 °C（298.15 K），行内 `notes` 已声明 0.15 K 差在报告精度内。

**复审已核实为真的关键声明**：数据集只有 VC / FEC 两行不同、canonical 哈希
`765fd8e0…646b60 → 1b285fe8…22456`、`build_dielectric_v03.py` **幂等**（前后 SHA256 完全相同）、
补丁层 33→30 且 FEC/VC 不再有任何补丁、FEC/VC 的 `notes` 与 round-5 `backlog` 的 VERBATIM 串逐字相等（476 / 518 字符）、
另外两个 ML 摘要只变哈希与 `generated_at`；三个轻量探针均重跑并重钉 dataset hash，`manual_appendix_reconciliation` 还更新了手册快照计数与 FEC/VC current-row 视图、
test fixture 与外部手册附录 J-补记三逐字节一致、历史哈希未被误改（`decisions_log.md` 为 +91/-0 纯追加）。

温度带决策、DC-200 成员表、受限目录 4 个未取值目标。**v0.3.12 这一节已结清。**


## 2026-09-25（续十一）第二轮对抗复审：C1 护栏 + 交付包 README

- 触发：`adversarial-review-optimize` skill 的 fresh re-review 步骤。基线 `024be15`，
  修复 revision `dd2a37d`。主线程是唯一写者；复审员 Turing（代码/数据）与 Euler（交付包/汇总）全程只读。
- 第一轮 finding：Turing 1 Important（原 C1 的 verifier 盲区仍在：把 summary 改成已知坏状态
  `246/5/[]` 后旧 verifier 仍 `27/27` PASS）+ 3 Minor；Euler 2 Important
  （week7 生成器仍写 v0.3.12 “without moving a dielectric value”；week7/week8 缺 README）+ 4 Minor。
- 修复：`probes/dielectric_representation_ablation.py` 写入 `source_path/source_sha256`；
  `scripts/verify_v032_benchmarks.py` 新增 `v0.3.2 lineage source provenance` 并 pin
  `data/dielectric_v032.csv / 39d15e16…b30be / 245 / 4 / [MOPN]`；
  `tests/test_verify_v032_benchmarks.py` 加负向测试；week7 叙事改为 FEC `102→78.4`；
  week7/week8 导出器生成 README 并纳入 `SHA256SUMS`；跨版本报告与 paper 的 stale 叙述同步修正。
- RED → GREEN：坏状态回归测试先在旧实现下 `assert not True` 失败，修复后通过；
  export README 测试先 `ImportError`，修复后 2 passed。全量 `pytest` **729 passed**、
  `ruff check .` 全绿、7 个 verifier 全绿。
- 第二轮 Euler 复审发现总汇总仍写 `HEAD 024be15`（Important）、README 校验命令目录不对等 4 个 Minor；
  已改为最终 revision、从仓库根目录运行、最终计数 week7 61/60、week8 75/74，并给两处 v0.3.11 历史哈希加 v0.3.12 re-pin 注记。
- **Re-review verdict**：Turing 对 `024be15..dd2a37d` 判
  `No Critical or Important findings; Ready.`；最终 7 个 verifier 与两个 manifest 均 PASS。
- 完整记录见 `reports/v0312_adversarial_review_round.md`。**本轮 v0.3.12 收口完成。**

## 2026-09-25（续十二）v0.3.13：FEC 107 腿在汇编层读到 + 78.4 的 40 °C 转述冲突

- 触发：用户要求继续推进 G1+ 的溯源收口。三名只读研究者（Popper 等）与主线程唯一写者并行，
  数据库侧 Materials Project / ECW-308 / Zenodo 均不在本轮重打；外部 API 调用 < 20 次。
- 前置约束：不改 `data/raw/*`；受限源数值不进可分发数据集；冲突值不平均；同源转述不写成独立互证。

### A. 两处真实发现

**发现 A —— FEC 的 107 腿在汇编层读到（仍未到原始测量层）。**
Ue, M.; Sasaki, Y.; Tanaka, M.; Morita, M. 的 Springer 章节
*Electrolytes for Lithium and Lithium-Ion Batteries* 第 2 章
（DOI `10.1007/978-1-4939-0302-3_2`）Table 2.3（印刷页 101）逐字含
`4-Fluoro-1,3-dioxolan-2-one (FEC) 106 1.50 107 4.1 -13.30 1.45`；
印刷页 105 的正文把 FEC 的介电数据归到该章 ref `[25]`，即
Hagiyama, K. 等，*Chem. Lett.* **37**, 210-211 (2008)。Table 2.3 本身在印刷页 100 被声明为
两篇 Sasaki 综述（refs `[4]`、`[5]`）的汇编，**FEC 行没有任何逐行脚注**，
所以 107 是**汇编层转述 Hagiyama 线**，不是独立一手测量。
Hagiyama 2008 本地仍无 PDF（OUP 403 / J-STAGE 404），该行保持 `model_ready=false`。

**发现 B —— 78.4 的 40 °C 版本是下游转述，不是第二组测量。**
Nanbu, N. 等，*Electrochemistry* **2007**, 75(8), 607-610
（DOI `10.5796/electrochemistry.75.607`）印刷页 608 逐字写
`The dynamic viscosity of FEC (4.1 mPa s at 40 C)4) ... the relative permittivity of FEC (78.4 at 40 C)4)`，
其 ref `4)` 逐字就是 Kobayashi 2003 —— 数据集已引的同一篇。
一手表 Kobayashi 2003 Table 2 的 FEC 行在 **印刷页 108**（见 §B 的 C1 更正）三个上标均为 `e`，
脚注 `e At 23 C.`；EC 行用 `c`(40 °C)、PC 行用 `d`(20 °C)，说明脚注字母确有区分作用。
Nanbu 把**介电与黏度两个量同时**从 23 °C 移到 40 °C，属系统性温度移位，不是孤立笔误。
**裁决：`T_K` 维持 296.15 K（23 °C），不改 313.15 K，不平均。**

**107 腿的温度。** 两篇开放 J-STAGE 2013 通讯（*Electrochemistry* 81(10), 817-819 与 820-822）
都写 `about 107 at 25 C`，ref 均指向 Hagiyama 2008。两条腿因此**近乎同温**
（23 °C vs 25 °C，**差 2.00 K**），**不能**用温度解释掉 78.4-vs-107 的分裂，仍是未决数值冲突。

**数据影响：只改 FEC 一行两字段。**
`conflict_status` → `primary_78.4_landed_107_leg_read_in_ue2014_compilation_plus_40C_temp_conflict`，
`notes` 追加 107 腿汇编层归源与 40 °C 转述冲突说明；
`dielectric` 仍 `78.4`、`T_K` 仍 `296.15`、`model_ready` 仍 `false`。
`data/processed/dielectric_v03_exclusions.csv` 的 FEC 行 `reason`/`evidence_b` 同步。
另修一处**既有回归**：该 exclusion 行的 `evidence_b` 原先含未加引号的逗号，裸 split 会读成 9 列；
已按最小引号规则重写为 6 列，5 条排除 InChIKey 集合不变。

### B. 提交前的只读对抗复审（Popper）与 1 Critical + 3 Important + 4 Minor

| 级别 | 对象 | 缺陷 | 处理 |
| --- | --- | --- | --- |
| Critical | `probes/g1plus_fec_temperature_attribution_evidence.json`、数据集 FEC `notes`、findings 报告、回归测试 | Kobayashi 2003 的 FEC 行页码写成 **印刷页 107 / PDF 第 9 页**；实测该 PDF 只有 6 页（标签 105-110），`78.4e` 行在 **页索引 3 = 印刷页 108 = PDF 第 4 页**，本地根本没有第 9 页。错误页码还被回归测试固定 | 已改 `printed_page=108`、`pdf_page=4`（另加 `pdf_page_index=3` 消歧）、数据集 `notes`、报告与测试断言；重跑全量产物 |
| Important | 同一证据链 | `gap_K` 写成 `1.85`；23→25 °C 的正确差值是 **2.00 K**（`1.85` 误把 23 °C 当成 23.15 °C） | 5 处（证据 JSON、报告、fixture、测试、外部手册）改为 `2.00`，重生成 fixture |
| Important | `reports/decisions_log.md` | 无 v0.3.13 小节，最新决策仍停在 v0.3.12 | 追加本节 |
| Important | `成果输出\数据结果汇总.md` | 仍停在 v0.3.12 / 旧 digest | 已更新到 v0.3.13 与新 digest |
| Minor | `probes/export_week8_results.py` | README 措辞只提 v0.3.12 | 改为「未被 v0.3.12 / v0.3.13 改动」 |
| Minor | `probes/dielectric_v03_representation_ablation_summary.json` | 较 HEAD 多出 `source_path`/`source_sha256` 两个字段 | 属 v0.3.12 续十一的 schema 补全，本轮重跑后保留，此处登记 |
| Minor | 新增 FEC 测试 | 只比对 JSON 里的 PDF 哈希字符串，未重算本地缓存 | 新增「缓存存在时才跑」的本地 SHA256 校验（absent 则 skip），CI 不依赖 git-ignored 缓存 |
| Minor | 2013_817 逐字引文 | 原文 `(about\n107 at 25°C)` 跨行，证据 JSON 写成单行 | 在证据 JSON 增 `verbatim_note` 说明已做空白/换行归一化 |
| Important（第二路复审 Zeno） | 手册闸门 | 「手册与 fixture 逐字节一致」无法发现手册把**过期 digest** 写成最终钉点（自洽 ≠ 最新） | 探针新增 `current_canonical_sha256` / `current_digest_pinned`；测试新增「committed fixture 必须钉住当前规范 digest」断言（定向用例 24 → **25**） |
| Minor | `probes/dielectric_target_scaffold_summary.json` | 重跑后较 HEAD 多出 `withheld_not_model_ready_count` / `withheld_not_model_ready_names` 两个键，另有键顺序调整 | 属 schema 补全（`verify_dielectric_target_scaffold` 仍 11/11 PASS、数值与预测未变），在此登记 |

Popper 同时**逐项复现为真**：数据集只动 FEC 一行两字段、240 条 `model_ready=true` 行逐字节未变、
exclusion CSV 结构合法且 5 条 InChIKey 不变、各探针 hash 与数据集自洽、
「重跑而非重钉」成立、无过度声称（107 全流程只写作 compilation level）。
注入验证：把 `printed_page` 改成实际值会让旧测试变红，证明测试非恒真——也正因此两条错误断言才被固定住、必须修。

### C. 钉点（钉点全量重跑，不是重钉）

| 项 | 旧值（v0.3.13 首稿） | 新值（终值） |
| --- | --- | --- |
| `data/dielectric_v03.csv` sha256 | `1a6b6bad…ed55` | `a446c216874538d900e9f3ebbf18178926b812b77a213a395f4ff8cddfc01085` |
| 行 × 列 | 246 × 38（不变） | 246 × 38（不变） |
| 变化单元格 | 无（首稿） | 仅 FEC 的 `conflict_status`、`notes` 两格 |
| `model_ready=true` 行 | 240，逐字节未变 | 240，逐字节未变（`FROZEN BENCHMARK VIOLATIONS: []`） |
| `data/processed/dielectric_v03_exclusions.csv` | — | 仅 FEC 行 `reason`/`evidence_b` 变化，5 条排除键不变 |

**重跑清单（真重跑，非重钉）**：`build_dielectric_v03.py`；三个轻量探针
（`nbs514_frequency_gate_audit`、`manual_appendix_reconciliation`、`nbs514_alpha_harmonization_probe`）
与 `g1plus_round5_crosscheck`；三个 ML 摘要
（`v032_ablation_summary`、`dielectric_v03_representation_ablation_summary`、`dielectric_onsager_delta_summary`）。
ML 摘要 diff **按文件**为：`v032_ablation_summary` 只有 `dataset_sha256`/`exclusions_sha256`；
`dielectric_v03_representation_ablation_summary` 为 `dataset_sha256`/`exclusions_sha256` 并新增 `source_path`/`source_sha256`；
`dielectric_onsager_delta_summary` 为 `dataset_sha256`/`generated_at`。**所有指标、折与预测逐字节未变**
——这是「FEC 不参与拟合」的独立证明。
⚠️ `v032_ablation_summary` 必须显式 `--source data/dielectric_v032.csv`，
否则默认取到 v0.3 roster 会导致 lineage accounting 失配（与 v0.3.12 §H 同型陷阱）。

### D. 本轮验证

`pytest -q -p no:cacheprovider` **741 passed**（含新增 FEC 温度归属 5 项与 Ue 2014 汇编层 5 项，
以及本地缓存哈希校验）；`ruff check .` 全绿；7 个 verifier 全绿
（`verify_dielectric_v03` digest = `a446c216…c01085`）；week7/week8 manifest 双 PASS；
`build_paper_full_draft` `--check` 与 `check_paper_artifact_consistency` 均通过。
注意：全量 pytest **不要加 `-X utf8`**，否则子进程 GBK 输出会令 25 个 DOI 注入测试假失败。

### E. Still open（不要误记为已解决）

- **Hagiyama et al. 2008**（DOI `10.1246/cl.2008.210`）本地仍无 PDF；只有汇编层与下游转述。
  曾有 agent 报告 OUP PDF 路径可读并给出 25 °C ≈ 107.4 / 40 °C ≈ 99，但**无任何可复核产物**，
  故未采纳入库；若后续采信必须先落盘 PDF 并复现。
- **MOPN**：缺独立一手确认 + GFN2-xTB 特征行。
- 受限目录 4 个未取值目标（EC/GVL/DME/环丁砜）；DC-200 成员表未接入；EC 的温度带决策（extended 313.15 K）。
- 环境现状：SpringerMaterials、上海有机所数据库打不开；RSC/ScienceDirect 部分刊无权限。

---

## 2026-09-25 · 诊断轮：4 条 `model_ready=true` 行的 xTB 特征为何失败（v0.3.14 前置）

**本轮只做只读诊断，不改任何冻结产物**（数据集、特征表、digest、排除单、交付包、论文草稿一律未动）。

### 触发

清点"240 条 `model_ready=true` vs 236 行拟合集"的差额时发现：差额那 4 行早就被记录为
`failed_physical_feature_count = 4`，四个分子名也在
`probes/dielectric_v03_representation_ablation_summary.json` 和
`probes/artifacts/v03_features_baseline_input.csv`（`status=error`）里，
但**全仓没有任何产物解释过它们为什么失败**——只有一句 `xTB failed ... with exit code 128`。

### 确认的缺陷（可复现）

四个失败分子**全部是多片段物种**，而 `generate_3d_xyz()` 对整个不连通图只调用一次 `EmbedMolecule`。
从 git-ignored 缓存 `data/interim/xtb_features/<InChIKey>/input.xyz` 实测**跨片段**最短原子间距：

| 分子 | 片段数 | 现管线跨片段最短距离 |
| --- | ---: | ---: |
| 1,3-二甲基咪唑鎓二甲基磷酸酯 | 2 | 0.163 Å |
| 1-丁基-3-甲基咪唑鎓六氟磷酸盐 | 2 | 0.762 Å |
| 1-丁基-2,3-二甲基咪唑鎓六氟磷酸盐 | 2 | 0.840 Å |
| 五羰基铁 | 6 | 0.000 Å |

四条起始几何在物理上都不可能存在。已记录到的 xTB 表现分两类：五羰基铁被直接拒绝
（`Found *very* short distance of  0.000E+00`），三个离子液体 SCF 不收敛
（`scf: Self consistent charge iterator did not converge`）。
**四条失败都能追到同一段嵌入代码的几何缺陷；但复跑显示缺陷消除后四条仍全部 exit 128，故几何缺陷真实存在、并足以让 xTB 在五羰基铁上直接拒绝起始几何，却不能单独解释三个离子液体的 SCF 失败。**

### 修法的验证与边界

逐片段嵌入 + 按片段半径打包（padding 3.0 Å）把跨片段最短距离提到
3.850 / 4.328 / 4.136 / 3.000 Å，最近原子对重新变回片段内正常键。
**但四条重跑 xTB 仍是 exit 128**，残余问题性质不同：

- 三个离子液体即便从合法几何出发仍不收敛；本轮只证明“几何修法不足以解锁”，未确定应采用哪种 SCF 策略，
  故不报告 HL-Gap 等数值。
- 五羰基铁的 SMILES 忠实转写自 `InChI=1S/5CO.Fe`，根本不含 Fe–C 键（即"5 个孤立 CO + 自由铁"），
  属**结构表示问题**；`O=C=[Fe](=C=O)(=C=O)(=C=O)=C=O` 能通过 RDKit 净化但无法嵌入，`[Fe](C#O)...` 才触发价键检查，故单纯换 SMILES 不够。

### 为什么不落地代码修改

改 `generate_3d_xyz()` 会改变多片段分子的特征值，令冻结的特征表与代码不再自洽；
而修法本身又不足以救回这 4 行。因此修法只以探针形式提供，落地需作为独立一轮 v0.3.14。

### 产物

| 文件 | 作用 |
| --- | --- |
| `probes/xtb_fragment_geometry_defect.py` | 诊断 + 打包修法；`--check` 校验证据，`--check-cache` 用本地缓存实测 |
| `probes/g1plus_xtb_fragment_geometry_defect.json` | 结构化证据（含逐字 xTB 报错与全部实测距离） |
| `reports/g1plus_xtb_fragment_geometry_defect.md` | 本报告 |
| `tests/test_xtb_fragment_geometry_defect.py` | 15 项回归（含"4 条失败行都是 model_ready=true"与"240−4=236"；缓存缺失时自动 skip） |

### 验证快照

定向用例 `tests/test_xtb_fragment_geometry_defect.py` **15 passed**；
探针 `--check` 通过；`--check-cache` 用本地缓存实测 **4/4 全部复现**记录值。

---

## 2026-09-25 · 恢复可行性判定轮：这 4 行能不能救回（v0.3.14 前置，第 2 轮）

**本轮仍只做只读诊断 + 本地 xTB 复算，不改任何冻结产物**（数据集、特征表、digest、排除单、交付包、论文草稿一律未动；4 行仍不进拟合集）。

### 判据修正（上一轮探针的一处错误）

上一轮把「成功」定义为 stdout 出现 `normal termination of xtb`，因此把一批 run 记为未正常终止。**该判据需要修正**：
xTB 6.7.1 把该串打印到 **stderr**（实测 stderr 逐字 `b'normal termination of xtb\r\n'`），而冻结运行器
`scripts/run_xtb_physical_features.py:279-285` 在 stdout 无标记串时，只要存在 `.xtboptok` 就把标记串补进文本再解析。
抽检冻结成功产物 `data/interim/xtb_features/AFBPFSWMIHJQDM-UHFFFAOYSA-N/xtb.out`（42 614 字节）确认不含该串、但哨兵文件在。
本轮探针改为**逐字对齐冻结运行器**的接受判据：`exit==0` ∧ `xtbopt.xyz` 存在 ∧（stdout 标记 ∨ `.xtboptok`）∧ 四个特征全部解析成功。

### 离子对：4 个协议对三者全部被接受（其中 3 个几何全部收敛；另有 1 个只对 2/3 成功）

起点为逐片段打包几何。冻结口径与 `--acc 5.0` 三个分子全部 exit 128；
`--etemp 1000`、`--etemp 5000`、`--etemp 5000 --acc 5.0`、`--alpb acetonitrile` 三个分子全部被接受。
其中 `--etemp 5000`（梯度 0.00044–0.00056 Eh/α）与 `--alpb acetonitrile`（0.00040–0.00070 Eh/α）两个**单项**改动
都让三个分子同时被接受、且几何优化全部收敛；
`--etemp 1000` 有两个分子几何优化未收敛（0.0018 / 0.0051 Eh/α）。
GFN-FF 预优化对 2/3 有效（1-丁基-3-甲基咪唑鎓 PF₆ 仍 exit 128）。
**仅放宽 SCC 阈值（`--acc 5.0`）单独使用不管用** ⇒ 原失败不是阈值太严，而是默认 300 K 电子温度下电荷分离体系的 SCF 行为。

### 五羰基铁：上一轮「单纯换 SMILES 不够」需要上调

找到 **至少 4 个**同时满足「净化成功 + 单片段 + 含 Fe–C 键 + 可嵌入」的结构（**不构成穷尽性证明**），最优为
`[Fe](<-[C]=O)(<-[C]=O)(<-[C]=O)(<-[C]=O)<-[C]=O`：
分子式 `C5FeO5`、总形式电荷 0、5 条 C→Fe 配位键、Fe–C 键长 2.0914–2.1328 Å；
默认 ETKDG（seed 42）返回 -1，打开 `useRandomCoords=True` 返回 0。
该族写法用中性 `[C]=O` 配体绕开中性 `C#O` 里 O 三价的净化错误；**这是一个建模选择**——
库存 `InChI=1S/5CO.Fe` 根本表达不出 Fe–C 配位作用。

### 决定性对照：拯救协议不是协议中立的

取三个在冻结协议下本来就成功的分子，从**各自的冻结起始几何**出发、只改一个标志位（`--etemp 5000`），比较四个特征：

| 对照分子 | 偶极 | HL-Gap | 极化率 | 总能量 |
| --- | ---: | ---: | ---: | ---: |
| 丙-1-醇 | 0.0000% | 0.0000% | 0.0000% | 0.0000% |
| N-甲基苯胺 | 4.25% | 0.93% | 0.0004% | 0.0046% |
| 三乙基戊基铵 双(三氟甲磺酰)亚胺（离子液体） | **40.36%** | **82.78%** | 0.0043% | 0.0657% |

最大相对位移 **82.8%**，出现在**同类体系（离子液体）的 HL-Gap** 上；丙-1-醇的偶极与 HL-Gap **完全未变**，
极化率与总能量只有 **1e-8 量级**漂移（四舍五入显示为 0.0000%）。
⇒ 位移**不是全表统一的**，因此**全表统一的「每特征加常数」式校正**被排除；
**但只排除到那儿为止**——按类别分别校准、分层建模、或给这 4 行单列补偿项都**没有被排除**，且本轮只有**一个**离子液体对照。
该离子液体对照在 `--etemp 5000` 下几何优化亦不再收敛，说明偏移伴随物理状态改变，不只是数值噪声。

### 判定

**这 4 行技术上可救回，但不能在原地救回。** 只对新行换口径 ⇒ 引入按分子类别分布的系统偏差隐患（本轮仅一个离子液体对照）；
全表换口径 ⇒ **不能假定逐行逐特征都会变**（丙-1-醇的偶极与 HL-Gap 已实测完全未变），236 行拟合集与全部基准必须整表重跑后重钉。
因此 v0.3.14 若落地，必须定位为**整表协议迁移**，而不是「补 4 行」的增量修复。本轮不替项目做这个取舍。

### 产物

| 文件 | 作用 |
| --- | --- |
| `probes/xtb_recovery_probe.py` | 策略矩阵 + 结构筛查 + 协议敏感性对照；`--check` 校验不变量 |
| `probes/g1plus_xtb_recovery_probe.json` | 结构化证据（逐条 argv、exit code、梯度范数、四个特征值） |
| `reports/g1plus_xtb_recovery_feasibility.md` | 本轮报告 |
| `tests/test_xtb_recovery_probe.py` | 15 项回归 |

### 验证快照

定向用例 `tests/test_xtb_recovery_probe.py` **15 passed**；`--check` 通过；
Fe(CO)₅ 的结构空间另由第二路**只读** agent 独立扫描，结论与本轮一致。

### 收口复审（adversarial-review-optimize，只读 Reviewer）

在 `d3de14c` 冻结基线上，只读复审员审计本轮报告、结构化证据与成果汇总稿，判 **Not Ready（0 Critical / 4 Important / 2 Minor）**；4 项 Important 经本地逐条复核**全部成立**并已最小修复：

| 级别 | 位置 | 问题 | 修复 |
| --- | --- | --- | --- |
| Important | 报告 `:15` | 「有 5 个可复现协议」与 JSON 冲突：对三者**全部接受**的是 4 个，**接受且几何全收敛**的是 3 个 | 改为 4 个全部接受、其中 3 个几何全收敛 |
| Important | 报告 `:23`、本节标题、汇总 §15.2/§16 | 「4 个协议对三者全部成功」把「运行器接受」压缩成「成功」，易误读为几何全收敛 | 统一改为「全部被接受（其中 3 个几何全部收敛）」 |
| Important | 报告 `:119`、本节「判定」段、汇总 §15.5 | 「四个特征逐行都会变」与本轮 JSON 直接冲突：丙-1-醇的偶极与 HL-Gap 绝对/相对变化均为 0 | 改为「不能假定逐行逐特征都会变」并举丙-1-醇反例，保留「须整表重跑重钉基准」的结论 |
| Important | 汇总 §12 表 | 「当前工作区」表仍写 `756 passed` | 改为当前 `771 passed`，756/753 标为历史轮次快照 |

**Delta 复审新发现（1 Important，已修）：** 报告 §五原把 `GFN-FF 预优化` 与 `--etemp 5000` / ALPB 并列为三者统一替代方案；
但同一报告的 §2.2 表格与 JSON 都显示 GFN-FF 预优化只对 2/3 有效（`IXQYBUDWDLYNMA-UHFFFAOYSA-N` 仍 `exit 128`）。
已改为「`--etemp 5000` 或 `--alpb acetonitrile`（这两者对三者都既被接受又几何收敛）」，
并显式注明 GFN-FF 只对 2/3 有效、不能作为三者统一替代。

本地复核用的判据（可复现）：对 `probes/g1plus_xtb_recovery_probe.json` 逐策略统计三者
「全部 `frozen_runner_accepts`」= 4 个（`etemp_1000`、`etemp_5000`、`etemp_5000_acc_5`、`alpb_acetonitrile`），
「全部接受且 `geoopt_converged`」= 3 个；`etemp_1000` 只在 1/3 上收敛，GFN-FF 预优化只对 2/3 成功。

**残留 Minor（已于收官优化轮关闭）：** `probes/g1plus_xtb_recovery_probe.json` 的 Fe 结构记录原先只保存重试后的
`embed_return`，未分列 `default_embed_return` / `random_coords_embed_return`，也没有形式电荷与 Fe–C 键型/方向字段。
复审员独立重跑 RDKit 已确认报告声明（默认嵌入 -1 / 随机坐标 0 / 净电荷 0 / 5 条 C→Fe DATIVE）**本身属实**，
影响限于结构化证据的可审计性。

收官优化轮已补齐该缺口：`screen_fe_candidate()` 分别记录 `default_embed_return` 与
`random_coords_embed_return`、`formal_charge`，并从**分子图**（而非构象）取 `fe_c_bond_types`
（含 `C->Fe:DATIVE` 这样的方向与键级），因此**即使嵌入失败也能读出键型**。
`check_payload()` 新增对应不变量（首次即成功不得记成重试、默认失败必须配平重试、
`has_fe_c_bond` 必须与键型列表一致、可测时键型数须等于键长数）；
`tests/test_xtb_recovery_probe.py` 新增 `test_embed_attempts_charge_and_dative_direction_are_recorded`，
固定最优候选的 `-1 / 0 / 0 / 5×C->Fe:DATIVE` 与库存值的 `6 片段 / 无 Fe–C 键`。
JSON 只重算了 `fe_structures` 段（`--fe-structures --write`），xTB 派生的 `ion_pairs` 与
`protocol_sensitivity` 两段未被触碰；规范数据集 digest 不变。

**计数复核（复审员独立执行）：** `reports/*.md` 54、`probes/*.json` 67、week1–8 递归 Markdown 72 / JSON 73、
week7 61 文件 / 60 manifest 行、week8 75 文件 / 74 manifest 行、
`data/dielectric_v03.csv` digest `a446c216…c01085`，均与文档一致。
