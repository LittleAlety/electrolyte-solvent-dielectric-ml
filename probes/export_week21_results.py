"""Export the Week 21 deliverables -- the v2 framework alignment package.

Week 21 does not buy a new scoreboard reading.  It buys *addressability*: the
already-built assets get re-coded onto the v2 framework's slots, and the
framework's own decision vocabulary (uncertainty-aware rank stability, Top-k
overlap, selection regret, the three splits, feature-cost accounting) gets
instantiated on the orbital channel for the first time.

Four lanes, none of them promoted, none of them touching a frozen number:

* W21-0 -- framework ingest + feature-cost map + multi-axis chemical space + Stage 0/1 verdicts;
* W21-1 -- sections 9 / 10 / 13 on P_0 (GFN2-xTB gas) vs R_sol (Batt, SMD eps=18.5);
* W21-2 -- the Walden kinematic_thaw close-out in the data layer;
* W21-3 -- Axis B C_1: the Li+ coordination condition state, first instantiation.

Nothing on the frozen side moves: 0.4091179943351143, 0.4766400383507876,
0.5861142332208197 and 0.6216672295270079 keep their own definitions, and the
main scoreboard gets 0 attempts this week (cumulative stays at 12).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
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

WEEK = "week21"

FROZEN_RED_LINES = {
    "data/dielectric_v03.csv": "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4",
    "probes/l3_stage1_pilot_pool.csv": "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18",
    "probes/l3_backvalidation_prereg.json": "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98",
    "data/processed/dielectric_observations_v11plus.csv": "159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9",
    "probes/dielectric_r2_levers_prereg.json": "ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa",
    "data/viscosity_v01.csv": "12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26",
}

FROZEN_READINGS = {
    "frozen_baseline": 0.4091179943351143,
    "frozen_headline": 0.4766400383507876,
    "single_representation_cross_seed": 0.5861142332208197,
    "w20_4_promoted_arm": 0.6216672295270079,
}

LANES: dict[str, dict[str, object]] = {
    "w21_0_framework_alignment": {
        "title": "Tier 1：v2 框架原文入库 + 槽位接口三表",
        "probe": "probes/w21_framework_alignment.py",
        "prereg": None,
        "summary": "probes/w21_framework_alignment_summary.json",
        "report": "reports/w21_framework_alignment.md",
        "tests": ("tests/test_w21_framework_alignment.py",),
        "artifacts": (
            "probes/artifacts/w21_feature_cost_map.csv",
            "probes/artifacts/w21_stage_gate_verdicts.csv",
            "data/processed/w21_chemical_space_metadata.csv",
            "docs/framework/ranking-electrolyte-materials-v2.md",
            "docs/framework/ranking-electrolyte-materials-v2.sha256",
            "reports/w21_framework_slot_map.md",
            "reports/w21_framework_notes.md",
        ),
        "produces_reading": False,
        "promoted": False,
    },
    "w21_1_rank_stability": {
        "title": "Tier 2：§9 排序稳定性 + §10 决策指标 + §13 拆分/复杂度阶梯",
        "probe": "probes/w21_rank_stability.py",
        "prereg": "probes/w21_rank_stability_prereg.json",
        "summary": "probes/w21_rank_stability_summary.json",
        "report": "reports/w21_rank_stability.md",
        "tests": ("tests/test_w21_rank_stability.py",),
        "artifacts": (
            "probes/artifacts/w21_rank_pairs.csv",
            "probes/artifacts/w21_topk_overlap.csv",
            "probes/artifacts/w21_split_metrics.csv",
            "probes/artifacts/w21_lofo_by_family.csv",
            "probes/artifacts/w21_tolerance_sensitivity.csv",
            "reports/w21_split_taxonomy.md",
        ),
        "produces_reading": True,
        "promoted": False,
    },
    "w21_3_li_coordination": {
        "title": "Tier 3：Axis B C_1 Li⁺ 配位条件态首次实例化（GFN2-xTB 级，X2 层由空转有）",
        "probe": "probes/w21_li_coordination.py",
        "prereg": "probes/w21_li_coordination_prereg.json",
        "summary": "probes/w21_li_coordination_summary.json",
        "report": "reports/w21_li_coordination.md",
        "tests": ("tests/test_w21_li_coordination.py",),
        "artifacts": (
            "data/processed/w21_li_coordination_layer.csv",
            "probes/artifacts/w21_li_coordination_inversions.csv",
            "probes/artifacts/w21_li_coordination_delta_stats.csv",
            "probes/artifacts/w21_li_coordination_topk.csv",
            "probes/artifacts/w21_li_coordination_qc.csv",
            "probes/artifacts/w21_li_coordination_batt_step.csv",
            "probes/artifacts/w21_li_coordination_binding_posthoc.csv",
            "probes/artifacts/w21_li_coordination_scf_retry_posthoc.csv",
        ),
        "produces_reading": True,
        "promoted": False,
    },
    "w21_2_eta_thaw": {
        "title": "Tier 2：Walden kinematic_thaw 解冻（数据层）",
        "probe": "probes/w21_eta_thaw.py",
        "prereg": None,
        "summary": "probes/w21_eta_thaw_summary.json",
        "report": "reports/w21_eta_thaw.md",
        "tests": ("tests/test_w21_eta_thaw.py",),
        "artifacts": ("probes/artifacts/w21_eta_thawed_rows.csv",),
        "produces_reading": False,
        "promoted": False,
    },
}

LANE_KEYS = tuple(LANES)

CARRY_FORWARD = (
    ("README.md", "README.md"),
    ("reports/decisions_log.md", "decisions_log.md"),
    ("probes/w21_framework_alignment.py", "w21_framework_alignment.py"),
    ("probes/w21_rank_stability.py", "w21_rank_stability.py"),
    ("probes/w21_eta_thaw.py", "w21_eta_thaw.py"),
    ("probes/w21_li_coordination.py", "w21_li_coordination.py"),
    ("probes/w21_li_coordination_figures.py", "w21_li_coordination_figures.py"),
    ("probes/w21_figures.py", "w21_figures.py"),
)

FIGURES = (
    "probes/artifacts/w21_rank_stability_matrix.png",
    "probes/artifacts/w21_rank_flow_map.png",
    "probes/artifacts/w21_split_taxonomy.png",
    "probes/artifacts/w21_li_coordination_shift.png",
)

VERIFIERS = (
    "scripts/verify_themol_orbital_layer.py --check",
    "scripts/verify_four_core_registry.py --check",
    (
        "-m pytest tests/test_repo_hygiene.py "
        "tests/test_w21_framework_alignment.py tests/test_w21_rank_stability.py tests/test_w21_eta_thaw.py tests/test_w21_li_coordination.py"
        " -q -p no:cacheprovider"
    ),
)


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source_root, capture_output=True, text=True, check=False)
    return (completed.stdout or "").strip()


def _worktree_status(source_root: Path) -> tuple[bool, int]:
    completed = subprocess.run(["git", "status", "--porcelain"], cwd=source_root, capture_output=True, text=True, check=False)
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return bool(lines), len(lines)


def _frozen_red_lines() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for relative, expected in FROZEN_RED_LINES.items():
        path = REPOSITORY_ROOT / relative
        measured = sha256_file(path) if path.is_file() else None
        result[relative] = {"expected_sha256": expected, "measured_sha256": measured, "intact": measured == expected}
    return result


def _lane_payload(key: str) -> dict[str, object]:
    lane = LANES[key]
    declared: list[str] = [str(lane["probe"]), str(lane["report"]), *[str(item) for item in lane["tests"]], *[str(item) for item in lane["artifacts"]]]
    if lane["prereg"]:
        declared.append(str(lane["prereg"]))
    if lane["summary"]:
        declared.append(str(lane["summary"]))
    prereg_block = None
    if lane["prereg"]:
        path = REPOSITORY_ROOT / str(lane["prereg"])
        payload = read_json(path)
        status = payload.get("status", payload.get("prereg_status"))
        prereg_block = {"path": str(lane["prereg"]), "sha256": sha256_file(path), "status": status, "locked_before_run": status == "locked_before_run"}
    summary_path = REPOSITORY_ROOT / str(lane["summary"]) if lane["summary"] else None
    return {
        "title": lane["title"],
        "probe": lane["probe"],
        "report": lane["report"],
        "report_sha256": sha256_file(REPOSITORY_ROOT / str(lane["report"])),
        "tests": list(lane["tests"]),
        "artifacts": list(lane["artifacts"]),
        "prereg": prereg_block,
        "summary_path": lane["summary"],
        "summary_sha256": sha256_file(summary_path) if summary_path and summary_path.is_file() else None,
        "declared_files": declared,
        "declared_files_missing": [item for item in declared if not (REPOSITORY_ROOT / item).is_file()],
        "produces_reading": lane["produces_reading"],
        "promoted": lane["promoted"],
    }


def _missing_lane_keys() -> tuple[str, ...]:
    return tuple(key for key in LANE_KEYS if not (REPOSITORY_ROOT / str(LANES[key]["report"])).is_file())


README_TEXT = """# Week 21 交付包（框架接线：资产 → v2 槽位 / §9 §10 §13 首次实例化 / η 解冻数据层结清 / C_1 Li⁺ 条件态首次实例化）

