# Week 24 交付说明：把母体论文的十级台阶从 N=18 扩到 N=246，并把 `P_1` / `P_2` 抬到 DFT 层

本文件是 Week 24 导出包的入口。两条车道，**主记分牌本周 0 次尝试（累计仍 12）**，四个冻结读数
（`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`）
一律不动，七条红线逐条 sha256 复核。

## 0. 这一周补的是谁的缺口

母体论文《电解液溶剂氧化还原描述符的决策稳定性》（`E:\Claude Code\电解液溶剂-HB\论文\电解液溶剂氧化还原描述符决策稳定性_结题论文_v5.pdf`）
自己写明三处**样本量**缺口：核心集只有 **18** 个分子；Li⁺ 条件态只建在 **10** 个分子上；配位饱和（`C_1`/`C_2`）只有**单一代表分子**。
本仓恰好有它没有的东西：一个冻结的 **246 化合物名册**。Week 24 因此是「论文衍生扩样」，不是新模型周。

同时，本仓有两处登记把「DFT 级 `P_1` / `P_2`」写成了做不到：

| 文件 | 行 | 原登记 | 复核 |
| --- | --- | --- | --- |
| `reports/w21_framework_slot_map.md` | 48 | ORCA / r2SCAN-3c 不在本仓工具链里 | **假**，已更正 |
| `reports/week23_2_project_charter.md` | 65 | 不跑 DFT 级 `P_1`，理由同上 | **假**，已更正 |

## 1. 两条车道

### W24-1 · Axis B 条件态（`probes/w24_condition_redox.py`）

把框架 §3.2 里那条**从未自算过**的量补上：

```
DDG_ox^coord  = DG_ox^Li  - DG_ox^free
DDG_red^coord = DG_red^Li - DG_red^free
```

- 池：冻结 ε 名册 **246 化合物**，`seed = 42 + row_index` 与 W21 / W23-1 / W23-2 逐位同源；
- 复合物：`c1 = [LiM]+`（1:1，复用 W21 几何）+ `c2 = [Li(M)2]+`（**反式 2:1**，点反演构造，新）；
- 介质 4 档（gas / thf / benzaldehyde / water）× 态 3 个（cation / ref / reduced）= **24 臂**；
- 总计 **246 × 24 = 5,904 次 GFN2-xTB 优化**；
- 九条预注册假设 H1–H9，其中 **H7 是资格审查**：气相 `c1_ref` 必须与 W21 的 `total_energy_li_hartree` 逐位一致（容差 1e-9 Hartree）。

**口径警告（不可混比）**：W24-1 三态**各自 `--opt`**，是**绝热**量；母体论文的 `P_1` / `P_2` 是**垂直**单点。
因此两条台阶只比**符号、结构、`tau_b`**，不比绝对值。`C_2` 使用**一个确定性反式 2:1 起始构型**，
不是最低能异构体；框架 §3.2 明令禁止对不同化学计量 cluster 做 Boltzmann 平均。

### W24-2 · Axis A 的 DFT 级 `P_1` / `P_2`（`probes/w24_2_orca_dft.py`）

- 分子池：论文核心集 **18** ∪ 气相锚点物种，按 InChIKey 去重 = **28** 个分子；
- 每分子：1 次 GFN2 `--opt`（G1 几何）+ 3 次 GFN2 **垂直**单点 + **6 次 ORCA 单点**（2 介质 × 3 态）；
- ORCA 设定：`! r2SCAN-3c RIJCOSX TightSCF`，SMD 用 `CPCM(ACETONITRILE) + smd true + SMDsolvent "ACETONITRILE"`，
  回读 **Epsilon = 35.6880**，与论文 35.688 逐位一致；
- 主读数 = `FINAL SINGLE POINT ENERGY`；稳健性变体 = `Total energy after SMD CDS correction`；两条都落盘；
- 总计 **28 × 6 = 168 个 ORCA 单点**。

**三种跑中更正（都有实测留痕，写进立项章第 4 节）**：

1. 这台 Windows 构建的 ORCA 6.1.1 **把整份日志写到 stdout、不生成 `.out`**，只生成 `.gbw` / `.property.txt` / `.bibtex`；
   首版探针只读 `.out`，于是六臂全判 `orca_failed`。已改为 **stdout 为主、`.out` 为非空回退**。
2. ORCA 6 的 `ORBITAL ENERGIES` 表**不标注 HOMO/LUMO**，非限制性计算每个自旋一张表；
   前缘轨道改为**按占据数列推**（占据 > 0.5 的最高者为 HOMO，≤ 0.5 的最低者为 LUMO）。
3. **并行 r2SCAN-3c + CPCM/SMD 带电溶质在本机会 MPI 死锁**：同一输入 `%pal nprocs 4` 停住不动
   （4 个 rank 在 12 分钟里只增加约 17 s CPU），改成 `%pal nprocs 1` 后 **258.9 s 正常终止**。
   最终以串行多 worker 运行，并内置「并行失败即自动降级串行重试一次」。

## 2. 复现

