# Week 41 交付说明

**本轮性质**：把 W40 登记的四条「下一份预注册要处理」事项**写成机器可复算的规则**，四条 lane 全是后验读数或治理件，**不重拟合主记分牌、不新增特征列、不改 `METRIC_NAMES`**。
**0 shot（累计仍 19）**，四个冻结读数（`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`）一个没动。四条探针各自 `exit 0`，判否项全部在 `REGISTERED_NEGATIVES` 中登记（H41b5 / H41d8）。

**一句话**：本轮把 W40 留在报告散文里的四条规则落成机械件 —— **阶梯准入**（比值判据只在干净池上问）、**域比双读数**（未校正与校正后同报）、**例外准入**（三类理由按源码证据分类）、**轨道层级声明**（跨层排序迁移不可传递，同层外部源缺位）。

## 1. lane 与读数

| lane | 回答 | 关键读数 | 判据 |
| --- | --- | --- | --- |
| **W41-A** 阶梯池准入 | 机械准入规则能不能逐位复现 W40-A 的五个阶梯比值 | 准入臂 **6 / 6 / 6 / 6 / 9**（40 臂 = 33 准入 + 7 剔除：换表示 2 / 安慰剂 1 / 非本网格 4）；比值 **21.044062 / 13.712271 / 8.092207 / 4.178785 / 7.272894**；AUC30 极差上限 **0.018851**；W28 全池反事实 **1.293416**（< 稳健门 4.0） | H41a1–H41a9（**9 条全成立**） |
| **W41-B** 域比双读数 | 同报未校正与校正后两个读数时相对变化是多少 | 未校正 **2.5817133417**、校正后 **3.1132529111**、相对变化 **0.2058863627 > 0.10**；高介电族（eps ≥ 60）**13.4044 → 17.3170**（校正后**更**分离）；双 μ 秩一致 **0.800684** | H41b1–H41b10（**10 条 = 9 成立 + 1 已登记判否 H41b5**） |
| **W41-C** 例外登记准入 | 22 个例外 owner 能不能机械落进三类理由 | pinned **16** / append **4** / strict **3**，重叠 **1**（`pubchem_identity_layer.py`）；反向漏网 **0**；三条准入规则已落进策略件 | H41c1–H41c10（**10 条全成立**） |
| **W41-D** 轨道层级声明 | 三条层级的排序迁移可不可传递 | 覆盖 xTB **237** / QM9 **103** / Batt **73**，三方交集 **48**；ρ(xTB,QM9)=**0.885628**、ρ(QM9,Batt)=**0.817674**、ρ(xTB,Batt)=**0.330371**（同一 48 化合物上 **0.538428**）；同层级对数 **0** | H41d1–H41d11（**11 条 = 10 成立 + 1 已登记判否 H41d8**） |

**合计 40 条判据 = 38 成立 + 2 已登记判否**（H41b5 / H41d8）。

## 2. 必须并读的边界

- **W41-A 的第一要求是「阶梯定义干净」。** 准入规则写死为「同一配置网格（`admit_prefix`）+ 剔除安慰剂 `shuffled|placebo|random_target` + 剔除换表示 `morgan|fingerprint|embedding` + 重复集完整」。W28 全 13 臂的比值只有 **1.293416**，落在稳健门 4.0 之下 ⇒ 污染池会给假判否。**不得**把比值判据用到未过准入的池子上。
- **W41-B 的双读数是硬条款。** 相对变化 **0.2058863627 > 0.10** ⇒ 只能声明「方向稳健」，**不得**声明「量级稳健」；域间比是**相关读数不是因果**；`g_rel` 只可做域间比较，不得与文献 g 绝对值对照。
- **W41-C 更正了 W40 手写分组。** 机械证据（源码 + 理由文本）下：`append_log` 计数是 **4**（W40 记 3）；真 `pinned∩append` 重叠是 **`pubchem_identity_layer.py`**（line 702 追加写 + 被依赖件摘要钉死），不是 W40 点名的 `pubchem_liquid_window_harvest.py`。**例外登记不是豁免**：这 22 个 owner 重跑**仍会弄脏工作树**，是明确保留的已知代价，不得计入迁移完成率。
- **W41-D 的三层两两都是 cross_level**（泛函 / 基组 / 溶剂化至少差一项），**同层级外部源数 = 0** ⇒ W40 登记的第 3 条（加权重前先补同层源）**仍未满足**；QM9 只能作**排序先验**，其数值不入标签池或特征列。标定式 `xTB = 2.0266971543817958·QM9 − 8.8728945529514` 只在 103 个命中化合物上成立。
- **H41d8 的在册判否**是「跨层排序先验可传递 / 可当作另一层的代理」这条**主张**被判否：同一 48 化合物上 min(ρ(xTB,QM9), ρ(QM9,Batt)) − ρ(xTB,Batt) = **0.281**，两条「与 Batt 一致」的链条推不出第三条。
- **分母纪律**：名册分母 **241** 行（`data/processed/dielectric_physical_features_v03.csv`）；xTB gap 有 4 行缺失，照实登记不插补。

