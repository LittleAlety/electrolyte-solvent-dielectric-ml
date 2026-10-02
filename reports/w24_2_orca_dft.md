# W24-2 · Axis A 的 P_1 / P_2 DFT 级首次实例化（ORCA 6.1.1 r2SCAN-3c）

- 任务：`w24_2_orca_dft` ｜ 预注册 sha256：`ecc63190d2c6d8e385aadb6916fa607130a0e0b66b27636192edcf509edc9228`
- ORCA：`E:\ORCA\orca_6_1_1\orca.exe`（6.1.1 / r2SCAN-3c / def2-mTZVPP / RIJCOSX / TightSCF）
- 几何：G1 = GFN2-xTB 优化几何；P_1 与 P_2 均为**垂直**三态 ΔSCF 单点（母体论文 2.3 口径），不做 Opt+Freq
- 规模：分子 28 个（核心集 18 ｜ 气相锚点 22）；ORCA 作业 168 个，成功 162，失败 6
- 记分牌纪律：本次**不取主记分牌 shot**（W24 计 0，历史累计 12），冻结读数不动

## 1. 假设裁决

| 编号 | 陈述 | 裁决 |
|---|---|---|
| O1 | reproduce paper Table 1: P1 MAE ~ 0.25 eV | **成立** |
| O2 | P0 MAE < P0prime MAE and P0prime MAE >= 2.0 eV | **成立** |
| O3 | value error and ranking error decouple: tau(P0prime) >= tau(P1) - 0.15 | **判否** |
| O4 | P0->P1: ox shift negative, red shift positive | **成立** |
| O5 | P1->P2: both shifts negative and tau(P1->P2 ox) > tau(P0->P1 ox) | **成立** |
| O6 | gas-phase anion unbound is the majority signature | **成立** |
| O7 | xTB GFN2 vertical dSCF IP ranks like the ORCA r2SCAN-3c IP (Spearman rho >= 0.8) | **成立** |
| O8 | energy convention (SMD CDS) does not move tau by more than 0.10 | **成立** |

### 关键读数

- O1：MAE(P1) = 0.248 eV（阈值 0.6，论文 0.251）
- O2：MAE(P0) = 1.364 eV，MAE(P0prime) = 4.903 eV（论文 1.377 / 4.481）
- O3：tau(P0prime) = 0.6710，tau(P1) = 0.8381（论文 0.911 / 0.727）
- O4：P0->P1 氧化位移 -1.4280 eV，还原位移 7.7086 eV（论文 -1.5496 / +7.5919）
- O5：P1->P2 氧化位移 -2.3426 eV，还原位移 -2.3972 eV；tau_ox(环境) = 0.8006 vs tau_ox(方法) = 0.6296（论文 -2.3934 / -2.1731）
- O6：气相阴离子不束缚 27/27 = 1.0000（论文 18/18）
- O7：xTB-DFT 桥 n = 27，rho = 0.8687，tau_b = 0.7493，偏移 -4.8161 ± 0.5796 eV
- O8：SMD-CDS 能量约定对 tau 的最大改动 0.0000（阈值 0.1）

## 2. 锚点复现（论文 Table 1，气相锚点）

| 层 | n | MAE (eV) | 偏置 (eV) | max abs err (eV) | tau_b | 论文 MAE | 论文 tau_b |
|---|---|---|---|---|---|---|---|
| `P0_koopmans` | 22 | 1.364 | 1.276 | 4.043 | 0.5671 | 1.377 | 0.6061 |
| `P0prime_gfn2_dscf` | 22 | 4.903 | 4.903 | 9.570 | 0.6710 | 4.481 | 0.9111 |
| `P1_r2scan3c_gas` | 21 | 0.248 | -0.211 | 1.163 | 0.8381 | 0.251 | 0.727 |

## 3. 台阶表（方法台阶 P0 -> P0prime -> P1，环境台阶 P1 -> P2）

