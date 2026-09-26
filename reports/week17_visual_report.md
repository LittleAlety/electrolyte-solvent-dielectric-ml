# Week 17 数据扩充可视化报告（四通道 + THEMol 扩展臂）

**一句话**：新增 **6 张**直观图，把四通道（ε / η / HOMO-LUMO / 氧化还原）的覆盖与达标、以及
THEMol 扩展臂（W17-17）的名册分层 / 交付占比 / 跨水平标定 / 能级偏移摊在一眼能看懂的位置。
所有数字都由仓库工件在画图时**现读**，脚本不硬编码任何测量值（字面量只用于 `--check` 断言）。

## 1. 环境与字体方案

- 解释器 `.\.venv\Scripts\python.exe`；matplotlib `Agg` 后端，`dpi=150`；`PYTHONIOENCODING=utf-8`。
- **字体方案**：matplotlib 启动时探测系统 CJK 字体表，命中候选 `Microsoft YaHei / SimHei /
  Noto Sans CJK SC / Source Han Sans SC / WenQuanYi Zen Hei` 中的第一个即启用中文标签，否则
  **自动退回英文标签**（脚本用 `t(zh, en)` 双语字典）。本机命中 `Microsoft YaHei`，故 6 张图
  **全部为中文标签**，运行输出 `zh_labels = true`，无方块字风险。
- `axes.unicode_minus = False`，避免负号缺字。

## 2. 快照说明（重要）

`data/processed/themol_orbital_layer_expanded.csv` **仍在重建**（收割进行中），读到的行数是中间态。
本报告与下图对应的**渲染时快照**为：

- 行数 **3,109**（表头之外 3,109 条数据行）、sha256
  `44f900b14778961eea878e167f06e459f7c0d953de15fabf13e55cd62dedd3a0`、字节 2,030,359；
- 该快照 `run_status = partial`，交付 **3,109 / 5,117 = 60.76%**；跨水平标定 **2,763 对**；
  HOMO r 0.857 / MAE 0.300，LUMO r 0.613 / MAE 0.344，gap r 0.437 / MAE 0.580；
  能级偏移 HOMO −1.197 eV（σ 0.399）、LUMO −7.524 eV（σ 1.970）、gap −6.327 eV（σ 1.961）。

> 简报里引用的另一组数字（约 238/239 行、148 对、HOMO r 0.8465 / MAE 0.3327、偏移 −1.1658 / σ 0.4253、
> LUMO −7.3763 / σ 2.1338）对应**更早的中间态快照**。两者都是中间态，会随重建继续变化——所以脚本
> **只把冻结工件当字面量钉**（四通道板 `data/processed/four_channel_coverage.csv`、冻结名册
> `probes/themol_registry_expansion_roster_summary.json`（sha256 `71277d2c…d0136d6`）、DN 计数），
> 重建中的层只做**结构自洽**校验（`delivered_rows == 行数`、`run_status` 规则、标定对 ≤ 行数），
> 不钉死会漂移的标定/偏移数字。定性结论（HOMO 可平移、LUMO 离散、HOMO 过门、LUMO/gap 仅参考）
> 在新旧两个快照上**一致**。

## 3. 图清单

| 文件名 | 数据源 | 一句话结论 |
|---|---|---|
| `probes/artifacts/w17_channels_gate_board.png` | `data/processed/four_channel_coverage.csv`（门限 + 门状态） | 8 个 MAE/覆盖类读数按**各自门**归一（1.0 即门）：**只有 HOMO、LUMO 两门为绿**，η(0.175/门0.15)、IP(0.201/0.2)、EA(0.234/0.2)、氧化(0.291/0.15)、还原(0.410/0.15)、DN(0/0.30) **六门全红**；ε 主记分牌 R² 0.409 单列为“排序级、无 0.15/0.2 硬门”。 |
| `probes/artifacts/w17_themol_tier_delivery.png` | `themol_registry_expansion_roster_summary.json` + `themol_orbital_layer_expanded_summary.json` | 冻结名册 **5,117** 键分层堆叠（无参考轨道 421 / 旗舰 ε 54 / 其他核心 68 / 标定主体 4,574），对照实际交付并**诚实标注 `run_status = partial`**（60.76%）；薄层交付率反而高（旗舰 ε 81.5% > 其他核心 72.1% > 标定主体 58.8%）。 |
| `probes/artifacts/w17_themol_calibration_parity.png` | `themol_orbital_layer_expanded.csv`（`*_gfn2_eV` vs `batt_*_eV`）+ summary 的 `calibration` 块 | xTB vs wB97X-V 三通道散点，画 **y=x / 总体 2 折拟合 / 两条折外拟合线**：HOMO 贴合最好（r 0.857、MAE 0.300，`usable_with_flag`），**LUMO、gap 拟合斜率塌陷（0.14–0.16，`reference_only`）**，LUMO 只能当参考不能反演。 |
| `probes/artifacts/w17_themol_level_offsets.png` | `themol_orbital_layer_expanded.csv` 的 `gfn2_minus_batt_{homo,lumo,gap}_eV` 列 | 偏移分布：**HOMO σ 0.399 eV（窄，可整体平移）**；**LUMO σ 1.970 eV、gap σ 1.961 eV（宽，离散）**——LUMO 靠常数平移救不回来，只能做有 flag 的参考。 |
| `probes/artifacts/w17_channels_label_inventory.png` | `four_channel_coverage_summary.json`（pinned）+ `models/homo_lumo_baselines.json` | 标签量差三个数量级：Batt 池 **29,515** 行（HOMO/LUMO/IP/EA 各 29,515，组 29,519）、η 3,582 行、ε 457 行、redox 392 行、**DN 可采信 0 / 1,043 = 0.00%（门 0.30，红，不入特征表）**。 |
| `probes/artifacts/w17_reaxys_round_tally.png` | `reaxys_v1x_stocking_query_summary.json` 的 `channel_tally` | Reaxys W17-16 本轮 19 个物质卡片普查的三轴产出：η 最多（144 行 / 130 有效 / 90 点值），ε 次之（98 / 70 / 53），IP 仅 30 点值，redox 27 行**全在 Comment 串里、点值 0**。 |

> 关于第 6 张：普通意义的“覆盖**变化**”需要 before/after 两份覆盖表，而该 summary **只给本轮产出
> 三元组**（行 / 有效值行 / 点值），没有基线对比——因此如实画成“**本轮产出**”，不假造成“增量”。

## 4. 已知限制

- **折外点标注**：层 CSV 不保存逐行折号，故标定图**不按折着色单点**；改为标注“全部 2,763 对均为
  折外点”（`n_out_of_sample == n`）并同时画出两条折外拟合线，避免编造逐点折归属。
- **移动快照**：标定/偏移两图反映渲染时快照，重建继续推进会变；四通道板与名册数字来自冻结工件，稳定。
- 本包**不拟合模型、不产新 R²、不碰冻结主记分牌**；不覆盖既有的 `themol_expansion_coverage.png` /
  `themol_expansion_calibration.png`。

## 5. 复现

    .\.venv\Scripts\python.exe probes\plot_week17_channels.py            # 画 6 张图到 probes\artifacts\
    .\.venv\Scripts\python.exe probes\plot_week17_channels.py --check    # 只校验输入与钉，不画图
    .\.venv\Scripts\python.exe -m pytest tests\test_plot_week17_channels.py -q -p no:cacheprovider
    .\.venv\Scripts\python.exe -m ruff check probes
