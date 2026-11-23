# Reviewer 3 — Data Mapping, Identity, Temperature, Frequency and Code Correctness

**Work package:** B04-PRECONFLICT · **Reviewer:** 3 of 4 (independent)
**Scope:** butan-2-ol `BTANRVKWQNVYAZ-UHFFFAOYSA-N` and DMAc `FXHOOIRPVKKKFG-UHFFFAOYSA-N`
**Deliverables:** `reviewer_3_decisions.csv`, this report
**Constraint honoured:** no existing file was modified. Verified by sha256 snapshot before and after
(`_r3_pre_hash.txt` vs `_r3_final_hash.txt`, all 7 tracked artifacts byte-identical).

---

## 0. Bottom line

| Conflict | Decision | v06 value correct? | Temp explains spread? | Resolution |
|---|---|---|---|---|
| `MCONF-BTANRVKWQNVYAZ-298` (butan-2-ol) | **PASS** | **yes** (16.6) | **no** (<3%) | `KEEP_V06_VALUE` |
| `MCONF-FXHOOIRPVKKKFG-303.15` (DMAc) | **HOLD** | **no** (not established) | **no** (ΔT = 0.000 K) | `NEEDS_PRIMARY_DOCUMENT` |
| `ALL` (machinery) | **FAIL** | — | — | `RETAIN_PARALLEL` |

Three systemic code defects found. Reproducibility itself **passes**.

---

## 1. Observations pulled from `measurement_ledger_v1.csv`

### 1.1 butan-2-ol — the 4-row cluster

| T (K) | ε | Source DOI | measurement_id | P (kPa) | f | Method |
|---|---:|---|---|---:|---|---|
| **298.0** | **17.6** | 10.1016/j.fluid.2013.12.014 | MSR-29e3026c33ebc6a8 | 101 | 0 | PNA-N5227A microwave network analyser |
| 298.15 | 16.58 | 10.1021/je900503p | MSR-644e137ed8fac806 | 101 | 0 | Dekameter |
| 298.15 | 16.6 | 10.1021/je3007666 | MSR-790ead4efdd5221b | 100 | 0 | Dielectrometer |
| 298.15 | 16.6 | 10.1021/je800593p | MSR-8f17666d0a81b3c0 | 101 | 0 | Dielectrometer |

`min=16.58`, `max=17.6`, spread `(17.6−16.58)/16.58 = 6.152%` → **register's 6.15% is real**.

All 15 ledger rows for this key were also inspected (288.15→313.15 K); the four above are the
only members of the ±0.5 K cluster at 298 K.

### 1.2 DMAc — the 3-row cluster

| T (K) | ε | Source DOI | measurement_id | P (kPa) | f | Method |
|---|---:|---|---|---:|---|---|
| 303.15 | **37.72** | 10.1016/j.fluid.2008.01.024 | MSR-5e013323fd6f27cb | 101 | 0 | capacitive method |
| 303.15 | **37.72** | 10.1016/j.fluid.2009.07.009 | MSR-de55e6c75a57f2a5 | 101.325 | 0 | parallel plate |
| 303.15 | **38.67** | 10.1021/je9002515 | MSR-fe12c1254a29e890 | 101 | 0 | parallel plate |

`min=37.72`, `max=38.67`, spread `(38.67−37.72)/37.72 = 2.519%` → **register's 2.52% is real**.

All 12 rows for this key were inspected (303.15→393.15 K); all three cluster members are at
**exactly** 303.15 K.

### 1.3 Frequency and pressure — excluded as explanations

Every cluster member in both conflicts has `frequency_mhz = 0`, `frequency_hz = 0`, and
`property_family = zero_frequency`. Pressure is 100–101.325 kPa throughout, i.e. ambient, and
within 1.3% — far too small to move ε by 2.5% or 6%. **Neither frequency nor pressure can
explain either spread.** The only remaining candidate is temperature, tested next.

---

## 2. Does temperature explain the spread? **No, in both cases.**

