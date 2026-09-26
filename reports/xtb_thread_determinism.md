# xTB 体积列线程确定性：根因、修复与验收

**日期：** 2026-09-26
**探针：** `probes/xtb_thread_determinism_probe.py`（把线程设置做成可扫参数 `--threads`）
**产出：** `probes/xtb_thread_determinism_probe_summary.json`、本报告
**测试：** `tests/test_xtb_thread_determinism.py`，15 项（14 项不启动 xTB + 1 项本机真跑）
**修复文件：** `src/electrolyte_ml/xtb_runner.py`（新增，唯一 launcher）、`scripts/run_xtb_physical_features.py`、`probes/xtb_protocol_migration_probe.py`、`probes/xtb_recovery_probe.py`
**本机 xTB：** `%LOCALAPPDATA%\electrolyte-ml\tools\xtb-6.7.1\extracted\xtb-6.7.1\bin\xtb.exe`，`xtb version 6.7.1pre (5071a88)`，sha256 `90bff4e570ffa10a1558364ee393711900bff239f02d313685353e055324f4c3`
**只读红线：** `data/dielectric_v03.csv` digest 复核仍为 `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`；`paper/` 零改动

## 一、判决（先说结论）

| 项 | 修复前 | 修复后 |
| --- | --- | --- |
| 同输入同设置重跑 `molecular_volume_A3`（2-氯-2-甲基丙烷，15 次） | **15/15 次几何各不相同**，体积跨 `93.368–93.448` ų（0.0856%） | **只有 1 种几何**，体积恒为 `93.408`（0.0000%） |
| 跨线程设置（父进程请求 1/2/4/8/16 线程） | 每个设置各自落在随机几何上，本机观测到 `93.408 / 93.424 / 93.448 / 93.440 / 93.440` | 5 个设置给出同一几何，xTB 横幅一律 `omp threads : 1`（0.0000%） |
| 固定线程重跑 run1 → run2（都从空 work-dir 起步，42 行 × 23 列） | — | **0 个格变化**（除 `xtb_seconds` 墙钟），体积列最大相对差 **0.0000000000%** |
| 冻结表 → 固定线程重跑（42 行） | — | 只动 **8 个格**（2 行 × 4 个体积导出列），最大相对差 **0.0132%** |

**验收门（同输入重跑体积列复现差 < 0.1%，且跨线程设置稳定）：通过。** 复现差 = **0.0000%**（要求 < 0.1%），跨 1/2/4/8/16 五档全部逐字节相同。

一句话根因：**xTB 6.7.1 的 SCF 与解析梯度走 OpenMP 归约，浮点加法不满足结合律，线程数（以及线程数大于 1 时每次运行的归约顺序）会扰动收敛梯度；`--opt` 以梯度范数为停机判据，于是 `xtbopt.xyz` 停在略微不同的点上，而 RDKit `ComputeMolVolume(gridSpacing=0.2)` 把体积量化到 0.008 ų 的格子，翻一格就把入库的体积列改写。**

**诚实边界（重要）**：修复前的漂移在本机、这两个分子上**并没有突破 0.1% 门**（15 次最大 0.0856%，60 次最大 0.0685%）。所以修复的理由不是「已证实的 >0.1% 误差」，而是**结果不可复现**：同一输入同一设置 60 次跑出 53 种不同几何，而这个上界没有任何先验保证。0.1% 门在修复前是「这次侥幸通过」，修复后是「结构上必然通过」。

## 二、根因：入口在线程，出口在体积格子

### 2.1 已经排除的两环（沿用 Week 11 实测，本轮未重做）

- `ComputeMolVolume` 自身 10 次复验确定；
- `generate_3d_xyz` 同 seed 5 次给出同一 block。

所以漂移只可能在 xTB 几何优化/调用路径上。

### 2.2 最小可复现证据：同一输入，只改线程环境

