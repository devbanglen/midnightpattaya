#!/usr/bin/env bash
# Car import on the GPU box: local GLB -> box (Blender build + QA) -> local out dir.
#   bash tools/blender/run_import_car.sh <car.glb> <out_dir> [car_id] [build options...]
# Sends ONLY the car GLB and the two scripts (tools/gpu/car_import_wheels.py, tools/blender/import_car.py); no .env,
# no keys. Blender runs through gslot.sh with --python-exit-code 1, under /root/robloxrace/car_import. Never pkill.
set -euo pipefail
SRC=$1; OUT=$2; ID=${3:-red_sports}; shift 3 || true; EXTRA="$*"   # extra build options, e.g. --image-format JPEG
HOST=vast-rtx6000-1
RD=/root/robloxrace/car_import
BL=/root/w/blender/blender
HERE=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$OUT"
ssh $HOST "mkdir -p $RD/in $RD/out/$ID $RD/qa/$ID"
scp -q "$SRC" $HOST:$RD/in/$ID.glb
scp -q "$HERE/tools/gpu/car_import_wheels.py" "$HERE/tools/blender/import_car.py" $HOST:$RD/
ssh $HOST "cd $RD && python3 car_import_wheels.py in/$ID.glb out/$ID/${ID}_detect.json --views qa/$ID \
  && bash /root/kit/fleet/gslot.sh -- $BL -b --factory-startup --python-exit-code 1 -P import_car.py -- \
       build in/$ID.glb out/$ID/${ID}_detect.json out/$ID --id $ID $EXTRA > out/$ID/build.log 2>&1 \
  && bash /root/kit/fleet/gslot.sh -- $BL -b --factory-startup --python-exit-code 1 -P import_car.py -- \
       qa out/$ID qa/$ID --src in/$ID.glb out/$ID/${ID}_detect.json --id $ID > out/$ID/qa.log 2>&1; \
  echo exit \$?; tail -5 out/$ID/build.log; tail -3 out/$ID/qa.log"
scp -q -r $HOST:$RD/out/$ID/. "$OUT/"
mkdir -p "$OUT/qa"
scp -q -r $HOST:$RD/qa/$ID/. "$OUT/qa/"
ls -la "$OUT" "$OUT/qa"
