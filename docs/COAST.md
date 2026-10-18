# Coast: shoreline, beach props, horizon (team4/coast, 2026-10-19)

**Status: written, NOT built in Studio.** Every number below comes from `tools/mapgen/coast.py` and its export-time
checks (shapely, numpy). `PattayaCoastBuilder.luau` compiles with `luau-compile` and its terrain-run decoding was
run against a stub `WriteVoxels` in the `luau` CLI. It has not run in Studio: no Studio screenshot exists and the probe
has not run.

Map data (c) OpenStreetMap contributors, ODbL 1.0. Elevation for the islands: Terrain Tiles (Terrarium, AWS Open
Data, z13). No RayCity assets and no brands: plain geometry, generic text ("BEACH BAR").

## What changed
All files are new. Nothing existing was edited: no exporter, layout, buildings, traffic or PattayaBuilder code, and
no chunk or manifest output.

| file | what |
|---|---|
| `tools/mapgen/coast.py` | the coast pass (terrain plan, props, islands, export, checks, images) |
| `tools/mapgen/config/coast.json` | every rule and number used |
| `data/osm/queries/koh_larn.overpassql`, `data/osm/raw/koh_larn_2026-10-19.json` | Koh Larn, Ko Sak and Ko Krok coastlines. **OSM base 2026-10-18T18:26:36Z**, downloaded 2026-10-19 from overpass-api.de with curl.exe (it needs a User-Agent header now: 406 without one) |
| `data/dem/terrarium/13_6388..6389_3798..3800.png` | 6 DEM tiles over the islands |
| `roblox/src/ServerStorage/PattayaCoastBuilder.luau` | builder: `Build/Remove`, `BuildTerrain/RemoveTerrain`, `BuildIsland/RemoveIsland`, `Probe` |
| `build/coast/roblox/` (gitignored, regenerate) | `manifest`, 48 `chunk_b<cx>_<cz>`, 26 `terrain_<n>`, 20 `fill_<n>` (95 modules, 980 KB, largest 35 KB) |
| `docs/images/coast_*.png` | check images: the old shoreline on the left, the new one on the right |

Command (repo root): `.venv\Scripts\python tools\mapgen\coast.py tools\mapgen\config\coast.json`. It needs
`build/central_pattaya` and `build/pattaya_wide` (graph_game.json, buildings_game.json, layout.json,
roblox/manifest.luau, roblox/joints.luau) from the mapgen pipeline. A rerun writes a byte-identical `build/coast/roblox`.

## 1. Shoreline terrain

### The old edge (measured from the data, not from Studio)
`PattayaBuilder` carved the sea on a **16-stud raster**: each sea row is 16 studs tall, its water runs end on a
16-stud column, and a 48-stud sand strip follows east of each run's end. `coast.py` replays exactly what `Build()`
and then `Extend({roads = false})` wrote: frame clear and fill, ground rectangles, sea rows, sand strips, and every
`Region3:ExpandToGrid(4)` snap. The result is the material of every 4 × 4-stud column in the three voxel layers
y -16..-12, -12..-8 and -8..-4. In the replay the shoreline is a 16-stud staircase (image left halves).

**Found while replaying: a 4-stud trench at the base/wide seam.** The wide ground rectangle north of the base frame
ends at z = -3776 (`f4(bminz)`), but the base frame starts at z = -3772 (the rounded `manifest.frame.minZ`). The row
z -3776..-3772, x -2068..3608 gets no terrain from either builder. It is **Air in the sea** (a dark line about
2,900 studs long, 737 cells) **and on land** (682 cells, a 4-stud-deep trench across north Pattaya
wherever no road slab covers it). The coast pass fills the sea part with water. The land part lies landward of the
beach, so it is left as it is: **PattayaBuilder owner to fix** (fill z -3776..-3772 inside the base frame's x range
with ground -16..-4).

### The new edge
Cells near the real OSM coastline (the wide world's sea mask: the main coastline split from the frame, minus the
islets) are classified by their signed distance `d` to the coastline, in studs (sea < 0). **The writes use 4-stud
cells along the real polyline**, the finest the 4-stud voxel grid allows:

| zone | voxels top / mid / low | cells written |
|---|---|---|
| deep sea, d ≤ -40 | Water / Water / Water | 745 (the seam row only) |
| mid water, -40 < d ≤ -16 | Water / Water / **Sand** (8 studs of water over sand) | 63,097 |
| shallow water, -16 < d < 0 | Water / **Sand** / Sand (4 studs of water: the sand shows through) | 41,521 |
| wet sand, 0 ≤ d < 8 | **Mud** / Sand / Sand; `Terrain:SetMaterialColor(Mud, 148,126,92)` | 18,606 |
| dry sand, d ≥ 8, old water | Sand / Sand / Sand | 361 |
| dry sand, old sand strip | unchanged | 0 |

