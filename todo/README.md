# TODO — what's left

Everything in the measurement *instrument* is built, tested, and documented (design,
six collectors, estimator + frozen decision rule, the RQ8 paper section, the
one-command `measure_all.py`, the runbook in `artifact/MEASUREMENT.md`).

> **UPDATE 2026-06-14 — the Cosmos arm is DONE with real data.** A live sweep
> measured **q_max = 0.97** (95% CI [0.83, 0.99]) from **30 verified double-sign
> slashes across 13 CometBFT chains**; Cosmos Hub estimates **RULED_OUT**. It's
> already folded into the paper (`results/measured/`, RQ8 macros filled, builds at
> 18 pp). So the remaining list is now **shorter** than it was — mainly the bridge
> subgraph, the corpora, the optional devnet, and finalizing the paper.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done.

| # | Task | Needs | Effort | File |
|---|---|---|---|---|
| 1 | ~~Cosmos RPC~~ **[x] done** · bridge subgraph still needed | internet, API key (bridge) | ~10 min | [1-obtain-endpoints.md](1-obtain-endpoints.md) |
| 2 | Assemble the reorg + exploit corpora | research, explorers (no fabrication) | 1–3 h | [2-assemble-corpora.md](2-assemble-corpora.md) |
| 3 | Run the measurement + fold into the paper | your machine + the URLs above | ~20 min | [3-run-and-assemble.md](3-run-and-assemble.md) |
| 4 | (Optional, full rigor) private devnet arms | Docker/devnet infra | 1–3 days | [4-optional-devnet.md](4-optional-devnet.md) |
| 5 | Finalize the paper for submission | your judgment + a host/DOI | ~1 day | [5-finalize-paper.md](5-finalize-paper.md) |
| ⚠ | Re-derive the Cosmos q_max against a **self-run archive node** for camera-ready provenance | an archive node | — | [1-obtain-endpoints.md](1-obtain-endpoints.md) |

## The fastest real result (minimum viable)

The **Cosmos RULED_OUT half is already done** (real data, in the paper). To complete
the dual finding you now only need the **bridge subgraph URL (Task 1b)** + the **reorg
corpus (Task 2a)** + **Task 3** → a measured bridge user-leg `T_settle` + the reorg
irreversibility evidence. That, with the Cosmos result already in hand, gives the full
read-only dual finding (no devnet) and changes the paper's punchline.

## Already done (so you don't redo it)
- `artifact/PREREGISTRATION-rq8.md` — frozen protocol + decision rule
- `artifact/measure_all.py` + `configs/main.yaml → rq8.endpoints` — one-command runner
- `artifact/collect_{cosmos,ibc,bridge,devnet,reorg,postmortem}.py` — the six arms
- `artifact/shardbribe/{livemeasure,estimate}.py` — parsers, estimators, decision rule
- `Paper/Section/measured_evaluation.tex` — the RQ8 section (compiles; shows `[pending]` until you run it)
- `artifact/MEASUREMENT.md` — the full runbook; `artifact/data/` — corpus templates + sourcing guide
