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
- The conservative applicability rule flags `HBD >= 1` and predicted
  dielectric `> 60` as `outside_associated_liquid`. On the fixed 6,150 OOF
  predictions, 6,120 rows remain inside the domain and 30 are marked outside.
  This is a disclosure boundary, not a new model score.
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
