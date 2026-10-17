# Gameplay transformation

Source layer (`graph_source.json`) keeps OSM geometry in UTM 47N metres around the slice centre. The gameplay layer
(`graph_game.json`) is derived from it; each edge keeps `way` (OSM way id) and junction node ids `a`/`b`.

| Step | Setting (config) | Current value | Notes |
|---|---|---|---|
| Projection | `crs` | EPSG:32647 | origin = slice bbox centre |
| Distance compression | `compression` | 0.5 | first experiment (master prompt: 1:2 is not final) |
| Units | `meters_per_stud` | 0.28 | Roblox convention; with compression 1 m real = 1.79 studs |
| Axes | — | +X east, +Z south | Roblox |
| Curve smoothing | `smoothing.chaikin_iterations` | 3 | end points fixed (junctions stay put) |
| Resampling | `smoothing.resample_studs` | 6 | then Douglas–Peucker 0.35 studs in export |
| Lane width | `lane_width_studs` | 13 | cars are ~8.3–9.8 studs wide, 16 long |
| Lanes | `road_classes.*.lanes` / OSM `lanes` | trunk 6, secondary 4, tertiary 2, soi 2 | OSM tag wins when present |
| Sidewalks | `sidewalk_studs` | main 10, soi 6, express 0 | trimmed back from junctions |
| Pruning | `drop_dead_end_sois_shorter_m` | 120 m | only soi tier; repeated until stable |
| Connectivity | — | largest component kept | 49 disconnected edges dropped in the first run |

## What was modified vs. Pattaya (first run)
- Whole slice compressed 1:2 uniformly; no local repositioning yet.
- Corners rounded by Chaikin smoothing (all edges).
- Roads drawn at game widths (wider than real for sois).
- Short dead-end sois and disconnected fragments removed.
- Tunnels skipped; bridges flattened (Phase 4 limitation).
- No fictional arcade roads added yet.
