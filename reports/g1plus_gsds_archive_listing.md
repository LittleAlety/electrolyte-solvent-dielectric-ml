# GSDS Zenodo 归档条目级核对：DC-200 逐分子表是否在 4.75 GB 包内

**日期**：2026-09-25
**对象**：`10.5281/zenodo.21061162` 的唯一附件 `GSDS_Prior_Finetune.zip`
（4,746,199,417 字节，md5 `f1736827b1a9f31e85587ca2eae913a7`）
**触发**：`reports/decisions_log.md` 一直把该归档标记为「未下载、未解包」，
这是 D6（DC-200 成员表）仅剩的免费路径。
**成本**：10 次未认证 HTTP GET（无 API key、不计费），**未下载 4.75 GB 正文**。

## 方法

ZIP 的中央目录位于文件尾部，而 Zenodo 支持 Range 请求，因此不需要下载正文：

1. 取最后 64 KiB，定位 zip64 中央目录结束记录；
2. 按 `Range` 精确取中央目录，读出全部条目名；
3. 需要看内容时，再取该条目的本地头 + 压缩流，就地 `zlib` 半解压——截断的 deflate 流
   依然能解出开头若干行，足以读 CSV 表头。

`zenodo.org` 在本环境不解析、`www.zenodo.org` 可解析，因此连接钉到已解析 IP，
TLS 仍以 `zenodo.org` 做 SNI 与证书校验。复现：

```
python probes/inspect_gsds_zenodo_archive.py                                  # 列全部条目 + 候选摘要
python probes/inspect_gsds_zenodo_archive.py --head <entry> --head-bytes 131072
```

## 结果

**条目数 15,524，与中央目录声明的条目数完全一致**，说明列目录没有漏读。
全部条目位于 `GSDS_Prior_Finetune/` 下，分 6 次微调运行
（`1_GSDS-PriorI-Seed1` … `6_GSDS-PriorII-Seed3`）。

后缀分布：`.csv` 3,348、无后缀目录 3,272、`.out` 2,385、`.txt` 1,890、`.png` 1,242、
`.smi` 1,242、`.valid` 1,242、`.log` 558、`.pth` 177、`.sh` 147、`.py` 1。

路径关键词计数：`Visc` 9,952、`MeltP` 9,526、`Redox` 9,466、`DonorNum` 6,950；
`dielectric` 0、`permittiv` 0、`epsilon` 0、`DC` 0、`MNSOL` 0、`Solvent` 0。

### 介电常数确实在包内——但形式不是数据集

1,892 个条目路径含 `DielecConst`，来自打分任务目录
`13_AgentS7-FilterSimi2NonF-Simi2NonF-Visc-MeltP-RedoxLog100-DielecConstLog1-{1,2,3}`。
逐条取头部核对后：

- `job_0/input.csv`（1,379 字节）是 **GraphINVENT 运行配置，不是数据表**：
  `score_components;['FilterSimi2NonF', 'Simi2NonF', 'Visc', 'MeltP', 'RedoxLog', 'DielecConstLog']`、
  `sol_dc_beta;1`、`sol_dc_max;10.0`，且
  `sol_ref_smiles_path;/mimer/NOBACKUP/groups/snic2022-5-322/zzy_data/5GSDS/9_GraphINVENT2/2_SolvRef/`
  ——介电常数以**打分组件**接入，其参考集指向一个**未随归档发布**的本地 HPC 路径。
- `.../generation_0_20k/ValidUniqueUnseenStrucViscProp.csv`（508,575 字节）表头为
  `index;SMILES;DN;DC;RedPot;OxPot`，行内容是**生成分子的预测值**（例如 `DC=17.719372`），
  既不是实验测量，也不是 DC-200 的 200 个成员。

## 结论

1. **DC-200 逐分子实验表不在该归档内。** 15,524 条条目名中没有任何介电常数数据集文件；
   介电常数只以「打分组件 + 未发布的 `2_SolvRef` 参考集」形式存在。
2. 旧措辞「4.75 GB 归档未下载、未解包，因此不能据此外推包内没有该表」升级为
   **「归档全部 15,524 条条目名已核对，包内无逐分子 DC-200 表」**。
3. **限制保留（不得省略）**：本次读出的是条目名与少数条目的头部，没有逐个解压 3,348 个 CSV。
   若某个通用命名的 CSV 恰好内嵌 200 分子介电表，按名核对的方法看不见它。
   缓解证据是所有含介电含义的路径都已定位并逐条查看，且各任务的属性维度由目录名显式声明。
4. 因此 D6 的剩余路径只剩**向通讯作者索取成员表**（需用户授权）与 tier-4 商业库，
   两者都不阻塞 v1.0。

## 请求记账

| # | 请求 | 结果 |
| --- | --- | --- |
| 1 | `GET /api/records/21061162`（钉 IP） | 200，元数据 |
| 2 | `GET .../content`，`Range: bytes=-65536` | 206，尾部 64 KiB |
| 3-4 | 探针首轮（尾部 + 中央目录） | 206 ×2，随后因结构体字段解析 bug 失败 |
| 5-6 | 探针升级后首跑（尾部 + 中央目录） | 206 ×2，同一 bug，仍无结论 |
| 7-8 | 探针修正后（尾部 + 中央目录） | 206 ×2，列出 15,524 条 |
| 9 | `--head .../DielecConstLog1-1/job_0/input.csv` | 206，解出 1,379 字节配置 |
| 10 | `--head .../generation_0_20k/ValidUniqueUnseenStrucViscProp.csv` | 206，解出 508,575 字节表 |

服务端 `x-ratelimit-limit: 133`，全程 10 次请求，未触发限速；无 API key、无计费。

## 产物

- `probes/inspect_gsds_zenodo_archive.py` —— 探针（仅标准库，钉 IP + SNI 校验）
- `probes/artifacts/gsds_zenodo_archive_entries.txt` —— 15,524 条条目名
- `probes/artifacts/gsds_zenodo_archive_listing.json` —— 条目元数据与候选摘要
- `tests/test_inspect_gsds_zenodo_archive.py` —— 6 条离线回归（中央目录往返、zip64、半解压）
