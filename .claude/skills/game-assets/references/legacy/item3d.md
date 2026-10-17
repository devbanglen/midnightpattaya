# Legacy (folded into game-assets on 2026-10-17, kept for the details it still has)


# 3D wearable item: the fixed flow (A025, A026, A027)

Spec: `docs/game/ITEM_SPEC_3D.md` (slots, seams, layering, sockets, gates). Budgets: `docs/game/PERFORMANCE.md` §3.
Slots and their names: `cap` (= RO head_top), `head_mid` (glasses/masks), `head_low`, `body`, `hands`, `legs`,
`feet`, `cape`. Item id = `<slot>_<set>_<g>_<tier>` (e.g. `body_sw1_m_t1`), always both genders `m` and `f`.

## 0. Which route (A029, A032)
- **Outfits: use skill `outfit3d`** (`tools/ayolab/outfit.sh <design.json>`, spec-first, A032). The paint route below is older.
- **Clothes (body, hands, legs, feet):** paint the TEMPLATE mesh with our concept — shape, volume and weights stay the
  template's, so the look matches universe-art and the gates pass:
  ```sh
  blender.exe -b -P tools/ayolab/bl_template_obj.py -- --lab <lab> --part <slot>_swordsman_<g>_t2 --out /tmp/paint_in/<part>.obj
  cp art/concepts/items3d/<concept>.png /tmp/paint_in/<part>.png        # one concept per template part
  rsync /tmp/paint_in/ to the box; flock /root/kit/hy.lock ... python gpu/paint_mesh.py paint_in paint_out   # ~11 s each
  tools/ayolab/paint_part.sh <part> art/items3d/paint/<part>_tex.obj art/items3d/paint/<part>.json \
      art/items3d/own/<slot>_<set>p_<g>_t1.glb <g>
  ```
  Pick the template whose shape is closest to the concept (t2/t3/t4, other sets). Shape changes = later silhouette edits.
  The concept for this route (A031, `docs/game/OUTFIT_METHOD.md`): GPT TEXT layout of the template's pieces with our
  materials/colours, ref = our style lock only (prompts `tools/ayolab/items/sw1_method_concepts.json` `sw1t_*`);
  optional back view as `<part>_back.png` next to it. Never a palette swap of the template texture for shipping.
- **Headgear and rigid props:** image-to-3D (steps 1–3 below) is fine: small, rigid, `--faces` at the budget.
- The old image-to-3D route for clothes (steps 3 body/legs) works on the gates but looks flat and noisy: don't use it.
- Every own item gets the templates' unlit material in `build_lab.py`.

## 1. Concept (GPT, logged)
- Add one entry per piece to a prompt file in `tools/ayolab/items/` (copy the newest entry of
  `sw1_concepts.json` as the template: ref = our own style lock `art/concepts/explore/r6_lock/…`, never third-party art).
- Prompt rules that make the later steps work:
  - ONE piece only, exactly FRONT view, orthographic, plain pure white background, generous margin.
  - Clothes on an INVISIBLE mannequin in our bind pose: A-pose, arms straight about 40° below horizontal, legs straight.
  - Sleeves CLOSE-FITTING, even width, ending at the wrist (bell/flared sleeves failed the fit gate: sw1 tunic v1).
  - Trousers waist to ankle; boots and gloves as a pair side by side with a gap; caps/glasses alone.
  - Headgear: say OPEN (circlet, band) or CLOSED (covers the crown); draw it at EYE LEVEL from the front with a level brim (A059: views from above come back tilted from image-to-3D); tall hats use `--fit tall`; pairs (ears) side by side with a head-width gap;
    mouth items held horizontally across the mouth. Prompts of a working set: `tools/ayolab/items/hg1_concepts.json`.
  - Avoid complex shells with add-ons at the cap budget (winged helmet failed at 480 tris); keep caps one simple shell.
  - Style line: stylized chibi-MMORPG 3D asset, RO charm + Rohan / Seal Online materials, hand-painted look.
- Run: `set -a; . ./.env; set +a; python3 tools/pipeline/gen_concepts.py <prompts.json> art/concepts/items3d --only <id>`
  (no need to ask about quota; report the call count). Look at the image before going on.

