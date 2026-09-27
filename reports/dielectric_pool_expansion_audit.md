<!-- 入库说明（本轮追加，审计原文一字未改，自下一行起） -->

> **处置指引**：本报告由只读子智能体（Poincare）于 2026-09-27 产出，原文见下（未改一字）。
> 其提出的八条发现按 `reports/decisions_log.md` **§28.30（B1 / M1 / M4）**、**§28.31（M5）**、
> **§28.32（M2 判误报 / M3 登记为口径出入 / B1 残留照实登记）** 逐条处置或结案。
> 报告里引用的 `generated_at_utc = 07:02:15Z` 与 `started_at_utc` 两处，是**处置前**的旧版产物读数；
> 修脚本缺陷并重跑后 shipped 值为 `07:24:39Z` / `07:11:32Z`（见 §28.30 第 1 条）。

---
# W17-AUDIT 对抗审计报告：介电常数（ε）扩池两枪（shot 12 / shot 13）

审计对象：`probes/dielectric_pool_expansion_*`（预注册、脚本、摘要、产物）与
`reports/dielectric_pool_expansion*.md`。审计方式：只读产物 + 小规模复算
（`.venv\Scripts\python.exe`，UTC+8 时区）。结论均附代码行号或文件路径证据。

**时区约定**：仓库所在机器本地时区为 UTC+8。下文凡由文件 mtime 推得的 UTC 时间，
均已用 `summary.json` 内 `generated_at_utc=2026-09-27T06:28:26Z` 与其 mtime
`14:28:26` 对齐（偏移恰为 +8h）验证。

---

## §1 逐条回答八问

### Q1 折泄漏：`masked_splits` / `build_splits` 是否保证同一化合物的其他温度行不进测它的那一折

**判定：确认（折不泄漏）。**

证据链（三条）：

1. **折只按「计分化合物」发牌。** `probes/dielectric_room_window_paired.py:268-271`
   在每次 repeat 里调用 `fold_of_by_repeat(group_array[score], ...)`——注意传进去的
   是 `group_array[score]`，即**只对 score_mask 命中的化合物的键**排序去重后 round-robin
   发牌（`fold_of_by_repeat` 定义见同文件 `225-235`）。
2. **同化合物的所有行共享同一个折号。** `dielectric_room_window_paired.py:273`
   `row_fold = [fold_of.get(str(key), -1) for key in group_array]`——对每一行按它的
   化合物键查折号；因此化合物 X 的**全部行**（无论计分与否、无论温度）拿到同一个折号；
   未出现在 score_mask 里的化合物得到 `-1`。
3. **训练侧的准入条件排除同折化合物。** `dielectric_room_window_paired.py:275-276`
   ```python
   test_index  = np.flatnonzero(score & (row_fold == fold))
   train_index = np.flatnonzero(train & (row_fold != fold))
   ```
   测试行 = 该折的计分行；训练行 = 折号 ≠ 本折的行。于是「测化合物 X 的那一折」里，
   **X 的任何一行（含其其他温度行、含其扩池行）都因 `row_fold == fold` 被排除出训练侧**。
   `-1`（纯训练化合物）永远 ≠ fold，故它们每折都在训练集里——这是设计意图（纯训练料），
   不是泄漏。

**独立实证**：用最小合成例（A/B/C 各 2 行计分，D/E 各 2 行纯训练，3 折 ×2 repeat）直接
调用 `masked_splits`，逐折断言「测试化合物无一出现在训练侧」，结果 `straddling folds = 0`，
例：fold0 测 C（行 4,5），训练侧为行 0-3,6-9，C 的行 4,5 不在其中。

**运行时自检**：`probes/dielectric_coordination_block.py:917-919`
`np.intersect1d(group_array[train], group_array[test])` 统计 train∩test 的化合物数，
汇总在 `985-989`；两枪摘要里全部臂的
`folds_with_a_straddling_compound = 0`（`dielectric_pool_expansion_summary.json`、
`dielectric_pool_expansion_full_table_summary.json` 各臂 `leak` 字段）。

**另有一层共享折证明**：`dielectric_pool_expansion_benchmark.py:608-613` 与
`dielectric_pool_expansion_full_table.py:343-360` 会逐臂比对
`fold_signature(splits) == fold_signature(frozen_splits)`，不一致即 `refusing to continue`。
即扩池后折分配与冻结基线逐位相同（`fold_signature` 定义见 benchmark `241-247`）。

