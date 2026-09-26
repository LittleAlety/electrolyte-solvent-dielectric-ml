# P4 氧化还原基线 v2：富特征探针（门仍为红，且已定位瓶颈）

**日期：** 2026-09-26（Asia/Shanghai）
**探针：** `probes/p4_redox_v2_enriched.py`
**测试：** `tests/test_p4_redox_v2_enriched.py`（25 条守卫，只读产物，不重跑 CV 网格）
**产物：**
- `probes/p4_redox_v2_summary.json`
- `probes/artifacts/p4_redox_v2_repeated_cv.csv`（折记录，列照 `data/processed/dielectric_gpr_repeated_cv.csv`）
- `probes/artifacts/p4_redox_v2_predictions.csv`（预测明细，51744 行）
- `probes/artifacts/p4_redox_v2_learning_curve.csv`（学习曲线）

**输入指纹：** `data/processed/redox_merged.csv` → `5b0731db9f1af784e6dc672212bcfe5d2fa68219a2832dafac6063dff9062b65`
（与 `probes/p4_redox_summary.json → merged.sha256` 逐位相同，说明输入未被改动）；
`data/external/Batt-SLM-RX-392.csv` → `d30ec1ffccba15538bac0b67157c14e045f1721441be23837c6195eca24a5d87`。

**复现命令：** `.\.venv\Scripts\python.exe -u probes\p4_redox_v2_enriched.py`
（加 `--skip-learning-curve` 可跳过学习曲线，快 ~4 分钟）

**只读声明：** 未改动 `probes/p4_redox_summary.json`、`probes/p4_redox_baseline.py`、
`data/processed/redox_merged.csv`、`data/external/Batt-SLM-RX-392.csv`、`reports/decisions_log.md`、`.gitignore` 与手册；
也未触碰另两位写手的 `probes/homo_lumo_baselines*`、`probes/l3_stage1_pilot*`。

**产物落点说明（与 v1 不同的地方，及原因）：** v1 把预测表放在 `data/processed/`，但 `.gitignore` 第 21 行是
`data/processed/*` 后跟逐文件白名单，新文件默认被忽略；我没有 `.gitignore` 的写权限（且该文件此刻已被他人改动），
若把 CSV 放在 `data/processed/` 会导致干净克隆缺文件、CI 变红。因此 v2 的折记录/预测/学习曲线 CSV 落到
`probes/artifacts/`——这正是本仓库 `dielectric_band_ablation_*`、`dielectric_coverage_placebo_arms_*`
等探针的一贯落点（列名契约仍按 `data/processed/dielectric_gpr_repeated_cv.csv`）。

## 一、目的

v1（`probes/p4_redox_baseline.py`）对每个目标只用**一列特征**：氧化用 `IP`、还原用 `EA`
（`TARGET_FEATURES = {"oxidation_free_energy": "IP", "reduction_free_energy": "EA"}`）。所以
`gate.best_model_mae` 的两枚数字实际上是**单特征线性回归**的留出误差。

本探针问一个更窄的问题：**把特征换成「结构派生量 + 该数据自带 IP/EA」的富特征集之后，冻结的 0.15 eV 门会不会变绿？**

要求是「如实判定」，所以两条口径都报，并额外给出**训练残差**与**学习曲线**，用来把「模型不够强」和
「n=392 标注量不够」这两件事分开。结论写在第八节，不粉饰。

## 二、复现锚点

探针在任何写盘动作之前先重算两枚锚点，任一枚漂移就抛异常终止（不会产出半成品）：

| 锚点 | 期望值（来自 v1 产物） | 本次复现值 | 判定 |
| --- | --- | --- | --- |
| 78 行留出集 `test_id_hash` | `dba15cd8c3a99215cc3e1fd5b2a73b9a5c0275eb2ee41fba436bcf62f2d2daee` | 同左（逐位相同） | 通过 |
| `oxidation_free_energy` `linear` MAE | `0.2905180517963865` | `0.2905180517963865` | 通过（容差 1e-9，实差 0） |
| `oxidation_free_energy` `linear` R² | `0.9443164629360373` | `0.9443164629360373` | 通过（容差 1e-9，实差 0） |

