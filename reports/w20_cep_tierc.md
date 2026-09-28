# W20-6c CEP 8.8 万 DFPT：句柄不可核（not_verifiable），只能进 Tier C

- **任务** `week20_w20_6c_cep_tierc`｜**节号** §28.62｜**日期** 2026-09-28
- **性质**：**不下任何行、不拟合任何模型、不占 shot 编号、不产任何通道读数、不动任何冻结件**；`produces_reading = false`、`promoted = false`、`shot_number_taken = null`、`scoreboard_attempts_delta = 0`、`reaxys_values_used = 0`、`models_fitted = 0`、`main_scoreboard_untouched = true`。
- **权威输入**：`reports/week20_project_charter.md` §1 `W20-6c`。
- **机器可读产物**：`probes/w20_cep_tierc_prereg.json`（跑前锁定）、`probes/w20_cep_tierc_summary.json`（跑后落盘）；**无逐行产物**（源拿不到，不编造表）。

## 1. 屏幕结论

**verdict = `not_verifiable`，tier = `C`（唯一允许的档位）。** 句柄「CEP 8.8 万 DFPT」（约 88,000 条 DFPT 计算的介电常数，被举为「ε 的 QM9 等价物」）在本仓**无法落成具名数据集**：既无可绑定的 DOI、仓库记录、具名数据集，也**许可文本**与**逐行表/图索引**都拿不到，而本探针**不发任何网络请求**（`screen_inputs` 五个字段全部为 `null`）。因此许可判词**读不出**，源**不得导入**。

要点是无**法核**，不是「已知受限」：不是行被许可挡住，而是**源本身无法钉死到能读许可、能定位某一行的程度**。在判据上二者都等于**不可采**，但陈述必须分开写。

## 2. 物理理由：气相计算 ε 与液相实验 ε 不是同一个量（永远只能 Tier C）

即便明天句柄落成，它也**永远不会破上限**，理由是物理而非许可。**气相 DFPT 计算的 ε 与液相实验的 ε 是两个不同的量**：液相值带**取向相关**，单分子计算没有。Kirkwood 把两者用 g 因子连起来：

    (ε − 1)(2ε + 1) / (9ε) = (4πN / 3) · (α + μ² g / (3 k T))

气相里 **g = 1 是构造性的**，所以计算得到的是「分子极化率披着介电常数的皮」，**不是**本仓要预测的体相液相数。故此类集合只能作 **Tier C**（特征 / 描述符 / 排序信号）进入，**永远不能**作液相实验靶的标签。这与立项章对一切计算值的规则一致（本仓的 DFT 只在轨道通道作**标签**，因为那里的被测量就是计算量本身；ε 的被测量是液相实验值，不是气相计算值）。

## 3. 判据（跑前钉）

- **可判定规则**：句柄须先落成**具名数据集 + 开放许可文本 + 逐行表/图定位**，才允许导出一行；否则 verdict = `not_verifiable`，上限为 **Tier C**。
- **档位规则**：气相计算 ε 与液相实验 ε 不同量（缺取向相关 g），故只能进 Tier C。
- **许可判词域**：`open` / `attribution_required` / `restricted` / `unknown` / `not_verifiable`；本件判 `not_verifiable`。

## 4. 照实登记「不可核」

- **无许可判词**：`licence_verdict = not_verifiable`；无 DOI / 具名数据集 / 许可文本 / 定位可登记。
- **无行级分类**：`row_level_classification.status = source_not_verifiable`，三档计数均 **0** —— 不是「跑了但三档都空」，是**拿不到源、故一行都没分类**。`row_count = 0`、`rows_artifact = null`。
- **不破上限**：`ceiling_break = false`；ε 标签上限 **161 → 157 → 153** 不动。
- **未做网络请求**：本件不发请求、不写 `data/`，只写 `probes/` 两个自级产物与 `reports/` 一份报告。

## 5. 纪律

- `promoted = false`、`produces_reading = false`、`shot_number_taken = null`、`scoreboard_attempts_delta = 0`、`reaxys_values_used = 0`、`models_fitted = 0`。
- 主记分牌本周 **0 次尝试**，累计 **11 次不变**。
- **不引用任何 Reaxys 数值**；**不为 ε 购买或抓取任何受限库**。
- 判不清处一律写 `not_verifiable`，**不猜**。