**Total: 124,330 cells in 7,917 runs.** A run is one 4-stud row of contiguous cells, written with one
`Terrain:WriteVoxels` call over exactly those cells (full occupancy, grid-aligned). There are 26 modules, one per
2048-stud tile or part of one. Mud is used nowhere else in the place: terrain uses Ground, Sand, Water and Grass
(the circuit). `BuildTerrain` keeps the old Mud colour in the Terrain attribute `CoastMudColorBefore`, and
`RemoveTerrain` restores it.

**Where a write may go (asserted after planning):**
- (a) the cell's old top voxel is Water or Sand (the sea and the old strip). The only Air cells written are the seam
  row's sea cells.
- (b) **the next 2 cells to the east are still Water/Sand: every write stays seaward of the sand strip's landward
  edge.** The edge was measured from the replay: 7,232 strip ends, each a Sand cell whose east neighbour is not
  Water/Sand. The smallest gap between a written cell and the edge in its row is 2 cells (asserted ≥ 2).
- (c) the cell's 4 × 4 square is clear of every road + sidewalk (both sides, central + wide), every junction and
  joint disc, and every building box, each grown by 4 studs, and clear of the landmarks team's areas (Bali Hai
  Pier way 504916659 + 60 studs, Dolphin Circle way 385837306 + 120 studs). Result: **0 cells touch** (asserted).
  11,826 candidate cells were blocked by this rule.
- The written modules are read back the way the builder reads them. The new codes reproduce the plan, and the old
  codes restore the replayed old terrain cell for cell (asserted).

**Limits (what this cannot do):**
- The water/sand edge now steps 4 studs, not 16. Smaller steps are impossible: a material change between two
  voxels is drawn at the 4-stud voxel boundary (Roblox blends the two textures there). The water surface stays flat
  at y = -2, so the "gradient" is the sea floor stepping up under the water (deep → 8 studs → 4 studs), not a
  change in water height.
- **The landward sand/ground boundary is still the old 16-stud staircase.** Smoothing it would mean writing the edge
  cells themselves, which this pass is not allowed to do. The probe checks exactly those cells.
- The 48-stud strip is narrow where the coast runs diagonally (Jomtien). Brown Ground lies between the strip and
  Beach Road even where OSM maps the whole width as beach. See the optional fill below.
- Cells near piers, the Walking Street end and the other teams' areas keep their old staircase (blocked cells).
- The seam trench on land is not fixed (see above).

### Optional: landward beach fill (opt-in, NOT part of the default pass)
`BuildTerrain({fill = true})` writes Ground → Sand in the **top voxel only**, for cells inside the 21 OSM
`natural=beach` polygons (within 260 studs of the coast), clear of every road, disc and building (+4 studs) and of
the other teams' areas: **108,504 cells, 4,275 runs, 20 modules** (6,591 cells blocked). It turns the brown band
between the narrow strip and Beach Road into sand that follows the OSM beach outline, and that smooths the landward
staircase. See `docs/images/coast_fill_jomtien.png` and `coast_fill_pattaya_n.png`.
**It moves the sand strip's landward edge, which the brief told this pass not to do. So it is a separate call for the
leader/owner to decide on.** Run the probe before it: afterwards the landward-edge samples report "changed" by
design. Undo with `RemoveTerrain({fill = true})`.

## 2. Beach props
The rules are in `coast.json` → `props`. Beaches are OSM ways 149698464 (Pattaya Beach) and 1297672173 (Jomtien
Beach). Stations are spaced along the real coastline inside the beach polygon (+25 studs). The normal points inland.

| prop | rule | count | Parts |
|---|---|---|---|
| umbrella + 2 loungers | rows 20 and 34 studs inland of the waterline, every 15 studs, ±1.5 stud jitter, the whole set on dry sand (new terrain) | 1,278 (Pattaya 495, Jomtien 783) | 5,112 |
| promenade lamp (base, pole, globe "Lamp") | every 60 studs along the sea side of every coastal road (Beach Road, Jomtien Beach Road, Naklua Road), 3 studs outside the sea-side sidewalk, on land, ≥ 6 studs from a palm, ≥ 20 from a street light; a SpotLight on every second lamp | 165 (Pattaya 79, Jomtien 81, Naklua 5) | 495 |
| lifeguard tower | every 600 studs of coastline, 14 studs inland (8 / 20 / 10 tried) | 24 | 168 |
| beach-bar hut, NightNeon trim + "BEACH BAR" board | every 520 studs, 40 studs inland where the sand is wide enough (often not: 67 spots rejected) | 20 | 120 |
| moored boat (longtail / speedboat proxy, anchored, no collision) | 12 per beach at Pattaya and 14 at Jomtien, 70–150 studs offshore, over water, 20+ studs from any pier | 26 (13 + 13) | 78 |
| parasail (canopy 70–95 studs up, tow line, speedboat) | 4 off Jomtien, 220–280 studs out | 4 | 20 |
| **total** | | | **5,993** |

