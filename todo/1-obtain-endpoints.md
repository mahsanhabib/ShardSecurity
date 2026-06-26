# 1 — Obtain live endpoints

**Why only you:** these are network resources (public RPCs, a subgraph, possibly a
free API key) that must be fetched from your machine with internet access.

Put what you find into `artifact/configs/main.yaml → rq8.endpoints`.

## 1a. Cosmos archive RPC + double-sign heights  → safe target (RULED_OUT)  — [x] DONE (2026-06-14)

**Result:** a live sweep found and verified **30 double-sign slashes across 13 CometBFT
chains** → **q_max = 0.97** (95% CI [0.83, 0.99]); Cosmos Hub specifically 5/5 → q≈1,
verdict **RULED_OUT**. Data is in `artifact/results/measured/cosmoshub-4.jsonl` and
`artifact/results/cosmos_doublesign_pool.jsonl`; the RQ8 macros/table/section are filled.
Notable real findings: the unslashable deadline is the **48h evidence-expiry, not
unbonding**; one Sentinel case shows the 48h `max_age_duration` is **not a hard cutoff**
(slash applied ~27 days later). `q_max` is an **upper bound** (enforcement conditional on
a record existing — un-pursued equivocations leave no trace).

- [x] CometBFT archive RPCs found and used (per-chain list in the workflow report;
      e.g. Cosmos Hub via `rpc.cosmoshub-4-archive.citizenweb3.com`).
- [x] 30 double-sign heights discovered + live-verified.
- [x] **Independent re-verification (2026-06-14):** re-pulled every incident's `/block`;
      **25/30 confirmed** (genuine `DuplicateVoteEvidence`, validator + timestamp match to
      the second — **0 mismatches, 0 fabrications**, incl. the obscure chains and the
      51-evidence Sentinel outlier). The **5 remaining are old Osmosis heights** that free
      public archives prune; they were confirmed in the original sweep on an endpoint now
      down — not refuted, just not currently re-fetchable. Re-confirm them against an
      Osmosis archive (Numia/Allthatnode, or a snapshot) when re-deriving for camera-ready.
- [ ] ⚠ **Camera-ready provenance:** re-derive against a **self-run archive node** (or
      ≥2 independent archives per chain). The current figures are single public-RPC
      reads; several endpoints are rolling windows that may stop serving the heights.
      Also chase the chains that were pruned/unreachable here (injective, evmos, stride)
      and the pre-fork Hub 2019 incident — they exist but weren't fetchable.

## 1b. Bridge subgraph URL  → open target (T_settle user/solver legs)

- [ ] Find an **Across V3 (or other intent-bridge) subgraph** GraphQL endpoint.
      The Graph's decentralized network needs a free API key; some bridges also
      expose a public indexer/API. Set `rq8.endpoints.bridge.graph_url`.
- [ ] If the entity/field names differ from the default query, set
      `bridge.query` (a `@file` path) and `bridge.deposits_key` / `bridge.fills_key`.
      (Ask the assistant to draft `data/across_query.graphql` if helpful.)
- **Done when:** `python collect_bridge.py --graph-url <url>` prints
  `USER leg: median ~Ns` with a few thousand transfers.

## 1c. (Optional) IBC two-zone devnet RPCs → negative control
Only if you run Task 4. Set `rq8.endpoints.ibc.{src_rpc,dst_rpc,src_heights,dst_heights}`.

---
**Next:** [2-assemble-corpora.md](2-assemble-corpora.md) then [3-run-and-assemble.md](3-run-and-assemble.md).