取冻结缓存里 2-氯-2-甲基丙烷的 `input.xyz`（`data/interim/xtb_features_v11plus/NBRKLOOSMBRFMH-UHFFFAOYSA-N__82a69bbe1429/input.xyz`），命令行完全不变（`xtb input.xyz --opt --gfn 2 --chrg 0 --uhf 0`），只改子进程环境变量。探针默认 `--repeats 15`、`--threads 1,2,4,8,16`：

| 臂 | 分子 | 请求线程 | xTB 自报 `omp threads` | 不同 `xtbopt.xyz` 数 / 15 | 体积范围（ų） | 相对跨度 |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| unpinned | 2-氯-2-甲基丙烷 | 1 | 1 | **1** | 93.408 – 93.408 | 0.0000% |
| unpinned | 2-氯-2-甲基丙烷 | 2 | 2 | **7** | 93.408 – 93.424 | 0.0171% |
| unpinned | 2-氯-2-甲基丙烷 | 4 | 4 | **15** | 93.368 – 93.448 | 0.0856% |
| unpinned | 2-氯-2-甲基丙烷 | 8 | 8 | **11** | 93.376 – 93.440 | 0.0685% |
| unpinned | 2-氯-2-甲基丙烷 | 16 | 16 | **12** | 93.384 – 93.440 | 0.0600% |
| unpinned | 1,1,1-三氟乙烷 | 1 | 1 | 1 | 60.632 – 60.632 | 0.0000% |
| unpinned | 1,1,1-三氟乙烷 | 2 | 2 | 2 | 60.640 – 60.640 | 0.0000% |
| unpinned | 1,1,1-三氟乙烷 | 4 | 4 | 5 | 60.632 – 60.640 | 0.0132% |
| unpinned | 1,1,1-三氟乙烷 | 8 | 8 | 2 | 60.632 – 60.632 | 0.0000% |
| unpinned | 1,1,1-三氟乙烷 | 16 | 16 | 2 | 60.632 – 60.632 | 0.0000% |
| **pinned** | 2-氯-2-甲基丙烷 | 1/2/4/8/16 | **1（全部）** | **1（全部）** | 93.408 – 93.408 | **0.0000%** |
| **pinned** | 1,1,1-三氟乙烷 | 1/2/4/8/16 | **1（全部）** | **1（全部）** | 60.632 – 60.632 | **0.0000%** |

三条读法：

1. **线程数 ≥ 2 时，同一设置重跑本身就不稳定**：请求 4 线程时 15 次跑出 15 种几何。所以这不是「每个线程数对应一个固定偏移量」，而是「只要不是 1 线程，结果就是随机的」。
2. **1 线程是确定性的**：unpinned 与 pinned 在 1 线程下给出同一个几何（`93.408` / `60.632`），说明 pinned 臂多设的 `OMP_DYNAMIC=FALSE`、`MKL_DYNAMIC=FALSE` 本身不改变数值——差异确实只来自线程数。
3. **跨线程也不稳**：同一个分子，请求 2/4/8/16 线程各自落在不同格子上，与 Week 11 记录的 `93.408/93.408/93.432/93.4/93.392` 是同一现象的不同抽样（每次抽样结果不同，本身就是结论）。

### 2.3 更长的采样（次要证据，同一探针）

`--threads 4 --arms unpinned --repeats 60`：

| 分子 | 不同几何 / 60 | 体积范围（ų） | 相对跨度 |
| --- | ---: | --- | ---: |
| 2-氯-2-甲基丙烷 | **53** | 93.376 – 93.440 | 0.0685% |
| 1,1,1-三氟乙烷 | 6 | 60.632 – 60.640 | 0.0132% |

`--threads 16 --arms pinned --repeats 60`：两个分子都只有 **1** 种几何，相对跨度 **0.0000%**。

### 2.4 为什么 0.008 ų 的格子会把这件事放大

