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
| c | b, with the NON-colliding detail parts built by the client within 384 studs (200 instances per frame); every colliding part stays engine-streamed | 1,628 | 537 | 0 | 30,141 |
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
3. **Progressive detail layer (layout c).** The NON-colliding parts of detail props (palm fronds, lamp heads, arms,
   boards and their GUIs, canopies, neon signs, umbrellas, boats) are not streamed by the engine. The client builds
   them within about 384 studs at 200 instances per frame, from data rows in production; the prototype uses
   templates in ReplicatedStorage.
   - Expected: about -8 to -10% instances inside TargetRadius, and the client work is bounded per frame.
   - Cost: client Lua and memory for the data.
   - Every part with collision (poles, trunks, posts, walls) stays engine-streamed, so the server, other cars and
     traffic see the same collision as today. There is **no client-only collision** (owner rule; §4.2).
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

## 4. The prototype experiment (A/B measured 2026-10-21; C and D approved, separate area only, one at a time)

Leader A/B results: `docs/test_results/streaming_proto_ab.txt`.
- Parity OK in Studio: 14,795 parts / 24,791 instances per variant.
- 0 frames with road missing under the car.
- Most runs were unfocused at 15 fps, so their frame times are not valid; they are re-measured in a focused Studio
  first.
- The slab-centre drive path was a harness bug. It is replaced by the road-graph route below.

### 4.1 What the prototype is

- `StreamingPrototype.Build(v)` clones every top-level part of PattayaWorld whose position lies within ±1,536 studs
  of world (23140, 1761). The source folders are:
  - Chunks, WideChunks;
  - Apron, Furniture, VisSlice, Coast, Landmark and **Shoulder** chunks;
  - the junction discs, VisMeshPalms and the gate.
- The copy goes to `workspace.StreamingProto` at +60,000 X, with its own flat Persistent ground (top y = -2, no
  terrain).
- **The source world is only read.** Parts are `Clone()`d; a test checks the source for this.
- **Road layer:** roads, sidewalks, junction and joint discs, aprons, corner fills, shoulders and markings
  (`ProtoCat = "road"` / `"marking"`). Every part of ShoulderChunks and ApronChunks counts as road.
- Variants:

  | Variant | Road layer | Buildings | Props (detail) |
  |---|---|---|---|
  | **A** control | as the source: one Atomic Model per source chunk (mixed), discs and palms loose | (same chunks) | (same chunks) |
  | **B** | Atomic per 256-stud cell, cap 1,500 | Default (non-atomic) | Default |
  | **C** | as B | Default | parts **with** CanCollide or CanTouch: Default, engine-streamed (as B). Parts **without** collision: client-built within 384 studs, 200 instances per frame, from templates in `ReplicatedStorage.StreamingProtoDetail` |
  | **D** | as B | Atomic per 256 cell, `LevelOfDetail = StreamingMesh` | Default |

- **Parity: A, B, C and D copy exactly the same source parts.** Only grouping and streaming mode differ.
  `P.ParityText()` prints parts and instances per source folder for all four variants and ends in `PARITY OK`.
  Model: 24,755 instances in each variant, 1,871 of them in ShoulderChunks. Studio: 24,791. Tests check parity in
  Python and in the luau CLI.
- Instances in the district by mode (model):

  | Variant | Atomic | Default | Client-built | Largest Atomic |
  |---|---|---|---|---|
  | A | 24,417 | 338 | 0 | 748 |
  | B | 10,194 | 14,561 | 0 | 841 |
  | C | 10,194 | 12,043 | 2,518 | 841 |
  | D | 10,194 road + 11,603 buildings (LOD) | 2,958 | 0 | 841 |

### 4.2 Collision: no client-only collision anywhere (owner rule)

The owner's rule: no client-only collision for anything a car can hit (road, kerbs, barriers, checkpoints, props)
unless its effect on the server and in multiplayer is documented and tested.

- **A, B and D**: every part is engine-streamed, so the server holds all of them. Server physics, other players'
  cars and traffic see exactly the collision they see in the city.
- **D**: buildings that are streamed out show as imposters. These have no collision, which is the same as a
  streamed-out building today (no part on the client). The server always has the real parts.
