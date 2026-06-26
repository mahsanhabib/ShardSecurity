# 2 — Assemble the reorg + exploit corpora

**Why only you:** these timestamps must be **transcribed from primary sources**
(block explorers, project postmortems). They must not be invented — fabricated rows
would poison the measurement. That's a research + judgment task.

Fill the header-only templates (do not commit invented data):
- `artifact/data/reorg_incidents.csv`
- `artifact/data/exploits.csv`

Column meanings and sourcing are in `artifact/data/README.md`. All `t_*` fields are
**Unix seconds (UTC)** — open the tx/block on an explorer and copy its timestamp.

## 2a. Reorg natural-experiment (the "beyond clawback" test) — **highest value**
- [ ] Research source-chain reorgs that hit bridge deposits and record, per incident:
      `chain, t_deposit_s, t_fill_s, t_repay_s, reorged_out, solver_repaid`.
- [ ] Candidates to investigate: Ethereum **25 May 2022** 7-block reorg; deep Polygon
      PoS reorgs; other high-throughput-chain reorgs.
- **Goal:** among `reorged_out=true` rows, what fraction still have a `t_fill_s`
      (user-leg value settled despite the source reversal). Expect ≈ 1.
- **Done when:** `python collect_reorg.py --corpus data/reorg_incidents.csv` reports a
      user-leg-irreversible fraction over a non-trivial n.

## 2b. Exploit-postmortem fast-tail (corroborative)
- [ ] Record, per documented bridge exploit:
      `name, chain, t_value_created_s, t_cashout_s, t_clawback_s, clawback_landed`.
- [ ] Candidates: Nomad (Aug 2022), Wormhole (Feb 2022), Ronin (Mar 2022),
      Horizon (Jun 2022), Multichain (2023). Use each project's postmortem + explorers.
- **Goal:** the fast tail of `t_cashout_s − t_value_created_s` (adversaries cash out
      far faster than honest transfers).
- **Done when:** `python collect_postmortem.py --corpus data/exploits.csv` reports a
      median/fastest cash-out.

> Tip: start with 2a only — it's the load-bearing irreversibility evidence and a
> handful of well-documented reorgs is enough.

---
**Next:** [3-run-and-assemble.md](3-run-and-assemble.md).
