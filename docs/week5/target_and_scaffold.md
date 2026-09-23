# Week 5 modelling protocol

## Target transform

The transformed target is:

`y = log(epsilon - 1)`

The model is trained on `y` and predictions are mapped back with
`epsilon = exp(y_hat) + 1`, then clipped to `epsilon >= 1`. Metrics are always
computed on the original epsilon scale.

The decision rule was fixed before running the comparison:

- accept the transform for a representation only if both MAE decreases and R2
  increases under the same random CV;
- retain the raw target otherwise;
- do not use the scaffold result to retroactively change the random-CV rule.

## Scaffold/cluster holdout

Ring-containing molecules are grouped by Murcko scaffold. Acyclic molecules
are grouped by ECFP4 Morgan radius-2 Butina clusters at Tanimoto distance
threshold `0.5`. This avoids treating every acyclic molecule as either a
unique group or one large invalid group.

Group assignment is greedy balanced. Five partition seeds (`42-46`) are used
to quantify sensitivity to the split. For each partition, all molecules in a
group remain in the same fold. The verifier rebuilds the groups and fold
assignments independently from SMILES.

## Interpretation boundary

The scaffold/cluster holdout is a stricter chemical-generalization check than
random CV, but it is not a prospective external validation set. It cannot
establish performance on genuinely new chemistries or mixtures. Its purpose
is to expose whether random-CV conclusions survive removal of close analogues.
