from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from build_anchor_crosscheck import (
    Evidence,
    _classify,
    _frequency_from_gate_flags,
    _matches_anchor,
    build_rows,
)

from electrolyte_ml.anchors import CrosscheckAnchor


def _anchor(**overrides: object) -> CrosscheckAnchor:
    values: dict[str, object] = {
        "anchor_id": "test_anchor",
        "name": "test compound",
        "inchikey": "AAAAYYYYBBBB-UHFFFAOYSA-N",
        "aliases": ("test compound",),
        "reference_value": 10.0,
        "reference_temperature_K": 298.15,
        "reference_frequency_MHz": 0.0,
        "tolerance": 0.5,
        "blocking_reason": "",
    }
    values.update(overrides)
    return CrosscheckAnchor(**values)  # type: ignore[arg-type]


def _evidence(**overrides: object) -> Evidence:
    values: dict[str, object] = {
        "anchor_id": "test_anchor",
        "evidence_source": "dielectric_v01",
        "source_doi": "10.0000/test",
        "source_record_id": "",
        "T_K": "298.15",
        "frequency_MHz": "0.0",
        "property_family": "zero_frequency",
        "value": "10.0",
        "gate_flags": "zero_frequency",
        "notes": "",
    }
    values.update(overrides)
    return Evidence(**values)  # type: ignore[arg-type]


def test_matches_anchor_is_exact_not_substring() -> None:
    anchor = _anchor(aliases=("benzene",))
    assert _matches_anchor(anchor, "Benzene")
    assert _matches_anchor(anchor, "benzene")
    # A substring rule would silently absorb every substituted benzene.
    assert not _matches_anchor(anchor, "Nitrobenzene")
    assert not _matches_anchor(anchor, "Benzene, 1,3,5-trimethyl-")


def test_frequency_derivation_from_gate_flags() -> None:
    assert _frequency_from_gate_flags("zero_frequency|pure_component") == (
        "0.0",
        "zero_frequency",
    )
    assert _frequency_from_gate_flags("frequency_1mhz|pure_component") == (
        "1.0",
        "frequency_dependent",
    )
    # An unrecognised flag set must not be guessed at.
    assert _frequency_from_gate_flags("pure_component") == ("", "")


def test_classify_agrees_within_tolerance() -> None:
    comparable, delta, agreement = _classify(_anchor(), _evidence(value="10.4"))
    assert comparable
    assert agreement == "agree"
    assert float(delta) == 0.4


def test_classify_disagrees_beyond_tolerance() -> None:
    comparable, _, agreement = _classify(_anchor(), _evidence(value="11.0"))
    assert comparable
    assert agreement == "disagree"


def test_classify_rejects_different_temperature() -> None:
    comparable, _, agreement = _classify(
        _anchor(), _evidence(value="10.0", T_K="313.15")
    )
    assert not comparable
    assert agreement == "not_comparable"


def test_classify_rejects_different_frequency() -> None:
    # A 1 MHz datum cannot be scored against a static reference.
    comparable, _, agreement = _classify(
        _anchor(), _evidence(value="10.0", frequency_MHz="1.0")
    )
    assert not comparable
    assert agreement == "not_comparable"


def test_classify_rejects_unknown_frequency_against_stated_reference() -> None:
    comparable, _, agreement = _classify(
        _anchor(), _evidence(value="10.0", frequency_MHz="")
    )
    assert not comparable
    assert agreement == "not_comparable"


def test_classify_tolerates_rounded_temperature() -> None:
    comparable, _, agreement = _classify(
        _anchor(), _evidence(value="10.0", T_K="298")
    )
    assert comparable
    assert agreement == "agree"


def test_build_rows_keeps_every_disagreeing_row_and_blocks_promotion() -> None:
    rows = build_rows(
        [_anchor()],
        [
            _evidence(evidence_source="dielectric_v01", value="10.2"),
            _evidence(evidence_source="dielectric_v02", value="12.0"),
        ],
    )
    assert len(rows) == 2
    assert {row["agreement"] for row in rows} == {"agree", "disagree"}
    # No side is chosen: the disagreeing value is still present.
    assert {row["value"] for row in rows} == {"10.2", "12.0"}
    assert {row["promotion_blocked"] for row in rows} == {"true"}
    assert {row["n_evidence_sources"] for row in rows} == {"2"}


def test_build_rows_emits_no_data_row_for_anchor_without_evidence() -> None:
    rows = build_rows([_anchor(blocking_reason="nothing anywhere")], [])
    assert len(rows) == 1
    assert rows[0]["agreement"] == "no_data"
    assert rows[0]["evidence_source"] == ""
    assert rows[0]["n_evidence_sources"] == "0"
    assert rows[0]["promotion_blocked"] == "false"
    assert rows[0]["notes"] == "nothing anywhere"


def test_build_rows_does_not_flag_promotion_when_everything_agrees() -> None:
    rows = build_rows(
        [_anchor()],
        [
            _evidence(evidence_source="dielectric_v01", value="10.1"),
            _evidence(evidence_source="dielectric_v02", value="9.9"),
        ],
    )
    assert {row["agreement"] for row in rows} == {"agree"}
    assert {row["promotion_blocked"] for row in rows} == {"false"}


def test_build_rows_only_returns_requested_anchors() -> None:
    rows = build_rows(
        [_anchor(anchor_id="wanted")],
        [_evidence(anchor_id="unwanted")],
    )
    assert len(rows) == 1
    assert rows[0]["anchor_id"] == "wanted"
    assert rows[0]["agreement"] == "no_data"
