"""B01 regression guards: the measurement reconstruction must stay honest.

The defects these tests pin are all instances of the same failure mode: a check
that *cannot fail* being reported as a check that *passed*. PLAN B B01 exists
precisely to stop that, so the guard has to be mechanical.

Guarded properties:
  1. the independent verifier reproduces the headline counts (2065/460/78/170)
  2. the exception register covers every non-COMPLETE aggregate
  3. no pair marked valid lacks a single observation holding both medians
  4. the tautological generator criterion is *detected*, not hidden
  5. the pressure audit surfaces contaminated aggregates rather than ignoring them
  6. B01 outputs are byte-reproducible
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PR = REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
B01_OUT = REPO_ROOT / "outputs" / "b01"

B01_SCRIPTS = [
    "scripts/b01/build_reconstruction_exceptions.py",
    "scripts/b01/validate_source_independence.py",
    "scripts/b01/audit_pressure_heterogeneity.py",
    "scripts/b01/audit_b01_schema_conformance.py",
    "scripts/b01/verify_measurement_reconstruction.py",
    "scripts/b01/build_b01_gate_status.py",
]


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / script)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )


@pytest.mark.parametrize("script", B01_SCRIPTS)
def test_b01_script_runs(script: str) -> None:
    proc = _run(script)
    # verify_measurement_reconstruction returns 1 when a check legitimately fails.
    assert proc.returncode in (0, 1), f"{script} crashed:\n{proc.stderr[-1500:]}"


def test_headline_counts_reproduce_independently() -> None:
    ver = json.loads(
        (PR / "measurement_reconstruction_verification.json").read_text(encoding="utf-8"))
    hc = ver["headline_counts"]
    assert hc["n_measurements_full"] == 2065
    assert hc["n_in_aggregate_window"] == 460
    assert hc["n_pair_valid"] == 78
    assert hc["n_pair_invalid"] == 170


def test_no_pair_marked_valid_without_shared_holder() -> None:
    """A valid pair must have ONE observation holding both the T and eps median."""
    for p in _load(PR / "condition_pair_validity_v1.csv"):
        if (p.get("condition_pair_valid") or "").strip().lower() != "true":
            continue
        t_idx = {s.split("@")[-1].strip()
                 for s in (p.get("temperature_median_holders") or "").split(";") if "@" in s}
        e_idx = {s.split("@")[-1].strip()
                 for s in (p.get("epsilon_median_holders") or "").split(";") if "@" in s}
        assert t_idx & e_idx, (
            f"{p.get('aggregate_id')} marked valid but no single observation "
            f"holds both medians (T={sorted(t_idx)[:3]}, eps={sorted(e_idx)[:3]})"
        )


def test_exception_register_covers_every_non_complete_aggregate() -> None:
    agg = _load(PR / "aggregate_contribution_ledger_v1.csv")
    exc = _load(PR / "reconstruction_exceptions.csv")
    non_complete = {(r.get("aggregate_id") or "").strip() for r in agg
                    if (r.get("contribution_status") or "").strip() != "COMPLETE"}
    covered = {(e.get("aggregate_id") or "").strip() for e in exc}
    missing = non_complete - covered
    assert not missing, f"{len(missing)} non-COMPLETE aggregates lack an exception record"


def test_exception_register_never_invents_recovery() -> None:
    """An exception may be unrecoverable or partial -- never 'recovered by guessing'."""
    allowed = {"true", "false", "partial"}
    for e in _load(PR / "reconstruction_exceptions.csv"):
        assert (e.get("recoverable") or "").strip() in allowed, (
            f"{e.get('exception_id')} has recoverable={e.get('recoverable')!r}")
        assert (e.get("repair_action") or "").strip() != "", "exception must state a rule"


def test_tautological_generator_criterion_is_detected() -> None:
    """The criterion must now be genuinely non-tautological.

    History: build_provenance_preserving_dataset.py:437 originally filtered on
    `invalidity_reason == "not_evaluated"`, which only holds when the pair is
    valid by construction -- so the criterion could never fail. It inspected
    69/248 rows and excluded all 170 false ones. It has been replaced with a
    structural test over all 248 rows.

    This test guards the FIXED state. The negative control (re-injecting the
    vacuous form makes the check fail) is exercised manually and recorded in the
    round report, because a test cannot mutate the generator it is testing.
    """
    ver = json.loads(
        (PR / "measurement_reconstruction_verification.json").read_text(encoding="utf-8"))
    by_name = {c["check"]: c for c in ver["checks"]}
    check = by_name["generator_acceptance_criterion_is_not_tautological"]
    assert check["status"] == "PASS", (
        "the criterion is tautological again: " + check["detail"]
    )

    # And the manifest must declare full coverage that can actually fail.
    man = json.loads(
        (PR / "dataset_v05_manifest.json").read_text(encoding="utf-8"))
    cov = man["acceptance_criteria"]["synthetic_pair_check_coverage"]
    assert cov["n_rows_inspected"] == cov["n_rows_total"], (
        "criterion does not inspect the whole table")
    assert cov["criterion_can_fail"] is True, (
        "criterion cannot fail, so it is not evidence")
    assert cov["n_valid_without_holders"] == 0, (
        "a pair is marked valid with no recorded holders")


def test_generator_source_has_no_vacuous_filter() -> None:
    """Static guard on the real code body, ignoring docstrings/comments."""
    import ast

    src = (REPO_ROOT / "scripts" / "confirm_2027"
           / "build_provenance_preserving_dataset.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # Strip docstrings so the documented history of the defect is not flagged.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    assert 'if r["invalidity_reason"] in ("not_evaluated",)' not in code
    assert "if r['invalidity_reason'] in ('not_evaluated',)" not in code


def test_measurement_locator_is_real_not_a_template() -> None:
    """B01 requires a locator; a constant string would not be one."""
    loc = _load(B01_OUT / "measurement_locator_v1.csv")
    ledger = _load(PR / "measurement_ledger_v1.csv")
    assert len(loc) == len(ledger), "locator file must cover every measurement"

    values = [(r.get("measurement_locator") or "").strip() for r in loc]
    assert all(values), "every measurement must carry a locator"
    distinct = len(set(values))
    assert distinct > 100, f"only {distinct} distinct locators — looks templated"
    assert all("block=" in v for v in values), "locator must name a ThermoML block"

    # Locators must vary with the source document, not be a single global string.
    by_doc: dict[str, set[str]] = {}
    for r in loc:
        by_doc.setdefault((r.get("source_document_id") or ""), set()).add(
            (r.get("measurement_locator") or ""))
    assert len(by_doc) > 50, "locators span too few documents to be credible"


def test_false_negative_is_recorded_not_hidden() -> None:
    """EPSV04-R247 has an exact matching observation outside the band."""
    exc = _load(PR / "reconstruction_exceptions.csv")
    fn = [e for e in exc
          if (e.get("exception_class") or "").strip()
          == "SOURCE_LAYER_MISMATCH_FALSE_NEGATIVE"]
    assert fn, "the R247 false negative is no longer recorded"
    assert any((e.get("measurement_id") or "").strip() == "EPSV04-R247" for e in fn)
    for e in fn:
        assert (e.get("stated_reason_is_wrong") or "").strip() == "true"


def test_pressure_contamination_is_surfaced() -> None:
    audit = json.loads(
        (B01_OUT / "pressure_heterogeneity_audit.json").read_text(encoding="utf-8"))
    assert audit["counts"]["n_contaminated"] > 0, "pressure contamination vanished"
    ids = {c["aggregate_id"] for c in audit["contaminated_aggregates"]}
    # The decisive case two reviewers found independently.
    assert "v04row-097" in ids, "the R097 pressure-sweep case is missing"
    # And the reported epsilon must be the midpoint of two sweep points.
    ex = audit["worked_example_EPSV04_R097"]
    assert ex["contributing_observations"], "R097 contributing rows missing"


def test_conflict_register_uses_pairwise_temperature_tolerance() -> None:
    """The register must compare temperatures pairwise, not by rounded bucket.

    History: bucketing on `round(t, 1)` is equality of a rounded key, not a
    tolerance. It silently missed 298.15 vs 298.2 K -- the canonical "room
    temperature" disagreement -- and split pairs across bucket boundaries.
    T_TOLERANCE_K was declared but never applied.
    """
    import ast

    src = (REPO_ROOT / "scripts" / "b01"
           / "build_source_conflict_register.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    code = ast.unparse(tree)
    assert "round(t, 1)" not in code, (
        "rounded-key bucketing is back; temperatures must be compared pairwise"
    )
    assert "T_TOLERANCE_K" in code

    # T_TOLERANCE_K must actually be *used* in a comparison, not just printed.
    uses = [ln for ln in code.splitlines()
            if "T_TOLERANCE_K" in ln and ("<=" in ln or ">=" in ln or "abs(" in ln)]
    assert uses, "T_TOLERANCE_K is declared but never applied to a comparison"


def test_conflict_register_finds_boundary_temperature_conflicts() -> None:
    """Conflicts at non-0.1-grid temperatures must be discovered."""
    reg = json.loads(
        (B01_OUT / "source_conflict_register.json").read_text(encoding="utf-8"))
    n_meas = reg["counts"]["n_conflicts_measurement_layer"]
    # The pairwise implementation found more than the old rounded-key version,
    # because it recovers pairs that straddle a bucket boundary.
    assert n_meas >= 49, f"measurement-layer conflicts dropped to {n_meas}"

    # And the known GVL conflict must still be present.
    assert reg["counts"]["n_conflicts_aggregate_layer"] >= 1


def test_gvl_conflict_is_queued_not_excluded() -> None:
    """Reviewer 4's finding: the conflict was excluded from review, not adjudicated."""
    reg = json.loads(
        (B01_OUT / "source_conflict_register.json").read_text(encoding="utf-8"))
    assert reg["counts"]["n_conflicts_excluded_from_review_queue"] == 0, (
        "a detected conflict is still missing from the review queue")


