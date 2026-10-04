# 工作日志 · Week 45（标定列泄漏审计、扩展层分层残差、偶极偏置分层归因与三条守卫复跑）

> 承接 `reports/work_log_week44.md`。本轮起点：W44 交付（HEAD `04b27e3`，工作树 178 项）；收口时工作树 182 项。本轮 0 shot，累计仍 19；四个冻结读数一个不动。

## Week 45：把三个「一个数」拆成分层表

**目标**：审计 W43 遗留的标定列 `calib_homo_eV` / `calib_lumo_eV`；把 4668 行 xTB–Batt 分层；把 W42-C 登记的 ~0.39 D 偶极偏置分层归因；并把 W44-A/B/D 三条守卫在本轮复跑成快照。

**交付**

- **预注册**：`probes/w45_compute_prereg.json`（`locked_before_run`，r3）。四条 lane 的分母、分层边界、阈值、重抽数、守卫口径与禁止动作跑前写死。r1->r2 修正稳健离群闸（对 ~6.99 eV 电平差去中位），r2->r3 修正偶极重原子分箱为 [[1,5],[6,7],[8,9]] 与符号约定 `mean(our-qm9)` 锚 +0.39451165048543685 D。
- **W45-A 标定列保真与泄漏审计**（10/10 成立）：`calib_homo_eV` 是 `homo_gfn2_eV` 的精确一元仿射（4668 行最大残差 1.8e-15），与 `homo_gfn2 -> homo_batt` 的 in-sample OLS 逐位同映射（Δslope 4.4e-16）；仿射保序 ⇒ Δρ(calib vs gfn2) = 0.0，MAE 1.2066 -> 0.3032 eV；5 折 CV MAE 0.30329、泄漏缺口 1.3e-4；`calib_lumo_eV` 全空（已知边界 H45a7）。
- **W45-B 4668 行分层残差与稳健离群**（10/10 成立）：总体 ρ 逐位复现 0.5984785837315431（CI [0.5800, 0.6173]、置换 p 0.0005）；tier ρ 0.5974/0.5280/0.5130（同质）；重原子分箱 ρ 0.8107/0.7315/0.4810（单调退化）；稳健离群比例 0.1165。
- **W45-C 偶极偏置分层归因**（10/10 成立）：重合 n=103、均值偏置 0.39451165048543685 D 逐位复现 W42-C；三分位中位 0.0598/0.4817/0.5207（随幅度增长）；偏置幅度 vs 偶极幅度 ρ 0.4775、vs 重原子数 0.0234（非尺寸伪影）。
- **W45-D 三条守卫 + 台账复跑快照**（7/7 成立）：闸门拒 3 / PubChemQC 过闸 / 未申报 0；验收 42 轮 / fail 0 / 最近五轮全过；静态 365 文件 / mutation 0 / 写入 0；台账并集 9 / 越界 0 / shot 上限 19。
- **测试与集成**：`tests/test_w45_*.py`（24 项）全绿；论文 v3 -> v1.9 §3.30；README §0/§5/§7/§8/§11；`reports/decisions_log.md` §28.100；导出脚本 `probes/export_week45_results.py`。

**结果与验收**

- **判据**：37 条（A 10 / B 10 / C 10 / D 7）**全部成立、0 判否**；四条探针连跑两遍，`git status --porcelain` 脏路径集**逐项稳定**。
- **测试**：`tests/test_w45_*.py`（6+7+6+5 = 24 项）加 `test_repo_hygiene.py` / `test_w38_data_recon.py` / `test_w37_gate_admission_export.py` 子集共 **43 passed**。
- **治理校验**：`scripts/verify_four_core_registry.py --check` 全 PASS；`scripts/check_paper_artifact_consistency.py` 打印 `paper drafts agree with the frozen artifacts`。
- **论文与渲染**：v3 头部升到 **v1.9**、证据范围 week21–week45、新增 §3.30；`paper/make_paper_v3_docx.py` 重渲染 **351 段 / 9 表 / 23 图**，23 张图全部以真实字节嵌入（合计 4.5 MB，无过小图）；`scripts/verify_paper_figures.py` 报 6 张被引图片 present 且可复现。
- **导出**：`probes/export_week45_results.py` -> `成果输出/week45`，**34 文件**、`verification_passed=true`、`lanes_missing=[]`、`frozen_red_lines_intact=true`、`worktree_dirty_paths=182`。

**坑与更正**

- 稳健离群闸第一版用未去中位的 z 分数，被 6.99 eV 的系统电平差淹没（几乎全是离群）；r2 改成「去中位后的 MAD 稳健尺度」才把 3.5σ 比例压到 0.1165。
- 偶极偏置符号约定必须先锚死：`mean(our - qm9)` = +0.3945 D；若写成 `qm9 - our` 会得到对称的 -0.3945，分层单调方向随之反转。
- 重原子分箱初版边界与 W42/W43 名册口径不一致（出现空箱）；r3 固定为 [[1,5],[6,7],[8,9]] 后每箱 n ≥ 29。
- 导出后 W45-B/D 的治理快照会随 `成果输出/week45` 出现而变（验收 41 -> 42 轮、声明 33 -> 34 轮、静态扫描 364 -> 365 文件，因为新增了导出脚本本体）；所有文档数字统一按「导出后复跑」的读数校准，再二次导出，避免包里留下过程读数。
- 用 Node 落盘文本时，反引号要先用占位符顶替、写完再整体替换回真反引号；本轮 `edit()` 漏做了这一步，`README.md` 一次性残留 **30 处**占位符，靠全局替换修回 —— 写后必须再扫一遍占位符确认为 0（含本仓既有的 BOM 老探针，扫描要用 `utf-8-sig` 读）。
- 测试计数初稿写成 29 项，实际 `--collect-only` 收集 **24 项**（6+7+6+5），已在 README / 交付说明 / decisions_log 全仓更正。

**下一步（已登记）**

- 见 README §11 第 42–44 条：① 标定列只是 in-sample 仿射（不得当独立层/同层级源、`calib_lumo` 全空）；② 偶极偏置随幅度增长（支撑 affine 优先于 shift，但仍不授权修数）；③ xTB 秩一致随分子变大从 0.81 退化到 0.48（代理只能声明小分子域）。
- 仍未闭合：要给 HOMO/LUMO 通道加权，仍须补一个 **strict same-level 独立源**；PubChemQC 入口（先 InChIKey→CID 再按分片定位）仍未执行。
