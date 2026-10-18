# Circuit race system (Phase F/G/I)

A data-driven circuit racing system for MIDNIGHT PATTAYA. It is not tied to Bira. Any circuit definition in
`ServerStorage.PattayaData.circuits` gets the following:

- lap timing with sectors, judged on the server
- hidden checkpoint validation: order, cuts, track limits, wrong way, teleports
- a pit lane with a speed limit
- a start procedure with five red lights
- races with results and rewards
- open practice, Time Attack and Track Day sessions
- private rooms
- personal, global and friends lap records
- reset to the last checkpoint
- a simple spectator camera

**Status: written, never playtested.** Only the logic below was run. It ran in an offline Luau harness with mocked
Roblox APIs (see "Offline check"), not in Studio.

## Files and Studio install

| Repo file | Studio location | Type |
|---|---|---|
| `roblox/src/ServerStorage/CircuitRegistry.luau` | `ServerStorage.CircuitRegistry` | ModuleScript |
| `roblox/src/ServerStorage/CheckpointValidator.luau` | `ServerStorage.CheckpointValidator` | ModuleScript |
| `roblox/src/ServerStorage/LapTimingService.luau` | `ServerStorage.LapTimingService` | ModuleScript |
| `roblox/src/ServerStorage/LeaderboardService.luau` | `ServerStorage.LeaderboardService` | ModuleScript |
| `roblox/src/ServerStorage/RaceSessionService.luau` | `ServerStorage.RaceSessionService` | ModuleScript |
| `roblox/src/ServerStorage/CircuitTestTrack.luau` | `ServerStorage.CircuitTestTrack` | ModuleScript (test helper) |
| `roblox/src/ServerScriptService/CircuitServer.server.luau` | `ServerScriptService.CircuitServer` | Script |
| `roblox/src/StarterPlayer/StarterPlayerScripts/CircuitRaceClient.client.luau` | `StarterPlayer.StarterPlayerScripts.CircuitRaceClient` | LocalScript |
| `roblox/data/circuits/test_oval.luau` | `ServerStorage.PattayaData.circuits.test_oval` (create the Folder `circuits`) | ModuleScript (fixture) |
| `roblox/src/ServerStorage/PattayaProgress.luau` (changed) | `ServerStorage.PattayaProgress` | ModuleScript: adds `GetData`/`SetData` |
| `roblox/src/ServerStorage/PattayaRoute.luau` (changed) | `ServerStorage.PattayaRoute` | ModuleScript: `busy()` also checks `CircuitActive` |

You need to make one edit by hand, in `PattayaRaceClient`: the loop-race panel must also hide during circuit
sessions. Change this line:

```lua
panel.Visible = state == "racing" or not (player:GetAttribute("SprintActive") or player:GetAttribute("JobActive"))
```

to:

```lua
panel.Visible = state == "racing" or not (player:GetAttribute("SprintActive") or player:GetAttribute("JobActive") or player:GetAttribute("CircuitActive"))
```

`CircuitServer` does nothing unless `ServerStorage.PattayaData.circuits` exists. It also needs
`PattayaData.graph`, because it requires `PattayaRoute` for `carOf`/`busy`.

The real Bira track comes from the geometry teammate's CircuitBuilder (the surface) and `circuits.bira` (the data).
Once that module is in the folder, it loads without any code change.

## Architecture

```
PattayaData.circuits.<id> (data) --> CircuitRegistry.compile --> circuit {pts, cum, len, gates, sectorS, grid, pit, entrance}
                                                                   |
CircuitServer (remotes, paddock markers, test surface) ---> RaceSessionService (sessions, Heartbeat loop)
                                                              |-- CheckpointValidator.new(circuit)  one per driver: events
                                                              |-- LapTimingService.new()            one per driver: laps/sectors
                                                              |-- LeaderboardService                PB / global / friends
                                                              '-- PattayaProgress.Award             money / EXP
CircuitRaceClient <-- Player attributes Circuit* + CircuitMsg events ;  CircuitRequest --> server
```

