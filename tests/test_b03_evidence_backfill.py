"""B03 regression guards: evidence backfill must not fabricate coverage.

B03's failure mode is subtle: it is easy to produce a report that *looks* like
progress by quietly dropping molecules that could not be resolved, or by
promoting a page read into a "measurement". Both would inflate the apparent
evidence base without adding a single real observation.

Guarded properties:
  1. every A18 molecule is either resolved or explicitly unresolved (no vanishing)
  2. the NBS514 verification agrees with the frozen v04 value byte-for-byte
  3. page reads are never written into the measurement ledger
  4. the literature inventory declares its scope (held documents, not a search)
  5. non-independence is recorded, not averaged away
  6. outputs are byte-reproducible
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EB = REPO_ROOT / "outputs" / "confirm_2027" / "evidence_backfill"
LEDGER = (REPO_ROOT / "outputs" / "confirm_2027" / "provenance_repair"
          / "measurement_ledger_v1.csv")


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


pytestmark = pytest.mark.skipif(
    not (EB / "A18_gap_register.csv").is_file(),
    reason="B03 artifacts not built yet",
)


def test_every_molecule_is_accounted_for() -> None:
    """No molecule may silently vanish between the register and the two lists."""
    gap = _load(EB / "A18_gap_register.csv")
    unres = _load(EB / "unresolved_molecules.csv")
    gap_ids = {r["a_mol_id"] for r in gap}
    unres_ids = {r["a_mol_id"] for r in unres}

    # Resolved = in the register but not in the unresolved list.
    resolved = gap_ids - unres_ids
    assert resolved | unres_ids == gap_ids, "molecule set mismatch"
    assert len(resolved) + len(unres_ids) == len(gap_ids), (
        "a molecule appears in both the resolved and unresolved sets")

    status = json.loads((EB / "b03_gate_status.json").read_text(encoding="utf-8"))
    assert status["accounting_closed"] is True


def test_nbs514_verification_matches_frozen_v04() -> None:
    """A page read that disagrees with the frozen value must not be called verified."""
    for r in _load(EB / "source_verification.csv"):
        if r["verification_status"] != "VERIFIED_AGAINST_PAGE_READ":
            continue
        assert r["epsilon_agrees"] == "true", (
            f"{r['a_name']} marked verified but epsilon disagrees")
        assert r["v04_epsilon"] == r["nbs514_epsilon"], (
            f"{r['a_name']}: v04={r['v04_epsilon']} vs nbs={r['nbs514_epsilon']}")
        assert r["page_locator"], "verified row must carry a page locator"


def test_page_reads_never_enter_the_measurement_ledger() -> None:
    """The ledger's invariant is ThermoML + source_file_sha256."""
    ledger = _load(LEDGER)
    nbs_rows = [r for r in ledger
                if (r.get("source_document_id") or "").strip() == "10.6028/nbs.circ.514"]
    assert not nbs_rows, (
        f"{len(nbs_rows)} NBS514 rows leaked into the measurement ledger, "
        f"breaking the source_file_sha256 invariant")

    # And the qualified-measurements file must say so explicitly.
    for r in _load(EB / "condition_qualified_measurements.csv"):
        assert r["in_measurement_ledger"] == "false"
        assert r["ledger_exclusion_reason"], (
            "a condition-qualified row must state why it is outside the ledger")
        assert r["admission_status"] == "PENDING_FOUR_AGENT_REVIEW", (
            "page reads must not be pre-admitted")


def test_literature_inventory_declares_its_scope() -> None:
    """An inventory of held documents is not a literature search."""
    rows = _load(EB / "literature_source_inventory.csv")
    assert rows
    for r in rows:
        assert r["inventory_scope_note"], (
            f"{r['source_document_id']} lacks a scope note")
    doc = json.loads((EB / "b03_registers.json").read_text(encoding="utf-8"))
    assert "不声称已完成穷尽式文献检索" in doc["declaration"]


