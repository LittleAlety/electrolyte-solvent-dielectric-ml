"""Export the Week 13 deliverables.

Covers three results and the one documentation correction that goes with them:

* the L3 back-validation *stage-1 pilot* (dielectric channel, in-roster pool,
  EC/PC only) -- ``stage_1_pilot_not_a_verdict``;
* outlet 2, the HOMO/LUMO/IP/EA structure-to-property baselines (gate 2/4, the
  "all four pass" criterion is **not** met);
* the P4 redox v2 enriched-feature probe (the 0.15 eV gate is **still red**);
* the manual appendix V / T-13 / T-14 reconciliation evidence.

The 75 MB of ``models/homo_lumo_*.ubj`` weights stay in the repository; this
package ships only ``models/homo_lumo_baselines.json``, which records the
sha256 of every weight file.
"""

from __future__ import annotations

import argparse
import hashlib
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

WEEK = "week13"

FROZEN_DIGEST = "ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4"
PREREG_SHA256 = "77f61a83b82de346292ff055c4f4c52003bccb6bfc98bf11813048abc6f0db98"
PILOT_POOL_SHA256 = "b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18"
HOMO_LUMO_POOL_SHA256 = "299ce3190dbbe5f37d514d4ca06e5db170360283e7943125bda990e0fc231524"


