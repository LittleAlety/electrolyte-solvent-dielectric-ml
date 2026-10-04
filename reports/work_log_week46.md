# 工作日志 · Week 46（还原轴描述符重定义、同装置锚点侦察、τ_b 功效工具化与论文回填）

> 承接 `reports/work_log_week45.md`。本轮起点：W45 交付（HEAD `04b27e3`，工作树 182 项）；收口时工作树 217 项。本轮 0 shot，累计仍 19；四个冻结读数一个不动。

## Week 46：把「还原轴需要重新定义」拆成可执行的三问

**目标**：W45 把偏置的形状算清了，但论文仍停在「还原轴需要重新定义」这句话上——没回答「怎么定义、锚点够不够、现行样本量能分辨多大的 τ」。W46 把它拆成四条并行 lane：**A** 预设候选描述符族的比较、**B** 同装置还原锚点的侦察与准入、**C** τ_b 功效分析工具化、**D** 论文回填与治理同步。

**交付**

- **预注册**：`probes/w46_taub_power_prereg.json`、`w46_reduction_anchor_recon_prereg.json`、`w46_reduction_family_prereg.json`、`w46_paper_governance_prereg.json`（均 `locked_before_run`）。Lane C 的 r2->r3 把 H46c9 的**期望值**补进判据（旧 0.5 猜测存 `revision_history`）；Lane B 的 r2->r3 补 `offline_references`（FEC/VC/EC 离盘参照登记）。所有判据在生产运行前冻结。
- **W46-A 候选描述符族**（8/8 成立）：预注册锁死 D0 裸 LUMO / D1 门禁过滤绝热 EA / D2 Li⁺ 耦合还原位移 / D3 溶剂化垂直 EA，放进（候选 × 层）网格。r2SCAN-3c 层 D0 可用 28、D1 门禁合法 **0**、D3 合法 **2 < 5** ⇒ 判**不可判定**；D2 无 r2SCAN-3c 原料；GFN2 合法气相子集 n = 48 上方向性 τ_b：D0–D1 **0.7393617021276596**（未解析 0.3980496453900709）/ D0–D2 **−0.3794326241134752**（0.8696808510638298）/ D1–D2 **−0.448581560283688**（0.8874113475177305）。主判据按 H46a2 不执行，**主判据 = 不可判定**。
- **W46-B 锚点侦察与准入**（10/10 成立）：扫 `data/`、`reports/`、`probes/`、`docs/` 共 **518** 个 CSV，候选列 **151** + 命名对照 **32**，台账 **190** 行；计算系列一律 `rejected_computed_only`（**181** 行）、介电锚点 `rejected_criterion_mismatch`（2 件）、离盘参照 `not_available_on_disk`（1 件）；层准入六层仅 PubChemQC 过闸。**n_anchors = 0、n_pairs_effective = 0、拒答分支触发。**产出表（候选/台账）的行数与 sha256 在 summary 的 `table_pins` 钉住，由 `test_anchor_tables_pinned_readonly` 复算复核。
- **W46-C 功效工具化**（10/10 成立）：`tools/taub_power.py`（只读）。n = 7 MDE **0.6540558963871848**；功效 0.4/0.6/0.8 = **0.23002645502645513 / 0.6298992673992675 / 1.0**；过 0.9 阈概率 **0.004365… / 0.0114335… / 0.0809027777777778**；n_min **17 / 8 / 6**；离散 α_eff(7) **0.034523809523809526**；连续化 MC **0.05015**；与 W33 精确零分布逐点一致（max_abs_delta **0.0**）；观测 τ_b 0.4285714285714286 的精确单侧 p = **602/5040**。
- **W46-D 论文与治理**（8/8 成立）：引用 7/7 在位；§1.2 T1/T2 定位段 + Gate 1 三处措辞修订在位；**§3.31** 落地；`decisions_log.md` §28.101；README §11 第 45–48 条；守卫复跑 refused 3 / mut 0 / writes 0 / shots 19 / negatives 9。
- **测试与集成**：`tests/test_w46_*.py`（6+7+7+7 = **27 项**）全绿；论文 v3 -> v1.10 新增 §3.31；README §0/§5/§7/§8/§11；导出脚本 `probes/export_week46_results.py`。

