# Week 0 环境搭建与验证（Windows PowerShell）

本文记录本项目在 Windows PowerShell 下的标准环境流程。所有项目命令默认从仓库根目录
`E:\Claude Code\电解质ML\电解质ML` 运行。

## 当前机器状态

截至 2026-09-22，当前 PowerShell 中没有可直接调用的全局 `python`、`python3` 或
`conda` 命令。Windows `py` 启动器即使存在，也只能看到 Python 3.9，低于本项目要求的
Python 3.11；不要用它运行项目或测试。

因此，本项目不依赖全局 Python 或全局 conda 包。必须先用 Miniconda 创建并激活
`electrolyte-ml` 环境，再执行检查、测试或数据脚本。

## 1. 安装或恢复 Miniconda

先检查是否已有可用的 conda：

```powershell
Get-Command conda -ErrorAction SilentlyContinue
conda --version
```

如果第二条命令失败，可选择以下任一方式：

1. 使用 winget 安装：

   ```powershell
   winget install --id Anaconda.Miniconda3 --exact --source winget
   ```

2. 从官方地址下载 Windows x86_64 安装程序，按图形界面选择“Just Me”安装：

   ```powershell
   $installer = Join-Path $env:TEMP 'Miniconda3-latest-Windows-x86_64.exe'
   Invoke-WebRequest `
     'https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe' `
     -OutFile $installer
   Start-Process -Wait -FilePath $installer
   ```

安装完成后关闭并重新打开 PowerShell。若仍找不到 `conda`，从开始菜单打开
“Miniconda Prompt”，执行 PowerShell 初始化，然后再次重开终端：

```powershell
conda init powershell
```

重新打开 PowerShell 后验证：

```powershell
Get-Command conda
conda --version
conda info --base
```

`Get-Command conda` 应返回一个 `.exe` 或 PowerShell 函数路径；版本命令应正常输出。

## 2. 无 conda 时的镜像快速通道

如果暂时不想安装 Miniconda，但本机已有 Python 3.11 或 3.12，可以先建立项目
`.venv`。这条路径已在 2026-09-22 实际验证；`pip` 默认源在当天只有约 190 KB/s，
而 USTC 镜像完成同一批下载后本地安装成功。

```powershell
Set-Location 'E:\Claude Code\电解质ML\电解质ML'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" `
  -i https://pypi.mirrors.ustc.edu.cn/simple `
  --timeout 60 `
  --retries 3
.\.venv\Scripts\python.exe scripts\check_environment.py
```

若本机没有 Python 3.12，可把第一条改为已有的 Python 3.11。镜像只是下载通道，
不会改变包版本解析和依赖内容。需要更快的备用源时，可按当前网络在
`https://pypi.tuna.tsinghua.edu.cn/simple`、`https://mirrors.aliyun.com/pypi/simple`
和 `https://pypi.mirrors.ustc.edu.cn/simple` 之间切换。

## 3. 创建 Conda 环境（正式路径）

```powershell
Set-Location 'E:\Claude Code\电解质ML\电解质ML'
conda env create -f environment.yml
conda activate electrolyte-ml
```

环境已存在时不要重复创建，更新即可：

```powershell
conda env update -n electrolyte-ml -f environment.yml
conda activate electrolyte-ml
```

确认当前解释器确实来自目标环境：

```powershell
python --version
python -c "import sys; print(sys.executable)"
```

Python 必须为 3.11 或更高，且 `sys.executable` 路径应包含
`envs\electrolyte-ml`。若仍显示 Python 3.9 或系统路径，说明环境没有正确激活。

## 4. 验证依赖与 RDKit

环境检查器只使用标准库和已声明依赖，导入阶段不会联网。它会检查 Python 版本、关键包
是否可导入及版本是否满足下限，并用乙醇 SMILES `CCO` 做最小 RDKit 解析和分子量测试。

```powershell
python scripts/check_environment.py
```

成功时退出码为 `0`；任一检查失败时退出码为非零。需要给其他程序读取结果时使用：

```powershell
python scripts/check_environment.py --json
```

JSON 顶层字段包括 `passed`、`python`、`packages`、`rdkit_smiles` 和 `failures`。

当前最低版本如下：

| 包 | 最低版本 |
|---|---:|
| Python | 3.11 |
| numpy | 1.26 |
| pandas | 2.1 |
| scikit-learn | 1.3 |
| xgboost | 2.0 |
| matplotlib | 3.8 |
| rdkit | 2023.9 |
| PyYAML | 6.0 |
| requests | 2.31 |
| pytest | 7.4 |

## 5. 运行测试

先运行 Week 0 环境检查器的针对性测试：

```powershell
python -m pytest tests/test_check_environment.py -q
```

再运行当前仓库的全部测试：

```powershell
python -m pytest -q
```

当 Week 0 其他交付物也完成后，可运行整体验收脚本：

```powershell
python scripts/verify_week0.py
```

该脚本会检查 ThermoML、文献笔记等更多文件；在这些文件尚未完成时失败是预期行为，
不能替代上面的环境测试。

## 6. 常见故障排查

| 症状 | 原因与处理 |
|---|---|
| `conda` 不是内部或外部命令 | 安装后未重开终端，或 PowerShell 尚未初始化。重开终端；必要时从 Miniconda Prompt 执行 `conda init powershell`。 |
| `conda activate` 后 `python` 仍是 3.9 | 环境未激活或 PATH 中其他解释器优先。用 `conda info --envs` 和 `python -c "import sys; print(sys.executable)"` 检查，再运行 `conda activate electrolyte-ml`。 |
| `check_environment.py` 报告 Python 低于 3.11 | 当前正在使用全局或旧解释器。关闭终端，重新打开并激活 `electrolyte-ml`。 |
| 某包无法导入 | 确认环境已激活，再运行 `conda list` 查看该包；然后使用 `conda env update -n electrolyte-ml -f environment.yml` 更新环境。 |
| 包版本低于要求 | 优先从 `environment.yml` 更新环境；不要在项目中进行全局 `pip install`。 |
| RDKit 最小 SMILES 测试失败 | 检查 `conda list rdkit` 和平台是否为 64 位 Windows；必要时删除并重建环境。不要用 pip 包临时替代 conda-forge 构建。 |
| `No module named pytest` | 环境未激活或环境不完整。激活后重新运行 `conda env update -n electrolyte-ml -f environment.yml`。 |
| `conda env create` 下载失败 | 检查网络、代理和系统时间，稍后重试；不要修改项目文件来绕过依赖安装。 |
| PowerShell 拒绝激活脚本 | 在当前用户范围查看 `Get-ExecutionPolicy -List`。若组织策略允许，可设置为 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，然后重开终端。 |
| TLS/证书错误 | 检查系统时间、公司代理和证书链。不要通过关闭证书校验来长期绕过问题。 |

## 7. 完成标准

以下命令均从仓库根目录执行，并且全部通过后，Week 0 环境部分才算完成：

```powershell
conda activate electrolyte-ml
python scripts/check_environment.py
python -m pytest tests/test_check_environment.py -q
```

如需留档，保存普通输出和 `--json` 输出、当前提交哈希，以及
`conda list --explicit` 的结果。不要记录 API 密钥、访问令牌或未脱敏的私有数据。
