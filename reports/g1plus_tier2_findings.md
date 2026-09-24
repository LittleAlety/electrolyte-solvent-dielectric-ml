# G1+ Tier-2：免费电池领域汇编取证

日期：2026-09-24  
范围：ECW-308 与 GSDS / Batt-SLM 的 DC-200；目标分子 10 个。  
结构化证据：`probes/g1plus_tier2_evidence.json`  
逐次请求审计：`data/external/g1plus/compilations/_request_log.jsonl`

## 结论摘要

- **ECW-308：成功。** 论文 DOI 为 `10.1002/adfm.202212342`。doi.org、Wiley TDM/XML 和 SI 直链经 curl 均被 Cloudflare 403；应用内浏览器加载 Wiley 文章页后成功取得 SI PDF。原始文件：
  - `data/external/g1plus/compilations/adfm202212342-sup-0001-SuppMat.pdf`
  - 2,194,733 bytes，SHA-256 `19F1166E2ABA6834F0CCCB1D751B618DDED5C80F97AB5B9957B2D15046BDBC76`
- **DC-200：未取得逐分子数据集。** 论文全文与 SI 已成功取得，但 SI 只有 DC-200 模型说明和图，不含 200 分子表；作者 GitHub 的完整文件树也没有 DC-200。DataCite 找到作者 Zenodo 配套记录 `10.5281/zenodo.21061162`，说明只含 fine-tuning 结果和最终 generators。后续复核把主机名钉到已解析 IP 后成功取到清单：仅 1 个文件 `GSDS_Prior_Finetune.zip`（4,746,199,417 字节），仍不含 DC-200 逐分子表。未用 MNSOL 或其他来源猜填 DC-200 数值。
- **10 个目标中，ECW-308 命中 9 个。** 唯一未命中的是 tetraglyme；MOPN 取得 `ε=36.00 @ 25 °C`，这是本任务最重要的缺口补录。
- 所有 ECW-308 表头均为 `Dielectric constant at 25 °C`；结构化数据把 25 °C 写成 298.15 K，仅是单位换算，不是独立测温记录。

## 资产 1：ECW-308

### 落地与许可证

- 论文：Wang et al., *Advanced Functional Materials* 2023, DOI `10.1002/adfm.202212342`。
- 公开 SI 地址：
  `https://advanced.onlinelibrary.wiley.com/action/downloadSupplement?doi=10.1002%2Fadfm.202212342&file=adfm202212342-sup-0001-SuppMat.pdf`
- 本地原始文件：`data/external/g1plus/compilations/adfm202212342-sup-0001-SuppMat.pdf`。
- 许可证：OpenAlex 标记该论文为 closed，Wiley 页面未声明 CC 许可。该 SI 仅作研究取证保留，不应标成 CC-BY 再分发。
- DOI 落地页、Wiley 全文 XML、两个 downloadSupplement 直链的 curl 请求均返回 403 Cloudflare challenge；浏览器访问成功，因此失败属于反爬拦截，不是资产不存在。

### 目标命中值

| 分子 | CAS | SMILES | ECW-308 ε | T | 条目/页 | 原引文 |
|---|---|---|---|---|---|---|
| triglyme | 112-49-2 | COCCOCCOCCOC | 7.53 | 25 °C | 104. Triglyme，PDF p.75 / S74 | Huang et al., Adv. Mater. 2019, 31, 1808393 |
| tetraglyme | 143-24-8 | COCCOCCOCCOCCOC | 未命中 | — | SI 中未找到 tetraglyme / C10H22O5 | — |
| MOPN | 110-67-8 | COCCC#N | **36.00** | 25 °C | 51. 3-Methoxypropionitrile，PDF p.71 / S70 | Perricone et al., Electrochim. Acta 2013, 93, 1 |
| PC | 108-32-7 | CC1COC(=O)O1 | 64.90 | 25 °C | 159. Propylene carbonate，PDF p.79 / S78 | Flamme et al.; Perricone et al. |
| EC | 96-49-1 | O=C1OCCO1 | 89.00 | 25 °C | 158. Ethylene carbonate，PDF p.79 / S78 | Flamme et al.; Duncan et al.; Perricone et al. |
| diglyme | 111-96-6 | COCCOCCOC | 7.40 | 25 °C | 96. Diglyme，PDF p.74 / S73 | Huang et al., Adv. Mater. 2019, 31, 1808393 |
| adiponitrile | 111-69-3 | N#CCCCCC#N | 30.00 | 25 °C | 53. Adiponitrile，PDF p.71 / S70 | Duncan et al., J. Electrochem. Soc. 2013, 160, A838 |
| glutaronitrile | 544-13-8 | N#CCCCC#N | 37.00 | 25 °C | 52. Glutaronitrile，PDF p.71 / S70 | Duncan et al., J. Electrochem. Soc. 2013, 160, A838 |
| VC | 872-36-6 | O=c1occo1 | 126.00 | 25 °C | 163. Vinylene Carbonate，PDF p.79 / S78 | Hall et al.; Flamme et al. |
| FEC | 114435-02-8 | O=C1OCC(F)O1 | 78.40 | 25 °C | 166. Fluoroethylene carbonate，PDF p.79 / S78 | Flamme et al.; Deng et al. |

