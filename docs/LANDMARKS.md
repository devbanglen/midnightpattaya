# Landmarks: Pattaya landmark proxies (team4/landmarks, 2026-10-19; written, NOT built in Studio)

Nothing here has been built or seen in Studio. The numbers come from the exporter, its shapely checks and an
offline Luau mock run of the builder (it builds all 1,658 parts, sets every NightNeon attribute and SurfaceGui, and
runs RemoveReplaced / RestoreReplaced / Remove). Roblox itself has not run the code.

Twelve recognisable Pattaya landmarks, each a handcrafted low-poly Part model in a stylised RayCity-like look that
reads well at night. Each one stands on its **real OSM footprint**. Positions come from OSM only: every way and node
id is listed below, and nothing is placed by hand. The shapes are generic: plain colours, Parts only, and names as
plain text on a SurfaceGui (Gotham). Real place names are used descriptively, as the master plan allows. There are
no logos, no official artwork and no trademarked design. The marquee and board texts are the OSM names in capitals.

## Data and attribution
Map data © OpenStreetMap contributors, ODbL 1.0. The attribution is in the manifest (`attribution`), in every chunk
module header and on `workspace.PattayaWorld.LandmarkChunks` and each landmark Model (attribute `Attribution`).
All 12 landmarks were found in the raw files that were already in the repo, so we fetched no new Overpass data:

| raw file | OSM base |
|---|---|
| `data/osm/raw/central_pattaya_2026-10-18.json` | 2026-10-17T22:33:51Z |
| `data/osm/raw/pattaya_wide_north_2026-10-18.json` | 2026-10-18T10:38:06Z |
| `data/osm/raw/pattaya_wide_south_2026-10-18.json` | 2026-10-18T10:38:06Z |
| `data/osm/raw/pattaya_wide_east_2026-10-18.json` | 2026-10-18T10:40:06Z (read; no landmark in it) |

## Method (`tools/mapgen/landmarks.py`, config `tools/mapgen/config/landmarks.json`)
- **Projection:** the city's own: EPSG:32647, `origin_utm` from `build/central_pattaya/graph_game.json`, compression
  0.5, 0.28 m per stud (1 stud = 0.56 m real horizontally), z = -northing. World position = map-local + (20000, 0, 0).
- **Footprints:** every body starts from the OSM polygon's minimum rotated rectangle. It is then shrunk one side at a
  time until it is 3 studs clear of every obstacle: each road slab, sidewalk strip and junction / joint disc of the
  central AND wide datasets (rebuilt from the exported chunk modules exactly as `tools/mapgen/road_check.py` does,
  `swSide` included), each kept procedural building box (`buildings` rows of every chunk module), and each street prop
  (palms, street lights with their arm, neon signs, job stands, the Walking Street gate). The front (boards, marquee,
  entrance) faces the nearest road. If a kept building or a road cuts into an OSM footprint (Central Pattaya,
  Terminal 21), up to two extra wing boxes fill the leftover pieces under the same rule.
- **Heights:** OSM `building:levels` x 8.57 studs + 3, the `buildings.py` rule (vertical_scale 0.75 / 0.28 m per
  stud = 2.68 studs per real metre). Where OSM has no levels, the theatres keep the height of the procedural box
  they replace. Where OSM has no height at all, we use a public real-world height x 2.68 (Sanctuary of Truth
  105 m, Big Buddha 18 m) and say so in the config (`height_src`). The Pattaya Park Tower uses only OSM
  (`building:levels`, `building:min_level`, mast `height=240`).
- **Ground:** bases go down to y = -2.5 (terrain surface -2, road top 1.0, procedural buildings start at 0).
- **Export-time check (asserted):** the 2-D footprint of EVERY exported part is checked, buffered by 0.5 studs. That
  footprint is the projected oriented box, or a disc for vertical cylinders and balls. It must touch no road slab,
  sidewalk, junction / joint disc, street prop or kept building box. Result: **0 of 1,658**. A second, independent
  pass rebuilt each part from the exported module numbers (`fromEulerAnglesYXZ` angles) and found 0 again. The
  check is strict and fully 2-D: a part high above a road would also fail it, and none does.
