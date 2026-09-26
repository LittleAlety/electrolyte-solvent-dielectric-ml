# W17-17「THEMol 全量轨道扩展」臂 —— 对抗式独立审计报告（第 2 轮 / 修复后复审计）

审计员：独立审计 agent（对抗式复核，只读被审对象，不修改任何被审文件）。
日期：2026-09-27（Asia/Shanghai）。
复核脚本：probes/audit_themol_expanded_layer.py；机器数字：probes/themol_expanded_layer_audit.json；离线钉桩：tests/test_themol_expanded_layer_audit.py。
本文件保留第 1 轮记录（见第 2 节），不覆盖历史。

## 0. 审计快照（第 2 轮，冻结终态）

开采已结束，图层为冻结终态。本轮锁定的唯一快照：

| 对象 | 路径 | sha256 | 字节 | 行数 |
|---|---|---|---|---|
| 交付层 | data/processed/themol_orbital_layer_expanded.csv | 8b10b23f3da60c48cafc96cf783605180869b890ff0c5a4df7d0dd9c2036703b | 3,347,049 | 5,117 |
| 层摘要 | probes/themol_orbital_layer_expanded_summary.json | 3accc57d83e66b42b6d8e9824ddbc1215f917ba7a8e6fc4824ebb68a2a8df9fc | 20,943 | — |
| 本层单位复核 | data/raw/themol/expand_unit_recheck.json | 23cad0a6941ed563947db76aad4da04ab04735f26a70be16a28f674042e04148 | 16,610 | — |
| 名册（冻结） | probes/themol_registry_expansion_roster.csv | 71277d2c2607dfc5efb31654e2bb668a2618ef6e830073c4aea7fcb48d0136d6 | 956,973 | 5,117 |

独立核对：交付层 sha256 = 8b10b23f…、5,117 行、run_status = complete、delivered 5,117 / roster 5,117、
failed_rows = 0。且构建器自检 build_themol_orbital_layer_expanded.py --check 现在返回
layer_matches=true / summary_matches=true / 5,117 / complete —— 图层已可由 raw 分片逐字节复现
（第 1 轮该检查为 false，因为当时运行在途）。

## 1. 第 2 轮结论摘要

修复已按根因落地，我逐条从代码与数据自行验证，未采信口头说明。9 条发现：7 条 closed、
1 条 partially_closed（F6）、1 条 open（F5）。最不放心的地方见第 6 节。

## 2. 历史保留：第 1 轮（修复前）记录

- 第 1 轮快照：layer sha256 44f900b14778961eea878e167f06e459f7c0d953de15fabf13e55cd62dedd3a0，3,109 行；
  summary sha256 557c9e3e08468b32a64745f346f32983c7f331dc6fc2da1d87ca08d1bb49e073。
- 第 1 轮判定：F1 fail / F2 fail / F3 pass / F4 pass / F5 partial / F6 fail / F7 fail / F8 fail / F9 not_reproducible。
- 上述写入 JSON 的 history.round1，测试 test_round1_history_is_preserved 钉住，不会被抹掉。

## 3. 逐条发现：第 2 轮判定 + 证据

### F1 —— 标定闸门（修复前 fail → 现在 closed）
- 代码证据：共享 W17-14 函数 calibration() 未动；扩展构建器新增 out_of_sample_r() 与
  apply_out_of_sample_gate()，在 compose() 第 340–342 行重新判定 status，只读
  mae_out_of_sample_eV 与 pearson_r_out_of_sample（源码含 r_out is not None 与 r_out >= R_LIMIT）。
  验证器第 128 行同样改为只认 r_out。
- 独立重算（对冻结层）：HOMO n=4668 slope=0.870257 r_in=0.854910 r_oos=0.854536 mae=0.303573；
  LUMO r_in=0.614063 r_oos=0.613737 mae=0.349506；GAP r_in=0.434268 r_oos=0.433587 mae=0.591021。
  三者 recorded.status 均等于"用 r_oos 的闸门"结果（HOMO usable_with_flag，LUMO/GAP reference_only），
  status_basis = out_of_sample_mae_and_out_of_sample_r。
