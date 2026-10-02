"""Export the Week 29 deliverables -- the dense-block binning and column-sampling ladder.

Week 28 took two pre-registered shots at the capacity question on the frozen main
scoreboard pool (2029 base training rows / 457 scored rows over 97 compounds, GroupKFold
by InChIKey, five frozen seeds): a nested retune over max_depth / n_estimators /
learning_rate, and a fixed ladder of the same six entries.  Both froze max_bin = 64,
colsample_bytree = 0.8 and reg_lambda = 1.0 as "not moved", yet those three keys are
capacity and regularisation knobs in exactly the same sense as depth: 64 bins on a
thirteen-column dense float block means every split searches 63 candidate thresholds per
feature, and colsample_bytree = 0.8 drops about three of the thirteen columns from every
tree.

Week 29 is a fixed ladder over exactly those three keys, with the frozen depth, tree
count and learning rate held still.  Nothing is selected: each of the six configurations
is fit once on the frozen folds, so every entry is an honest reading and no test row ever
takes part in a decision.  The frozen configuration is entry 0, so the anchor and the
ladder share one code path, and the anchor must reproduce the frozen seed-42 reading
0.6080587938801277 to 1e-9 and the frozen five-seed endpoint 0.5861142332208197 to 1e-6
before anything is reported.

Shot ledger: delta 1, cumulative 16.  The four frozen readings keep their own
definitions: 0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
0.6216672295270079.
"""
from __future__ import annotations

import argparse
import json
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

WEEK = "week29"

# The inputs the round reads and never writes.  A move here means a delivered reading
# no longer has the input it claims, so the export refuses to run.
FROZEN_RED_LINES = {
    "probes/artifacts/dielectric_xtb_full_table_migration_conformers.csv":
        "0b433df215de1eceac1d71af20148333403e2faef6537b21345b3031fb32ec76",
    "probes/artifacts/dielectric_coordination_block_features.csv":
        "e09a08d1c2620548c891b096f89bf641f6606c7bf3a5aacddcd6ae63e4849500",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w29_dense_binning": {
        "title": (
            "W29：稠密块分箱粒度与列采样的固定档位阶梯（只移动 W28 逐字冻结的三个容量键），"
            "冻结主记分牌池五种子 GroupKFold by InChIKey"
        ),
        "probe": "probes/w29_dense_binning.py",
        "prereg": "probes/w29_dense_binning_prereg.json",
        "summary": "probes/w29_dense_binning_summary.json",
        "report": "reports/w29_dense_binning.md",
        "tests": (
            "tests/test_w29_dense_binning.py",
            "tests/test_w28_dense_hyperparameters.py",
        ),
        "artifacts": (
            "probes/artifacts/w29_dense_binning_repeats.csv",
            "probes/artifacts/w29_dense_binning.png",
        ),
        "produces_reading": True,
        "promoted": False,
    },
}

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week29_project_charter.md", "week29_project_charter.md"),
    ("reports/week29_delivery_readme.md", "week29_delivery_readme.md"),
    ("reports/week28_project_charter.md", "week28_project_charter.md"),
    ("reports/week28_delivery_readme.md", "week28_delivery_readme.md"),
    ("reports/week28_dense_hyperparameters.md", "w28_dense_hyperparameters.md"),
    ("reports/week27_project_charter.md", "week27_project_charter.md"),
    ("reports/week27_delivery_readme.md", "week27_delivery_readme.md"),
    ("reports/week27_dielectric_response.md", "w27_dielectric_response.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("paper/make_paper_docx_template.py", "make_paper_docx_template.py"),
    ("probes/export_week28_results.py", "export_week28_results.py"),
    ("probes/export_week29_results.py", "export_week29_results.py"),
)

LANE_KEYS = tuple(LANES)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w29_dense_binning.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w29_dense_binning.py "
        "tests/test_w27_dielectric_response.py -q -p no:cacheprovider"
    ),
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_root, capture_output=True, text=True,
        check=False
    )
    return (completed.stdout or "").strip()


