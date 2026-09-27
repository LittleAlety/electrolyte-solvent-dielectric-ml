## 28.44 W18-P2 Onsager / Kirkwood Δ-learning（只换目标，池 / 折 / 计分器 / 表示全冻）：跨种子端点 0.224298 vs 参考 0.586114（Δ −0.361816），判 refuted；且安慰剂臂未按预注册塌回直接臂（2026-09-28）
|
**机制假设**：W17 的天花板分析说，单分子描述符缺的那一维是 **g（Kirkwood 取向相关因子）**。P2 不改模型、不改表示，只改**目标**：让冻结头去拟合残差 `ε_obs − ε_Onsager(μ², V_m, α, T)`，把 Onsager 反应场形式当先验注入。这是 W17 已证否的「描述符堆叠」之外的另一类射击——**物理函数形式**，而不是又一列特征。
|
**预注册**：`probes/dielectric_onsager_delta_w18_prereg.json`，sha256 `7c936b53e99182ab7f4bbe03aa13620f11095f2fc6a85eed882ef36759a08c8b`，`status = locked_before_run`，`non_blind = true`（seed 42 的锚点读数在写预注册前已知）。端点 = 预注册五种子 {42, 1234, 2026, 31337, 7} 上「10 重复 R² 均值」的跨种子算术平均；判据 = 该端点 ≥ 参考臂 + 0.02 判 `confirmed`，≥ +0.005 判 `partial`，否则 `refuted`。
|
### 一、锚点：先证协议没漂移（5/5 逐位复现）
- `reference_direct` 逐种子读数为 `0.6080587938801277` / `0.5653494903237062` / `0.5848044432962747` / `0.5985324927011000` / `0.5738259459028902`，与冻结记录 `full_table_lever4` / `Physical` 五种子**逐位相同**，5/5 `abs_gap = 0.000e+00`。
- 跨种子均值实测 `0.5861142332208197` vs 冻结端点 `0.5861142332208197`，`abs_gap = 0.000e+00`。
- 泄漏审计：5 种子 × 200 折 = **1000 折**，跨折化合物 0（`leakage_clean_text`）。池 = **2029** 全表行 / **457** 计分行 / **97** 化合物 / 362 外来扩展行；表示 `Physical(lever4)` 13 列。
|
### 二、单位自检：先证没算错，再看结论
- 向量式 vs 规范标量式（`src/electrolyte_ml/xtb_features.py::onsager_dielectric_estimate`）最大绝对偏差 **0.000e+00**；
- `mu_sq_over_Vm` 列 vs `dipole_D² / V_m` 最大相对偏差 **4.328e-08**（超差 0 行）；
- `molecular_volume_A3 × 1e-30 × N_A` vs 冻结 `molar_volume_m3_mol` 最大相对偏差 **3.855e-08**（超差 0 行）。
- **一处必须登记的自我纠错**：第一版把 `molecular_volume_A3`（**单分子**体积）直接当摩尔体积用，`q = N_A α/(3 V_m)` 被放大 N_A 倍、Lorentz–Lorenz 的 `n²` 落到 −2、解析项整体塌成 1.0。正确换算为 `V_m = molecular_volume_A3 × 1e-30 × N_A`（m³/mol）。这类量纲错误若不自检会把「公式没用」与「代码写错」混为一谈，故入册。
|
### 三、读数（跨种子端点）
| 臂 | 跨种子均值 | 相对 `reference_direct` |
| --- | ---: | ---: |
| `reference_direct`（冻结头直回 ε，锚点） | 0.5861142332208197 | 0 |
| `onsager_delta_xgb`（冻结头只拟合残差，预测时加回解析项） | 0.2242978111516481 | −0.3618164220691716 |
| `onsager_delta_recomputed`（同 Δ 方案，解析项改用 v0.4 构象表单构象偶极密度） | 0.22339251807234367 | −0.362721715148476 |
| `onsager_analytic_only`（纯解析，无 ML） | −0.5160011378298242 | −1.102115371050644 |
|
⇒ `best_arm = onsager_delta_xgb`、`best_improvement = −0.3618164220691716`、`verdict = refuted`、`promotable = false`。**没有任何一个判据臂摸到 +0.005 的 partial 线**，更不用说 +0.02 的 confirm 线。
|
### 四、`ε_Onsager` sanity check：这正是 Kirkwood g 的实测指纹
| 化合物 | T / K | μ / D | α / A³ | ε 观测 | ε_Onsager | 比值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| water | 273.15 | 2.287 | 1.397 | 87.00 | 46.84 | 0.538 |
| methanol | 298.15 | 1.987 | 3.196 | 39.25 | 17.81 | 0.454 |
| formamide | 303.15 | 1.054 | 4.120 | 106.14 | 4.79 | 0.045 |
| n-methylacetamide | 303.15 | 1.472 | 7.554 | 178.47 | 5.21 | 0.029 |
| dimethyl sulfoxide | 283.15 | 4.620 | 7.857 | 50.58 | 51.87 | 1.026 |
| acetonitrile | 293.15 | 3.872 | 4.362 | 37.70 | 54.12 | 1.435 |
|
- 质子性缔合液（水、甲醇、甲酰胺、NMA）比值 **≪ 1**（g ≫ 1）；非质子液（DMSO、乙腈）比值 **≥ 1**。这条反号分裂就是 `onsager_analytic_only` 跨种子端点 **−0.5160011378298242** 的来源：单分子量在中性非质子液上尚可，在缔合液上系统性低几个数量级。
- 计分池里 ε > 60 有 **13** 行，Onsager 覆盖其中 **1** 行。
|
### 五、安慰剂：如实登记一处**未达标**
- 目标在计分化合物上打乱后：`reference_direct` 跨种子均值 **0.5236384736868015**（较冻结端点低 **6.248e-02**，说明置换确实动了标签）、`onsager_delta_xgb` **0.09304306318408645**、`onsager_delta_recomputed` **0.1231841698291171**；`verdict = placebo`。
- **未达标处**：预注册写明的安慰剂模型是「每个 Δ 臂必须**塌回直接臂**」。实测 Δ 臂并没有收敛到参考臂（0.5236384736868015），而是**掉到参考臂以下**（−0.43059541050271505 / −0.4004543038576844）。即安慰剂下 Δ 变换不只是「无益」，而是**破坏性**。该偏离**照实登记，不解释成合格**；它意味着这条臂的安慰剂对照不像预注册假设的那样是「优势归零」，而更像「解析项本身带噪声」。
|
### 六、判定与边界
- **verdict = `refuted`**、`promotable = false`。冻结基线 `0.4091179943351143` 与冻结头条 `0.4766400383507876` 未动；W18 主记分牌尝试 **0 次**，累计 **11 次**不变。
- 本枪只换目标，池 / 折 / 计分器 / 表示全冻；`reference_direct` 逐位复现证明协议无漂移，故负结论可归因于「Onsager 形式的先验在本池上不携带可迁移信息」，**不是实现错误**。
- 与已有先例同向：`reports/week8_c4_onsager_delta.md` 在另一池、另一协议（MAE / RepeatedKFold）上也观察到 Δ 层输给直回（8.54 vs 6.36 MAE）。两枪在两个池上同向 ⇒ **Δ-learning 这条物理射击在 ε 上已被打掉**。
- 产物：`probes/dielectric_onsager_delta_w18.py`、`probes/dielectric_onsager_delta_w18_prereg.json`、`probes/dielectric_onsager_delta_w18_summary.json`、`probes/dielectric_onsager_delta_w18_placebo_summary.json`、`probes/artifacts/dielectric_onsager_delta_w18_repeats.csv`、`probes/artifacts/dielectric_onsager_delta_w18_folds.csv`、`reports/dielectric_onsager_delta_w18.md`、`reports/dielectric_onsager_delta_w18_placebo.md`、`tests/test_dielectric_onsager_delta_w18.py`。
- `wall_seconds = 2095.7947824000003`（`--jobs 2`）。
|
