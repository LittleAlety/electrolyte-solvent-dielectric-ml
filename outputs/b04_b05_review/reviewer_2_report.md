# Reviewer 2 — Source Literature, Provenance and Data Lineage

**Project** electrolyte-solvent-dielectric-ml · work packages B04 + B05  
**Scope** provenance and lineage only. Statistical power, model choice and domain logic belong to the other reviewers.  
**Independence** this is one of four independent reviews; every number below was recomputed from the frozen artifacts, not taken from the project's own manifests (the manifests were checked *against* them).  
**Files modified** none. Scripts and outputs written only under `outputs/b04_b05_review/`.

## Verdict summary

| item | decision | evidence_grade | eligibility_verified | lineage_complete | shared_source_found |
|---|---|---|---|---|---|
| B04_candidate_pool | **HOLD** | DOCUMENTED | true | false | true |
| E1 | **PASS** | DOCUMENTED | true | true | true |
| E4 | **PASS** | DOCUMENTED | true | true | true |
| E6 | **PASS** | DOCUMENTED | true | true | true |

## 1. The six questions, answered mechanically

### 1.1 Does every pool molecule trace back to a source? — YES in substance, NO at the documented key

The pool's `measurement_id` column does **not** join to the ledger. `EPSV04-RNNN` occurs **0/22** times in `measurement_ledger_v1.csv`; the literal string `EPSV04` appears in **none of the 2065 ledger rows**. The ledger re-keys observations as `MSR-<md5>` hash ids and retains only `aggregate_id = v04row-NNN`.

The documented join path is therefore broken, and the working join is an **undocumented positional convention** (`EPSV04-R%03d` <-> `v04row-%03d`). I verified that convention is strict and bijective across **all 248** v06 rows (248 unique measurement_ids, 248 unique aggregate_ids, zero exceptions), so it is reliable — but the pool file does not state it. This is the *same join-key defect class* already recorded as D1 in the `consensus_decisions.csv` reviewer evidence ('joins pv_rows keyed by aggregate_id using measurement_id').

Joined through `aggregate_id`, lineage is clean and exact. **22/22** pool rows resolve to exactly one literal `(T, eps)` ledger observation — not a median, not a composite — and **22/22** `source_doi` values equal the ledger's `source_document_id` (**0 mismatches**). All 22 aggregates are single-document, and no pool molecule has any *other* source document anywhere in the ledger.