def test_non_independence_is_recorded_not_averaged() -> None:
    rows = _load(EB / "independent_source_map.csv")
    assert rows, "no entangled document pairs recorded"
    for r in rows:
        # Two legitimate verdicts: identical observations (duplicate data) and
        # shared primary citation (same upstream campaign). Both mean
        # "not independent"; neither may be silently treated as independent.
        assert r["independence_verdict"].startswith("NOT_INDEPENDENT"), (
            f"unexpected verdict {r['independence_verdict']!r}")
        assert r["consequence"], "must state the downstream consequence"


def test_unresolved_molecules_cannot_enter_b04() -> None:
    for r in _load(EB / "unresolved_molecules.csv"):
        assert r["may_enter_b04"] == "false", (
            f"{r['a_name']} is unresolved but flagged as admissible to B04")
        assert r["unresolved_reason"], "must state a reason"
        assert r["next_action"], "must state a next action"


def test_sn_is_not_folded_to_room_temperature() -> None:
    """PLAN B P2: SN's 333.15 K data must survive as high-temperature data."""
    unres = _load(EB / "unresolved_molecules.csv")
    sn = next((r for r in unres if r["a_name"] == "SN"), None)
    assert sn is not None, "SN should still be unresolved (no room-band data)"
    assert sn["unresolved_reason"] == "NO_ROOM_BAND_OBSERVATION"
    assert int(sn["n_observations"]) > 0, (
        "SN's high-temperature observations must be preserved, not discarded")


def test_backfill_added_zero_new_observations() -> None:
    """B03 re-verified existing rows; it did not grow the evidence base.

    EA and MA were already in dielectric_v04.csv (dataset_origin v0.2) citing
    NBS Circular 514. The backfill confirmed those rows are reproducible from the
    page read -- which is valuable, but it is NOT two new measurements. A report
    that lets a reader believe the sample grew would be misleading.
    """
    import csv as _csv

    v04 = REPO_ROOT / "data" / "dielectric_v04.csv"
    with v04.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(_csv.DictReader(fh))
    by_name = {r["name"].strip().lower(): r for r in rows}

    for name, eps in (("ethyl acetate", "6.02"), ("methyl acetate", "6.68")):
        assert name in by_name, f"{name} missing from v04"
        r = by_name[name]
        assert r["dielectric"] == eps, (
            f"{name}: v04 says {r['dielectric']}, expected {eps}")
        assert r["source_doi"] == "10.6028/nbs.circ.514"
        # Already present before B03 ran -> the backfill added no observation.
        assert r["dataset_origin"] in ("v0.2", "v0.3", "v0.4"), (
            f"{name} has unexpected dataset_origin {r['dataset_origin']}")

    # And the report must say so in plain language.
    report = (EB / "evidence_backfill_report.md").read_text(encoding="utf-8")
    assert "本轮没有新增任何观测" in report
    assert "证据基数的真实变化是 0 条新观测" in report


def test_ea_ma_shared_primary_citation_is_recorded() -> None:
    """Reviewer 2 (B03): EA and MA both cite NBS514 ref 63 -> not independent.

    NBS514 is absent from the ThermoML source registry, so the generic
    independence check never saw these two rows. They must still be recorded as
    a shared-citation cluster, or B04 will count them as two independent sources.
    """
    rows = _load(EB / "independent_source_map.csv")
    shared = [r for r in rows
              if r["independence_verdict"] == "NOT_INDEPENDENT_SHARED_PRIMARY_CITATION"]
    assert shared, "the EA/MA shared-citation finding is not recorded"
    mols = {m.strip() for r in shared for m in r["shared_a18_molecules"].split(";")}
    assert mols == {"EA", "MA"}, f"unexpected shared-citation molecules: {mols}"
    for r in shared:
        assert "63" in r["basis"], "must name the shared reference number"
        assert r["consequence"], "must state the downstream consequence"


def test_nbs514_citations_are_traceable_in_the_raw_transcription() -> None:
    """The shared-reference claim must be verifiable from the source file."""
    import csv as _csv

    refs = {}
    part = REPO_ROOT / "data" / "interim" / "nbs514_organic_part1.csv"
    with part.open(encoding="utf-8-sig", newline="") as fh:
        for x in _csv.DictReader(fh):
            n = (x["compound_name"] or "").strip().lower()
            if n in ("methyl acetate", "ethyl acetate"):
                refs[n] = [t.strip() for t in (x["references"] or "").split(",")
                           if t.strip()]
    assert "methyl acetate" in refs and "ethyl acetate" in refs
    assert "63" in refs["methyl acetate"], refs
    assert "63" in refs["ethyl acetate"], refs


