# PLAN B 第十三轮执行汇报：完成度审计 22/22 PASS

**工作包：** B08 完成度审计（项目终检）
**时间：** 2026-11-23
**性质：** 项目收口。目标全部条件由独立审计逐项验证。

---

## 零、核心结论

| 项 | 结果 |
|---|---|
| **完成度审计** | ✅ **22/22 PASS** |
| 审计性质 | 每项从产物**重新推导**，不接受报告自述 |
| 测试 | ✅ **378/378 通过** |
| 冻结产物 | ✅ **OVERALL PASS** |
| 结论证据映射 | **25/25 全部有据** |
| DFT | **0 core-hours** |
| HUMAN_SIGNED 伪造 | **0 次** |
| Git 写操作 | **0** |

---

## 一、审计方法

审计脚本 `scripts/b08/audit_completion.py` 的设计原则：**不接受自述**。

| 声明 | 审计如何验证 |
|---|---|
| 「B01 收口」 | 数交付物文件（7/7）+ 程序文件（5/5），不读报告 |
| 「缺陷已修复」 | 重算 v06 账目恒等式 + 重验 v04 冻结哈希 |
| 「四审完成」 | 逐包数 reviewer 文件，按各包自己的命名规则 |
| 「未伪造签名」 | 读 status 字段 **+ grep 最终包** |
| 「未越权 DFT」 | 要求 `dft_started=false` **且** 工时=0 |
| 「结论有据」 | 逐条检查证据文件是否**真实存在** |

**任一项失败则脚本以非零码退出**，因此可作为发布门。

---

## 二、22 项检查结果

### 数据工程（R01–R07）

| # | 要求 | 依据 |
|---|---|---|
| R01 | B01 交付物 7/7 + 程序 5/5 | outputs=7/7, programs=5/5 |
| R02 | B01 独立校验全通过 | **18/18** |
| R03 | 合成中点+温度推定+冲突经 v06 修复 | 73 + 175 = 248；v04 未变 |
| R04 | 高压扫描污染已量化并排除 | 15 行污染，未改写冻结窗口 |
| R05 | 温度推定已量化并标记 | 22 行推定 |
| R06 | γ-戊内酯冲突入队并四审裁决 | 两条均 REJECTED |
| R07 | B03 交付物 7/7 且账目闭合 | accounting_closed=True |

### 模型与筛选（R08–R12）

| # | 要求 | 依据 |
|---|---|---|
| R08 | B04 候选池有版本与来源链 | 22 条；pool_C 未变 |
| R09 | 相态错误已审计 | **4/22 低于熔点** |
| R10 | E1/E4/E6 全部完成 | 三项均 done |
| R11 | E2/E3/E5 显式登记未运行 | NOT_RUN / NOT_RUN_CONDITIONAL |
| R12 | B07 交付物 8/8 | complete=True |

### 审核与交付（R13–R15）

| # | 要求 | 依据 |
|---|---|---|
| R13 | **四智能体审核 4/4 齐备** | B02=4/4, GVL=4/4, B03=4/4, B04+B05=4/4 |
| R14 | 六件套齐备 | 6/6 |
| R15 | 所有结论有证据映射 | **25 条，0 条缺证据** |

### 冻结与合规（R16–R22）

| # | 要求 | 依据 |
|---|---|---|
| R16 | J01/J02/J03 冻结 | verifier = PASS |
| R17 | `dielectric_v04` 未变 | sha256 匹配 |
| R18 | 未伪装 HUMAN_SIGNED | 0 写入，0 伪造文件 |
| R19 | 标注为 AI_CONSENSUS_NOT_HUMAN_SIGNED | 正确 |
| R20 | 未启动 DFT | `dft_started=False`, 0 小时 |
| R21 | 未 git commit/push/release | none |
| R22 | 计算在授权内 | < 0.35 / 300 core-hours |

---

## 三、审计中发现的自身缺陷（已修复）

审计第一版判 **21/22 FAIL**，R13（四审齐备）失败。核查后发现：

**B03 的 reviewer 文件命名为 `b03_reviewer_N_decisions.csv`**，
而审计脚本用统一通配 `reviewer_[1-4]_decisions.csv`，因此**漏数了 B03 的 4 份**。

这是一个「审计脚本自身有 bug 导致误报失败」的案例。
修正后按各包自己的命名规则计数：**四个包全部 4/4**。

**这个缺陷值得记录**，因为它说明：审计脚本也需要被审计。

---

## 四、最终科学结论

> **单分子描述符的信号几乎全部来自少数电子描述符（尤其偶极矩），
> 结构描述符在此样本上贡献噪声。**
>
> 电子块 MAE **6.08**，优于常数基线 10.81，特征置换 p = **0.000**；
> 但**没有可证明的筛选价值**（精确枚举 p = 0.157，位于第 15.7 百分位，
> 即优于 84.3% 的随机选择但未达显著）。

### 描述符有效性的精确边界

不是「描述符无用」，而是：

> **抓到了 μ²/V（单分子主导项），没抓到 Kirkwood g（偶极关联，液体 ε 的集体部分）。**

而**名义 12 列特征的有效秩只有 10**，其中最强的单一信号是偶极矩一个数。

### 三个假设

| 假设 | 判定 | 关键证据 |
|---|---|---|
| **H1** 误差有化学空间依赖性 | 部分支持 | 家族间 MAE 跨度 1.7–9.1；误差随结构距离增大（ρ=−0.51）|
| **H2** 更精确电子计算不必然带来更好预测 | **不支持** | ΔMAE = −3.46，p = 0.0004；且偶极矩单独即达电子块 106% |
| **H3** 回归误差与筛选收益脱钩 | 支持 | regret 在 σ=6 有内部最小，随后回升至随机 |