> 结论：**同一计分化合物的其他温度行不会进入测它的那一折**；并且这一性质有合成例、
> 运行时自检、共享折比对三重证据。无泄漏。

### Q2 预注册是否被事后改判：prereg 与脚本写死常量逐一对齐

**判定：常量全部对齐（数值确认）；但 prereg_v2 的 `locked_at_utc` 被错标（见 §2 B1），
且 shot 12 的「主臂名」与 prereg 列表存在口径出入（见 §2 M3）。**

| 量 | prereg | 脚本常量 | 对齐 |
|---|---|---|---|
| baseline R² | `prereg.json` `frozen_quantities_never_moved.baseline_r2 = 0.4091179943351143`；`prereg_v2` 同名同值 | benchmark `:78` `BASELINE_R2_REFERENCE = 0.4091179943351143`；full_table `:55` 同值 | ✅ |
| 目标 0.60 | `prereg.json` `target_r2 = 0.6` / `primary_criterion … exceeds 0.60`；`prereg_v2` `target_r2 = 0.6` | benchmark `:82` `PRIMARY_TARGET_R2 = 0.60`；full_table `:58` 同值 | ✅ |
| co-primary 臂名 | `prereg_v2` `primary_criterion.rule` 点名 `full_table_hybrid` 与 `full_table_lever4_lever8` | full_table `:63-65` `ARM_FULL_HYBRID="full_table_hybrid"`、`ARM_FULL_L4L8="full_table_lever4_lever8"`；判决 `:106-109`；`verdict.co_primary_arms` `:167-171` | ✅ |
| 安慰剂容差 | `prereg.json` arm_a `delta_r2 must stay <= +0.02`；`prereg_v2` arm_a 同 | benchmark `:85` `PLACEBO_TOLERANCE = 0.0200`（判 `:339`）；full_table `:59` 同（判 `:111`） | ✅ |

不涉及判据被「事后改动」的迹象：`reproduction_gap <= 1e-9` 的复现门槛
（benchmark `:79`/`:335`、full_table `:57`/`:105`）与 `primary_met = plus_r2 > 0.60`
（benchmark `:337`）均为严格大于/小于，未见阈值松动。

**唯一真正的「改判」风险不在常量，而在时间戳**：`prereg_v2.json` 声明
`locked_at_utc = 2026-09-27T07:05:00Z`，但它管辖的 `dielectric_pool_expansion_full_table_summary.json`
`generated_at_utc = 2026-09-27T07:02:15Z`（并随之被报告 `reports/dielectric_pool_expansion_full_table.md`
引用），即**声明锁时间晚于被它锁定的产出时间**。详见 §2。

### Q3 主臂 vs 非主臂：哪些数字可以提升、哪些不可以

**判定：确认（题述事实成立；两枪均无任何可提升的新数字）。**

**Shot 12**：
- 预注册主臂 = `plus_expansion_hybrid`（`prereg.json` `training_pool_rule` 的语义臂 +
  benchmark `:92` `ARM_PLUS_EXPANSION`），读数 **0.3809089252433510**，未过 0.60，
  `verdict.decision = primary_missed`。
- 臂内最高 = `plus_lever4_lever8` **0.4766400383507876**——但该数**早已是 §28.28 提升的
  v2 头条**（`reports/decisions_log.md:4987,4995,5007`，且等于 prereg_v2 的
  `promoted_headline_reference_r2`），不是本轮新数字。
- **全表最高读数 = 0.495943916130879（剂量 25%）**，来自 `dose_response[0]`
  （`dielectric_pool_expansion_summary.json` `dose_response`；报告
  `reports/dielectric_pool_expansion.md` 第 4 节）。它不是预注册臂，且 Arm B（剂量单调）
  **FAIL**（`verdict.arm_b_pass = false`）。
  → **0.4959 绝不可提升**：它是「数据量效应」的剂量切片，且只在 25% 剂量出现、非单调。

**Shot 13**：
- 两个 co-primary：`full_table_hybrid = 0.530028742596643`、
  `full_table_lever4_lever8 = 0.4914701852431905`（`…full_table_summary.json`
  `verdict.co_primary_values`）。二者均未过 0.60 → `co_primaries_missed`。