| measurement_id | molecule | T_K | eps | ledger observation | DOI | obs in aggregate | docs | shared? |
|---|---|---|---|---|---|---|---|---|
| EPSV04-R001 | N-methylaniline | 300.15 | 5.878 | `MSR-14b40e6eb1d7e983` | 10.1016/j.jct.2011.10.028 | 1 | 1 | unique |
| EPSV04-R004 | methyl propenoate | 298.15 | 7.021 | `MSR-78922b896508fb6f` | 10.1021/je301333b | 5 | 1 | unique |
| EPSV04-R008 | nonane | 298.15 | 1.98 | `MSR-3df31fcf897a283b` | 10.1016/j.jct.2008.09.006 | 1 | 1 | unique |
| EPSV04-R009 | 1,2-butanediol | 298.2 | 22.143 | `MSR-f7ce23fac5afba23` | 10.1016/j.jct.2011.07.021 | 1 | 1 | unique |
| EPSV04-R012 | octanedinitrile | 298.15 | 25.94 | `MSR-53be2b909855c3f6` | 10.1021/je300958c | 5 | 1 | **2 mols** (EPSV04-R045) |
| EPSV04-R013 | 2-amino-2-methylpropan-1-ol | 303.15 | 20.59 | `MSR-838b35348f0e0078` | 10.1021/je600515j | 1 | 1 | **5 mols** (EPSV04-R018;EPSV04-R024;EPSV04-R048;EPSV04-R092) |
| EPSV04-R014 | cycloheptanone | 298.15 | 12.92 | `MSR-cf33f1a64875f4e8` | 10.1021/je200682t | 5 | 1 | unique |
| EPSV04-R018 | 1,2-propanediol | 303.15 | 27.87 | `MSR-c6c8d8d8ffd6b20b` | 10.1021/je600515j | 1 | 1 | **5 mols** (EPSV04-R013;EPSV04-R024;EPSV04-R048;EPSV04-R092) |
| EPSV04-R024 | triethanolamine | 303.15 | 28.11 | `MSR-fdd965838ab62510` | 10.1021/je600515j | 1 | 1 | **5 mols** (EPSV04-R013;EPSV04-R018;EPSV04-R048;EPSV04-R092) |
| EPSV04-R026 | cyclohexanol | 298.15 | 15.71 | `MSR-ae9d3151cc2479c1` | 10.1021/acs.jced.8b00755 | 1 | 1 | unique |
| EPSV04-R028 | sulfolane | 298.15 | 44 | `MSR-2f91f71f3da1bd56` | 10.1016/j.tca.2012.10.004 | 3 | 1 | unique |
| EPSV04-R032 | dimethyl carbonate | 298.15 | 3.134 | `MSR-994f749db223ba9b` | 10.1016/j.jct.2008.02.015 | 1 | 1 | **2 mols** (EPSV04-R056) |
| EPSV04-R034 | heptane | 298.15 | 1.93 | `MSR-15d347e36169c56c` | 10.1016/j.jct.2010.09.008 | 1 | 1 | unique |
| EPSV04-R045 | heptanedinitrile | 298.15 | 29.71 | `MSR-879ddb7e040bbf6a` | 10.1021/je300958c | 5 | 1 | **2 mols** (EPSV04-R012) |
| EPSV04-R048 | N-(2-hydroxypropyl)-2-hydroxy-1-propanamine | 303.15 | 13.87 | `MSR-78bb90671e0e5cae` | 10.1021/je600515j | 1 | 1 | **5 mols** (EPSV04-R013;EPSV04-R018;EPSV04-R024;EPSV04-R092) |
| EPSV04-R051 | 1-methylimidazole | 298 | 39.78 | `MSR-6a84c1a0524e7b8b` | 10.1016/j.fluid.2014.05.006 | 1 | 1 | unique |
| EPSV04-R056 | diethyl carbonate | 298.15 | 2.834 | `MSR-9521cd05059ba2c6` | 10.1016/j.jct.2008.02.015 | 1 | 1 | **2 mols** (EPSV04-R032) |
| EPSV04-R061 | acetic acid | 293.15 | 6.15 | `MSR-6ba9189a3260d756` | 10.1016/j.jct.2012.08.009 | 1 | 1 | unique |
| EPSV04-R069 | methylcyclohexane | 298.2 | 2.01 | `MSR-7f22f77d1e5d57cc` | 10.1016/j.jct.2012.04.011 | 1 | 1 | unique |
| EPSV04-R076 | 1,4,7,10,13-pentaoxacyclopentadecane | 298.15 | 15.48 | `MSR-fd99ae74474ed182` | 10.1021/je300234g | 5 | 1 | unique |
| EPSV04-R079 | 2-acetylthiophene | 298.15 | 29.19 | `MSR-a8398138f033a8a8` | 10.1016/j.fluid.2016.10.026 | 5 | 1 | unique |
| EPSV04-R092 | diethanolamine | 303.15 | 24.69 | `MSR-abfaa4fd948647cd` | 10.1021/je600515j | 1 | 1 | **5 mols** (EPSV04-R013;EPSV04-R018;EPSV04-R024;EPSV04-R048) |

### 1.2 Is the eligibility claim true? — YES, exactly

The manifest's intersection claim reproduces to the row:

| gate | source | requirement | passing | pool members failing |
|---|---|---|---|---|
| 1 B02 four-agent | `admission_v2/consensus_decisions.csv` | `AI_CONSENSUS_ACCEPTED` (n_pass=4) | 22 | **0** |
| 2 v06 model-ready | `b01/dataset_v06_model_ready.csv` | `model_ready = true` | 73 | **0** |
| **intersection** | | | **22** | — |

- The set of `AI_CONSENSUS_ACCEPTED` rows is **exactly** the pool: nothing accepted is omitted, nothing rejected is included (`n_pass=4` and `ACCEPTED` are in perfect 1:1 correspondence — no row has one without the other).
- `pool INTERSECT excluded = 0` and `ACCEPTED INTERSECT excluded = 0`: no molecule is simultaneously in and out.
- Pool values match v06 on every field (T_K, dielectric, inchikey, source_doi): **0 drift**.
- All six SHA-256 digests declared in `pool_lineage_manifest.json` reproduce byte-exactly (3 inputs, 3 outputs), and every declared row count is correct (73 / 175 / 72 / 226).

Two caveats on the *wording* of the claim, neither of which changes membership:

1. **"Three independent gates" is an overstatement.** Gate 3's pass set (73) is *identical* to gate 2's pass set; `v06_ready` and `v06_excluded` are disjoint by construction, so gate 3 filters nothing beyond gate 2. There are **2 effective gates**, not 3. `candidate_pool_review.md` at least prints the honest number (73) in the gate-3 row.
2. **No gate carries human sign-off.** All 22 rows have `frozen_admission_verdict = BLOCKED_UNRESOLVED_GATE` and `admission_provenance = AI_CONSENSUS_NOT_HUMAN_SIGNED`. This is disclosed, not hidden, but the pool is machine-admitted.

