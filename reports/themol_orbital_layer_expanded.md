# W17-17　THEMol / GFN2-xTB 全量轨道扩展：把 W17-14 的 166 个分子做成 5,117 个

**一句话结论**：THEMol 的 Hessian 池覆盖本仓关键名册 **5,117 / 31,949** 个分子，W17-14 只跑了其中 166 个；
本臂把全部目标**冻结成名册**后用同一条 GFN2-xTB 单点链路跑到 **5,117 个（100.0%，`run_status = complete`）**，
其中 **291 个分子此前没有任何轨道数值**。跨水平标定样本从 **74 个锚**涨到 **4,668 对**，
W17-14 那条「差 **0.0031 eV** 没过门」的 HOMO 通道因此**翻过门**（r **0.8549**、MAE **0.3036 eV**）；
而 **LUMO 与 gap 仍是 `reference_only`**——「半经验紧束缚的虚轨道不可用」被更大的样本重新确认。

## 1. 为什么做这一臂

W17-14 的结论只建立在 **74 个配对锚**上：THEMol 值得用的地方是几何，不是能级。那句话方向对，
但样本小到一个通道只差 **0.0031 eV** 就能翻转结论。既然覆盖本身写着 **5,117**，就应该把这 5,117 跑完再下判断。

本臂同时回答作者的两个问题：**「HOMO/LUMO 数据是否已经收集」**（是，且比 W17-14 多一个数量级）与
**「能不能用 THEMol 补 HOMO/LUMO」**（能补参考值，不能当标签）。

## 2. 方法（与 W17-14 完全相同，只换样本量）

```
probes/themol_registry_expansion_roster.csv（运行前冻结，5817 → 实际 5,117 行）
   ↓ 按 hessian_N.h5 整组 round-robin 分 10 片
HTTP Range 读 THEMol 几何（不落 .h5）→ XYZ → electrolyte_ml.xtb_runner → GFN2-xTB --sp
   ↓ 写 data/raw/themol/expand/shard_*.csv（git-ignored）
probes/build_themol_orbital_layer_expanded.py → data/processed/themol_orbital_layer_expanded.csv
```

名册分四层（跑之前就定好，逐行落 `expansion_tier`）：**无参考轨道 421**、**旗舰 ε 名册 54**、
**其他核心通道 68**、**有 Batt 标签的标定主体 4,574**。

### 2.1 两处必须记下来的工程事实

- **镜像会限流**：10 路并发时 `hf-mirror` 开始返回 HTTP 429，第一版没有退避，一个分片 419 个目标里
  413 个直接失败。处置：给 `probes/themol_hessian_orbitals.py` 加**指数退避重试**（4 次、1→10 s、带 jitter，
  尊重 `Retry-After`）、拆分连接/读取超时（10 s / 25 s）、每分子 0.12 s 节流，并做**断点续跑**
  （续跑只跑还没拿到数值的键，重跑行按「有数值优先」去重）。
- **中途会黑洞**：一次约 55 分钟的全员静默里，10 个进程 CPU 时间为 0、CSV 停在同一分钟。
  收紧超时后同样的窗口只花约 4 分钟就能跳过。这是本臂 `run_status = complete` 的原因，不是数据问题。

## 3. 结果

### 3.1 覆盖

| 口径 | 命中 | 分母 |
| --- | --- | --- |
| 冻结名册（关键名册 ∩ THEMol） | 5,117 | 31,949 |
| **本臂交付（有 GFN2 数值）** | **5,117** | 5,117 |
| 其中「此前没有任何轨道数值」 | 291 | 421（无参考轨道层） |
| ε 名册命中 | 142 | 247 |

分层交付：无参考轨道 **421**、旗舰 ε **54**、其他核心通道 **68**、标定主体 **4,574**。

### 3.2 跨水平标定（对 Batt-P30K，2 折样本外，与 W17-14 同门限）

