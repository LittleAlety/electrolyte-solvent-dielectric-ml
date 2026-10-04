"""Export the Week 42 deliverables.

Week 42 is a computation-heavy, read-only week.  The third external orbital layer
(PubChemQC, B3LYP/6-31G*//PM6 gas, CC BY 4.0) joins the W41 three-layer network and four
lanes run offline statistics on the frozen 241-row roster.  No main-scoreboard shot is
taken (cumulative stays at 19).

  * W42-A builds the four-layer orbital transfer network: coverage 237/103/205/73, a
    four-way intersection of 48, all 15 intersections, six pairwise rank transfers with
    bootstrap CIs and permutation nulls, and the triangle non-transitivity closure.
    QM9 and PubChemQC are declared near_same_level; strict same_level stays 0.
  * W42-B bounds the xTB -> Batt proxy with isotonic regression: Spearman 0.3280 ->
    in-sample 0.5461 / 5-fold CV 0.4150, CV R2 0.2225, median-split AUC 0.6922 -> CV
    0.7305, proxy fidelity ratio 0.3704.
  * W42-C decomposes the dipole offset across our xTB, QM9 and PubChemQC sources:
    QM9-PubChemQC bias -0.0341 D (CI covers 0) versus our-QM9 +0.3945 D and
    our-PubChemQC +0.5130 D, which localises the ~0.4 D offset to the method layer.
  * W42-D refits the sampling law sd(N)=s0*sqrt(1/N-1/N_pop) on six layer pairs
    (max rmse 0.0084, Spearman(s0, 1-tau) 0.9429) and gives the domain ratio
    2.5817133417 a paired bootstrap CI [2.1220, 3.2271] and permutation p 0.0005.

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

WEEK = "week42"

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "frozen_single_representation_endpoint": 0.5861142332208197,
    "frozen_promoted_arm_w20_4": 0.6216672295270079,
}

LANES = {
    "w42_orbital_transfer_network": {
        "title": "W42-A 计算件：四层轨道迁移网络与非传递闭合（13 判据全成立；不占 shot）",
        "probe": "probes/w42_orbital_transfer_network.py",
        "prereg": "probes/w42_registry_transfer_prereg.json",
        "summary": "probes/artifacts/w42_orbital_transfer_network_summary.json",
        "report": "reports/w42_orbital_transfer_network.md",
        "tests": ("tests/test_w42_orbital_transfer_network.py",),
        "artifacts": (
            "probes/artifacts/w42_orbital_layer_registry.csv",
            "probes/artifacts/w42_orbital_intersections.csv",
            "probes/artifacts/w42_transfer_pairs.csv",
            "probes/artifacts/w42_transfer_triangles.csv",
            "probes/artifacts/w42_near_same_level.json",
            "probes/artifacts/w42_orbital_transfer_network.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w42_proxy_calibration": {
        "title": "W42-B 计算件：xTB→Batt isotonic 代理上界（10 判据全成立；不占 shot）",
        "probe": "probes/w42_proxy_calibration.py",
        "prereg": "probes/w42_registry_transfer_prereg.json",
        "summary": "probes/artifacts/w42_proxy_calibration_summary.json",
        "report": "reports/w42_proxy_calibration.md",
        "tests": ("tests/test_w42_proxy_calibration.py",),
        "artifacts": (
            "probes/artifacts/w42_proxy_calibration.csv",
            "probes/artifacts/w42_isotonic_curve.csv",
            "probes/artifacts/w42_proxy_calibration.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w42_dipole_sources": {
        "title": "W42-C 计算件：偶极三源回归分解与 Bland–Altman（11 判据全成立；不占 shot）",
        "probe": "probes/w42_dipole_sources.py",
        "prereg": "probes/w42_registry_transfer_prereg.json",
        "summary": "probes/artifacts/w42_dipole_sources_summary.json",
        "report": "reports/w42_dipole_sources.md",
        "tests": ("tests/test_w42_dipole_sources.py",),
        "artifacts": (
            "probes/artifacts/w42_dipole_sources.csv",
            "probes/artifacts/w42_bland_altman.csv",
            "probes/artifacts/w42_dipole_attribution.json",
            "probes/artifacts/w42_dipole_sources.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w42_sampling_law": {
        "title": "W42-D 计算件：四层轨道抽样律 + 域比 bootstrap/置换（11 判据全成立；不占 shot）",
        "probe": "probes/w42_sampling_law.py",
        "prereg": "probes/w42_registry_transfer_prereg.json",
        "summary": "probes/artifacts/w42_sampling_law_summary.json",
        "report": "reports/w42_sampling_law.md",
        "tests": ("tests/test_w42_sampling_law.py",),
        "artifacts": (
            "probes/artifacts/w42_sampling_law.csv",
            "probes/artifacts/w42_sampling_fits.csv",
            "probes/artifacts/w42_domain_bootstrap.csv",
            "probes/artifacts/w42_sampling_law.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
}
LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week42_project_charter.md", "week42_project_charter.md"),
    ("reports/week42_delivery_readme.md", "week42_delivery_readme.md"),
    ("reports/work_log_week42.md", "work_log_week42.md"),
    ("probes/w42_registry_transfer_prereg.json", "w42_registry_transfer_prereg.json"),
    ("probes/w42_common.py", "w42_common.py"),
    ("probes/export_week41_results.py", "export_week41_results.py"),
)
EXTERNAL_DELIVERABLES = {
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
    "probes/artifacts/w42_orbital_transfer_network.png",
    "probes/artifacts/w42_proxy_calibration.png",
    "probes/artifacts/w42_dipole_sources.png",
    "probes/artifacts/w42_sampling_law.png",
)
VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/check_paper_artifact_consistency.py",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w42_orbital_transfer_network.py "
        "tests/test_w42_proxy_calibration.py tests/test_w42_dipole_sources.py "
        "tests/test_w42_sampling_law.py tests/test_w38_data_recon.py "
        "tests/test_w37_gate_admission_export.py -q -p no:cacheprovider"
    ),
)
DELIVERY_README_PATH = REPOSITORY_ROOT / "reports/week42_delivery_readme.md"
README_TEXT = (DELIVERY_README_PATH.read_text(encoding="utf-8")
               if DELIVERY_README_PATH.is_file()
               else "# Week 42 交付包\n\n"
                    "本包由 probes/export_week42_results.py 生成；交付说明见 "
                    "reports/week42_delivery_readme.md。\n")

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
    registered = _registered_negatives()
    unregistered = sorted(set(failed) - set(registered))
    summary = {
        "schema": "week42_delivery/summary@1",
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
                                      "四条 lane 全是只读离线计算：只读盘上既有产物与名册，"
                                      "不拟合主记分牌臂、不新增特征列、不改 METRIC_NAMES。"},
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
            "四条 lane 全部只读计算：0 shot（累计仍 19）、不改 METRIC_NAMES、不新增特征列、缺行不插补、不动四个冻结读数。",
            "QM9 与 PubChemQC 只判 near_same_level（同泛函 B3LYP + 同相气相，基组 6-31G(2df,p) vs 6-31G*、几何 B3LYP vs PM6 不同）；strict same_level 源数仍为 0，不得当同层级互换使用。",
            "isotonic 样本内抬升来自并列归并（单调变换在无并列时不改 Spearman），引用必须用 5 折 CV 值；校正值不得当标签、不得入特征列。",
            "偶极 ~0.4 D 偏置已定位到方法层（xTB vs B3LYP），但本轮只归因、不修数、不插补；更正本身要单独预注册。",
            "抽样律与域比是相关读数不是因果；g_rel 只可域间比较，不得与文献 g 绝对值对照；s0 不是通道常数而是排序保真度的函数。",
            "名册分母是 241 行（data/processed/dielectric_physical_features_v03.csv）；四层各有缺行，照实登记不插补。",
            "本包不携带任何第三方数据集内容（含 QM9 CSV、Batt-P30K 与 PubChemQC 衍生层）；第三方件按 data/ 路径 + sha256 复现，许可与署名见 reports/decisions_log.md。",
        ],
    }
    write_json(week_root / "week42_summary.json", summary)
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
