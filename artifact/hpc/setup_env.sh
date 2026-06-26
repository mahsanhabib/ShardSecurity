#!/usr/bin/env bash
# One-time environment bootstrap for running the artifact on LONI (or any SLURM HPC).
# Creates a self-contained Python venv with numpy/matplotlib/pyyaml/cryptography.
# Idempotent: re-running just re-activates the existing venv.
#
#   cd artifact && bash hpc/setup_env.sh
#
# gaiad is NOT installed here -- only the Monte-Carlo / analysis pipeline needs this
# venv. The localnet arms additionally need a gaiad binary; see hpc/localnet.sbatch.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # artifact/
VENV="${SB_VENV:-$HERE/.venv-loni}"

# LONI ships Python as an environment module. Adjust the version to what `module avail
# python` lists on your cluster (e.g. python/3.12.x-anaconda). Harmless if `module`
# is absent (a plain `python3` on PATH is then used).
if command -v module >/dev/null 2>&1; then
  module load python 2>/dev/null || module load python/3.12 2>/dev/null || true
fi
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "ERROR: python3 not found; module load python first" >&2; exit 1; }

if [ ! -d "$VENV" ]; then
  echo "[setup_env] creating venv at $VENV"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip >/dev/null
python -m pip install -r "$HERE/requirements.txt"
echo "[setup_env] OK. Activate later with:  source $VENV/bin/activate"
python -c "import numpy, matplotlib, yaml, cryptography; print('[setup_env] deps import OK')"
