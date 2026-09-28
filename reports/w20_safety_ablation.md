# W20-2 Step 1：安全通道影响力消融（液窗过滤把排序头搬走了，但靠的是域包含而非独立信息）

- **任务** `week20_w20_2_step1_safety_influence_ablation`｜**节号** §28.58｜**生成时间（本机 UTC）** 2026-09-28T04:43:04Z
- **性质**：Step 1 是**影响力消融**。**不拟合任何模型、不占 shot 编号、不产任何通道读数**；`produces_reading = false`、`shot_number_taken = null`、`promoted = false`、`models_fitted = 0`。本件产出的是一组**消融数值**（head purity / Jaccard@k / 候选清单改变数），不是通道读数。
- **权威输入**：`reports/week20_project_charter.md` §1 `W20-2`、§5 执行顺序、§7 验收、附录数字出处；`probes/w20_safety_ablation.py`（W20-2 登记态骨架，本 lane 把它推进到可执行态，**未重写**）。
- **机器可读产物**：`probes/w20_safety_ablation_prereg.json`（跑前锁定）、`probes/w20_safety_ablation_summary.json`（跑后落盘）。
- **Step 2 不在本件内**：通道可建模性见 `reports/w20_safety_model.md` 与 `probes/w20_safety_model*.json`。Step 1 与 Step 2 **分开登记、分开判读、不得互相混比**。

## 1. 分域声明（结论的一部分，不是脚注）

**安全通道只进 ε 侧，不得进 η 侧。**

依据是同一把尺子（覆盖门 `0.3`，口径 `covered_keys / target_keys`）在三个目标集上的实测：ε v03 名册 **0.7358 过门**；η viscosity_v01 **0.1651 不过门**；η viscosity_v02 **0.1270 不过门**。安全通道（液窗：熔点 / 沸点 / 闪点）在这三张分母上**不是同一条通道**——它对 ε 侧可用，对 η 侧不可用。

⇒ 硬约束（写入 W20-3 排序键前置条件）：① 安全维度**只允许并入 ε 侧的排序键**；② **不得**把它并入 η 侧排序键，也**不得**用「安全通道已过门」为 η 侧的扩维背书；③ 本声明与 ε 的 D1 分域声明（`NumHDonors ≥ 1 and TPSA ≥ 20.0`，§28.45）**分开登记**，两者不是同一条规则。

## 2. 覆盖门实测（本 lane 重算，与 charter 表逐位一致）

| 目标集（分母） | 键数 | 安全通道命中 | 覆盖率 | 门 0.3 |
| --- | ---: | ---: | ---: | :--: |
| ε v03 名册（`data/dielectric_v03.csv`） | 246 | 181 | **0.7357723577235772** | ✅ 过 |
| η viscosity_v01（`data/viscosity_v01.csv`） | 957 | 158 | 0.16509926854754442 | ❌ 不过 |
| η viscosity_v02（`data/viscosity_v02.csv`） | 1228 | 156 | 0.1270358306188925 | ❌ 不过 |

安全通道键集 = 注册表 `data/processed/four_core_key_registry.csv` 里 `channels_present` 含 `liquid_window` 的 **218** 键（口径 `registry_liquid_window_channel`，即 charter 覆盖表所用口径）。

**口径澄清（机器强制）**：这三行不是手抄。`coverage_table()` 每次运行都从磁盘重算，并由 `check_coverage_against_readings()` 与模块内冻结的 `COVERAGE_READINGS` 逐位比对，**不一致即 `SystemExit`**；键集大小也必须等于 `218`。所以「引用了另一个口径的数字」这件事在本件里不可能悄悄发生。

**并入 314 键特征表口径（登记在册，本件不采用）**：另一条合法口径是 `data/processed/liquid_window_features.csv`（**314** 键），它对 v03 = **246/246 = 1.0**、v01 = **160/957**、v02 = **202/1228**。两条口径的门判定**一致**（ε 过、η 两处不过），但**数字不是同一个**，因此 `SAFETY_KEY_SET` 是预注册字段而非默认值。本 lane 钉 `registry_liquid_window_channel`，即 charter 覆盖表的口径。

## 3. 预注册三钉与骨架改动留痕

跑前（`probes/w20_safety_ablation_prereg.json`，`status = locked_before_run`）钉死的三个字段，骨架里原本都是 `None`：

