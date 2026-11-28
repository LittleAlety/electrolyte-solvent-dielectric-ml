# B01 压力异质性审计
> 生成器 `audit_pressure_heterogeneity/1.0.0` · 2026-11-25T04:42:14Z
> 只测量污染，不修复。修复需改动冻结窗口，属协议决策。

## 一、结论
- 有贡献测量的聚合行：**100**
- `AMBIENT_CONSISTENT`：**83**
- `MIXED_AMBIENT_AND_PRESSURISED`：**12**
- `PRESSURISED_ONLY`：**3**
- `UNCLASSIFIED`：**2**

**受污染聚合行：15**

## 二、决定性案例 EPSV04-R097
四审独立发现的决定性案例: 8 条『观测』实为 101 kPa 至 300 MPa 的压力序列, 报告的 14.26 恰为 100 MPa(14.07) 与 150 MPa(14.45) 的中点

| measurement_id | pressure (kPa) | ε | T (K) | 来源 |
|---|---:|---:|---:|---|
| `MSR-4bc293c7a300c4ff` | 100 | 13.06 | 298.15 | `10.1021/je060248p` |
| `MSR-0d4e51a10408d13e` | 101.3 | 13.06 | 298.15 | `10.1021/acs.jced.8b00755` |
| `MSR-0a8aec348d23bc39` | 50000 | 13.63 | 298.15 | `10.1021/je060248p` |
| `MSR-7922a0cbcac47987` | 100000 | 14.07 | 298.15 | `10.1021/je060248p` |
| `MSR-e63adb460584db04` | 150000 | 14.45 | 298.15 | `10.1021/je060248p` |
| `MSR-fd08b9193d002cd6` | 200000 | 14.77 | 298.15 | `10.1021/je060248p` |
| `MSR-58f93704ee0db53f` | 250000 | 15.06 | 298.15 | `10.1021/je060248p` |
| `MSR-5bfe46a79db53306` | 300000 | 15.33 | 298.15 | `10.1021/je060248p` |

报告的 ε = **14.26**，即 100–150 MPa 的中点。**这不是常压测量。**

## 三、受污染聚合行清单
| aggregate_id | 类别 | 严重度 | 压力范围 (kPa) | v04 ε | 压力是否披露 |
|---|---|---|---|---:|---|
| `v04row-003` | MIXED_AMBIENT_AND_PRESSURISED | HIGH | 100–300000 | 15.736 | true |
| `v04row-005` | MIXED_AMBIENT_AND_PRESSURISED | HIGH | 100–300000 | 12.65 | true |
| `v04row-006` | MIXED_AMBIENT_AND_PRESSURISED | HIGH | 100–300000 | 21.3 | true |
| `v04row-022` | PRESSURISED_ONLY | HIGH | 1000–16000 | 5.3105 | true |
| `v04row-031` | MIXED_AMBIENT_AND_PRESSURISED | HIGH | 100–5091 | 46.05 | true |
| `v04row-040` | MIXED_AMBIENT_AND_PRESSURISED | HIGH | 100–200000 | 10.66 | true |
| `v04row-041` | MIXED_AMBIENT_AND_PRESSURISED | HIGH | 101–307116 | 18.845 | true |
| `v04row-044` | MIXED_AMBIENT_AND_PRESSURISED | HIGH | 91.3–300000 | 25.02 | true |
| `v04row-046` | MIXED_AMBIENT_AND_PRESSURISED | HIGH | 100–300000 | 18.03 | true |
| `v04row-057` | MIXED_AMBIENT_AND_PRESSURISED | HIGH | 91.3–300000 | 33.6 | true |
| `v04row-080` | PRESSURISED_ONLY | HIGH | 1000–16000 | 11.8861 | true |
| `v04row-088` | PRESSURISED_ONLY | HIGH | 1000–16000 | 4.1348 | true |
| `v04row-091` | MIXED_AMBIENT_AND_PRESSURISED | HIGH | 100–41879 | 2.40445 | true |
| `v04row-095` | MIXED_AMBIENT_AND_PRESSURISED | HIGH | 101–5090 | 36.55 | true |
| `v04row-097` | MIXED_AMBIENT_AND_PRESSURISED | HIGH | 100–300000 | 14.26 | true |

## 四、为什么不自动修复
把加压点从窗口剔除会改变 R219 冻结窗口的语义, 从而改变 460/78/170 这些已报告计数. 这必须是一次经过审核的协议变更, 不是审计脚本可以做的.

修复前置条件：
- 四智能体审核确认污染范围
- 明确压力分层规则 (常压带定义)
- 生成新的版本号与哈希
- 不覆盖 J01/J02/J03 与 v04

**若不修复的后果：** 受污染聚合行的 ε 系统性偏高 (压力使 ε 上升), 若直接进入 B05 建模会引入非化学的结构性误差
