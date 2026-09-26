# L3 回溯验证「阶段一试点」——介电通道 · 池内 · EC/PC

> **`stage_1_pilot_not_a_verdict`**：**这不是判决**。本试点只跑介电通道、只在名册内池上做、
> 只报 EC/PC 两条。预注册 `stage_1_pilot.verdict_eligible = false`；L3 的真实判决要
> 四通道齐活（`criteria.pass_expression = C1 and C2_solvent and C2_additive and C3`），
> 本文件不得作为 L3 结论引用，不得进入任何对外文本。

**产物**

| 文件 | 内容 |
| --- | --- |
| `probes/l3_stage1_pilot.py` | CLI：先落盘池、再评分、最后写汇总 |
| `probes/l3_stage1_pilot_pool.csv` | 冻结池（236 行，LF，先于任何评分落盘） |
| `probes/l3_stage1_pilot_detail.csv` | 236 行明细（预测 ε / 三态适用域标志 / 是否冠军 / 是否进 top-20 / 折号聚合口径） |
| `probes/l3_stage1_pilot_summary.json` | 机读汇总（含回归锚点与四层排除自证） |

**依据**：`probes/l3_backvalidation_prereg.json`（`status = LOCKED`，
`locked_at_utc = 2026-09-25T19:38:49Z`）。七个锁定常量本轮一字未改（见 §6 与
`tests/test_l3_stage1_pilot.py::test_the_seven_locked_constants_are_untouched`）。

## 1 目的

把预注册里的「排除冠军之后，已知冠军还能不能被排回各自清单前列」从叙事变成可判定的实验，
但**只跑其中一条腿**：介电通道、池内、EC/PC。目的是在四通道齐活之前，先把这四个问题
一次钉死：池能不能先落盘、冻结配方能不能被逐位复现、排除是不是只落在训练侧、
读数口径有没有走样。C3（标签置换负对照）与 C2_additive（氧化还原门）本轮**不跑**。

## 2 池定义与 sha256

| 项 | 值 |
| --- | --- |
| 池路径 | `probes/l3_stage1_pilot_pool.csv` |
| 行数 | **236** |
| sha256（原始字节 = 规范化文本，两者一致 ⇒ 纯 LF） | `b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18` |
| `pool_size_by_list` | `{"solvent": 236}` |
| 先落盘后评分 | `pool_frozen_before_scoring = true`（**自述值 self-attested**，见下注） |
| 列 | `list, inchikey, name, smiles, T_K, target_dielectric, model_ready, is_champion, champion_short, pilot_label` |

纳入口径：`data/processed/dielectric_physical_features_v03.csv` 中
`model_ready = true`（对 `data/dielectric_v03.csv` 名册取闸）且 xTB 物理特征成功的行，
即冻结配方真正能出数的 **236 行**，顺序就是冻结的 236 行顺序。
`min_scored_per_list = 100`，236 ≥ 100，规模闸过。

**「先落盘后评分 = true」是自述值（self-attested），不是独立可验证的证据。** 它的旁证只有两条：(i) 池文件与汇总文件的 mtime 先后顺序；
(ii) `tests/test_l3_backvalidation_prereg.py` 的池闸门 —— 而该闸门**自身承认**（见其 docstring）它只能证明池**曾被落盘且规模达标**，
**不能**证明「冻结早于看到冠军名次」。因此后一条**仍只靠纪律**（纳入口径不得以冠军排名为条件）；上表里的 `true` 是脚本自报的值，不得当作已证事实。

**名册限制的如实声明**：仓库内没有任何「SMILES→ε」的正式预测入口，名册外 SMILES 会被
`probes/dielectric_representation_ablation.py` 的名册检查直接 `ValueError`。按预注册
`current_state_2026_09_26.gating_items_before_the_full_run` 第 3 条的备选方案执行：
**池限制为名册内并如实声明**。本轮没有新建 SMILES→ε 入口，没有接 xTB。

