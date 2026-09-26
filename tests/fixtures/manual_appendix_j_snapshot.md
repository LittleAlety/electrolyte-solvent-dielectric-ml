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

## 附录 J-补记九：J-STAGE 路线核查——Hagiyama 2008 前提证伪 + PC/EC 免费旁证（2026-09-25）

对应仓库产物：`reports/jstage_corroboration.md`、`probes/jstage_corroboration_evidence.json`、
`tests/test_jstage_corroboration.py`（9 项）。**未消耗任何受限源，未改动任何数据单元。**

### 一、被判定的前提

计划里写「Chem. Lett. 由日本化学会出版、J-STAGE 全文免费，DOI `10.1246/cl.2008.210`，
走 OUP 是走错了门」。本轮对这条前提做了**标识符级**核查。

### 二、结论：前提不成立（三重独立证据）

| 来源 | 观测 |
| --- | --- |
| DOI 解析（禁跳转） | `HTTP 302 → https://academic.oup.com/chemlett/article/37/2/210/7386188` |
| Crossref | `publisher = Oxford University Press (OUP)`；全部 `link[]` 指向 `academic.oup.com` 的 PDF |
| OpenAlex（work） | `is_oa=false`、`oa_status=closed`、`oa_url=null`、`any_repository_has_fulltext=false` |
| OpenAlex（journal） | *Chemistry Letters* 的 host organisation = **Oxford University Press**，30 317 works |
| J-STAGE 直探 | `/article/cl/37/2/37_210/_article`、`.../_pdf`、**期刊根 `/browse/cl`**、`/browse/cl/37/2/_contents/-char/en` 全部 **404** |

两个关键点：**（1）期刊根目录同样 404**，所以这不是"文章号写错"；
**（2）OpenAlex 只登记了一个 location 且就是出版商落地页**，`any_repository_has_fulltext=false`
说明任何仓储都没有副本。因此「打不开」应升级为**「没有开放副本可取」**——这两句话效力不同，只有后者能关闭检索。

### 三、对三级兜底的影响

- 第①级（精确 URL 重试）**已穷尽，不可能成功**；
- 第②级（馆际互借 / 文献传递，DOI `10.1246/cl.2008.210`）是**唯一剩余路径**；
- 第③级（两条未调和一手腿 + 维持 `model_ready=false`）是第②级失败时的默认，论文已写好。

FEC 行保持 `model_ready=false` 与排除清单条目不变。

### 四、附带红利：PC/EC 免费旁证（原 D5）

链：**Nanbu et al. 2007, *Electrochemistry* 75(8) 607-610（J-STAGE 开放）→ ref 12 = Riddick, Bunger & Sakano,
*Organic Solvents*, 4th ed., Wiley-Interscience (1986)**。印刷页 608 原文逐字：

> "… the relative permittivity of FEC (78.4 at 40 ℃)⁴⁾ is lower than that of EC (**89.78 at 40 ℃**).¹²⁾
> The relative permittivity of PC is **64.92 at 25℃**.¹²⁾"

| 目标 | 库存值（规范 CSV） | 开放旁证 | 同温 | 绝对偏差 | 相对偏差 |
| --- | --- | --- | --- | ---: | ---: |
| 碳酸丙烯酯 PC | **64.9** @ 298.15 K (25 ℃) | 64.92 @ 25 ℃ | 是 | 0.02 | 0.031% |
| 碳酸乙烯酯 EC | **90.5** @ 313.15 K (40 ℃) | 89.78 @ 40 ℃ | 是 | 0.72 | 0.802% |

另有两篇开放的 *Electrochemistry* 2013（81(10) 817-819、820-822）复现同样两个数字，排除单次转录假象。

**边界（必须守住）**：这是与**汇编层转述**的一致，不是独立测量；Riddick 本身即汇编。本轮**不改任何库存值**，
其作用是证明「受限目录从来不是拿到这两个数字的唯一路径」。GVL/DME 未被本路径覆盖。

### 五、明确未闭环

Hagiyama 2008 的 107 腿**仍在原始测量层未读**：开放引文链现持有三处独立的「about 107 at 25 ℃」转述，
全部指向该文，但原文闭源未读。DC-200 成员表同样仍未定位（见补记四与第四轮：SI 本地 50 页 OCR 全文里
`DC-200` 出现 13 次全是正文/图注，无成员表；作者 GitHub 递归 207 对象无该数据；Figshare 只有同一份 SI）。

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
- 敏感性探针（pre-registered，防审稿人问）：`probes/dielectric_leave_ec_out_probe.py`——冻结折号不变，从拟合集剔除 EC 单行重跑 hybrid raw/log 两臂，输出 `probes/leave_ec_out_summary.json`（R²/MAE/Spearman delta）。无门槛，如实报告。验收：结果行进入论文 Supplementary，主文一句话。
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

---

## 附录 N：3D 结构直训、温度维度与降方差路线图（回答"能不能用空间结构直接训练 + 加温度 + 提精度降方差"）

### N-0 裁决逻辑（证据链已闭环）
从零训 3D 模型（SchNet/PaiNN 类）在 236 行上不可行：MLP（R²<0）与 Chemprop（0.237<0.364）已证明 2D 图网络都养不活，3D 等变网络参数更多、需构象系综，数据饥渴更甚。物理警告：ε 是集体性质，单分子表示（2D 或 3D）的信息上限相同——三条边界（缔合盲区/极性非质子空洞/骨架外推）皆为此的临床表现。多体项只有两个来源：Kirkwood-Fröhlich 物理修正，或系综模拟（MD）。

### N-1 v1.x：温度分辨观测级表（投稿后 1–3 个月，最大杠杆）
- **数据**：主表从"298 K 单点/化合物"扩为 ε(T) 观测级表；来源 = NBS 514 α 系数存量（42/110 行带系数）+ ThermoML 文献 ε(T) 系列回采；目标 1,500–3,000 行（同批化合物 5–10×）；schema：observation 级（inchikey, T_K, ε, source）+ compound 级汇总；
- **模型**：冻结管线 + T_K 特征（已有）；ε(T) 单调下降提供额外物理约束；
- **预期**：精度与折间方差同时改善（数据量 ×5–10 + 物理约束）；这是不动架构的最大单项收益；
- **与 v0.4 合并**：xTB 协议整表迁移（4 行 blocked）并入同一大版本，摊薄重钉成本。

### N-2 近期降方差三件套（不动数据面，本周可做）
1. **Bagging 部署模型**：训练集 bootstrap ×50 个 XGBoost 取均值（半天；冻结管线不动，只改集成层）；
2. **分域精度声明**：精密声明收窄至 ε<20 非缔合域（域内 MAE 2.55–3.95），域外只给排序——把全域 R²=0.364 拆成分域声明；
3. **构象 Boltzmann 平均偶极**（C5 变体，1 天）：flexible 分子（glyme 类）多构象加权 μ，修复已声明的 conformer limitation。

### N-3 v2.0：3D 预训练微调探针（投稿后，2–3 天）
Uni-Mol 类 3D 基础模型（数百万构象预训练）冻结主干 + 236 行微调；输入直接用现有 xTB 构象。判据沿用 Go/Kill：超 hybrid 的 CV 置信区间才晋升。这是"3D 直训"在小数据上唯一正确的打开方式。

### N-4 Phase 2 大招：MD 偶极涨落计算层
ε = 1 + (⟨M²⟩−⟨M⟩²)/(3ε₀VkT)：3D、温度、多体关联原生包含。**先试算探针**：10 个有实验锚点的分子，GROMACS+GAFF2、5–10 ns NPT、偶极涨落 → 计算 ε vs 实验相关性与单分子成本（半天搭建 + 数天机时）。相关性好 → v2.0 开计算层（数百–数千分子 MD ε，供 3D 模型预训练/多任务）；差 → 负结果写一段。把计算层从 xTB 标量升级到系综模拟。

### N-5 定位纪律
MD 层落地前，"排序器不是测量仪"的定位不变；能力边界说明（"能用/不能用"清单）进论文 Usage Notes——该清单即审稿人最想看到的诚实度。

### 修订后的版本路线总图
| 版本 | 内容 | 治什么 |
|---|---|---|
| v1.0（冻结中） | 236 行单温点，排序器 | — |
| v1.x | ε(T) 观测级表 1,500–3,000 行 + T 特征 + bagging + 构象平均 μ + v0.4 协议迁移 | 精度/方差/温度 |
| v2.0 | Uni-Mol 3D 微调 + MD 计算层 | 3D 直训/多体物理 |

---

## 附录 O：v1.0 发布后的实际启动方案（数据源网站清单 + 三步行军）

> 状态锚点（2026-09-25）：v1.0 已发布（Zenodo `10.5281/zenodo.22957696`，CC-BY-4.0）；论文全稿 1047 行 + 六图 + 对抗审读收口；868 测试全绿；`--phase released` 绿、`--phase submission` 红（缺 cover letter 作者三项）。对账：J-STAGE 开放路线被四方证伪（Hagiyama 仅剩馆际互借）；PC/EC 免费旁证已落地；DC-200 经 Zenodo Range 查档判定包内无成员表，仅剩作者索取。

### O-1 Week 11 上半周：投稿收口
1. 补齐 cover letter 三个 `[TODO]`（作者/单位/ORCID）→ `--phase submission` 转绿；
2. 提交入口 `https://www.nature.com/sdata/submit`；稿件包 = full_draft + 六图 + Data Availability（Zenodo DOI）+ cover letter；
3. 投出即封存，启动 v1.x。

### O-2 v1.x 数据源清单（按优先级；第一刀不需要新网站）

| 序 | 来源 | 入口 | 免费 | 用途 |
|---|---|---|---|---|
| 1 | **本地 242 个 ThermoML XML 重解析** | 已在硬盘 | ✓ | 打开温度闸门重抽 246 个已有化合物的全部 ε(T) 观测，预期 1,000–2,500 行，零新数据源 |
| 2 | NBS 514 α 系数（存量） | 本地 | ✓ | 调和列 + 温度系数作先验特征 |
| 3 | NIST ThermoML 在线 | `trc.nist.gov/ThermoML` | ✓ | 补抓 2019 后新增介电文献 |
| 4 | OpenAlex + Unpaywall API | `api.openalex.org` / `api.unpaywall.org` | ✓ | 缺失电池溶剂 ε(T) 一手文献定向扫漏（glyme/adiponitrile/氟代醚 × 253–333 K），只收 OA 全文 |
| 5 | ILThermo | `ilthermo.boulder.nist.gov` | ✓ | v0.4 若收离子液体的正门：温度分辨、CSV 导出 |
| 6 | DDB Online Search | `www.ddbst.com` | 部分 | 纯组分 ε(T) 散点线索 |

### O-3 三步行军（每步带验收/判据）
1. **W11 下半周**：`scripts/build_dielectric_observations.py` 重解析本地 XML → `dielectric_observations_v11.csv`；验收：≥1,200 行、source_doi 齐全、verifier 通过；
2. **W12**：观测级 benchmark（XGBoost + T_K 特征）；**评估必须 GroupKFold by InChIKey**（同化合物不同温度点禁止跨折——黏度线 random_row 0.064 vs group_key 0.175 的教训前置）；随机行 CV 仅作参照；判据：grouped R² ≥ 0.364 即温度维度成立；
3. **W13**：OpenAlex/Unpaywall 扫漏（查询模板 `(dielectric OR permittivity) AND (glyme OR adiponitrile OR ...)`，2000 年后 + OA）→ 补录清单 = AL Round 3。

### O-4 v2.0 探针备料（v1.x 稳定后再启动，现在只建环境）
- **MD 试算**：`openff-toolkit` + `openmm`（conda-forge）；packmol ~500 分子盒子，NPT 5–10 ns，偶极涨落 ε = 1 + (⟨M²⟩−⟨M⟩²)/(3ε₀VkT)；先试 10 个有实验锚点的分子（水/AN/PC/DMC/甲醇）；
- **Uni-Mol 微调**：`github.com/dptech-corp/Uni-Mol` 官方预训练权重 + 现有 xTB 构象输入。

### O-5 纪律
v1.x 全程不动 v1.0 已发布工件；观测级表为**新文件**，化合物级主表 digest 保持 `ff214293…35ccce4`；投稿后至首轮审稿意见返回前，不接受任何新主线（只跑本附录内容）。

---

## 附录 P：方向修正——回归"溶剂/添加剂筛选"主线（2026-09-26）

### P-1 漂移诊断（诚实记录）
原始目标 = **筛选**（换溶剂→算性质→提候选；小体系、笔记本可算）。实际轨迹：P1 数据稀缺 → 建数据集 → 审计工程 → 数据集论文（v1.0 已发布）。每个分叉当时都合理，但合成效果是：终点从"筛出新溶剂"滑成"数清旧溶剂"；原手册第 11 周的"应用演示——双指标筛选"被挤掉。数据集论文是必要基础设施与独立的本科成果，但它是第一章，不是全书。**修正：投稿后将筛选闭环升回主线。**

### P-2 关键资产重估：筛选模型其实已凑齐
- **添加剂筛选的正主是氧化还原线**（VC/FEC 类成膜添加剂看还原电位/LUMO，不看介电）：RX-392 红线 R²=0.944，全项目最强模型，此前一直被当旁线；
- 介电线 = 溶剂极性的分诊排序器（适用域闸门可直接复用为筛选过滤规则）；
- 黏度线 = 族内排序参照；xTB 管线 = 候选复核工具（P5b 已标定本机算力）。

### P-3 筛选闭环方案（人机协同，笔记本可算）
1. **候选池**：Batt-P30K（29.5k，自带 HOMO/LUMO/IP/EA）+ ECW-308 + RDKit 虚拟枚举（碳酸酯/醚/腈骨架取代变体）；
2. **漏斗**：合法性/可合成性过滤 → **适用域闸门（数据集论文的三条边界 = 应用工作的过滤规则，两篇工作叙事闭环）** → 多指标打分（氧化还原窗口 × 介电排序 × 黏度族内序）→ Top-20；
3. **机器验证**：Top-20 xTB 全特征复核 → 最终 5 个上 MD 短程验证（高配笔记本即可）；
4. **人决策**：人工审视 Top-20，挑新骨架/反常识候选回喂 = 真正的 AL Round 2；
5. **产出**：《电解液溶剂/添加剂多指标筛选报告》——第二篇论文种子（域刊，非数据刊）。

### P-4 与附录 O 的关系
v1.x 温度扩展**降级为数据侧并行线**（重解析本地 XML 为主，机时活）；筛选闭环升为主线。筛选报告若需要工作温区论述，届时再正式启动 v1.x，需求更明确。

### P-5 纪律
- 投稿收口（附录 O-1）完成后才启动筛选闭环；
- 筛选全程复用冻结模型，**不为筛选重训 v1.0**（新模型属于下一轮论文）；
- Top-20 候选的每个结论必须带适用域标志与不确定性说明——数据集论文的诚实标准平移到应用工作。

---

## 附录 Q：性质模型覆盖缺口与补齐方案（HOMO/LUMO 等，2026-09-26）

### Q-1 现状对账
介电 ✓（v1.0）；氧化还原 ✓（RX-392，R²=0.944，添加剂筛选的决策性质）；黏度 △（族内排序）；**HOMO/LUMO/IP/EA ✗**（P2 只训过偶极矩且未过门；HOMO/LUMO 从未开训）。注意：P2 的 0.5636 失败是**偶极矩**（构象敏感难目标），其枪毙判据不迁移到 HOMO/LUMO。

### Q-2 三个出口（按成本）
1. **零成本**：候选池限 Batt-P30K 内 → 直接读 29.5k 分子的 ωB97X-V 级 HOMO/LUMO/IP/EA 真值，无需模型；
2. **半天（推荐）**：复用 P2 管线在 Batt-P30K 上换标签训 HOMO/LUMO/IP/EA 四个 Morgan+XGBoost 模型；大数据 regime（29.5k）下预期 MAE 0.1–0.2 eV；验收门 MAE ≤0.2 eV；输出 `models/homo_lumo_baselines.json`；
3. **兜底**：xTB `homo_lumo_gap_ev` 粗值 + 用 Batt-P30K 重叠分子做 ωB97X-V↔xTB 校准线。
线索存档：GSDS Zenodo 归档内含 MACEOFF 微调的 dipole/HOMO/LUMO/IP/EA 模型（177 个 .pth），许可允许时可作对照；自训更干净。

### Q-3 筛选漏斗四通道（修订 P-3）
| 通道 | 来源 | 覆盖 |
|---|---|---|
| 氧化还原窗口 | RX-392 模型 | 任意分子 |
| 介电排序 | v1.0 + 适用域闸门 | 域内 |
| HOMO/LUMO | Batt-P30K 真值（池内）/ Q-2 出口 2 模型（池外）/ xTB 校准（兜底） | 全覆盖 |
| 黏度 | 族内排序 | 参照级 |

### Q-4 纪律
出口 2 的训练属"筛选基础设施"，不是 v1.0 改动；数据面 digest 不动；四个新模型各自带 Dummy 对照与折号记录，沿用全项目验证纪律。

---

## 附录 R：数据库补给清单与 Reaxys 裁决（2026-09-26）

### R-1 按用途的补给图
| 用途 | 首选（免费） | 受权限/付费 | 备注 |
|---|---|---|---|
| 介电 ε(T) 温度序列（v1.x） | 本地 242 XML 重解析 → trc.nist.gov/ThermoML 补 2019 后；OpenAlex/Unpaywall 扫 OA | Reaxys、DDB 完整版、SpringerMaterials | 大头已在本地 |
| FEC/VC/MOPN 冲突裁决 | 馆际互借（Hagiyama） | **Reaxys**（可能直接解开，见 R-2） | 当前最痛点 |
| HOMO/LUMO/IP/EA | Batt-P30K 真值 + 自训模型；NIST CCCBDB（cccbdb.nist.gov，免费）验校准 | — | — |
| 氧化还原补充 | RX-392 已有 | Reaxys（电化学字段） | 不急 |
| 筛选过滤性质（mp/bp/闪点/密度=液态窗口） | PubChem PUG-REST（可批量）、NIST WebBook（蒸气压/Antoine） | Reaxys | 漏斗合法性过滤层 |
| 离子液体（若 v0.4 收编） | ILThermo（免费、温度分辨、CSV 导出） | — | IL 线正门 |
| 供体数 DN | GSDS 归档 DonorNum 产物 | — | 第五通道候选 |

### R-2 Reaxys 裁决：有用，且有一个被低估的具体价值
- **先决动作**：图书馆数据库导航查 Reaxys/SciFinder-n 订阅（tier-4 记的是"未验证"不是"没有"）；
- 若有权限，四个用途按价值排序：① **Reaxys 人工摘录论文实验数据点（值+温度+条件+出处），Hagiyama 2008 的 FEC 107 及其测量条件可能直接以结构化字段存在——一次检索或可同时解 FEC/VC/MOPN 三个 blocked 项，绕过馆际互借**；② v1.x ε(T) 批量补给；③ 候选分子液态窗口（mp/bp/闪点）批量过滤；④ 黏度/密度 T 依赖；
- **纪律**：Reaxys = 带原始指针的汇编层，provenance 记 `reaxys←primary_doi`，关键决策值回溯原文；**手动逐条查询+记录合规，爬虫批量导出违反 ToS，禁止**；
- 若无权限：SciFinder-n 次之；皆无则免费栈（ThermoML + OpenAlex/Unpaywall + PubChem + NIST WebBook/CCCBDB + ILThermo + DDB 免费层）覆盖约八成，余者进 Limitations。

### R-3 行动序
1. 查 Reaxys/SciFinder-n 权限（10 分钟 + 一封馆员邮件）；
2. 若有 → 第一小时查 FEC permittivity 全部摘录记录（目标：107 的温度/频率/方法）；
3. 无论有无 → 投稿收口优先；v1.x 本地重解析不依赖外部库。

### R-补记（2026-09-26）：Reaxys 权限确认在手，tier-4 只剩 SpringerMaterials

