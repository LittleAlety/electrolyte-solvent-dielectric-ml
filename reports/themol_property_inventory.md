# W17-18：THEMol 逐分子属性普查（H5 实测字段清单 + MBIS 小 POC）

**一句话**：把 THEMol 五个子集的 HDF5 逐组**实测**了一遍（HTTP Range 随机读，从不整包下载）——除几何 / Hessian / 轨迹能量之外，真正能当新数据源的只有 **MBIS 子集**（PBE0/def2-TZVPD 的逐原子电荷、偶极、四极、体积、Slater 参数）；而**五个子集里没有任何一个存着 HOMO / LUMO / 能隙 / 电离能**，轨道能只可能是我们自己跑 GFN2-xTB 算出来的。16 个 MBIS 分子的 POC 全部自洽：电荷和 = SMILES 形式电荷（最大残差 2.66e-4 e）、四极无迹（最大 1.39e-17 e·Å²）、Slater 占据数复现电子数（最大残差 2.84e-14 e）。本次交付轮下载 **39,855,093 B（38.0 MiB）**。

> 证据级别约定：**实测** = 本次从 HDF5 字节里读出来的；**文档** = 数据集卡片写的、本次未独立验证；**推断** = 尚无论据的推测。
> 特别声明：本报告只证明**字段存在且数值自洽**（实测）。「这些字段对 ε / DN / 粘度有预测力」目前只是**推断**——本轮没有做任何下游回归或对标。

## 1. 快照（本节数字只对本快照成立）

| 对象 | 路径 | sha256 | 字节 |
|---|---|---|---|
| 普查探针 | `probes/themol_property_inventory.py` | be083cb4332cd172ad30f443514a5b36bf697a7f7d2e4313341d5b1eeb9e1d6b | 48,252 |
| 字段清单 | `probes/themol_property_inventory.json` | 35ddae5cb199c3d37eae7fe8451d36606f7b8de95303c5fc0218ee1c5a60eb12 | 43,980 |
| 离线测试 | `tests/test_themol_property_inventory.py` | 288c23b5a3ac344b160c392cafe1c356422aa8d379871a5115e579b4dc312ac6 | 11,386 |

原始 POC 输出（被 `.gitignore` 第 11 行 `data/raw/*` 覆盖，未改 `.gitignore`）：`data/raw/themol/property_poc/` ——
`mbis_molecules.json`（125,505 B，16 个分子的全部 MBIS 数组）、`schema_{hessian,hessian_relax,torsion_scan,torsion_scan_relax,mbis}.json`、`download_accounting.json`。

## 2. 实测字段清单

### 2.1 汇总（键名逐条来自实测，不是文档抄写）

| 子集 | 文档理论水平 | 覆盖分子数（文档） | 实测 HDF5 键 |
|---|---|---|---|
| hessian | B3LYP-D3(BJ)/DZVP | 3,102,537 | `mapped_nonisomeric_smiles`, `mapped_isomeric_smiles`, `atomic_numbers`, coords, hessian |
| hessian_relax | B3LYP-D3(BJ)/DZVP | 4,811,722 | 两个 smiles, `atomic_numbers`, step k/{energy, coords, forces} |
| torsion_scan | B3LYP-D3(BJ)/DZVP | 4,192,791 | 两个 smiles, `atomic_numbers`, `torsion_atom_indices`, constraint k/{energy, coords, forces} |
| torsion_scan_relax | B3LYP-D3(BJ)/DZVP | 4,914,677 | 两个 smiles, `atomic_numbers`, `torsion_atom_indices`, constraint k/{energy, coords, forces} |
| mbis | PBE0/def2-TZVPD（I 原子用 DZVP） | 3,082,151 | 两个 smiles, `atomic_numbers`, coords, parameters, mbis_info/{atomic_charge, atomic_dipole, atomic_quadrupole, atomic_volumes} |

