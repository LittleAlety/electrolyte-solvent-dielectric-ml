<!--
Manual snapshot for CI.

Source: 执行手册_探针与周计划.md, the "## 附录 J-补记三" block.
The working manual lives outside this repository (absolute Windows
path), so a runner that has never seen it can only check a committed
excerpt.  This one carries the two round-5 guards:

  * no forbidden token (the fake `evidence_level` value, the retraction
    wording)
  * the Flamme Table 1 entry 21 quote still sits on its labelled line in
    full, with neither archived cell dropped

Regenerate after editing that appendix with:

  python probes/manual_appendix_reconciliation.py --write-manual-fixture

-->
## 附录 J-补记三：两条介电腿闭死与 G1+ 第五轮爬取（2026-09-25）

对应仓库产物：`probes/g1plus_crawl_round5_evidence.json`、`reports/g1plus_crawl_round5_findings.md`、
`tests/test_g1plus_crawl_round5.py`、`probes/g1plus_round5_crosscheck.py` 与其 summary，
决策日志 `reports/decisions_log.md` 的「2026-09-25（续九）」章节。

### 一、FEC 的 78.4 腿：读到原始测量

Kobayashi, Inoguchi, Iida, Tanioka, Kumase & Fukai, *J. Fluorine Chem.* **120**(2), 105–110 (2003)，
DOI `10.1016/S0022-1139(02)00317-2`，**Table 2** 第三条数据行逐字：

```
210   17.3   1497   4.1e   78.4e   1.04e   Our data
```

- 温度：介电值带脚注 e，Table 2 脚注 **e = "At 23 °C."** → **23 °C**；
- 归属：脚注 b = "Physical properties are cited from ref. [11,12] **except our data**"，
  该行 Ref 列即 **"Our data"** → **作者自测，不是转抄**；
- 锁定：该行 mp 17.3 / bp 210 / 黏度 4.1 / ε 78.4 与 Flamme 2017 Table 1 entry 21 的 FEC 四项完全一致。

链条：`ECW-308 entry 166 (78.40) → Flamme 2017 Table 1 entry 21 → [42] Kobayashi 2003 Table 2`。
**温度边界**：规范行存 298.15 K，原始测量在 23 °C = **296.15 K**，差 2.0 K，如实记录不做掩盖。

### 二、碳酸亚乙烯酯的 126 腿：读到原始测量

Saadi & Lee, *J. Chem. Soc. B*, 1966, pp. 5–6，DOI `10.1039/j29660000005`。
实验部分：**E (25°) = 126 ± 1.0**（介电测量池以苯、甲醇、水标定）。
Table 2「Physical properties of some cyclic carbonates at 25°」列 Vinylene carbonate **ε = 126**、μ = 4.45 D。
同表旁证：PC 61.0（25 °C）、EC 95.3（40 °C）、氯代 EC 62.0（40 °C）、水 78.5。

**数据集存的 126 本来就是对的**，缺的只是它当时的"身份"（此前记的是开放获取综述正文）。

### 三、两处对上一轮结论的更正

1. **Flamme 2017 承载 FEC 78.4 —— 这是给上一轮补下一层，不是撤回。**
   第四轮写的是"Flamme 2017 未被确立为 FEC 78.4 的原始测量"，**这句本身没有错、也没有被撤回**：
   Flamme 确实不是原始测量，第四轮只是没拿到全文；本轮读到全文后补下结论。
   正文原句：`εr=89.8 for EC and 78.4 for FEC, Table 1, entries 20 and 21`；
   Table 1 entry 21 逐字：`17.3 210 4.1 78.4 4.70 1.50 (70.70) 5.0 6.6 (Pt) [36],[42]`。
   另修正一处下标错误：Crossref `reference.key` 相对方括号编号有 **+3 偏移**，校正后 `[42]` = Kobayashi 2003。
   正确表述分两层：**Flamme 是承载者，Flamme 不是原始测量。**
2. **Saadi 1966 标识符彻底定案**：原文 + 已登录 Reaxys 双向确认该 DOI 是碳酸亚乙烯酯论文，
   Reaxys 把该引用挂在 vinylene carbonate 行（CAS 872-36-6，RN 105683）的
   "Dielectric Constant - 1" 分类下。**仓库此前把它当腈类票据是仓库的错，标识符本身无误。**
   补充事实：该 Reaxys 记录六个数值列**全为空**，只有 Reference 有值——索引知道有人测过，但不给数。

### 四、受限互证：同源确认 ≠ 独立互证

| 目标 | 判定 | 依据 |
|---|---|---|
| 己二腈 / 戊二腈 | **同源确认** | 受限记录与数据集行引用**同一 DOI** `10.1021/je300958c` |
| 四甘醇二甲醚 / 四氢呋喃 / NMP | **独立互证** | 受限引用与数据集来源无交集 |
| 二甘醇二甲醚 | **混合** | 一条同源（Lago 2009）+ 两条独立 |

计数 `same_source 2 / independent 3 / mixed 1 / no_capture 10`。
**两个腈类只有"抄写正确"级别的证明，没有独立互证**，不允许后续美化成"独立验证通过"。

压力闸门：生成器实现 90–110 kPa 常压窗口；NMP 的 Uosaki 1996 是 100 kPa–250 MPa 压力序列，
保留 5 条窗口内近室温行、**排除 5 条加压行**，无加压值进入比较。

### 五、四个数据源/网站的结论

| 来源 | 判定 |
|---|---|
| Materials Project | **不适用**（SiO₂ 对照 200/total_doc 322 证明 key 有效；EC/PC/乙腈均 total_doc 0；暴露的是晶体计算介电量） |
| NIST WebBook | **零命中**（53 个缓存页检索 dielectric/permittivity/epsilon/ε 全 0；水/甲醇/乙醇/丙酮正对照亦 0） |
| CatalystHub | **入口不可达**（三个测试两个超时；相似域名身份未确认；密钥未外发） |
| SpringerMaterials / 上海有机所库 | **当前都打不开**（用户确认）→ 本轮**没有从这两处取得任何新抓取**，涉及这两处的受限陈述均为对 2026-09-23 磁盘抓取的重读。**但本轮确实新增了受限材料**，来自另外几个受限源：Kobayashi 2003、Saadi & Lee 1966、Reaxys 抓取、Flamme 2017 HZDR 副本（清单见证据文件 `new_restricted_materials_this_round`） |

### 六、请求预算

Tesla 40 / Peirce 40 / Ampere 40 / Pasteur 10，**合计 130 次**；四个 agent 均未突破 40 次/人子上限；
用户 500 次/小时硬上限未被接近；主线程未发出计量 API 调用（Reaxys 走浏览器已登录会话，两份 PDF 由用户提供）。

### 七、仍未闭环（按优先级，已更新）

1. ~~**Saadi & Lee 1966**：VC 的原始测量。~~ **已结清**（本轮读到 E(25°) = 126 ± 1.0）。标识符更正同时结清。
2. ~~**Flamme et al. 2017**：FEC 78.4 分支的上游。~~ **已结清**（全文已读，确认为承载者而非原始测量）。
3. **Hagiyama et al. 2008**（`10.1246/cl.2008.210`）：FEC **107** 腿候选原始测量，OUP 403 / J-STAGE 404。
4. ~~**Ue et al. 2014 专著章节**（`10.1007/978-1-4939-0302-3_2`）：107 腿另一条候选，Springer 身份认证。~~ **已于 2026-09-25 在汇编层读到**：Table 2.3（印刷页 101）给 `107`，正文（印刷页 105）归源 Hagiyama 2008 `[25]`；原始 Hagiyama 仍未读。
5. **Ue, Ida & Mori 1994**（`10.1149/1.2059270`）：MOPN 具名主来源候选；Reaxys 侧已确认无介电分类。
6. ~~**v0.3.12 数据修订**：把两条字段级补丁落地并重跑全部哈希钉点（补丁全文见证据文件 `backlog`）。~~
   **已结清（2026-09-25，v0.3.12）。** 落地结果：
   FEC 存值 `dielectric 102 → 78.4`、`T_K 298.15 → 296.15`、`temperature_source → reported`、
   `evidence_level → primary`、`source_quality → primary_experimental`、
   `source_doi → 10.1016/S0022-1139(02)00317-2`、`source_table → Table 2`、`notes` 按原始测量重写，
   `conflict_status → primary_78.4_landed_107_leg_unread`，`model_ready` 保持 false；
   VC 数值不动，只改身份字段（`evidence_level → primary`、`source_quality → primary_experimental`、
   `temperature_source → reported`、`source_doi → 10.1039/j29660000005`、`source_table → Table 2`、
   `uncertainty_kind → reported` + `uncertainty_value 1.0`、`notes` 按原始测量重写）与
   `conflict_status → knovel_78_127_interval_contains_primary_value`，`model_ready` 保持 false。
   两行的 license 三列按付费原始源清空、`redistribution_status` 保持 `allowed`（与既有 PC/EC primary 行同形）。
   钉点：规范哈希 `765fd8e0…646b60` → `1b285fe8…22456`；246 行 × 38 列不变，
   240 条 `model_ready=true` 行**逐字节未变**，变化仅 FEC 与 VC 两行；补丁文件 33 → 30 行。
   **枚举沿用仓库既有取值 `primary` / `primary_experimental`；每条补丁的逐字替换 `notes` 见证据文件 `backlog`。**
