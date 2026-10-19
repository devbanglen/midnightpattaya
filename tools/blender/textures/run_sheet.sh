#!/usr/bin/env bash
# Local (Git Bash): render the VIS-7.1c material QA sheet on the GPU box and fetch it.
#   bash tools/blender/textures/run_sheet.sh [ssh-host] [glb-dir]
#     ssh-host default vast-rtx6000-1; glb-dir default build/vis_assets (needs buildings/ + roadside/ GLBs)
# Sends ONLY tools/blender/{textures,common}, the generated PNG maps (build/materials/<Set>/*.png) and four kit GLBs
# into its own folder /root/robloxrace/vis/team7tex (never .env, never keys; does not touch the pipeline's tools/ or
# out/). Blender runs through the fleet slot manager. Result: build/materials/qa/*.png + material_sheet.jpg.
set -eu
HOST=${1:-vast-rtx6000-1}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
GLB=${2:-$REPO/build/vis_assets}
R=/root/robloxrace/vis/team7tex
SSH="ssh -o BatchMode=yes $HOST"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/tools/blender" "$STAGE/maps" "$STAGE/glb/buildings" "$STAGE/glb/roadside"
cp -r "$REPO/tools/blender/textures" "$REPO/tools/blender/common" "$STAGE/tools/blender/"
(cd "$REPO/build/materials" && for d in */; do [ "$d" = "qa/" ] && continue; mkdir -p "$STAGE/maps/$d"; cp "$d"*.png "$STAGE/maps/$d"; done)
for a in BLD_GF_ShophouseShutter BLD_MF_BalconyRow BLD_GF_Restaurant; do cp "$GLB/buildings/$a.glb" "$STAGE/glb/buildings/"; done
cp "$GLB/roadside/RSD_Palm_A.glb" "$STAGE/glb/roadside/"
find "$STAGE" -name __pycache__ -prune -exec rm -rf {} +
$SSH "rm -rf $R && mkdir -p $R"
tar -cf - -C "$STAGE" . | $SSH "tar -xf - -C $R"
set +e
$SSH "cd $R && bash /root/kit/fleet/gslot.sh -- /root/w/blender/blender -b --factory-startup --python-exit-code 1 \
  -P tools/blender/textures/render_sheet.py -- maps glb out > render.log 2>&1; rc=\$?; grep -E '^(RENDER|DONE|Traceback|Error)' render.log; tail -5 render.log; exit \$rc"
rc=$?
set -e
mkdir -p "$REPO/build/materials/qa"
$SSH "cd $R && tar -cf - out render.log" | tar -xf - -C "$REPO/build/materials/qa" --strip-components=0
echo "fetched into build/materials/qa (blender rc=$rc)"
exit $rc
