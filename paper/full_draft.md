# Abstract

We present an auditable, machine-learning-ready dataset of static dielectric
constants (relative permittivities) for 246 pure organic liquids at near-room
temperature (293.15-303.15 K). The dataset is assembled from three sources:
the NIST ThermoML archive (v0.1, 100 compounds), NBS Circular 514 (v0.2, 210
compounds), and open-access review tables and primary literature covering
modern battery solvents (v0.3.3, 246 compounds), plus one non-redistributable
publisher-compilation value retained only as a numeric fact and explicitly
flagged. Every row carries deterministic
source provenance, gate-flag metadata, and conflict status, with license and
redistribution metadata recorded wherever the source supplies it. Conflicting public values are recorded rather than
averaged: nine rows carry an explicit conflict or unverified-provenance
record, six are flagged model_ready=false, and the benchmark withholds five
rows through a curated exclusion list.

A companion benchmark evaluates three representations (Morgan fingerprints,
13-dimensional physical features from GFN2-xTB and RDKit, and their
equal-weight hybrid) under fixed 10x5 repeated cross-validation,
scaffold/cluster holdout, and an external domain-gap test on 29 battery-relevant
solvents. The v0.3.2 benchmark is carried into the v0.3.3 candidate with one
integrity change: rows the dataset flags `model_ready=false` are now withheld
from every fit, which removes vinylene carbonate and takes the fitted set from
237 to 236 rows. The selected XGBoost Morgan+Physical hybrid on the raw target
achieves R2 0.364, Spearman 0.828, and MAE 6.69 on those 236 rows. A paired
control that freezes the v0.3 fold assignment and appends the two added battery
carbonates to the training folds only attributes +0.0059 R2 (95% CI -0.002 to
+0.013, p = 0.11) to the data addition -- a gain indistinguishable from zero --
and both added solvents remain outside the model's extrapolation range. All builds and verifiers are
deterministic and reproducible in continuous integration.

# Background and Summary

Battery electrolyte development requires accurate solvent permittivity data:
dielectric constant directly influences salt dissociation, ion pairing, and
ionic conductivity. Existing public resources for organic liquid permittivities
are fragmented across the NIST ThermoML archive (machine-readable but
limited near-room-temperature coverage), NBS Circular 514 (comprehensive but
published in 1951 as scanned tables), historical compilations (not
machine-readable), and individual journal articles (heterogeneous formats and
access conditions). Commercial databases (SpringerMaterials, Knovel) offer
broader coverage but under restrictive licenses that prevent redistribution
and limit reproducibility.

The Chodera lab (2015, arXiv:1506.00262) demonstrated that ThermoML could
supply static dielectric constants for force-field benchmarking, extracting
approximately 45 near-room-temperature pure-compound records. This extraction
established the feasibility of a public dataset but did not target
ML-ready formatting, battery-solvent coverage, or multi-source cross-validation.

The present dataset addresses these gaps by:
- Aggregating three independent public sources (ThermoML, NBS Circular 514,
  open-access literature) into a single auditable table.
- Recording deterministic provenance (DOI, page, table, temperature-source
  status, license, redistribution conditions) for every row.
- Maintaining explicit conflict records: disagreeing values are stored, never
  averaged, and the withholding decision is recorded per row rather than
  applied as a blanket rule. The benchmark withholds the five rows on the
  curated exclusion list and, since v0.3.4, every row the table flags
  `model_ready=false` as well; no flagged row is fitted.
- Providing a fixed multi-repeat cross-validation framework with three
  representations (fingerprint, physical descriptor, hybrid) and two targets
  (raw, log-transformed).
- Evaluating the frozen v0.2 model on an external domain-gap test of 29
  battery-relevant solvents, directly measuring how well a model trained on
  classic organic compounds generalizes to electrolyte-relevant chemical space.

The candidate model is intentionally conservative (shallow XGBoost with
equal-weight Morgan+Physical ensemble). Graph neural networks and deeper
architectures are evaluated as probes (MLP, Chemprop D-MPNN) but are not
promoted to the candidate model. The benchmark results establish a clear
representation ceiling: physical features provide the ranking signal
(Spearman 0.802 for Physical alone vs. 0.722 for Morgan), fingerprints
provide complementary breadth (R2 0.240 vs. 0.342), and their hybrid ensemble
outperforms either alone (R2 0.364, Spearman 0.828). Neural probes confirm
this ceiling: the best MLP (Physical, Spearman 0.884) outperforms XGBoost in
ranking but has negative R2 that is not recoverable by linear calibration.

The primary contribution is the curated, auditable dataset itself, not a claim
that small-data models solve static permittivity prediction. The remaining
public-data gaps are narrow and explicit: 3-methoxypropionitrile rests on a
secondary compilation with no traceable primary measurement, and
fluoroethylene carbonate now carries a primary 78.4 measurement at 296.15 K (Kobayashi et al. 2003, Table 2) while the competing 107 is now read at compilation level in Ue et al. (2014, Table 2.3) and its named primary source (Hagiyama et al. 2008) remains unread; the previously stored 102 was its flash point, not a permittivity. The glyme diethers
and the dinitriles (adiponitrile, glutaronitrile) that earlier internal reports
listed as absent are present in the table under their IUPAC names. These open
gaps are explicit targets for the v1.1 revision.

