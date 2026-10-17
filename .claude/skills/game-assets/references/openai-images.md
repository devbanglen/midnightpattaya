# OpenAI gpt-image: concepts and outfit paint

## Calls
- Only through the logged concept script (project.md). It sends `ref` images to `/images/edits`, logs every call
  (ok or error) to `<out>/log.jsonl`, skips ids whose PNG exists (delete a PNG to redraw it), prints the counts.
- Prompt file = a JSON list `[{id, kind: "item", size: "1024x1024", quality: "high", ref: [...], prompt}]`.
- `-j 6` is fine for a batch. Report the count of new ok calls to the owner (no need to ask about quota).
- Out of credit shows as `error You have no credits remaining`: everything already drawn is kept; rerun after a top-up.

## Prompt rules that make the 3D steps work
- Image 1 = our own style reference ("for style only"). Never third-party art as a reference.
- ONE subject, plain pure white background, centred, generous margin, no text, no ground shadow.
- Style line: stylized 3D game asset like a modern chibi MMORPG (Ragnarok-like charm, sturdier detailed materials),
  clean readable shapes, hand-painted texture look, soft even studio light, no strong shadows. Name the palette hexes.
- **Headgear:** say OPEN (band, circlet: top of the head stays open) or CLOSED (covers the crown). Draw it worn by an
  invisible head, **exactly from the FRONT at eye level**, orthographic, left-right symmetric, brim a straight horizontal
  line, hollow inside. Views from above come back tilted from image-to-3D. One simple shell; add-ons (feather, tassel)
  attached, never floating.
- **Weapons:** standing perfectly VERTICAL, the business end UP (blade tip, orb, axe head), handle at the bottom, seen
  exactly from the side (flat side to the viewer), orthographic. Everything connected (no floating gems: image-to-3D
  drops them, see weapons.md `--orb`). Say "cool and heroic, a weapon players want".
- **Bows:** vertical, limbs curving to the RIGHT, string straight on the left.
- **Outfit paint:** see outfits.md (the script writes those prompts itself from the design file).

## Look before going on
Make a contact sheet of the new images and read it. Redraw (delete + rerun) anything off-spec: wrong view, cut off,
two subjects, background not white, a gem floating free.

## Item sheets for a catalogue (many small items)
One image per type/line: "exactly N separate items in ONE horizontal row (or two rows of three), evenly spaced with wide
white gaps, none touching", left to right by level band, no text/numbers. Cut by white gaps (projection on rows, then
columns; sparkles need a larger gap). Normal items: "little or no glow, no aura, no sparkles"; costume items: name the
light, colour and effects explicitly. 4 items per 1536x1024 sheet came back clean every time (A076 pilot, 9/9).
- Equipment that is icon-only (armor, pants, shoes…): "ONLY the TORSO armor piece (RPG body-armor slot) … ends at the
  waist, no legs, no robe skirt, no full outfit … adventurer/fighter battle gear, not everyday clothing", style line
  "classic fantasy RPG inventory item art … chunky readable game-gear shapes … not a real-world garment". A first try
  that asked for "tunics/robes laid out" came back as real clothes / full outfits: the owner rejected it (A076).

## Item concept sheets (A077–A082)
- `tools/items/batch_concepts.py --name=batchN` groups every planned item without a concept into sheets of up to 4 on white; `--split` cuts them (`split_sheet.py`, equal-column fallback) and `split_sheet.py` runs `cutout.py` on every crop (border flood-fill to alpha; pure-white holes only for bows, puppets and knuckles, because white cloth would get holes; then drops slivers of a neighbour item: keeps the biggest run of columns and rows). Re-run `plan_items.py` after.
- Normal weapons (A080, A083): t1/t2 as colourful as end-game weapons (coloured enamel, gold, big gems, rune glow), t3/t4 only a little grander; aura and particles only on costume weapons. Knuckle = knuckle-duster object, say NOT a glove / hand or it draws a fist. Every slot gets a theme so items in one sheet differ.
- Armor / pants / shoes (A080): `CLASS_LOOK` gives each class line a text look plus our own class outfit concept as Image 2 (mage cloth, rogue dark leather, archer green leather, cleric white/gold, summoner pastel Thai cloth: no metal plates). Torso piece only, one pair of shoes.
- A planned type that is dropped (charm, katar) leaves crops: move them to `art/concepts/items3d/_old_a080/`.
- Class / job outfit concepts (A081–A088; turnaround of 5 views on white, style ref `r6_lock/char_sword_turn.png`): `art/concepts/classes/`, e.g. Assassin ninja (A081/A082).
