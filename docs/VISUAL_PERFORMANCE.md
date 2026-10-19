# Visual performance — VIS-4 slice budget and measurement protocol

Team vis-slice, 2026-10-19. Status: **written, not built or measured in Studio**. The slice numbers below come from
the exporter (`build/vis_slice/vis_slice.json`). The leader takes FPS and memory with the protocol in section 3.

## 1. Baseline (copied from docs/PERFORMANCE_BUDGET.md)
**2026-10-18, central slice only.** Studio Play on the owner's Windows PC, desktop, fresh session. A server
autopilot drove the race path at 160 studs/s for a full lap of about 41 s. Studio caps at 60 FPS.

| Scenario | Avg FPS | 1% low | Worst frame |
|---|---|---|---|
| Idle at spawn | 60.0 | 54.4 | — |
| Camera over the sea, facing away from the city | 60.0 | 55.0 | — |
| Full lap at 160 studs/s, day | 60.0 | 44.0 | 31 ms |
| Full lap at 160 studs/s, night (lit windows, 291 spotlights) | 60.0 | 45.2 | 32 ms |

World then: 16,027 Parts, 11,116 facade Textures, 291 SpotLights (night only). With streaming, a client had
3,700–6,500 Pattaya parts loaded at a time.

**2026-10-18, LOD test.** Night, Studio unfocused:
- Heartbeat 60/s, p99 18.9 ms;
- InstanceCount 60,188;
- parts streamed 4,819 (866 in view);
- textures streamed 2,628, of which 2,200 hidden by the LOD;
- SpotLights on: 9 of 71;
- memory: BaseParts 213 MB, GraphicsTexture 115 MB.

**2026-10-19, after the road fix, corridor dressing and street furniture.** Studio unfocused, night:
- PerfProbe at the Central start: parts loaded 8,118, textures 4,068 (visible 460), SpotLights on 11 of 104, traffic models 57.
- GPS drive Central → Bira: Heartbeat 60 (p50 16.9 ms, p99 19.3 ms, worst 20.2 ms).
- Memory: Instances 156 MB, GraphicsTexture 180 MB, InstanceCount 54k.
- RenderStepped is throttled while Studio is unfocused, so render FPS is unmeasured in that run.

Target from PERFORMANCE_BUDGET.md: 60 FPS on the owner's PC, with a 1% low of at least 45.

## 2. Slice budget (exporter output, 2026-10-19)
| | Count |
|---|---|
| Buildings upgraded | 507 of 535 boxes in the slice area (7 too thin, 2 replaced by landmark proxies, 19 all party walls / blocked) |
| New Parts | **22,953** (budget ≤ 25,000): 507 VisHull + 507 VisCore + 21,939 module parts, of which 1,024 roof parts (lit pass 2026-10-19; first build 21,856) |
| Parts removed from the city chunks | 507 boxes + 261 Roof slabs (moved to ServerStorage, not deleted) |
| **Net Parts in workspace** | **+22,185** |
| Facade Textures | about −515: decorated faces lose their Texture (1,944 → 1,429 on the upgraded boxes) |
| NightNeon parts (Neon at night) | 7,289 (7,196 lit panes + 93 neon strips); panes lit about 45 %, shopfronts about 70 %, warm amber tones |
| SurfaceGuis (signboards) | 462, PixelsPerStud 20, LightInfluence 0 |
| SpotLights / PointLights | 0 added |
| Collision parts | unchanged: 507 VisHull = the 507 boxes; all module parts CanCollide/CanQuery/CanTouch false, CastShadow false (VisCore casts shadows above 20 studs, like the box did) |
| Streaming | 58 Atomic chunk models, ≤ 600 parts each (largest 599); 8 build batches of ≤ 8 chunks (234–4,091 parts) |
| Parts per style | hotel 10,709 · shophouse 8,512 · commercial 2,708 · condo 607 · industrial 313 · house 104 |
| Parts per module | balcony_row_a 7,373 · window_pair_ac_a 4,483 · shopfront_a 2,811 · lobby_a 2,028 · transom_a 973 · shopfront_b 867 · curtain_wall_a 601 · roof_plant_a 528 · parapet_a 513 · water_tank_a 456 · balcony_grid_a 456 · fins_a 431 · band_glass_a 146 · garage_door_a 108 · window_row_a 76 · house_front_a 49 · ac_pair_a 40 |

