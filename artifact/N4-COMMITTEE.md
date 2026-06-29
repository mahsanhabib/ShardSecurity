# N4-COMMITTEE — the faithful committee fork on **real client code** (closes the attack side)

Runbook for the experiment that closes **Tier-1 #1 (attack side)** in `REVIEW-paper-gaps.md`:
realize, on **real gaiad/CometBFT**, the paper's *necessary-and-sufficient* condition —
**F+1 distinct equivocators + an honest-vote split → two conflicting commit certificates** — then
**real `x/evidence → x/slashing`** on **both** equivocators.

The existing arms (A/C/B) are all **two-nodes-one-key**: a *single* key double-signs. They validate
the **accountability** side (`T_acc`, `q`) and the **settlement race** (Prop. 1), but never produce
`F+1=2` *distinct* equivocators or the honest split into two real certificates. This arm does.

> **This is not an attack.** Runs on a **private, isolated localnet** with chain-id
> `shardbribe-committee-1` (in `livemeasure.ALLOWED_EQUIVOCATION_CHAINS`), your own keys, your own
> genesis stake. You self-equivocate **with your own keys on your own chain** and double-spend
> **between your own accounts**. The equivocation leg is chain-ID-gated and refuses any shared id at
> runtime. See `Paper/Section/ethical_considerations.tex`.

Design rationale + topology diagram: **`N4-COMMITTEE-DESIGN.md`** (read it first).

---

## 1. What it produces

`N = 3F+1` with `F = 1` ⇒ **N=4, Q=2F+1=3, floor k=F+1=2**. Four equal-power validators
(25% each); two of them (`e1,e2`) equivocate, two (`h1,h2`) split:

```
 partition A {e1a,e2a,h1} --commit block A at (H,r0)--.        the two /commit certs share
 partition B {e1b,e2b,h2} --commit block B at (H,r0)--+--->   {e1,e2} = F+1=2 equivocators
   (each partition = 3/4 = 75% >= 2/3, so each commits)         h1|h2 = the honest split
   block A != block B  (a real double-spend of e1's coins: e1->h1 in A, e1->h2 in B)
 heal --> conflicting precommits gossip --> DuplicateVoteEvidence(e1) AND (e2) --> both slashed
```

One `results/measured/committee-fork-rpc.jsonl` record with:
`committee_size=4, quorum_size=3, n_equivocators=2, n_honest_split=2, conflicting_certs=true,
quorum_intersection_ok=true, n_slashed=2, T_acc=<real>` (real x/slashing of both).

---

## 2. Prerequisites (same host as arms A/C/B)

| Need | Notes |
|---|---|
| WSL2 Ubuntu, userspace `gaiad v19.2.0` on PATH (no sudo/Docker) | same binary as A/C/B (`~/sb-localnet/bin/gaiad`) |
| `jq` + `curl` on PATH | `jq` already staged next to `gaiad`; `curl` for the RPC polls |
| the artifact staged in WSL (`~/sb-artifact`) | G: mount is invisible to WSL — stage via `\\wsl.localhost\Ubuntu\...` |
| free ports `41xxx`/`42xxx` | env.sh defaults; never collides with src `36xxx` / dst `38xxx` |

Runs on **one machine** (a laptop or **one interactive LONI node**). **No HPC needed** — it is
orchestration of real daemons, not compute (same guidance as Arm B §7).

---

## 3. Run it (in WSL)

```bash
cd ~/sb-artifact/artifact/localnet
bash run_committee.sh                 #  -> results/measured/committee-fork-rpc.jsonl
# or fold straight into RQ8 (run_all+make_tables run on Windows if WSL python lacks numpy):
bash run_committee.sh --assemble
```

`run_committee.sh` genesis-es the N=4 committee, starts the 6 partitioned nodes, injects the
double-spend, **scans for a height `H` where the two partitions' certs conflict at the same
`(H,round)` with ≥2 shared signers**, captures it, **heals**, and collects the real slash of both
equivocators.

Tune via env vars (defaults in `env.sh`): `N4_FORK_HEIGHT`, `N4_MAX_ATTEMPTS`, `N4_DOUBLESPEND_AMT`,
`N4_HEAL_WAIT`, `N4_SLASH_WINDOW`, `N4_TIMEOUT_COMMIT`, `N4_VAL_STAKE`.

### The flaky part (expect first-run tuning, like A/C/B)
A genuine `DuplicateVoteEvidence` needs the two conflicting precommits at the **same round**, which
requires the **round-0 proposer to be a shared equivocator** (`e1`/`e2`) so it proposes a *different*
block in each partition. When the round-0 proposer is an honest node (`h1`/`h2`, present in only one
partition), the other partition advances a round and the conflict lands at *different* rounds — not a
duplicate vote. The driver therefore **injects + scans in a retry loop** (`N4_MAX_ATTEMPTS`), exactly
as `run_arm.sh` oversamples the double-sign trigger. If it exhausts attempts: raise
`N4_MAX_ATTEMPTS`, and check `$WORK_N4/*/node.log` for which validator proposed at the target height.

### Honest caveat (documented, not hidden)
After heal, CometBFT may **halt one partition** on the conflicting-apphash rather than smoothly
continue. That is acceptable: the **structural fork at `H` is captured before heal**, so the
attack-side proof (two real conflicting certs + the `{e1,e2}` intersection + the `h1|h2` split)
stands regardless. If the post-heal slash does not land, the record carries
`quorum_intersection_ok=true` with `n_slashed=0` (the slashing path is already proven by arm A on
the same params); re-run or raise `N4_HEAL_WAIT`/`N4_SLASH_WINDOW` to catch both slashes.

---

## 4. Offline verification (no localnet) — run before and after

```powershell
python tests/test_livemeasure_committee.py   # 37 checks: 2 distinct equivocators, honest split,
                                             # conflict at same (H,round), both slashed; floor
                                             # fails on no-conflict / diff-round / single-equivocator
```

This proves the pure record/verdict logic. The WSL run supplies the real certs + slash times.

---

## 5. What it adds to the paper

A new measured row showing the **composed attack's necessary-and-sufficient conditions realized on
real client code** at the smallest faithful committee (N=4): the Lemma-1 quorum-intersection floor
(2 distinct equivocators) **and** the honest split ($\psucc$) — the half the A/C/B arms could not
exhibit. Combined with Arm B (value across a real settlement layer, knob flips OPEN↔RULED_OUT), the
two together answer the reviewer's "you never ran the composed attack on real code."

The make_tables row/flip wiring for this stem is **not yet added** (mirrors how arm C/B were staged:
data lands first, prose flips second). Once `committee-fork-rpc.jsonl` exists, wire a
`committee_fork` macro/row in `make_tables.py` keyed off the stem — left as the post-run paper step.

---

## 6. Division of labor

* **Implemented + offline-verified here:** the record schema fields, `parse_commit_signers` /
  `parse_committee_fork` / `assemble_committee_record` / `committee_harness` (livemeasure.py), the
  `collect_devnet.py --committee` plumbing, `setup_committee.sh` + `run_committee.sh`, the
  `shardbribe-committee-1` allowlist entry, and `tests/test_livemeasure_committee.py` (37 checks pass).
* **Needs the gaiad host (you, in WSL):** running `run_committee.sh`. It starts real consensus nodes
  and broadcasts real txs — the step that cannot be done from the authoring environment. Authored
  against the v0.50/gaiad-v19 recipe (as A/C/B were); expect the same class of first-run tuning the
  A/C bring-up needed (ports, fee genesis, and here the same-round proposer trigger).

Nothing runs against a shared network; the only "live" elements are your own isolated partitions.
