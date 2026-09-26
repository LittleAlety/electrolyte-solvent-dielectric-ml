# W17-2 Reaxys 薄家族定向补货（预注册队列 + 覆盖缺口算术）

**一句话**：本臂产出**手工查询队列**与**低界缺口算术**，**不执行任何 Reaxys 查询、不产 R²**
（`reaxys_queries_executed = 0`）；五族全部**未**达「族内 ≥ 5 物质且 ≥ 2 独立来源」下沿。

生成脚本：`probes/reaxys_thin_family_backfill.py`；预注册：
`probes/reaxys_thin_family_backfill_prereg.json`；队列：
`probes/reaxys_thin_family_backfill_queue.csv`（124 行）；护栏 `tests/test_reaxys_thin_family_backfill.py`。

## 1. 五族现状与缺口（口径 = 本仓 `classify_family`，与覆盖缺口表逐项吻合）

| 族 | 现有物质 | 现有行 | 独立来源 DOI | 缺物质 | 缺来源 | 队列候选 |
|---|---|---|---|---|---|---|
| acid | 1 | 1 | 1 | 4 | 1 | 58 |
| lactone | 1 | 5 | 1 | 4 | 1 | 1 |
| carbonate | 2 | 10 | 1 | 3 | 1 | 7 |
| sulfone | 2 | 113 | **5** | 3 | 0 | 54 |
| protic_ionic_pair | 4 | 4 | 1 | 1 | 1 | 4 |

要点：**sulfone 不缺来源只缺物质**（113 行、5 个 DOI，却只 2 个化合物 → 典型的"深而不宽"）；
**acid 最薄**（1 物质 1 行 1 来源）；**protic_ionic_pair 差 1 物质 1 来源**即可达下沿。
五族**没有一族**达下沿，所以 W17-0 的靶子（骨架外推 R² 0.276）**本轮未被攻下**——本臂只把弹药摆好。

## 2. 队列构成（124 行）

- **14 行**来自 `probes/reaxys_v1x_stocking_queue.csv`（167 行库存队列里落在五族的行），
  带 InChIKey、SMILES 派生的结构族标签、stocking_priority 与 local_rows；
- **110 行**来自受限 SpringerMaterials 标题索引
  `data/restricted/springer_materials/interactive_pure_dielectric_catalog.json`（1,670 条 title），
  **只有名字、没有数值**，`candidate_family_confidence = name_keyword_only`，属**线索**不属证据；
- 排序规则**跑前锁定**在预注册里：库存队列行 > 标题索引线索；再按 P1 < P2 < P3；
  再"已带 InChIKey"优先；再按名字升序。
- 标题索引的 acid 线索排除了 `ester / amide / amino / salt / anhydride` 字样——否则像
  "…acid methyl ester" 这样的酯会被当成羧酸塞进来（未加排除时 acid 线索虚高到 295 条）。

## 3. 渠道合规与受限值契约（照抄，未放宽）

- **逐条手工查询，批量爬虫禁止**；restricted 值**只作 crosscheck**，
  **不进 `data/`、不进任何池、不可再分发**；队列文件**只带名字、InChIKey 与覆盖事实**。
- 对外分发时该队列**整文件排除**（口径见 `reports/decisions_log.md` §28.2）。
- `data/restricted/springer_materials/interactive_pure_dielectric_catalog.json` 是**本机专属**，
  干净克隆上不存在；此时脚本把标题索引降级为 `available = false` 并照常出队列（零网络复现）。
- **不绕版权**：Schrödinger 受限 858 行照旧不取。

## 4. 诚实边界（不许省略）

1. 队列是**计划不是测量**：本臂没有执行任何 Reaxys 查询（`reaxys_queries_executed = 0`），
   因此**不得**引用任何覆盖增量或 R²。
2. 结构族标签对库存队列行是**结构判定**（`classify_family`），对标题索引线索是**关键词判定**，
   两者置信度不同，已在 `candidate_family_confidence` 列分开标注。
3. 标题索引的线索**未做电池相关性排序**（含大量脂肪酸等），需人工 triage；这是"线索"而非"候选"。
4. 观测表行口径与在线 ThermoML 切片口径**不可比**；本臂只用本地表。
5. 库存队列自带的 `family_tag` 是**另一套分类**（`other / alcohol_amine / ionic_liquid / …`），
   与本仓 `classify_family` 不同名不同义；本臂统一用后者，避免两套标签混用。

## 5. 复现

    .\.venv\Scripts\python.exe probes\reaxys_thin_family_backfill.py
    .\.venv\Scripts\python.exe -m pytest tests\test_reaxys_thin_family_backfill.py -q -p no:cacheprovider

树上有受限目录时也会读标题索引；干净克隆上自动降级，`--check` 语义与其余探针一致。