## 3. 包里有什么

| 类别 | 路径 |
| --- | --- |
| 预注册 | `probes/w41_governance_prereg.json`（revision 2，`locked_before_run`） |
| 探针 | `probes/w41_ladder_admission.py`、`w41_domain_ratio_robustness.py`、`w41_exemption_admission.py`、`w41_orbital_level_declaration.py` |
| 产物 | `probes/artifacts/w41_ladder_admission.csv`（40 行）、`w41_ladder_admission_summary.csv`（5 行）、`w41_domain_ratio_robustness.csv`（4 行）、`w41_domain_ratio_clause.json`、`w41_exemption_admission.csv`（22 行）、`w41_exemption_policy.json`、`w41_orbital_level_registry.csv`（3 行）、`w41_orbital_pair_matrix.csv`（6 行）、`w41_orbital_batt_hits.csv`（73 行）、`w41_orbital_level_declaration.json` 及四份 summary |
| 图 | `probes/artifacts/w41_ladder_admission.png`、`w41_orbital_level_declaration.png` |
| 报告 | `reports/w41_ladder_admission.md`、`reports/w41_domain_ratio_robustness.md`、`reports/w41_exemption_admission.md`、`reports/w41_orbital_level_declaration.md`、`reports/week41_project_charter.md`、`reports/work_log_week41.md` |
| 测试 | `tests/test_w41_ladder_admission.py`（7）、`test_w41_domain_ratio_robustness.py`（6）、`test_w41_exemption_admission.py`（6）、`test_w41_orbital_level_declaration.py`（7）（合计 26 项） |
| 导出 | `probes/export_week41_results.py` |

> **第三方数据集内容不进交付包**：Batt-P30K.h5 与 QM9 CSV 只按路径 + sha256 复现；本包携带的图与表均为本轮产物。

## 4. 复现

```
.venv\Scripts\python.exe probes\w41_ladder_admission.py
.venv\Scripts\python.exe probes\w41_domain_ratio_robustness.py
.venv\Scripts\python.exe probes\w41_exemption_admission.py
.venv\Scripts\python.exe probes\w41_orbital_level_declaration.py
.venv\Scripts\python.exe -m pytest tests\test_w41_ladder_admission.py tests\test_w41_domain_ratio_robustness.py tests\test_w41_exemption_admission.py tests\test_w41_orbital_level_declaration.py -q -p no:cacheprovider
.venv\Scripts\python.exe probes\export_week41_results.py --overwrite
```

## 5. 下一份预注册要处理的三件（已登记）

1. **同层级外部源仍然缺位**：三条轨道层两两 cross_level，给 HOMO/LUMO 通道加权前必须先补与 Batt ωB97X-V 同层级的独立源；PubChemQC 入口（InChIKey→CID 再定位分片）仍未执行。
2. **xTB→Batt 的排序迁移弱**：同一 48 化合物上 ρ(xTB,Batt) 仅 0.538、Pearson 0.088；任何用 xTB 作 Batt 代理的读数必须显式声明这一层差。
3. **例外类别扩展要走预注册**：新增例外只能落在三类之内；确需第四类时先改 `probes/w41_governance_prereg.json` 的 `evidence_rules` 再登记。