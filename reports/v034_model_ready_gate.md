# v0.3.4: the `model_ready` gate, and what it did to the benchmark

Date: 2026-09-24
Scope: P0-2 defect that was open from v0.3.2 through v0.3.4-pre
Artifacts: `probes/v032_ablation_summary.json`,
`probes/v032_target_scaffold_summary.json`,
`probes/v032_controlled_comparison_summary.json`,
`probes/dielectric_v03_representation_ablation_summary.json`,
`data/processed/dielectric_v03_exclusions.csv`

## 1. The defect

`data/dielectric_v03.csv` marks a row `model_ready=false` when its value is an
unresolved source conflict or is awaiting primary confirmation. Until v0.3.4
**nothing in the modelling pipeline read that column.** The only gates were the
curated exclusion list and the physical-feature status. Vinylene carbonate
(`model_ready=false`, `conflict_open`, eps = 126, contested range 78-127) was
therefore trained on and scored in every published benchmark from v0.3.2
onward.

The feature tables carry no `model_ready` column, which is why the defect was
invisible: the flag lives in the dataset roster and never travelled with the
features.

## 2. The fix

`probes/dielectric_representation_ablation.py::read_modelling_rows` is the single
choke point through which every dielectric fit obtains its rows. It now returns
a three-way split:

```
read_modelling_rows(path, *, dataset_path=DATASET_PATH)
    -> (modelling_rows, failed_feature_rows, withheld_not_model_ready_rows)
```

Design decisions, all deliberate:

1. **The gate reads the dataset roster, not the feature file.** `model_ready` is
   dataset-level provenance; the join is on InChIKey.
2. **Withheld rows are returned, never silently dropped.** A withheld row and a
   failed-feature row are different facts and are reported under different
   fields (`withheld_not_model_ready_*` versus `failed_physical_feature_*`).
   Conflating them would have hidden the very thing this fixes.
3. **A feature row outside the roster raises.** If a feature table contains a
   compound the dataset does not know, its status is unknowable, so the run
   fails rather than guessing. All shipped feature tables currently pass this.
4. **The accounting invariant was extended**, not relaxed:
   `fitted + failed_features + withheld + exclusions == source rows`.
5. **Exclusions are matched against the source lineage.** The exclusion file now
   also records 3-methoxypropionitrile, which previously was held out
   *implicitly* by never having received a feature row. When a script runs an
   older lineage, unmatched exclusions are reported under
   `excluded_not_in_source` rather than silently counted.

## 3. Effect on the fitted set

| Lineage | Source rows | Fitted | Excluded | Feature failures | Withheld |
|---|---|---|---|---|---|
| v0.3.2 (245) | 245 | 236 | 4 | 4 | 1 |
| v0.3.3 (246) | 246 | 236 | 5 | 4 | 1 |

The withheld row is vinylene carbonate in both lineages. The v0.3.3 roster adds
3-methoxypropionitrile as an explicit exclusion, so its accounting closes at
246 = 236 + 5 + 4 + 1.

## 4. What changed in the reported numbers

### Main benchmark (10x5 repeated CV, raw target)

| Representation | R2 before -> after | MAE before -> after | Spearman before -> after |
|---|---|---|---|
| Morgan | 0.2230 -> 0.2402 | 8.216 -> 7.612 | 0.689 -> 0.722 |
| Physical | 0.3538 -> 0.3422 | 7.495 -> 7.098 | 0.801 -> 0.802 |
| Morgan+Physical | 0.3660 -> 0.3636 | 7.133 -> 6.686 | 0.814 -> 0.828 |

The headline R2 moves by -0.0024; MAE improves by 0.45. The change is a fitted-set
change, not a model change -- the model, the folds and the seed are untouched.

### Controlled PC/EC comparison (the important result)

| Representation | Baseline R2 | +PC/EC (train only) | Paired delta | 95% CI | p |
|---|---|---|---|---|---|
| Morgan | 0.2203 | 0.2191 | -0.0012 | [-0.006, +0.003] | 0.59 |
| Physical | 0.3201 | 0.3194 | -0.0007 | [-0.016, +0.014] | 0.92 |
| Morgan+Physical | 0.3456 | 0.3515 | **+0.0059** | [-0.002, +0.013] | 0.11 |

