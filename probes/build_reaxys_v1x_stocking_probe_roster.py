"""Build the W17-16 Reaxys stocking-queue probe roster.

The v1.x stocking queue (167 rows, every row carrying a verbatim InChIKey in its
``inchikey`` column) is the channel the Week 17 plan names for compound expansion.
Only three of its rows are flagged as probed, but fourteen more were walked by the
W17-13/W17-15 thin-family lanes, so the queue flag understates what is already known.
This builder recomputes the split from the probe artefacts themselves: a row is
``already_probed`` when its key appears in a prior probe artefact or when the queue
flags it, and ``probe_target`` otherwise.

The roster is a plan, not a measurement.  It runs no query, and ruling B still holds:
no Reaxys rendered value enters this file, ``data/``, any pool or any feature table.
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
PREREG_PATH = REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_probe_prereg.json"
ROSTER_PATH = REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_probe_roster.csv"
SUMMARY_PATH = REPOSITORY_ROOT / "probes" / "reaxys_v1x_stocking_probe_roster_summary.json"
REPORT_PATH = REPOSITORY_ROOT / "reports" / "reaxys_v1x_stocking_probe_roster.md"

ROSTER_FIELDS = [
    "probe_order",
    "queue_rank",
    "inchikey",
    "name",
    "smiles",
    "family_tag",
    "stocking_priority",
    "target_dielectric",
    "target_T_K",
    "is_champion",
    "champion_short",
    "local_rows",
    "probe_status",
    "prior_evidence",
    "aromatic_non_electrolyte_suspect",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_prereg() -> dict:
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    inputs = prereg["inputs"]
    checks = [(inputs["queue"]["path"], inputs["queue"]["sha256"])]
    checks += [
        (item["path"], item["sha256"]) for item in inputs["prior_probe_artefacts"]
    ]
    for relative, expected in checks:
        measured = sha256_file(REPOSITORY_ROOT / relative)
        if measured != expected:
            raise SystemExit("input digest mismatch: " + relative)
    return prereg


def prior_probe_keys(prereg: dict) -> dict[str, list[str]]:
    """Every InChIKey a prior probe artefact is keyed on, with its provenance."""

    found: dict[str, list[str]] = {}
    for item in prereg["inputs"]["prior_probe_artefacts"]:
        relative = item["path"]
        for row in read_csv(REPOSITORY_ROOT / relative):
            key = (row.get("inchikey") or "").strip()
            if key:
                found.setdefault(key, [])
                if relative not in found[key]:
                    found[key].append(relative)
    return found


def flagged_as_aromatic_suspect(row: dict[str, str]) -> bool:
    return (row.get("family_tag") or "").strip() == "fluorinated" and "c" in (
        row.get("smiles") or ""
    )


def build_roster(prereg: dict) -> tuple[list[dict[str, str]], dict[str, list[str]]]:
    queue = read_csv(REPOSITORY_ROOT / prereg["inputs"]["queue"]["path"])
    tiers = set(prereg["scope"]["tiers_included"])
    prior = prior_probe_keys(prereg)

    selected = [row for row in queue if (row.get("stocking_priority") or "") in tiers]
    rows: list[dict[str, str]] = []
    for row in selected:
        key = (row.get("inchikey") or "").strip()
        evidence = list(prior.get(key, []))
        if (row.get("probed_in_this_round") or "").strip() == "yes":
            evidence.append("queue_flag:probed_in_this_round")
        status = "already_probed" if evidence else "probe_target"
        rows.append(
            {
                "queue_rank": (row.get("queue_rank") or "").strip(),
                "inchikey": key,
                "name": (row.get("name") or "").strip(),
                "smiles": (row.get("smiles") or "").strip(),
                "family_tag": (row.get("family_tag") or "").strip(),
                "stocking_priority": (row.get("stocking_priority") or "").strip(),
                "target_dielectric": (row.get("target_dielectric") or "").strip(),
                "target_T_K": (row.get("target_T_K") or "").strip(),
                "is_champion": (row.get("is_champion") or "").strip(),
                "champion_short": (row.get("champion_short") or "").strip(),
                "local_rows": (row.get("local_rows") or "").strip(),
                "probe_status": status,
                "prior_evidence": ";".join(evidence),
                "aromatic_non_electrolyte_suspect": (
                    "yes" if flagged_as_aromatic_suspect(row) else "no"
                ),
            }
        )

    tier_order = {tier: index for index, tier in enumerate(prereg["scope"]["tiers_included"])}

    def sort_key(row: dict[str, str]) -> tuple:
        return (
            0 if row["probe_status"] == "probe_target" else 1,
            tier_order.get(row["stocking_priority"], 9),
            1 if row["aromatic_non_electrolyte_suspect"] == "yes" else 0,
            int(row["queue_rank"]),
        )

    rows.sort(key=sort_key)
    for index, row in enumerate(rows, start=1):
        row["probe_order"] = str(index)
    return rows, prior


def verify_invariants(rows: list[dict[str, str]], queue: list[dict[str, str]]) -> list[str]:
    problems: list[str] = []
    queue_keys = {(row.get("inchikey") or "").strip() for row in queue}
    for row in rows:
        if row["inchikey"] not in queue_keys:
            problems.append("key not taken verbatim from the queue: " + row["inchikey"])
    if len(rows) != len({row["inchikey"] for row in rows}):
        problems.append("duplicate keys in the roster")
    if any(not row["prior_evidence"] for row in rows if row["probe_status"] == "already_probed"):
        problems.append("already_probed row without recorded evidence")
    if any(row["prior_evidence"] for row in rows if row["probe_status"] == "probe_target"):
        problems.append("probe_target row carries prior evidence")
    return problems


def build_summary(prereg: dict, rows: list[dict[str, str]], queue: list[dict[str, str]]) -> dict:
    targets = [row for row in rows if row["probe_status"] == "probe_target"]
    probed = [row for row in rows if row["probe_status"] == "already_probed"]
    suspects = [row for row in targets if row["aromatic_non_electrolyte_suspect"] == "yes"]
    queue_keys = {(row.get("inchikey") or "").strip() for row in queue}
    return {
        "schema_version": prereg["schema_version"],
        "lane": prereg["lane"],
        "week": prereg["week"],
        "generated": prereg["created"],
        "prereg": {"path": "probes/reaxys_v1x_stocking_probe_prereg.json", "sha256": sha256_file(PREREG_PATH)},
        "queue": {
            "path": prereg["inputs"]["queue"]["path"],
            "sha256": prereg["inputs"]["queue"]["sha256"],
            "row_count": len(queue),
        },
        "roster": {
            "path": "probes/reaxys_v1x_stocking_probe_roster.csv",
            "rows": len(rows),
            "sha256": sha256_file(ROSTER_PATH) if ROSTER_PATH.exists() else None,
        },
        "tiers": prereg["scope"]["tiers_included"],
        "counts": {
            "probe_target": len(targets),
            "already_probed": len(probed),
            "aromatic_non_electrolyte_suspect": len(suspects),
            "by_family_probe_target": dict(
                sorted(
                    (family, sum(1 for row in targets if row["family_tag"] == family))
                    for family in {row["family_tag"] for row in targets}
                )
            ),
            "by_family_already_probed": dict(
                sorted(
                    (family, sum(1 for row in probed if row["family_tag"] == family))
                    for family in {row["family_tag"] for row in probed}
                )
            ),
        },
        "probe_target_keys_in_order": [row["inchikey"] for row in targets],
        "already_probed": [
            {"inchikey": row["inchikey"], "name": row["name"], "evidence": row["prior_evidence"]}
            for row in probed
        ],
        "aromatic_non_electrolyte_suspect_keys": [row["inchikey"] for row in suspects],
        "key_audit": {
            "keys_not_from_the_queue": len([row for row in rows if row["inchikey"] not in queue_keys]),
            "rule": "every roster key must appear verbatim in the queue inchikey column",
        },
        "non_interference": prereg["non_interference"],
        "compliance": prereg["compliance"],
        "is_a_plan_not_a_measurement": True,
        "queries_executed": 0,
    }


def render_report(summary: dict, rows: list[dict[str, str]]) -> str:
    lines = [
        "# W17-16 Reaxys 库存队列实查名册（P1 + P2 层）",
        "",
        "**一句话**：Week 17 计划把 Reaxys 库存队列（P1 = 2 / P2 = 22 / P3 = 143）点名为扩物质渠道；",
        "本名册把 P1 + P2 的 **24 行**逐条拆成「W17-13/W17-15 已实查」与「仍待实查」，",
        "拆分**由前序探针产物重算**，不采信队列自带的 `probed_in_this_round` 旧标记。",
        "",
        "**这是计划，不是测量**：本件 `queries_executed = 0`，不含任何 Reaxys 渲染值。",
        "",
        "## 计数",
        "",
        "| 口径 | 行数 |",
        "| --- | ---: |",
        "| 名册总行数（P1 + P2） | " + str(len(rows)) + " |",
        "| `probe_target`（仍待实查） | " + str(summary["counts"]["probe_target"]) + " |",
        "| `already_probed`（已由前序车道实查） | " + str(summary["counts"]["already_probed"]) + " |",
        "| 其中芳香非电解液疑似（人工复核优先） | " + str(
            summary["counts"]["aromatic_non_electrolyte_suspect"]
        ) + " |",
        "",
        "## 仍待实查的物质（按 probe_order）",
        "",
        "| order | rank | tier | family | name | inchikey | target_eps | 芳香疑似 |",
        "| ---: | ---: | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in rows:
        if row["probe_status"] != "probe_target":
            continue
        lines.append(
            "| " + row["probe_order"] + " | " + row["queue_rank"] + " | "
            + row["stocking_priority"] + " | " + row["family_tag"] + " | " + row["name"]
            + " | `" + row["inchikey"] + "` | " + row["target_dielectric"] + " | "
            + ("是" if row["aromatic_non_electrolyte_suspect"] == "yes" else "") + " |"
        )
    lines += [
        "",
        "## 已由前序车道实查（不再重复查）",
        "",
        "| rank | tier | name | inchikey | 证据 |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for row in rows:
        if row["probe_status"] != "already_probed":
            continue
        lines.append(
            "| " + row["queue_rank"] + " | " + row["stocking_priority"] + " | " + row["name"]
            + " | `" + row["inchikey"] + "` | " + row["prior_evidence"] + " |"
        )
    lines += [
        "",
        "## 边界",
        "",
        "- 名的拆分**不采信队列旧 flag**：`probed_in_this_round` 只标了 3 行，实际前序车道已走过 14 个键；两者取并集。",
        "- `family_tag = fluorinated` 的子串规则会把**非电解液芳烃**（氟代甲苯 / 氟苯 / 二氟苯 / 三氟甲苯）拖进 P2；名册把它们标 `aromatic_non_electrolyte_suspect = yes` 并沉到同层队尾，**不静默删除**。",
        "- 键**逐字取自**队列 `inchikey` 列（`keys_not_from_the_queue = 0`）；禁止手抄键。",
        "- 合规（裁决 B）：Reaxys 派生数值不得进 `data/`、不得进任何池、不得进任何特征表；原始页证据只落被忽略的 `data/raw/reaxys_w17d/`。",
        "- 本件 `models_fitted = 0`、不报 R²、不碰主记分牌 0.4091179943351143。",
        "",
    ]
    return chr(10).join(lines) + chr(10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="re-derive and compare, write nothing")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    prereg = load_prereg()
    queue = read_csv(REPOSITORY_ROOT / prereg["inputs"]["queue"]["path"])
    rows, _ = build_roster(prereg)
    problems = verify_invariants(rows, queue)
    for problem in problems:
        print("INVARIANT FAILURE: " + problem)
    if problems:
        return 1

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ROSTER_FIELDS, lineterminator=chr(10))
    writer.writeheader()
    writer.writerows(rows)
    rendered = buffer.getvalue()

    if args.check:
        existing = ROSTER_PATH.read_text(encoding="utf-8")
        if existing != rendered:
            print("ROSTER MISMATCH")
            return 1
        print("roster reproduces: rows=" + str(len(rows)))
        return 0

    ROSTER_PATH.write_text(rendered, encoding="utf-8", newline="")
    summary = build_summary(prereg, rows, queue)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8", newline=chr(10))
    REPORT_PATH.write_text(render_report(summary, rows), encoding="utf-8", newline=chr(10))
    print("rows=" + str(len(rows)))
    print("probe_target=" + str(summary["counts"]["probe_target"]))
    print("already_probed=" + str(summary["counts"]["already_probed"]))
    print("wrote: " + str(ROSTER_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

