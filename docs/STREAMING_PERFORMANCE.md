# Streaming performance (client stream-in hitches)

team10/streaming, 2026-10-20. Written offline (no Studio). Every cost below is an **estimate** from reading the code;
the leader measures. Nothing in this branch changes world data, physics, the car or the camera.

## Problem

With `Workspace.StreamingEnabled = true` the world arrives as **Atomic 512-stud chunk Models** (PattayaBuilder,
PattayaApronBuilder, PattayaFurnitureBuilder, PattayaCoastBuilder). An Atomic model streams as one unit, so its whole
subtree (hundreds of Parts, their Textures and lights) arrives in one replication step. PattayaWorld is about 184k
descendants (about 133k Parts, 1.8k MeshParts). After joining, a teleport, or fast driving (150-215 studs/s), frames
spike to 100-200 ms for 10-20 s; steady state is 60 fps.

## Leader measurement (2026-10-20, Studio Play)

Render was throttled to about 15 fps, so absolute ms are inflated; the A/B comparison is valid.

| Setup | Stream-in after a teleport into a dense area | Cost per instance | Worst frame |
|---|---|---|---|
| PattayaLOD, PattayaNightLights, PattayaRoadLook, VisMeshPalmLOD **disabled** | 22-27k instances over 6-8 frames | 0.072 ms | 570 ms |
| the same scripts **enabled** (comparable area) | 22-27k instances over 6-8 frames | 0.058 ms | 275 ms |

Conclusion: **the client look scripts are not the main cause.** The engine's own per-instance stream-in cost
(creating the instances, adding them to physics and the renderer, fetching their content) is. So the script changes
in this branch are small and only flatten the scripts' share of the burst. Most of the effort went into
`PattayaPreload` (ask for the world earlier and fetch shared textures early). The structural fixes (fewer instances
per chunk) are listed at the end as proposals only.

## Audit: client work per streamed instance

Scope: every script in `roblox/src/StarterPlayer/StarterPlayerScripts`, `roblox/src/ReplicatedStorage` (and the
loading screen in ReplicatedFirst). "Burst" = estimated extra Lua time in the frame(s) when one Atomic chunk of about
600 Parts arrives (about 300 facade Textures, a few dozen lamps / SpotLights / NightNeon parts), **before** this branch.
Ranked by that estimate.

