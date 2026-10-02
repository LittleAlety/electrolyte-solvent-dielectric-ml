# 电解液溶剂筛选：可审计的多通道机器学习管线

> An auditable, pre-registered machine-learning pipeline for electrolyte-solvent
> screening: static permittivity (epsilon), viscosity (eta), the orbital window
> (HOMO / LUMO), and redox potential - with a frozen main scoreboard, a shot ledger,
> and every negative result retained rather than routed around.

**当前轮次：** W27（2026-10-03）· **规范数据集：** `data/dielectric_v04.csv`（248 行 × 38 列）
**主记分牌：** 累计 13 枪（W20-4 之后 W21–W26 各 0，W27 第 1 枪）
**许可：** 代码 MIT（`LICENSE`）、数据 CC BY 4.0（`LICENSE-DATA.md`）
**已发布：** v1.3（GitHub release 2026-09-28 + Zenodo，DOI 见文末）· W21–W27 尚未发布（v1.4 待定）

## 0. 本版 README 相对上一版的更新范围

上一版 README 停在 v1.3 / Week 20。此后仓库前进了七个轮次，本版补齐：

- **W21–W27 的四通道建设**：介电常数（ε）、粘度（η）、轨道窗口（HOMO/LUMO）、氧化还原电位，外加密度与液相窗口两张辅助表；四核心通道的统一注册表由 `scripts/verify_four_core_registry.py` 逐键复算。
- **W26 的稠密介电响应律**：xTB 6.7.1 ddCOSMO 任意 ε、242 分子、刚性气相几何，14 档 ε 网格，把「介电响应」从「几何弛豫」里分离出来。
- **W27 的第一枪（判否，含一处自我削弱）**：把 W26 的 13 列响应量当第四个表示家族接进冻结主记分牌，五种子增量均值 -0.096956；但安慰剂不惰性（-0.006099），因此净信息效应是 -0.090857 + 容量效应 0.0061，两个数必须并报。详见 `reports/week27_delivery_readme.md`。
- **论文按期刊模版重排并导出 docx**：`paper/make_paper_docx_template.py` → `成果输出/论文_电解液溶剂筛选中的描述符决策稳定性_期刊模版.docx`（379 段 / 15 张三线表 / 19 张图）。

## 1. 这个仓库是什么

一个**筛选导向**的可审计管线：给候选有机溶剂预测电解液关心的物性，并且把「哪些路走不通」与「哪些路走通了」用同一套预注册纪律记下来。三条硬约束贯穿全部轮次：

1. **每条读数都有预注册**（`*_prereg.json`，`status = locked_before_run`，带 sha256），阈值在生产运行之前冻结；事后修订只能写成「更正」，不能原地改。
2. **每条读数都有守卫**：交付表的每个数都要能从盘上产物重算（`tests/` 下 3,362 条测试函数，含「存储行可重算」「LF-only」「图非平凡」「表头与取值元组一致」等）。
3. **负结果与边界照报**：不晋升的臂、判否的判据、口径冲突与外部数据许可边界都留在仓库里。

## 2. 目录速览

| 路径 | 内容 |
| --- | --- |
| `data/` | 规范数据集与各轮构建的中间表（`dielectric_v04.csv` = 248 行 × 38 列；`density_v01.csv` 182,154 行；`viscosity_v02.csv` 42,941 行） |
| `data/processed/` | 120 张派生表（四通道键注册表、条件位移层、构象层、名册补丁等） |
| `probes/` | 221 个探针脚本：每个数、每张图都有对应脚本；`probes/artifacts/` 288 件产物 |
| `scripts/` | 59 个构建脚本与验证器（含 `verify_four_core_registry.py`） |
| `tests/` | 218 个测试文件（含跨轮次的纪律守卫与复算守卫） |
| `reports/` | 234 份 Markdown：决策日志（`decisions_log.md`，28.81 节）、逐轮立项章与交付说明 |
| `docs/` | 逐轮构建笔记与 schema |
| `paper/` | 论文源（`paper_zh_draft_v2.md`）与两个 docx 生成器 |
| `成果输出/` | 每一轮的交付导出（`week1` … `week27`）与论文 docx（仓库外的兄弟目录） |

## 3. 四个通道与主记分牌

四核心通道的键数由 `scripts/verify_four_core_registry.py --check` **从源表独立重算**（不是从摘要回读），最近一次校验收于 `data/processed/four_core_key_registry.csv`（sha256 `e42885eb43779b7a4d472da88fefe018fe94150ff5b6fba86b3ed9bc83dc8bee`）：

