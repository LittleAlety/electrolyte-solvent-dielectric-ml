from __future__ import annotations

import numpy as np

from probes.al_round1 import (
    acquisition_score,
    classify_hazards,
    classify_review_warnings,
    select_top30,
)


def test_hazard_filter_flags_requested_reactive_groups() -> None:
    examples = {
        "COOC": "peroxide",
        "CN=[N+]=[N-]": "azide",
        "CN=C=O": "isocyanate",
        "CC(=O)Cl": "acyl_halide",
        "CS(=O)(=O)Cl": "sulfonyl_halide",
        "C1CO1": "epoxide",
        "CC=O": "aldehyde",
        "C[N+](=O)[O-]": "nitro",
        "CNCl": "n_x_bond",
        "ClCOC": "alpha_halo_ether",
        "FOC": "halogen_oxygen",
        "ClOC": "halogen_oxygen",
        "BrOC": "halogen_oxygen",
        "IOC": "halogen_oxygen",
        "CC(=S)C": "thiocarbonyl",
        "C=S=C": "thiocarbonyl",
        "C1=S=C=C2OCCOC=12": "thiocarbonyl",
        "CSSC": "s_s_bond",
    }

    for smiles, expected in examples.items():
        assert expected in classify_hazards(smiles)


def test_polyhalogenated_alkyl_is_warning_not_hazard() -> None:
    smiles = "FC(F)C(F)F"

    assert "polyhalogenated_alkyl" in classify_review_warnings(smiles)
    assert "halogen_oxygen" not in classify_hazards(smiles)


def test_acquisition_score_is_std_percentile_times_novelty() -> None:
    assert acquisition_score(0.8, 0.5) == 0.4


def test_top30_selection_is_deterministic_and_family_capped() -> None:
    rows = [
        {
            "candidate_id": str(index),
            "family": f"F{index // 8}",
            "acquisition_score": str(1.0 - index / 100),
        }
        for index in range(40)
    ]
    fingerprints = {
        row["candidate_id"]: np.eye(40, dtype=np.uint8)[index]
        for index, row in enumerate(rows)
    }

    first = select_top30(rows, fingerprints, limit=30, max_per_family=6)
    second = select_top30(rows, fingerprints, limit=30, max_per_family=6)

    assert [row["candidate_id"] for row in first] == [
        row["candidate_id"] for row in second
    ]
    assert len(first) == 30
    for family in {row["family"] for row in rows}:
        assert sum(row["family"] == family for row in first) <= 6


def test_top30_selection_never_bypasses_family_quota() -> None:
    rows = [
        {
            "candidate_id": str(index),
            "family": "OnlyFamily",
            "acquisition_score": str(1.0 - index / 100),
        }
        for index in range(30)
    ]
    fingerprints = {
        row["candidate_id"]: np.eye(30, dtype=np.uint8)[index]
        for index, row in enumerate(rows)
    }

    selected = select_top30(rows, fingerprints, limit=30, max_per_family=6)

    assert len(selected) == 6
    assert {row["family"] for row in selected} == {"OnlyFamily"}


def test_top30_selection_can_continue_with_initial_rows_without_quota_bypass() -> None:
    rows = [
        {
            "candidate_id": str(index),
            "family": f"F{index // 6}",
            "acquisition_score": str(1.0 - index / 100),
        }
        for index in range(30)
    ]
    fingerprints = {
        row["candidate_id"]: np.eye(30, dtype=np.uint8)[index]
        for index, row in enumerate(rows)
    }

    selected = select_top30(
        rows,
        fingerprints,
        limit=30,
        max_per_family=6,
        initial_selected=rows[:6],
    )

    assert len(selected) == 30
    assert sum(row["family"] == "F0" for row in selected) == 6
    assert all(
        sum(row["family"] == family for row in selected) <= 6
        for family in {row["family"] for row in rows}
    )
