#!/bin/bash
#-------------------------------------------------------------------------------
# GFN2-xTB single point at FIXED r2SCAN-3c geometry (B710 low-priority item).
# No optimisation: --sp only. This fills the missing xTB-on-DFT-geometry cell.
# Usage: sbatch --array=1-12 run_xtb_on_dft.sbatch
#-------------------------------------------------------------------------------
#SBATCH --partition=hpxg
#SBATCH --job-name=b710_xtb_sp
#SBATCH --output=xtb_%A_%a.out
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G

set -u
BASE="$(pwd)"
source "$HOME/project/soft/xtb/env.sh"

DIRS=($(find "$BASE/xtb_dft_geom_inputs" -mindepth 1 -maxdepth 1 -type d | sort))
IDX=$((SLURM_ARRAY_TASK_ID - 1))
TARGET="${DIRS[$IDX]:-}"
if [ -z "$TARGET" ]; then
    echo "no target at array index ${SLURM_ARRAY_TASK_ID}"
    exit 0
fi

cd "$TARGET" || exit 1
xtb xtb.xyz --sp --chrg 0 --uhf 0 --namespace sp > xtb_sp.out 2>&1
RC=$?
echo "dir=$(basename "$TARGET") exit=$RC"
grep -q "normal termination" xtb_sp.out && echo "STATUS=OK" || echo "STATUS=CHECK"
exit $RC
