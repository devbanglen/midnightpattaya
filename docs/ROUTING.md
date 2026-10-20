# Routing: how routes join the road graph

`roblox/src/ServerStorage/PattayaRoute.luau` is the shared route module. It runs on the generated road graph
(`ServerStorage.PattayaData.graph` = `build/bira/roblox_corridor/graph.luau` + `graph_part_*.luau`, 2,941 nodes and 3,818
edges, city first, then the Bira corridor). Taxi and delivery jobs, the GPS, Street Sprint, Street Race, events,
challenges and Road Fight all use it.

Owner rule (2026-10-21): a route must never take a straight line through buildings as a shortcut onto the graph.

Branch `team15/routing`. Status: tested offline only (luau CLI harness, real data). **Not yet checked in Studio.**

## The bug

The leader started a taxi job at the Central Festival stand in Play (ring at world (21242, 1.2, 374)). The guidance
line ran straight from the stand to about (21338, 308) across a building block and terrain, then joined the roads. A
car following the line left the road. A job from Terminal 21 was clean.

### Cause

`PattayaJobsServer` connects a stand to the graph with `Route.nearestNode(stand, 600)`, the nearest **junction**
within 600 studs. Then it adds the stand position before the polyline. This gives a straight line from the stand to
that junction, whatever is between them:

- Central Festival (map-local (1242.27, 373.66)) is 0.5 studs from the centreline of edge #4 (a 13-stud soi, node 47
  → 46). Its nearest junction is node 58 at (1365.0, 289.8), 148.6 studs away. The straight line crosses OSM buildings
  153538003 and 272236566. The leader's (21338, 308) lies on this line. The harness checks this:
  `test_old_module_reproduces_the_central_festival_bug`.
- The same happens at the **end** of a job. The destination stand is joined from its nearest junction too, so every
  job *to* Central Festival had the same 149-stud line. Bangkok Hospital had a 198-stud line through 2 buildings.
- Terminal 21's junction is 51 studs away along open road, so its line stayed clean. That was luck.

`Route.routeTo` (GPS, TestKit `publishRouteTo`) already joined the graph by projecting onto the nearest edge. The
stand-to-junction connector lived only in the jobs flow.

## The fix (PattayaRoute.luau only)

1. **`Route.snap(p, maxSnap)`**: where a route from `p` joins the graph. It projects `p` onto every edge polyline
   (point on a segment, not the nearest vertex), then prefers, nearest first:
   1. an edge whose road slab contains `p`: the connector is at most half the road width (`e[5] / 2`) plus
      `SNAP_MARGIN` = 8. Inside the road surface no check is needed. In the 8-stud margin the connector must not
      cross a building.
   2. one of the `SNAP_TRIES` = 32 nearest edges whose connector crosses no building (for a paddock or car park off
      the graph);
   3. the nearest edge, as before. This covers a point boxed in by buildings, or no building data.
2. **Building footprints at runtime**: `Route.crossesBuilding(p, q)` reads the `buildings` rows of the chunk data
   modules that are already in ServerStorage. These are `PattayaData`, `PattayaDataWide` and `PattayaDataCorridor`
   (`chunk_<x>_<z>` and the corridor `chunk_d<x>_<z>`). Each row is an oriented box
   `x, z, w, d, h, yaw, palette, osmId`, the same convention as `PattayaBuilder.buildBuildings`. The modules load
   lazily, per 512-stud chunk, only when a connector leaves the road surface. Grazing within 1 stud of a footprint
   does not count.
3. **Anchors**: `Route.anchor(p)` makes a fixed node at `p`'s snap point. The edge is split into pieces
   a → anchor(s) → b that are added *next to* the original edge, which stays. Each piece costs its share of the edge
   cost + 1e-3, so a path through an anchor never beats the original edge. Routes between junctions do not change.
   Pieces follow the adjacency: a one-way edge (no b → a link) would give one-way pieces. Anchor indices are above
   `#nodes` and `baseNodes`, so they are never sprint or event destinations, and `Route.nodes` is unchanged.
