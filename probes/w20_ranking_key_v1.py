"""Week 20 -- W20-3 / section 28.59: the ranking key v1 and the intersection fill.

This module is the executable half of 'reports/w20_ranking_key_v1_spec.md'.  It
extends the Week 19 D6 ranking key (probes/w19_ranking_key.py, spec v0) with a
channel-extension register, a de-duplication guard and an applicability-domain gate,
and it fills the 115,756-candidate Batt-SLM space into a multi-dimension scoreable
candidate list through the Tier C layer (features plus model predictions).

Three rules are structural here, not editorial.

1. De-duplication.  IP is collinear with HOMO (Pearson r = -0.9876) and EA with LUMO
   (-0.9513) on the label space, so each pair is recorded as a collinearity group and
   validate_keys refuses any key that spends weight twice on one group.
2. The applicability-domain gate removes a row, it does not down-score it.  An
   out-of-domain row gets score None and rank None and stays off the Pareto front,
   and the min-max normalisation runs inside the in-domain set only, so a rejected row
   can never move a kept row's score.
3. The weights are declared before the run.  With no measured cost or benefit ratio
   between channels the only non-arbitrary choice is equal weight, and
   build_default_keys refuses to widen the key onto an extension channel whose column
   and direction have not been pinned by a new preregistration.

Discipline: predictions order candidates and are never written into any pool as
labels, and the generation loop stays welded shut.  This is a ranking key, not a
candidate generator.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
from export_results_common import write_json_stable

__all__ = [
    "CANDIDATE_COLUMNS",
    "CHANNEL_EXTENSION_STATUS",
    "CHANNEL_GATE_STATUS",
    "COLLINEARITY_RECORD",
    "D1_MIN_HBD",
    "D1_MIN_TPSA",
    "D1_RULE",
    "DEDUP_DROPPED_COLUMNS",
    "DEDUP_KEPT_COLUMNS",
    "DEFAULT_KEYS",
    "DEFAULT_WEIGHTS",
    "DOMAIN_IN",
    "DOMAIN_OUT",
    "DOMAIN_SCOREBOARD",
    "ELIGIBLE_CHANNELS",
    "EXAMPLE_MOLECULES",
    "EXTENSION_VERDICT_GLOBS",
    "GATED_CHANNELS",
    "HIGH_PERMITTIVITY_EPS",
    "KEY_CHANNEL_SPECS",
    "POSITION_STATEMENT",
    "PREREG_WEIGHTS",
    "PREREG_WEIGHTS_SOURCE",
    "KeySpec",
    "annotate_domains",
    "assign_scores",
    "build_default_keys",
    "classify_domain",
    "d1_in_domain",
    "dominates",
    "fill_candidates",
    "high_permittivity_excluded",
    "pareto_front",
    "ranking_key_table",
    "scan_extension_verdicts",
    "validate_keys",
    "write_candidate_csv",
]

# The one-sentence position, verbatim, so no reader can re-brand this artefact.
POSITION_STATEMENT = "这是排序键，不是候选生成器"

# --------------------------------------------------------------------------- #
# 1. Gate status of the six core channels (unchanged from Week 19 D6)
# --------------------------------------------------------------------------- #
# 'pass_when' is 'below' for an error metric and 'above' for a quality metric; and
# 'passed' is derived from 'measured' at import time, never typed by hand.
_CORE_GATE_DECLARATIONS: dict[str, dict[str, object]] = {
    "dielectric": {
        "label": "epsilon (dielectric constant), grouped R2",
        "metric": "r2",
        "gate": 0.60,
        "pass_when": "above",
        "measured": 0.4766400383507876,
        "source": (
            "probes/four_channel_coverage_summary.json"
            "#pinned.dielectric_main_scoreboard_headline_r2; gate 0.60 from "
            "reports/dielectric_pool_expansion_audit.md:74"
        ),
    },
    "viscosity": {
        "label": "eta (viscosity), group_key MAE in log10(cP)",
        "metric": "log10_cP_mae",
        "gate": 0.15,
        "pass_when": "below",
        "measured": 0.17477197208762,
        "source": (
            "probes/viscosity_baseline_summary.json#primary_gate (group_key MAE); "
            "the W18 row-level unfreeze best reading 0.15686276760094522 is also "
            "above the gate (reports/decisions_log.md 28.38)"
        ),
    },
    "homo": {
        "label": "HOMO energy, fold-mean MAE in eV",
        "metric": "mae_eV",
        "gate": 0.20,
        "pass_when": "below",
        "measured": 0.19050925839013938,
        "source": (
            "models/homo_lumo_baselines.json#gate.per_target.HOMO.best_model_mae; "
            "gate.threshold_mae = 0.2"
        ),
    },
    "lumo": {
        "label": "LUMO energy, fold-mean MAE in eV",
        "metric": "mae_eV",
        "gate": 0.20,
        "pass_when": "below",
        "measured": 0.13855083976437643,
        "source": (
            "models/homo_lumo_baselines.json#gate.per_target.LUMO.best_model_mae; "
            "gate.threshold_mae = 0.2"
        ),
    },
    "oxidation": {
        "label": "oxidation free energy, MAE in eV",
        "metric": "mae_eV",
        "gate": 0.15,
        "pass_when": "below",
        "measured": 0.2905180517963865,
        "source": (
            "probes/four_channel_coverage_summary.json"
            "#pinned.redox_oxidation_mae_ev; gate 0.15 from "
            "probes/p4_redox_v2_summary.json#gate.threshold_mae"
        ),
    },
    "reduction": {
        "label": "reduction free energy, MAE in eV",
        "metric": "mae_eV",
        "gate": 0.15,
        "pass_when": "below",
        "measured": 0.4096241620366996,
        "source": (
            "probes/four_channel_coverage_summary.json"
            "#pinned.redox_reduction_mae_ev; gate 0.15 from "
            "probes/p4_redox_v2_summary.json#gate.threshold_mae"
        ),
    },
}


def _derive_gate_status(
    declarations: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    """Recompute 'passed' from 'measured' so a typed verdict cannot be smuggled in."""

    status: dict[str, dict[str, object]] = {}
    for channel, record in declarations.items():
        measured = float(record["measured"])
        gate = float(record["gate"])
        pass_when = str(record["pass_when"])
        if pass_when == "below":
            passed = measured < gate
        elif pass_when == "above":
            passed = measured >= gate
        else:
            raise ValueError(f"unknown pass_when {pass_when!r} for {channel!r}")
        status[channel] = {**record, "passed": passed}
    return status

# --------------------------------------------------------------------------- #
# 2. The channel-extension register (W20-1 eta, W20-2 Step 2 safety)
# --------------------------------------------------------------------------- #
# Widening the key is gated on another lane's verdict.  While no verdict is on disk
# the conservative reading is 'not passed', so the extension stays out of the key and
# the blocked state is registered instead of being assumed away.
EXTENSION_CONDITIONS: dict[str, str] = {
    "viscosity": (
        "merged only if the W20-1 fairness recheck is on disk and passes "
        "(delta <= -0.02 with both arms' gate status unchanged)"
    ),
    "safety": (
        "merged only if the W20-2 Step-2 modelling verdict is on disk and passes "
        "its own gate"
    ),
}

EXTENSION_VERDICT_GLOBS: dict[str, tuple[str, ...]] = {
    "viscosity": (
        "probes/w20_*eta*.json",
        "probes/w20_*viscosity*.json",
        "reports/w20_*eta*.md",
        "reports/w20_*viscosity*.md",
        "reports/_w20_section_w201*.md",
    ),
    "safety": (
        "probes/w20_*safety*.json",
        "reports/w20_*safety*.md",
        "reports/_w20_section_w202*.md",
    ),
}

_EXTENSION_DECLARATIONS: dict[str, dict[str, object]] = {
    "viscosity": {
        "owner_lane": "W20-1",
        "verdict_present": True,
        "verdict": "eta_crosses_gate_out_of_fold",
        "conservative_default": "treated as not passed while no verdict is on disk",
        "detected_artifacts": (
            "probes/w20_eta_fairness_summary.json",
            "reports/_w20_section_w201.md",
            "reports/w20_eta_fairness.md",
        ),
        "note": (
            "W20-1 landed on 2026-09-28 with verdict eta_crosses_gate_out_of_fold "
            "(row-level delta -0.05419789751156204 against the +/-0.02 tolerance, both "
            "gate states unchanged), so the merge condition of EXTENSION_CONDITIONS is "
            "met.  The channel still does NOT enter the key, for two separately "
            "registered reasons: KEY_CHANNEL_SPECS pins no eta column and direction, and "
            "the locked W20-3 pre-registration requires a NEW pre-registration to pin "
            "them before the key may widen; and CHANNEL_GATE_STATUS still reads eta at "
            "the frozen W19 group-key value 0.17477197208762, which is above the 0.15 "
            "gate, so the channel would be filtered out even if a column were pinned.  "
            "The authorisation is registered here and the widening is deferred."
        ),
    },
    "safety": {
        "owner_lane": "W20-2 (Step 2)",
        "verdict_present": True,
        "verdict": "passed",
        "conservative_default": "treated as not passed while no verdict is on disk",
        "detected_artifacts": (
            "probes/w20_safety_model_summary.json",
            "reports/_w20_section_w202.md",
            "reports/w20_safety_model.md",
        ),
        "note": (
            "W20-2 Step 2 (section 28.58, shot 22) landed on 2026-09-28 with verdict "
            "modelable_all and no blocking conditions, so the merge condition is met; "
            "the key still cannot weight safety because safety has no declared gate "
            "reading and no pinned key column, so KEY_CHANNEL_SPECS is unchanged and "
            "the key stays on the two orbital channels; per the W20-2 domain "
            "declaration safety may only ever enter the eps-side key, never the eta side"
        ),
    },
}


def _derive_merged(record: Mapping[str, object]) -> bool:
    """A channel is merged only when a verdict is on disk and it reads 'passed'."""

    if not bool(record["verdict_present"]):
        return False
    return str(record["verdict"]) == "passed"


CHANNEL_EXTENSION_STATUS: dict[str, dict[str, object]] = {
    channel: {
        **record,
        "condition": EXTENSION_CONDITIONS[channel],
        "merged": _derive_merged(record),
    }
    for channel, record in _EXTENSION_DECLARATIONS.items()
}


def _is_plan_artifact(name: str) -> bool:
    """A preregistration, a skeleton or a Step-1 ablation is a plan, not a verdict."""

    lowered = name.lower()
    markers = ("prereg", "plan", "skeleton", "ablation", "step1", "step_1")
    return any(marker in lowered for marker in markers)


def scan_extension_verdicts(root: Path = REPOSITORY_ROOT) -> dict[str, dict[str, object]]:
    """Look on disk for the verdict artefacts this register is waiting on."""

    scan: dict[str, dict[str, object]] = {}
    for channel, patterns in EXTENSION_VERDICT_GLOBS.items():
        found: list[str] = []
        for pattern in patterns:
            found.extend(
                path.relative_to(root).as_posix()
                for path in sorted(root.glob(pattern))
                if path.is_file() and not _is_plan_artifact(path.name)
            )
        scan[channel] = {
            "verdict_present": bool(found),
            "detected_artifacts": tuple(sorted(set(found))),
        }
    return scan


def assert_no_unregistered_verdicts(root: Path = REPOSITORY_ROOT) -> None:
    """Refuse to widen the key onto a verdict this module was not told about.

    Merging an extension channel changes the key, so it is a preregistration change
    and not something a run may pick up silently.
    """

    scan = scan_extension_verdicts(root)
    for channel, record in scan.items():
        registered = bool(CHANNEL_EXTENSION_STATUS[channel]["verdict_present"])
        if bool(record["verdict_present"]) and not registered:
            raise RuntimeError(
                f"a {channel} verdict artefact appeared on disk: "
                f"{record['detected_artifacts']!r}; the ranking key must not widen "
                "onto it without a new preregistration"
            )


# --------------------------------------------------------------------------- #
# 3. De-duplication: collinear columns may not be counted twice
# --------------------------------------------------------------------------- #
# IP and EA are not extra channels: on the frozen label space IP is collinear with
# HOMO (r = -0.9876) and EA with LUMO (r = -0.9513), so counting them again would
# spend the same information twice.  The groups are recorded with their correlations.
COLLINEARITY_RECORD: tuple[dict[str, object], ...] = (
    {
        "columns": ("HOMO_eV", "IP_eV"),
        "pearson_r": -0.9876,
        "source": "reports/homo_lumo_baselines.md label-space diagnostics",
    },
    {
        "columns": ("LUMO_eV", "EA_eV"),
        "pearson_r": -0.9513,
        "source": "reports/homo_lumo_baselines.md label-space diagnostics",
    },
)
DEDUP_KEPT_COLUMNS: tuple[str, ...] = ("HOMO_eV", "LUMO_eV")
DEDUP_DROPPED_COLUMNS: tuple[str, ...] = ("IP_eV", "EA_eV")


def _collinear_partners(column: str) -> set[str]:
    partners: set[str] = set()
    for record in COLLINEARITY_RECORD:
        columns = tuple(str(name) for name in record["columns"])
        if column in columns:
            partners.update(columns)
    partners.discard(column)
    return partners


# --------------------------------------------------------------------------- #
# 4. The failure zone and the applicability domain
# --------------------------------------------------------------------------- #
# The epsilon > 60 zone is unsolved under single-molecule descriptors (the Onsager
# prior covers 0 of 5 high-permittivity compounds there).  D1 is the preregistered,
# model-independent polar-protic boundary, read from the frozen SMILES alone.
HIGH_PERMITTIVITY_EPS = 60.0
D1_MIN_HBD = 1
D1_MIN_TPSA = 20.0
D1_RULE = "NumHDonors(SMILES) >= 1 and TPSA(SMILES) >= 20.0"
DOMAIN_IN = "in_domain"
DOMAIN_OUT = "out_of_domain"
DOMAIN_COLUMN = "domain"

# The domain-split scoreboard this key aligns with (W18-B, section 28.45), quoted so
# the split is never stated without its readings.
DOMAIN_SCOREBOARD: dict[str, object] = {
    "global_r2": 0.45401075998423623,
    "d1_in_domain_r2": 0.524012313223719,
    "d1_out_of_domain_r2": 0.3198024498133034,
    "d1_pool_compounds": 97,
    "d1_out_of_domain_compounds": 40,
    "rule": D1_RULE,
    "source": (
        "probes/dielectric_applicability_domain_summary.json; "
        "reports/_w18_section_domain.md (28.45)"
    ),
}


def high_permittivity_excluded(epsilon: float | None) -> bool:
    """True when a permittivity reading falls in the declared failure zone."""

    if epsilon is None:
        return False
    return float(epsilon) > HIGH_PERMITTIVITY_EPS


def d1_in_domain(num_h_donors: float, tpsa: float) -> bool:
    """Rule D1: polar protic, from SMILES-derived features alone."""

    return float(num_h_donors) >= D1_MIN_HBD and float(tpsa) >= D1_MIN_TPSA


def classify_domain(
    row: Mapping[str, object],
    *,
    epsilon: float | None = None,
    donor_column: str = "NumHDonors",
    tpsa_column: str = "TPSA",
) -> str:
    """Return DOMAIN_IN or DOMAIN_OUT for one row.  No label is ever read."""

    label = _label(row)
    if epsilon is not None and high_permittivity_excluded(epsilon):
        return DOMAIN_OUT
    donors = _read(row, donor_column, label)
    tpsa = _read(row, tpsa_column, label)
    return DOMAIN_IN if d1_in_domain(donors, tpsa) else DOMAIN_OUT


def annotate_domains(
    rows: Iterable[Mapping[str, object]],
    *,
    epsilon_column: str | None = None,
) -> list[dict[str, object]]:
    """Attach the declared domain verdict to every row, in input order."""

    materialised = [dict(row) for row in rows]
    for row in materialised:
        raw = None if epsilon_column is None else row.get(epsilon_column)
        epsilon = None if raw is None else _require_finite(raw, epsilon_column, _label(row))
        row[DOMAIN_COLUMN] = classify_domain(row, epsilon=epsilon)
    return materialised


# --------------------------------------------------------------------------- #
# 5. The v1 key: eligible channels only, weights declared before the run
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class KeySpec:
    """One key dimension.  'direction' is the better direction: min = lower is better.

    'weight' is the explicit share of the score; the weights of a key set must sum to
    one.
    """

    channel: str
    column: str
    direction: str
    weight: float

    def __post_init__(self) -> None:
        if self.direction not in {"min", "max"}:
            raise ValueError(f"direction must be 'min' or 'max', got {self.direction!r}")
        if not 0.0 < self.weight <= 1.0:
            raise ValueError(f"weight must lie in (0, 1], got {self.weight!r}")


# The pinned interface for every channel allowed into the key.  A channel that
# becomes eligible without an entry here makes build_default_keys raise, so the key
# cannot widen onto an un-declared column.
KEY_CHANNEL_SPECS: dict[str, tuple[str, str]] = {
    "homo": ("HOMO_eV", "min"),
    "lumo": ("LUMO_eV", "max"),
}

CHANNEL_GATE_STATUS: dict[str, dict[str, object]] = _derive_gate_status(
    _CORE_GATE_DECLARATIONS
)
CHANNEL_GATE_STATUS["safety"] = {
    "label": "liquid window (mp / bp / flash point), modelling gate",
    "metric": "not_declared",
    "gate": None,
    "pass_when": "below",
    "measured": None,
    "passed": False,
    "source": (
        "no W20-2 Step-2 verdict is on disk; the Step-1 coverage readings live in "
        "probes/w20_safety_ablation.py (registered, not executed)"
    ),
}
GATED_CHANNELS: tuple[str, ...] = tuple(
    channel for channel, record in CHANNEL_GATE_STATUS.items() if record["passed"]
)


def _eligible_channels() -> tuple[str, ...]:
    """Gated channels that are not blocked extension channels."""

    eligible: list[str] = []
    for channel, record in CHANNEL_GATE_STATUS.items():
        if not record["passed"]:
            continue
        extension = CHANNEL_EXTENSION_STATUS.get(channel)
        if extension is not None and not extension["merged"]:
            continue
        eligible.append(channel)
    return tuple(eligible)


ELIGIBLE_CHANNELS: tuple[str, ...] = _eligible_channels()


def build_default_keys(
    channels: Sequence[str] = ELIGIBLE_CHANNELS,
) -> tuple[KeySpec, ...]:
    """Equal weights over the eligible channels, or refuse if one has no pinned spec.

    Equal weights are the only non-arbitrary choice while there is no measured cost or
    benefit ratio between the channels; a channel with no pinned column and direction
    cannot be given a weight at all.
    """

    if not channels:
        raise ValueError("the ranking key must name at least one channel")
    missing = [channel for channel in channels if channel not in KEY_CHANNEL_SPECS]
    if missing:
        raise ValueError(
            "channel(s) " + ", ".join(sorted(missing)) + " are eligible but have no "
            "pinned key column and direction; widening the key needs a new "
            "preregistration"
        )
    weight = 1.0 / len(channels)
    return tuple(
        KeySpec(
            channel=channel,
            column=KEY_CHANNEL_SPECS[channel][0],
            direction=KEY_CHANNEL_SPECS[channel][1],
            weight=weight,
        )
        for channel in channels
    )


DEFAULT_KEYS: tuple[KeySpec, ...] = build_default_keys()
DEFAULT_WEIGHTS: dict[str, float] = {spec.channel: spec.weight for spec in DEFAULT_KEYS}

# The weights as declared before the run.  They are typed here and cross-checked
# against the derived key, so a derivation change cannot slide past the declaration.
PREREG_WEIGHTS: dict[str, float] = {"homo": 0.5, "lumo": 0.5}
PREREG_WEIGHTS_SOURCE = "no_cost_ratio_evidence"
if DEFAULT_WEIGHTS != PREREG_WEIGHTS:
    raise ValueError(
        f"derived key weights {DEFAULT_WEIGHTS!r} drifted from the preregistered "
        f"{PREREG_WEIGHTS!r}"
    )


def validate_keys(keys: Sequence[KeySpec]) -> None:
    """Refuse a key that is ungated, blocked, duplicated or unnormalised."""

    if not keys:
        raise ValueError("the ranking key must name at least one channel")
    blocked: list[str] = []
    for spec in keys:
        record = CHANNEL_GATE_STATUS.get(spec.channel)
        if record is None:
            raise ValueError(f"unknown channel {spec.channel!r}")
        if not record["passed"]:
            raise ValueError(
                "the ranking key may only contain gated channels; ungated: "
                + spec.channel
            )
        if spec.channel not in ELIGIBLE_CHANNELS:
            blocked.append(spec.channel)
    if blocked:
        raise ValueError(
            "the ranking key is waiting on an extension verdict for: "
            + ", ".join(sorted(blocked))
        )
    columns = [spec.column for spec in keys]
    if len(set(columns)) != len(columns):
        raise ValueError("two key entries share one input column")
    for spec in keys:
        clash = sorted(_collinear_partners(spec.column).intersection(set(columns)))
        if clash:
            raise ValueError(
                f"column {spec.column!r} is collinear with {clash!r}; the same "
                "information may not be counted twice"
            )
    total = sum(spec.weight for spec in keys)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"the key weights must sum to one, got {total!r}")


validate_keys(DEFAULT_KEYS)


# --------------------------------------------------------------------------- #
# 6. Pure ranking primitives
# --------------------------------------------------------------------------- #
def _label(row: Mapping[str, object]) -> str:
    return str(row.get("name", "?"))


def _require_finite(value: object, column: str, label: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label}: column {column!r} is not a number ({value!r})") from error
    if not np.isfinite(number):
        raise ValueError(f"{label}: column {column!r} is not finite ({value!r})")
    return number


def _read(row: Mapping[str, object], column: str, label: str) -> float:
    if column not in row:
        raise ValueError(f"{label}: column {column!r} is missing")
    return _require_finite(row[column], column, label)


def _resolve_keys(keys: Sequence[KeySpec] | None) -> tuple[KeySpec, ...]:
    resolved = tuple(DEFAULT_KEYS if keys is None else keys)
    validate_keys(resolved)
    return resolved


def _strictly_better(first: float, second: float, direction: str) -> bool:
    if direction == "min":
        return first < second
    if direction == "max":
        return first > second
    raise ValueError(f"unknown direction {direction!r}")


def _is_in_domain(row: Mapping[str, object], domain_column: str, label: str) -> bool:
    if domain_column not in row:
        raise ValueError(
            f"{label}: column {domain_column!r} is missing; the domain gate is mandatory"
        )
    value = str(row[domain_column])
    if value not in {DOMAIN_IN, DOMAIN_OUT}:
        raise ValueError(
            f"{label}: {domain_column!r} must be {DOMAIN_IN!r} or {DOMAIN_OUT!r}, "
            f"got {value!r}"
        )
    return value == DOMAIN_IN


def dominates(
    first: Mapping[str, object],
    second: Mapping[str, object],
    keys: Sequence[KeySpec] | None = None,
    *,
    domain_column: str = DOMAIN_COLUMN,
) -> bool:
    """Strict domination on the key dimensions, for in-domain rows only.

    A row outside the applicability domain carries no order at all, so asking whether
    it dominates (or is dominated by) another row is refused rather than answered.
    """

    resolved = _resolve_keys(keys)
    if not _is_in_domain(first, domain_column, _label(first)):
        raise ValueError(f"{_label(first)}: an out-of-domain row carries no order")
    if not _is_in_domain(second, domain_column, _label(second)):
        raise ValueError(f"{_label(second)}: an out-of-domain row carries no order")
    strictly_better = False
    for spec in resolved:
        mine = _read(first, spec.column, _label(first))
        theirs = _read(second, spec.column, _label(second))
        if _strictly_better(theirs, mine, spec.direction):
            return False
        if _strictly_better(mine, theirs, spec.direction):
            strictly_better = True
    return strictly_better


def _front_flags(
    rows: Sequence[Mapping[str, object]],
    keys: Sequence[KeySpec],
    domain_column: str,
) -> list[bool]:
    in_domain = [_is_in_domain(row, domain_column, _label(row)) for row in rows]
    flags: list[bool] = []
    for index, row in enumerate(rows):
        if not in_domain[index]:
            flags.append(False)
            continue
        dominated = any(
            in_domain[position]
            and dominates(other, row, keys, domain_column=domain_column)
            for position, other in enumerate(rows)
            if position != index
        )
        flags.append(not dominated)
    return flags


def _desirability(values: np.ndarray, direction: str) -> np.ndarray:
    """Min-max map onto [0, 1] with 1 = best; a flat column maps to 0.5."""

    low = float(np.min(values))
    high = float(np.max(values))
    if high - low <= 0.0:
        return np.full(values.shape, 0.5, dtype=float)
    if direction == "min":
        return (high - values) / (high - low)
    return (values - low) / (high - low)


def assign_scores(
    rows: Iterable[Mapping[str, object]],
    keys: Sequence[KeySpec] | None = None,
    *,
    domain_column: str = DOMAIN_COLUMN,
) -> list[float | None]:
    """Weighted score per row, or None for an out-of-domain row.

    The score is set-relative and computed inside the in-domain set, so a rejected row
    cannot shift a kept row's score.  An out-of-domain row gets no number at all: the
    gate removes it, it does not rank it last.
    """

    materialised = list(rows)
    resolved = _resolve_keys(keys)
    if not materialised:
        return []
    in_domain = [_is_in_domain(row, domain_column, _label(row)) for row in materialised]
    kept = [row for row, flag in zip(materialised, in_domain, strict=True) if flag]
    scores: list[float | None] = [None] * len(materialised)
    if not kept:
        return scores
    total = sum(spec.weight for spec in resolved)
    raw = np.zeros(len(kept), dtype=float)
    for spec in resolved:
        column = np.array(
            [_read(row, spec.column, _label(row)) for row in kept],
            dtype=float,
        )
        raw += (spec.weight / total) * _desirability(column, spec.direction)
    position = 0
    for index, flag in enumerate(in_domain):
        if flag:
            scores[index] = float(raw[position])
            position += 1
    return scores


def pareto_front(
    rows: Iterable[Mapping[str, object]],
    keys: Sequence[KeySpec] | None = None,
    *,
    domain_column: str = DOMAIN_COLUMN,
) -> list[Mapping[str, object]]:
    """The non-dominated in-domain subset, in input order.

    Out-of-domain rows are never on the front: the front is the admissible set.
    """

    materialised = list(rows)
    resolved = _resolve_keys(keys)
    flags = _front_flags(materialised, resolved, domain_column)
    return [row for row, flag in zip(materialised, flags, strict=True) if flag]


def ranking_key_table(
    rows: Iterable[Mapping[str, object]],
    keys: Sequence[KeySpec] | None = None,
    *,
    domain_column: str = DOMAIN_COLUMN,
) -> list[dict[str, object]]:
    """Annotate rows with score, on_front, rank, excluded_reason, ranking_channels.

    The order is (-score, name) over the in-domain rows; out-of-domain rows follow in
    name order with score None and rank None, so nothing is hidden and nothing outside
    the domain is silently given a low score.
    """

    materialised = list(rows)
    resolved = _resolve_keys(keys)
    scores = assign_scores(materialised, resolved, domain_column=domain_column)
    flags = _front_flags(materialised, resolved, domain_column)
    channels = "+".join(spec.channel for spec in resolved)
    table: list[dict[str, object]] = []
    for row, score, flag in zip(materialised, scores, flags, strict=True):
        inside = _is_in_domain(row, domain_column, _label(row))
        table.append(
            {
                **dict(row),
                "score": score,
                "on_front": flag,
                "excluded_reason": None if inside else DOMAIN_OUT,
                "ranking_channels": channels,
            }
        )

    def order(entry: Mapping[str, object]) -> tuple[int, float, str]:
        score = entry["score"]
        name = str(entry.get("name", ""))
        if score is None:
            return (1, 0.0, name)
        return (0, -float(score), name)  # type: ignore[arg-type]

    table.sort(key=order)
    rank = 0
    for entry in table:
        if entry["score"] is None:
            entry["rank"] = None
        else:
            rank += 1
            entry["rank"] = rank
    return table


# --------------------------------------------------------------------------- #
# 7. Synthetic fixture -- arbitrary numbers, no chemistry claim
# --------------------------------------------------------------------------- #
#: Six demo rows over the two key dimensions plus the two D1 features.  demo-a and
#: demo-e fall outside D1 (no donor / TPSA below 20) and must receive no score at all;
#: demo-b, demo-c, demo-d and demo-f are in-domain, demo-b dominates demo-f, and the
#: front is {demo-b, demo-c, demo-d}.  The fixture exists so the literal pins in
#: tests/test_w20_ranking_key_v1.py have a fixed object.
EXAMPLE_MOLECULES: tuple[dict[str, object], ...] = (
    {"name": "demo-a", "HOMO_eV": -9.0, "LUMO_eV": 0.0, "NumHDonors": 0, "TPSA": 9.23},
    {"name": "demo-b", "HOMO_eV": -8.0, "LUMO_eV": 1.8, "NumHDonors": 1, "TPSA": 20.23},
    {"name": "demo-c", "HOMO_eV": -6.0, "LUMO_eV": 2.0, "NumHDonors": 2, "TPSA": 40.46},
    {"name": "demo-d", "HOMO_eV": -8.5, "LUMO_eV": 0.6, "NumHDonors": 1, "TPSA": 20.23},
    {"name": "demo-e", "HOMO_eV": -7.0, "LUMO_eV": 1.0, "NumHDonors": 1, "TPSA": 17.07},
    {"name": "demo-f", "HOMO_eV": -7.0, "LUMO_eV": 1.0, "NumHDonors": 1, "TPSA": 20.23},
)


# --------------------------------------------------------------------------- #
# 8. The intersection fill: Tier C features plus model predictions
# --------------------------------------------------------------------------- #
#: Tier C reads a frozen SMILES and writes a predicted reading.  It orders candidates
#: and it never becomes a label: nothing here is written into any pool.
TIER_C_MODEL_TARGETS: dict[str, str] = {"HOMO_eV": "HOMO", "LUMO_eV": "LUMO"}
TIER_C_FEATURE_LAYER = "rdkit_morgan_count_r2_2048+30_descriptors"
DEFAULT_SMILES_PATH = Path("data") / "external" / "Batt-SLM.smi"
DEFAULT_BASELINES_PATH = Path("models") / "homo_lumo_baselines.json"
DEFAULT_CANDIDATE_PATH = Path("probes") / "artifacts" / "w20_ranking_key_v1_candidates.csv"
DEFAULT_SUMMARY_PATH = Path("probes") / "w20_ranking_key_v1_summary.json"
REGISTRY_PATH = Path("data") / "processed" / "four_core_key_registry.csv"
CORE_CHANNELS: tuple[str, ...] = ("dielectric", "viscosity", "orbitals", "liquid_window")
CANDIDATE_COLUMNS: tuple[str, ...] = (
    "inchikey",
    "smiles",
    "canonical_smiles",
    "source_line",
    "NumHDonors",
    "TPSA",
    "HOMO_eV",
    "LUMO_eV",
    "gap_eV",
    "domain",
    "ranking_channels",
    "key_score",
    "rank",
    "on_front",
    "excluded_reason",
    "provenance",
)


def registry_reference_counts(root: Path = REPOSITORY_ROOT) -> dict[str, object]:
    """Re-derive the in-pool comparison numbers from the core key registry."""

    path = root / REGISTRY_PATH
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    two_dimensions = 0
    four_channels = 0
    for row in rows:
        try:
            float(str(row["HOMO_eV"]))
            float(str(row["LUMO_eV"]))
        except (TypeError, ValueError):
            pass
        else:
            two_dimensions += 1
        if int(float(str(row["n_core_channels"]))) >= 4:
            four_channels += 1
    return {
        "path": REGISTRY_PATH.as_posix(),
        "registry_rows": len(rows),
        "rows_with_two_key_dimensions": two_dimensions,
        "rows_with_four_core_channels": four_channels,
    }


def fill_candidates(
    *,
    smiles_path: Path | None = None,
    baselines_path: Path | None = None,
    chunk_size: int = 20000,
    limit: int | None = None,
    root: Path = REPOSITORY_ROOT,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Vectorise the Batt-SLM space onto the key dimensions with the Tier C layer.

    Each candidate leaves with a domain verdict, a traceable provenance string and the
    channel that produced its order.  The predictions order candidates; they are never
    labels and are never written into a pool.
    """

    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors

    from probes import homo_lumo_baselines as hlb

    resolved = _resolve_keys(None)
    unknown = [spec.column for spec in resolved if spec.column not in TIER_C_MODEL_TARGETS]
    if unknown:
        raise ValueError(
            "the Tier C fill only ships predictions for the key dimensions "
            + ", ".join(sorted(TIER_C_MODEL_TARGETS))
            + "; asked for "
            + ", ".join(sorted(unknown))
        )
    targets = [TIER_C_MODEL_TARGETS[spec.column] for spec in resolved]

    smiles_file = Path(smiles_path) if smiles_path is not None else root / DEFAULT_SMILES_PATH
    baselines_file = (
        Path(baselines_path) if baselines_path is not None else root / DEFAULT_BASELINES_PATH
    )
    raw_bytes = smiles_file.read_bytes()
    raw_lines = [
        line.split()[0] for line in raw_bytes.decode("utf-8").splitlines() if line.strip()
    ]
    in_file = len(raw_lines)
    if limit is not None:
        raw_lines = raw_lines[: int(limit)]

    RDLogger.DisableLog("rdApp.*")
    molecules = [Chem.MolFromSmiles(value) for value in raw_lines]
    valid_positions = [index for index, molecule in enumerate(molecules) if molecule is not None]
    invalid_positions = [index for index, molecule in enumerate(molecules) if molecule is None]
    valid_smiles = [raw_lines[index] for index in valid_positions]
    valid_molecules = [molecules[index] for index in valid_positions]
    if not valid_smiles:
        raise ValueError(f"no parsable SMILES in {smiles_file}")

    payload = json.loads(baselines_file.read_text(encoding="utf-8"))
    feature_names = tuple(
        payload["targets"][targets[0]]["feature_variant_detail"]["descriptor_names"]
    )
    for target in targets:
        names = tuple(payload["targets"][target]["feature_variant_detail"]["descriptor_names"])
        if names != feature_names:
            raise ValueError(
                "the Tier C targets do not share one feature block: " + target
            )
    models = hlb.load_target_models(payload, root)

    predictions = {target: np.zeros(len(valid_smiles), dtype=float) for target in targets}
    for start in range(0, len(valid_smiles), int(chunk_size)):
        stop = min(start + int(chunk_size), len(valid_smiles))
        features = hlb.featurize_smiles(valid_smiles[start:stop], feature_names)
        for target in targets:
            predictions[target][start:stop] = np.asarray(
                models[target].predict(features), dtype=float
            )

    donors = [float(Descriptors.NumHDonors(molecule)) for molecule in valid_molecules]
    tpsa = [float(Descriptors.TPSA(molecule)) for molecule in valid_molecules]
    canonical = [Chem.MolToSmiles(molecule) for molecule in valid_molecules]
    inchikeys = [Chem.MolToInchiKey(molecule) for molecule in valid_molecules]

    rows: list[dict[str, object]] = []
    for position, source_index in enumerate(valid_positions):
        homo = float(predictions["HOMO"][position])
        lumo = float(predictions["LUMO"][position])
        rows.append(
            {
                "name": inchikeys[position],
                "smiles": valid_smiles[position],
                "canonical_smiles": canonical[position],
                "inchikey": inchikeys[position],
                "source_line": source_index + 1,
                "NumHDonors": donors[position],
                "TPSA": tpsa[position],
                "HOMO_eV": homo,
                "LUMO_eV": lumo,
                "gap_eV": lumo - homo,
            }
        )
    rows = annotate_domains(rows)

    artifacts = ";".join(
        target
        + "="
        + str(payload["targets"][target]["model"]["artifact"]["path"])
        + "@"
        + str(payload["targets"][target]["model"]["artifact"]["sha256"])[:12]
        for target in targets
    )
    provenance = (
        "tier_c|features="
        + TIER_C_FEATURE_LAYER
        + "|prediction="
        + artifacts
        + "|domain="
        + D1_RULE
        + "|ranking_channel=orbitals"
    )
    for row in rows:
        row["provenance"] = provenance

    table = ranking_key_table(rows, resolved)
    in_domain = sum(1 for entry in table if entry["excluded_reason"] is None)
    unique_keys = len({str(entry["inchikey"]) for entry in table})
    top = [
        {
            "rank": entry["rank"],
            "inchikey": entry["inchikey"],
            "smiles": entry["smiles"],
            "HOMO_eV": round(float(entry["HOMO_eV"]), 6),
            "LUMO_eV": round(float(entry["LUMO_eV"]), 6),
            "key_score": round(float(entry["score"]), 6),
        }
        for entry in table
        if entry["excluded_reason"] is None
    ][:20]
    counts: dict[str, object] = {
        "smiles_file": smiles_file.relative_to(root).as_posix(),
        "smiles_file_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "candidates_in_file": in_file,
        "candidates_read": len(raw_lines),
        "limit_applied": limit,
        "smiles_parsed": len(valid_smiles),
        "smiles_invalid": len(invalid_positions),
        "invalid_source_lines": [index + 1 for index in invalid_positions[:5]],
        "unique_inchikey": unique_keys,
        "duplicate_inchikey_rows": len(valid_smiles) - unique_keys,
        "in_domain": in_domain,
        "out_of_domain": len(table) - in_domain,
        "out_of_domain_share": (len(table) - in_domain) / len(table) if table else 0.0,
        "key_dimensions": [spec.column for spec in resolved],
        "key_dimensions_per_candidate": len(resolved),
        "core_channels_filled": ["orbitals"],
        "core_channels_not_filled": [
            channel for channel in CORE_CHANNELS if channel != "orbitals"
        ],
        "scoreable_on_key_dimensions_rows": in_domain,
        "scoreable_on_core_channels": 1,
        "front_size": sum(1 for entry in table if entry["on_front"]),
        "top_20": top,
    }
    return table, counts


