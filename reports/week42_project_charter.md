# Week 42 立项章：把第三外部轨道层与偶极三源接进来（计算密集型四 lane）

**日期**：2026-10-04
**上一轮**：W41（四条治理 lane 合并交付；README §11 第 33–35 条登记）
**本轮范围**：W42 是**计算密集型周**。W41-D 登记的三条欠账（item 33 缺同层级外部轨道源、item 34 xTB→Batt 迁移弱、item 28/30 偶极 ~0.4 D 偏置来源未追溯）本轮各由一条**只读离线计算 lane** 处理：W42-A 四层轨道迁移网络、W42-B isotonic 代理上界、W42-C 偶极三源回归分解、W42-D 抽样律与域比重抽。
**shot 账本**：**本轮 0 shot，累计仍 19**。四条 lane 全是后验/只读计算，不拟合任何主记分牌臂。
**四个冻结读数**：`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`，本轮**一个都不动**。

---

## 1. 为什么把这一轮做成「计算密集型」

W41 把四条**规则**写成了机器件，但它留下的是一个更硬的问题：**第三外部轨道层（PubChemQC）已经在盘上，却还没有被接进网络**。接进来意味着一次成规模的计算：

- 四层覆盖与全部 15 个交集；
- 6 个两两序列的排序/量级迁移，每对配 2000 次成对 bootstrap 与 2000 次置换零分布；
- 四个三角形的非传递闭合；
- xTB→Batt 的保序（isotonic）校正 + 5 折 CV + 三档阈值 AUC + 2000 次重拟合 bootstrap；
- 三源偶极的两两 bias/MAE、三源 OLS 归因、Bland–Altman 一致性界限；
- 6 条序列 × 5 个样本档 × 1000 次无放回重抽的抽样律拟合，加上域比的 2000 次 bootstrap 与 2000 次置换。

因此本轮不放治理条款，而是**把计算本身作为交付**：四条 lane 共用 `probes/w42_common.py` 的装载与重抽层，全部只读、全部可机械复跑。

| lane | 回答 | 登记来源 |
| --- | --- | --- |
| W42-A 四层轨道迁移网络 | 第三外部层接进来后，四层覆盖/交集/迁移/闭合各是多少 | item 33 |
| W42-B isotonic 代理上界 | xTB 当 Batt 代理的样本外上界是多少 | item 34 |
| W42-C 偶极三源分解 | ~0.4 D 偏置出在方法层还是某一个源 | item 28 / 30 |
| W42-D 抽样律 + 域比重抽 | 抽样律在四层轨道对上是否仍成立；域比的重抽区间 | W32-A / W40-C |

## 2. 四条 lane 的判据与读数

| lane | 回答 | 关键读数 | 判据 |
| --- | --- | --- | --- |
| **W42-A** 四层迁移网络 | 四层覆盖、15 交集、6 对迁移、4 三角形 | 覆盖 **237/103/205/73**、四路交集 **48**；ρ(QM9,PubChemQC)=**0.9823**（near_same_level）、ρ(xTB,Batt)=**0.3280**；最大三角形 gap **0.4897**（断链在 xTB–Batt） | H42a1–H42a13（13 全成立） |
| **W42-B** isotonic 代理上界 | 保序校正的样本内/样本外保真度 | ρ raw **0.3280** → 样本内 **0.5461**、CV **0.4150**；中位数二分 AUC raw **0.6922** → CV **0.7305**；代理保真度比 **0.3704** | H42b1–H42b10（10 全成立） |
| **W42-C** 偶极三源分解 | 偏置落在哪一层 | QM9−PubChemQC bias **−0.0341 D**（CI 含 0）；our−QM9 **+0.3945 D**、our−PubChemQC **+0.5130 D**；三源 OLS R² **0.6515**、定位比 **0.7691** | H42c1–H42c11（11 全成立） |
| **W42-D** 抽样律 + 域比重抽 | s0 与域比重抽区间 | 6 条曲线最大 rmse **0.0084**；Spearman(s0,1−τ)=**0.9429**；域比 **2.5817133417**、CI **[2.1220,3.2271]**、置换 p **0.0005** | H42d1–H42d11（11 全成立） |

**合计 45 条判据全部成立**（本轮无新增判否）；阈值在预注册 `probes/w42_registry_transfer_prereg.json` 里跑前写死。

## 3. 口径要点（读数前写死）

- **near_same_level 不是 same_level**：QM9 与 PubChemQC 同泛函（B3LYP）、同相（气相），但基组（6-31G(2df,p) vs 6-31G*）与几何（B3LYP vs PM6）不同，故只判 `near_same_level`；strict same_level 源数仍为 **0**。
- **isotonic 的样本内抬升来自并列归并**：单调变换在无并列时不改变 Spearman，引用必须用 CV 值；校正后的值不得当标签、不得入特征列。
- **偶极偏置只归因、不修数**：本轮不修改名册偶极列、不插补；外部层数值仍只作只读对照。
- **抽样律与域比是相关读数不是因果**；`g_rel` 只可域间比较，不与文献 g 绝对值对照。
- **名册分母 241 行**（`data/processed/dielectric_physical_features_v03.csv`）；四层各有缺行，照实登记**不插补**。

## 4. 交付物

| 类别 | 路径 |
| --- | --- |
| 预注册 | `probes/w42_registry_transfer_prereg.json` |
| 共享计算层 | `probes/w42_common.py` |
| 探针 | `probes/w42_orbital_transfer_network.py`、`w42_proxy_calibration.py`、`w42_dipole_sources.py`、`w42_sampling_law.py` |
| 产物 | `probes/artifacts/w42_*.csv`、`w42_near_same_level.json`、`w42_dipole_attribution.json`、`w42_*.png`、四份 `*_summary.json` |
| 报告 | `reports/w42_*.md`、本立项章、`reports/week42_delivery_readme.md`、`reports/work_log_week42.md` |
| 测试 | `tests/test_w42_*.py`（四件） |
| 导出 | `probes/export_week42_results.py` → `成果输出/week42` |

## 5. 边界（本轮明确不做）

- 不把任何外部层数值写进标签池或特征列；不用 isotonic 校正值替换 Batt 标签。
- 不把 near_same_level 升格为 strict same_level；不让同泛函声明外推到溶剂相 ωB97X-V 层。
- 不修数、不插补偶极列；不新增主记分牌臂、不改 METRIC_NAMES、不占 shot。
