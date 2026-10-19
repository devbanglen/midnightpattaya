# Quality audit 2026-10-20 (team12/quality)

Scope: why cars tilt on Sukhumvit Road (offline road-seam scan), GPS / minimap code review, mobile HUD overlap.
Everything here was done **offline**. No Studio, no Play test. Nothing below has been tested in game. Every
coordinate is a world position (Studio frame = map-local + ORIGIN (20000, 0, 0); road top y = 1.0).

| Tool | Output (gitignored) |
|---|---|
| `tools/qa/road_seams.py` | `build/qa/road_seams.json`, `build/qa/road_seams.csv` (ranked, with `teleport` = `CFrame.new(x, 6, z)`) |
| `tools/qa/ui_layout_audit.py` | `build/qa/ui_layout.json` (every rectangle, per viewport and input) |

Rerun: `D:\ROBLOXRACE\.venv\Scripts\python.exe tools\qa\road_seams.py` (about 35 s; `--build-root` if build/ is
elsewhere; it finds the main checkout's build/ from a worktree) and `...python.exe tools\qa\ui_layout_audit.py`.

## 1. Road seams / Sukhumvit tilt

### Method
`road_seams.py` rebuilds the road surface as the Studio builders build it, from the exported modules they read:
central, wide and corridor chunk modules + joints (via `tools/mapgen/road_check.py`, which ports
PattayaBuilder's `stripe` / `offset` / `trim` and road_fix rule D `hidden` / `cutA` / `cutB` / `hide` / `fill`), plus
the apron layer (`build/aprons/roblox`, PattayaApronBuilder triangles / boxes). Fill triangles and aprons are cut into
the same two WedgeParts as `roadTriangle` / `Aprons.triangle`, with the same 0.05-stud skips. Surface tops: slab and
fill 1.00, junction / joint disc 0.99, apron 0.98, corner fill 1.58, sidewalk 1.60, terrain -2. 3,818 edges, 52,922
surface pieces, 332 Sukhumvit edges (177 of them hidden carriageways).

### Height, slope, roll: none in the data
- The exported road data has **no elevation at all**: no y, no layer, no grade. Every road part's top is a constant
  (1.00 / 0.99 / 0.98). Max height step between consecutive slab parts: **0.00**; at a node: **0.01** (disc vs slab).
  Slope change between neighbours: **0 deg**.
- Roll / pitch of every built part: **0.000 deg** (stripes are `CFrame.lookAt` between two points at the same y; discs
  `Angles(0, 0, 90)`; every fill / apron / corner WedgePart has its up axis computed from the builder formula
  `xv = yv x zv` with horizontal yv, zv: max deviation 0.000 deg over all wedges).
- So a car cannot be tilted by a sloped or rolled road part. A tilt can only come from a suspension ray that finds
  **nothing** (falls 3 studs to the terrain at -2 on one wheel) or a **raised** surface (+0.6 kerb) under one wheel.
  CarController casts one ray per wheel mount, `reach = suspensionRest + radius` (about 3.1 studs) and filters only the
  car and the character, so a one-wheel hole of 1-3 studs width is enough to drop that corner for a frame or two.

### What the scan found
| class | whole map | on / within 60 studs of Sukhumvit |
|---|---|---|
| `gap`: enclosed hole in the road surface, 0.5 to 3 studs wide | 28 | **20** |
| `sliver`: enclosed hole 0.05 to 0.5 studs wide | 75 | 19 |
| `end_gap`: slab end, then 0.5 to 4 studs of open ground, then road again | 20 | 4 |
| `narrowing`: slab end, part of its width has no road after it for > 4 studs | 16 | **10** |
| `kerb`: sidewalk / corner fill (+0.6) under a wheel track inside a lane | 31 | 0 |
| `drop`: wheel track inside a built slab with no surface | 0 | 0 |
| `tilt` (> 2 deg), `step` (> 0.3) | 0 | 0 |
| `zfight` disc / joint 0.99 under slab 1.00 (summary) | 12,471 pairs, 3.1 M studs² | 15 spots listed |

Holes wider than 3 studs or larger than 400 studs² (751) are city blocks and medians and are not counted.
Hidden carriageways are not scanned as lanes (their surface is the merged slab); scanning them gave thousands of
false "drops" on the outer 6.5 studs of the old carriageway outline, which is not built on purpose.

**Every Sukhumvit candidate lies in the road_fix rule D (team4/dual) output**: where a merged dual-carriageway slab
meets a one-way carriageway slab that has `cutA` / `cutB`, the hidden carriageway's `fill` triangles, or another merged
slab at a bend. The holes are the small leftovers between those pieces. This matches "the earlier roll was at the same
stretch" in ROAD_AUDIT_STUDIO (Beach Road -> Bira, up-vector min 0.92 after the dual rebuild).

### Top 10 candidates (whole map, z-fight excluded)
Teleport with `CFrame.new(x, 6, z)`; drive across the spot in each lane.

| # | class | world x, z | road | edge | chunk | what |
|---|---|---|---|---|---|---|
| 1 | end_gap | 23865, 8383 | Sukhumvit Road | 181737961:w2591 | 7_16 | 2.65 studs open after the slab end at node 1185842067 (degree 3), right 11 % of the width: merged slab meets merged slab at a bend, no disc |
| 2 | end_gap | 23880, 8404 | Sukhumvit Road | 32872670:w2089 | 7_16 | 2.65 studs open after the slab end at node 8678395693 (degree 2), right 11 % (other carriageway of #1) |
| 3 | gap | 23576, 4186 | trunk_link (by Sukhumvit) | 709378821:w1152 | 6_8 | hole 12.5 studs², 2.8 wide, ~19 long between a cut slip road (cutA 106) and the hidden Sukhumvit fill |
| 4 | end_gap | 24912, -393 | Sukhumvit Road | 740847244:w1272 | 9_-1 | 2.05 studs open after a cutB boundary across 16 % of the width |
| 5 | gap | 24372, 1491 | Sukhumvit Road | 688432504:w1006 | 8_2 | hole 12.1 studs², 2.7 wide (cutB slab vs hidden carriageway fills) |
| 6 | gap | 25294, 14256 | residential (Jomtien) | 936248301:w2915 | 10_27 | hole 124 studs², 2.5 wide, ~70 long between three residential slabs at one node |
| 7 | gap | 24379, 1467 | Sukhumvit Road | 688432504:w1006 | 8_2 | hole 11.0 studs², 2.6 wide, ~55 long (same place as #5) |
| 8 | gap | 27847, -8698 | Sukhumvit Road | 688730598:w1946 | 15_-17 | hole 9.9 studs², 2.6 wide (cutA 117 / cutB 53 carriageway vs merged slab) |
| 9 | gap | 19319, 6198 | Thepprasit 12 | 733656003:w2874 | -2_12 | hole 69 studs², 2.9 wide, ~42 long between two cut one-way slabs |
| 10 | gap | 23866, 8384 | Sukhumvit Road | 181737961:w2591 | 7_16 | hole 8.8 studs², 2.3 wide, right beside #1 |

### Sukhumvit list (in rank order, 53 in total in the JSON; the 25 worst)
| # | class | world x, z | edge | note |
|---|---|---|---|---|
| 1 | end_gap | 23865, 8383 | 181737961:w2591 | see top 10 #1 |
| 2 | end_gap | 23880, 8404 | 32872670:w2089 | see #2 |
| 3 | gap | 23576, 4186 | 709378821:w1152 (trunk_link) | see #3 |
| 4 | end_gap | 24912, -393 | 740847244:w1272 | see #4 |
| 5 | gap | 24372, 1491 | 688432504:w1006 | see #5 |
| 6 | gap | 24379, 1467 | 688432504:w1006 | see #7 |
| 7 | gap | 27847, -8698 | 688730598:w1946 | see #8 |
| 8 | gap | 23866, 8384 | 181737961:w2591 | see #10 |
| 9 | gap | 23878, 8403 | 32872670:w2089 | 8.7 studs², 2.3 wide |
| 10 | end_gap | 23597, 5074 | 742295595:w2877 | 1.25 studs open, left 11 % |
| 11 | narrowing | 24556, 974 | 742330563:w1290 | left 26 % of the width (offsets -23..-13) runs into open ground |
| 12 | gap | 24030, 10434 | 32872670:w2084 | 12.7 studs², 1.7 wide |
| 13 | gap | 24277, 1760 | 688432504:w1009 | 13.2 studs², 1.5 wide |
| 14 | narrowing | 24884, -381 | 688452705:w1022 | right 21 % at node 417274952 (degree 3) |
| 15 | narrowing | 28479, -9484 | 688729320:w1934 | right 11 % (outer lane edge) |
| 16 | gap | 25729, -3405 | 688493538:w1043 | 3.2 studs², 1.5 wide |
| 17 | gap | 25755, -3467 | 688736044:w1049 | 3.1 studs², 1.4 wide |
| 18 | narrowing | 24610, 425 | 688454077:w1026 | left 11 % |
| 19 | gap | 23872, 3219 | 929607920:w1320 | 2.6 studs², 1.3 wide |
| 20-25 | narrowing | 25948, -4142; 26720, -7095; 27594, -8399; 23645, 5721; 24159, 2097; 24058, 2449 | merged 58-65 wide slabs | outermost 5 % (offset +-29.2) runs off where the merged slab meets a narrower one at a degree-2 node |

Clusters to drive first: **(23860..23880, 8380..8405)** (#1, #2, #10, #9), **(24270..24560, 970..1760)** (#5, #6, #11,
#13 and slivers), **(24880..24915, -395..-380)** (#4, #14), **(27847, -8698)**.

### Proposed fixes (not applied: road data and builders belong to other teams)
- `gap` / `sliver` (dual.py fills): after computing the fill triangles, union the built surface of the stretch (merged
  slab + cut slabs + fills + discs), take its interior holes up to 3 studs wide and emit them as extra `fill` triangles
  (triangulate the hole, it is flat road). For slivers it is enough to grow each fill triangle by 0.05-0.1 studs
  (export rounds to 0.01 and the wedge split skips pieces under 0.05). A unit check: `road_seams.py` `gap` + `sliver`
  near Sukhumvit = 0.
- `end_gap` at merged-merged joints (#1, #2): put a joint disc of the merged half-width at the node (the bend rule B of
  road_fix already does this for normal edges; merged edges at nodes 1185842067 / 8678395693 do not have one), or
  extend the slab end by `width/2 * tan(turn/2)` like `stripe` does inside an edge.
- `end_gap` / `narrowing` at cut boundaries (#4, #11, #14, the 5 % ones): the slab of a one-way carriageway is cut
  where it meets the merged slab but the merged slab is narrower or offset there, so the outer lane steps off the edge.
  Add a taper fill triangle from the cut slab's outer corner to the merged slab edge 15-20 studs further on (1:6 or
  flatter), or shorten `cutA` / `cutB` until the cut slab end lies fully on the merged slab.
- `kerb` (31, none on Sukhumvit; worst: residential (20542, 1620), Pattaya Tai 14/1 (22199, 2810), tertiary
  (24193, 14835)): an edge's OWN inner sidewalk at a sharp interior vertex lies on its lane, because `offset()` moves
  each vertex by the averaged normal without the 1 / cos(turn/2) mitre factor and `stripe` then stretches the strip.
  Fix in the builder (mitre the offset, or trim the inner sidewalk around vertices turning > 35 deg), or fillet those
  vertices in road_fix.
- `zfight`: discs / joints sit 0.01 under the slab top. With RoadLook "wet" the disc gets WetAsphaltJunction
  (Reflectance 0.3) and the slab WetAsphalt (0.25), so the coplanar overlap can flicker at distance. No bump. If it
  shows, lower the discs to top 0.95 (CarController rays would hit the slab anyway where both exist).

## 2. GPS / minimap review

| # | file | bug | status |
|---|---|---|---|
| G1 | PattayaGPSClient | the arrow aimed at the first route point > 25 studs from the car, scanning from `route[1]`. The route starts where the car was at the server's last refresh (every 4 s), so after the car passed that start the arrow pointed back at it until the next refresh | **fixed**: search starts at the nearest route segment (shared `nearestSegment` helper, also used by the distance) |
| G2 | PattayaGPSClient | `changed` compared the new route's id with `current`, which `gpsCycle` sets optimistically before the reply: a switch to a new destination never counted as changed (no Bus toast, no immediate header publish) | **fixed**: compares with the id of the drawn route (`routeId`) |
| G3 | PattayaGPSServer + client | the server silently drops a GPSRequest inside 0.5 s of the previous one. A quick second G (next destination, or off) was lost: client showed "GPS off" while the server kept routing (the next refresh re-drew the route), or the client's `current` pointed at a destination the server never set | **fixed client-side** (server not in this team's files): every request from PattayaGPSClient goes through `request()`, spaced 0.6 s apart, latest wins; G -> off also clears `current`. Proposed server fix (keep the latest request as pending and apply it after the gap): diff in the appendix. The minimap's own destination click still goes straight to the server (one request per click, normally outside the gap) |
| M1 | PattayaMinimapClient | `otherPos` read `seat.Parent.PrimaryPart` for every other seated player: a seat whose parent is not a Model throws in RenderStepped (every 0.5 s) and stops all player dots; `focus()` already guarded this for the local player | **fixed**: same guard as `focus()` (seat as fallback) |

Checked, no bug: route recompute (server: one Dijkstra per Heartbeat, every 4 s per player, `active` cleaned on leave
and on arrival / no route), nil paths (client `route` nil-checked before draw / arrow; minimap `setRoute(nil)` hides
the pool), connections (GPS client: one RenderStepped, one OnClientEvent, Bus handlers registered once; the route
parts are destroyed and rebuilt per refresh, no leak; minimap: pooled route segments, `pressFx` disconnects its
per-press connection), map scale / orientation (north-up, world +Z = screen down, heading `atan2(lv.X, -lv.Z)`, so
+X = arrow right: consistent with `px()`). Minor, not changed: the redraw test `abs(heading - lastHead) >= 2` has no
wrap at +-180 deg (one extra redraw when crossing south); `findAnchor` does not re-anchor if MidnightHUD is ever
recreated (it is ResetOnSpawn = false and only rebuilt by a script reinstall).

## 3. Mobile HUD overlap

`ui_layout_audit.py` replays MidnightHUD `layout()` / `layoutCompact()` / `placeAvoiding()` (incl. the speedometer
slide-left loop and the job strip width), TouchControls `anchorPoint()` / `rectFor()`, the minimap compact card, the
speedometer and the owner-only PerfTelemetry overlay, with constants read from the Luau files. Roblox: top bar inset
58 px (HUD guis have IgnoreGuiInset = false), jump button 70 px at (W-95, H-90) on screens with min side <= 500, else
120 px at (W-170, H-210); dynamic thumbstick start zone = left 40 % x bottom 2/3. Every touch button slot is placed
(race / sprint / circuit / context marked transient).

| viewport | input | layout | permanent overlaps | transient / owner-only |
|---|---|---|---|---|
| 830x439 | touch | compact, scale 0.62 | none between HUD widgets; touch grid, speedometer (339, 268) and jump clear | job strip x PerfTelemetry overlay; minimap card + its 3 buttons reach into the thumbstick start zone (y >= 127) |
| 830x439 | mouse | compact, 0.5 | none | job strip x PerfTelemetry overlay |
| 1334x750 | touch | compact, 0.833 | none | job strip x PerfTelemetry; minimap expand button in the thumbstick zone |
| 1334x750 | mouse | desktop, 0.833 | none | activity strip (anchor 560 wide, content up to 600-660) x quick-menu tiles; toasts x speedometer dial top; chips row x speedometer panel corner; chips x PerfTelemetry |
| 2340x1080 | touch | compact, 1.2 | none | job strip x PerfTelemetry |
| 2340x1080 | mouse | desktop, 1.2 | none | toasts x speedometer dial (the dial is 340 design px tall, the toast column starts 312 above the bottom) |
| 1024x768 | touch / mouse | compact, 0.64 | none | job strip x PerfTelemetry |

**No UI file changed for layout**: the compact (touch) layout has no permanent overlap, and the desktop overlaps are
transient and outside the "keep desktop identical" brief. Proposed, not applied:
- PerfTelemetry overlay (other team's file, owner only, but it is exactly the mobile playtest device): move it off
  the bottom centre (e.g. `UDim2.new(0.5, -125, 0, 4)` under the top bar, or above the job strip), it covers the
  job strip during taxi / delivery jobs. It can be tapped to shrink to 60x18.
- Desktop toasts: start the toast column 40 design px higher (`+ 52` instead of `+ 12` in `layout()`), so the third
  toast clears the speedometer dial.
- Desktop at 1334 px: MidnightActivity's wide rows (600-660 design px) can reach the quick-menu tiles; check with a
  long activity line in Studio.

### TouchControls log spam (leader's measured bug)
`MidnightUI/TouchControls.luau`: `ContextActionService:GetButton(name)` on an unbound action prints "ContextActionService
could not find the function passed in, doing nothing." on every call; `refreshNow()` runs at 2 Hz for every registered
action (CarNitro / CarDrift / CarReset are unbound when not in a car), about 7 lines/s. **Fixed**: `buttonOf` returns
nil unless `GetBoundActionInfo` (silent) says the action is bound; `unstyle` restores the legacy position only for a
bound action. Other call sites checked: `place()` only runs for a button `buttonOf` returned (bound); `showAction`
SetTitle / SetPosition run right after BindAction; GPS / minimap SetTitle / SetPosition follow their BindAction;
TouchSelfTest calls GetButton only for names from GetAllBoundActionInfo.

## 4. Compile check
`luau-compile.exe` on every changed Luau file: TouchControls.luau, PattayaGPSClient.client.luau,
PattayaMinimapClient.client.luau: OK. (Compile only; nothing run.)

## 5. To verify in Studio (leader)
1. Road seams (Play, drive at 100-160 studs/s across each spot in every lane, watch the car's up vector and the wheel
   rays): (23865, 8383) / (23880, 8404) / (23866, 8384) / (23878, 8403); (23576, 4186); (24912, -393) / (24884, -381);
   (24372, 1491) / (24379, 1467) / (24277, 1760) / (24556, 974); (27847, -8698); (24030, 10434); (23597, 5074);
   (28479, -9484); (25729, -3405) / (25755, -3467). Non-Sukhumvit: (25294, 14256), (19319, 6198).
   A read-only Edit-mode check: `workspace:Raycast(Vector3.new(x, 10, z), Vector3.new(0, -20, 0))` at the spot should
   return the terrain (y about -2) if the hole is real.
2. Kerb bumps on inner bends: (20542, 1620), (22199, 2810), (24193, 14835).
3. TouchControls: with the phone emulator, not in a car, the output log no longer prints "could not find the
   function passed in"; in a car NOS / DRIFT / R still appear and are styled.
4. GPS: press G twice quickly (Bira, then Central): the second destination is routed; G G G (to off) quickly:
   GPS ends off and the route line disappears; while driving between refreshes the arrow keeps pointing ahead.
5. Minimap: a second player seated in a car whose seat is not under a Model (or no PrimaryPart) keeps a dot.
6. Mobile emulator 830x439 / 1334x750 / 2340x1080 / 1024x768: compare the HUD with `build/qa/ui_layout.json`
   (jump button and thumbstick positions there are CoreScript approximations).

## Appendix: proposed PattayaGPSServer change (not applied, for the owning team)
```diff
diff --git a/roblox/src/ServerScriptService/PattayaGPSServer.server.luau b/roblox/src/ServerScriptService/PattayaGPSServer.server.luau
index f600d22..3eed1db 100644
--- a/roblox/src/ServerScriptService/PattayaGPSServer.server.luau
+++ b/roblox/src/ServerScriptService/PattayaGPSServer.server.luau
@@ -73,17 +73,15 @@ local function send(plr: Player, dest)
 	GPSUpdate:FireClient(plr, "route", {id = dest.id, label = dest.label, route = r.route, length = r.length})
 end
 
--- at most one GPSRequest per REQUEST_GAP s per player; extras are dropped (the route itself is computed by the
--- Heartbeat below, one per frame, so a player never has two route searches running)
+-- at most one GPSRequest per REQUEST_GAP s per player (the route itself is computed by the Heartbeat below, one per
+-- frame, so a player never has two route searches running). A request inside the gap is not dropped any more: the
+-- latest one is kept and applied when the gap is over (a dropped "off" left the client showing GPS off while the
+-- server kept routing, and a dropped destination left the client's optimistic `current` stale)
 local REQUEST_GAP = 0.5
 local lastRequest: {[Player]: number} = {}
+local pending: {[Player]: {id: any}} = {}
 
-GPSRequest.OnServerEvent:Connect(function(plr: Player, id)
-	local clock = os.clock()
-	if clock - (lastRequest[plr] or -math.huge) < REQUEST_GAP then
-		return
-	end
-	lastRequest[plr] = clock
+local function handle(plr: Player, id)
 	if id == "list" then
 		GPSUpdate:FireClient(plr, "list", available())
 		return
@@ -100,6 +98,20 @@ GPSRequest.OnServerEvent:Connect(function(plr: Player, id)
 		end
 	end
 	GPSUpdate:FireClient(plr, "clear", "Destination not on the map yet")
+end
+
+GPSRequest.OnServerEvent:Connect(function(plr: Player, id)
+	if id ~= nil and type(id) ~= "string" then
+		return
+	end
+	local clock = os.clock()
+	if clock - (lastRequest[plr] or -math.huge) < REQUEST_GAP then
+		pending[plr] = {id = id}
+		return
+	end
+	lastRequest[plr] = clock
+	pending[plr] = nil
+	handle(plr, id)
 end)
 
 -- at most one route per Heartbeat (a route is a nearest-edge scan plus a Dijkstra over the whole graph, ~5-6 ms on
@@ -108,6 +120,15 @@ end)
 -- server keeps up (60 routes/s at most).
 RunService.Heartbeat:Connect(function()
 	local now = os.clock()
+	for plr, req in pending do
+		if not plr.Parent then
+			pending[plr] = nil
+		elseif now - (lastRequest[plr] or -math.huge) >= REQUEST_GAP then
+			pending[plr] = nil
+			lastRequest[plr] = now
+			handle(plr, req.id)
+		end
+	end
 	local due, dueAt = nil, math.huge
 	for plr, st in active do
 		if not plr.Parent then
@@ -126,4 +147,5 @@ end)
 Players.PlayerRemoving:Connect(function(plr)
 	active[plr] = nil
 	lastRequest[plr] = nil
+	pending[plr] = nil
 end)
```