| 台阶 | 轴 | n | 配对 | mean shift (eV) | std (eV) | tau_b | tau 95% CI | f_unresolved(1.96) | top10% | 论文 |
|---|---|---|---|---|---|---|---|---|---|---|
| `P0->P0prime` | ox | 28 | 378 | 3.4644 | 0.8924 | 0.7619 | [0.602, 0.886] | 0.3095 | 0.6667 | n/a |
| `P0->P0prime` | red | 28 | 378 | 4.3719 | 1.4040 | 0.7407 | [0.499, 0.911] | 0.3175 | 1.0000 | n/a |
| `P0->P1` | ox | 27 | 351 | -1.4280 | 0.8468 | 0.6296 | [0.398, 0.815] | 0.3932 | 0.3333 | -1.549600000000 |
| `P0->P1` | red | 27 | 351 | 7.7086 | 2.8009 | 0.5385 | [0.271, 0.748] | 0.7037 | 0.6667 | 7.591900000000 |
| `P1->P2` | ox | 27 | 351 | -2.3426 | 0.8758 | 0.8006 | [0.581, 0.959] | 0.2621 | 0.6667 | -2.393400000000 |
| `P1->P2` | red | 27 | 351 | -2.3972 | 0.6827 | 0.7322 | [0.509, 0.892] | 0.4131 | 0.3333 | -2.173100000000 |
| `P0->P1_cds` | ox | 27 | 351 | -1.4280 | 0.8468 | 0.6296 | [0.398, 0.815] | 0.3932 | 0.3333 | n/a |
| `P0->P1_cds` | red | 27 | 351 | 7.7086 | 2.8009 | 0.5385 | [0.271, 0.748] | 0.7037 | 0.6667 | n/a |
| `P1->P2_cds` | ox | 27 | 351 | -2.3459 | 0.8754 | 0.8006 | [0.581, 0.959] | 0.2621 | 0.6667 | n/a |
| `P1->P2_cds` | red | 27 | 351 | -2.3934 | 0.6830 | 0.7322 | [0.509, 0.892] | 0.4131 | 0.3333 | n/a |

## 4. 阴离子不束缚签名（O6）

- 气相阴离子 HOMO > 0 的分子：27 / 27（占比 1.0000，阈值 0.8）

## 5. xTB -> DFT 尺度桥（O7）

- 交集分子 n = 27，Spearman rho = 0.8687（阈值 0.8），Kendall tau_b = 0.7493
- DFT - xTB 的电离能偏移：-4.8161 ± 0.5796 eV（区间 -6.0769 ~ -3.5259 eV）

## 6. 逐臂 QC

| 臂 | 成功 | ORCA 失败 | 异常 | 未计算 | epsilon 观测 | 单作业均值 (s) | 单作业最大 (s) |
|---|---|---|---|---|---|---|---|
| `gas_neutral` | 27 | 1 | n/a | n/a | n/a（气相臂） | n/a | n/a |
| `gas_cation` | 27 | 1 | n/a | n/a | n/a（气相臂） | n/a | n/a |
| `gas_anion` | 27 | 1 | n/a | n/a | n/a（气相臂） | n/a | n/a |
| `smd_acetonitrile_neutral` | 27 | 1 | n/a | n/a | [35.688] | n/a | n/a |
| `smd_acetonitrile_cation` | 27 | 1 | n/a | n/a | [35.688] | n/a | n/a |
| `smd_acetonitrile_anion` | 27 | 1 | n/a | n/a | [35.688] | n/a | n/a |

## 7. 声明限制（照抄预注册）

- 几何口径差：论文用 CREST 构象搜索，本臂用确定性单构象（seed = 42 + row_index）。因此表 1 的 MAE 不完全可比。
- 构象数少：单构象下 EA 尤其脆弱（论文 2.3 亦指出气相 EA 只在趋势上有意义）。
- 能量约定未在论文中明示：本臂把 FINAL SINGLE POINT ENERGY 与 SMD CDS 修正两条都落盘，并预注册 primary，冲突时以 primary 为主读数、secondary 为稳健性。
- 核心集只有 18 个分子，tau_b 抽样误差大（论文自报 N=10 时 sd 0.1264）；本臂的 tau_b 不用于精细比较，只用于符号与量级检查。
- 本臂不动 W24-1 的 xTB 层；DFT<->xTB 桥只用于声明可转移性，不用于修改任何冻结读数。
- 不引用任何 Reaxys 数值。
- 本臂不改写母体论文；只回答「同一协议在本机是否能被复现」。

## 8. 复现命令

```powershell
.\.venv\Scripts\python.exe probes\w24_2_orca_dft.py --workers 2 --nprocs 8
.\.venv\Scripts\python.exe probes\w24_2_orca_dft.py --from-layer
.\.venv\Scripts\python.exe probes\w24_2_orca_dft.py --report-only
```

- 挂钟：2628.2 s ｜ 生成时间（UTC）：2026-10-02T12:09:32.096727+00:00