README_TEXT = """# Week 13 交付包（L3 阶段一试点 + 出口 2 门读数 + 氧化还原 v2 + 手册附录 V/T-13）

数据血缘: 规范数据集 data/dielectric_v03.csv **未改动**（digest
ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4）；
本轮全部产物为新增文件，v1.0 已发布工件未被触碰。
生成脚本: probes/export_week13_results.py

## 头条（三句话，都不许外推）

1. **L3 阶段一试点 = `stage_1_pilot_not_a_verdict`**：只跑介电通道、只在名册内池上做、只报 EC/PC，
   C1 = **0/2**（EC 第 24、PC 第 58）、C2_solvent **未过**（Δlog10 = -0.5939 / -0.5807，约门宽 0.10 的 5.8 倍），
   C3 与 C2_additive **显式未跑**。**这不是判决**（`verdict_eligible = false`），
   **不得写成「L3 未通过」** —— 预注册的 `failure_handling` 只管四通道完整跑批。
2. **出口 2 门读数 = 2/4**：LUMO 0.13855 过、HOMO 0.19051 过、IP 0.20110 未过（差 1.1 meV）、
   EA 0.23415 未过（差 34 meV）。「四个全过」口径 **未通过**；写手**明确拒绝**用合并 OOF 次级口径
   （IP 0.19466）把 IP 救成「过」。
3. **氧化还原 v2 门仍红**：留出 0.2174 / 0.3317、CV 0.2061 / 0.3183，全部高于冻结的 0.15 eV 门。
   富特征相对 v1 的 **-25.2% / -19.0%** 只作**方向证据**，**不得进任何对外文本**。

## 入口

- week13_summary.json - 机器可读摘要（三路结果 + 归档说明 + verifier 状态）
- verification.json - verifier 退出码与报告
- decisions_log.md - 含 §18（出口 2）、§19（氧化还原 v2 + 门判定）、§20（fold_source 通道补正 + 试点摘要措辞收口），以及 §17.7 的表述订正（§18.9）
- l3_stage1_pilot.py / _pool.csv / _detail.csv / _summary.json / l3_stage1_pilot.md - 阶段一试点本体
- l3_backvalidation_prereg.json - **当前修订**的 L3 预注册（sha256 77f61a83…0db98，含 amendment_3 的 fold_source 通道补正）；正文见 decisions_log.md §14/§15/§17/§20 与手册附录 U、U-6、T-14
- homo_lumo_baselines.json / .py / _summary.json / _screening.json / homo_lumo_baselines.md - 出口 2 本体
- data_processed/l3_homo_lumo_repeated_cv.csv 与 data_processed/l3_homo_lumo_cv_predictions.csv - 出口 2 的折记录与 OOF 明细
- p4_redox_v2_enriched.py / _summary.json / artifacts/*.csv / p4_redox_v2_enriched.md - 氧化还原 v2 本体
- manual_appendix_reconciliation.json / manual_appendix_j_snapshot.md - 手册附录 V 与 T-13 的机读证据
- reaxys_v1x_stocking_queue.csv / reaxys_v1x_stocking_scan_summary.json / reaxys_v1x_stocking_scan.md / reaxys_v1x_stocking_scan.py / verify_reaxys_v1x_stocking_scan.py - Reaxys v1.x 备货扫描（队列自动重算、读数为人工转录）
- test_l3_stage1_pilot.py / test_l3_backvalidation_prereg.py / test_homo_lumo_baselines.py / test_p4_redox_v2_enriched.py / test_reaxys_v1x_stocking_scan.py - 守卫

## Reaxys v1.x 备货扫描（数据侧，第四路）

- **队列**：池内 236 个溶剂里有 **167 个没有温度序列**（`<2` 个不同温度），池内**有**温度序列的是 **69** 个（167 + 69 = 236，脚本内已断言）；P1 = 2（由池内 `is_champion=true` 派生，不是硬编码物质名）、P2 = 22、P3 = 143。**P2 是族级复核顺序，不是可用性判断** —— `fluorinated` 是子串规则，会把 Fluorobenzene、m-/o-/p-Fluorotoluene、Trifluoroacetic acid 等 9 行非电解液含氟化合物一并排进 P2。
- **净新增**：人工查 7 个物质，只有 **4 条带温度的介电条目 / 2 个物质 / 3 篇一手文献**，4 条全部带给定频率口径（PC 两条 2 MHz、tetraglyme 两条 1 MHz）；PC 的「净新增 2 条」以 v03 冻结表冠军行为基线（观测表基线为 0 行）。
- **冠军核对（判决按证据强度降级）**：PC 的两条 25 C 条目是 `compilation_restatement_agrees` —— **汇编转述一致，不是独立测量**（证据链见 `reports/jstage_corroboration.md`，由守卫逐字断言引文出现在被引文件里）；EC 的 89.78 在本仓库溯源里是 40 C = 313.15 K，Reaxys 却标 25 C，判决 `value_matches_but_reaxys_temperature_label_conflicts`。
- **纪律**：全部读数 `restricted_crosscheck_only`，**永不进可分发数据集**；本产物不改模型、不改阈值、不改任何 L3 读数，与「外部免费 ε(T) 扩张收官」的既有结论方向一致（强化而非推翻）。
- **合规（点名 Reaxys）**：本包内含的 `reaxys_v1x_stocking_scan_summary.json` 与 `reaxys_v1x_stocking_scan.md` **确实带有受限数值的机器可读镜像**（`readings[].rendered_rows`、`net_new_detail[].value`），只允许留在本仓库与本交付包内，**禁止再次分发**；provenance 为 `reaxys<-bibliographic_citation`。

## 权重与归档说明（必须照写）

- **权重不在包里**：`models/homo_lumo_{lumo,homo,ip,ea}.ubj` 合计约 75 MB，留在仓库 `models/`；
  包内只放 `homo_lumo_baselines.json`，它已记录每个权重文件的 sha256，以及特征配置、每目标可复原信息、
  训练池 sha256、单位出处与 `gate`/`exclusion`/`cv_protocol` 全文。
- **`data/processed/` 是归档盲区**：该目录被仓库既有 `.gitignore` 排除，出口 2 的折记录 CSV 与 OOF 明细 CSV
  **不会进 git**；本包把 `data/processed/l3_homo_lumo_repeated_cv.csv` 与
  `data/processed/l3_homo_lumo_cv_predictions.csv` **复制进 `data_processed/`**，这是本轮这两份表的**唯一归档途径**
  （来源即仓库同名路径，逐字节复制，SHA256SUMS 里有独立哈希）。
- **week12 包里的 `l3_backvalidation_prereg.json` 是历史修订快照**：week12 交付时该文件为 17,735 B 的旧修订；
  **最新修订在 week13 包与仓库**（sha256 77f61a83…0db98；上一版 week13 快照 `39cc5e67…f435e9` 已由 amendment_3 修订覆盖）。审计时以各包内文件自身记录的 sha256 为准。

## 合规

- 阶段一试点带 `stage_1_pilot_not_a_verdict` 标签，不得引用为 L3 结论，不得进入对外文本。
- 出口 2 的特征路径只读 h5 的 `smiles`；全部 DFT 派生量在 `forbidden_inputs`。
- 氧化还原 v2 未改动 v1 的任何产物（`probes/p4_redox_summary.json`、`data/processed/redox_merged.csv` 等只读）。
- Reaxys 侧产物带受限数值的人工转录镜像（见上），只存于本仓库与 week13 包内，禁止再次分发。
"""