| # | Script | Signal / scan | Work per instance (before) | Est. burst per 600-part chunk (before) | Periodic full scans (before) | Now |
|---|---|---|---|---|---|---|
| 1 | PattayaNightLights | `workspace.DescendantAdded` (every instance in workspace) + `PattayaWorld.DescendantAdded` + `workspace.DescendantRemoving` | 2-3 IsA + 2 GetAttribute per Part; per Texture / Lamp / NeonSign a `task.defer(apply)`: 2 SetAttribute + 3-4 GetAttribute + Texture id + 2 tile writes; NightNeon parts: Material + Color writes; every deferred call runs in the same frame | about 2-5 ms (more at night: Material switches) | day/night change: `PattayaWorld:GetDescendants()` (one array of every streamed instance) then `apply` on 4000 per frame, plus every NightNeon part restyled in **one** frame; preset change: every lamp / sign / neon restyled in one frame; SpotLight budget every 0.25 s (all registered lights, `IsDescendantOf` each, one small table per near light) | queued (budget), registry instead of the world walk, writes only on change |
| 2 | PattayaRoadLook | `PattayaWorld.DescendantAdded` / `DescendantRemoving` | IsA + name lookup; road / mark / walk parts: `ML.save` (5 reads + 1 table) at once, styling (Material, MaterialVariant, Color, Reflectance writes) queued | about 0.5-1 ms at arrival, then up to 400 parts styled per frame with no time limit (Material writes are the expensive part) | start-up `GetDescendants()` (chunked 5000/frame); look change: all records queued (count budget) | styling inside the shared **time** budget |
| 3 | PattayaLOD | `DescendantAdded` / `DescendantRemoving` on PattayaWorld and every `Circuit_*` | 2 IsA + Parent.Parent.Name; then the whole queue registered on the next Heartbeat (IsDescendantOf, IsA, GetAttribute, 1 table per record) and a new queue table each frame | about 0.5-1.5 ms in the next frame | start-up `GetDescendants()` per root (chunked 5000/frame); sweep 300 records per frame (a teleport can flip all 300, each flip writes several Texture.Transparency) | registration inside the shared budget; sweep also capped at `LOD_SweepMs` |
| 4 | VisMeshPalmLOD (ReplicatedStorage copy of `ServerStorage/VisMeshPalmLOD.luau`) | `VisMeshPalms.ChildAdded` (`task.defer(add)`), one `ChildAdded` per palm model, `ChildRemoved` | GetPivot + GetChildren + GetAttribute per part; remove = `table.find` over all palms; the per-model connection was never disconnected | small (palms are few) | sweep 60 palms per frame; each flip creates 1 tween per part | O(1) remove, connection disconnected, sweep capped at 1 ms |
| 5 | PattayaPerfProbe (module) | none at stream time | only when the `PerfProbe` attribute is set: `GetDescendants()` of every world root (chunked) | 0 (on demand) | on demand only | unchanged (not mine) |
| 6 | PattayaTraffic.client | none (builds its own client cars) | n/a | 0 | per-frame allocations (`seen = {}` etc.) in Heartbeat; not streaming-related | unchanged (not mine) |
| 7 | PattayaJobsClient, PattayaRaceClient, PattayaChallengeClient, PattayaSprintClient, PattayaEventsClient | none | `GetChildren()` of small fixed folders (stands, checkpoints) in RenderStepped / on events | 0 | small per-frame GetChildren while stopped near a stand (Jobs) | unchanged (not mine) |
| 8 | MidnightHUD | `TouchGui:GetDescendants()` on layout change only | n/a | 0 | layout change only | unchanged (not mine) |
| 9 | PattayaMinimapClient | `PlayerGui.ChildAdded` | n/a | 0 | none | unchanged |
| 10 | CarController, MidnightCamera, MidnightSpeedo, MidnightActivity, PattayaGPSClient, PattayaGarageClient, CircuitRaceClient, PattayaPerfTelemetry, MidnightLoading, MidnightUI modules | none | n/a | 0 | none relevant to streaming | unchanged |

No client script uses CollectionService.

## What changed (this branch)

All changes keep the end state identical once the queues have drained: the same lights, materials and LOD state.

### `ReplicatedStorage/PattayaWorkQueue.luau` (new, installed by `tools/studio/install.ps1` with the other ReplicatedStorage modules)

Deduplicated FIFO queues (`WQ.new(name, fn)`, `q:push(item)`, `q:cancel(item)`, `q:size()`). All queues share one
per-frame **time** budget on Heartbeat (`os.clock()`), round robin between queues, at least one item per frame. The
Heartbeat connection exists only while something is pending, so the steady state costs nothing; the item array is
reused (no per-frame allocation). Each item runs in `pcall` (a failing item warns, the rest go on).
`require(game.ReplicatedStorage.PattayaWorkQueue).stats()` shows pending / processed per queue and the worst frame.

Every script falls back to its old behaviour if the module is missing (waits up to 10 s for it at start).

### PattayaNightLights

- NightNeon parts, floodlight parts and the world candidates (facade Textures, `Lamp`, `NeonSign`) go through three
  queues instead of `task.defer` per instance (same "a frame later" timing, now within the budget).
- Day/night change: re-applies the **registered** facade Textures, lamps and signs (registry kept as they are
  applied, dropped on `DescendantRemoving`) instead of `PattayaWorld:GetDescendants()`; NightNeon parts are queued
  instead of restyled in one frame. Preset change: lamps, signs and NightNeon parts are queued (SpotLights still
  restyled at once, they are few).
