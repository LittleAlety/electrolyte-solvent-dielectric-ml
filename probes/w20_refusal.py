"""Week 20 -- W20-5: a formal refusal regime for the high-permittivity region.

This module runs no model, reads no prediction table, takes no shot number,
touches no frozen artefact and makes no network request.  It turns the
"epsilon > 60 is not solvable with the features we have" statement from Weeks
18/19 into an *executable refusal rule* and measures how large the refused
region is on the frozen registry.

Why a refusal instead of a hard prediction
-------------------------------------------
The high-permittivity region is not a model-capacity problem.  In the frozen
Onsager/Kirkwood probe the epsilon > 60 region holds 5 compounds, the analytic
prior covers 0 of them, and the in-service delta arm carries an MAE of
75.95675695251926 there -- the missing dimension is the Kirkwood correlation
factor g, which no single-molecule descriptor supplies.  For a screening funnel
the honest object is therefore not a number but a decision: decline to rank the
candidate and route it to measurement.  Refusing out of domain is worth more
than answering out of domain, because a wrong answer enters the shortlist
silently while a refusal is visible and triageable.

Two rules, both executable
---------------------------
1. ``epsilon > HIGH_PERMITTIVITY_EPS`` (60.0, imported from the W19 ranking key
   so the threshold has one owner) refuses the high-permittivity region.
2. a compound outside the declared D1 applicability domain -- D1 is
   ``NumHDonors(SMILES) >= 1 and TPSA(SMILES) >= 20.0``, the polar-protic
   domain declared in ``probes/dielectric_applicability_domain_summary.json``
   -- refuses the second scoreboard out-of-domain set, whose endpoint R2 is
   0.3198024498133034 against 0.524012313223719 inside.

The refused row is never given a low score: it carries ``refused = true``, the
reasons, and ``exit = refused_experimental_queue``.  The rule is a predicate on
inputs, so the same function answers the screening question (a model output) and
the registry audit (a stored label).

What this module does not do
----------------------------
It produces no R2, no MAE and no ranking.  Its only numbers are counts of the
frozen registry and the frozen domain endpoints, which are registered as
descriptive.  ``produces_reading`` is false and the main scoreboard is
untouched.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from probes.w19_ranking_key import HIGH_PERMITTIVITY_EPS, high_permittivity_excluded

REGISTRY_PATH = REPOSITORY_ROOT / "data" / "processed" / "four_core_key_registry.csv"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w20_refusal_prereg.json"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_refusal_summary.json"
ARTIFACT_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_refusal_rule.json"

#: D1 applicability domain, verbatim from the frozen domain endpoint.
D1_MIN_HBD = 1
D1_MIN_TPSA = 20.0

#: The second (domain-declared) scoreboard, frozen at 5 seeds.  Never a
#: replacement for the global board and never mixed with it.
SECOND_SCOREBOARD: dict[str, Any] = {
    "global_endpoint_r2": 0.45401075998423623,
    "d1_in_domain_r2": 0.524012313223719,
    "d1_out_of_domain_r2": 0.3198024498133034,
    "d1_in_domain_compounds": 57.0,
    "d1_out_of_domain_compounds": 40.0,
    "scored_compounds": 97.0,
    "scored_rows": 457.0,
    "d1_definition": "NumHDonors(SMILES) >= 1 and TPSA(SMILES) >= 20.0",
    "source": "probes/dielectric_applicability_domain_summary.json#endpoint",
}

#: The frozen high-permittivity evidence, carried so the rule owns its reason.
HIGH_EPS_EVIDENCE: dict[str, Any] = {
    "compounds": 5,
    "onsager_coverage": "0/5",
    "in_service_mae": 75.95675695251926,
    "source": "probes/dielectric_onsager_delta_summary.json",
}

REFUSAL_EXIT_REFUSED = "refused_experimental_queue"
REFUSAL_EXIT_RANKED = "ranked"


@dataclass(frozen=True)
class RefusalRule:
    """One executable refusal predicate, its evidence and its exit code."""

    reason: str
    rule_id: str
    predicate: str
    evidence: tuple[str, ...]
    exit_code: str


REFUSAL_RULES: tuple[RefusalRule, ...] = (
    RefusalRule(
        reason="high_permittivity_region",
        rule_id="w20_refusal_high_eps_v1",
        predicate="epsilon > HIGH_PERMITTIVITY_EPS (60.0)",
        evidence=(
            "5 compounds in the epsilon > 60 region; Onsager prior coverage 0/5",
            "in-service delta-arm MAE 75.95675695251926 in that region",
            "reports/w19_ranking_key_spec.md section 6",
        ),
        exit_code=REFUSAL_EXIT_REFUSED,
    ),
    RefusalRule(
        reason="outside_applicability_domain",
        rule_id="w20_refusal_domain_d1_v1",
        predicate="not (NumHDonors >= 1 and TPSA >= 20.0)",
        evidence=(
            "D1 endpoint R2 in-domain 0.524012313223719 vs out-of-domain 0.3198024498133034",
            "40 of 97 scored compounds are out of domain",
            "reports/decisions_log.md section 28.45",
        ),
        exit_code=REFUSAL_EXIT_REFUSED,
    ),
)

REFUSAL_REASONS: tuple[str, ...] = tuple(rule.reason for rule in REFUSAL_RULES)


def d1_in_domain(donor_count: int, tpsa: float) -> bool:
    """The declared D1 domain: at least one donor and TPSA >= 20 A^2."""

    return donor_count >= D1_MIN_HBD and tpsa >= D1_MIN_TPSA


def d1_label(donor_count: int, tpsa: float) -> str:
    return "in_domain" if d1_in_domain(donor_count, tpsa) else "out_of_domain"


def refusal_reasons(*, epsilon: float | None, donor_count: int, tpsa: float) -> list[str]:
    """Every refusal this candidate triggers, in rule order.

    ``epsilon`` is whatever permittivity the caller holds -- a stored label
    during the registry audit, a model output during screening.  A missing
    value cannot trigger the high-permittivity rule (absence is not a value).
    """

    reasons: list[str] = []
    if epsilon is not None and epsilon > HIGH_PERMITTIVITY_EPS:
        reasons.append("high_permittivity_region")
    if not d1_in_domain(donor_count, tpsa):
        reasons.append("outside_applicability_domain")
    return reasons


def refusal_decision(*, epsilon: float | None, donor_count: int, tpsa: float) -> dict[str, Any]:
    """The executable verdict for one candidate: refuse, or let it be ranked.

    A refused candidate is *not* given a low score.  ``score_produced`` is false
    and ``exit`` names the destination queue, so downstream code cannot mistake
    a refusal for a bad prediction.
    """

    reasons = refusal_reasons(epsilon=epsilon, donor_count=donor_count, tpsa=tpsa)
    refused = bool(reasons)
    return {
        "refused": refused,
        "refusal_reasons": reasons,
        "domain_label": d1_label(donor_count, tpsa),
        "high_permittivity_excluded": bool(high_permittivity_excluded(epsilon)),
        "score_produced": not refused,
        "exit": REFUSAL_EXIT_REFUSED if refused else REFUSAL_EXIT_RANKED,
    }


def read_registry(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _smiles_domain(smiles: str) -> tuple[int, float] | None:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors

    RDLogger.DisableLog("rdApp.*")
    molecule = Chem.MolFromSmiles(smiles) if smiles else None
    if molecule is None:
        return None
    return int(Descriptors.NumHDonors(molecule)), float(Descriptors.TPSA(molecule))


def _epsilon_of(row: Mapping[str, str]) -> float | None:
    if str(row.get("has_dielectric", "")).strip().lower() != "true":
        return None
    try:
        return float(str(row.get("dielectric", "")).strip())
    except ValueError:
        return None


def registry_refusal_scale(registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Count the refused region on the frozen registry.  Descriptive only."""

    rows = read_registry(registry_path)
    counters = {
        "registry_rows": len(rows),
        "unparsable_smiles": 0,
        "rows_with_dielectric": 0,
        "d1_in_domain_rows": 0,
        "d1_out_of_domain_rows": 0,
        "eps_rows_d1_in_domain": 0,
        "eps_rows_d1_out_of_domain": 0,
        "eps_rows_refused_by_high_eps": 0,
        "eps_rows_refused_by_domain": 0,
        "eps_rows_refused_by_both": 0,
        "eps_rows_refused_total": 0,
        "eps_rows_ranked": 0,
    }
    for row in rows:
        domain = _smiles_domain(str(row.get("smiles", "")).strip())
        if domain is None:
            counters["unparsable_smiles"] += 1
            continue
        donor_count, tpsa = domain
        inside = d1_in_domain(donor_count, tpsa)
        counters["d1_in_domain_rows" if inside else "d1_out_of_domain_rows"] += 1
        epsilon = _epsilon_of(row)
        if epsilon is None:
            continue
        counters["rows_with_dielectric"] += 1
        reasons = refusal_reasons(epsilon=epsilon, donor_count=donor_count, tpsa=tpsa)
        high_eps = "high_permittivity_region" in reasons
        out_domain = "outside_applicability_domain" in reasons
        counters["eps_rows_d1_in_domain" if inside else "eps_rows_d1_out_of_domain"] += 1
        if high_eps:
            counters["eps_rows_refused_by_high_eps"] += 1
        if out_domain:
            counters["eps_rows_refused_by_domain"] += 1
        if high_eps and out_domain:
            counters["eps_rows_refused_by_both"] += 1
        if reasons:
            counters["eps_rows_refused_total"] += 1
        else:
            counters["eps_rows_ranked"] += 1
    with_eps = counters["rows_with_dielectric"]
    counters["eps_refusal_rate"] = (
        counters["eps_rows_refused_total"] / with_eps if with_eps else 0.0
    )
    return counters


