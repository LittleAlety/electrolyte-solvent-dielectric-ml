# 出口 2：HOMO / LUMO / IP / EA 结构→性质基线（手册附录 Q-2）

> **一句话结论**：四个目标里 **2 个过门（LUMO、HOMO）、2 个没过**（IP 折均 MAE 0.20110 eV，比 0.2 eV 门高 1.1 meV；EA 0.23415 eV，高出 34 meV）。**「四个全过」口径：未通过（2/4）**。特征全程只用结构派生量，未使用任何 DFT 派生特征，四个冠军未被任何一折的训练集看到。

## 1. 门读数（逐目标 + 全过）

阈值口径（脚本内预先声明，未事后改动）：`gate.threshold_mae = 0.20`，`unit = eV`，主判据 = **正式 5×10 折的折均 MAE**；同时给出合并 OOF MAE 作为**次级读数**。

| 目标 | 标签 | 主模型 | 折均 MAE (eV) ± std | 合并 OOF MAE (eV) | R²(OOF) | Dummy 折均 MAE | 逐目标判定 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LUMO | `Batt-P30K/lumo` | `morgan_plus_2d+deeper_slower` | 0.13855 ± 0.00286 | 0.13352 | 0.8370 | 0.5145 | **过门** |
| HOMO | `Batt-P30K/homo` | `morgan_plus_2d+deeper_slower` | 0.19051 ± 0.00287 | 0.18455 | 0.8908 | 0.6523 | **过门** |
| IP | `Batt-P30K/ip` | `morgan_plus_2d+deeper_slower` | 0.20110 ± 0.00321 | 0.19466 | 0.8926 | 0.7056 | **未过门** |
| EA | `Batt-P30K/ea` | `morgan_plus_2d+deeper_slower` | 0.23415 ± 0.00379 | 0.22777 | 0.8167 | 0.7008 | **未过门** |

### 两个口径，分开写清楚

- **逐目标口径（主）**：LUMO ✅、HOMO ✅、IP ❌、EA ❌ → 2/4。
  产物里记录的门读数：`{"HOMO": 0.19050925839013938, "LUMO": 0.13855083976437643, "IP": 0.2010970559642009, "EA": 0.23415453202842548}`
- **「四个全过」口径**：`gate.passed = false`，`targets_passed = 2/4`。**未通过**。
- **次级读数（仅供参考，不替代主判据）**：若改用合并 OOF MAE，IP 为 0.19466 eV（<0.2，会「过」），EA 为 0.22777 eV（仍不过）。**本轮不更换判据**：判据在跑批前已写进代码与产物，事后改用对结果更有利的口径正是预注册（`probes/l3_backvalidation_prereg.json` → L1..L4 同款纪律）明令禁止的行为。IP 按主判据就是**未过**。

## 2. 数据、标签与单位

| 项 | 值 |
| --- | --- |
| 来源 | `data/raw/batt/Batt-P30K.h5`（sha256 `587f1490613a008b91f45ee9de607a2e057c88c301fa9e5c9d7785b1968d118d`） |
| 顶层 group | 29519（索引 0..31099 **不连续**，按 `int(name[7:])` 数值序读） |
| 建模池（剔除冠军后） | 29515 行 |
| 池 sha256 | `299ce3190dbbe5f37d514d4ca06e5db170360283e7943125bda990e0fc231524` |
| units 出处 | `probes/p4_redox_summary.json`（sha256 `b91e4438890ec7d9…`） |
| 单位 | `eV`（DFT 方法 wB97X-V/def2-TZVPPD/SMD(epsilon=18.5)；h5 `attrs` 为空，**文件本身不声明单位**） |

| 目标 | 均值 | 标准差 | 最小 | 最大 |
| --- | --- | --- | --- | --- |
| LUMO | 1.1679 | 0.6879 | -7.6975 | 2.0710 |
| HOMO | -9.6424 | 0.8522 | -13.3755 | -3.3888 |
| IP | 7.2396 | 0.9262 | 0.5058 | 11.2726 |
| EA | 0.8583 | 0.8836 | -0.6682 | 17.1855 |

