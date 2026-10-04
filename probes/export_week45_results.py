"""Export the Week 45 deliverables.

Week 45 is a read-only computation and governance-rerun week.  It audits the
calibration columns that W43 left behind, stratifies the 4668-row xTB-Batt layer,
attributes the ~0.39 D dipole bias across strata, and re-runs the three W44
governance guards as a snapshot.  No main-scoreboard shot is taken (cumulative
stays at 19).

  * W45-A audits the expanded layer's calib_homo_eV / calib_lumo_eV columns: the
    calibration is an exact in-sample affine map of homo_gfn2_eV (max residual
    1.8e-15), identical to the homo_gfn2 -> homo_batt OLS (slope/intercept delta
    <= 4.4e-16), so it only shifts the level (MAE 1.2066 -> 0.3032 eV) and leaves
    the rank order untouched (delta rho = 0.0).  calib_lumo_eV is empty on all
    4668 paired rows, registered as a known boundary.
  * W45-B stratifies the 4668-row xTB-Batt layer: the overall rho reproduces the
    W43 anchor 0.5984785837315431 bit-for-bit, the tiers are homogeneous
    (0.5974 / 0.5280 / 0.5130), but the heavy-atom bins degrade monotonically
    (0.8107 for 5-12 atoms -> 0.4810 for 18-40), and the robust heavy-tail
    fraction (|z|>3.5 on the de-medianed scale) is 0.1165.
  * W45-C attributes the dipole bias: on the 103-row overlap the mean bias is
    +0.39451165048543685 D, reproducing W42-C bit-for-bit; the dipole terciles
    put the median bias at 0.0598 / 0.4817 / 0.5207 D, so the bias grows with
    dipole magnitude (rank corr 0.4775) rather than with molecule size (0.0234).
  * W45-D re-runs the W44-A/B/D guards: the gate refuses 3 negative controls and
    admits PubChemQC, zero undeclared prior uses; acceptance scans 41 weeks with
    zero failures and the last five weeks all passing; the AST static guard scans
    364 files with zero mutations / frozen-reading writes / unregistered
    promotions; the ledger keeps the 9 registered negatives, zero out-of-canon
    frozen readings and the cumulative shot cap 19.

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
from probes.export_week41_results import FROZEN_RED_LINES

WEEK = "week45"

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "frozen_single_representation_endpoint": 0.5861142332208197,
    "frozen_promoted_arm_w20_4": 0.6216672295270079,
}

LANES = {
    "w45_calibration_audit": {
        "title": "W45-A 计算件：扩展层标定列的保真与泄漏审计（10 判据全成立；不占 shot）",
        "probe": "probes/w45_calibration_audit.py",
        "prereg": "probes/w45_compute_prereg.json",
        "summary": "probes/artifacts/w45_calibration_audit_summary.json",
        "report": "reports/w45_calibration_audit.md",
        "tests": ("tests/test_w45_calibration_audit.py",),
        "artifacts": (
            "probes/artifacts/w45_calibration_audit.csv",
            "probes/artifacts/w45_calibration_audit.json",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w45_stratified_residual": {
        "title": "W45-B 计算件：4668 行 xTB-Batt 的分层残差与稳健离群（10 判据全成立；不占 shot）",
        "probe": "probes/w45_stratified_residual.py",
        "prereg": "probes/w45_compute_prereg.json",
        "summary": "probes/artifacts/w45_stratified_residual_summary.json",
        "report": "reports/w45_stratified_residual.md",
        "tests": ("tests/test_w45_stratified_residual.py",),
        "artifacts": (
            "probes/artifacts/w45_stratified_residual.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w45_dipole_strata": {
        "title": "W45-C 计算件：偶极偏置的分层归因（10 判据全成立；不占 shot）",
        "probe": "probes/w45_dipole_strata.py",
        "prereg": "probes/w45_compute_prereg.json",
        "summary": "probes/artifacts/w45_dipole_strata_summary.json",
        "report": "reports/w45_dipole_strata.md",
        "tests": ("tests/test_w45_dipole_strata.py",),
        "artifacts": (
            "probes/artifacts/w45_dipole_strata.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w45_governance_rerun": {
        "title": "W45-D 治理件：三条守卫 + 台账的本轮复跑快照（7 判据全成立；不占 shot）",
        "probe": "probes/w45_governance_rerun.py",
        "prereg": "probes/w45_compute_prereg.json",
        "summary": "probes/artifacts/w45_governance_rerun_summary.json",
        "report": "reports/w45_governance_rerun.md",
        "tests": ("tests/test_w45_governance_rerun.py",),
        "artifacts": (
            "probes/artifacts/w45_governance_rerun.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
}
LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week45_project_charter.md", "week45_project_charter.md"),
    ("reports/week45_delivery_readme.md", "week45_delivery_readme.md"),
    ("reports/work_log_week45.md", "work_log_week45.md"),
    ("probes/w45_compute_prereg.json", "w45_compute_prereg.json"),
    ("probes/w45_common.py", "w45_common.py"),
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
    "probes/artifacts/w45_stratified_residual.png",
    "probes/artifacts/w45_dipole_strata.png",
)
VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/check_paper_artifact_consistency.py",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w45_calibration_audit.py "
        "tests/test_w45_stratified_residual.py tests/test_w45_dipole_strata.py "
        "tests/test_w45_governance_rerun.py tests/test_w38_data_recon.py "
        "tests/test_w37_gate_admission_export.py -q -p no:cacheprovider"
    ),
)
DELIVERY_README_PATH = REPOSITORY_ROOT / "reports/week45_delivery_readme.md"
README_TEXT = (DELIVERY_README_PATH.read_text(encoding="utf-8")
               if DELIVERY_README_PATH.is_file()
               else "# Week 45 交付包\n\n"
                    "本包由 probes/export_week45_results.py 生成；交付说明见 "
                    "reports/week45_delivery_readme.md。\n")

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
        raise SystemExit("week45 export already exists; pass --overwrite")
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
        "schema": "week45_delivery/summary@1",
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
                                      "四条 lane 全是只读计算与治理复跑：不拟合主记分牌臂、"
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
            "扩展层的 calib_homo_eV 是 homo_gfn2_eV 的 in-sample 仿射、与 homo_gfn2->homo_batt 的 OLS 逐位同映射，只补电平不补序（delta rho = 0.0）；"
            "calib_lumo_eV 在 4668 行上全空；该列不得当独立层 / 同层级源 / 标签替换。",
            "4668 行的 rank 一致随分子变大单调退化（重原子分箱 rho 0.8107 -> 0.7315 -> 0.4810）；任何 xTB->Batt 代理只能声明小分子域。",
            "偶极偏置随偶极幅度增长（三分位中位 0.0598 / 0.4817 / 0.5207 D，vs 幅度秩相关 0.4775，vs 重原子数仅 0.0234）；"
            "这支持 affine 优先于 shift，但修数仍未授权、任何校正后偶极不得入标签或特征列。",
            "三条治理守卫在本轮复跑只作读数、不写回任何既有 summary；早期轮次缺字段记为 not_declared，不算 fail。",
            "本包不携带任何第三方数据集内容（含扩展层 CSV、QM9 CSV、Batt-P30K 与 PubChemQC 衍生层）；第三方件按 data/ 路径 + sha256/行数复现，许可与署名见 reports/decisions_log.md。",
        ],
    }
    write_json(week_root / "week45_summary.json", summary)
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
