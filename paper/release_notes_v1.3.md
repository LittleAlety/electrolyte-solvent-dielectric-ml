# v1.3 release notes

**Released:** 2026-09-28 · **Dataset:** v0.3.3, `data/dielectric_v03.csv` **unchanged**
(digest `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`) · **Archived by:** Zenodo
**DOI:** https://doi.org/10.5281/zenodo.22957695 — the version-independent concept DOI, which
resolves to the newest version of this archive.
**Version DOI (v1.3):** https://doi.org/10.5281/zenodo.23019467 — record `23019467`, created
`2026-09-28T15:44:02Z`, minted by Zenodo from the `v1.3` GitHub release. This line is written by
the backfill commit, after the tag froze: a version DOI cannot exist before the release that
mints it, and the archived tree at `v1.3` therefore names only the concept DOI. This is the Week
20 structural fix to the defect recorded in `reports/decisions_log.md` section 28.65 item 5,
which v1.1 and v1.2 both shipped.

This release closes **Week 20**. It publishes twelve lanes, and for the first time since the
headline was frozen it promotes one of them onto the main scoreboard.

## What Week 20 is

Weeks 16 to 18 killed the epsilon *representation* levers systematically: different fitted
models, network stacking and bagging, foreign chemical space, mixed anchors and restricted
sources were all measured and all failed. Section 28.55 closed that line and, with it, the
premise that 0.70 was reachable by adding compounds.

Week 20 therefore stopped buying representation and bought an optimiser instead, then spent the
remaining eleven lanes on the channels *next to* epsilon rather than on epsilon itself.

## The one promoted lane: W20-4, epsilon second stage

The single pre-registered arm `hp2_d4_n200_lr0.05_mcw5_ss0.8_cs0.8_bin128` (depth 4, 200 trees,
learning rate 0.05, `min_child_weight` 5, `subsample` and `colsample_bytree` 0.8, 128 bins)
scored a cross-seed mean of **0.6216672295270079** against the 0.60 gate, with a five-seed lower
bound of **0.5999547508973201** against the 0.55 floor. Per-seed means:
seed 42 `0.5999547508973201`, 1234 `0.6218233838892735`, 2026 `0.6202090430932049`,
31337 `0.6395023798932657`, 7 `0.6268465898619755` — four of five seeds clear 0.60 on their own.

Registered mechanism: the frozen depth-2 / 200-tree / 0.05 hyper-parameters were chosen for a
2048-column sparse Morgan block, and depth 2 is four leaves per tree on the 13-15 dense physical
columns that actually won the representation shoot-out. The honest expectation was fixed before
the run as +0.01 to +0.05, explicitly labelled a judgement rather than a measurement.

Caliber anchors that were re-measured rather than assumed:

- the `xgb_reference` anchor at seed 42 reproduced its frozen `0.6080587938801277` bit for bit
  (absolute gap 0.0 against the frozen single-shot value);
- its cross-seed mean over the same five seeds is `0.5861142332208197`, i.e. the honest
  single-representation endpoint;
- leakage audit: 50 folds per seed x 5 seeds, **0** folds with a straddling compound;
- placebo: permuting the target collapses the same registered arm to a cross-seed mean of
  **0.41179237661783363** (lower bound `0.37675835219632026`), below both the gate and the real
  arm, so `collapsed = true`.

**Discipline that matters more than the number.** The highest arm inside the grid,
`hp2_d4_n200_lr0.05_mcw5_ss0.8_cs0.8_bin64`, reached a cross-seed mean of
**0.6249509650342622** — higher than the registered arm. It was **not** used to change the
verdict. The verdict is decided by the one pre-registered arm; the other eight arms x five seeds
ship as side information only. The arm is written to the ledger as **one attempt this week,
twelve cumulative**.

## The eleven lanes that are not promoted

### Eta channel — W20-1 fairness check, W20-3 ranking key v1

W20-1 asked whether the eta channel's incumbent predictor is actually worse than a learned model,
or merely under-budgeted. Both sides were given the same out-of-fold protocol (GroupKFold by
InChIKey, 5 folds x 5 repeats) and the incumbent was upgraded to the strongest budget it had
never been given (a three-configuration grid, inner-fold selection on training rows only, and a
three-seed ensemble). On the row-level pool (4151 rows / 976 keys) Chemprop scored
**0.1054414994165841** against the incumbent's **0.15963939692814613**, delta
**-0.05419789751156204** against a 0.15 gate and a 0.02 tolerance, replicated across all three
ensemble seeds. Verdict: `eta_crosses_gate_out_of_fold`.

On the family-level pool (3582 rows / 957 keys) both sides clear 0.15
(Chemprop `0.1014586835798006`, incumbent `0.1471395849716971`), recorded as
`incumbent_budget_closes_gate`. The main verdict reads the row-level pool only. The lane's
placebo did **not** collapse (`0.3952143564868206` against a constant predictor's
`0.39910182316678505`) and is registered as such; it is not evidence of collapse.