四个冠军在池里的状态：

| 冠军 | InChIKey | 在池内 | 说明 |
| --- | --- | --- | --- |
| EC | `KMTRUDSVKNLOMY-UHFFFAOYSA-N` | 是 | `model_ready = true`，普通成员 |
| PC | `RUOJZAUFBMNUDX-UHFFFAOYSA-N` | 是 | `model_ready = true`，普通成员 |
| FEC | `SBLRHMKNNHXPHG-UHFFFAOYSA-N` | 否 | `model_ready = false`，本就在冻结拟合集外 |
| VC | `VAYTZRYEBVHVLE-UHFFFAOYSA-N` | 否 | `model_ready = false`，本就在冻结拟合集外 |

## 3 折号与种子

| 项 | 值 |
| --- | --- |
| 折方案 | `RepeatedKFold(n_splits=5, n_repeats=10, random_state=42)` |
| 种子方案 | `42 + 全局折号`（全局折号 0–49） |
| 折几何先例 | `probes/dielectric_leave_ec_out_sensitivity.py`（预注册 `fold_and_seed.fold_policy` 指定的那一份） |
| 冠军处置 | 冠军从**每一折的训练侧**剔除；冠军本身仍按原折号做样本外评分 |
| 折号聚合口径 | `mean_over_the_10_out_of_fold_repeat_predictions`（10 次重复的样本外预测取等权平均） |
| 同分裁决 | InChIKey 字典序升序 |

50 折 × 10 重复的几何**逐位不变**，只有冠军行的训练侧被删。自证写在
`summary.exclusion.audit`：EC / PC 各被从 **40** 折的训练侧剔除、
各在 **10** 折里被作为样本外预测（每重复恰好 1 次）；剔除后单折训练行数
**186–
189**。

## 4 读数表（介电通道 · solvent 清单 · 池内 236）

排序读数=冻结口径：**Morgan+Physical**，`target_mode = log_epsilon_minus_one`，
两个分量各自先逆变换回 raw ε 再 `0.5*(morgan + physical)`，预测裁剪到 ε ≥ 1，
方向=预测 ε 越高越好。适用域闸门取 `src/electrolyte_ml/applicability.py`
（`pred < 1 → outside_nonphysical`；`donor_count ≥ 1 → outside_associated_liquid`；
否则 `inside_domain`）。

### 4.1 C1（K = 20）——**未命中**

清单内 236 个成员按预测 ε 排序：

| 冠军 | 名次 | 预测 ε | 三态适用域标志 | 进 top-20？ | 真值 ε |
| --- | ---: | ---: | --- | --- | ---: |
| EC | **24** | 23.0565 | `inside_domain` | 否 | 90.5 |
| PC | **58** | 17.0438 | `inside_domain` | 否 | 64.9 |

**命中数 0 / 2**（介电通道 solvent 清单；预注册全量要求是 4/4，
含氧化还原通道的 FEC/VC）。**命中即命中、未命中即未命中**：EC 第 24 名、
PC 第 58 名，都在 K = 20 之外，不写成「接近前 20」。

完整 top-20 名单（方向：预测 ε 降序；本试点池规模 236）：

