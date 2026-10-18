# Bira Circuit: track reference (Phase C)

Last update: 2026-10-18. This file lists what we know about the real circuit, where each fact comes from, and how
sure we are. Game design choices are in `BIRA_CIRCUIT_DESIGN.md`. The access road is in `CIRCUIT_ACCESS_ROUTES.md`.

## Location
- Real name: Bira International Circuit (Bira Circuit). It is in Pong, Bang Lamung, Chon Buri, about 15 km
  northeast of central Pattaya.
- Wikipedia gives 12°55′17″N 101°0′33″E, which is 12.9214 N, 101.0092 E. The OSM raceway centre is at
  12.9206 N, 101.0090 E, so the two sources agree to within about 100 m. The brief's "12.92 N 100.99 E" is about 2 km too far west.
- It is about 12.4 km east of the central-slice origin (UTM 47N x 717.6 km vs 703.7 km).

## Facts from public sources (summarised, not copied)
| Fact | Value | Source | Confidence |
|---|---|---|---|
| Lap length | 2.410 km | Wikipedia; brief (bira.co.th) | good |
| Turns | 11 (Wikipedia); 12 (LapMeta, brief). One guide says sources give 11, 12 or 13 | Wikipedia, lapmeta.com, renndriver.com | sources disagree |
| Direction | clockwise | LapMeta track page | one secondary source only, **unverified** |
| Opened | 26 April 1986 (built 1985, first called "Pattaya Circuit", renamed Bira in 1988) | Wikipedia, renndriver.com | good |
| Character | twisty and bumpy, with elevation changes, two chicanes and a fast downhill double-apex corner | Wikipedia | descriptive |
| Pit garages | 30 | Wikipedia | not checked |
| Capacity | 30,000 | Wikipedia | not checked |
| Site area | about 65 acres (260,000 m²) | Wikipedia | not checked |
| FIA grade | "first circuit in Thailand to meet the FIA standard"; the brief says grade 3 | Wikipedia; brief | grade **unverified** |
| Track width, longest straight, exact elevation change | not found | — | **unknown** |

`https://bira.co.th/trackinfo/` was fetched. Its text gives no figures: the specifications are in a track map image
and a "Track Detail" tab that the fetch could not read. We copied no artwork, logo or map. The URLs are listed below
for reference only.

## What OpenStreetMap has (download 2026-10-18, OSM base 2026-10-18T10:37Z)
Query `data/osm/queries/bira_circuit.overpassql` (bbox 12.910,100.996,12.932,101.022). The raw file is
`data/osm/raw/bira_circuit_2026-10-18.json`.

| Feature | OSM | Notes |
|---|---|---|
| Race track | ways 107684749 + 1205208205, `highway=raceway`, `name=Bira Circuit`, `surface=asphalt`, 72 nodes | They chain into one closed loop of **2,391 m**, which is **-0.8 %** short of 2,410 m. After smoothing it is 2,383 m. Total turning is -360°, which fits a clockwise lap. The polyline is coarse (one node every ~33 m) and is traced, not surveyed |
| Kart track | way 107685029 `Bira Kart` (closed, 1,316 m outline) | Not built in the game |
| Pit lane | service ways 1205208206 → 132455223 (oneway) → 1205208207 | They leave the track before the west hairpin and rejoin it on the main straight. The road is untagged as a pit lane, so this is our interpretation |
| Venue outline | way 169455714 `leisure=stadium`, `name=Bira`, `sport=motor;karting` | Used as the facility footprint |
| Buildings | 3 × `building=yes name="Pit Stop"` (132453983, 165165898, 132457157); 1 × `"Seating"` (132453984) | Footprints only, no heights or levels. 132457157 is next to the kart track |
| Gate | node 1767298161 `barrier=gate access=no` on the venue outline (west corner) | |
| Access road | service way 132455221 from CBI.2081 (node 1457068485) to the track's west corner | |
| Parking | node 1767278421 `amenity=parking` inside the venue | Way 167028268 is 951 m away (golf club) and is ignored |
| Service roads | about 12 inside the outline; tunnel 132455224 runs under the track | |
| Not in OSM | race control, paddock layout, grid boxes, curbs, barriers, run-off, marshal posts, floodlights, kerb colours, start line position, track width | All of these are gameplay additions in our data (`verified=false`) |

