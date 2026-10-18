# Test kit (dev only)

`PattayaTestKit` turns the leader's ad-hoc Studio test code into two modules, so a test call is 5-10 lines:

| Repo file | Studio location | Runs on |
|---|---|---|
| `roblox/src/ReplicatedStorage/PattayaTestKit.luau` | `ReplicatedStorage.PattayaTestKit` (ModuleScript) | client (Play, the client's execute context) |
| `roblox/src/ServerStorage/PattayaTestKitServer.luau` | `ServerStorage.PattayaTestKitServer` (ModuleScript) | server |

- **Nothing in the game requires them.** Both modules only work in Studio (`RunService:IsStudio()`) or when
  `workspace` has the attribute `DevTest = true`. Otherwise every call errors with "... is disabled".
- On a live server with `DevTest = true`, clients may only call the server kit if they are the place's creator
  (`game.CreatorId`) or are listed in the `workspace` attribute `DevTestUsers` (`"123,456"`).
- **Install:**
  - `tools/studio/install.ps1` + `install.luau` already bundle every file in `roblox/src`, so they install both
    modules.
  - By hand: make the two ModuleScripts and paste the repo source into each.
- **Status: written and compiled, not run in Studio.** The path, lap-unrolling and drive logic (CFrame and physics
  modes, stalls, pit lap) were run offline with the `luau` CLI and mocked Roblox objects. Nothing ran in Roblox.

## Start (every Play session)

Server (command bar switched to **Server**, or the execute tool on the server):

```lua
local S = require(game.ServerStorage.PattayaTestKitServer).start()   -- also _G.TKS
```

Client:

```lua
local TK = require(game.ReplicatedStorage.PattayaTestKit)           -- also _G.TK
TK.hookRemotes()                                                     -- record every PattayaRemotes event from now on
```

Later calls can use `_G.TK` / `_G.TKS` directly. Drives run in the background. Poll them with
`print(TK.report())` or `print(TK.handles.drive:poll())`.

## API summary

**Client (`TK`):**

| Call | What it does |
|---|---|
| `TK.drivePath(points, opts)` → handle | Autopilot along a path (see the options below) |
| `TK.followRoute(remote, opts)` → handle, err | Drives the next route a remote sends: `"SprintUpdate"` (sprint, challenge, Road Fight, events), `"JobUpdate"`, `"GPSUpdate"`. `opts.trigger = function() ... end` sends the request after the recorder is ready. A race payload's `start` (GO time) is waited for. |
| `TK.autoFollow(remote?, opts)` → stopper | Drives every new route start until `stopper:stop()` (Survival rounds) |
| `TK.lapCircuit(pathAttr, laps, opts)` → handle | Closed path: to the start line, `laps` full laps, 30 studs past the line. Physics mode by default. `pathAttr` = `"RacePath"` (Central Loop) or a published circuit `"TK_Circuit_<id>"`; its `TK_Pit_<id>` is picked up automatically: a car in the pit lane drives out along it, `pitOnLap = k` takes the pits on lap k (`pitSpeed`, default 45). |
| `TK.hookRemotes(names?)` → recorder | Every `OnClientEvent` of `PattayaRemotes` plus every player attribute change, with timestamps. Recorder methods: `rec:dump(n, filter)`, `rec:last(remote, kind)`, `rec:wait(remote, kind, timeout)`, `rec:count(...)`, `rec:clear()`, `rec:stop()` |
| `TK.probeRoadUnderCar()` → info, text | One raycast under the car: what it hit, and whether that counts as road |
| `TK.seatIn(car?, at?)` | Server kit: seat in `workspace[car]`. `"personal"` = your garage car; `nil` = the nearest free race car |
| `TK.teleport(target, opts?)` | Server kit: move the car in hops (see below) |
| `TK.server(action, ...)` | Any server kit action by name |
| `TK.fire(remote, ...)` / `TK.invoke(remote, ...)` | `FireServer` / `InvokeServer` on `PattayaRemotes`. The call is logged as `out` in the recorder. |
| `TK.readPath(src)`, `TK.reverse`, `TK.concat`, `TK.slice`, `TK.nearestIndex`, `TK.lapPath` | Path helpers |
| `TK.jumpTo(pos)` | Instant client-side move (teleport-cheat tests) |
| `TK.ghostTraffic(true)` | Makes traffic non-solid for this client |
| `TK.report()` | One compact string with all the state (see below) |
| `TK.stopAll()` | Stops every drive |

**`drivePath` options:**

| Option | Default | Meaning |
|---|---|---|
| `speed` | 140 | studs/s, a number or `function(h)` |
| `physics` | `false` | `false`: CFrame + velocity are set every frame, and the ride height is kept on the road by raycast. `true`: only the horizontal `AssemblyLinearVelocity` and the yaw `AssemblyAngularVelocity` are set, so gravity, the suspension, hills and kerbs are real. |
| `corner` | none in CFrame mode, 150 in physics | Lateral grip for a corner speed profile, the same formula as the AI racers |
| `brake` | 110 | Braking for the corner profile |
| `accel` | instant (CFrame), 60 (physics) | Acceleration |
| `caps` | | Per-point speed limits |
| `lateral` | 0 | Studs to the right of the path, a number or `function(h)` |
| `stopAt` | | Distance along the path, or `function(h) -> bool` |
| `startAt` | | Server time to start at |
| `startWhen` | | `function(h) -> bool` that must be true before the drive starts |
| `stalls` | | `{{at = studs, time = s}}`: staged dead stops |
| `holdEnd` | 1 | Seconds the car is held at zero velocity at the end |
| `probeEvery` | 0.5 | Seconds between road probes |
| `onRoad` | | `function(hit, h) -> bool`: your own road test |
| `fromCar` | `true` | Join the path at the car's projection on it |
| `name` | | The key in `TK.handles` |
| `stopIfStuck` | `false` | Stop the drive if the car gets stuck |

**The drive handle:**
- Methods: `h:poll()`, `h:log(text)`, `h:stop(reason)`, `h:wait(timeout)`.
- Fields: `h.done`, `h.reason`, `h.logs`, and `h.stats` (probes, road, off, `byName`, `maxDev`, `minUp`,
  `maxSpeed`).
- The drive waits while the chassis is anchored, so a race grid holds it until GO.

**Server (`S`):**

| Call | What it does |
|---|---|
| `S.player(name?)` | Player by name; the first player if no name |
| `S.seat(plr, car?, at?)` | Seats the player in the car, then teleports it if `at` is given |
| `S.teleport(plr, target, opts)` | Moves the car anchored, in hops of `opts.hop` studs (300, never under 61). Loop-race and circuit gates ignore every jump longer than 60 studs, so the hops never count a gate. A Street Race checkpoint (26 studs from the path between samples) is not protected, so teleport is refused while a race, sprint, job or circuit session runs (`opts.force = true` to override). The ground is found by raycast and the chassis is put 2.8 studs above it. Streaming is requested around the target. |
| `S.publishPath(name, pts, closed?)` | `workspace` attribute `TK_<name>` = `"x,y,z;..."`. Long paths are chunked automatically. |
| `S.publishCircuit(id)` | `TK_Circuit_<id>` (the compiled centreline, closed), `TK_Pit_<id>` and `TK_Entrance_<id>` |
| `S.publishRouteTo(plr, "bira" \| "central" \| osmId \| index, isOsm?)` | Publishes the GPS route from the car as `TK_Route` |
| `S.setProgress(plr, {Money, Level, EXP, Title, RoadFight})` | Sets progress values |
| `S.setAttribute(plr, name, value)` | Sets a player attribute |
| `S.probePath(pathOrAttr, {every = 25, lateral = 0})` → summary, data | Raycasts along a path on the **server**, where every part exists. Client probes only see what is streamed in. |
| `S.startEvent(kind, lead)`, `S.setTime(21)` | Forces an event / locks the clock (`S.setTime(nil)` to run) |
| `S.report(plr?)` | Car, network owner, Anchored, leaderstats and mode attributes for each player |

**`TK.report()` example (format):**

```
car RaceCar_hatch Street PI 483 at (20412, 3.8, -1530) v=140 up=1.00
Level=3 Money=833 EXP=12 RaceState=finished RaceLastTime=94.63
LastReward: +833 ฿  +265 EXP  (Central Loop - new best)
lap: done(end) 100% s=13601/13601 t=97.1s v=0 vmax=140 | probes 194 road 192 off 2 [(car) 2, Junction 40, Road 152] | dev max 0.0 up min 1.00 | last: [97.1] stop: end
events: NitroBonus 45, attr 61, out 0
12.0 ChallengeMsg msg Finished 1st - waiting for the others
fps heartbeat 60 render 15
```

## Copy-paste tests

Each block assumes the start lines above have run (`S` on the server, `TK` on the client). Expected results are
the ones in RACING_ROUTE_DESIGN.md / CIRCUIT_RACE_SYSTEM.md "Tested".

### Central Loop, 2 laps (CFrame mode, road probes)

```lua
-- server: nearest free car to the spawn = a Pattaya grid car (two cars are called RaceCar_hatch: RaceMap + Pattaya)
print(S.seat(S.player()))
-- client
local h = TK.lapCircuit("RacePath", 2, {physics = false, speed = 140})
-- later
print(TK.report())   -- expect RaceState=finished, about 94.6 s, the "Central Loop" reward, probes all road but (car)
```

### Street Sprint

```lua
local h = TK.followRoute("SprintUpdate", {speed = 140, trigger = function() TK.fire("RequestSprint") end})
-- later: print(TK.report())  -> SprintUpdate finish, "Street Sprint" reward
```

### Teleport cheat (sprint)

```lua
local rec = TK.hookRemotes()
TK.fire("RequestSprint")
local cps = rec:wait("SprintUpdate", "start", 5)[2].checkpoints
TK.jumpTo(cps[1] + Vector3.new(0, 3, 0)) task.wait(0.3)
TK.jumpTo(cps[2] + Vector3.new(0, 3, 0)) task.wait(0.5)
print(rec:dump(3, "SprintUpdate"))   -- expect: stop Run invalid (moved too fast)
```

### Taxi / delivery jobs (with a staged knock)

```lua
for _, m in workspace.PattayaWorld.JobStands:GetChildren() do print(m.Name, m:GetAttribute("Kind"), m:GetAttribute("Label")) end
local stand = workspace.PattayaWorld.JobStands:FindFirstChild("<stand id>")
print(TK.teleport(stand.Ring.Position))
local h = TK.followRoute("JobUpdate", {speed = 140, stalls = {{at = 600, time = 0.4}},
	trigger = function() TK.fire("RequestJob", stand.Name) end})
-- later: print(TK.report())  -> JobUpdate bump 1, finish, fare x 0.88 + tip
```

Variants:
- **Refused from 80 studs:** `TK.teleport(stand.Ring.Position + Vector3.new(80, 0, 0))`, then `TK.fire("RequestJob", stand.Name)`.
  Expect no `JobUpdate` and `JobActive` not set.
- **Cancel:** `TK.fire("CancelJob")`.
- **Time out:** start a job and don't drive.
- **Braking without a knock:** pass `speed = function(h) return if h.s > 500 then 0 else 140 end` and `accel = 300`.

### Traffic and near misses

```lua
TK.ghostTraffic(true)        -- for long drives (the GPS drive test ran with traffic non-solid)
TK.fire("NearMiss")          -- server sanity check: only counts in a car at 60+ studs/s, at most one per 0.6 s
print(TK.recorder:count("NitroBonus"), game.Players.LocalPlayer:GetAttribute("NearMissCombo"))
```

### Street Challenge vs the AI (win at 150, lose at 70)

```lua
local h = TK.followRoute("SprintUpdate", {speed = 150, trigger = function() TK.fire("ChallengeRequest") end})
-- the drive waits for GO (payload.start) and while the car is held anchored
-- later: print(TK.report())  -> "YOU WIN!" (length/15 + 100)  /  at 70: "2nd place"
```

**Two players** (Test → Clients and Servers): Player1 runs the block above. On Player2's client:
`TK.fire("ChallengeReply", true)`, then `TK.followRoute("SprintUpdate", {useLast = true, speed = 120})`.

### Road Fight (lock, win, lose, rematch, titles)

```lua
-- server (optional): S.setProgress(S.player(), {RoadFight = 0, Title = ""})
local bosses = workspace.PattayaWorld.RoadFight:GetChildren()
table.sort(bosses, function(a, b) return a:GetAttribute("Order") < b:GetAttribute("Order") end)
local b = bosses[1]                                  -- 1 South, 2 Central, 3 North, 4 King
print(TK.teleport(b.Ring.Position))
local h = TK.followRoute("SprintUpdate", {speed = 150, trigger = function() TK.fire("RoadFightRequest", b.Name) end})
```

- Locked check: use `bosses[2]` first. Expect `ChallengeMsg msg Locked: beat ...` in `TK.recorder:dump(5)`.
- The King needs nitro speed: use `speed = 205`.

### Night Run / Day Run

```lua
-- server
S.setTime(21) print(S.startEvent("nightrun", 20))
-- client (within 1,500 studs of the ring; else first TK.teleport(game.ReplicatedStorage.PattayaEvent:GetAttribute("RingPos")))
task.wait(1) TK.fire("EventJoin")
local auto = TK.autoFollow("SprintUpdate", {speed = 150})
-- later: print(TK.report())  -> "NIGHT RUN WINNER!", the event reward, EventActive cleared
```

- **Day Run:** `S.setTime(12)` first.
- **Nobody joined:** skip `EventJoin`.

### Survival (all rounds)

```lua
-- server
print(S.startEvent("survival", 20))
-- client
task.wait(1) TK.fire("EventJoin")
local auto = TK.autoFollow("SprintUpdate", {speed = 150})   -- drives every round's route
-- later: print(TK.report()); print(S.report())   -> Equalised/SpeedCap during rounds, "LAST DRIVER STANDING"
-- auto:stop() when done
```

The car is capped at 150 by CarController (`SpeedCap`). The autopilot still sets the speed you ask for, so use
`speed = 140` to keep it realistic.

### Garage (buy, upgrade limit, spawn)

```lua
-- server
print(S.setProgress(S.player(), {Money = 90000, Level = 12}))
-- client (in a car)
print(TK.teleport(workspace.PattayaGarage.Ring.Position))
print(TK.invoke("GarageRequest", "buy", "supercar").msg)
for i = 1, 3 do print(TK.invoke("GarageRequest", "upgrade", "supercar", "engine").msg) task.wait(0.4) end
print(TK.invoke("GarageRequest", "spawn").msg)      -- personal car in a bay; auto-seated only from foot or your own car
```

### Circuit: travel and Time Attack (test oval)

```lua
-- server
print(S.publishCircuit("test_oval"))
-- client (in a car)
TK.fire("CircuitRequest", "travel", "test_oval") task.wait(2)
TK.fire("CircuitRequest", "join", {mode = "TimeAttack", circuit = "test_oval"}) task.wait(1.5)
local h = TK.lapCircuit("TK_Circuit_test_oval", 3, {speed = 95})   -- out of the pits, then 3 timed laps
-- later
print(TK.recorder:dump(10, function(e) return e.kind == "lap" or e.kind == "sector" end))
```

### Circuit rules: track limits, wrong way, reset, leave

```lua
-- 1.3 s off the track, in the middle of a lap
local h = TK.lapCircuit("TK_Circuit_test_oval", 1, {speed = 80,
	lateral = function(h) return if h.s > 500 and h.s < 640 then 45 else 0 end})
-- wrong way: drive 120 studs backwards along the car's heading (on a straight)
local c = TK.car() TK.drivePath({c.Position, c.Position - c.CFrame.LookVector * 120}, {speed = 50})
-- reset / leave
TK.fire("CircuitRequest", "reset")
TK.fire("CircuitRequest", "leave")
print(TK.recorder:dump(8))   -- warn TRACK LIMITS / invalid, attr CircuitWrongWay=true, warn reset, CollisionGroup restored
```

### Circuit race, solo, 3 laps (lights, jump-start fix)

```lua
local P = game.Players.LocalPlayer
TK.fire("CircuitRequest", "join", {mode = "CircuitRace", circuit = "test_oval", laps = 3})
task.spawn(function()   -- after the 25 s forming the car is put on the grid; start the drive at lights out
	repeat task.wait(0.25) until P:GetAttribute("CircuitState") == "StartLights"
	TK.lapCircuit("TK_Circuit_test_oval", 3, {speed = 95, name = "race",
		startWhen = function() return P:GetAttribute("CircuitState") == "Racing" end})
end)
-- later: print(TK.report())  -> no "JUMP START" this time (fix re-test), results row, reward
```

### Circuit race with the grid ahead of the line (out lap, U1)

Only for a circuit whose `grid` sits past the start/finish line (Bira and the fallback grid are behind it, so they
must behave exactly as before: lap 1 timed from lights out). With such a circuit `<id>`:

```lua
local P = game.Players.LocalPlayer
local rec = TK.hookRemotes()
TK.fire("CircuitRequest", "join", {mode = "CircuitRace", circuit = "<id>", laps = 2})
task.spawn(function()
	repeat task.wait(0.25) until P:GetAttribute("CircuitState") == "StartLights"
	TK.lapCircuit("TK_Circuit_<id>", 2, {speed = 95, name = "race",
		startWhen = function() return P:GetAttribute("CircuitState") == "Racing" end})
end)
-- later
print(rec:count("CircuitMsg", "lap"))   -- expect 2: the grid-to-line segment is not a lap
print(rec:dump(10, function(e) return e.kind == "lap" end))   -- both laps full length, no partial-lap PB/record
```

Expect `CircuitLap` = 0 (HUD "OUT LAP") from lights out until the first line crossing, then 1, 2. Penalties
(cuts, track limits, pit speeding) and the teleport DQ still apply on the out lap.

### Bira: physics laps and a pit lap

```lua
-- server
print(S.publishCircuit("bira"))
-- client
TK.fire("CircuitRequest", "travel", "bira") task.wait(3)
TK.fire("CircuitRequest", "join", {mode = "TimeAttack", circuit = "bira"}) task.wait(2)
local h = TK.lapCircuit("TK_Circuit_bira", 2, {speed = 95})              -- out lap + 2 laps (92.01 s each before)
-- pit lap on the next run:
-- TK.lapCircuit("TK_Circuit_bira", 1, {speed = 95, pitOnLap = 1, pitSpeed = 48})
```

`h.stats.minUp` (0.99 before) and `h.stats.maxDev` are in `h:poll()`.

### GPS drive to Bira, and corridor road probes

```lua
-- server: probe the whole route on the server (streaming does not matter there)
print(S.publishRouteTo(S.player(), "bira"))
print(S.probePath("TK_Route", {every = 25}))       -- 1,385/1,385 road before
-- client
TK.ghostTraffic(true)
local h = TK.followRoute("GPSUpdate", {physics = true, speed = 140,
	trigger = function() TK.fire("GPSRequest", "bira") end})
-- later: print(TK.report())  -> GPSUpdate arrived "Bira Circuit"; probes all road; up min 0.99
```

### Track geometry probes (server)

```lua
print(S.publishCircuit("bira"))
print(S.probePath("TK_Circuit_bira", {every = 4}))
print(S.probePath("TK_Circuit_bira", {every = 4, lateral = 18}))    -- right edge (use the track's half width)
print(S.probePath("TK_Circuit_bira", {every = 4, lateral = -18}))   -- left edge
```

### FPS

`TK.report()` ends with `fps heartbeat N render M`. Render runs at about 15/s while Studio is not the focused
window (seen in the Bira test), so only a focused run measures render FPS.

## Notes and limits

**CFrame mode:**
- It moves the car through anything, which is fine for routes on roads.
- The first leg of a sprint, from the car to the route's first junction, can cut a corner through a building.

**Physics mode:**
- The car really collides.
- Use `TK.ghostTraffic(true)` for long drives.
- Stuck cars are logged ("stuck at ...") after 3 s.

**Probes:**
- Client probes exclude the car, the character and `workspace.PattayaTraffic`.
- A probe that hits a parked race car is counted as `(car)`.
- Road part names counted as road: Road, Junction, Dash, Centre, Asphalt, PitLane, TransitionRoad, ServiceRoad,
  Parking, EdgeLine, PitLine and Curb*.
- A Sidewalk hit counts as off-road, as in the wide-world probe numbers.

**Recorder:**
- `rec:dump()` hides the noisy kinds (standings, tower, CircuitPos/Gap/Count, ...). `rec:dump(n, "RemoteName")`
  shows everything for one remote.

**Clean up:** `TK.stopAll()`, `TK.recorder:stop()` and `TK.ghostTraffic(false)`.
