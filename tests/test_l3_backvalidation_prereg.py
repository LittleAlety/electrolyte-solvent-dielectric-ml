"""Guards for the L3 back-validation pre-registration.

A pre-registration is only worth the paper it is written on if it cannot be
quietly relaxed once results are in.  These tests pin the locked constants to
three independent sources: the machine-readable registration, the frozen table
the champions are quoted from, and the prose copy in ``reports/decisions_log.md``.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import itertools
import json
import pathlib

from probes.manual_appendix_reconciliation import DEFAULT_MANUAL

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
PREREG_PATH = REPOSITORY_ROOT / "probes" / "l3_backvalidation_prereg.json"
FROZEN_TABLE = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
DECISIONS_LOG = REPOSITORY_ROOT / "reports" / "decisions_log.md"

REGISTRATION_HEADING = "## 2026-09-26 · Week 12 §14"

# The four champions, exactly as the frozen table carries them.  Kept as a
# literal so a silent edit to either side shows up as a failure rather than as
# the two sides agreeing with each other about the wrong thing.
CHAMPIONS = {
    "EC": ("ethylene carbonate", "KMTRUDSVKNLOMY-UHFFFAOYSA-N", 90.5, 313.15, True),
    "PC": ("propylene carbonate", "RUOJZAUFBMNUDX-UHFFFAOYSA-N", 64.9, 298.15, True),
    "FEC": ("fluoroethylene carbonate", "SBLRHMKNNHXPHG-UHFFFAOYSA-N", 78.4, 296.15, False),
    "VC": ("vinylene carbonate", "VAYTZRYEBVHVLE-UHFFFAOYSA-N", 126.0, 298.0, False),
}
FROZEN_SHA256 = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"


# The scoring run itself must write its summary here.  ``pool_rule`` reserves
# runtime fields for the frozen pool; this path is what turns those fields into
# a gate -- a scoring artifact cannot exist next to an unfrozen pool.
SCORING_ARTIFACT = REPOSITORY_ROOT / "probes" / "l3_backvalidation_run_summary.json"
POOL_RUNTIME_FIELDS = ("pool_path", "pool_sha256", "pool_size_by_list")


def _registration() -> dict:
    return json.loads(PREREG_PATH.read_text(encoding="utf-8"))


def _frozen_rows() -> dict[str, dict[str, str]]:
    with FROZEN_TABLE.open(encoding="utf-8", newline="") as handle:
        return {row["inchikey"]: row for row in csv.DictReader(handle)}


def _registration_prose() -> str:
    text = DECISIONS_LOG.read_text(encoding="utf-8")
    start = text.index(REGISTRATION_HEADING)
    tail = text[start + len(REGISTRATION_HEADING):]
    end = tail.find("\n## ")
    return tail if end == -1 else tail[:end]


def test_registration_is_locked_and_timestamped() -> None:
    registration = _registration()
    assert registration["status"] == "LOCKED"
    assert registration["schema_version"] == 1
    stamp = registration["locked_at_utc"]
    assert stamp.endswith("Z")
    parsed = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.UTC
    )
    assert parsed.year >= 2026


def test_champions_match_the_frozen_table_verbatim() -> None:
    registration = _registration()
    declared = registration["champion_set"]["solvent_list"] + registration["champion_set"]["additive_list"]
    assert len(declared) == 4
    rows = _frozen_rows()
    for champion in declared:
        short = champion["short"]
        name, inchikey, dielectric, temperature, model_ready = CHAMPIONS[short]
        assert champion["inchikey"] == inchikey
        assert champion["name"] == name
        assert float(champion["truth_dielectric"]) == dielectric
        assert float(champion["truth_T_K"]) == temperature
        assert champion["model_ready"] is model_ready
        row = rows[inchikey]
        assert row["name"].strip().lower() == name
        assert float(row["dielectric"]) == dielectric
        assert float(row["T_K"]) == temperature
        assert (row["model_ready"] == "true") is model_ready


def test_frozen_table_digest_matches_the_pin() -> None:
    digest = hashlib.sha256(FROZEN_TABLE.read_bytes()).hexdigest()
    assert digest == FROZEN_SHA256
    assert _registration()["frozen_table"]["sha256"] == FROZEN_SHA256


def test_locked_thresholds_are_the_pre_registered_numbers() -> None:
    criteria = _registration()["criteria"]
    assert criteria["C1_recall_at_K"]["K"] == 20
    assert criteria["C1_recall_at_K"]["champions_required_in_top_k_total"] == 4
    assert criteria["C2_magnitude_solvent"]["max_abs_delta_log10_epsilon"] == 0.10
    assert criteria["C2_additive"]["max_abs_delta_ev"] == 0.15
    assert criteria["C3_negative_control"]["permutation_seed"] == 20260928
    assert criteria["C3_negative_control"]["max_champion_hits"] == 1
    assert criteria["pass_expression"] == "C1 and C2_solvent and C2_additive and C3"
    assert _registration()["pool_rule"]["min_scored_per_list"] == 100


def test_the_additive_tolerance_reuses_the_existing_redox_gate() -> None:
    """0.15 eV is not invented here; it is the project's own redox gate."""

    criteria = _registration()["criteria"]
    assert criteria["C2_additive"]["source_of_threshold"].endswith("gate.threshold_mae")
    redox = json.loads(
        (REPOSITORY_ROOT / "probes" / "p4_redox_summary.json").read_text(encoding="utf-8")
    )
    assert redox["gate"]["threshold_mae"] == criteria["C2_additive"]["max_abs_delta_ev"]