| 通道 | n | slope | intercept | r | 样本外 MAE | 最大误差 | 判定 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HOMO | 4,668 | 0.8702565775 | -0.2042104026 | **0.8549** | **0.3036 eV** | 1.7121 eV | **usable_with_flag** |
| LUMO | 4,668 | 0.1497 | +2.2123655237 | 0.6141 | 0.3495 eV | 3.2032 eV | `reference_only` |
| gap | 4,668 | 0.1675275933 | +10.1616232897 | 0.4343 | 0.5910 eV | 4.9144 eV | `reference_only` |

门限 **MAE ≤ 0.35 eV 且 r ≥ 0.80**，逐字继承 `probes/orbital_second_source_prereg.json`。
W17-14 在 74 个锚上得到 HOMO r 0.8557 / MAE 0.3531（**差 0.0031 没过**）；本臂把样本放大到 **4,668** 后为
r **0.8549** / MAE **0.3036**。**结论变化要如实说**：HOMO 从 `reference_only` 变成 `usable_with_flag`，
但由于最大单点误差仍有 **1.7121 eV**，它只配一个**带旗标的**换算，不配当标签用。

### 3.3 能级偏移（GFN2 − Batt）

| 通道 | 均值 | σ | min | max |
| --- | --- | --- | --- | --- |
| HOMO | **-1.2052 eV** | 0.4046 | -3.0481 | +0.4635 |
| LUMO | **-7.5377 eV** | 1.9654 | -10.5861 | -0.8129 |
| gap | **-6.3325 eV** | 1.9545 | -9.3423 | +0.2829 |

HOMO 的偏移规整（σ 0.4046 eV，可平移）；LUMO 离散（σ 1.9654 eV，不可平移）——与 3.2 互相印证。

## 4. 诚实性与边界

- **`run_status = complete`**：交付 5,117 / 5,117。**没有跑到满分就不写满分**；续跑用同一份冻结名册，
  剩下的键随时可以接着跑。
- `structure_check` **逐行**从该行自己的 SMILES 重算 InChIKey（5,117 命中 / 0 不匹配 / 0 不可解析）。
- `unit_check` 是**管道级**声明，证据是 W17-14 的 `data/raw/themol/unit_audit.json`（独立重跑 8 分子、残差 ≤ 4.49e-05 eV）。
- **不拟合预测模型**（`models_fitted = 0`、不报 R²）；3.2 的线性映射是**跨能级换算**，不是模型性能。
- **Batt-P30K 与 PubChemQC 两列一个字节未改**；交付层是**新增文件**，`four_core_key_registry.csv` 未被触碰。
- 一条独立的复现臂（W17-19）在**第二条手写代码路径**上重跑了 W17-14 的 ε 子集：ΔHOMO 最大 1×10⁻⁴ eV、
  `themol_uuid` 一致率 100% ⇒ 两条链路互相复现，交付列可信。

## 5. 许可

THEMol 数据 **CC BY-NC 4.0**（代码 Apache-2.0）。几何是衍生输入的来源 ⇒ 原始开采表留在
**`data/raw/themol/expand/`（被 `.gitignore` 覆盖）**；进交付层的是每行带 `source_dataset` / `source_level` /
`source_license` 的派生数值，与 `data/processed/themol_orbital_layer.csv` 一起登记在 `LICENSE-DATA.md` 的**许可切分**节。

## 6. 交付件

| 件 | 说明 |
| --- | --- |
| `probes/build_themol_registry_expansion_roster.py` / `probes/themol_registry_expansion_roster.csv` | 冻结名册（5,117 行）与生成器（`--check` 逐字节） |
| `probes/themol_registry_expansion_prereg.json` | 运行前锁定的预注册（名册 digest、方法、门限、判据） |
| `probes/build_themol_orbital_layer_expanded.py` | 交付层生成器（复用 W17-14 的标定函数） |
| `data/processed/themol_orbital_layer_expanded.csv` | 交付层 5,117 行 × 35 列 |
| `scripts/verify_themol_orbital_layer_expanded.py --check` | 独立验证器（不 import 生成器，自己重算标定） |
| `probes/plot_themol_registry_expansion.py` + 两张 PNG | 覆盖图与标定图 |
| `tests/test_themol_registry_expansion.py` | 离线测试 |

