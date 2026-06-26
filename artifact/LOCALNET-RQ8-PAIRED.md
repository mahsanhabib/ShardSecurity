# LOCALNET-RQ8-PAIRED — the paired race on **real client code** (the last rehearsal → real)

This is the runbook for the single empirical step the paper still lists as *owed*: replacing
the **in-process shadow rehearsal** of the **paired race** (`across-v3-selffill.jsonl`) with a
**real-client-code** measurement, and — with one knob flipped — a **live demonstration of
Proposition 1** (immunity by construction). It completes the `[pending]` item in the project
notes: *"the real-client-code (`--backend rpc`) re-derivation of the paired race on a private
localnet."*

It is the **killing-fix experiment** for an S&P/CCS/USENIX submission: one run, designed so it
closes three of the four reviewer objections at once (see §0).

> **This is not an attack.** Every step runs on a **private, isolated localnet** with chain-ids in
> `livemeasure.ALLOWED_EQUIVOCATION_CHAINS` (`shardbribe-localnet-1`, `ibc-devnet-zone-b`), using
> **your own validator keys and your own genesis stake**. You self-equivocate **with your own key
> on your own chain**, fill a value sink **between two of your own accounts**, and never touch a
> shared/mainnet network, never bribe anyone, never move third-party funds. The equivocation
> trigger is chain-ID-gated and refuses any mainnet id at runtime. See
> `Paper/Section/ethical_considerations.tex` and PREREGISTRATION-rq8.md §5.

---

## 0. Why this one run is the killing fix

The arm is engineered to be **assumption-light and self-defending**, so each soft spot dies to a
different property of the *same* experiment:

| Reviewer objection | Closed by |
|---|---|
| **#3** "strongest demo is a rehearsal" | real `gaiad` client code on both legs (equivocation→slash and source-cert→fill) |
| **#2** "no real exposed value path" | a real fast settlement leg (the dst-zone fill) races real accountability and **wins** |
| **#1** "needs the `psucc=0.85` view-control assumption" | the run reports profit at the **floor `psucc`** (see §6); the OPEN verdict does **not** use 0.85 |
| **#4** "immunity is just a design rule" | the **gated twin** (one knob flipped) *demonstrates* `pwin→0` — Proposition 1 as a live, verified defense |

The only door left is novelty framing, which is prose, not experiment.

---

## 1. Design — two zones, one knob

```
  SOURCE zone  (shardbribe-localnet-1)            DEST "bridge" zone (ibc-devnet-zone-b)
  val0 (honest majority)                          dstval (single validator, fast blocks)
  val1a + val1b  (two-nodes-one-key equivocator)  solver --[ fill V ]--> sink   (realised value)
        |  conflicting cert at t_infraction               ^
        |  real x/evidence -> x/slashing at t_slash       |  relayer.sh fronts the fill,
        |  => real T_acc (cooperative, q~1)               |  predicated on the source cert,
        v                                                 |  after GATE_DEPTH confirmations
  ============== relayer (single clock) ====================
  t_src_cert = first sight of source cert     t_dst_receipt = fill confirmed
  T_settle = t_dst_receipt - t_src_cert   (single relayer clock; no cross-chain skew, prereg T13)
```

* **Source accountability is REAL and strong** (arm-A mainnet-like params: `q≈1`, real slash in
  ~1–2 blocks). The window is opened **only by the settlement gate**, never by weakened slashing —
  the cleanest possible isolation of the paper's thesis ("fast settlement vs slow/weak
  accountability", `evaluation.tex`).
* **The knob is `GATE_DEPTH`** — how many source confirmations the relayer waits before filling:
  * **`B-open`** (`B_GATE_DEPTH_OPEN=1`, ungated): fills on the source commit, before
    accountability resolves → `T_settle ≪ T_acc` → **OPEN**.
  * **`B-gated`** (`B_GATE_DEPTH_GATED=12`, finality-gated, past the slash horizon): fills only
    after the cert is past `T_acc` → `T_settle ≥ T_acc` **and** `structurally_gated=True` →
    **RULED_OUT** by Proposition 1.
