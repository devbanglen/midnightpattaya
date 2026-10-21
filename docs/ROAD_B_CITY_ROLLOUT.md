# Road B for the whole city: the batch rollout

**Status: OFFLINE design and data.** team20, 2026-10-22, branch `team20/road-city`. Nothing in this document has been
built in Studio. The leader installs a batch only after the owner's go-ahead and a fresh place backup. Every number
marked "offline" comes from the static model in `tools/roadvis/city_qa.py` (collision tops, the terrain height field,
buildings as walls). It is not physics.

## Owner summary

- The clean road of the pilot (Road B) and the ground at road level (+0.9) can now go out to the whole city, batch by
  batch. A batch is one 600 x 600-stud square on the pilot's grid (in quiet areas a 2 x 2 or 2 x 1 block of them).
- The plan has **262 batches**. Main roads go first: Sukhumvit both ways from the pilot, then Beach Road, Second Road,
  Pattaya Klang, North Pattaya Road, South Pattaya Road, Thepprasit and Jomtien Beach Road. Then the rest of the city,
  then the Bira corridor.
- Every batch can be undone on its own, in two calls: `RG.Remove("<id>")` puts the terrain back exactly and
  `RV.Remove("<id>")` puts every old road part back. The batch built last is undone first.
- **Batch 1** is Sukhumvit just north of the pilot (world x 24220..24820, z 50..650). Offline it has no lane hole in the
  box away from its open edges (0 of 2,807 lane samples), no drop and no wall on a 1-stud grid over the whole box, and
  every road edge sits 0.10..0.12 studs above the ground. All 72 off-road runs leave the road and come back with no drop.
  Batch 1 adds 1,057 parts and moves 539 old parts out (net +518).
- **City parts, the hard part.** Road B is made of many small parts. The whole city in the "lean" design (sidewalks and
  centre lines only on main roads, the default) adds a net **+206,348** parts (offline count); sidewalks on every soi
  ("full") +312,661. The QA warning line leaves room for only about +32,000. The main roads alone are +69,251.
  With two changes that do not change the look of the road (no invisible support wedges where the ground is raised;
  markings as one mesh per cell, which needs mesh uploads) the main roads come to about +28,900, which fits.
  The rest of the city then gets the raised ground (no parts) and keeps its old road until a cheaper road build exists.
  Section 3 has the numbers.
- **The owner decides:** the go for batch 1; the parts path for the rest (main roads only for now, and the two
  part savers); lean or full sidewalks; plain Ground or Pavement near buildings; what to do with street poles that
  stand on narrow median islands (2 in batch 1, 42 in the city). See section 8.

## 1. How a batch works

### 1.1 The grid and the directions

- Cells are 600 x 600 studs. The grid starts at the pilot's corner, world (24220, 650). The pilot is cell (0, 0).
- World x grows to the east. **World z grows to the south**: North Pattaya Road is near z -2,500, South Pattaya Road
  near z +2,900. So batch 1 (z 50..650) is **north** of the pilot (z 650..1250). They share the edge z = 650.
- A box is half-open: x0 <= x < x1 and z0 <= z < z1. A point on a shared edge belongs to exactly one batch.

### 1.2 What changed in the tools

| Piece | What it does now |
|---|---|
| `tools/roadvis/city.py` | The city model: all 65,873 old road-layer parts, the 1,822 pilot parts, the city-wide road chains. Per batch: the ideal Road B, who owns which part, frontier pieces, the pilot-band completion. The batch plan. |
| `tools/roadvis/city_export.py` | Road B data per batch: `PattayaDataRoadVis_<id>` (manifest + cell modules of at most 600 parts, the replace keys, the probe samples with their offline expectation). |
| `tools/roadvis/city_ground.py` | Ground data per batch, `PattayaDataRoadGround_<id>`, and the never-raise data, `PattayaDataRoadGroundNoRaise`. |
| `tools/roadvis/city_qa.py`, `city_batch.py`, `city_view.py` | Offline QA, the Studio drive list, previews. |
| `tools/roadvis/city_cli.py` | `plan` (all batches and their numbers), `batch <id> [--art]` (data, QA, drives, previews), `bundle <id>` (the install bundle), `map [--art]` (the plan map). |
| `PattayaRoadVisBuilder.luau` | A batch id selects the city mode: `RV.Plan("b001")`, `Build`, `MoveReplaced`, `Probe`, `Remove`, plus `RV.Status()` and `RV.Leftovers()`. |
| `PattayaRoadGroundBuilder.luau` | The same for the ground: `RG.Plan("b001")`, `Build`, `Probe`, `Remove`, plus `RG.Adopt`, `RG.Status()`, `RG.Leftovers()`. |

**The pilot is not migrated.** Without an id every call works on the pilot exactly as before (`RoadVisPilot`,
`PattayaDataRoadVis`, `RoadVisBackup`). The pilot export is byte for byte the same (a test checks it).

Names in the place:

| | Pilot (unchanged) | City batch `<id>` |
|---|---|---|
| Road B parts | `workspace.PattayaWorld.RoadVisPilot` | `workspace.PattayaWorld.RoadVisCity.<id>` (one Atomic Model `Cell_<cx>_<cz>` per 256-stud cell) |
| Road B data | `ServerStorage.PattayaDataRoadVis` | `ServerStorage.PattayaDataRoadVis_<id>` |
| Moved old parts | `ServerStorage.RoadVisBackup` | `ServerStorage.RoadVisCityBackup.<id>` |
| Ground data | none (raised by hand on 2026-10-22) | `ServerStorage.PattayaDataRoadGround_<id>` and `ServerStorage.PattayaDataRoadGroundNoRaise` |
| Ground undo | `ServerStorage.RoadGroundBackup_20261022` | `ServerStorage.RoadGroundCity.<id>` (TerrainRegion `Voxels` + checksums) |

Every city part carries `RoadVisBatch = <id>`. A frontier piece also carries `RoadVisFor = <the batch that replaces
it>`.

### 1.3 Who owns a part

1. **Old road parts** (the containers and names of the pilot: `WideChunks` / `Chunks` Road, Sidewalk, Dash, Centre;
   `WideJunctions` / `Junctions` Junction, Joint; `ApronChunks` Road and Sidewalk; `FurnitureChunks` ZebraStripe).
   A batch takes a part when the centre of its footprint is in the box, or when the part overlaps the box by 1 stud²
   or more. The first batch built over a part takes it. Later batches never see it again.
2. **Frontier pieces.** A taken part can stick out of the box. Its outside piece is rebuilt at once, same footprint,
   as Road B asphalt (top 1.0) or sidewalk (top 1.6). It is cut along the grid and tagged with the batch that owns
   that ground. When that batch is built, it takes the frontier piece like an old part. So the road outside a box never
   gets a hole.
3. **Pilot parts** that stick out of the pilot box into a batch box are taken the same way. Their part inside the pilot
   box is rebuilt exactly.
4. **The pilot seam band.** Near its edge the pilot tapered into the old road and left out some asphalt and sidewalk
   (within 40 studs of the edge). The batch next to that edge builds them ("pilot-band completion"). For batch 1 this is
   164.5 studs² of asphalt and 126.8 studs² of sidewalk.
5. **City batch to city batch.** Both batches compute the ideal road from the same city-wide road chains (so the lane
   dashes keep one rhythm) and cut it on the shared edge. Every vertex on the edge stays on the edge. The two sides meet
   with no gap and no overlap. Nothing waits for a later batch.
6. **Invisible wheel support** (`RoadSupport`) follows the pilot's rule: where a removed old part carried a wheel within
   2 studs of the new asphalt and Road B puts no kerb there.
