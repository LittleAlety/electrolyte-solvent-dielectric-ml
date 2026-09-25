"""Regression tests for the multi-fragment xTB start-geometry defect."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from probes.xtb_fragment_geometry_defect import (
    CACHE_ROOT,
    EVIDENCE_PATH,
    TARGETS,
    build_payload,
    closest_pair,
    compare_cache,
    fragment_index,
    measure_cache,
    min_inter_fragment_distance,
    pairwise_distances,
    positions_from_xyz,
    verify_evidence,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
BASELINE_INPUT = REPOSITORY_ROOT / "probes" / "artifacts" / "v03_features_baseline_input.csv"
V03_ABLATION = REPOSITORY_ROOT / "probes" / "dielectric_v03_representation_ablation_summary.json"

# The defect only bites multi-fragment molecules, and every one of the four
# failing rows is multi-fragment.  A packed geometry has to clear ordinary
# non-bonded contact; anything under 2 A between two different fragments means
# the fragments were never separated.
MIN_HEALTHY_INTER_FRAGMENT_ANGSTROM = 2.0


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_the_four_failed_feature_rows_are_all_model_ready() -> None:
    """The four feature failures are model_ready rows, not curated exclusions."""

    dataset = {row["inchikey"]: row for row in _rows(DATASET)}
    assert len(TARGETS) == 4
    for inchikey in TARGETS:
        assert inchikey in dataset
        assert dataset[inchikey]["model_ready"] == "true", inchikey


def test_the_four_failed_feature_rows_carry_status_error() -> None:
    """The committed baseline input records exactly these four as errors."""

    baseline = {row["inchikey"]: row for row in _rows(BASELINE_INPUT)}
    errored = {
        inchikey
        for inchikey, row in baseline.items()
        if row["status"] == "error"
    }
    assert errored == set(TARGETS)
    for inchikey in TARGETS:
        assert "exit code 128" in baseline[inchikey]["error"]


def test_roster_arithmetic_leaves_the_four_rows_out_of_the_fit_set() -> None:
    """240 declared model_ready rows minus 4 feature failures is the 236 fit set."""

    summary = json.loads(V03_ABLATION.read_text(encoding="utf-8"))
    assert summary["failed_physical_feature_count"] == 4

    dataset = _rows(DATASET)
    model_ready = [row for row in dataset if row["model_ready"] == "true"]
    assert len(model_ready) == 240
    assert len(model_ready) - summary["failed_physical_feature_count"] == 236


def test_committed_evidence_matches_a_freshly_built_payload() -> None:
    committed = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert verify_evidence(committed) == []


def test_a_forged_cache_measurement_cannot_self_certify() -> None:
    """A committed cache_measurement is a claim, not a self-signed pass."""

    forged = build_payload()
    forged["cache_measurement"] = {"forged": True}
    assert verify_evidence(forged), "a forged cache block must not verify"


@pytest.mark.parametrize("inchikey", sorted(TARGETS))
def test_packing_removes_the_inter_fragment_overlap(inchikey: str) -> None:
    """Embedding fragments separately lifts every inter-fragment contact."""

    record = TARGETS[inchikey]
    smiles = str(record["smiles"])
    packed = _packed_xyz(smiles)

    packed_inter = min_inter_fragment_distance(smiles, packed)
    assert packed_inter >= MIN_HEALTHY_INTER_FRAGMENT_ANGSTROM
    assert packed_inter > float(record["cached_min_pair_angstrom"])

    # After packing, the closest contact overall is an ordinary bond inside a
    # fragment, not a fragment sitting on top of another fragment.
    mapping = fragment_index(smiles)
    distance, i, j = closest_pair(packed)
    assert distance >= 0.8
    assert mapping[i] == mapping[j]


def test_packing_is_reproducible() -> None:
    """Two independent packings of a multi-fragment species agree, so the probe
    records a deterministic number rather than a lucky seed."""

    smiles = "CCCCn1cc[n+](C)c1.F[P-](F)(F)(F)(F)F"
    first = min_inter_fragment_distance(smiles, _packed_xyz(smiles))
    second = min_inter_fragment_distance(smiles, _packed_xyz(smiles))
    assert first == pytest.approx(second, abs=1e-6)


@pytest.mark.skipif(
    not (CACHE_ROOT / "FYOFOKCECDGJBF-UHFFFAOYSA-N" / "input.xyz").is_file(),
    reason="git-ignored xTB cache is absent (CI)",
)
def test_recorded_cache_geometry_values_reproduce() -> None:
    """With the local cache present, the recorded start-geometry numbers hold."""

    measured = measure_cache()
    assert set(measured) == set(TARGETS)
    for inchikey, observation in measured.items():
        record = TARGETS[inchikey]
        assert observation["is_inter_fragment"] is True
        assert observation["min_pair_angstrom"] == pytest.approx(
            float(record["cached_min_pair_angstrom"]), abs=5e-4
        )
        assert observation["pairs_below_0p5_angstrom"] == int(
            record["cached_pairs_below_0p5_angstrom"]
        )
        assert observation["molecule_fragments"] == int(record["fragments"])


def _packed_xyz(smiles: str) -> str:
    from probes.xtb_fragment_geometry_defect import embed_fragments_separately

    return embed_fragments_separately(smiles)


def test_positions_parser_rejects_a_truncated_block() -> None:
    """Guard the shared parser used by both the cache reading and the test."""

    with pytest.raises(ValueError):
        positions_from_xyz("3\ncomment\nH 0 0 0\n")


def test_pairwise_matrix_marks_self_pairs_as_infinite() -> None:
    xyz = "2\ncomment\nH 0.0 0.0 0.0\nH 0.0 0.0 1.0\n"
    matrix = pairwise_distances(xyz)
    assert matrix[0, 0] == float("inf")
    assert matrix[0, 1] == pytest.approx(1.0)


def test_compare_cache_accepts_a_clean_measurement() -> None:
    """A faithful live measurement compares clean, with no reported problem."""

    measured = measure_cache()
    if not measured:
        pytest.skip("git-ignored xTB cache is absent (CI)")
    assert compare_cache(measured) == []


def test_compare_cache_rejects_injected_divergences() -> None:
    """A partial cache, or any single wrong field, has to be reported."""

    measured = measure_cache()
    if not measured:
        pytest.skip("git-ignored xTB cache is absent (CI)")
    keys = sorted(measured)
    assert compare_cache(measured) == []

    # A partial cache can never be reported as a pass.
    partial = {key: value for key, value in measured.items() if key != keys[0]}
    assert any("no cached start geometry" in p for p in compare_cache(partial))

    for field, delta in (
        ("min_pair_angstrom", 1.0),
        ("molecule_fragments", 1),
        ("pairs_below_0p5_angstrom", 7),
    ):
        mutated = {key: dict(value) for key, value in measured.items()}
        mutated[keys[1]][field] = mutated[keys[1]][field] + delta
        problems = compare_cache(mutated)
        assert any(keys[1] in problem for problem in problems), (field, problems)

    # Flipping the inter-fragment verdict has to be caught as well.
    flipped = {key: dict(value) for key, value in measured.items()}
    flipped[keys[1]]["is_inter_fragment"] = not flipped[keys[1]]["is_inter_fragment"]
    assert any(keys[1] in problem for problem in compare_cache(flipped))
