# Car import: red_sports (owner's "red sports car 3d model.glb")

Branch `team19/car-import`. Status: **offline only. Nothing uploaded, nothing imported, nothing run in Roblox.**
Every in-game behaviour below is a prediction until the leader runs the Play test plan.

## Owner rules for this car (2026-10-21)

1. Originals untouched, outputs separate (see *Source file*).
2. **No upload and no import to Roblox until the owner confirms usage rights** (see *Licensing*).
3. **Not in the garage, not in CarSpecs, not available to players.** It is a test vehicle only: spawned by the
   TestKit (`S.spawnCar`), removable (see *Rollback*).
4. QA checks: alignment, steering pivot, suspension clearance, spin axis/direction, triangles, textures, collision.

## Licensing (owner must confirm)

The file says `"generator": "Tripo"`: the mesh and texture were produced by the Tripo AI service and downloaded by the
owner. **The owner must confirm they have the rights to use it in a published Roblox game** (Tripo plan / terms
for commercial use). Also: the texture carries **car-maker badges** (a prancing-horse shield on the nose and
tail, yellow wheel centre caps; the body shape reads as a Ferrari 812-style GT). A real brand's logo in a Roblox
game is a trademark / moderation risk even when the mesh licence is fine. This branch does **not** remove the
badges (the owner decides); if wanted, paint them over in the 1024 atlas before upload.

## Source file

| | |
|---|---|
| path (leader's machine) | `C:\Users\src3r\AppData\Local\Temp\claude\D--ROBLOXRACE\13fa2bc9-cdf0-4f9f-857d-7126dc2df433\scratchpad\glb_in\car.glb` (copy of the owner's download) |
| sha256 | `550802ba55a78c0f826d8fb8232768c5166a31bb849c3c2d4a670c3327e13f4e` |
| size | 57,493,380 bytes (too big for git: not committed, no `art/cars3d/source/` copy) |
| content | glTF 2.0, generator Tripo, 1 node, 1 mesh, 1 material, 1 embedded JPEG 2048x2048, 1,039,893 vertices, **1,943,102 triangles**, bbox x ±0.2405, y 0..0.2912, z ±0.4902 |

## Status of the outputs (read first)

