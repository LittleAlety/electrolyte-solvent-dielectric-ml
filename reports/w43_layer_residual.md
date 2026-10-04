# W43-A 层级残差分解与适用域条款（计算 lane，0 shot）

回应 W42 登记的 item 36：`near_same_level` 不能当同层级替换。本件把 xTB–Batt 从名册 73 行
扩到大样本扩展层 4668 行，并把残留拆成『同方法换几何』与『同泛函换基组』两档量化。

## 1 覆盖

- 扩展层 5117 行；xTB–Batt 4668；xTB–PubChemQC 208；名册 xTB–Batt 73。

## 2 三对秩相关

| 对 | 口径 | n | Spearman | Kendall | Pearson | MAE (eV) | ρ 的 95% CI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| xtb-batt | expanded | 4668 | 0.5985 | 0.4243 | 0.4343 | 6.3328 | [0.5800, 0.6173] |
| xtb-pubchemqc | expanded | 208 | 0.9108 | 0.7448 | 0.8356 | 2.3023 | [0.8733, 0.9364] |
| xtb-batt | roster | 73 | 0.3280 | 0.2329 | 0.0854 | 5.4276 | [0.1182, 0.5123] |

**关键读数**：名册 73 行 ρ = 0.3280，扩到 4668 行后 ρ = 0.5985，差 0.2705 ⇒ **名册子集是悲观尾，不是层级真值**。

## 3 几何残留（同方法，THEMol 几何 vs DFT 几何）

- n = 137；ρ = 0.9916；Kendall = 0.9397；Pearson = 0.9974。
- MAE = 0.1599 eV；RMSE = 0.2768 eV；有符号均值 = 0.0381 eV。
- ρ 的 bootstrap 95% CI = [0.9821, 0.9954]；置换检验 p = 0.000500。
- 读法：换几何**保序极好**（ρ ≥ 0.99），但电平整体平移 ~0.16 eV ⇒ 几何残留是 level-shift，不是 rank-break。

## 4 基组残留（near_same_level：QM9 6-31G(2df,p) vs PubChemQC 6-31G*）

| 容差 |Δ| (eV) | 覆盖分数 |
| ---: | ---: |
| 0.1 | 0.4563 |
| 0.2 | 0.6893 |
| 0.3 | 0.8350 |
| 0.5 | 0.9612 |
| 0.75 | 0.9903 |
| 1 | 1.0000 |

- n = 103；平均 |Δ| = 0.1612 eV；最大 |Δ| = 0.8599 eV。
- 读法：同泛函同相不同基组的残留**档位覆盖 0.6893（|Δ| ≤ 0.2 eV）**，所以
`near_same_level` 只能当『带 ±0.2 eV 容差的替换上界』，不是严格同层级。

## 5 描述符分解与代理上界

| 描述符 | n | Spearman(残差, ·) | Spearman(|残差|, ·) |
| --- | ---: | ---: | ---: |
| heavy_atom_count | 45 | 0.1385 | 0.1357 |
| hba | 45 | -0.1385 | -0.1414 |
| tpsa_A2 | 45 | 0.1559 | 0.1541 |
| molecular_volume_A3 | 45 | 0.1200 | 0.1157 |
| polarizability_A3 | 45 | 0.1468 | 0.1430 |
| dipole_D | 45 | 0.1846 | 0.1850 |
| homo_lumo_gap_ev | 45 | -0.6428 | -0.6414 |

- 9 描述符标准化 OLS：n = 45，R2 = 0.9508，残差 MAE = 0.4427 eV。
- 注意：描述符面板仅 45 行（扩展层 ∩ 名册 ∩ 双端 gap 齐备），该 R2 为样本内、含 10 个参数，不作外推。
- isotonic 代理：样本内 ρ = 0.6172 / R2 = 0.4146；5 折 CV ρ = 0.5995 / R2 = 0.4041。
- 阈值 AUC：raw = 0.7969 → CV = 0.7957（上四分位 CV = 0.7835）。

## 6 适用域条款

