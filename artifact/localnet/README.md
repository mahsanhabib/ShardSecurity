# RQ8 self-equivocation localnet kit — arms A & C (real client code)

Turns the **one-off** real gaiad double-sign you already captured
(`results/measured/devnet-rpc-gaiad.jsonl`, n=1) into the **full** real-client-code
arms, replacing the in-process `shadow` rehearsal for:

| Arm | What it measures | Output stem |
|---|---|---|
| **A** | attack-conditional `q_attack` + causal `T_acc` on **mainnet-like** params (slash catches the timed exit → `q≈1`; corroborates the safe side on real `x/evidence`→`x/slashing`) | `devnet-rpc-gaiad.jsonl` (grown to n=N) |
| **C** | **fast-exit positive control**: the equivocator submits a **real `MsgUndelegate`** a few blocks before the double-sign; with short unbonding it **matures (full payout) before the slash** → stake escapes → `q≈0` → **OPEN**. q is read from the **observed** `complete_unbonding` vs the observed slash (not analytic). | `fastexit-devnet-positive-rpc.jsonl` |

The frozen decision rule in `estimate.py` is unchanged — only the *source* of the
records flips from `devnet-shadow` to `devnet-rpc`.

> ⚠️ **Authored against your documented recipe, NOT executed here.** This kit was
> written on a machine with no gaiad/Docker. The genesis surgery and the
> double-sign trigger are version- and timing-sensitive; **your first run is the
> validation**. Expect to tune (see Troubleshooting).

## Prerequisites (the part that needs a real machine)

- `gaiad` **v19.2.0** on `PATH` (the version in your n=1 run; others may need jq-path tweaks), `jq`, `python3`, `curl`.
- A POSIX shell (your documented env: **WSL2 Ubuntu, no sudo**). No Docker, no root.
- Run from this directory. Everything lives under `$WORK` (default `/tmp/rq8-localnet`); nothing touches the system.

## Run

```bash
chmod +x *.sh
# smoke test ONE episode of each arm first (cheap; confirms the trigger fires):
EPISODES=1 ./run_arm.sh A
EPISODES=1 ./run_arm.sh C
# then the full arms (N>=40) and fold into the paper:
EPISODES=40 ./run_arm.sh A --assemble
EPISODES=40 ./run_arm.sh C --assemble
```

`--assemble` runs `run_all.py` + `make_tables.py`, so `tab_measured.tex` gets a
real `devnet-rpc-gaiad` row at n=N and a new `fastexit-devnet-positive (real code)`
row. Tunables (powers, params, ports, timeouts) are env vars in `env.sh`.

## Files

- `env.sh` — all config (binaries, ports, per-arm genesis params, N, timeouts).
- `lib.sh` — preflight (incl. the chain-id allowlist gate), RPC polling, evidence scan, genesis jq edits, teardown.
- `setup_localnet.sh <A|C>` — fresh 2-validator genesis + the two-nodes-one-key equivocator (`val0` majority for liveness, `val1a`+`val1b` share one consensus key, `double_sign_check_height=0`).
- `run_episode.sh <A|C> <out.jsonl> <unbond_lead_ms>` — start nodes, induce the double-sign, capture the infraction height, fold one record in via `collect_devnet.py --backend rpc`.
- `run_arm.sh <A|C> [--assemble]` — loop N fresh-genesis episodes (tombstone is permanent → one slash per genesis), then assemble.

## After a successful run — update the paper

In `Paper/Section/measured_evaluation.tex` and `limitations.tex`, for **only the
arms you actually re-ran**, change "in-process rehearsal" → "real client code" and
drop the matching owed item. The fast-exit positive control and the paired race are
the rehearsal lines to retire; keep the caveat for anything still on `shadow`.
(Arm C lands in a separate `-rpc` stem so the shadow baseline is preserved until
you choose to swap the row.)

## Troubleshooting (the trigger is the flaky part)

- **No `DuplicateVoteEvidence` within the timeout.** Two same-key nodes only
  *sometimes* sign conflicting votes. Increase `DBLSIGN_TIMEOUT`, confirm both
  `val1a`/`val1b` are validating (`val*/node.log`), and that `val0` keeps >2/3
  power so the chain doesn't halt when `val1` is jailed. Stagger `val1b`'s start.
- **Chain halts after the slash.** `val0` lacks a super-majority — raise `VAL0_STAKE` vs `VAL1_STAKE`.
- **jq path errors in genesis.** Evidence params moved to `.consensus.params.evidence`
  in cosmos-sdk v0.50; older builds use `.consensus_params.evidence` (handled), but
  other params may differ across gaiad versions.
- **Arm C never escapes (always `q≈1`).** This is the **clawback**: an unbonding with
  `creation_height ≥ infraction_height` is slashed in full. Raise `C_UNBOND_LEAD_BLOCKS` (submit
  the unbond earlier) and/or shorten `C_UNBONDING` so the unbond **matures before the evidence is
  processed**; raise `UNBOND_WATCH_BLOCKS` if `complete_unbonding` lands outside the scan window.
  A persistent `q≈1` on real gaiad is itself an honest finding (naïve post-infraction fast-exit is
  defeated by clawback) — report it rather than forcing the escape.
- **`unbond broadcast failed` / `key not found`.** Confirm `val1` is in `$H1`'s test keyring
  (`gaiad keys list --keyring-backend test --home $WORK/val1a`) and that `val1a` keeps enough
  self-delegation after `C_UNBOND_PCT`% to stay bonded and able to double-sign.

## Safety

The equivocation leg is hard-gated to `livemeasure.ALLOWED_EQUIVOCATION_CHAINS`
(`preflight` re-checks before genesis). Self-equivocation on your **own isolated,
chain-ID-gated localnet** only — never a shared testnet/mainnet, no bribery, no
third-party funds. See `Paper/Section/ethical_considerations.tex`.
