# Reviewer 3 — Data Mapping / Identity / Code Correctness
## gamma-valerolactone (GAEKPEKOJKCEMS-UHFFFAOYSA-N): EPSV04-R227 (ε=36.1) vs EPSV04-R248 (ε=36.9)

Work package **B02-CONFLICT** · independent implementation audit · no files modified

---

## 1. Verdict

| queue_id | decision | grade | authoritative ε | value discrepancy | code defect |
|---|---|---|---|---|---|
| Q-CONF-EPSV04-R227 | **HOLD** | DOCUMENTED | **36.1** | **true** | **true** |
| Q-CONF-EPSV04-R248 | **HOLD** | DOCUMENTED | **36.9** | false | **true** |

**The conflict is real at the row level and correctly flagged. It is not resolvable to a single number, and the
"same temperature" that creates it is an artefact of imputation on both legs.** There is a genuine code defect, but
it is *not* the one the brief suspected: the corrupted column is `gap_aggregation_audit.v04_epsilon`, and the damage
is **three rows wide, not one**.

---

## 2. Table-by-table value trace

The chain has five carriers. For R227 they do **not** all agree.

| # | Table | Key | R227 ε | R248 ε | Status |
|---|---|---|---|---|---|
| 0 | `data/dielectric_v04.csv` (master) | file row / inchikey+doi | **36.1** | **36.9** | authoritative |
| 1 | `condition_pair_validity_v1.csv` | `v04row-227` / `-248` | **36.1** | **36.9** | correct |
| 2 | `gap_aggregation_audit.csv` → `gap_epsilon` | `EPSV04-R227` / `-248` | **36.1** | **36.9** | correct |
| 3 | `gap_aggregation_audit.csv` → `v04_epsilon` | `EPSV04-R227` / `-248` | **36.9** ❌ | 36.9 | **WRONG on R227** |
| 4 | `admission_review_queue.csv` → `dielectric_raw` | `Q-CONF-*` | **36.1** | **36.9** | correct (post-fix) |

Verification (numeric, all 248 rows):

```
pv.v04_dielectric  ==  dielectric_v04.dielectric     : 248/248  (0 mismatches)
gap.gap_epsilon    ==  pv.v04_dielectric             : 248/248  (0 mismatches)
gap.v04_epsilon    ==  pv.v04_dielectric             : 245/248  (3 MISMATCHES)
```

### Which column is authoritative
**`gap_epsilon`, `pv.v04_dielectric` and `dielectric_v04.dielectric` are the same number on every row. `v04_epsilon`
is the corrupted column.** Anyone consuming `v04_epsilon` picks the wrong value on R227 — exactly the failure the
brief asked me to look for. It is the *audit* table, not the *master* table, that lies.

---

## 3. Code defects (file:line)

### DEFECT 1 — skeleton-only join collapses a duplicated InChIKey (root cause, 3 rows wide)
**`scripts/confirm_2027/audit_gap_aggregation_provenance.py:523`**
```python
"v04_by_skeleton": {skeleton(r["inchikey"]): r for r in v04 if skeleton(r["inchikey"])},
```
with, at **lines 161–163**:
```python
def skeleton(inchikey: str) -> str:
    text = (inchikey or "").strip()
    return text.split("-")[0] if text else ""
```
and consumed at **line 550**:
```python
v04_row = dataset["v04_by_skeleton"].get(skeleton(molecule_id))
```

`dielectric_v04.csv` contains **248 rows but only 245 distinct skeletons**. A dict comprehension keyed on the
skeleton silently keeps only the **last** row per group. Every row in a duplicated group is then resolved against
that one surviving row.

Three groups are affected, and **all three produce a wrong `v04_epsilon`**:

| group | rows | correct ε | `v04_epsilon` emitted | corrupted? |
|---|---|---|---|---|
| `ZQDPJFUHLCOCRG` | R166 cis-3-hexene | 2.062 | **2** | yes |
| | R167 trans-3-hexene | 2.000 | 2 | (correct by luck) |
| `KFUSEUYYWQURPO` | R174 cis-1,2-DCE | 9.20 | **2.14** | yes |
| | R175 trans-1,2-DCE | 2.14 | 2.14 | (correct by luck) |
| `GAEKPEKOJKCEMS` | R227 GVL review-table | 36.1 | **36.9** | yes |
| | R248 GVL primary SI | 36.9 | 36.9 | (correct by luck) |

Note what this means: **the two cis/trans isomer pairs are also corrupted**, and they are corrupted *worse* than
GVL — R174 reports the cis value as the trans value (9.20 → 2.14). This was never noticed because those rows are
`COMPOSITE_CONDITION_UNMATCHED`, not `UNRESOLVED_SOURCE_CONFLICT`, so no one was reading their ε.

The corruption is **positional, not substantive**: `v04_epsilon` is right on exactly the rows that happen to be
last in their skeleton group. Reverse the file order and R248 would read 36.1 and R227 36.9. R248 is therefore
"correct by accident" and I grade its `code_defect_found` as **true** on that basis.

**Why the audit table cannot see this**: `gap_aggregation_audit` is *itself* the artefact that would have exposed
the bug, but it is keyed by `molecule_id` + skeleton lookup, so it silently reports the same row twice rather than
failing loudly. Nothing in the pipeline cross-checks `v04_epsilon` against `gap_epsilon`.

### DEFECT 2 — the queue fix is correct but incomplete: 3 sibling call sites still use the wrong column
**`scripts/b02/build_admission_review_queue.py`**

The `UNRESOLVED_SOURCE_CONFLICT` track was fixed at **lines 376–378**:
```python
"dielectric_raw": (
    pv.get("v04_dielectric")
    or gap.get("v04_epsilon", "")),
```
**This fix is correct and I verify it works** — the shipped queue now carries 36.1 / 36.9, and the comment at
lines 371–375 documents the reasoning accurately. `pv` is properly bridged (`v04row-NNN` → `EPSV04-RNNN`,
lines 141–155, with a WARN if the bridge count drops).

But **three other tracks still read the corrupted column**:
- **line 237** — `P0_P1_NAMED_MOLECULE`
- **line 279** — `COMPOSITE_CONDITION_UNMATCHED_22`
- **line 318** — `J02A_REQUIRES_HUMAN_REVIEW_4`

All three do `"dielectric_raw": gap.get("v04_epsilon", "")`. The same defect the fix addressed is live in three
other tracks.

**Current blast radius: zero shipped rows.** I checked — none of R166/R174/R227 is exposed by those three tracks
today, so no wrong number is on the page. It is a **latent** defect, not an active one. But it is one row of
roster drift away from surfacing, and it is the identical bug that was just fixed next door. The fix should have
been applied at the shared boundary (one helper), not patched at one call site.

### DEFECT 3 — `T_TOLERANCE_K` is declared, documented, exported, and never used
**`scripts/b01/build_source_conflict_register.py:44`**
```python
T_TOLERANCE_K = 0.5          # treat these as "the same temperature"
```
It is written into the JSON manifest (line 241) and into the Markdown report (line 336), and the published
rationale says *"温度容差 0.5 K 用于识别『同一条件』"*. But bucketing at **line 90** and **line 180** is:
```python
buckets[(mol, round(t, 1))].append(p)
```
`round(t,1)` is a **0.1 K bucket**, not a 0.5 K tolerance. The constant is decorative. The register therefore
advertises a tolerance it does not implement — the worst kind of documentation defect, because a reader trusts
the manifest instead of reading the code.

### DEFECT 4 — stale `in_review_queue` flag in the shipped register
`outputs/b01/source_conflict_register.csv` (mtime **13:17**) says `in_review_queue=false` for the GVL conflict.
The queue was rebuilt at **13:24** and both rows **are** in it (I verified). The register simply predates the
queue. Cosmetic, but it means the register's headline claim — *"the conflict is absent from the queue"* — is
currently false against the artefact it ships beside. **Re-run `build_source_conflict_register.py`.**