def _worktree_status(source_root: Path) -> tuple[bool, int]:
    completed = subprocess.run(
        ["git", "status", "--porcelain"], cwd=source_root, capture_output=True, text=True,
        check=False
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
            "revision": payload.get("revision"),
            "locked_before_run": status == "locked_before_run",
        }
    summary_path = REPOSITORY_ROOT / str(lane["summary"]) if lane["summary"] else None
    report_path = REPOSITORY_ROOT / str(lane["report"])
    return {
        "title": lane["title"],
        "probe": lane["probe"],
        "report": lane["report"],
        "report_sha256": sha256_file(report_path) if report_path.is_file() else None,
        "tests": list(lane["tests"]),
        "artifacts": list(lane["artifacts"]),
        "prereg": prereg_block,
        "summary_path": lane["summary"],
        "summary_sha256": (sha256_file(summary_path)
                           if summary_path and summary_path.is_file() else None),
        "declared_files": declared,
        "declared_files_missing": [item for item in declared
                                   if not (REPOSITORY_ROOT / item).is_file()],
        "produces_reading": lane["produces_reading"],
        "promoted": lane["promoted"],
    }


def _missing_lane_keys() -> tuple[str, ...]:
    return tuple(key for key in LANE_KEYS
                 if not (REPOSITORY_ROOT / str(LANES[key]["report"])).is_file())


README_TEXT = (REPOSITORY_ROOT / "reports/week29_delivery_readme.md").read_text(encoding="utf-8")
PROBE_SUMMARY_PATH = REPOSITORY_ROOT / "probes/w29_dense_binning_summary.json"


def _verdicts() -> dict[str, dict[str, object]]:
    payload = read_json(PROBE_SUMMARY_PATH)
    return {entry["id"]: entry for entry in payload["verdicts"]}


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
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    promoted_lanes = sorted(key for key, payload in lanes.items() if bool(payload["promoted"]))
    reading_lanes = sorted(key for key, payload in lanes.items()
                           if bool(payload["produces_reading"]))
    verdicts = _verdicts()
    probe_summary = read_json(PROBE_SUMMARY_PATH)
    readings = probe_summary["readings"]

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
        "main_scoreboard_attempts_delta": 1,
        "cumulative_main_scoreboard_attempts": 16,
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "external_deliverables": [destination for _, destination in EXTERNAL_DELIVERABLES],
        "figures": [Path(figure).name for figure in FIGURES],
        "verdicts": verdicts,
        "headline_readings": {
            "anchor_seed42": readings["anchor_seed42"],
            "anchor_seed42_gap": readings["anchor_seed42_gap"],
            "frozen_configuration": readings["frozen_label"],
            "frozen_cross_seed": readings["frozen_mean"],
            "week28_cross_check_gap": readings["w28_gap"],
            "best_configuration": readings["best_config"],
            "best_cross_seed": readings["best_mean"],
            "best_delta_vs_frozen": readings["best_delta"],
            "seeds_beating_frozen": readings["seeds_beating_frozen"],
            "gate_r2": 0.6,
            "w27_physical_block_mean": 0.5003081615487617,
        },
        "files": sorted(copied),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "W29 的池、评分掩码、训练掩码、分组切分器、表示与五种子集合全部取自冻结主记分牌；本枪只移动 W28 逐字冻结的三个容量键（max_bin / colsample_bytree / reg_lambda）。",
            "这是阶梯不是搜索：六个固定配置在同样的折上各拟合一次，没有任何选择，外层测试行只被预测、从未参与任何决定。",
            "不新增量子化学、不装依赖、不联网；表示就是 W28 的 13 列稠密物理块，一列不加、一列不减。",
            "缺行不插补、不丢弃评分行；折任务的 random_state 是固定常量 42（冻结折任务的定义）。",
            "锚：seed 42 的冻结档位逐位复现 0.6080587938801277（容差 1e-9）；冻结档位的五种子端点复现 W28 的冻结臂 0.5861142332208197（容差 1e-6）。任一条不成立就不报任何结论。",
            "主记分牌 shot = 1（累计 16）；四个冻结读数未动，两条输入红线逐条 sha256 复核。",
            "不引用任何 Reaxys 数值；THEMol（CC BY-NC 4.0）不入交付包；Batt-P30K（MIT）与 RX-392 / SolvFunc-87 只作参考层。",
        ],
    }
    write_json(week_root / "week29_summary.json", summary)
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
