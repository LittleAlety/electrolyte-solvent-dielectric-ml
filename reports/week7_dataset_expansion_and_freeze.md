# Week 7 Report: data expansion round 1, G1+ closure and the v1.0 veto items

**Date:** 2026-09-24
**Baseline commit:** `867fae5` (Week 7 opening) through `060e9d7`
**Dataset:** `data/dielectric_v03.csv` - v0.3.3/v0.3.4 candidate, 246 rows
**Status:** candidate release. The `v1.0` tag stays deleted until the freeze
conditions in Appendix I are met.

> **Historical snapshot (2026-09-24).** The v0.3.3/v0.3.4 wording and the FEC
> "78.4 / 102 / 107" statements below record the state at the Week-7 freeze.
> The dataset at the v0.3.11 re-pin was **v0.3.11** (`765fd8e0...646b60`): the
> stored 102 was shown to be the flash point, leaving 78.4 vs 107 as the
> dielectric legs. As of v0.3.12 the current dataset is **v0.3.12**
> (`1b285fe8...22456`): FEC now stores 78.4 at 296.15 K from its primary
> measurement, and vinylene carbonate carries primary-source metadata. Both
> rows remain `model_ready=false`, so no benchmark row moved.

## Outcome

Week 7 closed the two Appendix I **veto** items (the PC/EC gap and the circular
applicability rule), completed the G1+ provenance ladder through tier 3, and
produced the G2 external test. No numeric value was averaged or promoted from a
compilation.

- `dielectric_v031.csv` -> `dielectric_v032.csv` -> `dielectric_v03.csv`:
  243 -> 245 -> 246 rows. PC (64.9 at 298.15 K) and EC (90.5 at 313.15 K) were
  added from their original measurements; the 30-row provenance patch layer
  records the traceability upgrade without touching `dielectric`, `T_K` or
  `model_ready`.
- The applicability rule was re-derived and the prescribed Onsager variant
  **measured and rejected**: it covers 0 of the 150 rows whose measured
  permittivity exceeds 60. The adopted rule counts structural hydrogen-bond
  donor sites (`[O,S,N;!H0]` from SMILES) and therefore never reads a model
  output; it triggers on 2,070 of the 6,150 out-of-fold rows (33.66%).
- G1+ tier 0-3 evidence: 242/242 ThermoML dielectric XML files parsed, 636 NBS
  Circular 514 organic rows and 215 structure candidates compared. PubChem and
  the NIST WebBook carry **no** structured dielectric field for any of the ten
  targets (all HTTP 404 / no field), so both were dropped as dielectric sources.
- G2 external test: the frozen v0.2 model predicts 29 new battery-relevant
  solvents.

## G2 domain-gap external test (frozen v0.2 model, 205 train / 29 test)

| Representation | R2 | Spearman |
| --- | --- | --- |
| Morgan | 0.122 | 0.692 |
| RDKit Physical | 0.154 | 0.367 |
| Morgan+Physical (hybrid) | 0.286 | 0.590 |
| v0.2 cross-validation reference (hybrid) | 0.320 | 0.830 |

The systematic underestimation of high-permittivity solvents (GVL, NMP) is the
domain gap that the v0.3 expansion exists to close; the probe is stored as
`probes/g2_domain_gap_summary.json` with the parity plot
`probes/artifacts/domain_gap_parity.png`.

## Applicability domain (Appendix I veto 2, closed by measurement)

| Quantity | Adopted structural rule | Rejected: predicted > 60 | Rejected: Onsager > 60 |
| --- | --- | --- | --- |
| Rows flagged | 2,070 (33.66%) | 30 (0.49%) | 30 (0.49%) |
| MAE outside domain | 11.51 | 22.32 | 1.97 |
| MAE inside domain | 5.02 | - | - |
| Measured eps > 60 covered | **150/150** | 5/150 | **0/150** |

## G1+ provenance ladder (tier 0-3)

