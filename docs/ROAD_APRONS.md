# Junction aprons and sidewalk corner fills

Status: **data built, not built in Studio.** Nothing here has been seen in Studio yet. The leader installs and
builds it (steps below).

| File | Role |
|---|---|
| `tools/mapgen/junction_aprons.py` | generator: throats, aprons, corner fills, checks, determinism run, drop audit |
| `tools/mapgen/config/aprons.json` | heights, colours, clearances, cleanup and audit parameters |
| `roblox/src/ServerStorage/PattayaApronBuilder.luau` | `.Build({batch?, only?, folder?})`, `.Probe()`, `.Remove()` |
| `build/aprons/roblox/` (generated, gitignored) | `manifest.luau` + 375 `chunk_a<cx>_<cz>.luau` modules (2.0 MB) |
| `build/aprons/aprons.json` | counts, every junction handled / skipped with reasons, corners left open, checks, audit |
| `build/aprons/apron_check_*.png` | top views: aprons orange, corner fills cyan, props green, remaining drops red |

Rerun (about 30 s, determinism run included):
`D:\ROBLOXRACE\.venv\Scripts\python.exe tools\mapgen\junction_aprons.py tools\mapgen\config\aprons.json --build-root D:\ROBLOXRACE\build`
(`--no-determinism` skips the second run, `--audit-only` only prints the before-audit). The script exits with
code 1 if a check fails or the two runs differ.

## The problem
The terrain beside the roads is at y = −2, road tops are at 1.0 and sidewalk tops at 1.6. PattayaBuilder ends every
road slab at its node, puts a junction disc (radius r = the widest half-width) on top, and starts the sidewalks
r + sidewalk studs from the node. So at every junction corner and at every soi mouth the ground is open,
3 studs below the road, between the two slab edges and the two sidewalk ends. A car that cuts the corner or drifts
into a soi mouth at speed drops a wheel and flips.

Drive-test finding: at Beach Road / Soi Pattaya 8 (world x 21042–21070, z 50–110) the terrain at −2 lies between
the end of the Soi 8 sidewalk and the Beach Road slab. A 600-stud-radius audit around world (21040, 60) found 87 drop
clusters, all at junction edges. A blind "fill every drop cluster with a slab" prototype overlapped buildings,
light poles and palms in 27 of 66 cases and still left the soi mouth open, so it was removed. This layer works from
the road data instead.

## Method
Input: the **built** road data, the chunk modules of `build/central_pattaya`, `build/pattaya_wide` and
`build/bira/roblox_corridor` after road_fix / dual. They are read with `road_check.py`, which ports PattayaBuilder's
`stripe` / `offset` / `trim` 1:1, so slab pieces (`cutA` / `cutB` / `hide` / `hidden`), fill triangles, junction and
joint discs, and the sidewalk strips (`swSide`, the trims at discs and bends) are exactly what Studio has.
Obstacles: building boxes (both yaw senses, as `road_fix.building_boxes`), palms (r 1.0), street-light poles
(r 0.5), neon signs, furniture parts that reach down to the sidewalk (signal / sign / bus / taxi / utility poles,
shelter pads, walls, posts, benches), coast props, landmark parts, the Walking Street gate, and the corridor's trees,
poles and gantry legs.

1. **Arms.** Every edge with a slab at a junction node is an arm. Junction nodes are degree ≥ 3, plus degree-2 bends
   whose sidewalks are trimmed by a joint disc, a bend trim or a slab cut. Each arm gets a cross-section at
   s = r + sidewalk, where the builder starts its sidewalks (r = disc radius, else the bend trim, at least the slab
   cut; an edge without a sidewalk uses r + 6). The cross-section gives the slab edge points PL / PR at ±width/2,
   and the sidewalk outer corners QL / QR at ±(width/2 + sidewalk) on the sides that have a sidewalk.
2. **Throat.** The arms are sorted by angle. For each pair of neighbouring arms less than 170° apart, the throat
   piece is the triangle node – PL(i) – PR(i+1): the convex hull of the two cross-sections and the node. The throat
   polygon is the union of these triangles.