# Methods

## Dataset scope

The dataset collects static (zero-frequency or low-frequency) dielectric constant
measurements for pure organic liquids in the near-room-temperature window
293.15-303.15 K. Each entry is a single compound at a single temperature.
Multi-temperature records are stored as separate rows with the temperature as
an explicit feature.

All molecular structures are standardized with RDKit (version 2024.09): salt
stripping, charge neutralization, canonical SMILES generation, and InChIKey
assignment. Every row carries a gate-flag vector recording source type
(experimental, compilation, review), frequency regime (zero-frequency,
static-equivalent, unspecified), phase (pure liquid), purity information, and
conflict status.

## Source construction

The dataset was assembled in three incremental versions, each independently
buildable and verifiable.

**Temperature bands.** The primary window is the closed interval
`293.15-303.15 K`, recorded as `temperature_band = room_temperature`. A second,
explicitly enumerated window `313.15-323.15 K` is recorded as
`temperature_band = extended_temperature` and is reserved for compounds that
cannot be measured as a liquid inside the primary window. The exception exists
because ethylene carbonate melts at about 36.4 C, so no room-temperature liquid
permittivity measurement of the pure compound exists. Its stored 90.5 at
313.15 K is the only extended-band row in v0.3, and it is labelled rather than
silently folded into the main window. No other compound may use the extended
band, and extended-band rows are reported separately so a reader can remove
them without editing the dataset.

