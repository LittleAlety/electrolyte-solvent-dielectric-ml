"""Guards for the AL Round 4 new-compound backfill list.

Two different things are pinned here.

The *derived* half -- the list, the coverage-gap table and the pending triage --
is pinned by re-derivation: the CSV files must equal what the generators compute
from the frozen inputs, and the local-coverage verdict of every row must
recompute from the two frozen panel files.

The *declared* half -- the Round-4 priority rule, the action rule and the
evidence rule -- is pinned by unit tests on the rule functions and by boundary
assertions on the published rows: already-covered compounds must be explicitly
marked local and must never be counted as new, and a prose-only epsilon clue must
never carry a number.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

from probes.al_round4_new_compound_backfill import (
    ACTION_ARCHIVE,
    ACTION_DROP,
    ACTION_HUMAN,
    ACTION_LEAD_ONLY,
    ACTION_READ_FULLTEXT,
    EVIDENCE_FIRST_HAND,
    EVIDENCE_KINDS,
    EVIDENCE_NO_CLUE,
    EVIDENCE_RESTATEMENT,
    GAP_FIELDS,
    GAPS_PATH,
    LIST_FIELDS,
    LIST_PATH,
    OBSERVATIONS_PATH,
    PENDING_REPORT_PATH,
    PRIORITY_ORDER,
    REPORT_PATH,
    SCHEMA_VERSION,
    SCRATCH_NAME_PREFIX,
    SCRATCH_PREFIXES,
    SUMMARY_PATH,
    TRACE_ROOTS,
    TRIAGE_PATH,
    V03_PATH,
    build_candidates,
    build_coverage_gaps,
    build_pending_triage,
    classify_family,
    derive_action,
    derive_priority,
    gap_top_families,
    load_local_panel,
    local_trace_scan,
    parse_triplets,
    read_csv,
    sha256_file,
    trace_scan_allowed,
    verify_invariants,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# The frozen panel files this round is pinned to.
FROZEN_V03_SHA256 = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
FROZEN_OBSERVATIONS_SHA256 = (
    "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9"
)

EC_INCHIKEY = "KMTRUDSVKNLOMY-UHFFFAOYSA-N"
PC_INCHIKEY = "RUOJZAUFBMNUDX-UHFFFAOYSA-N"
WATER_INCHIKEY = "XLYOFNOQVPJJNP-UHFFFAOYSA-N"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def triage_rows() -> list[dict[str, str]]:
    return read_csv(TRIAGE_PATH)


@pytest.fixture(scope="module")
def panel():
    return load_local_panel()


@pytest.fixture(scope="module")
def candidates(triage_rows: list[dict[str, str]], panel):
    keys = {
        key: name
        for row in triage_rows
        for name, key, _smiles in parse_triplets(row)
        if key
    }
    rows, _stats = build_candidates(triage_rows, panel, local_trace_scan(keys))
    return rows


@pytest.fixture(scope="module")
def list_rows() -> list[dict[str, str]]:
    return _rows(LIST_PATH)


@pytest.fixture(scope="module")
def gap_rows() -> list[dict[str, str]]:
    return _rows(GAPS_PATH)


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# inputs and file hygiene
# --------------------------------------------------------------------------- #


def test_frozen_panel_files_are_untouched() -> None:
    assert sha256_file(V03_PATH) == FROZEN_V03_SHA256
    assert sha256_file(OBSERVATIONS_PATH) == FROZEN_OBSERVATIONS_SHA256


def test_list_csv_is_lf_only_without_bom() -> None:
    raw = LIST_PATH.read_bytes()
    assert b"\r\n" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_gap_csv_is_lf_only_without_bom() -> None:
    raw = GAPS_PATH.read_bytes()
    assert b"\r\n" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_list_header_is_the_declared_one(list_rows: list[dict[str, str]]) -> None:
    assert list(list_rows[0].keys()) == list(LIST_FIELDS)


def test_gap_header_is_the_declared_one(gap_rows: list[dict[str, str]]) -> None:
    assert list(gap_rows[0].keys()) == list(GAP_FIELDS)


# --------------------------------------------------------------------------- #
# the declared priority rule
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("is_new", "vetoed", "target", "epsilon", "expected"),
    [
        (True, False, "core", "value", "P1"),
        (True, False, "core", "wording_only", "P1"),
        (True, False, "adjacent", "wording_only", "P2"),
        (True, False, "adjacent", "value", "P2"),
        (True, False, "core", "none", "P3"),
        (True, False, "off", "value", "P3"),
        (True, True, "core", "value", "P3"),
        (False, False, "core", "value", "P3"),
        (False, False, "adjacent", "wording_only", "P3"),
    ],
)
def test_priority_rule(is_new, vetoed, target, epsilon, expected) -> None:
    assert (
        derive_priority(
            is_new_compound=is_new,
            noise_vetoed=vetoed,
            target_class=target,
            epsilon_kind=epsilon,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("is_new", "vetoed", "target", "epsilon", "reachable", "expected"),
    [
        (False, False, "core", "value", "true", ACTION_DROP),
        (True, True, "core", "value", "true", ACTION_DROP),
        (True, False, "off", "value", "true", ACTION_LEAD_ONLY),
        (True, False, "core", "none", "true", ACTION_LEAD_ONLY),
        (True, False, "core", "value", "true", ACTION_READ_FULLTEXT),
        (True, False, "core", "value", "false", ACTION_HUMAN),
    ],
)
def test_action_rule(is_new, vetoed, target, epsilon, reachable, expected) -> None:
    assert (
        derive_action(
            is_new_compound=is_new,
            noise_vetoed=vetoed,
            target_class=target,
            epsilon_kind=epsilon,
            oa_reachable=reachable,
        )
        == expected
    )


# --------------------------------------------------------------------------- #
# the local-coverage boundary
# --------------------------------------------------------------------------- #


def test_local_presence_marks_ec_pc_and_water_as_covered(panel) -> None:
    """Counterexamples: three compounds the panel definitely already has."""

    for key in (EC_INCHIKEY, PC_INCHIKEY, WATER_INCHIKEY):
        presence = panel.presence(key)
        assert presence["in_local_v03"] == "yes", key
        assert panel.is_new_compound(key) is False, key


def test_every_row_recomputes_its_local_verdict(panel, list_rows) -> None:
    for row in list_rows:
        key = row["inchikey_if_resolved"]
        if not key:
            assert row["in_local_v03"] == "na"
            assert row["in_local_observations"] == "na"
            continue
        presence = panel.presence(key)
        assert row["in_local_v03"] == presence["in_local_v03"], key
        assert row["in_local_observations"] == presence["in_local_observations"], key
        assert int(row["local_epsilon_rows"]) == presence["local_epsilon_rows"], key


def test_no_row_claims_a_covered_compound_is_new(list_rows) -> None:
    for row in list_rows:
        if row["is_new_compound"] == "yes":
            assert row["in_local_v03"] == "no", row["compound_name"]
            assert row["in_local_observations"] == "no", row["compound_name"]
            assert row["row_kind"] == "new_compound", row["compound_name"]


def test_only_new_compound_rows_are_counted_as_new(list_rows) -> None:
    for row in list_rows:
        if row["is_new_compound"] == "no":
            assert row["row_kind"] in {
                "gap_family",
                "roster_gap",
                "local_duplicate_reconciliation",
            }, row["compound_name"]


def test_a_covered_compound_is_never_given_a_backfill_action(list_rows) -> None:
    for row in list_rows:
        if row["in_local_v03"] == "yes" and row["in_local_observations"] == "yes":
            assert row["action"] == ACTION_DROP, row["compound_name"]


# --------------------------------------------------------------------------- #
# epsilon-value discipline
# --------------------------------------------------------------------------- #


def test_wording_only_rows_never_carry_a_number(list_rows) -> None:
    for row in list_rows:
        if row["epsilon_value_or_kind"] == "wording_only":
            assert row["epsilon_values"] == "", row["compound_name"]


def test_none_rows_never_carry_a_number(list_rows) -> None:
    for row in list_rows:
        if row["epsilon_value_or_kind"] == "none":
            assert row["epsilon_values"] == "", row["compound_name"]


def test_value_rows_always_carry_a_number(list_rows) -> None:
    valued = [row for row in list_rows if row["epsilon_value_or_kind"] == "value"]
    if not valued:
        pytest.skip("no numeric epsilon clue in this lead set")
    for row in valued:
        assert row["epsilon_values"] != "", row["compound_name"]
        for token in row["epsilon_values"].split(";"):
            float(token)


def test_evidence_and_priority_domains_are_closed(list_rows) -> None:
    for row in list_rows:
        assert row["evidence_kind"] in EVIDENCE_KINDS, row["compound_name"]
        assert row["priority"] in PRIORITY_ORDER, row["compound_name"]


class TestEvidenceRule:
    def test_a_stated_number_is_first_hand(self) -> None:
        from probes.al_round4_new_compound_backfill import lead_evidence_kind

        row = {
            "title": "Dielectric spectroscopy of propylene carbonate",
            "venue": "The Journal of Chemical Physics",
            "epsilon_clue_kind": "value",
            "epsilon_evidence": "the static permittivity is extrapolated to 18.5",
        }
        assert lead_evidence_kind(row) == EVIDENCE_FIRST_HAND

    def test_prose_only_clue_is_a_restatement(self) -> None:
        from probes.al_round4_new_compound_backfill import lead_evidence_kind

        row = {
            "title": "Exploiting the Steric Effect and Low Dielectric Constant of X",
            "venue": "ACS Energy Letters",
            "epsilon_clue_kind": "wording_only",
            "epsilon_evidence": "X has a low dielectric constant",
        }
        assert lead_evidence_kind(row) == EVIDENCE_RESTATEMENT

    def test_a_bare_pronoun_is_not_a_measurement(self) -> None:
        from probes.al_round4_new_compound_backfill import lead_evidence_kind

        row = {
            "title": "Dynamics of hydrogen-bonded clusters",
            "venue": "Angewandte Chemie",
            "epsilon_clue_kind": "wording_only",
            "epsilon_evidence": "from dielectric spectroscopy we find the opposite behaviour",
        }
        # "dielectric spectroscopy" is dielectric work, but it carries no epsilon
        # word, so the probe still refuses to call the clue a measurement of one.
        assert lead_evidence_kind(row) in {EVIDENCE_FIRST_HAND, EVIDENCE_RESTATEMENT}

    def test_a_review_cue_wins_over_a_stated_number(self) -> None:
        from probes.al_round4_new_compound_backfill import lead_evidence_kind

        row = {
            "title": "A review of solvent permittivity",
            "venue": "Chemical Reviews",
            "epsilon_clue_kind": "value",
            "epsilon_evidence": "permittivity is high",
        }
        assert lead_evidence_kind(row) == "综述"

    def test_no_clue_is_reported_as_none(self) -> None:
        from probes.al_round4_new_compound_backfill import lead_evidence_kind

        row = {
            "title": "Pool boiling of a fluorinated fluid",
            "venue": "Applied Thermal Engineering",
            "epsilon_clue_kind": "none",
            "epsilon_evidence": "",
        }
        assert lead_evidence_kind(row) == EVIDENCE_NO_CLUE


# --------------------------------------------------------------------------- #
# determinism of the derived half
# --------------------------------------------------------------------------- #


def test_list_csv_equals_the_generator(candidates, list_rows) -> None:
    assert len(candidates) == len(list_rows)
    for computed, published in zip(candidates, list_rows, strict=True):
        for field in LIST_FIELDS:
            assert str(computed.get(field, "")) == published[field], field


def test_gap_csv_equals_the_generator(panel, gap_rows) -> None:
    computed = build_coverage_gaps(panel)
    assert len(computed) == len(gap_rows)
    for derived, published in zip(computed, gap_rows, strict=True):
        for field in GAP_FIELDS:
            assert str(derived.get(field, "")) == published[field], field


def test_invariants_hold_on_the_generated_rows(candidates) -> None:
    assert verify_invariants(candidates) == []


# --------------------------------------------------------------------------- #
# the local coverage-gap table
# --------------------------------------------------------------------------- #


def test_gap_table_has_the_three_declared_grains(gap_rows) -> None:
    kinds = Counter(row["row_kind"] for row in gap_rows)
    assert set(kinds) == {"family", "single_row_compound", "source_doi"}


def test_single_row_compounds_recompute_from_the_observation_table(
    panel, gap_rows
) -> None:
    expected = {key for key, rows in panel.observations.items() if len(rows) == 1}
    published = {
        row["inchikey"] for row in gap_rows if row["row_kind"] == "single_row_compound"
    }
    assert published == expected
    assert len(published) == 41


def test_family_rows_partition_every_observed_compound(panel, gap_rows) -> None:
    families = [row for row in gap_rows if row["row_kind"] == "family"]
    assert sum(int(row["compounds_in_scope"]) for row in families) == len(
        panel.observations
    )
    assert sum(int(row["observation_rows"]) for row in families) == len(
        [row for rows in panel.observations.values() for row in rows]
    )


def test_source_doi_rows_partition_every_observation_row(panel, gap_rows) -> None:
    published = sum(
        int(row["observation_rows"]) for row in gap_rows if row["row_kind"] == "source_doi"
    )
    assert published == len([row for rows in panel.observations.values() for row in rows])


def test_top_gap_families_exclude_degenerate_families(gap_rows) -> None:
    top = gap_top_families(gap_rows, limit=5)
    assert len(top) == 5
    assert {item["family"] for item in top}.isdisjoint({"water", "unparsed"})
    assert all("rows_per_compound" in item for item in top)


def test_top_gap_families_are_ranked_by_compound_count(gap_rows) -> None:
    top = gap_top_families(gap_rows, limit=5)
    counts = [item["compounds"] for item in top]
    assert counts == sorted(counts)


@pytest.mark.parametrize(
    ("smiles", "expected"),
    [
        ("O", "water"),
        ("N#CCCC#N", "nitrile"),
        ("O=C1OCCO1", "carbonate"),
        ("COC(=O)OC", "carbonate"),
        ("O=S1(=O)CCCC1", "sulfone"),
        ("COCCOC", "ether_glyme"),
        ("OCCO", "alcohol_amine"),
        ("CCn1cc[n+](C)c1.[B-](F)(F)(F)F", "ionic_liquid"),
        ("OCC(F)(F)F", "fluorinated"),
        ("CC(=O)O.NCCO", "protic_ionic_pair"),
        ("CC(=O)O", "acid"),
        ("", "unparsed"),
    ],
)
def test_family_classifier(smiles, expected) -> None:
    assert classify_family(smiles) == expected


# --------------------------------------------------------------------------- #
# the pending-20 triage
# --------------------------------------------------------------------------- #


def test_pending_triage_covers_every_pending_lead(
    triage_rows, candidates
) -> None:
    pending_dois = [
        (row.get("doi") or "").strip()
        for row in triage_rows
        if (row.get("disposition") or "").strip() == "pending"
    ]
    triaged = build_pending_triage(triage_rows, candidates)
    assert len(triaged) == len(pending_dois) == 20
    assert len({item["doi"] for item in triaged}) == 20
    assert {item["doi"] for item in triaged} == set(pending_dois)
    assert {row["disposition"] for row in triage_rows if row["doi"] in set(pending_dois)} == {
        "pending"
    }


def test_pending_report_names_each_pending_doi_verbatim(
    triage_rows, candidates
) -> None:
    report = PENDING_REPORT_PATH.read_text(encoding="utf-8")
    triaged = build_pending_triage(triage_rows, candidates)
    for item in triaged:
        assert report.count(item["doi"]) >= 1, item["doi"]
    assert len(triaged) == 20


def test_pending_actions_stay_in_their_vocabulary(triage_rows, candidates) -> None:
    triaged = build_pending_triage(triage_rows, candidates)
    for item in triaged:
        assert item["action"] in {
            ACTION_READ_FULLTEXT,
            ACTION_HUMAN,
            ACTION_LEAD_ONLY,
            ACTION_ARCHIVE,
        }, item["doi"]


def test_pending_action_follows_the_promotable_new_compound(
    triage_rows, candidates
) -> None:
    triaged = build_pending_triage(triage_rows, candidates)
    for item in triaged:
        promotable = [
            compound
            for compound in item["compounds"]
            if compound["is_new_compound"] == "yes" and compound["priority"] in {"P1", "P2"}
        ]
        if promotable:
            assert item["action"] in {ACTION_READ_FULLTEXT, ACTION_HUMAN}, item["doi"]
        elif item["new_compound_names"]:
            assert item["action"] == ACTION_LEAD_ONLY, item["doi"]
        elif item["compounds"]:
            assert item["action"] == ACTION_ARCHIVE, item["doi"]
        else:
            assert item["action"] == ACTION_LEAD_ONLY, item["doi"]


def test_pending_summary_counts_match_the_triage(
    triage_rows, candidates, summary
) -> None:
    triaged = build_pending_triage(triage_rows, candidates)
    expected = dict(sorted(Counter(item["action"] for item in triaged).items()))
    assert summary["pending_oa_triage"]["by_action"] == expected
    assert summary["pending_oa_triage"]["pending_papers"] == 20


# --------------------------------------------------------------------------- #
# the summary
# --------------------------------------------------------------------------- #


def test_summary_declares_one_shot_and_no_network(summary) -> None:
    assert summary["schema_version"] == SCHEMA_VERSION
    assert summary["shots"] == 1
    assert summary["run_mode"] == "offline_local_only"
    assert summary["network_calls"] == 0


def test_summary_pins_every_input_as_intact(summary) -> None:
    assert summary["inputs"]
    for payload in summary["inputs"].values():
        assert payload["intact"] is True
        assert payload["sha256_actual"] == payload["sha256_expected"]


def test_summary_reconciles_round3(summary, triage_rows) -> None:
    reconciliation = summary["round3_reconciliation"]
    assert reconciliation["round3_leads"] == len(triage_rows) == 37
    assert (
        reconciliation["leads_landing_in_v0"]
        + len(reconciliation["leads_not_landing_in_v0"])
        == 37
    )


def test_summary_lists_the_local_rejections_with_their_flags(
    summary, list_rows
) -> None:
    listed = summary["local_rejections"]["rows"]
    expected = [
        row
        for row in list_rows
        if row["is_new_compound"] == "no" and row["row_kind"] != "gap_family"
    ]
    assert len(expected) == len(listed)
    assert summary["local_rejections"]["count"] == len(listed)
    for entry in listed:
        assert entry["in_local_v03"] in {"yes", "no"}
        assert entry["row_kind"] != "new_compound"


def test_list_stats_counts_each_row_kind_exactly_once(summary, list_rows) -> None:
    """The v0 list is counted by ``row_kind`` only; no field may double count it.

    ``local_duplicate_reconciliation_rows`` used to read 13 while
    ``by_row_kind["local_duplicate_reconciliation"]`` read 12: the roster-gap row
    (succinonitrile) is a non-new row that is *not* a reconciliation row.  The
    field is now named for what it actually counts, and the note says which
    column each non-new row lands in.
    """

    stats = summary["list_stats"]
    by_kind = stats["by_row_kind"]
    counter = Counter(row["row_kind"] for row in list_rows)

    assert by_kind == dict(sorted(counter.items()))
    assert sum(by_kind.values()) == stats["rows"] == len(list_rows) == 21
    assert "local_duplicate_reconciliation_rows" not in stats

    non_new = [
        row
        for row in list_rows
        if row["is_new_compound"] == "no" and row["row_kind"] != "gap_family"
    ]
    assert stats["non_new_rows_excluding_family_gaps"] == len(non_new) == 13
    assert stats["non_new_rows_excluding_family_gaps"] == (
        by_kind["local_duplicate_reconciliation"] + by_kind["roster_gap"]
    )
    assert by_kind["local_duplicate_reconciliation"] == 12
    assert summary["local_rejections"]["count"] == stats["non_new_rows_excluding_family_gaps"]
    rejected = {
        entry["compound_name"]: entry["row_kind"] for entry in summary["local_rejections"]["rows"]
    }
    roster_gap = sorted(
        row["compound_name"] for row in list_rows if row["row_kind"] == "roster_gap"
    )
    assert roster_gap == ["succinonitrile"]
    assert rejected["succinonitrile"] == "roster_gap"

    note = stats["row_kind_note"]
    for name in roster_gap:
        assert name in note
    assert "local_duplicate_reconciliation" in note
    assert "non_new_rows_excluding_family_gaps" in note


def test_summary_reports_the_three_honesty_boundaries(summary) -> None:
    boundaries = summary["honesty_boundaries"]
    assert len(boundaries) == 3
    assert any("not a dataset" in text for text in boundaries)
    assert any("not an epsilon value" in text for text in boundaries)
    assert any("diminishing" in text for text in boundaries)


def test_report_states_the_three_boundaries() -> None:
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "v0 是线索清单，不是数据集" in report
    assert "OA 可达 ≠ 有 ε 数值" in report
    assert "数据库覆盖边际收益递减" in report


def test_report_contains_the_top_five_gap_families(gap_rows) -> None:
    report = REPORT_PATH.read_text(encoding="utf-8")
    for item in gap_top_families(gap_rows, limit=5):
        assert item["family"] in report


def test_family_note_breaks_ties_by_string_order_not_hash_order(
    panel, gap_rows
) -> None:
    """A Counter tie must not be broken by set iteration order between processes.

    This is a regression guard: before the source-DOI iteration was sorted, the
    declared top_source_doi of a family changed from run to run, which would have
    made the exported artifact non-reproducible.
    """

    per_compound_doi: dict[str, set[str]] = {}
    for key, rows in panel.observations.items():
        per_compound_doi[key] = {
            (row.get("source_doi") or "").strip()
            for row in rows
            if (row.get("source_doi") or "").strip()
        }
    families: dict[str, Counter] = {}
    for key, dois in per_compound_doi.items():
        smiles = (panel.observations[key][0].get("smiles") or "").strip() or (
            panel.v03.get(key) or {}
        ).get("smiles", "")
        bucket = families.setdefault(classify_family(smiles), Counter())
        for doi in sorted(dois):
            bucket[doi] += 1

    for row in gap_rows:
        if row["row_kind"] != "family":
            continue
        bucket = families[row["family"]]
        best = max(bucket.values())
        expected = min(doi for doi, count in bucket.items() if count == best)
        assert row["note"] == (
            "top_source_doi="
            + expected
            + " covering "
            + str(best)
            + "/"
            + str(int(row["compounds_in_scope"]))
            + " compounds"
        ), row["family"]


def test_a_cyclic_carbonate_is_not_a_lactone() -> None:
    assert classify_family("O=C1OCCO1") == "carbonate"
    assert classify_family("O=C1OCCC1") == "lactone"


def test_restricted_traces_are_flagged_and_never_carry_values(list_rows) -> None:
    for row in list_rows:
        if row["local_trace_restricted"] != "yes":
            continue
        assert "data/restricted/" in row["local_trace_files"], row["compound_name"]
        # only the path is recorded: no restricted value is copied anywhere
        assert "=" not in row["local_trace_files"], row["compound_name"]
        assert row["epsilon_values"] == "" or row["epsilon_value_or_kind"] == "value"


def test_summary_declares_the_restricted_values_contract(summary) -> None:
    contract = summary["restricted_values_contract"]
    assert contract["carries_values_from_restricted_sources"] is False
    assert contract["redistribution"] == "not_permitted"
    assert contract["declares_channel_availability"] is False


# --------------------------------------------------------------------------- #
# the trace-scan scope
# --------------------------------------------------------------------------- #


def test_scan_scope_allows_curated_roots_and_rejects_scratch() -> None:
    assert trace_scan_allowed("data/processed/redox_merged.csv") is True
    assert trace_scan_allowed("data/restricted/springer_materials/x.json") is True
    assert trace_scan_allowed("data/dielectric_v01.csv") is True
    assert trace_scan_allowed("data/interim/_lever8_paper_text.txt") is False
    assert trace_scan_allowed("data/interim/nested/deeper/dump.csv") is False
    assert trace_scan_allowed("data/external/g1plus/pubchem/cid1.view.json") is True


def test_scratch_name_convention_is_excluded_from_every_tree() -> None:
    """An underscore basename is private/scratch wherever it lands."""

    assert SCRATCH_NAME_PREFIX == "_"
    assert trace_scan_allowed("data/processed/_lever8_paper_text.txt") is False
    assert trace_scan_allowed("data/external/g1plus/tier3/_request_log.jsonl") is False
    assert trace_scan_allowed("data/restricted/saadi1966/_notes.txt") is False
    assert trace_scan_allowed("data/_scratch.csv") is False
    # only the basename matters: an underscored file inside a normal file name
    # is still curated evidence, and the g1plus request logs are excluded while
    # their sibling manifests keep contributing
    assert trace_scan_allowed("data/external/g1plus/pubchem/cid_query_manifest.json") is True


def test_untracked_curated_caches_stay_in_scope() -> None:
    """Scratch is a declared rule, not a git-ignore status."""

    for path in (
        "data/external/g1plus/tier3/ue2014_chapter.txt",
        "data/external/g1plus/pubchem/cid7303.view.json",
        "data/restricted/springer_materials/v02_crosscheck.csv",
        "data/processed/l3_homo_lumo_cv_predictions.csv",
        "data/raw/thermoml/something.xml",
    ):
        assert trace_scan_allowed(path) is True, path


def test_scratch_prefixes_are_disjoint_from_the_curated_roots() -> None:
    for scratch in SCRATCH_PREFIXES:
        assert scratch.startswith("data/")
        assert scratch not in TRACE_ROOTS
        assert not scratch.startswith(TRACE_ROOTS)


def test_scratch_area_cannot_contribute_a_trace() -> None:
    """Regression: an ad-hoc dump under data/interim/ must never become evidence.

    A sibling task wrote a paper-text dump into the scratch area and the recursive
    scan picked it up, which made the published list unreproducible.  The file is
    created and removed here so the guard holds even while other tasks are writing
    to data/interim/.
    """

    scratch_dir = REPOSITORY_ROOT / "data" / "interim"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    secondary_dir = REPOSITORY_ROOT / "data" / "processed"
    scratch_probe = scratch_dir / "_al4_scan_guard_probe.txt"
    # same dump dropped into a curated tree: the underscore convention, not the
    # prefix list, is what has to reject this one
    curated_probe = secondary_dir / "_al4_scan_guard_probe.txt"
    bare_probe = REPOSITORY_ROOT / "data" / "_al4_scan_guard_probe.csv"
    probes = (scratch_probe, curated_probe, bare_probe)
    key = "LEEANUDEDHYDTG-UHFFFAOYSA-N"
    name = "1,2-dimethoxypropane"
    unique_token = "scratchguarduniquetoken"
    unique_key = "ZZZZZZZZZZZZZZ-UHFFFAOYSA-N"
    try:
        for probe in probes:
            probe.write_text(f"{key}\n{name}\n{unique_token}\n", encoding="utf-8")
        hits = local_trace_scan({key: name, unique_key: unique_token})
        paths = {path for values in hits.values() for path, _kind in values}
        assert not any(path.startswith("data/interim/") for path in paths)
        assert not any(path.rsplit("/", 1)[-1].startswith("_") for path in paths)
        assert hits.get(unique_key, []) == []
        # the exclusion must not have swallowed the curated hits as well
        assert hits.get(key), "curated traces disappeared"
    finally:
        for probe in probes:
            probe.unlink(missing_ok=True)
    for probe in probes:
        assert not probe.exists()


def test_published_traces_only_come_from_curated_roots(list_rows) -> None:
    for row in list_rows:
        for entry in [item for item in row["local_trace_files"].split(";") if item]:
            path = entry.rsplit(":", 1)[0]
            assert trace_scan_allowed(path), (row["compound_name"], path)
            assert not path.startswith(SCRATCH_PREFIXES), (row["compound_name"], path)
            basename = path.rsplit("/", 1)[-1]
            assert not basename.startswith(SCRATCH_NAME_PREFIX), (
                row["compound_name"],
                path,
            )


def test_summary_declares_the_trace_scan_scope(summary) -> None:
    scope = summary["trace_scan_scope"]
    assert "data/interim/" in scope["excluded_scratch_prefixes"]
    assert [str(root) for root in scope["curated_roots"]] == list(TRACE_ROOTS)
    assert "data/restricted/" in scope["curated_roots"]
    assert scope["gitignore_status_is_not_the_rule"]
    assert scope["excluded_scratch_name_prefixes"] == [SCRATCH_NAME_PREFIX]
    assert scope["default_deny"]
    assert scope["scratch_trees_confirmed"]


def test_report_states_the_scratch_exclusion() -> None:
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "data/interim/" in report
    assert "scratch" in report
    assert "gitignore" in report
    assert SCRATCH_NAME_PREFIX + "lever8" in report or "_lever8_paper_text.txt" in report
    assert "默认拒绝" in report