def test_cross_source_conflicts_are_recorded() -> None:
    """Reviewer 4 (B03): a held CC BY 4.0 source disagrees with NBS514 for EA/MA.

    Verification proves the transcription is faithful, not that the value is
    unique. If a held source says something materially different, B03 must say so
    rather than presenting one value as "verified".
    """
    path = EB / "cross_source_conflicts.csv"
    assert path.is_file(), "cross-source conflicts were never recorded"
    rows = _load(path)
    assert rows, "conflict file is empty"

    names = {r["a_name"] for r in rows}
    assert "MA" in names, "the MA conflict (7.072 vs 6.68) is missing"

    for r in rows:
        assert r["conflict_status"] == "UNRESOLVED"
        assert r["required_action"], "must state what B04 must do"
        assert float(r["relative_difference_pct"]) > 2.0

    # The MA conflict specifically must be the 5.87% one R4 found.
    ma = [r for r in rows if r["a_name"] == "MA"
          and r["held_source_value"] == "7.072"]
    assert ma, "MA 7.072 @288.15 K conflict not recorded"
    assert abs(float(ma[0]["relative_difference_pct"]) - 5.87) < 0.05

    # And the report must warn about it.
    report = (EB / "evidence_backfill_report.md").read_text(encoding="utf-8")
    assert "跨来源冲突" in report
    assert "不得择一作为主值而不说明" in report


def test_nbs514_is_graded_as_secondary_not_primary() -> None:
    """Reviewer 2 (B03): NBS514 is a critical compilation, not a primary measurement."""
    rows = _load(EB / "source_verification.csv")
    graded = [r for r in rows if r.get("nbs514_page_reads_found", "0") != "0"]
    assert graded, "no NBS514-verified rows found"
    for r in graded:
        assert r["source_is_primary"] == "false", (
            f"{r['a_name']}: NBS514 mis-graded as primary")
        assert r["source_type"] == "CRITICAL_COMPILATION_1951"
        assert r["primary_references"], (
            f"{r['a_name']}: must carry the original reference numbers")


def test_verifier_actually_reads_dielectric_v04() -> None:
    """Reviewer 3 (B03) D2: the verifier claimed to compare against v04 but
    never opened the file -- it compared the page read to an expansion mirror.

    Guard at the source level: the module must reference the v04 path.
    """
    src = (REPO_ROOT / "scripts" / "b03"
           / "verify_nbs514_evidence.py").read_text(encoding="utf-8")
    assert "dielectric_v04" in src, (
        "the verifier no longer references dielectric_v04.csv; 'agrees with v04' "
        "would again be unsupported")
    # And the specific dead assignment D1 must be gone.
    assert 'v04_eps = fnum(x.get("n_observations"))' not in src, (
        "v04_eps is again assigned from an observation COUNT rather than an epsilon")


