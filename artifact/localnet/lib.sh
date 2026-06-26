#!/usr/bin/env bash
# Helpers shared by setup_localnet.sh / run_episode.sh. Source after env.sh.
set -euo pipefail

# Preflight: required tools present, gaiad version sane, chain-id allowlisted.
preflight() {
  command -v "$GAIAD" >/dev/null 2>&1 || die "gaiad not on PATH (set GAIAD=...)"
  command -v "$JQ"    >/dev/null 2>&1 || die "jq not on PATH"
  command -v "$PYTHON">/dev/null 2>&1 || die "python3 not on PATH"
  local v; v="$("$GAIAD" version 2>&1 | head -1 || true)"
  log "gaiad version: ${v:-unknown}  (recipe validated on v19.2.0)"
  # the equivocation leg is HARD-gated to the allowlist in livemeasure.py; check
  # here too so we fail fast on a typo'd / shared chain-id BEFORE genesis.
  ( cd "$ARTIFACT_DIR" && "$PYTHON" -c "
from shardbribe.livemeasure import assert_localnet_only
import sys
assert_localnet_only(sys.argv[1])
print('chain-id allowlisted:', sys.argv[1])
" "$1" ) || die "chain-id '$1' is NOT in ALLOWED_EQUIVOCATION_CHAINS (refusing)."
}

# Block until a CometBFT RPC answers /status with a height >= 1.
wait_rpc() {
  local rpc="$1" tries="${2:-60}"
  for _ in $(seq 1 "$tries"); do
    if curl -s --max-time 2 "$rpc/status" 2>/dev/null \
        | "$JQ" -e '.result.sync_info.latest_block_height|tonumber>=1' >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  die "RPC $rpc did not come up after ${tries}s"
}

rpc_height() { curl -s --max-time 2 "$1/status" | "$JQ" -r '.result.sync_info.latest_block_height'; }

# Return the height of the FIRST block carrying DuplicateVoteEvidence on $rpc,
# scanning from $from upward up to the current head; empty if none yet.
find_evidence_height() {
  local rpc="$1" from="$2" head; head="$(rpc_height "$rpc")"
  local h
  for (( h=from; h<=head; h++ )); do
    if curl -s --max-time 3 "$rpc/block?height=$h" \
        | "$JQ" -e '.result.block.evidence.evidence | length > 0' >/dev/null 2>&1; then
      echo "$h"; return 0
    fi
  done
  return 1
}

# jq-edit a JSON file in place (genesis/config) via a tmp file.
json_edit() { local f="$1" filter="$2"; "$JQ" "$filter" "$f" > "$f.tmp" && mv "$f.tmp" "$f"; }

# kill any nodes we started (by pidfile) and free the homes.
teardown() {
  local d
  for d in "$WORK"/val0 "$WORK"/val1a "$WORK"/val1b; do
    [ -f "$d/node.pid" ] && kill "$(cat "$d/node.pid")" 2>/dev/null || true
  done
  # catch any node not tracked by a pidfile (crash/restart) -- scoped to OUR work
  # dir so a separately-running localnet is never touched.
  pkill -f "$WORK" 2>/dev/null || true
  sleep 1
}
