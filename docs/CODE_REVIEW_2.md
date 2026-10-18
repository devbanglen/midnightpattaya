# Code review 2 (team2/qa, base main 32ff390)

This review covers all Luau in `roblox/src`: ServerScriptService, ServerStorage, StarterPlayerScripts,
ReplicatedStorage and ReplicatedFirst. Nothing was run in Studio.

**Static check:**
- `luau-compile`: all files compile.
- `luau-analyze`, without Roblox type definitions: almost all of its output is "Unknown global / Unknown type" or
  follows from them (`*error-type*`). The real errors were fixed with casts (commit `c12061c`).
- Left as is:
  - lint notes (SameLineStatement, LocalShadow `cf` in RaceCarServer, unused `len` in PattayaRoute)
  - two PattayaProgress errors that come from the missing DataStoreService / Player types

## Fixed in this branch (commit 118c85a, explained line by line there)

| # | File | Severity | Bug | Fix |
|---|---|---|---|---|
| F1 | `ServerStorage/PattayaStreetRace.luau` (startRace / GO / endRace) | high | A driver who gets out during the 3.5 s countdown leaves that car anchored forever. GO and endRace only un-anchored the car the player still sits in. The frozen shared grid car then makes RaceCarServer error for the next driver. | The grid car is kept as `p.chassis`. `releaseCar()` un-anchors it at GO and at the end of the race, and gives ownership to the driver only if they are still seated. |
| F2 | `ServerScriptService/RaceCarServer.server.luau` (Occupant handler) | medium | `SetNetworkOwner` throws on an anchored assembly: exiting on a held grid, or during a circuit reset or travel. | Guarded with `CanSetNetworkOwnership()`. |
| F3 | `ServerStorage/RaceSessionService.luau` `release` / `placeChassis` | low | Network ownership went back to a driver who had already left the car. A walking player's client then simulates the parked car. | The owner is the driver only if they are seated, else the server. |
| F4 | `ServerStorage/RaceSessionService.luau` `newSession` | medium | `laps` = NaN from the client (the join table is client data) passed `math.clamp`. The race never finished, and the safety limit was NaN too, so the circuit's race slot stayed blocked. | NaN or inf fall back to 3. |
| F5 | `ServerStorage/PattayaProgress.luau` | high | PlayerRemoving saved while `setup()` was still inside `GetAsync`. A player who left during the load had their record overwritten with level 1 and ฿0. | Saves wait for a `loaded` flag. State is cleaned up if the player left while loading. Load retries 3 times. Load and save failures are now warned. |
| F6 | `ServerStorage/LeaderboardService.luau` `submit` | medium | A PB lap that started mid-lap (grid ahead of the line) stored `s = {nil, x, y}` inside the progress record. An array with holes may fail to serialise, and that fails the player's whole save. | Sectors are stored only when all three exist. |

## Fixed in team3/review (base main b49d773; each commit message explains the change)

Nothing below was run in Studio. All 40 Luau files compile with `luau-compile`; `luau-analyze` shows no new
errors beyond the missing Roblox type definitions.

| # | Commit | Where | Fix |
|---|---|---|---|
| U1 | `544bc60` | `ServerStorage/RaceSessionService.luau` (`goRacing`, `handle`, `progressOf`) | A grid ahead of the line now runs an **out lap**: the tracker is armed at the grid (gates, limits, cuts, pit speeding and the teleport DQ apply from lights out), but lap 1 only starts at the first line crossing, so the partial segment is never a lap, PB or record. The race is still `laps` full laps; race time runs from lights out. Bira (grid behind the line) is unchanged. Test: TEST_KIT.md "Circuit race with the grid ahead of the line". |
| U2 | `5ff7806` | `ServerStorage/PattayaProgress.luau`, `PattayaChallengeServer`, `PattayaEventsServer` | Every earned title is kept in `extra.titles`; `Progress.GrantTitle(plr, name)`; the `Title` leaderstat shows the best by `Progress.TITLE_RANK` (Road King > Road Fighter > Survivor). The "only if empty" checks are gone. Old `title` strings load into the set, and saved RoadFight bits re-grant Road Fighter / Road King. |
| U3 | `5ff7806`, `9dd588f` | `ServerStorage/PattayaProgress.luau` | Session lock via `UpdateAsync` (`lock = {id, at}`; a foreign lock younger than 5 min is never overwritten; on load it is retried, then load-failed). Autosave every 120 s, non-overlapping saves per player, release on leave, parallel BindToClose (25 s). Studio without API access warns once and plays session-only. Format: RACING_ROUTE_DESIGN.md "Progression". |
| U4 | `9e68d6a` | `PattayaStreetRace` (`fireClient`, used for every send incl. `knockOut`), `PattayaChallengeServer`, `PattayaEventsServer`, `PattayaSprintServer.stop`, `PattayaJobsServer.stop`, `PattayaGPSServer.send` | No `FireClient` to a player whose `Parent` is nil. The Sprint Heartbeat did exactly that (`stop("Left the car")` for `not plr.Parent`). |
| U5 | `9e68d6a` | `PattayaJobsServer`, `PattayaSprintServer`, `PattayaGPSServer` | At most one request per 0.5 s per player (extras dropped); jobs and sprint refuse a request while a route search is marked running for the player (pcall-wrapped). GPS routes are only computed by the one-per-frame Heartbeat. |
| U6 | `681853b` | `ServerScriptService/RaceCarServer.server.luau` `buildCar` | `ModelStreamingMode = Atomic` for every race car, personal garage cars included (same builder). |
| U7 | `21dc645`, `9dd588f` | `PattayaGarageServer` `busy`, `PattayaRaceServer` loop start | Both use `Route.busy` (includes `CircuitActive`), required lazily once `PattayaData.graph` exists, else the same attribute check. |
| U8 | `593b0ae` | `ServerStorage/LeaderboardService.luau` `friends` | At most 25 `IsFriendsWith` web calls per request; cached answers (10 min per player) are free. |
| U11 | `681853b` | `ServerStorage/PattayaStreetRace.luau` `botModel` | Only shared grid cars are cloned; models with an `Owner` attribute are skipped. |
| U12 | `765eeb0` | `docs/PROJECT_STATUS.md` | One phase table; rows only found in the older copies (10f Night Run / Survival, 9 Broader world) kept with their "How tested" text. |
| Creep | `9dc2c50` | `StarterPlayerScripts/CarController.client.luau` | Idle creep (0.3 → 1.6 studs/s on the flat oval): the spring pushed along the chassis up vector, so a slightly pitched chassis got a constant g·sin(pitch) horizontal push, and with zero chassis friction the only resistance was the 0.25/s coast drag. The spring now pushes along the ground normal, and with no input below 3 studs/s an idle hold bleeds the speed at 20/s (capped by the brake). Driving values unchanged. |

