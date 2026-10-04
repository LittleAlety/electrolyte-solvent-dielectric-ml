# W44-D 静态 shot / 冻结读数守卫

AST 静态扫描；0 shot。三条规则：注册表 7 项、冻结读数写入 = 0、promoted 未登记 = 0。

## 1 扫描规模

- 扫到的 *.py 文件： 359 个；解析成功 359 个；AST 节点 1302367 个。
- 含 METRIC_NAMES / EXPECTED_METRIC_NAMES 赋值的文件： probes/dielectric_auc_sidecar.py, probes/dielectric_compound_coverage_curve.py, probes/dielectric_observations_grouped_benchmark.py, probes/l3_stage1_pilot.py, probes/v032_controlled_comparison.py。
- 冻结注册表定义检查： 2 处，状态 EXPECTED_METRIC_NAMES:frozen, METRIC_NAMES:frozen。
- legacy 局部同名量（老探针私有列名表，不计 mutation）： probes/dielectric_compound_coverage_curve.py, probes/l3_stage1_pilot.py, probes/v032_controlled_comparison.py。
- 冻结读数引用次数： 267；出现在赋值左侧次数： 0。
- promoted = True 的行： 无；未登记晋升： 无。

## 2 判据

| 判据 | 描述 | 读数 | 阈值 | 结论 |
| --- | --- | --- | --- | --- |
| H44d1 | 扫描到的 *.py 文件数 >= 200 | 359 | 200 | 成立 |
| H44d2 | 全部文件解析成功（AST 语法错误 = 0） | [] | [] | 成立 |
| H44d3 | 两个冻结注册表定义都等于冻结 7 项 | {"checked": 2, "statuses": ["EXPECTED_METRIC_NAMES:frozen", "METRIC_NAMES:frozen"]} | {"checked_min": 2, "all_frozen": true} | 成立 |
| H44d4 | METRIC_NAMES 改写（mutation）= 0 | [] | [] | 成立 |
| H44d5 | 四个冻结读数出现在赋值左侧（写入）= 0 | [] | [] | 成立 |
| H44d6 | 四个冻结读数仍作为引用出现在源码里（reads >= 4） | 267 | 4 | 成立 |
| H44d7 | 未登记的 promoted = True = 0 | [] | [] | 成立 |
| H44d8 | 输入（prereg + 两个注册表文件 + w42_common）sha256 未变 | True | True | 成立 |

## 3 边界

- 静态守卫只读源码，不跑模型、不写 summary。
- legacy 局部同名量是历史探针的私有列名表，不是冻结注册表；冻结注册表只在两个文件里定义。
- 0 shot；四个冻结读数一个不动。
