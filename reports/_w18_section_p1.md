## 28.43 W18-P1 多种子端点升级：四臂跨种子端点 0.4014 / 0.4484 / 0.4375 / 0.4540，冻结头条 0.4766 被证实是五种子中的最大单抽（2026-09-28）
|
**性质（必须明说）**：本 lane **不换模型、不拟合新模型族、不加任何信息**，只把「端点」的口径从 **seed 42 单次抽样** 改成「**跑前锁定的五种子**（42, 1234, 2026, 31337, 7）上、每种子 10 重复 R² 均值的算术平均」。它回答的是 W17 遗留的一处口径问题：冻结头条 `0.4766400383507876` 究竟是一个稳定的臂，还是一个走运的种子。
⇒ 它**不产出新主臂**：预注册 `decision_rule.promotes_no_reading = true` 写明「它只能从端点定义里去掉种子方差，本身不增加信息、也不可能单靠它把任何臂抬过目标」，故 `promoted = false`、`shots = 0`（W18 累计主记分牌尝试 **11 次不变**）。
|
**预注册**：`probes/dielectric_multiseed_endpoint_prereg.json`，`status = locked_before_run`，`locked_at_utc = 2026-09-27T14:10:00Z`（早于起跑 `15:06:14Z`）；**原始字节 sha256 = `3516befd25cf6ff9258f1d1d678786915504ac5a6c0fbd5529b75514a2313083`**（2573 字节、纯 LF、无 BOM），已作为字面量钉进 `tests/test_multiseed_endpoint.py`。
**四臂**：`baseline`（Morgan+Physical，物理块 13 列）/ `plus_lever4`（加 conformer-average 偶极迁移）/ `plus_lever8`（加 5 列 Li+ 配位块）/ `plus_both`（lever4 + lever8，即冻结头条臂）。
**端点规则（逐字）**：`the endpoint for any arm is the arithmetic mean of its per-seed 10-repeat R2 means over the pre-locked five-seed set; the seed-42 value is reported beside it as a single-draw reading, never alone`（`endpoint_rule`）。
|
**第一步·锚点先复现（先复现再报任何新数）**：四臂 seed 42 逐位复现冻结记分牌读数 `0.4091179943351143` / `0.4649564468823552` / `0.4531768105508106` / `0.4766400383507876`，`abs_gap` 全 `0.0`（容差 `1e-09`）⇒ `anchors.reproduced = true`。
|
**第二步·实测（跨种子均值 = 端点，本节核心数字）**：

| 臂 | seed 42（单抽） | 跨种子端点 | sd |
| --- | ---: | ---: | ---: |
| `baseline` | 0.4091179943351143 | **0.40135270382650734** | 0.02394435067835822 |
| `plus_lever4` | 0.4649564468823552 | **0.44840711903316777** | 0.01583870809667547 |
| `plus_lever8` | 0.4531768105508106 | **0.4374976919688038** | 0.017411299602092544 |
| `plus_both` | 0.4766400383507876 | **0.45401075998423623** | 0.01462722417311012 |

- `best_arm = plus_both`（端点 `0.45401075998423623`）；`target_r2 = 0.60`、`target_met_cross_seed = false`——**四臂的 `cross_seed_max` 全部落在自己的 seed 42 上，`above_060_seeds` 四臂皆 0/5**（0.454 距 0.60 很远）。
|
**最重要的一条诚实披露（不许省略）**：`plus_both` 的 `cross_seed_max` **恰好等于** seed 42 的 `0.4766400383507876` ⇒ **冻结头条那个数是五个种子里最大的一个单抽**；在锁定的跨种子端点口径下，**同一臂的诚实读数是 `0.45401075998423623`**（比头条低 0.0226）。
- 冻结头条仍**原位保留**（它是冻结记分牌读数，永不与基线互比、也永不与本 lane 的端点互比）；但**任何引用 `0.4766400383507876` 的地方都必须同时说明：它是 seed-42 单抽，其跨种子端点是 `0.45401075998423623`**。
- `cross_seed_mean` 与 `seed_42` 是两种口径，`endpoint_rule` 与预注册 `restrictions[2]` 都写明**两者永不互减**。
|
**符号稳健性（杠杆方向是否靠运气）**：`plus_both − baseline` 在 **5/5 个种子上都为正**：
- seed 42：`0.0675220440156733`
- seed 1234：`0.06719383048427285`
- seed 2026：`0.031659711999165674`
- seed 31337：`0.0704559453827242`
- seed 7：`0.026458748906808216`
- 跨种子均值差 `cross_seed_mean_minus_baseline = 0.052658056157728894`（对比冻结的单种子差 `0.0675220440156733`）⇒ **杠杆符号稳、幅度被种子 42 抬高**（全期最小的正差也还有 +0.02646）。
|
**折数门禁（不是只写 clean）**：`leakage.clean = true`，且 `leakage.by_seed_arm` 的 **20 个 (seed, arm) 格子**每个都记录 `folds = 50`、`folds_with_a_straddling_compound = 0`、`max_straddling_compounds_in_a_fold = 0`。
- 收口时给测试补了**两条门禁**并留证：① `test_every_seed_arm_pair_covers_all_fifty_folds` 逐格子断言 `folds == 50`（原门槛只能看见「跨折化合物」，`drop_thin_folds` 静默丢折它看不见）；② `test_the_preregistration_bytes_are_pinned_by_sha256` 把预注册 sha256 作为字面量钉死（LF / 无 BOM 同断言），事后改动任何字段——**包括未注册字段**——都会让测试变红。
- 折签名注：本仓的「GroupKFold by InChIKey」实为**自研按 InChIKey 整组轮转分折**（性质 = 同一化合物不跨折），**不是** sklearn 的 `GroupKFold`；引用时不要写错。
|
**池（回归守卫）**：`scored_rows = 457`、`scored_compounds = 97`、**`training_rows = 457`**（`!= 2029`）。
- 这是该 lane 首次运行的实测缺陷留下的守卫：探针最早按 shot-13 的 `full_base`（2029 行全表）配置训练，却声称复现四臂的 scored 池锚点，seed 42 会打印 `0.530029` 而不是 `0.409118`；要不是 `pool.training_rows == 457` 这条断言，整轮数小时的扫描会在事后才被扔掉。**2029 行全表没有进过训练侧**，测试逐字断言这一点。
|
**verdict = `endpoint_upgraded`**（锚点逐位复现，端点口径升级成立），`promotion.promoted = false`。
- 冻结头条 `frozen_headline_unchanged_r2 = 0.4766400383507876`、冻结基线 `frozen_baseline_unchanged_r2 = 0.4091179943351143` **原位未动**；本 lane **零次主记分牌尝试**（W18 累计 11 次不变）。
- **照实记三条边界**：
  1. 本 lane **不改任何模型、不拟合新族**，只换端点口径，所以**过门与否都不构成增益**——它甚至没有「过门」这个出口（`target_met_cross_seed = false`）。
  2. 跨种子差异里**仍混有折难度**：预注册未声明 placebo，本 lane **没有安慰剂臂**，故「符号 5/5 为正」只能说杠杆方向不靠 seed 42 的运气，**不能说**折难度已被排除。
  3. `shots = 0`、`models_fitted_here = 20`（四臂 × 五种子），`n_splits = 5`、`n_repeats = 10`；`wall_seconds = 4702.12`、`jobs = 4`。
