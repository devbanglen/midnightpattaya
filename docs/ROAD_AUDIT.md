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
