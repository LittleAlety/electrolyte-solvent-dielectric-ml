# v1.2 release notes

**Released:** 2026-09-28 · **Dataset:** v0.3.3, `data/dielectric_v03.csv` **unchanged**
(digest `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`) · **Archived by:** Zenodo
**DOI:** https://doi.org/10.5281/zenodo.23001632 (concept DOI
https://doi.org/10.5281/zenodo.22957695), minted from this GitHub release.

This release does **not** republish or amend anything from v1.0 or v1.1. It closes Week 19 on
top of the same frozen dataset; every artifact shipped by v1.1 keeps its bytes.

## What this release adds

- **W19-D3 Onsager residual layer under an out-of-family split** — the capped Week 18
  registration re-run on a structure-family grouped split (234 rows / 234 distinct InChIKeys /
  111 Murcko-Butina structure groups, 50 folds). Three pre-declared questions are adjudicated
  separately and are never mixed.
- **W19-D7 safety-channel registry (N14)** — flash point / boiling point / melting point /
  safety window are entered as a fourth candidate channel with tool, version and licence
  provenance; `registered_not_executed`, `produces_reading = false`, `shot_number_taken = null`.
- **W19-D8 orbital migration decision gate** — the Batt-P30K versus THEMol decision that the
  Week 19 plan requires to be recorded rather than silently switched.
- **W19-D9 shots ledger** — the shot-number accounting the plan discipline section asks for.
- `reports/decisions_log.md` sections 28.52-28.55.
- The Week 19 export bundle (`probes/export_week19_results.py`,
  `tests/test_export_week19_results.py`) and its figure
  (`probes/artifacts/w19_chemprop_viscosity.png`).

## Headline readings (honest, no extrapolation)

- Frozen baseline `0.4091179943351143` and frozen headline `0.4766400383507876` are unchanged,
  and the honest epsilon endpoint stays `0.5861142332208197` with the five-seed mean of the
  headline arm at `0.45401075998423623`. Neither 0.60 nor 0.70 is reached.
- **D8** — HOMO `r = 0.8223` with leave-one-out MAE `0.3475 eV` against the double gate
  (MAE <= 0.35 eV and r >= 0.80) clears by `0.0025 eV` only, with 16 of 49 folds over the gate,
  so it is `usable` at the boundary. LUMO `r = 0.4663` and gap `r = 0.1921` stay
  `reference_only`. The LUMO MAE of `0.1984 eV` is registered as an **empty reading**: the
  constant baseline is `0.2089 eV`, the relative skill is `0.0504` and the OLS slope is
  `0.0550`. **Decision: Batt-P30K is not promoted to primary descriptor source for the
  HOMO-LUMO channel and remains a second reference layer; THEMol stays the in-service primary
  source.**
- **D3** — under the structure-family split the three answers are
  `delta_layer_survives_out_of_family`, `sign_split_not_preserved_out_of_family` and
  `zone_still_unsolvable_out_of_family` (best confirmatory MAE `72.0614455552206`).
- **D9** — shots 19 and 20 are recorded as already spent (their assets were in the repository
  before this week), shot 21 is assigned to the extraction probe, and `next_shot_number = 22`.
  Both readings of the ambiguous branch converge on 22, so the ruling is insensitive to it; only
  the label of 19/20 needs the author.
- Week 19 makes **zero attempts** at the main scoreboard; the cumulative total stays **11**, and
  all eleven lanes are `promoted = false`.

## Honest negative results carried in this release

- The out-of-family re-run does not rescue the sign split: the domain sign split that held
  in-family is not preserved once whole structure families are held out.
- The epsilon > 60 zone remains unsolvable out of family.
- The HOMO-LUMO channel fails as a channel: the decision is taken on the weakest sub-channel and
  two of the three fail. The falsifiable prediction PR-5 is recorded as **falsified**
  (paired-layer gap `r = 0.4343` at n = 4668 against the main arm `0.1921` at n = 49).
- The HOMO pass is a boundary pass, not a margin.
- The safety channel is registered with `not_verifiable_in_repo` licences and an untested
  coverage gate, so nothing about safety is claimed this week.
- The shots ledger is `locked_pending_author_confirmation`: it was written after the seven lanes
  ran, so it does not claim `locked_before_run`.

## Licensing

- Source code: MIT (`LICENSE`). Dataset: CC BY 4.0 (`LICENSE-DATA.md`).
- `Batt-P30K` (Batt-SLM, MIT) is the only clean external orbital channel; THEMol is
  CC BY-NC 4.0 and stays confined to the internal reference layer.
- The Week 19 safety-channel registry ships no third-party model or table; its entries name
  upstream tools only, and their licences are recorded as not verifiable in this repository.
- No Reaxys value and no restricted-library value enters any pool, feature or delivered bundle.

## Reproduce

```
python probes/export_week19_results.py --overwrite
python -m pytest -q
```
