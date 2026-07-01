# N=4 Faithful Committee Fork — design (closes Tier-1 #1, attack side on real client code)

Goal: realize, on **real gaiad/CometBFT client code**, the paper's *necessary-and-sufficient*
attack condition — **F+1 distinct equivocators + an honest-vote split → two conflicting commit
certificates** — and then **real `x/evidence → x/slashing`** slashing **both** equivocators.

This is the gap the current kit does **not** cover. `setup_localnet.sh` is *two-nodes-one-key*:
**one** consensus key double-signs, producing `DuplicateVoteEvidence` but neither (a) `F+1=2`
*distinct* equivocators nor (b) the honest split into two real conflicting certificates. It
validates the **accountability** side only. This kit adds the **attack** side.

---

## 1. Parameters (smallest faithful committee)

`N = 3F+1` with `F = 1` ⇒ **N = 4**, commit quorum `Q = 2F+1 = 3`, equivocation floor `k = F+1 = 2`.

Quorum intersection (Lemma 1): any two `Q=3` certificates out of `N=4` overlap in
`≥ 2Q−N = 2 = F+1` signers — so two conflicting certs **force 2 distinct equivocators**. We realize
exactly that floor.

Four equal-power validators (25% each):

| Validator | Role | Runs as |
|---|---|---|
| `e1` | equivocator #1 | **two nodes** `e1a` (partition A) + `e1b` (partition B), SAME consensus key, `double_sign_check_height=0` |
| `e2` | equivocator #2 | **two nodes** `e2a` (A) + `e2b` (B), SAME consensus key |
| `h1` | honest, branch A | one node, partition A only |
| `h2` | honest, branch B | one node, partition B only |

6 node homes total. Equal power so **each partition of 3 validators = 75% ≥ 2/3** and can commit.

---

## 2. How the two conflicting certificates form (same height AND same round)

For a real `DuplicateVoteEvidence` the two conflicting precommits must be at the **same
`(height H, round r)`** (different rounds ≠ duplicate vote). The construction:

```
        partition A  {e1a, e2a, h1}                 partition B  {e1b, e2b, h2}
  p2p:  peer only within A                          peer only within B
  H,r0: proposer = e1 (deterministic). e1a proposes block A   e1b proposes block B
        (A and B differ: each partition's mempool holds a      (a DIFFERENT spend of the
         DIFFERENT spend of e1/e2's coins — a real             SAME coins → real double-spend
         shard-local double-spend)                              = the value the certs encode)
  precommit(H,r0): {e1a,e2a,h1} sign block A         {e1b,e2b,h2} sign block B
  commit:  3/4 ≥ 2/3 → A commits at H                3/4 ≥ 2/3 → B commits at H
```

`e1` and `e2` each precommit **both** A and B at `(H, r0)` (across their two nodes) → genuine
duplicate-vote equivocation by **2 distinct validators**. `h1` precommits only A, `h2` only B —
the **honest split** ($\psucc$ realized live, via leader equivocation, not assumed).

> This is leader equivocation engineering the split — the exact $\psucc$ mechanism the threat
> model grants "with bounded probability" — now *demonstrated*, not modeled.

### Capturing the evidence + the slash
After both partitions commit `H` (read each partition's `/commit?height=H` — they return
**different `block_id`s** = the conflict), **heal** the partition (add cross-partition peers /
restart with the full peer set). The conflicting precommits gossip; CometBFT forms
`DuplicateVoteEvidence` for `e1` **and** `e2`; the next block includes it; `x/slashing`
tombstones + slashes **both**. We read the two slash events via the existing `parse_slash_events`.

**Honesty caveat (documented in the runbook):** post-heal reconciliation of two finalized blocks at
the same height is the finicky part — nodes that committed A may reject B as a conflicting commit
and halt rather than smoothly continue. Mitigations the kit uses: (i) a low-power **observer** full
node peered to both partitions that collects the cross-partition precommits and can surface the
evidence even if a partition halts; (ii) the structural record (two conflicting `/commit`s with the
intersecting equivocator set) is captured **before** heal, so the *attack-side* proof (Lemma 1 +
honest split realized) stands on the two real certs regardless of how cleanly the slash post-heal
lands. The slash leg reuses arm A's proven path (mainnet-like params, real `q≈1`).

---

## 3. What the record proves (vs. the existing arms)

| Arm | Equivocators | Certs | Honest split | What it shows |
|---|---|---|---|---|
| A (existing) | 1 key | evidence only | none | accountability real (`T_acc`, `q≈1`) |
| C (existing) | 1 key | evidence only | none | fast-exit escapes (`q→0`) |
| B (existing) | 1 key | — | — | settlement vs. accountability race (Prop. 1) |
| **N4 (this)** | **2 distinct** | **2 conflicting (real)** | **realized (h1\|h2)** | **Lemma 1 floor + $\psucc$ on real client code** |

New `MeasuredRecord` fields: `committee_size` (N), `quorum_size` (Q), `n_equivocators`,
`n_honest_split`, `quorum_intersection_ok`, `conflicting_certs`, `n_slashed`. The record still
carries `t_infraction/t_slash/T_acc` so it flows through `estimate_path` like arm A (now with N=4,
2 distinct validators slashed).

---

## 4. Files (to be added)

- `shardbribe/livemeasure.py`: `parse_commit_signers`, `parse_committee_fork`,
  `assemble_committee_record` (pure, offline-tested).
- `tests/test_livemeasure_committee.py`: feeds synthetic two-partition `/commit`s, asserts
  `n_equivocators==2`, `quorum_intersection_ok`, `conflicting_certs`, both slashed.
- `localnet/setup_committee.sh`: N=4 genesis + 6-node partitioned topology (template = the
  verified `setup_localnet.sh`).
- `localnet/run_committee.sh` (+ `run_episode.sh` `N4` branch): bring up partitions isolated,
  inject the two double-spends, drive both to commit `H`, capture both `/commit`s, heal, collect
  the two slashes, fold a `committee-fork-rpc` record.
- `N4-COMMITTEE.md`: runbook (run on one box / one interactive LONI node; **no HPC needed**).

Offline-verifiable here; the live run is the operator's step (same class as A/C/B bring-up).
