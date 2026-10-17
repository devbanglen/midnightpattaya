#!/usr/bin/env bash
# Re-project colours on the multi-view cars, export Roblox-ready GLBs (wheels cut out + wheel layout), render checks.
cd /root/robloxrace/hy
PY=/root/ayothaya/hy/hyenv/bin/python
mkdir -p qa_glb
for c in "$@"; do
  $PY gpu/project_views.py out_mv/${c}_tex.obj views $c out_mvp | grep -e IoU -e projected
  $PY gpu/export_car.py out_mvp $c
  bash /root/kit/fleet/gslot.sh -- /root/w/blender/blender -b -P gpu/bl_turntable.py -- out_mvp/$c.glb qa_glb/$c.png > /dev/null 2>&1
  rm -f qa_glb/$c.png.v?.png
done
echo EXPORT DONE