- **C**: only parts with `CanCollide = false` **and** `CanTouch = false` go into the client layer. Examples:
  - palm fronds;
  - street-light arms and lamp heads, signal arms, heads and lamps;
  - sign boards with their GUIs, neon signs and frames;
  - shelter roofs, taxi canopies, racks and vests;
  - pole arms and wires, tree canopies;
  - umbrellas and loungers, boats, parasails, hut roofs and trims, tower decks, cabins and flags.

  Every part a car can hit stays engine-streamed in `Props`, exactly as in B: trunks, poles, posts, shelter pads and
  walls, benches, hut floors and walls, tower legs, gantry posts, and all road, kerb and building parts. The client
  clones also get CanCollide, CanTouch and CanQuery set to false.
- **Checks:**
  - `P.CollisionAudit()` lists every client-layer template with collision. `Build("C")` fails (and removes the
    prototype) if it is not empty.
  - In Play, the boot server script runs `P.Server.check()`, which prints:
    - the client-only collision part count (**must be 0**);
    - the drive path sampled every 4 studs against the copied road layer **on the server** (must be 100%);
    - colliding parts per category, which must be equal for A, B, C and D (C moves no colliding part).
- **Not affected:** checkpoints and traffic are not in the prototype. The Race folder is not copied and there is no
  traffic in the proto area, so checkpoint triggers are unaffected by construction.

### 4.3 Drive path (road graph)

`Build` now picks the path from `ServerStorage.PattayaRoute` (nearestNode, dijkstra, polylineOf, toWorld).
`P.PickRoute` does the choosing:
- Candidates: routes between up to 12 spread seed nodes and every graph node inside the district (40-stud margin).
  The 300 highest-cost routes become polylines; only those fully inside the district and at least 800 studs long
  are kept.
- The longest route whose samples every 4 studs are **100%** on copied road parts is chosen; up to 60 routes are
  sampled.
- If none reaches 100%, the best route is used only if it reaches 99%. Below that, **Build fails** and removes the
  prototype again.
- Optional fixed route, as the leader used: `P.Build("B", {pathFrom = Vector2.new(1800, 1700), pathTo =
  Vector2.new(4500, 1800)})`, in map-local coordinates.
- Result attributes on the root: `ProtoPath`, `ProtoPathInfo` (length, samples, % on road), `ProtoPathCoverage`.
- Unit tests (luau CLI, mock graph): the longest route wins; a route over a road gap is skipped; below 99% fails.

### 4.4 Run modes and per-run output

| Mode | How it starts |
|---|---|
| **cold** (`P.SetBoot("cold")`, fresh Play) | At join, the server seats the first player in the nearest race car and moves it to the path start with **no** `RequestStreamAroundAsync`. The client records 30 s from join. |
| **teleport** (`P.SetBoot("teleport")`, fresh Play) | The car is seated in the city. After 15 s the client asks the server to teleport it into the proto (kit teleport, with pre-stream like the game) and records 20 s. |
| **drives** (after cold or teleport) | 100, 150 and 200 studs/s, each speed in **CFrame mode and in physics mode** (`DriveModes = "both"`, the default; `P.SetBoot(kind, 30, "cframe" or "physics")` for one mode only). Directions alternate. `o.physics = true` on `P.Client.run` by hand. |

Each window prints one line:

```
[StreamProto] <variant> <mode> [v=<speed> cframe|physics] | avg <fps> fps, p99 <ms> ms, 1% low <fps> fps, worst <ms> ms,
>50ms <n>, >100ms <n>, <frames> frames | added/frame max <n> p99 <n> total <n> [(client layer max <n>)] |
road missing under car <n>/<checks>, ahead 0.5s <n>, 1s <n>; in proto at <s>s, first road <s>s |
complete min <pct> target <pct> | mem total <MB> MB (<delta>): Instances .., PhysicsParts .., GraphicsParts ..,
GraphicsMeshParts .., GraphicsTexture .., ...
```

The server prints one check line per session:

```
[StreamProto] server check variant <v>: client-only collision parts 0; path on road (server) <n>/<n> = 100.0%; colliding parts: building <n>, detail <n>, ground <n>, road <n>
```

`P.Client.report()` on the client joins all the lines of the session.

### 4.5 Exact Studio procedure

**Before C or D:** the leader re-measures A and B in a focused Studio. Use steps 1-3 with `"A"`, then `"B"`. C and D
follow, one at a time.

