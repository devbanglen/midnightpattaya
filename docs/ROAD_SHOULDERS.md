# Road shoulders, width tapers and hole fills (Sukhumvit pilot)

Status: **data built and tested offline only. Nothing has been built or driven in Studio.** The owner has not yet
approved installing it. Every number below comes from the offline geometry checks, not from the game. The leader
installs and tests it with the steps below. Removing it is one call.

| File | Role |
|---|---|
| `tools/mapgen/road_shoulders.py` | generator: edge analysis, shoulders, tapers, hole fills, terrain boxes, checks, drive check, determinism run |
| `tools/mapgen/config/shoulders.json` | target roads, widths, heights, colour, clearances, taper rule, terrain option, drive-check parameters |
| `roblox/src/ServerStorage/PattayaShoulderBuilder.luau` | `.Build({batch?, only?, folder?})`, `.Probe()`, `.BuildTerrain({batch?})`, `.RemoveTerrain()`, `.Remove()` |
| `tools/qa/tests/test_shoulders.py` | 17 offline tests (data, overlaps, caps, determinism, drive check, the real builder run in the luau CLI) |
| `build/shoulders/roblox/` (generated, gitignored) | `manifest.luau` + 79 `chunk_s<cx>_<cz>[_k].luau` modules (604 KB) |
| `build/shoulders/shoulders.json` | analysis, counts, tapers, fills, checks, drive before / after, the worst spots |
| `build/shoulders/shoulder_check_*.png` | top views of the two flip spots: shoulder yellow, taper magenta, fill cyan, terrain boxes green outline, unsupported car samples pink (before) / red (after) |

Rerun (about 60 s, includes a determinism run; `--no-determinism` makes it about 35 s, and `--analysis-only` prints only
the analysis and the before numbers):
`D:\ROBLOXRACE\.venv\Scripts\python.exe tools\mapgen\road_shoulders.py tools\mapgen\config\shoulders.json`
The script finds the main checkout's `build/` when it runs from a worktree (`--build-root` overrides this). It exits
with code 1 if a check fails or the two runs differ. Tests: `D:\ROBLOXRACE\.venv\Scripts\python tools\qa\tests\run_all.py`
(103 pass, 17 of them in `test_shoulders`).

## The problem (leader's Studio drive, physics, 150 studs/s)
The Sukhumvit centre line is clean for its whole length. A car in the outer lane flipped in two places:
- **(25250, 13430), lane offset 24, on a 52-wide slab.** The road slab Parts sit at y -1 and are 4 thick, so their top
  is at +1. The terrain beside them is at -2. A wheel that leaves the slab drops about 3 studs.
- **About (24560, 900), lane offset 14.** Sukhumvit narrows from 52 to 26–39 studs between z 990 and 1060, next to
  trunk_link pieces (the skipped underpass section).

## 1. Findings: Sukhumvit edges in the built road data
The input is the data the Studio builders read. `road_check.py` ports PattayaBuilder's stripe, offset and trim and
road_fix rule D's hidden / cutA / cutB / hide / fill exactly. The aprons come from `build/aprons/roblox`. Buildings,
props and furniture are loaded as in `junction_aprons.load_world`. Landmark parts use their exact rotated footprint
when they come within 4 studs of the road top. (The apron loader puts a bounding circle around every rotated part, so a
market roof 16 studs up became a 38-stud circle over the road edge.) World = map + ORIGIN (20000, 0, 0), the same as
`PattayaBuilder.ORIGIN` and `PattayaApronBuilder.ORIGIN`.

**Targets:**
- 155 built Sukhumvit (trunk) edges and 14 built trunk_link edges within 80 studs of them.
- 204 hidden carriageways. These are road_fix rule D lines with no slab; the merged slab carries them.
- 29,171 studs of built centre line.
- Widths: 52 (82 edges), 65 (43), 39 (25), 26 (10), 13 (5), 78 (4).
- **No target edge has a sidewalk.**

**Where the slab edges meet the terrain.** Both sides of every built slab piece were sampled every 2 studs, 1 stud
outside the slab edge:

| | studs of edge side | share |
|---|---|---|
| bare terrain (a 3-stud drop) | **37,508** (trunk 35,378, trunk_link 2,130) | **68.7 %** |
| another road surface (crossing road, disc, apron, fill) | 17,006 | 31.1 % |
| building box | 96 | 0.2 % |
| raised (sidewalk / corner fill of a crossing road) | 22 | 0.04 % |

