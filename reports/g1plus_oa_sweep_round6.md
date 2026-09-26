# G1+ 第六轮：OpenAlex + Unpaywall 定向扫漏（v1.x W13）

证据文件 `probes/openalex_unpaywall_sweep_summary.json`、`data/processed/openalex_oa_candidates.csv`。
脚本 `probes/openalex_unpaywall_sweep.py`，测试 `tests/test_openalex_unpaywall_sweep.py`（36 项，全离线可跑）。

**本轮没有改动任何数据集单元。** 产出是一张"候选线索"表，不是观测表：37 条候选里没有任何一条 ε(T) 数值被读进正文核对过。

---

## 1. 口径（可复现）

- 六个查询族，模板 `(dielectric OR permittivity) AND (...)`：
  `glymes` / `dinitriles` / `fluorinated_ethers` / `fluorinated_alcohols` / `sulfones` / `modern_carbonates_and_esters`。
- 入口：`https://api.openalex.org/works`，用 `filter=from_publication_date:2001-01-01,has_doi:true,title_and_abstract.search:<query>`，
  每族按相关性取前 20 条；`https://api.unpaywall.org/v2/<doi>?email=codex@local` 作 OA 闸门。
- **OA 只认 Unpaywall 的 `is_oa == true`**，OpenAlex 的 `open_access` 只作旁证。
- 礼貌客户端：`mailto=codex@local`、调用间隔 1 s、遵守 429 的 `retryAfter`（上限 45 s）、硬预算 200 次请求，结束时打印用量。
- 全程只用 `title_and_abstract.search`。匿名全文检索 `search` 端点被限流严重（实测连续 429），且过滤器值里出现逗号会被 OpenAlex 直接 400 拒绝，所以查询词去逗号、多词加引号。

## 2. 结果

| 查询族 | OpenAlex 命中总数 | 本轮取回 | OA 候选 |
|---|---:|---:|---:|
| glymes | 149 | 20 | 8 |
| dinitriles | 91 | 20 | 9 |
| fluorinated_ethers | 196 | 20 | 6 |
| fluorinated_alcohols | 79 | 20 | 5 |
| sulfones | 300 | 20 | 1 |
| modern_carbonates_and_esters | 490 | 20 | 8 |
| **合计** | **1,305** | **120** | **37** |

- 六族全部 HTTP 200，失败 0；请求用量 126/200。
- 120 条全部拿到 Unpaywall 应答；OA 判定 37 条。OpenAlex 也判 37 条，且 37 条候选的 `openalex_is_oa` 全为 True —— **两个闸门在本样本上完全一致**。
- OA 结构：publisher 25 / repository 12；`publishedVersion` 24 / `acceptedVersion` 3 / `submittedVersion` 10；
  许可 cc-by 15、cc-by-nc 1、cc-by-nc-nd 1、other-oa 2、无许可 18。
- 标题令牌比对：37 条中 21 条"本地未覆盖"，16 条命中本地名录（276 个溶剂名）。

## 3. 真正可用的新 ε(T) 线索（人工判读）

脚本的 `is_new_lead` 是标题令牌匹配，会高估。逐条看过之后，与"电池溶剂 ε(T)"相关的只有下面这几条：

| DOI | 年 | 体系 | 为什么算线索 |
|---|---|---|---|
| `10.1021/acsenergylett.2c02003` | 2022 | 1,2-dimethoxypropane | 标题即 "Low Dielectric Constant"；该溶剂是 glyme 同族、本地名录没有；OA 副本是 repository/submittedVersion |
| `10.1039/d2cp03200g` | 2022 | tetraglyme 基电解质 | 标题含 "low dielectric constant"，含二价阳离子输运 |
| `10.1063/5.0046073` | 2021 | glyme 电解质 / Na⁺ | 阴离子对离子缔合与介电环境的影响（green，机构库） |
| `10.1021/acs.jpclett.0c00334` | 2020 | 低介电常数多价电解质 | 离子对缔合/再解离，直接谈低 ε 与温度 |
| `10.1149/1945-7111/ab6975` | 2020 | LiNO₃/glyme 双溶剂 | 溶剂体系依赖性 |
| `10.1016/j.electacta.2019.02.110` | 2019 | glyme 基 Li/Na 电解质 | 离子输运与缔合（bronze，acceptedVersion） |
| `10.1149/2.0461816jes` | 2018 | 三氟甲基化己二腈 | dinitrile 族新结构 |
| `10.1063/1.4944394` | 2016 | 塑料晶体（丁二腈同族） | 非线性介电谱，偏方法学 |
| `10.1088/1361-648x/aab466` | 2018 | Na⁺ 固态聚合物电解质 | 介电弛豫，弱线索 |