- 产物：`probes/dielectric_multiseed_endpoint.py`、`probes/dielectric_multiseed_endpoint_prereg.json`、`probes/dielectric_multiseed_endpoint_summary.json`、`probes/artifacts/dielectric_multiseed_endpoint_repeats.csv`、`reports/dielectric_multiseed_endpoint.md`、`tests/test_multiseed_endpoint.py`。
|
**数字出处**（`值 ← 文件::JSON 键`）：
- 0.4091179943351143 ← `probes/dielectric_multiseed_endpoint_summary.json::anchors.rows[0].measured`（亦 `frozen_baseline_unchanged_r2`）
- 0.4649564468823552 ← `probes/dielectric_multiseed_endpoint_summary.json::endpoints[1].seed_42`
- 0.4531768105508106 ← `probes/dielectric_multiseed_endpoint_summary.json::endpoints[2].seed_42`
- 0.4766400383507876 ← `probes/dielectric_multiseed_endpoint_summary.json::endpoints[3].seed_42`（亦 `frozen_headline_unchanged_r2`、`promotion.frozen_headline`）
- 0.40135270382650734 ← `probes/dielectric_multiseed_endpoint_summary.json::endpoints[0].cross_seed_mean`（sd ← `endpoints[0].cross_seed_sd`）
- 0.44840711903316777 ← `probes/dielectric_multiseed_endpoint_summary.json::endpoints[1].cross_seed_mean`（sd ← `endpoints[1].cross_seed_sd`）
- 0.4374976919688038 ← `probes/dielectric_multiseed_endpoint_summary.json::endpoints[2].cross_seed_mean`（sd ← `endpoints[2].cross_seed_sd`）
- 0.45401075998423623 ← `probes/dielectric_multiseed_endpoint_summary.json::endpoints[3].cross_seed_mean`（sd ← `endpoints[3].cross_seed_sd`；亦 `best_arm.cross_seed_mean`）
- 0.052658056157728894 ← `probes/dielectric_multiseed_endpoint_summary.json::endpoints[3].cross_seed_mean_minus_baseline`
- 逐种子差值 ← `endpoints[3].seed_values[s] − endpoints[0].seed_values[s]`，s ∈ {42, 1234, 2026, 31337, 7}（本节五条精确值均由该键逐位相减得到，全为正）
- 50 折 × 20 格 ← `probes/dielectric_multiseed_endpoint_summary.json::leakage.by_seed_arm`（每个 (seed, arm) 格子的 `folds`）
- 457 / 97 ← `probes/dielectric_multiseed_endpoint_summary.json::pool.scored_rows` / `pool.scored_compounds`；训练行 ← `pool.training_rows`
- `endpoint_upgraded` ← `probes/dielectric_multiseed_endpoint_summary.json::verdict`；`promoted = false` ← `probes/dielectric_multiseed_endpoint_summary.json::promotion.promoted`
- sha256 `3516befd25cf6ff9258f1d1d678786915504ac5a6c0fbd5529b75514a2313083` ← `probes/dielectric_multiseed_endpoint_prereg.json` 原始字节（`hashlib.sha256`，2573 字节，无 BOM、纯 LF）
|
