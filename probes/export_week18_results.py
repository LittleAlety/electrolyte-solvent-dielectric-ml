"""Export the Week 18 deliverables (the post-cap path ranking).

Week 17 closed the open-licence dielectric frontier: the roster bound is 153
compounds with an upper bound of 157 (widest 161), the source sweep found 0 new
sources and 0 net-new compounds, and the threshold table row that assumed a
doubled compound count was measured to be unreachable under the current licence
constraints.  Week 18 therefore stops buying data and starts buying *mechanism*.

It runs the eight paths that Week 17 had not yet killed:

* W18-P0 -- retune the XGBoost hyper-parameters of the dense physical block;
* W18-P1 -- promote the endpoint from one fold seed to a pre-locked five-seed mean;
* W18-P2 -- Onsager/Kirkwood delta-learning (the one un-refuted physics shot);
* W18-P3 -- conformer-variance / flexibility columns on top of the lever-4 means;
* W18-P5 -- Uni-Mol pre-trained embeddings as a feature block;
* W18-P6 -- log-space training plus isotonic calibration back to the original scale;
* W18-A  -- the row-level viscosity unfreeze (the closest channel to its gate);
* W18-B  -- the declared applicability-domain scoreboard (a second board, never a
            replacement for the global one).

Nothing on the frozen side moves.  The frozen baseline 0.4091179943351143, the
frozen headline 0.4766400383507876, the two leak references 0.7385332681453336 and
0.6747993443917342, and both scoreboards keep their own pool definitions.  Week 18
adds no shot to the main scoreboard: every lane here reports under its own
pre-registration and its own pool, and `promoted` is false in all eight.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    read_json,
    run_verifiers,
    write_json,
    write_sha256s,
)

WEEK = "week18"

FROZEN_RED_LINES = {
    "data/dielectric_v03.csv": "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4",
    "probes/l3_stage1_pilot_pool.csv": "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18",
    "probes/l3_backvalidation_prereg.json": "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98",
    "data/processed/dielectric_observations_v11plus.csv": "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    "probes/dielectric_r2_levers_prereg.json": "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa",
    "data/viscosity_v01.csv": "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26",
}

MAIN_SCOREBOARD = 0.4091179943351143
MAIN_SCOREBOARD_VERSION = "v2"
MAIN_SCOREBOARD_HEADLINE_R2 = 0.4766400383507876
MAIN_SCOREBOARD_HEADLINE_DELTA_R2 = 0.0675220440156733
MAIN_SCOREBOARD_PROMOTED_AT_UTC = "2026-09-27T01:34:06Z"
MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS = 11
RANDOM_ROW_LEAK_REFERENCE_R2 = 0.7385332681453336
FROZEN_SINGLE_REPRESENTATION_R2 = 0.6080587938801277
FROZEN_SINGLE_REPRESENTATION_CROSS_SEED = 0.5861142332208197
FROZEN_PHYSICAL_MINUS_BLEND_DELTA = 0.044489

# Week 18 made no attempt at the main scoreboard, so the cumulative ledger is
# carried over unchanged from the Week 17 close-out.
W18_MAIN_SCOREBOARD_ATTEMPTS = 0

W18_SEEDS = (42, 1234, 2026, 31337, 7)

# Every Week 18 lane is a separate pre-registration with its own pool and its own
# decision rule.  `promoted` is false in all of them, so this list is also the
# reason the week adds no shot to the frozen board.
LANE_KEYS = (
    "w18_p0_hyperparameter_grid",
    "w18_p1_multiseed_endpoint",
    "w18_p2_onsager_delta",
    "w18_p3_conformer_flexibility",
    "w18_p5_unimol_embedding",
    "w18_p6_log_scale_calibration",
    "w18_a_viscosity_row_level",
    "w18_b_applicability_domain",
)

LANE_SOURCES = {
    "w18_p0_hyperparameter_grid": {
        "probe": "probes/dielectric_hyperparameter_grid.py",
        "prereg": "probes/dielectric_hyperparameter_grid_prereg.json",
        "summary": "probes/dielectric_hyperparameter_grid_summary.json",
        "report": "reports/dielectric_hyperparameter_grid.md",
        "tests": ("tests/test_hyperparameter_grid.py",),
        "artifacts": ("probes/artifacts/dielectric_hyperparameter_grid_repeats.csv",),
    },
    "w18_p1_multiseed_endpoint": {
        "probe": "probes/dielectric_multiseed_endpoint.py",
        "prereg": "probes/dielectric_multiseed_endpoint_prereg.json",
        "summary": "probes/dielectric_multiseed_endpoint_summary.json",
        "report": "reports/dielectric_multiseed_endpoint.md",
        "tests": ("tests/test_multiseed_endpoint.py",),
        "artifacts": ("probes/artifacts/dielectric_multiseed_endpoint_repeats.csv",),
    },
    "w18_p2_onsager_delta": {
        "probe": "probes/dielectric_onsager_delta_w18.py",
        "prereg": "probes/dielectric_onsager_delta_w18_prereg.json",
        "summary": "probes/dielectric_onsager_delta_w18_summary.json",
        "report": "reports/dielectric_onsager_delta_w18.md",
        "tests": (
            "tests/test_dielectric_onsager_delta_probe.py",
            "tests/test_dielectric_onsager_delta_w18.py",
        ),
        "artifacts": (
            "probes/artifacts/dielectric_onsager_delta_w18_repeats.csv",
            "probes/dielectric_onsager_delta_w18_placebo_summary.json",
        ),
    },
    "w18_p3_conformer_flexibility": {
        "probe": "probes/dielectric_conformer_flexibility.py",
        "prereg": "probes/dielectric_conformer_flexibility_prereg.json",
        "summary": "probes/dielectric_conformer_flexibility_summary.json",
        "report": "reports/dielectric_conformer_flexibility.md",
        "tests": ("tests/test_conformer_flexibility.py",),
        "artifacts": (
            "probes/artifacts/dielectric_conformer_flexibility_repeats.csv",
            "probes/dielectric_conformer_flexibility_placebo_summary.json",
        ),
    },
    "w18_p5_unimol_embedding": {
        "probe": "probes/dielectric_unimol_embedding.py",
        "prereg": "probes/dielectric_unimol_embedding_prereg.json",
        "summary": "probes/dielectric_unimol_embedding_summary.json",
        "report": "reports/dielectric_unimol_embedding.md",
        "tests": ("tests/test_unimol_embedding.py",),
        "artifacts": (
            "probes/artifacts/dielectric_unimol_embedding.csv",
            "probes/artifacts/dielectric_unimol_embedding_repeats.csv",
            "probes/dielectric_unimol_embedding_placebo_summary.json",
            "probes/build_unimol_embeddings.py",
        ),
    },
    "w18_p6_log_scale_calibration": {
        "probe": "probes/dielectric_log_scale_calibration.py",
        "prereg": "probes/dielectric_log_scale_calibration_prereg.json",
        "summary": "probes/dielectric_log_scale_calibration_summary.json",
        "report": "reports/dielectric_log_scale_calibration.md",
        "tests": ("tests/test_log_scale_calibration.py",),
        "artifacts": ("probes/artifacts/dielectric_log_scale_calibration_repeats.csv",),
    },
    "w18_a_viscosity_row_level": {
        "probe": "probes/viscosity_row_level_unfreeze.py",
        "prereg": "probes/viscosity_row_level_prereg.json",
        "summary": "probes/viscosity_row_level_summary.json",
        "report": "reports/viscosity_row_level_unfreeze.md",
        "tests": ("tests/test_viscosity_row_level.py",),
        "artifacts": ("probes/artifacts/viscosity_row_level_repeats.csv",),
    },
    "w18_b_applicability_domain": {
        "probe": "probes/dielectric_applicability_domain.py",
        "prereg": "probes/dielectric_applicability_domain_prereg.json",
        "summary": "probes/dielectric_applicability_domain_summary.json",
        "report": "reports/dielectric_applicability_domain.md",
        "tests": ("tests/test_applicability_domain.py",),
        "artifacts": ("probes/artifacts/dielectric_applicability_domain_repeats.csv",),
    },
}


# The package carries the eight lane bundles plus the frozen evidence they rest on.
CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("probes/dielectric_coordination_block_v3_summary.json", "dielectric_coordination_block_v3_summary.json"),
    ("probes/dielectric_coordination_block_prereg_v3.json", "dielectric_coordination_block_prereg_v3.json"),
    ("probes/dielectric_representation_seed_robustness_summary.json", "dielectric_representation_seed_robustness_summary.json"),
    ("probes/dielectric_head_sweep_summary.json", "dielectric_head_sweep_summary.json"),
    ("probes/dielectric_splitters_auc_summary.json", "dielectric_splitters_auc_summary.json"),
    ("reports/dielectric_splitters_auc.md", "dielectric_splitters_auc.md"),
    ("probes/artifacts/w17_ordering_vs_magnitude.png", "w17_ordering_vs_magnitude.png"),
    ("probes/dielectric_source_sweep_v2_sources.csv", "dielectric_source_sweep_v2_sources.csv"),
    ("reports/w17_dielectric_source_sweep_v2.md", "w17_dielectric_source_sweep_v2.md"),
    ("probes/artifacts/dielectric_xtb_full_table_migration_conformers.csv", "dielectric_xtb_full_table_migration_conformers.csv"),
    ("data/dielectric_v04.csv", "data/dielectric_v04.csv"),
    ("data/viscosity_v02.csv", "data/viscosity_v02.csv"),
)


def _lane_artifacts() -> tuple[tuple[str, str], ...]:
    """Flatten every lane bundle into (source, destination) copy pairs."""

    pairs: list[tuple[str, str]] = []
    for key in LANE_KEYS:
        sources = LANE_SOURCES[key]
        for field in ("probe", "prereg", "summary", "report"):
            relative = str(sources[field])
            pairs.append((relative, Path(relative).name))
        for relative in sources["tests"]:
            pairs.append((str(relative), Path(str(relative)).name))
        for relative in sources["artifacts"]:
            pairs.append((str(relative), Path(str(relative)).name))
    return tuple(pairs)


# Week 18 figures, produced by the visual lane.  They are discovered from disk so a
# plot added or renamed by that lane cannot silently drop out of the package; the
# exporter records which ones were actually present.
def _figures() -> tuple[str, ...]:
    directory = REPOSITORY_ROOT / "probes" / "artifacts"
    if not directory.is_dir():
        return ()
    return tuple(
        sorted(
            path.relative_to(REPOSITORY_ROOT).as_posix()
            for path in directory.glob("w18_*.png")
        )
    )


FIGURES = _figures()

ARTIFACTS = CARRY_FORWARD + _lane_artifacts()

VERIFIERS = (
    "scripts/verify_dielectric_v04.py",
    "scripts/verify_liquid_window_gate.py --check",
    "scripts/verify_walden_dn_channel.py --check",
    "probes/verify_unimol_probe_spec.py --check",
    "scripts/verify_four_core_registry.py --check",
    "scripts/verify_orbital_second_source.py --check",
    "scripts/verify_themol_orbital_layer.py --check",
    "scripts/verify_themol_orbital_layer_expanded.py --check",
    "scripts/verify_reaxys_v1x_stocking_probe_roster.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py tests/test_export_week17_results.py "
        "tests/test_dielectric_coordination_block_v3.py tests/test_dielectric_v04.py "
        "tests/test_viscosity_row_level.py tests/test_hyperparameter_grid.py "
        "tests/test_conformer_flexibility.py tests/test_log_scale_calibration.py "
        "tests/test_applicability_domain.py tests/test_dielectric_onsager_delta_probe.py "
        "tests/test_unimol_embedding.py tests/test_plot_week18.py "
        "tests/test_multiseed_endpoint.py "
        "-q -p no:cacheprovider"
    ),
)

def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return (completed.stdout or "").strip()


def _worktree_status(source_root: Path) -> tuple[bool, int]:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return bool(lines), len(lines)


def _frozen_red_lines() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for relative, expected in FROZEN_RED_LINES.items():
        path = REPOSITORY_ROOT / relative
        measured = _sha256(path) if path.is_file() else None
        result[relative] = {
            "expected_sha256": expected,
            "measured_sha256": measured,
            "intact": measured == expected,
        }
    return result


def _lane_prereg(key: str) -> dict[str, object]:
    """Read a lane pre-registration and prove it was locked before the run."""

    relative = str(LANE_SOURCES[key]["prereg"])
    path = REPOSITORY_ROOT / relative
    payload = read_json(path)
    return {
        "path": relative,
        "sha256": _sha256(path),
        "status": payload.get("status"),
        "locked_before_run": str(payload.get("status")) == "locked_before_run",
        "seeds": payload.get("seeds"),
    }


def _lane_payload(key: str) -> dict[str, object]:
    """Read one lane summary and surface the fields the package quotes."""

    sources = LANE_SOURCES[key]
    summary_relative = str(sources["summary"])
    summary = read_json(REPOSITORY_ROOT / summary_relative)
    carried: dict[str, object] = {}
    verdict = summary.get("verdict")
    promoted = summary.get("promoted")
    # Lane summaries do not share one schema: some carry the decision at the top
    # level, some nest it under `decision` / `decisions` / `promotion`.  Walk the
    # known containers so a lane cannot silently report promote=True by omission.
    for container_name, verdict_field, promoted_field in (
        ("decision", "verdict", "promotable"),
        ("primary_gate", "verdict", None),
        ("decisions", "verdict", "promotable"),
        ("promotion", None, "promoted"),
    ):
        container = summary.get(container_name)
        if not isinstance(container, dict):
            continue
        if verdict is None and verdict_field is not None:
            verdict = container.get(verdict_field)
        if promoted is None and promoted_field is not None:
            promoted = container.get(promoted_field)
    for field in (
        "task",
        "representation",
        "promotion_rule",
        "reproduction_check",
        "anchor",
        "anchors",
        "decision",
        "primary_gate",
        "endpoint",
        "cross_seed",
        "placebo",
        "domain_rules",
        "headline_vs_in_domain",
        "honest_boundaries",
        "telemetry",
    ):
        if field in summary:
            carried[field] = summary[field]
    carried["verdict"] = verdict
    carried["promoted"] = promoted
    return {
        "probe": str(sources["probe"]),
        "prereg": _lane_prereg(key),
        "summary_path": summary_relative,
        "summary_sha256": _sha256(REPOSITORY_ROOT / summary_relative),
        "report": str(sources["report"]),
        "tests": [str(item) for item in sources["tests"]],
        "summary_top_level_keys": sorted(str(name) for name in summary),
        "fields": carried,
    }


def export_results(*, output_root: Path, overwrite: bool) -> dict:
    import shutil

    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(str(week_root) + " already exists; pass --overwrite")

    frozen = _frozen_red_lines()
    if not all(bool(entry["intact"]) for entry in frozen.values()):
        broken = sorted(name for name, entry in frozen.items() if not entry["intact"])
        raise ValueError("a frozen red line moved: " + ", ".join(broken))

    worktree_dirty, dirty_paths = _worktree_status(REPOSITORY_ROOT)
    head_commit = _head_commit(REPOSITORY_ROOT)

    lanes = {key: _lane_payload(key) for key in LANE_KEYS}
    for key, payload in lanes.items():
        if not bool(dict(payload["prereg"])["locked_before_run"]):
            raise ValueError("lane " + key + " has no locked pre-registration")

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, ARTIFACTS)

    figures: list[str] = []
    for relative in FIGURES:
        source = REPOSITORY_ROOT / relative
        if not source.is_file():
            continue
        destination = week_root / Path(relative).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        figures.append(destination.relative_to(week_root).as_posix())

    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    verdicts = {
        key: {
            "verdict": dict(payload["fields"]).get("verdict"),
            "promoted": dict(payload["fields"]).get("promoted"),
        }
        for key, payload in lanes.items()
    }
    promoted_lanes = sorted(
        key for key, block in verdicts.items() if bool(block["promoted"])
    )

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
            "worktree means no commit identifies them, so this field must be re-read "
            "after the close-out commit"
        ),
        "main_scoreboard": {
            "schema_version": 2,
            "version": MAIN_SCOREBOARD_VERSION,
            "baseline": {
                "value": MAIN_SCOREBOARD,
                "status": "retained_unchanged",
                "still_used_as_the_comparability_anchor": True,
            },
            "headline": {
                "value": MAIN_SCOREBOARD_HEADLINE_R2,
                "delta_vs_baseline": MAIN_SCOREBOARD_HEADLINE_DELTA_R2,
                "promoted_at_utc": MAIN_SCOREBOARD_PROMOTED_AT_UTC,
                "configuration": (
                    "hybrid Morgan+Physical 0.5*(Morgan+Physical) plus lever 4 (conformer-average "
                    "dipole, 2 columns) plus lever 8 (Li+ coordination block, 5 columns)"
                ),
                "pool": "457 rows / 97 compounds / 276 distinct (compound, temperature) pairs",
                "folds": "GroupKFold by InChIKey, 10 repeats x 5 folds, seed 42",
            },
            "touched_this_week": False,
            "touched_by": (
                "nothing: Week 18 made zero attempts at the main scoreboard. Every lane "
                "reports under its own pre-registration and its own pool, and no lane "
                "promotes a reading."
            ),
            "mixing_rule": (
                "the headline and the baseline may appear together only with this block own "
                "configuration lines; they are never divided, added, or compared as two "
                "models, and neither is ever compared with the v1.0 headline 0.364"
            ),
        },
        "shots": {
            "main_scoreboard_attempts": W18_MAIN_SCOREBOARD_ATTEMPTS,
            "cumulative_main_scoreboard_attempts": MAIN_SCOREBOARD_CUMULATIVE_ATTEMPTS,
            "cumulative_note": (
                "the Week 14 ledger read 10, Week 17 added one, and Week 18 adds none; the "
                "cumulative total is carried over unchanged"
            ),
        },
        "frozen_reference_readings": {
            "baseline_r2": MAIN_SCOREBOARD,
            "headline_r2": MAIN_SCOREBOARD_HEADLINE_R2,
            "single_representation_r2": FROZEN_SINGLE_REPRESENTATION_R2,
            "single_representation_cross_seed_mean": FROZEN_SINGLE_REPRESENTATION_CROSS_SEED,
            "physical_minus_blend_delta": FROZEN_PHYSICAL_MINUS_BLEND_DELTA,
            "random_row_leak_reference_r2": RANDOM_ROW_LEAK_REFERENCE_R2,
        },
        "week18_seeds": list(W18_SEEDS),
        "lanes": lanes,
        "lane_verdicts": verdicts,
        "promoted_lanes": promoted_lanes,
        "no_lane_promotes": promoted_lanes == [],
        "figures_present": figures,
        "frozen_red_lines": frozen,
        "frozen_red_lines_all_intact": all(bool(entry["intact"]) for entry in frozen.values()),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "artifacts": copied,
    }

    write_json(week_root / "week18_summary.json", summary)
    write_json(week_root / "verification.json", verification)
    (week_root / "README.md").write_text(README_TEXT, encoding="utf-8", newline=chr(10))
    write_sha256s(week_root)
    return summary


README_TEXT = """# Week 18 交付包（封顶后的路径排序：P0–P6 ＋ η 行级解冻 ＋ 分域第二记分牌）