- **全表最高读数 = 0.5433111678100043（`full_table_lever4`）**，确认**不在 co-primary 名单**内
  （名单只含 `full_table_hybrid` 与 `full_table_lever4_lever8`）。它虽在 `prereg_v2.arms`
  清单里被列为一条臂，但主判据未点名它，故**不可按 co-primary 提升**。

> **允许/不允许**：两枪 primary/co-primary 均未达标，**没有任何扩池数字允许被提升为头条**；
> 冻结头条仍为 **0.4766400383507876**（`prereg_v2` `frozen_quantities_never_moved.promoted_headline_reference_r2`、
> `honest_boundaries` 末条、§28.28）。0.4959、0.5300、0.5433 三者**只许带池定义作探索读数引用**。

### Q4 诊断探针的非盲问题：disclosure 是否诚实、0.530029 还算不算预注册读数

**判定：disclosure 文本诚实（确认），但「可提升」的措辞夸大（夸大）；0.530029 应降级为
「事后选臂 + 预先写定的判决规则」，不得称为盲法预注册确认。**

事实：
- 诊断脚本自我声明 `status = exploratory_not_promotable`
  （`probes/dielectric_pool_expansion_diagnostic.py:1-15`、payload `:187`；
  `dielectric_pool_expansion_diagnostic.json` `status` 字段）。
- 诊断确在 prereg_v2 之前看到该臂：`diagnostic.json` mtime `14:39:01`(local)=`06:39:01Z`，
  `prereg_v2.json` mtime `14:39:37`(local)=`06:39:37Z`——**诊断早 36 秒**。
- 诊断的 `full_table` 臂（`diagnostic.py:127-130` 用 `np.ones(len(base_rows))` 训练）
  数值 **0.530028742596643**，与 shot 13 的 co-primary `full_table_hybrid`
  **逐位相同**（`dielectric_pool_expansion_diagnostic.json` `results[5]` vs
  `…full_table_summary.json` `arms.full_table_hybrid.r2`）。即：**co-primary 臂在预注册前
  就已被测出并公布**。

disclosure 是否诚实：**是**。`prereg_v2.json` 的 `disclosure`（并原样抄入摘要
`prereg.disclosure`）明确写了「this shot is NOT blind to the headline」「What is locked here is
the decision rule, the arm list, the governance arms and the reporting duty, **not the
discovery**」。它没有隐瞒非盲。

是否足以支持「0.530029 仍算预注册读数」：**不足以直接支持，应降级**。理由：
1. 预注册的核心价值是「假设/臂在见数之前冻结」。此处**臂是在见数之后才进入 co-primary 名单的**——
   `full_table_hybrid` 之所以被选中，正是因为诊断已显示它最高之一。
2. 「同一臂在预注册脚本里重测一遍」只能证明**可复现**，不能把「事后选臂」洗成盲法确认。
   disclosure 末句「The same arm is re-measured inside this pre-registered script and only that
   number may be promoted」把「重测」等同于「可提升」，属于**措辞夸大**。
3. 缓解：本枪结论是 `co_primaries_missed`，**实际没有任何数字被提升**，故夸大未被兑现为
   夸大交付；但若将来有人引用 0.5300 为「预注册确认」，即构成误标。

建议降级口径：把 0.530028 记为「**post-hoc 选定的臂 + 预先写定的判决规则下重测**」，
保留 `exploratory` 标签；删/软化疗 `only that number may be promoted`。

### Q5 数字可复现性：从 `_folds.csv` / `_repeats.csv` 重新聚合

**判定：确认（summary 每个臂读数均可逐位复现；`baseline_abs_gap` 确为 0）。**

脚本口径（据代码）：summary 的 `r2` 取自 `arm_r2(summary)`，而 `arm_r2` 返回的是
**各 repeat 的 R² 的均值**（`dielectric_pool_expansion_benchmark.py:312-314`；
repeat 内部把该 repeat 全部折的预测池化后算一次，见
`dielectric_coordination_block.py:955-968`）。

复算（对 `_repeats.csv` 的 `Morgan+Physical` 按 repeat 取均值）：

