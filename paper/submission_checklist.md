# 投稿与发布机械清单（v1.0）

> 打 tag 与投稿都是**不可逆的外部动作**。本清单只列机械前置，逐条勾掉再执行。
> 生成日期：2026-09-25；最近一次修订补齐发布闸门与完整占位符清单（当前 HEAD 见 `git log -1`）。

## A. v1.0 tag 前置条件

objective 把 tag 条件定义为「D1/D2 digest 重钉完成」，当前状态：

- [x] **D2** 四行（3 个离子液体 + Fe(CO)5）重分类为 `out_of_scope_ionic_or_organometallic`，
      不动任何拟合行；digest 一次性重钉为 `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`。
- [x] **D1** EC 313.15 K 例外口径（schema `temperature_band=extended_temperature` + Methods 规则）
      与预注册 leave-EC-out 敏感性分析（7,080 个冻结预测逐位复现；该探针不改任何 digest）。
- [x] 四类 verifier 全绿：一致性、图、v0.3 数据集、导出清单 **10/10**。
- [x] 全量测试 **851 passed**，`ruff` 与 `compileall` exit 0。
- [ ] `python scripts/check_release_readiness.py` exit 0 —— 占位符清零、release 行写成 v1.0、DOI 与仓库 URL 已替换（B 节）。
- [ ] **Zenodo 集成 + 真实 DOI 回填** —— 见下节 B/C。这是当前唯一未闭环的前置。

## B. 必须替换的占位符（不替换会被带进发布物）

| 位置 | 当前值 | 替换为 |
| --- | --- | --- |
| `paper/code_and_data.md:6` | `https://github.com/[repository-name]` | 真实 GitHub 仓库 URL |
| `paper/code_and_data.md:7` | `v0.3.3 (candidate; ...)` | `v1.0 (tagged <日期>)` |
| `paper/methods_data_records.md:197` | `https://github.com/[repository]` | 真实 GitHub 仓库 URL |
| `paper/code_and_data.md:8` | `https://doi.org/10.5281/zenodo.[XXXXX]` | 真实 Zenodo DOI |
| `paper/full_draft.md`（生成物） | 同上 | 改完源文件后重建，不要手改 |
| `paper/cover_letter.md` | `[TODO: repository]` / `[TODO: v1.0]` / `[TODO: DOI]` / 作者三项 | 真实值 |

替换后**必须**重跑（顺序不可省）：

```
python scripts/build_paper_full_draft.py
python scripts/build_paper_full_draft.py --check
python scripts/check_paper_artifact_consistency.py
python scripts/check_release_readiness.py
```

最后一条是**发布闸门**，只在打 tag 时运行：任一占位符（`[TODO: ...]` / `[repository]` / `zenodo.[XXXXX]`）残留、
release 行仍写着 candidate、DOI 不是真实 Zenodo DOI、或仓库 URL 不是真实 GitHub 地址，它都会 exit 1 并逐条打印位置。
它**故意不并入** `check_paper_artifact_consistency.py`：发布前占位符是正确状态，日常一致性闸门必须保持全绿，而这条闸门在全绿之前必须保持红。

## C. tag 与存档顺序（**Zenodo 集成必须先于打 tag**）

1. 在 GitHub 仓库启用 Zenodo 集成（**你在网页操作**）。
2. 打 tag 并推送：`git tag -a v1.0 -m "..."` → `git push origin v1.0`。
3. Zenodo 捕获该 release 并生成 DOI（版本化 DOI 与 concept DOI 各一）。
4. 把 DOI 回填到 `paper/code_and_data.md`，重建 `full_draft.md`，再走一次 B 的检查。
5. 更新 `paper/outline.md` 的 release line 表述——现在写的是 candidate，打 tag 后不再称 candidate。

> 注意顺序：先打 tag 会得到一个**没有 DOI 指向**的 release，第 4 步还要再动一次正文，所以集成在前。

## D. 投稿包清单（`Scientific Data`）

- [x] cover letter 草稿 —— `paper/cover_letter.md`（本清单同日生成）
- [ ] 正文 —— `paper/full_draft.md`（1044 行，5 节拼装）
- [ ] 6 张图 —— `probes/artifacts/*.png`，或成果输出 `week10/artifacts/`
- [ ] 数据与代码可用性声明 —— Zenodo DOI + GitHub tag（依赖 A/B）
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
