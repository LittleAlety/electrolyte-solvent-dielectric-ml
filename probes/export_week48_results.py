"""Export the Week 48 deliverables.

Week 48 is a governance and debt-closure week: it seals the tree and re-exports the version-state
package, lands the Ue 1997 adjudication, closes every registered debt in section 4.6, and delivers
the venue memo.  No main-scoreboard shot is taken (cumulative stays at 19).

  * W48-A seals the worktree and re-exports week47 on the commit state; the package pins the version
    state and an idempotent re-export is byte-identical.
  * W48-B lands the Ue 1997 disposition as not_available (source retrieval failed) and corrects the
    planned DOI 10.1149/1.1837585 to 10.1149/1.1837882.
  * W48-C delivers the venue memo (5 candidates x 4 axes) and records the submission package as
    deferred until the venue is chosen.
  * W48-D writes the section 4.6 debt-closure block so no registered debt stays silent.

The four frozen readings keep their own definitions: 0.4091179943351143, 0.4766400383507876,
0.5861142332208197, 0.6216672295270079.
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
    write_json_stable,
    write_sha256s,
)
from probes.export_week41_results import FROZEN_RED_LINES

WEEK = "week48"

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "frozen_single_representation_endpoint": 0.5861142332208197,
    "frozen_promoted_arm_w20_4": 0.6216672295270079,
}

LANES = {
    "w48_tree_seal": {
        "title": "W48-A 治理件：封树与干净重导（8 判据全成立；包改钉版本态；不占 shot）",
        "probe": "probes/w48_tree_seal_check.py",
        "prereg": "probes/w48_tree_seal_prereg.json",
        "summary": "probes/artifacts/w48_tree_seal_summary.json",
        "report": "reports/w48_tree_seal.md",
        "tests": (),
        "artifacts": ("probes/artifacts/w48_tree_seal_criteria.csv",),
        "produces_reading": False,
        "promoted": False,
    },
    "w48_ue1997_track": {
        "title": "W48-B 收口件：Ue 1997 三态落定（4 判据全成立；not_available；不占 shot）",
        "probe": "probes/w48_ue1997_track.py",
        "prereg": "probes/w48_ue1997_prereg.json",
        "summary": "probes/artifacts/w48_ue1997_summary.json",
        "report": "reports/w48_ue1997.md",
        "tests": ("tests/test_w48_ue1997_track.py",),
        "artifacts": ("probes/artifacts/w48_ue1997_ledger.csv",
                      "probes/artifacts/w48_ue1997_criteria.csv"),
        "produces_reading": False,
        "promoted": False,
    },
    "w48_submission_pack": {
        "title": "W48-C 计划件：venue 备忘录与形式漂移守卫（3 判据全成立；C2/C3 deferred；不占 shot）",
        "probe": "probes/w48_submission_pack.py",
        "prereg": "probes/w48_submission_pack_prereg.json",
        "summary": "probes/artifacts/w48_submission_pack_summary.json",
        "report": "reports/w48_submission_pack.md",
        "tests": ("tests/test_w48_submission_pack.py",),
        "artifacts": ("probes/artifacts/w48_submission_pack_criteria.csv",
                      "reports/w48_venue_memo.md"),
        "produces_reading": False,
        "promoted": False,
    },
    "w48_debt_closure": {
        "title": "W48-D 收口件：§4.6 欠账终稿（3 判据全成立；无沉默项；不占 shot）",
        "probe": "probes/w48_debt_closure.py",
        "prereg": "probes/w48_debt_closure_prereg.json",
        "summary": "probes/artifacts/w48_debt_closure_summary.json",
        "report": "reports/w48_debt_closure.md",
        "tests": ("tests/test_w48_debt_closure.py",),
        "artifacts": ("probes/artifacts/w48_debt_closure_criteria.csv",),
        "produces_reading": False,
        "promoted": False,
    },
}
LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("reports/week48_delivery_readme.md", "week48_delivery_readme.md"),
    ("probes/export_week41_results.py", "export_week41_results.py"),
)

EXTERNAL_DELIVERABLES = {
    "themol_orbital_layer_expanded": {
        "path": "data/processed/themol_orbital_layer_expanded.csv",
        "rows": 5117,
        "shipped": False,
        "why_not_shipped": "第三方衍生层内容不进交付包；同名 CSV 在仓库内按摘要行数与 source_level 复核。",
    },
    "qm9_dataset": {
        "path": "data/external/qm9_dataset.csv",
        "sha256": "01d196218c78a0e29575ef8cf9ceb6d2f33fda9cddc3e4b5bd133e191fa2e053",
        "rows": 133885,
        "license": "CC BY 4.0",
        "shipped": False,
        "why_not_shipped": "第三方数据集内容不进交付包；同名 CSV 在仓库内按摘要 sha256 校验。",
    },
    "batt_p30k": {
        "path": "data/raw/batt/Batt-P30K.h5",
        "sha256": "587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d",
        "molecules": 29519,
        "license": "MIT",
        "shipped": False,
        "why_not_shipped": "第三方数据集内容不进交付包；同名 HDF5 在仓库内按摘要 sha256 校验。",
    },
    "pubchemqc_b3lyp_layer": {
        "path": "data/processed/orbital_second_source_layer.csv",
        "sha256": "ba55897a296181267cc0673cbf2d4d98d17b3e5de8280958b7896556e053abfe",
        "rows": 912,
        "license": "CC BY 4.0",
        "shipped": False,
        "why_not_shipped": "第三方衍生层内容不进交付包；同名 CSV 在仓库内按摘要 sha256 校验。",
    },
}
FIGURES: tuple[str, ...] = ()
VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/check_paper_artifact_consistency.py",
    "scripts/verify_paper_figures.py",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w48_ue1997_track.py "
        "tests/test_w48_debt_closure.py tests/test_w48_submission_pack.py "
        "tests/test_w47_anchor_crosscheck.py tests/test_w47_experimental_track.py "
        "tests/test_w47_lane_c_plan.py tests/test_w47_paper_readiness.py "
        "-q -p no:cacheprovider"
    ),
)
DELIVERY_README_PATH = REPOSITORY_ROOT / "reports" / "week48_delivery_readme.md"
README_TEXT = (DELIVERY_README_PATH.read_text(encoding="utf-8")
               if DELIVERY_README_PATH.is_file()
               else "# Week 48 交付包\n\n由 probes/export_week48_results.py 生成。\n")

SUMMARY_PATHS = {key: REPOSITORY_ROOT / str(lane["summary"]) for key, lane in LANES.items()}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source_root,
                               capture_output=True, text=True, check=False)
    return (completed.stdout or "").strip()


def _worktree_status(source_root: Path) -> tuple[bool, int]:
    completed = subprocess.run(["git", "status", "--porcelain"], cwd=source_root,
                               capture_output=True, text=True, check=False)
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return bool(lines), len(lines)


def _frozen_red_lines() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for relative, expected in FROZEN_RED_LINES.items():
        path = REPOSITORY_ROOT / relative
        measured = sha256_file(path) if path.is_file() else None
        result[relative] = {"expected_sha256": expected, "measured_sha256": measured,
                            "intact": measured == expected}
    return result


def _lane_payload(key: str) -> dict[str, object]:
    lane = LANES[key]
    declared: list[str] = [str(lane["probe"]), str(lane["report"]),
                           *[str(item) for item in lane["tests"]],
                           *[str(item) for item in lane["artifacts"]]]
    if lane["summary"]:
        declared.append(str(lane["summary"]))
    if lane.get("prereg"):
        declared.append(str(lane["prereg"]))
    summary_path = REPOSITORY_ROOT / str(lane["summary"]) if lane["summary"] else None
    report_path = REPOSITORY_ROOT / str(lane["report"])
    prereg = lane.get("prereg")
    prereg_path = REPOSITORY_ROOT / str(prereg) if prereg else None
    return {"title": lane["title"], "probe": lane["probe"], "report": lane["report"],
            "report_sha256": sha256_file(report_path) if report_path.is_file() else None,
            "tests": list(lane["tests"]), "artifacts": list(lane["artifacts"]),
            "prereg": prereg,
            "prereg_sha256": (sha256_file(prereg_path)
                              if prereg_path and prereg_path.is_file() else None),
            "summary_path": lane["summary"],
            "summary_sha256": (sha256_file(summary_path)
                               if summary_path and summary_path.is_file() else None),
            "declared_files": declared,
            "declared_files_missing": [item for item in declared
                                       if not (REPOSITORY_ROOT / item).is_file()],
            "produces_reading": lane["produces_reading"], "promoted": lane["promoted"]}


def _missing_lane_keys() -> tuple[str, ...]:
    return tuple(key for key in LANE_KEYS
                 if not (REPOSITORY_ROOT / str(LANES[key]["report"])).is_file())


def _lane_verdicts() -> dict[str, dict[str, object]]:
    verdicts: dict[str, dict[str, object]] = {}
    for key, path in SUMMARY_PATHS.items():
        if not path.is_file():
            continue
        payload = read_json(path)
        for item in payload.get("criteria", []):
            verdicts[str(item["id"])] = {
                "lane": key,
                "verdict": str(item["verdict"]),
                "description": str(item["description"]),
                "value": item.get("value"),
                "threshold": item.get("threshold"),
            }
    return verdicts


def _registered_negatives() -> list[str]:
    registered: set[str] = set()
    for path in SUMMARY_PATHS.values():
        if not path.is_file():
            continue
        payload = read_json(path)
        registered.update(str(item) for item in payload.get("registered_negatives", []))
    return sorted(registered)


def export_results(output_root: Path = DEFAULT_OUTPUT_ROOT, *,
                   overwrite: bool = False) -> dict[str, object]:
    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise SystemExit("week48 export already exists; pass --overwrite")
    week_root.mkdir(parents=True, exist_ok=True)

    lanes = {key: _lane_payload(key) for key in LANE_KEYS}
    lanes_missing = list(_missing_lane_keys())
    worktree_dirty, dirty_paths = _worktree_status(REPOSITORY_ROOT)
    frozen = _frozen_red_lines()
    head_commit = _head_commit(REPOSITORY_ROOT)

    pairs: list[tuple[str, str]] = []
    for source_path, destination in CARRY_FORWARD:
        if (REPOSITORY_ROOT / source_path).is_file():
            pairs.append((source_path, destination))
    for key in LANE_KEYS:
        lane = LANES[key]
        for field in ("probe", "summary", "report"):
            value = lane[field]
            if value and (REPOSITORY_ROOT / str(value)).is_file():
                pairs.append((str(value), Path(str(value)).name))
        for item in (*lane["tests"], *lane["artifacts"]):
            name = str(item)
            if (REPOSITORY_ROOT / name).is_file():
                pairs.append((name, Path(name).name))
    copied = copy_artifacts(REPOSITORY_ROOT, week_root, pairs)
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)
    verdicts = _lane_verdicts()
    failed = sorted(identifier for identifier, item in verdicts.items()
                    if str(item["verdict"]) == "判否")
    registered = _registered_negatives()
    unregistered = sorted(set(failed) - set(registered))
    summary = {
        "schema": "week48_delivery/summary@1",
        "week": WEEK,
        "generated_at_utc": _utc_now(),
        "artifacts_commit": head_commit,
        "worktree_dirty": worktree_dirty,
        "worktree_dirty_paths": dirty_paths,
        "source_root": str(REPOSITORY_ROOT),
        "output_root": str(output_root),
        "lanes": lanes,
        "lanes_missing": lanes_missing,
        "promoted_lanes": [],
        "reading_lanes": [],
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "frozen_red_lines_intact": all(bool(entry["intact"]) for entry in frozen.values()),
        "main_scoreboard_shots": {"this_week": 0, "cumulative_after": 19,
                                  "why_not_a_shot":
                                      "四条 lane 全是封树、欠账收口、形式守卫与打包件：不拟合主记分牌臂、"
                                      "不新增特征列、不改 METRIC_NAMES、不动冻结读数。"},
        "verdicts": {identifier: item["verdict"] for identifier, item in verdicts.items()},
        "verdicts_failed": failed,
        "verdicts_registered_negatives": registered,
        "verdicts_unregistered_failures": unregistered,
        "files": sorted(copied),
        "figures": list(FIGURES),
        "external_deliverables": EXTERNAL_DELIVERABLES,
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "四条 lane 全部只读或形式件：0 shot（累计仍 19）、不改 METRIC_NAMES、不新增特征列、"
            "缺行不插补、不动四个冻结读数。",
            "Ue 1997 还原侧收口为 not_available（取件失败是合法收口）；计划候选 DOI 10.1149/1.1837585 "
            "已证伪并更正为 10.1149/1.1837882；不转录、不补造任何还原锚点。",
            "还原轨核心集覆盖并集 2/7 < 5 ⇒ H47a2 拒答分支触发，「不可判定」与功效下限必须同报。",
            "n = 4 时 MDE 0.9826 / 精确拒绝率 1/24：本轮收口价值不是翻盘主判据。",
            "§4.6 已登记欠账逐条落字（第 33/36/40/42/45/46/49-52 条 + D2/D3 + dipole_transfer_v1），无沉默项。",
            "venue 选择权在用户；本轮只出四轴备忘录，投稿包按 venue 未定登记 deferred。",
            "任何修数未授权（dipole_transfer_v1 维持 registered_not_authorized）；不改 v2 论文线与 _v2_* 冻结件，"
            "改稿只落 v3。",
            "本包不携带任何第三方数据集内容与外部 PDF；第三方件按 data/ 路径 + sha256 复现。",
        ],
    }
    write_json_stable(week_root / "week48_summary.json", summary)
    write_json_stable(week_root / "verification.json", verification)
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
    print(json.dumps({key: result[key] for key in ("week", "artifacts_commit", "worktree_dirty",
                                                   "worktree_dirty_paths", "lanes_missing",
                                                   "promoted_lanes", "verification_passed")},
                     ensure_ascii=False, indent=2))
    return 0 if not result["lanes_missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
