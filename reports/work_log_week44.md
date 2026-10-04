# 工作日志 · Week 44（层准入闸门、逐轮验收运行器、strict same-level 机器要求与 AST 静态守卫）

> 承接 `reports/work_log_week43.md`。本轮起点：W43 交付（HEAD `04b27e3`，工作树 124 项）。本轮 0 shot，累计仍 19。

## Week 44：把两条治理欠账接进机器

**目标**：W43 登记 item 38（层当排序先验要先过准入表）与 item 39（治理台账守卫纳入每轮验收）。本轮用四条只读治理 / 静态审计 lane 一次执行，并补两条新登记。

**交付**

- **预注册**：`probes/w44_governance_wiring_prereg.json`（`locked_before_run`，r1）。四条 lane 的判据阈值、闸门拒绝集合、静态守卫扫描口径与 AST 规则跑前写死。
- **W44-A 层准入闸门 + 全仓消费者审计**（8/8 成立）：`admit_prior(layer, use)` 只在 `verdict == admit` 时返回，否则抛 `PriorRefused`；扫 611 个 `*.py` / `*.md` 得 18 个（文件 × 层）对，运营性先验使用 1（正对照 pubchemqc，已过闸）、未申报 0；负对照 ccsd_t / qm9 / batt 全被拒，正对照 PubChemQC 过闸。
- **W44-B 逐轮验收运行器**（7/7 成立）：复用 W43-D 四个不变式，扫 41 轮交付摘要、33 轮声明验收字段、判 fail 0 轮；最近五轮 week40–week44 全过；台账不变式全成立。
- **W44-C strict same_level 机器要求 + 候选审计**（8/8 成立）：四属性全同 + 独立来源；六个在仓候选与 Batt 距离 0 的 0 个；最近一对 QM9–PubChemQC 距离 2；near 合法对恰为 qm9-pubchemqc 与 xtb-expanded；越权 0。
- **W44-D AST 静态 shot / 冻结读数守卫**（8/8 成立）：解析 359 个 `*.py` / 1,302,367 节点、解析错误 0；冻结注册表 2 处全等于冻结 7 项；冻结读数写入 0 / 引用 267；`promoted = True` 未登记 0；3 个 legacy 局部同名量登记为例外。
- **测试与集成**：`tests/test_w44_*.py`（31 项）全绿；论文 v3 → v1.8 §3.29；README §0/§5/§7/§8/§11；`reports/decisions_log.md` §28.99。

**坑与更正**

- 老探针 `probes/v032_controlled_comparison.py` 带 BOM，`ast.parse` 读 `utf-8` 会报 `U+FEFF` 语法错误；扫描必须用 `utf-8-sig` 读入再解析。
- 最近一对在 QM9–PubChemQC 与 xTB–扩展层之间**并列距离 2**，预注册写死 tie-break（按属性表顺序命名后取字典序最小）才稳定落到 `qm9-pubchemqc`；否则 `expanded-xtb` 会先被选中。
- 三条老探针里有私有 `METRIC_NAMES`（4 项，局部列名表），它们**不是**冻结注册表；静态守卫把冻结注册表限定在两个定义文件，其余记为 `legacy_local`，不虚报 mutation。
- 探针文件里的报告文本含反引号时，Codex 的 JS 模板写入会被截断；本轮继续用占位符替换后再落盘。

**下一步（已登记）**

- 见 README §11 第 40–41 条：仍缺 strict same-level 独立源；主记分牌与冻结读数要逐轮过 AST 静态守卫。
