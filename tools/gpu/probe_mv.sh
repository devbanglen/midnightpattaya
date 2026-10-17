#!/usr/bin/env bash
# Read-only look for a Hunyuan3D-2mv install + weights on the shared box.
ls -d /root/w/Hunyuan3D-2 /root/*/Hunyuan3D-2 /root/*/*/Hunyuan3D-2 2>/dev/null
for d in /root/hf /root/w/hf /dev/shm/hf /workspace/.hf_home /root/*/hf /root/*/*/hf /root/.cache/huggingface; do
  [ -d "$d/hub" ] && echo "== $d" && ls "$d/hub" | grep -i -E 'hunyuan|dinov2'
done
ls /root/.cache/hy3dgen/tencent 2>/dev/null
ls -d /root/*/hyenv /root/w/*env 2>/dev/null
free -g | head -2
