# W17-14　THEMol / GFN2-xTB 第三轨道源：**几何能拿到，能级不能直接混用**

**一句话结论**：THEMol 的 2,695,304 条 Hessian 几何里，本仓关键名册命中 **5,117/31,949（16.0%）**、旗舰 ε 名册命中 **142/247（57.5%）**；
用 HTTP Range 远程读几何 + GFN2-xTB 单点，**166 个分子全部产出 HOMO/LUMO**（0 失败、0 空值）。
但把它接到权威的 wB97X-V/def2-TZVPPD/SMD(ε=18.5) 水平上时：**HOMO 相关性强（r 0.856）却差 0.0031 eV 没过 MAE 门；LUMO（r 0.530）与 gap（r 0.307）完全不在一个刻度上**。
⇒ 判决：**三个通道全部 `reference_only`**，`calib_homo_eV` / `calib_lumo_eV` 整列为空。这一臂是**负结果**，但是被证据钉死的负结果。

---

## 1. 为什么要做这一臂

Week 17 的轨道通道此前只有两个源：

| 源 | 水平 | 规模 | 与本仓的关系 |
|---|---|---|---|
| Batt-P30K（`data/raw/batt/Batt-P30K.h5`） | wB97X-V/def2-TZVPPD/SMD(ε=18.5) | 29,519 | **唯一主源** |
| W17-12 第二源层（PubChemQC） | B3LYP/6-31G\*//PM6 气相 | 912 行 | 增量列，ε 名册覆盖 210/247 |

作者给出 `ByteDance-Seed/THEMol`（arXiv 2605.14973；代码 Apache-2.0 / **数据 CC BY-NC 4.0**），其数据集卡明确写覆盖 **electrolytes** 与 **ionic liquids**，并要求「继续为 HOMO/LUMO 找出路」。

**先核过字段（不是看名字猜）**：THEMol 五个子集（Hessian / HessianRelax / TorsionScan / TorsionScanRelax / MBIS）的 HDF5 组里只有
`atomic_numbers`、`coords`、`hessian`（Hessian 子集）、`step k/{energy,coords,forces}`、`constraint k/{...}`、`mbis_info/{atomic_volumes,atomic_charge,atomic_dipole,atomic_quadrupole}`。
**没有轨道能级、没有 gap、没有 IP/EA。** 所以「用 THEMol 出 HOMO/LUMO」只有一条路：**拿它的几何，自己算**。

## 2. 方法：远程读几何 + 一个 GFN2-xTB 单点

```
THEMol hessian_N.h5（4.79 GB，不下载）
   ↓  HTTP Range：只取该 uuid 组的 atomic_numbers 与 coords（≈2.9 MB/分子）
XYZ
   ↓  electrolyte_ml.xtb_runner（OMP_NUM_THREADS=1 钉死，私有 scratch 目录）
GFN2-xTB --sp
   ↓  解析 "# Occupation  Energy/Eh  Energy/eV" 表的 eV 列
HOMO / LUMO / gap
```

- **不落 .h5**：全程 0 字节 HDF5 落盘；166 个分子实测网络总量 **142,150,508 B（142.2 MB）**。
- **目标集**：ε 名册（`data/dielectric_v04.csv`）∪ W17-12 的 111 个 `paired_anchor`（同时有 PubChemQC 与 Batt 值的分子），去重后 166 个；其中 **72 个是标定锚**。
- **分片**：按 `hessian_N.h5` 分组后 round-robin 分 4 片（51/42/41/32），4 个 agent 并行 8 分钟内跑完；xTB 侧合计 1,408 s。
- **确定性**：每个分子独占 scratch 目录（避免 `xtbrestart` 被当成 SCF 重启），几何的 sha256 逐行落进 `geometry_sha256`。

## 3. 结果

### 3.1 覆盖（THEMol 本身能给你什么）

| 口径 | 命中 | 分母 | 比例 |
|---|---|---|---|
| THEMol Hessian 池（canonical SMILES 行数） | — | **2,695,304** | — |
| 本仓关键名册（`four_core_key_registry`） | **5,117** | 31,949 | **16.0%** |
| ε 名册 | **142** | 247 | **57.5%** |
| 黏度名册 | **242** | 1,228 | **19.7%** |
| W17-12 标定锚 | **72** | 111 | 64.9% |

