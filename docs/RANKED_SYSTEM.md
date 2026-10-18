# Ranked circuit racing (Phase I)

Ranked play for public circuit races in MIDNIGHT PATTAYA: a rating per car class, seasons, a ranked board per class.
Everything runs on the server and is built from the server's own results rows. The client only draws.

**Status: written, checked offline, never run in Studio.** The rating maths ran in the `luau` CLI
(`RankedRatingTest`: 45/45 checks). The session wiring and the ranked board ran in a mocked offline harness (see
"Offline checks"). No Studio test yet. **Ranked is off by default.**

## Files and Studio install

| Repo file | Studio location | Type |
|---|---|---|
| `roblox/src/ServerStorage/RankedRating.luau` (new) | `ServerStorage.RankedRating` | ModuleScript (pure maths, no Roblox services) |
| `roblox/src/ServerStorage/RankedRatingTest.luau` (new) | `ServerStorage.RankedRatingTest` | ModuleScript (dev only, nothing requires it) |
| `roblox/src/ServerStorage/RaceSessionService.luau` (changed) | `ServerStorage.RaceSessionService` | `Service.Ranked` filled in |
| `roblox/src/ServerStorage/LeaderboardService.luau` (changed) | `ServerStorage.LeaderboardService` | ranked boards |
| `roblox/src/StarterPlayer/StarterPlayerScripts/CircuitRaceClient.client.luau` (changed) | same | RANKED tags, rating on results |
| `tools/offline/*` (new) | not installed | offline mock harness (luau CLI) |

`RaceSessionService` now requires `ServerStorage.RankedRating`, so that module must be installed with it.
`tools/studio/install.ps1` bundles every file in `roblox/src`, so it installs both new modules.

No new remotes. The fields ride on the existing `CircuitMsg` payloads (`menu`, `tower`, `results`).

## Turning it on

Off by default. Either of these turns it on:

- `ServerStorage` attribute `RankedEnabled = true` (for tests, from the server command bar):
  `game.ServerStorage:SetAttribute("RankedEnabled", true)`
- `require(game.ServerStorage.RaceSessionService).Ranked.enabled = true` (module constant, for a release)

It is read when a race is **created**. A race that formed before the switch stays unranked, and one that formed
while it was on stays ranked even if it is turned off.

## What can be ranked

| Mode | Ranked? |
|---|---|
| CircuitRace (public) | yes, when ranked is on (`session.ranked`) |
| PrivateRoom | never (owner-picked field, solo rooms, invite-only) |
| FreePractice / TimeAttack / TrackDay | never (no finishing order) |

A ranked race still pays the normal CircuitRace rewards. Lap timing, validation, penalties and records are unchanged.

## When a ranked race counts (validate)

At results, `Ranked.validate(session, rows)` returns `ok, reason`. When it fails, no rating changes and the results
screen shows `UNRANKED - <reason>`. The race counts only if all of these hold:

| Rule | Reason shown when it fails |
|---|---|
| The session is ranked | (no line: an unranked race shows nothing) |
| At least 2 human drivers (rows with `ai`, `bot` or `ghost` set are not counted; there are no AI rows today) | `needs 2 or more drivers` |
| No driver was disqualified (teleport DQ, `row.dq`) | `a driver was disqualified` |
| Every driver is in the same bucket: the car's `Class`, or `Equalised` when the player has the server-set `Equalised` attribute at lights out | `mixed classes` |
| At least one driver finished | `nobody finished` |
| `laps x lap length >= 3000` studs (`Ranked.minRaceStuds`): the test oval (1,565.6 studs) needs 2+ laps, Bira 1+ | `too short (2+ laps here)` |

Disqualification voids the whole race (`Ranked.voidOnDisqualified = true`). See "Open questions".

The menu and the forming toast already say when a race will be too short: "Start a public race (1 laps, forms 25 s)
unranked: 2+ laps", "Race forming: 1 laps, starts in 25 s - unranked (RANKED needs 2+ laps here)".