7. **Studio's float32 positions.** A part whose overlap is within 0.15 stud² of the 1-stud² line, or whose centre is
   within 0.15 studs of a box edge, gets an optional key: MoveReplaced accepts it moved or not. Every triangle is also
   written so that the builder splits it into the same two WedgeParts in float32 as offline (no near-tie between its
   two longest sides, no side within 0.004 studs of the builder's 0.05 skip). Without this, a later batch could miss a
   frontier piece by its position.

### 1.4 Build order and undo

- The data of batch N is made for one state: batches 1..N-1 built, the later ones not. `Plan`, `Build` and
  `MoveReplaced` check this (manifest `builtBefore`) and refuse otherwise. Build in plan order.
- **Last in, first out.** `RV.Remove(id)` refuses while a later neighbour is built, or while a later batch's backup
  holds this batch's frontier pieces. `RG.Remove(id)` refuses while a later raised box overlaps this one, or when the
  terrain in the box changed since the build (checksum). `RV.Remove()` (the pilot) refuses while a city batch next to the
  pilot is built.
- Removing a batch gives back exactly the state before it: every moved part goes back to its parent with its CFrame;
  the terrain comes back from its TerrainRegion and is checked against the checksum taken before the build.
- `RV.Leftovers()` and `RG.Leftovers()` list anything left behind after everything is removed.

### 1.5 The ground per batch

- **Height.** The box, widened to the 4-stud voxel grid, is raised to **+0.9**. Voxel layer y -4..0 gets occupancy
  0.725 over the full layer below. This is the leader's measured model: surface = centre of the top filled voxel
  + 4 x its occupancy. Build uses WriteVoxels with explicit occupancies, never FillBlock (FillBlock overshoots).
- **Ramp.** A 20-stud ramp falls back to -2 around the box.
- **Neighbours merge.** Build writes a column only where the data asks for more than what is there. A raised neighbour
  is never lowered. Two raised boxes merge with no ramp between them. The ramp shows only at the outer edge of the
  raised area. Batch 1 merges with the pilot's hand raise on z = 650.
- **Check first.** Every data column must be land as PattayaBuilder made it (layer -2 Ground full, layers -1 and 0 Air)
  or ground this builder raised. Anything else (water, sand, another builder's terrain) makes Plan say NOT READY, and
  Build writes nothing.
- **Never-raise zones** (data `PattayaDataRoadGroundNoRaise`, 6,019 runs of voxel columns, 93 KB): the sea and beach
  sand cells of the city terrain (8,802,305 and 89,536 voxel columns), every column outside the city terrain frame (the
  coast islands Ko Lan, Ko Sak and Ko Krok lie outside it; their boxes are kept with a 16-stud margin as a second net),
  and three landmarks with low parts that a raise would bury (Bali Hai pier, the Pattaya City sign, the Floating Market;
  8-stud margin). The plan never asks for a column there, near such a zone the plateau ramps down instead, and Build
  refuses a write there all the same.
- **Material.** Ground everywhere by default. Pavement near buildings is ready as an option:
  `RG.Build(id, {pavement = true})` (16,012 of the 25,740 columns of batch 1 would be Pavement).
- **Undo.** Build first copies the voxel box (layers -2..0) into `ServerStorage.RoadGroundCity.<id>` with checksums
  before and after. `RG.Remove(id)` pastes it back and checks the checksum.
- **The pilot's hand raise** is registered once: `RG.Adopt("pilot", ServerStorage.RoadGroundBackup_20261022,
  Vector3.new(6048, -3, 156))`. It copies the backup into the registry as seq 0. The terrain does not change.
- The ground adds no instance to workspace. Each batch keeps one TerrainRegion in ServerStorage.

## 2. The batch plan

![plan map](../art/roadcity/plan_map_city.png)

`art/roadcity/plan_map_city.png`: every batch box coloured by its road group, with its number. The pilot is the black
box, batch 1 the filled one. North is up.

**Order:**

1. b001: the owner's batch 1, Sukhumvit north of the pilot.
2. Sukhumvit: every cell with at least 20 studs of Sukhumvit, nearest to the pilot first, north and south in turn.
   This is the worst road class today (97.9 % of its edges are drops).
3. Beach Road, Second Road, Pattaya Klang / Central Road, North Pattaya Road, South Pattaya Road, Thepprasit Road,
   Jomtien Beach Road. Each road starts at the cell nearest to what is built and grows from there.
4. The rest of the city terrain frame, in 2 x 2 blocks of cells. A block with more than 2,400 old parts, or one that
   touches a built cell, is split into 2 x 1 rows or single cells. The block nearest to what is built goes first, so
   the built area grows without islands.
5. The Bira corridor east of the city terrain frame: Road B only. The ground is raised only where a corridor box
   reaches into the frame (5,588 voxel columns in all 23 corridor batches).

**Per road group (lean, offline counts):**

| # | Group | Batches | Cells | Parts added | Old parts moved | Net | Largest Atomic cell | Frontier pieces built | Ground columns | Poles on islands |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Sukhumvit Road (b001..b057) | 57 | 57 | 48,300 | 15,450 | +32,850 | 599 | 5,747 | 1,463,183 | 16 |
| 2 | Beach Road (b058..b070) | 13 | 13 | 9,847 | 5,648 | +4,199 | 481 | 1,162 | 266,792 | 0 |
| 3 | Second Road (b071..b079) | 9 | 9 | 8,818 | 3,625 | +5,193 | 517 | 709 | 223,505 | 0 |
| 4 | Pattaya Klang / Central Road (b080..b084) | 5 | 5 | 7,413 | 2,827 | +4,586 | 529 | 898 | 128,700 | 4 |
| 5 | North Pattaya Road (b085..b088) | 4 | 4 | 2,970 | 1,020 | +1,950 | 303 | 159 | 102,960 | 0 |
| 6 | South Pattaya Road (b089..b096) | 8 | 8 | 12,838 | 4,478 | +8,360 | 461 | 1,010 | 205,920 | 9 |
| 7 | Thepprasit Road (b097..b106) | 10 | 10 | 10,868 | 2,742 | +8,126 | 487 | 710 | 257,400 | 1 |
| 8 | Jomtien Beach Road (b107..b130) | 24 | 24 | 9,010 | 5,023 | +3,987 | 403 | 1,083 | 427,193 | 2 |
| 9 | rest (b131..b239) | 109 | 276 | 170,243 | 38,572 | +131,671 | 577 | 4,824 | 6,138,149 | 10 |
| 10 | corridor (b240..b262) | 23 | 92 | 8,219 | 2,793 | +5,426 | 280 | 860 | 5,588 | 0 |
| | **City** | **262** | **498** | **288,526** | **82,178** | **+206,348** | **599** | **17,162** | **9,219,390** | **42** |

**Running total of net parts (lean):** after Sukhumvit Road: +32,850; after Beach Road: +37,049; after Second Road:
+42,242; after Pattaya Klang / Central Road: +46,828; after North Pattaya Road: +48,778; after South Pattaya Road:
+57,138; after Thepprasit Road: +65,264; after Jomtien Beach Road: +69,251; after rest: +200,922; after corridor:
+206,348.

At the end every one of the 65,873 old road-layer parts has been taken by a batch. Frontier pieces still standing at the
end: 202 (their target box has no batch). The 1,822 pilot parts: 127 are taken by city batches next to the pilot.
Triangle rows nudged by 0.01..0.03 stud for the float32 split: 1,519 (of about 118,000); slivers dropped: 1.

The 23 corridor batches raise 5,588 ground columns, where their boxes reach into the city terrain frame; outside the
frame nothing is raised.

Net instances in workspace for a batch = its net parts + its Atomic cell Models + 1 Folder (all batches: +209,223). The
moved old parts go to ServerStorage with one Folder per source parent.

The whole list with every number is Appendix A; `build/roadcity/plan_batches.csv` and `plan.json` have more columns.

## 3. Budget

**The place today.** The QA runner's reference is 126,886 BaseParts in workspace (`PattayaQARunner.PART_REFS`, the sum
of its folders) and its warning line is **160,000** (`TOTAL_PARTS_WARN`). Studio counted about 184,000 `PattayaWorld`
descendants before the shoulder pilot (docs/STREAMING_ARCHITECTURE.md). The pilot added a net +1,040 parts (1,822 built,
782 moved to ServerStorage). Moved parts leave workspace, so the QA total counts only the net; they stay in the place
file until their backup is deleted.

| Variant | What it builds | Parts added | Moved | Net in workspace | Workspace estimate (126,886 + pilot 1,040 + net) | vs 160,000 |
|---|---|---|---|---|---|---|
| lean (default) | sidewalks and centre lines only on main roads (trunk, secondary, tertiary and their links; the graph has no primary roads) | 288,526 | 82,178 | +206,348 | 334,274 | OVER by 174,274 |
| full | sidewalks and centre lines on every road, as the pilot | 394,839 | 82,178 | +312,661 | 440,587 | OVER by 280,587 |
| lean2 | lean, with coarser collision outlines (simplify 0.5 instead of the default) | 248,655 | 82,178 | +166,477 | 294,403 | OVER by 134,403 |

**Where the lean parts go** (offline counts, all batches): asphalt 81,526 (28 %), sidewalk 69,161 (24 %), invisible
support 52,159 (18 %), kerb strips 15,681 (5 %), edge lines 15,442 (5 %), frontier asphalt 14,533 (5 %), lane dashes
13,695 (5 %), island 8,170 (3 %), centre lines 4,517 (2 %), grass 3,933 (1 %), stop lines 3,618 (1 %), zebra stripes
3,462 (1 %), frontier sidewalk 2,629 (1 %).

**Room under the warning line:** 160,000 - 126,886 - 1,040 = about **32,074** net parts, if the reference is close to
the real count (the leader's QA run gives the real number).

**Ways to bring it down.** Counts are measured on the lean data (offline); what each saves is the count of the parts it
removes. None of them is built; each needs its own go.

| # | Option | Saves (whole plan) | Saves (main roads, groups 1-8) | Cost / condition |
|---|---|---|---|---|
| A | **Road B only on the main roads** (130 batches); the ground at +0.9 on every city batch (no parts) | -137,097 (the rest and the corridor keep the old road) | 0 | the sois keep today's look and overlaps; the ground still removes their trench (road edge 0.1 above the ground); needs a ground-only QA mode in `city_batch` (small) |
| B | **No invisible RoadSupport wedges where the ground is raised** (they kept a wheel at 1.0 where an old part was wider; on ground at +0.9 the wheel sits 0.1 lower) | -52,147 | -12,724 | keep them near never-raise zones and in the corridor (no ground there); a small change in `city.make_batch`; it can start at any batch (built batches keep theirs) |
| C | **Markings and kerb strips as one visual mesh per Atomic cell** | -53,802 (56,415 marks, +2,613 meshes) | -27,612 | the meshes must be uploaded as assets (about 2,613); an EditableMesh made in Edit mode is not saved |
| D | **lean2: coarser collision outlines** (0.5 instead of 0.25) | -39,871 (measured run) | -13,529 | road edges up to 0.5 stud less exact |
| E | **Lane dashes every 40 studs** instead of 20 | about -6,847 | about -5,245 | sparser dashes (the wide world already uses longer gaps) |

**Examples:** main roads only in lean (A): net +69,251. With B as well: +56,527. With B and C: +28,915; with D instead
of lean, roughly +15,386. The room under the line is about 32,074. The whole city in lean is +206,348, in full +312,661.

**Recommendation:** build the main roads in lean first (they carry the traffic and the worst edges), with B added before
the rollout goes far (it changes no look), and decide C (mesh upload) before the rest of the city. Raise the ground on
every city batch: it costs no parts and removes the trench everywhere. The owner decides.

**Atomic cells and streaming.** Each batch builds about 10 Atomic `Cell_*` Models (2,613 in all); the largest holds 599
parts. The data caps a module at 600 parts and the streaming layout b cap is 1,500 per road cell
(docs/STREAMING_ARCHITECTURE.md), so every cell is well under it. The old chunk Models lose parts. The largest net
change within one 1,280-stud streaming radius (batch centres around world x 20020, z 3650) is +21,509 parts, against
about 19,000 instances that stream in after a teleport today (estimate from counts; not measured).

**QA runner caps.** `PattayaQARunner` checks parts per top folder and Atomic chunk caps. `WideChunks`, `ApronChunks` and
`FurnitureChunks` only lose parts. `RoadVisCity` is new: it shows as INFO and counts toward the 160,000 total, but it
has no chunk cap (`CHUNK_CAPS` has no entry, and its per-folder check would count a whole batch Folder as one chunk).
Proposed, not changed here: count `RoadVisCity.<id>.Cell_*` against a cap of 600, and add a parts reference for
`RoadVisCity` (the lean total above).

## 4. Batch 1 (b001)

**Box: world x 24220..24820, z 50..650, as the leader gave it.** It holds Sukhumvit Road (both carriageways, the
trunk links), the sois Sukhumvit Pattaya 38, 40 and 47 and Porn Prapa Nimit. Its south edge is the pilot's north edge
(z = 650), so the seam with the pilot is one straight line. I kept the box. Its edges cross the roads on straight
stretches, with one exception: Soi 40 runs along the north edge for about 75 studs (x 24430..24505), so the edge cuts
it lengthwise. Until b003 (the next box north) is built, the north half of that soi stays today's road. Moving the
edge would move the whole grid column; the cost is small, so the grid stays. The owner's second screenshot is at this
north edge: the junction there is inside batch 1, and the roads north of z = 50 are finished by b003. b003 is third in
the plan (b002 is the box south of the pilot). If the owner wants that spot finished first, swap the two in the plan
(`city.plan_city`, the Sukhumvit sort) and regenerate: the data of every batch is made for one build order.

**Studio data** (`build/roadcity/b001/`, OFFLINE, regenerate in the main checkout with
`city_cli.py batch b001 --art`):

| Item | Value |
|---|---|
| Road B parts built | 1,057: own pieces 514, pilot-band completion 124, frontier pieces 45 (for b003 and b175), markings and kerb strips 374 |
| By kind | asphalt 246, sidewalk 307, island 54, grass 22, invisible support 9, frontier asphalt 37, frontier sidewalk 8; lane dashes 155, edge lines 67, kerb strips 45, centre lines 39, zebra stripes 63, stop lines 5 |
| Old parts moved to ServerStorage | 539: Road 231, ZebraStripe 141, Apron 56, Dash 32, Centre 22, CornerFill 8, Joint 7, Junction 6, Sidewalk 4, and 32 pilot parts (RV Road 30, RV Dash 2); optional keys 0 |
| Net parts in workspace | +518 |
| Atomic cells | 7 (largest 476 parts); 7 data modules, largest 40.8 KB |
| Ground | 25,740 voxel columns (plateau 22,650, ramp 3,090), never-raise columns 0; data 55.0 KB |
| Data sha1 | Road B `021dd07cc78287368c19ee828d4f2b7e3cc2f9d1`, ground `ab0c4b2209e0d4d4bd25c71d79d0bfc6acd153fe` |

**Offline QA** (today = the pilot only; Road B = b001 built, ground not raised in b001; + ground = b001 at +0.9):

| Check | Today | Road B | Road B + ground |
|---|---|---|---|
| Lane samples in the core (the box less 20 studs along its open edges), 2,807 | holes / drops 393 / 386 | 0 / 0 | **0 / 0** |
| Lane samples along the open edges, 178 | 22 / 22 | 4 / 4 | 4 / 0 (lowest wheel 0.65) |
| Lane samples across the pilot seam (40-stud band), 336 | 34 / 24 | 0 / 0 | **0 / 0** |
| 1-stud grid over the box, 274,815 cells: steps of 1.5 or more | 5,554 (largest 3.6) | 4,221 (3.6) | **0** (largest 0.804) |
| The same over the pilot seam band, 38,700 cells | 311 (3.0) | 163 (3.6) | **0** (0.7) |
| Road edge to ground, largest step | 3.0 | 3.0 | **0.114** |
| Sidewalk outer edge to ground (a kerb face, as in the pilot) | 3.58..3.6 | 0.755..3.6 | 0.7..0.804 |
| Spot runs (63: every carriageway through the box and on 160 studs into the pilot, at offsets 0, +-14, +-20, +-24): runs with a drop or a hang / a climb | 37 / 32 | 18 / 12 | 2 / 0 |
| The same, runs clear of buildings (56) | 31 / 28 | 11 / 8 | **0 / 0** |
| Pilot shoulder path B (flip spot 2), 36 runs | 0 / 0 | 0 / 0 | 0 / 0 |
| Off-road runs: leave the road 14..24 studs and come back (48) / deep (24): runs with a drop | 25 / 12 | 6 / 6 | **0 / 0** (lowest static up 0.996 / 0.993) |

Notes on the table:
- The 4 lane samples along the open edges are at the north-east corner (world x 24786..24803, z 50..56): Sukhumvit
  northbound leaves the box there, and the old road beyond the edge lies a few studs off the new lane. With the ground
  at +0.9 a wheel there meets the ground 0.35 below the lane: a bump, not a drop. b003 removes it.
- The 2 spot runs with a hang are Soi 40 at 14 studs off its centre (no sidewalk there): one side of the car
  is over the unraised terrain north of the box, and both runs also go through buildings, so a car cannot drive them.
  They are not Studio drives.
- Street poles on median islands (listed, not moved): a LightPole at (24663.9, 421.4) and a NameSignPost at
  (24666.3, 414.2), on a 14.6-stud island, 4.0 and 3.5 studs from its edge. A car that hits them at 70 flips (the
  leader saw this in the pilot).

**What `RV.Probe("b001")` should count** (offline, from the probe samples in the manifest; per offset from the lane
centre line, the worst of 6 wheel points: flat = a road part at 0.9..1.1, kerb = 1.1..1.8, ground = no road part):

| Offset | In box | flat | kerb | ground | Seam band | flat | kerb | ground |
|---|---|---|---|---|---|---|---|---|
| 0 | 630 | 630 | 0 | 0 | 92 | 92 | 0 | 0 |
| 8 | 546 | 546 | 0 | 0 | 92 | 92 | 0 | 0 |
| -8 | 546 | 545 | 0 | 1 | 92 | 84 | 0 | 8 |
| 14 | 293 | 293 | 0 | 0 | 30 | 30 | 0 | 0 |
| -14 | 293 | 293 | 0 | 0 | 30 | 21 | 1 | 8 |
| 20 | 104 | 101 | 3 | 0 | 16 | 16 | 0 | 0 |
| -20 | 104 | 100 | 4 | 0 | 16 | 14 | 2 | 0 |
| 24 | 98 | 93 | 5 | 0 | 16 | 16 | 0 | 0 |
| -24 | 98 | 91 | 5 | 2 | 16 | 7 | 7 | 2 |

The few "ground" points are wheel points just past the edge of a narrow road with no sidewalk (lean design); none is
on a lane (the lane check above has 0 holes in the core).

**Previews** (local EEVEE renders and top views, OFFLINE, not Studio; left = today, right = Road B b001 + ground):
- `D:\ROBLOXRACE\.claude\worktrees\agent-ab546e318453f9c86\art\roadcity\b001_cmp_overview.png`
- `D:\ROBLOXRACE\.claude\worktrees\agent-ab546e318453f9c86\art\roadcity\b001_cmp_seam_from_batch.png`
- `D:\ROBLOXRACE\.claude\worktrees\agent-ab546e318453f9c86\art\roadcity\b001_cmp_seam_from_pilot.png`
- `D:\ROBLOXRACE\.claude\worktrees\agent-ab546e318453f9c86\art\roadcity\b001_cmp_seam_driver.png`
- `D:\ROBLOXRACE\.claude\worktrees\agent-ab546e318453f9c86\art\roadcity\b001_cmp_driver.png`
- `D:\ROBLOXRACE\.claude\worktrees\agent-ab546e318453f9c86\art\roadcity\b001_top_today_B_ground.png`
- `D:\ROBLOXRACE\.claude\worktrees\agent-ab546e318453f9c86\art\roadcity\b001_steps_today_B_ground.png`
- `D:\ROBLOXRACE\.claude\worktrees\agent-ab546e318453f9c86\art\roadcity\plan_map_city.png`

## 5. Studio procedure for batch 1

### Before anything (each one is required)

1. The owner's go-ahead for batch 1, in the owner's own words, for both the road parts and the terrain write. An agent
   message is not permission.
2. A fresh backup: the owner saves the place (Ctrl+S, Team Create synced) and a new dated `.rbxl`
   (docs/STUDIO_BACKUP_AND_RECOVERY.md).
3. `team20/road-city` merged. In the main checkout:
   `D:\ROBLOXRACE\.venv\Scripts\python tools\roadvis\city_cli.py batch b001 --art`, then
   `D:\ROBLOXRACE\.venv\Scripts\python tools\roadvis\city_cli.py bundle b001`, then
   `D:\ROBLOXRACE\.venv\Scripts\python tools\qa\tests\run_all.py -k roadcity` (all PASS). The data sha1 in
   `build/roadcity/b001/qa.json` (`studio_data.rv.sha1`, `studio_data.ground.sha1`) should equal section 4 if the main
   checkout's build inputs equal this branch's.
4. The place as on 2026-10-22: `RoadVisPilot` built (1,822 parts), `ServerStorage.RoadVisBackup` present (782 parts),
   the pilot ground raised by hand to +0.9, its backup `ServerStorage.RoadGroundBackup_20261022` present.
   No `RoadVisCity`, no `RoadGroundCity` yet.

### Steps (Edit mode unless noted)

| # | Do | Pass |
|---|---|---|
| 1 | Serve the bundle: `powershell -File tools\studio\serve.ps1 -Dir build\roadcity\b001\install -Port 8765 -Seconds 300`. In the command bar run the text of `build\roadcity\b001\install\install_b001.luau`. | `road city b001: installed 12 modules (...); expected 12 modules`; `HttpEnabled restored to false`. It creates or updates `PattayaRoadVisBuilder`, `PattayaRoadGroundBuilder`, `PattayaDataRoadVis_b001` (8 modules), `PattayaDataRoadGround_b001`, `PattayaDataRoadGroundNoRaise`. It deletes nothing. |
| 2 | `local RV = require(game.ServerStorage.PattayaRoadVisBuilder:Clone()) local RG = require(game.ServerStorage.PattayaRoadGroundBuilder:Clone())` (the Clone: Edit mode caches required modules; repeat this line in every new command) | loads |
| 3 | Baseline, read only: `print(RV.Status())`, `RV.Probe()` (the pilot) | `pilot: built, backup present`; `0 city batches built`; the pilot probe as on 2026-10-22 (total drops 0) |
| 4 | `RV.Plan("b001")` | `road vis plan b001 (plan seq 1, Sukhumvit Road): 7 modules, 7 cells, 1057 parts to build (own 514, pilot-band completion 124, frontier 45, markings / kerbs 374)`; `ORDER OK: build order: 1 batches must be built before b001: all built`; `move plan: Apron 56, Centre 22, CornerFill 8, Dash 32, Joint 7, Junction 6, RV Dash 2, RV Road 30, Road 231, Sidewalk 4, ZebraStripe 141 -> MATCHES the data; selected 539 (required keys 539, optional keys 0 of 0 matched); unmatched selected 0, required but not found 0`; `batch built: false; backup present: false`. **DOES NOT MATCH: stop**, report the listed parts (the place differs from the export, as the pilot's zebras did). |
| 5 | `print(RV.Build("b001"))` | `road vis b001: built 7 cells, 1057 parts (data 1057)` and no warning |
| 6 | `print(RV.MoveReplaced("b001"))` | `road vis b001: moved 539 parts (...) to ServerStorage.RoadVisCityBackup.b001; selected 539 (...); unmatched selected 0, required but not found 0`. On ABORTED nothing moved: stop, report. |
| 7 | `RV.Probe("b001")` | `18 legs, 722 samples; parts 1057 (data 1057); building overlaps 0; moved parts 539`; per offset the in-box flat / kerb / ground counts of section 4, each within 2 % (a hairline seam is counted apart, not as ground). More ground than offline: stop, report the first points it lists. |
| 8 | `print(RG.Adopt("pilot", game.ServerStorage.RoadGroundBackup_20261022, Vector3.new(6048, -3, 156)))` (once for the whole rollout) | `road ground: adopted pilot (voxels x 6048..6212, y -3..2, z 156..319) from ServerStorage.RoadGroundBackup_20261022 as seq 0`. It copies the backup; the original stays where it is. |
| 9 | `RG.Plan("b001")` | `road ground plan b001 (plan seq 1): 25740 voxel columns of layer y -4..0 (plateau 22650 at y 0.90 = occupancy 0.7250, ramp 3090 over 20 studs, never-raise 0, plateau columns lowered toward a never-raise zone 0); 0 new instances`; `terrain box: voxels x 6050..6209, z 7..167 (...): READY; 25740 data columns: 25740 as expected (...), 0 not; 0 in a never-raise zone (must be 0)`; `raised batches overlapping the box: pilot (seq 0)`; `shoulder terrain backups overlapping the box: 0 (must be 0)`. **NOT READY: stop**, report the line. |
| 10 | `print(RG.Build("b001"))` (`RG.Build("b001", {pavement = true})` only if the owner chose Pavement) | `road ground b001: raised N columns to y Y (median of 100 probes, LO .. HI); K data columns already as high or higher (a raised neighbour); Ground everywhere; registry ServerStorage.RoadGroundCity.b001 (seq 1)` with Y in 0.85..0.95 and N + K = 25740. K is the part of b001's data that the pilot's raise already covers (offline, with the pilot raise modelled as its box plus a 20-stud ramp: N 24,788, K 952; the hand raise may differ a little). On ABORTED the terrain is already put back (`restored exactly (checksum)`): stop, report. |
| 11 | `RG.Probe("b001")` | median 0.85..0.95, target 0.90; `road-to-ground edges: ... largest step` at most 0.3 (offline 0.185), `over 0.6: 0`; `grid 2 studs over the box: 90000 rays, floor steps >= 1.5: 0 (offline 0)`, largest floor step at most 0.9 (offline 0.77), `rays that hit nothing 0`; box edges: the lowest point within 8 studs of an outer edge is on the ramp (above -2), largest 1-stud step under 0.6 (the ground pilot's line); `registry: entry present` |
| 12 | `RV.Probe("b001")` and `RV.Probe()` again | as in steps 7 and 3 (the ground is below every road top) |
| 13 | Play mode, physics drives (below) | per run as below |
| 14 | A GPS route through the box, 2 minutes of traffic on Sukhumvit there, one Street Challenge whose route crosses it | the route line lies on the new asphalt; no traffic car on a sidewalk or an island; every gate reached, none on an island or sidewalk |
| 15 | Captures with Studio focused: top down over (24520, 350), a driver view on Sukhumvit northbound at (24560, 7, 700) looking at (24600, 4, 450), the seam at z 650 from both sides | compare with the previews in section 4 (the Blender images are only previews) |
| 16 | Frame times with Studio focused (worst, p99, 1 % low) at (24520, 350) | as near the pilot |

**Physics drives (step 13).** `build/roadcity/b001/drives.json` has 135 runs (car centre paths, world x, z).
Drive the ones with `studio = true`: 56 spot runs (every carriageway at offsets 0, +-14, +-20, +-24 that is clear
of buildings), 48 off-road runs that leave the road and come back, 24 deep off-road runs; 185 drives in all
(each speed in `speeds`). The minimum set if time is short: the 9 offset-0 spot runs at 70 and 100 and the
48 off-road runs at 35. Per drive: `TK.seatIn()`, `TK.jumpTo` the first point of `packed`, then
`TK.drivePath(packed, {physics = true, speed = s})`.
- **Pass, every drive:** no flip; `h.stats.minUp` at least 0.71 (the ground pilot's line; the leader saw 1.00 at +0.9);
  no recovery prompt during the run.
- **Pass, spot runs:** the car ends on the road (`TK.probeRoadUnderCar()`), road probes on the road all the way.
- **Pass, off-road runs:** the car gets back onto the road by itself.
- On a fail: note the run id, the speed and `h.stats`, stop, and report.

### Rollback (any time, in this order)

1. `print(RG.Remove("b001"))` -> `road ground b001: terrain restored EXACTLY (checksum ... = before the build); registry
   entry removed`. It refuses while a later raised batch overlaps the box. If it says NOT exact, keep everything and
   restore the dated `.rbxl`.
2. `print(RV.Remove("b001"))` -> `road vis b001: removed; restored 539 of 539 parts to their original parents; backup
   removed`. If a parent is gone, the backup is KEPT and the message says how many parts could not go back.
3. `print(RV.Leftovers())` -> `road vis city leftovers: none`. `print(RG.Status())` -> `pilot seq 0: ...; adopted`,
   `1 raised batches`. The adopted pilot entry can stay: it changes nothing. **Do not** run `RG.Remove("pilot")` unless
   the pilot ground itself must go: it pastes the 2026-10-22 backup back, so the pilot box goes back to -2.
4. Optional: delete `ServerStorage.PattayaDataRoadVis_b001` and `PattayaDataRoadGround_b001`.
5. Last resort: the dated `.rbxl`.

## 6. Every later batch

The same steps with the batch id, in plan order (Appendix A). `RG.Adopt` is done once, before batch 1 only.

1. Offline, in the main checkout: `city_cli.py batch <id> --art` (data, QA, drives, previews), then `bundle <id>`.
   `batch` recomputes every batch before it (measured in the plan run: 17 s per batch on average, so b057 takes about
   8 minutes and b262 about 76, plus about a minute for its own QA). The plan run already writes every batch's Road B
   data (`build/roadcity/data/<id>/roblox_rv`); `batch` adds the ground data, the QA and the drives.
   Check `build/roadcity/<id>/qa.json`, state `B_ground`: `lanes_core` holes 0 and drops 0; `lanes_box` drops 0;
   `grid_box` drop_cells 0; `road_edges.road_to_ground_max_step` at most 0.6; `spot_clear` with_drop 0 and with_climb
   0; `offroad` with_drop 0. Anything else: do not install it, report it.
2. In Studio: steps 1 to 16 of section 5 with the id. `RV.Plan` must say `ORDER OK` (every earlier batch built, no
   later one). `RG.Plan` lists the raised neighbours it merges with.
3. **Several batches in one session** is fine, in plan order: install each bundle, then for each batch RV.Plan, Build,
   MoveReplaced, Probe, then RG.Plan, Build, Probe; then one set of drives over all of them. Undo in reverse order.
4. A batch's data folders can be deleted once the owner keeps it for good. Its backups (`RoadVisCityBackup.<id>`,
   `RoadGroundCity.<id>`) are what makes Remove possible: delete them only on the owner's word. After that, only version
   history can undo the batch.
5. **Never rebuild the old road chunks or the city terrain while batches are built.** A chunk rebuild would recreate
   old parts that a backup also holds; a terrain rebuild would wipe the raised ground, and `RG.Remove` would then refuse
   (the box changed). Remove the batches first (last in, first out), or restore the place.

## 7. Risks

- **The data comes from the export, not from the place.** If the place differs (the pilot's zebras did),
  `RV.Plan` says DOES NOT MATCH and nothing is moved. Then regenerate from a fresh export, or patch the keys as the
  leader did for the pilot (Studio only, logged).
- **Open edges until the neighbour is built.** Where a batch ends and the old road goes on, the old road may sit a few
  studs off the new lanes. A lane can leave the asphalt there onto the raised ground (batch 1: 4 lane samples at the
  north-east corner, 0.35 below the lane, no drop). A road that runs along an open edge keeps today's edge on the far
  side (batch 1: Soi 40). The next batch removes both.
- **Street poles on narrow median islands are not moved** (rule). They are real crash objects at speed. Batch 1 has 2;
  the city count is in the plan (`poles_on_islands`). A car that hits one at 70 flips.
- **Parts.** The whole city in lean is +206,348 net parts against about +32,000 of room under the QA warning line
  (section 3). It is a QA heuristic, not an engine limit, but the server holds every part. Past the main roads the
  rollout needs a cheaper road build (options B and C, or a mesh collision layer) or a higher line set on measured
  frame times and memory.
- **The Bira corridor** gets Road B only. Its ground is outside the city terrain frame and is never raised by this
  builder, so its road edges keep today's drop until a separate terrain plan exists.
- **Float32.** Studio positions differ from offline by about 0.001 stud. Keys match within 0.3; parts on a box edge get
  optional keys; triangle splits are made unambiguous offline. Offline checks found 0 count mismatches in the written
  data; Studio is the final word.
- **Time.** 262 batches at roughly 45 minutes each in Studio (install, checks, drives) is weeks of sessions. Several
  batches per session (section 6) cuts that. The physics drives are the slow part.
- **The QA runner does not know the new folders.** `PattayaQARunner` has no chunk cap for `RoadVisCity` (its per-folder
  check would count a whole batch Folder as one chunk). Proposed, not changed here: count `RoadVisCity.<id>.Cell_*`
  against a cap of 600 and add a parts reference for `RoadVisCity`.
- **The offline model is not physics.** Spot and off-road runs are static (collision tops, a 4-wheel footprint). The
  Studio drives decide.

## 8. Questions for the owner

1. **Sidewalks:** lean (sidewalks and centre lines on main roads only; most Thai sois have none) or full (sidewalks on
   every soi; many more parts, over the QA warning line)? Recommended: lean.
2. **Ground colour:** plain Ground everywhere (default) or Pavement near buildings (`{pavement = true}`)?
3. **Poles on narrow islands** (2 in batch 1; the city count is in section 3): leave them, or ask a later team to move
   them a few studs? This task does not move furniture.
4. **Batch 1:** go? The leader installs after a fresh backup.
5. **Pace:** one batch per session, or several batches per session in plan order with one set of drives?
6. **Parts budget:** Road B on the main roads only for now (130 batches) with the ground raised on every batch, and
   options B (no invisible supports under raised ground) and C (markings as uploaded meshes) before the rest? Or a
   higher part line, set after the leader measures frame times and memory with the main roads built?

## Appendix A: every batch (lean, build order, offline counts)

| Batch | Group | Box (world x0..x1, z0..z1) | Added | Moved | Net | Atomic cells (largest) | Frontier | Ground columns | Poles on islands |
|---|---|---|---|---|---|---|---|---|---|
| b001 | Sukhumvit Road | 24220..24820, 50..650 | 1057 | 539 | +518 | 7 (476) | 45 | 25740 | 2 |
| b002 | Sukhumvit Road | 24220..24820, 1250..1850 | 903 | 572 | +331 | 7 (316) | 258 | 25740 | 0 |
| b003 | Sukhumvit Road | 24220..24820, -550..50 | 1480 | 391 | +1089 | 11 (420) | 407 | 25740 | 0 |
| b004 | Sukhumvit Road | 24820..25420, -550..50 | 913 | 763 | +150 | 6 (507) | 4 | 25740 | 0 |
| b005 | Sukhumvit Road | 23620..24220, 1850..2450 | 1820 | 410 | +1410 | 9 (381) | 278 | 25740 | 0 |
| b006 | Sukhumvit Road | 24220..24820, 1850..2450 | 583 | 384 | +199 | 5 (229) | 0 | 25740 | 0 |
| b007 | Sukhumvit Road | 24820..25420, -1150..-550 | 925 | 205 | +720 | 7 (373) | 76 | 25740 | 0 |
| b008 | Sukhumvit Road | 23620..24220, 2450..3050 | 1756 | 453 | +1303 | 9 (548) | 32 | 25740 | 0 |
| b009 | Sukhumvit Road | 24820..25420, -1750..-1150 | 924 | 346 | +578 | 8 (453) | 16 | 25740 | 0 |
| b010 | Sukhumvit Road | 23620..24220, 3050..3650 | 1292 | 261 | +1031 | 11 (243) | 126 | 25740 | 0 |
| b011 | Sukhumvit Road | 24820..25420, -2350..-1750 | 1906 | 330 | +1576 | 13 (403) | 342 | 25740 | 0 |
| b012 | Sukhumvit Road | 25420..26020, -2350..-1750 | 425 | 296 | +129 | 4 (299) | 94 | 25740 | 0 |
| b013 | Sukhumvit Road | 23020..23620, 3650..4250 | 1933 | 355 | +1578 | 9 (572) | 457 | 25740 | 2 |
| b014 | Sukhumvit Road | 23620..24220, 3650..4250 | 750 | 464 | +286 | 3 (404) | 0 | 25740 | 5 |
| b015 | Sukhumvit Road | 24820..25420, -2950..-2350 | 1373 | 271 | +1102 | 11 (458) | 42 | 25740 | 0 |
| b016 | Sukhumvit Road | 25420..26020, -2950..-2350 | 921 | 309 | +612 | 6 (295) | 26 | 25740 | 0 |
| b017 | Sukhumvit Road | 23020..23620, 4250..4850 | 710 | 325 | +385 | 9 (209) | 353 | 25740 | 0 |
| b018 | Sukhumvit Road | 23620..24220, 4250..4850 | 387 | 501 | -114 | 4 (245) | 0 | 25740 | 0 |
| b019 | Sukhumvit Road | 25420..26020, -3550..-2950 | 1435 | 269 | +1166 | 7 (599) | 244 | 25740 | 3 |
| b020 | Sukhumvit Road | 23020..23620, 4850..5450 | 1164 | 168 | +996 | 13 (199) | 247 | 25740 | 0 |
| b021 | Sukhumvit Road | 23620..24220, 4850..5450 | 604 | 216 | +388 | 3 (270) | 201 | 25740 | 0 |
| b022 | Sukhumvit Road | 25420..26020, -4150..-3550 | 975 | 446 | +529 | 10 (281) | 78 | 25740 | 0 |
| b023 | Sukhumvit Road | 23620..24220, 5450..6050 | 375 | 492 | -117 | 3 (159) | 4 | 25740 | 0 |
| b024 | Sukhumvit Road | 25420..26020, -4750..-4150 | 1834 | 290 | +1544 | 10 (499) | 308 | 25740 | 0 |
| b025 | Sukhumvit Road | 26020..26620, -4750..-4150 | 64 | 166 | -102 | 2 (39) | 0 | 25740 | 0 |
| b026 | Sukhumvit Road | 23620..24220, 6050..6650 | 281 | 106 | +175 | 4 (142) | 4 | 25740 | 0 |
| b027 | Sukhumvit Road | 26020..26620, -5350..-4750 | 405 | 136 | +269 | 6 (225) | 8 | 25740 | 0 |
| b028 | Sukhumvit Road | 23620..24220, 6650..7250 | 639 | 252 | +387 | 7 (373) | 30 | 25740 | 0 |
| b029 | Sukhumvit Road | 26020..26620, -5950..-5350 | 315 | 84 | +231 | 7 (165) | 30 | 25740 | 0 |
| b030 | Sukhumvit Road | 23620..24220, 7250..7850 | 367 | 188 | +179 | 6 (85) | 76 | 25740 | 0 |
| b031 | Sukhumvit Road | 26020..26620, -6550..-5950 | 1905 | 394 | +1511 | 8 (566) | 253 | 25740 | 0 |
| b032 | Sukhumvit Road | 23620..24220, 7850..8450 | 623 | 261 | +362 | 9 (286) | 110 | 25740 | 0 |
| b033 | Sukhumvit Road | 26020..26620, -7150..-6550 | 1582 | 473 | +1109 | 8 (329) | 117 | 25740 | 0 |
| b034 | Sukhumvit Road | 26620..27220, -7150..-6550 | 142 | 81 | +61 | 4 (77) | 16 | 25740 | 0 |
| b035 | Sukhumvit Road | 23620..24220, 8450..9050 | 1085 | 325 | +760 | 8 (241) | 49 | 25740 | 0 |
| b036 | Sukhumvit Road | 26620..27220, -7750..-7150 | 1523 | 234 | +1289 | 15 (374) | 82 | 25740 | 0 |
| b037 | Sukhumvit Road | 23620..24220, 9050..9650 | 433 | 231 | +202 | 6 (212) | 16 | 25740 | 0 |
| b038 | Sukhumvit Road | 26620..27220, -8350..-7750 | 1369 | 236 | +1133 | 9 (331) | 128 | 25740 | 0 |
| b039 | Sukhumvit Road | 27220..27820, -8350..-7750 | 1102 | 176 | +926 | 6 (521) | 164 | 25740 | 0 |
| b040 | Sukhumvit Road | 23620..24220, 9650..10250 | 245 | 110 | +135 | 4 (94) | 4 | 25740 | 0 |
| b041 | Sukhumvit Road | 27220..27820, -8950..-8350 | 583 | 233 | +350 | 8 (182) | 34 | 25740 | 0 |
| b042 | Sukhumvit Road | 27820..28420, -8950..-8350 | 630 | 203 | +427 | 7 (220) | 38 | 25740 | 0 |
| b043 | Sukhumvit Road | 23620..24220, 10250..10850 | 795 | 213 | +582 | 7 (229) | 67 | 25740 | 0 |
| b044 | Sukhumvit Road | 27820..28420, -9550..-8950 | 695 | 210 | +485 | 6 (271) | 190 | 25740 | 0 |
| b045 | Sukhumvit Road | 28420..29020, -9550..-8950 | 79 | 85 | -6 | 4 (36) | 0 | 25740 | 0 |
| b046 | Sukhumvit Road | 23620..24220, 10850..11450 | 1142 | 375 | +767 | 8 (349) | 163 | 25740 | 0 |
| b047 | Sukhumvit Road | 24220..24820, 10850..11450 | 177 | 199 | -22 | 4 (62) | 4 | 25740 | 0 |
| b048 | Sukhumvit Road | 24220..24820, 11450..12050 | 513 | 104 | +409 | 9 (192) | 14 | 25740 | 0 |
| b049 | Sukhumvit Road | 24220..24820, 12050..12650 | 197 | 44 | +153 | 4 (100) | 6 | 25740 | 0 |
| b050 | Sukhumvit Road | 24820..25420, 12050..12650 | 75 | 17 | +58 | 4 (26) | 2 | 25740 | 0 |
| b051 | Sukhumvit Road | 24820..25420, 12650..13250 | 572 | 206 | +366 | 6 (240) | 18 | 25629 | 3 |
| b052 | Sukhumvit Road | 24820..25420, 13250..13850 | 391 | 67 | +324 | 8 (126) | 50 | 21854 | 0 |
| b053 | Sukhumvit Road | 24820..25420, 13850..14450 | 1471 | 240 | +1231 | 11 (303) | 154 | 25740 | 0 |
| b054 | Sukhumvit Road | 25420..26020, 13850..14450 | 537 | 263 | +274 | 6 (230) | 24 | 25740 | 0 |
| b055 | Sukhumvit Road | 25420..26020, 14450..15050 | 777 | 133 | +644 | 8 (267) | 128 | 25740 | 0 |
| b056 | Sukhumvit Road | 25420..26020, 15050..15650 | 321 | 77 | +244 | 5 (230) | 130 | 25740 | 0 |
| b057 | Sukhumvit Road | 26020..26620, 15050..15650 | 820 | 272 | +548 | 4 (326) | 0 | 25740 | 1 |
| b058 | Beach Road | 21820..22420, -2950..-2350 | 1160 | 465 | +695 | 11 (282) | 70 | 25740 | 0 |
| b059 | Beach Road | 21220..21820, -2950..-2350 | 414 | 204 | +210 | 8 (210) | 37 | 25113 | 0 |
| b060 | Beach Road | 21220..21820, -2350..-1750 | 388 | 328 | +60 | 7 (221) | 36 | 20518 | 0 |
| b061 | Beach Road | 21220..21820, -1750..-1150 | 742 | 379 | +363 | 8 (229) | 76 | 19898 | 0 |
| b062 | Beach Road | 21220..21820, -1150..-550 | 390 | 214 | +176 | 8 (90) | 49 | 23105 | 0 |
| b063 | Beach Road | 20620..21220, -550..50 | 489 | 573 | -84 | 5 (344) | 90 | 6720 | 0 |
| b064 | Beach Road | 21220..21820, -550..50 | 565 | 330 | +235 | 11 (136) | 94 | 25740 | 0 |
| b065 | Beach Road | 20620..21220, 50..650 | 571 | 397 | +174 | 7 (171) | 162 | 18333 | 0 |
| b066 | Beach Road | 20020..20620, 650..1250 | 590 | 572 | +18 | 7 (217) | 120 | 11786 | 0 |
| b067 | Beach Road | 20620..21220, 650..1250 | 983 | 580 | +403 | 9 (367) | 108 | 25736 | 0 |
| b068 | Beach Road | 19420..20020, 1250..1850 | 705 | 365 | +340 | 9 (240) | 68 | 12910 | 0 |
| b069 | Beach Road | 20020..20620, 1250..1850 | 1303 | 639 | +664 | 12 (481) | 108 | 25457 | 0 |
| b070 | Beach Road | 19420..20020, 1850..2450 | 1547 | 602 | +945 | 10 (435) | 144 | 25736 | 0 |
| b071 | Second Road | 21820..22420, -2350..-1750 | 470 | 264 | +206 | 6 (292) | 21 | 25740 | 0 |
| b072 | Second Road | 21820..22420, -1750..-1150 | 573 | 323 | +250 | 6 (218) | 12 | 25740 | 0 |
| b073 | Second Road | 21820..22420, -1150..-550 | 646 | 318 | +328 | 9 (270) | 54 | 25740 | 0 |
| b074 | Second Road | 21820..22420, -550..50 | 567 | 264 | +303 | 11 (269) | 46 | 25740 | 0 |
| b075 | Second Road | 21220..21820, 50..650 | 1434 | 611 | +823 | 9 (432) | 68 | 25740 | 0 |
| b076 | Second Road | 21220..21820, 650..1250 | 711 | 324 | +387 | 11 (215) | 52 | 25740 | 0 |
| b077 | Second Road | 20620..21220, 1250..1850 | 1291 | 464 | +827 | 10 (331) | 140 | 25740 | 0 |
| b078 | Second Road | 18820..19420, 1850..2450 | 928 | 383 | +545 | 6 (330) | 56 | 17585 | 0 |
| b079 | Second Road | 18820..19420, 2450..3050 | 2198 | 674 | +1524 | 9 (517) | 260 | 25740 | 0 |
| b080 | Pattaya Klang / Central Road | 21820..22420, 50..650 | 1673 | 707 | +966 | 9 (529) | 155 | 25740 | 2 |
| b081 | Pattaya Klang / Central Road | 22420..23020, 50..650 | 2426 | 1004 | +1422 | 10 (522) | 443 | 25740 | 2 |
| b082 | Pattaya Klang / Central Road | 23620..24220, 650..1250 | 1048 | 276 | +772 | 10 (265) | 50 | 25740 | 0 |
| b083 | Pattaya Klang / Central Road | 23020..23620, 50..650 | 1521 | 393 | +1128 | 13 (444) | 198 | 25740 | 0 |
| b084 | Pattaya Klang / Central Road | 23020..23620, 650..1250 | 745 | 447 | +298 | 8 (228) | 52 | 25740 | 0 |
| b085 | North Pattaya Road | 22420..23020, -2950..-2350 | 599 | 276 | +323 | 6 (231) | 51 | 25740 | 0 |
| b086 | North Pattaya Road | 24220..24820, -2950..-2350 | 881 | 190 | +691 | 7 (262) | 36 | 25740 | 0 |
| b087 | North Pattaya Road | 23020..23620, -2950..-2350 | 463 | 136 | +327 | 10 (159) | 32 | 25740 | 0 |
| b088 | North Pattaya Road | 23620..24220, -2950..-2350 | 1027 | 418 | +609 | 9 (303) | 40 | 25740 | 0 |
| b089 | South Pattaya Road | 19420..20020, 2450..3050 | 3754 | 1189 | +2565 | 21 (373) | 262 | 25740 | 5 |
| b090 | South Pattaya Road | 20020..20620, 2450..3050 | 2442 | 1063 | +1379 | 13 (399) | 91 | 25740 | 4 |
| b091 | South Pattaya Road | 22420..23020, 3050..3650 | 1053 | 187 | +866 | 9 (301) | 178 | 25740 | 0 |
| b092 | South Pattaya Road | 23020..23620, 3050..3650 | 1195 | 359 | +836 | 12 (403) | 4 | 25740 | 0 |
| b093 | South Pattaya Road | 20620..21220, 2450..3050 | 2051 | 792 | +1259 | 11 (461) | 191 | 25740 | 0 |
| b094 | South Pattaya Road | 21820..22420, 2450..3050 | 567 | 135 | +432 | 7 (204) | 200 | 25740 | 0 |
| b095 | South Pattaya Road | 21820..22420, 3050..3650 | 1044 | 353 | +691 | 13 (392) | 38 | 25740 | 0 |
| b096 | South Pattaya Road | 21220..21820, 2450..3050 | 732 | 400 | +332 | 10 (197) | 46 | 25740 | 0 |
| b097 | Thepprasit Road | 22420..23020, 5450..6050 | 852 | 176 | +676 | 7 (384) | 164 | 25740 | 0 |
| b098 | Thepprasit Road | 23020..23620, 5450..6050 | 1439 | 392 | +1047 | 8 (376) | 0 | 25740 | 1 |
| b099 | Thepprasit Road | 21820..22420, 5450..6050 | 864 | 203 | +661 | 11 (294) | 38 | 25740 | 0 |
| b100 | Thepprasit Road | 21220..21820, 5450..6050 | 1263 | 289 | +974 | 11 (306) | 54 | 25740 | 0 |
| b101 | Thepprasit Road | 20620..21220, 5450..6050 | 1458 | 376 | +1082 | 9 (487) | 42 | 25740 | 0 |
| b102 | Thepprasit Road | 20020..20620, 5450..6050 | 658 | 169 | +489 | 8 (242) | 102 | 25740 | 0 |
| b103 | Thepprasit Road | 20020..20620, 6050..6650 | 818 | 194 | +624 | 9 (370) | 24 | 25740 | 0 |
| b104 | Thepprasit Road | 19420..20020, 6050..6650 | 949 | 238 | +711 | 10 (206) | 131 | 25740 | 0 |
| b105 | Thepprasit Road | 18820..19420, 6050..6650 | 1253 | 346 | +907 | 7 (432) | 20 | 25740 | 0 |
| b106 | Thepprasit Road | 18220..18820, 6050..6650 | 1314 | 359 | +955 | 12 (405) | 135 | 25740 | 0 |
| b107 | Jomtien Beach Road | 17620..18220, 7250..7850 | 381 | 243 | +138 | 8 (262) | 61 | 18241 | 0 |
| b108 | Jomtien Beach Road | 18220..18820, 7250..7850 | 854 | 237 | +617 | 8 (218) | 254 | 25740 | 0 |
| b109 | Jomtien Beach Road | 18220..18820, 7850..8450 | 1091 | 804 | +287 | 8 (297) | 32 | 18389 | 2 |
| b110 | Jomtien Beach Road | 18820..19420, 7850..8450 | 233 | 66 | +167 | 10 (91) | 68 | 25740 | 0 |
| b111 | Jomtien Beach Road | 18820..19420, 8450..9050 | 603 | 472 | +131 | 6 (160) | 26 | 20769 | 0 |
| b112 | Jomtien Beach Road | 18820..19420, 9050..9650 | 30 | 17 | +13 | 1 (30) | 12 | 3359 | 0 |
| b113 | Jomtien Beach Road | 19420..20020, 9050..9650 | 159 | 125 | +34 | 5 (90) | 18 | 22645 | 0 |
| b114 | Jomtien Beach Road | 19420..20020, 9650..10250 | 32 | 25 | +7 | 3 (14) | 14 | 5541 | 0 |
| b115 | Jomtien Beach Road | 20020..20620, 9650..10250 | 418 | 335 | +83 | 8 (209) | 26 | 24481 | 0 |
| b116 | Jomtien Beach Road | 20020..20620, 10250..10850 | 315 | 318 | -3 | 3 (149) | 23 | 9151 | 0 |
| b117 | Jomtien Beach Road | 20620..21220, 10250..10850 | 490 | 174 | +316 | 11 (122) | 76 | 25461 | 0 |
| b118 | Jomtien Beach Road | 20620..21220, 10850..11450 | 315 | 365 | -50 | 4 (140) | 18 | 14092 | 0 |
| b119 | Jomtien Beach Road | 21220..21820, 10850..11450 | 468 | 147 | +321 | 9 (171) | 26 | 25740 | 0 |
| b120 | Jomtien Beach Road | 21220..21820, 11450..12050 | 944 | 527 | +417 | 10 (391) | 53 | 20185 | 0 |
| b121 | Jomtien Beach Road | 21220..21820, 12050..12650 | 28 | 21 | +7 | 2 (22) | 10 | 4375 | 0 |
| b122 | Jomtien Beach Road | 21820..22420, 12050..12650 | 802 | 298 | +504 | 9 (188) | 152 | 24145 | 0 |
| b123 | Jomtien Beach Road | 21820..22420, 12650..13250 | 248 | 189 | +59 | 5 (129) | 24 | 9516 | 0 |
| b124 | Jomtien Beach Road | 22420..23020, 12650..13250 | 89 | 49 | +40 | 7 (31) | 12 | 25721 | 0 |
| b125 | Jomtien Beach Road | 22420..23020, 13250..13850 | 108 | 50 | +58 | 5 (33) | 14 | 17473 | 0 |
| b126 | Jomtien Beach Road | 22420..23020, 13850..14450 | 76 | 86 | -10 | 1 (76) | 14 | 3003 | 0 |
| b127 | Jomtien Beach Road | 23020..23620, 13850..14450 | 678 | 190 | +488 | 8 (403) | 40 | 23573 | 0 |
| b128 | Jomtien Beach Road | 23020..23620, 14450..15050 | 210 | 123 | +87 | 6 (119) | 28 | 11400 | 0 |
| b129 | Jomtien Beach Road | 23620..24220, 14450..15050 | 330 | 83 | +247 | 9 (115) | 82 | 25740 | 0 |
| b130 | Jomtien Beach Road | 23620..24220, 15050..15650 | 108 | 79 | +29 | 4 (51) | 0 | 22713 | 0 |
| b131 | rest | 25420..26620, -8950..-7750 | 353 | 153 | +200 | 6 (121) | 26 | 14795 | 0 |
| b132 | rest | 26620..27220, -8950..-8350 | 192 | 33 | +159 | 5 (117) | 0 | 15191 | 0 |
| b133 | rest | 27820..28420, -8350..-7750 | 148 | 34 | +114 | 2 (107) | 0 | 25740 | 0 |
| b134 | rest | 24220..25420, -7750..-6550 | 1134 | 272 | +862 | 10 (268) | 194 | 30494 | 0 |
| b135 | rest | 23020..24220, -7750..-6550 | 129 | 12 | +117 | 6 (44) | 8 | 33294 | 0 |
| b136 | rest | 21820..23020, -7750..-6550 | 432 | 44 | +388 | 6 (198) | 6 | 48334 | 0 |
| b137 | rest | 25420..26620, -7750..-7150 | 1057 | 409 | +648 | 12 (242) | 86 | 44057 | 0 |
| b138 | rest | 27220..27820, -7750..-7150 | 75 | 12 | +63 | 2 (67) | 0 | 25740 | 0 |
| b139 | rest | 25420..26020, -7150..-6550 | 2083 | 489 | +1594 | 9 (440) | 50 | 25740 | 2 |
| b140 | rest | 20620..21820, -6550..-5350 | 136 | 13 | +123 | 5 (85) | 14 | 56570 | 0 |
| b141 | rest | 21820..23020, -6550..-5350 | 5444 | 625 | +4819 | 32 (472) | 72 | 96390 | 1 |
| b142 | rest | 23020..24220, -6550..-5350 | 5304 | 683 | +4621 | 33 (539) | 88 | 96390 | 0 |
| b143 | rest | 24220..25420, -6550..-5350 | 3646 | 703 | +2943 | 30 (417) | 87 | 96390 | 0 |
| b144 | rest | 25420..26020, -6550..-5950 | 2521 | 535 | +1986 | 9 (423) | 48 | 25740 | 2 |
| b145 | rest | 26620..27820, -6550..-5350 | 40 | 17 | +23 | 2 (36) | 0 | 96390 | 0 |
| b146 | rest | 25420..26020, -5950..-5350 | 197 | 72 | +125 | 7 (104) | 4 | 25740 | 0 |
| b147 | rest | 20620..21820, -5350..-4150 | 280 | 29 | +251 | 7 (77) | 36 | 38058 | 0 |
| b148 | rest | 21820..23020, -5350..-4150 | 1805 | 279 | +1526 | 20 (224) | 62 | 96390 | 0 |
| b149 | rest | 23020..24220, -5350..-4150 | 6579 | 1097 | +5482 | 37 (526) | 251 | 96390 | 0 |
| b150 | rest | 24220..25420, -5350..-4150 | 4165 | 638 | +3527 | 30 (567) | 28 | 96390 | 0 |
| b151 | rest | 25420..26020, -5350..-4750 | 656 | 101 | +555 | 7 (219) | 0 | 25740 | 0 |
| b152 | rest | 20620..21820, -4150..-2950 | 900 | 190 | +710 | 18 (346) | 42 | 63726 | 0 |
| b153 | rest | 21820..23020, -4150..-2950 | 3027 | 601 | +2426 | 28 (366) | 139 | 96390 | 0 |
| b154 | rest | 23020..24220, -4150..-2950 | 5596 | 1213 | +4383 | 38 (442) | 22 | 96390 | 0 |
| b155 | rest | 24220..25420, -4150..-2950 | 3089 | 512 | +2577 | 32 (510) | 0 | 96390 | 0 |
| b156 | rest | 26020..26620, -3550..-2950 | 63 | 15 | +48 | 1 (63) | 0 | 25740 | 0 |
| b157 | rest | 20620..21220, -2950..-2350 | 43 | 45 | -2 | 2 (31) | 0 | 4443 | 0 |
| b158 | rest | 22420..23020, -2350..-1750 | 418 | 148 | +270 | 8 (247) | 18 | 25740 | 0 |
| b159 | rest | 23020..24220, -2350..-1750 | 2193 | 378 | +1815 | 18 (402) | 48 | 49890 | 0 |
| b160 | rest | 24220..24820, -2350..-1750 | 348 | 116 | +232 | 6 (113) | 13 | 25740 | 0 |
| b161 | rest | 22420..23020, -1750..-1150 | 318 | 87 | +231 | 4 (127) | 25 | 25740 | 0 |
| b162 | rest | 23020..24220, -1750..-550 | 3253 | 569 | +2684 | 23 (336) | 126 | 96390 | 0 |
| b163 | rest | 24220..24820, -1750..-1150 | 1199 | 242 | +957 | 9 (310) | 22 | 25740 | 0 |
| b164 | rest | 25420..26620, -1750..-550 | 195 | 94 | +101 | 2 (105) | 0 | 96390 | 0 |
| b165 | rest | 26620..27820, -1750..-550 | 166 | 39 | +127 | 2 (91) | 26 | 96390 | 0 |
| b166 | rest | 27820..29020, -1750..-550 | 406 | 122 | +284 | 10 (220) | 14 | 96390 | 0 |
| b167 | rest | 22420..23020, -1150..-550 | 1334 | 441 | +893 | 8 (281) | 54 | 25740 | 0 |
| b168 | rest | 24220..24820, -1150..-550 | 537 | 159 | +378 | 5 (253) | 0 | 25740 | 0 |
| b169 | rest | 22420..23020, -550..50 | 1326 | 639 | +687 | 12 (421) | 12 | 25740 | 0 |
| b170 | rest | 23020..24220, -550..50 | 2182 | 574 | +1608 | 22 (345) | 60 | 49890 | 0 |
| b171 | rest | 25420..26620, -550..650 | 347 | 107 | +240 | 8 (117) | 26 | 96390 | 0 |
| b172 | rest | 26620..27820, -550..650 | 217 | 77 | +140 | 7 (91) | 0 | 96390 | 0 |
| b173 | rest | 27820..29020, -550..650 | 75 | 30 | +45 | 3 (55) | 15 | 96390 | 0 |
| b174 | rest | 23620..24220, 50..650 | 1148 | 329 | +819 | 7 (442) | 0 | 25740 | 0 |
| b175 | rest | 24820..25420, 50..650 | 357 | 79 | +278 | 6 (151) | 0 | 25740 | 0 |
| b176 | rest | 21820..23020, 650..1850 | 6253 | 2132 | +4121 | 37 (577) | 169 | 96390 | 2 |
| b177 | rest | 24820..25420, 650..1250 | 86 | 18 | +68 | 2 (52) | 0 | 25740 | 0 |
| b178 | rest | 21220..21820, 1250..1850 | 1481 | 671 | +810 | 13 (491) | 8 | 25740 | 0 |
| b179 | rest | 23020..24220, 1250..1850 | 1607 | 333 | +1274 | 18 (417) | 4 | 49890 | 0 |
| b180 | rest | 18220..18820, 1850..2450 | 72 | 37 | +35 | 2 (61) | 0 | 7830 | 0 |
| b181 | rest | 20020..20620, 1850..2450 | 893 | 341 | +552 | 8 (286) | 44 | 25740 | 0 |
| b182 | rest | 20620..21820, 1850..2450 | 3273 | 1376 | +1897 | 16 (560) | 16 | 49890 | 0 |
| b183 | rest | 21820..23020, 1850..2450 | 2071 | 862 | +1209 | 13 (530) | 54 | 49890 | 0 |
| b184 | rest | 23020..23620, 1850..2450 | 661 | 119 | +542 | 7 (174) | 0 | 25740 | 0 |
| b185 | rest | 18220..18820, 2450..3050 | 198 | 90 | +108 | 2 (99) | 30 | 25740 | 0 |
| b186 | rest | 22420..23020, 2450..3050 | 593 | 249 | +344 | 5 (172) | 0 | 25740 | 0 |
| b187 | rest | 23020..23620, 2450..3050 | 137 | 32 | +105 | 5 (59) | 0 | 25740 | 0 |
| b188 | rest | 17020..18220, 3050..4250 | 3323 | 569 | +2754 | 24 (468) | 104 | 96390 | 0 |
| b189 | rest | 15820..17020, 1850..3050 | 236 | 15 | +221 | 3 (107) | 82 | 30826 | 0 |
| b190 | rest | 15820..17020, 3050..4250 | 1755 | 186 | +1569 | 18 (309) | 4 | 73882 | 0 |
| b191 | rest | 18220..19420, 3050..4250 | 5714 | 1701 | +4013 | 32 (450) | 267 | 96390 | 1 |
| b192 | rest | 19420..20620, 3050..4250 | 5295 | 1405 | +3890 | 33 (462) | 43 | 96390 | 0 |
| b193 | rest | 20620..21820, 3050..4250 | 3335 | 653 | +2682 | 31 (391) | 126 | 96390 | 0 |
| b194 | rest | 21820..23020, 3650..4250 | 1173 | 222 | +951 | 13 (309) | 4 | 49890 | 0 |
| b195 | rest | 15820..17020, 4250..5450 | 2358 | 305 | +2053 | 26 (341) | 82 | 79109 | 0 |
| b196 | rest | 17020..18220, 4250..5450 | 3420 | 581 | +2839 | 33 (283) | 60 | 96390 | 0 |
| b197 | rest | 18220..19420, 4250..5450 | 4712 | 1233 | +3479 | 24 (535) | 50 | 96390 | 0 |
| b198 | rest | 19420..20620, 4250..5450 | 4980 | 783 | +4197 | 32 (491) | 201 | 96390 | 0 |
| b199 | rest | 20620..21820, 4250..5450 | 5870 | 1062 | +4808 | 33 (525) | 16 | 96390 | 1 |
| b200 | rest | 21820..23020, 4250..5450 | 646 | 186 | +460 | 17 (115) | 0 | 96390 | 0 |
| b201 | rest | 15820..17020, 5450..6650 | 494 | 93 | +401 | 10 (227) | 22 | 53187 | 0 |
| b202 | rest | 17020..18220, 5450..6650 | 502 | 105 | +397 | 10 (202) | 22 | 96390 | 0 |
| b203 | rest | 18220..19420, 5450..6050 | 1352 | 282 | +1070 | 11 (296) | 8 | 49890 | 0 |
| b204 | rest | 19420..20020, 5450..6050 | 779 | 240 | +539 | 8 (347) | 0 | 25740 | 1 |
| b205 | rest | 20620..21820, 6050..6650 | 1428 | 190 | +1238 | 16 (291) | 24 | 49890 | 0 |
| b206 | rest | 21820..23020, 6050..6650 | 1207 | 174 | +1033 | 13 (221) | 8 | 49890 | 0 |
| b207 | rest | 17020..18220, 6650..7250 | 1560 | 306 | +1254 | 11 (516) | 18 | 42163 | 0 |
| b208 | rest | 18220..19420, 6650..7250 | 1492 | 673 | +819 | 12 (504) | 4 | 49890 | 0 |
| b209 | rest | 19420..20620, 6650..7850 | 1636 | 250 | +1386 | 20 (278) | 250 | 96390 | 0 |
| b210 | rest | 20620..21820, 6650..7850 | 1363 | 289 | +1074 | 18 (288) | 35 | 96390 | 0 |
| b211 | rest | 21820..23020, 6650..7850 | 2159 | 320 | +1839 | 16 (520) | 33 | 96390 | 0 |
| b212 | rest | 23020..23620, 6650..7250 | 318 | 61 | +257 | 6 (194) | 0 | 25740 | 0 |
| b213 | rest | 18820..19420, 7250..7850 | 1095 | 598 | +497 | 8 (345) | 0 | 25740 | 0 |
| b214 | rest | 23020..23620, 7250..7850 | 193 | 37 | +156 | 5 (66) | 11 | 25740 | 0 |
| b215 | rest | 19420..20620, 7850..9050 | 2324 | 516 | +1808 | 25 (425) | 24 | 96390 | 0 |
| b216 | rest | 20620..21820, 7850..9050 | 1965 | 237 | +1728 | 19 (263) | 96 | 96390 | 0 |
| b217 | rest | 21820..23020, 7850..9050 | 3326 | 357 | +2969 | 24 (467) | 139 | 96390 | 0 |
| b218 | rest | 23020..23620, 7850..8450 | 271 | 48 | +223 | 5 (79) | 31 | 25740 | 0 |
| b219 | rest | 23020..23620, 8450..9050 | 515 | 107 | +408 | 8 (168) | 26 | 25740 | 0 |
| b220 | rest | 20020..20620, 9050..9650 | 160 | 150 | +10 | 4 (65) | 14 | 25740 | 0 |
| b221 | rest | 20620..21820, 9050..10250 | 2678 | 737 | +1941 | 22 (512) | 28 | 96390 | 0 |
| b222 | rest | 21820..23020, 9050..10250 | 3168 | 549 | +2619 | 25 (569) | 307 | 96390 | 0 |
| b223 | rest | 23020..23620, 9050..9650 | 1100 | 200 | +900 | 10 (349) | 12 | 25740 | 0 |
| b224 | rest | 23020..23620, 9650..10250 | 202 | 67 | +135 | 7 (70) | 0 | 25740 | 0 |
| b225 | rest | 21220..21820, 10250..10850 | 313 | 133 | +180 | 9 (109) | 12 | 25740 | 0 |
| b226 | rest | 21820..23020, 10250..11450 | 2673 | 698 | +1975 | 18 (547) | 369 | 96390 | 0 |
| b227 | rest | 23020..23620, 10250..10850 | 1074 | 121 | +953 | 9 (390) | 78 | 25740 | 0 |
| b228 | rest | 24220..24820, 10250..10850 | 110 | 80 | +30 | 2 (102) | 0 | 25740 | 0 |
| b229 | rest | 23020..23620, 10850..11450 | 1537 | 522 | +1015 | 11 (399) | 10 | 25740 | 0 |
| b230 | rest | 21820..23020, 11450..12050 | 2251 | 736 | +1515 | 18 (383) | 21 | 49890 | 0 |
| b231 | rest | 23020..24220, 11450..12650 | 2190 | 315 | +1875 | 24 (355) | 36 | 96390 | 0 |
| b232 | rest | 22420..23020, 12050..12650 | 393 | 199 | +194 | 8 (143) | 0 | 25740 | 0 |
| b233 | rest | 23020..24220, 12650..13850 | 1284 | 343 | +941 | 19 (312) | 68 | 96390 | 0 |
| b234 | rest | 24220..24820, 12650..13250 | 185 | 195 | -10 | 4 (86) | 0 | 25740 | 0 |
| b235 | rest | 23620..24220, 13850..14450 | 101 | 17 | +84 | 2 (93) | 4 | 25740 | 0 |
| b236 | rest | 24220..24820, 13850..14450 | 440 | 56 | +384 | 8 (259) | 12 | 25740 | 0 |
| b237 | rest | 24220..25420, 14450..15050 | 892 | 159 | +733 | 12 (227) | 16 | 49890 | 0 |
| b238 | rest | 26020..26620, 14450..15050 | 6 | 124 | -118 | 1 (6) | 0 | 25740 | 0 |
| b239 | rest | 24220..25420, 15050..16250 | 252 | 71 | +181 | 8 (123) | 0 | 88960 | 0 |
| b240 | corridor | 29020..30220, -550..650 | 244 | 94 | +150 | 8 (74) | 20 | 5588 | 0 |
| b241 | corridor | 30220..31420, -550..650 | 152 | 95 | +57 | 7 (54) | 12 | 0 | 0 |
| b242 | corridor | 31420..32620, -550..650 | 47 | 26 | +21 | 2 (29) | 14 | 0 | 0 |
| b243 | corridor | 31420..32620, 650..1850 | 122 | 72 | +50 | 7 (38) | 14 | 0 | 0 |
| b244 | corridor | 32620..33820, 650..1850 | 264 | 87 | +177 | 7 (84) | 12 | 0 | 0 |
| b245 | corridor | 33820..35020, 650..1850 | 288 | 77 | +211 | 5 (167) | 22 | 0 | 0 |
| b246 | corridor | 33820..35020, 1850..3050 | 423 | 147 | +276 | 7 (141) | 12 | 0 | 0 |
| b247 | corridor | 33820..35020, 3050..4250 | 350 | 97 | +253 | 3 (174) | 12 | 0 | 0 |
| b248 | corridor | 35020..36220, 1850..3050 | 16 | 1 | +15 | 1 (16) | 14 | 0 | 0 |
| b249 | corridor | 35020..36220, 3050..4250 | 293 | 112 | +181 | 7 (126) | 12 | 0 | 0 |
| b250 | corridor | 36220..37420, 1850..3050 | 259 | 85 | +174 | 4 (157) | 22 | 0 | 0 |
| b251 | corridor | 36220..37420, 3050..4250 | 158 | 68 | +90 | 6 (71) | 14 | 0 | 0 |
| b252 | corridor | 37420..38620, 3050..4250 | 560 | 166 | +394 | 8 (171) | 12 | 0 | 0 |
| b253 | corridor | 38620..39820, 3050..4250 | 521 | 136 | +385 | 6 (184) | 22 | 0 | 0 |
| b254 | corridor | 39820..41020, 1850..3050 | 650 | 160 | +490 | 9 (210) | 24 | 0 | 0 |
| b255 | corridor | 39820..41020, 3050..4250 | 141 | 76 | +65 | 4 (58) | 0 | 0 | 0 |
| b256 | corridor | 41020..42220, 1850..3050 | 493 | 112 | +381 | 6 (216) | 12 | 0 | 0 |
| b257 | corridor | 41020..42220, 3050..4250 | 541 | 166 | +375 | 8 (185) | 4 | 0 | 0 |
| b258 | corridor | 42220..43420, 3050..4250 | 1016 | 199 | +817 | 11 (204) | 4 | 0 | 0 |
| b259 | corridor | 43420..44620, 1850..3050 | 400 | 34 | +366 | 2 (280) | 252 | 0 | 0 |
| b260 | corridor | 43420..44620, 3050..4250 | 924 | 226 | +698 | 11 (189) | 175 | 0 | 0 |
| b261 | corridor | 44620..45820, 1850..3050 | 269 | 187 | +82 | 1 (269) | 175 | 0 | 0 |
| b262 | corridor | 44620..45820, 3050..4250 | 88 | 370 | -282 | 2 (58) | 0 | 0 | 0 |