### 1.3 Is the exclusion audit complete? — YES

| quantity | expected | actual | result |
|---|---|---|---|
| model-ready rows not in pool (73 − 22) | 51 | 51 (43 `MODEL_READY_NOT_REVIEWED` + 8 `MODEL_READY_BUT_NOT_UNANIMOUS`) | ok |
| 175 excluded | 175 | 175 | ok |
| audit rows | 226 | 226 (226 unique) | ok |
| pool INTERSECT audit | 0 | 0 | ok |
| v06 rows in neither pool nor audit | 0 | 0 | ok |
| audit rows not in v06 ready/excluded | 0 | 0 | ok |
| v06 ready INTERSECT v06 excluded | 0 | 0 | ok |

`73 + 175 = 248`, `248 - 22 = 226`. No molecule is both in and out at any level.

### 1.4 Are the 22 molecules independent? — **NO. 16 documents, not 22 experiments.**

This is the substantive finding. **9 of the 22 pool molecules share a source document with another pool molecule.**

| source DOI | molecules | measurement_ids |
|---|---|---|
| `10.1021/je600515j` | **5** | EPSV04-R013, R018, R024, R048, R092 |
| `10.1021/je300958c` | **2** | EPSV04-R012, R045 |
| `10.1016/j.jct.2008.02.015` | **2** | EPSV04-R032, R056 |

**Effective independent source documents = 16** (not 22). The pool manifest's `n_distinct_molecules: 22` is molecule-level and correct; it is not a count of independent experiments, and the project's own finding that DOI count != independent experiment count (27 byte-identical duplicate groups) applies here.

Additional independence facts:

- **7 rows are single-source aggregates** of 2–5 observations with `n_independent_experiments = 1` (R004, R012, R014, R028, R045, R076, R079) — the pool value is a within-paper mean, not an independent replicate.
- **Temperature is aliased with source.** All **5/5** rows at the upper boundary 303.15 K come from the single paper `10.1021/je600515j`; the sole 293.15 K row is `10.1016/j.jct.2012.08.009`; each of the 16 DOIs supplies exactly one distinct T value. T is a source property in this pool, so any temperature interpretation is a source interpretation.
- **Two entire chemical families are single-source**: carbonate (R032, R056 — both `10.1016/j.jct.2008.02.015`) and dinitrile (R012, R045 — both `10.1021/je300958c`).
- The duplicate-group cross-check is clean: `pool INTERSECT duplicate_observation_groups = 0`, so none of the 22 is *the same observation transcribed twice* — the sharing is same-document-different-molecule, a weaker but still real correlation.

### 1.5 Do E1/E4/E6 use the same 22? — **YES, verified set-equal**

| experiment | file | n | id set vs pool | y_true vs pool |
|---|---|---|---|---|
| E1 | `predictions_loo.csv` | 44 rows = 2 models x 22 | **set-equal** | 0 mismatches / 22 |
| E4 | `applicability_domain.csv`, `structural_distance_ood.csv` | 22 | **set-equal** | n/a (AD table) |
| E4 | `source_ood_results.csv` | n_molecules sums to 22 | 16 DOIs = pool's 16 DOIs | — |
| E6 | `rank_vs_error.csv` | 22 | **set-equal** | 0 mismatches / 22 |

E1 == E4 == E6 == pool, all four set-equal, not merely same-cardinality. E1 reports `n_samples=22` for both models, E4 `n_pool=22 / n_usable=22`, E6 `n_pool=22`. **Cross-experiment comparison is valid**; no sample drift.

### 1.6 Is the temperature vocabulary honest? — **YES**

| check | result |
|---|---|
| rows inside closed [293.15, 303.15] K | **22/22**, 0 outside |
| rows exactly on a boundary (counted in) | 6 — R013/R018/R024/R048/R092 at 303.15, R061 at 293.15 |
| `temperature_source` distribution | `reported` = 22, none imputed |
| imputed rows inside the pool | **0** of the 22 imputed rows (EPSV04-R223…R248) |
| raw values preserved un-coerced | 293.15, 298, 298.15, 298.2, 300.15, 303.15 — bare `298` (R051) kept as `298`, not rounded to 298.15 |

The `temperature_vocabulary_mapping.json` claim is **true**. The imputation audit's 22 flagged rows are exactly the 22 rows the exclusion audit labels `TEMPERATURE_IMPUTED` (set equality verified), all with `v06_model_ready=false`, and **none** reached the pool. The audit's `n_imputed_model_ready: 18` refers to the *superseded v04* flag — v06 closed that hole. This is a clean fix, not a residual risk.