| 字段 | 钉值 | 理由 |
| --- | --- | --- |
| `SAFETY_KEY_SET` | `registry_liquid_window_channel` | 与 charter 覆盖表同口径（本文件 §2） |
| `SCORED_UNIVERSE` | `registry_wide` | 参考集必须是被评分池的**真子集**，否则纯度恒为 1.0（若取 v03 名册宇宙，78 行的池会坐进自己的参考集里） |
| `RECOMMENDED_SET_PATH` | `data/dielectric_v03.csv` | 参考集 = 冻结 ε 名册（246 键，带实测介电常数）⇒ 「命中」= 头部覆盖到 ε 通道已经掌握的那个化合物 |

其余固定项（骨架原有、未动）：v0 键 = HOMO 0.5 / LUMO 0.5（`probes/w19_ranking_key.py::DEFAULT_KEYS`）；`TOP_K_VALUES = (10, 20, 50)`；placebo **200** 次置换、种子 **20260928**（保持过滤基数、只摧毁过滤内容）。

### 3.1 对登记态骨架的改动（逐条留痕）

骨架的消融逻辑（两条臂、v0 键、purity 定义、placebo 构造、`blocking_conditions`）**一字未改**。改的只有下面七处，其余字节保留：

| # | 改动 | 类型 |
| --- | --- | --- |
| 1 | 三个字段 `None` → 钉值（上表） | 从登记态推进到可执行态 |
| 2 | 新增 `pool_reference_density` 与 `purity_lift`（两臂各一个） | **加字段**（不改旧字段语义） |
| 3 | 新增 `coverage_table()` / `coverage_verdicts()` / `check_coverage_against_readings()`：覆盖门从磁盘重算并与冻结读数对表 | 加函数 |
| 4 | 新增 `input_digests()` / `prereg_summary()` / `prereg_reference()` 与 `--write-prereg` | 加函数 + 加 CLI |
| 5 | `--recommended-set` 默认值 `None` → 钉值（否则 CLI 永远拿不到参考集、永远拒绝评分） | 可执行化必需 |
| 6 | `run()` 的 `produces_reading`：`True` → **`False`**，并新增 `produces_ablation_numbers = True` | **刻意改**，见下 |
| 7 | 三处注释/文档句更正（本文件 §8 的「不可核」两条） | 照实更正 |
| 8 | 新增 `arms_csv_rows()` / `write_arms_csv()` 与 `--write-arms-csv` / `--arms-csv`（Step-1 缺口补齐：臂表落盘） | **加函数 + 加 CLI**；`run()` 字节未动，摘要摘要字节未变 |

**第 6 条为什么必须改（照实说明）**：登记态骨架在 `run()` 里把 `produces_reading` 翻成 `True`。本 lane 的任务书对 Step 1 明文要求 `produces_reading = false`（不拟合、不占号、不产通道读数）。两者不能同时成立，故按任务书取 `false`，并**新增** `produces_ablation_numbers = True` 把这个区别写进机器可读层：本件产出的是**消融数值**，不是通道读数。同款处理有 W19 先例（`probes/w19_batt_direct_hit_summary.json` 用 `read_only = true` / `models_fitted = 0` 表述同一件事）。`plan()`（预注册态）里的 `produces_reading` 一直是 `False`，未动。

### 3.2 被评分池与参考集（跑前锁定，跑后复核）

| 量 | 值 | 出处 |
| --- | ---: | --- |
| 注册表总行数 | 31,949 | `data/processed/four_core_key_registry.csv` |
| v0 键可评分行（orbitals 通道且 HOMO/LUMO 有限） | 29,519 | `scorable_rows()` |
| 安全通道键（`liquid_window`） | 218 | `safety_key_set()` |
| orbitals 且 liquid_window（只数标志） | 75 | `UNIVERSE_READINGS` |
| 可评分且 liquid_window（= arm1 的池） | **70** | `UNIVERSE_READINGS` |
| 参考集（ε v03 名册） | 246 | `data/dielectric_v03.csv` |
| 参考集 ∩ 可评分 | 78 | 本 lane 实测 |
| 参考集 ∩ arm1 池 | 64 | 本 lane 实测 |

⇒ **液窗过滤留下的不是一个过滤器，是一张短名单**：70 行（注册表口径）。「安全通道命中 181」是**键集**、不是 arm1 的池；把 181 当作 70 引用正是本设计要避免的错误。

