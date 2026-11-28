# PLAN B v7.2 — External Evidence Recovery, Source Independence & Screening Robustness

**版本**：v7.2（正式修订）  
**基线**：v7.1 / commit `2947938`  
**状态**：已完成（7 个阶段全部执行）

---

## 1. 本轮定位

v7.1 把研究推进到「内部证据 + 机制分解」，但留下三个硬约束：

1. 外部数据（LiquidBenchmark / ComBat）在仓库中找不到，来源独立性只能停在「本仓库有 41 个研究」；
2. ether 子族分类只有 3 类，环醚被塞进脂肪醚；
3. E6 只知道 regret 不稳，不知道**为什么**不稳。

v7.2 的任务是**把这三个约束逐一处理到可判定**：数据必须真的恢复，来源必须以原始研究和实验室为依据，E6 必须从「平均 regret」推进到「候选池组成效应 + 分子级推荐稳定性」。

---

## 2. 不变量

| 类别 | 冻结内容 |
|---|---|
| v7.0 的 17 个产物 | 哈希校验，不得修改 |
| v6.0 的 4 个历史文件 | 哈希校验，不得修改 |
| 分子身份、电荷、多重度 | 不变 |
| 目标定义 | 静态相对介电常数 ε_r |
| ACCEPT 标准 | 不因结果调整 |
| 评价规则 | Top-k=10、regret 定义、LOFO 定义不变 |
| 官方 `family` 列 | 不得覆盖（子族只进新列） |
| 原始外部数据 | 只读，不改写 |

---

## 3. 六个工作包

| 工作包 | 内容 | 优先级 | 状态 |
|---|---|---|---|
| B720 | LiquidBenchmark 恢复 | P0 | ✅ 246 行 / 45 化合物 |
| B721 | ComBat 恢复与审计 | P0 | ✅ 56 行，`De` 被拒绝 |
| B722 | 三层来源谱系 + 外部验证 | P0 | ✅ 41 研究 / 186 compendium-only |
| B723 | E6 候选池组成效应 | P1 | ✅ 池 sd 6.42 vs 训练 0.75 |
| B724 | Ether 子族外部证据 | P2 | ✅ 5 类，仍 n=2 |
| B725 | 论文结论与证据等级 | P1 | ✅ 27 条 claim |

---

## 4. 关键判定

### 4.1 ComBat 的 `De` 列被拒绝

**不是格式问题，是定义问题。** 用冻结 239 标签做探针：

| 分子 | ComBat `De` | 静态 ε | 相对差 |
|---|---|---|---|
| N-methylacetamide | 3.97 | 178.47 | 97.8% |
| Acetonitrile | 22.23 | 37.50 | 40.7% |
| 环己烷 | 2.02 | 2.02 | 0.0% |
| 乙酸甲酯 | 6.68 | 6.68 | 0.0% |

极性液体差 40–98%、非极性差 <2% —— 这是「混入高频/光学介电常数」的典型特征。**ComBat 不能用于静态介电常数研究。**

### 4.2 LiquidBenchmark 是重复测量，不是新证据

- 属性列名 `Relative permittivity at zero frequency` → 静态，无需假设
- 与 239 重叠 25 个化合物，82 对可比记录，**中位相对差 1.44%**
- 20 个新化合物**无逐行 DOI**，不能算独立原始研究

### 4.3 干净 Source OOD 不可行

判据：一个研究必须有 ≥3 个**只被它自己覆盖**的分子。

- 192 个分子只有 1 个来源
- 其中 186 个的唯一来源是汇编
- 唯一来源是单篇论文的只有 6 个分子，分散在 6 个研究里
- **满足条件的研究：0 个**

**因此所有 14 个「Source OOD」数字都是项目迁移压力测试，不是未见来源检验。**

### 4.4 E6 regret 波动归因

| 来源 | regret sd（μ²/Vm） |
|---|---|
| 训练集重采样 | 0.749 |
| **候选池子抽样（80%）** | **6.419** |
| 比值 | **8.57** |

**池组成主导。** 同时池规模改变 regret 水平：239 池 18.735 → 191 池 2.776。

### 4.5 推荐稳定性不足

