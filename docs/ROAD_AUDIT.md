# Road audit and road fix (team4/roadfix, 2026-10-19)

Owner's report: "Some roads in the city cross each other chaotically and some overlap ... go through all the roads
on the whole map and make them smooth." (The Walking Street gate is handled separately by the leader.)

Status: **data built and checked offline, NOT built in Studio yet.** Every number below comes from running the tools
on the current build data (copied from `D:\ROBLOXRACE\build`, i.e. what the leader imported, corridor dressing
included). Map data (c) OpenStreetMap contributors, ODbL 1.0.

## Tools
- `tools/mapgen/road_audit.py [--root <repo>] [--out <dir>]` - audits the EXPORTED road surface of the whole world:
  central slice (`build/central_pattaya/roblox`), wide world (`build/pattaya_wide/roblox`) and corridor
  (`build/bira/roblox_corridor`), 3,818 edges. Slabs = exported polyline buffered by width/2 exactly as
  PattayaBuilder builds them; OSM bridge/tunnel/layer/oneway/highway tags from `data/osm/raw`. Writes
  `findings.json`, `findings.csv`, `summary.json` and `overview.png` (worst 30 numbered). World coordinates
  = map-local + ORIGIN (20000, 0, 0), i.e. the Studio frame. Classes and rules: see the module docstring.
- `tools/mapgen/road_fix.py [--dry-run]` - the fix pass (below). Runs after `export_roblox.py` (central, wide) and
  `export_corridor.py`; deterministic (a second run from the same exports gave byte-identical modules) and refuses to
  run twice on modules it already rewrote. Writes `build/road_fix/changes.json` (copy: `docs/road_audit/road_fix_changes.json`).
- `tools/mapgen/road_check.py` now reads the new `jA`/`jB` fields (sidewalk trims at bends).
- Reports: `docs/road_audit/findings_before.csv` / `findings_after.csv`, `summary_*.json`,
  `docs/images/road_audit_before.png` / `road_audit_after.png`.
- Backups of the modules before the fix: `build/central_pattaya/roblox_prev`, `build/pattaya_wide/roblox_prev`,
  `build/bira/roblox_corridor_prev` (worktree D:\ROBLOXRACE-worldfix).

## What the audit found (before the fix)
| class | central | wide | corridor | cross-set | total | visible* |
|---|---|---|---|---|---|---|
| crossing (centrelines cross, no shared node) | 0 | 0 | 0 | 0 | **0** | 0 |
| tee (road end pokes into another road, no node) | 27 | 259 | 0 | 7 | 293 | 15 |
| parallel (slabs overlap along a stretch) | 27 | 648 | 5 | 4 | 684 | 206 |
| acute (merge < 60 deg, slabs overlap > 6 studs past the disc) | 38 | 202 | 0 | 0 | 240 | 48 |
| short (< 15 studs between two junction discs) | 4 | 36 | 0 | 0 | 40 | - |
| kink (> 60 deg: 6 inside an edge, 302 at degree-2 joints) | 41 | 264 | 2 | 1 | 308 | - |
| step (end points at a node > 0.05 studs apart) | 0 | 0 | 0 | 0 | 0 | - |

\* visible = marking Parts of one road lie on the other, or more than 10 studs² of one road's raised sidewalk lies on
the other. Otherwise the two slabs only share one flat surface (same height, same colour), which reads as one wider
road.

Key facts:
- **No crossing without a junction anywhere.** Graph nodes are shared OSM nodes; no two centrelines cross elsewhere.
  The 13 game edges tagged bridge/tunnel/layer (7 wide + 3 corridor at level 1, 2 wide + 1 central at -1, 1 wide at 2)
  cross nothing (canal bridges etc.), so nothing needs raising. No seam steps.
- What showed was, per dataset:

| visible conflicts | central | wide | corridor |
|---|---|---|---|
| marking Parts on another road (same/higher class) or a foreign disc | 173 | 1,267 | 14 |
| ... of which on another road slab | 163 | 1,154 | 14 |
| sidewalk sides lying > 10 studs² on another road | **116** | 1 | 0 |
| sidewalk area on other roads (studs²) | **44,217** | 109 | 3 |
| bends > 35 deg with no full-width disc (interior vertex / degree-2 joint) | 11 / 44 | 74 / 9 | 0 / 0 |
| centreline probes every 25 studs (road_check): sidewalk / hairline / none | 96 / 109 / 1 | 3 / 1 / 0 (wide+corridor) | |

  The central slice never had the wide world's sidewalk rule nor joint discs: 116 raised kerbs (0.6 studs) lie on
  other roads (Pattaya Nuea, Pattaya Tai, Second Road area, Beach Road end) - the bumps you crash into - and its
  degree-2 bends (e.g. Beach Road -> Pattaya Tai at the Walking Street end, world (19468, 1891)) had bare wedges.
  In the wide world the visible part is markings: dual carriageways squeezed together at x0.5 (Thep Prasit /
  Thepprasit, Sukhumvit, Thepprasit west, Jomtien Second, Thappraya) draw their lane dashes across each other.

### Worst 30 (before), ranked by visible surface; status after the fix
Score = rough studs² of bad surface (x0.2 when nothing on it is visible). Numbers match `overview.png`.

