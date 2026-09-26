# AL Round 3 周末缓冲支线：37 条 OA 线索的标题/摘要级分流

- 生成时间：`2026-09-25T18:24:35Z`（运行模式 `online`，耗时 160.86 s）
- 输入：`E:\Claude Code\电解质ML\成果输出\week11\al_round3_candidates.csv`（Week 11 留下的 37 条 OA 线索）
- 产物：`E:\Claude Code\电解质ML\电解质ML\probes\al_round3_oa_triage.csv`、`E:\Claude Code\电解质ML\电解质ML\probes\al_round3_oa_triage_summary.json`
- 脚本：`E:\Claude Code\电解质ML\电解质ML\probes\al_round3_oa_triage.py`
- 校验：`verification_passed = true`（20/20 项自检通过）

**一句话结论：37 条里 4 条进人工阅读清单（P0=0 / P1=4），20 条待定，13 条丢弃；其中标题/摘要层面真正给出 ε 数值线索的只有 1 条，明确覆盖 253–333 K 的有 1 条。**

## 1. 方法与口径

本支线**只做标题/摘要级判断**：不读全文、不下载受限全文。每条线索走四步：

1. **化合物/体系**：标题 + 摘要里的名称匹配 Week 11 手工维护的 name/alias -> SMILES 表（本脚本另补 3 个任务点名的目标化合物），用 RDKit 算 InChIKey；指不出单一分子的（泛指 glyme、聚合物、盐、品牌名）记为 unresolved，不猜。
2. **ε 线索**：在标题+摘要里找「介电措辞 + 合理数值」同句的句子，逐字保留；只有方法论措辞没数值的记为「仅措辞」。
3. **温度窗口**：只认带单位的显式温度（K/°C）。与 253–333 K 相交 -> `true`；显式温度全部在窗外 -> `false`；只写 room temperature 或完全没提 -> `unknown`（不做 298 K 换算）。
4. **OA 全文是否可得**：用 Unpaywall 的 `is_oa` + `best_oa_location` 复核，再对该 OA 链接发一次≤ 8 KB 的范围 GET，只记录 HTTP 状态码、Content-Type、字节数、是否为机器人校验页、以及是否只是一个 < 20 KB 的 HTML 落地页；**响应体不保留**。

- **数值过滤**：ε 数值必须通过「不是化学式里的数字（G4、LiClO4）、不是配比（EC:EMC 3:7）、不是电压/单位（4.3 V）」这一关，否则「介电常数」字样会顺手把分子式里的数字算成 ε。
- **温度过滤**：整句在讲 superheat／温差的句子被整体丢弃，低于 60 K 的 K 值也不算绝对温度 —— 「28 K 过热度」不会被当成 28 K 的实测温度。

**优先级梯子**（可审计：分量之和 = `priority_score`）

| 分量 | 取值 |
|---|---|
| score_target | core 目标=3；core 族未定位=2；相邻电池溶剂=1；非目标=0 |
| score_epsilon | 数值线索=3；仅措辞=1；无=0 |
| score_temperature | 覆盖=True 2；unknown=0；在外=-1 |
| score_oa | 2xx 且非校验页=2；未知=1；不可得=0 |

- `P0` = core 目标 且 ε 数值线索 且 总分 ≥ 8；`P1` = 总分 ≥ 5 且带目标族；`P2` = 总分 ≥ 2；其余 `P3`。
- 两个否决：命中 Week 11 噪声规则；或「既不是目标/相邻溶剂族、也没有 ε 线索」。否决会把最终优先级压到 `P3`，分数列仍保留原始分量供复核。
- 分流：`P0/P1 -> 进人工阅读清单`；`P2 -> 待定`；`P3 -> 丢弃`。

**合规**：受限值与受限全文只作为线索，永不进可分发数据集；报告与产物只记 DOI / 标题 / OA 状态 / 标题摘要片段。本次运行共发出 116 次请求（上限 220），详见 summary JSON 的 `api` 段。

## 2. 汇总统计