标签空间诊断（**仅诊断，绝不作为特征、绝不进入模型**，见 `analysis.label_space_diagnostics.used_as_feature = false`）：

| 关系 | 皮尔逊 r | 平均偏移 (eV) | 偏移标准差 (eV) |
| --- | --- | --- | --- |
| IP vs HOMO | -0.9876 | -2.4028 | 0.1582 |
| EA vs LUMO | -0.9513 | -0.3095 | 1.5525 |

## 3. 特征（只用结构派生量）

- Morgan count 指纹：radius=2，fpSize=2048（`GetCountFingerprintAsNumPy`）。
- 纯 2D RDKit 描述符 30 个：`MolWt`, `MolLogP`, `TPSA`, `LabuteASA`, `NumHDonors`, `NumHAcceptors`, `NumHeteroatoms`, `NOCount`, `NumRotatableBonds`, `NumValenceElectrons`, `NumAliphaticRings`, `NumAromaticRings`, `NumSaturatedRings`, `RingCount`, `FractionCSP3`, `HeavyAtomCount`, `BalabanJ`, `BertzCT`, `Chi0v`, `Chi1v`, `HallKierAlpha`, `Ipc`, `Kappa1`, `Kappa2`, `Kappa3`, `MaxPartialCharge`, `MinPartialCharge`, `MaxAbsPartialCharge`, `MinAbsPartialCharge`, `PEOE_VSA1`。
- 特征顺序：先指纹（2048），再接声明序的描述符；**拟合与打分走同一函数** `featurize_smiles`。
- 特征路径允许读取的 h5 dataset：**只有** `['smiles']`（其余全是标签或 DFT 派生量）。
- 显式禁用（`forbidden_inputs`）：`gap`, `homo`, `lumo`, `ip`, `ea`, `dipole`, `quadrupole`, `ener`, `ener_anion`, `ener_cation`, `coord`。`gap ≡ lumo − homo`（实测最大偏差 8.6e-7 eV），同样在禁用之列。
- 非有限描述符处理：non-finite descriptor values are replaced by 0.0 by the same code path at fit time and at scoring time（本轮全池命中 29519 行中 168 个值）。

## 4. L1 排除（冠军不得进入**任何一折**的训练集）

四个冠军（来自 `probes/l3_backvalidation_prereg.json`，`exclusion_levels[0]`）：

- `EC` — `KMTRUDSVKNLOMY-UHFFFAOYSA-N` — h5 group `CompMol169` —— 预测 HOMO -11.016 / LUMO 1.533 / gap 12.548 eV
- `FEC` — `SBLRHMKNNHXPHG-UHFFFAOYSA-N` — h5 group `CompMol12` —— 预测 HOMO -11.494 / LUMO 1.446 / gap 12.940 eV
- `PC` — `RUOJZAUFBMNUDX-UHFFFAOYSA-N` — h5 group `CompMol170` —— 预测 HOMO -10.952 / LUMO 1.539 / gap 12.491 eV
- `VC` — `VAYTZRYEBVHVLE-UHFFFAOYSA-N` — h5 group `CompMol173` —— 预测 HOMO -10.109 / LUMO 1.173 / gap 11.282 eV

执行方式（两层保险）：

1. **池级**：`build_pool` 把四个冠军整体移出建模池，并断言 `champions ∩ pool == ∅`；
   剔除后池行数 29515（29519 − 4），池 sha256 `299ce3190dbbe5f37d514d4c…`。
2. **逐折级**：`evaluate_folds` 对**每一折**都先执行 `exclude_champions` 再断言 `champions ∩ train_ids == ∅`（`assert_champions_absent`，违反即抛 `ChampionLeakError`）。**扫描协议与正式协议、主模型与 Dummy 的每一次拟合都走这条断言**，共覆盖 400 次折内拟合（正式 4 目标 × 50 折 × 2 模型）。

冠军只出现在最终评分步骤（L4）：走 `--score-smiles` 的同一条代码路径，无任何特判。

## 5. 正式协议与折记录

