# Week 24-2 立项章：Axis A 的 `P_1` / `P_2` DFT 级首次实例化 —— ORCA 6.1.1 r2SCAN-3c 三态垂直 ΔSCF

- **性质**：新数据臂（Tier 1）+ 论文衍生扩样 + **登记更正**。不拟合新模型、不动任何冻结件、**不占主记分牌 shot（本周 0，累计仍 12）**、不引用任何 Reaxys 数值。
- **状态**：`locked_before_run`（预注册 `probes/w24_2_orca_dft_prereg.json`，sha256 `ecc63190d2c6d8e385aadb6916fa607130a0e0b66b27636192edcf509edc9228`）
- **生成时间**：2026-10-02（本机）
- **与 W24-1 的关系**：W24-1（`probes/w24_condition_redox.py`）在 **GFN2-xTB 层**把 `C_1` 氧化还原臂与 `C_2` 显式微溶剂化臂实例化到 **N=246**；本件把 `P_1` / `P_2` 抬到 **DFT 层**，但只覆盖母体论文的核心集。两件互补，绝不混比。

## 0. 这一枪为什么开

母体论文《电解液溶剂氧化还原描述符的决策稳定性》的整条台阶链 `P_0 -> P_1 -> P_2` 中，`P_1` / `P_2` 是 **r2SCAN-3c** 级量。本仓到 W23-2 为止只把 `P_1` 建在 **GFN2-xTB 半经验层**（W23-2 / W24-1），于是两条台阶**层级不同**：符号与结构可以比，**数值不能比**。这是本仓与母体论文之间唯一还没搭上的那座桥。

更关键的是，本仓有两处登记把这座桥写成了「不存在」：

| 文件 | 行 | 原登记 | 复核结果 |
| --- | --- | --- | --- |
| `reports/w21_framework_slot_map.md` | 48 | 「ORCA / r2SCAN-3c 不在本仓工具链里」 | **假** |
| `reports/week23_2_project_charter.md` | 65 | 「不跑 DFT 级 `P_1`（ORCA / r2SCAN-3c 不在本仓工具链里）」 | **假** |

文件系统复核：`E:/ORCA/orca_6_1_1/orca.exe` 存在、许可有效、**6.1.1**；r2SCAN-3c 水分子 4 进程 **6.5 s** 正常终止；`CPCM(ACETONITRILE)+smd true+SMDsolvent "ACETONITRILE"` 回读 **Epsilon = 35.6880**，与论文的 35.688 逐位一致。因此本件同时做两件事：**更正登记** 与 **补上 DFT 级实例化**。

最后是可行性依据：母体论文 §2.3 明确「所有 ΔSCF 结果均取自三态**单点**计算」，即 `P_1` / `P_2` 是**垂直量**、三态共用同一个 G1 几何、**不需要 Opt+Freq**。这条协议约束正是让 DFT 级实例化变得可负担的原因——本臂只做单点。

## 1. 与母体论文的口径关系（先钉死）

| 项 | 母体论文 | 本臂 W24-2 | 可否直接比 |
| --- | --- | --- | --- |
| 电子结构层级 | r2SCAN-3c | **r2SCAN-3c**（同层） | **可以** |
| 量的性质 | 垂直三点 ΔSCF 单点 | **垂直三点 ΔSCF 单点** | **可以** |
| 几何 | CREST 构象搜索的 G1 | 确定性单构象 GFN2 优化几何 | 部分（构象口径差已登记） |
| 溶剂 | CPCM/SMD 乙腈 ε=35.688 | CPCM/SMD 乙腈（回读 35.6880） | **可以** |
| 样本量 | 核心集 18；气相锚点 12 | 28（核心集 18 ∪ 锚点物种，交集 12） | 本臂就是论文口径 |
| 能量约定 | 未明示 | primary = `FINAL SINGLE POINT ENERGY`；secondary = SMD CDS 修正 | 两条都落盘 |

## 2. 设计（跑前锁定）

