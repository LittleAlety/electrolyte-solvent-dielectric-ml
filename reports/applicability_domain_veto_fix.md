# Applicability-domain veto: re-derived and closed by measurement

Date: 2026-09-24
Scope: Appendix I veto item 2 (`适用域规则修复`), v1.0 freeze gate
Artifact: `probes/applicability_domain_summary.json` (schema_version 2),
`data/processed/dielectric_applicability_flags.csv` (6,150 rows)

## 1. Why this was reopened

The Appendix I veto required the applicability rule to stop reading the model
output it is supposed to police. The first two attempts both failed in
production, and the failure was found by measurement, not by inspection:

| Attempt | Rule | Rows flagged | Share | Measured eps>60 covered |
|---|---|---|---|---|
| 1 (original, circular) | `HBD >= 1` and predicted dielectric `> 60` | 30 | 0.49% | 5/150 |
| 2 (review-prescribed) | `HBD >= 1` and Onsager-estimated dielectric `> 60` | 30 | 0.49% | **0/150** |
| 3 (adopted) | at least one structural H-bond donor site | 2,070 | 33.66% | **150/150** |

Attempt 2 was the variant the review explicitly prescribed, so it was
implemented, wired into the only production caller
(`probes/build_applicability_flags.py`) and run over the full out-of-fold
table before being judged. It is correct code that encodes an incorrect
physical premise.

## 2. Why the Onsager estimate is the wrong instrument here

The estimate is a single-molecule reaction-field (Onsager cavity) model:

1. the high-frequency permittivity comes from the molecular polarizability via
   the Lorentz-Lorenz relation;
2. the static permittivity solves the Onsager reaction-field equation for a
   dipole in a spherical cavity.

That model has no term for orientational correlation, so it is inapplicable in
exactly the liquids the boundary exists to catch. For hydrogen-bonded
associated liquids the Kirkwood correlation factor `g` is much greater than 1
and the measured permittivity is far above the cavity estimate:

| Compound | Measured eps | Onsager estimate | Structural donors |
|---|---|---|---|
| N-methylacetamide | 178.47 | 5.97 | 1 |
| Formamide | 106.14 | 1.63 | 1 |
| 2-hydroxyethylammonium lactate | 85.60 | 5.98 | 1 |
| Water | 78.87 | 40.45 | 1 |
| Ethanolammonium nitrate | 60.90 | 20.83 | 1 |

All five rows with measured eps > 60 are missed. In the other direction the
estimate is *high* for ionic liquids (82-153 estimated against measured
12-30), so the variant does not degrade to a conservative fallback -- it
inverts. The single compound it flags,
`1-(2-hydroxyethyl)-3-methylimidazolium tetrafluoroborate`, has a measured
dielectric of 23.3.

## 3. The adopted rule

```
H_BOND_DONOR_SMARTS = "[O,S,N;!H0]"
predicted_dielectric < 1.0        -> outside_nonphysical
donor_count >= 1                  -> outside_associated_liquid
otherwise                         -> inside_domain
```

The donor count is computed from the SMILES in the feature table, so the
boundary is independent of every model output and of every model version. It
is also deliberately *not* RDKit `Lipinski.NumHDonors`, which is a
drug-likeness heuristic: it returns a donor count of **0 for water** (`O`)
and for other small protic solvents, which would have missed most of the
failure zone.

### Stratification on the frozen 6,150 out-of-fold rows

| Domain | Rows | Mean absolute error |
|---|---|---|
| `inside_domain` | 4,080 | 5.02 |
| `outside_associated_liquid` | 2,070 | 11.51 |

The flagged group carries 2.3x the error of the retained group, which is the
behaviour the disclosure boundary is supposed to have: it marks predictions
the features cannot support, it does not improve them.

### Coverage of the failure zone

| Quantity | Value |
|---|---|
| Rows with measured dielectric > 60 | 150 |
| Those rows flagged by the adopted rule | 150 (100%) |
| Those rows flagged by the original circular rule | 5 (3.3%) |
| Those rows flagged by the Onsager variant | 0 (0%) |
| MAE within the measured eps>60 zone | 72.45 |

## 4. How the veto is prevented from silently regressing

- `probes/applicability_domain_summary.json` records the adopted rule, its
  SMARTS, the trigger rate, the error stratification, the high-permittivity
  zone coverage, and **both rejected variants** under `rejected_variants`,
  each with its rule string, row count, MAE, and reason. The rejected variants
  are reported rather than deleted, so the next reader can see that the
  prescribed repair was tested.
- `scripts/check_paper_artifact_consistency.py::check_applicability_trigger_rate`
  re-derives the quoted trigger rate and flagged-row count from the summary
  and fails the build when a paper section quotes a different number.
- Two `STALE_PHRASES` entries fail the build if the circular
  predicted-dielectric threshold or the Onsager-threshold wording reappears
  in the paper sections.
- `tests/test_applicability.py` pins the structural examples (water = 1 donor,
  acetonitrile = 0), asserts that the boundary does not move with the
  prediction, and asserts that both rejected variants are recorded.

## 5. What this does not change

No `dielectric`, `T_K`, `model_ready` or `source_doi` value changes. The
6,150-row out-of-fold table, the 246-row dataset, the 237-row benchmark and
the controlled `+0.0265` R2 result are untouched. This is a disclosure boundary
and a reporting fix, not a data revision or a model improvement.

## 6. Reproducing

```
.venv\Scripts\python.exe probes\build_applicability_flags.py
.venv\Scripts\python.exe -m pytest tests\test_applicability.py -q
.venv\Scripts\python.exe scripts\check_paper_artifact_consistency.py
```

## 7. Honest limitation

The rule is a whole-molecule structural flag, not a per-condition estimate: it
marks every prediction for a donor-bearing solvent, including temperatures and
concentrations where association may be weak. That is intentional for a
disclosure boundary -- the cost of a false positive is a withheld prediction,
while the cost of a false negative is a confident number the features cannot
support.
