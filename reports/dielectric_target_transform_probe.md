# 杠杆 3：log(ε−1) 目标 + 稳健损失（Week 14 R2 攻坚）

> 本文由 `probes/dielectric_target_transform_probe.py` 从 `probes/dielectric_target_transform_probe_summary.json` 确定性渲染；数字与摘要同源，改一处必须重跑脚本。

## 一、口径与预注册

- 预注册：`probes/dielectric_r2_levers_prereg.json`（status=`locked_before_run`，sha256=`ab3503c037f05ac398b3c0c59d0e4845943d49fa5a5349fa46b8944f2bc1bdaa`），判据先锁后跑、事后不放宽
- 主记分牌：457 行 / 97 化合物，GroupKFold by InChIKey，5 折 × 10 重复，seed=42，min_test_rows_per_fold=2
- 基准读数（本脚本内重跑，走冻结的 `run_protocol`）：0.4091179943351143（已发布值 0.4091179943351143，|Δ| = 0.000e+00）→ 复现成立

## 二、变换契约

- 训练目标：`y_train = ln(epsilon - 1)`
- 反变换：`prediction = exp(y_hat) + 1, clipped at 1.0 exactly like the frozen hybrid`
- 模型改动：objective `reg:squarederror` → `reg:pseudohubererror`，huber_slope = 1.0；其余超参逐项不变
- 混合表示合并口径：the two single-representation predictions are back-transformed first and averaged on the raw scale, mirroring the frozen hybrid which also averages raw predictions
- 模型签名：`{"colsample_bytree":0.8,"huber_slope":1.0,"learning_rate":0.05,"max_bin":64,"max_depth":2,"n_estimators":200,"n_jobs":1,"objective":"reg:pseudohubererror","random_state":42,"reg_lambda":1.0,"subsample":0.8,"tree_method":"hist"}`

## 三、四臂读数（原始尺度，混合表示 `Morgan+Physical`）

| 臂 | R² 均值 | R² 标准差 | MAE | Spearman | MAE·ε>60 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 基准臂（原样重跑） | 0.409118 | 0.088967 | 8.0407 | 0.7763 | 55.7131 |
| 变换臂（ln(ε−1) + pseudo-Huber） | 0.303746 | 0.067713 | 7.8908 | 0.7908 | 67.3981 |
| 安慰剂臂（同变换、标签打乱） | -0.112559 | 0.013394 | 12.5999 | 0.0630 | 75.2334 |
| Dummy（折内训练均值） | -0.068711 | 0.047360 | 14.0197 | -0.3535 | 68.7348 |
| Dummy（安慰剂臂自身标签的折内均值） | -0.006352 | 0.003559 | 13.4258 | -0.0721 | 70.2431 |

## 四、log 空间诊断（非判据，照实报）

- 变换臂 log 空间 R² = 0.550558，同一臂原始尺度 R² = 0.303746，差 = +0.246813
- 变换臂 log 空间 Spearman = 0.790839，原始尺度 Spearman = 0.790839
- 「只在 log 空间成立的增益」判定：成立（反变换后消失）
- 安慰剂臂 log 空间 R² = -0.038577（打乱标签后 log 空间同样无信号）

## 五、判决

- 变换臂 − 基准臂（原始尺度）：ΔR² = -0.105372，ΔMAE = -0.1499，ΔSpearman = +0.0146，ΔMAE·ε>60 = +11.6849
- 安慰剂臂 R² = -0.112559，平凡地板（折内训练均值）R² = -0.006352，距地板 -0.106207，判据「不高于地板 +0.02」→ 塌缩成立
- 安慰剂臂 − 基准臂（仅供对照，非判据）：ΔR² = -0.521677
- 口径说明：the pre-registration names no reference for the collapse delta; measured against the real-label baseline the test is unsatisfiable by construction, so the control is measured against the no-information floor and both readings are reported
- 塌缩基准敏感性：主判据读法塌缩=成立；预注册字面读法塌缩=不成立；本杠杆按 ΔR² 的判决为 `dead`（低于枪毙线，与塌缩读法无关）
- 判据（照抄预注册）：通过 = 原始尺度 ΔR² ≥ +0.02；枪毙 = 原始尺度 ΔR² < +0.005；只在 log 空间涨而反变换后消失 = 死
- **判决：`dead`**
  - raw-scale grouped R2 moved by -0.1054, below the +0.005 kill line
  - the log-space R2 sits +0.2468 above the raw-scale R2 of the same arm: the dividend does not survive the back-transformation
- 是否进入合并臂：否
- shots 计数：本杠杆 1 枪

## 六、诚实边界

- 主记分牌是 97 化合物 / 457 行的 `paired_base` 池，**不是** v1.0 的 236 行池；本报告的 R² 不得与 v1.0 headline 0.364 直接比大小，两个数不在同一目标池上。
- 变换臂的拟合路径是本仓库唯一一处对冻结训练循环的重写，原因是`fit_predict_representation` 会在模型自身尺度上做 1.0 截断，log 空间下会改写预测值；基线臂仍走冻结的 `run_protocol`，因此复现对账是逐位可比的。
- 随机行切分（random_row）未进入任何判决，本脚本没有构造它。
- 测试残差没有参与特征选择：目标变换与损失在跑之前就写在预注册里。
- 评分池、折号、度量分母在本轮内未改动；变换不改变评分行、不改变折号。
- `dummy_control` 是打乱标签的安慰剂臂，`dummy_mean_reference` 是折内训练均值的平凡地板；两者都不是「模型」，存在是为了让增益有对照。
- shots 计数写入 `reports/decisions_log.md` §12 由主线集成者执行；本脚本不修改该文件。