- `apply` writes Texture id and tile size only when they differ (same result, fewer writes).
- Unchanged: lighting presets, SpotLight budget, car lights, all attributes (`PattayaLighting`, `LightingPreset`,
  `NightExposure`, `NightSky`, `LOD_Enabled`, `LOD_SpotCap`, ...).

### PattayaRoadLook

With the module, the styling queue uses the shared time budget instead of 400 parts per frame; a part that streams
out while queued is cancelled. Without the module: the old ROAD_BUDGET queue. `RoadLook` / `LightingPreset` behave as
before; `_G.PattayaRoadLook.stats().queued` counts both queues.

### PattayaLOD

Streamed Textures / props are registered through the queue (dedupe, cancel on stream-out) instead of the whole queue
in the next Heartbeat. The sweep also stops after `LOD_SweepMs` (default 1.0 ms) in a frame; the cursor keeps its
place. `LOD_Enabled`, `LOD_FacadeRange`, `LOD_PropRange`, `LOD_Budget` unchanged.

### VisMeshPalmLOD (`roblox/src/ServerStorage/VisMeshPalmLOD.luau`, installed as the ReplicatedStorage copy)

O(1) removal (index on the record), the per-model `ChildAdded` connection is disconnected on removal, the sweep is
capped at 1 ms per frame (BUDGET 60 kept). `FullRange` unchanged. The starter LocalScript is unchanged.

### PattayaPreload (new LocalScript)

1. **Stream ahead.** While the local player drives a RaceCar (Humanoid.SeatPart is a VehicleSeat whose parent has
   `RaceCar`, as `PattayaTestKit.car()`), and `HUD_SpeedKmh` (CarController telemetry, studs/s 1:1) is at least
   `Preload_MinSpeed` (80): `LocalPlayer:RequestStreamAroundAsync(point, Preload_Timeout)` with the point
   `speed * Preload_LeadSeconds` (4 s) ahead along the chassis' horizontal velocity, clamped to 600-900 studs. At most
   one request in flight, at most one per `Preload_Interval` (1.5 s), and only when the point moved at least
   `Preload_MinMove` (250 studs). Checked every 0.2 s from a `task.wait` loop (no per-frame work). Read-only towards
   the car. Only with `workspace.StreamingEnabled`.
   Expected effect: chunks on the road ahead are requested 3-4 s before the car reaches them, so they arrive while
   the car still has the current area loaded and are less likely to arrive together with the chunks around the car.
   It does not make an instance cheaper to create.
2. **Content preload** once after `game.Loaded`: `ContentProvider:PreloadAsync` in batches of 6 (0.1 s apart) for all
   ids in `ReplicatedStorage.MaterialLibraryMaps`, the facade tiles on PattayaWorld (`Facade_*` **and**
   `FacadeNight_*`, so the first dusk switch does not fetch night tiles mid-drive), every MaterialVariant in
   MaterialService and the SurfaceAppearance templates in `ReplicatedStorage.MaterialLibraryAssets`.
   `ServerStorage.VisAssetsManifest` is not visible to clients and holds Model (package) ids, not mesh ids, so kit
   meshes are not preloaded (see proposals).
3. `_G.PattayaPreload.stats()` from the client command bar: request count, failures, last / worst request time,
   last target, content counts.

## Switches (all workspace attributes, live)

| Attribute | Default | Effect |
|---|---|---|
| `WorkQueue_Enabled` | true | false = every queue drains completely on the next Heartbeat (old all-at-once behaviour) |
| `WorkQueue_BudgetMs` | 1.5 | shared Lua time budget per frame for all queues |
| `LOD_SweepMs` | 1.0 | PattayaLOD sweep time cap per frame (`LOD_Budget` still caps the count) |
| `LOD_Enabled` | true | unchanged: false = PattayaLOD shows everything and idles, SpotLight cap lifted |
| `Preload_Enabled` | true | false = PattayaPreload does nothing (no stream requests, no content preload) |
| `Preload_StreamAhead` | true | false = content preload only |
| `Preload_MinSpeed` / `Preload_LeadSeconds` / `Preload_AheadMin` / `Preload_AheadMax` | 80 / 4 / 600 / 900 | stream-ahead point |
| `Preload_Interval` / `Preload_MinMove` / `Preload_Timeout` | 1.5 s / 250 / 2 s | throttling |

