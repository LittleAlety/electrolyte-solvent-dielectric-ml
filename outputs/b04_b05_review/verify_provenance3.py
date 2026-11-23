# -*- coding: utf-8 -*-
"""Reviewer 2 part 3: hash integrity, exact pair match, source nature, temperature_source."""
import csv, json, collections, os, hashlib

OUT = r"E:\Claude Code\电解质ML\电解质ML\outputs"
ROOT = r"E:\Claude Code\电解质ML\电解质ML"
def p(*a): return os.path.join(OUT, *a)
def rd(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))
def sha(path):
    h = hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda: f.read(1<<20), b''): h.update(b)
    return h.hexdigest()

pool = rd(p('b04','candidate_pool_v2_draft.csv'))
v06r = rd(p('b01','dataset_v06_model_ready.csv'))
led  = rd(p('confirm_2027','provenance_repair','measurement_ledger_v1.csv'))
dupg = rd(p('confirm_2027','provenance_repair','duplicate_observation_groups.csv'))
cons = rd(p('admission_v2','consensus_decisions.csv'))
audit= rd(p('b04','candidate_exclusion_audit.csv'))

print("=== 1. MANIFEST HASH INTEGRITY ===")
man = json.load(open(p('b04','pool_lineage_manifest.json'), encoding='utf-8'))
targets = []
for k,v in man['inputs'].items():
    targets.append(('input:'+k, os.path.join(OUT, v.get('path','') if 'path' in v else ''), v['sha256']))
fmap = {'dataset_v06_model_ready': p('b01','dataset_v06_model_ready.csv'),
        'dataset_v06_exclusions': p('b01','dataset_v06_exclusions.csv'),
        'consensus_decisions': p('admission_v2','consensus_decisions.csv')}
for k,v in man['inputs'].items():
    fp = fmap[k]
    act = sha(fp)
    print(f"  input {k:32s} declared={v['sha256'][:16]} actual={act[:16]} MATCH={act==v['sha256'].lower()}")
for k,v in man['outputs'].items():
    fp = os.path.join(ROOT, v['path'])
    act = sha(fp)
    print(f"  output {k:32s} declared={v['sha256'][:16]} actual={act[:16]} MATCH={act==v['sha256'].lower()} exists={os.path.exists(fp)}")
print("  declared counts: ready=73 actual", len(v06r), "| excl declared 175 actual", len(rd(p('b01','dataset_v06_exclusions.csv'))),
      "| cons declared 72 actual", len(cons), "| audit rows declared 226 actual", len(audit))

print("\n=== 2. EXACT (T,eps) pair match against ledger observation ===")
led_agg = collections.defaultdict(list)
for r in led: led_agg[r['aggregate_id']].append(r)
exact = 0
for r in pool:
    rows = led_agg[r['aggregate_id']]
    hits = [x for x in rows if x['temperature_K']==r['T_K'] and x['dielectric']==r['dielectric']]
    exact += 1 if hits else 0
    print(f"  {r['measurement_id']:14s} eps={r['dielectric']:>7s} T={r['T_K']:>7s} "
          f"literal_hits={len(hits)}  ids={[x['measurement_id'] for x in hits]}")
print(f"  -> exact literal (T,eps) observation exists for {exact}/22 pool rows")

print("\n=== 3. temperature_source: pool vs v06 ===")
v6 = {r['measurement_id']: r for r in v06r}
diff = [(r['measurement_id'], r['temperature_source'], v6[r['measurement_id']]['temperature_source'])
        for r in pool if r['temperature_source'] != v6[r['measurement_id']]['temperature_source']]
print("  mismatches:", diff)
print("  v06 temperature_source distribution for pool rows:",
      collections.Counter(v6[r['measurement_id']]['temperature_source'] for r in pool))
print("  pool source_quality distribution:", collections.Counter(r['source_quality'] for r in pool))
print("  v06 source_quality distribution for pool rows:",
      collections.Counter(v6[r['measurement_id']]['source_quality'] for r in pool))