| 维度 | 计数 |
|---|---|
| 总线索 | 37 |
| 优先级 P0 | 0 |
| 优先级 P1 | 4 |
| 优先级 P2 | 20 |
| 优先级 P3 | 13 |
| 分流：进人工阅读清单 | 4 |
| 分流：待定 | 20 |
| 分流：丢弃 | 13 |
| ε 数值线索（标题/摘要） | 1 |
| ε 仅措辞、无数值 | 22 |
| 完全无 ε 线索 | 14 |
| 温窗覆盖=true | 1 |
| 温窗在外=false | 2 |
| 温窗 unknown | 34 |
| OA 全文可得=true | 9 |
| OA 全文不可得=false | 25 |
| OA 全文未知 | 3 |
| 摘要成功读到 | 32 |
| 摘要未读到 | 5 |
| 化合物完整指认 | 15 |
| 化合物未解析 | 3 |

API 请求：

| 类型 | 次数 |
|---|---|
| crossref | 5 |
| oa_probe | 37 |
| openalex | 37 |
| unpaywall | 37 |
| 合计 | 116 |

响应状态码分布：`{'200': 84, '403': 21, '206': 8, 'error': 3}`

## 3. 逐条分级表（37 条，按优先级排序）

| # | DOI | 化合物/体系 | 目标类 | ε 线索 | 温窗 253–333 K | OA 全文 | 优先级 | 分流 |
|---|---|---|---|---|---|---|---|---|
| 1 | `10.1149/1945-7111/ab6975` | tetraglyme | core 目标 | 仅措辞 | 未知 | 可得 (206) | P1 | 进人工阅读清单 |
| 2 | `10.1149/2.0461816jes` | adiponitrile;propylene carbonate | core 目标 | 仅措辞 | 未知 | 可得 (206) | P1 | 进人工阅读清单 |
| 3 | `10.1088/1361-648x/aab466` | succinonitrile | core 目标 | 仅措辞 | 未知 | 可得 (206) | P1 | 进人工阅读清单 |
| 4 | `10.1063/1.4944394` | glutaronitrile;succinonitrile | core 目标 | 仅措辞 | 未知 | 可得 (206) | P1 | 进人工阅读清单 |
| 5 | `10.1063/5.0230695` | succinonitrile | core 目标 | 仅措辞 | 未知 | 不可得 (403) | P2 | 待定 |
| 6 | `10.1002/app.56331` | succinonitrile | core 目标 | 无 | 在外 | 不可得 (403) | P2 | 待定 |
| 7 | `10.1039/d2cp05799a` | glutaronitrile;succinonitrile | core 目标 | 无 | 未知 | 不可得 (403) | P2 | 待定 |
| 8 | `10.1039/d2cp03200g` | tetraglyme | core 目标 | 仅措辞 | 未知 | 不可得 (403) | P2 | 待定 |
| 9 | `10.1021/acsenergylett.2c02003` | 1,2-dimethoxypropane;1,2-dimethoxyethane | core 目标 | 仅措辞 | 未知 | 不可得 | P2 | 待定 |
| 10 | `10.1016/j.nocx.2022.100097` | glutaronitrile;succinonitrile | core 目标 | 仅措辞 | 未知 | 不可得 (403) | P2 | 待定 |
| 11 | `10.1002/eem2.12494` | ethyl methyl carbonate;ethylene carbonate | 相邻(碳酸酯/酯) | 有(数值) | 未知 | 不可得 (403) | P2 | 待定 |
| 12 | `10.1063/5.0046073` | tetraglyme;1,2-dimethoxyethane;triglyme;digly… | core 目标 | 仅措辞 | 未知 | 不可得 (200) | P2 | 待定 |
| 13 | `10.1021/acs.jpclett.0c00334` | 1,2-dimethoxyethane;diglyme | core 目标 | 仅措辞 | 未知 | 不可得 | P2 | 待定 |
| 14 | `10.1016/j.electacta.2019.02.110` | unresolved | core 族(未定位分子) | 无 | 未知 | 未知 (200) 落地页 | P2 | 待定 |
| 15 | `10.1063/1.4913320` | propylene carbonate | 相邻(碳酸酯/酯) | 仅措辞 | 未知 | 不可得 (403) | P2 | 待定 |
| 16 | `10.1021/acs.jpcc.5b09380` | succinonitrile;glutaronitrile | core 目标 | 仅措辞 | 在外 | 不可得 (403) | P2 | 待定 |
| 17 | `10.1021/acs.jpcb.5b09561` | propylene carbonate;ethylene carbonate | 相邻(碳酸酯/酯) | 仅措辞 | 未知 | 不可得 | P2 | 待定 |
| 18 | `10.1063/1.4867095` | glutaronitrile;succinonitrile | core 目标 | 仅措辞 | 未知 | 不可得 (403) | P2 | 待定 |
| 19 | `10.1063/1.4794792` | propylene carbonate | 相邻(碳酸酯/酯) | 仅措辞 | 未知 | 可得 (206) | P2 | 待定 |
| 20 | `10.1063/1.4746022` | propylene carbonate | 相邻(碳酸酯/酯) | 仅措辞 | 未知 | 可得 (206) | P2 | 待定 |
| 21 | `10.1021/jp302790j` | hexafluoroisopropanol;2,2,2-trifluoroethanol | 非目标 | 仅措辞 | 未知 | 可得 (200) | P2 | 待定 |
| 22 | `10.1063/1.2815764` | 1,2-dimethoxyethane | core 目标 | 无 | 未知 | 不可得 (403) | P2 | 待定 |
| 23 | `10.1023/b:ijot.0000034239.58332.be` | 1,2-dimethoxyethane;ethane-1,2-diol;water | core 目标 | 无 | 未知 | 不可得 (403) | P2 | 待定 |
| 24 | `10.1149/1.1403730` | ethyl methyl carbonate;ethylene carbonate | 相邻(碳酸酯/酯) | 仅措辞 | 未知 | 可得 (206) | P2 | 待定 |
| 25 | `10.3390/app14020495` | methoxy-nonafluorobutane | core 目标 | 无 | 未知 | 不可得 (403) | P3 | 丢弃 |
| 26 | `10.1088/1742-6596/2685/1/012064` | decafluoropentane;perfluorohexane | 非目标 | 无 | 未知 | 可得 (206) | P3 | 丢弃 |
| 27 | `10.1002/anie.202416091` | hexafluoroisopropanol | 非目标 | 仅措辞 | 未知 | 不可得 (403) | P3 | 丢弃 |
| 28 | `10.1016/j.applthermaleng.2023.121803` | decafluoropentane;water | 非目标 | 无 | 未知 | 未知 (200) 落地页 | P3 | 丢弃 |
| 29 | `10.1021/jacs.2c07103` | water | 非目标 | 仅措辞 | 未知 | 不可得 (403) | P3 | 丢弃 |
| 30 | `10.3390/nano11123216` | decafluoropentane;1-butanol;water | 非目标 | 无 | 未知 | 不可得 (403) | P3 | 丢弃 |
| 31 | `10.1016/j.applthermaleng.2020.115862` | unresolved | 非目标 | 无 | 未知 | 不可得 (403) | P3 | 丢弃 |
| 32 | `10.1049/hve.2019.0144` | propylene carbonate | 相邻(碳酸酯/酯) | 无 | 未知 | 不可得 (403) | P3 | 丢弃 |
| 33 | `10.1016/j.bpj.2017.12.013` | unresolved | 非目标 | 仅措辞 | 未知 | 不可得 (403) | P3 | 丢弃 |
| 34 | `10.1002/2014wr015291` | methoxy-nonafluorobutane;water | core 目标 | 仅措辞 | 未知 | 不可得 (403) | P3 | 丢弃 |
| 35 | `10.1063/1.4740236` | propylene carbonate;tripropylene glycol | 相邻(碳酸酯/酯) | 无 | 未知 | 不可得 (403) | P3 | 丢弃 |
| 36 | `10.1529/biophysj.106.098715` | 2,2,2-trifluoroethanol | 非目标 | 无 | 未知 | 未知 (200) 落地页 | P3 | 丢弃 |
| 37 | `10.1073/pnas.182199699` | 2,2,2-trifluoroethanol;water | 非目标 | 无 | 覆盖 | 不可得 (403) | P3 | 丢弃 |