### 2.1 butan-2-ol — the 0.5 K window is not the problem

The cluster spans only `298.0 → 298.15 K`, i.e. **ΔT = 0.15 K**.

| Slope used | ε change over 0.15 K | Share of the 6.15% spread |
|---|---:|---:|
| Task assumption −0.25 %/K | 0.0375 % | **0.61 %** |
| Molecule's own measured slope −0.96 %/K | 0.15 % | **2.4 %** |

To close a 6.02% gap you would need **6.3 K** at the measured slope or **24.1 K** at
−0.25 %/K — against an actual range of 0.15 K and a clustering window of 0.5 K. The outlier is
also 5.4% off the molecule's own trend and corresponds to 292.5 K, i.e. **5.5 K** from the
labelled 298 K.

> **Conclusion:** the 0.5 K window can in principle mix physically different readings, and this is
> a genuine design weakness — but here it is **not** the cause. Only ≤2.4% of a 6.15% spread is
> attributable to temperature.

### 2.2 DMAc — ΔT is exactly zero

All three observations are at 303.15 K. `ΔT = 0.000 K`. Temperature contributes **nothing**.
The 2.52% is pure source disagreement.

> The task hypothesised that a 0.5 K window might be manufacturing these conflicts. It is not.
> Both spreads are genuine cross-source disagreements, and the 0.5 K tolerance is exonerated as
> the *cause* — though it remains a latent defect (§4.1).

---

## 3. Is the v06 value correct?

### 3.1 butan-2-ol → **16.6 is correct**

`build_dataset_v06.py` takes the v04 row verbatim; v04 built `v04row-010` as a
`median_in_window` over 293.15–303.15 K. Reproduced exactly:

```
in-window values (n=10): [15.75, 15.75, 15.75, 16.58, 16.6, 16.6, 17.51, 17.51, 17.51, 17.6]
median = 16.6   ==  v06 value 16.6  ✓
cluster-only values (n=4): [16.58, 16.6, 16.6, 17.6]  median = 16.6  (same)
```

16.6 is **not an interpolation** — it is an actually observed value, held by two rows
(`MSR-790ead4efdd5221b`, `MSR-8f17666d0a81b3c0`). It is both the median and a real datum, so the
"is it the median or a specific row?" question resolves as **both**.

The outlier **17.6** comes from a *mixture* paper (Guo-Zhu & Jie, *Fluid Phase Equilib.* 2013,
"DMSO – monohydric alcohol mixture solution at the microwave frequency"). Its seven "pure"
endpoints are 49, 33.1, 22.8, 21.3, 19.1, 17.8, **17.6** — a mixture-series endpoint, not a
dedicated pure-liquid measurement. Against same-T consensus medians that source is biased in
**both directions**:

| Compound | this source | consensus median | bias |
|---|---:|---:|---:|
| DMSO | 49.0 | 46.069 | **+6.36%** |
| butan-2-ol | 17.6 | 16.600 | **+6.02%** |
| 1-butanol | 17.8 | 18.290 | −2.68% |
| methanol | 21.3 | 22.265 | −4.33% |
| 1-propanol | 22.8 | 26.460 | **−13.83%** |
| ethanol | 33.1 | 36.235 | **−8.65%** |

Mean bias −2.69%, mixed sign → **not** a uniform calibration offset, but a low-reliability
endpoint source. It is the only cluster member measured by microwave network analyser.

**Author-level independence** (a point the register misses): the four DOIs are only **three**
author groups —

* `10.1021/je3007666` — Klimaszewski, Borun, Bald, Sengwa
* `10.1021/je800593p` — Chmielewska, Zurada, Klimaszewski, Bald
* `10.1021/je900503p` — Farhan, Awwad
* `10.1016/j.fluid.2013.12.014` — Guo-Zhu, Jie

The first two share **Klimaszewski + Bald** and agree on **15/15** shared (mol, T) points to
1e-9 — one measurement lineage counted twice. So effective independent evidence is **3 groups:
two agree at 16.58–16.6, one disagrees at 17.6.**