数据血缘: 冻结表 `data/dielectric_v03.csv` **未改动**（digest `ff2142936e…35ccce4`）；week1–week20 交付包与已发布工件未被触碰。
冻结**基线 `0.4091179943351143`**、冻结**头条 `0.4766400383507876`**、单表示端点 `0.5861142332208197`、W20-4 晋升臂 `0.6216672295270079` **一个字都不动**。
本周主记分牌尝试 **0 次**（累计仍 **12** 次），`promoted_lanes = []`。
生成脚本: `probes/export_week21_results.py`

## 本周买到了什么

W21 不买新读数，买**可寻址性**：把已经做出来的资产按《Understanding Electrolyte Materials through Decision-Centric Ranking Stability》(v2) 的槽位重新编址，并把框架自己的决策词汇**第一次**落到本仓的数据上。

1. **框架原文逐字节入库**（`docs/framework/ranking-electrolyte-materials-v2.md`，54,147 B / 1,779 行，sha256 `e55c1b07…`），并出台式版槽位映射表（`reports/w21_framework_slot_map.md`）。
2. **特征成本三档实测**（§11）：18 行里 X0 9 / X1 2 / **X2 1** / target 2 / reference 4 —— **X2 整层为空**，因为本仓没有做任何 Li⁺ 配位计算。这不是遗漏，是边界，如实登记。
3. **多轴 chemical-space metadata**（§5.2）：246 行、16 个互斥主家族 + 多选官能团标签 + 角色；四个仓内不存在的字段（`conformer_count` / `Li_motif_count` / `state_identity_status` / `reactivity_status`）写 `not_available_in_repo`，**不编造**。
4. **Stage 0 / Stage 1 判词**（§19）：14 条，成立 8 / 部分成立 3 / 未执行 3；**Gate 1 = NOT CLOSED**（本仓不跑 DFT 批量计算）。
5. **§9 首次实例化**（n = 49 化合物 / 1,176 个 pair；P_0 = GFN2-xTB 气相，R_sol = Batt ωB97X-V/SMD(ε=18.5)，仅作 reference layer）：
   - 朴素换序率 **0.1556**（183 个 pair 翻序），但**预注册的 95% 分离规则下 robust inversion = 0 / 451**；bootstrap 95% CI 全为 0，permutation p = 1.0。
   - 至少一侧不可分辨的 pair 占 **0.6165**；**只被一侧解析的 pair 占 0.5655** —— 这正是框架 §9.2 分母会静默丢掉的那部分，本件单列。
   - `unresolved` 的名分：框架 §22.7（大部分 pairs 都 unresolved）是本仓轨道通道的实测归属。
   - 容差敏感性（事后臂，已在报告里标明）：z=1.0 → 5 个；z=0.674 → 27 个；不可分辨全部放开（z=0）→ 153 个。
   - 其它通道：LUMO ρ = 0.6459 / τ_b = 0.4660（`reference_only`）；gap 的 §9.2 分母塌缩，`f_robust_inversion` **无定义**，如实登记。