def _csv_row(entry: Mapping[str, object]) -> dict[str, str]:
    def number(value: object, digits: int) -> str:
        return "" if value is None else f"{float(value):.{digits}f}"  # type: ignore[arg-type]

    return {
        "inchikey": str(entry["inchikey"]),
        "smiles": str(entry["smiles"]),
        "canonical_smiles": str(entry["canonical_smiles"]),
        "source_line": str(entry["source_line"]),
        "NumHDonors": f"{float(entry['NumHDonors']):.0f}",  # type: ignore[arg-type]
        "TPSA": f"{float(entry['TPSA']):.4f}",  # type: ignore[arg-type]
        "HOMO_eV": f"{float(entry['HOMO_eV']):.6f}",  # type: ignore[arg-type]
        "LUMO_eV": f"{float(entry['LUMO_eV']):.6f}",  # type: ignore[arg-type]
        "gap_eV": f"{float(entry['gap_eV']):.6f}",  # type: ignore[arg-type]
        "domain": str(entry["domain"]),
        "ranking_channels": str(entry["ranking_channels"]),
        "key_score": number(entry["score"], 6),
        "rank": "" if entry["rank"] is None else str(entry["rank"]),
        "on_front": "true" if entry["on_front"] else "false",
        "excluded_reason": (
            "" if entry["excluded_reason"] is None else str(entry["excluded_reason"])
        ),
        "provenance": str(entry["provenance"]),
    }


