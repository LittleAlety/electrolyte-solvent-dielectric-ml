# G1+ VETO Resolution and v0.3.2 Benchmark Report

**Date:** 2026-09-24
**Baseline commit:** 867fae5 (Week 7 G1-G5 deliverables)
**Output:** `data/dielectric_v032.csv` (245 compounds)
**Status:** release candidate. The `v1.0` tag stays deleted until the
Appendix I freeze conditions are met.

## Executive summary

Two Appendix I veto-level issues were raised against the proposed v1.0 freeze.
The first resolution attempt was then audited by an independent adversarial
reviewer (Dirac), who found that one veto was not actually wired into
production, that a second provenance guarantee had silently regressed, and
that the headline benchmark gain was not controlled. All findings are now
resolved and the benchmark claim has been **corrected downward** to the value
the controlled experiment supports.

| Finding | Raised by | Status | Evidence |
|---|---|---|---|
| PC (and EC) absent from every earlier revision | Appendix I veto | RESOLVED | PC 64.9 @ 298.15 K; EC 90.5 @ 313.15 K |
| Applicability-domain rule idle / circular | Appendix I veto | RESOLVED | Onsager estimate now passed by the production caller |
| Benchmark gain not attributable to the added data | audit P0 | CORRECTED | paired control: **+0.0265** R2, not +0.056 |
| v0.3.2 broke v0.3.1 provenance | audit P0 | RESOLVED | 243/243 shared rows byte-identical to v0.3.1 |
| v0.3.2 verifier was a smoke test | audit P1 | RESOLVED | 7 named checks; VC absence now fails |

## Veto 1: missing carbonate solvents

PC is the single most important battery carbonate solvent and was absent from
v0.2, v0.3 and the physical-feature table. The value was traced to the original
measurement:

- Simeral, L.; Amey, R. L. "Dielectric properties of liquid propylene
  carbonate." *J. Phys. Chem.* **1970**, 74, 1443.
- DOI: 10.1021/j100702a008 (bibliographic metadata verified via Crossref)
- epsilon = 64.9 at 298.15 K

Ethylene carbonate (EC) was added alongside PC because the same audit exposed
it as a second decisive gap:

- Chernyak, Y. *J. Chem. Eng. Data* **2006**, 51, 416.
- DOI: 10.1021/je050341y
- epsilon = 90.5 at 313.15 K; EC melts near 36 C, so the row is flagged
  `temperature_band=extended_temperature`.

**Residual limitation (not hidden, not averaged).** Crossref confirms both
records and their subject matter, but neither DOI resolves to an open full
text, so the specific table entries (PC Table II, EC Table 2) have not been
re-checked against the publisher PDF. The values are recorded as primary
measurements with the citation attached; the numeric transcription remains
the one item in this file that a reader with subscription access should
re-verify first. This is tracked as the top P2 item, not as a resolved claim.

### Compounds previously mis-reported as absent

The v0.3 G1 report listed diglyme, triglyme, tetraglyme and adiponitrile as
"absent". They were in fact already present under their IUPAC names:

| Common name | Name in dataset | epsilon at 298 K | InChIKey |
|---|---|---|---|
| Diglyme | 2,5,8-trioxanonane | 7.38 | SBZXBUIDTXKZTM-UHFFFAOYSA-N |
| Triglyme | 2,5,8,11-tetraoxadodecane | 7.60 | YFNKIDBQEZHQBU-UHFFFAOYSA-N |
| Tetraglyme | 2,5,8,11,14-pentaoxapentadecane | 7.80 | LNWVAMHESCFODF-UHFFFAOYSA-N |
| Adiponitrile | hexanedinitrile | 32.12 | BTGRAWJCKBQKAO-UHFFFAOYSA-N |
| Glutaronitrile | pentanedinitrile | 34.60 | ZTOMUSMDRMJOTH-UHFFFAOYSA-N |

All five derive from ThermoML (dinitriles: DOI 10.1021/je300958c).

## Veto 2: applicability domain

The previous rule triggered on `predicted_dielectric > 60`, a circular
condition: the flag depended on the same model output it was meant to police.

