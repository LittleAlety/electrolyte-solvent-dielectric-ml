# W37-B 报告：还原轴准入清单接进交付/导出链路

- **性质**：治理件 / 后验接线（只读真表与论文），**不占 shot**
- **累计 shot**：19
- **回答**：README §11 第 18 条「准入清单接进交付 manifest（W36-D 已备件，未接线）」

## 1. 接线方式

scripts/check_redox_admission.py 机械解析论文附录 A/B/C 的表格行，把其中出现的
登记读数（quoted_value 三位有效数字）与「合法子集/总体」分数绑到
probes/artifacts/w35_gated_reference_register.csv，逐点调用 W36-D 的 admit()：

1. 绑不到登记行 -> unregistered 违规；
2. admit() 抛 AdmissionRefused -> refused 违规；
3. 还原轴的 mark 由 W34-A 守卫复算，与登记值不一致 -> mark_mismatch 违规（禁止手写标记）；
4. 氧化轴引用点按既有约定标「不适用（门禁只覆盖还原轴）」。

全部通过 -> stdout 打印一行 JSON 且 exit 0；任一违规 -> 打印 JSON 且 exit 1。

## 2. 判据

| 判据 | 说明 | value | threshold | 裁决 |
| --- | --- | --- | --- | --- |
| H37b1 | 校验器在真表上 exit 0 且输出 JSON passed=true | 1.0 | 1.0 | 成立 |
| H37b2 | 论文侧引用点 >= 6 且全部找到登记行（未登记 0） | 7.0 | 6.0 | 成立 |
| H37b3 | 还原轴引用点全部由 W34-A 守卫复算（mark 非空、与登记值零不一致）；氧化轴标「不适用」 | 5.0 | 5.0 | 成立 |
| H37b4 | 合成违规自检：删行/改名 -> exit != 0，未改动副本 -> exit == 0 | 3.0 | 3.0 | 成立 |
| H37b5 | 0 shot（累计 19）、全 LF / 无 BOM、不改任何已交付字节 | 0.0 | 0.0 | 成立 |

## 3. 论文侧引用点清单

| 论文行 | 附录 | 表格行 | 轴 | 登记行 | 准入 | 标记 |
| --- | --- | --- | --- | --- | --- | --- |
| 913 | 附录 A | 跨层级对照（22 化合物） | oxidation | r6_ox_gfn2 | 准入 | 不适用（门禁只覆盖还原轴） |
| 913 | 附录 A | 跨层级对照（22 化合物） | oxidation | r6_ox_orca | 准入 | 不适用（门禁只覆盖还原轴） |
| 913 | 附录 A | 跨层级对照（22 化合物） | reduction | r6_red_gfn2 | 准入 | 不可判定 |
| 913 | 附录 A | 跨层级对照（22 化合物） | reduction | r6_red_orca | 准入 | 不可判定 |
| 914 | 附录 A | 态合法性门禁（W33-A） | reduction | r6_red_gfn2 | 准入 | 不可判定 |
| 914 | 附录 A | 态合法性门禁（W33-A） | reduction | r6_red_orca | 准入 | 不可判定 |
| 914 | 附录 A | 态合法性门禁（W33-A） | reduction | w33a_gfn2_gas | 准入 | 可宣读 |

## 4. 合成违规自检

把 register/registry/manifest 的副本写到临时目录后：

- 未改动副本 -> 校验器 exit 0（无假阳性）；
- 删掉被引用的登记行 r6_red_gfn2 -> 校验器 exit != 0（报 unregistered）；
- 把该行 reference_id 改名 -> 校验器 exit != 0。

**仓库里的真表未被改动**（前后 sha256 相等，见 summary 的 inputs）。

## 5. 为什么接在 test_repo_hygiene 而不是改历史导出器

tests/test_repo_hygiene.py 已被各周导出器的 VERIFIERS 列表引用（如 Week 14–20、
Week 25–27 的 run_verifiers）。在这些导出器的验证块里追加一个测试函数，等于把准入
检查**自动接进导出阶段的验证块**：任何人在导出时都会连带走这一关。

反过来，去改历史周的导出脚本会改动已交付字节、破坏已交付包的回归测试（AF-12 同族
风险：交付字节一变，artifacts_commit 就无法标识原交付）。因此只**在 test_repo_hygiene
末尾追加**一个 subprocess 测试，调用 scripts/check_redox_admission.py 并断言 exit 0。

## 6. 边界

- 准入清单只覆盖还原轴（阴离子态审计）；氧化轴引用点按既有约定标「不适用」。
- 拒答不是缺失值：mark=不可判定的点不得插补、赋伪值或静默丢弃。
- 本校验器只读；不拟合模型、不改任何已交付字节。
- 不改任何已交付字节；不 commit。