- **Palms are not doubled.** The 435 existing palms (157 central + 278 wide, from both `layout.json`) are read in,
  and every prop footprint keeps ≥ 6 studs from each of them (asserted: 0 within 6). No new palms are placed. The
  1,769 street lights are read in too.
- **Export-time check (asserted): 0 prop footprints touch a road + sidewalk, a junction/joint disc or a building**
  (central + wide; no clearance in the check). Placement itself used road + sidewalk + 1.5, disc + 1.5 and building
  + 2. It also kept clear of the Walking Street gate (+10), small OSM piers (+4) and the other teams' areas.
- The Beach Road promenade (OSM pedestrian way 1219262891) lies inside the widened game road and sidewalk (the road
  is 39 studs wide at ×0.5), so the lamps stand just outside the sidewalk, on the ground between it and the sand.
  The palms stand on the sidewalk.
- **48 chunks** `b<cx>_<cz>` (512-stud cells by prop position). The largest has 302 Parts (cap 600; no thinning
  needed). There are **6 batches** `b1`..`b6` of ≤ 8 chunks each, north to south.
- Night: the lamp heads are named `Lamp`, so `PattayaNightLights` makes them Neon after dark and puts their 91
  SpotLights in the shared lamp budget (nearest 60). The hut trim and board are `NightNeon` parts (`NightColor` =
  neon, `DayColor` = dimmed).
- LOD: `PattayaLOD` hides props only by name (`PalmTrunk`, `PalmFrond`, `NeonSign`, `SignFrame`). These props
  rely on instance streaming (Atomic chunks). Suggested one-line change for the LOD owner: add `UmbrellaCanopy`,
  `UmbrellaPole`, `Lounger`, `BoatHull`, `BoatBow`, `BoatEngine`, `BoatConsole`, `TowerFlag`, `TowerFlagPole`,
  `ParasailLine` to `PROP_NAMES`. Not done here (the file belongs to another team).

## 3. Horizon islands
The raw city downloads stop at lon 100.855, so they hold no island. A small Overpass fetch (above) returned three
closed coastline ways: **Ko Lan / Koh Larn (way 23484541), Ko Sak (26585171), Ko Krok (26585222)**. Each island is
cut into 420-stud strips north to south. One box per strip spans the island's x-extent, with its top at the 80th
percentile of the Terrarium elevation inside the strip. Where the peak is ≥ 1.25 × that, a narrower ridge box is
added. Heights use x0.5 / 0.28 m per stud (the horizontal compression, so the silhouette keeps its real
proportion). The boxes run from y = -6 to the top, with no terrain, no collision and no queries.

| island | parts | peak (DEM) | map-local bounds x / z |
|---|---|---|---|
| Ko Lan | 40 | 200.9 m → 359 studs | -21,484..-16,922 / 3..7,970 |
| Ko Sak | 4 | 28 m | -17,088..-15,994 / -1,657..-881 |
| Ko Krok | 5 | 30 m | -14,182..-13,711 / 1,368..2,350 |

**Risk, read before building:** the real position is 14–21k studs west of the beach, which is **world x
≈ -1,500..+6,300** (Ko Krok, the easternmost, at 5,800..6,300). Template content sits near the world origin and RaceMap at (6000, 100, 0). `BuildIsland()`
therefore checks every island box with `GetPartBoundsInBox` and **refuses to build** if any other part is inside
one. It lists up to 12 of them, and `BuildIsland({force = true})` builds anyway. The terrain sea ends at the wide
frame (map x -4,608), so the islands stand beyond the water's edge, seen through the haze. The model is Persistent,
because StreamingEnabled is on in the place.

## Budget
Props 5,993 + islands 49 = **6,042 Parts** (cap 8,000). Each chunk ≤ 302 Parts (cap 600) and each batch ≤ 8 chunks.

## Build steps for the leader
Save the place first (or rely on Team Create). The data goes in the same way as the other datasets: in
`tools/studio/install.ps1` add the line `$data += Entries 'build/coast/roblox' 'PattayaDataCoast'`. The builder
module is picked up automatically from `roblox/src/ServerStorage`.