## 4. 读数一：两条臂的 head purity 与基准密度

命中（hit）定义：头部成员落在参考集里（= 该化合物在冻结 ε 名册上有一个实测介电常数）。`head purity = |head_k ∩ reference| / k`。

| 臂 | 池大小 | 参考集在池内的密度 | purity@10 | purity@20 | purity@50 |
| --- | ---: | ---: | ---: | ---: | ---: |
| arm0 `arm0_v0_unfiltered` | 29,519 | 0.002642365933805346 | 0.0 | 0.0 | 0.02 |
| arm1 `arm1_v0_liquid_window` | 70 | 0.9142857142857143 | **1.0** | **1.0** | 0.98 |

对上池内基准密度的**增量**（`purity_lift = purity − 池内密度`）：

| 臂 | lift@10 | lift@20 | lift@50 |
| --- | ---: | ---: | ---: |
| arm0 | -0.002642365933805346 | -0.002642365933805346 | 0.017357634066194654 |
| arm1 | 0.08571428571428574 | 0.08571428571428574 | 0.06571428571428573 |

**这一列必须和 purity 一起读**：两条臂的基准密度差了 **346 倍**（0.9142857142857143 / 0.002642365933805346 = 346.05…），所以「arm1 的 purity 更高」里有很大一部分是**包含关系**带来的、不是排序带来的。真正的增量是 lift：arm1 在 k=10 上只比它自己池内的基准高 **0.08571428571428574**。

## 5. 读数二：Jaccard@k、头部保留率与候选清单改变数

| k | Jaccard(arm0 head, arm1 head) | 头部保留率（arm1 保留的 arm0 头部比例） | 候选清单改变数（对称差） |
| ---: | ---: | ---: | ---: |
| 10 | 0.0 | 0.0 | 20 |
| 20 | 0.0 | 0.0 | 40 |
| 50 | 0.010101010101010102 | 0.02 | 98 |

读法：**k=10 与 k=20 上两条臂的头部完全不相交**（Jaccard = 0.0，改变数 = 2k，即整张清单被换掉）。液窗过滤不是给头部**重排序**，是**把整个头部换掉**。到 k=50 才有 1 个共同成员（保留率 0.02），因为 arm1 的池只有 70 行、k=50 已占池的 71.4%。

## 6. 读数三：placebo（200 次置换，种子 20260928）

placebo 从**同一个 29,519 行池**里随机抽 **70** 个键（与 arm1 池等基数），只摧毁「哪些键」、保留「抽多少」。

| k | placebo purity 最小 | 中位 | 最大 |
| ---: | ---: | ---: | ---: |
| 10 | 0.0 | 0.0 | 0.1 |
| 20 | 0.0 | 0.0 | 0.05 |
| 50 | 0.0 | 0.0 | 0.04 |

⇒ 随机等基数子集在 k=10 上最好也只碰到 **0.1**（10 个里 1 个命中），中位数 **0.0**；arm1 的 **1.0** 远离 placebo 全域。**效应不是采样子集的假象**。但 placebo **不能**排除包含关系——包含关系是 arm1 池的**固有属性**（0.9142857142857143），已在 §4 单列。

## 7. 判定与边界

**H1（跑前锁定）：把被评分池限制到带实测液窗的行，会提高固定 k 上的 head purity。**

- **判定：方向成立，但机制是域包含，不是通道信息。** purity@10 由 0.0 升到 1.0、@20 由 0.0 升到 1.0；同时 head 被整张换掉（Jaccard@10 = 0.0，改变数 = 20）。
- **机制（照实写）**：安全通道键集与 ε 名册高度重叠——**181 / 218 = 0.8302752293577982** 的安全键本来就在 ε 名册里；而 arm1 的池（70 行）有 **64** 行在名册里（0.9142857142857143）。所以纯度上升的**大部分**在过滤发生的那一刻就已经决定了，与 v0 键（HOMO/LUMO）无关。
- **本条对 W20-3 的意义（这是本 lane 的真正交付）**：安全通道进排序键带来的**不是一条独立排序信号**，而是一道**域约束**。把安全维度当「第三个打分维度」加进 v0 键，会把一个近乎包含关系的集合伪装成一条通道；正确的接法是**闸门**（域内/域外），不是权重。
- **未被告知的**：本件**不**证明安全通道对 ε 目标没有信息；它只证明**在 v0 键（HOMO/LUMO）的头部排序上**，液窗过滤以域包含的方式起作用。

