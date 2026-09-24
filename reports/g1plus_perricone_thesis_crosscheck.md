# G1+ cross-check: the Perricone 2011 thesis against the v0.3.3 dataset

**Date:** 2026-09-24
**Evidence file:** `probes/g1plus_perricone_thesis_crosscheck.json`
**Source:** Perricone, E., *Mise au point d'electrolytes innovants et
performants pour supercondensateurs*, PhD thesis, Universite de Grenoble, 2011
(NNT `2011GRENI032`, HAL `tel-00630049`, open access, 214 pages)

The thesis was retrieved for the 3-methoxypropionitrile question (see
`reports/g1plus_mopn_thesis_findings.md`). Its Tableaux 5-8 turned out to be a
free, citable cross-check source for several compounds already in the dataset:
they are captioned "a 25 C (sauf precision contraire)" and carry per-value
reference letters, which is the evidence discipline the dataset asks for.

## Cross-check table

| Compound | Dataset (v0.3.3) | Thesis | Delta | Verdict |
| --- | --- | --- | --- | --- |
| Acetonitrile | 37.5 @ 293.15 K (NBS 514) | 36 @ 25 C (Tableau 5, ref [43]) | -1.5 | consistent with the temperature difference |
| Sulfolane | 44 @ 298.15 K (TCA 2012) | 43 @ 30 C (Tableau 5 a = ref [43]; Tableau 7 a = ref [4]) | -1.0 | consistent |
| **Propylene carbonate** | **64.9 @ 298.15 K (Simeral 1970)** | **65 @ 25 C (Tableaux 5, 8)** | **+0.1** | **corroborated** |
| Ethylene carbonate | 90.5 @ 313.15 K (Chernyak 2006) | 90 @ 25 C (Tableau 5, ref [49]) | -0.5 | consistent; the thesis temperature implies a supercooled sample (mp 36 C) |
| Ethyl acetate | 6.02 @ 298.15 K (NBS 514) | 6 @ 25 C (Tableau 8) | -0.02 | corroborated |
| Ethyl methyl carbonate | 2.96 @ 298.15 K (review table) | 3 @ 25 C (Tableau 8) | +0.04 | corroborated |
| **gamma-Valerolactone** | **36.1 @ 298.15 K (iScience 2026 review)** | **32 @ 25 C (Tableau 8, ref [87])** | **-4.1** | **CONFLICT OPEN** |
| 3-Methoxypropionitrile | 36.0 @ 298.15 K (ECW-308) | 36 (Tableau 12) | 0.0 | value corroborated, temperature unstated |

## What the pass establishes

- The **PC backfill is corroborated by a third document**: the thesis lists 65 at
  25 C against the 64.9 at 298.15 K taken from Simeral & Amey (1970). That
  removes the last doubt that 64.9 is an outlier transcription.
- **EC 90.5 at 313.15 K** is compatible with the thesis's 90, and the thesis's
  "25 C" annotation is itself evidence that this number circulates in the
  literature with a temperature that cannot be physically realised for a solid
  that melts at 36 C. The dataset keeps the 313.15 K row and flags it
  `temperature_band=extended_temperature`.
- The nitrile/ester values in the dataset agree with an independent document to
  rounding.

## The one conflict: gamma-valerolactone

Two secondary documents disagree by 4.1 permittivity units:

| Side | Value | Temperature | Document | Class |
| --- | --- | --- | --- | --- |
| Dataset | 36.1 | 298.15 K | iScience 2026 review table, DOI 10.1016/j.isci.2026.115778 | open-access review table |
| Thesis | 32 | 25 C | Perricone 2011, Tableau 8, source "d = ref [87]" | relayed in a thesis |

Neither side is a traced primary measurement, and 12.7% is far outside the
dataset's rounding-level agreement band. The dataset discipline applies:

- the two values are **not averaged**;
- the dataset value is **not swapped** for the thesis value - a thesis relay is
  not a higher evidence class than a review table;
- the disagreement is opened as a **conflict ticket** for primary review, and
  the immediate next step is to trace reference [87] of the thesis and the
  primary source behind the iScience table.

Promoting this ticket into the dataset's `conflict_status` column is a data
revision (it changes the frozen hash and every probe that records
`dataset_sha256`). It is **not** promoted in the v0.3.5 revision: v0.3.5 applies
only the 3-methoxypropionitrile provenance patch, so this disagreement is
recorded as an open ticket in `reports/decisions_log.md` and the dataset's
numeric value and `conflict_status` column are left untouched pending a traced
primary measurement.

## Method and limits

- Text was extracted with `pypdf` (214 pages, 341,433 characters) from the
  open-access PDF; Tableaux 5, 7, 8 and 12 were read directly, and the
  extraction was checked against the surrounding prose, which restates several
  values (for example "epsilon_r = 43 contre epsilon_r = 90 pour l'EC").
- A thesis is a **document**, not an independent measurement lineage: where the
  thesis and a dataset row share an upstream reference they are one chain, not
  two. None of these eight comparisons is counted as an independent
  cross-check in the paper's cross-source section.
- Only numeric facts and their citation letters are recorded; the PDF is not
  redistributed.
