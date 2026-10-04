# W49 投稿包落地（默认 venue = PCCP，0 shot）

类④（投稿操作）+ 类③（round-2 登记）。venue 默认 PCCP，可被用户一票覆盖。

## 1 投稿包四件

| 件 | 状态 |
| --- | --- |
| 期刊模板 docx | 在（段 412 / 表 9 / 图 25，sha256 b3708b75db11deb4） |
| cover letter | 在 |
| 可复现性声明 | 在 |
| submission manifest | 在 |

- 图片完整性：实测 25 图，最大长宽比偏差 2.4281268384829247e-07，越界 []。
- 包目录：E:\Claude Code\电解质ML\成果输出\week49\投稿包。

## 2 判据

| id | 判据 | 值 | 阈 | 判决 |
| --- | --- | --- | --- | --- |
| H49a1 | 形式适配映射清单交付且覆盖四类形式项（标题页/摘要/图件/参考文献） | {"exists": true, "markers": {"① 标题页": true, "② 摘要": true, "③ 图件": true, "④ 参考文献": true}} | {"markers": ["① 标题页", "② 摘要", "③ 图件", "④ 参考文献"]} | 成立 |
| H49a2 | 期刊模板 docx 结构与当前 v3 一致（段/表/图计数） | {"exists": true, "paragraphs": 412, "tables": 9, "figures": 25, "bytes": 4493314} | {"paragraphs": 412, "tables": 9, "figures": 25} | 成立 |
| H49a3 | 25 图逐图可完整显示：长宽比偏差 < 1e-3 且不超版面框 | {"n_measured": 25, "max_aspect_deviation": 2.4281268384829247e-07, "overflows": [], "usable_cm": [16.4, 23.3]} | {"min_measured": 25, "max_aspect_deviation": 0.001, "overflows": []} | 成立 |
| H49b1 | 投稿四件齐备（docx / cover letter / 可复现性声明 / manifest） | {"docx": true, "cover_letter": true, "reproducibility": true, "manifest": true} | {"all_four": true} | 成立 |
| H49b2 | 可复现性声明与导出包互指（week47 包 + SHA256SUMS + 基线 commit） | {"markers": {"成果输出/week47": true, "SHA256SUMS": true, "92d47b8": true}} | {"markers": ["成果输出/week47", "SHA256SUMS", "92d47b8"]} | 成立 |
| H49b3 | 形式改动零科学漂移：一致性校验 PASS 且四个冻结读数逐字在稿 | {"consistency_returncode": 0, "readings_literal": {"0.4091179943351143": true, "0.4766400383507876": true, "0.5861142332208197": true, "0.6216672295270079": true}} | {"consistency_returncode": 0, "all_literal": true} | 成立 |
| H49b4 | 0 shot（投稿操作不占主记分牌） | {"shots_this_week": 0} | {"shots": 0} | 成立 |
| H49d1 | README §11 第 54 条 round-2 登记落字 | {"markers": {"54. **新登记（W49）": true, "round-2": true}} | {"markers": ["54. **新登记（W49）", "round-2"]} | 成立 |
| H49d2 | 不变量复算一致：9 条负结果 / shot 19 / 冻结读数不在 canon 外 | {"registered_negatives": 9, "cumulative_shots_max": 19, "frozen_outside_canon": 0} | {"registered_negatives": 9, "cumulative_shots_max": 19, "frozen_outside_canon": 0} | 成立 |
| H49d3 | 0 shot（结算周不改主记分牌） | {"shots_this_week": 0} | {"shots": 0} | 成立 |