- **CircuitRegistry** prepares each circuit:
  - Re-indexes the centerline so point 1 is the start/finish line, and works out the cumulative arc length.
  - Places gates about every 90 studs. Each sector is split evenly, so the start/finish line and both sector lines
    are exactly gates. Gate fields: `line` 1/2/3 marks the start/finish and the two sector lines.
  - Marks the gates the pit lane bypasses (`inBypass`) and where the pit lane crosses each one (`pitLat`).
  - Adds the pit entry and exit gates.
  - Answers `nearest(pos)` (arc length, signed lateral offset, width there), `pointAt(s)` and `at(pos)` (which
    circuit a position is at).
- **CheckpointValidator** judges a single car from its replicated chassis position. It returns events: `gate`,
  `teleport`, `offTrack`, `trackLimit`, `cut`, `wrongWay`, `pit`, `pitSpeed`, `pitPenalty`.
- **LapTimingService** turns gate events into sector and lap times. Crossing times are interpolated between samples
  on the server clock. It also picks the split colours.
- **LeaderboardService** keeps the records (see "Records").
- **RaceSessionService** runs sessions, modes, the start procedure, penalties, standings, gaps, results, reset,
  spectating, travel, ghost mode, class filters, Ranked interfaces and future hooks.

## Session state machine

Each circuit has two session slots:

- **open**: FreePractice, TimeAttack or TrackDay. Only one mode runs at a time.
- **formal**: CircuitRace or PrivateRoom.

```
formal:  Idle -> Forming -> Grid -> StartLights -> Racing -> Finishing -> Results -> Idle
open:    Idle -> Racing (rolling laps) -> Idle (when the last driver leaves)
```

- **Forming**: anyone at the circuit can join a public race for 25 s. In a private room, only the owner and invited
  players can join, and it lasts until the owner presses START. An idle room closes after 10 min.
- **Grid** (3 s):
  - Drivers without a car are dropped, and so are cars whose class is not allowed.
  - Any open session on this circuit is closed, and its drivers are moved to the paddock.
  - The grid order is join order, or personal best (`gridBy = "pb"`).
  - Cars are anchored on their slots.
- **StartLights**:
  - Cars are released.
  - The five red lights come on 1 s apart. After the fifth, there is a random 0.5–2 s hold, then the lights go out.
    The client only learns the moment the lights go out from the `lightsOut` event.
  - Jump start: moving more than 4 studs from the slot before the lights go out costs +5 s.
- **Racing**:
  - If the grid is behind the line, the first line crossing starts lap 1. Lap 1 is timed from lights out.
  - If the grid is ahead of the line, lap 1 starts at lights out (`armAt`).
- **Finishing**: once the winner crosses the line, everyone else has 60 s, then they are DNF. There is also a
  safety time limit of `laps × length / 30 + 120` s.
- **Results** (12 s): finishers are sorted by time plus penalties, then DNFs by progress. Rewards are paid.

## Modes