切分用先例函数复现：`from probes.dielectric_gpr_baseline import deterministic_split`，
`deterministic_split(392, test_fraction=0.2, seed=42)` → **314 训练 / 78 测试**（与 v1 summary 的
`split.train_count / test_count` 一致）。哈希算法与 v1 相同：`sha256("|".join(row_id))`，
按**数据集原始下标升序**（不是按 id 字典序）拼接——这一点是实测出来的：按 id 字典序拼接会得到
`4e4028fd…`，与冻结值不符；按原始下标升序才得到 `dba15cd8…`。

另有独立于探针的一道检查：测试 `test_predictions_recompute_the_frozen_heldout_hash` 只用
**预测明细 CSV 里的 `row_id`/`split` 两列**就把这枚哈希重算出来，等于对「留出集确实是那 78 行」做了第二源验证。

这两枚锚点也直接从 v1 产物文件交叉核对（测试 `test_anchor_reproduces_v1_oxidation_linear`
比对 `probes/p4_redox_summary.json → metrics.oxidation_free_energy.linear`），而不是只信自己写下的常量。
## 三、两条口径读数

### 3.1 口径 (a)：预注册留出口径（同一 78 行留出集）

与 `gate.best_model_mae` 可直接比较。全部模型都在同一 314 行上拟合、在同一 78 行上打分。

**氧化 `oxidation_free_energy`（eV，80% 留出集上）**

| 模型 | MAE | RMSE | R² |
| --- | ---: | ---: | ---: |
| `linear_scalar`（= v1 `linear`，单特征 `IP`） | 0.2905 | 0.3791 | 0.9443 |
| `ridge_enriched`（富特征 + GCV ridge） | 0.2968 | 0.3759 | 0.9452 |
| `gpr_enriched`（13 维紧凑 + GP） | 0.2471 | 0.3536 | 0.9515 |
| **`xgb_enriched`（富特征 + XGB）** | **0.2174** | **0.3406** | **0.9551** |
| `xgb_structure_only`（去掉 IP/EA 的消融） | 0.5939 | 0.8700 | 0.7067 |
| `dummy_mean`（均值预测，对照） | 1.1300 | 1.6139 | −0.0093 |

**还原 `reduction_free_energy`（eV，80% 留出集上）**

| 模型 | MAE | RMSE | R² |
| --- | ---: | ---: | ---: |
| `linear_scalar`（= v1 `linear`，单特征 `EA`） | 0.4153 | 0.6597 | 0.7351 |
| `ridge_enriched` | 0.4675 | 0.6361 | 0.7537 |
| `gpr_enriched` | 0.3618 | 0.5705 | 0.8019 |
| **`xgb_enriched`** | **0.3317** | **0.5173** | **0.8371** |
| `xgb_structure_only` | 0.5899 | 0.8106 | 0.6000 |
| `dummy_mean` | 1.1171 | 1.2990 | −0.0271 |

与 v1 的对比（v1 每目标最优）：

| 目标 | v1 最优（模型） | v2 留出最优 | 相对 v1 |
| --- | ---: | ---: | ---: |
| 氧化 | 0.2905（`linear`） | 0.2174（`xgb_enriched`） | **−25.2%** |
| 还原 | 0.4096（`scalar_gpr`） | 0.3317（`xgb_enriched`） | **−19.0%** |

### 3.2 口径 (b)：项目标准重复 CV

`RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)`，**每折模型 seed = 42 + 全局折号**（即 42…91）。
50 个折的折级读数落在 `probes/artifacts/p4_redox_v2_repeated_cv.csv`（600 行 = 6 模型 × 2 目标 × 50 折）。
下表的 `mae_mean ± mae_std` 是**先按 repeat 把该 repeat 的 5 个测试折池化成整表 392 行的 OOF，再在 10 个
repeat 之间取均值与样本标准差**（另有折级均值 `fold_mae_mean`，两者在 CSV/JSON 里都留了）。

**氧化（eV）**