`src/electrolyte_ml/applicability.py` now accepts an `onsager_epsilon`
argument, and -- this is the part the audit found missing -- the only
production caller actually passes it. `_onsager_epsilon()` in
`probes/build_applicability_flags.py` derives a model-independent estimate
from GFN2-xTB and RDKit quantities already in the feature table:

1. the high-frequency permittivity is estimated from the molecular
   polarizability with the Lorentz-Lorenz relation,
   `(n^2 - 1)/(n^2 + 2) = N_A alpha / (3 V_m)`;
2. the static permittivity solves the Onsager reaction-field equation,
   `(eps - n^2)(2 eps + n^2) / (eps (n^2 + 2)^2) = N_A mu^2 / (9 eps_0 k_B T V_m)`.

Rows whose inputs are missing or non-physical fall back to the legacy
model-based path and are **counted explicitly** in the summary JSON
(`onsager_available`, `onsager_fallback`) rather than silently skipped. On a
full production run: `onsager_available=6150`, `onsager_fallback=0`.

The estimate deliberately ignores hydrogen bonding and association, so it is
used only as a screening threshold, never as a data value.

## Audit P0: the benchmark gain was not controlled

The original report claimed that adding PC and EC raised hybrid R2 from 0.310
to 0.366 (+0.056). That comparison is invalid. Enlarging the table
reshuffles `RepeatedKFold`: for the 235 shared compounds, **1272 of 2350**
compound x repeat fold assignments (**54.1%**) differ between the 235-row
v0.3 split and the 237-row v0.3.2 split, and the evaluation-set target
variance grows by 8.1%. The audit reviewer independently reproduced the same
54.1% churn figure.

### Controlled experiment

`probes/v032_controlled_comparison.py` freezes the v0.3 fold assignment, keeps
all 235 v0.3 compounds in their original folds across all ten repeats, and
appends PC and EC to the **training folds only**. Both arms therefore score
exactly the same held-out compounds in exactly the same folds, and every
number below is a paired per-repeat delta.

| Representation | v0.3 R2 | + PC/EC (train only) | Paired delta | 95% CI | Paired t p | Wilcoxon p |
|---|---|---|---|---|---|---|
| Morgan | 0.1898 | 0.1899 | +0.0001 | [-0.0057, +0.0059] | 0.97 | 1.00 |
| Physical | 0.2731 | 0.3233 | **+0.0502** | [+0.0324, +0.0681] | 1.3e-4 | 2.0e-3 |
| Morgan+Physical | 0.3099 | 0.3364 | **+0.0265** | [+0.0171, +0.0359] | 1.3e-4 | 2.0e-3 |

Secondary metrics, same pairing:

| Representation | metric | v0.3 | + PC/EC | delta | p |
|---|---|---|---|---|---|
| Morgan | MAE | 7.8795 | 7.9878 | +0.1084 (worse) | 0.0062 |
| Morgan | Spearman | 0.6972 | 0.6843 | -0.0129 (worse) | 0.0080 |
| Physical | RMSE | 16.6374 | 16.0527 | -0.5846 (better) | 9.1e-5 |
| Morgan+Physical | MAE | 6.9699 | 6.9063 | -0.0636 | 0.14 |
| Morgan+Physical | RMSE | 16.2193 | 15.9054 | -0.3139 (better) | 9.5e-5 |
| Morgan+Physical | Spearman | 0.8160 | 0.8101 | -0.0059 | 0.059 |

### What the corrected numbers say

- The attributable hybrid gain is **+0.027 (95% CI +0.017 to +0.036)**,
  roughly half of the +0.056 previously claimed. The rest came from a
  different random partition, not from the two compounds.
- The effect is carried entirely by the Physical representation (+0.050).
  Morgan fingerprint features are flat (+0.0001) and get *worse* on MAE and
  Spearman. This supports the mechanism claim (carbonate dipole, not
  fingerprint bits) but it is not a hybrid-wide step change.
- Hybrid MAE improves only marginally and not significantly (p = 0.14), and
  Spearman is marginally worse (p = 0.059). RMSE improves significantly. The
  honest summary is: real but moderate generalization gain.

