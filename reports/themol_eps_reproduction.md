# THEMol ε 名册 GFN2 轨道：链路 A × 链路 B 复现交叉校验

**一句话结论：两条独立链路互相复现。** 在 51 个共同 InChIKey、47 个可比分子上，链条 A 减链条 B 的全部差值都落在打印精度的最后一位（HOMO/LUMO 上界 1×10⁻⁴ eV，gap 上界 2×10⁻⁴ eV），UUID 与分子名一致率均为 100%。唯一需要上报的实质落差在覆盖面：链路 B 的文件名写着 eps142，实际三个分片 145 行、去重后只有 **51** 个 InChIKey。

## 一、两条链路与输入指纹

| 链路 | 产物 | 驱动 |
| --- | --- | --- |
| A（官方臂 W17-14） | `data/processed/themol_orbital_layer.csv` | `probes/themol_hessian_orbitals.py` 取 THEMol 的 Hessian 子集 → GFN2-xTB 单点 → `data/raw/themol/shard_*.csv` → `probes/build_themol_orbital_layer.py` 合成交付层 |
| B（临时并行臂） | `probes/themol_eps_reproduction_inputs/themol_eps142_shard{0,1,2}.csv` | 独立手写的驱动，同样在 THEMol 的 B3LYP-D3(BJ)/DZVP 几何上跑 GFN2-xTB 单点 |

两条链路的方法层级完全相同（GFN2-xTB // B3LYP-D3(BJ)/DZVP，气相单点），跑的是同一批 ε 名册分子，因此数值**应当**一致。本臂存在的意义就是把「应当」变成可审计的事实——包括它不成立时。

| 输入 | 行数 | 唯一键 | sha256 |
| --- | --- | --- | --- |
| `data/processed/themol_orbital_layer.csv`（链路 A） | 166 | 166 | `6e05f02e755c57ab09d73a784687b2c1deb757f80e43c5746358f1f7a5ecde80` |
| `probes/.../themol_eps142_shard0.csv` | 47 | — | `1c50c6c11358e59d511176628cc8e1c6bdae279e0fd0ac02676f73e7a1bff668` |
| `probes/.../themol_eps142_shard1.csv` | 51 | — | `b94fa37d9c319fd844b9c7c210361f9276857d00305cc4414fb4de0c1c74542d` |
| `probes/.../themol_eps142_shard2.csv` | 47 | — | `88b214fafc08e02c85d7f4bcf7dbb851153a1ff107f2cdadcc05b93400e38f09` |
| 链路 B 目录整体 digest | 145 | 51 | `ba622e4fbc198087d3d781aafa7ae86b3d408063c11518f3737cb168aeb18633` |

链路 B 的原始分片落在临时目录（CRLF 行尾）。固化进仓库时只做了 CRLF→LF 的行尾归一，字段内容逐字节不变；原始字节的 sha256 分别是 `587ec2bbf325efd44421edff6a0d861abfa4c0f75d753a752b7a9af126f8cc04`、`49d2a6b508a029b9e2ba1bd57d496e0da913c0b1fe59d9e6ae8153fdafc24b43`、`3e28b8b8fa390c4f2b9dc1cbae1309144a69041c9bd812acfa8f01897f8e946b`。不归一就不能进仓库：`.gitattributes` 会把 `*.csv` 规范化成 LF 提交，工作区留 CRLF 会让 `tests/test_repo_hygiene.py` 判红。

## 二、匹配计数

- 链路 A 键数 **166**（其中 ε 名册命中 142，锚名册命中 72；角色构成 `uncalibrated_reference` 92 + `paired_anchor` 74）
- 链路 B 键数 **51**（145 行去重后）
- `matched` = **51**，`only_in_A` = **115**，`only_in_B` = **0**

**链路 B 的每一个 InChIKey 都能在链路 A 里找到**，没有单边键；A 侧多出来的 115 个分子只是链路 B 这次没跑到，不是分歧。键全部为 14-10-1 标准 InChIKey 形状、后缀统一 `-UHFFFAOYSA-N`，并且逐字取自两个文件（`tests/test_themol_eps_reproduction.py` 用子串断言把这一点钉住了，没有任何手抄或由 SMILES 反推的键）。

51 个键里有 **47** 个双方都有数值，另外 4 个链路 B 侧全程打不开 HDF5 文件，按要求保留在键计数里、以空值出现，而不是被悄悄丢掉。

## 三、数值比对

`probes/themol_eps_reproduction_facts.csv` 逐分子记录 `chain_a_uuid / chain_b_uuid`、两侧原始字符串和 Δ = A − B。

