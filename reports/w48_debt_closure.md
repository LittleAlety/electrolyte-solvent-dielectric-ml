# W48-D §4.6 欠账终稿（逐条对照表）

修正案 A2 落地件：README §11 已登记欠账在论文 §4.6「已登记欠账的收口状态（W48）」逐条落字，二选一（照实写「未完成」或显式转 round-2），无沉默项。

## 1 逐条对照

| 欠账 | 内容 | §4.6 标记 | 是否落字 |
| --- | --- | --- | --- |
| README-33/36/40 | strict same-level 独立源仍为 0 | strict same-level 独立源仍为 0 | 是 |
| README-42 | 扩展层标定列是 in-sample 仿射 | §11-42 | 是 |
| README-45 | 还原轴候选描述符族门禁后不可判定 | §11-45 | 是 |
| README-46 | 盘上同装置还原锚点数 = 0 | §11-46 | 是 |
| README-49 | 还原轨覆盖并集 2/7 < 5，H47a2 拒答 | §11-49 | 是 |
| README-50 | Borodin 2013 是纯氧化论文 | §11-50 | 是 |
| README-51 | 氧化轴交叉一致性只作敏感性读数 | §11-51 | 是 |
| README-52 | Ue 1997 还原侧取件收口 | §11-52 与 Ue 1997 还原侧 | 是 |
| D2 | D2 的 r2SCAN-3c 版本未计算 | D2 的 r2SCAN-3c 版本 | 是 |
| D3 | D3（ddCOSMO 垂直 EA）未计算 | D3（ddCOSMO 垂直 EA） | 是 |
| dipole_transfer_v1 | 维持 registered_not_authorized | dipole_transfer_v1 | 是 |

- 处置词覆盖：未完成=有，round-2=有，已收口=有，已封顶=有，未授权=有。
- §4.6 小节长度：2657 字符。

## 2 改稿范围与不变量

- 只改 paper/paper_zh_draft_v3.md 的 §4.6；paper/paper_zh_draft_v2.md 与 _v2_* 冻结件零字节改动。
- 论文 v2 sha256 = c7bc66296e18cd63（与冻结值一致：是）。
- 论文 v3 sha256 = 9b93ab3b210ccd86e4afe76cb0a0df432adce5aeb7943ee106cf311a385452dd（变化登记在本件）。
- 四个冻结读数、9 条负结果、累计 shot 19 不动；无附录标题；25 张图链接全在盘。
- 治理件 check_paper_artifact_consistency.py 复跑返回码 = 0。

## 3 判据

| id | 判据 | 值 | 阈 | 判决 |
| --- | --- | --- | --- | --- |
| H48d1 | §4.6 逐条登记 33/36/40/42/45/46/49-52 + D2/D3/dipole，无沉默项 | {"n_items": 11, "missing": [], "readme_boundary_missing": []} | {"missing": [], "readme_boundary_missing": []} | 成立 |
| H48d2 | 改稿只落 v3；v2 sha256 不动；paper_artifact_consistency 复跑 PASS | {"paper_sha256": "9b93ab3b210ccd86e4afe76cb0a0df432adce5aeb7943ee106cf311a385452dd", "paper_v2_sha256": "c7bc66296e18cd6384760a3b49014800662800f5141124365fccf31fdaf1b50f", "paper_v2_unchanged": true, "consistency_returncode": 0} | {"paper_v2_unchanged": true, "consistency_returncode": 0} | 成立 |
| H48d3 | 0 shot；不新增判据族（H48d*） | {"shots_this_week": 0, "criteria_ids": ["H48d1", "H48d2", "H48d3"]} | {"shots": 0} | 成立 |

