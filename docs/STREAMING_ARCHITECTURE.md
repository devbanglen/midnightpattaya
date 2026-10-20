# Streaming architecture (analysis + prototype plan)

team16/streaming-arch, 2026-10-21. Written offline (no Studio). Follows docs/STREAMING_PERFORMANCE.md (team10 audit
and the leader's A/B measurements: the engine's own per-instance stream-in cost is the hitch, not the client scripts).

**Every gain in this document is an ESTIMATE** from a model of the builders and of the engine. Nothing here was
measured. The prototype exists so the leader can measure it. No citywide change is proposed for now.

| File | What it is |
|---|---|
| `tools/mapgen/streaming_analysis.py` | Offline analysis. It reads the exported chunk modules in `build/`, rebuilds each builder's instance list (count, category, position) and simulates streaming. It writes `build/streaming/analysis.json` and `summary.txt`. |
| `roblox/src/ServerStorage/StreamingPrototype.luau` | Edit-mode builder (`Plan` / `Build` / `Probe` / `Remove`) for a separate test district, plus the Play-mode harness (`Server.start`, `Client.run`) |
| `tools/qa/tests/test_streaming_proto.py` | Offline tests, run with `run_all.py`. Among other things they run the Luau planner in the luau CLI and check that it gives the same result as the Python plan. |

## 1. How the model is built (and how far to trust it)

- **Instances.** Each builder is re-created item by item from the chunk modules: PattayaBuilder (edge slabs, fill
  wedges, markings, sidewalks, buildings and their 4 facade Textures, roofs, props, dressing), aprons, furniture,
  coast, landmarks, the vis slice, and the junction and joint discs. Buildings that the vis slice or a landmark
  replaces are left out. SurfaceGui sub-trees are approximated. VisMeshPalms are not modelled.
- **Checked against the leader's Studio numbers:**

  | Check | Model | Studio |
  |---|---|---|
  | PattayaWorld descendants | 182,780 (185,339 with the 8 shoulder chunks) | about 184,000 (before shoulders) |
  | Chunk models per folder | Chunks 93, WideChunks 522, ApronChunks 375, FurnitureChunks 282, VisSliceChunks 59, CoastChunks 48, LandmarkChunks 12, ShoulderChunks 8 (2,536 parts) | the same |
  | Largest WideChunks model | 2,143 | 2,142 |
  | Junctions / WideJunctions | 495 / 2,846 | 495 / 2,853 |
  | Teleport into Chunk_5_3: instances within TargetRadius 1280 | 18,941 | about 19,000 streamed in |
  | Teleport burst | about 21,800 over 7-8 frames (engine budget 3,300 per frame) | 19,000-27,000 over 6-8 frames |

- **Engine model** (an assumption, not documented Roblox behaviour):
  - The pc profile is used: StreamingMinRadius 512, StreamingTargetRadius 1280.
  - A unit is queued when its bounding box comes within TargetRadius. The queue is served nearest first and
    re-ranked every 0.1 s.
  - The engine transfers `ENGINE_BUDGET` = 3,300 instances per frame. This number is calibrated on the measured
    burst.
  - A unit is created in the frame in which its last instance arrives. An Atomic Model therefore lands whole.
  - Frame cost = instances created in that frame x 0.058 ms. That figure is the leader's measured cost per instance
    (throttled Studio, so it is inflated in absolute terms).
  - Persistent units are present from the moment the player joins.
- **Road check.** In each 1/60 s frame, the road unit under the car and the road unit under the point 1 s ahead
  must already be loaded. The road unit is the one holding the nearest road slab, junction disc or apron piece.

## 2. Analysis

### 2.1 What the world is made of (instances, model)