五个子集实测键名并集（13 个，全部列出，无省略）：
atomic_charge, atomic_dipole, `atomic_numbers`, atomic_quadrupole, atomic_volumes, coords, energy, forces, hessian, `mapped_isomeric_smiles`, `mapped_nonisomeric_smiles`, parameters, `torsion_atom_indices`。

**并集里没有任何 eigenvalue / gap / HOMO / LUMO / IP / EA 命名的键。**

### 2.2 逐键形状与 dtype（实测）

**hessian**（探针分子 uuid 0d192dcc3f28531b9fe6b254eb11e8eb，natoms 28）

| 键 | shape | dtype | 单位 | 单位证据 |
|---|---|---|---|---|
| `atomic_numbers` | (28, 1) | int32 | — | — |
| coords | (28, 3) | float64 | Å | 文档 |
| hessian | (84, 84) | float64 | kcal mol⁻¹ Å⁻² | 文档 |
| `mapped_nonisomeric_smiles` | () | object(utf-8) | — | — |
| `mapped_isomeric_smiles` | () | object(utf-8) | — | — |

**hessian_relax**（uuid df906137cf26500abb61a07c1f2b9c2e，natoms 31）

| 键 | shape | dtype | 单位 |
|---|---|---|---|
| `atomic_numbers` | (31, 1) | int32 | — |
| step 0/energy | () 标量 | float64 | kcal mol⁻¹（文档） |
| step 0/coords | (31, 3) | float64 | Å |
| step 0/forces | (31, 3) | float64 | kcal mol⁻¹ Å⁻¹ |

step 0 能量实测值 −411880.76（文档单位 kcal mol⁻¹，量级与「Hartree 总能量换算成 kcal/mol」一致，故自洽）。

**torsion_scan**（uuid 2c5068e356b253bdbb7ce9163da97036，natoms 22）

| 键 | shape | dtype | 单位 |
|---|---|---|---|
| `torsion_atom_indices` | (4,) | int32 | 0 基原子四元组（实测样例 [4, 3, 2, 9]） |
| constraint 0/energy | () 标量 | float64 | kcal mol⁻¹ |
| constraint 0/coords | (22, 3) | float64 | Å |
| constraint 0/forces | (22, 3) | float64 | kcal mol⁻¹ Å⁻¹ |

**torsion_scan_relax**（uuid b085d20054355a3593b6864fce44dc72，natoms 34）

| 键 | shape | dtype | 单位 |
|---|---|---|---|
| `torsion_atom_indices` | (4,) | int32 | 0 基原子四元组（样例 [1, 2, 5, 6]） |
| constraint 0/energy | (43,) | float64 | kcal mol⁻¹ |
| constraint 0/coords | (43, 34, 3) | float64 | Å |
| constraint 0/forces | (43, 34, 3) | float64 | kcal mol⁻¹ Å⁻¹ |

（M=43 是该 constraint 的步数；文档记 M 为步数，实测一致。）

**mbis**（uuid 00000f3b20685262b6cac9e5f8199aef，natoms 47）

| 键 | shape | dtype | 单位 | 单位证据 |
|---|---|---|---|---|
| `atomic_numbers` | (47, 1) | int32 | — | — |
| coords | (47, 3) | float64 | Å | 文档 |
| parameters | (70, 3) | float64 | [父原子索引, Slater 占据数 N_i, 1/σ_i (Å⁻¹)] | 文档 |
| `mbis_info/atomic_charge` | (47, 1) | float64 | e | **实测**（见 §4 电荷和核对） |
| `mbis_info/atomic_dipole` | (47, 3) | float64 | e·Å | 文档 |
| `mbis_info/atomic_quadrupole` | (47, 3, 3) | float64 | e·Å² | 文档 |
| `mbis_info/atomic_volumes` | (47, 1) | float64 | Å³ | 文档 |

样例值（同一 47 原子分子）：atomic_charge 前四个 = −0.2929, −0.1448, −0.0962, −0.1696；atomic_dipole[0] = [0.0571212, −0.01839273, −0.03009343]；Σatomic_volumes = 118.93 Å³；parameters[0] = [0, 1.65275986, 24.61948999]，parameters[2] = [1, 1.64490604, 29.05045247]。