ARTIFACTS = (
    ("reports/decisions_log.md", "decisions_log.md"),
    # A. L3 back-validation stage-1 pilot (dielectric channel, in-roster, EC/PC).
    ("probes/l3_stage1_pilot.py", "l3_stage1_pilot.py"),
    ("probes/l3_stage1_pilot_pool.csv", "l3_stage1_pilot_pool.csv"),
    ("probes/l3_stage1_pilot_detail.csv", "l3_stage1_pilot_detail.csv"),
    ("probes/l3_stage1_pilot_summary.json", "l3_stage1_pilot_summary.json"),
    ("reports/l3_stage1_pilot.md", "l3_stage1_pilot.md"),
    ("tests/test_l3_stage1_pilot.py", "test_l3_stage1_pilot.py"),
    # The pre-registration shipped here is the current revision; the copy that
    # week12 shipped is a historical revision (see the README).
    ("probes/l3_backvalidation_prereg.json", "l3_backvalidation_prereg.json"),
    ("tests/test_l3_backvalidation_prereg.py", "test_l3_backvalidation_prereg.py"),
    # B. Outlet 2: HOMO / LUMO / IP / EA.  The .ubj weights stay in models/.
    ("models/homo_lumo_baselines.json", "homo_lumo_baselines.json"),
    ("probes/homo_lumo_baselines.py", "homo_lumo_baselines.py"),
    ("probes/homo_lumo_baselines_summary.json", "homo_lumo_baselines_summary.json"),
    ("probes/homo_lumo_baselines_screening.json", "homo_lumo_baselines_screening.json"),
    ("reports/homo_lumo_baselines.md", "homo_lumo_baselines.md"),
    ("tests/test_homo_lumo_baselines.py", "test_homo_lumo_baselines.py"),
    # data/processed/* is git-ignored, so this package is the only archive route.
    (
        "data/processed/l3_homo_lumo_repeated_cv.csv",
        "data_processed/l3_homo_lumo_repeated_cv.csv",
    ),
    (
        "data/processed/l3_homo_lumo_cv_predictions.csv",
        "data_processed/l3_homo_lumo_cv_predictions.csv",
    ),
    # C. P4 redox v2 (enriched features).
    ("probes/p4_redox_v2_enriched.py", "p4_redox_v2_enriched.py"),
    ("probes/p4_redox_v2_summary.json", "p4_redox_v2_summary.json"),
    (
        "probes/artifacts/p4_redox_v2_repeated_cv.csv",
        "artifacts/p4_redox_v2_repeated_cv.csv",
    ),
    (
        "probes/artifacts/p4_redox_v2_predictions.csv",
        "artifacts/p4_redox_v2_predictions.csv",
    ),
    (
        "probes/artifacts/p4_redox_v2_learning_curve.csv",
        "artifacts/p4_redox_v2_learning_curve.csv",
    ),
    ("reports/p4_redox_v2_enriched.md", "p4_redox_v2_enriched.md"),
    ("tests/test_p4_redox_v2_enriched.py", "test_p4_redox_v2_enriched.py"),
    # D. Manual appendix V / T-13 reconciliation evidence.
    (
        "probes/manual_appendix_reconciliation.json",
        "manual_appendix_reconciliation.json",
    ),
    ("tests/fixtures/manual_appendix_j_snapshot.md", "manual_appendix_j_snapshot.md"),
    # E. Reaxys v1.x stocking scan (derived queue + hand-transcribed probe).
    (
        "probes/reaxys_v1x_stocking_queue.csv",
        "reaxys_v1x_stocking_queue.csv",
    ),
    (
        "probes/reaxys_v1x_stocking_scan_summary.json",
        "reaxys_v1x_stocking_scan_summary.json",
    ),
    ("probes/reaxys_v1x_stocking_scan.py", "reaxys_v1x_stocking_scan.py"),
    (
        "probes/verify_reaxys_v1x_stocking_scan.py",
        "verify_reaxys_v1x_stocking_scan.py",
    ),
    ("reports/reaxys_v1x_stocking_scan.md", "reaxys_v1x_stocking_scan.md"),
    ("tests/test_reaxys_v1x_stocking_scan.py", "test_reaxys_v1x_stocking_scan.py"),
)

VERIFIERS = (
    "scripts/verify_dielectric_v03.py",
    "scripts/verify_p4_redox.py",
    (
        "-m pytest tests/test_l3_stage1_pilot.py tests/test_homo_lumo_baselines.py "
        "tests/test_p4_redox_v2_enriched.py tests/test_reaxys_v1x_stocking_scan.py "
        "-q -p no:cacheprovider"
    ),
)