**边界（不许省略）**

- **分数是集合相对量**：v0 键的 desirability 在被评分行集内做 min-max，故 arm0（29,519 行）与 arm1（70 行）的**分数量纲不可比**，本件不做任何分数比较，只比名次头部。
- **ε 主记分牌与 η 读数在本件里不得混比**（见 §8）。
- **参考集是一条判断，不是一条事实**（见 §9）：换参考集，purity 数字会变；不变的是 Jaccard@k 与候选清单改变数（那两项不依赖参考集）。
- **本件不占号、不产通道读数**：`shot_number_taken = null`、`produces_reading = false`、`models_fitted = 0`、`writes_any_pool = false`。

## 8. 隔离声明与记分牌纪律

**隔离声明**：本件读数**不得与 ε 主记分牌（基线 `0.4091179943351143` / 头条 `0.4766400383507876`）或 η 通道读数（行级 `0.08506361044387624` / 族级 `0.08908094784092072`）混比。** 本件的量是「短名单里有多少个是 ε 名册化合物」——集合重叠比；那四个数是分组 R² / MAE。上下文里并排出现即属误用。

- `promoted = false`、`main_scoreboard_untouched = true`、`scoreboard_attempts_delta = 0`；
- **主记分牌本周尝试 0 次，累计 11 次不变**；冻结基线 `0.4091179943351143` 与冻结头条 `0.4766400383507876` 原位未动；
- **不引用任何 Reaxys 数值**：`reaxys_values_used = 0`；本件全部数字来自仓内 CSV 或本件运行值；
- **不动任何冻结件、不改任何 `data/` 件、不做任何 git 操作**。

## 9. 数字出处与不可核登记

**可核（逐条回搜命中）**

- 覆盖三行（`246` / `181` / `0.7357723577235772`、`957` / `158` / `0.16509926854754442`、`1228` / `156` / `0.1270358306188925`）⇒ 本 lane 重算值，落在 `probes/w20_safety_ablation_summary.json::coverage`；与 `reports/week20_project_charter.md::§1 W20-2` 覆盖表逐位一致；键集口径见 `probes/w20_safety_ablation.py::COVERAGE_READINGS` / `::coverage_table`
- `218` / `314` / `246` / `957` / `1228` ⇒ `probes/w20_safety_ablation.py::COVERAGE_READINGS`；`314` 另见 `probes/liquid_window_gate_summary.json::coverage_set`
- `31949` / `29519` / `75` / `70` / `78` / `64` ⇒ `probes/w20_safety_ablation.py::UNIVERSE_READINGS` ＋ 本 lane 实测（`78` / `64` 为参考集交集，落在 summary `arms[*].reference_density_in_pool` 的分子）
- 全部 head purity / `purity_lift` / Jaccard / 改变数 / placebo ⇒ `probes/w20_safety_ablation_summary.json::arms` / `::overlap` / `::placebo_head_purity`
- `0.3`（覆盖门）⇒ `probes/w20_safety_ablation.py::COVERAGE_GATE`（同值另见 `probes/walden_dn_channel_summary.json::dn_channel.coverage_threshold`）
- `0.5` / `0.5`（v0 等权）与 `min` / `max` 方向 ⇒ `probes/w19_ranking_key.py::DEFAULT_KEYS`；字面钉见 `tests/test_w19_ranking_key.py`
- `0.4091179943351143` / `0.4766400383507876`（ε 主记分牌）⇒ `probes/export_week18_results.py` ＋ `probes/four_channel_coverage_summary.json::pinned`
- `0.08506361044387624` / `0.08908094784092072`（η 读数）⇒ `probes/w19_chemprop_viscosity_summary.json`｜`reports/_w19_section_d5.md`（§28.49）
- `20260928`（placebo 种子）/ `200`（置换次数）/ `(10, 20, 50)`（k）⇒ `probes/w20_safety_ablation.py::PLACEBO_SEED` / `::PLACEBO_PERMUTATIONS` / `::TOP_K_VALUES`
- `181 / 218 = 0.8302752293577982`（安全键集落在 ε 名册内的比例）⇒ 本 lane 实测（由 `data/processed/four_core_key_registry.csv` 的 `liquid_window` 键集与 `data/dielectric_v03.csv` 求交）
- `496`（`channels_present` 的写入行号）⇒ `probes/build_four_core_registry.py:496`

