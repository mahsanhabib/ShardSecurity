#!/usr/bin/env python3
r"""Collect paired self-fill episodes from the devnet equivocation harness.

This is the arm that produces the PAIRED (T_settle, T_acc) episodes, the
attack-conditional q (q_attack), and the adversarial upper-bound T_acc
(T_acc^hi) of PREREGISTRATION-rq8.md (sec 3.1/3.2). Two uses:

  * Positive control (fast-exit, OPEN): short unbonding lead -> low q_attack and a
    measured open window. Writes results/measured/fastexit-devnet-positive.jsonl.
  * Pairing for the bridge open target: append paired episodes to the bridge file
    (results/measured/across-v3.jsonl) to turn its INDETERMINATE settlement marginal
    into an OPEN p_win verdict.

SAFETY: the equivocation leg runs ONLY on a private chain-id in the localnet
allowlist (livemeasure.ALLOWED_EQUIVOCATION_CHAINS); any mainnet/shared id is
refused. The default backend is the in-process 'shadow' rehearsal (no external
binaries); --backend rpc drives a real private cometbft localnet.

Usage
-----
    # positive control (fast exit -> OPEN, low q):
    python collect_devnet.py --chain-id fastexit-devnet-positive --episodes 60 \
        --unbond-lead-ms 60000

    # adversarial T_acc^hi (evidence suppression):
    python collect_devnet.py --chain-id fastexit-devnet-positive --suppress-evidence

    # append paired episodes to the bridge file to fire its OPEN verdict:
    python collect_devnet.py --chain-id across-v3 --out results/measured/across-v3.jsonl \
        --append --episodes 60
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
    enforced = [r for r in records if r.t_slash_effective is not None
                and r.t_withdraw_unslashable is not None
                and r.t_slash_effective < r.t_withdraw_unslashable]
    paired = [r for r in records if r.T_settle is not None and r.T_acc is not None]
    wins = [r for r in paired if r.T_settle < r.T_acc]
    return {
        "episodes": len(records),
        "q_attack_point": (len(enforced) / len(records)) if records else None,
        "paired": len(paired),
        "pwin_point": (len(wins) / len(paired)) if paired else None,
        "T_settle_median_s": (statistics.median([r.T_settle for r in paired]) / 1000.0)
                             if paired else None,
        "T_acc_median_s": (statistics.median([r.T_acc for r in paired]) / 1000.0)
                          if paired else None,
        "tacc_bound": records[0].tacc_bound if records else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chain-id", default="fastexit-devnet-positive",
                    help="private chain-id (must be in the localnet allowlist)")
    ap.add_argument("--backend", default="shadow", choices=["shadow", "rpc"])
    ap.add_argument("--out", default=None,
                    help="output JSONL (default results/measured/<chain-id>.jsonl)")
    ap.add_argument("--append", action="store_true",
                    help="append to --out instead of overwriting (for bridge pairing)")
    ap.add_argument("--episodes", type=int, default=60)
    ap.add_argument("--suppress-evidence", action="store_true",
                    help="adversarial evidence withholding -> T_acc^hi (tacc_bound=hi)")
    ap.add_argument("--suppress-ms", type=float, default=180000.0)
    ap.add_argument("--unbond-lead-ms", type=float, default=60000.0,
                    help="equivocator stake-exit lead; short => low q_attack (fast exit)")
    ap.add_argument("--bridge-fill-mean-ms", type=float, default=8000.0)
    ap.add_argument("--acc-enforce-ms", type=float, default=260000.0)
    ap.add_argument("--seed", type=int, default=20240917)
    ap.add_argument("--rpc", default=None,
                    help="(--backend rpc) private localnet CometBFT RPC, e.g. http://localhost:26657")
    ap.add_argument("--evidence-heights", default=None,
                    help="(--backend rpc) comma-separated infraction heights you triggered "
                         "on the localnet (see LOCALNET-RQ8.md arm A)")
    ap.add_argument("--block-interval-ms", type=float, default=6000.0)
    ap.add_argument("--slash-window", type=int, default=8,
                    help="(--backend rpc) blocks after the infraction to scan for the applied "
                         "slash; set it to span the evidence-expiry horizon so a genuine "
                         "fast-exit escape (no slash) is distinguishable from slow enforcement")
    ap.add_argument("--unbond-height", type=int, default=None,
                    help="(--backend rpc, arm C) block height of the equivocator's real unbond "
                         "tx; enables OBSERVED-completion q_attack (real client code) instead of "
                         "an analytic exit deadline. See LOCALNET-RQ8.md arm C.")
    ap.add_argument("--unbond-amount", type=float, default=None,
                    help="(arm C) the unbonded amount in base units, to detect clawback "
                         "(returned < submitted => the slash caught the exiting stake)")
    ap.add_argument("--unbond-watch", type=int, default=30,
                    help="(arm C) blocks after the unbond to scan for its complete_unbonding")
    ap.add_argument("--paired-records", default=None,
                    help="(arm B) JSON array the relayer wrote, one obj per episode "
                         "{infraction_height,t_src_cert_ms,t_dst_receipt_ms,...}; combines the "
                         "real source slash (T_acc) with the real settlement leg (T_settle) into "
                         "a PAIRED record. See LOCALNET-RQ8-PAIRED.md.")
    ap.add_argument("--gated", action="store_true",
                    help="(arm B) the relayer finality-gated the fill -> structurally_gated "
                         "(the Proposition-1 twin; verdict RULED_OUT).")
    ap.add_argument("--dst-chain", default="ibc-devnet-zone-b",
                    help="(arm B) destination 'bridge' zone chain-id (value sink)")
    ap.add_argument("--committee", action="store_true",
                    help="(N4 committee fork) assemble ONE faithful committee-fork record "
                         "from the two partitions' conflicting /commit certs + the real "
                         "slashes. Needs --rpc-a, --rpc-b, --fork-height. See N4-COMMITTEE.md.")
    ap.add_argument("--rpc-a", default=None, help="(N4) partition-A CometBFT RPC")
    ap.add_argument("--rpc-b", default=None, help="(N4) partition-B CometBFT RPC")
    ap.add_argument("--fork-height", type=int, default=None,
                    help="(N4) committed height where the two partitions' certs conflict")
    ap.add_argument("--chain", default=None, help="(N4) committee chain-id (allowlisted)")
    args = ap.parse_args()

    out = Path(args.out) if args.out else Path(
        os.path.join(HERE, "results", "measured", f"{args.chain_id}.jsonl"))

    # --- N4 committee fork: F+1 distinct equivocators + honest split on real code ----
    if args.committee:
        chain = args.chain or args.chain_id
        if not (args.rpc_a and args.rpc_b and args.fork_height):
            print("[collect_devnet] --committee needs --rpc-a, --rpc-b, --fork-height "
                  "(the height where the two partitions' certs conflict). See N4-COMMITTEE.md.",
                  file=sys.stderr)
            return 2
        print(f"[collect_devnet] committee-fork arm on {chain} at height "
              f"{args.fork_height} (A={args.rpc_a} B={args.rpc_b}) ...")
        try:
            records = lm.committee_harness(
                chain, rpc_a=args.rpc_a, rpc_b=args.rpc_b, height=args.fork_height,
                F=1, slash_window=args.slash_window,
                block_interval_ms=args.block_interval_ms, src_chain=chain)
        except Exception as ex:                       # noqa: BLE001 - surface to user
            print(f"[collect_devnet] ERROR: {ex}", file=sys.stderr)
            return 2
        if not records:
            print("[collect_devnet] no committee-fork record assembled. Nothing written.")
            return 1
        if args.append and out.exists():
            existing = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
            payload = existing + [r.to_dict() for r in records]
            out.write_text("\n".join(json.dumps(x, sort_keys=True) for x in payload) + "\n")
        else:
            lm.write_jsonl(records, out)
        r0 = records[0]
        out.with_suffix(".meta.json").write_text(json.dumps(
            {"chain_id": chain, "backend": "committee-rpc", "fork_height": args.fork_height,
             "committee_size": r0.committee_size, "quorum_size": r0.quorum_size,
             "n_equivocators": r0.n_equivocators, "n_honest_split": r0.n_honest_split,
             "quorum_intersection_ok": r0.quorum_intersection_ok,
             "conflicting_certs": r0.conflicting_certs, "n_slashed": r0.n_slashed,
             "T_acc_ms": r0.T_acc}, indent=2))
        print(f"[collect_devnet] wrote {out}  (N={r0.committee_size}, Q={r0.quorum_size}, "
              f"equivocators={r0.n_equivocators}, honest_split={r0.n_honest_split}, "
              f"conflicting={r0.conflicting_certs}, slashed={r0.n_slashed}, "
              f"intersection_ok={r0.quorum_intersection_ok})")
        print("           next: run_all.py then make_tables.py to fold into RQ8.")
        return 0

    # --- arm B: paired settlement-vs-accountability race on real client code -----
    if args.paired_records:
        txt = Path(args.paired_records).read_text().strip()
        try:
            rr = json.loads(txt)
            if isinstance(rr, dict):                  # a single relayer episode object
                rr = rr.get("episodes", [rr])
        except json.JSONDecodeError:                  # JSONL: one episode object per line
            rr = [json.loads(l) for l in txt.splitlines() if l.strip()]
        print(f"[collect_devnet] paired arm on {args.chain_id} "
              f"({len(rr)} relayer episodes, {'GATED twin' if args.gated else 'OPEN'}) ...")
        try:
            records = lm.paired_harness(
                args.chain_id, rpc_url=args.rpc, relayer_records=rr, gated=args.gated,
                src_chain=args.chain_id, dst_chain=args.dst_chain,
                block_interval_ms=args.block_interval_ms, slash_window=args.slash_window)
        except Exception as ex:                       # noqa: BLE001 - surface to user
            print(f"[collect_devnet] ERROR: {ex}", file=sys.stderr)
            return 2
        if not records:
            print("[collect_devnet] no paired episodes assembled (no evidence at the "
                  "given heights?). Nothing written.")
            return 1
        if args.append and out.exists():
            existing = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
            payload = existing + [r.to_dict() for r in records]
            out.write_text("\n".join(json.dumps(x, sort_keys=True) for x in payload) + "\n")
        else:
            lm.write_jsonl(records, out)
        pv = preview(records)
        out.with_suffix(".meta.json").write_text(json.dumps(
            {"chain_id": args.chain_id, "backend": "paired-rpc",
             "gated": bool(args.gated), "preview": pv}, indent=2))
        print(f"[collect_devnet] wrote {out}  ({len(records)} paired episodes)")
        print(f"           paired p_win ~ {pv['pwin_point']}  "
              f"(T_settle med {pv['T_settle_median_s']}s vs T_acc med "
              f"{pv['T_acc_median_s']}s)")
        print("           next: run_all.py then make_tables.py to fold into RQ8.")
        return 0

    print(f"[collect_devnet] running {args.backend} equivocation harness on "
          f"{args.chain_id} ({args.episodes} episodes"
          f"{', suppressed' if args.suppress_evidence else ''}) ...")
    try:
        records = lm.equivocation_harness(
            args.chain_id, backend=args.backend, episodes=args.episodes,
            suppress_evidence=args.suppress_evidence, suppress_ms=args.suppress_ms,
            unbond_lead_ms=args.unbond_lead_ms,
            bridge_fill_mean_ms=args.bridge_fill_mean_ms,
            acc_enforce_ms=args.acc_enforce_ms, seed=args.seed,
            rpc_url=args.rpc, src_chain=args.chain_id,
            block_interval_ms=args.block_interval_ms, slash_window=args.slash_window,
            unbond_height=args.unbond_height, unbond_amount=args.unbond_amount,
            unbond_watch=args.unbond_watch,
            evidence_heights=([int(h) for h in args.evidence_heights.split(",") if h.strip()]
                              if args.evidence_heights else None))
    except Exception as ex:                           # noqa: BLE001 - surface to user
        print(f"[collect_devnet] ERROR: {ex}", file=sys.stderr)
        return 2
    if not records:
        print("[collect_devnet] no episodes produced a fork. Nothing written.")
        return 1

    if args.append and out.exists():
        existing = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
        payload = existing + [r.to_dict() for r in records]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(json.dumps(x, sort_keys=True) for x in payload) + "\n")
        print(f"[collect_devnet] appended {len(records)} episodes to {out} "
              f"(now {len(payload)} records)")
    else:
        lm.write_jsonl(records, out)
        print(f"[collect_devnet] wrote {out}  ({len(records)} episodes)")

    pv = preview(records)
    out.with_suffix(".meta.json").write_text(json.dumps(
        {"chain_id": args.chain_id, "backend": args.backend, "preview": pv}, indent=2))
    print(f"           q_attack ~ {pv['q_attack_point']}  (low => fast-exit danger)")
    print(f"           paired p_win ~ {pv['pwin_point']}  "
          f"(T_settle med {pv['T_settle_median_s']}s vs T_acc med "
          f"{pv['T_acc_median_s']}s, bound={pv['tacc_bound']})")
    print("           next: run_all.py then make_tables.py to fold into RQ8.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
