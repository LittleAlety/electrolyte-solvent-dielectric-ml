# AL Round 3：37 条 OA 线索的处置报告（v1.x W13）

证据文件 `probes/al_round3_summary.json`、`data/processed/al_round3_candidates.csv`。
脚本 `probes/al_round3_candidates.py`，测试 `tests/test_al_round3_candidates.py`（66 项，全离线可跑）。
输入 `data/processed/openalex_oa_candidates.csv`（第六轮浅扫的 37 条线索），对照 `data/dielectric_v03.csv`（246 化合物名录）与
`data/processed/dielectric_observations_v11.csv`。

**一句话结论：37 条线索里，读到 0 个 ε(T) 数值；真正可用的产出在化合物侧——18 个可指认化合物（其中 8 个不在名录），并且能读到的全文全部来自 arXiv。**

---

## 1. 口径（可复现）

每条线索走三步，每步都只记录实际观察到的东西：

1. **这个化合物是什么？** 标题里的名称匹配手工维护的 name/alias -> SMILES 表，用 RDKit 本地算 InChIKey；
   指认不出单一分子的（聚合物、蛋白、品牌名、泛指 glyme、盐、类别名词）写成 unresolved 并给出原因，不猜。
2. **全文真的能取到吗？** 取 `oa_url`，记录 HTTP 状态、Content-Type、最终 URL、实际抓到的字节数。
   200 但内容是机器人校验页或落地页的，判为 blocked，不算可达。
3. **里面真有 ε(T) 吗？** 只有确实解析出全文时才搜索「介电措辞 + 带单位的温度 + 合理数值」同行的句子，
   命中行逐字保留并带页码/行号。读不到就写 value_not_read 加原因。

硬上限：请求 90 次、单文档 12 MB、总字节 200 MB、调用间隔 1 s、遵守 429 的 Retry-After（上限 45 s）。
化合物身份另用 PubChem 交叉核对（独立预算 30 次请求）。噪声线索默认不发请求。

## 2. 结果总览

| 处置 | 条数 | 含义 |
|---|---:|---|
| blocked_fetch_error | 15 | 12 次 403 + 3 次连接/DNS 失败 |
| blocked_html_landing | 8 | 200 但是落地页，不是全文 |
| skipped_noise_prefilter | 10 | 标题层判定为噪声，故意不取 |
| table_candidate_needs_review | 3 | 拿到全文，但只有表形段落，没人可读的行内数值 |
| fulltext_no_value | 1 | 拿到全文 91k 字符，无「措辞+温度+数值」同行 |
| value_read | **0** | — |
| 合计 | 37 | 实际发起请求 27 次（=37−10 噪声） |

预算用量：请求 27/90，PubChem 18/30，状态码 {200: 12, 403: 12, 0: 3}，实际抓取 6,505,275 字节（无一份触发 12 MB 截断）。

化合物侧：解析出 **18 个唯一化合物**，其中 **10 个已在 246 名录**、**8 个不在名录**；
名录归属逐条统计为 all_in_roster 12 条 / some_new 6 条 / all_new 9 条 / unresolved 10 条。

## 3. 结论 A：没有读到任何一个 ε(T) 数值

37 条线索里 value_read = 0。这不是没查，而是查完之后的分布：

- **只有 4 条线索真的拿到了可解析全文**（`text_extractor = pypdf`），合计 215,237 字符、170 行含介电措辞。
  这 4 篇**全部是 arXiv**。
- 其中 1 篇（`10.1088/1361-648x/aab466`）91,366 字符里 62 行提到 permittivity，但没有任何一行同时带「措辞 + 带单位温度 + 数值」，
  按规则记为 value_not_read，原因是 `permittivity_wording_present_but_no_explicit_temperature_with_unit`。
- 另 3 篇记为 table_candidate_needs_review，逐条看下来是：
  | DOI | 触发的那行（逐字） | 判读 |
  |---|---|---|
  | `10.1063/1.4746022` | `High-pressure dielectric spectroscopy experiments were carried out in Toroid type anvils in the P-T region P < 4.1 GPa and 210 K < T < 410 K` | **真线索**：PC 高压 ε(T) 实测，但数值在图上，文本层读不到 |
  | `10.1063/1.4944394` | `quantity ln ε" = ln ε"(Eh) - ln ε"(El)` | 图标签，ε 是符号不是数值 |
  | `10.1063/1.4794792` | `ln P (δε/σ) ... T = 300K` | 分子动力学图标签，同上 |

  三个都不是「表格解析失败」，而是**触发词落在图题/图标签上**。脚本没有把任何一个数字写成 ε 值，这一条守住了。

