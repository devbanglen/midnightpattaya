# Legacy (folded into game-assets on 2026-10-17, kept for the details it still has)

---

# New outfit = new design file + one command (A032)

Method and spec: `docs/game/OUTFIT_METHOD.md`. Headgear and rigid props use skill `item3d` instead.

## 1. Write the design (the only creative step)
Copy `tools/ayolab/outfits/sw1s.json` to `tools/ayolab/outfits/<set>.json` (set = short new id, e.g. `ac1`, `mg2`):
- `template`: a key of `tools/ayolab/outfits/templates.json` (the shape: which pieces exist, e.g. `swordsman_t2` =
  capelet + chest plate + sleeves + bracers / trousers or skirt + apron + hip plates + shin wraps). Read its `pieces`.
- `roles`: one `[colour, material text]` per role the template uses (`collar`, `metal`, `trim`, `cloth`, `trousers`,
  `apron`, `leather`, `plates`, `line`). Colour = the main tone; shades come from the template. Text = what that
  piece is made of in this design (cloth, steel, leather, fur, embroidery…), never a new piece the mesh doesn't have.
- `roles` for gloves/boots/cape: `gloves`, `gloves_trim`, `boots`, `boots_trim`, `cape`, `cape_trim` (slots `hands`,
  `feet`, `cape`). Capes skip the fit gate (nothing to cover); flare them with `"axes": "x"`.
- `shape` (our silhouette, A033): ops per `<slot>` or `<slot>_<g>`, applied by `tools/ayolab/shape.py` to the template
  pieces (list them: `python3 tools/ayolab/shape.py <template part> --list`):
  `{"role": "collar", "stretch": 1.3}` longer downward · `{"role": "trousers", "flare": 1.15}` wider towards the hem ·
  `{"role": "cloth", "inflate": 0.014, "absx": 0.22}` volume: pushes the piece out (here only the sleeves, |x| ≥ 0.22) so layers stand off ·
  `{"role": "apron", "scale": [1.15, 1, 1]}` · `{"role": "plates", "remove": true}`. Keep changes within ±35 % and
  let the fit gate judge. Spikes (wrist frills, zigzag shin/wrist seams) are removed for every outfit automatically.
- `notes`: what to do with odd shapes (studs, fringes).
- Palette rules (spec §3): 5–7 colours, readable at 150 px, trim hue differs from the cloth next to it, no grime.
- If the owner gives a concept image or words, translate them into roles; ask only if the colour scheme is unclear.

## 2. Run
```sh
tools/ayolab/outfit.sh tools/ayolab/outfits/<set>.json            # all slots x genders in the file
tools/ayolab/outfit.sh tools/ayolab/outfits/<set>.json --step bake,lab --genders f   # partial rerun
tools/ayolab/outfit.sh tools/ayolab/outfits/<set>.json --step fit --fit full     # before release: all 10 clips
```
Steps: shape (our silhouette + no spikes → `art/items3d/shape/`) → spec (Blender, the piece layout in the design
colours, exact front/back frame; gloves/boots frame ONE piece and the bake mirrors it to the other) → concept (GPT,
2 calls per slot and gender: front, then back with the front as ref; female also gets the male front as ref) →
bake (register onto the spec, IoU gate ≥ 0.85, project into the shaped part's UVs) → fit (fit_check on foot and
riding, 3 Blender runs at once; `--fit quick` = walk/pickup/sword_atk3 while designing, `--fit full` = all 10 clips
before release) → item_gate → build_lab → sheet `art/items3d/qa/<set>_<g>.png`. A full set (5 slots × m + f) = 20 GPT
calls, no GPU; the fit runs foot + riding in one Blender launch and caches passing results by shape, so a whole
set checks in ~1 min. Templates in the catalogue: `swordsman_t2`, `archer_t2` (bare-skin areas use the `skin` role;
a design may override `skin` to cover them). Existing concept images are reused: delete `art/concepts/items3d/<set>_<slot>_<g>*.png`
to redraw one. The Blender launches retry on their own.

## 3. Check and report
- Items are worn one by one in the game: `python3 tools/ayolab/mix_check.py <set>` wears each piece with other sets'
  pieces (default swordsman_t3, archer_t2, novice_t1) and runs the fit gate on foot (quick + 3 at once by default; `--fit full` before release).
- Look at the sheets (front + back) and at the concept vs spec; IoU `WARN` = GPT moved the garment: delete and rerun.
- The fit step prints PASS/FAIL per part and pose; a FAIL after a shape op = soften that op (smaller stretch/flare).
- Labs: `#/labs/ayo3d`, slot dropdowns → the new set. Studio stays green (`npm run validate`).
- Log a decision only for a new rule; report to the owner in Thai: sheet paths, IoU, GPT calls used.

## New template shape
`python3 tools/ayolab/outfit.py --clusters <slot>_<class>_<g>_<tier>` → 7 colour clusters; render an id map with
`bl_spec_sheet.py --map "#c1=#ff0000,..."`, name each cluster's role per gender in `templates.json` (+ `pieces`).
Shipping still needs an owner decision row per set (A021): shape ops make the silhouette ours, the mesh topology
is still the template's.