注：`目标类` 里的 core 族 = glyme / 二腈 / 磺砺 / 氟代醚；相邻 = 碳酸酯与酯 / 醇醚；非目标 = 水、醇、氟代烷、传热流体等。`OA 全文` 列括号里是实测到的站点 HTTP 状态码。

## 4. 进人工阅读清单（4 条）

| DOI | 化合物/体系 | 优先级 | 分数 | OA 状态 | 分流理由 |
|---|---|---|---|---|---|
| `10.1149/1945-7111/ab6975` | tetraglyme | P1 | 6 | is_oa=true / oa_status=hybrid / probe=206 (8192 B) | target=core; epsilon=wording_only; temperature=unknown; oa=true; score=6 |
| `10.1149/2.0461816jes` | adiponitrile;propylene carbonate | P1 | 6 | is_oa=true / oa_status=hybrid / probe=206 (8192 B) | target=core; epsilon=wording_only; temperature=unknown; oa=true; score=6 |
| `10.1088/1361-648x/aab466` | succinonitrile | P1 | 6 | is_oa=true / oa_status=green / probe=206 (8192 B) | target=core; epsilon=wording_only; temperature=unknown; oa=true; score=6 |
| `10.1063/1.4944394` | glutaronitrile;succinonitrile | P1 | 6 | is_oa=true / oa_status=green / probe=206 (8192 B) | target=core; epsilon=wording_only; temperature=unknown; oa=true; score=6 |