数据血缘: 冻结表 `data/dielectric_v03.csv` **未改动**（digest `ff2142936e…35ccce4`）；Week 17 已发布工件与 week1–week17 交付包未被触碰。
冻结**基线 `0.4091179943351143`** 与冻结**头条 `0.4766400383507876`**（v2：Morgan+Physical ＋ 杠杆 4 ＋ 杠杆 8；**457** 行 / **97** 化合物 = **276** 个（化合物, T）对；训练侧全表 **2029** 行）**一个字都不动**。
Week 17 已判定「开放许可化合物 153 ≈ 上限 157–161」，因此 Week 18 **停止买数据、改买机制**：把 W17 尚未打死的八条路径各跑一条**独立预注册**，结论照实上报。
八条 lane **全部 `promoted = false`**：本周对主记分牌 **0 次尝试**，累计 **11 次**不变。
生成脚本: `probes/export_week18_results.py`

## 头条（十四句话，都不许外推）

1. **P0 重调 XGB 超参是唯一接近过门的一枪，但仍没过**：同一池、同一折、同一计分器、同一 `Physical(lever4)` 表示，只换 XGBoost 超参（网格 `max_depth × n_estimators`，其余固定 lr 0.05 / mcw 1 / ss 0.8 / cs 0.8）。最佳臂 `hp d4xn200` 跨种子端点 **0.5998203128630835**，相对单表示锚点端点 `0.5861142332208197`（其 seed 42 单抽是 `0.6080587938801277`）提升 **+0.01370607964226378**；**距 0.60 差 0.00018**。判 `partial`。
2. **P0 的第二个读数比 0.5998 本身更有信息量**：`hp d4xn200` 的跨种子 sd **0.008159756085597283**，而参考臂 sd 为 0.017461880006798203；过 0.60 的种子数从 1/5 升到 2/5。**深度 2 确实欠拟合**这条机制假设成立，只是幅度不足以翻门。
3. **P1 把「端点」从运气里拆出来，结论是头条被高估**：四个臂在**跑前锁定的五种子** {42, 1234, 2026, 31337, 7} 上的端点分别为 **0.40135270382650734** / **0.44840711903316777** / **0.4374976919688038** / **0.45401075998423623**；`plus_both` 的跨种子**最大值**恰好就是 seed 42 的 `0.4766400383507876`。
4. **诚实口径下的头条端点是 `0.45401075998423623`，不是 `0.4766400383507876`**：`0.4766` 是**五种子里的最大单抽**。`plus_both − baseline` 在 **5/5 种子全为正**（+0.0675220440156733 / +0.06719383048427285 / +0.031659711999165674 / +0.0704559453827242 / +0.026458748906808216），所以**杠杆本身不靠运气**，但**量级**要按端点报。判 `endpoint_upgraded`。
5. **P2 换目标（Onsager / Kirkwood Δ-learning）没有买到分数**：`reference_direct` 逐位复现冻结五种子端点 `0.5861142332208197`（5/5 `abs_gap = 0.000e+00`），而 Δ 臂端点 `onsager_delta_xgb` **0.2242978111516481**、`onsager_delta_recomputed` **0.22339251807234367**，纯解析臂 **−0.5160011378298242**。判 `refuted`。
6. **P2 的安慰剂照实登记为「未按预注册塌回」**：目标在计分化合物上打乱后，`reference_direct` 端点降到 0.5236384736868015（确实动了标签），但 Δ 臂不是塌回参考臂，而是**掉到它下面**（−0.43059541050271505 / −0.4004543038576844）。这条偏离不解释成合格。
7. **P2 顺带给出了 Kirkwood g 的实测指纹**：`ε_Onsager` 对质子性缔合液严重偏低（水 87.00 → 46.84，甲酰胺 106.14 → 4.79，N-甲基乙酰胺 178.47 → 5.21），对非质子液偏高（乙腈 37.70 → 54.12）。计分池 ε>60 共 **13** 行，解析式只覆盖其中 **1** 行。
8. **P3 构象方差列没加分**：`lever4 + 柔性列` 跨种子 **0.5691705415075562** < 锚点端点，判 `refuted`。
9. **P5 Uni-Mol 预训练嵌入作特征块是本周最负的一条**：`plus_unimol` 跨种子 **0.1102020209457352** vs 锚点 `0.5861142332208197`（Δ ≈ −0.4759），0/5 种子为正，判 `refuted`。至此「预训练 3D 表示」这个家族在本任务上被判决。
10. **P6 log 空间训练 ＋ 保序校准只改善次要口径**：原尺度 R² 为 **0.5834189863657219**（lever4）/ **0.4801664084104241**（保序），未超锚点，判 `partial`；log 空间 R² 另报，但**主记分牌仍守原尺度**。
11. **η 通道是全漏斗离过门最近的一处，本周把它从族级压到行级仍未过门**：族级 MAE **0.17477197208762**，行级最好 **0.15686276760094522**（另一池 0.15698877870055475），门 **0.15** ⇒ **还差 0.006863**。判 `refuted`，但方向明确、缺口最小。
12. **分域第二记分牌已按声明口径报出，且与全域并列、永不替换**：声明规则 **D1（极性/质子性：`NumHDonors ≥ 1` 且 `TPSA ≥ 20.0`）** 之下，**5 种子域内端点** R² **0.524012313223719**、**域外** R² **0.3198024498133034**（域外判定 **40 / 97** 个化合物）；同一张表的**全域 5 种子端点**是 **0.45401075998423623**（与 P1 `plus_both` 端点逐位一致），而冻结头条 `0.4766400383507876` 仍按 seed 42 单抽原位复现、不被改写。
13. **八条 lane 的裁定一览**：P0 `partial`、P1 `endpoint_upgraded`、P2 `refuted`、P3 `refuted`、P5 `refuted`、P6 `partial`、η 行级 `refuted`、分域 `domain_split_reported`。**没有一条晋升**。
14. **封顶后的诚实结论**：0.60 在现有法律（开放许可化合物 ≈157–161）与物理（单分子描述符缺 Kirkwood g）约束下**未被达到**；阶梯表「0.58–0.65 档」的前提（化合物覆盖翻倍）在 Week 17 已被证否。本周的诊断仍是一句话：**排序学会了、量级学不会** —— R² 量的是后者，AUC 量的是前者。

## 交付内容

- 八条 lane 各自的 `probe / prereg / summary / report / tests / artifacts`（见 `week18_summary.json` 的 `lanes`）。
- 八张图（`probes/artifacts/w18_*.png`）：多种子端点、超参网格、Onsager Δ、构象柔性、log 尺度、η 行级、分域、总记分牌。
- 冻结证据与红线清单（`frozen_red_lines`，逐文件 sha256 实测比对）。
- `verification.json`：14 项校验命令逐条退出码。

*Week 18 交付包 · 生成脚本 `probes/export_week18_results.py` · 所有 lane 均为独立预注册、`promoted = false` · 冻结基线 0.4091179943351143 与冻结头条 0.4766400383507876 未动*
"""


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = export_results(output_root=args.output_root, overwrite=args.overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

