# Road visual P0: root cause report (Sukhumvit / Pattaya Klang junction)

Status: **offline analysis only.** Every number below comes from the exported build data (`build/`), read by
`tools/roadvis` with the existing builder ports (`road_check.py`, `road_fix.py`, `junction_aprons.py`,
`road_seams.py`). Nothing was run in Studio. The images are offline previews (PIL top-down views and Blender renders),
not Roblox screenshots, and they are not a Visual PASS.

Rerun: `D:\ROBLOXRACE\.venv\Scripts\python tools\roadvis\cli.py analyze --city` (about 6 minutes). It writes
`build/roadvis/analysis.json`.

## 0. The place in the owner's screenshot

The owner's screenshot (`Screenshot 2026-10-21 045906.png`) was taken with this camera: Studio edit camera at world
(24609.8, 115.9, 713.3), look direction (-0.386, -0.386, 0.837), FOV 70. The look ray hits
`WideChunks.Chunk_8_1` "Sukhumvit Road" (edge `709043850:w1140`) at (24494.9, 1, 962.3).

The analysis box is world x 24220..24820, z 650..1250. In map-local studs that is x 4220..4820, z 650..1250
(world = map + (20000, 0, 0)). The box covers chunks 8_1, 8_2, 9_1, 9_2 plus edges that come in from 7_2. It holds:

- Sukhumvit Road (trunk): 4 one-way carriageways plus 2 service carriageways.
- 8 trunk_link slip roads.
- Pattaya Klang Road: a dual carriageway, plus its 5-lane two-way west arm.
- Soi Sukhumvit Pattaya 53 and Soi 40/2.
- 54 buildings.
- 17 junction discs and 10 joint discs. They sit on 12 graph nodes, all within about 130 studs of each other.

Images (offline previews):

