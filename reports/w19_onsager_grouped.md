# W19-D3: the Onsager residual layer under an out-of-family split

Task `week19_w19d3_onsager_grouped`, generated 2026-09-27T18:09:25.113107+00:00 (schema_version 1).

## 0. Red lines and positioning

- `promotes_no_reading = true`, `main_scoreboard_untouched = true`, `scoreboard_attempts_delta = 0`,
  `produces_deployable_model = false`. The epsilon main scoreboard stays at 11 cumulative attempts,
  and the frozen baseline `0.4091179943351143` and frozen headline `0.4766400383507876` are untouched.
- `reaxys_numeric_red_line`: Reaxys numeric values never enter any pool, feature or deliverable; this
  probe cites none.
- `onsager_is_label_free_and_deterministic = true`, `onsager_version =
  onsager_lorentz_lorenz_reaction_field_v1`. The Onsager column is computed once, outside every fold, so
  it cannot carry a label into training.
- `role`: appendix evidence for the capped W18 registration plus the mechanism disclosure layer; this is
  **not a promotion arm**.
- **Vocabulary gap registered on purpose**: this summary carries no `read_only`, no `models_fitted` and no
  `promoted` key. The literal keys that do the same job here are `promotes_no_reading`,
  `main_scoreboard_untouched`, `scoreboard_attempts_delta` and `produces_deployable_model`. The probe is
  read-only in effect (it deploys nothing and promotes nothing), but that word is not in the artifact and
  is not asserted as if it were.

## 1. Pool and splitters

| item | value |
| --- | --- |
| rows | 234 |
| distinct InChIKey | 234 |
| structure groups (Murcko scaffold, Butina for acyclic) | 111 |
| singleton structure groups | 76 |
| largest structure group | 31 |
| failed rows | 4 |
| withheld rows | 1 |
| strata lt20 / 20_60 / gt60 | 182 / 47 / 5 |
| domains none / assoc_only / ionic_only / both | 150 / 66 / 15 / 3 |

Three readings come out of this one pool and are never mixed:

- `structure_family` (primary grouped reading; 111 groups, 5 folds x 10 repeats = 50 folds, train 149-206).
- `row_level_reproduction` (`sklearn.model_selection.RepeatedKFold`, 5 x 10 = 50 folds, train 187-188): the
  side-by-side row-level baseline, and the bit-for-bit replay of the frozen row-level summary.
- `inchikey` (degenerate by construction: 234 rows carry 234 distinct InChIKeys, so every group is a
  singleton and the splitter collapses onto a plain row-out split). It was declared degenerate before the
  run and is never counted as out-of-family pressure.

Group assignment for the primary reading is `np.random.default_rng(SEED + repeat).permutation` over the
sorted group order, then round-robin assignment to folds; the fold seed rule is SEED + split_index.

## 2. Readings, per arm

### 2.1 Primary grouped reading `structure_family`

| arm | MAE | R2 | Spearman | MAE assoc_only | MAE ionic_only | MAE gt60 |
| --- | --- | --- | --- | --- | --- | --- |
| O0_onsager | 10.488447267414694 | -0.682296765194945 | 0.67637461648358 | 16.66422703535138 | 41.22140207561585 | 87.02347866934045 |
| O1_structured_offset | 9.712536036273614 | -0.5243166065971072 | 0.7508995711631504 | 14.83331535120289 | 42.864265815767226 | 83.21545083593107 |
| R0_direct_regression | 7.6638502783946505 | 0.2618082947442962 | 0.7576630886950296 | 12.423837183120286 | 8.420057119263543 | 73.94743297195434 |
| R1_direct_with_logg | 7.105924504314814 | 0.1840837816325239 | 0.7944375166885387 | 12.656377726344784 | 14.205047527750333 | 69.80816974258423 |
| D0_delta_core | 9.462750080736846 | -0.2823334839412389 | 0.7496583230171197 | 13.966612961983486 | 34.93832021859354 | 72.0614455552206 |
| D1_delta_core_morgan | 9.732598032673137 | -0.512513404542229 | 0.7301984899382461 | 13.031472247883638 | 40.17556915457252 | 76.81859574687758 |
| D2_delta_log | 16.6468345368987 | -4.0825878705138585 | 0.6418337835273601 | 23.5931562114305 | 50.20548179109598 | 93.62813989821383 |
| D3_delta_leaky | 8.562802610068925 | -0.062377601950978835 | 0.7558608323774854 | 13.598016619551448 | 23.7346588399047 | 65.60852006118998 |

`D3_delta_leaky` is the registered leaky control arm; it is not one of the three confirmatory delta arms
(`D0_delta_core`, `D1_delta_core_morgan`, `D2_delta_log`) and is not gated.

Two facts have to be stated next to this table. First, on this reading the best overall MAE is not a delta
arm at all: `R1_direct_with_logg` reads 7.105924504314814 and `R0_direct_regression` reads
7.6638502783946505, both below every delta arm. Second, `D0_delta_core` at 9.462750080736846 is inside the
bootstrap band of `O0_onsager` at 10.488447267414694: the paired compound-cluster bootstrap gives
delta_mean = -1.0256971866778457 with delta_ci95 = [-2.0646583943890198, 0.02264978539549294], which
straddles zero. The gate outcome is therefore a repeat-averaged point-estimate result, not a separated one.

