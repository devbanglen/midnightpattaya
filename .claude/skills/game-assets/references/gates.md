# Gates and budgets: when a piece is done

1. **Static gate** (`item_gate.py <slot> <glb>`): joint names from our rig only, only the bones the slot allows, triangle
   + texture budget, bind-pose box inside the slot envelope, head items inside their band.
2. **Fit gate** (worn pieces body/hands/legs/feet; capes skip it): the piece on the bare body over the clips, cover and
   seam ≥ 0.95, on foot and riding; riding sink ≤ the bare body + 0.05 or ≤ the untouched template + 0.02.
   `fit.json` → `miss` lists uncovered proxy points (position, bone): group them by bone/height to see why
   (calf at 0.15 = the ankle seam; pelvis/thigh at 0.3–0.5 in pickup = crotch in crouches).
3. **Looked at worn** (front + side, both genders) — see SKILL.md step 6.
4. Studio stays green (typecheck, tests, set validation).

## Budgets (tris; whole character ≤ 8,000)
head 900 · hair 2,000 · cap 500 · head_mid 400 · head_low 200 · body 1,500 · hands 800 · legs 1,000 · feet 400 ·
back 500 · weapon 800 · shield 600. Over budget: decimate with the rig kept (never raise a budget without an owner decision).

## Known gate traps
- Cached fit results must key on the worn piece itself (geometry + weights), not on its source shape.
- Windows Blender launched from WSL drops a launch now and then: wrappers retry 3×.