| 指标 | μ²/Vm | r²SCAN-3c 电子 |
|---|---|---|
| 曾入选分子 | 19 / 239 | 20 / 239 |
| 频率 ≥0.9 | **11** | 10 |
| 两块共同稳定 | **4** | |

**11 个稳定分子中 7 个是 nitrile、2 个 nitro** —— 高度集中，且两块几乎不重叠。

---

## 5. 工程实现

```text
scripts/b720_external/     recover_liquidbenchmark.py, recover_combat.py,
                           audit_external_conditions.py, build_source_registry.py,
                           analyze_source_ood.py
scripts/b723_screening/    audit_e6_protocol.py, analyze_candidate_composition.py,
                           analyze_topk_stability.py
scripts/b724_ether/        classify_ether_subfamilies.py, analyze_ether_subfamilies.py
scripts/b725_final/        build_claim_ledger.py
tests/test_b720_external/  test_v72_contracts.py (36 条)
```

输出目录：`outputs/b720_external_data/`、`outputs/b722_source_independence/`、`outputs/b723_screening_robustness/`、`outputs/b724_ether/`、`outputs/b725_final/`。

外部原始数据：`data/external_raw/liquidbenchmark/`（GPL-2.0）、`data/external_raw/combat/`（MIT），均含 `PROVENANCE.json`（固定 commit + SHA256）。

---

## 6. 测试覆盖（36 条，全部通过）

| 类别 | 测试 |
|---|---|
| 原始数据哈希 | `test_liquidbenchmark_raw_hashes_match_provenance`、`test_combat_raw_hashes_match_provenance` |
| 许可证 | `test_raw_files_are_not_relicensed` |
| 定义拒绝 | `test_combat_definition_rejection_is_computed` |
| 模拟数据隔离 | `test_combat_rows_never_enter_a_modelling_pool` |
| 纯液体准入 | `test_no_mixture_entered_as_pure_liquid`、`test_liquidbenchmark_property_is_static_by_definition` |
| 汇编计一次 | `test_compendium_counted_once_not_per_molecule` |
| 五数分离 | `test_five_counts_are_distinct_quantities` |
| 无来源泄漏 | `test_no_source_is_in_both_training_and_test_by_construction` |
| E6 公式 | `test_e6_regret_formula_hand_computed`、`test_e6_regret_definition_matches_code` |
| 池抽样 | `test_pool_sampling_has_no_replacement`、`test_all_arms_share_the_same_pool` |
| 入选频率算术 | `test_top10_frequency_denominator_is_eligibility` |
| Ether 规则 | `test_ether_subtypes_reproducible_from_smiles`、`test_official_family_never_overwritten` |
| 冻结保护 | `test_v70_frozen_artifacts_unchanged`、`test_v60_artifacts_unchanged` |
| 证据等级 | `test_no_claim_promotes_a_not_testable_finding` |

---

## 7. 发现并修正的自身错误

| 错误 | 后果 | 修正 |
|---|---|---|
| LiquidBenchmark 混合物判定用逗号 | 45 行 IUPAC 名称（`acrylic acid, methyl ester`）被误判为混合物 | 改只认分号；`REJECT_NOT_PURE_LIQUID` 45→0 |
| E6 池效应归因在 frac=1.0 比较 sd | pool sd 恒为 0，比值无意义 | 改在 frac=0.8 比较；理由写入 JSON |
| `fam_of` 只按第一个特征块填充 | 第二个块 KeyError | 改为全表填充 |
| claim 的 NOT_TESTABLE 测试用词匹配 | 误拒合法表述 | 改为检查是否被标为 paper-ready |

全部记录在脚本注释与对应 JSON 中。

---

## 8. 交给下一轮的东西

**已关闭**：
- LiquidBenchmark / ComBat 的 `UNRESOLVED`
- E6 池效应定量归因
- Ether 子族 5 类分类
- 推荐稳定性的定量否定

**仍然阻塞**：
1. 干净 Source OOD（0 个可用研究）
2. 氯代醚 n=2（外部无新增）
3. 无「新分子 + 验证静态 ε」的外部数据

这三项都不是分析问题，是数据获取问题。
