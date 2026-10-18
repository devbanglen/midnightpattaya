# Visual acceptance — VIS-4 slice + VIS-5 camera + VIS-7.1 kit MeshParts

Team vis-slice, 2026-10-19. The VIS-4 Part slice was built and captured by the leader on 2026-10-19 (22,953 parts).
The VIS-7.1 changes (building variety, which changes the Part numbers below, and the kit MeshPart sample block +
mesh palms, section 4) are **written, not built in Studio**. Every item below is for the leader to run.

The owner's directive §14 checklist was not in my brief. Section 3 is put together from the brief I got. The leader
should line it up with §14 and add whatever is missing.

## 1. Build steps (edit mode, save the place first)
1. Generate the data. `build/` is gitignored, so on the main checkout run:
   `.venv\Scripts\python tools\mapgen\vis_slice.py tools\mapgen\config\vis_slice.json`
   It needs `build/central_pattaya`, `build/landmarks`, `build/furniture` and `build/coast`.
   Expected output:
   - 507 buildings, 23,786 parts, 59 chunks, 8 batches (VIS-7.1 variety; the built lit pass was 22,953 / 58);
   - `checks:` all 0;
   - a last line `vismesh sample block: 14 buildings ...; Parts 634 -> 40 Parts + 1612 MeshParts; palms 157; camera ...`
     and the report `build/vis_slice/mesh_sample.json`.

   The script exits with status 1 if any check fails.
2. Install the modules:
   - `ServerStorage.PattayaVisSliceBuilder` ← `roblox/src/ServerStorage/PattayaVisSliceBuilder.luau`
   - `StarterPlayerScripts.MidnightCamera` ← `roblox/src/StarterPlayer/StarterPlayerScripts/MidnightCamera.client.luau`
   - `ServerStorage.PattayaDataVisSlice` (new Folder) ← `manifest.luau` + `vismesh.luau` + 59 `chunk_v*.luau` from `build/vis_slice/roblox/` (436 KB in total), with the same JSON bundle / HttpListener method as the other data folders.
   - VIS-7.1: `ServerStorage.VisMeshBuilder`, `ServerStorage.VisMeshPalmLOD` (both from `roblox/src/ServerStorage/`) and `ServerStorage.VisAssetsManifest` (already there).

   `tools/studio/install.ps1` does not bundle this folder yet. Add a line next to the landmarks/coast ones:
   `$data += Entries 'build/vis_slice/roblox' 'PattayaDataVisSlice'`
3. Build one batch per call. Each call skips chunks that already exist, so it can be repeated after an error:
   ```lua
   local V = require(game.ServerStorage.PattayaVisSliceBuilder)
   print(V.Build({batch = "s1"}))  -- 8 chunks, 2,981 parts   (north: Pattaya Nuea / Dolphin Circle end)
   print(V.Build({batch = "s2"}))  -- 8 chunks, 3,610 parts
   print(V.Build({batch = "s3"}))  -- 8 chunks, 2,858 parts
   print(V.Build({batch = "s4"}))  -- 8 chunks, 3,289 parts   (Pattaya Klang)
   print(V.Build({batch = "s5"}))  -- 8 chunks, 3,844 parts
   print(V.Build({batch = "s6"}))  -- 8 chunks, 3,699 parts
   print(V.Build({batch = "s7"}))  -- 8 chunks, 3,281 parts
   print(V.Build({batch = "s8"}))  -- 3 chunks,   224 parts   (south: Pattaya Tai / Walking Street end)
   ```
   The place already holds the 22,953-part build: run `V.Remove()` first (it restores the boxes), then the batches.
   Build moves each upgraded procedural box, and its Roof slab when the box is taller than 30 studs, to
   `ServerStorage.PattayaVisSliceRemoved`. It warns if a chunk's part count differs from the manifest. Expect
   "507 procedural boxes moved" in total.
