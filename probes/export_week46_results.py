"""Export the Week 46 deliverables.

Week 46 is a read-only computation, reconnaissance and governance-sync week.  It
re-defines the reduction axis as a family of pre-registered candidate
descriptors, scopes how many same-apparatus reduction anchors exist on disk,
turns the tau_b noise floor into a power tool, and back-fills the paper.  No
main-scoreboard shot is taken (cumulative stays at 19).

  * W46-A compares the reduction-axis descriptor family: on the (candidate x
    layer) grid the r2SCAN-3c layer has only 0 legally-admitted D1 molecules and
    2 D3 molecules (< 5), so the primary criterion is not evaluable; D2 has no
    r2SCAN-3c feedstock; the GFN2 gas-phase subset (n = 48) reports D0-D1 tau_b
    0.7394, D0-D2 -0.3794, D1-D2 -0.4486 with unresolved fractions 0.3980 /
    0.8697 / 0.8874.  Verdict: 不可判定 (not a failure).
  * W46-B scopes the same-apparatus reduction anchors: 515 CSVs scanned, 151
    candidate columns and 30 named cross-checks; every computed series is
    rejected_computed_only, the dielectric anchors are rejected_criterion_mismatch,
    the off-disk references are not_available_on_disk, only PubChemQC passes the
    layer gate, and n_anchors = n_pairs_effective = 0, so the H46a2 refusal
    branch fires.
  * W46-C tools the tau_b power analysis: n = 7 MDE is 0.6540558963871848; the
    power at tau_true = 0.4 / 0.6 / 0.8 is 0.2300 / 0.6299 / 1.0 and the
    probability of clearing the 0.9 threshold is 0.0044 / 0.0114 / 0.0809;
    n_min is 17 / 8 / 6; alpha_eff(7) = 0.034523809523809526; the continuous MC
    calibration is 0.05015; the pointwise agreement with the W33 exact null has
    max_abs_delta 0.0.
  * W46-D back-fills the paper and re-runs the guards: 7/7 references in place,
    the T1/T2 positioning paragraph and the three Gate-1 wording fixes in place,
    section 3.31 present, decisions_log 28.101 and README items 45-48 registered;
    the guard re-run refuses 3 negative controls, scans the acceptance and static
    pools with zero failures / mutations / frozen-reading writes, and keeps the
    9 registered negatives and the cumulative shot cap 19.

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

WEEK = "week46"

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "frozen_single_representation_endpoint": 0.5861142332208197,
    "frozen_promoted_arm_w20_4": 0.6216672295270079,
}

LANES = {
    "w46_reduction_family": {
        "title": "W46-A 计算件：还原轴候选描述符族的预注册比较（8 判据全成立，主判据不可判定；不占 shot）",
        "probe": "probes/w46_reduction_family.py",
        "prereg": "probes/w46_reduction_family_prereg.json",
        "summary": "probes/artifacts/w46_reduction_family_summary.json",
        "report": "reports/w46_reduction_family.md",
        "tests": ("tests/test_w46_reduction_family.py",),
        "artifacts": (
            "probes/artifacts/w46_reduction_family_candidates.csv",
            "probes/artifacts/w46_reduction_family_tau.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w46_reduction_anchor_recon": {
        "title": "W46-B 侦察件：还原轴同装置锚点系列侦察与准入（10 判据全成立；n_anchors = 0，拒答分支触发；不占 shot）",
        "probe": "probes/w46_reduction_anchor_recon.py",
        "prereg": "probes/w46_reduction_anchor_recon_prereg.json",
        "summary": "probes/artifacts/w46_reduction_anchor_recon_summary.json",
        "report": "reports/w46_reduction_anchor_recon.md",
        "tests": ("tests/test_w46_reduction_anchor_recon.py",),
        "artifacts": (
            "probes/artifacts/w46_reduction_anchor_candidates.csv",
            "probes/artifacts/w46_reduction_anchor_ledger.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w46_taub_power": {
        "title": "W46-C 工具件：tau_b 噪声地板功效分析工具化（10 判据全成立；不占 shot）",
        "probe": "probes/w46_taub_power.py",
        "prereg": "probes/w46_taub_power_prereg.json",
        "summary": "probes/artifacts/w46_taub_power_summary.json",
        "report": "reports/w46_taub_power.md",
        "tests": ("tests/test_w46_taub_power.py",),
        "artifacts": (
            "probes/artifacts/w46_taub_power_table.csv",
            "probes/artifacts/w46_taub_power_mde.csv",
            "probes/artifacts/w46_taub_power_retro.csv",
            "probes/artifacts/w46_taub_power_floor.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w46_paper_governance": {
        "title": "W46-D 治理件：论文回填复核与治理守卫复跑（8 判据全成立；不占 shot）",
        "probe": "probes/w46_paper_governance.py",
        "prereg": "probes/w46_paper_governance_prereg.json",
        "summary": "probes/artifacts/w46_paper_governance_summary.json",
        "report": "reports/w46_paper_governance.md",
        "tests": ("tests/test_w46_paper_governance.py",),
        "artifacts": (
            "probes/artifacts/w46_paper_governance_ledger.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
}
LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week46_project_charter.md", "week46_project_charter.md"),
    ("reports/week46_delivery_readme.md", "week46_delivery_readme.md"),
    ("reports/work_log_week46.md", "work_log_week46.md"),
    ("probes/w46_taub_power_prereg.json", "w46_taub_power_prereg.json"),
    ("probes/w46_reduction_anchor_recon_prereg.json", "w46_reduction_anchor_recon_prereg.json"),
    ("probes/w46_reduction_family_prereg.json", "w46_reduction_family_prereg.json"),
    ("probes/w46_paper_governance_prereg.json", "w46_paper_governance_prereg.json"),
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
FIGURES: tuple[str, ...] = (
    "probes/artifacts/w46_taub_power.png",
    "probes/artifacts/w46_reduction_family.png",
)
VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/check_paper_artifact_consistency.py",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w46_taub_power.py "
        "tests/test_w46_reduction_anchor_recon.py tests/test_w46_reduction_family.py "
        "tests/test_w46_paper_governance.py tests/test_w38_data_recon.py "
        "tests/test_w37_gate_admission_export.py -q -p no:cacheprovider"
    ),
)
DELIVERY_README_PATH = REPOSITORY_ROOT / "reports/week46_delivery_readme.md"
README_TEXT = (DELIVERY_README_PATH.read_text(encoding="utf-8")
               if DELIVERY_README_PATH.is_file()
               else "# Week 46 交付包\n\n"
                    "本包由 probes/export_week46_results.py 生成；交付说明见 "
                    "reports/week46_delivery_readme.md。\n")

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
        raise SystemExit("week46 export already exists; pass --overwrite")
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
        "schema": "week46_delivery/summary@1",
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
            "还原轴候选族一律同层（r2SCAN-3c）自比；与 xTB/GFN2 的任何对比只作层级伪影对照列，不进判据；"
            "D2 的 r2SCAN-3c 版本与 D3（ddCOSMO 溶剂化垂直 EA）需新 ORCA 单点，转下周期。",
            "Lane B 计算系列（含门禁后 xTB 层）一律 rejected_computed_only，介电锚点 rejected_criterion_mismatch，"
            "离盘参照 not_available_on_disk；n_anchors = 0 是侦察结论，不是「源不存在」。",
            "主判据按 H46a2 不执行、降级为「不可判定 + Lane C 功效下限」，与 W33 ORCA 层先例同规格登记，不算失败；"
            "「不可判定」与功效下限必须同报。",
            "tau_b 方向性读数（GFN2 合法气相 n = 48：D0-D1 0.7394 / D0-D2 -0.3794 / D1-D2 -0.4486）只作机制读法，"
            "不得当作候选族已重定义或门禁后下降的「无效」证据。",
            "任何修数未授权（dipole_transfer_v1 维持 registered_not_authorized）；不改 v2 论文线与 _v2_* 冻结件，改稿只落 v3。",
            "本包不携带任何第三方数据集内容（含扩展层 CSV、QM9 CSV、Batt-P30K 与 PubChemQC 衍生层）；第三方件按 data/ 路径 + sha256/行数复现，许可与署名见 reports/decisions_log.md。",
        ],
    }
    write_json_stable(week_root / "week46_summary.json", summary)
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