对照：iMolS 在 ε 名册上只有 103/247（41.7%），且已被许可否决。**THEMol 的几何覆盖率本身是这一臂最实在的收获**——它比 PubChemQC 的 ε 覆盖（85.0%）低，但覆盖的是**几何**，不是能级。

### 3.2 跨能级映射（74 个配对锚，2 折样本外）

| 通道 | slope | intercept | r | 样本外 MAE | 最大误差 | 判定 |
|---|---|---|---|---|---|---|
| HOMO | 1.0389102752198223 | 1.4879804327425656 | **0.8557** | **0.3531 eV** | 1.4162 eV | ❌ `reference_only` |
| LUMO | 0.0903748834229043 | 1.9336417639360564 | **0.5296** | 0.3311 eV | 1.0902 eV | ❌ `reference_only` |
| gap  | 0.11635116670254111 | 10.749742707994933 | **0.3072** | 0.7775 eV | 2.3835 eV | ❌ `reference_only` |

门限 **MAE ≤ 0.35 eV 且 r ≥ 0.80**，逐字继承 `probes/orbital_second_source_prereg.json`（见 `probes/themol_orbital_layer_prereg.json`）——**不是看到结果才定的**。

三条读法：

1. **HOMO 是「差一点」**：r 0.856 过门，MAE 0.3531 **超门 0.0031 eV**。这条不该被粉饰成「接近可用」——它就是一个没过门的通道，而且最大单点误差 1.42 eV 说明尾部很厚。
2. **LUMO 的 slope 是 0.09**：拟合出来的映射几乎是**一条水平线**。这说明 GFN2-xTB 的**虚轨道**（LUMO、gap）与 DFT 的 LUMO 流形在**排序意义上**都不成立——半经验紧束缚对空轨道的描述本来就弱。
3. **gap 也救不回来**：gap 是**平移不变**的通道（能级整体平移会抵消），所以「绝对能级差一个常数」这个借口在这里不成立。gap r 0.307 ⇒ 不是参考点问题，是**尺度**问题。

对照 W17-12 的 PubChemQC（B3LYP/6-31G\*）同一批锚：HOMO r 0.972 / MAE 0.177；gap r 0.777。**同一把尺子上，B3LYP 打得过 GFN2，而且赢得不勉强。**

### 3.3 能级偏移（74 个锚）

| 偏移 | 均值 | σ | min | max |
|---|---|---|---|---|
| GFN2 − Batt，HOMO | **−1.0595 eV** | 0.4797 | −2.3702 | +0.4043 |
| GFN2 − Batt，LUMO | **−7.0126 eV** | 2.4789 | −9.4398 | −0.8129 |
| GFN2 − Batt，gap | **−5.9531 eV** | 2.5081 | −8.4720 | +0.2829 |
| GFN2 − PubChemQC，HOMO（n=161） | **−4.0199 eV** | 0.4490 | −5.0157 | −2.7098 |

HOMO 的偏移**规整**（σ 0.48 eV，可平移）；LUMO 的偏移**离散**（σ 2.48 eV，不可平移）。这与 3.2 的两条结论互相印证。

### 3.4 三方对照（同 166 个分子）

| 情形 | 分子数 |
|---|---|
| 同时有 Batt 与 PubChemQC | 72 |
| 只有 Batt | 2 |
| 只有 PubChemQC | 89 |
| **三个源都没有，只有本臂** | **3** |

那 3 个分子确实在本臂之前**没有任何轨道数值**，但它们的值来自一个没过门的通道，**只能当参考**，不许当作「补齐了」。

## 4. 诚实性设计（针对上一臂被审出的三个 P1）

W17-12 的独立审计指出：交付图分子分母错配、`unit_check` 对 872/912 行无依据地标 `verified_eV`、校验器对该列是自证式检查。本臂逐条改：

| 项 | W17-12 的毛病 | 本臂的做法 |
|---|---|---|
| 单位 | 40 行有证据，912 行都标 `verified_eV` | `unit_check` 是**管道级**声明，证据在 `data/raw/themol/unit_audit.json`：**独立重跑 8 个分子、同时读 Eh 与 eV 两列、残差 ≤ 4.49e-05 eV、8/8 通过**；不过则整列写 `unverified` |
| 结构 | 23 行 `named_solvent` 跳过校验 | `structure_check` **逐行**从该行自己的 SMILES 重算 InChIKey 再比对（166/166 `inchikey_match`）；校验器独立重算，不是常量比对 |
| 派生列 | — | 验证器逐行重算每一个偏移列 = 其两个源列之差；**这条检查真的抓到过一个 bug**：图层最初把数值四舍五入到 6 位小数，导致「四舍五入后的差 ≠ 差的四舍五入」，验证器 457 项失败 ⇒ 改为全精度存储 |
| 校准列 | LUMO 降级但 `calib_lumo_eV` 语义含混 | 三通道全部未过门 ⇒ `calib_homo_eV` / `calib_lumo_eV` / `calibration_id` **整列为空**，`roles` 里 `calibrated_estimate = 0` |

