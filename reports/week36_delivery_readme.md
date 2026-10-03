# W36 交付说明：README §11 剩余五条一次性收口

## 0. 一句话

W35 之后 README §11 还剩五条登记未执行的事项。本轮把它们**全部**做成盘上产物：端点规则变成条款表 + 可执行复算符（A）、通道噪声地板接进显示层（B）、保真度缺口变成显式选择准则（C）、引用登记变成机械准入清单（D）、口径更正从已发布稿落回装配源（E）。五条 lane **全部后验、全部 0 shot**，累计仍是 **19**。

## 1. 五条 lane

| lane | README 条 | 性质 | shot | 探针 / 报告 |
| --- | --- | --- | --- | --- |
| W36-A | 第 4 条 | 规则入册 + 端点复算 | **0** | `probes/w36_endpoint_rule.py` / `reports/w36_endpoint_rule.md` |
| W36-B | 第 6 条 | 噪声地板显示层 | **0** | `probes/w36_channel_noise_floor.py` / `reports/w36_channel_noise_floor.md` |
| W36-C | 第 7 条 | 多保真度准则 | **0** | 同上 |
| W36-D | 第 14 条 | 准入清单 | **0** | `probes/w36_gate_admission.py` / `reports/w36_gate_admission.md` |
| W36-E | 第 15 条 | 装配源口径同步 | **0** | `probes/w36_v2_source_correction.py` / `reports/w36_v2_source_correction.md` |

判据合计 **5 + 8 + 5 + 5 = 23 条，全部成立**。

## 2. W36-A：端点规则正式化

盘上条款表 `data/processed/w36_endpoint_rule_registry.csv`，7 条：

| 条款 | 内容 |
| --- | --- |
| R1 | 端点 = 先对每个种子的**全部折**取算术均值，再对锁定种子集取算术均值 |
| R2 | 锁定种子集 `42,1234,2026,31337,7`（跑前锁定，不得事后增删） |
| R3 | 每个种子的折数 **10**（RepeatedKFold 5×10） |
| R4 | 稠密 13 列块默认 `max_bin=128; colsample_bytree=0.8; reg_lambda=1.0; max_depth=2; n_estimators=200; learning_rate=0.05` |
| R5 | 端点**判等容差 1e-12** |
| R6 | 冻结读数表不新增条目；四个冻结读数原值不变 |
| R7 | 四个冻结读数登记值 |

**复算符** `probes/w36_endpoint_rule.py::endpoint_of(rows, arm)`：种子集或折数不一致直接抛 `SeedSetDriftError`。

**结果**：六张逐重复表 / **49 个臂**；**26 条已发布端点全部复现**，最大差 `2.220446049250313e-16`（1 ulp）；3 个一折描述性臂标注「不适用」且无发布值。

**为什么 R5 必须存在**：独立复算的 `fmean` 与发布值最多差 1–3 ulp。逐位字符串比较会把 19 枪里 26 条端点中的一部分判成「不一致」，而那只是求均值顺序的最后一位。**判等必须是容差。**

## 3. W36-B：通道噪声地板显示层

`probes/artifacts/w36_channel_noise_floor.csv`（4 行）：

| 通道 | s0 | N_pop | Δτ=0.05 | Δτ=0.10 | Δτ=0.15 | Δτ=0.20 |
| --- | --- | --- | --- | --- | --- | --- |
| 介电常数 eps | 0.4737 | 205 | 178.9 | 129.5 | 88.7 | 61.6 |
| 分子轨道 | 0.5828 | 29,515 | 1987.0 | 523.2 | 234.8 | 132.5 |
| 氧化还原自由能 | 0.3695 | 392 | 268.9 | 138.4 | 76.6 | 47.1 |
| 黏度 eta | 0.4903 | 708 | 481.8 | 246.0 | 135.5 | 83.2 |

所需 N 由 W33-B 的精确零分布工具（`POWER_FACTOR = 2.80×√2`）复算，与 `w33_kendall_null_budget.csv` **最大差 0**。

`probes/artifacts/w36_repeats_display_layer.csv`：`*_repeats.csv` 共 **52 张**，**51 张**映射到通道并逐张带上 `display_note`（s0 + 三个 Δτ 档的分辨边界），**1 张**（`w20_safety_model_repeats.csv`，安全通道无 W32-A 地板）显式标注「未映射」。

**被冻结的 52 张表在生成前后逐文件 sha256 相等**——加列会改字节、破坏 AF-12 坐标，所以走**旁挂附表**，入口 `probes/artifacts/w36_channel_dashboard_v2.csv`（在 W34 看板上加 `req_n_dtau_0.10` 与 `display_note`，不改原表）。

## 4. W36-C：多保真度联合的显式准则

`s0_hat = 0.30758114075296145 + 0.33317352371160197 · (1 − tau_b_full)`，R² = `0.4437345881956626`；Spearman = `0.8058119658119658`（复现 W32-A 的 R2，26 条序列）。

| 通道 | 缺口 | s0 实测 | s0 预测 | N 实测 | N 预测 | 相对误差 | 一致 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 介电常数 | 0.342 | 0.4737 | 0.4214 | 129.5 | 118.1 | 8.8% | 是 |
| 分子轨道 | 0.634 | 0.5828 | 0.5189 | 523.2 | 416.3 | 20.4% | 是 |
| 氧化还原 | 0.233 | 0.3695 | 0.3850 | 138.4 | 145.9 | 5.4% | 是 |
| 黏度 | 0.882 | 0.4903 | 0.6015 | 246.0 | 314.9 | 28.0% | 是 |

