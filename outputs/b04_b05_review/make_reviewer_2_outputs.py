# -*- coding: utf-8 -*-
"""Reviewer 2: emit decisions CSV + report. Writes only under outputs/b04_b05_review/."""
import csv, json, collections, os, hashlib

OUT = r"E:\Claude Code\电解质ML\电解质ML\outputs"
REV = os.path.join(OUT, 'b04_b05_review')
def p(*a): return os.path.join(OUT, *a)
def rd(x):
    with open(x, encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))

pool  = rd(p('b04','candidate_pool_v2_draft.csv'))
audit = rd(p('b04','candidate_exclusion_audit.csv'))
cons  = rd(p('admission_v2','consensus_decisions.csv'))
v06r  = rd(p('b01','dataset_v06_model_ready.csv'))
v06x  = rd(p('b01','dataset_v06_exclusions.csv'))
led   = rd(p('confirm_2027','provenance_repair','measurement_ledger_v1.csv'))
imp   = json.load(open(p('b01','temperature_imputation_audit.json'), encoding='utf-8'))
man   = json.load(open(p('b04','pool_lineage_manifest.json'), encoding='utf-8'))
ads   = {r['measurement_id']: r for r in rd(p('b05','E4_domain_generalization','applicability_domain.csv'))}
e1    = {r['measurement_id'] for r in rd(p('b05','E1_structure_vs_electronic','predictions_loo.csv'))}
e6    = {r['measurement_id'] for r in rd(p('b05','E6_screening_decisions','rank_vs_error.csv'))}
e4    = set(ads)

led_agg = collections.defaultdict(list)
for r in led: led_agg[r['aggregate_id']].append(r)

# ---------- per-row lineage table ----------
doc2 = collections.defaultdict(list)
for r in pool: doc2[r['source_doi']].append(r['measurement_id'])

rows = []
for r in pool:
    lr = led_agg[r['aggregate_id']]
    hit = [x for x in lr if x['temperature_K'] == r['T_K'] and x['dielectric'] == r['dielectric']]
    sibs = [q for q in doc2[r['source_doi']] if q != r['measurement_id']]
    rows.append({
        'measurement_id': r['measurement_id'],
        'name': r['name'],
        'doi': r['source_doi'],
        'T': r['T_K'],
        'eps': r['dielectric'],
        'msr': hit[0]['measurement_id'] if hit else 'NO_LITERAL_MATCH',
        'n_obs': len(lr),
        'n_docs': len({x['source_document_id'] for x in lr}),
        'doc_group': len(doc2[r['source_doi']]),
        'sib': ';'.join(sibs) if sibs else '-',
        'family': ads[r['measurement_id']]['family'],
        'in_ad': ads[r['measurement_id']]['in_applicability_domain'],
    })

# ---------- decisions ----------
D = []

