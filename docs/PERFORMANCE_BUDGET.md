# Performance budget

## Measurements (2026-10-18, Roblox Studio Play on the owner's Windows PC, desktop only)
Method: fresh Play session; server test-autopilot moves the seated car along the race path at 160 studs/s (top
speed without nitro) for a full lap (~41 s) while the client records RenderStepped frame times. Studio caps at 60.

| Scenario | Avg FPS | 1% low | Worst frame |
|---|---|---|---|
| Idle at spawn | 60.0 | 54.4 | — |
| Camera over the sea, facing away from the city | 60.0 | 55.0 | — |
| Full lap at 160 studs/s, day | 60.0 | 44.0 | 31 ms |
| Full lap at 160 studs/s, night (lit windows, 291 spotlights) | 60.0 | 45.2 | 32 ms |

World size: 16,027 Parts, 11,116 facade Textures, 291 SpotLights (night only), terrain ground/sea. With instance
streaming (template setting) a client had 3,700–6,500 Pattaya parts loaded at a time.

Caveats:
- Earlier runs in a session that had already run several test autopilots showed 15–21 FPS; a fresh session gave the
  numbers above. Long sessions should be re-measured (possible leak in test scripts or Studio itself).
- Studio Play runs server and client on one machine; a real client may differ.
- Mobile 30 FPS target: NOT measured (needs the device emulator or a phone).
- Studio screenshots are unreliable when the Studio window is not in front; FPS may also drop when unfocused.

## Budget rules used so far
- Windows as Textures, not Parts. One box per building. Roof slab only above 30 studs.
- Real lights only on every second street lamp, no shadows, enabled only at night.
- Markings/props don't collide and are excluded from queries.
- Chunks are Atomic streaming models (512 studs); race gates/grid are Persistent.

## Wide world in Studio (2026-10-18): counts, client LOD, profiles, test plan
**Status: code written, NOT run in Studio.** Nothing below has been measured yet; the numbers to expect are
estimates for the leader's test.

### What is in the place now
| | Parts | Facade Textures | SpotLights |
|---|---|---|---|
| Central slice (`PattayaWorld.Chunks`) | 16,027 | 11,116 | 291 (every 2nd lamp) |
| Wide world (`PattayaWorld.WideChunks`, 444 district chunks) | ~35,000 | ~24,500 | ~607 |
| Bira corridor (11 more chunks in `WideChunks`) | ~2,800 | — | (in the wide count) |
| Bira venue (`workspace.Circuit_bira`) | ~6,000 | — | 105 floodlight parts (`FloodLight = true`) |
| **Total** | **~60,000** | **~35,600** | **~900 lamp + 105 flood** |

Traffic is client-only: 84 loops, a pool of 70 car models near the camera (`PattayaTraffic.client`). The minimap
draws ~1,000 Frames once and moves one container per frame (cheap). The server and Studio hold every Part; a
client holds what streaming gives it (see the profiles). Measured so far: simulation 60 Hz in the wide world
(Heartbeat), 60 FPS rendered in the central slice with Studio focused. **Render FPS in the wide world is unmeasured**
(Studio throttles rendering when its window is not in front).

### Client LOD rules (`StarterPlayerScripts.PattayaLOD` + the light budget in `PattayaNightLights`)
All local to each client, nothing replicated or saved; distances are from the camera.

| What | Rule (pc defaults) | How | Cost |
|---|---|---|---|
| Facade Textures (`Texture` with attribute `Facade`) | hidden beyond **740** studs, shown again inside **700** (40-stud hysteresis) | `Texture.Transparency = 1`, original kept in a Lua table per part; no reparenting, so the night tile swap still applies to hidden ones | one record per building body, not per Texture |
| Small props `PalmTrunk`, `PalmFrond`, `NeonSign`, `SignFrame` | hidden beyond **940**, shown inside **900** | `LocalTransparencyModifier = 1` (client-only; Transparency and collision untouched) | one record per part |
| Lamp + floodlight SpotLights (night only) | only the nearest **60** within **350** studs (lamps) / **550** (floodlights) are on; a light behind the camera counts 1.5x as far | `PattayaNightLights` section 3, 4 times a second, `Enabled` written only on change | ~1,000 distance checks per update |
| Car lights | unchanged: up to 8 cars within 350 studs | `PattayaNightLights` section 4 | — |

