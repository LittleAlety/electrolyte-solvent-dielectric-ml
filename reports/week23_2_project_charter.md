# Week 23-2 立项章：Axis A `P_1` 首次实例化 —— GFN2-xTB ΔSCF 电离能 / 电子亲和能（气相 + 三档 ALPB）

- **性质**：新数据臂（Tier 1）。**不拟合新模型、不动任何冻结件、不占主记分牌 shot、不引用任何 Reaxys 数值**。
- **状态**：`locked_before_run`（预注册 `probes/w23_redox_dscf_prereg.json`，sha256 `70c355f59cf01103…`）
- **权威输入**：`docs/framework/ranking-electrolyte-materials-v2.md`（§3 Axis A `P_1` gas-phase redox thermodynamics、§4.1 方向量、W22 评审矩阵 A5）；`data/processed/w21_chemical_space_metadata.csv`（池与顺序）；**W23-1** `data/processed/w23_orbital_medium_layer.csv`（中性臂回归锚）；`data/processed/redox_merged.csv` 的 RX-392 分支（外部参考层，只作对照）
- **生成时间**：2026-10-02（本机）

## 0. 为什么开这一枪

四类核心数据（粘度、介电常数、HOMO/LUMO、**氧化还原电位**）里，本仓此前**唯一从未自算过**的就是最后一类：`four_core_key_registry.csv` 的 IP/EA 列全部来自外部参考层，仓内没有任何一条自己算出来的电离能或电子亲和能。W23-1 把 `P_2`（固定介电背景）补上了一半——但那是**轨道能**，不是**氧化还原量**。

框架 §3 Axis A 的 `P_1` 原文是「气相氧化还原热力学」，它和 `P_0`（Koopmans 轨道能）的差别恰好是**本仓此前的全部轨道数据都没做的那一步**：把 −ε_HOMO 换成 ΔSCF=`E(cation) − E(neutral)`。

它还回答一个**已经写进 W22 评审矩阵的悬案**。A5 条登记：

> 「还原轴结论只以有连续介质的层为载体。」

这句话此前是**断言**（因为气相阴离子是否束缚从未在本仓测过）。本臂把它变成**可证伪的判据**：如果气相阴离子多数不束缚、而水相显著下降，A5 成立；否则 A5 必须修订。这是本仓方法学主张（负结果进交付物）的又一次落地。

## 1. 设计（跑前锁定）

| 项 | 内容 |
| --- | --- |
| 池 | 冻结 ε 名册 **246 化合物**，顺序与构象种子与 W21 / W23-1 逐位同源（seed = 42 + row_index） |
| 臂 | **12 臂 / 化合物**：4 介质 × 3 电荷态（neutral `--uhf 0`、cation `net+1` `--uhf 1`、anion `net−1` `--uhf 1`） |
| 介质 | gas + ALPB 三档（与 W23-1 **同一隐式模型**）：thf (ε=7.58)、benzaldehyde (ε=18.0)、water (ε=80.4) |
| 总次数 | **2,952 次 GFN2-xTB**（12 × 246） |
| 口径 | **绝热**（三态各自 `--opt`）；`IP = E(cation) − E(neutral)`、`EA = E(neutral) − E(anion)` |
| 几何 | 完全复用 `probes/w21_li_coordination.py` 的 embed；三个电荷态**共用一个起始几何**，各自在 xTB 内弛豫 |
| 执行 | 分子级并行（ProcessPoolExecutor），单臂仍是冻结 runner + 单线程 xTB |

**冻结件保护（本臂唯一的代码风险点）**：开壳层需要一个 `--uhf 1` 的命令行，而 `xtb_optimisation_arguments` 是冻结函数、被 `tests/test_xtb_thread_determinism.py` 逐字钉死。因此**不改冻结函数**，而是新增兄弟函数 `xtb_open_shell_arguments`（`src/electrolyte_ml/xtb_runner.py`），冻结函数的输出与单测逐字不变。

## 2. 六条跑前锁定的假设