| 臂 | 复算值 | summary 值 | 差异 |
|---|---|---|---|
| baseline_hybrid (shot12/13) | 0.4091179943351143 | 0.4091179943351143 | 0 |
| plus_expansion_hybrid | 0.3809089252433510 | 0.38090892524335096 | <1e-17 |
| expansion_only | 0.1250465112927389 | 0.12504651129273886 | <1e-17 |
| plus_lever4_lever8 | 0.4766400383507875 | 0.4766400383507876 | <1e-16 |
| plus_lever4_lever8_plus_expansion | 0.4353185412382898 | 0.4353185412382897 | <1e-16 |
| expansion_label_placebo | 0.2196470593710983 | 0.21964705937109832 | <1e-17 |
| full_table_hybrid | 0.5300287425966431 | 0.530028742596643 | <1e-16 |
| full_table_lever4 | 0.5433111678100043 | 0.5433111678100043 | 0 |
| full_table_lever4_lever8 | 0.4914701852431905 | 0.49147018524319047 | <1e-16 |
| full_table_plus_nbs_hybrid | 0.4544394689931626 | 0.4544394689931626 | 0 |
| full_table_plus_nbs_lever4 | 0.5234221271950796 | 0.5234221271950796 | 0 |
| full_table_label_placebo | 0.0553962190214187 | 0.05539621902141869 | <1e-17 |

各 representation（Morgan / Physical）同样逐位复现。

`baseline_abs_gap`：summary 由 `reproduction_gap = abs(baseline_r2 - 0.4091179943351143)`
实算（benchmark `:334-335,393`；full_table `:104-105,164`），且复算的 baseline
`Morgan+Physical` repeat 均值恰为 `0.4091179943351143`，故 **gap = 0.0 为真**（非写死）。

旁证：`data/processed/dielectric_pool_expansion_observations.csv` 与
`_features.csv` 的 sha256 与 summary 记录一致（`…observations_sha256`/`…features_sha256`
实测 MATCH）。

### Q6 脚本缺陷：`arms[name]['r2']` 是否修好、有无同类隐患

**判定：确认（已修好，实测无 KeyError）；但存在两处非 KeyError 的同类隐患。**

已修证据：full_table 的汇总改由 `bn.arm_r2(arms[name]["summary"])` 取数
（`dielectric_pool_expansion_full_table.py:99-103`，并写入 `arms[name]["r2"]` `:149-150`），
末尾打印 `:477`、`format_report` `:240-242` 都改走 `summary["arms"][name]["r2"]`。
**实测**：把现有两份 summary JSON 喂给各自 `format_report`，
`benchmark.format_report` 与 `full_table.format_report` 均正常返回（67/66 行），无 KeyError。
benchmark 侧历史路径同样使用 `arms[name]["r2"]`
（`dielectric_pool_expansion_benchmark.py:485-489`）——从 summary 读，键存在。

同类隐患（非 KeyError，但属「错标/口径」）：
- **H1（需修正）**：`dielectric_pool_expansion_full_table.py:435` 的 `telemetry["started_at_utc"]`
  用的是 `_utc_now()` 在**跑完之后**取样，故它与 `finished_at_utc`（`:436`）恒等
  （摘要里两者都是 `07:02:15Z`，而 `wall_seconds = 778.7`）。started 时间被错标为结束时间。
  （对照：benchmark `:547` 在开头取样，是正确的。）
- **H2（提示）**：两枪脚本均**无对应测试**（`tests/` 下无 `*pool_expansion*`），
  修好的取数路径没有回归护栏，未来改动可能复发同类错误。

### Q7 口径混用风险：本轮全部 R² 及池定义

**判定：确认（存在高危可混用项）。**

本轮出现的 R² 及其池定义：

