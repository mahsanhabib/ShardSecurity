#!/bin/bash
# ============================================================================
# LONI / SLURM batch job: the real-client-code localnet arms on ONE node.
# Runs an equivocation/paired arm to completion (it self-loops episodes, so no
# interactivity is needed). Pick the arm with ARM=...:
#
#   cd artifact
#   sbatch --export=ALL,ARM=B-open  hpc/localnet.sbatch   # paired race, OPEN (killing run)
#   sbatch --export=ALL,ARM=B-gated hpc/localnet.sbatch   # Proposition-1 twin -> RULED_OUT
#   sbatch --export=ALL,ARM=A       hpc/localnet.sbatch   # real q_attack / T_acc
#   sbatch --export=ALL,ARM=C       hpc/localnet.sbatch   # fast-exit positive control
#
# Needs userspace `gaiad` (v19.2.0, the version arms A/C were validated on) and `jq`
# on PATH -- NO sudo/Docker required (they bind 127.0.0.1 ports on the allocated node).
# Easiest: scp the exact binaries you already validated in WSL (same sha256), e.g.
#   scp ~/sb-localnet/bin/gaiad ~/sb-localnet/bin/jq  loni:~/bin/
#   export GAIAD=$HOME/bin/gaiad JQ=$HOME/bin/jq
# or build gaiad v19.2.0 from source on the node (needs Go + outbound git):
#   git clone --depth 1 -b v19.2.0 https://github.com/cosmos/gaia && (cd gaia && make install)
# ============================================================================
#SBATCH -J shardbribe-localnet
#SBATCH -A loni_dl_tu_bih                  # LONI allocation
#SBATCH -p single                         # 1 node; raise -c for a larger committee
#SBATCH -N 1
#SBATCH -c 8
#SBATCH -t 04:00:00                       # arms oversample to EPISODES; give them room
#SBATCH -o slurm-%x-%j.out
#SBATCH -e slurm-%x-%j.err

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"                     # = artifact/
ARM="${ARM:?set ARM=A|C|B-open|B-gated, e.g. sbatch --export=ALL,ARM=B-open hpc/localnet.sbatch}"

# gaiad + jq must be reachable (env override or PATH). Fail fast with guidance.
export GAIAD="${GAIAD:-gaiad}" JQ="${JQ:-jq}"
command -v "$GAIAD" >/dev/null 2>&1 || { echo "ERROR: gaiad not found (set GAIAD=...; see header)" >&2; exit 1; }
command -v "$JQ"    >/dev/null 2>&1 || { echo "ERROR: jq not found (set JQ=...; see header)"   >&2; exit 1; }

# venv so run_arm.sh's --assemble step (run_all + make_tables) has numpy/pyyaml.
source "${SB_VENV:-$PWD/.venv-loni}/bin/activate" 2>/dev/null || true
export PYTHON="${PYTHON:-python}"

# scratch for node homes on the node's local/temp FS (fast, auto-cleaned). Override
# WORK/WORK_DST if your cluster prefers a different scratch path.
export WORK="${WORK:-${TMPDIR:-/tmp}/rq8-localnet-$SLURM_JOB_ID}"
export WORK_DST="${WORK_DST:-${TMPDIR:-/tmp}/rq8-destzone-$SLURM_JOB_ID}"
export EPISODES="${EPISODES:-40}"

echo "[localnet] ARM=$ARM gaiad=$($GAIAD version 2>&1 | head -1) EPISODES=$EPISODES ($(date))"
bash localnet/run_arm.sh "$ARM"           # add a 2nd arg --assemble to fold + regenerate
echo "[localnet] done ($(date)). New records under results/measured/; commit/copy them back."
