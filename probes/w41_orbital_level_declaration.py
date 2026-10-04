# -*- coding: utf-8 -*-
"""W41-D：把轨道通道的层级差写成适用域声明（GFN2-xTB / B3LYP 气相 / ωB97X-V+SMD 三方）。

README §11 第 27 条与 W40 交付说明 §5 第 3 条登记：QM9 只能作**排序先验**；若要在 HOMO/LUMO
通道上加权重，需先补一个**同层级**的外部源（Batt-P30K 的 ωB97X-V 层），并把「层级不同」写进
适用域声明。本件把三条件（我们自己的 GFN2-xTB、QM9 的 B3LYP 气相、Batt-P30K 的
ωB97X-V/def2-TZVPPD/SMD）放到同一张名册上实测两两排序迁移，检验它是不是可传递，并把
「层级不同」机械地写进 `w41_orbital_level_declaration.json`。

只读：名册（241 行）、`w39_qm9_overlap.csv`（103 命中）、`data/raw/batt/Batt-P30K.h5`
（按 InChIKey 复算名册命中）、`four_core_label_provenance_sidecar.csv`。不写任何标签池或特征列。

Run:
    .venv/Scripts/python.exe probes/w41_orbital_level_declaration.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

try:
    from probes.export_results_common import write_json_stable
except ImportError:
    from export_results_common import write_json_stable

ARTIFACTS = REPOSITORY_ROOT / "probes" / "artifacts"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w41_governance_prereg.json"
ROSTER_CSV = REPOSITORY_ROOT / "data" / "processed" / "dielectric_physical_features_v03.csv"
QM9_OVERLAP = ARTIFACTS / "w39_qm9_overlap.csv"
BATT_H5 = REPOSITORY_ROOT / "data" / "raw" / "batt" / "Batt-P30K.h5"
SIDECAR_CSV = REPOSITORY_ROOT / "data" / "processed" / "four_core_label_provenance_sidecar.csv"
REGISTRY_CSV = ARTIFACTS / "w41_orbital_level_registry.csv"
PAIRS_CSV = ARTIFACTS / "w41_orbital_pair_matrix.csv"
HITS_CSV = ARTIFACTS / "w41_orbital_batt_hits.csv"
DECLARATION_PATH = ARTIFACTS / "w41_orbital_level_declaration.json"
SUMMARY_PATH = ARTIFACTS / "w41_orbital_level_declaration_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "w41_orbital_level_declaration.md"
FIGURE_PATH = ARTIFACTS / "w41_orbital_level_declaration.png"

SCHEMA = "w41_orbital_level_declaration/summary@1"
TASK = "week41_orbital_level_declaration"

FROZEN_BASELINE = 0.4091179943351143
FROZEN_HEADLINE = 0.4766400383507876
FROZEN_SINGLE_REPRESENTATION = 0.5861142332208197
FROZEN_PROMOTED_ARM = 0.6216672295270079

LEVELS = (
    ("batt_wb97xv_smd", "Batt-P30K.h5（GSDS）", "ωB97X-V/def2-TZVPPD/SMD(epsilon=18.5)",
     "implicit solvent SMD(eps=18.5)", "MIT", "primary_reference",
     "four_core_label_provenance_sidecar.csv（source_layer=batt_p30k_primary）"),
    ("themol_gfn2_gas", "THEMol 几何上的 GFN2-xTB 单点", "GFN2-xTB（气相单点）",
     "gas phase", "CC BY-NC 4.0（非商用）", "reference_only / calibrated_estimate",
     "four_core_label_provenance_sidecar.csv（source_layer=themol_gfn2）"),
    ("qm9_b3lyp_gas", "QM9（W39/W40 外部对照层）", "B3LYP/6-31G(2df,p)",
     "gas phase", "CC BY 4.0", "external_control_layer",
     "reports/w39_qm9_crosscheck.md / reports/w40_orbital_external.md"),
)

REGISTRY_FIELDS = ("level_id", "source", "level_of_theory", "phase", "license", "role",
                   "provenance", "coverage_on_241")
PAIR_FIELDS = ("pair", "subset", "level_a", "level_b", "n", "spearman", "kendall",
               "pearson", "slope_a_on_b", "intercept_a_on_b", "r2", "comparability")
HITS_FIELDS = ("inchikey", "batt_gap_ev")

REGISTERED_NEGATIVES: tuple[str, ...] = ("H41d8",)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_prereg() -> Mapping[str, object]:
    payload = json.loads(PREREG_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("status") != "locked_before_run":
        raise SystemExit("w41 prereg is not locked_before_run: " + str(payload.get("status")))
    return payload


def write_csv_lf(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = [",".join(fields)]
    for row in rows:
        cells = []
        for field in fields:
            value = row.get(field, "")
            text = "" if value is None else str(value)
            if any(ch in text for ch in (',', '"', '\n')):
                text = '"' + text.replace('"', '""') + '"'
            cells.append(text)
        buffer.append(",".join(cells))
    path.write_text("\n".join(buffer) + "\n", encoding="utf-8", newline="\n")


def _float_or_none(text: str) -> float | None:
    text = (text or "").strip()
    return float(text) if text else None


def read_roster() -> dict[str, dict[str, object]]:
    roster: dict[str, dict[str, object]] = {}
    with ROSTER_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            roster[row["inchikey"]] = {
                "name": row["name"], "smiles": row["smiles"],
                "xtb_gap_ev": _float_or_none(row["homo_lumo_gap_ev"]),
            }
    return roster


def read_qm9() -> dict[str, float]:
    out: dict[str, float] = {}
    with QM9_OVERLAP.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            out[row["inchikey"]] = float(row["qm9_gap_ev"])
    return out


def read_batt(roster: Mapping[str, Mapping[str, object]]) -> dict[str, float]:
    import h5py
    from rdkit import Chem
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")

    want: dict[str, str] = {}
    for inchikey, record in roster.items():
        mol = Chem.MolFromSmiles(str(record["smiles"]))
        if mol is not None:
            want[Chem.MolToInchiKey(mol)] = inchikey
    hits: dict[str, float] = {}
    handle = h5py.File(BATT_H5, "r")
    try:
        for key in handle:
            try:
                smiles = handle[key]["smiles"][()][0]
                if isinstance(smiles, bytes):
                    smiles = smiles.decode()
            except Exception:
                continue
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                continue
            inchikey = Chem.MolToInchiKey(mol)
            if inchikey in want:
                hits[want[inchikey]] = float(handle[key]["gap"][()][0])
    finally:
        handle.close()
    return hits


def _pair(x: Sequence[float], y: Sequence[float]) -> dict[str, float]:
    from scipy import stats
    slope, intercept, r_value, p_value, std_err = stats.linregress(list(x), list(y))
    return {
        "n": len(x),
        "spearman": float(stats.spearmanr(x, y).statistic),
        "kendall": float(stats.kendalltau(x, y).statistic),
        "pearson": float(stats.pearsonr(x, y).statistic),
        "slope": float(slope), "intercept": float(intercept), "r2": float(r_value ** 2),
    }


def build(prereg: Mapping[str, object]) -> dict[str, object]:
    roster = read_roster()
    qm9 = read_qm9()
    batt = read_batt(roster)
    xtb = {key: float(value["xtb_gap_ev"]) for key, value in roster.items()
           if value["xtb_gap_ev"] is not None}

    def subset(d1: Mapping[str, float], d2: Mapping[str, float]) -> tuple[list[float], list[float], list[str]]:
        keys = sorted(set(d1) & set(d2))
        return [d1[k] for k in keys], [d2[k] for k in keys], keys

    pairs: list[dict[str, object]] = []
    for name, a, b in (("xtb_qm9", xtb, qm9), ("xtb_batt", xtb, batt), ("qm9_batt", qm9, batt)):
        x, y, keys = subset(a, b)
        stats_block = _pair(x, y)
        pairs.append({"pair": name, "subset": "available", "level_a": name.split("_")[0],
                      "level_b": name.split("_")[1], "comparability": "cross_level",
                      "keys": keys, **stats_block})
    triple_keys = sorted(set(xtb) & set(qm9) & set(batt))
    for name, a, b in (("xtb_qm9", xtb, qm9), ("xtb_batt", xtb, batt), ("qm9_batt", qm9, batt)):
        x = [a[k] for k in triple_keys]; y = [b[k] for k in triple_keys]
        stats_block = _pair(x, y)
        pairs.append({"pair": name, "subset": "triple", "level_a": name.split("_")[0],
                      "level_b": name.split("_")[1], "comparability": "cross_level",
                      "keys": triple_keys, **stats_block})

    # calibration: xTB = slope * QM9 + intercept (the W39/W40 orientation)
    xk = sorted(set(xtb) & set(qm9))
    calib = _pair([qm9[k] for k in xk], [xtb[k] for k in xk])
    return {
        "roster": roster, "xtb": xtb, "qm9": qm9, "batt": batt,
        "pairs": pairs, "triple_keys": triple_keys, "calibration_xtb_on_qm9": calib,
    }


def level_registry(payload: Mapping[str, object]) -> list[dict[str, object]]:
    coverage = {"batt_wb97xv_smd": len(payload["batt"]),
                "themol_gfn2_gas": len(payload["xtb"]),
                "qm9_b3lyp_gas": len(payload["qm9"])}
    rows = []
    for level_id, source, level, phase, license_, role, provenance in LEVELS:
        rows.append({"level_id": level_id, "source": source, "level_of_theory": level,
                     "phase": phase, "license": license_, "role": role,
                     "provenance": provenance,
                     "coverage_on_241": str(coverage[level_id]) + "/241"})
    return rows


def pair_rows(payload: Mapping[str, object]) -> list[dict[str, object]]:
    rows = []
    for item in payload["pairs"]:
        rows.append({
            "pair": item["pair"], "subset": item["subset"], "level_a": item["level_a"],
            "level_b": item["level_b"], "n": item["n"], "spearman": item["spearman"],
            "kendall": item["kendall"], "pearson": item["pearson"],
            "slope_a_on_b": item["slope"], "intercept_a_on_b": item["intercept"],
            "r2": item["r2"], "comparability": item["comparability"],
        })
    return rows


def _verdict(ok: bool) -> str:
    return "成立" if ok else "判否"


def evaluate(payload: Mapping[str, object], prereg: Mapping[str, object]) -> list[dict[str, object]]:
    lane = prereg["lanes"]["w41_orbital_level_declaration"]
    cov = lane["expected_coverage"]
    expected = lane["expected_pairs"]
    by_key = {(item["pair"], item["subset"]): item for item in payload["pairs"]}
    tol = 1e-9
    criteria: list[dict[str, object]] = []
    criteria.append({
        "id": "H41d1",
        "description": "名册分母 241 行 ⊆ 每条轨道层都按同一名册取数",
        "value": float(len(payload["roster"])),
        "threshold": float(cov["roster"]),
        "verdict": _verdict(len(payload["roster"]) == int(cov["roster"])),
    })
    criteria.append({
        "id": "H41d2",
        "description": "xTB 覆盖 237/241（名册里 4 行 gap 缺失，不插补）",
        "value": float(len(payload["xtb"])),
        "threshold": float(cov["xtb_hits"]),
        "verdict": _verdict(len(payload["xtb"]) == int(cov["xtb_hits"])),
    })
    criteria.append({
        "id": "H41d3",
        "description": "QM9 命中 103/241（对齐 W39/W40）",
        "value": float(len(payload["qm9"])),
        "threshold": float(cov["qm9_hits"]),
        "verdict": _verdict(len(payload["qm9"]) == int(cov["qm9_hits"])),
    })
    criteria.append({
        "id": "H41d4",
        "description": "Batt-P30K 按 InChIKey 复算名册命中 73/241（对齐 W38-D）",
        "value": float(len(payload["batt"])),
        "threshold": float(cov["batt_hits"]),
        "verdict": _verdict(len(payload["batt"]) == int(cov["batt_hits"])),
    })
    criteria.append({
        "id": "H41d5",
        "description": "三方交集（triple）n = 48",
        "value": float(len(payload["triple_keys"])),
        "threshold": float(cov["triple_hits"]),
        "verdict": _verdict(len(payload["triple_keys"]) == int(cov["triple_hits"])),
    })
    p = by_key[("xtb_qm9", "available")]
    criteria.append({
        "id": "H41d6",
        "description": "xTB-QM9 全域 Spearman 复现 W40 锚 0.8856281475401158",
        "value": float(p["spearman"]),
        "threshold": float(expected["xtb_qm9_n103_spearman"]),
        "verdict": _verdict(abs(float(p["spearman"]) - float(expected["xtb_qm9_n103_spearman"])) < tol),
    })
    pb = by_key[("qm9_batt", "available")]
    criteria.append({
        "id": "H41d7",
        "description": "QM9-Batt Spearman 复现 0.8176735614281957（两方都算好的排序代理）",
        "value": float(pb["spearman"]),
        "threshold": float(expected["qm9_batt_n48_spearman"]),
        "verdict": _verdict(abs(float(pb["spearman"]) - float(expected["qm9_batt_n48_spearman"])) < tol),
    })
    tb = by_key[("xtb_batt", "triple")]
    tq = by_key[("xtb_qm9", "triple")]
    tg = by_key[("qm9_batt", "triple")]
    gap = min(float(tq["spearman"]), float(tg["spearman"])) - float(tb["spearman"])
    criteria.append({
        "id": "H41d8",
        "description": "『跨层排序先验可传递、可当作另一层的代理』被判否（在册）：同一 48 化合物上 "
                       "min(ρ_xTB-QM9, ρ_QM9-Batt) − ρ_xTB-Batt 超过 0.2",
        "value": float(gap),
        "threshold": float(lane["nontransitivity_gap_gate"]),
        "verdict": _verdict(gap <= float(lane["nontransitivity_gap_gate"])),
    })
    criteria.append({
        "id": "H41d9",
        "description": "三层两两都标 cross_level，同层级外部源数 = 0（登记要求未满足）",
        "value": float(sum(1 for item in payload["pairs"] if item["comparability"] == "same_level")),
        "threshold": 0.0,
        "verdict": _verdict(not any(item["comparability"] == "same_level" for item in payload["pairs"])),
    })
    calib = payload["calibration_xtb_on_qm9"]
    anchor = lane["calibration_anchor_xtb_on_qm9"]
    criteria.append({
        "id": "H41d10",
        "description": "标定式 xTB = slope·QM9 + intercept 复现 W39/W40 冻结值（slope 2.0266971543817958 / intercept -8.8728945529514）",
        "value": float(calib["slope"]),
        "threshold": float(anchor["slope"]),
        "verdict": _verdict(abs(float(calib["slope"]) - float(anchor["slope"])) < tol
                            and abs(float(calib["intercept"]) - float(anchor["intercept"])) < tol),
    })
    criteria.append({
        "id": "H41d11",
        "description": "三个输入件（名册 / QM9 命中 / Batt h5）sha256 前后一致",
        "value": 1.0,
        "threshold": 1.0,
        "verdict": "成立",
    })
    return criteria


def make_figure(payload: Mapping[str, object]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for candidate in ("Microsoft YaHei", "SimHei", "DengXian", "Arial Unicode MS"):
        try:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False

    by_key = {(item["pair"], item["subset"]): item for item in payload["pairs"]}
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.3))
    labels = ["xTB-QM9", "xTB-Batt", "QM9-Batt"]
    keys = [("xtb_qm9", "available"), ("xtb_batt", "available"), ("qm9_batt", "available")]
    values = [float(by_key[k]["spearman"]) for k in keys]
    counts = [int(by_key[k]["n"]) for k in keys]
    axes[0].bar(labels, values, color="#1f77b4")
    for i, (value, count) in enumerate(zip(values, counts)):
        axes[0].text(i, value, " ρ=" + format(value, ".3f") + "\n n=" + str(count),
                     ha="center", va="bottom", fontsize=8)
    axes[0].set_ylim(0, 1.0)
    axes[0].set_ylabel("Spearman ρ（gap）")
    axes[0].set_title("W41-D 两两排序迁移（全域）", fontsize=10)
    axes[0].grid(alpha=0.25, axis="y")

    tq = float(by_key[("xtb_qm9", "triple")]["spearman"])
    tb = float(by_key[("xtb_batt", "triple")]["spearman"])
    tg = float(by_key[("qm9_batt", "triple")]["spearman"])
    axes[1].bar(labels, [tq, tb, tg], color="#8c564b")
    for i, value in enumerate([tq, tb, tg]):
        axes[1].text(i, value, " " + format(value, ".3f"), ha="center", va="bottom", fontsize=9)
    axes[1].set_ylim(0, 1.0)
    axes[1].set_ylabel("Spearman ρ（gap）")
    axes[1].set_title("同一 48 化合物：min(0.860,0.818) − 0.538 = " + format(min(tq, tg) - tb, ".3f"),
                      fontsize=9)
    axes[1].grid(alpha=0.25, axis="y")
    fig.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH)
    plt.close(fig)


def render_report(payload: Mapping[str, object], criteria: Sequence[Mapping[str, object]],
                  prereg: Mapping[str, object]) -> str:
    by_key = {(item["pair"], item["subset"]): item for item in payload["pairs"]}
    tq = by_key[("xtb_qm9", "triple")]
    tb = by_key[("xtb_batt", "triple")]
    tg = by_key[("qm9_batt", "triple")]
    gap = min(float(tq["spearman"]), float(tg["spearman"])) - float(tb["spearman"])
    lines = [
        "# W41-D 轨道通道层级声明（GFN2-xTB / B3LYP 气相 / ωB97X-V+SMD）",
        "",
        "**性质**：后验 / 治理件 + 只读复算，**0 shot（累计仍 19）**。外部层数值不入标签池或特征列。",
        "",
        "## 1. 层级登记",
        "",
        "| level | 来源 | 层级 | 相 | 许可 | 角色 | 覆盖 |",
        "| --- | --- | --- | --- | --- | --- | ---: |",
    ]
    for row in level_registry(payload):
        lines.append("| " + str(row["level_id"]) + " | " + str(row["source"]) + " | "
                     + str(row["level_of_theory"]) + " | " + str(row["phase"]) + " | "
                     + str(row["license"]) + " | " + str(row["role"]) + " | "
                     + str(row["coverage_on_241"]) + " |")
    lines += [
        "",
        "## 2. 两两排序迁移",
        "",
        "| pair | 子集 | n | Spearman | Kendall | Pearson | 可比性 |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in pair_rows(payload):
        lines.append("| " + str(row["pair"]) + " | " + str(row["subset"]) + " | "
                     + str(row["n"]) + " | " + format(float(row["spearman"]), ".6f") + " | "
                     + format(float(row["kendall"]), ".6f") + " | "
                     + format(float(row["pearson"]), ".6f") + " | " + str(row["comparability"]) + " |")
    lines += [
        "",
        "**不可传递**：在**同一个 48 化合物**子集上，ρ(xTB, QM9) = "
        + format(float(tq["spearman"]), ".4f") + "、ρ(QM9, Batt) = "
        + format(float(tg["spearman"]), ".4f") + "，但 ρ(xTB, Batt) 只有 "
        + format(float(tb["spearman"]), ".4f") + "（gap = " + format(gap, ".4f") + " > 0.2）。"
        "两条「与 Batt 一致」的链条不能推出第三条。",
        "",
        "**量级侧**：xTB-Batt 的 Pearson 只有 " + format(float(tb["pearson"]), ".4f")
        + "、线性斜率 " + format(float(tb["slope"]), ".4f")
        + " —— 即便序侧也只有中等一致，量级侧几乎无线性信息。",
        "",
        "## 3. 适用域声明",
        "",
        "> " + str(prereg["lanes"]["w41_orbital_level_declaration"]["ad_statement"]),
        "",
        "- 三层两两都是 `cross_level`（泛函 / 基组 / 溶剂化至少差一项），**同层级外部源数 = 0**。",
        "- 因此 W40 登记的第 3 条（「加权重前先补同层级外部源」）在本轮**仍未满足**：QM9 只能作排序先验。",
        "- 标定式 `xTB = 2.0266971543817958·QM9 − 8.8728945529514` 复现 W39/W40 冻结值，"
        "只在 103 个命中化合物上成立。",
        "",
        "## 4. 判据",
        "",
        "| 判据 | 说明 | 读数 | 门槛 | 判定 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for item in criteria:
        value = item["value"]
        text = format(float(value), ".6g") if isinstance(value, (int, float)) else str(value)
        threshold = item["threshold"]
        ttext = format(float(threshold), ".6g") if isinstance(threshold, (int, float)) else str(threshold)
        lines.append("| " + str(item["id"]) + " | " + str(item["description"]) + " | "
                     + text + " | " + ttext + " | " + str(item["verdict"]) + " |")
    lines += [
        "",
        "## 5. 边界",
        "",
        "- 只谈**排序与标定**，不把任何跨层数值写进标签池或特征列。",
        "- QM9 的 B3LYP 层与 Batt 的 ωB97X-V/SMD 层**不可互换**；名册里 xTB 有 4 行 gap 缺失，照实登记不插补。",
        "- H41d8 是「排序迁移不可传递」的**在册判否**：它不是缺陷，而是对「用单一跨层先验给通道加权」的否证。",
        "- 0 shot；四个冻结读数一个不动。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-figure", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    prereg = load_prereg()
    sources = [ROSTER_CSV, QM9_OVERLAP, BATT_H5]
    before = {str(path): sha256_file(path) for path in sources}
    payload = build(prereg)
    after = {str(path): sha256_file(path) for path in sources}
    inputs_unchanged = before == after
    criteria = evaluate(payload, prereg)
    criteria[-1]["value"] = 1.0 if inputs_unchanged else 0.0
    criteria[-1]["verdict"] = _verdict(inputs_unchanged)
    failed = [item for item in criteria if item["verdict"] != "成立"]
    unregistered = [item for item in failed if str(item["id"]) not in REGISTERED_NEGATIVES]

    write_csv_lf(REGISTRY_CSV, REGISTRY_FIELDS, level_registry(payload))
    write_csv_lf(PAIRS_CSV, PAIR_FIELDS, pair_rows(payload))
    write_csv_lf(HITS_CSV, HITS_FIELDS,
                 [{"inchikey": key, "batt_gap_ev": payload["batt"][key]}
                  for key in sorted(payload["batt"])])
    if not args.skip_figure:
        make_figure(payload)

    by_key = {(item["pair"], item["subset"]): item for item in payload["pairs"]}
    declaration = {
        "schema": "w41_orbital_level_declaration/declaration@1",
        "task": TASK,
        "statement": prereg["lanes"]["w41_orbital_level_declaration"]["ad_statement"],
        "levels": level_registry(payload),
        "comparability": {row["pair"] + "/" + row["subset"]: row["comparability"]
                          for row in pair_rows(payload)},
        "n_same_level_pairs": sum(1 for row in pair_rows(payload)
                                  if row["comparability"] == "same_level"),
        "non_transitivity_gap_spearman": float(
            min(float(by_key[("xtb_qm9", "triple")]["spearman"]),
                float(by_key[("qm9_batt", "triple")]["spearman"]))
            - float(by_key[("xtb_batt", "triple")]["spearman"])),
        "same_level_external_source_present": False,
        "calibration_xtb_on_qm9": payload["calibration_xtb_on_qm9"],
        "not_used_as": "外部层数值不入标签池、不入特征列；跨层只声明排序可比、量级不可互换。",
    }
    write_json_stable(DECLARATION_PATH, declaration)

    summary = {
        "schema": SCHEMA,
        "task": TASK,
        "generated_at_utc": _utc_now(),
        "elapsed_seconds": float(time.perf_counter() - started),
        "ledger": {
            "main_scoreboard_shots_this_week": 0,
            "cumulative_main_scoreboard_attempts_after": 19,
            "why_not_a_shot": "只读名册与两件外部层做层级声明与只读复算；不拟合主记分牌臂、不新增特征列、不改 METRIC_NAMES、不动冻结读数。",
        },
        "inputs": before,
        "inputs_unchanged": inputs_unchanged,
        "frozen_readings_untouched": [FROZEN_BASELINE, FROZEN_HEADLINE,
                                      FROZEN_SINGLE_REPRESENTATION, FROZEN_PROMOTED_ARM],
        "coverage": {"roster": len(payload["roster"]), "xtb": len(payload["xtb"]),
                     "qm9": len(payload["qm9"]), "batt": len(payload["batt"]),
                     "triple": len(payload["triple_keys"])},
        "pairs": pair_rows(payload),
        "levels": level_registry(payload),
        "calibration_xtb_on_qm9": payload["calibration_xtb_on_qm9"],
        "declaration": declaration,
        "criteria": criteria,
        "registered_negatives": list(REGISTERED_NEGATIVES),
        "headline": [
            "三层覆盖：xTB " + str(len(payload["xtb"])) + "/241、QM9 " + str(len(payload["qm9"]))
            + "/241、Batt " + str(len(payload["batt"])) + "/241；三方交集 "
            + str(len(payload["triple_keys"])) + "。",
            "两两排序迁移不可传递：同一 48 化合物上 ρ(xTB,QM9)="
            + format(float(by_key[("xtb_qm9", "triple")]["spearman"]), ".4f") + "、ρ(QM9,Batt)="
            + format(float(by_key[("qm9_batt", "triple")]["spearman"]), ".4f") + "，但 ρ(xTB,Batt)="
            + format(float(by_key[("xtb_batt", "triple")]["spearman"]), ".4f") + "。",
            "三层两两都是 cross_level，同层级外部源数 = 0 ⇒ W40 登记的第 3 条仍未满足。",
            "0 shot（累计仍 19）。",
        ],
    }
    write_json_stable(SUMMARY_PATH, summary)
    REPORT_PATH.write_text(render_report(payload, criteria, prereg), encoding="utf-8", newline="\n")

    print("coverage roster %d xtb %d qm9 %d batt %d triple %d"
          % (len(payload["roster"]), len(payload["xtb"]), len(payload["qm9"]),
             len(payload["batt"]), len(payload["triple_keys"])))
    for row in pair_rows(payload):
        print("pair %-9s %-10s n=%-4d rho=%.6f pearson=%.6f"
              % (row["pair"], row["subset"], row["n"], row["spearman"], row["pearson"]))
    print("verdicts " + str(len(criteria) - len(failed)) + "/" + str(len(criteria)))
    for item in failed:
        print(("REGISTERED-NEGATIVE " if str(item["id"]) in REGISTERED_NEGATIVES
               else "UNREGISTERED-FAIL ") + str(item["id"]) + " " + str(item["description"]))
    return 1 if unregistered else 0


if __name__ == "__main__":
    raise SystemExit(main())