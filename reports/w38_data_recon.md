# W38-D 数据侦察报告：四核心量的新来源核实 + 渠道红线登记

- 生成件：probes/w38_data_recon.py（可复算；本文件由它写出）
- 名册分母：data/processed/dielectric_physical_features_v03.csv，241 行 / 241 个唯一 InChIKey
- 口径：四核心量 = 静态介电常数 eps / 粘度 eta / HOMO-LUMO 轨道能 / 氧化-还原电位
- 红线：第三方数值不入池、不入特征、不入交付物；NC / ND / 专有 / 未知一律不入池
- 记账：本件为后验读数与治理登记，**不占 shot**（累计仍 19）

## 0. 一句话结论

本轮**没有在既有可商用线之外找到新的 eps / eta 标签源**：eta 覆盖最高的那一件是 CC BY-NC 4.0（不得入商用池），而 eps 的唯一可商用候选是 GPL-2.0 的零频汇编。真正的新增量在**轨道能**一侧——HF 镜像上出现了 CC-BY-4.0 的 PubChemQC 副本。

## 1. 名册命中实测（本地件）

| 件 | 许可 | 可入池 | 本轮新增 | 行数 | 唯一 InChIKey | 名册命中 / 241 |
| --- | --- | --- | --- | --- | --- | --- |
| batt_p30k | MIT | 是 | 否（已在库） | 29519 | 29519 | 73 (30.3%) |
| batt_slm_smi | MIT | 是 | 否（已在库） | 115756 | 115756 | 79 (32.8%) |
| batt_slm_rx392 | MIT | 是 | 否（已在库） | 392 | 392 | 10 (4.1%) |
| batt_slm_cpi_features | MIT | 是 | 是 | 87 | 87 | 26 (10.8%) |
| batt_slm_cpi_features_nof | MIT | 是 | 是 | 46 | 46 | 23 (9.5%) |
| solvfunc_87 | MIT | 是 | 否（已在库） | 87 | 87 | 26 (10.8%) |
| chew_viscosity_supp2 | CC BY-NC 4.0 | 否 | 否（已在库） | 3582 | 957 | 140 (58.1%) |
| chew_viscosity_supp3 | CC BY-NC 4.0 | 否 | 否（已在库） | 650 | 50 | 24 (10.0%) |
| chodera_dielectric | GPL-2.0 | 是 | 否（已在库） | 246 | 45 | 45 (18.7%) |

## 2. 渠道红线登记

| 渠道 | 许可 | 类别 | 含四核心量 | 含轨道能 | 可达性 | 可入池 | 证据级别 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| reaxys | proprietary / subscription | proprietary | 四核心量（作为文献索引可得） | 否 | 本机 Edge 可达（已登录） | 否 | 实测 |
| hf_mirror | 镜像站（内容许可随各数据集） | n/a | 取决于数据集 | 否 | HTTP 200，API 可用 | 是 | 实测 |
| colabfit_omol25_train | CC-BY-4.0 | permissive | 能量 + 原子力（**无 HOMO/LUMO**） | 否 | HTTP 200 | 是 | 实测 |
| molssiai_pubchemqc_b3lyp | CC-BY-4.0 | permissive | HOMO/LUMO/gap + orbital-energies | 是 | HTTP 200 | 是 | 文档 |
| molssiai_pubchemqc_pm6 | CC-BY-4.0 | permissive | HOMO/LUMO/gap | 是 | HTTP 200 | 是 | 文档 |
| qm9_original | CC BY 4.0 | permissive | homo / lumo / gap（B3LYP/6-31G(2df,p)） | 是 | DataCite 元数据可达 | 是 | 文档 |
| batt_p30k_channel | MIT | permissive | HOMO/LUMO/gap + IP/EA + dipole + 3D 坐标 | 是 | api.github.com 可达 | 是 | 实测 |
| qmugs | CC BY-NC-SA 4.0 | NC | HOMO/LUMO 等 | 是 | 原始在 Zenodo，本机 DNS 不可达 | 否 | 文档 |
| themol | CC BY-NC 4.0 | NC | DFT 能量/Hessian/扭转（非四核心量） | 否 | HTTP 200 | 否 | 实测 |
| molssiai_liquid_electrolytes | CC BY-NC-ND 4.0 | NC | 电解质分子性质 | 否 | HTTP 200 | 否 | 文档 |
| nist_webbook | All rights reserved（Standard Reference Data Act） | proprietary | IE/EA（HOMO/LUMO 代理）；**无 eps / 无 eta / 无氧化还原电位** | 否 | HTTP 200 | 否 | 实测 |
| ddbst | proprietary（订阅/买断） | proprietary | eta + eps（DDB 内） | 否 | HTTP 200 | 否 | 实测 |
| chemeo | proprietary + sui generis 数据库权 | proprietary | eta（36,765 条）+ eps（仅 46 条）+ IE/EA | 否 | HTTP 200 | 否 | 实测 |
| mnsol | 学术免费 / 商业 6000 USD 授权 | restricted | 溶剂化自由能（**非四核心量**） | 否 | HTTP 200 | 否 | 实测 |
| pubchemqc_riken | CC BY 4.0（论文声明） | permissive | HOMO/LUMO | 是 | 本机 DNS 不可达 | 是 | 文档 |
| zenodo | 随各条目 | unknown | 多个上游的全量归档 | 否 | 本机 DNS 不可达 | 否 | 实测 |

## 3. 判据

