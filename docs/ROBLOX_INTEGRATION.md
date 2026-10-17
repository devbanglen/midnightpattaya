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
- The template's old SpawnLocation is disabled; RaceMap has `RaceSpawn`. Pattaya has no spawn yet (Phase 6).

## Vehicles
`RaceCarServer` (server) spawns cars on `RaceMap.StartGrid`; `CarController` (client) drives with raycast suspension.
Pattaya roads are colliding, queryable Parts, so the existing car works on them unchanged (to be verified in Phase 6).