7. **受限目录 4 个未取值目标**：EC（`SMI_SC_31657`）、GVL（`SMI_SC_31853`）、DME（`SMI_SC_31827`）、
   环丁砜（`SMI_SC_31784`）——有目录记录、无抓取值，需 SpringerMaterials 恢复可达。
8. **温度带决策**：33 条 A 类零频候选（18-crown-6、butanedinitrile）全在近室温带之上。
9. **DC-200 成员表**：需向作者索取数据可用性，属"发布缺失"而非"访问失败"。

### 八、验证快照

`tests/test_g1plus_crawl_round5.py` **12 项断言全通过**；
`probes/g1plus_round5_crosscheck.py` 可复跑并复现 tracked summary；
规范数据集仍 246 行、`changed_fields = []`、sha256 `765fd8e0…646b60`（本轮未改任何单元格）。

> **v0.3.12 后续修订（2026-09-25，已落地）。** 上面这一行是**第五轮当时**的快照；随后独立的 v0.3.12 数据修订把 FEC 与 VC 两条字段级补丁落地，
> v0.3.12 规范哈希为 `1b285fe852c13a99e26cc94e85ffab389857351cd4fca36aed0ccf3f40d22456`（v0.3.11 的 `765fd8e0…646b60` 为历史值）。
> **v0.3.13 当前状态（2026-09-25）：** 当前规范哈希为 `a446c216874538d900e9f3ebbf18178926b812b77a213a395f4ff8cddfc01085`（v0.3.13 首稿 1a6b6bad…，提交前复审修正 Kobayashi 2003 Table 2 页码后重钉为现值）；仅 FEC 的 `conflict_status` 与 `notes` 变化，246 行 × 38 列不变，240 条 `model_ready=true` 行逐字节未变。
> **v0.3.14 当前状态（2026-09-25，D2 落地）：** 当前规范哈希为 `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`（v0.3.13 的 `a446c216…c01085` 为历史值）。仅 4 条越界行的 `gate_flags` 与 `notes` 变化，246 行 × 38 列不变，240 条 `model_ready=true` 行逐字节未变。

### 九、第二轮对抗复审收口（2026-09-25，v0.3.12）

- 触发：`adversarial-review-optimize` skill 的 fresh re-review。基线 `024be15`，修复 revision `dd2a37d`，复审记录 `abece75`，三重提交均已推送 `origin/main`。
- 第一轮 finding：Turing 发现 1 Important——旧 `verify_v032_benchmarks.py` 对已知坏状态
  `source_count=246 / excluded_count=5 / excluded_not_in_source=[]` 仍给 `27/27 PASS`；
  Euler 发现 2 Important——week7 生成器仍写 v0.3.12 “without moving a dielectric value”、week7/week8 缺 README。
- 修复：`probes/v032_ablation_summary.json` 现记录 `source_path=data/dielectric_v032.csv`、
  `source_sha256=39d15e161a4fb5cf6dddf31749144ce038078823f7ed02aacbead5a1d75b30be`；
  verifier 新增 `v0.3.2 lineage source provenance` 并 pin `245 / 4 / [OOWFYDWAMOKVSF-UHFFFAOYSA-N]`；
  新增“坏状态必须 FAIL”的回归测试；week7 叙事改为 FEC `102 → 78.4`；
  week7/week8 导出器生成 README 并纳入 `SHA256SUMS`。
- 复审 verdict：Turing 对 `dd2a37d` 判 `No Critical or Important findings; Ready.`；
  Euler 对最终交付包判 Ready，未发现剩余 Critical/Important/Minor。
- 最终验证：`pytest -q -p no:cacheprovider` **729 passed**；`ruff check .` All checks passed；
  7 个 verifier 全绿；week7 manifest `[PASS]`（61 文件 / 60 条目）、
  week8 manifest `[PASS]`（75 文件 / 74 条目）。
- §九复审收口时规范哈希为 `1b285fe852c13a99e26cc94e85ffab389857351cd4fca36aed0ccf3f40d22456`；v0.3.13 后当前值为 `a446c216874538d900e9f3ebbf18178926b812b77a213a395f4ff8cddfc01085`；
  本轮复审只动验证、叙事与交付包，不改任何数据单元格。

### 十、v0.3.13：FEC 107 腿在汇编层读到（2026-09-25）

- 突破：Ue et al. 2014 专著章节（DOI `10.1007/978-1-4939-0302-3_2`，*Electrolytes for Lithium and Lithium-Ion Batteries*，Modern Aspects of Electrochemistry 58，pp. 93–165）
  在本轮以直连 HTTP 200 取得**完整 73 页 PDF**（2,721,678 B，sha256 `88931e6a…c0eefe`）。手册此前记录的「Springer 身份认证墙」不再成立；
  该 PDF 只存入 git-ignored 的 `data/external/g1plus/tier3/`，**不随数据集再分发**。
- 读到的值：Table 2.3「Physical properties of fluorinated solvents」印刷页 101 列出
  `4-Fluoro-1,3-dioxolan-2-one (FEC)  106  1.50  107  4.1  -13.30  1.45`，即 `eps_r = 107`。
- 归属链（决定这 107 值多少）：该表整体来源是正文印刷页 100 声明的两篇 Sasaki 综述 `[4]`/`[5]`，FEC 行**没有逐行脚注**；
  正文印刷页 105 把 FEC 的相对介电常数与黏度数据归到 `[25]` = **Hagiyama et al. 2008, Chem. Lett. 37, 210–211**，即数据集早已具名的原始候选。
  因此结论是：**107 在汇编层已读到，原始测量仍未读到**——它与 Hagiyama 票据是同一件事的两层，不是两条独立腿。
- 数据动作（v0.3.13）：FEC 行 `conflict_status` 由 `primary_78.4_landed_107_leg_unread` 改为 `primary_78.4_landed_107_leg_read_in_ue2014_compilation`，同轮内再追加下游温度冲突标记，终值 `primary_78.4_landed_107_leg_read_in_ue2014_compilation_plus_40C_temp_conflict`；
  `notes` 按上述两层重写。`dielectric` 仍 **78.4**、`T_K` 仍 **296.15**、`model_ready` 仍 **false**；246 行 × 38 列不变，240 条 `model_ready=true` 行逐字节未变。
- 钉点：规范哈希 `1b285fe8…22456` → `a446c216…c01085`（v0.3.13 首稿为 `1a6b6bad…3ed55`，提交前复审修正 Kobayashi 页码后重钉）；v0.3.2 lineage 保持 `245 / 4 / [OOWFYDWAMOKVSF-UHFFFAOYSA-N]`，v0.3.3 lineage 保持 236 拟合行。
- **重跑而不是重钉**：三个 ML 摘要（v0.3.2 ablation、v0.3.3 ablation、Onsager delta）全部真正重跑，diff 仅 `dataset_sha256` / `exclusions_sha256` / `generated_at`
  （v0.3.3 摘要同时补齐 `source_path` / `source_sha256`），**所有指标、折与预测逐字节未变**；四个轻量探针重跑；四个静态证据 JSON 重钉 `canonical_sha256` 并累积修订注记。
- 仍未闭环：Hagiyama et al. 2008（`10.1246/cl.2008.210`）本轮仍 OUP 403 / J-STAGE 404；受限目录 4 个未取值目标、MOPN 独立一手确认与 GFN2-xTB 特征行、温度带决策、DC-200 成员表不变。
- 拒绝的线索：同章节 ref `[57]` 是 **fluoroacetonitrile**（Electrochemistry 2007, 75, 611–614），不是 3-methoxypropionitrile，已明确剔除，避免污染 MOPN 票据。
- 证据文件：`probes/g1plus_ue2014_chapter_evidence.json`、`reports/g1plus_ue2014_chapter_findings.md`、`tests/test_g1plus_ue2014_chapter.py`。

### 十一、v0.3.13 补充：FEC 78.4 的「40 °C」是下游转述冲突（2026-09-25）

- 触发：v0.3.13 落地后，复核发现同组的 Nanbu et al. 2007（*Electrochemistry* 75(8) 607–610，印刷页 608）把**同一个 Kobayashi 测量**写成 40 °C：
  `Strange to say, the relative permittivity of FEC (78.4 at 40 C)4) is lower than that of EC (89.78 at 40 C).12)`；
  其 ref 4) 逐字为 `M. Kobayashi, T. Inoguchi, T. Iida, T. Tanioka, H. Kumase, and Y. Fukai, J. Fluorine Chem., 120, 105 (2003)`，即本行已引的同一篇。
