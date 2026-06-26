#!/bin/bash
# ============================================================================
# LONI / SLURM batch job: the full reproducible Monte-Carlo + analysis pipeline.
# This is the IDEAL HPC workload -- pure compute, no network, no gaiad, seeded and
# deterministic. Produces results/main.json, all figures, and the generated tables.
#
#   cd artifact
#   sbatch hpc/montecarlo.sbatch
#   # watch:  squeue -u $USER   ;  tail -f slurm-shardbribe-mc-*.out
# ============================================================================
#SBATCH -J shardbribe-mc
#SBATCH -A loni_dl_tu_bih                  # LONI allocation
#SBATCH -p single                         # single-node partition (this job is 1 node)
#SBATCH -N 1
#SBATCH -c 8                              # cores (numpy BLAS uses them); raise for big sweeps
#SBATCH -t 01:00:00                       # walltime (the default config runs in ~minutes)
#SBATCH -o slurm-%x-%j.out
#SBATCH -e slurm-%x-%j.err

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"                     # = artifact/ (submit from there)

# keep numpy from oversubscribing the allocated cores
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export OPENBLAS_NUM_THREADS="$OMP_NUM_THREADS"
export MPLBACKEND=Agg                      # headless matplotlib on compute nodes

source "${SB_VENV:-$PWD/.venv-loni}/bin/activate"  # created by hpc/setup_env.sh

CONFIG="${CONFIG:-configs/main.yaml}"
echo "[mc] run_all on $CONFIG  ($(date))"
mkdir -p _generated_loni
python run_all.py --config "$CONFIG"               # -> results/main.json (RQ0-RQ8)
python make_tables.py --input results/main.json --out _generated_loni   # tables (local copy)
python plot_figures.py --input results/main.json --out figures/         # 12 PDFs
echo "[mc] done ($(date)). results/main.json + figures/ + _generated_loni/ ready."
echo "[mc] copy results/main.json back to your laptop to regenerate the paper tables."
