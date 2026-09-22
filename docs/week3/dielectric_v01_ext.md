# Dielectric v0.1 High-Temperature Extension

The main `data/dielectric_v01.csv` is unchanged. This extension is a separate
evidence table and does not alter the 100-compound v0.1 training baseline.

## NIST Window

The extension selects P1 zero-frequency pure-component observations from
`313.15 K` through `323.15 K`, inclusive. This range is outside the original
v0.1 dielectric window and captures the available high-temperature NIST data.

- NIST observations: 205
- NIST InChIKeys: 46

## EC Literature Point

Ethylene carbonate is added as one manually curated literature row:

- InChIKey: `KMTRUDSVKNLOMY-UHFFFAOYSA-N`
- Temperature: `313.15 K` (40 C)
- Relative permittivity: `90.5`
- Frequency: `1 MHz`
- Property family: `frequency_dependent`
- Method: static dielectric constant by capacitance
- Uncertainty: article states `<1.5% relative`
- DOI: `10.1021/je050341y`
- Source: Chernyak, *J. Chem. Eng. Data* 2006, 51(2), 416-418, Table 1 p416
- Sample purity: `>99.9 mass%`
- Instrument: Agilent 4284A / 16452A

The EC value is not relabeled as zero-frequency, not extrapolated to other
temperatures, and not averaged with the separate values 89.78 or 90.36.

## Counts

- NIST keys: 46
- EC keys added: 1
- Total keys: 47
- Observations: 205 NIST + 1 EC = 206

## Limitation

EC is a single-source manual literature point. Its `single_source` flag is
intentional and prevents it from being treated as replicated evidence.
