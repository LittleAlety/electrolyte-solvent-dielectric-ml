# -*- coding: utf-8 -*-
"""Reviewer 2 part 6: crosswalk bijection, gate redundancy, boundary rows."""
import csv, json, collections, os
OUT = r"E:\Claude Code\电解质ML\电解质ML\outputs"
def p(*a): return os.path.join(OUT, *a)
def rd(x):
    with open(x, encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))

v6=rd(p('b01','dataset_v06_model_ready.csv'))
ex=rd(p('b01','dataset_v06_exclusions.csv'))
aud=rd(p('b04','candidate_exclusion_audit.csv'))
pool=rd(p('b04','candidate_pool_v2_draft.csv'))
led=rd(p('confirm_2027','provenance_repair','measurement_ledger_v1.csv'))
man=json.load(open(p('b04','pool_lineage_manifest.json'),encoding='utf-8'))

print("=== A. EPSV04-RNNN <-> v04row-NNN bijection across all 248 ===")
allv = [(r['measurement_id'], r['aggregate_id']) for r in v6] + \
       [(r['measurement_id'], r['aggregate_id']) for r in ex]
print("total v06 rows:", len(allv))
ids=[a for a,b in allv]; aggs=[b for a,b in allv]
print("unique measurement_id:", len(set(ids)), "unique aggregate_id:", len(set(aggs)))
print("bijection holds:", len(set(ids))==len(allv)==len(set(aggs)))
# is it strictly positional R%03d <- row-%03d ?
pos = all(r.split('-R')[1].lstrip('0').zfill(3)==a.split('row-')[1] for r,a in allv)
badpos=[(r,a) for r,a in allv if r.split('-R')[1].lstrip('0').zfill(3)!=a.split('row-')[1]]
print("strict positional R%03d == row-%03d for all 248:", pos, "exceptions:", badpos[:5])

print("\n=== B. GATE REDUNDANCY: is gate3 the same set as gate2? ===")
g2={r['measurement_id'] for r in v6}
g3=g2 - {r['measurement_id'] for r in ex}
print("gate2 pass n=",len(g2)," gate3 pass n=",len(g3)," identical:",g2==g3)
print("v06_ready ∩ v06_excluded:", len(g2 & {r['measurement_id'] for r in ex}))
print("manifest declaration:", man['declaration'])
print("manifest gate3 says n_excluded=", man['eligibility_gates']['gate_3_no_unresolved_blocker']['n_excluded'])
print("=> effective number of INDEPENDENT gates =", 2 if g2==g3 else 3)

print("\n=== C. pool aggregate single-document check ===")
led_agg=collections.defaultdict(list)
for r in led: led_agg[r['aggregate_id']].append(r)
for r in pool:
    docs={x['source_document_id'] for x in led_agg[r['aggregate_id']]}
    assert len(docs)==1, (r['measurement_id'],docs)
print("all 22 pool aggregates are SINGLE-document: True")

print("\n=== D. 303.15 boundary cluster vs source ===")
b=[(r['measurement_id'],r['name'],r['source_doi'],r['T_K']) for r in pool if r['T_K']=='303.15']
print(f"{len(b)} rows at the upper boundary 303.15 K:")
srcs=collections.Counter(x[2] for x in b)
for x in b: print("   ",x)
print("   source counts:", dict(srcs))
lo=[(r['measurement_id'],r['name'],r['source_doi']) for r in pool if r['T_K']=='293.15']
print("lower boundary 293.15 K:", lo)

print("\n=== E. T distribution by source (is T source-determined?) ===")
d=collections.defaultdict(set)
for r in pool: d[r['source_doi']].add(r['T_K'])
for k,v in sorted(d.items()): print(f"   {k:32s} T={sorted(v,key=float)}")

print("\n=== F. E1 CV vs source leak: how many pool rows have a same-document sibling? ===")
n=0
for r in pool:
    sib=[q['measurement_id'] for q in pool if q['source_doi']==r['source_doi'] and q['measurement_id']!=r['measurement_id']]
    if sib: n+=1
print(f"pool rows with >=1 same-source sibling molecule: {n}/22 ({100*n/22:.1f}%)")
print("distinct sources:", len({r['source_doi'] for r in pool}))

print("\n=== G. family x source cross-tab (E4 confounding) ===")
ads={r['measurement_id']:r for r in rd(p('b05','E4_domain_generalization','applicability_domain.csv'))}
ct=collections.defaultdict(list)
for r in pool: ct[ads[r['measurement_id']]['family']].append(r['source_doi'])
for f,v in sorted(ct.items()):
    c=collections.Counter(v)
    single = len(c)==1 and len(v)>1
    print(f"   {f:26s} n={len(v)} sources={dict(c)}" + ("   <<< ENTIRE FAMILY FROM ONE SOURCE" if single else ""))

print("\n=== H. oracle top-3 composition vs source (E6) ===")
pr=rd(p('b05','E6_screening_decisions','rank_vs_error.csv'))
top=sorted(pr,key=lambda r:-float(r['y_true']))[:3]
pdoc={r['measurement_id']:r['source_doi'] for r in pool}
for r in top: print("   ",r['measurement_id'],r['name'],r['y_true'],pdoc[r['measurement_id']])
print("   distinct sources in oracle top-3:", len({pdoc[r['measurement_id']] for r in top}))