| 项 | 内容 |
| --- | --- |
| 分子池 | 母体论文 `core_set.csv` 的 **18** 个分子 ∪ `gas_phase_anchors.csv` 的 IP 物种，按 InChIKey 去重 => **28** 个分子（核心 18 ｜ 锚 22 ｜ 交集 12） |
| 几何 G1 | GFN2-xTB `--opt`（与 W21 / W23 / W24-1 逐位同源） |
| xTB 侧 | 每分子 1 次 GFN2 `--opt` + **3 次 GFN2 垂直单点**（neutral / cation / anion，`xtb_optimisation_arguments` 之外的新 `vertical_arguments`） |
| ORCA 侧 | 每分子 **6 次单点** = 2 介质（gas / `smd_acetonitrile`）× 3 态（neutral q=0 M=1 / cation q=+1 M=2 / anion q=−1 M=2） |
| 泛函与基组 | `! r2SCAN-3c RIJCOSX TightSCF`（r2SCAN + def2-mTZVPP + 几何 Counterpoise 色散 + RIJCOSX） |
| 溶剂输入 | `%cpcm` / `smd true` / `SMDsolvent "ACETONITRILE"` |
| 主读数 | `FINAL SINGLE POINT ENERGY`（primary）；`Total Energy after SMD CDS correction`（secondary，稳健性变体） |
| 前置门 | `PREREG["status"] == "locked_before_run"`，否则拒绝运行 |
| 资源门 | `workers * nprocs <= 16`（本机逻辑核数），否则拒绝运行 |
| 断点续跑 | 每完成一个分子的 6 臂即追加 `probes/artifacts/w24_2_orca_records.jsonl`；重跑默认复用，`--no-checkpoint` 关闭 |
| 调度 | 重原子数降序派发：大分子的 6 个 ORCA 作业是全队长杆，先占用 worker 与其余任务重叠 |

## 3. 八条假设（O1–O8，跑前锁定）

| id | 内容 | 判据 | 论文对照 |
| --- | --- | --- | --- |
| O1 | 复现 Table 1 的 `P_1` | MAE ≤ **0.60 eV** | 0.251（放宽 2.4 倍以吸收构象与几何口径差） |
| O2 | `P_0` 的值误差显著大于 `P_0prime` | `MAE(P0) < MAE(P0prime)` 且 `MAE(P0prime) ≥ 2.0 eV` | 1.377 vs 4.481 |
| O3 | 值误差与排序误差解耦 | `tau_b(P0prime) ≥ tau_b(P1) − 0.15` | 0.911 vs 0.727 |
| O4 | `P_0 -> P_1` 氧化为负、还原为正 | 符号 | −1.5496 / +7.5919 |
| O5 | `P_1 -> P_2` 两轴为负且环境台阶更保序 | 两轴 mean < 0 且 `tau_b(P1->P2, ox) > tau_b(P0->P1, ox)` | −2.3934 / −2.1731 |
| O6 | 气相阴离子不束缚是普遍签名 | 阳 HOMO 占比 ≥ **0.80** | 18/18 |
| O7 | DFT ↔ xTB 桥存在 | 交集分子 `rho(IP_r2SCAN3c, IP_GFN2_vertical) ≥ 0.80` | 本臂新增 |
| O8 | 能量约定稳健 | `abs(delta tau_b) ≤ 0.10`（两台阶两轴） | 本臂新增 |

**O7 的门是有后果的**：若 `rho < 0.80`，则声明桥不成立，**W24-1 的 246 个台阶不得映射到 DFT 尺度**。

## 4. 跑中更正（实测发现，逐条登记）

本臂在冒烟测试中撞到两处**只有真跑才会暴露**的实现问题，均已在正式跑之前修正并留痕：

1. **这台 Windows 构建的 ORCA 6.1.1 把整份日志写到 stdout，不生成 `.out`**，只生成 `.gbw` / `.property.txt` / `.bibtex` 旁文件。首版探针按 Linux 习惯只读 `<label>.out`，于是**六臂全判 `orca_failed`**（`terminated=False`）。更正：`stdout` 为主源、`.out` 为其非空回退，且 `stderr` 并入 `stdout`。
2. **ORCA 6 的 `ORBITAL ENERGIES` 表不标注 HOMO / LUMO**，且非限制性计算每个自旋各打印一张表。更正：前缘轨道改由**占据数列**推——占据 > 0.5 的最高者为 HOMO，≤ 0.5 的最低者为 LUMO。

3. **并行 r2SCAN-3c + CPCM/SMD 带电溶质会在这台机器上 MPI 死锁**。正式跑的第一个作业
   （一个 SMD 乙腈中的阳离子）在 6 分钟正常推进后彻底静止：4 个 MPI 进程在随后的 12 分钟里
   合计只增加约 17 s CPU，`%pal nprocs 4` 的并行形式无法完成。对照实验把**同一个输入**改成
   `%pal nprocs 1` 后 **258.9 s 正常终止**（`exit=0`）。因此本臂最终以 `--nprocs 1` 多 worker
   运行；探针同时内置「并行失败即自动降级串行重试一次」的兜底，并把每个作业的超时压到 20 分钟。
   这条不是实现细节而是**可复现性事实**：同一份输入在本机并行会挂、串行不会。