| # | class | world x, z | chunk | dataset | roads | visible before (marks / kerb studs²) | after |
|---|---|---|---|---|---|---|---|
| 1 | parallel | 44521, 3048 | 47_5 | corridor | Thammasat Road / Thammasat Road | 5 / 0 — two edges leave node 1077826607 31 deg apart and overlap 1575 studs (dual carriageway split) | hidden |
| 2 | parallel | 41984, 3716 | 42_7 | corridor | Thammasat Road / Thammasat Road | 9 / 0 — two edges leave node 1077826539 4 deg apart and overlap 1298 studs (dual carriageway split) | hidden |
| 3 | parallel | 26029, 15256 | 11_29 | wide | Sukhumvit Road / Sukhumvit Road | 34 / 0 — slabs overlap 296 studs, centreline gap 21.7 < 78.0 | hidden |
| 4 | parallel | 22544, 5538 | 4_10 | wide | Thep Prasit Road / Thepprasit Road | 31 / 0 — slabs overlap 343 studs, centreline gap 13.9 < 58.5 | hidden |
| 5 | parallel | 25600, 14247 | 10_27 | wide | Sukhumvit Road / Sukhumvit Road | 33 / 0 — slabs overlap 515 studs, centreline gap 39.0 < 65.0 | hidden |
| 6 | parallel | 21804, 5646 | 3_11 | wide | Thep Prasit Road / Thepprasit Road | 35 / 0 — slabs overlap 294 studs, centreline gap 14.3 < 58.5 | hidden |
| 7 | parallel | 26029, 15256 | 11_29 | wide | Sukhumvit Road / Sukhumvit Road | 18 / 0 — slabs overlap 296 studs, centreline gap 34.8 < 78.0 | hidden |
| 8 | parallel | 26198, -5509 | 12_-11 | wide | Sukhumvit Road / Sukhumvit Road | 29 / 0 — slabs overlap 603 studs, centreline gap 24.5 < 45.5 | hidden |
| 9 | parallel | 25940, 15126 | 11_29 | wide | Sukhumvit Road / Sukhumvit Road | 15 / 0 — two edges leave node 13102994172 16 deg apart and overlap 306 studs (dual carriageway split) | hidden |
| 10 | parallel | 19050, 6320 | -2_12 | wide | Thepprasit Road / Thepprasit Road | 36 / 0 — slabs overlap 444 studs, centreline gap 11.9 < 39.0 | hidden |
| 11 | parallel | 23303, 5485 | 6_10 | wide | Thepprasit Road / Thep Prasit Road | 23 / 0 — slabs overlap 281 studs, centreline gap 16.1 < 58.5 | hidden |
| 12 | parallel | 22254, 5564 | 4_10 | wide | Thep Prasit Road / Thepprasit Road | 24 / 0 — slabs overlap 235 studs, centreline gap 14.3 < 58.5 | hidden |
| 13 | parallel | 25914, 14975 | 11_29 | wide | Sukhumvit Road / Sukhumvit Road | 27 / 0 — slabs overlap 311 studs, centreline gap 33.8 < 65.0 | hidden |
| 14 | parallel | 18656, 6407 | -3_12 | wide | Thepprasit Road / Thepprasit Road | 20 / 0 — slabs overlap 364 studs, centreline gap 13.5 < 39.0 | hidden |
| 15 | parallel | 22041, 5590 | 3_10 | wide | Thep Prasit Road / Thepprasit Road | 23 / 0 — slabs overlap 194 studs, centreline gap 13.8 < 58.5 | hidden |
| 16 | parallel | 22820, 5520 | 5_10 | wide | Thep Prasit Road / Thepprasit Road | 12 / 0 — slabs overlap 213 studs, centreline gap 13.3 < 58.5 | hidden |
| 17 | parallel | 20735, 5885 | 1_11 | wide | Thepprasit Road / Thepprasit Road | 14 / 0 — slabs overlap 351 studs, centreline gap 16.3 < 39.0 | hidden |
| 18 | parallel | 22216, -2762 | 4_-6 | central | Pattaya Nuea Road / Pattaya Nuea Road | 41 / 4533.9 — slabs overlap 454 studs, centreline gap 22.5 < 39.0 | hidden |
| 19 | parallel | 21313, 5733 | 2_11 | wide | Thepprasit Road / Thep Prasit Road | 15 / 0 — slabs overlap 153 studs, centreline gap 14.0 < 58.5 | hidden |
| 20 | parallel | 23482, 5492 | 6_10 | wide | Thep Prasit Road / Thepprasit Road | 10 / 0 — slabs overlap 185 studs, centreline gap 16.9 < 58.5 | hidden |
| 21 | parallel | 26062, 15292 | 11_29 | wide | Sukhumvit Road / Sukhumvit Road | 11 / 0 — slabs overlap 139 studs, centreline gap 16.5 < 65.0 | hidden |
| 22 | parallel | 21468, 5722 | 2_11 | wide | Thep Prasit Road / Thepprasit Road | 15 / 0 — slabs overlap 155 studs, centreline gap 15.3 < 58.5 | hidden |
| 23 | parallel | 25741, 14582 | 11_28 | wide | Sukhumvit Road / Sukhumvit Road | 14 / 0 — slabs overlap 212 studs, centreline gap 33.3 < 65.0 | hidden |
| 24 | parallel | 20280, 8997 | 0_17 | wide | Jomtien Second Road / Jomtien Second Road | 3 / 0 — slabs overlap 516 studs, centreline gap 20.9 < 32.5 | hidden |
| 25 | parallel | 21738, 2993 | 3_5 | central | Pattaya Tai Road / Pattaya Tai Road | 30 / 1711.5 — two edges leave node 12803794105 35 deg apart and overlap 232 studs (dual carriageway split) | hidden |
| 26 | parallel | 25120, 13140 | 10_25 | wide | Sukhumvit Road / Sukhumvit Road | 1 / 0 — slabs overlap 617 studs, centreline gap 43.3 < 52.0 | hidden |
| 27 | parallel | 25817, 14756 | 11_28 | wide | Sukhumvit Road / Sukhumvit Road | 15 / 0 — slabs overlap 170 studs, centreline gap 32.6 < 65.0 | hidden |
| 28 | parallel | 26091, 15454 | 11_30 | wide | Sukhumvit Road / Sukhumvit Road | 8 / 0 — slabs overlap 120 studs, centreline gap 22.5 < 78.0 | hidden |
| 29 | parallel | 20386, 5986 | 0_11 | wide | Thepprasit Road / Thepprasit Road | 12 / 0 — slabs overlap 253 studs, centreline gap 17.2 < 39.0 | hidden |
| 30 | parallel | 21603, 5694 | 3_11 | wide | Thep Prasit Road / Thepprasit Road | 6 / 0 — slabs overlap 121 studs, centreline gap 14.0 < 58.5 | hidden |

Rank 18 (Pattaya Nuea Road, central, 41 marks + 4,534 studs² of kerb on the other carriageway) and 25 (Pattaya Tai
Road at node 12803794105, 30 marks + 1,712 studs² kerb) are the worst spots inside the city.

## Fix rules (tools/mapgen/road_fix.py)
All fixes touch only the road lines of chunk modules (and the joints modules). `graph_game.json` is not changed, so
the runtime graph (node and edge indices and polylines), jobs, Road Fight, traffic, layout, buildings and manifests
are byte-identical (checked with `diff -rq`: only `chunk_*` files, the wide `joints.luau` and the new central
`joints.luau` differ). An edge that needs no fix keeps its line byte for byte.
- **K kinks**: interior polyline vertices turning > 35 deg get a quadratic fillet (cut <= 6 studs and <= 45 % of the
  shorter neighbour segment; edge end points never move). 63 edges.
- **B bends** (coordinator request): every degree-2 joint turning > 20 deg (374) gets a joint disc of the WIDER road's
  half-width (fills the open outer wedge, whose corners are at width/2 from the node; 19 existing wide discs widened,
  129 new central joint discs incl. straight joints), and both edge ends get `jA`/`jB` = (other width/2) x
  tan(turn/2) (<= 60): markings and sidewalks stop there like at a junction disc, so the inner kerb no longer runs into
  the other road (106 edge lines; sois without markings or sidewalks are not rewritten). Slab ends are NOT mitred:
  the inner overlap triangle is the same flat colour as the disc; cutting the slab back would open a gap the disc
  cannot cover.
- **S kerbs**: a sidewalk side is dropped when it lies on > 10 studs² of another road or foreign disc (the worldfix
  rule, now applied to all three datasets together and after the bend trims). 111 sides (central 98 edges, wide 1).
- **M marks**: markings are not drawn where they would lie on another road of the same or a higher class or on a disc
  not on this edge: new chunk field `noMarks = {s0, s1, ...}` (arc ranges). 362 edges. A dual carriageway that
  overlaps then reads as one unmarked boulevard; one-way semantics and two slabs stay (traffic unchanged).

