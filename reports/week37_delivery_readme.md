# Week 37 交付说明：README §11 第 16 / 17 / 18 条（全部后验，不占 shot）

**本轮 = W37**：把 §11 里最后三条「已登记、未执行」全部收口。
**shot 账本**：**本轮 0 shot，累计仍 19**。四个冻结读数一个都没动。
**收口顺序**：按 AF-12 —— 先封树提交 → 用该提交**干净重导** → 按需补修复提交。

## 1. 一句话结论

- **第 16 条（装配源回灌）**：漂移 **11 段 → 0 段**（实际回灌 **12 段**，多出的一段是
  §3.21 末尾那个被 `strip_rules` 吃掉的空行）。重建产物与已发布稿
  `paper/paper_zh_draft_v2.md` **逐字节相等**，已发布稿 sha256 `dfb3b282f8cc…` **未变**；
  真跑一次 `build_paper_v2.py`（不加 `--force`）后交付字节仍不变。
- **第 17 条（端点判等守卫）**：仓库现存「≥ 8 位有效数字字面量 `==` / `!=`」共 **95 处**，
  逐条判定后**禁止 0 处**（现存的全在测试断言里，属于登记常量回归）；合成违规能被抓、
  合法容差用法不误抓；容差**从注册表 R5 读出**（`1e-12`），改注册表会被发现。
- **第 18 条（准入接进导出）**：论文附录 A 的还原轴引用点 **7 个**（还原 5 / 氧化 2）
  全部匹配到登记行并准入，`mark` 由 W34-A 守卫复算、**零不一致**、未登记 0；
  删行 / 改名会 `exit ≠ 0`。校验器已挂进 `tests/test_repo_hygiene.py`，
  而该文件被各周导出器的 `VERIFIERS` 引用 ⇒ **导出阶段的验证块自动带上准入检查**。

## 2. 判据

**16 条全部成立**：W37-A `H37a1–H37a5`（5）、W37-B `H37b1–H37b5`（5）、
W37-C `H37c1–H37c6`（6）。逐条读数见 `reports/week37_project_charter.md` 第 4 节。

## 3. 交付物

| 类别 | 路径 |
| --- | --- |
| 探针 | `probes/w37_v2_backfill.py`、`probes/w37_endpoint_tolerance_guard.py`、`probes/w37_gate_admission_export.py` |
| 校验器 | `scripts/check_redox_admission.py` |
| 装配源改动 | `paper/build_paper_v2.py`（新增拼接步骤）、`paper/_v2_splices.json`、`paper/_v2_splice_sec381_*.md`、`paper/_v2_splice_sec310_*.md`、`paper/_v2_splice_sec314_*.md`、`paper/_v2_body_b.md`、`paper/_v2_appendix.md`、`paper/_v2_concl.md`、`paper/_v2_disc_extra.md` |
| 产物 | `probes/artifacts/w37_v2_backfill_inventory.csv`、`probes/artifacts/w37_v2_backfill_summary.json`、`probes/artifacts/w37_endpoint_compare_sites.csv`、`probes/artifacts/w37_endpoint_tolerance_guard_summary.json`、`probes/artifacts/w37_gate_admission_export_sites.csv`、`probes/artifacts/w37_gate_admission_export_summary.json` |
| 报告 | `reports/w37_v2_backfill.md`、`reports/w37_endpoint_tolerance_guard.md`、`reports/w37_gate_admission_export.md` |
| 测试 | `tests/test_w37_v2_backfill.py`（7 项）、`tests/test_w37_endpoint_tolerance_guard.py`（7 项）、`tests/test_w37_gate_admission_export.py`、`tests/test_repo_hygiene.py`（追加 1 条） |
| 导出 | `probes/export_week37_results.py` → `成果输出/week37` |

## 4. 验收命令

```powershell
$env:OMP_NUM_THREADS=1; $env:OPENBLAS_NUM_THREADS=1; $env:MKL_NUM_THREADS=1; $env:PYTHONIOENCODING="utf-8"

# 三条 lane 的探针
python probes\w37_v2_backfill.py
python probes\w37_endpoint_tolerance_guard.py
python probes\w37_gate_admission_export.py

# 准入校验器（导出阶段的那一条）
python scripts\check_redox_admission.py

# 口径校验（必须仍然通过）
python scripts\verify_four_core_registry.py --check
python scripts\check_paper_artifact_consistency.py

# 测试子集
python -m pytest tests\test_repo_hygiene.py tests\test_w37_v2_backfill.py tests\test_w37_endpoint_tolerance_guard.py tests\test_w37_gate_admission_export.py -q -p no:cacheprovider

# 交付导出（先提交、后重导）
python probes\export_week37_results.py --overwrite
```

## 5. 边界（照实说）

1. **W37-A 的扫描边界**：只扫「字面量」比较（float 字面量或可解析为 float 且 ≥ 8 位有效数字的
   字符串字面量）。运行期两个变量之间的一般相等**不在扫描范围内**。
2. **W37-A 的 `1e-12` 不是显著性门**，只是判等容差；不得用它放宽任何判据。
3. **W37-B 的已知盲区**：读数令牌是静态词汇表，论文里全新出现的、不在词汇表内的
   未登记数值不会被拦截（见 `reports/w37_gate_admission_export.md` 第 6 节）。
4. **W37-B 只覆盖还原轴**：氧化轴是阳离子态，门禁（阴离子态审计）无对应条款，
   按既有约定标「不适用」。
5. **`_v2_splices.json` 的锚点必须唯一**：命中数 ≠ 1 时 `build_paper_v2.py` 直接报错退出。
   这条保证了「装配源 = 交付字节」不会静默退化。
6. **不占 shot**：累计仍 19；四个冻结读数未动；不改 `METRIC_NAMES`；缺行不插补。
