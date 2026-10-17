# Procedural buildings

Pipeline: `tools/mapgen/buildings.py` (config block `buildings` in `tools/mapgen/config/<slice>.json`) →
`build/<slice>/buildings_game.json` + `buildings_check.png` → `export_roblox.py` puts rows into the chunk modules →
`PattayaBuilder.buildBuildings`.

## How a footprint becomes a building
1. OSM footprint projected and compressed exactly like the roads (same origin, same factor).
2. Road corridors (road + sidewalks + 3-stud margin) and junction circles are cut out of it (shapely difference);
   the largest remaining piece is kept.
3. Minimum rotated rectangle of that piece, shrunk about its centre (×0.88 steps) until it clears every corridor.
4. Height: OSM `height` or `building:levels` when present (274 buildings), else a seeded random range per category;
   beachfront hotels/condos/commercial get +4..+8 floors. Floor = 3.2 m × 0.75 vertical scale = 8.57 studs.
5. Category from tags (tourism/amenity/shop/building/name) or, for `building=yes`, from size and beachfront distance.

## In Roblox
- One anchored box Part per building (+ a non-colliding roof slab when taller than 30 studs). Footing 1 stud below
  the road top.
- Windows are `Texture` instances (no per-window Parts) from three procedural tiles (`tools/mapgen/facades.py` →
  `art/textures/facade_*.png`, asset ids in `tools/mapgen/config/facade_assets.json`): tower (hotels, condos,
  apartments), office (commercial, malls, parking), shophouse. Houses and temples are plain.
- Wall colour picked per palette from the OSM id (deterministic). Attribute `OsmBuilding` = OSM way id.

## First run (central slice)
3,018 buildings kept (4,655 footprints cross the slice edge and were skipped; 113 fully on a widened road; 149 could
not be fitted; 109 clipped too small; 62 tiny). Categories: shophouse 1,943, hotel 464, house 235, commercial 211,
industrial 93, apartments 37, mall 10, public 9, parking 7, condo 5, temple 4. Heights: median 29, p95 149,
max 457 studs. 11,116 facade Textures.

Acceptance check run in Studio: 2,437 road/junction Parts probed for overlap with building bounds → 0 overlaps.

## Limits / next
- Boxes only: no podiums, setbacks, shop signs or night lights yet (Phase 7).
- Footprints crossing the slice edge are dropped (gap along the slice border).
- Landmark proxies not placed yet.
- No LOD yet: all buildings are always loaded (instance streaming not enabled).
