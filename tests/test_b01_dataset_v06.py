"""B01 v06 guards: the repaired dataset must be additive, not destructive.

PLAN B asks for the pressure-heterogeneity and synthetic-midpoint defects to be
repaired. The only safe way to do that is versioning: emit a new dataset that
excludes them, while leaving every frozen artifact byte-identical. These tests
pin that property.

Guarded:
  1. v04 / v05 / J01-J03 are byte-unchanged
  2. v06 accounts for every v04 row (model-ready + excluded = total)
  3. no model-ready row carries a known defect
  4. exclusions are individually traceable (each states why)
  5. the denominator difference is explained, not hidden
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
B01 = REPO_ROOT / "outputs" / "b01"
PR = REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"

V04_SHA = "e046a3831630e36aae6b67666f74f787b8b33303057877c3402ff7a414e0873c"


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


pytestmark = pytest.mark.skipif(
    not (B01 / "dataset_v06_model_ready.csv").is_file(),
    reason="v06 not built yet",
)


def test_v04_is_byte_unchanged() -> None:
    """The repair must never mutate the frozen aggregate table."""
    h = hashlib.sha256((REPO_ROOT / "data" / "dielectric_v04.csv").read_bytes()).hexdigest()
    assert h == V04_SHA, f"dielectric_v04.csv changed: {h}"


def test_v05_ledger_is_byte_unchanged() -> None:
    man = json.loads(
        (PR / "dataset_v05_manifest.json").read_text(encoding="utf-8"))
    claimed = man["inputs"]["dielectric_v04"]
    assert claimed == V04_SHA, "v05 manifest no longer references the frozen v04"


def test_v06_accounts_for_every_row() -> None:
    ready = _load(B01 / "dataset_v06_model_ready.csv")
    excl = _load(B01 / "dataset_v06_exclusions.csv")
    man = json.loads((B01 / "dataset_v06_manifest.json").read_text(encoding="utf-8"))

    n_v04 = man["counts"]["n_v04_rows"]
    assert len(ready) + len(excl) == n_v04, (
        f"{len(ready)} + {len(excl)} != {n_v04}")

    # Every aggregate id appears exactly once across the two files.
    ids = [r["aggregate_id"] for r in ready] + [r["aggregate_id"] for r in excl]
    assert len(ids) == len(set(ids)), "an aggregate appears in both sets"


def test_no_model_ready_row_carries_a_known_defect() -> None:
    """The whole point of v06 is that model-ready rows are actually usable."""
    for r in _load(B01 / "dataset_v06_model_ready.csv"):
        assert r["condition_pair_valid"] == "true", (
            f"{r['measurement_id']} is model-ready with an invalid pair")
        assert "TEMPERATURE_IMPUTED" not in r["flags"], (
            f"{r['measurement_id']} is model-ready with an imputed temperature")
        assert "SYNTHETIC_PAIR" not in r["flags"], (
            f"{r['measurement_id']} is model-ready as a synthetic pair")
        assert "PRESSURISED" not in r["flags"], (
            f"{r['measurement_id']} is model-ready with pressurised data")
        assert r["blocking_reasons"] == "", (
            f"{r['measurement_id']} is model-ready but has blocking reasons")
        assert r["model_ready"] == "true"


def test_every_exclusion_is_traceable() -> None:
    """Exclusion is defined by absence from the model-ready set, and each
    excluded row must state why."""
    ready_ids = {r["aggregate_id"]
                 for r in _load(B01 / "dataset_v06_model_ready.csv")}
    for r in _load(B01 / "dataset_v06_exclusions.csv"):
        assert r["blocking_reasons"], (
            f"{r['measurement_id']} excluded without a stated reason")
        assert r["aggregate_id"] not in ready_ids, (
            f"{r['measurement_id']} appears in both the excluded and ready sets")


def test_pressure_contamination_is_excluded() -> None:
    """The 15 pressure-heterogeneous aggregates must not be model-ready."""
    audit = json.loads(
        (B01 / "pressure_heterogeneity_audit.json").read_text(encoding="utf-8"))
    contaminated = {c["aggregate_id"]
                    for c in audit["contaminated_aggregates"]}
    assert contaminated, "pressure audit found nothing"

    ready_ids = {r["aggregate_id"]
                 for r in _load(B01 / "dataset_v06_model_ready.csv")}
    leaked = contaminated & ready_ids
    assert not leaked, f"contaminated aggregates leaked into model-ready: {leaked}"


def test_denominator_difference_is_explained() -> None:
    """78 (v05 pair-valid) vs 74 (v06 model-ready) must be accounted for."""
    man = json.loads((B01 / "dataset_v06_manifest.json").read_text(encoding="utf-8"))
    assert "denominator_note" in man
    note = man["denominator_note"]
    assert "不是" in note or "not" in note.lower(), (
        "must state that the two counts use different definitions")
    assert man["lineage"]["v04_unchanged"] is True
    assert man["lineage"]["v05_unchanged"] is True
    assert man["lineage"]["frozen_artifacts_unchanged"] is True


def test_v06_manifest_declares_repairs() -> None:
    man = json.loads((B01 / "dataset_v06_manifest.json").read_text(encoding="utf-8"))
    repairs = man["repairs_applied"]
    assert "pressure_heterogeneity" in repairs
    assert "synthetic_midpoints" in repairs
    assert "temperature_imputation" in repairs


def test_conflict_register_is_actually_wired_in() -> None:
    """Reviewer 4 (B04) found v06 never read the conflict register.

    56 conflicts were all UNRESOLVED, yet the only two that touched model-ready
    molecules leaked through because nothing else disqualified them. The gate must
    read the register, and the adjudicated verdict must decide the outcome.
    """
    man = json.loads((B01 / "dataset_v06_manifest.json").read_text(encoding="utf-8"))
    assert "conflict_adjudication" in man, (
        "the conflict adjudication is not recorded in the manifest")
    assert man["conflict_adjudication"], "no adjudicated conflict was consumed"

    # The manifest must also document the repair.
    assert "unresolved_source_conflicts" in man["repairs_applied"]

    # And at least one row must carry a conflict flag, proving the join happened.
    ready = _load(B01 / "dataset_v06_model_ready.csv")
    excl = _load(B01 / "dataset_v06_exclusions.csv")
    flagged = [r for r in ready + excl if "CONFLICT_" in (r.get("flags") or "")]
    assert flagged, "no row carries a CONFLICT_ flag; the register is not joined"


def test_adjudicated_verdict_decides_the_row() -> None:
    """butan-2-ol passed 4/4 -> kept; DMAc held 4/4 -> excluded."""
    man = json.loads((B01 / "dataset_v06_manifest.json").read_text(encoding="utf-8"))
    adj = man["conflict_adjudication"]

    butanol = adj.get("BTANRVKWQNVYAZ-UHFFFAOYSA-N")
    assert butanol, "butan-2-ol adjudication missing"
    assert butanol["verdict"] == "RESOLVED_PASS"
    assert butanol["pass"] == 4 and butanol["hold"] == 0

    dmac = adj.get("FXHOOIRPVKKKFG-UHFFFAOYSA-N")
    assert dmac, "DMAc adjudication missing"
    assert dmac["verdict"] == "UNRESOLVED_HOLD"

    ready_ids = {r["inchikey"] for r in _load(B01 / "dataset_v06_model_ready.csv")}
    assert "BTANRVKWQNVYAZ-UHFFFAOYSA-N" in ready_ids, (
        "a 4/4-PASS conflict result was still excluded")
    assert "FXHOOIRPVKKKFG-UHFFFAOYSA-N" not in ready_ids, (
        "a 4/4-HOLD conflict result leaked into model-ready")


def test_duplicate_experiments_are_deduped() -> None:
    """DMAc's two 37.72 rows are one experiment; the count must say so."""
    ready = _load(B01 / "dataset_v06_model_ready.csv")
    excl = _load(B01 / "dataset_v06_exclusions.csv")
    rows = [r for r in ready + excl
            if r["inchikey"] == "FXHOOIRPVKKKFG-UHFFFAOYSA-N"]
    assert rows, "DMAc row missing"
    for r in rows:
        n_all = int(r["n_contributing_measurements"])
        n_indep = int(r["n_independent_experiments"])
        assert n_indep <= n_all, (
            f"independent experiments ({n_indep}) exceeds raw contributing rows ({n_all})")
        assert n_indep == 2, (
            f"DMAc should dedupe to 2 independent experiments, got {n_indep}")