| 通道 | 可比分子 | Δ = 0 | 最大 \|Δ\| | 平均 \|Δ\| | 超出打印精度 |
| --- | --- | --- | --- | --- | --- |
| HOMO | 47 | 39 | 1×10⁻⁴ eV | 1.70×10⁻⁵ eV | 0 |
| LUMO | 47 | 35 | 1×10⁻⁴ eV | 2.55×10⁻⁵ eV | 0 |
| gap | 47 | 34 | 2×10⁻⁴ eV | 2.98×10⁻⁵ eV | 1 |

gap 的上界是 2×10⁻⁴ 而不是 1×10⁻⁴，因为两侧的 gap 都是由各自打印到小数点后四位的 HOMO/LUMO 相减得到，两端各差一个末位就会叠加成两个末位。这是口径，不是失灵。

**最差的一对是碳酸乙烯酯（ethylene carbonate，`KMTRUDSVKNLOMY-UHFFFAOYSA-N`）**：A 记 HOMO −12.4189 / LUMO −6.4318 / gap 5.9871，B 记 −12.4188 / −6.4319 / 5.9869——两端各偏一个末位。这是整份比对里唯一一个 gap 差到 2×10⁻⁴ 的分子。

链路上还有一处口径说明：链路 A 交付层的 `gap_gfn2_eV` 存的是相减后的浮点数（例如 `3.737800000000001`），而链路 A 自己的原始 harvest 存的是打印值 `3.7378`。两者**数值完全相同**（166 行逐个比对，数值差 0），只有字符串长得不一样。事实表里两侧都按各自文件的字面值落盘，不做格式化，所以读者看到的原始值就是文件里的原始值。

## 四、偏差分布

把 47 个分子的三个通道合并成 141 个 |Δ| 值：

| \|Δ\| | 个数 | 占比 |
| --- | --- | --- |
| 0（逐位相同） | 108 | 76.6% |
| 1×10⁻⁴ eV（0.1 meV） | 32 | 22.7% |
| 2×10⁻⁴ eV（0.2 meV） | 1 | 0.7% |

也就是说四分之三的通道是**逐位相同**的，其余全部停在打印精度的最后一个数字上，没有任何一个值跳到 10⁻³ eV 量级。对 ε / η / HOMO-LUMO / 氧化还原这四个核心通道中的轨道通道而言，0.1–0.2 meV 完全落在噪声地板以下。

## 五、UUID 与分子名

- `chain_a_uuid` vs `chain_b_uuid`：**51 / 51 一致，一致率 100.0%，不一致清单为空**
- 分子名：51 / 51 与链路 A 相同，0 处分歧

这一点值得单独写出来。两边取的是同一个 THEMol `uuid`（32 位十六进制），说明两条链路索引到的是**同一个构象记录**，而不是同一分子的不同构象——如果 uuid 对不上，即使轨道能级碰巧吻合，比较的也是两个不同的几何。现在它全对上了，第三节的 Δ 才可以被解读为「同一几何、同一方法、两套驱动的差」。

## 六、链路 B 的覆盖面落差（必须上报）

链路 B 的文件名是 `themol_eps142_shard{0,1,2}.csv`，任务描述也按「142 数据行」转述。**实测不是。**

| 事实 | 数值 |
| --- | --- |
| 三个分片实际行数 | 145（47 + 51 + 47） |
| 去重后的唯一 InChIKey | **51** |
| 行数 − 键数 | 94 |
| 出现在多个分片里的键 | 47 |
| 键集完全相同的分片对 | `shard0` ≡ `shard2` |
| 只在单个分片出现的键 | 4（全在 `shard1`） |
| 分片之间内容不一致的键 | 7 |
| 完全没有能级值的分片行 | 13 |
| 全程打不开 HDF5 的键 | 4 |

三个分片不是三份互补的切片，而是**同一批分子的重复运行**：`shard0` 与 `shard2` 的键集完全相同（各自 47 个键），`shard1` 是它们的超集（51 个键，多出 4 个）。所以 145 行折叠成 51 个分子，而文件名承诺的 142 个从未落盘。

7 个键在分片之间不一致，形态全部是「某一分片写了 `ERR:KeyError(...)`、另一分片写出了数值」——即镜像 429 / HDF5 截断导致的**随机性失败**，不是数值分歧。分片日志 `shard*_out.txt` 末尾的 `open fail hessian_*.h5` 与之对应。

4 个全程无值的键（保留在事实表里，数值列为空、`chain_b_rc` 为错误文本）：

