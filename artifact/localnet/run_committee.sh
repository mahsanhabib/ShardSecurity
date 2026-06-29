#!/usr/bin/env bash
# Drive the faithful N=4 committee fork end-to-end on real client code and fold a
# committee-fork record into RQ8. Usage: run_committee.sh [--assemble]
#
#   -> results/measured/committee-fork-rpc.jsonl
#
# Steps: genesis the N=4 committee (setup_committee.sh) -> start the 6 partitioned
# nodes -> inject a DIFFERENT spend of the SAME e1 coins in each partition (real
# double-spend) -> SCAN for a height H where the two partitions' /commit certs
# genuinely conflict at the SAME (height,round) with >= F+1=2 shared signers (the
# quorum-intersection floor + honest split) -> HEAL the partition -> collect the real
# x/slashing of BOTH equivocators. The same-round conflict is flaky (proposer must be
# a shared equivocator), so we inject+scan in a retry loop, exactly like run_arm.sh
# oversamples the double-sign trigger.
#
# AUTHORED against the v0.50/gaiad-v19 recipe (as arms A/C/B were); the live run is
# the operator's step (needs running consensus nodes). See N4-COMMITTEE.md.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/env.sh"; source "$HERE/lib.sh"
ASSEMBLE="${1:-}"

CHAIN="$CHAIN_N4"; WORK="$WORK_N4"
H_E1A="$WORK/e1a"; H_E2A="$WORK/e2a"; H_H1="$WORK/h1"
H_E1B="$WORK/e1b"; H_E2B="$WORK/e2b"; H_H2="$WORK/h2"
ALL_HOMES=("$H_E1A" "$H_E2A" "$H_H1" "$H_E1B" "$H_E2B" "$H_H2")
OUT="$ARTIFACT_DIR/results/measured/committee-fork-rpc.jsonl"

start_node() { # start_node <home>
  local home="$1"
  nohup "$GAIAD" start --home "$home" --x-crisis-skip-assert-invariants \
    >"$home/node.log" 2>&1 &
  echo $! > "$home/node.pid"
}
stop_all() { local h; for h in "${ALL_HOMES[@]}"; do
  [ -f "$h/node.pid" ] && kill "$(cat "$h/node.pid")" 2>/dev/null || true; done
  pkill -f "$WORK" 2>/dev/null || true; }
trap stop_all EXIT

# 1. genesis + partitioned topology
bash "$HERE/setup_committee.sh"
# shellcheck disable=SC1090
source "$WORK/.committee"          # CHAIN, A_PEERS, B_PEERS, ACCT_E1

# 2. start all 6 nodes (partitions isolated by the intra-partition peer config)
log "[N4] starting 6 nodes (partition A: e1a,e2a,h1 | partition B: e1b,e2b,h2)"
for h in "${ALL_HOMES[@]}"; do start_node "$h"; done
wait_rpc "$RPC_A"; wait_rpc "$RPC_B"
log "[N4] both partitions producing (A=$RPC_A B=$RPC_B)"

# helper: ask Python whether RPC_A and RPC_B have a valid conflicting cert at $1.
fork_ok_at() { # fork_ok_at <height> -> prints "1" if quorum_intersection_ok
  ( cd "$ARTIFACT_DIR" && "$PYTHON" - "$RPC_A" "$RPC_B" "$1" <<'PY'
import sys, json, urllib.request
from shardbribe.livemeasure import parse_committee_fork
def commit(rpc, h):
    req=urllib.request.Request(f"{rpc}/commit?height={h}",
        headers={"Accept":"application/json","User-Agent":"n4"})
    with urllib.request.urlopen(req, timeout=5) as r: return json.loads(r.read())
ra, rb, h = sys.argv[1], sys.argv[2], int(sys.argv[3])
try:
    f = parse_committee_fork(commit(ra,h), commit(rb,h), F=1)
except Exception:
    print("0"); sys.exit(0)
print("1" if f.get("quorum_intersection_ok") else "0")
PY
  ) 2>/dev/null || echo "0"
}