3. **Apron** (road height). The apron is the throat minus the road slabs, the fill triangles, the sidewalk strips,
   an inscribed 12-gon core of every disc, buildings (+0.5), props (+0.3) and earlier aprons. It is then cleaned
   (opening 0.08, clipped back, shrunk 0.03 so the 1 mm rounding never touches a neighbour) and cut into
   constrained-Delaunay triangles. A rectangle stays one Part. The top is at **0.98** (2 cm under the road top, so
   no z-fighting), 4 thick, Asphalt 62,63,68, named `Road`, attributes `RoadFill = true`, `Apron = true`, `JunctionId`.
   Aprons may lie under the edge of a disc or slab. They are coplanar and below it, which avoids arc slivers.
4. **Corner fill** (sidewalk height). For each pair of neighbouring arms with a sidewalk on at least one of the two
   facing sides, take the convex hull of PL, QL, QR, PR. For pairs 170°–180° apart (the straight side of a tee), add
   the node triangle. Subtract every road surface (slabs, fills, discs, aprons, +0.02), the sidewalks, buildings
   (+0.5) and earlier corner fills. A small prop inside the corner (palm, pole, post: the pit is ≤ 12 studs²) is cut
   out as a tree pit. A larger prop, or an open area > 900 studs² (an acute block, not a kerb corner), leaves the
   corner open, and it goes on the list. Top **1.58**, 3.6 thick, Concrete 150,148,142, named `Sidewalk`,
   attributes `CornerFill = true`, `JunctionId`.
5. **Output.** Same 512-stud chunk grid as the other layers (map-local centroid of each piece, `chunk_a<cx>_<cz>`),
   ORIGIN (20000, 0, 0) added by the builder, manifest + per-chunk modules, batches of ≤ 8 chunks ordered by distance
   from world (21040, 60). Rows: `aprons` / `corners` = flat triangles {x1, z1, x2, z2, x3, z3, junction},
   `apronBoxes` / `cornerBoxes` = {cx, cz, ux, uz, length, width, junction}. Each triangle becomes two WedgeParts,
   split at the foot of the altitude on the longest side, exactly like `PattayaBuilder.roadTriangle`.

## Counts (generator run 2026-10-19, digest `40c61bef`)
| | |
|---|---|
| junction nodes considered | 1,564 (1,510 junctions with 3+ ways, 54 trimmed bends) |
| handled (≥ 1 piece) | 1,509; 55 had nothing exposed (78 pairs with no throat because the neighbouring arms are ≥ 170° apart) |
| not considered | 95 dead ends, 1,095 degree-2 joints whose sidewalks run through, 187 nodes with fewer than 2 slab arms (hidden carriageways / very short edges) |
| apron pieces | 4,605 → **9,154 parts** |
| corner-fill pieces | 7,639 → **14,637 parts** |
| **parts total** | **23,791** in 375 chunks, 47 batches (largest chunk module 19 KB, none over 1,500 parts) |
| corners left open | 6: 1 acute block (node 411288137, map (−491, 3318), 1,424 studs² open); 5 tiny corners (2–6 studs²) with nothing left after building / prop clearance |
| props at the edge | 204 corner fills clipped around (or pitted for) a palm / pole; 18 throats clipped by a prop |

## Offline checks (all 0, asserted)
apron outside its throat polygon 0 · apron top not below the road top 0 · apron on a sidewalk strip 0 · corner fill
on a road surface / disc 0 · corner fill on a sidewalk strip 0 · piece intersects a building box 0 · piece intersects
a prop footprint 0 · two pieces overlap 0 · degenerate pieces 0. **Determinism:** two full runs, byte-identical
output. The modules re-parse (luau_table) to 23,791 parts, the same as the manifest and every chunk's `parts`.

## Drop audit (before → after)
Points every 3 studs on the line 2 studs outside the road surface (slabs + fills + discs). A point is a drop
(> 1.2 studs; the terrain is at −2, 3 under the road) when it lies on no sidewalk, corner fill, apron, building box or
shelter pad. Clusters use single linkage at 4.5 studs. "Sidewalk roads" = drops beside roads that have sidewalks
(the junction / kerb gaps). "Bare roads" = beside roads built without sidewalks, which have an open edge along their
whole length by design (most of the wide world).

