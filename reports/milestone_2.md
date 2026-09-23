# Milestone 2 Acceptance Review

## Executive status

The data-expansion gate is now **complete**. The diagnostics, benchmark probes,
candidate queue, and v0.2 dataset are reproducible. Several model-performance
gates remain below their thresholds, so the overall scientific milestone is not
presented as a model-success milestone.

| Item | Status | Evidence | Blocker or interpretation |
| --- | --- | --- | --- |
| v0.2 >= 200 compounds | **PASS** | `data/dielectric_v02.csv` has 210 unique compounds: 100 unchanged v0.1 rows plus 110 selected NBS Circular 514 additions; verifier passes 8/8 checks | Size gate passed; model generalization remains a separate question |
| Tanimoto + CV | **PARTIAL** | 10x5 CV completed; Tanimoto mean R2 `0.04246 +/- 0.81976`, only `+0.01950` over RBF, gate false | Model-performance gate failed; this is a result, not a pipeline failure |
| Viscosity baseline | **PARTIAL** | Random-row MAE `0.06357` passes; grouped-key MAE `0.17477` fails | Random success primarily measures temperature interpolation; new-molecule generalization is not solved |
| EC high-temperature extension | **PASS** | 47 keys and 206 observation rows; exact EC literature row and source metadata verified | Supplemental table only; main v0.1 unchanged |
| Chodera cross-check | **PASS** | 45 common keys; median absolute median difference `0.175`; max `7.341`; 44 near-isothermal keys | Measurement-method attribution is not supported without direct evidence |
| Learning curve | **PARTIAL / NEGATIVE** | On a fixed v0.1 test set, equal-size v0.2 samples have lower R2 than v0.1 at 20/40/60/80; v0.2 reaches R2 `0.06471` at 160 training compounds | More data increases chemical heterogeneity faster than the current Morgan+RBF GPR can exploit it; no closed-loop accuracy gain is claimed |
| AL Top-30 | **PASS for queue generation** | 30 candidates, longlist 300, hard family quota 6, no v0.1 leakage | All candidates remain `awaiting_manual_review`; not confirmed experimental availability |
| P4 redox probes | **PARTIAL** | Shared pipeline and verifier pass; best oxidation MAE `0.29052 eV`, reduction `0.40962 eV` | The requested `0.15 eV` gate fails for both targets |

The failed model gates are results, not evidence that the pipelines are broken.
All listed artifacts are independently verified.

## Week 4 physical-feature control

The Week 4 representation ablation now passes its independent verifier
`12/12`. On the 205 compounds with complete physical features, 10x5 repeated
CV gives mean R2 `0.203` for Morgan, `0.283` for xTB/RDKit physical features,
and `0.320` for the exact 0.5/0.5 Morgan+Physical ensemble. MAE is `7.654`,
`7.238`, and `6.726`, respectively.

The gain is strongest in continuous regression and ranking. Pure physical
features remain best at `epsilon > 30` discrimination (AUC `0.928` versus
`0.915` for the ensemble). The high-permittivity stratum (`epsilon > 60`)
still has mean MAE `63.8-81.3`, so the result supports a physics-informed
screening direction rather than a resolved full-range model.

The v0.2 accounting is explicit: 210 source rows = 205 successful physical
features + 4 xTB failures + 1 excluded source conflict. The conflict and
failures are not imputed. The physical-feature and representation-ablation
details are in `reports/week4_physical_features.md`.

## Week 5 target and extrapolation control

The target transform is representation-specific. Under random repeated CV,
`log(epsilon - 1)` is accepted only for the Physical representation
(`R2 0.283 -> 0.303`, `MAE 7.238 -> 6.066`) and rejected for Morgan and
raw-scale Morgan+Physical.

Across five balanced ring-scaffold/acyclic-ECFP cluster partitions, the log
Physical model has the best mean R2 (`0.267 +/- 0.014`) and MAE
(`6.718 +/- 0.316`). The raw hybrid remains competitive by R2
(`0.263 +/- 0.032`), and the log hybrid has the best `epsilon > 30` AUC
(`0.911 +/- 0.007`). These are screening models, not claims of prospective
chemical generalization; the `epsilon > 60` stratum remains weak.

The database recheck finds no automatic path from 210 to 300-400 training
compounds. NBS has four pending small-hydrocarbon candidates, Landolt remains
manual transcription, and SpringerMaterials remains restricted cross-check
data only.