def test_champion_asymmetry_is_recorded_not_flattened() -> None:
    """FEC and VC are already withheld; EC and PC are not.  Say so."""

    registration = _registration()
    solvents = {item["short"]: item for item in registration["champion_set"]["solvent_list"]}
    additives = {item["short"]: item for item in registration["champion_set"]["additive_list"]}
    assert solvents["EC"]["already_withheld_from_dielectric_fit"] is False
    assert solvents["PC"]["already_withheld_from_dielectric_fit"] is False
    assert additives["FEC"]["already_withheld_from_dielectric_fit"] is True
    assert additives["VC"]["already_withheld_from_dielectric_fit"] is True
    for item in list(solvents.values()) + list(additives.values()):
        assert item["already_withheld_from_dielectric_fit"] is (not item["model_ready"])


def test_exclusion_covers_all_four_levels() -> None:
    levels = _registration()["exclusion_levels"]
    assert len(levels) == 4
    for marker in ("L1", "L2", "L3", "L4"):
        assert any(marker in level for level in levels)


def test_prose_copy_in_the_decisions_log_quotes_every_locked_constant() -> None:
    prose = _registration_prose()
    for short, (_, inchikey, _, _, _) in CHAMPIONS.items():
        assert inchikey in prose, f"{short} InChIKey missing from the prose copy"
    for needle in (
        "K = 20",
        "0.10",
        "0.15 eV",
        "20260928",
        "100 个可评分分子",
        "probes/l3_backvalidation_prereg.json",
        "stage_1_pilot_not_a_verdict",
    ):
        assert needle in prose, f"prose copy no longer quotes {needle!r}"


def test_prose_copy_states_the_conjunction_and_the_no_relaxation_rule() -> None:
    prose = _registration_prose()
    assert "C1 ∧ C2_solvent ∧ C2_additive ∧ C3" in prose
    assert "先锁后跑" in prose
    assert "不得" in prose


def test_pinned_inputs_still_exist() -> None:
    registration = _registration()
    pinned = registration["inputs_pinned"]
    assert "data/dielectric_v03.csv" in pinned
    for relative in pinned:
        assert (REPOSITORY_ROOT / relative).exists(), f"pinned input vanished: {relative}"


def test_manual_points_at_the_registration_when_present() -> None:
    if not DEFAULT_MANUAL.exists():
        return
    manual = DEFAULT_MANUAL.read_text(encoding="utf-8")
    assert "l3_backvalidation_prereg.json" in manual
    assert "stage_1_pilot_not_a_verdict" in manual


