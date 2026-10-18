# Visual acceptance — VIS-4 slice + VIS-5 camera

Team vis-slice, 2026-10-19. Status: **written, not built in Studio**. Every item below is for the leader to run.
Nothing here has been seen or measured yet.

The owner's directive §14 checklist was not in my brief. Section 3 is put together from the brief I got. The leader
should line it up with §14 and add whatever is missing.

## 1. Build steps (edit mode, save the place first)
1. Generate the data. `build/` is gitignored, so on the main checkout run:
   `.venv\Scripts\python tools\mapgen\vis_slice.py tools\mapgen\config\vis_slice.json`
   It needs `build/central_pattaya`, `build/landmarks`, `build/furniture` and `build/coast`.
   Expected output:
   - 507 buildings, 21,856 parts, 56 chunks, 7 batches;
   - `checks:` all 0.

   The script exits with status 1 if any check fails.
2. Install the modules:
   - `ServerStorage.PattayaVisSliceBuilder` ← `roblox/src/ServerStorage/PattayaVisSliceBuilder.luau`
   - `StarterPlayerScripts.MidnightCamera` ← `roblox/src/StarterPlayer/StarterPlayerScripts/MidnightCamera.client.luau`
   - `ServerStorage.PattayaDataVisSlice` (new Folder) ← `manifest.luau` + 56 `chunk_v*.luau` from `build/vis_slice/roblox/` (372 KB in total), with the same JSON bundle / HttpListener method as the other data folders.

   `tools/studio/install.ps1` does not bundle this folder yet. Add a line next to the landmarks/coast ones:
   `$data += Entries 'build/vis_slice/roblox' 'PattayaDataVisSlice'`
3. Build one batch per call. Each call skips chunks that already exist, so it can be repeated after an error:
   ```lua
   local V = require(game.ServerStorage.PattayaVisSliceBuilder)
   print(V.Build({batch = "s1"}))  -- 8 chunks, 2,767 parts   (north: Pattaya Nuea / Dolphin Circle end)
   print(V.Build({batch = "s2"}))  -- 8 chunks, 3,896 parts
   print(V.Build({batch = "s3"}))  -- 8 chunks, 2,574 parts
   print(V.Build({batch = "s4"}))  -- 8 chunks, 3,332 parts   (Pattaya Klang)
   print(V.Build({batch = "s5"}))  -- 8 chunks, 3,569 parts
   print(V.Build({batch = "s6"}))  -- 8 chunks, 3,345 parts
   print(V.Build({batch = "s7"}))  -- 8 chunks, 2,373 parts   (south: Pattaya Tai / Walking Street end)
   ```
   Build moves each upgraded procedural box, and its Roof slab when the box is taller than 30 studs, to
   `ServerStorage.PattayaVisSliceRemoved`. It warns if a chunk's part count differs from the manifest. Expect
   "507 procedural boxes moved" in total.
4. Probe:
   ```lua
   print(V.Probe())
   ```
   Expected:
   ```
   vis parts 21856 (manifest total 21856); touching road/sidewalk/disc 0; outside their box 0;
   hull != original 0; boxes still in the city 0; chunks with a different part count 0;
   NightNeon 6043; signboards 464
   ```
   NightNeon = 5,950 lit panes + 93 neon strips.
5. Cross-probes with the existing layers:
   - `require(game.ServerStorage.PattayaCoastBuilder).Probe()`
   - `require(game.ServerStorage.PattayaLandmarksBuilder).Probe()`
   - the leader's furniture overlap probe from STREET_FURNITURE.md (PattayaFurnitureBuilder has no Probe function)

   Their numbers must be unchanged. Building checks find `VisHull`, which has the original box's size and position
   and the `OsmBuilding` attribute; the offline check found 0 upgraded boxes touching a road/sidewalk corridor or disc.
6. Undo:
   - `V.Remove()` destroys the vis chunks and puts every box back.
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
- [ ] All 7 batches build without errors. `V.Probe()` gives 0 / 0 / 0 / 0 / 0 as above.
- [ ] Footprints unchanged: `hull != original 0` (size, position and orientation equal to the stored box).
- [ ] Collisions unchanged: drive into a shophouse front, a hotel front and a corner at 60–100 studs/s. The car stops at the same place as before; with the boxes the faces are flush, so there is no "inset" to drive into. Facade parts never collide.
- [ ] Road clearance: run the existing road raycast probe (`tools/mapgen/studio_probes.py` / the furniture probe's 45,015 raycasts along every road part). No new hit on a vis part, because facade parts have CanQuery false.
- [ ] No facade part floating or poking out of a box. Check shots 1, 3 and 4 and corner buildings.
- [ ] Night: lit windows are selective, about 25–40 %, warm and cool mixed. At 21:00 `NightNeon 6043` parts switch to Neon (PattayaNightLights). By day they are SmoothPlastic in their day colour.
- [ ] Neon budget: 93 strips in total, cyan or magenta only, on commercial and some shophouse fronts. A face with a city neon sign (near Walking Street) has no extra signboard or neon from us (20 faces).
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
