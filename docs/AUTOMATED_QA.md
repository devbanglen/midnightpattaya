# Automated QA

Two parts:

| Part | Where it runs | File(s) |
|---|---|---|
| Offline regression tests | any PC with the repo, no Studio | `tools/qa/tests/` (Python standard library + the luau CLI) |
| Live-state runner | Studio Play, server context | `roblox/src/ServerStorage/PattayaQARunner.luau` → `ServerStorage.PattayaQARunner` |

Both are read-only. The tests read the repo sources, `roblox/data`, the exporter configs and the generated `build/`
outputs. The runner reads instances, attributes and `Stats`. Neither one changes the place. `tools/qa/offline_checks.py`
(compile, asset manifest, vis_slice determinism, rollback entry points) is separate and still works as before.

## 1. Offline tests

```
.venv\Scripts\python tools\qa\tests\run_all.py          (one line per test, exit 1 on a failure)
.venv\Scripts\python tools\qa\tests\run_all.py -v -k circuits
.venv\Scripts\python -m pytest tools/qa/tests -q        (only if pytest is installed; the venv has none today)
```

- **Needs:**
  - `build/` (gitignored). It is found at `$MP_BUILD_DIR`, then `<repo>/build`, then, when the repo is a worktree
    under `<main>/.claude/worktrees/`, at `<main>/build`.
  - The luau CLI (`luau.exe`, `luau-compile.exe`). It is found at `$LUAU_DIR`, then the session scratchpad
    `…/scratchpad/luau/`, then any Claude scratchpad `luau` folder under `%TEMP%`, then `tools/luau/`, then PATH.
- A test whose input is missing is **skipped** with the reason (for example "luau CLI not found" or
  "build/… missing"). It never passes silently.
- **Known problems** are marked `@unittest.expectedFailure`, shown as `XFAIL`, and pytest reports them as xfail.
  When one is fixed, the test shows `XPASS` and the run fails. Then remove the marker.
- **No mocks claiming success:**
  - The circuit and ranked tests run the **real** Luau modules with the luau CLI. The only stand-ins are for
    Roblox types (`Vector3`, `CFrame`, `game:GetService`), in `tools/qa/tests/luau/prelude.luau`, and for the
    services the ranked harness needs (`tools/offline/ranked_*_head.luau`).
  - Formulas that are ported to Python (CarSpecs PI and upgrades, reward lines) are either parsed from the source
    or asserted to still be in it word for word.

### What each file covers

