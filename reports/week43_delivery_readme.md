# Week 43 交付说明

**本轮性质**：治理与量化周。把 W42 登记的两条欠账（`near_same_level` 不得当同层级互换、偶极校正要单独预注册）写成机器件，并补一条层准入规则与一条仓库级治理台账守卫。
**shot 账本**：**0 shot，累计仍 19**。四条 lane 全是只读离线统计与治理件。
**冻结读数**：`0.4091179943351143` / `0.4766400383507876` / `0.5861142332208197` / `0.6216672295270079`，一个不动。

---

## 1. 判据总账

| lane | 标题 | 判据 |
| --- | --- | --- |
| W43-A | 层级残差分解与适用域条款 | H43a1–H43a15：**15 成立** |
| W43-B | 偶极校正协议预注册 + 离线影响评估 | H43b1–H43b12：**12 成立** |
| W43-C | 外部轨道层当排序先验的准入规则 | H43c1–H43c10：**10 成立** |
| W43-D | 仓库级治理台账守卫 | H43d1–H43d8：**8 成立** |

**合计 45 条判据 = 45 成立 + 0 判否**（本轮无新增在册判否）。四个冻结读数未动，36 项 W43 测试全绿（含 `tests/test_repo_hygiene.py`）。

## 2. 关键读数与边界

- **层级残差**：扩展层 `themol_orbital_layer_expanded.csv` 5117 行（GFN2-xTB//B3LYP-D3(BJ)/DZVP 气相单点、DFT 几何），xTB–Batt 4668 行 ρ `0.5985`；名册 73 行只有 `0.3280` ⇒ **名册子集是悲观尾**。
- **几何残留**（同方法换几何，n=137）：ρ `0.9916`、MAE `0.1599 eV` ⇒ **保序、平移**（level-shift，不是 rank-break）。
- **基组残留**（near_same_level，n=103）：|Δ|≤0.2 eV 覆盖 `0.6893` ⇒ `near_same_level` 只能当**带 ±0.2 eV 容差的替换上界**，`strict same_level` 计数为 0。
- **isotonic 代理上界**（4668 行）：CV ρ `0.5995`、CV R² `0.4041`、CV AUC `0.7957`。
- **偶极协议**：`dipole_transfer_v1` 状态 **`registered_not_authorized`**；n=103 仿射 slope `0.7506` / R² `0.6142`；LOO 偏置 `0.3945 D`、CI `[0.2248, 0.5788]` 不含 0；离线域比 2.5817 → `2.4696–3.1726`（|Δ| ≤ 1.0）。**修数仍未授权**。
- **层准入**：xTB defer / QM9 defer / **PubChemQC admit**（score `0.8394`）/ Batt reject；`near_same_level(qm9,pubchemqc)` **未自动准入**。
- **治理守卫**：扫 `337` 个 JSON；登记负结果并集 == 已知 **9** 条（W43 无新增）；冻结读数越界 **0**；41 份带 ledger 的 summary 累计 shot 单调不减、上限 **19**；W43 各件 shots = 0。

## 3. 复现

```powershell
$env:PYTHONIOENCODING="utf-8"; $env:OMP_NUM_THREADS=1; $env:OPENBLAS_NUM_THREADS=1
python probes\w43_layer_residual.py
python probes\w43_dipole_protocol.py
python probes\w43_prior_admission.py
python probes\w43_governance_ledger.py
python -m pytest tests\test_repo_hygiene.py tests\test_w43_layer_residual.py tests\test_w43_dipole_protocol.py tests\test_w43_prior_admission.py tests\test_w43_governance_ledger.py -q -p no:cacheprovider
python probes\export_week43_results.py --overwrite
```

## 4. 产物清单

- 预注册：`probes/w43_protocol_prereg.json`（`locked_before_run`，r1）。
- 探针：`probes/w43_common.py`、`w43_layer_residual.py`、`w43_dipole_protocol.py`、`w43_prior_admission.py`、`w43_governance_ledger.py`、`export_week43_results.py`。
- 产物：`probes/artifacts/w43_layer_residual_pairs.csv`、`w43_geometry_residual.csv`、`w43_basis_residual.csv`、`w43_residual_descriptors.csv`、`w43_applicability_clause.json`、`w43_dipole_protocol.json`、`w43_dipole_impact.csv`、`w43_prior_admission.csv`、`w43_prior_admission.json`、`w43_governance_ledger.csv`、`w43_governance_ledger.json`、`w43_layer_residual.png` 与四份 `*_summary.json`。
- 报告：`reports/w43_layer_residual.md`、`w43_dipole_protocol.md`、`w43_prior_admission.md`、`w43_governance_ledger.md`、`week43_project_charter.md`、`week43_delivery_readme.md`、`work_log_week43.md`。
- 测试：`tests/test_w43_layer_residual.py`、`test_w43_dipole_protocol.py`、`test_w43_prior_admission.py`、`test_w43_governance_ledger.py`。
