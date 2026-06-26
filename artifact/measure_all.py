#!/usr/bin/env python3
r"""One-command orchestrator for the RQ8 live measurement.

Reads endpoints from configs/main.yaml (``rq8.endpoints``) and runs each collector
whose inputs are configured; skips the rest with a clear message. The in-process
``devnet`` shadow arm needs no external infrastructure, so a bare
``python measure_all.py`` already produces the positive control.

Usage
-----
    python measure_all.py                 # run every configured arm
    python measure_all.py --dry-run       # print the commands, run nothing
    python measure_all.py --only devnet   # run a single arm (cosmos|ibc|bridge|devnet|reorg|postmortem)
    python measure_all.py --assemble      # after collecting, run run_all + make_tables

Fill in configs/main.yaml -> rq8.endpoints (URLs, heights, corpus paths). Anything
left null is skipped. See MEASUREMENT.md for where to source each input.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def _load_endpoints(cfg_path: str) -> dict:
    with open(cfg_path) as fh:
        cfg = yaml.safe_load(fh)
    return ((cfg.get("rq8") or {}).get("endpoints") or {})


def _plan(ep: dict) -> list:
    """Build (arm, argv, skip_reason) for each collector from the endpoints."""
    plan = []

    c = ep.get("cosmos") or {}
    if c.get("rpc"):
        argv = ["collect_cosmos.py", "--rpc", c["rpc"],
                "--chain-id", c.get("chain_id", "cosmoshub-4")]
        if c.get("heights"):
            argv += ["--heights", str(c["heights"])]
        plan.append(("cosmos", argv, None))
    else:
        plan.append(("cosmos", None, "set rq8.endpoints.cosmos.rpc (a CometBFT archive RPC)"))

    ib = ep.get("ibc") or {}
    if ib.get("src_rpc") and ib.get("dst_rpc") and ib.get("src_heights") and ib.get("dst_heights"):
        argv = ["collect_ibc.py", "--src-rpc", ib["src_rpc"], "--dst-rpc", ib["dst_rpc"],
                "--src-heights", str(ib["src_heights"]), "--dst-heights", str(ib["dst_heights"])]
        if ib.get("channel"):
            argv += ["--channel", ib["channel"]]
        plan.append(("ibc", argv, None))
    else:
        plan.append(("ibc", None, "set rq8.endpoints.ibc.{src_rpc,dst_rpc,src_heights,dst_heights}"))

    ibp = ep.get("ibc_public") or {}
    if ibp.get("enabled") and ibp.get("src_rpc") and ibp.get("dst_rpc"):
        argv = ["collect_ibc_public.py", "--src-rpc", ibp["src_rpc"], "--dst-rpc", ibp["dst_rpc"]]
        for k, flag in (("channel", "--channel"), ("src_chain", "--src-chain"),
                        ("dst_chain", "--dst-chain")):
            if ibp.get(k):
                argv += [flag, str(ibp[k])]
        plan.append(("ibc_public", argv, None))
    else:
        plan.append(("ibc_public", None, "set rq8.endpoints.ibc_public.{enabled,src_rpc,dst_rpc}"))

    br = ep.get("bridge") or {}
    if br.get("graph_url"):
        argv = ["collect_bridge.py", "--graph-url", br["graph_url"]]
        for k, flag in (("query", "--query"), ("deposits_key", "--deposits-key"),
                        ("fills_key", "--fills-key")):
            if br.get(k):
                argv += [flag, str(br[k])]
        plan.append(("bridge", argv, None))
    else:
        plan.append(("bridge", None, "set rq8.endpoints.bridge.graph_url (a bridge subgraph)"))

    dv = ep.get("devnet") or {}
    if dv.get("enabled", True):          # shadow backend: no external infra
        eps = str(dv.get("positive_episodes", 60))
        plan.append(("devnet",
                     ["collect_devnet.py", "--chain-id", "fastexit-devnet-positive",
                      "--episodes", eps], None))
        # Pair episodes INTO the bridge file only when the bridge marginal is being
        # collected. Episodes run on a private (allowlisted) chain-id; only the
        # output file is the bridge path (the safety gate forbids a public chain-id).
        if dv.get("pair_bridge", True) and br.get("graph_url"):
            plan.append(("devnet-pair",
                         ["collect_devnet.py", "--chain-id", "shardbribe-localnet-1",
                          "--out", "results/measured/across-v3.jsonl", "--append",
                          "--episodes", eps], None))
    else:
        plan.append(("devnet", None, "set rq8.endpoints.devnet.enabled: true"))

    rg = ep.get("reorg") or {}
    if rg.get("corpus"):
        plan.append(("reorg", ["collect_reorg.py", "--corpus", rg["corpus"]], None))
    else:
        plan.append(("reorg", None, "set rq8.endpoints.reorg.corpus (a .csv/.json you assemble)"))

    pm = ep.get("postmortem") or {}
    if pm.get("corpus"):
        plan.append(("postmortem", ["collect_postmortem.py", "--corpus", pm["corpus"]], None))
    else:
        plan.append(("postmortem", None, "set rq8.endpoints.postmortem.corpus (a .csv/.json)"))

    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join("configs", "main.yaml"))
    ap.add_argument("--only", default=None, help="run a single arm by name")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--assemble", action="store_true",
                    help="run run_all.py + make_tables.py after collecting")
    args = ap.parse_args()

    ep = _load_endpoints(os.path.join(HERE, args.config))
    plan = _plan(ep)
    if args.only:
        plan = [p for p in plan if p[0].startswith(args.only)]
        if not plan:
            print(f"[measure_all] no arm matches --only {args.only!r}")
            return 1

    ran, skipped, failed = 0, 0, 0
    print("[measure_all] RQ8 collection plan:")
    for arm, argv, skip in plan:
        if skip:
            print(f"  - {arm:12s} SKIP  ({skip})")
            skipped += 1
            continue
        cmd = [PY] + argv
        print(f"  - {arm:12s} RUN   {' '.join(argv)}")
        if args.dry_run:
            continue
        rc = subprocess.run(cmd, cwd=HERE).returncode
        if rc == 0:
            ran += 1
        else:
            failed += 1
            print(f"    ! {arm} exited {rc}")
    if args.dry_run:
        print("[measure_all] dry run; nothing executed.")
        return 0

    print(f"[measure_all] arms run: {ran}, skipped: {skipped}, failed: {failed}")
    if args.assemble and ran:
        print("[measure_all] assembling: run_all.py + make_tables.py ...")
        subprocess.run([PY, "run_all.py", "--config", args.config], cwd=HERE)
        subprocess.run([PY, "make_tables.py", "--input", "results/main.json",
                        "--out", os.path.join("..", "Paper", "Section", "_generated")], cwd=HERE)
        print("[measure_all] done. RQ8 macros + tab_measured.tex regenerated.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