**格局更新**：Reaxys 可用 → R-2 的四个用途全部激活；SpringerMaterials 缺的 GVL/DME/环丁砜交叉核验由 Reaxys 摘录层替代（同一批一手文献；纪律：`reaxys←primary_doi` provenance、只读核验、不进可分发数据集）。

**优先查询队列（按解锁价值）**：
1. **FEC**（SMILES `O=C1OCC(F)O1`）：Physical Data → Dielectric constant，找 107 记录的温度/频率/方法/出处（是否指向 Hagiyama 2008）。找到 = 双腿条件层面对齐、免 ILL；找不到 = 维持 ILL；
2. **VC**：核对 Knovel 78–127 区间内每个值的出处与条件（Saadi & Lee 1966 的 126±1.0 应在内，重点找独立第二测量）；
3. **MOPN**：找 Ue 1994 或任何独立于 Perricone 的一手测量；找到 → 解除 corroboration + 补 xTB 特征行 → 可入库；
4. **GVL/DME/环丁砜**：受限交叉核验替身（见上）；
5. **v1.x 备货（投稿后）**：glyme/adiponitrile/氟代醚 ε(T) 序列 → AL Round 3 补录清单。

**操作要点**：物质检索（SMILES/InChIKey/名称）→ Physical Data → Dielectric constant（或 Query Builder 直接建字段查询）；每条记录抄四样：值、温度、频率/方法、一手出处（卷期页）；**手动逐条查询合规，批量爬虫导出违反 ToS，禁止**。

---

## 附录 S：Week 11 总结、计划修订与终局目标重述（2026-09-26）

### S-1 Week 11 记账

**确认（可入库的结论）**：
- 观测级 v11 表：1,630 行 / 103 化合物（频率闸门合并后 2,065 行 / 153 化合物）；
- 固定评分池（457 行 / 97 化合物、同折号）：paired_base R²=0.4091 → paired_plus_coverage R²=0.5332，**ΔR²=+0.1241，ΔMAE=−1.5362，Δρ=+0.1081**，训练池 97→147 化合物；
- 对抗审计 5 确认 / 0 反驳（13,706/13,710 预测格变化；与评分池 0 重叠；rank-invariance 演示排除"先验漂移"）；
- 1,591 测试绿；v1.0 数据面 digest 未动。

**证伪（同样值钱）**：
- ThermoML 在线 11,923 条 = 0 新增 vs 本地；
- ILThermo ε 数据集 109 个仅 1 个 T-span>5K → 温度维度关闭，降级为单点 ε 补充源；
- DDB 免费层 = 0 值；
- OpenAlex/Unpaywall 37 篇 OA 候选 = 0 个 ε 值被读出（仅线索）；
- NBS α 先验特征 0/97 覆盖 = inert → **新准则：任何新特征入库前先过覆盖率检查**。

**悬置（未过关不许引用）**：
- +0.1241 的归因：观测级信息 vs 样本量/正则化效应未分离 → **placebo 重训是 Week 12 第一技术任务**；
- xTB 体积列随 OMP_NUM_THREADS 漂移 → v1.x/v2.0 任何 xTB 特征入库前必须修复；
- 投稿收口仍红（`--phase submission` 未绿；cover letter 有 [TODO] 作者项）→ **仍是顶门**。

### S-2 终局目标重述（三层金字塔 + 完成判据）

```
L3 终局：候选溶剂/添加剂排序清单 + 筛选应用论文（第二篇）
   ↑ 由四通道漏斗产出：氧化还原 ✓ / 介电 ε(T) / HOMO-LUMO / 黏度排序
L2 模型层：v1.x 温度分辨介电模型（Week 11 方向已实证）
   ↑ 训练在观测级温度分辨表上
L1 基础设施：v1.0 数据集论文（已发布，DOI 在手）✅
```

**为什么 ε(T) 是终局的刚需而非支线**：电解液工作温度窗口 −20~60 °C，298K 单点排序无法回答"低温下谁还保持高 ε/低黏度"。v1.x 把介电通道从室温排序升级为温度窗口排序——这是筛选闭环的合法组成，不是漂移。

**L3 完成判据（可检验，防自欺）**：
1. top-20 溶剂 + top-20 添加剂候选清单，每条四通道预测值 + 适用域闸门标记（结构性 SMARTS）+ 不确定性 + 实验优先级；
2. **回溯验证（预注册）**：训练时排除 EC/PC/FEC/VC 等已知冠军分子，漏斗须把它们排回前列——0 成本、筛选论文最有说服力的验证；
3. 第二篇论文（筛选应用）草稿。

### S-3 计划修订（Week 11 后格局）

**数据增长引擎切换**：外部免费扩张收官（源 3/5/6 证伪），增长只剩三通道——
| 通道 | 状态 | 下一步 |
|---|---|---|
| 本地 XML 重解析 | ✅ 已收割（+0.1241 的载体） | 完成 |
| Reaxys 摘录层 | 权限在手 | 按 R-补记优先队列执行：FEC→VC→MOPN→GVL/DME/环丁砜→v1.x 备货 |
| 37 条 OA 线索 | 仅线索 | 标题/摘要分流 → 全文本人工阅读清单（周末缓冲，不进主线） |

**纪律重申**：Reaxys 手动逐条查询合规、批量爬虫禁止；受限值只作 `restricted_crosscheck_only` / `reaxys←primary_doi` provenance，永不进可分发数据集；投稿收口仍是一切的顶门。

### S-4 Week 12 逐日任务表

| 日 | 任务 | 验收门 |
|---|---|---|
| 周一 | **投稿收口（顶门）**：cover letter [TODO] 作者项补齐；`--phase submission` 转绿 | 绿灯截图 + 提交回执 |
| 周二 | **Placebo 三臂预注册 + 开跑**（见 S-5） | 预注册文本进 decisions_log §10，跑批启动 |
| 周三 | Placebo 判读 + **xTB 线程修复**：固定 OMP_NUM_THREADS 重跑体积列，出 diff 报告 | 判读结论入档；体积列复现差 <0.1% |
| 周四 | Reaxys 队列第一刀：FEC（107 的温度/频率/方法/出处）+ VC（Knovel 区间逐值溯源） | 逐条记录值/T/频率方法/一手出处 |
| 周五 | Reaxys 队列第二刀：MOPN（独立一手）+ GVL/DME/环丁砜交叉核验；周收尾审计 | 审计报告；手册附录更新 |
| 周末缓冲 | 37 OA 线索标题/摘要分流（不读全文） | AL Round 3 补录清单草稿 |

### S-5 Placebo 重训预注册规范（三臂）

**目的**：分离 +0.1241 的归因——观测级信息 vs 样本量/正则化。固定评分池与折号不变（沿用 Week 11 paired 设计）。

| 臂 | 构造 | 预期（若增益为信息驱动） |
|---|---|---|
| Arm A 标签安慰剂 | 新增 50 化合物的 ε 标签在化合物间随机置换（行数、组成、正则化全同） | ΔR² 塌缩至 ≈0（阈值 ≤+0.02） |
| Arm B 剂量曲线 | 新增行按 25%/50%/75%/100% 四档子采样重训 | 增益单调递增（剂量-响应证据） |
| Arm C 均值退化 | 新增化合物只保留化合物均值行（消灭 T/频率分辨率，保留化合物数） | 增益显著低于全量臂 → 证明温度分辨率是载体 |

**判据**：Arm A Δ≤+0.02 且 Arm B 单调 → 才许把 +0.1241 表述为"观测级信息驱动"；任一不过 → 表述降级为"数据量效应"，v1.x 叙事重写。**过关前 +0.1241 不进任何对外文本（论文、摘要、封面信、GitHub README）**。

### S-6 对账（Orchestrator 侧，诚实记账）

- ✅ R-1 "ThermoML 大头已在本地" —— 被证实（在线 0 新增）；
- ⚠️ ILThermo 被标为"温度分辨的 IL 线正门" —— ε 温度维度实际关闭（1/109），降级为单点补充源，IL 线 ε(T) 希望缩水；
- ⚠️ OpenAlex/Unpaywall 扫描源 —— 实际只产线索不产值，人工成本低估；结论不变但排位降至周末缓冲；
- 准则沉淀：**"先验特征要过覆盖率检查"** 与 **"placebo 不过门，增益不引用"** 两条入全项目纪律。

---

## 附录 T：Week 12 收口 —— placebo 判决把 +0.1241 打下来了（2026-09-26）

### T-1 头条（本轮唯一改变对外结论的结果）

**S-5 三臂 placebo 的判决是 `data_volume_effect`（数据量效应）。Week 11 的 ΔR² = +0.1241 从一切对外文本中撤下。**

| S-5 判据 | 阈值 | 实测 | 结果 |
| --- | --- | --- | --- |
| Arm A 标签安慰剂塌缩 | ΔR² ≤ +0.02 | **+0.0141** | PASS |
| Arm B 剂量曲线单调递增 | 25→50→75→100% 每步为正 | 步长 **+0.0004 / +0.1163 / −0.0164** | **FAIL** |
| Arm C 均值退化低于全量臂 | 机制旁证，不入判据 | +0.1021（+0.0997）vs +0.1241 | PASS |

判据是**合取**（S-5 原文：Arm A 过 **且** Arm B 单调）。Arm B 没过 → 降级。**预注册跑批前锁定，事后未放宽一个字。**

**怎么读**：Arm A 塌到 +0.0141 其实**支持**"信息驱动"，但单臂不足定案（只打乱标签、保住行数/组成/正则化，本就会打散靠标签分布撑起来的拟合——这正是要求 B 臂同时单调的原因）。**决定性证据是 B 臂的非单调**：75% 档（93 行/折）比 100% 档（127 行/折）还高 +0.0164；若增益是观测级信息随剂量累积，100% 档理应最高。Arm C 方向一致：把 127 行压成 50 行（每化合物 1 行、消灭 T/频率分辨率）仍保住 +0.1021，只亏 0.0220 → **温度分辨率不是增益的主要载体**。

**处置**：v1.x 叙事改为"建温度分辨观测表是**基础设施**投入（覆盖度/可复现性/口径统一）"，**不以该 ΔR² 为卖点**。GroupKFold by InChIKey 仍是诚实评估唯一口径。

**完整性**：W11 钉死值 `paired_base` 0.4091179943351143、`paired_plus_coverage` 0.5332044440328436、ΔR² 0.1240864496977293 **逐位复现**（`bit_exact=True`）；15 项完整性自检全 PASS；10 次重复、无降级；种子 = 折 42 / 置换 20260926 / 剂量 20260927。

### T-2 S-4 逐日对账

| 日 | S-4 任务 | 状态 |
| --- | --- | --- |
| 周一 | 投稿收口（cover letter TODO + `--phase submission` 转绿） | **部分**：仓库 URL 与 `v1.0` tag 已填（GitHub API 实测仓库 public、远端 tag `v1.0` 存在）；**剩 3 项作者个人数据（姓名/单位/email）待用户提供**，故仍红 |
| 周二 | placebo 三臂预注册 + 开跑 | **完成**：§10 预注册落 `decisions_log.md`；三臂跑完 |
| 周三 | placebo 判读 + xTB 线程修复 | **完成**：判读 = 数据量效应；xTB 固定线程修复落地 |
| 周四 | Reaxys 第一刀：FEC + VC | **完成并超额**：扩到 FEC / VC / GVL / DME / sulfolane 五个分子 |
| 周五 | Reaxys 第二刀 + 周收尾审计 + 手册附录更新 | **完成**：第二刀并入周四同批；审计与本节 |
| 周末缓冲 | 37 条 OA 线索分流 | **完成**（提前） |

### T-3 xTB 线程修复（S-1 悬置项闭环）

- **根因**：xTB 6.7.1 的 SCF 与解析梯度按 OpenMP 线程做浮点归约，**加法不满足结合律** → 收敛梯度带线程数与运行相关的扰动；`--opt` 以梯度范数停机，于是 `xtbopt.xyz` 停在略不同的点，而 RDKit `ComputeMolVolume(gridSpacing=0.2)` 量化到 **0.008 Å³** 格子，翻一格就改写体积列。
- **最小证据**：同输入同行命令，只改子进程环境 → 请求 4 线程时 **15/15 次跑出 15 种不同几何**（体积跨 93.368–93.448）；请求 1 线程恒为 93.408。
- **修复**：新增唯一 launcher `src/electrolyte_ml/xtb_runner.py`，钉死 `OMP_NUM_THREADS=1` / `MKL_NUM_THREADS=1` / `OMP_DYNAMIC=FALSE` / `MKL_DYNAMIC=FALSE`，并清除父进程泄漏的同名变量；特征路径的 `threads` 形参与 `--threads` CLI 一并删除。
- **验收**：同输入重跑 **0 个格变化**（体积列最大相对差 **0.0000%**，门限 < 0.1%）；跨线程 1/2/4/8/16 五档几何逐字节相同。全表 42 行只动 8 个格（两分子的 4 个体积派生列），其余 39 行全部 23 列逐位相同。
- **顺带固化第二前置条件**：工作目录残留 `xtbrestart` 会被当 SCF 重启读入，1 线程下也能复现 → 必须清空工作目录。
- **诚实边界**：修复前的漂移在本机这两行上**并未突破 0.1%**（15 次最大 0.0856%）。修复理由是**结果不可复现**，不是"已证实的 >0.1% 误差"；**冻结表未覆盖**。

### T-4 Reaxys 第一刀（五个分子，S-3 队列走完）

| 化合物 | Reaxys 条目 | 本地观测行 | 净新增 | 判决 |
| --- | ---: | ---: | ---: | --- |
| FEC | 1（Static） | 1 | 0 | 只有 78.4 @ 23 °C（Kobayashi 2003），**无 107 腿** |
| VC | 1 | 1 | 0 | 无数值**引用存根**；DOI 与冻结行 `source_doi` **逐字相同** |
| **GVL** | 1 | **0** | **+1** | **真缺口**：36.9（Segato 2021, SI）vs 冻结 36.1（iScience 2026 综述表），**两者都无温度** |
| DME | 7 | 9 | +1 线索 | 本地温度序列已在；新增唯一带温度区间的源 Werblan 1985（7–9.1 @ −30…25 °C, 1591 Hz） |
| **sulfolane** | 12 | 8 | 0 | 与本地**逐点一致**（同一 DOI）→ 独立再确认 |

**Reaxys 数据模型（结构性事实，会影响后面所有摘录计划）**：介电数据分两个类别——`Static Dielectric Constant`（列：值/温度/Location/Comment/Reference，**无频率列**）与 `Dielectric Constant`（**有 Frequency 列**）。**两类都没有"方法"列**，只有 `Location`/`Comment` 两个自由文本列偶尔承载方法信息。→ **"频率/方法/出处"三件套里，方法必须回到一手文献**；FEC 恰好落在 Static 类别，连频率都给不了。

**净产出**：没有翻出任何本地缺失的成品数据；真收获是「GVL 真缺口 + DME 新源线索 + sulfolane 独立再确认」+ 两条否定性证据（FEC 无 107 腿、VC 无值）。

### T-5 37 条 OA 线索分流（周末缓冲，提前完成）

- P0/P1/P2/P3 = **0 / 4 / 20 / 13**；进人工阅读清单 **4**、待定 20、丢弃 13。
- 有 ε 数值线索 **1** 条；温窗覆盖 true/false/unknown = 1 / 2 / **34**；OA 全文可得 9 / 25 / 3。
- API 请求 **116** 次（上限 220）：OpenAlex 37、Unpaywall 37、OA 链接探测 37、Crossref 5。
- 诚实边界：**5 条摘要读不到**（两家 API 都返回 200 但无摘要字段）；21 条 OA 链接返回 403（出版商 Cloudflare）；OA 可达性是**瞬时状态敏感**的（同一链接上一轮 200、本轮 403）。

### T-6 投稿门禁状态（顶门仍未开）

- 已填（**均为可核实事实，非编造**）：`paper/cover_letter.md` 的仓库 URL = `https://github.com/LittleAlety/electrolyte-solvent-dielectric-ml`（GitHub API 实测 `private=false`）；版本 tag `v1.0`（GitHub tags API 返回 `["v1.0"]`）。
- **仍红 3 项**：`[TODO: corresponding author name]` / `[TODO: affiliation]` / `[TODO: email]` —— **属个人数据，必须由本人提供，不得编造**。
- `scripts/check_release_readiness.py --phase submission` 当前报 3 条 unresolved TODO。

### T-7 成果输出位置

`E:\Claude Code\电解质ML\成果输出\week12\` —— **31 个文件**（27 件产物 + `README.md` / `verification.json` / `week12_summary.json` / `SHA256SUMS`；其中 3 件在 `artifacts/` 子目录），含 `week12_summary.json`、`verification.json`、`README.md`、`decisions_log.md`（含 §10 预注册 + §11 判决 + §12 手册回退 + §13 Reaxys MOPN 复验 + §14 `l3_backvalidation_prereg.json` 预注册 + §15 池闸门 amend）、四路产物与其逐折明细。
门禁实测：`probes/export_week12_results.py --overwrite` → `verification_passed = true`；`verify_export_manifests.py --output-dir 成果输出/week12` → **[PASS]**。

### T-8 纪律（本轮新增/重申）

1. **placebo 不过门，增益不引用** —— 本轮第一次真正执行，撤下了自己 Week 11 的头条数字；
2. **新特征先过覆盖率检查**（NBS α 教训）；
3. **Reaxys 手动逐条查询合规、批量爬虫禁止**；受限值只作 `restricted_crosscheck_only`，**永不进可分发数据集**；
4. **预注册要写在跑批之前**，且事后不许放宽（本轮 §10 先落档、§11 严格按合取判据执行）。

### T-9 下一步（不新开主线）

1. 拿到作者三项个人数据 → `--phase submission` 转绿 → 投出（`https://www.nature.com/sdata/submit`）；
2. GVL 是 v1.x 温度表第一优先缺口（本地 0 观测）；Segato 2021 与 iScience 2026 的 36.9 vs 36.1 冲突待判；
3. Hagiyama 2008（`10.1246/cl.2008.210`）仍是 FEC 107 腿唯一收口项，Reaxys 帮不上，只剩馆际互借；
4. 4 条进人工阅读清单的 OA 线索（tetraglyme / adiponitrile / succinonitrile ×2）排在 v1.x 之后。
### T-10 手册正文回退的发现与恢复（同轮，先于交付包封版）

**症状**：本轮全量 `pytest` 的唯一红灯是 `tests/test_manual_appendix_reconciliation.py::test_committed_manual_fixture_still_carries_the_round5_guards`（已提交 fixture 不等于当前手册的抽取）。

**定位**：不是「追加附录 T 使抽取末尾变长」这种表面原因，而是手册正文**整整回退了一个版本** —— 缺失附录 J-补记三的「§十二 v0.3.14（D2）」整节、附录 J-补记九（J-STAGE 路线核查）整节，以及附录 K 的「修订说明二」与 D2/D3/D5 三行裁决。

**三条互相独立的判据**：
1. 正文引用的 `probes/dielectric_leave_ec_out_probe.py` **不存在**；仓库里实际是 `probes/dielectric_leave_ec_out_sensitivity.py`（22,856 B），正是 fixture 写的那个名字；
2. `reports/jstage_corroboration.md`、`probes/jstage_corroboration_evidence.json`、`tests/test_jstage_corroboration.py`（9 项）都在仓库里，而记录它们的补记九已从手册消失；
3. 冻结数据集实测 digest = `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`（v0.3.14；4 行 `out_of_scope_ionic_or_organometallic`、`model_ready=true` 恰 240 条），而正文写的是「当前规范哈希 `a446c216…c01085`」（v0.3.13）。

**处置**：先备份到 `bak/执行手册_探针与周计划.md.bak-20260926-preW12restore`（151,955 B），再用本手册自己的已提交抽取替换「附录 J-补记三 → 附录 M」区间，**本轮新写的附录 N–T 全部保留**。恢复后手册 1,699 行 / 160,949 B。

