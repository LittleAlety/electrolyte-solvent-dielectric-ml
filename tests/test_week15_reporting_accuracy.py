"""Accuracy guards for the Week 15 reporting round (appendix AC / decisions §24).

The adversarial review of the Week 15 data-layer arm found two classes of
defect in the prose, and both of them are statements, not numbers:

1.  Falsified claims that survived the write-up.  The review re-derived the
    lever-9 ``k=10`` arm under the *corrected* column order (the column order is
    decided by the broken ranking, and XGBoost runs with
    ``colsample_bytree=0.8``, so the fit is order-dependent) and got a different
    delta-R2.  So "k=10 读数不受影响" and "k=10 = 全池，不受影响" are wrong, not
    merely imprecise.  The T3 write-up likewise called the five SMILES
    differences *structural* although every one of those keys round-trips
    through PubChem (``identity_check = roundtrip_match`` and
    ``pubchem_inchikey == inchikey``), i.e. they are drawing differences under
    one and the same identifier, not identity doubts.  Finally the reported
    PubChem string ``N#CN=C=[N-]`` does not occur anywhere in the repository;
    the artefact stores ``C(=[N-])=NC#N``.

2.  Cost accounting with no carrier in the repository.  The harvest log only
    holds post-harvest cache-hit runs, so "315 次请求" and the derived "77.86"
    seconds cannot be recomputed from anything committed.

The guards below are phrased as *exact sentences that must not reappear* plus
*exact corrected values that must appear*, so a later edit cannot quietly
restore the old wording.  The manual lives outside the repository, so the
committed CI excerpt (``tests/fixtures/manual_appendix_j_snapshot.md``) is
guarded unconditionally and the live manual is guarded whenever it is present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DECISIONS_LOG = REPOSITORY_ROOT / "reports" / "decisions_log.md"
MANUAL = Path("E:/大二/d2qc/电解液（长期项目）/文献调研/执行手册_探针与周计划.md")
MANUAL_FIXTURE = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "manual_appendix_j_snapshot.md"
)

DECISIONS_SECTION_HEADING = "## §24 "
MANUAL_APPENDIX_HEADING = "## 附录 AC"

# Sentences the review proved wrong.  Each one is a claim, so "roughly right"
# is not an option: either the statement is true or it must not be written.
FALSIFIED_PHRASES = (
    "k=10 读数不受影响",
    "k=10 = 全池，不受影响",
    "k=10 = 全池不受影响",
    "N#CN=C=[N-]",
    "315 次请求",
    # Contextual, not a bare "77.86": an unrelated number with the same
    # digits must not trip the guard.
    "累计 77.86",
    "真分歧",
    "不同阴离子",
)

# The corrected, locally checkable facts that have to be stated instead.
CORRECTED_FACTS = (
    "+0.008666009048",
    "4.878e-02",
    "C(=[N-])=NC#N",
    "314/314",
    "0.25",
)


def _section(text: str, prefix: str) -> str:
    """Return the block starting at ``prefix`` up to the next top-level heading."""

    lines = text.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.startswith(prefix)),
        None,
    )
    assert start is not None, "no heading starting with " + repr(prefix)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return chr(10).join(lines[start:end])


def _manual_sections() -> dict[str, str]:
    sections: dict[str, str] = {}
    if MANUAL_FIXTURE.exists():
        sections["committed fixture"] = _section(
            MANUAL_FIXTURE.read_text(encoding="utf-8"), MANUAL_APPENDIX_HEADING
        )
    if MANUAL.exists():
        sections["live manual"] = _section(
            MANUAL.read_text(encoding="utf-8"), MANUAL_APPENDIX_HEADING
        )
    assert sections, "neither the live manual nor the committed fixture is readable"
    return sections


def test_decisions_section_24_has_no_falsified_claims() -> None:
    section = _section(
        DECISIONS_LOG.read_text(encoding="utf-8"), DECISIONS_SECTION_HEADING
    )
    offenders = [phrase for phrase in FALSIFIED_PHRASES if phrase in section]
    assert offenders == [], (
        "reports/decisions_log.md §24 still carries wording the Week 15 review "
        "disproved: " + repr(offenders)
    )


def test_decisions_section_24_states_the_corrected_facts() -> None:
    section = _section(
        DECISIONS_LOG.read_text(encoding="utf-8"), DECISIONS_SECTION_HEADING
    )
    missing = [fact for fact in CORRECTED_FACTS if fact not in section]
    assert missing == [], (
        "reports/decisions_log.md §24 no longer states the corrected Week 15 "
        "facts: " + repr(missing)
    )


def test_manual_appendix_ac_has_no_falsified_claims() -> None:
    for label, section in _manual_sections().items():
        offenders = [phrase for phrase in FALSIFIED_PHRASES if phrase in section]
        assert offenders == [], (
            label + " appendix AC still carries wording the Week 15 review "
            "disproved: " + repr(offenders)
        )


def test_manual_appendix_ac_states_the_corrected_facts() -> None:
    for label, section in _manual_sections().items():
        missing = [fact for fact in CORRECTED_FACTS if fact not in section]
        assert missing == [], (
            label + " appendix AC no longer states the corrected Week 15 "
            "facts: " + repr(missing)
        )


# ---------------------------------------------------------------------------
# T2 probe: the merge boundary has to be measured, not declared.
# ---------------------------------------------------------------------------

SCHRODINGER_REPORT = (
    REPOSITORY_ROOT / "reports" / "schrodinger_si_reconciliation.md"
)


@pytest.fixture(scope="module")
def t2_summary(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    from probes.schrodinger_si_reconciliation import build_summary

    output = tmp_path_factory.mktemp("week15_reporting_accuracy")
    return build_summary(summary_path=output / "summary.json")


def test_t2_merge_boundary_is_a_measurement_not_a_literal(
    t2_summary: dict[str, object],
) -> None:
    """``rows_merged_into_experimental_table`` used to be a hardcoded 0.

    The probe has no code path that writes into an experimental table, so the
    number described nothing.  It now has to come from an actual scan of the
    experimental tables for predicted rows / a prediction column.
    """

    supp_3 = t2_summary["supp_3"]
    measurement = supp_3["merge_boundary_measurement"]
    assert measurement["kind"] == "measured_over_experimental_tables"
    scanned = measurement["tables"]
    assert len(scanned) == 2, scanned
    assert all(table["present"] for table in scanned.values()), scanned
    assert measurement["predicted_rows_found"] == 0
    assert supp_3["rows_merged_into_experimental_table"] == 0
    # `merge_forbidden` is a design statement (there is no merge code path),
    # so it must say so instead of masquerading as a measurement.
    assert supp_3["merge_forbidden"] is True
    assert (
        supp_3["merge_forbidden_kind"] == "design_declaration_not_measurement"
    )


def test_t2_reports_an_order_independent_second_comparison(
    t2_summary: dict[str, object],
) -> None:
    """Row-order agreement is not independent evidence: the stored table is
    generated from the supplement, so it would share the order anyway.  The
    summary therefore has to carry a multiset comparison as well.
    """

    multiset = t2_summary["row_multiset_comparison"]
    assert multiset["multiset_matches"] is True
    assert multiset["left_rows"] == 3582
    assert multiset["right_rows"] == 3582
    findings = " ".join(t2_summary["findings"])
    assert "多重集" in findings
    report = SCHRODINGER_REPORT.read_text(encoding="utf-8")
    assert "多重集" in report
    assert "所以结论不是「集合相同但顺序不同」的弱命题" not in report


# ---------------------------------------------------------------------------
# T4 fidelity ledger: every column needs a tier.
# ---------------------------------------------------------------------------

KPI_MODULE = REPOSITORY_ROOT / "src" / "electrolyte_ml" / "kpi_descriptors.py"
KPI_REPORT = REPOSITORY_ROOT / "reports" / "kpi_64_feature_module.md"


def test_kpi_fidelity_ledger_classifies_vale() -> None:
    """``ValE`` fell through the VERBATIM/APPROXIMATE/UNCONFIRMED ledger.

    It is neither copied from the paper nor one of the four unconfirmed charge
    columns, so the ledger has to name it in exactly one tier.
    """

    docstring = KPI_MODULE.read_text(encoding="utf-8").split(chr(34) * 3)[1]
    verbatim = docstring.split("VERBATIM")[1].split("APPROXIMATE")[0]
    approximate = docstring.split("APPROXIMATE")[1].split("UNCONFIRMED")[0]
    unconfirmed = docstring.split("UNCONFIRMED")[1]
    assert "ValE" not in verbatim
    assert "ValE" in approximate
    assert "ValE" not in unconfirmed


def test_kpi_report_places_vale_in_the_same_tier() -> None:
    rows = [
        line
        for line in KPI_REPORT.read_text(encoding="utf-8").splitlines()
        if line.startswith("| ") and "`ValE`" in line
    ]
    assert len(rows) == 1, rows
    assert "本仓自写" in rows[0], rows[0]