### 4.1 逐字证据（标题/摘要级）

| DOI | ε 证据（标题/摘要逐字） | 温度证据（逐字） | 来源 |
|---|---|---|---|
| `10.1149/1945-7111/ab6975` | Namely, acetonitrile and dimethyl sulfoxide (DMSO) with relatively high dielectric constant and low viscosity were mixed with G4 solvent to increase the number per volume and mobility of Li+ and NO3 − as carrier ions for reduction of the large overpotential during charge process and enhancement of the power density. | (无) | openalex |
| `10.1149/2.0461816jes` | In cases where neither electrolyte components nor decomposition products thereof enable the formation of protective surface layers on aluminum current collectors, both the viscosity and relative permittivity of the solvents could be identified as key parameters for reducing aluminum dissolution. | (无) | openalex |
| `10.1088/1361-648x/aab466` | Structural, electrical properties and dielectric relaxations in Na + -ion-conducting solid polymer electrolyte + x wt. % succinonitrile. | (无) | openalex |
| `10.1063/1.4944394` | Nonlinear dielectric spectroscopy in a fragile plastic crystal In this work we provide a thorough examination of the nonlinear dielectric properties of a succinonitrile-glutaronitrile mixture, representing one of the rare examples of a plastic crystal with fragile glassy dynamics. | (无) | openalex |

## 5. 待定（20 条）

