# ILThermo（NIST SRD 147）探针报告

**一句话结论：ILThermo 是"化合物覆盖"方向的一扇真门，不是"温度扩展"的门。**
它能一次给出 **76 个纯化合物**的相对介电常数，其中 **58 个不在我们名册里**；
但纯组分的 ε 绝大多数只有**单一温度点**，指望它补 ε(T) 序列会落空。

复现：

```
.\.venv\Scripts\python.exe probes\ilthermo_probe.py
.\.venv\Scripts\python.exe -m pytest tests/test_ilthermo_probe.py -q
```

---

## 一、先把入口摸清，再用它（发现段的证据）

站点是 Dojo 单页应用，HTML 外壳里**没有**查询面。真正的接口写在 `/ilthermo.js` 里，
探针先做一轮 discovery，把每个候选端点的 URL / 状态 / 字节数记进
`probes/ilthermo_probe_summary.json` 的 `discovery` 段，然后才使用：

| 端点 | 状态 | 字节 | 说明 |
| --- | --- | --- | --- |
| `/` | 200 | 5,554 | 应用外壳 |
| `/ilthermo.js` | 200 | 14,414 | 真正的接口清单在这里 |
| `/ILT2/ilprpls` | 200 | 2,690 | 属性清单（JSON） |
| `/ILT2/ilsearch` | 200 | 67 | 数据集检索（无参时返回 errors） |
| `/ILT2/ilset` | 200 | 11 | 单个数据集（JSON） |
| `/ILT2/ilstats` | 200 | 659 | 状态页 |
| `/ILT2/` | **403** | 1,589 | 目录列表被拒 |
| `/ILT2/ilset.csv` | **404** | 648 | 批量导出猜想一（不存在） |
| `/ILT2/ilsearch.txt` | **404** | 648 | 批量导出猜想二（不存在） |

礼貌性：UA 自报、每次调用间 sleep 1s、`429`/`Retry-After` 退避（服务端提示优先，上限 60s）、
硬预算 60 次。本次实跑用掉 **24 次 / 113,388 字节 / 失败 0**。

---

## 二、四个问题逐条判

### (a) 是否暴露"相对介电常数"——**是**

- `ilprpls` 里属性名就叫 `Relative permittivity`，属于 `Refraction, surface tension, and
  speed of sound` 类，对应短键 **`TGKW`**。
- 用 `prp=TGKW` 实查：116 条数据集**全部**返回 `Relative permittivity`。
- **配对陷阱（必须记）**：短键与属性名是**按下标配对**的，键本身不自描述。
  对照组 `prp=JYHK` 返回的是 `Speed of sound`，证明过滤器确实在区分、而不是全命中。
  不验这一点就会抓错属性——第一次试 `JYHK` 时拿到的正是"声速"。

### (b) 是否带温度——**是，但要说清是哪种"是"**

- 8/8 抽样数据集的 `dhead` 都声明了 `Temperature, K` 列，值网格里也确有数值温度。
- **但** 8/8 纯组分抽样中 **0 个**温度跨行变化：它们是同一次 298.15 K 下的**频率扫描**
  （Bennett et al. 2019，116 条里独占 66 条）。
- 纯组分总体数据点分布：`{1: 51, 15: 1, 18: 57}`——51 条只有一个点，57 条 18 个点。
- 定向核查取总体里最大的两个数据集：`KXnxb` 确有 3 个温度（293.15–313.15 K），
  但它是 **IL/甲醇二元混合物**，不是纯组分；`AkwwH` 仍是单温频率扫描。
- 结论：**库与 JSON 格式支持温度，但纯组分的 ε 持仓本质上是单温的。**
  这直接推翻了"ILThermo 天然温度分辨"的预期。

### (c) 有没有机器可读导出——**有 JSON API，没有批量 CSV/TXT**

- `/ILT2/ilset` 返回完整数据集：列头（含单位）、数值、不确定度、参考文献、实验方法，
  全部 JSON，可直接机器读。
- 没有批量导出：两个猜的导出路径都是 **404**；`ilthermo.js` 里也没有任何
  `download` / `export` / `csv` 字样。
- 手册里"支持 CSV 导出"的说法在本探针的证据下**不成立**，应更正为"JSON API 可取，
  需自行落表"。