### 2.2 Row-level reference `row_level_reproduction` (never mixed with 2.1)

| arm | MAE | R2 | Spearman |
| --- | --- | --- | --- |
| O0_onsager | 10.488447267414694 | -0.682296765194945 | 0.67637461648358 |
| O1_structured_offset | 9.410772852055805 | -0.41524386193202883 | 0.7337668534738065 |
| R0_direct_regression | 6.35725856767149 | 0.3456241908943502 | 0.8286977867573793 |
| R1_direct_with_logg | 6.437591020637247 | 0.24014387187520908 | 0.8243946898736372 |
| D0_delta_core | 8.794601712769303 | -0.2213976420097256 | 0.7706927992987188 |
| D1_delta_core_morgan | 8.539002477227934 | -0.21033912582778366 | 0.7654233495915702 |
| D2_delta_log | 12.850511212667517 | -3.1046834081748615 | 0.7415093058591151 |
| D3_delta_leaky | 7.220052457534419 | 0.1894396526735172 | 0.7883800389220903 |

### 2.3 Degenerate control `inchikey`

| arm | MAE | R2 | Spearman |
| --- | --- | --- | --- |
| O0_onsager | 10.488447267414694 | -0.682296765194945 | 0.67637461648358 |
| O1_structured_offset | 9.382285325724204 | -0.40435257362407373 | 0.7378642207876995 |
| R0_direct_regression | 6.3037319758476364 | 0.34711121075047024 | 0.829228059656891 |
| R1_direct_with_logg | 6.1527453433772035 | 0.31642328052282087 | 0.8287644855811441 |
| D0_delta_core | 8.724067967948029 | -0.18984274418447 | 0.7745348957072343 |
| D1_delta_core_morgan | 8.542056461022677 | -0.18160423403127113 | 0.7655927429737276 |
| D2_delta_log | 12.965646387724146 | -3.1802960076478834 | 0.7429739275375661 |
| D3_delta_leaky | 7.049070497619115 | 0.24874165129772718 | 0.7911496221660936 |

`O0_onsager` is identical across 2.1 / 2.2 / 2.3 to the last digit, which is itself a check: Onsager is
label-free and deterministic, so only the fitted arms move with the splitter.

## 3. Gate table for the primary grouped reading

Five gates were locked in the pre-registration before any result existed. Their numeric forms are:

- `a_donor_mae_below_onsager`: `mae_assoc(arm) < mae_assoc(O0_onsager)`; the bar is 16.66422703535138.
- `b_ionic_mae_not_worse_than_onsager`: `mae_ionic(arm) <= mae_ionic(O0_onsager)`; the bar is 41.22140207561585.
- `c_high_permittivity_improved`: `mae_gt60(arm) < mae_gt60(O0_onsager)` **or** `spearman_gt60(arm) >
  spearman_gt60(O0_onsager)`; the bars are 87.02347866934045 and -0.7999999999999999.
- `d_overall_mae_below_structured_offset`: `mae(arm) < mae(O1_structured_offset)`; the bar is 9.712536036273614.
- `e_donor_mae_below_structured_offset`: `mae_assoc(arm) < mae_assoc(O1_structured_offset)`; the bar is
  14.83331535120289.

Decision level is repeat-averaged point estimates, and the gate code is reused verbatim from the frozen
row-level probe rather than re-written.

| arm | a (mae_assoc) | b (mae_ionic) | c (mae_gt60 / spearman_gt60) | d (mae) | e (mae_assoc) | passed |
| --- | --- | --- | --- | --- | --- | --- |
| D0_delta_core | 13.966612961983486 PASS | 34.93832021859354 PASS | 72.0614455552206 / -0.7699999999999998 PASS | 9.462750080736846 PASS | 13.966612961983486 PASS | **true** |
| D1_delta_core_morgan | 13.031472247883638 PASS | 40.17556915457252 PASS | 76.81859574687758 / -0.8899999999999999 PASS | 9.732598032673137 FAIL | 13.031472247883638 PASS | false |
| D2_delta_log | 23.5931562114305 FAIL | 50.20548179109598 FAIL | 93.62813989821383 / -0.6199999999999999 PASS on the spearman clause only | 16.6468345368987 FAIL | 23.5931562114305 FAIL | false |

The gate `headline_arm` for this reading is `D0_delta_core`, and the summary labels that selection as
post hoc (lowest repeat-averaged overall MAE among the confirmatory delta arms) with every per-arm gate
outcome reported next to it. `gates.passed = true` means the headline arm clears all five gates; it does
not mean that the best arm on this reading is a delta arm, because it is not (see section 2.1).

## 4. The three questions

### Q1. Does the delta layer still clear its five gates out of family?

Verdict: `delta_layer_survives_out_of_family`.

- Grouping key `murcko_butina_structure_family`, 111 groups, headline arm `D0_delta_core`,
  `headline_passed_all_five_gates = true`.
