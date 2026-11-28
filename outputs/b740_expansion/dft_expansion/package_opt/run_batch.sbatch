#!/bin/bash
#-------------------------------------------------------------------------------
# B742 ORCA opt batch on WHU hpxg (chunked).
# ORCA invokes mpirun itself, so Slurm must give it N TASK slots, not 1 task with
# N cpus: the latter fails at startup with "not enough slots".
# Usage: sbatch --array=1-9 run_batch.sbatch
#-------------------------------------------------------------------------------
#SBATCH --job-name=b742_opt
#SBATCH -p hpxg
#SBATCH -N 1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --output=slurm-%A_%a.out

set -u
module load openmpi/5.0
source $HOME/project/soft/orca/env.sh

PKG_DIR="${SLURM_SUBMIT_DIR}"
CHUNK=8
FIRST=$(( (SLURM_ARRAY_TASK_ID - 1) * CHUNK + 1 ))
LAST=$(( SLURM_ARRAY_TASK_ID * CHUNK ))

for IDX in $(seq $FIRST $LAST); do
  JOB_DIR=$(sed -n "${IDX}p" "$PKG_DIR/joblist.txt")
  [ -z "$JOB_DIR" ] && continue
  WORK="$PKG_DIR/$JOB_DIR"
  [ -f "$WORK/job.out" ] && grep -q "ORCA TERMINATED NORMALLY" "$WORK/job.out" && continue
  cd "$WORK" || continue
  $ORCA_DIR/orca job.inp > job.out 2>&1
  RC=$?
  OK=$(grep -c "ORCA TERMINATED NORMALLY" job.out || true)
  echo "task=${SLURM_ARRAY_TASK_ID} idx=$IDX dir=$JOB_DIR exit=$RC ok=$OK"
  cd "$PKG_DIR" || exit 1
done
echo "chunk ${SLURM_ARRAY_TASK_ID} finished"
