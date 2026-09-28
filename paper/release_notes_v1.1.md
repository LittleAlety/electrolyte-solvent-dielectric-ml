# v1.1 release notes

**Released:** 2026-09-28 · **Dataset:** v0.3.3, `data/dielectric_v03.csv` **unchanged**
(digest `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`) · **Archived by:** Zenodo
**DOI:** https://doi.org/10.5281/zenodo.23001408 (concept DOI
https://doi.org/10.5281/zenodo.22957695), minted from this GitHub release.

This release does **not** republish or amend anything from v1.0. It adds the Week 18 and
Week 19 evidence bundles on top of the same frozen dataset.

## What this release adds

- **Week 18 post-cap path ranking** — eight independently pre-registered lanes, every one
  `promoted = false`, zero attempts at the main scoreboard (cumulative 11 unchanged):
  P0 XGB hyper-parameter grid, P1 five-seed endpoint, P2 Onsager/Kirkwood delta-learning,
  P3 conformer flexibility, P5 Uni-Mol embeddings, P6 log-space + isotonic calibration,
  W18-A row-level viscosity unfreeze, W18-B declared applicability domain.
- **Week 19 literature-driven three-line lanes** — D1 the plan-vs-machine state audit,
  D2 the Batt-P30K direct-hit check, D4 the extraction template Phase-0, D5 the Chemprop
  viscosity cross-model check, D6 the multi-objective ranking key, plus the N2 xTB-vs-Batt
  orbital cross-check and the channel-transfer plan.
- `reports/decisions_log.md` sections 28.42-28.51.
- Eight Week 18 figures (`probes/artifacts/w18_*.png`) and the Week 18 export bundle
  (`probes/export_week18_results.py`).

## Headline readings (honest, no extrapolation)

- Frozen baseline `0.4091179943351143` and frozen headline `0.4766400383507876` are unchanged.
  The honest five-seed endpoint of the headline arm is `0.45401075998423623`: the published
  0.4766 is the largest single draw of the five pre-locked seeds.
- Best Week 18 arm is P0 `hp d4xn200` at a cross-seed endpoint of `0.5998203128630835`,
  `+0.01370607964226378` over the `Physical(lever4)` anchor `0.5861142332208197` —
  **0.00018 short of 0.60**, so it is reported as `partial`, not as a pass.
- W18-B applicability domain reports a second board beside the global one and never replaces
  it: global `0.45401075998423623`, D1 in-domain `0.524012313223719`, D1 out-of-domain
  `0.3198024498133034` (40 of 97 compounds out of domain).
- The viscosity channel moved first: the in-service head is `0.17477197208762` family-level /
  `0.15686276760094522` row-level against a `0.15` gate, i.e. 0.006863 short; the Chemprop
  cross-model check reaches `0.08506361044387624` row-level / `0.08908094784092072`
  family-level and does clear the gate (`chemprop_better`, `promoted = false`).

## Honest negative results carried in this release

- Onsager / Kirkwood delta-learning is refuted on this pool: `onsager_delta_xgb`
  `0.2242978111516481` against the direct reference `0.5861142332208197`, and the placebo arm
  did not collapse back to the reference as pre-registered — both deviations are logged.
- Pre-trained 3D embeddings (Uni-Mol) as a feature block: `0.1102020209457352`, 0/5 seeds
  positive, the most negative reading of the week.
- Conformer-variance columns: `0.5691705415075562`, below the anchor.
- Hyper-parameter retuning does not close 0.60: the 0.00018 gap is reported as a gap.
- The Batt-P30K orbital channel only half-passes: HOMO `r = 0.8223` with leave-one-out MAE
  `0.3475 eV` (`usable`, but by 0.0025 eV and sensitive to one fold), while LUMO `r = 0.4663`
  and gap `r = 0.1921` stay `reference_only`.
- The Week 19 extraction lane produces no reading this week (`produces_reading = false`).

## Licensing

- Source code: MIT (`LICENSE`). Dataset: CC BY 4.0 (`LICENSE-DATA.md`).
- `Batt-P30K` (Batt-SLM, MIT) is the only clean external orbital channel; THEMol is
  CC BY-NC 4.0 and stays confined to the internal reference layer.
- No Reaxys value and no restricted-library value enters any pool, feature or delivered
  bundle.

## Reproduce

```
python probes/export_week18_results.py --overwrite
python probes/plot_week18.py --check
python -m pytest -q
```
