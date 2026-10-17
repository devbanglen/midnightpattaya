# Hunyuan3D on our GPU box (simple props) + colour clean-up

Hunyuan is the first tool for every rigid prop; Meshy only for the pieces it fails (SKILL.md "3D tool per category").
Test (ayothaya A097): 6 items, Hunyuan ≈ Meshy on simple shapes, ~1 min and ~$0.01 a piece vs 30 credits.

## Box rules
- Work only in the project's own folder on the box; never touch, modify or kill another agent's files/processes; no
  `pkill -f`. Copy shared tools (Blender, venv, weights) read-only into our folder.
- Share the GPU and CPU through the box's slot/lock convention (Blender = one process per lock; Hunyuan = the shared
  Hunyuan slot). VRAM: ~28 GB per Hunyuan process with texture.
- No API keys on the box. Concepts stay on the dev machine; send only images/meshes; pull results back (dev = master).

## Making a piece
- Set the face count (`--faces` = slot budget) **before** texturing: decimating a 20k textured mesh to a few hundred tris shreds it.
- Fit with the same fit modes as any prop (headgear.md, weapons.md).

## Known Hunyuan faults and the fix (apply in this order, deterministic, strengths as parameters)
| Fault | Fix |
|---|---|
| Colours dull / darker than the concept | match the texture to the concept crop's opaque pixels (Lab mean/std or per-channel histogram), clamp highlights, leave unused UV space alone |
| Uneven, blotchy colour; specks, dots, noise | edge-preserving smoothing in UV space with island padding (bilateral / mean-shift; small median for specks) |
| Regions not flat like our cel style | snap texels to a 6–10 colour palette k-means'd from the concept, keep 2–3 tone steps per colour, keep line art (skip strong edges or add a light edge map back) |
| White / uncovered patches | dilate neighbouring island colour or inpaint |
| Flat faces (shields) off from the concept; shields too thin | project the concept onto the front face (front-view projection like the outfit bake), cleaned Hunyuan texture for sides/back; scale depth up ~1.6–2× in the fit if gates allow |
| Texture 512 px | the paint step halves its bake on save: ask for `--tex-size 2048` to get 1024 |
| Glasses lenses come out solid white (cover the eyes) | not fixable in the texture: glasses with clear lenses go to Meshy or get the lens faces removed |

Check every piece worn (front + side, both genders) after the clean-up; retakes go to Meshy.
Project paths, scripts and the chosen defaults: [project.md](project.md).

## What we use (ayothaya A099, A100, A104)
- Box run: `/root/ayothaya/hy/run_b.sh` → `gpu/batch.py in_b out_b --texture --steps 30 --octree 256 --tex-size 2048
  --render-size 1024 --no-upright` through `gslot.sh --hy`; `in_b/faces.json` = per-item face budget (cap 480, head_mid
  380, head_low 190, shield 570). ~60–80 s a piece next to another agent's two Hunyuan processes.
- Clean-up `tools/items/hy_texfix.py <tex.obj> <concept.png> <out.jpg> [--front]`, defaults picked on the 6 test items:
  `--color region --match 0.8` (lightness mean/std globally, then per concept palette colour: its texels take that
  colour's mean + spread, so area differences between atlas and concept don't tint the whole piece), median 3 +
  bilateral (`--clean 1`), palette snap `--k 8 --snap 0.5 --tones 3 --tone-step 7` with edges kept, white-blob inpaint,
  `--front` (shields) projects the concept onto the viewer-facing faces (best of 2 sides × mirror by correlation), gutter
  padding. Rejected: a global Lab mean/std match (`--color global --ab-shift 1`) tinted a steel dome gold and washed the
  wool cap out; `--snap 0.85 --tone-step 9` made the fez blotchy; `--trim` (force the global mean back) undoes the region match.
- Judge colour in a flat render (`tools/items/bl_flat_render.py`, texture only like the unlit Labs shader): the lit
  ingest previews look darker than the game. Before/after sheet: `look/qa/hy_color_fix.png`.
- Fit + gate: `tools/items/hy_batch.py --pull [-j 3]` (fit modes per item in its `FIT` table; shields: thickness ×1.8 by
  `bl_hytest_shield.py`, then `weapon_fit.py <glb> shield <tier>p<k> --length 0.75|1.0|1.35`). Results
  `art/items3d/hytest/batch/results.json`.
- Wide brims / cones / mortarboards read as flat reliefs (depth < 0.5 × width) and `bl_ingest.py` switches to the
  facade fit (2 m wide, gate FAIL): pass `--no-facade` (`tall --hscale 0.6 --no-facade`, or `crown --no-facade --wscale
  0.85`). Other gate fixes that worked: a wreath as `band --wscale 0.85`; wide glasses `--wscale 0.52–0.6`; a wide
  moustache `mouth --wscale 0.6`. The full table is `FIT` in `hy_batch.py`.
- Clear lenses (A099): `tools/items/hy_lens.py <in _tex.obj> <concept.png> <out.obj> --tex <fixed.jpg>` before the fit
  (hy_batch.py `LENS`). The lens mask comes from the concept (light, grey areas enclosed by the frame). A face is removed
  when it touches the mask and its own texture is glass-like (L > 70, chroma < 16), or when 3 of 4 sample points are in
  the mask. The Labs shader is opaque, so removing the faces is the clean way. Check the eyes in Labs.
- Shield facing rule (A104): keep `weapon_fit.py shield`'s facing as it comes out and never flip a shield after it.
  The fitted GLB must lie in +Y: the back rests on the forearm at y = 0, the face points out, and max y > 0
  (hy_batch.py prints `FACE y a..b ok`). If all the geometry is at y <= 0, something flipped it and it sits inside the
  forearm, hidden. Judge the face only worn in Labs (check-worn.mjs with a sword + the shield, m + f, front + side), not in
  flat renders. A render-correlation flip script (removed) read the views the wrong way round and put 8 of 12 shields
  into the arm.
- Retry (A099/A100): one more Hunyuan run with `--steps 50 --octree 384 --seed 777` (`run_r.sh`, `hy_batch.py --set r`
  writes to `batch/r/` so both takes can be compared side by side in flat renders before copying the better one into
  `own/`). In the A104 batch, 19 of 88 were retried: 15 came out better, 1 kept its first take, and 3 still failed and
  went to Meshy (30 credits each): a turban that broke into shards, a shako with scrambled colours, and a moustache with
  baked blue patches. Hunyuan is weakest on wrapped cloth, tall glossy cylinders and dark hair-like fur.
