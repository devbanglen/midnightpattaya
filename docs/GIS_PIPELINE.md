# GIS pipeline

Run from the repo root (Windows):
```
.venv\Scripts\python tools\mapgen\osm_normalize.py tools\mapgen\config\central_pattaya.json
.venv\Scripts\python tools\mapgen\road_graph.py      tools\mapgen\config\central_pattaya.json
.venv\Scripts\python tools\mapgen\buildings.py       tools\mapgen\config\central_pattaya.json
.venv\Scripts\python tools\mapgen\gameplay_layout.py tools\mapgen\config\central_pattaya.json
.venv\Scripts\python tools\mapgen\export_roblox.py   tools\mapgen\config\central_pattaya.json
```
`buildings_game.json` and `layout.json` record the SHA-1 of the `graph_game.json` they were made from;
`export_roblox.py` refuses to run on stale ones. (`tools/mapgen/facades.py` only when facade art changes.)

## Download
`data/osm/queries/central_pattaya.overpassql` (bbox 12.912,100.855,12.960,100.910 with margin) fetched with
`curl.exe --data-urlencode data@<query> https://overpass-api.de/api/interpreter` (PowerShell 5.1's
Invoke-WebRequest failed: 406 without User-Agent, then TLS errors). Raw file is committed for reproducibility.

## Licence
OpenStreetMap data © OpenStreetMap contributors, ODbL 1.0. The attribution string travels with every generated
file (`attribution` field) and is stored as an attribute on `workspace.PattayaWorld`. An in-game credit is needed
before publishing.

## Normalised layer
Roads (class, names th/en, oneway, lanes, bridge/tunnel/layer, node ids, lat/lon), coastline ways, building
footprints (kind, levels, height, names, tourism/amenity/shop), areas (landuse/natural/leisure/man_made), named POIs.
Counts for the 2026-10-17 snapshot: 3,702 roads, 5 coastline ways, 8,106 buildings, 441 areas, 3,795 POIs.

## Wide world (pattaya_wide) — Naklua to Jomtien, sea to Sukhumvit
Same six stages with `tools\mapgen\config\pattaya_wide.json` (osm_normalize, road_graph, buildings, gameplay_layout,
traffic, export_roblox). It is an incremental extension of central_pattaya: run the central pipeline first (it is
the `base`), then the wide one. Central outputs are unchanged by the new code (regression 2026-10-18: every file in
`build/central_pattaya` byte-identical to the main checkout's build, and `data/osm/normalized/central_pattaya.json`
unchanged; the only difference is an old `sea_check.png` in the main checkout that the current scripts don't write).

Downloads 2026-10-18 (curl.exe, overpass-api.de, same filters as the central query; three parts around the central
download so the central data stays exactly what the slice was built from):

| query | bbox (S,W,N,E) | file | size | elements (ways/nodes; highways; buildings) | OSM base |
|---|---|---|---|---|---|
| `pattaya_wide_north` | 12.960,100.855,12.985,100.922 | `data/osm/raw/pattaya_wide_north_2026-10-18.json` | 1.28 MB | 1,907 (1,799/108; 1,047; 596) | 2026-10-18T10:38Z |
| `pattaya_wide_south` | 12.858,100.855,12.912,100.922 | `data/osm/raw/pattaya_wide_south_2026-10-18.json` | 6.28 MB | 9,997 (9,212/785; 3,329; 5,360) | 2026-10-18T10:38Z |
| `pattaya_wide_east` | 12.912,100.910,12.960,100.922 | `data/osm/raw/pattaya_wide_east_2026-10-18.json` | 1.26 MB | 2,010 (1,924/86; 1,139; 696) | 2026-10-18T10:40Z |

`sources` in the config lists the central raw file first plus the three parts; osm_normalize merges by (type, id),
first file wins: 29,131 elements → 28,849 unique → 9,048 roads, 8 coastline ways, 14,687 buildings, 1,075 areas,
5,070 POIs. (Ways are returned with full geometry even where they leave a query bbox.) Naklua's building coverage
in OSM is thin (596 buildings in the north part) — that is the data, not a filter.

New config keys (all optional, absent in central_pattaya.json): `sources`, `origin_utm`, `base`,
`clip_polygon_lat_lon`, `force_keep_ways`, `merge_graphs`, `roads_lod`, `buildings.lod`, `layout.districts`,
`layout.bira_entrance`; see the docstrings of each script, `docs/WORLD_CHUNKS.md`, `docs/PERFORMANCE_BUDGET.md`
and `docs/WORLD_MAP_INTEGRATION.md`.

Merging another graph (Bira corridor): `"merge_graphs": ["build/bira/corridor_graph_game.json"]` — same schema,
origin, compression and scale are required (checked); see `docs/WORLD_MAP_INTEGRATION.md`.

Results (2026-10-18): 3,186 new edges (+614 base), 2,925 nodes; new road length ~538,600 studs; 7,175 new
buildings; 13 new job stands; 278 palms on Jomtien Beach Rd / Naklua coast, 1,214 street lights; 48 new traffic
loops; 444 new chunk modules. Check images: `build/pattaya_wide/compare.png`, `buildings_check.png`,
`layout_check.png` (districts, stands, bosses).
