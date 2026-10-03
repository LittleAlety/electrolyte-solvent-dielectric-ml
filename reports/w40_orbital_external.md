# W40-D 轨道通道外部对照层（QM9）与 PubChemQC 单文件子集可行性

- 任务：W40-D（后验读数，0 shot）
- 名册：data/processed/dielectric_physical_features_v03.csv（241 行）
- 外部层：data/external/qm9_dataset.csv（sha256 01d196218c78a0e29575ef8cf9ceb6d2f33fda9cddc3e4b5bd133e191fa2e053）
- 记账：**不占 shot**（累计仍 19）；不改 METRIC_NAMES、不新增特征列、不动四个冻结读数

## 0. 口径声明（口径先于读数）

1. QM9 的 homo / lumo / gap 单位是 **Hartree**（1 Ha = 27.211386245988 eV）；它们是 **B3LYP/6-31G(2df,p) 气相**轨道能。
2. 我们的 homo_lumo_gap_ev 是 **xTB GFN2 单点**。两者**层级不同** ⇒
   本件**只谈排序（Spearman / Kendall）与标定（线性映射）**，
   **不把 QM9 数值写进任何标签池 / 特征列 / 交付标签**，**不得直接互换**。
3. QM9 许可 = CC BY 4.0（原始 deposition 10.6084/m9.figshare.978904）。
4. W39 已判决的结论（含「刚性 vs 柔性构象」那条判否）本件**只引用、不重复声明为新发现**。

## 0.1 一句话结论

QM9 作为轨道通道**外部对照层**是宽的（**103 / 241**）、排序是可信的（Spearman 0.8856、Kendall 0.7114），但**量级不可互换**（未标定 |delta| 中位数 2.577 eV，102/103 条 >= 1 eV）；线性标定只消掉约 36.8% 的误差（留一）⇒ 仍然只能当**排序先验**，不能当标签。PubChemQC 的扩大覆盖路线**照实登记为受阻**（详见 §5）。

## 1. 对照层读数

| 量 | 值 |
| --- | --- |
| 名册命中 | 103 / 241 |
| Spearman | 0.885628 |
| Kendall tau | 0.711442 |
| Pearson | 0.840944 |
| 中位数比 xTB / QM9 | 0.705757 |
| 未标定 MAE | 2.532944 eV |
| 未标定 中位数 \|delta\| | 2.577390 eV |
| \|delta\| >= 1 eV | 102 / 103（99.0%） |
| QM9 内部自洽 max \|gap - (lumo - homo)\| | 2.721e-03 eV |

## 2. 层级不可互换的定量证据

- 两个层级的中位数比（xTB / QM9）= 0.7058 ⇒ 系统性压缩，方向与 W39 一致。
- 未标定偏差：MAE 2.533 eV，中位数 |delta| 2.577 eV。
- 在 103 条命中里有 102 条 |delta| >= 1 eV ⇒ **任何把 QM9 值当标签或特征的做法都会引入 >= 1 eV 的层级误差**。
- 完整离群清单见 w40_orbital_external_control.csv 的 abs_delta_gap_ev 列；下表列前 15 条。

| 化合物 | xTB (eV) | QM9 (eV) | delta (eV) |
| --- | --- | --- | --- |
| water | 14.160 | 9.837 | -4.323 |
| Acetonitrile | 5.911 | 9.905 | 3.994 |
| Propionitrile | 5.756 | 9.668 | 3.912 |
| pentanenitrile | 5.724 | 9.633 | 3.909 |
| butanenitrile | 5.759 | 9.660 | 3.901 |
| hexanenitrile | 5.710 | 9.587 | 3.877 |
| hexanedinitrile | 5.644 | 9.459 | 3.815 |
| octanenitrile | 5.671 | 9.464 | 3.793 |
| heptanedinitrile | 5.634 | 9.399 | 3.765 |
| pentanedinitrile | 5.624 | 9.091 | 3.467 |
| ethylene carbonate | 5.666 | 9.078 | 3.412 |
| methanol | 12.759 | 9.353 | -3.407 |
| N-methylacetamide | 4.341 | 7.633 | 3.292 |
| cyclohexane | 13.579 | 10.294 | -3.284 |
| beta-Ethoxyethyl acetate ("Cellosolve" acetate) | 4.373 | 7.562 | 3.189 |

