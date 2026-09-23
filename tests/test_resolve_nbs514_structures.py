from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from resolve_nbs514_structures import (
    Candidate,
    ResolvedStructure,
    _candidate_output_rows,
    _is_strict_room_temperature,
    name_variants,
)


def test_name_variants_include_parenthetical_alias() -> None:
    variants = name_variants(
        "4-Propenyl-1,2-dimethoxybenzene (Methyl isoeugenol)"
    )
    assert "4-Propenyl-1,2-dimethoxybenzene (Methyl isoeugenol)" in variants
    assert "Methyl isoeugenol" in variants
    assert "4-Propenyl-1,2-dimethoxybenzene" in variants


def test_name_variants_strip_stereo_prefixes() -> None:
    variants = name_variants("dl-erythro-3,4-diacetoxyheptane")
    assert "3,4-diacetoxyheptane" in variants


def test_strict_room_temperature_requires_target_window_and_quality() -> None:
    assert _is_strict_room_temperature(
        {"t_C": "20", "source_quality": "three_figures"}
    )
    assert _is_strict_room_temperature(
        {"t_C": "30", "source_quality": "four_figures"}
    )
    assert not _is_strict_room_temperature(
        {"t_C": "19.9", "source_quality": "four_figures"}
    )
    assert not _is_strict_room_temperature(
        {"t_C": "25", "source_quality": "two_or_less"}
    )


def test_candidate_output_marks_selected_top_rows() -> None:
    candidate = Candidate(
        row={
            "source_id": "nbs514:p1:001",
            "source_page": "1",
            "compound_name": "example",
            "formula": "CH4O",
            "dielectric": "32.63",
            "t_C": "25",
            "T_K": "298.15",
            "source_quality": "four_figures",
            "alpha_1e5": "2.64",
            "alpha_kind": "alpha",
            "valid_range_C": "5,55",
            "references": "218",
            "frequency_note": "",
        },
        structure=ResolvedStructure(
            smiles="CO",
            inchikey="OKKJLVBELUTLKV-UHFFFAOYSA-N",
            molecular_formula="CH4O",
            resolution_source="pubchem",
            resolved_name="methanol",
        ),
        formula_match=True,
        max_tanimoto_solvfunc=0.5,
        al_round1_hit=False,
        carbon_count=1,
        hetero_count=1,
        polar_group_bonus=1,
        hazard_flags="",
        stability_flags="",
        selection_eligible=True,
        selection_exclusion="",
        priority_score=1.0,
    )
    rows = _candidate_output_rows([candidate], target_new_compounds=1)
    assert rows[0]["selected_for_v02"] == "true"
    assert rows[0]["selection_eligible"] == "true"
    assert rows[0]["inchikey"] == "OKKJLVBELUTLKV-UHFFFAOYSA-N"
