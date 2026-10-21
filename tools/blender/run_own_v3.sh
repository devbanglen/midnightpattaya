#!/usr/bin/env bash
# Own body v3 on the GPU box (Blender through the shared slot manager gslot.sh, one job per call), results fetched.
#   bash tools/blender/run_own_v3.sh build  <local_out_dir>
#   bash tools/blender/run_own_v3.sh render <local_car_dir> <id> <local_out_dir> <tag> [views.json] [engine] [res] [steer]
# engine workbench | eevee (GPU slot) | cycles (Cycles on the CPU, gslot --cpu: no VRAM needed, for a busy GPU).
# A paint variant without its own wheels json (<base>_red, <base>_white) renders with <base>_wheels.json.
# Writes only under /root/robloxrace/car_v3 (own job folder, removed at the end, also after an error). Sends only the
# generator script, the views file and the GLB / json inputs it needs (no .env, no keys, no personal data).
set -euo pipefail
HERE=$(cd "$(dirname "$0")/../.." && pwd)
HOST=vast-rtx6000-1
BL=/root/w/blender/blender
CMD=$1; shift
JOB=$CMD-$$
RD=/root/robloxrace/car_v3/$JOB
cleanup() { ssh $HOST "rm -rf $RD" || true; }
trap cleanup EXIT
trap 'exit 130' INT TERM HUP      # (a remote gslot job still waiting for a slot is not stopped: look its PID up)
ssh $HOST "mkdir -p $RD/in $RD/out"
scp -q "$HERE/tools/blender/car_own_v3.py" $HOST:$RD/
if [ "$CMD" = build ]; then
  OUT=$1
  mkdir -p "$OUT"
  scp -q "$HERE/art/cars3d/roblox/red_sports_original_v2_wheels.json" $HOST:$RD/in/
  ssh $HOST "cd $RD && bash /root/kit/fleet/gslot.sh --cpu -- $BL -b --factory-startup --python-exit-code 1 \
    -P car_own_v3.py -- build out --v2-dir in > out/build.log 2>&1; echo exit \$?; tail -3 out/build.log"
  scp -q $HOST:"$RD/out/*" "$OUT/"
else
  CAR=$1; ID=$2; OUT=$3; TAG=$4; VIEWS=${5:-}; ENGINE=${6:-workbench}; RES=${7:-900}; STEER=${8:-0}
  mkdir -p "$OUT"
  WJ="$CAR/${ID}_wheels.json"
  [ -f "$WJ" ] || WJ="$CAR/${ID%_*}_wheels.json"
  scp -q "$CAR/$ID.glb" "$WJ" $HOST:$RD/in/
  for w in $(grep -o '"[^"]*_wheel_[A-Z]*\.glb"' "$WJ" | tr -d '"' | sort -u); do
    scp -q "$CAR/$w" $HOST:$RD/in/
  done
  VARG=""
  if [ -n "$VIEWS" ]; then scp -q "$VIEWS" $HOST:$RD/views.json; VARG="--views views.json"; fi
  SLOT=""
  if [ "$ENGINE" = cycles ]; then SLOT="--cpu"; fi
  ssh $HOST "cd $RD && bash /root/kit/fleet/gslot.sh $SLOT -- $BL -b --factory-startup --python-exit-code 1 \
    -P car_own_v3.py -- render in $ID out $TAG $VARG --engine $ENGINE --res $RES --steer $STEER \
    --wheels in/$(basename "$WJ") > out/render.log 2>&1; echo exit \$?; grep -c wrote out/render.log; \
    tail -2 out/render.log"
  scp -q $HOST:"$RD/out/*.png" "$OUT/"
fi
