"""Export the Week 38 deliverables.

Week 38 is a post hoc round: it turns "abstain" into a coverage-guaranteed shortlist,
quantifies structure-vs-function, tests the Kirkwood-Onsager residual prediction, and
closes the last unhandled README section 11 item.  No main-scoreboard shot is taken
(cumulative stays at 19).

  * W38-A (conformal shortlist) reads the shipped out-of-fold prediction rows and builds
    a compound-split conformal shortlist.  Calibration and evaluation are split BY
    COMPOUND (98 compounds -> 49 / 49), which is what makes the coverage claim valid.
    H38a2 is a registered negative: the pooled precision at tau=30 / alpha=0.10 is
    0.8125, under the 0.90 gate; tightening to alpha=0.05 gives 1.000 (6 picks).
  * W38-B (structure != function) runs a Morgan-Tanimoto nearest-neighbour label-gap
    spectrum over 241 compounds with a 999-permutation null.  The headline is the
    fingerprint-blind class: 26 pairs at Tanimoto >= 0.99, of which 4 differ by >= 5 in
    epsilon, up to 13.25 (1,4-dioxane 2.2 vs 15-crown-5 15.5).  H38b1 is a registered
    negative (no Tanimoto >= 0.80 pair reaches |delta eps| >= 30; the ceiling is 25.98).
  * W38-C (Onsager residual) tests the falsifiable prediction that the residual of the
    single-molecule description concentrates on self-associating protic liquids.  Using
    only the table's hbd column as the mechanical domain rule, the donor-domain median
    g_rel is 2.5016x the non-donor median (z = 4.076, p = 0.006, leave-top-5-out 2.5597).
  * W38-E (timestamp closeout) fixes README section 11 item 19: write_json_stable keeps
    the on-disk bytes when only generated_at_utc / elapsed_seconds differ, so re-running
    the Week 37 export probe no longer dirties the tracked summary.  Status is
    "mechanism fixed, migration incomplete" (1 of 111 tracked timestamped JSONs migrated).

The four frozen readings keep their own definitions: 0.4091179943351143,
0.4766400383507876, 0.5861142332208197, 0.6216672295270079.
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

WEEK = "week38"

FROZEN_RED_LINES = {
    "paper/paper_zh_draft_v2.md":
        "dfb3b282f8ccf76653d244a6a2c618d92a6e12003d012b81cca9f08dc9c6e78e",
    "paper/_v2_body_b.md":
        "e1d5fb38e71cd1336bbdc8caba3b5b4c57822072c84cbc8443268fdb2650751d",
    "paper/_v2_appendix.md":
        "4677c9ece09ac0fa3b42b7b0a2e28d018d4665adfe6668aef6c620d1fd99d8ef",
    "paper/_v2_concl.md":
        "f7feb3c4795f0a2839d282f7ffc22e542eed7542cede164ca44406aefe47d4b2",
    "paper/_v2_disc_extra.md":
        "5916a27e58233161021640e75647a3ff6ff38089bb8935763298ca2ac6ac2257",
    "paper/build_paper_v2.py":
        "be1121e4216cc48e1dc62b7ae08c7ea084c22bbfc194aabda47f2b318b80f8c7",
    "paper/_v2_splices.json":
        "cd25c9de88826b17262999045f815085f464e117a6e1aad714273db6f175d70a",
    "probes/artifacts/w35_gated_reference_register.csv":
        "b201c776ff66bf07cf85a2e68039d2547f31da3d59845e62a3641f98b69b098c",
    "probes/artifacts/w33_kendall_null_budget.csv":
        "eb16242737abc9b0c8308fb855a2f52cc3a3ba3b755726a67b4e480b0afe0b28",
    "probes/artifacts/w32_rank_stability.json":
        "106983b41e84808b331043927df3aba9afc9addcebdf985d9845d4330e2e8e95",
    "probes/artifacts/w34_channel_dashboard.csv":
        "f5db0cd34e8e66cdc4ccf34388bf24fddabfc97ccb4e2f739b5ef6f2629f62ca",
    "data/processed/redox_state_legality_registry.csv":
        "a01272b3e75514a609295275d18c82c39fb65c5bc27056feb4ed8c6cd0c6b60d",
    "data/processed/four_core_key_registry.csv":
        "e42885eb43779b7a4d472da88fefe018fe94150ff5b6fba86b3ed9bc83dc8bee",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "frozen_single_representation_endpoint": 0.5861142332208197,
    "frozen_promoted_arm_w20_4": 0.6216672295270079,
}

LANES = {
    "w38_conformal_shortlist": {
        "title": "W38-A 后验读数：保形筛选举荐（化合物级切分，覆盖-规模曲线；不占 shot）",
        "probe": "probes/w38_conformal_shortlist.py",
        "prereg": None,
        "summary": "probes/artifacts/w38_conformal_shortlist_summary.json",
        "report": "reports/w38_conformal_shortlist.md",
        "tests": ("tests/test_w38_conformal_shortlist.py",),
        "artifacts": (
            "probes/artifacts/w38_conformal_coverage.csv",
            "probes/artifacts/w38_conformal_shortlist.csv",
            "probes/artifacts/w38_conformal_coverage.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w38_structure_function": {
        "title": "W38-B 后验读数：结构≠功能（指纹盲区 26 对 / 置换检验；不占 shot）",
        "probe": "probes/w38_structure_function.py",
        "prereg": None,
        "summary": "probes/artifacts/w38_structure_function_summary.json",
        "report": "reports/w38_structure_function.md",
        "tests": ("tests/test_w38_structure_function.py",),
        "artifacts": (
            "probes/artifacts/w38_structure_nn.csv",
            "probes/artifacts/w38_structure_pairs.csv",
            "probes/artifacts/w38_structure_function.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w38_onsager_residual": {
        "title": "W38-C 后验读数：Kirkwood-Onsager 残差诊断（域间中位数比 2.50，z=4.08；不占 shot）",
        "probe": "probes/w38_onsager_residual.py",
        "prereg": None,
        "summary": "probes/artifacts/w38_onsager_residual_summary.json",
        "report": "reports/w38_onsager_residual.md",
        "tests": ("tests/test_w38_onsager_residual.py",),
        "artifacts": (
            "probes/artifacts/w38_onsager_compounds.csv",
            "probes/artifacts/w38_onsager_domains.csv",
            "probes/artifacts/w38_onsager_g.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w38_summary_timestamp": {
        "title": "W38-E 后验治理件：时间戳脏树收口（稳定写入 + 端到端守卫；不占 shot）",
        "probe": "probes/w38_summary_timestamp.py",
        "prereg": None,
        "summary": "probes/artifacts/w38_summary_timestamp_summary.json",
        "report": "reports/w38_timestamp_closeout.md",
        "tests": ("tests/test_w38_summary_timestamp.py",),
        "artifacts": (
            "probes/artifacts/w38_timestamp_inventory.csv",
            "probes/export_results_common.py",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w38_data_recon": {
        "title": "W38-D 后验侦察：四核心量新来源核实 + 渠道红线登记（9 判据；不占 shot）",
        "probe": "probes/w38_data_recon.py",
        "prereg": None,
        "summary": "probes/artifacts/w38_recon_summary.json",
        "report": "reports/w38_data_recon.md",
        "tests": ("tests/test_w38_data_recon.py",),
        "artifacts": (
            "probes/artifacts/w38_recon_hits.csv",
            "probes/artifacts/w38_recon_channels.csv",
            "probes/artifacts/w38_recon_hits.png",
            "reports/w38_reaxys_literature_index.md",
        ),
        "produces_reading": False,
        "promoted": False,
    },
}

LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week38_project_charter.md", "week38_project_charter.md"),
    ("reports/week38_delivery_readme.md", "week38_delivery_readme.md"),
    ("reports/work_log_week1_to_week36.md", "work_log_week1_to_week36.md"),
    ("probes/export_week37_results.py", "export_week37_results.py"),
)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w38_conformal_coverage.png",
    "probes/artifacts/w38_structure_function.png",
    "probes/artifacts/w38_onsager_g.png",
    "probes/artifacts/w38_recon_hits.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/check_paper_artifact_consistency.py",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w38_conformal_shortlist.py "
        "tests/test_w38_structure_function.py tests/test_w38_onsager_residual.py "
        "tests/test_w38_summary_timestamp.py tests/test_w38_data_recon.py "
        "tests/test_w37_gate_admission_export.py "
        "-q -p no:cacheprovider"
    ),
)

DELIVERY_README_PATH = REPOSITORY_ROOT / "reports/week38_delivery_readme.md"
README_TEXT = (DELIVERY_README_PATH.read_text(encoding="utf-8")
               if DELIVERY_README_PATH.is_file()
               else "# Week 38 交付包\n\n"
                    "本包由 probes/export_week38_results.py 生成；交付说明见 "
                    "reports/week38_delivery_readme.md。\n")

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
    summary_path = REPOSITORY_ROOT / str(lane["summary"]) if lane["summary"] else None
    report_path = REPOSITORY_ROOT / str(lane["report"])
    return {"title": lane["title"], "probe": lane["probe"], "report": lane["report"],
            "report_sha256": sha256_file(report_path) if report_path.is_file() else None,
            "tests": list(lane["tests"]), "artifacts": list(lane["artifacts"]),
            "prereg": None, "summary_path": lane["summary"],
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

    pairs: list[tuple[str, str]] = []
    for source_path, destination in CARRY_FORWARD:
        if (REPOSITORY_ROOT / source_path).is_file():
            pairs.append((source_path, destination))
    for key in LANE_KEYS:
        lane = LANES[key]
        for field in ("probe", "summary", "report"):
            value = lane[field]
            if value is not None and (REPOSITORY_ROOT / str(value)).is_file():
                pairs.append((str(value), Path(str(value)).name))
        for item in (*lane["tests"], *lane["artifacts"]):
            name = str(item)
            if (REPOSITORY_ROOT / name).is_file():
                pairs.append((name, Path(name).name))
    pairs.extend((figure, Path(figure).name) for figure in FIGURES)

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, pairs)
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    verdicts = _lane_verdicts()
    failed = sorted(identifier for identifier, item in verdicts.items()
                    if str(item["verdict"]) == "判否")
    registered = sorted(identifier for identifier, item in verdicts.items()
                        if str(item["verdict"]) == "判否")
    summary = {
        "schema": "week38_delivery/summary@1",
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
                                      "四条 lane 全部是后验读数 / 治理件：只读盘上既有产物，"
                                      "不拟合主记分牌臂、不新增特征列、不改 METRIC_NAMES。"},
        "verdicts": {identifier: item["verdict"] for identifier, item in verdicts.items()},
        "verdicts_failed": failed,
        "verdicts_registered_negatives": registered,
        "files": sorted(copied),
        "figures": list(FIGURES),
        "external_deliverables": {},
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "四条 lane 全部后验：0 shot（累计仍 19）、不改 METRIC_NAMES、不新增特征列、缺行不插补、不动四个冻结读数。",
            "W38-A 的覆盖是**边际覆盖**，不是给定化合物上的后验概率；必须并读区间宽度中位数与未决份额。校准/评估按化合物切分，同一化合物的行不跨侧。",
            "W38-A 的 H38a2 是**已登记判否**（tau=30 / alpha=0.10 合并精度 0.8125 < 0.90）；阈值不原地改，改法（反解「达到精度门所需的最小 alpha」）登记进下一份预注册。",
            "W38-B 是**提示性证据**（单一指纹、单一描述符集、n 有限）；极值对不得读成「某分子不可预测」。H38b1 是**已登记判否**（Tanimoto ≥ 0.80 且 |Δε| ≥ 30 的对不存在，实测上限 25.98）。",
            "W38-C 的 g_rel 是**无量纲相对量**，只可做域间比较，不得与文献 g 绝对值对照；`dipole_D` / `mu_sq_over_Vm` 有质量疑点且 `L/x` 在 μ → 0 处发散，故主判据全用中位数/秩，并加 μ ≥ 1.0 D 的数值门槛（H38c8）。",
            "W38-C 的域规则继承 RDKit 的 Lipinski donor 定义，该定义不把水算作给体，所以 water 落在 g ≈ 1 域——这是域规则的已知边界。",
            "W38-E 的状态是**机制已修、迁移未完成**：111 个带时间戳的被跟踪 JSON 里已迁移 1 个，其余待迁移；稳定写入只覆盖顶层键。",
            "本包携带的三张图（w38_*.png）均为本轮产物；不携带任何第三方数据集内容。",
        ],
    }
    write_json(week_root / "week38_summary.json", summary)
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
    print(json.dumps({key: result[key] for key in ("week", "artifacts_commit", "worktree_dirty",
                                                   "worktree_dirty_paths", "lanes_missing",
                                                   "promoted_lanes", "verification_passed")},
                     ensure_ascii=False, indent=2))
    return 0 if not result["lanes_missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())