**验收**：新生 fixture 与已提交 fixture 的 diff 为**单处纯追加（末尾 +327 行 = 附录 N–T）、删除 0 行**，说明恢复逐行精确；手册守卫 26 passed（含「excerpt 必须钉住现行规范 digest」这条硬闸门）；探针工件按恢复后的手册重生（stale 命中 0、forbidden 命中 0）。

**成因未定（如实记录）**：`bak/` 里 8 个快照（2026-09-24 至 09-25）**没有一个**含补记九或修订说明二，所以这不是某次 `.bak` 还原能解释的；此处只写「现象已查清、成因未锁定」，不做猜测性归因。完整记录见 `reports/decisions_log.md` §12。

### T-11 附录 Q 陈旧结论的订正（同轮；成对订正 + fixture 重生）

**发现来源**：本轮只读对抗审读指出附录 Q 的 Q-1 与 Q-3 仍把氧化还原通道写成「✓ / RX-392 全项目最强模型 / 覆盖任意分子」，与同文件的附录 U-3/U-4（门是红的、无 `--smiles` 入口）正面冲突；这段陈旧文本已进入受守卫的 CI 抽取 `tests/fixtures/manual_appendix_j_snapshot.md`，不修就会一直留着。

**改了哪两个位置**（只**新增订正行**，不删除原文）：
1. Q-1 段末新增一行订正（紧随 Q-1 正文）：写明「0.944 是一维线性映射的留出 R²、预注册门实测 0.2905 未过、无 `--smiles` 可调用入口」；
2. Q-3 四通道表下新增一行订正（紧随 Q-3 表）：写明「氧化还原窗口那一行的覆盖声称不成立」，并指向附录 U-3/U-4。

**验收**：
- `probes/manual_appendix_reconciliation.py --write-manual-fixture` 重生抽取 → 新生 fixture 与改前 fixture 的 diff = **净增 26 行（新增 27 行、改写 1 行、删除 0 行）**；实测 fixture 1146 → 1172 行、手册 1760 → 1786 行（原位订正：原写「新增 27 行」是插入操作数，净增为 26；绝对行号引用已改为锚点式，避免随后续插入漂移）；
- `tests/test_manual_appendix_reconciliation.py` **26 passed**（含「excerpt 必须钉住现行规范 digest」这条硬闸门）；`tests/test_jstage_corroboration.py`、`tests/test_l3_backvalidation_prereg.py` 全绿；
- 手册 CRLF 计数仍为 **0**。

**与本轮其它 amend 的关系**：这与 `reports/decisions_log.md` §15 是同一轮的两个动作 —— §15 管机读预注册（池闸门 + 阈值 rationale 勘误，见附录 U-6），T-11 管手册正文的陈旧结论；共同点是**只补订正、不动任何锁定数值**。


### T-12 同源陈旧断言的第二处闭合 + 闸门边界（第二轮，2026-09-26）

**现象**：T-11 只订正了附录 Q 的 Q-1/Q-3；对抗复审指出同一断言还有两处未标注 —— **P-2**（「RX-392 红线 R²=0.944，全项目最强模型」）与 **S-2 三层金字塔图**（「由四通道漏斗产出：氧化还原 ✓ / …」）。本轮补上，并把「机读闸门能证明什么」的边界写清。

**改了哪两行**（只**新增订正行**，不删除原文）：
1. P-2 首条 bullet 之下新增一行订正（紧随 P-2 首条 bullet）：口径与 Q-1/Q-3 一致 —— 0.944 是 IP→氧化自由能**一维线性映射**在 78 行留出集上的 R²，不是可调用模型；预注册门 `MAE < 0.15 eV` 实测 **0.2905180517963865** 未过（门是红的）；仓库内无 `--smiles` 可调用入口；现状以附录 U-3/U-4 为准；
2. S-2 金字塔图**围栏代码块之后**新增一行订正（代码块内不插行，否则订正会被渲染成代码）。

**实测数字（本轮）**：手册 **1786 → 1803 行**、fixture **1172 → 1189 行**（均净增 **17**：2 行新订正 + 15 行 T-12 本体，另 T-11 内 3 行被就地改写、净增 0）；CRLF 仍为 **0**；`probes/manual_appendix_reconciliation.json`：`stale_phrase_hit_count = 0`、`forbidden_token_hit_count = 0`、`current_digest_pinned = true`。

**验证**：`tests/test_manual_appendix_reconciliation.py` 26 passed；全手册 grep「未标注的 `氧化还原 ✓` / `全项目最强模型` / `覆盖任意分子`」= **0**（其余命中都紧跟订正行或属 T-11/T-12 的自我叙述）。完整记录见 `reports/decisions_log.md` §16。

**闸门边界（同轮订正两处措辞）**：`tests/test_l3_backvalidation_prereg.py` 的「评分产物存在 ⇒ 池字段必须非 null」闸门**只能证明池曾被落盘且规模达标**，**不能**证明落盘早于看见冠军排名 —— 那一条仍靠纪律（纳入口径不得以冠军排名为条件）+ `pool_sha256` 的时间戳审计；本次只改措辞，未删任何断言、未弱化任何守卫。

### T-13 §17.7 的「断言只增不减」表述订正（本轮；只改措辞，不删断言、不动锁值）

**来源**：本轮独立只读审读（Minor 1）指出 `reports/decisions_log.md` §17.7 与守卫 docstring 现写「断言只增不减、未删未弱化」/
「strictly more than the old assertions checked」，**字面为假**。

**实测（审读员对 week12 快照做的扁平 diff）**：`tests/test_l3_backvalidation_prereg.py::test_pool_rule_carries_the_machine_readable_freeze_fields`
的真实改法是 —— **3 条 `is None` 占位断言被替换掉**（`pool_path` / `pool_sha256` / `pool_size_by_list`，换成「路径存在 + digest 与磁盘文件一致 + 每个清单规模过锁值」），
**1 条 `is False` 被翻转成 `is True`**（`pool_frozen_before_scoring`）；即每条断言是**被改写而非新增**。**净强度提高、没有丢弃任何检查**，
七个锁定常量仍逐条断言；**本轮未删任何断言、未动任何锁定值**。

**改了哪两处**（只改措辞，不删正文）：
1. `reports/decisions_log.md` §17.7 的结论句改为「该守卫的断言没有净丢失、强度净提高」，并把上述 diff 事实写进正文；
2. `tests/test_l3_backvalidation_prereg.py` 该守卫 docstring 的同句改为 replaced / flipped 的准确描述。

**保留原状的一处（如实声明）**：`probes/l3_stage1_pilot_summary.json` 的 `conflicts_with_frozen_points[0].resolution` 用的是
「upgraded, never weakened」——该表述与订正后的版本**相容**（它未声称「只增不减」），且该文件是**上游写手的产物、不在本轮写入集内**，
因此**保留不改**；这一条不是回避，而是把「哪句是真的、哪句只是相容」分开写清。

**互相指向**：本小节 ↔ `reports/decisions_log.md` §17.7 与 §18.9。

### T-14 预注册 `fold_source` 补正 + 试点摘要措辞收口（本轮；只增不改、不动锁值）

1. **A（预注册 amend 落文本）**：`probes/l3_backvalidation_prereg.json → fold_and_seed.fold_source` 指向介电通道的 `data/processed/v032_ablation_predictions.csv`（**不含 Batt-P30K 分子**），对 HOMO/LUMO 通道**不成立**；本轮**只增不改**地新增 `fold_and_seed.fold_source_by_channel`（`dielectric_roster` = 该介电表；`batt_p30k_homo_lumo` = 「generated_by RepeatedKFold(5,10,42) on the 29,515-row pool」）与 `fold_and_seed.amendment_3`（`kind = per_channel_fold_source_correction`），原 `fold_source` / `fold_policy` 原文一字未动。
2. **A 的更严读法（不是放宽阈值）**：冠军**整体移出建模池**（29,519 → 29,515），折号由 `RepeatedKFold(5,10,42)` 在 29,515 行上**重新生成**，冠军由**全池生产模型**打分；比预注册字面要求（只从冠军所在折的训练侧剔除）**更严**。七个锁定常量（`K = 20` / `0.10` / `0.15` / `20260928` / `1` / `100` / `pass_expression`）与 `fold_scheme` / `seed_scheme` 逐字未动。
3. **B（措辞收口）**：`probes/l3_stage1_pilot_summary.json` 的 `conflicts_with_frozen_points[0].resolution` 由 `upgraded, never weakened` 改为准确表述（3 条 `is None` 被替换、1 条 `is False` 被翻转、无检查丢失）；**只改措辞，未动任何数值字段**。T-13 那句「保留原状」在本轮被取代。
4. **sha256（旧 → 新）**：`probes/l3_backvalidation_prereg.json` `39cc5e67…f435e9` → `6394209ae292ce7b9dde72fa852e5eca160376f3b463b3e8f7320b9c05fd74ef`；`probes/l3_stage1_pilot_summary.json` `e57dff25…89d37` → `212ec2493dcaf4b757ea6a25295890b7144694191f49aeee4b8bba8bfec272d7`。
5. **未改（禁改项，如实记录）**：`probes/l3_stage1_pilot.py`（生成器会把 B 的措辞打回旧串）、`models/homo_lumo_baselines.json`（仍记 `prereg_sha256 = 39cc5e67…`，属历史记录）。

**互相指向**：本小节 ↔ `reports/decisions_log.md` §20（A 另见 §18.7、B 另见 §18.9）。

### T-15 Reaxys v1.x 备货扫描（本轮；数据侧第四路，队列可复现、读数为人工转录；含对抗审读收口）

1. **触发**：手动 Reaxys 队列的最后一格（FEC → VC → MOPN → GVL/DME/环丁砜 → **v1.x 备货**）本轮用 **Edge 已登录会话**走完；**手动逐条查询，未用批量爬虫、无导出、无自动化遍历**；全部读数 `restricted_crosscheck_only`，**不进 `data/`、不进池、不替代任何冻结读数**。
2. **合规串已按审读改正（原串不实）**：原串称「查询产物不含任何受限数值字段的机器可读镜像」，而产物自身的 `readings[].rendered_rows` 与 `net_new_detail[].value` 就是渲染表数值列的**逐值机器可读镜像**，该自述被自己证伪。现串如实承认镜像存在，并写明「只存于本仓库与 week13 交付包内，**禁止再次分发**」；机读侧新增 `restricted_values_contract`（`machine_readable_mirror_present = true`、`redistribution = not_permitted`、`declares_channel_availability = false`）。provenance 由 `reaxys←primary_doi` 改为 `reaxys<-bibliographic_citation`——Reaxys 渲染表只给文献题录、不给 DOI。
3. **先修正自己的错（覆盖度检查的键）**：按俗名（adiponitrile、diglyme、triglyme、tetraglyme）去本地观测表匹配会**全部误判为「本地 0 行」**——本地表用 IUPAC 登记名（`hexanedinitrile`、`2,5,8-trioxanonane`、`2,5,8,11-tetraoxadodecane`、`2,5,8,11,14-pentaoxapentadecane`），实测本地温度点数为 31 / 6 / 5 / 5。**队列因此改为按 InChIKey 重算**：覆盖度检查本身也要用不依赖命名的键。
4. **队列（两个计数口径已分开；旧稿把 236/167/106 写混）**：池 236 个溶剂里 **167 个没有温度序列**（`<2` 个不同温度），池内**有**温度序列的是 **69** 个（167 + 69 = 236，脚本内已断言）。旧稿那句「有温度序列的只有 106 个」是**观测表全表**（153 个物质）口径，167 + 106 ≠ 236 本身即自相矛盾；现两个计数分别落在 `pool_members_with_two_or_more_distinct_T` 与 `observation_table_compounds_with_two_or_more_distinct_T` 两个键下。优先级 **P1 = 2**、**P2 = 22**、**P3 = 143**；**P1 由池内 `is_champion=true` 派生**（不再硬编码 EC/PC 两个名字），`model_ready` 条件在本队列上恒真（已记 `model_ready_filter_is_vacuous_on_this_queue`）；**P2 是族级复核顺序、不是可用性判断**——`fluorinated` 是子串规则，会把非电解液芳烃（Fluorobenzene、m-/o-/p-Fluorotoluene、Trifluoroacetic acid 等 9 行）一并排进 P2。产物 `probes/reaxys_v1x_stocking_queue.csv`；复核 `probes/verify_reaxys_v1x_stocking_scan.py`（**独立重算同一集合**，**70 项检查全过**）。
5. **族分类规则已修（审读给出 ≥5 例误分类）**：`ionic_liquid` 提到 `fluorinated` **之前**（否则含氟阴离子会把咪唑盐拖进 `fluorinated`，并补 `imidazol-3-ium` / `azolium` 拼法）；新增 `siloxane` 规则挡在 `glyme_ether` 之前（`oxa` 会命中「disiloxane」，Hexamethyldisiloxane 曾被判成 `glyme_ether`）；补「-ol / diol」后缀规则（`1,2-ethanediol` 曾落到 `other`），并显式排除硫醇（`1-Butanethiol`）。
6. **校验器已补非派生列覆盖（原校验器 36/36 可被伪造）**：审读手工把 `target_dielectric=11.1`、`target_T_K=999.0`、`local_rows=42` 改进去，原校验器仍 36/36 全过、pytest 22 passed。现校验器逐行重算 `name / smiles / target_dielectric / target_T_K / family_tag（对 classify()）/ local_rows / is_champion / champion_short / model_ready / probed_in_this_round / access`，并给池与观测表各加 sha256 钉（观测表 `159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9`）。
7. **Reaxys 探测读数（7 个物质）**：唯一带温度序列的是 **tetraglyme**（声明 8 hits、实际渲染 7 行、1 MHz、14.99–54.99 °C，Rivas et al., *J. Chem. Thermodynamics* 2006, 38(3), 245-256）；triglyme 与己二腈各只有 1 条**五列全空**的「提及级」条目（本地反而有 5 点 / 31 点温度序列）；diglyme 与 TTE 在 Reaxys 侧为 0 条。EC / PC 在**观测表**里是 0 行，人工转录的那 1 个点取自 **v03 冻结表**冠军行——两个计数口径不同，报告中列名已分开。
8. **净新增 = 4 条 / 2 个物质 / 3 篇一手文献**：tetraglyme 高端 2 条（318.14 K、328.14 K，1 MHz）；PC 的 20 °C、35 °C 两点（2 MHz，Laurence 1994 / Ritzoulis 1989）。tetraglyme 其余 5 点与本地逐点重合（差 0.01 K）。**口径限定**：PC 的「净新增 2 条」以 **v03 冻结表冠军行**为基线（观测表基线为 0 行）；4 条全部带给定频率口径。
9. **冠军核对（判决按证据强度降级；旧稿的「独立旁证」已推翻）**：旧稿称 PC「被两个互相独立的一手来源复现」，**与本仓库自己的溯源结论相反**——`reports/jstage_corroboration.md` 已写明 64.92 来自 Nanbu 2007 转引的 Riddick《Organic Solvents》4th ed. 汇编（原文：Corroboration here means *agreement with a compilation restatement*, not independent measurement）。判决降级为 `compilation_restatement_agrees`，证据链写成机读字段（互异题录 + 共同汇编出处 + 交叉引用与**逐字引文**，由守卫断言引文确实出现在被引文件里）。EC 那条同时补上旧稿漏用的既有事实：89.78 在本仓库溯源里是 **40 °C = 313.15 K**（正是 EC 冻结温度，相对偏差 0.80%），Reaxys 却标 25 °C，而 EC 熔点 36.4 °C——判决为 `value_matches_but_reaxys_temperature_label_conflicts`，这本身即「Reaxys 温度栏不可信」的内部证据。
10. **与既有结论的关系**：**方向一致，不改结论**——与「外部免费 ε(T) 扩张收官」（ThermoML 在线 / ILThermo 温度维度 / DDB 免费层 / OA 直读四源全证伪）同向，四源证据分别见 `reports/thermoml_online_topup_round6.md`、`reports/ilthermo_probe.md`、`reports/ddb_free_search_probe.md`、`reports/al_round3.md`；本次探测**强化**该结论，不推翻、不重开。
11. **未闭合**：tetraglyme 声明 8 hits 但表内只渲染 7 行（疑缺 39.99 °C 那条）；**PC 声明 10 hits 但只渲染 7 行（差 3 行）**，本轮未读到；EC 的 5.4 @ 25 °C 条目与同物质其余三条差一个数量级，只登记、不判定；TTE 在 Reaxys 与本地都只有单点，缺口未闭合。
12. **本产物不产生任何通道可用性声明**：不说介电通道可用、不说任何家族过门、不替代任何冻结读数；第 9 条是**证据强度**判决，不是通道判决。



---

## 附录 U：L3 回溯验证预注册（锁定）+ 四通道现状对账（2026-09-26）

> 本附录是手册对「机读预注册」的索引。锁定常量的唯一权威是 `probes/l3_backvalidation_prereg.json`（`status = LOCKED`），正文版本在 `reports/decisions_log.md` §14，两者由 `tests/test_l3_backvalidation_prereg.py` 看守。

### U-1 锁了什么

- **冠军集**（真值逐字取自冻结表 `data/dielectric_v03.csv`，digest `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`）：
  - 溶剂侧：EC `KMTRUDSVKNLOMY-UHFFFAOYSA-N`（ε=90.5）、PC `RUOJZAUFBMNUDX-UHFFFAOYSA-N`（ε=64.9）；
  - 添加剂侧：FEC `SBLRHMKNNHXPHG-UHFFFAOYSA-N`（ε=78.4）、VC `VAYTZRYEBVHVLE-UHFFFAOYSA-N`（ε=126.0）。
- **判据（合取，没有部分通过）**：C1 召回（**K = 20**，两清单各 2/2）∧ C2_solvent（**|Δlog10(ε)| ≤ 0.10**）∧ C2_additive（**≤ 0.15 eV**，直接沿用既有还原门 `p4_redox_summary.json → gate.threshold_mae`）∧ C3 阴性对照（置换种子 **20260928**，对照臂进前 20 的冠军数 **≤1**）。
- **排除四层 L1–L4**：训练集 / 特征构造 / 选择环节 / 评分路径，冠军一律不得进入。
- **池规则**：每清单 **≥100 个可评分分子**（`min_scored_per_list = 100`），不足即判「效力不足」；池必须先落盘并把 sha256 写入 `pool_rule` 才允许评分；**反挑选**：纳入口径不得以冠军排名为条件。
- **阶段一试点**：允许先只跑介电通道、池内、只报 EC/PC，但必须显式标注 `stage_1_pilot_not_a_verdict`，不得作为结论引用。

### U-2 不对称（必须照写，不许含糊）

FEC 与 VC 的 `model_ready` 本来就是 `false`，它们**已经**不在冻结介电拟合集里 —— 介电通道对它们无需额外剔除；真正需要额外剔除的只有 EC 与 PC。**不许**写成「四个都做了留一」。

### U-3 四通道现状对账（只读子智能体实测审计，2026-09-26）

| 通道 | 判决 | 关键事实 |
| --- | --- | --- |
| 介电排序 | 部分可运行 | 口径已冻结（raw→R²、`log(epsilon-1)`→排序）；适用域闸门 `src/electrolyte_ml/applicability.py`，触发率 **33.66%**；**无持久化模型文件**；无 `SMILES→ε` 入口 |
| 氧化还原 | 部分可运行，**门是红的** | R²=**0.9443164629360373** 是 IP→氧化自由能**一维线性映射**在 78 行留出集上的值；预注册门 `MAE<0.15 eV` **未过**（实测 **0.2905180517963865**）；还原侧 **0.4096** |
| HOMO/LUMO | **出口 2 模型不存在** | 附录 Q-2 的 `models/homo_lumo_baselines.json` 全仓零命中；池内真值可用（Batt-P30K 29,519 分子）；唯一训过的构象敏感目标是偶极矩，R²=0.5636 未过门 |
| 黏度 | 部分可运行（全局） | **族内排序在代码层没有实现物**；全局资产齐全 |