- 行为证据（关键）：本快照 r_in 与 r_oos 极近，光看判定结果无法区分修复与否。因此测试
  test_builder_gate_is_governed_by_out_of_sample_r 直接调用构建器的 apply_out_of_sample_gate：
  构造 r_in=0.0 但 r_oos=1.0 → usable_with_flag；构造 r_in=0.99 但 r_oos=−0.96 → reference_only。
  证明闸门确由 r_oos 决定，与 r_in 无关。判 closed。
- 残留（本臂范围外）：共享模块 probes/build_themol_orbital_layer.py:224 仍以样本内 r 判定
  W17-14 自己的 status；本次修复是 W17-17 局部重判，未回改 W17-14 口径。已记入 JSON。

### F2 —— off-roster / 重复计数（修复前 fail → 现在 closed）
- 代码证据：构建器第 246–260 行重排——off-roster 在过滤处即 append（可达）；
  每一次重复都 append 到 duplicate_keys，另计 duplicate_upgrades。第 1 轮的死分支已删除。
- 独立复刻（对 raw 分片）：shard_*.csv 共 30 个（含 _b/_c/_d），原始解析行 5,419；
  off-roster 0、duplicate_collisions 302、duplicate_upgrades 117、unique 5,117 —— 与摘要逐字段相等。
- 合成实验（证明可达）：off-roster 行 → 计数 1；两条 ok 重复 → 碰撞计数 1；error→ok → 升级计数 1。
- 判 closed。

### F3 —— 5,117 名册口径（修复前 pass → 现在 closed）
- 独立从 registry + themol 索引 + 电介质名册重算：counters 31949/2/26830/0/5117、
  tiers 421/54/68/4574，与摘要逐字段相等；名册 digest 与预注册/汇总一致。判 closed。

### F4 —— 验证器独立性（修复前 pass → 现在 closed）
- AST 导入扫描：仅 stdlib + rdkit；不 import 生成器、源码不含 build_themol；生成器仍 import 共享模块
  （即验证器与生成器不共享代码）。并新增确认验证器已走 r_oos 闸门。判 closed。

### F5 —— structure_check（修复前 partial → 现在 open，未修）
- 现状不变：确实逐行从该行 SMILES 用 rdkit 现算，我 5,117 行全部重算一致（match=5,117、mismatch=0、
  unparsable=0、与落盘列零分歧）。
- 但两个削弱仍在：(1) 只比较 InChIKey 第一段（骨架），立体/同位素异构体放行；
  (2) 被查 SMILES 来自名册行本身，证明的是"名册 SMILES ↔ 名册键自洽"，非"THEMol 几何与该键一致"。
  本轮无对应改动 → 判 open（属部分成立的老问题，非新缺陷）。

### F6 —— 单位证据（修复前 fail → 现在 partially_closed）
- 新增 probes/themol_expand_unit_recheck.py：自带 occupation 解析器（明确不用 parse_orbitals），
  固定种子 20260927 抽样 24 行，重取几何、重跑 GFN2-xTB、重解析，并逐行比对几何 digest。
- 我独立核对：以同一种子重放 sample_rows() 得到的 24 个 InChIKey 与 JSON 完全一致（非事后挑选）；
  JSON 里 24 行的 homo/lumo 与冻结层对应行数值一致；layer_sha256 与当前层一致；
  sample_share = 24/5117 = 0.00469（0.47%）；geometry_digest_matches 24/24；
  ΔHOMO = ΔLUMO = 0.0 eV；all_passed = true。
- "这不是全量复现"写死在 coverage_note：
  "a passing sample shows the delivered numbers are reproducible; it is not a re-derivation of
  every row, and the share above is the honest coverage"，摘要挂 unit_check.this_layer_evidence。
- 与"预注册判据 C 未落实"的关系（回答维护者）：
  判据 C 原文要求"独立重解析存储的 xTB 输出复现每个交付数字（every delivered number）"。
  新探针满足其精神（第二次代码路径 + 重取几何 + 重新解析，复现了所交付数字），
  但没满足字面（0.47% 抽样，非 every row）；且它复用同一 write_xyz 计算几何 digest
  （同族代码；非循环的部分在"重取 + 重解析"，digest 计算本身非独立）。
  因此判据 C = 部分落实（抽样层面落实、字面未达成，且已如实标注）。故 F6 判 partially_closed。