| 模型 | OOF MAE 均值 ± SD（10 repeats） | 折级 MAE 均值 ± SD（50 folds） |
| --- | ---: | ---: |
| `linear_scalar`（单特征 `IP`） | 0.2737 ± 0.0009 | 0.2737 ± 0.0261 |
| `ridge_enriched` | 0.3005 ± 0.0201 | 0.3005 ± 0.0399 |
| `gpr_enriched` | 0.2390 ± 0.0025 | 0.2390 ± 0.0274 |
| **`xgb_enriched`** | **0.2061 ± 0.0060** | **0.2061 ± 0.0250** |
| `xgb_structure_only` | 0.5158 ± 0.0096 | 0.5159 ± 0.0600 |
| `dummy_mean` | 0.9669 ± 0.0026 | 0.9670 ± 0.0758 |

**还原（eV）**

| 模型 | OOF MAE 均值 ± SD（10 repeats） | 折级 MAE 均值 ± SD（50 folds） |
| --- | ---: | ---: |
| `linear_scalar`（单特征 `EA`） | 0.4212 ± 0.0013 | 0.4212 ± 0.0516 |
| `ridge_enriched` | 0.4499 ± 0.0155 | 0.4499 ± 0.0467 |
| `gpr_enriched` | 0.3696 ± 0.0051 | 0.3696 ± 0.0429 |
| **`xgb_enriched`** | **0.3183 ± 0.0115** | **0.3183 ± 0.0453** |
| `xgb_structure_only` | 0.5313 ± 0.0108 | 0.5313 ± 0.0550 |
| `dummy_mean` | 1.1405 ± 0.0017 | 1.1405 ± 0.0977 |

**富特征 vs 现行单特征（同一 CV 口径，逐目标）：**

| 目标 | `linear_scalar`（现行） | 富特征最优（`xgb_enriched`） | 相对改善 | v1 留出锚点 |
| --- | ---: | ---: | ---: | ---: |
| 氧化 | 0.2737 | **0.2061** | **−24.7%** | 0.2905 |
| 还原 | 0.4212 | **0.3183** | **−24.4%** | 0.4096 |

**两个非线性模型都优于单特征，ridge 反而不行。** `gpr_enriched` CV 0.2390 / 0.3696 与
`xgb_enriched` 0.2061 / 0.3183 都低于单特征；`ridge_enriched`（0.3005 / 0.4499）**高于**单特征。
原因在第七节：2061 维 + 392 行，线性模型在 LOO-GCV 选出的 α 下仍然要么欠拟合要么过拟合，
拿不到非线性模型那样的增益。这里不掩饰——**富特征本身不保证变好，增益来自非线性模型。**

**与协调者探索性数字的差异（如实记录，未做任何对齐）：**

| 模型/目标 | 协调者探索 CV | 本次正式 CV | 说明 |
| --- | ---: | ---: | --- |
| `linear`/[IP] 氧化 | 0.2738 | 0.2737 | 一致 |
| `xgb`[IP,EA]+RDKit2D+morgan 氧化 | 0.2235 | 0.2061 | 本次更低（超参/口径细节不同） |
| `xgb` 同上 还原 | 0.3239 | 0.3183 | 接近 |
| `ridge` 同上 氧化 | 0.2152 | 0.3005 | **差很多**（见上，ridge 配置差异） |
| `xgb` 只用 2D+morgan 氧化 | 0.5155 | 0.5158 | 一致（消融） |
| `xgb` 只用 2D+morgan 还原 | 0.5218 | 0.5313 | 接近 |
| `xgb` 训练残差 氧化/还原 | 0.0432 / 0.0650 | 0.0508 / 0.0780 | 接近 |

## 四、Dummy 对照

- `dummy_mean = DummyRegressor(strategy="mean")` 与所有主模型**共用完全相同的折**（同一份
  `RepeatedKFold(5,10,42)` 索引，`repeat`/`fold` 逐格对齐；由测试
  `test_dummy_control_shares_every_fold` 对 600 行折记录逐 `(target, repeat, fold)` 断言
  `train_id_hash`/`test_id_hash` 在 6 个模型间唯一）。
