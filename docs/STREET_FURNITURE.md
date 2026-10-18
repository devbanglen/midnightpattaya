# Street furniture layer (team4/furniture, 2026-10-19). Written, NOT built in Studio

This layer adds traffic lights, zebra crossings, bilingual road name signs, bus shelters, motorbike-taxi stands and
utility poles to the city (the central slice and the wide world), so that Pattaya reads as Pattaya at driving speed.
Every position comes from an OSM node or from a rule written below, measured from the road graph (centreline,
width and sidewalk).

**Status: written, NOT built in Studio.** The numbers below come from the exporter and its shapely checks. The
Luau builder has not been compiled or run, and nobody has looked at the result in Studio yet.

- Map data © OpenStreetMap contributors, ODbL 1.0. The attribution is in the manifest (`attribution`,
  `osmBase`, `graphOsmBase`), in every chunk header and on `workspace.PattayaWorld.FurnitureChunks`.
- Nothing has logos or brands. Signs show only plain text: real OSM road names, "BUS", "WIN" and "TAXI".
  Operator names and taxi company names from OSM are deliberately left out.

## Files (all new; no existing file was changed)
| file | what |
|---|---|
| `tools/mapgen/furniture.py` | the exporter, including its shapely checks and the check PNGs |
| `tools/mapgen/config/furniture.json` | rules, margins and budget |
| `data/osm/queries/pattaya_furniture.overpassql` | the Overpass query (bbox of the wide world, which contains the central slice) |
| `data/osm/raw/pattaya_furniture_2026-10-19.json` | 697 OSM elements, **OSM base 2026-10-18T18:23:36Z**, downloaded 2026-10-19 from overpass-api.de with curl.exe. Contents: 169 traffic_signals, 425 highway=crossing, 30 bus_stop, 38 amenity=taxi, 27 power towers. There are no `power=pole` nodes, so no soi has mapped poles |
| `roblox/src/ServerStorage/PattayaFurnitureBuilder.luau` | `.Build({only?, batch?, folder?})` and `.Remove()` |
| `docs/images/furniture_check_junction.png` | copy of the busiest-junction check crop (red masts, white bars, blue name signs, orange WIN stands, green existing lights) |
| output `build/furniture/` (gitignored, regenerated) | `roblox/manifest.luau`, `roblox/chunk_f<cx>_<cz>.luau` (267), `furniture.json` (every item with its OSM source / rule), `furniture_check.png` (central slice), `_1` (centre zoom), `_2` (busiest signalised junction) |

The existing gameplay outputs are not touched: no chunk, manifest, layout, export_roblox, gameplay_layout,
buildings, traffic or PattayaBuilder change. The chunk ids carry an `f` prefix, so they never collide with road
chunks (`<cx>_<cz>`) or corridor dressing (`d…`).

## Rules
All distances are in studs: map-local, x0.5 compression, 0.28 m per stud, the same `origin_utm` as
`build/central_pattaya/graph_game.json`. Builder position = map-local + ORIGIN (20000, 0, 0). Road top y = 1.0,
sidewalk top y = 1.6, ground y = -2.

- **Kerb margin.** No ground footprint (pole, post or pad) comes closer than **3 studs** beyond width/2 + sidewalk of
  any road: the wide world (including the central edges), plus the Bira corridor graph. The same 3 studs apply around
  every node disc. A node disc has radius max(width/2 + sidewalk) over the node's edges, which is wider than
  Studio's junction and joint discs.
  - Every other part (boards, roofs, crossarms, wires) also stays off every road slab, sidewalk and disc. The one
    exception is the signal arm and its head, which hang over the road by design (y ≥ 11.1).
  - Every part keeps 0.5 studs from every building box: central, wide, and the corridor dressing buildings.
  - Every part keeps 1.5 studs from every existing prop: city street lights (pole and arm), palms (r 3), neon signs,
    the corridor's lights, trees (r 7), palms, poles, wires, road signs and gantry, and the landmarks in
    `layout.json` (Walking Street gate, r = span/2 + 4).
  - Every part keeps 1 stud from all other furniture.
- **Traffic lights (6 Parts per mast).**
  1. Each OSM `highway=traffic_signals` node is snapped to the nearest junction (degree ≥ 3) within 45 studs.
  2. Signalised junction nodes within 50 studs of each other count as one junction (dual carriageways).
  3. Rule for junctions with no tagged signal: ≥ 3 incident `trunk/primary/secondary` edges, and no OSM signal
     within 120 studs.
  4. Each inbound approach gets one mast. One-way edges that leave the junction get none. The mast stands on the
     driver's **left** kerb, because Thailand drives on the left. It stands 4+ studs back from the node disc and
     3.6 studs outside the sidewalk, and slides back or out until it is clear.
  5. The arm reaches over the inbound lane (≤ 24 studs). The 3-lamp head faces the oncoming drivers.
  6. One lamp per mast is lit, alternating red and green by approach order around the junction. There is no
     signal logic. The lit lamp is Neon, with `NightNeon` / `DayColor` / `NightColor` for PattayaNightLights.
  7. OSM signals that are not near a junction are mid-block (pedestrian) signals. They get one mast per direction,
     placed before the crossing.
  - The existing street lights stand on the main-road sidewalks every `light_spacing_studs`. These masts are an
    extra row 3.6 studs behind the sidewalk, and they keep 1.5 studs from every street-light pole and arm, so the
    two never double up.
