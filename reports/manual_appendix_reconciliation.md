# Manual Appendix I/J reconciliation: the glyme and dinitrile roster claim was a false negative

**Date:** 2026-09-24
**Scope:** Appendix I section A item 1 (the `PC / EC / glutaronitrile /
methoxypropionitrile / glyme` missing-roster finding) and its reuse in
Appendix J
**Artifact:** `probes/manual_appendix_reconciliation.json` (schema
`manual_appendix_reconciliation/v1`), built by
`probes/manual_appendix_reconciliation.py`
**Verdict:** 4 of the 6 sub-claims reproduce and are already closed; **2 are
false negatives** and must be corrected in the manual, not carried forward as
open data work.

## 1. Why this was re-derived

Appendix I section A stated that propylene carbonate, ethylene carbonate, the
three glymes, glutaronitrile and 3-methoxypropionitrile were all absent from
the dataset. That conclusion was then used to justify the v1.0 freeze veto and
a resource-ladder (Appendix J) that spends its first three tiers looking for
values the dataset already held.

The re-derivation keys on **InChIKey**, never on a common name, and reads the
committed CSVs. The alias registry it consumes,
`data/reference/dielectric_molecule_aliases.csv`, records both the string the
dataset stores and the name the literature uses.

## 2. Claim-by-claim verdict

| # | Appendix I A.1 claim | Verdict | Basis |
|---|---|---|---|
| 1 | `PC（碳酸丙烯酯）三版本全部缺席` | **confirmed, since closed** | absent in v0.1, v0.2, v0.3.1; first present in **v0.3.2** |
| 2 | `EC 应入 313–323K 扩展表` | **confirmed, since closed** | absent in v0.1, v0.2, v0.3.1; first present in **v0.3.2** |
| 3 | `extended band 为空` | **confirmed, since closed** | `extended_temperature` rows: **0** in v0.3.1 -> **1** in v0.3.2 and v0.3 |
| 4 | `diglyme/triglyme/tetraglyme 缺席` | **FALSE NEGATIVE** | all three present in **every** version from v0.1 onward |
| 5 | `glutaronitrile 缺席` | **FALSE NEGATIVE** | present in **every** version as `pentanedinitrile` |
| 6 | `methoxypropionitrile 缺席` | **confirmed, since closed** | absent through v0.3.2; added by the v0.3 build, still `model_ready=false` |

Dataset versions re-read (canonical LF-normalized SHA-256):

| Version | Rows | `temperature_band` column | Columns | canonical sha256 |
|---|---:|---|---:|---|
| v0.1 | 100 | absent | 17 | `6f31c5b2...4e5396` |
| v0.2 | 210 | absent | 24 | `569cebdf...3cc28a` |
| v0.3.1 | 243 | present, all `room_temperature` | 38 | `08941a76...938d78` |
| v0.3.2 | 245 | 244 room + 1 extended | 38 | `39d15e16...75b30be` |
| v0.3 | 246 | 245 room + 1 extended | 38 | `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4` |

The v0.1/v0.2 files predate the `temperature_band` column, so "the extended
band was empty" is only meaningful from v0.3.1 on. The probe records the column
as absent rather than as a zero-row band.

## 3. The false negative, explained

The dataset stores five of its molecules under names that share **no token**
with the name the literature uses:

| Common name (literature) | Stored name in the dataset | InChIKey |
|---|---|---|
| diglyme | `2,5,8-trioxanonane` | `SBZXBUIDTXKZTM-UHFFFAOYSA-N` |
| triglyme | `2,5,8,11-tetraoxadodecane` | `YFNKIDBQEZZDLK-UHFFFAOYSA-N` |
| tetraglyme | `2,5,8,11,14-pentaoxapentadecane` | `ZUHZGEOKBKGPSW-UHFFFAOYSA-N` |
| adiponitrile | `hexanedinitrile` | `BTGRAWJCKBQKAO-UHFFFAOYSA-N` |
| glutaronitrile | `pentanedinitrile` | `ZTOMUSMDRMJOTH-UHFFFAOYSA-N` |

