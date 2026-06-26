# Artifact — *Priced to Equivocate*

Reproducible simulation/analysis artifact for the paper **"Priced to Equivocate:
Sub-Threshold Committee Bribery and the Accountability Race in Sharded
Blockchains."**

Every figure and table in the paper is regenerated from this directory by two
commands. The artifact is **safe and local-only**: it never contacts a network,
targets no live system, and handles no real funds or keys. All randomness is
seeded, so results are deterministic given `configs/main.yaml`.

## What is here

| Path | Role |
|---|---|
| `shardbribe/model.py` | Closed-form model: equivocation floor, `psucc`, bribe cost `B`, race `pwin`, profit, the two viability gates. |
| `shardbribe/quorum.py` | Monte-Carlo BFT committee/quorum simulator; reproduces the closed-form `psucc`. |
| `shardbribe/bft_harness.py` | Abstract HotStuff/Tendermint-style committee harness with real (toy) signatures; **produces verifiable equivocation evidence**. |
| `shardbribe/escrow.py` | Model `PayToEquivocate` escrow: pays a bribe only on a valid equivocation proof (local logic). |
| `shardbribe/crossshard.py` | Cross-shard receipt + delayed-accountability processing; the object the race runs over. |
| `shardbribe/race.py` | Monte-Carlo accountability-race simulator (`Tsettle` vs `Tacc`). |
| `shardbribe/reconfig.py` | Epoch-boundary state/receipt-handoff model; per-design `E[Pi(a)]` across the epoch (designs A–F). |
| `shardbribe/testbed.py` | **Discrete-event BFT testbed with real Ed25519 signatures**: runs a commit round over a modeled network so `Tacc`/`Tsettle`/`pwin` are *measured* from a running protocol (cross-validates the model). |
| `shardbribe/realsystems.py` | Case study: applies the model to documented parameters of named deployed systems → exposure verdicts. |
| `run_all.py` | Runs all experiments; writes `results/main.json`; self-validates. |
| `plot_figures.py` | Regenerates all 12 figures (vector PDF). |
| `make_tables.py` | Regenerates the LaTeX data tables consumed by the paper. |
| `configs/main.yaml` | The single source of all parameters. |
| `tests/test_model.py` | Unit tests encoding the paper's load-bearing claims. |

## Reproduce everything

```bash
pip install -r requirements.txt

# 1. run all simulations (~70 s on a laptop; deterministic)
python run_all.py --config configs/main.yaml

# 2. regenerate every figure (PDF -> figures/)
python plot_figures.py --input results/main.json --out figures/

# 3. regenerate the LaTeX data tables consumed by the paper
python make_tables.py --input results/main.json --out ../Paper/Section/_generated
```

For a fast smoke run, add `--quick` to step 1 (scales Monte-Carlo trials down
~10×). Run the tests with:

```bash
python -m pytest tests/          # or: python tests/test_model.py
```

## Live measurement on deployed systems (RQ8)

The simulation above is network-free. The **pre-registered live measurement** of
`q`, `T_acc`, `T_settle` on real systems (RQ8) is a separate, out-of-band step with
its own runbook in **[`MEASUREMENT.md`](MEASUREMENT.md)** and protocol in
**[`PREREGISTRATION-rq8.md`](PREREGISTRATION-rq8.md)**. The collectors write
`results/measured/*.jsonl`, which `run_all.py` (RQ8) and `make_tables.py` fold into
the paper, filling the `[pending]` placeholders in `../Paper/Section/measured_evaluation.tex`.

| Collector | Arm | Expected verdict |
|---|---|---|
| `collect_cosmos.py` | passive Cosmos `q_max`/`T_acc^lo` | RULED_OUT |
| `collect_ibc.py` | native-IBC negative control | RULED_OUT |
| `collect_bridge.py` | fast-bridge `T_settle` (user/solver legs) | OPEN once paired |
| `collect_devnet.py` | paired self-fill, `q_attack`, `T_acc^hi`, positive control | OPEN, low q |
| `collect_reorg.py` | beyond-clawback irreversibility | corroborative |
| `collect_postmortem.py` | adversarial `T_settle` fast-tail | corroborative |
| `shardbribe/livemeasure.py` | collectors' shared parsers + the localnet safety gate | — |
| `shardbribe/estimate.py` | network-free estimators + the frozen decision rule | — |

The equivocation leg runs ONLY on a private chain-id in the localnet allowlist;
every other arm is read-only over public data or offline over curated corpora.

## What `run_all.py` checks

Before producing any results it self-validates and exercises the
proof-of-concept, and **fails loudly** if either breaks:

1. **Model validation.** The Monte-Carlo quorum harness must reproduce the
   closed-form `psucc` for every `(N, phi)` to within `tolerance` (default 0.02).
   The reported `max |psucc_mc - psucc_cf|` is ~0.006 at full trial counts.
2. **Floor check.** With `k < F+1` purchased equivocators, a conflicting
   certificate is *impossible*; the harness must report exactly zero successes.
3. **End-to-end PoC.** A committee of `N=31` (`F=10`) is driven to two
   conflicting certificates with the `F+1=11` floor under an engineered view
   split; the harness emits 11 valid equivocation proofs; the `PayToEquivocate`
   escrow pays exactly those 11 and rejects a forged (non-conflicting) proof.

## Mapping results → paper figures/tables

| Paper artifact | Produced by |
|---|---|
| Fig. 1 attack flow / Fig. 2 quorum / Fig. 5 handoff FSM | `plot_figures.py` (drawn programmatically) |
| Fig. 3 profit phase diagram `(rho, V)` | `rq3_profit` |
| Fig. 4 bribe cost vs `N` | `rq2_cost` |
| Fig. 6 `E[Pi(a)]` over the epoch | `rq4_reconfig` (designs A–F) |
| `pwin(rho)` threshold | `rq1_pwin` |
| `psucc` floor vs view-split (+ MC) | `floor_experiment` |
| profit heatmap `(q, V)` | `rq3_profit` |
| defense comparison | `rq5_defenses` |
| testbed measured-vs-analytical `pwin` | `rq6_testbed` (real Ed25519, modeled network) |
| real-systems exposure figure + table | `rq7_realsystems` |
| break-even + real-systems tables | `make_tables.py` |

## Configuration knobs (for a local BFT harness study)

All live in `configs/main.yaml`: committee size `N` (hence quorum `Q=2F+1` and
floor `F+1`), view-split `phi`, enforcement probability `q` / `q_base`, the
adversary's split-control reliability `psucc`, settlement and accountability
stage means (`settle_mean`, `acc_mean`) and their coefficients of variation,
epoch length `tau`, unbonding delay `U`, cross-epoch receipt/state latencies
(`Treceipt`, `Tstate`), the handoff penalty `Hmax`, Monte-Carlo `trials`, and
the master `seed`. The reconfiguration design is selected per-curve in
`shardbribe/reconfig.py` (`DESIGNS`).

## Ethics / safety

This artifact is a model. It does not implement a deployable attack: there is no
networking, no real signature scheme protecting value, and the `PayToEquivocate`
escrow is local Python with no currency. It exists to make the paper's claims
falsifiable and its figures reproducible. **No live network is targeted.**
