# 工作日志 · Week 42（计算密集型：第三外部轨道层、四层迁移网络与三源偶极归因）

> 承接 `reports/work_log_week41.md`。本轮起点：W41 交付（HEAD `04b27e3`，工作树 49 项）。本轮 0 shot，累计仍 19。

## Week 42：把「第三外部层」从一个待办变成一张可复算的四层网络

**目标**：W41-D 登记了三条欠账 —— item 33（缺同层级外部轨道源）、item 34（xTB→Batt 迁移弱）、item 28/30（偶极 ~0.4 D 偏置来源未追溯）。本轮把盘上已有的 PubChemQC（B3LYP/6-31G*//PM6 气相，CC BY 4.0）接成第三外部轨道源，用**四条只读离线计算 lane**一次算完。

**交付**

- **预注册**：`probes/w42_registry_transfer_prereg.json`（`locked_before_run`，r1）。四条 lane 的分母、阈值、bootstrap/置换重抽数、闭合口径跑前写死。
- **共享计算层**：`probes/w42_common.py` —— 四层轨道/三源偶极的只读装载、成对 bootstrap、置换零分布、LF 写盘与判据构造。
- **W42-A 四层轨道迁移网络**（13/13 成立）：覆盖 xTB `237` / QM9 `103` / PubChemQC `205` / Batt `73`，四路交集 `48`；15 个交集全部复算自洽。6 对迁移（各 2000 bootstrap + 2000 置换）：ρ(xTB,QM9)=`0.8855`、ρ(xTB,PubChemQC)=`0.8824`、ρ(xTB,Batt)=`0.3280`、ρ(QM9,PubChemQC)=`0.9823`、ρ(QM9,Batt)=`0.8177`、ρ(PubChemQC,Batt)=`0.7386`。**QM9–PubChemQC 判 near_same_level**（同泛函+同相，gap MAE `0.1612 eV`）；strict same_level 仍 0。三角形最大断口 `0.4897`（断链边恒 xTB–Batt）。
- **W42-B isotonic 代理上界**（10/10 成立）：73 化合物上保序回归，ρ raw `0.3280` → 样本内 `0.5461`、5 折 CV `0.4150`；CV R² `0.2225`；中位数二分 AUC raw `0.6922` → CV `0.7305`、上四分位 CV `0.7719`；代理保真度比 `0.3704`。
- **W42-C 偶极三源归因**（11/11 成立）：QM9 − PubChemQC bias `−0.0341 D`（CI 含 0），our − QM9 `+0.3945 D`、our − PubChemQC `+0.5130 D`（CI 不含 0）；三源 OLS R² `0.6515`、定位比 `0.7691`。偏置定位在方法层。
- **W42-D 抽样律 + 域比重抽**（11/11 成立）：6 条曲线最大 rmse `0.0084`，Spearman(s0,1−τ)=`0.9429`；xTB–QM9 N=12 噪声地板 `0.1138`。域比 `2.5817133417`、CI `[2.1220,3.2271]`、sd `0.3033`、置换 p `0.0005`。

**关键读数**：判据 **13 + 10 + 11 + 11 = 45 条全部成立**（本轮无新增判否）；shot 0（累计仍 19）；四个冻结读数一个不动；W42 测试全绿。

**判否与口径**

- 本轮无新增判否。三条「读数是弱/受限」的事实被写清：① xTB–Batt ρ 仅 0.328、isotonic CV 上界 0.415；② 同泛函同相只到 near_same_level（基组/几何仍差），strict same_level = 0；③ 偶极偏置已定位但**仍不修数**。
- 单调变换在无并列时不改 Spearman，样本内抬升来自并列归并 ⇒ 引用必须用 CV 值。
- 外部层数值仍只作只读对照，不入标签池/特征列；域比是相关读数不是因果。

**产物**

`probes/w42_registry_transfer_prereg.json`、`probes/w42_common.py`、四条 `probes/w42_*.py`；`probes/artifacts/w42_*.csv`、`w42_near_same_level.json`、`w42_dipole_attribution.json`、`w42_orbital_transfer_network.png`、`w42_proxy_calibration.png`、`w42_dipole_sources.png`、`w42_sampling_law.png`、四份 `*_summary.json`；`reports/w42_*.md`、`reports/week42_project_charter.md`、`reports/week42_delivery_readme.md`、本日志；四份 `tests/test_w42_*.py`；`probes/export_week42_results.py`。

**下一步（登记）**

- 用 near_same_level 的 PubChemQC 层给轨道通道做**排序先验加权**前，先补 strict same-level 源或把基组/几何残差量化成适用域条款。
- 偶极偏置的方法层定位已具备「可更正」的前提，但更正本身要单独预注册（单位/构象口径 + 对既有读数的影响）。
