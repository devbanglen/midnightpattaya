#!/usr/bin/env bash
# Round 2: new shapes for the 3 redesigned fronts (from the new 3/4 views), then exact colours from all 5 views on all 6.
cd /root/robloxrace/hy
mkdir -p in_r2 out_r2 out_proj
for c in kei muscle gt_sedan; do cp -n views/${c}_34.png in_r2/${c}.png; done
echo '{"kei": 18000, "muscle": 18000, "gt_sedan": 18000}' > in_r2/faces.json
bash run_hy.sh in_r2 out_r2
PY=/root/ayothaya/hy/hyenv/bin/python
for c in jdm_coupe hatch supercar; do $PY gpu/project_views.py out/r1_${c}_tex.obj views $c out_proj | tail -3; done
for c in kei muscle gt_sedan; do $PY gpu/project_views.py out_r2/${c}_tex.obj views $c out_proj | tail -3; done
for f in out_proj/*_proj.obj; do
  n=$(basename $f .obj)
  bash /root/kit/fleet/gslot.sh -- /root/w/blender/blender -b -P gpu/bl_turntable.py -- $f qa/$n.png > /dev/null 2>&1
done
rm -f qa/*.v?.png
echo ROUND2 DONE