4. **Job stands without a caller change**: `Route.nearestNode(p, maxDist)` called **without a look direction** at a
   job stand's own position (within 1 stud of a `PattayaData.jobs` row) returns that stand's anchor. The first such
   call makes the anchors for all stands, so the Dijkstra from the start stand reaches every destination anchor.
   `PattayaJobsServer`'s `standNode` → `dijkstra` → `polylineOf` flow and its output format do not change. The
   polyline now runs stand → its own road (0.5–33 studs) → roads → destination road → destination stand.
5. `Route.routeTo` uses `Route.snap` instead of the pure nearest edge (same result whenever the car is on a road). It
   checks one-way through the adjacency. It no longer indexes a missing tail when the destination is the far end of
   a one-way edge.
6. `polylineOf` reads the cached edge polylines (`edgePts`) instead of re-parsing `graph.edges[i][6]`. Same points.
   `Route.nodePos(n)` returns a junction or anchor position.

Unchanged: `pointToPoint` (Street Sprint, Street Race, events, challenges, Road Fight) still starts at the nearest
junction ahead (`nearestNode` with a look direction) and keeps the default snap. `nearestEdge`, `dijkstra`, `along`,
`length`, `segDist`, `carOf`, `busy`, `toLocal`/`toWorld` are unchanged. `routeTo` keeps its default `maxSnap` (150)
and the GPS keeps 700. All old functions still exist, and the polyline format is unchanged.

## Before / after (offline harness, real data)

All 25 job stands in `build/pattaya_wide/roblox/jobs.luau`. Each stand goes to every destination the jobs server can
offer (900–3,200 studs by road). "Off-road" means samples every 4 studs that are farther than half the road width
+ 8 from every edge. Building checks use 10,193 footprints from all chunk modules.

| Jobs (all stand → destination routes) | old module | new module |
|---|---|---|
| routes | 62 | 54 |
| longest stand → graph connector (start) | 269.3 | 20.5 |
| longest graph → stand connector (end) | 269.3 | 20.5 |
| routes crossing a building | 14 (4 buildings) | 0 |
| longest off-road stretch | 237 | 0 |
| stands with at least one job | 20 | 19 |

| stand | old connector to junction | crosses buildings | new connector to its road | jobs offered old / new |
|---|---|---|---|---|
| central_festival | 148.6 | **yes** | 0.5 | 6 / 5 |
| terminal21 | 51.1 | no | 6.4 | 4 / 4 |
| walking_street | 15.7 | no | 13.5 | 4 / 4 |
| alcazar | 53.8 | no | 20.3 | 5 / 6 |
| tiffanys | 200.4 | no | 19.9 | 3 / 2 |
| art_in_paradise | 264.4 | no | 19.6 | 3 / 2 |
| police_station | 49.4 | no | 0.5 | 7 / 5 |
| night_plaza | 10.6 | no | 7.0 | 6 / 5 |
| bua_khao | 20.6 | no | 7.0 | 3 / 3 |
| chai_mongkhon | 129.8 | no | 20.5 | 3 / 2 |
| hong_tu_la | 128.9 | no | 19.5 | 3 / 2 |
| windy_plaza | 45.2 | no | 0.5 | 6 / 6 |
| sanctuary_truth | 10.6 | no | 6.9 | 0 / 0 |
| wong_amat | 106.0 | no | 6.7 | 1 / 0 |
| lan_pho_naklua | 25.7 | no | 7.4 | 1 / 1 |
| naklua_fresh | 61.8 | no | 7.0 | 1 / 1 |
| bangkok_hospital | 198.3 | **yes** | 7.1 | 1 / 1 |
| mini_siam | 10.6 | no | 7.0 | 1 / 1 |
| big_buddha | 146.2 | no | 7.2 | 0 / 0 |
| pratumnak_night | 62.1 | no | 7.0 | 0 / 0 |
| thepprasit_night | 46.3 | no | 33.0 (78-stud road) | 0 / 0 |
| jomtien_beach_north | 72.6 | no | 13.2 | 0 / 0 |
| jomtien_marina | 62.9 | no | 7.2 | 2 / 2 |
| jomtien_night | 139.9 | no | 7.0 | 1 / 1 |
| big_market_jomtien | 269.3 | no | 7.7 | 1 / 1 |

