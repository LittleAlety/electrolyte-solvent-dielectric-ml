#!/bin/bash
#-------------------------------------------------------------------------------
# ORCA r2SCAN-3c single-point for one B704 conformer on WHU hpxg.
# ORCA invokes mpirun itself, so Slurm must give it N TASK slots, not 1 task with
# N cpus: the latter fails at startup with "not enough slots".
# Usage: sbatch --array=1-<N> run_b704_conformers.sbatch <joblist>
#-------------------------------------------------------------------------------
#SBATCH --partition=hpxg
#SBATCH --job-name=b704_conformer
#SBATCH --output=output_%A_%a.out
#SBATCH --error=output_%A_%a.err
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G

set -u
JOBS_DIR="$(pwd)/jobs"
JOBLIST="${1:-joblist.txt}"

LINE=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$JOBLIST" | tr -d '\r\n')
if [ -z "$LINE" ]; then
    echo "No job at index ${SLURM_ARRAY_TASK_ID}"
    exit 0
fi

TARGET="$JOBS_DIR/$LINE"
INP="$TARGET/job.inp"
XYZ="$TARGET/geom.xyz"

if [ ! -f "$INP" ]; then
    echo "Missing input: $INP"
    exit 1
fi

# ORCA shells out to mpirun itself, so the MPI runtime must be on PATH.
module load openmpi/5.0
source "$HOME/project/soft/orca/env.sh"

cd "$TARGET"
$ORCA_DIR/orca job.inp > job.out 2>&1
RC=$?
echo "orca_exit=$RC"

# Keep key outputs
if [ -f job.out ]; then
    grep -q 'ORCA TERMINATED NORMALLY' job.out && echo "STATUS=OK" || echo "STATUS=FAILED"
fi

exit $RC