## The rating maths (RankedRating)

Elo, extended to a race with many drivers:

1. **Every pair of drivers is one duel.** Ahead = 1, behind = 0. Two DNFs draw (0.5). A DNF always loses to every
   finisher. The order is the server's results order: finishers by time plus penalties, then DNFs.
2. **Expected score** of A against B: `E = 1 / (1 + 10^((Rb - Ra) / 400))`.
3. **Change** for A: `delta = K(A) / (N - 1) x sum over the other drivers of w x (S - E)`, rounded to a whole point.
   `N` is the number of rated drivers.
4. **K shrinks with races played** in that bucket: `K = 16 + 32 x 10 / (10 + races)`. So 48 for a new driver, 32 after
   10 races, 26.7 after 20, and towards 16 in the long run.
5. **Glicko-lite weight.** A driver with fewer than 5 rated races is **provisional**. An established driver's duel
   against a provisional one counts with `w = 0.5`; every other duel has `w = 1`. New drivers move fast, and
   settled ratings are not dragged around by unknowns.
6. **DNF:** a DNF's change is capped at 0. A DNF can never gain rating.
7. **Bounds:** ratings stay between 100 and 3000. Everyone starts at 1000.

In short: each driver's rating moves by a K-factor (48 for a new driver, falling towards 16) times the average over
all opponents of (actual minus expected Elo score), where finishing ahead counts as a win and two DNFs draw. Duels
against provisional drivers (fewer than 5 races) count half for established drivers, DNFs never gain, and ratings
are clamped to 100..3000.

### Worked example (3 drivers)

| Driver | Rating | Races so far | K | Result |
|---|---|---|---|---|
| A | 1000 | 0 (provisional) | 48 | P1 |
| B | 1200 | 20 | 26.667 | P2 |
| C | 1100 | 8 | 33.778 | DNF |

Expected scores: E(A vs B) = 1 / (1 + 10^0.5) = 0.2403, E(A vs C) = 1 / (1 + 10^0.25) = 0.3599,
E(B vs C) = 0.6401.

- **A** (provisional, so all weights 1): (1 - 0.2403) + (1 - 0.3599) = 1.3998. Delta = 48 / 2 x 1.3998 = **+33.60 → +34,
  1034**.
- **B** (established; A is provisional, so w = 0.5 against A): 0.5 x (0 - 0.7597) + (1 - 0.6401) = -0.3799 + 0.3599 =
  -0.0200. Delta = 26.667 / 2 x -0.0200 = **-0.27 → 0, 1200**. Losing to an unknown newcomer costs B almost nothing.
- **C** (established, DNF; w = 0.5 against A): 0.5 x (0 - 0.6401) + (0 - 0.3599) = -0.6800. Delta = 33.778 / 2 x
  -0.6800 = **-11.48 → -11, 1089**.

After the race: A 1034 (1 race, still provisional), B 1200 (21 races), C 1089 (9 races).

### Two new drivers (the Studio test)

| Race | Before | K | E (winner) | Winner | After |
|---|---|---|---|---|---|
| 1 | P1 1000, P2 1000, 0 races each | 48 | 0.5000 | P1 | P1 **1024 (+24)**, P2 **976 (-24)** |
| 2 | P1 1024, P2 976, 1 race each | 45.09 | 0.5690 | P1 | P1 **1043 (+19)**, P2 **957 (-19)** |
| 3 | P1 1043, P2 957, 2 races each | 42.67 | 0.3787 (P2) | P2 | P2 **984 (+27)**, P1 **1016 (-27)** |

Both stay provisional until their 5th ranked race in that bucket.

## Buckets, storage and seasons

- **Buckets:** Street, Sport, Super, Hyper, Track Spec (the car's `Class` attribute, set by the server at spawn from
  its PI; upgrades never change class), plus Equalised. Each bucket is its own rating.