| File | Covers |
|---|---|
| `test_luau_compile.py` | Every `roblox/src/**/*.luau` and `roblox/data/**/*.luau` compiles (`luau-compile --null`). `.server`/`.client` suffixes sit in the right services. No two scripts share a name in one folder. |
| `test_race_central.py` | **Central Loop** (`build/central_pattaya` race, which PattayaBuilder turns into `PattayaWorld.Race.Checkpoints`):<br>- start/finish = checkpoint 1 at the path start;<br>- closed path whose length = `length_studs`;<br>- 22 checkpoints on the path, in order, facing the route, 60–900 studs apart;<br>- the grid behind the line, facing it;<br>- `route_edges` exist in the graph;<br>- `manifest.luau` and the wide layout carry the same race;<br>- builder ↔ race server attribute names (`Index`, `Laps`, `LengthStuds`).<br>Also:<br>- every server's teleport `MAX_SPEED` ≥ `CarSpecs.NITRO_LIMIT` + 10 (race, sprint, CheckpointValidator, jobs, street race);<br>- sprint length / spacing / time limit;<br>- road graph integrity and connectivity (central and wide: largest component ≥ 97 % of nodes). |
| `test_circuits.py` | **Bira data** (`roblox/data/circuits/bira.luau`):<br>- closed, evenly spaced centreline;<br>- length 8,521 studs ≈ 2.4 km;<br>- one width per point;<br>- indices in range;<br>- the pit lane joins the track;<br>- ≥ 12 grid slots;<br>- every `def.*` key that CircuitBuilder reads is present.<br>**Compiled by the real `CircuitRegistry.compile`** (both circuits):<br>- lap length;<br>- gates numbered 1..n in driving order, 60–120 studs apart, exactly one start/finish line and two sector lines;<br>- Bira = 96 gates / 1,702 points;<br>- pit gates and bypass;<br>- grid on the track;<br>- entrance.<br>**Judged drives** through the real `CheckpointValidator` + `LapTimingService`:<br>- 2 clean laps at 100 studs/s (every gate once, no missed gate, valid laps of len/100 s);<br>- 1 lap at 230 studs/s (no teleport);<br>- a lap through the pit lane at 50 studs/s (pit on/off, no missed gate, valid).<br>**`build/bira` corridor graph:** connects the city join node to the Bira end. |
| `test_garage.py` | **CarSpecs:**<br>- every car has all 15 stats, in sane ranges;<br>- ORDER = cars, the starter is free, prices and levels go up;<br>- upgraded cars stay ≤ NITRO_LIMIT and well under 260.<br>**docs/GARAGE_AND_CLASSES.md matches the code:**<br>- the car table (stats, PI, class, price, level);<br>- the class bands;<br>- the upgrade table (E/G tiers and best PI, from the class rule);<br>- the price examples.<br>**Levels:** car level gates are reachable with `PattayaProgress.expToNext`.<br>**GarageRequest contract:** a RemoteFunction; every client action (`state`, `spawn`, `buy`, `select`, `upgrade`) is handled by the server; the upgrade kinds = `UPGRADE_KINDS`. |
| `test_remotes_contract.py` | A static contract over all of `roblox/src` (comments stripped):<br>- every remote a `.client.luau` waits for is created by a server script or module;<br>- client FireServer ↔ server OnServerEvent, client OnClientEvent ↔ server FireClient/FireAllClients, InvokeServer ↔ RemoteFunction.OnServerInvoke;<br>- no server remote is unused;<br>- one class per remote;<br>- all under `PattayaRemotes`.<br>The 18 known remotes (jobs/missions, events, challenge, Road Fight, sprint, GPS, garage, circuit, nitro, telemetry) must be found, so the grep itself is guarded. |
| `test_progress_rewards.py` | **Money/EXP formulas**, read from the source and evaluated over realistic inputs: the Central Loop, Street Sprint, Street Challenge, Night Run, jobs (taxi/delivery), Road Fight, Survival.<br>- Never negative, always some EXP.<br>- No single run pays more than 10 % of the top car's price.<br>- Slower or lower placed never pays more.<br>- The cheapest car is reachable in ≤ 20 loops.<br>- The podium and boss tables are ordered.<br>**PattayaProgress:**<br>- the EXP curve;<br>- every granted title is in `TITLE_RANK`;<br>- every `Progress.Award` call has 4 arguments. |
| `test_ranked.py` | Runs `ServerStorage/RankedRatingTest.luau` on the real `RankedRating` (45/45 checks). Runs the mocked `RaceSessionService.Ranked` and `LeaderboardService` ranked-board harnesses from `tools/offline` (the same as `run_ranked.sh`). Checks that ranked is wired in the session service and in the Studio runner. |
| `test_budgets.py` | **build/ against the documented budgets:**<br>- vis slice: ≤ 600 parts per chunk, total ≤ 25,000, ≤ 8 chunks per batch, every chunk in one batch with matching part sums, exporter checks 0, chunk modules present;<br>- street furniture: ≤ 10,000 parts, cap 600, checks 0, batches;<br>- aprons: cap 1,500, checks 0, batches;<br>- coast: chunk ≤ 600, total ≤ 8,000, no cells touching roads, export checks 0;<br>- landmarks: ≤ 900 parts each, batches, module size;<br>- wide world: ≤ 140 buildings per chunk;<br>- every generated Luau module ≤ 200 KB;<br>- vis assets ≤ 10,000 triangles and ≤ 4 materials each.<br>**PERFORMANCE_BUDGET.md profile table = `PattayaPerfProfile.PROFILES`:**<br>- the client LOD/light defaults = the `pc` profile;<br>- mobile ≤ pc;<br>- pc streams ≥ 1,000 studs ahead. |
| `test_qa_runner.py` | Keeps the Studio runner in sync:<br>- its remote list = the server sources;<br>- its script lists = the repo files;<br>- chunk caps = the configs;<br>- 22 checkpoints / 96 Bira gates = the data;<br>- the folder names exist in the builders;<br>- it compiles;<br>- **read-only:** a grep forbids `Destroy`, `Instance.new`, `SetAttribute`, `.Parent =`, `PivotTo`, `Fire*`, `Invoke*`, `.CFrame =`, `.Value =`, the test-kit mutators and the PerfProfile apply/revert. |

