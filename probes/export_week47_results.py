"""Export the Week 47 deliverables.

Week 47 is a read-only transcription, cross-check and governance week.  It reads the three
transcribed anchor tables correctly, accounts for the core-set coverage, executes the executable
part of the primary criterion, downgrades the experimental track, freezes the Lane C protocol and
assesses submission readiness.  No main-scoreboard shot is taken (cumulative stays at 19).

  * W47-A accounts for the computed-anchor coverage and runs the oxidation-axis
    computed-vs-experimental cross-consistency reading: core-set reduction coverage union is 2 < 5,
    so the H47a2 refusal branch fires and the D0-D3 primary criterion is not executed; on n = 4 the
    oxidation tau_b = 0.6667 with exact one-sided p = 0.1667, top-1 overlap 1.00 / top-2 0.50 and
    unresolved share 0.3333 (sensitivity reading only, and the bootstrap CI is uninformative).
  * W47-B reclassifies Moshkovich 2001 as mechanism evidence only and registers a 9-item
    experimental-track ledger (every item carries a verdict and a non-empty condition_flag); the
    track verdict is not_evaluable_condition_differs.
  * W47-C freezes the D2 (r2SCAN-3c) and D3 (ddCOSMO) protocols and the nitrile triad (3 solvents x
    3 checks = 9 rows); with no ORCA on this host every item is pending_orca_compute and the
    scheduling estimate is 76 single points.
  * W47-D back-fills 13 references, adds section 3.32, updates the positioning and limitation
    sections, and reports a 10-gate submission-readiness assessment (verdict conditional_go) with
    the residual scientific blockers listed; no appendix heading and all 25 figures exist on disk.
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
    write_json_stable,
    write_sha256s,
)
from probes.export_week41_results import FROZEN_RED_LINES

WEEK = "week47"

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "frozen_single_representation_endpoint": 0.5861142332208197,
    "frozen_promoted_arm_w20_4": 0.6216672295270079,
}

LANES = {
    "w47_anchor_crosscheck": {
        "title": "W47-A 计算件：计算锚点覆盖核算与氧化轴交叉一致性（9 判据全成立；主判据按 H47a2 不可判定；不占 shot）",
        "probe": "probes/w47_anchor_crosscheck.py",
        "prereg": "probes/w47_anchor_prereg.json",
        "summary": "probes/artifacts/w47_anchor_crosscheck_summary.json",
        "report": "reports/w47_anchor_crosscheck.md",
        "tests": ("tests/test_w47_anchor_crosscheck.py",),
        "artifacts": (
            "probes/artifacts/w47_anchor_coverage.csv",
            "probes/artifacts/w47_oxidation_crosscheck.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w47_experimental_track": {
        "title": "W47-B 台账件：实验还原轨候选逐件裁定（8 判据全成立；not_evaluable_condition_differs；不占 shot）",
        "probe": "probes/w47_experimental_track.py",
        "prereg": "probes/w47_experimental_track_prereg.json",
        "summary": "probes/artifacts/w47_experimental_track_summary.json",
        "report": "reports/w47_experimental_track.md",
        "tests": ("tests/test_w47_experimental_track.py",),
        "artifacts": (
            "probes/artifacts/w47_experimental_ledger.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w47_lane_c_plan": {
        "title": "W47-C 计划件：D2/D3 协议冻结与 ORCA 算力欠账登记（9 判据全成立；pending_orca_compute；不占 shot）",
        "probe": "probes/w47_lane_c_plan.py",
        "prereg": "probes/w47_orca_rerun_prereg.json",
        "summary": "probes/artifacts/w47_lane_c_summary.json",
        "report": "reports/w47_lane_c_plan.md",
        "tests": ("tests/test_w47_lane_c_plan.py",),
        "artifacts": (
            "probes/artifacts/w47_lane_c_plan.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w47_paper_readiness": {
        "title": "W47-D 治理件：论文回填复核与投稿就绪评估（12 判据全成立；conditional_go；不占 shot）",
        "probe": "probes/w47_paper_readiness.py",
        "prereg": "probes/w47_paper_readiness_prereg.json",
        "summary": "probes/artifacts/w47_paper_readiness_summary.json",
        "report": "reports/w47_paper_readiness.md",
        "tests": ("tests/test_w47_paper_readiness.py",),
        "artifacts": (
            "probes/artifacts/w47_paper_readiness_ledger.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
}
LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week47_project_charter.md", "week47_project_charter.md"),
    ("reports/week47_delivery_readme.md", "week47_delivery_readme.md"),
    ("reports/work_log_week47.md", "work_log_week47.md"),
    ("probes/w47_anchor_prereg.json", "w47_anchor_prereg.json"),
    ("probes/w47_experimental_track_prereg.json", "w47_experimental_track_prereg.json"),
    ("probes/w47_orca_rerun_prereg.json", "w47_orca_rerun_prereg.json"),
    ("probes/w47_paper_readiness_prereg.json", "w47_paper_readiness_prereg.json"),
    ("reports/w47_literature_verdict.md", "w47_literature_verdict.md"),
    ("tools/taub_power.py", "taub_power.py"),
    ("probes/export_week41_results.py", "export_week41_results.py"),
)

EXTERNAL_DELIVERABLES = {
    "themol_orbital_layer_expanded": {
        "path": "data/processed/themol_orbital_layer_expanded.csv",
        "rows": 5117,
        "source_level": "GFN2-xTB//B3LYP-D3(BJ)/DZVP (gas-phase single point on the DFT geometry)",
        "shipped": False,
        "why_not_shipped": "第三方衍生层内容不进交付包；同名 CSV 在仓库内按本摘要的行数与 source_level 复核。",
    },
    "qm9_dataset": {
        "path": "data/external/qm9_dataset.csv",
        "sha256": "01d196218c78a0e29575ef8cf9ceb6d2f33fda9cddc3e4b5bd133e191fa2e053",
        "rows": 133885,
        "license": "CC BY 4.0",
        "citation": "Ramakrishnan et al. 2014, Sci. Data 1:140022",
        "shipped": False,
        "why_not_shipped": "第三方数据集内容不进交付包；同名 CSV 在仓库内按本摘要的 sha256 校验。",
    },
    "batt_p30k": {
        "path": "data/raw/batt/Batt-P30K.h5",
        "sha256": "587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d",
        "molecules": 29519,
        "license": "MIT",
        "citation": "Batt-SLM / Batt-P30K (GSDS)",
        "shipped": False,
        "why_not_shipped": "第三方数据集内容不进交付包；同名 HDF5 在仓库内按本摘要的 sha256 校验。",
    },
    "pubchemqc_b3lyp_layer": {
        "path": "data/processed/orbital_second_source_layer.csv",
        "sha256": "ba55897a296181267cc0673cbf2d4d98d17b3e5de8280958b7896556e053abfe",
        "rows": 912,
        "license": "CC BY 4.0",
        "citation": "molssiai-hub/pubchemqc-b3lyp; DOI 10.1021/acs.jcim.3c00899",
        "shipped": False,
        "why_not_shipped": "第三方衍生层内容不进交付包；同名 CSV 在仓库内按本摘要的 sha256 校验。",
    },
}
FIGURES: tuple[str, ...] = ()
VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/check_paper_artifact_consistency.py",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w47_anchor_crosscheck.py "
        "tests/test_w47_experimental_track.py tests/test_w47_lane_c_plan.py "
        "tests/test_w47_paper_readiness.py tests/test_w38_data_recon.py "
        "tests/test_w37_gate_admission_export.py -q -p no:cacheprovider"
    ),
)
DELIVERY_README_PATH = REPOSITORY_ROOT / "reports/week47_delivery_readme.md"
README_TEXT = (DELIVERY_README_PATH.read_text(encoding="utf-8")
               if DELIVERY_README_PATH.is_file()
               else "# Week 47 交付包\n\n"
                    "本包由 probes/export_week47_results.py 生成；交付说明见 "
                    "reports/week47_delivery_readme.md。\n")

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
        raise SystemExit("week47 export already exists; pass --overwrite")
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
    pairs.extend((figure, Path(figure).name) for figure in FIGURES)

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, pairs)
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    verdicts = _lane_verdicts()
    failed = sorted(identifier for identifier, item in verdicts.items()
                    if str(item["verdict"]) == "判否")
    registered = _registered_negatives()
    unregistered = sorted(set(failed) - set(registered))
    summary = {
        "schema": "week47_delivery/summary@1",
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
                                      "四条 lane 全是只读计算、侦察与治理件：不拟合主记分牌臂、"
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
            "四条 lane 全部只读：0 shot（累计仍 19）、不改 METRIC_NAMES、不新增特征列、缺行不插补、不动四个冻结读数。",
            "还原轨核心集覆盖并集 2/7 < 5 ⇒ H47a2 拒答分支触发，D0–D3 主判据不执行、降级为「不可判定 + 功效下限」"
            "（与 W33 ORCA 层先例同规格，不算失败）；「不可判定」与功效下限必须同报。",
            "不得用任何计算系列（Borodin 2013 Table 1 / Borodin 2015 图 6–8 / 2019 换算）补造实验还原锚点；"
            "「Borodin 2013 有 EA 表」是错误归属（其 ref51 Vydrov 2006 的 G2 离子测试集只有 58 个 EA）。",
            "氧化轴计算-实验交叉一致性（n = 4：tau_b 0.6667 / 精确 p 0.1667 / Top-1 1.00 / 未解析 0.3333）"
            "只作敏感性读数，不进判决、不写进摘要级结论；tau_b 必须与精确单侧 p 同报。",
            "Moshkovich 2001 重分类为 mechanism_evidence_only（PC 单溶剂）；实验轨 not_evaluable_condition_differs，"
            "只作 D2 的敏感性检验对象，不作 Gate 1 主检验替换。",
            "D2 的 r2SCAN-3c 版本与 D3（ddCOSMO 垂直 EA）未计算，需新 ORCA 单点；腈类三项检查未执行；"
            "全部条目 pending_orca_compute，完成后按同一预注册复跑 Lane A 并两版并列登记。",
            "任何修数未授权（dipole_transfer_v1 维持 registered_not_authorized）；不改 v2 论文线与 _v2_* 冻结件，改稿只落 v3。",
            "投稿就绪裁决为 conditional_go（10 条形式闸门全过），剩余阻塞项是科学证据（锚点 0 / D2-D3 未算 / Ue 1997 待取原件 / strict same-level 源 0）；本包不作出投稿决策。",
            "本包不携带任何第三方数据集内容（含扩展层 CSV、QM9 CSV、Batt-P30K 与 PubChemQC 衍生层）与外部 PDF；第三方件按 data/ 路径 + sha256/行数复现，外部 PDF 按文件名 + 字节数 + sha256 钉住，许可与署名见 reports/decisions_log.md。",
        ],
    }
    write_json_stable(week_root / "week47_summary.json", summary)
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
