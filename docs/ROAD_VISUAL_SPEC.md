# Road visual spec: design A vs design B (RayCity-quality roads on real Pattaya routes)

Status: **offline spec + offline pilot only.** Nothing has been built in Studio. The leader installs a pilot only after
the owner approves. All images are offline previews (PIL top-down and Blender Cycles renders of the exported
geometry), never Roblox visual acceptance and never a Visual PASS. Root cause and numbers:
`docs/ROAD_VISUAL_ROOT_CAUSE.md`.

| File | Role |
|---|---|
| `tools/roadvis/world.py` | Loads the built layers exactly as the builders build them (read only) |
| `tools/roadvis/analyze.py` | Defect metrics for one area and citywide |
| `tools/roadvis/junction.py` | Offline generator for one area, design A or B (collision, visual, markings, crossings, sidewalks / kerbs, islands), plus its checks |
| `tools/roadvis/shoulders_view.py` | Shoulder-pilot visibility in the owner's view, and the anti-flip drive gate (offsets 0, ±8, ±14, ±20, ±24) |
| `tools/roadvis/raster.py`, `scene.py`, `blender_preview.py` | Top-down images, Blender scenes, Blender renders |
| `tools/roadvis/cli.py` | `analyze [--city]`, `pilot [--art]` |
| `tools/roadvis/export_luau.py` | Design B pilot -> Studio data modules `build/roadvis/roblox/` (manifest + cells, <= 600 parts each, the exact replace list, probe samples + expectation) |
| `roblox/src/ServerStorage/PattayaRoadVisBuilder.luau` | Studio builder: Plan / Build / MoveReplaced / Probe / Remove / ShoulderLook (+Revert), offline-tested only |
| `tools/qa/tests/test_roadvis.py` | 29 offline tests (incl. the shoulder proof) (incl. the builder in the luau CLI on the real data: counts, cells, move / restore round trip, abort, shoulders untouched) |
| `build/roadvis/` (gitignored) | `analysis.json`, `compare.json`, `pilot_sukhumvit_klang_{A,B}.json`, `scene_{before,A,B}.json`, `top_*.png` |
| `art/roadvis/` | Small preview PNGs (top-down and the 4 camera views for before / A / B) |

Rerun the pilot and previews (about 25 s): `D:\ROBLOXRACE\.venv\Scripts\python tools\roadvis\cli.py pilot --art`

## 1. Constraints (confirmed by the owner)

- No Studio install by this team. No PattayaWorld rebuild. No citywide road rebuild.
- No change to the road graph, GPS, routing, checkpoints, traffic data or car physics. Graph files are read only (a
  test checks the hash).
- The approved shoulder pilot is never deleted or regenerated. Its anti-flip support must stay: the drive gate
  checks it.
- Pilot area: Sukhumvit / Pattaya Klang, world x 24220..24820, z 650..1250. This is the owner's screenshot area,
  around (24495, 962).

## 2. Layers (both designs)

1. **Connectivity graph (unchanged).** `graph_game.json` edges keep ids, polylines, widths and lanes. Routing, GPS,
   checkpoints and traffic read it as today. The visual and collision layers are derived from it and never write back.
2. **Carriageways.** Chains of graph edges joined through degree-2 joints (same direction, turn < 50°). Width =
   lanes x 13 (graph). Width changes taper at 4 studs per stud (20–90 studs). **Both** carriageways of a dual road are
   carriageways: no edge is hidden.
3. **Junction geometry (topology-aware, no discs).**
   - A node is an *intersection* only when two of its arms meet at 50–130°.
   - Merges, diverges and carriageway splits are not intersections. Their lanes run through, and the gore becomes an
     island.
   - Each intersection zone is the convex hull of the node and its arms' cross-sections at the **mouth**: the first
     point along the arm where its ribbon no longer touches another arm.
   - Zones that touch merge into one complex (dual-carriageway crossings).
   - Kerb returns are a morphological closing with radius 10, applied only inside the complex.
   - Where two chains meet, the hull of their end cross-sections closes the notch. It is never wider than the arms.
4. **Collision surface.**
   - **Design A:** collision = visual (Parts, as today).
   - **Design B:** collision is invisible (Transparency 1, CastShadow off). The asphalt is grown 0.3 (it tucks under the
     kerb), simplified 0.25, and triangulated as constrained Delaunay into WedgeParts with a flat top at 1.0.
     Sidewalks and islands are shrunk 0.3 (they never reach over the asphalt) and triangulated the same way.
     Collision covers 100 % of the visible asphalt (0.0 studs² uncovered).