6. **§10 首次实例化**：Top-k overlap（k/N = 10/20/30%）= **0.400 / 0.900 / 0.800**；selection regret = **0.7874 / 0.1003 / 0.1147 eV**。**最顶上那 5 个候选，便宜模型和参考层只重叠 40%** —— 这是本件对筛选叙事最有用的一条。§10.3 threshold decision error 按 `not_instantiated` 登记（HOMO 通道没有外部设计阈值，且框架自己禁止事后挑阈值）。
7. **§13 首次并排**（target = Batt HOMO，45 个化合物带完整 X0 块）：
   - random 5×10：ridge 0.376 / GPR 0.447 / GBM 0.484 / 单特征 0.508 / RF **0.594**；
   - **骨架留出：全部为负**（最好 RF −0.901）；**LOFO：全部为负**（最好 GPR −5.681）；
   - 均值基线在 LOFO 下 **−27.45** ⇒ 「R² 的零点不是 0，是均值基线」；
   - KRR 按冻结超参跑会炸（−164.8），单列一条 `krr_tuned`（训练折内选参）后回到 −26.8，如实并列。
8. **η 解冻（数据层结清）**：Walden 臂的唯一依赖 `data/density_v01.csv` 已在盘上，176 条运动黏度行按**冻结配对规则**全部精确折成 η（`η = ν × ρ`，176/176 exact，0 unmatched），但只覆盖 **5** 个化合物、且 **0** 个新键 ⇒ **模型层明确不重拟合**（176 行撑不起通道级读数，且重拟合要另立预注册）。
9. **一条立项章笔误被纠正**：立项章 Tier 2 第 11 项写「把 `auc_gt15`/`auc_gt30` 加进 `METRIC_NAMES`」——该条**不执行**：问题已由 W18 的 AUC sidecar 解决，且 `tests/test_auc_sidecar_and_splitters.py` 断言 `METRIC_NAMES` 冻结为七项。改登记在 `reports/w21_framework_notes.md` 第 11 条。
10. **Tier 3：Axis B `C_1`（Li⁺ 配位条件态）首次实例化** —— 冻结 ε 名册 246 化合物 × 2 臂（free / [LiM]⁺）共 **492** 次 GFN2-xTB：
    - `X2` 槽位由「**整层为空**」变为「**有内容**」；`C_1` 由红字「未执行」变为「已实例化（低层级）」，层级**只到半经验**，如实标注，不冒充框架 §7 要求的 DFT 级；
    - HOMO 通道：Δ 均值 **−4.05 eV**、ρ(C_0,C_1) = **0.627**、Top-10% overlap = **10/11** ⇒ 配位**保住**了 HOMO 排序；
    - LUMO 通道：ρ = **0.230**、Top-10% overlap = **0/22** ⇒ 配位**摧毁**了 LUMO 排序（本臂最尖锐的一条）；
    - §9 三层并排（49 化合物 Batt 子集）：C_0 **0/482**、C_1 **0/329**，且 `P0` 行逐位复现 W21-1 的 `0/451`（回归核验通过）；
    - 质控与两条**事后**诊断（明确标 `post_hoc_not_preregistered`，不进任何主读数）：9 个臂 SCF 不收敛（离子液体盐 / Iron pentacarbonyl）、`no_motif` 类在结构判据下被判 `intact` 而结合能体检把它们标为 `not_a_bound_state`。


