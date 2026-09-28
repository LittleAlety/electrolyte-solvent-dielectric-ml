## 28.61 高 ε 区正式拒答机制：可执行规则、出口码与冻结注册表拒答规模（2026-09-28）
|
**定位**：本件是 Week 20 lane W20-5（§28.61）的落地章，把「ε > 60 用现有特征不可解」从一句判断变成**可执行拒答规则**，并在冻结注册表上量出被拒规模；不造新科学。全文见 `reports/w20_refusal.md`，机器可读规则集见 `probes/artifacts/w20_refusal_rule.json`。|
**纪律**：`produces_reading = false`、`shot_number_taken = null`、`scoreboard_attempts_delta = 0`、`reaxys_values_used = 0`、`promoted = false`；主记分牌**累计 11 次不变**；不动任何冻结件。|
**① 可执行拒答规则（`probes/artifacts/w20_refusal_rule.json`）**：`w20_refusal_high_eps_v1`（谓词 `epsilon > 60.0`）、`w20_refusal_domain_d1_v1`（谓词 `not (NumHDonors >= 1 and TPSA >= 20.0)`）；两者 `exit_code = refused_experimental_queue`，被拒行 `score_produced = false`，出口是实验测量队列、不进短名单。|
**② 冻结注册表拒答规模**：注册表 **31,949** 行；带 dielectric **247** 行；被拒 **187** 行；ε-refusal rate **0.7571**（精确 `0.757085020242915` = 187 / 247）；高 ε 规则 **9** 行、域规则 **183** 行、两规则同时命中 **5** 行；可排序 **60** 行；D1 域内 802 / 域外 31,145。|
**③ 分域第二记分牌（并列，不替换全域）**：全域 `0.45401075998423623`、D1 域内 `0.524012313223719`、D1 域外 `0.3198024498133034`。|
**④ 隔离声明（永不可混）**：本拒答读数**不得**与 ε 主记分牌比较，**不得**与 η 读数（运动黏度解冻臂）比较；`0.7571` 是**注册表 ε 行口径**，与分域记分牌 `40/97` 化合物口径**不是同一分母**，不得混说。|
**⑤ 性质**：本件不产读数、不占 shot 编号、不引 Reaxys 数值；拒答阈值单一所有者 `probes/w19_ranking_key.py::HIGH_PERMITTIVITY_EPS = 60.0`；verdict = `refusal_region_quantified`。|
|
