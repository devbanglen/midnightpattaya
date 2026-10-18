#!/usr/bin/env bash
# Local (Git Bash / Linux / macOS): push tools/blender to the GPU box, run the whole pipeline headless, fetch results.
#   bash tools/blender/run_remote.sh [ssh-host]       (default host alias: vast-rtx6000-1)
# Results: build/vis_assets/{buildings,roadside,racing}/*.glb, meta/, manifest.json, qa/*.png, logs/*.log
# Nothing but tools/blender goes to the box (no .env, no keys); everything stays under /root/robloxrace/vis.
set -eu
HOST=${1:-vast-rtx6000-1}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
OUT="$REPO/build/vis_assets"
SSH="ssh -o BatchMode=yes $HOST"
$SSH 'mkdir -p /root/robloxrace/vis/tools && rm -rf /root/robloxrace/vis/tools/blender'
tar -cf - --exclude=__pycache__ -C "$REPO/tools" blender | $SSH 'tar -xf - -C /root/robloxrace/vis/tools'
set +e
$SSH 'bash /root/robloxrace/vis/tools/blender/remote_job.sh'
rc=$?
set -e
mkdir -p "$OUT"
rm -rf "$OUT/buildings" "$OUT/roadside" "$OUT/racing" "$OUT/meta" "$OUT/qa" "$OUT/logs"
$SSH 'cd /root/robloxrace/vis && tar -cf - -C out/run . && true' | tar -xf - -C "$OUT"
mkdir -p "$OUT/logs"
$SSH 'cd /root/robloxrace/vis && tar -cf - -C logs .' | tar -xf - -C "$OUT/logs"
echo "fetched into $OUT (remote validate rc=$rc)"
cat "$OUT/logs/timings.txt"
exit $rc
