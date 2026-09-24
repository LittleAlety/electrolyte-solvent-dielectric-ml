# Abstract

We present an auditable, machine-learning-ready dataset of static dielectric
constants (relative permittivities) for 245 pure organic liquids at near-room
temperature (293.15-303.15 K). The dataset is assembled from three sources:
the NIST ThermoML archive (v0.1, 45 compounds), NBS Circular 514 (v0.2, 210
compounds), and open-access review tables and primary literature covering
modern battery solvents (v0.3.2, 245 compounds). Every row carries deterministic
source provenance, gate-flag metadata, license and redistribution conditions,
and conflict status. Five compounds with unresolved public-source conflicts
are explicitly documented and excluded from model fitting. A companion
benchmark evaluates three representations (Morgan fingerprints, 13-dimensional
physical features from GFN2-xTB and RDKit, and their equal-weight hybrid)
under fixed 10x5 repeated cross-validation, scaffold/cluster holdout, and an
external domain-gap test on 29 battery-relevant solvents. The v0.3.2 release
candidate (XGBoost, Morgan+Physical hybrid on raw target) achieves R2 0.366,
Spearman 0.814, and MAE 7.13 on the 237-row table. A paired control that
freezes the v0.3 fold assignment and appends the two added battery carbonates
to the training folds only attributes +0.027 R2 (95% CI +0.017 to +0.036) to
the data addition, and both added solvents remain outside the model's
extrapolation range. All builds and verifiers are deterministic and
reproducible in continuous integration.

# Background and Summary

Battery electrolyte development requires accurate solvent permittivity data:
dielectric constant directly influences salt dissociation, ion pairing, and
ionic conductivity. Existing public resources for organic liquid permittivities
are fragmented across the NIST ThermoML archive (machine-readable but
limited near-room-temperature coverage), NBS Circular 514 (comprehensive but
published in 1951 as scanned tables), historical compilations (not
machine-readable), and individual journal articles (heterogeneous formats and
access conditions). Commercial databases (SpringerMaterials, Knovel) offer
broader coverage but under restrictive licenses that prevent redistribution
and limit reproducibility.

The Chodera lab (2015, arXiv:1506.00262) demonstrated that ThermoML could
supply static dielectric constants for force-field benchmarking, extracting
approximately 45 near-room-temperature pure-compound records. This extraction
established the feasibility of a public dataset but did not target
ML-ready formatting, battery-solvent coverage, or multi-source cross-validation.

The present dataset addresses these gaps by:
- Aggregating three independent public sources (ThermoML, NBS Circular 514,
  open-access literature) into a single auditable table.
- Recording deterministic provenance (DOI, page, table, temperature-source
  status, license, redistribution conditions) for every row.
- Maintaining explicit conflict records: values from disagreeing public
  sources are stored but excluded from model fitting, never averaged.
- Providing a fixed multi-repeat cross-validation framework with three
  representations (fingerprint, physical descriptor, hybrid) and two targets
  (raw, log-transformed).
- Evaluating the frozen v0.2 model on an external domain-gap test of 29
  battery-relevant solvents, directly measuring how well a model trained on
  classic organic compounds generalizes to electrolyte-relevant chemical space.

The v0.3.2 candidate model is intentionally conservative (shallow XGBoost with
equal-weight Morgan+Physical ensemble). Graph neural networks and deeper
architectures are evaluated as probes (MLP, Chemprop D-MPNN) but are not
promoted to the v0.3.2 candidate model. The benchmark results establish a clear
representation ceiling: physical features provide the ranking signal
(Spearman 0.801 for Physical alone vs. 0.689 for Morgan), fingerprints
provide complementary breadth (R2 0.223 vs. 0.354), and their hybrid ensemble
outperforms either alone (R2 0.366, Spearman 0.814). Neural probes confirm
this ceiling: the best MLP (Physical, Spearman 0.884) outperforms XGBoost in
ranking but has negative R2 that is not recoverable by linear calibration.

The primary contribution is the curated, auditable dataset itself, not a claim
that small-data models solve static permittivity prediction. We identify
several known gaps (glyme diethers, adiponitrile, FEC) as explicit targets for
the v1.1 revision.
