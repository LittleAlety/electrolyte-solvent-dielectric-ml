# B01 测量账本 schema 符合性检查
> 生成器 `audit_b01_schema_conformance/1.0.0` · 2026-11-23T14:34:34Z
> 只判断字段是否诚实存在。不重命名列、不改写账本字节。

## 一、结论
- 账本行数：**2065**，列数：**28**
- PLAN B B01 要求的 14 个字段中：

| 判定 | 字段数 |
|---|---:|
| `PRESENT_AS_NAMED` | 4 |
| `PRESENT_UNDER_ALIAS` | 9 |
| `ABSENT_STRUCTURALLY` | 1 |
| `NOT_EVALUATED_FILLER` | 0 |

- **真实缺口：0 个** — 无

## 二、逐字段明细
| PLAN B 字段 | 实际列 | 判定 | 覆盖率 | 说明 |
|---|---|---|---:|---|
| `measurement_id` | `measurement_id` | PRESENT_AS_NAMED | 100% |  |
| `molecule_id` | `molecule_key` | PRESENT_UNDER_ALIAS | 100% | 同义: molecule_key 承载分子主键. 另有 a_mol_id (A 仓编号) 与 inchikey. |
| `InChIKey` | `inchikey` | PRESENT_UNDER_ALIAS | 100% | 大小写差异, 信息完整 |
| `temperature_raw_K` | `temperature_K` | PRESENT_UNDER_ALIAS | 100% | 列名少了 _raw. 需人工确认数值是否为未经折算的原始温度 |
| `dielectric_raw` | `dielectric` | PRESENT_UNDER_ALIAS | 100% | 列名少了 _raw. 需人工确认是否为原始值而非聚合值 |
| `phase` | `phase` | PRESENT_AS_NAMED | 100% |  |
| `frequency_Hz` | `frequency_hz` | PRESENT_UNDER_ALIAS | 100% | 大小写差异 |
| `pressure` | `pressure_kpa` | PRESENT_UNDER_ALIAS | 100% | 单位为 kPa, 已显式标注; 不可与 Pa 混用 |
| `source_document_id` | `source_document_id` | PRESENT_AS_NAMED | 100% |  |
| `evidence_group_id` | `evidence_group_id` | PRESENT_AS_NAMED | 100% |  |
| `measurement_locator` | — | ABSENT_STRUCTURALLY | 0% | 账本本身无定位符列. **已在 b01/measurement_locator_v1.csv 中单独交付**: 定位到 ThermoML block/property/row (2065/2065 覆盖). 定位到论文页码仍不可得, 因 ThermoML 不携带页码, 编造页码属伪造. |
| `extraction_method` | `method` | PRESENT_UNDER_ALIAS | 100% | 语义不同: method 是测量方法 (平行板电容/谐振腔...), 不是**提取**方法 (人工转录/XML 解析/OCR). 提取方法实际未记录, 应按缺口处理. |
| `source_hash` | `source_file_sha256` | PRESENT_UNDER_ALIAS | 100% | 文件级 sha256 |
| `verification_status` | `traceability_status` | PRESENT_UNDER_ALIAS | 100% | 语义不同: traceability_status 记录可追溯性, 不是审核/验证状态 |

## 三、必须区分的三处语义差异
以下三处如果只看列名会误判为「已满足」，实际语义不同，本检查判为缺口或降级：

1. **`extraction_method` vs `method`**
   `method` 记录的是**测量方法**（平行板电容、重入腔谐振器、阻抗分析仪…），不是**提取方法**（人工转录 / XML 解析 / OCR）。PLAN B 要求的是「这个数字是怎么从原文搬进数据库的」，账本没有记录这一层。
2. **`verification_status` vs `traceability_status`**
   `traceability_status` 记录「能否追溯到源文件」，不是「是否经过审核」。两者不能互相替代：一条测量可以完全可追溯但从未被审核。
3. **`measurement_locator`**
   完全缺失。`source_row_index` 只能定位到源文件的行号，不能定位到论文的表格/图/页码。对于需要回原文复核的测量，这是硬缺口。

## 四、账本内的单位与属性声明
- `epsilon_unit` 分布：`{'not_evaluated': 2065}`
- `property_name` 分布：`{'Relative permittivity at zero frequency': 1630, 'Relative permittivity at various frequencies': 435}`
- `traceability_status` 分布：`{'TRACEABLE': 2065}`

epsilon_unit 全部为占位符, 意味着介电常数的单位在账本内**未被显式声明**. 静态相对介电常数应无量纲; 该假设目前依赖上游, 不是账本保证.

## 五、本检查不做什么
- 不重命名任何列（会让下游静默改变语义）
- 不把 `method` 复制进 `extraction_method`（那是伪造提取方法）
- 不补造 `measurement_locator`（需要回原文逐条核对）
- 不修改账本字节；本检查只读