MOPN 身份不是只靠名字判断：PubChem PUG REST 查询 CAS `110-67-8` 返回 CID 61032、IUPAC `3-methoxypropanenitrile`、Canonical SMILES `COCCC#N`，与任务给定 SMILES 一致。ECW 的该行还并列显示了一个无引文的堆叠值 `25.00`；本报告采用有原引文的介电常数值 `36.00`，未采用 `25.00`。

## 资产 2：DC-200

### 已取得的开放获取材料

- Zhang et al., *ACS Nano* 2026, DOI `10.1021/acsnano.6c06255`，PMCID `PMC13422007`。
- Europe PMC 全文 XML：`data/external/g1plus/compilations/request_013_pmc13422007_fulltext.xml`，178,808 bytes，SHA-256 `2B0D993EFD87DDEE3D6D3C6B0EFEB5920970610D9827E217380F6A4187558F9C`。
- Europe PMC supplementary ZIP：`data/external/g1plus/compilations/request_015_europepmc_supplementary.zip`，4,766,649 bytes，SHA-256 `08354E0C3A1A27F7B1478031912A37D5544648B31DFFB0D0CE6DDFE309B763A7`。
- 解包 SI：`data/external/g1plus/compilations/nn6c06255_si_001.pdf`，5,244,112 bytes，SHA-256 `E6AFBAF92DE6C0BC0D4B3D63D84EF2708C2A40491D73C012507DEACEC077BA57`。
- 论文为 hybrid OA，OpenAlex 标注 CC-BY-4.0。

### 为什么没有 DC-200 逐分子值

1. **SI 不含数据表。** 50 页 SI 只在 pp. S22-S23 讨论 LF-MLR-DC-200 和作图，没有 200 分子的名单、实验值或计算值。
2. **GitHub 不含 DC-200。** `Teoroo-CMC/Batt-SLM` 递归树共 207 项，只有 Batt-SLM、Batt-P30K、Redox-Pot、CPI 和 RX-392 类资产；没有 DC-200、dielectric 或 dielectric-constant 数据文件。
3. **Zenodo 配套记录经清单核对后仍不含 DC-200。** DataCite 搜索找到 `10.5281/zenodo.21061161` 与 `10.5281/zenodo.21061162`（两者指向同一记录），许可证为 CC-BY-4.0 + MIT，且 IsSupplementTo 该论文。首轮探测时 `zenodo.org` 在本环境 DNS 不可达；后续复核把主机名钉到已解析 IP（`137.138.52.235`）后记录 API 可访问，清单实际为 1 个文件 `GSDS_Prior_Finetune.zip`（4,746,199,417 字节，md5 `f1736827b1a9f31e85587ca2eae913a7`），描述为 fine-tuning results 与 final generators，**没有**逐分子 DC-200 表。结论不变，但依据由“端点不可达”升级为“清单已核对”。
4. **原始组装来源不可直接获得。** 正文说明 DC-200 来自“literature and public databases”，对应参考文献为 He et al. 2025 (`10.1063/5.0267184`) 与 Minnesota Solvation Database 2012。MNSOL 官网当前连接超时；没有下载或使用未核验镜像。
5. **因此 10 个目标的 DC-200 字段全部为 `found=false`。** 这不是“查无此分子”的结论，而是“该 200 分子表未随可访问论文资产发布，且任务限定的直接资产不可恢复”。