`molecular_volume_A3` 由 `AllChem.ComputeMolVolume(..., gridSpacing=0.2)` 给出，返回值只能是 `0.2³ = 0.008 ų` 的整数倍，所以体积不是连续漂移而是「翻格子」：`93.4 / 93.408 / 93.416 / …`。冻结表里记的 `93.4` 与 `60.64` 正是某一次**多线程**运行的格子值——它们既不等于 1 线程的 `93.408`/`60.632`，也不可复现。

## 三、修复：一个 launcher 拥有子进程环境

新增 `src/electrolyte_ml/xtb_runner.py`：

- `DETERMINISTIC_THREADS = 1`；
- `xtb_thread_environment(base=None, *, threads=1)`：先把 `OMP_NUM_THREADS / MKL_NUM_THREADS / OMP_DYNAMIC / MKL_DYNAMIC` 四个变量删掉再写入固定值，**调用方的设置无法泄漏**；
- `xtb_optimisation_arguments(input_name, *, formal_charge)`：冻结命令行（`--opt --gfn 2 --chrg q --uhf 0`）的唯一出处；
- `run_xtb_subprocess(executable, arguments, *, cwd, timeout_seconds, environment=None)`：唯一的 `subprocess.run` 点；
- `reported_omp_threads(text)`：读 xTB 横幅里的 `omp threads`，供验收直接核对。

三个调用点全部改走它，且**不再各自拼环境**：

| 调用点 | 改动 |
| --- | --- |
| `scripts/run_xtb_physical_features.py` | `run_xtb` 删掉 `threads` 形参、删掉自建 `environment`、删掉 `--threads` CLI；改调 `run_xtb_subprocess` |
| `probes/xtb_protocol_migration_probe.py` | `run_candidate` 同上；`describe_run_environment(xtb)` 改为上报 `DETERMINISTIC_THREADS`（值仍是 1，committed 证据 JSON 不变，`--check` 仍通过） |
| `probes/xtb_recovery_probe.py` | `_run` 改调 `run_xtb_subprocess`（原本硬编码 `OMP_NUM_THREADS=1`，行为不变） |

**为什么修在这一层**：`--threads` 这个旋钮本身就是缺陷来源——它把「任务级性能选择」接到了「入库数值」上，所以修复是**把旋钮从持久化路径上拿掉**，而不是在每个调用点再抄一遍 `OMP_NUM_THREADS=1`。
`run_xtb_subprocess` 仍保留 `environment=` 逃生口，因为探针必须能复现 Week 11 的缺陷调用才能度量它；`tests/test_xtb_thread_determinism.py` 里有一条源码级不变量测试，断言上述三个文件里不再出现 `subprocess.run(`。

## 四、验收：修复前后 diff

### 4.1 冻结表 → 固定线程重跑（全表）

`data/processed/dielectric_physical_features_v11plus_new.csv`（42 行）对固定线程重跑 `run1`（同一 `--input`，从空 work-dir 起步）：

| inchikey | 名称 | 列 | 冻结表 | 固定线程重跑 | 绝对差 | 相对差 |
| --- | --- | --- | --- | --- | ---: | ---: |
| NBRKLOOSMBRFMH-UHFFFAOYSA-N | 2-chloro-2-methylpropane | `molecular_volume_A3` | 93.4 | 93.408 | 0.008 | 0.0086% |
| NBRKLOOSMBRFMH-UHFFFAOYSA-N | 2-chloro-2-methylpropane | `molar_volume_m3_mol` | 5.6246795e-05 | 5.6251612e-05 | 4.817e-09 | 0.0086% |
| NBRKLOOSMBRFMH-UHFFFAOYSA-N | 2-chloro-2-methylpropane | `mu_sq_over_Vm` | 105674.36 | 105665.31 | 9.05 | 0.0086% |
| NBRKLOOSMBRFMH-UHFFFAOYSA-N | 2-chloro-2-methylpropane | `alpha_over_Vm` | 0.10095821 | 0.10094957 | 8.64e-06 | 0.0086% |
| UJPMYEOUBPIPHQ-UHFFFAOYSA-N | 1,1,1-trifluoroethane | `molecular_volume_A3` | 60.64 | 60.632 | 0.008 | 0.0132% |
| UJPMYEOUBPIPHQ-UHFFFAOYSA-N | 1,1,1-trifluoroethane | `molar_volume_m3_mol` | 3.6518262e-05 | 3.6513444e-05 | 4.818e-09 | 0.0132% |
| UJPMYEOUBPIPHQ-UHFFFAOYSA-N | 1,1,1-trifluoroethane | `mu_sq_over_Vm` | 267075.39 | 267110.63 | 35.24 | 0.0132% |
| UJPMYEOUBPIPHQ-UHFFFAOYSA-N | 1,1,1-trifluoroethane | `alpha_over_Vm` | 0.077745893 | 0.077756151 | 1.0258e-05 | 0.0132% |

