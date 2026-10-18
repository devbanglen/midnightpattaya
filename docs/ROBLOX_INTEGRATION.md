# Roblox integration

## Getting generated data into Studio
There is no Rojo yet. The Studio MCP cannot read local files, so the data modules are served from
`build/<slice>/roblox/` on `http://localhost:8766` by a short-lived PowerShell HttpListener and pulled in with
`HttpService:GetAsync` from an `execute_luau` call. `HttpService.HttpEnabled` is switched on only for the duration
of that call and restored afterwards (it is off in the place).

Then: `require(game.ServerStorage.PattayaBuilder).Build()` rebuilds `workspace.PattayaWorld` (and terrain).

## Coexistence
- Pattaya world origin (20000, 0, 0); RaceMap test city at (6000, 100, 0); template content near the origin.
- The template overrides Asphalt/Concrete materials in MaterialService; generated parts use SmoothPlastic.
- Spawns: the template's SpawnLocation and RaceMap's `RaceSpawn` are disabled (re-enable to undo);
  players start at `PattayaWorld.Race.PattayaSpawn`.
- `Workspace.StreamingEnabled` is on (template setting). Race gates/grid are Persistent models.
- Saving: the Studio MCP has no save command and cannot send Ctrl+S to Studio; the owner saves, or turns on
  Collaboration (Team Create) for automatic cloud saves.

## Vehicles
`RaceCarServer` (server) spawns cars on `RaceMap.StartGrid`; `CarController` (client) drives with raycast suspension.
Pattaya roads are colliding, queryable Parts, so the existing car works on them unchanged (to be verified in Phase 6).

## Saving, crashes and rebuilding (added 2026-10-18 after a Studio crash)
- The MCP cannot save the place. **Studio Auto-Recovery** saved us once: after the crash the reopened place had
  everything up to the moment of the crash. Keep it on (File → Studio Settings → search "Auto-Recovery", interval
  5 min) and accept the recovery prompt when Studio restarts.
- Better: **Team Create** (Collaborate → Team Create on). Every change is saved to the cloud as it happens, so no
  Ctrl+S is needed and a crash loses nothing.
- Everything in the place is reproducible from the repo: `tools/studio/install.ps1` bundles all scripts and data
  modules and serves them; `tools/studio/install.luau` (run in the command bar) recreates every Script/ModuleScript.
  World geometry is then rebuilt with the builders:
  1. `require(ServerStorage.PattayaBuilder).Build()` (central slice)
  2. `Extend({roads = false})`, then `Extend({terrain = false, only = <8 ids>})` groups over `manifest.batches`
  3. `Extend({folder = "PattayaDataCorridor"})` (Bira corridor)
  4. `require(ServerStorage.CircuitBuilder).Build(require(ServerStorage.CircuitData.bira))`
  Always `require` a **Clone()** of a ModuleScript you just replaced in edit mode: Studio caches the first require.
- Cars (`ServerStorage.CarBodies`) are the one thing not in the repo as Studio instances: re-import the GLBs in
  `art/cars3d/roblox/` if the place is lost completely.