| 通道 | 量 | 键数 | 现状 |
| --- | --- | --- | --- |
| 介电常数 ε | 静态相对介电常数（近室温纯有机液体） | 247 | 冻结主记分牌所在通道；v0.3.3 名册 246 行 + W17-1 双行补丁 = `dielectric_v04.csv` 248 行 |
| 轨道窗口 | HOMO / LUMO / 间隙（xTB、DFT、第三方） | 29,868 | 通道内最大的表；`data/raw/` 里的第三方数据集不入交付包 |
| 氧化还原电位 | 氧化 / 还原标签（含条件态位移） | 392 | 标签层；W24-1/W24-2 给出条件态位移 |
| 粘度 η | 动力学粘度（多来源、带温度与频率元数据） | 1,228 | W18A 行级解冻已**判否**（组键 MAE 0.1748 → 0.1570，门 0.15），不要再走这条 |
| 密度（辅助） | 纯密度 | 2,178 | 182,154 行原始表；对 ε 名册行级覆盖 73.2% |
| 液相窗口（辅助） | 温度 / 压力窗口 | 218 | 表键 314、有数值 218、四列全空 96 |

**四通道全齐的化合物数**（三种口径，独立重算）：预注册核心四通道 **7**；加上液相窗口数值 **51**；按液相窗口表键 **53**。另有 Kirkwood 和式公式的 Pearson **r = 0.6464482483155133**（n = 79）作为 ε 通道的外部一致性读数。

## 4. 冻结读数（口径不同，**永不混比**）

| 读数 | 值 | 定义 |
| --- | --- | --- |
| 基线 | `0.4091179943351143` | 原池、原配置的原位基线 |
| **头条 headline** | `0.4766400383507876` | 杠杆 4+8 合并臂，457 行 / 97 化合物 / 276 个（化合物, T）对，pass_merged_blocks |
| 单表示跨种子端点 | `0.5861142332208197` | 五种子均值（sd 0.0175），唯一候选「提升路径」的端点 |
| W20-4 唯一晋升翼 | `0.6216672295270079` | 迄今唯一被晋升并入库的臂 |

- **主记分牌 shot 账本：累计 13。** W20-4 之后 W21–W26 各计 0；**W27 计 1**（第一个触及冻结池与评分掩码的新表示家族）。
- 任何新读数都必须注明它属于哪一行口径；跨行比较一律无效。

## 5. 负结果登记（截至 W27，全部保留）

- **换拟合器**：GPR 0.2313、MLP -0.172 —— 证否。
- **网络叠加 / bagging**：+0.00175，惰性 —— 证否。
- **外来化学空间**：NBS-514 → 0.3809 反噬 —— 证否。
- **杂类锚点**：shot 15 → 0.5102 反噬 —— 证否。
- **η 行级解冻**：组键 MAE 0.174772 → 0.1570，门 0.15 —— 判否。
- **阴离子束缚闸门**（W26-2）：GFN2 层级不存在，原因是方法（气相 EA 的 p05–p95 跨距 9.307 eV vs 介电扫描能给的 2.4684 eV 位移）—— 判否并归因。
- **几何弛豫的贡献**（W26-1 H1e）：离子对中位 0.0547 eV > 0.05，W24-1 的 2.1 eV 前因子被轻度污染但方向未变 —— 判否。
- **介电响应描述符块**（W27）：五种子增量均值 -0.096956，确认线与部分线双判否；**且安慰剂不惰性**（-0.006099 > 0.005），故净信息效应 -0.090857 + 容量效应 0.0061 必须并报 —— 判否。

## 6. 口径铁律

- **层级不可混**：本仓 W26 / W27 的介电特征来自 **GFN2-xTB / ddCOSMO 任意 ε / 刚性气相几何 / 242 分子**；母体论文 v6 是 **r2SCAN-3c / CPCM / 18 分子**。跨层级只比函数形式与量级，绝不比绝对值。
- **绝热量 ≠ 垂直量**：W24-1 / W23-2 是绝热口径，W24-2 与 v6 的 P1/P2 是垂直口径，绝对值不可比。
- **缺行不插补**：稀疏块与稠密块拼接时留 NaN，交给 XGBoost 原生缺失值处理；不计算折内统计量。
- **特征块不得触及被测标签**：例如 W27 的 13 列全是「溶质对给定 ε 的连续介质」的响应，没有一列读到被预测的那个 ε。
- **第三方许可分层**：THEMol 为 CC BY-NC 4.0（非商用），**只留在 `data/raw/`、不入交付包**；**Batt-P30K（MIT）是本仓唯一干净的第三方线**；OMat24 是**无机晶体**数据集，对有机溶剂分子不合适。Reaxys 数值一律不引用。

## 7. 复现

