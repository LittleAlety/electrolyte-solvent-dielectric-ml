#!/usr/bin/env bash
# Reproducibility harness: back up outputs, run B04/B05 twice, compare, restore.
set -u
ROOT="E:/Claude Code/电解质ML/电解质ML"
REV="$ROOT/outputs/b04_b05_review"
BK="$REV/_backup_original_outputs"
PY="$ROOT/.venv/Scripts/python.exe"

cd "$ROOT" || exit 1
rm -rf "$BK"; mkdir -p "$BK"
cp -a outputs/b04 "$BK/b04"
cp -a outputs/b05 "$BK/b05"
echo "backup done"
find "$BK" -type f | wc -l

run_all() {
  local tag="$1"
  "$PY" scripts/b04/build_candidate_pool_v2.py  > "$REV/run_${tag}_b04.log"  2>&1
  echo "b04 rc=$?" >> "$REV/run_${tag}_b04.log"
  "$PY" scripts/b05/build_feature_registry.py   > "$REV/run_${tag}_b0.log"   2>&1
  echo "b0 rc=$?"  >> "$REV/run_${tag}_b0.log"
  "$PY" scripts/b05/run_e1_structure_vs_electronic.py > "$REV/run_${tag}_e1.log" 2>&1
  echo "e1 rc=$?"  >> "$REV/run_${tag}_e1.log"
  "$PY" scripts/b05/run_e4_domain_generalization.py   > "$REV/run_${tag}_e4.log" 2>&1
  echo "e4 rc=$?"  >> "$REV/run_${tag}_e4.log"
  "$PY" scripts/b05/run_e6_screening_decisions.py     > "$REV/run_${tag}_e6.log" 2>&1
  echo "e6 rc=$?"  >> "$REV/run_${tag}_e6.log"
  "$PY" scripts/b05/build_model_boundary_report.py    > "$REV/run_${tag}_b7.log" 2>&1
  echo "b7 rc=$?"  >> "$REV/run_${tag}_b7.log"
}

rm -rf "$REV/_run1" "$REV/_run2"
run_all 1
mkdir -p "$REV/_run1"; cp -a outputs/b04 "$REV/_run1/b04"; cp -a outputs/b05 "$REV/_run1/b05"
run_all 2
mkdir -p "$REV/_run2"; cp -a outputs/b04 "$REV/_run2/b04"; cp -a outputs/b05 "$REV/_run2/b05"

echo "=== exit codes ==="
grep -h "rc=" "$REV"/run_1_*.log "$REV"/run_2_*.log

echo "=== diff run1 vs run2 (full) ==="
diff -rq "$REV/_run1" "$REV/_run2" | tee "$REV/diff_run1_run2.txt"
echo "--- differing file count ---"
diff -rq "$REV/_run1" "$REV/_run2" | wc -l

echo "=== diff original-backup vs run1 ==="
mkdir -p "$REV/_orig"; cp -a "$BK/b04" "$REV/_orig/b04"; cp -a "$BK/b05" "$REV/_orig/b05"
diff -rq "$REV/_orig" "$REV/_run1" | tee "$REV/diff_orig_run1.txt"
echo "--- differing file count ---"
diff -rq "$REV/_orig" "$REV/_run1" | wc -l
