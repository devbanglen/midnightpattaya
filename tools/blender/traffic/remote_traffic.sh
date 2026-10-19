#!/usr/bin/env bash
# Runs ON the GPU box (called by run_traffic.sh). Own work dir /root/robloxrace/vis/team9traffic so no other team's
# tools/blender or out/ is touched. Every Blender call goes through the fleet slot manager (never pkill).
set -u
W=/root/robloxrace/vis/team9traffic
BL=${BLENDER:-/root/w/blender/blender}
SLOT="bash /root/kit/fleet/gslot.sh --"
cd "$W" || exit 2
rm -rf out && mkdir -p out logs
$SLOT "$BL" -b --factory-startup --python-exit-code 1 -P tools/blender/gen_traffic.py -- --out out \
  > logs/gen_traffic.log 2>&1 || { tail -40 logs/gen_traffic.log; exit 3; }
grep -E '^(EXPORT|DONE)' logs/gen_traffic.log
python3 tools/blender/traffic/validate_traffic.py out > logs/validate_traffic.log 2>&1; vrc=$?
cat logs/validate_traffic.log
NAMES=$(cd out/traffic && ls *.glb | sed 's/\.glb$//' | paste -sd, -)
$SLOT "$BL" -b --factory-startup --python-exit-code 1 -P tools/blender/traffic/qa_traffic.py -- out/traffic \
  out/traffic/qa --views "$NAMES" > logs/qa_traffic.log 2>&1 || tail -40 logs/qa_traffic.log
grep -c '^RENDER' logs/qa_traffic.log
python3 tools/blender/qa_compose.py out/traffic/qa
exit $vrc
