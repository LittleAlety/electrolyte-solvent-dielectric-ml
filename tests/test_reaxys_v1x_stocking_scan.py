"""Guards for the Reaxys v1.x stocking scan.

The queue half of the artifact is derived, so it is pinned by re-derivation: the
CSV must equal what the generator computes from the frozen pool and the local
observation table. The probe half is a transcription of a manual, logged-in
Reaxys session and cannot be re-derived offline, so it is pinned by its own
declarations -- every reading restricted, the net-new total consistent, the
single net-new source named, and the champion cross-check reported with the
right strength, and -- after the first adversarial review -- the champion
cross-check is pinned to the *evidence chain* rather than to a bare adjective:
the two declared sources must be distinct, and the conclusion they are said to
support must be verbatim in the file the chain cites.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from probes.manual_appendix_reconciliation import REPOSITORY_ROOT
from probes.reaxys_v1x_stocking_scan import (
    OBS_SHA256,
    POOL_SHA256,
    PROBED_INCHIKEY,
    QUEUE_FIELDS,
    QUEUE_PATH,
    READINGS,
    REPORT_PATH,
    SUMMARY_PATH,
    build_queue,
    classify,
)

FROZEN = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
POOL_CSV = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_pool.csv"
FROZEN_SHA256 = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
POOL = REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_pool.csv"
OBSERVATIONS = REPOSITORY_ROOT / "data" / "processed" / "dielectric_observations_v11plus.csv"
VERIFIER = REPOSITORY_ROOT / "probes" / "verify_reaxys_v1x_stocking_scan.py"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def queue() -> list[dict[str, str]]:
    return _rows(QUEUE_PATH)


@pytest.fixture(scope="module")
def summary() -> dict[str, object]:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pool_by_key() -> dict[str, dict[str, str]]:
    return {r["inchikey"]: r for r in _rows(POOL_CSV)}


def test_queue_csv_is_lf_only_without_bom() -> None:
    raw = QUEUE_PATH.read_bytes()
    assert b"\r\n" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_queue_header_is_the_declared_one(queue: list[dict[str, str]]) -> None:
    assert list(queue[0].keys()) == QUEUE_FIELDS


def test_queue_ranks_are_dense_and_ordered(queue: list[dict[str, str]]) -> None:
    assert [int(r["queue_rank"]) for r in queue] == list(range(1, len(queue) + 1))
    assert len({r["inchikey"] for r in queue}) == len(queue)


def test_queue_row_count_matches_the_generator(queue: list[dict[str, str]]) -> None:
    derived, stats = build_queue()
    assert len(derived) == len(queue) == stats["queue_size"]


def test_queue_is_exactly_the_pool_members_without_a_temperature_series(
    queue: list[dict[str, str]],
) -> None:
    """A pool member belongs here iff the observation table gives it <2 distinct T."""
    distinct: dict[str, set[float]] = {}
    for row in _rows(OBSERVATIONS):
        try:
            distinct.setdefault(row["inchikey"], set()).add(round(float(row["T_K"]), 2))
        except (TypeError, ValueError):
            pass
    expected = {r["inchikey"] for r in _rows(POOL) if len(distinct.get(r["inchikey"], set())) < 2}
    assert {r["inchikey"] for r in queue} == expected


def test_no_queue_row_has_a_temperature_series(queue: list[dict[str, str]]) -> None:
    assert all(int(r["local_distinct_T"]) < 2 for r in queue)


def test_local_distinct_t_recomputes_from_the_observation_table(
    queue: list[dict[str, str]],
) -> None:
    distinct: dict[str, set[float]] = {}
    for row in _rows(OBSERVATIONS):
        try:
            distinct.setdefault(row["inchikey"], set()).add(round(float(row["T_K"]), 2))
        except (TypeError, ValueError):
            pass
    for row in queue:
        assert int(row["local_distinct_T"]) == len(distinct.get(row["inchikey"], set()))


def test_queue_is_sorted_by_priority_then_family_then_key(queue: list[dict[str, str]]) -> None:
    order = {"P1": 0, "P2": 1, "P3": 2}
    keys = [(order[r["stocking_priority"]], r["family_tag"], r["inchikey"]) for r in queue]
    assert keys == sorted(keys)


def test_the_two_champions_are_in_the_queue_as_ordinary_members(
    queue: list[dict[str, str]],
) -> None:
    champions = {r["champion_short"] for r in queue if r["is_champion"].strip().lower() == "true"}
    assert {"EC", "PC"} <= champions
    assert all(r["stocking_priority"] == "P1" for r in queue if r["champion_short"] in {"EC", "PC"})


def test_this_probe_never_touched_the_frozen_inputs() -> None:
    assert hashlib.sha256(POOL.read_bytes()).hexdigest() == POOL_SHA256
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest() == FROZEN_SHA256
    assert hashlib.sha256(OBSERVATIONS.read_bytes()).hexdigest() == OBS_SHA256


def test_every_non_derived_column_is_reproduced_from_its_source(
    queue: list[dict[str, str]], pool_by_key: dict[str, dict[str, str]],
) -> None:
    """The queue may not invent target values, flags, or a family tag.

    The first adversarial review forged ``target_dielectric=11.1``,
    ``target_T_K=999.0`` and ``local_rows=42`` by hand and the verifier still
    reported 36/36, because it only re-derived ``local_distinct_T``. Every other
    column is now checked against the pool or against ``classify()``.
    """
    for row in queue:
        pool_row = pool_by_key[row["inchikey"]]
        assert row["target_dielectric"] == pool_row["target_dielectric"]
        assert row["target_T_K"] == pool_row["T_K"]
        assert row["is_champion"] == pool_row["is_champion"]
        assert row["champion_short"] == pool_row["champion_short"]
        assert row["model_ready"] == pool_row["model_ready"]
        assert row["name"] == pool_row["name"]
        assert row["smiles"] == pool_row["smiles"]
        assert row["family_tag"] == classify(row["name"])


def test_local_rows_recomputes_from_the_observation_table(queue: list[dict[str, str]]) -> None:
    counts: dict[str, int] = {}
    for row in _rows(OBSERVATIONS):
        counts[row["inchikey"]] = counts.get(row["inchikey"], 0) + 1
    for row in queue:
        assert int(row["local_rows"]) == counts.get(row["inchikey"], 0)


def test_p1_is_exactly_the_champion_rows(queue: list[dict[str, str]]) -> None:
    """P1 must be derived from the pool flag, not hard-coded compound names."""
    p1 = {r["inchikey"] for r in queue if r["stocking_priority"] == "P1"}
    champions = {r["inchikey"] for r in queue if r["is_champion"].strip().lower() == "true"}
    assert p1 == champions
    assert len(p1) == 2
    assert {r["champion_short"] for r in queue if r["inchikey"] in champions} == {"EC", "PC"}


def test_access_is_derived_per_row_not_asserted_for_the_file(
    queue: list[dict[str, str]],
) -> None:
    probed = set(PROBED_INCHIKEY.values())
    probed_rows = 0
    for row in queue:
        expected_flag = "yes" if row["inchikey"] in probed else "no"
        assert row["probed_in_this_round"] == expected_flag
        if expected_flag == "yes":
            probed_rows += 1
            assert row["access"] == "public_local_metadata_plus_manual_reaxys_probe"
        else:
            assert row["access"] == "public_local_metadata_only_not_yet_probed"
    assert probed_rows == 3
    assert {r["access"] for r in queue} == {
        "public_local_metadata_plus_manual_reaxys_probe",
        "public_local_metadata_only_not_yet_probed",
    }


def test_the_two_temperature_series_counts_carry_their_own_scope(
    summary: dict[str, object],
) -> None:
    """236 / 167 / 106 must never be added together again.

    The first version reported the observation-table count (106) in a sentence
    about the pool, which contradicts its own queue size (167 + 106 != 236). The
    real pool figure is 69, and the partition identity is now asserted.
    """
    stats = summary["queue_stats"]
    assert stats["queue_size"] + stats["pool_members_with_two_or_more_distinct_T"] == \
        stats["pool_distinct_keys"] == 236
    assert stats["pool_members_with_two_or_more_distinct_T"] == 69
    assert stats["observation_table_compounds_with_two_or_more_distinct_T"] == 106
    assert stats["observation_compounds"] == 153
    assert "compounds_with_two_or_more_distinct_T" not in stats
    assert stats["p1_equals_champion_rows"] is True


def test_summary_queue_stats_match_the_csv(queue: list[dict[str, str]], summary: dict[str, object]) -> None:
    stats = summary["queue_stats"]
    assert stats["queue_size"] == len(queue)
    assert sum(stats["queue_by_priority"].values()) == len(queue)
    assert sum(stats["queue_by_family"].values()) == len(queue)
    assert summary["pool_sha256"] == POOL_SHA256


def test_every_reading_is_restricted_and_names_a_verdict(summary: dict[str, object]) -> None:
    readings = summary["readings"]
    assert len(readings) == len(READINGS) >= 7
    for reading in readings:
        assert reading["verdict"]
        assert isinstance(reading["reaxys_dielectric_entries"], int)
        assert isinstance(reading["local_registered_distinct_T"], int)
        assert isinstance(reading["observation_table_distinct_T"], int)
        assert reading["local_registered_scope"]
        assert reading["provenance"]["restriction"] == "restricted_crosscheck_only"
        assert reading["provenance"]["declares_channel_availability"] is False
    assert "restricted_crosscheck_only" in json.dumps(summary, ensure_ascii=False)


def test_net_new_temperature_points_agree_between_readings_and_headline(
    summary: dict[str, object],
) -> None:
    per_reading = sum(int(r["net_new_temperature_points"]) for r in summary["readings"])
    headline = sum(int(n["n_points"]) for n in summary["net_new_temperature_points"])
    assert per_reading == headline == 4


def test_the_net_new_headline_has_exactly_two_substances_and_names_its_sources(
    summary: dict[str, object],
) -> None:
    headline = summary["net_new_temperature_points"]
    assert {h["short"] for h in headline} == {"PC", "tetraglyme"}
    flat = [src for h in headline for src in h["sources"]]
    assert len(flat) == 3
    assert any("Rivas" in src and "Journal of Chemical Thermodynamics, 2006" in src for src in flat)
    assert all(h["frequency_Hz"] and h["qualifier"] for h in headline)


def test_the_tetraglyme_reaxys_series_declares_one_more_hit_than_it_rendered(
    summary: dict[str, object],
) -> None:
    tetraglyme = next(r for r in summary["readings"] if r["short"] == "tetraglyme")
    assert tetraglyme["temperature_series"] is True
    assert tetraglyme["entries_rendered"] == tetraglyme["reaxys_dielectric_entries"] - 1


def test_compliance_admits_the_machine_readable_mirror(summary: dict[str, object]) -> None:
    """The first compliance string denied the mirror that the artifact itself carries.

    ``readings[].rendered_rows`` and ``net_new_detail[].value`` are row-by-row
    transcriptions of the restricted values, so claiming "no machine-readable
    mirror" was false. The string now states the mirror and forbids
    redistribution instead.
    """
    compliance = str(summary["compliance"])
    assert "机器可读镜像" in compliance
    assert "禁止再次分发" in compliance
    contract = summary["restricted_values_contract"]
    assert contract["machine_readable_mirror_present"] is True
    assert contract["mirror_fields"] == [
        "readings[].rendered_rows", "net_new_detail[].value"]
    assert contract["redistribution"] == "not_permitted"
    assert contract["may_join_into_data_or_pool"] is False
    assert contract["declares_channel_availability"] is False
    assert contract["provenance"] == "reaxys<-bibliographic_citation"
    assert summary["observation_sha256"] == OBS_SHA256


def test_declared_vs_rendered_gaps_are_disclosed(summary: dict[str, object]) -> None:
    """A reading that declares more entries than it rendered must say so."""
    open_text = " ".join(str(i) for i in summary["open_items"])
    gaps = [r for r in summary["readings"]
            if r["entries_rendered"] < r["reaxys_dielectric_entries"]]
    assert {r["short"] for r in gaps} == {"PC", "tetraglyme"}
    assert "PC 侧" in open_text
    assert "tetraglyme" in open_text


def test_family_classifier_fixes_the_known_misclassifications() -> None:
    """Adversarial review found at least three systematic tag errors."""
    assert classify("Hexamethyldisiloxane") == "siloxane"
    assert classify("1,2-ethanediol") == "alcohol_amine"
    assert classify("1,3-Propanediol") == "alcohol_amine"
    assert classify("1-Butanethiol") == "other"
    assert classify("1,2-difluorobenzene") == "fluorinated"
    for name in ("1-ethyl-3-methylimidazolium tetrafluoroborate",
                 "3-butyl-1,2,4,5-tetramethyl-1H-imidazol-3-ium tetrafluoroborate"):
        assert classify(name) == "ionic_liquid", name
    assert classify("ethylene carbonate") == "carbonate"
    assert classify("2,5,8,11,14-pentaoxapentadecane") == "glyme_ether"


def test_net_new_points_declared_without_a_detail_list_are_rejected() -> None:
    from probes.reaxys_v1x_stocking_scan import resolved_readings

    resolved = resolved_readings()
    assert all(r["net_new_temperature_points"] == len(r.get("net_new_detail") or [])
               for r in resolved)


def test_propylene_carbonate_is_downgraded_to_a_compilation_restatement(
    summary: dict[str, object],
) -> None:
    """Two Reaxys rows are two *bibliographic* sources, not two measurements.

    ``reports/jstage_corroboration.md`` already established that 64.92 traces
    back to Riddick "Organic Solvents" 4th ed. through Nanbu 2007, so calling
    this an independent corroboration contradicts the repository's own finding.
    """
    pc = next(c for c in summary["cross_checks"] if c["champion"] == "PC")
    assert pc["verdict"] == "compilation_restatement_agrees"
    assert "independently" not in pc["verdict"]
    assert len(pc["reaxys_corroboration"]) == 2
    assert all("25 C" in line for line in pc["reaxys_corroboration"])
    assert len(set(pc["reaxys_corroboration"])) == 2
    chain = pc["evidence_chain"]
    assert chain["n_reaxys_sources"] == 2
    assert chain["distinct_sources"] is True
    assert "Riddick" in chain["shared_provenance"]


def test_ethylene_carbonate_records_the_temperature_label_conflict(
    summary: dict[str, object],
) -> None:
    """89.78 is not a 25 C reading: the repository's own trace says 40 C.

    ``reports/jstage_corroboration.md`` aligns the same 89.78 with 40 C =
    313.15 K, which is exactly the frozen EC temperature. Reaxys labels it 25 C
    even though EC melts at 36.4 C, so the honest verdict is "the value matches
    but the Reaxys temperature label is wrong" -- neither "agrees" nor "no
    conflict".
    """
    ec = next(c for c in summary["cross_checks"] if c["champion"] == "EC")
    assert ec["verdict"] == "value_matches_but_reaxys_temperature_label_conflicts"
    assert ec["frozen_truth"].startswith("90.5")
    assert not any("25 C" in line and "40 C" in line for line in ec["reaxys_corroboration"])
    chain = ec["evidence_chain"]
    assert chain["reaxys_temperature_label_C"] == 25
    assert chain["open_literature_temperature_C"] == 40
    assert chain["open_literature_temperature_K"] == chain["frozen_truth_temperature_K"] == 313.15
    assert chain["relative_deviation_vs_frozen_truth"] < 0.01
    assert "313.15" in chain["reading"]


def test_evidence_chain_quotes_are_verbatim_in_the_cross_referenced_file(
    summary: dict[str, object],
) -> None:
    """A cited conclusion must actually appear in the file it cites."""
    for check in summary["cross_checks"]:
        chain = check["evidence_chain"]
        cited = (REPOSITORY_ROOT / chain["cross_reference"]).read_text(encoding="utf-8")
        assert chain["cross_reference_quote"] in cited
        assert (REPOSITORY_ROOT / chain["cross_reference"]).exists()


def test_readings_that_are_weaker_than_local_are_labelled_as_such(
    summary: dict[str, object],
) -> None:
    for short in ("triglyme", "adiponitrile", "diglyme"):
        reading = next(r for r in summary["readings"] if r["short"] == short)
        assert reading["local_registered_distinct_T"] >= 5
        assert reading["observation_table_distinct_T"] >= 5
        assert reading["net_new_temperature_points"] == 0


def test_open_items_are_declared(summary: dict[str, object]) -> None:
    items = summary["open_items"]
    assert len(items) >= 3
    joined = " ".join(items)
    assert "39.99" in joined
    assert "5.4" in joined
    assert "TTE" in joined or "tetrafluoroethyl" in joined


def test_report_is_lf_only_and_carries_the_claims(summary: dict[str, object]) -> None:
    raw = REPORT_PATH.read_bytes()
    assert b"\r\n" not in raw
    text = raw.decode("utf-8")
    assert POOL_SHA256[:16] in text
    assert "restricted_crosscheck_only" in text
    assert "净新增带温度的介电条目 4 条" in text
    assert "不改结论" in text
    assert "池内**有**温度序列的是" in text
    assert "**全表**" in text
    assert "机器可读镜像" in text
    assert "不产生任何通道可用性声明" in text
    assert "不是可用性判断" in text
    assert "两个互相独立的一手来源复现" not in text
    assert OBS_SHA256[:16] in text


def test_verifier_script_passes_end_to_end() -> None:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(VERIFIER)],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(REPOSITORY_ROOT), check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout