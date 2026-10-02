# W22-3 收口：数据统一文档 + broad-pool 最小信息预算演示（B5 / D7）

- **性质**：文档统一 + 一次「便宜层预判」演示。**不新增昂贵计算、不拟合模型、不动任何冻结件、不引用任何受限数值、不做 git 操作。**
- **权威依据**：`reports/week22_project_charter.md` §1（B5 / D7）、§2 W22-3。
- **上游资产**：`probes/artifacts/w20_ranking_key_v1_candidates.csv`、`data/processed/four_core_key_registry.csv`、`probes/w20_funnel_kpi_summary.json`、全仓 `data/**` 与 `probes/*_summary.json`。
- **用户交付物**：`E:\Claude Code\电解质ML\成果输出\数据统一文档.md`。

---

## 1 交付物

| # | 路径 | 作用 |
| --- | --- | --- |
| 1 | `probes/build_unified_data_document.py` | 统一数据文档生成器；支持 `--out` 与 `--check`（逐字节重算比对） |
| 2 | `E:\Claude Code\电解质ML\成果输出\数据统一文档.md` | 生成的统一文档 |
| 3 | `probes/w22_broad_pool_budget.py` | broad-pool 预算演示执行体 |
| 4 | `probes/w22_broad_pool_budget_prereg.json` | 跑前锁定的唯一升级判据 + 输入哈希 |
| 5 | `probes/w22_broad_pool_budget_summary.json` | 跑后读数（无时间戳，可复算） |
| 6 | `tests/test_w22_unified_document.py` | pytest 守卫（5 项） |
| 7 | `reports/w22_data_consolidation.md` | 本报告 |

## 2 统一文档覆盖

生成口径：扫描 `data/**/*.csv`、`data/**/*.json`、`probes/*_summary.json`、`probes/artifacts/*.csv`、
`docs/framework/*.md`、`paper/*.md`、`reports/week*_project_charter.md`，逐件登记。

| 扫描组 | 匹配式 | 文件数 | 合计 bytes |
| --- | --- | ---: | ---: |
| data_csv | `data/**/*.csv` | 214 | 313,403,224 |
| data_json | `data/**/*.json` | 2751 | 1,417,007,092 |
| probes_summary | `probes/*_summary.json` | 160 | 6,000,752 |
| artifacts_csv | `probes/artifacts/*.csv` | 128 | 189,660,056 |
| docs_framework | `docs/framework/*.md` | 1 | 54,147 |
| paper_md | `paper/*.md` | 16 | 236,774 |
| charters | `reports/week*_project_charter.md` | 3 | 43,991 |
| **合计** | — | **3273** | **1,926,406,036** |

固定章节（文档内逐节可查）：

| 节 | 内容 |
| --- | --- |
| §0 口径纪律 | 7 条硬约束（不平均冲突值 / 受限源不入可分发数据集 / 同源确认≠独立互证 / 被挡≠查无 / 有效数字随值走 / 否定结果同等收录 / 冻结件零改动） |
| §1 数据表清单 | 覆盖概览 + data CSV 逐件 + data JSON 逐件（含目录汇总）+ artifacts CSV 逐件 + 文档件登记 |
| §2 探针摘要清单 | 每件 sha256 / schema_version / task / title + 前 25 条递归数值标量 |
| §3 冻结读数 | 四条逐位引用 |
| §4 通道覆盖 | `four_core_key_registry.csv` 31949 行的六通道命中数与 `n_core_channels` 分布 |
| §5 KPI 板 | 出自 `probes/w20_funnel_kpi_summary.json` 的 ranking / coverage_cost / discipline |
| §6 负结果登记 | `reports/*.md` 中 `refuted` / `capped` 命中的逐文件计数与逐行摘录 |
| §7 出处索引 | 头条读数 → 源文件对照 |

逐件登记的粒度：

- **数据文件**：相对路径、sha256、bytes、行数/记录数、列数、表头（前 20 列，单元格截断 40 字符）、解析状态。
- **探针摘要**：相对路径、sha256、schema_version、task、title、递归数值标量。
- **文档件**：相对路径、sha256、bytes、标题数、首标题。

大文件纪律：JSON 超过 4 MiB 只登记元数据（`not_parsed_over_4MiB`，共 109 件 / 约 1.1 GB）；
哈希按 1 MiB 分块流式读取；CSV 用流式 reader 计行，45 MB 的候选池与 80 MB 的原始黏度表均不整表载入内存。

## 3 broad-pool 最小信息预算演示（B5 / D7）

**跑前锁定的唯一判据**（`w22_broad_pool_budget_prereg.json`，`prereg_status = locked_before_run`）：

> `domain == 'in_domain'` **且** `on_front` 为真 **且** `key_score` 非空 ⇒ 值得升级到昂贵层。

