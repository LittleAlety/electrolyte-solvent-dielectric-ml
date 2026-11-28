#!/bin/bash
# Package and fetch the B701 preflight results from the WHU cluster.
# Kept as a script file so nested quoting does not need to survive a remote shell.
set -u
REMOTE=pengqihang@202.114.96.180
KEY="$HOME/.ssh/id_ed25519_whu"
STAGE="${1:-sp}"
LOCAL="outputs/b700/B701_DFT/preflight_12/results_${STAGE}"
PKG="package_${STAGE}"

ssh -i "$KEY" -o BatchMode=yes "$REMOTE" "cd ~/b700/B701/preflight_12/$PKG && \
  n_out=\$(find jobs -name job.out | wc -l) && \
  n_ok=\$(grep -l 'TERMINATED NORMALLY' jobs/*/job.out 2>/dev/null | wc -l) && \
  echo \"job.out=\$n_out terminated_normally=\$n_ok\" && \
  tar czf /tmp/${STAGE}_out.tgz jobs"

mkdir -p "$LOCAL"
scp -q -i "$KEY" -o BatchMode=yes "$REMOTE:/tmp/${STAGE}_out.tgz" "/tmp/${STAGE}_out.tgz" || exit 1
rm -rf "$LOCAL/jobs"
tar xzf "/tmp/${STAGE}_out.tgz" -C "$LOCAL"
echo "fetched: $(find "$LOCAL/jobs" -name job.out | wc -l) job.out files"
