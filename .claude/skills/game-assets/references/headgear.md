# Headgear (cap = RO head_top, head_mid, head_low)

## Spec
- cap ≤ 500 tris, 512–1024 px, skinned 100 % to `head`; head_mid (glasses, masks, ears) ≤ 400; head_low (mouth) ≤ 200.
- Closed caps cover the crown: the lab marks them (`coversHair`) and stores the brim plane + radius profile; the shader
  hides hair inside the hat (no pre-cut hair). Open bands/circlets keep the full hair.
- Tall hats may reach 1.80 m (RO has tall hats); everything else stays inside the slot envelope (gate).

## Concept → 3D
Concept rules in openai-images.md (OPEN/CLOSED, eye level, front, symmetric). Meshy with `--faces 480`.

## Fit modes (`--fit`)
| Mode | For | What it does |
|---|---|---|
| `crown` | closed cap that hugs the skull (beret, ranger cap, helmet) | depth from the crown, top just over the hair, **top measured on the shell's middle** (a feather or wing sticking up at the side used to push the cap onto the face), pushed out of head + hair twice |
| `tall` | closed hat that rises (lomphok, wizard hat, pillbox, top hat) | brim plane levelled (lowest point per direction), 8° back-down tilt, width from the skull at 1.37 ×1.9, height × `--hscale` (pillbox 0.6, tall 1.0) |
| `band` | open band / circlet / bandana | **wrapped round the hair per direction** (band ring → hair radius + 6 mm, ornaments keep their offset; hair radius median-filtered so a ponytail doesn't balloon it) |
| `ontop` | ears on a headband | sits on the hair, base sunk 2 cm |
| `glasses` | glasses, eye masks (head_mid) | face width at eye height, in front of the face (`--wscale 0.8` round specs) |
| `ears` | elf ears (head_mid) | on the skull sides |
| `mask` / `mouth` | head_low | over mouth + nose / held in the mouth |
| `hood` | hoods worn round the head (cat hood, wolf pelt, ranger / bandit hood) | width from the hood's skull part (1.22 × hair width at the brow), top over the hair, centred on the skull front-to-back, pushed out twice; closed cap (hair clipped). **Hood concepts always use this, never `ontop`** (owner A103: ontop perched it on the hair, face tipped up) |
| `facade` | flat relief from image-to-3D (front-only concept: depth < 0.5 × width); crown/band switch to it by themselves (`--no-facade` to stop) | width = hair at the brow, ≤ 7 cm deep, back on the front of the hair, sides bent round the head, lower edge over the brows (A103) |
Options: `--sink` (ontop: how far the base goes into the hair, default 0.07; bunny ears on a bow needed 0.13), `--wscale` also for `mouth`.
Every crown and band fit ends with a **brow lift**: the front quarter's lower edge (10th percentile, so a knot tail
hanging down doesn't count) may not be below the brows (1.30); bands are lifted first, then wrapped at their own height.
Hoods and wide bandanas used to cover the eyes.
Pick by shape, not by name: a round flat-topped cap that rose like a dome was too big in `crown` and right in `tall --hscale 0.6`; tall headdresses
and tall velvet hats need `--hscale 1.3–1.4` (1.0 came out squat). The preview frame cuts very tall hats at the top.

## Batch from the item plan (A103)
`tools/items/headgear3d.py [--costume] [--only ids] [--meshy-only|--fit-only] [--refit]`: concept crop → 3D → OBJ → ingest m + f with
the item's mode from `MODE` → item_gate. Gate fails seen: band/crown ballooning a flat relief (→ facade), tall hats with a
wide back piece past the envelope (→ `--hscale 1.15 --wscale 0.82`), big masks past the head_mid band (→ `--wscale 0.75–0.85`),
low round hats (cupcake, pudding, cat hood) hiding the bangs in `tall` and covering the face in `crown` (→ `ontop --sink 0.10–0.15`).
Open fits (ontop / band / facade, and flat reliefs) write `<cap>.json` `{"open": true}`; build_lab then keeps the full hair
(its crown test called wide hats on the hair closed and the shader cut the bangs: a bald band on the forehead). Worn check in Labs: `cd studio && node scripts/check-worn.mjs '<json>' <dir>`
(`GENDERS=หญิง` for one gender; about 45 s per item per gender on SwiftShader, so split long lists).

## Check worn (always)
Sheet of `_front.png` + `_side.png` for m and f, read it: on the head (not the face), level, not floating wider than the
head, no skin showing through the shell, ornaments where the concept has them. The previews don't apply the hair clip
(hair poking through a closed cap there is fine; it is hidden in the game). Then look in the preview tool on both genders.
