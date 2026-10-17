#!/usr/bin/env bash
# Render a 6-view preview strip of every textured OBJ in <dir> matching <suffix> into qa/ (Blender slot on the shared box).
#   bash /root/robloxrace/hy/render_qa.sh [dir] [suffix]      e.g. render_qa.sh out_proj _proj.obj
cd /root/robloxrace/hy
DIR=${1:-out}; SUF=${2:-_tex.obj}
mkdir -p qa
for f in "$DIR"/*"$SUF"; do
  n=$(basename "$f" .obj)
  bash /root/kit/fleet/gslot.sh -- /root/w/blender/blender -b -P gpu/bl_turntable.py -- "$f" "qa/$n.png" > "qa/$n.log" 2>&1 \
    && echo "ok $n" || echo "FAIL $n (qa/$n.log)"
  rm -f "qa/$n.png".v?.png
done
