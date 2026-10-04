"""Export the Week 41 deliverables.

Week 41 executes the four registered items that W40 left for the next preregistration
(README section 11, items 29-32) as four read-only governance lanes.  No main-scoreboard
shot is taken (cumulative stays at 19).

  * W41-A turns the ladder admission rule into a machine check: an arm counts only when
    its name matches the ladder's own admit_prefix, is not a placebo and not a
    representation swap, and its repeat set is complete.  The rule splits the 40 arms
    into 33 admitted and 7 excluded, and the five clean ladders reproduce the W40-A
    frozen ratios (21.04 / 13.71 / 8.09 / 4.18 / 7.27) with AUC30 spread <= 0.018851.
    The W28 full-pool counterfactual is 1.293416, below the robust gate of 4.0.
  * W41-B writes the domain-ratio dual-reading clause: any between-domain ratio must
    report the bias-uncorrected and the dipole-bias-corrected value.  The relative
    change is 0.205886 > 0.10, so only a direction-robust claim is allowed (H41b5 is a
    registered negative).
  * W41-C re-derives the exemption classes from source evidence: pinned bytes 16,
    append write 4, strict JSON 3, overlap 1 (pubchem_identity_layer.py), reverse leak 0.
    It also corrects the hand-written W40 grouping (append was 4, not 3).
  * W41-D declares the orbital levels and checks transitivity: xTB 237/241, QM9 103/241,
    Batt 73/241, triple intersection 48.  Ranking agreement does not chain (H41d8 is a
    registered negative); the same-level external-source count stays 0.

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

WEEK = "week41"

FROZEN_RED_LINES = {
    "paper/paper_zh_draft_v2.md":
        "c7bc66296e18cd6384760a3b49014800662800f5141124365fccf31fdaf1b50f",
    "paper/_v2_body_b.md":
        "e1d5fb38e71cd1336bbdc8caba3b5b4c57822072c84cbc8443268fdb2650751d",
    "paper/_v2_appendix.md":
        "2157331a9681d7dce41b43f5314babf31782e271911ba42e1d9a6fe27dc80983",
    "paper/_v2_concl.md":
        "7f98a38961ad91bb076239e1087c50f459d3580a6b8660d9d1f36ffe8a62e8fe",
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
    "w41_ladder_admission": {
        "title": ("W41-A 治理件：阶梯池准入规则（40 臂 = 33 准入 + 7 剔除）与五个比值复现"
                  "（9 判据全成立；不占 shot）"),
        "probe": "probes/w41_ladder_admission.py",
        "prereg": "probes/w41_governance_prereg.json",
        "summary": "probes/artifacts/w41_ladder_admission_summary.json",
        "report": "reports/w41_ladder_admission.md",
        "tests": ("tests/test_w41_ladder_admission.py",),
        "artifacts": (
            "probes/artifacts/w41_ladder_admission.csv",
            "probes/artifacts/w41_ladder_admission_summary.csv",
            "probes/artifacts/w41_ladder_admission.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w41_domain_ratio_robustness": {
        "title": ("W41-B 治理件：域比双读数稳健性条款（未校正 2.581713 / 校正后 3.113253）"
                  "（10 判据含 1 条已登记判否；不占 shot）"),
        "probe": "probes/w41_domain_ratio_robustness.py",
        "prereg": "probes/w41_governance_prereg.json",
        "summary": "probes/artifacts/w41_domain_ratio_robustness_summary.json",
        "report": "reports/w41_domain_ratio_robustness.md",
        "tests": ("tests/test_w41_domain_ratio_robustness.py",),
        "artifacts": (
            "probes/artifacts/w41_domain_ratio_robustness.csv",
            "probes/artifacts/w41_domain_ratio_clause.json",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w41_exemption_admission": {
        "title": ("W41-C 治理件：例外登记表三类准入（pinned 16 / append 4 / strict 3）"
                  "（10 判据全成立；不占 shot）"),
        "probe": "probes/w41_exemption_admission.py",
        "prereg": "probes/w41_governance_prereg.json",
        "summary": "probes/artifacts/w41_exemption_admission_summary.json",
        "report": "reports/w41_exemption_admission.md",
        "tests": ("tests/test_w41_exemption_admission.py",),
        "artifacts": (
            "probes/artifacts/w41_exemption_admission.csv",
            "probes/artifacts/w41_exemption_policy.json",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w41_orbital_level_declaration": {
        "title": ("W41-D 治理件：轨道通道层级声明与排序迁移不可传递（H41d8 已登记判否）"
                  "（11 判据含 1 条已登记判否；不占 shot）"),
        "probe": "probes/w41_orbital_level_declaration.py",
        "prereg": "probes/w41_governance_prereg.json",
        "summary": "probes/artifacts/w41_orbital_level_declaration_summary.json",
        "report": "reports/w41_orbital_level_declaration.md",
        "tests": ("tests/test_w41_orbital_level_declaration.py",),
        "artifacts": (
            "probes/artifacts/w41_orbital_level_registry.csv",
            "probes/artifacts/w41_orbital_pair_matrix.csv",
            "probes/artifacts/w41_orbital_batt_hits.csv",
            "probes/artifacts/w41_orbital_level_declaration.json",
            "probes/artifacts/w41_orbital_level_declaration.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
}
LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week41_project_charter.md", "week41_project_charter.md"),
    ("reports/week41_delivery_readme.md", "week41_delivery_readme.md"),
    ("reports/work_log_week41.md", "work_log_week41.md"),
    ("probes/w41_governance_prereg.json", "w41_governance_prereg.json"),
    ("probes/export_week40_results.py", "export_week40_results.py"),
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
}
FIGURES: tuple[str, ...] = (
    "probes/artifacts/w41_ladder_admission.png",
    "probes/artifacts/w41_orbital_level_declaration.png",
)
VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    "scripts/check_paper_artifact_consistency.py",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w41_ladder_admission.py "
        "tests/test_w41_domain_ratio_robustness.py tests/test_w41_exemption_admission.py "
        "tests/test_w41_orbital_level_declaration.py tests/test_w38_data_recon.py "
        "tests/test_w37_gate_admission_export.py -q -p no:cacheprovider"
    ),
)
DELIVERY_README_PATH = REPOSITORY_ROOT / "reports/week41_delivery_readme.md"
README_TEXT = (DELIVERY_README_PATH.read_text(encoding="utf-8")
               if DELIVERY_README_PATH.is_file()
               else "# Week 41 交付包\n\n"
                    "本包由 probes/export_week41_results.py 生成；交付说明见 "
                    "reports/week41_delivery_readme.md。\n")

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
        "schema": "week41_delivery/summary@1",
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
            "W41-A 的准入规则写死为「同一配置网格（admit_prefix）+ 剔除安慰剂（shuffled|placebo|random_target）+ 剔除换表示（morgan|fingerprint|embedding）+ 重复集完整」；W28 全池反事实比值 1.2934 落在稳健门 4.0 之下，不得把比值判据用到未过准入的池子上。",
            "W41-B 的双读数是硬条款：相对变化 0.205886 > 0.10 ⇒ 只能声明「方向稳健」，不得声明「量级稳健」；域间比是相关读数不是因果，g_rel 只可做域间比较，不得与文献 g 绝对值对照。",
            "W41-C 更正 W40 手写分组：append 计数是 4（非 3），真 pinned∩append 重叠是 probes/pubchem_identity_layer.py；例外登记不是豁免，这 22 个 owner 重跑仍会弄脏工作树，是保留代价，不计入迁移完成率。",
            "W41-D 三层两两都是 cross_level（泛函 / 基组 / 溶剂化至少差一项），同层级外部源数 = 0 ⇒ W40 登记的第 3 条仍未满足；QM9 只能作排序先验，其数值不入标签池或特征列。",
            "H41d8 在册判否的是「跨层排序先验可传递 / 可当作另一层代理」这条主张：同一 48 化合物上 min(ρ(xTB,QM9), ρ(QM9,Batt)) − ρ(xTB,Batt) = 0.2792 > 0.2。",
            "名册分母是 241 行（data/processed/dielectric_physical_features_v03.csv）；xTB gap 有 4 行缺失，照实登记不插补。",
            "本包不携带任何第三方数据集内容（含 QM9 CSV 与 Batt-P30K）；第三方件按 data/raw 或 data/external 的路径 + sha256 复现，许可与署名见 reports/decisions_log.md。",
        ],
    }
    write_json(week_root / "week41_summary.json", summary)
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