相对误差中位 **14.6%**（门 25%）。四个通道的「可分辨」裁决在预测与实测之间**全部一致**。

**用法**：拿到一个低保真代理 → 量缺口 → 查 `s0_hat` → 算所需 N → 若手上 N 低于该线，该代理在这个样本上**不可分辨**。

## 5. W36-D：引用登记升为准入清单

`probes/artifacts/w36_gate_admission_manifest.csv`（10 行 = 登记表 10 行）：还原 8 / 氧化 2；`mark` 全部由 **W34-A 守卫复算**（`mark_source = W34-A 守卫复算`），与登记值**不一致 0**；氧化轴标「不适用（门禁只覆盖还原轴）」。

`probes/artifacts/w36_gate_admission_refusals.csv`（3 行，**全部拒绝**）：

| 合成格子 | 理由 |
| --- | --- |
| `r2scan3c / gas / census_246` | 新层级从未登记 |
| `gfn2 / benzene / census_246` | 新介质从未登记 |
| `gfn2 / gas / paired_orca_27` | 新总体从未登记 |

## 6. W36-E：装配源口径同步

**第 15 条答案**：v1 线 `paper/paper_zh_draft.md` 与英文线 `paper/full_draft.md` 的「不敏感」命中 **0 处**。

**发现的隐患**：W35-B 的四处更正只落在已发布稿，装配源未改 ⇒ 重建会复活旧文案。

**已落回装配源**：C1 / C2 → `paper/_v2_body_b.md`；C3 → `paper/_v2_appendix.md`；C4 → `paper/_v2_concl.md`（逐字同 W35-B，幂等）。

**已发布稿未动**：`paper/paper_zh_draft_v2.md` sha256 = `dfb3b282f8ccf76653d244a6a2c618d92a6e12003d012b81cca9f08dc9c6e78e`，与预注册里的 `sha256_before` 逐位相同。

**重建校验**：临时路径重建（不碰仓库文件）确认四处更正全部出现在产物里。

**登记未修**：`probes/artifacts/w36_v2_drift_inventory.csv` 记 **11 段**装配源无法复现的漂移（§3.8.1 等只在已发布稿里存在的段落）。留给专门的回灌轮次。

## 7. 产物与复算

- W36-A：`probes/w36_endpoint_rule.py`、`data/processed/w36_endpoint_rule_registry.csv`、`probes/artifacts/w36_endpoint_conformance.csv`、`probes/artifacts/w36_endpoint_rule_summary.json`、`reports/w36_endpoint_rule.md`、`tests/test_w36_endpoint_rule.py`
- W36-B/C：`probes/w36_channel_noise_floor.py`、`probes/artifacts/w36_channel_noise_floor.csv`、`probes/artifacts/w36_repeats_display_layer.csv`、`probes/artifacts/w36_channel_dashboard_v2.csv`、`probes/artifacts/w36_fidelity_criterion.csv`、`probes/artifacts/w36_channel_noise_floor_summary.json`、`reports/w36_channel_noise_floor.md`、`tests/test_w36_channel_noise_floor.py`
- W36-D：`probes/w36_gate_admission.py`、`probes/artifacts/w36_gate_admission_manifest.csv`、`probes/artifacts/w36_gate_admission_refusals.csv`、`probes/artifacts/w36_gate_admission_summary.json`、`reports/w36_gate_admission.md`、`tests/test_w36_gate_admission.py`
- W36-E：`probes/w36_v2_source_correction_prereg.json`、`probes/w36_v2_source_correction.py`、`probes/artifacts/w36_v2_drift_inventory.csv`、`probes/artifacts/w36_v2_source_correction_summary.json`、`reports/w36_v2_source_correction.md`、`tests/test_w36_v2_source_correction.py`
- 复算（零网络、零新算力，各约 1 秒，顺序无关）：
  `python probes\w36_endpoint_rule.py`
  `python probes\w36_channel_noise_floor.py`
  `python probes\w36_gate_admission.py`
  `python probes\w36_v2_source_correction.py`
- 验收：`python scripts\verify_four_core_registry.py --check`、`python scripts\check_paper_artifact_consistency.py`、
  `python -m pytest tests\test_repo_hygiene.py tests\test_w36_endpoint_rule.py tests\test_w36_channel_noise_floor.py tests\test_w36_gate_admission.py tests\test_w36_v2_source_correction.py -q -p no:cacheprovider`

## 8. 口径与边界

- 五条 lane **全部 0 shot**（累计仍 **19**）、不改 `METRIC_NAMES`、不新增特征列、缺行不插补、不动四个冻结读数。
- **1e-12 是判等容差，不是显著性门**；**跨 0 = 未检出差异 ≠ 无差异**。
- **被冻结的 `*_repeats.csv` 零字节改动**；噪声地板以附表形式接管显示层。
- **准入件只约束还原轴**；氧化轴「不适用」。
- **装配源漂移已登记未修复**：W36-E 只保证已发布稿的四处更正不会在重建时消失；整体回灌是下一轮的立项对象。