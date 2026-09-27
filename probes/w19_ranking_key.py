"""Week 19 -- D6: the multi-objective ranking key (spec v0) as pure functions.

This module is the executable half of 'reports/w19_ranking_key_spec.md'.  It is a
ranking key, not a candidate generator: it consumes molecular-level readings that
already exist for **gated channels only** and returns

* a strict Pareto domination verdict (dominates);
* the non-dominated front (pareto_front);
* a weighted ranking-key score (assign_scores / ranking_key_table).

Four properties are structural rather than editorial:

1. CHANNEL_GATE_STATUS carries, for every core channel, the gate criterion, the
   measured value and the owning artefact.  'passed' is derived from 'measured'
   and 'gate' at import time, so this module cannot drift away from the record it
   cites.
2. validate_keys refuses any key set that names an ungated channel, that names
   one input column twice, or whose weights do not sum to one.  The v0 default
   key is validated at import, so an ungated channel cannot enter it silently.
3. The course of the key is a declared convention: a deeper HOMO (harder to
   oxidise) and a higher LUMO (harder to reduce) is better, i.e. a wider
   electrochemical stability window.  Directions live in KeySpec.direction and
   changing them is a preregistration change, not a code change.
4. Nothing here fits a model, reads a table or writes a file.  The bundled
   example fixture is synthetic and labelled as such.

Scores are set-relative: desirabilities are min-max mapped inside the scored row
set, so a score orders the rows it was computed on.  It is never a predicted
property value and never a substitute for the Pareto front.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

__all__ = [
    "CHANNEL_GATE_STATUS",
    "DEFAULT_KEYS",
    "DEFAULT_WEIGHTS",
    "EXAMPLE_MOLECULES",
    "GATED_CHANNELS",
    "HIGH_PERMITTIVITY_EPS",
    "KeySpec",
    "assign_scores",
    "dominates",
    "high_permittivity_excluded",
    "pareto_front",
    "ranking_key_table",
    "validate_keys",
]

# --------------------------------------------------------------------------- #
# 1. Gate status of the six core channels, re-read 2026-09-28 (W19 D6)
# --------------------------------------------------------------------------- #
# Every core gate is one-sided and carries its own side: 'pass_when' is
# 'below' for an error metric (MAE: measured < gate) and 'above' for a
# quality metric (R2: measured >= gate).  'passed' is derived, never typed.
_GATE_DECLARATIONS: dict[str, dict[str, object]] = {
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


def _derive_gate_status() -> dict[str, dict[str, object]]:
    """Return the declarations with 'passed' recomputed from 'measured'.

    The recomputation is the guard: a gate row whose recorded value does not
    satisfy its own rule cannot be smuggled in by editing prose.
    """

    status: dict[str, dict[str, object]] = {}
    for channel, record in _GATE_DECLARATIONS.items():
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


CHANNEL_GATE_STATUS: dict[str, dict[str, object]] = _derive_gate_status()
GATED_CHANNELS: tuple[str, ...] = tuple(
    channel for channel, record in CHANNEL_GATE_STATUS.items() if record["passed"]
)

# --------------------------------------------------------------------------- #
# 2. The failure zone the key must never rank through
# --------------------------------------------------------------------------- #
#: The epsilon > 60 zone is unsolved under single-molecule descriptors: the
#: Onsager prior crosses 60 for 0 of the 5 high-permittivity compounds and the
#: delta-learning headline arm still carries MAE 75.95675695251926 there
#: (probes/dielectric_onsager_delta_summary.json).
HIGH_PERMITTIVITY_EPS = 60.0


def high_permittivity_excluded(epsilon: float | None) -> bool:
    """True when a permittivity reading falls in the declared failure zone."""

    if epsilon is None:
        return False
    return float(epsilon) > HIGH_PERMITTIVITY_EPS


# --------------------------------------------------------------------------- #
# 3. The v0 key: gated channels only, weights explicit and normalised
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class KeySpec:
    """One channel of the ranking key.

    'direction' is the *better* direction: "min" means lower is better.
    'weight' is the explicit share of the score; the weights of a key set must
    sum to one.
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


#: v0 equal weighting over the two gated orbital channels.  Equal weights are the
#: only non-arbitrary choice while there is no measured cost ratio between the
#: two channels; any change here must be re-pinned in the preregistration.
DEFAULT_KEYS: tuple[KeySpec, ...] = (
    KeySpec(channel="homo", column="HOMO_eV", direction="min", weight=0.5),
    KeySpec(channel="lumo", column="LUMO_eV", direction="max", weight=0.5),
)
DEFAULT_WEIGHTS: dict[str, float] = {spec.channel: spec.weight for spec in DEFAULT_KEYS}


def validate_keys(keys: Sequence[KeySpec]) -> None:
    """Refuse a key set that is ungated, ambiguous or unnormalised."""

    if not keys:
        raise ValueError("the ranking key must name at least one channel")
    ungated: list[str] = []
    for spec in keys:
        record = CHANNEL_GATE_STATUS.get(spec.channel)
        if record is None:
            raise ValueError(f"unknown channel {spec.channel!r}")
        if not record["passed"]:
            ungated.append(spec.channel)
    if ungated:
        raise ValueError(
            "the ranking key may only contain gated channels; ungated: "
            + ", ".join(sorted(ungated))
        )
    columns = [spec.column for spec in keys]
    if len(set(columns)) != len(columns):
        raise ValueError("two key entries share one input column")
    total = sum(spec.weight for spec in keys)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"the key weights must sum to one, got {total!r}")


validate_keys(DEFAULT_KEYS)

