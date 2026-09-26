# 室温窗口配对口径：窗口外那 950 行该不该进训练面

**日期：** 2026-09-25
**探针：** `probes/dielectric_room_window_paired.py`
**测试：** `tests/test_dielectric_room_window_paired.py`（62 passed，全离线：合成小数据 + 桩预测器）
**产物：** `probes/dielectric_room_window_paired_summary.json`、`probes/artifacts/dielectric_room_window_paired_{folds,repeats,predictions}.csv`
**输入指纹：** `dielectric_observations_v11.csv` → `7803587afabdec1fcf9cfd319bb64d23f83af8d3fe07124df75052cfcd6a75fc`；`dielectric_physical_features_v03.csv` → `b36d3439560e4381b7779565b9950eed379832e832b72ea6a3a010662ed24fa3`（与 `dielectric_band_ablation_summary.json` 记录的输入指纹一致）
**复现命令：** `.\.venv\Scripts\python.exe -u probes\dielectric_room_window_paired.py`
**只读声明：** 未改动 `data/dielectric_v03.csv`、`data/processed/dielectric_observations_v11.csv`、`probes/dielectric_band_ablation.py`、`probes/dielectric_observations_grouped_benchmark.py`、`probes/dielectric_compound_coverage_curve.py`、任何 `paper/*`、`.gitignore`、`.github/workflows/*`。全部交付物为新建文件。

## 一、结论先行

1. **窗口外的行进训练面是净亏，而且是配对实测的。** 在完全相同的折与完全相同的打分池（457 行室温带 / 97 化合物）下，把训练面从「室温带 457 行」依次铺到「+extended 644 行」「全部 1,594 行」：
   Hybrid R² **0.4091 → 0.3625 → 0.3230**，两段分别 **−0.0466** 与 **−0.0395**，合计 **−0.0861**。MAE 同步恶化（8.0407 → 8.3202 → 8.5436，合计 +0.5029）。Spearman 几乎不动（0.7763 → 0.7721 → 0.7792，合计 +0.0030）。三个数字同向读，是「预测被压向均值」的典型签名，不是排序能力提升。
2. **把训练面铺满会跌破 v1.0。** `train_all_test_room` 的 0.3230 **低于** v1.0 冻结基准的 0.3636。为了窗口内打分更好而把训练面铺到窗口外，是负收益且跨过了 v1.0 这条线。
3. **但「同一窗口内更多的观测值」进训练面是小幅正收益——这是本次唯一的新增正面结论。** 在 97 化合物池、打分池字节相同（同为 97 行、方差 583.2199）的严格配对下：训练面 97 行 → 457 行，Hybrid R² **0.2198 → 0.2299（+0.0101，判 helps）**，Spearman +0.0178。**但 MAE 反向恶化 +0.2193**（10.4321 → 10.6513）——黏度线那条「MAE 变好不等于模型变好、反过来 MAE 变坏也不等于模型变坏」的护栏在这里再次生效，故正收益按 R² 与 Spearman 双确认后仍标注为「小、且只在窗口内」。
4. **配对版 v1.0 对账：0.4091 仍然不能宣称超过 v1.0 的 0.3636。** 在同池同折的 97 化合物上：v1.0 冻结行 0.2158 → v1.1 单行 0.2198 → 全室温行 0.4091。三步里最大的一步（+0.1792）来自**被打分池变了**（97 行 → 457 行），不是模型变好；真正归因于「多用数据去拟合」的只有 +0.0101。把被打分池锁死（只给每化合物 1 行）后，v1.1 的最好成绩是 **0.2299**，与 v1.0 的 0.3636 之间的缺口来自**化合物覆盖（236 → 97）**，不是温度维度。
5. **五处自检逐位一致**（详见第六节）：`band_room_only` 0.4091、`band_all` 0.1602 与 band ablation 逐位一致（`max_abs_delta = 0.0`，3 个表示 × 7 个指标）；分折器与 `grouped_folds` 等价（从索引数组反算，`identical=True`）；冻结 236 端点重放 `bit_exact=True`；`cohort_room_rows` 与 `band_room_only` 逐位相同（0.4091 / 8.0407 / 0.7763）。

