# Outfits: template mesh + our silhouette + baked GPT paint (no GPU)

An outfit set = body, hands, legs, feet, cape for both genders (10 pieces), plus its hat (headgear.md) and weapon
(weapons.md). One command runs everything once the design file exists.

## Steps (the outfit script)
shape (our silhouette ops + spikes removed) → spec (Blender: the template's piece layout in OUR role colours, exact
front/back frame) → concept (GPT: front, then back with the front as ref; female also gets the male front) → bake
(register each image onto its spec, IoU ≥ 0.85, project into the piece's UVs) → **decimate if over the slot budget,
fold disallowed bones to their parent** → fit (on foot + riding; quick = 3 clips while designing, full = 10 before
release) → item gate → lab build → front/back sheet per gender. 20 GPT calls per set. Partial reruns:
`--step bake,fit --slots feet --genders f`. Existing concept images are reused (delete one to redraw).

## 1. Template (once per class/tier)
- The template = the class's own outfit mesh (its silhouette: robe, vest, skirt…). Pick the tier closest to the idea.
- New template: `idmap.py <class>_<tier>` → 7 colour clusters per piece, an id-colour render per slot/gender
  (`*_key.png`, legend = cluster hex + share) and a skeleton entry. Name every cluster with a role by looking at the
  renders (collar, cloth, robe, vest, metal, trim, line, trousers, apron, leather, plates, sash, skin, gloves(_trim),
  boots(_trim), cape(_trim)…; light/dark of one region = same role with shade factors 0.8 / 1.15). Pale peach clusters
  are bare skin: role `skin`. Copy the `despike` block per slot from a working template.
  Parallel agents can each name one template (they write `<template>.named.json`; one writer merges into templates.json).
- Odd templates to note in the design: bare midriff / arms / thighs (cover them with a `skin` override if the theme
  wants), open fronts, capes that are really scarves.

## 2. Design file (the creative step)
- `template`, `slots`, `genders`, `style_ref`, `roles` = `[hex, material text]` for every role the template uses,
  `notes`, `shape` ops. Palette: 5–7 colours, readable at 150 px, trim hue differs from the cloth next to it, no grime.
- Material text says what the piece is made of in this design, never a new piece the mesh doesn't have.
- `skin` override: `["#hex", "covered: a thin <colour> under-layer (no bare skin)"]`.
- Shape ops (keep within ±15 %; the fit gate judges): `stretch` (longer down), `flare` (wider to the hem), `inflate` +
  `absx` / `y` (volume in a region), `scale` [x,y,z], `remove`, per `<slot>` or `<slot>_<g>`. Capes: `"axes": "x"`.

## Lessons (each became a rule)
- Boots that fail cover after despike: `"ring_to": "highest"` on the feet despike (boot tops reach the old spike tips).
- Boots that sink into the mount when riding: don't scale boots up (keep ≤ 1.02).
- Trousers failing in crouches (pickup, lunges: crotch / inner thigh misses): `{"role": "trousers", "inflate": 0.014, "y": [0.3, 0.72]}`, no flare.
- Low shoes failing at the shin seam (cover 0.946 / seam 0.911, misses at y 0.17–0.22 on calf): raise the top with `{"role": ["boots", "boots_trim"], "top_to": 0.26, "from": 0.08, "hi": 0.162}` (+ `scale` 1.04 xz); `hi` = the boot top so trim pieces follow the same stretch. Taller boots sink a bit more into the mount when riding (far leg inside the Peco, +0.03 over the template): note it, not a blocker.
- Back views of single gloves/boots: GPT copies the front; the prompt now says keep Image 1's outline, no front decoration.
- IoU WARN = GPT moved the garment: delete that concept image and rerun the slot.
- Over-budget template pieces (mage f legs 1,170 > 1,000) are decimated with the rig kept; never raise a slot budget.
- Fit results are cached by the worn piece's geometry + weights: same shape in another set is not checked twice.
- **Half-built sets in Labs (A098):** `build_lab.py` indexes whatever GLBs exist, so a set built while another run was still
  baking showed body/legs but no boots (bare stumps "sunk into the floor"). Run the `lab` step only after `bake` + `fit`
  of every slot; the Labs job row enables a set only when every piece is in the index.
- **Partial lab step = partial sheet:** `--step lab --slots feet` renders a sheet of the boots only; rerun `--step lab`
  for the whole gender after a slot retake.
- **Boot bones with no allowed ancestor (A098):** mage_t4 boots carry `skirt_*` / `pelvis` weights; `bone_fix.py` now sends
  such weights to the nearest allowed joint per vertex (it used to leave them and the item gate failed).
- **Job outfits (A098):** `tools/ayolab/job_designs.py` writes `outfits/jb<class>.json` from per-class colours + materials,
  roles taken from the template, shape ops copied from a passing design on the same template; style_ref = the class
  concept `art/concepts/classes/class_<class>_m.png`. Run sets in ≤3 parallel lanes (`--step shape,spec,concept,bake,fit
  --jobs 2`), then the lab step one set at a time (single build_lab writer). ~20 GPT calls and ~1–1.5 h per set on a busy box.
- Novice_t0 male boots (`top_to` low-shoe fix): riding sink +0.148 vs template +0.120 = the known no2/no4 case, not a
  blocker. Shrinking them to 1.02 made it worse (foot cover 0.968 FAIL, sink +0.168): keep the no2 ops.
- **GPU box route (A098):** `AYOTHAYA_LINUX=1 AYOTHAYA_BLENDER=<flock wrapper> AYOTHAYA_TMP=<own dir>` runs shape, spec,
  bake and fit on Linux Blender (one process per `/root/kit/bl<N>.lock`); the concept step (GPT, keys) stays local. Order
  per set: box `--step shape,spec` → pull specs → local `--step concept` → push concepts → box `--step bake,fit` → pull
  own/golden + merge `fit_cache.json` → local `--step lab`. Measured: a whole set ≈ 20 min (GPT bound) vs 1–1.5 h on the
  busy WSL box; shape+spec 30 s vs ~20 min; bake+fit of a set ≈ 2 min; full 10-clip fit of 22 sets 7 min.
- **White garments (A098):** the registration mask used only "ink" pixels, so white cloth inside the outline was dropped
  (paladin / saint / cleric IoU 0.55–0.85, poor alignment). `bake_views.mask` now fills everything not reachable from the
  border through near-white; white sets rose to 0.92–0.99 with the same concepts.
- `decimate_skinned.py` needs its temp dir (`/tmp/ayo` was deleted in a disk clean-up → over-budget pieces silently kept
  their tris and failed the item gate); it now creates it (`AYOTHAYA_TMP`).
- acolyte_t2 male robe fails the full fit in `pickup` (cover 0.92) even on the costume pr1: template-inherent, not fixed
  by inflating the robe.
