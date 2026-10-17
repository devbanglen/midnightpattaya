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
