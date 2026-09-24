# G1+ Tier 1: what PubChem actually holds for the dielectric targets

**Date:** 2026-09-24
**Probe:** `probes/g1plus_pubchem_probe.py`
**Evidence:** `probes/g1plus_pubchem_evidence.json` (sha256
`9f180a5941fe2fa2eebf067343436c60d6c119894a047787b5ef46977b849c83`; raw responses cached under
`data/external/g1plus/pubchem/`, git-ignored)
**Opened with:** plain HTTPS through `urllib` (PubChem PUG-REST + PUG-View). No
browser session and no login is needed for these endpoints; the SpringerMaterials
links below are the ones that need the user's Microsoft Edge session.

## The claim under test

Appendix J ranks PubChem as tier 1 and states that its "Experimental Properties"
section deposits Riddick handbook dielectric data, naming ethylene carbonate as
the worked example. Fourteen targets were resolved **by InChIKey first**, so a
name collision can never be recorded against the wrong substance; the name page
is then looked up separately only to check it is the same CID.

Result: **every target resolved to the dataset InChIKey, and none of them carries
a dielectric value that PubChem itself attributes to Riddick.** The claim is
accurate in spirit - the handbook is cited on these pages - but not as a source
of the number.

## What is citable from PubChem

Only two of the fourteen targets expose a number inside PubChem, and neither is a
Riddick entry. In the evidence JSON this is the `with_standard_dielectric_value`
list; the nine SpringerMaterials hits are **links, never values**, and ethylene
carbonate is filed separately under `with_narrative_mention_only`:

| Compound | PubChem CID | Value | As stated | Source PubChem cites |
| --- | --- | --- | --- | --- |
| Sulfolane | 31347 | **43.3** | no temperature | Kirk-Othmer Encyclopedia of Chemical Technology, 4th ed., Vol. 23, p. 135 (1995), PEER REVIEWED |
| Acetonitrile | 6342 | **38.8** | at 20 C | O'Neil (ed.), The Merck Index, Royal Society of Chemistry, 2013, p. 14, PEER REVIEWED |
| Acetonitrile | 6342 | **42.0 / 38.8 / 26.2** | at 0 / 20 / 81.6 C | DeVito, Nitriles, Kirk-Othmer Encyclopedia of Chemical Technology (2007 posting) |

The acetonitrile entry is the interesting one: the dataset holds **37.5 at
293.15 K**, which is 20 C, the same temperature as PubChem's 38.8 - a 3.5%
disagreement at matched conditions. It is recorded as a cross-check note; the
NBS Circular 514 basis of the retained row is still the stronger evidence class,
so no value is changed and no average is formed.

Sulfolane's 43.3 has no temperature attached. It sits between the dataset's 44 at
298.15 K and the Perricone thesis's 43 at 30 C, which is what a mildly
temperature-dependent constant should look like; it is recorded as corroboration
of the 43-44 neighbourhood, not as a replacement.

## The ethylene carbonate subtlety

The EC record (CID 7303) does cite Riddick, but the citation is attached to a
**purification** procedure, not to a measurement:

> "...purified ethylene carbonate for dielectric constant and dipole moment
> studies by fractional distillation at reduced pressure and fractional
> crystallizations from dry ethyl ether."
> - Formulations/Preparations, citing Riddick, J.A., W.B. Bunger, Sakano T.K.,
> *Techniques of Chemistry 4th ed., Volume II. Organic Solvents*, New York, NY:
> John Wiley and Sons, 1985, p. 989 (the record carries a second, p. 990,
> citation; the quoted sentence is verbatim from the cached response).

So the Riddick fourth edition is genuinely reachable through PubChem for EC - and
that page of it describes how to purify the sample **before** the dielectric
measurement. The number itself is not deposited. Anyone reading the manual's
wording as "EC's PubChem page contains the Riddick dielectric value" would be
misreading it; this note is the correction.

Two details were corrected after an adversarial read of the first draft of this
report: the handbook page is **989**, not 98, and the quoted text says "dry
ethyl ether". Both are checked against the cached PUG-View response, which is
why the quote is kept verbatim - a paraphrase that drifts on pages and reagents
is exactly the kind of error this probe exists to prevent.

## The actionable half: exact SpringerMaterials deep links

Nine of the fourteen records carry a **SpringerMaterials Properties** section
whose "Dielectric constant" entry is a hyperlink, not a value. That is the
pointer that makes the tier-3/tier-4 round cheap: the substance id in the URL is
the exact SpringerMaterials substance, so the user's existing Edge session can
open the dielectric facet directly instead of searching by name.

| Compound | SpringerMaterials substance | Deep link (dielectric facet) |
| --- | --- | --- |
| Ethylene carbonate | `smsid_kobmrheuldzdoegc` | searchTerm=ethylene+carbonate |
| Adiponitrile | `smsid_bohrfgfycqwosrfu` | searchTerm=hexanedinitrile |
| Glutaronitrile | `smsid_dxoupiddlfsvkcpq` | searchTerm=pentanedinitrile |
| 1,2-Dimethoxyethane | `smsid_ibjfqpwvdsaaexjv` | searchTerm=1,2-dimethoxy-ethane |
| Diglyme | `smsid_yobfvkfbtfofwznt` | searchTerm=2,5,8-trioxanonane |
| Triglyme | `smsid_yecdwnpudovxbdla` | searchTerm=2,5,8,11-tetraoxadodecane |
| Tetraglyme | `smsid_lbchugdajsjofeys` | searchTerm=tetraethylene glycol dimethyl ether |
| Sulfolane | `smsid_uwltlxdlrbexmdjg` | searchTerm=tetrahydrothiophene-S,S-dioxide |
| Acetonitrile | `smsid_qcpbsqjqhpizpjkl` | searchTerm=methylnitrile |

The full URLs, with the `propertyFacet=dielectric constant` parameter, are in the
evidence JSON under `springer_dielectric_links`. Crucially, **propylene
carbonate, vinylene carbonate, fluoroethylene carbonate, gamma-valerolactone and
3-methoxypropionitrile carry no SpringerMaterials pointer at all** - for those
five, PubChem offers no route into the closed database, so they still need the
institutional/print ladder.

## What this closes and what it does not

Closed:

- The tier-1 PubChem question is answered per compound instead of assumed. No
  future round needs to re-check the same fourteen records; the cache makes the
  answer reproducible without spending calls.
- Five compounds (PC, VC, FEC, GVL, MOPN) are now known to have **no** PubChem
  dielectric evidence, so the manual's expectation that "PC, glyme and EC can be
  solved in tiers 0-2" does not hold for PC.
- Nine exact SpringerMaterials substance ids are on record, which turns the
  restricted-database round into a lookup rather than a search.

Not closed - still open after this probe:

- The **FEC 78.4 / 102 / 107** spread, the **VC 126 vs 78-127** conflict and the
  new **GVL 36.1 vs 32 (thesis also gives 34)** conflict. PubChem has nothing for
  any of them.
- **MOPN** still has no GFN2-xTB feature row, so it cannot be fitted regardless of
  provenance.

## Budget and reproducibility

- PubChem was the only network source touched. Fourteen compounds cost three
  requests each the first time (InChIKey to CID, CID to InChIKey, PUG-View
  record), plus one name lookup, i.e. 56 calls, well inside the 500/hour ceiling.
- Re-running `python probes/g1plus_pubchem_probe.py` with the cache present
  spends **zero** calls and rewrites the same evidence JSON byte for byte.
- Every recorded value keeps its own citation string; nothing was averaged,
  promoted or dropped.
