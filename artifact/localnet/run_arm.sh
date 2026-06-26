#!/usr/bin/env bash
# Drive a full arm: N fresh-genesis episodes (a tombstone is permanent per
# validator, so one slash per genesis) accumulated into one JSONL, then fold
# into the RQ8 pipeline. Usage: run_arm.sh <A|C> [--assemble]
#
#   Arm A -> results/measured/devnet-rpc-gaiad.jsonl        (real-code q_attack/T_acc, n=N)
#   Arm C -> results/measured/fastexit-devnet-positive-rpc.jsonl (real-code positive control)
#
# Arm C uses a NEW stem (…-rpc) so it never clobbers the shadow
# fastexit-devnet-positive.jsonl; swap the paper row once you trust the real run.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/env.sh"; source "$HERE/lib.sh"   # log/die, A_/C_/B_ params, rpc helpers

ARM="${1:?usage: run_arm.sh <A|C|B-open|B-gated> [--assemble]}"; ASSEMBLE="${2:-}"
# Arm-B (paired race) episodes pass GATE_DEPTH as run_episode's $3 and GATED as $4;
# arms A/C pass the stake-exit lead as $3. ARG3/ARG4 abstract that difference.
GATED=0
case "$ARM" in
  A) STEM="devnet-rpc-gaiad";              UNBONDING="$A_UNBONDING"; ARG3=$(( ${UNBONDING%s} * 1000 )); ARG4=0; EARM="A";;
  C) STEM="fastexit-devnet-positive-rpc";  UNBONDING="$C_UNBONDING"; ARG3=$(( ${UNBONDING%s} * 1000 )); ARG4=0; EARM="C";;
  B-open)  STEM="across-v3-selffill-rpc";       ARG3="$B_GATE_DEPTH_OPEN";  ARG4=0; GATED=0; EARM="B";;
  B-gated) STEM="across-v3-paired-gated-rpc";   ARG3="$B_GATE_DEPTH_GATED"; ARG4=1; GATED=1; EARM="B";;
  *) die "arm must be A, C, B-open, or B-gated";;
esac
OUT="$ARTIFACT_DIR/results/measured/$STEM.jsonl"

# Arm B: stand up the destination "bridge" zone ONCE (it persists across episodes;
# only the source re-genesises per episode). Tear it down on exit.
DST_PID=""
dst_down() { [ -n "$DST_PID" ] && kill "$DST_PID" 2>/dev/null || true; pkill -f "$WORK_DST" 2>/dev/null || true; }
if [ "$EARM" = "B" ]; then
  trap dst_down EXIT
  pkill -f "$WORK_DST" 2>/dev/null || true; sleep 1
  bash "$HERE/setup_destzone.sh"
  nohup "$GAIAD" start --home "$WORK_DST/dstval" --x-crisis-skip-assert-invariants \
    >"$WORK_DST/dstval/node.log" 2>&1 &
  DST_PID=$!
  wait_rpc "$DST_RPC"
  log "destination bridge zone up on $DST_RPC (pid $DST_PID, gate_depth=$ARG3, gated=$ARG4)"
fi
# Don't silently destroy a previously captured real-code record (e.g. the hand-run
# n=1 in devnet-rpc-gaiad.jsonl). Back it up before starting a fresh run.
if [ -s "$OUT" ]; then
  BAK="$OUT.bak.$(date +%s)"; cp "$OUT" "$BAK"
  log "backed up $(grep -c . "$OUT") existing record(s) -> $BAK"
fi
: > "$OUT"                                            # fresh run: real-code records only

# The double-sign trigger is flaky, so oversample: keep launching episodes until we
# have TARGET records or hit the attempt cap (push-button N>=40 instead of best-effort).
TARGET="$EPISODES"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-$(( EPISODES * 3 ))}"
log "ARM $ARM -> $OUT  (target n=$TARGET, <=$MAX_ATTEMPTS attempts, arg3=$ARG3 gated=$ARG4)"
ok=0; attempt=0
while [ "$ok" -lt "$TARGET" ] && [ "$attempt" -lt "$MAX_ATTEMPTS" ]; do
  attempt=$((attempt+1))
  log "=== attempt $attempt  (have $ok/$TARGET records) ==="
  # invoke via `bash` (not direct exec) so a Windows-staged copy without the +x
  # bit still runs; same reason setup_localnet.sh is called via bash in run_episode.
  if bash "$HERE/run_episode.sh" "$EARM" "$OUT" "$ARG3" "$ARG4"; then
    ok=$((ok+1))
  else
    log "attempt $attempt did not yield evidence (continuing)"   # best-effort: trigger is flaky
  fi
done
n=$(grep -c . "$OUT" 2>/dev/null || true); n=${n:-0}
log "ARM $ARM done: $ok/$TARGET records from $attempt attempts; $n lines in $OUT"
[ "$ok" -ge "$TARGET" ] || log "WARN: only $ok/$TARGET records after $attempt attempts — raise MAX_ATTEMPTS or tune the trigger."
[ "$n" -gt 0 ] || die "no records captured — inspect $WORK/val*/node.log and tune the trigger."

# regenerate the sha sidecar so write_jsonl's provenance check stays consistent
( cd "$ARTIFACT_DIR" && "$PYTHON" - "$OUT" <<'PY'
import hashlib,sys,pathlib
p=pathlib.Path(sys.argv[1]); payload=p.read_text().rstrip("\n")
p.with_suffix(".sha256").write_text(hashlib.sha256(payload.encode()).hexdigest()+"\n")
print("[run_arm] wrote", p.with_suffix(".sha256").name)
PY
)

if [ "$ASSEMBLE" = "--assemble" ]; then
  log "assembling: run_all.py + make_tables.py"
  ( cd "$ARTIFACT_DIR" && "$PYTHON" run_all.py --config configs/main.yaml \
      && "$PYTHON" make_tables.py --input results/main.json --out ../Paper/Section/_generated )
  log "RQ8 regenerated. Review the $STEM row in tab_measured.tex."
fi