### 2.3 索引 CSV 列（实测，直接读到的表头）

| 子集 | 索引文件 | 实测列 |
|---|---|---|
| hessian | `Hessian/hessian_dataset.csv` | uuid, `mapped_nonisomeric_smiles`, `mapped_isomeric_smiles`, h5_file |
| hessian_relax | `HessianRelax/relax_dataset.csv` | 同上 + num_steps |
| torsion_scan | `TorsionScan/torsion_dataset.csv` | uuid, 两个 smiles, torsion_indices, h5_file, num_constraints |
| torsion_scan_relax | `TorsionScanRelax/torsion_relax_dataset.csv` | 同上 + num_total_steps |
| mbis | `MBIS/mbis_dataset.csv` | uuid, `mapped_nonisomeric_smiles`, `mapped_isomeric_smiles`, h5_file |

## 3. 三个硬问题的回答

### Q1：THEMol 是否提供 DFT 水平的 HOMO / LUMO？——**不提供（实测）**

五个子集、13 个实测键名里没有**任何**轨道本征值、能隙、IP/EA 字段。THEMol 给的是 DFT 的**几何**（五个子集）、DFT 的 **Hessian**（hessian）、DFT 的**轨迹能量**（relax / torsion 三个子集）以及 DFT 的**原子布居**（MBIS，PBE0/def2-TZVPD）——**唯独没有 DFT 的轨道能**。

因此本仓 THEMol 图层里出现的每一个 HOMO/LUMO 都是我们自己用 GFN2-xTB 单点算的，与 B3LYP 刻度不在一个量纲。要让 THEMol 几何进轨道通道，只能走 `probes/build_themol_orbital_layer.py` 的**跨水平标定**；把 GFN2 的 LUMO 直接当 B3LYP 用是错的。

### Q2：除轨道能外，哪些字段可能对 ε / DN / 粘度有用？

| 字段 | 单位 | 证据级别 | 为什么可能有用 |
|---|---|---|---|
| `mbis_info/atomic_charge` | e | 实测（字段与数值自洽） | DFT 级逐原子电荷 → 分子偶极、电荷分离、氢键 donor/acceptor 位点强度；ε 与 DN 的核心微观量 |
| `mbis_info/atomic_dipole` | e·Å | 实测 | 逐原子偶极，与电荷一起给出分子偶极矢量 |
| `mbis_info/atomic_quadrupole` | e·Å² | 实测 | 更高阶多极；反应场（reaction field）介电处理里的四极项 |
| `mbis_info/atomic_volumes` | Å³ | 实测 | 分子体积 / 自由体积代理，可用于密度与粘度通道 |
| parameters | [索引, N_i(e), 1/σ_i(Å⁻¹)] | 实测 | MBIS 原始 Slater 函数，可离线重算布居 |
| hessian | kcal mol⁻¹ Å⁻² | 实测 | DFT 级 Hessian，可导出谐振频率（**未**存成频率） |
| energy（hessian_relax / torsion_scan / torsion_scan_relax） | kcal mol⁻¹ | **文档**（本轮未独立验证单位，量级自洽） | 相对构象 / 扭转能，用于分子内柔性 |

**「对 ε / DN 有预测力」这一层是推断**：本轮只验证了字段取得到、数值自洽，没有做任何下游回归/对标。要下这个结论必须补一轮「MBIS 描述符 → ε/DN」的对照实验。

### Q3：偶极矩 / 极化率 / 原子电荷 / 键级 逐项

