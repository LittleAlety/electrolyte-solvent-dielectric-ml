# W20-5 高 ε 区拒答机制（§28.61）

**性质**：登记 + 规范 + 轻量实测。本件**不拟合任何模型、不产任何 R² / MAE、不占主记分牌、不动任何冻结件、不引用任何 Reaxys 数值**。

**产物**：`probes/w20_refusal.py`、`probes/w20_refusal_prereg.json`、`probes/w20_refusal_summary.json`、`tests/test_w20_refusal.py`、机器可读规则集 `probes/artifacts/w20_refusal_rule.json`、本报告。

---

## 1 一句话结论

- 把 ε>60 区的「不可解」从**硬预测**改成**正式拒答**：拒答是一条对 `(epsilon, donor_count, tpsa)` 的**纯函数**，被拒行**不给分**（`score_produced = false`），出口是 `refused_experimental_queue`。
- 冻结注册表实测被拒规模：带 ε 值的 **247** 行里 **187** 行被拒（**0.757085020242915**），其中高 ε 规则 **9** 行、分域规则 **183** 行、两规则同时命中 **5** 行；剩 **60** 行可排序。
- 与分域第二记分牌衔接（全域 `0.45401075998423623` / D1 域内 `0.524012313223719` / 域外 `0.3198024498133034`）；**在筛选语境里，域外拒答比域外错答值钱**——这是相对文献方法的一条可辩护优势。

## 2 为什么是拒答，不是硬预测

- `probes/dielectric_onsager_delta_summary.json` 实测：ε>60 区共 **5** 个化合物，Onsager 先验在该区覆盖率 **0/5**，在役 Δ-learning 臂在该区 MAE **75.95675695251926**（偏置同值）。
- 成因是**缺 Kirkwood g（取向相关）这一维**，不是模型容量 ⇒ 单分子描述符下**结构性地不可解**。
- 对筛选使命，诚实对象不是「一个数」而是「一个决定」：**拒绝排序 + 分流到测量**。错误答案静默进入短名单；拒答可见、可分流、可计数。

## 3 可执行规则（谁被拒、拒答后出口是什么）

| 规则 | `reason` | 谓词 | 判据出处 | 出口 |
| --- | --- | --- | --- | --- |
| 高 ε 区 | `high_permittivity_region` | `epsilon > 60.0` | `probes/w19_ranking_key.py::HIGH_PERMITTIVITY_EPS`（本件 import，不复制常量） | `refused_experimental_queue` |
| 分域外 | `outside_applicability_domain` | `not (NumHDonors >= 1 and TPSA >= 20.0)` | `probes/dielectric_applicability_domain_summary.json::domain_rules.D1.definition` | `refused_experimental_queue` |

- **谁被拒**：两谓词任一为真即拒（`refusal_decision` 返回 `refused = true` 与命中的 `refusal_reasons` 列表）。`epsilon` 缺失**不触发**高 ε 规则（缺席不是取值）。
- **出口**：被拒行**不产分数**（`score_produced = false`）、带 `domain_label` 与 `refusal_reasons`、`exit = refused_experimental_queue` ⇒ 进入**实验测量队列**，不进短名单、不进前沿。
- **无分数、非低分**：实现里被拒行根本不走打分分支；下游无法把拒答误读成「预测值很低」。

## 4 被拒规模（冻结注册表实测）

| 量 | 值 | 口径 |
| --- | ---: | --- |
| 注册表行数 | 31,949 | `data/processed/four_core_key_registry.csv` |
| SMILES 不可解析 | 2 | 不参与规则判定 |
| D1 域内 / 域外（全表） | 802 / 31,145 | `NumHDonors >= 1 and TPSA >= 20.0` |
| **带 ε 值行数** | **247** | `has_dielectric == true` |
| ├ D1 域内 / 域外 | 64 / 183 | —— |
| ├ 高 ε 规则拒（ε>60） | 9 | —— |
| ├ 分域规则拒 | 183 | —— |
| ├ 两规则同时命中 | 5 | —— |
| **被拒合计（并集）** | **187** | 9 + 183 − 5 |
| 可排序 | 60 | 247 − 187 |
| **ε 行拒答率** | **0.757085020242915** | 187 / 247 |

**分域第二记分牌口径（5 种子，97 化合物）**：D1 域内 57 个化合物（R² `0.524012313223719`）、域外 40 个化合物（R² `0.3198024498133034`）⇒ 域外 **40/97** 被拒，拒答率 **0.41237113402061853**。

## 5 价值判断（必须写进报告）

**在筛选语境里，域外拒答比域外错答值钱。** 域外端点 R² `0.3198024498133034` 意味着一个「域外答案」有相当概率把错序写进短名单，而短名单之后的每一步（合成、测量）都要花真金白银；拒答把不确定显式隔离成「待测」，成本从「错误决策」降级为「一次测量」。这是相对「无论如何都出一个数」的文献方法的一条**可辩护优势**，且它与本仓既有纪律一致：**域内/域外并列、域外声明在先**。

## 6 边界与纪律

- 本件**不替换**全域记分牌：全域 `0.45401075998423623` 照报，分域数只是**并列的第二块**。
- 拒答阈值**只有一个所有者**：`HIGH_PERMITTIVITY_EPS = 60.0` 由 `probes/w19_ranking_key.py` 持有，本件 `import` 而非复制；`high_permittivity_excluded` 同源。
- 本件**不产读数**：`produces_reading = false`、`promoted = false`、`scoreboard_attempts_delta = 0`、`shot_number_taken = null`。
- 注册表统计**全部由冻结件重算**（`tests/test_w20_refusal.py` 逐数字钉死），不手工抄写。

## 7 不可核 / 照实登记

- **`InChIKey` 未用于规则判定**：D1 与高 ε 规则都在**结构/取值**上判定；2 行 SMILES 不可解析者既不进域内也不进域外（不计入 802/31,145），照实登记为缺口。
- **`0.757085020242915` 是 registry ε 行口径**，与分域记分牌 `40/97` 化合物口径**不是同一个分母**，不得混说。
- **域外 R² 优于全域的因果未核**：域外端点低（`0.3198`）但其 MAE 反而更小（`5.925326555541991` vs 全域 `7.656617449123975`）——本件只登记事实，不对「为何」作因果声明。

## 8 数字出处

- `60.0` / `high_permittivity_excluded` ⇒ `probes/w19_ranking_key.py::HIGH_PERMITTIVITY_EPS`
- `0.45401075998423623` / `0.524012313223719` / `0.3198024498133034` / `57.0` / `40.0` / `97.0` / `457.0` / `7.656617449123975` / `5.925326555541991` ⇒ `probes/dielectric_applicability_domain_summary.json#endpoint`
- `5` / `0/5` / `75.95675695251926` ⇒ `probes/dielectric_onsager_delta_summary.json`；亦可 `reports/decisions_log.md` §28.43
- 被拒规模全部计数 ⇒ 本件 `probes/w20_refusal_summary.json::registry_scale`（对 `data/processed/four_core_key_registry.csv`，sha256 `e42885eb43779b7a4d472da88fefe018fe94150ff5b6fba86b3ed9bc83dc8bee`，重算）