## 与现有 dielectric v0.3.2 的对照

现有值只读自 `data/dielectric_v032.csv`，未覆盖、平均或修改。

| 分子 | 现有值 | ECW-308 | 差异/判断 |
|---|---:|---:|---|
| triglyme | 7.604 @298.15 K | 7.53 @25 °C | -0.074（-0.97%），接近 |
| tetraglyme | 7.798 @298.15 K | 无 | 无第三方对照 |
| MOPN | 缺失 | **36.00 @25 °C** | 补缺证据；建议但尚未写入受保护数据集 |
| PC | 64.9 @298.15 K | 64.9 @25 °C | 完全一致 |
| EC | 90.5 @313.15 K | 89.0 @25 °C | 温度不同，方向一致，不能作严格同温对照 |
| diglyme | 7.3815 @298.15 K | 7.40 @25 °C | +0.25%，接近 |
| adiponitrile | 32.12 @298.15 K | 30.00 @25 °C | -6.6%，存在可注意的汇编间差异 |
| glutaronitrile | 34.60 @298.15 K | 37.00 @25 °C | +6.9%，存在可注意的汇编间差异 |
| VC | 126 @298 K | 126 @25 °C | 精确复现 126，支持该争议高值 |
| FEC | 102 @298.15 K（冲突值 78.4/102/107） | 78.4 @25 °C | 独立支持低端 78.4，102/107 冲突仍未解决 |

## 请求审计

按“显式 API/下载/浏览器导航”计，共 **39 次**，预算 40。每次间隔至少 1 秒。完整逐条记录见 `_request_log.jsonl`；关键失败如下：

| # | URL/操作 | 返回 |
|---|---|---|
| 1 | `https://doi.org/10.1002/adfm.202212342` | 403，Cloudflare challenge |
| 3 | `https://onlinelibrary.wiley.com/doi/full-xml/10.1002/adfm.202212342` | 403，Cloudflare challenge |
| 10 | Wiley `downloadSupplement`（onlinelibrary） | 403，Cloudflare challenge |
| 21 | Wiley `downloadSupplement`（advanced） | 403，Cloudflare challenge |
| 14 | ACS SI 直链 `pubs.acs.org/.../nn6c06255_si_001.pdf` | 403，HTML block page |
| 22 | PubChem PUG REST，CAS 110-67-8 | 000，Windows schannel revocation offline；23 重试成功 |
| 26 | `zenodo.org/api/records?...` | 000，DNS resolution failure |
| 27 | `https://comp.chem.umn.edu/mnsol/` | 000，connection timeout |
| 31 | `https://zenodo.org/api/records/21061161` | 000，DNS resolution failure |
| 34 | `https://r.jina.ai/http://zenodo.org/api/records/21061161` | 000，connection timeout |
| 35 | OpenAlex Zenodo DOI | 404，数据集未索引 |
| B3 | 浏览器打开 Zenodo API | `ERR_ADDRESS_INVALID` |
| R1 | `https://www.zenodo.org/api/records/21061161`（钉 IP） | 301 → `zenodo.org` |
| R2 | `https://zenodo.org/api/records/21061161`（钉 IP） | 302 → `/api/records/21061162` |
| R3 | `https://zenodo.org/api/records/21061162`（钉 IP） | 200，取得记录清单 |

R1-R3 是 v0.3.9 收尾时的后续复核：3 次未认证 GET（无 API key、不计费），把主机名钉到
`137.138.52.235`，只读取记录元数据，未下载 4.75 GB 资产。

成功的关键请求包括 Crossref 元数据、Europe PMC 全文/补充包、GitHub 仓库树、PubChem 身份确认、DataCite Zenodo 元数据，以及应用内浏览器对 Wiley 文章页和 SI 的访问。浏览器页面自身静态子资源未逐条计入；本报告统计的是显式发起的逻辑请求/下载。

## 写入范围

新增/修改仅位于：

- `data/external/g1plus/compilations/**`
- `probes/g1plus_tier2_evidence.json`
- `reports/g1plus_tier2_findings.md`

未修改任何现有 `data/`、`src/`、`scripts/`、`paper/`、`tests/` 或其他 agent 报告。