5. **Visual surface (design B).**
   - One asphalt polygon per area, drawn at 1.01 (1 cm over any old part it meets at the seam).
   - Kerbed sidewalks at 1.6 and islands at 1.45, with a grass middle when wider than 6 studs.
   - Built as triangle meshes: one MeshPart per 128-stud tile for asphalt + markings, one for sidewalk / kerb / island.
     CanCollide, CanQuery and CanTouch all false.
6. **Sidewalk + kerb.**
   - An 8-stud sidewalk with a 1-stud kerb strip along every outer asphalt edge and around every island, on **all**
     tiers, Sukhumvit included.
   - It stops 0.5 short of buildings and never paves the far side of the seam.
   - It is cut back wherever a shoulder-pilot piece lies (section 7).
7. **Lane markings.**
   - Each carriageway is marked with its own lanes: dashes 8 / gap 12, one dash phase along the whole chain, so they
     are continuous across joints. A two-way road gets a double centre line.
   - Where two carriageways share asphalt (the compression overlap), the asphalt is split by nearest centreline
     (Voronoi). The split line becomes a double yellow between opposite directions and a solid white between
     same-direction ones.
   - Edge lines run 1.2 inside every kerb, never along the seam.
   - No lane, centre or edge markings inside the junction polygon. That polygon is the intersection complexes
     plus every place where two carriageways share asphalt at more than 12° to each other (merging slip roads, the
     field between Pattaya Klang and the slip roads), closed with a 12-stud radius. Only stop lines and zebras sit at
     its boundary. A stop line moves out along its leg (up to 60 studs) until it is clear of the field.
   - Same-direction carriageways that share asphalt get no separator line; each keeps its own lane dashes. The
     opposite-direction double line is straightened (simplified 2 studs) before it is drawn.
   - Stop lines (1.6 wide) on every inbound mouth: the left half on two-way roads (Thailand drives on the left).
8. **Crosswalks.**
   - Only on junction legs that have OSM crossing evidence within 60 studs of the mouth (the real Pattaya crossings).
   - Placed at the mouth + 1 + depth / 2, perpendicular to the leg.
   - Span the whole asphalt section kerb to kerb. Islands count as refuges (they may cross several carriageways).
   - Both ends must land on a sidewalk or island. Maximum span 110. No overlap with another junction or crossing.
   - Mid-block OSM crossings away from junctions are not drawn in the pilot. They need a sidewalk on both sides first.
9. **Signs.** Name signs and signals stay where furniture.py puts them (kerb + margin). With design B's sidewalks,
   signs and poles move onto the new sidewalk band. That is a furniture rerun (out of pilot scope).

## 3. Rules that forbid meaningless asphalt

- Asphalt = union of carriageway ribbons + node hulls + kerb-return fillets inside junction complexes. Nothing else:
  no discs, no fill triangles, no aprons.
- Checked: asphalt outside every lane corridor and outside the junction complexes (+ kerb radius) must be 0. It is
  **0.0** for B (198 for A).
- A terrain sliver narrower than 14 studs between carriageways, or an enclosed hole under 4,000 studs², becomes a
  raised kerbed island, never asphalt.
- No visual piece overlaps another (one polygon per layer; layer overlap 0.0).

## 4. Proportions

The car (7 x 15 chassis) and the 13-stud lane agree: 3.7–3.8 studs/m. The city is at 1.786 studs/m, so roads take
2.08x their real share and dual carriageways overlap. Options for the owner (none are in the pilot):

| Option | Effect | Cost / risk |
|---|---|---|
| a. Keep 13-stud lanes, render the overlap honestly (design B) | Shared asphalt is split by real direction lines. Islands appear where the real ones fit. | None to gameplay. The junction stays big, as in real Bangkok-scale junctions. |
| b. 11-stud lanes for slip roads / service carriageways only (`lane_w` in the generator) | About 15 % less overlap | Traffic lane offsets must be regenerated. Car feel on narrow lanes needs a drive test. |
| c. Local decompression around dual carriageways (move graph lines apart by up to 15 studs) | Real medians come back | Changes the graph and GPS: needs owner approval. |
| d. Buildings x1.3 height, footprints kept | Fixes "tiny buildings next to wide roads" from the driver's view | Building layer rebuild, outside road scope |