| Category | Instances | Share | Biggest contributors |
|---|---|---|---|
| road (collision ground the car drives on) | 52,918 | 29% | corner fills 14,633, road slabs 13,706, aprons 9,154, sidewalks 6,122, fill wedges 5,962, junction discs 1,696, joint discs 1,645 |
| marking (paint, no collision) | 12,947 | 7% | centre lines 4,532, zebra stripes 4,321, lane dashes 4,094 |
| building | 74,656 | 41% | 9,684 city boxes, of which 8,466 carry 4 facade **Textures** (33,864 Texture instances); vis-slice buildings 25,649; roofs 3,753; landmarks 1,706 |
| detail (props) | 35,944 | 20% | furniture **name signs 11,716** (738 signs, 16 instances each: 2 Parts plus 2 faces of SurfaceGui, labels, paddings, stroke, frame), street lights 7,774, beach umbrellas 6,390, palms 2,898, poles 2,357 |
| container Models | 6,315 | 3% | one Model per road edge (3,818), the chunk models, the Buildings / Props folders |

### 2.2 Per folder (today every chunk is one Atomic Model)

| Folder | Chunks | Instances | Largest chunk | Road | Decorative |
|---|---|---|---|---|---|
| Chunks (central) | 93 | 24,960 | 772 | 5,956 | 18,143 |
| WideChunks (wide + Bira corridor) | 522 | 74,721 | **2,143** | 19,834 | 50,491 |
| ApronChunks | 375 | 24,162 | 490 | 23,787 | 0 |
| FurnitureChunks | 282 | 20,433 | 307 | 0 | 19,869 |
| VisSliceChunks | 59 | 25,708 | 657 | 0 | 25,649 |
| CoastChunks | 48 | 7,737 | 389 | 0 | 7,689 |
| LandmarkChunks | 12 | 1,718 | 683 | 0 | 1,706 |
| Junctions / WideJunctions (loose parts) | | 495 / 2,846 | | all road | |
| ShoulderChunks (Sukhumvit pilot, added on main 2026-10-21) | 8 | 2,559 | 604 | 2,536 | 0 |

The largest chunks are `WideChunks/Chunk_24_2` (2,143), then `Chunks/Chunk_4_2` (772), `Chunk_-2_4` (771),
`Chunk_4_3` (723), `Chunk_4_5` (721), `Chunk_4_1` (704) and `WideChunks/Chunk_40_4` (701).

**Finding: `WideChunks/Chunk_24_2` is a single Atomic Model whose parts span 12,700 x 4,200 studs.** It holds the
Bira corridor roads that are stored in that chunk. Because it is Atomic, all 2,143 instances stream in as soon as any
of its parts comes within range, and that range covers a large part of the east city. In the drive simulation this
model alone is the worst frame of today's layout (2,143 instances, about 124 ms with the 0.058 ms cost per instance).

### 2.3 Density

| Cell | Cells with content | Max per cell | Median | p90 | Densest cells (map cell, instances) |
|---|---|---|---|---|---|
| 512 studs | 593 | 3,917 | 181 | 724 | (2,0) 3,917 · (1,1) 2,987 · (-1,3) 2,940 · (3,-4) 2,690 · (0,2) 2,532 |
| 256 studs | 1,945 | 1,566 | 50 | 227 | (4,0) 1,566 · (5,0) 1,243 · (-2,7) 1,107 · (4,-1) 1,085 · (1,4) 1,056 |

The densest 512-stud cell is map (1280, 256), world (21280, 256): central Beach Road with the vis slice. The
prototype district is centred on world (23140, 1761), the target the leader named, next to Chunk_5_3.

### 2.4 Layouts compared (model)

| Layout | What changes | Atomic units | Largest Atomic | Persistent | Client-built |
|---|---|---|---|---|---|
| **A** today | 512-stud Atomic chunks that mix roads, buildings and props; discs loose | 1,391 | 2,143 | 0 | 0 |
| a | everything in 256-stud Atomic chunks (still mixed) | 1,945 | 1,566 | 0 | 0 |
| b | roads + markings Atomic per 256 cell (cap 1,500, quadrant split); buildings and props Default (each part streams on its own) | 1,628 | 537 | 0 | 0 |
| b2 | b, with the road layer Persistent | 0 | 0 | **67,493** | 0 |
| c | b, with detail props built by the client within 384 studs (200 instances per frame) | 1,628 | 537 | 0 | 35,944 |
| d | b, with buildings Atomic per 256 cell, LevelOfDetail = StreamingMesh, TargetRadius 896 | 3,060 | 1,487 | 0 | 0 |