| id | 判据 | 读数 | 门槛 | 判定 |
| --- | --- | --- | --- | --- |
| H38d1 | 名册分母 = 241 行且唯一 InChIKey 亦为 241（分母口径锁死） | 241.0 | 241.0 | 成立 |
| H38d2 | MIT 轨道源 Batt-P30K 的名册命中 >= 70（可商用轨道线仍在） | 73.0 | 70.0 | 成立 |
| H38d3 | eta 覆盖最高件（chew 2024 supp2）名册命中 >= 140 | 140.0 | 140.0 | 成立 |
| H38d4 | 三份「已在库」的 Batt-SLM 附属件与上游 git blob sha256 逐字节相等（不算新源） | 3.0 | 3.0 | 成立 |
| H38d5 | 本轮真新增文件 = 2（CPI Features / Features-NoF）且均为 MIT | 2.0 | 2.0 | 成立 |
| H38d6 | 渠道表自洽：任何 can_enter_pool 的渠道，其许可类别必须是 permissive / n/a | 0.0 | 0.0 | 成立 |
| H38d7 | 除 Batt-P30K 外，仍存在 >= 2 条「含 HOMO/LUMO 且许可可商用」的渠道 | 5.0 | 2.0 | 成立 |
| H38d8 | OMol25 不含轨道能（properties = energy + atomic forces）⇒ 不能当 HOMO/LUMO 源 | 1.0 | 1.0 | 成立 |
| H38d9 | 红线渠道（NC / 专有 / 受限）已被显式登记且全部 can_enter_pool = false | 0.0 | 0.0 | 成立 |

## 4. 逐件备注

- batt_p30k：ωB97X-V 气相单分子 + SMD 隐式溶剂，与本地 xTB 单点不同层级；跨层级映射必须走既有标定门。
- batt_slm_smi：只值「候选新化合物的分母」，不是标签源。
- batt_slm_rx392：381/392 行同一层级串；介质设定以 UniqueSolvents 的 DIELECTRIC=18.5 为主，引用必须带条件声明。
- batt_slm_cpi_features：本轮**真新增**。比 SolvFunc-87 多 4 列；列义未独立验证。
- batt_slm_cpi_features_nof：本轮**真新增**；46 行。
- solvfunc_87：所有 *_Pred 列都是模型输出，**只能作外部对照，不入标签池**。
- chew_viscosity_supp2：全项目 eta 覆盖最高（140/241），但**NC ⇒ 不得入商用池**。文章正文的 CC BY 4.0 被 Data availability 单独声明的 NC 覆盖。
- chew_viscosity_supp3：列名带 _pred 且含 is_within_training ⇒ 跨模型对照件，不入标签池。
- chodera_dielectric：可商用但带 copyleft 义务；且是「零频 eps」，与近静态 eps 口径需对齐。数值上游为 NIST ThermoML 档案。

## 5. 渠道备注

- reaxys：本轮用它做**文献索引**（取 DOI），未读入任何数值。红线：数值不入任何池/特征/交付物。
- hf_mirror：本机 huggingface.co DNS 不可达，此镜像为当前唯一稳定 HF 入口。
- colabfit_omol25_train：101,666,280 构型；README Properties included = 「energy, atomic forces」⇒ 不是轨道源。
- molssiai_pubchemqc_b3lyp：README 字段表 + 抽样 JSON 命中 energy-alpha-homo/lumo/gap；全量约 7.7 TB。许可与论文（10.1021/acs.jcim.3c00899）一致。
- molssiai_pubchemqc_pm6：2.21 亿次计算；全量约 8.4 TB。
- qm9_original：133,885 分子；DataCite rightsList = CC BY 4.0。注意：HF 上的第三方镜像卡片**自身无 license 字段**，应从原始源取数。
- batt_p30k_channel：29,519 分子；ωB97X-V/def2-TZVPPD/SMD(eps=18.5)。本仓已在用。
- qmugs：**红线**：NC + SA。HF 上的派生镜像许可与原始冲突，不采信。
- themol：**红线**：NC。只留 data/raw/。
- molssiai_liquid_electrolytes：**红线**：NC + ND（禁改作）。
- nist_webbook：免费浏览 ≠ 开放许可；再分发/批量入池需走 NIST SRD 授权。
- ddbst：条款原文禁止保存/下载/系统性抓取建库。**红线**。
- chemeo：条款原文禁止整库下载/爬取与整体嵌入产品。**红线**。
- mnsol：含未发表材料；商业需付费。既不覆盖四核心量，商用入池亦为红线。
- pubchemqc_riken：内容 CC BY 4.0，但站点本机不可达；改走 MolSSI AI-Hub 镜像。
- zenodo：环境受阻 ≠ 源不存在；换出口后可再评。

## 6. 边界与不做的清单

- 所有命中数都是实测集合交（RDKit 全 27 位 InChIKey），没有一个是估计值。
- 分母统一 241 行；既有报告的 246 / 247 行是 data/dielectric_v03.csv 口径，两者不得混引。
- 所有 *_Pred 列（HOMO_Pred / DC_Pred / EdgePool_log(Viscosity)_pred）都是模型输出，只能作外部对照，不入标签池。
- 未下载任何第三方大文件到仓库；未把任何第三方数值写进池或特征列。
- 环境受阻（huggingface.co / zenodo.org / pubchemqc.riken.jp 在本机 DNS 不可达）登记为「受阻」，不登记为「源不存在」。
