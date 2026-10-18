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

## Not fixed: uncertain, or a gameplay rule to decide (file:line on this branch)

| # | Where | Severity | Finding |
|---|---|---|---|
| U1 | `ServerStorage/RaceSessionService.luau:999-1003` with `:734` | medium | A race grid ahead of the start line arms the tracker and times lap 1 from lights out to the first line crossing. That is a partial lap, but it is `valid` and goes to `Leaderboard.submit`, so it can become a PB or "track record" that is shorter than a real lap. Bira's grid is behind the line, so this does not happen today. It would happen with a circuit whose grid sits past the line. Suggest: no bests from lap 1 when `armAt` was used. This is a rule decision. |
| U2 | `ServerScriptService/PattayaChallengeServer.server.luau:216` | medium | "Road Fighter" is only given when the title is empty. A player who won Survival first (title "Survivor", `PattayaEventsServer:487`) never gets Road Fighter. The Road King still overrides. This is probably not intended, but titles are a gameplay rule. |
| U3 | `ServerStorage/PattayaProgress.luau:58,99,164` | medium (real servers) | Three issues: no session locking (`SetAsync`, not `UpdateAsync` with a session id), so a fast rejoin on another server can load the old record and later overwrite newer data; no periodic autosave, so a server crash loses the session; `BindToClose` saves players one by one, and many players can run out of the 30 s close budget. |
| U4 | `ServerStorage/PattayaStreetRace.luau:415` (`knockOut`) | low | Calls `FireClient` on a player who already left the game (`not p.plr.Parent`). It is not clear whether this throws. If it does, the error aborts that Heartbeat pass for every race once. `p.out` is set first, so it does not repeat. |
| U5 | `ServerScriptService/PattayaJobsServer.server.luau:132-145`, `PattayaSprintServer.server.luau:47` | low | No rate limit. Every refused or failed request still runs Dijkstra over about 3,000 nodes (plus 25 `nearestNode` scans for jobs). A spamming client costs server CPU. ChallengeRequest has a 3 s limit and CircuitRequest 0.2 s. |
| U6 | `ServerScriptService/RaceCarServer.server.luau:118` | low/medium (StreamingEnabled is on) | Race car models use the default streaming mode, not Atomic like the AI bots. A car only partly streamed in (for example a wheel part missing) makes `CarController.enter` return early, so the car can't be driven until the player sits again. Setting `ModelStreamingMode = Atomic` in `buildCar` looks safe but has not been tested. |
| U7 | `ServerScriptService/PattayaGarageServer.server.luau:196`, `PattayaRaceServer.server.luau:91` | low | Both have their own busy checks that ignore `CircuitActive`; `Route.busy` covers it. The circuits are far from the garage and gate 1, so this is harmless today. |
| U8 | `ServerStorage/LeaderboardService.luau:216,225` | low | `Leaderboard.friends` can make up to 100 `IsFriendsWith` web calls per request on a cold cache (cached 10 min). CircuitServer allows one request per 0.2 s per player. This could hit HTTP limits with many players. |
| U9 | `StarterPlayerScripts/CarController.client.luau:140,218` | info | Known and documented: `SpeedCap` / `Equalised` and the R reset are client-trusted. The servers keep a 260 studs/s teleport check, but that does not catch a 160 → 215 overspeed in an equalised event. |
| U10 | `ServerScriptService/PattayaJobsServer.server.luau:190` | info | Known: NearMiss is client-reported. The server only checks that the car is moving at 60+ studs/s and enforces a 0.6 s cooldown, which is worth about 26 nitro/s and 5 ฿ tips. |
| U11 | `ServerStorage/PattayaStreetRace.luau:90-92` | info | Known: `botModel` can clone any free race car, including another player's personal car (the copy has no seat). |
| U12 | `docs/PROJECT_STATUS.md` | info | The phase table appears three times (two older copies are appended). This is a docs-only problem. |

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