# --------------------------------------------------------------------------- #
# 4. Pure ranking primitives
# --------------------------------------------------------------------------- #
def _label(row: Mapping[str, object]) -> str:
    return str(row.get("name", "?"))


def _require_finite(value: object, column: str, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label}: column {column!r} is not a number ({value!r})") from error
    if not np.isfinite(number):
        raise ValueError(f"{label}: column {column!r} is not finite ({value!r})")
    return number


def _read(row: Mapping[str, object], column: str, label: str) -> float:
    """Read one key column, refusing a missing or non-finite entry."""

    if column not in row:
        raise ValueError(f"{label}: column {column!r} is missing")
    return _require_finite(row[column], column, label)


def _strictly_better(first: float, second: float, direction: str) -> bool:
    if direction == "min":
        return first < second
    if direction == "max":
        return first > second
    raise ValueError(f"unknown direction {direction!r}")


def _resolve_keys(keys: Sequence[KeySpec] | None) -> Sequence[KeySpec]:
    resolved = DEFAULT_KEYS if keys is None else keys
    validate_keys(resolved)
    return resolved


def dominates(
    row: Mapping[str, object],
    other: Mapping[str, object],
    keys: Sequence[KeySpec] | None = None,
) -> bool:
    """Strict Pareto dominance on the declared key directions.

    'row' dominates 'other' when it is never worse on any key and strictly better
    on at least one.  Equal key vectors therefore do not dominate each other:
    ties are non-dominating by definition.
    """

    resolved = _resolve_keys(keys)
    strictly_better = False
    for spec in resolved:
        mine = _read(row, spec.column, _label(row))
        theirs = _read(other, spec.column, _label(other))
        if _strictly_better(theirs, mine, spec.direction):
            return False
        if _strictly_better(mine, theirs, spec.direction):
            strictly_better = True
    return strictly_better


def _front_flags(
    rows: Sequence[Mapping[str, object]],
    keys: Sequence[KeySpec],
) -> list[bool]:
    flags: list[bool] = []
    for index, row in enumerate(rows):
        flags.append(
            not any(
                dominates(other, row, keys)
                for position, other in enumerate(rows)
                if position != index
            )
        )
    return flags


def pareto_front(
    rows: Iterable[Mapping[str, object]],
    keys: Sequence[KeySpec] | None = None,
) -> list[Mapping[str, object]]:
    """The non-dominated subset, in input order.

    Ties stay on the front: two rows with identical key vectors do not dominate
    each other and both are reported.
    """

    materialised = list(rows)
    resolved = _resolve_keys(keys)
    flags = _front_flags(materialised, resolved)
    return [row for row, flag in zip(materialised, flags, strict=True) if flag]


def _desirability(values: np.ndarray, direction: str) -> np.ndarray:
    """Min-max map a column onto [0, 1] with 1 = best; a flat column maps to 0.5."""

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
) -> list[float]:
    """Weighted ranking-key score per row, in input order.

    The score is set-relative: it orders the rows it was computed on and is not a
    property value.  A row whose column is missing or non-finite is refused
    rather than silently ranked.
    """

    materialised = list(rows)
    resolved = _resolve_keys(keys)
    if not materialised:
        return []
    total = sum(spec.weight for spec in resolved)
    score = np.zeros(len(materialised), dtype=float)
    for spec in resolved:
        column = np.array(
            [
                _read(row, spec.column, _label(row))
                for row in materialised
            ],
            dtype=float,
        )
        score += (spec.weight / total) * _desirability(column, spec.direction)
    return [float(value) for value in score]


def ranking_key_table(
    rows: Iterable[Mapping[str, object]],
    keys: Sequence[KeySpec] | None = None,
) -> list[dict[str, object]]:
    """Annotate the rows with 'score', 'on_front' and a 1-based 'rank'.

    The returned list is already sorted by (-score, name); that order *is* the
    ranking.  Dominated rows stay in the table, flagged on_front=False, so
    nothing is hidden: the front is the admissible set and the score only orders
    it.
    """

    materialised = list(rows)
    resolved = _resolve_keys(keys)
    scores = assign_scores(materialised, resolved)
    flags = _front_flags(materialised, resolved)
    table: list[dict[str, object]] = [
        {**dict(row), "score": score, "on_front": flag}
        for row, score, flag in zip(materialised, scores, flags, strict=True)
    ]
    table.sort(key=lambda entry: (-float(entry["score"]), str(entry.get("name", ""))))
    for position, entry in enumerate(table, start=1):
        entry["rank"] = position
    return table


# --------------------------------------------------------------------------- #
# 5. Synthetic fixture -- arbitrary numbers, no chemistry claim
# --------------------------------------------------------------------------- #
#: Five demo rows over the two gated channels.  demo-x / demo-z trade the two
#: objectives against each other, demo-y and demo-v are an exact tie, and demo-w
#: is dominated by both members of that tie.  The fixture exists so that the
#: literal pins in tests/test_w19_ranking_key.py have a fixed object.
EXAMPLE_MOLECULES: tuple[dict[str, object], ...] = (
    {"name": "demo-x", "HOMO_eV": -9.0, "LUMO_eV": 0.0},
    {"name": "demo-y", "HOMO_eV": -8.0, "LUMO_eV": 1.8},
    {"name": "demo-z", "HOMO_eV": -6.0, "LUMO_eV": 2.0},
    {"name": "demo-v", "HOMO_eV": -8.0, "LUMO_eV": 1.8},
    {"name": "demo-w", "HOMO_eV": -7.0, "LUMO_eV": 1.0},
)


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    print("gated channels:", GATED_CHANNELS)
    for entry in ranking_key_table(EXAMPLE_MOLECULES):
        print(entry["rank"], entry["name"], entry["score"], entry["on_front"])
