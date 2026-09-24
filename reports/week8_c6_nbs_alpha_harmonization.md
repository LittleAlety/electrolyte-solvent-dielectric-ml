# Week 8 C6: NBS Circular 514 temperature harmonization to 298.15 K

**Date:** 2026-09-24
**Probe:** probes/nbs514_alpha_harmonization_probe.py
**Summary:** probes/nbs514_alpha_harmonization_summary.json
**Status:** closed. The probe quantifies the shift and flags the records it
refuses to harmonize. It does not modify data/dielectric_v03.csv.

## Outcome

The frozen dataset carries 110 NBS Circular 514 rows. 42 of them also carry a
published temperature coefficient, so the 293.15 K to 298.15 K harmonization can
actually be computed rather than assumed:

| Quantity | Value |
| --- | --- |
| NBS rows in v0.3 | 110 |
| of which carry a coefficient | 42 |
| of which are already at 298.15 K | 44 |
| coefficient rows whose stated valid range covers 25 C | 32 of 42 (76.2%) |
| median absolute shift | 0.011 |
| mean absolute shift | 0.248 |
| maximum absolute shift | 2.50 |
| mean relative shift | 1.42% |

The conclusion is that the temperature window is a real but **minor**
limitation. For most 293.15 K entries the harmonization moves the value by a few
hundredths, which is far inside the three-figure accuracy band NBS assigns to
those rows. Ten coefficient rows sit outside their stated applicability range;
those are flagged rather than silently extrapolated.

## The sign convention had to be corrected

The working note that seeded this task wrote the logarithmic branch as
10^(alpha * 1e-5 * (298.15 - T)). That is the wrong sign. NBS Circular 514,
section 2.1, defines

    a     = -d(eps)/dt
    alpha = -d(log10 eps)/dt

so both coefficients are minus derivatives, and inverting them gives

    a     : eps(298.15) = eps(T) + a * 1e-5 * (T - 298.15)
    alpha : eps(298.15) = eps(T) * 10 ** (alpha * 1e-5 * (T - 298.15))

Both branches therefore move the value in the same direction. The sign was not
argued from algebra alone; it was checked against the table's own data.

## Independent checks

Because the two branches disagree in sign with the working note, the direction
was verified three ways.

**1. Internal double-entry comparison.** When NBS lists the same compound at two
temperatures and one entry carries a coefficient, the coefficient predicts the
other entry:

| Compound | Coefficient | Predicted | Tabulated | Relative error |
| --- | --- | ---: | ---: | ---: |
| 1,2-Dichloroethane | alpha = 235e-5 | 10.6441 | 10.65 | 0.055% |
| Chlorobenzene | alpha = 130e-5 | 5.6252 | 5.621 | 0.074% |
| 1-Butanol | alpha = 335e-5 | 17.7724 | 17.80 | 0.155% |
| 1-Butanol | alpha = 300e-5 | 17.1957 | 17.10 | 0.560% |

Mean relative error 0.21%, maximum 0.56%. The first two pairs are strict: the
comparison entry carries no coefficient of its own. The two 1-butanol rows both
carry a coefficient, so they are reported separately as a weaker check.

The same test run with the opposite sign produced errors of 2% to 5%, i.e. an
order of magnitude worse. The table's own numbers select the convention, not the
algebra in the working note.

**2. Slope sanity.** The implied slope d(eps)/dt is negative for 182 of the 188
coefficient-bearing rows, which is what a normal liquid does.

**3. ThermoML overlap.** The frozen corpus was scanned for an independent
pure-component zero-frequency observation within 297.15-299.15 K. The overlap is
**zero of the 110 frozen NBS keys** (not merely the ten G1+ target molecules). Strict same-structure, same-frequency
cross-validation of this subset is therefore not available.

The nearest defensible relaxation keeps the sample pure and near ambient
pressure and opens the frequency gate to at most 3 MHz, and additionally
requires the ThermoML temperature to fall inside the NBS validity window, so the
comparison never extrapolates the coefficient it is testing. That yields 18
pairs over 5 compounds:

| Cohort | MAE before | MAE after | RMSE before | RMSE after | Max abs before | Max abs after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 18 in-range proxy pairs | 0.375 | 0.232 | 0.733 | 0.368 | 2.171 | 0.880 |

The aggregate improves, but only 6 of the 18 pairs improve individually and the
per-compound picture is genuinely mixed. 2-Butanone improves sharply at 308.20 K
and 318.20 K (2.171 to 0.088) while getting worse at 298.20 K (0.121 to 0.319).
Acetonitrile's coefficient is extreme (a = 0.16 per degree) and one 288.15 K
pair degrades from 0.020 to 0.780. This is reported as a mixed risk signal, not
as validation passed.

## Records the probe refuses to harmonize

Two rows carry a negative NBS coefficient, which implies a dielectric constant
that *rises* with temperature:

| Row | Compound | Coefficient | Implied slope |
| --- | --- | ---: | ---: |
| nbs514:p14:009 | Trifluoroacetic acid | a = -50 (printed as -50.) | +0.50 |
| nbs514:p20:020 | Butyric acid | a = -0.23 | +0.0023 |

The negative sign is faithfully transcribed from the printed table, so this is
not a transcription bug. It is flagged for manual review and excluded from the
headline statistics; excluding both rows moves the mean absolute shift from
0.248 to 0.198.

## How many rows are actually correctable

A coefficient is necessary but not sufficient: 298.15 K must also lie inside the
temperature window the circular declares the coefficient valid for. Splitting
the 110 NBS rows in v0.3:

| Category | Rows |
| --- | ---: |
| no temperature coefficient | 68 |
| already at 298.15 K, nothing to correct | 17 |
| coefficient present, 298.15 K inside the stated range | 15 |
| coefficient present, window excludes or does not bound 25 C | 10 |
| total | 110 |

So the truly correctable population is **15 rows**, not 42. Ten of them use the
linear coefficient and five the logarithmic one:

* linear a (10): carbon disulfide, trifluoroacetic acid, acetonitrile,
  1,2-ethanediamine, butyric acid, n-pentane, benzene, 2,5-dimethylpyrazine,
  butyl acetate, n-hexane
* logarithmic alpha (5): 2-butanone, 2-pentanone, 3-pentanone,
  4-methyl-2-pentanone, aniline

Two of the fifteen (trifluoroacetic acid and butyric acid) are the
non-physical-slope rows flagged above. Acetonitrile sits exactly on the
right-hand endpoint of its stated window (15,25); counting the endpoint as
closed gives 15 rows, treating it as open gives 14. The probe uses the closed
convention and records the boundary assumption.

## Limitation

The internal double-entry check is not fully independent: both the coefficient
and the comparison value come from the same NBS table. It validates the
transcription and the sign convention, not the underlying measurement. Where
298.15 K falls outside the stated applicability range the coefficient is being
extrapolated beyond the range NBS judged satisfactory.

## Verification

tests/test_nbs514_alpha_harmonization_probe.py passes 20 tests, covering both
formula branches with hand-computed anchors, the applicability-range parser, the
slope sign, the double-entry validation logic, and a guard that the canonical
v0.3 hash is unchanged. Ruff is clean.