Streaming: `PattayaLOD` watches `workspace.PattayaWorld` and every `workspace.Circuit_*` (DescendantAdded /
DescendantRemoving). New instances go into a queue that is registered on the next Heartbeat; streamed-out parts are
dropped in O(1). The distance sweep is round-robin, **LOD_Budget = 300 parts per Heartbeat**, so a chunk streaming
in never causes a spike. A full sweep of ~6,000 loaded records takes ~20 frames (0.3 s, ~70 studs at nitro speed),
well inside the distances involved.

Knobs are **workspace attributes** (live: the server can change them during Play and every client follows):
`LOD_Enabled` (false = everything shown and the light cap lifted, the old behaviour), `LOD_FacadeRange`,
`LOD_PropRange`, `LOD_Budget`, `LOD_SpotCap`, `LOD_LampLightRange`, `LOD_FloodLightRange`. Debug on the client:
`_G.PattayaLOD.stats()`.

### Streaming advice and profiles (`ServerStorage.PattayaPerfProfile`)
Why these values (cars 160 studs/s, 215 with nitro; ~1,000 studs of road needed ahead; 512-stud Atomic chunks):
- **StreamingMinRadius 512** (pc): the area that must be loaded around the car, streamed with top priority. It is
  one chunk size, so the chunk under the car and its neighbours are always present (2.4 s of nitro driving). The
  default 64 is meant for walking characters; at 215 studs/s a car leaves it in 0.3 s.
- **StreamingTargetRadius 1280** (pc): how far the client tries to load. 1,280 = 1,000 studs ahead plus half a
  chunk of margin, ~6 s of nitro driving. Larger only adds parts the LOD hides anyway (facades beyond 700) and costs
  join time and memory.