| 名次 | 化合物 | InChIKey | 预测 ε | 三态适用域标志 | 冠军 |
| ---: | --- | --- | ---: | --- | --- |
| 1 | triethanolamine lactate | `RJQQOKKINHMXIM-UHFFFAOYSA-N` | 47.3343 | `outside_associated_liquid` | — |
| 2 | 2-aminoethan-1-ol | `HZAXFHJVJLSVMW-UHFFFAOYSA-N` | 39.7661 | `outside_associated_liquid` | — |
| 3 | 1,2-propanediol | `DNIAPMSPPWPWGF-UHFFFAOYSA-N` | 38.6572 | `outside_associated_liquid` | — |
| 4 | triethanolammonium acetate | `UPCXAARSWVHVLY-UHFFFAOYSA-N` | 36.6622 | `outside_associated_liquid` | — |
| 5 | ethanolammonium nitrate | `LZJIBRSVPKKOSI-UHFFFAOYSA-O` | 34.3929 | `outside_associated_liquid` | — |
| 6 | 1,2-ethanediol | `LYCAIKOWRPUZTN-UHFFFAOYSA-N` | 32.2031 | `outside_associated_liquid` | — |
| 7 | 2-hydroxyethylammonium lactate | `NEQXUPRFDXNNTA-UHFFFAOYSA-N` | 32.1455 | `outside_associated_liquid` | — |
| 8 | butanenitrile | `KVNRLNFWIYMESJ-UHFFFAOYSA-N` | 30.5699 | `inside_domain` | — |
| 9 | dimethylformamide | `ZMXDDKWLCZADIW-UHFFFAOYSA-N` | 29.9786 | `inside_domain` | — |
| 10 | 2-hydroxyethylammonium acetate | `VVLAIYIMMFWRFW-UHFFFAOYSA-N` | 29.5180 | `outside_associated_liquid` | — |
| 11 | glycerol | `PEDCQBHIVMGVHV-UHFFFAOYSA-N` | 27.6278 | `outside_associated_liquid` | — |
| 12 | Acetonitrile | `WEVYAHXRMPXWCK-UHFFFAOYSA-N` | 26.7650 | `inside_domain` | — |
| 13 | hexanedinitrile | `BTGRAWJCKBQKAO-UHFFFAOYSA-N` | 26.7538 | `inside_domain` | — |
| 14 | N-(2-hydroxypropyl)-2-hydroxy-1-propanamine | `LVTYICIALWPMFW-UHFFFAOYSA-N` | 25.5409 | `outside_associated_liquid` | — |
| 15 | Crotononitrile (bp 108 C) | `NKKMVIVFRUYPLQ-NSCUHMNNSA-N` | 25.4991 | `inside_domain` | — |
| 16 | 1-(2-hydroxyethyl)-3-methylimidazolium tetrafluoroborate | `KLTUZFZUYLXTFF-UHFFFAOYSA-N` | 24.4486 | `outside_associated_liquid` | — |
| 17 | 1-butyl-3-methylimidazolium thiocyanate | `SIXHYMZEOJSYQH-UHFFFAOYSA-M` | 23.6811 | `inside_domain` | — |
| 18 | 2-amino-2-methylpropan-1-ol | `CBTVGIZVANVGBH-UHFFFAOYSA-N` | 23.6718 | `outside_associated_liquid` | — |
| 19 | Xylitol | `HEBKCHPVOIAQTA-NGQZWQHPSA-N` | 23.5982 | `outside_associated_liquid` | — |
| 20 | pentanedinitrile | `ZTOMUSMDRMJOTH-UHFFFAOYSA-N` | 23.5888 | `inside_domain` | — |

值得一并记下的事实：这 20 个里 **13** 个
被适用域闸门判为 `outside_associated_liquid`——闸门认为它们本身就不在本模型的适用域内。
名册内 236 行的闸门分布：`inside_domain` 167、
`outside_associated_liquid` 69、
`outside_nonphysical` 0。

### 4.2 C2_solvent（`|Δlog10(ε)| ≤ 0.1`）——**未过**

| 冠军 | 预测 ε | 真值 ε（预注册钉死） | Δlog10 | \|Δlog10\| | 过门？ |
| --- | ---: | ---: | ---: | ---: | --- |
| EC | 23.0565 | 90.5 | -0.5939 | 0.5939 | 否 |
| PC | 17.0438 | 64.9 | -0.5807 | 0.5807 | 否 |

两条都在同一侧、且都低约 0.58–0.59 个 log10 单位（约 −74%）。这不是「勉强擦边」：
比 0.1 的门宽了约 5.8 倍。

