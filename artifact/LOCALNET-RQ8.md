# LOCALNET-RQ8 — upgrading the RQ8 rehearsal to **real client code** on a self-run private devnet

This is the runbook for the one empirical step the paper still lists as *owed*: replacing
the **in-process shadow rehearsal** of the paired race / controls with a **measurement on
real consensus client code**, and filling the remaining `[pending]` cell (native-IBC
`T_settle`). It executes the `--backend rpc` path that `livemeasure._equivocation_rpc`
documents, and the `prereg/rq8-v1` Week-2/Week-4 arms.

> **This is not an attack.** Every step runs on a **private, isolated localnet** with a
> chain-id in `livemeasure.ALLOWED_EQUIVOCATION_CHAINS`, using **your own validator keys and
> your own genesis stake**. You self-equivocate **with your own key on your own chain**; you
> never bribe anyone, never touch a shared/mainnet network, and never move third-party funds.
> The equivocation trigger is chain-ID-gated and refuses any mainnet id at runtime. The
> passive `q_max` arm is read-only over already-public data. See
> `Paper/Section/ethical_considerations.tex`.

---

## ✅ EXECUTED (2026-06-17) — real client-code slash captured

Run end-to-end on a laptop (WSL2 Ubuntu, userspace `gaiad v19.2.0`, **no sudo**): a 2-validator
localnet (`val0` honest, `val1` equivocator) plus a **second instance of `val1`'s consensus key**
(two-nodes-one-key, fresh `node_key`, `double_sign_check_height=0`). `val0` observed `val1`'s
conflicting precommits and reported a real `DuplicateVoteEvidence`:

| Quantity | Value |
|---|---|
| infraction height / slash block | 163 / 164 |
| slash event | `reason=double_sign`, `burned_coins=5000000` (5%), **tombstoned**, jailed-until 9999 |
| `val1` tokens | `100000000 -> 95000000` (-5%) |
| **real `T_acc` (infraction -> slash)** | **1325 ms = 1.32 s (1 block)** |
| `q_attack` | `1.0` (slash at +1.3 s << 60 s stake-exit -> stake caught) |

Genuine Cosmos SDK `x/evidence`->`x/slashing` execution. It **upgrades the cooperative `T_acc^lo`**
from the in-process shadow rehearsal + passive public-data reads to **real client code**, confirming
"enforcement within ~1-2 blocks." Recorded in `results/measured/devnet-rpc-gaiad.jsonl` (+
`.meta.json`); appears in the RQ8 measured table as the **"gaiad v19 localnet (real)"** row (`n=1`,
`q_hat=1.00`, `T_acc=1.3 s`). Self-equivocation on an OWN isolated, chain-ID-gated localnet -- no
shared network, no bribery, no third-party funds.

> A tombstone is permanent per validator, so one validator = one slash (`n=1`); for a distribution,
> repeat with fresh validators / re-genesis. The bridge user-leg and controls remain as documented below.

---

## 1. What it upgrades (today → after this runbook)

| Quantity / cell | In-tree today | After the localnet run | Arm |
|---|---|---|---|
| `q_attack`, causal `T_acc` | in-process **shadow** rehearsal (`backend=shadow`) | **real client code** (`x/evidence`→`x/slashing`) on a private localnet | A |
| Adversarial `T_acc^hi` | real pooled-P90 **passive proxy** (`26.3 d`) | **active** evidence-suppression + eclipse on the fork | B |
| Fast-exit positive control | shadow rehearsal | real client code, short unbonding/evidence-age | C |
| Native-IBC `T_settle` = `\ArtifactTsettleIBC` | **`[pending]`** | measured on a two-zone IBC devnet (`collect_ibc.py`, already implemented) | D |
| Cooperative `T_acc^lo` (now block-resolution bounded, "~1–2 blocks") | one real incident set | tightened with **≥4-node** real-internet propagation timing | E |
| `q_max` provenance | public-archive RPC reads | re-derived against a **self-run `gaiad` archive node** | E |

After arms A–D the two rehearsal rows of Table~VII (`tab:measured`) become **real-client-code**
rows, and `\ArtifactTsettleIBC` stops being `[pending]`. Update the paper's "rehearsal, not
production" caveat to "real client code" **only for the arms actually re-run** — keep the honest
framing for anything still on `shadow`.

---

## 2. Prerequisites (infrastructure — the part that needs real machines)

| Need | For | Notes |
|---|---|---|
| `gaiad` (or any CometBFT app) binary | arms A–E | pin a version; record it in the meta |
| Docker / `localnet` tooling, or `gaiad testnet` | arms A–C | resettable single-chain localnet |
| **Two CometBFT nodes sharing one consensus key**, `double_sign_check_height=0` | arm A | the operator "footgun" that produces real `DuplicateVoteEvidence` |
| **Hermes** IBC relayer + a second zone | arm D | two-zone IBC devnet for the negative control |
| ≥4 small VMs in distinct regions, subscribed to consensus gossip | arm E | observe/propagate term that no simulator can supply |
| One **archive** node (`pruning=nothing`) | arm E | self-hosted re-derivation of `q_max` |
| `netem`/`iptables` (egress control on the equivocator/reporter) | arm B | delay/withhold evidence gossip + eclipse to protocol tolerance |