- 留出 MAE：0.9669 / 0.9669 级别的均值预测在 78 行上给出 **1.1300 / 1.1171 eV**；
  CV 给出 **0.9669 / 1.1405 eV**。
- 富特征最优模型相对 dummy 的改善：氧化 CV 0.2061 vs 0.9669（**−78.7%**），
  还原 CV 0.3183 vs 1.1405（**−72.1%**）。也就是说富特征信号是真的，不是"比均值好一点点"。
- `dummy_mean` **不进入门候选**（`GATE_CANDIDATE_MODELS` 明确排除它；测试
  `test_dummy_is_never_a_gate_candidate` 断言它从不出现在 `gate.best_model` / `gate_repeated_cv.best_model` 里，
  且它恒差于最优候选）。
## 五、特征清单与禁用合规

### 5.1 允许与使用的特征（`summary.features`）

| 组 | 内容 | 维数 |
| --- | --- | ---: |
| 预注册量 | `IP`、`EA` | 2 |
| 低阶交互 | `IP_times_EA`、`IP_squared`、`EA_squared` | 3 |
| RDKit 2D 描述符 | `MolWt`、`TPSA`、`MolLogP`、`RingCount`、`NumHDonors`、`NumHAcceptors`、`NumRotatableBonds`、`FractionCSP3` | 8 |
| Morgan count | `radius=2, fpSize=2048`，直接复用 `probes/p4_redox_baseline.py::_morgan_count_features` | 2048 |

三个特征视图：`compact` = 13 维（上游 + 交互 + RDKit2D，给 `gpr_enriched`）；
`structure_only` = 2056 维（RDKit2D + Morgan，给消融）；`enriched` = **2061 维**（全体，给 `ridge`/`xgb`）。
特征名全表落在 `summary.features.feature_names`（2061 个，已断言唯一）。

### 5.2 禁用清单与运行期守卫

**绝对禁止**把两个自由能标签或其任何派生当特征：`oxidation_free_energy`、`reduction_free_energy`、
`ox + red`（→`ox_plus_red`/`sum_free_energy`）、`ox − red`（→`ox_minus_red`/`delta_free_energy`）。

守卫是**运行期**的，不是只有文档：`assert_no_label_leakage(feature_names)` 在 `build_feature_matrix`
里对全部 2061 个特征名调用，命中以下任一条件即 `raise ValueError` 并终止探针：

1. 名字等于 6 个显式禁用名之一；
2. 名字包含子串 `free_energy`（这一条把「任何我没想到的标签派生名」也一并拦掉）；
3. 名字与两个标签列互为子串。

`summary.features.leakage_guard == "passed"` 是这次构建的实测结果。
测试侧另有三道：`test_feature_names_carry_no_label_derivative`（对 2061 个名字逐个断言不含 `free_energy`）、
`test_label_leakage_guard_rejects_derived_names`（对 6 个禁用名 + 一个构造的派生名断言抛异常，同时对合法名断言不抛）、
`test_feature_groups_only_use_allowed_sources`（断言特征分组恰好是表 5.1 那几个来源）。

数据侧同样干净：`read_rx_rows` 只从合并表取 `smiles`/`IP`/`EA` 与两个标签列，标签列**只**作为 `y` 使用；
`Batt-P30K` 的 29,519 行（无自由能标签）一律排除，训练数据恒为 392 行。

## 六、门判定

阈值 **0.15 eV 不许动**（测试断言探针常量、v1 summary、v2 summary 三处都恰好是 `0.15`）。
以下是 `summary.gate`（留出口径，与 `p4_redox_summary.json → gate` 同结构）：

| 目标 | 最优模型 | 留出 MAE (eV) | 过门？ | 距门 |
| --- | --- | ---: | :---: | ---: |
| `oxidation_free_energy` | `xgb_enriched` | 0.217401 | **否** | 高出 44.9% |
| `reduction_free_energy` | `xgb_enriched` | 0.331693 | **否** | 高出 121.1% |

