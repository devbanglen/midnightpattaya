#!/usr/bin/env bash
# Convert a built car's GLBs (body + 4 wheels) to FBX on the GPU box and fetch them.
#   bash tools/blender/run_car_fbx.sh <car_dir> <id> <out_dir>
# Sends ONLY the 5 GLBs, <id>_wheels.json and the script. No .env, no keys. Nothing is uploaded anywhere else.
set -euo pipefail
CAR=$1; ID=$2; OUT=$3
HERE=$(cd "$(dirname "$0")/../.." && pwd)
HOST=vast-rtx6000-1
RD=/root/robloxrace/car_debrand
BL=/root/w/blender/blender
mkdir -p "$OUT"
ssh $HOST "rm -rf $RD/car/$ID $RD/fbx/$ID; mkdir -p $RD/car/$ID $RD/fbx/$ID"
scp -q "$CAR/$ID.glb" "$CAR/${ID}_wheels.json" "$CAR"/${ID}_wheel_??.glb $HOST:$RD/car/$ID/
scp -q "$HERE/tools/blender/car_glb_to_fbx.py" $HOST:$RD/
ssh $HOST "cd $RD && bash /root/kit/fleet/gslot.sh -- $BL -b --factory-startup --python-exit-code 1 \
  -P car_glb_to_fbx.py -- car/$ID $ID fbx/$ID > fbx/$ID/fbx.log 2>&1; echo exit \$?; tail -3 fbx/$ID/fbx.log"
scp -q $HOST:"$RD/fbx/$ID/*.fbx" $HOST:"$RD/fbx/$ID/${ID}_fbx.json" "$OUT/"