The read side needs only Python + `requests`/stdlib (already in the artifact); all of
`cosmos_rpc`, `ibc_relayer`, and the `parse_*` / `build_incident_record` helpers are
implemented and unit-clean.

---

## 3. Arm A — self-equivocation localnet → `q_attack`, causal `T_acc`

1. **Genesis** a single-chain localnet with mainnet-like params — `staking.UnbondingTime`,
   `evidence.max_age_duration` / `max_age_num_blocks` — and `chain-id = shardbribe-localnet-1`
   (must be in the allowlist).
2. Run **two nodes sharing ONE `priv_validator_key.json`**, `double_sign_check_height = 0`,
   so they sign conflicting precommits at the same height/round → real `DuplicateVoteEvidence`.
3. **Per episode**: trigger the conflicting vote; **submit an unbond** for the equivocator at the
   infraction height (`gaiad tx staking unbond …`); then read `/block`, `/block_results`,
   `/consensus_params`.
4. Assemble the record with the existing parsers (`parse_duplicate_vote_evidence`,
   `parse_slash_events`, `evidence_expiry_ms`, `build_incident_record`); **reset** the localnet
   and repeat. Episodes are resettable on a private chain → **N ≥ 40** (Wilson upper on
   `p_win=0` ≈ 0.09 at N=40).

`q_attack = Pr[t_slash_effective < t_withdraw_unslashable]` is now observed directly: did the
slash reach the stake before the equivocator's exit completed?

```bash
# after _equivocation_rpc is wired to your localnet (section 8):
python collect_devnet.py --backend rpc --chain-id shardbribe-localnet-1 \
    --rpc http://localhost:26657 --episodes 40
```

## 4. Arm B — evidence-suppression + eclipse → `T_acc^hi` (active, real code)

Same localnet; on each episode **withhold/delay** evidence gossip and **eclipse** the would-be
reporter up to protocol tolerance (`netem` delay + `iptables` peer drop), running the real
`x/evidence`→`x/slashing` paths. Records carry `tacc_bound="hi"`.

```bash
python collect_devnet.py --backend rpc --chain-id shardbribe-localnet-1 \
    --rpc http://localhost:26657 --suppress-evidence --suppress-ms 180000 --episodes 40
```

Report `T_acc^hi` as the **active-adversary** bound alongside the passive pooled-P90 proxy; the
structural `RULED_OUT` is evaluated against whichever is larger (the bias working against a rule-out).

## 5. Arm C — fast-exit positive control (real unbond, **observed** completion)

Re-genesis with **short** `UnbondingTime` (`C_UNBONDING`, default `1s`) + **short**
`evidence.max_age`, chain-id `fastexit-devnet-positive`. Then the equivocator submits a
**real `MsgUndelegate`** of part of its self-delegation (`gaiad tx staking unbond`,
`C_UNBOND_PCT`%) a few blocks **before** the double-sign (`C_UNBOND_LEAD_BLOCKS`), so the
unbonding **matures and pays out in full before the evidence is processed** → the stake
escapes on real client code. `q_attack` is then measured from the **observed**
`complete_unbonding` event vs the **observed** slash — not an analytic deadline:

- caught (clawback): the unbonding entry still existed when the slash was processed
  (`h_slash ≤ h_complete`; evidence runs in BeginBlock, before the staking EndBlocker that
  completes the unbond in the same block) **or** the returned amount came back reduced.
- escaped: the unbonding matured (full amount) in a strictly earlier block (`h_complete <
  h_slash`). `livemeasure._arm_c_exit` encodes the verdict into the two timestamps the frozen
  `estimate.py` rule compares, and stores the real `t_unbond_complete` / `unbond_caught` on
  the record.

> **Why the pre-infraction lead matters (honest caveat).** On stock Cosmos, an unbonding with
> `creation_height ≥ infraction_height` is **clawed back** — a naïve *post*-infraction unbond
> does **not** escape, and on a fast localnet would measure `q≈1`. A genuine real-code escape
> therefore requires the unbond to mature *before* the evidence lands (the `C_UNBOND_LEAD_BLOCKS`
> staging) or evidence to expire (arm B). This is a faithful, ungated "fast-exit" realization;
> the `realsystems.py` hypothetical row remains the design that lacks creation-height clawback
> entirely. Report whatever `q_attack` the chain actually yields. Verdict target: `OPEN-WINDOW`.