Recommendation: a (now), d (with the art team), b only after a drive test.

## 5. Design A vs design B (same junction, same checks)

- **Design A** = improve the existing generator. Keep slab Parts as visual = collision. Clip discs, aprons and fill
  triangles to the lane corridor and close the notches with node hulls. Merged slabs stay merged. Then apply the new
  marking, crosswalk, sidewalk and island rules on that surface.
- **Design B** = separate collision and visual surfaces, with new topology-aware geometry from the graph (both
  carriageways). Shoulder pieces are recoloured as a concrete gutter in its renders.

| | Before (built today) | Design A | Design B |
|---|---|---|---|
| Asphalt (studs²) | 85,516 (25.7 % stacked twice or more) | 84,177 | 90,406 (single polygon) |
| Disc overhang | 15,629 | 0 (clipped) | 0 (no discs) |
| Meaningless asphalt (outside lane corridors and junction complexes) | 470, plus blobs from fills and discs | 198 | **0** |
| Wheel drops on lane centres, 3,253 samples outside the seam band | 250 | 248 | **0** |
| Same, including the seam band (3,871) | 295 | 304 | 35 (at the seam, where the old merged slab continues outside) |
| Lane-boundary coverage (where the carriageway has asphalt) | 45.8 % visible / 11.9 % hidden | 98.9 % | **99.3 %** (all carriageways, outside the junction polygon) |
| Crossings | 18; 0 land on a sidewalk at both ends | 3 (both ends land) | 5 (both ends land, perpendicular, kerb to kerb; 2 across all of Sukhumvit, 104–109 studs) |
| Stop lines | none | at inbound mouths | at inbound mouths |
| Shoulder gate: drops after ≤ before at every offset (0 / ±8 / ±14 / ±20 / ±24) | baseline (0, 0/10, 0/74, 1/155, 3/247) | **fails at +14** (2 vs 0) | **passes**. In-lane drops 0 at every offset. Out-of-lane −24: 61 vs 247 |
| Kerb contacts (0.45–0.6 step up, no drop) at ±24 in-lane | 0 | 7 / 53 | 57 / 71 (carriageway edge = kerb line) |
| Parts in the area (the 799 replaced) | 799 (53 slabs, 338 fill, 27 discs, 141 aprons, 13 corner, 7 sidewalk, 63 markings, 157 zebra) | 2,090 (53 slabs, 807 wedges, 914 sidewalk + 68 island wedges, 248 marking Parts) | **1,457** with visual meshes (552 asphalt + 717 sidewalk + 146 island collision wedges + 42 MeshParts, markings inside the meshes); **1,935 with the default Parts build** (collision visible + 397 marking Parts + 64 kerb + 70 grass). The shoulder-safe collision (2026-10-21, docs/ROAD_B_OWNER_REVIEW.md section 6) costs about 550 parts over the first version. |
| Visual triangles | | 1,276 | 603 |
| Streaming (road-only Atomic cells, layout b: 256 studs, cap 1,500) | about 5.5 cells × 145 instances | about 310 per cell | about 165 per cell. 8 MeshParts per cell (each tile mesh streams with its cell). |
| Installation complexity | | Medium-high: changes to PattayaBuilder / road_fix / dual / aprons rules, chunk modules regenerated, RebuildChunks per batch. Touches tested code paths citywide. | Medium: a NEW builder + a new folder. Old parts in the area are moved to a backup folder (not deleted). Visual meshes need edit-time EditableMesh → MeshPart (or uploaded mesh assets). Fallback: visual as WedgeParts (+1,200 parts). |
| Rollback | Restore old chunk modules + RebuildChunks | One call: destroy the pilot folder and move the backed-up parts back. |
| Visual quality (offline preview) | Blobs, circles, broken lines | Cleaner outline, but the merged slabs still sit on the median, hidden lanes stay half built, and zebras cannot span the merged field | Crisp single surface, both carriageways, islands, kerbs, continuous lines, zebras kerb to kerb |

Part-level note: the Studio replace list counts real Parts with one footprint box each (a fill triangle is 2
WedgeParts). It is 804 parts, against 799 in the surface-level count above (same area rule).

**Recommendation: design B.** A cannot remove the main defects. They come from the merged-slab model (lane holes 248
vs 250, invented lane layout, zebras that cannot land), and A costs more parts (Parts for every marking) and touches
citywide code. B fixes the geometry from the graph without touching it, removes every disc and fill, keeps the
shoulder support, and uses fewer parts than A (1,935 against 2,090 as Parts). Both need more parts than today's 804
because they add sidewalks, islands and complete markings. Roll it out junction by junction with the same gates.