```json
"gate": {
  "threshold_mae": 0.15,
  "unit": "eV",
  "criterion": "best model per target has held-out MAE below threshold",
  "best_model": {"oxidation_free_energy": "xgb_enriched", "reduction_free_energy": "xgb_enriched"},
  "best_model_mae": {"oxidation_free_energy": 0.2174014393126818,
                     "reduction_free_energy": 0.33169277465193164},
  "passed": false
}
```

再看重复 CV 口径（`summary.gate_repeated_cv`，阈值同为 0.15）：

| 目标 | 最优模型 | CV MAE (eV) | 过门？ | 距门 |
| --- | --- | ---: | :---: | ---: |
| `oxidation_free_energy` | `xgb_enriched` | 0.206085 ± 0.006015 | **否** | 高出 37.4% |
| `reduction_free_energy` | `xgb_enriched` | 0.318350 ± 0.011458 | **否** | 高出 112.2% |

**两条口径同向：门仍为红，`passed = false`。**

## 七、可及下限证据：瓶颈是模型还是 n=392？

### 7.1 训练残差（同一模型在全部 392 行上拟合后的 in-sample MAE）

| 模型 | 氧化 in-sample | 还原 in-sample |
| --- | ---: | ---: |
| `linear_scalar`（单特征） | 0.2722 | 0.4185 |
| `ridge_enriched`（GCV） | **0.0006** | **0.0295** |
| `gpr_enriched` | 0.2191 | 0.3242 |
| `xgb_enriched` | **0.0508** | **0.0780** |

把 in-sample 与对应口径的 out-of-sample 摆在一起，两类模型泾渭分明：

| 模型 | 氧化 in / out(OOF) | 还原 in / out(OOF) | 读数 |
| --- | --- | --- | --- |
| `linear_scalar` | 0.2722 / 0.2737 | 0.4185 / 0.4212 | **受模型限制**：一列线性项，记不住也没法拟合 |
| `gpr_enriched` | 0.2191 / 0.2390 | 0.3242 / 0.3696 | 基本**受模型限制**：13 维平滑 GP 先验 |
| `ridge_enriched` | 0.0006 / 0.3005 | 0.0295 / 0.4499 | **受数据限制**：能背下 392 行，一出门就塌 |
| `xgb_enriched` | 0.0508 / 0.2061 | 0.0780 / 0.3183 | **受数据限制**：容量到 0.05/0.08，泛化只到 0.21/0.32 |

`xgb_enriched` 的 in-sample 0.0508 / 0.0780 **只有门（0.15）的 33.9% / 52.0%**——模型有足够容量把
392 行拟合到门以下；同样的模型在 10×5 OOF 上却停在 0.2061 / 0.3183。这个落差（泛化缺口
0.155 / 0.240 eV）**只能由样本量解释**，不是容量。

### 7.2 学习曲线（`probes/artifacts/p4_redox_v2_learning_curve.csv`）

协议：对 392 行做确定性子样本（seed 42）取 n∈{100,200,300,392}，每个规模跑
`RepeatedKFold(n_splits=5, n_repeats=3, random_state=42)`（**降低预算**，与主协议的 10 repeats 不同，
所以 n=392 点的数字与表 3.2 略有出入：0.2038 vs 0.2061）。

**OOF MAE（eV，3 repeats 均值）**

| n | 氧化 `xgb_enriched` | 氧化 `linear_scalar` | 还原 `xgb_enriched` | 还原 `linear_scalar` |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 0.2569 | 0.2794 | 0.4759 | 0.4567 |
| 200 | 0.2489 | 0.2830 | 0.4048 | 0.4565 |
| 300 | 0.2247 | 0.2775 | 0.3495 | 0.4161 |
| 392 | 0.2038 | 0.2732 | 0.3214 | 0.4215 |

两个形状都在说同一件事：

1. **单特征曲线是平的**（氧化 0.2794→0.2732；还原 0.4567→0.4215 且非单调）——给它更多数据几乎没用，
   因为它的天花板由**模型形式**决定。
2. **富特征曲线单调下降且尚未走平**（氧化 −0.0531 eV；还原 −0.1545 eV 从 n=100 到 n=392）——
   给它更多数据还在持续变好，说明它受**数据量**约束。
