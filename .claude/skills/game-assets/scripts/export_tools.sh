#!/usr/bin/env bash
# Copy the tools this skill calls into another project (references/porting.md): export_tools.sh <target project dir>
set -euo pipefail
SRC="$(cd "$(dirname "$0")/../../../.." && pwd)"; DST="${1:?target project dir}"
files=(tools/pipeline/gen_concepts.py studio/src/char3d/glow.ts)
for f in api3d.py meshy_obj.sh bl_glb2obj.py bl_decimate.py bl_ingest.py ingest.sh weapon_fit.py item_gate.py \
         decimate_skinned.py bone_fix.py idmap.py outfit.py outfit.sh shape.py bl_spec_sheet.py bake_views.py \
         fit_check.sh bl_fit.py build_lab.py hy_hair.py; do files+=("tools/ayolab/$f"); done
for f in "${files[@]}"; do
  [ -e "$SRC/$f" ] || { echo "missing $f"; continue; }
  mkdir -p "$DST/$(dirname "$f")"; [ -e "$DST/$f" ] && { echo "exists, kept: $f"; continue; }
  cp "$SRC/$f" "$DST/$f"; echo "copied $f"
done
echo "now rewrite .claude/skills/game-assets/references/project.md for the new project"
