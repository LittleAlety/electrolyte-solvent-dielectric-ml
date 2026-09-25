# Cover letter

> Draft for the *Scientific Data* submission. Every `[TODO: ...]` must be
> resolved before sending; see `paper/submission_checklist.md`.

**To:** The Editors, *Scientific Data*

**Re:** Submission of a data descriptor, "An auditable, machine-learning-ready
dataset of static dielectric constants for 246 organic liquids"

Dear Editors,

We submit the enclosed data descriptor for consideration at *Scientific Data*.

**What the dataset is.** A curated, machine-learning-ready table of static
dielectric constants (relative permittivities) for 246 pure organic liquids at
near-room temperature (293.15-303.15 K), with one explicitly labelled
extended-temperature exception. It is assembled from three tiers of public
sources: the NIST ThermoML archive (100 compounds), NBS Circular 514
(210 compounds), and open-access review tables plus primary literature covering
modern battery solvents. Every row carries deterministic source provenance,
gate-flag metadata, conflict status, and licence and redistribution metadata
wherever the source supplies it. Conflicting public values are recorded rather
than averaged: nine rows carry an explicit conflict or unverified-provenance
record and six are flagged `model_ready=false`.

**Why we think it fits.** The value of this dataset is not only its size but the
auditability of how each number was chosen. Four properties may be of interest
to your reviewers:

1. **Publicly auditable by construction.** No subscription-restricted value
   enters the distributable table. Where a restricted catalogue was the only
   convenient route to a number, we either found an open corroborating source
   or recorded the gap as access-blocked rather than as absent, and we say
   which of the two it is.
2. **Three independent layers of verification.** Frozen dataset and benchmark
   values are recomputed by their own verifiers; the manuscript is checked
   against the frozen artefacts by a separate consistency gate; and the
   exported deliverables are checked by a manifest gate. The three layers have
   different responsibilities and do not substitute for one another.
3. **Honest negative results, retained.** We report what did not work: a
   ranking-oriented neural head that reaches Spearman 0.884 with R2 = -0.172
   and does not recover under pre-registered calibration (-0.309); a density
   feature that adds nothing (-0.001 R2); an added-carbonate gain that is
   indistinguishable from zero (p = 0.11); a conformal interval whose marginal
   coverage holds (0.915) while its high-permittivity stratum collapses to
   1.5-26%; and an Onsager-based applicability rule that covered 0 of the 150
   high-permittivity rows and was rejected.
4. **A quantitative applicability domain instead of an unqualified claim.** A
   structural hydrogen-bond-donor rule flags 33.66% of out-of-fold rows as
   outside the model boundary, where mean absolute error is 11.51 against 5.02
   inside, and it covers all 150 rows above epsilon 60. The manuscript states
   three distinct model boundaries: an association blind spot, scaffold
   extrapolation, and a polar-aprotic high-permittivity gap that we quantify.

We would be glad to provide any additional material your reviewers need,
including the per-row provenance table and the probe outputs behind every
figure.

**Data and code availability.** The dataset and the benchmark code are released
under CC BY 4.0 at https://github.com/[TODO: repository] under tag `[TODO: v1.0]`
and archived at https://doi.org/10.5281/zenodo.[TODO: DOI].

**Declarations.** This manuscript is original, is not under consideration
elsewhere, and all authors have approved the submission. The authors declare no
competing interests. All data and code needed to reproduce the analysis are
publicly available at the links above.

Sincerely,

[TODO: corresponding author name]  
[TODO: affiliation]  
[TODO: email]  
