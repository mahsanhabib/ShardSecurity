#!/usr/bin/env python3
r"""Collect real fast-bridge settlement into measured T_settle records (open target).

READ-ONLY. This is the open-window arm of PREREGISTRATION-rq8.md (sec 3.3): it
replays already-settled transfers on a fast/intent bridge (Across V3 by default)
from a subgraph, correlates each deposit with its destination fill (and optional
solver repayment), and writes ``results/measured/<protocol>.jsonl`` with
``T_settle`` = the seconds-scale USER leg (the irreversible value the attacker
realizes) and the clawback-gated solver leg in ``t_withdraw_final``.

It replays only ordinary, public, already-settled transfers; it broadcasts no
fraudulent branch and mounts no attack.

IMPORTANT (prereg 4.1): this is the settlement *marginal*. On its own the path is
reported \textsc{indeterminate} (a paired p_win needs the devnet self-fill arm);
the marginal calibrates the real T_settle distribution and, with the reorg
natural-experiment, shows fills survive source reversals. When devnet self-fill
episodes (paired T_settle,T_acc) are appended to the same JSONL, the verdict
becomes \textsc{open-window}.

Usage
-----
    python collect_bridge.py --graph-url https://api.thegraph.com/subgraphs/name/<across-subgraph>
    python collect_bridge.py --graph-url URL --protocol across-v3 --max 20000
    python collect_bridge.py --graph-url URL --query @my_query.graphql \
        --deposits-key v3FundsDepositeds --fills-key filledV3Relays

If your subgraph uses different entity/field names, override --query / keys; the
default query is best-effort and must match the live schema.
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


def preview(records: list) -> dict:
    user = [r.T_settle for r in records if r.T_settle is not None]
    solver = [(r.t_withdraw_final - r.t_src_cert)
              for r in records
              if r.t_withdraw_final is not None and r.t_src_cert is not None]
    return {
        "n_transfers": len(records),
        "user_leg_median_s": (statistics.median(user) / 1000.0) if user else None,
        "user_leg_p90_s": (sorted(user)[int(0.9 * (len(user) - 1))] / 1000.0)
                          if user else None,
        "n_with_solver_leg": len(solver),
        "solver_leg_median_s": (statistics.median(solver) / 1000.0) if solver else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graph-url", required=True, help="bridge subgraph GraphQL URL")
    ap.add_argument("--protocol", default="across-v3")
    ap.add_argument("--out", default=None,
                    help="output JSONL (default results/measured/<protocol>.jsonl)")
    ap.add_argument("--query", default=None,
                    help="GraphQL query string, or @file to read from a file")
    ap.add_argument("--deposits-key", default="deposits")
    ap.add_argument("--fills-key", default="fills")
    ap.add_argument("--repayments-key", default=None)
    ap.add_argument("--page-size", type=int, default=1000)
    ap.add_argument("--max", type=int, default=20000, help="max deposits to pull")
    args = ap.parse_args()

    out = Path(args.out) if args.out else Path(
        os.path.join(HERE, "results", "measured", f"{args.protocol}.jsonl"))

    query = args.query
    if query and query.startswith("@"):
        query = Path(query[1:]).read_text()

    print(f"[collect_bridge] replaying {args.protocol} settlement from subgraph "
          "(read-only) ...")
    try:
        records = lm.bridge_events(
            args.graph_url, query=query, deposits_key=args.deposits_key,
            fills_key=args.fills_key, repayments_key=args.repayments_key,
            page_size=args.page_size, max_records=args.max, protocol=args.protocol)
    except Exception as ex:                           # noqa: BLE001 - surface to user
        print(f"[collect_bridge] ERROR: {ex}", file=sys.stderr)
        return 2
    if not records:
        print("[collect_bridge] no correlated transfers found. Check the subgraph "
              "URL/schema and --deposits-key/--fills-key.")
        return 1

    lm.write_jsonl(records, out)
    pv = preview(records)
    meta = {"graph_url": args.graph_url, "protocol": args.protocol,
            "n_records": len(records), "preview": pv,
            "note": "settlement marginal (T_acc=None); pair with devnet self-fill "
                    "episodes for a p_win verdict (prereg 4.1)"}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))

    print(f"[collect_bridge] wrote {out}  ({len(records)} transfers)")
    print(f"           USER leg (realized V): median "
          f"{pv['user_leg_median_s']}s, P90 {pv['user_leg_p90_s']}s")
    print(f"           SOLVER leg (clawback-gated): {pv['n_with_solver_leg']} matched"
          + (f", median {pv['solver_leg_median_s']}s" if pv['solver_leg_median_s'] else ""))
    print("           verdict on this path stays INDETERMINATE until paired devnet "
          "self-fill episodes are appended (prereg 4.1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