| # | 数字 | 池/口径定义 | 出处 |
|---|---|---|---|
| 1 | 0.4091179943351143 | 457 行/97 化合物（实为 276 个 (化合物,T) 对）；GroupKFold by InChIKey，10×5，seed 42；hybrid Morgan+Physical；**repeat 均值** | 冻结基线，全场并列 |
| 2 | 0.4766400383507876 | 同 1 的池与折；+lever4/+lever8 特征 | v2 提升头条；§28.28；= shot12 `plus_lever4_lever8` |
| 3 | 0.3809089252433510 | 同 1 的池与折；训练池加 NBS 块 | shot12 `plus_expansion_hybrid` |
| 4 | 0.12504651129273886 | 同 1 的池与折；训练池=仅 NBS | shot12 `expansion_only` |
| 5 | 0.21964705937109832 | 同 1 的池与折；扩池标签跨化合物置换 | shot12 `expansion_label_placebo` |
| 6 | 0.4959 / 0.4021 / 0.4059 | 同 1 的池与折；NBS 训练量 25/50/75%（单次随机子集） | shot12 `dose_response` |
| 7 | 0.530028742596643 | 同 1 的池与折；训练池=全部 2029 行基表 | shot13 co-primary `full_table_hybrid`；**= 诊断 `full_table`** |
| 8 | 0.5433111678100043 | 同 1 的池与折；+lever4 | shot13 `full_table_lever4`（**非 co-primary**） |
| 9 | 0.49147018524319047 | 同 1 的池与折；+lever4/+lever8 | shot13 co-primary `full_table_lever4_lever8` |
| 10 | 0.5234221271950796 | 全表+NBS；+lever4 | shot13 `full_table_plus_nbs_lever4` |
| 11 | 0.05539621902141869 | 全表；标签置换 | shot13 placebo |
| 12 | 0.3674 / 0.3585 / 0.4665 | 全表 25/50/75%（单次随机子集） | shot13 `dose_response` |
| 13 | 0.06487386371009436 / 0.2531659995294713 | 同 1 池但**单 representation**（Morgan / Physical） | 各臂 `representations` |
| 14 | 0.6080587938801277 | 同 1 池但 **Physical 单表示**（非 hybrid） | shot13 `full_table_lever4.representations.Physical` |
| (参照) | 0.364 / 0.7385332681453336 / 0.5332 / 0.5454 | **不同池**：v1.0 headline(236 池) / random_row 泄漏参照 / 其它池 | `reports/decisions_log.md`、快照 |

**绝不可相减或混比者**（按危险度）：
1. ⚠️ **同一臂的「repeat 均值」 vs 「fold 均值」**。summary 用 repeat 均值（#1）；
   若有人对 `_folds.csv` 直接取均值会得到 0.3447657542377554（baseline hybrid）、
   0.5139642017592796（full_table_hybrid）、0.5251336311010050（full_table_lever4）等
   **另一套数**。两者相差 0.01~0.06，但语义不同，**一律不得相减**。
2. **跨池数字**（#1-#12 的 457 池 vs 参照行的其它池）**永不混比/相除**；
   prereg 与 §28.28 都明文禁止（`prereg.json` `honest_boundaries`；
   `decisions_log.md:5010`）。
3. **representation 混用**：#13/#14 是单表示读数（如 Physical 0.6081），
   与 hybrid（Morgan+Physical）**不是同一口径**；尤其 `full_table_lever4` 的
   `Physical=0.608` > 0.60 **绝不能**当作「主判据达标」——主判据只认 Morgan+Physical
   的 0.5433。
4. **剂量切片**（#6/#12）是单次随机子集、非子集平均（`prereg_v2` `honest_boundaries`
   第 3 条），彼此之间与全量读数不得当作精度比较。
5. **暴露的池定义缺失**：#6/#12 若离开「NBS/全表 + 457 计分池」的上下文，
   数字不可解释。

### Q8 特征覆盖缺口：`full_table_lever4` 高于 `full_table_lever4_lever8` 是否因配位块覆盖稀疏

**判定：现象确认；归因部分确认（方向成立，但「97 行」低估了稀疏度，且因果未被受控实验证明）。**

现象（数值确认）：
- `full_table_lever4` `Morgan+Physical` = **0.5433111678100043**
- `full_table_lever4_lever8` `Morgan+Physical` = **0.4914701852431905**
- 差值 **0.05184098256681383**（lever4 比 lever4+lever8 高 ~0.052）。

覆盖（对 `probes/artifacts/dielectric_coordination_block_features.csv` 实测）：
- 该 CSV 共 **97 行 / 97 化合物**，但 `status == "ok"` 的只有 **88 个**；
  有 **9 个 `status = "undefined_no_hetero_site"`**。
- 计分侧 `coordination_matrix` 要求 `status=="ok"` 且各列非空，否则整块置 NaN
  （`probes/dielectric_coordination_block.py:1077-1092`）。
- 扩池训练全域（v11plus ∪ NBS）共 496 个化合物，其中只有 **88 个**有可用配位块
  → 化合物覆盖率 ≈ **17.7%**；按行覆盖，`…full_table_summary.json` telemetry 记
  `coordination_rows_with_the_block = 996 / 2391 ≈ 41.6%`。