Left out (deliberately):
- Moving centrelines apart / merging dual carriageways into one slab. The Thep Prasit pair needs 58.5 studs between
  centrelines and has 14; pulling them apart by ~45 studs (Sukhumvit: up to 56) would move traffic lanes, GPS lines,
  job-stand kerbs, props and buildings of the tested slice and the graph polylines. The slabs therefore still overlap
  geometrically (the leader's Studio slab-overlap probe will still count them) but nothing shows on the overlap.
- Junction nodes at crossings (there are none), raised bridges (no bridge crosses anything).
- Short edges (40): overlapping discs of the same colour; no visible effect, nothing to fix.
- Joint kinks themselves (real 90-150 deg corners of sois) keep their shape; they are now covered by bend discs.

## After the fix
| class | total | visible before | visible after |
|---|---|---|---|
| crossing | 0 | 0 | 0 |
| tee | 293 | 15 | **0** |
| parallel | 684 | 206 | **0** |
| acute | 240 | 48 | **0** |
| short | 40 | - | - |
| kink (60 deg) | 308 -> 300 (inside 6 -> 0) | - | - |

| visible conflicts after | central | wide | corridor |
|---|---|---|---|
| marking Parts on another road / disc | 0 | 0 | 0 |
| sidewalk sides > 10 studs² on another road | 0 | 0 | 0 |
| sidewalk area on other roads (studs², all under 10 per side) | 86 | 49 | 0 |
| bends > 35 deg without full-width disc | 0 | 0 | 0 |
| road_check probes: sidewalk / hairline / none | 0 / 8 / 1 | 0 / 1 / 0 | |

(The 8 central hairlines and the 1 "none" are at the slice border where the wide world's discs cover them; the
central-only check does not load the wide data.)

### Cross-check with the leader's Studio probes
Slab-overlap probe (92 pairs): every listed spot that has an audit finding within 40 studs is now hidden (no marks,
no kerb on it): Thep Prasit x Thepprasit (44 findings in the box, 16 visible with 239 marking Parts -> 0 visible),
Sukhumvit x trunk_link (8_1, 9_0), Thappraya x residential, Jomtien Second x trunk_link, Porn Prapa Nimit, Chalerm-
phrakiat x secondary_link, Chalermphrakiat 5, Phet Trakun (was 567 studs² of kerb), Sukhumvit x residential,
Jomtien Second x tertiary/secondary_link, Sukhumvit 14/1, Soi Thappraya 3, Thap Phraya. The geometric overlap
itself stays (see "Left out"), so the slab-overlap probe will report about the same 92 pairs. Spots Chalermphrakiat 7,
Pattaya Nua Soi 6, Chalermphrakiat 12x14, Soi Baku are degree-2 bends (now bend discs); Khopai Soi 4 and Jomtien
Second x residential are acute merges 40 studs from the listed point (hidden).
Kink probe (345 places > 35 deg without a disc): the offline replica finds 138 (central 55 = 11 interior + 44 joints,
the leader counted 57; wide 83 = 74 + 9, the leader counted 288 - the Studio probe also counts Road parts meeting end
to end that are not graph neighbours or that are stretched segments, which the replica cannot see). After the fix the
replica finds 0: interior bends are filleted below 35 deg and every degree-2 bend over 20 deg has a disc of the wider
half-width. Please re-run the Studio kink probe; anything left will be one of the cases the replica misses.

## Changed modules and chunk ids
- `ServerStorage.PattayaBuilder` <- `roblox/src/ServerStorage/PattayaBuilder.luau` (noMarks, jA/jB, base joints in
  `Build()`, joint discs resized when their radius changed, new `RebuildChunks`; everything else unchanged).
- `PattayaData` (central): 49 chunk modules + NEW module `joints` (129 discs). Manifest unchanged.
  ```
  "-3_4","-3_5","-3_6","-2_4","-2_5","-2_6","-1_3","-1_4","-1_5","-1_6","0_3","0_4","0_5","1_3","1_4","1_5","2_-6","2_-5","2_-1","2_2","2_3","2_4","2_5","3_-6","3_-5","3_-1","3_0","3_1","3_2","3_3","3_5","3_6","4_-6","4_-1","4_0","4_1","4_2","4_3","4_4","4_5","5_-6","5_-3","5_-2","5_-1","5_0","5_1","5_2","5_3","5_4"
  ```
- `PattayaDataWide`: 130 chunk modules + `joints` (19 radii widened). Manifest, graph, graph_part_*, jobs,
  roadfight, traffic, worldmap unchanged.
  ```
  "-7_8","-6_8","-5_13","-4_7","-4_12","-4_13","-3_6","-3_7","-3_8","-3_9","-3_12","-3_13","-3_14","-2_6","-2_11","-2_12","-2_14","-2_15","-1_6","-1_10","-1_11","-1_12","-1_15","-1_16","0_7","0_11","0_17","1_11","1_15","1_18","2_6","2_8","2_10","2_11","3_6","3_7","3_8","3_10","3_11","3_12","3_23","4_-12","4_7","4_8","4_10","4_18","4_20","4_22","5_-13","5_-8","5_-6","5_10","5_22","6_-9","6_-6","6_-1","6_1","6_3","6_7","6_8","6_10","6_27","7_-10","7_-9","7_-6","7_-5","7_4","7_5","7_6","7_7","7_8","7_10","7_11","7_12","7_13","7_16","7_18","7_23","7_25","7_29","8_-11","8_-10","8_-9","8_-8","8_-7","8_1","8_2","8_3","8_4","8_21","9_-14","9_-8","9_-7","9_-6","9_-5","9_-1","9_0","9_24","9_25","9_27","9_28","10_-15","10_-14","10_-6","10_-5","10_-4","10_25","10_27","11_-16","11_-11","11_-9","11_-8","11_-7","11_28","11_29","11_30","12_-14","12_-13","12_-12","12_-11","12_30","13_-16","13_-15","13_-14","14_-17","14_-16","15_-18","15_-17","16_-19","16_-18"
  ```
- `PattayaDataCorridor`: 7 road chunk modules (no dressing chunk, manifest/joints/traffic unchanged):
  `"40_4","42_7","44_6","46_7","47_5","48_5","48_6"`
- Largest road part count per chunk (slabs + sidewalks) after the fix: central 278 (was 270), wide 177; markings
  are fewer (362 edges lose some).

## Rebuild steps for the leader (Studio)
Save the place first (or Team Create). Build in groups of 8 chunks, as before. Data comes from
`D:\ROBLOXRACE-worldfix\build\...\roblox` (or main's build/ after a merge + rerun of `road_fix.py`).
1. Replace `ServerStorage.PattayaBuilder` with the new source; require a `:Clone()` of it in the command bar.
2. Replace the modules listed above as NEW ModuleScript instances (so `require` is not served from the cache):
   49 central chunks + add `PattayaData.joints`; 130 wide chunks + replace `PattayaDataWide.joints`; 7 corridor
   chunks. Nothing else.
3. Central: `B.RebuildChunks({<8 ids>})` x 7 (the 49 ids above). Each call replaces those `PattayaWorld.Chunks`
   models only (roads, buildings, props of the chunk; landmarks, race, terrain, junction discs untouched), keeps the 8
   removed seam buildings out, and adds the 129 central joint discs to `PattayaWorld.Junctions` (first call).
4. Wide: `B.RebuildChunks({<8 ids>}, {folder = "PattayaDataWide"})` x 17 (= delete `WideChunks.Chunk_<id>` +
   `Extend({terrain = false, only = ids})`); the first call also resizes the 19 widened joint discs.
5. Corridor: `B.RebuildChunks({"40_4","42_7","44_6","46_7","47_5","48_5","48_6"}, {folder = "PattayaDataCorridor"})`.
6. Run the probe below; then the leader's own slab-overlap and kink probes.
Undo: put the `_prev` modules back and run the same RebuildChunks calls (base joint discs: delete the `Joint` parts
in `PattayaWorld.Junctions`).

### Probe (command bar, read-only)
```lua
-- road fix probe: (1) marking Parts lying on another road of the same or a higher class, (2) centreline raycasts
-- every 25 studs along every Road part: road / sidewalk (raised kerb on a road) / nothing; (3) disc counts
local W = workspace.PattayaWorld
local RANK = {express = 0, main = 1, soi = 2}
local folders = {W:FindFirstChild("Chunks"), W:FindFirstChild("WideChunks")}
local op = OverlapParams.new()
op.FilterType = Enum.RaycastFilterType.Include
op.FilterDescendantsInstances = {W}
local rp = RaycastParams.new()
rp.FilterType = Enum.RaycastFilterType.Include
rp.FilterDescendantsInstances = {W}
local marks, marksBad, rays, kerb, none, n = 0, 0, 0, 0, 0, 0
local badList, kerbList = {}, {}
for _, f in folders do
	if not f then continue end
	for _, chunk in f:GetChildren() do
		for _, edge in chunk:GetChildren() do
			local id = edge:GetAttribute("EdgeId")
			if not id then continue end
			local rank = RANK[edge:GetAttribute("Tier")] or 2
			for _, p in edge:GetChildren() do
				if not p:IsA("BasePart") then continue end
				if p.Name == "Dash" or p.Name == "Centre" then
					marks += 1
					local q = Vector3.new(p.Position.X, 0.5, p.Position.Z)
					for _, r in workspace:GetPartBoundsInRadius(q, 0.05, op) do
						local m = r.Parent
						if r.Name == "Road" and m and m:GetAttribute("EdgeId") ~= id and (RANK[m:GetAttribute("Tier")] or 2) <= rank then
							local lp = r.CFrame:PointToObjectSpace(q)
							if math.abs(lp.X) < r.Size.X / 2 - 0.3 and math.abs(lp.Z) < r.Size.Z / 2 - 0.3 then
								marksBad += 1
								if #badList < 15 then table.insert(badList, ("%s on %s at (%.0f, %.0f)"):format(edge.Name, m.Name, q.X, q.Z)) end
								break
							end
						end
					end
				elseif p.Name == "Road" then
					for t = -p.Size.Z / 2, p.Size.Z / 2, 25 do
						local c = p.CFrame * Vector3.new(0, 0, t)
						local hit = workspace:Raycast(Vector3.new(c.X, 30, c.Z), Vector3.new(0, -60, 0), rp)
						rays += 1
						if not hit then
							none += 1
						elseif hit.Instance.Name == "Sidewalk" then
							kerb += 1
							if #kerbList < 15 then table.insert(kerbList, ("%s at (%.0f, %.0f)"):format(edge.Name, c.X, c.Z)) end
						end
					end
				end
			end
			n += 1
			if n % 300 == 0 then task.wait() end
		end
	end
end
local joints = 0
for _, p in W.Junctions:GetChildren() do if p.Name == "Joint" then joints += 1 end end
print(("marking parts %d, on another road %d; road rays %d, on a sidewalk %d, nothing %d; base joint discs %d, WideJunctions %d")
	:format(marks, marksBad, rays, kerb, none, joints, W:FindFirstChild("WideJunctions") and #W.WideJunctions:GetChildren() or 0))
print("marks on other roads:", table.concat(badList, "; "))
print("kerbs on roads:", table.concat(kerbList, "; "))
```
Expected after the rebuild: marking parts on another road 0 (offline: 1,331 before, of which central 163, wide 1,154,
corridor 14; a few may remain at degree-2 continuations, which the offline count excludes); rays on a sidewalk close
to 0 (sidewalks can be hit legitimately where a ray at the very end of a Road part lands on the junction kerb next to
it - compare with a run before the rebuild); base joint discs 129; WideJunctions 2,500 + 0 (discs are resized, not
added). Running the probe once BEFORE step 3 gives the Studio "before" numbers.

## Open risks
- Builder changes were not run in Studio (no Luau analyser here); review the Script Analysis output after step 1.
- `RebuildChunks` for the base slice rebuilds buildings/props of those 49 chunks from the modules: manual Studio edits
  inside those chunk models (if any) would be lost.
- The geometric dual-carriageway overlaps remain (by choice); only what is drawn on them changed.
- The fix pass runs on exported modules: rerunning `export_roblox.py`/`export_corridor.py` drops the fixes until
  `road_fix.py` is run again (it is deterministic, so the same modules come back).
- The main repo's build/ is not updated by this branch (build/ is gitignored): after merging, run `road_fix.py` in the
  main checkout too, or copy the modules from the worktree.

## Pass 2 (after the leader's Studio probes, docs/ROAD_AUDIT_STUDIO.md)
New tool `tools/mapgen/studio_probes.py`: offline replicas of the two Studio probes on the exported modules (kerb =
Sidewalk Part centre > 1 stud inside another edge's Road Part, outside every disc + 2; kink = Road Parts >= 6 studs
meeting end to end within 1.5 studs at 35-150 deg with no disc within r + 2).

| replica | before road_fix (exports as imported) | after pass 1 (= Studio now) | after pass 2 | Studio after pass 1 |
|---|---|---|---|---|
| kerb parts inside another road | 99 | **0** | 0 | 58 |
| kinks without a disc | 134 | 78 | **0** | 90 |

### (1) The 58 Studio kerbs are not in the data
None of the 58 exists in the current modules (nor in the pass-1 input): the nearest Sidewalk Part the data builds
is 34-118 studs away from each listed spot. They match, to the stud and the part length, the sidewalks of the
ORIGINAL wide export before the team2 worldfix dropped them (e.g. (21293, 5761) len 47 = `1181954458:w3056`
side -1, (23559, 5496) len 79 = `1181954458:w3064`, (24790, 12807) len 68 = `375975908:w2736`, (18849, 7369) len 25 =
`948070138:w2999`). These edges have had `sidewalk = 0` since the worldfix and still do. So the places hold stale
Sidewalk Parts, most likely a second (old) `Chunk_<id>` model or a second (old) `chunk_<id>` ModuleScript next to the
new one (`WaitForChild`/`FindFirstChild` then picks either). Affected chunks per the listed spots: wide `2_11`, `7_10`,
`9_0`, `-3_12`, `9_25`, `-3_14` (and wherever the other spots are). If the whole worldfix were missing, the replica
would count 540, so only some chunks are stale. Nothing to change in the data; diagnose and rebuild:
```lua
-- which models hold the stale kerbs, and are there duplicate chunk models / modules?
local W = workspace.PattayaWorld
local want = {["1181954458:w3055"] = true, ["1181954458:w3056"] = true, ["1181954458:w3057"] = true,
	["1181954458:w3064"] = true, ["375975908:w2736"] = true, ["146447446:w2419"] = true, ["948070138:w2999"] = true}
for _, m in W:GetDescendants() do
	if m:IsA("Model") and want[m:GetAttribute("EdgeId")] then
		local sw = 0
		for _, p in m:GetChildren() do if p.Name == "Sidewalk" then sw += 1 end end
		print(m:GetAttribute("EdgeId"), m:GetFullName(), "Sidewalk parts:", sw) -- data says 0 for all of these
	end
end
for _, f in {W.Chunks, W.WideChunks} do
	local seen = {}
	for _, c in f:GetChildren() do
		if seen[c.Name] then print("DUPLICATE model", f.Name, c.Name) end
		seen[c.Name] = true
	end
end
for _, n in {"PattayaData", "PattayaDataWide", "PattayaDataCorridor"} do
	local seen = {}
	for _, c in game.ServerStorage[n]:GetChildren() do
		if seen[c.Name] then print("DUPLICATE module", n, c.Name) end
		seen[c.Name] = true
	end
end
print(game.ServerStorage.PattayaDataWide.chunk_2_11.Source:match('id = "1181954458:w3056".-sidewalk = %d+'))
```
Then delete the duplicates (keep the module whose Source matches `build/pattaya_wide/roblox/chunk_<id>.luau`) and
`B.RebuildChunks({<those ids>}, {folder = "PattayaDataWide"})`. The builder now refuses to rebuild when a data folder
holds two modules of one name or two `Chunk_<id>` models exist, and `RebuildChunks` passes `fresh = true` to `Extend`
(chunk and joints modules required from a `Clone()`, never from the require cache).

### (2) The 90 kinks: interior vertices next to short parts
All checked spots are interior vertices of one edge (not degree-2 nodes, not chunk splits): (a) next to the pass-1
fillet pieces (segments 0.6-3 studs; the probe skips parts < 6 studs, so the long parts on both sides meet with the
whole 60-77 deg turn), (b) 29-33 deg vertices next to a 5.9-6.0-stud segment (the probe skips it and sees two turns
as one ~60 deg turn). Rule V (road_fix.py): a joint disc (synthetic negative id, radius = road half-width, on the
centreline) wherever Road Parts >= 5 studs meet within 3 studs at 30-150 deg with no disc - looser than the probe so
small replica differences are covered. 407 discs: central 54, wide 346, corridor 7. They change only the `joints`
modules; every chunk module is byte-identical to pass 1 (checked with `diff -rq`).

### Changed modules in pass 2 (no chunk modules)
`PattayaData.joints` (183 rows), `PattayaDataWide.joints` (1,450), `PattayaDataCorridor.joints` (20); builder
(`fresh` option, duplicate checks).

Rebuild: replace `PattayaBuilder` (require a Clone) and the three `joints` modules (new instances), then
- `B.RebuildChunks({})` - base: adds the 54 new joint discs to `PattayaWorld.Junctions` (441 -> 495);
- `B.Extend({folder = "PattayaDataWide", terrain = false, only = {}, fresh = true})` - adds 346 to `WideJunctions`;
- `B.Extend({folder = "PattayaDataCorridor", terrain = false, only = {}, fresh = true})` - adds 7 (WideJunctions
  2,500 -> 2,853);
- fix the stale kerb chunks as above.
Expected Studio counts after pass 2: kink probe ~0 (replica 0; the replica found 78 where Studio found 90, so a few
Studio-only cases may remain - send their coordinates); kerb probe 0 once the stale parts are gone (replica 0).


## Dual carriageways and slip roads (team4/dual, 2026-10-19)

Status: **data built and checked offline, NOT built in Studio yet.** Passes 1 and 2 only hid what was drawn on the
overlapping slabs; this pass removes the overlaps themselves (the 92 slab-overlap pairs of docs/ROAD_AUDIT_STUDIO.md).
All numbers come from the tools run on this worktree's build/ (= the modules the leader has in Studio, regenerated
byte-identically by the unchanged pipeline before anything was changed). Map data (c) OpenStreetMap contributors, ODbL 1.0.

### Tool and pipeline
New module `tools/mapgen/dual.py` (rules in its docstring). Pipeline order:
`road_graph.py` central, wide (wide calls `dual.apply_offsets`, rule b; config flag `dual_offsets` in pattaya_wide.json)
-> **`dual.py`** (writes `build/dual/plan.json`: merge groups, kept / hidden roles, trims; copy `docs/road_audit/dual_plan.json`)
-> `buildings.py` / `gameplay_layout.py` wide -> `traffic.py` central, wide (lane fix from the plan) -> `export_roblox.py`
central, wide -> `export_corridor.py ... build/pattaya_wide` -> `corridor_traffic.py` (lane fix) -> `road_fix.py`
(new rule D, first after K) -> furniture.py (leader). Two complete runs from road_graph.py gave byte-identical outputs
(every module, plan, json). `dual.py --png <root before>` writes the check images.

Per pair of overlapping edges (the road_audit pair rules: parallel without a shared node, < 60 deg at a shared node):
- **(a) merge** - same name (normalised: case / space / '-' / '.' insensitive, Thai or English; Thep Prasit = Thepprasit)
  and parallel, or an unnamed pair of one-way ways of one class running opposite (an unnamed dual carriageway). Both
  edges stay in the graph. Per merge component the widest edges are KEPT (greedy, no two kept edges may overlap, also
  re-checked after the shift: 27 more demoted to hidden), the others HIDDEN. Kept chunk line: `merged = true`, pts =
  merged centreline (shifted sideways by half the lateral offset to the hidden partner = centred between the two
  centrelines, centred on the extent with partners on both sides; fades out over 20 studs of extra gap, over 60 studs
  before an end where the road continues un-merged; turns <= 17 deg off the old line), width = its own (the wider one),
  two-way markings (lanes = width / 13) when the directions differ, sidewalks restored and re-checked by rule S.
  Hidden chunk line: `hidden = true` (no slab, markings, kerbs), or - where the carriageway leaves the merged slab -
  `cutA` / `cutB` / `hide` ranges: its slab is built only where it is clear of the merged surface, the transition is
  rebuilt as `fill` triangles. Cross streets / median connectors ending at a merged node: their slab end is cut back to
  where it is no longer fully inside the merged surface (no fill needed).
  Pairs: 527 one-way opposite (rule a proper), 5 unnamed one-way opposite pairs, 42 one-way same direction (main carriageway + service carriageway of the
  same road, e.g. Sukhumvit at flyovers: an offset would have to move them 40-56 studs), 11 with a two-way way
  (Chalermphrakiat's 4-5 parallel carriageways, Thap Phraya). 27 groups: Sukhumvit (5 groups), Thep Prasit / Thepprasit
  (22 kept / 23 hidden edges), Thappraya, Pattaya Nuea (central + wide), Jomtien Second Road (2), Chalermphrakiat (2),
  Pattaya Tai (2), Pattaya Klang, Pattaya Na Kluea, Rajchawaroon, Central Park 2, Sukhumvit Pattaya 18, Thammasat
  (corridor), 5 unnamed dual sois. 256 kept edges, 328 hidden (306 build nothing, 21 partly, 1 untouched).
- **(b) offset** - two different roads in parallel, the minor one movable (wide world, not base), overlap at least 60
  studs from both end nodes, shift <= 30: **1 edge**, `130659182:w2277` (unnamed soi beside `936726418:w2981`, world
  ~(17,890, 6,940)), interior points moved up to 9.8 studs, end nodes fixed, 60-stud ramps. Every other different-road
  pair touches an end node within its ramp length (or is in the base slice), so it falls to rule c.
- **(c) trim** - acute pairs at a shared node (240 acute + 9 longer splits), slip roads (29 `*_link` pairs), different
  roads overlapping near an end / in the base slice (60), new overlaps a merged line made (11): the minor road's slab is
  cut back (`cutA` / `cutB`, or `hide` ranges for a parallel stretch) to where it fully leaves the other road; that part
  of its old slab not covered by any other surface is rebuilt exactly as flat triangles (`fill`, two WedgeParts each,
  attribute `RoadFill`) - lossless, no hole. Polylines (routing, GPS, traffic) unchanged.
- Places that must stay on the road (job stands, bosses, race grid, spawn - none of them moves): 3 such points
  (among them the job stands thepprasit_night and jomtien_beach_north, which sit at the kerb lane of a merged
  carriageway) would have ended up off or within 3 studs of the edge of the narrower merged slab; the old slab is kept
  under them as fill (+-25 studs along the road).

Rule D totals (`road_fix` stats): 256 merged lines, 306 hidden + 21 partly hidden carriageways, 651 trim applications
(424 cut edges, 126 short connectors / slip stubs entirely covered), 529 cross-street ends cut, 2,943 fill triangles
(~280,000 studs^2) on 385 edges.

### Before / after
| check | before this pass | after |
|---|---|---|
| road_audit `parallel` (geometric, any names) | 684 (visible 0) | **1** (9 studs, central Chalermphrakiat x connector) |
| road_audit `acute` (geometric) | 240 (visible 0) | **0** |
| road_audit `tee` / `crossing` / `step` | 293 / 0 / 0 | 118 / 0 / 0 |
| marking Parts on another road / kerb sides > 10 studs^2 on another road | 0 / 0 | **0 / 0** |
| bare bends > 35 deg (audit) / kinks without disc (Studio replica) | 0 / 0 | **0 / 0** |
| kerb parts inside another road (Studio replica) | 0 | **0** |
| **slab-overlap probe replica, different road names** (Studio: 92 pairs, ~2,300 studs) | 70 edge pairs, 973 samples (~3,900 studs), 21 road-name pairs | **0** |
| slab-overlap replica, all names (incl. Sukhumvit x Sukhumvit) | 234 edge pairs, ~18,700 studs | **0** |
| road_check central: sidewalk / hairline / none (4,422 probes) | 0 / 8 / 1 | 0 / 8 / 1 |
| road_check wide (23,142) / wide + corridor (24,404) | 0 / 1 / 0, 0 / 1 / 0 | 0 / 1 / 1, 0 / 2 / 1 |
| traffic loop samples (every 10 studs, 60.4k) on no road surface | 3,013 | **1,182** |
| race path (1,327 samples) on road, 3+ studs inside | 1,327 | 1,327 |
| job stands / bosses / grid / spawn on road | all | all |

The one `none` probe is `258748314:w2639` at world (24,938, 12,875): a point exactly on the border of its own fill
triangle and slab (distance 0.00), i.e. a hairline. Replicas: `tools/mapgen/studio_probes.py` (now also the slab-overlap
probe and a traffic probe), `road_audit.py`, `road_check.py` - all read hidden / cutA / cutB / hide / fill.
Reports: `docs/road_audit/summary_before_dual.json`, `summary_after_dual.json`, `findings_after_dual.csv`,
`docs/images/road_audit_after_dual.png`; check images `docs/images/dual_thep_prasit.png`,
`dual_slip_sukhumvit_north.png` ((23,550, 4,431)), `dual_slip_sukhumvit_klang.png` ((24,479, 910) and (24,691, 342)).

Road surface: merged carriageways get narrower on purpose (one slab of the wider width instead of the union of two):
~1.08 M studs^2 of the old union is gone, all of it inside merge groups; outside them only the moved soi's old strip
(847 studs^2) and simplification slivers (< 8 studs^2 each). Road Parts: before 15,005 slab Parts (matches Studio);
after 13,706 slabs + 5,862 fill WedgeParts = 19,568 (central 2,063 + 374, wide 11,160 + 5,444, corridor 483 + 44);
hidden carriageways also drop their markings and kerbs.

### Downstream changes (asserted)
- Graph (index stability): node lists, node order, edge order and every edge line of `graph.luau` are identical;
  exactly one line differs, the moved soi in `graph_part_2.luau` (pattaya_wide line 186 / corridor line 418: length
  322.6 -> 314.0, polyline). `graph_game.json` central: unchanged; wide: only `130659182:w2277`'s pts.
- `jobs.luau`, `roadfight.luau`, `manifest.luau`, `worldmap.luau` (central, wide, corridor): byte-identical. Race path,
  job stands, bosses, grid: unchanged (layout.json `race` / `job_stands` equal).
- Traffic: same loops, same order, same speeds / car kinds / car counts (cars are counted on the unmerged lane length,
  the moved soi is planned with its unshifted length); lane geometry changed on 8 of 36 central loops, 41 of 84 wide
  loops (incl. those 8) and 2 of 3 corridor loops (max lane move 27 studs): on a merged slab the lane is measured from
  the merged centre, opposite directions each on their left half, inside the slab.
- buildings_game.json wide: 1 building trimmed (311941392 Grand Condominium, next to the moved soi). layout.json wide:
  only `graph_sha1` and `landmarks` (the wide copy of the central landmark list was stale; it now carries the gate fix
  the central slice already has - the wide export does not use it).
- Backups: `build/*/roblox_prev_dual`, `build/bira/roblox_corridor_prev_dual`, `build/road_fix_prev_dual`,
  `build/central_pattaya/traffic_prev_dual.json`, `build/pattaya_wide/{graph_game,buildings_game,layout,traffic}_prev_dual.json`.

### What the leader installs and rebuilds (Studio)
Save the place first. Replace modules as NEW ModuleScript instances (or let RebuildChunks require Clones, as now).
1. `ServerStorage.PattayaBuilder` <- `roblox/src/ServerStorage/PattayaBuilder.luau` (hidden / cutA / cutB / hide /
   fill / merged; edges without these fields build exactly as before).
2. `ServerStorage.PattayaData.graph_part_2` <- `build/bira/roblox_corridor/graph_part_2.luau` (graph and graph_part_1
   unchanged). `ReplicatedStorage.PattayaTraffic` <- `build/bira/roblox_corridor/traffic.luau`.
   `ServerStorage.PattayaDataWide.joints` <- `build/pattaya_wide/roblox/joints.luau` (central and corridor joints unchanged).
3. Chunk modules + `RebuildChunks` (groups of 8):
   - central (`PattayaData`, `B.RebuildChunks(ids)`), 28:
     `"-3_5","-3_6","-2_4","-2_5","-2_6","-1_4","-1_5","0_4","1_5","2_-1","2_3","2_5","3_-6","3_1","3_2","3_3","3_5","3_6","4_-6","4_2","4_3","4_4","4_5","5_-6","5_-2","5_0","5_1","5_4"`
   - wide (`PattayaDataWide`, `B.RebuildChunks(ids, {folder = "PattayaDataWide"})`), 214: see
     `docs/road_audit/dual_chunks.json` (`wide`).
   - corridor (`PattayaDataCorridor`), 5: `"42_7","44_6","45_7","46_7","47_5"`.
4. Furniture: replace `ServerStorage.PattayaDataFurniture` (manifest + every `chunk_f*`) with
   `build/furniture/roblox` of this worktree, then `F.Remove()` and `F.Build({batch = "f1"})` ... `"f35"` (see
   "Furniture follow-up" below; 92 chunks changed, 7 new, so a full furniture rebuild is simplest).
5. Probes below + the pass-2 probes (kink, kerb) + drive regression (Central Loop; a lap on Sukhumvit / Thep Prasit).
Undo: the `*_prev_dual` modules + the same RebuildChunks calls.

### Slab-overlap probe (command bar, read-only)
```lua
-- Slab-overlap probe (docs/ROAD_AUDIT.md "Dual carriageways and slip roads"; offline replica tools/mapgen/studio_probes.py):
-- every pair of intersecting Road Parts whose road Models have different names: the centreline of one Part is sampled
-- every 4 studs; a sample counts inside the other Part (0.5 studs inside its edge) and outside every Junction/Joint disc
-- (radius + 6). Model pairs with 2+ samples are findings. Fill wedges (attribute RoadFill) are not sampled.
_G.SO = {state = "running"}
task.spawn(function()
	local W = workspace.PattayaWorld
	local roads, grid, G = {}, {}, 64
	for _, f in {W:FindFirstChild("Chunks"), W:FindFirstChild("WideChunks")} do
		if f then
			for _, p in f:GetDescendants() do
				if p:IsA("BasePart") and p.Name == "Road" and not p:GetAttribute("RoadFill") then table.insert(roads, p) end
			end
		end
	end
	for _, f in {W:FindFirstChild("Junctions"), W:FindFirstChild("WideJunctions")} do
		if f then
			for _, d in f:GetChildren() do
				if d:IsA("BasePart") then
					local r, c = d.Size.Y / 2 + 6, d.Position -- discs are cylinders: Size.Y = Size.Z = 2 r
					for gx = math.floor((c.X - r) / G), math.floor((c.X + r) / G) do
						for gz = math.floor((c.Z - r) / G), math.floor((c.Z + r) / G) do
							local k = gx .. "," .. gz
							grid[k] = grid[k] or {}
							table.insert(grid[k], {c.X, c.Z, r})
						end
					end
				end
			end
		end
	end
	local function inDisc(x, z)
		for _, d in grid[math.floor(x / G) .. "," .. math.floor(z / G)] or {} do
			if (x - d[1]) ^ 2 + (z - d[2]) ^ 2 <= d[3] ^ 2 then return true end
		end
		return false
	end
	local op = OverlapParams.new()
	op.FilterType = Enum.RaycastFilterType.Include
	op.FilterDescendantsInstances = {W}
	local hits, n = {}, 0
	for _, a in roads do
		local ma = a.Parent :: Instance
		for _, b in workspace:GetPartsInPart(a, op) do
			local mb = b.Parent :: Instance
			if b.Name == "Road" and not b:GetAttribute("RoadFill") and mb ~= ma and mb.Name ~= ma.Name then
				local cnt = 0
				for t = -a.Size.Z / 2, a.Size.Z / 2, 4 do
					local p = a.CFrame * Vector3.new(0, 0, t)
					local lp = b.CFrame:PointToObjectSpace(p)
					if math.abs(lp.X) < b.Size.X / 2 - 0.5 and math.abs(lp.Z) < b.Size.Z / 2 - 0.5 and not inDisc(p.X, p.Z) then
						cnt += 1
					end
				end
				if cnt > 0 then
					local k = tostring(ma:GetAttribute("EdgeId")) .. " | " .. tostring(mb:GetAttribute("EdgeId"))
					hits[k] = hits[k] or {n = 0, x = a.Position.X, z = a.Position.Z, names = ma.Name .. " x " .. mb.Name}
					hits[k].n += cnt
				end
			end
		end
		n += 1
		if n % 300 == 0 then task.wait() end
	end
	local findings, samples = {}, 0
	for k, h in hits do
		if h.n >= 2 then
			table.insert(findings, ("%s (%s) %d samples at (%.0f, %.0f)"):format(h.names, k, h.n, h.x, h.z))
			samples += h.n
		end
	end
	local fills, hidden, merged = 0, 0, 0
	for _, f in {W:FindFirstChild("Chunks"), W:FindFirstChild("WideChunks")} do
		if f then
			for _, d in f:GetDescendants() do
				if d:IsA("WedgePart") and d:GetAttribute("RoadFill") then fills += 1
				elseif d:IsA("Model") and d:GetAttribute("Hidden") then hidden += 1
				elseif d:IsA("Model") and d:GetAttribute("Merged") then merged += 1 end
			end
		end
	end
	_G.SO = {state = "done", roads = #roads, findings = findings, samples = samples, fills = fills, hidden = hidden, merged = merged}
	print(("slab-overlap: %d Road parts, %d edge pairs, %d samples (~%d studs); fill wedges %d, hidden models %d, merged models %d")
		:format(#roads, #findings, samples, samples * 4, fills, hidden, merged))
	for i = 1, math.min(#findings, 20) do print("  " .. findings[i]) end
end)
```
Expected after the rebuild (offline replica): **0 edge pairs** (before: 70 pairs / ~3,900 studs by this definition; the
original Studio probe counted 92); Road parts sampled 13,706; fill wedges 5,862 (central 374, wide 5,444, corridor 44);
hidden models 432 (central 26, wide 403, corridor 3 - includes 126 fully covered stubs); merged models 256 (central 8,
wide 245, corridor 3). Run the pass-1 probe too: marking parts on another road 0; road rays on a sidewalk ~0.

### Open risks
- Builder changes and the WedgePart triangle were not run in Studio. The triangle math was verified offline (80k
  random points: exactly one wedge under every point of the triangle, none outside) assuming Roblox's WedgePart shape
  (slope from the front-bottom edge up to the back-top edge). If the fills come out mirrored, flip the sign of `zv`.
- Merged roads are narrower than the two carriageways were (by design: one slab of the wider width); junction discs at
  the kept carriageway's nodes stay at their graph position and can bulge up to half the old centreline gap (Thep
  Prasit 7 studs, Sukhumvit up to ~20) past the merged slab's edge.
- Traffic lanes: on merged slabs fixed; 1,182 loop samples still off any road surface (pre-existing: outer-lane rule
  `width/2` on wide one-way roads and DP corner cutting; was 3,013).
- Furniture: fixed in the follow-up below (the unchanged furniture.py would have left 168 of 502 zebra crossings
  hanging partly off the merged slabs). Kerb props stay clear of all roads (they keep off the union of the old
  corridors) but may stand up to ~20 studs back from the narrower merged kerb.
- Part count +4,500 net (fill wedges vs dropped hidden slabs); busiest chunk wide `8_2` (Sukhumvit / Pattaya Klang
  interchange) ~370 fill wedges.
- road_fix runs on fresh exports only; `dual.py` must run after road_graph.py (traffic.py and road_fix.py refuse a stale plan).

### Furniture follow-up (team4/dual)
`tools/mapgen/furniture.py` now reads the BUILT road surface from the fixed chunk modules (road_check.slab_rects: slab
pieces after rule D, fill triangles, junction / joint discs) and the dual plan (`build/dual/plan.json`):
- Zebra crossings on an edge whose chunk line is `merged` / `hidden` / cut (or of a dual group) are centred on the
  merged (kept) centreline of the group and span that slab's width; a second crossing within `merge_studs` of one
  already placed (the other carriageway had one at the same spot) is dropped; bars are dropped in pairs until all lie
  on the built surface; a crossing on a hidden edge with no kept twin is skipped.
- New export checks (asserted): `crossing_bar_off_built_road` and `on_built_road` (any non-overhead furniture part on
  the built road surface), besides the old graph-corridor checks, so a road-surface change can no longer pass silently.

Run (from D:/ROBLOXRACE-worldfix): `D:/ROBLOXRACE/.venv/Scripts/python.exe tools/mapgen/furniture.py tools/mapgen/config/furniture.json --build-root D:/ROBLOXRACE-worldfix/build`

| | installed (D:/ROBLOXRACE/build/furniture) | after |
|---|---|---|
| zebra crossings | 502, 168 of them partly off the built road (checked on the dual build) | **438, 0 off the built road** (253 moved onto a merged centreline, 51 duplicates of the other carriageway dropped, 7 on hidden edges without a twin skipped, 14 no room on the built slab) |
| signals / name signs / shelters / taxis on the built road | - | **0** (all checks 0) |
| poles | 519 | 715 (the part budget freed by the crossings goes to more soi poles, as the budget rule says) |
| parts / chunks | 9,246 / 267 | 9,140 / 274 (largest chunk 235 parts) |

Changed furniture modules: manifest, 92 `chunk_f*` changed, 7 new (`f-1_9`, `f-2_8`, `f-2_9`, `f2_10`, `f2_9`,
`f5_9`, `f6_-5`), none removed; list in `docs/road_audit/dual_furniture_chunks.json`.

### Excluding merges (owner's choice)
`tools/mapgen/config/dual.json`: `exclude_link_kinds` (any of `opposite`, `same_direction`, `two_way`, `unnamed_dual`)
and `exclude_groups` (ids as in `build/dual/plan.json`, `"g:<edge id>"` = the member with the lowest graph index,
stable while the graph is). Excluded pairs are not merged; they fall to rule b / c (offset, or cut + exact fill) like
different roads. Each plan group lists its `link_kinds`, e.g. Sukhumvit `g:541668101:w945` {opposite 154,
same_direction 26}, `g:688427427:w999` {opposite 3, same_direction 16}; the two-way ones are `g:35068359:w35`
(Chalermphrakiat) and `g:143685763:w455` (Thap Phraya); unnamed duals `g:35608360:w99`, `g:742697975:w1984`,
`g:375840698:w2720`, `g:936560638:w2938`, `g:1185423798:w3065`. Tried: `exclude_link_kinds: ["same_direction"]`
gives 26 groups / 456 trims (the 42 frontage pairs become cut + fill). After a change rerun from road_graph.py
(the whole chain, then furniture.py); empty lists = this build.

### Dual pass 2 (after the leader's Studio rebuild and probes)
Studio results of the dual build: markings on another road 0, kerb centres in another road 0, bare bends 0, slab
overlaps 70 short ones (12-16 studs at junction throats, the `tee` class, accepted). Three leftovers fixed (data only):
1. **Fill triangles under buildings** (osm 311941409, Chunk_-2_6; 311061457 + 311061340, Chunk_9_1): road_fix rule D
   now clips every fill polygon to stay `dual.BUILDING_CLEAR` = 1 stud (+0.4 for the triangle simplification) away from
   every building box of every chunk module (corridor dressing included), and asserts it at export
   (`check_fill_triangles_at_buildings` 0; 1,459 studs^2 of fill clipped). **Yaw caveat:** the three reported fills only
   touch those boxes when a box is rotated by -yaw; the exporters' shapely checks rotate by +yaw (under +yaw the fills
   were 3 studs away). The clip uses both readings. If -yaw is what Studio builds, note that 1,187 Sidewalk strips
   already touched buildings before the dual pass (7 under +yaw) - worth one Studio look at a building's CFrame.
