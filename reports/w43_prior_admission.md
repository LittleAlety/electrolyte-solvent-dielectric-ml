# W43-C 外部轨道层当排序先验的准入规则（治理 lane，0 shot）

一条机械准入规则，把 W42 的六对秩相关与层元数据合成一张判决表。

## 1 规则

- score = 0.5*spearman(L, Batt) + 0.2*coverage_frac + 0.2*unit_check_frac + 0.1*structure_check_frac
- admit：score >= 0.6 且 spearman >= 0.5 且 unit_check_frac >= 0.9 且 license 合规
- defer：0.4 <= score < 0.6 或元数据缺项
- reject：score < 0.4 或 spearman < 0.3 或 license 不允许再分发；Batt 是标签目标，永不作先验

## 2 判决表

| 层 | 角色 | 覆盖 | 覆盖分数 | ρ(·,Batt) | unit | structure | score | 判决 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| xtb | 本仓自有层（非外部先验候选） | 237 | 0.9834 | 0.3280 | 1.0000 | 1.0000 | 0.6607 | defer |
| qm9 | 外部先验候选 | 103 | 0.4274 | 0.8177 | 0.0000 | 0.0000 | 0.4943 | defer |
| pubchemqc | 外部先验候选 | 205 | 0.8506 | 0.7386 | 1.0000 | 1.0000 | 0.8394 | admit |
| batt | 标签目标层（永不作先验） | 73 | 0.3029 | 1.0000 | 0.0000 | 0.0000 | 0.5606 | reject |

## 3 判决理由

- **xtb**：defer —— 分数或秩相关未达 admit 门槛。
- **qm9**：defer —— 元数据缺项：unit/structure 核验字段未随层发布。
- **pubchemqc**：admit —— 四元条件全过。
- **batt**：reject —— 标签目标层：永不作排序先验（硬规则）。

## 4 near_same_level 处置

- qm9–pubchemqc 判 **near_same_level**（同泛函 B3LYP、同气相），strict same_level = False ⇒ 计数仍为 0。
- 该组合**未被自动准入**：QM9 因元数据缺项被 defer，只有 PubChemQC 单独 admit。
- 反事实：admit 层与 Batt 的秩相关 = {"pubchemqc": 0.7386459868154263}。

## 5 判据

| 判据 | 描述 | 读数 | 阈值 | 结论 |
| --- | --- | --- | --- | --- |
| H43c1 | 四层全部打分（xTB/QM9/PubChemQC/Batt） | 4 | 4 | 成立 |
| H43c2 | 至少一层被判 admit | ["pubchemqc"] | >= 1 | 成立 |
| H43c3 | 至少一层被判 defer 或 reject | ["xtb", "qm9", "batt"] | >= 1 | 成立 |
| H43c4 | Batt 永不作先验（判 reject） | reject | reject | 成立 |
| H43c5 | strict same_level 计数 = 0（near_same_level 不自动准入） | {"strict_same_level": 0, "qm9_pubchemqc_admitted": false} | {"strict_same_level": 0, "qm9_pubchemqc_admitted": false} | 成立 |
| H43c6 | admit 层四元条件全过 | {"pubchemqc": [0.839447474735514, 0.7386459868154263, 1.0]} | all admit satisfy | 成立 |
| H43c7 | 非 admit 层都登记了具体原因（非空） | {"xtb": "分数或秩相关未达 admit 门槛", "qm9": "元数据缺项：unit/structure 核验字段未随层发布", "batt": "标签目标层：永不作排序先验（硬规则）"} | all non-empty | 成立 |
| H43c8 | 反事实：admit 层与 Batt 的秩相关 >= 0.5 | {"pubchemqc": 0.7386459868154263} | >= 0.5 | 成立 |
| H43c9 | xTB 层因秩相关未达 admit 门槛而被 defer | {"verdict": "defer", "spearman": 0.32799580402320133} | {"verdict": "defer", "spearman_max": 0.5} | 成立 |
| H43c10 | 输入文件生成前后 sha256 不变 | 1.0 | 1.0 | 成立 |

## 6 边界

- 只读：准入规则不新增特征列、不改标签、不替换 Batt。
- admit 只表示『可当只读排序先验』，不等于可当同层级标签替换；strict same_level 仍为 0。
- 0 shot；四个冻结读数一个不动。