| Mode | Collisions | Timing | Records | Pay |
|---|---|---|---|---|
| FreePractice | ghost | optional (`timing = false`) | PB | EXP length/160 per valid lap |
| TimeAttack | ghost | sectors, PB, global | PB + global (OrderedDataStore) | length/60 ฿ + length/80 EXP per valid lap, +100 PB, +250 record |
| TrackDay | on | everyone timed, live tower | PB | as Time Attack |
| CircuitRace | on | laps, sectors, gaps | PB | P1: L×laps/20 + 80×(n−1) ฿, L×laps/40 EXP; others: L×laps/40 ฿, L×laps/60 EXP; DNF: 0 |
| PrivateRoom | owner chooses | as race | PB | EXP only (no money, so solo rooms can't be farmed) |

- Laps can be 3, 5 or 10 from the menu buttons, or any custom number from 1 to 20.
- Allowed classes come from the car model attribute `Class` ("Street", "Sport", "Super", "Hyper", "Track Spec").
  A missing attribute counts as "Street".
- No mode requires upgrades.
- **Ghost mode** is the CollisionGroup `CircuitGhost`, which does not collide with itself. It is set on every
  BasePart of the car and of the seated driver's character, and restored when the driver leaves.
  - Ghost cars still collide with the track and with non-session cars (group `Default`).
  - CarController's wheel raycasts may still land on another ghost car: they use the default raycast collision
    group, which collides with `CircuitGhost`.

## Rules and validation (all on the server)

**Gates**
- A gate counts when the path between two Heartbeat samples crosses the gate plane going forwards. This is
  edge-triggered, the same idea as the loop race.
- The crossing must be within the track half width + 10 studs. For a gate the pit lane bypasses, it can instead be
  within the pit lane at `pitLat`.
- Gates must be passed in order. A tracker is unarmed (out lap) until the first start/finish crossing.

**Lap validity.** A lap counts for bests and records only if all of these hold:
- All gates were passed in order.
- No teleport.
- No track-limit violation and no cut.
- No reset.
- No pit-lane speeding penalty.
- No wrong way.

Invalid laps are still shown, with a red split and "INVALID".

**Missed gate (cut):** crossing a gate up to 4 ahead of the expected one re-syncs the tracker, and the skipped
gates count as missed.

**Teleport:** more than 260 studs/s over a 0.25 s window. A single jump over 60 studs between samples is never
counted as a crossing.

**Track limits:** the chassis centre is more than `width/2 + 6` from the centerline, outside the pit lane, for
more than 1 s.

**Cut:** an off-track excursion that gains more centerline progress than the distance driven while off
(× 1.05 + 8 studs, and more than 20 studs).

**Wrong way:** centerline progress goes back more than 30 studs.

**Penalties in races:**

| Offence | Penalty |
|---|---|
| Jump start | +5 s |
| Cut or missed gate | +3 s, at most once per lap |
| Track limits | 2 warnings, then +5 s each |
| Pit-lane speeding | +5 s |
| Teleport | disqualified (DNF) |

In open sessions the same offences only invalidate the lap.

**Pit lane:**
- Crossing the pit entry gate starts pit mode, and the exit gate ends it.
  - Both gates sit where the pit lane is more than track half width + pit half width + 8 from the centerline, so a
    car running wide on the track can't trip them.
- In pit mode, speed above `pitSpeedLimit + 3` gives a warning. Being over it for more than 1.5 s in total during
  one visit gives a penalty.
- A lap through the pits still counts:
  - Bypassed gates also count inside the pit lane.
  - Gates the pit lane never crosses are skipped silently in pit mode.
- Open sessions start the car in the pit lane, 40 studs before the exit, with pit mode on.

**Reset:** press **T** (DPadDown on a gamepad).
- The server anchors the car, moves it with `Model:PivotTo` to the last gate passed, facing the driving direction,
  and then calls `SetNetworkOwner(driver)`.
- Before the first gate, or while in the pit lane, it uses the nearest centerline point instead.
- There is a 3 s cooldown, and the current lap becomes invalid.
- CarController's own R (flip in place) is unchanged.

## Records (LeaderboardService)

**Personal best:**
- Saved with the player's progress record, through `Progress.GetData`/`SetData`. The key is `circuitPB` and the
  value is `{[id] = {lap, s = {s1, s2, s3}, car, class, at}}`.
- Old records `{level, money, exp, title, roadFight}` still load. The new field is `data`.

**Global best:**
- Stored in the OrderedDataStore `CircuitBest_<id>`. The key is `u<userId>` and the value is the lap in ms.
  `UpdateAsync` keeps the faster lap.
- Only Time Attack personal bests are written.
- The top 100 are read ascending, every 60 s at most.
- Every call is in `pcall`. When the store is unavailable (for example Studio without API access), the board uses
  this server's session memory, and the store is retried after 5 minutes.

**Friends:**
- Filtered from the global top 100 plus this server's session times, using `plr:IsFriendsWith` (in `pcall`, cached
  for 10 min).
