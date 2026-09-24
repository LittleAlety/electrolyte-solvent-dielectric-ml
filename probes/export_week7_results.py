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
            "dataset_version": "0.3.6",
            "dataset_version_note": (
                "the 246-row set was frozen at v0.3.3; v0.3.4 fixed the "
                "model_ready modelling gate; v0.3.5-v0.3.6 revised provenance. "
                "No dielectric value moved in any of those revisions."
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
            "g1plus": {
                "tier0_local_sources": "242/242 ThermoML dielectric XML; 636 NBS rows",
                "tier1_verdict": "PubChem and NIST WebBook carry no structured dielectric field",
                "tier2_verdict": "ECW-308 is a secondary compilation",
                "tier3_finding": (
                    "Perricone 2011 open-access thesis reports eps_r = 36 for "
                    "3-methoxypropionitrile (temperature not stated)"
                ),
                "tier4_status": "blocked on institutional access, recorded as a limitation",
            },
            "open_items": [
                "vinylene carbonate conflict_open (Saadi & Lee 1966 paywalled)",
                "fluoroethylene carbonate values 78.4 / 102 / 107 unresolved",
                "3-methoxypropionitrile temperature unstated in the public source",
                "tier 4 print and subscription sources unverified",
            ],
            "verification": verification["passed"],
        },
    )
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
