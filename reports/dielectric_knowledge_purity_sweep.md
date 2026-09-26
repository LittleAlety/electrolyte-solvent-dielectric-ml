# Lever 9: knowledge purity sweep (per-fold importance ranking)

Motivation: Angew. Chem. Int. Ed. 2025, 64, e202416506 (DOI 10.1002/anie.202416506) reports that embedding all 64 knowledge dimensions is worse than embedding the top 20 / 20 / 10, because less relevant knowledge adds learning burden. Lever 2 of this programme appended six association descriptors at once and the grouped R2 fell by 0.0119. This probe tests the resulting hypothesis directly.

## 1 Baseline reproduction

- arm: `paired_base` re-run inside this script
- reproduced hybrid R2: `0.4091179943351143`
- published hybrid R2: `0.4091179943351143`
- absolute difference: `0.0` against a tolerance of `1e-09` -> verified `True`
- `Morgan`: reproduced `0.06487386371009436` vs expected `0.06487386371009436` (bit exact `True`)
- `Morgan+Physical`: reproduced `0.4091179943351143` vs expected `0.4091179943351143` (bit exact `True`)
- `Physical`: reproduced `0.2531659995294713` vs expected `0.2531659995294713` (bit exact `True`)
- purity loop vs `run_protocol` on the identical frozen block: `0.4091179943351143` vs `0.4091179943351143`, abs difference `0.0` -> agrees `True`
- scoreboard guards: `True` (457 rows / 97 compounds / 50 splits / seed 42)

## 2 The purity curve: delta-R2 against k

| k | grouped R2 | delta R2 | positive repeats |
| --- | --- | --- | --- |
| 2 | `0.41205905249359925` | `+0.0029` | 5 / 10 |
| 4 | `0.4168916719618879` | `+0.0078` | 5 / 10 |
| 6 | `0.41794343838029013` | `+0.0088` | 6 / 10 |
| 10 | `0.42382797189483473` | `+0.0147` | 6 / 10 |
- best k: `10` at delta R2 `+0.0147` (positive `True`)
- curve shape: `monotone_increasing`
- monotone decreasing: `False`
- monotone increasing: `True`
- interior peak: `False` (strict `False`)
- mechanism reading: `no_interior_peak_monotone_increase` -> contradicts the paper's interior-peak law `True` (= `not interior_peak`); the paper's law that more embedded knowledge lowers accuracy predicts an interior peak; inside the frozen grid the curve has none, so that law is not reproduced. What is falsified is the decline branch, not the existence of an optimum: the grid caps at k=10, which is the whole knowledge pool, so a peak beyond the grid cannot be excluded

Per-repeat signs:

- k=2: `-+-++-+--+` (repeat 0..9) -> 5 positive
- k=4: `-++++----+` (repeat 0..9) -> 5 positive
- k=6: `-++++-+--+` (repeat 0..9) -> 6 positive
- k=10: `-+++--++-+` (repeat 0..9) -> 6 positive

## 3 Importance stability across folds

- folds ranked: `50`
- distinct top-3 sets: `21`
- modal top-3 set: `['heteroatom_over_carbon', 'donor_acceptor_pair_density', 'ring_count']` in `14` folds
- changes between consecutive folds: `45`
- members in every top-3 set: `[]`

| member | mean rank | median rank | top-3 folds | mean importance |
| --- | --- | --- | --- | --- |
| `heteroatom_over_carbon` | 1.36 | 1.0 | 49 | +92.11046 |
| `donor_acceptor_pair_density` | 2.84 | 2.5 | 37 | +39.81346 |
| `ring_count` | 3.08 | 3.0 | 35 | +44.60687 |
| `double_bond_count` | 3.72 | 4.0 | 19 | +27.41458 |
| `rotatable_bond_count` | 4.88 | 5.0 | 7 | +17.49425 |
| `has_1_donor` | 6.02 | 6.0 | 2 | +5.68009 |
| `has_2_donors` | 6.28 | 7.0 | 1 | +3.57510 |
| `has_3plus_donors` | 8.36 | 8.0 | 0 | +0.82315 |
| `donor_count` | 8.58 | 9.0 | 0 | +0.15700 |
| `acceptor_count` | 9.88 | 10.0 | 0 | +0.00000 |

