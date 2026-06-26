#!/usr/bin/env python3
r"""Build the reorg natural-experiment records (the 'beyond clawback' test, T6).

READ-ONLY / OFFLINE. Turns a curated corpus of source-chain reorgs -- deposits
whose source block was later reorged out -- into measured records showing whether
the destination FILL settled anyway (user leg irreversible to the recipient) and
whether the SOLVER repayment fired (clawback-gated solver leg). This is the direct
irreversibility evidence behind the open-window claim (PREREGISTRATION-rq8.md 3.3):
the attacker's realized value (user-leg fill) survives a source reversal.

The corpus is assembled by the RA from block explorers and bridge-exploit
postmortems (Ethereum May-2022 7-block reorg, Polygon deep reorgs, Nomad/Wormhole/
Ronin/Horizon timelines). Format: .json (list of dicts) or .csv (header row) with
fields: chain, t_deposit_s, t_fill_s, t_repay_s (optional), reorged_out, solver_repaid.

Usage
-----
    python collect_reorg.py --corpus reorg_incidents.csv
    python collect_reorg.py --corpus reorg_incidents.json --out results/measured/reorg.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from shardbribe import livemeasure as lm

HERE = os.path.dirname(os.path.abspath(__file__))


def preview(records: list) -> dict:
    reorged = [r for r in records if r.reorg_survived is not None]
    survived = [r for r in records if r.reorg_survived]
    repaid = [r for r in records if r.solver_repaid]
    return {
        "n_incidents": len(records),
        "n_reorged_with_surviving_fill": len(survived),
        "user_leg_irreversible_fraction":
            (len(survived) / len([r for r in records if r.reorg_survived is not None]))
            if reorged else None,
        "n_solver_repaid": len(repaid),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", required=True, help="reorg corpus .json or .csv")
    ap.add_argument("--protocol", default="reorg-natural-experiment")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = Path(args.out) if args.out else Path(
        os.path.join(HERE, "results", "measured", f"{args.protocol}.jsonl"))

    try:
        incidents = lm.load_reorg_corpus(args.corpus)
        records = lm.reorg_corpus(incidents, protocol=args.protocol)
    except Exception as ex:                           # noqa: BLE001 - surface to user
        print(f"[collect_reorg] ERROR: {ex}", file=sys.stderr)
        return 2
    if not records:
        print("[collect_reorg] empty corpus. Nothing written.")
        return 1

    lm.write_jsonl(records, out)
    pv = preview(records)
    out.with_suffix(".meta.json").write_text(json.dumps(
        {"protocol": args.protocol, "corpus": args.corpus, "preview": pv}, indent=2))
    print(f"[collect_reorg] wrote {out}  ({len(records)} incidents)")
    print(f"           user-leg irreversible fraction: "
          f"{pv['user_leg_irreversible_fraction']} "
          f"({pv['n_reorged_with_surviving_fill']} fills survived a source reorg)")
    print(f"           solver repaid (clawback landed): {pv['n_solver_repaid']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