- **StreamOutBehavior Opportunistic**: stream out what is beyond the target radius even without memory pressure.
  With the default (LowMemory) a PC client that drives across the map keeps up to all ~60k parts and draws them, so
  render cost would grow with the distance driven. Opportunistic keeps the loaded set (and the LOD's work) bounded
  to the area around the car.
- **ModelStreamingBehavior Improved**: models with the default mode (Junctions, sub-models) are not all sent at join;
  they arrive with their parts. Atomic chunks and Persistent models (race gates, grid, job stands, rival bots) are
  unaffected. Faster join on a ~60k-part place. This is the first setting to revert if a client script cannot find
  something (the current client scripts `WaitForChild` with timeouts and only rely on persistent parts).
- `StreamingIntegrityMode` is NOT touched. `MinimumRadiusPause` (pause the player until the min radius is loaded)
  would prevent driving onto unloaded road after a teleport; consider it only if testing shows falls.

| Profile | MinRadius | TargetRadius | StreamOut | ModelStreaming | Facade | Props | SpotCap | Lamp / flood light range |
|---|---|---|---|---|---|---|---|---|
| `pc` | 512 | 1280 | Opportunistic | Improved | 700 | 900 | 60 | 350 / 550 |
| `pc_night` (Night Run grids, +16 car lights) | 512 | 1280 | Opportunistic | Improved | 900 (lit-window skyline) | 900 | 40 | 300 / 550 |
| `mobile` | 384 | 768 | Opportunistic | Improved | 400 | 500 | 16 | 220 / 400 |

The mobile target radius (768) gives ~3.5 s of nitro road ahead, so expect some pop-in at nitro on phones; that is
the trade for memory. With no profile applied, the scripts use the `pc` LOD defaults and streaming is unchanged.

Commands (reversible; the first `apply` saves the original values in the workspace attribute `PerfProfileBackup`):
```lua
-- EDIT mode, command bar (streaming properties are read at server start), then save the place:
local P = require(game.ServerStorage.PattayaPerfProfile:Clone()); P.apply("pc")
-- PLAY mode, server command bar: LOD knobs only, live on every client:
require(game.ServerStorage.PattayaPerfProfile).applyLOD("pc_night")
-- undo everything (in edit mode, so the streaming properties go back too):
require(game.ServerStorage.PattayaPerfProfile:Clone()).revert()
require(game.ServerStorage.PattayaPerfProfile).show()
```
Every property write is pcall'd. If Studio refuses one, the message names it, and it can be set by hand in
Properties → Workspace → Streaming.

### Measuring without a focused Studio (`ReplicatedStorage.PattayaPerfProbe`)
- From the **server** (command bar or an MCP call that runs on the server): `workspace:SetAttribute("PerfProbe", 10)`.
  Every client samples 10 s and prints `[PerfProbe] ...` lines (time, heartbeat, renderStepped, engine, memoryMB,
  counts, lod, knobs) to the Output. Set a different number (10.01) to run it again.
- From the **client** command bar: `require(game.ReplicatedStorage.PattayaPerfProbe).run(10)` (returns the table),
  or `.counts(700)` for the counts only.
- What it reports:
  - Heartbeat rate and p50 / p99 / worst frame time (valid when unfocused).
  - RenderStepped rate (valid only when `renderLooksFocused=true`).
  - `Stats:GetMemoryUsageMbForTag` for every DeveloperMemoryTag (Instances, GraphicsTexture, GraphicsParts,
    GraphicsMeshParts, PhysicsParts, LuaHeap, ...) and the total.
  - Stats counters: InstanceCount, PrimitivesCount, HeartbeatTimeMs, PhysicsStepTimeMs, and RenderCPU/GPU frame
    times when the engine exposes them.
  - Loaded Parts, visible / near / in-view Textures, SpotLights on (near), PointLights on, Neon parts near,
    BillboardGuis, traffic models in use.
  - `drawProxyInView` = visible parts + visible Textures in the view cone within the radius + lights on. There is no
    script API for real draw calls, so this is the proxy.
- **Real render FPS (the owner, playing on PC):** play in the Roblox Player, or in Studio with the window in front.
  - **Shift+F5**: the frame-rate summary overlay (FPS and frame time). The other Shift+F keys show further stat pages
    on most versions; press the same key again to close.
  - Esc → Settings → **Performance Stats: On**: CPU / GPU ms, memory and frame bars at the top of the screen.
  - **MicroProfiler**: Ctrl+F6 in the Roblox Player (Ctrl+Alt+F6 in Studio). The top bar shows ms per frame and
    whether the frame is CPU-bound (`render` / `jobs` on the main thread) or waiting on the GPU. Ctrl+P pauses it so
    a slow frame can be inspected; "Dump" saves an HTML capture to send to us.
  - **F9** Developer Console → Memory tab shows the same memory categories as the probe.
  - Please report: FPS while driving the Central Loop at night, while driving Thappraya → Jomtien at nitro, and at
    the Bira grid at night, plus the graphics quality (Settings → Graphics: Automatic or the slider value).

### Server per-frame cost (reviewed, behaviour kept)
- `PattayaGPSServer`: at most **one route per Heartbeat**. A route is a full nearest-edge scan plus a Dijkstra
  (5–6 ms on the wide graph). The most overdue player goes first, and each player still refreshes every 4 s while the
  server keeps up. Before, players whose refresh fell on the same frame stacked 5–6 ms each into one frame.
- `PattayaJobsServer`: each stand's nearest graph node is cached (stands and graph are static), so a job request no
  longer does 25 linear scans of ~2,900 nodes.
- `RaceSessionService` (CircuitServer): no table allocation per slot per frame in the session Heartbeat.
- Checked and fine (O(players) with constant work per player, no GetDescendants in loops): `PattayaRaceServer`,
  `PattayaSprintServer`, the `PattayaJobsServer` Heartbeat, `PattayaStreetRace` / `PattayaChallengeServer` (the
  bots' `PivotTo` per frame is the motion itself), `PattayaEventsServer` (0.25 s join scan while gathering, 1 s
  scheduler), and `CheckpointValidator` (windowed ±60-point centreline search with a hint).
- `RaceCarServer`'s parked-car spring does 4 raycasts per parked car per frame (grid cars plus one garage car per
  player). That is needed to keep the cars on their wheels; leave it unless the server MicroProfiler shows it.