> **Verdict:** 16.6 is correct and well supported. The "6.15% conflict" is one mixture-paper
> endpoint against a duplicated consensus — **not** an unresolved measurement conflict.

### 3.2 DMAc → **37.72 is not established as correct**

37.72 is the median of `[37.72, 37.72, 38.67]` and is an observed value held by two rows. But
those two rows are **the same three authors** (Sengwa, Khatri, Sankhla — in different orders) and
agree **exactly on 5/5** shared (mol, T) points:

```
FXHOOIRPVKKKFG  T=303.15  37.72  ==  37.72
PEDCQBHIVMGVHV  T=303.15  41.17  ==  41.17
UEEJHVSXFDXPFK  T=303.15  17.18  ==  17.18
ZHNUHDYFZUAESO  T=303.15 106.14  == 106.14
ZMXDDKWLCZADIW  T=303.15  36.55  ==  36.55
```

The register's `n_distinct_sources = 3` is a count of **DOI strings**, not independent
measurements; author-level independent groups = **2**. The "median of 3" is really a
**1-vs-1 tie**, and the median rule breaks that tie arbitrarily in favour of the duplicated pair.

**Shape test strongly favours 38.67.** The Swiergiel & Jadzyn paper reports DMAc at ten
temperatures 303.15–393.15 K as one coherent curve:

| T (K) | 303.15 | 313.15 | 323.15 | 333.15 | 343.15 | 353.15 | 363.15 | 373.15 | 383.15 | 393.15 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ε | **38.67** | 36.551 | 34.678 | 32.949 | 31.458 | 29.954 | 28.578 | 27.287 | 26.074 | 24.923 |

Substitution test — forcing 303.15 to 37.72 degrades the fit:

| Fit | RMS as reported | RMS with 37.72 forced | penalty |
|---|---:|---:|---:|
| quadratic | 0.0684 | 0.1332 | **1.9×** |
| cubic | 0.0266 | 0.1113 | **4.2×** |

Back-extrapolating the nine points ≥313.15 K to 303.15 K:

| Method | ε(303.15) | distance to 37.72 | distance to 38.67 |
|---|---:|---:|---:|
| quadratic, all 9 | 38.375 | 0.655 | **0.295** |
| quadratic, first 5 | 38.530 | 0.810 | **0.140** |
| quadratic, first 4 | 38.638 | 0.918 | **0.032** |
| quadratic, first 3 | 38.568 | 0.848 | **0.102** |
| linear, all 9 | 37.483 | −0.237 | −1.187 |

Even a straight line gives **37.483 — below 37.72**, so 37.72 sits *under* the linear
continuation while 38.67 sits on the curvature. The implied first-interval slope is **−0.212 /K**
if ε(303.15)=38.67, matching the later slopes (−0.187, −0.173, −0.149, −0.150; mean −0.165 /K),
whereas 37.72 implies an anomalous **−0.117 /K** that breaks monotone steepening. 38.67 also
recurs as the x→0 endpoint of the DMAc + N-methylacetamide mixture series in the same paper.

> **Verdict — HOLD, not adoption.** Internal coherence establishes the *shape* of the Swiergiel
> curve, not its *absolute accuracy*: a self-consistent series can still be uniformly offset, and
> a single-point source can still be right. The quoted 95% uncertainties (0.23 and 0.387) are both
> smaller than the 0.95 gap, so uncertainty does not arbitrate. **Nothing in the ledger decides
> whether Swiergiel's absolute scale or Sengwa's single point is correct.** Primary documents are
> required. v06's 37.72 is **not** established as correct — it is an artefact of counting one
> duplicated lineage as two independent sources.

---

## 4. Code audit — three defects, one clean pass

### 4.1 D1 — greedy `used`-set clustering is order-dependent **and can silently drop a conflict**

**`scripts/b01/build_source_conflict_register.py:207–224`**

