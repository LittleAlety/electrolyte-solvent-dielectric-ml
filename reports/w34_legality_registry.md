# W34-A：还原轴态合法性注册表 + 四通道看板 + 门禁守卫

**性质**：后验注册表/看板（只读四张冻结表）。**不占主记分牌 shot**（累计仍 19）；不重跑 xTB / ORCA、不拟合模型、不联网。

## 0. 一句话

- **门禁从报告里的表升成盘上的权威列**：注册表 1028 行 = GFN2 4 x 246 + ORCA 配对 2 x 22。
- **守卫与读数在同一次调用**：`redox_reading` 先过门禁再算 τ_b，合法 < 5 抛 `RedoxGateRefusal`，不返回 None —— 下游无法绕过门禁，也无法把拒答当缺失值插补。
- **看板把四通道并成一张入口表**：介电 s0 = 0.4737、黏度 0.4903、轨道 0.5828、氧化还原 0.3695；只有氧化还原通道带门禁（GFN2 气相合法 52/246；ORCA 气相合法 0/22）。
- **气相合法率仍是那 21.1%**（52/246）：门禁不是新算力，它只是把 W33-A 的判定钉在盘上，让「还原轴必须先在定义域内」成为可执行约束。

## 1. 注册表（`data/processed/redox_state_legality_registry.csv`）

| 层级 | 介质 | eps | 行数 | 合法 | 因几何 | 因不束缚 | 因 EA 非正 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gfn2 | 气相 | 1.0 | 246 | 52 | 5 | 188 | 1 |
| gfn2 | THF | 7.6 | 246 | 154 | 4 | 86 | 2 |
| gfn2 | 苯甲醛 | 18.0 | 246 | 154 | 4 | 87 | 1 |
| gfn2 | 水 | 80.4 | 246 | 161 | 5 | 80 | 0 |
| orca | ORCA 气相 | 1.0 | 22 | 0 | 0 | 22 | 0 |
| orca | ORCA SMD 乙腈 | 35.7 | 22 | 2 | 0 | 16 | 4 |

- 关键不变量：`legal == geom_ok AND homo_bound AND ea_positive`；`reason` 按 geom > homo > ea 取首个失败条款。
- 拒答不是缺失值：拒答 = 「在本层不可宣读」的明确结论，不得插补、不得赋伪值、不得静默丢弃。

## 2. 门禁守卫

```python
from w34_legality_registry import redox_reading, RedoxGateRefusal
reading = redox_reading(census_rows, orca_rows, 'gfn2', 'gas')   # 合法 52 >= 5 -> 返回读数
redox_reading(census_rows, orca_rows, 'orca', 'gas')             # 合法 0 < 5 -> raise RedoxGateRefusal
```

- 守卫与读数在**同一次调用**里，调用方无法绕过门禁；拒答时抛异常，不返回 None。
- 复现锚：`gfn2/gas` 合法子集 τ_b = 0.7450980392157、`gfn2/water` = 0.8119565217391（与 W33-A 逐位一致）。

## 3. 四通道看板

| 通道 | s0 | N_pop | sd@N=12 | 所需 N（sd<=0.05） | 门禁 | 可否宣读 |
| --- | --- | --- | --- | --- | --- | --- |
| 介电常数 eps | 0.4737 | 205 | 0.132683 | 178.9 | 否 | 可宣读 |
| 分子轨道 HOMO/LUMO/IP/EA | 0.5828 | 29515 | 0.168207 | 1987.0 | 否 | 可宣读 |
| 氧化还原自由能 | 0.3695 | 392 | 0.105010 | 268.9 | 是 | GFN2 可宣读；ORCA 不可判定 |
| 黏度 eta | 0.4903 | 708 | 0.140340 | 481.8 | 否 | 可宣读 |

## 4. 判据（H34a–H34e）

- **H34a 成立**：注册表规模：GFN2 四介质 x 246 + ORCA 两介质 x 22（读数 1028.000000 对阈值 1028.000000）。
- **H34b 成立**：注册表 legal 与 W33-A gates.csv 逐条一致（不一致的介质数）（读数 0.000000 对阈值 0.000000）。
- **H34c 成立**：reason 优先级（geom > homo > ea）与 legal 合取一致（读数 0.000000 对阈值 0.000000）。
- **H34d 成立**：守卫行为：ORCA 气相抛拒答 / GFN2 气相放行且 τ_b 复现 W33-A（读数 1.000000 对阈值 1.000000）。
- **H34e 成立**：看板四通道齐备且 redox 行带门禁状态（读数 0.000000 对阈值 0.000000）。

## 5. 口径与边界

- 注册表逐位派生自冻结表与 W33-A 预注册门禁；不改门禁规则、不改阈值、不改拒答优先级。
- 拒答不是缺失值：守卫抛错是「在本层不可宣读」的明确结论，不得插补、不得赋伪值、不得静默丢弃。
- 跨层级只在配对集上比裁决一致性，不把两层数值结果混在同一张记分牌上。
- 不改 METRIC_NAMES、不新增特征列、不动四个冻结读数与 ε 主记分牌。
- 本件是后验注册表/看板，不占 shot、不得当作预注册结论引用。

## 6. 产物与复算

- `probes/w34_legality_registry.py`、`data/processed/redox_state_legality_registry.csv`、`probes/artifacts/w34_legality_registry_summary.json`、`probes/artifacts/w34_channel_dashboard.csv`、`probes/artifacts/w34_channel_dashboard.md`、`probes/artifacts/w34_legality_registry.png`、`reports/w34_legality_registry.md`
- 复算：`python probes\w34_legality_registry.py`（零网络、零新算力，约数秒）。
