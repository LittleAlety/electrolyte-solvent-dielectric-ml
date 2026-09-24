# G1+ crawl round 2: three read-only agents, four adjudications, zero new static values

**Date:** 2026-09-24
**Scope:** Appendix J tiers 1-2 (free programmatic sources and free
battery-domain compilations) applied to the modern battery-solvent candidate
queue, plus the two open conflict tickets (VC, FEC)
**Artifact:** `probes/g1plus_crawl_round2_evidence.json`
**Verdict:** the round produced **no new ingestable static permittivity**, and
that is the correct outcome: three agent claims were rejected after local
adjudication, one is blocked on publisher access and two are corroborations.

## 1. What was dispatched, and at what cost

| Agent | Assignment | HTTP calls |
|---|---|---:|
| Kant | vinylene carbonate and fluoroethylene carbonate conflict closure | 12 |
| Averroes | sulfones, sulfoxides and hydrofluoroethers | 15 |
| Aquinas | nitriles, carbonates and fluorinated esters | 12 |

**39 external calls** for the round, against the 500/hour ceiling. All three
agents were read-only: no agent wrote to the repository, and every agent claim
was re-checked against a tracked local cache before being accepted. Two
OpenAlex requests returned HTTP 429; no retry storm was issued.

## 2. The three rejected claims

### 2.1 isobutyronitrile - frequency-gated, not a static value

The crawl surfaced `nbs514:p20:009`: 20.4 at 297.15 K. The transcript line
also carries `f=3.6x10^8 cycles/sec`. The rule that excludes it is the **NBS
import rule**, not a project-wide zero-frequency contract: the manual schema
also admits an explicitly justified `static_low_frequency` protocol (which is
how the 1 MHz EC row entered), while the NBS path rejects *any* row carrying a
frequency note (`scripts/resolve_nbs514_structures.py`,
`scripts/build_dielectric_v02.py`). Measured, not assumed: **all 127**
frequency-noted NBS rows are outside the dataset, and **all 110** inherited NBS
rows inside it carry the `zero_frequency` gate. The neighbour `p20:008`
butyronitrile (20.3 at 294.15 K, same frequency) is the precedent: it was
skipped in favour of the independent primary value 22.0 at 298.15 K. Details:
`reports/nbs514_frequency_gate_audit.md`.

### 2.2 methyl trifluoromethyl ether - the deposited compound is not the candidate

The crawl read ThermoML `10.1021/je7000446` as an open primary for queue
candidate `modern:024` at 9.28 / 302.8 K. The local XML does not support that
reading:

- the citation title names an ether, "trifluoromethyl methyl ether (HFE 143a)";
- the **deposited compound 1** is `C2H3F3`, `UJPMYEOUBPIPHQ-UHFFFAOYSA-N`,
  common names "1,1,1-trifluoroethane / CFC 143A / Freon 143a / R-143a". That
  is an HFC, and it contains no oxygen, so it is not the named ether;
- the record's own abstract bounds the measurements to **1.5-31.6 MPa and
  303-383 K**. The 14 near-303 K rows run from 1.6 MPa (9.28) to 30.7 MPa
  (10.51) at 0.06 MHz. **There is no ambient-pressure value.**

Both reasons independently disqualify the row. The dataset has no pressure
column, and a compressed-liquid measurement is a different observable from an
ambient static permittivity. `modern:024` therefore stays restricted-only. The
identity conflict sits upstream in the NIST deposition, not in this
repository's extractor, which faithfully carried the deposited compound.

### 2.3 The remaining candidates - restricted-only, not retired

No open primary value was found this round for succinonitrile or
cyclopentanecarbonitrile, nor for the seven sulfone/sulfoxide candidates, nor
for the hydrofluoroether family. Each keeps its named primary lead
(Nakazawa 2001, Marchionni 1999, Casteel 1974, Kolosnitsyn 1991, Egorov 1978,
Markarian 2011, and so on). **None was recorded as "no data"**: a metadata-only
search that finds no open full text is an access result.

## 3. The two corroborations

| Item | Result |
|---|---|
| propanenitrile | NBS 514 `p17:014` = 27.2 at 293.15 K, which is exactly the row the dataset already carries under that record id. Value-level corroboration; NBS 514 does not list Vuks, so they are not proven to share a measurement. |
| FEC 78.40 leg | ECW-308 supplement line 5879 reads `C3H3FO3 17.30 210.00/249.50 4.10 78.40 5.00 130.00 [16, 42]`. The two upstream relays are now named (Flamme et al.; Deng et al., *Energy Storage Materials*) but were not retrieved, so the leg stays a compilation relay. |

## 4. What this does not close

- **Vinylene carbonate stays `conflict_open`.** The 1966 abstract states only
  that the dielectric constant was measured; it carries no number, temperature,
  table or digit count. Semantic Scholar reports the PDF as CLOSED and NBS
  Circular 514 does not contain the compound. This is a publisher-access block,
  and the row is not promoted to primary.
- **FEC stays out of the model-ready set.** The 78.4 and 107 legs now have
  named upstream relays; the 102 leg's relay to Xie et al. 2023
  (`10.1002/anie.202216934`) was reported by an agent but not re-verified
  against a tracked cache, and no evidence establishes it is an original
  measurement. Three values at unstated or nominal-25 C conditions are not a
  same-condition comparison.
- **Tier 3-4 access** is untouched: the printed and subscription sources remain
  blocked rather than empty.

## 5. Dataset impact

**None.** `data/dielectric_v03.csv` is still 246 rows x 38 columns with
canonical SHA-256
`57387b98f899c6c0eff12716cc5b754f65d2ee0edd5523330af049ddded26fab`. No value,
temperature, evidence level, `model_ready` flag or conflict status moved. The
round's product is adjudication: three crawl hits that would each have corrupted
the dataset in a different way (a dispersion measurement, a wrong-compound
identity, and a compressed-liquid condition) are now documented as rejected
with their reasons.

## 6. Honest boundary

"Not found in this budget" is not "no value exists". Most candidates were
searched through Crossref, OpenAlex and Europe PMC **metadata**; only the two
open-access full texts that were fetched, plus the tracked local caches, were
read in full.
