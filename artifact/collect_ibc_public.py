#!/usr/bin/env python3
r"""Collect native-IBC settlement (the negative control) from a REAL public IBC
channel -- the deployed-mainnet variant of collect_ibc.py.

READ-ONLY. This is the negative control of PREREGISTRATION-rq8.md (sec 2.3),
realised on real public ledger data instead of a self-run two-zone devnet (a
disclosed deviation; see measured_evaluation.tex). A native-IBC light client acts
only on a *committed* (finalized) source header, so the path is finality-gated by
construction -- T_settle >= T_acc -- and must return RULED_OUT. Measuring it on a
live deployed channel (Cosmos Hub -> Osmosis by default) is consistent with the
"every quantity is obtained from public ledger data" ethos of the other passive
arms, and is arguably a stronger control than a synthetic devnet.

What it does
------------
1. Discovers recent matched packets on CHANNEL via tx_search on both chains
   (bounded to a recent height window so the public node answers quickly).
2. Correlates send_packet (source) with recv_packet (dest) by packet sequence
   using shardbribe.livemeasure.ibc_relayer (same code path as collect_ibc.py).
3. Writes results/measured/<protocol>.jsonl (+ .sha256) and a .meta.json carrying
   full provenance: RPCs, channel, the exact heights used (immutable history, so
   the specific run is reproducible), the height window, and n.

Usage
-----
    python collect_ibc_public.py            # Cosmos Hub -> Osmosis, channel-141
    python collect_ibc_public.py --src-rpc ... --dst-rpc ... --channel channel-141 \
        --src-chain cosmoshub-4 --dst-chain osmosis-1
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

from shardbribe import livemeasure as lm

HERE = os.path.dirname(os.path.abspath(__file__))


def _latest_height(rpc: str) -> int:
    return int(lm._rpc_get(rpc, "/status")["result"]["sync_info"]["latest_block_height"])


def _tx_search(rpc: str, etype: str, channel: str, window: int, per_page: int) -> list:
    """tx_search for an IBC event on `channel`, JSON-quoted query bounded to a
    recent height window so a public node returns promptly."""
    lo = _latest_height(rpc) - window
    query = f'"{etype}.packet_src_channel=\'{channel}\' AND tx.height>{lo}"'
    r = lm._rpc_get(rpc, "/tx_search", {
        "query": query, "order_by": '"desc"', "per_page": str(per_page), "page": "1"})
    if "error" in r:
        raise RuntimeError(f"tx_search error on {rpc}: {r['error']}")
    return r.get("result", {}).get("txs", []) or []


def _seq_to_height(txs: list, etype: str, channel: str) -> dict:
    """packet_sequence -> block height for `etype` events on `channel`
    (matched on packet_src_channel, exactly as livemeasure.parse_ibc_events does)."""
    out = {}
    for tx in txs:
        h = int(tx["height"])
        for ev in (tx.get("tx_result", {}).get("events") or []):
            if ev.get("type") != etype:
                continue
            a = {lm._maybe_b64(at.get("key")): lm._maybe_b64(at.get("value"))
                 for at in ev.get("attributes", [])}
            if a.get("packet_src_channel") != channel:
                continue
            seq = a.get("packet_sequence")
            if seq is not None:
                out.setdefault(str(seq), h)        # newest first; keep first seen
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src-rpc", default="https://cosmos-rpc.publicnode.com",
                    help="source-chain CometBFT RPC (sends the packet)")
    ap.add_argument("--dst-rpc", default="https://osmosis-rpc.publicnode.com",
                    help="destination-chain CometBFT RPC (receives the packet)")
    ap.add_argument("--channel", default="channel-141",
                    help="source-side IBC channel (Hub->Osmosis is channel-141)")
    ap.add_argument("--src-chain", default="cosmoshub-4")
    ap.add_argument("--dst-chain", default="osmosis-1")
    ap.add_argument("--window", type=int, default=20000,
                    help="recent-height window bounding tx_search")
    ap.add_argument("--per-page", type=int, default=50)
    ap.add_argument("--protocol", default="ibc-cosmoshub-osmosis-negative")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = Path(args.out) if args.out else Path(
        os.path.join(HERE, "results", "measured", f"{args.protocol}.jsonl"))

    print(f"[collect_ibc_public] discovering {args.src_chain}->{args.dst_chain} "
          f"packets on {args.channel} (read-only) ...")
    try:
        src_latest, dst_latest = _latest_height(args.src_rpc), _latest_height(args.dst_rpc)
        src = _seq_to_height(_tx_search(args.src_rpc, "send_packet", args.channel,
                                        args.window, args.per_page), "send_packet", args.channel)
        dst = _seq_to_height(_tx_search(args.dst_rpc, "recv_packet", args.channel,
                                        args.window, args.per_page), "recv_packet", args.channel)
    except Exception as ex:                            # noqa: BLE001 - surface to user
        print(f"[collect_ibc_public] ERROR: {ex}", file=sys.stderr)
        return 2

    matched = sorted(set(src) & set(dst), key=lambda s: int(s))
    print(f"[collect_ibc_public] send={len(src)} recv={len(dst)} matched={len(matched)}")
    if not matched:
        print("[collect_ibc_public] no matched sequences in the window; widen --window.")
        return 1
    src_heights = sorted({src[s] for s in matched})
    dst_heights = sorted({dst[s] for s in matched})

    records = lm.ibc_relayer(args.src_rpc, args.dst_rpc, src_heights=src_heights,
                             dst_heights=dst_heights, channel=args.channel,
                             src_chain=args.src_chain, dst_chain=args.dst_chain)
    if not records:
        print("[collect_ibc_public] correlation produced no records.")
        return 1

    lm.write_jsonl(records, out)
    settle = [r.T_settle for r in records if r.T_settle is not None]
    meta = {"protocol": args.protocol, "source": "public-ibc",
            "src_rpc": args.src_rpc, "dst_rpc": args.dst_rpc, "channel": args.channel,
            "src_chain": args.src_chain, "dst_chain": args.dst_chain,
            "window": args.window, "src_latest_height": src_latest,
            "dst_latest_height": dst_latest, "matched": len(matched),
            "src_heights": src_heights, "dst_heights": dst_heights,
            "n_records": len(records), "structurally_gated": True,
            "T_settle_median_s": (statistics.median(settle) / 1000.0) if settle else None}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[collect_ibc_public] wrote {out}  ({len(records)} packets, "
          f"T_settle median {meta['T_settle_median_s']}s)")
    print("           structurally finality-gated -> RULED_OUT (negative control).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