Some destination counts change because road distances are now measured from the stand's own road, not from a
junction up to 269 studs away. Wong Amat loses its only destination, which was just in range before. The stands with
0 jobs had none before either.

**GPS** (`routeTo`, snap 700) ran from the garage (spawn and ±20 studs), the Bira paddock, all 25 stands and 40 cars on
random roads (city and corridor), to `bira` and `central`: 98 routes. Every route is **identical** to the old module
(projection already). The longest start connector is 33 studs, except the Bira paddock (232.5, see below). No route
crosses a building or has an off-road stretch.

**Off-road starts behind buildings** (30 random off-road points in the central slice whose nearest-edge connector
crosses a building): the new snap finds a building-free connector for 15. The other 15 are boxed in by buildings
(courtyards a car cannot reach) and keep the old nearest edge.

**Sprints / Street Race / events** (`pointToPoint`, 34 seeded calls from the garage, stands and junctions, both
1,200–2,400 and 1,500–2,600): checkpoints, directions and route are **byte-identical** to the old module. They also
match after the job anchors exist.

Cost (luau CLI, no native codegen): GPS route ~9.6 ms (old ~9.5). Making the 25 stand anchors once is ~150 ms, on the
first job request. The worst off-road snap with building checks is 15 ms.

## Callers checked

| caller | uses | effect |
|---|---|---|
| PattayaJobsServer | `nearestNode(standPos, 600)` (no look), `dijkstra`, `polylineOf`, `length`, `toLocal`/`toWorld`, `carOf`, `busy` | **fixed**: stand anchors on the stand's own road; no code change needed |
| PattayaGPSServer | `routeTo(pos, look, osm, true, 700)`, `osmIndex` | same routes for cars on roads; off-road starts avoid building crossings |
| PattayaTestKitServer `publishRouteTo` | `routeTo(..., 700)` | as GPS |
| PattayaSprintServer | `pointToPoint`, `carOf`, `busy` | identical |
| PattayaStreetRace | `pointToPoint` (default 1,500–2,600) | identical; checkpoint logic and its snap untouched |
| PattayaEventsServer | `Route.nodes[n]`, `pointToPoint` from a junction | identical (`Route.nodes` unchanged) |
| PattayaChallengeServer | `pointToPoint` with a seeded `Random` | identical |
| RaceSessionService, CircuitServer, PattayaGarageServer, PattayaRaceServer | `carOf`, `busy` (and graph presence) | unchanged |

### Proposed (optional) caller diff, not applied

The stand match in `nearestNode` (1 stud, no look) makes the fix work without touching the jobs server. If you
prefer an explicit call, change `PattayaJobsServer.standNode` like this (same behaviour):

```diff
-		n = Route.nearestNode(Route.toLocal(s.pos), 600) or false
+		n = (Route.anchor and Route.anchor(Route.toLocal(s.pos), 600)) or Route.nearestNode(Route.toLocal(s.pos), 600) or false
```

With the explicit call, every stand's anchor must exist before the first `dijkstra`. Make all of them in a loop over
`byId` before the first request. The built-in stand match already does this.

## Map data items (separate, awaiting approval, NOT changed)

1. **Bira paddock road is not in the road graph.** `roblox/data/circuits/bira.luau` has `paddockRoad` (20 studs wide,
   (44979, 2879) → (44993, 2829)). The graph stops at the facility junction, 232.5 studs from the paddock, so the GPS
   route from the paddock starts with a straight 232-stud leg over the apron. That leg crosses no building in the
   exported map data, so it was kept. The circuit's own buildings are not in the chunk data and were not checked;
   the pit buildings are ~800 studs east. Proposal: add the paddock road to the corridor graph
   (`tools/circuit/export_corridor.py`). Same case: `bira_paddock → bira` gives a 1-point route (the destination is the
   snap point), as before.