def _head_commit(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return (completed.stdout or "").strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_results(*, output_root: Path, overwrite: bool) -> dict:
    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(f"{week_root} already exists; pass --overwrite")

    copied = copy_artifacts(REPOSITORY_ROOT, week_root, ARTIFACTS)
    verification = run_verifiers(REPOSITORY_ROOT, VERIFIERS)

    pilot = read_json(REPOSITORY_ROOT / "probes" / "l3_stage1_pilot_summary.json")
    outlet2 = read_json(REPOSITORY_ROOT / "probes" / "homo_lumo_baselines_summary.json")
    redox = read_json(REPOSITORY_ROOT / "probes" / "p4_redox_v2_summary.json")
    stocking = read_json(
        REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_scan_summary.json"
    )

    prereg_digest = _sha256(REPOSITORY_ROOT / "probes" / "l3_backvalidation_prereg.json")
    frozen_digest = _sha256(REPOSITORY_ROOT / "data" / "dielectric_v03.csv")

    pilot_pool = pilot.get("pool", {})
    pilot_readouts = pilot.get("readouts", {}).get("log_epsilon_minus_one", {})
    pilot_champions = pilot_readouts.get("champions", {})
    pilot_criteria = pilot.get("readings", {})
    recall = pilot_criteria.get("C1_recall_at_K", {})

    outlet2_gate = outlet2.get("gate", {})
    per_target = outlet2_gate.get("per_target") or {}

    summary = {
        "week": WEEK,
        "head_commit": _head_commit(REPOSITORY_ROOT),
        "frozen_dataset": {
            "path": "data/dielectric_v03.csv",
            "sha256": frozen_digest,
            "expected_sha256": FROZEN_DIGEST,
            "unchanged": frozen_digest == FROZEN_DIGEST,
        },
        "preregistration": {
            "path": "probes/l3_backvalidation_prereg.json",
            "sha256": prereg_digest,
            "expected_sha256": PREREG_SHA256,
            "is_the_current_revision": prereg_digest == PREREG_SHA256,
            "note": (
                "this is the current revision; the copy shipped inside the "
                "week12 package is a historical revision"
            ),
        },
        "stage_1_pilot": {
            "label": pilot.get("label"),
            "not_a_verdict": pilot.get("not_a_verdict"),
            "verdict_eligible": pilot.get("verdict_eligible"),
            "declaration": (
                "a pilot is not a verdict: only the dielectric channel, the "
                "in-roster pool and EC/PC were run; C3 and C2_additive were not "
                "run, so the conjunction cannot be satisfied or refuted by this "
                "run, and it must not be written as L3 having failed"
            ),
            "pool": {
                "path": pilot_pool.get("path"),
                "sha256": pilot_pool.get("sha256"),
                "rows": pilot_pool.get("rows"),
                "size_by_list": pilot_pool.get("size_by_list"),
                "line_ending": pilot_pool.get("line_ending"),
                "matches_the_pin": pilot_pool.get("sha256") == PILOT_POOL_SHA256,
            },
            "C1_recall_at_K": {
                "K": recall.get("K"),
                "hits_in_dielectric_solvent_list": recall.get(
                    "hits_in_dielectric_solvent_list"
                ),
                "passed_in_this_channel": recall.get("passed_in_this_channel"),
                "champion_ranks": recall.get(
                    "champion_ranks_in_dielectric_solvent_list"
                ),
            },
            "C2_solvent": {
                short: {
                    "predicted_dielectric": block.get("predicted_dielectric"),
                    "truth_dielectric": block.get("truth_dielectric"),
                    "delta_log10": block.get("delta_log10"),
                    "within_c2_tolerance": block.get("within_c2_tolerance"),
                }
                for short, block in pilot_champions.items()
            },
            "C3": "c3_not_run_stage_1_pilot",
            "C2_additive": "not_run_stage_1_pilot_redox_channel_not_executed",
            "regression_anchor": {
                "status": pilot.get("regression_anchor", {}).get("status"),
                "max_abs_metric_diff": pilot.get("regression_anchor", {}).get(
                    "max_abs_metric_diff"
                ),
                "row_values_compared": pilot.get("regression_anchor", {}).get(
                    "row_values_compared"
                ),
                "row_value_mismatches": pilot.get("regression_anchor", {}).get(
                    "row_value_mismatches"
                ),
            },
            "temperature_check": pilot.get("temperature_check"),
            "honest_boundaries": [
                (
                    "pool_frozen_before_scoring = true is self-attested: the only "
                    "corroboration is mtime plus a gate that itself admits it cannot "
                    "prove the freeze preceded seeing the champion ranks"
                ),
                (
                    "only EC and PC were actually removed from a training side; FEC "
                    "and VC were already withheld, so this is not all four being left out"
                ),
                (
                    "most valuable observation: removing the training side moved EC from "
                    "rank 14 to 24 and PC from rank 43 to 58"
                ),
            ],
        },
        "outlet_2": {
            "task": outlet2.get("task"),
            "pool_rows": outlet2.get("pool_rows"),
            "pool_sha256": outlet2.get("pool_sha256"),
            "pool_matches_the_pin": outlet2.get("pool_sha256") == HOMO_LUMO_POOL_SHA256,
            "unit": outlet2.get("unit", {}).get("unit"),
            "gate": {
                "threshold_mae": outlet2_gate.get("threshold_mae"),
                "best_model_mae": outlet2_gate.get("best_model_mae"),
                "targets_passed": outlet2_gate.get("targets_passed"),
                "targets_total": outlet2_gate.get("targets_total"),
                "passed": outlet2_gate.get("passed"),
                "criterion_scopes": outlet2_gate.get("criterion_scopes"),
            },
            "cv_protocol": outlet2.get("cv_protocol"),
            "per_target_pass": {
                target: block.get("passed") for target, block in per_target.items()
            },
            "honest_boundaries": [
                (
                    "the writer refuses to rescue IP with the pooled-OOF secondary "
                    "readout (0.19466 eV); the primary criterion is the mean fold MAE, "
                    "so IP is not passed"
                ),
                (
                    "fold_policy divergence: the pre-registration's fold_source "
                    "pointed at data/processed/v032_ablation_predictions.csv, a "
                    "dielectric table that carries no Batt-P30K molecules; the "
                    "coordinator ruled in favour of the stricter reading (champion "
                    "wholly out of the pool, 29,519 -> 29,515, folds regenerated by "
                    "RepeatedKFold(5,10,42) on the 29,515-row pool) and it is now "
                    "recorded as fold_and_seed.amendment_3 plus fold_source_by_channel"
                ),
                (
                    "data/processed/* is git-ignored, so the fold-record and OOF "
                    "prediction CSVs are archived only inside this package"
                ),
            ],
        },
        "redox_v2": {
            "probe": redox.get("probe"),
            "anchors": redox.get("anchors"),
            "split": redox.get("split"),
            "gate": redox.get("gate"),
            "gate_repeated_cv": redox.get("gate_repeated_cv"),
            "verdict": redox.get("verdict"),
            "discipline": (
                "the gate is red, so the redox channel must not be described as "
                "usable; the enriched-feature improvement is directional evidence "
                "only and must not enter any outward-facing text"
            ),
        },
        "manual_appendix": {
            "new_sections": [
                "附录 V（进展索引）",
                "T-13（§17.7 表述订正）",
                "T-14（§20：fold_source 通道补正 + 试点摘要措辞收口）",
            ],
            "note": (
                "the working manual lives outside the repository; the "
                "machine-readable evidence for this round is "
                "manual_appendix_reconciliation.json plus the regenerated "
                "tests/fixtures/manual_appendix_j_snapshot.md"
            ),
        },
        "reaxys_v1x_stocking_scan": {
            "path": "probes/reaxys_v1x_stocking_scan_summary.json",
            "date": stocking.get("date"),
            "browser": stocking.get("browser"),
            "compliance": stocking.get("compliance"),
            "queue_stats": stocking.get("queue_stats"),
            "net_new_temperature_points": stocking.get(
                "net_new_temperature_points"
            ),
            "cross_checks": stocking.get("cross_checks"),
            "open_items": stocking.get("open_items"),
            "honest_boundaries": [
                (
                    "the queue half is derived and re-derived by "
                    "probes/verify_reaxys_v1x_stocking_scan.py; the probe half is "
                    "a hand transcription of a manual logged-in session and "
                    "cannot be re-derived offline"
                ),
                (
                    "every Reaxys value is restricted_crosscheck_only: it may "
                    "not be joined into data/ or into the pool, and it is not a "
                    "substitute for any frozen readout"
                ),
                (
                    "the net-new total is 4 temperature-bearing dielectric "
                    "entries across 2 substances and 3 primary sources; all four "
                    "carry a stated-frequency qualifier (PC 2 MHz, tetraglyme "
                    "1 MHz), and the PC baseline is the v03 frozen champion row"
                ),
                (
                    "this probe changes no model, no threshold and no L3 "
                    "readout; it reinforces rather than reopens the closed "
                    "'external free epsilon(T) expansion' conclusion"
                ),
            ],
        },
        "verification": verification,
        "verification_passed": bool(verification.get("passed")),
        "artifacts": copied,
    }

    write_json(week_root / "week13_summary.json", summary)
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
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