### F7 —— models_fitted（修复前 fail → 现在 closed）
- 摘要新增 models_fitted_note，说明本臂不训练任何目标性质模型，唯一被拟合的是 calibration 里的
  跨能级线性映射，并按样本外误差报告。该说明与"存在全量拟合 + 样本外闸门"不再冲突。判 closed。

### F8 —— 报告缺失（修复前 fail → 现在 closed）
- reports/themol_orbital_layer_expanded.md 已存在（10,033 B），含"## 7. 收尾补记"，逐一回应 F1/F2/F6/F7/F8。判 closed。

### F9 —— 被点名的 ruff F841（修复前 not_reproducible → 现在 closed）
- 依旧不可复现：ruff check probes tests 全绿，无 F841。判 closed（无须修复）。

## 4. 逐条怀疑判定（第 2 轮）

| # | 怀疑 | 第 1 轮 | 第 2 轮 |
|---|---|---|---|
| 1 | 标定泄漏（样本内 r 判闸） | 不通过 | closed |
| 2 | 5,117 名册统计口径 | 通过 | closed |
| 3 | 去重 / 合并计数守卫 | 不通过 | closed |
| 4 | 验证器独立性 | 通过 | closed |
| 5 | structure_check 逐行重算 | 部分通过 | open（未修） |
| 6 | 单位 / 刻度证据比例 | 不通过 | partially_closed |
| 7 | models_fitted = 0 自洽性 | 不通过 | closed |
| — | 报告交付物存在 | 不通过 | closed |
| — | ruff F841 | 不成立 | closed |

## 5. 工具结果

- ruff：.\.venv\Scripts\python.exe -m ruff check probes tests → All checks passed!
- pytest（未用 -X utf8）：
  tests/test_themol_expanded_layer_audit.py → 15 passed；
  连同 tests/test_themol_registry_expansion.py、tests/test_themol_eps_reproduction.py → 39 passed。
- 构建器自洽：build_themol_orbital_layer_expanded.py --check → layer_matches=true, summary_matches=true, 5,117, complete。
- 验证器自洽：verify_themol_orbital_layer_expanded.py --check → failures=0, PASS。
- 单位复核自洽：themol_expand_unit_recheck.py --check → failures=[], n_sampled=24, CHECK OK。

## 6. 我最不放心的地方

1. F1 修复在本快照上"数据不可证伪"：HOMO/LUMO/GAP 三通道的 r_in 与 r_oos 相差都在 1e-4 量级，
   用哪种口径判定结果都一样。所以"已改成 r_oos"这件事，只能靠读代码 + 我用合成输入做的行为探针
   证实，靠这批真实数据本身是证不出来的。若后续有人回退该改动，现有数据不会报警——
   只有那条行为测试会拦住它。
2. 共享 W17-14 模块的口径没回改：probes/build_themol_orbital_layer.py:224 仍以样本内 r 判定
   W17-14 自己的 status。W17-17 是局部重判修好的，等于同一套判据在仓库里现在有两种口径。
   本次审计范围只到 W17-17，但这个不一致值得单独处理。
3. F5 完全没动：structure_check 仍只比骨架段、且 SMILES 来自名册自身，"几何↔键"这层其实没被证明。
   它不是回归，但也没被修复，属长期存在的弱证（现判 open）。
4. F6 的 digest 用同族代码：单位复核确实是第二次独立解析 + 重取几何，但几何 digest 仍由
   harvest 用的同一个 write_xyz 计算，digest 计算这一环非独立；且覆盖 0.47%，样本外推到 5,117 行
   仍有外推风险（探针已如实声明不覆盖全量）。
5. 名册层面的口径风险仍未变：预注册标题/图件若单独引用"166 → 5,117"，需强制带
   run_status=complete 与"配对 4,668"的限制语（本臂 calibration 配对是 4,668，不是 5,117 全量）。

## 7. 审计边界

- 未联网、未重跑 xTB、未下载几何，故未独立复现在 24 个抽样分子以外的任一 HOMO/LUMO 数值。
  本审计覆盖管线一致性、标定协议、计数守卫、单位证据比例与交付完整性，不覆盖"xTB 单点数值是否物理正确"。
- 冻结层 sha256 8b10b23f… 若日后被改动，第 0 节快照即失效；但 F1–F9 的判定是代码/协议级结论。