- 一手复核（视觉判读，不用纯文本抽取）：把 Kobayashi 2003 Table 2 所在页以 **600 dpi 渲染成图**逐格核对，
  FEC 行上标确为 `4.1^e / 78.4^e / 1.04^e`；表下脚注逐字 `c At 40 °C.` / `d At 20 °C.` / `e At 23 °C.`；
  EC 行（90）用 `c`（40 °C）、PC 行（65）用 `d`（20 °C），说明脚注字母在该表中确有区分作用。**一手脚注只支持 23 °C。**
- 冲突性质：Nanbu 把**介电与黏度两个量同时**从 23 °C 搬到 40 °C，属系统性温度移位，不是第二组测量；
  未发现 Kobayashi 存在 40 °C 版本。按「一手源优先、不平均」：**`T_K` 维持 296.15 K，不改 313.15 K**。
- 竞品腿的温度也一并钉住：107 在**两篇开放 2013 年论文**里都带温度——
  Nambu et al., *Electrochemistry* **81**(10) 817（印刷页 817）`The relative permittivity of FEC (about 107 at 25 C)5`；
  Nambu et al., *Electrochemistry* **81**(10) 820（印刷页 820）`was comparable with that of FEC (about 107 at 25 C).4`；
  两处 ref 均指向 **Hagiyama et al. 2008, Chem. Lett. 37, 210–211**。
- 结论性读数：两条腿（78.4@23 °C vs ~107@25 °C）**近乎同温**，差 2.00 K，**不能**用温度解释掉，仍是未决数值冲突。
- 数据动作：`conflict_status` 追加 `_plus_40C_temp_conflict`；`notes` 与排除单 `evidence_b` 增记温度冲突。
  `dielectric` 仍 **78.4**、`T_K` 仍 **296.15**、`model_ready` 仍 **false**；246 行 × 38 列不变，240 条 `model_ready=true` 行逐字节未变。
- 钉点：规范哈希 `ed3f446b…c546` → `a446c216…c01085`（v0.3.13 首稿为 `1a6b6bad…3ed55`，提交前复审修正 Kobayashi 页码后重钉）。
- 证据文件：`probes/g1plus_fec_temperature_attribution_evidence.json`、`reports/g1plus_fec_temperature_attribution_findings.md`、`tests/test_g1plus_fec_temperature_attribution.py`。
- 工具提示：`jstage_2007_607.pdf` 的**纯文本抽取会隐藏全部数字串**（嵌入字体编码损坏），必须用 PyMuPDF 重抽或直接渲染页面；这正是该 40 °C 说法在第一轮漏检的原因。

### 十二、v0.3.14（D2）：4 条无 xTB 特征行改为显式越界标注（2026-09-25）

- 决策：`v0.3.14` 整表特征协议迁移**不授权**——为 4 行边界分子迁移 246 行的特征协议，代价/收益不成立且违反冻结纪律。
- 对象与理由：`GSGLHYXFTXGIAQ-UHFFFAOYSA-M`、`IXQYBUDWDLYNMA-UHFFFAOYSA-N`、`JWFPQAXAGSAKRF-UHFFFAOYSA-N` 三行是离子液体
  （介电常数频率依赖强、电导主导，本就不属于纯分子溶剂数据集刻画的对象），`FYOFOKCECDGJBF-UHFFFAOYSA-N` 是五羰基铁（有机金属）。
- 落法：共享词表新增 token `out_of_scope_ionic_or_organometallic`；经 `data/processed/dielectric_v03_provenance_patches.csv`
  以 4 条 patch 追加到上述 4 行的 `gate_flags`（不覆盖原有 `zero_frequency|pure_component|experimental|…` token），并各补一条 `notes`；
  由 `build_dielectric_v03.py` 从输入可复现重建（重建前已逐字节验证过旧输入能重现旧 CSV）。
- **`model_ready` 保持 `true`，不改 `false`。** 该列的语义是「取值是否因来源冲突/待主证确认而不应进入拟合」，不是「化合物是否在模型适用域内」；
  这 4 行没有来源冲突，属适用范围排除。两条独立只读审计（Rawls 与主线程）一致确认：改成 `false` 会同时打破
  `tests/test_xtb_fragment_geometry_defect.py`（`failed_physical_feature_count == 4`、`model_ready == 240`）、
  `tests/test_verify_v032_benchmarks.py`（withheld 恰 1 行且必须为 VC）、`tests/test_dielectric_representation_ablation.py`
  （非 ready 行数 6、withheld 仅 VC）等 7 处硬断言，并把它们错误地重新定义成「来源冲突待确认」。
- 钉点：`a446c216…c01085` → `ff214293…35ccce4`。
- **重跑而不是空口重钉**：v0.3.3 消融探针本轮**真正重跑**（89 s）；`cv.csv`、`predictions.csv`（7081 行）、`repeats.csv`、PNG 与
  全部 summary 指标逐字节一致（两个产物 CSV 的字节差异仅为探针写出的 CRLF 与仓库 `eol=lf` 行尾，内容逐行完全相同）。
  四个轻量探针（nbs514 频率闸门、nbs514 alpha 谐调、手册对账、Onsager delta）与 `g1plus_round5_crosscheck` 亦全部重跑，
  diff 仅限 digest 与 `generated_at` 字段。
- 未改动：236 行冻结拟合集、`model_ready=true` 集合、`data/dielectric_v032.csv`、排除单 5 行；
  v0.3.2 lineage 保持 `245 / 4 / [OOWFYDWAMOKVSF-UHFFFAOYSA-N]`，v0.3.3 lineage 保持 236 拟合行。
- 已知残留（不隐瞒）：`read_modelling_rows` 仍把这 4 行归入 `failed_physical_feature`（它们确实 xTB 失败），越界语义由 `gate_flags` 承担；
  把 `out_of_scope` 提升为独立记账分桶属 schema 变更，留给后续版本，不在本轮夹带。
- 证据文件：`probes/dielectric_v03_summary.json`、`probes/dielectric_v03_representation_ablation_summary.json`、
  `probes/v032_ablation_summary.json`、`data/processed/dielectric_v03_provenance_patches.csv`。

## 附录 J-补记四：4 条 model_ready 行的 xTB 特征失败——诊断轮与恢复可行性判定轮（2026-09-25）

对应仓库产物：`probes/xtb_fragment_geometry_defect.py`、`probes/xtb_recovery_probe.py`、
`reports/g1plus_xtb_fragment_geometry_defect.md`、`reports/g1plus_xtb_recovery_feasibility.md`、
`probes/g1plus_xtb_fragment_geometry_defect.json`、`probes/g1plus_xtb_recovery_probe.json`、
`tests/test_xtb_fragment_geometry_defect.py`（15 项）、`tests/test_xtb_recovery_probe.py`（16 项）。
对应提交：`45d81eb`（诊断轮）与 `d3de14c` + `29ab05b`（恢复可行性判定轮 + 复审措辞修复）。

### 一、问题

v0.3.13 的规范数据集有 246 行、其中 240 行 `model_ready=true`，但冻结基准的拟合集只有 **236 行**。
差的这 4 行不是数据缺失，而是**物理特征没算出来**：3 个离子对 + 1 个五羰基铁。
此前只留下一句不透明的 `exit code 128`。

### 二、诊断轮（`45d81eb`）：把报错换成可复现的几何判据

- 根因之一是多片段分子的起始几何：`generate_3d_xyz()` 把各片段叠在一起，
  跨片段最短原子距离只有 **0.000–0.840 Å**，物理上不可能。
- 修法（逐片段打包）能把该距离抬到 **3.000–4.328 Å**，但**只消除重叠、救不回这 4 行**：
  三个离子对仍在 xTB 里 `exit 128`；五羰基铁的库存 SMILES `[C]=O.[C]=O.[C]=O.[C]=O.[C]=O.[Fe]`
  是 **6 片段、无 Fe–C 键**（它忠实转写自 `InChI=1S/5CO.Fe`，而该 InChI 不表达 Fe–C 键）。
- 因此修法只以探针形式提供；改 `generate_3d_xyz()` 会让冻结特征表与代码不再自洽，
  落地必须作为独立一轮 v0.3.14。

### 三、恢复可行性判定轮（`d3de14c`）：先纠一条判据错误

上一轮探针把「成功」定义成 stdout 出现 `normal termination of xtb`。**这个判据是错的**：

1. xTB 6.7.1 把该串打到 **stderr**（逐字 `b'normal termination of xtb\r\n'`），stdout 0 命中；
2. 冻结运行器 `scripts/run_xtb_physical_features.py:279-285` 还有 `.xtboptok` 哨兵兜底——
   stdout 无标记串时，只要哨兵存在就把标记串补进文本再解析。

正确判据：`exit code == 0` 且 `xtbopt.xyz` 存在 且（stdout 标记串 或 `.xtboptok`）且四个特征全部解析成功。
抽检冻结成功产物 `data/interim/xtb_features/AFBPFSWMIHJQDM-UHFFFAOYSA-N/xtb.out`（42 614 字节）
确认不含该串、但哨兵与 `xtbopt.xyz` 都在。

