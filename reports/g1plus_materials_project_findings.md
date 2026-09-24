# Materials Project and CatalystHub: are they dielectric sources for this dataset?

**Date:** 2026-09-24
**Probe:** `probes/g1plus_materials_project_probe.py`
**Evidence:** `probes/g1plus_materials_project_evidence.json` (sha256
`9f8837b152d6546a904a48364f106897ffa72019f39a74b78ff135b8ef60137a`; raw responses cached
under `data/external/g1plus/materials_project/`, git-ignored)
**Opened with:** plain HTTPS through `urllib`, authenticated with the caller's own
`X-API-KEY`. The key is read from the git-ignored `config/materials_project_key.txt`; it is
never printed and never written into the evidence. No browser session is involved.

## Why these two were checked

Both were offered as alternative data routes after the SpringerMaterials interactive view
became unavailable. Neither had been tested, and "we could not open the website" is not the
same finding as "the database does not hold this data", so each was checked on its own terms.

## Materials Project

The question is narrow: does the collection hold these molecules at all? It is worth asking
precisely because the Materials Project *does* carry dielectric information - the summary
endpoint exposes `e_total`, `e_ionic`, `e_electronic` and the refractive index `n` from DFPT.
The catch is scope: the collection is built from inorganic crystals.

| Group | Queries | With entries |
| --- | --- | --- |
| Positive control (SiO2) | 1 | **yes** - 322 matching documents, with populated `e_total` / `n` (`control_status = ok`) |
| G1+ targets | 14 | **0** |

All fourteen targets return `total_doc = 0` from a **successful** query
(`summary.targets_confirmed_empty`; the summary keeps a separate
`targets_inconclusive` list, and it is empty here): EC (C3H4O3), PC (C4H6O3),
VC (C3H2O3), FEC (C3H3FO3), GVL (C5H8O2), MOPN (C4H7NO), adiponitrile (C6H8N2),
glutaronitrile (C5H6N2), DME (C4H10O2), diglyme (C6H14O3), triglyme (C8H18O4),
tetraglyme (C10H22O5), sulfolane (C4H8O2S) and acetonitrile (C2H3N).

The control is what makes the empty result readable. If the key, the endpoint or the field
names were wrong, SiO2 would be empty too. It is not, so the negative is about the scope of
the collection rather than about a broken query.

**Scope of this result.** The probe searches by **molecular formula only**, and the
Materials Project has no substance-identity gate of the kind the PubChem and WebBook probes
apply. What is demonstrated is therefore that **no record exists for any of these fourteen
formulas**, not that a future chemical-identity match is impossible. If a formula ever does
return a hit, that hit must be identified structurally before it is attributed to a target;
a formula is not an identity. The same caveat applies to reading the table above.

**Conclusion:** the Materials Project cannot source a dielectric constant for these molecular
liquids. Its dielectric tensors are computed for the solid crystals it holds, which is a
different physical quantity for a different phase; even if a molecular crystal of one of these
compounds appeared, a DFPT value for the crystal would not be interchangeable with the
experimental liquid permittivity this dataset records. **No value is imported.**

## CatalystHub

The stored key (`config/catalysthub_key.txt`, git-ignored) was kept, but no reachable
documented API endpoint could be confirmed from this environment:

| Host | Result |
| --- | --- |
| `catalysthub.ai` | resolves (3.33.130.190), HTTPS request times out |
| `www.catalysthub.ai` | resolves (15.197.148.33), HTTPS request times out |
| `api.catalysthub.ai` | does not resolve |
| `catalysthub.org` | resolves, but is a different site and fails TLS certificate validation |

This is recorded as **unverified**, not as "CatalystHub has no such data". The distinction
matters: the source has not been shown to be empty, it has been shown to be inaccessible from
here. If a documented endpoint or an API base URL becomes available, the check can be redone
the same way the Materials Project one was.

## What this changes

- Nothing in the dataset. **No row, number, `model_ready` flag or `conflict_status` changes**;
  `data/dielectric_v03.csv` stays at
  `f5256d164c814030a4b986db6c878f1d64edb2b4f91cf39af3a75ffeaeac853c`.
- Appendix J gains a recorded outcome for both sources, so the next round does not re-litigate
  them: the Materials Project is out of scope, CatalystHub is pending a usable endpoint.
- The five targets with no tier-1 or tier-2 primary value (PC, VC, FEC, GVL, MOPN) still need
  tier 3-4: the fourth edition of Riddick on paper, the CRC "Permittivity of Liquids" table, or
  Reaxys / SciFinder-n / DIPPR 801 through a library subscription.

## Cost

First pass: **15 Materials Project API calls** (1 control + 14 targets), inside the 500/hour
ceiling. Re-runs read the cache and cost **0 calls**. The CatalystHub probing was 5 DNS/HTTPS
attempts and is not an API usage.