- 协议：`RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)`，逐折 seed = `42 + 全局折号`（= repeat × 5 + fold），共 50 折。
- **是否偏离项目标准**：`deviates_from_project_standard = false` —— 本轮**用的就是项目标准 5×10**，没有降级。
- 折记录 CSV：`data/processed/l3_homo_lumo_repeated_cv.csv`，列 `model, seed, repeat, fold, n_train, n_test, train_sha, test_sha, mae, rmse, r2`（LF 行尾）。
- 预测明细 CSV：`data/processed/l3_homo_lumo_cv_predictions.csv`（逐分子 OOF 均值/标准差/覆盖折数，主模型与 Dummy 各一份）。
- 计算设置：XGBoost `n_jobs=8`、`tree_method=hist`，折级并行 `fold_jobs=4`（只并行整折，**不改变任何单折的线程数**，已实测 fold_jobs=1/2/4 的折记录 CSV 逐字节相同）。
- 目标跑批顺序：LUMO → HOMO → IP → EA，每个目标跑完立即落一次中间产物（`summary.json` 以 `complete=false` + `completed_targets` 增量刷新，折记录与预测明细同步落盘）。

## 6. Dummy 对照

`DummyRegressor(strategy="mean")`（经 `MeanDummyModel` 包装，与 `probes/p2_diagnostics.py` 同款：fit/predict 都喂零矩阵），**与主模型严格共用同一组折**——同一 `RepeatedKFold` 实例、同一 repeat/fold/seed，折记录里 `train_sha`/`test_sha`/`n_train`/`n_test` 逐折一致（有测试守卫）。

| 目标 | 主模型折均 MAE | Dummy 折均 MAE | 相对 Dummy 的改善 |
| --- | --- | --- | --- |
| LUMO | 0.13855 | 0.5145 | ×3.71 |
| HOMO | 0.19051 | 0.6523 | ×3.42 |
| IP | 0.20110 | 0.7056 | ×3.51 |
| EA | 0.23415 | 0.7008 | ×2.99 |

## 7. 尝试记录表（特征/模型扫描，全部有记录）

扫描协议：`RepeatedKFold(n_splits=5, n_repeats=1, random_state=42)`（**筛选协议**，只有 5 折；门的读数一律取自正式 5×10 协议）。三个配置 × 四个目标全部跑完，无一遗漏、无一事后挑选。

| 目标 | 配置 | 特征数 | 折均 MAE (eV) | 相对 Morgan-only | 相对 Dummy |
| --- | --- | --- | --- | --- | --- |
| LUMO | Morgan-only + P2 超参 | 2048 | 0.1492 |  | ×3.45 |
| LUMO | Morgan+2D 描述符 + P2 超参 | 2078 | 0.1404 | -0.0088 | ×3.67 |
| LUMO | Morgan+2D 描述符 + deeper_slower | 2078 | 0.1380 | -0.0112 | ×3.73 |
| LUMO | *DummyRegressor(mean)* | — | 0.5145 | — | ×1.00 |
| HOMO | Morgan-only + P2 超参 | 2048 | 0.2245 |  | ×2.91 |
| HOMO | Morgan+2D 描述符 + P2 超参 | 2078 | 0.1958 | -0.0288 | ×3.33 |
| HOMO | Morgan+2D 描述符 + deeper_slower | 2078 | 0.1903 | -0.0343 | ×3.43 |
| HOMO | *DummyRegressor(mean)* | — | 0.6523 | — | ×1.00 |
| IP | Morgan-only + P2 超参 | 2048 | 0.2414 |  | ×2.92 |
| IP | Morgan+2D 描述符 + P2 超参 | 2078 | 0.2073 | -0.0341 | ×3.40 |
| IP | Morgan+2D 描述符 + deeper_slower | 2078 | 0.2004 | -0.0410 | ×3.52 |
| IP | *DummyRegressor(mean)* | — | 0.7056 | — | ×1.00 |
| EA | Morgan-only + P2 超参 | 2048 | 0.2472 |  | ×2.83 |
| EA | Morgan+2D 描述符 + P2 超参 | 2078 | 0.2366 | -0.0106 | ×2.96 |
| EA | Morgan+2D 描述符 + deeper_slower | 2078 | 0.2339 | -0.0133 | ×3.00 |
| EA | *DummyRegressor(mean)* | — | 0.7008 | — | ×1.00 |