### (d) 多少化合物带这个数据、其中多少是新的

| 口径 | 集合 | 数据点 | 不同化合物 |
| --- | --- | --- | --- |
| 全部 | 116 | 1,164 | 80 个组分（77 离子 / 3 分子） |
| **纯组分** | **109** | **1,092** | **76** |

对 `data/dielectric_v03.csv`（246 条）做名册对照：

- **18 个已在名册**（全部是离子液体，带真实 InChIKey）
- **58 个是新的**（相对名册 +24%）
---

## 三、两个必须记住的对账

**1. ILThermo 不给结构标识符。** 它**没有 CAS、没有 SMILES、没有 InChIKey**，
只有名称、分子式和结构图 key。因此：

- 名册对齐用的是**名称归一化**（覆盖全部 76 个），外加对**实际抓到的 8 个数据集**
  做 RDKit 分子式结构核对；
- 另外 68 个只有名称级结论，标注 `structure_resolved: false`，**没有**被包装成结构结论；
- 要拿到 InChIKey 级别的判定，必须过第三方结构服务（本次未做）。

**2. 分子式相同 ≠ 同一化合物。** 抽样里有 1 个化合物与名册某条**分子式完全相同**，
但它们是**同分异构体**：ILThermo 的 `1-methyl-3-propylimidazolium
bis[(trifluoromethyl)sulfonyl]imide` vs 名册的 `1-ethyl-2,3-dimethylimidazolium
bis[(trifluoromethyl)sulfonyl]imide`。探针**没有**把它算作命中，而是单列为
`formula_collisions_needing_manual_review`。若当初用分子式当命中判据，这 1 个新化合物
会被静默抹掉。

同一条对账还有一层：手册写"名册只有 4 个边界离子液体，IL 是全新家族"。实际名册**按名字**
已收 18 个离子液体（只有 4 条被标 `out_of_scope_ionic_or_organometallic`）。
所以诚实说法是**"大部分是新的"**，不是"整个家族都是新的"。

---

## 四、接入机制（真正能用的那条路）

1. 取清单：`GET /ILT2/ilsearch?prp=TGKW&ncmp=1` → `res` 数组，每条含
   `setid / ref / prp / np / nm1..nm3`（**注意：行在 `res` 里，不在 `data` 里**）。
2. 取数据：`GET /ILT2/ilset?set=<setid>` → 含 `dhead`（列头+相态）、
   `components`（名称/分子式/分子量/结构图 key）、`data`（每格为 `[值]` 或 `[值, 不确定度]`）、
   `ref`、`expmeth`。
3. 落表前必须按列筛选：结果里混着**频率扫描**（有 `Frequency, MHz` 列、ε 随频率变）
   和真正的**零频点**。本次 8 个抽样**全部**是频率扫描。

**不要**用 `prp=JYHK`——那是 Speed of sound。

---

## 五、对 v1.x 的判断

- **第一刀仍然对**：本地 242 个 ThermoML XML 重解析依旧是零成本首选。
- **ILThermo 是第二刀**：它给的是**新化合物**（58 个新纯化合物，全在离子液体这条支线上），
  不是新温度点。这与 `reports/dielectric_compound_coverage_curve.md` 的结论一致——
  杠杆在化合物覆盖，不在温度覆盖。
- 若要把它并入训练表，建议单开 `v0.4 ionic-liquid tier`，与 v1.x 温度表分开记账，
  评估口径继续用 `GroupKFold by InChIKey`。

---

## 六、局限（没有验证的，不许当结论用）

- 抽样是有界的：76 个纯化合物里只取了 8 个取数据、另 2 个做定向温度核查；
  "多少条是温度序列"是按数据点分布 + 抽样推断，**不是** 109 条全查。
- 名称对齐是归一化字符串匹配，不能排除同义词漏配（trivial name 差异）；
  分子式核对只覆盖抓到的 8 个。
- 无 CAS/SMILES/InChIKey，所以"58 个新"是**名称级**结论，其中 8 个有结构旁证。
- 报告里每个数字都来自本次实际收到的响应；逐条请求的 URL/状态/字节记在
  `probes/ilthermo_probe_summary.json` 的 `request_log` 与 `discovery` 段。