**照实登记为「不可核」**

1. **参考集的「正确性」不可核——它是一条判断，不是一条事实。** 「命中 = 落在冻结 ε 名册里」是本 lane 跑前钉的选择（理由：ε 是安全通道声明服务的唯一目标侧）。换一个参考集，purity 与 lift 会变；`Jaccard@k` 与候选清单改变数**不依赖参考集**，故 §5 的两张表是本件最硬的读数。
2. **骨架的一处理由句被实测推翻（已更正、留痕）。** 登记态骨架称「注册表 per-channel `has_*` 布尔列在 `csv.DictReader` 下读作 false」。本机实测**不成立**：六个通道的 `has_*` 列与 `channels_present` 在 **31,949 行上零失配**（例：`has_liquid_window` 为 true 的恰是那 218 行）。`channel_present()` 的**行为未改**（两条口径给出同一个键集），只把理由句换成实测过的那条。
3. **注册表 `dielectric` 通道 247 键 ≠ ε 名册 246 键。** 多出的一键是 `IAHFWCOBPZCAEA-UHFFFAOYSA-N`（succinonitrile，ε `56.09` @ `333.15` K，不在 v03 的温度带内）。本 lane 的分母一律取**冻结名册**（`data/dielectric_v03.csv`，246），与 charter 覆盖表同口径；**「注册表该不该把它算作 dielectric 通道」不是本 lane 的裁定范围**，留给 W20-7 的三层标签规范统一。
4. **三通道分母的入选口径未复核。** `957`（v01 键数）与 `1228`（v02 键数）由 `data/viscosity_v01.csv` / `data/viscosity_v02.csv` 去重 `inchikey` 得到（行数分别为 3,582 / 42,941），本 lane **只去重、不复核**这两张表的行入选规则（那是 η 侧 W20-1 的范围）。
5. **`data/processed/*` 的版本状态**：`data/processed/four_core_key_registry.csv` 与 `data/processed/liquid_window_features.csv` 实测**已被 git 跟踪**（`git ls-files` 两者均列出），故可核。

## 10. 对下游 lane 的输入

- **W20-3（排序键 v1）**：① 安全维度按 §7 接成**闸门**而非权重；② 若仍要计权，必须先给出一条可证伪的、非包含关系的排序证据；③ `Jaccard@10 = 0.0` 意味着一旦加闸门，短名单会被整张换掉，必须有适用域声明配套。
- **W20-5（高 ε 区拒答）**：本件的「域外不给分」思路与拒答机制同源；但本件不裁 ε > 60 区的任何事。
- **W20-7（三层标签规范）**：本件 §9 第 2、3 条是两条待统一的登记项（`has_*` 与 `channels_present` 双列并存；注册表通道宽于冻结名册）。

## 11. 复现与产物摘要

```powershell
# 1) 先锁预注册（跑前）
$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe probes\w20_safety_ablation.py --write-prereg
# 2) 再跑消融（跑后写摘要）；加 --write-arms-csv 则同时补写臂表 CSV（纯投影）
$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe probes\w20_safety_ablation.py --write-summary --write-arms-csv
# 3) 单测
$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe -m pytest tests\test_w20_safety_ablation.py -q
```

| 产物 | 行数 | bytes | sha256 |
| --- | ---: | ---: | --- |
| `probes/w20_safety_ablation.py` | 810 | 32155 | `ea180ebb67efad6c35914c08b705231fe4ee7cb3145c4cd8683b69d546ae7e39` |
| `probes/artifacts/w20_safety_ablation_arms.csv` | 7 | 656 | `ba51bad2a81ea0e5e694b56dca83e144dc24be8fa2d6224a9e8bbc2c19e011ea` |
| `probes/w20_safety_ablation_prereg.json` | — | 4296 | `94598a638462892a582eef385627da7cb4f801262445c54ce31fc6c4c875d6b8` |
| `probes/w20_safety_ablation_summary.json` | — | 5276 | `da36e9addd124381712162eb11f0881285fa2d69cd2836797c0cc08f0a14b1a2` |
| `reports/w20_safety_ablation.md` | 本件 | — | 见 `reports/_w20_section_w202.md` 落章（片段内不引本件自身 digest） |