读法：**纯结构导出的 2D 描述符是这一轮唯一的有效杠杆**（Morgan-only → Morgan+2D：HOMO −0.029、IP −0.034、EA −0.011、LUMO −0.009 eV）；模型加深再挤出一小截（−0.003 ~ −0.007 eV）。**没有任何一次尝试使用过 DFT 派生特征。**

交叉核对：Morgan-only 一列与本轮之前的独立快速探针（另一实现、单次 6:2 切分）几乎重合 ——

| 目标 | 独立快速探针 | 本轮 Morgan-only | 差 |
| --- | --- | --- | --- |
| LUMO | 0.1464 | 0.1492 | +0.0028 |
| HOMO | 0.2259 | 0.2245 | -0.0014 |
| IP | 0.2424 | 0.2414 | -0.0010 |
| EA | 0.2490 | 0.2472 | -0.0018 |

两套独立实现对同一表示给出了同一档数字（差 ≤ 0.003 eV），说明管线本身没有实现缺陷。

## 8. 主模型与选择规则

**规则（先声明，后执行；原样写在 `probes/homo_lumo_baselines.py` 的 `SELECTION_RULE`，并已写入 `summary.json` / `screening.json`）**：

> Declared before any fit: for each target independently, rank the pre-declared screening configurations by mean held-out MAE over the screening folds (RepeatedKFold n_splits=5, n_repeats=1, random_state=42; every configuration and the DummyRegressor control share identical folds). The winner must be strictly better than the DummyRegressor(strategy='mean') mean MAE on the same folds; if no configuration beats Dummy the lowest-MAE configuration is still reported with beat_dummy=false. Candidates within 1e-3 eV of the best MAE are treated as tied and the tie is broken by (1) fewer features, then (2) the declared model-variant order. Configurations are screened in the declared order regardless of outcome.

执行结果（脚本按规则机械算出，不是看着结果挑的）：

| 目标 | 胜出配置 | 特征数 | 筛选折均 MAE | 与 Dummy 之比 | 是否优于 Dummy |
| --- | --- | --- | --- | --- | --- |
| LUMO | `morgan_plus_2d+deeper_slower` | 2078 | 0.1380 | ×3.73 | 是 |
| HOMO | `morgan_plus_2d+deeper_slower` | 2078 | 0.1903 | ×3.43 | 是 |
| IP | `morgan_plus_2d+deeper_slower` | 2078 | 0.2004 | ×3.52 | 是 |
| EA | `morgan_plus_2d+deeper_slower` | 2078 | 0.2339 | ×3.00 | 是 |

并列判定（1e-3 eV 容差内取特征更少者）：`tied_configs` 每个目标都只有 `morgan_plus_2d+deeper_slower` 一个，因此没有触发特征数的并列裁决 —— 四个目标都是**在容差之外**被 deeper_slower 赢下的（差距 0.0024 ~ 0.0055 eV），不是靠偏好规则凑的。

落盘的主模型（每个目标一个，训练集 = 剔除冠军后的完整池 29515 行，sha256 `299ce3190dbbe5f3…`）：

| 目标 | 变体 | 可复原信息 |
| --- | --- | --- |
| LUMO | `deeper_slower` | xgboost 3.4.1，n_estimators=1000, max_depth=12, learning_rate=0.04, seed=42；权重 `models/homo_lumo_lumo.ubj`（sha256 `9f6c2d6e6f86476c…`） |
| HOMO | `deeper_slower` | xgboost 3.4.1，n_estimators=1000, max_depth=12, learning_rate=0.04, seed=42；权重 `models/homo_lumo_homo.ubj`（sha256 `7e945fc5647fb811…`） |
| IP | `deeper_slower` | xgboost 3.4.1，n_estimators=1000, max_depth=12, learning_rate=0.04, seed=42；权重 `models/homo_lumo_ip.ubj`（sha256 `1f16857fe9a30dde…`） |
| EA | `deeper_slower` | xgboost 3.4.1，n_estimators=1000, max_depth=12, learning_rate=0.04, seed=42；权重 `models/homo_lumo_ea.ubj`（sha256 `143258c78cae73c4…`） |