- **Saved** in the player's progress record: `Progress.SetData(plr, "circuitRating", {[bucket] = {rating, races,
  season}})`, under `extra`, so the record's `UpdateAsync` session lock and autosave cover it. Written only by
  `Ranked.apply`, from the server's rows.
- **Seasons:** `RankedRating.SEASONS` is a table of `{id, name, starts}` (UTC unix time). Season 1 started
  2026-10-01. To start a new season, add a row with a later `starts`; never edit a row that has started.
- **Soft reset:** an entry from an earlier season is reset when it is next read (menu or race):
  `rating = round((rating + 1000) / 2)`, `races = min(races, 5)`. A 1400 becomes 1200 and keeps a medium K (37.3 at
  5 races), and it is not provisional.
- **Leaving mid-race:** the ratings are snapshotted at lights out. A driver who leaves the game is still a DNF
  opponent for the others, but their own new rating cannot be saved (their record was saved when they left).

## Ranked board (LeaderboardService)

- OrderedDataStore `CircuitRating_S<season>_<bucket>` (spaces become `_`, e.g. `CircuitRating_S1_Track_Spec`), key
  `u<userId>`, value `rating x 10 + (1 if established, 0 if provisional)`, read descending (top 100, every 60 s at
  most). The last digit carries the provisional marker. One `SetAsync` per driver per ranked race.
- `Leaderboard.submitRating(plr, bucket, season, rating, provisional)` and `Leaderboard.rankedTop(bucket, season, n)`
  → `{userId, name, rating, provisional}`.
- Same fallback as the lap boards: every call is in `pcall`. When the store is unavailable (Studio without API
  access), the board shows this server's session memory, and the store is retried after 5 minutes. This server's
  newest values always override the cached store rows.
- The board is display only. The rating itself is the progress record.

## Client (CircuitRaceClient)

- **Menu (RACES):** `RANKED ON - Season 1 - your STREET rating 1024 (PROVISIONAL 1/5)` for the car you sit in. A
  forming race shows `[RANKED] CircuitRace: Forming, ...`, or `[UNRANKED: too few laps]`. The "Start a public race"
  button ends with `RANKED` or `unranked: 2+ laps`.
- **Menu (under the lap records):** `RANKED BOARD - STREET - Season 1`, top 5, `(P)` after provisional drivers.
- **Tower:** a `RANKED RACE` header line in orange.
- **Results:** the title ends with `RANKED STREET`, a RATING column (`1024 (+24) P`), and a bottom line
  `YOUR STREET RATING 1024 (+24) PROVISIONAL 1/5`. An unranked ranked-session result shows
  `UNRANKED - <reason>`. `(not saved)` is shown if your progress had not loaded.

Payload fields: `menu.ranked = {bucket, season, minLaps, rating, races, provisional, provisionalRaces, top}`,
`menu.formal.ranked / rankedOk`, `tower.ranked`, `results.ranked / bucket / unranked / provisionalRaces`, and on each
rated results row `bucket, rating, ratingDelta, provisional, ratedRaces, ratingSaved`.

## Offline checks (not a playtest)

There was no runnable harness for the earlier "offline Luau harness with mocked services" in the repo, so these were
written for this work (the luau CLI binary itself is not in the repo):

- `RankedRatingTest` against `RankedRating`: **45/45 checks passed**. They cover K values, expected scores, the
  2-player sequence above, the 3-driver worked example, the end of provisional, DNF capping, bounds, solo races,
  seasons, soft reset and broken stored entries. A deliberately broken module (K_MAX = 40) failed 15 checks, so the
  test does catch errors.
- `tools/offline/ranked_session_*`: the real `RaceSessionService` source with mocked Players, DataStore, Progress,
  Leaderboard, Route, Registry, Validator and Timing. It runs whole formal races through the Heartbeat state machine,
  and **31/31 checks passed**:
  - Off by default: no rating fields, nothing saved.
  - With `RankedEnabled`: 1024/976, then 1043/957, saved under `circuitRating.Sport` with season 1, board submit,
    `RANKED` flag on the tower payload.
  - Unranked: 1 lap on the oval (too short), a private room, mixed classes, a DQ, solo, nobody finished.
  - Time Attack has no ranked flag. A DNF is rated (−16). Equalised is a separate bucket. A driver who left mid-race
    is rated against but not saved. The menu shows the rating.
- `tools/offline/ranked_board_*`: the real `LeaderboardService` with a failing store (session fallback, order,
  provisional marker, buckets and seasons apart) and a working mock store (encoding, read back on a "fresh server"):
  **11/11 checks passed**. A failing `GetOrderedDataStore` is cached as unavailable without a warning, the same as the
  existing lap boards.
- All changed files compile with `luau-compile`.

Run: `bash tools/offline/run_ranked.sh <path to luau.exe>`.

## Studio test plan (for the leader)

Before you start: keep Game Settings → Security → "Enable Studio Access to API Services" **off**. See "DataStore
caveat".

**1. Unit test (Edit mode or any Play session, command bar):**

```lua
print(require(game.ServerStorage.RankedRatingTest)())
```

Expected: `RankedRating: 45/45 checks passed  true`.

**2. Off by default (regression).** Press Play (1 player), run a solo or 2-player public race as in
CIRCUIT_RACE_SYSTEM.md test 8. Expected: no RANKED text anywhere, and the results look exactly as before (no RATING
column, no bottom line).

**3. Two-player ranked race.** Test → Clients and Servers, **2 players**, Start.

- Server command bar:
  ```lua
  game.ServerStorage:SetAttribute("RankedEnabled", true)
  local S = require(game.ServerStorage.PattayaTestKitServer).start()
  print(S.publishCircuit("test_oval"))
  ```
- Seat both players in **the same class**, e.g. Player1 in `RaceCar_hatch` and Player2 in `RaceCar_kei` (both
  Street). Then travel each to the test oval paddock. Each client:
  ```lua
  local TK = require(game.ReplicatedStorage.PattayaTestKit) TK.hookRemotes()
  TK.seatIn("RaceCar_hatch")   -- Player2: TK.seatIn("RaceCar_kei")
  TK.fire("CircuitRequest", "travel", "test_oval")
  ```
- Player1 presses P. Expected: `RANKED ON - Season 1 - your STREET rating 1000 (PROVISIONAL 0/5)`, the button
  "Start a public race (3 laps, forms 25 s) RANKED", and "RANKED BOARD - STREET - Season 1 / No ranked results yet".
- Player1 client (starts the race and drives faster):
  ```lua
  local P = game.Players.LocalPlayer
  TK.fire("CircuitRequest", "join", {mode = "CircuitRace", circuit = "test_oval", laps = 3})
  task.spawn(function()
  	repeat task.wait(0.25) until P:GetAttribute("CircuitState") == "StartLights"
  	TK.lapCircuit("TK_Circuit_test_oval", 3, {speed = 95, name = "race",
  		startWhen = function() return P:GetAttribute("CircuitState") == "Racing" end})
  end)
  ```
  Toast: `Race forming: 3 laps, starts in 25 s - RANKED`.
- Player2 client, within the 25 s (slower, offset to the side so the cars do not touch):
  ```lua
  local P = game.Players.LocalPlayer
  TK.fire("CircuitRequest", "join", {mode = "CircuitRace", circuit = "test_oval", join = true})
  task.spawn(function()
  	repeat task.wait(0.25) until P:GetAttribute("CircuitState") == "StartLights"
  	TK.lapCircuit("TK_Circuit_test_oval", 3, {speed = 80, lateral = 8, name = "race",
  		startWhen = function() return P:GetAttribute("CircuitState") == "Racing" end})
  end)
  ```
- Expected during the race: the tower's first line is `RANKED RACE` (orange).
- Expected at results:
  - Title `Test Oval - CircuitRace - 3 laps - RANKED STREET`.
  - Row 1 `Player1 ... 1024 (+24) P`, row 2 `Player2 ... 976 (-24) P`.
  - Bottom line on Player1: `YOUR STREET RATING 1024 (+24) PROVISIONAL 1/5`; on Player2: `976 (-24)`.
- Server check:
  ```lua
  local Pr = require(game.ServerStorage.PattayaProgress)
  for _, p in game.Players:GetPlayers() do
  	print(p.Name, game:GetService("HttpService"):JSONEncode(Pr.GetData(p, "circuitRating")))
  end
  ```
  Expected: `Player1 {"Street":{"races":1,"rating":1024,"season":1}}` and `Player2 {"Street":{"races":1,"rating":976,
  "season":1}}`.
- Run the same race again (Player1 faster). Expected: **1043 (+19) / 957 (-19)**, races 2. Then swap the speeds
  (Player2 95, Player1 80). Expected: Player2 **984 (+27)**, Player1 **1016 (-27)**.
- Menu (P) after a race: `RANKED BOARD - STREET`, `1. 1024  Player1  (P)`, `2. 976  Player2  (P)`.

**4. Unranked cases** (2 players, ranked on). Expected bottom line on the results:
- 1 lap: the menu button says "unranked: 2+ laps", and the results say `UNRANKED - too short (2+ laps here)`.
- Player2 in a Sport car (`RaceCar_jdm_coupe`): `UNRANKED - mixed classes`.
- Private room (invite Player2, START): no ranked line at all.
- Solo race: `UNRANKED - needs 2 or more drivers`.
- Player2 jumps with `TK.jumpTo(...)` mid-race (teleport DQ): `UNRANKED - a driver was disqualified`.
- In every case `circuitRating` is unchanged (server check above).

**5. Regression.** Time Attack, Track Day, Free Practice and private rooms behave as before. No `[Circuit] ranked`
warnings in the output.

### DataStore caveat

- Studio without API access: `PattayaProgress` keeps the rating in memory for the Play session only (it starts at 1000
  again next Play). The ranked board uses session memory. This is the intended way to test.
- With "Enable Studio Access to API Services" on, Studio writes to the **real** place stores: `PattayaProgress_v1`
  and `CircuitRating_S1_<bucket>`. Studio test players have negative UserIds (`Player1` = -1), so this would put `u-1`
  rows on the live ranked board. Don't test ranked with API access on, unless the place is a test copy.
- Saving and rejoining (rating persists across servers) can only be tested on a published test place.

## Open questions and risks

- **Leaving dodges a loss.** A driver who leaves the game mid-race keeps their old rating, because their record was
  saved on leave. Others still count them as a DNF. A fix needs a pending-penalty write that the progress save picks
  up (connection order on `PlayerRemoving` is not guaranteed), or a separate store.
- **One DQ voids the race.** `voidOnDisqualified = true` follows the brief, but one teleporting (or badly lagging)
  driver denies the rating to everyone. The alternative is to rate the DQ'd driver as last and keep the race:
  set `voidOnDisqualified = false` and treat `dq` as DNF. Owner decision.
- **Physics is client-owned (CODE_REVIEW_2 U9).** The server catches teleports (260 studs/s) but not a modest
  overspeed, and `Equalised` / `SpeedCap` are client-trusted. For a real ranked release, add a per-sample speed check
  against the class's top speed.
- **Win trading.** Two drivers on an otherwise empty server can trade wins. The minimum is 2 drivers. Consider 3+, or
  less gain against the same opponent within a time window.
- **Mixed public grids.** Public races have no class filter, so a mixed grid finds out only at the results that it is
  unranked. Option: lock a ranked public race to the first joiner's bucket and refuse other classes at join.
- **Season dates:** only Season 1 (2026-10-01) is defined. The length of a season is the owner's call.
- **Results width:** the RATING column makes a row about 73 characters at text size 14 in a 628 px area. That is a
  tight fit, not yet seen on screen (phone widths especially).
