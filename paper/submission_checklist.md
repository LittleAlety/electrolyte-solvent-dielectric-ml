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