**现成起点**：`probes/al_round1.py` 是全仓唯一现成的端到端筛选入口（`Batt-SLM.smi` 115,756 行 → hazard_excluded 29,808 → safe 85,921 → longlist 300 → top30 30）。

### U-4 两处订正（本轮新增，必须传下去）

1. **黏度的 0.064 / 0.175 是 `log10_cP` 的 MAE，不是 R²**（出处 `probes/viscosity_baseline_summary.json` 的 `splits.*.models.MorganTemperatureXGBoost.log10_cP.mae`）。此前多处写作「R² 0.064 vs 0.175」属口径笔误；教训本身不变（同分子跨折会虚高，`primary_gate` 里 `group_key_passed = false`）。
2. **「RX-392 R²=0.944」≠「氧化还原通道能用」**：它是一维线性映射的留出 R²，且其预注册门是红的；把 0.944 当成四通道里最可靠的那条会误导排期。

### U-5 启动完整跑批前的阻塞项（按依赖排序）

1. **HOMO/LUMO 出口 2 模型**（附录 Q-2）必须先训练并过 `MAE ≤ 0.2 eV` 门；
2. **氧化还原门必须先变绿**（`MAE < 0.15 eV`），否则 C2_additive 预先注定不过；
3. 介电通道需要不依赖名册样本外的 `SMILES→ε` 正式入口，**或**把池限制为名册内并如实声明；
4. 池定义落盘 + sha256 写入 `pool_rule`，然后才允许评分。

**纪律**：判据先锁、后跑批、事后不放宽（与附录 T 的 §10/§11 同一条）。

### U-6 池闸门落地与阈值 rationale 勘误（2026-09-26 同轮 amend；锁值未动）

- **池闸门**：`probes/l3_backvalidation_prereg.json → pool_rule` 新增四个预留运行时字段（`pool_path` / `pool_sha256` / `pool_size_by_list` / `pool_frozen_before_scoring`，初值 `null` / `null` / `null` / `false`），并新增 `amendment_1` 元数据；`stage_1_pilot` 新增 `verdict_eligible = false`。守护测试新增 4 条，其中一条是**「评分产物 `probes/l3_backvalidation_run_summary.json` 存在 ⇒ 池字段必须非 null」**（该文件今天不存在，闸门空转，跑批那天才咬人）。
- **阈值 rationale 勘误**：C2_solvent 的 rationale 原把 `probes/v032_target_scaffold_summary.json` 的 `log_epsilon_minus_one['Morgan+Physical'].mae.mean = 6.2727` 读成「log(ε−1) 尺度的点估计 MAE」，据此推出 ≈0.040 log10；同块分层值（`mae_20_60 = 10.79`、`mae_gt60 = 72.64`）证明它是**回变换到 raw ε 尺度**的全表 MAE。原句已逐字保存在 `amendment_1.rationale_erratum.original_text`，正文改动与 `reports/decisions_log.md` §15 成对。
- **这不是放宽阈值**：七个锁定常量（`K = 20`、`0.10`、`0.15 eV`、`20260928`、`max_champion_hits = 1`、`min_scored_per_list = 100`、`pass_expression`）与折号/种子一个字未动（`tests/test_l3_backvalidation_prereg.py::test_pool_rule_amendment_preserves_every_locked_value` 逐值看守）；新增的全是更严的闸门。

**互相指向**：本小节 ↔ `reports/decisions_log.md` §15；T-11 记录同一轮的手册正文订正。

---

## 附录 V：进展索引 —— L3 阶段一试点 / 出口 2 / 氧化还原 v2（2026-09-26）

> 本附录是本轮三项结果的**索引与读法**，不是新判据。所有数值一律以仓库产物为准（机读 JSON + 报告）；本附录只做导航与「怎么读 / 不许怎么读」。

### V-1 阶段一试点：介电通道 · 池内 · EC/PC —— **未过，但这不是判决**

- 标签 `stage_1_pilot_not_a_verdict`；预注册 `stage_1_pilot.verdict_eligible = false`。
- 池 `probes/l3_stage1_pilot_pool.csv`，**236 行**，sha256 `b838febbca4d65975d1820ae9275215288968979b78756611cb031eb7c408b18`；已回填 `pool_rule` 四个运行时字段 + `amendment_2`。
- **C1 = 0/2**：EC 第 **24** 名（预测 ε 23.0565，真值 90.5）、PC 第 **58** 名（预测 17.0438，真值 64.9）。
- **C2_solvent 未过**：Δlog10 = **−0.5939**（EC）/ **−0.5807**（PC），约为门宽 `0.10` 的 **5.8 倍**。
- **C3 显式未跑**（`c3_not_run_stage_1_pilot`）；**C2_additive 显式未跑**（`not_run_stage_1_pilot_redox_channel_not_executed`）。
- 回归锚点：与 `probes/v032_target_scaffold_summary.json` 六臂 × 9 指标**最大绝对差 = 0.0**，14,160 个逐行预测字符串**逐字符一致** ⇒ 失败不是实现问题。
- 温度：EC `T_K = 313.15`、PC `T_K = 298.15`，与预注册真值温度一致。
- 最有价值的观察：**剔除训练侧后 EC 从第 14 退到第 24、PC 从第 43 退到第 58**（未剔除时 EC 14 / PC 43）；top-20 里 13 个被适用域闸门判为 `outside_associated_liquid`。

**怎么读（硬规定）**：

1. **不得写成「L3 未通过」。** 预注册的 `failure_handling` 只管**四通道完整跑批**；本试点只跑介电通道的一条腿，
   合取式 `C1 ∧ C2_solvent ∧ C2_additive ∧ C3` 因此**无法**被本轮任何数字满足或否定（`verdict_eligible = false`）。
2. **`pool_frozen_before_scoring = true` 是自述值（self-attested）**：旁证只有 mtime 先后 + 一个自身承认
   「无法证明冻结早于看见冠军名次」的闸门；后一条仍靠纪律（纳入口径不得以冠军排名为条件）。
3. 独立只读审读员复核结论：**无 Critical / 无 Important**（锚点、锁值、冠军真值、温度、「未跑」声明、标签、17 条守卫的可咬人性全部成立）。

### V-2 出口 2：HOMO/LUMO/IP/EA 门读数 —— **2/4（「四个全过」未通过）**

| 目标 | 折均 MAE (eV) ± std | 合并 OOF（次级读数） | 判定 |
| --- | ---: | ---: | --- |
| LUMO | 0.13855 ± 0.00286 | 0.13352 | **过门** |
| HOMO | 0.19051 ± 0.00287 | 0.18455 | **过门** |
| IP | 0.20110 ± 0.00321 | 0.19466 | **未过**（差 1.1 meV） |
| EA | 0.23415 ± 0.00379 | 0.22777 | **未过**（差 34 meV） |

- `gate.passed = false`、`targets_passed = 2/4`；协议是**未降级的** `RepeatedKFold(5, 10, 42)`（逐折 seed = 42 + 全局折号，共 50 折）。
- **不许**用合并 OOF 次级口径把 IP 救成「过」（0.19466 < 0.20 只是次级读数）；**不许**据此说「出口 2 已可用」——只有 LUMO/HOMO 两个目标过门。
- 可及下限：**IP 的 0.20 eV 地板是结构性的**（IP−HOMO 常数差 2.403 eV、散布 0.158 eV、r = −0.9876）；
  **EA 是数据受限**（学习曲线未饱和，幂律指数 ≈ −0.165；进 0.20 eV 约需 **2.4× 数据 ≈ 58k**）。
- 特征只允许读 h5 的 `smiles`；`gap`/`homo`/`lumo`/`ip`/`ea`/`dipole`/`quadrupole`/`ener*` 全在 `forbidden_inputs`。

### V-3 氧化还原 v2（富特征）—— **门仍红**

- 留出 MAE 氧化 **0.2174** / 还原 **0.3317**；CV（5×10）氧化 **0.2061 ± 0.0060** / 还原 **0.3183 ± 0.0115**；门 `0.15 eV` **未动**，`passed = false`。
- 相对 v1 最优 **−25.2% / −19.0%**；Dummy 共折 CV **0.9669 / 1.1405**。
- 锚点复现：`deterministic_split(392, 0.2, 42)` → **314 / 78**，`test_id_hash` 逐位相同；v1 `linear` 的 MAE `0.2905180517963865` / R² `0.9443164629360373` **实差 0**。
- 瓶颈是 **n = 392 的标注量**：训练残差 0.0508 / 0.0780（远低于门），学习曲线单调下降**未走平**，单特征曲线基本水平。

**纪律（硬规定）**：**门是红的 ⇒ 氧化还原通道不得被表述为可用**；富特征改善**只作方向证据，不得进任何对外文本**
（与附录 T-1 及 `decisions_log.md` §11 把 Week 11 的 `+0.1241` 从对外文本撤下同一条纪律）。

### V-4 新事实与裁定（本轮）

1. **裁定：`fold_policy` 分歧采纳写手的更严读法。** 预注册 `fold_and_seed.fold_policy` 写「其余行折号逐位不变、只把冠军从其所在折的训练侧剔除」，
   其 `fold_source` 指向 `data/processed/v032_ablation_predictions.csv`（**该表不含 Batt-P30K 分子**）；
   写手按「冠军整体移出建模池（29,519 → 29,515）+ 折号在 29,515 行上由 `RepeatedKFold(5,10,42)` 重新生成」执行，
   预注册 L1 被**严格满足**。**协调者裁定：采纳写手读法**；**同时必须如实记录：预注册的 `fold_policy` 对 HOMO/LUMO 通道的 `fold_source` 指向不成立，
   需下一步 amend 补正 —— 不许假装原本就一致。**
2. **归档盲区：`data/processed/*` 被仓库既有 `.gitignore` 排除**，出口 2 的折记录 CSV 与 OOF 明细 CSV **不进 git**，只能由脚本重跑再生；
   week13 交付包把这两份表**复制进包**作为唯一归档途径。本轮**未改** `.gitignore`（不在写手写入集内）。
3. **门红不得表述为可用**：氧化还原（V-3）与出口 2 的 IP/EA（V-2）**不得**表述为可用；阶段一试点（V-1）**不得**表述为 L3 判决。
4. **自述值边界**：守卫对 `amendment_2` 的自我分类字段（`kind` / `locked_values_unchanged`）属**自我复述**，不是独立证据；
   独立证据是审读员对 week12 快照做的**扁平 diff**（只有 4 个运行时字段填值 + `amendment_2` 新增，无锁定值移动）。
5. **一处表述订正**：`decisions_log.md` §17.7 与守卫 docstring 原写「断言只增不减/未删未弱化」字面为假，已改为准确表述；详见 T-13。

### V-5 下一步与阻塞

1. **出口 2**：IP 卡在门口（1.1 meV）、EA 数据受限 —— 若要 EA 过 0.20 eV，需要约 **2.4× 数据**或换 3D/GNN 表示；**不能**靠放宽特征禁用清单。
2. **预注册 amend**：补正 `fold_policy` 对 HOMO/LUMO 通道的 `fold_source` 指向（裁定已下，文本尚未落）。
3. **氧化还原**：门仍红；学习曲线外推需补标注量（氧化 ≈ n 630、还原 ≈ n 950，仅量级指示，不构成承诺）。
4. **L3 四通道完整跑批**：仍被门槛挡着 —— 出口 2 门 2/4 未过、氧化还原门红、介电通道仍无「名册外」的 `SMILES→ε` 入口
   （备选方案 = 名册内池 + 如实声明，本试点已按此执行）。

**互相指向**：V-1 ↔ 附录 U（预注册与四通道对账）与 `reports/l3_stage1_pilot.md`；V-2 ↔ 附录 Q-2 与 `reports/homo_lumo_baselines.md`；
V-3 ↔ 附录 U-3/U-4 与 `reports/p4_redox_v2_enriched.md`；V-4/V-5 ↔ `reports/decisions_log.md` §18 / §19。

## 附录 W：Week 12–13 判读与路线修订（2026-09-26）

> 命名说明：本地手册已占用 T-13/T-14 与附录 V，本附录取 W 以免合并撞号。

### W-1 两周记账

**Week 12（判决周）**：
- Placebo 三臂落地：Arm A 标签安慰剂 ΔR²=+0.0141（≤+0.02，塌缩 ✓）；Arm B 剂量曲线 25/50/75/100% = +0.0239/+0.0242/+0.1405/+0.1241（非单调 ✗）；Arm C 均值退化臂 +0.1021（保住全量臂 82%）→ **预注册判决：data_volume_effect，+0.1241 不得对外引用**；15 项完整性自检全 PASS；
- xTB 线程根因确诊（OpenMP 浮点归约非结合 → 梯度扰动 → opt 停在不同几何 → RDKit 体积网格翻转）；修复 = 唯一启动器钉死 OMP_NUM_THREADS=1；验收：钉死后 max_distinct_geometries=1、离散度 0.0；
- Reaxys 首刀：FEC 仅 Kobayashi 2003 一条（无 107 腿，Hagiyama 仍唯一收口路径）；VC 净新增 0；GVL 36.9(Segato 2021) vs 36.1(iScience 2026) 冲突待判且本地 0 观测（v1.x 第一优先缺口）；DME +1 条 Werblan 1985 温度区间线索；sulfolane 八点逐点独立再确认；**MOPN 三级否定，Reaxys 侧路线关闭**；
- Reaxys 数据模型实测：Static Dielectric Constant 无频率列、Dielectric Constant 有频率列、**方法字段不存在**。

**Week 13（闸门周）**：
- L3 回溯 Stage-1 试点（非判决）：C1 recall@20 = 0 命中（EC 24 名 / PC 58 名）；C2 溶剂 EC 预测 23.06 vs 90.5、PC 17.04 vs 64.9 均超差；C3 与 C2_additive 未跑；最有价值观测 = 移出训练侧后 EC 14→24、PC 43→58；
- HOMO/LUMO 基线（Q-2 出口 2 执行）：池 29,515 行（29,519 − 4 冠军），5×10 RepeatedKFold seed 42：HOMO 0.1905 ✓ / LUMO 0.1386 ✓ / IP 0.2011 ✗ / EA 0.2342 ✗ → 四门判据 2/4 未过；写者拒绝以 pooled-OOF 0.19466 抢救 IP（纪律正确）；
- Redox v2 enriched：留出 MAE 氧化 0.2174 / 还原 0.3317（门 0.15，双挂）；重复 CV 同判（0.206/0.318）；瓶颈诊断：在样 0.078 vs 留出 0.332 → **天花板是 392 条标签，不是模型容量**；v1 锚点逐位复现（MAE 0.2905180…, R² 0.9443164…）；
- Reaxys v1.x 备货扫描（手动合规）：167 队列（P1:2/P2:22/P3:143）净增仅 **4 个温度点 / 2 物质**（PC 20/35 °C@2 MHz；tetraglyme 45/55 °C@1 MHz）；PC 双题录同值降级为 compilation_restatement_agrees（同指 Riddick 汇编，非独立测量）；**EC 89.78 被 Reaxys 错标 25 °C（熔点 36.4 °C 以下非液态）→ Reaxys 温度栏不可信的内部证据**；该探针"加固而非重开"外部免费 ε(T) 扩张已收官的结论；
- 合规与工程：Raman 2 Critical + 7 Important 全修（restricted_values_contract 机读化、PC 判决降级、106/69 口径拆分、校验器 36→70 项）；Sartre 3 Important + 4 Minor 全修；自查修复 verify_export_manifests 静默跳过 week11–13；1807 测试绿 / ruff 绿 / week13 导出 36 文件 / manifests week1–13 全 PASS；冻结红线（v03 digest、池 b838febb…、试点摘要 212ec249…）未动；预注册按设计变为 77f61a83…。

### W-2 同构性判读：三个红灯指向同一结论

Placebo（载体=化合物覆盖而非温度分辨率）+ band ablation（窗口外行 −0.086）+ L3 试点（EC/PC 安静地错）——**"温度维度提升精度"叙事三向证伪，收回**。v1.x 观测表的正确定性 = 覆盖/模式资产（coverage/schema gain），精度杠杆只剩化合物覆盖。

**本轮最危险的实证发现**：EC/PC 上没有任何现存闸门开火——结构 SMARTS 规则针对缔合液体（EC/PC 的 O 不带 H），模型对极性非质子高 ε 候选是**无旗标的安静错误**。第二篇论文的故事因此更清晰：边界③不是论文修辞，是筛选漏斗的实弹失效模式。

### W-3 路线修订 D1–D5（漏斗规范级）

- **D1 v1.x 重新定性**：观测级 ε(T) 表 = 数据模型/覆盖资产，放弃一切精度提升表述；AL Round 4 取向从新温度点切换为**新化合物**；
- **D2 L3 回溯双轨重设计**：轨 A 域内召回（留出 glyme/腈类域内好溶剂考排名）；轨 B 域外旗标（EC/PC 类候选的正确行为 = 被闸门拦下并路由到实测/物理估计）；配套新探针 = **特征包络闸门**（候选 μ²/Vm 等特征超训练域包络 → 强制升旗），规格周三预注册；论文必须写明 236 池 → 29.5k 池的召回难度 scaling；
- **D3 Redox 通道降级**：从排序通道改为粗滤通道 + 宽不确定带；标签增长投稿后议；
- **D4 HOMO/LUMO 按目标分域**：漏斗只用 HOMO/LUMO 模型（过门）；IP/EA 限池内 Batt-P30K 真值，池外不作预测；
- **D5 Reaxys ε(T) 备货线降权**：残余动作 = tetraglyme 7/8 与 PC 7/10 渲染差行收尾（低优先）；Reaxys 主战场回到冲突裁决与液态窗口过滤；**所有 Reaxys 温度栏取值须回溯一手文献核实后方可引用**。

### W-4 Week 14 逐日表

| 日 | 任务 | 门 |
|---|---|---|
| 周一 | **用户本人填 cover_letter.md:71-73 → 投稿** | 提交回执（全项目唯一红灯） |
| 周二 | week12 包 reaxys_dielectric_queue_first_cut.* 合规串按 restricted_values_contract 同口径改写 | 校验器全过 |
| 周三 | L3 双轨预注册 v2 + 特征包络闸门探针规格 | 入 decisions_log §11 |
| 周四 | 包络闸门探针开跑；AL Round 4：人读 4 篇 human_reading_list OA | 探针摘要 + 阅读笔记 |
| 周五 | 20 篇 pending OA 分流；周收尾审计 | 审计报告 |
| 缓冲 | Reaxys 差行收尾会话 | 闭合或登记 |

### W-5 对账（Orchestrator 侧）

- ✗ 附录 S 称 +0.1241 为"v1.x 温度线方向性证据（悬置）"——placebo 判决后连方向性亦不成立，**收回**；S-5 预注册判据本身工作正常（Arm A 过、Arm B 挂 → 合取判 data_volume_effect），判据设计账记对；
- ⚠️ S-5 的二分框架（"样本量/正则化 vs 信息"）粒度不足——实测答案是第三态："信息为真，载体是化合物覆盖而非温度分辨率"，框架已按此修订；
- ✅ N-2/N-3 以来坚持"placebo 不过门不引用"——本轮证明这条纪律直接挡住了一个会写进论文的错误结论；
- 准则沉淀：**"闸门不开火的安静错误比报错更危险"**——适用域建设从'减少误用'升级为'筛选产品的核心组件'。

---

## 附录 X：R² 攻坚纲领（2026-09-26，应用户要求立项：投稿暂缓，精度优先）

### X-1 唯一记分牌（先钉死，后攻坚）

R² 对评分池敏感（同模型：97 池 0.409 / 236 冻结池 0.364 / 1594 行全带池 0.160），没有锁定记分牌则一切"提升"不可比。

