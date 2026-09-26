# ILThermo 结构解析报告：58 个"名录外"化合物到底能不能进覆盖率清单

**一句话结论：ILThermo 那 76 个纯化合物 100% 是离子液体；58 个名录外化合物里 29 个（50%）拿到了 InChIKey，
其中 27 个通过分子式核对、2 个被核对拦下；而温度维度上 109 个数据集只有 1 个真正随温度变化
（[P66614]Cl，208.15–283.15 K，15 点，Kottummal 2018）。所以这条线对"化合物覆盖"有条件的用，
对 v1.x 的"温度扩展"基本没用。**

复现：

```
.\.venv\Scripts\python.exe probes\ilthermo_structure_resolution.py
.\.venv\Scripts\python.exe probes\ilthermo_structure_resolution.py --facts-from probes\ilthermo_structure_resolution_summary.json
.\.venv\Scripts\python.exe -m pytest tests\test_ilthermo_structure_resolution.py -q
```

---

## 一、这一步补的是什么洞

上一份报告（`reports/ilthermo_probe.md`）已经确认：ILThermo 有 116 条 `Relative permittivity` 数据集、
76 个纯化合物、其中 58 个不在 `data/dielectric_v03.csv` 名录里。但同时确认了硬伤：
**ILThermo 不提供 CAS、不提供 SMILES、不提供 InChIKey**——只有名字、分子式和一张结构图键。
没有机器可读标识的化合物进不了覆盖率曲线，所以本步用 PubChem PUG-REST 的名称反查把这个洞补上：

- 入口：`https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/property/SMILES,InChIKey,MolecularFormula/JSON`
- 清单：只查"按归一化名字不在名录里"的 58 个（名录内的 18 个直接用名录自己的 InChIKey，省请求也更可信）
- 礼貌性：UA 自报、每次调用间 sleep 0.35 s、`429`/`5xx` 按服务器提示退避（上限 45 s）、硬预算 120 次
- 本次实跑：**PubChem 59/120 次**（200 ×29、404 ×30）、**ILThermo ilset 109/130 次**、失败 0、总字节 148,982

三条诚实性规则是写在代码里的，不是写在文档里的：

1. **分子式相同永远不算命中**。同分异构体共享分子式，所以公式命中只记为碰撞标记并转人工。
2. **名录归属由 InChIKey 决定**，归一化名字只作次要通道。
3. **读不到就写原因**：HTTP 状态、传输失败、歧义都原样落进 `notes`，绝不继承一个"看起来合理"的 InChIKey。

公式核对和温度列都来自同一批 `ilset` 载荷（109 条全部读到），不是靠抽样假设。

---

## 二、结果

| 口径 | 数量 |
| --- | --- |
| 纯化合物 | 76 |
| ε 数据集 / 数据点 | 109 / 1,092 |
| 按名字在名录内 | 18（其中 3 条 roster 自带 `out_of_scope_ionic_or_organometallic`） |
| 按名字在名录外（要解析的） | 58 |
| **解析成功（resolved）** | **29（50%）** |
| 解析失败（unresolved） | 29（全部是 HTTP 404） |
| 歧义（ambiguous） | 0 |
| 需要人工复核 | 5 |
| 解析后按 InChIKey 回到名录 | 0 |

### 2.1 解析成功率 50%：30 个 404 的分布

29 个失败名字全部是 PubChem 名称索引里**没有这条记录**（404），没有一条是网络、DNS 或超时失败。
59 次请求里 30 个 404 = 29 个名字 + 1 个错拼修正变体（`1-hexylpyridinium bis(trifluromethylsulfonyl)imide`
的正字法变体，同样 404）。失败族的构成：