* **Timing is single-clock.** `relayer.sh` stamps both `t_src_cert` (first sight of the cert) and
  `t_dst_receipt` (fill confirmed) on its **own** wall clock, so `T_settle` is a single-clock delta
  with no cross-chain alignment problem. `T_acc` is read from the source chain
  (`t_slash − t_infraction`) by `collect_devnet`. Both are durations from the same `t=0` (the
  source conflicting cert), so the race is apples-to-apples. The relayer poll interval
  (`B_RELAYER_POLL_MS=50`) is recorded as `measurement_resolution_ms` (prereg T10).
* **Conservative evaluation.** The OPEN arm races the **cooperative** (un-suppressed) slash
  (`tacc_bound="lo"`), the bound that works *against* an OPEN claim (prereg §4.3). The dst zone runs
  **sub-second blocks** (`DST_TIMEOUT_COMMIT=200ms`) so the ungated fill confirms with a wide margin
  inside the ~1–2-block source slash.

---

## 2. Prerequisites (same host as arms A/C)

The exact environment the existing real-code arms already use:

| Need | Notes |
|---|---|
| WSL2 Ubuntu, userspace `gaiad v19.2.0` on PATH (no sudo/Docker) | same binary as arms A/C (`~/sb-localnet/bin/gaiad`) |
| `jq` static binary on PATH | already staged next to `gaiad` |
| the artifact staged in WSL (`~/sb-artifact`) | G: mount is invisible to WSL — stage via `\\wsl.localhost\Ubuntu\...` |
| free ports `36xxx` (source) and `38xxx` (dest) | env.sh defaults; the June-17 manual localnet on `26657/9090` is untouched |

No new infrastructure beyond arms A/C — Arm B reuses arm A's source localnet and adds **one
single-node zone** (the value sink) plus the relayer. It runs on **one machine** (a laptop).

---

## 3. Run it (in WSL)

```bash
cd ~/sb-artifact/artifact/localnet
# OPEN arm: ungated fast fill beats the real cooperative slash -> OPEN-WINDOW (real code)
bash run_arm.sh B-open                 #  -> results/measured/across-v3-selffill-rpc.jsonl
# Proposition-1 twin: finality-gated relayer -> T_settle >= T_acc -> RULED_OUT
bash run_arm.sh B-gated                #  -> results/measured/across-v3-paired-gated-rpc.jsonl
```

Each arm oversamples to `EPISODES=40` real paired episodes (Wilson upper on `pwin=0` ≈ 0.09 at
`n=40`). Per episode the kit: re-genesises the source, triggers the real double-sign, the relayer
catches the source cert live and fronts the real `gaiad tx bank send` fill, then
`collect_devnet --paired-records` folds a **paired** record (real `T_settle` vs real `T_acc`).

Tune via env vars if the trigger or timing needs it (defaults in `env.sh`):
`EPISODES`, `B_GATE_DEPTH_OPEN`, `B_GATE_DEPTH_GATED`, `DST_TIMEOUT_COMMIT`, `B_RELAYER_POLL_MS`,
`DBLSIGN_TIMEOUT`, `SLASH_WINDOW_BLOCKS`.

---

## 4. Assemble + the data-gated paper flip (on Windows)

`run_all.py`/`make_tables.py` run on **Windows** (PowerShell python has numpy/pyyaml; WSL python
does not, and `Paper/` is not in WSL). Stage the new `results/measured/*.jsonl` back to G: first.

```powershell
cd "G:\...\9 Shard Security\artifact"
python run_all.py     --config configs/main.yaml
python make_tables.py --input results/main.json --out ../Paper/Section/_generated
python plot_figures.py --input results/main.json --out figures/
cd ..\Paper\IEEE; pdflatex main; bibtex main; pdflatex main; pdflatex main   # + ..\Paper\ACM
```

The flip is **data-gated** — nothing in the prose is edited by hand:

* `make_tables._provenance_macros` sees `across-v3-selffill-rpc` and flips `\ArtifactPairedMode`
  → *"the paired race runs on real client code"*, `\ArtifactRqEightRemains` →
  *"…complete the remaining propagation-timing and self-run-archive re-derivations"*, and (with
  arm C present) `\ArtifactRqEightProvenance` → *"…now run on real consensus client code."*