- **Zebra crossings (1 Part per bar).**
  - Sources:
    - OSM `highway=crossing` nodes, except `crossing=no/unmarked` and `crossing:markings=no`. Each is snapped to the
      nearest edge, within width/2 + 4.
    - One crossing per signalised approach where OSM has none within 25 studs. It goes at disc radius + 5 from the
      node.
    - One at each mid-block signal.
  - The crossing is kept clear of junction discs (it is pushed along the edge). Crossings on the same edge closer
    than 14 studs are merged.
  - Bars are 2 studs wide with 2-stud gaps, 6 studs long along the road. They are inset 1.2 studs from the slab
    edge, and each bar must lie inside the road slab.
  - Each bar is a flat Part: y 1.02–1.07 (0.05 thick), CanCollide = false, CanQuery = false, attribute
    `onRoad = true`. No bump, and it never catches the car's raycasts.
- **Road name signs (2 Parts).**
  - Placed at every junction (degree ≥ 3) with ≥ 2 distinct road names where at least one road is main or
    express tier.
  - One sign per name, skipped if the same name already has a sign within 60 studs (this suppresses repeats at
    dual-carriageway junctions).
  - The sign stands on that road's kerb near the junction, 3.6 studs outside the sidewalk, so it is off the
    sidewalk's walking line. The board is parallel to the road it names (like a soi sign seen from the main road)
    and has text on both faces.
  - The blue board shows the Thai OSM `name` on top and OSM `name:en` below, exactly as tagged. 719 signs have both,
    13 have Thai only and 10 have English only. Attributes `NameTh` / `NameEn` are set on the board.
- **Bus shelters (8 Parts).**
  - OSM `highway=bus_stop` / `public_transport=platform` nodes (bus stops within 20 studs of each other count
    once). Each is snapped to the nearest edge within 60 studs.
  - The shelter goes on the node's side of the road. A node on the carriageway goes on the a→b driver's left.
  - Parts: a 12 x 5 pad level with the sidewalk top, glass back wall, 2 posts, roof, bench, and a pole with a "BUS"
    sign. The sign also shows the stop's OSM name, but only when it is a Thai name (1 stop: วัดหนองใหญ่ (พัทยา)).
- **Taxi stands.**
  - Motorbike-taxi stands: OSM `amenity=taxi` with `motorcycle=yes` / `taxi_vehicle=motorcycle`, or
    `amenity=motorcycle_taxi`. Parts (7): canopy, 2 posts, rack with 2 orange vests (proxy), "WIN" sign.
  - Other `amenity=taxi` nodes: the same stand without the vests, signed "TAXI" (5 Parts).
- **Utility poles (2 Parts + 1 per wire).**
  - Placed along residential / unclassified sois ≥ 120 studs long that are not coastal. There is no OSM pole data
    and no existing city poles.
  - One pole every 90 studs on the a→b driver's left, 3.7 studs outside the sidewalk. Each pole has the corridor
    pole's look and a wire to the next pole of the same run, when that wire is clear of every road, building, prop
    and furniture item.
  - Sois are taken central slice first, then outward by distance, until the part target (9,600) is reached.
- **Budget.**
  - Total ≤ 10,000 Parts, each chunk ≤ 600 (asserted). Poles are thinned first, then name signs, in any chunk over
    the cap (nothing needed thinning).
  - Chunks are the 512-stud grid by item position.
  - Batches hold ≤ 8 chunks each, ordered by distance from the central slice's centre.

## Counts (current export)
| item | central (Parts) | wide (Parts) | total (Parts) | source |
|---|---|---|---|---|
| traffic-light masts | 81 (486) | 133 (798) | **214 (1,284)** | 154 OSM-junction, 41 OSM mid-block, 19 rule; 67 OSM + 10 rule junctions, 36 mid-block points |
| zebra crossings | 101 (928) | 401 (3,978) | **502 (4,906)** | 377 OSM, 118 signal-approach rule, 7 mid-block rule |
| road name signs | 245 (490) | 497 (994) | **742 (1,484)** | junction rule, OSM names |
| bus shelters | 7 (56) | 16 (128) | **23 (184)** | OSM |
| taxi stands | 12 (82) | 16 (104) | **28 (186)** | OSM: 23 WIN, 5 TAXI |
| utility poles | 258 (583) | 261 (619) | **519 (1,202)** | rule, 164 wires |
| **total** | **2,625** | **6,621** | **9,246** | |

