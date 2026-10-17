# Racing route design

Background research on RayCity's race systems: `docs/RAYCITY_RESEARCH.md`. What is built follows its Phase 1
recommendations: a lap race on a real-road loop, a street challenge on a server-picked route, a RayCity-style
nitro gauge, and money/EXP for every race.

## 1. Pattaya Central Loop (lap race)
Generator: `tools/mapgen/gameplay_layout.py` (config block `layout`). Runtime: `PattayaRaceServer`, `PattayaRaceClient`.
- The route is built from legs named by OSM road names: Beach Road (Pattaya Sai 1) southbound → Pattaya Tai →
  Pattaya Sai 2 northbound → Pattaya Klang → back to Beach Road. These are the real one-way directions.
  Each leg is a Dijkstra path between the junctions where the legs meet, and every route edge keeps its OSM way id.
- Length is 6,647 studs per lap (1.86 km in game), 2 laps, 22 checkpoints about 300 studs apart.
- Every checkpoint stays at least 35 studs from any 3-way or bigger junction. Gates are judged by plane crossing,
  so a gate on a junction never counted a lap: a car turning in from the crossing road is already past the plane.
  The automated test caught this.
- Gate width is the width of the route edge at the gate's position along the route, plus 6 studs.
- The route centreline (one point every 20 studs, starting at gate 1) is the attribute `Path` on
  `PattayaWorld.Race`. It is used for GPS, the minimap and the tests.
- 6-slot start grid behind gate 1, with `PattayaSpawn` behind the grid.

Rules (server):
- A gate counts when the car's path between two samples crosses the gate plane going forwards, within the gate
  width plus 12 studs.
  - This is edge-triggered, so a car parked in the finish gate cannot restart the race.
  - A late network sample cannot jump over a gate.
- Start: cross gate 1 going forwards. Pass the gates in order. Finish: cross gate 1 after the last lap.
- Teleport check: if the car moves faster than 260 studs/s between two gates, the run is invalid. Nitro top
  speed is 215.
- Reward: money = distance/25 + 3 × (average speed above 90) + 150 for a personal best. EXP = distance/50.
- Each checkpoint adds 15 nitro.

## 2. Street Sprint (point-to-point challenge on the live streets)
Runtime: `PattayaSprintServer` (route finding on `ServerStorage.PattayaData.graph`) and `PattayaSprintClient`.
- While driving, press **H** (or tap the SPRINT button on mobile). The server takes the nearest junction within
  400 studs, preferring one ahead of the car.
  - It runs Dijkstra over the real road graph. Sois cost 1.6×, so main roads are preferred.
  - It picks a random destination 1,500–2,600 studs away.
  - It places checkpoints every ~250 studs, ending at the destination.
- On the client:
  - Gates appear only for this player: cyan posts, gold for the next one, white for the finish.
  - A gold GPS arrow above the car points at the next checkpoint. The HUD shows distance and time.
- A checkpoint counts when the car's path since the last sample passes within 26 studs of it.
- Limits and checks: 150 s time limit, the same 260 studs/s teleport check, and the run stops if you leave the car
  or start the loop race.
- Reward: money = distance/20 + 2 × (average speed above 90). EXP = distance/40. Each checkpoint adds 20 nitro.
- A RayCity-style "challenge another driver" (two players) is not built yet. This is the solo version.

## 3. Nitro gauge (RayCity SP style, in `CarController`)
Capacity 100.
- Drain: 28 per second while boosting (Shift + throttle).
- Refill: 4 per second always, plus 14 per second while drifting above 40 studs/s, plus 15 or 20 per checkpoint.
- Boosting raises top speed from 160 to 215 studs/s.
- Shown as a bar above the speedometer, orange while boosting.

## 4. Progression (`ServerStorage.PattayaProgress`)
- leaderstats: Level, Money (฿), EXP. EXP needed per level = 100 + 60 × (level − 1).
- A reward toast is shown on screen (`LastReward` attribute).
- Data is saved with DataStoreService under `PattayaProgress_v1`. In Studio this needs "Enable Studio Access to
  API Services". Without it the values last for the session only; the code handles that with a warning.

## Tested (2026-10-18, Studio Play, client-owned car moved by a client-side test autopilot at 140 studs/s)
- **Loop race:** 2 laps.
  - Road under the car at 5,740 of 5,740 samples.
  - States went racing → finished, and the car stayed "finished" while parked past the line.
  - Time 94.63 s. Paid +833 ฿ and +265 EXP (Level 1 → 3).
- **Street Sprint:** 2,339 studs, 9 checkpoints, 9 local gates shown.
  - All checkpoints counted and the run finished in 17.25 s. Paid +208 ฿ and +58 EXP.
- **Teleport cheat:** jumping onto checkpoints 1 and 2 ended the run with "Run invalid (moved too fast)".
- **Nitro:**
  - 2 s of Shift+W took the gauge from 1.00 to 0.43, with the speed label at "217 km/h NOS".
  - 3.5 s without boost refilled it 0.43 → 0.55.
- Not tested: a human driving a full lap or sprint, and multiplayer.
