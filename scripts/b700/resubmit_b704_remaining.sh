#!/bin/bash
# Resubmit the remaining B704 conformers (missing or failed).
# Builds an index list from joblist.txt, writes joblist_remaining.txt in the
# same order, then submits one Slurm array over it.
cd /project/pengqihang/b700/B704 || exit 1

: > joblist_remaining.txt
n=0
idx=0
while IFS= read -r path; do
    path="${path%$'\r'}"
    [ -z "$path" ] && continue
    idx=$((idx + 1))
    f="jobs/$path/job.out"
    keep=0
    if [ ! -f "$f" ]; then
        keep=1
    elif ! grep -q 'ORCA TERMINATED NORMALLY' "$f" 2>/dev/null; then
        keep=1
    fi
    if [ "$keep" = "1" ]; then
        echo "$path" >> joblist_remaining.txt
        n=$((n + 1))
    fi
done < joblist.txt

echo "remaining=$n"
if [ "$n" -eq 0 ]; then
    exit 0
fi

sbatch --array="1-${n}" --partition=hpxg run_b704_conformers.sbatch joblist_remaining.txt
