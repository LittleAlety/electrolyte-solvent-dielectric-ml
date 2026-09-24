# v0.3.12 对抗复审轮记录（adversarial-review-optimize）

**日期**: 2026-09-25（Asia/Shanghai）
**基线 SHA**: `024be15` — `feat(data): land the v0.3.12 FEC/VC provenance revision`
**实现修复 revision**: `dd2a37d` — `fix(review): harden the v0.3.12 lineage gate and delivery packages`
**本文件所在提交**: 为该轮复审记录的落盘提交；代码/数据 revision 仍以 `dd2a37d` 为准。
**Scope**: v0.3.12 的 FEC/VC 数据修订、v0.3.2/v0.3.3 lineage 验证、week7/week8 交付包与跨版本文档叙事。
**冻结条件**: 开始时 `git status --porcelain` 为空；主线程是唯一写者，所有复审 agent 均只读。

---

## 1. Reviewer findings by severity

### 第一轮（对 `024be15`）

| 级别 | ID | 位置 | 可复现证据 / 影响 | 最小修复 | 状态 |
|---|---|---|---|---|---|
| Important | T-I1 | `scripts/verify_v032_benchmarks.py:245-266` | 把 `probes/v032_ablation_summary.json` 改成已知坏状态 `source_count=246, excluded_count=5, excluded_not_in_source=[]` 后，旧 verifier 仍 `passed=true, 27/27`。原 Critical 的验证盲区未封堵。 | summary 记录 `source_path/source_sha256`；verifier 显式 pin `245/4/[MOPN]`；加“坏状态必须 FAIL”的回归测试。 | 已修 |
| Important | E-I1 | `probes/export_week7_results.py:199-207,286` | week7 生成器仍写 v0.3.12 “again without moving a dielectric value”与“the stored 102”；与 FEC 102→78.4 的实际修订矛盾。 | 改写 v0.3.12 叙事与 FEC open item；重新导出 week7。 | 已修 |
| Important | E-I2 | `成果输出/week7`、`week8` | 两个交付包没有 README，缺入口、文件职责、复现命令与限制索引。 | 导出器生成 `README.md`，并纳入 `SHA256SUMS`。 | 已修 |
| Minor | T-M1 | `paper/code_and_data.md:104` | “Two rows need explicit qualification”只点名 MOPN。 | 改为逐行点名 MOPN、TEP/TMP、VC、FEC。 | 已修 |
| Minor | T-M2 | `reports/g1_data_gate_review.md:21,63` | VC 状态仍写 `open_access_article_text`；patch 数仍写 19。 | 更新为 `primary_experimental` 与 30 patches。 | 已修 |
| Minor | T-M3 | `reports/decisions_log.md:1681` | 声称三个轻量探针“只差 generated_at_utc”，与真实 diff 不符。 | 改为“均重跑并重钉 dataset hash；manual reconciliation 同时更新快照计数与 current-row 视图”。 | 已修 |
| Minor | E-M1 | `成果输出/数据结果汇总.md:449-452` | 57/71 是复制源工件数，不是最终包文件数 61/75。 | 修正计数口径。 | 已修 |
| Minor | E-M2 | `成果输出/数据结果汇总.md:508` | week 包内 Markdown 计数未含新增 README，也未区分根目录总汇总。 | 改为“包内 72 份 + 根目录总汇总 1 份”。 | 已修 |
| Minor | E-M3 | `成果输出/week8/week8_report.md:113` | `509 passed` 未标为历史值或限定 commit。 | 标注 `at commit 060e9d7 (historical)`。 | 已修 |
| Minor | E-M4 | `成果输出/week7/week7_report.md:83-88` | 旧 FEC/VC 状态易被读成当前状态。 | 改为 v0.3.12 当前状态，并保留 107 腿未读。 | 已修 |

### 第二轮（对交付包与总汇总的 fresh re-audit）

| 级别 | ID | 位置 | 证据 / 影响 | 最小修复 | 状态 |
|---|---|---|---|---|---|
| Important | E2-I1 | `成果输出/数据结果汇总.md:4-5` | 顶部仍写当前 `HEAD 024be15`，而修复 revision 已是 `dd2a37d`。 | 更新为最终复审 revision，并注明 `024be15` 是数据修订提交。 | 已修 |
| Minor | E2-M1 | `week7/README.md:23-26`、`week8/README.md:22-25` | README 写“在本目录运行”，但包内没有 `scripts/`。 | 改为“从仓库根目录运行（scripts/ 不在交付包内）”。 | 已修 |
| Minor | E2-M2 | `成果输出/数据结果汇总.md:449-452` | 包总数/manifest 条目仍未列全。 | 写为最终文件数 61/75，manifest 60/74，复制源 57/71。 | 已修 |
| Minor | E2-M3 | `成果输出/数据结果汇总.md:508` | Markdown 计数需含两个 README。 | 修正为 72 + 1。 | 已修 |
| Minor | E2-M4 | `reports/manual_appendix_reconciliation.md:99-104`、`reports/g1plus_crawl_round3_findings.md:67-82` | 旧稿以现在时写 v0.3.11 的 `765fd8e0…` 为当前哈希。 | 加 v0.3.12 re-pin 注记，当前为 `1b285fe8…22456`。 | 已修 |