W20-3 then widened the screening ranking key only as far as its own pre-registration allowed.
It did not: folding eta in requires a new pre-registration that pins the key column and its
direction, and the module still reads eta's gate value at the frozen family-level
`0.17477197208762` (above 0.15, not cleared). So the key remains two equally weighted dimensions
(HOMO / LUMO) with
`extension_status.viscosity = {verdict_present: true, verdict: eta_crosses_gate_out_of_fold, merged: false}`.
Its Batt-SLM candidate table holds 115,756 rows (45,093,401 B, sha256
`b52f720bfa904a1c71e730e0d8fb2bb7ec7d4041ce9aae7ce7b1835c518ae6c5`), all out of domain:
`in_domain = 0`, `front_size = 0`, `top_20 = []`. An empty frontier is the domain rule working,
not a failure: out-of-domain candidates are given no score rather than a low score that would be
misread.

### Safety channel — W20-2, two steps

Step 1 measured influence without fitting anything: the liquid-window filter moves the whole
ranking head (purity@10/20/50 = `0.0 / 0.0 / 0.02` without it, `1.0 / 1.0 / 0.98` with it;
Jaccard@10/20/50 = `0.0 / 0.0 / 0.010101010101010102`; 20 / 40 / 98 candidates changed), but the
lift comes mainly from domain inclusion rather than from the safety channel itself.

Step 2 (shot 22) asked whether the channel is modelable at all. Melting point, boiling point and
flash point share 186 rows and 281 features (Morgan count r2 256 + 25 RDKit descriptors), fitted
with ExtraTreesRegressor(300) under GroupKFold by InChIKey. Group-keyed MAE is
`24.97767123875773` / `25.395136749805708` / `18.93154740989103` K against baselines of
`40.645869505093216` / `51.918480354950496` / `41.417524232531726` K, while every placebo
collapses (`48.36` / `59.37` / `47.20` K). The channel is modelable; the lane is not promoted.

### Refusal rule — W20-5

The high-permittivity region now has an executable refusal rather than a silent prediction. Of
31,949 registry rows, 247 carry a permittivity and 187 are refused (**0.757085020242915**), with
9 high-permittivity rows, 183 domain rows, 5 double hits and 60 still sortable. Exit code:
`refused_experimental_queue`.

### Ceiling probes — W20-6a / 6b / 6c

Three independent attempts to break the open-licence compound ceiling, all negative:
Org-Mol provenance is `inadmissible`; the NBS-514 transcription yields 636 rows -> 121 roster
hits -> 28 candidates -> **26** usable (25 unique connected blocks) with all three
admissibility gates passing and still `ceiling_break = false`; the CEP 88k source is
`not_identifiable` with `licence_verdict = not_verifiable` and is filed Tier C.

### Label provenance — W20-7

A closed four-role vocabulary and an 11-row sidecar now attribute every label channel to its
source, covering 34,131 keys (density 2178, dielectric 247, liquid_window 218, orbitals 29,868,
redox_label 392, viscosity 1228) with a role tally of 255,254 / 1,250 / 5,259 / 0.

### Funnel KPI board — W20-8

The funnel is now scored on ranking, not on magnitude: pooled `auc_gt15 = 0.8947205768486257`,
`auc_gt30 = 0.9392420870425322`, Spearman `0.7737616891926036`, top-20 precision `0.95` against a
base rate of `0.26258205689277897`, enrichment `3.4275 / 3.617916666666667 / 2.5135000000000005`.
R2 is explicitly a forbidden funnel KPI, because the diagnosis is that ranking is learned and
magnitude is not. The board also caps the ladder: the open-licence roster is 153 compounds with an
upper bound of 157 (widest 161), so the "0.58-0.65 needs a doubled compound count" rung is
revised, net new compounds +4, `status_after = capped`.

## What is frozen

- Baseline `0.4091179943351143` — retained, unchanged, still the comparability anchor.
- Headline `0.4766400383507876` — retained, unchanged, not rewritten by this release.
- Dataset bytes — unchanged; `data/dielectric_v03.csv` keeps its digest.
- No Reaxys number and no restricted-library number enters any pool, feature or deliverable.
- `0.6216672295270079` (this release's arm) and the single-shot `0.6080587938801277` name
  different quantities and are **never** compared, divided or added.

## What this release does not claim

- It does not claim the epsilon gate generalises beyond the arm's own cross-seed endpoint.
- It does not claim the eta channel's gate is closed: the row-level verdict is a modelling
  result, not a legal or experimental one.
- It does not claim any ceiling was broken; all three probes are negative and are shipped as
  negative.
- It does not claim 0.70 has a path. Under the current licence and physics constraints it does
  not.

## Release discipline kept

- No existing tag is moved: `v1.0`, `v1.1`, `v1.2` and `v1.2.1` all keep their commits.
- No GitHub release body is edited after its DOI is minted; measured under this concept, body
  edits re-trigger archiving.
- The archived files carry no self-referential placeholder: both `README.md` and this file name
  only live, resolving DOIs at the tagged commit.
- One version number keeps exactly one record.

## Reproduce

```
python probes/export_week20_results.py --overwrite
python -m pytest -q
```