def test_pool_rule_carries_the_machine_readable_freeze_fields() -> None:
    """The pool rule's runtime fields must describe one consistent frozen pool.

    Before the stage-1 pilot ran, these four fields were the reserved
    ``null`` / ``false`` placeholders and this guard pinned them that way.
    Filling them is exactly what ``pool_rule.requirements`` item 5 asks for
    ("pool first to disk, sha256 recorded in this section"), so the guard now
    pins the *frozen* state instead: a path that exists, a digest that is that
    file's digest, and list sizes that clear the locked floor.

    What changed, stated precisely -- because "an assertion was only ever added"
    would be false.  An independent reviewer's flat diff of the week-12 snapshot
    shows the rewrite *replaced* the three `is None` placeholder assertions
    (`pool_path` / `pool_sha256` / `pool_size_by_list`) rather than keeping them
    beside a new check, and *flipped* the `pool_frozen_before_scoring is False`
    assertion to `is True`.  So one assertion each was rewritten, not added.  The
    net strength is higher (the replacements read the pool file off disk, re-hash
    it, and size-check every list), no check was dropped, and every locked
    constant is still re-asserted verbatim elsewhere in this file.
    """

    pool_rule = _registration()["pool_rule"]
    for field in POOL_RUNTIME_FIELDS:
        assert field in pool_rule, f"pool_rule lost its runtime field {field!r}"
    assert pool_rule["pool_frozen_before_scoring"] is True
    pool_path = REPOSITORY_ROOT / pool_rule["pool_path"]
    assert pool_path.is_file(), f"the frozen pool is missing: {pool_rule['pool_path']}"
    assert pool_rule["pool_sha256"] == hashlib.sha256(pool_path.read_bytes()).hexdigest(), (
        "pool_sha256 no longer matches the frozen pool on disk"
    )
    assert isinstance(pool_rule["pool_size_by_list"], dict)
    assert pool_rule["pool_size_by_list"]
    for list_name, size in pool_rule["pool_size_by_list"].items():
        assert size >= pool_rule["min_scored_per_list"], (
            f"{list_name} pool has {size} scored molecules, below the locked "
            f"minimum {pool_rule['min_scored_per_list']}"
        )
    assert pool_rule["amendment_2"]["locked_values_unchanged"] is True
    assert pool_rule["amendment_2"]["locked_values_touched"] == []
    assert pool_rule["amendment_2"]["kind"] == "runtime_field_fill_only"


def test_stage_1_pilot_cannot_be_read_as_a_verdict() -> None:
    pilot = _registration()["stage_1_pilot"]
    assert pilot["verdict_eligible"] is False


def test_pool_rule_amendment_preserves_every_locked_value() -> None:
    """The amendment adds metadata only; no locked number may move."""

    registration = _registration()
    pool_rule = registration["pool_rule"]
    amendment = pool_rule["amendment_1"]
    assert amendment["locked_values_unchanged"] is True
    assert amendment["locked_values_touched"] == []
    criteria = registration["criteria"]
    assert criteria["C1_recall_at_K"]["K"] == 20
    assert criteria["C2_magnitude_solvent"]["max_abs_delta_log10_epsilon"] == 0.10
    assert criteria["C2_additive"]["max_abs_delta_ev"] == 0.15
    assert criteria["C3_negative_control"]["permutation_seed"] == 20260928
    assert criteria["C3_negative_control"]["max_champion_hits"] == 1
    assert pool_rule["min_scored_per_list"] == 100
    assert criteria["pass_expression"] == "C1 and C2_solvent and C2_additive and C3"
    assert amendment["rationale_erratum"]["locked_threshold_unchanged"] == 0.10