## 4 Placebo arm

- placebo curve: `monotone_decreasing`, best k `2`
- placebo delta by k: `{'2': -0.004559983675993778, '4': -0.006181783633436799, '6': -0.008216153015457354, '10': -0.009031557926625716}`
- R2 at the best real k: `-0.0548962290631438`
- no-information floor on the identical permuted labels: `-0.0063523871448647904`
- delta over the floor: `-0.0485`
- within-pipeline delta on shuffled labels: `-0.0090`
- collapsed: `True`

## 5 Verdict

- decision: `sub_threshold`
- k=10 moved grouped R2 by +0.0147: above the kill line +0.005 but below the pass line +0.02
- the delta-R2 curve is `monotone_increasing` with no interior peak (`no_interior_peak_monotone_increase`): the paper's law that more embedded knowledge lowers accuracy is not reproduced inside the frozen grid, and the contradiction is reported as such rather than filed as a non-result
- shots: `4` declared up front; every k is reported

## 6 Knowledge pool

- members (10): `['donor_count', 'acceptor_count', 'has_1_donor', 'has_2_donors', 'has_3plus_donors', 'donor_acceptor_pair_density', 'ring_count', 'double_bond_count', 'rotatable_bond_count', 'heteroatom_over_carbon']`
- every member is computed from the row SMILES with RDKit; no xTB rerun

## 7 Honest boundaries

- The flow controller is not implemented. The paper learns how much of the selected knowledge to blend in; this probe ranks and truncates only. That is a stated boundary, not an achieved feature.
- The paper's absolute R2 of 0.97-0.99 is measured on melting, boiling and flash points, which are atomic-count-dominated phase-change temperatures. Our target is the collective dielectric response. Their numbers are not portable to us and are never quoted as a bar.
- 0.5332 and 0.5454 may only be quoted with their pool definitions (a 147-compound training pool against a 97-compound fixed scoring pool). The v1.0 headline 0.364 lives on the frozen 236-compound pool and is a different scoreboard from the 457-row fixed pool this probe scores.
- The knowledge ranking is recomputed inside every training fold, so this probe is stricter than the paper, whose ranking is computed on the whole dataset before training. The stricter version can only differ from theirs by being less leaky.
- What is falsified by a curve without an interior peak is the paper's law that more embedded knowledge lowers accuracy, not the existence of an optimum k. The frozen k grid stops at k=10, which is the entire ten-member pool, so the sweep has a hard ceiling: a peak living beyond the grid cannot be excluded. The honest reading is 'no interior peak inside the frozen grid', never 'the optimum is the full pool'.

## 8 Reproduction

```
.venv/Scripts/python.exe probes/dielectric_knowledge_purity_sweep.py
```

- coverage table: `data/processed/dielectric_observations_v11plus.csv` sha256 `159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9`
- probe script: `probes/dielectric_knowledge_purity_sweep.py` sha256 `373707f59d7a468e4beb8826dca12960ce05f38204196bfe1233842ee726dcef`
- pre-registration: `probes/dielectric_knowledge_purity_sweep_prereg.json` sha256 `e0b1093246517d440b27a168fb01d53a0479a007797797d1bb03aead52625623`
- output `summary`: `probes/dielectric_knowledge_purity_sweep_summary.json`
- output `report`: `reports/dielectric_knowledge_purity_sweep.md`
- output `folds`: `probes/artifacts/dielectric_knowledge_purity_sweep_folds.csv`
- output `repeats`: `probes/artifacts/dielectric_knowledge_purity_sweep_repeats.csv`
- output `predictions`: `probes/artifacts/dielectric_knowledge_purity_sweep_predictions.csv`
- output `importance`: `probes/artifacts/dielectric_knowledge_purity_sweep_importance.csv`
