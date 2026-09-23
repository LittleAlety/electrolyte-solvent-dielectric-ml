"""Keep the two copies of the Week 1 spot-check anchors from drifting apart.

`SPOT_CHECK_ANCHORS` in `electrolyte_ml.anchors` is a verbatim copy of a tuple
that still lives inline in `scripts/build_week1_closure.py`.  The script was
deliberately not refactored to import it: it produces a byte-reproducible
artifact that `scripts/verify_week1.py` pins by hardcoded counts and that the
Week 1 export manifest hashes, so a refactor would risk real artifacts for no
functional gain.

Extracting the inline tuple with `ast` gives the same protection -- if either
copy changes alone, this test fails -- without touching the artifact.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.anchors import (
    EC_TEMPERATURE_GUARD,
    SPOT_CHECK_ANCHORS,
    V02_CROSSCHECK_ANCHORS,
)

BUILD_WEEK1 = REPOSITORY_ROOT / "scripts" / "build_week1_closure.py"


def _inline_spot_check_anchors() -> tuple[dict[str, object], ...]:
    """Pull the anchors tuple straight out of ``build_spot_check_rows``."""

    tree = ast.parse(BUILD_WEEK1.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "build_spot_check_rows":
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            target = statement.targets[0]
            if isinstance(target, ast.Name) and target.id == "anchors":
                value = ast.literal_eval(statement.value)
                assert isinstance(value, tuple)
                return value
    pytest.fail("could not find the inline anchors tuple in build_week1_closure")


def test_inline_spot_check_anchors_match_the_shared_copy() -> None:
    inline = _inline_spot_check_anchors()
    assert len(inline) == len(SPOT_CHECK_ANCHORS)
    for inline_anchor, shared_anchor in zip(inline, SPOT_CHECK_ANCHORS, strict=True):
        assert dict(inline_anchor) == dict(shared_anchor), inline_anchor.get("anchor_id")


def test_v02_only_anchors_do_not_leak_into_the_spot_check_set() -> None:
    # Four anchors are deliberately shared by id. The rest are v0.2 additions,
    # and adding those to SPOT_CHECK_ANCHORS would append rows to
    # p1_spot_check.csv and break the counts verify_week1.py pins.
    spot_ids = {anchor["anchor_id"] for anchor in SPOT_CHECK_ANCHORS}
    v02_ids = {anchor.anchor_id for anchor in V02_CROSSCHECK_ANCHORS}
    assert v02_ids - spot_ids == {
        "benzene_298K",
        "ethylene_carbonate_313K_1MHz",
        "dec_298K",
    }


def test_shared_anchors_agree_across_the_two_definitions() -> None:
    """A compound in both sets must carry the same reference in both.

    The two definitions overlap on id, so they are a genuine drift risk: editing
    only the v0.2 copy would silently make the cross-check score a different
    tolerance than the Week 1 spot check uses.
    """

    spot_by_id = {anchor["anchor_id"]: anchor for anchor in SPOT_CHECK_ANCHORS}
    compared = 0
    for anchor in V02_CROSSCHECK_ANCHORS:
        spot = spot_by_id.get(anchor.anchor_id)
        if spot is None:
            continue
        compared += 1
        assert spot["name"] == anchor.name, anchor.anchor_id
        assert spot["expected_value"] == anchor.reference_value, anchor.anchor_id
        assert spot["expected_temperature"] == anchor.reference_temperature_K
        assert spot["frequency"] == anchor.reference_frequency_MHz
        assert spot["tolerance"] == anchor.tolerance, anchor.anchor_id
    assert compared == 4


def test_v02_anchors_are_unique_and_well_formed() -> None:
    identifiers = [anchor.anchor_id for anchor in V02_CROSSCHECK_ANCHORS]
    assert len(identifiers) == len(set(identifiers))
    keys = [anchor.inchikey for anchor in V02_CROSSCHECK_ANCHORS]
    assert len(keys) == len(set(keys))
    for anchor in V02_CROSSCHECK_ANCHORS:
        assert anchor.name
        assert anchor.aliases
        assert anchor.tolerance > 0
        assert anchor.inchikey.count("-") == 2


def test_ethylene_carbonate_is_not_anchored_near_room_temperature() -> None:
    """EC melts near 309.5 K, so it can never be a near-room liquid anchor."""

    assert "temperature_gate" in str(EC_TEMPERATURE_GUARD["gate_flags"])
    assert not any(
        anchor.name == "ethylene carbonate"
        and anchor.reference_temperature_K == 298.15
        for anchor in V02_CROSSCHECK_ANCHORS
    )


def test_the_drift_guard_actually_fails_on_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prove the comparison above is not vacuous.

    A guard that silently finds nothing to compare passes forever while
    protecting nothing, so mutate one value in the inline tuple and assert the
    mismatch is detected.
    """

    source = BUILD_WEEK1.read_text(encoding="utf-8")
    mutated = source.replace('"expected_value": 32.6,', '"expected_value": 32.7,')
    assert mutated != source, "the mutation matched nothing; the guard proves nothing"

    copy = tmp_path / "build_week1_closure.py"
    copy.write_text(mutated, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "BUILD_WEEK1", copy)

    with pytest.raises(AssertionError):
        test_inline_spot_check_anchors_match_the_shared_copy()
