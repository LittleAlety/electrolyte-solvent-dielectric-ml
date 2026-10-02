# 投稿与发布机械清单（v1.0）

> 打 release 与投稿都是**不可逆的外部动作**。本清单只列机械前置，逐条勾掉再执行。
> 生成日期：2026-09-25；最近修订：回填 Zenodo DOI（`10.5281/zenodo.22957696`），并记下「集成未生效时必须先启用再重建 release」这条实测教训（当前 HEAD 见 `git log -1`）。

## A. v1.0 release 前置条件

objective 把发布条件定义为「D1/D2 digest 重钉完成」，当前状态：

- [x] **D2** 四行（3 个离子液体 + Fe(CO)5）重分类为 `out_of_scope_ionic_or_organometallic`，
      不动任何拟合行；digest 一次性重钉为 `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`。
- [x] **D1** EC 313.15 K 例外口径（schema `temperature_band=extended_temperature` + Methods 规则）
      与预注册 leave-EC-out 敏感性分析（7,080 个冻结预测逐位复现；该探针不改任何 digest）。
- [x] 四类 verifier 全绿：一致性、图、v0.3 数据集、导出清单 **10/10**。
- [x] 全量测试 **868 passed**，`ruff` 与 `compileall` exit 0（2026-09-25）。
- [x] `python scripts/check_release_readiness.py --phase pre-release` exit 0 ——
      手稿无占位符、release 行写成 v1.0、DOI 为显式 `pending`（DOI 由 release 铸出，见 C 节）。
- [x] **创建 GitHub Release v1.0** → Zenodo 生成 DOI → 回填 → `--phase released` exit 0。
      实测：集成未生效时首次 release 不会建档；须在 Zenodo 里把本仓库开关打 **On** 后**重建** release（见 C.4）。

## B. 版本与占位符

| 位置 | 发布前状态 | 需要的最终值 |
| --- | --- | --- |
| `paper/code_and_data.md` 仓库行 | ✅ 已填真实 URL | 不变 |
| `paper/methods_data_records.md` 仓库行 | ✅ 已填真实 URL | 不变 |
| `paper/code_and_data.md` release 行 | ✅ `v1.0 (GitHub release 2026-09-25; dataset v0.3.3)` | 不变 |
| `paper/code_and_data.md` DOI 行 | ✅ `https://doi.org/10.5281/zenodo.22957696`（concept `10.5281/zenodo.22957695`） | 不变 |
| `paper/full_draft.md`（生成物） | ✅ 已随源文件重建 | 不变（DOI 回填后已再重建一次） |
| `paper/cover_letter.md` | `[TODO: ...]` | ⬜ 作者三项 + 仓库 + tag + DOI（**投稿前**，不随 release 归档） |

DOI 回填后**必须**重跑（顺序不可省）：

```
python scripts/build_paper_full_draft.py
python scripts/build_paper_full_draft.py --check
python scripts/check_paper_artifact_consistency.py
python scripts/check_release_readiness.py --phase released
```

`check_release_readiness.py` 有三个相位：`pre-release`（默认；DOI 只允许写成显式 `pending`）、
`released`（DOI 必须是真 Zenodo DOI）、`submission`（在 released 之上再要求 cover letter 无 `[TODO: ...]`）。
它**故意不并入** `check_paper_artifact_consistency.py`：发布前 `pending` 是正确状态，
日常一致性闸门必须保持全绿，而这条闸门在对应相位满足前必须保持红。

## C. 发布顺序（**Zenodo 只归档 GitHub Release；只推 tag 不会触发**）

1. 在 Zenodo 设置里对 `LittleAlety/electrolyte-solvent-dielectric-ml` 启用集成
   （**你在网页完成，2026-09-25**）。
2. 在 Zenodo 的 GitHub 列表里点该仓库的 **Create release**，它会引导到 GitHub 的新建 release 页面。
3. 在 GitHub 创建 **Release**（tag = `v1.0`，target = `main` 的发布提交）：

   ```
   gh release create v1.0 --title "v1.0: auditable dielectric dataset (246 rows)" \
     --notes-file paper/release_notes_v1.0.md --target main
   ```

   仅 `git tag -a v1.0 && git push origin v1.0` **不会**让 Zenodo 建档。
   > **实测教训（2026-09-25）**：若只「Connect」授权了 App、却没在 Zenodo 的 GitHub
   > 列表里把本仓库开关打成 **On**，release 创建成功但 Zenodo 永远收不到事件。
   > 判别方法：同一时段 Zenodo 正常为别的仓库铸 DOI
   > （`/api/records?q=resource_type.type:software&sort=mostrecent`），而按本仓库 URL 检索为 0
   > —— 此时把开关改成 On 并**重建 release**；已经发过的 release 不会被补录。