| DOI | 化合物/体系 | 目标类 | 优先级 | 分数 | 分流理由 |
|---|---|---|---|---|---|
| `10.1063/5.0230695` | succinonitrile | core 目标 | P2 | 4 | target=core; epsilon=wording_only; temperature=unknown; oa=false; score=4 |
| `10.1002/app.56331` | succinonitrile | core 目标 | P2 | 2 | target=core; epsilon=none; temperature=false; oa=false; score=2 |
| `10.1039/d2cp05799a` | glutaronitrile;succinonitrile | core 目标 | P2 | 3 | target=core; epsilon=none; temperature=unknown; oa=false; score=3 |
| `10.1039/d2cp03200g` | tetraglyme | core 目标 | P2 | 4 | target=core; epsilon=wording_only; temperature=unknown; oa=false; score=4 |
| `10.1021/acsenergylett.2c02003` | 1,2-dimethoxypropane;1,2-dimethoxyethane | core 目标 | P2 | 4 | target=core; epsilon=wording_only; temperature=unknown; oa=false; score=4 |
| `10.1016/j.nocx.2022.100097` | glutaronitrile;succinonitrile | core 目标 | P2 | 4 | target=core; epsilon=wording_only; temperature=unknown; oa=false; score=4 |
| `10.1002/eem2.12494` | ethyl methyl carbonate;ethylene carbona… | 相邻(碳酸酯/酯) | P2 | 4 | target=adjacent; epsilon=value; temperature=unknown; oa=false; score=4 |
| `10.1063/5.0046073` | tetraglyme;1,2-dimethoxyethane;triglyme… | core 目标 | P2 | 4 | target=core; epsilon=wording_only; temperature=unknown; oa=false; score=4 |
| `10.1021/acs.jpclett.0c00334` | 1,2-dimethoxyethane;diglyme | core 目标 | P2 | 4 | target=core; epsilon=wording_only; temperature=unknown; oa=false; score=4 |
| `10.1016/j.electacta.2019.02.110` | unresolved | core 族(未定位分子) | P2 | 3 | target=core_family_unresolved; epsilon=none; temperature=unknown; oa=unknown; score=3 |
| `10.1063/1.4913320` | propylene carbonate | 相邻(碳酸酯/酯) | P2 | 2 | target=adjacent; epsilon=wording_only; temperature=unknown; oa=false; score=2 |
| `10.1021/acs.jpcc.5b09380` | succinonitrile;glutaronitrile | core 目标 | P2 | 3 | target=core; epsilon=wording_only; temperature=false; oa=false; score=3 |
| `10.1021/acs.jpcb.5b09561` | propylene carbonate;ethylene carbonate | 相邻(碳酸酯/酯) | P2 | 2 | target=adjacent; epsilon=wording_only; temperature=unknown; oa=false; score=2 |
| `10.1063/1.4867095` | glutaronitrile;succinonitrile | core 目标 | P2 | 4 | target=core; epsilon=wording_only; temperature=unknown; oa=false; score=4 |
| `10.1063/1.4794792` | propylene carbonate | 相邻(碳酸酯/酯) | P2 | 4 | target=adjacent; epsilon=wording_only; temperature=unknown; oa=true; score=4 |
| `10.1063/1.4746022` | propylene carbonate | 相邻(碳酸酯/酯) | P2 | 4 | target=adjacent; epsilon=wording_only; temperature=unknown; oa=true; score=4 |
| `10.1021/jp302790j` | hexafluoroisopropanol;2,2,2-trifluoroet… | 非目标 | P2 | 3 | target=off; epsilon=wording_only; temperature=unknown; oa=true; score=3 |
| `10.1063/1.2815764` | 1,2-dimethoxyethane | core 目标 | P2 | 3 | target=core; epsilon=none; temperature=unknown; oa=false; score=3 |
| `10.1023/b:ijot.0000034239.58332.be` | 1,2-dimethoxyethane;ethane-1,2-diol;wat… | core 目标 | P2 | 3 | target=core; epsilon=none; temperature=unknown; oa=false; score=3 |
| `10.1149/1.1403730` | ethyl methyl carbonate;ethylene carbona… | 相邻(碳酸酯/酯) | P2 | 4 | target=adjacent; epsilon=wording_only; temperature=unknown; oa=true; score=4 |

## 6. 丢弃（13 条）

| DOI | 标题 | 优先级 | 分数 | 分流理由 |
|---|---|---|---|---|
| `10.3390/app14020495` | Saturated Boiling Enhancement of Novec-7100 on Microgrooved S… | P3 | 3 | target=core; epsilon=none; temperature=unknown; oa=false; score=3; noise veto (pool_boiling_heat_transfer) |
| `10.1088/1742-6596/2685/1/012064` | Pool boiling performances comparison of FC-72 and Novec 649 i… | P3 | 2 | target=off; epsilon=none; temperature=unknown; oa=true; score=2; noise veto (pool_boiling_heat_transfer) |
| `10.1002/anie.202416091` | Fast Collective Hydrogen‐Bond Dynamics in Hexafluoroisopropan… | P3 | 1 | target=off; epsilon=wording_only; temperature=unknown; oa=false; score=1 |
| `10.1016/j.applthermaleng.2023.121803` | Enhanced nucleate boiling of Novec 649 on thin metal foils vi… | P3 | 1 | target=off; epsilon=none; temperature=unknown; oa=unknown; score=1; noise veto (pool_boiling_heat_transfer) |
| `10.1021/jacs.2c07103` | Why Do Sulfone-Containing Polymer Photocatalysts Work So Well… | P3 | 1 | target=off; epsilon=wording_only; temperature=unknown; oa=false; score=1; noise veto (polymer_photocatalyst) |
| `10.3390/nano11123216` | Hydrophilic and Hydrophobic Nanostructured Copper Surfaces fo… | P3 | 0 | target=off; epsilon=none; temperature=unknown; oa=false; score=0; noise veto (pool_boiling_heat_transfer) |
| `10.1016/j.applthermaleng.2020.115862` | Immersion cooling effect of dielectric liquid and self-rewett… | P3 | 0 | target=off; epsilon=none; temperature=unknown; oa=false; score=0; noise veto (pool_boiling_heat_transfer) |
| `10.1049/hve.2019.0144` | Effect of surface modification of electrodes on charge inject… | P3 | 1 | target=adjacent; epsilon=none; temperature=unknown; oa=false; score=1 |
| `10.1016/j.bpj.2017.12.013` | Structural Impact of Phosphorylation and Dielectric Constant … | P3 | 1 | target=off; epsilon=wording_only; temperature=unknown; oa=false; score=1; noise veto (biophysics_peptide_or_protein) |
| `10.1002/2014wr015291` | Electrical permittivity and resistivity time lapses of multip… | P3 | 4 | target=core; epsilon=wording_only; temperature=unknown; oa=false; score=4; noise veto (geophysics_dnapl) |
| `10.1063/1.4740236` | Shear and dielectric responses of propylene carbonate, tripro… | P3 | 1 | target=adjacent; epsilon=none; temperature=unknown; oa=false; score=1 |
| `10.1529/biophysj.106.098715` | 2,2,2-Trifluoroethanol Changes the Transition Kinetics and Su… | P3 | 1 | target=off; epsilon=none; temperature=unknown; oa=unknown; score=1; noise veto (biophysics_peptide_or_protein) |
| `10.1073/pnas.182199699` | Mechanism by which 2,2,2-trifluoroethanol/water mixtures stab… | P3 | 2 | target=off; epsilon=none; temperature=true; oa=false; score=2; noise veto (biophysics_peptide_or_protein) |