| View | File |
|---|---|
| Top-down layer classification (same legend as the leader's map) | `art/roadvis/top_before_layers.png` |
| Top-down, as the eye sees it | `art/roadvis/top_before.png` |
| Owner's camera, rebuilt in Blender from the chunk data | `art/roadvis/cam_before_owner_view.png` |

The rebuilt owner view has the same layout as the screenshot. So the analysed data is what the owner saw.

## 1. Pipeline trace (where each defect is made)

| Stage | File | What it does | Defect it causes here |
|---|---|---|---|
| Graph | `road_graph.py` | OSM to gameplay. Distances x0.5 (compression 0.5, 0.28 m/stud gives 1.786 studs per real metre). Lanes are NOT compressed: 13 studs per lane (3.71 studs per metre). | Roads are 2.08x too wide for the city around them, so carriageways overlap. See section 2. |
| Graph | `dual.py` rule b (`apply_offsets`) | Shifts a minor road sideways when it runs too close to another road. Only interior points move. | Only small fixes. A dual carriageway is never pulled apart. |
| Layout | `gameplay_layout.py`, `buildings.py` | Building footprints get the same x0.5. Heights x0.75. The road corridor plus 3 studs is cut out of each footprint. | Buildings are half scale next to full-scale roads. Their setback is whatever is left over (median 18 studs, p10 3.8). |
| Export | `export_roblox.py` | One slab per DP-simplified segment (max 120 studs). Junction disc radius = widest arm half-width. Sidewalk 10 on main roads, 0 on express. | Every degree-3+ node gets a full circle. Sukhumvit (express) has no sidewalk while the side roads have one. |
| Fix pass | `road_fix.py` | Kink fillets. Bend joint discs (radius = full half-width), jA/jB trims, `noMarks`. | More discs. Markings get cut wherever a disc or another slab lies under them. |
| Dual | `dual.py` rule a/c, through `road_fix` rule D | Merges same-name carriageways. The kept edge gets a centreline shifted halfway to its partner, keeps its OWN width, and becomes two-way with `lanes = round(width/26)*2`. The partner is hidden or cut. Leftover old slab becomes `fill` triangles. | The merged slab sits over the median, not over the real lanes. Lanes of the hidden carriageway are left only partly covered, then patched with irregular fill triangles (blobs). The markings describe an invented two-way road (double yellow down the merged centre, wrong lane count). |
| Aprons | `junction_aprons.py`, `PattayaApronBuilder` | Asphalt throat triangles at 0.98 between arms, corner fills at 1.58. | More asphalt slivers at the junction edges. |
| Shoulders | `road_shoulders.py`, `PattayaShoulderBuilder` (approved pilot) | 8-stud concrete strips at 0.985 along exposed slab edges, tapers, and gap fills for holes. | Concrete-grey strips and small irregular pieces along every jagged edge of the merged surface. See section 6. |
| Furniture | `furniture.py` | Zebras at OSM crossing nodes snapped to an edge, plus one per signalised approach. Bars are 2 wide, 6 long, and must lie on the built slab. On merged groups they are centred on the kept slab. | Zebras sit where OSM tagged a crossing on the real carriageway. Here that point is in the middle of a merged asphalt field, so the zebra is too short and ends in the asphalt. |
| Builder | `PattayaBuilder.buildEdge` | Slabs (stripe), fill wedges, markings trimmed by disc radius or noMarks, dashes 8 long with a 32 gap (wide world), sidewalks trimmed by disc radius + sidewalk. | Markings are cut into short fragments, and none run through junctions or joints. |

## 2. Proportions (the main cause)

| Scale | Studs per metre |
|---|---|
| City distances, building footprints (x0.5 / 0.28) | **1.786** |
| Lane width (13 studs / 3.5 m) | **3.714** |
| Race car (chassis 7 x 15, body 16 long; 7 studs / 1.85 m) | 3.78 |
| Building height (0.75 / 0.28) | 2.68 |

Lane width matches the car, which is good for driving. Everything the roads sit between is at half that scale. So a road
takes **2.08x** its real share of the ground:

- Real share of road at city scale in this box (OSM lanes x lane width): **15.2 %**.
- Game: asphalt 23.8 % of the box, lane corridors 32.4 %.
- Buildings: 15.6 % of the box. Median building 44 x 19 studs, height 29: smaller than two Sukhumvit lanes (26 studs)
  are wide.

Real Sukhumvit here has 4 + 4 main lanes, 2 + 2 service lanes and 8 slip roads, separated by medians and islands of
5–15 m. At 1.786 studs/m those separators shrink to 9–27 studs. But the carriageways are drawn 39–65 studs wide each, so
they run into one another: **12,188 studs² of carriageway-on-carriageway overlap outside the junctions** in this box. The
pipeline then has to merge them (dual.py), and every later layer patches the merge.

## 3. Defects at this junction, measured

All areas in studs², box x 4220..4820, z 650..1250. "Asphalt" means slabs + fill triangles + discs + aprons.

| Defect | Number |
|---|---|
| Asphalt area | 85,516 |
| Area covered by **2 or more** separate asphalt units (raster 0.5) | **21,998 (25.7 % of the asphalt)**, 4,239 by 3 or more |
| Stacked excess (sum of areas minus union) | 26,684 |
| Disc area / **disc area outside every slab and fill** (sticks out past the road edge) | 40,865 / **15,629 (38 %)**. 28 of 29 discs overhang by more than 5 studs². Worst: node 6949723645 (1,855 of 2,123), 1078508668 (1,273), 1572760134 (1,223). |
| Fill-triangle area (rule D patches) | 10,860 (360 WedgeParts) |
| Asphalt outside every real lane corridor (both carriageways, junction hulls) | 470 (0.5 %) |
| Asphalt not explained by the **drawn** (visible) carriageways | **16,400 (19 %)**: the hidden carriageways' lanes and medians paved over |
| Shoulder-pilot concrete in the box | 11,449 (1,601 parts) |
| Edges with the lane count changed by the merge | Sukhumvit 688452706 / 688432504 / 709043298 (OSM 3 one-way lanes, built as 4-lane two-way, 39 wide); 740847242 (OSM 5 one-way, built as 4-lane two-way, 65 wide); 740847243 (OSM 4 one-way, built two-way) |

**What "meaningless asphalt" really is here.** Almost all asphalt (99.5 %) lies inside SOME real lane corridor. The
blobs are not random extra pavement. They are the real lanes of six carriageways and eight slip roads, pressed into
half the space they need, and drawn as one surface. That surface has:

- no medians, islands or kerbs to separate the carriageways;
- 29 circles sticking out past its edges;
- 360 fill triangles giving it a ragged outline;
- markings that describe a different road.

**Crossings (18 zebras in the box).**

| Finding | Count |
|---|---|
| Cover less than 80 % of the asphalt cross-section they sit on (median coverage 0.46; e.g. 22 studs of zebra across 180 studs of asphalt at (24498.8, 818.3)) | 14 |
| Reach a sidewalk at neither end | 16 |
| Reach a sidewalk at both ends | **0** |
| On a hidden carriageway (no slab of their own) | 4 |
| On a merged slab | 3 |
| Mid-block, more than 60 studs from a junction node (OSM crossing nodes along Sukhumvit) | 6 |

Every zebra is square to its own OSM edge (angle error < 1°). The misplacement comes from the merged geometry, not
from the angle.

**Lane lines.**

- 63 marking parts in the box.
- Expected lane boundaries (OSM lanes - 1 per carriageway, plus the centre of two-way roads, sampled every 4 studs
  outside the junctions) covered by a drawn line, dash gaps bridged: **45.8 %** on visible carriageways, **11.9 %** on
  hidden ones, 35.1 % overall.
- 69 separate marking runs, median length 41 studs. 98 of 132 run ends are away from any junction mouth. A line just
  stops where a disc, a cut or a noMarks range begins.
- Degree-2 joints between marked edges: 4, of which 3 are broken (median gap 14.7 studs). 3 change lane count or width,
  and 1 has a lateral jump over 3 studs.
- No stop lines exist anywhere in the pipeline.

**Wheel support (this box, car footprint on every lane centre of every graph carriageway, outside a 50-stud seam
band).** 250 of 3,253 samples have a wheel over the terrain (3-stud drop). These are the lanes of hidden or cut
carriageways that the merged slab does not cover.

## 4. Citywide (same definitions, 551 chunks of 512 studs, raster 1 stud)

| Defect | City |
|---|---|
| Asphalt | 17.45 M studs² |
| Area under 2 or more asphalt units | **2.53 M (14.5 %)**, 0.71 M under 3 or more |
| Discs | 3,743. **1,584 overhang by more than 5 studs²**. Overhang 0.43 M = 13.1 % of all disc area. |
| Fill triangles / aprons | 0.28 M / 0.13 M |
| Carriageway-on-carriageway overlap outside junctions | **0.85 M** |
| Asphalt not explained by drawn carriageways | 1.14 M (6.5 %) |
| Asphalt outside every lane corridor | 0.09 M (0.5 %). Worst chunks: 6_15, 6_16, 6_10, 4_10, 5_10 (Thepprasit / Jomtien dual roads). |
| Zebras: 502 | 192 cover less than 80 % of their asphalt section. **369 reach no sidewalk at either end, 52 reach one at both.** 116 on hidden carriageways, 137 on merged slabs, 165 mid-block. |
| Lane-boundary coverage | Visible carriageways 56 %, hidden 12 %. 12,998 marking runs, median length 4.7 studs (single dashes). 22,632 of 25,996 run ends away from junction mouths. |
| Degree-2 joints between marked edges | 235: 72 broken, 32 with a lane / width change, 48 with a lateral jump over 3 studs |
| Road-layer parts (slabs, fills, discs, aprons, corner fills, sidewalks, shoulders) | 70,839 |

So the defects are not local to Sukhumvit. They are worst on every dual carriageway, slip-road complex and close
parallel road, which is where dual.py merged things. The central slice has its own version of the problem (base-slice
sidewalks over new roads).

## 5. Ranked root causes

1. **Scale mismatch (x0.5 city, x1 lanes).** Roads are 2.08x too wide for the city fabric. Dual carriageways, service
   roads and slip roads overlap (12,188 studs² here, 0.85 M citywide). Every later layer patches that overlap.
2. **Merging by centreline shift (dual.py rule a).** The kept carriageway is moved onto the median and keeps its own
   width. The partner's lanes are left uncovered (250 wheel-drop samples here) and patched with fill triangles. The
   merged edge is relabelled two-way with an invented lane count, so its markings describe a road that does not exist.
3. **Discs as junction geometry.** A circle of radius = widest half-width at every degree-3+ node, plus joint discs at
   degree-2 nodes. 38 % of the disc area here, and 13 % citywide, lies outside the slabs. Discs also trim the markings
   and sidewalks of every arm.
4. **No layer separation.** The visible surface IS the collision surface (Parts at 1.0 / 0.99 / 0.98 / 0.985). Every
   collision patch (fill, apron, disc, shoulder, gap fill) is also something you see, in a slightly different place
   and height. Overlaps are not hidden, they are built.
5. **Markings and zebras derived per edge, not per carriageway or junction.** Markings stop at every disc or cut and
   never form stop lines. Zebras come from OSM points on carriageways that the merge moved or hid: 0 of 18 here end
   on a sidewalk.
6. **Sidewalk rule by tier.** Express roads get 0 sidewalk, main roads get 10. Sukhumvit has bare edges while its side
   roads have kerbs. The shoulder pilot later filled the bare edges with concrete strips (section 6).

## 6. The approved shoulder pilot in the owner's view (honest assessment)

The pilot has 2,536 parts in 8 chunks (`ShoulderChunks`: s10_26, s9_1, s10_25, s8_2, s8_1, s9_25, s8_2_2, s8_1_2).
1,601 of them are inside this box: 352 shoulder strips (642 parts), 157 tapers (303) and 362 gap fills (656). They are
concrete (92, 91, 88) at 0.985, so they read as a slightly lighter grey than the asphalt (46, 47, 52).

Visible in the owner's camera footprint (not under a higher surface):

| Kind | Pieces visible | Visible area | How it reads |
|---|---|---|---|
| Shoulder strips | 227 | 8,796 studs² | Continuous lighter-grey bands along both sides of the merged surface. They follow its jagged outline, steps and disc bulges, so the outline reads even more irregular. They are the "concrete grey strips" in the screenshot. |
| Tapers | 109 | 630 | Small wedges where the width changes (52 to 39 / 26 near z 990–1060). |
| Gap fills | 154 | 1,395 | Small irregular triangles in slivers between slabs, discs and fills, mostly inside the slip-road complex. Individually tiny, but they add speckle to the edges. |

**Conclusion:** the shoulder pilot does not cause the blobs. Those come from causes 1–4 above. But it **does contribute
to the look the owner dislikes**. It outlines and so emphasises the ragged merged surface with a second grey, and its
gap fills add speckle. The anti-flip support it gives is real and must stay. The spec (`docs/ROAD_VISUAL_SPEC.md`,
section 7) proposes how to change its appearance without losing that support.
