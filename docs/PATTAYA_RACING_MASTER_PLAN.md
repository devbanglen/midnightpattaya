# Pattaya Racing World — master plan (superseded)

> The game is now **MIDNIGHT PATTAYA**. The current plan is `MIDNIGHT_PATTAYA_MASTER_PLAN.md`; this file is kept as the
> original plan (architecture and first-slice decisions still apply).

Design mode C: RayCity-style, gameplay-optimised Pattaya. Recognisable real road layout and coast, compressed
distances, widened roads, smoothed curves. Owner communication in Thai.

## Architecture (decided 2026-10-18)
```
OSM (Overpass, cached raw JSON, ODbL)            data/osm/raw/*.json             geographic truth, never edited
  -> tools/mapgen/osm_normalize.py               data/osm/normalized/*.json      truth, typed (roads, coast, buildings, areas, POIs)
  -> tools/mapgen/road_graph.py                  build/<slice>/graph_source.json UTM metres, original ids, connected graph
                                                 build/<slice>/graph_game.json   gameplay layer: compression, smoothing, widths
  -> tools/mapgen/export_roblox.py               build/<slice>/roblox/*.luau     chunked data modules + manifest (sea mask, junctions)
  -> local HTTP (localhost) -> Studio            ServerStorage.PattayaData       ModuleScripts
  -> ServerStorage.PattayaBuilder (Luau)         workspace.PattayaWorld          Parts per chunk (ModelStreamingMode Atomic) + Terrain
```
- Everything configurable lives in `tools/mapgen/config/<slice>.json`; re-running the three scripts and the builder
  reproduces the world. `build/` is gitignored (regenerable).
- Python 3.12 venv (`.venv`, `requirements.txt`: numpy, shapely, pyproj, pillow). No heavy GIS stack.
- World placement: gameplay (0,0) at Roblox (20000, 0, 0), clear of the template and the RaceMap test city.
  Gameplay coordinates stay within about ±3,800 studs of that origin for the central slice.

## Phases
See `PROJECT_STATUS.md` for the live status. Order: 0 audit, 1 GIS, 2 graph, 3 transform, 4 roads, 5 buildings and
coast, 6 first playable central zone (spawn + loop race), 7 visuals, 8 high-speed streaming/perf, 9 districts,
10 racing infrastructure, 11 polish.

## First playable slice
Central Pattaya bbox 12.921–12.953 N, 100.862–100.893 E: Beach Road (Pattaya Sai 1) along the bay, Second Road
(Pattaya Sai 2), Pattaya Nuea / Klang / Tai, Thappraya start, Walking Street area, sois between.
Planned loop race: Beach Road → Pattaya Tai → Second Road → Pattaya Klang (or Nuea) → Beach Road.
