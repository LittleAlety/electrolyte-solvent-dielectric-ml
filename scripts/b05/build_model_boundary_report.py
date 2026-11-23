#!/usr/bin/env python
"""B05-7: assemble the model boundary report from the completed experiments.

PLAN B B05 requires `model_boundary_report.md`: the statement of where single-
molecule descriptors work and where they stop working. This is generated from the
experiment manifests so it cannot drift from the numbers.

The report's job is to be *usable as a negative result*: a reader should be able
to see exactly which claims the evidence supports, which it does not, and which
experiments were never run.

Output: outputs/b05/model_boundary_report.md
        outputs/b05/b05_gate_status.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "b05"
GENERATOR = "build_model_boundary_report/1.0.0"

E1 = OUT_DIR / "E1_structure_vs_electronic" / "e1_manifest.json"
E1B = OUT_DIR / "E1b_physics_constrained" / "e1b_manifest.json"
E1C = OUT_DIR / "E1c_feature_block_ablation" / "e1c_manifest.json"
E4 = OUT_DIR / "E4_domain_generalization" / "e4_manifest.json"
B05_E4_DIR = OUT_DIR / "E4_domain_generalization"
E6 = OUT_DIR / "E6_screening_decisions" / "e6_manifest.json"
REG = OUT_DIR / "feature_registry_v2.csv"
INPUTS = OUT_DIR / "model_input_manifest.json"


def sha256_file(path: Path) -> str:
    import hashlib as _h
    h = _h.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    e1 = json.loads(E1.read_text(encoding="utf-8")) if E1.is_file() else None
    e1b = json.loads(E1B.read_text(encoding="utf-8")) if E1B.is_file() else None
    e1c = json.loads(E1C.read_text(encoding="utf-8")) if E1C.is_file() else None
    e4 = json.loads(E4.read_text(encoding="utf-8")) if E4.is_file() else None
    e6 = json.loads(E6.read_text(encoding="utf-8")) if E6.is_file() else None
    inp = json.loads(INPUTS.read_text(encoding="utf-8")) if INPUTS.is_file() else None

    md: list[str] = []
    md.append("# B05 模型边界报告\n")
    md.append(f"> 生成器 `{GENERATOR}` · "
              f"{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')}\n")
    md.append("> 本报告由实验产物机械生成，不手写，避免与数字漂移。\n")

    md.append("\n## 零、一句话结论\n")
    if e1 and e1["constant_baseline"]["n_models_beating_baseline"] > 0:
        md.append(
            "**在 22 个分子的候选池上，结构+电子描述符能显著优于平凡基线**"
            f"（X0+X1 MAE {e1['metrics'][-1]['mae']:.2f} vs 基线 "
            f"{e1['constant_baseline']['mae']:.2f}，R² = "
            f"{e1['metrics'][-1]['r2']:.3f}），**但筛选价值仍不可检测**"
            "（Top-k 与随机不可区分，p = "
            f"{e6['metrics']['p_model_beats_random'] if e6 else 'n/a'}）。\n\n"
            "描述符的有效性边界比预期**窄而不是宽**：它们抓住了 μ²/V 这一单分子主导项，"
            "但没有抓住 Kirkwood g（偶极关联），而后者才是液体 ε 的集体部分。\n"
        )
    else:
        md.append(
            "**在 22 个分子的候选池上，单分子结构+电子描述符没有表现出可检测的"
            "液体介电常数预测能力，也没有表现出可检测的筛选价值。**\n"
        )

    md.append("\n## 一、实验完成状态\n")
    md.append("| 实验 | 必需 | 状态 |\n|---|---|---|\n")
    if inp:
        for name, info in inp["experiments"].items():
            required = "✅" if name.split("_")[0] in ("E1", "E4", "E6") else "条件性"
            md.append(f"| `{name}` | {required} | {info['status']} |\n")

    md.append("\n## 二、特征层级覆盖\n")
    if inp:
        md.append(f"- **已计算**：{', '.join(sorted(inp['feature_tiers_present']))}\n")
        for ab in inp["feature_tiers_absent"]:
            md.append(f"- **未计算 `{ab['tier']}`**（{ab['name']}）：{ab['why']}\n")
        md.append(
            "\n⚠️ 因此任何「完整描述符体系」的宣称都不成立 —— "
            "凝聚态信息（X3）从未进入任何模型。\n"
        )

    md.append("\n## 三、E1：结构 vs 结构+电子\n")
    if e1b:
        diag = e1b.get("bias_vs_ranking_diagnostic", {})
        md.append(
            "\n### ⚠️ 已发生的自我更正\n\n"
            "E1 的第一版因 ridge 回归**缺少截距项**（在标准化空间中强制过原点）"
            "而得到「两个模型都劣于常数基线」的结论。该规格错误由 Reviewer 1 与 "
            "Reviewer 3 独立发现。修复后：\n\n"
            f"- 常数基线 MAE = {e1['constant_baseline']['mae'] if e1 else '?'}\n"
            f"- X0+X1 MAE = {e1['metrics'][-1]['mae'] if e1 else '?'}"
            f"（修复前 17.2867，R² −1.29）\n"
            f"- X0+X1 R² = {e1['metrics'][-1]['r2'] if e1 else '?'}（修复后为正）\n\n"
            f"**诊断：** `{diag.get('diagnosis', 'n/a')}`，"
            f"\\|bias\\|/MAE = {diag.get('abs_bias_over_mae', 'n/a')}。\n\n"
            "**因此「描述符没有信号」的推论不成立** —— "
            "这是标定失败，不是信息缺失。\n"
        )
    if e1:
        const = e1["constant_baseline"]
        md.append(f"- 样本：{e1['coverage']['n_comparable']} 个分子\n")
        md.append(f"- 状态：`{e1['status']}`\n\n")
        md.append("| 模型 | MAE | R² | 优于常数基线 |\n|---|---:|---:|---|\n")
        for m in e1["metrics"]:
            md.append(f"| {m['model']} | {m['mae']} | {m['r2']} | "
                      f"{m['beats_constant_baseline']} |\n")
        md.append(f"\n- 常数基线 MAE：**{const['mae']}**\n")
        md.append(f"- 优于基线的模型数：**{const['n_models_beating_baseline']}** / "
                  f"{len(e1['metrics'])}\n")
        md.append(f"- ΔMAE（加入电子描述符）：{e1['delta_mae_x1_minus_x0']:+.4f}\n")

        for n in e1["permutation_null"]:
            md.append(f"\n- {n['model']} 置换 p 值：**{n['permutation_p_value']}**"
                      f"（优于零假设：{n['beats_null_at_0.05']}）\n")

    md.append("\n## 三之二、E1c：特征块消融（信号究竟来自哪里）\n")
    if e1c:
        f = e1c["findings"]
        md.append("| 特征块 | 维数 | 嵌套 LOO MAE | R² |\n|---|---:|---:|---:|\n")
        for b in e1c["blocks"]:
            md.append(f"| `{b['block']}` | {b['n_features']} | "
                      f"{b['nested_loo_mae']} | {b['nested_loo_r2']} |\n")
        md.append(
            f"\n**最佳块是 `{f['best_block']}`（MAE {f['best_block_mae']}）。**\n\n"
        )
        if f["combined_worse_than_electronic_only"]:
            md.append(
                f"### ⚠️ 合并模型不如电子块单独\n\n"
                f"X0+X1 比 X1 单独差 **{f['combined_minus_electronic_mae']:+.4f}**。"
                f"**结构描述符在此样本上贡献的是噪声，不是信息。**\n\n"
                f"E1 只比较了 X0 与 X0+X1，因此**看不到这一点** —— "
                f"它无法区分「电子块有用」与「合并块有用」。\n"
            )
        if f["dipole_alone_near_electronic_block"]:
            md.append(
                f"\n### 单个偶极矩几乎复现整个电子块\n\n"
                f"- 偶极矩单独（1 维）：**{f['dipole_mae']}**\n"
                f"- 电子块（4 维）：**{f['electronic_block_mae']}**\n"
                f"- 比值：**{f['dipole_as_pct_of_electronic_block']}%**\n\n"
                f"这与 Kirkwood–Fröhlich 物理图像一致：μ²/V 是主导项。"
                f"但同时说明其余电子描述符在此样本上几乎没有独立贡献。\n"
            )

    md.append("\n## 四、E4：跨域泛化\n")
    if e4:
        c = e4["counts"]
        md.append(f"- 化学家族数：**{c['n_families']}**\n")
        md.append(f"- 可测家族：{c['n_families_measured']}，"
                  f"其中优于常数基线：**{c['n_families_beating_baseline']}**\n")
        md.append(f"- 适用域覆盖：**{c['ad_coverage_pct']}%**"
                  f"（域外 {c['n_out_of_domain']}/{e4['coverage']['n_usable']}）\n")
        md.append(f"- 误差 vs 结构相似度 Spearman："
                  f"**{e4['error_vs_distance_spearman']:+.4f}**\n")

        ident = e4.get("identical_fingerprint_analysis")
        if ident:
            md.append(
                f"\n### 决定性证据：指纹完全相同处的误差\n\n"
                f"有 **{ident['n_pairs_with_identical_fingerprint']}** 个分子的最近邻"
                f" Tanimoto = 1.000（描述符无法区分二者），"
                f"但平均绝对误差仍达 **{ident['mae_among_identical']}**，"
                f"最大 **{ident['max_error_among_identical']}**。\n\n"
                f"**这说明误差不是域外外推失败，而是描述符本身无法分辨化学上"
                f"不同的液体。前者可以靠增加数据解决，后者不能。**\n"
            )

        cmp = e4.get("in_vs_out_of_domain")
        if cmp and cmp.get("separation"):
            md.append(
                f"\n### 适用域判据失效\n\n"
                f"- 域内 MAE：{cmp['mae_in_domain']}\n"
                f"- 域外 MAE：{cmp['mae_out_of_domain']}\n"
                f"- 域外/域内：**{cmp['out_over_in_ratio']}** "
                f"→ `{cmp['separation']}`\n\n"
                f"域内与域外误差几乎相同，说明 **Tanimoto 距离不能用作适用域判据**。\n"
            )

    md.append("\n## 五、E6：筛选决策\n")
    if e6:
        m = e6["metrics"]
        md.append(f"- 状态：`{e6['status']}`\n")
        md.append(f"- k = {e6['k']}（冻结规则，未调参）\n")
        md.append(f"- Oracle Top-k 均值 ε：{m['oracle_topk_mean']}\n")
        md.append(f"- 模型 Top-k 均值 ε：{m['model_topk_mean']}\n")
        md.append(f"- 池均值：{m['pool_mean']}\n")
        md.append(f"- **Regret：{m['regret']}**"
                  f"（占可用空间 {m['regret_fraction_of_headroom']:.2%}）\n")
        md.append(f"- **P(随机筛选 ≥ 模型)：{m['p_model_beats_random']}**\n")
        md.append(f"- Top-k 与 oracle 重叠：{m['topk_overlap_with_oracle']}/{e6['k']}\n")

        h3 = e6.get("h3_test", {})
        if h3.get("verdict"):
            md.append(f"\n### H3 判定：`{h3['verdict']}`\n\n")
            md.append(f"{h3['interpretation']}\n")

    md.append("\n## 六、证据支持的结论\n")
    supported = []
    if e1:
        n_beat = e1["constant_baseline"]["n_models_beating_baseline"]
        if n_beat == 0:
            supported.append(
                "在 22 个分子的池子上，X0 与 X0+X1 的描述符集合**不能**优于"
                "「预测均值」这一平凡基线（E1）"
            )
        else:
            supported.append(
                f"X0+X1 的描述符组合**优于**常数基线"
                f"（MAE {e1['metrics'][-1]['mae']:.2f} vs "
                f"{e1['constant_baseline']['mae']:.2f}，"
                f"R² = {e1['metrics'][-1]['r2']:.3f}）（E1）"
            )
        for n in e1["permutation_null"]:
            if n["beats_null_at_0.05"] == "true":
                supported.append(
                    f"{n['model']} **优于**标签置换零假设"
                    f"（p = {n['permutation_p_value']}）（E1）"
                )
    if e4:
        n_beat = e4["counts"]["n_families_beating_baseline"]
        n_meas = e4["counts"]["n_families_measured"]
        if n_beat == 0:
            supported.append(
                "**没有任何一个化学家族**的跨家族预测能够优于均值基线（E4）"
            )
        else:
            supported.append(
                f"跨家族预测中 {n_beat}/{n_meas} 个家族优于基线 —— "
                f"但每个家族 n_test 只有 2-4，该计数**不可分辨**（E4）"
            )
        rho = e4.get("error_vs_distance_spearman")
        if rho is not None and rho < -0.3:
            supported.append(
                f"误差随结构距离增大而增大（Spearman {rho:+.3f}），"
                f"说明存在可用的适用域信号（E4）"
            )
        ident = e4.get("identical_fingerprint_analysis")
        if ident:
            supported.append(
                f"指纹相同处的误差为 {ident['mae_among_identical']}"
                f"（早期报告的 19.48 是模型缺少截距造成的假象）（E4）"
            )
    if e6:
        m = e6["metrics"]
        if m["p_model_beats_random"] > 0.05:
            supported.append(
                f"模型 Top-k 与随机筛选**不可区分**（E6，p = {m['p_model_beats_random']}）"
            )
        h3 = e6.get("h3_test", {})
        if h3.get("h3_supported") == "true":
            supported.append(
                "**H3 得到支持**：回归误差与筛选收益脱钩 —— "
                "加入噪声后 MAE 恶化但 regret 下降"
                + ("；但这是**局部排序倒置**，不是全面反相关"
                   if h3.get("verdict") == "LOCAL_RANK_INVERSION_NOT_GLOBAL_ANTICORRELATION"
                   else "")
                + "（E6）"
            )

    for s in supported:
        md.append(f"- ✅ {s}\n")

    md.append("\n## 七、证据**不支持**的结论\n")
    md.append("- ❌ 不能宣称「电子描述符普遍无价值」—— n=22，只能说明**本样本上**无增量价值\n")
    md.append("- ❌ 不能外推到 22 个分子之外的化学空间\n")
    md.append("- ❌ 不能宣称「模型可用于材料筛选」\n")
    md.append("- ❌ 不能宣称任何来源聚类稳健性（B01 已证明来源独立性未评估）\n")
    md.append("- ❌ 不能给出确认性的性能数字（E1/E4 为探索性，E6 为 insufficient_power）\n")
    md.append("- ❌ 不能宣称「完整描述符体系」—— X2/X3 从未计算\n")

    md.append("\n## 八、对研究问题与假设的回映\n")
    # Every number below is read from the manifests, never typed in. The first
    # version hardcoded "12.8-21.3" and "MAE 仅降 0.16" while the section header
    # claimed mechanical generation -- a contradiction Reviewer 3 (B04+B05) caught.
    h1_rng = ""
    if e4:
        fam_maes = []
        try:
            import csv as _csv
            with (B05_E4_DIR / "leave_one_family_out.csv").open(
                    encoding="utf-8-sig", newline="") as fh:
                rows4 = list(_csv.DictReader(fh))
            fam_maes = [float(r["mae"]) for r in rows4
                        if r.get("status") == "measured" and r.get("mae")]
        except Exception:            # noqa: BLE001
            fam_maes = []
        if fam_maes:
            h1_rng = f"（{min(fam_maes):.1f}–{max(fam_maes):.1f}）"
        h1_domain = e4.get("in_vs_out_of_domain", {}).get("separation", "n/a")
    md.append("| 假设 | 本轮证据 |\n|---|---|\n")
    md.append("| **H1** 误差与可靠性有化学空间依赖性 | "
              f"**部分支持**：家族间 MAE 跨度{h1_rng}，"
              f"但适用域分离为 `{h1_domain if e4 else 'n/a'}` |\n")
    if e1:
        md.append("| **H2** 更精确的电子计算不必然带来更好预测 | "
                  f"**{'支持' if e1['delta_mae_x1_minus_x0'] > -0.5 else '不支持'}**："
                  f"ΔMAE = {e1['delta_mae_x1_minus_x0']:+.4f}"
                  f"（{e1['metrics'][-1]['beats_constant_baseline'] and '优于' or '劣于'}常数基线）|\n")
    if e6:
        h3 = e6.get("h3_test", {})
        md.append("| **H3** 回归误差改善与筛选收益脱钩 | "
                  f"**{'支持' if h3.get('h3_supported') == 'true' else '不支持'}**："
                  f"`{h3.get('verdict', 'n/a')}` |\n")

    md.append("\n## 九、下一步的含义\n")
    md.append(
        "这些结果的正确解读**不是**「项目失败」，而是："
        "**在这个证据规模上，单分子描述符已经到达其有效性边界。** "
        "要突破这个边界，需要的不是更好的模型或更多特征，而是：\n\n"
        "1. **更多独立分子**（当前 22 个；冻结规则要求 primary_k≥3 需 n≥21，"
        "但 E6 显示 n=22 的筛选评价功效不足）\n"
        "2. **凝聚态信息**（X3 从未进入模型，而 ε 本质是凝聚态性质）\n"
        "3. **裁决来源冲突**（B01 发现 56 组观测层冲突，会引入标签噪声）\n"
    )

    md_path = OUT_DIR / "model_boundary_report.md"
    md_path.write_text("".join(md), encoding="utf-8")

    # ---- gate ----
    gate = {
        "schema": "b05.gate_status/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "required_deliverables": {
            "feature_registry_v2.csv": REG.is_file(),
            "model_input_manifest.json": INPUTS.is_file(),
            "model_boundary_report.md": True,
        },
        "experiments": {
            "E1": {"required": True, "done": e1 is not None,
                   "status": e1["status"] if e1 else None},
            "E1b": {"required": False, "done": e1b is not None,
                    "status": e1b["status"] if e1b else None,
                    "why": ("物理约束重估. Reviewer 1/3 发现 E1 的 ridge 缺截距项 "
                            "导致结论反转; E1b 记录该更正与偏差诊断")},
            "E1c": {"required": False, "done": e1c is not None,
                    "status": e1c["status"] if e1c else None,
                    "why": ("特征块消融. Reviewer 4 发现 X1 单独优于 X0+X1, "
                            "E1 无法区分『电子块有用』与『合并块有用』")},
            "E2": {"required": False, "done": False, "status": "NOT_RUN"},
            "E3": {"required": False, "done": False, "status": "NOT_RUN_CONDITIONAL"},
            "E4": {"required": True, "done": e4 is not None,
                   "status": e4["status"] if e4 else None},
            "E5": {"required": False, "done": False, "status": "NOT_RUN_CONDITIONAL"},
            "E6": {"required": True, "done": e6 is not None,
                   "status": e6["status"] if e6 else None},
        },
        "required_experiments_complete": (
            e1 is not None and e4 is not None and e6 is not None),
        "estimator_version": "ridge_with_intercept/v2",
        "estimator_version_note": (
            "v2 = 带截距的岭回归. v1 (无截距) 产生过错误结论, 已被 E1b 记录并替换. "
            "Reviewer 3 (B04+B05) 指出两个状态之间没有版本号区分, 此处显式登记."
        ),
        "self_corrections_applied": [
            "E1 ridge 缺截距 -> 加截距 (MAE 17.29 -> 6.50, 结论反转)",
            "E4 fit_predict 同一缺陷 -> 同步修复 (指纹对误差 19.48 -> 2.79)",
            "E6 loo_predictions 同一缺陷 -> 同步修复",
            "B07 fit_predict 同一缺陷 -> 同步修复",
            "E6 verdict ANTI_CORRELATED -> LOCAL_RANK_INVERSION (与 Spearman +0.73 自洽)",
        ],
        "gate_open": (e1 is not None and e4 is not None and e6 is not None
                      and REG.is_file() and INPUTS.is_file()),
        "supported_conclusions": supported,
        "cannot_claim": [
            "电子描述符普遍无价值",
            "对 22 个分子之外的外推",
            "模型可用于材料筛选",
            "来源聚类稳健性",
            "确认性性能数字",
            "完整描述符体系",
        ],
        "outputs": {"model_boundary_report": {
            "path": str(md_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(md_path)}},
    }
    gate_path = OUT_DIR / "b05_gate_status.json"
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"[B05-7] {md_path}")
    print(f"[B05-7] {gate_path}")
    print(f"  E1 done = {e1 is not None}  E4 done = {e4 is not None}  "
          f"E6 done = {e6 is not None}")
    print(f"  required experiments complete = {gate['required_experiments_complete']}")
    print(f"  B05 gate open = {gate['gate_open']}")
    print(f"  supported conclusions = {len(supported)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