There are 349 exposed runs. The longest:

| Length | World (x, z) | Note |
|---|---|---|
| 982 studs | (25162, 13360) | the left side of 815003412:w2891, which is flip spot 1 |
| 924 | (24766, 12313) | |
| 754 | (27211, -7774) | |
| 748 | (23969, 10022) | |
| 652 | (23701, 6458) | |
| 624 | (24029, 10105) | |
| 612 | (23755, 6454) | |
| 586 | (25583, 14357) | |

All are listed in `shoulders.json` → `analysis.exposed_runs`.

**Abrupt width changes.** A width change is a node where a target edge continues (turn ≤ 40°) into a target edge that is
at least 2 studs narrower. There are **37**:
- 65 → 52: 26 nodes
- 52 → 39: 4 nodes
- 52 → 26: 3 nodes
- 39 → 26: 2 nodes
- 65 → 39: 1 node
- 78 → 52: 1 node

The flip-spot-2 cluster:
- (24554, 898): 65 → 52
- (24550, 922): 52 → 26, the trunk_link 541666907
- (24538, 969): **52 → 26**, the 742330563 → 740847240 one-way carriageway that the car followed
- (24518, 1039): 39 → 26
- (24421, 1171): 39 → 26

The third 52 → 26 narrowing is at (24976, 12908), at the south end of flip spot 1's slab. In addition, **52 slab cut ends** (cutA / cutB on
target edges) end the slab before its node. The longest are 145 studs on trunk_link 688483203 at (24442, 948), 117 at
(27899, -8737), 106 at (23552, 4440) and 95 at (24199, 11023).

**Gap and hole candidates.** The road_seams scan (team12, `build/qa/road_seams.json`) found these within 60 studs of
Sukhumvit:
- gap 20
- sliver 19
- end_gap 4
- narrowing 10
- zfight 15

This layer adds a fill pass: whatever is still open inside the full exported polyline's stripe (at width + 2 ×
shoulder) and between two continuing edge ends ≤ 30 studs apart. It closes **218 open regions** (1,450 pieces). These
include:
- the end gaps at (23865, 8383) / (23880, 8404), where two merged slabs end at different nodes and there is no disc
- (24912, -393)
- the holes at (24372, 1491) / (24379, 1467)
- **large cut-region holes** inside the nominal carriageway: 1,039 studs² at (24245, 11058) on 1219572541:w3076, which
  is cut 47 + 95 and has no road under its polyline. Others are 413 at (24421, 1459), 344 at (24228, 1773), 317 at
  (27955, -8758) and 305 at (24474, 880).

Large fills are listed in `shoulders.json` → `gaps`. A fill larger than `clean.max_fill_area` (2,500 studs²) would be
reported, not built; there are none.

## 2. Design (what the patch adds)
The road graph, GPS, checkpoints, lane widths, every existing part and the car physics are unchanged. Every piece is a
new anchored Part in its own folder.
- **Shoulder** (kind 1). Per slab segment and side, a band from `width/2 - 0.1` to `width/2 + 8` studs (`shoulder.width`
  8, the top of the owner's 4–8 range). At joints it is stretched like `Builder.stripe` (`min(h·tan(turn/2), h)` with h
  = the outer half-width). It is clipped by everything else (see "Clearances").
  - 8 rather than 6: the default race car's suspension rays sit at ±3.4 studs (RaceCarServer `DEFAULT_LAYOUT`). With 6,
    the GPS line of the hidden carriageways (≈ 22 studs off the merged slab centre) at lane offset -8 still had 2,270
    unsupported samples. With 8 it has 4.
- **Taper** (kind 2). At each of the 37 width changes, a variable-width strip along the narrower edge and its
  continuation, on both sides, plus the fan triangle at the node.
  - Its half-width goes linearly from `W1/2 + 8` to `W2/2 + 8` over `L = clamp(4 × (W1 - W2)/2, 30, 90)` studs: 30 for
    65 → 52, 52 for 52 → 26.
  - The lane edge is the old wide one at the node and reaches the narrow one ≥ 30 studs later.
