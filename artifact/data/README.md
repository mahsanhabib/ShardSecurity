# Corpus templates for the corroborative RQ8 arms

Two header-only CSV templates. Fill them with **real, verified** rows from primary
sources, then run `collect_reorg.py --corpus data/reorg_incidents.csv` and
`collect_postmortem.py --corpus data/exploits.csv` (or set their paths under
`rq8.endpoints.{reorg,postmortem}.corpus` and run `measure_all.py`). They ship
empty on purpose — do not invent timestamps; transcribe them.

All `t_*` fields are **Unix seconds** (UTC). On a block explorer, open the relevant
transaction/block and copy its timestamp.

## `reorg_incidents.csv` — the "beyond clawback" natural experiment

One row per source-chain reorg that affected a bridge deposit.

| column | meaning | where to get it |
|---|---|---|
| `chain` | source chain | — |
| `t_deposit_s` | source deposit tx timestamp | explorer (the tx later reorged out) |
| `t_fill_s` | destination fill timestamp | destination explorer / bridge dashboard |
| `t_repay_s` | solver repayment timestamp (blank if none) | bridge HubPool / settlement tx |
| `reorged_out` | was the source deposit reorged out? (true/false) | explorer reorg/uncle records |
| `solver_repaid` | did the solver get repaid? (true/false) | settlement tx presence |

Candidate events to research: the Ethereum **25 May 2022** 7-block reorg; deep
Polygon PoS reorgs; high-throughput-chain reorgs. The finding you are after: among
`reorged_out=true` rows, what fraction still have a `t_fill_s` (the user-leg value
settled despite the source reversal).

## `exploits.csv` — adversarial T_settle fast-tail

One row per documented bridge exploit / intent liquidity-exhaustion event.

| column | meaning |
|---|---|
| `name` | incident name (e.g. nomad, wormhole, ronin, horizon, multichain) |
| `chain` | chain |
| `t_value_created_s` | when the fraudulent/exploit value was created |
| `t_cashout_s` | when the attacker realized/cashed out (the fast leg) |
| `t_clawback_s` | when (if ever) it was clawed back (blank if none) |
| `clawback_landed` | did a clawback land? (true/false) |

Source timelines from the projects' incident postmortems and chain explorers. The
finding you are after: the **fast tail** of `t_cashout_s - t_value_created_s` —
real adversaries monetize far faster than honest transfers.
