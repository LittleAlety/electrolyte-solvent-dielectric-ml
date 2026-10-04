# W48-C 投稿执行包（C1 交付 / C2-C3 待 venue 拍板）

类④（投稿操作）lane，0 shot。venue 选择权在用户；本件只交付备忘录并守住零科学漂移。

## 1 交付状态

- C1 venue 备忘录：reports/w48_venue_memo.md（sha256 37852776c3b00797）。
- 候选命中（5/5）：Journal of Molecular Liquids，PCCP，J. Chem. Inf. Model.，Electrochimica Acta，J. Electrochem. Soc.。
- 四轴命中：范围匹配，审计叙事接受度，周期，版面／OA。
- deferred：H48c2=投稿包（docx + 图件 + 可复现性声明 + cover letter）待 venue 拍板后生成；本周期 venue 未定，登记 deferred 而非失败。。

## 2 判据

| id | 判据 | 值 | 阈 | 判决 |
| --- | --- | --- | --- | --- |
| H48c1 | venue 备忘录交付且含 >= 3 候选的四轴对比 | {"memo_exists": true, "n_candidates": 5, "axes_present": ["范围匹配", "审计叙事接受度", "周期", "版面／OA"]} | {"memo_exists": true, "min_candidates": 3, "axes": ["范围匹配", "审计叙事接受度", "周期", "版面／OA"]} | 成立 |
| H48c3 | 形式改动零科学漂移：一致性校验 PASS 且四个冻结读数逐字在稿 | {"consistency_returncode": 0, "readings_all_literal": true, "readings_literal": {"0.4091179943351143": true, "0.4766400383507876": true, "0.5861142332208197": true, "0.6216672295270079": true}} | {"consistency_returncode": 0, "readings_all_literal": true} | 成立 |
| H48c4 | 0 shot；投稿包条目按 venue 未定登记 deferred（非失败） | {"shots_this_week": 0, "deferred_criteria": {"H48c2": "投稿包（docx + 图件 + 可复现性声明 + cover letter）待 venue 拍板后生成；本周期 venue 未定，登记 deferred 而非失败。"}} | {"shots": 0} | 成立 |