```powershell
# W24-1（Tier A，xTB 条件态）
.\.venv\Scripts\python.exe probes\w24_condition_redox.py --workers 12 --timeout 3600
.\.venv\Scripts\python.exe probes\w24_condition_redox.py --from-layer
.\.venv\Scripts\python.exe probes\w24_condition_redox.py --report-only

# W24-2（Tier B，ORCA DFT 级）；--nprocs 1 是本机唯一稳定的形式，见上文更正 3
.\.venv\Scripts\python.exe probes\w24_2_orca_dft.py --workers 3 --nprocs 1 --maxcore 800 --timeout 1200
.\.venv\Scripts\python.exe probes\w24_2_orca_dft.py --from-layer
.\.venv\Scripts\python.exe probes\w24_2_orca_dft.py --report-only

# 图与导出
.\.venv\Scripts\python.exe probes\w24_condition_redox_figures.py
.\.venv\Scripts\python.exe probes\export_week24_results.py --overwrite
```

两条车道都默认**断点续跑**：每完成一个分子就把整条记录追加到
`probes/artifacts/w24_condition_redox_records.jsonl` / `probes/artifacts/w24_2_orca_records.jsonl`，
重跑自动跳过已完成分子（`--no-checkpoint` 可关）。这是长臂的**必需**能力：本周已经因为
一个格式串缺陷与一次 MPI 死锁各中断过一次，靠它没有丢任何已完成分子的算力。

## 3. 纪律

- **不引用任何 Reaxys 数值**；`RX-392` / `Batt-P30K` / THEMol 只作参考层，不进任何训练池或标签；
- **不给任何综合电解液总分**（框架 §18）；
- 负结果照实入交付物：每条臂按「预注册 → 探针 → 测试 → 报告 → 导出 → 提交」推进；
- 冻结红线（逐条 sha256 复核，见 `week24_summary.json` 的 `frozen_red_lines`）：
  `data/dielectric_v03.csv`、`probes/l3_stage1_pilot_pool.csv`、`probes/l3_backvalidation_prereg.json`、
  `data/processed/dielectric_observations_v11plus.csv`、`probes/dielectric_r2_levers_prereg.json`、
  `data/viscosity_v01.csv`、`data/processed/w21_li_coordination_layer.csv`。

## 4. 产物清单

| 路径 | 内容 |
| --- | --- |
| `data/processed/w24_condition_redox_layer.csv` | W24-1 逐分子逐臂层（246 行） |
| `data/processed/w24_2_orca_dft_layer.csv` | W24-2 逐分子逐臂层（28 行） |
| `probes/w24_condition_redox_summary.json` | W24-1 全量读数与 H1–H9 裁决 |
| `probes/w24_2_orca_dft_summary.json` | W24-2 全量读数与 O1–O8 裁决 |
| `reports/w24_condition_redox.md` | W24-1 自动结题报告 |
| `reports/w24_2_orca_dft.md` | W24-2 自动结题报告 |
| `reports/week24_project_charter.md` | W24-1 立项章（含跑前修订 `amendment_before_run`） |
| `reports/w24_2_orca_dft_charter.md` | W24-2 立项章（含三条跑中更正） |
| `probes/artifacts/w24_*.csv` / `w24_2_*.csv` | 台阶表、位移律、闭式恒等式、Born 律、状态识别、抽样 sd、论文缺口映射、QC |
| `probes/artifacts/w24_condition_redox_ladder.png` | 五面板图（全中文标签） |
| `tests/test_w24_condition_redox.py` / `tests/test_w24_2_orca_dft.py` | 回归与纪律守卫 |

## 5. 与母体论文的关系（一句话）

母体论文的结论是在 **N=18（`C` 台阶 10–12）** 上得到的；Week 24 把同一组台阶放到 **N=246** 上重取一次，
并把 `P_1` / `P_2` 抬到**同一层级**（r2SCAN-3c）以搭上那座此前缺失的**尺度桥**。
两条台阶的**符号与结构**若在 13.7 倍样本量上仍成立，母体论文的结论就从「单点证据」变成「规模化证据」；
若不成立，也是一条必须在交付物里写清楚的负结果。

## 6. 跑后修复登记（两处「只有真跑才暴露」）

两条车道各自在首跑后暴露了缺陷。**判据一个没改**，改动全部落在解析与流水线上；两处都留了证据与钉子。

### W24-1 · 24 个 Li 列全空 → H2 被算成假阴性

- **症状**：首跑 5,904 个臂算完，layer 的 **24 个 `*_li_q` 列全部为空**，H2 的配对数 n = 0，被记成「判否」。
- **根因**：`probes/w23_redox_dscf.py::parse_arm` 逐字段重建 payload，把 `w21.parse_arm` 刚算出的
  `li_mulliken_q` / `li_min_dist_A` / `li_nearest_atom` **丢掉了**；本臂 24 个臂全部经过这个 wrapper。
