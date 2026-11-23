# -*- coding: utf-8 -*-
"""Reviewer 2 part 5: consensus duplicate rows + gate reproducibility."""
import csv, json, collections, os
OUT = r"E:\Claude Code\电解质ML\电解质ML\outputs"
def p(*a): return os.path.join(OUT, *a)
def rd(x):
    with open(x, encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))

cons=rd(p('admission_v2','consensus_decisions.csv'))
print("rows:", len(cons), "unique measurement_id:", len({r['measurement_id'] for r in cons}),
      "unique queue_id:", len({r['queue_id'] for r in cons}))
c=collections.Counter(r['measurement_id'] for r in cons)
dups={k:v for k,v in c.items() if v>1}
print("duplicated measurement_ids:", dups)
for mid in dups:
    rs=[r for r in cons if r['measurement_id']==mid]
    print(f"\n--- {mid} appears {len(rs)}x")
    for r in rs:
        print(f"   queue_id={r['queue_id']:24s} track={r['track'][:22]:22s} T={r['temperature_raw_K']:>7s} "
              f"eps={r['dielectric_raw']:>7s} r1..r4={r['r1_decision']}/{r['r2_decision']}/{r['r3_decision']}/{r['r4_decision']} "
              f"n_pass={r['n_pass']} status={r['consensus_status']} name={r['canonical_name'][:28]}")
    if len({r['consensus_status'] for r in rs})>1:
        print("   *** CONFLICTING STATUS ACROSS DUPLICATE ROWS ***")
    if len({r['dielectric_raw'] for r in rs})>1 or len({r['temperature_raw_K'] for r in rs})>1:
        print("   *** CONFLICTING (T,eps) ACROSS DUPLICATE ROWS ***")

print("\n=== does any duplicated id sit in the pool? ===")
pool=rd(p('b04','candidate_pool_v2_draft.csv'))
P={r['measurement_id'] for r in pool}
print("pool ∩ duplicated:", sorted(P & set(dups)))

print("\n=== naive vs deduped gate-1 count ===")
naive=[r for r in cons if r['consensus_status']=='AI_CONSENSUS_ACCEPTED']
print("naive ACCEPTED rows:", len(naive), "unique ids:", len({r['measurement_id'] for r in naive}))
print("accepted ids:", sorted({r['measurement_id'] for r in naive}))

print("\n=== tracks / priority groups of the 22 accepted ===")
acc=[r for r in cons if r['consensus_status']=='AI_CONSENSUS_ACCEPTED']
print(collections.Counter(r['track'] for r in acc))
print(collections.Counter(r['priority_group'] for r in acc))
print(collections.Counter(r['provenance_class'] for r in acc))
print(collections.Counter(r['frozen_admission_verdict'] for r in acc))
print("j03 verdicts:", collections.Counter(r['j03_verdict'] for r in acc))
print("j04 condition pair valid:", collections.Counter(r['j04_condition_pair_valid'] for r in acc))
print("j03 pair in single observation:", collections.Counter(r['j03_pair_in_single_observation'] for r in acc))
