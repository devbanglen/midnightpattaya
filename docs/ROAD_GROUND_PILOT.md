# Ground at road level: pilot at the Sukhumvit / Pattaya Klang junction

**Status (2026-10-22): designed and tested OFFLINE only. Nothing in this document is built in Studio.**
Road B is built in the place (this morning, at the owner's go-ahead): `RoadVisPilot` with 7 cells and 1,822 parts, and
782 old parts moved to `ServerStorage.RoadVisBackup`. The ground needs a terrain write. The leader's first terrain
write was refused by the safety check, so it needs the owner's own explicit permission (section 7).

Every number is OFFLINE unless it says "Studio". Offline means the static model in `tools/roadvis/ground.py` on the
generated `build/` data, or the luau CLI with a voxel-level Terrain mock. Every image is an offline preview, not a
Studio capture, and none of it is a Visual PASS.

Regenerate: `D:\ROBLOXRACE\.venv\Scripts\python tools\roadvis\cli.py ground --city --art` (about 2 minutes), then the
local renders and `cli.py ground-compose` (section 4). Tests: `tools\qa\tests\run_all.py -k test_roadground` (23).

## Owner summary

**Your three complaints, and what changes inside the Road B box**

| You said | Why | With Road B (built) | With Road B + ground (proposed) |
|---|---|---|---|
| 1. The roads overlap messily and cars fall off | the old slabs overlapped; 250 of 3,253 lane wheel points had no road under them | fixed: 0 of 3,253 | stays fixed |
| 2. No edge shows where you can drive | the road ends in a 3-stud drop to bare terrain | 57 % of the road edge now has a kerb; 1,214 studs of road edge still drop 3 studs | every road edge meets a kerb, or the ground 0.57 below; a light kerb line marks 88 % of those ground edges |
| 3. A car that falls beside the road gets stuck | the terrain is 3 studs below the road and 3.6 below the sidewalks; a car cannot climb a 3-stud face | the same trenches stay | gone: a car can drive off the road and back on |

**What you will see**
- The pits beside the roads are filled. The ground comes up to y +0.43, only 0.57 below the road.
- Near buildings and along the roads the new ground is grey Pavement. In open lots it is the same ground as today,
  just higher.
- A thin light kerb line runs along every road edge that meets the ground (193 thin strips). They are only a look:
  cars and raycasts pass through them. There are no invisible walls.
- Buildings stand in the ground. Today they float 2 studs above it.
- At the edge of the box the ground slopes back down to today's level over 28 studs (8.7 %). Outside the box nothing
  changes.
- From your screenshot camera the change is modest (dark pits become light ground). The big change is for driving.

**What you must decide**
1. Allow the terrain write in this one box (exact text in section 7). Without it nothing happens. One command
   (`RG.Remove()`) puts every voxel back and checks that the result is exact.
2. Pavement colour: keep the place's Pavement colour (recommended for the first look) or set it to (150, 148, 142).
   The setting is global for Pavement terrain, but nothing else in the place uses Pavement terrain today.
3. Later, after the pilot: whether to plan the same for more of the city. City-wide, 790,000 studs of road edge
   (71 %) drop 3 studs to the terrain today (section 1.2).

Images: [top-down](../art/roadground/top_today_B_ground.png), [edge steps](../art/roadground/steps_today_B_ground.png),
[your camera](../art/roadground/ground_cmp_owner.png), [overview](../art/roadground/ground_cmp_overview.png),
[driver at spot 2](../art/roadground/ground_cmp_driver_low.png), [driver at a trench](../art/roadground/ground_cmp_driver_edge.png).

## 1. Root cause

### 1.1 At the junction

**Studio (the leader's read-only probe, before Road B, world x 24,220..24,820, z 650..1,250):**
- Terrain top y -2.00 everywhere it was hit (5,744 of 10,201 samples). Road tops 1.00, discs and joints 0.99,
  shoulders 0.98–0.99, aprons 0.98, sidewalks 1.58–1.60. Slabs reach down to y -3.0..-1.5.
- 76 % of the road edge samples (700 of 921) are a 3-stud drop to the terrain. Only 19 % (175) have a sidewalk with a
  0.6 kerb.
- From the 700 terrain edges, the next building face is within 8 studs for 63, 8–16 for 88, 16–24 for 46, 24–40 for
  74. 218 are open beyond 40 studs. The other 211 reach another road or sidewalk.
- Building bottoms at y 0.0–1.0 float 2–3 studs over the terrain. The trench is 3 studs deep. A car cannot climb out.
- Overlapping road pieces are flush within 2 cm, but they form a patchwork.

**Offline, the same box today (static model, every stud of every edge):**
- Road edges 3,488 studs. Facing the terrain 2,439 (69.9 %), a kerb up to a sidewalk 584 (16.7 %), another surface
  within 1 stud (a slot) 465 (13.3 %). Without the slots: 80.7 % terrain and 19.3 % kerb. Studio: 76 % and 19 %.
- From the 2,439 terrain edges, the first thing along the outward normal: a building within 8 studs 567, 8–16 145,
  16–24 203, 24–40 148, 40–60 72; another surface 644; nothing within 60 studs 660. The share within 8 studs is higher
  than in Studio (23 % against 9 %). The sampling differs (every stud of every edge here, 921 points in Studio).
- Confidence: high for the heights and the edge classes; medium for the trench distances.

**Why.** PattayaBuilder fills the terrain up to y -4, so its surface is at y -2. Roads are slabs with tops at y 1.0,
sidewalks at 1.6. Everything between a road and the next building is that terrain, 3 studs down (3.6 from a sidewalk).
The car's chassis clears 1.58 studs and its wheels have a radius of 1.5, so a 3-stud face is a wall it cannot climb.
Buildings start at y 0 (the road top minus 1), so they float 2 studs over the terrain.

### 1.2 City-wide audit (offline, from the generated data; no city-wide build)

Source: the exported modules (`central_pattaya`, `pattaya_wide`, `bira` corridor, furniture, coast, landmarks) and the
8 shoulder chunks installed in the place, sampled every 2 studs (`tools/roadvis/ground_audit.py`,
`build/roadground/city_audit.json`). It assumes the place holds exactly the generated data. Studio checked this only at
the junction (above).

**Road-height edges** (asphalt, shoulders, aprons, joints): what lies just outside the edge.

| Street class | Edge, studs | To terrain (3-stud drop) | Share | Kerb up |
|---|---|---|---|---|
| residential | 794,560 | 672,466 | 84.6 % | 119,532 |
| tertiary | 142,288 | 11,258 | 7.9 % | 130,612 |
| secondary | 94,306 | 22,250 | 23.6 % | 71,088 |
| trunk (mainly Sukhumvit) | 55,628 | 54,438 | 97.9 % | 288 |
| unclassified | 23,716 | 23,170 | 97.7 % | 160 |
| trunk_link | 3,606 | 2,990 | 82.9 % | 116 |
| secondary_link | 762 | 502 | 65.9 % | 234 |
| tertiary_link | 174 | 114 | 65.5 % | 56 |
| no class | 2,804 | 2,712 | 96.7 % | 0 |
| **all** | **1,117,844** | **789,900** | **70.7 %** | **322,086** |

The rest: a slot to another surface 2,980, another surface 2,276, a building face 290, water 206, sand 106.
Sidewalk back edges: 471,776 studs, of them 324,262 (68.7 %) drop 3.6 studs to the terrain.
Confidence: medium-high (the method matches Studio at the junction within about 5 points).

**The trench** (from every terrain-facing road edge, a ray 60 studs along the outward normal):

| First thing the ray meets | Share of the 789,900 studs |
|---|---|
| a building within 8 studs | 11.0 % |
| a building 8–16 | 4.6 % |
| a building 16–24 | 2.6 % |
| a building 24–40 | 4.5 % |
| a building 40–60 | 3.1 % |
| another road or sidewalk | 13.5 % |
| water | 0.05 % |
| nothing within 60 studs (open lots) | 60.6 % |

Trench area between road edges and building faces within 40 studs: about 2.35 million studs² (ray-swept). Width from
the road edge to the building face (where one is within 40): residential median 7.2 studs (p10 3.7, p90 29.8),
unclassified 8.3, tertiary 15.4, secondary 21.4, trunk 25.6. Confidence: medium (2D footprints; props ignored).

**Floating buildings.** 10,255 building boxes, all with the base at y 0. 10,206 (99.5 %) have part of their outline
over bare terrain. 1,377,862 of 1,446,384 studs of outline (95.3 %) float 2.0 studs above it. Per building, the
floating outline is 110 studs (median; p10 58, p90 242). Confidence: high for "at least 2.0" (Studio saw bottoms at
0.0–1.0, so some float 3).

**Objects a raise to +0.43 would bury** (counts from the data; foot heights read from the builder code, not measured):

| Kind | City | Foot y | What a raise to +0.43 does |
|---|---|---|---|
| Palms (PattayaBuilder) | 483 | 0 | 0.43 of the trunk in the ground (median 115 studs from the beach sand) |
| Light poles | 2,203 | 1.0 | not buried; the slit under the foot shrinks from 3.0 to 0.57 |
| Road signs | 9 | 0 | 0.43 |
| Utility poles | 950 | -2 | 2.43 of 26 studs |
| Trees (corridor) | 532 | -2 | 2.43 of the trunk |
| Gantry | 1 | -2 | 2.43 |
| Signal poles | 214 | -2 | 2.43 of 18 |
| Street name posts | 738 | -2 | 2.43 of 9.4 (the board, 7.4 and up, stays visible) |
| Bus shelter pads | 23 | -2 | the pad shows 1.17 above the ground, like a sidewalk |
| Bus sign poles | 23 | -2 | 2.43 |
| Taxi stands | 28 | -2 | 2.43 |
| Coast props | 1,517 (166 on land) | -2 | on the beach, which is never raised |

Nothing visible is lost: every object is taller than what a raise covers. Confidence: medium.

**Never raise** (sizes from the data):
- Sea: 141.3 million studs². Beach sand: 1.43 million studs² (the 48-stud strip along the waterline). 124,330 coast
  terrain cells, 48 coast prop chunks, the islands Ko Lan, Ko Sak and Ko Krok.
- Landmarks with parts below +0.73: the floating market (33 of 678 parts, its water and pontoons), Bali Hai pier
  (29 of 106, piles down to -12), the Pattaya City Sign (9 of 37). The other 9 landmarks have none.
- No canal or river terrain exists in the data (all water in the frame is sea).
- Outside the city terrain frame (world x 15,392..29,072), so never touched: the race map (world 6,000, 100, 0), the
  streaming prototype (world x +60,000), the template near the origin, and the Bira venue and corridor (own Grass
  terrain, about world x 44,800).
- The visual slice (map-local x -617..2,281, z -2,870..2,137): kit buildings with the base at 0, no special case.

The pilot box holds no water, sand, coast or landmark cell (0 of 27,722 columns).

## 2. Design

### 2.1 Three options

| | (a) raise the terrain | (b) pave with parts at sidewalk height | (c) pave the frontage, raise the rest |
|---|---|---|---|
| New instances for the ground | **0** (one TerrainRegion backup in ServerStorage) | 1,492 (1,355 wedges + 137 kerbs) | 1,543 (1,438 wedges + 105 kerbs) plus the terrain write |
| Largest 256-stud cell | | 393 parts | 367 parts |
| Road-to-ground step | 0.555–0.57 | 0.6 up (a kerb) | both |
| Building bases | 0.43 in the ground | 1.6 in the paving | mixed |
| Rollback | `RG.Remove()`: PasteRegion, proven exact by a checksum | delete the parts | both |
| Box edge | 28-stud ramp to today's level | a 3.6 drop to the terrain unless ramped | ramp |

**Choice: (a), the terrain raise, plus thin kerb strips.** It adds no ground instances, it fixes every edge in the box
to a step of 0.6 or less, it hides the floating gap under every building, and it rolls back exactly. Paving (b) would
add 1,492 parts on top of Road B's 1,822 and still needs a ramp or a new cliff at its edge. (c) costs even more parts
because the frontage shapes are ragged.

### 2.2 The ground

- **Box:** world x 24,220..24,820, z 648..1,252 (the Road B box on the 4-stud voxel grid), 362,400 studs².
- **Height:** one voxel layer (y -4..0) gets a partial occupancy over full Ground below. PattayaBuilder measured that a
  layer filled up to grid line Y renders at Y + 2. The start value assumes a straight line in between: surface =
  -2 + 4 × occupancy, so 0.6075 gives +0.43. This line is not measured. `RG.Build()` measures the surface with
  terrain-only raycasts at 100 columns and corrects the occupancy (secant method, at most 4 writes). Outside the
  window 0.40..0.46, or if the 100 columns spread more than 0.06, it puts the old terrain back and stops.
- **Edge of the box:** a 4-stud flat collar, then a 28-stud ramp down to y -2 (8.7 %).
- **Materials:** Pavement within 20 studs of a building or 10 studs of a paved edge inside the box; Ground in open
  lots, on the collar and on the ramp. Visible ground in the box: 193,878 studs² (Pavement 98,310, Ground 95,568).
- **Written:** 27,674 voxel columns (22,650 in the box, 5,024 collar and ramp); Pavement 16,677, Ground 10,997.
- **Backup box:** voxels x 6,046..6,213, z 153..321, y -2..0 (world x 24,184..24,856, z 612..1,288, y -8..+4),
  85,176 voxels, copied with `Terrain:CopyRegion` into `ServerStorage.RoadGroundBackup` before the first write, with
  a checksum of every voxel.

### 2.3 Why +0.43

- The road edge must step 0.6 or less: the ground must be at +0.4 or higher.
- The road must stay the highest surface, so the edge still reads as an edge: the ground stays at least 0.52 below the
  lowest road top (0.98).
- One voxel layer spans -2 to +2; +0.43 is well inside that range, with room to calibrate either way.
- Buildings start at y 0, so any height above 0 closes their floating gap. The 0.43 they lose is under 4 % of the
  lowest wall in the box (11.6 studs).

### 2.4 Kerb strips (complaint 2)

193 thin Parts in 7 Atomic cells (`workspace.PattayaWorld.RoadGroundEdges`) along 1,058.8 of the 1,200 studs of road
edge that meet the ground (88 %; the rest are pieces under 0.3 studs, road tips under 1 stud wide, the last stud at
the box edge, and edges with a building, a sidewalk or another surface within 1 stud outside). Straight pieces up to
12 studs that hug curves within 0.08 studs, 0.8 studs wide, on the road side of the edge (the outer face 0.02 past
it), from y 0.39 to 1.03 (0.03 above the road), Concrete, colour (205, 203, 196). CanCollide, CanQuery and CanTouch
are all false, so a car and its wheel rays never meet them. Each has the attribute `RoadGround = "kerb"`. Edges that
already have a sidewalk keep Road B's real kerb. No barrier: no drop-off stays in the box (no water, no wall), so the
brief's "low barrier only at a real drop-off" needs none here.

### 2.5 What gets buried or changes (the written region, 59 buildings and 34 objects)

| Kind | Count | Today | With the ground |
|---|---|---|---|
| Buildings (base 0) | 59 | float 2.0 over the terrain | 0.43 of the wall in the ground; up to 1.74 still floats where a building stands on the ramp |
| Light poles (foot 1.0) | 18 (10 on sidewalks, 8 on the ground) | 3.0 slit under the foot | 0.57 (up to 0.86 on the ramp) |
| Signal poles (foot -2) | 3 | | 2.43 more in the ground; 15.6 visible |
| Street name posts (foot -2) | 9 | | 0.87–2.43; the board is fully visible (6.97 visible) |
| Bus shelter pads (foot -2, top 1.6) | 2 | 3.6 face | 1.17 face, like a sidewalk |
| Bus sign poles (foot -2) | 2 | | 2.43; 7.57 visible |
| Palms, trees, taxi stands, coast props | 0 in the region | | |

### 2.6 What it does not touch

The road graph, GPS, traffic data, car physics, `RoadVisPilot` and `RoadVisBackup` (no part moved or changed),
`ShoulderChunks`, furniture, buildings. Only terrain voxels in the backup box change, plus the kerb strip folder and
the backup folder.

## 3. QA: today | Road B | Road B + ground (offline, static model)

The model: the collision tops of every surface that exists in that state (Road B as exported; the 8 installed shoulder
chunks), the terrain as a height field (y -2, or the raised ground through the column centres), buildings as walls.
Wheels at ±3.4 across and ±5.2 along the car. A drop is a step down of 1.5 or more between 1-stud samples, or 1.5 or
more between wheels; a climb is a step up of 1.5 or more.

| Check | Today | Road B (built) | Road B + ground |
|---|---|---|---|
| Surface edge facing the ground, studs | 2,974 | 2,696 | 2,696 |
| ... of it a drop of 1.5 or more | 2,957 | 2,679 | **0** |
| Road edge to ground, step | 2.98–3.0 | 2.985–3.0 | **0.555–0.57** |
| Sidewalk edge to ground, step | 3.6 | 3.6 | 1.17 |
| Island edge to ground, step | (no islands) | 3.45 | 1.02 |
| 1-stud grid over the box (305,864 cells): steps of 1.5 or more | 7,860 | 6,644 | **0** |
| Largest step on that grid | 3.6 | 3.6 | 1.17 |
| Lane wheel points over a hole (3,253) | 204 | 0 | **0** |
| Same, in the 40-stud seam band where Road B meets the old roads (384) | 34 | 0 | 0 |
| Road B review lane metric (3,253) | 250 | 0 | not computed (B's own check) |
| Spot 2 runs (36) with a drop / a climb | 15 / 15 | 12 / 12 | **0 / 0** |
| Spot 2: largest step down / up; min up | 2.99 / 3.0; 0.916 | 3.6 / 2.985; 0.916 | 1.17 / 0.615; 0.989 |
| Off-road runs ±20 / ±24 (56) with a drop / a climb | 38 / 37 | 34 / 33 | **0 / 0** |
| Off-road runs 8 studs past the edge (28) with a drop / a climb | 19 / 19 | 18 / 18 | **0 / 0** |
| Off-road: largest step up; min up | 3.6; 0.862 | 3.6; 0.862 | 1.17; 0.974 |

- **Targets met (offline):** 0 lane holes; 0 drops of 1.5 or more anywhere in the box (there is no water edge in it);
  every road-to-ground edge 0.555–0.57.
- **Off-road runs** leave the carriageway centreline at a point, move out to the side over 30 studs, hold for 40,
  and come back over 30, one every 60 studs on every carriageway, both directions. "Harness" uses the TestKit
  laterals ±20 / ±24; "deep" puts the car centre 8 studs past the carriageway edge. 6 spot 2 runs, 12 harness and
  4 deep runs touch a building wall in every state (a wall, not a drop).
- **The box edge:** in the 40-stud band outside the box, 874 cells still have a step of 1.5 or more with the ground
  (1,449 with B alone, 1,425 today). Those are today's drops on the roads beyond the box. The ramp adds no new one;
  it raises a step by at most 0.13 (the ramp's own slope).
- **The ground alone, without Road B** (a reference only): also 0 drops, but the 204 lane holes stay (0.57 deep). So
  both are needed.
- **Static, not physics.** It shows where a wheel would drop or meet a face. It cannot show flips or how the
  suspension takes a 1.17 sidewalk face from the ground side. Studio physics drives decide (section 6).

## 4. Images (offline previews, not Studio)

| Image | What |
|---|---|
| [top_today_B_ground.png](../art/roadground/top_today_B_ground.png) | from straight above: today, Road B, Road B + ground (Pavement light grey, Ground brown, today's pit dark olive) |
| [steps_today_B_ground.png](../art/roadground/steps_today_B_ground.png) | every surface edge coloured by its step down: red 1.5 or more (2,957 / 2,679 / 0 studs), green 0.6 or less, yellow 0.6–1.2 (sidewalk and island faces) |
| [ground_cmp_owner.png](../art/roadground/ground_cmp_owner.png) | your screenshot camera: world (24564, 57, 807), look (-0.39, -0.39, 0.84), FOV 70 |
| [ground_cmp_overview.png](../art/roadground/ground_cmp_overview.png) | from above the corner, the raised area and the ramp |
| [ground_cmp_driver_low.png](../art/roadground/ground_cmp_driver_low.png) | a driver at spot 2, 5 studs above the road, looking at the frontage of the two buildings at world x 24,544..24,561 |
| [ground_cmp_driver_edge.png](../art/roadground/ground_cmp_driver_edge.png) | a driver beside the longest Road B edge that still faces the trench with a building close behind it (around world (24516, 1136)) |

Local EEVEE renders, 16 samples, half resolution, flat colours (Roblox lighting and materials look different):
`ROADVIS_THREADS=4 <bpy venv python> tools\blender\bpy_local.py tools\roadvis\blender_preview.py --
build\roadground\scene_ground_<today|B|B_ground>.json build\roadground\renders_local <state> 16 0.5 EEVEE
owner,overview,driver_low,driver_edge`, then `cli.py ground-compose`.

## 5. Road B follow-up after this morning's Studio build

### 5.1 The zebra list (782, not 804)

- **Studio:** `RV.Plan` matched every road part (649) but only 70 of the 155 expected ZebraStripe keys. The place has
  133 zebras in the box (`FurnitureChunks.Chunk_f8_1` 85, `Chunk_f8_2` 42, `Chunk_f9_1` 6).
- **Cause:** the exporter read `build/furniture/furniture.json`. That file is from the first furniture pass
  (2026-10-19 01:43, 4,906 bars city-wide, 155 in the box). The place was built from the dual pass 2 chunk modules in
  `build/furniture/roblox` (04:19, 4,321 bars, 133 in the box). docs/ROAD_AUDIT.md records that pass.
- **Fix (commit fa5dd19):** `world.built_crossings()` takes the zebra bars from the `crossings` rows of the built
  `chunk_f*.luau` modules, so the export follows what the place was built from. The manifest records
  `zebraSource`. The replace list is now **782**: Road 397, Sidewalk 7, Dash 41, Centre 22, Junction 17, Joint 10,
  Apron 142, CornerFill 13, ZebraStripe 133. That is the leader's Studio patch. The 7 cell modules are byte-identical
  to the ones in the place. A test (`ZebraKeysFromBuiltFurniture`) checks the zebra keys against the modules.
- **Regeneration:** after the merge, in the main checkout: `D:\ROBLOXRACE\.venv\Scripts\python tools\roadvis\cli.py
  pilot` (it rewrites `build/roadvis` only). Then, to retire the Studio-only patch, put the new manifest in as
  `PattayaDataRoadVis.manifest_new` and run this read-only check:

```lua
local D = game:GetService("ServerStorage").PattayaDataRoadVis
local A, B = require(D.manifest).replace, require(D.manifest_new).replace
local used, matched = {}, 0
for i = 1, #B.keys, 3 do
	for j = 1, #A.keys, 3 do
		if not used[j] and A.keys[j] == B.keys[i] and math.abs(A.keys[j + 1] - B.keys[i + 1]) <= 0.05
			and math.abs(A.keys[j + 2] - B.keys[i + 2]) <= 0.05 then
			used[j], matched = true, matched + 1
			break
		end
	end
end
print(("patched %d keys, regenerated %d, matched %d"):format(#A.keys // 3, #B.keys // 3, matched))
```

  Pass: `patched 782 keys, regenerated 782, matched 782`. Then move the patched `manifest` and `manifest_orig` into a
  `_prev_2026-10-22` folder and rename `manifest_new` to `manifest`. `RV.Remove()` does not read the manifest (it
  restores from `RoadVisBackup`), so this is tidy-up, not a blocker. With Road B built, `RV.Plan()` says "DOES NOT
  MATCH": the 782 parts are in the backup, so the selection is empty. That is expected.

### 5.2 Sample 220: a hairline seam, not a hole

- **Studio:** `RV.Probe` offset 0, sample 220, wheel point (24504.9, 1045.4): the ray reached the terrain at -2. A
  1-stud grid of rays around it hits road everywhere.
- **Offline:** the point lies in asphalt triangle 49 of `cell_17_4`. It is a needle: 40.0 studs long, 0.30 wide,
  area 6.0, corners (24531.91, 1036.84), (24493.85, 1048.85), (24532.09, 1037.10). The point is 0.0028 studs from the
  40-stud edge it shares with triangle 19. Both triangles use the same exported corners, so the data has no gap.
- **Why it reaches the terrain:** at x ≈ 24,500 a float32 position can only change in steps of 0.00195 studs. Each
  WedgePart's CFrame and Size are rounded on their own, so the shared edge of two wedges can open by about that much.
  A ray that lands in the crack meets nothing until the terrain: the slabs are 4 studs thick and nothing is below them.
- **How often:** Road B has 329 shared triangle edges (10,803 studs) plus the split between the two wedges of each
  triangle (2,621 studs), over 94,833 studs² of asphalt and support. With a mean open gap of 0.0005–0.002 studs the
  Probe's 17,064 rays should find 1.2–4.8 seams per run. Studio found 1. 13 triangles are needles (under 0.5 wide and
  over 10 long); 58 are under 0.5 wide.
- **Effect on a car:** `CarController` casts one ray per wheel (reach = rest + radius = 3.1). A ray in a seam misses
  for one frame, so that wheel gives no spring force for that frame. With the ground raised, the ray meets the ground
  0.57 lower: still a miss at rest, or a 0.57 dip for one frame.
- **Should a RoadSupport back it? No.** Backing every seam needs a strip under each shared edge and each split (about
  +330 to +650 parts) for a crack of 0.002 studs. Instead, `RV.Probe` now counts a point as a hairline seam when 4
  rays 0.05 studs around it all hit road (commit fa5dd19), and reports real drops apart. Optional, at the next Road B
  data rebuild: let neighbouring wedges overlap by 0.01 studs along shared edges, and avoid needle triangles.

### 5.3 Kerb contacts 3 / 4 / 0

Studio measured kerb contacts -20: 3, +24: 4, -24: 0. The old offline expectation (3 / 15 / 20) came from the visual
sidewalk outlines. The Probe's rays hit the collision parts, whose outline is different. Computed from the collision
tops (`ground.State`, the model this pilot uses), the expectation is 3 / 4 / 0, the same as Studio (commit 7c66d50).
This also checks the static model against Studio.

## 6. Studio procedure (from today's built state)

Start state: Road B built (`RoadVisPilot`, 7 cells, 1,822 parts; `RoadVisBackup` with Count 782); terrain unchanged
(y -2 in the box); the Studio-only manifest patch may still be in place (section 5.1).

**Before anything (each one is required):**
1. The owner's explicit permission for the terrain write, in the owner's own words (section 7). An agent message is
   not permission. Do not work around the safety check.
2. A Git checkpoint: this branch merged, `git log -1` noted.
3. The owner saves the place (Ctrl+S, Team Create synced) and a new dated `.rbxl`
   (`midnightpattaya_backup_YYYY-MM-DD[_n].rbxl`, docs/STUDIO_BACKUP_AND_RECOVERY.md).
4. Data in the main checkout: `D:\ROBLOXRACE\.venv\Scripts\python tools\roadvis\cli.py ground` writes
   `build/roadground/roblox` (manifest + 7 `edges_*` modules) and `build/roadground/excursions.json`. Then
   `tools\qa\tests\run_all.py -k test_roadground`: all PASS (`StudioData.test_export_on_disk_is_current` proves the
   data on disk is current). The export sha1 in `build/roadground/pilot.json` should be
   `39f5ebf0311061f288031e9bbd2dc135bf5d47b4` if main's build inputs equal this branch's.

**Steps (Edit mode unless noted):**

| # | Do | Pass |
|---|---|---|
| 1 | Put in `ServerStorage.PattayaRoadGroundBuilder` (ModuleScript, source `roblox/src/ServerStorage/PattayaRoadGroundBuilder.luau`) and `ServerStorage.PattayaDataRoadGround` (Folder: ModuleScripts `manifest`, `edges_16_3`, `edges_16_4`, `edges_17_2`, `edges_17_3`, `edges_17_4`, `edges_18_2`, `edges_18_3`). Update `ServerStorage.PattayaRoadVisBuilder` to this branch's source (only its Probe changed: the hairline seam rule). `local RG = require(game.ServerStorage.PattayaRoadGroundBuilder)` | loads |
| 2 | `RG.Plan()` | `terrain box: voxels x 6046..6213, z 153..321, y -2..0 (world x 24184..24856, z 612..1288): MATCHES the expected state ... 85176 voxels as expected, 0 not`; `Road B: RoadVisPilot built (7 cells, 1822 parts; data 7 cells, 1822 parts); RoadVisBackup present (Count 782, ...)`; `shoulder terrain backups overlapping the box: 0`; `ground built: false; kerb bands present: false`. Anything else: stop. |
| 3 | Baseline, read-only: `RV.Probe()` and `RG.Probe()`; captures from the owner's camera and the two driver views (section 4) with Studio focused; frame times with Studio focused | `RV.Probe` as this morning: `total drops 0`, a few hairline seams (this morning's sample 220 now counts as a seam), kerb -20: 3, +24: 4, -24: 0. `RG.Probe`: terrain median -2.000; edge pairs step about 3.0 (all over 0.6); grid `floor steps >= 1.5` about 1,488 (offline without the ground: 1,488); `kerb bands: 0 parts` |
| 4 | `RG.Build()` (calibration on, kerb strips on, Pavement colour unchanged; `RG.Build({pavementColor = true})` only if the owner chose it) | `road ground: raised 27674 columns (22650 in the box, 5024 collar + ramp) to y Y (median of 100 probes, LO .. HI; N writes, occupancy O); 193 kerb band parts in 7 cells; backup ServerStorage.RoadGroundBackup (checksum)` with Y in 0.40..0.46, HI - LO ≤ 0.06, N ≤ 4. Note O (0.6075 if the straight-line model holds). On `ABORTED`, the terrain is already restored ("restored exactly (checksum)"): stop and report the line. |
| 5 | `RG.Probe()` | terrain median 0.40..0.46; `road-to-ground edges: ... over 0.6: 0` (offline 0.555..0.570); `grid 2 studs over the box: 90600 rays, floor steps >= 1.5: 0`, largest floor step ≤ 1.2 (offline 1.17), `rays that hit nothing 0`; ramp: largest 1-stud step under 0.6, lowest -2.00; `kerb bands: 193 parts (data 193); backup present` |
| 6 | `RV.Probe()` again | the same as step 3 (the ground is below every Road B top) |
| 7 | Play mode, physics: the 72 shoulder-harness drives (2 spots × 2 directions × ±24 / ±20 / ±14 × 100 / 150 / 200) | 0 flips, min up ≥ 0.71 |
| 8 | Play mode, physics: the off-road excursions in `build/roadground/excursions.json`. Each run has `packed` (car centre path, world x, z): `TK.seatIn()`, `TK.jumpTo` to the first point, then `TK.drivePath(packed, {physics = true})`. Drive at least the 52 runs whose `static.B` shows a drop or a climb; all 84 if time allows | per run: no flip, min up ≥ 0.71, the car ends on the road (`TK.probeRoadUnderCar`), no recovery prompt during the run |
| 9 | By hand: drive off the road into the frontage at world (24550, 1005) (spot 2) and at (24516, 1136), stop, drive back onto the road; drive from the ground up onto a sidewalk (a 1.17 face) | the car gets back on the road by itself; the sidewalk face is a bump, not a wall |
| 10 | Every open direction of the junction once, a GPS route through it, 2 minutes of traffic | as with Road B alone |
| 11 | Captures from the same cameras with Studio focused; frame times with Studio focused | the pits are gone in the captures; frame times as in step 3 |
| 12 | Rollback rehearsal: `RG.Remove()`, `RG.Leftovers()`, `RG.Plan()` | `road ground: terrain restored EXACTLY (checksum ... = before the build), backup removed; 193 kerb band parts removed`; `road ground leftovers: none`; the box `MATCHES the expected state` again |
| 13 | If the owner keeps it: `RG.Build()` and `RG.Probe()` again (same pass as steps 4–5); save the place | |

**Rollback at any point:** `RG.Remove()`. It deletes the kerb strips, pastes the backup over the box, restores the
Pavement colour if it was changed, and checks every voxel against the checksum. If it says "NOT exact", it keeps
`RoadGroundBackup`: do not delete it; restore the place version or the dated `.rbxl`. `RG.Remove()` does not touch
Road B. If Road B must go too, run `RG.Remove()` first, then `RV.Remove()` (the kerb strips follow Road B's edges).

**Later rebuilds while the ground is built:** run `RG.Remove()` before a city terrain rebuild
(`PattayaBuilder` clears Ground, Sand and Water but not Pavement, so it would leave the Pavement part of the raise
standing) and before `PattayaShoulderBuilder.BuildTerrain` in this box. Build the ground again afterwards.

## 7. Approval request (exact wording for the owner)

> I approve a Studio PILOT terrain change at the Sukhumvit / Pattaya Klang junction, on a freshly saved place version
> with a dated .rbxl backup. The terrain in the box world x 24,184..24,856, z 612..1,288 (voxel layer y -4..0) is
> raised from y -2 to about y +0.43 (Pavement near buildings and roads, Ground in open lots, a 28-stud ramp back down at
> the edge), and 193 thin non-colliding kerb strips are added along the road edges. A copy of the old terrain is kept
> in ServerStorage.RoadGroundBackup, and RG.Remove() must restore it exactly. Road B, the road graph, GPS, traffic,
> car physics and ShoulderChunks stay unchanged. The Pavement colour is [kept / set to 150, 148, 142]. Acceptance:
> RG.Probe shows every road-to-ground step at 0.6 or less and 0 drops, the physics drives have 0 flips and the car
> drives back onto the road, and captures from my camera. Any failure means RG.Remove().

## 8. Risks and open questions

**Risks**
- **The height model is not measured.** Surface = -2 + 4 × occupancy is an assumption. Build measures and corrects it;
  if it cannot reach 0.40..0.46 with a flat result, it restores and stops. If smooth terrain renders the partial layer
  unevenly, the flatness check and the 2-stud Probe grid will show it.
- **4-stud voxels.** The ground edge against walls and roads follows a 4-stud grid. Under roads, sidewalks and
  buildings it is hidden. On the ramp, a few building corners still float (up to 1.74).
- **Look.** Terrain Pavement and Ground textures at 4-stud resolution; how the material borders blend can only be
  judged in Studio captures. The Pavement colour is global (opt-in; unused elsewhere today).
- **Small slits stay:** 8 light poles stand on the ground with a 0.57 gap (0.86 on the ramp) under the foot. Studio saw
  some building bottoms at y 1.0; they would keep a 0.57 gap too. The data has every building in the box at 0.
- **Sidewalk faces from the ground side** are 1.17 (islands 1.02): under the 1.5 limit and the 1.58 chassis clearance,
  but a bump. Step 9 checks it.
- **Recovery prompt:** a car that rolls slower than 20 studs/s on the raised ground for 6 s gets the off-road prompt
  (prompt only; RescueAuto is off). Today such a car is stuck in a trench.
- **Static model, not physics.** It matched Studio on the edge classes (76 % vs 80.7 % terrain) and on the kerb
  contacts (3 / 4 / 0). Flips and suspension behaviour need the Studio drives.
- **Outside the box nothing changes:** the roads beyond the ramp keep today's 3-stud drops (874 cells in the 40-stud
  band, all already there today).
- **Order of operations:** remove the ground before a city terrain rebuild, before a shoulder terrain build in the box,
  and before `RV.Remove()` (section 6).
- **Data in main:** `build/roadvis` and `build/roadground` in the main checkout must be regenerated after the merge
  (`cli.py pilot`, `cli.py ground`). Until then the zebra test and the ground data tests skip there.

**Open questions for the owner**
1. Permission for the terrain write (section 7)?
2. Pavement colour: keep the place's, or (150, 148, 142)?
3. The kerb strips: keep the light line, or no line (the 0.57 step alone)?
4. After the pilot: plan the next area? Sukhumvit (trunk) is the worst class: 97.9 % of its road edge drops to the
   terrain. Extending the box along Sukhumvit also removes the drops just outside the ramp.

## 9. Files

| File | What |
|---|---|
| `tools/roadvis/ground.py` | the plan (columns, occupancy, ramp, materials), the static QA, the kerb strips, the paving cost of options b and c |
| `tools/roadvis/ground_audit.py` | the city-wide audit and the never-raise zones |
| `tools/roadvis/ground_export.py` | the Studio data: `build/roadground/roblox` (manifest + `edges_<cx>_<cz>`; largest module 35.7 KB) |
| `tools/roadvis/ground_view.py` | top-down looks, edge-step maps, Blender scenes, the composed previews |
| `tools/roadvis/cli.py ground [--city] [--art]`, `ground-compose` | one command for all of it; `build/roadground/pilot.json`, `city_audit.json`, `excursions.json` |
| `roblox/src/ServerStorage/PattayaRoadGroundBuilder.luau` | `RG.Plan / Build / Probe / Remove / Leftovers` |
| `tools/qa/tests/test_roadground.py` | 23 tests: the plan, the targets, the excursion paths, the data on disk, the builder in the luau CLI with a voxel-level Terrain mock (backup first, calibration converges for a curved height map and aborts with an exact restore for a dead one, Remove restores every voxel exactly, aborts write nothing, kerb strips do not collide, Pavement colour opt-in, Leftovers none) |
| `art/roadground/*.png` | the offline previews in section 4 |
