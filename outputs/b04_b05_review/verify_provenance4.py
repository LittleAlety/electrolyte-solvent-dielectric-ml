# -*- coding: utf-8 -*-
"""Reviewer 2 part 4: cross-file coverage arithmetic + family/source confounding."""
import csv, json, collections, os
OUT = r"E:\Claude Code\电解质ML\电解质ML\outputs"
def p(*a): return os.path.join(OUT, *a)
def rd(x):
    with open(x, encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))

pool=rd(p('b04','candidate_pool_v2_draft.csv'))
cons=rd(p('admission_v2','consensus_decisions.csv'))
v6=rd(p('b01','dataset_v06_model_ready.csv'))
ex=rd(p('b01','dataset_v06_exclusions.csv'))
aud=rd(p('b04','candidate_exclusion_audit.csv'))

P={r['measurement_id'] for r in pool}
C={r['measurement_id'] for r in cons}
V={r['measurement_id'] for r in v6}
X={r['measurement_id'] for r in ex}
A={r['measurement_id'] for r in aud}

print("=== COVERAGE ARITHMETIC ===")
print(f"|pool|={len(P)} |consensus|={len(C)} |v06ready|={len(V)} |v06excl|={len(X)} |audit|={len(A)}")
print(f"pool ⊂ consensus : {P <= C}   pool ⊂ v06ready : {P <= V}")
print(f"consensus ∩ v06excl = {len(C & X)} {sorted(C & X)}")
print("consensus ids NOT in v06ready and NOT in v06excl:",
      sorted(C - V - X))
print("v06ready NOT in consensus:", sorted(V - C), "count", len(V - C))
print("consensus n_pass distribution:", collections.Counter(r['n_pass'] for r in cons))
print("consensus status distribution:", collections.Counter(r['consensus_status'] for r in cons))
print("n_pass=4 but status!=ACCEPTED:",
      [(r['measurement_id'], r['consensus_status'], r['n_pass']) for r in cons if r['n_pass']=='4' and r['consensus_status']!='AI_CONSENSUS_ACCEPTED'])
print("status=ACCEPTED but n_pass!=4:",
      [(r['measurement_id'], r['consensus_status'], r['n_pass']) for r in cons if r['consensus_status']=='AI_CONSENSUS_ACCEPTED' and r['n_pass']!='4'])
acc={r['measurement_id'] for r in cons if r['consensus_status']=='AI_CONSENSUS_ACCEPTED'}
print("ACCEPTED ∩ v06excl (should be empty):", sorted(acc & X))
print("ACCEPTED count:", len(acc))

print("\n=== AUDIT vs CONSENSUS status consistency ===")
cst={r['measurement_id']:r['consensus_status'] for r in cons}
bad=[(r['measurement_id'],r['b02_consensus_status'],cst.get(r['measurement_id'])) for r in aud
     if r['measurement_id'] in cst and r['b02_consensus_status']!=cst[r['measurement_id']]]
print("audit b02_consensus_status != consensus_decisions status:", len(bad), bad[:5])
print("audit rows with b02_consensus_status=NOT_IN_QUEUE:", sum(1 for r in aud if r['b02_consensus_status']=='NOT_IN_QUEUE'))
print("  of those, present in consensus file:", sum(1 for r in aud if r['b02_consensus_status']=='NOT_IN_QUEUE' and r['measurement_id'] in cst))

print("\n=== audit reason x v06 flag cross-tab ===")
ct=collections.Counter((r['v06_model_ready'], r['exclusion_reason']) for r in aud)
for k,v in sorted(ct.items()): print("  ",k,v)

print("\n=== FAMILY x SHARED-DOI confounding (E4 relevance) ===")
ads={r['measurement_id']:r for r in rd(p('b05','E4_domain_generalization','applicability_domain.csv'))}
doc2=collections.defaultdict(list)
for r in pool: doc2[r['source_doi']].append(r)
for d,v in sorted(doc2.items(), key=lambda x:-len(x[1])):
    if len(v)>1:
        print(f"  {d} ({len(v)} mols):")
        for r in v:
            a=ads[r['measurement_id']]
            print(f"     {r['measurement_id']} {r['name'][:40]:40s} family={a['family']:24s} "
                  f"in_AD={a['in_applicability_domain']} nn={a['nn_tanimoto']} eps={r['dielectric']}")
print("\nfamily totals:", collections.Counter(a['family'] for a in ads.values()))

print("\n=== E1/E4/E6 id-set identity vs pool (final) ===")
e1={r['measurement_id'] for r in rd(p('b05','E1_structure_vs_electronic','predictions_loo.csv'))}
e6={r['measurement_id'] for r in rd(p('b05','E6_screening_decisions','rank_vs_error.csv'))}
e4={r['measurement_id'] for r in rd(p('b05','E4_domain_generalization','applicability_domain.csv'))}
print("E1==pool",e1==P,"| E1==E4",e1==e4,"| E1==E6",e1==e6,"| E4==pool",e4==P,"| E6==pool",e6==P)

print("\n=== E4 lofo family counts vs pool ===")
lofo=rd(p('b05','E4_domain_generalization','leave_one_family_out.csv'))
print("cols",list(lofo[0].keys()))
for r in lofo: print("  ",r)

print("\n=== E6 topk_regret n_pool ===")
for r in rd(p('b05','E6_screening_decisions','topk_regret.csv')): print("  ",r)