### Current results (2026-10-20, branch `team11/qa`)

`run_all.py`: **PASS 82, XFAIL 4, FAIL 0** in ~7 s. The luau CLI and `build/` were present, so nothing was skipped.

The 4 XFAILs are two real problems, each seen in the data and again after compiling:

1. **Bira grid slots compile to the world origin.**
   - `CircuitRegistry.compile` reads grid slots positionally (`s[1]..s[5]`, the documented `{x,y,z,dx,dz}` array
     form; the test oval uses it).
   - `bira.luau` (generated by `tools/circuit/bira_circuit.py`) writes keyed tables `{x =, y =, z =, dx =, dz =}`.
     That is the form CircuitBuilder reads for the grid marks.
   - Result: the judge gets 16 slots at `(0, 0, 0)` facing −Z.
   - Open sessions start in the pit lane, so practice and the tested laps are fine. But a **Circuit Race on Bira**
     would put every car at the world origin. CIRCUIT_RACE_SYSTEM.md lists "a race on Bira" as not tested.
   - Tests: `BiraData.test_grid_slot_format_matches_registry`, `CompiledCircuits.test_bira_grid_on_track`.
   - Fix (game source, not done here): make `CircuitRegistry` accept both forms (`s.x or s[1]`, ...), or have the
     exporter write arrays and CircuitBuilder read both.
2. **Bira pit-lane width is ignored by the judge.**
   - `CircuitRegistry` reads `def.pitWidth` (default 20).
   - The Bira data names it `pitLaneWidth` (32.14 studs; CircuitBuilder builds the lane that wide).
   - Result: the judge's "in the pit lane" test (`width/2 + 4`) and the pit-gate width use 20 instead of 32.14. The
     test lap through the pits on the centre of the lane still passes.
   - Tests: `BiraData.test_registry_keys_present`, `CompiledCircuits.test_bira_pit_width_from_data`.
   - Fix: `def.pitWidth or def.pitLaneWidth or DEFAULT_PIT_WIDTH`.

Everything else matches its documentation:
- the Central Loop data;
- the remote contract (18 remotes, every direction);
- the garage table, PIs, upgrades and prices;
- the reward formulas;
- the ranked maths (45/45);
- every chunk, part and module budget in build/;
- the profile table.

## 2. Studio runner (`ServerStorage.PattayaQARunner`)

- `tools/studio/install.ps1` bundles every file in `roblox/src`, so the runner is installed with the rest. By hand:
  make a ModuleScript `ServerStorage.PattayaQARunner` and paste the source.
- In **Play**, on the **server** (command bar set to Server, or the execute tool in the server context):

```lua
local lines = require(game.ServerStorage.PattayaQARunner:Clone()).run()
print(table.concat(lines, "\n"))
-- or, the same printed:      require(game.ServerStorage.PattayaQARunner:Clone()).report()
-- with the road probe:       require(game.ServerStorage.PattayaQARunner:Clone()).report({probe = true})
-- with per-chunk lines:      ...run({verbose = true})
```

