# Code and Data Availability

The complete dataset, all build scripts, probe scripts, verifiers, and
benchmark outputs are deposited in a public GitHub repository:

**Repository:** https://github.com/[repository-name]
**Release:** v1.0 (immutable)
**DOI:** https://doi.org/10.5281/zenodo.[XXXXX]

## Repository structure

`
├── data/
│   ├── dielectric_v01.csv          # v0.1: 45 ThermoML compounds
│   ├── dielectric_v02.csv          # v0.2: 210 NBS + ThermoML compounds
│   ├── dielectric_v03.csv          # v0.3: 243 compounds (candidate)
│   ├── dielectric_v031.csv         # v0.3.1: G1 revision
│   ├── processed/                  # Derived data (physical features, predictions)
│   └── restricted/                 # Non-redistributable cross-check evidence
├── scripts/
│   ├── build_dielectric_v03.py     # v0.3 deterministic builder
│   ├── verify_dielectric_v03.py    # v0.3 independent verifier (passes 6/6)
│   ├── run_xtb_physical_features.py
│   └── build_dataset_v01.py, build_dielectric_v02.py, ...
├── probes/
│   ├── dielectric_representation_ablation.py  # Main XGBoost benchmark
│   ├── dielectric_mlp_probe.py                # MLP neural probe
│   ├── dielectric_mlp_calibration_probe.py    # Pre-registered calibration probe
│   ├── dielectric_chemprop_baseline.py        # Chemprop D-MPNN baseline
│   ├── g2_domain_gap_test.py                  # External domain-gap test
│   └── artifacts/                             # Figures and plots
├── reports/
│   ├── decisions_log.md                       # Full decision record
│   └── g1_data_gate_review.md                 # G1 conflict list
├── paper/
│   ├── outline.md
│   ├── abstract_and_intro.md
│   ├── methods_data_records.md
│   ├── technical_validation.md
│   ├── benchmark_and_figures.md
│   └── code_and_data.md
├── src/electrolyte_ml/                        # Python package
├── tests/                                     # CI test suite
├── environment.yml                            # Conda environment
└── pyproject.toml
`

## Software dependencies

- Python 3.12
- RDKit 2024.09 (structure standardization, Morgan fingerprints, 2D descriptors)
- XGBoost 2.1 (primary frozen model)
- scikit-learn 1.5 (cross-validation, MLP, metrics)
- GFN2-xTB 6.7.1 (physical features)
- Chemprop 2.1.0 (D-MPNN baseline, isolated environment)
- NumPy, SciPy, pandas, matplotlib, pytest

## Reproducibility

Every dataset version is built by a deterministic script and verified by an
independent verifier that re-derives all metrics from the committed outputs.
All probe scripts accept explicit command-line arguments for input and output
paths. The conda environment is frozen in environment.yml.

Verifiers run in CI (GitHub Actions, Ubuntu 22.04) on every commit:

`ash
# Full verification suite
pytest tests/ -v

# Individual dataset verifiers
python scripts/verify_dielectric_v03.py  # 6/6 checks
python scripts/verify_export_manifests.py
`

## License

The dataset and code are released under the Creative Commons Attribution 4.0
International (CC BY 4.0) license, except where individual source records
carry more restrictive licenses (CC BY-NC, CC BY-NC-ND) as noted in the
source_license and redistribution_conditions columns of each row.
