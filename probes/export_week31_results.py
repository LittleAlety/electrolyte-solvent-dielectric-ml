"""Export the Week 31 deliverables.

Week 31 answers the parent paper (v6) directly.  The parent paper rewrote "can a cheap
proxy be used for screening?" as a question about ranking stability and closed with
three conclusions on the electronic-structure level, plus a stated limitation: its core
set is only eighteen molecules, so the sampling standard deviation of tau_b on a
ten-molecule subset is about 0.126.

Lane A (post hoc, no shot) asks whether the same law survives one level down.  Inside
one molecular representation and one fold split, moving only hyperparameters moves
R-squared by 8.1x to 21.0x more than it moves AUC(eps>30); changing the representation
family moves both.  The independent check is quantitative: this repository's sampling
law sd(N) = s0 * sqrt(1/N - 1/N_pop), fitted on six measured resampling curves from a
246-compound census, predicts a median of 0.1345 at N = 10 against the parent paper's
own 0.126 -- a 6.7 per cent gap between two codebases and two compound pools.  The same
lane registers one correction: the value an earlier week stored as "the median of the
six" (0.1335681773982666) is the upper middle of the sorted six; the true median is
0.1222.

Lane B (shot 18) is the refined plan the parent paper's third conclusion points at.  If
expensive layers are skippable in the ranking sense, then model capacity is a layer too.
Within this repository the largest such reading is that depth 2 -> 4 buys only
+0.0045840097020970, and every existing reading stops at min_child_weight in {1, 5}.
Week 31 therefore sweeps the leaf penalty to 7 and 10 at depth 2 and adds depth 4 at
min_child_weight 7.  Two of the three new predictions fail, and that is the result: the
leaf penalty saturates past 5 (+0.000932 against a +0.002 bar) and the depth margin does
not shrink at a larger leaf penalty (+0.004584 versus +0.004641), so the two capacity
knobs are orthogonal rather than substitutable.

Shot ledger: delta 1, cumulative 18.  The four frozen readings keep their own
definitions: 0.4091179943351143, 0.4766400383507876, 0.5861142332208197,
0.6216672295270079.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    read_json,
    run_verifiers,
    sha256_file,
    write_json,
    write_sha256s,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEEK = "week31"

TOLERANCE = 1e-09

# The inputs the round reads and never writes.  A move here means a delivered reading no
# longer has the input it claims, so the export refuses to run.
FROZEN_RED_LINES = {
    "probes/artifacts/w24_3_sampling_law.csv":
        "8cd15a8e23d06809f06b75f1918a7529bdb30e33cc27b6391a446ada98c5cfcc",
    "probes/artifacts/w24_3_level_crosscheck.csv":
        "71dd995850080176595f3c554e7338f76714b0e622e57975409d25696a991ee0",
    "probes/artifacts/w28_dense_hyperparameters_repeats.csv":
        "3d4eaa370de493f37ece3a0a3fa74bc20face4f29f22ae14b96fb07afa5d4db9",
    "probes/artifacts/w29_dense_binning_repeats.csv":
        "050944a7be345873371a086ea9822dd66dec66d21c6b82f950c4dc3057a24961",
    "probes/artifacts/w30_combination_ladder_repeats.csv":
        "60a2cb25ff1b432935acd45fc0aaeb4ecc39c47c53cef292b8a6d8742ad63fe1",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w31_v6_bridge": {
        "title": (
            "W31-A 后验读数：母体论文 v6 的三条结论 × 本仓三层读数，"
            "并把 v6 自报的噪声地板 0.126（N=10）与本仓闭式互证（不占 shot）"
        ),
        "probe": "probes/w31_v6_bridge.py",
        "prereg": None,
        "summary": "probes/w31_v6_bridge.json",
        "report": "reports/w31_v6_bridge.md",
        "tests": ("tests/test_w31_v6_bridge.py",),
        "artifacts": (
            "probes/artifacts/w31_v6_bridge.csv",
            "probes/artifacts/w31_v6_bridge.png",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w31_capacity_exchange": {
        "title": (
            "W31：稠密块容量交换阶梯（叶惩罚 7 / 10 能否买回深度的边际），"
            "冻结主记分牌池五种子 GroupKFold by InChIKey"
        ),
        "probe": "probes/w31_capacity_exchange.py",
        "prereg": "probes/w31_capacity_exchange_prereg.json",
        "summary": "probes/w31_capacity_exchange_summary.json",
        "report": "reports/w31_capacity_exchange.md",
        "tests": (
            "tests/test_w31_capacity_exchange.py",
            "tests/test_w30_combination_ladder.py",
        ),
        "artifacts": (
            "probes/artifacts/w31_capacity_exchange_repeats.csv",
            "probes/artifacts/w31_capacity_exchange.png",
        ),
        "produces_reading": True,
        "promoted": False,
    },
}

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("reports/week31_project_charter.md", "week31_project_charter.md"),
    ("reports/week31_delivery_readme.md", "week31_delivery_readme.md"),
    ("reports/w31_v6_bridge.md", "w31_v6_bridge.md"),
    ("reports/w31_capacity_exchange.md", "w31_capacity_exchange.md"),
    ("reports/week30_project_charter.md", "week30_project_charter.md"),
    ("reports/week30_delivery_readme.md", "week30_delivery_readme.md"),
    ("reports/week29_delivery_readme.md", "week29_delivery_readme.md"),
    ("paper/paper_zh_draft_v2.md", "paper_zh_draft_v2.md"),
    ("paper/make_paper_docx_template.py", "make_paper_docx_template.py"),
    ("probes/export_week30_results.py", "export_week30_results.py"),
    ("probes/export_week31_results.py", "export_week31_results.py"),
)

LANE_KEYS = tuple(LANES)

EXTERNAL_DELIVERABLES: tuple[tuple[str, str], ...] = ()

FIGURES: tuple[str, ...] = (
    "probes/artifacts/w31_v6_bridge.png",
    "probes/artifacts/w31_capacity_exchange.png",
)

VERIFIERS = (
    "scripts/verify_four_core_registry.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_w31_capacity_exchange.py "
        "tests/test_w31_v6_bridge.py tests/test_w30_combination_ladder.py "
        "-q -p no:cacheprovider"
    ),
)

README_TEXT = (REPOSITORY_ROOT / "reports/week31_delivery_readme.md").read_text(encoding="utf-8")
BRIDGE_SUMMARY_PATH = REPOSITORY_ROOT / "probes/w31_v6_bridge.json"
LADDER_SUMMARY_PATH = REPOSITORY_ROOT / "probes/w31_capacity_exchange_summary.json"


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
    bridge = read_json(BRIDGE_SUMMARY_PATH)
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
        "reading_lanes": reading_lanes,
        "promoted_lanes": promoted_lanes,
        "main_scoreboard_attempts_delta": 1,
        "cumulative_main_scoreboard_attempts": 18,
        "shots_by_lane": {"w31_v6_bridge": 0, "w31_capacity_exchange": 1},
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "external_deliverables": [destination for _, destination in EXTERNAL_DELIVERABLES],
        "figures": [Path(figure).name for figure in FIGURES],
        "v6_bridge": {
            "parent_paper_sd_tau_b_at_n10": bridge["v6_readings"]["sd_tau_b_at_n10"],
            "our_sd_at_n10_median": bridge["readings"][0]["ours_median"],
            "our_sd_at_n10_mean": bridge["readings"][0]["ours_mean"],
            "relative_gap": bridge["readings"][0]["relative_gap"],
            "layer_table": [
                {"layer": row["layer"], "family": row["family"],
                 "magnitude_range": row["magnitude_range"],
                 "order_range": row["order_range"],
                 "range_ratio": row.get("range_ratio")}
                for row in bridge["layer_table"]
            ],
            "correction": {
                "recorded_value": bridge["readings"][4]["recorded"],
                "true_median": bridge["readings"][4]["true_median"],
                "true_mean": bridge["readings"][4]["true_mean"],
                "upper_middle": bridge["readings"][4]["upper_middle"],
            },
        },
        "headline_readings": {
            "anchor_seed42": readings["anchor_seed42"],
            "anchor_seed42_gap": readings["anchor_seed42_gap"],
            "frozen_cross_seed": readings["frozen_mean"],
            "frozen_cross_seed_gap": readings["frozen_gap"],
            "week20_4_registered_reproduced": readings["w20_mean"],
            "week20_4_gap": readings["w20_gap"],
            "week30_best_reproduced": readings["w30_best_mean"],
            "week30_best_gap": readings["w30_best_gap"],
            "best_new_arm": readings["best_new_label"],
            "best_new_cross_seed": readings["best_new_mean"],
            "best_new_delta_vs_week30": readings["best_new_delta_vs_w30"],
            "mcw_curve_at_depth2": readings["mcw_curve_d2"],
            "capacity_exchange_gain": readings["mcw_gain_at_d2"],
            "depth_margin_mcw5": readings["depth_margin_mcw5"],
            "depth_margin_mcw7": readings["depth_margin_mcw7"],
            "depth_margin_shrink": readings["depth_margin_shrink"],
            "global_best_arm": readings["global_best_label"],
            "global_best_cross_seed": readings["global_best_mean"],
            "ceiling_delta_vs_week20_4": readings["ceiling_delta"],
            "r2_spread": readings["r2_range"],
            "auc_gt30_spread": readings["auc30_range"],
            "ratio_r2_over_auc30": readings["range_ratio"],
            "gate_r2": 0.6,
        },
        "verdicts": {identifier: verdict["verdict"] for identifier, verdict in verdicts.items()},
        "verdicts_failed": failed,
        "files": sorted(copied),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "boundaries": [
            "W31 的池、评分掩码、训练掩码、分组切分器、表示与五种子集合全部取自冻结主记分牌；容量交换阶梯的六个档位只覆盖 max_depth / n_estimators / learning_rate / min_child_weight / max_bin / reg_lambda 六列声明键（subsample 0.8 / objective / tree_method / n_jobs / random_state 42 一律不动）。",
            "这是阶梯不是搜索：六个固定配置在同样的折上各拟合一次，没有任何选择，外层测试行只被预测、从未参与任何决定；因此不设安慰剂臂（没有选择器就没有可塌缩的对象）。",
            "容量交换阶梯带回三条复现锚，全部逐位命中（gap 恰好 0.0）：冻结档位 0.5861142332208197、W20-4 注册臂 0.6216672295270079、W30 最佳新组合 0.6170832198249109；seed 42 的冻结档位同时逐位复现 0.6080587938801277。",
            "**判否照实登记**：H31f（容量交换 +0.000932 对门 +0.002）与 H31g（深度边际收缩 -0.000057 对门 0）是**实质判否** —— 叶惩罚在 mcw = 5 之后饱和、深度边际不随叶惩罚收缩，两个容量旋钮正交而非可替代。H31h 是**判据设计缺陷**（序侧 AUC30 极差 0.008681 < 0.02 成立，量级侧 0.08 那个门是从更宽阶梯抄来的）；阈值不在原地改动，改法写进下一份预注册。",
            "`bin128_mcw7_d4` = 0.622389 名义上比 W20-4 注册臂高 +0.000722，但远小于种子间抖动、且落在预注册的 0.005 松弛带内 —— **不构成新纪录、不改冻结读数、不构成晋升**。",
            "W31-A 是**后验读数**：只读已提交的冻结产物与母体论文 v6 结语页上已发表的数字，**不占主记分牌 shot**，不得当作预注册结论引用；v6 侧数字一律引用不重算。",
            "该 lane 同时登记一条**口径更正**：0.1335681773982666 是六条 sd@N=12 排序后的上中位，不是六条的中位；真中位 0.1222、均值 0.1212。**不修改任何冻结产物**，只改正论文与 README 的口径描述。",
            "不新增量子化学、不装依赖、不联网；表示就是 13 列稠密物理块，一列不加、一列不减。缺行不插补、不丢弃评分行；折任务的 random_state 是固定常量 42。",
            "主记分牌 shot = 1（累计 18）；四个冻结读数未动。不引用任何 Reaxys 数值；THEMol（CC BY-NC 4.0）不入交付包。",
        ],
    }
    write_json(week_root / "week31_summary.json", summary)
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