D.append(dict(
 item='B04_candidate_pool', decision='HOLD', evidence_grade='DOCUMENTED',
 eligibility_verified='true', lineage_complete='false', shared_source_found='true',
 evidence_detail=(
  "ELIGIBILITY IS MECHANICALLY TRUE. Gate 1: 22/22 pool ids appear in admission_v2/consensus_decisions.csv with "
  "n_pass=4 and consensus_status=AI_CONSENSUS_ACCEPTED (R001,R004,R008,R009,R012,R013,R014,R018,R024,R026,R028,R032,"
  "R034,R045,R048,R051,R056,R061,R069,R076,R079,R092); the ACCEPTED set is exactly the pool (no accepted row omitted, "
  "no pool row rejected). Gate 2: 22/22 appear in b01/dataset_v06_model_ready.csv with model_ready=true, and "
  "|ACCEPTED INTERSECT v06_ready| = 22 = pool exactly. Pool-vs-v06 value drift = 0 (T_K, dielectric, inchikey, source_doi "
  "all agree). Exclusion audit is complete: 226 rows = 51 model-ready-not-in-pool (43 MODEL_READY_NOT_REVIEWED + 8 "
  "MODEL_READY_BUT_NOT_UNANIMOUS) + 175 excluded; pool INTERSECT audit = empty, 0 phantom rows, 0 uncovered v06 rows; "
  "v06_ready INTERSECT v06_excluded = 0. All six manifest SHA-256 hashes reproduce byte-exactly. "
  "LINEAGE FAILS AT THE DOCUMENTED KEY. The pool's measurement_id (EPSV04-RNNN) occurs 0/22 times in "
  "confirm_2027/provenance_repair/measurement_ledger_v1.csv; the string EPSV04 appears in none of the 2065 ledger rows, "
  "which re-key observations as MSR-<md5>. Rows resolve only through aggregate_id (v04row-NNN) - an undocumented "
  "positional convention (EPSV04-R%03d <-> v04row-%03d) which I verified bijective and strict for all 248 v06 rows. This "
  "is the same join-key class as the already-documented defect D1 in consensus_decisions r1/r2 evidence ('joins keyed by "
  "aggregate_id using measurement_id'). Joined that way, lineage is sound: 22/22 have exactly ONE literal (T,eps) ledger "
  "observation (e.g. R001->MSR-14b40e6eb1d7e983 at 300.15 K/5.878; R061->MSR-6ba9189a3260d756 at 293.15 K/6.15; "
  "R092->MSR-abfaa4fd948647cd at 303.15 K/24.69), 22/22 source_doi equals the ledger source_document_id (0 mismatches), "
  "all 22 aggregates are single-document, and no pool molecule has any other source document in the ledger. "
  "INDEPENDENCE: only 16 distinct DOIs cover 22 molecules. 9/22 share a source document - 10.1021/je600515j holds 5 "
  "molecules (R013,R018,R024,R048,R092), 10.1021/je300958c holds 2 (R012,R045), 10.1016/j.jct.2008.02.015 holds 2 "
  "(R032,R056). All 5 rows at the upper temperature boundary 303.15 K come from the single source 10.1021/je600515j, so "
  "temperature and source are perfectly aliased in the warm half of the pool. 7 rows are single-source aggregates of 2-5 "
  "observations (R004,R012,R014,R028,R045,R076,R079) with n_independent_experiments=1. "
  "SECONDARY: the manifest declares the pool is the intersection of 'three independent gates', but gate_3's pass set is "
  "identical to gate_2's (both 73; v06_ready and v06_excluded are disjoint by construction), so there are 2 effective "
  "gates and the third adds zero filtering. All 22 carry frozen_admission_verdict=BLOCKED_UNRESOLVED_GATE and "
  "admission_provenance=AI_CONSENSUS_NOT_HUMAN_SIGNED (no human sign-off). Inherited upstream defect: consensus_decisions "
  "has 72 rows but 64 unique ids (R031,R085,R086,R099 enrolled on 3 tracks each; R086 carries conflicting "
  "temperature_raw_K 295.65 vs 293.15) - none of these touch the pool. "
  "VERDICT: no fabricated or unverifiable row; hold only for (a) add an explicit ledger MSR crosswalk column so the pool "
  "is citable at the documented key, and (b) stop treating n=22 as 22 independent experiments (16 documents, 9 rows in "
  "shared-source groups).")))
D.append(dict(
 item='E1', decision='PASS', evidence_grade='DOCUMENTED',
 eligibility_verified='true', lineage_complete='true', shared_source_found='true',
 evidence_detail=(
  "SAME 22 MOLECULES AS B04. b05/E1_structure_vs_electronic/predictions_loo.csv contains 44 rows = 2 models x 22, and its "
  "unique measurement_id set is EXACTLY equal to candidate_pool_v2_draft.csv (set-equal, not just same size). y_true "
  "reproduces each pool row's dielectric with 0 mismatches across all 22, so no silent relabelling occurred. "
  "The result is uniformly negative and internally consistent: X0_structure_only MAE 17.4465 (R2 -1.8203, bias -16.7209), "
  "X0_plus_X1_electronic MAE 17.2867 (R2 -1.2881, bias -17.0095), both worse than the constant-baseline MAE 10.8062; "
  "permutation p = 0.164 and 0.060 over 500 permutations, neither beating the null at 0.05; delta_MAE(X1-X0) = -0.1599. "
  "The manifest correctly labels the run EXPLORATORY_NOT_CONFIRMATORY for n=22. "
  "PROVENANCE CAVEAT: the shared-source defect is inherited (9/22 rows have a same-document sibling molecule), and the "
  "declared leakage control - 'each molecule its own fold, preventing same-molecule leakage' - closes molecule-level but "
  "NOT document-level leakage, so cross-validated error may be optimistically biased by within-paper correlation "
  "(notably the 5-molecule 10.1021/je600515j block). This does not overturn the verdict: leakage inflates apparent skill, "
  "and here skill is absent or negative under the leaky scheme, so the negative conclusion is conservative and survives. "
  "E1 reports no source-level disclosure of its own (unlike E4's source_ood_results.csv note) - recommended addition.")))
