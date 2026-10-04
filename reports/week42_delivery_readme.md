# Week 42 交付说明

**本轮性质**：计算密集型周。把第三外部轨道层 PubChemQC（B3LYP/6-31G*//PM6 气相，CC BY 4.0）接进 W41 的三层网络，并一次跑完四层覆盖/交集/迁移/非传递闭合、xTB→Batt 的 isotonic 代理上界、偶极三源回归分解与 Bland–Altman、四层抽样律与域比 bootstrap/置换。
**shot 账本**：**0 shot，累计仍 19**。四条 lane 全是只读离线计算。
**冻结读数**：`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`，一个不动。

---

## 1. 判据总账

| lane | 标题 | 判据 |
| --- | --- | --- |
| W42-A | 四层轨道迁移网络与非传递闭合 | H42a1–H42a13：**13 成立** |
| W42-B | xTB→Batt isotonic 代理校正与代理上界 | H42b1–H42b10：**10 成立** |
| W42-C | 偶极三源回归分解与 Bland–Altman | H42c1–H42c11：**11 成立** |
| W42-D | 四层轨道抽样律 + 域比 bootstrap/置换 | H42d1–H42d11：**11 成立** |

**合计 45 条判据 = 45 成立 + 0 判否**（本轮无新增在册判否）。四个冻结读数未动，30 项 W42 测试全绿。

## 2. 关键读数与边界

- **四层覆盖**：xTB `237` / QM9 `103` / PubChemQC `205` / Batt `73`，四路交集 `48`；全部 15 个交集逐条复算自洽。
- **两两迁移**（Spearman）：xTB–QM9 `0.8855`、xTB–PubChemQC `0.8824`、xTB–Batt `0.3280`、QM9–PubChemQC `0.9823`、QM9–Batt `0.8177`、PubChemQC–Batt `0.7386`。6 对 bootstrap 95% CI 下界全 > 0、置换 p ≤ 0.006。
- **near_same_level**：QM9 与 PubChemQC 同泛函（B3LYP）同相（气相），ρ = 0.9823、gap MAE = 0.1612 eV ⇒ 判 `near_same_level`。**strict same_level 源数仍为 0**（基组与几何不同）；不得当同层级互换使用。
- **非传递闭合**：凡跨到 xTB 的三角形断口最大 `0.4897`（断链边恒为 xTB–Batt）；QM9–PubChemQC–Batt 的 gap 只有 `0.0790`。四层里的断链在 **xTB–Batt** 这条边上。
- **isotonic 代理上界**：ρ raw `0.3280` → 样本内 `0.5461`、5 折 CV `0.4150`；CV R² `0.2225`；中位数二分 AUC raw `0.6922` → CV `0.7305`，上四分位二分 CV AUC `0.7719`。代理保真度比 `0.3704` ⇒ **xTB 不可代理 ωB97X-V/SMD 通道**。样本内抬升来自并列归并，引用必须用 CV 值。
- **偶极三源归因**：QM9 − PubChemQC bias `−0.0341 D`（CI 含 0）；our − QM9 `+0.3945 D`、our − PubChemQC `+0.5130 D`（CI 均不含 0）；三源 OLS R² `0.6515`、偏置定位比 `0.7691`（同号）。⇒ **~0.4 D 偏置在方法层（xTB vs B3LYP）**，不是某一个源的数据问题。本轮**只归因、不修数、不插补**。
- **抽样律与域比**：6 条曲线最大拟合 rmse `0.0084`，Spearman(s0, 1−τ) = `0.9429`（s0 是保真度函数）；xTB–QM9 在 N=12 的噪声地板 `0.1138`。域比 `2.5817133417` 逐位复现，bootstrap 95% CI `[2.1220, 3.2271]`（sd 0.3033），置换 p `0.0005`（0/2000 超观测）；校正后读数 3.1133 落在未校正 CI 内。

## 3. 包里有什么

| 类别 | 内容 |
| --- | --- |
| 预注册 | `w42_registry_transfer_prereg.json`（`locked_before_run`） |
| 共享计算层 | `w42_common.py` |
| 探针 | 四条 `probes/w42_*.py` |
| 产物 | `probes/artifacts/w42_*.csv`、`w42_near_same_level.json`、`w42_dipole_attribution.json`、两张 `w42_*.png`、四份 `*_summary.json` |
| 报告 | 四份 `reports/w42_*.md` + 立项章/交付说明/工作日志 |
| 测试 | 四份 `tests/test_w42_*.py`（30 项） |
| 导出 | `export_week42_results.py` → `成果输出/week42` |