- 全表 42 行只动了这 **8 个格**；其余 39 个可用行的**全部 23 列**逐位相同（含 `total_energy_hartree`、`dipole_D`、`polarizability_au`、`homo_lumo_gap_ev`）。这正是「只有几何敏感列会动」的预期形状。
- 行状态统计三方一致：`{ok: 39, error: 3}`；3 个 error 仍是 Week 11 就有的多组分离子液体（`1,3-dimethylimidazolium dimethylphosphate`、`1-butyl-3-methylimidazolium hexafluorophosphate`、`1-butyl-2,3-dimethylimidazolium hexafluorophosphate`），与线程问题无关。
- 两次重跑耗时 10.28 s / 11.24 s。

### 4.2 固定线程重跑 → 再重跑（验收门本体）

两次都从**空 work-dir** 起步，`run1` 对 `run2`：除 `xtb_seconds`（墙钟）外 **0 个格变化**；4 个体积导出列在 39 个可用行上的最大相对差 **0.0000000000%**。

| 验收项 | 门 | 实测 | 判定 |
| --- | --- | --- | --- |
| 同输入重跑，体积列复现差 | < 0.1% | **0.0000%**（run1 对 run2，39 行 × 4 列） | 通过 |
| 跨线程设置稳定（父进程请求 1/2/4/8/16） | 稳定 | 5 档全部 `omp threads : 1`，几何逐字节相同，跨度 **0.0000%** | 通过 |
| 冻结表 → 固定线程重跑是否为可解释 diff | 需可解释 | 8 个格，最大 0.0132%，全部来自那 2 行的体积格子 | 通过 |
| 冻结表 → 固定线程重跑（若按 <0.1% 门口径） | < 0.1% | 最大 **0.0132%** | 通过 |

**本次未覆盖 `data/processed/dielectric_physical_features_v11plus_new.csv`**：该表是 Week 11 交付件（`probes/export_week11_results.py` 的产物清单里有它，`probes/dielectric_coverage_paired_benchmark*` 也消费它），Week 11 已决定「只做行尾归一、不按重跑覆盖」。本轮的 diff 全部跑在 `data/interim/xtb_v11plus_rerun/` 下，冻结表与任何 `data/processed/` 产物均未改动。上表的 `93.408`/`60.632` 就是**下一次 xTB 特征入库应当写入**的值。

## 五、顺带发现的第二个前置条件：工作目录必须干净

写探针时先踩了一次：第一版没有在每次重复前清空单元目录，结果**连 pinned（1 线程）臂**都出现 2 种几何、0.106% 跨度。原因是 xTB 会把工作目录里遗留的 `xtbrestart` 当作 SCF 重启文件读入，重新扰动收敛梯度——与线程问题一模一样的放大链，只是入口换成了磁盘。

最小复现（同一 `input.xyz`、同一 1 线程环境）：

| 运行方式 | 第 1 次 `xtbopt.xyz` sha256（前 16 位） | 第 2 次 |
| --- | --- | --- |
| 同一目录连跑两次，**不清空** | `aeccbe3eaad6eed7` | `a0ee5a4c28c93d94`（**不同**） |
| 每次**清空**后再跑 | `aeccbe3eaad6eed7` | `aeccbe3eaad6eed7`（相同） |