| 族 | 数量 | 说明 |
| --- | --- | --- |
| 胆碱 / 铵-氨基酸盐 | 10 | `choline L-lysinate`、`cholinium L-phenylalaninate`、`acetylcholine ...` 等 |
| 咪唑类（其他） | 6 | `3-(2-hydroxyethyl)-1-methylimidazolium hexafluorophosphate` 等 |
| NTf2 / 三氟甲磺酰亚胺盐 | 5 | `... bis[(trifluoromethyl)sulfonyl]imide` 这类带方括号的连写 |
| 膦盐（3-氨丙基三丁基膦） | 4 | `(3-aminopropyl)tributylphosphonium L-lactate` 等 4 个阴离子变体 |
| 吡啶 / 锍 | 1 | `1-hexylpyridinium bis(trifluromethylsulfonyl)imide` |
| 其他 | 3 | `methyltrioctylammonium bis-(trifluoromethylsulfonyl)imide` 等 |

共性很清楚：**失败集中在"阴阳离子连写成一长串"的命名习惯上**——手性前缀（L-/S-）、多余的位标、方括号写法、
`bis-` 与 `bis(...)` 的写法差异，都会让 PubChem 的名称索引查不到。这不是网络问题，是命名口径问题。

### 2.2 分子式核对拦下 2 条假阳性（这条防线是必须的）

47 条化合物同时拿到 ILThermo 分子式和 PubChem 结果的 RDKit 分子式：**45 条 match、2 条 mismatch**。
两条 mismatch 都是溴化物：

| 化合物 | ILThermo | PubChem 命中的结构 | 判断 |
| --- | --- | --- | --- |
| 1-butyl-3-methylimidazolium bromide | C8H15BrN2 | C8H17BrN2（`CCCCN1CN(C=C1)C.Br`，中性加合物） | 不是同一物种 |
| 1-methyl-3-octylimidazolium bromide | C12H23BrN2 | C12H25BrN2（同型中性加合物） | 不是同一物种 |

PubChem 的名称索引在这两条上返回的是**中性（氢化）加合物**，组成差 2 个氢。如果只看
`resolution_status == resolved`，这两条会被当成"结构已确认"混进候选清单。公式核对把它们拦住了，
并进了 `needs_manual_review`。对照组：18 条名录内化合物 **18/18 match**，说明核对逻辑本身没跑偏。

### 2.3 名录对账：InChIKey 回收 0 条，5 条转人工

- 18 条按归一化名字命中名录（含 3 条 roster 自己标了 `out_of_scope_ionic_or_organometallic` 的：
  BMIM-PF6、BDMIM-PF6、1,3-二甲基咪唑二甲基磷酸盐）。这 3 条说明"名录里有"不等于"名录认为可用"。
- 58 条名字未命中；用解析出的 InChIKey 回查名录：**0 条命中**。也就是说这 58 条确实是新化合物，
  不是"同一个化合物、换了种拼写"。
- 5 条 `needs_manual_review`：

| 化合物 | 复核原因 | 状态 |
| --- | --- | --- |
| 1-methyl-3-propylimidazolium bis[(trifluoromethyl)sulfonyl]imide | 同分异构体碰撞：名录 1-ethyl-2,3-dimethylimidazolium bis[(trifluoromethyl)sulfonyl]imide | unresolved |
| 1-butyl-2,3-dimethylimidazolium bis(trifluoromethylsulfonyl)amide | 同分异构体碰撞：名录 1-butyl-2,3-dimethyl-1H-imidazolium bis(trifluoromethylsulfonyl)amide | unresolved |
| 2-(hydroxyethyl)trimethylammonium formate | 同分异构体碰撞：名录三乙醇胺（同为 C6H15NO3，完全不同的化合物） | unresolved |
| 1-butyl-3-methylimidazolium bromide | 分子式不符（见 2.2） | resolved |
| 1-methyl-3-octylimidazolium bromide | 分子式不符（见 2.2） | resolved |

