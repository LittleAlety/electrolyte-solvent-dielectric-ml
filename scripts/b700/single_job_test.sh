#!/bin/bash
# Submit ONE molecule as a standalone job, to discriminate "bad molecule" from
# "chunked array / MPI problem". The chunked array left ~130 jobs with empty output
# and a zero-byte job.bas0, which is the signature of ORCA dying at startup rather
# than a chemistry failure. This test settles which it is.
set -u
REMOTE=pengqihang@202.114.96.180
KEY="$HOME/.ssh/id_ed25519_whu"
IK="${1:?usage: single_job_test.sh INCHIKEY}"

ssh -i "$KEY" -o BatchMode=yes "$REMOTE" "mkdir -p ~/b700/scratch && cat > ~/b700/scratch/one.sbatch <<'SB'
#!/bin/bash
#SBATCH --job-name=b701_one
#SBATCH -p hpxg
#SBATCH -N 1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --time=00:40:00
#SBATCH --output=~/b700/scratch/one-%j.out
set -u
module load openmpi/5.0
source \$HOME/project/soft/orca/env.sh
cd ~/b700/B701/production_239/package_sp/jobs/$IK || exit 9
\$ORCA_DIR/orca job.inp > job.out 2>&1
echo exit=\$?
grep -c 'ORCA TERMINATED NORMALLY' job.out || true
SB
chmod +x ~/b700/scratch/one.sbatch && cd ~/b700/scratch && sbatch one.sbatch"
