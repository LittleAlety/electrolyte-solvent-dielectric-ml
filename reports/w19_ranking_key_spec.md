# Week 19 · D6 —— 多目标排序键规范 v0（决策域 Pareto / Level-Diagram 排序键）

**状态**：v0，2026-09-28 拟。输入只含**已过门通道**；权重显式；示例排序被测试字面钉住（AF-13 同款纪律）。
**可执行实现**：`probes/w19_ranking_key.py`；**字面钉测试**：`tests/test_w19_ranking_key.py`。
**权威依据**：`E:/大二/d2qc/电解液（长期项目）/文献调研/重点且同向/Week19立项计划_文献驱动三线.md` §W19-4。

## 1. 定位：这是排序键，不是候选生成器

- **输入**：已过门通道的**分子级读数**（v0 = HOMO / LUMO 两个轨道通道）。
- **输出**：① 支配关系判定；② Pareto 前沿（可行集）；③ 加权排序键分数（前沿内部排序与平局裁决）。
- **明确不是**：不是生成模型、不产生新分子、不产生任何新性质预测值；分数是**集合相对**的排序量，不是物性值。
- 本件与实现**不拟合任何模型、不读任何大表、不写任何数据文件**：门槛表以字面量 + 出处冻结在模块里，import 时自检（`passed` 由 `measured` 与门规则**重新推导**，不是手抄）。

## 2. 生成闭环永久钉死（三条证据）

① **uniqueness 塌缩**：ElectrolyteGPT（JACS Au 2026，`au5c01628`）在 10 性质条件化下 uniqueness 塌到 **0.349**；
② **代理输出的审计缺口**：其 10 个性质**全部为代理输出、从未做分组审计**（never subjected to a group-split audit）；
③ **许可**：其数据许可为 **CC-BY-NC-ND 4.0**（不得改作，no derivatives）。

**制度结论（永久）**：本项目**不做生成闭环、不做候选生成器**；ElectrolyteGPT 的代理输出**永不作为训练数据、永不入任何池、永不进特征或交付包**；其字段设计可借鉴（思想不受版权保护），其数据与产物不可改造入库。

## 3. 输入通道表（本机从仓内文件实测，2026-09-28）

| 通道 | 判据（门） | 门方向 | 实测值 | 过门 | 进 v0 排序键 | 出处 |
| --- | --- | --- | --- | --- | --- | --- |
| ε 介电常数 | 分组 R² ≥ 0.60 | 越高越好 | **0.4766400383507876** | **未过** | **不进键** | `probes/four_channel_coverage_summary.json#pinned.dielectric_main_scoreboard_headline_r2`；门 0.60 见 `reports/dielectric_pool_expansion_audit.md:74` |
| η 黏度 | MAE < 0.15 log10(cP)（group_key） | 越低越好 | **0.17477197208762** | **未过** | **不进键** | `probes/viscosity_baseline_summary.json#primary_gate`；W18 行级解冻最好 0.15686276760094522 也未过（`reports/decisions_log.md` §28.38） |
| HOMO | MAE < 0.20 eV | 越低越好 | **0.19050925839013938** | **过门** | **进键（权重 0.5，方向 min）** | `models/homo_lumo_baselines.json#gate.per_target.HOMO.best_model_mae` |
| LUMO | MAE < 0.20 eV | 越低越好 | **0.13855083976437643** | **过门** | **进键（权重 0.5，方向 max）** | `models/homo_lumo_baselines.json#gate.per_target.LUMO.best_model_mae` |
| 氧化（自由能） | MAE < 0.15 eV | 越低越好 | **0.2905180517963865** | **未过** | **不进键** | `probes/four_channel_coverage_summary.json#pinned.redox_oxidation_mae_ev`；门 0.15 见 `probes/p4_redox_v2_summary.json#gate.threshold_mae` |
| 还原（自由能） | MAE < 0.15 eV | 越低越好 | **0.4096241620366996** | **未过** | **不进键** | `probes/four_channel_coverage_summary.json#pinned.redox_reduction_mae_ev`；门 0.15 见 `probes/p4_redox_v2_summary.json#gate.threshold_mae` |

**一句话**：六通道里**只有 HOMO / LUMO 两条过门**，v0 排序键因此只含轨道两维。三种门的**方向不同**（ε 是高者过的 R² 门；η / redox / 轨道是高者不过的 MAE 门），实现里逐通道用 `pass_when = below / above` 显式声明，绝不用一套方向套全部通道。

补充读数（不进键，仅登记）：IP 0.2010970559642009、EA 0.23415453202842548 也各自差 1.1 meV / 34 meV 未过 0.20 eV 门；且 IP 与 HOMO、EA 与 LUMO 高度共线（Pearson r = -0.9876 / -0.9513，`reports/homo_lumo_baselines.md` 标签空间诊断），本版不把它们当独立通道重复计权。

## 4. v0 权重（必须显式）

- 进键权重：**HOMO 0.5 / LUMO 0.5**（等权）。
- **为什么等权**：两个通道之间**没有任何实测的成本或收益比**可以据以加权；在没有证据时，等权是唯一不引入自由度的选择。任何非等权都必须先给出一条可证伪的理由（例如某个下游任务的灵敏度实测），否则就是隐式拍脑袋。
- 分数定义：对每个通道在**被评分行集内**做 min-max 归一到 [0,1]（方向按通道声明，1 = 最好；整列同值时取 0.5），再按权重线性求和。⇒ 分数是**集合相对排序量**，不是物性值、不得跨集合比较、不得当预测值引用。
- **权重与方向改动 = 预注册改动**：任何权重或 `direction` 调整都必须新钉一份预注册并重跑字面钉测试，留档之后才可生效；不许事后静默改数。

