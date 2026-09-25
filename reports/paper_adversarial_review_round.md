# Week 10 M-1 论文对抗审读记录（adversarial-review-optimize）

- 冻结基线：`795b52c`（main；审读开始时 `git status --short` 为空，工作区干净）
- 审读范围：`paper/` 五节分稿 + `paper/full_draft.md`（由 `scripts/build_paper_full_draft.py` 拼装）+ 六图产物 + 五个 verifier
- 角色分离：reviewer = Mill（独立只读 agent，全程未写任何文件）；writer / auditor = 主线程
- 结论：**1 Critical + 1 Important + 4 Minor 被采纳并修复；1 条 reviewer 意见经复核驳回；1 条静态判断未复现、留档不处置**

> 过程说明：审读期间主线程在 reviewer 未返回时先落了两处已独立复现的修改（m-1、m-3），因此 reviewer 报告里"工作区出现 4 个未提交改动"是主线程并发写入，不是 reviewer 越界。冻结基线仍是 `795b52c`，全部结论按该 commit 定格，修复后对**新 SHA** 重跑了全套闸门。

## 1. 采纳并修复

| 编号 | 级别 | 位置 | 缺陷 | 处置 |
| --- | --- | --- | --- | --- |
| C-1 | Critical | `paper/abstract_and_intro.md:73-75` | 摘要"表征天花板"六个数（0.801 / 0.689 / 0.223 / 0.354 / 0.366 / 0.814）是 pre-gate 被取代值；同文件 `:25` 已写正确值（0.364 / 0.828），**摘要自相矛盾** | 改为 0.802 / 0.722 / 0.240 / 0.342 / 0.364 / 0.828 |
| I-2 | Important | `paper/methods_data_records.md`（Known gaps 末） | 手册附录 J 第 4 条明确要求披露「tier-4 未核验」，正文只有 Tier-0 与 Tier-1/Tier-2 | 补 Tier-3/Tier-4 未闭环披露，并指向 `reports/g1plus_tier34_access_findings.md` |
| m-2 | Minor（事实性） | `paper/technical_validation.md:35-37` | 称两篇 2013 论文「重述同两个数值」；实测 817 只含 PC 64.92（`89.78`=False），820 才含两者 | 改为「两篇合起来覆盖两个值（第一篇 PC，第二篇 PC 与 EC）」 |
| m-1 | Minor | `technical_validation.md:54`、`methods_data_records.md:109,289` | `confirmed to have no open full text` 是绝对化断言，超出可自证边界（索引状态会变） | 改为 `no open full text discoverable as of 2026-09-25` |
| m-3 | Minor | `paper/benchmark_and_figures.md`（Fig6 图注） | 把 42 行子集的比例（0.762 = 32/42）与 74 行全量的计数（18）并列，**分母不一致** | 两口径分别显式标注：74 行 → 56（0.757）覆盖、18 排除；42 行 → 32（0.762） |
| m-5 | Minor（图注口径） | Fig5 图注 | 未声明误差棒口径（攻击清单第 6 条要求） | 补 `Error bars are +/-1 SD across the five partitions` |

### C-1 复现证据

```
python -c "import json;d=json.load(open('probes/v032_ablation_summary.json'))['summary'];print({k:(round(v['r2']['mean'],4),round(v['spearman']['mean'],4)) for k,v in d.items()})"
```

实测 `probes/v032_ablation_summary.json` → `summary`：Morgan r2=0.2402 / spearman=0.7223；Physical r2=0.3422 / spearman=0.8021；Morgan+Physical r2=0.3636 / spearman=0.8282。摘要旧值出处为 `reports/v034_model_ready_gate.md` 的 before → after 左列，即 v0.3.4 已明示 superseded。

## 2. 复核后驳回

- **I-1（reviewer 主张「C2 排序头与 C4 delta 层负结果整体缺失」）→ 驳回。**
  reviewer 的复现命令 grep 的是**内部标签**（`C2|C4|pairwise|ranking head|delta layer`），命中 0 属预期；两条负结果的**内容与数字**均在文：
  - C2（排序头 / MLP）：`methods_data_records.md:159-164`（Physical MLP Spearman 0.884、R² −0.172、校准后 −0.309，明写 `true negative result`）；`abstract_and_intro.md:76`。
  - C4（Onsager delta 层被拒）：`methods_data_records.md:188-192`；`technical_validation.md:283-292`（缔合液 1.6-40 估计 vs 61-178 实测；离子液体 82-153 vs 12-30；覆盖 **0/150**）。
  手册附录 J 第 3 条要求「六条负结果一条不许删」，约束的是**内容保留**，不是内部标签入文。为凑标签而改会引入新风险，故不改文字。