D.append(dict(
 item='E4', decision='PASS', evidence_grade='DOCUMENTED',
 eligibility_verified='true', lineage_complete='true', shared_source_found='true',
 evidence_detail=(
  "SAME 22 MOLECULES AS B04. applicability_domain.csv and structural_distance_ood.csv are both set-equal to the 22 pool "
  "ids; family_counts sum to 22 (alcohol 3, carbonate 2, dinitrile 2, ketone 2, primary_secondary_amine 4, tertiary_amine "
  "1, carboxylic_acid 1, ester 1, ether 1, imidazole 1, unclassified 4). leave_one_family_out.csv reports MAE only where "
  "n_members >= min_test_n_rule = 2 (6 families, n_train 18-20) and marks the 5 singleton families insufficient_power "
  "with an explicit note - the estimation is not silently over-claimed. source_ood_results.csv sums n_molecules to 22 "
  "across the same 16 DOIs as the pool and every 'measured' row carries the disclaimer 'source independence not "
  "evaluated: B01 has shown DOI count != independent experiment count, therefore this row must not be used as cluster "
  "robustness evidence', with e4_manifest cannot_claim listing 'source cluster robustness'. This is the strongest "
  "provenance hygiene in the B05 package and it correctly refuses the claim that the shared-source defect would otherwise "
  "license. "
  "RESIDUAL CONFOUND (flag for the statistics reviewers, does not reverse this verdict): the carbonate family (2 "
  "molecules, both 10.1016/j.jct.2008.02.015) and the dinitrile family (2 molecules, both 10.1021/je300958c) are each "
  "entirely one source document, so their leave-one-family-out rows are simultaneously leave-one-source-out and the two "
  "effects are not separable; the only family beating its baseline (carbonate, MAE 15.4703 vs train-mean baseline 15.7646) "
  "is a 0.29 margin on n=2 from a single document, and E4 does not flag that specific confound. The headline conclusions "
  "(AD coverage 31.82%, out/in MAE ratio 1.045 = NO_USEFUL_SEPARATION, Spearman(error,distance) = -0.0494) are negative "
  "and descriptive, so they cannot be inflated by the shared-source defect.")))
D.append(dict(
 item='E6', decision='PASS', evidence_grade='DOCUMENTED',
 eligibility_verified='true', lineage_complete='true', shared_source_found='true',
 evidence_detail=(
  "SAME 22 MOLECULES AS B04. rank_vs_error.csv has 22 rows whose measurement_id set is EXACTLY the pool set, and y_true "
  "reproduces each pool dielectric with 0 mismatches. topk_regret.csv declares n_pool=22, k=3 = max(1, ceil(22/10)) fixed "
  "in advance (k_fixed_in_advance=true) with a predefined random_uniform_screening baseline - no post-hoc choice of k. "
  "The headline is negative and correctly labelled insufficient_power: model top-3 mean eps 24.45 vs oracle 37.83, regret "
  "13.38 = 65.22% of headroom, p_model_beats_random = 0.16 over 2000 permutations, top-3 overlap with oracle = 1/3. The "
  "oracle top-3 - sulfolane 44.0 (10.1016/j.tca.2012.10.004), 1-methylimidazole 39.78 (10.1016/j.fluid.2014.05.006), "
  "heptanedinitrile 29.71 (10.1021/je300958c) - spans 3 distinct source documents, so the screening target is not a "
  "single-paper artefact. "
  "The shared-source defect is inherited (16 DOIs / 22 molecules; 9 rows in shared-source groups) but it cannot "
  "manufacture a positive screening result: the model is already indistinguishable from random, so within-paper "
  "correlation cannot be what is suppressing the signal nor what would rescue it. The verdict stands. Note the H3 sub-claim "
  "(noise lowers regret, 13.380 -> 10.561, while MAE rises) is a single-pool descriptive artefact of a negative-signal "
  "model and should not be transported beyond this 22-molecule pool.")))
