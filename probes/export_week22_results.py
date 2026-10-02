"""Export the Week 22 deliverables -- the external-review remediation round.

Week 22 does not buy a new scoreboard reading.  It buys *defensibility*: the
external review (A/B/C/D groups) is turned into executable assertions wherever
the repository can carry them, and everything else is registered as an explicit
open item instead of being papered over.

Four lanes, none of them promoted, none of them touching a frozen number:

* W22-1 -- the leakage-safety theorem, tightened from ``A_axis`` to ``2*A_axis``
  (analytic bound + Monte-Carlo coverage + leave-one-rung-out prognosis);
* W22-2 -- statistical hardening of the n=49 ranking arm (paired bootstrap CI,
  leave-one-compound sensitivity, multiple-comparison correction);
* W22-3 -- the unified data document plus the broad-pool minimum-information
  budget demonstration;
* W22-4 -- the review response matrix, in-repo editorial fixes, and the
  minimum-information-budget decision flow figure.

Nothing on the frozen side moves: 0.4091179943351143, 0.4766400383507876,
0.5861142332208197 and 0.6216672295270079 keep their own definitions, and the
main scoreboard gets 0 attempts this week (cumulative stays at 12).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    read_json,
    run_verifiers,
    sha256_file,
    write_json,
    write_sha256s,
)

WEEK = "week22"

FROZEN_RED_LINES = {
    "data/dielectric_v03.csv": "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4",
    "probes/l3_stage1_pilot_pool.csv": "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18",
    "probes/l3_backvalidation_prereg.json": "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98",
    "data/processed/dielectric_observations_v11plus.csv": "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    "probes/dielectric_r2_levers_prereg.json": "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa",
    "data/viscosity_v01.csv": "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w22_1_safety_theorem": {
        "title": "W22-1：漏解安全定理严格化（A3/D1，解析界 + 蒙特卡洛）",
        "probe": "probes/w22_safety_theorem.py",
        "prereg": "probes/w22_safety_theorem_prereg.json",
        "summary": "probes/w22_safety_theorem_summary.json",
        "report": "reports/w22_safety_theorem.md",
        "tests": ("tests/test_w22_safety_theorem.py",),
        "artifacts": (
            "probes/artifacts/w22_safety_theorem_leakage.png",
            "probes/artifacts/w22_safety_theorem_coverage.png",
        ),
        "produces_reading": True,
        "promoted": False,
    },
    "w22_2_stat_hardening": {
        "title": "W22-2：n=49 排序臂统计加固（B1/B2/B3/B4）",
        "probe": "probes/w22_stat_hardening.py",
        "prereg": "probes/w22_stat_hardening_prereg.json",
        "summary": "probes/w22_stat_hardening_summary.json",
        "report": "reports/w22_stat_hardening.md",
        "tests": ("tests/test_w22_stat_hardening.py",),
        "artifacts": (
            "probes/artifacts/w22_stat_hardening_pair_bootstrap.csv",
            "probes/artifacts/w22_stat_hardening_leave_one_out.csv",
            "probes/artifacts/w22_stat_hardening_multiple_comparison.csv",
        ),
        "produces_reading": True,
        "promoted": False,
    },
    "w22_3_data_consolidation": {
        "title": "W22-3：统一数据文档 + broad-pool 最小信息预算演示（B5/D7）",
        "probe": "probes/build_unified_data_document.py",
        "prereg": "probes/w22_broad_pool_budget_prereg.json",
        "summary": "probes/w22_broad_pool_budget_summary.json",
        "report": "reports/w22_data_consolidation.md",
        "tests": ("tests/test_w22_unified_document.py",),
        "artifacts": (
            "probes/w22_broad_pool_budget.py",
            "probes/artifacts/w22_broad_pool_budget.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w22_4_review_response": {
        "title": "W22-4：评审逐条整改矩阵 + 仓内口径修订 + 最小信息预算流程图（A/B/C/D 文字组）",
        "probe": "probes/w22_min_information_figure.py",
        "prereg": None,
        "summary": None,
        "report": "paper/review_response_matrix.md",
        "tests": (),
        "artifacts": ("probes/artifacts/w22_min_information_budget.png",),
        "produces_reading": False,
        "promoted": False,
    },
}

LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week22_project_charter.md", "week22_project_charter.md"),
    ("reports/week22_delivery_readme.md", "week22_delivery_readme.md"),
    ("probes/export_week22_results.py", "export_week22_results.py"),
)

# Deliverables that live outside the repository (the user-facing unified document).
EXTERNAL_DELIVERABLES = (
    (r"E:\Claude Code\电解质ML\成果输出\数据统一文档.md", "数据统一文档.md"),
)

FIGURES: tuple[str, ...] = ()

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/verify_themol_orbital_layer.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w22_safety_theorem.py "
        "tests/test_w22_stat_hardening.py tests/test_w22_unified_document.py -q -p no:cacheprovider"
    ),
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_root, capture_output=True, text=True, check=False
    )
    return (completed.stdout or "").strip()


def _worktree_status(source_root: Path) -> tuple[bool, int]:
    completed = subprocess.run(
        ["git", "status", "--porcelain"], cwd=source_root, capture_output=True, text=True, check=False
    )
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return bool(lines), len(lines)


def _frozen_red_lines() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for relative, expected in FROZEN_RED_LINES.items():
        path = REPOSITORY_ROOT / relative
        measured = sha256_file(path) if path.is_file() else None
        result[relative] = {
            "expected_sha256": expected,
            "measured_sha256": measured,
            "intact": measured == expected,
        }
    return result


def _lane_payload(key: str) -> dict[str, object]:
    lane = LANES[key]
    declared: list[str] = [
        str(lane["probe"]),
        str(lane["report"]),
        *[str(item) for item in lane["tests"]],
        *[str(item) for item in lane["artifacts"]],
    ]
    if lane["prereg"]:
        declared.append(str(lane["prereg"]))
    if lane["summary"]:
        declared.append(str(lane["summary"]))
    prereg_block = None
    if lane["prereg"]:
        path = REPOSITORY_ROOT / str(lane["prereg"])
        payload = read_json(path)
        status = payload.get("status", payload.get("prereg_status"))
        prereg_block = {
            "path": str(lane["prereg"]),
            "sha256": sha256_file(path),
            "status": status,
            "locked_before_run": status == "locked_before_run",
        }
    summary_path = REPOSITORY_ROOT / str(lane["summary"]) if lane["summary"] else None
    return {
        "title": lane["title"],
        "probe": lane["probe"],
        "report": lane["report"],
        "report_sha256": sha256_file(REPOSITORY_ROOT / str(lane["report"]))
        if (REPOSITORY_ROOT / str(lane["report"])).is_file()
        else None,
        "tests": list(lane["tests"]),
        "artifacts": list(lane["artifacts"]),
        "prereg": prereg_block,
        "summary_path": lane["summary"],
        "summary_sha256": sha256_file(summary_path) if summary_path and summary_path.is_file() else None,
        "declared_files": declared,
        "declared_files_missing": [item for item in declared if not (REPOSITORY_ROOT / item).is_file()],
        "produces_reading": lane["produces_reading"],
        "promoted": lane["promoted"],
    }


def _missing_lane_keys() -> tuple[str, ...]:
    return tuple(key for key in LANE_KEYS if not (REPOSITORY_ROOT / str(LANES[key]["report"])).is_file())


README_TEXT = (REPOSITORY_ROOT / "reports/week22_delivery_readme.md").read_text(encoding="utf-8")


def _copy_external(week_root: Path) -> list[str]:
    written: list[str] = []
    for source, destination in EXTERNAL_DELIVERABLES:
        source_path = Path(source)
        if not source_path.is_file():
            continue
        destination_path = week_root / destination
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        written.append(destination_path.relative_to(week_root).as_posix())
    return written


def export_results(*, output_root: Path, overwrite: bool) -> dict:
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

    pairs: list[tuple[str, str]] = []
    for source, destination in CARRY_FORWARD:
        if (REPOSITORY_ROOT / source).is_file():
            pairs.append((source, destination))
    for key in LANE_KEYS:
        lane = LANES[key]
        for field in ("probe", "summary", "report"):
            value = lane[field]
            if value is not None:
                name = str(value)
                if (REPOSITORY_ROOT / name).is_file():
                    pairs.append((name, Path(name).name))
        if lane["prereg"]:
            name = str(lane["prereg"])
            if (REPOSITORY_ROOT / name).is_file():
                pairs.append((name, Path(name).name))
        for item in (*lane["tests"], *lane["artifacts"]):
            name = str(item)
            if (REPOSITORY_ROOT / name).is_file():
                pairs.append((name, Path(name).name))
    pairs.extend((figure, Path(figure).name) for figure in FIGURES)

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, pairs)
    copied.extend(_copy_external(week_root))
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    promoted_lanes = sorted(key for key, payload in lanes.items() if bool(payload["promoted"]))
    reading_lanes = sorted(key for key, payload in lanes.items() if bool(payload["produces_reading"]))

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
            "worktree means no commit identifies them, so this field must be re-read after "
            "the follow-up commit."
        ),
        "lanes": lanes,
        "lanes_missing": lanes_missing,
        "reading_lanes": reading_lanes,
        "promoted_lanes": promoted_lanes,
        "main_scoreboard_attempts_delta": 0,
        "cumulative_main_scoreboard_attempts": 12,
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "external_deliverables": [destination for _, destination in EXTERNAL_DELIVERABLES],
        "figures": [Path(figure).name for figure in FIGURES],
        "files": sorted(copied),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "不引用 Reaxys 数值；不新增昂贵量化计算；不动任何冻结件。",
            "本周 0 次主记分牌尝试，累计仍 12 次；四个冻结读数未动。",
            "评审原文 PDF 不在本仓：依赖原文页面/数据表的条目登记为待办，绝不编造原文数字。",
        ],
    }
    write_json(week_root / "week22_summary.json", summary)
    write_json(week_root / "verification.json", verification)
    (week_root / "README.md").write_text(README_TEXT, encoding="utf-8", newline="\n")
    write_sha256s(week_root)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = export_results(output_root=args.output_root, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "week",
                    "artifacts_commit",
                    "worktree_dirty",
                    "worktree_dirty_paths",
                    "lanes_missing",
                    "promoted_lanes",
                    "verification_passed",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not result["lanes_missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())