最强的三条是 1,2-dimethoxypropane、tetraglyme 基、和 `10.1021/acs.jpclett.0c00334`。其余需要回全文确认是否真有 ε(T) 表。

## 4. 负结果（同样重要）

- **氟代醚族整族基本是幻影。** `novec` 把 Novec 649/7100 这类"介电冷却液"的池沸腾传热论文全带了进来（6 条里 5 条），那些论文里的 "dielectric" 是形容词，不含 ε(T)。下一轮应删掉 `novec`，改用具体化合物名。
- 磺酮族只回 1 条，且是聚合物光催化论文，不是溶剂 ε(T)。
- 三氟乙醇族 5 条几乎全是生物物理/多肽论文（TFE 作共溶剂，不是纯溶剂 ε(T)）。
- 其余假阳性：DNAPL 地球物理、synaptotagmin 内在无序区、染料溶剂化。
- **已知溶剂侧是一个正面结论**：16 条命中的是 PC / EC / DMC / 丁二腈 / 戊二腈 / 1,2-二甲氧基乙烷，其中不少是分子动力学论文（如 `10.1021/acs.jpcb.5b09561` "Dielectric Relaxation of EC and PC from MD"）。这独立佐证了主流溶剂的 ε(T) 本地已有覆盖，不是缺口。
- 注意区分"新化合物"与"新温度点"：已知溶剂里有些确实是温度分辨**实验**测量（`10.1063/1.4746022` 高压下 PC 介电谱、`10.1063/1.4740236` PC 剪切+介电、`10.1149/1.1403730` 电导随温度）。它们不是新化合物线索，但可能是 v1.x 观测表里**已覆盖溶剂的新温度点**来源——进 AL Round 3 时建议单列这一类。

## 5. 不能核实的（明写）

- 37 条全是线索，**没有一条 ε(T) 数值被取回核对**。
- **本轮是浅扫不是穷举**：六族命中 1,305 条，每族只读了相关性前 20 条，5 族命中 ≥79 条，绝大多数匹配未被检视。
- `title_and_abstract.search` 只索引标题+摘要：只在表格里给 ε(T)、标题摘要不含 dielectric/permittivity 的论文，本轮看不见。
- Unpaywall 是唯一 OA 闸门：被它误判为 closed 的真开放论文会静默丢掉，本轮没有量化这个损失。
- `is_new_lead` 是标题令牌匹配，本地名录只有 276 个名字，且本地多用 IUPAC 名收录。论文用俗名时（diglyme = 2,5,8-trioxanonane、triglyme、tetraglyme）会误报"新"，所以 **21 这个数字偏大**。
- 匿名检索受限：**本轮之前的一次运行**（12:29 UTC）有两族被 429 打掉（当时退避只有 5/15 s，而 OpenAlex 自己提示 `retryAfter≈39 s`）。改成遵守 `retryAfter` 后重跑（12:34 UTC）六族全绿、失败 0。这个"0 失败"不保证可复现——API 明确建议用免费 key 换取不中断访问。
- DOI→标题的映射来自 OpenAlex，本轮未逐条打开原文核对题名。

## 6. 复现

```powershell
.\.venv\Scripts\python.exe -m ruff check probes scripts tests
.\.venv\Scripts\python.exe -m pytest tests/test_openalex_unpaywall_sweep.py -q
.\.venv\Scripts\python.exe probes\openalex_unpaywall_sweep.py   # 真实联网，约 2 分钟、126 次请求
```

第三条会真实联网。断网时脚本不编数据：`candidates` 为空、失败逐条写进 summary 的 `failures`，CSV 只留表头。