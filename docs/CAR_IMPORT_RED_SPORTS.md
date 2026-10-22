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

## Original design v2

Branch `team22/car-original` (2026-10-21). Owner decision: the fictional-brand car still reads as a Ferrari 812
Superfast, and that shape risk is not accepted. So this pass changes the **shape** cues (geometry), not only paint.
The result is a separate set, `red_sports_original_v2*`. `red_sports` (optimised Tripo) and `red_sports_fictional`
are untouched; the test checks their sha256 against the hashes the build recorded.

**Upload BLOCKED** (see *Tripo rights evidence*). Nothing was uploaded or imported. Nothing was done in Studio,
nothing went into the garage, and nothing changed under `roblox/src`. This is not legal advice.

### How it was made

| step | command / file | what |
|---|---|---|
| build | `python tools/gpu/car_original_v2.py build art/cars3d/roblox art/cars3d/roblox --source <scratchpad>\glb_in\car.glb` | numpy + Pillow, local. Input: `red_sports_fictional.glb` (geometry, badge-free texture), `red_sports.glb` (to find the texels team21 repainted) and the 57 MB Tripo source (only for its 2048² texture; kept out of the repo, sha256 `550802ba…3e13f4e`). Without `--source` it samples the 1024² build texture instead. Deterministic: a rebuild gives byte-identical GLBs |
| FBX | `<bpy venv>\python tools/blender/bpy_local.py tools/blender/car_glb_to_fbx.py -- art/cars3d/roblox red_sports_original_v2 art/cars3d/roblox --extra red_sports_original_v2_red.glb,red_sports_original_v2_white.glb` | one FBX per GLB, origins kept (`--extra` is new: more bodies that share the wheels) |
| renders | `<bpy venv>\python tools/blender/bpy_local.py tools/blender/car_debrand_render.py -- <dir> <id> <out> --views tools/blender/original_v2_views.json --tag after` | Workbench, back faces culled; views in `original_v2_views.json` |
| sheets | `python tools/gpu/car_original_v2.py grid <out.png> view1,view2 "<dir>\|<id>\|<tag>\|<label>" ...` | before/after sheets |

On 2026-10-21 the GPU box (`vast-rtx6000-1`) could not run Blender: its cgroup `cpu.max` was `1000 100000`
(1 % of one CPU), and `gslot.sh` had a Blender cap of 0. So every Blender step ran on this PC through the PyPI
`bpy` module (Blender 5.1.2 as a Python module, Python 3.13, installed in a scratchpad venv, not in the repo).
`tools/blender/bpy_local.py` runs any `blender -b -P` script that way. When the box is healthy again,
`run_debrand_render.sh` / `run_car_fbx.sh` work with these ids as before.

### What changed (812 cue -> v2)