4. Probe:
   ```lua
   print(V.Probe())
   ```
   Expected:
   ```
   vis parts 23786 (manifest total 23786); touching road/sidewalk/disc 0; outside their box 0;
   hull != original 0; boxes still in the city 0; chunks with a different part count 0;
   NightNeon 6430; signboards 390
   ```
   NightNeon = 6,339 lit panes + 91 neon strips (before BuildMesh; after it, the 14 sample buildings count as their
   Part build in the chunk check, but `vis parts` and NightNeon / signboards count what is really there).
5. Cross-probes with the existing layers:
   - `require(game.ServerStorage.PattayaCoastBuilder).Probe()`
   - `require(game.ServerStorage.PattayaLandmarksBuilder).Probe()`
   - the leader's furniture overlap probe from STREET_FURNITURE.md (PattayaFurnitureBuilder has no Probe function)

   Their numbers must be unchanged. Building checks find `VisHull`, which has the original box's size and position
   and the `OsmBuilding` attribute; the offline check found 0 upgraded boxes touching a road/sidewalk corridor or disc.
6. Undo:
   - `V.Remove()` runs `V.RemoveMesh()` (section 4), destroys the vis chunks and puts every box back.
   - Camera: `game.Lighting:SetAttribute("MidnightCamera", false)`.
   - After a `PattayaBuilder.RebuildChunks()` on a slice chunk, run `V.RemoveReplaced()` again.

## 2. The six required captures (world studs; map-local x + 20000; road top y = 1)
Take each "after" capture twice: day (`game.Lighting:SetAttribute("TimeLock", 13)`) and night (`TimeLock` 21),
unless the shot says otherwise.

To get a "before" capture of the same frame:
1. Run `V.Remove()` (the boxes come back).
2. Capture.
3. Rebuild with `V.Build`.

Car positions are given for an autopilot or teleport. The heading is the direction of travel.

| # | Shot | Car / camera | Time | What to look for |
|---|---|---|---|---|
| 1 | Beach Road chase, southbound (hero shot, mockup angle) | car at (21373, 1, -1000), heading (-0.138, 0, 0.990), driving ≥ 150 studs/s, MidnightCamera on | night | hotel balcony bands with some lit windows, shopfront awnings and signboards on the land side, palms and promenade on the sea side, road ahead visible, FOV widened |
| 2 | Same as 1 by day | same | day | wall colours are the cream/white/pastel palette with no purple tint; dark glass; awning colours varied |
| 3 | Second Road chase | car at (21915, 1, -600), heading (0.246, 0, -0.969) | night | shophouse rows with window pairs and AC units, a few cyan/magenta neon strips, selective lit windows (not every window) |
| 4 | Soi Pattaya 2 street level | free camera `CFrame.lookAt(Vector3.new(21760, 7, -1802), Vector3.new(21840, 9, -1803))` | night | both soi sides: roller shutters, lit shop interiors, Thai/English signboards readable, rooftop water tanks on the skyline |
| 5 | Aerial over the slice | free camera `CFrame.lookAt(Vector3.new(21250, 240, 300), Vector3.new(21600, 0, -1200))` | dusk (`TimeLock` 18.5) | roofline: parapets, plant rooms, tanks; varied facades instead of identical boxes; navy sky (lighting team) |
| 6 | Beachfront from the sand | free camera `CFrame.lookAt(Vector3.new(20600, 10, 664), Vector3.new(20700, 40, 740))` | night | beachfront hotels face the sea with lit bands; no duplicated palms or railings; nothing in the promenade lamp row |

Add one capture of the camera itself: hold Q (look back) and right-drag (look sideways) while driving shot 1.

