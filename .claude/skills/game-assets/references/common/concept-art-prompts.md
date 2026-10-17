<!-- copied from ~/.claude/skills/sprite-pipeline/references/common (ced2f55) on 2026-10-17; ayothaya owns this copy now -->
# Prompt blocks per kind

Routes: the POSE/VIEW blocks are for image-to-3D input (3d-sprite, 3d-realtime, redesign); STYLE, icon grid, card, aura and prop blocks fit any route. Origin: aroa (all blocks passed there).

Each prompt = **subject/design note** (1–3 sentences: type, shape, colours, motif; hex colours help) + **POSE/VIEW** + **PROPORTIONS** + **STYLE** + **FRAMING/BACKGROUND**. The blocks below are the ones that passed in aroa (chibi, soft 3D toon look); swap the PROPORTIONS/STYLE wording for your game's look, keep the structural rules.

## Shared STYLE (aroa example)
> softly 3D but not realistic: toon / cel shading with only 2-3 tones per colour, flat clean colour areas, limited harmonious palette, clean thin dark outline, matte surfaces, no PBR shine, no texture noise, no fine print or tiny details.

## Character (base body, image-to-3D + auto-rig input)
> POSE (very important, this image is the input for image-to-3D and auto-rigging): one single character, full body, strict front view facing the viewer, perfectly symmetric neutral A-pose. Both arms straight and held clearly away from the body at about 40 degrees below horizontal, with a wide clear gap of empty background between each arm and the torso; open relaxed hands, fingers together, palms facing the thighs. Legs straight, feet slightly apart with a visible gap between the legs, feet flat on the ground pointing forward. Neutral friendly expression, eyes open.
> PROPORTIONS: cute chibi proportions, about 3.25 heads tall … (original design, not any existing character).
> FRAMING: entire figure visible from the top of the hair to the soles, centred, with margin on all sides. Plain pure white background, even soft frontal lighting, no cast shadow, no ground plane, no text, no logo, no extra objects. Nothing in the hands, no weapon, no shield, no cape or long scarf hanging away from the body.

Size 1024×1536, high. Siblings use the first approved character as edit reference ("use the reference ONLY for pose, proportions, head size, camera, framing, style; redesign completely").

- **Female variant** (when male and female share one skeleton but must read differently): add *FEMALE LOOK: feminine face with large eyes and visible upper eyelashes, softer rounder jaw, small nose, light blush; slightly narrower shoulders, visible waist, slightly wider hips; modest outfit* and the *HAIR RULE (for 3D rigging): nothing may hang in the gap between the arms and the torso; long hair goes straight down the BACK behind the body, or is tied up close to the head.* (aroa)
- **Cropped-hair base** (for swappable hair layers, edit of the approved character): *Redraw EXACTLY the same character … Change ONLY the hair: a VERY SHORT CLOSE-CROPPED BUZZ CUT that hugs the skull … full forehead and both ears visible, no fringe, nothing sticking out. NOT bald: the hair colour covers the scalp.* (aroa)

## Head bust (standard head / face redesign)
> Draw only a head-and-neck bust … VIEW (input for image-to-3D): strict front view, perfectly straight, level and symmetric, centred, margin on all sides; the bust ends with a short neck stump; no shoulders, no clothes. HAIR: the same very short close-cropped buzz cut as the reference.

Face direction as a description, never a person: *youthful slim V-line face with FULL smooth rounded cheeks (never gaunt), large clear eyes with soft double-eyelid line and glossy irises, small straight nose as a tiny soft shadow, small closed-mouth smile.*

## Hair style (two images per style)
1. **Concept** on the approved bust: *keep EXACTLY the face; replace the cropped hair with: <style>. A single hair colour with 2-3 toon tones and darker strand lines … No hat.* Styles with something behind the head (ponytail, buns) get a *front three-quarter view, head turned ~35°*. (aroa)
2. **Mannequin twin** (the actual mesh input): *Redraw EXACTLY the same image … Change ONLY the head: face, ears and neck become a blank smooth matte LIGHT BLUE-GREY mannequin (one flat cool grey, only two thin closed-eye lines). The hair stays the only coloured thing, separated by a thin dark outline.* The grey head lets the fitter separate hair from skull cleanly. (aroa)

## Monster (by archetype)
> MONSTER: <design note, hex colours>. SCALE: a SMALL creature (about knee-high to a chibi hero); it fills about 60% of the image height. | MEDIUM … 75% | mini-boss: "noticeably bigger and more impressive than a normal one".
> PROPORTIONS: cute chubby chibi creature, big simple rounded shapes, big readable silhouette, few small details (original creature design).
> STYLE: … no fur strands.
> FRAMING: exactly one creature, entire body visible with margin, centred. Plain pure white background … no grass, no ground plane.

