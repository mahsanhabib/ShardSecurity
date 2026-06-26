#!/usr/bin/env python3
r"""Collect real Cosmos double-sign incidents into measured q_max / T_acc^lo records.

READ-ONLY. This is the passive arm of PREREGISTRATION-rq8.md (sec 3.1/3.2): it
queries a CometBFT RPC (a self-run archive node is preferred over a public one)
for the blocks that carried a *double-sign slash*, reconstructs the infraction /
evidence / slash timestamps via ``shardbribe.livemeasure``, and writes
``results/measured/<chain>.jsonl`` -- the file ``run_all.py``/``estimate.py``
consume to produce the measured q and T_acc.

It NEVER induces equivocation. It only reads already-public ledger data, so it
circumvents no access control and mounts no attack.

Usage
-----
    # discover incidents automatically (needs an RPC with block event indexing):
    python collect_cosmos.py --rpc https://cosmos-rpc.publicnode.com

    # or supply heights you already found (Mintscan / an indexer), bypassing search:
    python collect_cosmos.py --rpc URL --heights 12345,2345678

    # other chains / params:
    python collect_cosmos.py --rpc URL --chain-id osmosis-1 --block-interval-ms 5500

The default discovery query is ``slash.reason='double_sign'`` (the slashing-module
event emitted when DuplicateVoteEvidence is processed). Override with --query.
If your RPC has block search disabled, pass --heights instead.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from shardbribe import livemeasure as lm

HERE = os.path.dirname(os.path.abspath(__file__))


def discover_heights(rpc: str, query: str, max_n: int, per_page: int = 100) -> list:
    """Find block heights carrying the slash event via CometBFT /block_search.

    String params are JSON-quoted as the URI interface requires. Returns up to
    ``max_n`` heights, ascending. Raises a clear error if search is unavailable."""
    heights: list = []
    page = 1
    while len(heights) < max_n:
        resp = lm._rpc_get(rpc, "/block_search", {
            "query": f'"{query}"',
            "page": page,
            "per_page": per_page,
            "order_by": '"asc"',
        })
        if "error" in resp:
            raise RuntimeError(
                f"block_search failed ({resp['error']}); your RPC may not index "
                "block events. Re-run with --heights h1,h2,... instead.")
        res = resp.get("result", {})
        blocks = res.get("blocks", []) or []
        if not blocks:
            break
        for b in blocks:
            heights.append(int(b["block"]["header"]["height"]))
        total = int(res.get("total_count", 0) or 0)
        if len(blocks) < per_page or len(heights) >= total:
            break
        page += 1
    # de-dup preserve order
    seen, uniq = set(), []
    for h in heights:
        if h not in seen:
            seen.add(h); uniq.append(h)
    return uniq[:max_n]


def quick_qmax(records: list) -> dict:
    """A no-dependency preview of q_max from the collected records (the full
    Clopper-Pearson interval is produced by estimate.py on the committed file)."""
    have = [r for r in records if r.t_slash_effective is not None
            and r.t_withdraw_unslashable is not None]
    enforced = sum(1 for r in have
                   if r.t_slash_effective < r.t_withdraw_unslashable)
    n = len(have)
    return {"n_incidents": len(records), "n_with_slash": n,
            "q_max_point": (enforced / n) if n else None,
            "enforced": enforced}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rpc", required=True, help="CometBFT RPC base URL (read-only)")
    ap.add_argument("--chain-id", default="cosmoshub-4")
    ap.add_argument("--out", default=None,
                    help="output JSONL (default results/measured/<chain-id>.jsonl)")
    ap.add_argument("--heights", default=None,
                    help="comma-separated evidence heights (skip auto-discovery)")
    ap.add_argument("--query", default="slash.reason='double_sign'",
                    help="block_search query used for discovery")
    ap.add_argument("--max", type=int, default=200, help="max incidents to collect")
    ap.add_argument("--slash-window", type=int, default=4,
                    help="blocks after the evidence height to scan for the slash")
    ap.add_argument("--block-interval-ms", type=float, default=6000.0)
    ap.add_argument("--min-delta-blocks", type=float, default=2.0,
                    help="drop incidents whose infraction->slash gap is below this "
                         "many block intervals (timestamp resolution floor, T10)")
    args = ap.parse_args()

    out = Path(args.out) if args.out else Path(
        os.path.join(HERE, "results", "measured", f"{args.chain_id}.jsonl"))

    if args.heights:
        heights = [int(h) for h in args.heights.split(",") if h.strip()]
        print(f"[collect_cosmos] using {len(heights)} supplied heights")
    else:
        print(f"[collect_cosmos] discovering incidents via block_search "
              f"(query: {args.query}) ...")
        try:
            heights = discover_heights(args.rpc, args.query, args.max)
        except Exception as ex:                       # noqa: BLE001 - surface to user
            print(f"[collect_cosmos] ERROR: {ex}", file=sys.stderr)
            return 2
        print(f"[collect_cosmos] discovered {len(heights)} candidate height(s)")
    if not heights:
        print("[collect_cosmos] no incidents found. Nothing written.\n"
              "  Tip: confirm the chain has had double-sign slashes, or pass "
              "--heights from an explorer (e.g. Mintscan).")
        return 1

    print(f"[collect_cosmos] extracting records from {args.rpc} (read-only) ...")
    records = lm.cosmos_rpc(
        args.rpc, heights, slash_window=args.slash_window,
        block_interval_ms=args.block_interval_ms, src_chain=args.chain_id,
        min_delta_blocks=args.min_delta_blocks)

    lm.write_jsonl(records, out)
    meta = {"rpc": args.rpc, "chain_id": args.chain_id, "query": args.query,
            "heights": heights, "n_records": len(records),
            "preview": quick_qmax(records)}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))

    pv = meta["preview"]
    print(f"[collect_cosmos] wrote {out}  ({len(records)} records)")
    print(f"           q_max preview: {pv['enforced']}/{pv['n_with_slash']} "
          f"enforced before evidence-expiry -> q_max~"
          f"{pv['q_max_point'] if pv['q_max_point'] is not None else 'n/a'}")
    print("           next: python run_all.py --config configs/main.yaml  "
          "(RQ8 picks this up), then make_tables.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
