# Racing route design

Generator: `tools/mapgen/gameplay_layout.py` (config block `layout`) → `build/<slice>/layout.json`,
`layout_check.png`. Runtime: `ServerScriptService.PattayaRaceServer` + `StarterPlayerScripts.PattayaRaceClient`
(copies in `roblox/src/`).

## How a route is made
- A race is a closed list of legs, each named by OSM road names. Corners are the graph junctions shared by
  consecutive legs; each leg is a Dijkstra path between its corners that costs 25x off the named road (so tiny
  connector edges are allowed but the race stays on the intended roads). Every route edge keeps its OSM way id.
- Checkpoints every ~300 studs along the route centreline; checkpoint width = route road width + 6 studs.
- The route centreline (every 20 studs) is stored on `PattayaWorld.Race` as attribute `Path` for GPS/minimap/tests.
- Start grid: 6 slots (2 columns) behind checkpoint 1, facing along the route. `PattayaSpawn` behind the grid.

## Race 1: Pattaya Central Loop (`central_loop`)
Beach Road (Pattaya Sai 1) southbound → Pattaya Tai → Pattaya Sai 2 northbound → Pattaya Klang → Beach Road.
These are the real one-way directions of Beach Road and Second Road. 6,647 studs per lap (1.86 km in-game),
45 edges, 22 checkpoints, 2 laps.

## Race logic
Server checks the next gate each Heartbeat in the gate's local space (|z| < 9, |x| < half width + 2). Start =
through gate 1 moving forward. Player attributes: RaceState, RaceLap, RaceNext, RaceStart (server clock),
RaceLastTime, RaceBest (per session). The HUD glows the next gate gold.

## Tested (2026-10-18, Studio Play)
Server-side autopilot held the car at ride height and followed `Path` for 2 laps at 140 studs/s:
672/672 waypoints, a road part under the car at 5,691 of 5,698 samples (the 7 others were parked grid cars),
race state racing → finished, time 94.65 s recorded as RaceBest.
Not tested with a human driver at racing speed; corners cut over 0.6-stud curbs.

## Instance streaming
The place has `Workspace.StreamingEnabled = true` (from the template). Checkpoints and StartGrid are Models with
`ModelStreamingMode = Persistent` so every client always has all gates.
