# Dielectric Dataset v0.2

## Result

`data/dielectric_v02.csv` contains **210 unique compounds** in the
293.15-303.15 K window:

- 100 unchanged v0.1 compounds.
- 110 new compounds from NBS Circular 514.
- 22 four-figure source estimates and 88 three-figure source estimates.

The v0.2 verifier passes `8/8` checks, including v0.1 preservation, source-row
joining, structure regeneration, temperature gating, metadata completeness, and
SHA256 provenance.

## Source

NBS Circular 514, Arthur A. Maryott and Edgar R. Smith, 1951:

- DOI: `10.6028/nbs.circ.514`
- Public PDF:
  `https://nvlpubs.nist.gov/nistpubs/Legacy/circ/nbscircular514.pdf`
- PDF SHA256:
  `cb3fa9239fd977d7fa85389fbc219baea69667d5cc7c9e5382b09157fda40683`

The publication contains critically evaluated static dielectric constants for
more than 800 pure liquids, with temperature, temperature-coefficient, and
reference metadata.

## Selection

The first extraction pass covered organic table pages 13-47. For the initial
v0.2 expansion:

1. Retained tabulated values at 20-30 C.
2. Retained only three- or four-figure estimates.
3. Excluded frequency-footnoted rows.
4. Excluded known hazard motifs and reactive aliphatic halides, alkynes, vinyl
   heteroatom motifs, and hydrogen cyanide.
5. Resolved names through PubChem with CACTUS fallback.
6. Canonicalized structures with RDKit, checked formulas against the source,
   and deduplicated by InChIKey.
7. Ranked the remaining structures using AL-longlist hits, SolvFunc similarity,
   polarity-related functional groups, source quality, and a size penalty.

The result was 215 resolved new structures; the 110 highest-ranked eligible
structures entered v0.2.

## Independent Audit

A separate audit sampled 20 selected rows, one from every PDF page 13-32. All
sampled names, formulas, dielectric values, temperatures, and page identifiers
matched the source PDF. The same audit found one metadata error: carbon
disulfide `2.641` was labeled as three figures instead of four. The source
transcription and all dependent artifacts were corrected and regenerated.

The remaining residual risk is that the independent audit was a stratified
sample, not a complete 110-row typography review.

## Learning-Curve Result

Using the fixed v0.1 test set, the 10-repeat learning curve did not show an
immediate accuracy gain from the v0.2 additions:

| Training compounds | v0.1 mean R2 | v0.2 mean R2 |
| ---: | ---: | ---: |
| 20 | -0.00114 | -0.16076 |
| 40 | 0.11975 | -0.10368 |
| 60 | 0.12458 | -0.12594 |
| 80 | 0.23126 | -0.04117 |
| 120 | not applicable | -0.09926 |
| 160 | not applicable | 0.06471 |
| 180 | not applicable | 0.05781 |

The larger dataset covers more chemical heterogeneity, and the current
Morgan+RBF GPR does not exploit it at these training sizes. The correct
conclusion is that v0.2 passes the data-size gate, while the current feature and
kernel choice still fails to convert the added data into a better fixed-test
model.

## Artifacts

- `data/dielectric_v02.csv`
- `probes/dielectric_v02_summary.json`
- `data/processed/nbs514_structure_candidates.csv`
- `data/processed/dielectric_v02_learning_curve.csv`
- `probes/dielectric_v02_learning_curve_summary.json`
- `probes/artifacts/dielectric_v02_learning_curve.png`
- `scripts/verify_dielectric_v02.py`