- **主记分牌**：固定评分池 457 行 / 97 化合物、GroupKFold by InChIKey、10×5 RepeatedKFold、seed 42（Week 11 paired 设计原样）。只允许训练侧与特征侧变化；
- **辅记分牌**：v1.0 冻结 236 池（与论文 headline 0.364 可比）；
- **泄漏警示价目**：random_row 切分 = R² 0.934。任何逼近 0.9 的读数，第一动作是泄漏审计，不是报喜。

### X-2 阶梯与天花板

| 档 | R² | 载体 | 状态 |
|---|---|---|---|
| 到手 | 0.409 → 0.533 | +50 化合物（训练池 97→147） | ✅ 实测；0.5332 作为"147 池在 97 固定评分池的分组 CV"如实描述可用——placebo 枪毙的是温度分辨率**归因**，不是这个数 |
| 到手 | 0.533 → 0.545 | 新化合物 xTB 特征块 | ✅ 实测 0.5454 |
| 下一档 | 0.58–0.65 | 化合物覆盖再翻倍 + 盲区靶向特征 + 目标变换 | 数周 |
| 努力档 | 0.65–0.72 | Uni-Mol 3D / 两阶段专家模型 / MD 补尾 | 探针级，不确定 |
| 不可达 | →1.0 | —— | 噪声地板（同源共识偏差中位 0.6%、p95 6.4%）+ 样本量 + 结构→集体极化的固有信息缺口（缺 Kirkwood g 维）封死；文献同类上限 0.7–0.8 |

### X-3 七杠杆（全部预注册：判据 + 枪毙线先行）

| # | 杠杆 | 预期 ΔR² | 成本 | 备注 |
|---|---|---|---|---|
| 1 | 化合物覆盖（AL Round 4 转新化合物；OA 人读 4+20；GVL 等真缺口） | +0.05~0.12 / 50 个，递减 | 高（人工） | 唯一实证杠杆 |
| 2 | 缔合盲区靶向特征（HBD/HBA、可缔合位点密度、分子内氢键竞争） | +0.02~0.05 | 半天 | 打最大误差块（33.7% 行、MAE 11.5） |
| 3 | log(ε−1) 训练目标 + Huber 损失 | +0.02~0.04 | 半天 | log 变换已证 Spearman 0.880，原始尺度 R² 红利未收 |
| 4 | xTB 全表迁移（v0.4 决议；线程已钉死）+ 构象平均偶极 | +0.01~0.03 | 1-2 天算力 | 路障已清 |
| 5 | 两阶段专家模型（闸门 → 缔合/非缔合 specialist） | 探针级 | 1 天 | 缔合样本 ~80 条，勉强 |
| 6 | Uni-Mol 3D 微调 | 0~0.10 | 2-3 天 | 236 样本微调高风险，失败记负结果 |
| 7 | bagging 集成 | ~+0.01，主收益=方差收窄 | 半天 | 治"方差过大"旧抱怨 |

### X-4 反作弊纪律

1. 每杠杆预注册进 decisions_log §12，判据与枪毙线先于跑批；
2. 禁止：random-row 切分、测试残差指导特征选择、静默缩域、改评分池/折号；
3. 冻结红线不动：dielectric_v03.csv digest 永不改，新数据只进 v1.x 工作表；
4. **shots 计数**：对主记分牌的尝试次数逐次登记；多重比较下的单次"成功"不作数，需独立重复确认；
5. 每个杠杆带 Dummy/安慰剂对照（沿用 S-5 三臂传统）。

### X-5 Week 14 修订逐日表（投稿暂缓版）

| 日 | 任务 | 门 |
|---|---|---|
| 周一 | 预注册三连：杠杆 2（盲区特征）+ 杠杆 3（目标变换）+ 杠杆 7（bagging） | decisions_log §12 三条 |
| 周二 | 杠杆 2、3、7 开跑 | 各自摘要 JSON |
| 周三 | 三杠杆判读；过门者合并复测 | 合并臂 Δ 报告 |
| 周四 | 杠杆 4：xTB 全表迁移裁决（v0.4）+ 构象平均偶极 | 迁移 diff 报告 |
| 周五 | AL Round 4 启动（新化合物取向）：OA 人读 4 篇 + Reaxys GVL 冲突裁决 | 补录清单 v0 |
| 缓冲 | cover letter 三字段（用户本人，5 分钟）；Uni-Mol 探针设计 | —— |

### X-6 边界与对账

- 用户指令"投稿暂缓、精度优先"已执行；登记风险一条：cover letter 仅差三字段，拖延无工程收益，建议在任意等待间隙填掉；
- 0.533/0.545 两数可用性的措辞边界：**只许带池定义引用**（"147 化合物训练池 / 97 化合物固定评分池"），不许与 v1.0 headline 0.364 直接比大小（池不同）；
- 天花板判断（0.7–0.8）基于：噪声地板实测（week11 frequency_gate noise_floor）、文献同类上限、Kirkwood g 信息缺口三方面；若 Uni-Mol 或 MD 路线突破此区间，须以泄漏审计为前提接受。

---

## 附录 Y：KPI 论文（Gao et al., Angew 2025, e202416506）判读与计划修订（2026-09-26）

### Y-1 论文要点速查

- **出处**：Yu-Chen Gao et al., "A Knowledge–Data Dual-Driven Framework for Predicting the Molecular Properties of Rechargeable Battery Electrolytes", Angew. Chem. Int. Ed. 2025, 64, e202416506（Hot Paper）；清华化工系陈翔/张强组；通讯邮箱 xiangchen@mail.tsinghua.edu.cn；
- **框架**：三模块闭环——(a) API 自动采集 + 隐式先验过滤（Molwt<600、#Heavy<30、11 种元素）→ 4,235 MP / 4,153 BP / 3,504 FP 分子；(b) 64 维 RDKit 描述符 + SHAP 知识发现（MP 由键性质主导 48.9%、BP/FP 由原子数质量主导 ~48% + 电子性质 ~14%）；(c) Uni-Mol 微调 + 知识控制器（纯度控制器 = 拼入表征的知识向量维数 top-K；流量控制器 = 可学习嵌入比例）+ 11 构象输入；
- **成绩**：R² 0.974/0.990/0.986，MAE 10.5/4.6/4.8 K；知识嵌入相对纯 Uni-Mol 降 MAE 6.7–17.8%，相对纯描述符 RF 降 51.9–68.2%；20 个基线数据集 18 个 SOTA；
- **筛选**：QM9 133,885 → 结构过滤（去活性氢等）51,001 → MP<230K → BP>430K → FP>360K → 15 有 CAS + 14 无 CAS；邻域搜索（DOL/EA 为中心，MACCS+t-SNE）；筛出 PC、腈类（含 MOPN 同族，其 ref[35] 即 MOPN 电解液文献 Langevin JMCA 2022 / Qin Angew 2024）；
- **数据可用性**："available from the corresponding author upon reasonable request"（非开放）；SI 含筛选清单（S19–S21）、64 特征定义（S6–S9）、基线数据集信息（S26–S28）。

### Y-2 冷静剂：为什么他们的 0.99 不改变我们的天花板

1. 目标难度：BP/FP 是 Molwt/#Heavy 主导的单分子性质（BP-FP ρ=0.97），ε 是集体极化性质（Kirkwood g 信息缺口）——不同量级；
2. 协议强度：KPI 用随机 8:1:1 + 4 折 CV，无分组/scaffold/适用域/不确定性——按本项目纪律不入围；**我们的 10×5 GroupKFold + 闸门 + 三边界是方法论差异化卖点**；
3. 推论：ε 攻坚阶梯（附录 X）不动；MP/BP/FP 自训预期可复现 0.95+（目标易、数据量同级）。

### Y-3 计划修订 D6–D9

**D6 液态窗口通道升级（本周启动）**：
- 出口 a（首选）：邮件请求陈翔组 MP/BP/FP 数据集。骨架要点：自介（本科生+电解液 ML 项目）→ 具体请求（SI 之外的结构化 MP/BP/FP 表）→ 互惠（我方 Zenodo 公开数据集 DOI 10.5281/zenodo.22957695 可为其介电维度所用）→ 合规承诺（注明出处、遵守其使用条件）；
- 出口 b（两周无回复触发）：PubChem PUG-REST 自采 + Wiley SI 下载（S19–S21 筛选清单、S6–S9 特征表）；
- 出口 c（数据到手后）：按 KPI 配方自训三模型；验收门 MAE ≤ 10.5/4.6/4.8 K 量级；协议用本项目标准（分组 CV），不用他们的随机 8:1:1。

**D7 Uni-Mol 探针规格升级（附录 X 杠杆 6 修订）**：知识控制器机制（SHAP top-K 纯度 + 可学习流量 + 11 构象）写入预注册；枪毙线不变（236 样本打不过 hybrid XGBoost 即停，记负结果）；新增零成本杠杆：**SHAP 知识发现模块**（hybrid 模型上跑 SHAP → ε 主导特征分析 → 论文一节 + 特征剪枝依据）。

**D8 漏斗模板采用**：第二篇论文筛选图对标 KPI Fig.5b 级联（池 → 结构过滤 → 逐通道阈值 → 短清单），我方增两层差异化：适用域闸门 + 不确定性带；邻域搜索模块并入漏斗规范；交叉验证：我方漏斗独立筛 Batt-P30K，与 KPI 15+14 清单比对交集（交集 = 互证，无交集 = 分析分歧来源）。

**D9 定位与引用**：v1.0 投稿稿 related work 检查补引 e202416506；定位话术 = KPI 管线解决热学性质，我方解决介电 provenance + 边界 + 适用域，互补不撞车；开放性是护城河（我方 Zenodo 公开 DOI vs 对方"请求才给"）。

### Y-4 不变项与防线

冻结红线、主记分牌、+0.1241 禁引、Reaxys 合规、四通道门禁全部不动；MP/BP/FP 是漏斗**通道**不是新论文方向——防 scope creep；KPI 方法若引入，协议一律按本项目标准重做（分组 CV、预注册、安慰剂对照），不移植其随机切分习惯。

### Y-5 对账（Orchestrator 侧）

- ✅ 附录 N-3/X-3 预判"Uni-Mol 预训练 3D 是 v2.0 候选杠杆"——KPI 提供独立实证支持，探针优先级上调；
- ⚠️ 附录 R 把液态窗口过滤层排在"PubChem/Reaxys 逐条查"——低估了现成数据集可能性；D6 出口 a 若成功，该通道成本从月级降到周级；
- 准则沉淀：**"顶刊同期工作先拆协议强度再看数字"**——0.99 的 R² 在随机切分+易目标下不构成对我方天花板的反驳。

---

## 附录 Z：新数据集立项裁决——"做得比他们好"的可检验定义（2026-09-26）

### Z-1 志向校准

用户决议：自研新数据集且优于 KPI。Orchestrator 校准：**不在 KPI 主场（MP/BP/FP）拼规模**——封闭数据 + API 爬取 + 顶配团队，规模轴必输。赢面在对方共同软肋、且我方已被证明的轴上：开放、溯源、温度分辨、可校验、协议强度、适用域。

### Z-2 格局核查（2026-09-26 实测）

| 方向 | 在任者 | 开放度 | 裁决 |
|---|---|---|---|
| MP/BP/FP | KPI（Angew 2025, e202416506）：4,235/4,153/3,504 分子 | 封闭（upon request） | 不做 |
| 黏度（分子液体） | Schrödinger 组 Chew et al., J. Cheminformatics 2024（s13321-024-00820-5）：4,440 温度分辨黏度点 + QSPR/MD 描述符，验证过 6 个电池溶剂（MA/EA/MB/MP/DMC/EMC） | 部分开放：Availability Statement 原文仅 3,582/4,440 可公开（版权限制） | 不做纯黏度对打；见 Z-5 |
| 黏度（DES） | ORNL Mohan 2024：573 DES / 4,423 点 | — | 体系不同，无冲突 |
| 多性质预训练集 | arXiv 2504.18728：241,414 条 / 11 性质（含 ε、η），来源混杂 | 不明 | 竞争观察项，不追 |

**关键待核实假设**：我方存量"黏度 3,582 行 / 957 keys"与 Schrödinger 开放子集（3,582 条）数目完全一致——大概率为同一文件。Week 14 第一项：digest + 来源字段逐行对照确认。

### Z-3 "比他们好"的六条可检验轴

| # | 轴 | KPI | Schrödinger | 我方目标 |
|---|---|---|---|---|
| 1 | 开放 | 封闭 | 80%（版权截断） | CC-BY + Zenodo DOI 全量 |
| 2 | 逐值溯源 | 无 | 受限 | 每行 source DOI + 冲突披露 |
| 3 | 温度分辨 | 单点 | 有（温度是特征） | 观测级 (值, T, 方法, 出处) 元组 |
| 4 | 机器可校验 | 无 | 无 | SHA256 manifest + 验证器 + 冻结 digest |
| 5 | 评估协议 | 随机 8:1:1 | 随机 | GroupKFold by InChIKey + scaffold holdout |
| 6 | 适用域/不确定性 | 无 | 无 | 闸门 + 置信带元数据 |

### Z-4 杀手锏：ThermoML 语料的第二收割

本地 242 XML ThermoML 语料为 ε 重解析过一轮，**同一批文件含黏度字段未收割**——重解析管线现成，边际成本近零。**ε+η 联合观测表（同溶剂、同温度、同溯源）无现存竞品**：漏斗双通道同源生长，Walden 型 ε-η 耦合分析为白送增项。

### Z-5 立项裁决

- **立项**：电解液溶剂 ε+η 温度分辨联合数据集（工作名 ηε-joint）= 论文 #2 素材（Scientific Data 型）；
- **不做**：MP/BP/FP 重做（KPI 主场）、纯黏度对打（Schrödinger 在任）、redox 一期（实验溯源混乱：参比电极/溶剂/扫速三自由度过载，留二期）；
- 定位话术："在任者给量，我们给可信 + 开放 + 联合"。

### Z-6 启动序列（Week 14–15）

| 序 | 任务 | 门 |
|---|---|---|
| 1 | 存量核对：本地 3,582 行 vs Schrödinger SI（s13321-024-00820-5 Additional files）逐行对照 | digest/来源一致性报告 |
| 2 | ThermoML 黏度重解析探针（纯计数）：多少 InChIKey 有黏度+温度序列；与 ε 观测表重叠数（= 联合表骨架规模） | 计数摘要 JSON |
| 3 | 预注册建造协议：复用 v1.0 全套（model_ready 闸门、冲突不平均、GroupKFold、manifest、受限值纪律） | decisions_log §13 |
| 4 | **并行：v1.0 cover letter 三字段 + 投稿**（用户本人 5 分钟） | 提交回执 |

### Z-7 风险与防线

1. WIP 翻倍风险：v1.0 未投稿前不开第二条写作线，ηε-joint 只做数据工程不动笔；
2. 若 Z-6 序 1/2 核实后格局有变（如存量非 Schrödinger 子集、ThermoML 黏度重叠过少），预注册允许中止并回滚本附录裁决；
3. 防 scope creep：ηε-joint 服务漏斗通道 3/4，不是独立帝国；redox 二期与否视投稿后精力再议；
4. 版权纪律：Schrödinger 受限 858 条（4,440−3,582）不得绕版权获取；其开放子集的再利用遵守其许可并注明出处。

### Z-8 对账（Orchestrator 侧）

- ✅ 附录 Y/D6 将液态窗口通道押在"向 KPI 请求数据"上——维持，但该通道与本立项互不依赖；
- ⚠️ 此前手册把黏度通道标为"族内排序、参照级"——低估了存量资产价值；Z-4 的重解析第二收割是本轮回最值钱的新发现；
- 准则沉淀：**"立项前先问在任者的地基是不是已经在你手里"**——3,582 这个数若早一点对上，可以省一轮方向摇摆。

---

## 附录 AA：Reaxys/PubChem 分工细化与 Week 15–16 精细计划（2026-09-26，基于 KPI SI 全文拆解）

### AA-1 两库分工（一句话版）

**PubChem = 收割机（批量、开放、进数据层）；Reaxys = 法官（手动、逐条、只裁决不进表）**。依据：合规（PUG-REST 允许合理批量；Reaxys 批量导出违 ToS）+ 开放红线（ηε-joint 全量开放，Reaxys 值永不进可分发数据集）。

### AA-2 三层数据流架构

| 层 | 职责 | 工具 | 产物 |
|---|---|---|---|
| L0 身份层 | InChIKey↔SMILES↔CID↔CAS 映射；别名注册表扩充 | PubChem PUG-REST 批量 | identity_map.csv + aliases |
| L1 开放收割层 | ε（已完成）；η（ThermoML 重解析 + Schrödinger 开放子集 3,582）；MP/BP/FP/密度 | ThermoML 管线 + PubChem 批量 | ηε-joint 观测表 |
| L2 裁决/QA 层 | 冲突裁决（FEC/VC/MOPN/GVL 队列延续）；重解析抽样复核；PubChem 值抽查 | Reaxys 手动逐条 | 裁决台账（restricted_crosscheck_only） |

**质量双层纪律**：可发表层（ε/η 核心值必须带一手 source DOI，KPI 式汇编爬取不达标）vs 漏斗过滤层（PubChem 汇编值可用，打 compilation 旗标）。KPI 的 MP/BP/FP 数据源 = PubChem API + ChemSpider API + AAT Bioquest + Li Fuel 2021 / Liu Fuel 2022 两篇——即汇编级，我方"更好"的第一条轴（逐值溯源）正打在这里。

### AA-3 KPI SI 五件战利品

1. **64 特征全表**（S6–S9）：原子/质量 7（Molwt/#Heavy/#C/#O/#O#C/#Het/#Het#C）+ 键 17（#R=R/#R#R/#Donor/#Accept/#Rot/#Ring/#Nring/脂环芳环系列/#Bran）+ 官能团 ~33 + 电子性质（AvgI/AvgA/AvgX = Σ元素性质×原子数/总原子数，查表即算；MinAPC/ValE 等）→ Week 15 复刻为特征模块（1-2 天）；
2. **Uni-Mol 超参**：RDKit 10 构象 + LMDB；Adam + smooth MAE；batch 32；≤500 epoch；early stop patience 20；lr 1e-4 多项式衰减 → 我方 Uni-Mol 探针规格照抄；
3. **筛选级联数字**：QM9 133,885 → 结构过滤（去 –OH/–COOH，Molwt<600，#Heavy<30）51,001 → MP<230K → 13,155 → BP>430K → 3,619 → FP>360K → 35 → CAS 分拆 + SAscore>0.9 → 15+14 → Batt-P30K 漏斗各级存活数预注册对标；
4. **15+14 清单**（SI Fig. S20/S21，含 CAS/SMILES/三性质值）→ 抠取后跑我方漏斗交叉互证（D8）；
5. **邻域搜索参数**：一级半径 = 3% 聚类图最大笛卡尔距、二级 10%、性质差 ≤30 K → 直接移植。

### AA-4 Week 15（数据层周）

| 日 | 任务 | 门 |
|---|---|---|
| 一 | ThermoML 黏度重解析探针（纯计数：η+T 序列的 InChIKey 数；与 ε 观测表 153 化合物重叠数） | 计数摘要 JSON |
| 二 | 存量核对：本地 3,582 行 vs Schrödinger SI（s13321-024-00820-5）逐行对照 | 一致性报告 |
| 三 | PubChem 身份层管线 + 别名注册表扩充 | 映射覆盖率报告 |
| 四 | KPI 64 特征模块复刻 + 单测 | 模块入库 |
| 五 | SHAP 跑 ε hybrid（附录 Y/D7 落地） | 特征排序报告 |

### AA-5 Week 16（schema + 首建周）

| 日 | 任务 | 门 |
|---|---|---|
| 一 | ηε-joint schema 预注册（观测级：value/T/方法/出处/质量层旗标） | decisions_log §13 |
| 二 | PubChem 液态窗口批量收割（限流；记录 depositor） | 收割清单 |
| 三 | 首建合并：ε 观测表 ∪ ThermoML-η ∪ Schrödinger 子集（全带 provenance 列） | 构建脚本 + manifest |
| 四 | Reaxys 裁决会话：η 冲突抽样 ~20 条 + PubChem 抽查 ~10 条 | 裁决台账 |
| 五 | KPI 15+14 清单抠取 + 漏斗交叉试跑 | 交集分析报告 |
| 缓冲 | Uni-Mol 探针规格定稿（KPI 超参 + 知识控制器） | 预注册文本 |

