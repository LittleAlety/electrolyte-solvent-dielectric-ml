# 工作日志 · Week 43（层级残差适用域、偶极校正协议、层准入与治理守卫）

> 承接 `reports/work_log_week42.md`。本轮起点：W42 交付（HEAD `04b27e3`，工作树 90 项）。本轮 0 shot，累计仍 19。

## Week 43：把两条欠账写成机器件

**目标**：W42 登记 item 36（`near_same_level` 不得当同层级互换）与 item 37（偶极校正要单独预注册）。本轮用四条只读 lane 一次执行，并补两条新登记。

**交付**

- **预注册**：`probes/w43_protocol_prereg.json`（`locked_before_run`，r1）。四条 lane 的分母、阈值、bootstrap/置换重抽数、准入硬门与守卫不变式跑前写死。
- **共享层**：`probes/w43_common.py` —— 扩展层 `themol_orbital_layer_expanded.csv` 的只读装载、名册描述符联结、W42 迁移表读取与全仓 JSON 台账迭代。
- **W43-A 层级残差分解**（15/15 成立）：扩展层 5117 行；xTB–Batt 4668 行 ρ `0.5985`（名册 73 行仅 `0.3280`）；几何残留 n=137 ρ `0.9916` / MAE `0.1599 eV`；基组残留 |Δ|≤0.2 eV 覆盖 `0.6893`；isotonic 样本内 ρ `0.6172` / 5 折 CV ρ `0.5995` / CV R² `0.4041`；CV AUC `0.7957`。条款 `w43_applicability_clause.json`：同方法 `rank_preserving`、基组 `usable_as_bound`、跨方法 `not_same_level`，`strict same_level` = 0。
- **W43-B 偶极校正协议预注册**（12/12 成立）：协议 `dipole_transfer_v1`，状态 `registered_not_authorized`；三变体 + 适用范围 + 回退 + LOO 失效闸；n=103 仿射 slope `0.7506` / R² `0.6142`，MAE `0.6103 → 0.4605 D`，LOO 偏置 `0.3945 D`、CI `[0.2248, 0.5788]` 不含 0；legacy 变体逐位复现域表 `mu_corr_D`（max|Δ| ≈ 1.8e-15）；离线域比 2.5817 → `2.4696–3.1726`。**标签一字未改**。
- **W43-C 层准入规则**（10/10 成立）：xTB defer（ρ 0.3280 未达 0.5 门）/ QM9 defer（元数据缺项）/ **PubChemQC admit**（score `0.8394`）/ Batt reject（标签目标）；`near_same_level(qm9,pubchemqc)` 未自动准入。
- **W43-D 治理台账守卫**（8/8 成立）：扫 `337` 个 JSON；登记负结果并集 == 已知 9 条；冻结读数越界 0；带 ledger 的 41 份 summary 累计 shot 单调不减、上限 19；W43 各件 shots = 0。
- **测试与集成**：`tests/test_w43_*.py`（36 项）全绿；论文 v3 → v1.7 §3.28；README §0/§5/§7/§8/§11；`reports/decisions_log.md` §28.98。

**坑与更正**

- 扩展层的 `in_epsilon_roster` 标记（142）与「名册键 ∩ 扩展层且双端 gap 齐备」（45）不是一回事；描述符回归只能用后者，且 45 行样本内 R² 不作外推（报告已注明）。
- 域表 `mu_corr_D` 是**带符号常量**偏移（−0.3914 D），不是仿射；协议把它登记为 legacy 变体用于精确复现，仿射只作敏感性变体。
- 探针文件里的报告文本含反引号时，Codex 的 JS 模板写入会被截断；本轮统一用占位符替换后再落盘。

**下一步（已登记）**

- 见 README §11 第 36–39 条：仍缺 strict same-level 独立源；偶极修数仍未授权；层准入表与治理守卫须逐轮重跑。