2. **Furniture on a kerb** (NameSignPost at (21,589, 5,644) on the merged Thep Prasit sidewalk): furniture.py now also
   reads the BUILT sidewalks (road_check.sidewalk_rects on the fixed chunk modules); non-overhead parts may not touch the
   built road or sidewalks, ground parts keep `kerb_margin_studs` from them; asserted checks `on_built_road_or_sidewalk`
   and `ground_part_inside_built_kerb_margin` (both 0). No name sign is left within 15 studs of that spot.
3. Changed modules against the place as rebuilt (list also in `docs/road_audit/dual_pass2_chunks.json`):
   - central (`PattayaData`), 1: "-2_6"
   - wide (`PattayaDataWide`), 21: "-1_14","-2_6","-3_9","-4_10","-4_9","-7_9","10_-5","10_-8","11_-7","1_9","2_19","3_-13","5_-6","5_23","6_-3","6_1","7_4","7_6","8_3","9_0","9_1"
   - corridor: none. No graph / traffic / joints / manifest module changed.
   - furniture (`PattayaDataFurniture`): manifest + 135 changed + 8 new chunk modules
     (new: "f-1_10","f-2_10","f-6_6","f-6_7","f0_10","f10_-2","f3_-7","f5_-7"); 282 chunks, 9,119 parts, 438 crossings (0 off the road), 717 poles. The
     sidewalk clearance moves name signs / poles, and the freed part budget refills the soi poles, so many furniture
     chunks change: a full furniture rebuild (`F.Remove()`, batches f1..f36) is simplest.
Checks after: audit parallel 1 / acute 0 / crossing 0 / visible conflicts 0; slab-overlap replica 0; road_check
central 0 / 8 / 1, wide + corridor 0 / 2 / 2 (the new `none` is a centreline point now under a building where the fill
was clipped); two runs (exports + road_fix + furniture) byte-identical.