print("\n=== 4. shared-DOI source nature (3 DOIs, 9 rows) ===")
shared = ['10.1021/je600515j','10.1021/je300958c','10.1016/j.jct.2008.02.015']
for d in shared:
    rows = [r for r in led if r['source_document_id']==d]
    print(f"\n  DOI {d}: ledger obs={len(rows)}, molecules={len({x['inchikey'] for x in rows})}, "
          f"methods={sorted({x['method'] for x in rows})}, prop={sorted({x['property_name'] for x in rows})}")
    print(f"    source_file: {sorted({x['source_file'] for x in rows})[:2]}")
    print(f"    evidence_group_id: {sorted({x['evidence_group_id'] for x in rows})}")
    print(f"    independence_unit: {sorted({x['experimental_independence_unit'] for x in rows})}")
    print(f"    aggregates: {sorted({x['aggregate_id'] for x in rows})}")
    print(f"    traceability: {collections.Counter(x['traceability_status'] for x in rows)}")
    print(f"    notes: {sorted({x['traceability_note'] for x in rows if x['traceability_note'] not in ('not_evaluated','')})[:3]}")
    # which pool rows
    pr = [r for r in pool if r['source_doi']==d]
    print(f"    pool rows: {[(r['measurement_id'], r['name'], r['method'] if 'method' in r else '') for r in pr]}")
    for x in pr:
        lr = [y for y in rows if y['aggregate_id']==x['aggregate_id']]
        print(f"      {x['measurement_id']}: ledger method={[y['method'] for y in lr][:1]} "
              f"phase={[y['phase'] for y in lr][:1]} press={[y['pressure_kpa'] for y in lr][:1]} n={len(lr)}")

print("\n=== 5. pool rows whose ledger 'method' differs -> check method column presence ===")
print("  ledger method vocab:", collections.Counter(x['method'] for x in led).most_common(8))

print("\n=== 6. dupe-group cross-check by MSR id ===")
pool_msr = {x['measurement_id'] for r in pool for x in led_agg[r['aggregate_id']]}
print("  pool covers", len(pool_msr), "ledger MSR observations")
dg_ids = {i for r in dupg for i in r['measurement_ids'].split(';')}
print("  dupe-group MSR ids:", len(dg_ids))
print("  intersection with pool's underlying observations:", sorted(pool_msr & dg_ids))
print("  pool InChIKeys in dupgroups:", sorted({r['inchikey'] for r in pool} & {r['inchikey'] for r in dupg}))
# duplicate by molecule identity across the whole ledger for pool molecules
pool_ik = {r['inchikey'] for r in pool}
for ik in sorted(pool_ik):
    obs = [x for x in led if x['inchikey']==ik]
    docs = {x['source_document_id'] for x in obs}
    if len(docs) > 1:
        print(f"  {ik}: {len(obs)} obs from {len(docs)} docs {sorted(docs)}")

print("\n=== 7. per-pool-row: does any OTHER ledger doc also measure this molecule? ===")
for r in pool:
    obs = [x for x in led if x['inchikey']==r['inchikey']]
    docs = {x['source_document_id'] for x in obs}
    other = docs - {r['source_doi']}
    if other:
        print(f"  {r['measurement_id']} {r['name'][:30]:30s} cited={r['source_doi']} ALSO measured by {sorted(other)}")
print("  (blank above = cited DOI is the sole source in ledger for that molecule)")

print("\n=== 8. pressure anomalies (non-101.325) ===")
for r in pool:
    lr = led_agg[r['aggregate_id']]
    pr = {x['pressure_kpa'] for x in lr}
    if pr != {'101.325'}:
        print(f"  {r['measurement_id']} {r['name'][:30]:30s} pressures={sorted(pr)}")

print("\n=== 9. E4 source_ood note (utf8) ===")
for r in rd(p('b05','E4_domain_generalization','source_ood_results.csv')):
    print("  ", r['source_doi'], r['n_molecules'], r['status'], '|', r['note'])