2. **The graph has no one-way information.** Rows are `{a, b, len, tier, width, pts}`. PattayaRoute (old and new)
   treats every edge as two-way, while the traffic data drives some wide roads one-way. The new code already follows
   the adjacency, so it respects one-way once the export provides it. Proposal: export a one-way flag and drop the
   b → a link for one-way edges. That changes job, GPS and sprint routes and needs its own review.
   `test_graph_has_no_oneway_flag` fails if the row format changes, so the module gets revisited.

## Tests

`tools/qa/tests/test_routing.py` (22 tests, ~6 s; part of `run_all.py`):

```
D:\ROBLOXRACE\.venv\Scripts\python tools/qa/tests/run_all.py -k test_routing
```

The harness `tools/qa/routing_harness/` contains `route_harness.py`, `env.luau` (Vector2, Random, fake ServerStorage
with ModuleScripts and a require cache), `tail.luau` (scenarios) and `PattayaRoute_old.luau` (the module before the
fix, from main d6140fb). It runs the real module and the old copy side by side in the luau CLI, on the real graph,
stands and chunk building data from `build/`. The tests skip when `build/` or the luau CLI is missing. They check:

- the old module reproduces the bug: the Central Festival connector is 148.6 studs, crosses buildings and passes
  through (1338, 308);
- the Luau `crossesBuilding` agrees with an independent Python footprint check;
- for every job route: start and end connectors ≤ 42.5, no building crossed, no off-road stretch > 6 studs, and every
  point between the connectors on an edge polyline (continuity);
- every stand anchor is on its road centreline, building-free, and is the nearest edge;
- GPS routes are unchanged where they were clean, on-road starts join their own road, and the garage and Bira
  paddock cases work;
- `pointToPoint` is identical before and after;
- the API is kept and the graph row format is as assumed (no one-way field);
- the before/after summary (prints with `-v`).

The whole suite: 108 tests pass.

## Studio verification (leader)

Install `team15/routing` (only `ServerStorage.PattayaRoute` changed). Then in Play:

1. **Central Festival job**: drive or `TK.teleport` into the Central Festival ring (world (21242, 1.2, 374)) and run
   the job snippet from `docs/TEST_KIT.md` "Taxi / delivery jobs":
   ```lua
   local stand = workspace.PattayaWorld.JobStands:FindFirstChild("central_festival")
   print(TK.teleport(stand.Ring.Position))
   local h = TK.followRoute("JobUpdate", {speed = 140, trigger = function() TK.fire("RequestJob", stand.Name) end})
   ```
   Expect: the guidance line leaves the ring sideways onto the soi the stand is on (first leg < 1 stud), never across
   the block towards (21338, 308). `TK.report()` should show probes on the road and the job finished.
2. **Terminal 21 job**: same with `terminal21`. The first leg is now 6 studs (was 51), and the job still finishes.
3. **GPS to Bira from the garage**: `print(S.publishRouteTo(S.player(), "bira"))`, then
   `print(S.probePath("TK_Route", {every = 25}))`. Expect the same route as before (all road). Optionally run
   `TK.followRoute("GPSUpdate", {physics = true, speed = 140, trigger = function() TK.fire("GPSRequest", "bira") end})`.
4. **GPS from the Bira paddock**: in the paddock run `TK.fire("GPSRequest", "central")`. Expect the same route as
   before (232-stud first leg over the apron, see map data item 1).
5. Optional: start a Street Sprint and a Street Race. Courses come from `pointToPoint` and do not change.

## Rollback

The pre-fix module is kept byte-for-byte at `tools/qa/routing_harness/PattayaRoute_old.luau` (main d6140fb). To roll
back, copy it over `roblox/src/ServerStorage/PattayaRoute.luau`, or `git revert` the fix commit, and reinstall. No
other file depends on the new functions (`snap`, `anchor`, `crossesBuilding`, `nodePos`).