- **Chunks:** 267 chunks, largest 246 Parts, largest module 3 KB. **34 batches** `f1` … `f34` (≤ 8 chunks each,
  52–608 Parts per batch).
- **Skipped, from the exporter stats:**
  - Traffic lights: 40 approaches got no clear mast spot (signal_mast_blocked), and 10 OSM signals were not near
    any road.
  - Crossings: 18 OSM crossings were off the built roads, 3 were skipped by tag, 27 were on edges too short to
    clear both discs, and 8 were merged.
  - Name signs: 65 had no clear spot, and 75 were suppressed as the same name nearby.
  - Bus and taxi: 5 bus stops and 7 taxi stands had no clear spot. 2 bus stops and 3 taxi nodes were more than 60
    studs from a road.
  - Poles: 449 pole spots were blocked (mostly buildings sitting exactly at the 3-stud kerb margin), and 61 wires
    were blocked. 925 soi edges were left without poles by the budget.
- **Export-time checks (all asserted = 0):**
  - non-crossing parts on a road slab, sidewalk or junction/joint disc (Studio discs from the manifests and the
    `joints` modules, plus the wider node discs)
  - ground parts inside the 3-stud kerb margin
  - parts inside building boxes
  - parts on existing lights, palms, signs or landmarks
  - furniture overlapping other furniture
  - crossing bars outside the road slab

  The crossing bars are 0.05 thick, top at y 1.07.
- **Rerun determinism:** a second run gives a byte-identical `build/furniture/`.

## Rerun after the road fix (one command)
Run this from the repo root after the team4/roadfix geometry lands and `graph_game.json`, `layout.json` and
`buildings_game.json` (and, if changed, the manifests and `joints.luau`) have been regenerated:
```
D:\ROBLOXRACE\.venv\Scripts\python.exe tools\mapgen\furniture.py tools\mapgen\config\furniture.json --build-root D:\ROBLOXRACE\build
```
It reads:
- `<build-root>/central_pattaya`: graph_game, layout, buildings_game, roblox/manifest
- `<build-root>/pattaya_wide`: the same, plus roblox/joints
- `<build-root>/bira`: corridor_graph_game, roblox_corridor manifest/joints/chunks
- `data/osm/raw/pattaya_furniture_2026-10-19.json`

It rewrites only `<build-root>/furniture/`. Without `--build-root` it uses `./build`. That is how this branch was
run, with copies of the leader's build outputs from 2026-10-19.

If the checks find a hit, the run fails with the counts. Every placement searches for a clear spot, so a new road
shape only moves or skips items. It never puts them on the road. New download (only if the area changes):
`curl.exe -A "MidnightPattaya-mapgen/1.0" --data-urlencode data@data/osm/queries/pattaya_furniture.overpassql https://overpass-api.de/api/interpreter -o data/osm/raw/pattaya_furniture_<date>.json`
(overpass-api.de returned 406 without a User-Agent). Then point `raw` in the config at the new file.

## Build steps for the leader (save the place first)
1. `ServerStorage.PattayaFurnitureBuilder` ← `roblox/src/ServerStorage/PattayaFurnitureBuilder.luau` (new ModuleScript).
2. Create the Folder `ServerStorage.PattayaDataFurniture`. Load `build/furniture/roblox/manifest.luau` and the 267
   `chunk_f*.luau` modules into it, using the same JSON-bundle / HttpListener method as the other data folders
   (0.44 MB in total).
3. Build in batches, one call each (built chunks are skipped, so a call can be repeated):
   ```lua
   local F = require(game.ServerStorage.PattayaFurnitureBuilder)
   print(F.Build({batch = "f1"}))   -- central slice first; then "f2" ... "f34" (manifest.batchOrder)
   ```
   Each call prints the chunks and Parts built. It warns if a chunk's Part count differs from the data's `parts`.
4. Run the probes below. Undo with `require(game.ServerStorage.PattayaFurnitureBuilder).Remove()`, which removes
   only `workspace.PattayaWorld.FurnitureChunks`.

