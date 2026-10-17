# GIS pipeline

Run from the repo root (Windows):
```
.venv\Scripts\python tools\mapgen\osm_normalize.py tools\mapgen\config\central_pattaya.json
.venv\Scripts\python tools\mapgen\road_graph.py    tools\mapgen\config\central_pattaya.json
.venv\Scripts\python tools\mapgen\export_roblox.py tools\mapgen\config\central_pattaya.json
```

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