## 交付内容

- 四条 lane 各自的 `probe / summary / report / tests / artifacts`（见 `week21_summary.json` 的 `lanes`；缺件记在 `lanes_missing`，本周应为空）。
- 图 4 张：`w21_rank_stability_matrix.png`、`w21_rank_flow_map.png`、`w21_split_taxonomy.png`、`w21_li_coordination_shift.png`。
- 框架原文副本 + sha256 侧车、槽位映射表、框架补丁清单。
- 冻结证据与红线清单（`frozen_red_lines`，逐文件 sha256 实测比对）。
- `verification.json`：逐条校验命令退出码。
- `decisions_log.md`：含 §28.67–§28.70。

*Week 21 交付包 · 生成脚本 `probes/export_week21_results.py` · 四条 lane 独立预注册（或声明无读数）· 本周 0 次主记分牌尝试（累计 12）· 冻结读数未动*
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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

    pairs: list[tuple[str, str]] = list(CARRY_FORWARD)
    for key in LANE_KEYS:
        lane = LANES[key]
        for field in ("probe", "summary", "report"):
            value = lane[field]
            if value is not None:
                name = str(value)
                pairs.append((name, Path(name).name))
        if lane["prereg"]:
            name = str(lane["prereg"])
            pairs.append((name, Path(name).name))
        for item in (*lane["tests"], *lane["artifacts"]):
            name = str(item)
            pairs.append((name, Path(name).name))
    pairs.extend((figure, Path(figure).name) for figure in FIGURES)

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, pairs)
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    promoted_lanes = sorted(key for key, payload in lanes.items() if bool(payload["promoted"]))
    reading_lanes = sorted(key for key, payload in lanes.items() if bool(payload["produces_reading"]))

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
        "main_scoreboard_attempts_delta": 0,
        "cumulative_main_scoreboard_attempts": 12,
        "frozen_readings": FROZEN_READINGS,
        "frozen_red_lines": frozen,
        "figures": [Path(figure).name for figure in FIGURES],
        "files": sorted(copied),
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "framework": {
            "copy": "ranking-electrolyte-materials-v2.md",
            "sha256": read_json(REPOSITORY_ROOT / "probes/w21_framework_alignment_summary.json")["framework"]["sha256"],
            "source": "E:\\Claude Code\\电解液溶剂-HB\\核心文件\\ranking-electrolyte-materials-v2.md",
        },
        "boundaries": [
            "不引用 Reaxys 数值；不把 Batt 参考层当训练标签；不把 THEMol（CC BY-NC 4.0）值折进任何交付池。",
            "本周 0 次主记分牌尝试，累计仍 12 次；四个冻结读数未动。",
            "参考层物理不确定度未量化，只登记 0.05 eV 数值容差 —— 该缺口随读数一起报告。",
        ],
    }
    write_json(week_root / "week21_summary.json", summary)
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
    print(json.dumps({k: result[k] for k in ("week", "artifacts_commit", "worktree_dirty", "worktree_dirty_paths", "lanes_missing", "promoted_lanes", "verification_passed")}, ensure_ascii=False, indent=2))
    return 0 if not result["lanes_missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())