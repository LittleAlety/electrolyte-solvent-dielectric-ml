# B01 阶段门状态
> 生成器 `build_b01_gate_status/1.0.0` · 2026-11-24T02:22:31Z

## 一、三个必须分开的问题
**1_data_reconstruction** — 测量级账本是否成立? —— 2065 条测量全部可追溯, 78 条配对有效, 170 条例外已登记

**2_verification** — 独立校验是否通过? —— 见 checks 明细. 注意其中一项判 FAIL, 该失败是**正确行为**, 因为它抓到了生成器判据的同义反复

**3_stage_gate** — B02/B04 是否可推进? —— 由 blockers 决定, 不由'看起来做完了'决定

## 二、交付物
| 文件 | 存在 | 字节 | sha256(前16) |
|---|---|---:|---|
| `measurement_ledger_v1.csv` | ✅ | 1049231 | `1031611d703a5a29` |
| `source_document_registry_v1.csv` | ✅ | 23530 | `524d6eefc69d9339` |
| `aggregate_contribution_ledger_v1.csv` | ✅ | 75753 | `d0af80e3e7af1caf` |
| `condition_pair_validity_v1.csv` | ✅ | 64143 | `8baea7bc87842d6c` |
| `dataset_v05_manifest.json` | ✅ | 3631 | `14cec38ebe299c81` |
| `reconstruction_exceptions.csv` | ✅ | 86127 | `938e51a97b19b570` |
| `provenance_repair_report.md` | ✅ | 15025 | `50f3b53e8bb51c63` |

| 程序 | 存在 |
|---|---|
| `reconstruct_measurement_ledger.py` | ✅ |
| `build_provenance_preserving_dataset.py` | ✅ |
| `audit_condition_pair_integrity.py` | ✅ |
| `validate_source_independence.py` | ✅ |
| `verify_measurement_reconstruction.py` | ✅ |

## 三、独立校验
- 总判定：**PASS**（18/18）

## 四、例外登记
- `NO_CONTRIBUTING_MEASUREMENT`：147
- `SOURCE_LAYER_MISMATCH_FALSE_NEGATIVE`：1
- `SYNTHETIC_PAIR_FROM_INDEPENDENT_MEDIAN`：22

**发现的假阴性：** `EPSV04-R247`

这些行的证书声称来源层无数据，但账本中存在精确匹配观测，只是温度落在硬编码窗口外。**结论仍对，理由错误。**

## 五、来源独立性
- 跨文档完全重复观测组：**27**
- 涉及文档：**9**
- 受影响聚合行：**28**

n_contributing_sources 数的是 DOI 字符串, 不是独立实验. 注册表对 61/61 文档标注 independence=not_evaluated. B07 来源聚类检验必须先按文档去重.

## 六、压力异质性
- 受污染聚合行：**15**
  - `AMBIENT_CONSISTENT`：83
  - `MIXED_AMBIENT_AND_PRESSURISED`：12
  - `PRESSURISED_ONLY`：3
  - `UNCLASSIFIED`：2

10.1021/je060248p 等来源是固定温度下的压力扫描研究, 聚合把单调压力序列的中位数当作常压观测. R097 的 14.26 恰为 100/150 MPa 中点. 修复需改动冻结窗口, 属协议决策.

## 七、未决来源冲突
- 聚合层冲突：**1** 组
- 观测层冲突：**56** 组
- 未进入审核队列：**0** 组

γ-戊内酯 36.1 vs 36.9 冲突已进入审核队列并由四智能体裁决. 观测层另有 56 组同分子同温分歧, 尚未逐一裁决.

**γ-戊内酯裁决：** 两条记录均 REJECTED (未达 4/4 PASS). R2/R4 判 FAIL, R1/R3 判 HOLD. 四位对处置方式分歧: RETAIN_PARALLEL vs NEEDS_PRIMARY_DOCUMENT vs REJECT_ROW. 未取平均, 未择一主值.

## 八、温度推定
- 推定温度行：**22**
- 其中 model_ready=true：**18**
  - `not_reported`：1
  - `reported`：226
  - `review_table_standard_room_temperature`：21

22/248 行温度是推定值, 其中 18 行 model_ready=true. GVL 冲突的『同温』前提正是两次独立推定碰巧一致 —— 该前提不成立, 因此不能按同温实测矛盾裁决.

## 九、阶段门
**B01 阶段门：OPEN**

无已知缺陷阻塞 B04