def write_candidate_csv(
    path: Path,
    table: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Write the candidate list as LF / UTF-8 / no BOM and report its digest."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CANDIDATE_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for entry in table:
            writer.writerow(_csv_row(entry))
    payload = path.read_bytes()
    return {
        "path": path.as_posix(),
        "bytes": len(payload),
        "rows": len(table),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "columns": list(CANDIDATE_COLUMNS),
    }


PREREG_PATH = Path("probes") / "w20_ranking_key_v1_prereg.json"


def file_sha256(path: Path) -> str:
    """Digest a file without loading it twice into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_summary(
    *,
    counts: Mapping[str, object],
    artifact: Mapping[str, object],
    root: Path = REPOSITORY_ROOT,
) -> dict[str, object]:
    """Assemble the run summary; every field is either measured or declared above."""

    return {
        "schema_version": 1,
        "task": "week20_w20_3_ranking_key_v1",
        "section": "28.59",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "position": POSITION_STATEMENT,
        "position_en": "this is a ranking key, not a candidate generator",
        "key": {
            "gated_channels": list(GATED_CHANNELS),
            "eligible_channels": list(ELIGIBLE_CHANNELS),
            "dimensions": [
                {
                    "channel": spec.channel,
                    "column": spec.column,
                    "direction": spec.direction,
                    "weight": spec.weight,
                }
                for spec in DEFAULT_KEYS
            ],
            "weights": DEFAULT_WEIGHTS,
            "weights_source": PREREG_WEIGHTS_SOURCE,
        },
        "dedup": {
            "kept_columns": list(DEDUP_KEPT_COLUMNS),
            "dropped_columns": list(DEDUP_DROPPED_COLUMNS),
            "collinearity": [dict(record) for record in COLLINEARITY_RECORD],
        },
        "extension_status": {
            channel: dict(record) for channel, record in CHANNEL_EXTENSION_STATUS.items()
        },
        "domain": {
            "rule": D1_RULE,
            "high_permittivity_eps": HIGH_PERMITTIVITY_EPS,
            "out_of_domain_policy": "no score, no rank, never on the front",
            "scoreboard": dict(DOMAIN_SCOREBOARD),
        },
        "preregistration": {
            "path": PREREG_PATH.as_posix(),
            "sha256": file_sha256(root / PREREG_PATH),
            "status": "locked_before_run",
        },
        "extension_verdict_scan_at_run": scan_extension_verdicts(root),
        "registry_reference": registry_reference_counts(root),
        "fill": dict(counts),
        "candidate_artifact": dict(artifact),
        "discipline": {
            "promoted": False,
            "main_scoreboard_attempts_this_week": 0,
            "main_scoreboard_attempts_cumulative": 11,
            "frozen_baseline": 0.4091179943351143,
            "frozen_headline": 0.4766400383507876,
            "predictions_written_to_any_pool": False,
            "generation_loop": "welded_shut (uniqueness 0.349 on record)",
            "reaxys_values_used": False,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="W20-3 ranking key v1 + intersection fill")
    parser.add_argument("--print-example", action="store_true")
    parser.add_argument("--check-extensions", action="store_true")
    parser.add_argument("--smiles", type=Path, default=None)
    parser.add_argument("--baselines", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--chunk-size", type=int, default=20000)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    if args.print_example:
        for entry in ranking_key_table(annotate_domains(EXAMPLE_MOLECULES)):
            print(
                entry["rank"],
                entry["name"],
                entry["score"],
                entry["on_front"],
                entry["excluded_reason"],
            )
        return 0

    assert_no_unregistered_verdicts()

    if args.check_extensions:
        print(json.dumps(scan_extension_verdicts(), ensure_ascii=False, indent=2))
        return 0

    table, counts = fill_candidates(
        smiles_path=args.smiles,
        baselines_path=args.baselines,
        chunk_size=args.chunk_size,
        limit=args.limit,
    )
    output = args.output if args.output is not None else REPOSITORY_ROOT / DEFAULT_CANDIDATE_PATH
    summary_path = args.summary if args.summary is not None else REPOSITORY_ROOT / DEFAULT_SUMMARY_PATH
    artifact = write_candidate_csv(output, table)
    summary = build_summary(counts=counts, artifact=artifact)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    # LF only: Windows text mode would translate '\n' into CRLF and trip the
    # repository hygiene gate, so the handle pins newline explicitly.
    write_json_stable(summary_path, summary)
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    raise SystemExit(main())