### AA-6 防线与对账

- Reaxys 纪律重申：手动逐条、禁爬虫、restricted_crosscheck_only、永不进可分发数据集；其温度栏取值须回溯一手核实（EC 89.78 错标事件）；
- PubChem 纪律：合理限流；depositor 来源记录；汇编值只进漏斗过滤层并打旗标；
- 版权：Schrödinger 受限 858 条（4,440−3,582）不得绕版权获取；开放子集再利用须遵其许可并注明出处；
- ✅ 对账：附录 Z-6 序 1/2 假设本周即可证实/证伪；若"存量=在任者子集"证实，则 ηε-joint 的净新增主要来自 ThermoML 重解析 + OA 人读，规模预期据此校准；
- 准则沉淀：**"收割机与法官分开，质量层与过滤层分开"**——数据工程的四象限纪律。

---

## 附录 AB：Week 14 收口 —— 六杠杆、包络闸门与 AL Round 4（2026-09-26）

> 命名说明：本附录起草时按字母序取 **Y**，但手册随后由用户改写，**附录 Y 已让给「KPI 论文判读」**（`reports/kpi_framework_mapping.md`，见手册正文），本附录改用 **AB**，紧随 **附录 AA（Week 15–16 计划）** 之后。机读台账见 `reports/decisions_log.md` **§22**（预注册）与 **§23**（读数、判决、shots 计数、缺陷登记）。

### AB-1 本轮范围与记账

- **六杠杆开跑**：2（缔合盲区靶向特征）、3（log(ε−1)+Huber）、4（xTB v0.4 构象平均偶极迁移）、7（bagging）、8（Li⁺ 配位块）、9（知识纯度扫描）。**未开跑**：1（已由 2 覆盖）、5（两阶段专家）、6（Uni-Mol）。
- **并行非杠杆项**：D2 轨 B 特征包络闸门、AL Round 4 取向切换（新化合物）、KPI 框架映射（Angew. 2024 Gao，`10.1002/anie.202416506`）。
- **shots**：对主记分牌的尝试共 **10 次**（杠杆 2/3/4/7 各 1、杠杆 8 **2**、杠杆 9 **4**）；**包络闸门那 1 次另计**（校准读数、买不到 R²，**不计入**主记分牌 shots）；合并臂按预注册 `if_nothing_passes` **不开跑**（杠杆 2/3/7 全死），新增实测 **0 次**。
- **基线复现**：七条脚本**各自在脚本内原地重跑** `paired_base`，全部**逐位**复现 `0.4091179943351143`（|Δ| = 0.0，容差 1e-9），三个表示读数（Morgan / Physical / Morgan+Physical）同时命中。复现不成立则 delta 不得引用——本轮七条全部成立。

### AB-2 读数与判决总表

| 编号 | 通道 | 读数 | 判决 |
| --- | --- | --- | --- |
| 2 | +6 列 RDKit 缔合描述符 | R² 0.39723372774460053，**ΔR² −0.0118842665905138** | **dead** |
| 3 | ln(ε−1) + pseudo-Huber | 原始尺度 R² 0.3037456715367863，**ΔR² −0.1053723227983280**（log 空间高 +0.2468，反变换后红利消失） | **dead** |
| 4 | v0.4 构象平均偶极（只迁 `dipole_D` / `mu_sq_over_Vm`） | R² 0.4649564468823552，**ΔR² +0.0558384525472409** | **pass**（覆盖 95/97 化合物） |
| 7 | bagging（n_bags=10） | 均值 **+0.001750**；重复级 σ 0.088967 → 0.082979（**−6.73%**） | **dead**（区间未交付） |
| 8 | Li⁺ 配位块（+5 列） | R² 0.4532，**ΔR² +0.044058816215696295**，正向重复 8/10 | v1 **dead**（条款缺陷，见 AB-4）；v2 **`pass_under_amended_placebo_clause`** |
| 9 | 知识纯度扫描（**每折训练侧内部**排序） | k=2 **+0.002941058158484944** / k=4 **+0.007773677626773612** / k=6 **+0.008825444045175823** / k=10 **+0.014709977559720422**；正向 6/10 | **sub_threshold** |
| D2-B | 特征包络闸门（held-out EC/PC） | 规则 A 升旗 EC（+1.649 IQR）与 PC（+1.752 IQR）；236 池 LOO 升旗率 **80/236 = 0.3390**（规则 B 12/236 = 0.0508） | **`primary_met_secondary_not_met`** |

### AB-3 两枪越线：能说什么、不能说什么

本轮唯一的好消息是**杠杆 4 与杠杆 8 越过了各自的过门线**，这也是最需要设防的地方——10 枪里 2 枪越线，按 §22.5 的规则**本身不构成发现**。

- **杠杆 4（ΔR² +0.0558）**：判据来自附录 X-3 期望带（+0.01~+0.03）的**下沿 +0.0100**，脚本内**跑前写死**。机制旁证扎实：增益**整块落在被迁移的物理列**（纯 Physical 0.2532 → 0.4227，+0.1695），而纯 Morgan 臂四臂**逐位相同**（证明四臂的评分行、折号、模型与分母完全一致，差异只可能来自被迁移的两列）。**代价极低**：xTB 阶段实测墙钟 **268.6 s**（预算 2400 s，用 11%），无需 bounded pilot。
- **杠杆 8（ΔR² +0.0441）**：块把 `li_binding_energy_ev` / `li_binding_distance_a` / `q_max_h` / `q_min_hetero` / `esp_imbalance` 五列并入物理块。v1 因**预注册安慰剂条款构造性缺陷**判 `dead`；v2 以**读后修订的条款文件**（**非盲锁**——它晚于 v1 读数 5 分 47 秒落盘，见 AB-8）**独立重跑一次**（同一块、同一折号、同一打乱标签向量，读数**逐位相同**）后得 `pass_under_amended_placebo_clause`。**v1 的 `dead` 逐字保留、未被推翻。**
- **不能说什么**：① 不许把两枪合并成「本轮 R² 提升 +0.10」——两条杠杆**从未合并复测**；② 不许把杠杆 8 的 v2 判决表述为「v1 判错了」——它是**新增一枪 + 一次条款修订**；③ 不许把 0.4532 / 0.4650 与 v1.0 headline **0.364** 直接比大小（**池不同**：0.364 在 236 冻结池，本轮全部读数在 457 行 / 97 化合物固定评分池）；④ 杠杆 4 的读数**覆盖 95/97 而非全表**（见 AB-7）。

### AB-4 三条纪律增补（= T-16）

**增补一：「塌缩」判据必须写参照物。** 预注册里「安慰剂塌缩 = `|ΔR²| ≤ 0.0200`」未写明参照：对**真实标签基准**取绝对距离时，该式在安慰剂**真塌缩**时**必然不满足**，属构造性不可满足。本轮该式命中五处（杠杆 2/7/9 摘要、杠杆 8 v1 的唯一 kill reason、杠杆 4 的 `control_collapsed` 布尔）。**统一读法（先于杠杆 8 v1 读数落盘）**：塌缩 = 安慰剂臂**不得击败其「同折、同打乱标签向量」上的无信息地板**超过 +0.0200，并**并列**上报管线内增量。此后写作预注册时，塌缩判据**必须**写出「参照物 + 方向 + 容差」三件套。

**增补二：`locked_at_utc` 自述字段不得单独作为锁定证据。** 本轮六份**预注册/修订文件**里 **三份**的自述锁定时间**晚于自身文件 mtime**（最多晚 101 分钟）——锁不可能晚于文件写出。**以文件 mtime 为准**；自述字段照实保留、**不回填**（回填会抹掉审计痕迹）。每一份的自述时间仍早于其对应结果产物的 mtime，故「先锁后跑」在 mtime 口径下全部成立。

**增补三：布尔塌缩字段不得作为门。** `placebo_collapsed` / `control_collapsed` 一律**只作披露字段**，门只用**同一跑内的对照关系**（迁移 Δ 与对照 Δ 的间距、地板距离）。

**附带事实（会影响此后所有「样本量」表述）**：457 行记分池实测只覆盖 **276 个不同的 `(化合物, T)` 对**，即 181 行是同化合物同温度的多来源重复行。GroupKFold 把同化合物整块放一折，重复行整块同行、不制造跨折泄漏——但**「样本量」必须写 276，不能写 457**。

### AB-5 数据侧：AL Round 4 取向切换（D1 落地）

- **取向**：从「新温度点」切换到「**新化合物**」（D1）。产出补录清单 **v0 = 21 行**：真新化合物 **7 个**（P1 = 1，`1,2-dimethoxypropane`），本地重复对账 13 行、族缺口 1 行；`triplet_mismatch_rows = 0`。离线只读、**零网络调用**。
- **pending OA 分流**：20 篇 —— 归档 17 / 人读 1（`10.1021/acsenergylett.2c02003`）/ 仅线索 2 / 取全文 0。**推翻 Round 3 三处**：① 「pending 是待取全文的新线索」不成立（17/20 只含本地已有化合物）；② succinonitrile 是**名册缺口**（熔点 58 °C 被室温窗口挡掉）而非数据缺口；③ TFE 有受限 Springer 介电目录痕迹。
- **本地缺口 top-5**：acid 1/5、lactone 1/5、carbonate **2/10（EC/PC 根本不在观测表里）**、sulfone 2/113、protic_ionic_pair 4/4。
- **综述（`10.1021/acsenergylett.5c02291`）的结构候选**：另出一张 37 行候选表，其中真新 **22 个**（glyme 8 / 环醚 4 / 硅氧烷 4 / 酰胺 2 / 碳酸酯 1 / 硅酸酯 1 / 添加剂 1 / 醚 1）。**对账要求**：该表的 `family` 是自有分类，**与补录清单 v0 的判据类别不是同一套口径**，两份表**不得直接对齐**。

### AB-6 KPI 框架映射的净收获（`reports/kpi_framework_mapping.md`）

- **可搬项 1（已搬，= 杠杆 9）**：知识纯度控制器。**结论是半**：KPI 的「纯度截断」**不被支持**（k=2 只拿最信息量两位仍差于全池），但其「**要编形状不要编原始计数**」**被支持**——最优三位是 `heteroatom_over_carbon`（49/50 折进 top-3，平均名次 1.36）、`donor_acceptor_pair_density`（37/50）、`ring_count`（35/50），而线性计数垫底（`donor_count` 平均名次 8.58、`acceptor_count` 9.88 且平均重要度**恰为 0**，与冻结块 `hba` 近重复）。
- **形状判定**：真实曲线 `monotone_increasing`（**无内部峰值**）→ **证伪的是「知识越多越差」这条定律**，不是「存在最优 k」。k 网格上界 10 = 全池，是**硬顶**，峰值可能在网格之外——诚实表述只能是「冻结网格内无内部峰值」。
- **可搬项 2（纪律）**：KPI 的 SHAP 排序用全量数据 → **泄漏**。我们的版本**每折训练侧内部排序**，比它严；这条已写进杠杆 9 的预注册与守卫。
- **可搬项 3（漏斗规范增补；编号待与 P-3 对账后回填）**：**结构白名单** —— 分子量 0–600 / 重原子 0–30 / 元素 {H, C, N, O, F, Si, P, S, Cl, Br, I}；高通量筛选**先剔除 –OH 与 –COOH**。注意动机相反：KPI 为电化学活性剔除，**我们为缔合盲区剔除**（同一动作、不同理由，必须写明）。
- **第三方旁证我们的天花板**：该文结论段自述「现有分子描述符无法充分描述……先验知识是必要的」——与本仓 X-2「缺 Kirkwood g 维」是同一条独立复述。
- **规模诚实记账**：它 4,235/4,153/3,504 分子 vs 我们 246/97；但它的目标是原子数主导的相变温度（R² 0.97–0.99），我们是**集体极化**（0.409）→ **规模差不是主因，目标信息结构才是**。

### AB-7 下一步（Week 15）与边界

- **候选顺序**：① 杠杆 8 与 v0.4 偶极迁移的**合并臂**（本轮被显式推迟，见 §23.6）；② 杠杆 9 的 k 网格向上延展（**新预注册**，不得拿本轮读数当先验去挑 k）；③ 杠杆 4 的**几何迁移**（`molecular_volume_A3` / `molar_volume_m3_mol` / `alpha_over_Vm`）与宽容构象策略（跑后新增协议变体，须**新预注册**）。
- **杠杆 4 的覆盖边界（不许省略）**：覆盖 **95/97 化合物**（迁移 2027/2029 行）。2 个多组分咪唑鎓盐（`HQWOEDCLDNFWEV-UHFFFAOYSA-M`、`XDJYSDBSJWNTQT-UHFFFAOYSA-N`）在普通 GFN2 单点下 **SCF 不收敛**（exit 128），这 2 行保留冻结偶极。失败是**逐构象**的（各只有 1–2 个坏构象），整化合物判失败来自探针「首个失败即放弃」的 **fail-fast 策略**——要 whole-table 覆盖须改宽容策略，**那是跑后新增的协议变体，本轮故意不跑**。机制早有记载（`probes/xtb_fragment_geometry_defect.py`：单次 ETKDG 嵌入不连通图导致片段重叠）。
- **包络闸门不得宣称为可用过滤器**：主判据（EC/PC 被升旗）成立，但**次判据不过**（236 池 LOO 升旗率 33.9% > 20%），即两规则在池内假阳性过高。
- **杠杆 8 的块覆盖 88/97**：烃/氢氟烷无 O/N 位点，按预注册规则记为「**未定义**」而非「未跑」；三个电荷列取自**孤立溶剂**的冻结运行，非 Li⁺ 扰动后几何。
- **random_row 只作泄漏参照**：`paired_base_random_row_leak` R² = **0.7385332681453336**，**从不进入任何判决**。
- **冻结红线复核（本附录落盘时实测）**：`data/dielectric_v03.csv` `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`、`probes/l3_stage1_pilot_pool.csv` `b838febb…c408b18`、`probes/l3_backvalidation_prereg.json` `77f61a83…6f0db98`、`data/processed/dielectric_observations_v11plus.csv` `159b928f…68a49af9` —— **四条全部 INTACT**；七个锁定常量一个字未动。

### AB-8 落盘后更正与导出契约（2026-09-26，审查收口轮）

- **I-1 溯源坐标（条件式）**：导出摘要新增 `artifacts_commit`（导出时 HEAD）、`worktree_dirty`（布尔）、`worktree_dirty_paths`（计数）与 `provenance_note`。单独一个 `head_commit` 已不足以定位本轮交付件：**导出时 `worktree_dirty=true`**，包内 4 个文件（探针、其 summary、台账、测试）的字节在 `659066a` 里**并不存在**。规则：`artifacts_commit` **只在 `worktree_dirty=false` 时才可作工件坐标**；本轮须在审查收口提交**之后**从该提交重新导出，再引用新的 `artifacts_commit`。**不得**无条件当作坐标。
- **I-2 预注册分类更正**：本轮登记的六份文件**并非全是盲锁件**——实为 **5 份盲锁 + 1 份读后修订**。`probes/dielectric_coordination_block_prereg_v2.json` 于 **04:02:50Z** 落盘，晚于 v1 读数 **03:57:03Z** 共 **5 分 47 秒**，是**读到 v1 条款缺陷之后**才写出的修订，**非盲锁**；`probes/l3_backvalidation_prereg_v2.json` 标为「**仅预注册、本轮未跑**」。该文件本体**不回填**（锁定件照原样留档），mtime 口径规则见 AB-4 增补二。
- **M-1 AL Round 4 计数**：summary 字段 `local_duplicate_reconciliation_rows` 更名为 **`non_new_rows_excluding_family_gaps`**（值仍 **13**），并新增 `row_kind_note` 说明 `by_row_kind` 四项——`new_compound 7` / `local_duplicate_reconciliation 12` / `roster_gap 1`（succinonitrile）/ `gap_family 1`。**CSV 与报告逐字节未变**，仅机读字段改名。
- **M-2 / M-3 键名**：杠杆 8 的 `v2_note` → **`v1_decision_is_still_in_force`**（v1 的 `dead` 逐字保留）；AL Round 4 的 `al_round_4.shots` → **`al_round_4.runs`**（离线本地扫描，非主记分牌尝试）。**主记分牌 `shots` 块不受影响**：仍为 10 次尝试，包络闸门 1 次另计。
- **M-4 无块化合物分母**：新增 `scored_compounds_without_the_block = 9` 与 `coverage_note`，明写分母构成 `compounds_without_the_block = 60 = 9`（`undefined_no_hetero_site`）+ `51`（有记分观测、但在配位块特征表里无行）。
- **M-6 导出守卫接线**：`verification.json` 的 VERIFIERS 新增 `tests/test_manual_appendix_reconciliation.py`（此前只在 CI 的 fixture 路径上校验，未进导出关）；**不含** `test_export_week14_results.py`，避免自引用。
- **残余项（登记不修）**：杠杆 4 的 xTB 迁移探针仍缺 `--check` 与脚本 digest 钉（M-5），本轮**未修**，留作下周技术债。

---

## 附录 AC：Week 15 数据层周 —— 黏度重解析、身份层、KPI 64 特征与 SHAP（2026-09-26）

> 命名说明：紧随附录 AB 之后取 **AC**。范围 = 附录 AA-4 的周一至周五（ηε-joint 数据层）。机读台账见 `reports/decisions_log.md` **§24**。本轮**不动笔、不做建模判决、不碰冻结件**（附录 Z-7）。

### AC-1 三臂并行与写集

| 臂 | 任务 | 交付（新增） |
|---|---|---|
| A | T1 ThermoML 黏度重解析 + T2 存量 vs Schrödinger SI 对照 | `probes/thermoml_viscosity_coverage_probe.py`、`probes/schrodinger_si_reconciliation.py`＋两份 summary＋两份报告＋两个测试＋`data/processed/viscosity_observations_thermoml.csv`（9 件） |
| B | T3 PubChem 身份层 L0 + T4 KPI 64 特征模块 | `data/reference/identity_map.csv`、`probes/pubchem_identity_layer.py`＋summary、`src/electrolyte_ml/kpi_descriptors.py`、两个测试、`reports/kpi_64_feature_module.md`（7 件） |
| C | T5 SHAP 跑 ε hybrid | `probes/dielectric_hybrid_shap.py`＋summary＋两份 artifacts、`reports/dielectric_hybrid_shap.md`、测试（6 件） |

合并后定向测试 **113 passed**，`ruff check src probes tests` 全绿；三臂**均未改动任何已跟踪文件**。

### AC-2 T1：ThermoML 黏度重解析——Z-4 前提证实，但规模须下修

- 全量重解析 **242** 个本地 XML（走仓内 `electrolyte_ml.thermoml.parse_thermoml_file`），11 项验收值与侦察预期**逐项相符**（`expectation_mismatches=[]`）：`viscosity_files=29`、`viscosity_rows=2725`（`Viscosity, Pa*s` 2549 + `Kinematic viscosity, m2/s` 176）、`pure_rows=569`／`mixture_rows=2156`（`pure+mixture=2725`）、`pure_keys=47`、`overlap_eps_obs=37`、`overlap_viscosity_v01=28`、`new_vs_eps_and_v01=3`。
- **「未收割」由假设升级为机读事实**：存量三张抽取表的黏度行数**全为 0**、连黏度列都不存在。
- **规模下修**：纯组分只有 **569 行 / 47 键**，相对 ε 观测表(153) 与存量黏度表(957) 并集，**净新增实体仅 3 键**——Z-4 语气暗示的「千行级新矿脉」**不成立**。
- 边界：本地 XML 只是 NIST 全库（11,923 条记录）的**筛选子集**，「29 个文件」**不是** NIST 黏度总体上界，在线黏度切片核查**本轮未做**；多组分 2,156 行未做溶质/溶剂角色拆分；运动黏度 176 行无密度无法换算。
- 顺带锚点：PC（`RUOJZAUFBMNUDX-UHFFFAOYSA-N`）本地有 **28 行纯组分 η(T)**，而本地无 PC 的 ε——PC 的 η 不需外部源，ε 才需要。