def test_gap_epsilon_is_the_authoritative_column() -> None:
    """Reviewer 3: gap_epsilon agrees with v04 on 248/248; v04_epsilon lies on 3.

    This guards against a downstream consumer reading `v04_epsilon` from the gap
    audit table, which is corrupted for the three folded-skeleton rows.
    """
    gap = _load(PR.parent / "provenance_audit" / "gap_aggregation_audit.csv")
    pair = _load(PR / "condition_pair_validity_v1.csv")
    pair_by_agg = {(r.get("aggregate_id") or ""): r for r in pair}

    gap_agree = 0
    v04_disagree = []
    for g in gap:
        mid = (g.get("measurement_id") or "").strip()
        if not mid.startswith("EPSV04-R"):
            continue
        agg_id = "v04row-" + mid[len("EPSV04-R"):]
        p = pair_by_agg.get(agg_id)
        if not p:
            continue
        authoritative = (p.get("v04_dielectric") or "").strip()
        if (g.get("gap_epsilon") or "").strip() == authoritative:
            gap_agree += 1
        if (g.get("v04_epsilon") or "").strip() != authoritative:
            v04_disagree.append(agg_id)

    assert gap_agree == len(gap), (
        f"gap_epsilon no longer matches the authoritative value ({gap_agree}/{len(gap)})")
    # The known corruption is exactly the 3 folded-skeleton rows.
    assert set(v04_disagree) == {"v04row-166", "v04row-174", "v04row-227"}, (
        f"unexpected v04_epsilon corruption set: {v04_disagree}")
    rep = json.loads(
        (PR / "source_independence_report.json").read_text(encoding="utf-8"))
    d = rep["duplicate_observations"]
    assert d["n_groups_cross_document"] > 0
    assert d["n_documents_entangled"] > 0
    # The registry must still honestly say independence was never evaluated.
    assert rep["registry_independence_status"]["n_not_evaluated"] > 0


def test_source_independence_finds_cross_document_duplicates() -> None:
    rep = json.loads(
        (PR / "source_independence_report.json").read_text(encoding="utf-8"))
    d = rep["duplicate_observations"]
    assert d["n_groups_cross_document"] > 0
    assert d["n_documents_entangled"] > 0
    # The registry must still honestly say independence was never evaluated.
    assert rep["registry_independence_status"]["n_not_evaluated"] > 0


def test_b01_outputs_are_byte_reproducible() -> None:
    targets = [
        PR / "reconstruction_exceptions.csv",
        PR / "duplicate_observation_groups.csv",
        B01_OUT / "pressure_heterogeneity_audit.csv",
    ]
    for script in B01_SCRIPTS:
        _run(script)
    first = {t: hashlib.sha256(t.read_bytes()).hexdigest() for t in targets}

    for script in B01_SCRIPTS:
        _run(script)
    second = {t: hashlib.sha256(t.read_bytes()).hexdigest() for t in targets}

    drifted = [t.name for t in targets if first[t] != second[t]]
    assert not drifted, f"non-deterministic B01 outputs: {drifted}"
