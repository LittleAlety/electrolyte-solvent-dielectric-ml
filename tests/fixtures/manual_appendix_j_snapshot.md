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