- **Re-runs give byte-identical output.** The modules hold one row of 15 numbers per part (name, shape, size,
  map-local position, YXZ Euler angles, colour, material, flags, transparency) plus `neon` and `texts` lists.

## The landmarks
World position = map-local x + 20000, z. Check images (top-down over the road layout, north up; blue = OSM geometry,
red dashed = the procedural box the proxy replaces) are in `docs/images/landmarks/<id>.png`.

| id | landmark | OSM | chunk | world (x, z) | parts | neon | what it is |
|---|---|---|---|---|---|---|---|
| `sanctuary_of_truth` | Sanctuary of Truth (Naklua) | way 223698118 (building), way 765578335 (site) | `l4_-14` | (22203.1, -7087.4) | 89 | 13 | 121 x 148 stepped terrace, cross-shaped teak hall with stepped roofs and carved gables, 9-tier central prang to 281 studs (105 m), 4 side prangs, 4 corner pavilions, amber floodlit terrace edge |
| `big_buddha` | Big Buddha, Wat Phra Yai (Khao Phra Tamnak) | way 322626265 (temple area), way 36330868 (steps) | `l-4_8` | (18313.1, 4502.5) | 33 | 5 | octagonal marble plinth (r 25.5, 12 high) inside the temple area, seated gold figure 48 studs (18 m) facing down the stair; 9 stair steps along the OSM steps way, naga balustrades, name board at the foot |
| `pattaya_city_sign` | PATTAYA CITY hillside letters (Pratumnak) | node 11210117797; ways 1210031614 P, 1210031615 A, 1210031616 T, 1210031617 T, 1210031618 A, 1210031620 Y, 1210031619 A, 1210468401 "City" | `l-5_4` | (17472.0, 2272.2) | 37 | 29 | plain white block letters, one per OSM letter sculpture way (its width = the way's length, 10.8–14.2 studs), 17 high; "CITY" in smaller letters on its own way; white glow at night; reads left to right from the north-east (the city side) |
| `bali_hai_pier` | Bali Hai Pier | way 504916659 (pier area), way 1211023097 (pavilion roof), node 1199397671 (ferry terminal) | `l-4_3` | (18085.2, 1715.9) | 106 | 20 | deck (top y 1.0) covering 17,403 of the 23,354 sq-stud OSM pier in 8 oriented pieces (stem + arms), posts, rails, 15 lamps, red-roofed ferry pavilion on the OSM roof footprint, name gate at the land end |
| `dolphin_circle` | Dolphin Circle statue | way 385837306 (the roundabout) | `l3_-6` | (21920.6, -2779.2) | 23 | 2 | fountain basin + pedestal + three leaping dolphins (22 high) on the free part of the roundabout island (r 5.2: at x0.5 the ring road covers most of it), plaque |
| `central_pattaya` | Central Pattaya (mall, Beach Rd / Second Rd) | way 151000011 | `l2_0` | (21241.3, 508.3) | 51 | 41 | 6-level box (54.4) 168 x 297 + 2 five-level wings, glass bands that glow pale cyan at night, entrance canopy, roof board "CENTRAL PATTAYA"; cut clear of the Hilton Pattaya box 1226656044 that OSM puts on the mall |
| `terminal21` | Terminal 21 Pattaya (mall, North Pattaya Rd) | way 651015521 | `l4_-6` | (22347.9, -2588.4) | 23 | 9 | generic terminal-style 4-level box 79 x 492 with vaulted metal roof, glass curtain front, a generic control-tower element with a red beacon, wing 231 x 79; cut clear of the Grande Centre Point box 838813335 |
| `floating_market` | Pattaya Floating Market (Sukhumvit, south) | way 962535135 (site), way 153523488 (water), node 995956011 | `l11_26` | (25763.4, 13479.7) | 678 | 87 | thin water surface on the OSM water (33 strips, no collision), 83 Thai pavilions on the 83 OSM house footprints of the site (55 on stilts over the water), terracotta / red roofs with glowing ridges, entrance gate 60 studs from the OSM node |
| `jomtien_night_market` | Jomtien Night Market | way 307546385 | `l-1_17` | (19503.3, 8943.2) | 552 | 140 | 136 stalls (counter, coloured canopy, post, neon strip) in back-to-back rows on the free part of the market area, entrance arch "JOMTIEN NIGHT MARKET" facing the road |
| `pattaya_park_tower` | Pattaya Park Tower | node 4605338296; ways 311141625 (shaft, 51 levels), 445129636 (deck, levels 51–55), 445129828 (mast, min_level 57, height 240 m), 311141627 (24-level podium) | `l-6_11` | (17264.6, 6092.4) | 25 | 13 | podium 208.7, shaft to 440, octagonal glass deck 440–474 with boards, jump-deck platform under it, red-white mast to 643 with a red beacon, cyan light strips on the shaft |
| `tiffanys_show` | Tiffany's Show (Pattaya Sai Song) | way 279387367 | `l3_-5` | (21938.5, -2386.5) | 22 | 8 | theatre box 131 x 126 x 37.3, columned porch, marquee board with pink text and cyan neon frame, bulb strip, corner neon blades |
| `alcazar_show` | Alcazar Cabaret Show (Pattaya Sai Song) | way 153538106 | `l4_-3` | (22221.0, -1202.8) | 19 | 8 | same theatre pattern, gold / magenta scheme |
| | **total** | | 12 chunks | | **1,658** | 375 | budget 6,000 |

Candidates from the brief that we did not build: Pattaya Viewpoint (only a point in OSM, and the Pratumnak hilltop
already has the letters), Jomtien Beach sign (not in OSM), and the brand theme parks (skipped as the brief says).

**Flat-world note:** the city terrain is flat (y = -2). The Big Buddha, the letters and the tower stand at street
level instead of on their hills. That is the data: we did not add hills.

## Chunks and batches
`build/landmarks/roblox/`: `manifest.luau` (7.5 KB) and 12 `chunk_l<cx>_<cz>.luau` modules (largest `l11_26` at 48 KB,
then `l-1_17` at 38 KB, all the rest under 9 KB). The `l` prefix means the ids never collide with a city, wide,
corridor or dressing chunk. One chunk = one Atomic-streaming Model
`workspace.PattayaWorld.LandmarkChunks.Chunk_l<cx>_<cz>`, holding one Model per landmark (named by its id; attributes
`LandmarkName`, `Label`, `Source`, `Attribution`).

| batch | chunks |
|---|---|
| `l1` | `l-6_11` (tower), `l-5_4` (letters), `l-4_3` (pier), `l-4_8` (Big Buddha), `l-1_17` (night market), `l2_0` (Central), `l3_-6` (Dolphin Circle), `l3_-5` (Tiffany's) |
| `l2` | `l4_-14` (Sanctuary), `l4_-6` (Terminal 21), `l4_-3` (Alcazar), `l11_26` (floating market) |

## Procedural boxes the proxies replace (56)
Until they are removed, these boxes stand inside the proxies. `RemoveReplaced()` takes them out. It does not destroy
them: it moves them to `ServerStorage.PattayaLandmarksRemoved`, and `RestoreReplaced()` puts them back.

| landmark | folder | city chunk | OSM building ids |
|---|---|---|---|
| sanctuary_of_truth | WideChunks | `Chunk_4_-14` | 223698118 |
| bali_hai_pier | Chunks | `Chunk_-4_3` | 1211023097 (the pavilion roof) |
| central_pattaya | Chunks | `Chunk_2_0` | 151000011 |
| terminal21 | Chunks | `Chunk_4_-5` | 651015521 |
| tiffanys_show | Chunks | `Chunk_3_-5` | 279387367 |
| alcazar_show | Chunks | `Chunk_4_-3` | 153538106 |
| pattaya_park_tower | WideChunks | `Chunk_-6_11` | 311141625 (shaft), 445129636 (deck, today a 474-stud solid box), 311141627 (podium) |
| floating_market | WideChunks | `Chunk_10_26` | 1244062532–1244062551, 1244062553–1244062561, 1244062563–1244062568, 1244064359–1244064362 (39 boxes) |
| floating_market | WideChunks | `Chunk_11_26` | 1244062552, 1244064351, 1244064353, 1244064365–1244064369 (8 boxes) |

The 47 floating-market boxes are the market's OSM houses (the wide LOD merged the 83 house footprints into 47 boxes).
The pavilions rebuild all 83 from OSM. Inside the site area there are no buildings other than houses.
Kept on purpose: Hilton Pattaya 1226656044 (on Central), Grande Centre Point 838813335 (on Terminal 21), Pattaya Park
Building 108189506, and the temple roof 683341082 in Wat Phra Yai. The proxies are cut clear of all four.

## Leader build steps (save the place first)
1. `ServerStorage.PattayaLandmarksBuilder` ← `roblox/src/ServerStorage/PattayaLandmarksBuilder.luau` (new module;
   PattayaBuilder is not changed).
2. `ServerStorage.PattayaDataLandmarks` (new Folder) ← `manifest.luau` and the 12 `chunk_l*.luau` from
   `build/landmarks/roblox/`. Use the same JSON-bundle / HttpListener method as the other data folders; the whole
   folder is about 135 KB. `build/` is gitignored. On a fresh checkout, run
   `.venv\Scripts\python tools\mapgen\landmarks.py tools\mapgen\config\landmarks.json` first. It needs
   `build/central_pattaya` and `build/pattaya_wide` from the mapgen pipeline.
3. Chunks, one call per batch (each call skips chunks that already exist, so it can be repeated after an error):
   ```lua
   local L = require(game.ServerStorage.PattayaLandmarksBuilder)
   print(L.Build({batch = "l1"}))   -- 8 chunks, 849 parts
   print(L.Build({batch = "l2"}))   -- 4 chunks, 809 parts
   -- or explicit ids, at most 8: L.Build({only = {"l2_0", "l4_-6"}})
   ```
4. Look at them. Then take out the procedural boxes inside them:
   `print(L.RemoveReplaced())` (expected "removed 56 procedural boxes; 0 not found"; tall boxes take their Roof slab
   along). To do it per landmark: `L.RemoveReplaced({only = {"terminal21", "central_pattaya"}})`.
5. Run the probes below.
6. Undo: `L.Remove()` (landmarks) and `L.RestoreReplaced()` (boxes). `PattayaBuilder.Build()` rebuilds the whole
   `PattayaWorld` folder, which deletes `LandmarkChunks` too. After that, run step 3 again.

## Probes (Command Bar, after step 3 / 4)
`print(L.Probe())` runs probe 1. Here is the same code as a standalone snippet:
```lua
-- 1) no landmark part touches a road, sidewalk, junction or joint disc (expected: landmark parts 1658, touching 0)
local world = workspace.PattayaWorld
local roads = {}
for _, d in world:GetDescendants() do
	if d:IsA("BasePart") and (d.Name == "Road" or d.Name == "Sidewalk" or d.Name == "Junction" or d.Name == "Joint") then
		table.insert(roads, d) -- landmark chunks contain no parts with these names
	end
end
local params = OverlapParams.new()
params.FilterType = Enum.RaycastFilterType.Include
params.FilterDescendantsInstances = roads
local n, hits = 0, 0
for _, p in world.LandmarkChunks:GetDescendants() do
	if p:IsA("BasePart") then
		n += 1
		if #workspace:GetPartsInPart(p, params) > 0 then
			hits += 1
			warn("touches road:", p:GetFullName())
		end
	end
end
print(("landmark parts %d, touching road/sidewalk/disc %d"):format(n, hits))
```
```lua
-- 2) after RemoveReplaced: no landmark part inside a procedural building box (expected 0; before RemoveReplaced
--    expect hits on the 56 boxes listed above only)
local world = workspace.PattayaWorld
local boxes = {}
for _, folder in {world:FindFirstChild("Chunks"), world:FindFirstChild("WideChunks")} do
	if folder then
		for _, d in folder:GetDescendants() do
			if d:IsA("BasePart") and d:GetAttribute("OsmBuilding") then table.insert(boxes, d) end
		end
	end
end
local params = OverlapParams.new()
params.FilterType = Enum.RaycastFilterType.Include
params.FilterDescendantsInstances = boxes
local hits, ids = 0, {}
for _, p in world.LandmarkChunks:GetDescendants() do
	if p:IsA("BasePart") then
		for _, b in workspace:GetPartsInPart(p, params) do
			hits += 1
			ids[b:GetAttribute("OsmBuilding")] = true
		end
	end
end
local list = {}
for id in ids do table.insert(list, tostring(id)) end
print(("landmark/box contacts %d, boxes: %s"):format(hits, table.concat(list, ", ")))
```
Offline, every landmark part is at least 0.5 studs from road geometry (most parts 3 studs; the Big Buddha stair, the
floating-market pavilions and the Dolphin Circle statue 1.5), so probe 1 should report 0. `GetPartsInPart` uses the real part geometry, so a wedge or ball counts as its
shape, not its bounding box.

## Night and LOD
- 375 parts carry `NightNeon = true` with `DayColor` / `NightColor`: board frames, marquee bulbs, glass bands,
  window bands, the letters, ridge lines, lamps and beacons. `PattayaNightLights` turns them Neon after dark and back
  to SmoothPlastic by day. These parts are always SmoothPlastic, because the client sets that material by day.
- The 136 night-market stall strips are named `NeonSign`, so `PattayaLOD` fades them beyond `LOD_PropRange` (900)
  like the city's neon signs. No other landmark part is faded: they are meant to be seen from far away, and the
  1,658 Parts are spread over 12 places. Board text uses SurfaceGuis with `LightInfluence = 0` (readable at night,
  13 boards).
- No Lights instances are added (no SpotLight budget used).

## Files
- `tools/mapgen/landmarks.py`: generator, fitting, checks, export, check images. It imports `road_check.py`
  read-only and does not modify it.
- `tools/mapgen/config/landmarks.json`: the landmark list, OSM ids, labels, height sources.
- `roblox/src/ServerStorage/PattayaLandmarksBuilder.luau`: `Build`, `RemoveReplaced`, `RestoreReplaced`, `Probe`,
  `Remove`.
- `build/landmarks/` (gitignored): `roblox/manifest.luau`, `roblox/chunk_l*.luau`, `landmarks.json` (summary with
  every part count by name, sizes, replaced boxes), `check/*.png`. The check images are also committed in
  `docs/images/landmarks/`.

## Open risks / not done
- Nothing has been built or seen in Studio. Proportions, colours and the neon amount need an eye pass. Likely
  candidates: the Big Buddha figure (box anatomy), the dolphins (small, r 5.2 island), and the tower mast height:
  OSM `height=240` m gives 643 studs, which is taller than the real 170 m look.
- The checks use the current road and building data of `build/central_pattaya` and `build/pattaya_wide`. If the
  roads team changes slab widths, sidewalks or discs, or the beach / street-furniture teams add parts near these
  sites, rerun `landmarks.py`: the assert fails if anything now overlaps. The Bali Hai Pier is on the coast, so
  check it against the beach/coast team's work.
- The Bali Hai Pier is 578 studs from the nearest road in our graph. The road onto the real pier is not in the road
  data, so the pier is a stand-alone deck you can see but not drive to. Its land end is 28.5 studs from the nearest
  building.
- The Dolphin Circle statue is small because at x0.5 the roundabout's ring road covers almost the whole island.
- The theatre heights (37.3) are the procedural default for an untagged building: OSM has no levels for them.
- The Sanctuary of Truth and Big Buddha heights are public reference values, not OSM tags. The config says so.
- If a procedural chunk is rebuilt after `RemoveReplaced`, its boxes come back and stand inside the proxies again:
  run `RemoveReplaced()` again (it reports "not found" for boxes that are already gone).