第一条正是上一份报告点名预言的案例（1-methyl-3-propylimidazolium vs 1-ethyl-2,3-dimethylimidazolium，
同为 C9H13F6N3O4S2），这一轮拿到了实证：分子式相同、两个名字归一化后不同、PubChem 查不到，只能转人工。
第三条是同一防线抓到的另一种假碰撞（胆碱甲酸盐 vs 三乙醇胺），证明"共享公式"这条规则确实在拦真东西。

**一个可修的归一化缺口**：第二条里，名录里的 `1-butyl-2,3-dimethyl-1H-imidazolium ...` 与 ILThermo 的
`1-butyl-2,3-dimethylimidazolium ...` 只差一个位标 `1H-`；把 `1H-` 剥掉之后两者归一化键完全相同
（已实测）。PubChem 对 ILThermo 那个拼写回 404，所以这条只能从名录侧修（1 条可从"未命中"回收为"名录内"）。

### 2.4 温度维度：本次最重要的否证

先给坦白的部分：**76/76 化合物的 ε 值都读到了**，109/109 数据集都声明 `Temperature, K` 列。
但温度是否真的变化，全量数据给出的答案是：

| 口径 | 数量 |
| --- | --- |
| 数据集总数 | 109 |
| 温度跨行变化的数据集 | **1** |
| 单一温度数据集 | 108 |
| 单一温度取值分布 | 298.15 K ×69、298.1 K ×35、296.15 K ×2、296 K ×1、311 K ×1 |
| 化合物视角（跨数据集取并集）单点 | 60 |
| 化合物视角 near_single（跨度 ≤ 5 K，多为重复数据集 0.05–2 K 的差异） | 15 |
| 化合物视角 **temperature_series（跨度 > 5 K）** | **1** |

唯一那条真正的温度序列：

| 项 | 值 |
| --- | --- |
| 集合 | `yGTrp`（化合物 trihexyl(tetradecyl)phosphonium chloride，[P66614]Cl） |
| 方法 | Broadband dielectric spectroscopy |
| 文献 | Kottummal, T. K. et al. (2018)（8 篇来源之一） |
| 点数 / 跨度 | 15 点 / 208.15–283.15 K |
| ε(T) | 3.184（208.15 K）→ 2.384（283.15 K），单调下降 |

**这里要更正上一份报告的一个抽样结论**：探针当时抽 8 条数据集得到"0/8 纯组分温度变化"，
全量 109 条把它收紧为"**1/109**"——抽样恰好漏掉了唯一那条序列。方向没变（这条线不是温度维度的大门），
但"完全没有"应该说成"只有 1 条"。

顺带一个采集口径警告：ε 列的名字叫 `Relative permittivity at zero frequency`，
但 **57/109 数据集同时带 `Frequency, MHz` 列（1–18 MHz 扫描）**，52/109 完全没有频率列，
没有任何数据集的频率列取 0。也就是说这 57 条到底是"静态 ε"还是"某频率下的 ε 外推"，
ILThermo 自己的标签是自相矛盾的。v0.4 若真要收录这些 ε，必须先把这个口径判清楚，否则会把
不同物理量混进同一个标签。

---

## 三、判决：这条线值不值得进 v0.4

| 问题 | 实测答案 | 判决 |
| --- | --- | --- |
| 能补温度维度吗？ | 109 条数据集里 1 条随温度变化，76 个纯化合物里 1 个有序列 | **不能，别当温度线** |
| 能补化合物覆盖吗？ | 76/76 全是离子液体；58 条名录外里 29 条可结构化 | **有条件：只有 v0.4 决定收 IL 时才值得** |
| 有机器可读导出吗？ | 前一份报告已证：无批量 CSV/TXT（两个猜测端点均 404），只有 JSON API | 不构成"正门"，只能一条条取 |
| 成本 | 109 次 ilset + 59 次 PubChem，全部 0 失败；重放 0 请求 | 便宜 |

具体建议：