cols = ['item','decision','evidence_grade','eligibility_verified','lineage_complete',
        'shared_source_found','evidence_detail']
cp = os.path.join(REV, 'reviewer_2_decisions.csv')
with open(cp, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_ALL)
    w.writeheader()
    for d in D: w.writerow(d)
print("wrote", cp, "rows", len(D))

# ---------- report ----------
L = []
A = L.append
A("# Reviewer 2 — Source Literature, Provenance and Data Lineage")
A("")
A("**Project** electrolyte-solvent-dielectric-ml · work packages B04 + B05  ")
A("**Scope** provenance and lineage only. Statistical power, model choice and domain logic belong to the other reviewers.  ")
A("**Independence** this is one of four independent reviews; every number below was recomputed from the frozen artifacts, "
  "not taken from the project's own manifests (the manifests were checked *against* them).  ")
A("**Files modified** none. Scripts and outputs written only under `outputs/b04_b05_review/`.")
A("")
A("## Verdict summary")
A("")
A("| item | decision | evidence_grade | eligibility_verified | lineage_complete | shared_source_found |")
A("|---|---|---|---|---|---|")
for d in D:
    A(f"| {d['item']} | **{d['decision']}** | {d['evidence_grade']} | {d['eligibility_verified']} | "
      f"{d['lineage_complete']} | {d['shared_source_found']} |")
A("")
A("## 1. The six questions, answered mechanically")
A("")
A("### 1.1 Does every pool molecule trace back to a source? — YES in substance, NO at the documented key")
A("")
A("The pool's `measurement_id` column does **not** join to the ledger. `EPSV04-RNNN` occurs **0/22** times in "
  "`measurement_ledger_v1.csv`; the literal string `EPSV04` appears in **none of the 2065 ledger rows**. The ledger "
  "re-keys observations as `MSR-<md5>` hash ids and retains only `aggregate_id = v04row-NNN`.")
A("")
A("The documented join path is therefore broken, and the working join is an **undocumented positional convention** "
  "(`EPSV04-R%03d` <-> `v04row-%03d`). I verified that convention is strict and bijective across **all 248** v06 rows "
  "(248 unique measurement_ids, 248 unique aggregate_ids, zero exceptions), so it is reliable — but the pool file does "
  "not state it. This is the *same join-key defect class* already recorded as D1 in the `consensus_decisions.csv` "
  "reviewer evidence ('joins pv_rows keyed by aggregate_id using measurement_id').")
A("")
A("Joined through `aggregate_id`, lineage is clean and exact. **22/22** pool rows resolve to exactly one literal "
  "`(T, eps)` ledger observation — not a median, not a composite — and **22/22** `source_doi` values equal the ledger's "
  "`source_document_id` (**0 mismatches**). All 22 aggregates are single-document, and no pool molecule has any *other* "
  "source document anywhere in the ledger.")
A("")
A("| measurement_id | molecule | T_K | eps | ledger observation | DOI | obs in aggregate | docs | shared? |")
A("|---|---|---|---|---|---|---|---|---|")
for r in rows:
    share = f"**{r['doc_group']} mols** ({r['sib']})" if r['doc_group'] > 1 else "unique"
    A(f"| {r['measurement_id']} | {r['name']} | {r['T']} | {r['eps']} | `{r['msr']}` | {r['doi']} | {r['n_obs']} | "
      f"{r['n_docs']} | {share} |")