A substring search for "diglyme", "triglyme", "tetraglyme", "adiponitrile" or
"glutaronitrile" over the `name` column returns nothing. Every one of those
rows has been present since v0.1. This is not a judgement call: the row counts
of the two earliest files already contain the molecules.

The same failure mode had already been recorded once, in a different guise:
`probes/g1plus_tier0_evidence.json` carries a
`method.incorrect_prior_keys_not_used` block pinning
`YFNKIDBQEZHQBU-UHFFFAOYSA-N` for triglyme and
`LNWVAMHESCFODF-UHFFFAOYSA-N` for tetraglyme - neither is a dataset key. A
key-based lookup with a wrong key and a name-based lookup with a trivial name
fail identically, and both produce a confident "absent".

What survives from the review is real: PC and EC genuinely were missing and
were added in v0.3.2, and 3-methoxypropionitrile genuinely was missing until
the v0.3 build. Those three are data work that has been done, not open items.

## 4. The guard

1. `data/reference/dielectric_molecule_aliases.csv` registers 87 names for 23
   molecules: the stored name, the literature common name, abbreviations and
   systematic synonyms. The current dataset is the authority for the stored
   name - the registry is checked against it, not the other way round.
2. `probes/manual_appendix_reconciliation.py` reports, per molecule, whether a
   common-name search would find the row, and the report exposes the five
   token-disjoint cases.
3. `tests/test_manual_appendix_reconciliation.py` fails if any glyme or
   dinitrile ever leaves any dataset version, if the registry drifts from the
   stored names, or if the working manual reintroduces the stale sentence.

## 5. What did not change

This probe moved no dielectric value, temperature, evidence level, `model_ready`
flag, conflict status or dataset byte; the manual reconciliation it describes is
itself the change. The dataset is 246 rows x 38 columns. Its canonical SHA-256
was `57387b98f899c6c0eff12716cc5b754f65d2ee0edd5523330af049ddded26fab` when this
reconciliation was written, and is
`765fd8e04270f3e277681d6ae8e6200bfcc77c8841a89ebe0f8a3a70bc646b60` after the
separate v0.3.11 revision, which changed only fluoroethylene carbonate's
`conflict_status` and `notes`. The reconciliation is a provenance-and-QA
correction: it prevents a reviewer-facing document from spending its first three
resource tiers rediscovering data the repository has shipped since v0.1.

> **v0.3.13 re-pin (2026-09-25):** the current canonical digest is
> `a446c216874538d900e9f3ebbf18178926b812b77a213a395f4ff8cddfc01085`.
> The `57387b98...`, `765fd8e0...`, and v0.3.12 `1b285fe8...` values are the
> historical v0.3.3, v0.3.11, and v0.3.12 pins; this reconciliation probe itself
> still wrote no cell.

## 6. Reproducing

```
.venv\Scripts\python.exe probes\manual_appendix_reconciliation.py
.venv\Scripts\python.exe -m pytest tests\test_manual_appendix_reconciliation.py -q
```

## 7. Honest limitation

The "common-name search would miss" flag is a bounded lexical heuristic over the
registered aliases, not a semantic identity check. A stored name counts as
findable only when a registered common name is a substring of it, or when they
share a token of at least four characters that is not on the generic-token
denylist (for example, "methyl", "carbonate" or "sulfone"). If no common name
was registered, the field is null: the probe reports that the question cannot be
judged rather than silently treating it as a miss. The heuristic says nothing
about whether the underlying measurement is correct; that remains the job of the
per-row provenance layer.

> **Re-pinned for v0.3.14 (2026-09-25).** The current canonical digest of
> `data/dielectric_v03.csv` is
> `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`.
> The v0.3.14/D2 scope relabel added the `out_of_scope_ionic_or_organometallic`
> gate flag plus a scope note to the four rows whose xTB feature generation
> failed. It changed no numeric value, temperature, `model_ready` flag or
> `conflict_status`; the 246 rows x 38 columns, the 240 `model_ready=true` rows
> and the 236-row frozen benchmark are byte-identical. Every earlier hash quoted
> above remains the historical pin of its own revision and is deliberately not
> rewritten.
>
> The D1 leave-EC-out probe wrote no data cell and did not change this digest;
> see `reports/d1_leave_ec_out_sensitivity.md`.
