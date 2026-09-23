from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from build_dielectric_v02 import build_rows


def _v01_row(key: str = "V01KEY-UHFFFAOYSA-N") -> dict[str, str]:
    return {
        "inchikey": key,
        "smiles": "CO",
        "name": "methanol",
        "T_K": "298.15",
        "dielectric": "32.63",
        "uncertainty": "",
        "uncertainty_value": "",
        "uncertainty_kind": "",
        "confidence_level": "",
        "uncertainty_json": "[]",
        "source_doi": "10.0000/v01",
        "source_dois_all": "10.0000/v01",
        "n_observations": "1",
        "n_historical_observations": "0",
        "source_scope": "p1_thermoml_zero_frequency_pure_293.15_303.15K",
        "crosscheck_available": "false",
        "gate_flags": "zero_frequency|pure_component|experimental",
    }


def _candidate_row(rank: int = 1) -> dict[str, str]:
    return {
        "selected_for_v02": "true",
        "selection_eligible": "true",
        "source_id": f"nbs514:p1:{rank:03d}",
        "source_page": "1",
        "compound_name": "acetonitrile",
        "formula": "C2H3N",
        "dielectric": "37.5",
        "t_C": "20",
        "T_K": "293.15",
        "source_quality": "three_figures",
        "alpha_1e5": "",
        "alpha_kind": "",
        "valid_range_C": "",
        "references": "1",
        "frequency_note": "",
        "smiles": "CC#N",
        "inchikey": "WEVYAHXRMPXWCK-UHFFFAOYSA-N",
        "molecular_formula": "C2H3N",
        "formula_match": "true",
        "resolution_source": "pubchem",
        "resolved_name": "acetonitrile",
        "max_tanimoto_solvfunc": "0.5",
        "al_round1_hit": "false",
        "carbon_count": "2",
        "hetero_count": "1",
        "polar_group_bonus": "1",
        "hazard_flags": "",
        "stability_flags": "",
        "selection_rank": str(rank),
        "priority_score": "10",
        "notes": "",
    }


def test_build_rows_preserves_v01_and_appends_selected_candidate() -> None:
    rows = build_rows([_v01_row()], [_candidate_row()], minimum_additions=1)
    assert len(rows) == 2
    assert rows[0]["name"] == "methanol"
    assert rows[1]["name"] == "acetonitrile"
    assert rows[1]["source_scope"] == "nbs514_manual_static_293.15_303.15K"
    assert rows[1]["source_record_id"] == "nbs514:p1:001"


def test_build_rows_rejects_duplicate_structure() -> None:
    with pytest.raises(ValueError, match="duplicates a v0.1 key"):
        build_rows(
            [_v01_row("WEVYAHXRMPXWCK-UHFFFAOYSA-N")],
            [_candidate_row()],
            minimum_additions=1,
        )
