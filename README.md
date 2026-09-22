# Electrolyte Solvent Dielectric ML

Week 0/1 bootstrap for a human-in-the-loop machine learning project on the
dielectric constants of electrolyte solvents.

## Scope

- Reproducible Python environment for RDKit, scikit-learn, XGBoost, pandas,
  and matplotlib.
- A documented ThermoML acquisition and parsing workflow.
- A structured reading note for the Kim et al. PNAS 2023 paper.
- A lightweight LLM-assisted development workflow with review gates.
- P0 environment and molecular-fingerprint sanity checks.
- P1 ThermoML dielectric-data census and feasibility gate.

## Quick start

```powershell
conda env create -f environment.yml
conda activate electrolyte-ml
python scripts/verify_week0.py
```

The week's acceptance criteria and artifact map are documented in
`docs/week0/README.md`.

Week 1 probe commands and outputs are documented in `docs/week1/README.md`.

## Repository layout

```text
data/                 Downloaded and processed datasets
docs/                 Week 0 notes, decisions, and runbooks
notebooks/            Exploratory analysis
scripts/              User-facing setup and verification commands
src/electrolyte_ml/   Reusable Python package
tests/                Automated tests
```
