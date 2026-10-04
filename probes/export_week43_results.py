"""Export the Week 43 deliverables.

Week 43 is a read-only governance-and-quantification week.  It turns the two items W42
registered at close-out into machine-checkable artifacts and adds two new registrations.
No main-scoreboard shot is taken (cumulative stays at 19).

  * W43-A decomposes the orbital-layer residual on the 5117-row expanded layer: the
    xTB-Batt pair is lifted from 73 to 4668 rows (rho 0.3280 -> 0.5985), the same-method
    geometry shift keeps the ranking (rho 0.9916) but shifts the level (MAE 0.1599 eV),
    and the near_same_level basis residual covers 0.6893 within |d| <= 0.2 eV.
  * W43-B preregisters the dipole-correction protocol dipole_transfer_v1 with status
    registered_not_authorized and measures its offline impact on the W40-C domain table
    (domain ratio 2.5817 -> 2.4696..3.1726, |delta| <= 1.0); no label is rewritten.
  * W43-C scores every orbital layer for use as a read-only ranking prior: PubChemQC is
    admitted, QM9 and xTB defer, Batt is rejected as the target layer.
  * W43-D guards the repo ledger: 337 JSON files scanned, registered negatives stable,
    zero frozen-reading violations, shot count monotone and capped at 19.

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

WEEK = "week43"

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "frozen_single_representation_endpoint": 0.5861142332208197,
    "frozen_promoted_arm_w20_4": 0.6216672295270079,
}

LANES = {
    "w43_layer_residual": {
        "title": "W43-A 计算件：层级残差分解与适用域条款（15 判据全成立；不占 shot）",
        "probe": "probes/w43_layer_residual.py",
        "prereg": "probes/w43_protocol_prereg.json",
        "summary": "probes/artifacts/w43_layer_residual_summary.json",
        "report": "reports/w43_layer_residual.md",
        "tests": ("tests/test_w43_layer_residual.py",),
        "artifacts": (
            "probes/artifacts/w43_layer_residual_pairs.csv",
            "probes/artifacts/w43_geometry_residual.csv",
            "probes/artifacts/w43_basis_residual.csv",
            "probes/artifacts/w43_residual_descriptors.csv",
            "probes/artifacts/w43_applicability_clause.json",
            "probes/artifacts/w43_layer_residual.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w43_dipole_protocol": {
        "title": "W43-B 治理件：偶极校正协议预注册 + 离线影响评估（12 判据全成立；不占 shot）",
        "probe": "probes/w43_dipole_protocol.py",
        "prereg": "probes/w43_protocol_prereg.json",
        "summary": "probes/artifacts/w43_dipole_protocol_summary.json",
        "report": "reports/w43_dipole_protocol.md",
        "tests": ("tests/test_w43_dipole_protocol.py",),
        "artifacts": (
            "probes/artifacts/w43_dipole_protocol.json",
            "probes/artifacts/w43_dipole_impact.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w43_prior_admission": {
        "title": "W43-C 治理件：外部层当排序先验的准入规则（10 判据全成立；不占 shot）",
        "probe": "probes/w43_prior_admission.py",
        "prereg": "probes/w43_protocol_prereg.json",
        "summary": "probes/artifacts/w43_prior_admission_summary.json",
        "report": "reports/w43_prior_admission.md",
        "tests": ("tests/test_w43_prior_admission.py",),
        "artifacts": (
            "probes/artifacts/w43_prior_admission.csv",
            "probes/artifacts/w43_prior_admission.json",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w43_governance_ledger": {
        "title": "W43-D 治理件：仓库级治理台账守卫（8 判据全成立；不占 shot）",
        "probe": "probes/w43_governance_ledger.py",
        "prereg": "probes/w43_protocol_prereg.json",
        "summary": "probes/artifacts/w43_governance_ledger_summary.json",
        "report": "reports/w43_governance_ledger.md",
        "tests": ("tests/test_w43_governance_ledger.py",),
        "artifacts": (
            "probes/artifacts/w43_governance_ledger.csv",
            "probes/artifacts/w43_governance_ledger.json",
        ),
        "produces_reading": False,
        "promoted": False,
    },
}
LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week43_project_charter.md", "week43_project_charter.md"),
    ("reports/week43_delivery_readme.md", "week43_delivery_readme.md"),
    ("reports/work_log_week43.md", "work_log_week43.md"),
    ("probes/w43_protocol_prereg.json", "w43_protocol_prereg.json"),
    ("probes/w43_common.py", "w43_common.py"),
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
FIGURES: tuple[str, ...] = ("probes/artifacts/w43_layer_residual.png",)
VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/check_paper_artifact_consistency.py",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w43_layer_residual.py "
        "tests/test_w43_dipole_protocol.py tests/test_w43_prior_admission.py "
        "tests/test_w43_governance_ledger.py tests/test_w38_data_recon.py "
        "tests/test_w37_gate_admission_export.py -q -p no:cacheprovider"
    ),
)
DELIVERY_README_PATH = REPOSITORY_ROOT / "reports/week43_delivery_readme.md"
README_TEXT = (DELIVERY_README_PATH.read_text(encoding="utf-8")
               if DELIVERY_README_PATH.is_file()
               else "# Week 43 交付包\n\n"
                    "本包由 probes/export_week43_results.py 生成；交付说明见 "
                    "reports/week43_delivery_readme.md。\n")

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
        "schema": "week43_delivery/summary@1",
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
                                      "四条 lane 全是只读离线统计与治理件：不拟合主记分牌臂、"
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
            "名册 73 行上的 rho(xTB,Batt)=0.3280 是悲观尾，不是层级真值；扩到 4668 行是 0.5985。",
            "几何残留保序（rho 0.9916）但平移（MAE 0.1599 eV）；near_same_level 基组残留 |d|<=0.2 eV 只覆盖 0.6893，只能当带容差的替换上界，strict same_level 计数仍为 0。",
            "偶极校正协议 dipole_transfer_v1 只有 registered_not_authorized 状态：LOO 偏置 CI 不含 0（偏置真实），但修正未授权，任何校正后偶极不得入标签或特征列。",
            "层准入的 admit 只表示可作只读排序先验；Batt 是标签目标，恒 reject。",
            "治理台账守卫生成的 w43_governance_ledger.csv 是逐文件审计台账；四个不变式须逐轮重跑。",
            "本包不携带任何第三方数据集内容（含扩展层 CSV、QM9 CSV、Batt-P30K 与 PubChemQC 衍生层）；第三方件按 data/ 路径 + sha256/行数复现，许可与署名见 reports/decisions_log.md。",
        ],
    }
    write_json(week_root / "week43_summary.json", summary)
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
