#!/usr/bin/env bash
echo "=== tools ==="
for t in gaiad jq python3 curl; do printf "%s: " "$t"; command -v "$t" || echo MISSING; done
echo
echo "=== gaiad version ==="
gaiad version 2>&1 | head -3
echo
echo "=== existing WSL localnet (~/sb-localnet) ==="
ls -d ~/sb-localnet 2>/dev/null && ls ~/sb-localnet 2>/dev/null | head
echo
echo "=== artifact dir reachable from WSL ==="
ls "$(dirname "$0")/run_arm.sh" && echo "run_arm.sh: OK"
echo
echo "=== /tmp writable (node homes) ==="
touch /tmp/_rq8_probe && rm -f /tmp/_rq8_probe && echo "/tmp: OK"