**The GPU box `vast-rtx6000-1` refused every ssh connection for the whole session (port 53158, "Connection
refused", polled for about 75 minutes).** Blender only runs there, so the Blender step has **not run yet**:

- written and checked (compile / syntax): the Blender script, the measuring script, the run script, the game code,
  the TestKit path, the install-snippet generator;
- measured locally (numpy, no Blender): front direction, the four wheel cylinders, and a dry run of the cut
  (point-splat pictures of the cut-out wheel and of the body without wheels, see *Wheel detection*);
- **not produced yet:** `art/cars3d/roblox/red_sports*.glb`, `red_sports_wheels.json`, `qa/red_sports_*.png`,
  `red_sports_qa.json`, and so every triangle count, texture size and clearance number after decimation.

One command produces all of them once the box is back (Git Bash, repo root):

```
bash tools/blender/run_import_car.sh "<path to car.glb>" build/car_import/red_sports red_sports
```

It sends only the GLB and the two scripts, runs `car_import_wheels.py`, then `import_car.py build` and
`import_car.py qa` through `gslot.sh` with `--python-exit-code 1`, under `/root/robloxrace/car_import`, and fetches
everything into `build/car_import/red_sports/` (gitignored). Then copy the files in *Upload list* into
`art/cars3d/roblox/` (each must be < 5 MB; expected about 1.5-2.5 MB body, 0.3-0.6 MB per wheel) and the QA PNGs
into `art/cars3d/roblox/qa/`, look at the PNGs, and fill in *Results*. **Nothing in the "measured" column has been
run.**

## Pipeline

| step | file | what |
|---|---|---|
| 1 measure | `tools/gpu/car_import_wheels.py` (numpy + Pillow, local or box) | reads the GLB, decides the front, maps to frame N (X right, Y up, **front -Z**, metres, length 4.5 m like the other cars, centred on the bbox), finds the 4 wheel cylinders, writes `<id>_detect.json`; `--views DIR` writes end-on point splats; `--luau <id>_wheels.json` prints the Studio install snippet |
| 2 build | `tools/blender/import_car.py -- build` | imports, moves into frame N, cuts every face whose 3 vertices are inside a wheel cylinder (radius 1.03 r, across x_in-3 cm .. x_out+3 cm; body-paint fragments of the arch lip beyond 0.95 r stay on the body); each wheel gets its origin on the axle (x = bbox middle, so the Roblox MeshPart centre is the axle), a dark cap closing the tyre back, Decimate collapse to <= 2,000 tris, and its own 512x512 texture (Cycles EMIT bake onto new smart-project UVs); the body gets a dark double-sided disc (radius 1.3 r, clipped 0.55 r below the axle) 6 cm inside each wheel so the arch is not see-through, Decimate collapse to <= 18,000 tris keeping UVs, atlas 2048 -> 1024 PNG, centred on its own bbox; exports 5 GLBs + `_wheels.json` + `_build.json` |
| 2' build_parts | `import_car.py -- build_parts <body.glb> <wheel.glb> <parts.json> <out>` | for a **separate body + one wheel** (e.g. new Meshy files): body to frame N; the wheel's thinnest bbox axis turned onto X, scaled to `radius`, outer face to -X, exported once as `<id>_wheel_L` (the game turns it 180 deg for the right side); wheel centres come from `parts.json` (schema in the script header). Not tried on real input yet. |
| 3 qa | `import_car.py -- qa <out> <qa> --src <in.glb> <detect.json>` | renders + `<id>_qa.json` (checks below) |
| run | `tools/blender/run_import_car.sh` | local -> box -> local |

## How the front was decided

The source is length-along-Z with no stated front. Three independent signs all say **source +Z = front**:

1. **Lamps in the texture.** Atlas colours over the end 6 % of the length (mid-height band): light grey/white
   lamp/chrome pixels are 1.46 % at +Z and 0.21 % at -Z (7x). Saturated-red pixels are no use on a red car (13 % vs
   10 %: the paint swamps the tail lamps).
2. **End-on pictures** (`--views` splats, looked at): the +Z end shows two swept headlight clusters, the grille and
   the front intakes; the -Z end shows four round red tail lamps, a diffuser and quad exhausts.
3. **Roof-line profile.** The +Z end is the low end (0.132 vs 0.215 source units): bonnet sloping to the nose
   against a high rear deck.

So the pipeline turns the source 180 deg about Y (front +Z -> -Z) before scaling. `car_import_wheels.py` warns if
the lamp vote and the profile vote disagree; `--front` overrides.

## Wheel detection (frame N, metres, relative to the bbox of the WHOLE source car; measured locally)

Ground-contact run + arc fit per axle (the `export_car.py` method), then radius from the tread under the axle and
width from the tread's |x| range:

| wheel | x | y | z | r | width (x_in .. x_out) |
|---|---|---|---|---|---|
| FL | -0.8984 | -0.2825 | -1.2938 | 0.3857 | 0.348 (0.724 .. 1.073) |
| FR | +0.8884 | -0.2820 | -1.2938 | 0.3863 | 0.349 (0.714 .. 1.063) |
| RL | -0.8986 | -0.2866 | +1.3500 | 0.3816 | 0.349 (0.724 .. 1.073) |
| RR | +0.8888 | -0.2869 | +1.3500 | 0.3813 | 0.349 (0.714 .. 1.063) |

Wheelbase 2.644 m, track about 1.787 m (on a 4.5 m car). The model is **1 cm off-centre in X** (left wheels 0.898,
right 0.888 from the bbox centre): AI-mesh asymmetry, kept (the wheel meshes follow the real tyres). Front and rear
radius differ by 1 %.

**Cut dry run (numpy, same rules as the Blender cut, without the lip rule):** 156,915 / 143,868 / 160,188 / 152,516
faces go to FL / FR / RL / RR. Point splats (scratch files `cut_FL_outer.png`, `cut_body_left.png`, looked at): the
cut wheel is the complete tyre + 5-spoke rim + hub + yellow centre cap + red brake caliper, and it is round; the body
keeps clean round arch openings plus a few arch-lip paint fragments (the lip rule keeps those on the body). **Known
effect: the brake caliper is part of the wheel mesh, so it turns with it** (a real one does not). It shows at low
speed only; cutting it out would leave a hole.

**These are not the final layout numbers.** `red_sports_wheels.json` gives the centres relative to the bbox of the
final body. Without wheels the body's lowest point rises, so the y values move up by a few cm. Use the json.

## QA checks (`red_sports_qa.json` + PNGs): what each one tests

| check | how | pass rule |
|---|---|---|
| wheel alignment | FL/FR z and y equal, RL/RR too; FL.x + FR.x (symmetry); wheel mesh bbox centre vs axle | < 1 cm (the ~1 cm asymmetry is the model's own) |
| wheel inside arch | body surface points (verts, tri centres, edge midpoints; arch discs excluded) inside the tyre cylinder at rest; min gap tyre -> body | 0 points inside |
| suspension travel | wheel moved over CarController's travel: droop (1.6-0.88)/s = 0.203 m, bump 0.88/s = 0.248 m (s = 16 studs / 4.5 m = 3.556 studs/m); first bump height with body points inside the tyre | report. Contact before full bump is expected (real arch gaps are 3-6 cm), the same holds for every car in the game, and it only shows on hard landings |
| steering pivot | fronts at +-28 deg (CarController) about the vertical axis through the wheel centre, at rest and at half bump | report points inside (tyre front/back edge vs the arch ends) |
| rotation | mesh axle = X, origin on the axle; renders of each wheel turned 30 deg about X | spoke pattern turns in place, outline unchanged |
| spin direction | CarController: `spin += fs*dt/r`, `C0 * Angles(-spin,0,0)`: forward (-Z) motion moves the contact point to +Z, which is rolling | by construction. Game radius is 1.04 r, so the mesh turns 4 % slow and floats about 1.5 cm |
| triangles | body <= 18,000, each wheel <= 2,000 (MeshPart limit 20,000) | from `_build.json` |
| textures | body 1024x1024 PNG atlas; each wheel its own 512x512 baked PNG | from `_build.json` |
| collision | chassis Part 7 x 1.6 x 15 studs collides; body MeshPart CanCollide false, Massless; wheel meshes CanCollide/CanQuery/CanTouch false, Massless, welded to the hidden wheel cylinder (also non-colliding); suspension is raycasts | by code (RaceCarServer) |

PNGs (`art/cars3d/roblox/qa/`): `red_sports_before.png` (source, 6 views), `red_sports_after.png` (body + wheel
meshes, the same 6 views), `red_sports_body_only.png` (arch discs, cut), `red_sports_sweeps.png` (full bump side +
3/4, full steer top + 3/4), `red_sports_wheels.png` (each wheel: outer, inner, tread, turned 30 deg).

## Results

| | expected | measured |
|---|---|---|
| body triangles | <= 18,000 | not run (box down) |
| wheel triangles FL/FR/RL/RR | <= 2,000 each | not run |
| body texture | 1024x1024 PNG | not run |
| wheel textures | 512x512 PNG each | not run |
| GLB sizes | body ~1.5-2.5 MB, wheels ~0.3-0.6 MB | not run |
| clearance / steer / travel | see QA table | not run |

## Game integration (code on this branch, reversible)

- `RaceCarServer.server.luau`: if `ServerStorage.CarBodies.<id>` holds MeshParts `WheelMesh_FL/_FR/_RL/_RR` (or one
  per side, `WheelMesh_L/_R`; a missing side uses the other side's mesh turned 180 deg about Y), each procedural
  wheel part gets a clone, scaled like the body, at `wheel.CFrame * yaw`, welded with a WeldConstraint, Massless,
  CanCollide/CanQuery/CanTouch false. The cylinder stays (same size, weld, physics) at Transparency 1, and no
  procedural rim/spokes are made. **CarController is unchanged**: it moves the wheel part through `WheelWeld.C0`
  (suspension, steer about Y, spin about X), and the mesh rides along. The body lookup now skips `WheelMesh_*`, so a
  car folder can hold them. Cars without wheel meshes build exactly as before.
- Yaw: the wheel meshes use `WheelYawFix` if it is set, else the car's `YawFix` (180 for every imported GLB so far).
  The importer maps the glTF front (+Z) to the Roblox front, which is a 180 deg rotation, so the same fix should
  apply to the wheels. If a left wheel shows its inner face outward in the test, set `WheelYawFix = 0` on the car
  folder.
- `PattayaTestKitServer.luau`: `S.spawnCar(plr, carId, opts)` (also `TK.server("spawnCar", "red_sports")`). It builds
  `TestCar_<id>_<userId>` 14 studs ahead through `ServerStorage.BuildCar`, replaces the previous one, and seats the
  player (`opts.seat = false` only builds). Like the whole TestKit it works in Studio or `DevTest` places only.
  **Not in CarSpecs, not in the garage**: an unknown id drives with `CarSpecs.BASE` stats.
- CarController needs no change, so nothing touches team18/recovery's file.

## Upload list (only after the owner confirms the rights)

Asset type **Model** (Open Cloud `POST /assets/v1/assets`, `model/gltf-binary`), each < 20 MB:

| file | MeshPart after import -> name in CarBodies |
|---|---|
| `art/cars3d/roblox/red_sports.glb` | `red_sports` -> `Body` |
| `art/cars3d/roblox/red_sports_wheel_FL.glb` | `red_sports_wheel_FL` -> `WheelMesh_FL` |
| `art/cars3d/roblox/red_sports_wheel_FR.glb` | `red_sports_wheel_FR` -> `WheelMesh_FR` |
| `art/cars3d/roblox/red_sports_wheel_RL.glb` | `red_sports_wheel_RL` -> `WheelMesh_RL` |
| `art/cars3d/roblox/red_sports_wheel_RR.glb` | `red_sports_wheel_RR` -> `WheelMesh_RR` |

Fewer uploads also work: FL + FR only (the rears reuse them; 1 % radius difference), or FL only (the right side uses
it turned 180 deg). Import all with the **same** settings as the other cars (same Scale Unit), so body and wheels
share one unit; the code scales both by the same factor.

## Studio install (edit mode, command bar, after the imports are in workspace)

1. Generate the snippet from the real json and run its output:
   `python tools/gpu/car_import_wheels.py --luau art/cars3d/roblox/red_sports_wheels.json red_sports`.
   It collects the MeshParts named `red_sports` / `red_sports_wheel_*` from workspace into
   `ServerStorage.CarBodies.red_sports` (a Folder: `Body`, `WheelMesh_FL..RR`, anchored, non-colliding), sets
   `YawFix = 180`, `WheelRadius`, `WheelWidth`, `RimColor`, `WheelFL/FR/RL/RR` (metres, body space, front -Z),
   moves an older `red_sports` to `ServerStorage._old`, and prints what it installed. The output looks like this
   (placeholder numbers; use the generated ones):

```lua
local f = Instance.new("Folder"); f.Name = "red_sports"
-- Body, WheelMesh_FL, WheelMesh_FR, WheelMesh_RL, WheelMesh_RR are moved in here
f:SetAttribute("YawFix", 180)
f:SetAttribute("WheelRadius", 0.38)                             -- red_sports_wheels.json "radius"
f:SetAttribute("WheelWidth", 0.35)                              -- "width"
f:SetAttribute("RimColor", Color3.fromRGB(40, 40, 42))          -- "rim"
f:SetAttribute("WheelFL", Vector3.new(-0.90, -0.26, -1.29))     -- "wheels".FL (and FR, RL, RR)
f.Parent = game.ServerStorage.CarBodies
```

2. Install the scripts from this branch (`RaceCarServer`, `PattayaTestKitServer`) the usual way
   (`tools/studio/install.ps1` + `install.luau`).
3. Nothing goes on the start grid or into the garage: `CARS` in RaceCarServer and CarSpecs are unchanged.

## Play test plan (leader, Studio Play)

1. Server: `local S = require(game.ServerStorage.PattayaTestKitServer).start()`, then
   `print(S.spawnCar(S.player(), "red_sports"))`. Expect `TestCar_red_sports_<id> built (body mesh yes, wheel
   meshes 4); seated ...`.
2. Parked, screenshot each side: body upright, nose toward the car's LookVector, all 4 wheels in their arches,
   **outer rim faces outward on both sides** (else `WheelYawFix = 0`), no see-through arches, no floating.
3. Drive straight at 50, 100 and 150 (HUD km/h = studs/s): the top of each wheel moves forward, spin matches the
   ground speed, no wobble (wheel centred on its axle).
4. Full lock left and right at low speed: only the fronts turn, each about its own centre; watch the tyre front edge
   against the arch ends.
5. Kerbs and a ramp landing: the wheels move with the suspension; note any wheel showing through the bodywork at full
   bump (expected only on hard landings, see the QA sweeps).
6. Drift (Ctrl) and reverse: the wheels spin backwards in reverse.
7. Mobile perf: device emulator (low-end phone) with 1 and with 6 of these cars; compare frame time and memory
   (`Stats`) with a grid car. Cost per car: 5 extra MeshParts, 5 textures (1 x 1024 + 4 x 512).
8. Leave the car and spawn it again (`S.spawnCar` replaces it); check nothing is left behind.

## Rollback

- Remove the car: delete `ServerStorage.CarBodies.red_sports` (or move it to `_old`) and any
  `workspace.TestCar_red_sports_*`.
- Code: revert `RaceCarServer.server.luau` and `PattayaTestKitServer.luau` to `main`. Cars without `WheelMesh_*`
  behave exactly as before either way, so the code can also stay.

## Risks

- **Rights and brand badges** (see *Licensing*): blocker for upload.
- The importer's yaw for the wheels is assumed to equal the body's (180); one look in Play settles it (`WheelYawFix`).
- The brake calipers spin with the wheels.
- 1.94 M -> 18 k triangles (1 %) on an AI mesh: thin parts (mirrors, wing, grille bars, interior) lose detail. The
  before/after renders decide whether the body needs 2 MeshParts (2 x 18 k) instead.
- Open cabin: the modelled interior will be crude at 18 k triangles and shows through the glass area. The driver is
  hidden while seated (existing behaviour).
- The source is 1 cm asymmetric left/right.
