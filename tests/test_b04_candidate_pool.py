"""B04 guards: the candidate pool must be the narrow intersection, not a union.

B04 is the first point where a new pool may be built, and the temptation is to
grow it. These tests pin the opposite property: the pool contains exactly the
records that passed ALL three independent gates, and nothing else.

Guarded:
  1. pool == intersection(B02 4/4, v06 model-ready)
  2. no pool row is missing a measurement_id or source DOI
  3. candidate_pool_C and the merge_forbidden rule are untouched
  4. every excluded row is individually audited with a reason
  5. no temperature was harmonised
  6. the pool is not described as a training set
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
B04 = REPO_ROOT / "outputs" / "b04"
ADM = REPO_ROOT / "outputs" / "admission_v2"
V06 = REPO_ROOT / "outputs" / "b01"
STANDALONE = REPO_ROOT.parent / "v56_standalone"

pytestmark = pytest.mark.skipif(
    not (B04 / "candidate_pool_v2_draft.csv").is_file(),
    reason="B04 pool not built yet",
)


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def test_pool_is_exactly_the_intersection() -> None:
    pool = _load(B04 / "candidate_pool_v2_draft.csv")
    ready = {(r["measurement_id"]): r
             for r in _load(V06 / "dataset_v06_model_ready.csv")}
    consensus = _load(ADM / "consensus_decisions.csv")
    accepted = {r["measurement_id"] for r in consensus
                if r["consensus_status"] == "AI_CONSENSUS_ACCEPTED"}

    expected = accepted & set(ready)
    actual = {r["measurement_id"] for r in pool}
    assert actual == expected, (
        f"pool differs from the intersection: "
        f"extra={sorted(actual - expected)}, missing={sorted(expected - actual)}")


def test_no_pool_row_lacks_provenance() -> None:
    for r in _load(B04 / "candidate_pool_v2_draft.csv"):
        assert r["measurement_id"], "pool row without a measurement_id"
        assert r["source_doi"], f"{r['measurement_id']} has no source DOI"
        assert r["b02_four_of_four"] == "true"
        assert r["v06_model_ready"] == "true"
        assert r["admission_provenance"] == "AI_CONSENSUS_NOT_HUMAN_SIGNED"


def test_temperatures_are_not_harmonised() -> None:
    """Every raw temperature must survive; no folding to a single value."""
    pool = _load(B04 / "candidate_pool_v2_draft.csv")
    temps = {r["T_K"] for r in pool}
    assert len(temps) > 1, "all temperatures collapsed to one value"
    # And each must be a plausible Kelvin value, not a Celsius relabel.
    for t in temps:
        assert 200.0 <= float(t) <= 400.0, f"implausible temperature {t}"


def test_closed_interval_boundaries() -> None:
    """PLAN B B04: 293.15 and 303.15 are inside the closed band."""
    vocab = json.loads(
        (B04 / "temperature_vocabulary_mapping.json").read_text(encoding="utf-8"))
    ct = vocab["closed_interval_test"]
    assert ct["low_K"] == 293.15
    assert ct["high_K"] == 303.15
    # Every pool row must fall in the closed band, since that is the pool's scope.
    assert ct["n_pool_rows_outside"] == 0


def test_pool_c_is_byte_unchanged() -> None:
    pool_c = STANDALONE / "reports" / "candidate_pool_C_R001.csv"
    if not pool_c.is_file():
        pytest.skip("candidate_pool_C not present in this checkout")
    lineage = json.loads(
        (B04 / "pool_lineage_manifest.json").read_text(encoding="utf-8"))
    recorded = lineage["frozen_artifacts"]["candidate_pool_C"]["sha256"]
    actual = hashlib.sha256(pool_c.read_bytes()).hexdigest()
    assert actual == recorded, "candidate_pool_C changed"
    assert lineage["frozen_artifacts"]["candidate_pool_C"]["status"] == \
        "AUTHORITATIVE_HISTORICAL_UNCHANGED"


def test_merge_forbidden_still_holds() -> None:
    lineage = json.loads(
        (B04 / "pool_lineage_manifest.json").read_text(encoding="utf-8"))
    preview = lineage["frozen_artifacts"]["master_in_49_preview"]
    assert preview["merge_forbidden"] is True
    assert preview["status"] == "HISTORICAL_S4_FOLD_UNCHANGED"
    for r in _load(B04 / "candidate_pool_v2_draft.csv"):
        assert r["merge_forbidden"] == "true"


def test_every_excluded_record_is_audited() -> None:
    pool_ids = {r["measurement_id"]
                for r in _load(B04 / "candidate_pool_v2_draft.csv")}
    audit = _load(B04 / "candidate_exclusion_audit.csv")
    for r in audit:
        assert r["exclusion_reason"], (
            f"{r['measurement_id']} excluded without a reason")
        assert r["measurement_id"] not in pool_ids, (
            f"{r['measurement_id']} is both excluded and in the pool")

    # Every ready-or-excluded v06 row must appear in exactly one of the two files.
    ready = _load(V06 / "dataset_v06_model_ready.csv")
    excl = _load(V06 / "dataset_v06_exclusions.csv")
    all_ids = {r["measurement_id"] for r in ready} | \
              {r["measurement_id"] for r in excl}
    accounted = pool_ids | {r["measurement_id"] for r in audit}
    assert accounted == all_ids, (
        f"unaccounted rows: {sorted(all_ids - accounted)[:5]}")


def test_pool_is_not_described_as_a_training_set() -> None:
    lineage = json.loads(
        (B04 / "pool_lineage_manifest.json").read_text(encoding="utf-8"))
    assessment = lineage["pool_character"]["assessment"]
    assert "筛选可行性集" in assessment, (
        "the pool must be described as a screening feasibility set")
    assert "不是训练集" in assessment

    review = (B04 / "candidate_pool_review.md").read_text(encoding="utf-8")
    assert "22 条不是数据集" in review
    assert "未宣称统计功效充分" in review


def test_pool_outputs_are_byte_reproducible() -> None:
    import subprocess
    import sys

    targets = [B04 / "candidate_pool_v2_draft.csv",
               B04 / "candidate_exclusion_audit.csv"]
    script = str(REPO_ROOT / "scripts" / "b04" / "build_candidate_pool_v2.py")
    subprocess.run([sys.executable, script], cwd=str(REPO_ROOT), capture_output=True)
    before = {t: t.read_bytes() for t in targets}
    subprocess.run([sys.executable, script], cwd=str(REPO_ROOT), capture_output=True)
    after = {t: t.read_bytes() for t in targets}
    drifted = [t.name for t in targets if before[t] != after[t]]
    assert not drifted, f"non-deterministic B04 outputs: {drifted}"
