# 工作日志 · Week 41（把 W40 登记的四条欠账写成机器规则）

> 承接 `reports/work_log_week37_to_week40.md`。本轮起点：W40 交付（HEAD `04b27e3`）。本轮 0 shot，累计仍 19。

## Week 41：四条治理 lane 把「下次要记得」变成「跑前已写死」

**目标**：W40 交付说明 §5 与 README §11 第 29–32 条留下四条只写在报告散文里的规则。本轮把它们逐条落成机器可复算件：W41-A 阶梯池准入、W41-B 域比双读数、W41-C 例外登记准入、W41-D 轨道层级声明。

**交付**

- **预注册**：`probes/w41_governance_prereg.json`（revision 2，`locked_before_run`；v1→v2 更正了 W41-C 的 append 计数与重叠 owner，见下）。
- **W41-A 阶梯池准入**：把「阶梯 = 同一配置网格上的档位」写死为 R1–R4（`admit_prefix` + 剔除 `shuffled|placebo|random_target` + 剔除 `morgan|fingerprint|embedding` + 重复集完整）。40 臂切成 **33 准入 + 7 剔除**；准入池比值 **21.044062 / 13.712271 / 8.092207 / 4.178785 / 7.272894**，逐位复现 W40-A 冻结锚，AUC30 极差上限 **0.018851**。**反事实**：W28 全 13 臂比值只有 **1.293416**（< 稳健门 4.0）—— 不复用准入规则就会得到假判否。9 条判据全成立。
- **W41-B 域比双读数**：从 `w40_onsager_domain_compounds.csv` 逐化合物**独立重算**两套域比：未校正 **2.5817133417**、校正后 **3.1132529111**、相对变化 **0.2058863627 > 0.10**；高介电族（eps ≥ 60）**13.4044 → 17.3170**（校正后**更**分离，方向与全域相反）。条款件 `w41_domain_ratio_clause.json` 写死「双读数 + 相对变化」，`direction_robust=True / magnitude_robust=False`。10 条判据 = 9 成立 + 1 在册判否（**H41b5**）。
- **W41-C 例外登记准入**：按**源码证据**（不是手写分组）把 `EXEMPT_WRITERS` 的 22 个 owner 分到三类：pinned **16** / append **4** / strict **3**，重叠 **1**。**更正 W40 手写分组**：真 `pinned∩append` 是 `probes/pubchem_identity_layer.py`（line 702 追加写 + 被 `identity_smiles_drawing_decision_summary.json` 当依赖件钉死），不是 `pubchem_liquid_window_harvest.py`；append 计数是 4 不是 3。反向漏网 **0**（没有任何被登记 owner 含 `write_json_stable`）。三条准入规则写进 `w41_exemption_policy.json`。10 条判据全成立。
- **W41-D 轨道层级声明**：把三条件（GFN2-xTB 气相 / QM9 B3LYP 气相 / Batt ωB97X-V+SMD）放到同一 241 行名册上，batt 按 InChIKey 复算命中 **73**（对齐 W38-D），三方交集 **48**。两两排序迁移：ρ(xTB,QM9)=**0.885628**、ρ(QM9,Batt)=**0.817674**、ρ(xTB,Batt)=**0.330371**；在**同一 48 化合物**上 min(ρ(xTB,QM9), ρ(QM9,Batt)) − ρ(xTB,Batt) = **0.281 > 0.2** ⇒ **不可传递**。三层两两都是 `cross_level`、同层级外部源数 **0** ⇒ W40 登记的第 3 条仍未满足。11 条判据 = 10 成立 + 1 在册判否（**H41d8**）。

**关键读数**：判据 **9 + 10 + 10 + 11 = 40 条 = 38 成立 + 2 已登记判否**（H41b5 / H41d8）；shot 0（累计仍 19）；四个冻结读数一个不动；26 项 W41 测试全绿。

**判否与口径**

- 两条在册判否：**H41b5**「域比量级稳健」被否（相对变化 > 0.10）；**H41d8**「跨层排序先验可传递 / 可代理」被否（不可传递 gap 0.281）。
- 阶梯准入是**问法**规则，不是数据改动；域比是相关读数不是因果；例外登记不是豁免；外部层数值不入标签池或特征列。

**产物**

`probes/w41_governance_prereg.json`、`probes/w41_ladder_admission.py`、`w41_domain_ratio_robustness.py`、`w41_exemption_admission.py`、`w41_orbital_level_declaration.py`；`probes/artifacts/w41_*.csv`、`w41_domain_ratio_clause.json`、`w41_exemption_policy.json`、`w41_orbital_level_declaration.json`、`w41_*.png`、四份 `*_summary.json`；`reports/w41_*.md`、`reports/week41_project_charter.md`、`reports/week41_delivery_readme.md`；`tests/test_w41_*.py`；`probes/export_week41_results.py`。