- 且在 NBS 块中只有 23 个化合物有配位块。

即：**「稀疏」是真的，而且比题述（97 行）更稀疏**（有效仅 88 化合物、~18% 化合物覆盖）。
把一块 ~18% 覆盖、含大量 NaN 的 5 列特征叠到已含 lever4 的模型上，使分组 R² 下降 0.052
**与稀疏假设一致**；但两枪都**没有**做「覆盖补全 / 对照臂」实验，
因此严格说这是**相关而非已证因果**——应写成「与配位块覆盖稀疏相符」，不得写成已证机制。

---

## §2 按严重度排序的问题清单

### 阻断级（写入交付包/提交前必须处理）

**B1. prereg_v2 的 `locked_at_utc` 被错标，字面上「写在跑完之后」。**
- `probes/dielectric_pool_expansion_prereg_v2.json` 声明
  `locked_at_utc = 2026-09-27T07:05:00Z`，`status = locked_before_run`；
  该值被原样抄进 `probes/dielectric_pool_expansion_full_table_summary.json`
  （`prereg.locked_at_utc`）与报告 `reports/dielectric_pool_expansion_full_table.md` 头部。
- 但**它管辖的产出** `…full_table_summary.json` 的 `generated_at_utc = 2026-09-27T07:02:15Z`
  ——**早于声明的锁时间 3 分钟**。
- 文件系统 mtime（换算 UTC）：`prereg_v2.json = 06:39:37Z`，
  `full_table_summary.json = 07:02:15Z`，`diagnostic.json = 06:39:01Z`。
  即真实写入顺序是「诊断(06:39:01) → prereg_v2(06:39:37) → 跑(≈06:49 起，wall≈779s) →
  摘要(07:02:15)」，**prereg_v2 实际早于跑**；但**声明的 07:05Z 反而晚于摘要**。
- 危害：git 不保存 mtime，交付克隆里**唯一可见的时间就是声明值**，读者据此会得出
  「预注册写在产出之后」的相反结论。属**错标**，必须改成真实落盘时间或删去该字段。
- 同类：`probes/dielectric_pool_expansion_prereg.json` 声明
  `locked_at_utc = 2026-09-27T02:20:00Z`，但其 mtime = `06:06:49Z`——
  凭空早了 3h46m（方向不致命，但同属手工时间戳不可信）。

### 需修正

**M1. Q4 的「可提升」措辞夸大。** `prereg_v2.disclosure` 末句
「only that number may be promoted」把「事后选臂后的重测」表述为可提升读数。
应降级为「post-hoc 选定臂 + 预先写定的判决规则下重测」，并删除/软化该句（详见 §1 Q4）。

**M2. 两 prereg 的 `author_instruction` 中文串乱码。**
`dielectric_pool_expansion_prereg.json` 与 `prereg_v2.json` 的 `author_instruction`
为 `缁х画鍔犳暟鎹?..`（GBK/UTF-8 误码），交付前应改为正确中文或删。

**M3. shot 12 主臂名与 prereg 清单口径出入。**
`prereg.json` 的 `linearm_upgrade_targets.arms` 只列
`[baseline_hybrid, plus_lever4_lever8, plus_lever4_lever8_plus_expansion, expansion_only]`，
**不含** `plus_expansion_hybrid`；而 benchmark 把 `plus_expansion_hybrid` 作为主臂
（`:92,:395-396`）。尽管「base+扩池」的语义臂可从 `training_pool_rule` 推出，
但字面臂名不一致，交付时应补一句说明或把该臂写进 prereg。

**M4. full_table telemetry 的 `started_at_utc` 被错标为结束时间。**
`probes/dielectric_pool_expansion_full_table.py:435` 在结尾用 `_utc_now()` 取 started，
致 `started_at_utc == finished_at_utc == 07:02:15Z`（而 `wall_seconds=778.7`）。
应像 benchmark `:547` 那样在开头取样。（此缺陷也间接支撑了 B1 的时间线混乱。）

**M5. Q8 归因表述应降级。** 把 lever4>lever4+lever8 归因于配位块覆盖稀疏，
目前是**相关**；且真实覆盖是 88 化合物 / ~18%（不是「97 行」的字面印象）。
应写成「与覆盖稀疏相符」，并补 `88 ok / 996 of 2391 rows` 的量化。

