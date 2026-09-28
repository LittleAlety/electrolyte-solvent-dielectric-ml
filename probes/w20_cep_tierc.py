"""Week 20 -- W20-6c: the "CEP 88k DFPT" dielectric handle is Tier C only.

The handle
----------
Week 20 carries an optional probe for a large computed dielectric set -- about
88,000 DFPT (density-functional perturbation theory) permittivities -- held up
as the "QM9 equivalent for epsilon".  It is worth a screen because a computed
epsilon set that large would be a genuine feature source.

The screen found (2026-09-28)
-----------------------------
The handle does not resolve to a named dataset with an open licence and a
per-row locator.  No DOI, no repository record, no licence text and no table
or figure index can be tied to it from inside this repository, and the probe
makes no network request, so a licence verdict cannot be read.  The screen is
therefore verdict = not_verifiable, and the set may not be imported: it is not
that the rows are restricted, it is that the source itself cannot be pinned
down well enough to read its licence or locate a row.

Why it can only ever be Tier C
-------------------------------
Even if the set resolved tomorrow, it could never be a ceiling break, and the
reason is physics rather than licensing.  A gas-phase DFPT permittivity and a
liquid-phase experimental permittivity are different quantities: the liquid
value carries an orientational correlation that a single-molecule calculation
does not.  Kirkwood ties them through the g factor,

    (eps - 1)(2 eps + 1) / (9 eps) = (4 pi N / 3) (alpha + mu^2 g / (3 k T))

and in the gas phase g = 1 by construction, so a computed gas-phase value is a
molecular polarisability dressed as a permittivity, not the bulk liquid number
this project predicts.  Such a set can only ever enter as Tier C -- a feature,
a descriptor or a ranking signal -- and never as a label for the liquid target.
This is the same rule the Week 20 charter states for every computed value.

Nothing is promoted.  The probe fits no model, takes no shot number, reads no
restricted numeric value (no Reaxys), touches no frozen artefact and makes no
network request.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_cep_tierc_summary.json"

#: The handle as the charter carries it, plus the spellings a screen would try.
HANDLE = "CEP 88k DFPT"
HANDLE_ALIASES = ("CEP 88k DFPT", "CEP 8.8e4 DFPT", "CEP-88k", "CEP tier C")

#: The only tier a computed permittivity may enter as.
TIER = "C"

VERDICT = "not_verifiable"
IDENTIFIABILITY = "not_identifiable"

#: The verdicts a licence review may return.  "not_verifiable" is the one a
#: handle earns when no licence text can be reached at all.
LICENCE_VERDICTS = ("open", "attribution_required", "restricted", "unknown", "not_verifiable")
LICENCE_VERDICT = "not_verifiable"

#: Every input the charter named is pinned here, so a later lane cannot claim
#: it "read the licence" without touching this file.
SCREEN_INPUTS = {
    "repository_identifier": None,
    "doi": None,
    "licence_text": None,
    "table_or_figure_locator": None,
    "named_dataset": None,
}

PHYSICS_REASON = {
    "statement": (
        "a gas-phase computed epsilon and a liquid-phase experimental epsilon "
        "are different quantities"
    ),
    "missing_term": "orientational correlation (Kirkwood g factor)",
    "kirkwood_relation": (
        "(eps - 1)(2 eps + 1) / (9 eps) = (4 pi N / 3) "
        "(alpha + mu^2 g / (3 k T))"
    ),
    "why_g_is_one_in_gas": (
        "a single-molecule DFPT calculation has no orientational correlation, "
        "so g = 1 by construction; the computed number is a molecular "
        "polarisability, not the bulk liquid permittivity"
    ),
    "consequence": (
        "such a set can only ever enter as Tier C (feature, descriptor or "
        "ranking signal), never as a label for the liquid-phase experimental "
        "target, because the quantity computed is not the quantity predicted"
    ),
}


def licence_verdicts() -> tuple[str, ...]:
    return LICENCE_VERDICTS


def identifiability() -> dict[str, object]:
    """Can the handle be tied to a source whose licence can be read?"""

    return {
        "handle": HANDLE,
        "aliases": list(HANDLE_ALIASES),
        "status": IDENTIFIABILITY,
        "handle_identifiable": False,
        "open_licence_readable": False,
        "licence_verdict": LICENCE_VERDICT,
        "screen_inputs": dict(SCREEN_INPUTS),
        "reason": (
            "no DOI, repository record, licence text, named dataset or "
            "table/figure index can be tied to the handle from inside this "
            "repository, and the probe makes no network request; a licence "
            "verdict therefore cannot be read and the source may not be imported"
        ),
    }


def plan() -> dict[str, object]:
    """The pinned configuration, printable without importing anything."""

    return {
        "schema_version": "w20_cep_tierc_plan_v0",
        "task": "week20_w20_6c_cep_tierc",
        "tier": TIER,
        "licence_verdicts": list(LICENCE_VERDICTS),
        "decidable_rule": (
            "the handle must resolve to a named dataset with an open licence "
            "text and a per-row table/figure locator before any row may be "
            "exported; failing that the verdict is not_verifiable and the "
            "ceiling is Tier C"
        ),
        "tier_rule": (
            "a gas-phase computed epsilon is a different quantity from a "
            "liquid-phase experimental epsilon (missing orientational "
            "correlation g), so the set may only ever enter as Tier C"
        ),
        "produces_reading": False,
        "promoted": False,
        "shot_number_taken": None,
        "scoreboard_attempts_delta": 0,
        "reaxys_values_used": 0,
        "models_fitted": 0,
        "main_scoreboard_untouched": True,
    }


def screen() -> dict[str, object]:
    """The screen result: the handle is not verifiable and is Tier C only."""

    payload = plan()
    payload.update(
        {
            "status": "screened",
            "verdict": VERDICT,
            "ceiling_break": False,
            "identifiability": identifiability(),
            "licence_verdict": LICENCE_VERDICT,
            "physics_reason": PHYSICS_REASON,
            "tier": TIER,
            "tier_ceiling": "features_and_predictions_only",
            "rows_artifact": None,
            "row_count": 0,
            "row_level_classification": {
                "status": "source_not_verifiable",
                "admissible": 0,
                "needs_lead": 0,
                "inadmissible": 0,
                "note": (
                    "no row is classified: the source cannot be identified well "
                    "enough to read a licence or locate a row, so no count is "
                    "invented"
                ),
            },
            "produces_reading": False,
            "promoted": False,
            "shot_number_taken": None,
            "scoreboard_attempts_delta": 0,
            "reaxys_values_used": 0,
            "models_fitted": 0,
            "main_scoreboard_untouched": True,
        }
    )
    return payload


def write_summary(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="print the pinned plan and exit")
    parser.add_argument("--write-summary", action="store_true", help="write the summary JSON")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    summary = screen()
    if args.write_summary:
        write_summary(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    raise SystemExit(main())
