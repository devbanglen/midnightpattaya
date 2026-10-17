#!/usr/bin/env bash
# Hunyuan3D-2.1 image -> textured 3D for this project on the shared GPU box (vast-rtx6000-1).
# Works only in /root/robloxrace; uses the installed Hunyuan env/weights read-only; takes a shared Hunyuan slot.
#   bash /root/robloxrace/hy/run_hy.sh <in dir> <out dir> [extra batch.py args]
cd /root/robloxrace/hy
export HF_HOME=/root/ayothaya/hy/hf HY3D_REPO=/root/ayothaya/hy/Hunyuan3D-2.1 HF_HUB_OFFLINE=1
IN=${1:-in}; OUT=${2:-out}; shift 2
s=$(date +%s)
bash /root/kit/fleet/gslot.sh --hy -- /root/ayothaya/hy/hyenv/bin/python gpu/batch.py "$IN" "$OUT" \
  --texture --steps 30 --octree 256 --tex-size 2048 --render-size 1024 --no-upright "$@"
echo "EXIT $? TOTAL $(( $(date +%s)-s ))s"