- Limit: friends who are outside the top 100 and not on this server are not shown.

**Purple (overall best):**
- Lap: the best of the global top 1 and this session.
- Sectors: this server's best sectors. Sector times are not stored in the OrderedDataStore.

**Split colours:**

| Colour | Meaning |
|---|---|
| Purple | Overall best |
| Green | Your personal best (the saved PB lap's sectors, or better ones this session) |
| Yellow | Slower |
| Red | The lap is already invalid |

## Data interface (what a circuit module returns)

```lua
{ id, name, lengthStuds,
  centerline = {x1,y1,z1, ...},     -- world studs, closed loop, driving direction, ~4-6 studs apart, y = surface
  width = {w...} | trackWidth = n,  -- per point or one value (default 40)
  startFinish = {index = i}, sectors = {i1, i2},     -- centerline indices (sectors default to thirds)
  grid = {{x,y,z,dx,dz}, ...},      -- >= 12 slots, y = surface height (car is placed 2.8 above)
  pitLane = {x,y,z,...}, pitEntryIndex, pitExitIndex, pitSpeedLimit,   -- studs/s (default 60)
  pitWidth = 20,                    -- optional
  entrance = {x, z, dx, dz [, y]},  -- paddock: marker + menu prompt, travel destination
  curbs, brakeMarkers, buildings, parking,          -- ignored by the race logic
  defaultLaps = 3,                  -- optional, menu default
  testSurface = true }              -- optional: CircuitServer builds CircuitTestTrack when workspace.Circuits.<id> is missing
```

The geometry teammate's builder should put its models in `workspace.Circuits.<id>`. When that folder exists,
the test surface is never built.

## Remotes and attributes

The remotes are in `ReplicatedStorage.PattayaRemotes` and are created with the same `remote()` helper as the other
servers.

**`CircuitRequest` (client → server):** `(action, arg, arg2)`. Requests are rate-limited to one every 0.2 s.

| Action | Argument |
|---|---|
| `menu` | |
| `join` | `{mode, circuit, laps, gridBy, collisions, classes, timing, join}` |
| `leave` | |
| `reset` | |
| `start` | (room owner only) |
| `invite` | `userId` |
| `spectate` | `circuitId`, `targetUserId?` |
| `unspectate` | |
| `travel` | `circuitId` |
| `friends` | `circuitId` |

**`CircuitMsg` (server → client):** `menu`, `toast`, `warn {kind, text}`, `sector {n, time, colour}`,
`lap {lap, time, valid, colour, pb, sectors, reason}`, `lights {at, interval, count}`, `lightsOut {at}`,
`tower {mode, rows}`, `results {name, mode, laps, rows, bestLap}`, `spectate {…}|nil`, `invite {…}`,
`friends {circuit, rows}`.

**Player attributes:** `CircuitActive`, `CircuitId`, `CircuitName`, `CircuitMode`, `CircuitState`, `CircuitLap`,
`CircuitLaps`, `CircuitLapStart`, `CircuitLastLap`, `CircuitBestLap`, `CircuitPB`, `CircuitLapValid`,
`CircuitPos`, `CircuitCount`, `CircuitGap`, `CircuitPit`, `CircuitPitLimit`, `CircuitOff`, `CircuitWrongWay`,
`CircuitPenalty`, `CircuitFormEnds`, `CircuitFinished`, `CircuitOwner`.

`CircuitActive` blocks the other modes through `PattayaRoute.busy`. Joining a session is refused while
`RaceState`, `SprintActive` or `JobActive` is set.

## Client (CircuitRaceClient)

**Keys:**

| Key | Action |
|---|---|
| **P** (CIRCUIT button on mobile) | Menu |
| F at the paddock | Opens the same menu (ProximityPrompt) |
| **T** | Reset |
| Z / X | Switch car while spectating |
| B | Stop spectating |

**Menu:**
- Away from a circuit, it offers "Travel: <circuit>". This needs a car: the server moves it to the paddock after
  requesting streaming around the paddock.
- At a circuit, it offers:
  - Time Attack, Free Practice (timing on or off) and Track Day
  - a public race: laps 3/5/10/±1, grid order
  - a private room: collisions, allowed class
  - join or spectate the current session
  - the top 5 lap records and your PB
  - the friends board

**HUD (top left):**
- circuit and mode
- LAP x/y, or OUT LAP / LAP n in open sessions
- the current lap time (red with an X when the lap is invalid), LAST, BEST and PB
- position and gap to the car ahead (time difference at the same gate), plus penalties
- the three coloured sector boxes

**Other screen elements:**
- A timing tower below the HUD.
- Five start lights, then GO.
- A results table.
- Warnings in the middle of the screen: flashing WRONG WAY, PIT LANE speed/limit (red when over), TRACK LIMITS,
  and penalty or invalid-lap toasts.

The UI is original and says "MIDNIGHT PATTAYA". It uses no RayCity assets.

## Implemented vs prepared

**Implemented:**
- all five modes
- the formal state machine
- start lights and the jump start rule
- penalties
- the pit lane limiter
- reset
- ghost mode
- the class filter
- PB, global and friends boards with the session fallback
- standings and gaps
- results and rewards
- private room invites and spectators
- travel to the paddock
- the simple spectator camera (server `ReplicationFocus` + client `CameraSubject`)

**Prepared (interfaces only):**
- `RaceSessionService.Ranked`: `enabled = false`, `ratingKey = "circuitRating"`, `defaultRating`, `bucketOf(class)`,
  `validate(session, rows)`, `apply(session, rows)`. These are called at results when enabled.
- `RaceSessionService.hooks`: `onState`, `onGate`, `onLap`, `onIncident`, `onResults`. Future systems subscribe
  here:
  - yellow/blue flags (from `onIncident` and the gaps)
  - safety car
  - tyre wear and fuel (per-lap `onLap`)
  - damage
  - replay and ghost car (record `onGate` times and positions)
  - AI drivers (the Street Challenge bot profile can follow `circuit.pts`)
  - marshals
  - TV-style spectator cameras

**Not built:**
- AI on circuits
- drive-through penalties (time penalties only)
- sharing one track between two open modes at the same time
- auto-moving spectators from an open session to a race

## Offline check (not a playtest)

`CircuitRegistry`, `CheckpointValidator`, `LapTimingService`, `LeaderboardService` and `RaceSessionService` were
run with the `luau` CLI. Vector3, CFrame, Players, DataStore and time were mocked, and a scripted "car" followed the
fixture centerline. All files compile with `luau-compile`. Results on `test_oval`:

**Fixture geometry:**
- 300 points, 1,565.6 studs, 17 gates.
- Sector lines at 548.7 and 1,017.0 studs.
- The pit lane is 395 studs long and bypasses gates 16, 17, 1, 2 and 3. The start/finish gate is crossed by the
  pit lane at lateral −45.

**Validator and timing:**
- Clean laps at 150 studs/s: 10.438 s each (length/150 = 10.438).
- A lap through the pits at 55 studs/s was valid. A lap through the pits at 100 studs/s gave a limiter warning and
  then a penalty.
- Cutting straight through the chicane was caught as cut events and missed gates 9 and 10. The lap was invalid.
- Driving backwards set wrong way on. A 150-stud jump was caught as a teleport.

**Sessions:**
- Race, 2 drivers, 2 laps: Forming 25 s, then Grid, then lights. The lights went out 5.7 s after the first light.
  - Bob's 6-stud creep gave JUMP START +5 s.
  - Results: Alice P1 20.97 s, Bob P2 22.49 s + 5 s.
  - Rewards were paid, and both players were back to free roam after Results.
- Time Attack:
  - The car started in the pit lane with pit mode on, did its out lap, and then a valid lap of 10.438 s (PB and
    record paid).
  - A reset on the next lap made that lap invalid.
  - Leaving the car ended the session. The board fell back to session memory because the DataStore was mocked as
    failing.
- Private room and Track Day:
  - The class filter refused a Street car.
  - An uninvited player was refused, then accepted after an invite.
  - START moved the Track Day driver to the paddock and closed that session.
  - A driver who left the car mid-race became DNF.
  - The room paid EXP only.

## Studio test plan (test fixture)

Install the files listed above. Make sure Game Settings → Security → "Enable Studio Access to API Services" is on
or off as you want: off tests the session fallback. Then press Play.

1. **Load.**
   - Expected: no `[Circuit]` warnings in the output.
   - `workspace.Circuits.test_oval` appears: grass base, dark asphalt oval, lighter pit lane outside the main
     straight, white start/finish stripe, two yellow sector stripes, white grid marks.
   - `workspace.Circuits.Paddock_test_oval` appears: cyan ring and pole with the "Test Oval PADDOCK (P)" sign, about
     95 studs outside the main straight (around world 60000, 59794).
2. **Travel.**
   - In Pattaya, get in a car and press P. Expected: the menu says "You are not at a circuit" and lists
     "Travel: Test Oval (1565 studs)".
   - Click it. Expected: the car lands on the paddock ring facing +X, with the toast "Welcome to the paddock".
   - Pressing P on foot says "Get in a car first".
3. **Time Attack.**
   - Press P (or F at the pole), then choose Time Attack.
   - Expected:
     - The car moves into the pit lane near its exit and becomes ghosted.
     - The HUD shows "TEST OVAL TIMEATTACK", "OUT LAP" and the cyan "PIT LANE xx / 60".
     - Driving faster than 63 gives a "PIT LIMITER" toast.
   - Leave the pits, drive the out lap and cross the start/finish line. Expected: "LAP 1" and the timer running.
   - Expected at each sector line: a coloured box. On the first ever lap all three are purple and the lap flashes
     purple.
   - Complete a clean lap. Expected: a "+… ฿ +… EXP (Test Oval lap … - track record!)" toast, and the LAST/BEST/PB
     lines filled in.
   - The menu now lists your time under LAP RECORDS.
4. **Invalid laps.**
   - On the back straight, drive straight through the chicane. Expected:
     - "TRACK LIMITS" while you are off.
     - "Lap invalid: corner cut" or "missed checkpoint".
     - The current lap timer turns red with an X, the following splits are red, and the lap flashes "INVALID".
   - Stay on the grass for more than 1 s. Expected: "Lap invalid: track limits".
   - Turn around and drive back. Expected: a flashing "WRONG WAY".
5. **Reset.**
   - Mid-lap, press T. Expected: the car is put back on the last gate (at most about 90 studs back), facing the
     driving direction and drivable at once, with the toast "Car reset … lap invalid".
   - Pressing T again within 3 s does nothing.
6. **Pit lap.**
   - Coming out of the last corner onto the main straight, keep left into the pit lane, stay under 60 and rejoin at
     the end of the straight.
   - Expected: "PIT LANE" is shown, and the lap still completes and counts as valid. It is slower, so it shows
     yellow or green.
7. **Leave.**
   - Choose Leave session, or get out of the car. Expected: the HUD disappears and the loop panel is back (with the
     1-line edit). The ghost group is restored: `Chassis.CollisionGroup == "Default"`.
8. **Race (solo is allowed).**
   - At the paddock, open the menu and choose Laps 3, then "Start a public race".
   - Expected:
     - "RACE FORMING - start in N s" counting down from 25.
     - At 0, the car is placed on grid slot 1 and held ("ON THE GRID - hold still").
     - The lights panel lights 5 red lights 1 s apart. After 0.5–2 s they go out and GO! is shown.
   - Creeping forward during the lights. Expected: "JUMP START +5 s" and "PEN +5 s" on the HUD.
   - Expected during and after the laps:
     - Lap 1 is timed from lights out.
     - After 3 laps: "Finished m:ss.sss (+5 s penalties)".
     - The results table appears for 12 s, and the reward is paid (P1/1: L×3/20 ฿).
   - Then everything is back to idle.
9. **Two players** (Test → Clients and Servers, 2 players, both travel to the paddock).
   - Player1 starts a race and Player2 joins from the menu. Expected:
     - Grid slots 1 and 2.
     - Collisions on: the cars can touch.
     - Tower lines "1 Player1 L1 LEADER" and "2 Player2 L1 +0.xxx".
     - P1/P2 and the gap on the HUD.
   - When Player1 finishes, Player2 sees "THE LEADER HAS FINISHED". After 60 s Player2 is DNF if not finished.
   - Spectate: a third client (or Player2 after finishing and leaving) uses P and "Spectate the race". Expected:
     the camera follows the car, Z/X switches car, B stops.
10. **Private room.**
    - Player1 sets class Sport and creates a private room.
    - Expected: refused with "Class Street not allowed" if the car has no `Class` attribute. Set
      `RaceCar_*.Class = "Sport"` in the Explorer to test.
    - Invite Player2. Expected: Player2 sees the purple invite toast and can join, and START begins the grid.
    - With collisions off, the cars pass through each other.
11. **Track Day pre-emption.**
    - Player2 is in Track Day while Player1 starts a race.
    - Expected at grid time: Player2 gets "Session closed: a race is starting. Moved to the paddock."
12. **Regression.**
    - The Central Loop race, Street Sprint (H), Challenge (C) and jobs (E) still work in Pattaya.
    - All of them are refused while `CircuitActive` is true.

## Known risks

- **Network jitter:** all judging uses the server's copy of a client-owned car. Bad latency could trip:
  - the teleport check (it averages over 0.25 s)
  - the 4-stud jump-start rule, if the car settles or rolls on release
- **Server moves of a client-owned car** (grid, pit placement, reset, travel) anchor the car for 0.5 s or until the
  lights. This is the pattern the Street Challenge already uses.
- **Travel streaming:** if streaming is enabled, a car landing 50,000 studs away could fall before the ground streams
  in. `RequestStreamAroundAsync` is called first, but this has not been tried.
- **Ghost raycasts:** CarController's wheel raycasts can hit other ghost cars (see Modes).
- **Track width for track limits:** it uses the centerline width. Wide runoffs that are inside `width` count as
  track. The width data must match the painted edges.
- **Tuning on Bira:** gate lookahead (4 gates, about 360 studs) and lateral margins are tuned on the fixture. Tight
  hairpins on Bira, where two parts of the track are close together, should be checked.
- **Progress API merge:** `Progress.GetData`/`SetData` are added minimally, saved as `data` in the same record. If
  the garage teammate adds the same API, keep one copy. The semantics are identical: a per-player key/value table
  saved on leave.

## Tested by the leader in Studio (2026-10-18)
Autopilot driving the client-owned car; the server judged everything.

**Test oval (fixture):**
- Load: no `[Circuit]` warnings; `workspace.Circuits.test_oval` (338 parts) and `Paddock_test_oval` built.
- Travel from Pattaya: car landed at the paddock, toast "Welcome to the paddock".
- Time Attack: car placed in the pit lane, ghosted (`CollisionGroup = CircuitGhost`), "Out lap" toast. Out lap + 3
  timed laps: 16.27 / 16.21 / 16.22 s, all valid, sector messages with purple/yellow colouring, PB updated, paid.
- Rules: 1.3 s off the track → `CircuitOff=true`, "Lap invalid: track limits"; 20 points backwards →
  `CircuitWrongWay=true`; reset remote moved the car 8 studs back onto the last gate with "Car reset … lap invalid";
  leave restored `CollisionGroup = Default`, cleared `CircuitActive` and showed the loop panel again.
- Circuit Race, solo, 3 laps: "Race forming: 3 laps, starts in 25 s" → "Grid slot 1 of 1" → 5 lights → lights out →
  3 laps → "Finished 0:50.324 (+5 s penalties)" → results row (P1, FIN, 234 ฿ / 117 EXP) → paid, back to idle.
  - **Bug found:** "JUMP START +5 s" fired 1 s before the lights went out although the car was held still. The
    rule measured from the grid slot from the moment of release, when the client-owned car is still settling after
    the server's PivotTo and ownership handoff. Fixed: the reference position is taken 0.75 s after the lights
    start (`JUMP_SETTLE`), then 4 studs of movement is a jump start. **Re-test: still a false penalty.** A
    server-side recorder showed the released car creeping on its own with no input, accelerating from 0.3 to
    1.6 studs/s and covering 5.3 studs over the 5 s of lights (a CarController idle quirk, see below). Second fix:
    the rule is now **ground speed > 10 studs/s before lights out** (`JUMP_SPEED`); idle creep never reaches it, a
    throttle launch passes it within 0.3 s. **Re-tested: a car held still through the lights got penalty 0.**
  - **Known quirk:** a driven car with no input creeps forward at up to ~1.6 studs/s (seen on the flat test oval).
    CarController should brake to a stop when idle; not changed here.

**Bira (real venue, physics-driven lap: the autopilot only set horizontal velocity and yaw, so gravity and the
car's own raycast suspension handled the hills):**
- Bira registered from `PattayaData.circuits.bira`; `Paddock_bira` built; travel worked (car at the entrance,
  y −1.2) and Time Attack placed the car in the pit lane on the hill (y 38).
- Out lap 84 s, then **lap 1 valid: 92.01 s** at 95 studs/s cruising (55–72 in bends), car upright the whole way
  (min UpVector.Y 0.99), no stalls. **Lap 2 valid: 92.01 s.** Two consecutive valid laps, as the acceptance
  criteria require. 16,076 physics samples; the chassis was at most 4.5 studs above the centreline height (its
  ride height plus crests).
- Venue geometry before this: 5,106 raycast probes (centre + both track edges) hit track at every point, mean error
  0.02 studs, max 0.29, max step between points 0.66 — after the run-off fix in `CircuitBuilder` (see
  BIRA_CIRCUIT_DESIGN.md).
- **Pit lap on Bira:** driven round to the pit entry, through the 378-point pit lane at ≤48 studs/s (server showed
  `CircuitPit` from the entry gate to the exit), rejoined and crossed the line: lap valid, 107.77 s. So pit entry and
  exit are usable and a pit lap counts.
- The lap before it (lap 3) was reported invalid for "wrong way": that lap included a two-minute pause on a slope
  between test runs, and the parked car most likely rolled backwards more than 30 studs (`CircuitWrongWay` was
  clear afterwards). Probable cause only, not reproduced.
- **FPS at the venue: not measurable in this session.** Parked at the paddock, `RenderStepped` ran at 15/s while
  `Heartbeat` and physics ran at 61/s: Studio throttles rendering when its window is not in front (the same reason
  the screen captures come back white). Simulation stayed at 60 Hz while driving the whole lap, so the physics cost
  of the 6,079-part venue is fine; render FPS needs a run with Studio focused (owner at the keyboard). The earlier
  Pattaya figure of 60 FPS was taken with Studio focused.
- Not tested: a race on Bira, two players, the drive from the city (the corridor is not yet merged into the road
  graph).
