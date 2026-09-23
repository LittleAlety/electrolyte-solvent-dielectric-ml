from __future__ import annotations

from pathlib import Path

from scripts.audit_dielectric_databases import _local_nbs_audit


def test_nbs_audit_counts_current_eligibility() -> None:
    result = _local_nbs_audit(
        Path(__file__).resolve().parents[1],
    )

    assert result["candidate_count"] == 215
    assert result["eligible_count"] == 114
    assert result["selected_count"] == 110
    assert result["additional_eligible_count"] == 4