What this means for a client:
- The slice is about 3,000 × 5,150 studs.
- At StreamingTargetRadius 1,280 (the `pc` profile), a car on Beach Road loads roughly a third to a half of the slice at once. Expect about 7,000–11,000 extra Parts loaded on top of today's 8,118 at the Central start. This is an estimate, not measured.

Risks:
- **7,289 NightNeon parts.** Neon parts with bloom are cheap to draw but add bloom area at night.
- **SurfaceGuis.** 462 signboards; each SurfaceGui costs a GUI layout and a texture.
- **PattayaLOD does not know the new part names.** Only the neon strips (`NeonSign`) and signboards (`SignFrame`) are faded beyond LOD_PropRange (900).

Cut list, if the measurements miss the target (cheapest first):
1. `V.Build({signs = false})`: no SurfaceGuis.
2. Lower `lit_win` in the config: fewer lit panes.
3. Larger `mid_bay` for hotels.
4. Ask team2/perf to add the small kit parts to `PROP_NAMES` in PattayaLOD: `ACUnit`, `Window`, `WindowLit`, `ShopGlow`, `Shutter`, `Sill`, `BalconyRail`, `ACCondenser`, `TankStand`, `WaterTank`, `Pilaster`, `Mullion`, `Transom`.

## 3. Measurement protocol (leader; the same steps before and after)
Run everything in a fresh Studio session with the Studio window in front. Use profile `pc`
(`require(game.ServerStorage.PattayaPerfProfile:Clone()).apply("pc")` in edit mode, then save).

1. **Before.**
   - Make sure no vis chunks exist (`V.Remove()` if they do).
   - Play, then `game.Lighting:SetAttribute("TimeLock", 21)` (server).
2. **Probes at three fixed spots** (server: teleport the car or use the test-kit autopilot):
   - A = Beach Road (21373, 1, -1000)
   - B = Second Road (21915, 1, -600)
   - C = Soi Pattaya 2 (21800, 1, -1802)

   At each spot, idle 5 s, then `workspace:SetAttribute("PerfProbe", 10)` (use 10.01, 10.02 … for reruns). Record:
   - `heartbeat` rate, p50 / p99 / worst;
   - `renderStepped` rate (valid only with `renderLooksFocused=true`);
   - memoryMB Instances / GraphicsParts / GraphicsTexture / total;
   - `counts.parts`, `texturesVisible`, `neonNear`, `drawProxyInView`, InstanceCount.
3. **Drive.** Autopilot the Central Loop (Beach Road → Pattaya Tai → Second Road → Pattaya Klang), 1 full lap at 160 studs/s, then one Beach Road run at 215 studs/s (nitro). Record:
   - FPS avg / 1% low / worst frame (Shift+F5 or the MicroProfiler, Ctrl+Alt+F6 in Studio);
   - whether streaming kept up (no "road missing" moments).
4. Repeat steps 2–3 by day (`TimeLock` 13).
5. **After.**
   - Stop Play.
   - Build all 8 batches (`V.Build({batch = "s1"})` … `"s8"`), run `V.Probe()`, save.
   - Repeat steps 1–4 with the same seeds and spots.
6. **Camera only.** Repeat step 3 with `MidnightCamera` true vs false (the slice built both times). The camera costs at most 4 raycasts per frame; its FPS effect is expected to be within noise.
7. **Report** a table like section 1 with these rows: idle A/B/C night, lap night, lap day, nitro Beach Road. Columns: FPS avg, 1% low, worst, Heartbeat p99, memory Instances/GraphicsParts, parts loaded. Report before/after deltas.

**Pass:** after-avg 60 FPS and 1% low ≥ 45 on the owner's PC (the PERFORMANCE_BUDGET target), and memory growth
in line with the part count. If it fails, apply the cut list in section 2 one step at a time and re-measure.
Mobile (≥ 30 FPS with profile `mobile`) is not measured in this phase.


## 4. Measured (leader, 2026-10-19, Studio focused unless noted; Device Emulator viewport 830 × 439, vsync 60)
`PattayaPerfProbe.run(10)` on the client, camera frozen, car parked.

