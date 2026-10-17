#!/usr/bin/env bash
# One-time: Hunyuan3D-2mv (multi-view shape). Owner chose the locations (2026-10-18):
#   code /root/Hunyuan3D-2, weights /root/Hunyuan3D-2mv (repo layout: hunyuan3d-dit-v2-mv/...)
# Reuses ayothaya's hyenv read-only (no pip installs into it).
set -e
[ -d /root/Hunyuan3D-2 ] || git clone --depth 1 https://github.com/Tencent-Hunyuan/Hunyuan3D-2 /root/Hunyuan3D-2
/root/ayothaya/hy/hyenv/bin/python - <<'EOF'
from huggingface_hub import snapshot_download
p = snapshot_download('tencent/Hunyuan3D-2mv', allow_patterns=['hunyuan3d-dit-v2-mv/*'], local_dir='/root/Hunyuan3D-2mv')
print('weights at', p)
EOF
ls -la /root/Hunyuan3D-2mv/hunyuan3d-dit-v2-mv
echo "setup done"