Images (offline previews, same owner camera for all three):

| | Before | Design A | Design B |
|---|---|---|---|
| Owner's camera (24609.8, 115.9, 713.3), look (-0.386, -0.386, 0.837), vertical FOV 70, 1831 x 1074 | `art/roadvis/cam_before_owner_view.png` | `art/roadvis/cam_A_owner_view.png` | `art/roadvis/cam_B_owner_view.png` |
| Aerial | `cam_before_aerial.png` | `cam_A_aerial.png` | `cam_B_aerial.png` |
| Street level (east kerb of Sukhumvit, eye 6 over the sidewalk) | `cam_before_street.png` | `cam_A_street.png` | `cam_B_street.png` |
| Driver (chase cam, northbound carriageway) | `cam_before_driver.png` | `cam_A_driver.png` | `cam_B_driver.png` |
| Top-down | `top_before.png`, `top_before_layers.png` | `top_A.png` | `top_B.png` |
| Strips | `cmp_owner_view.png` (before / A / B), `top_before_A_B.png` | | |

## 6. Part-count strategy

- Fewer, larger pieces. The collision is invisible, so its triangles may overlap and tuck under kerbs, and they can be
  large.
- Visual = a few meshes per 128-stud tile. Markings are in the mesh, not one Part per dash. Today's city has 8,631
  marking Parts and about 4,900 zebra bars.
- No decorative patch geometry (discs, aprons, fills, gap fills) is ever visible.
- Road-only containers, so they drop straight into the streaming layout b cells.

## 7. Shoulder pilot: coexistence and appearance (anti-flip support kept)

**Kept as is.** The builder, the data and the 2,536 parts are untouched. None of its parts is in the replace set (a
test checks this).

**Design B integration:**

1. The pilot asphalt (1.01) covers the shoulder pieces that lie inside the new carriageways. That is 4,018 studs² of
   strip (visible strip area 9,269 to 5,466 in the box), plus most gap fills. They still collide underneath (flush
   0.985), so their support is unchanged.
2. Sidewalks are cut back wherever a shoulder piece lies outside the asphalt. The strip stays flush and reads as a
   **concrete gutter** between the asphalt and the kerb, the RayCity kerb + gutter look. Every wheel footprint it
   supported is still supported.
3. Appearance change, proposed and owner-approved per step. These are property edits on existing parts, not
   rebuilds:
   - (a) Strips and tapers: Color 176, 174, 168 / Material Concrete (gutter look, used in the B renders), or asphalt
     46, 47, 52 if the owner prefers an invisible shoulder.
   - (b) Gap fills (362 pieces here, 154 visible in the owner view): set Transparency 1, keep CanCollide.
     Invisible collision, no speckle.
   - (c) Longer term, the shoulder data is regenerated from design B's visual outline (one straight strip per kerb
     run instead of ragged pieces). That is a new shoulder version that needs approval.

**Gate (keep it):** `shoulders_view.offset_drive`. A car footprint (4 x 9, 6 points, as `road_shoulders.drive`) runs
every 2 studs along every Sukhumvit carriageway at offsets 0, ±8, ±14, ±20, ±24. Drops after must be ≤ drops before at
every offset, and in-lane drops must be 0. B passes. A fails at +14.

## 8. Streaming

Both designs fit layout b from `docs/STREAMING_ARCHITECTURE.md` (team16): road-only Atomic cells of 256 studs, capped at
1,500 instances, with decoration non-atomic. Design B puts each 128-stud tile's 2 MeshParts plus its collision wedges
into the road cell of the tile. Cells stay under 200 instances in the pilot area. The A/B streaming test on main
(`docs/test_results/streaming_proto_ab.txt`: 0 road missing under the car while driving) is unaffected, because road
collision keeps arriving with its cell. The 1,871 ShoulderChunks parts in that test stay in their own road cells.

## 9. Pilot install for the leader (only after owner approval; NOT done by this team)

### What is ready (offline)

**Builder:** `roblox/src/ServerStorage/PattayaRoadVisBuilder.luau`. It is NEW and nothing else depends on it. It has
run only offline: the luau CLI with stub Roblox types on the real data, in `test_roadvis.LuauRoadVis`. It has never
run in Studio.