## 3. 标定（只在排序意义上可用）

| 量 | 值 |
| --- | --- |
| 标定式 | xTB = 2.026697 * QM9 -8.872895 |
| 与 W39 冻结值一致 | 是 |
| 样本内标定 MAE | 1.575506 eV |
| 样本内下降比例 | 0.377994 |
| 留一标定 MAE | 1.601998 eV |
| 留一下降比例 | 0.367535 |

读数：标定把 MAE 从 2.533 eV 降到 1.602 eV（留一），下降 36.8%。这**低于 50%** ⇒ 线性标定只修复了层级差的一小部分（其余来自泛函/基组/相态差异），所以对照层只能用于**相对排序**，不能用于**绝对量级**。

## 4. 判据

| id | 判据 | 读数 | 门槛 | 判定 |
| --- | --- | --- | --- | --- |
| H40d1 | 名册命中 >= 100（轨道通道外部对照层的宽度，对齐 W39 的 103） | 103.0 | 100.0 | 成立 |
| H40d2 | xTB 间隙与 QM9 间隙的 Spearman >= 0.70（排序可互相代理） | 0.8856281475401158 | 0.7 | 成立 |
| H40d3 | 同一对齐的 Kendall tau >= 0.50（对并列与秩更稳健的第二口径） | 0.7114415223878093 | 0.5 | 成立 |
| H40d4 | 未标定 |delta| 中位数 >= 1.0 eV（两个层级不能直接互换的定量证据） | 2.577389731918365 | 1.0 | 成立 |
| H40d5 | 留一标定后 MAE 下降比例 >= 1/3（标定必须是一阶有效修正，而非装饰） | 0.36753521545876466 | 0.3333333333333333 | 成立 |
| H40d6 | |delta| >= 1 eV 的离群条数 >= 1 且已登记清单（对照层不得被当成标签） | 102.0 | 1.0 | 成立 |
| H40d7 | PubChemQC 单文件子集可行性评估完成且结论已登记（census + 受阻原因 + 替代） | 1.0 | 1.0 | 成立 |
| H40d8 | PubChemQC 存在「按名册命中定位的单文件子集」本机可行下载路径（判否：登记为受阻） | 0.0 | 1.0 | 判否 |
| H40d9 | 本件重算的层级标定与 W39 冻结值逐位一致（口径可复现） | 1.0 | 1.0 | 成立 |
| H40d10 | 输入未被改写：名册与 QM9 的 sha256 前后一致，且两者与登记指纹相符 | 1.0 | 1.0 | 成立 |

阈值首次冻结的依据：H40d2 沿用 W39 已经用过的 0.70，保持口径连续；H40d3 的 0.50 是 0.70 在双变量正态下的对应 tau；H40d4 的 1 eV 是「不能当标签」的物理下限；H40d5 的 1/3 是「标定若有效至少应消去三分之一层级差」的下限；H40d1 的 100 对齐 W39 的 103，只把「够宽」量化。

## 5. PubChemQC 单文件子集可行性评估（只读侦察，未下载）

侦察端点（2026-10-03，hf-mirror.com dataset tree API，只读）：

- https://hf-mirror.com/api/datasets/molssiai-hub/pubchemqc-b3lyp/tree/main/data
- https://hf-mirror.com/api/datasets/molssiai-hub/pubchemqc-pm6/tree/main/data
- https://hf-mirror.com/api/datasets/molssiai-hub/pubchemqc-b3lyp/tree/refs%2Fconvert%2Fparquet
  （返回 Invalid rev id ⇒ **无 parquet 分支**）

各 config 的 train 分片统计（bytes 为 LFS 实文件大小）：

