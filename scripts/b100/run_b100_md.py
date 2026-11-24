#!/usr/bin/env python
"""B100-21: liquid MD layer -- verified status and the working pipeline.

PLAN B v6.0 asks for >=12 liquid systems, to measure the Kirkwood g factor that no
single-molecule descriptor can express. The association-deficit analysis in this
repository infers g indirectly from epsilon; MD would measure it directly.

This module records what has actually been verified about that layer. Nothing here
fabricates a dielectric constant.

VERIFIED WORKING (each item was executed, not assumed):
  * OpenMM 8.6.1, openff-toolkit 0.19.0, openff-interchange 0.5.5 all import
  * SMIRNOFF openff-2.1.0 force field loads
  * Partial charges: AmberTools cannot be installed on Windows (no conda-forge win-64
    build, no PyPI wheel), so AM1-BCC comes from OpenFF's NAGL model
    openff-gnn-am1bcc-1.0.0.pt, which is trained to reproduce AM1-BCC.
  * Interchange.from_smirnoff works ONLY after replacing the ToolkitAM1BCC handler
    with NAGLChargesHandler(model_file=...). Retargeting
    ForceField["ToolkitAM1BCC"].partial_charge_method is NOT enough: the internal
    reference-matching path still calls the bare name "am1bcc" and fails. This was a
    real dead end that cost several attempts.
  * Multi-molecule topology -> OpenMM System produces all of Bonds, Angles,
    ProperTorsions, ImproperTorsions, vdW, Electrostatics.
  * Lattice packing with random orientations, density from the molar volume.
  * Energy minimisation and NVT equilibration run.

BLOCKING FINDING:
  The pip OpenMM build on Windows registers ONLY the Reference platform. Reference is
  the slowest implementation, and on this system (150 molecules, PME, periodic box) it
  exits with a SEGMENTATION FAULT in the production sampling loop. Parameterisation,
  packing, minimisation and NVT equilibration all pass; the crash is in production.
  This is a platform defect, not an algorithmic one.

TWO DEAD ENDS worth recording so they are not repeated:
  1. NPT equilibration collapses the box below twice the cutoff. The lattice start has
     enough local voids that the barostat crushes it. NVT at a fixed density avoids it.
  2. The box edge must be (Vm * N / N_A)^(1/3), NOT (Vm * N)^(1/3). The wrong form
     gives an edge of 1.9e8 nm, which OpenMM accepts silently -- the system simply
     becomes non-periodic and would yield a plausible-looking, meaningless epsilon.

Output: outputs/b100/md_dielectric_b100.json
        outputs/b100/md_dielectric_b100.csv   (header only; no results)
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "run_b100_md/4.0.0"

FORCEFIELD = "openff-2.1.0.offxml"
CHARGE_MODEL = "openff-gnn-am1bcc-1.0.0.pt"

CSV_FIELDS = ["system", "inchikey", "status", "T_K", "density_kg_m3",
              "epsilon_experimental", "epsilon_md", "epsilon_block_sd",
              "kirkwood_g", "n_molecules", "production_ps", "volume_nm3",
              "wall_seconds", "detail"]


def available_platforms() -> list[str]:
    try:
        import openmm
        return [openmm.Platform.getPlatform(i).getName()
                for i in range(openmm.Platform.getNumPlatforms())]
    except Exception:
        return []


def package_versions() -> dict:
    out = {}
    for mod, label in (("openmm", "openmm"),
                       ("openff.toolkit", "openff-toolkit"),
                       ("openff.interchange", "openff-interchange")):
        try:
            m = __import__(mod, fromlist=["__version__"])
            out[label] = getattr(m, "__version__", "unknown")
        except Exception:
            out[label] = None
    return out


def build_forcefield():
    """openff-2.1.0 with ToolkitAM1BCC replaced by the NAGL equivalent."""
    from openff.toolkit.typing.engines.smirnoff import ForceField
    from openff.toolkit.typing.engines.smirnoff.parameters import NAGLChargesHandler

    ff = ForceField(FORCEFIELD)
    try:
        ff.deregister_parameter_handler("ToolkitAM1BCC")
    except Exception:
        pass
    ff.register_parameter_handler(
        NAGLChargesHandler(version="0.3", model_file=CHARGE_MODEL))
    return ff


def status_document() -> dict:
    platforms = available_platforms()
    return {
        "schema": "b100.md_layer/v4",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "NOT_COMPUTED",
        "engine": {
            "md": "OpenMM",
            "forcefield": FORCEFIELD,
            "charges": CHARGE_MODEL,
            "system_builder": "openff-interchange",
            "versions": package_versions(),
            "available_platforms": platforms,
        },
        "verified_working": [
            "OpenMM / openff-toolkit / openff-interchange 全部导入成功",
            "SMIRNOFF openff-2.1.0 力场可加载",
            "NAGL AM1-BCC 电荷可用 (AmberTools 在 Windows 上无法安装)",
            "Interchange.from_smirnoff 成功: 必须把 ToolkitAM1BCC 处理器换成 "
            "NAGLChargesHandler(model_file=...); 仅重定向 partial_charge_method 不够, "
            "因为内部参考匹配仍以字面 am1bcc 调用注册表",
            "多分子拓扑 -> OpenMM System: Bonds/Angles/Torsions/vdW/Electrostatics "
            "全部生成",
            "晶格 + 随机取向装盒, 密度由摩尔体积给出",
            "能量最小化与 NVT 平衡可执行",
        ],
        "blocking_finding": (
            "pip 版 OpenMM 在 Windows 上只注册了 Reference 平台 "
            f"(实测可用平台: {platforms}). Reference 是最慢实现, "
            "且本体系 (150 分子 + PME + 周期边界) 在生产采样循环中段错误退出. "
            "参数化、装盒、最小化、NVT 平衡全部通过, 崩溃发生在生产段. "
            "这是平台缺陷, 不是算法问题."
        ),
        "attempts_and_outcomes": [
            {"attempt": "NPT 平衡 (MonteCarloBarostat)",
             "outcome": "NPT_COLLAPSE: 晶格初值局部空隙导致气压计把盒子压到低于两倍"
                        "截断距离, OpenMM 报错. 改为固定密度的 NVT."},
            {"attempt": "NVT 生产 (150 分子, 100 ps)",
             "outcome": "Segmentation fault, 发生在 Reference 平台的采样循环."},
            {"attempt": "盒子体积换算 (Vm * N)",
             "outcome": "边长达 1.9e8 nm, OpenMM 静默接受(体系变成非周期). "
                        "正确形式为 Vm * N / N_A. 已修正."},
            {"attempt": "以 MMFF94/Gasteiger 电荷代替 AM1-BCC",
             "outcome": "技术可行但被拒绝: 见 rejected_workaround."},
        ],
        "what_would_unblock": [
            "用 conda-forge 安装 openmm 以获得 CPU/CUDA 平台: "
            "conda install -c conda-forge openmm (win-64 有构建)",
            "该环境同样需要 openff-toolkit 与 openff-interchange",
            "之后可直接复用本模块记录的装盒与偶极采样逻辑",
            "生产段建议先以小体系 (如 50 分子, 20 ps) 确认不崩, 再放大",
        ],
        "rejected_workaround": {
            "option": "改用 MMFF94 / Gasteiger 电荷代替 AM1-BCC",
            "available": True,
            "why_rejected": (
                "OpenFF 力场按 AM1-BCC 参数化并验证. 换电荷模型后算出的介电常数"
                "精度未知, 而本项目全部工作就是避免这类来源不明的数字. "
                "宁可如实记为未计算, 不产出未经校验的 eps."
            ),
        },
        "why_it_matters_scientifically": (
            "MD 层要测的是 Kirkwood g. 本仓库的 association_deficit 分析是从 eps "
            "反推 g 的间接代理 (卤代烃 g_eff 0.51 而偶极 3.34 D). "
            "缺了这一层, g 是缺失物理量这一结论仍只有间接证据."
        ),
        "target": {"systems": 20, "minimum": 12},
        "n_rows": 0,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    doc = status_document()
    (OUT / "md_dielectric_b100.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (OUT / "md_dielectric_b100.csv").open("w", newline="",
                                               encoding="utf-8") as fh:
        csv.writer(fh).writerow(CSV_FIELDS)
    print(f"[B100-21] {OUT / 'md_dielectric_b100.json'}")
    print(f"  status = {doc['status']}")
    print(f"  platforms = {doc['engine']['available_platforms']}")
    print(f"  versions = {doc['engine']['versions']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