## 7. 诚实边界与没读到的内容

- 标题/摘要级判断：没有读全文，也没有下载任何受限全文；本清单只用于决定“谁值得人工去读”。
- 化合物身份来自 Week 11 手工维护的 name/alias -> SMILES 表，加上本脚本补充的 3 个目标化合物（sulfolane / 3-methoxypropionitrile / HFE-347）。它只能回答“标题或摘要里点名了哪个分子”，不是从正文抽结构；泛指 glyme、类别名词、聚合物、盐、品牌名一律记为 unresolved。
- ε 线索只是“摘要里出现了介电措辞 + 一个合理数值”，不是测量值，也不区分“本文实测”与“引用文献值”。数值必须通过“不是化学式里的数字（G4、LiClO4）、不是配比（EC:EMC 3:7）、不带单位（4.3 V）”的过滤；日常实践中它仍会漏掉写成“ε 值约为某数”的句子，也可能误收对比句里的数字。
- 温度判定只认带单位的显式绝对温度（K/°C）。整句谈论 superheat / 温差的句子被整体丢弃，低于 60 K 的开尔文值也不算绝对温度，避免把“28 K 过热度”当成实测温度。只写 room temperature / ambient 的一律记为 unknown，不做 298 K 换算；false 的含义是“标题/摘要里出现的绝对温度全部在 253-333 K 之外”，不等于“正文里没有该窗口的数据”。
- OA 可得性以 Unpaywall 的 is_oa + best_oa_location 为准，再对该 OA 链接发一次 ≤ 8 KB 的范围 GET 取状态码，**响应体不保留**。reachable=true 只表示“匿名请求拿到 2xx、不是机器人校验页、也不是一片小于 20 KB 的 HTML 落地页”，不等于“全文可解析、能取到 ε 数值”；状态码 206 表示服务器支持 Range，看不到总大小。
- Unpaywall 说 is_oa=false 的条目没有探测 OA 链接，reachable 记为 false，含义是“不存在可匿名获取的 OA 全文”，不代表机构订阅也拿不到。
- API 失败按实际状态码/异常原文记录；本次运行碰到的 403 大多是出版商的 Cloudflare 拦截，匿名 UA 下无法区分“内容受保护”与“拒绝机器人访问”。
- 本支线只产线索清单，不建数据集、不建特征；任何受限值都没有进入本报告或产物文件。

### 7.1 摘要未读到的条目（5 条）

