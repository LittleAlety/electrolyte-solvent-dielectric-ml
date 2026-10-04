# W47-C Lane C 协议锁定与算力欠账登记

只读 lane，0 shot。本环境无 ORCA，本件只锁协议、登记欠账、给排期估算，不产数值。

## 1 计划条目（21 项）

| id | 组 | 目标 | 状态 |
| --- | --- | --- | --- |
| d2_definition | d2_r2scan3c | definition | pending_orca_compute |
| d2_method | d2_r2scan3c | method | pending_orca_compute |
| d2_geometry | d2_r2scan3c | geometry | pending_orca_compute |
| d2_level | d2_r2scan3c | level_declaration | pending_orca_compute |
| d2_conformer_sampling | d2_r2scan3c | conformer_sampling | pending_orca_compute |
| d2_conformer_report | d2_r2scan3c | conformer_report | pending_orca_compute |
| d3_vertical | d3_ddcosmo | vertical | pending_orca_compute |
| d3_adiabatic | d3_ddcosmo | adiabatic_component | pending_orca_compute |
| d3_dielectric_pipeline | d3_ddcosmo | dielectric_pipeline | pending_orca_compute |
| d3_level | d3_ddcosmo | level_declaration | pending_orca_compute |
| nitrile_GN_somo_spatial_extent | nitrile_check | GN | pending_orca_compute |
| nitrile_GN_dipole_bound_state_test | nitrile_check | GN | pending_orca_compute |
| nitrile_GN_legality_registry_entry | nitrile_check | GN | pending_orca_compute |
| nitrile_MPN_somo_spatial_extent | nitrile_check | MPN | pending_orca_compute |
| nitrile_MPN_dipole_bound_state_test | nitrile_check | MPN | pending_orca_compute |
| nitrile_MPN_legality_registry_entry | nitrile_check | MPN | pending_orca_compute |
| nitrile_BC_somo_spatial_extent | nitrile_check | BC | pending_orca_compute |
| nitrile_BC_dipole_bound_state_test | nitrile_check | BC | pending_orca_compute |
| nitrile_BC_legality_registry_entry | nitrile_check | BC | pending_orca_compute |
| rerun_lane_a | rerun | lane_a_main_judgment | pending_after_orca_compute |
| dipole_transfer_v1 | external | dipole_transfer_v1 | registered_not_authorized |

## 2 腈类专项（V4：Timerghazin 2008 偶极束缚态警告）

- 溶剂 x 项 = 9 / 9；齐备 = 是。
- 三项分别为 GN / MPN / BC 的 somo_spatial_extent、dipole_bound_state_test、legality_registry_entry。

## 3 算力估算（排期用，不是读数）

- D2：N_core * 2 * n_conformers = 42。
- D3：N_core * 4 (NE/EQ x neutral/anion) = 28。
- 腈类：n_nitrile * 2 = 6。
- 合计 = **76** 个 ORCA 单点（估算）。

## 4 判据

| id | 判据 | 值 | 阈 | 判决 |
| --- | --- | --- | --- | --- |
| H47c1 | D2 (r2SCAN-3c) 协议六项齐备（定义/方法/几何/层级/构象采样/构象散布） | {"n": 6, "expected": 6} | {"expected": 6} | 成立 |
| H47c2 | D3 (ddCOSMO) 协议四项齐备（垂直 NE / 绝热 EQ / 介电管线 / 层级） | {"n": 4, "expected": 4} | {"expected": 4} | 成立 |
| H47c3 | 腈类三项 x 3 溶剂 = 9 行齐备（缺一项即该溶剂检查判据不成立） | {"n": 9, "pairs": [["BC", "dipole_bound_state_test"], ["BC", "legality_registry_entry"], ["BC", "somo_spatial_extent"], ["GN", "dipole_bound_state_test"], ["GN", "legality_registry_entry"], ["GN", "somo_spatial_extent"], ["MPN", "dipole_bound_state_test"], ["MPN", "legality_registry_entry"], ["MPN", "somo_spatial_extent"]], "complete": true} | {"expected_pairs": 9} | 成立 |
| H47c4 | 计算可得性照实登记：orca_available = false、全部条目 pending/declared（不强建数值） | {"orca_available": false, "statuses": ["pending_after_orca_compute", "pending_orca_compute", "registered_not_authorized"], "compute_status": {"orca_available": false, "status": "pending_orca_compute", "reason": "本环境无 ORCA 可执行体；Lane A 先出可执行版，本 lane 为计划内复跑而非前置依赖。", "reruns": "完成后按 w47_anchor_prereg.json 同一口径重跑 Lane A，两版读数并列登记，不掩盖。"}} | {"orca_available": false, "all_pending_or_declared": true} | 成立 |
| H47c5 | D2 构象散布必须报（conformer_report_required = true，敏感度量级约 0.13 V） | {"conformer_report_required": true} | {"required": true} | 成立 |
| H47c6 | 计划内复跑登记：r2SCAN-3c 全层后按同一预注册重跑 Lane A，两版并列 | {"rerun_rows": [{"item_id": "rerun_lane_a", "group": "rerun", "target": "lane_a_main_judgment", "requirement": "r2SCAN-3c 全层完成后按 w47_anchor_prereg.json 同一口径重跑；两版并列登记", "status": "pending_after_orca_compute", "evidence": "probes/w47_anchor_prereg.json"}]} | {"status": "pending_after_orca_compute"} | 成立 |
| H47c7 | dipole_transfer_v1 维持 registered_not_authorized（本轮不碰、不授权修数） | {"rows": [{"item_id": "dipole_transfer_v1", "group": "external", "target": "dipole_transfer_v1", "requirement": "维持 registered_not_authorized；本轮不碰、不授权任何修数", "status": "registered_not_authorized", "evidence": "reports/decisions_log.md W43-B 登记"}]} | {"status": "registered_not_authorized"} | 成立 |
| H47c8 | 算力估算可复算（公式 + 值），且标注为估算而非读数 | {"basis": {"core_set_size": 7, "conformers_min": 3, "nitrile_solvents": ["GN", "MPN", "BC"]}, "d2_r2scan3c": {"formula": "N_core * 2 * n_conformers", "value": 42}, "d3_ddcosmo": {"formula": "N_core * 4 (NE/EQ x neutral/anion)", "value": 28}, "nitrile_check": {"formula": "n_nitrile * 2", "value": 6}, "total": 76, "disclaimer": "排期用估算，不是读数；实际单点数以完成后的 ORCA 日志计数为准。"} | {"total_reported": true} | 成立 |
| H47c9 | 输入（Lane C 预注册 + Lane A 预注册）sha256 未变 | {"inputs_unchanged": true} | {"unchanged": true} | 成立 |