**Teleport** (empty client stream, then a teleport onto the road nearest world (23140, 1761)):

| Layout | Within MinRadius | Within TargetRadius | Created in total | Frames with > 1,000 instances | Worst frame (instances, est. ms) |
|---|---|---|---|---|---|
| A | 4,974 | 20,629 | 21,775 | 7 | 3,463 (~201 ms) |
| a | 2,331 | 16,230 | 17,501 | 6 | 3,582 (~208 ms) |
| b | 1,373 | 14,192 | 14,871 | 5 | 3,471 (~201 ms) |
| b2 | 1,373 | 14,192 | 8,983 after join | 3 | 3,300 (~191 ms) |
| c | 1,313 | 12,731 | 13,369 (+ client layer) | 4 | 3,325 (~193 ms) |
| d | 2,223 | 7,637 | 8,324 | 3 | 3,339 (~194 ms) |

At the densest cell (world (21280, 256)), the instances within MinRadius are A 12,453, b 7,890, c 6,891 and
d 8,497.

Reading the teleport table:
- The worst frame of a teleport hardly changes with the layout. In the model it is set by the engine's per-frame
  throughput, not by how the world is cut into chunks.
- What the layout does change is how long the burst lasts: 7 heavy frames today against 3-5 with the alternatives.
  Part of the reason is that Atomic chunks overlapping MinRadius pull in their whole content, so A loads 3.6 times
  as much as b inside MinRadius.
- To shorten the teleport hitch itself, fewer instances must arrive at all (layouts c and d, merged meshes), or the
  hitch must be covered (a fade / loading curtain during server teleports, which RaceSessionService-style pre-streams
  already allow).

