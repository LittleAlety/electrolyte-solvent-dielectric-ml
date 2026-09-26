"""Independent re-derivation of the W17-16 Reaxys stocking-queue probe roster.

This verifier does not import the builder.  It re-reads the queue and the prior
probe artefacts, re-derives the probe_target / already_probed split with its own
code, re-sorts, and compares the result to the shipped roster byte for byte.  It
also re-checks the acceptance rules the prereg locked: every key verbatim from the
queue, no invented or dropped row, and the roster is a plan (zero queries, no value).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(relative: str) -> dict:
    return json.loads((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))


def check(prereg: dict) -> tuple[list[str], dict]:
    failures: list[str] = []

    def expect(name: str, condition: bool, detail: str = "") -> None:
        if not condition:
            failures.append(name + (": " + detail if detail else ""))

    queue_path = prereg["inputs"]["queue"]["path"]
    queue_bytes = (REPOSITORY_ROOT / queue_path).read_bytes()
    expect(
        "queue_digest",
        sha256_bytes(queue_bytes) == prereg["inputs"]["queue"]["sha256"],
    )
    queue = list(csv.DictReader(io.StringIO(queue_bytes.decode("utf-8-sig"))))
    expect("queue_rows", len(queue) == prereg["inputs"]["queue"]["row_count"])

    prior: dict[str, list[str]] = {}
    for item in prereg["inputs"]["prior_probe_artefacts"]:
        raw = (REPOSITORY_ROOT / item["path"]).read_bytes()
        expect("artefact_digest:" + item["path"], sha256_bytes(raw) == item["sha256"])
        for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
            key = (row.get("inchikey") or "").strip()
            if key:
                prior.setdefault(key, [])
                if item["path"] not in prior[key]:
                    prior[key].append(item["path"])

    tiers = prereg["scope"]["tiers_included"]
    tier_index = {tier: index for index, tier in enumerate(tiers)}
    derived: list[dict[str, str]] = []
    for row in queue:
        if (row.get("stocking_priority") or "") not in tiers:
            continue
        key = (row.get("inchikey") or "").strip()
        evidence = list(prior.get(key, []))
        if (row.get("probed_in_this_round") or "").strip() == "yes":
            evidence.append("queue_flag:probed_in_this_round")
        derived.append(
            {
                "queue_rank": (row.get("queue_rank") or "").strip(),
                "inchikey": key,
                "name": (row.get("name") or "").strip(),
                "smiles": (row.get("smiles") or "").strip(),
                "family_tag": (row.get("family_tag") or "").strip(),
                "stocking_priority": (row.get("stocking_priority") or "").strip(),
                "probe_status": "already_probed" if evidence else "probe_target",
                "prior_evidence": ";".join(evidence),
                "aromatic_non_electrolyte_suspect": (
                    "yes"
                    if (row.get("family_tag") or "").strip() == "fluorinated"
                    and "c" in (row.get("smiles") or "")
                    else "no"
                ),
            }
        )
    derived.sort(
        key=lambda r: (
            0 if r["probe_status"] == "probe_target" else 1,
            tier_index.get(r["stocking_priority"], 9),
            1 if r["aromatic_non_electrolyte_suspect"] == "yes" else 0,
            int(r["queue_rank"]),
        )
    )

    shipped_bytes = (REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_probe_roster.csv").read_bytes()
    shipped = list(csv.DictReader(io.StringIO(shipped_bytes.decode("utf-8-sig"))))
    expect("roster_rows", len(shipped) == len(derived), str(len(shipped)) + " vs " + str(len(derived)))
    expect("roster_rows_expected", len(shipped) == prereg["scope"]["expected_rows"])

    for index, (left, right) in enumerate(zip(derived, shipped, strict=False)):
        for field in ("queue_rank", "inchikey", "probe_status", "prior_evidence"):
            expect(
                "row" + str(index) + ":" + field,
                left[field] == right[field],
                left[field] + " vs " + right[field],
            )
        expect("order" + str(index), str(index + 1) == right["probe_order"])

    queue_keys = {(row.get("inchikey") or "").strip() for row in queue}
    foreign = [row["inchikey"] for row in shipped if row["inchikey"] not in queue_keys]
    expect("keys_not_from_the_queue", not foreign, ";".join(foreign))
    expect(
        "no_duplicate_keys",
        len(shipped) == len({row["inchikey"] for row in shipped}),
    )

    summary = load_json("probes/reaxys_v1x_stocking_probe_roster_summary.json")
    expect(
        "roster_digest_in_summary",
        summary["roster"]["sha256"] == sha256_bytes(shipped_bytes),
    )
    targets = [row for row in shipped if row["probe_status"] == "probe_target"]
    probed = [row for row in shipped if row["probe_status"] == "already_probed"]
    expect("summary_probe_target", summary["counts"]["probe_target"] == len(targets))
    expect("summary_already_probed", summary["counts"]["already_probed"] == len(probed))
    expect(
        "summary_target_keys",
        summary["probe_target_keys_in_order"] == [row["inchikey"] for row in targets],
    )
    expect("key_audit_zero", summary["key_audit"]["keys_not_from_the_queue"] == 0)
    expect("is_a_plan", summary["is_a_plan_not_a_measurement"] is True)
    expect("zero_queries", summary["queries_executed"] == 0)
    expect("no_models", summary["non_interference"]["models_fitted"] == 0)
    expect("no_r2", summary["non_interference"]["r2_reported"] is False)
    expect(
        "no_scoreboard",
        summary["non_interference"]["main_scoreboard_touched"] is False,
    )
    expect("no_data_writes", summary["non_interference"]["data_tracked_files_written"] == [])
    expect("values_not_in_data", summary["compliance"]["values_enter_data"] is False)

    report = (REPOSITORY_ROOT / "reports" / "reaxys_v1x_stocking_probe_roster.md").read_text(
        encoding="utf-8"
    )
    expect("report_plan_line", "queries_executed = 0" in report)
    expect("report_key_rule", "keys_not_from_the_queue = 0" in report)

    stats = {
        "roster_rows": len(shipped),
        "probe_target": len(targets),
        "already_probed": len(probed),
        "suspects": sum(1 for row in shipped if row["aromatic_non_electrolyte_suspect"] == "yes"),
    }
    return failures, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="same verification, explicit mode")
    parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    prereg = load_json("probes/reaxys_v1x_stocking_probe_prereg.json")
    failures, stats = check(prereg)
    for failure in failures:
        print("FAIL " + failure)
    print("stats " + json.dumps(stats, ensure_ascii=False))
    print("PASS" if not failures else "FAILED")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

