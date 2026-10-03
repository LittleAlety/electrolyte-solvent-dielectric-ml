# Week 37 立项章：README §11 剩余三条一次性收口（全部后验，不占 shot）

**日期**：2026-10-03
**上一轮**：W36（README §11 第 4/6/7/14/15 条一次性收口 ＋ week1–36 工作日志）
**本轮范围**：README §11 第 **16 / 17 / 18** 条 —— 这是 §11 里最后三条「已登记、未执行」。
**shot 账本**：三条 lane 全部是后验读数 / 治理件 / 装配源回灌：**本轮 0 shot，累计仍 19**。
**四个冻结读数**：`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` /
`0.6216672295270079`，本轮**一个都不动**。

---

## 1. 为什么是这三条

W36 收口后，README §11 只剩三条没有着落，而它们**互相咬合**：

- 第 16 条（**装配源回灌**）是**字节级**问题：`paper/_v2_*.md` 与已发布稿
  `paper/paper_zh_draft_v2.md` 之间登记了 11 段漂移，W36-E 只登记没修。只要不修，
  任何人跑一次 `paper/build_paper_v2.py` 就会把这些段落（§3.8.1、§3.21、
  附录里的 5 + 16 + 2 行）从交付字节里**删掉**。这与 AF-12 同族：交付字节与声明的来源不一致。
- 第 17 条（**端点判等容差守卫**）是**判据级**问题：W36-A 把「端点判等容差 = `1e-12`」
  写成了规则 R5，但没有任何东西阻止后来的人再写 `if value == 0.5861142332208197:`。
  规则不入守卫，等于没有规则。
- 第 18 条（**准入清单接进交付/导出链路**）是**流程级**问题：W36-D 造好了 `admit()`，
  但它是**自觉**调的。未登记的还原轴引用点必须在**导出阶段**就失败，而不是靠人记得。

一句话：**W36 把三条「知道但没做」写进了册子，W37 把三条都接到机器上。**

## 2. 三条 lane

| lane | 回答 | 做法 | 判据 |
| --- | --- | --- | --- |
| **W37-C** 装配源回灌 | §11 第 16 条 | 用重建器把装配源拼成临时产物、与已发布稿做 difflib 比对；每段按机械规则选家（追加 / 就地插入 / 锚点拼接），直到漂移为 0；要求重建产物与已发布稿**逐字节相等** | H37c1–H37c6（6 条） |
| **W37-A** 端点判等守卫 | §11 第 17 条 | AST + 子串扫描仓库内「8 位以上有效数字字面量做 `==` / `!=`」的点，逐条判「允许 / 禁止」；提供 `endpoints_equal()`（容差取自注册表 R5）与合成违规自检 | H37a1–H37a5（5 条） |
| **W37-B** 准入接进导出 | §11 第 18 条 | `scripts/check_redox_admission.py` 把论文附录 A 的还原轴引用点逐个对回登记表并要求 `admit()` 通过；把它挂进 `tests/test_repo_hygiene.py`（各周导出器的 VERIFIERS 都引用该文件），于是**导出阶段的验证块自动带上准入检查** | H37b1–H37b5（5 条） |

合计 **16 条判据**。

### W37-C 的两处非平凡发现

1. **漂移是 11 段，但要回灌 12 段。** 第一轮把 §3.21 追加进 `_v2_body_b.md` 之后，
   重建产物仍与已发布稿差**一个空行**——因为装配器对每个部分都跑 `strip_rules`
   （尾部空行与 `---` 一律剥掉），而交付字节在 §3.21 末尾有两个空行。
   所以那段只能用**最终产物上的锚点拼接**复现。本件因此写成**多轮收敛**（本轮 2 轮）。
2. **§3.1–§3.14 没有独立装配源。** 那一段是从 v1 线 `paper/paper_zh_draft.md`
   按 `## 3 结果` → `## 4 讨论` **切片**来的。把 v2 专有的段落直接写进 v1 线，
   等于把 v2 的内容泄漏进 v1 交付物；因此 §3.8.1 / §3.10 / §3.14 三段写成
   `paper/_v2_splices.json` 的**锚点清单**，正文落在 `paper/_v2_splice_<节号>_<sha8>.md`。
   锚点命中数必须**恰好为 1**，否则 `build_paper_v2.py` 直接报错退出（不静默漂移）。

## 3. 交付物

