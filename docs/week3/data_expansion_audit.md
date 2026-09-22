# Data Expansion Audit for v0.2

## Decision

`data/dielectric_v02.csv` was **not created**. Current v0.1 contains 100 unique
compound keys. No audited automatic source path reaches the 200-compound
minimum, and padding with mixtures, frequency-dependent values, missing
temperatures, or low-precision text records is not allowed.

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
The next work is to search the literature, handbooks, and primary sources for
at least 100 additional qualifying compounds and record the required metadata.

## Deliverables

- `probes/data_expansion_summary.json`
- `data/processed/data_expansion_source_audit.csv`
- `reports/milestone_2.md`
- `docs/week3/manual_dielectric_entry_schema.md`
