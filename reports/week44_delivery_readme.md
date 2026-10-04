# Week 44 交付说明

**本轮性质**：治理接线 + 静态守卫周。把 W43 登记的两条治理欠账（层准入要过闸、治理守卫要逐轮跑）接进机器，并给 strict same_level 写机器定义、给主记分牌加一条 AST 静态守卫。
**shot 账本**：**0 shot，累计仍 19**。四条 lane 全是只读治理件与静态审计。
**冻结读数**：`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`，一个不动。

---

## 1. 判据总账

| lane | 标题 | 判据 |
| --- | --- | --- |
| W44-A | 层准入闸门 + 全仓消费者审计 | H44a1–H44a8：**8 成立** |
| W44-B | 逐轮验收运行器 | H44b1–H44b7：**7 成立** |
| W44-C | strict same_level 机器要求 + 在仓候选审计 | H44c1–H44c8：**8 成立** |
| W44-D | AST 静态 shot / 冻结读数守卫 | H44d1–H44d8：**8 成立** |

**合计 31 条判据 = 31 成立 + 0 判否**（本轮无新增在册判否）。四个冻结读数未动，31 项 W44 测试全绿（含 `tests/test_repo_hygiene.py`）。

## 2. 关键读数与边界

- **准入闸门**：`admit_prior(layer, use)` 只在 `verdict == admit` 时返回，否则抛 `PriorRefused`（未登记层同样拒绝）。扫 **611** 个 `*.py` / `*.md`、命中 **18** 个（文件 × 层）对，**运营性先验使用 1**（正对照 pubchemqc，已过闸）、**未申报 0**。负对照 `ccsd_t` / `qm9` / `batt` 全被拒，正对照 **PubChemQC 过闸**。
- **验收运行器**：扫 `成果输出/week*/week*_summary.json` 共 **41** 轮、**33** 轮声明验收字段、判 **fail 0** 轮；最近五轮 **week40–week44 全过**；台账不变式全成立。
- **strict 规格**：六个在仓候选（xTB / QM9 / PubChemQC / Batt(target) / ORCA r2SCAN-3c / 扩展层）与 Batt 属性距离 0 的 **0** 个（`strict same_level` 计数 **0**，登记为已知边界）；最近一对 **QM9–PubChemQC 属性距离 2**（仅泛函 + 相相同），与 xTB–扩展层并列最近；`near_same_level` 合法对恰为这两对，**越权 0**。
- **静态守卫**：解析 **359** 个 `*.py` / **1,302,367** 个 AST 节点、解析错误 **0**；冻结注册表 2 处全等于冻结 7 项（**mutation 0**）；四个冻结读数**写入 0** / 作 RHS 引用 **267**；`promoted = True` 未登记 **0**；三个老探针的 4 项私有同名局部量登记为 `legacy_local`。

## 3. 复现

```powershell
$env:PYTHONIOENCODING="utf-8"; $env:OMP_NUM_THREADS=1; $env:OPENBLAS_NUM_THREADS=1
python probes\w44_prior_gate.py
python probes\w44_acceptance_runner.py
python probes\w44_same_level_spec.py
python probes\w44_static_shot_guard.py
python -m pytest tests\test_repo_hygiene.py tests\test_w44_prior_gate.py tests\test_w44_acceptance_runner.py tests\test_w44_same_level_spec.py tests\test_w44_static_shot_guard.py -q -p no:cacheprovider
python probes\export_week44_results.py --overwrite
```
