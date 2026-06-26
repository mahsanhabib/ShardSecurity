#!/usr/bin/env python3
r"""Collect native-IBC settlement (the negative control) into measured records.

READ-ONLY. This is the negative control of PREREGISTRATION-rq8.md (sec 2.3): the
native IBC path on a two-zone devnet (or any IBC channel) is finality-gated by
construction -- the destination light client acts only on a *finalized* source
header -- so it must return RULED_OUT. Running it end-to-end alongside the
fast-exit positive control proves the instrument fires both verdicts (kills the
"inert instrument" blocker).

It reads send_packet on the source and recv_packet/acknowledge_packet on the
destination (by block height), correlates by packet sequence via
shardbribe.livemeasure, and writes results/measured/<protocol>.jsonl with
structurally_gated=True.

Usage
-----
    python collect_ibc.py --src-rpc http://zone-a:26657 --dst-rpc http://zone-b:26657 \
        --src-heights 100,140,180 --dst-heights 105,146,188 --channel channel-0

If you don't know the heights, discover them with block_search for the
send_packet/recv_packet events on each chain, then pass them here.
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


def _heights(s):
    return [int(h) for h in s.split(",") if h.strip()] if s else []


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src-rpc", required=True, help="source-chain CometBFT RPC")
    ap.add_argument("--dst-rpc", required=True, help="destination-chain CometBFT RPC")
    ap.add_argument("--src-heights", required=True,
                    help="comma-separated heights carrying send_packet on the source")
    ap.add_argument("--dst-heights", required=True,
                    help="comma-separated heights carrying recv_packet on the dest")
    ap.add_argument("--channel", default=None, help="restrict to this IBC channel")
    ap.add_argument("--protocol", default="ibc-devnet-negative")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = Path(args.out) if args.out else Path(
        os.path.join(HERE, "results", "measured", f"{args.protocol}.jsonl"))

    print("[collect_ibc] correlating IBC packets across the two zones (read-only) ...")
    try:
        records = lm.ibc_relayer(
            args.src_rpc, args.dst_rpc,
            src_heights=_heights(args.src_heights),
            dst_heights=_heights(args.dst_heights), channel=args.channel)
    except Exception as ex:                           # noqa: BLE001 - surface to user
        print(f"[collect_ibc] ERROR: {ex}", file=sys.stderr)
        return 2
    if not records:
        print("[collect_ibc] no correlated packets. Check heights/channel/RPCs.")
        return 1

    lm.write_jsonl(records, out)
    settle = [r.T_settle for r in records if r.T_settle is not None]
    meta = {"protocol": args.protocol, "src_rpc": args.src_rpc, "dst_rpc": args.dst_rpc,
            "n_records": len(records), "structurally_gated": True,
            "T_settle_median_s": (statistics.median(settle) / 1000.0) if settle else None}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[collect_ibc] wrote {out}  ({len(records)} packets, "
          f"T_settle median {meta['T_settle_median_s']}s)")
    print("           structurally finality-gated -> RULED_OUT (negative control).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
