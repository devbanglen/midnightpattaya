# Performance budget

## Measurements (2026-10-18, Roblox Studio Play on the owner's Windows PC, desktop only)
Method: fresh Play session; server test-autopilot moves the seated car along the race path at 160 studs/s (top
speed without nitro) for a full lap (~41 s) while the client records RenderStepped frame times. Studio caps at 60.

| Scenario | Avg FPS | 1% low | Worst frame |
|---|---|---|---|
| Idle at spawn | 60.0 | 54.4 | — |
| Camera over the sea, facing away from the city | 60.0 | 55.0 | — |
| Full lap at 160 studs/s, day | 60.0 | 44.0 | 31 ms |
| Full lap at 160 studs/s, night (lit windows, 291 spotlights) | 60.0 | 45.2 | 32 ms |

World size: 16,027 Parts, 11,116 facade Textures, 291 SpotLights (night only), terrain ground/sea. With instance
streaming (template setting) a client had 3,700–6,500 Pattaya parts loaded at a time.

Caveats:
- Earlier runs in a session that had already run several test autopilots showed 15–21 FPS; a fresh session gave the
  numbers above. Long sessions should be re-measured (possible leak in test scripts or Studio itself).
- Studio Play runs server and client on one machine; a real client may differ.
- Mobile 30 FPS target: NOT measured (needs the device emulator or a phone).
- Studio screenshots are unreliable when the Studio window is not in front; FPS may also drop when unfocused.

## Budget rules used so far
- Windows as Textures, not Parts. One box per building. Roof slab only above 30 studs.
- Real lights only on every second street lamp, no shadows, enabled only at night.
- Markings/props don't collide and are excluded from queries.
- Chunks are Atomic streaming models (512 studs); race gates/grid are Persistent.

## Wide world estimate (pattaya_wide, 2026-10-18) — NOT imported, NOT measured
Counts from the pipeline; Parts are estimated with the builder's rules (the same estimator gives 16,966 for the
central slice vs 16,027 measured, i.e. ~6% high; Textures matched exactly, 11,116).

| | central slice (measured) | new in wide world | wide total |
|---|---|---|---|
| Graph edges / nodes | 614 / 463 | 3,186 / 2,462 | 3,800 / 2,925 |
| Road length (studs) | 102,852 | ~538,600 (Sukhumvit 60,745 express) | 641,494 |
| Junction discs | 312 | 1,380 | 1,692 |
| Buildings | 3,018 | 7,175 (275 merged away by LOD) | 10,193 |
| Parts | 16,027 | ~39,800 (roads+markings 23.2k, buildings 7.2k, roofs 2.7k, props 5.3k, discs 1.4k) | ~56,000 |
| Facade Textures | 11,116 | ~24,500 | ~35,600 |
| Palms / street lights | 157 / 555 | 278 / 1,214 (≈607 more night SpotLights) | 435 / 1,769 |
| Chunk modules | 93 (largest 44 KB) | 444 (largest 13 KB) | 537 |
| Traffic loops / cars | 36 / 464 | 48 / 691 | 84 / 1,155 |

Budget view: with instance streaming a client loads only nearby Atomic chunks, so client cost per view should stay
close to the central slice's (3,700–6,500 Pattaya parts loaded at a time) — the wide areas are less dense than the
centre. The server and Studio hold all ~56k Parts. Re-measure FPS (desktop and a mobile emulator) after the seam
batch and after the whole extension; the night SpotLights (every second lamp) are the first thing to cut if night
FPS drops.

### LOD / thinning options (config, all used by pattaya_wide only)
- `drop_dead_end_sois_shorter_m: 250` (central 120): prunes 1,274 short dead-end sois.
- `clip_polygon_lat_lon`: only land between the sea and Sukhumvit (the first try with a bbox doubled the road length).
- `sidewalk_studs.soi: 0`: new sois have no sidewalk strips (most Thai sois have none) — saves 2 Parts per segment.
- `roads_lod.dash_gap_studs: 32`: lane dashes every 40 studs instead of 20 on new roads (`manifest.dashGap`).
- `layout.light_spacing_studs: 110` (central 70).
- `buildings.lod`: `merge_below_area_studs2` / `merge_gap_studs` / `merge_min_fill` merge small neighbouring
  boxes (shophouse rows) into one when the box still clears all road corridors; `max_per_chunk` caps boxes per chunk
  (140; not reached — the densest new chunk has 137); `facade_min_height_studs` (0 = all keep facades) drops Textures on
  low boxes; `min_area_studs2` as before. Boxes are already single oriented boxes.
Together these cut the new Part estimate from ~66,500 to ~39,800.

### Elevation (Pratumnak hill) — not added, flat as before
A free, no-key DEM exists: AWS Terrain Tiles (terrarium PNG,
`https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`, height = R·256 + G + B/256 − 32768 m).
One z12 tile checked: Pratumnak hill top ~89–96 m, Pra Tumnak Rd ~54 m, Beach Road ~7 m. The Bira team already uses
these tiles (`data/dem/` in their checkout). Not used here because every road, building, prop, traffic car and the
car controller assume one flat road top (y = 1); hills need builder + chassis + traffic work first. If added it must
be an optional config flag, off by default, sampling node heights from the tiles (ODbL-compatible attribution
"Mapzen/Tilezen Terrain Tiles, SRTM and others").