| 类别 | 路径 |
| --- | --- |
| 探针 | `probes/w37_v2_backfill.py`、`probes/w37_endpoint_tolerance_guard.py`、`probes/w37_gate_admission_export.py` |
| 校验器 | `scripts/check_redox_admission.py` |
| 装配源 | `paper/_v2_splices.json`、`paper/_v2_splice_sec381_*.md`、`paper/_v2_splice_sec310_*.md`、`paper/_v2_splice_sec314_*.md`、`paper/build_paper_v2.py`（新增拼接步骤） |
| 产物 | `probes/artifacts/w37_v2_backfill_{inventory.csv,summary.json}`、`probes/artifacts/w37_endpoint_{compare_sites.csv,tolerance_guard_summary.json}`、`probes/artifacts/w37_gate_admission_export_{sites.csv,summary.json}` |
| 报告 | `reports/w37_v2_backfill.md`、`reports/w37_endpoint_tolerance_guard.md`、`reports/w37_gate_admission_export.md` |
| 测试 | `tests/test_w37_v2_backfill.py`、`tests/test_w37_endpoint_tolerance_guard.py`、`tests/test_w37_gate_admission_export.py`、`tests/test_repo_hygiene.py`（追加一条） |
| 导出 | `probes/export_week37_results.py` → `成果输出/week37` |

## 4. 判据一览

| lane | 判据 | 内容 | 读数 |
| --- | --- | --- | --- |
| W37-A | H37a1 | 注册表 R5 读出容差 == `w36_endpoint_rule.ENDPOINT_TOLERANCE` == `1e-12` | 1e-12 / 1e-12 |
| W37-A | H37a2 | 现存禁止项 = 0（扫 `probes` / `scripts` / `src` / `tests` 的高精度字面量 `Eq` / `NotEq`） | 0 禁止 / 95 允许 |
| W37-A | H37a3 | 合成违规 `if value == 0.5861142332208197:` 被抓 | 1 / 1 |
| W37-A | H37a4 | 合法用法 `abs(a - b) <= ENDPOINT_TOLERANCE` 不被误抓 | 0 / 0 |
| W37-A | H37a5 | `endpoints_equal` 容忍 1–2 ulp、拒绝 `1e-9` 级差异 | 1 / 1 |
| W37-B | H37b1 | 校验器在真表上 exit 0 且 JSON `passed = true` | 1 / 1 |
| W37-B | H37b2 | 论文侧引用点 ≥ 6 且全部找到登记行（未登记 0） | 7 点 / 未登记 0 |
| W37-B | H37b3 | 还原轴引用点全部由 W34-A 守卫复算（mark 非空、零不一致）；氧化轴标「不适用」 | 5 / 5 |
| W37-B | H37b4 | 合成违规：删行 / 改名 → exit ≠ 0；未改动副本 → exit = 0 | 3 / 3 |
| W37-B | H37b5 | 0 shot、累计 19、全 LF / 无 BOM、输入 sha256 前后相等 | 0 / 0 |
| W37-C | H37c1 | 回灌前漂移段数（登记值，不设门） | 11 段（第 2 轮再暴露 1 段） |
| W37-C | H37c2 | 回灌后漂移段数 | 0 |
| W37-C | H37c3 | 重建产物与已发布稿逐字节相等 | 相等 |
| W37-C | H37c4 | 已发布稿 sha256 在回灌前后未变 | `dfb3b282f8cc…` 未变 |
| W37-C | H37c5 | 真跑 `build_paper_v2.py`（不加 `--force`）后交付字节未变（变了则自动回滚） | exit 0 / rolled_back False |
| W37-C | H37c6 | 回灌件数 = 漂移段数（无遗漏） | 12 / 12 |

## 5. 边界与不做清单

- **不占 shot**：三条 lane 都不拟合主记分牌臂、不新增特征列、不改 `METRIC_NAMES`、缺行不插补。
- W37-C **不重新生成任何数字**：回灌是逐字搬运；已发布稿的字节由 sha256 钉住，
  重建器真跑一次也不能改动它们（若改动，探针自动回滚并把判据记判否）。
- W37-A 的 `1e-12` 是**判等容差**，不是新的显著性门；扫描边界是「≥ 8 位有效数字的字面量比较」，
  **不覆盖**运行期变量之间的一般相等。
- W37-B 的门禁**只覆盖还原轴**（阴离子态审计）；氧化轴引用点按既有约定标「不适用」。
  其读数令牌是**静态词汇表**（为了让「删掉登记行」可被查出），因此论文里全新出现的、
  不在词汇表内的未登记数值**不会被拦截**——这是已知边界，写在报告第 6 节。
- **不做**：不把 bootstrap 区间外推；不把区间跨 0 读成「证明无差异」；不把拒答当缺失值；
  不把单表示读数与冻结头条 `0.4766400383507876` 混比。
