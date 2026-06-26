# Running on LONI (HPC) — pull and run

Self-contained SLURM harness for the `Priced to Equivocate` artifact. Two workloads:

| Job | Needs | What it is |
|---|---|---|
| `hpc/montecarlo.sbatch` | python venv only | the seeded MC + analysis pipeline (`run_all.py` → `results/main.json`, figures, tables). **The ideal HPC job** — pure compute, no network, no gaiad. |
| `hpc/localnet.sbatch` | gaiad v19.2.0 + jq + venv | the real-client-code localnet arms (A / C / **B-open** / **B-gated**) on one node. |

> The **paired "killing run"** (`B-open` + `B-gated`) does **not** need HPC — it runs fine on a
> laptop and only needs *one* node here. LONI's real value is the MC sweeps (`montecarlo.sbatch`)
> and, if you want to tighten `T_acc^lo`/`q_max`, a larger-committee localnet or self-run archive
> node. See `artifact/LOCALNET-RQ8-PAIRED.md` §7 for the full split.

## 0. One-time setup (login node)

```bash
git clone git@github.com:mahsanhabib/ShardSecurity.git
cd ShardSecurity/artifact
bash hpc/setup_env.sh                 # creates .venv-loni with numpy/matplotlib/pyyaml/cryptography
```

Edit the two `.sbatch` files and set `#SBATCH -A REPLACE_WITH_YOUR_ALLOCATION` to your LONI
allocation (check `balance` / `qshow`). Adjust `-p`/`-c`/`-t` to your cluster's partitions.

## 1. Monte-Carlo / analysis pipeline (no gaiad)

```bash
cd artifact
sbatch hpc/montecarlo.sbatch
squeue -u $USER                       # watch
tail -f slurm-shardbribe-mc-*.out
```
Outputs `results/main.json` (RQ0–RQ8), `figures/*.pdf`, and `_generated_loni/*.tex`. Copy
`results/main.json` back to your laptop to regenerate the paper tables (`Paper/` is intentionally
not built here).

## 2. Real-client-code localnet arms (needs gaiad)

Put `gaiad` (v19.2.0 — the version arms A/C were validated on) and `jq` on PATH first. Easiest is to
**scp the exact binaries you already validated in WSL** (identical sha256) — see the header of
`hpc/localnet.sbatch` for both that and the build-from-source option.

```bash
cd artifact
export GAIAD=$HOME/bin/gaiad JQ=$HOME/bin/jq
sbatch --export=ALL,ARM=B-open  hpc/localnet.sbatch   # paired race -> across-v3-selffill-rpc.jsonl (OPEN)
sbatch --export=ALL,ARM=B-gated hpc/localnet.sbatch   # Prop-1 twin -> across-v3-paired-gated-rpc.jsonl (RULED_OUT)
```

New records land in `results/measured/`. Commit them (or copy back to the laptop), then on the
laptop run `python run_all.py --config configs/main.yaml` + `python make_tables.py …` to flip the
paper from "shadow rehearsal" to "real client code" (data-gated; nothing edited by hand).

## 3. Verify offline first (any machine, no gaiad)

```bash
source .venv-loni/bin/activate
python tests/test_livemeasure_paired.py   # 18 checks: OPEN->OPEN, gated->RULED_OUT, knob flips verdict
python tests/test_model.py                # 13 model/testbed checks
```

## Notes
- All localnet equivocation is chain-ID-gated to private localnet ids and binds only `127.0.0.1` on
  the allocated node — nothing touches a shared network.
- `WORK` / `WORK_DST` default to the node's `$TMPDIR`; override if your cluster prefers project
  scratch.
- Cluster specifics (partition names, `module load python` version, allocation) vary across LONI
  machines (QB3/SuperMike/etc.) — the `.sbatch` headers are commented placeholders; edit to match.
