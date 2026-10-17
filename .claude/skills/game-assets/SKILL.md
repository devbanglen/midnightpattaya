---
name: game-assets
description: Make game assets for this project (and any project that copies this skill) — outfits/clothes, headgear (hats, circlets, bands), weapons per class and level, and later monsters, mounts, props, icons. Says which tool does what (OpenAI gpt-image for concepts and outfit paint, Hunyuan3D on our GPU box for rigid 3D props with Meshy only for the pieces Hunyuan fails, confirmed by the owner once per batch, Blender for fitting/baking, gates for "done"), the spec per asset type, and the order of steps. Use whenever the owner asks for a new item, set, outfit, hat, weapon, monster or any generated art, a retake, or a batch of them. ไทย: ทำไอเท็ม ชุด หมวก อาวุธ มอนสเตอร์ ของสวมใส่ ทำเพิ่มหลายชุด
---

# Game assets: what to use for what, and the fixed order

Project specifics (paths, budgets, palette, ids, decision numbers) are in [references/project.md](references/project.md).
Everything else here is meant to work in any project that copies this folder ([references/porting.md](references/porting.md)).

## Which tool for which job
| Job | Tool | Why | Detail |
|---|---|---|---|
| Concept of a prop (hat, weapon, shield, accessory) | **OpenAI gpt-image** via the logged concept script | fast, cheap, follows our style ref | [openai-images.md](references/openai-images.md) |
| Paint of an outfit piece | **gpt-image** on a *spec image* of the template piece (front, then back) | the paint lands on a mesh that already fits | [outfits.md](references/outfits.md) |
| Rigid prop to 3D | **Hunyuan3D on our GPU box** first, **Meshy** only for pieces Hunyuan fails (next section) | | [meshy.md](references/meshy.md), [hunyuan.md](references/hunyuan.md) |
| Outfit geometry (body, hands, legs, feet, cape) | **never image-to-3D**: the template mesh + our silhouette ops + the baked paint | fits and animates like the template | [outfits.md](references/outfits.md) |
| Fitting a prop to the rig | Blender (headless) fit modes / weapon_fit by family | same placement for every head / every attack clip | [headgear.md](references/headgear.md), [weapons.md](references/weapons.md) |
| Hair | parked in this project (template hair) | our generated hair looked wrong 3 times | [project.md](references/project.md) |
| Animation clips for new weapon types / actions (spear, staff, casts…) | **retarget** a humanoid clip pack onto the template rig in Blender (world-rotation delta + rest-direction alignment) | new types need their own stand/walk/attack clips; the template has none | [animations.md](references/animations.md) |
| Item icon + stats (armor, pants, shoes, garment, accessory, and every 3D item) | `tools/items/make_icons.py` from our concept crop (no GPU box, no new art); `tools/items/item_stats.py` by type × band | the concept already has the look; icons stay in the same style | [project.md](references/project.md) |
| Monsters, mounts | not built yet: plan in [monsters.md](references/monsters.md) | | |
| Class / job outfit design | gpt-image turnaround (5 views on white, style ref = locked turnaround) per class × gender, then the outfit route | one look per class before 3D | [outfits.md](references/outfits.md) |

## 3D tool per category (default; the owner confirms per batch)
**Hunyuan first, Meshy only for the really hard pieces.** Every rigid prop (weapons, costume weapons, headgear normal and
costume, shields, props, monsters, map objects) starts on Hunyuan3D on our GPU box with the colour clean-up
([hunyuan.md](references/hunyuan.md)). A piece goes to Meshy ([meshy.md](references/meshy.md)) only when Hunyuan fails it:
1. Hunyuan + clean-up → fit → gates → look at it worn.
2. Fails (shape broken, parts missing, colours/texture still wrong, see-through parts unfixable) → one Hunyuan retry
   (other seed / settings).
3. Still fails → **Meshy for that item only**, inside the confirmed plan (no need to ask); count it in the report.
Known Hunyuan-hard cases (A104 batch, 3 of 88 needed Meshy): wrapped cloth (turban), tall glossy cylinders (shako), dark
fur/hair shapes (moustache). Retry these once anyway; plan for Meshy. Glasses lenses are fixed by the lens step, and
shields keep weapon_fit's facing, never flipped afterwards (hunyuan.md). Each batch plan names the expected Meshy share and credits.