**v0.1 (100 compounds).** Extracted from the NIST ThermoML archive
(https://trc.nist.gov/ThermoML/) using the thermoml-io parser. Only
zero-frequency, pure-component observations within 293.15-303.15 K were
retained. The extraction shares 45 keys with Chodera et al. (2015)
arXiv:1506.00262 from the same archive, and that 45-record overlap is the figure
quoted in the cross-check below; v0.1 itself holds 100 compounds.

**v0.2 (210 compounds).** Added manually curated records from NBS Circular 514
(Maryott & Smith, 1951, https://doi.org/10.6028/nbs.circ.514), a critical
compilation of static dielectric constants for 822 organic compounds. Each NBS
entry was manually transcribed with its page number, figure quality, and
selection rank from the circular's own ranking system. All v0.2 rows carry
the gate flag nbs514_circular_514.

**v0.3 (243 compounds).** Added 33 publicly accessible values from:
- Six n-nitriles from Helambe et al. (1995) Pramana
  (https://doi.org/10.1007/BF02848094), open access.
- Four NBS Circular 514 records that were eligible in v0.2 but remained below
  the selection cutoff.
- Twenty-three values from CC-BY and CC-BY-NC review tables and open-access
  articles published 2024-2026, covering modern battery solvents: carbonates
  (EMC), cyclic ethers (DOL, THF, 2-MeTHF), lactones (GVL), phosphates (TEP,
  TMP), fluorinated ethers (TTE, BTFE, HFE), nitriles, chlorinated diluents,
  and fluorinated carbonates (FEC, VC).

**v0.3.2 (245 compounds).** Added the two decisive battery carbonates that were
absent from every earlier revision:
- Propylene carbonate (PC, epsilon=64.9 at 298.15 K) from Simeral & Amey (1970)
  J. Phys. Chem. 74, 1443 (https://doi.org/10.1021/j100702a008).
- Ethylene carbonate (EC, epsilon=90.5 at 313.15 K) from Chernyak (2006)
  J. Chem. Eng. Data 51, 416 (https://doi.org/10.1021/je050341y); EC melts at
  36.4 C, so the measurement is flagged extended_temperature (the only
  extended-band row in v0.3; see the temperature-band rule above).

**v0.3.3 (246 compounds).** Adds one row and repairs provenance. The new row is
3-methoxypropionitrile (epsilon=36.0 at 298.15 K), transcribed from the ECW-308
battery-solvent supporting information (Wang & Shi, Adv. Funct. Mater. 2023,
https://doi.org/10.1002/adfm.202212342). No traceable primary measurement was
found for it, so it is flagged secondary_compilation_unverified with
model_ready=false. v0.3.3 introduced the reproducible provenance-patch
layer (data/processed/dielectric_v03_provenance_patches.csv) with 30 patches
that restore the source-priority decisions and conflict records that earlier
hand-edits had lost; the current v0.3.14 layer applies 38 (the D2 scope relabel
added 8 rows).

Every v0.3 addition records its source DOI, table or section identifier,
temperature-source status, and any license or redistribution metadata the
source supplies. Review-
table values that do not state an independent measurement temperature are
flagged with review_table_standard_room_temperature and are distinguished from
primary-literature values.

The restricted SpringerMaterials Interactive database (Landolt-Bornstein
series) was used as cross-check evidence only, and no subscription-restricted
SpringerMaterials value was promoted into the public dataset. The two values
that do come from paywalled primary articles (FEC 78.4 and vinylene carbonate
126) are individual measurement facts; their source PDFs are kept outside the
repository and are not redistributed.

ECW-308 (Wang et al., Adv. Funct. Mater. 2023, DOI
10.1002/adfm.202212342) was retrieved from a non-redistributable publisher
supplement and used only as a secondary cross-check. It reproduces PC 64.90
exactly, reports EC 89.00 at a different temperature (25 C versus the stored
313.15 K), supports the glyme values, and disagrees with the retained primary
nitrile values. No ECW-308 numeric value replaces a primary row.

## Conflict handling

When independent public sources disagree materially, the conflicting values
are recorded and the row is flagged; conflicts are never averaged. Nine rows
carry an explicit conflict_status and six are flagged model_ready=false. The
benchmark withholds five rows through a curated exclusion list
(data/processed/dielectric_v03_exclusions.csv): FEC (primary 78.4 at 296.15 K,
107 read at compilation level in Ue et al. 2014, Table 2.3, with named primary
Hagiyama et al. 2008 still unread, with no open full text discoverable as of 2026-09-25 (the DOI resolves to Oxford University Press as a closed-access article, and J-STAGE returns 404 for both the article pattern and the journal root), and a 2007 downstream paper restating the
same 78.4 leg as 40 C that the primary table footnote "At 23 C." overrides), TEP (10, 13), TMP (10, 21.6), ethyl isothiocyanate
(NBS 19.5 at 294.15 K vs.
restricted cross-check 29.7 at 293.2 K), and 3-methoxypropionitrile (ECW-308
secondary compilation 36.0, awaiting primary confirmation). A sixth row,
vinylene carbonate, is withheld by the `model_ready` gate itself. Methyl propionate (NBS 5.5 vs. review
6.2) is also documented and retained. Adiponitrile and glutaronitrile retain
their ThermoML primary values (32.12 and 34.6); ECW-308 compilation values
(30.00 and 37.00) are recorded as disagreements, not replacements.

Vinylene carbonate now carries a primary measurement of 126 +/- 1.0 at 25 C
(Saadi & Lee 1966, Table 2; stored as 298.0 K) with the conflict recorded as
knovel_78_127_interval_contains_primary_value. Flamme et al. 2017 repeats the
same primary source, so it is same-source repetition rather than independent
corroboration. Since the v0.3.4 revision the modelling gate honours the
model_ready flag, so this row is withheld from every fit. 3-methoxypropionitrile
has no physical-feature row, so it is absent from the fitted set for that reason
alone.

## Physical features

GFN2-xTB (xtb version 6.7.1) was used to compute gas-phase dipole moment and
molecular polarizability for each compound. The Onsager-inspired feature
mu_sq_over_Vm (dipole moment squared divided by molar volume) is the primary
physical descriptor. Molar volume is estimated from the xTB-optimized geometry.

RDKit-computed features include: molecular weight, rotatable bond count,
hydrogen-bond donor and acceptor counts, heavy atom count, ring and aromatic
ring counts, fraction of sp3 carbons, and topological polar surface area.

For 66 of 205 successful physical-feature rows, an experimental-density variant
replaces the xTB-estimated molar volume with a ThermoML density observation
within 10 K of the target temperature. This variant is stored separately and
shows no detectable improvement in any metric on the 66-compound subset.

## Models and validation

All models use a fixed 10x5 repeated cross-validation (random state 42),
ensuring every probe and baseline shares identical train-test splits.

**Primary model.** XGBoost (version 2.1) with n_estimators=200, max_depth=2,
learning_rate=0.05, colsample_bytree=0.8, subsample=0.8, reg_lambda=1.0.
Three representations are compared:
- Morgan: ECFP4-like count fingerprints (radius 2, 2048 bits).
- Physical: the 13-dimensional feature vector described above.
- Hybrid: equal-weight ensemble of independently trained Morgan and Physical
  models.

Raw-scale and log(epsilon - 1) targets are evaluated for each representation.

**Neural baselines.** A single-hidden-layer MLP (64 neurons, ReLU, Adam,
early stopping) is trained on the same representations and folds. Its best
representation (Physical) achieves Spearman 0.884 but negative R2 (-0.172).
A pre-registered linear calibration probe (intercept + slope fitted within
each training fold) did not recover positive R2 (-0.309 after calibration),
confirming a true negative result.

Chemprop 2.1.0 D-MPNN (BondMessagePassing, MeanAggregation, 50 epochs) is
evaluated in an isolated environment (NumPy 1.x constraint) on the same outer
folds. Mean R2 is 0.237 and Spearman 0.665.

**Extrapolation benchmark.** A scaffold/cluster holdout groups ring compounds
by Murcko scaffold and acyclic compounds by ECFP4 Butina clustering, repeated
over five balanced partitions. The log-target Physical representation has the
best mean R2 (0.267 +/- 0.014) under this holdout.

A pre-registered leave-EC-out sensitivity probe is reported in
`reports/d1_leave_ec_out_sensitivity.md`; it is report-only and cannot change
the v1.0 model.

## Applicability domain

A prediction is flagged outside_associated_liquid when the compound carries at
least one hydrogen-bond donor site, counted with the SMARTS pattern
`[O,S,N;!H0]` directly from the structure; a prediction below 1.0 is flagged
outside_nonphysical. The donor count is structural, so the boundary is
independent of any model output. The rule triggers on 2,070 of the 6,150
out-of-fold rows (33.66%). This is a disclosure boundary: donor sites indicate
that Kirkwood correlation effects, which require multi-body or
explicit-solvent descriptions, are likely dominant. Two alternative
formulations -- the original `predicted dielectric > 60` rule and a
model-independent Onsager estimate -- were measured and rejected; both are
recorded with their numbers in `probes/applicability_domain_summary.json` and
`reports/applicability_domain_veto_fix.md`.

# Data Records

All dataset versions, intermediate tables, and probe outputs are stored in the
GitHub repository at https://github.com/LittleAlety/electrolyte-solvent-dielectric-ml.

## Core dataset files

### data/dielectric_v03.csv (246 compounds)

The current table (dataset version 0.3.3). It is a strict superset of v0.3.2:
the only added row is 3-methoxypropionitrile, flagged
secondary_compilation_unverified and model_ready=false. Each row contains:

- **Structural identifiers**: InChIKey, canonical SMILES, common name.
- **Measurement**: dielectric constant (epsilon), temperature (T_K, K),
  uncertainty (value, kind, confidence level) when reported.
- **Source provenance**: source_doi, source_dois_all, source_url,
  source_citation, source_table, evidence_level (primary, open_access_review_table,
  open_access_article_text, v0.2_primary_or_critical_compilation).
- **Licensing**: redistribution_status, source_license, license_url,
  redistribution_conditions.
- **Quality flags**: gate_flags (pipeline-separated), source_quality
  (three_figures, four_figures, etc.), selection_rank, conflict_status.
- **Temperature metadata**: temperature_band, temperature_source.

### data/dielectric_v031.csv (243 compounds)

Superseded historical revision (v0.3.1) incorporating the first G1 data-gate
findings:
- Vinylene carbonate: model_ready demoted to false, conflict range 78-127.
- Ethoxybenzene: provenance promoted to primary (NBS Circular 514 p35:011
  eps=4.22 matches review 4.2).
- Methyl propionate: conflict opened (NBS 5.5 vs. review 6.2, 13% difference).

### data/dielectric_v032.csv (245 compounds)

Superseded by v0.3.3. Supersedes v0.3.1 by adding two decisive battery
solvents that were missing from all earlier revisions:
- Propylene carbonate (PC), epsilon=64.9 at 298.15 K, primary source traced to
  Simeral & Amey (1970) DOI 10.1021/j100702a008.
- Ethylene carbonate (EC), epsilon=90.5 at 313.15 K (liquid range), primary
  source DOI 10.1021/je050341y, flagged extended_temperature.
The glyme diethers (diglyme/triglyme/tetraglyme) and the dinitriles
(adiponitrile, glutaronitrile) that earlier reports listed as "absent" were
already present under their IUPAC names; they are now documented explicitly.

### data/dielectric_v02.csv (210 compounds)

The v0.2 predecessor built from ThermoML and NBS Circular 514.

## Derived data files

| File | Contents |
|------|----------|
| data/processed/dielectric_physical_features.csv | GFN2-xTB and RDKit features for 205 compounds |
| data/processed/dielectric_applicability_flags.csv | Per-row applicability flags (6150 = 205 compounds x 3 representations x 10 repeats; each row carries the held-out fold index) |
| data/processed/dielectric_mlp_probe_predictions.csv | OOF predictions from MLP probe |
| data/processed/dielectric_mlp_calibration_predictions.csv | OOF predictions from calibration probe |
| data/processed/dielectric_chemprop_predictions.csv | OOF predictions from Chemprop D-MPNN |

## Probe and verification outputs

| File | Description |
|------|-------------|
| probes/dielectric_v031_summary.json | v0.3.1 revision manifest |
| probes/dielectric_representation_ablation_summary.json | Full 10x5 CV metrics for all representations |
| probes/dielectric_mlp_probe_summary.json | MLP probe results |
| probes/dielectric_mlp_calibration_summary.json | Calibration probe results |
| probes/dielectric_chemprop_summary.json | Chemprop D-MPNN baseline |
| probes/g2_domain_gap_summary.json | Domain-gap external test (frozen v0.2 model) |
| probes/dielectric_density_feature_summary.json | Experimental-density comparison |
| probes/dielectric_target_scaffold_summary.json | Scaffold/cluster holdout benchmark (v0.2, 205 rows) |
| probes/v032_target_scaffold_summary.json | v0.3.2 target-transform and scaffold benchmark (236 rows) |
| probes/v032_ablation_summary.json | v0.3.2 main ablation benchmark (236 rows) |
| probes/v032_controlled_comparison_summary.json | Paired PC/EC train-only control |
| probes/dielectric_leave_ec_out_sensitivity.py | Pre-registered leave-EC-out sensitivity probe |
| probes/dielectric_leave_ec_out_summary.json | Report-only sensitivity metrics for the EC single-row removal |
| probes/artifacts/dielectric_leave_ec_out_predictions.csv | 14,160-row leave-EC-out prediction table |
| scripts/verify_d1_leave_ec_out.py | Independent 8/8 verifier for the leave-EC-out artefact |
| probes/dielectric_v03_summary.json | v0.3.3 build manifest, patches and SHA256 |
| reports/g1_data_gate_review.md | G1 conflict list and provenance changes |

## Known gaps (for v1.1)

**Fluoroethylene carbonate (FEC).** Withheld from model fitting through the
curated exclusion list because the competing 107 is available only through the Ue et al. 2014 compilation (Table 2.3), while its named primary source (Hagiyama et al. 2008) remains unread. The
stored value is now a primary 78.4 at 296.15 K (Kobayashi et al. 2003, Table 2);
the previously stored 102 was its flash point, not a permittivity.

**3-Methoxypropionitrile (MOPN).** Present in the table as a flagged,
non-model-ready row (36.0 at 298.15 K, secondary_compilation_unverified). Tier-0
checks over all 242 local ThermoML dielectric files and all 636 transcribed NBS
Circular 514 organic rows returned no permittivity observation for it. The value
rests on the ECW-308 battery-solvent compilation, and its cited primary source
(Perricone et al. 2013, https://doi.org/10.1016/j.electacta.2013.01.084) is
closed access, with no open full text discoverable as of 2026-09-25. It is the
single named solvent gap. Tier-3 (print handbooks and physical library holdings)
and Tier-4 (subscription databases such as Reaxys, SciFinder-n and DIPPR) were
attempted but not closed this round; every open item is blocked by entitlement or
entry point rather than by an absent value, and the blocking evidence is recorded
in `reports/g1plus_tier34_access_findings.md`.

**Resolved gap reports.** The glyme diethers and the dinitriles that earlier
internal reports listed as absent are present in the table under their IUPAC
names (diglyme = 2,5,8-trioxanonane, and so on); those reports were wrong about
absence, not about the underlying measurements. The open items above constitute
explicit targets for the next dataset revision.

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

# Benchmark Tables

## Main benchmark: 10x5 repeated cross-validation (v0.3.2 benchmark, 236 fitted rows)

| Representation | Target | R2 | MAE | Spearman | AUC (eps > 30) | MAE (eps < 20) |
|---|---|---|---|---|---|---|
| Constant (train-fold mean) | raw | -0.012 | 11.75 | — | — | 7.84 |
| Morgan (ECFP4) | raw | 0.240 | 7.61 | 0.722 | 0.837 | 4.38 |
| Physical (13-dim) | raw | 0.342 | 7.10 | 0.802 | 0.937 | 4.33 |
| Morgan+Physical | raw | **0.364** | **6.69** | **0.828** | 0.933 | 3.95 |
| Morgan | log(eps-1) | 0.187 | 7.32 | 0.766 | 0.845 | 3.20 |
| Physical | log(eps-1) | 0.290 | 6.37 | 0.880 | 0.926 | 2.70 |
| Morgan+Physical | log(eps-1) | 0.293 | 6.27 | 0.878 | 0.927 | 2.55 |

The reference row is a constant predictor set to the training-fold mean on the
same 10x5 folds, recomputed from `data/processed/v032_ablation_predictions.csv`.
The 236 fitted rows are the 241 featurized v0.3.2 rows minus four xTB failures
and minus vinylene carbonate, which the dataset flags `model_ready=false`;
`read_modelling_rows` withholds it and reports it separately.
It replaces an earlier `Dummy (mean)` row whose 21.66 MAE could not be
reproduced from any committed artifact. A constant predictor has no ranking
signal, so its Spearman and AUC are undefined rather than 0.5.

The equal-weight Morgan+Physical hybrid on the raw target is the v0.3.2
candidate model. It is selected for its consistent rank across all metrics, not
for a single best score. The log(eps-1) target improves the Physical
representation but does not transfer to the hybrid.

## Neural baselines (205-row v0.2 feature table, same 10x5 folds)

These rows were computed on `data/processed/dielectric_physical_features.csv`
(205 compounds, v0.2). They were **not** recomputed on the v0.3.2 236-row folds,
so they may only be compared against like-for-like 205-row XGBoost references.
They also predate the `model_ready` gate, which the 205-row v0.2 table never
triggers (no v0.2 compound is flagged).

| Model | R2 | MAE | Spearman | AUC (eps > 30) |
|---|---|---|---|---|
| MLP-Morgan | -0.447 | 12.81 | 0.170 | 0.563 |
| MLP-Physical | -0.172 | 7.43 | **0.884** | 0.940 |
| MLP-Hybrid | -0.458 | 12.89 | 0.228 | 0.646 |
| MLP-Physical (calibrated) | -0.309 | 7.81 | 0.865 | 0.937 |
| Chemprop D-MPNN | 0.237 | 7.89 | 0.665 | 0.857 |

MLP-Physical achieves the highest Spearman correlation across all models (0.884)
but with negative R2. A pre-registered linear calibration probe did not recover
positive R2, confirming this as a ranking-only representation ceiling.
Chemprop D-MPNN R2 (0.237) exceeds the like-for-like 205-row v0.2 Morgan
XGBoost baseline (0.203) but its Spearman (0.665) is lower than both Morgan
(0.697) and Physical (0.821) on that same 205-row table, reinforcing that graph
representations carry fingerprint-level information while physical features
drive ranking quality. The neural rows are retained as representation-ceiling
evidence on the v0.2 feature table; they were not recomputed on the v0.3.2
236-row fold set.

## Extrapolation: scaffold/cluster holdout (v0.3.2, 236 rows)

Source: `probes/v032_target_scaffold_summary.json` (ring Murcko scaffolds plus
acyclic ECFP4 clusters, five balanced partitions). These values supersede the
older 205-row scaffold table.

| Representation | Target | R2 | MAE | Spearman |
|---|---|---|---|---|
| Morgan | raw | 0.138 +/- 0.014 | 9.097 +/- 0.239 | 0.597 +/- 0.014 |
| Physical | raw | 0.268 +/- 0.051 | 8.082 +/- 0.317 | 0.747 +/- 0.016 |
| Morgan+Physical | raw | 0.295 +/- 0.027 | 7.806 +/- 0.105 | 0.756 +/- 0.017 |
| Morgan | log(eps-1) | 0.130 +/- 0.020 | 8.442 +/- 0.188 | 0.639 +/- 0.024 |
| **Physical** | **log(eps-1)** | **0.276 +/- 0.044** | **6.669 +/- 0.218** | **0.862 +/- 0.016** |
| Morgan+Physical | log(eps-1) | 0.261 +/- 0.029 | 6.885 +/- 0.129 | 0.838 +/- 0.015 |

Physical with log(eps-1) is the best representation for scaffold extrapolation,
confirming that physical descriptors generalize better to novel chemical
structures than fingerprint-based representations.

## Domain-gap external test: frozen v0.2 model on 29 new battery solvents

| Representation | R2 | Spearman |
|---|---|---|
| Morgan | 0.122 | 0.692 |
| RDKit Physical | 0.154 | 0.367 |
| Morgan+Physical (hybrid) | 0.286 | 0.590 |
| v0.2 CRV reference (hybrid) | 0.320 | 0.830 |

The external R2 of 0.286 (vs. 0.320 cross-validation) confirms that the v0.2
model partially generalizes to battery-relevant solvents. The systematic
underprediction of high-permittivity targets (GVL, NMP) directly visualizes
the domain gap that v0.3's expanded coverage aims to close.

# Figures

The v1.0 manuscript carries six figures. Each one names the artifact that holds
the rendered file and a committed command that re-renders it, so a reader can
reproduce every panel without the authors. Two of the six (Figures 1 and 4) are
produced by a purpose-built figure probe that fails when the numbers it draws
stop matching the committed summaries. Figures 2 and 5 expose a --plot-only mode
that re-renders them from their committed benchmark summaries without refitting a
model; Figures 3 and 6 are recomputed from the frozen inputs by the probes that
produced them. Panels that earlier drafts listed as
separate figures (chemical-space projection, applicability-domain error split,
cross-source scatter) are reported as tables or prose instead: they either
duplicated a panel above or rested on fewer than ten compounds, and a six-figure
budget is easier to audit than an eight-figure one that repeats itself.

**Figure 1. Dataset growth and source composition.**
Panel A: compounds in each released roster (v0.1 100, v0.2 210, v0.3 243,
v0.3.2 245, v0.3.3 246) with the 236-row modelling subset marked. That subset is
frozen on the v0.3.2 table and is re-derived in the figure as 245 rows - 4 rows
named in the five-row curated exclusion list that are present in that source -
4 rows failing the xTB physical features - 1 row
withheld by `model_ready` = 236.
Panel B: provenance mix of the current 246-row roster by `evidence_level` (208
v0.2 core values, 20 open-access review-table values, 17 open-access primary
measurements, 1 secondary compilation with no traceable primary source),
annotated with the gate counts (240 `model_ready=true`, 6 withheld), the single
extended-temperature row (EC at 313.15 K) and the 45 ThermoML rows that also
appear in the independent Chodera et al. (2015) extraction from the same archive.
Artifact: `probes/artifacts/paper_fig1_dataset_growth.png`.
Script: `python probes/paper_figure_dataset_growth.py` (the probe re-reads every
roster digest and fails if the row counts or the exclusion arithmetic drift).

**Figure 2. Main benchmark across representations and targets.**
R2, MAE, RMSE and Spearman rho for the Morgan, RDKit-physical and hybrid
representations under the frozen 10x5 repeated cross-validation on 236 rows,
with error bars of +/- 1 SD across the ten repeats. The hybrid representation is
the best of the three on R2 (0.364), Spearman (0.828) and MAE (6.69), and the
physical block is what carries the improvement over Morgan.
Artifact: `probes/artifacts/v032_ablation.png` (`probes/v032_ablation_summary.json`).
Script: `python probes/dielectric_representation_ablation.py --plot-only --summary-output probes/v032_ablation_summary.json --plot probes/artifacts/v032_ablation.png` (re-rendering this artifact from the committed summary reproduces the
tracked file byte for byte).

**Figure 3. Domain-gap parity plot.**
Frozen v0.2 model predictions against experimental permittivity for the 29
battery-relevant solvents added in v0.3, one panel per representation; points
whose absolute error exceeds 10 are labelled. On this external set the frozen
model reaches R2 = 0.122 (Morgan), 0.154 (RDKit physical) and 0.286 (hybrid).
The two worst calls are the polar solvents at the right edge: gamma-valerolactone
(36.1) and N-methylpyrrolidone (32.2) are both predicted near 13-16, the same
range as the non-polar diluents.
Artifact: `probes/artifacts/domain_gap_parity.png` (`probes/g2_domain_gap_summary.json`).
Script: `python probes/g2_domain_gap_test.py`.

**Figure 4. Split-conformal coverage is marginal and collapses above eps 60.**
Panel A: empirical coverage of the nominal 90% split-conformal interval inside
eps < 20 (n = 182), 20-60 (n = 47) and eps > 60 (n = 5), for the three
representations. Marginal coverage sits at the nominal level for all three
(0.9153-0.9156), but the same intervals cover 0.0145 (Morgan), 0.2568 (physical)
and 0.0382 (hybrid) of the eps > 60 compounds.
Panel B: re-scaling the residual by 1+|prediction| raises eps > 60 coverage to
0.1995, 0.4778 and 0.2881 respectively, and still does not restore nominal
coverage, because a marginal interval does not become conditional by rescaling
its width. The eps > 60 stratum holds five compounds, so these conditional
values are an exploratory diagnostic and are not claimed as a coverage
guarantee. The analogous failure of the point predictions is in the benchmark
tables: hybrid MAE is 3.9 below eps 20 and 63.8 above eps 60.
Artifact: `probes/artifacts/paper_fig4_conformal_strata.png`.
Script: `python probes/paper_figure_conformal_strata.py` (the probe fails if the
marginal guarantee stops holding or the high-permittivity collapse disappears).

**Figure 5. Target transform and scaffold/cluster holdout.**
R2, MAE, Spearman rho and AUC > 30 for random cross-validation against
scaffold/cluster holdout, crossed with the raw and log(eps-1) targets. Under
cluster holdout the physical and hybrid representations retain R2 = 0.27-0.29
where Morgan falls to 0.14, which is the quantitative form of the extrapolation
claim: what survives leaving the scaffold neighbourhood is the physical block,
not the fingerprint. Error bars are +/-1 SD across the five partitions.
Artifact: `probes/artifacts/v032_target_scaffold.png` (`probes/v032_target_scaffold_summary.json`).
Script: `python probes/dielectric_target_and_scaffold.py --plot-only --summary-output probes/v032_target_scaffold_summary.json --plot probes/artifacts/v032_target_scaffold.png` (likewise byte-identical to the tracked artifact).

**Figure 6. NBS Circular 514 temperature harmonization to 298.15 K.**
Panel A: the shift eps(298.15 K) - eps(tabulated) implied by the coefficients
printed in the circular, over the 74 transcribed records that carry one; the
median shift is 0.0 and the mean is -0.15.
Panel B: the same shift as a percentage of the tabulated value (mean absolute
1.4%). The panel exists to bound a systematic error, not to move data: of the 74
coefficient rows, 56 (0.757) state a validity range that covers 25 C and 18 state
a range that excludes it, so only those 18 would need the harmonization to be
treated as an extrapolation; within the 42 coefficient rows carried into the
frozen dataset, 32 (0.762) cover 25 C. No value in the frozen dataset is modified
by this probe.
Artifact: `probes/artifacts/nbs514_alpha_harmonization.png` (`probes/nbs514_alpha_harmonization_summary.json`).
Script: `python probes/nbs514_alpha_harmonization_probe.py` (recomputes the
summary from the frozen transcript, so it rewrites that summary with a fresh
timestamp, and re-renders the plot).

## Applicability domain (reported as prose, not a figure)

The adopted boundary is structural rather than a predicted-dielectric
threshold: the SMARTS pattern `[O,S,N;!H0]` counts textbook
hydrogen-bond donors, so the trigger is independent of any model output. The
structural donor rule triggers on 2,070 of the 6,150 out-of-fold rows (33.66%)
and covers all 150 rows whose experimental permittivity exceeds 60. Mean
absolute error is 5.02 permittivity units inside the domain and 11.51 outside
it. The superseded variant, which combined the donor count with a predicted
dielectric above 60, reached only 5 of those 150 rows and was retired for
reading the model output the boundary exists to qualify. An earlier draft
carried this material as Figure 7; it is two numbers and a flag table
(`data/processed/dielectric_applicability_flags.csv`), so it is reported here instead.

# Code and Data Availability

The complete dataset, all build scripts, probe scripts, verifiers, and
benchmark outputs are deposited in a public GitHub repository:

**Repository:** https://github.com/LittleAlety/electrolyte-solvent-dielectric-ml
**Release:** v1.0 (GitHub release 2026-09-25; dataset v0.3.3)
**DOI:** https://doi.org/10.5281/zenodo.22957696
**Concept DOI:** https://doi.org/10.5281/zenodo.22957695 (version-independent)

## Repository structure

```text
├── data/
│   ├── dielectric_v01.csv           # v0.1: 100 ThermoML compounds
│   ├── dielectric_v02.csv           # v0.2: 210 NBS + ThermoML compounds
│   ├── dielectric_v03.csv           # v0.3.3: 246 compounds (released in v1.0)
│   ├── dielectric_v031.csv          # v0.3.1: G1 revision (243, historical)
│   ├── dielectric_v032.csv          # v0.3.2: PC+EC freeze (245, historical)
│   ├── processed/
│   │   ├── dielectric_v03_exclusions.csv           # 5-row curated exclusion list
│   │   ├── dielectric_v03_provenance_patches.csv   # 38 patches (30 at v0.3.3, +8 at v0.3.14)
│   └── restricted/                  # Non-redistributable cross-check evidence
├── scripts/
│   ├── build_dielectric_v03.py      # v0.3/v0.3.3 deterministic builder
│   ├── verify_dielectric_v03.py     # v0.3.3 verifier (7/7 checks, 246 rows)
│   ├── verify_dielectric_v032.py    # v0.3.2 verifier (7/7 checks, 245 rows)
│   ├── verify_d1_leave_ec_out.py    # D1 sensitivity verifier (8/8 checks)
│   ├── build_paper_full_draft.py    # Assembles paper/full_draft.md from the sections
│   ├── check_paper_artifact_consistency.py  # Paper claims vs. frozen artifacts
│   ├── run_xtb_physical_features.py
│   └── build_dataset_v01.py, build_dielectric_v02.py, ...
├── probes/
│   ├── dielectric_representation_ablation.py    # Main XGBoost benchmark
│   ├── dielectric_mlp_probe.py                  # MLP neural probe
│   ├── dielectric_mlp_calibration_probe.py      # Pre-registered calibration probe
│   ├── dielectric_chemprop_baseline.py          # Chemprop D-MPNN baseline
│   ├── g2_domain_gap_test.py                    # External domain-gap test
│   ├── v032_ablation_summary.json               # v0.3.2 236-row benchmark
│   ├── v032_target_scaffold_summary.json        # v0.3.2 scaffold holdout
│   ├── v032_controlled_comparison_summary.json  # Paired PC/EC control
│   ├── dielectric_leave_ec_out_sensitivity.py  # Pre-registered leave-EC-out probe
│   ├── dielectric_leave_ec_out_summary.json     # D1 report-only sensitivity metrics
│   └── artifacts/                               # Figures and plots
├── reports/
│   ├── decisions_log.md                         # Full decision record
│   ├── agent_workflow.md                        # Delegation and verification log
│   └── g1_data_gate_review.md                   # G1 conflict list
├── paper/
│   ├── outline.md
│   ├── abstract_and_intro.md
│   ├── methods_data_records.md
│   ├── technical_validation.md
│   ├── benchmark_and_figures.md
│   ├── code_and_data.md                         # sources of full_draft.md
│   └── full_draft.md                            # generated; do not edit by hand
├── src/electrolyte_ml/                          # Python package
├── tests/                                       # CI test suite
├── environment.yml                              # Conda environment
└── pyproject.toml
```

## Software dependencies

- Python 3.12
- RDKit 2024.09 (structure standardization, Morgan fingerprints, 2D descriptors)
- XGBoost 2.1 (primary candidate model)
- scikit-learn 1.5 (cross-validation, MLP, metrics)
- GFN2-xTB 6.7.1 (physical features)
- Chemprop 2.1.0 (D-MPNN baseline, isolated environment)
- NumPy, SciPy, pandas, matplotlib, pytest

## Reproducibility

Every dataset version is built by a deterministic script and verified by an
independent verifier that re-derives all metrics from the committed outputs.
All probe scripts accept explicit command-line arguments for input and output
paths. The conda environment is frozen in environment.yml.

`paper/full_draft.md` is generated from the five section files by
`scripts/build_paper_full_draft.py`; edit the sections, never the draft. The
section files and the generated draft are checked against the frozen artifacts
by `scripts/check_paper_artifact_consistency.py`, which runs in CI.

Verifiers run in CI (GitHub Actions, Ubuntu 22.04) on every commit:

```bash
# Full verification suite
pytest tests/ -v

# Individual dataset verifiers
python scripts/verify_dielectric_v032.py # 7/7 checks, 245 rows
python scripts/verify_dielectric_v03.py  # 7/7 checks, 246 rows
python scripts/verify_export_manifests.py
python scripts/verify_d1_leave_ec_out.py # 8/8 checks

# Paper claims vs. frozen artifacts
python scripts/check_paper_artifact_consistency.py
```

## License

The dataset and code are released under the Creative Commons Attribution 4.0
International (CC BY 4.0) license, except where individual source records
carry more restrictive licenses (CC BY-NC, CC BY-NC-ND) as noted in the
source_license and redistribution_conditions columns of each row, or because
the underlying source has no stated reuse license.

Several rows need explicit qualification. 3-Methoxypropionitrile (MOPN) was
transcribed from the ECW-308 supporting information and carries no license
statement of its own, so it is flagged model_ready=false; the numeric fact is
retained while the underlying publisher supplement remains non-redistributable,
and no open-license claim is made for that source. Triethyl phosphate and
trimethyl phosphate retain their CC BY-NC 4.0 source_license metadata and are
also withheld from the modelling set; their conflict_status fields record the
competing public values rather than treating the licence as the reason for
withholding. Vinylene carbonate and fluoroethylene carbonate now each cite a
paywalled primary article, so their three licence columns are empty and
redistribution_status=allowed; only the measured fact, not the source PDF, is
redistributed. The ECW-308 supporting-information text and
the other closed-access extractions used during the Tier-1/Tier-2 search are
kept outside the repository (data/external/ is git-ignored) and are not
redistributed here.
