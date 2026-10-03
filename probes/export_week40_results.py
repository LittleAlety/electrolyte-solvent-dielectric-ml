"""Export the Week 40 deliverables.

Week 40 folds four registered items into one delivery: the three criteria reforms that
W37/W38 had registered but never executed (W40-A), the remaining timestamped writers
migrated to the stable writer (W40-B), the Onsager domain rule refinement with dual-mu
readouts (W40-C), and the orbital-channel external control layer plus the PubChemQC
feasibility verdict (W40-D).  No main-scoreboard shot is taken (cumulative stays at 19).

  * W40-A re-reads existing artifacts only.  The budget inversion gives alpha* = 0.06 at
    tau=30 (10 recommends holding precision >= 0.90); tau=15 inverts to nothing and is a
    registered negative.  The zero-hit absolute gate |delta eps| >= 30 is replaced by a
    self-normalised decile ratio (0.6518, p = 0.000) plus a fingerprint blind-spot count
    (26 pairs, 4 of them with |delta eps| >= 5).  The absolute 0.08 scale gate is replaced
    by the parametric ratio R2 spread / AUC30 spread on five clean ladders
    (21.04 / 13.71 / 8.09 / 4.18 / 7.27), all with AUC30 spread < 0.02.
  * W40-B migrates the remaining tracked summaries onto write_json_stable so a replay no
    longer dirties the worktree through generated_at_utc / elapsed_seconds (AF-12 family).
  * W40-C refines the Kirkwood-Onsager domain rule from the inherited RDKit Lipinski donor
    definition to an explicit ionisable-proton definition, and reports the dipole readout
    with both mu sources (ours and QM9).
  * W40-D wires the QM9 homo/lumo/gap layer into the orbital channel as an external control
    layer and records the PubChemQC single-shard feasibility verdict honestly.

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

WEEK = "week40"

FROZEN_RED_LINES = {
    "paper/paper_zh_draft_v2.md":
        "228003f73db55c57cf735b77bfff0eb84ca13b6c64bbc40b53559cb7d2d3da35",
    "paper/_v2_body_b.md":
        "e1d5fb38e71cd1336bbdc8caba3b5b4c57822072c84cbc8443268fdb2650751d",
    "paper/_v2_appendix.md":
        "28a1c30ae82c33e4ccaccf1bae15d5085446de6918aa7d042ed3c4fbd7642304",
    "paper/_v2_concl.md":
        "72b0037de63c764b5699620cdfcae147fbe48605adfab657dd36a292ba5ef926",
    "paper/_v2_disc_extra.md":
        "5916a27e58233161021640e75647a3ff6ff38089bb8935763298ca2ac6ac2257",
    "paper/build_paper_v2.py":
        "043f7555e76c4a9a97acef861dd2de7cf67ea040c492ba16378b1295f114bf85",
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
    "w40_criteria_reform": {
        "title": ("W40-A 后验读数：三条判据改法（反解预算 / 相对与盲区 / 比值判据）"
                  "（14 判据含 1 条已登记判否；不占 shot）"),
        "probe": "probes/w40_criteria_reform.py",
        "prereg": None,
        "summary": "probes/artifacts/w40_criteria_reform_summary.json",
        "report": "reports/w40_criteria_reform.md",
        "tests": ("tests/test_w40_criteria_reform.py",),
        "artifacts": (
            "probes/artifacts/w40_conformal_inversion.csv",
            "probes/artifacts/w40_similarity_bins.csv",
            "probes/artifacts/w40_ladder_ratio.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w40_timestamp_migration": {
        "title": ("W40-B 治理件：剩余带时间戳跟踪件迁到稳定写入（重跑不脏树；不占 shot）"),
        "probe": "probes/w40_timestamp_migration.py",
        "prereg": None,
        "summary": "probes/artifacts/w40_timestamp_migration_summary.json",
        "report": "reports/w40_timestamp_migration.md",
        "tests": ("tests/test_w40_timestamp_migration.py",),
        "artifacts": ("probes/artifacts/w40_timestamp_inventory.csv",),
        "produces_reading": False,
        "promoted": False,
    },
    "w40_onsager_domain": {
        "title": ("W40-C 后验读数：Onsager 域规则精化（显式可给体质子）与双 μ 读数（不占 shot）"),
        "probe": "probes/w40_onsager_domain.py",
        "prereg": None,
        "summary": "probes/artifacts/w40_onsager_domain_summary.json",
        "report": "reports/w40_onsager_domain.md",
        "tests": ("tests/test_w40_onsager_domain.py",),
        "artifacts": (
            "probes/artifacts/w40_onsager_domain_compounds.csv",
            "probes/artifacts/w40_onsager_domain_summary.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w40_orbital_external": {
        "title": ("W40-D 后验读数：轨道通道外部对照层（QM9）与 PubChemQC 可行性登记（不占 shot）"),
        "probe": "probes/w40_orbital_external.py",
        "prereg": None,
        "summary": "probes/artifacts/w40_orbital_external_summary.json",
        "report": "reports/w40_orbital_external.md",
        "tests": ("tests/test_w40_orbital_external.py",),
        "artifacts": (
            "probes/artifacts/w40_orbital_external_control.csv",
            "probes/artifacts/w40_orbital_channels_update.csv",
        ),
        "produces_reading": False,
        "promoted": False,
    },
}
LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week40_project_charter.md", "week40_project_charter.md"),
    ("reports/week40_delivery_readme.md", "week40_delivery_readme.md"),
    ("reports/work_log_week37_to_week40.md", "work_log_week37_to_week40.md"),
    ("probes/export_week39_results.py", "export_week39_results.py"),
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
}

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w40_criteria_reform.png",
    "probes/artifacts/w40_onsager_domain.png",
    "probes/artifacts/w40_orbital_external.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/check_paper_artifact_consistency.py",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w40_criteria_reform.py "
        "tests/test_w40_timestamp_migration.py tests/test_w40_onsager_domain.py "
        "tests/test_w40_orbital_external.py tests/test_w40_timestamp_migration.py "
        "tests/test_w38_data_recon.py tests/test_w37_gate_admission_export.py "
        "-q -p no:cacheprovider"
    ),
)
DELIVERY_README_PATH = REPOSITORY_ROOT / "reports/week40_delivery_readme.md"
README_TEXT = (DELIVERY_README_PATH.read_text(encoding="utf-8")
               if DELIVERY_README_PATH.is_file()
               else "# Week 40 交付包\n\n"
                    "本包由 probes/export_week40_results.py 生成；交付说明见 "
                    "reports/week40_delivery_readme.md。\n")

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
        "schema": "week40_delivery/summary@1",
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
                                      "四条 lane 全是后验或治理件：只读盘上既有产物与名册，"
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
            "四条 lane 全部后验或治理：0 shot（累计仍 19）、不改 METRIC_NAMES、不新增特征列、缺行不插补、不动四个冻结读数。",
            "W40-A 只换判据重读盘上既有产物；它不重拟合任何主记分牌臂，也不因此把 0.586 变成新头条。",
            "比值判据的五个阶梯必须同构：W28 只取 grid_fixed_* 网格臂，安慰剂臂与换表示臂已剔除（不剔除会把 AUC30 极差从 0.0056 抬到 0.5438，把比值压到 1.29 造成假判否）。",
            "反解预算给出的是**存在性**：alpha* = 0.06 只说明在该预算下五个重复、化合物级切分上的合并读数能守住 0.90，不是对未见化合物的承诺；tau=15 上反解为空已登记为判否。",
            "QM9 只作**外部对照/审计层**：它的 gap / dipole 数值不写进任何标签池或特征列；两个层级只能谈排序与标定，不能直接互换。",
            "偶极审计里 **QM9 的构象不保证是全局最小**，柔性分子的差距可能是它这一侧的问题；只有刚性子集能定责到某一侧。约 0.39 D 的系统偏置在查清来源之前**不修数、不插补**。",
            "Onsager 域定义是**机械规则**（显式可给体质子），不按 ε 大小挑样本；g_rel 是无量纲相对量，只可做域间比较，不得与文献 g 绝对值对照。",
            "PubChemQC 的可行性结论按实测登记：若最小分片仍超出本机可承受体积，就写「受阻」并给出最小可行替代，不伪造已下载。",
            "名册分母是 **241 行**（data/processed/dielectric_physical_features_v03.csv）；既有报告里的 246 / 247 行属 dielectric_v03.csv 口径，两者不得混引。",
            "本包**不携带任何第三方数据集内容**（含 QM9 CSV 与 Batt-P30K）；第三方件按 data/external/ 的路径 + sha256 复现，许可与署名见 reports/decisions_log.md。",
        ],
    }
    write_json(week_root / "week40_summary.json", summary)
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