| DOI | 原因 |
|---|---|
| `10.1016/j.applthermaleng.2020.115862` | abstract not read: OpenAlex HTTP 200: no abstract_inverted_index; Crossref HTTP 200: no abstract field |
| `10.1016/j.electacta.2019.02.110` | abstract not read: OpenAlex HTTP 200: no abstract_inverted_index; Crossref HTTP 200: no abstract field |
| `10.1016/j.bpj.2017.12.013` | abstract not read: OpenAlex HTTP 200: no abstract_inverted_index; Crossref HTTP 200: no abstract field |
| `10.1529/biophysj.106.098715` | abstract not read: OpenAlex HTTP 200: no abstract_inverted_index; Crossref HTTP 200: no abstract field |
| `10.1023/b:ijot.0000034239.58332.be` | abstract not read: OpenAlex HTTP 200: no abstract_inverted_index; Crossref HTTP 200: no abstract field |

### 7.2 API 失败（24 条，展示前 60）

| 类型 | URL | 状态码 | 错误 |
|---|---|---|---|
| oa_probe | https://www.mdpi.com/2076-3417/14/2/495/pdf?version=1704460575 | 403 |  |
| oa_probe | https://doi.org/10.1063/5.0230695 | 403 |  |
| oa_probe | https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/app.56331 | 403 |  |
| oa_probe | https://doi.org/10.1002/anie.202416091 | 403 |  |
| oa_probe | https://pubs.rsc.org/en/content/articlepdf/2023/cp/d2cp05799a | 403 |  |
| oa_probe | https://pubs.rsc.org/en/content/articlepdf/2022/cp/d2cp03200g | 403 |  |
| oa_probe | https://doi.org/10.1021/jacs.2c07103 | 403 |  |
| oa_probe | https://zenodo.org/record/7801393 |  | ConnectionError: HTTPSConnectionPool(host='zenodo.org', port=443): Max retries exceeded w… |
| oa_probe | https://www.sciencedirect.com/science/article/pii/S2590159122000176/pdf | 403 |  |
| oa_probe | https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/eem2.12494 | 403 |  |
| oa_probe | https://www.mdpi.com/2079-4991/11/12/3216/pdf?version=1638350429 | 403 |  |
| oa_probe | https://www.osti.gov/servlets/purl/1630283 |  | ConnectTimeout: HTTPSConnectionPool(host='www.osti.gov', port=443): Max retries exceeded … |
| oa_probe | https://www.sciencedirect.com/science/article/am/pii/S1359431120333445 | 403 |  |
| oa_probe | https://doi.org/10.1049/hve.2019.0144 | 403 |  |
| oa_probe | http://www.cell.com/article/S0006349517350932/pdf | 403 |  |
| oa_probe | https://aip.scitation.org/doi/pdf/10.1063/1.4913320 | 403 |  |
| oa_probe | https://doi.org/10.1021/acs.jpcc.5b09380 | 403 |  |
| oa_probe | https://www.osti.gov/servlets/purl/1238653 |  | ConnectTimeout: HTTPSConnectionPool(host='www.osti.gov', port=443): Max retries exceeded … |
| oa_probe | https://aip.scitation.org/doi/pdf/10.1063/1.4867095 | 403 |  |
| oa_probe | https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/2014WR015291 | 403 |  |
| oa_probe | https://pubs.aip.org/aip/jcp/article-pdf/doi/10.1063/1.4740236/14080820/064508_1_online.p… | 403 |  |
| oa_probe | https://www.ncbi.nlm.nih.gov/pmc/articles/2717614 | 403 |  |
| oa_probe | http://hdl.handle.net/11380/613299 | 403 |  |
| oa_probe | https://www.ncbi.nlm.nih.gov/pmc/articles/129418 | 403 |  |

## 8. 复现

```
.\.venv\Scripts\python.exe probes\al_round3_oa_triage.py --offline   # \u96f6\u8bf7\u6c42\uff0c\u53ea\u9a8c\u5206\u6790/\u5206\u7ea7\u94fe\u8def
.\.venv\Scripts\python.exe probes\al_round3_oa_triage.py             # \u771f\u5b9e\u8054\u7f51\uff0cOpenAlex + Unpaywall + \u53ef\u9009 Crossref
```

离线模式不发任何请求：分析列照算，只是各个 API 列写成 `offline` / `unknown`，不会编造摘要、也不会编造 OA 状态。