## 9. 可及下限证据（不许粉饰）

### 9.1 误差是「尾巴」不是「系统性平移」

| 目标 | 平均符号误差(偏差) eV | MAE | 中位绝对误差 | p90 绝对误差 | p99 绝对误差 | 绝对误差≤0.2 eV 的比例 |
| --- | --- | --- | --- | --- | --- | --- |
| LUMO | +0.00193 | 0.1335 | 0.0623 | 0.3155 | 0.9760 | 81.2% |
| HOMO | -0.00672 | 0.1845 | 0.1268 | 0.4035 | 0.9534 | 68.2% |
| IP | +0.00711 | 0.1947 | 0.1292 | 0.4290 | 1.0179 | 66.3% |
| EA | -0.00256 | 0.2278 | 0.1454 | 0.5163 | 1.1608 | 60.9% |

**四个目标的平均符号误差都不超过 7 meV**，即主模型**没有 Koopmans 型常数偏移**：0.2 eV 的失败不是「整体平移」，而是**厚尾**（p90 比中位数大 3~4 倍）。

需要区分两件事（之前的口头情报把二者混为一谈）：

- **标签之间的 2.40 eV 间隙确实存在**，但它是 **IP 与 HOMO 两个标签家族之间**的常数差（mean(IP + HOMO) = -2.403 eV，散布 0.158 eV，r = -0.9876），**不是模型对 IP 的预测偏差**（模型对 IP 的偏差只有 +7 meV）。
- 这条关系同时说明 **IP 的可及下限基本由 HOMO 决定**：把 IP 看成「−HOMO − 2.403 + 噪声」时，仅这 0.158 eV 的标签内散布就会贡献约 0.127 eV 的 MAE 地板；叠加 HOMO 自身 0.191 eV 的误差，IP 落在 0.20 eV 附近**是表示能力的结构性结果，不是调参能翻过去的**。
- **EA 与 LUMO 不是一回事**：r = -0.9513，但 mean(EA − LUMO) = -0.310 eV、散布高达 1.553 eV。EA 的标签本身还是重尾（均值 0.858 eV、最大 17.186 eV）。这解释了 EA 的 RMSE/MAE = 1.66，明显比另外三个目标差。

### 9.2 EA 是**数据受限**，不是（纯）表示受限

学习曲线（目标 EA，折 `repeat=0 fold=0` 的测试集，同一模型变体）：

| 训练分子数 | MAE (eV) | RMSE | R² |
| --- | --- | --- | --- |
| 1000 | 0.3993 | 0.5768 | 0.5626 |
| 5000 | 0.3041 | 0.4565 | 0.7261 |
| 12000 | 0.2592 | 0.4067 | 0.7826 |
| 23612 | 0.2318 | 0.3623 | 0.8275 |

最后一个区间（12000 → 23612，数据 ×1.97）MAE 仍在下降（0.2592 → 0.2318），**没有饱和**。按幂律斜率 （指数 ≈ -0.165）外推，EA 要走到 0.20 eV 大约还需要 **×2.4** 的分子数（≈ 57,000 训练分子）。**结论：EA 差 0.2 eV 主要是数据量问题，不是「2D 结构表示不可能」**——但这条路要求新数据，不是本轮能补的。

### 9.3 底线陈述

- 过门的是 **LUMO（0.1386）与 HOMO（0.1905）**，两个都是稳定过（折间 std ≈ 0.003 eV）。
- **IP 是「卡在门口」**：折均 0.20110 eV，只差 1.1 meV（0.55%）。它的下限被 HOMO 的误差与 0.158 eV 的 IP–HOMO 标签散布共同锁住；pooled OOF 读数本来就在门内（0.19466），**但主判据是折均，按主判据就是没过，不换口径**。
- **EA 是真正没过**（0.23415 eV，差 34 meV / 17%），且证据显示它是**数据受限**：学习曲线尚未饱和，需要约 2.4× 数据才可能进 0.2 eV。
- 全程**没有**为了过门引入任何 DFT 派生特征（`gap` / `homo` / `lumo` / `ip` / `ea` / `dipole` / `quadrupole` / `ener*` / `coord` 全部禁用，且只用 `smiles` 一个 h5 dataset）。

