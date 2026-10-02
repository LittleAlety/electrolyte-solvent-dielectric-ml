"""Export the Week 30 deliverables.

Week 30 has two lanes and they are deliberately different in kind.

The first is a post-hoc, zero-cost decomposition of readings that already exist: the
Week 28 and Week 29 ladders re-fit the same thirteen-column dense block on the same
folds with the same five seeds and move nothing but hyperparameters.  Inside one ladder
R-squared spans 0.0989 to 0.1170 while AUC(eps>30) spans 0.0056 to 0.0072 -- a ratio of
13.7x to 21.0x -- so on this block the hyperparameters buy magnitude and not ordering.
The same decomposition shows the opposite failure for the sparse Morgan block: frozen it
cannot rank at all (AUC(eps>30) 0.4972), retuned the ordering largely returns (0.7193)
while R-squared stays near zero (0.0211).  That lane occupies no shot.

The second lane is a pre-registered ladder: by Week 29 all four capacity keys had their
own single-key reading, so Week 30 asks the one question left, combinations.  Six fixed
configurations are fit once each on the frozen folds, carrying three reproduction
anchors (the frozen configuration, the Week 29 best, and the Week 20-4 registered arm).

Shot ledger: delta 1, cumulative 17.  The four frozen readings keep their own
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

WEEK = "week30"

# The inputs the round reads and never writes.  A move here means a delivered reading
# no longer has the input it claims, so the export refuses to run.
FROZEN_RED_LINES = {
    "probes/artifacts/dielectric_xtb_full_table_migration_conformers.csv":
        "0b433df215de1eceac1d71af20148333403e2faef6537b21345b3031fb32ec76",
    "probes/artifacts/dielectric_coordination_block_features.csv":
        "e09a08d1c2620548c891b096f89bf641f6606c7bf3a5aacddcd6ae63e4849500",
    "probes/artifacts/w28_dense_hyperparameters_repeats.csv":
        "3d4eaa370de493f37ece3a0a3fa74bc20face4f29f22ae14b96fb07afa5d4db9",
    "probes/artifacts/w29_dense_binning_repeats.csv":
        "050944a7be345873371a086ea9822dd66dec66d21c6b82f950c4dc3057a24961",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w30_ordering_magnitude": {
        "title": (
            "W30-A 后验读数：稠密 13 列块上超参买的是量级而不是序，"
            "稀疏 Morgan 块则是排序与量级一起失败（不占 shot）"
        ),
        "probe": "probes/w30_ordering_magnitude.py",
        "prereg": None,
        "summary": "probes/w30_ordering_magnitude_summary.json",
        "report": "reports/w30_ordering_magnitude.md",
        "tests": ("tests/test_w30_ordering_magnitude.py",),
        "artifacts": (
            "probes/artifacts/w30_ordering_magnitude.csv",
            "probes/artifacts/w30_ordering_magnitude.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w30_combination_ladder": {
        "title": (
            "W30：稠密块组合/交互阶梯（单键定价闭合之后的组合点），"
            "冻结主记分牌池五种子 GroupKFold by InChIKey"
        ),
        "probe": "probes/w30_combination_ladder.py",
        "prereg": "probes/w30_combination_ladder_prereg.json",
        "summary": "probes/w30_combination_ladder_summary.json",
        "report": "reports/w30_combination_ladder.md",
        "tests": (
            "tests/test_w30_combination_ladder.py",
            "tests/test_w29_dense_binning.py",
        ),
        "artifacts": (
            "probes/artifacts/w30_combination_ladder_repeats.csv",
            "probes/artifacts/w30_combination_ladder.png",
        ),
        "produces_reading": True,
        "promoted": False,
    },
}

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week30_project_charter.md", "week30_project_charter.md"),
    ("reports/week30_delivery_readme.md", "week30_delivery_readme.md"),
    ("reports/week30_ordering_magnitude.md", "w30_ordering_magnitude.md"),
    ("reports/week30_combination_ladder.md", "w30_combination_ladder.md"),
    ("reports/week29_project_charter.md", "week29_project_charter.md"),
    ("reports/week29_delivery_readme.md", "week29_delivery_readme.md"),
    ("reports/week28_delivery_readme.md", "week28_delivery_readme.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("paper/make_paper_docx_template.py", "make_paper_docx_template.py"),
    ("probes/export_week29_results.py", "export_week29_results.py"),
    ("probes/export_week30_results.py", "export_week30_results.py"),
)

LANE_KEYS = tuple(LANES)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w30_ordering_magnitude.png",
    "probes/artifacts/w30_combination_ladder.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w30_combination_ladder.py "
        "tests/test_w30_ordering_magnitude.py tests/test_w29_dense_binning.py "
        "-q -p no:cacheprovider"
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


README_TEXT = (REPOSITORY_ROOT / "reports/week30_delivery_readme.md").read_text(encoding="utf-8")
LADDER_SUMMARY_PATH = REPOSITORY_ROOT / "probes/w30_combination_ladder_summary.json"
DECOMPOSITION_SUMMARY_PATH = REPOSITORY_ROOT / "probes/w30_ordering_magnitude_summary.json"


def _verdicts() -> dict[str, dict[str, object]]:
    payload = read_json(LADDER_SUMMARY_PATH)
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
    ladder = read_json(LADDER_SUMMARY_PATH)
    decomposition = read_json(DECOMPOSITION_SUMMARY_PATH)
    readings = ladder["readings"]
    blocks = {block["week"]: block for block in decomposition["ladders"]}

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
        "cumulative_main_scoreboard_attempts": 17,
        "shots_by_lane": {
            "w30_ordering_magnitude": 0,
            "w30_combination_ladder": 1,
        },
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "external_deliverables": [destination for _, destination in EXTERNAL_DELIVERABLES],
        "figures": [Path(figure).name for figure in FIGURES],
        "verdicts": verdicts,
        "headline_readings": {
            "anchor_seed42": readings["anchor_seed42"],
            "anchor_seed42_gap": readings["anchor_seed42_gap"],
            "frozen_cross_seed": readings["frozen_mean"],
            "frozen_cross_seed_gap": readings["frozen_gap"],
            "week29_best_reproduced": readings["w29_mean"],
            "week29_best_gap": readings["w29_gap"],
            "week20_4_registered_reproduced": readings["w20_mean"],
            "week20_4_gap": readings["w20_gap"],
            "best_new_combination": readings["best_new_label"],
            "best_new_combination_cross_seed": readings["best_new_mean"],
            "best_new_delta_vs_week29": readings["best_new_delta"],
            "seeds_beating_week29": readings["seeds_beating_w29"],
            "global_best_arm": readings["global_best_label"],
            "global_best_cross_seed": readings["global_best_mean"],
            "ceiling_delta_vs_week20_4": readings["ceiling_delta"],
            "gate_r2": 0.6,
        },
        "ordering_vs_magnitude": {
            week: {
                "arms": block["arms"],
                "r2_spread": block["spread"]["r2_mean"],
                "spearman_spread": block["spread"]["spearman_mean"],
                "auc_gt30_spread": block["spread"]["auc_gt30_mean"],
                "ratio_r2_over_auc30": block["ratio_r2_over_auc30"],
            }
            for week, block in blocks.items()
        },
        "files": sorted(copied),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "W30 的池、评分掩码、训练掩码、分组切分器、表示与五种子集合全部取自冻结主记分牌；组合阶梯的六个档位只覆盖 max_depth / n_estimators / learning_rate / min_child_weight / max_bin / reg_lambda 六列声明键。",
            "这是阶梯不是搜索：六个固定配置在同样的折上各拟合一次，没有任何选择，外层测试行只被预测、从未参与任何决定。",
            "组合阶梯带回三条复现锚：冻结档位（seed 42 0.6080587938801277，逐位）、W29 最佳档位（0.6031674542995844，容差 1e-6）、W20-4 注册臂（0.6216672295270079，容差 1e-6）；任一条不成立就不报任何结论。",
            "W30-A 是**后验读数**：判据写在 W28/W29 产物既存之后，**不占主记分牌 shot**，不得当作预注册结论引用；它只读两张已提交的逐重复表，输入 sha256 逐条复核。",
            "不新增量子化学、不装依赖、不联网；表示就是 13 列稠密物理块，一列不加、一列不减。",
            "缺行不插补、不丢弃评分行；折任务的 random_state 是固定常量 42（冻结折任务的定义）。",
            "主记分牌 shot = 1（累计 17）；四个冻结读数未动。",
            "不引用任何 Reaxys 数值；THEMol（CC BY-NC 4.0）不入交付包；Batt-P30K（MIT）与 RX-392 / SolvFunc-87 只作参考层。",
        ],
    }
    write_json(week_root / "week30_summary.json", summary)
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