**一句话判决：窗口外的行不进训练面（配对实测 −0.0861，且铺满即跌破 v1.0）；同一窗口内、同一化合物的更多观测值可以进，但只值 +0.0101，且 MAE 反向。**

## 二、为什么必须做配对口径（`dielectric_band_ablation.md` 的两处留白）

band 消融报告自己标注了两个不能回答的问题：

- **§7.4**：`train_core_test_room`（训练=room+ext，测试=room）与 `train_all_test_room`（训练=全部，测试=room）**没跑**。原报告只证明了「为了让窗口内打分，把**测试面**铺到窗口外不行」，而 v1.x 真正要决定的是「把**训练面**铺到窗口外行不行」。
- **§6**：`band_room_only`（0.4091）与 v1.0（0.3636）**目标池不配对**（被打分池方差 335.64 vs 580.30），所以不能宣称反超。

本探针把这两件事都用严格配对口径补上。「配对」的定义是：**同一折构造、同一化合物池、同一被打分行集**，delta 只归因于唯一变动的那一项。

## 三、八个口径与配对规则

冻结管线不动：Morgan(2048, r=2) / Physical(13 维 xTB，`T_K` 换成本条观测自己的温度) / Hybrid(两者 0.5 等权平均)，`XGBRegressor` 用 v1.0 的 `XGB_PARAMS` 原值，`SEED=42`，10×5。

### 3.1 窗口家族（4 条，前 3 条严格配对）

| 口径 | 训练行 | 被打分行 | 训练池行数 | train/fold | test/fold |
| --- | --- | --- | ---: | ---: | ---: |
| `band_room_only` | room | room | 457 | 365.6 | 91.4 |
| `train_core_test_room` | room + extended | room | 644 | 521.6 | 91.4 |
| `train_all_test_room` | 全部 | room | 1,594 | 1304.2 | 91.4 |
| `band_all` | 全部 | 全部 | 1,594 | 1275.2 | 318.8 |

`band_room_only` → `train_core_test_room` → `train_all_test_room` 只动训练面；三条的被打分行集**字节相同**（`identical_scored_rows=True`，50 折共 4,570 个被打分条目，被打分池方差同为 335.6435）。

### 3.2 cohort 家族（4 条，配对版 v1.0 对账）

化合物池锁定为 **v1.0 建模池 236 ∩ v1.1 建模池 98 = 98**，其中 97 个有室温带行（`cohort`）：

| 口径 | 每化合物行数 | 标签 | 训练池 | 被打分行 |
| --- | --- | --- | ---: | ---: |
| `cohort_v10_frozen` | 1（v1.0 表本身） | v1.0 冻结 `dielectric` | 97 | 97 |
| `cohort_single_row` | 1（最接近 298.15 K 的室温行） | v1.1 观测 | 97 | 97 |
| `cohort_room_train_single_test` | 训练=全部室温行，打分=单行 | v1.1 观测 | 457 | 97 |
| `cohort_room_rows` | 全部室温行 | v1.1 观测 | 457 | 457 |

### 3.3 配对规则（写死在代码里）

**折只在被打分掩码的化合物上发牌**（`masked_splits`）。两个口径只要被打分化合物集合相同，就必然拿到同一份折；`train_mask` 只决定「别的折里哪些行能进拟合」。因此换训练面**不会**动折归属，也不会把被留出的化合物漏回训练侧（`audit_masks` 从索引数组反算：50 折 × 8 口径，`folds_with_a_straddling_compound = 0`、`train_rows_offered_but_unused = 0`——即所有可用的扩宽行都真的用上了，没有静默丢弃）。

发牌函数 `fold_of_by_repeat` 与 `grouped_folds` 的规则逐位相同，并且**在探针里现场反算比对**（`own_mode_equivalence`，`identical=True`）。

## 四、窗口家族：同折同打分池，只换训练面

Hybrid 表示，10×5（mean ± std over 10 repeats）：

| 口径 | R² | MAE | RMSE | Spearman |
| --- | ---: | ---: | ---: | ---: |
| `band_room_only` | **0.4091** ± 0.0890 | 8.0407 | 14.0504 | 0.7763 |
| `train_core_test_room` | 0.3625 ± 0.0690 | 8.3202 | 14.6087 | 0.7721 |
| `train_all_test_room` | 0.3230 ± 0.0573 | 8.5436 | 15.0616 | 0.7792 |
| `band_all`（参照，打分池不同） | 0.1602 ± 0.1106 | 10.2924 | 16.9471 | 0.4595 |

