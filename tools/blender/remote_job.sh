#!/usr/bin/env bash
# Runs ON the GPU box (called by run_remote.sh / run_remote.ps1). Works only under /root/robloxrace/vis.
# Every Blender call goes through the fleet slot manager (never pkill; a job is stopped by the PID in its assign.log).
set -u
VIS=/root/robloxrace/vis
BL=${BLENDER:-/root/w/blender/blender}
SLOT="bash /root/kit/fleet/gslot.sh --"
cd "$VIS" || exit 2
rm -rf out/run && mkdir -p out/run logs
: > logs/timings.txt
step() {   # step <name> <cmd...>
  local name=$1; shift
  local t0; t0=$(date +%s.%N)
  "$@" > "logs/$name.log" 2>&1
  local rc=$?
  local t1; t1=$(date +%s.%N)
  printf '%-16s rc=%d  %.1f s\n' "$name" "$rc" "$(echo "$t1 - $t0" | bc)" | tee -a logs/timings.txt
  return $rc
}
for fam in buildings roadside racing; do
  step "gen_$fam" $SLOT "$BL" -b --factory-startup --python-exit-code 1 -P tools/blender/gen_$fam.py -- --out out/run || { tail -30 "logs/gen_$fam.log"; exit 3; }
  grep -E '^(EXPORT|DONE)' "logs/gen_$fam.log" | tail -1
done
step validate python3 tools/blender/validate.py out/run; vrc=$?
tail -1 logs/validate.log
step qa_render $SLOT "$BL" -b --factory-startup --python-exit-code 1 -P tools/blender/qa_render.py -- out/run out/run/qa || tail -30 logs/qa_render.log
grep -c '^RENDER' logs/qa_render.log
step shrink_qa python3 tools/blender/shrink_qa.py out/run/qa out/run/qa_small
"$BL" --version | head -1 > logs/blender_version.txt
exit $vrc