- **Output:**
  - Line 1: `QA <n> PASS, <n> FAIL, <n> WARN (<ms> ms)`.
  - Then one line per check: `PASS` / `FAIL` / `WARN` (a budget heuristic or a known issue) / `INFO`.
  - A check that errors becomes a `FAIL ... check errored: ...` line. The run never stops half way.
- **Read-only:**
  - The runner only reads.
  - `CircuitRegistry`, `RankedRating(Test)` and `PattayaPerfProfile` are required as **clones**, so their module
    state stays out of the game's copies.
  - It calls the test kit only for `S.report()` and, with `probe = true`, for `S.probePath` (server raycasts).

| Check | What it reads | Pass when |
|---|---|---|
| `context.*` | RunService | Server and Play mode |
| `remotes.*` | `ReplicatedStorage.PattayaRemotes`, `ReplicatedStorage.PerfTelemetry` | All 17 named remotes with the right class, no duplicate names (extras listed as INFO) |
| `scripts.server` / `scripts.client` | ServerScriptService, StarterPlayerScripts | Every repo script is present (server ones Enabled) |
| `scripts.no_duplicates` / `no_stray_server_copies` | Every LuaSourceContainer in the main services and workspace | No two scripts with one name and class under one parent; no enabled copy of a server script outside ServerScriptService |
| `garage.*` | `ServerStorage.BuildCar`, `workspace.PattayaGarage`, `CarSpecs`, every `RaceCar` model | The services ran; each car's `PI` and `Class` = `CarSpecs.Describe(CarId, UpgEngine, UpgGrip)` |
| `progress.*` | Each player's leaderstats, `ProgressLoaded` | Level/Money/EXP/Title exist |
| `race.*` | `PattayaWorld.Race` | 22 checkpoints, `Index` 1..22 unique, Laps / LengthStuds / Path attributes |
| `jobs.stands`, `events.*`, `data.*` | JobStands, `ReplicatedStorage.PattayaEvent`, `ServerStorage.StartEvent`, EventRing, PattayaData.graph/circuits | The servers built their objects |
| `circuit.*` | A cloned CircuitRegistry loaded from PattayaData.circuits, `workspace.Circuit_bira`, the Paddock_bira marker, the PattayaWorldMap attribute | Bira compiled with 96 gates. The venue and paddock exist, and the CircuitServer published the entrance. The grid and pit width are WARN while the known issues above stand. |
| `ranked.rating_test` | RankedRatingTest on RankedRating | All checks pass |
| `budget.parts <folder>` | BaseParts per top folder of workspace (PattayaWorld one level deeper) | ≤ 1.25 × the reference count from PERFORMANCE_BUDGET.md / build totals (WARN, not FAIL: there is no single documented cap) |
| `budget.chunk_cap <folder>` | Every chunk model of VisSliceChunks / FurnitureChunks / CoastChunks (600), ApronChunks (1,500), LandmarkChunks (900) | No chunk over its cap |
| `budget.parts_total`, `stats.*` | Workspace BaseParts, Stats InstanceCount / PrimitivesCount / memory by tag | Total ≤ 160,000 parts, memory ≤ 6,000 MB (WARN; Studio runs server and client in one process) |
| `budget.streaming_pc_profile` | `PattayaPerfProfile.show(true)` (reads only) | StreamingEnabled, MinRadius / TargetRadius = the `pc` profile (WARN otherwise, e.g. mobile) |
| `testkit.*` | `PattayaTestKitServer.report()`; `probePath("RacePath")` with `probe = true` | ≥ 95 % of the Central Loop probes hit road |

**Status:** written and compile-checked (`luau-compile`). The offline test `test_qa_runner.py` keeps it in sync and
read-only. **It has not been run in Studio yet.** The leader runs it in the next Play session.