**Data:** `build/roadvis/roblox/` (written by `tools/roadvis/cli.py pilot` or `tools/roadvis/export_luau.py`):

- `manifest.luau`
- 10 `cell_<cx>_<cz>[q<qx><qz>][_k].luau` modules: at most 600 parts each. A 256-stud cell over 600 parts is split into its four 128-stud quadrants.

**The default build is Parts, 1,935 parts in 10 Atomic cells (Model `Cell_<id>`, at most 600 parts each):**

| Kind | Parts | Notes |
|---|---|---|
| Asphalt collision | 550 WedgeParts | Visible, named `Road` so RoadLook styles them like other roads |
| Sidewalk | 710 WedgeParts | Pulled back 0.3 from the asphalt only, never on a shoulder piece |
| Island | 144 WedgeParts | |
| Markings | 397 thin non-colliding Parts | lane 179, centre 36, edge 108, stop 6, zebra 68 |
| Kerb strips | 64 | |
| Grass | 70 | |

The replaced set is 804 parts. This list is checked part by part.

**Why Parts are the default:** a MeshPart made from an EditableMesh in Edit mode lives in memory only. It is not saved
or published unless the mesh is uploaded as an asset, it needs the EditableMesh API enabled, and it counts against the
EditableMesh memory budget.

**Opt-in mesh build:** `Build({mesh = true})` builds invisible collision (1,415 wedges) plus up to 7 MeshParts per cell.
It is a preview only, and it falls back to Parts when the API is missing.

### Edit-mode procedure (command bar, Studio focused)

1. **Save the place** (File > Save to Roblox, or a local copy). Check that version history has an entry.
2. **Put in the builder and data.**
   - `ServerStorage.PattayaRoadVisBuilder` gets the source of `roblox/src/ServerStorage/PattayaRoadVisBuilder.luau`.
   - Create Folder `ServerStorage.PattayaDataRoadVis` with ModuleScripts `manifest` and every `cell_*`, from
     `build/roadvis/roblox/`. Use the same localhost bundle method as the other data folders.
3. **Plan:** `local RV = require(game.ServerStorage.PattayaRoadVisBuilder) print(RV.Plan())`
   - Expected: `10 modules, 10 cells, 1935 parts to build`.
   - Move plan: `Road 397, Sidewalk 7, Dash 41, Centre 22, Junction 17, Joint 10, Apron 142, CornerFill 13,
     ZebraStripe 155 -> MATCHES the data; selected 804, expected 804`.
   - **If it says DOES NOT MATCH, stop.** The place differs from the build data (e.g. a chunk was rebuilt). Report the
     printed unmatched parts and do not continue.
4. **Build:** `print(RV.Build())`. Expected: `built 10 cells, 1935 parts (Parts)` and no warnings.
5. **Move the old parts:** `print(RV.MoveReplaced())`.
   - Expected: `moved 804 parts ... to ServerStorage.RoadVisBackup`.
   - It aborts and moves nothing if the selection differs from the list. It never selects anything in
     `ShoulderChunks` (two checks).
   - Every moved part keeps its attributes `OriginalParent` (path) and `OriginalCFrame`.
   - Each source parent gets a backup Folder with an ObjectValue `OriginalParentRef`.
6. **Probe:** `print(RV.Probe())`.
   - Expected per offset (0, ±8, ±14, ±20, ±24, in-lane samples only): `drop 0`.
   - Kerb contacts close to the offline values: about 3 at -20, 15 at +24, 20 at -24.
   - Building overlaps 0. Pilot parts 1935 (data 1935). Moved parts 804.
7. **Optional, only if the owner approves the shoulder look:**
   `print(RV.ShoulderLook({recolour = true, hideGapFills = true}))`. Revert with `RV.ShoulderLookRevert()`.
   - Strips and tapers become gutter concrete 176, 174, 168.
   - Gap fills get Transparency 1. CanCollide and CanQuery stay unchanged.
   - Original values are stored as attributes first.