### The added solvents are still outside the extrapolation range

Training on all 235 v0.3 compounds and predicting PC and EC as external
holdouts underestimates both:

| Compound | True epsilon | Hybrid prediction | Abs error |
|---|---|---|---|
| Propylene carbonate | 64.9 | 29.8 +/- 1.1 | 35.1 |
| Ethylene carbonate | 90.5 | 50.3 +/- 2.2 | 40.2 |

Adding PC and EC improves interpolation among the existing 235 compounds. It
does not give the model extrapolation ability for unseen high-permittivity
carbonates. The Physical representation is the least bad on EC (77.9 +/- 5.2)
and the worst on PC is Morgan (20.7 +/- 1.3). This is a limitation of the
released model and is now stated as such in the paper.

## Audit P0: v0.3.2 broke v0.3.1 provenance

The rebuild that added PC and EC also reverted three existing rows. The
ethoxybenzene row `DLRJIFUOBPOJNS-UHFFFAOYSA-N` lost its NBS Circular 514
corroboration (`10.6028/nbs.circ.514`), its `evidence_level=primary` upgrade
and its note; VC and methyl propionate lost their notes.

All three rows are restored. `data/dielectric_v032.csv` is now a strict
superset of `data/dielectric_v031.csv`:

- 243 shared keys, **243 rows equal field-by-field**, 0 missing keys,
  0 field mismatches, 2 added keys (PC, EC).
- 245 rows, 240 `model_ready=true`, 6 rows carrying a `conflict_status`,
  5 compounds excluded from model fitting.

Because the provenance text changed, the v0.3 freeze hash was **re-frozen**
deliberately rather than left stale: `3068a4ff...` -> `39d15e16...`, updated
in both `tests/test_build_dielectric_v03.py` and
`probes/dielectric_v03_summary.json`.

### Collateral fix: public-domain sources on review rows

Restoring the NBS DOI exposed a real validator defect: `review_license_errors`
treated *every* DOI on a review-sourced row as requiring CC licence metadata,
so a public-domain corroborating compilation was rejected as an "unsupported
review source_doi". `scripts/build_dielectric_v03.py` now exempts
`10.6028/nbs.circ.514` explicitly while still enforcing the allowlist for the
review DOI itself. Without this fix the restored provenance and the build
validator could not both be satisfied.

## Audit P1: the v0.3.2 verifier

`scripts/verify_dielectric_v032.py` previously reported `passed=true` while
never checking the properties it claimed to protect. It now runs seven named
checks and is wired into `pytest` via `tests/test_verify_dielectric_v032.py`:

| Check | What it now enforces |
|---|---|
| `required_columns` | explicit error on missing columns instead of KeyError |
| `unique_inchikeys` | duplicates fail instead of being silently overwritten |
| `smiles_inchikey_consistency` | RDKit re-derivation of every InChIKey |
| `source_metadata` | DOI / URL / citation / table / scope fields populated |
| `required_key_rows` | VC absence is a **failure** (previously skipped) |
| `dataset_counts` | 245 / 240 / 6 asserted, not merely printed |
| `v031_superset` | 243/243 field-by-field superset proof |

PC additionally has its SMILES, `evidence_level` and
`source_dois_all` (containing `10.1021/j100702a008`) asserted; EC has its
`T_K` and `model_ready` asserted; methyl propionate's conflict status is
asserted.

## Reproducing this report

```
.venv\Scripts\python.exe probes/v032_controlled_comparison.py
.venv\Scripts\python.exe scripts/verify_dielectric_v032.py
.venv\Scripts\python.exe -m pytest -q
```

## Repository hygiene

- The premature `v1.0` tag remains deleted locally and from the remote; the
  release line is v0.3.2 and the paper says so.
- `probes/v032_ablation_summary.json` retains the 237-row coverage numbers
  (hybrid R2 0.3660). They are valid as *coverage* results and are no longer
  cited as the causal effect of the two added compounds.
- `temp_header.txt` (an untracked scratch file) was removed.
- Full suite: **457 passed** (up from 441 at the audit baseline);
  `ruff check scripts src probes tests` clean.
