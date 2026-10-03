# W35 交付说明：把门禁接进下游，并把「不敏感」降级为「未检出差异」

## 0. 一句话

W34 留下两个口子：**守卫可用但没人被强制调用它**（引用 −0.602 / +0.835 的地方只写数字），以及**一个从未被分辨率检验过的肯定式论文表述**（「氧化轴对层级不敏感」）。本轮一边把门禁做成下游可查的旁路层 + 引用登记 + 消费者审计，一边用锁定预注册把论文口径改成「未检出差异（n = 22 不可分辨）」。

## 1. 两条 lane

| lane | 性质 | shot | 驱动件 | 探针／报告 |
| --- | --- | --- | --- | --- |
| W35-A | 后验旁路层 + 消费者审计（只读冻结表） | **0** | — | `probes/w35_redox_gate_consumers.py` / `reports/w35_redox_gate_consumers.md` |
| W35-B | 论文口径更正（预注册驱动、幂等） | **0** | `probes/w35_paper_r6_correction_prereg.json` | `probes/w35_paper_r6_correction.py` / `reports/w35_paper_r6_correction.md` |

两条 lane 都**不占主记分牌 shot（累计仍 19）**、都不改四个冻结读数、都不触 ε 主记分牌。

## 2. W35-A：门禁旁路层 + 引用登记表 + 消费者审计

**旁路表**（`data/processed/redox_readability_sidecar.csv`，**246 行** = 一行一键）：把 W34 注册表的（层级 × 介质）判定摊平成列。与注册表逐位比对了 **1028** 个（层级 × 介质 × 键）格，**不一致 0 个**；主注册表 sha256 `a01272b3e75514a6…` **未变**，四核心注册表 sha256 `e42885eb43779b7a…` **未变**。

**引用登记表**（`probes/artifacts/w35_gated_reference_register.csv`，**10 行**）：每行的 `mark` 都由 W34-A 的 `assert_redox_readable` 给出——拒答即写「不可判定」，不是本脚本自算一遍。

| 引用点 | 轴 | 层级/介质 | 值 | 合法/总体 | 标记 |
| --- | --- | --- | --- | --- | --- |
| `r6_ox_gfn2` | 氧化 | gfn2 / 气相 | 0.696970 | — / 22 | 不适用（门禁只覆盖还原轴） |
| `r6_ox_orca` | 氧化 | orca / 气相 | 0.653680 | — / 22 | 不适用（门禁只覆盖还原轴） |
| `r6_red_gfn2` | 还原 | gfn2 / 气相 | 0.835498 | **1** / 22 | **不可判定** |
| `r6_red_orca` | 还原 | orca / 气相 | −0.601732 | **0** / 22 | **不可判定** |
| `w33a_gfn2_gas` | 还原 | gfn2 / 气相 | 0.745098 | 52 / 246 | 可宣读 |
| `w33a_gfn2_thf` | 还原 | gfn2 / THF | 0.733130 | 154 / 246 | 可宣读 |
| `w33a_gfn2_benzaldehyde` | 还原 | gfn2 / 苯甲醛 | 0.674063 | 154 / 246 | 可宣读 |
| `w33a_gfn2_water` | 还原 | gfn2 / 水 | 0.811957 | 161 / 246 | 可宣读 |
| `w33a_orca_gas` | 还原 | orca / 气相 | （拒答，值列留空） | **0** / 22 | **不可判定** |
| `w33a_orca_smd_acetonitrile` | 还原 | orca / SMD 乙腈 | （拒答，值列留空） | **2** / 22 | **不可判定** |

**门禁范围的新口径**：门禁是**阴离子态**审计（`geom ∧ homo ∧ ea`），只覆盖**还原轴**；氧化轴两条登记为「不适用」——不得把阴离子门禁套到阳离子轴上。

**一条新发现的读法**：**同一（层级，介质）在两个总体上的可宣读性可以相反**——GFN2 气相加起来合法 **52/246**（可宣读），但在 R6 的 22 个配对化合物上只有 **1/22**（不可判定）。因此引用还原轴读数必须声明 `population_scope`。

**消费者审计**（`probes/artifacts/w35_gated_consumer_audit.csv`，**7 行**）：论文 §3.20 / §3.21 / 附录 A / 结论 #8、W34 看板、决策日志 §28.87 / §28.88。规则是「引用受门禁约束的数值（`0.602` / `0.601732` / `0.835` / `1.437`）就必须在同一段出现 `不可判定`」。