1. **不要**把 ILThermo 排进 v1.x 的温度表数据源（附录 O 的 W12/W13 顺序不变）。
2. 若 v0.4 决定收离子液体，把 29 条 InChIKey（27 条通过公式核对）当"IL 分支"候选，
   先用覆盖率曲线量一下"加 27–29 个化合物能抬多少 R²"，再决定是否真收；
   这正是 `probes/dielectric_compound_coverage_curve.py` 已经验证过的杠杆方向。
3. 名录归一化补一条规则：剥掉 `1H-` 这类冗余位标（可回收 1 条），并把 `1H-` 案例写进
   AL 的归一化清单。
4. 这 5 条人工复核在 v0.4 之前不需要动；它们的价值是证明防线在工作，不是阻塞项。

---

## 四、交付物

| 文件 | 内容 |
| --- | --- |
| `probes/ilthermo_structure_resolution.py` | 探针本体（注入式 HTTP、预算、`--offline`、`--facts-from` 重放） |
| `tests/test_ilthermo_structure_resolution.py` | 91 项单元测试，全离线（假 HTTP + tmp_path 名录） |
| `data/processed/ilthermo_new_compounds.csv` | 76 行 × 31 列，LF；含 `in_roster` / `needs_manual_review` / `temperature_span_class` 等判定列 |
| `probes/ilthermo_structure_resolution_summary.json` | 人口/请求/解析/名录/温度五段汇总 + **109 条 `set_facts`**（可零请求重放） |
| `reports/ilthermo_structure_resolution.md` | 本报告 |

放行条已就位：`.gitignore` 第 120 行已有 `!data/processed/ilthermo_new_compounds.csv`
（由主线程在上一轮补入；本任务不改 `.gitignore`，只核对）：`git check-ignore -v` 显示该文件命中的是
这条放行规则，而不是 `data/processed/*` 通配。

CSV 里 76 行都在（含 18 条名录内行），而不是只留 58 条：名录归属是这份表的结论之一，
把名录内行一起留着，`in_roster` / `roster_join_basis` 两个字段才可审计。

复现与重放：

```
# 实跑（约 4 分钟，170 次请求：109 ilset + 59 PubChem + 余量）
.\.venv\Scripts\python.exe probes\ilthermo_structure_resolution.py

# 零请求重放：从已有 summary 的 set_facts 重建 CSV/JSON，不再读 NIST
.\.venv\Scripts\python.exe probes\ilthermo_structure_resolution.py --facts-from probes\ilthermo_structure_resolution_summary.json

# 完全离线（不发任何请求，只做名录与人口统计）
.\.venv\Scripts\python.exe probes\ilthermo_structure_resolution.py --offline --output <tmp>\off.csv --summary <tmp>\off.json
```

---

## 五、诚实边界（未闭环）

- **名字归一化是唯一接口**。ILThermo 不给结构标识，PubChem 的名称索引覆盖不了 IL 的命名习惯，
  所以 50% 的成功率是"名称索引覆盖率"的下界，不等于"PubChem 里没有这些化合物"。
- **公式核对不能区分同分异构体**。它只能排除"组成不同"；取代位置不同（1,2-/1,3-）必须靠 InChIKey
  或人工，本轮 3 条同分异构体碰撞已全部转人工。
- **29 条未解析不等于不存在**。其中 5 条是 NTf2/膦盐类，理论上可以拆成阳离子 + 阴离子分别解析再拼装
  （并把电荷与组成对齐）——**本轮没做**，这是下一步唯一可能明显提高成功率的动作。
- 296 K、311 K、298.1 K 这些非常规温度点只记录了 setid 与参考文献，**没有逐条回到原文核对**。
- 本轮**没有**把任何 InChIKey 写进 `data/dielectric_v03.csv` 或任何名录文件：IL 分支要不要收是 v0.4 的决定，
  这份表只是候选与证据。
- 网络侧：ILThermo JSON API 与 PubChem PUG-REST 全程可达、0 重试；未遇到限流。