**LOD (optional, a one-line change in another team's file, not made here).** `PattayaLOD.client.luau` hides props
by part name (`PROP_NAMES`). To hide the small furniture beyond `LOD_PropRange` as well, extend that table with
`SignalArm, SignalHead, SignalLamp, NameSignBoard, BusSign, TaxiSign, TaxiVest, TaxiCanopy, ShelterRoof, PoleArm,
PoleWire, ZebraStripe`. Without the change, the furniture simply stays visible (about 9k Parts, streamed per Atomic chunk).

## Probes (Command Bar, after step 3)
```lua
-- 1) no non-crossing furniture Part intersects a Road / Sidewalk / Junction / Joint Part; crossings are flat
local world = workspace.PattayaWorld
local roots = {}
for _, n in {"Chunks", "WideChunks", "Junctions", "WideJunctions"} do
	local f = world:FindFirstChild(n)
	if f then table.insert(roots, f) end
end
local op = OverlapParams.new()
op.FilterType = Enum.RaycastFilterType.Include
op.FilterDescendantsInstances = roots
local ROAD = {Road = true, Sidewalk = true, Junction = true, Joint = true}
local parts, bad, cross, badCross = 0, 0, 0, 0
for _, p in world.FurnitureChunks:GetDescendants() do
	if p:IsA("BasePart") then
		if p:GetAttribute("onRoad") then
			cross += 1
			if p.Size.Y > 0.1 or p.Position.Y + p.Size.Y / 2 > 1.1 or p.CanCollide or p.CanQuery then badCross += 1 end
		else
			parts += 1
			for _, q in workspace:GetPartsInPart(p, op) do
				if ROAD[q.Name] then
					bad += 1
					if bad <= 10 then print("HIT", p:GetFullName(), q:GetFullName()) end
					break
				end
			end
		end
	end
end
print(("furniture: %d parts, %d intersect road/sidewalk/disc; %d crossing bars, %d thicker than 0.1 / raised / solid"):format(parts, bad, cross, badCross))

-- 2) raycasts along every road part: between y 8 and 0 the only furniture on the slab is a crossing bar.
-- CanQuery is switched on for every furniture Part for the duration of the probe, then restored. Signal heads hang
-- higher (bottom y 11.1), so rays start at y 8.
local rp = RaycastParams.new()
rp.FilterType = Enum.RaycastFilterType.Include
rp.FilterDescendantsInstances = {world.FurnitureChunks}
local saved = {}
for _, p in world.FurnitureChunks:GetDescendants() do
	if p:IsA("BasePart") then saved[p] = p.CanQuery; p.CanQuery = true end
end
local rays, onCross, other = 0, 0, 0
for _, root in roots do
	for _, r in root:GetDescendants() do
		if r:IsA("BasePart") and (r.Name == "Road" or r.Name == "Junction" or r.Name == "Joint") then
			local pts = if r.Name == "Road" then {-0.4, 0, 0.4} else {0}
			for _, f in pts do
				local pos = if r.Name == "Road" then (r.CFrame * CFrame.new(0, 0, f * r.Size.Z)).Position else r.Position
				rays += 1
				local hit = workspace:Raycast(Vector3.new(pos.X, 8, pos.Z), Vector3.new(0, -8, 0), rp)
				if hit then
					if hit.Instance:GetAttribute("onRoad") then onCross += 1 else
						other += 1
						if other <= 10 then print("ON ROAD", hit.Instance:GetFullName(), hit.Position) end
					end
				end
			end
		end
	end
end
for p, v in saved do p.CanQuery = v end
print(("raycasts %d: %d on crossing bars, %d on other furniture (expected 0)"):format(rays, onCross, other))
```
Expected results: probe 1 reports 0 hits and 0 bad crossing bars, and probe 2 reports 0 on other furniture. The
junction/joint names follow `PattayaBuilder`: discs are named `Junction` / `Joint`, slabs `Road`, kerbs `Sidewalk`.

## Open risks
- **Road fix in flight.** The export uses the 2026-10-19 copies of the leader's build outputs. After team4/roadfix
  lands (joint discs, pulled-apart dual carriageways, slip-road trims), rerun the command above before importing. The
  3-stud margin and the asserted checks keep the old export safe against small shifts, but they cannot catch a slab
  moved by more than about 3 studs.
- **Thai glyphs.** The boards use `Enum.Font.GothamBold` and rely on Roblox's font fallback for Thai script. Not
  checked in Studio. If Thai renders as boxes, switch the label font to one with Thai coverage.
- **Tight frontages.** Buildings were cut back to exactly width/2 + sidewalk + 3 studs (`buildings.py`), the same
  line as this layer's margin. So in dense blocks furniture only fits in gaps, and many soi poles stand alone without
  wires.
- **Landmarks.** The landmark team's new proxies are not in `layout.json` yet. Rerun after they land, so their
  footprints become obstacles. Today only the Walking Street gate is known.
- **Mid-block signals and the rule junctions** are a stated reading of the OSM data and the rule, not a survey of
  real signal heads. Lamp colours are fixed per mast.
- **LOD.** See the optional PattayaLOD change above.
- **Not covered:** the Bira corridor east of Sukhumvit, which has its own dressing (its roads and props are
  obstacles here).