def test_pool_must_be_frozen_on_disk_before_any_scoring_artifact_exists() -> None:
    """A scoring run cannot exist unless the pool was written down first.

    ``pool_rule`` reserves ``pool_path`` / ``pool_sha256`` / ``pool_size_by_list``
    / ``pool_frozen_before_scoring`` for the run itself.  If the scoring summary
    has been written while those fields are still empty, no pool was recorded at
    all, and the registration's own rule ("池必须先落盘为文件并记录 sha256，
    随后才允许评分") is broken.  What this gate proves is bounded: it proves the
    pool *was* written down and cleared its size floor by the time the run was
    reported.  It cannot prove the freeze happened before anyone saw the
    champions' ranks -- that ordering stays with discipline plus the
    ``pool_sha256`` timestamp audit.  Today the artifact does not exist, so the
    gate is a no-op -- it bites on the day someone runs the pool.
    """

    if not SCORING_ARTIFACT.exists():
        return
    pool_rule = _registration()["pool_rule"]
    message = (
        f"{SCORING_ARTIFACT.name} exists but pool_rule records no frozen pool: "
        "pool_frozen_before_scoring / pool_path / pool_sha256 / "
        "pool_size_by_list must all be filled in before scoring is reported"
    )
    assert pool_rule["pool_frozen_before_scoring"] is True, message
    assert pool_rule["pool_path"] is not None, message
    assert pool_rule["pool_sha256"] is not None, message
    assert isinstance(pool_rule["pool_size_by_list"], dict), message
    assert pool_rule["pool_size_by_list"], message
    for list_name, size in pool_rule["pool_size_by_list"].items():
        assert size >= pool_rule["min_scored_per_list"], (
            f"{list_name} pool has {size} scored molecules, below the locked "
            f"minimum {pool_rule['min_scored_per_list']}"
        )


# ---- amendment_3: per-channel fold sources, scoring clause, timestamps ------
#
# The week-13 adversarial review of the pre-registration found three gaps: the
# amendment's timestamps were stamped in the future, which made the "declared
# before executed" ordering unprovable; the new per-channel fold mapping had no
# guard at all; and the three champion-scoring clauses lived only in prose.  The
# guards below pin all three so the amendment cannot drift silently.

V2_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "dielectric_channel_v2_summary.json"
HOMO_LUMO_SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "homo_lumo_baselines_summary.json"
HOMO_LUMO_POOL_ROWS = 29515
CHAMPIONS_REMOVED_FROM_HOMO_LUMO_POOL = 4
UTC_STAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _utc(stamp: str) -> datetime.datetime:
    return datetime.datetime.strptime(stamp, UTC_STAMP_FORMAT).replace(tzinfo=datetime.UTC)


def _amendment_timeline() -> list[tuple[str, datetime.datetime]]:
    """Every stamp that must be ordered for `declared before executed`."""

    registration = _registration()
    return [
        ("locked_at_utc", _utc(registration["locked_at_utc"])),
        ("amendment_1", _utc(registration["pool_rule"]["amendment_1"]["amended_at_utc"])),
        ("amendment_2", _utc(registration["pool_rule"]["amendment_2"]["amended_at_utc"])),
        ("amendment_3", _utc(registration["fold_and_seed"]["amendment_3"]["amended_at_utc"])),
    ]