## 4. 结论 B：OA ≠ 可匿名抓取（本轮最重要的负结果）

把 27 次实际抓取按 OA 托管方切开：

| 托管方 | 抓取次数 | 得到全文 | 403/连接失败 | 落地页 |
|---|---:|---:|---:|---:|
| publisher | 16 | **0** | 10 | 6 |
| repository | 11 | **4（全部 arXiv）** | 5 | 2 |

- 12 次 403 几乎全是 Cloudflare 的 `Just a moment...` 页：Wiley 4（含 IET）、AIP 3、RSC 2、Elsevier 1、ACS 1、Springer 1。
  这些是直接 403，没有跳转，所以连机器人校验页都拿不到，只在错误详情里留下了前 300 字节。
- 6 个 publisher 落地页说明 200 不等于全文：IOP 三条被跳到机器人校验域 `validate.perfdrive.com`（14,371 字节）、
  AIP 两条 `aip.scitation.org`（1,390 / 1,414 字节）、Elsevier 一条 `linkinghub.elsevier.com`（2,709 字节）。
  它们都没触发机器人校验关键词，所以按「落地页」而不是「bot check」记账——这正是规则保守的地方。
- **环境级硬阻断（已单独复验，非偶发）**：`zenodo.org` 在本机 **DNS 根本不解析**（gaierror 11004）；`www.osti.gov` DNS 正常但 TCP 连接 21 s 超时。
  这两条恰好覆盖了第六轮点名的两个「最强线索」——`10.1021/acsenergylett.2c02003`（1,2-二甲氧基丙烷，唯一 OA 副本在 Zenodo）
  与 `10.1021/acs.jpclett.0c00334`（OSTI 副本）；PMC 的 `2717614` 也回 403。

也就是说：**Unpaywall 说 is_oa=true，并不等于一个匿名的诚实 UA 能拿到字节。** 本轮 27 次抓取只有 4 次（15%）拿到全文，
且 100% 来自 arXiv。这直接改变了 v1.x 的取数路线——见第 7 节的清单。

## 5. 结论 C：氟代醚整族是噪声，本轮定案

噪声按标题字面规则判定（规则可审计），10 条命中：

| 规则 | 命中 | 涉及线索 |
|---|---:|---|
| pool_boiling_heat_transfer | 5 | Novec 7100 / Novec 649 ×2 / FC-72 / 浸没冷却 |
| biophysics_peptide_or_protein | 3 | 三氟乙醇 ×2（多肽、MscS 通道）、synaptotagmin |
| geophysics_dnapl | 1 | DNAPL 电阻率/介电时移 |
| polymer_photocatalyst | 1 | 含砜聚合物光催化 |

按查询族看：`fluorinated_ethers` **6/6 全是噪声**（第六轮说「6 条里 5 条」，本轮加上 DNAPL 那条就是 6/6，
其中「dielectric」全部是形容词）；`sulfones` 1/1 噪声；`fluorinated_alcohols` 3/5 噪声；
`dinitriles` 0/9、`glymes` 0/8、`modern_carbonates_and_esters` 0/8。
下一轮检索应删掉 `novec`，改用具体化合物名（decafluoropentane / methoxy-nonafluorobutane）。

## 6. 真正的产出：化合物侧

18 个唯一化合物，**PubChem 交叉核对 18/18 分子式一致、0 个不匹配**（CID 全部命中），说明手工 SMILES 表立得住。

不在 246 名录的 8 个：

| 化合物 | InChIKey | 与电池溶剂的关系 |
|---|---|---|
| 1,2-dimethoxypropane | LEEANUDEDHYDTG-UHFFFAOYSA-N | **最相关**，glyme 同族、标题即「低介电常数」，第六轮最强线索 |
| succinonitrile | IAHFWCOBPZCAEA-UHFFFAOYSA-N | **相关**，塑料晶体电解质主溶剂 |
| tripropylene glycol | LEQCJROTXBYLEU-UHFFFAOYSA-N | 弱相关，醇醚 |
| 2,2,2-trifluoroethanol | RHQDFWAXVIIEBN-UHFFFAOYSA-N | 来自噪声族（生物物理共溶剂） |
| hexafluoroisopropanol | BYEAHWXPCBROCE-UHFFFAOYSA-N | 来自噪声族 |
| methoxy-nonafluorobutane | OKIYQFLILPKULA-UHFFFAOYSA-N | 传热流体（Novec 7100） |
| decafluoropentane | RIQRGMUSBYGDBL-UHFFFAOYSA-N | 传热流体（Novec 649） |
| perfluorohexane | ZJIJAJXFLBMLCK-UHFFFAOYSA-N | 传热流体（FC-72） |