A("")
A("### 1.2 Is the eligibility claim true? — YES, exactly")
A("")
A("The manifest's intersection claim reproduces to the row:")
A("")
A("| gate | source | requirement | passing | pool members failing |")
A("|---|---|---|---|---|")
A("| 1 B02 four-agent | `admission_v2/consensus_decisions.csv` | `AI_CONSENSUS_ACCEPTED` (n_pass=4) | 22 | **0** |")
A("| 2 v06 model-ready | `b01/dataset_v06_model_ready.csv` | `model_ready = true` | 73 | **0** |")
A("| **intersection** | | | **22** | — |")
A("")
A("- The set of `AI_CONSENSUS_ACCEPTED` rows is **exactly** the pool: nothing accepted is omitted, nothing rejected is "
  "included (`n_pass=4` and `ACCEPTED` are in perfect 1:1 correspondence — no row has one without the other).")
A("- `pool INTERSECT excluded = 0` and `ACCEPTED INTERSECT excluded = 0`: no molecule is simultaneously in and out.")
A("- Pool values match v06 on every field (T_K, dielectric, inchikey, source_doi): **0 drift**.")
A("- All six SHA-256 digests declared in `pool_lineage_manifest.json` reproduce byte-exactly (3 inputs, 3 outputs), and "
  "every declared row count is correct (73 / 175 / 72 / 226).")
A("")
A("Two caveats on the *wording* of the claim, neither of which changes membership:")
A("")
A("1. **\"Three independent gates\" is an overstatement.** Gate 3's pass set (73) is *identical* to gate 2's pass set; "
  "`v06_ready` and `v06_excluded` are disjoint by construction, so gate 3 filters nothing beyond gate 2. There are "
  "**2 effective gates**, not 3. `candidate_pool_review.md` at least prints the honest number (73) in the gate-3 row.")
A("2. **No gate carries human sign-off.** All 22 rows have `frozen_admission_verdict = BLOCKED_UNRESOLVED_GATE` and "
  "`admission_provenance = AI_CONSENSUS_NOT_HUMAN_SIGNED`. This is disclosed, not hidden, but the pool is machine-admitted.")
A("")
A("### 1.3 Is the exclusion audit complete? — YES")
A("")
A("| quantity | expected | actual | result |")
A("|---|---|---|---|")
A("| 226 licensed (73 ready x 51 not-in-pool) | 51 | 51 (43 `MODEL_READY_NOT_REVIEWED` + 8 `MODEL_READY_BUT_NOT_UNANIMOUS`) | ok |")
A("| 175 excluded | 175 | 175 | ok |")
A("| audit rows | 226 | 226 (226 unique) | ok |")
A("| pool INTERSECT audit | 0 | 0 | ok |")
A("| v06 rows in neither pool nor audit | 0 | 0 | ok |")
A("| audit rows not in v06 ready/excluded | 0 | 0 | ok |")
A("| v06 ready INTERSECT v06 excluded | 0 | 0 | ok |")
A("")
A("`73 + 175 = 248`, `248 - 22 = 226`. No molecule is both in and out at any level.")
A("")
A("### 1.4 Are the 22 molecules independent? — **NO. 16 documents, not 22 experiments.**")
A("")
A("This is the substantive finding. **9 of the 22 pool molecules share a source document with another pool molecule.**")
A("")
A("| source DOI | molecules | measurement_ids |")
A("|---|---|---|")
A("| `10.1021/je600515j` | **5** | EPSV04-R013, R018, R024, R048, R092 |")
A("| `10.1021/je300958c` | **2** | EPSV04-R012, R045 |")
A("| `10.1016/j.jct.2008.02.015` | **2** | EPSV04-R032, R056 |")
A("")
A("**Effective independent source documents = 16** (not 22). The pool manifest's `n_distinct_molecules: 22` is "
  "molecule-level and correct; it is not a count of independent experiments, and the project's own finding that "
  "DOI count != independent experiment count (27 byte-identical duplicate groups) applies here.")
A("")
A("Additional independence facts:")
A("")
A("- **7 rows are single-source aggregates** of 2–5 observations with `n_independent_experiments = 1` "
  "(R004, R012, R014, R028, R045, R076, R079) — the pool value is a within-paper mean, not an independent replicate.")
A("- **Temperature is aliased with source.** All **5/5** rows at the upper boundary 303.15 K come from the single "
  "paper `10.1021/je600515j`; the sole 293.15 K row is `10.1016/j.jct.2012.08.009`; each of the 16 DOIs supplies exactly "
  "one distinct T value. T is a source property in this pool, so any temperature interpretation is a source "
  "interpretation.")
