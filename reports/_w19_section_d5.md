## 28.49 Week 19 D5 η 跨模型一致性：Chemprop-η 行级 MAE 0.085064 vs 在役 XGB 0.156863（Δ −0.071799），判 chemprop_better（2026-09-28）
|
**机制假设**：η 是全漏斗里离过门最近的在役通道（组键 MAE `0.17477197208762` vs 门 0.15，只差 0.025）。W18-A 只在**特征层**解冻行级数据，把「表示层是不是天花板」这个问题留着没答。D5 的问法是：同池、同切分、同目标、同单位，只把表示从 2048 列 Morgan 计数指纹换成**学出来的图表示**（Chemprop D-MPNN），MAE 会不会移动超过预注册容差 ±0.02。判据是 **delta，不是门**；门 0.15 只作上下文报告。
**预注册**：`probes/w19_chemprop_viscosity_prereg.json`，sha256 `c42846ccb9c898ebfd7da429e40247132134c90089b0d41d684ce6c5f313f7b9`，`status = locked_before_run`；配置**跑前注册、从未搜索**（60 epochs、batch 64、d_h 300、depth 3、三种子 42/1234/2026、descriptor 只用 T_K 与 1000/T_K 并在**训练行**上 fit StandardScaler）。容差三分支：`|Δ| ≤ 0.02` ⇒ `consistency_confirmed`；`Δ ≤ −0.02` ⇒ `chemprop_better`；`Δ ≥ +0.02` ⇒ `incumbent_confirmed`。`amendment_rule` 亦跑前声明（若计时外推超 60 分钟则按 epochs 60→30、集成 3→1、d_h 300→150 依序缩减，缩减项必须点名）。
|
**读数 · 只用组外（GroupShuffleSplit by InChIKey）留出集**
| 池 | 行 | 键 | 测试行 | 在役 MAE | Chemprop MAE | Δ | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `row_level`（主池） | 4151 | 976 | 838 | 0.15686276760094522 | 0.08506361044387624 | −0.07179915715706899 | `chemprop_better` |
| `family_level` | 3582 | 957 | 708 | 0.17477197208762 | 0.08908094784092072 | −0.08569102424669928 | `chemprop_better` |
- 两个池都报 `split_verified_against_incumbent = true`、`group_overlap_keys = 0`：两模型看到**同一批训练行与同一批测试行**。
- **在役原位复现**：两池 `incumbent_reproduction.abs_gap = 0.0`、`matches_frozen = true` ⇒ 协议无漂移，负/正结论都不能归因于切分漂移。
- 主池在役 R2 `0.752682215223955`、Chemprop 集成 R2 `0.908162916149498`；family 池在役 R2 `0.7481271437772365`、Chemprop 集成 R2 `0.9174353584088537`。
- 门上下文：主池 Chemprop **过** 0.15 门、在役**不过**（`gate_0_15_passed_by_chemprop = true` / `gate_0_15_passed_by_incumbent = false`）。
|
**判定与边界**
- `verdict = chemprop_better`（两池同判）：学到的主池 Δ = −0.07179915715706899，**超过**预注册容差 ±0.02 ⇒ 在本协议下**表示层曾是 η 通道的天花板**。这是**开一条跟进 lane 的触发，不是晋级**。
- `promoted = false`；主记分牌尝试 **0** 次、累计仍 **11** 次；冻结基线 `0.4091179943351143` 与冻结头条 `0.4766400383507876` 未动。
- **η 通道独立报数**：row_level **4151 行 / 976 键**、family_level **3582 行 / 957 键** —— 这组数与 ε 通道的 457 / 97 / 276 / 2029 **不得混说**。
- **设计混淆必须照实说**：在役是**冻结单配置单种子** XGB，Chemprop 是**三种子集成**，Δ 里有集成/调参成分（W18-P0 显示 ε 上纯调参只动 `0.01370607964226378`，故「纯调参」不太可能是这个量级的解释，但该混淆无法从本设计里移除）。
- **无折级方差**：组外协议只有**一次** 20 percent 留出抽样；三种子只探初始化方差，不探切分方差。Chemprop 固定 60 epochs、无 validation fold、无 early stopping / checkpoint 选择 ⇒ 测试折无法影响任何超参。
- **口径更正（跑前登记）**：计划写「kinematic 存量 214 行仍冻结」，两半都错 —— 214 是**族级排除计数**、行级残差只有 **86** 行，且 §28.38 已解冻并判 `refuted`；本枪只**复用**已解冻的池，不重新解冻。
- 环境登记：`.venv-chemprop` 补装 `matplotlib` / `xgboost` / `h5py`（`viscosity_baseline` 导入即需要），镜像曾把 numpy 拉到 2.5.3（chemprop 要求 <2.0.0），已**回钉 1.26.4** 并复验全部导入。
- 本枪不引用任何文献数字作对照靶；在役 MAE 是**仓内实测值**，故 Δ 有意义。
|
**产物清单**
- `probes/w19_chemprop_viscosity.py`（sha256 `2e2a582b8627aafcbfd5547ba8151c6d1612441cd3a0ad9036d4bb35ea98b15c`）
- `probes/w19_chemprop_viscosity_prereg.json`（sha256 `c42846ccb9c898ebfd7da429e40247132134c90089b0d41d684ce6c5f313f7b9`）
- `probes/w19_chemprop_viscosity_summary.json`（sha256 `6fb74468dfa4844f5feeb012ec652ef3d08b70ede355293b60691b32173f7796`）
- `reports/w19_chemprop_viscosity.md`（sha256 `ca3213a76897f88a188e5b92324756f6764ce617906ec16ff2a887e1820da118`）
- `tests/test_w19_chemprop_viscosity.py`（sha256 `c7dd58c72fce682c2f88bf328ecf9f4283bebc3878065f86d5615f057d7faae1`）
- 侧车：`probes/artifacts/w19_chemprop_viscosity_repeats.csv`（sha256 `71e64d79b8e4138b808056c9ed4081ad18d4443d41285a8a3903d022828abec7`）、`probes/artifacts/w19_chemprop_viscosity.png`（sha256 `96f9f069095f86a714187ca912d0457126d75ffeefa65ce0a27e66ef80b292d1`）
|
**数字出处**
- 4151 / 976 / 3313 / 838 / 780 / 196 与 3582 / 957 / 2874 / 708 / 765 / 192 ← `probes/w19_chemprop_viscosity_summary.json::pools.row_level` / `::pools.family_level`
- 0.15686276760094522 / 0.08506361044387624 / −0.07179915715706899 与 0.17477197208762 / 0.08908094784092072 / −0.08569102424669928 ← 同 JSON 两池的 `incumbent.mae_log10_cP` / `chemprop.ensemble_mae_log10_cP` / `delta_mae_log10_cP`
- 0.752682215223955 / 0.908162916149498 / 0.7481271437772365 / 0.9174353584088537 ← 同 JSON 两池的 `r2_log10_cP`
- 0.02 三分支 / `amendment_rule_declared_before_run` ← `probes/w19_chemprop_viscosity_prereg.json::tolerance_preregistered` 与 `::amendment_rule_declared_before_run`
- 0.01370607964226378 ← `reports/w19_chemprop_viscosity.md::4`（引 W18-P0 的 ε 读数）
- 60 epochs / 3 集成 / 三种子 42 1234 2026 / 2.1.0 / 3.12.14 / 1.26.4 ← `probes/w19_chemprop_viscosity_summary.json::registered_config` 与 `::environment`
- 214 / 86 / 0.15 ← `reports/w19_chemprop_viscosity.md::0` 与 `::1`
**数字自检**：片段内数值 token 已对 `reports/w19_chemprop_viscosity.md` + `probes/w19_chemprop_viscosity_summary.json` + `probes/w19_chemprop_viscosity_prereg.json` + `tests/test_w19_chemprop_viscosity.py` 逐字回搜（ISO 日期整段排除、digest 不作数值 token）。**推算值 / 运行值 / 外部常量**：`28.49`（节号，任务书指定）；节标题里的 `0.085064` / `0.156863` / `0.071799` 是**四舍五入展示值**（文件里是 `0.08506361044387624` / `0.15686276760094522` / `-0.07179915715706899`；标题由任务书逐字指定，正文一律用全精度值）；`0.025`（**推算差值**：门 0.15 与在役 family_level MAE 0.17477197208762 之差）；`2.5` / `2.0`（numpy 镜像事件的环境版本事实：`2.5.3` / 要求 `<2.0.0`；其中 `1.26.4` 在 summary 的 `environment` 里有字面量）；`11`（累计主记分牌尝试，W18 冻结记账）。其余全部数值 token 在本 lane 素材内逐字命中。
|
