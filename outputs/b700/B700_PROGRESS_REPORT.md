# 已废弃：请阅读 `B700_FINAL_REPORT_v7.md`

本文件是 B700 执行过程中的**中间进度报告**，其中 E1/E2/E4/E6 的数字来自
B706 的首轮实现。该实现遗漏了"训练折内标准化"步骤（v6.0 `fit_predict` 的
标准做法），导致 1e-54 量级的 `mu_sq_over_Vm` 被 ridge 惩罚吞掉，
`X0 + mu²/Vm` 臂与纯结构臂给出完全相同的结果。

协议修正后（`scripts/b700/run_b706_experiments.py::fit_predict`，
在训练折内标准化、测试点用同一均值/方差变换），结果发生变化，其中
`X0 + mu²/Vm` 成为最强特征块，Top-10 regret 从 26.97 降到 2.778。

**因此本文件中的所有模型性能数字均已作废，不得引用。**

当前有效的报告与数字来源：

| 内容 | 文件 |
|---|---|
| 最终科学报告 | [B700_FINAL_REPORT_v7.md](B700_FINAL_REPORT_v7.md) |
| 机器可读数字汇总（唯一数字来源） | [B700_FINAL_SUMMARY.json](B700_FINAL_SUMMARY.json) |
| 修正后的 E1/E2/E4/E6 | `B706_experiments_report_sp.json` / `_opt.json` |
| 契约测试 | `tests/test_b700_orca/test_b700_contracts.py` |