### Test plan for the leader (Studio Play, fresh session)
1. Install with `tools/studio/install.ps1` + `install.luau`. It picks up `PattayaLOD.client`, `PattayaPerfProbe`,
   `PattayaPerfProfile` and the changed scripts automatically. In edit mode run `P.apply("pc")`, then save.
2. Play. Expect no errors and a silent Output. Run `game.Lighting:SetAttribute("TimeLock", 21)` (server) for night.
3. At the spawn, run `workspace:SetAttribute("PerfProbe", 10)` (server). Expect:
   - heartbeat rate ~60;
   - `counts.spotLightsOn` ≤ 60 (before: every streamed lamp light, a few hundred);
   - `texturesVisible` below `textures`, and `lod.hidden` > 0.
4. Drive (or autopilot) Thappraya → Jomtien at 160–215 studs/s. The road must always be there ahead (no driving into
   the void, no falling). `counts.parts` should stay roughly flat (Opportunistic) instead of growing with the
   distance driven. Run the probe at Jomtien and compare `memoryMB` GraphicsParts / GraphicsTexture / Instances
   with step 3.
5. Set `workspace:SetAttribute("LOD_Enabled", false)`, probe again, then set it back to `true`. The difference is
   what the LOD saves. Buildings must not flicker at the 700-stud edge; distant facades become plain wall colour.
6. Bira at night: the floodlights near the camera are on (up to the cap), and the track still looks lit from the
   grandstand.
7. With Studio focused (or in the Roblox Player), use Shift+F5 / the MicroProfiler as above. Targets: 60 FPS on the
   owner's PC (the Studio cap) with a 1% low of at least 45, as measured in the central slice. Mobile ≥ 30 comes
   later, with the `mobile` profile.
8. Undo if anything is wrong: `LOD_Enabled = false` (live) and/or `revert()` in edit mode.

## Wide world estimate (pattaya_wide, 2026-10-18) — before the import, kept for the history
Counts from the pipeline; Parts are estimated with the builder's rules (the same estimator gives 16,966 for the
central slice vs 16,027 measured, i.e. ~6% high; Textures matched exactly, 11,116).

| | central slice (measured) | new in wide world | wide total |
|---|---|---|---|
| Graph edges / nodes | 614 / 463 | 3,186 / 2,462 | 3,800 / 2,925 |
| Road length (studs) | 102,852 | ~538,600 (Sukhumvit 60,745 express) | 641,494 |
| Junction discs | 312 | 1,380 | 1,692 |
| Buildings | 3,018 | 7,175 (275 merged away by LOD) | 10,193 |
| Parts | 16,027 | ~39,800 (roads+markings 23.2k, buildings 7.2k, roofs 2.7k, props 5.3k, discs 1.4k) | ~56,000 |
| Facade Textures | 11,116 | ~24,500 | ~35,600 |
| Palms / street lights | 157 / 555 | 278 / 1,214 (≈607 more night SpotLights) | 435 / 1,769 |
| Chunk modules | 93 (largest 44 KB) | 444 (largest 13 KB) | 537 |
| Traffic loops / cars | 36 / 464 | 48 / 691 | 84 / 1,155 |

Budget view: with instance streaming a client loads only nearby Atomic chunks, so client cost per view should stay
close to the central slice's (3,700–6,500 Pattaya parts loaded at a time) — the wide areas are less dense than the
centre. The server and Studio hold all ~56k Parts. Re-measure FPS (desktop and a mobile emulator) after the seam
batch and after the whole extension; the night SpotLights (every second lamp) are the first thing to cut if night
FPS drops.