**Confirm once, then run long.** Before a batch, show the owner one short plan: category → tool, item counts, Meshy
credits and GPU time, and which items fall into "detailed" vs "simple". The owner confirms or changes it (they can
change the defaults above at any time; record changes in project.md). After the confirmation, run the whole batch
without stopping to ask: the owner may be away or asleep. Make judgement calls inside the confirmed plan (e.g. a
Hunyuan retake to Meshy), note them, and report them at the end. Ask again only for something outside the plan
(credits run out, a new category, a change that costs much more than planned).

## The order for any new asset (do not skip steps)
1. **Design in words** (theme, palette from the game palette, 5–7 colours, what each piece is made of). Names (th + en)
   go into the set catalogue at the same time.
2. **Concept** with gpt-image, our own style reference only (never third-party art). Look at every image before going on.
3. **Make it 3D** with the route of its type (table above).
4. **Fit** onto the rig with the fit mode of its type.
5. **Gates**: static gate (budget, bones, texture, envelope) + fit gate for worn pieces (cover/seam ≥ 0.95 on foot and
   riding, sinking into the mount ≤ template + 0.02). [gates.md](references/gates.md)
6. **Look at it worn** — every hat/weapon/outfit on the character, front + side, both genders, before saying done.
   Gates passing is not enough (owner found caps sitting over the face that passed every gate).
7. **Into the preview tool** (lab build + a one-click button), then report: what passed (numbers), what failed, images
   and links, API counts (GPT images, Meshy jobs/credits).
8. **Log** a decision row for every new rule; update the handoff.

## Common rules (own copy, no longer from sprite-pipeline)
| Need | Read |
|---|---|
| Renting, bootstrapping, verifying, tearing down GPU boxes (one box / a fleet) | [common/gpu-server-setup.md](references/common/gpu-server-setup.md), [common/gpu-server-setup-fleet.md](references/common/gpu-server-setup-fleet.md) |
| Keys, `.env`, what never goes to a box | [common/secrets.md](references/common/secrets.md) |
| Third-party material, what may be AI input | [common/third-party-and-ip.md](references/common/third-party-and-ip.md) |
| Tier budgets, measuring on a real GPU | [common/performance.md](references/common/performance.md) |
| GPT concept art, style lock, prompt blocks | [common/concept-art.md](references/common/concept-art.md), [common/concept-art-prompts.md](references/common/concept-art-prompts.md) |
| Decision log, golden samples, gates mindset | [common/decisions-and-gates.md](references/common/decisions-and-gates.md) |
| Where generated output lives, dir budgets, backups | [common/generated-output.md](references/common/generated-output.md) |
| The sprite-kit this project started from | [common/kit.md](references/common/kit.md) |

## Specs in one place
- Outfit pieces: slots, seams, budgets, silhouette ops, template catalogue → [outfits.md](references/outfits.md)
- Headgear: open/closed, eye-level concept, fit modes crown / tall / band / ontop / glasses / ears / mask / mouth → [headgear.md](references/headgear.md)
- Weapons: one frame for all types, families blade / head / bow, glow orbs, level tiers and RO-style progression → [weapons.md](references/weapons.md)
- Budgets and gates → [gates.md](references/gates.md)
- Hunyuan on the GPU box: setup, sharing rules, colour clean-up recipe → [hunyuan.md](references/hunyuan.md)
- Animations: retargeting a bought/other rig's clips, naming `<type>_atk1..`, checks → [animations.md](references/animations.md)

## Batches
Run sets in parallel (concepts are the slow part); one lab build at a time (it is locked). Give each set its own log;
watch for `error`, `FAIL`, `WARN`, `credits`. API credit can run out mid-batch: existing images are kept, rerun the same
command after a top-up. [batches.md](references/batches.md)

## Keep this skill true
When a step, a tool option, a fit mode, a budget or a lesson changes, **update this skill in the same task** (SKILL.md for
the map and the order, the reference file for the detail) and say so in the report. If something here turns out wrong,
fix it here rather than working around it. Project-only facts go to references/project.md, never into the general files.
