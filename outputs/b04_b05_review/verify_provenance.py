# -*- coding: utf-8 -*-
"""Reviewer 2: provenance/lineage mechanical verification. Read-only on existing files."""
import csv, json, collections, os, io

OUT = r"E:\Claude Code\电解质ML\电解质ML\outputs"
def p(*a): return os.path.join(OUT, *a)

def rd(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

pool   = rd(p('b04', 'candidate_pool_v2_draft.csv'))
audit  = rd(p('b04', 'candidate_exclusion_audit.csv'))
cons   = rd(p('admission_v2', 'consensus_decisions.csv'))
v06r   = rd(p('b01', 'dataset_v06_model_ready.csv'))
v06x   = rd(p('b01', 'dataset_v06_exclusions.csv'))
ledger = rd(p('confirm_2027', 'provenance_repair', 'measurement_ledger_v1.csv'))
dupg   = rd(p('confirm_2027', 'provenance_repair', 'duplicate_observation_groups.csv'))
imp    = json.load(open(p('b01', 'temperature_imputation_audit.json'), encoding='utf-8'))

R = {}
def out(k, v):
    R.setdefault(k, []).append(v)
    print(f"[{k}] {v}")

print("=" * 78)
print("SIZES")
print("pool", len(pool), "audit", len(audit), "cons", len(cons),
      "v06_ready", len(v06r), "v06_excl", len(v06x), "ledger", len(ledger))
print("=" * 78)

pool_ids = [r['measurement_id'] for r in pool]
out('shape', f"pool rows={len(pool)}, unique measurement_id={len(set(pool_ids))}, "
             f"unique inchikey={len({r['inchikey'] for r in pool})}")

# ---------- 1. ledger traceability ----------
led_by_id = collections.defaultdict(list)
for r in ledger:
    led_by_id[r['measurement_id']].append(r)

print("\n--- 1. pool -> ledger trace ---")
missing_ledger, doi_mismatch, per_row = [], [], []
for r in pool:
    mid, doi = r['measurement_id'], r['source_doi']
    rows = led_by_id.get(mid)
    if not rows:
        # try aggregate-based fallback lookup
        missing_ledger.append(mid)
        out('ledger_missing', f"{mid} {r['name']} NOT FOUND in measurement_ledger_v1.csv")
        continue
    l = rows[0]
    docs = [x['source_document_id'] for x in rows]
    ok = doi in docs
    per_row.append((mid, doi, docs, ok))
    if not ok:
        doi_mismatch.append((mid, doi, docs))
        out('doi_mismatch', f"{mid} {r['name']}: pool DOI {doi} != ledger doc(s) {docs}")
print(f"pool ids present in ledger: {len(per_row)}/{len(pool)}; DOI mismatches: {len(doi_mismatch)}")
out('ledger', f"n_pool_ids_in_ledger={len(per_row)}/{len(pool)}; n_doi_mismatch={len(doi_mismatch)}")

# ledger observation count behind each pool row (is source_doi the FULL source set?)
print("\n--- 1b. is pool source_doi the COMPLETE source set for that aggregate? ---")
agg_ledger_docs = collections.defaultdict(set)
agg_ledger_n = collections.defaultdict(int)
for r in ledger:
    agg_ledger_docs[r['aggregate_id']].add(r['source_document_id'])
    agg_ledger_n[r['aggregate_id']] += 1
hidden = []
for r in pool:
    docs = agg_ledger_docs.get(r['aggregate_id'], set())
    if docs and r['source_doi'] not in docs:
        out('hidden_source', f"{r['measurement_id']} {r['name']}: pool DOI {r['source_doi']} "
                             f"NOT in ledger aggregate docs {sorted(docs)}")
    if len(docs) > 1:
        hidden.append((r['measurement_id'], r['name'], r['source_doi'],
                       sorted(docs), agg_ledger_n[r['aggregate_id']],
                       r['n_contributing_measurements'], r['n_independent_experiments']))
for h in hidden:
    out('multi_source', f"{h[0]} {h[1]}: pool DOI={h[2]} but aggregate has {h[3]} ({h[4]} obs); "
                        f"pool n_contrib={h[5]} n_indep_exp={h[6]}")
print(f"pool rows whose aggregate carries >1 source document: {len(hidden)}")

# ---------- 2. eligibility gates ----------
print("\n--- 2. gate 1: consensus AI_CONSENSUS_ACCEPTED ---")
cons_by_id = collections.defaultdict(list)
for r in cons:
    cons_by_id[r['measurement_id']].append(r)
gate1_fail = []
for mid in pool_ids:
    rows = cons_by_id.get(mid, [])
    if not rows:
        gate1_fail.append((mid, 'ABSENT_FROM_CONSENSUS', None, None))
        continue
    st = rows[0]['consensus_status']
    np_ = rows[0]['n_pass']
    if st != 'AI_CONSENSUS_ACCEPTED' or np_ != '4':
        gate1_fail.append((mid, st, np_, rows[0]['consensus_reason']))
for g in gate1_fail:
    out('gate1', f"{g[0]}: status={g[1]} n_pass={g[2]} reason={g[3]}")
print(f"GATE1: {len(pool_ids)-len(gate1_fail)}/{len(pool_ids)} pass")

print("\n--- 2b. union test: does gate1 alone yield exactly the pool? ---")
cons_acc = {r['measurement_id'] for r in cons if r['consensus_status'] == 'AI_CONSENSUS_ACCEPTED'
            and r['n_pass'] == '4'}
out('gate1_set', f"consensus 4/4 ACCEPTED ids={len(cons_acc)}; pool={len(set(pool_ids))}; "
                 f"accepted_not_in_pool={sorted(cons_acc - set(pool_ids))}; "
                 f"pool_not_accepted={sorted(set(pool_ids) - cons_acc)}")
print(sorted(cons_acc - set(pool_ids)), sorted(set(pool_ids) - cons_acc))

print("\n--- 2c. gate 2: v06 model_ready ---")
mready = {r['measurement_id']: r for r in v06r}
gate2_fail = [mid for mid in pool_ids if mid not in mready]
print(f"GATE2: {len(pool_ids)-len(gate2_fail)}/{len(pool_ids)} present in dataset_v06_model_ready.csv")
for m in gate2_fail:
    out('gate2', f"{m} ABSENT from dataset_v06_model_ready.csv")
# also check model_ready flag true
notready = [mid for mid in pool_ids if mid in mready and mready[mid].get('model_ready') != 'true']
out('gate2', f"n_absent={len(gate2_fail)}, n_model_ready_false={len(notready)}")
# value consistency between pool and v06
incons = []
for r in pool:
    m = mready.get(r['measurement_id'])
    if not m: continue
    if m['T_K'] != r['T_K'] or m['dielectric'] != r['dielectric'] or m['inchikey'] != r['inchikey']:
        incons.append((r['measurement_id'], r['T_K'], m['T_K'], r['dielectric'], m['dielectric']))
    if m['source_doi'] != r['source_doi']:
        incons.append((r['measurement_id'], 'DOI', r['source_doi'], m['source_doi']))
for i in incons:
    out('value_drift', f"pool/v06 disagree {i}")
print(f"pool vs v06 value disagreements: {len(incons)}")

# intersection test
ready_ids = set(mready)
out('intersection', f"|cons4/4 ∩ v06ready| = {len(cons_acc & ready_ids)}; pool={len(set(pool_ids))}; "
                    f"in_intersection_not_pool={sorted((cons_acc & ready_ids) - set(pool_ids))}")

# ---------- 3. exclusion audit completeness ----------
print("\n--- 3. exclusion audit completeness ---")
pool_s, audit_s = set(pool_ids), {r['measurement_id'] for r in audit}
ready_s, excl_s = set(mready), {r['measurement_id'] for r in v06x}
print("audit rows", len(audit), "unique", len(audit_s))
print("v06 ready", len(ready_s), "v06 excl", len(excl_s), "ready|excl", len(ready_s | excl_s))
print("ready & excl overlap:", sorted(ready_s & excl_s))
out('audit_union', f"|ready ∪ excl|={len(ready_s|excl_s)} (declared 248); "
                   f"overlap_ready_excl={len(ready_s & excl_s)}={sorted(ready_s & excl_s)}")
out('audit_counts', f"ready={len(ready_s)} excl={len(excl_s)} total={len(ready_s|excl_s)} "
                    f"pool={len(pool_s)} expected_audit={len(ready_s|excl_s)-len(pool_s)} "
                    f"actual_audit={len(audit_s)}")
out('audit_overlap', f"pool ∩ audit = {sorted(pool_s & audit_s)}")
not_covered = (ready_s | excl_s) - pool_s - audit_s
phantom = audit_s - (ready_s | excl_s)
out('audit_gap', f"v06 rows neither in pool nor in audit: {sorted(not_covered)}")
out('audit_phantom', f"audit rows not in v06 ready/excl: {sorted(phantom)}")
# breakdown
reason = collections.Counter(r['exclusion_reason'] for r in audit)
print("\naudit reason breakdown:")
for k, v in reason.most_common(): print(f"  {v:4d}  {k}")
ready_reason = collections.Counter(r['exclusion_reason'] for r in audit if r['v06_model_ready'] == 'true')
excl_reason = collections.Counter(r['exclusion_reason'] for r in audit if r['v06_model_ready'] != 'true')
print("  of which v06_model_ready=true:", sum(ready_reason.values()), dict(ready_reason))
print("  of which v06_model_ready!=true:", sum(excl_reason.values()), dict(excl_reason))
out('audit_reason', f"ready-not-in-pool audited={sum(ready_reason.values())} (expect 51); "
                    f"excluded audited={sum(excl_reason.values())} (expect 175)")
# pool molecules in audit by inchikey but different measurement_id?
audit_ik = {r['inchikey'] for r in audit}
shared_ik = [r['inchikey'] for r in pool if r['inchikey'] in audit_ik]
out('audit_ik', f"pool InChIKeys also appearing in exclusion audit: {len(shared_ik)} {shared_ik}")

# ---------- 4. source independence among the 22 ----------
print("\n--- 4. source-document independence of the 22 ---")
doc2pool = collections.defaultdict(list)
for r in pool:
    doc2pool[r['source_doi']].append((r['measurement_id'], r['name']))
dupe = {d: v for d, v in doc2pool.items() if len(v) > 1}
out('src_shared', f"n_distinct_source_doi={len(doc2pool)} of 22 rows; "
                  f"n_doi_shared_by>1_pool_row={len(dupe)}")
for d, v in sorted(dupe.items(), key=lambda x: -len(x[1])):
    out('src_shared_detail', f"{d} -> {len(v)} pool rows: " + "; ".join(f"{a}({b})" for a, b in v))
n_eff = len(doc2pool)
out('src_shared_summary', f"effective independent source documents = {n_eff} < 22; "
                          f"rows involved in sharing = {sum(len(v) for v in dupe.values())}")

# also: full ledger aggregate doc sets — union of underlying docs
agg2docs = collections.defaultdict(set)
for r in ledger:
    agg2docs[r['aggregate_id']].add(r['source_document_id'])
all_docs = set()
for r in pool:
    all_docs |= agg2docs.get(r['aggregate_id'], {r['source_doi']})
out('src_full', f"union of all ledger source documents behind the 22 aggregates = {len(all_docs)}")

# duplicate observation groups touching pool molecules
pool_ik = {r['inchikey'] for r in pool}
dg_hits = [r for r in dupg if r['inchikey'] in pool_ik]
out('dupgroups', f"duplicate_observation_groups rows whose InChIKey is a pool molecule: {len(dg_hits)}")
for r in dg_hits:
    out('dupgroups_detail', f"{r['inchikey']} T={r['temperature_K']} eps={r['dielectric']} "
                            f"n_obs={r['n_observations']} docs={r['documents']} ({r['interpretation']})")
# pool molecules that have >1 ledger observation (i.e., n_contributing > 1)
print("\npool rows with n_contributing_measurements > 1 (aggregate of multiple obs):")
for r in pool:
    if int(r['n_contributing_measurements']) > 1:
        out('multi_obs', f"{r['measurement_id']} {r['name']} n_contrib={r['n_contributing_measurements']} "
                         f"n_indep={r['n_independent_experiments']} agg={r['aggregate_id']} "
                         f"docs={sorted(agg2docs.get(r['aggregate_id'], []))}")

# ---------- 5. E1/E4/E6 same n? ----------
print("\n--- 5. E1/E4/E6 n consistency ---")
m1 = json.load(open(p('b05', 'E1_structure_vs_electronic', 'e1_manifest.json'), encoding='utf-8'))
m4 = json.load(open(p('b05', 'E4_domain_generalization', 'e4_manifest.json'), encoding='utf-8'))
m6 = json.load(open(p('b05', 'E6_screening_decisions', 'e6_manifest.json'), encoding='utf-8'))
ns = {
    'E1': (m1['coverage']['n_pool'], m1['coverage']['n_with_x0_x1'], m1['coverage']['n_comparable'],
           [x['n_samples'] for x in m1['metrics']]),
    'E4': (m4['coverage']['n_pool'], m4['coverage']['n_usable'], m4['coverage']['n_usable'], None),
    'E6': (22, None, None, None),
}
for k, v in ns.items():
    out('n', f"{k}: {v}")
# E6 has no explicit n -> infer from outputs
r6 = rd(p('b05', 'E6_screening_decisions', 'topk_regret.csv'))
pr6 = rd(p('b05', 'E6_screening_decisions', 'rank_vs_error.csv'))
pv6 = rd(p('b05', 'E6_screening_decisions', 'screening_reliability.csv'))
print("E6 topk_regret cols", list(r6[0].keys()), "rows", len(r6))
print("E6 rank_vs_error cols", list(pr6[0].keys()), "rows", len(pr6))
print("E6 screening_reliability cols", list(pv6[0].keys()), "rows", len(pv6))
ads = rd(p('b05', 'E4_domain_generalization', 'applicability_domain.csv'))
lofo = rd(p('b05', 'E4_domain_generalization', 'leave_one_family_out.csv'))
sood = rd(p('b05', 'E4_domain_generalization', 'source_ood_results.csv'))
sdist = rd(p('b05', 'E4_domain_generalization', 'structural_distance_ood.csv'))
pred = rd(p('b05', 'E1_structure_vs_electronic', 'predictions_loo.csv'))
print("E4 applicability_domain rows", len(ads), "| lofo rows", len(lofo), "| source_ood rows", len(sood),
      "| structural_distance_ood rows", len(sdist))
print("E1 predictions_loo rows", len(pred), "cols", list(pred[0].keys()))

def idcol(rows, cands):
    for c in cands:
        if c in rows[0]: return c
    return None
e1id = idcol(pred, ['measurement_id', 'molecule_id', 'id'])
e6id = idcol(pr6, ['measurement_id', 'molecule_id', 'id'])
e4id = idcol(ads, ['measurement_id', 'molecule_id', 'id'])
print("id columns:", e1id, e6id, e4id)
if e1id:
    s1 = {r[e1id] for r in pred}
    out('n_e1', f"E1 predictions unique ids={len(s1)}")
else:
    s1 = None
if e6id:
    s6 = {r[e6id] for r in pr6}
    out('n_e6', f"E6 rank_vs_error unique ids={len(s6)} (rows={len(pr6)})")
else:
    s6 = None
if e4id:
    s4 = {r[e4id] for r in ads}
    out('n_e4', f"E4 applicability_domain unique ids={len(s4)}")
else:
    s4 = None
if s1 and s6:
    out('n_same', f"E1 vs E6 id sets equal={s1 == s6}; only_E1={sorted(s1-s6)[:5]} only_E6={sorted(s6-s1)[:5]}")
if s1 and s4:
    out('n_same', f"E1 vs E4 id sets equal={s1 == s4}; only_E1={sorted(s1-s4)[:5]} only_E4={sorted(s4-s1)[:5]}")
# 22 or something else?
print("\nE1 prediction ids sample:", sorted(s1)[:3] if s1 else None)
print("pool ids sample:", sorted(pool_ids)[:3])

# ---------- 6. temperature honesty ----------
print("\n--- 6. temperature vocabulary ---")
vals = collections.Counter(r['T_K'] for r in pool)
out('temp', f"raw T_K vocabulary in pool: {dict(vals)}")
ts = collections.Counter(r['temperature_source'] for r in pool)
out('temp', f"temperature_source in pool: {dict(ts)}")
bad = [r for r in pool if not (293.15 <= float(r['T_K']) <= 303.15)]
out('temp_interval', f"rows outside closed [293.15,303.15]: {len(bad)} {[(r['measurement_id'], r['T_K']) for r in bad]}")
# boundary check
edge = [(r['measurement_id'], r['T_K']) for r in pool if float(r['T_K']) in (293.15, 303.15)]
out('temp_interval', f"rows exactly on boundary: {edge}")
# imputed rows
imp_ids = {x['measurement_id'] for x in imp['imputed_rows']}
imp_in_pool = imp_ids & set(pool_ids)
out('imputed', f"n_imputed overall={imp['counts']['n_imputed']} (model_ready {imp['counts']['n_imputed_model_ready']}); "
               f"imputed rows inside pool = {len(imp_in_pool)} {sorted(imp_in_pool)}")
# ledger temperature_band_v11 for pool rows: is T actually reported at that value?
print("\npool row T vs ledger T:")
for r in pool:
    rows = led_by_id.get(r['measurement_id'], [])
    if not rows: continue
    led_T = {x['temperature_K'] for x in rows}
    if r['T_K'] not in led_T:
        out('temp_vs_ledger', f"{r['measurement_id']} pool T={r['T_K']} but ledger T(s)={sorted(led_T)}")
    band = {x['temperature_band_v11'] for x in rows}
    print(f"  {r['measurement_id']:14s} pool_T={r['T_K']:7s} ledger_T={sorted(led_T)} band={band} src={r['temperature_source']}")

# 298 vs 298.15
weird = [(r['measurement_id'], r['T_K']) for r in pool if r['T_K'] == '298']
out('temp_vocab', f"rows with bare 298 K (not 298.15): {weird}")

# ---------- aggregate automatic verdicts ----------
print("\n" + "=" * 78)
print("SUMMARY")
print("=" * 78)
for k, v in R.items():
    if k.startswith(('gate1','gate2','ledger_missing','doi_mismatch','audit_gap','audit_phantom','n_same','temp_vs_ledger')):
        for x in v: print(f"  {k}: {x}")