### LOD / thinning options (config, all used by pattaya_wide only)
- `drop_dead_end_sois_shorter_m: 250` (central 120): prunes 1,274 short dead-end sois.
- `clip_polygon_lat_lon`: only land between the sea and Sukhumvit (the first try with a bbox doubled the road length).
- `sidewalk_studs.soi: 0`: new sois have no sidewalk strips (most Thai sois have none) — saves 2 Parts per segment.
- `roads_lod.dash_gap_studs: 32`: lane dashes every 40 studs instead of 20 on new roads (`manifest.dashGap`).
- `layout.light_spacing_studs: 110` (central 70).
- `buildings.lod`: `merge_below_area_studs2` / `merge_gap_studs` / `merge_min_fill` merge small neighbouring
  boxes (shophouse rows) into one when the box still clears all road corridors; `max_per_chunk` caps boxes per chunk
  (140; not reached — the densest new chunk has 137); `facade_min_height_studs` (0 = all keep facades) drops Textures on
  low boxes; `min_area_studs2` as before. Boxes are already single oriented boxes.
Together these cut the new Part estimate from ~66,500 to ~39,800.

### Elevation (Pratumnak hill) — not added, flat as before
A free, no-key DEM exists: AWS Terrain Tiles (terrarium PNG,
`https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`, height = R·256 + G + B/256 − 32768 m).
One z12 tile checked: Pratumnak hill top ~89–96 m, Pra Tumnak Rd ~54 m, Beach Road ~7 m. The Bira team already uses
these tiles (`data/dem/` in their checkout). Not used here because every road, building, prop, traffic car and the
car controller assume one flat road top (y = 1); hills need builder + chassis + traffic work first. If added it must
be an optional config flag, off by default, sampling node heights from the tiles (ODbL-compatible attribution
"Mapzen/Tilezen Terrain Tiles, SRTM and others").

## Leader's first LOD test (2026-10-18, Play at the central grid, night locked at 21:00, Studio unfocused)
- No script errors with PattayaLOD + the new NightLights installed; `PerfProfile.apply("pc")` set the LOD knobs
  (the Workspace streaming properties are not scriptable: the owner sets them by hand, see HOW_TO_PLAY_TH.md).
- PerfProbe: Heartbeat 60/s (p99 18.9 ms), RenderStepped 15/s because Studio was unfocused (`renderLooksFocused=false`,
  so no render FPS claim); InstanceCount 60,188; parts streamed 4,819 (866 in view); textures streamed 2,628,
  visible 444, **hidden by LOD 2,200**; SpotLights streamed 71, **on 9** (all within 350 studs; the cap of 60 was
  not reached); traffic models 46; memory: BaseParts 213 MB, GraphicsTexture 115 MB, Terrain 36 MB.
- Not measured: render FPS with Studio focused, the wide districts at night, mobile.

## Streaming settings check (2026-10-18, owner set MinRadius 512 / TargetRadius 1280 / ModelStreamingBehavior Improved)
- Physics-driven GPS run from the start grid toward Bira at a constant 200 studs/s (above the 160 top speed, nitro
  territory): 22,566 studs covered before the test driver left the road on a bend; 240 of 245 road probes under the
  car hit road, the 5 misses are the moment it went off. No "no road yet" events: streaming kept ahead of the car at
  200 studs/s the whole way. (The crash itself is the test autopilot's yaw rate on a fast bend, not geometry: the
  only collidable parts near the spot are the road, its sidewalks and light poles on the sidewalks.)
- With Studio focused during that run the probe reported render 60 FPS on the corridor.

## Measurement after the road fix, corridor dressing and street furniture (leader, 2026-10-19, Studio unfocused)

World now: Road parts 15,005, discs 495 + 2,853, corridor dressing 2,139 parts, street furniture 9,246 parts (267
Atomic chunks), night (ClockTime 21). PerfProbe at the Central start: parts loaded 8,118, textures 4,068 (visible 460,
LOD hidden 1,088 parts), SpotLights on 11 of 104, traffic models 57. GPS drive Central → Bira at 200 studs/s:
161.5 s, 317/318 probes on road, Heartbeat 60 the whole way (p50 16.9 ms, p99 19.3 ms, worst 20.2 ms), physics step
0.26 ms; parts loaded stayed flat (2,746 mid-corridor, 2,904 at the venue: Opportunistic stream-out works);
memory total 4.4 GB in Studio (GraphicsParts 3.5 MB, GraphicsTexture 180 MB, Instances 156 MB, InstanceCount 54k).
RenderStepped is throttled to 15/s while Studio is unfocused, so render FPS is still unmeasured here.