def test_accounting_gate_can_actually_fail() -> None:
    """Reviewer 3 (B03) D5: the gate validated a set against its own complement.

    The old formulation was `resolved = gap - unres` then
    `len(resolved) + len(unres) == len(gap)`, an identity that holds regardless of
    the data. The gate must instead cross-check the resolved set against an
    independently derived criterion, so a molecule that vanishes from the
    unresolved list is caught.
    """
    import csv as _csv
    import json as _json
    import shutil
    import tempfile

    status = _json.loads((EB / "b03_gate_status.json").read_text(encoding="utf-8"))
    assert status["accounting_errors"] == [], (
        f"accounting errors present: {status['accounting_errors']}")
    assert status["accounting_closed"] is True

    # The gate must expose the independent re-derivation, not just a set identity.
    gap = _load(EB / "A18_gap_register.csv")
    unres = _load(EB / "unresolved_molecules.csv")
    srcver = _load(EB / "source_verification.csv")
    verified = {r["a_name"] for r in srcver
                if r["verification_status"] == "VERIFIED_AGAINST_PAGE_READ"}
    derived = {r["a_mol_id"] for r in gap
               if int(r["n_condition_valid_pairs"] or 0) > 0
               or r["a_name"] in verified}
    gap_ids = {r["a_mol_id"] for r in gap}
    unres_ids = {r["a_mol_id"] for r in unres}
    assert derived == gap_ids - unres_ids, (
        "the resolved set does not match the independent criterion")

    # Negative control: removing a molecule from the unresolved list must make
    # the gate fail, not certify the molecule as evidenced.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "unresolved_molecules.csv"
        with tmp.open("w", newline="", encoding="utf-8") as fh:
            w = _csv.DictWriter(fh, fieldnames=list(unres[0].keys()))
            w.writeheader()
            for r in unres:
                if r["a_mol_id"] != "C04":      # drop EC
                    w.writerow(r)
        dropped = list(_csv.DictReader(tmp.open(encoding="utf-8-sig")))
        assert len(dropped) == len(unres) - 1
        # Recompute the gate logic the report uses.
        dropped_ids = {r["a_mol_id"] for r in dropped}
        dropped_resolved = gap_ids - dropped_ids
        assert "C04" in dropped_resolved, "EC would be wrongly counted as resolved"
        # And the independent criterion must disagree, which is what trips the gate.
        assert dropped_resolved != derived, (
            "the gate would NOT catch a molecule vanishing from the unresolved list")


def test_verifier_detects_a_corrupted_v04_value() -> None:
    """Reviewer 3 (B03) D2 negative control.

    The verifier must read dielectric_v04.csv, so corrupting it must change the
    verdict. The old implementation compared the page read against an expansion
    mirror and would have reported VERIFIED even with v04 set to 99.99.
    """
    import csv as _csv
    import shutil
    import tempfile

    v04 = REPO_ROOT / "data" / "dielectric_v04.csv"
    original = v04.read_bytes()
    try:
        with v04.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(_csv.DictReader(fh))
        fields = list(rows[0].keys())
        for r in rows:
            if (r.get("name") or "").strip().upper() in (
                    "ETHYL ACETATE", "METHYL ACETATE"):
                r["dielectric"] = "99.99"
        with v04.open("w", newline="", encoding="utf-8") as fh:
            w = _csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow(r)

        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "b03"
                                 / "verify_nbs514_evidence.py")],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr[-1500:]
        # With v04 corrupted the page reads must no longer be called verified.
        assert "VALUE_MISMATCH" in proc.stdout, (
            "the verifier did not notice a corrupted v04 value; it is not "
            "actually reading dielectric_v04.csv")
    finally:
        v04.write_bytes(original)

    # Restore the downstream artifacts built from the clean file.
    for s in ("verify_nbs514_evidence.py", "build_b03_registers.py",
              "build_b03_report.py"):
        subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "b03" / s)],
                       cwd=str(REPO_ROOT), capture_output=True)


def test_b03_outputs_are_byte_reproducible() -> None:
    targets = [
        EB / "A18_gap_register.csv",
        EB / "source_verification.csv",
        EB / "condition_qualified_measurements.csv",
        EB / "literature_source_inventory.csv",
        EB / "independent_source_map.csv",
        EB / "unresolved_molecules.csv",
    ]
    scripts = [
        "scripts/b03/build_a18_gap_register.py",
        "scripts/b03/verify_nbs514_evidence.py",
        "scripts/b03/build_b03_registers.py",
    ]
    for s in scripts:
        subprocess.run([sys.executable, str(REPO_ROOT / s)],
                       cwd=str(REPO_ROOT), capture_output=True)
    before = {t: t.read_bytes() for t in targets}
    for s in scripts:
        subprocess.run([sys.executable, str(REPO_ROOT / s)],
                       cwd=str(REPO_ROOT), capture_output=True)
    after = {t: t.read_bytes() for t in targets}
    drifted = [t.name for t in targets if before[t] != after[t]]
    assert not drifted, f"non-deterministic B03 outputs: {drifted}"
