# MEASUREMENT — executing the RQ8 live measurement (turnkey runbook)

This is the ordered, copy-pasteable runbook for the pre-registered measurement of
the load-bearing quantities `q`, `T_acc`, `T_settle` on real deployed systems,
defined in [`PREREGISTRATION-rq8.md`](PREREGISTRATION-rq8.md) (tag `prereg/rq8-v1`).
It produces the dual verdict the paper needs: the **same instrument** returns
**RULED_OUT** on the finality-gated paths and **OPEN** on a fast-settlement path,
flanked by a calibrated negative and positive control.

Everything here writes one JSONL per path into `results/measured/`. That directory
is consumed by `run_all.py` (RQ8) → `make_tables.py`, which fill the `[pending]`
placeholders in [`../Paper/Section/measured_evaluation.tex`](../Paper/Section/measured_evaluation.tex).
The reproduction path itself stays **network-free**: collection is a separate,
out-of-band step.

> **Safety (enforced, not just documented).** The equivocation leg runs ONLY on a
> private chain-id in the localnet allowlist (`livemeasure.ALLOWED_EQUIVOCATION_CHAINS`);
> any mainnet/shared id is refused at runtime. Every other arm is strictly read-only
> over public ledger data or offline over curated corpora. No attack is mounted on
> any shared network. See `Paper/Section/ethical_considerations.tex`.

---

## TL;DR — one command

Fill in whatever endpoints you have under `configs/main.yaml → rq8.endpoints`
(URLs, heights, corpus paths), then:

```bash
python measure_all.py --dry-run     # show the plan: which arms run, which are skipped
python measure_all.py               # run every configured arm (writes results/measured/*)
python measure_all.py --assemble    # then run_all.py + make_tables.py to fill the paper
python measure_all.py --only cosmos # run a single arm
```

Anything left `null` is skipped with a message telling you exactly what to set.
The `devnet` shadow arm needs nothing external, so `python measure_all.py` already
produces the positive control out of the box. The steps below are what each arm
does and where to source its input; `measure_all.py` just runs them in order.

---

## 0. Prerequisites

```bash
pip install -r requirements.txt          # numpy, pyyaml, cryptography, matplotlib
```

| Arm | What you need to supply |
|---|---|
| Cosmos safe | a CometBFT **archive** RPC (self-run `gaiad` preferred) + double-sign evidence heights |
| IBC negative control | two CometBFT RPCs (a two-zone devnet) + packet-event heights |
| Bridge open target | an Across (or other intent-bridge) **subgraph** GraphQL URL |
| Devnet self-fill / positive control | nothing external — the `shadow` backend is in-process |
| Reorg natural-experiment | a curated reorg corpus (`.json`/`.csv`) you assemble from explorers |
| Exploit-postmortem tail | a curated exploit corpus (`.json`/`.csv`) |

All commands are run from `artifact/`. Each collector also writes a `*.meta.json`
provenance sidecar and a `*.sha256` content hash next to its JSONL.

---

## 1. Freeze the pre-registration (do this first)

Before touching any data, tag the protocol so the decision rule, ε, and sample
sizes are committed in advance:

```bash
git add PREREGISTRATION-rq8.md configs/main.yaml
git commit -m "Freeze prereg/rq8-v1"
git tag prereg/rq8-v1
# record the hash in configs/main.yaml: rq8.preregistration.hash
```

Sanity-check the estimator against the testbed oracle (must pass before you trust
any real number):

```bash
python -m shardbribe.estimate          # prints self_test(): ok=true, pwin/rho match
```

---

## 2. Safe target — Cosmos (RULED_OUT)  ·  `collect_cosmos.py`

Passive `q_max` and `T_acc^lo` from real double-sign slashes. The Cosmos *Hub* has
few such events; pool several zones to accumulate the dozen-ish the CI wants.

```bash
# auto-discover (needs an RPC with block-event indexing):
python collect_cosmos.py --rpc https://cosmos-rpc.publicnode.com --chain-id cosmoshub-4
# or supply heights from Mintscan/an indexer if search is disabled:
python collect_cosmos.py --rpc <archive-rpc> --heights 12345,2345678 --chain-id <zone>
```

Writes `results/measured/cosmoshub-4.jsonl`. Expected console line:
`q_max preview: <e>/<n> enforced before evidence-expiry -> q_max~<~1.0>`.
Verdict after step 7: **RULED_OUT** (structurally finality-gated; q≈1).

---

## 3. Negative control — native IBC (RULED_OUT)  ·  `collect_ibc.py`

Proves the instrument *can* return safe on a genuinely sharded cross-domain hop.

**Easiest (real public data, no infra):** auto-discover recent matched packets on a live
public channel (Cosmos Hub→Osmosis) and measure native-IBC `T_settle` read-only:

```bash
python collect_ibc_public.py   # -> results/measured/ibc-cosmoshub-osmosis-negative.jsonl
```

**Self-run two-zone devnet (optional, stronger):** find the heights carrying `send_packet`
(zone A) and `recv_packet` (zone B), then:

```bash
python collect_ibc.py \
  --src-rpc http://zone-a:26657 --dst-rpc http://zone-b:26657 \
  --src-heights 100,140,180 --dst-heights 105,146,188 --channel channel-0
```

Either writes a `structurally_gated=True` negative-control file. Verdict after step 7: **RULED_OUT**.

---

## 4. Open target — fast bridge settlement marginal  ·  `collect_bridge.py`