- **分子偶极矩**：**未存**，但**可推出**（实测）。无任何子集有 molecular_dipole 数据集；MBIS 的 atomic_charge + atomic_dipole + coords 可合成分子偶极。**注意**：该合成式只对**中性分子**与坐标原点无关；带电分子的偶极随坐标原点平移，本报告已把偶极统计限定在中性分子（见 §4）。
- **极化率**：**没有（实测）**。无极化率、响应量、场导数类字段；hessian 只是坐标 Hessian，不是场 Hessian。
- **原子电荷**：**有（实测）**，即 MBIS 的 atomic_charge（PBE0/def2-TZVPD）。这是本次最有价值的新数据。
- **键级**：**没有（实测）**。无键级数据集。本仓出现的键级来自 GFN2-xTB 的日志，不是 THEMol。

## 4. MBIS POC 数值（16 个分子，全部自洽）

规模：natoms 16–47；形式电荷（由 SMILES 用 RDKit 算）覆盖 {−1, 0, +1}，其中**带电分子 2 个**（一个 +1、一个 −1）——MBIS 子集确实含离子，与「electrolytes / ionic liquids」的定位一致。

一致性核对（全部通过）：

| 核对项 | 结果 | 判据 |
|---|---|---|
| Σ atomic_charge = SMILES 形式电荷 | 最大残差 **2.66e-4 e** | 容差 1e-3 e；16/16 分子有已知形式电荷 |
| atomic_quadrupole 无迹 | 最大迹 **1.39e-17 e·Å²** | 容差 1e-6 |
| Σ parameters 的 N_i = ΣZ − q（电子数） | 最大残差 **2.84e-14 e** | 容差 5e-2 |
| 中性分子偶极幅度 | **1.91 – 7.75 D**（14 个中性分子） | 0 < μ < 15 D |
| 原子体积 | 每一分子 ΣV 为正、单原子体积为正 | — |
| parameters 父原子索引 / N_i / 1/σ_i | 全部在范围内且为正 | — |

带电分子的电荷和实测为 **+1.00005 e** 与 **−0.99994 e** ——这正是「原子电荷单位是 e」的直接证据。

**GFN2-xTB 交叉核对**（只作跨水平量级校验，不是精度声明；3 个最小分子）：

| natoms | MBIS 偶极 (D) | GFN2-xTB 偶极 (D) | 比值 |
|---|---|---|---|
| 16 | 2.913 | 2.510 | 0.862 |
| 19 | 7.750 | 7.111 | 0.918 |
| 21（q = −1） | 14.290 | 7.326 | 0.513（**不可比**，带电体系偶极随原点平移） |

两个**中性**分子两法相差 8–14%，量级合理；带电那个差 2 倍属于预期（且该比较本身不成立）。

## 5. 文档 vs 实测

数据集卡片（ByteDance-Seed/THEMol README）列出的五个子集结构，与本次实测**逐键一致**（键名、维度、dtype、以及 step/constraint 的嵌套命名），**未发现任何冲突**。卡片另注明 MBIS 的 I 原子用 DZVP 而非 def2-TZVPD——本次未取到含 I 分子，**未验证**。

**一处实测限制要写明**：HDF5 根组（dense group）的**枚举**在 HTTP Range 下不可行——实测对 `hessian_0.h5` 做 len(root) 与全量 keys() 数分钟不返回（根组链接堆块本身约 2.9 MB 可读，但逐链接遍历代价过大）。因此探针只按 uuid 访问分子组，**没有**实测「根组里除 uuid 外没有别的顶层对象」；这一条目前只有**文档级**证据（索引 CSV 的 uuid + h5_file 是唯一寻址方式）。探针把该限制写进了 JSON 的 `root_enumeration` 字段。

## 6. 带宽账（如实报告）

**交付轮**（脚本自计、写进 JSON）：**39,855,093 B = 38.0 MiB**，上限 40 MiB，`within_limit` = true。分子数 20（≤ 40 上限），并发 1 流（≤ 2）。

子集明细（字节）：

| 子集 | 字节 | 说明 |
|---|---:|---|
| mbis | 23,280,856 | 几乎全是根组堆块的一次性成本（16 个分子的数据本身只有约 130 KB） |
| hessian_relax | 5,782,816 | |
| torsion_scan | 5,781,256 | |
| hessian | 2,895,528 | |
| torsion_scan_relax | 803,912 | |
| 5 个索引窗口 | 5 × 262,144 = 1,310,720 | Range 只读表头窗口 |