## Accepted risks (documented, not changed)

| # | Where | Severity | Finding |
|---|---|---|---|
| U9 | `StarterPlayerScripts/CarController.client.luau` (`SpeedCap` / `Equalised`, R reset) | info | Known and documented: `SpeedCap` / `Equalised` and the R reset are client-trusted. The servers keep a 260 studs/s teleport check, but that does not catch a 160 → 215 overspeed in an equalised event. |
| U10 | `ServerScriptService/PattayaJobsServer.server.luau` (NearMiss) | info | Known: NearMiss is client-reported. The server only checks that the car is moving at 60+ studs/s and enforces a 0.6 s cooldown, which is worth about 26 nitro/s and 5 ฿ tips. |

## Checked and fine

**Remotes and shared state:**
- All servers create remotes with `FindFirstChild(name) or Instance.new` and no yield in between. Luau is
  single-threaded, so two scripts can never create the same remote twice.
- `GarageRequest` is the only RemoteFunction, and it has its own name.
- Mode exclusion works through attributes:
  - `Route.busy` = RaceState racing / SprintActive / JobActive / CircuitActive.
  - Events and StreetRace hold `SprintActive`.
  - Job, sprint and loop-race Heartbeats stop each other on those attributes.
  - Circuit join and travel check `Route.busy`.

**Clocks:**
- Server time sent to clients always uses `workspace:GetServerTimeNow()`: race start, goAt, StartAt, LastRewardAt,
  lights.
- `os.clock()` is only used for local rate limits, caches and GPS refresh. It never crosses the network, and both
  sides use the same clock for invite expiry.

**Per-player tables:** every one is cleared on PlayerRemoving:
- Sprint / Jobs `active`, `nearState`
- Challenge `invites` / `lastRequest`
- GPS `active`
- Garage `personal` / `lastRequest`
- Circuit `lastAt`, `byPlayer` / `spectating` / `lastReset`
- Leaderboard `friendCache`
- Events `joined` / `entrants`
- Loop race `states` / `lastPos`
- Progress `extra` / `loadFailed` (now also `loaded`)

**Remote argument types:**
- Strings are checked (`type(action)`, `type(id)`).
- Table lookups with client keys (`byId[standId]`, `bosses[id]`, `OPEN_MODES[mode]`) are safe for any type.
- `invite` checks `typeof(userId) == "number"`. `join` treats `opts` as a table only if it is one.

**StreamingEnabled:**
- These are Persistent: race checkpoints, job stands, Road Fight rings, event rings, the garage and paddocks.
- Clients use `WaitForChild` with timeouts.
- Server code never depends on streaming.

## Leader's verification after merging team3/review (2026-10-18, Studio Play)
- No script errors with the 14 replaced scripts; race car models are `Atomic`.
- Idle creep: the hatch sat on the flat start grid for 10 s with no input and moved 0.00 studs (max ground speed
  0.01 studs/s); before the fix it drifted ~5 studs in 5 s.
- U5 rate limit: a burst of 10 `RequestSprint` produced exactly one SprintUpdate "start".
- Regression with the test kit: Street Sprint 2,374 studs +198 ฿; Challenge vs AI "Challenge won" +245 ฿
  (= 2,175/15 + 100). `SprintActive` cleared afterwards.
- Not re-tested: U1 (no circuit with a grid ahead of the line exists yet), U2 title ranking, U3 session lock and
  autosave (needs API access / a real server).
