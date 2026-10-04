# W42-A 四层轨道迁移网络与非传递闭合

计算 lane（0 shot，累计仍 19）。把 PubChemQC B3LYP 层接进 W41-D 三层网络，在 241 行名册上做一次完整的四层迁移计算。

## 1. 四层覆盖与全部交集

| 层 | 理论层级 | 相 | 覆盖 /241 |
| --- | --- | --- | ---: |
| xtb | GFN2-xTB | gas phase | 237 |
| qm9 | B3LYP/6-31G(2df,p) | gas phase | 103 |
| pubchemqc | B3LYP/6-31G*//PM6 | gas phase | 205 |
| batt | ωB97X-V/def2-TZVPPD/SMD(epsilon=18.5) | implicit solvent SMD(eps=18.5) | 73 |

四路交集 = **48**（xTB 237、QM9 103、PubChemQC 205、Batt 73）。全部 15 个交集逐条复算，满足包含排除自洽。

## 2. 两两迁移（full 交集，含 bootstrap 与置换）

| 对 | n | Spearman rho | Kendall tau | Pearson | rho 95% CI | 置换 p |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| xtb-qm9 | 103 | 0.8855 | 0.7114 | 0.8410 | [0.8158, 0.9252] | 0.00050 |
| xtb-pubchemqc | 205 | 0.8824 | 0.7032 | 0.7981 | [0.8346, 0.9139] | 0.00050 |
| xtb-batt | 73 | 0.3280 | 0.2329 | 0.0854 | [0.1108, 0.5146] | 0.00150 |
| qm9-pubchemqc | 103 | 0.9823 | 0.9135 | 0.9946 | [0.9586, 0.9927] | 0.00050 |
| qm9-batt | 48 | 0.8177 | 0.6353 | 0.7387 | [0.6846, 0.8991] | 0.00050 |
| pubchemqc-batt | 71 | 0.7386 | 0.5642 | 0.7263 | [0.5994, 0.8365] | 0.00050 |

**关键结构**：两个 B3LYP 气相源（QM9 与 PubChemQC）彼此 rho = 0.9823、gap MAE = 0.1612 eV ⇒ 判 **near_same_level**（同泛函 B3LYP + 同相 gas，基组与几何仍不同）。而 xTB 与 Batt 的 rho 只有 0.3280。

## 3. 三角形非传递闭合

| 三角形 | rho(a,b) | rho(b,c) | rho(a,c) | 最大 gap | 断链边 |
| --- | ---: | ---: | ---: | ---: | --- |
| xtb-qm9-pubchemqc | 0.8855 | 0.9823 | 0.8824 | 0.0031 | xtb-pubchemqc |
| xtb-qm9-batt | 0.8855 | 0.8177 | 0.3280 | 0.4897 | xtb-batt |
| xtb-pubchemqc-batt | 0.8824 | 0.7386 | 0.3280 | 0.4107 | xtb-batt |
| qm9-pubchemqc-batt | 0.9823 | 0.7386 | 0.8177 | 0.0790 | pubchemqc-batt |

链条 QM9 → PubChemQC → Batt 几乎可传递（最大 gap 0.0790），而凡是跨到 xTB 的三角形都出现 > 0.4 的断口：**四层里的断链在 xTB–Batt 这条边上**。

## 4. 适用域声明（回应 item 33）

- QM9 与 PubChemQC 判 **near_same_level**：泛函与相相同（B3LYP + gas），但基组（6-31G(2df,p) vs 6-31G*）与几何来源（B3LYP vs PM6）不同，故判 near_same_level，不判 strict same_level。
- **strict same_level 源数仍为 0**；near_same_level 不得当作同层级可互换使用。
- 所有外部层数值仍只作只读对照，不入标签池、不入特征列。

## 5. 判据

| 判据 | 说明 | 读数 | 门槛 | 判定 |
| --- | --- | ---: | ---: | --- |
| H42a1 | 四层覆盖复现 237/103/205/73 | {'xtb': 237, 'qm9': 103, 'pubchemqc': 205, 'batt': 73} | {'xtb': 237, 'qm9': 103, 'pubchemqc': 205, 'batt': 73} | 成立 |
| H42a2 | 四路交集 = 48 | 48 | 48 | 成立 |
| H42a3 | 全部 15 个交集可复算且自洽 | 15 | 15 | 成立 |
| H42a4 | rho(QM9, PubChemQC) >= 0.95（near_same_level 排序） | 0.982334 | 0.95 | 成立 |
| H42a5 | rho(xTB, QM9) 落在 [0.85, 0.92] | 0.88554 | [0.85, 0.92] | 成立 |
| H42a6 | rho(xTB, PubChemQC) >= 0.85 | 0.88245 | 0.85 | 成立 |
| H42a7 | rho(xTB, Batt) <= 0.60（弱迁移） | 0.327996 | 0.6 | 成立 |
| H42a8 | 6 对 bootstrap 95% CI 下界全部 > 0 | 0.110823 | 0 | 成立 |
| H42a9 | 6 对置换 p 全部 <= 0.01 | 0.00149925 | 0.01 | 成立 |
| H42a10 | 存在非传递链：三角形最大 gap > 0.2 | 0.489678 | 0.2 | 成立 |
| H42a11 | QM9–PubChemQC 判 near_same_level（rho >= 0.95 且 gap MAE <= 0.30 eV） | {'spearman': 0.9823336400382101, 'gap_mae_ev': 0.1612343280021094} | {'spearman': 0.95, 'mae_ev': 0.3} | 成立 |
| H42a12 | strict same_level 源数（本轮仍为 0） | 0 | 0 | 成立 |
| H42a13 | 输入文件生成前后 sha256 不变 | 1 | 1 | 成立 |

## 6. 边界

- 只谈排序与层级声明，不把任何跨层数值写进标签池或特征列。
- near_same_level 是「同泛函 + 同相」的弱声明；基组与几何不同，不得升格为 strict same_level。
- 名册分母 241；四层各有缺行，照实登记不插补。
- 0 shot；四个冻结读数一个不动。