### 四、三个离子对：冻结口径全失败，但有 4 个协议对三者全部被接受

起点是逐片段打包几何。每格写「冻结运行器是否接受 / 几何优化是否收敛」：

| 协议 | 1,3-二甲基咪唑鎓二甲基磷酸酯 | 1-丁基-3-甲基咪唑鎓 PF₆ | 1-丁基-2,3-二甲基咪唑鎓 PF₆ |
| --- | :---: | :---: | :---: |
| 冻结口径 `--opt --gfn 2 --chrg 0 --uhf 0` | ✗ exit 128 | ✗ exit 128 | ✗ exit 128 |
| `--etemp 1000` | ✓ / geoopt ✗ | ✓ / geoopt ✓ | ✓ / geoopt ✗ |
| `--etemp 5000` | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ |
| `--acc 5.0` | ✗ exit 128 | ✗ exit 128 | ✗ exit 128 |
| `--etemp 5000 --acc 5.0` | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ |
| `--alpb acetonitrile` | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ |
| GFN-FF 预优化 → GFN2 | ✓ / ✓ | ✗ exit 128 | ✓ / ✓ |

- **4 个协议**被冻结运行器对三者全部接受（`--etemp 1000`、`--etemp 5000`、`--etemp 5000 --acc 5.0`、
  `--alpb acetonitrile`）；其中 **3 个**同时几何全部收敛。
- **只放宽 SCC 精度阈值（`--acc 5.0`）单独无效** ⇒ 原失败不是阈值太严，
  而是电荷分离体系在默认 300 K 电子温度下的 SCF 行为本身。
- `--etemp 1000` 虽被接受，但 2/3 的几何优化未收敛（梯度 0.0018 / 0.0051 Eh/α）——「运行器接受」≠「物理到位」。
- `--etemp 5000`（梯度 0.00044–0.00056 Eh/α）与 `--alpb acetonitrile`（0.00040–0.00070 Eh/α）
  两个**单项**改动都让三者既被接受又收敛。
- GFN-FF 预优化只对 **2/3** 有效，**不能**作为三者统一替代。

### 五、五羰基铁：至少 4 个「既能净化、又能嵌入」的结构

上一轮「单纯换 SMILES 不够」需要**上调**为「存在可行写法」（**不构成穷尽性证明**）。
最优候选 `[Fe](<-[C]=O)(<-[C]=O)(<-[C]=O)(<-[C]=O)<-[C]=O`：分子式 `C5FeO5`、净电荷 0、单片段、
5 条 `C->Fe:DATIVE` 配位键、Fe–C 键长 **2.0914–2.1328 Å**；默认 ETKDG（seed 42）返回 **-1**，
打开 `useRandomCoords=True` 返回 **0**。已记录可行候选 4 个。

该族写法用括号化的 `[C]=O` / `[C-]=[O+]` 配体 + `<-` 配位键，绕开中性 `C#O` 里 O 三价的净化错误；
对照的 `[Fe](C#O)...` 写法净化失败。**这是一个建模选择**——库存 InChI 表达不出 Fe–C 配位作用。

### 六、决定性负结论：拯救协议不是协议中立的

三个在冻结协议下本来就成功的对照，从**各自冻结起始几何**出发，只改 `--etemp 5000`：

| 对照分子 | 偶极 | HL-Gap | 极化率 | 总能量 |
| --- | ---: | ---: | ---: | ---: |
| 丙-1-醇 | 0.0000% | 0.0000% | 0.0000% | 0.0000% |
| N-甲基苯胺 | 4.25% | 0.93% | 0.0004% | 0.0046% |
| 三乙基戊基铵 双(三氟甲磺酰)亚胺（离子液体） | **40.36%** | **82.78%** | 0.0043% | 0.0657% |

最大相对位移 **0.82779**。丙-1-醇的偶极与 HL-Gap **完全未变**，极化率与总能量只有 1e-8 量级漂移；
该离子液体对照在 `--etemp 5000` 下**几何优化不再收敛**。

⇒ 这排除了**全表统一的「每个特征加一常数」式校正**；按分子类别分别校准、分层建模、
或给这 4 行单列补偿项**都没有排除**，而这类做法本身要引入新假设与新的泄漏风险。
注意本轮只有**一个**离子液体对照，「漂移集中在离子液体这一类」是**观察**，不是已证的一般规律。

### 七、判定与 v0.3.14 闸门

**这 4 行技术上可救回，但不能在原地救回。**

- 只对新行换口径 ⇒ 特征表并存两套电子结构口径，位移最大的正是新增那一类 ⇒
  埋下一个按分子类别分布的系统偏差隐患。
- 对全部 246 行换同一新口径 ⇒ **不能假定逐行逐特征都会变**（丙-1-醇已实测偶极与 HL-Gap 完全不变），
  但 236 行拟合集、全部基准数字、全部骨架/共形结果都必须在整表重跑后重新确认并重钉。

**因此 v0.3.14 若要落地，必须定位为一次整表协议迁移，而不是一次「补 4 行」的增量修复。**
迁移前要先决定：接受全表重跑后的新基准，还是保持 236 行现状不动。**执行侧不替项目做这个决定。**

### 八、数据动作与钉点

- **数据动作：无。** 没有改 `generate_3d_xyz()`，没有改冻结的 `--opt --gfn 2 --chrg 0 --uhf 0` 口径，
  没有改任何数据集单元格、特征表、排除单、交付包或论文草稿。
- 规范哈希 **`a446c216874538d900e9f3ebbf18178926b812b77a213a395f4ff8cddfc01085`** 不变；
  246 行 × 38 列、240 条 `model_ready=true` 逐字节未变；4 行仍不进拟合集，236 行拟合集不变。
- `--etemp 5000` 一类结果**没有**写进 `data/processed/dielectric_physical_features_v03.csv`。

### 九、请求预算

外部计量 API 调用 **0 次**（纯本地 xTB 6.7.1 + RDKit）；未触及用户 500 次/小时硬上限。

### 十、对抗复审

- 第一路（只读）：Not Ready（0 Critical / 2 Important / 3 Minor）→ 13 处逐条修复 → delta 复审 **Ready**。
- 收口轮换另一名只读 Reviewer 审报告、JSON 证据与成果汇总：Not Ready（0 Critical / 4 Important / 2 Minor）→
  4 项 Important 逐条复核成立后最小修复（协议计数改正为「4 个被接受 / 3 个几何全收敛」、
  删去与本轮 JSON 冲突的「逐特征逐行都会变」并补丙-1-醇反例、成果汇总 §12 当前 pytest 改 771、
  收窄 GFN-FF 的统一替代表述）→ 终轮 delta **Ready，无新增发现**。
- 复审发现的一处**上一轮遗留事实错误**：报告 §五原把 GFN-FF 预优化列为三者统一替代，实际只对 2/3 有效，已改。
- 复审登记的 Minor 已在收官优化轮关闭：Fe 结构证据补 `default_embed_return` / `random_coords_embed_return` /
  `formal_charge` / `fe_c_bond_types`（键型与方向取自分子图，**嵌入失败时也能读出**），并加不变量与回归测试。

### 十一、验证快照

`pytest -q -p no:cacheprovider` **771 passed**；`ruff check .` All checks passed；7 个 verifier 全绿
（`verify_dielectric_v03` digest = `a446c216…c01085`）；week7/week8 manifest 双 PASS；
`probes/xtb_recovery_probe.py --check` = evidence invariants hold；`tests/test_xtb_recovery_probe.py` **16 passed**。

### 十二、仍未闭环（按优先级，已更新）

1. **v0.3.14 协议迁移决策**（本轮新增的硬闸门）：整表重跑换新基准，还是保持 236 行现状不动。**需项目决策，不由执行侧单方面选择。**
2. **Hagiyama et al. 2008**（`10.1246/cl.2008.210`）：FEC **107** 腿候选原始测量，OUP 403 / J-STAGE 404。
3. **受限目录 4 个未取值目标**：仅作受限交叉验证，数值不入可分发数据集。
4. **MOPN**：已有开放获取的同一作者学位论文给出 36 @25 °C，缺**独立一手确认**与 GFN2-xTB 特征行。
5. **温度带决策**：33 条 A 类零频候选（18-crown-6、butanedinitrile）全在近室温带之上。
6. **压力闸门**：145 条 dimethyl ether 高压序列；**频率闸门**：550 条 A 类 + 344 条 B 类变频候选。
7. **DC-200 成员表**：需向作者索取数据可用性（属发布缺失，不是访问失败）。

### 十三、证据文件

