#!/bin/bash
# GFN2-xTB single point at fixed r2SCAN-3c geometry (no optimisation)
set -u
xtb xtb.xyz --sp --chrg 0 --uhf 0 --namespace sp > xtb_sp.out 2>&1
echo exit=$?
