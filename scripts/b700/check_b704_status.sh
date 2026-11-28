#!/bin/bash
# B704 status report: list missing / failed conformer jobs
cd /project/pengqihang/b700/B704
n_total=0
n_ok=0
while IFS= read -r path; do
    path="${path%$'\r'}"
    [ -z "$path" ] && continue
    n_total=$((n_total + 1))
    f="jobs/$path/job.out"
    if [ ! -f "$f" ]; then
        echo "MISSING $path"
    elif ! grep -q 'ORCA TERMINATED NORMALLY' "$f" 2>/dev/null; then
        echo "FAILED $path"
    else
        n_ok=$((n_ok + 1))
    fi
done < joblist.txt
echo "TOTAL=$n_total OK=$n_ok"
