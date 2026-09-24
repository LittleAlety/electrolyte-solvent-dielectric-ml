"""Export the Week 7 data-expansion, G1+ closure and veto artefacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.export_results_common import (
    DEFAULT_OUTPUT_ROOT,
    copy_artifacts,
    read_json,
    run_verifiers,
    write_json,
    write_sha256s,
)

WEEK = "week7"

README_TEXT = """# Week 7 交付包

数据血缘: v0.3.12（规范数据集 dielectric_v03.csv，246 行 x 38 列）
生成脚本: probes/export_week7_results.py

## 入口
- week7_report.md - Week 7 主报告（数据扩展、G1+ 与冻结）
- week7_summary.json - 机器可读摘要、版本注记与 open items
- dielectric_v03.csv - 规范数据集（sha256 1b285fe8...22456）
- verification.json - 四个 verifier 的退出码与报告
- SHA256SUMS - 本目录全部文件的清单

## 关键内容
- 数据: dielectric_v031.csv, dielectric_v032.csv, dielectric_v03.csv,
  dielectric_v03_exclusions.csv, dielectric_v03_provenance_patches.csv,
  dielectric_physical_features_v03.csv
- G1+: g1plus_*_findings.md, g1plus_*_evidence.json
- 适用域: applicability_domain_summary.json, g2_domain_gap_summary.json,
  g2_domain_gap_parity.png
- 手册闸门: manual_appendix_reconciliation.md/.json

## 校验
从仓库根目录运行（scripts/ 不在交付包内）:
python scripts/verify_export_manifests.py --output-dir <本目录>
python scripts/verify_dielectric_v03.py
python scripts/verify_v032_benchmarks.py