- `probes/xtb_fragment_geometry_defect.py` / `probes/g1plus_xtb_fragment_geometry_defect.json`
- `probes/xtb_recovery_probe.py` / `probes/g1plus_xtb_recovery_probe.json`
- `reports/g1plus_xtb_fragment_geometry_defect.md` / `reports/g1plus_xtb_recovery_feasibility.md`
- `tests/test_xtb_fragment_geometry_defect.py`（15 项）/ `tests/test_xtb_recovery_probe.py`（16 项）
- `reports/decisions_log.md`（两轮各一节 + 收口复审记录）

## 附录 J-补记五：v0.3.14 全表协议迁移代价（2026-09-25）

对应仓库产物：`probes/xtb_protocol_migration_probe.py`、`probes/g1plus_xtb_protocol_migration_probe.json`、
`reports/g1plus_xtb_protocol_migration_feasibility.md`、`tests/test_xtb_protocol_migration_probe.py`（22 项）。
对应提交：v0.3.14 整表迁移决策卷宗提交（待本轮远端推送，仓库 HEAD 将在本节后补记；数据面仍未改）。

### 一、为什么必须做全表

上一轮只用 3 个对照分子（丙-1-醇、N-甲基苯胺、离子液体）证明 `--etemp 5000` 不是协议中立的，
但无法回答整表迁移会改变多少行。v0.3.14 若落地，必须知道：
**是只救 4 行，还是会让 236 行拟合集与全部基准一起改口径。**

### 二、方法与证据保护

- 候选协议：`--opt --gfn 2 --chrg <q> --uhf 0 --etemp 5000`。
- 每一行从冻结管线实际使用过的**同一个 input.xyz** 重跑，只换电子结构处理；
  因此位移归因于协议，而不是重新嵌入出的几何。
- 缓存配对不放宽：读取 `cache_manifest.json`，按冻结运行器同样的 Python 文本语义（CRLF→LF）
  对 `input.xyz` 计算 SHA-256，必须与 manifest 的 `input_sha256` 完全一致。
- 每次重跑前清除旧 `xtbopt.xyz`、`.xtboptok`、`xtbrestart`、`xtb.out`、`charges`、`wbo`。
- 接受判定复用冻结运行器真实判据；几何收敛单独记录。
- 输出只落 git-ignored 的 `data/interim/xtb_protocol_migration/` 与本证据 JSON。
- 证据 JSON 记录 xTB 可执行文件 SHA-256、版本行、线程数与起始几何来源；迁移没有使用新的几何 seed。

### 三、全表结果

| 指标 | 结果 |
| --- | ---: |
| 冻结成功且严格配对 | **237/237** |
| 被冻结运行器拒绝 | **0/237** |
| 运行器接受但几何未收敛 | **1/237** |
| 任一特征相对位移 >1% | **74/237（31.22%）** |
| 无特征超过 1% | **163/237（68.78%）** |
| 偶极 >1% | 69/237 |
| HL-Gap >1% | 34/237 |
| 极化率 >1% | 9/237 |
| 总能量 >1% | 0/237 |

逐特征最大 mover：

- 偶极：1-butyl-2,3-dimethylimidazolium tetrafluoroborate，1.374 → 5.561 D（+304.73%）。
- HL-Gap：3-butyl-1,2,4,5-tetramethyl-1H-imidazol-3-ium tetrafluoroborate，0.0453 → 0.3900 eV（+760.93%）。
- 极化率：1-ethyl-3-methylimidazolium butylsulfonate，168.1764 → 182.0997 a.u.（+8.28%）。
- 总能量：ethanolammonium nitrate，−9.85899570109 → −9.895725718573 hartree（0.37%）。

HL-Gap 的最大相对百分比被接近零的分母放大，但绝对变化 0.3447 eV 同样可观，不能写成浮点噪声。

### 四、判定与建议

**不把 v0.3.14 当作“补 4 行”。** 整表迁移会改变 74/237 条既有可用行的至少一个特征，
必须整表重跑并重钉全部基准。本补记建议：

1. 当前冻结版保持 236 行不动，4 行继续记 `blocked`，不写“无值”、不写“已恢复”。
2. 若项目确实要覆盖 4 条失败行或统一带电体系口径，另立 v0.4，一次性重跑全部 241 条可用目标
   （237 条现有行 + 4 条恢复路线），再重钉所有基准、骨架留出、共形区间与论文数字。
3. 不建议把两套协议的行直接拼进同一特征表；那会引入按类别的口径断点。

### 五、数据动作与钉点

- **数据动作：无。** 未改 `data/raw/*`、规范数据集、特征表、digest、排除单、交付包或论文草稿。
- 规范哈希 `a446c216874538d900e9f3ebbf18178926b812b77a213a395f4ff8cddfc01085` 不变；
  246 行 × 38 列、240 条 `model_ready=true`、236 行拟合集逐字节未变。
- `--etemp 5000` 的 237 行结果没有写进任何可分发冻结数据。

### 六、请求预算

外部计量 API 调用 **0 次**（纯本地 xTB 6.7.1pre + RDKit）；未触及用户 500 次/小时硬上限。

### 七、仍未闭环

1. **v0.3.14 项目决策**：全表迁移的最后一道闸门仍未关闭；本轮只给出分布证据与执行建议。
2. 4 条失败行的完整恢复路线（离子对 SCF + Fe(CO)₅ 结构表示）仍未落地。
3. `--alpb acetonitrile` 的全表位移分布未测；它不能借用本轮 `--etemp 5000` 的数量结论。
4. 受限目录 4 个未取值目标、Hagiyama 2008 FEC 107 腿、MOPN 独立一手确认等既有未闭环项不变。

### 八、验证快照

探针 `--run --write --threads 1`（237/237 行）与 `--check` 均通过（`evidence invariants hold`，
deep check 现逐行复验缓存 manifest 的可执行文件指纹）；专项测试 `26 passed`；
全量 `pytest -q -p no:cacheprovider` **798 passed**（本轮新增 4 条迁移回归后由 794 增至 798；耗时随机器负载浮动，本机多次全量实测 129–190 s）；
`ruff check .` All checks passed；7 个数据集/基准 verifier、`check_paper_artifact_consistency.py`、
`verify_export_manifests.py`（week7/week8 双 PASS）与手册对账全部通过；规范数据集 digest 未变。
### 九、第三轮只读对抗复审（delta，2026-09-25）

第三轮 Reviewer 提交 **Not Ready（2 Critical / 3 Important / 3 Minor）**，但其行号与当前文件不符，
判断依据是**较早的工作区副本**。在当前修订上用其原攻击向量逐条实测，5 项 Critical/Important **全部被拒**：

1. 把 237 条成功行整体改名 `unmeasured` 并伪造 `reason` —— 拒绝（逐行重解缓存，237 行仍可配对）；
2. 把全部 `frozen_runner_accepts` 自报为 `false` —— 拒绝（不再按自报字段跳过，逐行 `frozen_verdict` 复算）；
3. 篡改 `cache_manifest_sha256` / `start_geometry_sha256` / `run_environment.xtb_executable_sha256` —— 逐条拒绝；
4. 把候选工作目录设为冻结缓存内**尚不存在**的子目录，或冻结缓存根 —— 两例均抛错，`data/interim/xtb_features/__review*` 无残留；
5. 成果汇总 §13 的手册 / fixture 陈旧哈希 —— 本轮按当前实测值重写。

**残留 Minor（记录不做）**：①`check_payload()` 外层 `try/except` 会把多条内部错误压成单条诊断（仍 fail-closed）；
②CRLF 与起始几何两个回归经测试内辅助函数驱动，而非直接经 `resolve_row_cache()`（同文件另有 6 个测试直接驱动生产函数）。
**本轮修正的 Minor**：极化率最大 mover 四舍五入应为 `182.0997 a.u.`（原先写成 `182.0998`）。
第四轮 delta 复审（同一位 Reviewer，钉住哈希后重跑）：5 个攻击向量**全部 BLOCKED**，
但新增 **1 个 Important** —— `_deep_row_problems()` 的缓存 provenance 校验以 `row.get("cache_dir")` 为守卫，
**删掉 `cache_dir` 即可把整段 manifest 指纹 / manifest SHA / 缓存 `input.xyz` 校验一并跳过**
（其最小反例实测返回 `[]`）。本轮已最小修复：①`cache_dir` 改为必填字段；
②`cache_dir` 目录名必须属于该行 InChIKey；③缓存 `input.xyz` 摘要必须同时等于 manifest 与候选起始几何 `start_geometry_sha256`。
新增 2 条回归（专项 26 项），「删光 cache_dir」与「借另一行的合法缓存」两个攻击向量现均被拒。