A("- **Two entire chemical families are single-source**: carbonate (R032, R056 — both `10.1016/j.jct.2008.02.015`) and "
  "dinitrile (R012, R045 — both `10.1021/je300958c`).")
A("- The duplicate-group cross-check is clean: `pool INTERSECT duplicate_observation_groups = 0`, so none of the 22 is "
  "*the same observation transcribed twice* — the sharing is same-document-different-molecule, a weaker but still real "
  "correlation.")
A("")
A("### 1.5 Do E1/E4/E6 use the same 22? — **YES, verified set-equal**")
A("")
A("| experiment | file | n | id set vs pool | y_true vs pool |")
A("|---|---|---|---|---|")
A("| E1 | `predictions_loo.csv` | 44 rows = 2 models x 22 | **set-equal** | 0 mismatches / 22 |")
A("| E4 | `applicability_domain.csv`, `structural_distance_ood.csv` | 22 | **set-equal** | n/a (AD table) |")
A("| E4 | `source_ood_results.csv` | n_molecules sums to 22 | 16 DOIs = pool's 16 DOIs | — |")
A("| E6 | `rank_vs_error.csv` | 22 | **set-equal** | 0 mismatches / 22 |")
A("")
A("E1 == E4 == E6 == pool, all four set-equal, not merely same-cardinality. E1 reports `n_samples=22` for both models, "
  "E4 `n_pool=22 / n_usable=22`, E6 `n_pool=22`. **Cross-experiment comparison is valid**; no sample drift.")
A("")
A("### 1.6 Is the temperature vocabulary honest? — **YES**")
A("")
A("| check | result |")
A("|---|---|")
A("| rows inside closed [293.15, 303.15] K | **22/22**, 0 outside |")
A("| rows exactly on a boundary (counted in) | 6 — R013/R018/R024/R048/R092 at 303.15, R061 at 293.15 |")
A("| `temperature_source` distribution | `reported` = 22, none imputed |")
A("| imputed rows inside the pool | **0** of the 22 imputed rows (EPSV04-R223…R248) |")
A("| raw values preserved un-coerced | 293.15, 298, 298.15, 298.2, 300.15, 303.15 — bare `298` (R051) kept as `298`, not rounded to 298.15 |")
A("")
A("The `temperature_vocabulary_mapping.json` claim is **true**. The imputation audit's 22 flagged rows are exactly the "
  "22 rows the exclusion audit labels `TEMPERATURE_IMPUTED` (set equality verified), all with `v06_model_ready=false`, "
  "and **none** reached the pool. The audit's `n_imputed_model_ready: 18` refers to the *superseded v04* flag — v06 "
  "closed that hole. This is a clean fix, not a residual risk.")
A("")
A("## 2. Findings by severity")
A("")
A("| # | finding | severity | affected |")
A("|---|---|---|---|")
A("| F1 | Pool `measurement_id` does not join to the ledger (0/22); lineage depends on an undocumented positional "
       "convention. Same defect class as documented D1. | **high (artifact integrity)** | B04 |")
A("| F2 | Only 16 source documents behind 22 molecules; 9/22 rows in shared-source groups; T perfectly aliased with "
       "source at 303.15 K. | **high (independence)** | B04, inherited by E1/E4/E6 |")
A("| F3 | \"Three independent gates\" is false — gate 3 == gate 2. | medium (documentation honesty) | B04 |")
A("| F4 | E1's stated leakage control ('each molecule its own fold') does not address document-level clustering. | "
       "medium (method disclosure) | E1 |")
A("| F5 | Carbonate and dinitrile families are single-source, so their leave-one-family-out rows are also "
       "leave-one-source-out; the only family beating baseline is 0.29 MAE on n=2 from one paper. | medium | E4 |")
A("| F6 | Upstream: `consensus_decisions.csv` has 72 rows / 64 unique ids (R031, R085, R086, R099 appear 3x each; R086 "
       "carries conflicting `temperature_raw_K` 295.65 vs 293.15). | low (does not touch pool) | inherited |")