### 提示（不影响判定，但建议随交付注明）

**T1. 聚合口径须显式声明。** summary 的 R² 是「repeat 均值」；
`_folds.csv` 直接取均值会得到另一套数（baseline 0.3448 vs 0.4091 等）。
建议在报告/交付包注明「本表 R² 为 repeat 均值」，避免复算者误以为数不对或混比（见 Q7-1）。

**T2. 频率缺失被默认当静态。** `load_expansion` 只在 `frequency_mhz` 非空时校验
（`benchmark.py:163-169`），空串直接通过；prereg 要求「≤1.0MHz 或显式标 static/zero-frequency」。
本次 392 行 `frequency_mhz` 多数为空，建议在交付注明「空=视作静态」的口径。

**T3. 无回归测试。** `tests/` 无 `*pool_expansion*`，Q6 的修复路径无护栏。

**T4. 样本量口径。** 457 行中不同 (化合物,T) 对实测为 276（对 v11plus 施加
`thermoml_zero_frequency & room_temperature` 裸筛得 460 行/100 化合物/279 对，
过 xTB/SMILES 冻结门后收敛到 457/97/276，与摘要一致）。交付时继续写「276 对」而非 457。

---

## §3 可写进交付包的诚实陈述

> 我们按预注册（`probes/dielectric_pool_expansion_prereg.json` 与
> `…_prereg_v2.json`）只加宽**训练池**、冻结 457 行 / 97 化合物（实为 276 个
> (化合物, T) 对）的计分池与 10×5 GroupKFold（by InChIKey, seed 42）折分配。
> 折的分离是**结构性的**：折只在计分化合物上发牌，同一化合物的所有行（含其其他温度行）
> 与本折同号而永不进入该折的训练侧，运行时自检 `folds_with_a_straddling_compound = 0`，
> 基线在脚本内逐位复现 `0.4091179943351143`（`abs_gap = 0.0`）。**两枪均未达标**：
> shot 12 主臂 `plus_expansion_hybrid` = **0.3809089252433510**（Δ −0.028209，Arm A 过、
> Arm B 失败）；shot 13 两条 co-primary `full_table_hybrid` = **0.530028742596643** 与
> `full_table_lever4_lever8` = **0.4914701852431905**，均未过 0.60
> （`co_primaries_missed`）。过程中的最高读数（shot 12 的 0.4959 来自 25% 剂量、
> shot 13 的 0.5433 来自**非 co-primary** 的 `full_table_lever4`）**只是数据量/配置读数，
> 一律不提升**。需要如实披露：shot 13 的两条 co-primary 之一是**非盲**的——
> 一个明确标注 `exploratory_not_promotable` 的诊断探针在本预注册落盘前 36 秒已测出
> `full_table = 0.530028742596643`（与 co-primary 逐位相同），故该项只能读作
> 「事后选定臂、在预先写定的判决规则下重测」，**不是盲法预注册确认**；本枪结论为未达标，
> 未产生任何提升。冻结头条仍为 **0.4766400383507876**，与上述任何扩池数字不得相减或混比。

---

## 附录：审计使用的关键文件与命令（只读/复算）

- 预注册/摘要：`probes/dielectric_pool_expansion_prereg{,_v2}.json`、
  `probes/dielectric_pool_expansion_{summary,full_table_summary,diagnostic,build_summary}.json`
- 脚本：`probes/dielectric_pool_expansion_{benchmark,full_table,diagnostic}.py`、
  `probes/dielectric_room_window_paired.py`、`probes/dielectric_coordination_block.py`
- 产物：`probes/artifacts/dielectric_pool_expansion{,_full_table}_{folds,repeats}.csv`、
  `probes/artifacts/dielectric_coordination_block_features.csv`
- 报告/对照：`reports/dielectric_pool_expansion{,_full_table}.md`、
  `reports/decisions_log.md`（§28.28）、`probes/four_channel_coverage.py`
- 复算：对 `_repeats.csv` 分 arm/representation 取 repeat 均值；对 mtime 按 UTC+8 换算；
  合成例验证 `masked_splits`；`format_report` 吃现有 summary 无异常；两处 sha256 MATCH。

*本报告只写入 `data/raw/audit_w17g/`，未修改任何被跟踪文件，未执行任何 git 命令。*
