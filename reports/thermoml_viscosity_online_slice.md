# T1 在线黏度切片核查（NIST/TRC ThermoML JSON API）

- 探针：probes/thermoml_viscosity_online_slice.py
- 预注册（跑前冻结）：probes/thermoml_viscosity_online_slice_prereg.json，sha256 f62ad8eca0bea4714cbfad63e7af028c7b3c202d3e899675981289970feb4389，locked_at_utc 2026-09-26T10:17:13Z，status locked_before_run
- 机读汇总：probes/thermoml_viscosity_online_slice_summary.json
- 复现：首跑 --resolve-online（联网）；--check 离线零网络，与磁盘产物比对
- 建模：无。冻结数据集写入：无。本轮不改任何既有文件。

## 1 在线读数（口径：记录数，不是数据行数）

| 检索词 | 在线 size（记录数） | 已抓记录数 | 页数 | 结构化 ePropName 命中 | 仅 phrase 命中 |
|---|---:|---:|---:|---:|---:|
| * | 11923 条记录 | — | 1 | — | — |
| "Viscosity, Pa*s" | 1690 条记录 | 1690 | 17 | 1690 | 0 |
| "Kinematic viscosity, m2/s" | 70 条记录 | 70 | 1 | 70 | 0 |

- 判据 A：在线三数逐位复现，0 条违反，允许 0，判 通过。

## 2 本地 ⊆ 在线（判据 B）

- 本地来源：probes/thermoml_viscosity_coverage_summary.json，含黏度 XML 29 个（逐条判定 29 条）。
- 命中在线黏度切片并集：29 / 29；其中结构化 ePropName 命中 29 个，仅 phrase 命中 0 个。
- 未命中清单：无

| 本地 DOI | 在 Viscosity Pa*s 切片 | 在 Kinematic viscosity 切片 | 匹配性质 |
|---|---|---|---|
| 10.1007/s10765-007-0220-0 | 是 | 否 | structured_property |
| 10.1016/j.fluid.2011.11.002 | 是 | 否 | structured_property |
| 10.1016/j.fluid.2016.10.026 | 否 | 是 | structured_property |
| 10.1016/j.fluid.2016.11.029 | 是 | 否 | structured_property |
| 10.1016/j.fluid.2017.07.006 | 是 | 否 | structured_property |
| 10.1016/j.fluid.2019.06.022 | 是 | 否 | structured_property |
| 10.1016/j.jct.2006.01.011 | 是 | 否 | structured_property |
| 10.1016/j.jct.2010.10.016 | 是 | 否 | structured_property |
| 10.1016/j.jct.2012.11.020 | 是 | 否 | structured_property |
| 10.1016/j.jct.2013.03.018 | 是 | 否 | structured_property |
| 10.1016/j.jct.2013.05.025 | 是 | 否 | structured_property |
| 10.1016/j.jct.2013.08.034 | 是 | 否 | structured_property |
| 10.1016/j.jct.2014.09.015 | 是 | 否 | structured_property |
| 10.1016/j.jct.2015.08.013 | 是 | 否 | structured_property |
| 10.1016/j.jct.2018.04.007 | 是 | 否 | structured_property |
| 10.1016/j.tca.2013.11.010 | 是 | 否 | structured_property |
| 10.1016/j.tca.2015.08.013 | 否 | 是 | structured_property |
| 10.1016/j.tca.2016.03.002 | 是 | 否 | structured_property |
| 10.1021/acs.jced.8b00153 | 是 | 否 | structured_property |
| 10.1021/je030127e | 是 | 否 | structured_property |
| 10.1021/je049576k | 是 | 是 | structured_property |
| 10.1021/je0496903 | 是 | 否 | structured_property |
| 10.1021/je100594u | 是 | 否 | structured_property |
| 10.1021/je300603d | 是 | 否 | structured_property |
| 10.1021/je301333b | 是 | 否 | structured_property |
| 10.1021/je400783h | 是 | 否 | structured_property |
| 10.1021/je800562h | 是 | 否 | structured_property |
| 10.1021/je800664z | 是 | 否 | structured_property |
| 10.1021/je900709n | 是 | 否 | structured_property |

## 3 口径诚实性（判据 C）

- 在线 size 是检索命中的 ThermoML 记录（文档）数，不是数据行数，不能与本地解析器的行数直接相减或相除。
- 在线数据行数：unknown —— JSON API 只暴露记录数；记录内的 data_summary 是 NIST 侧的另一种计数单位（data_points），与本地解析器的 PropertyValue 行不同口径，故不用它顶替行数，也不做任何估计。
- 检索词走的是全文 phrase 索引：命中不代表记录里真有同名的结构化属性。本探针逐记录检查结构化 Property 字段的 ePropName，两者分别计数。
  - viscosity_pa_s：size 1690 条记录，结构化命中 1690 条记录，仅 phrase 命中 0 条记录。
  - kinematic_viscosity：size 70 条记录，结构化命中 70 条记录，仅 phrase 命中 0 条记录。
- 覆盖率（记录口径）：29 / 1690 条记录 = 1.7160%。
- 覆盖率（行口径）：不可比 —— 本地 2725 行是 XML 属性行；在线行数不可得（见 online_row_count），故按行口径的覆盖率不可比，也不给数。
- 判据 C：0 条违反，允许 0，判 通过。

## 4 读数与边界

- 在线全库 11923 条记录（检索词 * 的 size 记录数），其中 Viscosity Pa*s 切片 1690 条记录、Kinematic viscosity 切片 70 条记录，三数与预注册逐位一致。
- 本地 29 个含黏度 XML 的 DOI 29 / 29 命中在线黏度切片并集，未命中 0 条。
- 检索词索引是全文 phrase 索引：Viscosity Pa*s 切片里结构化 ePropName 命中 1690 条记录，仅 phrase 命中 0 条记录，两者已分开计数。
- API 分页口径已实测锁死：pageNum 是 0 基的（窗口 [pageNum*pageSize, (pageNum+1)*pageSize)）；本轮两个切片都从 pageNum=0 抓全，逐切片 records_collected 与 size 记录数相等且 DOI 唯一。
- 在线 size 是记录数，不是数据行数；在线行数记 unknown，本地 2725 行与在线记录数不可比，本探针不给任何行口径覆盖率。
- 「本地 ⊆ 在线」只说明本地 29 个文件都在在线黏度切片里，不说明「在线 = 本地」：本地是为介电检索组建的筛选缓存，不是 NIST 全库。
- 切片只取两个黏度属性名（Viscosity, Pa*s 与 Kinematic viscosity, m2/s），其它黏度写法不计入，避免把 phrase 噪声当属性。
- 本探针只测量：不拟合模型、不产 R2/MAE、不把任何值写进 data/ 冻结表。

## 5 复现

- 首跑：python probes/thermoml_viscosity_online_slice.py --resolve-online
- 增量：python probes/thermoml_viscosity_online_slice.py
- 离线核查：python probes/thermoml_viscosity_online_slice.py --check
- 在线清单摘要指纹（slices_sha256）：52aa8d68c69438b0d3a2727f7ba66dbe148083a648cdd2b1b88904409ae2a9be
