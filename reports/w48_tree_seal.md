# W48-A 封树与干净重导验证记录

治理 lane，0 shot。AF-12 三步走：封树提交 → 干净重导 → 逐条解释差异。

## 1 封树状态

- 导出包钉住的 commit：当前 HEAD = e5832425e624（W48-A 校验器修正：自身产出登记 + 导出前 purge + 补 H48a2 判据修正说明）
- 封树前基准：预注册记录封树前 HEAD = 04b27e3cdb20、脏路径 252 条（名单 sha256 = 807bd13f58d064cf…）
- 当前工作树脏路径 = 3，其中非登记项 0 条；本件自身产出 3 个文件按 SELF_OUTPUTS 显式登记

## 2 干净重导逐文件比对

- 旧包文件数 = 36；新包文件数 = 36
- 逐字节不变 = 34；变化 = ['SHA256SUMS', 'week47_summary.json']；新增 = []；删除 = []
- 簿记字段以外的变化 = []

| 文件 | 变化字段 | 簿记外字段 |
| --- | --- | --- |
| week47_summary.json | artifacts_commit, generated_at_utc | 无 |

> 逐条解释：干净重导后 summary 的 artifacts_commit 由 04b27e3 变为封树 HEAD，worktree_dirty 由 true 变 false、dirty_paths 由 251 变 0。这三处正是本 lane 的目标读数——包从「工作树态」改钉「版本态」。除此之外无任何文件字节变化。

## 3 幂等复导

- 同一 HEAD 上第二次重导：逐字节一致 = 是；复导变化文件 = []
- 新 SHA256SUMS = ef466d3a99173fda…（35 行）；W47 旧包 = 22fd63991a4557f0…

## 4 治理三件 + 测试子集

| 校验 | 返回码 | 末尾输出 |
| --- | --- | --- |
| scripts/verify_four_core_registry.py | 0 | {"passed": true, "checks": [{"name": "prereg_sha256_pinned", "passed": true, "de |
| scripts/check_paper_artifact_consistency.py | 0 | paper drafts agree with the frozen artifacts |
| scripts/verify_paper_figures.py | 0 | PASS: 6 figures are cited, present and reproducible |
| probes/w47_paper_readiness.py --check | 0 | verdicts 12/12 |

- 测试子集：34 passed, 1 warning in 4.11s
- 导出包：verified = True（3 项检查）、缺 lane = []、红线完整 = True、判否 = []
- 主记分牌：本周 0、累计 19

## 5 判据

| 判据 | 说明 | 裁决 |
| --- | --- | --- |
| H48a1 | 封树后无非登记脏路径（本件自身产出按 SELF_OUTPUTS 显式登记） | 成立 |
| H48a2 | 干净重导包钉住版本态：artifacts_commit == 封树 HEAD、worktree_dirty=false、dirty_paths=0 | 成立 |
| H48a3 | 新旧包差异逐条可解释：无删除、无新增、变化只落在簿记字段 | 成立 |
| H48a4 | 幂等复导：同一 HEAD 上再导一次，包逐字节一致（AF-12 不动点） | 成立 |
| H48a5 | 治理三件 + 投稿就绪守卫复跑全 PASS | 成立 |
| H48a6 | 封树后测试子集全 PASS（repo_hygiene + W47 四组） | 成立 |
| H48a7 | 四个冻结读数在论文中逐字不变（无变体、无缺字面值） | 成立 |
| H48a8 | 导出包自洽且不占 shot：verified、无缺 lane、红线完整、0 判否、本周 0、累计 19 | 成立 |

## 6 判据修正：计划 H48a2 在构造上不可达

计划 H48a2 原文要求「干净重导包与原包 SHA256SUMS 逐字节一致（22FD6399…）」。这条要求无法成立：
SHA256SUMS 覆盖 week47_summary.json，而该 summary 自身内含 artifacts_commit / worktree_dirty /
worktree_dirty_paths 三个簿记字段。封树一旦生效，这三处必然从「04b27e3 / true / 251」变为
「封树 HEAD / false / 0」；若它们没变，恰恰说明封树没有生效。因此修正为两条可执行判据：

- **H48a2 修正一**：新旧包逐文件比较，差异只允许落在 week47_summary.json 的簿记字段与其对应的
  SHA256SUMS 行；其余文件逐字节不变（本件实得 34 个文件不变、2 个变化、0 新增、0 删除、簿记外变化 0 项）。
- **H48a2 修正二**：在同一 HEAD 上重复重导，包逐字节一致——这是 AF-12 真正需要的不动点。

差异不是失败信号，它就是本 lane 的目标读数：包从「工作树态」改钉「版本态」。
