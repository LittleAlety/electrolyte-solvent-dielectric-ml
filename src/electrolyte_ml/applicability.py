"""Applicability-domain rules for dielectric-solvent predictions.

The boundary implemented here is a *structural* statement about the liquid, not
a statement about any model output.  A liquid whose molecules can donate a
hydrogen bond is treated as self-associated: in the bulk it forms directed,
saturable, orientationally correlated H-bond networks, and its static
permittivity is governed by the Kirkwood correlation factor g.  A network like
that is not representable by the single-molecule mean-field features used by
this project, so those predictions are declared outside the domain.

Two alternative formulations were implemented and measured before this one was
adopted; both are recorded in `probes/applicability_domain_summary.json` and in
`reports/applicability_domain_veto_fix.md`:

* `hbd >= 1 and predicted dielectric > 60` (the original rule) fires on 30 of
  6150 out-of-fold rows (0.49%) because the model cannot predict the compounds
  the rule is meant to catch, so the rule is circular.
* `hbd >= 1 and Onsager-estimated dielectric > 60` (the model-independent
  repair prescribed by the review) is not circular, but it is physically
  inverted: the Onsager reaction-field estimate is *low* for exactly the
  hydrogen-bonded associated liquids (1.6-40 estimated against measured values
  of 61-178) and *high* for ionic liquids (82-153 estimated against measured
  values of 12-30).  It covers 0 of the 150 rows whose measured permittivity
  exceeds 60.

The adopted rule covers 150 of those 150 rows.
"""

from __future__ import annotations

from rdkit import Chem

# Textbook hydrogen-bond donor site: O, S or N that still carries a hydrogen.
# This is deliberately not RDKit's Lipinski counter, which is a drug-likeness
# heuristic and reports zero donors for water and other small protic molecules.
H_BOND_DONOR_SMARTS = "[O,S,N;!H0]"

_DONOR_PATTERN = Chem.MolFromSmarts(H_BOND_DONOR_SMARTS)

INSIDE_DOMAIN = "inside_domain"
OUTSIDE_ASSOCIATED_LIQUID = "outside_associated_liquid"
OUTSIDE_NONPHYSICAL = "outside_nonphysical"


def count_hbond_donors(smiles: str) -> int:
    """Count hydrogen-bond donor sites in the given SMILES.

    Raises:
        ValueError: if the SMILES string cannot be parsed.
    """

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError(f"unparsable SMILES: {smiles!r}")
    return len(molecule.GetSubstructMatches(_DONOR_PATTERN))


def applicability_domain(
    predicted_dielectric: float,
    *,
    donor_count: int,
) -> str:
    """Return a conservative domain label for one prediction.

    Args:
        predicted_dielectric: the model's raw predicted permittivity.  It is
            used only for the non-physical sanity guard, never for the
            association boundary.
        donor_count: number of hydrogen-bond donor sites in the compound, as
            returned by count_hbond_donors.
    """

    if predicted_dielectric < 1.0:
        return OUTSIDE_NONPHYSICAL
    if donor_count >= 1:
        return OUTSIDE_ASSOCIATED_LIQUID
    return INSIDE_DOMAIN