A("| F7 | 7 pool rows are single-source aggregates with `n_independent_experiments=1`. | low (disclosed in-file) | B04 |")
A("| F8 | No human sign-off on any of the 22 (`AI_CONSENSUS_NOT_HUMAN_SIGNED`). | low (disclosed) | B04 |")
A("")
A("## 3. Why B04 is HOLD and not FAIL")
A("")
A("Nothing in the pool is fabricated, mis-sourced or unverifiable. Every row has a real, resolvable DOI, exactly one "
  "literal observation in the ledger holding both its T and its eps, a single-document source set, and a DOI that "
  "matches. The eligibility intersection is exact and the exclusion audit is airtight.")
A("")
A("It is held because the artifact **cannot be cited at the key it publishes**. A downstream reader joining "
  "`candidate_pool_v2_draft.measurement_id` to `measurement_ledger_v1.measurement_id` gets **zero matches** — and this "
  "project has already been burned once by exactly that join-key mistake (D1). Two specific remedies:")
A("")
A("1. Add an explicit `ledger_observation_id` (MSR-*) column, or document the `EPSV04-R%03d` <-> `v04row-%03d` "
  "convention in the manifest. All 22 values are known — see the table in §1.1.")
A("2. Replace the \"22 molecules / 22 independent sources\" framing with \"22 molecules drawn from 16 source documents\", "
  "and list the three shared-source groups. B07's planned cluster test depends on this being stated explicitly.")
A("")
A("## 4. Why E1, E4 and E6 pass despite the shared-source defect")
A("")
A("All three conclusions are **negative**, and shared-source correlation can only *inflate* apparent skill:")
A("")
A("- **E1** — both feature sets are worse than the constant baseline (MAE 17.45 / 17.29 vs 10.81) with negative R² and "
  "permutation p = 0.164 / 0.060. Leaky CV would make the model look *better*; it still loses. Negative result is "
  "conservative.")
A("- **E4** — the headline claims are descriptive negatives (AD coverage 31.82%, in/out MAE ratio 1.045 = "
  "`NO_USEFUL_SEPARATION`, Spearman(error, distance) = −0.0494), and the file **already refuses** the cluster-robustness "
  "claim in every source-OOD row and in `cannot_claim`. This is the best-handled provenance in the package.")
A("- **E6** — the model is statistically indistinguishable from random (p = 0.16, top-3 overlap 1/3), the oracle top-3 "
  "spans 3 distinct sources, and k = 3 was fixed before the run. Correlation cannot manufacture the absent signal.")
A("")
A("The one sub-claim I would not transport beyond this pool is E6's H3 reading (adding noise *lowers* regret while "
  "raising MAE). It is a valid observation on these 22 points, but on a negative-signal model it is an artifact of a flat "
  "prediction surface, not a general law about screening.")
A("")
A("## 5. Reproduction")
A("")
A("All checks are mechanical; scripts under `outputs/b04_b05_review/`:")
A("")
A("- `verify_provenance.py` — ledger trace, gate sets, audit arithmetic, source sharing, n consistency, temperature")
A("- `verify_provenance2.py` — join-key resolution by `aggregate_id`, imputation cross-check, B05 n audit")
A("- `verify_provenance3.py` — SHA-256 integrity, exact literal (T,eps) match, shared-DOI source nature")
A("- `verify_provenance4.py` — coverage arithmetic, family x source confounding, E1/E4/E6 id-set identity")
A("- `verify_provenance5.py` — consensus duplicate-row and gate-1 robustness audit")
A("- `verify_provenance6.py` — crosswalk bijection, gate redundancy, 303.15 K boundary cluster")
A("- `make_reviewer_2_outputs.py` — emits this report and `reviewer_2_decisions.csv`")
A("")
A("Run with `E:\\Claude Code\\电解质ML\\电解质ML\\.venv\\Scripts\\python.exe`; no existing file was written.")
A("")

rp = os.path.join(REV, 'reviewer_2_report.md')
with open(rp, 'w', encoding='utf-8', newline='\n') as f:
    f.write('\n'.join(L))
print("wrote", rp, "lines", len(L))
