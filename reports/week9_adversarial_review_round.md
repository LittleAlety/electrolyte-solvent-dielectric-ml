# Week 9 对抗式审读记录（adversarial-review-optimize）

- 基线 revision：`8c5582b`（main，工作区干净）
- 审读范围：`766cbcc`、`04d3ab1`、`8c5582b` 三个提交
- 角色分离：reviewer 为独立只读 agent（未改任何文件）；修复由主线程在该范围的最小写集内完成；修复后由同一 reviewer 复核
- 复核结论：**0 Critical / 1 Important / 5 Minor**；Important 已修，4 项 Minor 已修，2 项 Minor 明确保留

## 一、数值核对（reviewer 逐条复算，全部复现）

| 论文声明 | 产物字段 | 实测 |
| --- | --- | --- |
| Fig1 100/210/243/245/246，拟合 236 = 245−4−4−1 | `paper_figure_dataset_growth_summary.json` / `v032_ablation_summary.json` | 一致 |
| Fig2 hybrid R² 0.364 / Spearman 0.828 / MAE 6.69；MAE ε<20 3.9、ε>60 63.8 | `v032_ablation_summary.json` | 0.3636 / 0.8282 / 6.6862 / 3.9470 / 63.7984 |
| Fig3 29 个新溶剂；R² 0.122/0.154/0.286 | `g2_domain_gap_summary.json` | 0.12243 / 0.15366 / 0.28599 |
| Fig4 边际 0.9153–0.9156；ε>60 0.0145/0.2568/0.0382；归一化 0.1995/0.4778/0.2881 | `paper_figure_conformal_strata_summary.json` | 一致 |
| Fig5 cluster 留出 R² 0.138/0.268/0.295 | `v032_target_scaffold_summary.json`（raw 支） | 0.13832 / 0.26778 / 0.29533 |
| 适用域 2070/6150 = 33.66%；域内 5.02 vs 域外 11.51 | `applicability_domain_summary.json` | 0.33658536 / 5.02033 / 11.51458 |

结论：**没有任何数字与产物不符**；论文对 ε>60 层 n=5 的免责声明与 summary 的 `honest_boundary` 一致，没有出现「caption 承诺 summary 明确否认的保证」。

## 二、Important（已修）

**论文声称六张图都给出了生成脚本，实际只有 2/6 张有 `Script:` 行。**

修复不是在文字上退让，而是把缺的四条补实：

1. `probes/dielectric_representation_ablation.py` 新增 `--plot-only`（从已提交 summary 重渲染，不重跑基准、不重写任何 CSV）。
2. Fig2/Fig5 的产物用新命令重渲染，**与仓库中原产物逐字节相同**：
   - `probes/artifacts/v032_ablation.png` sha256 `8c3df6c4df2fc061…`（渲染结果与 tracked 文件同哈希）
   - `probes/artifacts/v032_target_scaffold.png` sha256 `7bb3a181e7e44220…`（同上）
3. 六张图全部补上 `Script:` 行（Fig2/5 给出 `--plot-only` 完整命令，Fig3/6 给出探针命令）。

## 三、Minor

| # | 问题 | 处置 |
| --- | --- | --- |
| 1 | `paper_figure_dataset_growth.py` 的 `sum(evidence.values()) != len(rows)` **恒为假**（空值被归为 `unlabelled`），是死代码 | **已修**：新增 `_missing_evidence_rows()`，缺 `evidence_level` 的行现在会真正让探针失败；配单测 |
| 2 | `verify_paper_figures.py` 只校验「路径存在」，把 Fig3 的产物换成 `data/dielectric_v03.csv` 仍 PASS | **已修**：新增逐图 `EXPECTED_FIGURE_ARTIFACTS` 固定映射 + 限定产物必须在 `probes/artifacts/` 下且为 `.png`；配两条反例单测 |
| 3 | `write_sha256s` 的排序/排除口径与仓库 canonical writer 不一致（平台相关的行序） | **已修**：改为直接委派 `electrolyte_ml.exporting.write_export_manifest`；重导 week9 后清单与 canonical writer **逐字节相同** |
| 4 | Week 9 导出器 `main()` 恒返回 0，校验失败也退出码 0 | **已修**：改为 `return 0 if result["verification_passed"] else 1` |
| 5 | 图注 "4 rows named in the exclusion file" 与仓库别处「5 行排除清单」口径冲突 | **已修**：改为「五条排除清单中出现在该源表里的 4 行」 |
| 6 | `shlex.split` 使用 POSIX 规则，未来若在 `VERIFIERS` 里写 Windows 反斜杠路径或含空格路径会静默跑错 | **保留**：当前 8 个 week1–8 条目与 week9 条目全部实测为 `shlex.split(x) == [x]`（除刻意带 `--check` 的那条）；属未来误用风险，不构成现存缺陷 |
| 7 | 导出的 5 个 verifier 全部在**仓库**上运行，`verification.json` 不为**交付副本**背书；Fig2/3/5/6 的 PNG 与 summary 是否同步无自动新鲜度校验 | **保留**：`--overwrite` 不清理目录属既有 week1–8 模式；已在 README 的校验小节要求手动跑 `verify_export_manifests.py --output-dir <本目录>` |

## 四、修复后的最终校验

- `pytest -q -p no:cacheprovider`：**834 passed**（231.50 s）
- `ruff check scripts src probes tests notebooks`：全绿
- `compileall`：通过
- `check_paper_artifact_consistency.py`：PASS
- `build_paper_full_draft.py --check`：up to date（1006 行）
- `verify_paper_figures.py`：PASS（6 图，含逐图产物映射与脚本强制）
- `verify_export_manifests.py`：**9/9 PASS**
- 数据面：本轮**未改任何数值**（新增的 `--plot-only` 只渲染，不重跑基准）