- **Fill** (kind 3), as described under "Gap and hole candidates" above.
- **Top 0.985, 4 thick** (bottom -3.015, below the terrain).
  - It is 1.5 cm under the road top (1.00) and 0.5 cm under the junction / joint discs (0.99), and above the aprons
    (0.98). A wheel sees it as flush.
  - Each piece tucks 0.1 studs under the slab edge, so there is no ray gap and no visible seam. Being under the slab
    (and its colour) means no z-fighting.
  - Neighbouring pieces overlap by ≤ 0.05 (same height and style).
- **Look:**
  - Name `Shoulder`, Material Concrete, Color 92,91,88: road-like, but lighter than the asphalt (46,47,52 / RoadLook
    62,63,68).
  - RoadLook restyles only parts named Road / Joint / Junction / markings / Sidewalk, so shoulders keep their own look in
    dry and wet modes.
  - CanCollide true, CanQuery true (the suspension rays must hit it), CanTouch false, CastShadow false.
  - Attributes: `RoadFill = true` (the leader's slab-overlap probe skips RoadFill), `Shoulder = true`,
    `ShoulderKind = shoulder | taper | gap`.
- **Clearances.** Each piece stays clear of:
  - road surfaces, shrunk by 0.1 (the tuck)
  - aprons and corner fills, +0.02
  - sidewalks, +0.02
  - building boxes, +0.5
  - props, +0.3: palms, lights, signs, furniture ground parts, coast props, landmark parts, gantries, the gate
  - earlier pieces

  Each piece is cleaned (opening 0.08) and cut into one box when it is truly a rectangle (Hausdorff distance ≤ 0.02 to
  the fitted box), otherwise into constrained-Delaunay triangles. Each triangle is two WedgeParts, exactly like
  `PattayaBuilder.roadTriangle` / `PattayaApronBuilder.triangle`.
- **Chunks.** Same 512-stud grid of the map-local piece centroid as the other layers. Each `chunk_s<cx>_<cz>` is one
  Atomic Model. A chunk over 600 parts is split into `_2`, `_3`, … modules. Batches of ≤ 8 chunks, nearest to world
  (24560, 900) first.
- **Terrain (optional, separate):**
  - `Terrain:FillBlock` boxes outside the shoulder, 10 studs wide, in 8-stud slices.
  - A slice is kept only if it is clear of every road, sidewalk, apron, corner fill, building (+2) and prop (+1).
    Contiguous slices merge into one box.
  - The box fills y -4 … -2, half of the voxel layer -4 … 0. PattayaBuilder measured that a full layer up to grid line Y
    renders at Y + 2, so a full layer here would show at +2, above the road. Half occupancy is *expected* to show near 0
    (1 stud under the shoulder instead of 3). **This is not measured.** `Probe()` reports the surface height at every
    built box.
  - Before each box, the voxels of its bounds (y -8 … 4) are copied into a TerrainRegion in
    `ServerStorage.PattayaShoulderTerrainBackup`. RemoveTerrain pastes them back newest-first, which is exact even
    where boxes overlap.

## Counts (generator run 2026-10-21, digest `e229e7ba`, deterministic)
| | pieces | parts | area (studs²) |
|---|---|---|---|
| shoulder | 4,096 | 7,677 | 305,595 |
| taper | 1,003 | 1,938 | 3,059 |
| fill | 1,450 | 2,578 | 7,123 |
| **total** | 6,549 | **12,193 parts** in 79 chunk modules (largest 600: `s8_1`), 10 batches | |
| terrain boxes (optional) | 688 FillBlock boxes | 0 parts | |

Instances added: 12,193 BaseParts + 79 chunk Models + ≤ 3 kind Models per chunk + 1 folder. The world is about 56k road /
city parts plus 23.8k aprons, so this adds roughly +15 %, streamed per Atomic chunk. Three of the 79 modules reach the
600 cap (s8_1, s8_2, s9_25); the split keeps them there.

## Offline checks (all 0, asserted by the generator and again by the tests)
- piece outside the target envelope 0
- piece on a building box 0, prop footprint 0, sidewalk strip 0, apron 0, corner fill 0
- piece deeper than 0.15 under a road surface 0
- two pieces overlapping outside the 0.1 rim of one of them 0
- degenerate pieces 0
- chunk over 600 parts 0
- terrain box touching a road / sidewalk / building / apron 0

The modules on disk are byte-identical to a fresh in-process build. The real `PattayaShoulderBuilder.luau` was run in the
luau CLI with stub Roblox types (Instance / CFrame / Terrain) on all 80 modules:
- part count = data for every chunk; every chunk is Atomic; a second Build skips built chunks
- every part top = 0.985, named Shoulder, CanCollide, RoadFill
- the union of the Luau parts' footprints matches the generator's pieces (within the 0.001 print rounding)
- Probe: not flush 0 / above road 0 / obstacle hits 0
- BuildTerrain: one TerrainRegion backup per box, not repeated
- Remove: restores newest-first, then destroys the folder and the backup

The real collision, look and the probe numbers in Studio are unverified.

## Drive check: before / after (offline geometry, not physics)
The built Sukhumvit polylines are sampled every 2 studs (13,632 samples per offset) at lateral offsets 0, ±8, ±14, ±20,
±24. A sample is **supported** when every wheel point lies on a surface whose top is within 0.3 of the road top (slab,
fill, disc, apron, shoulder) within a 0.05-stud tyre patch. A sidewalk (1.6), a corner fill (1.58) or the terrain (-2)
does not count. "On slab" = samples whose car centre is on the slab (|offset| ≤ width/2), i.e. a lane the road has.

Positive offset = left of the polyline direction. TestKit's `lateral` is to the **right** of the path, so TestKit
`lateral = 24` is the tables' -24.

**Spec footprint 4 × 9** (6 points: 4 corners + 2 side middles):

| offset | unsupported before → after | on the slab: before → after |
|---|---|---|
| 0 | 0 → 0 | 0 → 0 |
| +8 / -8 | 5 → 0 / 11 → 0 | 5 → 0 / 11 → 0 |
| +14 / -14 | 6 → 0 / 62 → 0 | 6 → 0 / 29 → 0 |
| +20 / -20 | 256 → 4 / 1,228 → 101 | 11 → 0 / 32 → 0 |
| +24 / -24 | 321 → 6 / 1,391 → 284 | 48 → 2 / 93 → 10 (of 12,142) |

**Real wheel track**: 4 suspension rays at (±3.4, ±5.2), the default race car. This is what reproduces the Studio
flips:

| offset | unsupported before → after | on the slab: before → after |
|---|---|---|
| 0 | 11 → 0 | 11 → 0 |
| +8 / -8 | 7 → 0 / 11 → 0 | 7 → 0 / 11 → 0 |
| +14 / -14 | 14 → 0 / 72 → 0 | 14 → 0 / 37 → 0 |
| +20 / -20 | 243 → 3 / 1,283 → 166 | 6 → 0 / 34 → 0 |
| **+24 / -24** | **6,791 → 3 / 8,640 → 342** | **6,518 → 1 / 7,313 → 27** |

- **Both Studio flip spots:** the samples within 120 studs of (25250, 13430) at offsets ±24 and of (24560, 900) at ±14
  are unsupported before and supported after (asserted in `test_leader_flip_spots`).
- **On-slab samples left after** (real wheel track, all at ±24):

  | Samples | World (x, z) | Note |
  |---|---|---|
  | 7 + 2 | (24573, 927) / (24575, 918) | a building stands 1–2 studs from the slab edge, so the shoulder is clipped |
  | 4 | (23807, 3369) | |
  | 3 | (24259, 11098) | |
  | 3 | (28485, -9498) | |
  | 3 | (27872, -8659) | |
  | 2 | (26342, -6249) | |
  | 1 | (28447, -9528) | |

  These are buildings or props right at the edge, or the very end of a short edge.
- **Off-slab samples left after** (car centre beyond the slab edge, e.g. -24 on a 39-wide carriageway) cluster at
  (24547, 1020), (24251, 1694) and (24864, -133). They are not lanes the road has.
- **Hidden carriageway lines.** These are the graph polylines that GPS routes follow; road_fix rule D builds no slab on
  them, and they lie about 20–24 studs off the merged slab centre. 15,072 samples per offset:

  | Offset | Unsupported before → after |
  |---|---|
  | -8 | 6,210 → **4** |
  | +8 | 112 → 0 |
  | ±14 | 163 → 0 / 8,374 → 6,099 |
  | ±24 | 144 → 29 / 11,645 → 10,453 |

  -14 and beyond on the outer side of a hidden line is 36+ studs from the merged centre, past any shoulder.
- **trunk_link lines** (1,044 samples): ±8 254 → 8 / 314 → 35; their 13 / 26 widths make ±14 and beyond off-slab.

## Studio install and test procedure (leader; save the place / take the owner's backup first)
**Edit mode, install:**
1. `ServerStorage.PattayaShoulderBuilder` ← `roblox/src/ServerStorage/PattayaShoulderBuilder.luau` (new ModuleScript).
   `tools/studio/install.ps1` already bundles every file in roblox/src.
2. Create the Folder `ServerStorage.PattayaDataShoulders`. Load `build/shoulders/roblox/manifest.luau` and the 79
   `chunk_s*.luau` modules into it as ModuleScripts named like the files without `.luau` (604 KB). Use the same
   JSON-bundle / HttpListener method as the apron data.
3. Pilot: batch `s1` is the narrowing at (24560, 900); batch `s9` holds chunk `s10_26`, which is (25250, 13430).

   ```lua
   local Sh = require(game.ServerStorage.PattayaShoulderBuilder)
   print(Sh.Build({batch = "s1"}))   -- wanted: 8 chunks, no "parts built, data says" warning
   print(Sh.Build({batch = "s9"}))
   print(Sh.Probe())   -- wanted: parts = built chunks' data, not flush 0, above road top 0, obstacle hits 0,
                       -- sidewalk overlaps 0, apron overlaps 0, ray covered 0 ("touching a road surface" > 0 is expected)
   ```

4. Read-only spot checks (Edit). Each should hit a `Shoulder` part with top ≈ 0.985:

   ```lua
   for _, p in {Vector3.new(25216.5, 10, 13491), Vector3.new(24538.3, 10, 1049.9)} do
       local r = workspace:Raycast(p, Vector3.new(0, -20, 0)) print(r and r.Instance:GetFullName(), r and r.Position.Y)
   end
   ```

   Look at the chamfers at (24538, 969) and (24518, 1039) against the magenta pieces in
   `shoulder_check_narrowing_24540_1000.png`. Then check the material / colour in day and night, and RoadLook wet.
5. When the pilot is accepted: `Sh.Build({batch = "s2"})` … `"s10"` (manifest.batchOrder; built chunks are skipped), or
   `Sh.Build()`.
6. Terrain (optional, only after the parts are accepted):

   ```lua
   print(Sh.BuildTerrain({batch = "s1"}))
   print(Sh.Probe())   -- the "terrain boxes probed" line must say "at / above the road top 0"; look at a few boxes
   ```

   If the surface is above about 0.5, or looks wrong: `print(Sh.RemoveTerrain())`.

**Play mode, physics drives.** Setup (server and client, as in docs/TEST_KIT.md):

```lua
-- server
local S = require(game.ServerStorage.PattayaTestKitServer).start()
print(S.seat(S.player()))
-- client
local TK = require(game.ReplicatedStorage.PattayaTestKit) TK.hookRemotes() TK.ghostTraffic(true)
-- shoulders are named "Shoulder": count them as road in the probes
local okNames = {Road = true, Junction = true, Joint = true, Shoulder = true}
local function onRoad(hit) return hit ~= nil and okNames[hit.Instance.Name] == true end
```

1. **Flip spot 1, (25250, 13430), the merged 52-wide two-way slab.** Run both directions, at 100, 150 and 200 studs/s,
   at offsets 24, -24, 20, -20, 14:

   ```lua
   local A = "24975.8,12907.9;24980.2,12916.4;24995.6,12937.1;25020.3,12966.3;25040.2,13011.5;25061.2,13061.1;25093.4,13133.7;25125.6,13206.3;25158.3,13282.0;25191.0,13357.6;25223.8,13433.3;25264.0,13524.6;25304.3,13615.8;25331.4,13678.2;25363.1,13753.1;25394.8,13827.9"
   print(TK.teleport(Vector3.new(24975.8, 6, 12907.9)))
   local h = TK.drivePath(A, {physics = true, speed = 150, lateral = 24, onRoad = onRoad})
   -- later: print(h:poll())   -- wanted: no flip, stats.minUp >= 0.9, the probes all road (Shoulder counts)
   -- reverse: TK.drivePath(TK.reverse(TK.readPath(A)), {...}) after a teleport to the north end
   ```

2. **Flip spot 2, the narrowing (24560, 900) → (24518, 1039).** The road is one-way north from (24554, 898), so drive
   south → north. Use offsets 14, -14, 20, -20 and 24 at 100, 150 and 200. Also run the reverse (wrong-way, but it is
   the same ramp geometry).

   ```lua
   local B = "24596.6,653.5;24573.8,735.1;24568.6,752.1;24553.5,806.2;24554.9,890.5;24554.0,898.5;24549.5,921.9;24538.3,969.3;24517.5,1038.6"
   print(TK.teleport(Vector3.new(24596.6, 6, 653.5)))
   local h = TK.drivePath(B, {physics = true, speed = 150, lateral = 14, onRoad = onRoad})
   ```

3. **The whole road by GPS** (the carriageway lines players follow). From the south end (28467, -9514) to the north end
   (26160, 15568): north end node 3116546378, south end node 1106839456. Check that the route follows Sukhumvit (about
   27–30k studs); if it does not, drive it in legs.

   ```lua
   -- server, car at the south end:  print(TK.teleport(Vector3.new(28466.7, 6, -9513.7)))
   print(S.publishRouteTo(S.player(), 3116546378, true))
   print(S.probePath("TK_Route", {every = 4, lateral = 8, onRoad = onRoad}))   -- -8 too; ±14 / ±20 / ±24
   -- client: one run per speed / offset
   local h = TK.drivePath("TK_Route", {physics = true, speed = 150, lateral = -8, onRoad = onRoad})
   ```

   Repeat at 100 and 200 studs/s and at offsets 0, ±8, ±14 and ±24, then north → south (publish the route to node
   1106839456 from the north end). Record `h.stats.minUp`, `h.stats.off` and `byName` for every run.

Pass criteria to propose to the owner:
- no flip, and `minUp ≥ 0.9` at 150 and 200 for offsets with the car centre on the slab
- spots 1 and 2 drive clean at every listed offset, where before they flipped
- no new wall or bump at the shoulder edge, no z-fighting

Offline the patch only predicts support; whether 200 studs/s is stable on a shoulder is a physics result that only
Studio can give.

## Rollback
- **Everything:** `print(require(game.ServerStorage.PattayaShoulderBuilder).Remove())`. This restores the terrain boxes
  (if any were built) from `ServerStorage.PattayaShoulderTerrainBackup`, newest first, and destroys
  `workspace.PattayaWorld.ShoulderChunks`. Nothing else in the place was changed by Build.
- **Terrain only:** `print(require(game.ServerStorage.PattayaShoulderBuilder).RemoveTerrain())`.
- Then delete `ServerStorage.PattayaDataShoulders` and the module if the layer is dropped.
- Do not delete the backup folder by hand while terrain boxes are built: it is the only copy of the old voxels.

## Risks and open points
- **Not seen in Studio:** look, collision and the probe numbers are offline predictions.
  - The WedgePart convention is the one PattayaBuilder / the aprons use in Studio.
  - The terrain fill height is a guess (see Terrain above). `CopyRegion` / `PasteRegion` voxel bounds are taken as
    inclusive min/max with a 1-voxel margin.
- **Test probes.** TestKit `ROAD_NAMES` and `PattayaGarageServer.isRoad` do not know the name `Shoulder`. Without the
  `onRoad` above, a probe on a shoulder counts as off-road. No game logic depends on it: CarController's suspension
  hits any CanQuery part.
- **QA runner.** `PattayaQARunner.CHUNK_CAPS` / `PART_REFS` have no `ShoulderChunks` entry yet (file not owned here).
  Suggested: `ShoulderChunks = 600`, `["PattayaWorld.ShoulderChunks"] = 12193`.
- **Clipped shoulders.** Buildings or props 1–2 studs from the slab edge (e.g. (24573, 927)) leave the shoulder clipped
  there. The car can still drop at ±24 at about 37 of 12,142 on-slab samples.
- **Large cut-region fills.** Hole fills inside the nominal carriageway (up to 1,039 studs² at (24245, 11058)) put road
  where rule D cut the slab but nothing covered it. Check them visually in the pilot. They are at road height with the
  shoulder colour, so they read as patched asphalt.
- **Parts.** +12.2k parts. Setting `shoulder.width` to 6 changes the part count very little but gives worse coverage
  (see above). `clean.min_gap_area` drops small fills.
- **Pilot only on Sukhumvit and its trunk_links.** Other bare roads (most of the wide world, about 240k drop samples in
  ROAD_APRONS.md) can be targeted later by adding names / classes / `bboxes_world` to `targets` in the config.

Map data © OpenStreetMap contributors, ODbL 1.0.