| dataset | config | 分片数 | 最小分片 (B) | 最大分片 (B) | 合计 (B) | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| molssiai-hub/pubchemqc-b3lyp | b3lyp_pm6 | 430 | 3451907673 | 9905178633 | 2244891376968 |  |
| molssiai-hub/pubchemqc-b3lyp | b3lyp_pm6_chnopsfcl300nosalt | 149 | 3329101674 | 4279899464 | 585419076926 |  |
| molssiai-hub/pubchemqc-b3lyp | b3lyp_pm6_chnopsfcl500nosalt | 339 | 3166530000 | 6182779852 | 1658006696822 |  |
| molssiai-hub/pubchemqc-b3lyp | b3lyp_pm6_chnopsfclnakmgca500 | 347 | 2113728631 | 6197949096 | 1696785969280 |  |
| molssiai-hub/pubchemqc-b3lyp | b3lyp_pm6_chon300nosalt | 87 | 2184575419 | 4371881945 | 349293321756 |  |
| molssiai-hub/pubchemqc-b3lyp | b3lyp_pm6_chon500nosalt | 232 | 536126834 | 6280942234 | 1135035374141 |  |
| molssiai-hub/pubchemqc-pm6 | pm6opt | 1000 | 2482690433 | 7031196000 | 3873347155187 | tree API 1000 项截断，合计为下界 |
| molssiai-hub/pubchemqc-pm6 | pm6opt_chon300nosalt | 87 | 1498874351 | 3011860000 | 238937813600 |  |
| molssiai-hub/pubchemqc-pm6 | pm6opt_chon500nosalt | 156 | 2423347276 | 4158000000 | 510618083373 |  |

**结论：名册级（241 化合物）单文件子集下载 — 受阻（判否，已登记）。**

- 全局最小单文件 = 536126834 B（511.3 MiB），路径 data/b3lyp_pm6_chon500nosalt/train/121433757-121494125.json，CID 区间 [121433757, 121494125]。
- 该值**低于 1 GiB** ⇒ 「单片体量」本身**不是**绝对阻塞；**必须照实写这一点**，不能笼统记成「最小切片 325 GB 不可行」。
- 真正阻塞的是可定位性：
  - 无 CID / InChIKey 索引：分片文件名只是闭区间 CID 范围，没有「按 InChIKey 定位分片」的索引文件。
  - 无 parquet 分支：refs/convert/parquet 返回 Invalid rev id（该数据集 viewer: false，未自动转换）。
  - 本机 PubChem PUG REST 不可达（pubchem.ncbi.nlm.nih.gov 挂起超时）⇒ 无法把名册 241 条 InChIKey 解析成 CID。
  - 名册化合物（常见溶剂）CID 分散在 1-1.2 亿区间 ⇒ 即使拿到全部 CID，覆盖也必须跨多个 0.5-6 GB 分片。
- 最小可行替代：在能访问 PubChem 的机器上先做 InChIKey -> CID 解析（只读、便宜），再按 CID 落在哪个分片决定下载；对 1-3 个化合物的实证校验成本约 0.5-6 GB/片。本机（PubChem 不可达）不可行。

## 6. 边界

- QM9 = **CC BY 4.0 外部对照层**：可参考、可审计，但**不入任何池 / 特征 / 交付标签**。
- 「刚性 vs 柔性」结论属 **W39**（H39a7 判否，刚性与柔性 |dmu| 中位数几乎一样）；本件**只引用**，不重复声明为新发现。
- 标定是**样本内 + 留一**两种读数；本件不做任何超参搜索，也不占用主记分牌 shot。
- PubChemQC 部分**只做只读侦察**：本机未下载任何分片，结论的量化依据是 tree API 的 LFS 大小。
- 本机 PubChem PUG REST 不可达这一条是**环境事实**，换机器后需要重新评估（见最小可行替代）。

## 7. 输入指纹

- E:\Claude Code\电解质ML\电解质ML\data\processed\dielectric_physical_features_v03.csv = b36d3439560e4381b7779565b9950eed379832e832b72ea6a3a010662ed24fa3
- roster_sha256_after = b36d3439560e4381b7779565b9950eed379832e832b72ea6a3a010662ed24fa3
- roster_expected_sha256 = b36d3439560e4381b7779565b9950eed379832e832b72ea6a3a010662ed24fa3
- E:\Claude Code\电解质ML\电解质ML\data\external\qm9_dataset.csv = 01d196218c78a0e29575ef8cf9ceb6d2f33fda9cddc3e4b5bd133e191fa2e053
- qm9_sha256_after = 01d196218c78a0e29575ef8cf9ceb6d2f33fda9cddc3e4b5bd133e191fa2e053
- qm9_expected_sha256 = 01d196218c78a0e29575ef8cf9ceb6d2f33fda9cddc3e4b5bd133e191fa2e053