## 10. 评分入口（筛选漏斗可直接用）

```powershell
.\.venv\Scripts\python.exe probes/homo_lumo_baselines.py --score-smiles path\to\molecules.smi `
    --score-output path\to\scores.csv
```

- 输入：每行一个 SMILES（取第一个空白前缀字段）；输出列：`smiles`, `canonical_smiles`, `HOMO_eV`, `LUMO_eV`, `IP_eV`, `EA_eV`, `gap_eV`。
- `gap_eV` 是**预测的** LUMO − HOMO（派生输出，不是特征）。
- `models/homo_lumo_baselines.json` 自包含：特征配置（radius/fpSize/描述符清单/顺序/非有限值策略）、每个目标的模型可复原信息（框架+版本+全部超参+seed）、训练池 sha256、单位与出处、以及 `gate`/`exclusion`/`cv_protocol` 全文。权重以 sidecar 落盘并在 JSON 里记 sha256（每个 16.9–20.6 MB，4 个合计约 75 MB，未内联进 JSON）。

## 11. 产物清单

| 产物 | 说明 |
| --- | --- |
| `models/homo_lumo_baselines.json` | 自包含评分入口（特征配置 + 每目标可复原信息 + 训练池 sha256 + units + gate） |
| `models/homo_lumo_lumo.ubj` 等 4 个 | 生产模型权重（训练于剔除冠军后的 29,515 行全池，合计 75 MB） |
| `probes/homo_lumo_baselines.py` | CLI（跑批 / `--screen-only` / `--score-smiles`） |
| `probes/homo_lumo_baselines_summary.json` | 汇总（筛选全表 + 折读数 + gate + 学习曲线） |
| `probes/homo_lumo_baselines_screening.json` | 扫描原始记录（可 `--skip-screening` 复用，带 sha 校验） |
| `data/processed/l3_homo_lumo_repeated_cv.csv` | 400 行折记录（4 目标 × 50 折 × 2 模型） |
| `data/processed/l3_homo_lumo_cv_predictions.csv` | 逐分子 OOF 预测明细（236,120 行） |
| `data/processed/l3_homo_lumo_features.npz` | 特征缓存（`schema_version` + `feature_config_json` + `source_sha256` 三重校验） |
| `tests/test_homo_lumo_baselines.py` | 23 条守卫（实测值；原写 21 为笔误，已订正） |
| `reports/homo_lumo_baselines.md` | 本报告 |

## 12. 复现命令

```powershell
# 全量（筛选 + 正式 5×10 + 门 + 产物；本轮实际 ~30 min）
.\.venv\Scripts\python.exe probes/homo_lumo_baselines.py --fold-jobs 4
# 只跑筛选
.\.venv\Scripts\python.exe probes/homo_lumo_baselines.py --screen-only
# 复用筛选结果，只跑正式协议
.\.venv\Scripts\python.exe probes/homo_lumo_baselines.py --skip-screening --fold-jobs 4
# 打分
.\.venv\Scripts\python.exe probes/homo_lumo_baselines.py --score-smiles mols.smi
# 守卫 + 静态检查
.\.venv\Scripts\python.exe -m pytest tests/test_homo_lumo_baselines.py -q
.\.venv\Scripts\python.exe -m ruff check scripts src probes tests notebooks
```

## 13. 未决风险与存疑

1. **IP 卡在门口（1.1 meV）**：任何对折协议/超参/池定义的微小改动都可能让 IP 翻转。本轮按预先声明的折均判据判**未过**，不追认 pooled 口径。
2. **EA 的 0.2 eV 目标在本数据量下不可达**（学习曲线外推需 ~2.4× 数据）。若项目坚持 0.2 eV，EA 需要新数据或换表示（3D/GNN），**不能靠放宽特征禁用清单解决**。
3. **产物归档盲区**：`data/processed/*` 被仓库既有 `.gitignore` 排除（折记录 CSV 与预测明细 CSV 正好落在该目录），所以这两个表**不会进 git**，只能由脚本重跑再生。本轮未改 `.gitignore`（不在我的写入集内）。需要长期归档的话请决定是否加 negation。
4. **hash 快照的时效**：`payload.unit.source_sha256` 绑定的是**本次运行时刻**的 `probes/p4_redox_summary.json`；若该文件被别的进程改写，`--score-smiles` 仍可用，但 `tests/test_homo_lumo_baselines.py::test_unit_block_is_present_and_points_at_the_live_p4_summary` 会红。`Batt-P30K.h5` 的 digest 已按预注册快照封存（`587f1490…`），文件被换会立刻报错。
5. **权重是 sidecar 不是内联**：JSON 记 sha256 而不是把 75 MB 权重塞进去。若审核要求「JSON 单文件即可打分」，需要把 UBJ base64 内联（base64 后体积会到约 100 MB）。
6. **`--fold-jobs` 的等价性**：已实测 fold_jobs=1/2/4 折记录逐字节相同；但这是同一台机器上的经验结论，跨机器的浮点差异仍需按项目既有纪律处理。
7. **门只覆盖纯 2D 结构输入**：本轮的 0.2 eV 读数**不能**外推到含 3D 构象/溶剂的输入。
8. **预注册文件在本轮跑批中途被其他写手改写过（非我改动）**：`probes/l3_backvalidation_prereg.json` 的 mtime 为 2026-09-26T04:43:35。我的**筛选**阶段读到的是改写前修订（sha256 `45e04e88…`，记在 `probes/homo_lumo_baselines_screening.json`），**正式**阶段读到的是改写后修订（sha256 `39cc5e67…`，记在 `models/homo_lumo_baselines.json` 与 `probes/homo_lumo_baselines_summary.json`）。改写是**元数据性质**的（新增 `fold_and_seed` / `criteria` / `stage_1_pilot` / `reporting_rules` / `current_state_2026_09_26` 与 `pool_rule.amendment_1`）：四个冠军的 InChIKey、`exclusion_levels`（L1 全文）、`frozen_table.sha256`（`ff214293…`）与 `inputs_pinned[data/raw/batt/Batt-P30K.h5].sha256`（`587f1490…`）**逐字节未变**，所以本轮门读数不受影响；但两个产物里的 `prereg_sha256` 分属两个修订，审计时以各自文件内记录的值为准（有测试守卫断言本产物记录的 L1 规则与冠军集与**当前**预注册一致）。
9. **`fold_policy` 的读法**（**裁决已下，见 `reports/decisions_log.md` §18：采纳下文的「更严一档」，并如实记录预注册的 `fold_source` 指向不成立、需下一步 amend 补正**）：改写后的预注册 `fold_and_seed.fold_policy` 写的是「其余行的折号逐位不变，只把冠军行从其所在折的训练侧剔除；冠军本身仍按原折号做样本外评分」，且 `fold_source` 指向介电通道的 `data/processed/v032_ablation_predictions.csv`（该表不含 Batt-P30K 分子）。本轮出口 2 采用的是**更严的一档**：(i) 冠军整体移出建模池（29,519 → 29,515），因此冠军既不在任何折的训练侧、也不在任何折的测试侧；(ii) 折号由 `RepeatedKFold(5,10,42)` 在 29,515 行上生成（`fold_scheme` / `seed_scheme` 与预注册逐字一致，有测试守卫），而非沿用 `v032_ablation_predictions.csv` 的折号；(iii) 冠军最终由**全池生产模型**打分（走 `--score-smiles` 同一路径），而非「原折号样本外」。若漏斗的终局回溯验证要求折号与冻结表逐位对齐、且冠军必须样本外评分，则本通道要按 `fold_policy` 重跑一版（当前脚本的池是**池级**剔除，需要先改造）。本轮按作业书执行（「记录剔除后总行数与池 sha256」+「每折断言 `champions ∩ train_ids == ∅`」），L1 的硬要求被**严格满足**（比预注册字面要求更强）。