Before the gate the same control reported **+0.0265** for the hybrid and
**+0.0502** for Physical. Both were driven by the withheld row: propylene
carbonate and ethylene carbonate are structural analogues of vinylene carbonate,
so appending them to the training folds mostly improved the prediction of that
one contested compound. Removing it collapses the effect.

**The honest conclusion is that adding PC/EC broadens chemical coverage but
delivers no measurable accuracy gain on the v0.3 compounds at this sample size.**

Fold churn also falls from 1272/2350 (54.1%) to 1224/2340 (52.3%), because the
shared-compound set shrank.

### Scaffold/cluster holdout

The extrapolation table was re-derived on 236 rows. The qualitative ranking is
unchanged -- Physical with `log(eps-1)` remains best (R2 0.276 +/- 0.044, MAE
6.669 +/- 0.218, Spearman 0.862 +/- 0.016) -- but the numbers differ from the
237-row table and the paper now carries the 236-row values.

## 5. Enforcement

- `scripts/check_paper_artifact_consistency.py::check_modelling_set_and_controlled_delta`
  re-derives the fitted-row count and the paired R2 gain and CI from the
  artifacts, and fails the build when the prose disagrees.
- `tests/test_dielectric_representation_ablation.py` pins the three-way split,
  the difference between a withheld row and a feature failure, the
  unknown-roster error, and the real shipped tables (exactly one withheld row,
  named vinylene carbonate).
- `tests/test_build_dielectric_v03.py::test_only_known_non_model_ready_rows_reach_the_modelling_feature_file`
  now also asserts that the gate withholds exactly the pinned offender set.
- `tests/test_paper_artifact_consistency.py` gains injected-drift tests for both
  new checks.

## 6. Deliberate non-changes

- The feature tables still contain vinylene carbonate. They are an inventory of
  what was featurized, and removing the row would silently change row counts in
  unrelated artifacts. The gate, not the inventory, decides fitness.
- No `dielectric`, `T_K`, `source_doi` or `model_ready` value changes;
  `data/dielectric_v03.csv` was byte-identical in that round (sha256
  `2cd58144...` as of v0.3.4; v0.3.11 was
  `765fd8e04270f3e277681d6ae8e6200bfcc77c8841a89ebe0f8a3a70bc646b60`; v0.3.12 was
  `1b285fe852c13a99e26cc94e85ffab389857351cd4fca36aed0ccf3f40d22456`; the current revision is
  `a446c216874538d900e9f3ebbf18178926b812b77a213a395f4ff8cddfc01085` as of
  v0.3.13. Every revision up to and including v0.3.11 touched provenance
  metadata only; v0.3.12 promoted FEC's 78.4 to the stored value and rewrote
  both withheld rows' provenance; v0.3.13 changed only FEC's `conflict_status`
  and `notes` (twice: the 107-leg compilation read, then the addendum registering the
  downstream 40 C restatement of the 78.4 leg). No `model_ready=true` row has changed).
- Historical reports keep their v0.3.1-era numbers as records of what was
  reported then; each is annotated where it conflicts with the current state.

## 7. Reproducing

```
.venv\Scripts\python.exe scripts\build_dielectric_v03.py
.venv\Scripts\python.exe probes\dielectric_representation_ablation.py \
  --input data/processed/dielectric_physical_features_v03.csv \
  --source data/dielectric_v03.csv \
  --exclusions data/processed/dielectric_v03_exclusions.csv \
  --repeat-output data/processed/dielectric_v03_representation_ablation_repeats.csv \
  --cv-output data/processed/dielectric_v03_representation_ablation_cv.csv \
  --predictions-output data/processed/dielectric_v03_representation_ablation_predictions.csv \
  --summary-output probes/dielectric_v03_representation_ablation_summary.json \
  --plot probes/artifacts/dielectric_v03_representation_ablation.png
.venv\Scripts\python.exe probes\dielectric_target_and_scaffold.py
.venv\Scripts\python.exe probes\v032_controlled_comparison.py
.venv\Scripts\python.exe scripts\check_paper_artifact_consistency.py
```

## 8. Residual limitation

The gate withholds whole compounds, not individual temperature rows, and it
fails closed only for the `model_ready` flag. A row whose value is wrong but
marked ready is still fitted; the conflict records and the cross-source
verifiers remain the defence there.