def test_amendment_3_records_the_per_channel_fold_source_and_scoring_clause() -> None:
    """The amendment must be machine-readable, not only prose.

    amendment_3 corrects which table supplies each channel's fold numbers and
    fixes how the champions are scored.  A review flagged that only the
    fold-source pointer was machine-readable: the three scoring clauses lived in
    prose alone, and the wording ("only the channel mapping") understated the
    change.  This pins the machine-readable copies, the verbatim preservation of
    the original fold_source / fold_policy, and the corrected wording.
    """

    registration = _registration()
    fold_and_seed = registration["fold_and_seed"]
    amendment = fold_and_seed["amendment_3"]

    by_channel = fold_and_seed["fold_source_by_channel"]
    assert set(by_channel) == {"dielectric_roster", "batt_p30k_homo_lumo"}
    assert by_channel["dielectric_roster"] == fold_and_seed["fold_source"]
    assert (REPOSITORY_ROOT / by_channel["dielectric_roster"]).is_file()
    assert "RepeatedKFold(5,10,42)" in by_channel["batt_p30k_homo_lumo"]
    assert "29,515" in by_channel["batt_p30k_homo_lumo"]
    assert "fold_source_by_channel" in amendment["fold_source_by_channel"]

    # "only add, never rewrite": both locked prose fields must survive verbatim.
    preserved = amendment["original_text_preserved"]
    assert preserved["fold_source"] == fold_and_seed["fold_source"]
    assert preserved["fold_policy"] == fold_and_seed["fold_policy"]

    scope = amendment["why_this_is_not_a_threshold_relaxation"]
    assert "冠军评分口径" in scope
    assert "champion_scoring_clause" in scope
    assert "只补正" not in scope

    clause = amendment["champion_scoring_clause"]
    assert isinstance(clause, dict)
    for roman in ("i", "ii", "iii"):
        assert clause.get(roman), f"champion_scoring_clause lost clause ({roman})"
    assert clause["pool_rows_before_champion_removal"] == 29519
    assert clause["pool_rows_after_champion_removal"] == HOMO_LUMO_POOL_ROWS
    assert clause["l1_strictly_satisfied"] is True

    resolution = amendment["resolution"]
    assert "29,515" in resolution
    assert "champion_scoring_clause" in resolution

    note = amendment["amended_at_utc_note"]
    assert isinstance(note, str) and note.strip()
    assert "2026-09-25" in note


def test_amendment_3_timestamps_are_monotonic_and_precede_the_consuming_artifact() -> None:
    """A revision cannot be consumed before it is amended.

    `probes/dielectric_channel_v2_summary.json` pins the digest produced by
    amendment_3, so its `generated_at_utc` must be later than that amendment.  A
    review found amendment_2 and amendment_3 stamped in the future, which broke
    exactly this ordering.  The guard keeps the timeline monotonic and anchored
    to files on disk, so it does not depend on the wall clock.
    """

    timeline = _amendment_timeline()
    for (earlier_name, earlier), (later_name, later) in itertools.pairwise(timeline):
        assert earlier < later, f"{earlier_name} must precede {later_name}"

    consumed_at = _utc(
        json.loads(V2_SUMMARY_PATH.read_text(encoding="utf-8"))["generated_at_utc"]
    )
    for name, stamp in timeline[1:]:
        assert stamp < consumed_at, (
            f"{name} ({stamp.isoformat()}) must be earlier than the artifact "
            f"that pins its digest ({consumed_at.isoformat()})"
        )

    mtime = datetime.datetime.fromtimestamp(PREREG_PATH.stat().st_mtime, datetime.UTC)
    for name, stamp in timeline:
        assert stamp <= mtime, f"{name} ({stamp.isoformat()}) postdates the registration file"


def test_amendment_3_pool_size_is_interlocked_with_the_homo_lumo_summary() -> None:
    """The amended pool size must match the artifact that built the pool.

    amendment_3 says the four champions were removed whole (29,519 -> 29,515).
    That number is only meaningful if it agrees with
    `probes/homo_lumo_baselines_summary.json.pool_rows`, the artifact that
    actually constructed the pool.
    """

    homo_lumo = json.loads(HOMO_LUMO_SUMMARY_PATH.read_text(encoding="utf-8"))
    assert homo_lumo["pool_rows"] == HOMO_LUMO_POOL_ROWS == 29515

    clause = _registration()["fold_and_seed"]["amendment_3"]["champion_scoring_clause"]
    assert clause["pool_rows_after_champion_removal"] == homo_lumo["pool_rows"]
    assert (
        clause["pool_rows_before_champion_removal"] - clause["pool_rows_after_champion_removal"]
        == CHAMPIONS_REMOVED_FROM_HOMO_LUMO_POOL
    )
    assert len(homo_lumo["champions_excluded"]) == CHAMPIONS_REMOVED_FROM_HOMO_LUMO_POOL

    by_channel = _registration()["fold_and_seed"]["fold_source_by_channel"]
    assert f"{HOMO_LUMO_POOL_ROWS:,}" in by_channel["batt_p30k_homo_lumo"]