| cue (812 / fictional) | v2 | kind |
|---|---|---|
| narrow swept-back headlights rising onto the wing | the recess is **filled**: vertices go onto a cubic surface fitted to the nose around it, with a soft 3 cm border. On top sits a **new straight lamp bar**: smoked housing, LED line, two square projectors, teal accent, 4 mm proud with side walls. A **separate vertical LED "fang"** sits at each outer bumper corner | geometry |
| deep scallop / outlet behind the front wheel running into the door | **filled** (wing surface refit, soft border, arch kept). **Three stepped horizontal gills** with a teal top edge instead | geometry |
| four round tail lamps in two twin-pod recesses (team21 only painted them) | recesses **filled flat**. **One full-width light blade** (2.2 cm) with turned-down ends | geometry |
| quad round exhausts in two outboard trapezoid housings + centre fog lamp | housings flattened into dark lower panels; tips and fog lamp collapsed. **Two rectangular outlets** inboard, between the inner diffuser fins (2.5 cm lip, 7 cm deep) | geometry |
| bonnet vents (two side slashes, centre vent) | filled | geometry |
| grille | team21's dark slats + a **body-colour blade** across the grille | geometry + texture |
| five twin-spoke rims, red calipers | **new procedural wheels**: tyre, **10-blade turbine rim**, hub cap with the MP emblem, slotted brake disc, **no caliper** (it would spin with the wheel) | new geometry |
| red paint | **midnight blue default**; red and white variants | texture |
| badges | the MP emblem (team21's own design) on a raised capsule, now in its own 224 px decal (was about 10 texels) | geometry + texture |

Vertices moved per region (from `red_sports_original_v2_build.json`): side scallop L 216 / R 304, headlight
recess L 312 / R 136, tail pods L 677 / R 590, exhaust housings L 563 / R 534, bonnet vents 43 + 16 + 196, fog lamp
87. Nothing moved between z = -0.15 and z = 1.75 (doors, cabin, rear wheels); a test checks this. The body's
bounding box is unchanged (vertices are clamped to it), because Roblox centres a MeshPart on its box and the wheel
layout depends on it. Old topology and triangle order are kept; the new parts are appended.

### Texture quality

- The Tripo atlas used only **30 %** of the 1024² image (3,992 islands). It is **re-packed**: skyline packing of
  the island bitmaps, 90° turns allowed, 2 px gutters.
  - Visible islands get **1.275x** the old texel density (1.6x the texels).
  - Islands in the cabin get 0.96x and the underside 0.57x.
  - Texels are sampled from the **2048² Tripo source** (the build had scaled it to 1024²). Texels team21 repainted
    (the badges) come from the fictional texture.
- The bottom **1024 x 128 px** of the atlas holds the new parts' graphics:
  - emblem 224 x 112 px;
  - lamp bar 512 x 48;
  - tail blade 780 x 24;
  - gills, DRL, outlet metal, trims.
- The old cue areas are repainted from the surrounding paint (inverse-distance fill in 3D). Then the paint is
  recoloured with its shading kept and lightly smoothed.
- Wheels: their own 512² texture (tyre, rim, blades, disc, a **256 px emblem cap**).
- `red_sports_original_v2_emblem.png` shows both emblem decals cut out of the shipped textures at 2x.
- Still one material and one texture per part, so the Roblox cost is unchanged: 1 x 1024² body + 1 x 512² for the
  four wheels (they share one image).

### Outputs (`art/cars3d/roblox/`)

| file | bytes GLB / FBX | tris |
|---|---|---|
| `red_sports_original_v2.glb` / `.fbx` (midnight blue, default) | 1,843,312 / 1,819,116 | 18,979 |
| `red_sports_original_v2_red.glb` / `.fbx` | 1,883,288 / 1,859,132 | 18,979 |
| `red_sports_original_v2_white.glb` / `.fbx` | 1,923,808 / 1,899,676 | 18,979 |
| `red_sports_original_v2_wheel_FL/FR/RL/RR.glb` / `.fbx` (shared by all paints; left wheels mirrored) | 89,644 / about 84,100 each | 2,120 each |
| `red_sports_original_v2_wheels.json` | layout = `red_sports` (same axle centres, radius 0.3848), rim colour (62, 66, 74), `original_v2.upload` = BLOCKED | |
| `red_sports_original_v2_build.json`, `_fbx.json`, `_emblem.png` | per-step numbers, input hashes, FBX check, emblem decals | |

Body: 17,801 old + 1,178 new = **18,979 tris** (budget 20,000). Wheels: **2,120 tris** (budget 2,500).
- Origin = axle centre, axle along X, bounding box centred on the origin (0.0 mm).
- Radius **0.3848** exactly; tread round (48 segments).
- Tyre width 0.344 m. The layout's `WheelWidth` 0.3875 only sizes the hidden cylinder.
- Hub cap outside on both sides: -X for the left wheels, +X for the right.

The FBX boxes match the GLBs.

If it is installed later:
1. Import ONE body (pick the paint) plus the four wheels. Rename the body MeshPart to `red_sports_original_v2`.
2. Run the snippet from `python tools/gpu/car_import_wheels.py --luau art/cars3d/roblox/red_sports_original_v2_wheels.json red_sports_original_v2`.

Game code is unchanged (`WheelMesh_*` path, see *Game integration*).

### QA images (`art/cars3d/qa/`, looked at)

- `red_sports_original_v2_overall_before_after.png`: front 3/4, rear 3/4, side, front, rear. Columns:
  `red_sports_fictional` (812-like) | v2 midnight blue | v2 red.
- `red_sports_original_v2_closeups_front.png`: headlight L, headlight R, nose, side intake L and R, nose emblem
  (before | after).
- `red_sports_original_v2_closeups_rear.png`: tail, tail lamp, diffuser, low rear 3/4, tail emblem.
- `red_sports_original_v2_closeups_wheel.png`: rim, rim 3/4, hub.
- `red_sports_original_v2_paints.png`: midnight blue / red / white, front 3/4, rear 3/4, side.

What I saw (faults left):

- Around the right headlight the facets of the 18 k-triangle decimated nose show as shading steps (the source lamp
  area is not symmetric); the left side is clean.
- The flattened lower outer rear panels are flat slabs. They look grey in Workbench (studio specular); the texture
  is dark.
- A small notch where the tail blade turns down at the outer ends: the corner of the old pod recess wraps round the
  body corner.
- Tripo's baked lighting is still in the texture: lighter and darker patches, most visible on white. The repainted
  areas are smooth but softer than the rest.
- Interior unchanged (no glass, roll-cage-like frame visible). The recolour also turns red interior parts blue or
  white.
- The new parts are thin shells 3-6 mm proud of the body (only the lamp bar and the DRL have side walls).
  Invisible at game distance.
- Not seen in Roblox (no import).

### Similarity reassessment (honest; not legal advice)

- **Gone:**
  - every 812 signature graphic: the swept headlights, the scallop/outlet behind the front wheel, the twin round
    tail lamps and their recesses, the quad exhausts in trapezoid housings, the fog lamp, the bonnet vents, the
    five twin-spoke rims and red calipers;
  - (team21) every badge;
  - the red default paint.
- **Remain** (geometry of the whole shell; changing them means a new body):
  - long bonnet, cabin set far back, fastback roof, short tail with a lip spoiler, wing volumes over the wheels;
  - the side-window graphic and door/shoulder lines;
  - the outline of the wide grille with the outer intakes and corner fins;
  - splitter, diffuser fins, mirrors.
- **Verdict:**
  - From the front and the rear, in the default paint, it reads as an unbranded modern GT with its own face and
    tail. Lamp bar + fangs, gills, full-width blade, inboard outlets and turbine wheels are not 812 traits.
  - In side profile the proportions are still those of the 812-like source shell. Someone who knows the car could
    still call it "812-shaped".
  - **Residual risk: low to medium**, down from medium.
  - It is not zero, because the shell is an AI-generated near-copy of a real car's body. Removing it completely
    needs a new body: own modelling, or a different base model.
  - The red variant brings some of the association back. Recommend midnight blue (or white) as the shipped paint.

### Tripo rights evidence

What the repo and docs record (searched for "Tripo" in every text file of the repo, docs and team memory; nothing
browsed, no personal data sent anywhere):

- [x] The source file says what made it: `asset.generator = "Tripo"`, node `tripo_node_<uuid>`, material
  `tripo_material_<uuid>`. It has **no licence, copyright or author field** (no `asset.copyright`, no `extras`).
- [x] Where it came from: the owner's Downloads folder, `red sports car 3d model.glb` (status notes, 2026-10-21).
  sha256 `550802ba55a78c0f826d8fb8232768c5166a31bb849c3c2d4a670c3327e13f4e`, 57,493,380 B.
- [x] This doc already says the owner must confirm the rights before any upload (owner rule 2, *Licensing and
  badges*).
- [ ] **No record** of which Tripo account or plan generated it, of the terms in force that day, of a receipt, or
  of the generation input. The only other mention is a general team note in
  `.claude/skills/game-assets/references/common/third-party-and-ip.md`: "Paid Meshy/Tripo output is owned by the
  payer". It comes from another project, it is not a copy of Tripo's terms, and it is not proof for this model.

Proof the owner still needs before the upload block can be lifted (keep copies in a private folder, outside the
repo):

1. **Plan at generation time:** the Tripo account and plan used to make this model. Screenshot of the subscription
   page plus the invoice or receipt with its date. A free plan may give different rights from a paid one, so this
   decides the rest.
2. **The terms for that plan, on that date:** a saved copy (PDF) of Tripo's terms of service / licence in force
   then. It must cover:
   - commercial use of generated models in a published, monetised game;
   - who owns the output;
   - whether outputs are public or under an open licence;
   - whether attribution is required;
   - any limits on redistribution inside a game platform like Roblox.
3. **Generation record:** the Tripo history entry (task id, date) for this model, and whether it came from a
   **text prompt or an input image**.
4. **If it came from an image:** where that image came from and the right to use it. A photo or render of a real
   car brings in that car's owner's rights, and would explain why the model looks like an 812.
5. **Same file:** confirm that the downloaded file is the one used here (sha256 above).
6. **Roblox:** the uploader warrants the rights under Roblox's terms. The owner also has to accept, separately, the
   residual **design (shape) similarity** risk above, which a Tripo licence does not cover.
7. **Written go-ahead** from the owner naming the paint variant. Until 1-7 are recorded, upload and import stay
   **BLOCKED** (`red_sports_original_v2_wheels.json` -> `original_v2.upload`).

### Tests

`tools/qa/tests/test_car_original_v2.py` (picked up by `run_all.py`):

- files, FBX and QA sheets exist;
- tris: bodies <= 20,000, wheels <= 2,500 (GLB and FBX);
- body bounding box = `red_sports_fictional`'s (1 mm); layout = `red_sports`;
- wheels:
  - bounding box centred on the axle (1 mm), axle = X, max radius = 0.3848 (1 mm);
  - round: 10° sector max-radius spread < 3 mm;
  - hub cap on the outside;
  - new geometry;
- shape edits only in their regions: none between z -0.15 and 1.75, old topology kept, tail pods and scallops really
  moved, `bbox_shift` 0;
- the new parts are listed in the build json;
- emblem decal >= 200 px with navy field and silver glyph, mapped by the emblem shells; wheel cap 256 px;
- the default and white paints have no red paint, the red variant does;
- no brand words in GLB / FBX / wheels json;
- upload BLOCKED in the json files; this section and the checklist are present;
- the inputs still match the hashes the build recorded, and no v2 file is a copy of an original.

## Own body v3

Branch `team23/car-own-body` (2026-10-22). Owner brief: v2 still reads as an 812 in side profile, so the test car
gets a **new body, modelled from scratch by our own Blender script**. No view, and above all not the side profile,
may read as a Ferrari 812. v3 is a drop-in alternative to `red_sports_original_v2`: same wheel layout, and the v2
turbine wheels are used as they are. The set is `red_sports_own_v3*`. `red_sports`, `red_sports_fictional`,
`red_sports_meshy` and every `red_sports_original_v2*` file are untouched; a test checks the sha256 of all 70
original `red_sports*` files under `art/cars3d`.

**upload BLOCKED until the owner approves.** Nothing was uploaded or imported. Nothing was done in Studio, nothing
went into the garage or `CarSpecs`, and nothing changed under `roblox/src`. This is not legal advice.

Status 2026-10-22 (after the merge): the owner allowed the upload for a test drive. The leader uploaded the body and
the four v2 wheels and filed `ServerStorage.CarBodies.red_sports_own_v3` as a test vehicle
(`docs/test_results/car_own_v3_studio.txt`). After that drive the owner asked for better headlights: see *Lamps*
below (new body GLB + three lamp meshes, game code for them). The `upload` field in the json files still reads
BLOCKED; that wording is the leader's call.

### How it was made

Sources: none. No Tripo, Meshy or other AI mesh, no texture from them, no photo or reference image, no downloaded
model. Every vertex and every texel comes from the numbers and functions in `tools/blender/car_own_v3.py`. The MP
emblem is the v2 decal (same drawing code; team21's own design). The wheels are the v2 wheels (team22's script).

1. **Control cage:** 17 cross-sections (`RINGS`) x 12 points per half section, mirrored. A quad grid closes the
   nose; the tail ring stays open.
2. **Subdivision:** Catmull-Clark, 2 levels, with edge creases where a line must stay sharp: the floor edge, the
   Kamm tail edge, the shoulder character line, the roof and rear-window edges, the buttresses. Then one flat face
   closes the tail (constrained Delaunay triangulation). Flat floor faces are merged to save triangles.
3. **Size:** centred on its bounding box (Roblox centres a MeshPart on its box) and given red_sports' exact length,
   4.50145 m (the game scales every body to 16 studs by its length).
4. **Exact booleans at the red_sports wheel layout:** four wheel tubs (front radius 0.445 m, rear 0.43 m), two side
   intakes ahead of the rear wheels, two exhaust pockets, two lamp pockets in the nose face (*Lamps*). The body
   stays one closed shell.
5. **30 detail parts**, each a closed solid sunk into the body: the lamp back plates and four projector rings (in
   the lamp pockets), two fang housings, the tail light housing (a bar and two end blocks), three stepped gills per
   side, mirrors on arms, outlet rims, four diffuser fins, the splitter, two MP emblems. The surfaces that give
   light are three separate meshes (*Lamps*). Before the lamp polish: 24 parts (thin lamp bars, fangs, a tail
   blade).
6. **Normals and UVs:** smooth by angle (32 degrees), so only creases and part edges are sharp. Own box-projection
   UVs; left and right share texels; 226.5 px per metre on the visible body.
7. **Texture:** one procedural 1024² image per paint: paint with soft shading, dark glass, black roof and pillars,
   panel gaps, deck and nose vents, the intake mesh. A 1024 x 128 strip holds the lamp, blade, gill and emblem
   graphics. One material, one texture.
8. **Own GLB writer** (generator `MIDNIGHT PATTAYA tools/blender/car_own_v3.py`, no timestamps, sorted JSON).

| step | command | notes |
|---|---|---|
| build | `<bpy venv>\python tools/blender/bpy_local.py tools/blender/car_own_v3.py -- build art/cars3d/roblox` | this PC, PyPI bpy 5.1.2, 12 s. Box: `bash tools/blender/run_own_v3.sh build <dir>` |
| FBX | `... car_own_v3.py -- fbx art/cars3d/roblox` | this PC, 2 s |
| QA numbers | `python tools/gpu/car_own_v3_qa.py silhouette art/cars3d/roblox art/cars3d/qa`, then `clearance art/cars3d/roblox` and `shells art/cars3d/roblox` | numpy + Pillow. Writes `red_sports_own_v3_qa.json`; each section carries the sha256 of the GLB it measured |
| renders | `... car_own_v3.py -- render <dir> <id> <out> <tag> --views tools/blender/own_v3_views.json [--engine workbench\|eevee\|cycles] [--steer 28] [--wheels <json>]` | Workbench on this PC (light). Box: `bash tools/blender/run_own_v3.sh render <dir> <id> <out> <tag> <views> cycles 900` |
| sheets | `python tools/gpu/car_own_v3_qa.py grid <out.png> view1,view2 "<dir>\|<id>\|<tag>\|<label>" ...` | one row per view, one column per car |

Deterministic: two builds on this PC gave byte-identical GLBs, PNG and json files. On the GPU box
(Blender 5.2.2) two builds were byte-identical too. Box against this PC: the same positions, triangles, UVs and
texture; normals differ by less than 1e-16, so the GLB bytes differ.
The official build is the one from this PC (bpy 5.1.2, recorded in `_build.json`), so anyone with the repo venv
can rebuild it byte for byte.

### Design: why this shape

A **cab-forward mid-engine GT with a long tail and a flat Kamm face.** Each 812 cue from the v2 review:

| 812 cue | v3 | measured (vs `red_sports_fictional`) |
|---|---|---|
| long bonnet | short, low front deck: the windscreen starts about 0.25 m behind the front axle line (fictional: about 0.5 m) | windscreen base z about -1.0 m (fictional about -0.8 m) |
| cabin set far back | cab-forward canopy, then a long engine deck | cabin (side outline above 0.45 m) z -0.74 to 0.83 m, fictional -0.41 to 1.33 m: its middle is 0.42 m further forward. Roof peak 0.54 m further forward |
| fastback roof | short canopy, steep rear window between two sail-panel buttresses, then a long flat engine deck with two vents | roofline 10 to 15 cm lower from z 0.25 to 1.0 m |
| short tail with a lip spoiler | long tail, tall flat Kamm face, no spoiler | tail end 50 cm higher |
| side-window graphic | dark visor canopy: black roof and A-pillars, side glass with a pointed front and a vertical rear edge, body-colour sail panel behind it | |
| door and shoulder lines | one sharp shoulder crease from the nose corner to the tail, kicking up over the rear haunch; the doors are tucked in under it | |
| wide grille outline | no grille shape: a slim dark mouth between two straight lamp bars on a sloped nose face; a flat splitter with a teal edge | |
| wing volumes over the wheels | low round front fenders; wide rear haunches that run into the buttresses; a meshed side intake ahead of the rear wheel | |

Kept from the v2 "MP" language: straight lamp bars, vertical LED fangs, stepped gills (behind the front wheel,
raised, teal top edge), the full-width rear light blade with turned-down ends, inboard rectangular outlets, the MP
emblem on the nose and the tail, the v2 turbine wheels.

Top view (the top-down camera): dark canopy in the middle, a low front deck with two small vent groups, two long
four-slot vents in the engine deck, a square tail.

### Numbers

- **Triangles:** body shell 12,376 + 30 parts 3,136 = **15,512** (budget 20,000); 11,383 vertices. The FBX files
  have the same count. Before the lamp polish: 11,924 + 2,128 = 14,052. The three lamp meshes add 892 (*Lamps*).
- **Bounding box:** **2.2085 x 1.2200 x 4.5014 m** (X x Y x Z), centred (0.0 mm). red_sports: 2.2067 x 1.2552 x
  4.5014. Width +0.1 %, height -2.8 %, length equal.
- Frame and units as v2: X right, Y up, front -Z, metres, origin = centre of the body bounding box.
- **Wheel layout = `red_sports`** (axle centres, radius 0.3848, track). Wheels: `red_sports_original_v2_wheel_*.glb`.
- **Tyre clearance** (closed cylinder round the v2 tyre, radius 0.3848 m, width 0.344 m):

| wheel | at rest | free bump travel | worst over steering -28 to +28 degrees |
|---|---|---|---|
| FL | 5.9 cm | 6.0 cm | 2.25 cm (at full lock) |
| FR | 5.9 cm | 5.9 cm | 2.26 cm (at 24 degrees; 2.28 cm at full lock) |
| RL | 4.4 cm | 4.4 cm | - |
| RR | 4.4 cm | 4.5 cm | - |

  The same check on `red_sports_fictional` and v2 gives -13 to -15 cm: their tyres sit inside the body shell (no
  real wheel tubs).
- **Closed shells:** 31 (body + 30 parts), 0 open edges, 0 duplicate edges, all wound outward. Opaque, single-sided
  material; no interior. The lamp meshes are closed outward shells too (6 + 4 + 3 components).
- **Silhouettes vs `red_sports_fictional`** (5 mm pixels, body meshes only):
  - side IoU **0.857**; **0.890** with the fictional's see-through window holes filled. v2: 0.997;
  - top IoU **0.947**. v2: 0.990;
  - roofline: mean difference 7.9 cm; more than 5 cm apart along 60 % of the length.

### Outputs (`art/cars3d/roblox/`)

| file | bytes GLB / FBX | tris |
|---|---|---|
| `red_sports_own_v3.glb` / `.fbx` (midnight blue, default) | 596,776 / 597,708 | 15,512 |
| `red_sports_own_v3_red.glb` / `.fbx` | 597,688 / 598,668 | 15,512 |
| `red_sports_own_v3_white.glb` / `.fbx` | 601,876 / 602,876 | 15,512 |
| `red_sports_own_v3_lamp_head.glb` / `.fbx` (LampMesh_Head) | 20,220 / 28,956 | 408 |
| `red_sports_own_v3_lamp_drl.glb` / `.fbx` (LampMesh_DRL) | 14,736 / 25,548 | 272 |
| `red_sports_own_v3_lamp_tail.glb` / `.fbx` (LampMesh_Tail) | 10,952 / 20,076 | 212 |
| `red_sports_own_v3_lamps.json` | lamp meshes (offset, size, tris, sha256, day look) and anchors, body metres | |
| `red_sports_own_v3_wheels.json` | layout = `red_sports`; `wheel_meshes` = the v2 wheels; `own_v3.upload` = BLOCKED | |
| `red_sports_own_v3_build.json` | script sha256, Blender version, box, tris, atlas, paints with sha256 | |
| `red_sports_own_v3_qa.json` | silhouette, clearance, shells | |
| `red_sports_own_v3_emblem.png`, `_fbx.json` | the MP decal as shipped (2x); FBX check | |

Roblox cost: one MeshPart of 15.5 k tris with one 1024² texture (v2: 19 k tris, one 1024²), plus three small
untextured lamp MeshParts (892 tris in all). Wheels as v2.

If the owner approves it later:
1. Import ONE body (pick the paint) and the four v2 wheel files. Rename the body MeshPart to `red_sports_own_v3`.
2. Run the snippet from `python tools/gpu/car_import_wheels.py --luau art/cars3d/roblox/red_sports_own_v3_wheels.json red_sports_own_v3`.
   The snippet now also takes wheel parts named after the car whose wheel files the json lists (here
   `red_sports_original_v2_wheel_FL` ...), because v3 has no wheel files of its own. For every other car the snippet
   is unchanged (checked: the v2 snippet is byte-identical).

Game code: the `WheelMesh_*` path (see *Game integration*) and, since the lamp polish, the `LampMesh_*` path
(*Lamps*).

### QA images (`art/cars3d/qa/`, looked at)

These sheets show the body before the lamp polish (`red_sports_own_v3_silhouette.png` is re-made for the current
body). The lamp renders are in `art/car_own_v3_lamps/` (*Lamps*).

- `red_sports_own_v3_compare.png`: `red_sports_fictional` | v2 | v3 in side, front 3/4, rear 3/4, front, rear,
  top and the game's chase camera (Workbench, the same studio light for all three).
- `red_sports_own_v3_silhouette.png`: side and top silhouettes of v3 (blue) over the fictional body (red), with the
  IoU and roofline numbers.
- `red_sports_own_v3_clearance.png`: steering -28 degrees / at rest / +28 degrees: top view, from below, front-left,
  front-right and rear-left arch (Workbench), labelled with the gaps.
- `red_sports_own_v3_closeups.png`: nose, lamp bar, fang, nose emblem, gills, front arch, side intake, tail, tail
  lamp, tail emblem, outlets. Left Cycles (sky and sun), right Workbench (flat light: the texture as painted).
- `red_sports_own_v3_paints.png`: midnight blue / red / white in front 3/4, rear 3/4, side, top and chase camera
  (Cycles).
- `red_sports_own_v3_looks.png`: v2 | v3 under the same Cycles light: front 3/4, rear 3/4, side, top, chase camera
  straight behind and from 30 degrees.

The box GPU was busy each time I checked (another project's Hunyuan job held 28 of its 32 GB), so `gslot.sh`
gave Blender no GPU slot. The "look" renders use Cycles on a CPU slot (`gslot.sh --cpu`) instead of EEVEE.

What I saw (faults left):

- Workbench shows the nose mouth and the lower tail as grey bands: studio specular on a dark texture. Cycles shows
  them dark.
- The lamp bars (about 4 cm tall) and the fangs (2 cm wide) are thin. At game distance they read as lines, not as
  big lamps. (Fixed by the lamp polish, *Lamps*.)
- The mouth slats are about 5 texels apart, so they are soft up close.
- The flanks are big plain paint areas. The deck and nose vents are painted, not cut, so they have no depth up close.
- On the red paint the red light blade has little contrast.
- At full lock the front tyres stick out past the body in the top view. That is normal; they never touch the body.
- Not seen in Roblox (no import).

### Similarity assessment (honest; not legal advice)

- **Gone:** all eight 812 cues from the v2 review (table above). The side profile is a cab-forward mid-engine
  shape with a Kamm tail; the 812 is a front-engine, long-bonnet fastback. The canopy, the tail and the top view
  are new.
- **Measured:** side silhouette IoU against the fictional body 0.857 (0.890 with its window holes filled); v2
  scores 0.997. The roofline differs by more than 5 cm along 60 % of the length. The roof peak is 0.54 m further
  forward.
- **Still the same, by design:** wheel positions, wheelbase, track and length, and so the overhangs (the drop-in
  rule). Every car on this layout shares them. The front fenders stand at about the height of the fictional's
  bonnet (within 2.5 cm between z -1.75 and -1.0 m).
- **Other cars:** v3 belongs to the 1990s mid-engine supercar genre: long tail, cab-forward canopy, a side intake
  ahead of the rear wheel, a slotted engine cover. It was not modelled on any car, and no reference image was used.
  I know of no single car it copies, but people may see a family likeness to cars of that era. It has none of the
  signature graphics I know from them (no oval mouth, no pop-up lamps, no side strakes, no big rear wing). Not
  checked against design registrations.
- **Verdict:** I cannot see the 812 in any view. Residual 812 shape risk: **very low** (v2: low to medium). General
  shape risk: low (generic genre traits only). This is not legal advice.

### Looks (honest)

Compared with v2 under the same Cycles light (`red_sports_own_v3_looks.png`):

- **Better than v2:**
  - clean, smooth surfaces and crisp creases. v2 shows Tripo's lumpy bonnet, dents and baked light patches;
  - real wheel tubs: the tyres sit in open arches, with room to steer;
  - a strong, simple silhouette and a clear rear graphic at the chase camera: light blade, emblem, twin outlets,
    slotted engine cover;
  - 14 k instead of 19 k tris, closed shells, and a texture that is entirely ours.
- **Worse than v2:**
  - much less detail: big plain flanks, painted vents, thin lamps (since fixed, *Lamps*), a simple nose. Up close it
    looks plainer and less expensive than v2;
  - the style is retro. It reads as a 1990s concept car, a bit toy-like, more than a modern GT;
  - v2's rear (diffuser, layered bumper) gives the chase camera more to look at.
- **Plainly:** up close v3 looks simpler than v2, and to many eyes worse. At game distance it reads cleaner and is
  at least as good. It is the only one of the two that is not 812-shaped.

### Lamps (team23/car-lamps, 2026-10-22)

The owner after the first drive (night, Studio Play): "ล้อเริ่มดูดีแล้ว แต่ไฟหน้ายังเป็นอะไรก็ไม่รู้ ลองดูหน่อย
เก็บรายละเอียด" (the wheels look good now, but the headlights still look like I-don't-know-what; take a look and
polish the details).

**What was wrong.**

- The two big white discs in front of the nose were not the car. `PattayaNightLights` (section 4) put the same
  generic BillboardGui flares on every RaceCar at night, at positions made for the old placeholder box car.
  - Head flares: hard round discs, 1.3 studs wide, 15 % transparent, at chassis (±2.7, 0.9, -7.6). That is about
    1.4 studs above v3's lamps, in the air in front of the hood.
  - Tail flares: at (±2.7, 1.1, 7.6), on top of the rear deck.
- v3's own lamps were thin painted strips (lamp bar 3.8 cm tall, fang 1.8 cm wide) that never lit up.

**The new lamps** keep the v3 language (straight lamp bars, LED fangs, a full-width tail light). Each is modelled in
`tools/blender/car_own_v3.py` (section "the lamps"):

- **Headlamp**, one per side, 50 x 9 cm, `|x|` 0.335 to 0.835 m:
  - a pocket cut 2.5 cm into the nose face (exact boolean, like the wheel tubs), with black walls;
  - a smoked back plate with fine reflector ribs and the teal accent line along the bottom edge;
  - two projector modules: a chrome reflector ring and a domed lens, 4.6 cm across;
  - a slim LED module, 10 x 2.2 cm;
  - a DRL light guide, 46 x 1.4 cm, along the top edge;
  - a chamfered outer tip: the bottom edge rises 4.6 cm over the last 10 cm.
- **Fang**: the LED fang below the tip stays, now a dark housing with the LED standing 3 mm proud of it.
- **Mouth**: the grille texture under the nose is 1.8 cm lower, so 2 cm of paint separates it from the lamps.
- **Tail**: a smoked housing on the Kamm face. It is a 5 cm bar plus two end blocks (14.5 x 19.5 cm, inner foot
  chamfered at 45 degrees). It holds a 1.85 cm light bar across the car and two solid end lamps.
- **Open lamps, no clear cover.** A see-through cover in Roblox would be one more transparent part (sorting, cost)
  and would wash out the detail. The domed lenses give the lens read.

**The lamp meshes.** The surfaces that give light are not in the body. They are three separate GLBs (+ FBX):

- untextured: one material each, the colour is set in Roblox, so no paint changes them;
- each centred on its own bounding box (Roblox centres a MeshPart on it), with that centre in body space as its
  offset;
- closed outward shells.

| mesh (Roblox name) | what lights | tris | size (m) | offset (m, body space) | day (installer) | night (client) |
|---|---|---|---|---|---|---|
| `red_sports_own_v3_lamp_head.glb` (`LampMesh_Head`) | 4 projector lenses, 2 LED modules | 408 | 1.3975 x 0.0481 x 0.0373 | (0, -0.227917, -2.151337) | SmoothPlastic 214, 220, 230 | Neon, the preset's head colour (MidnightClear 255, 241, 222) |
| `red_sports_own_v3_lamp_drl.glb` (`LampMesh_DRL`) | 2 DRL light guides, 2 fangs | 272 | 1.6261 x 0.1525 x 0.0714 | (0, -0.25322, -2.135295) | **Neon** 196, 210, 228: daytime running lights | Neon 226, 236, 255 |
| `red_sports_own_v3_lamp_tail.glb` (`LampMesh_Tail`) | light bar, 2 end lamps | 212 | 1.922 x 0.167 x 0.0075 | (0, 0.1025, 2.246474) | SmoothPlastic 128, 12, 20 | Neon 170, 14, 20; braking 255, 36, 40 |

The DRL glowing by day is a design call. If the owner does not want it, set `Material = SmoothPlastic` on
`CarBodies.red_sports_own_v3.LampMesh_DRL`.

**Anchors** (`red_sports_own_v3_lamps.json`; positions in body metres; directions turned 8 degrees outward):

| anchor | body metres | chassis studs | looks | where |
|---|---|---|---|---|
| HeadL / HeadR | (-/+0.466, -0.217, -2.204) | (-/+1.66, -0.49, -7.83) | forward | between the two projectors, 3 cm in front of the nose |
| TailL / TailR | (-/+0.900, 0.095, 2.290) | (-/+3.20, 0.62, 8.14) | back | on the end lamps, 4 cm behind them |

Chassis studs use s = 3.554 and the body offset +0.277. For comparison, the old head flares were at
(±2.7, 0.9, -7.6). The JSON also lists the beam: one spot between the head anchors, 8 degrees down; the game works
it out from the head anchors.

**Game integration.**

- **`RaceCarServer`**:
  - `bodyMeshOf` skips `LampMesh_*` (as it skips `WheelMesh_*`).
  - `attachLamps` clones every `LampMesh_*` that has a `BodyOffset` and scales it by the body's s. Its CFrame is
    `chassis * (0, bodyOffset, 0) * (BodyOffset * s) * YawFix` (`LampYawFix` overrides `YawFix`).
  - Each clone is welded to the chassis: Massless, CanCollide / CanQuery / CanTouch false, CastShadow false (like the
    wheel meshes).
  - The folder's `LampHeadL/R`, `LampTailL/R` (with `LampHeadDir`, `LampTailDir`) become Attachments
    `LampAnchor_<name>` on the **Body** MeshPart, never on the chassis: the parked-car spring at the bottom of
    `RaceCarServer` treats every chassis Attachment as a wheel mount.
  - Bodies without lamp data: nothing changes.
- **`PattayaNightLights`** section 4. When a car's Body has all four anchors:
  - the lamp meshes turn Neon in the night colours. This is local only, and the meshes get their own look back by
    day, when the car leaves the nearest 8, or on a preset change;
  - one small, soft glare sits on each lamp: three stacked rounds (head: halo 1.15 x 0.7 studs at 90 %
    transparency, then mid and core; tail 0.8 x 0.9). It fades when the lamp faces away from the camera: full
    within about 45 degrees of its axis, gone beyond about 95. The size is written only when the rounded value
    changes;
  - the beam SpotLight sits between the real headlamps, 8 degrees down (brightness, range and angle as before);
  - the faint tail glow sits between the end lamps;
  - the tail lamps and their glare brighten while `DriveSeat.ThrottleFloat < -0.1` (braking or reversing; the seat
    is only read).
  - Every other car keeps the generic lights exactly as before.
- **Studio installer**: `car_import_wheels.py --luau` reads `lamps` from the wheels json. It then:
  - takes the MeshParts named `<id>_lamp_<head|drl|tail>` and files them as `LampMesh_*`;
  - sets `BodyOffset`, the day look and CastShadow false;
  - removes any SurfaceAppearance and clears TextureID;
  - warns on a missing lamp or a size more than 2 % off;
  - sets the six anchor attributes.
  - The snippets of cars without lamps are byte-identical to before (`red_sports`, v2).

**Own-design check** (my knowledge of production lamp signatures; not a registered-design search, not legal advice).
Not used:

- Ferrari 812 / F12: long swept lamps on the fender tops, round twin tail lamps. Ours are short horizontal slots on
  the nose face, and the tail has no round lamps.
- Lamborghini: Y or hexagon graphics. Ours are straight lines, round lenses and one 45-degree chamfer.
- Porsche: 4-point LED DRL and brake lights, the lettered light bar. Audi: segmented DRL / tail signatures. Ours
  have no dot clusters and no lettering.
- McLaren: the hockey-stick / eye-socket DRL. Our DRL brow is straight, with no hook.
- BMW: lit "angel eye" rings. Our rings are unlit chrome; only the lenses light.
- Peugeot: long sabre-tooth DRLs running from the lamp into the bumper, claw-mark tail lamps. Our fang is a short
  8 cm tick below the lamp tip with a 2.3 cm gap; it is v2/v3's own fang.
- Lexus: the L-shaped arrowhead DRL. The fang and the brow do not join.
- Acura Jewel Eye (a row of five lenses), Hyundai parametric pixels, Volvo "Thor's hammer", Kia "tiger nose".
- Ford Mustang tri-bar tail lamps, Dodge racetrack ring. Our end lamps are solid and the ⊓ is open at the bottom.

A full-width light bar plus a lens-and-DRL headlamp is generic today.

**Install** (leader, Studio edit mode, after a fresh owner backup):

1. Upload four Model assets, as for v3:
   - `art/cars3d/roblox/red_sports_own_v3.glb` (new body, midnight blue; replaces 90094845763929);
   - `red_sports_own_v3_lamp_head.glb`, `red_sports_own_v3_lamp_drl.glb`, `red_sports_own_v3_lamp_tail.glb`.

   The wheels do not change: FL 134630398494002, FR 74871958760739, RL 121469048851077, RR 86681611253418.
2. Load the eight assets into workspace. Each should be one MeshPart named `red_sports_own_v3`,
   `red_sports_original_v2_wheel_FL` .. `_RR`, or `red_sports_own_v3_lamp_head` / `_drl` / `_tail` (rename if
   needed).
3. Run the snippet from `python tools/gpu/car_import_wheels.py --luau
   art/cars3d/roblox/red_sports_own_v3_wheels.json red_sports_own_v3` in the command bar.
   - The old folder moves to `ServerStorage._old` (rollback).
   - The new `CarBodies.red_sports_own_v3` has Body, `WheelMesh_FL/FR/RL/RR` and `LampMesh_Head/DRL/Tail` (each
     with `BodyOffset`).
   - Its attributes: YawFix 180, the wheel layout, `LampHeadL/R`, `LampTailL/R`, `LampHeadDir`, `LampTailDir`.
4. Set `TestVehicleOnly = true` and `AssetIds` again (the old folder in `_old` still has them).
5. Install `ServerScriptService.RaceCarServer` and `StarterPlayer.StarterPlayerScripts.PattayaNightLights` from this
   branch. Back up the old sources first.
6. Test in Play with `S.spawnCar(player, "red_sports_own_v3")`.
   - The car has `LampMesh_*` (massless, no collision / query / touch) and `Body.LampAnchor_*`. The Chassis still
     has only the four `Mount_*` Attachments.
   - At night (ClockTime 21): the lamps are lit, the glare sits on them, the beam comes from the nose, and the
     glare is gone from the side and the rear. Braking (S) brightens the tail.
   - By day: the DRL glows, the lenses are pale, the tail is dark red.
   - The other cars keep their old lights.

**Renders** (`art/car_own_v3_lamps/`, from the GPU box: EEVEE on a GPU slot through `gslot.sh`, 960 px; same light
before and after):

- `red_sports_own_v3_lamps_front34_old_vs_new.png`: before / after, front 3/4 by day (game-like camera and
  orthographic).
- `red_sports_own_v3_lamps_headlamp_closeup.png`: one headlamp before (day) / after (day) / after (night).
- `red_sports_own_v3_lamps_rear34_old_vs_new.png`: rear 3/4 and the tail lamp, before / after, by day.
- `red_sports_own_v3_lamps_night_front34.png`, `..._night_rear34.png`: night set (dark sky, a warm street lamp, the
  beam spot), lamp meshes emissive, compositor bloom. Run with `bash tools/blender/run_own_v3.sh render
  art/cars3d/roblox red_sports_own_v3 <out> night tools/blender/own_v3_lamp_views.json eevee 960 0 night`.

**Not verified** (no Studio here):

- How Roblox imports the untextured, very thin lamp GLBs. The tail mesh is 7.5 mm deep; the snippet warns if a size
  is off.
- How Neon and bloom look in the place, and the exact glare look: BillboardGui depth and size.
- The day DRL glow at Roblox daylight.
- The server and client code compiles (luau-compile) and the placement math is tested offline. Nothing has run in
  Roblox yet.

### Owner decisions

1. Accept the v3 shape (cab-forward, long Kamm tail) for the test car, keep v2, or ask for changes.
2. Pick the paint to ship: midnight blue (default), red or white.
3. Lift the upload block for v3, or not. The body and its texture come only from our script; the wheels are v2's
   own procedural wheels; the emblem is team21's design. No Tripo rights question applies to v3.
4. Garage and `CarSpecs`: nothing was changed. Adding v3 is a separate step after 1 to 3.

### Tests

`tools/qa/tests/test_car_own_v3.py` (picked up by `run_all.py`):

- the files, the FBX files and the six QA sheets exist;
- tris <= 20,000 (and >= 8,000) per body; FBX count = GLB count;
- one mesh, one material, one 1024² texture per body; opaque, single-sided; the paints share one geometry;
- layout = `red_sports`; wheels, width, rim and per-wheel data = v2; the script's layout constants match;
- box centred (0.1 mm), length = red_sports (0.1 mm), every axis within 5 % of red_sports;
- tyre clearance recomputed: at rest > 3 cm, bump travel > 3 cm, steering > 1.5 cm, and equal to the stored numbers;
- closed shells (no open or duplicate edges, all outward);
- generator = our script; the GLBs are the build output of the committed script (sha256);
- no vertex position and no texture tile shared with the Tripo, Meshy, fictional or v2 files;
- the emblem PNG is the shipped decal and matches the v2 MP decal;
- default and white paints have no red, the red variant does;
- no brand or AI-service words in our GLB / FBX / json files;
- upload BLOCKED in the json files and here; nothing under `roblox/src` names v3;
- the Studio snippet for v3 also takes the v2 wheel part names; the v2 snippet is unchanged;
- side and top silhouettes differ from the fictional (thresholds on the stored IoU numbers);
- all 70 original `red_sports*` files still have their main-branch sha256, and no v3 file is a copy of one;
- lamps:
  - the three lamp meshes are untextured, closed, centred on their own box, under 2,000 tris, and one set for all
    paints;
  - their offsets put them on the nose (inside the pockets' range) and on the tail, inside the body box and mirrored;
  - the anchors sit on the lamps and look out of the car;
  - the lamp GLBs are the build output (sha256 in `_build.json` and `_lamps.json`);
  - the snippet files the lamps and sets the anchors; the snippets of cars without lamps do not mention lamps;
  - the owner renders exist.

`tools/qa/tests/test_car_lamps.py`:

- `RaceCarServer`: `LampMesh_*` is never the body. The lamp clones are made like the wheel meshes (massless, no
  collision / query / touch, welded). The anchors go on the Body, never on the chassis. The driving setup is
  unchanged.
- `PattayaNightLights`: the lamp path needs all four anchors, and the generic lights stay verbatim for every other
  car. The glare is soft and small, the meshes get their look back, and the seat is only read.
- Placement maths with the real numbers (numpy CFrame algebra, Roblox import = 180-degree yaw + box centring):
  every lamp vertex lands exactly where the same point of the body lands. The head anchors sit about 1.4 studs
  below the old generic flares.