配对链（含 MAE 与 Spearman，防止只看 R² 误判）：

| 配对步 | ΔR² | ΔMAE | ΔSpearman | 判决 |
| --- | ---: | ---: | ---: | --- |
| `band_room_only` → `train_core_test_room`（+extended 187 行） | **−0.0466** | +0.2796 | −0.0042 | hurts |
| `train_core_test_room` → `train_all_test_room`（再 +窗口外 950 行） | **−0.0395** | +0.2233 | +0.0071 | hurts |
| `band_room_only` → `train_all_test_room`（合计） | **−0.0861** | +0.5029 | +0.0030 | hurts |

**读法：**

- 两段都是负贡献，但**第一段（贴窗口上沿的 extended 带，313.15–323.15 K，187 行 / 45 化合物）比第二段（其余窗口外 950 行：<293.15 K 543 行、303.15–313.15 K 空档 134 行、>323.15 K 273 行）更贵**。也就是说「就在窗口边上、看着最无害的那批」不是更划算，反而更伤。这条与 band 消融的「窗口外不是贴着边缘的一点点外推，86% 离窗口 5 K 以外」一起读：伤害不来自温度跨度本身，而来自「同一化合物在别的温度上 ε 变了，而模型只能给一个与温度无关的主预测」。
- Spearman 在两段里 ±0.01 内浮动、合计只 +0.0030，而 MAE 单调恶化 +0.5029：这是**预测被压向均值**（方差变小、排序没变好）的签名。所以「加窗口外数据当正则」这条机制被否证。
- `train_all_test_room`（0.3230）< v1.0（0.3636）：**训练面铺满窗口外，连 v1.0 这条线都守不住。**
- 训练侧化合物数从 97 增到 98（多出 `LCGLNKUTAGEVQW-UHFFFAOYSA-N`，它是**只有 extended 行、没有室温行**的那个化合物）：它在每一折里都是「训练专用」（`training_only_compounds` 已如实列出），不会被留出。这也是 `train_all_test_room` 的 train/fold（1304.2）略高于 `band_all`（1275.2）的原因。

## 五、cohort 家族：配对版 v1.0 对账

**化合物池锁定结果：** v1.0 建模池 236 行，v1.1 建模池 98 个化合物，**98 个全部落在 v1.0 的 236 名录里**（v1.1 在 v1.0 名录之外的化合物：**0 个**）；其中 `LCGLNKUTAGEVQW-UHFFFAOYSA-N` 没有室温带行，被排除，`cohort = 97`。反向看，v1.0 的 236 个里只有 98 个进了 v1.1，另外 138 个没有观测级温度数据。

Hybrid 表示，10×5：

| 口径 | 被打分行 | R² | MAE | RMSE | Spearman | 被打分池方差 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `cohort_v10_frozen` | 97 | 0.2158 ± 0.0658 | 10.5055 | 21.3171 | 0.6682 | 580.3621 |
| `cohort_single_row` | 97 | 0.2198 ± 0.0617 | 10.4321 | 21.3164 | 0.6796 | 583.2199 |
| `cohort_room_train_single_test` | 97 | **0.2299** ± 0.0458 | 10.6513 | 21.1843 | 0.6974 | 583.2199 |
| `cohort_room_rows` | 457 | 0.4091 ± 0.0890 | 8.0407 | 14.0504 | 0.7763 | 335.6435 |

配对链：

| 配对步 | 变动的东西 | ΔR² | ΔMAE | ΔSpearman | 判决 |
| --- | --- | ---: | ---: | ---: | --- |
| `cohort_v10_frozen` → `cohort_single_row` | 标签来源（v1.0 精选值 → v1.1 原始观测） | +0.0040 | −0.0735 | +0.0113 | inert |
| `cohort_single_row` → `cohort_room_train_single_test` | **只加训练行**（97 → 457），被打分池字节相同 | **+0.0101** | +0.2193 | +0.0178 | **helps（小）** |
| `cohort_room_train_single_test` → `cohort_room_rows` | 只加被打分行（97 → 457） | +0.1792 | −2.6106 | +0.0788 | helps |
| `cohort_single_row` → `cohort_room_rows` | 两者一起 | +0.1893 | −2.3914 | +0.0967 | helps |