4. 等 Zenodo 处理该 release（时间取决于 Zenodo 负载），生成版本化 DOI 与 concept DOI。
5. 把 DOI 回填到 `paper/code_and_data.md`，重建 `full_draft.md`，跑 B 的检查（`--phase released`），提交。
6. 在 Zenodo 记录页面核对/补全标题、作者、描述与许可（记录元数据可改，DOI 不变）。
7. **DOI 铸出后，绝不要再编辑 GitHub release 的标题或正文。** 实测（2026-09-25）：
   修改 release body 会**再次触发归档**，生成一个内容相同的重复版本
   （`10.5281/zenodo.22957976`，与 `10.5281/zenodo.22957696` 同属 concept
   `10.5281/zenodo.22957695`）。要补元数据就改 Zenodo 记录本身，不要动 release。
   - [x] 在 Zenodo 记录页删除重复版本 `10.5281/zenodo.22957976`（2026-09-25 已删；
        该 DOI 现返回 HTTP `410 Gone`，`/api/records/22957696/versions` 只剩 **1** 个版本）。
   - [改判 2026-09-28] 上一条括号里的「只剩 **1** 个版本」**已不再成立**。2026-09-28 实测该 concept
        下共 **5** 条在册记录：v1.0 三条（`10.5281/zenodo.22957696`＝本仓引用，`10.5281/zenodo.22958270`、
        `10.5281/zenodo.22958541` 未被引用）、v1.1 一条（`10.5281/zenodo.23001408`）、v1.2 一条
        （`10.5281/zenodo.23001632`）。由 `created` 时间戳可知：2026-09-25 当天共铸出 **4** 条 v1.0
        记录（`22957696` 11:08:04Z、已删的 `22957976`、`22958270` 11:41:54Z、`22958541` 11:56:22Z），
        存活 3 条。三条 v1.0 是否收敛留给作者裁定；本仓**只登记不处置**。
   - [同族缺陷 2026-09-28] v1.1 也曾出现三条同版本号记录（`23001299` / `23001408` / `23001424`）；
        作者已按 `removal_reason = duplicate` 删除 `23001299` 与 `23001424`，保留 `23001408` 为唯一在册版本。
        本仓 `README.md` 与 `paper/release_notes_v1.1.md` 原引的 `23001299` 因此变成 HTTP `410` 断链，
        已一并更正为 `23001408`。详见 `reports/decisions_log.md` §28.56。
   - [v1.3 2026-09-28] **第五次发布（Week 20 交付）**。发布前置提交 `5aa3151`；tag `v1.3` =
        `5aa315169f22f3adb8d88365cd1bcfa763b4e0d6`；Release 由
        `gh release create v1.3 --target main --notes-file paper/release_notes_v1.3.md` 建立，
        `publishedAt = 2026-09-28T13:59:07Z`、`isDraft = false`；webhook `685484825` 于
        `13:59:08Z` 投递 `409 / 409 / 202`。**版本 DOI `10.5281/zenodo.23019467`**（记录 `23019467`，
        `created = 2026-09-28T15:44:02Z`；concept `10.5281/zenodo.22957695` 下现 **7** 条），已回填
        `README.md` 与 `paper/release_notes_v1.3.md`；**v1.3 Release 正文未编辑、也不得编辑**
        （同本条已测触发机制）。
        tag 树内被归档文件（`README.md`、`paper/release_notes_v1.3.md`）**无** `pending` 字样与
        本版本 DOI 自指行 —— §28.65 ⑤ 规则的首次落地。

> 顺序由 Zenodo 的机制决定：DOI 由 release 铸出，所以被归档的 v1.0 快照里 DOI 行写的是
> `pending`，仓库里的真实 DOI 从回填提交开始生效。

## D. 投稿包清单（`Scientific Data`）

- [x] cover letter 草稿 —— `paper/cover_letter.md`（本清单同日生成）
- [x] 正文 —— `paper/full_draft.md`（5 节拼装，`--check` 绿）
- [x] 6 张图 —— `probes/artifacts/*.png`，成果输出 `week10/artifacts/`
- [x] 发布说明 —— `paper/release_notes_v1.0.md`
- [ ] 数据与代码可用性声明 —— DOI `10.5281/zenodo.22957696` 与 tag `v1.0` 已就位；待 cover letter 作者三项
- [ ] 作者贡献与利益冲突声明
- [ ] 推荐审稿人（可选）
- [ ] 按期刊要求拆分 Abstract / Methods / Data Records 等节

