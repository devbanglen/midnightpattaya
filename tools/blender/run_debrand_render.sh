#!/usr/bin/env bash
# Render close-ups / turntable of a built car on the GPU box (Blender, Workbench) and fetch the PNGs.
#   bash tools/blender/run_debrand_render.sh <car_dir> <id> <out_dir> <tag> [views.json]
# Sends ONLY <id>.glb, the 4 wheel GLBs, <id>_wheels.json, the render script and the views file. No .env, no keys.
set -euo pipefail
CAR=$1; ID=$2; OUT=$3; TAG=$4
HERE=$(cd "$(dirname "$0")/../.." && pwd)
VIEWS=${5:-$HERE/tools/blender/debrand_views.json}
HOST=vast-rtx6000-1
RD=/root/robloxrace/car_debrand
BL=/root/w/blender/blender
mkdir -p "$OUT"
ssh $HOST "rm -rf $RD/car/$ID $RD/r/$ID-$TAG; mkdir -p $RD/car/$ID $RD/r/$ID-$TAG"
scp -q "$CAR/$ID.glb" "$CAR/${ID}_wheels.json" "$CAR"/${ID}_wheel_??.glb $HOST:$RD/car/$ID/
scp -q "$HERE/tools/blender/car_debrand_render.py" $HOST:$RD/
scp -q "$VIEWS" $HOST:$RD/r/$ID-$TAG/views.json
ssh $HOST "cd $RD && bash /root/kit/fleet/gslot.sh -- $BL -b --factory-startup --python-exit-code 1 \
  -P car_debrand_render.py -- car/$ID $ID r/$ID-$TAG --views r/$ID-$TAG/views.json --tag $TAG ${RES_ARGS:-} \
  > r/$ID-$TAG/render.log 2>&1; echo exit \$?; grep -c wrote r/$ID-$TAG/render.log; tail -2 r/$ID-$TAG/render.log"
scp -q $HOST:"$RD/r/$ID-$TAG/*.png" "$OUT/"
