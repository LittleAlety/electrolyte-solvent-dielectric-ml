"""Delivery-package regression tests for the Week 19 export.

The expectations are literals on purpose, for the reason Week 16 recorded: the
machine lanes stay pinned while the prose layer rots.  The README bytes are pinned
by a digest and every narrative number is asserted as a literal of its own, and each
of those numbers is also traced back to a shipped lane artifact so a hand-typed
number cannot survive in the prose.

The verifier block deliberately does NOT run this file: the `exported` fixture
executes the export, which runs the verifiers, so listing this test inside VERIFIERS
would recurse.  Only the Week 19 lane tests and the repository hygiene test run
inside the export.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import sys
from pathlib import Path

import pytest

from electrolyte_ml.exporting import verify_export_manifest
from probes.export_week19_results import (
    ARTIFACTS,
    CARRY_FORWARD,
    DOCUMENTED_VERDICTS,
    FIGURES,
    FROZEN_RED_LINES,
    FROZEN_SINGLE_REPRESENTATION_CROSS_SEED,
    FROZEN_SINGLE_REPRESENTATION_R2,
    LANE_KEYS,
    LANE_KIND,
    LANE_SOURCES,
    MAIN_SCOREBOARD,
    MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS,
    MAIN_SCOREBOARD_HEADLINE_DELTA_R2,
    MAIN_SCOREBOARD_HEADLINE_R2,
    MEASURED_VERDICT_FALLBACK,
    PENDING_LANES,
    RANDOM_ROW_LEAK_REFERENCE_R2,
    README_TEXT,
    RECORDED_VERDICTS,
    VERIFIERS,
    W19_MAIN_SCOREBOARD_ATTEMPTS,
    W19_SEEDS,
    WEEK,
    _missing_lane_keys,
    _parse_args,
    export_results,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

RED_LINE_EXPECTATIONS = (
    ("data/dielectric_v03.csv", "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"),
    ("probes/l3_stage1_pilot_pool.csv", "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"),
    (
        "probes/l3_backvalidation_prereg.json",
        "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98",
    ),
    (
        "data/processed/dielectric_observations_v11plus.csv",
        "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    ),
    (
        "probes/dielectric_r2_levers_prereg.json",
        "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa",
    ),
    ("data/viscosity_v01.csv", "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26"),
)
FROZEN_BASELINE_R2 = 0.4091179943351143
FROZEN_PROMOTED_HEADLINE_R2 = 0.4766400383507876
FROZEN_PROMOTED_HEADLINE_DELTA_R2 = 0.0675220440156733
FROZEN_LEAK_REFERENCE_R2 = 0.7385332681453336
FROZEN_SINGLE_REPRESENTATION = 0.6080587938801277
FROZEN_SINGLE_REPRESENTATION_ENDPOINT = 0.5861142332208197
VISCOSITY_MAE_GATE = 0.15

# A mutant that rewrites one narrative number must move this line as well.
README_SHA256 = "67cc4629a8f004f3d5d374035e293a043c0fa08a1f0772de9155f1abedaa8b5d"
README_NARRATIVE_NUMBERS = (
    "0.4091179943351143",
    "0.4766400383507876",
    "0.5861142332208197",
    "457",
    "97",
    "276",
    "2029",
    "11",
    "0.60",
    "183,771,012",
    "0.17662467232470583",
    "0.24935401611452185",
    "0.304",
    "0.350",
    "0.7349044734023142",
    "18,316",
    "214",
    "86",
    "246",
    "77",
    "78",
    "111",
    "234",
    "72.0614455552206",
    "0.95",
    "0.80",
    "0.90",
    "0.15686276760094522",
    "0.08506361044387624",
    "0.17477197208762",
    "0.08908094784092072",
    "0.15",
    "0.19050925839013938",
    "0.13855083976437643",
    "0.20",
    "60.0",
    "75.95675695251926",
    "0.349",
    "0.3",
    "1043",
    "0.8223",
    "0.3475",
    "0.4663",
    "0.1921",
    "0.1984",
    "0.7445",
    "0.055",
    "0.0025",
    "0.35",
    "49",
    "0.5998203128630835",
    "0.00018",
)


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("week19")
    return root, export_results(output_root=root, overwrite=False)


def _summary(root: Path) -> dict:
    return json.loads((root / WEEK / "week19_summary.json").read_text(encoding="utf-8"))


def _report_text(key: str) -> str:
    return (REPOSITORY_ROOT / str(LANE_SOURCES[key]["report"])).read_text(encoding="utf-8")


def _shipped_corpus() -> str:
    """Every shipped text artifact, so a README number can be traced to one of them."""

    chunks: list[str] = []
    for key in LANE_KEYS:
        sources = LANE_SOURCES[key]
        for field in ("probe", "prereg", "summary", "report"):
            relative = sources[field]
            if relative is None:
                continue
            path = REPOSITORY_ROOT / str(relative)
            if path.is_file():
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    for source, _destination in CARRY_FORWARD:
        path = REPOSITORY_ROOT / source
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def test_the_module_constants_are_the_frozen_literals() -> None:
    assert MAIN_SCOREBOARD == FROZEN_BASELINE_R2 == 0.4091179943351143
    assert MAIN_SCOREBOARD_HEADLINE_R2 == FROZEN_PROMOTED_HEADLINE_R2 == 0.4766400383507876
    assert (
        MAIN_SCOREBOARD_HEADLINE_DELTA_R2
        == FROZEN_PROMOTED_HEADLINE_DELTA_R2
        == 0.0675220440156733
    )
    assert RANDOM_ROW_LEAK_REFERENCE_R2 == FROZEN_LEAK_REFERENCE_R2 == 0.7385332681453336
    assert FROZEN_SINGLE_REPRESENTATION_R2 == FROZEN_SINGLE_REPRESENTATION == 0.6080587938801277
    assert FROZEN_SINGLE_REPRESENTATION_CROSS_SEED == FROZEN_SINGLE_REPRESENTATION_ENDPOINT
    assert MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS == 11
    assert W19_MAIN_SCOREBOARD_ATTEMPTS == 0
    assert VISCOSITY_MAE_GATE == 0.15


def test_the_lane_registry_is_the_declared_order_and_kind() -> None:
    assert tuple(LANE_SOURCES) == LANE_KEYS
    assert tuple(LANE_KIND) == LANE_KEYS
    assert len(LANE_KEYS) == 11
    assert tuple(W19_SEEDS) == (42, 1234, 2026, 31337, 7)
    assert set(LANE_KIND.values()) == {"measured", "documented", "registered"}
    assert set(PENDING_LANES) <= set(LANE_KEYS)
    for key in LANE_KEYS:
        if LANE_KIND[key] == "measured":
            assert LANE_SOURCES[key]["summary"] is not None, key
        else:
            assert LANE_SOURCES[key]["summary"] is None, key


def test_every_declared_artifact_exists_and_has_a_unique_destination() -> None:
    missing = [source for source, _ in ARTIFACTS if not (REPOSITORY_ROOT / source).is_file()]
    assert missing == []
    destinations = [destination for _, destination in ARTIFACTS]
    assert len(destinations) == len(set(destinations))


def test_every_non_pending_lane_file_exists_on_disk() -> None:
    problems: list[str] = []
    for key in LANE_KEYS:
        if key in PENDING_LANES:
            continue
        sources = LANE_SOURCES[key]
        for field in ("probe", "prereg", "summary", "report"):
            relative = sources[field]
            if relative is None:
                continue
            if not (REPOSITORY_ROOT / str(relative)).is_file():
                problems.append(str(relative))
        for relative in sources["tests"]:
            if not (REPOSITORY_ROOT / str(relative)).is_file():
                problems.append(str(relative))
    assert problems == []


def test_export_ships_every_artifact_readme_manifest_and_verification(
    exported: tuple[Path, dict],
) -> None:
    root, result = exported
    week_root = root / WEEK

    assert result["verification_passed"] is True
    for _, destination in ARTIFACTS:
        assert (week_root / destination).is_file(), destination
    for name in ("README.md", "week19_summary.json", "verification.json", "SHA256SUMS"):
        assert (week_root / name).is_file(), name
    assert verify_export_manifest(week_root) == []


def test_the_summary_records_the_artifact_list_it_shipped(exported: tuple[Path, dict]) -> None:
    _, result = exported
    assert result["artifacts"] == [destination for _, destination in ARTIFACTS]


def test_the_shipped_readme_is_the_module_constant(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    assert (root / WEEK / "README.md").read_text(encoding="utf-8") == README_TEXT
    assert _summary(root)["week"] == WEEK == "week19"


def test_the_provenance_note_is_recorded(exported: tuple[Path, dict]) -> None:
    _, result = exported
    assert str(result["artifacts_commit"]) != "" or result["worktree_dirty"] is True
    assert "provenance_note" in result


def test_export_refuses_to_overwrite_without_the_flag(tmp_path: Path) -> None:
    (tmp_path / WEEK).mkdir()
    with pytest.raises(FileExistsError):
        export_results(output_root=tmp_path, overwrite=False)


def test_the_overwrite_flag_is_wired_through_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["export_week19_results.py", "--overwrite"])
    assert _parse_args().overwrite is True
    monkeypatch.setattr(sys, "argv", ["export_week19_results.py"])
    assert _parse_args().overwrite is False


def test_declared_verifiers_are_real_scripts() -> None:
    for command in VERIFIERS:
        parts = shlex.split(command)
        if parts[0] == "-m":
            assert len(parts) >= 3 and parts[1] == "pytest", command
            for target in parts[2:]:
                if target.endswith(".py"):
                    assert (REPOSITORY_ROOT / target).is_file(), command
            continue
        assert (REPOSITORY_ROOT / parts[0]).is_file(), command


def test_the_verifier_block_actually_ran_and_passed(exported: tuple[Path, dict]) -> None:
    _, result = exported
    checks = result["verification"]["checks"]

    assert [check["command"] for check in checks] == list(VERIFIERS)
    assert all(check["passed"] and check["exit_code"] == 0 for check in checks)
    assert result["verification"]["passed"] is True


def test_summary_pins_every_frozen_red_line(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    red_lines = _summary(root)["frozen_red_lines"]

    assert dict(RED_LINE_EXPECTATIONS) == FROZEN_RED_LINES
    assert set(red_lines) == {name for name, _ in RED_LINE_EXPECTATIONS}
    for relative, expected in RED_LINE_EXPECTATIONS:
        entry = red_lines[relative]
        assert entry["expected_sha256"] == expected
        assert entry["measured_sha256"] == expected
        assert entry["intact"] is True
    assert _summary(root)["frozen_red_lines_all_intact"] is True


def test_the_frozen_board_is_reported_untouched(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    board = _summary(root)["main_scoreboard"]

    assert board["baseline"]["value"] == FROZEN_BASELINE_R2
    assert board["baseline"]["status"] == "retained_unchanged"
    assert board["headline"]["value"] == FROZEN_PROMOTED_HEADLINE_R2
    assert board["headline"]["delta_vs_baseline"] == FROZEN_PROMOTED_HEADLINE_DELTA_R2
    assert board["touched_this_week"] is False
    assert _summary(root)["shots"]["main_scoreboard_attempts"] == W19_MAIN_SCOREBOARD_ATTEMPTS == 0
    assert (
        _summary(root)["shots"]["cumulative_main_scoreboard_attempts"]
        == MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS
        == 11
    )


def test_the_accounting_self_attestation_is_recorded(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    summary = _summary(root)

    assert summary["main_scoreboard_attempts_this_week"] == 0
    assert summary["cumulative_main_scoreboard_attempts"] == 11
    assert summary["cumulative_main_scoreboard_attempts"] == MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS
    assert summary["promoted_lanes"] == []
    assert summary["no_lane_promotes"] is True


def test_no_lane_promotes_a_reading(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    summary = _summary(root)

    assert summary["promoted_lanes"] == []
    assert summary["no_lane_promotes"] is True
    for key, block in summary["lane_verdicts"].items():
        assert block["promoted"] is False, key
        assert "refused" not in str(block["verdict"]), key
    readings = summary["frozen_reference_readings"]
    assert readings["baseline_r2"] == FROZEN_BASELINE_R2
    assert readings["headline_r2"] == FROZEN_PROMOTED_HEADLINE_R2
    assert readings["single_representation_r2"] == FROZEN_SINGLE_REPRESENTATION
    assert readings["single_representation_cross_seed_mean"] == FROZEN_SINGLE_REPRESENTATION_CROSS_SEED
    assert readings["random_row_leak_reference_r2"] == FROZEN_LEAK_REFERENCE_R2


def test_every_lane_carries_its_report_and_recorded_verdict(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    lanes = _summary(root)["lanes"]
    missing = set(_missing_lane_keys())

    assert tuple(lanes) == LANE_KEYS
    for key in LANE_KEYS:
        block = lanes[key]
        assert block["kind"] == LANE_KIND[key], key
        assert block["fields"]["promoted"] is False, key
        if key not in missing:
            assert block["report_present"] is True, key
            assert len(str(block["report_sha256"])) == 64, key
            assert block["tests_present"], key
        if block["summary_path"] is not None and key not in missing:
            assert len(str(block["summary_sha256"])) == 64, key
        prereg = block["prereg"]
        if prereg is not None:
            assert prereg["locked_before_run"] is True, key
            assert (REPOSITORY_ROOT / str(prereg["path"])).is_file(), key
        if key in RECORDED_VERDICTS and key not in missing:
            assert block["fields"]["verdict"] == RECORDED_VERDICTS[key], key


def test_documented_lane_verdicts_appear_verbatim_in_their_reports() -> None:
    missing = set(_missing_lane_keys())

    assert set(DOCUMENTED_VERDICTS) <= set(LANE_KEYS)
    for key, token in DOCUMENTED_VERDICTS.items():
        assert LANE_KIND[key] == "documented", key
        assert key not in missing, key
        assert token in _report_text(key), (key, token)


def test_measured_lane_fallback_verdicts_appear_verbatim_in_their_reports() -> None:
    missing = set(_missing_lane_keys())

    assert set(MEASURED_VERDICT_FALLBACK) <= set(LANE_KEYS)
    assert set(RECORDED_VERDICTS) == set(DOCUMENTED_VERDICTS) | set(MEASURED_VERDICT_FALLBACK)
    for key, token in MEASURED_VERDICT_FALLBACK.items():
        assert LANE_KIND[key] == "measured", key
        assert key not in missing, key
        assert token in _report_text(key), (key, token)


def test_missing_lanes_are_confined_to_the_pending_set(exported: tuple[Path, dict]) -> None:
    _, result = exported

    assert set(result["lanes_missing"]) <= set(PENDING_LANES)
    assert result["lanes_missing"] == list(_missing_lane_keys())
    assert set(_missing_lane_keys()) <= set(PENDING_LANES)


def test_every_exported_csv_is_lf_only(exported: tuple[Path, dict]) -> None:
    root, _ = exported
    for path in sorted((root / WEEK).rglob("*.csv")):
        assert b"\r\n" not in path.read_bytes(), path.name


def test_the_readme_text_is_pinned_by_a_literal_digest() -> None:
    assert hashlib.sha256(README_TEXT.encode("utf-8")).hexdigest() == README_SHA256


def test_the_readme_carries_the_numbers_the_lanes_measured() -> None:
    for number in README_NARRATIVE_NUMBERS:
        assert number in README_TEXT, number


def test_every_readme_number_is_traceable_to_a_shipped_artifact() -> None:
    corpus = _shipped_corpus()
    for number in README_NARRATIVE_NUMBERS:
        assert number in corpus, number


def test_the_figure_slots_are_declared() -> None:
    for name in FIGURES:
        assert name.startswith("probes/artifacts/w19_"), name
        assert (REPOSITORY_ROOT / name).is_file(), name
