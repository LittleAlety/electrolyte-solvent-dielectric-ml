# 方法学冻结 v2 — ORCA r2SCAN-3c

- 状态: **FROZEN**
- 程序: ORCA 6.1.1 @ `/home/pengqihang/project/soft/orca`
- 方法: `r2SCAN-3c` (r2SCAN + D4 + gCP + def2-mTZVPP (ORCA built-in))
- 电荷/多重度: 0 / 1

## 预检闸门

- PASS — orca_runs_12_of_12_sp
- PASS — orca_runs_12_of_12_opt
- PASS — optimization_converged_12_of_12
- PASS — polarizability_parsed_12_of_12
- PASS — parser_matches_independent_orca_run

## 三层设计

- **fixed_geometry_single_point**: 分离电子结构方法差异: 只有方法变, 几何不变, 因此描述符差异可归因于方法
- **optimised_geometry**: 生产特征层: 几何与性质来自同一方法, 内部一致, 但不能与 v6.0 一一对比
- **v60_b3lyp_reference**: 历史对照层, 保留不动, 用于三方分解方法/几何效应

## 本冻结不声称的事

- 预检通过不等于 239 个分子都会成功; 失败必须保留失败证书, 不得从分母删除
- r2SCAN-3c 是为几何与热化学参数化的复合方法, 它的偶极/极化率可靠性由本预检的性质层面检查支持, 不能由能量收敛自动推出
- 偶极与极化率通过预检不代表所有描述符都正确