## 7. 收尾补记（交付后追加，不覆盖上文）

**（a）失败重试把最后 268 个键补齐。** 主轮结束时 5,117 个键里有 271 个只留下 `error:HTTPError` 行
（单分子级 429，10 路并发下随机发生，错误均匀分布在 10 个 shard 上）。用同一份冻结名册做重试：
`retry_roster.csv`（268 行，sha256 `66cbc7740bbbdb83dea98d6bc73bcdfb5be25064286cca88188ffc8e8640e00d`）恢复 261 个，
`retry2_roster.csv`（40 行，sha256 `73d3e5fdddaad8b822d4425b4ef143b1257fb96b4b402d34c23eecb940b0579a`）把剩下 40 个**全部**拿到。
最终 `run_status = complete`（5,117 / 5,117，`failed_rows = 0`）；原始分片共 5,419 行，
`duplicate_collisions = 302`、`duplicate_upgrades = 117`（重试把"失败行"升级成"有数值行"的次数）。

**（b）对抗审计的发现与处置。** 独立审计（`reports/themol_expanded_layer_audit.md`）对本臂提了 9 条，处置如下：

- **F2 计数守卫曾是死代码**（off-roster 行在计数之前就被 `continue` 丢掉，重复只在一种碰撞下计数）⇒ **已修**。
  修完立刻吐出真实信息（302 次碰撞 / 117 次升级），`rows_off_roster` 现在是真的 0 而不是"偶然的 0"。
- **F1 判闸混用样本内 r** ⇒ **已修**：`status` 现在只由**样本外** MAE 与**样本外** r 决定
  （`status_basis = out_of_sample_mae_and_out_of_sample_r`），样本内 r 仍照报。实测 HOMO r_in 0.8549 / r_oos 0.8545
  ⇒ **结论不翻转**（LUMO/gap 两种口径都远低于 0.8 门）。
- **F6 单位证据只有 8 个分子、而且属于 W17-14** ⇒ **已补本层自己的证据**：`probes/themol_expand_unit_recheck.py`
  用**自带的 occupation 解析器**（不调用 `parse_orbitals`）在 **24 个抽样分子**上重新取几何、重跑 xTB、重解析，
  并逐行核对几何 digest：**ΔHOMO = ΔLUMO = 0.0 eV，24/24 passed**。抽样占比 **0.47%**——
  也就是说这仍然**不是**全量复现，`unit_check.this_layer_evidence` 里已把这一点写死，不靠读者自己发现。
- **F7 `models_fitted = 0` 与"文里有拟合"读起来矛盾** ⇒ **已补** `models_fitted_note`：本臂不训练任何目标性质模型，
  唯一被拟合的是 `calibration` 里的跨能级线性映射，它不是模型性能。
- **F8 预注册交付的报告当时还不存在** ⇒ 即本文件。

**（c）THEMol 里到底有什么（逐字节实测，见 `reports/themol_property_inventory.md`）。** H5 实测键名并集 13 个，
**没有任何 eigenvalue / gap / HOMO / LUMO / IP / EA**：THEMol 提供的是 DFT 几何、DFT Hessian、轨迹能量，
以及 **MBIS 原子布居**（PBE0/def2-TZVPD 的逐原子电荷/偶极/四极/体积，3,082,151 分子）。
⇒ **本仓所有 THEMol 轨道数都是我们自己跑 GFN2-xTB 算出来的**，所以必须走上面的跨水平标定；
MBIS 那一路**可能**对 ε / DN 有用，但"有预测力"目前仍只是推断，需要另做下游对照实验。

**（d）诚实的边界。** 属性普查那一臂的下载量为 ~108 MB，**超出其 50 MB 硬约束**（侦查阶段误用整包 GET 读索引，
加上首轮两个代码 bug 作废一次），已在 `probes/themol_property_inventory.json` 的 `download_accounting` 里如实记账，
未做任何隐藏。
