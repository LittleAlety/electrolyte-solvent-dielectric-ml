# W20-6a Org-Mol 溯源探针：源识别为受限汇编，三关全不过，判 inadmissible，不破上限

- **任务** `week20_w20_6a_orgmol_provenance_probe`｜**节号** §28.62｜**生成时间（本机 UTC）** 2026-09-28T04:47:45Z
- **性质**：**不拟合任何模型、不占 shot 编号、不产任何通道读数、不动任何冻结件**；`produces_reading = false`、`shot_number_taken = null`、`promoted = false`、`models_fitted = 0`、主记分牌本周 **0 次尝试**（累计 **11 次不变**）。本件产出的是**溯源判读**，不是读数。
- **权威输入**：`reports/week20_project_charter.md` §1 `W20-6a`、§3 预期管理、§4 不做清单、§6.1、附录；`probes/w20_orgmol_provenance.py`（W20-6a 登记态骨架，本 lane 把它推进到**可执行态**，**未重写**）。
- **机器可读产物**：`probes/w20_orgmol_provenance_prereg.json`（跑前锁定）、`probes/w20_orgmol_provenance_summary.json`（跑后落盘）。

## 1. 源识别：线索落地为哪一份东西

线索是「850+ 种有机液体、约 25 °C 的实验 ε」。逐条检索（arXiv / Crossref / Europe PMC / HuggingFace datasets 与 full-text / Zenodo / GitHub / Bing / DuckDuckGo）后，唯一命中的是 **Org-Mol** 表示模型：

| 项 | 值 |
| --- | --- |
| 论文 | High-accuracy physical property prediction for pure organics via molecular representation learning: bridging data to discovery |
| 出处 | *npj Computational Materials* **11**, 224 (2025) |
| DOI | `10.1038/s41524-025-01720-4` |
| arXiv | `2501.09896` |
| 预训练 | 6000 万条 PM6 半经验优化的小有机分子结构 |
| 上游框架 | Uni-Mol（`github.com/DeepModeling/Uni-Mol`） |

**Org-Mol 是模型，不是数据**；那 850+ 条近室温 ε 是它的**微调集**。论文正文（方法一节逐字）写：

> the dielectric constant near 25 °C collected from **ref. 53** and **ref. 54**

两条参考文献是：

| ref | 文献 | 许可 | 在本仓不做清单上？ |
| --- | --- | --- | :--: |
| 53 | Haynes, W. *CRC Handbook of Chemistry and Physics*（CRC Press, 2014） | **受限** | ✅（§4 明列 CRC） |
| 54 | Wohlfahrt, C. *2 pure liquids: Data*，Springer Materials `sm_lbs_978-3-540-47619-1_2`，© 1991 Springer-Verlag Berlin Heidelberg | **受限** | ✅（§4 明列 Landolt-Börnstein） |

⇒ 这条线索**没有引入新的一手测量**：它的 ε 值来自两份**受限汇编**，而这两份汇编**正是** W20 不做清单上点名「不为 ε 再买受限库」的同类源。

## 2. 三关判据（按序）

| 关 | 判据 | 读数 | 判 |
| --- | --- | --- | :--: |
| 1 licence | 从源自身许可文本读判词，逐行分类前必须先钉 | 汇编**未公开发布**（见下）；ε 值溯至两源**均受限** | ❌ **restricted** |
| 2 locator | 每个被接收行需 `DOI + 表/图定位` | 论文只在**系列级**引 refs 53 / 54，**无逐行定位** | ❌ **unreachable** |
| 3 first_hand | 定位到的文献须回一手源复核，不得采编译集自带元数据 | 第 2 关无行可回，且一手源**付费墙** | ❌ **unreachable** |

**第 1 关的决定性依据（论文自身 data availability，逐字）**：

> The data that support the findings of this study … are available via the referenced sources. **Complete fine-tuning datasets can be obtained upon reasonable request by contacting the corresponding authors.**

即：**完整微调集不公开发布**，只在「合理的请求」下由通讯作者提供。文章本体许可为 **CC BY-NC-ND 4.0**（正文 `rel="license"` 四处的落点），但**真正承载 ε 数值的那一层是受限汇编**，文章许可不能覆盖它。

## 3. 三档出口与计数（照实写，不编数）

| 出口 | 含义 | 计数 |
| --- | --- | ---: |
| `admissible` | 许可过、定位齐、一手复核有记录 | **0**（源不可得） |
| `needs_lead` | 许可过、定位缺或不完整 | **0**（源不可得） |
| `inadmissible` | 许可受限/未知，或落在窗口外 | **0**（源不可得；**源级判词为 inadmissible**） |

**「源不可得」是照实登记**：`summary.json` 里 `row_level_classification.status = "source_not_obtainable"`，三档计数均为 **0**——**不是**「跑了但三档都空」，而是**行级表拿不到、因此一行都没分类**。若有该表，第 1 关的 `licence_not_cleared` 是**致命理由**（`FATAL_REASONS`），所有行都会落 `inadmissible`。

**诚实降级**：即便拿到表，这类「汇集自文献」的 ML 集也只会是**线索集**（用于定位哪些化合物有值，再抓开放一手），**绝不作破上限**。本件因此**不产生任何新标签**。

## 4. 与 W17 十三源普查的关系

Org-Mol **确不在** W17 十三源普查表内（ThermoML、PubChem PUG-View、Europe PMC ×2、NIST WebBook、Zenodo 8252886、HuggingFace 热物性集、figshare、Dryad、foundry-ml、molssai、Na-ion boxes、ORD_reaction）。但**不在表内 ≠ 新源**：它的 ε 值溯至 **CRC + Landolt-Börnstein**，落在「同源同类、边际为负」的受限库一类。

## 5. 上限判词

**不破上限。** ε 标签上限 `161 → 157 → 153` **不动**，净新增上界 `+4` **不变**。理由：① 行级表不可得；② 即便可得，其来源为受限汇编，`licence_not_cleared` 致命 ⇒ 全部 `inadmissible`；③ 本件 `models_fitted = 0`、主记分牌 0 次尝试。

## 6. 照实登记「不可核」（不可核清单）

- **微调集内容不可核**：论文未发布，仅在「合理请求」下提供；本仓**未**（也不应擅自）以邮件方式索取，故行列内容一律 `not_verifiable_in_repo`。
- **「850+」的确切行数不可核**：未拿到表，`850` 只是论文/线索层陈述，**不采信为实测**。
- **逐行 `DOI + 表/图定位` 不可核**：论文未给，`locator = unreachable`。
- **一手复核不可核**：一手源（CRC / Landolt-Börnstein）付费墙，`first_hand = unreachable`。
- **是否含开放一手行不可核**：无法在未获表的条件下证否；即便有，也须先过许可关再谈。

## 7. 纪律

- `promoted = false`、`produces_reading = false`、`shot_number_taken = null`。
- 主记分牌本周 **0 次尝试**，累计 **11 次不变**。
- **未把任何外部行写入 `data/`**：本件只写 `probes/` 三个自产物与 `reports/` 一份报告。
- **不引用任何 Reaxys 数值**；**不为 ε 购买或抓取任何受限库**。
- 许可判词照实登记；判不清处一律写 `not_verifiable_in_repo` / `not_verifiable`，**不猜**。