| Where | State | Render fps | p50 / p99 / worst frame (ms) | Heartbeat p99 | parts in view | InstanceCount | memory total (MB) |
|---|---|---|---|---|---|---|---|
| Neon district B (19570, 10, 1796) | MidnightClear, after lighting pass | 59.9 | 16.6 / 19.6 / 40.7 | 18.2 | 1,643 | 75,083 | 5,494 |
| Neon district B | MidnightWet | 60.0 | 16.7 / 18.6 / 20.0 | 18.2 | 1,653 | 75,047 | 5,491 |
| Sample block street cam (20980, 40, 8) | before mesh swap, Part slice, 21:00 | 59.9 | 16.7 / 19.1 / 37.7 | 18.3 | 4,657 | 81,750 | 5,281 |
| Sample block street cam | after mesh swap (Studio **unfocused**: render throttled to 15 fps, invalid) | — | — | 18.5 | 6,030 | 83,451 | 5,582 |

- 1 % low ≈ 1000 / p99: ~51 fps (Clear), ~54 fps (Wet), ~52 fps (sample block before). The first 10 s after a camera
  jump shows streaming hitches (p99 67 ms, worst 113 ms at the sample block) — measure after the block has streamed in.
- Wet vs dry: no measurable difference (Reflectance is a material parameter; the RoadLook Heartbeat only exists while
  its queue drains).
- The focused "after mesh" row: see §6 (measured 2026-10-20).

## 5. Mesh instance optimisation (team7/mesh-opt, 2026-10-19 — exporter numbers, NOT built in Studio)
Problem (§4 / VISUAL_ACCEPTANCE §5.2): the VIS-7.1 kit swap made the 14-building sample block 634 Parts → 40 Parts +
1,612 MeshParts (1-bay modules, 1–4 MeshParts each). Fix: **merged kit modules**. `tools/blender/gen_merged.py` (pure
Python, no bpy) copies W × H cells of a validated kit `.glb` into one asset `BLD_<G>_<Variant>W<w>H<h>` (W bays of
7.143, H floors of 8.571; same geometry, UVs, normals, MP_* materials; one MeshPart per material; the glass split into
`_Glass` + `_GlassAlt` so lit panes still vary). `VisMesh.merge_rows` cuts every run of equal adjacent 1-bay modules
greedily into widths {4,3,2,1} × floor bands {4,3,2,1} (one row repeated every H floors); signboard-text columns,
wide/centre modules (HotelLobby, Commercial7Bay) and roof items stay as they were; corner stacks merge vertically.
Every merged instance passes the same footprint checks; the VisHull / VisCore / Part-kit fallback are unchanged.

| Sample block (14 buildings) | Parts | MeshParts | total |
|---|---|---|---|
| Part slice (before) | 634 | 0 | 634 |
| VIS-7.1 1-bay kit (`BuildMesh({merged = false})`) | 40 | 1,612 | 1,652 |
| **mesh-opt merged (default)** | 40 | **508** | **548** |
| rejected: one MeshPart per kit module (vertex colour / atlas, loses per-part Material + lit panes) | 40 | 481 | 521 |
| rejected: one unique asset per building (17 uploads here, 604 citywide / ~230 MB glb) | 40 | 127 | 167 |