**诚实提醒**：8 个「新」里只有 **2 个**（1,2-dimethoxypropane、succinonitrile）是电池溶剂主线相关的；
其余 6 个来自噪声族，属于「顺手解析出来但不该进 v1.x 化合物扩展」的一类。

另一个易被忽略的对账：**succinonitrile 不在 246 名录里，却已经在 v11 观测表里躺着 17 行、17 个互不相同的温度点**
（333.15 K 起，实测 ε 由 56.09 递减到 54.29，相态标注 Liquid）。这才是 v1.x 真正的形态：名录是静态单值的 246 条，
观测表是温度分辨的 1,630 行，**补录化合物时只看名录，会漏掉已经具备 ε(T) 的化合物**。

## 7. AL Round 3 补录清单（可执行）

**A 类 — 人工读图取数（4 条，全部 arXiv，可自助下载，零版权风险）**

| DOI | arXiv | 要读什么 |
|---|---|---|
| `10.1063/1.4746022` | 1305.3840 | PC 在 210–410 K 的高压 ε(T)（图 1 三条等压线） |
| `10.1063/1.4944394` | 1512.06020 | 塑料晶体非线性介电谱 |
| `10.1063/1.4794792` | 1212.5304 | PC 界面 MD（⟨ε⟩ 随温度，表 1/图 12） |
| `10.1088/1361-648x/aab466` | 1807.03969 | Na⁺ 固态聚合物电解质介电弛豫 |

**B 类 — 换通道取数（12 条 Cloudflare 403）**
Wiley 4、AIP 3、RSC 2、Elsevier 1、ACS 1、Springer 1。匿名 UA 取不到，需要机构代理 / 浏览器会话 / 馆际互借。
其中真正相关的是 `10.1021/acs.jpcc.5b09380`（丁二腈塑料共晶）与 `10.1002/eem2.12494`（1 M LiPF6 in EC:EMC 的介电常数随溶剂化）。

**C 类 — 环境阻断，换网络即可重试（3 条）**
`10.1021/acsenergylett.2c02003`（Zenodo DNS 不解析）、`10.1021/acs.jpclett.0c00334` 与 `10.1021/acs.jpcb.5b09561`（OSTI 超时）。
前两条是第六轮认定的「最强线索」，值得换一台机器/网络再跑一次 `probes/al_round3_candidates.py`。

**D 类 — 归档为噪声（10 条）**，不要再花预算。

## 8. 未核实 / 局限

- **化合物解析来自手工 name/alias -> SMILES 表**，不是从正文抽结构；标题间接指认的化合物不会被解析出来（10 条 unresolved 就是这类）。
- **ε 数值一个都没有被读进正文**；3 条 table_candidate 是给人工复核的信号，不是数值。
- PDF 文本层对符号字体无能为力：本轮抽取结果里出现过私用区码位（U+F044）代替 ε，**词形匹配会漏掉这类论文的真实 ε 数值**。
- 噪声只看标题、且默认不取正文；它们的可达性是**故意未知**，不是「已确认不可达」。
- HTML 一律要求 ≥60,000 字符才算全文，因此一篇真正很短的 HTML 文章会被误判为落地页；本轮没有出现这种情况（8 条落地页实测都只有 1.4 KB–500 KB 的骨架/跳转页）。
- 除 429 外没有重试逻辑；zenodo/osti 的失败已单独复验为确定性失败，但**换网络后结论可能不同**。
- 匿名 + 诚实 UA 本身可能就是 403 的原因之一；本轮没有用浏览器指纹、代理或带会话的客户端做对照，
  所以**无法区分「内容受保护」与「单纯拒绝机器人访问」**——这个区分直接决定 B 类是走机构代理还是走馆际互借。
- 只跑了一轮，没有对 403 的 URL 做第二通道尝试。
- `data/processed/al_round3_candidates.csv` 仍被 `.gitignore` 的 `data/processed/*` 规则忽略（本轮未改 .gitignore）。

## 9. 复现

    .\.venv\Scripts\python.exe -m ruff check probes scripts tests
    .\.venv\Scripts\python.exe -m pytest tests/test_al_round3_candidates.py -q
    .\.venv\Scripts\python.exe probes\al_round3_candidates.py --offline --sleep 0   # 0 次请求，只验解析/分类
    .\.venv\Scripts\python.exe probes\al_round3_candidates.py                      # 真实联网，约 2.5 分钟、27 次请求 + 18 次 PubChem

断网或离线时脚本不编数据：不发起任何请求，37 行照写，只是抓取类列全空、处置列记 not_attempted_offline / skipped_noise_prefilter。
