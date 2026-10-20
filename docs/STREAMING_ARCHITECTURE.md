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
  | PattayaWorld descendants | 182,780 | about 184,000 |
  | Chunk models per folder | Chunks 93, WideChunks 522, ApronChunks 375, FurnitureChunks 282, VisSliceChunks 59, CoastChunks 48, LandmarkChunks 12 | the same |
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

## 4. The prototype experiment

### 4.1 What the prototype is

- `StreamingPrototype.Build(v)` clones every top-level part of PattayaWorld (the Chunks, WideChunks, Apron,
  Furniture, VisSlice, Coast and Landmark chunks, the junction discs, VisMeshPalms and the gate) whose position lies
  within ±1,536 studs of world (23140, 1761).
- The copy goes to `workspace.StreamingProto`, shifted +60,000 studs in X. It has its own flat ground (a few
  Persistent parts, top at y = -2, no terrain).
- It is re-chunked per variant. Variants A-D are the same as the Python plan (the tests check that the Luau planner
  and the Python planner agree):
  - **A** control: one Atomic Model per source chunk; discs and palms loose.
  - **B** roads Atomic per 256 cell + decoration Default.
  - **C** B + the detail layer built by the client.
  - **D** B + building cells Atomic with LevelOfDetail StreamingMesh.
- Size of the district copy (model): **22,884 instances**:
  - roads 6,791, markings 1,532, buildings 11,603, detail 2,958.
  - Largest Atomic unit: A 748, B/C/D 299 (roads).
- **The source world is only read.** Parts are `Clone()`d. Nothing in PattayaWorld is moved, changed or destroyed;
  a test checks the source for this.
- The copy carries attributes:
  - `ProtoCat` (road / marking / building / detail / ground) and `ProtoSrc` on every copied part.
  - `Mode`, `Layer` and `Expect` on every container.
  - On the root: an `Index` (JSON) and `ProtoPath`, a drive path along the named road with the most slab length.
    It is kept only where a downward ray hits a road part of the copy.
- `Build` also puts a copy of the module in ReplicatedStorage for the client harness. `Remove()` takes it out again.

**`Build()` is a Place change.** It adds about 23k instances, and variant C also adds templates in ReplicatedStorage.
The leader runs it **only after the owner confirms a fresh .rbxl backup.** Rollback: `P.Remove()`, or the backup.

### 4.2 Leader run steps

Edit mode, after the owner has confirmed the backup:

```lua
local P = require(game.ServerStorage.StreamingPrototype:Clone())
print(P.Plan("A")); print(P.Plan("B"))         -- dry run, changes nothing
print(P.Build("A")); print(P.Probe())          -- then save the place
```

Play, fresh session per run.

Server:

```lua
require(game.ServerStorage.PattayaTestKitServer).start()
require(game.ServerStorage.StreamingPrototype).Server.start()
```

Client:

```lua
local TK = require(game.ReplicatedStorage.PattayaTestKit); TK.seatIn()
local P = require(game.ReplicatedStorage.StreamingPrototype)
P.Client.run({mode = "teleport"})                          -- 20 s after the teleport into the proto
P.Client.run({mode = "drive", speed = 150})                -- settle 8 s, then drive ProtoPath
P.Client.run({mode = "teleport_drive", speed = 200})       -- drive off at once (road stress)
-- also: speed = 100; prestream = false (teleport without RequestStreamAroundAsync)
```

- Stop Play, then `P.Build("B")`, save, and repeat. Then do C, and D if wanted.
- For D, optionally run with `StreamingTargetRadius = 896` (`PattayaPerfProfile`: apply and revert).
- Each run prints one `[StreamProto]` line, and `_G.StreamProto.result` holds the table. The line contains:
  - frames, worst / p99 / p95 / median ms, frames over 50 ms and over 100 ms;
  - instances added per frame (max, total) and the client layer's maximum per frame;
  - road-missing frames under the car, 0.5 s ahead and 1 s ahead;
  - time to the first road under the car;
  - completeness inside MinRadius and inside TargetRadius;
  - memory total and the per-tag change (Instances, PhysicsParts, GraphicsParts, GraphicsTexture, ...).
- Run each variant and mode at least 3 times. Run-to-run spread in Studio is large (leader runs B vs E).

### 4.3 Pass / fail (B or C against control A, same session, medians of 3 runs)

| Measure | Pass |
|---|---|
| Road missing (under the car, 0.5 s ahead, 1 s ahead) in drive at 100 / 150 / 200 st/s | **0 in every run** (hard fail otherwise) |
| Road missing under the car in teleport_drive 200 | 0, and first road under the car ≤ A |
| Drive worst frame | ≤ 60% of A |
| Drive p99 | ≤ 80% of A |
| Max instances added in one frame (drive) | ≤ 700 (A: up to one full chunk) |
| Teleport frames > 100 ms | ≤ 75% of A |
| Teleport worst frame | not worse than A + 10% |
| Completeness inside MinRadius at the end of a run | 100% (≥ 99% in teleport_drive) |
| Memory total after the run | ≤ A + 5% |
| C only: client layer per frame | ≤ 200 + one template; no visible gaps inside about 250 studs (screenshot check) |
| D only | imposters visible beyond TargetRadius (screenshot); otherwise D is dropped |

Notes on the test setup:
- The proto lies 60,000 studs from the city. A teleport into it also streams the city out, and every variant pays
  that the same.
- The drive path is shorter than Sukhumvit (one district).
- The proto has no terrain, so the ground parts stand in for it. A ray that hits the ground counts as "road missing".

### 4.4 Rollback

- Remove the prototype: `require(game.ServerStorage.StreamingPrototype:Clone()).Remove()` in Edit mode. It deletes
  `workspace.StreamingProto`, `ReplicatedStorage.StreamingProtoDetail`, `ReplicatedStorage.StreamingPrototype` and
  `ReplicatedStorage.StreamingProtoRemote`. Then save.
- No world, script, streaming or lighting setting is changed by Build.
- The only optional setting is D's TargetRadius run, which goes back through `PattayaPerfProfile.revert()`.
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