def plan() -> dict[str, Any]:
    """The pinned configuration, printable without touching the registry."""

    return {
        "schema_version": "w20_refusal_plan_v0",
        "task": "week20_w20_5_high_epsilon_refusal",
        "status": "registered_no_model",
        "produces_reading": False,
        "promoted": False,
        "main_scoreboard_untouched": True,
        "scoreboard_attempts_delta": 0,
        "shot_number_taken": None,
        "high_permittivity_eps": HIGH_PERMITTIVITY_EPS,
        "d1_min_hbd": D1_MIN_HBD,
        "d1_min_tpsa": D1_MIN_TPSA,
        "refusal_reasons": list(REFUSAL_REASONS),
        "refusal_rules": [
            {
                "reason": rule.reason,
                "rule_id": rule.rule_id,
                "predicate": rule.predicate,
                "exit_code": rule.exit_code,
            }
            for rule in REFUSAL_RULES
        ],
        "second_scoreboard": dict(SECOND_SCOREBOARD),
        "high_eps_evidence": dict(HIGH_EPS_EVIDENCE),
        "value_judgement": (
            "in a screening funnel, refusing out of domain is worth more than "
            "answering out of domain: a wrong answer enters the shortlist "
            "silently, a refusal is visible and routes to measurement"
        ),
        "registry": "data/processed/four_core_key_registry.csv",
    }