`scripts/run_xtb_physical_features.py::run_xtb` 本来就调 `_clear_run_artifacts`，`probes/xtb_protocol_migration_probe.py` 也清；只有新探针漏了，已补上（直接复用冻结 runner 的 `_clear_run_artifacts`，不另写一份）。`xtb_runner` 的模块 docstring 已把「cwd 必须无 xTB 残留」写成前置条件，`tests/test_xtb_thread_determinism.py` 加了一条不依赖 xTB 的护栏：预置一个 `xtbrestart`，断言 `run_xtb` 跑完后它已消失。

## 六、跑了什么

- `pytest tests/test_xtb_thread_determinism.py` → **15 passed**（含本机真跑 xTB 的那 1 项，未 skip）
- `pytest tests/test_xtb_thread_determinism.py tests/test_run_xtb_physical_features.py` → **17 passed**
- `pytest tests/test_xtb_thread_determinism.py tests/test_run_xtb_physical_features.py tests/test_xtb_protocol_migration_probe.py tests/test_xtb_recovery_probe.py tests/test_xtb_features.py tests/test_xtb_fragment_geometry_defect.py` → **80 passed**
- `pytest` 上述 6 个文件 + `tests/test_repo_hygiene.py` + `tests/test_build_dielectric_v03.py` → **193 passed**
- `pytest` 上述 8 个文件 + `tests/test_export_week11_results.py` + `tests/test_ci_workflow.py` → **220 passed**
- `ruff check` 本轮的 7 个文件（`xtb_runner.py`、冻结 runner、两个探针、新探针、两个测试）→ `All checks passed!`
- `ruff check scripts src probes tests notebooks` → **未全绿**：本轮实测 21 个报错**全部落在本轮未触碰的文件**上（`probes/_diag.tmp.py`、`probes/_show.tmp.py`、`probes/_test.tmp.py`、`probes/al_round3_oa_triage.py`），是并发进行的其他工作留下的临时/新文件；本轮的 7 个文件单独跑全绿
- `git status`：本轮只改/新增下述文件；工作区里 `paper/cover_letter.md` 在本轮期间被**另一个并发进程**改写（mtime 02:12:36，内容是 cover letter 的仓库 URL），本轮从未向 `paper/` 写入
- `probes/xtb_protocol_migration_probe.py --check` → `evidence invariants hold`（退出码 0）
- `probes/xtb_recovery_probe.py --check` → `evidence invariants hold`（退出码 0）

未跑全量 `pytest -q`（按本轮纪律，13–20 分钟）。

## 七、边界与未做的事（如实记）

- **修复前的漂移没有突破 0.1%**：本机这两行的最大观测跨度是 0.0856%（15 次）与 0.0685%（60 次）。所以「0.1% 门」在修复前是抽样侥幸，而不是已被证伪；不要把这个修复说成「消除了 >0.1% 的误差」。
- **探针只逐行测了那 2 个线程敏感行**；其余 37 个可用行的可复现性是靠 `run1` 对 `run2` 全表比对（0 格变化）间接确认的，没有逐行做 15 次重复。
- **`--threads` 旋钮已删除**：`scripts/run_xtb_physical_features.py --benchmark` 的计时现在是单线程数值（该路径不写特征表；`probes/p5b_xtb_timing.csv` 未重跑、未改动）。
- **3 个 error 行未处理**：多组分离子液体 SMILES 的起几何缺陷是另一条线（见 `probes/xtb_fragment_geometry_defect.py`），本轮未动。
- **未覆盖 xTB 版本维**：只验证了本机这台 `6.7.1pre (5071a88)`；换版本必须重跑本探针。
- 本报告、探针、测试、JSON 都是新建文件；`reports/decisions_log.md` 只改了 I6 相关段落。
