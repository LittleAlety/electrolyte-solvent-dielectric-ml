"""Week 20 -- W20-2 Step 1: does the liquid-window filter move the ranking head?

Skeleton. Registered, NOT executed: this module fits no model, reads no
prediction table, takes no shot number and never touches the main scoreboard.
What it fixes today is the interface of the W20-2 Step-1 influence ablation, so
that the preregistration has a concrete object to freeze.

Why the interface must be pinned before anything is scored
----------------------------------------------------------
W19 registered a fourth (safety) channel -- flash point, boiling point, melting
point and the liquid window they jointly imply -- and measured its coverage
against two different key sets.  Both readings are on record and they disagree,
because "the safety channel" is not one object:

    key set                  v03 roster (246)   v01 (957)    v02 (1228)
    registry channel (218)   181 = 0.7358       158 = 0.1651  156 = 0.1270
    feature table  (314)     246 = 1.0000       160 = 0.1672  202 = 0.1645

Against the 0.30 gate the epsilon side passes and the eta side fails under both
key sets, so the conclusion is choice-independent while the number is not.
SAFETY_KEY_SET is therefore a preregistration field, not a default.

The scored universe has the same problem.  Measured read-only in this repository
on 2026-09-28:

    universe                                       rows    role
    registry rows, orbitals channel                29,868
    registry rows, orbitals + finite HOMO/LUMO     29,519  arm0, registry
    registry rows carrying liquid_window              218  arm1 key set
    registry rows, orbital channel AND liquid          75  flags only
    registry rows, scoreable AND liquid                70  arm1 pool, registry
    v03 roster                                        246
    v03 roster, orbitals channel                       83
    v03 roster, orbitals + finite HOMO/LUMO            78  arm0, roster
    v03 roster, liquid_window                         181  arm1 key set, roster
    v03 roster, orbital channel AND liquid             69  flags only
    v03 roster, scoreable AND liquid                   64  arm1 pool, roster

Two pairs of numbers need separating.  Orbital channel AND liquid counts the
channels_present flags; scoreable AND liquid additionally requires a finite
HOMO and LUMO, which is what the key actually needs.  The flags-only pair is
75 / 69; the scoreable pair, which is the one the arms use, is 70 / 64.  Both
are on this table on purpose, because quoting 181 -- the arm1 key set -- as if
it were the arm1 pool is exactly the error the design has to avoid.

The scoreable pair decides the design: whichever universe is chosen, a
liquid-window filter leaves 64-70 scoreable rows, not 181.  A filter that leaves
about seventy rows is a shortlist, not a filter, and the arm must report that
rather than quote 181.  This is the W20-2 Step-1 finding already on the record;
W20-2 Step 2 (model the channel) depends on it.

The preregistered hypothesis
----------------------------
H1, fixed before any number is produced: restricting the scored universe to rows
that carry a measured liquid window improves head purity at the pinned k.  The
wording is directional so the arm can fail; a refutation is a result, not a bug.

What purity is measured against
-------------------------------
Purity needs a reference set, and this skeleton refuses to invent one.
RECOMMENDED_SET_PATH was left None while the module was only registered; the W20-2
Step-1 preregistration pinned it on 2026-09-28, and run() still refuses to score
while it is unset.  That keeps a purity number from being defined after it has been
seen.

Pinned at W20-2 Step 1 (2026-09-28, section 28.58)
-------------------------------------------------
Three fields stopped being defaults the moment this lane was executed:

    SAFETY_KEY_SET       registry_liquid_window_channel
    SCORED_UNIVERSE      registry_wide
    RECOMMENDED_SET_PATH data/dielectric_v03.csv

The pinned key set is the one the charter coverage table was measured with (218
keys: 181/246 = 0.7358, 158/957 = 0.1651, 156/1228 = 0.1270), so the gate verdict
and the ablation talk about the same object.  The pinned universe is the whole
orbital-scorable registry (29,519 rows), because the reference set has to be a
proper subset of the scored pool for purity to mean anything: on the roster
universe the pool would sit inside its own reference and every purity would be 1.0.

The reference set is the frozen epsilon roster -- the 246 compounds carrying a
measured dielectric constant -- so a hit is a head member the epsilon channel
already owns.  Its role is recorded in REFERENCE_ROLE.  Two properties of that
choice have to be reported rather than enjoyed:

* the reference density is not the same on the two arms.  It is 78/29,519 =
  0.00264 on arm0 and 64/70 = 0.9143 on arm1, so a purity rise is expected from
  containment alone.  run() therefore reports the density and the lift next to the
  raw purity, and the placebo holds the filter cardinality fixed so the
  containment baseline is measured rather than assumed;
* 181 of the 218 safety keys sit inside the epsilon roster (0.8303), which is why
  the containment is large.  The ablation measures how far the head moves; it does
  not claim the safety channel carries independent ranking information.

Change log against the registered skeleton
------------------------------------------
Only the three pins above, the two additive fields (reference density and lift),
the coverage recomputation, the CLI default for --recommended-set and the
discipline flags changed.  The arms, the key, the purity definition, the placebo
construction and blocking_conditions are untouched.  One flag is deliberately
different: run() reports produces_reading = false next to
produces_ablation_numbers = true, because W20-2 Step 1 fits no model, takes no
shot number and produces no channel reading -- it produces ablation numbers.  The
registered skeleton flipped that flag to true on execution; the lane
specification for section 28.58 pins it false, and the W19 read-only precedent
(probes/w19_batt_direct_hit_summary.json) records a read-only lane the same way.

The W20-2 Step-1 gap fill (same day, same section 28.58) added one additive
output: arms_csv_rows() projects the executed summary into
probes/artifacts/w20_safety_ablation_arms.csv and main() writes it behind
--write-arms-csv.  run() is byte-for-byte unchanged, so the summary and every
number recorded above keep their value; only this file digest moves.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from electrolyte_ml.pathing import portable_relative_path
from probes.w19_ranking_key import DEFAULT_KEYS, ranking_key_table

REGISTRY_PATH = REPOSITORY_ROOT / "data" / "processed" / "four_core_key_registry.csv"
LIQUID_WINDOW_PATH = REPOSITORY_ROOT / "data" / "processed" / "liquid_window_features.csv"
V03_ROSTER_PATH = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "w20_safety_ablation_summary.json"
PREREG_PATH = REPOSITORY_ROOT / "probes" / "w20_safety_ablation_prereg.json"
ARMS_CSV_PATH = REPOSITORY_ROOT / "probes" / "artifacts" / "w20_safety_ablation_arms.csv"

#: The two admissible definitions of "the safety channel key set".  They are
#: different objects and give different coverage, so the preregistration picks
#: one; run() refuses while SAFETY_KEY_SET is None.
REGISTRY_CHANNEL = "registry_liquid_window_channel"
FEATURE_TABLE = "liquid_window_feature_table"
SAFETY_KEY_SET: str | None = REGISTRY_CHANNEL

#: The two admissible scored universes.
ROSTER_UNIVERSE = "dielectric_v03_roster"
REGISTRY_UNIVERSE = "registry_wide"
SCORED_UNIVERSE: str | None = REGISTRY_UNIVERSE

COVERAGE_GATE = 0.30

#: Read-only readings taken 2026-09-28.  Recorded here so the arm cannot quote a
#: different pair of numbers later.
COVERAGE_READINGS: dict[str, dict[str, object]] = {
    REGISTRY_CHANNEL: {
        "key_count": 218,
        "denominators": {"v03": 246, "v01": 957, "v02": 1228},
        "covered": {"v03": 181, "v01": 158, "v02": 156},
    },
    FEATURE_TABLE: {
        "key_count": 314,
        "denominators": {"v03": 246, "v01": 957, "v02": 1228},
        "covered": {"v03": 246, "v01": 160, "v02": 202},
    },
}

#: The same read-only pass, as pool sizes rather than coverage fractions.
#: orbital_channel counts the channels_present flag; orbital_scorable
#: additionally requires a finite HOMO and LUMO, which is what the key needs.
UNIVERSE_READINGS: dict[str, int] = {
    "registry_orbital_channel": 29868,
    "registry_orbital_scorable": 29519,
    "registry_liquid_window": 218,
    "registry_orbital_channel_and_liquid_window": 75,
    "registry_orbital_scorable_and_liquid_window": 70,
    "v03_roster": 246,
    "v03_roster_orbital_channel": 83,
    "v03_roster_orbital_scorable": 78,
    "v03_roster_liquid_window": 181,
    "v03_roster_orbital_channel_and_liquid_window": 69,
    "v03_roster_orbital_scorable_and_liquid_window": 64,
}

#: Pinned before the shot: the head sizes, and the placebo that destroys the
#: filter content while keeping its cardinality.
TOP_K_VALUES: tuple[int, ...] = (10, 20, 50)
PLACEBO_PERMUTATIONS = 200
PLACEBO_SEED = 20260928

#: The reference set a purity number is measured against.  None until the
#: preregistration pins the set together with its provenance.
RECOMMENDED_SET_PATH: Path | None = REPOSITORY_ROOT / "data" / "dielectric_v03.csv"

#: What a purity number is measured against, and what counts as a hit.  Written
#: down because a purity number is only as meaningful as its reference set.
REFERENCE_ROLE = (
    "the frozen epsilon v03 roster: the 246 compounds carrying a measured "
    "dielectric constant.  A hit is a head member the epsilon channel already "
    "owns, so head purity reads as the share of the shortlist the epsilon side "
    "can already speak for."
)


@dataclass(frozen=True)
class ArmSpec:
    """One arm of the ablation: the v0 key, over a possibly restricted pool."""

    name: str
    restrict_to_liquid_window: bool
    hypothesis: str


ARMS: tuple[ArmSpec, ...] = (
    ArmSpec(
        name="arm0_v0_unfiltered",
        restrict_to_liquid_window=False,
        hypothesis="comparator: the v0 key over every scorable row",
    ),
    ArmSpec(
        name="arm1_v0_liquid_window",
        restrict_to_liquid_window=True,
        hypothesis="H1: restricting to liquid-window rows improves head purity at k",
    ),
)


#: The three frozen target rosters the charter coverage table quotes.
TARGET_ROSTERS: dict[str, Path] = {
    "v03": V03_ROSTER_PATH,
    "v01": REPOSITORY_ROOT / "data" / "viscosity_v01.csv",
    "v02": REPOSITORY_ROOT / "data" / "viscosity_v02.csv",
}


def coverage_table(
    keys: set[str],
    *,
    rosters: Mapping[str, Path] = TARGET_ROSTERS,
) -> dict[str, dict[str, object]]:
    """Recompute the coverage gate for every pinned target roster.

    covered / denominator per roster, plus the gate verdict at COVERAGE_GATE.  The
    numbers this returns are the ones COVERAGE_READINGS froze; run() checks that
    they agree, so the quoted table cannot drift away from the artifact.
    """

    table: dict[str, dict[str, object]] = {}
    for name, path in rosters.items():
        target = roster_key_set(read_csv_rows(path))
        covered = len(target & keys)
        denominator = len(target)
        fraction = covered / denominator if denominator else 0.0
        table[name] = {
            "roster": portable_relative_path(path, root=REPOSITORY_ROOT),
            "target_keys": denominator,
            "covered_keys": covered,
            "coverage_fraction": fraction,
            "gate": COVERAGE_GATE,
            "passed": fraction >= COVERAGE_GATE,
        }
    return table


def coverage_verdicts() -> dict[str, dict[str, object]]:
    """The gate verdict per target roster, derived from the frozen readings."""

    frozen = COVERAGE_READINGS[SAFETY_KEY_SET]
    verdicts: dict[str, dict[str, object]] = {}
    for roster, denominator in frozen["denominators"].items():
        covered = frozen["covered"][roster]
        fraction = covered / denominator
        verdicts[roster] = {
            "covered_keys": covered,
            "target_keys": denominator,
            "coverage_fraction": fraction,
            "gate": COVERAGE_GATE,
            "passed": fraction >= COVERAGE_GATE,
        }
    return verdicts


def check_coverage_against_readings(
    keys: set[str],
    table: Mapping[str, Mapping[str, object]],
) -> None:
    """Refuse to quote a coverage table that no longer matches the frozen one."""

    frozen = COVERAGE_READINGS[SAFETY_KEY_SET]
    if len(keys) != frozen["key_count"]:
        raise SystemExit(
            f"the safety key set moved: {len(keys)} keys vs the pinned "
            f"{frozen['key_count']}"
        )
    for roster, denominator in frozen["denominators"].items():
        covered = frozen["covered"][roster]
        row = table[roster]
        if row["target_keys"] != denominator or row["covered_keys"] != covered:
            raise SystemExit(
                f"the coverage table moved for {roster}: "
                f"{row['covered_keys']}/{row['target_keys']} vs the pinned "
                f"{covered}/{denominator}"
            )


def input_digests(paths: Iterable[Path]) -> dict[str, dict[str, object]]:
    """Byte size and sha256 of every input the pins depend on."""

    digests: dict[str, dict[str, object]] = {}
    for path in paths:
        raw = Path(path).read_bytes()
        digests[portable_relative_path(path, root=REPOSITORY_ROOT)] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    return digests


def prereg_reference(path: Path = PREREG_PATH) -> dict[str, object] | None:
    """Where the frozen registration is, and its digest, once it exists."""

    if not Path(path).is_file():
        return None
    raw = Path(path).read_bytes()
    return {
        "path": portable_relative_path(path, root=REPOSITORY_ROOT),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def prereg_summary(*, locked_at_utc: str) -> dict[str, object]:
    """The frozen registration: the pins, the blockers and the input digests."""

    pinned_inputs: list[Path] = [
        REGISTRY_PATH,
        LIQUID_WINDOW_PATH,
        V03_ROSTER_PATH,
        TARGET_ROSTERS["v01"],
        TARGET_ROSTERS["v02"],
    ]
    if RECOMMENDED_SET_PATH is not None:
        pinned_inputs.append(RECOMMENDED_SET_PATH)
    return {
        **plan(),
        "status": "locked_before_run",
        "prereg_status": "locked_before_run",
        "locked_at_utc": locked_at_utc,
        "authority": [
            "reports/week20_project_charter.md::section 1 W20-2",
            "reports/week20_project_charter.md::section 5",
            "reports/week20_project_charter.md::section 7",
        ],
        "inputs": input_digests(pinned_inputs),
        "blocking_conditions_at_lock": blocking_conditions(),
    }

def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def channel_present(row: Mapping[str, str], channel: str) -> bool:
    """Membership in channels_present, the column this file reads membership from.

    The registered skeleton justified this by claiming the per-channel has_*
    columns read as false under csv.DictReader.  That justification was measured
    on 2026-09-28 and does not hold: for all six channels the has_* column agrees
    with channels_present on every one of the 31,949 rows (zero mismatches;
    has_liquid_window is true on exactly the 218 rows that name liquid_window).
    Behaviour is unchanged -- both readings give the same key set -- but the
    reason is now the tested one: channels_present is the column
    probes/build_four_core_registry.py writes at line 496, and it is what
    UNIVERSE_READINGS was measured with.
    """

    return channel in (row.get("channels_present") or "").split("|")


def is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def scorable_rows(rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    """Rows the v0 key can score: the whole orbital block present and finite."""

    columns = [spec.column for spec in DEFAULT_KEYS]
    return [
        dict(row)
        for row in rows
        if channel_present(row, "orbitals")
        and all(is_finite_number(row.get(column)) for column in columns)
    ]


def safety_key_set(
    source: str | None,
    registry_rows: Iterable[Mapping[str, str]],
    feature_rows: Iterable[Mapping[str, str]],
) -> set[str]:
    """The key set the preregistration named, and nothing else."""

    if source == REGISTRY_CHANNEL:
        return {
            str(row["inchikey"])
            for row in registry_rows
            if channel_present(row, "liquid_window")
        }
    if source == FEATURE_TABLE:
        return {str(row["inchikey"]) for row in feature_rows if row.get("inchikey")}
    raise ValueError(
        f"unknown safety key set: {source!r} (expected one of the two pinned names)"
    )


def roster_key_set(rows: Iterable[Mapping[str, str]]) -> set[str]:
    return {str(row["inchikey"]) for row in rows if row.get("inchikey")}


def score_pool(
    registry_rows: Iterable[Mapping[str, str]],
    *,
    universe: str | None,
    roster_keys: set[str],
) -> list[dict[str, str]]:
    """The scored universe, as named by the preregistration."""

    rows = scorable_rows(registry_rows)
    if universe == REGISTRY_UNIVERSE:
        return rows
    if universe == ROSTER_UNIVERSE:
        return [row for row in rows if str(row["inchikey"]) in roster_keys]
    raise ValueError(f"unknown scored universe: {universe!r}")


def top_k_keys(table: Sequence[Mapping[str, object]], k: int) -> list[str]:
    if k <= 0:
        raise ValueError(f"k must be positive, got {k!r}")
    return [str(entry["inchikey"]) for entry in table[:k]]


def jaccard(first: Iterable[str], second: Iterable[str]) -> float:
    left, right = set(first), set(second)
    union = left | right
    return 0.0 if not union else len(left & right) / len(union)


def head_retention(arm0_head: Sequence[str], arm1_head: Sequence[str]) -> float:
    """Share of the arm0 head kept by arm1.  Position-insensitive on purpose."""

    base = set(arm0_head)
    if not base:
        raise ValueError("the arm0 head is empty; there is nothing to retain")
    return len(base & set(arm1_head)) / len(base)


def purity(head: Sequence[str], reference: Iterable[str]) -> float:
    if not head:
        raise ValueError("an empty head has no purity")
    return len(set(head) & set(reference)) / len(head)


def placebo_key_sets(
    scorable_keys: Sequence[str],
    *,
    size: int,
    permutations: int = PLACEBO_PERMUTATIONS,
    seed: int = PLACEBO_SEED,
) -> list[set[str]]:
    """Draw size keys at random from the pool, once per permutation.

    The placebo keeps the filter cardinality and destroys only its content, so an
    effect that survives it is not an artefact of shrinking the pool.
    """

    if size < 0 or size > len(scorable_keys):
        raise ValueError("the placebo size must lie in [0, len(scorable_keys)]")
    rng = random.Random(seed)
    pool = list(scorable_keys)
    drawn: list[set[str]] = []
    for _ in range(permutations):
        rng.shuffle(pool)
        drawn.append(set(pool[:size]))
    return drawn


def blocking_conditions(
    *,
    safety_key_set_name: str | None = SAFETY_KEY_SET,
    universe: str | None = SCORED_UNIVERSE,
    recommended_set_path: Path | None = RECOMMENDED_SET_PATH,
) -> list[str]:
    """Everything the preregistration must pin before a number may be scored."""

    blockers: list[str] = []
    if safety_key_set_name is None:
        blockers.append(
            f"SAFETY_KEY_SET is unset (choose {REGISTRY_CHANNEL} or {FEATURE_TABLE})"
        )
    elif safety_key_set_name not in {REGISTRY_CHANNEL, FEATURE_TABLE}:
        blockers.append(f"SAFETY_KEY_SET is not a pinned name: {safety_key_set_name!r}")
    if universe is None:
        blockers.append(
            f"SCORED_UNIVERSE is unset (choose {ROSTER_UNIVERSE} or {REGISTRY_UNIVERSE})"
        )
    elif universe not in {ROSTER_UNIVERSE, REGISTRY_UNIVERSE}:
        blockers.append(f"SCORED_UNIVERSE is not a pinned name: {universe!r}")
    if recommended_set_path is None:
        blockers.append("RECOMMENDED_SET_PATH is unset; head purity has no reference set")
    elif not Path(recommended_set_path).is_file():
        blockers.append(f"RECOMMENDED_SET_PATH does not exist: {recommended_set_path}")
    return blockers


def plan() -> dict[str, object]:
    """The pinned configuration, printable without producing a reading."""

    return {
        "schema_version": "w20_safety_ablation_plan_v0",
        "task": "week20_w20_2_step1_safety_influence_ablation",
        "status": "pinned_awaiting_execution",
        "not_executed_this_week": True,
        "produces_reading": False,
        "promotes_no_reading": True,
        "main_scoreboard_untouched": True,
        "scoreboard_attempts_delta": 0,
        "shot_number_taken": None,
        "coverage_gate": COVERAGE_GATE,
        "coverage_readings": COVERAGE_READINGS,
        "universe_readings": UNIVERSE_READINGS,
        "safety_key_set": SAFETY_KEY_SET,
        "scored_universe": SCORED_UNIVERSE,
        "recommended_set": (
            None
            if RECOMMENDED_SET_PATH is None
            else portable_relative_path(RECOMMENDED_SET_PATH, root=REPOSITORY_ROOT)
        ),
        "key": [
            {
                "channel": spec.channel,
                "column": spec.column,
                "direction": spec.direction,
                "weight": spec.weight,
            }
            for spec in DEFAULT_KEYS
        ],
        "arms": [
            {
                "name": arm.name,
                "restrict_to_liquid_window": arm.restrict_to_liquid_window,
                "hypothesis": arm.hypothesis,
            }
            for arm in ARMS
        ],
        "top_k_values": list(TOP_K_VALUES),
        "placebo": {"permutations": PLACEBO_PERMUTATIONS, "seed": PLACEBO_SEED},
        "inputs": {
            "registry": portable_relative_path(REGISTRY_PATH, root=REPOSITORY_ROOT),
            "liquid_window": portable_relative_path(LIQUID_WINDOW_PATH, root=REPOSITORY_ROOT),
            "v03_roster": portable_relative_path(V03_ROSTER_PATH, root=REPOSITORY_ROOT),
        },
        "reading_class": "read_only_influence_ablation",
        "models_fitted": 0,
        "reaxys_values_used": 0,
        "writes_any_pool": False,
        "promoted": False,
        "recommended_set_role": REFERENCE_ROLE,
        "coverage_verdicts": coverage_verdicts(),
        "blocking_conditions": blocking_conditions(),
    }


def run(
    *,
    registry_path: Path = REGISTRY_PATH,
    liquid_window_path: Path = LIQUID_WINDOW_PATH,
    roster_path: Path = V03_ROSTER_PATH,
    recommended_set_path: Path | None = RECOMMENDED_SET_PATH,
) -> dict[str, object]:
    """Score the two arms.  Refuses while the preregistration is incomplete."""

    blockers = blocking_conditions(recommended_set_path=recommended_set_path)
    if blockers:
        raise SystemExit("W20-2 Step 1 is not armed: " + "; ".join(blockers))
    assert recommended_set_path is not None  # narrowed by blocking_conditions

    registry_rows = read_csv_rows(registry_path)
    feature_rows = read_csv_rows(liquid_window_path)
    roster_keys = roster_key_set(read_csv_rows(roster_path))
    keys = safety_key_set(SAFETY_KEY_SET, registry_rows, feature_rows)
    reference = roster_key_set(read_csv_rows(recommended_set_path))
    recomputed_coverage = coverage_table(keys)
    check_coverage_against_readings(keys, recomputed_coverage)

    pool = score_pool(registry_rows, universe=SCORED_UNIVERSE, roster_keys=roster_keys)
    restricted = [row for row in pool if str(row["inchikey"]) in keys]
    if not restricted:
        raise SystemExit(
            "the restricted arm is empty; check SAFETY_KEY_SET against the registry"
        )

    when_unrestricted = ranking_key_table(pool, DEFAULT_KEYS)
    when_restricted = ranking_key_table(restricted, DEFAULT_KEYS)

    arms: list[dict[str, object]] = []
    for arm, table in zip(ARMS, (when_unrestricted, when_restricted), strict=True):
        arm_keys = {str(entry["inchikey"]) for entry in table}
        density = len(arm_keys & reference) / len(table) if table else 0.0
        purities = {
            str(k): purity(top_k_keys(table, k), reference) for k in TOP_K_VALUES
        }
        arms.append(
            {
                "name": arm.name,
                "restrict_to_liquid_window": arm.restrict_to_liquid_window,
                "pool_size": len(table),
                "reference_density_in_pool": density,
                "head_purity": purities,
                "purity_lift": {
                    key: value - density for key, value in purities.items()
                },
            }
        )

    overlap: dict[str, object] = {}
    for k in TOP_K_VALUES:
        base_head = top_k_keys(when_unrestricted, k)
        filtered_head = top_k_keys(when_restricted, k)
        overlap[str(k)] = {
            "jaccard": jaccard(base_head, filtered_head),
            "head_retention": head_retention(base_head, filtered_head),
            "membership_changes": len(set(base_head) ^ set(filtered_head)),
        }

    pool_keys = [str(row["inchikey"]) for row in pool]
    placebo = placebo_key_sets(pool_keys, size=len(restricted))
    placebo_purity: dict[str, object] = {}
    for k in TOP_K_VALUES:
        sampled = []
        for drawn in placebo:
            table = ranking_key_table(
                [row for row in pool if str(row["inchikey"]) in drawn], DEFAULT_KEYS
            )
            sampled.append(purity(top_k_keys(table, k), reference))
        sampled.sort()
        placebo_purity[str(k)] = {
            "min": sampled[0],
            "median": sampled[len(sampled) // 2],
            "max": sampled[-1],
        }

    return {
        **plan(),
        "status": "executed",
        "not_executed_this_week": False,
        "produces_reading": False,
        "produces_ablation_numbers": True,
        "models_fitted": 0,
        "reaxys_values_used": 0,
        "writes_any_pool": False,
        "promoted": False,
        "main_scoreboard_untouched": True,
        "scoreboard_attempts_delta": 0,
        "shot_number_taken": None,
        "coverage": recomputed_coverage,
        "arms": arms,
        "overlap": overlap,
        "placebo_head_purity": placebo_purity,
        "prereg": prereg_reference(),
    }


ARMS_CSV_FIELDS: tuple[str, ...] = (
    "arm",
    "k",
    "pool_size",
    "reference_density_in_pool",
    "top_k_hit_rate",
    "purity_lift",
    "jaccard_vs_arm0",
    "head_retention_vs_arm0",
    "candidate_list_change_count",
)


def arms_csv_rows(summary: Mapping[str, object]) -> list[dict[str, object]]:
    """Flatten the Step-1 arm table into one row per (arm, k).

    A pure projection of the executed summary: the per-arm top-k hit rate and its
    containment lift, plus the overlap block Jaccard@k and candidate-list change
    count.  Arm0 is the overlap reference, so its Jaccard, retention and change
    count are 1.0 / 1.0 / 0 by construction rather than by measurement.
    """

    arms = summary["arms"]
    overlap = summary["overlap"]
    assert isinstance(arms, list) and isinstance(overlap, Mapping)
    rows: list[dict[str, object]] = []
    for arm in arms:
        assert isinstance(arm, Mapping)
        name = str(arm["name"])
        purity = arm["head_purity"]
        lift = arm["purity_lift"]
        assert isinstance(purity, Mapping) and isinstance(lift, Mapping)
        for k in TOP_K_VALUES:
            key = str(k)
            if name == ARMS[0].name:
                jaccard_value: object = 1.0
                retention_value: object = 1.0
                changes: object = 0
            else:
                block = overlap[key]
                assert isinstance(block, Mapping)
                jaccard_value = block["jaccard"]
                retention_value = block["head_retention"]
                changes = block["membership_changes"]
            rows.append(
                {
                    "arm": name,
                    "k": k,
                    "pool_size": arm["pool_size"],
                    "reference_density_in_pool": arm["reference_density_in_pool"],
                    "top_k_hit_rate": purity[key],
                    "purity_lift": lift[key],
                    "jaccard_vs_arm0": jaccard_value,
                    "head_retention_vs_arm0": retention_value,
                    "candidate_list_change_count": changes,
                }
            )
    return rows


def write_arms_csv(path: Path, summary: Mapping[str, object]) -> None:
    """Write the Step-1 arm table.  LF only, so the artifact stays diff-stable."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(ARMS_CSV_FIELDS), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(arms_csv_rows(summary))


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="print the pinned plan and exit")
    parser.add_argument(
        "--recommended-set",
        type=Path,
        default=RECOMMENDED_SET_PATH,
        help="the pinned reference set; defaults to the preregistered pin",
    )
    parser.add_argument(
        "--write-prereg",
        action="store_true",
        help="write the frozen preregistration JSON",
    )
    parser.add_argument("--prereg", type=Path, default=PREREG_PATH)
    parser.add_argument("--write-summary", action="store_true", help="write the summary JSON")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument(
        "--write-arms-csv",
        action="store_true",
        help="write the Step-1 arm table CSV",
    )
    parser.add_argument("--arms-csv", type=Path, default=ARMS_CSV_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.plan:
        print(json.dumps(plan(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.write_prereg:
        prereg = prereg_summary(
            locked_at_utc=datetime.now(UTC).isoformat()
        )
        args.prereg.write_text(
            json.dumps(prereg, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps(prereg, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    summary = run(recommended_set_path=args.recommended_set)
    if args.write_summary:
        args.summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.write_arms_csv:
        write_arms_csv(args.arms_csv, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    raise SystemExit(main())