1. **Edit mode, once:**
   ```lua
   local P = require(game.ServerStorage.StreamingPrototype:Clone())
   print(P.ParityText())     -- last line ends in "PARITY OK"
   ```
2. **Build one variant:**
   ```lua
   print(P.Build("C"))       -- or "A" / "B" / "D"; removes the previous variant first
   print(P.Probe())
   print(P.CollisionAudit()) -- must print an empty line
   print(P.SetBoot("cold"))
   ```
   Then **save**.
3. **Run the sessions.** Keep Studio in front (focused), or the frame numbers are invalid.
   - 3 fresh Play sessions with cold. Each runs by itself: cold, then 6 drives (CFrame and physics at 100, 150 and
     200), about 2-3 minutes.
   - After each session, collect the server check line and the client lines (`print(require(game.ReplicatedStorage.
     StreamingPrototype).Client.report())` on the client). Stop Play.
   - Edit `print(P.SetBoot("teleport"))`, save, and run 3 fresh Play sessions the same way.
4. **Next variant:** repeat steps 2 and 3. D can also be run once more with `StreamingTargetRadius = 896` through
   `PattayaPerfProfile` apply and revert; that is optional and changes a world setting until reverted.
5. **Removal check (Edit mode):**
   ```lua
   print(P.Remove())             -- ends in "leftovers: none"
   print("[" .. P.Leftovers() .. "]")   -- prints "[]"
   ```
   Then save.

**Expected outputs (model estimates, not measurements):**
- `Build`:
  - `variant C: ... -> ... containers (Atomic ..., Client ..., Default ...); largest Atomic about 841; road in decor 0`;
  - then `built ... parts ...; drive path N points (route ~4000+ studs, ... samples, 100% on road); ... SAVE the place`.
- `ParityText`: identical rows for A, B, C and D, total about 24.8k instances, `PARITY OK`.
- Server check: `client-only collision parts 0`, `path on road (server) 100.0%`, the same colliding-part counts in
  every variant.
- Drives, compared with A in the model:
  - B: max instances added per frame about 300-850 (largest road cell 841), against A's full chunks.
  - C: about 10% fewer engine-streamed instances near the car; `client layer max` ≤ about 200 plus one template.
  - D: about 45% fewer instances within TargetRadius only when the radius is lowered. At the pc radius, D mainly
    groups buildings.
- Road missing: **0** (hard fail otherwise).

### 4.6 Pass / fail (each variant against the focused A control, medians of 3 runs)

| Measure | Pass |
|---|---|
| Parity (`P.ParityText()`) | PARITY OK (hard fail) |
| Client-only collision parts (server check, `CollisionAudit`) | 0 (hard fail) |
| Path on road on the server | 100% (hard fail) |
| Road missing under the car / 0.5 s / 1 s ahead, every drive, CFrame and physics | **0** (hard fail) |
| Road missing under the car, cold and teleport | ≤ A |
| Drive worst frame / p99 | ≤ 60% / ≤ 80% of A |
| Drive 1% low FPS | ≥ A |
| Instances added per frame in drives: max / p99 | ≤ 900 / ≤ A |
| Cold / teleport frames > 100 ms | ≤ 75% of A; worst frame not worse than A + 10% |
| Completeness inside MinRadius at the end | 100% |
| Memory total at the end | ≤ A + 5% (C: the templates in ReplicatedStorage are included) |
| C: client layer per frame | ≤ 200 + one template; no visible gaps inside about 250 studs (screenshot) |
| D: imposters | visible beyond the streamed area (screenshot); otherwise D is dropped |

### 4.7 Rollback and leftover check

`P.Remove()` (Edit mode) deletes:
- `workspace.StreamingProto` and `StreamingProtoClient`;
- `ReplicatedStorage.StreamingPrototype`, `StreamingProtoRemote` and `StreamingProtoDetail`;
- `ServerScriptService.StreamingProtoBoot` and `StarterPlayerScripts.StreamingProtoBootClient`;
- any `StreamProto*` attribute on workspace or ReplicatedStorage.

It ends in `leftovers: none`. `P.Leftovers()` must return an empty string. A luau mock-place test checks this,
including that PattayaWorld, PattayaRemotes and unrelated attributes stay. Player attributes (`StreamProtoSeated`,
`StreamProtoArrived`) exist only during Play. Build changes no world, streaming or lighting setting. Full fallback:
the owner's .rbxl backup.

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