**读法：**

- **唯一可以当「模型变好」读的是第二行（+0.0101）**：这是本次唯一被证明字节配对的「多观测值进训练面」步（`identical_scored_rows=True`，被打分池方差同为 583.2199，被打分池 970 个条目完全一致）。它小，但在 10 次重复的均值上越过了 0.005 的惰性阈值，且 R² 与 Spearman 同向；MAE 反向 +0.2193，按护栏规则不予采信。
- **+0.1792 那一行不能当模型改进读**：训练行没变（457），只有被打分行从 97 增到 457。同一个模型在不同的被打分集上打分，R² 分母变了，所以它是「口径差」而不是「能力差」。这正是 §6 那条「不配对」警告**在同一化合物池内部**也成立——这正是回答配对版 v1.0 对账的关键。
- **v1.0 侧锚点**：`cohort_v10_frozen` 用 v1.0 自己的特征与标签、在同样 97 个化合物、同样 grouped 折下拿 0.2158。作为对照，本探针把 v1.0 的 236 化合物冻结端点重放了一遍：R² = 0.36357268752900124（`bit_exact=True`，与发布值逐位一致）。所以 0.3636 → 0.2158 这个落差是**化合物池从 236 缩到 97** 造成的。仓库里已有一条独立的覆盖曲线（`reports/dielectric_compound_coverage_curve.md`：60 → 0.216、90 → 0.216、120 → 0.234、160 → 0.310、200 → 0.343、236 → 0.364），97 化合物落在 0.216–0.234 区间内，量级一致；但那条曲线用的是 v1.0 的行级折，本次是 grouped，故只作量级印证，不作配对相等。
- **标签来源这一步是 inert（+0.0040）**：把 v1.0 的精选值换成 v1.1 的原始观测，在同池同折下不改变结论。诚实标注：这一步除标签外还动了 12/97 行的 `T_K`（中位 0、最大 5.01 K）与 26/97 行的 ε（中位 0、最大 1.25），所以它不是纯粹的单变量步。
- **`cohort_room_rows` ≡ `band_room_only` 逐位相同**（0.4091 / 8.0407 / 0.7763 / 14.0504）：cohort 的室温行就是室温带本身，两个独立路径给出同一结果，反证 cohort 的池锁定没有引入偏差。

## 六、复现自检（全部来自本次实测，不引用外部数字）

| 自检 | 结果 |
| --- | --- |
| `band_room_only` vs band ablation 同名口径 | **bit_exact=True，`max_abs_delta = 0.0`**（Morgan / Physical / Morgan+Physical × 7 个指标） |
| `band_all` vs band ablation 同名口径 | **bit_exact=True，`max_abs_delta = 0.0`** |
| 分折器 vs `grouped_folds`（从索引数组反算） | `band_room_only` identical=True（50 折 / 457 行）、`band_all` identical=True（50 折 / 1,594 行） |
| v1.0 冻结 236 端点重放（`verify_frozen_endpoint`） | rows=236、failed=4、withheld=1、**bit_exact=True、`max_abs_delta = 0.000e+00`** |
| 配对契约（从 predictions 逐行指纹反算） | 窗口三条：`identical_scored_rows=True`；cohort 的 `single_row → room_train_single_test`：`True`（其余步按设计为 False） |
| 泄漏审计 | 8 个口径 × 50 折：`folds_with_a_straddling_compound = 0`，`max_straddling_compounds_in_a_fold = 0` |
| 输入指纹 | 与 band ablation 摘要记录的 `observations_sha256` / `features_sha256` 逐字符一致 |

`random_row` 行级折在本次**没有使用**，也不作为任何结论数字。

### 一处已修的自检缺陷（如实记录）