| 消费者 | 段内受约束数值 | 更正前 | 更正后 |
| --- | --- | --- | --- |
| `paper_s320` | 0.602 / 0.835 / 1.437 | **缺标记** | 有标记 |
| `paper_s321` | 0.602 / 0.835 | 有标记 | 有标记 |
| `paper_appendix_a` | 0.602 / 0.835 / 1.437 | **缺标记** | 有标记 |
| `paper_conclusion` | 0.602 / 0.835 / 1.437 | **缺标记** | 有标记 |
| `dashboard_w34` | — | 有标记 | 有标记 |
| `decisions_log_w33a` | 0.602 / 0.601732 / 0.835 | 有标记 | 有标记 |
| `decisions_log_w34b` | 0.601732 / 0.835 / 1.437 | 有标记 | 有标记 |

缺失数：更正前 **3** → 更正后 **0**。判据 **5/5 成立**（H35a–H35e）。

## 3. W35-B：R6 口径更正

**问题**：论文写「**氧化轴对层级不敏感**：换层级只动 0.043」。W34-B 的配对 bootstrap 给出 95% 区间 **[−0.1982, +0.0909]、跨 0** ⇒ 正确表述是「**在 n = 22 上未检出差异（不可分辨）**」。

**做法**：锁定件 `probes/w35_paper_r6_correction_prereg.json`（`locked_before_run`，sha256 `3bef7a992f124a8bfdef9ff2dba94e6bd41ba3a1f25fc688c8869b447edf85ac`）写死四条替换与不变量；`probes/w35_paper_r6_correction.py` **幂等**施加（第二次运行得到同一批字节）：

| id | 位置 | 更正 |
| --- | --- | --- |
| C1 | §3.20 第 1 条要点 | 「不敏感」→「未检出差异（不是「无差异」）」，带区间与「跨 0 ⇒ 不可分辨」 |
| C2 | §3.20 限制段 | 追加「分辨率与定义域并报」（还原轴区间不跨 0，但两层读数均判不可判定） |
| C3 | 附录 A 跨层级对照行 | 补区间与门禁判词（原 0.043 / +0.835 / −0.602 原位保留） |
| C4 | 结论 #8 | 内联「95% 区间跨 0 ⇒ 未检出差异」与「该轴门禁判不可判定」 |

论文 sha256 `8984fb6b6523fd6a…` → `dfb3b282f8ccf766…`；**所有既有数字原位保留**（只加注记）；四个冻结读数出现次数逐位不变；全 LF。判据 **5/5 成立**（H35f–H35j，含幂等）。

## 4. 口径与边界

- 两 lane 都**不占 shot（累计仍 19）**、不改 `METRIC_NAMES`、不新增特征列、缺行不插补、不动四个冻结读数。
- **拒答不是缺失值**：登记表里 ORCA 两层的 `tau_legal` 值列留空，就是守卫抛出的拒答结论，不得插补、赋伪值或静默丢弃。
- **门禁只管还原轴**：氧化轴登记为「不适用」，不得把阴离子门禁套到阳离子轴上。
- **总体必须声明**：同一（层级，介质）在 246 普查与 22 配对集上的合法子集数不同，引用时必须带 `population_scope`。
- **区间跨 0 = 未检出差异，不等于证明无差异**。
- W35-A / W35-B 按附录 C 属后验读数 / 预注册驱动的口径更正，**不得当作预注册结论引用**；单表示读数永不与冻结头条 `0.4766400383507876` 混比。

## 5. 产物与复算

- W35-A：`probes/w35_redox_gate_consumers.py`、`data/processed/redox_readability_sidecar.csv`、`probes/artifacts/w35_gated_reference_register.csv`、`probes/artifacts/w35_gated_consumer_audit.csv`、`probes/artifacts/w35_redox_gate_consumers_summary.json`、`probes/artifacts/w35_redox_gate_consumers.png`、`reports/w35_redox_gate_consumers.md`、`tests/test_w35_redox_gate_consumers.py`
- W35-B：`probes/w35_paper_r6_correction_prereg.json`、`probes/w35_paper_r6_correction.py`、`probes/artifacts/w35_paper_r6_correction_summary.json`、`reports/w35_paper_r6_correction.md`、`tests/test_w35_paper_r6_correction.py`
- 复算（零网络、零新算力，各约数秒，按此顺序）：
  `python probes\w35_paper_r6_correction.py`（先施加/校验论文更正）
  `python probes\w35_redox_gate_consumers.py`（再跑审计，它读更正后的论文）
- 验收：`python scripts\verify_four_core_registry.py --check`、`python scripts\check_paper_artifact_consistency.py`、
  `python -m pytest tests\test_repo_hygiene.py tests\test_w35_paper_r6_correction.py tests\test_w35_redox_gate_consumers.py tests\test_w34_legality_registry.py tests\test_w34_paired_power.py tests\test_w33_bound_state_gate.py -q -p no:cacheprovider`