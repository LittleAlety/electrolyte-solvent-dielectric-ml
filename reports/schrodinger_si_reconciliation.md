# T2 对账：存量黏度表 vs Schrödinger 2024 开放 SI（Week 15）

- 探针：`probes/schrodinger_si_reconciliation.py`
- 机读汇总：`probes/schrodinger_si_reconciliation_summary.json`
- 复现命令：`.\.venv\Scripts\python.exe probes\schrodinger_si_reconciliation.py`
- 网络访问：无。冻结数据集写入：无。建模：无。

## 数据来源

| 项 | 路径 | 实测规模 | sha256（LF 归一化） |
|---|---|---|---|
| 存量黏度表（v0.x 输入） | `data/viscosity_v01.csv` | 3,582 行 / 14 列 / 957 InChIKey | `12dfa03f34284c93204d1054f75b5a342fd82094da0ca17cee372b4c581c5b26` |
| Schrödinger 补充材料 2（实验） | `data/external/chew_2024_viscosity_supp_2.csv` | 3,582 行 / 16 列 | `8a8cb6810779d305922b25be1ea507f7de60a5eafec8ef8584571f32553d8fa0` |
| Schrödinger 补充材料 3（预测） | `data/external/chew_2024_viscosity_supp_3.csv` | 650 行 / 7 列 / 50 SMILES | `48435a88214fbd441aca8e48923a8b2aee0994816b03ce0bfe1933266e6f4795` |

出处 DOI：`10.1186/s13321-024-00820-5`（Chew et al., *J. Cheminform.* 2024）。两个补充材料是**只读输入**，本探针不修改它们。

## 方法

1. 按**行序**拉链对齐两份 3,582 行的表（不做集合运算、不做排序）。
2. 逐行比对 4 个可对齐字段：`T_K ↔ Temperature (K)`、`viscosity_cP ↔ Viscosity (cP)`（数值，绝对容差 **1e-9**）、`name ↔ Name`、`smiles ↔ CANON_SMILES`（字符串精确）。
3. 记录逐列不一致计数与前 10 条不一致样例；行数差单列记录。
4. **与逐行比对相互独立的第二种比对**：多重集比对——对每行取 4 个对齐字段的原始单元格，两侧分别排序后逐项比对（不依赖行序）。存量表本就由该补充材料生成，同源必然同序，所以行序一致**不构成证据**，证据是「逐行 + 多重集」双重比对。
5. 附加内部一致性检查：存量表的 `viscosity_Pa_s × 1000` 是否等于 `viscosity_cP`；`record_id` / `Index` 是否从 0 起顺序编号（这只是两侧各自的编号性质，**不作为**「同一份文件」的证据）。
6. 对 `supp_3` 的硬边界改成**测量**：真的去读两张实验表（`data/viscosity_v01.csv`、`data/processed/viscosity_observations_thermoml.csv`），按 `data_status=predicted` 或预测列计数，结果为 0；`merge_forbidden=True` 是**设计声明**（本探针没有写入实验表的代码路径），并在汇总里标为 `design_declaration_not_measurement`。
7. 幂等性：去掉 `generated_at_utc` 后连续两次运行逐键一致。

## 读数

### 验收值对账（侦察预期 vs 本次实测）

| 指标 | 侦察预期 | 实测 | 判定 |
|---|---:|---:|---|
| `row_aligned_matches` | 3,582 | 3,582 | match |
| `mismatches` | 0 | 0 | match |
| `unique_keys` | 957 | 957 | match |
| `source_doi_set` | `{10.1186/s13321-024-00820-5}` | 单元素集合，等于该 DOI | match |

### 明细

- **逐行、逐列全等**：3,582/3,582 行匹配；逐列不一致数 `T_K = 0`、`viscosity_cP = 0`、`name = 0`、`smiles = 0`；不一致样例列表为空；两侧行数差为 0。**附录 Z-2 的「关键待核实假设」升级为已核实事实。**
- **逐行 + 多重集双重比对**：除逐行比对外，还做了**与行序无关的多重集比对**（每行取 4 个对齐字段的原始单元格，两侧分别排序后逐项比对），`multiset_matches = True`。
- **行序一致不作为证据**：`supp_2.Index` 与 `viscosity_v01.record_id` 各自都是 0…3581 的顺序编号（`index_is_sequential = True`），但这只是两侧各自的编号性质——存量表本就由该补充材料生成，同源必然同序。
- **DOI 唯一**：存量表 3,582 行的 `source_doi` 只有一个取值。
- **内部一致**：3,582 行的 `viscosity_Pa_s × 1000 == viscosity_cP`（容差内）全部成立；`data_status` 全为 `experimental`，**没有任何 predicted 行混入**。
- **`supp_3` 是预测，已隔离**：
  - 650 行 / 50 个溶剂；含 `EdgePool_log(Viscosity)_pred` 列，**100% 的行都有该列**；
  - `is_within_training` = False 403 行 / True 247 行；
  - 与 `supp_2` 只共享 19 个 SMILES；
  - `data_status = predicted`；**并入检查是测量而非字面量**：真的去读 `data/viscosity_v01.csv`（3,582 行）与 `data/processed/viscosity_observations_thermoml.csv`（2,725 行）两张实验表，按 `data_status=predicted` 或预测列计数 → `predicted_rows_found = 0`，即 `rows_merged_into_experimental_table = 0`。
  - `merge_forbidden = True` 是**设计声明**（本探针没有写入实验表的代码路径），汇总里标为 `merge_forbidden_kind = design_declaration_not_measurement`。
- **受限部分照实登记**：论文原始数据 4,440 点，公开子集 3,582 点，**差额 858 点**按要求保留为「声称的受限量」。

## 边界（不许省略）

1. **表内对账 ≠ 官方字节对账**。本地没有 Schrödinger 官方发布的校验和/清单，所以本报告证明的是「存量表与本地保存的 supp_2 逐行一致」，不能证明「与出版社官网字节一致」。
2. **逐行同一 ≠ 开放子集本身无误**。两份表可能是同一个抄录错误的两次复制；原始数值的正确性必须回到 Schrödinger 论文及其引用的原始文献才能判定。
3. **858 条受限记录不得绕版权获取**。它们被作者以版权原因保留，既不得爬取、不得从第三方镜像补齐，也不得用来推测其内容或把它计入本地语料规模。开放子集（`supp_2`）的再利用须遵守其许可并注明出处 `10.1186/s13321-024-00820-5`。
4. **4,440 是声称值**，来自论文/手册；本地只有开放子集，因此 858 是「声称的差额」，不是本地可复算的观测数。
5. **`supp_3` 永远不进实验表**。它是 EdgePool 的模型预测，`is_within_training=True` 的 247 行更是训练集内的自预测；它们不能用于拟合、不能用于评估、不能进入任何可发表层。本对账把它们排除在 `row_aligned_matches` 之外。
6. **本仓已有联合表不是可用的联合观测表**。`data/processed/dielectric_viscosity_intersection.csv`（456 行 / 46 keys）是 Week 3 的 loose join，`pair_type=loose_join`、`model_ready=false`，`exact_temperature_match` 只有 119/456；它不能当作 ηε-joint 的现成骨架。
7. **本轮不建模**。本探针不改评分池、不训练模型、不把任何值写进冻结数据集；黏度线此前的诚实口径（观测级 + GroupKFold by InChIKey）继续适用于后续训练，`random_row` 结果只能作泄漏参照。
