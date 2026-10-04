# W44-C strict same_level 规格与在仓候选审计

只读治理 lane；0 shot。strict same_level = 四属性全同 + 独立来源。

## 1 候选层属性表

| 层 | 角色 | 泛函 | 基组 | 相 | 几何来源 | 与 target 距离 |
| --- | --- | --- | --- | --- | --- | --- |
| xtb | prior_candidate | GFN2-xTB | (none) | gas | THEMol | 4 |
| qm9 | prior_candidate | B3LYP | 6-31G(2df,p) | gas | QM9-geom | 4 |
| pubchemqc | prior_candidate | B3LYP | 6-31G* | gas | PM6 | 4 |
| batt | target | omegaB97X-V | def2-TZVPPD | SMD | (none) | 0 |
| orca | prior_candidate | r2SCAN-3c | def2-mTZVPP | gas+SMD(MeCN) | ORCA | 4 |
| expanded | prior_candidate | GFN2-xTB | (single point) | gas | B3LYP-D3(BJ)/DZVP geom | 4 |

## 2 最近对与 near 声明

- 最近一对： qm9-pubchemqc，属性距离 2。
- strict same_level 对： 无。
- near_same_level（泛函+相相同）对： xtb-expanded, qm9-pubchemqc。
- 仅部分相似（只同泛函或只同相）因而不许声明 near 的对： xtb-qm9, xtb-pubchemqc, qm9-expanded, pubchemqc-expanded。
- 越权 near 声明： 无。
- 与 target 距离 0 的层： 0 个。

## 3 判据

| 判据 | 描述 | 读数 | 阈值 | 结论 |
| --- | --- | --- | --- | --- |
| H44c1 | 被评分的候选层数 >= 6（含 target） | 6 | 6 | 成立 |
| H44c2 | strict same_level 计数 = 0（登记为已知边界，非判否） | 0 | 0 | 成立 |
| H44c3 | 最近一对的属性距离 == 2 且 pair == qm9-pubchemqc | {"closest_pair": "qm9-pubchemqc", "closest_distance": 2} | {"closest_pair": "qm9-pubchemqc", "closest_distance": 2} | 成立 |
| H44c4 | spec 四属性齐备且顺序 == functional/basis_set/phase/geometry_source | ["functional", "basis_set", "phase", "geometry_source"] | ["functional", "basis_set", "phase", "geometry_source"] | 成立 |
| H44c5 | 每个非 target 层都带 >= 1 条缺失属性理由（非空） | True | True | 成立 |
| H44c6 | Batt 是 target 行且 role == target | {"layer": "batt", "role": "target"} | {"layer": "batt", "role": "target"} | 成立 |
| H44c7 | near_same_level 声明只在泛函+相都相同时允许（越权 = 0） | {"near_pairs": ["xtb-expanded", "qm9-pubchemqc"], "unlicensed": [], "similar_but_not_near": ["xtb-qm9", "xtb-pubchemqc", "qm9-expanded", "pubchemqc-expanded"]} | {"rule": "functional_match and phase_match", "unlicensed_max": 0} | 成立 |
| H44c8 | 输入（六个层文件 + 名册 + prereg）sha256 未变 | True | True | 成立 |

## 4 边界

- 只读：不改任何 summary、标签或特征列。
- strict same_level 计数为 0，登记为已知边界；不得拿 near_same_level 冒充同层级。
- 0 shot；四个冻结读数一个不动。
