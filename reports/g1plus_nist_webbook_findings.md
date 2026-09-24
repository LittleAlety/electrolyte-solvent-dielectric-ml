# G1+ tier 1, second half: what the NIST WebBook actually holds

**Date:** 2026-09-24
**Probe:** `probes/g1plus_nist_webbook_probe.py`
**Evidence:** `probes/g1plus_nist_webbook_evidence.json` (sha256
`ff56c4f16cec86fd5328dc147c964d57c1b25afb7c0c92411ef3c95885d1fdd4`; raw HTML cached under
`data/external/g1plus/webbook/`, git-ignored)
**Opened with:** plain HTTPS through `urllib` (NIST Chemistry WebBook, SRD 69). No browser
session and no login is involved, so this source carries no access restriction.

## The claim under test

Appendix J ranks the NIST WebBook as tier 1 and states that "some substances carry a
dielectric constant and a refractive index". The first G1+ pass queried the CAS pages of ten
targets, received HTTP 200 from each, and reported no dielectric field. That result is
reproduced here, but a target-only negative cannot distinguish two very different worlds:

1. the WebBook does not model dielectric data at all, or
2. these particular lookups failed to surface a field that other records do carry.

So the check was rebuilt with an identity gate and with positive controls.

## Method

1. **Accepted query surface.** Compounds are found with `Name=` and each hit is addressed by
   `ID=`. The `InChIKey=` form is recorded for the record only; the site answers it with HTTP
   400 (`method.unsupported_query_form` in the evidence JSON).
2. **Identity gate.** Each compound page embeds its own `inChIKey` inside a JSON-LD block, so
   a hit is accepted only when that embedded key equals the dataset InChIKey. A name collision
   can therefore never be filed as evidence. The gate demonstrably does work: `water` returns
   seven candidate ids and six of them are rejected before `C7732185` matches.
3. **Property test.** Case-insensitive counts of `dielectric`, `permittivity`, `epsilon`
   and the symbol `ε` over the whole page, not only over its section headings. The
   vocabulary is deliberately wide because the claim under test is a negative.
4. **Positive controls.** Water, methanol, ethanol and acetone - substances whose dielectric
   constants are not in dispute - are run through the identical path. They are used to test the
   data model and are never added to the dataset.

## Result

| Group | Records resolved (InChIKey match) | Records exposing a dielectric facet |
| --- | --- | --- |
| G1+ targets | **13 / 14** | **0 / 14** |
| Positive controls | **4 / 4** | **0 / 4** |

The controls are the load-bearing part of the result. The property test is deliberately
generous - it counts `dielectric`, `permittivity`, `epsilon` and the symbol `ε`, so a page
that spelled the property in any of those ways would register a hit. Water, methanol, ethanol
and acetone are the strongest expected positives for a surface that does carry this property;
all four are empty, which is strong support for a structural absence on the queried surface
rather than a formal proof about the whole site.

**Scope of that conclusion, stated plainly.** What is demonstrated is that **no dielectric
evidence appears on the WebBook surfaces this probe queried** - the compound pages reached via
`Name=` and `ID=`, across 18 records in total - and that the absence is not an artefact of the
lookup, since the controls are populated with other data and the identity gate passes. What is
*not* demonstrated is that no WebBook entry point anywhere (an unqueried `Mask` variant, a
JavaScript-rendered panel, a sub-page not linked from the compound page) could ever carry such
a quantity. The honest form of the conclusion is therefore: **the WebBook is not usable as a
dielectric source for this dataset**, which is a statement about this probe's coverage rather
than a claim about the whole site.

The one unresolved target is fluoroethylene carbonate: the name search returns no candidate at
all, and the CAS number 114435-02-8 answers `Registry Number Not Found`. Note the provenance
of that CAS sentence: the `Registry Number Not Found` response for FEC was captured in the
**first tier-1 pass** (`g1plus_tier1_findings.md` and its raw cache), not by this probe, whose
FEC name search simply returns no candidates. Both observations point the same way; they are
recorded as two separate checks rather than merged into one.

## Identity corroboration as a by-product

Every resolved page yields its own CAS registry number, read from the page rather than
hard-coded. Nine of the thirteen also appear in `g1plus_tier1_findings.md`, and in all nine
the two numbers agree exactly:

| Compound | WebBook CAS | `g1plus_tier1_findings.md` CAS |
| --- | --- | --- |
| Ethylene carbonate | 96-49-1 | 96-49-1 |
| Propylene carbonate | 108-32-7 | 108-32-7 |
| Vinylene carbonate | 872-36-6 | 872-36-6 |
| 3-Methoxypropionitrile | 110-67-8 | 110-67-8 |
| Adiponitrile | 111-69-3 | 111-69-3 |
| Glutaronitrile | 544-13-8 | 544-13-8 |
| Diglyme | 111-96-6 | 111-96-6 |
| Triglyme | 112-49-2 | 112-49-2 |
| Tetraglyme | 143-24-8 | 143-24-8 |

The remaining four - gamma-valerolactone (108-29-2), 1,2-dimethoxyethane (110-71-4), sulfolane
(126-33-0) and acetonitrile (75-05-8) - were added to the target set after that first pass and
have no second CAS list in this repository to compare against, so their numbers are recorded as
observed and are **not** claimed as corroborated here. The ninth tier-1 target, FEC, is the one
the WebBook does not hold at all.

An earlier draft of this section claimed all thirteen agreed with the prior report. Only nine
can be checked that way; the claim was corrected rather than left standing, since this document
is meant to be an auditable record of what was verified and what was merely observed.

## What this changes

- The earlier tier-1 line item ("all ten targets carry no dielectric field") was correct but
  unfalsifiable. It is now a claim backed by a populated positive control, a working identity
  gate and a four-spelling property test, and it covers GVL and the two cross-check anchors
  (sulfolane, acetonitrile) as well; MOPN was already in the first pass.
- Appendix J's parenthetical that the WebBook holds dielectric constants is not supported by
  anything this probe could reach; the manual line now records the outcome and the tier-1b
  results instead of standing as an unfinished lead.
- Nothing in this result is a new data value. **No row, number, `model_ready` flag or
  `conflict_status` changes**, and the dataset hash is therefore untouched by this probe.

## What is still open

Tier 1 is now closed on both halves: PubChem holds two citable compilation numbers (sulfolane,
acetonitrile - see `g1plus_pubchem_findings.md`) and the WebBook yielded none on any surface
this probe could reach. The five targets
with no tier-1 evidence at all - **PC, VC, FEC, GVL, MOPN** - still need tier 3-4: the fourth
edition of Riddick on paper, the CRC "Permittivity of Liquids" table, or Reaxys / SciFinder-n /
DIPPR 801 through a library subscription. For the VC and FEC conflicts the print Riddick route
is the only identified path to a primary value.

## Cost

First pass: **53 HTTP requests** (18 name searches plus 34 compound pages plus the one recorded
400), against a budget of 500 per hour. Re-runs read the cache and cost **0 requests**; the
evidence JSON was verified byte-identical across a second run
(`ff56c4f16cec86fd5328dc147c964d57c1b25afb7c0c92411ef3c95885d1fdd4`).