| scope | samples | drop samples | clusters | sidewalk-road drops | sidewalk-road clusters | bare-road drops |
|---|---|---|---|---|---|---|
| citywide, before | 368,372 | 266,798 | 3,884 | 20,185 | 1,769 | 246,613 |
| citywide, after | 368,372 | 248,569 | 4,044 | **8,370** | **579** | 240,199 |
| 600 studs around (21040, 60), before | 2,533 | 359 | 35 | 330 | 35 | 29 |
| 600 studs around (21040, 60), after | 2,533 | **16** | **11** | 10 | 10 | 6 |

The before count (35 clusters) differs from the drive test's 87 because the method differs (that audit's sampling
is not documented). Citywide clusters go up slightly because filling the middle of a gap splits a long cluster
into its small leftovers. The leftovers are at tree pits, acute corners and junctions not handled (see
`aprons.json`). The bare-road edges are a separate, citywide issue: their kerb would need a road-shoulder layer, not
a junction fix.

## Leader's Studio build steps (save the place first)
1. `ServerStorage.PattayaApronBuilder` ← `roblox/src/ServerStorage/PattayaApronBuilder.luau` (new ModuleScript).
2. Create the Folder `ServerStorage.PattayaDataAprons`. Load `build/aprons/roblox/manifest.luau` and the 375
   `chunk_a*.luau` modules into it with the same JSON-bundle / HttpListener method as the other data folders
   (2.0 MB).
3. Pilot first: build batch `a1` (the Beach Road / Soi 8 area), drive the Soi 8 mouth and the Beach Road corners,
   then build the rest batch by batch (built chunks are skipped, so a call can be repeated):
   ```lua
   local A = require(game.ServerStorage.PattayaApronBuilder)
   print(A.Build({batch = "a1"}))   -- then "a2" ... "a47" (manifest.batchOrder)
   print(A.Probe())                  -- wanted: obstacle hits 0, aprons above road top 0, corner fills above
                                     -- sidewalk top 0, corner parts on a road surface 0, ray covered 0,
                                     -- part counts = data
   ```
   `Build` warns if a chunk's part count differs from the data's `parts`.
4. Visual check at world (21056, 80): an asphalt chamfer at each Soi 8 corner (the orange pieces in
   `apron_check_soi8_beach_road.png`) and concrete corners closing the sidewalk gaps (cyan), incl. the Beach Road
   beach side.

**Rollback:** `require(game.ServerStorage.PattayaApronBuilder).Remove()` destroys only
`workspace.PattayaWorld.ApronChunks`. Nothing else in the place is changed by Build.

## Unverified / notes for the leader
- Not seen in Studio: look, collision and the probe numbers are offline predictions only.
- Material: aprons use `Enum.Material.Asphalt` and corner fills `Concrete`, as specified. The city roads are
  SmoothPlastic, textured through RoadLook. If RoadLook / MaterialVariants select by part name (`Road`, `Sidewalk`),
  the new parts may pick up the variant; if they select by material, the aprons may look different. Check the
  pilot batch.
- Parts: +23.8k parts on top of the roughly 56k-part world (streamed per Atomic chunk). If that is too many, set
  `min_piece_area` / `min_corner_area` higher or build only the central batches.
- Terrain is assumed at −2 everywhere beside the roads (sand and sea included). Mesh palms (VisMesh) are assumed at
  the palm rows' positions.
- Other scripts that count or probe parts named `Road` / `Sidewalk` will now see these. Aprons carry `RoadFill = true`
  (the slab-overlap probe already skips that); corner fills carry `CornerFill = true`.

Map data © OpenStreetMap contributors, ODbL 1.0.


## Studio result (leader, 2026-10-20 16:30)
Built citywide after the owner's backup: 375 chunks, 23,787 parts (9,154 apron + 14,633 corner). Probe: aprons above road
top 0, corner fills above sidewalk top 0, sidewalk overlaps 0, obstacle hits 4 (2 signal poles + 2 utility poles standing
inside a corner fill — harmless). The probe's "corner parts on a road surface 1,602" is a bounding-box test; an exact
raycast check of 42,734 points on corner-fill tops found 0 places where a fill sits above a road surface. Pilot area
road-edge drops 771 → 131; drives: Beach Road → Bira 425/426 with no tilt below 0.9, Central Loop 102/103 up min 0.99.
