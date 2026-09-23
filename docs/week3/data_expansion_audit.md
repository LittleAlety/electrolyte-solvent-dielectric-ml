# Data Expansion Audit for v0.2

## Decision

`data/dielectric_v02.csv` was created with **210 unique compounds**: the 100
unchanged v0.1 rows plus 110 NBS Circular 514 additions. The additions pass the
near-room, pure-liquid, structure, temperature, precision, and hazard/frequency
filters. Mixtures, frequency-dependent values, missing temperatures, and
low-precision text records remain excluded.

## Source inventory

The machine-readable audit is
`data/processed/data_expansion_source_audit.csv`. Key source limits:

### NIST and ChalkLab

- NIST local fallback: 205 XML documents, 91 dielectric source documents,
  11,646 observations, 103 all-temperature zero-frequency pure keys, and 100
  near-room pure keys.
- ChalkLab JSONLD repository:
  `https://github.com/chalklab/Dataset-NIST-TRC-JSONLD/tree/681a946669feaf6ccc13ba6e1de760385c57ce73`.
- ChalkLab license: CC0-1.0.
- Five pinned archive objects total 411,920,425 bytes and contain 122,403
  JSONLD entries.
- ChalkLab zero-frequency pure: 103 keys, all 100 v0.1 compounds overlap, and
  3 keys are new.
- Near-room new ChalkLab additions: 0.
- Adding various-frequency pure records would reach 161 keys, but those labels
  are not interchangeable with zero-frequency near-room training values.
- The broader component universe is 187 keys, still below 200.

### NBS Circular 514

- Maryott and Smith, NBS Circular 514 (1951), DOI `10.6028/nbs.circ.514`, is a
  public NIST PDF containing critically evaluated static dielectric constants
  for more than 800 pure liquids.
- PDF SHA256:
  `cb3fa9239fd977d7fa85389fbc219baea69667d5cc7c9e5382b09157fda40683`.
- Table pages 13-47 were manually extracted. Pages 13-32 supplied all 110 rows
  selected into v0.2; pages 33-47 remain a larger candidate pool for later
  expansion.
- The selected 110 rows contain 88 three-figure estimates and 22 four-figure
  estimates.
- Structures were resolved through PubChem with CACTUS fallback, canonicalized
  with RDKit, formula-checked against the source row, and deduplicated by
  InChIKey.
- Frequency-footnoted rows and reactive/hazardous motifs were excluded.

### Other sources

- ChemDataExtractor has 60,804 dielectric records and 11,054 compounds, but no
  independent structured temperature field and insufficient precision for
  direct labels. It is candidate-discovery material only.
- MNSOL is solvation-focused and has no verified bulk path to qualifying
  dielectric labels in this audit.
- VirtualChemistry has a public web presence but no audited bulk export,
  license/coverage proof, or direct v0.2 extraction path.
- SolvFunc-87 provides 87 compounds for relevance and family context, not
  dielectric training labels.
- RX-392 provides 392 redox molecules and is not a dielectric v0.2 source.
- The Chernyak ethylene carbonate point is a single 313.15 K, 1 MHz
  literature measurement and remains supplemental.
- The 308 ECW dataset remains unavailable with zero rows fabricated.

### Second-round manual-source investigation

- Landolt-Börnstein 2015, DOI `10.1007/978-3-662-48168-4`, has chapter
  metadata for at least 217 pure substances. It is closed, but it is a viable
  manual transcript candidate if each record passes the v0.2 eligibility rules.
- Landolt-Börnstein IV/17, DOI `10.1007/978-3-540-75506-7`, is a closed
  supplemental source with no audited machine-readable extraction path.
- The CRC Handbook Permittivity of Liquids official page is login/subscription
  gated. It is potentially sufficient but requires manual row-level
  verification and rights review.
- The DDBST no-data policy page defines an access/redistribution constraint; it
  is not a dataset.
- The DTU fluorescence dataset records fluorescence response, not a
  pure-component zero-frequency dielectric label, and is not usable for direct
  v0.2 training.
- The binary-solvent QSPR Figshare item `10.6084/m9.figshare.2802712` is
  mixture-focused and outside the pure-component v0.2 definition.
- The GitHub repository
  `https://github.com/MDMISC/Dielectric_constants_binary_mixtures` has no
  declared license and is binary-mixture-focused, so it cannot be used directly.

The second-round conclusion is unchanged for automation: the open-data ceiling
is 187 compounds, below 200. Landolt-Börnstein and CRC are the strongest manual
transcript candidates, but reaching 200 still depends on manual verification of
temperature, phase, frequency, structure, and rights.

