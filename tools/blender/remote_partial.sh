#!/usr/bin/env bash
# Runs ON the GPU box (called by run_remote_partial.sh). Regenerates only the named assets on top of a copy of the
# current build (out/base = the local build/vis_assets that was uploaded), so every other .glb keeps its bytes, then
# validates the whole set (manifest.json) and renders per-asset QA views (+ an untouched control) with qa_render.py.
#   ONLY=A,B,C CONTROL=X bash remote_partial.sh
set -u
VIS=/root/robloxrace/vis
BL=${BLENDER:-/root/w/blender/blender}
SLOT="bash /root/kit/fleet/gslot.sh --"
cd "$VIS" || exit 2
rm -rf out/part && mkdir -p out/part logs && cp -r out/base/. out/part/
rm -rf out/part/qa_views && mkdir -p out/part/qa_views
: > logs/timings_partial.txt
for fam in buildings roadside racing; do
  $SLOT "$BL" -b --factory-startup --python-exit-code 1 -P tools/blender/gen_$fam.py -- --out out/part --only "$ONLY" \
    > "logs/part_gen_$fam.log" 2>&1 || { tail -30 "logs/part_gen_$fam.log"; exit 3; }
  grep -E '^(EXPORT|DONE)' "logs/part_gen_$fam.log"
done
python3 tools/blender/validate.py out/part > logs/part_validate.log 2>&1; vrc=$?
cat logs/part_validate.log
$SLOT "$BL" -b --factory-startup --python-exit-code 1 -P tools/blender/qa_render.py -- out/part out/part/qa_views \
  --views "$ONLY,${CONTROL:-BLD_GF_CommercialBay}" --only-views > logs/part_qa.log 2>&1 || tail -30 logs/part_qa.log
grep -c '^RENDER' logs/part_qa.log
python3 tools/blender/qa_compose.py out/part/qa_views
exit $vrc