8. **Captures (Studio window focused, Edit mode):**
   - The owner's camera: `workspace.CurrentCamera.CFrame = CFrame.lookAt(Vector3.new(24609.8, 115.9, 713.3),
     Vector3.new(24609.8, 115.9, 713.3) + Vector3.new(-0.386, -0.386, 0.837))`, FieldOfView 70, viewport 1831 x 1074.
   - Plus a top-down shot over (24520, 950) and a street-level shot at (24540, 7.6, 1040) looking at (24470, 4, 960).
   - Compare with `art/roadvis/cmp_owner_view.png`. The Blender images are previews; the Studio capture is what the
     owner judges.

### Play-mode checks (physics, Studio focused for frame-time numbers)

1. **Physics drives with the TestKit (`TK.drivePath` in physics mode, not CFrame mode)** at 50, 100 and 150 studs/s.
   Run them through every open direction of the junction:
   - Sukhumvit northbound (west carriageway, from z 1300 to z 600) and southbound (east carriageway, z 600 to 1300).
   - Pattaya Klang Road eastbound into the junction and westbound out of it.
   - Soi Sukhumvit Pattaya 53 (east arm) both ways.
   - Every slip road: `trunk_link` 35608372, 328550904, 688483203, 541666907, 541666908, 1010414884, 1010414885.
   - Soi 40/2.
   - Each leg on every lane: lane centres = carriageway centre ± (k + 0.5) × 13 − width / 2.
   - Sukhumvit also at offsets ±14 / ±20 / ±24.
   - Pass: the car stays upright, no wheel drop (the TK probe never reads terrain under a lane), no stuck kerb hits on a
     lane.
2. **GPS / routing:** route from the central grid to a job stand east of Sukhumvit. The route line follows the same
   graph (unchanged) and lies on the new asphalt in the area.
3. **Traffic:** watch the loops through the junction for 2 minutes. Traffic cars use the graph lanes; formerly merged
   edges keep `lane_adjust`. No car drives on a sidewalk or island. If one does, list the loop id.
4. **Checkpoints:** start a Street Challenge whose route crosses the junction. Every gate is reached and none sits on an
   island or sidewalk.
5. **Streaming (StreamingEnabled place copy only, if already set up):** the 7 `Cell_*` Models stream as Atomic units.
   Road is never missing under the car (TK report).
6. Record worst frame time, p99 and 1 % low with Studio focused. Unfocused numbers are invalid.

### Rollback (one call, any time)

1. `print(RV.ShoulderLookRevert())` if step 7 was done.
2. `print(RV.Remove())`. It destroys `RoadVisPilot`, puts all 804 parts back into their exact original parents with
   their original CFrames, and verifies the count. Expected: `restored 804 of 804 ... backup removed`.
   - If any parent is gone, the backup is KEPT and the message says how many parts could not be restored.
3. `RV.Plan()` must again show `pilot built: false; backup present: false` and the move plan matching.
4. Version history is the last resort.

The shoulder pilot (`ShoulderChunks`, 2,536 parts) is never moved, rebuilt or destroyed by any of these calls.

## 10. Preview renders (GPU box)

Upload `build/roadvis/scene_{before,A,B}.json` and `tools/roadvis/blender_preview.py` to
`vast-rtx6000-1:/root/robloxrace/road_p0/`, then run:

`bash /root/kit/fleet/gslot.sh -- /root/w/blender/blender -b --python-exit-code 1 --python blender_preview.py -- scene_B.json out B 48 0.75`

This renders Cycles GPU with a Nishita sky and sun. Only the scripts and the exported geometry are sent (no keys, no
.env).

## 11. Risks

- The default Parts build has more parts than it replaces (1,935 against 804) because every marking is a Part. The
  mesh build (1,457) needs EditableMesh assets that persist. Uploading the tile meshes as assets is the follow-up that
  brings the count down.

- MeshPart creation at edit time (EditableMesh) depends on Studio API availability and limits. The WedgePart fallback
  costs about 1,200 more parts in this area.
- The seam with old merged geometry: 35 wheel samples in the 40-stud band. The last 40 studs of each road taper to the
  old slab ends. Rolling B out to the neighbouring junctions removes the seams.
- Kerbs where there were bare edges: the car meets 0.45–0.6-stud steps at ±24 instead of falling 3 studs. A drive test
  must confirm the car physics handles them at speed (no physics change is planned).
- Furniture (signals, name signs, bus stops) was placed against the old kerbs. Some may stand on the new sidewalk or
  island edges until furniture.py reruns against the new outline.
- Traffic lanes on formerly merged edges were moved inside the merged slab (lane_adjust). With both carriageways
  built, traffic could use the true lanes again. That is optional and needs a traffic regen.
- Offline previews use flat colours and extruded footprints. Roblox lighting and materials will look different. This is
  not visual acceptance.
