# G1+ Tier 3–4：可达性审计与本轮结论

日期：2026-09-24
范围：Tier 3（图书馆实体书）与 Tier 4（机构数据库）；含 Perricone 2011 博士论文这条开放全文支线。
执行：Banach（只读 agent，独立预算 40 次）+ 主线程浏览器核验

## 结论

**Tier 3 与 Tier 4 本轮全部未闭环，且全部属于"权限/入口阻断"，不是"查无此值"。**

没有任何一条可以写成 found=false。同时，本轮定位到**一条此前未知的开放全文**（Perricone 2011 博士论文），它是 MOPN 36.0 的底层工作，已确认可访问，数值抽取留待下一步。

## Tier 3：图书馆实体书

| 资源 | 本轮入口 | 判定 |
|---|---|---|
| Riddick, Bunger & Sakano, *Organic Solvents*, 4th ed. (1986) | Google Books API、Open Library、Internet Archive、HathiTrust、WorldCat、LoC | **blocked**：未证明存在可合法下载的免费全文；实体书或馆际互借仍需人工 |
| CRC Handbook, "Permittivity of Liquids" | CHEMnetBASE 官方入口 + Google Books / IA / WorldCat | **blocked**：官方表需机构订阅或实体书 |
| Marcus, *The Properties of Solvents* | 未实际查询 | **blocked**：需馆藏扫描或馆际互借 |
| Aurbach, *Nonaqueous Electrolytes Handbook* | 未实际查询 | **blocked**：同上 |
| Landolt-Börnstein 纸质老版 | 未实际查询 | **blocked**：无 SpringerMaterials 权限时只能走实体馆藏 |

可复核入口（均已验证为合法公开入口，不代表有全文）：

- Riddick: `https://openlibrary.org/search?q=Organic+Solvents+Riddick`、`https://catalog.hathitrust.org/`、`https://search.worldcat.org/`
- CRC: `https://hbcp.chemnetbase.com/faces/contents/ContentsSearch.xhtml`

## Tier 4：机构数据库

| 数据库 | 入口 | 判定 |
|---|---|---|
| Reaxys | `https://www.reaxys.com/` | **blocked**：需机构订阅 / 校园网 / 机构 SSO |
| SciFinder-n | `https://scifinder-n.cas.org/` | **blocked**：需机构订阅，通常还需个人 CAS 注册 |
| DIPPR 801 | `https://www.aiche.org/dippr/projects/801` | **blocked**：需机构或院系授权 |

公开说明页只能证明产品入口存在，不能替代物性记录。

## 本轮新增：Perricone 2011 博士论文（开放全文已定位）

这是本轮 Tier 3–4 唯一的实质进展，也是 MOPN 缺口最有可能的出路。

| 项目 | 内容 |
|---|---|
| 标题 | *Mise au point d'électrolytes innovants et performants pour supercondensateurs* |
| 作者 | Emmanuelle Perricone |
| 年份 | 2011 |
| NNT | `2011GRENI032` |
| HAL id | `tel-00630049`（v1） |
| 元数据页 | https://theses.hal.science/tel-00630049 |
| 全文 PDF | https://theses.hal.science/tel-00630049v1/file/Perricone_emmanuelle_2011_archivage.pdf |
| 开放状态 | HAL 标记 `openAccess_bool=true` |
| 站点保护 | Anubis 工作量证明（`Difficulty: 4`）。经机构 Edge 会话访问后**正常放行**，已在页面上确认标题、作者、年份与"Télécharger pour visualiser"入口 |

**为什么重要**：Perricone 2013（Electrochim. Acta 93, 1）是 ECW-308 为 MOPN 36.00 标注的引用对象，而这篇 2013 论文来自同一作者的博士工作。如果论文正文报告了 MOPN 的介电常数，MOPN 就有机会从 `secondary_compilation_unverified` 升级。

**本轮未完成的原因**（诚实记录）：

- HAL 页面本身可访问，但页面正文不在只读 DOM 作用域内（`document.body.innerText` 为空、`fetch` 不可用）；
- 扩展的资源打包能力对本页面返回 `Asset inventory is no longer valid for this page`；
- 因此**没有读取 PDF 文本，也就没有取得任何 MOPN 数值**。MOPN 的存储值、证据等级与 `model_ready=false` 均未改动。

**下一步（二选一即可）**：

1. 在该 Edge 标签页点开"Télécharger pour visualiser"，确认下载后我读取本地 PDF；或
2. 直接在该 PDF 里检索 `méthoxypropionitrile` / `constante diélectrique` / `36`，把页面截图给我。

## "查无此值" vs "权限阻断"

**在合法可达范围内确实查无此值（found=false）**：

- Perricone 2013 的 Crossref / OpenAlex / OpenAIRE / Semantic Scholar 元数据：无介电数值。
- HAL 中 Perricone 2013 记录：存在但 `open_access=false`，无文件。
- HAL 全文检索 `methoxypropionitrile AND (dielectric OR permittivity)`：HTTP 200，`numFound=0`。
- Semantic Scholar 引用上下文：只有泛化提及，无 MOPN 的 36 / 温度 / 频率 / 方法。
- `36.00` 的温度以外的频率、方法与不确定度：全部 `found=false`。

**因权限或技术原因无法核验（blocked，不得写成无值）**：

- Perricone 2013 正文；Perricone 2011 论文 PDF（本轮）；Deng 2020；Saadi & Lee 1966 正文（2 页）。
- Reaxys / SciFinder-n / DIPPR 801 / Riddick / CRC / Marcus / Aurbach / Landolt-Börnstein。
- 失败请求同样不能当作负面证据：Unpaywall HTTP 422、Europe PMC HTTP 503、CORE HTTP 429、BASE 连接超时、DART-Europe HTTP 301。

## 请求预算与写入状态

| 项目 | 数值 |
|---|---:|
| 可证实的已返回请求 | 22（含失败） |
| 被中断批次的计划请求 | ≤17 |
| 实际总数区间 | 22–39（无法精确恢复） |
| 请求间隔 | ≥1.1 s |
| 写入文件 | **0** |

收到收口指令后未再发起新的探测请求。
