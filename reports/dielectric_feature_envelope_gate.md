# Feature-envelope applicability gate (Week 14, track B)

Pre-registered in probes/dielectric_feature_envelope_gate_prereg.json before this probe ran.  k = 1.5 and the 95th percentile are the locked constants; nothing was tuned after seeing the result.

## Verdict

- Overall: **primary_met_secondary_not_met**
- Primary criterion met: True
- Secondary criterion met: False
- Kill line triggered: False
- Raised by the leave-one-out sweep: 80 of 236 rows (0.3390)

## Rule A (robust interval fence, median +/- 1.5 IQR)

- EC: flagged=True; dipole_D = 5.786 (median 2.2455, fence [-0.97575, 5.46675], +1.649 IQR); mu_sq_over_Vm = 768854 (median 90145.8, fence [-121616, 301907], +4.808 IQR)
- PC: flagged=True; dipole_D = 6.008 (median 2.2455, fence [-0.97575, 5.46675], +1.752 IQR); mu_sq_over_Vm = 675353 (median 90145.8, fence [-121616, 301907], +4.145 IQR)

## Rule B (kNN distance fence, 95th-percentile LOO radius)

- Training-domain threshold: 1.8764 (median LOO nearest-neighbour distance 0.4201)
- EC: distance 1.5538, flagged=False
- PC: distance 1.1348, flagged=False

## Leave-one-out control over the 236-compound pool

- Rule A alone: 80 / 236 = 0.3390
- Rule B alone: 12 / 236 = 0.0508
- Combined (either rule): 80 / 236 = 0.3390

## Why the existing SMARTS gate stayed silent

The applicability rule's association branch fires when hbd_smarts_donor_count >= 1. For the two held-out candidates: EC donor_count=0, structural_gate_fires=False; PC donor_count=0, structural_gate_fires=False. A gate that needs a donor site cannot fire on a carbonate.
Cross-tab over the pool (old = structural branch, new = this gate): both 31, old only 38, new only 49, neither 118.

## Honest boundaries

1. Scaling: the envelope is calibrated on the 236-compound pilot pool. The real funnel scores a 29.5k candidate pool, where recall for a fixed enveloping rule is systematically different. Every rate above is a 236-pool rate and must travel with that count.
2. The gate does not rank. Its only action is to remove a candidate from the ranking channel and route it to measurement or a physical estimate. It says nothing about how good a retained candidate is.
3. If EC or PC had not been raised, that would be reported as a failed envelope. No k or percentile was moved to rescue either one.