第一版 `run_cohort_family` 的「折是否共享」判据写成 `len(set(assignments)) == 1`——这是**错的**：不同 repeat 本来就该拿到不同的化合物排列，所以 10 个 repeat 天然产生 10 个不同的分配。真值因此被误报为 `False`（首次全量运行的 JSON 里就写着 `false`）。正确的不变量是**同一 repeat 内**四个口径共用一份分配。判据已按此重写并复跑全量；同时补了一条 `n_repeats=2` 的回归测试（`test_run_cohort_family_shares_the_folds_across_repeats`）——原来的测试只用 1 个 repeat，正好把这个 bug 掩盖住了。R² / MAE / Spearman 数值不受影响（错的只是那个布尔量），重跑后逐位相同。

## 七、判决与对 v1.x 的含义

1. **窗口外的行不进训练面。** 配对实测 −0.0861，两段同向为负，且铺满后 0.3230 跌破 v1.0 的 0.3636。这一条现在有同折同打分池的直接证据，不再是从「测试面有害」外推的。
2. **窗口内的多观测值可以进训练面，但要按小收益对待。** +0.0101（R² 与 Spearman 同向，MAE 反向）。所以 v1.x 的正确姿势是「**在 293.15–303.15 K 内把同一化合物的更多观测灌进训练面**」，而不是「把温度闸门整体打开」。
3. **不要用 `band_room_only` 的 0.4091 宣称超过 v1.0。** 锁定被打分池后，v1.1 的最好成绩是 0.2299，v1.0 冻结口径在同池上是 0.2158。缺口来自化合物覆盖（236 → 97），与温度维度无关——这与覆盖曲线「杠杆是化合物覆盖，不是温度覆盖」的结论互相独立地印证。
4. **报告纪律**：凡是被打分行集变过的口径对比，一律不得当作模型能力对比；R² 必须与 Spearman 同报，MAE 只作护栏。

## 八、局限与未做

- 只跑了冻结的 XGBoost 混合表示；LPR / MLP / Chemprop 未跑，所以结论的适用范围是「v1.0 这条管线」。
- cohort 家族锁死了**化合物池与折**，但没有锁死**被打分行数**；只有 `cohort_single_row → cohort_room_train_single_test` 这一步是被打分池字节相同（已由逐行指纹证明）的严格配对步。其余步的 ΔR² 含口径差，报告里已逐条标明。
- `cohort_v10_frozen → cohort_single_row` 除标签外还动了 12/97 行的 `T_K`（最大 5.01 K），所以「标签来源」这一步不是纯单变量。
- 温度带口径来自 `scripts/build_dielectric_observations.py`：room = 293.15–303.15 K、extended = 313.15–323.15 K，**303.15–313.15 K 的空档（134 行）也算窗口外**。本次沿用，未改动定义。
- 没有做超参搜索，全部用冻结的 `XGB_PARAMS`。
- `train_all_test_room` 与 `band_all` 的 train/fold 差异（1304.2 vs 1275.2）来自「被留出的化合物组成不同 + extended-only 化合物在每折都是训练专用」，不是实现偏差。

## 九、产物与复现

| 文件 | 内容 |
| --- | --- |
| `probes/dielectric_room_window_paired_summary.json` | 口径定义、配对规则、8 个口径的行/化合物/折统计、审计、目标池方差、两族配对链、逐行配对契约、band ablation 复现对照、冻结端点重放 |
| `probes/artifacts/dielectric_room_window_paired_folds.csv` | 逐折指标（protocol × representation × repeat × fold × 11 列） |
| `probes/artifacts/dielectric_room_window_paired_repeats.csv` | 逐重复 7 项指标 |
| `probes/artifacts/dielectric_room_window_paired_predictions.csv` | 逐条预测（含 InChIKey / T_K / 真值 / 预测），配对契约就是从这里反算的 |
| `tests/test_dielectric_room_window_paired.py` | 62 项离线测试：发牌一致性、配对掩码、审计、目标池方差、配对契约、cohort 锁定、端到端产物与 LF |

```powershell
.\.venv\Scripts\python.exe -m ruff check probes\dielectric_room_window_paired.py tests\test_dielectric_room_window_paired.py
.\.venv\Scripts\python.exe -m pytest tests/test_dielectric_room_window_paired.py -q
.\.venv\Scripts\python.exe -u probes\dielectric_room_window_paired.py
```

三个 CSV 全部 **LF only**（无 `\r\n`），与 `.gitattributes` 的 `* text=auto eol=lf` 一致。