| InChIKey | 名称 |
| --- | --- |
| `CGZZMOTZOONQIA-UHFFFAOYSA-N` | cycloheptanone（环庚酮） |
| `QBELEDRHMPMKHP-UHFFFAOYSA-N` | 1-Bromo-2-chlorobenzene（1-溴-2-氯苯） |
| `SBLRHMKNNHXPHG-UHFFFAOYSA-N` | fluoroethylene carbonate（氟代碳酸乙烯酯） |
| `SWXVUIWOUIDPGS-UHFFFAOYSA-N` | 4-Hydroxy-4-methyl-2-pentanone（双丙酮醇） |

这 4 个分子链路 A 全都跑出来了，取数时可以直接用 A 侧。链路 B 的价值到此为止：它是**复现校验**，不是第二个数据源。

## 七、附带观察：链路 B 内部也不自洽

链路 B 自己还留着两份先后不同步的产物：

| 产物 | 时间戳 | 键数 | sha256 |
| --- | --- | --- | --- |
| `themol_eps142_homo_lumo.csv`（合并产物） | 01:45 | 48 | `78b749ca1ceb00e3722b4619f606e03731d5e8098849d8d2b1ed603e9ebc1157` |
| 三个分片（本比对采用的输入） | 03:45 | 51 | 见第一节 |

那份 01:45 的合并产物在**全部 48 个键的 HOMO/LUMO 上与链条 A 逐字相同**（gap 因浮点写法差异另计），却在自己 16 个键上与 03:45 的分片差 1×10⁻⁴ eV。也就是说：链路 B 内部两次运行之间的差、以及它与链条 A 之间的差，量级完全相同。

两套驱动都显式设了 `OMP_NUM_THREADS=1`（`resume.py` / `resume_shard.py` 第 80 / 83 行），所以线程数不是这 10⁻⁴ 的来源。真正的原因是「两次 GFN2 单点为什么会在末位上分岔」，本臂无法从现有材料判定（两次下载的 HDF5 几何是否逐字节相同、两套输出的解析路径是否一致，都没有留下记录）。**这一点留给 Peirce 澄清**，但不影响结论：10⁻⁴ eV 是这套环境里两次独立运行的复现精度，而不是某一侧的实现缺陷。

## 八、这说明了什么

1. **W17-14 的链路 A 数值经得起独立复现。** 一条完全独立手写的驱动，在同一批分子上把 HOMO/LUMO 复现到 100% 逐位或末位相同，说明交付层里的 GFN2 轨道数不是解析或单位换算的产物。
2. **该结论有明确的作用域。** 它验证的是**路径可复现**，不是**方法准确**。GFN2-xTB 对 wB97X-V 的偏差另有量级（W17-14 已记：HOMO MAE 0.353 eV、LUMO 0.331 eV、gap 0.778 eV，三通道全是 `reference_only`），那才是决定这些数能不能进模型的那个数字。这次交叉校验只是排除了「链路 A 自己算错了/写错了」这一种解释。
3. **取数只能取一列。** 既然两条链路复现，就不存在「两个数据源取平均」的价值；A 是唯一权威列，B 是对照列。
4. **覆盖面的缺口是真实存在的。** 链路 B 少跑的那 91 个分子（142 − 51）以及那 4 个打不开的键，都不是「已覆盖」。

## 九、复现方式

```powershell
.\.venv\Scripts\python.exe probes/themol_eps_reproduction.py            # 重新生成两件产物
.\.venv\Scripts\python.exe probes/themol_eps_reproduction.py --check   # 逐字节比对
.\.venv\Scripts\python.exe -m pytest tests/test_themol_eps_reproduction.py -q -p no:cacheprovider
```

### 交付件

| 文件 | 内容 |
| --- | --- |
| `probes/themol_eps_reproduction.py` | 生成器，`--check` 可逐字节复算 |
| `probes/themol_eps_reproduction_facts.csv` | 51 行 × 15 列逐分子事实表 |
| `probes/themol_eps_reproduction_summary.json` | 匹配计数、Δ 统计、uuid 清单、分片完整性、输入 sha256 |
| `probes/themol_eps_reproduction_inputs/` | 链路 B 三个分片的 LF 归一冻结副本 |
| `tests/test_themol_eps_reproduction.py` | 12 条用例，全部自有重算，不依赖常量 |
| `reports/themol_eps_reproduction.md` | 本文件 |

`queries_executed = 0`、`is_a_plan_not_a_measurement = false`：本臂没有发起任何网络请求，全部数字来自两条链路**已经发生**的运行；它是一次测量，不是计划。