## 3. Test checklist
### Buildings / facades (VIS-4)
- [ ] All 8 batches build without errors. `V.Probe()` gives 0 / 0 / 0 / 0 / 0 as above.
- [ ] Footprints unchanged: `hull != original 0` (size, position and orientation equal to the stored box).
- [ ] Collisions unchanged: drive into a shophouse front, a hotel front and a corner at 60–100 studs/s. The car stops at the same place as before; with the boxes the faces are flush, so there is no "inset" to drive into. Facade parts never collide.
- [ ] Road clearance: run the existing road raycast probe (`tools/mapgen/studio_probes.py` / the furniture probe's 45,015 raycasts along every road part). No new hit on a vis part, because facade parts have CanQuery false.
- [ ] No facade part floating or poking out of a box. Check shots 1, 3 and 4 and corner buildings.
- [ ] Night: lit windows are selective, about 45 % (shopfronts about 70 %), warm amber in 3 tones (hotel/condo upper half of the building a cooler 140,130,110), never white. At 21:00 `NightNeon 6430` parts switch to Neon (PattayaNightLights). By day they are SmoothPlastic in their day colour.
- [ ] Neon budget: 91 strips in total, cyan or magenta only, on commercial and some shophouse fronts. A face with a city neon sign (near Walking Street) has no extra signboard or neon from us (19 faces).
- [ ] Variety (VIS-7.1): neighbouring buildings of one category differ in wall tint, trim and glass tint; tall hotels change balcony type between floor bands (3–7 floors); tops alternate parapet / cornice / crown fins (crown only on >= 8 levels); not every bay has an AC unit and not every shopfront a signboard. Boxes, hulls and collisions as before (`hull != original 0`).
- [ ] Signboards: generic words only (no brands or logos), Thai line + English line. The Thai glyphs render; Roblox font fallback is not seen yet.
- [ ] Palms, promenade lamps and railings are not duplicated (we add nothing outside the boxes).
- [ ] Undecorated faces still show the old facade Texture and its night tile; PattayaLOD still hides them beyond 700 studs.
- [ ] `V.Remove()` restores every box ("restored N parts; 0 left") and the city looks as before.
- [ ] HUD unchanged (docs/UI_CONTRACT.md): no script touches the UI.

### Camera (VIS-5)
- [ ] Sitting in a car switches to the chase camera with a short glide (0.4 s).
- [ ] Getting out gives back Roblox's camera with FOV 70.
- [ ] Road ahead visible at 160 and 215 studs/s on Beach Road and through the Second Road bends. FOV 70 at rest, about 85 at nitro top speed.
- [ ] No shake on kerbs, junction discs or in a crash, and no roll. The camera does not jump when passing light poles or palms (ThinObstacle).
- [ ] Next to a building wall the camera moves in front of the wall and eases back out.
- [ ] Hold Q to look back (camera swings around the car); release to return. Right-drag / right stick to look sideways, springing back.
- [ ] `game.Lighting:SetAttribute("MidnightCamera", false)` gives Roblox's vehicle camera instantly, while driving. Setting it back to true (or nil) brings the chase camera back.
- [ ] Circuit spectate (Z/X/B in CircuitRaceClient): the spectator camera works. MidnightCamera steps aside while the subject is another car and takes over again after B.
- [ ] Garage spawn, reset (R), race teleports and Survival grids: no stuck or black camera.
- [ ] Reduce Motion (`LocalPlayer.ReducedMotion = true`): the FOV stays at 70.

### Performance
- [ ] Run the before/after protocol in `docs/VISUAL_PERFORMANCE.md`.

## 4. VIS-7.1 kit MeshParts: sample block + mesh palms (written, not built in Studio)

Code: `tools/mapgen/VisMesh.py` (called by vis_slice.py), `ServerStorage.VisMeshBuilder` (through
`PattayaVisSliceBuilder`), client `VisMeshPalmLOD`. Report: `build/vis_slice/mesh_sample.json` (per building: slots
swapped, Parts before / after, MeshParts, insets, kept-Parts reasons; palms). Every count below is what the exporter
expects; none was measured in Studio.

### 4.1 Sample block
Config `vismesh.sample_block`: centre map-local (1100, 41), radius 120 → world centre **(21100, y, 41)**, Beach Road
at Soi 7 / Soi 8, city chunks 2_-1 / 2_0 (vis chunks `v2_-1_2`, `v2_0`, `v2_0_2`, `v2_0_3`). 14 buildings:

| OSM id | category | levels | world x, z | faces | Parts before → after | MeshParts |
|---|---|---|---|---|---|---|
| 1209261453 | hotel tower | 29 (251.6 studs) | 21100.4, 40.8 | 1 | 156 → 2 | 515 |
| 317141439 | hotel | 25 | 21132.0, 57.3 | 1 | 129 → 2 | 364 |
| 422398694 | commercial (corner) | 11 | 21080.1, 61.5 | 2 | 65 → 2 | 143 |
| 422397473 | commercial | 11 | 21159.6, 131.8 | 1 | 45 → 2 | 81 |
| 342674701 | shophouse | 3 | 21190.8, 107.7 | 1 | 61 → 2 | 132 |
| 1209261451 | shophouse | 4 | 21174.4, 76.0 | 1 | 27 → 2 | 92 |
| 422398832 | shophouse | 2 | 21093.8, 94.6 | 1 | 32 → 2 | 68 |
| 723863876 | shophouse | 4 | 21069.5, 78.5 | 1 | 32 → 2 | 35 |
| 1209268122 | shophouse | 4 | 21154.3, -38.4 | 1 | 20 → 2 | 33 |
| 1209261454 | shophouse | 2 | 21134.4, 23.5 | 1 | 13 → 2 | 25 |
| 1209270237 | shophouse | 2 | 21096.9, 73.0 | 1 | 14 → 2 | 13 |
| 336826683 | industrial | 2 | 21203.8, 60.0 | 1 | 16 → 7 | 47 |
| 422155360 | industrial | 2 | 21034.4, 135.8 | 1 | 13 → 6 | 38 |
| 1209156036 | industrial | 2 | 21054.4, 148.6 | 1 | 11 → 5 | 26 |
| **total** | | | | | **634 → 40** | **1,612** |

"2" = VisHull + VisCore. The 3 industrial buildings keep their Part garage doors (no kit asset). The MeshPart
instance count is 2.5× the Part count it replaces (each kit module is 1–4 MeshParts, and modules are 7.14 studs wide
where the Part bays were 10–14): the instances share the meshes of 20 building assets, so they batch, but this is the number for the
performance pass to measure before any wider rollout.

### 4.2 Slot → asset map (`vismesh.slots`, `roof_slots`, `corners`; instances in the sample)
| Part module (MeshSlot) | kit asset(s) | sample instances |
|---|---|---|
| shopfront_a | BLD_GF_ShophouseAwning / BLD_GF_ShophouseShutter (seeded per column; the awning needs a 4.55 inset) | 4 / 23 |
| shopfront_b | BLD_GF_CommercialBay / BLD_GF_Restaurant, BLD_GF_Commercial7Bay per 7 columns | 3 / 2 / 0 |
| lobby_a | BLD_GF_HotelLobby (2 modules, centred) + BLD_GF_CommercialBay | 2 + 5 |
| window_pair_ac_a | BLD_MF_PunchedAC, or BLD_MF_PunchedTwin where the seeded AC density says no AC | 18 / 13 |
| window_row_a | BLD_MF_PunchedTwin / BLD_MF_ShophouseUpper | 35 / 33 |
| balcony_row_a | BLD_MF_BalconyRow | 128 |
| balcony_grid_a | BLD_MF_CondoBalcony | 108 |
| transom_a | BLD_MF_CurtainWall (column 0 BLD_MF_CurtainWallNeon on neon buildings) | 17 / 6 |
| band_glass_a, fins_a, curtain_wall_a | dropped when the face's floors are meshes (the kit has the glass) | — |
| parapet_a / cornice_a / crown_a | BLD_TP_Parapet / BLD_TP_CorniceNeon / BLD_TP_CrownFin (on the roof) | 24 / 35 / 0 |
| roof_plant_a / water_tank_a / ac_pair_a | BLD_RF_PlantRoom / BLD_RF_WaterTank / BLD_RF_ACUnits | 3 / 7 / 3 |
| corners (two mesh faces meeting) | BLD_CN_Ground, BLD_CN_Mid (BLD_CN_GlassMid on commercial), BLD_CN_Top | 1 / 10 / 1 |
| garage_door_a, house_front_a | none: Part kit | — |

Placement: exact kit size (scale 1; the export carries a scale per row, all 1), n = floor(run / 7.1429) modules centred
on the run, the leftover shows the VisCore wall. Ground rows need the 11.571 ground floor, mid rows the 8.571 floor
(±0.05). The VisCore is inset deeper on mesh faces (max(Part inset, deepest module + 0.05), at most 8 studs and 25 % of
the box side; e.g. the 29-floor hotel 1.8 → 7.95 for the lobby canopy); a module deeper than that falls back along
`vismesh.alt`. Tops, the corner top and roof items stand on the roof (attribute `AboveRoof`); everything else stays
inside the box. Each mesh instance passed the same offline checks as the Parts (own box, road + sidewalk, discs,
furniture, coast, landmarks, city props, other boxes): 0 failures in the sample.

### 4.3 Build steps (edit mode, after section 1 steps 1–4; save the place first)
```lua
local V = require(game.ServerStorage.PattayaVisSliceBuilder)
print(V.BuildMesh())   -- 14 sample buildings + 157 palms; loads 23 assets once into ServerStorage.VisAssets
print(V.ProbeMesh())
print(V.Probe())       -- the Part probe still passes: a mesh building counts as its Part build in the chunk check
```
Options: `V.BuildMesh({only = {1209261453}})` (OSM ids or vis chunk ids; palms only when `palms = true`),
`V.BuildMesh({palms = false})`, `V.BuildMesh({buildings = false})`. A second call skips what is already mesh and
reuses `ServerStorage.VisAssets` (no second LoadAsset).

Expected `BuildMesh` line when every asset loads: `assets 23 loaded now, 0 from ServerStorage.VisAssets, 0 unusable [] (loaded
vs manifest: max centre offset …, max rotation … deg); buildings 14 built (40 Parts + 1612 MeshParts, 0 Part rows fell
back, 10 signboards, 61 lit panes) …; palms: 157 mesh palms built (314 MeshParts), 0 already there, 942 Part palm parts
moved …, 0 Part palms not found …`. The two "loaded vs manifest" numbers are measured, not used: placement uses
the manifest centres and no rotation. If the rotation is not ~0 or the offset is not ~0 with an assembly that looks
wrong, tell vis-mesh.

If an asset fails to load (LoadAsset error, missing MeshPart, size ≠ manifest ± 0.05), it is listed as unusable and
every Part row that needed it is built from the Part kit instead (counted as "Part rows fell back"); palms of that
variant keep their Parts.

Expected `ProbeMesh`: `14 mesh buildings (sample 14): 40 Parts + 1612 MeshParts (export expects 40 + 1612 with every
asset); MeshParts outside their box 0; touching road/sidewalk/disc 0; size != manifest x scale 0; buildings whose
counts differ from the builder 0, from the export 0; Part rows on fallback 0 | palms 157 (of 157), 314 MeshParts, 314
impostor parts, 157 colliders, Part palms still at a mesh palm 0`.

Undo: `V.RemoveMesh()` (Part buildings back from `ServerStorage.VisMeshRemoved.Buildings`, Part palms back from
`…Palms`, mesh palms destroyed); `V.Remove()` does this too. `RestoreReplaced()` / `RemoveReplaced()` are unchanged:
mesh buildings carry `OsmBuilding` like the Part ones.

### 4.4 Before / after capture (same camera)
1. Before: build the Part slice (section 1), `V.RemoveMesh()` if needed.
2. Street camera (sea side of Beach Road, checked not inside a box):
   `workspace.CurrentCamera.CFrame = CFrame.lookAt(Vector3.new(20979.8, 40.0, 8.0), Vector3.new(21119.9, 45.0, 75.0))`
3. Aerial: `CFrame.lookAt(Vector3.new(20808.5, 170.0, -74.1), Vector3.new(21119.9, 60.0, 75.0))`
4. Capture both at `TimeLock` 13 and 21, then `V.BuildMesh()` and capture the same four again.

### 4.5 Palms
157 city palms (all of them lie in the slice bbox): RSD_Palm_A 66, B 42, C 49 (variant = floor(|7x + 13z|) % 3).
Before: 942 Parts (PalmTrunk + 5 PalmFrond each). After: 314 MeshParts (bark → `PalmTrunk`, leaf → `PalmFrond`,
RenderFidelity Automatic, CastShadow on like the Part palms) + 314 impostor Parts (`PalmTrunk` cylinder + flat
`PalmFrond` disc, attribute `VisMeshImpostor`, Transparency 1) + 157 invisible `VisMeshPalmCollider` (1.6 × 20 × 1.6,
CanCollide, at the trunk foot; the old trunk collided). Mesh at the old trunk foot (world x + 20000, y 0, z), the Part
palm's yaw, upright (no lean); the mesh heights are 22.7 / 28.1 / 16.8 studs against 26–34 for the Part palms.
LOD: PattayaLOD hides `PalmTrunk` / `PalmFrond` beyond LOD_PropRange (900) as before. The 400-stud mesh → impostor
switch needs the client module: copy `ServerStorage.VisMeshPalmLOD` to ReplicatedStorage and run
`require(game.ReplicatedStorage.VisMeshPalmLOD).Start()` from a LocalScript (owner of the client scripts). Without it
the full mesh shows up to 900 studs and the impostor stays hidden.

### 4.6 Checklist
- [ ] `BuildMesh` reports 0 unusable assets; `ProbeMesh` 0 / 0 / 0 / 0 / 0 as above.
- [ ] Modules line up with the floors (no gap or overlap between ground row and first mid floor, between bands, or at
      the top under the parapet); corners close the 422398694 corner.
- [ ] The VisCore wall shows in the leftover strip at the run ends (< 1 module) and looks intentional.
- [ ] Facade fronts face the street (front −Z = outward): canopies, awnings and balconies stick out, not in.
- [ ] Night: about 45 % of kit glass panes lit warm amber (61 panes in the sample), lobby / cornice / crown LEDs cyan,
      CurtainWallNeon magenta; neon strips at street level fade beyond LOD_PropRange (named `NeonSign`).
- [ ] Signboard text sits on the kit sign panel (10 in the sample), readable, not mirrored.
- [ ] Drive into a mesh shophouse and the hotel: the car stops at the original box face (VisHull), never on a mesh.
- [ ] Palms: one palm per old position, trunk foot on the ground, no Part palm left (`Part palms still at a mesh
      palm 0`), cars still stop at the trunk (collider).
- [ ] Performance pass (`docs/VISUAL_PERFORMANCE.md`) from the street camera, before / after.

### 4.7 Risks
- **The look cannot be checked offline.** UVs, the imported materials / baseColor, how MaterialLibrary styles a
  MeshPart (SurfaceAppearance only where one exists), the frond cards without an alpha texture (solid green cards)
  and the sign panel orientation are unseen. The footprint maths is checked offline; the assembly is not.
- **Importer naming / pivots.** MeshParts are found by name, by their `_Node` parent, or by unique size; a different
  hierarchy makes the asset "unusable" (reported, Part fallback), not a broken build.
- **Instance count.** 1,612 MeshParts for 634 Parts in the sample; a whole-slice rollout this way would be roughly
  60 k instances. Measure first; options: fewer columns per tower face, only the street face, the merged
  `Commercial7Bay`-style wide meshes.
- **Deeper insets** (up to 7.95 studs on the hotel face): the visible wall moves back; the hull, collisions and the road
  clearance do not change, but the street face of a mesh building reads slightly smaller than its footprint.
- **Kit rows on 20.1-stud boxes** end 0.04 studs above the roof (the box height is rounded to 0.1, the kit grid is
  20.142). Allowed by the offline check (grid tolerance 0.05); ProbeMesh allows 0.06.
- **Palm LOD** needs the client module above; palm heights differ from the Part palms (no rescale).