* `_measured_macros` prefers `across-v3-selffill-rpc` over the shadow `across-v3-selffill` for
  `\ArtifactBridgeVerdict` (now the measured **OPEN**) and `\ArtifactBridgePwin`.
* The gated twin appears as the **"Across V3 (gated twin) — finality-gated relayer (Prop.1)"** row,
  verdict **RULED_OUT** — the live immunity demonstration, in the same `tab_measured` instrument.

If the files are absent, every macro stays at the honest *shadow-rehearsal* wording (verified).

---

## 5. Offline verification (no localnet)

The pure record/verdict logic is unit-tested without a network — run before and after the WSL run:

```powershell
python tests/test_livemeasure_paired.py    # 18 checks: OPEN->OPEN, gated->RULED_OUT, knob flips verdict
```

This proves `assemble_paired_record` + `estimate_path` return the claimed verdicts; the WSL run
supplies the real `T_settle`/`T_acc` numbers that feed them.

---

## 6. Reporting profit at the floor `psucc` (closes objection #1)

The paired arm measures the **window** (`pwin`) and the **settlement/accountability latencies**.
Profit is then `E[Π] = psucc·pwin·V − B − Cop` with `B=(F+1)·q·(s+R)` and the **measured** `q≈1`
from arm A. **Report the headline `E[Π]` at the floor `psucc`** (`\ArtifactPsuccFloor`, the
no-view-control value), not at `0.85`. If `E[Π] > 0` at the floor on this real path, the demonstrated
attack no longer depends on the contested view-control assumption — keep `0.85` only as an upper
sensitivity band (`\S\ref{sec:floor}`, `limitations.tex` (2)).

---

## 7. LONI / HPC — what helps, what doesn't

**The killing run does NOT need HPC.** Arm B is an *integration/orchestration* task running real
`gaiad` binaries on one box; HPC adds nothing to its *realness*, and HPC constraints work against it
(SLURM batch vs long-running daemons; compute nodes often lack outbound internet, which the
public-RPC arms below need; userspace gaiad already needs no root). Run B-open/B-gated on your
**laptop or one interactive LONI node**.

LONI **is** the right tool for the *compute-bound* arms that surround it:

| Workload | LONI fit | Why |
|---|---|---|
| **Arm B paired race + gated twin** (real client code) | laptop / **1 interactive node** | orchestration, not compute; needs live daemons, not a batch queue |
| **≥4-node propagation timing** (`T_acc^lo`, prereg arm E) | **1 fat node** (many cores/RAM) | a larger-committee localnet (e.g. N=64) exceeds a laptop; one node hosts all validators |
| **Monte-Carlo / testbed sweeps** (`run_all.py` RQ1/RQ3/RQ6, seeds) | **SLURM array jobs** | embarrassingly parallel over seeds; the ideal HPC use |
| **self-run archive node** re-derivation of `q_max` (arm E) | **1 big-disk node** | storage/compute heavy; a LONI node with scratch fits |
| Public-RPC arms (bridge marginal, public-IBC negative control) | **laptop, NOT a compute node** | need outbound internet that compute nodes usually block |

Recommended split: **B-open + B-gated on the laptop** (fastest path to the killing result), then
LONI SLURM array jobs for the Monte-Carlo sweeps and the ≥4-node/archive enrichment if you want to
tighten `T_acc^lo` and `q_max`.

---

## 8. Division of labor

* **Implemented + offline-verified here:** `assemble_paired_record` / `_paired_rpc` /
  `paired_harness` (livemeasure.py), the `collect_devnet --paired-records/--gated/--dst-chain`
  plumbing, `setup_destzone.sh`, `relayer.sh`, the `run_episode.sh`/`run_arm.sh` Arm-B branches,
  the config + make_tables data-gated flip, and `tests/test_livemeasure_paired.py` (18 checks pass).
* **Needs the gaiad host (you, in WSL):** running `run_arm.sh B-open` and `B-gated`. These start
  real consensus nodes and broadcast real txs — the one step that cannot be done from the authoring
  environment. Authored against the documented v0.50/gaiad-v19 recipe (as arms A/C were); expect the
  same class of first-run tuning the A/C bring-up needed (ports, fee genesis, trigger flakiness).

Nothing here runs against a shared network; the only "live" elements are your own isolated zones.
