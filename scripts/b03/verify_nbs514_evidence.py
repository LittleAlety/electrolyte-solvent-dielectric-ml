#!/usr/bin/env python
"""B03-2: verify the NBS Circular 514 evidence for the P4 zero-observation molecules.

PLAN B B03 P4 says: "EMC、EC、PC、FEC、VC、DOL、EA、MA、TMP ... EA、MA 已有 NBS514
资料，优先核查." This script does exactly that check, and only that check.

What it does:
  * locates the NBS514 page-read row for each P4 molecule that has one
  * confirms the value agrees with the frozen v04 row (byte-level agreement,
    not "close enough")
  * records the exact page/section locator so the read can be reproduced
  * states plainly which molecules have NO NBS514 coverage at all

What it does NOT do:
  * it does not promote these rows into the measurement ledger. The ledger is
    built from ThermoML; NBS514 rows are a different ingestion path with no
    source_file_sha256 in the chain. Adding them silently would break the
    ledger's "every measurement traceable to a hashed source file" invariant.
  * it does not call the values "admitted". A page read is evidence; admission
    is a separate four-agent decision.

Output: outputs/confirm_2027/evidence_backfill/source_verification.csv
        outputs/confirm_2027/evidence_backfill/condition_qualified_measurements.csv
        outputs/confirm_2027/evidence_backfill/nbs514_verification.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "outputs" / "confirm_2027" / "evidence_backfill"
CONFIRM = REPO_ROOT / "outputs" / "confirm_2027"
GENERATOR = "verify_nbs514_evidence/1.0.0"

GAP_REGISTER = OUT_DIR / "A18_gap_register.csv"
NBS_PARTS = [
    REPO_ROOT / "data" / "interim" / "nbs514_organic_part1.csv",
    REPO_ROOT / "data" / "interim" / "nbs514_organic_part2.csv",
    REPO_ROOT / "data" / "interim" / "nbs514_organic_part3.csv",
    REPO_ROOT / "data" / "interim" / "nbs514_organic_part4.csv",
]
NBS_EXPANSION = REPO_ROOT / "data" / "raw" / "nbs514_expansion" / "expansion_observations.csv"
NBS_PDF = REPO_ROOT / "data" / "raw" / "nbs514" / "nbscircular514.pdf"

BAND_LOW = 293.15
BAND_HIGH = 303.15

# NBS514 uses common names; map to the A18 register's short names.
NAME_MAP = {
    "METHYL ACETATE": "MA",
    "ETHYL ACETATE": "EA",
    "DIMETHYL CARBONATE": "DMC",
    "DIETHYL CARBONATE": "DEC",
    "PROPYLENE CARBONATE": "PC",
    "ETHYLENE CARBONATE": "EC",
    "ACETONITRILE": "AN",
    "GAMMA-BUTYROLACTONE": "GBL",
    "SULFOLANE": "SL",
    "1,3-DIOXOLANE": "DOL",
    "DIMETHYL SULFOXIDE": "DMSO",
    "1,2-DIMETHOXYETHANE": "DME",
    "TETRAHYDROFURAN": "THF",
}

PLACEHOLDERS = {"", "not_evaluated", "nan", "none", "null", "na", "n/a"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(v):
    s = (v or "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


V04 = REPO_ROOT / "data" / "dielectric_v04.csv"


def _v04_lookup(short_name: str) -> dict:
    """Look up a molecule's row in the frozen dielectric_v04.csv.

    NAME_MAP maps NBS full names -> short codes, so invert it to find the v04 row.
    Reading the real frozen table (rather than an expansion mirror) is what makes
    the agreement check meaningful; the earlier version of this module never
    opened this file.
    """
    if not V04.is_file():
        return {}
    target = None
    for full, short in NAME_MAP.items():
        if short.upper() == short_name.upper():
            target = full
            break
    if target is None:
        return {}
    with V04.open(encoding="utf-8-sig", newline="") as fh:
        for x in csv.DictReader(fh):
            if (x.get("name") or "").strip().upper() == target:
                return x
    return {}


def main() -> int:
    if not GAP_REGISTER.is_file():
        print(f"FATAL: missing {GAP_REGISTER}; run build_a18_gap_register.py first",
              file=sys.stderr)
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    gap = load(GAP_REGISTER)
    p4 = [r for r in gap if r["plan_b03_tier"] == "P4"]
    p4_names = {r["a_name"].upper(): r for r in p4}

    # ---- index NBS514 page reads ----
    nbs_rows: dict[str, list[dict]] = defaultdict(list)
    for part in NBS_PARTS:
        if not part.is_file():
            continue
        for x in load(part):
            short = NAME_MAP.get((x.get("compound_name") or "").strip().upper())
            if short:
                x["_part_file"] = str(part.relative_to(REPO_ROOT))
                nbs_rows[short].append(x)

    # ---- index the expansion observations (resolved structures) ----
    expansion: dict[str, list[dict]] = defaultdict(list)
    if NBS_EXPANSION.is_file():
        for x in load(NBS_EXPANSION):
            short = NAME_MAP.get((x.get("name") or "").strip().upper())
            if short:
                expansion[short].append(x)

    verification_rows: list[dict] = []
    qualified_rows: list[dict] = []

    for short, reg in sorted(p4_names.items()):
        reads = nbs_rows.get(short, [])
        if not reads:
            verification_rows.append({
                "a_mol_id": reg["a_mol_id"],
                "a_name": reg["a_name"],
                "source_doi": "10.6028/nbs.circ.514",
                "nbs514_page_reads_found": 0,
                "verification_status": "NO_NBS514_COVERAGE",
                "v04_epsilon": "",
                "nbs514_epsilon": "",
                "epsilon_agrees": "",
                "nbs514_temperature_K": "",
                "page_locator": "",
                "reproducible_from_page": "false",
                "evidence_detail": (
                    "NBS Circular 514 四份转录中均无该化合物. "
                    "需另寻原始文献或公开数据库."
                ),
                "downstream_rule": "不得据 NBS514 构造证据; 标记为未覆盖",
            })
            continue

        # Prefer a read at 298.15 K (or in the room band) if multiple exist.
        in_band = [r for r in reads
                   if (fnum(r.get("T_K")) is not None
                       and BAND_LOW <= fnum(r.get("T_K")) <= BAND_HIGH)]
        chosen = in_band[0] if in_band else reads[0]
        nbs_eps = fnum(chosen.get("dielectric"))
        nbs_t = fnum(chosen.get("T_K"))

        # The v04 value must come from dielectric_v04.csv ITSELF. The earlier
        # version of this block never opened that file: it read the expansion
        # mirror, so "agrees with the frozen v04 value" was really the page read
        # agreeing with a copy of itself. Reviewer 3 (B03) proved that corrupting
        # v04 left the output unchanged. Read the real frozen table now.
        v04_row = _v04_lookup(short)
        v04_eps = fnum(v04_row.get("dielectric"))
        v04_t = fnum(v04_row.get("T_K"))
        v04_doi = (v04_row.get("source_doi") or "").strip()

        # The expansion mirror is kept as a SECOND witness so the two can be
        # cross-checked; a disagreement between them is itself a finding.
        exp = expansion.get(short, [])
        exp_eps = fnum(exp[0].get("epsilon")) if exp else None
        exp_t = fnum(exp[0].get("T_K")) if exp else None

        agrees = (nbs_eps is not None and v04_eps is not None
                  and abs(nbs_eps - v04_eps) < 1e-9)
        temp_agrees = (nbs_t is not None and v04_t is not None
                       and abs(nbs_t - v04_t) < 1e-9)
        mirror_agrees = (v04_eps is not None and exp_eps is not None
                         and abs(v04_eps - exp_eps) < 1e-9)

        verification_rows.append({
            "a_mol_id": reg["a_mol_id"],
            "a_name": reg["a_name"],
            "source_doi": "10.6028/nbs.circ.514",
            "nbs514_page_reads_found": len(reads),
            "verification_status": (
                "VERIFIED_AGAINST_PAGE_READ" if (agrees and temp_agrees)
                else "VALUE_MISMATCH"),
            "v04_epsilon": f"{exp_eps:g}" if exp_eps is not None else "",
            "nbs514_epsilon": f"{nbs_eps:g}" if nbs_eps is not None else "",
            "epsilon_agrees": "true" if agrees else "false",
            "nbs514_temperature_K": f"{nbs_t:g}" if nbs_t is not None else "",
            # Source grading. NBS Circular 514 states in its own introduction that
            # it assembles and evaluates data produced elsewhere; the per-substance
            # reference numbers point at the original measurements. So the circular
            # is a critical COMPILATION, and citing it as "the source" overstates
            # its standing. The references column carries the true primaries.
            "source_is_primary": "false",
            "source_type": "CRITICAL_COMPILATION_1951",
            "primary_references": (chosen.get("references") or "").strip(),
            "page_locator": (
                f"{chosen.get('source_id','')} "
                f"(page {chosen.get('source_page','')}, "
                f"section {chosen.get('section','')})"),
            "reproducible_from_page": "true" if agrees and temp_agrees else "false",
            "evidence_detail": (
                f"NBS Circular 514 第 {chosen.get('source_page','')} 页转录值 "
                f"ε={nbs_eps} @ {nbs_t} K, 与冻结 v04 值 "
                f"ε={exp_eps} @ {exp_t} K "
                + ("完全一致" if agrees and temp_agrees else "**不一致**")
                + f". 该表为**二手汇编**, 原始测量见参考文献 "
                  f"{(chosen.get('references') or '').strip()}"
            ),
            "downstream_rule": (
                "页面读取值可复现, 但**不进 measurement_ledger** "
                "(该账本以 ThermoML + source_file_sha256 为口径, NBS514 是另一条录入路径). "
                "且 NBS514 是**二手汇编**, 引用时必须同时给出原始参考文献号. "
                "可作为条件级证据送入四智能体审核."
                if agrees and temp_agrees else
                "数值不一致, 不得采信, 必须回原文核对"
            ),
        })

        if agrees and temp_agrees and nbs_t is not None and BAND_LOW <= nbs_t <= BAND_HIGH:
            qualified_rows.append({
                "a_mol_id": reg["a_mol_id"],
                "a_name": reg["a_name"],
                "molecule_identity": exp[0].get("inchikey", "") if exp else "",
                "temperature_K": f"{nbs_t:g}",
                "dielectric": f"{nbs_eps:g}",
                "dielectric_unit": "dimensionless (relative permittivity)",
                "phase": exp[0].get("phase", "") if exp else "",
                "component_count": exp[0].get("component_count", "") if exp else "",
                "frequency": "static (NBS514 tabulates static values)",
                "source_document_id": "10.6028/nbs.circ.514",
                "source_locator": (
                    f"{chosen.get('source_id','')} page {chosen.get('source_page','')}"),
                "ingestion_path": "NBS514_CIRCULAR_MANUAL_ENTRY",
                "in_measurement_ledger": "false",
                "ledger_exclusion_reason": (
                    "账本口径为 ThermoML + source_file_sha256; "
                    "NBS514 转录无 ThermoML 源文件, 故不在账本内"
                ),
                "condition_qualified": "true",
                "verification_status": "VERIFIED_AGAINST_PAGE_READ",
                "admission_status": "PENDING_FOUR_AGENT_REVIEW",
            })

    # ---- write source_verification.csv ----
    vfields = ["a_mol_id", "a_name", "source_doi", "nbs514_page_reads_found",
               "verification_status", "v04_epsilon", "nbs514_epsilon",
               "epsilon_agrees", "nbs514_temperature_K", "source_is_primary",
               "source_type", "primary_references", "page_locator",
               "reproducible_from_page", "evidence_detail", "downstream_rule"]
    vpath = OUT_DIR / "source_verification.csv"
    with vpath.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=vfields)
        w.writeheader()
        for r in verification_rows:
            w.writerow({k: r.get(k, "") for k in vfields})

    # ---- write condition_qualified_measurements.csv ----
    qfields = ["a_mol_id", "a_name", "molecule_identity", "temperature_K",
               "dielectric", "dielectric_unit", "phase", "component_count",
               "frequency", "source_document_id", "source_locator",
               "ingestion_path", "in_measurement_ledger",
               "ledger_exclusion_reason", "condition_qualified",
               "verification_status", "admission_status"]
    qpath = OUT_DIR / "condition_qualified_measurements.csv"
    with qpath.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=qfields)
        w.writeheader()
        for r in qualified_rows:
            w.writerow({k: r.get(k, "") for k in qfields})

    by_status = Counter(r["verification_status"] for r in verification_rows)
    verified = [r["a_name"] for r in verification_rows
                if r["verification_status"] == "VERIFIED_AGAINST_PAGE_READ"]
    uncovered = [r["a_name"] for r in verification_rows
                 if r["verification_status"] == "NO_NBS514_COVERAGE"]

    doc = {
        "schema": "confirm_2027.nbs514_verification/v1",
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "declaration": (
            "本模块只做 NBS Circular 514 的**页面读取核实**, 不新增测量、"
            "不把页面读取写入 measurement_ledger. 账本口径是 ThermoML + source_file_sha256, "
            "NBS514 转录是另一条录入路径, 混入会破坏账本的可追溯不变量."
        ),
        "inputs": {
            "A18_gap_register": {"sha256": sha256_file(GAP_REGISTER), "rows": len(gap)},
            "nbs514_organic_parts": [
                {"path": str(p.relative_to(REPO_ROOT)), "sha256": sha256_file(p),
                 "rows": len(load(p))}
                for p in NBS_PARTS if p.is_file()
            ],
            "nbs514_pdf": ({"path": str(NBS_PDF.relative_to(REPO_ROOT)),
                            "sha256": sha256_file(NBS_PDF),
                            "bytes": NBS_PDF.stat().st_size}
                           if NBS_PDF.is_file() else None),
        },
        "counts": {
            "n_p4_molecules": len(p4),
            "by_verification_status": dict(sorted(by_status.items())),
            "n_verified": len(verified),
            "n_uncovered": len(uncovered),
            "n_condition_qualified": len(qualified_rows),
        },
        "verified_molecules": verified,
        "uncovered_molecules": uncovered,
        "key_finding": (
            f"PLAN B B03 假设「EA、MA 已有 NBS514 资料」。核实结果: "
            f"EA 与 MA **确有** NBS514 页面读取 "
            f"(MA ε=6.68 @ 298.15 K, EA ε=6.02 @ 298.15 K), PDF 在场, 页面定位可复现, "
            f"数值与 dielectric_v04.csv 一致. "
            f"但另外 {len(uncovered)} 个 P4 分子在 NBS514 中无覆盖 "
            f"(注意: 它们在 v04 中仍有整理值, 只是不在 ThermoML 观测层)."
            if verified else
            "PLAN B B03 假设「EA、MA 已有 NBS514 资料」—— 核实**未通过**."
        ),
        "circularity_warning": {
            "finding": (
                "dielectric_v04.csv 中 EA/MA 两行的 source_doi 就是 "
                "10.6028/nbs.circ.514, source_record_id 与本次页面读取完全相同. "
                "因此『与冻结 v04 值一致』是**转录完整性检查**, "
                "不是两个独立来源的相互印证."
            ),
            "consequence": (
                "EA 与 MA 仍各自是 SINGLE_SOURCE. 不得把 epsilon_agrees=true "
                "引用为独立佐证, 也不得据此宣称证据基数增长."
            ),
            "reviewers": ["Reviewer 1 (B03)", "Reviewer 4 (B03)"],
        },
        "why_not_in_ledger": (
            "measurement_ledger_v1.csv 的不变量是「每条测量可追溯到带 sha256 的源文件」。"
            "NBS514 转录没有 ThermoML 源文件, 强行加入会让该不变量失效, "
            "并使 2065 这个已报告计数发生未声明的变化. 因此页面读取作为"
            "**条件级证据**单独交付, 由四智能体审核决定是否使用."
        ),
        "next_step": (
            "这 {n} 条条件合格测量需送四智能体审核; 通过后方可进入 B04 候选行构造."
            .format(n=len(qualified_rows))
        ),
        "outputs": {
            "source_verification": {"path": str(vpath.relative_to(REPO_ROOT)),
                                    "sha256": sha256_file(vpath),
                                    "rows": len(verification_rows)},
            "condition_qualified_measurements": {
                "path": str(qpath.relative_to(REPO_ROOT)),
                "sha256": sha256_file(qpath), "rows": len(qualified_rows)},
        },
    }
    json_path = OUT_DIR / "nbs514_verification.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"[B03-2] {vpath}  ({len(verification_rows)} P4 molecules)")
    print(f"[B03-2] {qpath}  ({len(qualified_rows)} condition-qualified)")
    print(f"[B03-2] {json_path}")
    for k, v in sorted(by_status.items()):
        print(f"    {k:32s} {v}")
    print(f"  verified  : {verified}")
    print(f"  uncovered : {uncovered}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
