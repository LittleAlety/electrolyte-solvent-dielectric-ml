"""Is the Week 24-1 re-run a faithful replay of the first pass?

The first pass dropped the lithium diagnostics, so H2 was scored on zero pairs.  The
repair is a re-run, not a patch, and a re-run is only admissible if it reproduces the
first pass exactly wherever the defect could not have reached.  This compares the two
archived layers column by column and lists every difference.

Timing columns are excluded by construction: they measure the host, not the protocol.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _extra in (ROOT / "probes", ROOT / "src"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))
import w21_li_coordination as w21
try:  # W40-B import shim: works as `probes.<mod>` and as a direct script
    from probes.export_results_common import write_json_stable
except ImportError:  # direct execution: probes/ is sys.path[0]
    from export_results_common import write_json_stable


BEFORE = ROOT / "probes" / "artifacts" / "w24_condition_redox_layer_firstpass.csv"
AFTER = ROOT / "data" / "processed" / "w24_condition_redox_layer.csv"
SUMMARY = ROOT / "probes" / "w24_condition_redox_summary.json"
ARTIFACTS = ROOT / "probes" / "artifacts"

VOLATILE_SUFFIXES = ("_li_q", "seconds_total")
VOLATILE_EXACT = ("error",)


def is_volatile(column):
    """Columns the repair was allowed to change, or that measure the host."""

    if column in VOLATILE_EXACT:
        return True
    return any(column.endswith(suffix) for suffix in VOLATILE_SUFFIXES)


def compare(before_rows, after_rows, fields):
    before = {int(row["row_index"]): row for row in before_rows}
    after = {int(row["row_index"]): row for row in after_rows}
    differences = []
    compared = 0
    identical = 0
    for index in sorted(set(before) & set(after)):
        for field in fields:
            if is_volatile(field):
                continue
            compared += 1
            left = (before[index].get(field) or "").strip()
            right = (after[index].get(field) or "").strip()
            if left == right:
                identical += 1
            else:
                differences.append({"row_index": index, "name": before[index].get("name"),
                                    "column": field, "first_pass": left, "re_run": right})
    return {"compared": compared, "identical": identical, "differences": differences,
            "only_in_first_pass": sorted(set(before) - set(after)),
            "only_in_re_run": sorted(set(after) - set(before))}


def li_fill(after_rows):
    columns = [column for column in after_rows[0] if column.endswith("_li_q")]
    filled = 0
    total = 0
    per_column = {}
    for column in columns:
        values = [(row.get(column) or "").strip() for row in after_rows]
        non_empty = sum(1 for value in values if value not in ("", "None", "nan"))
        per_column[column] = non_empty
        filled += non_empty
        total += len(values)
    return {"columns": len(columns), "filled": filled, "cells": total,
            "per_column": per_column}


def main():
    before_rows = w21.read_rows(BEFORE)
    after_rows = w21.read_rows(AFTER)
    fields = [field for field in after_rows[0]]
    result = compare(before_rows, after_rows, fields)
    fill = li_fill(after_rows)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    payload = {
        "before_rows": len(before_rows),
        "after_rows": len(after_rows),
        "columns_compared": result["compared"],
        "columns_identical": result["identical"],
        "differences": len(result["differences"]),
        "only_in_first_pass": result["only_in_first_pass"],
        "only_in_re_run": result["only_in_re_run"],
        "li_columns": fill["columns"],
        "li_cells_filled": fill["filled"],
        "li_cells_total": fill["cells"],
        "h2_verdict": ((summary.get("hypotheses") or {}).get("H2") or {}).get("verdict"),
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    fields_out = ["row_index", "name", "column", "first_pass", "re_run"]
    w21.write_csv(ARTIFACTS / "w24_firstpass_reproduction.csv", fields_out,
                  [[row[field] for field in fields_out] for row in result["differences"]])
    write_json_stable(ARTIFACTS / "w24_firstpass_reproduction.json", payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())