```python
used: set[int] = set()
for i in range(len(mol_rows)):
    if i in used: continue
    ti = fnum(mol_rows[i].get("temperature_K"))
    cluster = [mol_rows[i]]; used.add(i)
    for j in range(i + 1, len(mol_rows)):        # only LATER rows
        if j in used: continue
        if abs(ti - tj) <= T_TOLERANCE_K:        # anchor-radial, never re-checked
            cluster.append(mol_rows[j]); used.add(j)
```

The cluster is *anchor-radial*, not *span-based*: it tests every row only against the anchor
`t_i`, and never re-checks the cluster's own span. **Yes, this is a real defect.**

**Measured on real data** — 201 random row orders per molecule: **24 of 153 molecules** produce a
different clustering. `BTANRVKWQNVYAZ` alone shows **117** distinct clusterings, and its
`conflict_id` flips between:

* `MCONF-BTANRVKWQNVYAZ-298.15` — 1502/2000 shuffles
* `MCONF-BTANRVKWQNVYAZ-298` — 498/2000 shuffles

The anchor — hence the identifier — is a coin flip determined by which row happens to be first.

**Minimal reproducer showing actual suppression** (not just relabelling): rows at
`(297.0, 20.0)`, `(297.4, 20.1)`, `(297.9, 25.0)` span 0.9 K with every *adjacent* pair within
0.5 K:

| Row order | Result |
|---|---|
| A, B, C | **0 conflicts — 24.4% disagreement silently lost** |
| A, C, B | **0 conflicts — silently lost** |
| B, A, C | 1 conflict, 3 rows, 25.00% |
| C, B, A | 1 conflict, 2 rows, 24.38% |

This defeats the register's own stated purpose (docstring lines 9–11: conflicts should enter the
queue *"by construction rather than by luck"*). Admission is currently luck.

**Could it merge or split *these two* conflicts wrongly? No.** DMAc: 2000/2000 shuffles give
anchor 303.15, the same 3 rows, the same 2.5186%. butan-2-ol: always the same 4 rows and the same
6.152% — only the **label** flips. So both conflict *numbers* are sound; the identifiers and the
completeness guarantee are not. Note the register already uses correct pairwise comparison at the
**aggregate** layer (lines 103–120) — the defect is confined to the measurement layer.

**Fix:** sort by temperature and use a span-based (complete-linkage) cluster, or bucket by
`(molecule, T rounded to tolerance)` with an explicit max-span assertion.

### 4.2 D2 — v06 is completely blind to the conflict register

**`scripts/b01/build_dataset_v06.py`** — grep for `conflict`, `MCONF`,
`measurement_conflict_register`, `source_conflict_register`: **0 hits in all cases.**

`model_ready` is computed at lines **187–199** from pressure / pair-validity / temperature /
band only. `resolution_status = "UNRESOLVED"` is **never consulted**. Consequence:

* **2 of 74 model-ready rows (2.70%)** carry an unresolved conflict — `v04row-010` butan-2-ol
  (16.6) and `v04row-021` DMAc (37.72) — both with `flags=NONE`, `blocking_reasons=''`, i.e. they
  look perfectly clean.
* The other 14 conflicted molecules are excluded only **incidentally** (they happen to be
  `PRESSURE_HETEROGENEOUS` or `PAIR_NOT_VALID`), not because they conflict.
* One conflicted molecule (`UJPMYEOUBPIPHQ`, 5.45% spread) is **absent from v06 entirely**.

So v06's exclusion of conflicts is **accidental, not a rule** — and the two conflicts that survive
are precisely the two under adjudication. **This is the direct answer to question 6.**

### 4.3 D3 — exclusion tally is double-counted

`build_dataset_v06.py` appends `NO_CONTRIBUTING_MEASUREMENT` at **lines 171–173** (via
`excl_reason`) and again at **lines 196–197** (the `not members` branch). **147 of 174** exclusion
rows carry that reason twice.