---

## 2. Optimizer RED evidence

```powershell
# 已知坏 lineage 状态在旧 verifier 下仍通过 -> 回归测试先红
.\.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider ^
  tests\test_verify_v032_benchmarks.py::test_the_known_bad_v032_lineage_state_is_rejected
# => 1 failed: assert not True  (旧 verify 对 246/5/[] 返回 passed=True)
```

```text
# 导出测试先红：README 生成契约尚不存在
ImportError: cannot import name 'README_TEXT' from 'probes.export_week7_results'
```

独立只读复审员（Turing）在临时目录复现了同一负向对照：旧 `verify_v032_benchmarks.py` 对坏状态给出
`passed=True, 27/27`；修复后 verifier 明确失败于
`v0.3.2 lineage source provenance`。

---

## 3. Optimizer GREEN evidence

- 生成器 `probes/dielectric_representation_ablation.py` 现在写入
  `source_path` 与 `source_sha256`。
- 用正确的 `--source data/dielectric_v032.csv` 重跑后，`probes/v032_ablation_summary.json` 仅新增两行：
  - `source_path = data/dielectric_v032.csv`
  - `source_sha256 = 39d15e161a4fb5cf6dddf31749144ce038078823f7ed02aacbead5a1d75b30be`
  - 计数保持 `source_count=245`、`excluded_count=4`、`excluded_not_in_source=[OOWFYDWAMOKVSF-UHFFFAOYSA-N]`
- `scripts/verify_v032_benchmarks.py` 新增 `v0.3.2 lineage source provenance`，
  `verify_v032_benchmarks.py` 输出 `passed=true, 28/28`。
- `tests/test_verify_v032_benchmarks.py`：`9 passed`；坏状态测试在当前实现下变绿。
- 导出器生成 README 并纳入 `SHA256SUMS`；week7 叙事改为
  “moved the stored FEC dielectric from 102 to 78.4”。
- `tests/test_export_week7_week8_results.py`：`2 passed`。
- 交付包 manifest：week7 `[PASS]`（61 files / 60 entries），week8 `[PASS]`（75 files / 74 entries）。
- 全量：`pytest -q -p no:cacheprovider` **729 passed**；`ruff check .` **All checks passed**；
  7 个 verifier 全绿；`build_paper_full_draft.py --check` up to date。

---

## 4. Re-review verdict on the exact new revision

- **Turing（只读）对 `024be15..dd2a37d`**：
  - 实际 diff：14 files, +261/−27；工作区干净。
  - 确认 T-I1 / E-I1 / E-I2 全部真实修复，且负向测试对旧实现可证伪。
  - `verify_v032_benchmarks.py` → `passed=true, 28/28`；
    `tests/test_verify_v032_benchmarks.py` → 9 passed；
    `tests/test_export_week7_week8_results.py` → 2 passed；
    week7/week8 manifest 均 `[PASS]`；全 7 个 verifier 通过。
  - **结论：No Critical or Important findings; Ready.**
- **Euler（只读）对交付包与总汇总**：
  - 两个 README 已在各自 manifest 中，包内 `dielectric_v03.csv` 哈希与仓库一致；
  - week7 57/57、week8 71/71 复制源工件逐项一致，0 mismatch/0 missing；
  - 第二轮发现 E2-I1 与 4 个 Minor，已全部修复；最终包计数 week7 61/60、week8 75/74。

---

## 5. Final validation commands and results

| 命令 | 结果 |
|---|---|
| `pytest -q -p no:cacheprovider` | 729 passed |
| `ruff check .` | All checks passed |
| `scripts/verify_dielectric_v02.py` | exit 0 |
| `scripts/verify_dielectric_v032.py` | exit 0 |
| `scripts/verify_dielectric_v03.py` | 7/7, 246 rows, `1b285fe8…22456` |
| `scripts/verify_v032_benchmarks.py` | 28/28, 含 lineage source provenance |
| `scripts/verify_dielectric_representation_ablation.py` | exit 0 |
| `scripts/verify_dielectric_target_scaffold.py` | exit 0 |
| `scripts/check_paper_artifact_consistency.py` | paper drafts agree |
| `scripts/build_paper_full_draft.py --check` | up to date |
| `scripts/verify_export_manifests.py --output-dir week7 --output-dir week8` | `[PASS]` `[PASS]` |

---

## 6. Remaining Minor findings / residual risks

- FEC 107 腿（Hagiyama 2008 / Ue 2014）仍受访问权限限制；这是**数据缺口**，不是代码缺陷。
- MOPN 仍缺独立一手确认与 GFN2-xTB 特征行。
- VC 存 `T_K=298.0` 而源文写 25 °C（298.15 K）；行内 notes 已声明 0.15 K 在报告精度内。
- Kobayashi Table 2 的 FEC 行归属依赖 mp/bp/η/ε 指纹对齐，不是行内文字标签；当前未证伪。
- 论文侧仍以 `v0.3.3` 作为数据集血缘标签（未 bump 到 `v0.3.12`），这是先前已记录的决定；一致性脚本仍通过。
- 受限目录 4 个未取值目标、温度带决策与 DC-200 成员表仍为开放数据工作项。