输入锚定：`probes/artifacts/w20_ranking_key_v1_candidates.csv`，
sha256 `b52f720bfa904a1c71e730e0d8fb2bb7ec7d4041ce9aae7ce7b1835c518ae6c5`，
45,093,401 B / 115,756 行。执行体在开跑前校验该哈希，不一致即拒绝运行。

| 读数 | 值 | 出处 |
| --- | ---: | --- |
| 候选总数 `candidates_total` | 115,756 | 同表行数 |
| 域内数 `in_domain` | 0 | `column=domain` |
| 在 front 数 `on_front` | 0 | `column=on_front` |
| 有分 `key_score_present` | 0 | `column=key_score` |
| **判据升级数 `criterion_upgrade`** | **0** | 三条件与 |
| 被筛掉数 `filtered_out` | 115,756 | 总数 − 升级数 |
| **节省比例 `savings_ratio`** | **1.0** | `1 − 升级数 / 总数` |

**诚实范围（必须与排序质量分开叙述）**：该池是按发布前锁定的 D1 域规则
（`NumHDonors ≥ 1` 且 `TPSA ≥ 20`）生成的 Tier C 单点筛查池，全部 115,756 行判域外
（`excluded_reason` 直方图只有 `out_of_domain` 一项），因此**没有候选获得分数、前沿为空**。
节省比例 1.0 由**域闸门**承担，不是由排序键承担；本演示证明的是「便宜层可以在花钱之前过滤掉整个池」，
**不能**被读成「排序键本身有 100% 的筛选力」。分解读数（`rows_with_both_key_dimensions = 115,756`、
`ranked_rows = 0`）同时登记在 `_summary.json::diagnostics`，供审稿人核对贡献归属。

## 4 可复算性与并发说明

- **`--check` 语义**：不写盘，在内存中按当前树重建文档，与 `--out` 指定文件逐字节比对，不一致时打印首个差异字节偏移并返回 1。
- **无时间戳**：文档与 `_summary.json` 均不含生成时间；相同输入必然得到相同字节。
- **并发漂移（照实登记）**：本轮运行时同仓的 W22-4 lane 正在写 `paper/*.md`，
  其它 lane 也在新增 `probes/*_summary.json` 与 `probes/artifacts/*.csv`。
  首次 `--check` 在 byte 1969（§1.1 概览行）报 `DRIFT`，同一长度、不同内容 —— 属工作区被并发改写的环境现象，
  不是生成器缺陷。随后「重建 → 立刻校验」一次即 `[check] OK`，文档收敛。
- **结论**：`--check` 保证的是「文档 = 当前树的纯函数」；在并发写入停止的时刻，两者逐字节一致。

## 5 自检

| 检查 | 结果 |
| --- | --- |
| `pytest tests/test_w22_unified_document.py` | **5 passed**（合成仓确定性往返 / 单字节漂移检出 / 交付文档章节与冻结读数 / 活仓往返 / broad-pool 锁定与钉值） |
| `--check`（交付文档本体） | 重建后 `[check] OK`（1,011,966 B 逐字节一致） |
| 两次生成 sha256 | 同一次往返内逐字节相同（合成仓与活仓两条路径都断言了这一点） |
| 冻结件 | 四读数逐位未动；`main_scoreboard_attempts` 本周 0 次、累计 11 次（`_summary.json` 内只读引用，未触发） |
| 昂贵计算 | 0 次；仅流式扫描既存文件 |

## 6 产物行数 / bytes / sha256

| 产物 | 行数 | bytes | sha256 |
| --- | ---: | ---: | --- |
| `probes/build_unified_data_document.py` | 513 | 23,100 | `c15c5454d8642ddcdaad6b5dfdcf3eba12769d885e6ed071d5c98d839f961505` |
| `成果输出/数据统一文档.md` | 7,936 | 1,011,966 | `2f1276c1140acf50a4b5a137bb8f0108576d5770c75468574b3dcab450dcde79` |
| `probes/w22_broad_pool_budget.py` | 203 | 8,504 | `f4c7035c6b2ce27940cd233a423cc896d389631d8b98a55f1ec7cbf278dcba2b` |
| `probes/w22_broad_pool_budget_prereg.json` | 47 | 2,373 | `6bfef93d251c417c750a6ef067a0ce4d08b8dd3ea692e2a6289948da7e7e4cfd` |
| `probes/w22_broad_pool_budget_summary.json` | 110 | 3,677 | `261c1570a5146cd175f656e46e844573e30b4b2068aa618cd1b6bb59465173da` |
| `tests/test_w22_unified_document.py` | 189 | 7,095 | `b750dea9f5a0be21ab1c1c651946d6037cfab360d2860664f380b718a3b1b867` |

注：本报告自身的哈希不列入上表（自引用会形成不动点问题）；它的文本会被统一文档 §6 作为扫描输入登记。