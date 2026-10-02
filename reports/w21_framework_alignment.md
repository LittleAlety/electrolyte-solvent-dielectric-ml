# W21 Tier 1：v2 框架原文入库与槽位接口三表

本件不拟合任何模型、不联网、不动任何冻结件；只把已经做出来的资产按《Understanding Electrolyte Materials through Decision-Centric Ranking Stability》(v2) 的槽位重新编址。

## 1. 框架原文入库（逐字节）

- 来源：`E:\Claude Code\电解液溶剂-HB\核心文件\ranking-electrolyte-materials-v2.md`
- 落点：`docs/framework/ranking-electrolyte-materials-v2.md`
- sha256：`e55c1b07a127ef7d0bb2f25302ac39f0640f24f45c0547bb482a63b1f4f17c0e`（54147 B / 1779 行 / 32 个一级章节）
- 逐字节一致：`True`

## 2. 特征成本分级（框架 §11）

| cost level | 条数 | 含义 |
| --- | --- | --- |
| X0 | 9 | query 前即可得（结构、RDKit、xTB 代理量） |
| X1 | 2 | free-molecule DFT 之后可得 |
| X2 | 1 | Li 配合物 DFT 之后可得 |
| reference | 4 | 外部参考层（§3.3），不是标签源 |
| target | 2 | 本仓要预测的实验标签（§18 不许塞进单一综合分） |

完整表：`probes/artifacts/w21_feature_cost_map.csv`（sha256 `ede0e725bee50e3f1fe06add4ee17182aea650ab3c83103e55e47a2857637eca`）。

**X2 是空的**：本仓没有做任何 Li⁺ 配位计算，因此框架 §11.3 的一整层在本仓不存在——这不是遗漏，是边界，§2 槽位表里如实登记为「未执行」。

## 3. 多轴 chemical-space metadata（框架 §5.2）

- 行数：**246**（去重键 246）
- 主家族分布：`{"alcohol": 52, "other": 47, "ether": 31, "aromatic_hydrocarbon": 29, "ionic_liquid_or_salt": 21, "nitrile": 16, "ester": 15, "halogenated": 14, "amine": 6, "amide": 3, "cyclic_carbonate": 3, "linear_carbonate": 3, "phosphate": 2, "sulfoxide": 2, "sulfone": 1, "water": 1}`
- 角色分布：`{"state_of_the_art_solvent": 15, "background_candidate": 231}`
- 无 xTB 特征的登记行：9
- 仓内**不存在**的字段（如实留空而非编造）：`conformer_count, Li_motif_count, state_identity_status, reactivity_status`

## 4. Stage 0 / Stage 1 判词（框架 §19）

| gate | 条目 | 判词 | 依据 |
| --- | --- | --- | --- |
| S0-1 | 确定 core set 与 broad pool | **成立** | epsilon 名册 246 / 建模集 236；轨道可核主臂 n=49；eta 4,151 行 / 976 键 |
| S0-2 | 建立 structural_family / functionalization_tags / use_role | **成立** | 本件新建，246/246 全覆盖（互斥主家族 + 多选标签 + 角色） |
| S0-4 | 定义 oxidation/reduction quantity 与方向 | **部分成立** | 轨道通道按 §4.1 约定（P_0^ox=-HOMO, P_0^red=LUMO）；排序键 v1 仍把两方向混在一条键里 -> 待拆 |
| S0-5 | 冻结 common embedding 的物理含义 | **成立** | P_0 = GFN2-xTB 气相单点（THEMol B3LYP-D3(BJ)/DZVP 几何）；R_sol = wB97X-V/def2-TZVPPD/SMD(eps=18.5) |
| S0-6 | 预注册 k/N = 10%,20%,30% | **成立** | 本件预注册 k=5/10/15（n=49） |
| S0-7 | 预注册 robust-pair tolerance 的确定方法 | **成立** | 本件预注册：delta 由留一残差与 bootstrap 共同决定 |
| S0-8 | 冻结 reference ligand R | **未执行** | 本仓不做 Li+ 配位，故无 R |
| S0-9 | 冻结 external anchor 搜集规则 | **成立** | 四角色 sidecar（primary_reference / calibrated_estimate / reference_only）+ 许可分级 |
| S1-1 | 选 8-10 个 method-audit molecules | **未执行** | 本仓无 DFT 方法审计；轨道层为 xTB 单点 + 外部源交叉核对 |
| S1-2 | 比较 functionals / basis / diffuse treatment | **未执行** | 同上 |
| S1-4 | 建立 gas-phase external anchors | **部分成立** | pubchemqc 第二源（B3LYP/6-31G*//PM6, 801+111 行）已入 sidecar；Batt 为 SMD 溶剂化层，不是气相锚 |
| S1-5 | 搜集 solution redox anchor subset | **成立** | RX-392 392 行，含显式溶剂清单 |
| S1-6 | 比较 absolute error 与 rank stability | **成立** | w19_batt_gap_crosscheck：homo r=0.8223 / rho=0.8640 / 留一 MAE 0.3475 eV（常数基线 0.7383） |
| S1-7 | 冻结 production protocol | **部分成立** | GFN2-xTB 6.7.1pre 已冻结并跑了全名册；DFT production protocol 不存在 |

- Gate 0：成立（本件不改动任何已冻结定义）
- Gate 1：NOT CLOSED（本仓不跑 DFT 批量计算，框架不禁止本仓工作）

## 5. 边界

- 不拟合、不联网、不写任何池；新增文件只有三张表 + 框架副本 + 本摘要。
- 不引用 Reaxys 数值；不把 Batt 参考层当标签源。
- 框架原文**不进** `data/`，也不参与任何训练。
