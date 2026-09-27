"""Guards for the Week 18 AUC sidecar and the splitter x ranking table.

Two things happened this round and both are easy to get wrong later:

1. Every scoreboard repeats CSV was silently dropping the two AUC columns that
   evaluate_repeat has always computed, because METRIC_NAMES carries only seven
   metrics.  The fix is a sidecar rebuilt from the shipped prediction rows, and
   the whole point is that it must add columns WITHOUT touching a frozen byte.
2. The R2/AUC gap is the story of the funnel, and it needed one table with the
   row-level leak reference, the honest compound split and the scaffold split
   side by side.

These tests pin both: the frozen schema is not allowed to move, the shipped
repeats files must still hash to what the sidecar recorded, the random_row arm
must stay labelled non-citable, and nothing may be promoted.

Everything here is offline: no network, no fitting.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIDECAR_SUMMARY = ROOT / "probes/dielectric_auc_sidecar_summary.json"
SIDECAR_CSV = ROOT / "probes/artifacts/dielectric_auc_sidecar.csv"
SIDECAR_REPORT = ROOT / "reports/dielectric_auc_sidecar.md"
SPLITTER_SUMMARY = ROOT / "probes/dielectric_splitters_auc_summary.json"
SPLITTER_TABLE = ROOT / "probes/artifacts/dielectric_splitters_auc.csv"
SPLITTER_REPORT = ROOT / "reports/dielectric_splitters_auc.md"
SPLITTER_PLOT = ROOT / "probes/plot_splitters_auc.py"

EXPECTED_METRIC_NAMES = (
    "r2",
    "mae",
    "rmse",
    "spearman",
    "mae_lt20",
    "mae_20_60",
    "mae_gt60",
)
ADDED_COLUMNS = ("auc_gt15", "auc_gt30")
SIDECAR_COLUMNS = (
    "source",
    "key",
    "representation",
    "repeat",
    "rows",
    "r2",
    "r2_shipped",
    "abs_gap",
    "spearman",
    *ADDED_COLUMNS,
)
TABLE_COLUMNS = (
    "protocol",
    "representation",
    "repeat",
    "rows",
    "r2",
    "r2_shipped",
    "abs_gap",
    "spearman",
    *ADDED_COLUMNS,
)
SOURCES = (
    "dielectric_coordination_block_v3",
    "dielectric_observations_benchmark",
    "dielectric_room_window_paired",
    "dielectric_coverage_paired_benchmark",
    "dielectric_band_ablation",
)
REPRESENTATIONS = ("Morgan", "Physical", "Morgan+Physical")
PROTOCOLS = ("random_row", "grouped", "scaffold", "grouped_single_row")
REUSED_PROTOCOLS = ("random_row", "grouped", "grouped_single_row")
PRIMARY_PROTOCOL = "grouped"
PRIMARY_REPRESENTATION = "Morgan+Physical"
R2_TOLERANCE = 1e-09
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_BASELINE = 0.4091179943351143
FROZEN_SCOREBOARD_HEADLINE_R2 = 0.4766400383507876


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_frozen_metric_schema_is_still_the_seven_it_was() -> None:
    """The sidecar exists because METRIC_NAMES is frozen. It must stay frozen."""

    from probes.dielectric_observations_grouped_benchmark import METRIC_NAMES

    assert tuple(METRIC_NAMES) == EXPECTED_METRIC_NAMES
    assert "auc_gt15" not in METRIC_NAMES
    assert "auc_gt30" not in METRIC_NAMES


def test_the_shipped_repeats_files_still_hash_to_what_the_sidecar_recorded() -> None:
    """The sidecar adds columns without rewriting a shipped file. Prove it."""

    from electrolyte_ml.exporting import canonical_text_sha256

    summary = _json(SIDECAR_SUMMARY)
    sources = summary["sources"]
    assert set(sources) == set(SOURCES)
    for stem, block in sources.items():
        path = ROOT / str(block["repeats"])
        assert path.is_file(), path
        assert canonical_text_sha256(path) == str(block["repeats_sha256"]), stem
    assert summary["metric_names_shipped"] == list(EXPECTED_METRIC_NAMES)
    assert summary["metric_names_extended"] == [*EXPECTED_METRIC_NAMES, *ADDED_COLUMNS]


def test_every_rescored_repeat_reproduces_the_shipped_r2_exactly() -> None:
    summary = _json(SIDECAR_SUMMARY)
    assert float(summary["worst_r2_abs_gap"]) <= R2_TOLERANCE
    assert float(summary["r2_tolerance"]) == R2_TOLERANCE
    with SIDECAR_CSV.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert reader.fieldnames == list(SIDECAR_COLUMNS)
    assert rows
    for row in rows:
        assert float(row["abs_gap"]) <= R2_TOLERANCE, row
        assert 0.0 <= float(row["auc_gt15"]) <= 1.0, row
        assert 0.0 <= float(row["auc_gt30"]) <= 1.0, row
    assert bytes([13, 10]) not in SIDECAR_CSV.read_bytes()
    assert {row["source"] for row in rows} == set(SOURCES)


def test_the_sidecar_gives_the_frozen_headline_arm_an_auc_and_never_promotes() -> None:
    summary = _json(SIDECAR_SUMMARY)
    promotion = summary["promotion"]
    assert promotion["promoted"] is False
    assert float(promotion["frozen_headline"]) == FROZEN_HEADLINE
    assert float(promotion["frozen_baseline"]) == FROZEN_BASELINE
    with SIDECAR_CSV.open(encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["source"] == "dielectric_coordination_block_v3"
        ]
    headline = [
        row
        for row in rows
        if row["key"] == "plus_both" and row["representation"] == "Morgan+Physical"
    ]
    assert len(headline) == 10
    mean_r2 = sum(float(row["r2"]) for row in headline) / len(headline)
    assert abs(mean_r2 - FROZEN_SCOREBOARD_HEADLINE_R2) <= 1e-06
    mean_auc = sum(float(row["auc_gt30"]) for row in headline) / len(headline)
    assert mean_auc > 0.90
    placebo = [
        row
        for row in rows
        if row["key"] == "placebo_shuffled_target"
        and row["representation"] == "Morgan+Physical"
    ]
    assert placebo
    placebo_auc = sum(float(row["auc_gt30"]) for row in placebo) / len(placebo)
    assert abs(placebo_auc - 0.5) < 0.10


def test_the_sidecar_report_says_what_it_is_and_what_it_is_not() -> None:
    text = SIDECAR_REPORT.read_text(encoding="utf-8")
    for needle in (
        "把主链路丢掉的 AUC 补回来",
        "METRIC_NAMES",
        "不修改",
        "离线重算",
        "0.4766400383507876",
        "0.4091179943351143",
        "不动任何冻结数",
    ):
        assert needle in text, needle


def test_the_splitter_table_carries_all_four_cuts_and_ten_repeats_each() -> None:
    summary = _json(SPLITTER_SUMMARY)
    assert list(summary["protocol_order"]) == list(PROTOCOLS)
    assert summary["frozen_side"]["representations"] == list(REPRESENTATIONS)
    with SPLITTER_TABLE.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert reader.fieldnames == list(TABLE_COLUMNS)
    assert len(rows) == len(PROTOCOLS) * len(REPRESENTATIONS) * 10
    assert bytes([13, 10]) not in SPLITTER_TABLE.read_bytes()
    counts = Counter((row["protocol"], row["representation"]) for row in rows)
    for protocol in PROTOCOLS:
        for representation in REPRESENTATIONS:
            assert counts[(protocol, representation)] == 10, (protocol, representation)
    for row in rows:
        if row["protocol"] in REUSED_PROTOCOLS:
            assert float(row["abs_gap"]) <= R2_TOLERANCE, row
        assert 0.0 <= float(row["auc_gt15"]) <= 1.0, row
        assert 0.0 <= float(row["auc_gt30"]) <= 1.0, row


def test_the_leak_reference_is_optimistic_and_the_honest_split_is_not() -> None:
    """The whole reading rests on this ordering; if it flips the report is wrong."""

    summary = _json(SPLITTER_SUMMARY)
    by_protocol = summary["by_protocol"]
    leak = float(by_protocol["random_row"][PRIMARY_REPRESENTATION]["r2"])
    honest = float(by_protocol[PRIMARY_PROTOCOL][PRIMARY_REPRESENTATION]["r2"])
    hostile = float(by_protocol["scaffold"][PRIMARY_REPRESENTATION]["r2"])
    assert leak > honest
    assert leak > 0.80
    assert hostile < leak
    for protocol in PROTOCOLS:
        auc = float(by_protocol[protocol][PRIMARY_REPRESENTATION]["auc_gt30"])
        assert auc > 0.5, protocol


def test_the_splitters_probe_never_promotes_and_keeps_the_frozen_numbers() -> None:
    summary = _json(SPLITTER_SUMMARY)
    promotion = summary["promotion"]
    assert promotion["promoted"] is False
    assert float(promotion["frozen_headline"]) == FROZEN_HEADLINE
    assert float(promotion["frozen_baseline"]) == FROZEN_BASELINE
    assert float(summary["reused_max_r2_abs_gap"]) <= R2_TOLERANCE
    assert summary["new_run"]["leak"]["folds_with_a_straddling_compound"] == 0
    assert summary["new_run"]["leak"]["max_straddling_compounds_in_a_fold"] == 0


def test_the_splitter_report_says_which_number_may_be_quoted() -> None:
    text = SPLITTER_REPORT.read_text(encoding="utf-8")
    for needle in (
        "排序学会了、量级没学会",
        "泄漏参考",
        "不得当达标题",
        "化合物留出",
        "骨架留出",
        "本叙事被证否",
        "0.4766400383507876",
        "0.4091179943351143",
        "零重拟合",
    ):
        assert needle in text, needle


def test_the_plot_pins_match_the_splitter_table() -> None:
    summary = _json(SPLITTER_SUMMARY)
    source = SPLITTER_PLOT.read_text(encoding="utf-8")
    assert "0.9337" in source
    assert "0.1602" in source
    by_protocol = summary["by_protocol"]
    assert abs(float(by_protocol["random_row"][PRIMARY_REPRESENTATION]["r2"]) - 0.9337) <= 1e-03
    assert abs(float(by_protocol[PRIMARY_PROTOCOL][PRIMARY_REPRESENTATION]["r2"]) - 0.1602) <= 1e-03
