# Week 41 立项章：把 W40 登记的四条欠账写成机器可复算的规则（阶梯准入 / 域比双读数 / 例外准入 / 轨道层级声明）

**日期**：2026-10-04  
**上一轮**：W40（四条 lane 合并交付；README §11 第 29–32 条登记）  
**本轮范围**：W40 交付说明 §5 与 README §11 第 29–32 条留下四条「下一份预注册要处理」的事项，本轮**四条 lane 一并落地**：W41-A 阶梯池准入（第 29 条）、W41-B 域比双读数稳健性条款（第 30 条）、W41-C 例外登记表准入规则（第 32 条）、W41-D 轨道通道层级声明（第 27 / 31 条的同层源口径）。  
**shot 账本**：**本轮 0 shot，累计仍 19**。四条 lane 全是后验读数或治理件，不拟合任何主记分牌臂。  
**四个冻结读数**：`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`，本轮**一个都不动**。

---

## 1. 为什么是这四条

W40 把「登记」与「执行」之间最旧的一批欠账清掉了，但它自己又新增了四条**只写在报告散文里、还没写成机器规则**的条款。四条的共同点是：**规则本身是零成本的、且越晚写越容易与旧读数混引**。把它们并进一轮，是为了让「下次预注册要记得……」不再继续累积。

| lane | 登记来源 | 为什么现在做 |
| --- | --- | --- |
| W41-A 阶梯池准入 | §11 第 29 条 | W40-A 已证明污染池会把结论从「成立」翻成「判否」，但准入规则只写在探针注释里 |
| W41-B 域比双读数 | §11 第 30 条 | W40-C 的 H40c10 判否说明域比对偶极偏置敏感，双读数必须成为硬条款 |
| W41-C 例外登记准入 | §11 第 32 条 | `EXEMPT_WRITERS` 的三类理由只写在 reason 散文里，准入规则未机械化 |
| W41-D 轨道层级声明 | §11 第 27 / 31 条 | QM9 只能作排序先验；「层级不同」必须写进适用域声明，且要检验同层源是否真的缺位 |

## 2. 四条 lane 的判据与读数

| lane | 回答 | 关键读数 | 判据 |
| --- | --- | --- | --- |
| **W41-A** 阶梯池准入 | 机械准入规则能不能逐位复现 W40-A 的五个阶梯比值 | 准入臂 6/6/6/6/9（40 臂 = 33 准入 + 7 剔除）；比值 **21.044062 / 13.712271 / 8.092207 / 4.178785 / 7.272894**；W28 全池反事实 **1.293416** | H41a1–H41a9（9 条全成立） |
| **W41-B** 域比双读数 | 同报未校正与校正后两个读数时相对变化是多少 | 未校正 **2.5817133417**、校正后 **3.1132529111**、相对变化 **0.2058863627**；高介电族 **13.4044 → 17.3170** | H41b1–H41b10（10 条 = 9 成立 + 1 已登记判否 H41b5） |
| **W41-C** 例外登记准入 | 22 个例外 owner 能不能机械落进三类理由 | pinned **16** / append **4** / strict **3**，重叠 1（`pubchem_identity_layer.py`）；反向漏网 0 | H41c1–H41c10（10 条全成立） |
| **W41-D** 轨道层级声明 | 三条层级的排序迁移可不可传递 | 覆盖 237 / 103 / 73，三方交集 **48**；ρ(xTB,QM9)=**0.885628**、ρ(QM9,Batt)=**0.817674**、ρ(xTB,Batt)=**0.330371**（同一 48 化合物上 **0.538428**） | H41d1–H41d11（11 条 = 10 成立 + 1 已登记判否 H41d8） |

**合计 40 条判据 = 38 成立 + 2 已登记判否**（H41b5 / H41d8），全部在册、阈值不原地改。

## 3. 口径要点（读数前写死）

- **W41-A 只换问法，不换数据**：准入规则是「同一配置网格 + 剔除安慰剂/换表示/非本网格 + 重复集完整」，只读 W28–W32 逐重复表。**不得**用比值判据去救已被污染的池子。
- **W41-B 的双读数是硬条款**：相对变化 **0.2058863627 > 0.10** ⇒ 只能声明「方向稳健」，**不得**声明「量级稳健」；高介电族校正后 **更**分离（13.40 → 17.32），说明校正影响不是单向偏移。
- **W41-C 有三处更正**：机械证据下 append 计数是 **4** 不是 W40 手写分组的 3；真 pinned∩append 重叠是 **`pubchem_identity_layer.py`** 不是 `pubchem_liquid_window_harvest.py`；例外登记**不是豁免**，这 22 个 owner 重跑仍会弄脏工作树。
- **W41-D 三层两两都是 cross_level**（泛函 / 基组 / 溶剂化至少差一项），**同层级外部源数 = 0** ⇒ W40 登记的第 3 条（加权重前补同层源）**仍未满足**；外部层数值不入任何标签池或特征列。
- **名册分母 241 行**（`data/processed/dielectric_physical_features_v03.csv`）；xTB gap 有 4 行缺失，照实登记**不插补**。

## 4. 交付物

| 类别 | 路径 |
| --- | --- |
| 预注册 | `probes/w41_governance_prereg.json`（revision 2，`locked_before_run`） |
| 探针 | `probes/w41_ladder_admission.py`、`probes/w41_domain_ratio_robustness.py`、`probes/w41_exemption_admission.py`、`probes/w41_orbital_level_declaration.py` |
| 产物 | `probes/artifacts/w41_ladder_admission.csv`、`w41_ladder_admission_summary.csv`、`w41_domain_ratio_robustness.csv`、`w41_domain_ratio_clause.json`、`w41_exemption_admission.csv`、`w41_exemption_policy.json`、`w41_orbital_level_registry.csv`、`w41_orbital_pair_matrix.csv`、`w41_orbital_batt_hits.csv`、`w41_orbital_level_declaration.json` 及四份 `*_summary.json` |
| 图 | `probes/artifacts/w41_ladder_admission.png`、`w41_orbital_level_declaration.png` |
| 报告 | `reports/w41_ladder_admission.md`、`reports/w41_domain_ratio_robustness.md`、`reports/w41_exemption_admission.md`、`reports/w41_orbital_level_declaration.md` |
| 测试 | `tests/test_w41_ladder_admission.py`、`test_w41_domain_ratio_robustness.py`、`test_w41_exemption_admission.py`、`test_w41_orbital_level_declaration.py` |
| 导出 | `probes/export_week41_results.py` → `成果输出/week41` |

## 5. 下一份预注册要处理的（已登记）

1. **同层级外部源仍然缺位（W41-D 登记）**：三条轨道层两两都是 cross_level，若要给 HOMO/LUMO 通道加权，必须先补一个与 Batt ωB97X-V 同层级的独立源；PubChemQC 的入口问题（先 InChIKey→CID 再定位分片）仍未执行。
2. **xTB→Batt 的排序迁移弱（W41-D 登记）**：同一 48 化合物上 ρ(xTB,Batt) 仅 0.538、Pearson 0.088；任何用 xTB 作 Batt 代理的读数都要显式声明这一层差。
3. **例外准入的类别扩展要走预注册（W41-C 登记）**：新增例外只能落在三类之内；若确需第四类，先改 `probes/w41_governance_prereg.json` 的 evidence_rules 再登记。
4. **域比双读数已条款化（W41-B 登记，已落地）**：条款件 `probes/artifacts/w41_domain_ratio_clause.json` 已可被下游引用；后续任何域比读数必须携带两个值。