<!-- copied from ~/.claude/skills/sprite-pipeline/references/common (ced2f55) on 2026-10-17; ayothaya owns this copy now -->
# Concept art (GPT image → 3D input)

Routes: all. The 3D-input rules (white background, A-pose gaps, front vs back views) apply where the concept feeds image-to-3D (3d-sprite, 3d-realtime, redesign); style lock, logging, retakes, refusals, icon grids and cards apply to every route including 2d. Origin: aroa unless tagged otherwise.

A concept here is **input for image-to-3D and auto-rigging**, not a painting. Every rule below exists because the mesh step failed without it.

## Rules for any 3D-input concept
- **Plain pure white background, even frontal light, no cast shadow, no ground plane, no text.** Prep flood-fills the white connected to the border into hard alpha. Soft alpha (rembg) makes Hunyuan build a relief plate instead of a solid. (aroa)
- **Exactly one subject, whole and centred with margin.** Cropped parts get invented. (aroa)
- **Big simple shapes, few small details, matte, no glow.** Fine inlays vanish in the mesh; glow areas come back off-hue; transparent glass and translucent wings come back opaque, so ask for opaque toon wings. (aroa)
- **Pose for the rig:** characters in a strict front, symmetric A-pose with a clear gap between arms and torso and between the legs, nothing in the hands, nothing hanging into the arm gap (long hair goes straight down the back or is tied up). Creatures in the pose their archetype rig expects (see prompts). (aroa)
- **Front views are trusted, backs are guessed** by the mesh step; when the back matters (ponytails, wings, capes) ask for a three-quarter (back) view. (aroa)

## Style lock
1. Write one shared STYLE/VIEW block per kind in a sidecar (`<items>.json.style.json` → appended to every prompt of that kind), so the style cannot drift per prompt. (aroa)
2. Generate golden concepts (one character, one weapon, one monster) and get user approval. The real approval is the **rendered** sprite in the studio, not the concept. (aroa)
3. Later concepts of the same family go through the image-edit endpoint with the approved golden as reference: *"Use the reference image ONLY for the pose, the chibi body proportions, the head size, the camera, the framing and the rendering style. Redesign the character and outfit completely."* (aroa)
4. Variants of an existing image (cropped hair, new face, outfit on the base body) use *"Redraw EXACTLY the same … Change ONLY the …"*. (aroa)

Prompt blocks per kind (character, female look, cropped-hair base, idol bust, hair on mannequin, monster per archetype, weapon/shield/headgear/garment/back, icon grid, card art, outfit, aura, map prop): [concept-art-prompts.md](concept-art-prompts.md).

## Reference images
- Default: only your own generated images or your own renders go into the generator. (aroa)
- Third-party images as references only when the user explicitly decides it per asset class; log the decision. (aroa A029: the reference game's item images allowed as refs for items, never for monsters.) Wording that works: keep type, silhouette, proportions and how it is worn; *"ignore the low-resolution blur and pixels, any faint glow, sparkle or motion trail and any drop shadow, and do not copy its tilted angle"*; then apply **our** design note.
- Originality check per item: change at least 2 of 3: silhouette, main palette, signature motif. Keep reference-vs-ours comparison sheets internal. (aroa)
- Never put a real person's name in a prompt; describe the look (aroa A040: "Korean-drama / idol-like youthful look, original face").

## Running and logging
- Generate before renting GPUs: the account rate limit, not hardware, bounds this step (aroa: 8 images per ~90 s at `-j 3`).
- **Log every call, success or error**, one JSON line in a shared `log.jsonl`: time, id, kind, endpoint, model, quality, size, ref files, output file, status, usage, prompt, `by` (agent). Line count = calls made. Keep a human note per agent run in `budget.txt`. Network errors are logged too: they may have been billed. (aroa)
- The generator skips ids whose file exists: **retake = move the old file to `_rejected/` and rerun**. (aroa)
- Keys: strip `\r`, scrub `sk-…` from error text, never send a key to a box: [secrets.md](secrets.md). (aroa)
- Sizes that worked (aroa): characters/outfits/cards 1024×1536 high; monsters 1024×1024 high (bipeds 1024×1536); items 1024×1024 medium; grids 1536×1024.

## Safety refusals
Occasional false positives (aroa: 7 of 112 monster calls, e.g. a "wide toothy grin" turnip). Retry once as-is; most pass. If it refuses again, soften the trigger words (teeth, blood, skulls, weapons pointing at the viewer) without changing the design. Refusals are logged like any error.

## Icon-only items: grids
Armour, shoes, accessories, consumables and materials need no mesh. Put 4–6 items in one 1536×1024 call ("separate items … lots of empty white space between them, none touching, no grid lines, no labels"), split by the white gaps, cut each to an icon. Cuts calls ~5×.

## Cards
Ask for full-bleed art only ("no frame, no border, no text"); draw frame and name in code so it stays deterministic and localisable. For monsters, rendering the card from the finished 3D model beats GPT art: same creature, zero calls (sprite-pipeline route doc, not copied).

## Approval sheets
- Contact sheet per category (concept + id + name), plus internal reference-vs-ours sheets when refs were used. (aroa)
- Retake common failures: wrong proportions, items in the arm gap, hair rule broken, shape note ignored (keep shape notes short and prominent: GPT drew an oval when asked for a heater shield). (aroa)

## Outfit option boards (4 options × both genders)
- One sheet per option = boy front, boy back, girl front, girl back, so the pair always matches; 2 candidates per option and pick per option: about half the sheets add props you excluded (a quiver on the wrong option) or loose bits (hanging sash tails, tassels). (aroa, 48 calls over 6 classes)
- Long cloaks: allow them per option with a dedicated block (one solid cloak, smooth hem, no strips/tails, big back silhouette) instead of loosening the class-wide "no long cloth" rule.
- Game-size row: mask the background as near-white pixels connected to the crop border; a brightness threshold turns white/cream cloth transparent. (aroa)

## Done when
Every catalog row in scope has a concept file and a log line, rejected files are in `_rejected/`, a contact sheet exists, and the golden/style approval is recorded in the decision log.

## Port to a new project
Kit: `~/projects/templates/sprite-kit` (v1; `kit/init_project.sh` copies all of it and already renamed `aroa`/`AROA_*`, `/root/aroa`, `vast-3d`; see [kit.md](kit.md) and the project's `docs/PORTING.md`). Files: `tools/pipeline/gen_concepts.py` (logging, ref/edit endpoint, style sidecar, key scrub; drop or reset its `BUDGET` cap), `tools/pipeline/concepts.json.style.json` as a template, `tools/pipeline/items/{gen_items.py,split_sheet.py,icon2d.py,card_frame.py}`, `tools/pipeline/monsters/concepts/` and `tools/pipeline/items/wave2/concepts_w2.py` as prompt builders, `tools/art-models/gen/` (GPT, Meshy, Tripo clients). Still to adapt: the model env var default (`OPENAI_IMAGE_MODEL`), output dirs, the `by` tags and the STYLE block.
