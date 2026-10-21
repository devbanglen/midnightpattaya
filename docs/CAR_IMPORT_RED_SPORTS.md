# Car import: red_sports (Tripo) and red_sports_meshy (Meshy)

Branch `team19/car-import`. Status: **built and QA-rendered offline in Blender on the GPU box (2026-10-21).
Nothing uploaded, nothing imported, nothing run in Roblox.** Every in-game behaviour below is a prediction until
the leader runs the Play test plan.

**Recommendation: use `red_sports` (Tripo).** See *Which one looks better*.

## Owner rules for this car (2026-10-21)

1. Originals untouched, outputs separate (see *Source files*).
2. **No upload and no import to Roblox until the owner confirms usage rights** (see *Licensing and badges*).
3. **Not in the garage, not in CarSpecs, not available to players.** Test vehicle only: spawned by the TestKit
   (`S.spawnCar`), removable (see *Rollback*).
4. QA checks: alignment, steering pivot, suspension clearance, spin axis/direction, triangles, textures, collision.

## Licensing and badges (owner must confirm)

- `red_sports`: `"generator": "Tripo"`, made by the Tripo AI service. `red_sports_meshy`: made by Meshy (written by
  pygltflib). **The owner must confirm they have the rights to use each one in a published Roblox game** (plan /
  terms of the service).
- **Trademark risk, both textures.** Both cars read as a Ferrari 812-style GT and carry Ferrari badges in the
  texture:
  - **Tripo:** yellow prancing-horse shield on the nose, a horse on the grille and the tail, yellow shields on both
    front wings, yellow centre caps with the horse on all four wheels.
  - **Meshy:** shield on the nose, a horse on the grille and the tail, yellow centre caps with the horse on the
    wheels. The wing shields are less clear.
  - A real brand's logo in a Roblox game is a moderation and trademark risk even when the mesh licence is fine.
    `red_sports` keeps them (owner decision). The de-badged copy is `red_sports_fictional`: see
    *Fictional-brand version* at the end.

## Source files (not in git, too large)