The seconds-scale **user leg** (the irreversible value) vs the clawback-gated
**solver leg**, from a bridge subgraph.

```bash
python collect_bridge.py --graph-url https://api.thegraph.com/subgraphs/name/<across-subgraph>
# if the live schema differs, override the query/keys:
python collect_bridge.py --graph-url URL --query @my_query.graphql \
  --deposits-key v3FundsDepositeds --fills-key filledV3Relays
```

Writes `results/measured/across-v3.jsonl`. Expected: `USER leg: median ~8s`.
On its own this path is **INDETERMINATE** (a settlement marginal); step 5 supplies
the paired p_win that flips it to **OPEN**.

---

## 5. Paired self-fill + positive control + adversarial T_acc  ·  `collect_devnet.py`

The `shadow` backend (in-process, built on the validated RQ6 testbed) produces the
paired `(T_settle, T_acc)` episodes, `q_attack`, and the adversarial `T_acc^hi`.

```bash
# (a) positive control: fast exit -> OPEN with a LOW q (the danger regime)
python collect_devnet.py --chain-id fastexit-devnet-positive --episodes 60 --unbond-lead-ms 60000

# (b) pair episodes INTO the bridge file to fire its OPEN verdict
python collect_devnet.py --chain-id across-v3 --out results/measured/across-v3.jsonl \
  --append --episodes 60

# (c) adversarial upper-bound T_acc^hi (evidence suppression) for the RULED_OUT side
python collect_devnet.py --chain-id fastexit-devnet-positive --suppress-evidence
```

Expected: `q_attack ~ 0.0` (fast-exit), `paired p_win ~ 1.0`. Verdicts after step 7:
`fastexit-devnet-positive` → **OPEN**, `across-v3` → **OPEN**.

> For the production measurement on real client code, swap `--backend rpc` and point
> it at a private cometbft two-nodes-one-key localnet (see `_equivocation_rpc`).

---

## 6. Corroborative arms (irreversibility + adversarial tail)

```bash
# reorg natural-experiment: do fills survive a source reorg? (beyond-clawback test)
python collect_reorg.py --corpus reorg_incidents.csv

# exploit-postmortem: how fast does a real adversary cash out? (T_settle fast tail)
python collect_postmortem.py --corpus exploits.csv
```

Corpus columns (CSV header or JSON list of dicts):
- reorg: `chain, t_deposit_s, t_fill_s, t_repay_s, reorged_out, solver_repaid`
- exploit: `name, chain, t_value_created_s, t_cashout_s, t_clawback_s, clawback_landed`

These are **corroborative** (reported INDETERMINATE as marginals): they shape the
`T_settle` distribution and supply the irreversibility evidence, not a verdict.

---

## 7. Assemble the verdict and fill the paper

```bash
python run_all.py    --config configs/main.yaml          # RQ8 reads results/measured/*
python make_tables.py --input results/main.json --out ../Paper/Section/_generated
python plot_figures.py --input results/main.json --out figures/

cd ../Paper/IEEE && pdflatex main && bibtex main && pdflatex main && pdflatex main
```

`make_tables.py` writes the measured macros (`\ArtifactQMaxCosmos`,
`\ArtifactCosmosVerdict`, `\ArtifactBridgePwin`, `\ArtifactBridgeVerdict`,
`\ArtifactCliffCosmos`, …) and `tab_measured.tex`; the RQ8 section then shows real
numbers instead of `[pending]`. When every measured macro is populated, apply the
camera-ready abstract/limitation rewrites in
[`../Paper/Section/_rq8_camera_ready_edits.md`](../Paper/Section/_rq8_camera_ready_edits.md).

---

## Minimum-viable path (read-only only, no devnet)

If devnet time is short, steps **2 + 4 + 6(reorg)** alone yield one measured
RULED_OUT (Cosmos) and the measured bridge user-leg `T_settle` + the reorg
irreversibility evidence — the dual finding from public data only. The bridge then
reports INDETERMINATE (paired arm omitted), reported honestly as "open window
indicated by settlement marginal; paired p_win pending."

---

## Expected end-state (`results/measured/`)

| File | Arm | Verdict |
|---|---|---|
| `cosmoshub-4.jsonl` | passive Cosmos | RULED_OUT |
| `ibc-devnet-negative.jsonl` | negative control | RULED_OUT |
| `across-v3.jsonl` | bridge + paired episodes | OPEN |
| `fastexit-devnet-positive.jsonl` | positive control | OPEN |
| `reorg-natural-experiment.jsonl` | irreversibility | corroborative |
| `exploit-postmortem.jsonl` | adversarial tail | corroborative |

Per-path verdicts, q intervals, T_acc/T_settle fits, ρ, p_win, and the
distance-to-cliff land under `results/main.json → rq8`, and in `tab_measured.tex`.

---

## Decision rule (frozen — from `estimate.apply_decision_rule`)

- **OPEN** iff one-sided 95% upper CI of `p_win` > ε (=0.05), the median-ρ CI
  excludes 1 from below, and G2 is clearable — evaluated against `T_acc^lo`.
- **RULED_OUT** iff structurally finality-gated, or one-sided 95% upper CI of
  `p_win` ≤ ε across every cell — evaluated against `T_acc^hi`.
- **INDETERMINATE** otherwise (including a settlement marginal with no paired
  `(T_settle, T_acc)`) — never a silent null.

Each verdict is evaluated against the `T_acc` bound working *against* its own claim.
