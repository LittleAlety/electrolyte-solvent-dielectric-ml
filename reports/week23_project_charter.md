# Week 23 立项章：Axis A `P_2` 首次实例化 —— ALPB 介电阶梯下的轨道条件位移

- **性质**：新数据臂（Tier 1）。**不拟合新模型、不动任何冻结件、不占主记分牌 shot、不引用任何 Reaxys 数值**。
- **状态**：`locked_before_run`（预注册 `probes/w23_orbital_medium_prereg.json`）
- **权威输入**：`docs/framework/ranking-electrolyte-materials-v2.md`（§3 Axis A `P_2` fixed-background continuum、§3 Axis B `C_1`、§11 X2）；W21 交付 `data/processed/w21_li_coordination_layer.csv`（气相回归锚）；`data/processed/w21_chemical_space_metadata.csv`（池与顺序）
- **生成时间**：2026-10-02（本机）

## 0. 为什么开这一枪

框架的 §3 Axis A 里有三个槽位：`P_0`（便宜标量代理，在役）、`P_1`（气相氧化还原热力学，未执行）、`P_2`（**固定背景连续介质**，未执行）。W21 的 Tier 3 把 Axis B 的 `C_1`（Li⁺ 配位条件态）在 GFN2-xTB 层级实例化了，但**气相单点仍是本仓唯一的轨道数**。

对电解液溶剂筛选来说这不是小事：**决定氧化稳定性的不是气相 HOMO，而是溶剂化后的 HOMO**。整个仓的便宜层都缺这一维，而它是四类核心数据（粘度、介电常数、HOMO/LUMO、氧化还原电位）里最便宜可补的一环。

同时它还回答一个**纯科学问题**：把分子丢进介电背景，轨道能怎么动？这是个有明确符号预言（HOMO 上移、LUMO 下移、gap 收窄）且随 ε 单调的可证伪命题，正好适合本仓"预注册 + 判否也写进交付物"的方法学。

## 1. 设计（跑前锁定）

| 项 | 内容 |
| --- | --- |
| 池 | 冻结 ε 名册 **246 化合物**，顺序与构象种子与 W21 逐位同源（seed = 42 + row_index） |
| 臂 | **8 臂 / 化合物**：气相 free、气相 Li⁺（回归锚）+ 2 态 × 3 介质 |
| 介质 | ALPB 三档、**同一隐式模型**：thf (ε=7.58)、benzaldehyde (ε=18.0)、water (ε=80.4) |
| 总次数 | **1,968 次 GFN2-xTB**（8 × 246） |
| 几何 | 完全复用 `probes/w21_li_coordination.py` 的 embed / 基序分类 / Li 放置，**不新建几何构造代码** |
| 执行 | 分子级并行（ProcessPoolExecutor，10 并发），单臂仍是冻结 runner + 单线程 xTB |

**为什么是这三档 ε**：thf 与 ElectrolyteGPT 的 DFT 协议溶剂（SMD(THF)）同名；benzaldehyde 是 xTB ALPB 溶剂表中最接近参考层 Batt SMD(ε=18.5) 的一档；water 是表内高介电端。三档同一隐式模型，因此 ε 单调性检验不被"换模型"污染。

## 2. 五条跑前锁定的假设

| id | 假设 | 判据 |
| --- | --- | --- |
| H1 | 隐式溶剂使 HOMO 上移、LUMO 下移（gap 收窄） | 6 个"态 × 介质"组合里，占比 ≥ 0.80 |
| H2 | 位移随 ε 逐化合物单调（三档严格递增） | 占比 ≥ 0.60，homo 与 \|gap\| 各自判定 |
| H3 | 介质位移是二阶效应 | var(Δmedium)/var(gas) < var(ΔC1)/var(gas)（homo） |
| H4 | 介质变化**保持**排序（与 C_1 摧毁 LUMO 排序对照） | ρ(gas, medium) ≥ 0.90，homo 与 lumo、三档介质全部成立 |
| H5 | 几何同源回归锚：重算气相与 W21 已提交层逐位一致 | 全部 246 化合物 max\|Δ\| ≤ 1e-6 eV |

H5 是**资格审查**：不通过则本臂整体作废（否则三档位移会混入构象漂移）。

## 3. 读数清单

R1 三档位移分布 ｜ R2 ε 单调性（逐化合物 + 符号检验） ｜ R3 排序稳定性（气相→介质、介质两两） ｜ R4 态 × 介质 均值表 ｜ R5 §9 Batt 子集九层并排 ｜ R6 gap 与 v03 物理块一致性 ｜ R7 Li⁺ 臂质控（与 W21 同判据） ｜ R8 失败与重试登记 ｜ R9 气相回归锚证据表

## 4. 交付物

`probes/w23_orbital_medium_prereg.json` / `probes/w23_orbital_medium.py` / `probes/w23_orbital_medium_summary.json` / `data/processed/w23_orbital_medium_layer.csv` / `probes/artifacts/w23_orbital_medium_*.csv` / `probes/artifacts/w23_orbital_medium_shift.png` / `tests/test_w23_orbital_medium.py` / `reports/w23_orbital_medium.md`

## 5. 不做清单

- 不跑 DFT（`P_1` 气相 DFT、`P_2` 的 SMD 级实现仍空着）；本臂只推半经验 + ALPB。
- 不补 `C_2`（显式微溶剂化）——那是另一条臂，需要新建团簇几何管线。
- 不把介质位移与配位位移合成一条排序键去打分（§18 禁止构造武断综合分）。
- 不声称能回答 §10.3（阈值决策误差）：仓内仍没有来自外部设计要求的 HOMO/LUMO 阈值。
- 不把「重算气相」当新测量——它与 W21 同协议同种子，只能当回归锚。
