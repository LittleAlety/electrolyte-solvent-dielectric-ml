"""Export the Week 19 deliverables (the literature-driven three-line plan).

Week 18 closed the post-cap path ranking: the frozen baseline
0.4091179943351143 and the frozen headline 0.4766400383507876 did not move, no
lane promoted a reading, and the best epsilon arm stayed just below the 0.60 gate.
Week 19 therefore stops buying epsilon points and starts building the adjacent
channels the plan calls for:

* W19-D1 -- the state-audit and revision ledger (documented);
* W19-D2 -- the Batt-P30K direct-hit check on the frozen roster (measured);
* W19-D3 -- the Onsager residual layer under an out-of-family split (measured);
* W19-D4 -- the literature-extraction probe Phase-0 spec (documented);
* W19-D5 -- the eta channel under a second model family, Chemprop D-MPNN (measured);
* W19-D6 -- the multi-objective ranking-key spec v0 (documented);
* W19-D7 -- the safety-channel registration, register-only (measured);
* W19-N2 -- the direct Batt-P30K orbital cross-check (measured);
* W19-7  -- the alpha-to-orbital channel-transfer plan (documented);
* W19-D8 -- the orbital-migration gate (registered; produced by a parallel lane);
* W19-D9 -- the shots ledger (registered; produced by a parallel lane).

Nothing on the frozen side moves.  Every lane reports under its own
pre-registration and its own pool, `promoted` is false in all of them, and Week 19
adds no shot to the main scoreboard: the cumulative ledger stays at 11.  Lanes that
a parallel writer has not landed yet are reported in `lanes_missing` rather than
crashing the export.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    read_json,
    run_verifiers,
    write_json,
    write_sha256s,
)

WEEK = "week19"

FROZEN_RED_LINES = {
    "data/dielectric_v03.csv": "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4",
    "probes/l3_stage1_pilot_pool.csv": "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18",
    "probes/l3_backvalidation_prereg.json": "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98",
    "data/processed/dielectric_observations_v11plus.csv": "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    "probes/dielectric_r2_levers_prereg.json": "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa",
    "data/viscosity_v01.csv": "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26",
}

MAIN_SCOREBOARD = 0.4091179943351143
MAIN_SCOREBOARD_VERSION = "v2"
MAIN_SCOREBOARD_HEADLINE_R2 = 0.4766400383507876
MAIN_SCOREBOARD_HEADLINE_DELTA_R2 = 0.0675220440156733
MAIN_SCOREBOARD_PROMOTED_AT_UTC = "2026-09-27T01:34:06Z"
MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS = 11
RANDOM_ROW_LEAK_REFERENCE_R2 = 0.7385332681453336
FROZEN_SINGLE_REPRESENTATION_R2 = 0.6080587938801277
FROZEN_SINGLE_REPRESENTATION_CROSS_SEED = 0.5861142332208197

# Week 19 made no attempt at the main scoreboard, so the cumulative ledger is
# carried over unchanged from the Week 18 close-out.
W19_MAIN_SCOREBOARD_ATTEMPTS = 0

W19_SEEDS = (42, 1234, 2026, 31337, 7)

# Every Week 19 lane is a separate pre-registration with its own pool and its own
# decision rule.  `promoted` is false in all of them, so this list is also the
# reason the week adds no shot to the frozen board.
LANE_KEYS = (
    "w19_d1_state_audit",
    "w19_d2_batt_direct_hit",
    "w19_d3_onsager_grouped",
    "w19_d4_extraction_phase0",
    "w19_d5_chemprop_viscosity",
    "w19_d6_ranking_key",
    "w19_d7_safety_channel",
    "w19_n2_batt_gap_crosscheck",
    "w19_7_channel_transfer",
    "w19_d8_orbital_migration_gate",
    "w19_d9_shots_ledger",
)

# Lanes written by a parallel worker.  They are registered here so the package
# picks them up the moment they land; until then they are reported as entries of
# `lanes_missing`, which is a reportable state and never a crash.
PENDING_LANES = (
    "w19_d8_orbital_migration_gate",
    "w19_d9_shots_ledger",
)

# `measured` lanes carry a machine-readable summary; `documented` lanes carry only
# a report; `registered` lanes are named but their verdict is not pinned here.
LANE_KIND = {
    "w19_d1_state_audit": "documented",
    "w19_d2_batt_direct_hit": "measured",
    "w19_d3_onsager_grouped": "measured",
    "w19_d4_extraction_phase0": "documented",
    "w19_d5_chemprop_viscosity": "measured",
    "w19_d6_ranking_key": "documented",
    "w19_d7_safety_channel": "measured",
    "w19_n2_batt_gap_crosscheck": "measured",
    "w19_7_channel_transfer": "documented",
    "w19_d8_orbital_migration_gate": "registered",
    "w19_d9_shots_ledger": "measured",
}

# A documented lane has no machine-readable summary, so its verdict is pinned here
# as a literal and the tests assert that literal appears verbatim in the report, so
# a rewritten report cannot silently decouple from this constant.
DOCUMENTED_VERDICTS = {
    "w19_d1_state_audit": "三处必须改判或登记",
    "w19_d4_extraction_phase0": "不占 shot 编号",
    "w19_d6_ranking_key": "这是排序键，不是候选生成器",
    "w19_7_channel_transfer": "触发成立",
}

# Measured lanes whose summary does not carry a top-level verdict token.
MEASURED_VERDICT_FALLBACK = {
    "w19_d2_batt_direct_hit": "分母口径分歧",
    "w19_d3_onsager_grouped": "delta_layer_survives_out_of_family",
    "w19_d7_safety_channel": "registered_not_executed",
}

RECORDED_VERDICTS = {**DOCUMENTED_VERDICTS, **MEASURED_VERDICT_FALLBACK}

LANE_SOURCES = {
    "w19_d1_state_audit": {
        "probe": None,
        "prereg": None,
        "summary": None,
        "report": "reports/w19_state_audit.md",
        "tests": ("tests/test_w19_state_audit.py",),
        "artifacts": (),
    },
    "w19_d2_batt_direct_hit": {
        "probe": "probes/w19_batt_direct_hit.py",
        "prereg": None,
        "summary": "probes/w19_batt_direct_hit_summary.json",
        "report": "reports/w19_batt_direct_hit.md",
        "tests": ("tests/test_w19_batt_direct_hit.py",),
        "artifacts": (),
    },
    "w19_d3_onsager_grouped": {
        "probe": "probes/w19_onsager_grouped.py",
        "prereg": "probes/w19_onsager_grouped_prereg.json",
        "summary": "probes/w19_onsager_grouped_summary.json",
        "report": "reports/w19_onsager_grouped.md",
        "tests": ("tests/test_w19_onsager_grouped.py",),
        "artifacts": (),
    },
    "w19_d4_extraction_phase0": {
        "probe": None,
        "prereg": "probes/w19_extraction_phase0_prereg.json",
        "summary": None,
        "report": "reports/w19_extraction_phase0.md",
        "tests": ("tests/test_w19_extraction_phase0.py",),
        "artifacts": (),
    },
    "w19_d5_chemprop_viscosity": {
        "probe": "probes/w19_chemprop_viscosity.py",
        "prereg": "probes/w19_chemprop_viscosity_prereg.json",
        "summary": "probes/w19_chemprop_viscosity_summary.json",
        "report": "reports/w19_chemprop_viscosity.md",
        "tests": ("tests/test_w19_chemprop_viscosity.py",),
        "artifacts": ("probes/artifacts/w19_chemprop_viscosity_repeats.csv",),
    },
    "w19_d6_ranking_key": {
        "probe": "probes/w19_ranking_key.py",
        "prereg": None,
        "summary": None,
        "report": "reports/w19_ranking_key_spec.md",
        "tests": ("tests/test_w19_ranking_key.py",),
        "artifacts": (),
    },
    "w19_d7_safety_channel": {
        "probe": None,
        "prereg": None,
        "summary": "probes/w19_safety_channel_registry.json",
        "report": "reports/w19_safety_channel.md",
        "tests": ("tests/test_w19_safety_channel.py",),
        "artifacts": (),
    },
    "w19_n2_batt_gap_crosscheck": {
        "probe": "probes/w19_batt_gap_crosscheck.py",
        "prereg": "probes/w19_batt_gap_crosscheck_prereg.json",
        "summary": "probes/w19_batt_gap_crosscheck_summary.json",
        "report": "reports/w19_batt_gap_crosscheck.md",
        "tests": ("tests/test_w19_batt_gap_crosscheck.py",),
        "artifacts": (),
    },
    "w19_7_channel_transfer": {
        "probe": None,
        "prereg": None,
        "summary": None,
        "report": "reports/w19_channel_transfer.md",
        "tests": ("tests/test_w19_channel_transfer.py",),
        "artifacts": (),
    },
    "w19_d8_orbital_migration_gate": {
        "probe": None,
        "prereg": None,
        "summary": None,
        "report": "reports/w19_orbital_migration_gate.md",
        "tests": ("tests/test_w19_orbital_migration_gate.py",),
        "artifacts": (),
    },
    "w19_d9_shots_ledger": {
        "probe": None,
        "prereg": None,
        "summary": "probes/w19_shots_ledger.json",
        "report": "reports/w19_shots_ledger.md",
        "tests": ("tests/test_w19_shots_ledger.py",),
        "artifacts": (),
    },
}


# The package carries the eleven lane bundles plus the frozen evidence they rest on.
CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("data/dielectric_v03.csv", "dielectric_v03.csv"),
    ("data/dielectric_v04.csv", "dielectric_v04.csv"),
    ("data/viscosity_v02.csv", "viscosity_v02.csv"),
    ("probes/four_channel_coverage_summary.json", "four_channel_coverage_summary.json"),
    ("probes/homo_lumo_baselines_summary.json", "homo_lumo_baselines_summary.json"),
    ("probes/walden_dn_channel_summary.json", "walden_dn_channel_summary.json"),
    ("probes/dielectric_applicability_domain_summary.json", "dielectric_applicability_domain_summary.json"),
    ("reports/dielectric_applicability_domain.md", "dielectric_applicability_domain.md"),
    ("probes/dielectric_coordination_block_v3_summary.json", "dielectric_coordination_block_v3_summary.json"),
    ("probes/dielectric_splitters_auc_summary.json", "dielectric_splitters_auc_summary.json"),
    ("reports/dielectric_splitters_auc.md", "dielectric_splitters_auc.md"),
    ("data/external/SolvFunc-87.csv", "SolvFunc-87.csv"),
    ("data/external/Batt-SLM-RX-392.csv", "Batt-SLM-RX-392.csv"),
)


def _exists(relative: object) -> bool:
    if relative is None:
        return False
    return (REPOSITORY_ROOT / str(relative)).is_file()


def _declared_files(key: str) -> tuple[str, ...]:
    """Every repository path a lane bundle claims, present or not."""

    sources = LANE_SOURCES[key]
    files: list[str] = []
    for field in ("probe", "prereg", "summary", "report"):
        value = sources[field]
        if value is not None:
            files.append(str(value))
    files.extend(str(item) for item in sources["tests"])
    files.extend(str(item) for item in sources["artifacts"])
    return tuple(files)


def _missing_lane_keys() -> tuple[str, ...]:
    """A lane is missing when its report is not on disk yet."""

    return tuple(key for key in LANE_KEYS if not _exists(LANE_SOURCES[key]["report"]))


def _lane_tests(key: str) -> tuple[str, ...]:
    return tuple(str(item) for item in LANE_SOURCES[key]["tests"] if _exists(item))


def _verifier_tests() -> tuple[str, ...]:
    ordered: list[str] = []
    for key in LANE_KEYS:
        for relative in _lane_tests(key):
            if relative not in ordered:
                ordered.append(relative)
    return tuple(ordered)


def _lane_artifacts() -> tuple[tuple[str, str], ...]:
    """Flatten every lane bundle into (source, destination) copy pairs.

    Files a parallel lane has not landed yet are skipped here so a missing report is
    reported through `lanes_missing` instead of raising from the copy step.
    """

    pairs: list[tuple[str, str]] = []
    for key in LANE_KEYS:
        sources = LANE_SOURCES[key]
        for field in ("probe", "prereg", "summary", "report"):
            relative = sources[field]
            if _exists(relative):
                name = str(relative)
                pairs.append((name, Path(name).name))
        for relative in sources["tests"]:
            name = str(relative)
            if _exists(name):
                pairs.append((name, Path(name).name))
        for relative in sources["artifacts"]:
            name = str(relative)
            if _exists(name):
                pairs.append((name, Path(name).name))
    return tuple(pairs)


def _figures() -> tuple[str, ...]:
    """Week 19 figures, discovered from disk so a renamed plot cannot drop out."""

    directory = REPOSITORY_ROOT / "probes" / "artifacts"
    if not directory.is_dir():
        return ()
    return tuple(
        sorted(
            path.relative_to(REPOSITORY_ROOT).as_posix()
            for path in directory.glob("w19_*.png")
        )
    )


FIGURES = _figures()

ARTIFACTS = CARRY_FORWARD + _lane_artifacts()

VERIFIER_TESTS = _verifier_tests()

VERIFIERS = (
    "scripts/verify_dielectric_v04.py",
    "scripts/verify_orbital_second_source.py --check",
    "scripts/verify_themol_orbital_layer.py --check",
    "scripts/verify_themol_orbital_layer_expanded.py --check",
    "scripts/verify_four_core_registry.py --check",
    "scripts/verify_reaxys_v1x_stocking_probe_roster.py --check",
    "scripts/verify_liquid_window_gate.py --check",
    "scripts/verify_walden_dn_channel.py --check",
    "probes/verify_unimol_probe_spec.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py "
        + " ".join(VERIFIER_TESTS)
        + " -q -p no:cacheprovider"
    ),
)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return (completed.stdout or "").strip()


def _worktree_status(source_root: Path) -> tuple[bool, int]:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return bool(lines), len(lines)


def _frozen_red_lines() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for relative, expected in FROZEN_RED_LINES.items():
        path = REPOSITORY_ROOT / relative
        measured = _sha256(path) if path.is_file() else None
        result[relative] = {
            "expected_sha256": expected,
            "measured_sha256": measured,
            "intact": measured == expected,
        }
    return result


CARRY_FIELDS = (
    "verdict",
    "verdict_statement",
    "promoted",
    "role",
    "pool",
    "pools",
    "gate",
    "produces_reading",
    "prereg_status",
    "promotes_no_reading",
    "main_scoreboard_untouched",
    "scoreboard_attempts_delta",
    "shot_number_taken",
    "three_questions",
    "honest_boundary",
    "honest_boundaries",
    "cross_level",
    "shot_accounting_judgement",
    "boundary_revision",
)


def _lane_prereg(key: str) -> dict[str, object]:
    """Read a lane pre-registration and prove it was locked before the run."""

    relative = str(LANE_SOURCES[key]["prereg"])
    path = REPOSITORY_ROOT / relative
    payload = read_json(path)
    return {
        "path": relative,
        "sha256": _sha256(path),
        "status": payload.get("status"),
        "locked_before_run": str(payload.get("status")) == "locked_before_run",
        "seeds": payload.get("seeds"),
    }


def _lane_payload(key: str) -> dict[str, object]:
    """Read one lane bundle and surface the fields the package quotes."""

    sources = LANE_SOURCES[key]
    report_relative = str(sources["report"])
    report_path = REPOSITORY_ROOT / report_relative
    payload: dict[str, object] = {
        "kind": LANE_KIND[key],
        "report": report_relative,
        "report_present": report_path.is_file(),
        "report_sha256": _sha256(report_path) if report_path.is_file() else None,
        "probe": str(sources["probe"]) if sources["probe"] is not None else None,
        "tests": [str(item) for item in sources["tests"]],
        "tests_present": [str(item) for item in _lane_tests(key)],
        "artifacts": [str(item) for item in sources["artifacts"]],
        "declared_files": list(_declared_files(key)),
        "declared_files_missing": [item for item in _declared_files(key) if not _exists(item)],
        "prereg": _lane_prereg(key) if _exists(sources["prereg"]) else None,
        "summary_path": str(sources["summary"]) if sources["summary"] is not None else None,
        "summary_sha256": None,
        "summary_top_level_keys": [],
        "fields": {},
    }
    carried: dict[str, object] = {}
    verdict = None
    promoted = None
    verdict_source = None
    summary_relative = sources["summary"]
    if _exists(summary_relative):
        summary = read_json(REPOSITORY_ROOT / str(summary_relative))
        verdict = summary.get("verdict")
        promoted = summary.get("promoted")
        if verdict is not None:
            verdict_source = "summary"
        # Lane summaries do not share one schema: some carry the decision at the top
        # level, some nest it under a container.  Walk the known containers so a lane
        # cannot silently report promote=True by omission.
        for container_name, verdict_field, promoted_field in (
            ("decision", "verdict", "promotable"),
            ("primary_gate", "verdict", None),
            ("decisions", "verdict", "promotable"),
            ("promotion", None, "promoted"),
        ):
            container = summary.get(container_name)
            if not isinstance(container, dict):
                continue
            if verdict is None and verdict_field is not None:
                verdict = container.get(verdict_field)
                if verdict is not None:
                    verdict_source = "summary." + container_name + "." + verdict_field
            if promoted is None and promoted_field is not None:
                promoted = container.get(promoted_field)
        for field in CARRY_FIELDS:
            if field in summary:
                carried[field] = summary[field]
        payload["summary_sha256"] = _sha256(REPOSITORY_ROOT / str(summary_relative))
        payload["summary_top_level_keys"] = sorted(str(name) for name in summary)
    if verdict is None and key in RECORDED_VERDICTS:
        verdict = RECORDED_VERDICTS[key]
        verdict_source = "recorded_lane_verdict"
    carried["verdict"] = verdict
    carried["promoted"] = bool(promoted) if promoted is not None else False
    carried["verdict_source"] = verdict_source
    payload["fields"] = carried
    return payload


def export_results(*, output_root: Path, overwrite: bool) -> dict:
    import shutil

    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(str(week_root) + " already exists; pass --overwrite")

    frozen = _frozen_red_lines()
    if not all(bool(entry["intact"]) for entry in frozen.values()):
        broken = sorted(name for name, entry in frozen.items() if not entry["intact"])
        raise ValueError("a frozen red line moved: " + ", ".join(broken))

    worktree_dirty, dirty_paths = _worktree_status(REPOSITORY_ROOT)
    head_commit = _head_commit(REPOSITORY_ROOT)

    lanes_missing = list(_missing_lane_keys())
    lanes = {key: _lane_payload(key) for key in LANE_KEYS}
    for key, payload in lanes.items():
        prereg = payload["prereg"]
        if prereg is not None and not bool(dict(prereg)["locked_before_run"]):
            raise ValueError("lane " + key + " has no locked pre-registration")

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, ARTIFACTS)

    figures: list[str] = []
    for relative in FIGURES:
        source = REPOSITORY_ROOT / relative
        if not source.is_file():
            continue
        destination = week_root / Path(relative).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        figures.append(destination.relative_to(week_root).as_posix())

    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    verdicts = {
        key: {
            "verdict": dict(payload["fields"]).get("verdict"),
            "promoted": dict(payload["fields"]).get("promoted"),
        }
        for key, payload in lanes.items()
    }
    promoted_lanes = sorted(key for key, block in verdicts.items() if bool(block["promoted"]))

    summary = {
        "schema_version": 1,
        "week": WEEK,
        "generated_at_utc": _utc_now(),
        "source_root": str(REPOSITORY_ROOT),
        "artifacts_commit": head_commit,
        "worktree_dirty": worktree_dirty,
        "worktree_dirty_paths": dirty_paths,
        "provenance_note": (
            "artifacts_commit is the commit that identifies the delivered bytes; a dirty "
            "worktree means no commit identifies them, so this field must be re-read "
            "after the close-out commit"
        ),
        "main_scoreboard": {
            "schema_version": 2,
            "version": MAIN_SCOREBOARD_VERSION,
            "baseline": {
                "value": MAIN_SCOREBOARD,
                "status": "retained_unchanged",
                "still_used_as_the_comparability_anchor": True,
            },
            "headline": {
                "value": MAIN_SCOREBOARD_HEADLINE_R2,
                "delta_vs_baseline": MAIN_SCOREBOARD_HEADLINE_DELTA_R2,
                "promoted_at_utc": MAIN_SCOREBOARD_PROMOTED_AT_UTC,
                "configuration": (
                    "hybrid Morgan+Physical 0.5*(Morgan+Physical) plus lever 4 (conformer-average "
                    "dipole, 2 columns) plus lever 8 (Li+ coordination block, 5 columns)"
                ),
                "pool": "457 rows / 97 compounds / 276 distinct (compound, temperature) pairs",
                "folds": "GroupKFold by InChIKey, 10 repeats x 5 folds, seed 42",
            },
            "touched_this_week": False,
            "touched_by": (
                "nothing: Week 19 made zero attempts at the main scoreboard. Every lane "
                "reports under its own pre-registration and its own pool, and no lane "
                "promotes a reading."
            ),
            "mixing_rule": (
                "the headline and the baseline may appear together only with this block own "
                "configuration lines; they are never divided, added, or compared as two "
                "models, and neither is ever compared with the v1.0 headline 0.364"
            ),
        },
        "shots": {
            "main_scoreboard_attempts": W19_MAIN_SCOREBOARD_ATTEMPTS,
            "cumulative_main_scoreboard_attempts": MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS,
            "cumulative_note": (
                "the Week 14 ledger read 10, Week 17 added one, Week 18 and Week 19 add "
                "none; the cumulative total is carried over unchanged"
            ),
        },
        "main_scoreboard_attempts_this_week": W19_MAIN_SCOREBOARD_ATTEMPTS,
        "cumulative_main_scoreboard_attempts": MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS,
        "frozen_reference_readings": {
            "baseline_r2": MAIN_SCOREBOARD,
            "headline_r2": MAIN_SCOREBOARD_HEADLINE_R2,
            "single_representation_r2": FROZEN_SINGLE_REPRESENTATION_R2,
            "single_representation_cross_seed_mean": FROZEN_SINGLE_REPRESENTATION_CROSS_SEED,
            "random_row_leak_reference_r2": RANDOM_ROW_LEAK_REFERENCE_R2,
        },
        "week19_seeds": list(W19_SEEDS),
        "lanes": lanes,
        "lane_verdicts": verdicts,
        "promoted_lanes": promoted_lanes,
        "no_lane_promotes": promoted_lanes == [],
        "lanes_missing": lanes_missing,
        "pending_lanes": list(PENDING_LANES),
        "figures_present": figures,
        "frozen_red_lines": frozen,
        "frozen_red_lines_all_intact": all(bool(entry["intact"]) for entry in frozen.values()),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "artifacts": copied,
    }

    write_json(week_root / "week19_summary.json", summary)
    write_json(week_root / "verification.json", verification)
    (week_root / "README.md").write_text(README_TEXT, encoding="utf-8", newline=chr(10))
    write_sha256s(week_root)
    return summary


README_TEXT = """# Week 19 交付包（文献驱动三线：现状核对 / 轨道通道外推 / 抽取与登记前置）