The v0.2 size gate passes, but the fixed-test learning curve does not show an
immediate accuracy gain. At the same training size, v0.2 R2 was `-0.16076`,
`-0.10368`, `-0.12594`, and `-0.04117` for 20/40/60/80 compounds, versus
`-0.00114`, `0.11975`, `0.12458`, and `0.23126` for v0.1. Extending v0.2 to 160
training compounds reached R2 `0.06471`, still below the 80-compound v0.1
baseline. This is a negative result for the current model/feature choice, not a
reason to reject the larger dataset.

## Restricted SpringerMaterials cross-check

After authenticating with the user's Edge session, 25 Thermophysical Property
datasets and 61 name-matched Interactive pure-substance datasets were captured
locally. The Interactive capture contains 3,263 rows and 933 near-room rows.
Using a ±5 K match window, 60 v0.2 compounds have at least one independent
SpringerMaterials comparison. The median absolute difference is `0.05`, the
90th percentile is `0.669`, and the maximum is `10.2`.

The maximum is `Ethyl isothiocyanate`, where the NBS value and the restricted
SpringerMaterials source appear to reflect different measurements. It is kept
as an explicit cross-check conflict pending manual source inspection; the v0.2
value was not silently changed. Raw restricted values and the cross-check plot
remain under `data/restricted/springer_materials/`, which is Git-ignored.

## Data expansion decision

The audit is in `docs/week3/data_expansion_audit.md`; source-level evidence is in
`data/processed/data_expansion_source_audit.csv` and
`probes/data_expansion_summary.json`.

Key facts:

- NIST fallback inventory: 205 local XML files, 91 dielectric source documents,
  and 11,646 observations.
- Near-room pure zero-frequency keys: 100.
- All-temperature zero-frequency pure keys: 103.
- ChalkLab pinned commit:
  `681a946669feaf6ccc13ba6e1de760385c57ce73`.
- ChalkLab archive aggregate: five LFS zip objects, 411,920,425 bytes total,
  122,403 JSONLD entries.
- ChalkLab zero-frequency pure: 103 keys, 100 overlapping v0.1, 3 new but none
  in the near-room window.
- ChalkLab zero-frequency plus various-frequency pure: 161 keys.
- ChalkLab component universe: 187 keys.
- NBS Circular 514 `10.6028/nbs.circ.514` provides more than 800 critically
  evaluated pure liquids. After extraction and filtering, 215 new structures
  were resolved and the top 110 were selected for v0.2.
- ChemDataExtractor: 60,804 records and 11,054 compounds, but no independent
  temperature field and insufficient precision for direct training labels.
- The 308 ECW target remains unavailable with zero fabricated rows.
- Landolt-Börnstein 2015 DOI `10.1007/978-3-662-48168-4` exposes at least 217
  pure-substance chapter metadata records but is closed and requires manual
  transcription. A metadata-only queue is stored in
  `data/processed/landolt_boernstein_2015_pure_liquid_queue.csv`; it contains
  zero transcribed dielectric values and does not count toward v0.2.
  transcription.
- Landolt-Börnstein IV/17 and the CRC Handbook Permittivity of Liquids page are
  closed/login-gated manual sources. They may contain sufficient quantities,
  but row-level eligibility and redistribution rights must be verified before
  claiming that v0.2 can reach 200.
- DDBST's no-data policy is an access constraint, not a dataset. The DTU
  fluorescence dataset does not provide pure zero-frequency dielectric labels.
  The binary-solvent QSPR Figshare item and the unlicensed GitHub binary-mixture
  repository are mixture-focused and cannot be promoted into the pure table.

## Blocker Resolution

The original v0.2 size blocker was resolved through NBS Circular 514, a public
NIST-published table of more than 800 pure liquids. The selected 110 additions
have traceable source pages, temperatures, formulas, structures, resolution
sources, and source-quality metadata. Closed-source Landolt/CRC expansion is no
longer required to pass the Milestone 2 size gate.

## Unfinished deliverables

- `data/dielectric_v02.csv` exists and the minimum-size gate passes.
- Closed-source Landolt/CRC expansion remains future work, not a v0.2 blocker.
- Tanimoto, viscosity group holdout, learning-curve scaling, and P4 gates remain
  below their requested thresholds.