### Corner count from the OSM geometry
`tools/circuit/bira_circuit.py` measures the curvature of the smoothed centreline. A "corner" is a run of curvature
with radius under 250 m and turning of at least 12°. Pieces in the same direction less than 25 m apart are merged.
Distances below are from our start line:

`L154° @314 m (r23)`, `R171° @674 m (r20)`, `R54° @1012 m`, `R59° @1133 m`, `R33° @1262 m (r104, fast kink)`,
`L48°/R52° @1571-1601 m (chicane)`, `L65°/R52° @1825-1869 m (chicane)`, `R123° @1972 m (west hairpin)`, `R59° @2114 m`
→ **11 corners**. This matches Wikipedia's 11, and the two chicanes match Wikipedia's description. With a stricter
threshold (≥30°, r<160 m) the fast kink drops out and the count is 10. Counting each chicane as one corner gives 9.
The official numbering is **unverified**.

## Elevation
- Source: Terrain Tiles (Terrarium PNG encoding) on the AWS Registry of Open Data, bucket `elevation-tiles-prod`.
  It is free and needs no API key. Zoom 15 has 12 tiles in `data/dem/terrarium/` (668 KB). Each pixel's height is
  `R*256 + G + B/256 - 32768` m.
- Resolution: at z15 a pixel is about 4.6 m, but the source data here is coarser. Terrain Tiles mix SRTM, GMTED,
  ETOPO1 and national datasets, and in Thailand the best source is most likely SRTM (~30 m). We have **not checked**
  which source each tile uses.
- Profile along the track: raw 100.2–124.2 m. Smoothed over 90 m: 100.8–123.5 m, a relief of about **23 m**, with a
  steepest smoothed grade of **12.1 %**. The high point is about 590 m into the lap, just before T2 (the
  northeast hairpin). The low point is about 1,280 m in, on the southern section after T4. This fits "elevation changes" and "downhill double-apex",
  but SRTM is a surface model (trees and buildings raise it) and is noisy at this scale. **Absolute heights and
  grades are unverified.** Use them as a plausible shape, not as survey data.
- Licence: Terrain Tiles may be used with attribution. See
  https://github.com/tilezen/joerd/blob/master/docs/attribution.md (SRTM: NASA/USGS, public domain; other sources
  as listed there). The attribution string is in `tools/circuit/config/bira.json` and in the generated module.

## Licensing and naming
- OSM data: © OpenStreetMap contributors, ODbL 1.0. The attribution travels in every generated file and is set as an
  attribute on `workspace.Circuit_bira`. An in-game credit is needed before publishing (same as the city).
- "Bira" is used **descriptively** for the real place ("Bira Circuit (game venue)"). We do not use Bira's logos,
  official track map, artwork or sponsor marks. Signs in the game show only the descriptive name. Sponsor boards,
  if they are added, must use invented placeholder brands. Before publishing, the owner should decide whether to
  keep the real name or rename the venue (for example "Pong Hills Circuit") in case the circuit owner objects. This
  is not legal advice.
- Wikipedia/LapMeta facts are paraphrased. No text or images were copied.

## Sources
- https://bira.co.th/ and https://bira.co.th/trackinfo/ (official; figures not readable as text)
- https://en.wikipedia.org/wiki/Bira_Circuit
- https://www.lapmeta.com/en/track/variation/375 (direction, 12 turns)
- https://renndriver.com/places/bira-international-circuit/ (history, turn-count disagreement)
- OpenStreetMap via Overpass API (queries in `data/osm/queries/bira_*.overpassql`)
- Terrain Tiles: https://registry.opendata.aws/terrain-tiles/