## 仍未闭环（不要误读为已解决）
- FEC 107 腿: Ue et al. 2014 Table 2.3 / Hagiyama 2008 受限，尚未读到。
- MOPN: 缺独立一手确认与 GFN2-xTB 特征行。
- Tier 4 印刷/订阅来源: 访问受限，记录为 limitation，不是"查无此值"。
"""


def row_count(path: Path) -> int:
    lines = path.read_text(encoding="utf-8-sig").strip().splitlines()
    return max(len(lines) - 1, 0)


ARTIFACTS = (
    ("reports/week7_dataset_expansion_and_freeze.md", "week7_report.md"),
    ("reports/v032_veto_resolution.md", "v032_veto_resolution.md"),
    ("reports/v033_provenance_upgrade.md", "v033_provenance_upgrade.md"),
    ("reports/applicability_domain_veto_fix.md", "applicability_domain_veto_fix.md"),
    ("reports/g1_data_gate_review.md", "g1_data_gate_review.md"),
    ("reports/g1plus_tier0_findings.md", "g1plus_tier0_findings.md"),
    ("reports/g1plus_tier1_findings.md", "g1plus_tier1_findings.md"),
    ("reports/g1plus_tier2_findings.md", "g1plus_tier2_findings.md"),
    ("reports/g1plus_tier2_adversarial_check.md", "g1plus_tier2_adversarial_check.md"),
    ("reports/g1plus_tier3_mopn_findings.md", "g1plus_tier3_mopn_findings.md"),
    ("reports/g1plus_mopn_thesis_findings.md", "g1plus_mopn_thesis_findings.md"),
    (
        "reports/g1plus_perricone_thesis_crosscheck.md",
        "g1plus_perricone_thesis_crosscheck.md",
    ),
    ("reports/g1plus_citation_trace_findings.md", "g1plus_citation_trace_findings.md"),
    ("reports/g1plus_pubchem_findings.md", "g1plus_pubchem_findings.md"),
    (
        "reports/g1plus_nist_webbook_findings.md",
        "g1plus_nist_webbook_findings.md",
    ),
    (
        "reports/g1plus_materials_project_findings.md",
        "g1plus_materials_project_findings.md",
    ),
    ("reports/g1plus_tier34_access_findings.md", "g1plus_tier34_access_findings.md"),
    ("reports/g1plus_ecw308_crosscheck.md", "g1plus_ecw308_crosscheck.md"),
    (
        "reports/g1plus_perricone2011_thesis_and_gvl.md",
        "g1plus_perricone2011_thesis_and_gvl.md",
    ),
    ("probes/g1plus_ecw308_extract.py", "g1plus_ecw308_extract.py"),
    ("probes/g1plus_ecw308_evidence.json", "g1plus_ecw308_evidence.json"),
    ("probes/g1plus_ecw308_crosscheck.json", "g1plus_ecw308_crosscheck.json"),
    ("data/dielectric_v031.csv", "dielectric_v031.csv"),
    ("data/dielectric_v032.csv", "dielectric_v032.csv"),
    ("data/dielectric_v03.csv", "dielectric_v03.csv"),
    (
        "data/processed/dielectric_v03_exclusions.csv",
        "dielectric_v03_exclusions.csv",
    ),
    (
        "data/processed/dielectric_v03_provenance_patches.csv",
        "dielectric_v03_provenance_patches.csv",
    ),
    (
        "data/processed/dielectric_physical_features_v03.csv",
        "dielectric_physical_features_v03.csv",
    ),
    (
        "data/processed/dielectric_applicability_flags.csv",
        "dielectric_applicability_flags.csv",
    ),
    ("probes/dielectric_v031_summary.json", "dielectric_v031_summary.json"),
    ("probes/dielectric_v03_summary.json", "dielectric_v03_summary.json"),
    ("probes/applicability_domain_summary.json", "applicability_domain_summary.json"),
    ("probes/g2_domain_gap_summary.json", "g2_domain_gap_summary.json"),
    ("probes/g1plus_tier0_evidence.json", "g1plus_tier0_evidence.json"),
    ("probes/g1plus_tier1_evidence.json", "g1plus_tier1_evidence.json"),
    ("probes/g1plus_tier2_evidence.json", "g1plus_tier2_evidence.json"),
    (
        "probes/g1plus_tier2_adversarial_check.json",
        "g1plus_tier2_adversarial_check.json",
    ),
    ("probes/g1plus_tier3_mopn_evidence.json", "g1plus_tier3_mopn_evidence.json"),
    ("probes/g1plus_pubchem_probe.py", "g1plus_pubchem_probe.py"),
    ("probes/g1plus_pubchem_evidence.json", "g1plus_pubchem_evidence.json"),
    ("probes/g1plus_nist_webbook_probe.py", "g1plus_nist_webbook_probe.py"),
    (
        "probes/g1plus_nist_webbook_evidence.json",
        "g1plus_nist_webbook_evidence.json",
    ),
    ("probes/g1plus_materials_project_probe.py", "g1plus_materials_project_probe.py"),
    (
        "probes/g1plus_materials_project_evidence.json",
        "g1plus_materials_project_evidence.json",
    ),
    ("probes/g1plus_mopn_thesis_evidence.json", "g1plus_mopn_thesis_evidence.json"),
    (
        "probes/g1plus_perricone_thesis_crosscheck.json",
        "g1plus_perricone_thesis_crosscheck.json",
    ),
    (
        "probes/g1plus_citation_trace_evidence.json",
        "g1plus_citation_trace_evidence.json",
    ),
    ("probes/artifacts/domain_gap_parity.png", "g2_domain_gap_parity.png"),
    (
        "reports/manual_appendix_reconciliation.md",
        "manual_appendix_reconciliation.md",
    ),
    (
        "probes/manual_appendix_reconciliation.py",
        "manual_appendix_reconciliation.py",
    ),
    (
        "probes/manual_appendix_reconciliation.json",
        "manual_appendix_reconciliation.json",
    ),
    (
        "data/reference/dielectric_molecule_aliases.csv",
        "dielectric_molecule_aliases.csv",
    ),
    ("reports/nbs514_frequency_gate_audit.md", "nbs514_frequency_gate_audit.md"),
    (
        "probes/nbs514_frequency_gate_audit.py",
        "nbs514_frequency_gate_audit.py",
    ),
    (
        "probes/nbs514_frequency_gate_audit.json",
        "nbs514_frequency_gate_audit.json",
    ),
    (
        "reports/g1plus_crawl_round2_findings.md",
        "g1plus_crawl_round2_findings.md",
    ),
    (
        "probes/g1plus_crawl_round2_evidence.json",
        "g1plus_crawl_round2_evidence.json",
    ),
)
VERIFIERS = (
    "scripts/verify_dielectric_v02.py",
    "scripts/verify_dielectric_v032.py",
    "scripts/verify_dielectric_v03.py",
    "scripts/verify_v032_benchmarks.py",
)


def export_results(
    *,
    source_root: Path = REPOSITORY_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    overwrite: bool = False,
) -> dict[str, object]:
    week_root = output_root / WEEK
    if week_root.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing output: {week_root}")
    written = copy_artifacts(source_root, week_root, ARTIFACTS)

    verification = run_verifiers(source_root, VERIFIERS)
    write_json(week_root / "verification.json", verification)

    v03_summary = read_json(source_root / "probes" / "dielectric_v03_summary.json")
    applicability = read_json(source_root / "probes" / "applicability_domain_summary.json")
    g2 = read_json(source_root / "probes" / "g2_domain_gap_summary.json")
    exclusions = (
        (source_root / "data" / "processed" / "dielectric_v03_exclusions.csv")
        .read_text(encoding="utf-8-sig")
        .strip()
        .splitlines()
    )
    write_json(
        week_root / "week7_summary.json",
        {
            "dataset_version": "0.3.12",
            "dataset_version_note": (
                "the 246-row set was frozen at v0.3.3; v0.3.4 fixed the "
                "model_ready modelling gate; v0.3.5-v0.3.6 revised provenance; "
                "v0.3.7 added the ECW-308 whole-table cross-check and its resolved "
                "citation chain; v0.3.8 added the citation DOIs, the Perricone 2011 "
                "thesis evidence and the corrected GVL conflict description; v0.3.9 "
                "closed the second adversarial round: three same-CID synonym "
                "pairs moved the cross-check to 27 gated comparisons, and four "
                "ECW-308 extraction defects were fixed (41 rows gained a formula, "
                "130 rows had their name repaired). No dielectric value moved in "
                "any of those revisions; v0.3.10 corrected the 3-methoxypropionitrile "
                "temperature in the row's provenance notes and tightened the DC-200 "
                "attribution, again without moving a value; v0.3.11 resolved "
                "the stored 102 as the flash point of fluoroethylene carbonate in "
                "the row's conflict_status and notes, again without moving a "
                "dielectric value. G1+ crawl round 5 read both surviving primary "
                "measurements (Kobayashi 2003 Table 2 for the FEC 78.4 leg, Saadi & "
                "Lee 1966 Table 2 for the vinylene carbonate 126 leg); v0.3.12 then "
                "landed the two field-level revisions it enabled: it moved the stored "
                "FEC dielectric from 102 to 78.4 and adopted the VC primary identity "
                "fields, while releasing neither row into the modelling set."
            ),
            "v03": {
                "row_count": v03_summary.get("compound_count"),
                "output_sha256": (v03_summary.get("output") or {}).get("sha256"),
                "addition_count": v03_summary.get("addition_count"),
            },
            "row_counts": {
                name: row_count(source_root / "data" / filename)
                for name, filename in (
                    ("v0.3.1", "dielectric_v031.csv"),
                    ("v0.3.2", "dielectric_v032.csv"),
                    ("v0.3.3", "dielectric_v03.csv"),
                )
            },
            "exclusion_count": max(len(exclusions) - 1, 0),
            "applicability": {
                "row_count": applicability["row_count"],
                "trigger_rate": applicability["trigger_rate"],
                "outside_count": applicability["outside_count"],
                "mae_inside": applicability["mean_absolute_error_by_domain"]["inside_domain"],
                "mae_outside": applicability["mean_absolute_error_by_domain"][
                    "outside_associated_liquid"
                ],
                "high_permittivity_covered": applicability["high_permittivity_zone"],
                "rejected_variants": {
                    name: {
                        "rule": value.get("rule"),
                        "row_count": value.get("row_count"),
                        "high_permittivity_zone_covered": value.get(
                            "high_permittivity_zone_covered"
                        ),
                    }
                    for name, value in applicability["rejected_variants"].items()
                },
            },
            "g2_domain_gap": {
                "train_count": g2["train_count"],
                "test_count": g2["test_count"],
                "metrics": g2["metrics"],
            },
            "roster_reconciliation": {
                "manual_artifact": "reports/manual_appendix_reconciliation.md",
                "summary_artifact": "probes/manual_appendix_reconciliation.json",
                "alias_registry": "data/reference/dielectric_molecule_aliases.csv",
                "claims_re_derived": 6,
                "claims_confirmed_and_closed": 4,
                "claims_false_negative": 2,
                "false_negative_claims": [
                    "diglyme/triglyme/tetraglyme reported absent; present in every version since v0.1 under IUPAC-type names",
                    "glutaronitrile reported absent; present in every version since v0.1 as pentanedinitrile",
                ],
                "guard": (
                    "tests/test_manual_appendix_reconciliation.py fails if a glyme or "
                    "dinitrile leaves any dataset version, if the alias registry drifts "
                    "from the stored names, or if the working manual re-asserts the "
                    "false negative"
                ),
            },
            "g1plus": {
                "tier0_local_sources": "242/242 ThermoML dielectric XML; 636 NBS rows",
                "tier1_verdict": "PubChem and NIST WebBook carry no structured dielectric field",
                "tier2_verdict": "ECW-308 is a secondary compilation",
                "tier3_finding": (
                    "Perricone 2011 open-access thesis reports eps_r = 36 at 25 C for "
                    "3-methoxypropionitrile (Tableau 4 and Tableau 14)"
                ),
                "tier4_status": "blocked on institutional access, recorded as a limitation",
            },
            "open_items": [
                (
                    "vinylene carbonate: the primary measurement (Saadi & Lee 1966 "
                    "Table 2, eps = 126 +/- 1.0 at 25 C) landed in v0.3.12, so the "
                    "row now carries source_quality = primary_experimental and "
                    "conflict_status = knovel_78_127_interval_contains_primary_value. "
                    "The row stays withheld (model_ready = false) because no primary "
                    "source resolves the competing Knovel 78/127 interval"
                ),
                (
                    "fluoroethylene carbonate: the previously stored 102 is "
                    "recorded as a flash point, not a permittivity. The 78.4 leg "
                    "(Kobayashi 2003 "
                    "Table 2, 'Our data', 23 C) was promoted to the row's primary "
                    "measurement in v0.3.12; the 107 leg (Ue et al. 2014 Table 2.3 "
                    "read through Hall 2018 Table I, with Hagiyama 2008 Chem. Lett. "
                    "37 210 blocked) is still unread, so the two legs stay "
                    "unreconciled and the row stays withheld (model_ready = false)"
                ),
                "3-methoxypropionitrile still needs its primary-confirmation exclusion cleared and a GFN2-xTB feature row run (value and 25 C condition are now corroborated)",
                "tier 4 print and subscription sources unverified",
            ],
            "verification": verification["passed"],
        },
    )
    (week_root / "README.md").write_text(
        README_TEXT, encoding="utf-8", newline="\n"
    )
    written.append("README.md")
    write_sha256s(week_root)
    return {
        "week": WEEK,
        "output": str(week_root),
        "written_count": len(written),
        "verification_passed": verification["passed"],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = export_results(output_root=args.output_root, overwrite=args.overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