| Tier | What it is | Result |
| --- | --- | --- |
| 0 | Local ThermoML + NBS 514 grep | 242/242 XML parsed; 636 NBS rows compared; PC and the glymes/dinitriles located |
| 1 | Free programmatic sources (PubChem, NIST WebBook, Chodera) | PubChem and NIST carry no structured dielectric field for the targets; Chodera shares 45 v0.1 keys with a median absolute deviation of 0.175 |
| 2 | Free battery-domain compilations (ECW-308, DC-200) | ECW-308 classified as a secondary compilation; its two-decimal nitrile precision is its own, not Duncan's |
| 3 | Author documents behind the compilation | Perricone 2013 is closed, but the **same author's open-access 2011 thesis** reports eps_r = 36 for 3-methoxypropionitrile |
| 4 | Print books and institutional databases | All `blocked` on access (Riddick, CRC, Marcus, Aurbach, Landolt-Bornstein, Reaxys, SciFinder-n, DIPPR 801) - recorded as access limitations, never as "no data" |

The tier-3 thesis retrieval is recorded in
`reports/g1plus_mopn_thesis_findings.md` and
`probes/g1plus_mopn_thesis_evidence.json`. HAL is protected by a proof-of-work
interstitial; the PDF was obtained by driving the user's Microsoft Edge through
Playwright, i.e. the same route a human reader takes.

## What is still open

- **Vinylene carbonate** carries `conflict_open`: the literature range is
  78-127 and the ECW-308 value 126 could not be traced to an original
  measurement. The 1966 paper that first measured it (Saadi & Lee) is paywalled.
- **FEC**: resolved down to two legs in v0.3.11. The stored 102 was shown to
  be the flash point rather than a permittivity, leaving 78.4 (ECW-308) and
  107 (Ue 2014 Table 2.3); neither has a readable primary measurement, so the
  row stays excluded from the model-ready set.
- **3-methoxypropionitrile**: the value and its 25 C condition are both
  citable to the open-access thesis (Tableau 4 and Tableau 14). The row still
  stays out of the model-ready set for two independent reasons, neither of them
  the temperature: it is a curated exclusion awaiting primary confirmation
  (`data/processed/dielectric_v03_exclusions.csv`), and it has no GFN2-xTB
  physical-feature row.
- **Tier 4 access**: every print or subscription resource remains unverified
  rather than absent.

## Evidence files

- `data/dielectric_v03.csv`, `data/dielectric_v032.csv`, `data/dielectric_v031.csv`
- `data/processed/dielectric_v03_exclusions.csv`
- `data/processed/dielectric_v03_provenance_patches.csv`
- `probes/applicability_domain_summary.json`, `probes/g2_domain_gap_summary.json`
- `reports/v032_veto_resolution.md`, `reports/v033_provenance_upgrade.md`,
  `reports/applicability_domain_veto_fix.md`
- `reports/g1plus_tier0_findings.md` ... `reports/g1plus_tier34_access_findings.md`

## Verification

- `scripts/verify_dielectric_v03.py`: 7/7 checks, 246 rows,
  sha256 `1b285fe852c13a99e26cc94e85ffab389857351cd4fca36aed0ccf3f40d22456` (v0.3.11 was `765fd8e0...646b60`;
  re-pinned in v0.3.6 by the PubChem tier-1 cross-check notes on acetonitrile
  and sulfolane, then in v0.3.10 by the 3-methoxypropionitrile temperature
  correction, then in v0.3.11 by the FEC flash-point conflict correction, then
  in v0.3.12 by the FEC primary-value promotion; no revision has moved a
  numeric value in a `model_ready=true` row)
- `scripts/verify_dielectric_v032.py`: 7/7 checks, 245 rows, 243/243
  field-by-field superset of v0.3.1
- `scripts/verify_dielectric_v02.py`: 9/9 checks
- `scripts/verify_week1.py`: 15/15 checks