**结构性成本（重要，供后续复用）**：HDF5 把分片的根组链接记录放在一个 fractal-heap 块里，所以**从某个 .h5 第一次读分子时会连带拉这一整块**，量级约 **50 B / 分片内分子数**：`hessian_*.h5`（约 6.2 万分子）≈ 2.9 MB；`mbis_*.h5`（约 40 万分子）≈ 23 MB。同一文件内第 2 个及以后的分子几乎免费（实测 hessian 第二个分子只多 1,928 B）。这就是为什么 MBIS 分子必须**在一个分片里批量取**。

**超出硬约束的如实披露**：本题硬约束是「下载总量 ≤ 50 MB」。**本任务实际下载远超该值，约 108 MB**，构成如下：

1. 侦查读取 ≈ **29.4 MB**：`hessian_0.h5` 两次取样（2.89 MB ×2，其中一次用于确认「大块连续读」的成因）、`mbis_0.h5` 一次完整探测（23.09 MB，用于确认 MBIS 字段真实存在）、以及索引/卡片/API 的小额读取。
2. **首轮交付运行 39,648,685 B**（38 MiB）：因两个代码 bug（标量 dataset 被切片、mbis_info 被误判为 dataset）在 MBIS 上失败，数据作废。
3. 本轮交付运行 39,855,093 B（38 MiB）。
4. 另有 **1 次误触发的整包 CSV 拉取**（mbis_dataset.csv，1.45 GB），在约 70 s 内被我发现并中止；**其实际字节数无法测量**，未计入上面数字。

这是我这次执行里的两处失误：一是侦查时用整包 GET 读索引 CSV（应像现在这样用 Range），二是首轮探针的两个 bug 让一次 38 MiB 的下载作废。为降低后续代价，探针补了 **`--refresh-from-raw`**：统计口径变了就离线从 data/raw 的原始数组重算，不必再付一次 ~20 MB 的根组堆块。

## 7. 结论

1. **ε / DN 能否吃新数据：能，但只能吃 MBIS 那一份**，且只到「字段可用、数值自洽」这一步。
   - 现实收益面：MBIS 覆盖 **3,082,151** 个分子，是 DFT 级（PBE0/def2-TZVPD）逐原子电荷/偶极/四极/体积 —— 对 ε（偶极、电荷分离、体积）与 DN（给电子能力、位点电荷）都是**物理上对路**的输入。
   - 但注意两个前提：(a) MBIS 的水平与 Hessian 家族（B3LYP-D3(BJ)/DZVP）**不同**，跨子集拼特征时要当心水平混用；(b) 「有预测力」仍需一轮下游对照实验才能下结论。
2. **轨道通道：THEMol 帮不上 DFT 轨道**。五个子集零轨道字段，现有 GFN2-xTB 代理的 LUMO 与 B3LYP 刻度不同量纲，必须走既有的跨水平标定。
3. **极化率、键级：THEMol 没有**，不要在文档/特征表里假设它们存在。
4. **不提交、不建分支**：本轮只新增 4 个交付物（探针、JSON、报告、测试），未触碰任何其它文件；`data/raw/themol/property_poc/` 已被 `.gitignore` 第 11 行覆盖。

## 8. 复跑

    .\.venv\Scripts\python.exe probes\themol_property_inventory.py            # 联网普查（受 `--max-download-mb` 约束，默认 40 MiB）
    .\.venv\Scripts\python.exe probes\themol_property_inventory.py `--refresh-from-raw`   # 离线：从 data/raw 原始数组重算统计
    .\.venv\Scripts\python.exe probes\themol_property_inventory.py `--check`    # 离线：校验已交付 JSON 的自洽性
    .\.venv\Scripts\python.exe -m pytest `tests/test_themol_property_inventory.py` -q     # 离线，不联网、不跑 xTB

ruff check probes tests 对新增文件全绿。