### AC-3 T2：存量 3,582 行 = Schrödinger 开放子集（Z-2 假设落锤）

- 逐行对齐：**`row_aligned_matches=3582` / `mismatches=0`**（`T_K`/`viscosity_cP` 容差 1e-9），`unique_keys=957`，`source_doi` 唯一 = `10.1186/s13321-024-00820-5`。→ Z-2 的「关键待核实假设」**降级为已证实的既定条件**。
- 受限边界：原始 **4,440** 点中仅 **3,582** 可公开，差额 **858** 条受限，**不得绕版权获取**；`4,440` 是论文声称值、**本地不可复算**。
- `supp_3`（650 行 / 50 溶剂）`data_status=predicted`，**并入实验表 0 行**（已由测试钉死）。

### AC-4 T3：PubChem 身份层 L0（314/314）

- 覆盖集 = 名册 246 ∪ lowfreq 50 ∪ ilthermo 47 = **314 键**；**246/246 名册键全部解析**，缺口 **0**，InChIKey 回环 314/314。
- 成本记账（审查收口轮改为只用仓库内可复算的口径）：提交态 `network_calls=0`（缓存全命中）；**可复算的填充痕迹** = `data/external/g1plus/pubchem/identity_layer/` 下 **628 个文件**（314 `.json` + 314 `.url`），mtime 窗口 **2026-09-26T05:49:15Z → 05:55:08Z**（352.7 s），限流常量 `DEFAULT_THROTTLE_SECONDS = 0.25` s/请求（`probes/pubchem_identity_layer.py:62`）。**必须照实说明**：`_harvest_runs.jsonl` 现存各行**全部是收割之后**的缓存命中运行（首行 `05:56:02Z`，晚于窗口结束 `05:55:08Z`，逐行 `network_calls=0 / retries=0`）——**收割那一次本身没有落运行记录行，请求级计数在仓库内不可复现**，不得据此记账。
- 顺带查出：**5 条本地 SMILES 与 PubChem 画法不同**——`identity_check` 全部 `roundtrip_match`、`pubchem_inchikey` 与 `inchikey` **逐字相同**，即**同一 InChIKey 下的画法差异、身份全部无误**（2 条咪唑鎓溴化物本地写电中性、1 条二氰胺本地 `N#C[N-]C#N` vs PubChem `C(=[N-])=NC#N`、2 条酰胺写成亚胺酸互变异构体），待人工决定是否改写本地 SMILES；**2 对立体异构体共用一个 PubChem SMILES** → 身份层**必须按 InChIKey 建键**；**1 条 CID 冲突**；另 10 条为 `ConnectivitySMILES` 无立体层的假警报。
- 本轮**未做任何 Reaxys 裁决**（AA-1：Reaxys 是法官）。

### AC-5 T4：KPI 64 特征模块复刻（列级诚实清点）

- 定义源：正文 PDF **确无** 64 特征表；同目录 SI（64 页）提取成功，Table S6–S9 在字符位 25,973 / 26,471 / 27,310 / 28,719。**未用回退源**。
- 64 列 = **逐字复刻 3**（`AvgX`/`AvgI`/`AvgA`，公式照抄 SI；元素值表论文没印、值取 CRC/NIST）+ **RDKit 原生映射 15** + **本仓自写 42**（论文只给措辞）+ **未确证 4**（`MaxPC`/`MinPC`/`MaxAPC`/`MinAPC`；SI 未说明电荷模型，用 Gasteiger）。
- 已知偏差点：`#R=R` 按字面计入 S=O；`#Bran` 等长链可能差 1；`#Nring` 取 SSSR 最大环；`#Donor`/`#Accept` 用 Lipinski（水会得 0）。名册含白名单外 **B(4)/Si(1)/Fe(1)**，Fe 取 0.0 参与平均并由 `element_coverage()` 暴露。

### AC-6 T5：SHAP 跑 ε hybrid，与【P0 缺陷】杠杆 9 引用表错位

**（a）本轮读数**

- 泄漏守卫在**每折生产路径**执行：`folds_checked=150`、`max_test_rows_visible_to_ranking=0`；折划分**完全复用杠杆 9 主记分牌**（`signature_sha256=864b3a53…86be`），基线逐位复现 `0.4091179943351143`。
- 零依赖实现：`shap` 未安装 → 走 `xgboost.predict(pred_contribs=True)`，末列 bias **被校验剔除**（相对残差 ≤ 4.73e-06）。
- hybrid top-10：`mu_sq_over_Vm`(2.648／平均名次 1.64)、`total_energy_hartree`(1.911)、`tpsa_A2`(1.626)、`molecular_volume_A3`(1.528)、`morgan_bit_0790`(1.326)、`morgan_bit_0427`(0.969)、`morgan_bit_0114`(0.907)、`morgan_bit_0080`(0.738)、`hbd`(0.709)、`morgan_bit_0650`(0.670)；Morgan 50.2% / physical 49.8%。
- **名次极不稳**：2,061 列里 `stable` 仅 6、`unstable` 2,055，**1,880 列从未被任何树分裂**（名次是并列位次而非测量值）。

**（b）【P0 缺陷】杠杆 9 洗错了列 → AB-6 的三强叙述不可引用**

- `probes/dielectric_knowledge_purity_sweep.py:560` 构造 `full = hstack([frozen_physical, knowledge])`（物理块在前），但 `:565` 传 `columns=KNOWLEDGE_POOL`，而 `permutation_importance` 在 `:307` 用 `enumerate(columns)` → **`position` 从 0 起**，洗的是 `full[:, 0..K-1]`（**物理块前 K 列**），**知识池名字只是标签**。
- 后果：k 臂的 `order[:k]` 等价于「按物理列重要度打乱顺序的知识池子集」→ **k=2/4/6 的扫描没有测到它想测的东西**；**k=10 的「选择集」不受影响（十名全取），但其列序由破损排序决定**——探针 `:596-599` 用 `columns = [position_of[m] for m in order]` 定列序，而 `XGB_PARAMS` 含 `colsample_bytree: 0.8`，拟合**依赖列序**，故 **k=10 的列序与读数都不是不变量**。
- 独立复算（同 50 折、另一实现）：`donor_acceptor_pair_density` 49/50、`heteroatom_over_carbon` 42/50、`ring_count` **0/50**；「线性计数垫底」按字面规则**不成立**（`donor_count` 3.60/4.14、`acceptor_count` 5.50/5.88）。与 AB-6 实际引用的表逐折 top-3 一致率 **2/50**，与修正后的置换 **27/50**。
- **k=10 列序复算（审查收口轮独立完成，脚本未入库、待 Week 16 勘误轮固化）**：破损列序 **+0.014709977559720422**（在任上报值）→ 正确列序 **+0.008666009048**，差 **0.006044（41%）**，单重复最大差 **4.878e-02**。
- **裁定（C-1 修正后）**：**AB-6 的逐特征解释与「三强」名单在勘误前不得引用**；杠杆 9 的判决在**两种已测列序下均为 `sub_threshold`**（修正列序值仍未跨过判据带），但**修正排序下的正式 k 扫描尚未跑**、其判决**待 Week 16 勘误轮重跑后确定，不得写成已定结论**；**k=2/4/6 读数所依据的排序无效**。修正需**新预注册 + 独立重跑**（沿用杠杆 8 v2 范式：v1 读数逐字保留、不覆盖），**本轮不跑**，列为 Week 16 首位技术债。

### AC-7 下一步与边界

- **Week 16 首位**：杠杆 9 引用表勘误轮（新预注册 → 独立重跑 → 勘误读数与 v1 并列留档）；其次仍是 AA-5 的 ηε-joint schema 预注册 → 首建合并（ε 观测表 ∪ ThermoML-η ∪ Schrödinger 子集，全带 provenance）。
- **仍未做**：T1 在线黏度切片核查；T3 的 5 条同一 InChIKey 下的画法差异人工决定是否改写本地 SMILES；ηε-joint 联合观测表**尚未新建**（本仓只有 Week 3 的 loose-join 探索表 `dielectric_viscosity_intersection.csv`，456 行 / 46 keys / `model_ready=false`）。
- **训练方向（不许忘记）**：ηε-joint 建模须继承 v1.x 诚实口径——**观测级 + GroupKFold by InChIKey + 每折训练侧排序**，并断言 `group_overlap == 0`（黏度线已交学费：`random_row` 0.93689 vs `group_key` 0.74813）；`random_row` 只作泄漏参照、从不进判决。

### AC-8 冻结红线复核（本附录落盘时实测）

- `data/dielectric_v03.csv` = `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`（**INTACT**）
- `data/processed/dielectric_observations_v11plus.csv` = `159b928f800a55969963da275ed05c30ce8a19cffc48353a9c490eec68a49af9`（**INTACT**）
- `probes/l3_stage1_pilot_pool.csv`、`probes/l3_backvalidation_prereg.json`、`probes/l3_stage1_pilot_summary.json` **均 INTACT**；七个锁定常量一个字未动；`data/viscosity_v01.csv` 与 `data/external/*` 零改动。

## 附录 AD：Week 16 开局 —— 杠杆 9 勘误轮、ηε 联表首建与 Reaxys 渲染缺口闭合（2026-09-26）

> 命名说明：紧随附录 AC 之后取 **AD**。范围 = AC-7 登记的「Week 16 首位技术债」清偿，加上用户点名要求的 Reaxys 实做。机读台账见 `reports/decisions_log.md` **§25**。本轮**不动笔（不写论文）**、不开新主线、不碰冻结件。

### AD-1 三臂并行与验收

| 臂 | 任务 | 交付（新增） | 验收 |
|---|---|---|---|
| A | 杠杆 9 **勘误轮**（AC-6 的 P0 技术债） | `probes/dielectric_knowledge_purity_sweep_erratum.py`＋`_prereg.json`＋`_summary.json`＋6 份 artifacts CSV＋报告＋测试（11 件） | `--check` 24/24；`14 passed`；ruff 绿 |
| B | 观测级 **ηε 联表**首建（AC-7 第二项） | `probes/build_eta_epsilon_joint_table.py`＋verifier＋schema 预注册＋summary＋两张 `data/processed/eta_epsilon_joint_*.csv`＋报告＋测试（8 件） | 8,359 行；`group_overlap=0`；测试绿 |
| C | **Reaxys 渲染缺口闭合**（用户点名） | `probes/reaxys_render_gap_closure.csv`＋summary＋verifier＋报告＋测试（5 件） | verifier 85 项检查全过；`22 passed` |

另两条并行线出料：`probes/kpi_shortlist_extraction.py`（Gao 2025 两幅图共 29 行短名单 → `data/reference/kpi_15_14_shortlists.csv`）与 `probes/pubchem_liquid_window_harvest.py`（314 键液相窗口 M/B/F 收割）。两者都不产判决，只产候选料。**披露（M-6）**：`data/reference/kpi_15_14_shortlists.csv` 的 29 行**全部自带 `redistributable=false` / `usage=cross_check_only`**（逐字转录已发表 SI 的图 S20/S21，汇编级证据），随仓库分发，**只作交叉核对，不得当数据集再用**。

### AD-2 杠杆 9 勘误轮：AC-6 的技术债已清，判决未变

- 预注册 `2026-09-26T07:24:48Z` 锁定、`shots_registered_up_front = 4`（k = 2/4/6/10）；判据**照抄 v1**（pass +0.0200 / kill +0.005 / 正向重复 ≥ 8/10 / 安慰剂容差 0.02），**未放宽**。
- 同 50 折（`signature_sha256 = 864b3a53…86be`，与 AC-6 一致）三基线**逐位**复现：Morgan `0.06487386371009436`、Morgan+Physical `0.4091179943351143`、Physical `0.2531659995294713`，`abs_difference = 0.0`。
- **修正读数（修正重要度列序）**：k2 `−0.005136434` / k4 `+0.005201058` / k6 `+0.004912652` / k10 `+0.015746812`，正向重复 5 / 4 / 6 / 7。
- **判决 `sub_threshold`（与 v1 同判）**：k=10 过 kill 线（+0.005）但未过 pass 线（+0.0200）；`carried_into_the_merge_arm = false`。
- 曲线 `edge_peak_high_k`、无内点峰 → 论文「知识越多精度越低」的**下降支在冻结网格内未被复现**；但 k=10 已是全池，**不能排除网格外的峰**。
- 安慰剂塌缩：地板 R² `−0.0063523871448647904`、安慰剂 `−0.054562963693843815`、超地板 `−0.04821057654897903`；管线内 |增量| `0.00869829255732573` < 0.02。**预注册没有为「塌缩增量」指定参照**，故同时报「地板」与「真标签基线」两种读法。
- 缺陷复现 50/50 折、`worst_max_abs_score_difference = 0.0`；修正排序的标签-列绑定 3/3 折、`worst_max_abs_difference = 0.0`。
- v1 五件套 digest 逐位未变（`version_1_reading_not_rewritten`）——**v1 读数未改写、未就地重算**。判决未变**不等于**缺陷无害：勘误照样上报。

### AD-3 【必须记住】AC-6 / §24.6 / §24.9 的 k=10 标签写错

- 这三处把 `+0.008666009048` 标成「**修正（正确）列序**下的 k=10 读数」。**这个标签是错的。**
- 实测：`+0.008666009048190704` 是**预注册池序**读数（与重审引用的 `+0.008666` **12 位小数吻合（= 10 位有效数字）**，`k10_exact_difference = 1.9070335588455833e-13` —— 相对差，**不是逐位相等**）；**修正重要度列序**下的 k=10 是 `+0.015746812033317625`。
- **原文逐字保留、不回改**，依据是项目既有规则「**已落盘读数不被就地改写**」，更正以并列方式追加；守卫只做关键串**存在性**检查，**不是不回改的理由**。更正**只在本附录与 §25 给**。
- 三序并列：v1 破损序 `+0.014709978` / 预注册池序 `+0.008666009` / 修正重要度序 `+0.015746812`（spread `0.007080803`）；**三序全部低于 +0.0200**，判决仍 `sub_threshold`。口径是**更正一个标签，不是重开一个问题**。

### AD-4 ηε 联表首建（观测级）

- 8,359 行观测 / 1,043 个 InChIKey；ε 2,065 行、η 6,294 行；纯组分 6,293 / 混合物 2,066。
- `publishable_core` **8,196 行 / 1,037 键**（`filter_only` 163 行按 `redistributable = false` 单列）。
- 来源四分：ε 观测表 2,065（冻结件）、ThermoML-η 2,549（源 2,725 行，176 行运动黏度排除）、Schrödinger 开放子集 3,582（冻结件）、PubChem 液相窗口 163（源 11,910 行）。
- **冲突不平均**：`(inchikey, property, T_K)` 多值的键 304 个（全表）/ 283 个（纯核内），**原值保留、`averaging_applied = false`**。
- **排除留痕** 11,977 条；「行数缩水而无排除记录」被定义为缺陷（`source_rows_uncovered = 0`）。
- **评估口径前置写死**：`GroupKFold by InChIKey`、5 折、`publishable_core ∧ pure`（6,130 行 / 1,032 组）、**每折断言 `group_overlap == 0`**。同轮对照 **random_row 泄漏比例 0.906199**（只作泄漏参照，**永不进判决**）—— AC-7 的「训练方向」那条由此落成机器断言。
- 本轮**不拟合任何模型**（`verdict_derived_this_round = none`），不花 R² 配额。

### AD-5 Reaxys 渲染缺口闭合（用户点名：把已登录的 Reaxys 用起来）

- **路线与合规**：Edge + 用户已登录的 Reaxys 会话，**手动逐条**查询；无爬虫、无批量导出、无自动遍历。产物是**离线转录镜像**（`network_calls_made_by_this_artifact = 0`）。
- **核心 UI 发现（方法学）**：Reaxys 属性表（`Physical Data > Dielectric Constant`）**未点表上方「Show all」时只渲染前 M 行**；**「声明数 > 渲染数」是 UI 折叠，不是数据缺失**。这一条同时解释了上一轮登记的两条「未读到的行未闭合」。
- **PC（碳酸丙烯酯，CAS 108-32-7）**：声明 10 / 未点渲染 7 / 点后 10。新读到第 8 行 `64 @ 2E+06 Hz @ 30 °C`、第 9 行 `64.4 @ 2E+06 Hz @ 25 °C`（Ritzoulis 1989, *Can. J. Chem.* 67, 1105-1108）、第 10 行**无数值引用存根** → 与第 6/7 行合为 **2 MHz 上 20/25/30/35 °C 的 ε(T) 序列**（**只是线索**：受限、只到题录一级）。
- **tetraglyme（四乙二醇二甲醚，CAS 143-24-8）**：声明 8 / 未点渲染 7 / 点后 8；第 8 行六列全空（Ugelstad 1965 + Graczyk 1978 的**引用存根**）→ 上一轮猜测「缺的那条疑为 **39.99 °C = 313.14 K**」**被证伪**，不得再当事实引用。
- **同线另两轮（已完成，一并留档）**：伸到 FEC / VC / GVL / DME / sulfolane / MOPN —— **MOPN 三级否定**（物质层 103 条 / 24 类无介电类别、属性检索 0 条、文献层 112 篇无值）→ Reaxys 侧关闭，唯一电学量是偶极矩 4.04 D；**sulfolane** 8 点与本地 Vahidi 2013 逐点一致（再确认，非新增）；**GVL** 36.9（Segato 2021）vs 36.1（iScience 2026）冲突待判、本地 0 行 → v1.x 第一优先缺口；**FEC** 仅 1 条、无 107 腿。
- **反面证据（重要）**：EC 的 `89.78` 在 Reaxys 被标 **25 °C**，本仓溯源记 **40 °C = 313.15 K**，且 EC 熔点 36.4 °C、25 °C 本就不是液态 → **Reaxys 温度栏会错标**，引用其温度必须与本地溯源比对。
- **纪律**：`restricted_crosscheck_only`、**永不进 `data/`、永不进任何池**；Reaxys 不给 DOI，provenance 只到**题录一级**；**不构成通道可用性声明**。

### AD-6 AL Round 4 二次重算与 Week 15 交付包补齐

- `local_trace_files` 是**磁盘状态的函数**：新增 `data/processed/eta_epsilon_joint_*.csv` 与 `data/reference/kpi_15_14_shortlists.csv` 后按生成器重跑，**128 → 146**（`by_row_kind` 未变 1/12/7/1）。正解 `git ls-files` 未被采纳，缺陷登记为待办。
- **Week 15 首次有导出器**：新建 `probes/export_week15_results.py`（733 行，T1–T5 五通道 + 守卫快照 + AL4 读段，28 件产物）；`scripts/verify_export_manifests.py` 的 `LATEST_WEEK` **14 → 15**（原默认 range 会静默跳过 week11–15 并照样报成功）；实跑 week1–week15 **全 [PASS]**。
- 包内 `verification.json` **4/4** verifier 退 0；冻结红线扩到 **6 条** 全 INTACT；T5 在导出时**逐位复现** `0.4091179943351143`；`shots.main_scoreboard_attempts = 0`。
- **已知文案漂移（登记不只修）**：包内 `README.md` 正文仍写「114 → 128」，而机器字段已是 **146** —— 已登记，下次导出统一。

### AD-7 训练方向与下一步（不许忘记）

