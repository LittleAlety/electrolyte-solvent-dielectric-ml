"""Export the Week 28 deliverables -- the dense-block hyperparameter retune.

Week 27 priced the width penalty on the frozen main scoreboard pool: the thirteen
ddCOSMO response columns cost 0.096956 when appended to the dense lever-4 physical
block, while a row-shuffled block of the same width still cost 0.006099, above the
0.005 inert line.  The frozen estimator settings (max_depth 2, 200 trees, lr 0.05,
max_bin 64) were chosen for a 2048-column sparse Morgan fingerprint, and the dense
lever-4 physical block has 13 columns, so two levels of depth is four leaves per tree.

Week 28 takes two shots on the same frozen pool (2029 base training rows / 457 scored
rows over 97 compounds, GroupKFold by InChIKey, five frozen seeds):

* shot 1 -- nested retune: inside every outer fold the training rows are split by
  compound into three inner folds, each of the six grid entries is scored on the
  pooled inner holdout, and the winner is refit on the whole outer training set.  The
  outer test rows never take part in the choice.  The same procedure runs on the
  Week 27 response block, and a shuffled-training-target placebo prices the procedure;
* shot 2 -- fixed ladder: every grid entry is fit once on the same folds with no
  selection at all, so "is there a better fixed setting" is a separate fact from
  "can the selector find it".

Shot ledger: delta 2, cumulative 15.  The four frozen readings keep their own
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

WEEK = "week28"

# The inputs the round reads and never writes.  A move here means a delivered reading
# no longer has the input it claims, so the export refuses to run.
FROZEN_RED_LINES = {
    "probes/artifacts/w26_dielectric_scan.csv":
        "8ac4fc2a2b50185f989cda358fd39203c6204dc6b3dcaae17affdb5f55ec325f",
    "probes/artifacts/w26_born_fit.csv":
        "e50ae20acf007cb48d93eef6a05d5eb72c831b163272a2170b58e9275c9c7393",
    "probes/artifacts/w26_anion_gate.csv":
        "6dd5663921a6c85e6c9d6fda7a02f38aacd0c97278e409b7cff5002911a3acc9",
    "probes/artifacts/w27_dielectric_response_block.csv":
        "1b4ed9d851d3afa915d7e5d65b1aeace7e8813edf00c6920aef793d4102d2ad2",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w28_dense_hyperparameters": {
        "title": (
            "W28：稠密块 XGB 超参的嵌套重调（第 1 枪）与固定档位阶梯（第 2 枪），"
            "冻结主记分牌池五种子 GroupKFold by InChIKey"
        ),
        "probe": "probes/w28_dense_hyperparameters.py",
        "prereg": "probes/w28_dense_hyperparameters_prereg.json",
        "summary": "probes/w28_dense_hyperparameters_summary.json",
        "report": "reports/w28_dense_hyperparameters.md",
        "tests": (
            "tests/test_w28_dense_hyperparameters.py",
            "tests/test_w27_dielectric_response.py",
        ),
        "artifacts": (
            "probes/artifacts/w28_dense_hyperparameters_selection.csv",
            "probes/artifacts/w28_dense_hyperparameters_repeats.csv",
            "probes/artifacts/w28_dense_hyperparameters.png",
        ),
        "produces_reading": True,
        "promoted": False,
    },
}

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week28_project_charter.md", "week28_project_charter.md"),
    ("reports/week28_delivery_readme.md", "week28_delivery_readme.md"),
    ("reports/week27_project_charter.md", "week27_project_charter.md"),
    ("reports/week27_delivery_readme.md", "week27_delivery_readme.md"),
    ("reports/week27_dielectric_response.md", "w27_dielectric_response.md"),
    ("reports/week26_project_charter.md", "week26_project_charter.md"),
    ("reports/week26_delivery_readme.md", "week26_delivery_readme.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("paper/make_paper_docx_template.py", "make_paper_docx_template.py"),
    ("probes/export_week27_results.py", "export_week27_results.py"),
    ("probes/export_week28_results.py", "export_week28_results.py"),
)

LANE_KEYS = tuple(LANES)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w28_dense_hyperparameters.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w28_dense_hyperparameters.py "
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


README_TEXT = (REPOSITORY_ROOT / "reports/week28_delivery_readme.md").read_text(encoding="utf-8")
PROBE_SUMMARY_PATH = REPOSITORY_ROOT / "probes/w28_dense_hyperparameters_summary.json"


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
        "main_scoreboard_attempts_delta": 2,
        "cumulative_main_scoreboard_attempts": 15,
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "external_deliverables": [destination for _, destination in EXTERNAL_DELIVERABLES],
        "figures": [Path(figure).name for figure in FIGURES],
        "verdicts": verdicts,
        "headline_readings": {
            "anchor_seed42": readings["anchor_seed42"],
            "anchor_seed42_gap": readings["anchor_seed42_gap"],
            "anchor_cross_seed_gap": readings["anchor_cross_seed_gap"],
            "frozen_cross_seed": readings["frozen_mean"],
            "retuned_cross_seed": readings["retuned_mean"],
            "retune_delta": readings["retune_delta"],
            "response_block_delta_frozen": readings["response_delta_frozen"],
            "response_block_delta_retuned": readings["response_delta_retuned"],
            "placebo_mean": readings["placebo_mean"],
            "morgan_retune_delta": readings["control_delta"],
            "ladder_best_entry": readings["ladder_best_entry"],
            "ladder_best_mean": readings["ladder_best_mean"],
            "ladder_delta_vs_frozen": readings["ladder_delta"],
            "seeds_with_a_deep_mode": readings["seeds_with_a_deep_mode"],
            "gate_r2": 0.6,
            "w27_physical_block_mean": readings["w27_expected"],
        },
        "files": sorted(copied),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "W28 的池、评分掩码、训练掩码、分组切分器、拟合器与五种子集合全部取自冻结主记分牌；本枪只移动网格里的三个超参。",
            "选择是嵌套的：内层折只切外层训练行，外层测试行从未参与任何选择；平局取网格里更早的一档，过程确定可复现。",
            "不新增量子化学、不装依赖、不联网；响应块由盘上已有的 W26 产物派生，与 W27 用的是同一块。",
            "缺行不插补：块在名册之外的池行上留 NaN，交给 XGBoost 自带的缺失值处理；不计算任何折内统计量。",
            "安慰剂只打乱外层折内的训练靶值（生成器种子 2026 在预注册里冻结），测试靶值保持真实。",
            "第 2 枪的阶梯没有任何选择：每一档都是一个诚实读数，用来把『有没有更好的固定档位』与『选择器能不能挑中它』分开。",
            "主记分牌 shot = 2（累计 15）；四个冻结读数未动，四条输入红线逐条 sha256 复核。",
            "不引用任何 Reaxys 数值；THEMol（CC BY-NC 4.0）不入交付包；Batt-P30K（MIT）与 RX-392 / SolvFunc-87 只作参考层。",
        ],
    }
    write_json(week_root / "week28_summary.json", summary)
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