修正后的端到端首测（DMC，气相中性，4 进程）与物理自洽性检查：

| 项 | 实测 | 说明 |
| --- | --- | --- |
| 终止状态 | 六臂全部 `ORCA TERMINATED NORMALLY` | — |
| `Epsilon` | 35.6880（gas 组为空，SMD 组回读） | 与论文 35.688 一致 |
| 气相 ΔSCF IP | **10.4612 eV** | 实验电离能 ≈ 10.5 eV |
| 气相 ΔSCF EA | **−3.2213 eV** | 阴离子在气相不束缚的签名 |
| HOMO / LUMO | **−7.0019 / +0.3435 eV** | HOMO 为第 24 条占据轨道，48 电子，与 C₃H₆O₃ 一致 |
| 单作业挂钟（空载） | 气相中性 ~8 s；阳离子 ~24 s；阴离子 ~31 s | 开壳层更贵 |

> 口径提醒：上表的 `IP` 是 **ΔSCF 垂直量**，HOMO/LUMO 是 **Kohn-Sham 轨道能**。两者在本臂**分别落盘、绝不互换**——论文 §2.3 用 ΔSCF 做 `P_1`，正是因为它不受 KS 轨道能偏移（r2SCAN-3c 的 KS HOMO 比 ΔSCF IP 高约 3.5 eV）的影响。

## 5. 声明限制（照抄预注册）

- 几何口径差：论文用 CREST 构象搜索，本臂用确定性单构象（`seed = 42 + row_index`）。因此 Table 1 的 MAE 不完全可比。
- 构象数少：单构象下 EA 尤其脆弱（论文 §2.3 亦指出气相 EA 只在趋势上有意义）。
- 能量约定未在论文中明示：本臂把 `FINAL SINGLE POINT ENERGY` 与 SMD CDS 修正两条都落盘，并预注册 primary；冲突时以 primary 为主读数、secondary 为稳健性。
- 核心集只有 18 个分子，`tau_b` 抽样误差大（论文自报 N=10 时 sd 0.1264）；本臂的 `tau_b` 不用于精细比较，只用于符号与量级检查。
- 本臂不动 W24-1 的 xTB 层；DFT↔xTB 桥只用于声明可转移性，不用于修改任何冻结读数。
- 不引用任何 Reaxys 数值。
- 本臂不改写母体论文；只回答「同一协议在本机是否能被复现」。

## 6. 不做清单

- 不跑 `G1 -> G2` 的 `Opt+Freq` 台阶：论文的 `P_1` / `P_2` 是垂直量，`G2` 是另一件臂。
- 不做色散外推 / 显式溶剂团簇：属 §2.3 之外的口径，会污染可比性。
- 不做 `C_*` 条件态（W24-1 的地盘），**不给任何综合电解液总分**。
- 不把 Batt-P30K / RX-392 / THEMol 折进训练池或标签。
- 不动主记分牌：本件是**表示/层级**通道，不是 ε 通道。

## 7. 复现命令

```powershell
# 全量（28 分子 x 6 臂 = 168 个 ORCA 单点 + 4 次 xTB/分子）
.\.venv\Scripts\python.exe probes\w24_2_orca_dft.py --workers 1 --nprocs 4 --maxcore 1200 --timeout 7200
# 断点续跑（默认开启，重跑即自动跳过已完成分子）
.\.venv\Scripts\python.exe probes\w24_2_orca_dft.py --workers 1 --nprocs 4 --maxcore 1200
# 只重算读数与报告，不重跑任何电子结构
.\.venv\Scripts\python.exe probes\w24_2_orca_dft.py --from-layer
.\.venv\Scripts\python.exe probes\w24_2_orca_dft.py --report-only
```

## 8. 产物

| 路径 | 内容 |
| --- | --- |
| `data/processed/w24_2_orca_dft_layer.csv` | 逐分子逐臂层（E、E_cds、HOMO、LUMO、epsilon、status、seconds） |
| `probes/w24_2_orca_dft_summary.json` | 全量读数与 O1–O8 裁决 |
| `probes/artifacts/w24_2_rung_table.csv` | `P0->P0prime` / `P0->P1` / `P1->P2` 两轴台阶（含 SDK-CDS 变体） |
| `probes/artifacts/w24_2_anchor_table.csv` | 三层对气相锚点的 MAE / 偏置 / tau_b |
| `probes/artifacts/w24_2_bridge.csv` | DFT ↔ xTB 桥 |
| `probes/artifacts/w24_2_unbound_anion.csv` | 阴离子不束缚签名 |
| `probes/artifacts/w24_2_hypotheses.csv` | O1–O8 裁决 |
| `probes/artifacts/w24_2_qc.csv` | 逐臂 QC |
| `probes/artifacts/w24_2_orca_records.jsonl` | 断点续跑检查点 |
| `reports/w24_2_orca_dft.md` | 自动生成的结题报告 |

