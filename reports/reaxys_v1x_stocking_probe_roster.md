# W17-16 Reaxys 库存队列实查名册（P1 + P2 层）

**一句话**：Week 17 计划把 Reaxys 库存队列（P1 = 2 / P2 = 22 / P3 = 143）点名为扩物质渠道；
本名册把 P1 + P2 的 **24 行**逐条拆成「W17-13/W17-15 已实查」与「仍待实查」，
拆分**由前序探针产物重算**，不采信队列自带的 `probed_in_this_round` 旧标记。

**这是计划，不是测量**：本件 `queries_executed = 0`，不含任何 Reaxys 渲染值。

## 计数

| 口径 | 行数 |
| --- | ---: |
| 名册总行数（P1 + P2） | 24 |
| `probe_target`（仍待实查） | 18 |
| `already_probed`（已由前序车道实查） | 6 |
| 其中芳香非电解液疑似（人工复核优先） | 6 |

## 仍待实查的物质（按 probe_order）

| order | rank | tier | family | name | inchikey | target_eps | 芳香疑似 |
| ---: | ---: | --- | --- | --- | --- | ---: | --- |
| 1 | 8 | P2 | fluorinated | 2-Fluoro-2-methylbutane | `HLLCNVLEVVFTJB-UHFFFAOYSA-N` | 5.89 |  |
| 2 | 10 | P2 | fluorinated | 1-Fluoropentane | `OEPRBXUJOQLYID-UHFFFAOYSA-N` | 4.24 |  |
| 3 | 14 | P2 | glyme_ether | 1,1,2,2-tetrafluoroethyl 2,2,3,3-tetrafluoropropyl ether | `HCBRSIIGBBDDCD-UHFFFAOYSA-N` | 2.8 |  |
| 4 | 15 | P2 | glyme_ether | 2-methyltetrahydrofuran | `JWUJQDFVADABEY-UHFFFAOYSA-N` | 6.2 |  |
| 5 | 16 | P2 | glyme_ether | bis(2,2,2-trifluoroethyl) ether | `KGPPDNUWZNWPSI-UHFFFAOYSA-N` | 2.5 |  |
| 6 | 17 | P2 | glyme_ether | Propyl ether | `POLCUAVZOMRGSN-UHFFFAOYSA-N` | 3.39 |  |
| 7 | 18 | P2 | glyme_ether | Ethyl ether | `RTZKZFJDLAIYFH-UHFFFAOYSA-N` | 4.335 |  |
| 8 | 19 | P2 | glyme_ether | 1,1-Dimethoxyethane | `SPEUIVXLLWOEMJ-UHFFFAOYSA-N` | 3.49 |  |
| 9 | 20 | P2 | glyme_ether | 1,3-dioxolane | `WNXJIVFYUVYPPR-UHFFFAOYSA-N` | 7.3 |  |
| 10 | 21 | P2 | glyme_ether | tetrahydrofuran | `WYURNTSHIVDZCO-UHFFFAOYSA-N` | 7.5 |  |
| 11 | 22 | P2 | glyme_ether | Isopropyl ether | `ZAFNJMIOTHYJRJ-UHFFFAOYSA-N` | 3.88 |  |
| 12 | 23 | P2 | glyme_ether | 2,2'-dichlorodiethyl ether | `ZNSMNVMLTJELDZ-UHFFFAOYSA-N` | 20.79 |  |
| 13 | 4 | P2 | fluorinated | m-Fluorotoluene | `BTQZKHUEUDPRST-UHFFFAOYSA-N` | 5.42 | 是 |
| 14 | 6 | P2 | fluorinated | alpha,alpha,alpha-Trifluorotoluene | `GETTZEONDQJALK-UHFFFAOYSA-N` | 9.18 | 是 |
| 15 | 7 | P2 | fluorinated | 1,2-difluorobenzene | `GOYDNIKZWGIXJT-UHFFFAOYSA-N` | 7.1 | 是 |
| 16 | 9 | P2 | fluorinated | o-Fluorotoluene | `MMZYCBHLNZVROM-UHFFFAOYSA-N` | 4.22 | 是 |
| 17 | 11 | P2 | fluorinated | Fluorobenzene | `PYLWMHQQBFSUBP-UHFFFAOYSA-N` | 5.42 | 是 |
| 18 | 12 | P2 | fluorinated | p-Fluorotoluene | `WRWPPGUCZBJXKX-UHFFFAOYSA-N` | 5.86 | 是 |

## 已由前序车道实查（不再重复查）

| rank | tier | name | inchikey | 证据 |
| ---: | --- | --- | --- | --- |
| 1 | P1 | ethylene carbonate | `KMTRUDSVKNLOMY-UHFFFAOYSA-N` | probes/reaxys_thin_family_query_b2_facts.csv;probes/reaxys_core_four_crosscheck.csv;queue_flag:probed_in_this_round |
| 2 | P1 | propylene carbonate | `RUOJZAUFBMNUDX-UHFFFAOYSA-N` | probes/reaxys_thin_family_query_facts.csv;probes/reaxys_core_four_crosscheck.csv;queue_flag:probed_in_this_round |
| 3 | P2 | ethyl methyl carbonate | `JBTWLSYIZRCDFO-UHFFFAOYSA-N` | probes/reaxys_thin_family_query_b2_facts.csv |
| 5 | P2 | Trifluoroacetic acid | `DTQVDTLACAAQTR-UHFFFAOYSA-N` | probes/reaxys_thin_family_query_facts.csv |
| 13 | P2 | 1,1,2,2-tetrafluoroethyl 2,2,2-trifluoroethyl ether | `CWIFAKBLLXGZIC-UHFFFAOYSA-N` | queue_flag:probed_in_this_round |
| 24 | P2 | gamma-valerolactone | `GAEKPEKOJKCEMS-UHFFFAOYSA-N` | probes/reaxys_thin_family_query_b2_facts.csv;probes/reaxys_core_four_crosscheck.csv |

## 边界

- 名的拆分**不采信队列旧 flag**：`probed_in_this_round` 只标了 3 行，实际前序车道已走过 14 个键；两者取并集。
- `family_tag = fluorinated` 的子串规则会把**非电解液芳烃**（氟代甲苯 / 氟苯 / 二氟苯 / 三氟甲苯）拖进 P2；名册把它们标 `aromatic_non_electrolyte_suspect = yes` 并沉到同层队尾，**不静默删除**。
- 键**逐字取自**队列 `inchikey` 列（`keys_not_from_the_queue = 0`）；禁止手抄键。
- 合规（裁决 B）：Reaxys 派生数值不得进 `data/`、不得进任何池、不得进任何特征表；原始页证据只落被忽略的 `data/raw/reaxys_w17d/`。
- 本件 `models_fitted = 0`、不报 R²、不碰主记分牌 0.4091179943351143。

