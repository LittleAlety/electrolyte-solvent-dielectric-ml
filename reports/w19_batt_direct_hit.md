# W19-1 步骤 1 剩余开口：Batt-P30K 直接命中核查（D2）

只读复核：不拟合模型（models_fitted = 0）、不产 R2/MAE、不动任何冻结件、不引用 Reaxys 数值。

## 1. 直接命中

| 读数 | 命中 | 分母 | 比率 |
| --- | --- | --- | --- |
| 逐字 SMILES 相等 | 77 | 246 | 0.313008 |
| RDKit 规范化（主读数 = InChIKey 全 27 位） | 78 | 246 | 0.317073 |
| 最宽阶梯（去盐去电荷后取骨架前 14 位） | 78 | 246 | 0.317073 |

主读数用的是与第 28.17 节 Batt 键**同一配方**（裸 RDKit MolFromSmiles -> MolToInchiKey，取全 27 位），因此与既有 registry / 锚点可直接对齐；逐级配方写在 summary 的 normalization_recipe。

## 2. 阶梯（逐级累计命中）

| 阶梯 | 累计命中 |
| --- | --- |
| verbatim_raw_smiles | 77 |
| rdkit_canonical_smiles_isomeric_true | 78 |
| inchikey_full_27_bare_rdkit | 78 |
| inchikey_skeleton_14_bare_rdkit | 78 |
| inchikey_full_27_desalted_uncharged | 78 |
| inchikey_skeleton_14_desalted_uncharged | 78 |

## 3. 分母发现（计划书写 239 / 76，磁盘实测 246 / 77）

磁盘 data/dielectric_v03.csv 实测 246 行、唯一 InChIKey 246 个；逐字命中 77、规范化命中 78。计划书写的 239 / 76 两个数都对不上——这是**分母口径分歧**，不是数据变化（该文件是冻结件，本次未改一个字节）。

## 4. 与第 28.17 节 n = 111 配对锚点的包含关系

- 锚点定义：orbital_second_source_layer.csv 中 role == paired_anchor 且 batt_homo_eV 非空的行；总数 111。
- 锚点落在 Batt 键全集里：111 / 111（子集判定 True） → 两条链的身份配方一致，这一点成立。
- 锚点落在冻结 eps 名册里：75 / 111；落在逐字命中键集里：75；落在规范化命中键集里：75（骨架口径 111）。
- **111 是否为本轮命中集的子集：False**。

两个集合的宇宙不同，不能直接说谁包含谁：111 锚点的分母是 PubChemQC 抓取窗口内、恰好也落在 four_core_key_registry 的 has_orbitals 键上的分子（全 Batt 池 29,519 键 + 名册外分子），不限于 eps 名册；本轮命中集的分母是冻结 eps 名册的 246 行。真正有意义的核对是三条：锚点是否落在 Batt 键全集里（配方一致性检验）、锚点有多少落在 eps 名册里、以及名册命中集与锚点集的交并。

补充：本轮名册命中集共 78 个键，其中 3 个不在锚点集内；111 锚点里有 36 个根本不在这份 eps 名册里。

## 5. 与 four_core_key_registry 的配方交叉核对

- registry 的 has_orbitals 键数：29868；其中能在 Batt 里找到：29519。
- 本轮 Batt 键集是否全在 registry 轨道键里：True。

## 6. 边界

- 只统计「名册直接落在 Batt-P30K 里」的键数；命中不等于拿到 Batt 级 HOMO/LUMO 估计，更不等于过第 28.17 节的 cross-level 标定门。
- 计划书写名册 239 行；磁盘上 data/dielectric_v03.csv 实测 246 行。本件按磁盘实测口径报数，并把差异登记在案，不静默改用 239。
- 前 14 位骨架读数只作敏感性上界：它会抹掉质子化/立体差异，不得当主读数引用。
- 本件不引用任何 Reaxys 数值，无受限值进入任何交付层。