### DEFECT 5 — mislabelled chemistry in the provenance note
`data/processed/dielectric_v04_provenance_patches.csv` and the v04 `notes` call the 36.1 leg *"the beta lactone
value"*. The row's own SMILES `CC1CCC(=O)O1` is a **five-membered γ-lactone** (GVL), not a β-lactone. The
annotation contradicts the row's own structure. Harmless to the number, but it is exactly the kind of label that
misleads a future reviewer into thinking two *different compounds* were conflated.

---

## 4. Identity join — is the InChIKey safe?

**`GAEKPEKOJKCEMS-UHFFFAOYSA-N` is a genuine single compound, and the full key does NOT fold stereoisomers.**
RDKit verification:

| SMILES | InChIKey | note |
|---|---|---|
| `CC1CCC(=O)O1` | `GAEKPEKOJKCEMS-UHFFFAOYSA-N` | undefined stereo — **our rows** |
| `C[C@H]1CCC(=O)O1` | `GAEKPEKOJKCEMS-BYPYZUCNSA-N` | (S) |
| `C[C@@H]1CCC(=O)O1` | `GAEKPEKOJKCEMS-SCSAIBSYSA-N` | (R) |

The second block (`UHFFFAOYSA`) is the stereo/isotope layer. `UHFFFAOYSA` = **no stereo specified**, so the two
enantiomers have *different* full keys and the full key correctly does not merge them. GVL does have a stereocentre
at C5, and the dataset stores the stereo-unspecified skeleton — which is the right choice for a bulk-solvent
dielectric constant, since the racemate and either enantiomer have the same ε. **No identity defect here.**

**However**, the *first block alone* (`GAEKPEKOJKCEMS`) does fold the enantiomers, and **the pipeline joins on it in
at least 12 scripts**. Defect 1 is precisely an instance of this. The general pattern is a real hazard: it is safe
for GVL today only because no stereo-resolved GVL row exists. For the cis/trans pairs it has **already** produced
wrong numbers (§3, Defect 1). Any future enantiopure entry would silently collide.

---

## 5. Why zero contributing observations — ingestion path

**Confirmed: exactly 0 rows.** `measurement_ledger_v1.csv` has 2065 rows over 153 InChIKeys and **not one** is
`GAEKPEKOJKCEMS`. Corroborating: `data/processed/dielectric_observations_v11plus.csv` (2065 rows, 153 keys) also
has zero GVL rows, and the ledger is reconstructed from it.

**Ingestion path is manual curation, NOT ThermoML and NOT NBS.** Every one of the 2065 ledger rows has a
`source_file` under `data/raw/thermoml/`. GVL's legs both came in by hand:

- **36.1 (R227)** — `data/processed/modern_solvent_public_review_observations.csv`, `source_quality =
  open_access_review_table`, `dataset_origin = v0.3_addition`, Sun et al. 2026 iScience Table 3.
- **36.9 (R248)** — `data/processed/dielectric_v04_roster_additions.csv`, `dataset_origin = v0.4_addition`,
  `source_quality = primary`, Segato et al. 2021 Inorg. Chim. Acta SI. Traces upstream to
  `data/raw/reaxys_w17c/observations.csv` (Reaxys substance card, CAS 108-29-2, `value=36.9`, **`T_K` empty**),
  with the DOI resolved separately via Crossref.

Neither carries `source_file` / `source_file_sha256` / `source_row_index`, which is *why* the ledger — which
requires those fields — cannot admit them. **`NO_CONTRIBUTING_MEASUREMENTS` is a structural consequence of the
curation path, not evidence of a bad value.**

`gate_flags` and `source_mechanism` are **empty on both v04 rows**, so they carry no signal; the provenance lives in
`notes` / `temperature_source` / `dataset_origin`.

### The temperature is imputed on both legs
This is the most important finding for the adjudication:

