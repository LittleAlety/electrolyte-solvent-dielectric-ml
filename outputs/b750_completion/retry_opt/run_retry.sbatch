#!/bin/bash
#SBATCH --job-name=b742_retry
#SBATCH -p hpxg
#SBATCH -N 1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --output=slurm-%A_%a.out
set -eu
module load openmpi/5.0
source "$HOME/project/soft/orca/env.sh"
PKG_DIR="$SLURM_SUBMIT_DIR"
JOB_DIR=$(sed -n "$SLURM_ARRAY_TASK_ID p" "$PKG_DIR/joblist.txt")
cd "$PKG_DIR/$JOB_DIR"
if [ -f job.out ] && grep -q 'ORCA TERMINATED NORMALLY' job.out && grep -q 'THE OPTIMIZATION HAS CONVERGED' job.out && grep -q 'Isotropic polarizability' job.out; then exit 0; fi
"$ORCA_DIR/orca" job.inp > job.out 2>&1
