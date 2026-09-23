# SpringerMaterials Thermophysical Dielectric Capture

## Scope

Captured on 2026-09-23 through the user-authorized Edge institutional session.
Two searches were captured:

- `Thermophysical Property` + phrase `dielectric constant`
- `SpringerMaterials Interactive` pure-substance records whose names match v0.2

The Thermophysical search returned 25 datasets and 108 rows. The matched
Interactive capture contains 61 datasets, 3,263 rows, and 933 near-room rows.

## Captured Fields

The local export retains:

- dataset ID and title
- source URL
- temperature in K
- pressure in kPa
- dielectric constant
- phase/state
- reference label
- expanded reference text when available

## Local Files

Raw restricted exports are under `data/restricted/springer_materials/`:

- `thermophysical_dielectric_export.json`
- `thermophysical_dielectric_export.csv`
- `thermophysical_dielectric_summary.csv`
- `interactive_v02_dielectric_export.json`
- `interactive_v02_dielectric_export.csv`
- `interactive_v02_dielectric_summary.csv`
- `interactive_pure_dielectric_catalog.json`
- `v02_crosscheck.csv`
- `v02_crosscheck.png`

These files are intentionally excluded from Git. The source is a subscription
product from Springer Nature and DDBST; do not redistribute the raw rows or
reference text without permission.

## Observed Coverage

The captured datasets include benzene, water, methanol, ethanol, acetonitrile,
acetone, DMSO, toluene, xylene isomers, cyclic ethers/alcohols, several
halogenated solvents, and common aprotic solvents. The capture is a
thermophysical-property cross-check set, not a replacement for the open NBS
Circular 514 training source.

## Cross-check

Using a ±5 K temperature window, 60 v0.2 compounds matched at least one
Interactive observation. The median absolute difference between the v0.2
compound value and the median matched SpringerMaterials value is `0.05`; the
90th percentile is `0.669`; the maximum is `10.2`.

The largest discrepancy is `Ethyl isothiocyanate`. The original open NBS table
and the restricted SpringerMaterials record appear to reflect different source
measurements. It is flagged for manual review rather than silently changing
the v0.2 value.

## Next Use

Match these records to v0.2 by canonical structure and compare values at
compatible temperatures. Keep matches in the restricted area unless the
redistribution status is resolved.