## E. 不阻塞发布（已如实记录即闭环）

- **FEC**：78.4@296.15 K（Kobayashi 2003）与 107@25 °C（经 Ue et al. 2014 转录）双腿并存，
  不平均、不裁决，维持 `model_ready=false`。其命名的原始文献 Hagiyama 2008 无开放全文，只剩馆际互借。
- **VC**：Knovel 区间与一手值冲突，维持 `model_ready=false`。
- **MOPN**：36.0 仅来自 ECW-308 二级汇编，无独立一手测量，已在 Limitations 与 Known data gaps 点明。
- **DC-200**：成员表需向通讯作者索取（ACS Nano SI 与作者仓库均无；Zenodo 归档 15,524 条条目名已于 2026-09-25 全部核对，包内只有微调产物与配置，介电常数以打分组件接入、参考集未发布），列为发表后交叉验证资产。

## F. 发表后 backlog

- v1.x 多温度观测表
- DC-200 交叉验证（SI / 邮件）
- N3 / N4 待办
- 离子液体是否单开一层，留给 v2.0 路线图

---

## Week 22 评审整改补充检查项

> 追加于 2026-10-02（W22-4 lane）。本节**只追加**，不改动上文任何条目。
> 来源：外部评审 A/B/C/D 四组；逐条登记见 `paper/review_response_matrix.md`。

### 提交前必查（A 组硬伤，依赖原文 PDF 版面）
- [ ] **A1 英文摘要截断**：PDF 导出后**逐页**核对英文摘要的渲染边界；原截断处（`…|d0 − d1| ≤ A_axis, under which`）之后必须还有完整段落；若判据改为 `2A_axis`，摘要公式须同步改。
- [ ] **A4 页眉乱码**：逐页核对运行页眉来源（模板变量 vs 图内标题/文件名被误注入）；已发现的坏串（如 `F24 the dielectric ladder, measured to eps = 200`、含 `orbita al` 者、`45 R8: prcinq t`）必须全部消失。
- [ ] **A2 摘要方向自检**：按规则 R-A2（`paper/review_response_matrix.md` §1.4）核对——数值单调性自检 + 解耦论据必须引用误差与排序方向相反的那一对；`0.73 > 0.61` 之类「降为/反而」一律改写。
- [ ] **A5/A6 口径句**：正文写死「还原轴结论只以带连续介质的层为载体」与「单一连续介质计算不可省；可省的是 `ε ≥ 200` 细化与 `ε` 扫描」；摘要 / §3.7 / §3.10 三处一致。

### 统计与口径（B 组）
- [ ] **B2 配对 bootstrap 的 `Δτb` CI** 已报（同批分子内重抽样，而非两个点估计并排）。
- [ ] **B4 表注/图注写明 N 与池**：同台阶数字（`0.673` vs `0.60`、`0.595` vs `0.600`）已统一或已注明口径差；`ε` 点数三处一致；「360 格普查」与「90 抽样点」两级关系已交代。
- [ ] **B3 多重比较**：校正后未存者明确标 `suggestive_only`（提示性证据）。
- [ ] **B5 broad pool** 承诺已兑现或已删除。
- [ ] **A3 安全定理**：阈值 `2A_axis` 下的保护格计数与节省率已**重报**（不得沿用旧 28.3% / 3.3%）；正文把「定理（严格界）」与「实测（经验零漏）」分成两句。

### 图件（C 组）
- [ ] **C6 图 1 图注与图内文字一致**（本仓 `paper/paper_zh_draft.md` L194 已修；重出图后复查）。
- [ ] **C8 图表语言统一**：图内英文标题与中文图注风格统一（当前状态 `pending_needs_figure_regen`，修法须重出 PNG）。
- [ ] **C1/C2/C3/C4/C5/C7** 经本仓实测为 `n/a_in_repo`（依据见 `paper/review_response_matrix.md` §4）；若原文另有对应段落，按矩阵口径回填。

### 依赖原文（不得代填数字）
- [ ] `A1`、`A2`、`A4`、`B2` 原文表、`B4` 原文表/图注、`D2–D5` 已按 `pending_needs_original` 登记；**原文到位前不得提交**，任何人不得用替代数字回填。