## 3. 留档不处置

- **m-4**：`probes/dielectric_target_and_scaffold.py:772-774, 798-800` 仍有裸 `.relative_to(REPOSITORY_ROOT)`；reviewer 只读代码、**未运行**，属静态判断，且不影响论文引用的 `--plot-only` 路径（该路径已走 `_display_path`）。记录待后续清理。

## 4. 防回归守卫（C-1 的根因是校验盲区）

- `scripts/check_paper_artifact_consistency.py` 原有 `check_main_benchmark_table()` **只读 `benchmark_and_figures.md`**，摘要散文数字从不被检查，所以 pre-gate 值一路活到 M-1。
- 新增 `check_abstract_ceiling_numbers()`：用 6 条只匹配摘要那句的正则，把每个值绑到 `probes/v032_ablation_summary.json`；句子被改写则报错而非静默失效。已挂入 `verify_paper()`。
- 未采用全局 stale-phrase 方案：`0.223` 这类旧值在 v0.3.4 的 before → after 引用里是**合法**的，全局扫描会误伤。
- **守卫自检（证明它会咬）**：临时把摘要改回 `0.801`，`check_paper_artifact_consistency.py` 立即非零退出并输出 `abstract_and_intro.md: Physical spearman is 0.801, artifact says 0.802`；随后还原。同场景已固化为 `tests/test_paper_artifact_consistency.py::test_a_stale_abstract_ceiling_number_is_rejected`。

## 5. 闸门证据（修复后、新 SHA）

| 闸门 | 结果 |
| --- | --- |
| `scripts/build_paper_full_draft.py --check` | exit 0（1034 行） |
| `scripts/check_paper_artifact_consistency.py` | exit 0（含新守卫） |
| `scripts/verify_paper_figures.py` | exit 0（6 图齐全、逐图唯一产物） |
| `scripts/verify_dielectric_v03.py` | exit 0（7/7，246 行，sha256 `ff214293…`） |
| `scripts/verify_export_manifests.py` | exit 0（week1–week9 共 9/9 PASS） |
| `ruff check .` | exit 0 |
| `compileall` | exit 0 |
| `pytest -q -p no:cacheprovider` | 847 passed（224.3 s） |

reviewer 侧独立跑过的退出码（不依赖主线程）：`verify_paper_figures.py` 0、`verify_dielectric_v03.py` 0、`verify_dielectric_v032.py` 0、`verify_d1_leave_ec_out.py` 0、`build_paper_full_draft.py --check` 0。

## 6. 未修项与残余风险

- 论文正文**无** `tier-4` / `closed_source` 字面量；本轮补的是 Tier-3/Tier-4 披露（I-2）。`closed_source` 不引入，因为数据集 `redistribution_status` 实际取值只有 `""`(210) / `allowed`(32) / `public_domain`(4)，正文用 `non-redistributable` / `subscription-restricted` / `closed-access` 措辞已经准确。
- 相图/表格数字层面本轮**未发现**其他 Critical/Important：主基准表、G2 三模型、共形分层（逐位一致）、适用域、leave-EC-out、Fig1 行数口径均由 reviewer 独立复算通过。

## 7. 需用户决策（未授权不执行）

1. **v1.0 tag**：`git tag -l "v*"` 为空。前置条件（D1/D2 digest 重钉）已满足，但 **Zenodo 集成必须先于打 tag**，否则 archive 触发不到。
2. **Zenodo**：`paper/code_and_data.md:8` 仍是 `https://doi.org/10.5281/zenodo.[XXXXX]` 占位符，需用户账号启用集成后才有真 DOI。
3. **ILL**：Hagiyama 2008（DOI `10.1246/cl.2008.210`）馆际互借，是 FEC 107 腿唯一收口路径。
4. **DC-200 索取邮件**：模板见手册附录 L-1.6，会**以用户身份发出**，须先获授权。