## 5. Pareto 前沿定义

- **支配（严格）**：行 a 支配行 b ⟺ 在所有键上 a **不劣于** b，且至少一个键上 a **严格优于** b。优劣方向按通道声明（HOMO 越小越好、LUMO 越大越好）。
- **前沿** = 不被任何其它行支配的行集合（非支配集），按输入序返回。
- **平局处理**：键向量完全相同的两行**互不支配**（严格优于一项不成立），两行都留在前沿；前沿内部与全表的先后再用分数 `(-score, name)` 裁定（名字升序），因此同分行次序是确定性的、可被测试钉死。
- **被支配行不隐藏**：`ranking_key_table` 仍给出其分数并标 `on_front=False`。**前沿是可行集，分数只是它的排序**；分数不得用来把被支配行抬进前沿。
- **缺失 / 非有限读数**：直接 `ValueError` 拒绝，不静默填 0（禁止把未知当最差）。

## 6. 适用域与失效区（ε > 60 高介电区）

- 读数（`probes/dielectric_onsager_delta_summary.json`）：ε > 60 区共 **5 个化合物**；Onsager 先验在该区**覆盖率 0/5**（`onsager_high_permittivity_coverage = {threshold: 60.0, row_count: 5, onsager_above_threshold: 0}`）；Δ-learning headline 臂在该区 **MAE 75.95675695251926**（偏置同值）。
- 结论：**高介电区在单分子描述符下不可解** —— 不是模型容量问题，是缺 Kirkwood g（取向相关）这一维；在获得该维之前，该区不接受任何排序结论。
- 对排序键的硬约束：① v0 **不含 ε**，因此不存在用不可信通道排序的问题；② 将来 ε 若过 0.60 门并要入键，必须先把该区显式声明为**域外**：`high_permittivity_excluded(eps) == True` 的行不得参与排序、不得进前沿，只能单列为待实验 / 待新物理维度。阈值以模块常量 `HIGH_PERMITTIVITY_EPS = 60.0` 钉住。
- 本件**不做分域记分牌的替换**：全域数字照报，域外声明在先（与既有适用域声明同款纪律）。

## 7. N9 依据（文献缺口与仓内实测并档）

- 文献自认缺口（`au5c01628`）：physics-informed descriptors that can implicitly capture intermolecular interactions。
- 仓内同向实测（`probes/dielectric_onsager_delta_summary.json`，并见 `reports/decisions_log.md`）：Onsager 反应场对**氢键缔合液偏低**（Kirkwood g 远大于 1）、对**离子液偏高**；且 ε > 60 区覆盖率 0/5。
- 并档结论：缺口那一维正是**隐式捕获分子间相互作用**的描述符。本排序键的适用域声明与此同源 —— 排序键**只在其过门通道的适用域内发言**，超域即沉默（域外标注，不给误导性排序）。

## 8. 复现与测试

- 实现：`.venv/Scripts/python.exe probes/w19_ranking_key.py`（打印示例排序表）。
- 测试：`.venv/Scripts/python.exe -m pytest tests/test_w19_ranking_key.py -q -p no:cacheprovider`。
- 示例（**合成夹具，数值任意、不含任何化学主张**）：`EXAMPLE_MOLECULES` 5 行 × 2 通道。
  - 默认键（0.5 / 0.5）排序：demo-v 0.7833333333333333 = demo-y 0.7833333333333333 > demo-x 0.5 = demo-z 0.5 > demo-w 0.41666666666666663；前沿 = {demo-x, demo-y, demo-z, demo-v}，demo-w 被 demo-y / demo-v 支配。
  - 权重改为 HOMO 0.9 / LUMO 0.1 后排序变为 demo-x 0.9 > demo-v 0.69 = demo-y 0.69 > demo-w 0.35 > demo-z 0.1 ⇒ 权重是显式的、可被测试直接推翻的。

## 9. 边界（不许省略）

- 排序键**不产生新数据**：它只用已过门通道的既有读数；六通道里只有 2 条过门，所以 v0 的决策域很窄，不得叙述成四通道综合排序。
- 分数是集合相对量、不是物性预测；ε / η / 氧化 / 还原未过门，**其数字不得进键、不得作排序依据**。
- 与文献的对齐纪律：10 篇扫描文献里 0 篇报告分组拆分 ε R²；本件不引用任何随机拆分文献数字做对照靶或晋升依据。
- 未来扩通道的唯一路径：先把该通道推过自己的门，再改本件并重钉预注册；**先加通道再加门是禁止的**。

## 10. v0 自检清单（照抄可实现口径）

- [x] 输入只含已过门通道（实现 `validate_keys` 对未过门通道直接 `ValueError`）。
- [x] 权重显式且和为 1（等权 0.5 / 0.5）。
- [x] Pareto 支配与平局处理有严格定义。
- [x] 失效区（ε > 60）声明在先，模块以常量钉住阈值。
- [x] 示例排序以字面量钉进测试，权重改动会让测试红。
- [x] 生成闭环三条证据与制度结论入册（本节 §2）。
