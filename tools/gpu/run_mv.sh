#!/usr/bin/env bash
# Multi-view cars: 2mv shape + 2.1 base paint (mv_car.py), then exact colours from the 5 views (project_views.py),
# then 6-view previews. Takes a shared Hunyuan slot per car.
#   bash /root/robloxrace/hy/run_mv.sh <id> [<id> ...]
cd /root/robloxrace/hy
export HF_HOME=/root/ayothaya/hy/hf HF_HUB_OFFLINE=1
PY=/root/ayothaya/hy/hyenv/bin/python
mkdir -p out_mv out_mvp qa
for c in "$@"; do
  s=$(date +%s)
  bash /root/kit/fleet/gslot.sh --hy -- $PY gpu/mv_car.py views out_mv $c || { echo "FAIL $c shape/paint"; continue; }
  $PY gpu/project_views.py out_mv/${c}_tex.obj views $c out_mvp | tail -2
  echo "$c done in $(( $(date +%s)-s ))s"
done
bash render_qa.sh out_mvp _proj.obj
echo RUN_MV DONE
