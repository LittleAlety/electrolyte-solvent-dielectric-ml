# On-disk check of the J-STAGE route: the Hagiyama 2008 premise is false, and what the open chain did corroborate

**Date:** 2026-09-25
**Evidence file:** `probes/jstage_corroboration_evidence.json`
**Scope:** two questions the Week 9 plan left open on the J-STAGE route
**Restricted sources used:** none
**Dataset impact:** none (no cell changed; `data/dielectric_v03.csv` digest `ff214293...` untouched)

## 1. Why this probe exists

The Week 9 plan carried a specific instruction: *go to J-STAGE and fetch Hagiyama et al. 2008,
because Chemistry Letters is a Chemical Society of Japan journal whose J-STAGE full text is free.*
If that were true, the FEC 107 leg could be closed at primary-measurement level with one download,
and two restricted-catalog targets (PC, EC) would come free in the same paper.

The premise is false. This probe records the falsification with identifier-level evidence, and then
records what the open literature **did** corroborate.

## 2. Verdict on the premise: falsified

`10.1246/cl.2008.210` resolves to **Oxford University Press**, and the article is **closed access**.

| Source | Observation |
| --- | --- |
| DOI resolver, redirects disabled | `HTTP 302 -> https://academic.oup.com/chemlett/article/37/2/210/7386188` |
| Crossref | `publisher = Oxford University Press (OUP)`; every `link[]` entry targets an `academic.oup.com` PDF |
| OpenAlex (work) | `is_oa=false`, `oa_status=closed`, `oa_url=null`, `any_repository_has_fulltext=false` |
| OpenAlex (journal) | *Chemistry Letters* host organisation = **Oxford University Press**, 30,317 works |
| J-STAGE article pattern | `/article/cl/37/2/37_210/_article` and `/article/cl/37/2/37_210/_pdf` both **HTTP 404** |
| J-STAGE journal root | `/browse/cl` and `/browse/cl/37/2/_contents/-char/en` both **HTTP 404** |

Two things follow:

1. **The journal root 404s, not just the article id.** The negative is therefore not an artefact of a
   mistyped article identifier. There is no URL-pattern correction that turns this into a hit.
2. **OpenAlex indexes exactly one location for the work, and it is the publisher landing page.**
   `any_repository_has_fulltext=false` means no repository deposit exists anywhere in its index.

So "we could not open it" upgrades to **"there is no open copy to open."** Those are different
claims, and only the second one closes the search.

### Consequence for the plan's three tiers

| Tier | Status after this probe |
| --- | --- |
| 1. Retry the exact J-STAGE URLs | **Exhausted. Cannot succeed.** The URLs are not wrong; the host is not J-STAGE. |
| 2. Interlibrary loan / document delivery against the DOI | **Still open** — the only remaining route to the primary measurement. |
| 3. State two unreconciled primary legs and keep the row withheld | **The default if tier 2 fails.** Already written into the paper. |

The FEC row keeps `model_ready=false` and its curated-exclusion entry unchanged.

### Honest boundary

This shows no open copy is *discoverable*. It does not show the article is unreadable by other
means (institutional entitlement, interlibrary loan, print), and it says nothing about whether
**107** is the right number. The claim is about the state of the indexes on 2026-09-25.

## 3. What the open chain did corroborate: PC and EC

Two of the four restricted-catalog cross-check targets can be verified **without SpringerMaterials**,
from an open-access J-STAGE paper that names its own source.

### The chain

```
Nanbu et al. 2007, Electrochemistry 75(8) 607-610        (open access, J-STAGE)
   |  printed page 608, verbatim:
   |    "... the relative permittivity of FEC (78.4 at 40 C)4) is lower than that of
   |     EC (89.78 at 40 C).12) The relative permittivity of PC is 64.92 at 25 C.12)"
   |
   +-- ref 12) J. A. Riddick, W. B. Bunger, and T. K. Sakano,
              "Organic Solvents: physical properties and methods of purification",
              4th ed., Wiley-Interscience, New York (1986)
```

The reference list was read from the same PDF, so the attribution is not inferred: the open paper
says its PC and EC permittivities come from Riddick 4th ed., which is precisely the compilation the
restricted-catalog cross-check was standing in for.

### Agreement with the stored rows

| Target | Stored (canonical CSV) | Corroborating (open literal) | T aligned | Absolute deviation | Relative |
| --- | --- | --- | --- | ---: | ---: |
| Propylene carbonate | **64.9** at 298.15 K (25 C) | 64.92 at 25 C | yes | 0.02 | 0.031% |
| Ethylene carbonate | **90.5** at 313.15 K (40 C) | 89.78 at 40 C | yes | 0.72 | 0.802% |

Both are temperature-aligned, so neither comparison needs a temperature correction. Two further open
papers (`Electrochemistry` 2013, 81(10) 817-819 and 820-822) reproduce the same PC **64.92 at 25 C**
and EC **89.78 at 40 C** figures, so neither value is a single-transcription artefact.

### What this is not

Corroboration here means *agreement with a compilation restatement*, not independent measurement.
Riddick 4th ed. is itself a compilation. Nothing in this section claims a new measurement, and the
stored values are not changed. What it establishes is narrower and still useful: **the restricted
catalog was never the only route to these two numbers.**

**Not corroborated by this probe:** GVL and DME, the remaining two restricted targets.

## 4. Reproduction

```bash
python -c "import json,urllib.request;print(json.load(urllib.request.urlopen('https://api.openalex.org/works/doi:10.1246/cl.2008.210'))['open_access'])"
python -c "import json,urllib.request;print(json.load(urllib.request.urlopen('https://api.crossref.org/works/10.1246/cl.2008.210'))['message']['publisher'])"
```

The three Electrochemistry PDFs are held under `data/external/g1plus/tier3/` and are git-ignored;
their SHA-256 values are recorded in the evidence file so a holder of the PDFs can confirm the same
bytes were read. Regression tests: `tests/test_jstage_corroboration.py`.