| row | T_K | `temperature_source` |
|---|---|---|
| R227 (36.1) | 298.15 | `review_table_standard_room_temperature` |
| R248 (36.9) | 298.15 | **`not_reported`** |

The Reaxys source record for 36.9 has an **empty** `T_K`. 298.15 was **assigned**, not measured. On the other leg
the review table gives no temperature either; 298.15 was assigned as "standard room temperature". All 21 rows
tagged `review_table_standard_room_temperature` in v04 are pinned to exactly 298.15.

**So the "same temperature 298.15 K" that defines this conflict is an artefact of two independent imputations
landing on the same default.** The conflict is real as a *value* conflict but the "same condition" premise is not
documented by either source. Any resolution that assumes the two measurements were made at the same temperature is
resting on an assumption, not on data.

---

## 6. Is `condition_pair_valid=false` correct?

**Yes — correct, and it is not masking anything.** Verified directly from `condition_pair_validity_v1.csv`:

```
v04row-227: n_contributing_measurements=0, n_contributing_sources=0,
            condition_pair_valid=false, invalidity_reason=NO_CONTRIBUTING_MEASUREMENTS,
            median_temperature=not_evaluated, median_epsilon=not_evaluated
v04row-248: identical
```
Cross-checked in `gap_aggregation_audit.csv`: `verdict=PROVENANCE_INCOMPLETE`,
`verdict_reason=NO_BAND_OBSERVATIONS_FOUND`, `in_band_n_observations=0`,
`aggregation_documented=false`, `aggregation_rule=NOT_DOCUMENTED`, `single_source_lookup_possible=false`.

The reason string is the correct one: with no observations in the 293.15–303.15 K band there is no median to
validate, so pair validity cannot be established. It is **not** masking a different defect — the underlying defect
(no admissible observation at all) is exactly what the reason reports. The two rows are genuinely unvalidatable,
not mislabelled.

---

## 7. Are the conflict-register tolerances sound?

`outputs/b01/source_conflict_register.csv` **does** capture this conflict:
```
CONF-GAEKPEKOJKCEMS-298.1 | T=298.1 | eps 36.1;36.9 | spread=2.22% | 2 distinct sources | UNRESOLVED
```
But it captures it **by 0.22 percentage points of headroom.** 2.22% vs a 2.00% threshold. I tested the logic
directly:

| scenario | outcome |
|---|---|
| actual: 298.15 vs 298.15, 36.1/36.9 (2.22%) | **CAUGHT** |
| 298.15 vs **298.2** (ΔT = 0.05 K) | **MISSED** |
| 298.15 vs **298.25** (ΔT = 0.10 K) | **MISSED** |
| 298.15 vs 298.0 (ΔT = 0.15 K) | **MISSED** |
| 298.15 vs 298.65 (ΔT = 0.50 K, *at* the declared tolerance) | **MISSED** |
| spread 1.9% (36.10 vs 36.79) | **MISSED** |
| spread 2.0% (36.10 vs 36.82) | **MISSED** |
| spread 2.1% (36.10 vs 36.86) | **CAUGHT** |

**Two independent brittleness problems:**

**(a) The temperature bucketing is wrong, and it is the dangerous one.** `round(t,1)` buckets on a 0.1 K grid.
298.15 → **298.1** while 298.2 → **298.2**: two rows 0.05 K apart land in different buckets and are never compared.
This is not hypothetical — 298.15 vs 298.2 is *the* canonical way two papers disagree about "room temperature", and
it is precisely the case this register exists to find. The declared 0.5 K tolerance would have handled it; the
implemented 0.1 K grid does not. Worse, `round()` is a **boundary** function, so even two rows at the *same* 0.1 K
offset can split across a bucket edge (298.15→298.1 vs 298.25→298.2). **A tolerance must be implemented as
`|t1 − t2| ≤ tol` over candidate pairs, never as an equality on a rounded key.** Defect 3 and this are the same
root: the constant was never wired up.

