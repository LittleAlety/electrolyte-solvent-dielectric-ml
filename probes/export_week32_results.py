"""Export the Week 32 deliverables.

Week 32 has two lanes.  Lane A (post hoc, no shot) moves the resampling law that
Week 24-3 measured on the permittivity channel -- sd(N) = s0 * sqrt(1/N - 1/N_pop) --
onto a harder object: "proxy versus label" instead of "level versus level", run once
across all four core channels (permittivity, viscosity, orbitals, redox).  The law
survives: the median fit residual is 0.0071 against a gate of 0.012, and s0 is not a
channel constant but a function of ranking fidelity (Spearman 0.81 between s0 and the
fidelity gap 1 - tau_b).  Each channel therefore gets its own noise floor and its own
minimum information budget.

Lane B (shot 19) is the next arm the Week 31 charter registered: the third capacity
face nobody had swept.  colsample_bytree had only been read at the frozen 0.8 and at
1.0 (both drops), and subsample had never moved from 0.8.  Nine fixed configurations
on the registered arm as base, zero selectors, four reproduction anchors hit bit for
bit.

Shot ledger: delta 1, cumulative 19.  The four frozen readings keep their own
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

WEEK = "week32"

FROZEN_RED_LINES = {
    "probes/artifacts/w24_3_sampling_law.csv":
        "8cd15a8e23d06809f06b75f1918a7529bdb30e33cc27b6391a446ada98c5cfcc",
    "probes/artifacts/w24_3_level_crosscheck.csv":
        "71dd995850080176595f3c554e7338f76714b0e622e57975409d25696a991ee0",
    "probes/artifacts/w31_capacity_exchange_repeats.csv":
        "3b1e77579f643c80f4ea0d2486432e5d47f459a7220e234dfdcc8ff9f9ecc68f",
    "data/processed/dielectric_representation_ablation_predictions.csv":
        "a8dee3c6b1bd31c979931f34b7e6f463614808e67c11bef81741917fce061a19",
    "data/processed/viscosity_baseline_predictions.csv":
        "55fe5d1f6575b2cd8c033a85bb8e793063f06471f39bc77e72cfb5a0a16a9604",
    "data/processed/l3_homo_lumo_cv_predictions.csv":
        "4ebba5565da7541f420cc0440e499ad5b2331df574d637ab14d754e88e4d8d70",
    "probes/artifacts/p4_redox_v2_predictions.csv":
        "ad529cfa18a50727baf33e3c96add1ba92af318f7d14b17c6a1fea360ad6d432",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w32_rank_stability": {
        "title": (
            "W32-A 后验读数：四通道 x 多代理的排序不稳定性抽样律，"
            "每个通道给出自己的噪声地板与最小信息预算（不占 shot）"
        ),
        "probe": "probes/w32_cross_channel_rank_stability.py",
        "prereg": None,
        "summary": "probes/artifacts/w32_rank_stability.json",
        "report": "reports/w32_rank_stability.md",
        "tests": ("tests/test_w32_rank_stability.py",),
        "artifacts": (
            "probes/artifacts/w32_rank_stability_series.csv",
            "probes/artifacts/w32_rank_stability_curves.csv",
            "probes/artifacts/w32_rank_stability.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w32_regularization_ladder": {
        "title": (
            "W32-B：稠密块正则化中间值阶梯（colsample_bytree 0.8/0.9/1.0；"
            "subsample 0.6/0.7/0.8/0.9/1.0），冻结主记分牌池五种子 GroupKFold"
        ),
        "probe": "probes/w32_regularization_ladder.py",
        "prereg": "probes/w32_regularization_ladder_prereg.json",
        "summary": "probes/w32_regularization_ladder_summary.json",
        "report": "reports/w32_regularization_ladder.md",
        "tests": (
            "tests/test_w32_regularization_ladder.py",
            "tests/test_w31_capacity_exchange.py",
        ),
        "artifacts": (
            "probes/artifacts/w32_regularization_ladder_repeats.csv",
            "probes/artifacts/w32_regularization_ladder.png",
        ),
        "produces_reading": True,
        "promoted": False,
    },
}

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week32_project_charter.md", "week32_project_charter.md"),
    ("reports/week32_delivery_readme.md", "week32_delivery_readme.md"),
    ("reports/w32_rank_stability.md", "w32_rank_stability.md"),
    ("reports/w32_regularization_ladder.md", "w32_regularization_ladder.md"),
    ("reports/week31_project_charter.md", "week31_project_charter.md"),
    ("reports/week31_delivery_readme.md", "week31_delivery_readme.md"),
    ("reports/w31_v6_bridge.md", "w31_v6_bridge.md"),
    ("reports/w31_capacity_exchange.md", "w31_capacity_exchange.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("paper/make_paper_docx_template.py", "make_paper_docx_template.py"),
    ("probes/export_week31_results.py", "export_week31_results.py"),
    ("probes/export_week32_results.py", "export_week32_results.py"),
    ("probes/w32_presentation_figures.py", "w32_presentation_figures.py"),
)

LANE_KEYS = tuple(LANES)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w32_rank_stability.png",
    "probes/artifacts/w32_regularization_ladder.png",
    "probes/artifacts/w32_fig_noise_floor.png",
    "probes/artifacts/w32_fig_fidelity_law.png",
    "probes/artifacts/w32_fig_milestones.png",
    "probes/artifacts/w32_fig_regularization_curves.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w32_rank_stability.py "
        "tests/test_w32_regularization_ladder.py tests/test_w31_capacity_exchange.py "
        "-q -p no:cacheprovider"
    ),
)

README_TEXT = (REPOSITORY_ROOT / "reports/week32_delivery_readme.md").read_text(encoding="utf-8")
RANK_SUMMARY_PATH = REPOSITORY_ROOT / "probes/artifacts/w32_rank_stability.json"
LADDER_SUMMARY_PATH = REPOSITORY_ROOT / "probes/w32_regularization_ladder_summary.json"


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
    if lane["prereg"]:
        declared.append(str(lane["prereg"]))
    if lane["summary"]:
        declared.append(str(lane["summary"]))
    prereg_block = None
    if lane["prereg"]:
        path = REPOSITORY_ROOT / str(lane["prereg"])
        payload = read_json(path)
        status = payload.get("status", payload.get("prereg_status"))
        prereg_block = {"path": str(lane["prereg"]), "sha256": sha256_file(path),
                        "status": status, "revision": payload.get("revision"),
                        "locked_before_run": status == "locked_before_run"}
    summary_path = REPOSITORY_ROOT / str(lane["summary"]) if lane["summary"] else None
    report_path = REPOSITORY_ROOT / str(lane["report"])
    return {"title": lane["title"], "probe": lane["probe"], "report": lane["report"],
            "report_sha256": sha256_file(report_path) if report_path.is_file() else None,
            "tests": list(lane["tests"]), "artifacts": list(lane["artifacts"]),
            "prereg": prereg_block, "summary_path": lane["summary"],
            "summary_sha256": (sha256_file(summary_path)
                               if summary_path and summary_path.is_file() else None),
            "declared_files": declared,
            "declared_files_missing": [item for item in declared
                                       if not (REPOSITORY_ROOT / item).is_file()],
            "produces_reading": lane["produces_reading"], "promoted": lane["promoted"]}


def _missing_lane_keys() -> tuple[str, ...]:
    return tuple(key for key in LANE_KEYS
                 if not (REPOSITORY_ROOT / str(LANES[key]["report"])).is_file())


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
    rank = read_json(RANK_SUMMARY_PATH)
    ladder = read_json(LADDER_SUMMARY_PATH)
    readings = ladder["readings"]
    verdicts = {verdict["id"]: verdict for verdict in ladder["verdicts"]}
    failed = sorted(identifier for identifier, verdict in verdicts.items()
                    if verdict["verdict"] != "成立")

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
        "promoted_lanes": promoted_lanes,
        "reading_lanes": reading_lanes,
        "shots_by_lane": {"w32_rank_stability": 0, "w32_regularization_ladder": 1},
        "main_scoreboard_attempts_delta": 1,
        "cumulative_main_scoreboard_attempts": 19,
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "rank_stability": {
            "channels": rank["channels"],
            "readings": {item["id"]: item for item in rank["readings"]},
            "series": len(rank["records"]),
            "draws_per_point": rank["draws_per_point"],
            "n_grid": rank["n_grid"],
            "reference_law": rank["reference_law"],
        },
        "headline_readings": {
            "anchor_seed42": readings["anchor_seed42"],
            "anchor_seed42_gap": readings["anchor_seed42_gap"],
            "frozen_cross_seed": readings["frozen_mean"],
            "frozen_cross_seed_gap": readings["frozen_gap"],
            "week20_4_registered_reproduced": readings["registered_mean"],
            "week20_4_gap": readings["registered_gap"],
            "week31_fixed_reproduced": readings["w31_fixed_mean"],
            "week31_fixed_gap": readings["w31_fixed_gap"],
            "colsample_curve": readings["colsample_curve"],
            "colsample_gap_09": readings["colsample_gap_09"],
            "colsample_gap_10": readings["colsample_gap_10"],
            "subsample_curve": readings["subsample_curve"],
            "subsample_best_label": readings["subsample_best_label"],
            "subsample_best_gain_vs_registered": readings["subsample_best_gain_vs_registered"],
            "best_new_arm": readings["best_new_label"],
            "best_new_cross_seed": readings["best_new_mean"],
            "global_best_arm": readings["global_best_label"],
            "global_best_cross_seed": readings["global_best_mean"],
            "ceiling_delta_vs_week20_4": readings["ceiling_delta"],
            "r2_spread": readings["r2_range"],
            "auc_gt30_spread": readings["auc_gt30_range"],
            "ratio_r2_over_auc30": readings["range_ratio"],
            "gate_r2": 0.6,
        },
        "verdicts": {identifier: verdict["verdict"] for identifier, verdict in verdicts.items()},
        "verdicts_failed": failed,
        "files": sorted(copied),
        "figures": list(FIGURES),
        "external_deliverables": {},
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "W32 的池、评分掩码、训练掩码、分组切分器、表示与五种子集合全部取自冻结主记分牌；正则化阶梯的九个档位只覆盖 max_depth / n_estimators / learning_rate / min_child_weight / colsample_bytree / subsample / max_bin / reg_lambda 八列声明键（objective / tree_method / n_jobs / random_state 42 一律不动）。",
            "这是阶梯不是搜索：九个固定配置在同样的折上各拟合一次，没有任何选择，外层测试行只被预测、从未参与任何决定；因此不设安慰剂臂。",
            "正则化阶梯带回四条复现锚（冻结档位 0.5861142332208197、W20-4 注册臂 0.6216672295270079、W31 固定最优 0.6223892738254433，以及 seed 42 的 0.6080587938801277），全部逐位命中。",
            "拟合路径直接复用 W31 的 evaluate_ladder（只替换模块级配置表与臂前缀），因此两轮的对照是同一条代码路径。",
            "W32-A 是**后验读数**：只读已冻结的逐分子预测表，不重新拟合主记分牌臂、不占 shot，不得当作预注册结论引用。",
            "W32-A 的评测单元随通道而定：介电 / 氧化还原按分子，轨道用出折预测均值，黏度按（分子 x 温度）行；逐序列登记在 _series.csv 的 unit / aggregation 列。",
            "主记分牌 shot = 1（累计 19）；四个冻结读数未动。不引用任何 Reaxys 数值；THEMol（CC BY-NC 4.0）不入交付包。",
            "论文 v2 的 N=12 噪声地板已按 W31-A/B5 口径更正为 0.122（六条中位；0.134 是上中位），附录 A 保留审计注记。",
        ],
    }
    write_json(week_root / "week32_summary.json", summary)
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