数据血缘: 冻结表 `data/dielectric_v03.csv` **未改动**（digest `ff2142936e…35ccce4`）；Week 17 与 Week 18 已发布工件、week1–week18 交付包未被触碰。
冻结**基线 `0.4091179943351143`** 与冻结**头条 `0.4766400383507876`**（v2：Morgan+Physical ＋ 杠杆 4 ＋ 杠杆 8；**457** 行 / **97** 化合物 = **276** 个（化合物, T）对；训练侧全表 **2029** 行）**一个字都不动**。
Week 19 不再买 ε 点数，改做《Week19立项计划_文献驱动三线》的三条线：轨道通道外推、η 第二模型族交叉、抽取与登记前置。
十一条 lane **全部 `promoted = false`**：本周对主记分牌 **0 次尝试**，累计 **11 次**不变；**0.60** 仍未达到。
生成脚本: `probes/export_week19_results.py`

## 头条（逐条照实，不许外推）

1. **D1 现状核对：计划的资产表与 Onsager 读数在字节级、数值级上高度复现，但有三处必须改判或登记**。`Batt-P30K.h5` 实测 **183,771,012** B、sha256 `587f1490…8d118d`，与冻结 `v03` 的 digest 逐位一致；HOMO/LUMO MAE 仓内实测为 **0.17662467232470583** / **0.24935401611452185** eV（转录表记 **0.304** / **0.350** 记错）；EDB 的 **18,316** 条实为「EDB + MP」合计；LUMO 交叉标定 r 只有 **0.7349044734023142**（< 0.80），故 LUMO 通道降级。
2. **D1 另登记一条计划未记的矛盾**：§W19-3 依赖写「kinematic 存量 214 行仍冻结」，而 W18 已解冻并实测过——**214** 是族级排除数，行级残差是 **86** 行。
3. **D2 Batt-P30K 直接命中：名册实测 246 行、逐字命中 77、规范化命中 78**。计划书写 239 / 76，两个数在磁盘上都对不上，属**分母口径分歧**（冻结件本次未改一个字节）；归一化主读数取与第 28.17 节同一配方的 InChIKey 全 27 位。
4. **D2 的锚点包含关系只成立一半**：**111** 个 paired_anchor 全部落在 Batt 键全集里（配方一致，成立），但 111 不是本轮命中集的子集；命中集 78 键里有 3 个不在锚点集内，锚点里有 36 个不在 ε 名册内。
5. **D3 把 Onsager 残差层放到组外（结构族）拆分下复跑，三问裁定**：Q1 `delta_layer_survives_out_of_family`（残差层仍过五门）；Q2 `sign_split_not_preserved_out_of_family`（域符号分裂在组外不保）；Q3 `zone_still_unsolvable_out_of_family`（ε>60 区组外仍无解，最佳确认型 MAE **72.0614455552206**）。
6. **D3 的池与拆分口径**：**234** 行 / **234** 个唯一 InChIKey（InChIKey 拆分器因此退化为逐行拆分）；结构族拆分器 **111** 组；本件 `promotes_no_reading = true`、`produces_deployable_model = false`。
7. **D5 η 通道换第二模型族（Chemprop D-MPNN）后首次过门**：行级 MAE 在役 **0.15686276760094522** vs Chemprop 集成 **0.08506361044387624**（Δ `-0.07179915715706899`）；族级 **0.17477197208762** vs **0.08908094784092072**（Δ `-0.08569102424669928`）。门 **0.15**：Chemprop 过、在役不过 ⇒ 该通道此前的天花板在表示层。判 `chemprop_better`，只开后续 lane，**不晋升**。
8. **D5 的混淆照实登记**：在役是冻结单配置单种子 XGBoost，Chemprop 是三种子集成；只有一次 20% 留出、无折级方差。故「表示层是天花板」这条结论带一个未排除的集成/调参混淆。
9. **N2 轨道交叉核对（我方 GFN2-xTB vs Batt-P30K，n = 49）三通道分裂**：HOMO 判 `usable`（r **0.8223**、留一 MAE **0.3475** eV ≤ 门 **0.35**），但只赢 0.0025 eV，属边界；LUMO r **0.4663**、留一 MAE **0.1984** eV 但斜率 0.055（空读数）；GAP r **0.1921**、留一 MAE **0.7445** eV、线性映射 skill 为负 ⇒ 后两者 `reference_only`。
10. **D6 排序键 v0：六通道只有两条过自己的门**——HOMO **0.19050925839013938**、LUMO **0.13855083976437643**（门 **0.20** eV），等权 0.5 / 0.5 进键；ε / η 未过门、不进键。**这是排序键，不是候选生成器**；生成闭环永久钉死（uniqueness **0.349** 证据在册）。
11. **D6 声明失效区在先**：`HIGH_PERMITTIVITY_EPS = 60.0`，ε>60 区在役 MAE **75.95675695251926**，Onsager 覆盖 0/5。
12. **D7 安全通道只登记不执行**：闪点 / 沸点 / 熔点 / 安全窗口四条候选通道，`produces_reading = false`、`shot_number_taken = null`；覆盖门 **0.3**，DN 前例 **0** / **1043**（0.0%）未过门 ⇒「拿得到预测列也未必能进特征表」。许可与版本照实登记为不可核。
13. **D4 抽取探针 Phase-0 只锁模板与门槛**：13 字段模板 + 四门槛 **0.95** / **0.80** / **0.90** / 100%，本周不执行抽取、不联网、**不占 shot 编号**。
14. **W19-7 通道转移预案触发成立**：W18 最优臂 **0.5998203128630835** 距 0.60 只差 **0.00018**，且所有已知 W18 提门杠杆均未过门 ⇒ 三级转移（η ⇒ HOMO-LUMO ⇒ 氧化还原）启动；主记分牌不动。
15. **诚实结论未变**：ε 的诚实端点仍是 **0.5861142332208197**，与冻结头条 **0.4766400383507876** 永不混比；0.60 未达、0.70 无路径；诊断仍是「排序学会了、量级学不会」。
16. **D8 / D9 按登记纳入本包**：轨道迁移决策门（`reports/w19_orbital_migration_gate.md`）与 shots 记账台账（`reports/w19_shots_ledger.md` ＋ `probes/w19_shots_ledger.json`）由并行 lane 产出；两条 lane 的读数以各自报告为准，本 README 不转述其数值。

## 交付内容

- 十一条 lane 各自的 `probe / prereg / summary / report / tests / artifacts`（见 `week19_summary.json` 的 `lanes`；缺件记在 `lanes_missing`）。
- 图（`probes/artifacts/w19_chemprop_viscosity.png`）。
- 冻结证据与红线清单（`frozen_red_lines`，逐文件 sha256 实测比对）。
- `verification.json`：逐条校验命令退出码。

*Week 19 交付包 · 生成脚本 `probes/export_week19_results.py` · 所有 lane 均为独立预注册、`promoted = false` · 冻结基线 0.4091179943351143 与冻结头条 0.4766400383507876 未动*
"""


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = export_results(output_root=args.output_root, overwrite=args.overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    missing = [str(item) for item in result.get("lanes_missing", [])]
    if missing:
        print("lanes_missing: " + ", ".join(missing))
    return 0 if result["verification_passed"] and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