## 6. Arm D — two-zone IBC devnet → native-IBC `T_settle` (fills `\ArtifactTsettleIBC`)

This arm needs **no new code** — `collect_ibc.py` / `ibc_relayer` are implemented:

1. Stand up two zones (`ibc-devnet-zone-a`, `ibc-devnet-zone-b`) and a **Hermes** channel.
2. Send a packet from a **finalized** source header; find the `send_packet` heights on A and the
   `recv_packet`/`acknowledge_packet` heights on B (`block_search` for the events).
3. Run:
   ```bash
   python collect_ibc.py --src-rpc http://zone-a:26657 --dst-rpc http://zone-b:26657 \
       --src-heights <…> --dst-heights <…> --channel channel-0
   ```
The destination acts only on a **committed** source header ⇒ `T_settle ≥ T_acc` structurally ⇒
`RULED_OUT`. This writes `results/measured/ibc-devnet-negative.jsonl`, and `make_tables` then
fills `\ArtifactTsettleIBC` (currently `[pending]`).

## 7. Arm E — propagation timing (`T_acc^lo`) + self-archive `q_max`

- **≥4 dispersed listeners** subscribed to consensus gossip timestamp first-observation of the
  conflicting cert across the real internet → the observe/propagate term, tightening `T_acc^lo`
  below the "~1–2 blocks" floor.
- Re-run the passive arm against a **self-run archive node** instead of public RPCs:
  ```bash
  python collect_cosmos.py --rpc http://localhost:26657 --chain-id cosmoshub-4 --source rpc
  ```
  (read-only; re-derives `q_max` from your own archive, removing the public-endpoint caveat).

---

## 8. Wiring the `rpc` backend (`_equivocation_rpc`)

`collect_devnet.py --backend rpc` now threads `--rpc/--gaiad/--home` into
`livemeasure.equivocation_harness(..., backend="rpc")` → `_equivocation_rpc`, which **reuses the
existing read parsers**. What the Python owns vs. what the operator owns:

- **Python (implemented):** poll/read `/block`, `/block_results`, `/consensus_params`; parse the
  evidence/slash and (arm C) the `complete_unbonding` event; decide caught-vs-escaped in
  `_arm_c_exit`; tag `tacc_bound` and apply the measured suppression delay; emit the testbed-schema
  record (with `t_unbond_complete` / `unbond_caught`).
- **localnet kit (`run_episode.sh`, implemented):** the per-episode start/reset, and — for arm C —
  the real `gaiad tx staking unbond` of the equivocator's own stake, staged `C_UNBOND_LEAD_BLOCKS`
  before the double-sign, then handing the unbond height/amount to `collect_devnet`.
- **Operator (manual / infra):** the two-nodes-one-key node setup, tuning the double-sign trigger,
  and the `netem`/`iptables` suppression+eclipse for arm B. These are node-/network-level actions
  Python cannot perform through the RPC alone.

`_equivocation_rpc` raises a clear, actionable error if `--rpc` is unreachable or omitted, so the
network-free reproduction path is unchanged.

**Turnkey automation:** `artifact/localnet/` scripts this whole arm — fresh 2-validator genesis,
the two-nodes-one-key footgun, the per-episode double-sign + capture, and the `collect_devnet
--backend rpc` fold-in — for arms A and C at N episodes. Run `localnet/run_arm.sh A --assemble`
and `localnet/run_arm.sh C --assemble` on a gaiad-capable host. See `localnet/README.md`.

## 9. Assemble (unchanged, frozen)

The decision rule is frozen in `estimate.py` and does **not** change — only the *source* of the
records flips from `devnet-shadow` to `devnet-rpc`:

```bash
python run_all.py     --config configs/main.yaml      # RQ8 reads results/measured/*
python make_tables.py --input results/main.json --out ../Paper/Section/_generated
python plot_figures.py --input results/main.json --out figures/
cd ../Paper/IEEE && pdflatex main && bibtex main && pdflatex main && pdflatex main
# (and ../Paper/ACM likewise)
```

Then, in `Paper/Section/measured_evaluation.tex`, change "in-process rehearsal" → "real client
code" **only for the arms you actually re-ran**, and drop the corresponding "owed" items from the
"Results to date" paragraph and Limitation (3).

## 10. Division of labor

- **I can do now** (no infra): finish the `_equivocation_rpc` orchestration against a given RPC,
  the genesis/`config.toml`/`app.toml` templates, the unbond-tx and suppression toggles, and the
  `collect_devnet --backend rpc` plumbing — all clearly marked *untested without a live localnet*.
- **Needs real machines** (you / whoever runs infra): running the nodes, Hermes, the ≥4 listeners,
  and the archive node; triggering the double-sign and the eclipse. I cannot provision machines or
  run a consensus network from this environment.

Nothing here is run against a shared network; the only "live" element is your own isolated devnet.