- **修法**：补回三个字段（三行）+ 两条测试钉子（wrapper 字段传递 / live 列必须填满所有 `ok` 臂）。
- **为什么重跑**：首跑 checkpoint 里**没有几何**（同一个 wrapper 也丢了 `optimized_xyz`），没有可补单点的冻结几何。
- **重跑可采信**：`probes/verify_w24_firstpass_reproduction.py` 逐列比对首跑与重跑 layer ——
  **45,018 个「缺陷不可能触达」的单元逐位全同、0 差异**，唯一系统差异是 Li 列填充 0 → 5,227（恰等于 `ok` 臂数）。
  挂钟 1,800.3 s，H1/H3–H9 裁决一条未变。
- **修复后的真读数**：H2 **判否** —— 达到 0.5 e 的化合物占比 `c1` = **0.340**（n = 209，气相）、`c2` = **0.258**（n = 213），
  阈值 0.50，论文 11/12。**这是本臂最值钱的一条负结果**：在 246 个候选溶剂上「还原时电子半数落到 Li 上」是约 1/3 的少数行为，不是普遍行为。
  但论文的 11/12 建在**挑选过的 12 个体系**上，本臂是**无量纲普查**，两者不是同一件事。

### W24-2 · 84 个 GFN2 垂直臂误判 + 修复分支自身崩溃

详见 `reports/w24_2_orca_dft_charter.md` §9 与 `reports/decisions_log.md` §28.77。三条：

1. 垂直单点**不写 `.xtboptok`**，而哨兵只认那个文件 → 84 个 GFN2 垂直臂全判 `xtb_failed`；
2. 终止横幅在本机 xTB 打在 **stderr** 而非 stdout → 第一版修复**仍然全判失败**；
3. `--repair-gfn2` 分支 `UnboundLocalError`（`workers` 未绑定）且**缺 `return`**（会掉进 168 个 ORCA 主跑）。

修完 GFN2 垂直臂 **84/84 `ok`**，**O7（xTB↔DFT 桥）由 `no_data` 变为成立**（`rho = 0.8687`，偏差 **-4.816 ± 0.580 eV**），
O2 随之由「判否」变为成立（其输入正是先前为空的 `gfn2_ip_gas_eV`）。

### 一处 QC 排除（不改判据）

W24-2 的 `nitrogen dioxide` 六臂全失败：NO2 是稳定自由基，预注册的中性态闭壳单重态对它物理上不可能
（ORCA 原文 `multiplicity (1) is odd and number of electrons (23) is odd`；改 `M2` 后正常终止）。
**不改预注册多重度**，该分子按 QC 排除，所有 `n = 27` 的读数如实标注来源，作业台账 162 成功 / 6 失败 / 168 计划闭合。

## 7. 跑后追加产物

| 路径 | 内容 |
| --- | --- |
| `probes/artifacts/w24_2_orca_bridge.png` | W24-2 四面板图（桥散点 / 锚点 MAE / 台阶位移 / 裁决板） |
| `probes/w24_2_orca_dft_figures.py` | 上图只读生成脚本 |
| `probes/artifacts/w24_2_no2_probe.log` | NO2 多重度失败的复现日志 |
| `probes/verify_w24_firstpass_reproduction.py` | 首跑 / 重跑逐列比对器 |
| `probes/artifacts/w24_condition_redox_layer_firstpass.csv` | 首跑 layer（缺陷证据：24 个 Li 列全空） |
| `probes/artifacts/w24_condition_redox_records_firstpass.jsonl` | 首跑 checkpoint（同上） |
| `probes/artifacts/w24_firstpass_reproduction.csv` / `.json` | 比对结果（0 差异 + Li 填充统计） |


## 8. 论文交付（Week 24 结题稿 v2）

| 路径 | 内容 |
| --- | --- |
| `paper/paper_zh_draft_v2.md` | 全文 Markdown（19 图 / 15 表 / 10 章）。主线＝**描述符决策稳定性**：层级伪影、轴锁定分歧与筛查可用性 |
| `paper/build_paper_v2.py` | 装配脚本：把 v1 稿的 §3.1–3.14、§4.1–4.5 与新写的 §1、§2.9、§3.15–3.20、§4.6–4.7、§5 与附录拼成 v2 |
| `paper/make_paper_docx.py` | 渲染脚本：标题样式 / 表格 / 19 张图按序插入，CJK 字体（宋体正文、黑体标题） |
| `paper/_v2_*.md` | 装配用的分节片段（head / front / sec29 / body_a / body_b / disc_extra / concl / appendix） |

- **成品 docx**：`成果输出/论文_电解液溶剂筛选中的描述符决策稳定性.docx`（3,895,232 B，sha256 `050ceed915bbaa843caecec62fca22dc81e868a72e58930cc841d6e0d2a27919`），19 张内嵌图、15 张表、54 个标题。
- **重新生成**：`python paper/build_paper_v2.py` → `python paper/make_paper_docx.py`（docx 渲染需 `python-docx`，项目 venv 未装，使用捆绑运行时 Python）。
- **口径**：§3.18–§3.20 是后验再分析，正文与附录 B 已逐条标注「不得引用为预注册结论」，且不占 shot；四个冻结读数不动。
- **与母体论文的关系**：同一套 `P`/`C` 台阶与 `tau_b` 口径，把 N=10–22 的挑选样本放大到 N=246 普查；母体论文读数保持原位、不被修订（§4.7 三条「不宣称」）。