The manifest's `exclusions_by_reason` sums to **514** across **174** excluded rows:

| Reason | manifest | true distinct rows |
|---|---:|---:|
| NO_CONTRIBUTING_MEASUREMENT | 294 | **147** |
| PAIR_NOT_VALID | 170 | 170 |
| TEMPERATURE_IMPUTED | 22 | 22 |
| PRESSURE_HETEROGENEOUS | 15 | 15 |
| SYNTHETIC_PAIR | 11 | 11 |
| OUTSIDE_ROOM_BAND | 2 | 2 |
| **sum** | **514** | **367** |

The per-reason histogram in `dataset_v06_manifest.json` is unusable as a denominator.

### 4.4 Reproducibility — **passes**

`build_source_conflict_register.py` run twice:

```
measurement_conflict_register.csv  a7637bc64b7e7a244cb57d0ed3e949d63ddf9f2be5f03762a684ab5d12fab3de  (both runs)
source_conflict_register.csv       395a4c98651f96e40f3d536d84e362abf63fdf7976930098afc7627ad064de6f  (both runs)
→ BYTE-IDENTICAL
```

The only non-determinism is the wall-clock `generated_at_utc` in `.json`/`.md`, which is expected
(the CSVs carry no timestamp). Determinism therefore holds **for the current row order only** —
D1 shows it would not survive a re-ordered input.

> **Housekeeping note:** because the builder rewrites `source_conflict_register.json` and
> `source_conflict_report.md` with a fresh timestamp, my two verification runs did change those two
> files. I restored both to their **exact pre-run bytes** by recovering the original
> `generated_at_utc = 2026-11-23T05:36:50Z` and confirming the sha256 matched the pre-run snapshot.
> Final state: all 7 tracked artifacts byte-identical to before I started.

---

## 5. Answer to question 6 — should a conflicted molecule be excluded?

**Both are currently `model_ready = true` despite `UNRESOLVED` conflicts. That is wrong as
machinery, even though one of the two values happens to be defensible.**

The principled position:

* An unresolved conflict is a **label-uncertainty** flag, not automatically a disqualification. If
  the evidence clearly favours one value (butan-2-ol: 16.6), retaining it is correct — but the row
  must **carry the conflict as a flag** so downstream training can weight or ablate it.
* If the evidence does **not** decide (DMAc), the row must **not** enter a model-ready set at all.
  Feeding 37.72 as a clean label teaches the model a value that is at best a coin flip between two
  duplicated lineages.
* The current behaviour — `flags=NONE`, empty `blocking_reasons`, no conflict reference — is the
  worst of both: the conflict is invisible to every downstream consumer.

**Recommended:** make `resolution_status` an explicit `model_ready` gate. `UNRESOLVED` +
`evidence_grade=DOCUMENTED` + clear direction → retain with a `CONFLICT_<id>` flag.
`UNRESOLVED` + undecidable → `blocking_reasons += "UNRESOLVED_CONFLICT"`, exclude.

---

## 6. What I did not decide

* I did **not** average, pick, or merge anything — both values stay visible.
* I did **not** attempt to resolve DMAc from secondary evidence. The shape test is strong but
  cannot settle absolute accuracy; that needs the primary papers.
* I did **not** re-adjudicate the other 14 conflicted molecules; their exclusion was incidental,
  which is itself a finding (D2), but their individual merits are outside my remit.

---

## 7. Files

| File | Purpose |
|---|---|
| `reviewer_3_decisions.csv` | Required deliverable — 3 rows (2 conflicts + `ALL`) |
| `reviewer_3_report.md` | This report |
| `_r3_pull.py` … `_r3_analysis8.py` | Reproduction scripts for every number quoted |
| `_r3_pre_hash.txt` / `_r3_final_hash.txt` | Proof no existing file was modified |
| `_r3_run1.log` / `_r3_run2.log`, `_r3_run{1,2}_hash.txt` | Reproducibility evidence |