第五轮 delta 复审（只验本项修复）：**Ready（0 Critical / 0 Important / 1 Minor）**。`..\` 穿越、同 InChIKey 多目录、同步篡改 `start_geometry_sha256` 三个变体均被拒；真实证据 `--check` 仍通过。残留 Minor：`cache_dir` 只用目录名前缀校验归属，未额外断言解析后路径落在冻结缓存之下（三类现有拦截已挡住实际攻击，未复现通过路径，记为后续加固项）。

## 附录 J-补记六：CI 修复轮——全新克隆为什么是红的（2026-09-25）

**起因。** v0.3.14 证据轮（`a5419aa`）在本机全绿，但**全新克隆**的 CI 是红的。
两条根因都与数值无关，而是仓库卫生问题；本地看不到，是因为本机工作区恰好与仓库的存储形态不一致。

### 一、行尾漂移：pin 的是 CRLF 字节

`.gitattributes` 规定文本按 LF 入库（`* text=auto eol=lf`，另有显式 `*.csv` 规则），
但本机有 16 个被跟踪文件在工作区漂成了 CRLF。`probes/g1plus_round5_crosscheck_summary.json`
的 `raw_sha256` 钉的正是那份 CRLF 字节的摘要，于是出现「本机通过、干净克隆不一致」。

处置：把工作区归一为 LF，并**用探针自身重生成** `raw_sha256`（LF 摘要 `6f6c2eb9…654fd0`），
不是手改证据；重生成结果与旧文件逐字段比对**只差这一个字段**。

### 二、ignore 黑洞：验证脚本要读的文件从未入库

`data/processed/*` 与 `data/interim/*` 默认被忽略，只对白名单放行。结果是
`verify_v032_benchmarks.py`、`check_paper_artifact_consistency.py`、`export_week8_results.py`
要读的 9 个文件从未被跟踪：6 个 v0.3.2 消融/CV/骨架产物、2 个 MLP 校准产物、1 份基特征矩阵
（`data/interim/v03_features_original.csv`）。干净克隆里它们不存在，导出与校验必然失败。
处置：加显式 `!` 白名单并入库；week8 交付包随之重生成（包内 11 份 CRLF 副本一并归一为 LF）。

### 三、新增护栏（并做了负向证明）

| 护栏 | 位置 | 作用 |
| --- | --- | --- |
| 行尾策略 | `tests/test_repo_hygiene.py` | 被跟踪文本文件在工作区出现 CRLF 即红 |
| pin 与行尾无关 | 同上 | pin 只被 CRLF 字节满足、与 LF 摘要不符即红 |
| 缺本地缓存的诚实 skip | `tests/test_xtb_protocol_migration_probe.py`、`tests/test_thermoml_local_coverage_probe.py` | 只在 git 忽略的本地状态缺失时 skip，**断言不削弱** |
| 交付包默认范围 | `scripts/verify_export_manifests.py` | 默认覆盖 week1–week8 |

负向证明：临时把 `dielectric_raw.csv` 改回 CRLF 并把 pin 改回 CRLF 摘要，两道护栏**都变红**（2 failed）；
还原后复绿。这是「护栏不是恒真断言」的证据。

### 四、实测与边界

全新 detach 工作树复刻 CI：**24/24 步通过**，其中 `pytest -q` 为 **786 passed / 14 skipped**；
本机含全部本地缓存时为 **800 passed**。提交 `32a8b7f`。

**诚实边界（不回写、不追改）：** 仓库里仍有 3 处 v0.2 时代的历史 pin
（`database_recheck.json` 与 `springer_materials_crosscheck_summary.json` 的 `v02_sha256`、
`v03_baseline_reproduction_summary.json` 的 `exclusions_sha256`）指向**当前仓库中已不存在的旧版本字节**，
其生成脚本已不在仓库内。它们不参与任何 CI 断言，本轮按「历史证据不追改」记录，不臆造重钉。

## 附录 J-补记七：真实 CI 首次转绿——EXE001 与「本机复刻」的盲区（2026-09-25）

**补记六的边界。** 补记六记录的「全新工作树复刻 CI 24/24 步通过」是**在 Windows 上**完成的。
真实 CI（`ubuntu-latest`）在当次推送的 **`Lint project`** 就失败了——本机复刻与真实 CI **不等价**：
两者都要过，但**只有真实 CI 能执行「读文件系统元数据」的那一类判据**。

**证据链（GitHub Actions 实查，非推断）。**

- 当次推送（`a5e6686`，run `36093292552`）的失败步骤是 `Lint project`，日志为
  `EXE001 Shebang is present but file is not executable --> probes/g1plus_ecw308_extract.py:1:1`。
- 往前追溯：`a5419aa`（run `36088228353`）与更早的 `1f31f218`（run `35966915981`，2026-09-24T06:55）
  **同样停在 `Lint project`**。即**自 2026-09-24 起 CI 从未越过 lint**，`Run tests` 一步根本没被执行——
  上一轮修掉的那批 pytest 缺口是**真实缺陷，但当时从未被 CI 触达**。

**根因。** 该文件第一行是 shebang，而 git 索引模式是 `100644`（不可执行）。ruff 的 `EXE001` 读**文件系统执行位**，
Windows 无法表达该位 ⇒ 同一棵树在本机 lint 全绿、在 ubuntu-latest 报错。
**不是 ruff 版本漂移**：本机 0.16.8 与 CI 实装的 0.16.9 在 Windows 上都不报该错；差异来自平台。

**处置。** 该文件确实是可运行脚本（以 `raise SystemExit(main())` 收尾），所以保留 shebang，把索引模式改为 `100755`。
另加**平台无关护栏** `tests/test_repo_hygiene.py::test_executable_bit_agrees_with_the_shebang`：
直接读 git 索引模式，覆盖 `EXE001`（有 shebang 无执行位）与 `EXE002`（有执行位无 shebang）两类；
负向证明：把执行位去掉，该护栏**变红**（1 failed），还原后复绿。

**结果。** 提交 `44c5136`（run `36093852395`）的 `verify` 5m53s、`environment` 1m3s，**两个 job 全绿**——
这是自 2026-09-23T12:08 以来**首次**成功。Linux 侧 `pytest` 为 **783 passed / 18 skipped / 0 failed**（66.96s），
`Lint`、`Compile` 与其余全部校验步骤通过。

**18 个 skip 的口径。** 来自 git 忽略的本地缓存、本机 xTB 可执行文件或外部手册缺失（ECW-308 SI PDF、round2/round4 抓取缓存等）；
本机因这些本地资源存在而多跑若干用例（本机 **801 passed / 0 skip**）——不是数据集或模型平台差异，也没有任何断言被削弱。

**新增纪律。** 凡判据依赖**文件系统元数据**（执行位即是一例），必须以 **git 索引或真实 CI** 为准；
本机 lint 全绿**不构成**这类判据的证据。

## 附录 J-补记八：审查 Minor 优化轮（2026-09-25）

**起因。** 真实 CI 转绿后，只读对抗复查仍留下三个可复现的工程 Minor：仓库卫生护栏的扫描集大于 ruff 实际 lint 集，且 shebang 取自工作区而非 git 索引 blob；`manual_appendix_reconciliation.py --output` 指向仓库外时文件已写出但 `relative_to()` 抛错、进程返回非零；skip 口径被写成“全部是 git 忽略的缓存缺失”，而实际还包含本机 xTB 可执行文件与外部手册缺失。

**处置。**

1. `tests/test_repo_hygiene.py` 现在覆盖 CI 执行 ruff 的五个根目录（`notebooks`、`probes`、`scripts`、`src`、`tests`）与 Python 类后缀，并用 `git cat-file --batch` 读取索引 blob 头部。ruff 的解析 include 另含 `*.md`，但当前 93 个跟踪 Markdown 全为 `100644` 且无 shebang，未形成 `EXE001`/`EXE002` 实际漏报；护栏以 Python 类后缀为适用范围；脏工作区不能再掩盖干净克隆的 `EXE001`。回归固定三种行为：`.sh` 钩子不误报、`.py` shebang 缺执行位会报、反向 `EXE002` 会报。
2. `probes/manual_appendix_reconciliation.py` 新增 `describe_path()`：仓库内写相对路径，仓库外写绝对路径；`--output` 指向 scratch 目录时正常返回 0。新增端到端回归。
3. 手册与决策日志的 skip 口径改为“git 忽略缓存 + 缺失的 xTB 可执行文件 + 缺失的外部手册”，并保留“断言一条不削弱”的边界。

**验证。** 定向测试 30 passed；`ruff` 全绿；本机全量 `pytest -q -p no:cacheprovider` **803 passed / 0 skipped**（184.52 s）；真实 CI 见本轮推送结果。数据面未改：规范数据集 digest 仍为 `a446c216…c01085`。

---

## 附录 K（修订版）：Week 7/8 总结、阻塞裁决 D1–D6 与 Week 9–12 方向

> 修订说明（2026-09-25）：本版取代初版附录 K 的两处判断——①Hagiyama 2008 的 J-STAGE 可达性已被实测 404（见补记四），D3 改为"精确 URL 序列 → 馆际互借 → 汇编层如实声明"三级兜底；②D2 收敛为补记五的建议（保持 236 行冻结、4 行记 `blocked`、另立 v0.4），不再提议 gate_flag 重分类（避免 schema 搅动）。

### Week 7/8 状态（已定案，此处只留索引）
v0.3.3 冻结 246 行（digest `a446c216…c01085`）；PC/EC 入库；适用域改结构 SMARTS 规则（触发率 33.66%，ε>60 覆盖 150/150）；model_ready 闸门泄漏修复，PC/EC 增益坍缩为 +0.0059（p=0.11）；冻结基准（236 行）：hybrid raw R²=0.364 / Spearman 0.828，scaffold 留出 Physical-log R²=0.276 / 0.862；MLP 校准=真负结果；C1 共形边际 0.915 / ε>60 条件覆盖 1.5–26%；C2 排序头负结果；C4 delta 层真实但不具竞争力；C6 温度混合=次要限制。803 测试全绿，真实 CI 绿。

### 对账（Orchestrator 判断正误，诚实记录）
✅ PC/EC 缺口为真且已修复；❌ glyme/glutaronitrile"缺失"系假阴性（v0.1 起以 IUPAC 名在库，俗名搜索所致；别名注册表 + 防漂移测试为系统性修复）；❌ 适用域 Onsager 触发方案被实测否证（0/150），结构规则更优；❌ MLP 校准假设被预注册探针否证。

### 阻塞裁决 D1–D6（修订版）
- **D1 EC 313.15 K**：保留为显式 `extended_temperature` 例外（mp 36.4 °C，无 298 K 常态液态测量）。落法见附录 L-1.1。
- **D2 四条无特征行**：采纳补记五建议——v1.0 保持 236 行拟合集不动，4 行维持 `blocked`（不写"无值"、不写"已恢复"），论文 Limitations 如实说明；若未来要统一带电体系口径，另立 v0.4 一次性整表重跑并重钉全部基准。**不授权 v0.3.14 整表迁移。**
- **D3 FEC 107 腿**：三级兜底——① 精确 URL 重试（`https://www.jstage.jst.go.jp/article/cl/37/2/37_210/_article`，注意补记四的 404 可能来自错误 URL 模式；同时试 CiNii 与 CSJ Journal Archive）；② 学校图书馆馆际互借（通常 1–3 工作日）；③ 若终不可得：论文写"两条未调和的一手腿——78.4@23 °C（Kobayashi 2003 Table 2，已读）vs ~107@25 °C（经 Ue 2014 Table 2.3 及两篇 Electrochemistry 2013 论文转引自 Hagiyama 2008，原文未读）"，维持 `model_ready=false`。**此声明本身即闭环。**
- **D4 MOPN**：维持排除；thesis 为 corroboration；Limitations 记"独立一手测量缺失"。
- **D5 受限 4 目标**：PC/EC 已由 Electrochemistry 2013 转引 Riddick 获得免费旁证（PC 64.92@25 °C vs 库存 64.9；EC 89.78@40 °C vs 库存 90.5@313.15 K，温度对齐）——写入 Technical Validation；GVL/DME 保留为 limitation。
- **D6 DC-200**：先查 GSDS 论文 SI（ACS SI 通常免费），无则邮件通讯作者（模板见附录 L-1.6）；发表后交叉验证资产，不阻塞。

### 科学叙事升级（论文主故事线）
G2 外部测试（PC/EC 预测 21.6/33.7 vs 真值 64.9/90.5）定量了**第三类盲区：极性非质子高 ε 空洞**（环状碳酸酯 μ≈5 D、无 HBD，仍被低估 3 倍）。论文三条边界：缔合盲区（Kirkwood g）、骨架外推（0.276）、极性非质子空洞（G2）。

---

## 附录 L：Week 9 论文冲刺 · 日级作战手册（含 v1.0 冻结闸门）

### L-1 决策落地执行规格（周一–周二，约 1.5 天）

**L-1.1 D1：EC 温度带例外（半天）**
- 数据动作：`data/dielectric_v03.csv` 中 EC 行的 `temperature_band` 已应为 `extended_temperature`——核查确认；论文 Methods 加一句口径定义（模板）：*"The main window is 293.15–303.15 K; ethylene carbonate (m.p. 36.4 °C) is admitted as a single explicit exception at 313.15 K, flagged `extended_temperature`, because no room-temperature liquid measurement exists."*
- 敏感性探针（pre-registered，已于 2026-09-25 落地）：`probes/dielectric_leave_ec_out_sensitivity.py`——冻结折号不变，只把 EC 移出训练折，重跑 Morgan/Physical/Hybrid 三种表示；机读摘要 `probes/dielectric_leave_ec_out_summary.json`，逐 repeat 预测 `probes/artifacts/dielectric_leave_ec_out_predictions.csv`，人类可读报告 `reports/d1_leave_ec_out_sensitivity.md`。结果：Hybrid R² 0.3494→0.3381（95% CI [−0.0243,+0.0018]，p=0.083），三种表示的组内指标排序均不变。无门槛、不参与 v1.0 模型选择；已接入 CI，`verify_d1_leave_ec_out.py` 8/8 PASS。
- 验证：`verify_dielectric_v03.py` 7/7 不动（本探针不改数据）。

**L-1.2 D2：4 条 blocked 行的文档措辞（1 小时）**
- 数据动作：无。只在 `data/processed/dielectric_v03_exclusions.csv` 的 reason 文本与论文 Limitations 中统一口径为 `blocked_pending_v04_protocol_decision`（禁用词：`unmeasured`、`rescued`、`recovered`、`no value`）。
- 护栏：在 `tests/` 加一条 lint 级测试，扫描交付文档禁用词（沿用 manual_appendix_reconciliation 的违禁 token 模式）。

**L-1.3 D3：FEC 三级兜底（周一发起，ILL 周期内并行其他任务）**
- ① 依次尝试：J-STAGE 精确 URL（`/article/cl/37/2/37_210/_article` 与 `_pdf`）、CiNii Research 检索 "Hagiyama fluoroethylene 2008"、CSJ Journal Archive；
- ② 失败即当日提交馆际互借/文献传递申请（给馆员的信息：Hagiyama K. et al., *Chem. Lett.* **2008**, *37*(2), 210–211, DOI 10.1246/cl.2008.210）；
- ③ 等待期把"双腿未调和"声明句先写进论文（占位符标记 `[[FEC-HAGIYAMA-PENDING]]`），ILL 到货后只改一处；`check_paper_artifact_consistency.py` 若做全文扫描，把该占位符登记为已知 token，到货后移除。

**L-1.4 D5：PC/EC 免费旁证入 Technical Validation（2 小时）**
- 动作：新建 `reports/jstage_corroboration.md`，记录 Electrochemistry 2013 两篇论文的转引句原文截图位置、引文链（→ Riddick 4th ed.）、与库存值的偏差（PC 0.02；EC 0.72，温度对齐 313.15 K=40 °C）；
- 论文 Technical Validation 增一小段"restricted-catalog-free corroboration"。

**L-1.5 D4：MOPN（15 分钟）**：Limitations 加一句；无其他动作。

**L-1.6 D6：DC-200（30 分钟发起）**
- ① 下载 GSDS 论文 SI 查成员表；② 无则发邮件。模板：
  > *Dear Prof. [X], We are finalizing an auditable public dataset of static dielectric constants for electrolyte solvents (236 fitted compounds, to be submitted to Scientific Data). Your GSDS work mentions the DC-200 dielectric dataset. Could you share the DC-200 membership list (SMILES/InChIKey) or point us to its SI/Zenodo deposit? We would like to run an InChIKey-level intersection and same-temperature cross-validation, with attribution. …*
- 状态记 `dc200_membership_requested: <date>`；未回复不影响 v1.0。

### L-2 v1.0 冻结闸门（周三，顺序执行，任一红即停）

| # | 闸门 | 命令/动作 | 通过判据 |
|---|---|---|---|
| F1 | L-1.1/L-1.2 落地并 commit | git | 工作区干净 |
| F2 | 数据面零改动确认 | `verify_dielectric_v03.py` | 7/7，digest 仍 `a446c216…c01085` |
| F3 | 全部 verifier | v02(9/9)、v032(7/7)、benchmarks、ablation、scaffold、week1、crosschecks、manifests(week1–8) | 全 PASS |
| F4 | 测试与 lint | `pytest -q` + `ruff check .` | 全绿 |
| F5 | 干净克隆 CI 复刻 | `git worktree add --detach` 24 步流程 | 24/24 |
| F6 | 论文一致性 | `check_paper_artifact_consistency.py` + `build_paper_full_draft.py --check` | PASS |
| F7 | 受限文件泄漏扫描 | `git ls-files` 与 restricted 清单比对 + `git log --diff-filter=A` 抽查 | 0 命中 |
| F8 | 打标与发布 | `git tag v1.0` → push tag → GitHub Release（附 SHA256SUMS 与 verifier 输出） | Release 页可见 |
| F9 | Zenodo | 开启 GitHub–Zenodo 集成→对 v1.0 release 存档→取 DOI→回写 README 与论文 Data Availability | DOI 可解析 |

注意：F8 之前确认 Zenodo 集成已开（先集成后打 tag，否则 archive 触发不到）；若已打过 tag，用 GitHub Release 编辑页重新触发或补发 v1.0.1 说明性 tag。

### L-3 六图规格（周三–周四，每张图：数据源 artifact → 生成脚本 → 验收）

| 图 | 内容 | 数据源 | 脚本 | 验收 |
|---|---|---|---|---|
| Fig 1 | 数据集增长与来源构成（v0.1→v0.2→v0.3 阶梯 + 来源堆叠条） | 三个版本 CSV + summary JSON | `paper/fig1_growth.py` | 数字与 summary JSON 一致（脚本断言） |
| Fig 2 | 化学空间投影（物理特征 PCA/UMAP；碳酸酯/醚/腈/砜家族着色；PC/EC/FEC/VC 标出） | `dielectric_physical_features_v03.csv` | `paper/fig2_chemspace.py` | 4 个标志分子可见； withheld 行用空心标记 |
| Fig 3 | 主 benchmark（236 行冻结表，含 constant 行；repeat 散布误差棒，注明描述性非推断） | `v032_ablation_summary.json` | `paper/fig3_benchmark.py` | 与 JSON 逐数一致 |
| Fig 4 | **钱图 A**：G2 领域差距 parity plot（29 外部化合物，PC/EC 高亮，y=x 线） | `g2_domain_gap_summary.json` | `paper/fig4_domain_gap.py` | 29 点齐全 |
| Fig 5 | **钱图 B**：共形区间条件覆盖塌缩（边际 0.915 vs ε>60 层 1.5–26%，分层柱状） | `dielectric_split_conformal_summary.json` | `paper/fig5_conformal.py` | 与 C1 JSON 一致 |
| Fig 6 | 适用域边界 + 跨源一致性地图（结构规则触发率、Chodera 0.175、受限 0.05、J-STAGE 旁证、FEC/VC 冲突点） | applicability + crosscheck JSON | `paper/fig6_ad_crosscheck.py` | 触发率 33.66% 等数字一致 |

**规范**：脚本只读 artifact 不改数据；每图附生成命令进 README；图注里写清 n 与行数口径（236 vs 205）。

### L-4 三表规格

| 表 | 内容 | 口径要点 |
|---|---|---|
| T1 主 benchmark | Dummy(constant)/Morgan/Physical/Hybrid × raw/log(eps−1)，R²/MAE/Spearman/AUC>30/分层 MAE | 236 行冻结；repeat 散布标注"描述性" |
| T2 骨架/簇留出 | 同五臂 | 明写"结构外推"，Physical-log 最优 0.276 |
| T3 神经基线 | MLP×3 + 校准 MLP + Chemprop | **205 行 v0.2 口径**，表注解释行数差异原因（闸门修复前管线，重跑不回溯——成本/收益不成立，已在 Week 8 记录） |
| T4 行会计表 | 245/246 → 236 血统恒等式（fitted+feature_failures+exclusions+withheld=source） | 审稿人必查项，放 Data Records |

### L-5 逐节写作要点（Scientific Data 格式）

- **Background & Summary**：3 段——需求（电解液筛选缺公开可审计介电数据）→ 资产（246 行、三级来源、逐行溯源、交叉验证链）→ 边界（三盲区一句话预告）。禁用词：solves、accurate prediction、state-of-the-art。
- **Methods**：数据构建（窗口、门旗、冲突处置"不平均不掩盖"）→ 物理特征（xTB 协议钉死版本/参数；4 行 blocked 声明）→ 模型与验证（折号、种子、预注册）→ **Reproducibility 小节**：verifier 清单 + 每个 verifier 一行命令。所有数字必须能被 `check_paper_artifact_consistency.py` 重导出。
- **Data Records**：逐文件列表 + SHA256 + Zenodo DOI + T4 行会计表。
- **Technical Validation**：Chodera（0.175）→ 受限交叉核验（0.05，注明 restricted）→ J-STAGE 旁证（L-1.4）→ G2 外部测试 → 共形条件覆盖 → C6 温度调和（次要限制的定量化）。
- **Usage Notes**：适用域规则 + 三盲区 + "排序/分诊工具"定位 + FEC/VC 冲突使用警告。
- **Limitations**：小样本、单温度为主、conformer 平均偶极未实现、缔合液体出界、MOPN/FEC/VC 未决、tier-4 未核验、IL/有机金属出范围（待 v0.4）。
- **Code Availability**：GitHub URL + v1.0 tag + Zenodo DOI + 环境 pin。

### L-6 周五收口
论文全稿 v0.9（五节齐全、六图三表占位→成图、占位符清单）；周末不排新任务，只留 ILL 等待。

---

## 附录 M：Week 10–12 · 论文对抗审读、投稿包与投稿后 backlog

### M-1 Week 10：论文对抗审读（复用三角色，对象换成论文）

**流程**：writer（Hubble）出全稿 → reviewer（Archimedes，只读）按下方清单攻击 → auditor（Epicurus，只读）独立复核数字 → 修复 → delta 复审至 Ready（沿用"Not Ready/Ready + Critical/Important/Minor"分级与最小修复纪律）。

**审稿攻击清单（按致命度排序）**：
1. **数字对账**：正文/图/表每个数字能否被 `check_paper_artifact_consistency.py` 重导出；205 与 236 两种行数口径是否处处标注；
2. **声明强度**：全文搜 overclaim 词（solve/accurate/universal/generalize/predictive power）；筛选定位声明必须绑适用域；
3. **负结果保留**：C2 排序头、C4 delta 不具竞争力、MLP 校准失败、密度特征无效、PC/EC 增益不显著、共形条件塌缩——六条负结果一条不许删（它们是被拒稿防护网）；
4. **冲突披露**：FEC 双腿、VC Knovel 区间、MOPN 单源、tier-4 未核验、受限数据声明（closed_source/non_redistributable 措辞）逐条在文；
5. **可复现性**：抽查 3 个 verifier 命令在干净克隆上真能跑（F5 已做，复审重做一遍抽样）；
6. **图表自洽**：图注 n 值、误差棒口径（描述性 vs 推断）、单位（D vs a.u. 换算脚注）。

### M-2 Week 11：投稿包（Scientific Data）

- [ ] 格式：Data Descriptor 结构（Background & Summary / Methods / Data Records / Technical Validation / Usage Notes / Code Availability）；无字数硬限但摘要 ≤~170 词；
- [ ] 数据托管：Zenodo DOI（F9）；仓库 README 顶部挂 DOI 徽章；
- [ ] Cover letter 三点卖点：① 首个公开、逐行溯源、可程序化验证的电池溶剂静态介电数据集；② 三层验证（独立 verifier / 跨源交叉核验 / 干净克隆 CI）；③ 把负结果与适用域做成一等公民的方法学示范；
- [ ] 建议审稿人方向：电解质热物性实验家 + ML 分子性质数据集作者（避开有私有介电数据集利益冲突的组）；
- [ ] 许可：数据 CC-BY 4.0，代码 MIT；受限交叉核验文件**不在**发布包（F7 已保证）；
- [ ] 投稿系统信息：作者 ORCID、资助声明、利益冲突声明、Data Availability 段（Zenodo DOI + GitHub tag）。

### M-3 Week 12：缓冲 + 投稿后 backlog 排期

投稿发出后立即解锁（优先级序）：
1. **v0.4 决策点**：是否整表迁移电子结构协议救 4 行 blocked + 统一带电体系口径（补记五证据：74/237 行位移 >1%，故必须整表重跑+重钉全部基准）——建议与"v1.x 多温度观测表"合并成一次大版本，摊薄重钉成本；
2. **N3/N4**（Batt-P30K 预训练迁移、介电×黏度多任务）：v0.4 之后数据面稳定再启动；
3. **DC-200 交叉验证**（若作者回复）；
4. **Hagiyama ILL 到货后**的 FEC 双腿终裁与论文增补（若已投稿则记入修订轮）；
5. 社区贡献通道：`CONTRIBUTING.md` + 新数据提交 issue 模板（字段=gateway schema：SMILES/InChIKey、T_K、ε、来源 DOI、位数、频率）。

### M-4 风险与回退
- **ILL 超过 2 周未到** → 按 D3-③ 声明投稿，不等；
- **审稿人要求 FEC/VC 定论** → 回应策略：冲突记录即数据集立场，提供冲突单与溯源链；
- **审稿人要求 GNN 细节/更全 NN 对比** → 附录补 N0–N2 已冻结行 + N3/N4 指向 future work；
- **Week 9 全稿未完** → 砍图顺序：Fig 4/5（钱图）> Fig 3/T1 > Fig 1 > Fig 2 > Fig 6；表不可砍。

---

> 至此手册覆盖：探针（P0–P5）→ 周计划（W4–13）→ 附录 A–K（逐周实测调整与裁决）→ L/M（论文冲刺与投稿）。v1.0 之后的新方向一律先在 `decisions_log.md` 立项再动手。
