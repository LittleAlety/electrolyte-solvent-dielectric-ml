#!/bin/bash
#-------------------------------------------------------------------------------
# ORCA r2SCAN-3c OPT batch on WHU hpxg.
# ORCA invokes mpirun itself, so Slurm must give it N TASK slots, not 1 task with
# N cpus: the latter form fails at startup with "not enough slots".
# Usage: sbatch --array=1-12 run_batch.sbatch
#-------------------------------------------------------------------------------
#SBATCH --job-name=b701_opt
#SBATCH -p hpxg
#SBATCH -N 1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --time=08:00:00
#SBATCH --output=slurm-%A_%a.out

set -u
# ORCA shells out to mpirun itself, so the MPI runtime must be on PATH.
# Without this the job dies at startup with 'mpirun: command not found'.
module load openmpi/5.0
source $HOME/project/soft/orca/env.sh

PKG_DIR="${SLURM_SUBMIT_DIR}"
JOB_DIR=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$PKG_DIR/joblist.txt")
if [ -z "$JOB_DIR" ]; then echo "no job for task $SLURM_ARRAY_TASK_ID"; exit 1; fi
WORK="$PKG_DIR/$JOB_DIR"
cd "$WORK" || exit 1

# %pal is already in job.inp; only sanity-check the slot count
# ORCA 6 requires the BLOCK form of %pal. The legacy single-line form
# '%pal nprocs N' is rejected at scan time with 'Unrecognized symbol in PAL block'.

$ORCA_DIR/orca job.inp > job.out 2>&1
RC=$?
echo "exit=$RC dir=$JOB_DIR"
grep -c "TERMINATED NORMALLY" job.out || true
exit $RC
