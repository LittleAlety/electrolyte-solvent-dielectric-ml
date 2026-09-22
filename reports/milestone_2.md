# Milestone 2 Acceptance Review

## Executive status

Milestone 2 is **not complete**. The diagnostics, benchmark probes, and candidate
queue are reproducible, but the v0.2 dataset was not created and its minimum
size gate fails.

| Item | Status | Evidence | Blocker or interpretation |
| --- | --- | --- | --- |
| v0.2 >= 200 compounds | **FAIL** | v0.1 remains 100 keys; ChalkLab component universe is 187 and automatic new near-298 additions are 0 | Manual curation required; `data/dielectric_v02.csv` intentionally does not exist |
| Tanimoto + CV | **PARTIAL** | 10x5 CV completed; Tanimoto mean R2 `0.04246 +/- 0.81976`, only `+0.01950` over RBF, gate false | Model-performance gate failed; this is a result, not a pipeline failure |
| Viscosity baseline | **PARTIAL** | Random-row MAE `0.06357` passes; grouped-key MAE `0.17477` fails | Random success primarily measures temperature interpolation; new-molecule generalization is not solved |
| EC high-temperature extension | **PASS** | 47 keys and 206 observation rows; exact EC literature row and source metadata verified | Supplemental table only; main v0.1 unchanged |
| Chodera cross-check | **PASS** | 45 common keys; median absolute median difference `0.175`; max `7.341`; 44 near-isothermal keys | Measurement-method attribution is not supported without direct evidence |
| Learning curve | **PARTIAL** | GPR R2 by train size: 20 `-0.02261`, 40 `0.12456`, 60 `0.03447`, 80 `0.23126` | Non-monotonic and variance-dominated; no reliable scaling claim |
| AL Top-30 | **PASS for queue generation** | 30 candidates, longlist 300, hard family quota 6, no v0.1 leakage | All candidates remain `awaiting_manual_review`; not confirmed experimental availability |
| P4 redox probes | **PARTIAL** | Shared pipeline and verifier pass; best oxidation MAE `0.29052 eV`, reduction `0.40962 eV` | The requested `0.15 eV` gate fails for both targets |

The failed model gates are results, not evidence that the pipelines are broken.
All listed artifacts are independently verified.

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
- ChemDataExtractor: 60,804 records and 11,054 compounds, but no independent
  temperature field and insufficient precision for direct training labels.
- The 308 ECW target remains unavailable with zero fabricated rows.
- Landolt-Börnstein 2015 DOI `10.1007/978-3-662-48168-4` exposes at least 217
  pure-substance chapter metadata records but is closed and requires manual
  transcription.
- Landolt-Börnstein IV/17 and the CRC Handbook Permittivity of Liquids page are
  closed/login-gated manual sources. They may contain sufficient quantities,
  but row-level eligibility and redistribution rights must be verified before
  claiming that v0.2 can reach 200.
- DDBST's no-data policy is an access constraint, not a dataset. The DTU
  fluorescence dataset does not provide pure zero-frequency dielectric labels.
  The binary-solvent QSPR Figshare item and the unlicensed GitHub binary-mixture
  repository are mixture-focused and cannot be promoted into the pure table.

## Blocker

`v0.2` requires manual literature and handbook mining. The AL longlist and Top30
provide the starting review queue, but they are candidate hypotheses, not
validated dielectric observations. No automatic source join reaches 200
qualified compounds. The second-round audit confirms an open-data automatic
ceiling of 187. Closed subscribed sources are plausible quantity sources, but
availability of 200 labels is still unproven until each row is manually checked
for pure-component, near-room, zero-frequency eligibility.

**Blocker:** manual curation is required to identify at least 100 additional
distinct compounds with pure-component, near-room zero-frequency dielectric
measurements and traceable temperature, phase, structure, and source metadata.

## Unfinished deliverables

- No `data/dielectric_v02.csv` was created.
- No claim is made that v0.2 minimum size has passed.
- Tanimoto, viscosity group holdout, learning-curve scaling, and P4 gates remain
  below their requested thresholds.
