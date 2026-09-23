# G1 Data Gate Review: Conflict List & Provenance Changes

> Generated for v0.3.1 revision. All findings from Week 7 G1 source-priority pass.

## 1. New Conflict Exclusions

| Compound | Value | Conflict Interval | Current Status | Action | Reason |
|---|---|---|---|---|---|
| Vinylene carbonate (VC) | 126 | 78-127 | model_ready=true, open_access_article_text | **model_ready -> false** | ????????Knovel????, ????????; mp~22C, 298K????? |
| Methyl propionate | 6.2 | 5.5-6.2 | open_access_review_table | **open conflict** | NBS 514 ? eps=5.5 vs ?? 6.2, ?13%; ???NBS?????????? |

## 2. Provenance Promotions

| Compound | Current evidence | New evidence | NBS value | Review value | Match |
|---|---|---|---|---|---|
| Ethoxybenzene | open_access_review_table | **primary** | 4.22 (NBS p35:011) | 4.2 (Cui 2026) | ~0.5%, promote |

## 3. No NBS/ThermoML Match (keep review table)

The following compounds were checked against NBS Circular 514 and local ThermoML 
archive. No primary source values were found. Review table provenance retained.

- EMC, DOL, GVL, TEP, TMP, FEC (conflict already open)
- methyl propionate -> conflict opened (see above)
- difluorobenzene isomers, HFE, TTE, BTFE
- 2-MeTHF
- ethoxybenzene -> promoted (see above)
- chlorobenzene & chlorinated diluents from Cui 2026
- methyl butyrate (NBS 5.6 vs review 5.48, 2% diff, needs citation chain check)

## 4. Known Gaps (for paper Limitations)

These compounds lack publicly traceable dielectric constant measurements:

| Compound | CAS | Status | Evidence |
|---|---|---|---|
| Diglyme | 111-96-6 | **Absent** | No reliable value in public sources |
| Triglyme | 112-49-2 | **Absent** | ChemicalBook eps=7.5, no provenance |
| Tetraglyme | 143-24-8 | **Absent** | No reliable value in public sources |
| Adiponitrile | 111-69-3 | **Absent** | No reliable value in public sources (expected ~30-35) |
| FEC | 114435-16-8 | **Excluded** | Three conflicting values (78.4/102/107), no traceable source |

## 5. G3 MLP Calibration Probe Result

**Pre-registered probe**: Within each of 10x5 folds, fit intercept+slope between
MLP_Physical training predictions and true targets (nested, test fold untouched).
Then apply calibration to test predictions and re-evaluate R^2.

| Metric | Raw MLP_Physical | Calibrated | Change |
|---|---|---|---|
| R^2 | -0.172 +/- 0.481 | **-0.309 +/- 0.647** | **worse** |
| Spearman | 0.884 +/- 0.013 | 0.865 +/- 0.027 | slightly reduced |
| MAE | 7.43 +/- 0.63 | 7.81 +/- 0.69 | slightly worse |

**Conclusion**: Calibration did NOT recover positive R^2. The negative R^2 is
not solely a scale-offset issue. Report as true negative result.
NN line closed for v1.0. N3/N4 into future work.

---

### Next Steps (per Week 7 plan):
1. [ ] Review and confirm G1 conflict list and provenance changes
2. [ ] Apply changes -> v0.3.1 revision
3. [ ] G2: Frozen v0.2 model -> external test on 30 new compounds -> parity plot
4. [ ] G4: Chemprop --features-path physical features
5. [ ] G5: Paper body, benchmark freeze, v1.0 tag + DOI