POSE per archetype (each begins "POSE (input for image-to-3D and rigging):"). The common thread: **every limb, wing, tail and arm separated from the body by visible background**, because the fitter finds limbs from gaps.
| archetype | POSE wording |
|---|---|
| blob | front three-quarter view, sitting still on its flat round bottom, neutral idle, symmetric, eyes open |
| quadruped | standing on all four legs, side three-quarter view (left side shows, head turned slightly toward the viewer), all four legs straight, separated, gaps between them, tail held clearly away from the body, mouth closed |
| bird | standing on both feet, front three-quarter view, legs straight and visible, wings opened slightly away from the body with background between wing and body, beak closed |
| flyer | hovering in mid-air, front three-quarter view; wings spread slightly open, fully visible, not overlapping the body; arms, legs or chains hang relaxed and separated |
| serpent | side three-quarter view, the long body lying on the ground in a gentle shallow S-curve, fully visible head to tail, not coiled, not rearing up, head slightly raised toward the viewer |
| insect upright | standing on its rear legs (front legs may hold its item close to the body), front three-quarter view, all legs separated with gaps |
| insect low | standing low on all legs, side three-quarter view (left side shows), every leg separated, nothing raised high |
| plant | front three-quarter view, rooted upright, arms or leaves held out to the sides with gaps |
| biped (uses the character rig) | full body, strict front view, neutral A-pose, arms ~40° below horizontal with a wide gap, legs apart; a held weapon points straight down along the outside of the right leg, not crossing the body; anything trailing stays below and between the legs; mouth closed or neutral (1024×1536) |

## Items
- **Weapon:** *VIEW: one single weapon, side view, standing perfectly upright and vertical: grip/handle at the bottom, tip or head at the top, centred, whole object visible with margin. Nothing else: no hands, no stand, no shadow, no text.* (Whips: lash held stiff in a gentle vertical S-curve, nothing coiled or crossing. Fist weapons: one empty glove-like object, fingers up, no hand inside.) (aroa)
- **Shield:** *one single shield, straight front view, upright, centred … no arm, no stand.* (aroa)
- **Headgear:** *one single EMPTY headgear, three-quarter front view (turned slightly left, seen a little from above) … no head, no hair, no face, no mannequin.* Rings and scarves: front view, not "from above" (the mesh step flattens them into a horizontal disc). (aroa)
- **Garment / cape:** *one single empty cape as worn by an invisible person, three-quarter BACK view, hollow inside, collar at the top, cloth hanging straight down in simple thick folds, ending above the knees.* (aroa)
- **Wings / back items:** *both wings spread symmetrically, joined by a small flat back mount, three-quarter BACK view, opaque solid toon wings, no transparency, no body, no straps.* (aroa)
- **Item PROPORTIONS/STYLE:** *chunky stylized chibi game item, slightly oversized, thick rounded parts, big simple readable shapes, very few small details. softly 3D toon / cel shading with 2-3 tones per colour … matte, no realistic PBR, no glow effects. BACKGROUND: plain pure white, even soft lighting.* (aroa)

## Icon grid (icon-only items)
> GAME ITEM ICON SHEET: N separate small game items arranged in a loose grid of 2 rows and 3 columns (read left to right, top row first): (1) … (6) …. VIEW: each item upright, three-quarter view, centred in its own cell, whole object visible, each item alone with lots of empty white space around it, no item touching another or the image edge. Nothing else: no grid lines, no frames, no hands, no shadow, no text, no labels, no numbers.

With a reference grid: *Draw EVERY item in the SAME position and order … pale ghost copies, glow shapes and shadow ellipses are NOT items; exactly one object per position.*

## Card illustration
> CARD ILLUSTRATION (portrait, full bleed, no frame, no border, no text): <creature> in <setting>, soft warm light, gentle depth of field; the creature fills the middle. STYLE: softly 3D chibi game illustration matching the toon look, painterly simple background. Original design.

## Outfit (full-body costume on the shared rig)
Edit with two refs (cropped-hair base body + standard head):
> Redraw EXACTLY the same character as the first reference: same body, proportions, symmetric A-pose, framing and style, with the cropped hair and the head/face of the second reference. Change ONLY the clothes and shoes: <outfit>. The outfit hugs the body and stays close to the default body outline: NO hood, NO headwear, NO wide or flared sleeves, NO cape, NO long skirt or train (anything long ends at mid-calf and is split at the front so the legs show), nothing in the hands, nothing on the head. Collar at the base of the neck, the neck visible.

The silhouette rules exist because hair/headgear/back layers of the base body are reused on the outfit body.

Themes that drift (aroa P4: 2 of 8 retaken): swimwear and gothic/vampire outfits drift toward high-cut legs, open shirts, sweetheart necklines and tall stand-up or spiked collars, which break both all-ages rules and the above-collar gate. Spell the safe version out in the item's own text instead of trusting "modest": *swim dress with a high round neckline, cap sleeves and built-in shorts to mid-thigh, sarong wrapped all the way round to the knee*; *shirt buttoned over a tank top*; *HIGH CLOSED neckline, chest fully covered*; *collar LOW and flat at the base of the neck, any collar points pointing DOWN, nothing rising beside or behind the head*. Check the torso crop at full size, not only the thumbnail.

## Aura (reference only; the aura itself is procedural)
> GAME EFFECT CONCEPT: a looping cosmetic aura shown ALONE with no character … fixed game camera looking down at 45°: a flat elliptical ring on the ground in the lower middle (~45 % of image width), particles rising around an EMPTY vertical space above the ring … flat 2-tone shapes, thin darker outline, no blur, no bloom. BACKGROUND: flat dark slate grey (#3A3F4A).

## Map prop
> PROP: <object, hex colours>. VIEW: three-quarter view from the front and slightly above (camera ~20° above the horizon), standing upright. SHAPES: chunky, rounded, solid volumes, no thin floating parts. FRAMING: exactly one object … no grass base or soil disc under it.
