# Weapons

## Spec
- Rigid mesh on its mount bone (right hand; bow: left hand), ≤ 800 tris, one texture, unlit. The lab build re-encodes
  opaque PNG textures as JPEG (~500 KB → ~190 KB per weapon); the preview keeps the old weapon in hand until the new one
  has loaded, ignores late loads and preloads an opened arsenal row (the tunnel takes ~6 s per file, whatever its size).
- One frame for every template weapon: long axis +Y, grip at the origin, flat side on Z. weapon_fit puts ours in the
  same frame so every attack clip holds it the same way. File `<type>_<set>`; the type has no `_`.
- Template extents (y): sword −0.16..0.77 (guard 0.13), greatsword −0.21..1.25, dagger −0.14..0.58, axe −0.15..0.47
  (blade +X), greataxe −0.16..0.59, mace −0.15..0.51, rod −0.34..0.67, bow −0.36..0.36 (limbs +X).

## Fit families (weapon_fit)
| Family | Types | Placement |
|---|---|---|
| blade | sword, greatsword, dagger | guard (widest slice near one end) at the template's guard height, blade length × `--length` |
| head | rod, mace, axe, greataxe | widest end up, **handle straightened** (PCA leans toward a heavy head), total length matched, grip at the template's ratio, axe blade to the side that reaches further (+X) |
| bow | bow | centred on the grip, length matched, limbs to the template's side |
| gun / fist / puppet | pistol, rifle / knuckle, book / puppet | A087 fist frame (+Y grip line, +X along the fingers): gun barrel +X, grip down at the origin; knuckle box-fitted to the fist x 0..0.06, y ±0.05, z ±0.03 with the spikes +X (side = the outer edge broken by gaps; wrong picks → `FLIP_X` in weapons3d.py / `--flip-x`), book cover +X; puppet control bar in the hand, doll below; overall size `LEN` (A089) |
| shield | shield | clips' frame (A096): origin = grip at the back centre, +Y face, -X top, Z width; height 0.40 × `--length` (buckler 0.75, tower 1.35), bone `shield` (A103) |
| head (pole) | spear, halberd, lance, staff | no template mesh: `SPAN` in weapon_fit gives the y extents (grip about a third up from the butt; lance near the butt), blade / hook to +X; mounted on the greatsword bone (A086) |
Render the fitted weapons with texture next to the template (Blender workbench) and look: blade side, straight handle, scale.

## Glow (rods, gems, magic weapons)
`--glow '#5fd0ff'` writes the orb (centre, radius, colour) next to the weapon. The orb is found as the best sphere among
the top vertices (RANSAC, radius 2–8 cm, near the shaft axis); colour matching failed (gold trim and blue shafts match too).
Check the circle on `<weapon>_front.png`; `--glow-at x,y,z,r` sets it by hand when it caught a cup or ring instead. `--orb` adds our own crystal sphere (radial gradient strip under
the atlas) when image-to-3D lost the orb. The client draws a breathing halo, a four-point star flash every ~1.7 s and 5
sparkles circling (3 draws). Owner approved it on the mage rods (A066).

## RO-style progression (the plan for the class arsenals)
RO weapon levels map to our tiers; every class gets its default weapon type at every tier, more variety at the top:
| Tier | Levels | Look | Per class |
|---|---|---|---|
| t1 | 1–20 | plain, honest materials (wood, iron, cloth wraps), small | 1 |
| t2 | 20–50 | steel, brass, simple engraving, a small gem | 1–2 |
| t3 | 50–80 | silver/gold trim, carved motifs, gems, stronger silhouette | 2 |
| t4 | 80–99 | signature pieces: several lines per class (holy, dark, fire/ice/wind/earth element, dragon, royal Ayutthaya, MVP-drop style), glow where magic | 4–6 |
Second weapon types per class follow RO (swordsman: greatsword; thief: dagger + later katar; acolyte: rod too; merchant:
greataxe; archer: bow only; mage: rod; novice: dagger + sword). Name every weapon (th + en) in the weapon catalogue (project.md). First arsenal: 56 weapons, 8 per class (A069).

## Batch from the item plan (A086)
`tools/items/weapons3d.py [--types spear,staff] [--only ids] [--max N] [-j 6]`: planned normal weapons in order (spear,
staff, then by tier) → concept crop flattened on white → Meshy (`--faces 760`, ~30 credits) → weapon_fit → a row in
`lab_weapons.json` with `plan: <plan id>` (lab id `<type>_<tier>p<k>`, Labs arsenal row = the old class of the line).
Resumable; `--meshy-only` buys meshes while another agent tunes the fit, `--fit-only` / `--refit` fit later. Then `build_lab.py`, `plan_items.py` (the plan keeps the plan id and marks it done). QA: `bl_weapon_sheet.py`
(front + side, grip bar at y = 0; small types `--lo -0.3 --hi 0.3 --gap 0.5`) and a Labs screenshot per type. Meshy balance: `GET /openapi/v1/balance`; plan the
batch to the credits left (a 402 mid-batch only costs a rerun).

## Grip check in Labs (A086, 2026-10-17)
- `cd studio && G=m,f node scripts/shot-grip.mjs` shoots every plan weapon (front `stand` + side attack frozen with ■ หยุด, dummy hidden, camera via `window.__ayolab.controls`), ~50 s per weapon per gender in swiftshader; skips shots that exist. Gender switch remounts the canvas: wait ≥ 7 s after it.
- 26 pole/axe weapons (spear, staff SPAN grip about a third up) sit in the hand on m and f in attacks; scale ≈ 1.5× body height reads fine. No refit needed.
- Known (Labs wiring, not fit): the `stand` button plays the class's universe stand (sword pose), so spears/staffs point head-down at rest; the pole types need the RPG pack's idle clip as their stand.

Costume weapons (A103): `weapons3d.py --costume` → lab id `<type>_cw<k>`, rows `costume: true` (Labs shows them as ✦ costume in the class's arsenal row).