- **训练方向**：ηε-Joint 建模继承 v1.x 诚实口径 —— **观测级 + GroupKFold by InChIKey + 每折训练侧排序**，断言 `group_overlap == 0`；`random_row` 只作泄漏参照、**从不进判决**（黏度线的学费：`log10_cP` 的 **MAE 0.064 vs 0.175**；R² 口径为 **0.93689 vs 0.74813** —— **这对数字是 MAE 不是 R²**，本手册此前已登记过该笔误）。**温度维度已就绪**（`T_K` 特征已在管线里，无需新增）。
- **v1.x 第一刀（零新网站）**：打开本地 242 个 ThermoML XML 的**温度闸门**重抽 ε(T)（入库时按 293–303 K 窗口过滤掉了大量序列点）→ 预计 1,000–2,500 行观测。
- **Week 16 余项**：① KPI 15+14 漏斗交叉试跑（`data/reference/kpi_15_14_shortlists.csv` 已就位）；② Uni-Mol 探针规格定稿（缓冲项）；③ Reaxys 侧待办只剩**全文阅读**，不再是 Reaxys 待办。
- **等待期纪律**：审稿意见回来前只跑本附录与 §25 登记的内容，不开新主线。

### AD-8 冻结红线复核

- 六件 digest 逐位未变：`data/dielectric_v03.csv` `ff2142936e…35ccce4`、`probes/l3_stage1_pilot_pool.csv` `b838febb…`、`probes/l3_backvalidation_prereg.json` `77f61a83…`、`data/processed/dielectric_observations_v11plus.csv` `159b928f80…68a49af9`、`probes/dielectric_r2_levers_prereg.json` `ab3503c0…`、`data/viscosity_v01.csv` `12dfa03f…1c5b26`。
- **本轮** Reaxys 产物未进 `data/`、也未进任何交付包；**但既有例外要照实登记（I-1）**：week12 / week13 交付包里**已经**装运过 Reaxys 受限镜像（`成果输出/week12/reaxys_dielectric_queue_first_cut.csv`、`成果输出/week13/reaxys_v1x_stocking_scan_summary.json`），按原口径**禁止再分发**。Schrödinger 受限 **858** 条未被绕取（`withheld_points = 858`、`supp_3_rows_merged_into_experimental_table = 0`）。

## 附录 AE：Week 16 收官 —— KPI 29 行 × 本仓漏斗交叉试跑、Uni-Mol 规格就位（2026-09-26）

> 命名说明：紧随附录 AD 之后取 **AE**。本附录**不动笔（不写论文）**、不拟合模型、不产任何 R2、不碰冻结件。范围 = 附录 AD-7 登记的 **Week 16 余项 ① 与 ②** 的清偿。机读台账见 `reports/decisions_log.md` **§26**。**AD 原文不回改**，清偿只在本附录声明。

### AE-1 两条臂与验收（本附录落盘时实测）

| 臂 | 任务 | 交付（新增） | 验收 |
|---|---|---|---|
| D8 | KPI 15+14 短清单 × **本仓漏斗**跨池交叉试跑 | `probes/kpi_funnel_cross_run.py` ＋ 预注册 `_prereg.json` ＋ 身份表 `data/reference/kpi_shortlist_identity.csv` ＋ `_summary.json` ＋ 报告 ＋ 测试（6 件） | `--check` 绿（离线逐字节复现）；**26 passed**；ruff 绿 |
| U | **Uni-Mol 探针规格**定稿（只定规格） | `probes/unimol_probe_spec_prereg.json` ＋ `reports/unimol_probe_spec.md` ＋ 测试 ＋ `probes/verify_unimol_probe_spec.py`（4 件） | verifier `checks=34 passed=34 failed=0`；**22 passed**；ruff 绿；变异测试可红可还原（含摘要钉等式断言） |

**披露（既有产物改动）**：本轮的**指定既有写集**为 `reports/decisions_log.md`（§26）与 `tests/fixtures/manual_appendix_j_snapshot.md`（由 `probes/manual_appendix_reconciliation.py --write-manual-fixture` 从本手册重生；本手册本身在仓库外）；除此之外，新增身份表之后，**AL Round 4 的 `local_trace_files` 是磁盘状态的函数**（`probes/al_round4_new_compound_backfill.py:651` 递归扫 `data/`）。新增 `data/reference/kpi_shortlist_identity.csv` 后必须**按生成器原样重跑**，否则 `tests/test_al_round4_new_compound_backfill.py::test_list_csv_equals_the_generator` 变红。重跑后实测：仅碳酸丙烯酯（`RUOJZAUFBMNUDX-UHFFFAOYSA-N`）那行新增两个 trace token，**无删除、无其它行变动**；summary 除 `generated_at` 外逐字未变；该测试文件 **80 passed**。

> **这是本项目的一条常设操作纪律**：任何往 `data/` 树下新增 `.csv/.json/` 等被扫后缀的文件之后，都要重跑 AL Round 4 生成器并把它写进当轮台账，否则测试会红，或者更糟——清单静默过期。

### AE-2 D8 交叉试跑：怎么做、判据、结果

**怎么跑**（本仓 PowerShell，注意脚本已自举 `sys.path`，无需设 `PYTHONPATH`；联网时须清代理）：

    .\.venv\Scripts\python.exe probes\kpi_funnel_cross_run.py --resolve-online   # 首跑：解析 15 条 CAS
    .\.venv\Scripts\python.exe probes\kpi_funnel_cross_run.py                    # 增量：缓存里有的不再联网
    .\.venv\Scripts\python.exe probes\kpi_funnel_cross_run.py --check            # 离线重跑并与磁盘产物比对

**先冻结再跑**：预注册 `2026-09-26T09:11:42Z` 锁定（`status = locked_before_run`，sha256 `42e3fa658d90…6a12ee`）。三条判据与 7 条 `forbidden` 跑后**未回填、未放宽**；S4 在跑前就写死为 `registered_as = gap`。

| 判据 | 内容 | 结果 |
|---|---|---|
| A 自洽 | 29 行全部满足 S1 结构过滤与三阈值（MP<230K / BP>430K / FP>360K），允许违反数 = 0 | **通过**，0/29 |
| B 身份 | 29/29 解析出 InChIKey（14 行 SMILES→RDKit，15 行 CAS→PubChem） | **达成**，29/29，未解析为空 |
| C 交集 | 与 Batt-P30K / 314 键名册 / 冻结 ε v0.3 / v1.x 观测表 | **13 / 2 / 2 / 1** |

**本仓漏斗 S0–S3 实测**（池 = Batt-P30K，声明 29,519、实测读入 29,519、SMILES 不可解析 0）：

| 阶段 | 规则 | 存活 | 本级剔除 | 对池存活率 |
|---|---|---|---|---|
| S0 | 池内全部 | 29,519 | 0 | 1.000000 |
| S1 | KPI 结构过滤（`[OX2H]` / `[CX3](=O)[OX2H1]`、Molwt<600、重原子<30） | 29,519 | **0** | 1.000000 |
| S2 | 本仓危险官能团（16 条 `HAZARD_SMARTS`，单一真源 `probes/al_round1.py:57`） | 22,249 | 7,270 | 0.753718 |
| S3 | 元素白名单（**导出值**，标 `derived_not_declared`） | 11,709 | 10,540 | 0.396660 |
| S4 | MP/BP/FP 三阈值 | **不跑** | 不跑 | 不跑 |

- **S2 逐因**：`aldehyde 1885` / `epoxide 729` / `acyl_halide 714` / `thiocarbonyl 713` / `nitro 559` / `peroxide 547` / `s_x_bond 531` / `alpha_halo_ether 463` / `p_x_bond 382` / `n_x_bond 372` / `sulfonyl_halide 325` / `halogen_oxygen 323` / `isocyanate 222` / `s_s_bond 219` / `azide 4`。各因之和 7,988 **大于**本级剔除 7,270 —— 因为一个分子可同时命中多条 SMARTS，排除取**并集**。
- **S3 逐因**：`F 3206` / `S 2836` / `Cl 1770` / `P 1100` 及组合（`Cl+S 319` / `Cl+F 309` / `P+S 185` / `F+P 117` / `Cl+P 65` / `Cl+F+S 24` / `F+P+S 8` / `Cl+P+S 6` / `Cl+F+P 2`）。逐因之和**恰好** 10,540。

**身份层可离线复现的机制**：CAS 行的值一旦落进已提交的 `kpi_shortlist_identity.csv`，离线模式就**直接采用该表的取值**（零网络），因此干净克隆上 `--check` 复现身份层与全部判据；但**属性交叉核对**要读 `data/external/g1plus/` 下的 PubChem 缓存，该目录被忽略，干净克隆上那一节会照实记 `available = false`。**硬守卫**：重解与已提交表在 InChIKey 上不一致时，脚本**拒绝写盘并退出码 2**（除非显式 `--refresh-identity`）。 **闭环说明（审读 I-3）**：离线复现对 15 条 CAS 行是**闭环自证**（离线直接从被校验的那张表读数）；这 15 行的正确性由首跑活库取数 ＋ 审读轮独立活库重查（15/15 MATCH）共同担保，`--check` 本身不重证它们。

### AE-3 本轮三条反直觉发现（照实读数，不是结论）

1. **S1 在电池分子池上零剔除**：29,519 个分子一个都没被 KPI 的结构过滤剔掉。电池分子池本来就没有游离 -OH/-COOH，重原子 < 30、Molwt < 600 也天然成立 → **S1 是一条对「为电池而生的池」完全不咬合的闸门**。教训：**不要指望结构过滤在这种池上体现筛选力**，要比较就比 S2/S3 这种真在咬合的级。
2. **导出的白名单比 KPI 声明的更严**：29 行解析出的元素并集只有 **C / N / O（3 种）**，而 KPI 正文声明 **11 种元素**且不给清单。所以 S3 用的是**导出值**、且**比声明值更严** → **S3 存活数 11,709 只能当下界读，不是我方规则的复现**。summary 与报告都已标 `derived_not_declared`。
3. **KPI 印刷 MP/BP/FP ≈ 本仓独立取的 PubChem 汇编值**：只在名册覆盖到的行上比，共 **6 组**（GBL `96-48-0` 与 PC `108-32-7` 各 M/B/F），|Δ| 中位数 **0.05 K**、最大 **1.42 K**（GBL 熔点 228.2 vs HSDB 229.62）。**口径**：KPI 侧是**论文模型的预测值**，本仓侧是**实验汇编值** —— 「别人的预测 vs 我们的实验汇编」的旁证，**不是两个实验源之间的比对**；0.05 K 那一档基本就是 °C→K 的四舍五入残差。

另：**13 个命中分子逐个带 Batt-P30K 自带 DFT 标签**（`dipole_norm` / `homo` / `lumo` / `gap` / `ip` / `ea`），本轮**只照抄、未用于训练或评分**。PC（`RUOJZAUFBMNUDX-UHFFFAOYSA-N`）与 GBL（`YEJRWHAVMIAJKC-UHFFFAOYSA-N`）同时落在 314 键名册与冻结 ε v0.3 表里。

### AE-4 Uni-Mol 规格就位（只到「备料」为止）

- 验收（审读修复后复跑）：`probes/verify_unimol_probe_spec.py --check` → `checks=34 passed=34 failed=0`；`tests/test_unimol_probe_spec.py` **22 passed**；ruff 绿。**变异测试**（临时把 KPI 超参 `batch_size` 的 32 改成 33）：**首跑记录有误**，原记「测试 3 failed、verifier failed=1」，**实为 2 failed / 18 passed**，verifier `failed=1 (kpi_hyperparameter_provenance)`；当时 `test_spec_digest_is_pinned_in_the_report` **是 PASSED** —— 报告正文自己印了变异 sha，弱断言被自身满足，该钉对「被文档化的那次变异」等于永久失效。**根因已修**（改等式断言：报告头部声明的 sha == 盘上规格 sha）。**本轮复跑**：`pytest` **3 failed / 19 passed**、verifier `checks=34 passed=32 failed=2`（`kpi_hyperparameter_provenance` ＋ `report_declares_spec_digest`）、变异态 sha256 `5234f7972c86…3d5589`；还原后 `byte_identical = true`、sha256 回到 `40ba1d6f2c89…132857`，两处重新全绿。即规格是**被钉住的**，不是一纸散文。
- **规格查证到的仓库事实**：xTB 构象产物**不在耐久产物里** —— 冻结单构象 `data/interim/xtb_features`（246 目录 / 250 个 `input.xyz`）、新增 42 化合物 `data/interim/xtb_features_v11plus`、**唯一多构象集合** `data/interim/xtb_conformer_migration`（276 目录 / 2198 个 `input.xyz`，`MAX_CONFORMERS = 8`）；三者都在 `.gitignore` 之下（**不可分发**）；全仓**无 .sdf/.lmdb/.pkl**（排除口径 = `.git` ＋**全部虚拟环境目录**；本轮实测非虚拟环境内三者均为 0，虚拟环境内合计 `.pkl` 23（`.venv` 11 + `.venv-chemprop` 12）、`.sdf` 9（`.venv` 4 + `.venv-chemprop` 5），属 vendor 命中）。
- **「236 样本」= 哪张表，已核实**：`probes/l3_stage1_pilot_pool.csv`（236 行）与 `data/dielectric_v03.csv` 的 `model_ready = true` 240 行减 4 个多片段 xTB 特征失败行 = 236；**集合相等、对称差 = 0**。
- **照实登记、不静默调和**：① **「11 构象」vs「RDKit 10 构象」**（Y-1 / D7 与 AA-3 互相矛盾）→ 并列登记、`status = unresolved`、`no_silent_resolution = true`，「10 RDKit + 1 xTB = 11」只作**未证实**的算术解释；② **D7 枪毙线没给比较算子**。
- **能力缺口照实写「待建」**：`torch`、`unimol`、`lmdb` **均未安装**，Uni-Mol 预训练权重与运行时**未获取**。**不许把规格当作已有环境**。

### AE-5 训练方向与等待期纪律（不许忘记）

- **D8 不是评测**：本轮**不拟合任何模型、不产任何判决性 R2**（`fitted_any_model = false`、`r2_reported = false`，7 条 `forbidden` 逐条 `false`）。
- **若要真用这 13 个做迁移**（v2.0 候选）：必须走**观测级 + `GroupKFold by InChIKey`**、断言 `group_overlap == 0`；`random_row` **只作泄漏参照、从不进判决**。温度维度已就绪（`T_K` 特征已在管线里，**无需新增**）。
- **主记分牌口径隔离照旧**：`0.4091179943351143`（457 行 / 97 化合物）与 v1.0 headline `0.364` **不得混用**；`0.5332` / `0.5454` 只许带池定义引用。黏度线的学费照旧引用为 **MAE**（`log10_cP` 0.064 vs 0.175；R² 口径 0.93689 vs 0.74813）。
- **短期不新开主线**：v1.x 温度表与 ILThermo 线仍是「已登记未启动」；Uni-Mol 与 MD 只到「规格就位」，**环境与权重留到 v2.0 正式启动时再建**。**不开新主线**这条在投稿等待期内继续生效。

### AE-6 冻结红线复核（本附录落盘时实测）

- 六件 digest 逐位未变：`data/dielectric_v03.csv` `ff2142936e…35ccce4`、`probes/l3_stage1_pilot_pool.csv` `b838febbca4d…408b18`、`probes/l3_backvalidation_prereg.json` `77f61a83b82d…f0db98`、`data/processed/dielectric_observations_v11plus.csv` `159b928f800a…a49af9`、`probes/dielectric_r2_levers_prereg.json` `ab3503c037f0…c1bdaa`、`data/viscosity_v01.csv` `12dfa03f3428…1c5b26`。`probes/l3_stage1_pilot_summary.json`、七个锁定常量、`data/external/*` **除本轮新增的 `pubchem/kpi_shortlist_identity/` 缓存目录（30 个文件，被 `.gitignore:150` 忽略、不进版本库）外**零改动。
- **短清单边界不变**：`data/reference/kpi_15_14_shortlists.csv` 的 29 行仍是 `cross_check_only` / `redistributable = false`（汇编级证据），随仓库分发但**只作交叉核对**。新增的 `data/reference/kpi_shortlist_identity.csv` **只装结构身份**（PubChem 侧公有领域），**不含论文印刷的 MP/BP/FP**、不含任何 Reaxys 值，也不参与特征构造、训练或评分。
- **Reaxys 与 Schrödinger 红线未触碰**：本轮**零 Reaxys 访问**；week12 / week13 交付包内已装运的 Reaxys 受限镜像（**禁止再分发**）**未新增、未扩散**；Schrödinger 受限 **858** 条未被绕取（`withheld_points = 858`）。
- 本轮新增产物全部落在 `probes/`、`reports/`、`tests/`、`data/reference/` 四处，**未进任何交付包**。

### AE-7 独立对抗审读与修复（同一轮；审读者 = 另一智能体，独立复算）

- **审读方式（不许读结论）**：审读者从磁盘独立重算 digest、独立重跑 `--check`（含「把 `socket`/`urlopen` 全 monkeypatch 成抛异常后仍退出 0 且逐字节复现三件产物」）、独立重跑变异测试并还原、独立复算黏度线 MAE/R²、独立比对 `probes/l3_stage1_pilot_pool.csv` 与 `data/dielectric_v03.csv` 的 `model_ready` 集合（对称差 0）、独立清点 xTB 三处目录计数、独立扫描 `成果输出/` 是否混入本轮产物（零命中）。
- **D8 主线：0 Critical** —— P1–P8、AL Round 4 联动、变异测试、六件冻结件 digest 全部独立复算站得住。
- **已修 6 条**：**C-1**（U 臂把 R² 写成 MAE、预注册「逐字引用」实为拼接）→ 改为带盘上出处的 `MAE 0.064 vs 0.175、R² 0.93689 vs 0.74813`，预注册引文拆成两条真逐字并登记 `corrections_before_first_commit`；**I-1**（摘要钉弱断言 → 等式断言，见 AE-4）；**M-1**（「唯一被改动的既有产物」措辞过宽 → 改为「指定既有写集」，见 AE-1）；**M-2**（身份表 `notes` 自述与同表列冲突 → 改成「`source_url` / `retrieved_at` 即本行取数凭据」）；**M-3**（「无 .sdf/.lmdb/.pkl」补排除口径，见 AE-4）；**I-2**（`data/external/*` 并非零改动 → 按实况改写，见 AE-6）。
- **登记说明 1 条**：**I-3**（CAS 行离线复现是闭环自证）→ 已在 AE-2 补写担保来源。
- **登记不修 1 条**：**M-4**（15 条 CAS 行落的是无立体层 InChIKey，交集是**立体盲的**；本轮无实害，留作 v1.x 复权时的已知限制）。
- **审读者无法独立复核的 2 项（负命题，照实写「不可复核」）**：① 「本轮零 Reaxys 访问」无网络审计日志，只能间接支持（新增/改动文件里 `reaxys` 零命中、`成果输出/` 无新增 Reaxys 物）；② 首跑 15 次 PubChem 取数不可回放，但**取值**已被逐行活库重查证实（15/15 MATCH）。

- **第二轮复核（只核修复，独立实测）**：请求的 7 项**全部通过、0 Critical**。新增 1 条 Minor（**M-a**：AE-4 把 `.pkl/.sdf` 的**目录归属**写错，聚合数 23/9 对但归属错 → 已按实测改写为 「`.pkl` 23 = `.venv` 11 + `.venv-chemprop` 12、`.sdf` 9 = `.venv` 4 + `.venv-chemprop` 5」）与 1 条 Important（**I-a**：审读窗口内台账被本轮写入，文件是**移动靶** → 流程登记：提交前以**冻结副本**复算全部 pin；审读者自己的全量跑为 **2435 passed / 817.64 s**，与本节 783.65 s 的差异只是机器负载）。

> **纪律价值**：这轮审读打红的全是**「口径/措辞/自证强度」**，没有一条是数值造假 —— 但其中 I-1 是**真缺陷**（弱断言使摘要钉永久失效），若不复核就会带着「钉住了」的错觉进 v2.0。教训：**凡「我钉住了 X」的断言，都必须让 X 变化时该断言真的变红**（本例即变异测试要打到钉本身）。