```powershell
# 环境（二选一）
conda env create -f environment.yml; conda activate electrolyte-ml
# 或使用仓库内已建好的虚拟环境 .venv

# 四核心通道注册表：从源表独立重算每一个键
python scripts\verify_four_core_registry.py --check

# 数据集与基准
python scripts\verify_dielectric_v04.py
python scripts\verify_v032_benchmarks.py

# 最近一轮（W27）：主探针 + 导出器
$env:PYTHONIOENCODING="utf-8"; $env:OMP_NUM_THREADS=1; $env:OPENBLAS_NUM_THREADS=1
python -X utf8 -u probes\w27_dielectric_response.py --jobs 8
python -m pytest tests\test_repo_hygiene.py tests\test_w27_dielectric_response.py -q -p no:cacheprovider
python probes\export_week27_results.py --overwrite
```

> 全套 `pytest -q` 很慢（3,362 条测试函数）。日常验收用逐轮文档化的子集：`tests\test_repo_hygiene.py` 加该轮的 `tests\test_wN_*.py`。
> 跑长任务前请设 `OMP_NUM_THREADS=1` / `OPENBLAS_NUM_THREADS=1` / `MKL_NUM_THREADS=1`，否则 BLAS 线程超订会让矩阵作业假死。

## 8. 论文与交付物

- **论文源（中文）**：`paper/paper_zh_draft_v2.md`
- **期刊模版 docx**：`paper/make_paper_docx_template.py` → `成果输出/论文_电解液溶剂筛选中的描述符决策稳定性_期刊模版.docx`（A4、正文五号宋体、固定行距 15 磅、字间距 0.15 磅；379 段 / 15 张三线表 / 19 张图）
- **另一版 docx**：`paper/make_paper_docx.py` → `成果输出/论文_电解液溶剂筛选中的描述符决策稳定性.docx`
- **逐轮交付导出**：`成果输出/week1` … `week27`。每一轮的 `weekN_summary.json` 带 `artifacts_commit`（标识交付字节的提交）、`worktree_dirty`、`lanes_missing` 与 `verification_passed`；导出按 **AF-12 三步走**：先封树提交 → 用该提交干净重导 → 按需补修复提交。

## 9. 许可与第三方数据

| 对象 | 许可 | 处置 |
| --- | --- | --- |
| 代码 | MIT（`LICENSE`） | 可自由使用与再分发 |
| 本仓数据集与产物 | CC BY 4.0（`LICENSE-DATA.md`） | 署名即可再分发 |
| THEMol（ByteDance-Seed） | CC BY-NC 4.0 | **非商用**；只留在 `data/raw/`，**不入交付包** |
| Batt-P30K（Teoroo-CMC/Batt-SLM） | MIT | 唯一干净的第三方线，可作参考层与迁移源 |
| OMat24 | 自有条款 | **无机晶体**数据集，对有机溶剂分子不适用 |
| Reaxys | 商业条款 | **不引用任何数值** |

## 10. 版本与 DOI

- **v1.3**（Week 20）：https://doi.org/10.5281/zenodo.23019467
- **v1.2.1**（归档更正）：https://doi.org/10.5281/zenodo.23006276
- **v1.2**（Week 19 收口）：https://doi.org/10.5281/zenodo.23001632
- **v1.1**（Week 18–19 证据包）：https://doi.org/10.5281/zenodo.23001408
- **v1.0**（首个可复现版本）：https://doi.org/10.5281/zenodo.22957696
- **Concept DOI（引用全部版本）：** https://doi.org/10.5281/zenodo.22957695

> 引用单轮结论时，请同时引用该轮的 `reports/weekN_delivery_readme.md` 与它登记在 `reports/decisions_log.md` 的节号；引用跨轮结论时用 Concept DOI。

## 11. 下一步（已登记，未执行）

1. **给稠密配置重调 XGB 超参**：冻结的 `max_depth = 2` / 200 树是为 2048 维稀疏 Morgan 定的；W27 的安慰剂掉的 0.0061 就是容量惩罚的直接证据。预注册一次 inner-fold 网格（深度 2–6 / 树数 200–1200 / lr 0.02–0.1）。**这是唯一可能把单表示跨种子端点 0.5861 推过 0.60 的单杠杆。**
2. **显示层补强（近乎零成本）**：把 `auc_gt15` / `auc_gt30` 补进 `METRIC_NAMES`，让每个臂的重复表自带 AUC；再出一张「三档划分（随机 / 化合物 / 骨架）×（R² / AUC / Spearman）」对照表 —— 「排序学会了、量级学不会」这句话需要这张表才讲得清。
3. **同容量对照下重测 W27 的响应块**：否则负增量无法区分「信息无用」与「容量惩罚」。
