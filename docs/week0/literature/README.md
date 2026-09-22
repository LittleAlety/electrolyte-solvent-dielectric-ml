# Week 0 Literature Index

The user-provided PDFs were read in four independent workstreams. Each note
separates source claims from project inferences and records page-level checks.

| Note | Papers covered | Evidence status |
|---|---|---|
| `pnas_2023_kim.md` | Kim et al., PNAS 2023 | Full 8-page main article; SI absent |
| `reviews_battery_ai.md` | Gao et al. 2025; Zhan et al. 2026; Chen et al. 2021 | Full main articles; figures checked where needed |
| `reviews_electrolyte_ai.md` | Lombardo et al. 2022; Chen et al. 2024 | Full main articles; one SI absent |
| `data_and_active_learning.md` | Ma et al. 2025; StreaMD 2024 | Full main articles; SI absent |

## Important evidence corrections

- The file named `s13321-024-00918-w.pdf` is the StreaMD software paper, not
  the dielectric/property dataset paper implied by the earlier research
  outline. The note is written from the actual content and discloses this.
- The active-learning paper reports six rounds of expected-improvement
  acquisition and a seventh greedy campaign. These should not be described as
  seven identical active-learning rounds.
- The active-learning paper's approximate counts for the candidate pool use
  different filtering stages. Raw database records, unique solvents, expanded
  electrolyte combinations, and the final unlabeled pool must be counted
  separately.

## Project implications

The common conclusions are consistent with the Week 0 dataset rules:

1. Preserve source, units, temperature, frequency, phase, and composition.
2. Separate static/low-frequency and optical-frequency targets.
3. Use grouped or temporal validation when random splitting would leak.
4. Start with interpretable small-data baselines before considering GNNs.
5. Report uncertainty and compare active learning against random and greedy
   selection under the same budget.