## Label rules

A v0.2 compound is eligible only if it has:

1. A distinct canonical structure and InChIKey.
2. A pure-component phase assignment.
3. A near-room temperature, currently defined as 293.15-303.15 K.
4. Zero-frequency dielectric data, or an explicitly justified static-frequency
   protocol.
5. Traceable source metadata and uncertainty/quality notes.
6. No silent merging of mixture, frequency-dependent, or all-temperature-only
   records.

## Manual curation queue

The AL Round-1 longlist has 300 rows and the Top30 has 30 rows. They provide
candidate structures and families, but not validated dielectric observations.
The Landolt-Börnstein 2015 Crossref metadata query produces
`data/processed/landolt_boernstein_2015_pure_liquid_queue.csv` with 217
pure-substance chapter entries. This file contains bibliographic identifiers
only: no dielectric value, temperature, phase, SMILES, or InChIKey has been
transcribed, and none of these rows enters v0.2.
The initial 100-compound expansion target is satisfied by the open NBS
Circular 514 path. The remaining closed-source queue is now used for later
expansion, cross-checks, and coverage rather than the Milestone 2 size blocker.

## Anchor cross-check

`data/processed/anchor_crosscheck.csv` holds one row per `(anchor, evidence
source)` pair for the seven v0.2 anchors across six in-repo sources: 23 rows of
13 `agree`, 3 `disagree`, 6 `not_comparable`, and 1 `no_data`.

Comparability is decided before agreement. A value measured at a different
temperature or frequency is `not_comparable` rather than scored, so a 1 MHz
datum is never matched against a static reference and a 293.15 K datum is never
matched against a 298.15 K one. Nothing is averaged and no side is chosen: an
anchor whose sources disagree keeps every disagreeing row and is marked
`promotion_blocked`.

Results by anchor:

- **Methanol is `promotion_blocked`.** The spot check (`32.72`) and the NBS 514
  transcription (`32.63`) agree with the `32.6` reference, but the promoted v0.1
  and v0.2 value `33.6` is off by `1.0` at tolerance `0.2`, and Chodera gives
  `33.1`. The Week 1 spot check passes while the promoted value does not match
  the reference. Seven rows attributed to pure methanol at 298.15 K from
  `10.1021/je060248p` span `32.72-39.25`, which is implausible for one pure
  solvent and is the likely cause.
- **Benzene agrees** from NBS 514 and v0.2 (`2.284` at 293.15 K). All 45 of its
  NIST zero-frequency rows are binary mixtures, so its near-room pure value
  rests on a single source.
- **Acetonitrile** agrees at 1 MHz (`35.88`), but its v0.2 NBS 514 entry
  (`37.5` static at 293.15 K) is `not_comparable` to the 1 MHz / 298.15 K
  reference.
- **DMC and DEC agree** from up to four sources. The DMC reference `3.09` sits
  `0.044` below both v0.1 and Chodera, at the edge of its `0.05` tolerance.
- **Ethylene carbonate** rests on one manual source at 313.15 K / 1 MHz.
- **Propylene carbonate** is `no_data`: re-verified against every in-repo
  artifact, it appears nowhere.

## Gate flags and provenance

`nbs514_circular_514` was used by all 110 NBS rows while being absent from
`GATE_FLAGS`. No check compared a dataset's flags against the enum, so the drift
was invisible. The label is now registered along with `crosscheck_only`, the
v0.2 verifier checks every used label against the enum, and
`tests/test_gate_flag_enum.py` guards the vocabulary against recurrence.

`closed_source` and `non_redistributable` remain dedicated columns in
`docs/week3/manual_dielectric_entry_schema.md` and are deliberately not gate
flags.

The NBS Circular 514 redistribution status stays `unclear` until a copyright
determination is recorded in `data/processed/data_expansion_source_audit.csv`.
A US Government publication is usually public domain, but that is not assumed
here.

## Deliverables

- `probes/data_expansion_summary.json`
- `data/dielectric_v02.csv`
- `probes/dielectric_v02_summary.json`
- `data/processed/data_expansion_source_audit.csv`
- `data/processed/landolt_boernstein_2015_pure_liquid_queue.csv`
- `data/processed/nbs514_structure_candidates.csv`
- `data/processed/anchor_crosscheck.csv`
- `probes/anchor_crosscheck_summary.json`
- `reports/milestone_2.md`
- `docs/week3/manual_dielectric_entry_schema.md`
