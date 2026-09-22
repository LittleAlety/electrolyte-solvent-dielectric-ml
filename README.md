# Electrolyte Solvent Dielectric ML

Week 0/1/2 bootstrap for a human-in-the-loop machine learning project on the
dielectric constants and related properties of electrolyte solvents.

## Scope

- Reproducible Python environment for RDKit, scikit-learn, XGBoost, pandas,
  and matplotlib.
- A documented ThermoML acquisition and parsing workflow.
- A structured reading note for the Kim et al. PNAS 2023 paper.
- A lightweight LLM-assisted development workflow with review gates.
- P0 environment and molecular-fingerprint sanity checks.
- P1 ThermoML dielectric-data census and feasibility gate.
- Week 1 closure with source provenance, spot checks, a documented 308-data
  gap, and experimental viscosity integration.
- P2 Batt-P30K fingerprint-to-XGBoost baseline, including its negative R2 gate.
- Week 3 Chodera cross-check and high-temperature dielectric extension.

## Quick start

```powershell
conda env create -f environment.yml
conda activate electrolyte-ml
python scripts/verify_week0.py
```

The week's acceptance criteria and artifact map are documented in
`docs/week0/README.md`.

Week 1 probe commands and outputs are documented in `docs/week1/README.md`.
The unified property schema is in `docs/week1/data_schema.md`.
Week 3 extension documentation is in `docs/week3/dielectric_v01_ext.md`.
Viscosity baseline documentation is in `docs/week3/viscosity_baseline.md`.

## Repository layout

```text
data/                 Downloaded and processed datasets
docs/                 Week 0 notes, decisions, and runbooks
notebooks/            Exploratory analysis
scripts/              User-facing setup and verification commands
src/electrolyte_ml/   Reusable Python package
tests/                Automated tests
```