### 4.3 C3 与 C2_additive——**本轮不跑**

| 判据 | 状态 | 理由 |
| --- | --- | --- |
| C3_negative_control | `c3_not_run_stage_1_pilot` | 标签置换对照属四通道完整跑批（种子 20260928，命中上限 1） |
| C2_additive | `not_run_stage_1_pilot_redox_channel_not_executed` | FEC/VC 是氧化还原通道的添加剂清单冠军，本试点只跑介电通道 |

## 5 温度诚实性

| 冠军 | 冻结表 `T_K` | 预注册 `truth_T_K` | 一致？ |
| --- | ---: | ---: | --- |
| EC | 313.15 | 313.15 | **一致** |
| PC | 298.15 | 298.15 | **一致** |

两条都一致：EC 的真值 90.5 是 **313.15 K** 下的值（`temperature_band = extended_temperature`），
PC 的真值 64.9 是 **298.15 K** 下的值（`temperature_band = room_temperature`）。
本轮实际用的就是冻结表里的 `T_K`（它同时是物理特征 `PHYSICAL_COLUMNS` 里的一列，
直接进模型），所以「预测 ε 与真值 ε 温度不同」这条风险在 EC 上**确实存在**：
模型看到的是 313.15 K 的 EC，真值也记在 313.15 K——两者同温，但 313.15 K 本身在
近室温窗口之外，这也是 `probes/dielectric_leave_ec_out_sensitivity.py` 存在的理由。
**没有发现冻结表与预注册真值温度不一致的情形。**

## 6 与冻结基准的对照（回归锚点）

正确性证明：用本实现跑一次「全名册（236 行）、不排除任何冠军」的样本外预测，
与既有冻结产物对齐。锚点是 `probes/v032_target_scaffold_summary.json`
（**主参照**，本试点实际调用的就是它那条 `fit_predict` 管线）与
`probes/v032_ablation_summary.json`（**交叉参照**）。

- **主参照：逐值完全一致，最大绝对差 = 0**（容差 1e-09），
  6 条臂 × 9 个指标全中。
- **逐行预测**：与 `data/processed/v032_target_scaffold_predictions.csv` 的
  **14160** 个存盘字符串（6 臂 × 236 行 × 10 重复）**逐字符一致**，失配
  0 个。
- 度量口径细节：冻结汇总的平均值是对**先按 `%.12g` 落盘再读回**的每重复指标求平均
  （`_run_random_cv` 写 `f"{value:.12g}"` 行、`_summarize` 读回求平均）。本实现采用同一口径，
  否则会在 10 次重复上留下约 5e-8 的差。

| 目标变换 | 表征 | MAE（本实现） | MAE（冻结） | RMSE（本实现） | R²（本实现） | 最大绝对差 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `raw` | Morgan | 7.612386 | 7.612386 | 16.583923 | 0.240198 | 0 |
| `raw` | Physical | 7.097620 | 7.097620 | 15.421840 | 0.342234 | 0 |
| `raw` | Morgan+Physical | 6.686173 | 6.686173 | 15.176208 | 0.363573 | 0 |
| `log_epsilon_minus_one` | Morgan | 7.320659 | 7.320659 | 17.161729 | 0.186721 | 0 |
| `log_epsilon_minus_one` | Physical | 6.372718 | 6.372718 | 16.031670 | 0.289758 | 0 |
| `log_epsilon_minus_one` | Morgan+Physical | 6.272733 | 6.272733 | 16.002903 | 0.292760 | 0 |