## 2. Findings by severity

| # | finding | severity | affected |
|---|---|---|---|
| F1 | Pool `measurement_id` does not join to the ledger (0/22); lineage depends on an undocumented positional convention. Same defect class as documented D1. | **high (artifact integrity)** | B04 |
| F2 | Only 16 source documents behind 22 molecules; 9/22 rows in shared-source groups; T perfectly aliased with source at 303.15 K. | **high (independence)** | B04, inherited by E1/E4/E6 |
| F3 | "Three independent gates" is false — gate 3 == gate 2. | medium (documentation honesty) | B04 |
| F4 | E1's stated leakage control ('each molecule its own fold') does not address document-level clustering. | medium (method disclosure) | E1 |
| F5 | Carbonate and dinitrile families are single-source, so their leave-one-family-out rows are also leave-one-source-out; the only family beating baseline is 0.29 MAE on n=2 from one paper. | medium | E4 |
| F6 | Upstream: `consensus_decisions.csv` has 72 rows / 64 unique ids (R031, R085, R086, R099 appear 3x each; R086 carries conflicting `temperature_raw_K` 295.65 vs 293.15). | low (does not touch pool) | inherited |
| F7 | 7 pool rows are single-source aggregates with `n_independent_experiments=1`. | low (disclosed in-file) | B04 |
| F8 | No human sign-off on any of the 22 (`AI_CONSENSUS_NOT_HUMAN_SIGNED`). | low (disclosed) | B04 |

## 3. Why B04 is HOLD and not FAIL

Nothing in the pool is fabricated, mis-sourced or unverifiable. Every row has a real, resolvable DOI, exactly one literal observation in the ledger holding both its T and its eps, a single-document source set, and a DOI that matches. The eligibility intersection is exact and the exclusion audit is airtight.

It is held because the artifact **cannot be cited at the key it publishes**. A downstream reader joining `candidate_pool_v2_draft.measurement_id` to `measurement_ledger_v1.measurement_id` gets **zero matches** — and this project has already been burned once by exactly that join-key mistake (D1). Two specific remedies:

1. Add an explicit `ledger_observation_id` (MSR-*) column, or document the `EPSV04-R%03d` <-> `v04row-%03d` convention in the manifest. All 22 values are known — see the table in §1.1.
2. Replace the "22 molecules / 22 independent sources" framing with "22 molecules drawn from 16 source documents", and list the three shared-source groups. B07's planned cluster test depends on this being stated explicitly.

## 4. Why E1, E4 and E6 pass despite the shared-source defect

All three conclusions are **negative**, and shared-source correlation can only *inflate* apparent skill:

- **E1** — both feature sets are worse than the constant baseline (MAE 17.45 / 17.29 vs 10.81) with negative R² and permutation p = 0.164 / 0.060. Leaky CV would make the model look *better*; it still loses. Negative result is conservative.
- **E4** — the headline claims are descriptive negatives (AD coverage 31.82%, in/out MAE ratio 1.045 = `NO_USEFUL_SEPARATION`, Spearman(error, distance) = −0.0494), and the file **already refuses** the cluster-robustness claim in every source-OOD row and in `cannot_claim`. This is the best-handled provenance in the package.
- **E6** — the model is statistically indistinguishable from random (p = 0.16, top-3 overlap 1/3), the oracle top-3 spans 3 distinct sources, and k = 3 was fixed before the run. Correlation cannot manufacture the absent signal.

The one sub-claim I would not transport beyond this pool is E6's H3 reading (adding noise *lowers* regret while raising MAE). It is a valid observation on these 22 points, but on a negative-signal model it is an artifact of a flat prediction surface, not a general law about screening.

## 5. Reproduction

All checks are mechanical; scripts under `outputs/b04_b05_review/`:

- `verify_provenance.py` — ledger trace, gate sets, audit arithmetic, source sharing, n consistency, temperature
- `verify_provenance2.py` — join-key resolution by `aggregate_id`, imputation cross-check, B05 n audit
- `verify_provenance3.py` — SHA-256 integrity, exact literal (T,eps) match, shared-DOI source nature
- `verify_provenance4.py` — coverage arithmetic, family x source confounding, E1/E4/E6 id-set identity
- `verify_provenance5.py` — consensus duplicate-row and gate-1 robustness audit
- `verify_provenance6.py` — crosswalk bijection, gate redundancy, 303.15 K boundary cluster
- `make_reviewer_2_outputs.py` — emits this report and `reviewer_2_decisions.csv`

Run with `E:\Claude Code\电解质ML\电解质ML\.venv\Scripts\python.exe`; no existing file was written.