```json
{
  "clause_id": "w43_applicability_clause_v1",
  "status": "locked_before_run",
  "scope": "外部轨道层在名册上的适用域",
  "rank_preserving_threshold_spearman": 0.95,
  "level_shift_tolerance_ev": 0.35,
  "same_method_geometry": {
    "rule": "同方法（GFN2-xTB 气相）换几何：若 ρ >= 0.95 且 MAE <= 0.35 eV，判为 rank-preserving + level-shift 可接受",
    "n": 137,
    "spearman": 0.991566636175257,
    "mae_ev": 0.15989343065693432,
    "verdict": "rank_preserving"
  },
  "near_same_level_basis": {
    "rule": "同泛函同相不同基组：档位覆盖 >= 0.60（|Δ| <= 0.2 eV）才可当同层级替换的上界",
    "n": 103,
    "coverage_le_0.2": 0.6893203883495146,
    "mae_ev": 0.1612343280021094,
    "verdict": "usable_as_bound"
  },
  "cross_method": {
    "rule": "跨方法（xTB vs Batt，不同泛函/相/基组）：任何层级都不作同层级替换",
    "expanded_spearman": 0.5984785837315431,
    "roster_spearman": 0.32799580402320133,
    "verdict": "not_same_level"
  },
  "forbidden": [
    "把 near_same_level 声明升格为 strict same_level",
    "用外部层数值替换 Batt 标签或作特征列"
  ]
}
```

## 7 判据

| 判据 | 描述 | 读数 | 阈值 | 结论 |
| --- | --- | --- | --- | --- |
| H43a1 | 扩展层 5117 行；xTB–Batt 4668、xTB–PubChemQC 208 | {"expanded_rows": 5117, "expanded_xtb_batt": 4668, "expanded_xtb_pubchemqc": 208} | {"expanded_rows": 5117, "expanded_xtb_batt": 4668, "expanded_xtb_pubchemqc": 208} | 成立 |
| H43a2 | 扩展层 xTB–Batt Spearman 落在 [0.5, 0.7] | 0.5984785837315431 | [0.5, 0.7] | 成立 |
| H43a3 | 名册 73 行是悲观尾：roster ρ 与 expanded ρ 之差 >= 0.2 | 0.2704827797083417 | >= 0.2 | 成立 |
| H43a4 | 名册 xTB–Batt n = 73 且 ρ <= 0.4 | {"n": 73, "spearman": 0.32799580402320133} | {"n": 73, "spearman_max": 0.4} | 成立 |
| H43a5 | 几何残留 n >= 130 且同方法换几何 ρ >= 0.95 | {"n": 137, "spearman": 0.991566636175257} | {"n": 130, "spearman": 0.95} | 成立 |
| H43a6 | 几何残留 MAE <= 0.35 eV（量级平移） | 0.15989343065693432 | 0.35 | 成立 |
| H43a7 | 几何残留置换检验 p <= 0.01 | 0.0004997501249375312 | 0.01 | 成立 |
| H43a8 | 基组残留 |Δ| <= 0.2 eV 覆盖 >= 0.60 | 0.6893203883495146 | 0.6 | 成立 |
| H43a9 | isotonic 样本内 ρ >= 0.60 | 0.6172241723893919 | 0.6 | 成立 |
| H43a10 | isotonic 5 折 CV R2 >= 0.30 | 0.40413466378707663 | 0.3 | 成立 |
| H43a11 | isotonic 5 折 CV ρ >= 0.50 | 0.5994823471948241 | 0.5 | 成立 |
| H43a12 | 阈值 AUC（CV）>= 0.70 | 0.7957433572045887 | 0.7 | 成立 |
| H43a13 | 描述符分解：最大 |Spearman(|残差|, 描述符)| >= 0.20 | 0.6413702239789195 | 0.2 | 成立 |
| H43a14 | 适用域条款三档判决齐备且 strict same_level 计数 = 0 | {"geometry": "rank_preserving", "basis": "usable_as_bound", "cross": "not_same_level", "strict_same_level": 0} | {"geometry": "rank_preserving", "basis": "usable_as_bound", "cross": "not_same_level", "strict_same_level": 0} | 成立 |
| H43a15 | 输入文件生成前后 sha256 不变 | 1.0 | 1.0 | 成立 |

## 8 边界

- 只读：不改任何标签或特征列，扩展层数值只作对照。
- `near_same_level` 未被升格为 `strict same_level`；条款把 strict 计数写死为 0。
- 0 shot；四个冻结读数一个不动。