**必须单列的冲突**：两份被点名的冻结锚点**彼此**不一致——raw Morgan+Physical 上
最大互相差 **5.28e-08**，而 Morgan / Physical 两臂只差约 1e-11。
差异来自更早的 ablation 跑批在集成两个分量时多做了一次 float32 舍入
（两份各自存的逐行 raw Morgan+Physical 预测最大差 1.91e-06）。
因此**任何单一的 1e-9 容差都不可能同时覆盖两者**。本试点按更保守的一侧处理：
对主参照要求**逐值精确**（≤ 1e-9，实测 0），对交叉参照只报实测差并给 1e-6 的上界，
**没有改动任何锚点数字，也没有把容差静默放宽**。

## 7 排除四层与「四个冠军」的不对称

| 层 | 预注册 | 本轮实现 |
| --- | --- | --- |
| L1 训练集 | 任何拟合的训练行不得含任一冠军 | EC/PC 从 50 折中每一折的训练侧剔除；冠军仍按原折号做样本外评分。**FEC/VC 无需额外剔除**——它们 `model_ready = false`，本就在冻结拟合集外 |
| L2 特征构造 | 不得用冠军标签派生的特征 | 特征只有 Morgan count（radius 2，2048）与 13 维冻结物理列；无 target encoding、无冠军均值、无冠军近邻 |
| L3 选择环节 | 超参数/特征子集/早停不得看冠军 | `XGB_PARAMS`、特征集、种子、200 轮无早停全部是冻结前既定值 |
| L4 评分路径 | 冠军走与其他池成员完全相同的代码路径 | 冠军与其余 234 行调用同一次 `fit_predict`、同一折聚合；`is_champion` 列只进产物，不进评分路径 |

**不对称必须写明**：真正做了额外剔除的只有 **EC 与 PC 两个**；FEC 与 VC 因为
`model_ready = false` 本来就不在冻结介电拟合集里，**没有**为它们做留一。
**这不是「四个都做了留一」。**

## 8 这不是判决

`stage_1_pilot_not_a_verdict`。本试点只覆盖介电通道的 solvent 清单，
C3 与 C2_additive 明确未跑，预注册的合取式
`C1 ∧ C2_solvent ∧ C2_additive ∧ C3` 因此**无法**被本轮任何数字满足或否定。
本文件、`probes/l3_stage1_pilot_summary.json`、明细 CSV 与池 CSV 都带该标签；
不得引用为 L3 结论，不得进入对外文本。

## 9 未决风险与存疑

1. **读数口径的二义性**：预注册 `pool_rule.solvent_list_readout` 的
   「排序读数为 log(epsilon-1) 物理表征输出」本试点读作「`target_mode = log_epsilon_minus_one`
   的 Morgan+Physical 集成、回变换到 raw ε 排序」。若把排序改到 **raw** 目标
   （诊断臂），排名会变成 EC 第 12 名、PC 第 41 名，
   仍然 0/2 进前 20。也就是说**两种读法都不通过 C1**；但 raw 臂只作诊断记录，
   **不是** C1 的读数，不得用它改写 C1。
2. **池是名册内池**，236 行，非「全部可用溶剂」。这符合预注册的备选方案，
   但它意味着洗牌结构偏向已有名册，不能外推到名册外分子。
3. **两份冻结锚点彼此差 5.3e-8**（见 §6）。本试点选择与
   `v032_target_scaffold_summary.json` 精确对齐；若将来以
   `v032_ablation_summary.json` 为准，需要先解释那次 float32 集成差异。
4. **预测偏高 ε 的分子偏保守**：top-20 里 13 个被适用域闸门判为
   `outside_associated_liquid`。按闸门口径，这些「高 ε」预测本身就在域外，
   C1 若在这类池上做，名次的可解释性有限。
5. **EC/PC 被剔出训练侧后**，两者的样本外预测都比不去除时更低
   （EC 从第 14 名退到第 24 名、PC 从第 43 名退到第 58 名），
   说明冻结配方的高 ε 区几乎全靠同桌的少数高 ε 行撑住。这是本轮最有价值的观察，
   但它指向的是「介电通道在留出外推上的能力」，**不是**对 L3 漏斗的判决。
