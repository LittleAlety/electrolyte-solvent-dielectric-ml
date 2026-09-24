# G1+ VETO Resolution and v0.3.2 Benchmark Report

**Date:** 2026-09-24
**Historical notice:** This report documents the superseded v0.3.2 line.
The current candidate is v0.3.3; see `reports/v033_provenance_upgrade.md`.
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
| Applicability-domain rule idle / circular | Appendix I veto | RESOLVED (re-derived 2026-09-24) | Onsager variant measured and rejected; structural HBD rule adopted, 33.66% trigger |
| Benchmark gain not attributable to the added data | audit P0 | CORRECTED, then **further corrected in v0.3.4** | paired control: **+0.0059** R2 (p = 0.11), not +0.056; the +0.0265 figure predates the `model_ready` gate |
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
| Diglyme | 2,5,8-trioxanonane | 7.3815 | SBZXBUIDTXKZTM-UHFFFAOYSA-N |
| Triglyme | 2,5,8,11-tetraoxadodecane | 7.604 | YFNKIDBQEZZDLK-UHFFFAOYSA-N |
| Tetraglyme | 2,5,8,11,14-pentaoxapentadecane | 7.798 | ZUHZGEOKBKGPSW-UHFFFAOYSA-N |
| Adiponitrile | hexanedinitrile | 32.12 | BTGRAWJCKBQKAO-UHFFFAOYSA-N |
| Glutaronitrile | pentanedinitrile | 34.60 | ZTOMUSMDRMJOTH-UHFFFAOYSA-N |

All five derive from ThermoML (dinitriles: DOI 10.1021/je300958c).

## Veto 2: applicability domain

The previous rule triggered on `predicted_dielectric > 60`, a circular
condition: the flag depended on the same model output it was meant to police.
It fired on 30 of the 6,150 out-of-fold rows (0.49%) only because the model
cannot reproduce the compounds the rule exists to catch.

The review prescribed a model-independent repair: flag `HBD >= 1` together
with an Onsager-estimated dielectric above 60. That variant was implemented,
wired into the production caller, and run. The measurement rejected it. The
reaction-field estimate is

1. **low for exactly the associated liquids it should catch.** Estimated
   1.6-40 against measured values of 61-178, because the Kirkwood correlation
   factor `g` is much greater than 1 for hydrogen-bonded networks and the
   single-molecule cavity picture does not apply;
2. **high for ionic liquids.** Estimated 82-153 against measured 12-30;
3. **blind to the failure zone.** It covers **0 of the 150** rows whose
   measured permittivity exceeds 60, and the one compound it flags,
   `1-(2-hydroxyethyl)-3-methylimidazolium tetrafluoroborate`, has a measured
   dielectric of 23.3.

The adopted rule is therefore structural rather than electrostatic. A compound
carrying at least one hydrogen-bond donor site, counted from its structure with
the SMARTS pattern `[O,S,N;!H0]`, is flagged `outside_associated_liquid`; a
prediction below 1.0 is flagged `outside_nonphysical`. The count is computed
from SMILES and never from the model output, so the boundary is not circular.
It also avoids RDKit's `NumHDonors`, which is a drug-likeness heuristic and
returns zero donors for water.

Measured on the frozen 6,150 out-of-fold rows:

| Quantity | Adopted structural rule | Rejected: predicted > 60 | Rejected: Onsager > 60 |
|---|---|---|---|
| Rows flagged | 2,070 (33.66%) | 30 (0.49%) | 30 (0.49%) |
| MAE outside domain | 11.51 | 22.32 | 1.97 |
| MAE inside domain | 5.02 | -- | -- |
| Measured eps>60 covered | **150/150** | 5/150 | **0/150** |

Both rejected variants remain in `probes/applicability_domain_summary.json`
under `rejected_variants`, with their rules, row counts, MAE and reasons, so the
veto is closed by measurement rather than by assertion. The Onsager estimate
survives only as a recorded diagnostic column (`onsager_epsilon`);
`onsager_available=6150`, `onsager_fallback=0` on the production run. A full
write-up is in `reports/applicability_domain_veto_fix.md`.

## Audit P0: the benchmark gain was not controlled

The original report claimed that adding PC and EC raised hybrid R2 from 0.310
to 0.366 (+0.056). That comparison is invalid. Enlarging the table
reshuffles `RepeatedKFold`: for the 235 shared compounds, **1272 of 2350**
compound x repeat fold assignments (**54.1%**) differ between the 235-row
v0.3 split and the 237-row v0.3.2 split, and the evaluation-set target
variance grows by 8.1%. The audit reviewer independently reproduced the same
54.1% churn figure. **Corrected 2026-09-24 (v0.3.4):** with the `model_ready`
gate enforced both arms fit 236 rows and the recomputed churn is **1224 of
2340** assignments (**52.3%**); the conclusion is unchanged.

### Controlled experiment (pre-gate figures)

`probes/v032_controlled_comparison.py` freezes the v0.3 fold assignment, keeps
all 234 v0.3 compounds in their original folds across all ten repeats, and
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

> **Superseded 2026-09-24 (v0.3.4).** The figures in this section were computed
> before the `model_ready` gate. With vinylene carbonate withheld from both arms
> the attributable hybrid gain is **+0.0059 (95% CI -0.002 to +0.013, p = 0.11)**:
> indistinguishable from zero. See `reports/v034_model_ready_gate.md`.

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

Training on all 234 v0.3 compounds (the gate-fixed frozen fold set) and
predicting PC and EC as external holdouts underestimates both:

| Compound | True epsilon | Hybrid prediction | Abs error |
|---|---|---|---|
| Propylene carbonate | 64.9 | 29.8 +/- 1.1 | 35.1 |
| Ethylene carbonate | 90.5 | 50.3 +/- 2.2 | 40.2 |

Adding PC and EC improves interpolation among the existing 234 compounds. It
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
  4 compounds withheld from model fitting through the curated exclusion list
  (FEC, TEP, TMP, ethyl isothiocyanate). **Corrected 2026-09-24:** this line
  previously read "5 compounds excluded from model fitting", which was wrong.
  **Further corrected 2026-09-24 (v0.3.4):** that correction stopped one step
  short. Vinylene carbonate is flagged `model_ready=false`, and since v0.3.4
  the modelling gate enforces the flag, so it is withheld from every fit as
  well. The current accounting is 245 source rows = 236 fitted + 4 curated
  exclusions + 4 physical-feature failures + 1 withheld; the v0.3.3 roster of
  246 rows is 236 + 5 + 4 + 1, the fifth exclusion being
  3-methoxypropionitrile.

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
- `probes/v032_ablation_summary.json` was rebuilt by the v0.3.4 gate: its
  coverage numbers are now 236 fitted rows with hybrid R2 0.3636, matching the
  v0.3.3 lineage exactly (both fit the same rows). They remain *coverage*
  results and are not cited as the causal effect of the two added compounds; the
  only valid causal statement is the paired control, `+0.0059` (p = 0.11).
- `temp_header.txt` (an untracked scratch file) was removed.
- Full suite: **457 passed** (up from 441 at the audit baseline);
  `ruff check scripts src probes tests` clean.
- Nine wording/structure inconsistencies remain in the per-section paper
  drafts (`paper/abstract_and_intro.md`, `paper/benchmark_and_figures.md`,
  `paper/code_and_data.md`, `paper/outline.md`,
  `paper/technical_validation.md`). They are enumerated in
  `reports/agent_workflow.md` under "Known remaining inconsistencies" and
  must be closed before a v1.0 freeze. They do not affect the dataset, the
  verifier or the controlled benchmark.
