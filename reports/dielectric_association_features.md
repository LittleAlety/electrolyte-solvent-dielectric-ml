# 杠杆 2：缔合盲区靶向特征（Week 14 R2 攻坚）

> 本文由 `probes/dielectric_association_features_probe.py` 从 `probes/dielectric_association_features_summary.json` 确定性渲染；数字与摘要同源，改一处必须重跑脚本。

## 一、口径与预注册

- 预注册：`probes/dielectric_r2_levers_prereg.json`（status=`locked_before_run`，sha256=`ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa`），判据先锁后跑、事后不放宽
- 主记分牌：457 行 / 97 化合物，GroupKFold by InChIKey，5 折 × 10 重复，seed=42，min_test_rows_per_fold=2
- 折划分与评分行：直接复用 `masked_splits` + `drop_thin_folds` + `run_protocol`，实测折数 = 50，三个臂共享同一份评分折号（the scored side of every fold is identical across the three arms）
- 基准读数（本脚本内重跑）`paired_base` 混合表示 R² = 0.4091179943351143（已发布值 0.4091179943351143，|Δ| = 0.000e+00，容差 1e-09）→ 复现成立

## 二、新增特征块

| 列 | 最小 | 最大 | 均值 |
| --- | ---: | ---: | ---: |
| `hbond_donor_sites` | 0.0000 | 5.0000 | 0.2666 |
| `hbond_acceptor_sites` | 0.0000 | 6.0000 | 1.1981 |
| `donor_site_density` | 0.0000 | 0.6667 | 0.0454 |
| `acceptor_site_density` | 0.0000 | 0.5000 | 0.1842 |
| `intramolecular_hbond_competition` | 0.0000 | 6.0000 | 0.1789 |
| `donor_acceptor_pair_density` | 0.0000 | 0.2500 | 0.0147 |

- 打分子 SMILES 解析失败：0 行（失败行填 0 并计数，不静默）
- 给体 SMARTS：`[$([O;H1,H2]),$([N;H1,H2,H3]),$([S;H1])]`；受体 SMARTS：`[$([O;H0,H1]),$([N;H0,H1,H2]),$([S;H0,H1])]`
- 竞争计数口径：donor~*~acceptor (2 bonds) and donor~*~*~acceptor (3 bonds), de-duplicated by atom pair

## 三、三臂读数（混合表示 `Morgan+Physical`）

| 臂 | R² 均值 | R² 标准差 | MAE | Spearman | MAE·ε>60 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 基准臂（原样重跑） | 0.409118 | 0.088967 | 8.0407 | 0.7763 | 55.7131 |
| 杠杆臂（+6 特征） | 0.397234 | 0.056606 | 7.9206 | 0.7865 | 59.4878 |
| 安慰剂臂（同特征、标签打乱） | -0.052736 | 0.010970 | 13.8556 | 0.0334 | 70.0208 |
| Dummy（折内训练均值） | -0.068711 | 0.047360 | 14.0197 | -0.3535 | 68.7348 |
| Dummy（安慰剂臂自身标签的折内均值） | -0.006352 | 0.003559 | 13.4258 | -0.0721 | 70.2431 |

## 四、判决

- 杠杆臂 − 基准臂：ΔR² = -0.011884，ΔMAE = -0.1200，ΔSpearman = +0.0102，ΔMAE·ε>60 = +3.7747
- 安慰剂臂 R² = -0.052736，平凡地板（折内训练均值）R² = -0.006352，距地板 -0.046384，判据「不高于地板 +0.02」→ 塌缩成立
- 安慰剂臂 − 基准臂（仅供对照，非判据）：ΔR² = -0.461854
- 口径说明：the pre-registration names no reference for the collapse delta; measured against the real-label baseline the test is unsatisfiable by construction, so the control is measured against the no-information floor and both readings are reported
- 塌缩基准敏感性：主判据读法塌缩=成立；预注册字面读法塌缩=不成立；本杠杆按 ΔR² 的判决为 `dead`（低于枪毙线，与塌缩读法无关）
- 判据（照抄预注册）：通过 = ΔR² ≥ +0.02；枪毙 = ΔR² < +0.005；只有 mae_gt60 改善而总 R² 不升 = 死
- **判决：`dead`**
  - grouped R2 moved by -0.0119, below the +0.005 kill line
- 是否进入合并臂：否
- shots 计数：本杠杆 1 枪（预注册口径：每一次对主记分牌的评分尝试都计）

## 五、诚实边界

- 主记分牌是 97 化合物 / 457 行的 `paired_base` 池，**不是** v1.0 的 236 行池；本报告的 R² 不得与 v1.0 headline 0.364 直接比大小，两个数不在同一目标池上。
- 随机行切分（random_row）未进入任何判决，本脚本甚至没有构造它。
- 测试残差没有参与特征选择：六个描述符在跑之前就写在预注册里，列名与实现一一对应。
- 评分池、折号、度量分母在本轮内未改动；只有特征侧变化，且只在新增列上变化，v03 既有列逐列未动。
- `dummy_control` 是打乱标签的安慰剂臂，`dummy_mean_reference` 是折内训练均值的平凡地板，两者都不是「模型」；它们的存在是为了让增益有对照。
- shots 计数写入 `reports/decisions_log.md` §12 由主线集成者执行；本脚本不修改该文件。