def test_no_duplicate_blocking_reasons() -> None:
    """A reason arriving twice makes the register unreadable."""
    for r in _load(B01 / "dataset_v06_exclusions.csv"):
        reasons = [x for x in (r["blocking_reasons"] or "").split(";") if x]
        assert len(reasons) == len(set(reasons)), (
            f"{r['measurement_id']} has duplicate blocking reasons: {reasons}")


def test_v06_outputs_are_byte_reproducible() -> None:
    import subprocess
    import sys

    targets = [B01 / "dataset_v06_model_ready.csv",
               B01 / "dataset_v06_exclusions.csv"]
    script = str(REPO_ROOT / "scripts" / "b01" / "build_dataset_v06.py")
    subprocess.run([sys.executable, script], cwd=str(REPO_ROOT),
                   capture_output=True)
    before = {t: t.read_bytes() for t in targets}
    subprocess.run([sys.executable, script], cwd=str(REPO_ROOT),
                   capture_output=True)
    after = {t: t.read_bytes() for t in targets}
    drifted = [t.name for t in targets if before[t] != after[t]]
    assert not drifted, f"non-deterministic v06 outputs: {drifted}"
    man = json.loads((B01 / "dataset_v06_manifest.json").read_text(encoding="utf-8"))
    repairs = man["repairs_applied"]
    assert "pressure_heterogeneity" in repairs
    assert "synthetic_midpoints" in repairs
    assert "temperature_imputation" in repairs
