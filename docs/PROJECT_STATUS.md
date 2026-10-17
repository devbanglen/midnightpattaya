# Project status — Pattaya Racing World

Last update: 2026-10-18. Statuses are only "done" when tested; see "How tested".

| Phase | Status | Deliverables | How tested | Known limits |
|---|---|---|---|---|
| 0 Audit | done | Python 3.12 venv + Git installed (owner approved), repo initialised, first checkpoint | tools run, `git log` | Game code lives in the Studio place only; copies of new Luau sources are in `roblox/src/` |
| 1 GIS retrieval | done | `data/osm/queries/central_pattaya.overpassql`, raw `data/osm/raw/central_pattaya_2026-10-18.json` (15,217 elements, OSM base 2026-10-17T22:33Z), normalised `data/osm/normalized/central_pattaya.json` | element counts printed; road names checked (Pattaya Sai 1/2, Nuea/Klang/Tai, Thappraya, Pra Tamnak, Sukhumvit) | No elevation data yet; only the central bbox downloaded |
| 2 Road graph | done (slice) | `build/central_pattaya/graph_source.json` | connected-component check: 1 component kept (49 disconnected edges dropped, 141 short dead-end sois pruned) | Bridges/tunnels/layers not modelled (tunnels skipped) |
| 3 Gameplay transform | done (first pass) | `build/central_pattaya/graph_game.json`, `compare.png` | visual source vs gameplay comparison | 1:2 compression is the starting experiment; no overlap check between widened parallel roads yet |
| 4 Roblox roads | in progress | `tools/mapgen/export_roblox.py`, `roblox/src/ServerStorage/PattayaBuilder.luau`, Studio `workspace.PattayaWorld` (72 chunks, 7,545 road parts, 463 junction discs), terrain ground/sea/sand | builder ran in Studio without errors; Play test: hatch placed on Beach Road drove 3 s to 160 km/h, stayed level (UpVector.Y 1.00) at constant height on the road parts | Not visually checked: every Studio screenshot came back white after the build, even with PattayaWorld removed (capture/render problem in Studio, not the map; one sea shot rendered fine). Only one straight stretch driven; no spawn point in Pattaya yet |
| 4a Fixes after owner review ("looks odd") | done | junction discs only at 3+-way nodes (312, was 463: blobs on straight roads); sidewalks run through plain joints; sea carved with ReplaceMaterial (FillBlock silently kept Ground: no sea existed before); ground lowered to surface y=-2 (terrain had covered the roads at y=2); road slabs 4 studs thick | terrain material/height read back with ReadVoxels + raycasts; screenshots of Beach Road and the first junction row | sidewalks still break on both sides where a soi joins from one side; beach edge is stair-stepped (16-stud cells) |
| 5 Buildings + coast | not started | | | |
| 6 First playable zone | not started | | | |
| 7–11 | not started | | | |

## Existing systems kept (not replaced)
- Car pipeline (concepts → Hunyuan3D → GLB) and 6 cars in `ServerStorage.CarBodies`.
- `RaceMap` test city at X≈6000, `RaceCarServer`, `CarController` (raycast arcade chassis).
- Template content in the place is untouched.