```lua
local C = require(game.ServerStorage.PattayaCoastBuilder)
-- props, one batch per call (each well under 1 s expected; resumable, built chunks are skipped)
C.Build({batch = "b1"}) C.Build({batch = "b2"}) C.Build({batch = "b3"})
C.Build({batch = "b4"}) C.Build({batch = "b5"}) C.Build({batch = "b6"})
C.Probe()                       -- step 1 of the probe: 0 coast parts touching road/sidewalk/disc/building
```

**Terrain: a separate step. WARNING: terrain writes are slow and cannot be undone with Ctrl+Z in any useful way.**
Run one tile module per call. Each module is one ≤ 2048-stud tile (the builder `task.wait()`s every 250 runs and
after every module):
```lua
for i = 1, 26 do print(C.BuildTerrain({tile = i})) task.wait() end   -- 7,917 WriteVoxels runs in total
C.Probe()   -- landward edge unchanged at 240 sample cells; shoreline applied
-- undo: C.RemoveTerrain()   (writes the old states back; it also re-opens the seam row's sea cells)
-- OPTIONAL, owner's decision (moves the strip's landward edge):
-- for i = 1, 20 do print(C.BuildTerrain({tile = i, fill = true})) task.wait() end
```
Islands (after checking the message):
```lua
print(C.BuildIsland())   -- "island NOT built: ..." if template/RaceMap content is in the boxes
```

## Probe (Luau, command bar)
`C.Probe()` prints three lines. An equivalent standalone snippet:
```lua
local w, o = workspace.PattayaWorld, Vector3.new(20000, 0, 0)
local man = require(game.ServerStorage.PattayaDataCoast.manifest)
-- 1. coast parts vs Road / Sidewalk / Junction / Joint / building parts
local params = OverlapParams.new()
params.FilterType = Enum.RaycastFilterType.Include
params.FilterDescendantsInstances = {w.Chunks, w.WideChunks, w.Junctions, w.WideJunctions}
local n, bad = 0, 0
for _, d in w.CoastChunks:GetDescendants() do
	if d:IsA("BasePart") then
		n += 1
		for _, h in workspace:GetPartsInPart(d, params) do
			if h.Name == "Road" or h.Name == "Sidewalk" or h.Name == "Junction" or h.Name == "Joint" or h.Name == "Roof"
				or h:GetAttribute("OsmBuilding") then bad += 1 break end
		end
	end
end
print(n, "coast parts,", bad, "touching")                        -- expect 0 touching
-- 2. the sand strip's landward edge (last sand cell / first land cell) is unchanged at 240 sample points
local same = 0
for _, s in man.terrain.probe do
	local m = workspace.Terrain:ReadVoxels(Region3.new(o + Vector3.new(s[1] - 2, -8, s[2] - 2), o + Vector3.new(s[1] + 2, -4, s[2] + 2)), 4)
	if m[1][1][1] == Enum.Material[s[3]] then same += 1 end
end
print(same, "of", #man.terrain.probe, "edge cells unchanged")     -- expect 240 of 240
```
Run part 2 once **before** `BuildTerrain`, too. If it already reports mismatches there, the place's terrain differs
from the replay (another tool wrote terrain there). Look before writing.

## Open risks
- Nothing has run in Studio. The terrain replay assumes the place's terrain is exactly `Build()` + `Extend({roads =
  false})`. If anyone wrote terrain at the coast since (the landmarks team at Bali Hai or the Dolphin roundabout,
  or a later rebuild), the probe's "before" run shows it. WriteVoxels only touches the listed cells, but it does
  overwrite them.
- The seam trench (z -3776..-3772) on land stays for the PattayaBuilder owner.
- The islands may overlap template/RaceMap content (they are refused by default). Very distant parts may be culled
  at low graphics quality.
- Mud's colour is global. If anyone later uses Mud terrain, it will look like wet sand.
- The props are not LOD-hidden by name (see above). 5,993 Parts rely on streaming.
- Visual check needed: canopy height (8.6 studs), the lounger size, the hut without corner posts, and whether the
  4-stud water over sand reads as shallow at the place's `WaterTransparency`.

## Seam trench (leader, 2026-10-19, Studio)
The 4-stud Air row at z -3776..-3772 (wide ground ends at -3776, the base frame starts at -3772) was filled in
Studio: for x 14,000..30,000 in 512-stud regions, every seam column whose top was Air with land (not Water/Air) on
both the z-4 and z+4 sides got the z-4 column's voxels copied in (`ReadVoxels` → edit the arrays → `WriteVoxels`,
6 regions, 672 columns). Verification read-back: 0 land-neighboured Air columns left. The root cause (frame offset
between `Build()` ground and `Extend()` ground) is still in PattayaBuilder; a full rebuild would reopen it.