验证器：`scripts/verify_themol_orbital_layer.py --check`（CI 用，无需原始层）与 `--check-raw`（本地，重算逐字节比对）。

## 5. 许可与入库纪律

- THEMol 数据 **CC BY-NC 4.0**（非商用）。几何是衍生输入的来源 ⇒ 采集表留在 **`data/raw/themol/`（被 `.gitignore` 的 `data/raw/*` 覆盖）**。
- 进交付层的只有 `data/processed/themol_orbital_layer.csv`，逐行带 `source_dataset` / `source_level` / `source_license`。
- **加性**：Batt-P30K 列（`four_core_key_registry.csv`）与 PubChemQC 列（`orbital_second_source_layer.csv`）**一个字节都没改**。
- 本臂**不拟合任何预测模型**（`models_fitted = 0`、不报 R²）；3.2 的线性映射是**跨能级换算**，不是模型性能。

## 6. 与 2026-09-26 六分子 POC 的关系

agent Peirce 用 6 个分子（PC / GVL / THF / 乙腈 / 丙酮 / DOL）跑通了同一链路，当时的读数是「HOMO 系统偏负约 1.2 eV，LUMO 完全不在一个刻度上」。
本臂在 **74 个锚**上把这两句话钉成了数字：HOMO 均值 −1.06 eV（σ 0.48），LUMO 均值 −7.01 eV（σ 2.48）。**POC 的方向性结论成立，本臂给出的是它与判决。**

## 7. 结论与下一步

- **THEMol 值得用，但用在几何上，不是用在能级上。** 它的价值在 `coords`（乃至 Hessian、MBIS 多极），而这三类在本仓都没有第二家能补。
- **要真出 HOMO/LUMO，必须换引擎**：本机 `.venv` 无 PySCF、Windows 无官方 wheel ⇒ 需要 GPU4PySCF 或火山引擎 `volcengine-qcclient`（后者已在 `reports/decisions_log.md` §28.15 逐字段核过，可指定 xc/基组/隐式溶剂 ε，能与 Batt 口径对齐）。这一步需要作者批额度 + 预注册。
- **不建议**把 GFN2-xTB 的 LUMO/gap 以任何形式并入轨道通道——3.2 与 3.3 已经把「不可混用」证明到位。

## 8. 交付件

| 件 | 说明 |
|---|---|
| `probes/themol_hessian_orbitals.py` | 采集器：Range 读 H5 + xTB 单点，支持 `--shard/--nshards` 与 `--rebuild-index`（重流式下载 1.47 GB 索引） |
| `probes/build_themol_target_roster.py` | 由已提交表生成两份目标名册 |
| `probes/themol_orbital_unit_audit.py` | 单位独立审计（Eh×27.211386 与 eV 列比对） |
| `probes/build_themol_orbital_layer.py` | 图层构建 + 标定，`--check` 可逐字节重算 |
| `probes/themol_orbital_layer_prereg.json` | 预注册（门限逐字继承 W17-12） |
| `probes/themol_orbital_layer_summary.json` | 摘要（sha256、覆盖、标定、偏移、三方计数） |
| `data/processed/themol_orbital_layer.csv` | **166 行 × 34 列**，sha256 `6e05f02e755c57ab09d73a784687b2c1deb757f80e43c5746358f1f7a5ecde80` |
| `probes/plot_themol_orbital_layer.py` + `probes/artifacts/themol_orbital_layer_{calibration,coverage}.png` | 两张图 |
| `scripts/verify_themol_orbital_layer.py` | 独立验证器（`--check` / `--check-raw`） |
| `tests/test_themol_orbital_layer.py` | 16 项测试 |
| `data/raw/themol/` | 原始证据：索引、目标名册、4 个分片、单位审计（被 `.gitignore` 覆盖，本机保留） |