Biggest three: hotel tower 1209261453 (29 fl) 156 Parts → 2 + 515 (VIS-7.1) → **2 + 111**; hotel 317141439 (25 fl)
129 → 2 + 364 → **2 + 50**; corner commercial 422398694 (11 fl) 65 → 2 + 143 → **2 + 67**. Triangles are unchanged
(cells are copies): 49,382 for the 14 buildings (hotel tower 14,544). Merged assets: 36 for the sample (1.29 MB glb,
16,972 tris, max 2,400 per asset = CondoBalcony W4H4; ≤ 10,000 per asset enforced) on top of the 20 kit assets already
uploaded. Palms: the impostor trunk cylinder (at the trunk foot) is now the collider: 5 → 4 instances per palm
(157 palms: 785 → 628). Block count (14 buildings + the 8 palms within 160 studs of (21100, 41)): 682 before →
1,692 VIS-7.1 → **580** (the leader's Studio 1,018 / 2,074 used a different area; re-measure with the same query).

Citywide estimate (all 507 slice buildings through the mesh path; `mesh_sample.json` `citywide_estimate`):

| Tiles (W × H) | Parts + MeshParts | MeshParts / building mean, p90, max | merged assets | merged glb |
|---|---|---|---|---|
| Part slice today | 23,786 + 0 | — | — | — |
| 1-bay kit (VIS-7.1) | 1,763 + 76,382 = 78,145 | 151, 366, 2,793 | 0 | — |
| 1–3 × 1–3 | 26,334 | 49, 104, 583 | 66 | 2.7 MB |
| **1–4 × 1–4 (default)** | **21,896** | 40, 83, 359 | **111** | **6.2 MB** |
| 1–4 × 1–4, glass not split | 19,306 | 35, 70, 287 | 111 | 6.2 MB |
| 1,2,4,8 × 1,2,4,8 | 24,278 | 44, 91, 337 | 86 | 7.8 MB |
| 1–8 × 1–8 | 17,395 | 31, 57, 158 | 250 | 35.8 MB |

Memory: mesh data is shared per asset (sample: 0.82 MB kit + 1.29 MB merged glb ≈ GPU vertex + index data of the same
order); the instance saving is ~1,100 instances in the block and ~56 k citywide vs the 1-bay kit. Per-instance memory
and draw-call batching of the merged tiles are **not measured** — run §3 at the street camera with
`BuildMesh()` and `BuildMesh({merged = false})`.
LOD: no new far variant; Roblox's own MeshPart LOD (RenderFidelity Automatic) applies per merged mesh, and the palm
impostor switch (client VisMeshPalmLOD) is unchanged. Beyond that, `Model.LevelOfDetail = StreamingMesh` would only
help with StreamingEnabled (not used now).


## 6. Focused measurement after mesh-opt + PBR (leader, 2026-10-20 ~10:50, desktop viewport 2684 × 1148, vsync 60)
Same street camera as §4 (`CFrame.lookAt((20979.8, 40, 8), (21119.9, 45, 75))`), 21:00 MidnightClear, HUD hidden, car parked,
`PattayaPerfProbe.run(10)` after the block streamed in, render-rate check ≥ 50 before and during the probe.

| Build in the block | Render fps | p50 / p99 / worst (ms) | 1 % low ≈ | parts in view | InstanceCount | memory total / textures (MB) |
|---|---|---|---|---|---|---|
| merged tiles (40 + 508 MeshParts) + PBR maps | 59.9 | 16.7 / 18.1 / 39.6 | 55 fps | 5,203 | 83,533 | 6,164 / 232 |
| original Part build (V.RemoveMesh, 0 MeshParts) + PBR maps | 60.0 | 16.7 / 18.0 / 18.8 | 56 fps | 5,248 | 83,240 | 6,325 / 232 |

Result: the merged-tile build costs nothing measurable against the Part build at this camera (both vsync-bound at 60, p99 18 ms, parts in view within 1 %).
Note: the §4 rows were taken on the 830 × 439 emulator viewport, so "parts in view" is not directly comparable
(this desktop viewport is wider). The A/B rows below use the same desktop viewport.

### 5.1 Pilot block 2: Second Road (prepared, not installed; exporter numbers, not built in Studio)
`vismesh.blocks` replaces the single block (block 1 = `sample_block`, unchanged: 634 → 40 + 508). Block 2
`second_road_soi5_10`: buildings whose centre is within 140 studs of Pattaya Sai Song Road and projects between the
Soi Pattaya 5 crossing (map-local 2101, −1299) and the Soi Pattaya 10 crossing (1091, 979). The slice road data has no
Soi 13, and x 1700–1950 holds only 23 upgraded buildings within 140 studs, so the span runs Soi 5 → Soi 10 to reach 60.
60 buildings: 38 shophouse, 11 hotel, 4 commercial, 4 industrial, 2 house, 1 public (ids in `mesh_sample.json`
`blocks[2].osm`).

| Block 2 | Parts | MeshParts | total |
|---|---|---|---|
| Part slice (before) | 2,577 | 0 | 2,577 |
| 1-bay kit (`merged = false`) | 137 | 6,724 | 6,861 |
| **merged 1–4 × 1–4** | 137 | **2,177** | **2,314** |

Triangles 202,526; biggest: hotel 1210196040 (21 fl) 154 → 2 + 92, hotel 322203172 (17 fl) 137 → 2 + 74, hotel
153538042 (11 fl) 136 → 2 + 81. 6 Part rows stay Parts (garage doors, house fronts: no kit asset). Merged assets
used: 70 (22 of the 36 uploaded + 48 new: 2.05 MB glb, 27,840 tris, max 1,800); kit assets 15. Shophouse rows with
mixed per-column modules merge less (runs of 1–2), so this block saves 10 % against the Part build where block 1
saved 14 %. Citywide estimate unchanged (§5 table: 21,896 instances, 111 merged assets; 84 now exist).

| everything installed (merged block + palette + citywide aprons + mesh traffic), 2026-10-20 18:00 | 60.0 | 16.7 / 18.3 / 22.0 | 55 fps | 5,366 | 86,053 | 6,756 / 230 |

The 2026-10-20 18:00 row is the same desktop camera after the junction aprons (+23.8k parts citywide, streamed) and the mesh
traffic: still vsync-bound at 60 with p99 18.3 ms; memory +592 MB vs the 10:50 row (aprons + traffic templates).
Mobile (Device Emulator) baseline: still to be measured.


## 7. Mobile baseline — Device Emulator (leader, 2026-10-20 18:20)
Device Emulator, landscape, viewport 830 × 439, touch on, compact HUD on, quality Automatic, MidnightClear 21:00, everything
installed (merged block, palette, citywide aprons, mesh traffic). **The emulator renders on the PC GPU: these numbers are the
client's frame pacing and memory on this machine, not a phone's GPU.** A real-phone run (Roblox app, same place) is still
needed for true mobile FPS.

| Scene | Render fps | p50 / p99 / worst (ms) | 1 % low ≈ | parts in view | memory total / textures / GUI (MB) |
|---|---|---|---|---|---|
| Static street cam, HUD on, 1st 10 s after arriving | 55.4 | 16.6 / 53.8 / 101 | 19 fps (streaming hitches) | 4,949 | 6,874 / 231 / 262 |
| Static street cam, 2nd 10 s | 59.9 | 16.7 / 18.8 / 43.7 | 53 fps | 4,952 | 6,856 / 231 |
| Driving 150 studs/s through the slice, first 20 s (fresh streaming) | 50.0 | 16.9 / 71.9 / 203 | 14 fps | 1,254 | 5,831 / 238 |
| Driving, next 20 s | 59.7 | 16.6 / 28.2 / 68.3 | 35 fps | 823 | 5,854 / 242 |

- GraphicsTexture 230–242 MB on this client — far above the owner's 18 MiB mobile texture budget. Most of it is not the
  new PBR maps (18 MiB estimated): it includes Roblox's own UI/terrain/material textures and the facade decals. Next
  step: measure GraphicsTexture with the PBR module removed (A/B) and on a real phone, then cut (512² for Concrete /
  DarkGlassGrid, facade decal LOD) until the PBR share fits 18 MiB.
- Streaming hitches dominate the 1 % low in the first seconds after a teleport / fast entry (worst frames 100–200 ms).
  During one such hitch the test car tipped (up −0.33) on the first run; the repeat run of the same route had no tilt
  (up min 0.97).

- Texture A/B in the same Play session (18:30): destroying all 492 SurfaceAppearances and clearing 8,591 MaterialVariant
  uses left GraphicsTexture at 244.7 MB after 15 s, i.e. textures are cached and an in-session A/B cannot show the PBR
  share. The world uses only 3 distinct facade images (3,236 Texture objects). The 230–245 MB GraphicsTexture and the
  262–272 MB "Gui" figure in Studio include Studio's own editor/CoreGui and built-in material/terrain textures, so the
  owner's 18 MiB budget can only be checked on a **real phone client** (Roblox app → Developer Console → Memory →
  GraphicsTexture), comparing a fresh join with and without ReplicatedStorage.MaterialLibraryMaps. PENDING_OWNER_TEST.
