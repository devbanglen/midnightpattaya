#!/usr/bin/env bash
# Local (Git Bash): push tools/blender to the GPU box, generate + validate + QA-render the traffic vehicles, fetch
# build/vis_assets/traffic/ ({*.glb, meta/, manifest.json, qa/, logs/}).
#   bash tools/blender/traffic/run_traffic.sh [ssh-host]       (default vast-rtx6000-1)
# Nothing but tools/blender goes to the box (no .env, no keys); the box work dir is /root/robloxrace/vis/team9traffic.
set -eu
HOST=${1:-vast-rtx6000-1}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
OUT="$REPO/build/vis_assets/traffic"
SSH="ssh -o BatchMode=yes $HOST"
W=/root/robloxrace/vis/team9traffic
$SSH "mkdir -p $W/tools && rm -rf $W/tools/blender"
tar -cf - --exclude=__pycache__ -C "$REPO/tools" blender | $SSH "tar -xf - -C $W/tools"
set +e
$SSH "bash $W/tools/blender/traffic/remote_traffic.sh"
rc=$?
set -e
rm -rf "$OUT" && mkdir -p "$OUT"
$SSH "cd $W/out/traffic && tar -cf - ." | tar -xf - -C "$OUT"
mkdir -p "$OUT/logs"
$SSH "cd $W/logs && tar -cf - ." | tar -xf - -C "$OUT/logs"
echo "fetched into $OUT (remote validate rc=$rc)"
exit $rc