- The InChIKey control is flagged `inchikey_control_degenerate = true` and its headline arm also passes
  all five gates, which is expected once the control is degenerate and is not independent evidence.
- Per-arm failures under this reading: `D1_delta_core_morgan` fails `d_overall_mae_below_structured_offset`;
  `D2_delta_log` fails four of the five gates.

### Q2. Is the domain sign split preserved out of family?

Verdict: `sign_split_not_preserved_out_of_family`.

- Per-domain bias sign versus the row-level reading: `D0_delta_core` opposite, `D1_delta_core_morgan`
  opposite, `D2_delta_log` same, `O0_onsager` opposite, `O1_structured_offset` opposite. The grouped and
  row-level patterns agree with each other arm by arm, and both call four of the five arms opposite.
- Per-domain sign accuracy on the grouped reading, `D0_delta_core`: assoc_only 0.8318181818181818,
  ionic_only 0.5733333333333334, both 0.8666666666666666, none 0.5093333333333333.
- The reading the question was written to test is therefore a negative one: the split that shows up in
  the row-level folds does not carry over as a grouped-out fact, so it is recorded as an interpolation
  artefact of random folds rather than as a mechanism.

### Q3. Is the eps > 60 zone still unsolvable out of family?

Verdict: `zone_still_unsolvable_out_of_family`.

- `row_count = 5`, `threshold = 60`, `onsager_coverage_fraction = 0`,
  `onsager_coverage_is_split_invariant = true`.
- Best confirmatory grouped `mae_gt60` is 72.0614455552206 against a row-level best of 70.26943459448498,
  so `grouped_best_not_better_than_row_level = true`.
- Grouped `bias_gt60`: `D0_delta_core` 70.74055320184931, `D1_delta_core_morgan` 76.65222626086577,
  `D2_delta_log` 48.31560765575515.
- The five rows are water 78.87 (XLYOFNOQVPJJNP-UHFFFAOYSA-N), formamide 106.14
  (ZHNUHDYFZUAESO-UHFFFAOYSA-N), N-methylacetamide 178.47 (OHLUUHNLEMFGTQ-UHFFFAOYSA-N),
  2-hydroxyethylammonium lactate 85.6 (NEQXUPRFDXNNTA-UHFFFAOYSA-N) and ethanolammonium nitrate 60.9
  (LZJIBRSVPKKOSI-UHFFFAOYSA-O).

## 5. Reproduction check

- `max_abs_difference = 0.0` and `reproduced_bit_for_bit = true` over the six compared keys
  (`mae`, `mae_assoc`, `mae_ionic`, `mae_gt60`, `r2`, `spearman`).
- Row-level reference: `probes/dielectric_onsager_delta_summary.json`, sha256
  `3acd499b2653135556bcdd61a1bdb2e8977973821f8b00f804e2431edef1754b`.
- Pre-registration: `probes/w19_onsager_grouped_prereg.json`, sha256
  `921ba092c6dfc8976d045c089caeeafb714da639f6c24634a97bd3f9284c6839`, `status = locked_before_run`,
  with one amendment registered before any run existed (`row_level_reproduction` added as the side-by-side
  baseline).
- Frozen inputs: `data/dielectric_v03.csv` sha256
  `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`, features
  `data/interim/v03_features_original.csv` sha256
  `da82f748daeccbc9c7c045aa2369085b147c2124693c62dc72994a4cb629f5f4`.

## 6. Limitations and honest boundary

Registered limitations, verbatim:

1. the pool holds 234 one-row-per-compound entries, so the plan request for GroupKFold-by-InChIKey cannot
   constrain anything on this pool;
2. the structure family is the only non-vacuous grouping key here and it is coarser than a compound split,
   so its reading is a lower bound;
3. 76 of 111 structure groups are singletons, so most rows see the same training pool they would see under
   a compound-level split;
4. the eps > 60 zone holds 5 rows, so its MAE is a point estimate with no meaningful interval;
5. Onsager is label-free and deterministic, so its zone coverage cannot change with the splitter; only the
   fitted arms move.

Registered honest boundary: `epsilon_lane_is_frozen = true`, `frozen_baseline = 0.4091179943351143`,
`frozen_headline = 0.4766400383507876`, `main_scoreboard_untouched = true`, `not_a_promotion_arm = true`.

## 7. What this does not do

- The grouped reading does not replace, amend or promote anything on the epsilon main scoreboard. The
  scoreboard still reads its frozen baseline and frozen headline, and its attempt count is still 11.
- Section 2.1 and section 2.2 are two different protocols on one pool. They are reported side by side and
  are never averaged, never compared as if one were the other, and never substituted for one another.
- No reading here changes the W18 cap conclusion, and no number here is a promotion candidate.

## 8. Artifacts

- `probes/w19_onsager_grouped.py`
- `probes/w19_onsager_grouped_prereg.json`
- `probes/w19_onsager_grouped_summary.json`
- `reports/w19_onsager_grouped.md` (this file)
- `tests/test_w19_onsager_grouped.py`
