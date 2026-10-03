# Week 38 立项章：把「拒答」升级成有保证的推荐集合，并把残差钉到物理形式上（全部后验，不占 shot）

**日期**：2026-10-03
**上一轮**：W37（README §11 第 16/17/18 条收口）
**本轮范围**：四条 lane + 一条治理收口。**全部是后验读数 / 治理件，不拟合主记分牌臂。**
**shot 账本**：**本轮 0 shot，累计仍 19**。
**四个冻结读数**：`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` /
`0.6216672295270079`，本轮**一个都不动**。

---

## 1. 为什么是这四条

W37 把 §11 清空之后，仓库第一次出现「治理件齐了、但科学问题没有新进展」的状态。本轮回答
四个**已经在盘上、却从未被问过**的问题：

1. **拒答队列是黑白的，能不能变成灰的？** 现有口径把「不可判定」整族踢出（W33-A 门禁、
   W35-A 注册表），但一个既不能预测、也不能丢掉的化合物，正确做法是给它一个**带覆盖保证的
   区间**并据此决定「推荐 / 不推荐 / 拒答」。这是保形预测（conformal prediction）的标准语汇，
   本仓从未使用，而 OOF 预测行（`dielectric_observations_benchmark_predictions.csv`，98,580 行）
   已经在盘上——**不需要重拟合**。
2. **「结构≠功能」我们只有定性的句子，没有定量的谱。** W18 的分域记分牌说明了域内域外精度差，
   但没有回答「长得像的分子到底差多少」。指纹近邻的标签差谱可以直接量出来，并为分域声明
   （把 6 个自缔合质子液声明为域外）提供方法学先例式的证据。
3. **母体论文与 GSDS 共同的诊断——「单分子描述符传不了分子间关联」——从未在我们自己的
   数据上被检验过。** 表里已有 `dipole_D` 与 `mu_sq_over_Vm`，Kirkwood–Onsager 关系可以直接算，
   残差就是取向相关因子 g 的代理。可证伪预测：**残差集中在自缔合质子性液体上**。
4. **README §11 最后一条未处理项（导出重写时间戳使工作树变脏）** 卡着 AF-12：
   只要它不修，「干净重导」跑完交付字节坐标就失效。

一句话：**W37 把册子接上机器，W38 把机器接上物理与保证。**

## 2. 四条 lane

| lane | 回答 | 做法 | 判据 |
| --- | --- | --- | --- |
| **W38-A** 保形筛选举荐 | 拒答能不能变成带保证的短名单 | 用 `grouped` 协议的 OOF 预测行做**化合物级 split-conformal**（半数化合物校准、半数评估），给出区间与「推荐 / 未决 / 拒答」三值短名单 | H38a1–H38a5（5 条） |
| **W38-B** 结构≠功能反向检索 | 指纹相近的分子，标签能差多少 | 241 个化合物的 Morgan-Tanimoto 最近邻标签差谱，**双向**检索（像而不同 / 不像而同） | H38b1–H38b4（4 条） |
| **W38-C** Onsager/Kirkwood 残差诊断 | 缺的那一维是不是取向相关 g | 令 `L(eps) = (eps-1)(2eps+1)/(9eps)`，在给体数 `hbd == 0` 的域上过原点拟合 `L ~ mu_sq_over_Vm`，残差比即相对 g | H38c1–H38c4（4 条） |
| **W38-E** 时间戳脏树收口 | 干净重导为什么不干净 | 把 `generated_at_utc` / `elapsed_seconds` 从被跟踪 summary 挪进派生的 `*_run_meta.json`，导出器与测试不再写跟踪件 | H38e1–H38e4（4 条） |

合计 **17 条判据**。W38-D（数据侦察）由子代理并行执行，产出登记报告，不设数值判据。

### W38-A 的口径要点（必须在读数前写死）

- **校准/评估按化合物切分**，不按行切分：行级切分会把同一化合物的行同时放进两侧，
  校准集与评估集不再可交换，覆盖率保证失效。切分种子按 repeat 固定（`2026 + repeat`）。
- **主读数**用 `Physical` 单表示（与冻结端点同表示）；`Morgan+Physical` 作对照。
- 三值短名单的阈值取 `tau = 15` 与 `tau = 30`（与既有 AUC 口径同轴，不新造阈值）。
- **覆盖率是「目标值落在区间内」的行份额**，在**评估侧**化合物上计算，校准侧不参与读数。
- 本件**不重拟合任何模型**，只读盘上预测行 ⇒ 后验读数、0 shot。

### W38-C 的口径要点

- `x = mu_sq_over_Vm` 的单位未知，因此斜率 s 由数据拟合、g 只报**相对值**：
  `g_rel = (L/x) / median_{hbd==0}(L/x)`，于是非给体域的中位数恰为 1——这是**定义**，不是结果。
- 域划分是**机械规则**（`hbd == 0` / `hbd >= 1`），不许按 ε 大小挑样本。
- 高 ε 自缔合族用**机械阈值** `eps >= 60` 定义（预期落在那 6 个化合物上），不手写名单。

## 3. 交付物

| 类别 | 路径 |
| --- | --- |
| 探针 | `probes/w38_conformal_shortlist.py`、`probes/w38_structure_function.py`、`probes/w38_onsager_residual.py`、`probes/w38_summary_timestamp.py` |
| 产物 | `probes/artifacts/w38_conformal_*.csv`、`probes/artifacts/w38_structure_*.csv`、`probes/artifacts/w38_onsager_*.csv`、`probes/artifacts/w38_timestamp_*.csv` |
| 图 | `probes/artifacts/w38_conformal_coverage.png`、`probes/artifacts/w38_structure_function.png`、`probes/artifacts/w38_onsager_g.png` |
| 报告 | `reports/w38_conformal_shortlist.md`、`reports/w38_structure_function.md`、`reports/w38_onsager_residual.md`、`reports/w38_timestamp_closeout.md` |
| 测试 | `tests/test_w38_conformal_shortlist.py`、`tests/test_w38_structure_function.py`、`tests/test_w38_onsager_residual.py`、`tests/test_w38_summary_timestamp.py` |
| 导出 | `probes/export_week38_results.py` → `成果输出/week38` |

## 4. 边界与不做清单

- **不占 shot**：不拟合主记分牌臂、不新增特征列、不改 `METRIC_NAMES`、缺行不插补。
- **不把保形区间当置信区间**：保形给的是**边际覆盖**，不是给定化合物上的后验概率；
  报告必须并报「区间宽度中位数」与「未决份额」，否则覆盖率单读会被误读。
- **不把相对 g 当绝对 Kirkwood g**：`g_rel` 的单位被斜率吸收，只可用于**域间比较**，
  不得与文献的 g 绝对值对照。
- **不把结构≠功能的极值对当反例定理**：那是**提示性证据**（n 有限、单一描述符集），
  用于支持分域声明，不用于宣称某个分子「不可预测」。
- **红线不变**：Reaxys 数值不入任何池；THEMol 只留 `data/raw/`；Batt-P30K 是唯一可商用第三方线。
- **不做**：不重跑已被证否的路线（换拟合器 / 网络叠加 / 外来化学空间 / η 行级解冻）；
  不把 W31 `0.622389` 与 W32 `0.626589` 读作新纪录。