def run(registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Plan plus the frozen-registry refusal census."""

    scale = registry_refusal_scale(registry_path)
    return {
        **plan(),
        "status": "executed_descriptive",
        "registry_scale": scale,
        "verdict": _verdict(scale),
    }


def _verdict(scale: Mapping[str, Any]) -> str:
    if scale["eps_rows_refused_total"] <= 0:
        return "no_refusal_region_found"
    return "refusal_region_quantified"




def refusal_rule_document(registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """The machine-readable refusal rule set: rules, exits, reasons, scale."""

    scale = registry_refusal_scale(registry_path)
    return {
        "schema_version": "w20_refusal_rule_v0",
        "task": "week20_w20_5_high_epsilon_refusal",
        "status": "executed_descriptive",
        "produces_reading": False,
        "promoted": False,
        "main_scoreboard_untouched": True,
        "scoreboard_attempts_delta": 0,
        "shot_number_taken": None,
        "reaxys_values_used": 0,
        "high_permittivity_eps": HIGH_PERMITTIVITY_EPS,
        "d1_definition": SECOND_SCOREBOARD["d1_definition"],
        "d1_min_hbd": D1_MIN_HBD,
        "d1_min_tpsa": D1_MIN_TPSA,
        "registry": "data/processed/four_core_key_registry.csv",
        "exit_codes": {
            "refused": REFUSAL_EXIT_REFUSED,
            "ranked": REFUSAL_EXIT_RANKED,
        },
        "rules": [
            {
                "rule_id": rule.rule_id,
                "reason": rule.reason,
                "predicate": rule.predicate,
                "exit_code": rule.exit_code,
                "evidence": list(rule.evidence),
            }
            for rule in REFUSAL_RULES
        ],
        "refusal_reasons": list(REFUSAL_REASONS),
        "registry_scale": scale,
        "verdict": _verdict(scale),
        "value_judgement": plan()["value_judgement"],
    }


def write_artifact(
    path: Path = ARTIFACT_PATH, registry_path: Path = REGISTRY_PATH
) -> Path:
    """Write the machine-readable refusal rule set to ``probes/artifacts``."""

    document = refusal_rule_document(registry_path=registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="print the pinned plan and exit")
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--write-summary", action="store_true", help="write the summary JSON")
    parser.add_argument(
        "--write-artifact", action="store_true", help="write the refusal rule artifact"
    )
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.write_artifact:
        write_artifact()
    summary = run(registry_path=args.registry)
    if args.write_summary:
        args.summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    raise SystemExit(main())
