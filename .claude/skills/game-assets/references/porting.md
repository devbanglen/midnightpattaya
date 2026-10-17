# Using this skill in another project

1. Copy the folder `.claude/skills/game-assets/` into the new project.
2. Copy the tools it calls (they live in the project, not in the skill) — `scripts/export_tools.sh <new project>` copies:
   `tools/pipeline/gen_concepts.py`, `tools/ayolab/{api3d.py,meshy_obj.sh,bl_glb2obj.py,bl_decimate.py,bl_ingest.py,
   ingest.sh,weapon_fit.py,item_gate.py,decimate_skinned.py,bone_fix.py,idmap.py,outfit.py,outfit.sh,shape.py,
   bl_spec_sheet.py,bake_views.py,fit_check.sh,bl_fit.py,build_lab.py,hy_hair.py}`, `studio/src/char3d/glow.ts`.
3. Rewrite `references/project.md` for the new project: paths, rig, slots and budgets, palette, classes, decisions.
   The general files (SKILL.md and the other references) should not need project facts; if they do, move them out.
4. Things that are rig-specific and need a look in a new project: the slot bands/heights in the headgear fit modes
   (eye 1.214, crown 1.37…), the seam heights, the template weapon frame, `ALLOWED` bones per slot in the gate.
5. Keys: each project has its own `.env` (OPENAI_API_KEY, MESHY_API_KEY); never copy a key into the skill.
