# v1.0 release notes

**Released:** 2026-09-25 · **Dataset:** v0.3.3 · **Archived by:** Zenodo
**DOI:** https://doi.org/10.5281/zenodo.22957696 (concept DOI
https://doi.org/10.5281/zenodo.22957695), minted from this GitHub release.

## What this release contains

- `data/dielectric_v03.csv` — the canonical dataset: **246 compounds x 38 columns**,
  digest `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`
  (7/7 checks in `scripts/verify_dielectric_v03.py`).
- The frozen benchmark: 236 modelling rows, 10x5 cross-validation, hybrid
  R2 0.3636 / MAE 6.6862 / Spearman 0.8282, recomputed by
  `scripts/verify_v032_benchmarks.py`.
- Six reproducible figures, each pinned to the script that draws it
  (`scripts/verify_paper_figures.py`).
- The data descriptor draft (`paper/full_draft.md`), a generated artifact:
  `scripts/build_paper_full_draft.py --check` fails if it drifts from its sections.
- Three verification layers: per-artifact verifiers, a manuscript-to-artifact
  consistency gate, and an export manifest gate.

## Honest negative results carried in this release

- a ranking-oriented neural head at Spearman 0.884 with R2 = -0.172 that does not
  recover under pre-registered calibration (-0.309);
- a density feature that adds nothing (-0.001 R2);
- an added-carbonate gain indistinguishable from zero (p = 0.11);
- a conformal interval whose marginal coverage holds (0.915) while its
  high-permittivity stratum collapses to 1.5-26%;
- an Onsager-based applicability rule that covered 0 of 150 high-permittivity rows
  and was rejected in favour of a structural SMARTS rule (150/150).

## Known data gaps (disclosed, not blocking)

- **FEC**: two legs recorded, 78.4 at 296.15 K (Kobayashi 2003) and 107 at 25 C
  (read only through the Ue et al. 2014 compilation); `model_ready=false`.
- **VC**: the Knovel range conflicts with the primary value; `model_ready=false`.
- **MOPN**: 36.0 rests on a secondary compilation; no independent primary measurement.
- **DC-200**: the membership table could not be obtained; the GSDS Zenodo archive's
  15,524 entry names were listed and contain no per-molecule table.
- Four boundary compounds (3 ionic liquids + Fe(CO)5) are explicitly
  `out_of_scope_ionic_or_organometallic` rather than silently dropped.

## Reproduce

```
python scripts/verify_dielectric_v03.py
python scripts/verify_v032_benchmarks.py
python scripts/verify_paper_figures.py
python scripts/check_paper_artifact_consistency.py
python scripts/build_paper_full_draft.py --check
python -m pytest -q                      # 868 passed at v1.0
```

## Licensing

Data under CC BY 4.0 (`LICENSE-DATA.md`); source code under MIT (`LICENSE`).
Per-row upstream licences and redistribution status are in the dataset itself.