**结果与验收**

- **判据**：36 条（A 8 / B 10 / C 10 / D 8）**全部成立、0 判否**；四条探针连跑两遍，`git status --porcelain` 脏路径集**逐项稳定**。
- **测试**：`tests/test_w46_*.py`（26 项）加 `test_repo_hygiene.py` / `test_w38_data_recon.py` / `test_w37_gate_admission_export.py` 子集共 **46 passed**。
- **治理校验**：`scripts/verify_four_core_registry.py --check` 全 PASS；`scripts/check_paper_artifact_consistency.py` 打印 `paper drafts agree with the frozen artifacts`；`scripts/verify_paper_figures.py` PASS。
- **论文与渲染**：v3 头部升到 **v1.10**、证据范围 week21–week46、新增 §3.31（图 21 = taub_power、图 22 = reduction_family）；`paper/make_paper_v3_docx.py` 重渲染 **373 段 / 9 表 / 25 图**，25 张图全部以真实字节嵌入（合计 4.7 MB，最小 56 KB，无过小图）。
- **导出**：`probes/export_week46_results.py` -> `成果输出/week46`，`verification_passed=true`、`lanes_missing=[]`、`frozen_red_lines_intact=true`。

**坑与更正**

- **Lane B 的扫描分母含探针自己的产物**：它扫仓内 `data/reports/probes/docs` 下的全部 CSV，因此随本轮产物写齐，分母从首跑的 **515** 涨到 **518**（命名对照 30 -> 32、computed_only 179 -> 181）。所有文档（论文 §3.31、README §11、decisions_log、立项章、交付说明）统一按**产物齐备后**的 518/32/181 校准，并复跑确认分母连续两遍逐位一致。
- **论文标题被粘连**：§3.31 的小节标题一度被接在 W45 段落末尾（同一行），Markdown/docx 会渲染成普通正文而非小节标题；已拆回独立行，并全仓扫描确认无第二处行内标题。
- **导出后治理快照会变**：`成果输出/week46` 出现后，Lane D 的逐轮验收 42 -> **43** 轮、AST 静态守卫 365 -> **370** 文件（新增导出器本体 + W46 探针/工具/测试）；所有文档数字统一按「导出后复跑」的读数校准，再二次导出，避免包里留下过程读数。
- **Lane C 两处口径**：① 报告键名首版写成 `observed_p_upper`，与 W33 的 `p_upper()` 函数口径不一致，改为 `observed_exact_p_upper`；② H46c2 必须用 W33 的 `p_upper()` 函数（而不是 `p_value_table` 的 CDF 字段）才算逐点一致。两处均已在预注册修订史留痕，未改判据。
- **不需要新目录**：本轮 4 条 lane 都复用 `probes/w42_common.py`，未新建 `w46_common.py`；新增的唯一顶层件是只读工具 `tools/taub_power.py`。

**下一步（已登记）**

- 见 README §11 第 45–48 条：① D2 的 r2SCAN-3c 版本与 D3（ddCOSMO 溶剂化垂直 EA）需**新 ORCA 单点**，转下周期；② 主判据要执行，须先把同装置还原锚点从 0 补到 ≥ 5（含 Li⁺ 支持电解质、同判据）；③ `dipole_transfer_v1` 维持 `registered_not_authorized`，修数未授权；④ strict same_level 外部源仍为 0。
- 仍未闭合：要给 HOMO/LUMO 通道加权，仍须补一个 **strict same-level 独立源**；PubChemQC 入口（先 InChIKey->CID 再按分片定位）仍未执行。