Full rollback of this branch without a code revert: `WorkQueue_Enabled = false`, `Preload_Enabled = false`
(VisMeshPalmLOD's O(1) removal and 1 ms cap have no switch; they do not change what is shown).

## Risks

- **Day/night and preset switches now ripple** across frames instead of happening in one (big) frame: for a short
  time some lit windows / lamps / facades are in the old state. The state is the same once the queues drain (at
  1.5 ms per frame, expected well under a second for one area).
- Streamed-in NightNeon / facade / road parts can show their builder look a few frames longer during a heavy burst
  (they did for one frame before).
- `RequestStreamAroundAsync` makes the client keep more of the world in memory (regions ahead); on low-memory phones
  the engine streams out more aggressively. Watch `PerfTelemetry` memory on a real phone; `Preload_StreamAhead =
  false` if it hurts. Each request also costs the server some work (one request per 1.5 s per fast driver).
- If `RequestStreamAroundAsync` turns out not to be callable from the client in a given Roblox version, the pcall
  catches it, warns three times at most, and the script keeps working with content preload only.

## How to measure (leader)

1. Same teleport into a dense area as the measurement above, with `WorkQueue_Enabled` true vs false, and
   `Preload_Enabled` true vs false. Read `require(game.ReplicatedStorage.PattayaWorkQueue).stats()` (worst frame,
   pending) and the PerfTelemetry p99 / worst.
2. A straight drive at 200 studs/s into a not-yet-streamed area with `Preload_StreamAhead` true vs false; compare
   worst frame and how often frames over 100 ms occur in the "drive150" phase. `_G.PattayaPreload.stats()` shows
   whether requests were made and how long they took.

## Structural proposals (not done; world data not changed)

Since the engine's per-instance cost dominates, the real wins are fewer instances per arrival:

1. **Fewer instances per chunk: merged meshes.** Bake each chunk's static decorative geometry (facade boxes and their
   Textures, window tiles, sidewalk pieces, kerbs, furniture) into a few MeshParts per chunk (the mesh-opt pipeline
   already merges tiles). Facade Textures are separate instances: one atlas-mapped mesh per building removes most of
   them. Expected: per-instance cost scales with count, so 10x fewer instances is the largest possible lever.
2. **Non-Atomic streaming for decorative folders.** Atomic forces a chunk's whole subtree into one step. For pure
   decoration (furniture, coast props, aprons, signs), `ModelStreamingMode = Default` / `Nonatomic` (or parts not
   inside a model) lets the engine stream parts individually by distance, spreading the cost over more frames. Keep
   Atomic only where all pieces must appear together (roads with their markings, buildings whose parts must not
   show half-built).
3. **Smaller chunks** (256 studs) for dense districts: same total, smaller single steps.
4. **Decorative parts out of physics:** `CanCollide = false`, `CanTouch = false`, `CanQuery = false`, and
   `CollisionFidelity = Box` on decorative MeshParts reduce the physics broadphase insert cost of every streamed part.
5. **Server-side stream before teleports:** every server teleport (garage, race start, events, jobs, test kit) calls
   `player:RequestStreamAroundAsync(destination)` before moving the car (RaceSessionService does this for one path).
6. **Streaming properties to try:** `StreamingTargetRadius` / `StreamingMinRadius` (smaller min radius = less forced
   before the car can move), `StreamOutBehavior = Opportunistic` (memory), and Model `LevelOfDetail =
   StreamingMesh` on large chunk models so the far city is an imposter mesh instead of full instances.
7. **A client-visible preload manifest:** the server (or the build pipeline) writes the distinct kit MeshIds /
   TextureIDs into a ReplicatedStorage module, so PattayaPreload can fetch mesh content in the first seconds too.