**(b) The 2% ε tolerance is defensible but tight.** Empirically, of 108 v04 rows with a numeric uncertainty, the
median relative uncertainty is **0.95%** (max 21.3%). A 2% gate is ≈2× the median uncertainty, which is a
reasonable "beyond noise" line and I would not call it wrong. But it is a **fixed absolute** threshold applied to a
population whose uncertainty spans 0.017%–21.3%. A 2% disagreement between two high-precision (±0.05%) measurements
is a real conflict and would be **missed**; a 2% disagreement between two ±5% measurements is noise and is correctly
ignored. A fixed cut cannot do both. This is a design limitation, not a bug — and it is the *documented* choice
(`"两者都是本审计的选择, 不是冻结协议的一部分"`), so it is defensible. It is, however, silently lossy at the margin.

**Verdict on tolerances: the ε tolerance is defensible; the temperature logic is not — it is defective and
overstated in the manifest.**

---

## 8. Direct answers to the brief

1. **Value discrepancy?** **Yes, but only in `gap_aggregation_audit.v04_epsilon`** — it says 36.9 for R227 where
   everything else says 36.1. **A downstream consumer that read `v04_epsilon` would pick the wrong value**, and
   three queue tracks still do (§3, Defect 2). Authoritative column is `gap_epsilon` / `pv.v04_dielectric`.
2. **Identity join?** Full InChIKey is **safe** — `UHFFFAOYSA` is the undefined-stereo layer and RDKit gives the two
   enantiomers distinct keys. First-block-only joins **do** fold stereoisomers and are used in ≥12 scripts;
   that is the mechanism behind Defect 1 and it has already produced two wrong numbers (R166, R174).
3. **Zero observations?** Confirmed **0 rows** in the ledger and in `observations_v11plus`. Path is **manual
   curation** (review table + Reaxys→Crossref), **not** ThermoML/NBS. `gate_flags`/`source_mechanism` are empty;
   provenance is in `notes`/`temperature_source`.
4. **`condition_pair_valid=false` correct?** **Yes**, reason `NO_CONTRIBUTING_MEASUREMENTS` is right, and it is not
   masking another defect.
5. **Conflict-detection code?** Catches *this* case by 0.22 pp. **Would MISS** any spread ≤2% and **any** pair at
   298.15 vs 298.2 (0.05 K apart). `T_TOLERANCE_K=0.5` is dead code; `round(t,1)` is a 0.1 K equality, not a
   tolerance. ε tolerance defensible, temperature logic defective.
6. **Queue fix?** **Correct and verified working** — queue shows 36.1/36.9. But the **same defect survives in three
   other tracks** (lines 237, 279, 318). No wrong value is currently shipped; it is latent.

---

## 9. What I would change

1. **Fix the join properly**: key `v04_by_skeleton` on `(skeleton, source_doi)` or the full InChIKey + source, and
   make a duplicated skeleton a **hard error** rather than a silent overwrite. Same for every other
   `split("-")[0]` join (12 scripts).
2. **Route all four queue tracks through one `_dielectric_for(mid)` helper** that prefers `pv.v04_dielectric` and
   never touches `v04_epsilon`.
3. **Implement the temperature tolerance**: pairwise `|t1−t2| ≤ T_TOLERANCE_K`; delete `round(t,1)`.
4. **Regenerate `source_conflict_register.csv`** so `in_review_queue` is truthful.
5. **Fix the "beta lactone" label** to gamma-lactone.
6. **For the adjudication itself**: do not resolve on "same temperature", because 298.15 K is imputed on *both*
   legs and the 36.9 source has no recorded temperature at all. The honest disposition is **HOLD on both rows**
   until the Segato SI temperature is read from the SI itself, or the pair is recorded as a source-quality
   preference (primary 36.9 over review-table 36.1) rather than as a same-condition contradiction.

---

*Reviewer 3 · data-mapping / identity / code-correctness audit · all findings verified by executing
`E:\Claude Code\电解质ML\电解质ML\.venv\Scripts\python.exe` against the named artefacts. No file was modified
other than the two deliverables.*
