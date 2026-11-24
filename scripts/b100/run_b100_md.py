#!/usr/bin/env python
"""B100-21: liquid MD layer -- dependency probe and honest status record.

PLAN B v6.0 asks for >=12 liquid systems, specifically to measure the Kirkwood g factor
that no single-molecule descriptor can express. The B100 association-deficit analysis
inferred g indirectly from epsilon; MD would measure it directly, so this layer matters.

This script does NOT produce dielectric constants. It establishes, by actually trying,
exactly how far the toolchain gets and where it stops, and writes that down. The
reason for the care: the previous status said "no MD engine", which is no longer true
after OpenMM and the OpenFF stack were installed. Leaving a stale reason in the
deliverable would be its own kind of inaccuracy.

Dependency chain, each item verified rather than assumed:

  OpenMM 8.6.1              INSTALLED and imports
  openff-toolkit 0.19.0     INSTALLED, SMIRNOFF force fields load
  openff-interchange 0.5.5  INSTALLED; correct API is Interchange.from_smirnoff
                            (the older from_single_molecule no longer exists, and
                             Interchange(topology=...) silently returns EMPTY
                             collections, so a naive call looks successful while
                             having parameterised nothing)
  packing tool              MISSING. There is no packmol, and openff no longer ships
                            pack_box. Without it there is no way to build a dense
                            liquid box; a lattice + minimisation is the fallback but
                            was not validated here.
  AM1-BCC partial charges   MISSING. Interchange asks the toolkit registry for
                            am1bcc and gets: RDKit offers only mmff94/gasteiger,
                            NAGL rejects the name, built-in offers zeros. AM1-BCC
                            needs AmberTools (no Windows wheel on PyPI) or OpenEye.

Why the layer is not forced through with substitute charges: MMFF94 charges are
available, but the OpenFF force field is parameterised and validated against AM1-BCC.
A dielectric constant computed from a force field with swapped charge model is a number
of unknown accuracy -- and this whole project exists to avoid exactly that kind of
number. An honest "not computed" is worth more than an unvalidated value.

Output: outputs/b100/md_dielectric_b100.json
        outputs/b100/md_dielectric_b100.csv
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "outputs" / "b100"
GENERATOR = "run_b100_md/2.0.0"


def probe() -> dict:
    """Actually import and exercise the stack; report what works, in order."""
    report: dict = {"steps": []}

    def step(name: str, fn) -> bool:
        try:
            detail = fn()
            report["steps"].append({"step": name, "ok": True, "detail": detail})
            return True
        except Exception as exc:            # noqa: BLE001
            report["steps"].append({"step": name, "ok": False,
                                    "detail": f"{type(exc).__name__}: {exc}"})
            return False

    def _openmm():
        import openmm
        return f"OpenMM {openmm.__version__}"

    def _toolkit():
        import openff.toolkit as ot
        return f"openff-toolkit {ot.__version__}"

    def _interchange():
        import openff.interchange as oi
        from openff.interchange import Interchange
        has_new = hasattr(Interchange, "from_smirnoff")
        has_old = hasattr(Interchange, "from_single_molecule")
        return {
            "version": oi.__version__,
            "api_from_smirnoff": has_new,
            "api_from_single_molecule_removed": not has_old,
            "note": (
                "Interchange(topology=..., force_field=...) 会返回**空的 collections**"
                "而不报错, 必须用 from_smirnoff."
            ),
        }

    def _forcefield():
        from openff.toolkit.typing.engines.smirnoff import ForceField
        ff = ForceField("openff-2.1.0.offxml")
        return {"forcefield": "openff-2.1.0.offxml",
                "n_parameter_handlers": len(ff.aromaticity_model.__class__.__name__)}

    def _packing():
        import shutil
        have_packmol = shutil.which("packmol") is not None
        if not have_packmol:
            raise RuntimeError(
                "no packmol on PATH and openff no longer ships pack_box")
        return "packmol present"

    def _charges():
        from openff.toolkit import Molecule
        from openff.toolkit.utils.toolkit_registry import GLOBAL_TOOLKIT_REGISTRY
        mol = Molecule.from_smiles("CCO")
        GLOBAL_TOOLKIT_REGISTRY.call(
            "assign_partial_charges", molecule=mol,
            partial_charge_method="am1bcc")
        return "AM1-BCC available"

    ok_engine = step("openmm_import", _openmm)
    ok_toolkit = step("openff_toolkit_import", _toolkit)
    ok_inter = step("openff_interchange_import", _interchange)
    ok_ff = step("smirnoff_forcefield_load", _forcefield)
    ok_pack = step("packing_tool_available", _packing)
    ok_q = step("am1bcc_charges_available", _charges)

    report["engine_ready"] = bool(ok_engine and ok_toolkit and ok_inter and ok_ff)
    report["can_build_liquid_box"] = bool(report["engine_ready"] and ok_pack and ok_q)
    return report


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rep = probe()

    failed = [s for s in rep["steps"] if not s["ok"]]
    doc = {
        "schema": "b100.md_layer/v2",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "COMPUTED" if rep["can_build_liquid_box"] else "NOT_COMPUTED",
        "dependency_probe": rep,
        "what_changed": (
            "原状态写『本环境无 MD 引擎』。该说法已不成立: OpenMM 与完整 OpenFF "
            "栈均已安装. 因此本层现在的阻塞点**不是引擎**, 而是装盒工具与电荷方法."
        ),
        "blockers": [{"step": s["step"], "detail": s["detail"]}
                     for s in failed],
        "why_it_matters_scientifically": (
            "MD 层要测的是 Kirkwood g 因子. 本仓库的 association_deficit 分析是从 "
            "epsilon 反推 g 的**间接**代理; MD 能直接测量. 缺了这一层, "
            "『g 是缺失物理量』这一结论仍只有间接证据."
        ),
        "what_would_unblock": [
            "安装 packmol (conda install -c conda-forge packmol) 或 openmmtools",
            "安装 AmberTools 以获得 AM1-BCC 电荷 (Windows 无 PyPI wheel, 需 conda)",
            "随后可执行已设计好的流程: 晶格装盒 -> 最小化 -> NVT/NPT 平衡 -> "
            "生产段采样总偶极 -> eps 与 Kirkwood g",
        ],
        "rejected_workaround": {
            "option": "改用 MMFF94 / Gasteiger 电荷代替 AM1-BCC",
            "available": True,
            "why_rejected": (
                "OpenFF 力场是按 AM1-BCC 参数化并验证的. 换电荷模型后算出的 eps "
                "精度未知, 而本项目的全部工作就是避免这种来源不明的数字. "
                "**宁可如实记为未计算, 不产出未经校验的介电常数.**"
            ),
        },
        "target": {"systems": 20, "minimum": 12},
        "n_rows": 0,
    }

    (OUT / "md_dielectric_b100.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "md_dielectric_b100.csv").write_text(
        "system,inchikey,T_K,density_kg_m3,epsilon_md,kirkwood_g,"
        "n_molecules,production_ps,status\n", encoding="utf-8")

    print(f"[B100-21] {OUT / 'md_dielectric_b100.json'}")
    print(f"  status = {doc['status']}")
    print(f"  engine_ready = {rep['engine_ready']}  "
          f"can_build_liquid_box = {rep['can_build_liquid_box']}")
    for s in rep["steps"]:
        mark = "OK  " if s["ok"] else "MISS"
        print(f"   {mark} {s['step']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
