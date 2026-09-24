# Code and Data Availability

The complete dataset, all build scripts, probe scripts, verifiers, and
benchmark outputs are deposited in a public GitHub repository:

**Repository:** https://github.com/[repository-name]
**Release:** v0.3.3 (candidate; v1.0 tag will be applied only after the Appendix I freeze conditions are met)
**DOI:** https://doi.org/10.5281/zenodo.[XXXXX]

## Repository structure

```text
├── data/
│   ├── dielectric_v01.csv           # v0.1: 100 ThermoML compounds
│   ├── dielectric_v02.csv           # v0.2: 210 NBS + ThermoML compounds
│   ├── dielectric_v03.csv           # v0.3.3: 246 compounds (current candidate)
│   ├── dielectric_v031.csv          # v0.3.1: G1 revision (243, historical)
│   ├── dielectric_v032.csv          # v0.3.2: PC+EC freeze (245, historical)
│   ├── processed/
│   │   ├── dielectric_v03_exclusions.csv           # 5-row curated exclusion list
│   │   ├── dielectric_v03_provenance_patches.csv   # 30 reproducible patches
│   └── restricted/                  # Non-redistributable cross-check evidence
├── scripts/
│   ├── build_dielectric_v03.py      # v0.3/v0.3.3 deterministic builder
│   ├── verify_dielectric_v03.py     # v0.3.3 verifier (7/7 checks, 246 rows)
│   ├── verify_dielectric_v032.py    # v0.3.2 verifier (7/7 checks, 245 rows)
│   ├── build_paper_full_draft.py    # Assembles paper/full_draft.md from the sections
│   ├── check_paper_artifact_consistency.py  # Paper claims vs. frozen artifacts
│   ├── run_xtb_physical_features.py
│   └── build_dataset_v01.py, build_dielectric_v02.py, ...
├── probes/
│   ├── dielectric_representation_ablation.py    # Main XGBoost benchmark
│   ├── dielectric_mlp_probe.py                  # MLP neural probe
│   ├── dielectric_mlp_calibration_probe.py      # Pre-registered calibration probe
│   ├── dielectric_chemprop_baseline.py          # Chemprop D-MPNN baseline
│   ├── g2_domain_gap_test.py                    # External domain-gap test
│   ├── v032_ablation_summary.json               # v0.3.2 236-row benchmark
│   ├── v032_target_scaffold_summary.json        # v0.3.2 scaffold holdout
│   ├── v032_controlled_comparison_summary.json  # Paired PC/EC control
│   └── artifacts/                               # Figures and plots
├── reports/
│   ├── decisions_log.md                         # Full decision record
│   ├── agent_workflow.md                        # Delegation and verification log
│   └── g1_data_gate_review.md                   # G1 conflict list
├── paper/
│   ├── outline.md
│   ├── abstract_and_intro.md
│   ├── methods_data_records.md
│   ├── technical_validation.md
│   ├── benchmark_and_figures.md
│   ├── code_and_data.md                         # sources of full_draft.md
│   └── full_draft.md                            # generated; do not edit by hand
├── src/electrolyte_ml/                          # Python package
├── tests/                                       # CI test suite
├── environment.yml                              # Conda environment
└── pyproject.toml
```

## Software dependencies

- Python 3.12
- RDKit 2024.09 (structure standardization, Morgan fingerprints, 2D descriptors)
- XGBoost 2.1 (primary candidate model)
- scikit-learn 1.5 (cross-validation, MLP, metrics)
- GFN2-xTB 6.7.1 (physical features)
- Chemprop 2.1.0 (D-MPNN baseline, isolated environment)
- NumPy, SciPy, pandas, matplotlib, pytest

## Reproducibility

Every dataset version is built by a deterministic script and verified by an
independent verifier that re-derives all metrics from the committed outputs.
All probe scripts accept explicit command-line arguments for input and output
paths. The conda environment is frozen in environment.yml.

`paper/full_draft.md` is generated from the five section files by
`scripts/build_paper_full_draft.py`; edit the sections, never the draft. The
section files and the generated draft are checked against the frozen artifacts
by `scripts/check_paper_artifact_consistency.py`, which runs in CI.

Verifiers run in CI (GitHub Actions, Ubuntu 22.04) on every commit:

```bash
# Full verification suite
pytest tests/ -v

# Individual dataset verifiers
python scripts/verify_dielectric_v032.py # 7/7 checks, 245 rows
python scripts/verify_dielectric_v03.py  # 7/7 checks, 246 rows
python scripts/verify_export_manifests.py

# Paper claims vs. frozen artifacts
python scripts/check_paper_artifact_consistency.py
```

## License

The dataset and code are released under the Creative Commons Attribution 4.0
International (CC BY 4.0) license, except where individual source records
carry more restrictive licenses (CC BY-NC, CC BY-NC-ND) as noted in the
source_license and redistribution_conditions columns of each row, or because
the underlying source has no stated reuse license.

Several rows need explicit qualification. 3-Methoxypropionitrile (MOPN) was
transcribed from the ECW-308 supporting information and carries no license
statement of its own, so it is flagged model_ready=false; the numeric fact is
retained while the underlying publisher supplement remains non-redistributable,
and no open-license claim is made for that source. Triethyl phosphate and
trimethyl phosphate retain their CC BY-NC 4.0 source_license metadata and are
also withheld from the modelling set; their conflict_status fields record the
competing public values rather than treating the licence as the reason for
withholding. Vinylene carbonate and fluoroethylene carbonate now each cite a
paywalled primary article, so their three licence columns are empty and
redistribution_status=allowed; only the measured fact, not the source PDF, is
redistributed. The ECW-308 supporting-information text and
the other closed-access extractions used during the Tier-1/Tier-2 search are
kept outside the repository (data/external/ is git-ignored) and are not
redistributed here.
