#!/usr/bin/env bash
# Local (Git Bash): regenerate only some assets on the GPU box on top of the current build/vis_assets, validate the
# whole set, render per-asset QA views, fetch the changed .glb/meta, manifest.json and qa/<NAME>_views.jpg back.
#   bash tools/blender/run_remote_partial.sh "BLD_GF_ShophouseAwning,RSD_Palm_A" [control-asset] [ssh-host]
# Nothing but tools/blender and the current build .glb/meta go to the box (no .env, no keys).
set -eu
ONLY=$1
CONTROL=${2:-BLD_GF_CommercialBay}
HOST=${3:-vast-rtx6000-1}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
OUT="$REPO/build/vis_assets"
SSH="ssh -o BatchMode=yes $HOST"
$SSH 'mkdir -p /root/robloxrace/vis/tools /root/robloxrace/vis/out && rm -rf /root/robloxrace/vis/tools/blender /root/robloxrace/vis/out/base && mkdir -p /root/robloxrace/vis/out/base'
tar -cf - --exclude=__pycache__ -C "$REPO/tools" blender | $SSH 'tar -xf - -C /root/robloxrace/vis/tools'
tar -cf - -C "$OUT" buildings roadside racing meta manifest.json | $SSH 'tar -xf - -C /root/robloxrace/vis/out/base'
set +e
$SSH "ONLY='$ONLY' CONTROL='$CONTROL' bash /root/robloxrace/vis/tools/blender/remote_partial.sh"
rc=$?
set -e
mkdir -p "$OUT/qa"
files="manifest.json"
for n in ${ONLY//,/ }; do
  for fam in buildings roadside racing; do
    $SSH "test -f /root/robloxrace/vis/out/part/$fam/$n.glb" && files="$files $fam/$n.glb meta/$n.json"
  done
done
$SSH "cd /root/robloxrace/vis/out/part && tar -cf - $files" | tar -xf - -C "$OUT"
$SSH 'cd /root/robloxrace/vis/out/part/qa_views && tar -cf - *_views.jpg' | tar -xf - -C "$OUT/qa"
echo "fetched $files and qa/*_views.jpg into $OUT (remote validate rc=$rc)"
exit $rc