| id | 假设 | 判据 |
| --- | --- | --- |
| H1 | 溶剂化降低电离能 `dIP = IP(medium) − IP(gas) < 0` | 三档介质占比均 ≥ 0.90 |
| H2 | 溶剂化提高电子亲和能 `dEA > 0` | 三档介质占比均 ≥ 0.80 |
| H3 | `\|dIP\|` 随 ε 逐化合物单调递增（thf → benzaldehyde → water） | 占比 ≥ 0.60 |
| H4 | A5 可证伪形式：气相阴离子多数「不束缚」（阴离子最高占据轨道能 > 0） | 气相占比 ≥ 0.50 **且** 气相 − 水 ≥ 0.20 |
| H5 | dSCF IP 与 RX-392 参考层之间**量级偏差大而排序相关** | n = 10 交集上 `\|mean 有符号差\| ≥ 1.0 eV` **且** `Spearman ρ ≥ 0.60` |
| H6 | 回归锚：4 个介质的中性态与 W23-1 已提交层逐位一致 | `max\|Δ\| ≤ 1e-6 eV`，不通过则**本臂整体作废** |

H6 是**资格审查**：不通过则说明 IP/EA 的两个新电荷态与中性态不共享几何来源，整臂读数作废。

## 3. 读数清单

R1 IP/EA 四介质分布 ｜ R2 dIP/dEA 相对气相的符号与 ε 单调性（H1/H2/H3） ｜ R3 Koopmans 对照（dSCF vs −ε_HOMO / −ε_LUMO） ｜ R4 阴离子束缚签名计数（H4） ｜ R5 排序稳定性（四介质两两） ｜ R6 RX-392 外部对照（含**约定警告**） ｜ R7 中性臂回归锚（H6） ｜ R8 失败与重试登记

## 4. 交付物

`probes/w23_redox_dscf_prereg.json` / `probes/w23_redox_dscf.py` / `probes/w23_redox_dscf_summary.json` / `data/processed/w23_redox_dscf_layer.csv`（246 行 / 94 列） / `probes/artifacts/w23_redox_dscf_*.csv`（11 件） / `probes/artifacts/w23_redox_dscf_shift.png` / `tests/test_w23_redox_dscf.py` / `reports/w23_redox_dscf.md`

## 5. 口径纪律（写死，避免事后调整）

1. **绝热 ≠ 垂直**。本臂三态各自 `--opt`，是**绝热**口径；框架 §2.3 的 P1 是**垂直**三点法。两者**不得混比**，也不得与本仓历史 Koopmans 数值直接相减。
2. **层级是 GFN2-xTB 半经验**，不是 §7 要求的 DFT 级。本臂把 `P_1` 从「未执行」推到「已实例化（低层级）」，**不声称**替代 DFT 级 `P_1`。
3. **RX-392 是自由能约定**（`redox_free_ener.py`），本臂是**能量差**；H5 的偏差里含约定差，**不得**读成纯方法误差。
4. **净电荷非零化合物单独统计**。本轮冻结名册 246 条记录**全部**是净电荷为零的输入（离子液体以中性盐对形式入池），因此带电类分支样本为 0——这一点如实登记，不构成「跳过=通过」。
5. **阴离子束缚签名**只描述「阴离子 SCF 收敛后最高占据轨道能的符号」这一件事；半经验层没有弥散函数，它**不是**束缚能的严格判据。

## 6. 不做清单

- 不跑 DFT 级 `P_1`（ORCA / r2SCAN-3c 不在本仓工具链里）。
- 不做 `P_2` 的 SMD 级实现（ALPB 不是 SMD/CPCM）。
- 不补 `C_2`（显式微溶剂化）——需要新建团簇几何管线，是另一条臂。
- 不把 IP/EA 与 HOMO/LUMO 合成一条排序键去打分（§18 禁止构造武断综合分）。
- 不声称能回答 §10.3（阈值决策误差）。
- 不把 RX-392 / Batt 参考层折进任何训练池或标签。
