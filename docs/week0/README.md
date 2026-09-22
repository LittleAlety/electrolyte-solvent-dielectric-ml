# Week 0 Deliverables

The first week is complete when the repository contains evidence for each
item below:

| Requirement | Deliverable | Verification |
|---|---|---|
| Reproducible ML environment | `environment.yml` | `conda env create -f environment.yml` |
| Repository ready for first push | Git metadata and initial commit | `git log -1` |
| ThermoML format understood | acquisition and parsing runbook | follow the commands in `thermoml/README.md` |
| First dielectric data batch | normalized CSV plus provenance | `thermoml/data_summary.md` |
| PNAS 2023 paper read | structured critical reading note | `literature/README.md` |
| User-provided PDF reading set | four page-checked literature notes | `literature/README.md` |
| LLM coding workflow configured | reviewed runbook and prompt templates | `llm/README.md` |

## Non-negotiable data rules

1. Keep raw source files unchanged.
2. Record source URL, retrieval time, and checksum for every batch.
3. Preserve the original property name, unit, temperature, frequency, and
   phase before converting values.
4. Treat static or low-frequency values separately from optical-frequency
   values.
5. Never silently convert units or discard duplicate records.
