#!/usr/bin/env python3
r"""Build the adversarial T_settle fast-tail from bridge-exploit postmortems.

READ-ONLY / OFFLINE. Honest-transfer replay (collect_bridge.py) measures T_settle
biased SLOW; a real adversary cashes out as fast as possible. This arm calibrates
that fast tail from a curated corpus of documented bridge exploits / intent
liquidity-exhaustion events (Nomad, Wormhole, Multichain, Ronin, Horizon, ...),
timing value-creation -> cash-out -> any clawback (PREREGISTRATION-rq8.md 3.3).
Corroborative (T_acc=None): it shapes the T_settle distribution, it is not a
verdict path on its own.

Corpus format: .json (list of dicts) or .csv (header row) with fields:
  name/chain, t_value_created_s, t_cashout_s, t_clawback_s (optional),
  clawback_landed (optional bool).

Usage
-----
    python collect_postmortem.py --corpus exploits.csv
    python collect_postmortem.py --corpus exploits.json --out results/measured/exploit-postmortem.jsonl
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


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", required=True, help="postmortem corpus .json or .csv")
    ap.add_argument("--protocol", default="exploit-postmortem")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = Path(args.out) if args.out else Path(
        os.path.join(HERE, "results", "measured", f"{args.protocol}.jsonl"))

    try:
        incidents = lm.load_postmortem_corpus(args.corpus)
        records = lm.exploit_postmortem(incidents, protocol=args.protocol)
    except Exception as ex:                           # noqa: BLE001 - surface to user
        print(f"[collect_postmortem] ERROR: {ex}", file=sys.stderr)
        return 2
    if not records:
        print("[collect_postmortem] empty corpus. Nothing written.")
        return 1

    lm.write_jsonl(records, out)
    settle = [r.T_settle for r in records if r.T_settle is not None]
    clawed = [r for r in records if r.solver_repaid]
    meta = {"protocol": args.protocol, "corpus": args.corpus, "n_records": len(records),
            "cashout_median_s": (statistics.median(settle) / 1000.0) if settle else None,
            "cashout_fastest_s": (min(settle) / 1000.0) if settle else None,
            "n_clawed_back": len(clawed)}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[collect_postmortem] wrote {out}  ({len(records)} incidents)")
    print(f"           adversarial cash-out: median {meta['cashout_median_s']}s, "
          f"fastest {meta['cashout_fastest_s']}s, clawed back {meta['n_clawed_back']}")
    print("           corroborative T_settle fast-tail (not a verdict path).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
