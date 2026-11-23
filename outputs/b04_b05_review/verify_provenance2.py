# -*- coding: utf-8 -*-
"""Reviewer 2 part 2: resolve the true join key and test pair-level provenance."""
import csv, json, collections, os

OUT = r"E:\Claude Code\电解质ML\电解质ML\outputs"
def p(*a): return os.path.join(OUT, *a)
def rd(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

pool  = rd(p('b04','candidate_pool_v2_draft.csv'))
audit = rd(p('b04','candidate_exclusion_audit.csv'))
cons  = rd(p('admission_v2','consensus_decisions.csv'))
v06r  = rd(p('b01','dataset_v06_model_ready.csv'))
v06x  = rd(p('b01','dataset_v06_exclusions.csv'))
led   = rd(p('confirm_2027','provenance_repair','measurement_ledger_v1.csv'))
imp   = json.load(open(p('b01','temperature_imputation_audit.json'), encoding='utf-8'))

print("LEDGER COLUMNS:", list(led[0].keys()))
print("n ledger rows", len(led))
# does EPSV04 appear anywhere in ledger?
blob = set()
for r in led:
    for k,v in r.items():
        if v and 'EPSV04' in v: blob.add((r['measurement_id'], k, v))
print("rows mentioning EPSV04 anywhere in ledger:", len(blob), list(blob)[:5])

# aggregate coverage
led_agg = collections.defaultdict(list)
for r in led: led_agg[r['aggregate_id']].append(r)
print("\nn distinct aggregate_id in ledger:", len(led_agg))
print("sample aggregates:", sorted(led_agg)[:5], "...", sorted(led_agg)[-3:])

pool_aggs = {r['aggregate_id'] for r in pool}
print("pool aggregates present in ledger:", len(pool_aggs & set(led_agg)), "/", len(pool_aggs))
missing = sorted(pool_aggs - set(led_agg))
print("pool aggregates ABSENT from ledger:", missing)

# EPSV04-RNNN <-> v04row-NNN mapping check via consensus
cons_map = {r['measurement_id']: r.get('queue_id') for r in cons}
print("\nconsensus rows:", len(cons))
print("consensus column list:", list(cons[0].keys()))

print("\n=== A. pool row -> ledger via aggregate_id ===")
for r in pool:
    rows = led_agg.get(r['aggregate_id'], [])
    docs = sorted({x['source_document_id'] for x in rows})
    Tset = sorted({x['temperature_K'] for x in rows}, key=float)
    # exact pair match within the aggregate
    pair = [x for x in rows if x['temperature_K'] == r['T_K'] and abs(float(x['dielectric']) - float(r['dielectric'])) < 5e-4]
    doci = r['source_doi'] in docs
    flag = '' if (pair and doci) else '  <<<'
    print(f"{r['measurement_id']} {r['aggregate_id']} {r['name'][:34]:34s} eps={r['dielectric']:>7s} T={r['T_K']:>7s} "
          f"| ledger_obs={len(rows):2d} docs={len(docs)} doi_in_docs={doci} pair_matches={len(pair)}"
          f" ledger_T={Tset if len(Tset)<=6 else str(len(Tset))+'vals'}{flag}")
    if not doci:
        print(f"     !! pool source_doi {r['source_doi']} NOT among ledger docs {docs}")
    if not pair:
        near = [(x['temperature_K'], x['dielectric'], x['source_document_id']) for x in rows]
        print(f"     !! NO ledger observation holds (T={r['T_K']}, eps={r['dielectric']}); ledger rows: {near[:8]}")
    if len(docs) > 1:
        print(f"     !! multi-document aggregate: {docs}")

print("\n=== B. duplicate (inchikey,T,eps) collisions among pool? ===")
key = collections.Counter((r['inchikey'], r['T_K'], r['dielectric']) for r in pool)
print("duplicate fingerprints:", [k for k,c in key.items() if c>1])

print("\n=== C. same molecule, multiple records? ===")
ik = collections.Counter(r['inchikey'] for r in pool)
print("max records per inchikey:", max(ik.values()))

print("\n=== D. imputation audit vs v06 ready & exclusion audit ===")
imp_ids = {x['measurement_id'] for x in imp['imputed_rows']}
ready_ids = {r['measurement_id'] for r in v06r}
excl_ids  = {r['measurement_id'] for r in v06x}
print("n imputed", len(imp_ids))
print("imputed ∩ v06_ready :", len(imp_ids & ready_ids), sorted(imp_ids & ready_ids))
print("imputed ∩ v06_excl  :", len(imp_ids & excl_ids), sorted(imp_ids & excl_ids)[:30])
print("imputed ∩ pool      :", len(imp_ids & {r['measurement_id'] for r in pool}))
tk = [r['measurement_id'] for r in audit if 'TEMPERATURE_IMPUTED' in r['exclusion_reason']]
print("audit rows flagged TEMPERATURE_IMPUTED:", len(tk))
print("  those ids:", sorted(tk))
print("  equal to imputed set?", set(tk) == imp_ids, " overlap:", len(set(tk) & imp_ids))
print("  v06_model_ready of flagged rows:", collections.Counter(
    r['v06_model_ready'] for r in audit if 'TEMPERATURE_IMPUTED' in r['exclusion_reason']))
print("imputed_model_ready field in b01 audit:", imp['counts']['n_imputed_model_ready'])

print("\n=== E. any pool row carrying an imputed temperature_source? ===")
print(collections.Counter(r['temperature_source'] for r in pool))
# ledger temperature_source equivalent: is T the raw reported value? check pressure/frequency/phase
for r in pool:
    rows = led_agg.get(r['aggregate_id'], [])
    if not rows: continue
    ex = [x for x in rows if x['temperature_K'] == r['T_K']]
    if not ex:
        print(f"!! {r['measurement_id']} pool T={r['T_K']} not in ledger T set for aggregate")
    else:
        s = ex[0]
        print(f"   {r['measurement_id']:14s} band={s['temperature_band_v11']:24s} phase={s['phase']:8s} "
              f"press={s['pressure_kpa']:9s} freq={s['frequency_mhz']} trace={s['traceability_status']}")

print("\n=== F. E4 source_ood_results.csv ===")
sood = rd(p('b05','E4_domain_generalization','source_ood_results.csv'))
print("cols", list(sood[0].keys()), "rows", len(sood))
for r in sood: print("  ", r)

print("\n=== G. E4 applicability_domain.csv head ===")
ads = rd(p('b05','E4_domain_generalization','applicability_domain.csv'))
print("cols", list(ads[0].keys()))
for r in ads[:3]: print("  ", r)

print("\n=== H. E6 rank_vs_error ids vs pool ===")
pr = rd(p('b05','E6_screening_decisions','rank_vs_error.csv'))
s6 = {r['measurement_id'] for r in pr}
print("E6 ids == pool ids:", s6 == {r['measurement_id'] for r in pool})
print("E6 y_true vs pool dielectric mismatches:",
      [(r['measurement_id'], r['y_true']) for r in pr
       if abs(float(r['y_true']) - float({q['measurement_id']: q for q in pool}[r['measurement_id']]['dielectric'])) > 1e-6])

print("\n=== I. E1 predictions y_true vs pool ===")
pred = rd(p('b05','E1_structure_vs_electronic','predictions_loo.csv'))
pm = {q['measurement_id']: q for q in pool}
bad = [(r['measurement_id'], r['model'], r['y_true'], pm[r['measurement_id']]['dielectric']) for r in pred
       if abs(float(r['y_true']) - float(pm[r['measurement_id']]['dielectric'])) > 1e-6]
print("mismatch:", bad[:5], "count", len(bad))
print("n rows per model:", collections.Counter(r['model'] for r in pred))

print("\n=== J. b05 gate status / model_input_manifest ===")
print(open(p('b05','b05_gate_status.json'), encoding='utf-8').read())
print(open(p('b05','model_input_manifest.json'), encoding='utf-8').read()[:2500])