**Driving** (Sukhumvit Road, the leader's 9,000-stud test route; the area around the start is already loaded):

| Layout | 100 st/s: worst / p99 (instances per frame) | 150 st/s | 200 st/s | Frames > 1,000 | Min road lead at 200 st/s |
|---|---|---|---|---|---|
| A | 2,143 / 114 | 2,143 / 158 | 2,143 / 183 | 1 | 6.2 s |
| a | 365 / 93 | 365 / 121 | 365 / 145 | 0 | 6.4 s |
| **b** | 273 / 49 | 273 / 72 | 273 / 83 | 0 | 6.3 s |
| b2 | 41 / 16 | 41 / 16 | 41 / 19 | 0 | (always loaded) |
| **c** | 273 / 49 | 273 / 67 | 273 / 79 | 0 | 6.3 s |
| d | 165 / 49 | 165 / 63 | 165 / 75 | 0 | 4.4 s |

Estimated worst driving frame at 0.058 ms per instance: A about 124 ms, b and c about 16 ms, d about 10 ms. In the
p99 frame, b is about 55% below A.

### 2.5 Will road collision ever be missing under the car? (model)

- **Driving forward at 100, 150 or 200 studs/s:** the model gives 0 frames with no road under the car in every
  layout. Road arrives 4-12 s before the car reaches it.
- **Cold-start stress test** (fresh stream, 200 studs/s, engine throughput cut to 150, 300 or 600 instances per
  frame to stand in for a weak phone or a bad link):
  - 0 frames with no road under the car.
  - With 150 instances per frame, 1 frame with no road at the point 1 s ahead, in every layout except b2.
- **Teleport and drive off at once** (150 studs/s, and 200 studs/s on a slow client): 0 missing frames. The road under
  the car arrives in frame 0, because it is the nearest unit.
- The difference between layouts is **what has to arrive together with that road**:
  - A: up to a 2,143-instance mixed chunk, which can be about 120 ms of stall in that same frame.
  - b / c: one road cell of at most about 540 instances (cap 1,500), with no decoration.
- **Where real risk remains** (outside the model):
  - `StreamOutBehavior = Opportunistic` under memory pressure.
  - Engine ordering that is not strictly nearest first.
  - Atomic transfers of very large models on slow links.
  - Physics: the car touches down on a part that arrives in the same frame.

  Layout b2 (Persistent roads) removes the road risk by construction. It costs 67,493 instances at join and in
  memory (37% of the world) on every device. That is too much for phones as the world is today. After the road merge
  in §3 step 4 it could be reconsidered.

## 3. Recommended architecture (estimates; to be confirmed by the prototype)

1. **Road layer apart from decoration.** Roads, sidewalks, junction and joint discs, aprons, corner fills and
   markings go into Atomic road cells of 256 studs, capped at 1,500 instances (split into 128 / 64 quadrants above
   the cap). A road cell never holds decoration, and decoration never holds road. This is layout b.
   - Expected: worst driving frame about 2,143 → about 273 instances (about 124 → about 16 ms est.); p99 -55%.
     Instances inside MinRadius after a teleport -35 to -75%, depending on the target.
2. **Decoration non-atomic.** Buildings (body + Textures) and props are Default Models (each part streams on its own)
   in cells of 256 studs. A building whose parts must appear together, such as a vis-slice building Model, stays one
   small Atomic Model, which is still far smaller than a chunk.
3. **Progressive detail layer (layout c).** Detail props (furniture, palms, lights, signs, coast props) are not
   streamed by the engine. The client builds them within about 384 studs at 200 instances per frame, from data rows
   in production; the prototype uses templates in ReplicatedStorage.
   - Expected: about -10% instances inside TargetRadius, and the client work is bounded per frame.
   - Cost: client Lua and memory for the data.
   - The collision of solid props (poles, trunks) becomes client-only. That is fine for the client-owned car, but
     server-side checks no longer see them.
4. **Fewer instances (the largest lever, unchanged from team10):**
   - Merge the aprons and corner fills (23,787 instances, 13% of the world) per junction into a few parts or meshes.
   - Replace the 33,864 facade Textures with one atlas mesh per building.
   - Shrink the name-sign GUI tree from 16 to about 5 instances per sign (about -8,000).
   - Split `WideChunks/Chunk_24_2`.
   - Expected: about -30 to -35% of all instances (about -60,000), which shortens teleport bursts in proportion.
5. **LOD (layout d): only after a Studio check.** Check whether `Model.LevelOfDetail = StreamingMesh` renders
   imposters for these Models in this place. If it does, TargetRadius can drop to about 900 without losing the
   skyline.
   - Expected: about -45% instances within TargetRadius after a teleport, and worst driving frame about 165
     instances.
   - Risk: imposter quality and the cost of generating them are unknown.
6. **Streaming-safe rendering, kept:** the WorkQueue budget, content preload with stream-ahead off (leader run F), and
   a pre-stream before every server teleport (`RequestStreamAroundAsync`). Covering the residual teleport burst with a
   short fade is a separate UI decision.

## 4. The prototype experiment (approved: variants A and B; C and D later)

### 4.1 What the prototype is

- `StreamingPrototype.Build(v)` clones every top-level part of PattayaWorld whose position lies within ±1,536 studs
  of world (23140, 1761). The source folders are:
  - Chunks, WideChunks;
  - Apron, Furniture, VisSlice, Coast, Landmark and **Shoulder** chunks;
  - the junction discs, VisMeshPalms and the gate.
- The copy goes to `workspace.StreamingProto`, shifted +60,000 studs in X. It has its own flat ground (a few
  Persistent parts, top at y = -2, no terrain).
- **ShoulderChunks** (the Sukhumvit shoulder pilot, which includes the narrowing at about (24550, 900)) are road
  collision in every variant, in the same layer as the roads and aprons. Every part of `ShoulderChunks` and
  `ApronChunks` gets `ProtoCat = "road"`.
- Variants (the tests check that the Luau planner gives the same result as the Python plan):
  - **A** control: one Atomic Model per source chunk; discs and palms loose.
  - **B** road layer (roads, sidewalks, discs, aprons, corner fills, shoulders, markings) Atomic per 256-stud cell,
    capped at 1,500 instances; buildings and props Default.
  - C and D later.
- **Parity: A and B copy exactly the same source parts.** Only grouping and streaming mode differ. In Edit mode,
  `P.ParityText()` prints the table below (Studio counts) and `P.Parity()` returns it. Unit tests check parity in
  Python and in the luau CLI.

  Offline model of the parity table ("items" = modelled part groups; Studio counts BaseParts, so its parts column
  will be higher where a triangle is 2 WedgeParts):

  | Source folder | A items | A instances | B items | B instances |
  |---|---|---|---|---|
  | ApronChunks | 1,550 | 3,079 | 1,550 | 3,079 |
  | Chunks | 3,769 | 8,547 | 3,769 | 8,547 |
  | FurnitureChunks | 333 | 3,193 | 333 | 3,193 |
  | Junctions | 135 | 135 | 135 | 135 |
  | **ShoulderChunks** | 1,014 | 1,871 | 1,014 | 1,871 |
  | VisSliceChunks | 6 | 244 | 6 | 244 |
  | WideChunks | 3,040 | 7,483 | 3,040 | 7,483 |
  | WideJunctions | 203 | 203 | 203 | 203 |
  | **total** | 10,050 | **24,755** | 10,050 | **24,755** |

- In the copy, road instances total 8,662 (shoulders included). Largest Atomic unit: A 748, B 841 (a road cell with
  shoulders).
- **The source world is only read.** Parts are `Clone()`d. Nothing in PattayaWorld is moved, changed or destroyed;
  a test checks the source for this.
- The copy carries attributes:
  - `ProtoCat` (road / marking / building / detail / ground) and `ProtoSrc` on every copied part.
  - `Mode`, `Layer` and `Expect` on every container.
  - On the root: `Index` (JSON), `Boot`, `ColdSeconds`, and `ProtoPath`. ProtoPath is a drive path along the named
    road with the most slab length in the district. It is kept only where a downward ray hits a road part of the copy.
- `Build` also installs:
  - a copy of the module as `ReplicatedStorage.StreamingPrototype`;
  - two boot scripts, `ServerScriptService.StreamingProtoBoot` and `StarterPlayerScripts.StreamingProtoBootClient`.
    They run only in Studio and only when `StreamingProto.Boot` is not `"off"`. Build sets it to off.

**`Build()` is a Place change.** It adds about 25k instances and two small scripts. The leader runs it **only after
the owner confirms a fresh .rbxl backup.**

### 4.2 Run modes and what each run reports

| Mode | How it starts |
|---|---|
| **cold** | `P.SetBoot("cold")`, then a fresh Play. At join, the boot server script seats the first player in the nearest race car (`PattayaTestKitServer.seat`) and moves that car to the proto path start **without** `RequestStreamAroundAsync` (anchored 0.3 s). The proto has never been streamed to this client. The client records from the moment its boot script starts, right after join, for `ColdSeconds` (30 s). Road checks start once the car is inside the proto. |
| **teleport** | `P.SetBoot("teleport")`, then a fresh Play. The car is seated where the player spawned (city). After 15 s the client asks the server to teleport it into the proto (`PattayaTestKitServer.teleport`, which pre-streams like the game) and records 20 s. |
| **drive 100 / 150 / 200** | Run automatically after cold or teleport, in the same session. Each drive follows `ProtoPath` (PattayaTestKit.drivePath, CFrame mode), alternating forward and reverse, and each is recorded separately. |

Every recorded window prints one `[StreamProto]` line (`_G.StreamProto.runs` holds them all; `P.Client.report()`
joins them):
- avg FPS, p99 frame ms, 1% low FPS (mean of the slowest 1% of frames), worst frame, frames over 50 ms and over
  100 ms;
- instances added per frame (max, p99, total);
- road-missing frames under the car, plus 0.5 s and 1 s ahead in drives. These are counted against the copied road
  layer (`ProtoCat == "road"`: roads, discs, aprons, corner fills, shoulders); a ray that hits the proto ground or
  nothing counts as missing;
- when the car entered the proto and when the first road was under it;
- completeness inside MinRadius and inside TargetRadius;
- memory total and by tag (Instances, PhysicsParts, PhysicsCollision, GraphicsParts, GraphicsMeshParts,
  GraphicsTexture, GraphicsSolidModels, Gui, LuaHeap, Script), each with the change over the window.

### 4.3 Leader run sequence (A and B, 3 fresh Play runs per variant and start mode)

Edit mode, after the owner has confirmed the backup:

```lua
local P = require(game.ServerStorage.StreamingPrototype:Clone())
print(P.ParityText())                  -- must end in "PARITY OK" (changes nothing)
print(P.Plan("A")); print(P.Plan("B"))
print(P.Build("A")); print(P.Probe())
print(P.SetBoot("cold"))               -- then SAVE
```

1. **A, cold**: 3 fresh Play sessions. Each one runs by itself: cold 30 s, then drive 100, 150, 200 (about 1 minute
   in total). After each session, copy the four `[StreamProto]` lines from the client output, or run
   `print(require(game.ReplicatedStorage.StreamingPrototype).Client.report())` on the client. Then stop Play.
2. **A, teleport**: Edit `print(P.SetBoot("teleport"))`, save, then 3 fresh Play sessions: teleport 20 s, then the
   three drives.
3. **B**: Edit `print(P.Build("B"))` (it removes A first), `print(P.ParityText())`, `print(P.SetBoot("cold"))`,
   save. Then 3 fresh cold sessions, then `SetBoot("teleport")`, save, and 3 fresh teleport sessions.
4. **End**: Edit `print(P.Remove())` must end in "leftovers: none". `print(P.Leftovers())` must print an empty
   string. Save. Or keep B for later C/D runs.

That is 12 Play sessions in total: 2 variants x 2 start modes x 3, each about 1-1.5 minutes. The minimum, if time is
short, is 3 cold sessions per variant: they also contain the drives.

### 4.4 Pass / fail (B against control A, medians of 3 runs)

| Measure | Pass |
|---|---|
| Parity (`P.ParityText()`) | PARITY OK before every run set (hard fail otherwise) |
| Road missing (under the car, 0.5 s ahead, 1 s ahead) in drive 100 / 150 / 200 | **0 in every run** (hard fail otherwise) |
| Road missing under the car in cold and teleport | ≤ A, and first road under the car ≤ A |
| Drive worst frame | ≤ 60% of A |
| Drive p99 | ≤ 80% of A |
| Drive 1% low FPS | ≥ A |
| Instances added per frame (drive): max | ≤ 900 (B's largest road cell is 841) |
| Instances added per frame (drive): p99 | ≤ A |
| Cold / teleport frames > 100 ms | ≤ 75% of A |
| Cold / teleport worst frame | not worse than A + 10% |
| Completeness inside MinRadius at the end of a window | 100% |
| Memory total at the end | ≤ A + 5% |

Notes on the test setup:
- The proto lies 60,000 studs from the city. In teleport mode the city also streams out, and both variants pay that
  the same.
- The cold window also contains the city stream-in around the spawn during the first second or two, before the car
  is moved. It is the same for A and B.
- The drive path is one district long, shorter than Sukhumvit.
- The proto has no terrain; a ray that hits the proto ground counts as "road missing".

### 4.5 Rollback

- In Edit mode, `require(game.ServerStorage.StreamingPrototype:Clone()).Remove()`. It deletes:
  - `workspace.StreamingProto` and `workspace.StreamingProtoClient`;
  - `ReplicatedStorage.StreamingPrototype`, `StreamingProtoRemote` and `StreamingProtoDetail`;
  - `ServerScriptService.StreamingProtoBoot` and `StarterPlayerScripts.StreamingProtoBootClient`;
  - any `StreamProto*` attribute on workspace or ReplicatedStorage (none are set; checked anyway).

  It returns "leftovers: none" when the place is clean. `P.Leftovers()` lists anything that remains (empty = clean).
  A test in the luau CLI checks this with a mock place, and checks that PattayaWorld, PattayaRemotes and other
  attributes stay.
- Then save.
- Player attributes (`StreamProtoSeated` / `StreamProtoArrived`) exist only during a Play session.
- No world, streaming or lighting setting is changed by Build.
- Full fallback: the owner's .rbxl backup.

## 5. A later citywide migration (plan only; not to be executed)

- **Approach: re-parent in place, not rebuild.** An Edit-mode, resumable migration moves the existing parts of
  PattayaWorld into the new containers by the same rules as the prototype. Every tuned state is kept (vis-slice
  replacements, stashes, RoadLook state, IDs).
- **Code that depends on today's structure** (it must change first, then be tested):
  - PattayaLOD: `Parent.Parent.Name`, the per-root DescendantAdded hooks.
  - PattayaRoadLook and PattayaNightLights: PattayaWorld-wide hooks keep working; check the folder names.
  - PattayaVisSliceBuilder (`Chunks/Chunk_<src>`, backups per chunk name).
  - PattayaLandmarksBuilder (`replaces` by chunk).
  - PattayaBuilder: RebuildChunks, Extend, RemoveExtension, base-conflict handling.
  - The Apron, Furniture and Coast builders' Remove / Probe.
  - The per-edge road Models carry `EdgeId` / `OsmWay` / `Tier`. Flattening them into cells drops these. Keep them as
    part attributes, or keep the edge Models inside the road cells. This needs a decision first.
  - Leader probes and the QA road audit (slab-overlap probe and `RoadFill` skips).
  - PattayaTestKit `isRoadHit` (names, unchanged).
  - The install and rebuild docs.
- **Effort (estimate):**
  - 2-3 days of builder and script changes plus offline tests.
  - 1 day for the migration script with Probe, dry run and undo.
  - 1-2 Studio sessions for the leader: measure, then a 30-minute drive through every district, mobile included.
- **Order:**
  1. Prototype pass.
  2. §3 step 4 instance cuts (separate approvals: aprons, textures, signs, Chunk_24_2).
  3. Migrate one district.
  4. Measure.
  5. The rest by batches, with the backup taken before each batch.
- **Risks:**
  - Imposters (D) and Persistent roads (b2) are not part of the migration until they are measured.
  - Default-mode decoration may show buildings half-streamed for a moment, because each part arrives on its own.
    Buildings that must not do that stay small Atomic Models.
  - The client detail layer needs data rows in ReplicatedStorage (join size) and a client builder with a time
    budget, which is new code.
- **Rollback of a migration:**
  - The pre-batch backup.
  - The migration writes each part's old parent path as an attribute, so a reverse pass can restore the structure
    without a backup.

## 6. Reproduce

```
D:\ROBLOXRACE\.venv\Scripts\python tools\mapgen\streaming_analysis.py     # build/streaming/analysis.json, summary.txt
D:\ROBLOXRACE\.venv\Scripts\python tools\qa\tests\run_all.py -k streaming_proto
```

Model parameters (top of `streaming_analysis.py`):

| Parameter | Value |
|---|---|
| `ENGINE_BUDGET` | 3300 |
| `COST_MS` | 0.058 |
| `CLIENT_BUDGET` | 200 |
| `NEAR_RADIUS` | 384 |
| `LOD_TARGET` | 896 |

`analysis.json` also has `teleport_budget_sensitivity` (1,500 / 3,300 / 6,000 per frame) and `drive_stress`.