| | Tripo `red_sports` | Meshy `red_sports_meshy` |
|---|---|---|
| path (leader's machine) | `C:\Users\src3r\AppData\Local\Temp\claude\D--ROBLOXRACE\13fa2bc9-cdf0-4f9f-857d-7126dc2df433\scratchpad\glb_in\car.glb` | `...\scratchpad\meshy_in\texture.glb` (`generate.glb` = the same mesh without UV/texture, not used) |
| sha256 | `550802ba55a78c0f826d8fb8232768c5166a31bb849c3c2d4a670c3327e13f4e` | `2646147e8c4c7ceb145b40ebea4e6bf2dd6332f7ea56dd08d5ce444895383c10` (`generate.glb`: `76fc2d88227cc5b090741df4907190314492e5fba72576e51f4721f6b306b6d2`) |
| size | 57,493,380 B | 43,395,124 B |
| content | 1 node, 1 mesh, 1 material, base colour JPEG 2048², **1,943,102 tris**, length along Z | 1 node (identity matrix), 1 mesh, PBR: base colour + metallic-roughness + normal (3 JPEGs), **1,229,448 tris**, length along **X** |

## How the front was decided

`car_import_wheels.py` takes glTF Y as up and the longest horizontal axis (X or Z) as the length. It turns that
axis onto Z, then votes on the two ends:

1. **Lamps in the texture:** the share of light grey/white lamp or chrome pixels over the end 6 % of the length.
   Saturated red does not work on a red car.
2. **Roof-line profile:** the nose is the lower end.

| | lamp vote | profile vote | looked at (end-on / side point splats) | front |
|---|---|---|---|---|
| Tripo | +Z 1.46 % vs -Z 0.21 % | +Z end lower (0.132 vs 0.215) | +Z: swept headlights, grille, intakes; -Z: 4 round red tail lamps, diffuser, quad exhausts | **source +Z** |
| Meshy | -X end has more light pixels (0.24 % vs 0.06 %) | -X end lower | -X: splitter, low nose; +X: tail lamps, exhausts, high deck | **source -X** |

Both are turned so the front is **-Z** (pipeline / Roblox convention), length 4.5 m, like the other cars. The
script warns if the two votes disagree; `--front` overrides.

## Pipeline (all scripts on this branch)

| step | file | what |
|---|---|---|
| run | `tools/blender/run_import_car.sh <glb> <out> <id> [--image-format JPEG]` | sends only the GLB + the 2 scripts to `/root/robloxrace/car_import`, runs Blender via `gslot.sh` with `--python-exit-code 1`, fetches into `<out>`. In a git worktree, use an `<out>` outside the repo: a worktree-local `build/` hides the main checkout's map outputs from `run_all.py` (`test_module_sizes` fails). Full build outputs of this run: `C:\Users\src3r\AppData\Local\Temp\claude\D--ROBLOXRACE\13fa2bc9-cdf0-4f9f-857d-7126dc2df433\scratchpad\car_import_out\<id>\` |
| 1 measure | `tools/gpu/car_import_wheels.py` (numpy + Pillow) | applies the node transform, picks the up and length axes, decides the front, maps to frame N (X right, Y up, front -Z, metres), finds the 4 wheel cylinders (ground-contact run + arc fit, then tread radius and width) -> `<id>_detect.json`; `--luau <id>_wheels.json` prints the Studio install snippet |
| 2 build | `tools/blender/import_car.py -- build` | cuts each wheel (faces with all verts inside 1.015 r and inside the tyre's x band ±3 cm). Body paint over the tyre (> 0.82 r), arch-lip strips that face the axle, and loose pieces under 2 % stay with the body. Each wheel: origin on the axle, a dark cap on its back, Decimate to <= 2,000 tris, colour baked to its own 512² texture. Body: a dark double-sided disc (1.15 r) 6 cm inboard of each wheel so the arch is not see-through, Decimate to <= 18,000 tris (UVs kept), every texture map scaled to 1024², centred on its bbox |
| 2' build_parts | `import_car.py -- build_parts <body.glb> <wheel.glb> <parts.json> <out>` | separate body + one wheel (Meshy "split"): not needed here because Meshy's split did not separate the wheels, so its fused mesh went through `build` like Tripo. Not tried on real input |
| 3 qa | `import_car.py -- qa` | renders + `<id>_qa.json` |

## Results (measured, from `<id>_build.json`, `<id>_wheels.json`, `qa/<id>_qa.json`)

| | Tripo `red_sports` | Meshy `red_sports_meshy` |
|---|---|---|
| source tris | 1,943,102 | 1,229,448 |
| body tris after cut -> final | 1,358,846 -> **17,820** (incl. 224 arch-disc tris) | 759,747 -> **17,819** |
| wheel tris FL / FR / RL / RR (cut -> final) | 151,005 / 138,605 / 150,808 / 143,838 -> **1,979 / 1,980 / 1,980 / 1,978** | 113,952 / 116,350 / 122,372 / 117,027 -> **1,980 / 1,979 / 1,979 / 1,979** |
| body textures | base colour 1024² (PNG embedded) | base colour 1024², metallic-roughness 1024², normal 1024² (JPEG q90 embedded; PNG made the body 5.3 MB) |
| wheel textures | 4 x 512² baked colour (PNG) | 4 x 512² baked colour (JPEG); the wheels carry no PBR maps |
| GLB sizes | body 2,358,052 B; wheels 337,852 / 326,572 / 337,740 / 335,468 B | body 1,288,936 B; wheels 130,604 / 134,768 / 134,048 / 130,268 B |
| body size (m, x y z) | 2.207 x 1.255 x 4.501 | 2.062 x 1.160 x 4.499 |
| wheel radius / width (layout) | 0.3848 / 0.3875 (all four within 1 mm) | 0.4234 / 0.4302 (front 0.407, rear 0.440: staggered) |
| wheel centres (m, body space, front -Z) | FL (-0.8878, -0.3235, -1.2939) FR (0.8782, -0.3229, -1.2939) RL (-0.8879, -0.3276, 1.3498) RR (0.8783, -0.3279, 1.3498) | FL (-0.7563, -0.2842, -1.2956) FR (0.7531, -0.2822, -1.2956) RL (-0.7556, -0.2510, 1.3988) RR (0.7530, -0.2525, 1.3988) |
| rim colour | (52, 45, 45) | (74, 74, 74) |

Width is the cut width (tyre + 3 cm margins). In game it only sizes the hidden cylinder.

### QA checks

| check | Tripo | Meshy |
|---|---|---|
| axle alignment (front/rear z, y left vs right) | 0.0 / 0.6 mm | 0.0 / 2 mm |
| left-right symmetry (FL.x + FR.x) | -9.6 mm (the source is 1 cm off-centre; kept) | -3 mm |
| wheelbase / track | 2.644 / 1.766 m | 2.694 / 1.509 m |
| **wheel mesh bbox centre vs axle** (Roblox centres a MeshPart on its bbox: this offset is spin wobble) | 3-6 mm (invisible) | **29-34 mm on FL, FR, RR** (arch-lip bits left on the wheel; a visible wobble of about 0.1 stud) |
| roundness (empty 10° sectors in the tread ring) | 0 on all four | 3-5 per wheel (polygonal outline) |
| wheel in arch at rest: body points inside the tyre ring / deepest | FL 603 / 1.9 cm, FR 670 / 1.9 cm, RL 189 / 1.7 cm, RR 43 / 1.1 cm: thin arch-lip slivers kept on the body that overlap the tyre surface. Hidden at rest | FL 640 / 7.7 cm, FR 624 / 8.1 cm, RL 1299 / 8.6 cm, RR 1543 / 8.3 cm: the arch liner sits inside the tyre |
| suspension travel (CarController: bump 0.248 m, droop 0.203 m at 3.554 studs/m) | contact from the first bump step (0.4 cm) because of those slivers; at full bump the tyre top goes through the wing (side picture in `_sweeps.png`); full droop clean on the rears, 60-70 points on the fronts | same, plus 685-947 points at full droop on the rears |
| steering ±28° about the vertical axis through the wheel centre | 303-467 points, deepest 9.6 cm: the tyre's front/back edge swings into the arch ends, and at full lock the FR tyre top shows above the low front wing (`_sweeps.png`, 3/4) | 379-581 points, deepest 10 cm, and **large black arch-liner chunks swing out with the wheel** (they were cut with it) |
| spin axis / direction | mesh X = wheel part X; origin = axle. `CarController`: `spin += fs*dt/r`, `C0 * Angles(-spin,0,0)`: forward (-Z) motion moves the contact point to +Z = rolling. Game radius = WheelRadius x 1.04, so the mesh turns 4 % slow and floats 1.5 cm | same |
| collision | chassis Part 7 x 1.6 x 15 studs collides; body 7.84 x 4.46 x 16.0 studs, CanCollide false, Massless; wheel meshes CanCollide/CanQuery/CanTouch false, Massless, welded to the hidden (non-colliding) wheel cylinder; suspension is raycasts | body 7.33 x 4.12 x 16.0 studs; rest the same |

Clearance numbers come from body surface points (verts, triangle centres, edge midpoints, arch discs excluded)
inside the tyre ring (0.75 r .. 0.985 r, 90 % of the cut width). "Hub area" points (< 0.75 r) are counted
separately: Tripo 8-44, Meshy 0-2. They sit behind the rim.

### QA renders (looked at; `art/cars3d/roblox/qa/`, 1100 px wide)

- `<id>_before.png`: source mesh (1.9 M / 1.2 M tris), 6 views (sides, top, 3/4 front, front, 3/4 rear).
- `<id>_after.png`: final body + 4 wheel GLBs at the layout centres, the same 6 views.
- `<id>_body_only.png`: body without wheels (arch discs, cut quality).
- `<id>_sweeps.png`: full bump (side, 3/4), full steer (top, 3/4).
- `<id>_wheels.png`: per wheel: outer face, inner face (dark cap), tread, turned 30° about X.
- `<id>_source_splat_side.png`: the point splat used for the front decision.

**What I saw.**

- **Tripo after decimation:** close to the source. Clean paint, sharp lamps, grille and diffuser, round 5-spoke
  wheels with red calipers, arches look closed. Faults:
  - no window glass in the source, so the open side windows show seats and a roll-cage-like frame;
  - the calipers turn with the wheels;
  - at full steer the tyre edges leave the arches.
- **Meshy after decimation:** body surfaces blotchy and faceted (the paint breaks into darker triangles on the
  doors and bonnet), grille and intakes noisy, wheels polygonal with red / black arch pieces on top (rears worst),
  and 3 cm off-centre (wobble). It does have dark glass (closed cabin) and PBR maps.

## Which one looks better

**Tripo `red_sports`.** At the same 18 k-triangle body and 2 k-triangle wheels it keeps the shape and the paint
much cleaner, its wheels are round and centred on the axle (3-6 mm vs 3 cm), and its arch cut is clean. The reason
is in the sources: Tripo's tyres are separate from the arches inside the fused mesh, while Meshy's arch liner and
lip wrap the tyre, so any cylinder cut drags liner into the wheel and leaves tyre surface in the body. Meshy's two
advantages are glass in the windows and PBR maps (metal/roughness/normal), with a smaller file (1.3 MB). The PBR
maps do not save it: its normal map was made for the 1.2 M-tri surface and the decimated mesh shades blotchy anyway.

If Meshy is wanted later: a Meshy export **with wheels as separate parts** (body without wheels + one wheel) goes
through `build_parts` and avoids every Meshy fault above.

## Game integration (code on this branch, reversible)

- `RaceCarServer.server.luau`: if `ServerStorage.CarBodies.<id>` holds MeshParts `WheelMesh_FL/_FR/_RL/_RR` (or one
  per side, `WheelMesh_L/_R`; a missing side uses the other side's mesh turned 180° about Y), each procedural wheel
  part gets a clone of that mesh:
  - scaled like the body, placed at `wheel.CFrame * yaw`;
  - welded with a WeldConstraint;
  - Massless, CanCollide/CanQuery/CanTouch false.

  The cylinder stays (same size, weld, physics) at Transparency 1, and no procedural rim or spokes are made.
  **CarController is unchanged**: it moves the wheel part through `WheelWeld.C0` (suspension, steer about Y, spin
  about X), and the mesh rides along. The body lookup skips `WheelMesh_*`. Cars without wheel meshes build exactly
  as before.
- Yaw: the wheel meshes use `WheelYawFix` if set, else the car's `YawFix` (180 for every imported GLB so far). If a
  left wheel shows its inner (dark cap) face outward in the test, set `WheelYawFix = 0` on the car folder.
- `PattayaTestKitServer.luau`: `S.spawnCar(plr, carId, opts)` (also `TK.server("spawnCar", "red_sports")`) builds
  `TestCar_<id>_<userId>` 14 studs ahead through `ServerStorage.BuildCar`, replaces the previous one, and seats the
  player (`opts.seat = false` to only build). Studio or `DevTest` only. **Not in CarSpecs or the garage**: the
  unknown id drives with `CarSpecs.BASE` stats.

## Upload list (only after the owner confirms the rights) - recommended car

Asset type **Model** (Open Cloud `POST /assets/v1/assets`, `model/gltf-binary`), each < 20 MB:

| file | bytes | MeshPart after import -> name in CarBodies |
|---|---|---|
| `art/cars3d/roblox/red_sports.glb` | 2,358,052 | `red_sports` -> `Body` |
| `art/cars3d/roblox/red_sports_wheel_FL.glb` | 337,852 | `red_sports_wheel_FL` -> `WheelMesh_FL` |
| `art/cars3d/roblox/red_sports_wheel_FR.glb` | 326,572 | `red_sports_wheel_FR` -> `WheelMesh_FR` |
| `art/cars3d/roblox/red_sports_wheel_RL.glb` | 337,740 | `red_sports_wheel_RL` -> `WheelMesh_RL` |
| `art/cars3d/roblox/red_sports_wheel_RR.glb` | 335,468 | `red_sports_wheel_RR` -> `WheelMesh_RR` |

For the Meshy comparison, the same five files are named `red_sports_meshy*.glb`. Import them with the **same**
settings as the other cars (same Scale Unit), so body and wheels share one unit.

## Studio install (edit mode, command bar, after the imports are in workspace)

1. Run the output of `python tools/gpu/car_import_wheels.py --luau art/cars3d/roblox/red_sports_wheels.json red_sports`.
   It does all of this:
   - collects the MeshParts named `red_sports` / `red_sports_wheel_*` from workspace into
     `ServerStorage.CarBodies.red_sports`, a Folder holding `Body` and `WheelMesh_FL..RR` (anchored, non-colliding);
   - sets `YawFix = 180`, `WheelRadius`, `WheelWidth`, `RimColor` and `WheelFL/FR/RL/RR`;
   - moves an older `red_sports` to `ServerStorage._old`.

   For Tripo it sets:

```lua
f:SetAttribute("YawFix", 180)
f:SetAttribute("WheelRadius", 0.3848)
f:SetAttribute("WheelWidth", 0.3875)
f:SetAttribute("RimColor", Color3.fromRGB(52, 45, 45))
f:SetAttribute("WheelFL", Vector3.new(-0.8878, -0.3235, -1.2939))
f:SetAttribute("WheelFR", Vector3.new(0.8782, -0.3229, -1.2939))
f:SetAttribute("WheelRL", Vector3.new(-0.8879, -0.3276, 1.3498))
f:SetAttribute("WheelRR", Vector3.new(0.8783, -0.3279, 1.3498))
```

2. Install the scripts from this branch (`RaceCarServer`, `PattayaTestKitServer`) the usual way
   (`tools/studio/install.ps1` + `install.luau`).
3. Nothing goes on the start grid or into the garage.

## Play test plan (leader, Studio Play)

1. Server: `local S = require(game.ServerStorage.PattayaTestKitServer).start()`, then
   `print(S.spawnCar(S.player(), "red_sports"))`. Expect `TestCar_red_sports_<id> built (body mesh yes, wheel
   meshes 4); seated ...`.
2. Parked, screenshot each side: body upright and nose forward; wheels in their arches; **rim faces outward on both
   sides** (else `WheelYawFix = 0`); no see-through arches; tyres on the ground.
3. Drive straight at 50, 100 and 150 (HUD km/h = studs/s): the top of each wheel moves forward, spin matches the
   ground speed, no wobble.
4. Full lock left and right at low speed: only the fronts turn, each about its own centre. Expect the tyre edge to
   leave the arch at full lock (QA sweeps).
5. Kerbs and a ramp landing: the wheels move with the suspension. Expect the tyre top through the wing at full bump
   (same for every car's travel).
6. Drift (Ctrl) and reverse: the wheels spin backwards in reverse.
7. Mobile perf: device emulator (low-end phone) with 1 and with 6 of these cars; compare frame time and memory with
   a grid car. Cost per car: 5 MeshParts (about 26 k tris), textures 1 x 1024² + 4 x 512².
8. Leave the car and spawn it again (`S.spawnCar` replaces it); check nothing is left behind.

## Rollback

- Remove the car: delete `ServerStorage.CarBodies.red_sports` (or move it to `_old`) and any
  `workspace.TestCar_red_sports_*`.
- Code: revert `RaceCarServer.server.luau` and `PattayaTestKitServer.luau` to `main`. Cars without `WheelMesh_*`
  behave exactly as before either way.

## Risks

- **Rights and Ferrari badges** (see above): blocker for upload.
- The importer's yaw for the wheel meshes is assumed to equal the body's (180°); one look in Play settles it.
- Brake calipers turn with the wheels (they are part of the cut).
- Tyre vs bodywork at full steer / full bump (QA sweeps). The suspension travel is the game's, shared by all cars.
- No glass in the Tripo source: the open side windows show the crude interior. The driver is hidden while seated.
- The source is 1 cm off-centre left/right; the wheels follow the real tyres.

## Fictional-brand version

Branch `team21/car-debrand` (2026-10-21). Owner decision: Blender optimisation and wheel separation are allowed
offline; **uploading or importing to Roblox stays BLOCKED until the owner confirms a licence.** There is no Ferrari
licence, so this is a fictional-make version of the Tripo car, `red_sports_fictional`. **Not in the garage, not in
CarSpecs, nothing touched in the Studio place, nothing uploaded.** This is not legal advice.

### How it was made

- Input: the optimised Tripo build above (`red_sports.glb` + 4 wheel GLBs), not the 1.9 M source. So the
  separated-wheel rig is exactly the one already checked: wheel geometry, UVs, pivots (origin = axle, axle along X),
  layout centres and radius are byte-identical; body topology and UVs are identical.
- `tools/gpu/car_debrand.py` (numpy + Pillow, local, no network):
  - `scan <dir> <id> <out.json>`: rasterises every triangle in UV space, so each texel knows its 3D body-space
    position, then lists the yellow (badge-coloured) texel clusters in 3D. This is how the marks were found in the
    fragmented Tripo atlas.
  - `apply <dir> red_sports <dir> red_sports_fictional`: repaints the marks (3D region + colour seed, grown over
    non-paint texels, filled by the inverse-distance mean of the nearest paint / trim texels), flattens the badge
    reliefs, paints the cue changes, draws the emblem, and writes the GLBs, `<id>_wheels.json`, `<id>_debrand.json`
    (numbers per mark) and `<id>_emblem.png`.
  - `pairs` / `sheet`: the before/after and turntable sheets.
- `tools/blender/car_debrand_render.py` + `run_debrand_render.sh` (GPU box, Workbench, back faces culled):
  close-ups and whole-car views from `tools/blender/debrand_views.json`.
- `tools/blender/car_glb_to_fbx.py` + `run_car_fbx.sh` (GPU box): one FBX per GLB, textures embedded, -Z forward /
  Y up, origins kept. Only the 5 GLBs, the json and the script go to the box.

### Marks found and removed

| mark | where (frame N, m) | how | proof (sheet row) |
|---|---|---|---|
| yellow shield with black horse on the nose, above the grille | (0, -0.13, -2.17) | 26 texels repainted with the surrounding paint; MP badge on top | `nose`, `grille` |
| chrome prancing horse in the grille | (0, -0.35, -2.17) | **embossed geometry**: 177 verts flattened onto a quadratic fit of the grille around it (max move 2.9 cm; the walls become zero-area, same triangle count); 92 texels repainted dark | `grille` |
| yellow shield on the left front wing | (-0.95, 0.09, -0.67) | 32 texels repainted with paint; no new badge there (the wing-shield position is itself a cue) | `fender_L` |
| right front wing (mirror position) | (0.95, 0.09, -0.67) | checked: no shield in this texture | `fender_R` |
| chrome prancing horse in the tail centre | (0, 0.08, 2.18) | small relief: 23 verts flattened (max 1.2 cm); 33 texels repainted; MP badge on top | `tail_centre` |
| yellow/orange badge on the steering-wheel boss | (-0.39, 0.12, -0.15) | 126 texels repainted dark | `steering` |
| yellow horse centre caps, all 4 wheels | wheel hub, outer face | cap repainted navy + MP disc emblem (about 26 texels across) | `hub_FL`, `wheel_FL` |
| brake calipers | | red, **no text** at this resolution (512² wheel texture); recoloured teal anyway (cue change) | `wheel_FL` |
| "Ferrari" wordmark / script | | **none found** in the body texture (tail, sides and sills checked) | `tail` |

Yellow texels on the body: 107 before, 1 after (no cluster of 4 or more). Wheel caps: 154-168 yellow texels each
before, 0 after. No brand word in any shipping file (GLB / FBX / wheels json; checked by the test). The GLB
material name is still Tripo's generic `tripo_material_<uuid>` (no brand).

### The emblem (own design)

`art/cars3d/roblox/red_sports_fictional_emblem.png`: "MP" for Midnight Pattaya. A silver twin-peak zigzag "M" (also
two waves / two peaks) on a navy field with a silver rim: a horizontal capsule on the body (nose, tail) and a disc
on the wheel caps. Generated in code (signed-distance shapes in `car_debrand.py`), not traced from any real brand. A
lozenge (Renault-like) and an oval winged M (Mazda-like) were avoided on purpose. On the body it is only 9-10
texels across (the Tripo atlas is 1024² for the whole car), so in game it reads as a small silver-navy badge, not
as letters. The wheel caps (about 26 texels) show the M.

### Changes to reduce the resemblance (the cheap and safe ones were applied)

| cue | change | kind |
|---|---|---|
| prancing horse / shields | removed (above) | texture + relief flattening |
| honeycomb grille mesh | dark horizontal slats | texture |
| four separate rounded tail-lamp pods (812 signature) | each side's twin pods painted as one dark smoked lens; one thin full-width red light bar across the tail with the MP badge in the middle | texture (the recessed pod shapes in the mesh remain, see the renders) |
| black forged 5-twin-spoke rims, yellow caps | silver finish, navy MP caps | texture (spoke geometry unchanged) |
| red calipers | teal (the fictional make's accent colour) | texture |

Not changed, because it would need remodelling the mesh (not cheap, or not safe for the rig): body silhouette,
headlight shape, bonnet vents, door scallop / side intake, tail-lamp recesses, quad exhausts and diffuser, rim
spoke geometry. The paint stays red (the owner's "red sports car"). A non-red default paint would cut the Ferrari
association further at no cost.

### Similarity assessment (honest; not legal advice)

- **Most resembles: Ferrari 812 Superfast** (front-engine V12 GT, 2017), with some 812 Competizione-style details.
  Matching signature cues:
  - long bonnet, set-back cabin, fastback proportions;
  - narrow swept headlights and a wide black grille between them;
  - the deep scallop and air outlet behind the front wheel running into the door;
  - bonnet vents;
  - **twin rounded tail lamps per side** in recesses;
  - quad exhausts either side of a finned diffuser;
  - 5 twin-spoke rims and red paint.
- **After this pass:** every logo, shield, horse and badge shape is gone (body, wheels, steering wheel). The grille
  pattern, rims, calipers and tail-lamp graphics are different. From a distance the car now reads as "a red
  Italian-style V12 GT" rather than a branded car. **Up close the body shape is still clearly 812-derived**: the
  tail-lamp recesses, the side scallop and the headlights are geometry.
- **Remaining risk: medium.** Removing logos deals with the logo-trademark problem. Car makers, Ferrari included,
  also assert rights in the shape / trade dress of their models, and an AI-generated near-copy of an 812 can still
  be challenged or moderated. To lower it further: remodel the tail (a single lamp-bar geometry), the side scallop
  and the front lamps; change the rim geometry; use a non-red default paint. Still open, independent of the brand:
  **the Tripo terms of use for a published game** (see *Licensing and badges*).
- **Upload is BLOCKED pending the owner's licence decision.** `red_sports_fictional_wheels.json` carries
  `"fictional_brand": {"upload": "BLOCKED until the owner confirms the licence"}`.

### Outputs (`art/cars3d/roblox/`, for later Roblox use only)

| file | bytes (GLB / FBX) | tris |
|---|---|---|
| `red_sports_fictional.glb` / `.fbx` | 2,097,596 / 2,143,484 | 17,801 |
| `red_sports_fictional_wheel_FL.glb` / `.fbx` | 304,388 / 332,156 | 1,979 |
| `red_sports_fictional_wheel_FR.glb` / `.fbx` | 295,532 / 323,772 | 1,980 |
| `red_sports_fictional_wheel_RL.glb` / `.fbx` | 304,640 / 330,908 | 1,980 |
| `red_sports_fictional_wheel_RR.glb` / `.fbx` | 304,160 / 332,332 | 1,978 |
| `red_sports_fictional_wheels.json` | layout: the same numbers as `red_sports`, rim colour silver (164, 168, 176) | |
| `red_sports_fictional_debrand.json`, `_fbx.json`, `_emblem.png` | per-mark numbers, FBX check, emblem | |

Textures: body 1024² + wheels 4 x 512² base colour (PNG, embedded). The FBX bounding boxes match the GLBs (body
centred on its bbox, wheel bbox centres 0.2-6 mm from the axle). If it is installed later: the same Studio snippet
as `red_sports` with the id `red_sports_fictional` (same attributes, `RimColor` from the json).

### QA images (`art/cars3d/qa/`, looked at)

- `red_sports_fictional_badges_before_after.png`: close-ups, before | after: nose, grille, both front wings, tail
  centre, whole tail, wheel hub, wheel, steering wheel.
- `red_sports_fictional_overall_before_after.png`: front 3/4, rear 3/4, side, front, rear.
- `red_sports_fictional_turntable.png`: after only: front 3/4, rear 3/4, side, front, rear, wheel, nose, tail, hub.

What I saw:

- the badges are gone everywhere;
- the nose and tail capsules are small blurred silver-navy badges (texel limit);
- the grille slats are irregular where the atlas islands are coarse;
- the tail light bar is thin and broken into segments across atlas islands (it reads as a dark-red strip, not a
  crisp LED bar), and the lamp recesses still show their twin-pod outline;
- silver rims, teal calipers and navy MP caps look clean and spin-symmetric.

### Tests

`tools/qa/tests/test_car_fictional.py` (picked up by `run_all.py`):

- wheel geometry and layout identical to `red_sports`; the body moved only inside the badge reliefs, same UVs and
  topology;
- tris: body <= 20,000, wheels <= 2,000;
- wheel bbox centre < 1 cm from the axle, axle = X, tread round about X (10° sector max-radius spread < 3 cm,
  median within 2 cm of the layout radius);
- no yellow cluster on the body, no yellow on the caps, the MP navy field present on all four caps;
- no brand words in the GLB / FBX / wheels json; upload marked BLOCKED; this section present.
