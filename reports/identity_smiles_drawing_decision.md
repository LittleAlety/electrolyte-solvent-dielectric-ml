# 身份层画法差异：机械溯源与「不改写」裁决建议

**任务**：`identity_smiles_drawing_decision` ｜ **生成时刻**：2026-09-26T10:18:07Z ｜ **网络调用**：0 ｜ **拟合模型**：0 ｜ **产出 R²**：无（false）

**结论（建议，非裁决）**：`recommended_no_rewrite_awaiting_human_confirmation`；不改写本地 SMILES，保留从来源复制来的原串

## 1. 事实底座

| 项 | 数 |
|---|---|
| 身份层行数 | 314 |
| SMILES 相同 | 299 |
| SMILES 不同（合计） | 15 |
| 其中仅立体层（ConnectivitySMILES 假警报） | 10 |
| 其中看似结构层（本报告对象） | 5 |
| 本地串落在**冻结件**里 | 4 |
| 本地串落在派生表里 | 1 |
| 本地串由身份层自己撰写 | 0 |

## 2. 五条逐条

| InChIKey | 名称 | 本地 SMILES | PubChem SMILES | 本地串出处 | 出处性质 | identity_check |
|---|---|---|---|---|---|---|
| `FSXANJBLYFVXEU-UHFFFAOYSA-N` | 1-methyl-3-octylimidazolium bromide | `CCCCCCCCN1CN(C=C1)C.Br` | `CCCCCCCCN1C[NH+](C=C1)C.[Br-]` | data/processed/ilthermo_new_compounds.csv | derived_table | roundtrip_match |
| `LBHLGZNUPKUZJC-UHFFFAOYSA-N` | 1-butyl-1-methylpyrrolidinium dicyanamide | `CCCC[N+]1(C)CCCC1.N#C[N-]C#N` | `CCCC[N+]1(CCCC1)C.C(=[N-])=NC#N` | data/dielectric_v03.csv, data/processed/ilthermo_new_compounds.csv | frozen_red_line | roundtrip_match |
| `OHLUUHNLEMFGTQ-UHFFFAOYSA-N` | N-methylacetamide | `CN=C(C)O` | `CC(=O)NC` | data/dielectric_v03.csv | frozen_red_line | roundtrip_match |
| `OOKUTCYPKPJYFV-UHFFFAOYSA-N` | 1-methylimidazolium bromide | `Br.Cn1ccnc1` | `C[N+]1=CNC=C1.[Br-]` | data/dielectric_v03.csv | frozen_red_line | roundtrip_match |
| `ZHNUHDYFZUAESO-UHFFFAOYSA-N` | formamide | `N=CO` | `C(=O)N` | data/dielectric_v03.csv | frozen_red_line | roundtrip_match |

## 3. 五道门

| 门 | 含义 | 实测 | 期望 | 判定 |
|---|---|---|---|---|
| `A_identity_identical` | 五对全部共用一个 InChIKey，且 identity_check == roundtrip_match | 5 | 5 | 通过 |
| `B_copied_never_authored` | 每条本地串都是某个声明来源文件里的逐字节子串（即身份层只复制、不撰写） | 5 | 5 | 通过 |
| `C_frozen_sources_still_carry_the_string` | 冻结名册仍逐字携带五条中的四条 | 4 | 4 | 通过 |
| `D_nothing_rewritten` | 本探针不写任何 data/ 文件，六件冻结件 digest 逐位复现 | 6 条冻结件（全 INTACT） | 6 | 通过 |
| `E_drawing_form_feeds_geometry` | 这些键携带几何派生特征，故画法不是装饰性的：就地改写 SMILES 会静默移动它们的物性特征，除非同步重生特征表 | 4 | 4 | 通过 |

## 4. 裁决建议与理由

- 五对全部身份同一：InChIKey 未变，而 InChIKey 正是下游一切联表所用的键（名册 246 + lowfreq 50 + ilthermo 47 = 314），所以改写既不移动任何联表、也不改变身份
- 五条本地串里有四条落在冻结红线 data/dielectric_v03.csv 内，第五条落在 data/processed/ilthermo_new_compounds.csv 内；身份层只是逐字复制它们，所以就地改写要么打破冻结 digest、要么在生成器下次运行时被静默还原
- 这些差异正是标准 InChI 有意归一化的类别（盐 vs 电中性、酰胺 vs 亚胺酸），外加一处环支链顺序，所以本地串没有丢任何「键仍然保留」的信息
- 五条键里有四条携带几何派生特征，所以改写不是一次文本编辑，而是一次迁移：它要求同步重生那些特征表并出新冻结版本，而不是就地改字

**若作者仍要改写**：请走版本化迁移：出新的冻结表，并在同一次变更里重生特征表，再重跑身份层，让本探针保持全绿、并把台账里的 pin 一并更新

**几何派生特征涉及的键**（4 个）：LBHLGZNUPKUZJC-UHFFFAOYSA-N, OHLUUHNLEMFGTQ-UHFFFAOYSA-N, OOKUTCYPKPJYFV-UHFFFAOYSA-N, ZHNUHDYFZUAESO-UHFFFAOYSA-N

## 5. 边界与已知未核

- 这里证明的是身份同一，描述符是否同一未测：五对里有四对差在电荷分离或互变异构选择上，即便标准 InChIKey 相同，这仍可能移动 RDKit 与几何描述符
- FSXANJBLYFVXEU 这条还带着已登记的 CID 冲突（本地 ILThermo 表记 60196376、PubChem 记 57351531），那是另一笔缺陷，本探针不碰它
- 那十条「仅立体层」是 ConnectivitySMILES 回退的假警报，不是画法差异，不在本次裁决范围内

## 6. 复现

    .\.venv\Scripts\python.exe probes\identity_smiles_drawing_decision.py
    .\.venv\Scripts\python.exe probes\identity_smiles_drawing_decision.py --check

