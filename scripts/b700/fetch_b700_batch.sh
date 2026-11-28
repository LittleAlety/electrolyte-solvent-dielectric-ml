#!/bin/bash
# Fetch a completed ORCA batch from the WHU cluster.
# Work lives on /project (500 GB quota); /home is capped at 1 GB and filling it is
# what silently killed the first SP attempt with "I/O OPERATION FAILED".
set -u
REMOTE=pengqihang@202.114.96.180
KEY="$HOME/.ssh/id_ed25519_whu"
STAGE="${1:?usage: fetch_b700_batch.sh STAGE [preflight|production]}"
KIND="${2:-production}"

if [ "$KIND" = "preflight" ]; then
  REMOTE_DIR="/project/pengqihang/b700/B701/preflight_12/package_${STAGE}"
  LOCAL="outputs/b700/B701_DFT/preflight_12/results_${STAGE}"
else
  REMOTE_DIR="/project/pengqihang/b700/B701/production_239/package_${STAGE}"
  LOCAL="outputs/b700/B701_DFT/production_239/results_${STAGE}"
fi

ssh -i "$KEY" -o BatchMode=yes "$REMOTE" "cd $REMOTE_DIR && \
  n=\$(find jobs -name job.out | wc -l) && \
  ok=\$(grep -l 'ORCA TERMINATED NORMALLY' jobs/*/job.out 2>/dev/null | wc -l) && \
  echo \"job.out=\$n terminated_normally=\$ok\" && \
  tar czf /tmp/${STAGE}_b700.tgz jobs"

mkdir -p "$LOCAL"
scp -q -i "$KEY" -o BatchMode=yes "$REMOTE:/tmp/${STAGE}_b700.tgz" "/tmp/${STAGE}_b700.tgz" || exit 1
rm -rf "$LOCAL/jobs"
tar xzf "/tmp/${STAGE}_b700.tgz" -C "$LOCAL"
echo "fetched: $(find "$LOCAL/jobs" -name job.out | wc -l) job.out files into $LOCAL"