## 9. 跑后修复登记（W24-2）

本节记录**只有真跑才暴露**的三个缺陷。三者都写进了 `tests/test_w24_2_orca_dft.py`；改判据的一个都没有。

**① 垂直单点的哨兵读错了流（改了 84 个臂的成败判定）**

`w21.parse_arm` 用 `.xtboptok` 哨兵文件判「这次真的跑完了」，而 xTB **只对 `--opt` 写这个文件**。
本臂的三态是**垂直单点**，没有可供认证的优化几何，首版因此把 3 个 GFN2 垂直臂 × 28 分子 =
**84 个臂全部判成 `xtb_failed`**，而能量其实躺在日志里。改为：`optimise=False` 时以
「`returncode == 0` **且** 终止横幅出现」为哨兵。

**② 终止横幅在 stderr，不在 stdout（①的修复第一版仍然错）**

本机 xTB 6.7.1 把**科学日志写 stdout、终止横幅 `normal termination of xtb` 写 stderr**
（实测：stderr 全长 27 字节，就是这一行）。而 runner 是 `capture_output=True`，两股流分开。
第一版修复只在 stdout 里找横幅，于是 84 个臂**依然全判失败**。二次修复改为**两股流都找**。

**③ 修复分支自己会崩，而且会掉进 ORCA 主跑**

`--repair-gfn2` 分支在 `workers` 绑定之前就读它（`UnboundLocalError`），而且**没有 `return`**
—— 修完 GFN2 会继续往下执行完整的 168 个 ORCA 单点。两者都改掉（把 `workers` 绑定移到分支内首行，
分支末尾 `return 0`），并让分支在写回 checkpoint 之后**同步重建 layer**，否则 `--from-layer`
会继续读到失败那轮写下的旧 layer。

**修复后的读数（第 1–6 节即修复后重导）**：GFN2 垂直臂 **84/84 `ok`**；O7 由 `no_data` 变为
**成立**（`rho = 0.8687 ≥ 0.80`）；O2 由「判否」变为**成立** —— 它的输入正是先前为空的
`gfn2_ip_gas_eV`，所以这次翻的是**数据缺失**，不是判据。

**xTB → DFT 桥的实测形状（要写进结论的一条读数）**：秩很齐（`rho = 0.8687`、`tau_b = 0.7493`），
**量级不齐**（GFN2 垂直 IP 系统性**高出** ORCA r2SCAN-3c **4.816 ± 0.580 eV**，区间 −6.08 ~ −3.53 eV）。
⇒ GFN2 的 ΔSCF 排序可作**筛选**，绝对值不可作**标定**。

**④ 唯一的 ORCA 失败是物理上应当失败的（QC 登记，不改判据）**

`nitrogen dioxide` 的 6 个臂全部 `orca_failed`，且耗时 0.13 s（输入阶段即被拒）。复现实验
（`probes/artifacts/w24_2_no2_probe.log`）给出 ORCA 原文：

```
Error : multiplicity (1) is odd and number of electrons (23) is odd -> impossible
```

NO₂ 是**稳定自由基**（`O=[N+][O-]`，1 个自由基电子），而预注册把中性态锁成闭壳单重态（`M1`）
—— 这条约定对另外 27 个分子都对。把同一输入改成 `M2` 后 **`ORCA TERMINATED NORMALLY`**。
**处置**：预注册的每态多重度不改（改了就不是同一支枪）。该分子**按 QC 排除**，`n = 27` 的读数
全部如实标注来源；`tests/test_w24_2_orca_dft.py` 把「失败必须可归因」钉死
（`failed == {"nitrogen dioxide": 6}`），而不是钉死「零失败」。

## 10. 跑后追加产物

| 路径 | 内容 |
| --- | --- |
| `probes/artifacts/w24_2_orca_bridge.png` | 四面板图：xTB→DFT 桥散点、三层锚点 MAE 对照、台阶位移对照、裁决板 |
| `probes/w24_2_orca_dft_figures.py` | 上图的只读生成脚本 |
| `probes/artifacts/w24_2_no2_probe.log` | NO₂ 多重度失败的复现日志（M1 被拒 / M2 正常终止） |
| `probes/artifacts/w24_2_repair_stdout.log` | GFN2 修复运行的输出 |