## 2. Image → 3D (Hunyuan3D-2.1 on vast-rtx6000-1 or -2)
```sh
W=/tmp/ayo_hy_<id>; mkdir -p $W
python3 tools/art-models/tools/cut_white.py art/concepts/items3d $W <id> [<id> ...]
rsync -a $W/ vast-rtx6000-1:/root/ayothaya/hy_in_<batch>/
ssh vast-rtx6000-1 'cd /root/ayothaya && flock /root/kit/hy.lock env HF_HOME=/workspace/.hf_home \
  HY3D_REPO=/root/w/Hunyuan3D-2.1 /root/w/hyenv/bin/python gpu/batch.py hy_in_<batch> hy_out --texture \
  --faces <F> --steps 30 --octree 256 --tex-size 1024 --render-size 1024 --no-upright > hy_<batch>.log 2>&1'
rsync -a --include='<id>*' --exclude='*' vast-rtx6000-1:/root/ayothaya/hy_out/ art/items3d/hy_sw1/
```
- `--faces <F>`: let Hunyuan simplify BEFORE it unwraps and bakes the texture: F = slot budget minus ~5 %
  (cap 480, head_mid 380, head_low 190; clothes 20000 and our decimation is fine). Decimating a 20k textured mesh down
  to a few hundred tris shreds it. One batch per F.
- ~15–30 s shape + 12–20 s texture per item. Work only in `/root/ayothaya`; never touch aroa's files or other
  processes on the box; kill only our own PIDs; no key ever goes to the box. `gpu/batch.py` = `tools/art-models/gpu/batch.py`.

## 3. Auto-fit onto our rig
`tools/ayolab/ingest.sh <slot> art/items3d/hy_sw1/<id>_tex.obj art/items3d/own/<slot>_<set>_<g>_t1.glb <g>`
for `g` in `m` and `f` (Blender `tools/ayolab/bl_ingest.py`; budgets per slot are inside `ingest.sh`).
Head items need `--fit <mode>` (and optionally `--wscale`): `crown` closed cap/hat (cap), `band` circlet (cap),
`ontop` ears on a headband (cap), `glasses` glasses/eye masks (head_mid; round specs `--wscale 0.8`), `ears` a pair of
ears on the skull sides (head_mid, like RO elf ears), `mask` cloth over mouth+nose (head_low), `mouth` held in the mouth
(head_low). Ears are head_mid as in RO (they exclude glasses); cat ears on a band are cap. It decimates
to budget, fits by slot (body: box + sleeves onto the arms + cuffs levelled past the wrist; legs: waistband and cuffs
levelled to the seams; hands/feet: per side; head items by `--fit`), cinches hems onto the seam rings, pushes the
piece out of the base body, copies weights, writes `<out>_front.png` / `_side.png`. Look at the previews.

## 4. Gates (an item is done only when both are green)
- Static: `python3 tools/ayolab/item_gate.py <slot> art/items3d/own/<file>.glb` (bones, tris, texture, envelope, band).
- Fit (skinned slots body/hands/legs/feet), on foot and riding:
  ```sh
  tools/ayolab/fit_check.sh <slot> <glb> art/items3d/golden/own_<slot>_<g> <g>
  M=$(wslpath -w "$(realpath studio/public/universe-art/creature/item_ride_pecopeco_orange.glb)")
  tools/ayolab/fit_check.sh <slot> <glb> art/items3d/golden/own_<slot>_<g>_ride <g> --mount "$M" --saddle 23 \
    --ride-clips ride_pecopeco_stand,ride_pecopeco_running
  ```
  Pass = cover ≥ 0.95 and seam ≥ 0.95 over 10 clips; riding also mount sinking ≤ bare body + 5 %.
  `fit.json` → `miss` lists the uncovered proxy points (x, −front, up, on-seam): plot them on the renders to see why.
- Report: `python3 tools/ayolab/golden_report.py --out art/items3d/golden/REPORT.md`.
- Windows Blender from WSL sometimes fails to launch (`UtilAcceptVsock`): the wrappers retry 3×; if a FIT line is
  still missing, wait a few seconds and rerun.

## 5. Into the lab and report
- `python3 tools/ayolab/build_lab.py` (copies `art/items3d/own/*.glb` in, `own: true`), then check `#/labs/ayo3d`
  (preset "ของเราเอง <set>" or the slot dropdowns; ride a pecopeco and press "ตีบนหลัง").
- Studio must stay green: `cd studio && npx tsc --noEmit -p . && npm run validate`.
- Log new decisions in `docs/DECISIONS.md`, update `docs/HANDOFF.md`, answer the owner in Thai, short:
  what passed, what failed with the numbers, GPT calls used, GPU minutes, what to look at in Labs.

Body (tunic) defaults that made it pass (A028): sleeves shrink-wrapped onto the template's sleeves (`--wrap 0.006`,
the template is known to fit), arm bones only inside the sleeve tubes (`--tube 0.13`, hem panels next to the hanging
hands go to pelvis/spine). Tried and worse: bone-heat weights, tighter sleeves alone, template-only weights.

## Known limits (2026-10-15)
- Template outfits: spikes and seams are handled by `shape.py` in the outfit route (A033), not here.
- Female trousers in `pickup` 0.90; universe's own female skirt legs t2 fails in lunges (inner thighs).
- Rider's feet sink ~30 % into the pecopeco in ride poses (seat/pose issue, not items).
