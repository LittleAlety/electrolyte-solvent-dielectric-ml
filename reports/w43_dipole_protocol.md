# W43-B 偶极校正协议预注册 + 离线影响评估（治理 lane，0 shot）

回应 W42 登记的 item 37：把 ~0.39 D 的 xTB→B3LYP 偶极偏置校正写成预注册协议。
**本轮不执行校正**：协议状态 `registered_not_authorized`，只在离线域表上量化影响。

## 1 协议九要素

- **protocol_id**：dipole_transfer_v1
- **status**：registered_not_authorized
- **applicability**：仅当目标行同时有 xTB 偶极与任一 B3LYP 气相偶极层（QM9 或 PubChemQC）时可用；否则回退到未校正偶极
- **fallback**：缺外部偶极 ⇒ 原样返回 mu_xTB，并在输出行标注 correction_applied=false
- **invalidation**：若留一交叉验证的 |bias| 的 95% CI 跨 0，或 MAE 未下降，则协议判为未通过、不得发布
- **variants**：
  - legacy（signed_shift）：mu_corr = mu + offset（带符号增量，抽自 W40-C 域表，用于精确复现）
  - shift_mean（signed_shift）：mu_corr = mu + offset（带符号增量 = -mean(mu_xTB - mu_QM9)）
  - shift_median（signed_shift）：mu_corr = mu + offset（带符号增量 = -median(mu_xTB - mu_QM9)）
  - affine（affine）：mu_corr = intercept + slope*mu，QM9 ~ our 的 OLS

## 2 估计诊断（名册 ∩ QM9，n = 103）

- 仿射 OLS：slope = 0.7506（bootstrap 95% CI [0.5657, 0.8931]），intercept = 0.1623，R2 = 0.6142。
- 未校正 MAE = 0.6103 D → 校正后 MAE = 0.4605 D。
- LOO 失效检验：偏差 = 0.3945 D，95% CI = [0.2248, 0.5788] ⇒ CI 不含 0，协议过失效闸。
- legacy 变体精确复现域表 mu_corr_D：max|Δ| = 1.776e-15 D。

## 3 离线影响评估（W40-C 域表 241 行）

未校正域比 = 2.581713。

| 变体 | 应用行数 | 丢弃(mu<=0) | 域比 | Δ vs 未校正 | n_A | n_B |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| legacy | 211 | 26 | 3.113253 | 0.531540 | 144  | 67 |
| shift_mean | 211 | 26 | 3.112220 | 0.530507 | 144  | 67 |
| shift_median | 208 | 29 | 3.172633 | 0.590920 | 141  | 67 |
| affine | 227 | 0 | 2.469576 | -0.112137 | 160  | 67 |

- 读法：三个变体都把域比抬到 2.4696–3.1726 区间，Δ 全部 ≤ 1.0 ⇒ 偶极校正在域比这一层是**同档扰动**，不是结论翻转。
- 但**协议未获授权**：任何校正后的数值都不得替换标签或作特征列，`mu_corr_D` 仍是只读对照列。

## 4 判据

| 判据 | 描述 | 读数 | 阈值 | 结论 |
| --- | --- | --- | --- | --- |
| H43b1 | 协议状态为 registered_not_authorized（未执行校正） | registered_not_authorized | registered_not_authorized | 成立 |
| H43b2 | 估计重叠 n = 103（名册 ∩ QM9） | 103 | 100 | 成立 |
| H43b3 | 仿射变体斜率落在 [0.5, 1.5] | 0.7505560209207711 | [0.5, 1.5] | 成立 |
| H43b4 | 仿射变体 R2 >= 0.50 | 0.6141809025552685 | 0.5 | 成立 |
| H43b5 | LOO 偏差 95% CI 不含 0（校正有据） | [0.22482240291262132, 0.5788337621359223] | 0 not in CI | 成立 |
| H43b6 | 仿射校正后 MAE < 未校正 MAE | {"before": 0.610309708737864, "after": 0.4604847987809531} | after < before | 成立 |
| H43b7 | legacy 变体精确复现域表 mu_corr_D（max|Δ| <= 1e-9 D） | 1.7763568394002505e-15 | 1e-09 | 成立 |
| H43b8 | 离线应用行数 >= 200（三个变体） | {"legacy": 211, "shift_mean": 211, "affine": 227} | {"min": 200} | 成立 |
| H43b9 | 三个变体的域比 |Δ| 全部 <= 1.0 | 0.5909197513192797 | 1.0 | 成立 |
| H43b10 | 校正后域比仍落在 [2.0, 4.0]（同档） | {"legacy": 3.113252911075283, "shift_mean": 3.112220043710082, "affine": 2.4695764102256095} | [2.0, 4.0] | 成立 |
| H43b11 | 被丢弃行（mu_corr <= 0）在三个变体下都 <= 30 且登记 | {"legacy": 26, "shift_mean": 26, "affine": 0} | {"max": 30} | 成立 |
| H43b12 | 输入文件生成前后 sha256 不变（标签一字未改） | 1.0 | 1.0 | 成立 |

## 5 边界

- 只读：不改任何标签或特征列；本件不发布任何校正后的偶极。
- LOO 失效闸通过只说明『偏置真实存在』，不等于『校正可用』；授权留给后续周单独决策。
- 0 shot；四个冻结读数一个不动。