**H2 的判定在项目过程中发生过反转**（原为「支持」），原因是修复了 ridge 缺截距缺陷。

---

## 五、项目过程中发现的缺陷总览

| 类别 | 数量 |
|---|---:|
| 四审发现的自身代码/流程缺陷 | **16** |
| 其中导致**结论反转** | **3** |
| 数据层系统性缺陷 | **7** |
| 特征质量缺陷 | **4** |
| 审核基础设施缺陷 | **4** |

### 三处结论反转

| 原结论 | 根因 | 修复后 |
|---|---|---|
| 两模型均劣于基线 → 描述符无信号 | ridge 缺截距 | MAE 17.29 → **6.50**，R² −1.29 → **+0.54** |
| 指纹相同处误差 19.48 = 描述符失明 | 同一缺陷（85.9% 是整体偏移）| → **2.79** |
| 噪声使 regret 下降 → 预测有害 | 阶梯停在凹曲线下坡段 | 内部最小 σ=6，随后回升 |

**这三处全部由四智能体审核发现**（R1/R3/R4 独立命中前两处）。
单一模型的自审不会发现「代码能跑、数字能出、但结论反转」的缺陷。

---

## 六、测试与资源

| 项 | 结果 |
|---|---|
| `test_b08_completion_audit.py` | **8/8**（新增）|
| 实质测试合计 | **195 + 183 = 378 通过** |
| 冻结产物 | **OVERALL PASS** |
| B01 独立校验 | **18/18 PASS** |
| CPU core-hours | **< 0.90** |
| DFT | **0** |

---

## 七、仍需人工批准

| # | 事项 | 为何需批准 |
|---|---|---|
| G14 | 温度推定 22 行改 `model_ready=false` | 改变 v04 可用样本数 |
| G15 | `v04_epsilon` 骨架连接污染修复（3 行）| 改变 J03 产物 |
| G1 | `outputs/` 未被 git 跟踪 | 需 commit 或仓库外写入 |
| G2 | `v56_standalone` 在仓库外 | 需仓库外写入 |
| — | `git push`（本地纯快进 5 个提交）| 第八章列为需批准动作 |

**这些都没有做，因为它们需要你的决定。**

---

## 八、交付物清单

### `outputs/final/`（六件套 + 2 份审计）

| 文件 | 内容 |
|---|---|
| `B_FINAL_STATUS.json` | 9 个工作包状态、计算消耗、合规声明 |
| `B_FINAL_MEASUREMENT_LEDGER.csv` | 2065 条测量，每条带源文件 sha256 |
| `B_FINAL_CLAIM_EVIDENCE_LEDGER.csv` | **25 条结论**，全部有证据映射 |
| `B_FINAL_HASH_MANIFEST.json` | **193 个产物**字节冻结 |
| `B_FINAL_REVIEW.json` | 4 轮四审记录 + 16 处缺陷 + 3 处结论反转 |
| `B_FINAL_REPORT.md` | 可读的完整叙述 |
| `B_FINAL_COMPLETION_AUDIT.json` | 22 项完成度检查 |
| `B_FINAL_COMPLETION_AUDIT.md` | 同上，可读版 |

---

## 附录：复现完整链路

```bash
cd "E:/Claude Code/电解质ML/电解质ML"
PY=.venv/Scripts/python.exe

# 0. 冻结校验（失败则停止）
$PY scripts/b00/verify_frozen_artifacts.py

# 1. B01
$PY scripts/b01/verify_measurement_reconstruction.py
$PY scripts/b01/build_reconstruction_exceptions.py
$PY scripts/b01/audit_pressure_heterogeneity.py
$PY scripts/b01/audit_temperature_imputation.py
$PY scripts/b01/build_source_conflict_register.py
$PY scripts/b01/build_dataset_v06.py
$PY scripts/b01/build_b01_gate_status.py

# 2. B02
$PY scripts/b02/build_admission_review_queue.py
$PY scripts/b02/build_consensus_gate.py
$PY scripts/b02/build_gvl_conflict_consensus.py

# 3. B03
$PY scripts/b03/build_a18_gap_register.py
$PY scripts/b03/verify_nbs514_evidence.py
$PY scripts/b03/build_b03_registers.py
$PY scripts/b03/build_b03_report.py
$PY scripts/b03/build_b03_consensus.py

# 4. B04
$PY scripts/b04/audit_pool_phase_state.py
$PY scripts/b04/build_candidate_pool_v2.py

# 5. B05
$PY scripts/b05/build_feature_registry.py
$PY scripts/b05/audit_feature_quality.py
$PY scripts/b05/run_e1_structure_vs_electronic.py
$PY scripts/b05/run_e1b_physics_constrained.py
$PY scripts/b05/run_e1c_block_ablation.py
$PY scripts/b05/run_e4_domain_generalization.py
$PY scripts/b05/run_e6_screening_decisions.py
$PY scripts/b05/build_model_boundary_report.py

# 6. B07
$PY scripts/b07/run_b07_split_comparison.py
$PY scripts/b07/assemble_b07.py

# 7. B08
$PY scripts/b08/build_final_package.py
$PY scripts/b08/audit_completion.py

# 8. 全量测试
$PY -m pytest tests/ -q
```
