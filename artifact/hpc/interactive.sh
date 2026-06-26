#!/usr/bin/env bash
# Allocate an interactive LONI compute node and drop into a shell ON it, so you can
# run the localnet arms by hand and watch them. SLURM allocates the node the moment
# this srun is granted; you are then no longer on the login node.
#
#   cd ShardSecurity/artifact
#   bash hpc/interactive.sh            # waits in queue, then gives you a shell on the node
#   # --- now ON the compute node: ---
#   bash hpc/setup_env.sh             # once per node/env
#   export GAIAD=$HOME/bin/gaiad JQ=$HOME/bin/jq      # (localnet arms only)
#   bash localnet/run_arm.sh B-open   # or B-gated / A / C
#
# Override any knob inline, e.g.:  PART=checkpt CORES=16 TIME=06:00:00 bash hpc/interactive.sh
set -euo pipefail
ALLOC="${ALLOC:-loni_dl_tu_bih}"     # LONI allocation (billed account)
PART="${PART:-single}"               # partition -- verify with `sinfo -s` (single/checkpt/workq)
NODES="${NODES:-1}"
CORES="${CORES:-8}"
TIME="${TIME:-04:00:00}"             # walltime HH:MM:SS

echo "[interactive] requesting $NODES node x ${CORES} cores for $TIME on -A $ALLOC -p $PART ..."
echo "[interactive] (Ctrl-C to give up the queue wait; 'exit' on the node releases it)"
exec srun -A "$ALLOC" -p "$PART" -N "$NODES" -n 1 -c "$CORES" -t "$TIME" --pty /bin/bash