3. 还原目标在 n=100 时 xgb（0.4759）**还差于**单特征（0.4567），到 n=200 才反超——小样本下富特征会过拟合，
   这正是"n 不够"的直接指纹。
4. 粗线性外推（**非预注册**，仅量级指示）：氧化按最后一段 300→392 的 −0.0208 eV/92 行外推，补到 0.15 还需
   约 +240 行（n≈630）；还原按 −0.0282 eV/92 行外推，还需约 +560 行（n≈950）。曲线未走平，这两个数字只做
   量级判断，不能当承诺。

## 八、诚实边界

1. **门仍红，没有粉饰。** 氧化 0.2174（留出）/ 0.2061（CV）、还原 0.3317 / 0.3183，四个数字全部高于 0.15 eV。
   富特征把 v1 的最优留出误差压低 25.2%（氧化）与 19.0%（还原），但**不足以过门**。
2. **瓶颈是标注量，不是模型容量。** 证据三条：(i) `xgb_enriched` 全量拟合残差 0.0508 / 0.0780，远低于 0.15 eV；
   (ii) 同一模型 OOF 停在 0.2061 / 0.3183，泛化缺口 0.155 / 0.240 eV；(iii) 学习曲线单调下降且未走平，
   而单特征曲线是平的。
3. **但"更多数据必然过门"不成立。** 学习曲线外推很粗（未预注册、只 4 个规模、reduced repeats），
   而且 0.15 eV 这个阈值本身还牵扯化学口径——`IP`/`EA` 与自由能之间存在系统性偏移，靠结构/单分子量
   能否压到 0.15 eV 以内，本探针并没有给出证明，只给出了"还没到拐点"。
4. **还原目标明显更难。** 同一模型下还原的 MAE 是氧化的 1.5–1.6 倍（0.3183 vs 0.2061），距门是 2.12× vs 1.37×。
5. **"特征变多"本身不产生增益。** `ridge_enriched` 在 2061 维上反而**差于**单特征（CV 0.3005 vs 0.2737；
   0.4499 vs 0.4212），`xgb_structure_only`（去掉 IP/EA）更差（CV 0.5158 / 0.5313，是单特征 0.2737 / 0.4212 的 1.9 倍 / 1.3 倍）。
   有增益的是「非线性模型 + 预注册的 IP/EA」这一组合。
6. **best model 的选择偏差。** `gate.best_model` 在 78 行留出集上按 MAE 挑出（沿用 v1 的 criterion），
   因此留出的 0.2174 / 0.3317 有轻微乐观偏差；CV 口径 0.2061 / 0.3183 是独立读数，两者同向，结论不因此改变。
7. **本次明确没做的事：** 未使用 Batt-P30K 的 29,519 行（无自由能标签，不能当训练料）；未使用两个标签的任何派生；
   未对 XGB 做超参网格搜索（固定一组超参 `n_estimators=400, max_depth=4, lr=0.05, subsample/colsample=0.8,
   reg_lambda=1.0`，以免引入选择偏差）；未做嵌套 CV 的模型选择。
8. **与协调者探索数字的差异已如实保留**（表 3.2 下方），尤其是 `ridge`（探索 0.2152 / 0.3361 vs 本次
   0.3005 / 0.4499）。本次 ridge 的配置是 `StandardScaler + RidgeCV(alphas=logspace(-2,4,25), cv=None → 精确
   LOO-GCV)`，具体原因未查明——可能是探索时用了不同 α/不同描述符集合。这条差异**不影响门判定**，因为
   两个口径的最优模型都是 `xgb_enriched`。
9. **产物落点偏离 v1 约定**（`probes/artifacts/` 而非 `data/processed/`），原因是 `data/processed/*` 默认被
   `.gitignore` 忽略而我没有该文件的写权限。若项目希望统一回 `data/processed/`，需要由有 `.gitignore`
   写权限的人补两条白名单：
   `!data/processed/p4_redox_v2_repeated_cv.csv`、`!data/processed/p4_redox_v2_predictions.csv`
   （学习曲线同理）。