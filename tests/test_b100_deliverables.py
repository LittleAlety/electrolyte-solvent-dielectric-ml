"""B100 deliverable-set guards.

PLAN B v6.0 §8 names eleven files and eight chart types. The risk this guards against
is a "complete" deliverable set that is complete only by omission: a blocked layer
quietly left out of the directory looks the same as one never planned.

Guarded:
  1. all eleven named files exist
  2. a blocked layer is present AND states why, rather than being absent
  3. every deliverable is hashed in the freeze manifest
  4. all eight chart types exist
  5. a figure that could not be drawn is an explicit panel, not a missing file
  6. the freeze manifest records the known limitations
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "outputs" / "b100"
DELIV = OUT / "deliverables"
FIG = OUT / "figures"

REQUIRED_FILES = [
    "molecule_registry_b100.csv",
    "measurement_ledger_b100.csv",
    "source_registry_b100.csv",
    "exclusion_ledger_b100.csv",
    "epsilon_labels_b100.csv",
    "xtb_descriptors_b100.csv",
    "dft_descriptors_b100.csv",
    "conformer_ensemble_b100.csv",
    "md_dielectric_b100.csv",
    "b100_freeze_manifest.json",
    "B100_FINAL_REPORT.md",
]

REQUIRED_FIGURES = [
    "fig1_family_coverage.png",
    "fig2_epsilon_distribution.png",
    "fig3_xtb_vs_dft.png",
    "fig4_conformer_effect.png",
    "fig5_applicability_domain.png",
    "fig6_md_dipole_correlation.png",
    "fig7_mae_vs_regret.png",
    "fig8_computation_status.png",
]

pytestmark = pytest.mark.skipif(not DELIV.is_dir(),
                               reason="deliverables not built yet")


def _j(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def test_all_required_files_exist() -> None:
    missing = [f for f in REQUIRED_FILES if not (DELIV / f).is_file()]
    assert not missing, f"missing deliverables: {missing}"
    # PLAN B v6.0 names eleven files; the manifest is the twelfth artifact.
    assert len(REQUIRED_FILES) == 11


def test_final_report_numbers_come_from_the_manifests() -> None:
    """The report is generated, so a quoted figure must match its source."""
    import json as _json
    report = (DELIV / "B100_FINAL_REPORT.md").read_text(encoding="utf-8")
    e1 = _json.loads((OUT / "e1_manifest_b100.json").read_text(encoding="utf-8"))
    best_mae = min(b["nested_loo_mae"] for b in e1["blocks"])
    assert f"{best_mae}" in report, (
        f"the best E1 MAE {best_mae} does not appear in the report; the report "
        f"may have been hand-edited and drifted")
    man = _json.loads((DELIV / "b100_freeze_manifest.json").read_text(
        encoding="utf-8"))
    assert str(man["hard_gates"]["achieved_qualified"]) in report


def test_blocked_layers_are_present_with_a_reason() -> None:
    """An absent file is ambiguous; a file that explains itself is not.

    DFT has since been computed (PySCF), so only MD remains blocked. The rule being
    tested is that a layer which has NOT been computed must say so explicitly rather
    than silently leaving an empty file.
    """
    for name in ("dft_descriptors_b100.json", "md_dielectric_b100.json"):
        doc = _j(DELIV / name)
        assert doc is not None, f"{name} missing; every layer must be represented"
        status = doc.get("status")
        assert status in ("NOT_COMPUTED", "COMPUTED"), f"{name} has status {status}"
        if status == "NOT_COMPUTED":
            assert doc.get("reason"), f"{name} is empty with no stated reason"
            assert doc.get("required_to_unblock"), (
                f"{name} does not say what would unblock it")
        else:
            # a computed layer must carry its protocol and coverage
            assert doc.get("protocol"), f"{name} computed without a protocol"
            assert doc.get("coverage"), f"{name} computed without coverage info"


def test_md_layer_is_still_explicitly_blocked() -> None:
    """MD has no engine in this environment and must not be silently omitted."""
    doc = _j(DELIV / "md_dielectric_b100.json")
    assert doc is not None
    assert doc["status"] == "NOT_COMPUTED"
    assert doc.get("reason")


def test_dft_layer_is_now_computed() -> None:
    """The DFT layer was unblocked by installing PySCF; that must be visible."""
    doc = _j(DELIV / "dft_descriptors_b100.json")
    assert doc is not None
    assert doc["status"] == "COMPUTED", (
        "DFT results exist but the deliverable still reports it as blocked")
    assert (doc.get("coverage") or {}).get("n_ok", 0) >= 60
    assert doc.get("protocol_substitution_declared"), (
        "the ORCA->PySCF protocol substitution must be declared")


def test_blocked_csv_has_a_header_so_the_schema_is_visible() -> None:
    for name in ("dft_descriptors_b100.csv", "md_dielectric_b100.csv"):
        p = DELIV / name
        text = p.read_text(encoding="utf-8")
        assert text.strip(), f"{name} is entirely empty; header expected"
        assert "," in text.splitlines()[0]


def test_freeze_manifest_hashes_every_deliverable() -> None:
    man = _j(DELIV / "b100_freeze_manifest.json")
    assert man is not None
    hashed = set(man["deliverables"])
    on_disk = {p.name for p in DELIV.iterdir()
               if p.is_file() and p.name != "b100_freeze_manifest.json"}
    missing = on_disk - hashed
    assert not missing, f"deliverables absent from the hash manifest: {missing}"
    for f in hashed:
        assert (DELIV / f).is_file()


def test_freeze_manifest_records_the_hard_gates() -> None:
    man = _j(DELIV / "b100_freeze_manifest.json")
    hg = man["hard_gates"]
    assert hg["min_qualified_molecules"] == 100
    assert hg["min_xtb_coverage"] == 100
    assert hg["achieved_qualified"] >= 100, (
        f"only {hg['achieved_qualified']} qualified molecules")
    assert hg["achieved_xtb"] >= 100


def test_freeze_manifest_records_limitations() -> None:
    man = _j(DELIV / "b100_freeze_manifest.json")
    lim = " ".join(man["known_limitations"])
    assert "NBS" in lim, "the single-source caveat must be recorded"
    assert "DFT" in lim and "MD" in lim, (
        "the uncomputed layers must be listed as limitations")


def test_source_independence_caveat_survives_into_the_manifest() -> None:
    man = _j(DELIV / "b100_freeze_manifest.json")
    caveat = man["source_independence"]["critical_caveat"]
    assert "单一" in caveat or "single" in caveat.lower()


# ------------------------------------------------ figures

def test_all_eight_figures_exist() -> None:
    missing = [f for f in REQUIRED_FIGURES if not (FIG / f).is_file()]
    assert not missing, f"missing figures: {missing}"


def test_blocked_figures_are_explicit_panels_not_absent() -> None:
    man = _j(FIG / "figures_manifest.json")
    assert man is not None
    blocked = {b["figure"] for b in man["blocked_figures"]}
    assert blocked, "blocked figures were not declared"
    for f in blocked:
        p = FIG / f
        assert p.is_file(), f"{f} declared blocked but not rendered"
        assert p.stat().st_size > 2000, (
            f"{f} is too small to contain a placeholder panel")


def test_figure_manifest_counts_match_disk() -> None:
    man = _j(FIG / "figures_manifest.json")
    assert man["n_written"] == len(man["figures"]) == 8
    for w in man["figures"]:
        assert (FIG / w["figure"]).is_file()