# 3. inject divergent double-spends + scan for a valid conflicting height.
#    e1 spends its surplus to h1 in partition A and to h2 in partition B (same coins,
#    two ways). Both txs use e1 sequence 0 (each partition is independent), so they
#    are mutually exclusive after heal -- a real double-spend the two certs encode.
TX=(tx bank send e1 --keyring-backend test --chain-id "$CHAIN" --home "$H_E1A"
    --fees "${UNBOND_FEES:-2000}$DENOM" --gas 400000 --sequence 0 -y)
FORK_H=""; attempt=0; MAX="${N4_MAX_ATTEMPTS:-30}"
recipientA="$("$GAIAD" keys show h1 -a --keyring-backend test --home "$H_H1")"
recipientB="$("$GAIAD" keys show h2 -a --keyring-backend test --home "$H_H2")"
while [ -z "$FORK_H" ] && [ "$attempt" -lt "$MAX" ]; do
  attempt=$((attempt+1))
  base="$(rpc_height "$RPC_A")"; target=$(( base + 1 ))
  log "[N4] attempt $attempt: double-spend e1 -> {h1 in A | h2 in B}, aiming near height $target"
  "$GAIAD" "${TX[@]}" "$recipientA" "$N4_DOUBLESPEND_AMT$DENOM" --node "$RPC_A" >/dev/null 2>&1 || true
  "$GAIAD" "${TX[@]}" "$recipientB" "$N4_DOUBLESPEND_AMT$DENOM" --node "$RPC_B" >/dev/null 2>&1 || true
  sleep 3
  # scan the recent window on BOTH partitions for a same-(H,round) conflicting cert
  headA="$(rpc_height "$RPC_A")"
  for (( h=target; h<=headA; h++ )); do
    if [ "$(fork_ok_at "$h")" = "1" ]; then FORK_H="$h"; break; fi
  done
done
[ -n "$FORK_H" ] || die "no valid conflicting cert after $attempt attempts (raise N4_MAX_ATTEMPTS; check that the round-0 proposer landed on a shared equivocator -- see node.logs)."
log "[N4] CAPTURED conflicting certs at height $FORK_H (2 distinct equivocators + honest split)"
echo "$FORK_H" > "$WORK/.fork_height"

# 4. HEAL: append the cross-partition peers and restart so the conflicting precommits
#    gossip -> DuplicateVoteEvidence for BOTH e1,e2 -> real x/evidence -> x/slashing.
log "[N4] healing partition (append cross-peers, restart) to land the real slash"
stop_all; sleep 2
ALL_PEERS="$A_PEERS,$B_PEERS"
for h in "${ALL_HOMES[@]}"; do
  sed -i -e "s#^persistent_peers = .*#persistent_peers = \"$ALL_PEERS\"#" "$h/config/config.toml"
done
for h in "${ALL_HOMES[@]}"; do start_node "$h"; done
# one partition may halt on the apphash conflict; that is acceptable (documented) --
# the structural fork at $FORK_H is already captured. Best-effort wait for the slash.
sleep "$N4_HEAL_WAIT"

# 5. collect: read both /commits at $FORK_H + the real slashes -> committee-fork record
log "[N4] collecting committee-fork record -> $OUT"
( cd "$ARTIFACT_DIR" && "$PYTHON" collect_devnet.py --committee \
    --rpc-a "$RPC_A" --rpc-b "$RPC_B" --fork-height "$FORK_H" \
    --chain "$CHAIN" --slash-window "$N4_SLASH_WINDOW" --out "$OUT" )
n=$(grep -c . "$OUT" 2>/dev/null || true); n=${n:-0}
[ "$n" -gt 0 ] || die "collect wrote no record — inspect $WORK/*/node.log"
log "[N4] wrote $n record(s). Inspect quorum_intersection_ok / n_equivocators / n_slashed."

if [ "$ASSEMBLE" = "--assemble" ]; then
  log "[N4] assembling: run_all.py + make_tables.py (run on Windows if numpy missing)"
  ( cd "$ARTIFACT_DIR" && "$PYTHON" run_all.py --config configs/main.yaml \
      && "$PYTHON" make_tables.py --input results/main.json --out ../Paper/Section/_generated )
fi
