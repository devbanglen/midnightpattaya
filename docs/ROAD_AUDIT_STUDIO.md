# Road audit in Studio (leader, 2026-10-19)

Owner report (Thai): some city roads cross each other chaotically / overlap, and the Walking Street gate stood in the
road (gate fixed the same day: see PROJECT_STATUS row 5b). This is the Studio-side ground truth that the pipeline
audit (`tools/mapgen/road_audit.py`, `docs/ROAD_AUDIT.md`, team4/roadfix) is checked against.

**Probe:** every built `Road` part under `workspace.PattayaWorld` (14,665 parts; 2,812 `Junction`/`Joint` discs).
For each pair of intersecting Road parts with different road names, the centreline of one part was sampled every
4 studs; a sample counts when it lies inside the other part (0.5 studs inside its edge) and outside every disc
(radius + 6). Pairs with 2+ samples are findings (length = samples x 4). Edit mode, no streaming issue (everything
is loaded in Edit).

**Result: 92 overlapping pairs, about 2,300 studs in total; none inside the central slice's base chunks.**

| Road pair | spots | studs | where (world studs) | class |
|---|---|---|---|---|
| Thep Prasit Road x Thepprasit Road | 38 | 1,284 | x 21,274..23,571, z 5,487..5,753 (Chunk_2_11, 3_10, 3_11, 4_10, 5_10, 6_10, 7_10) | dual carriageway, two OSM ways with different name spellings; slabs overlap after the 0.5 compression |
| Sukhumvit Road x trunk_link | 22 | 348 | (23,550, 4,431) Chunk_6_8; (24,479, 910) Chunk_8_1; (24,691, 342) Chunk_9_0 | slip roads merging at acute angles |
| Thappraya Road x residential | 6 | 112 | (18,623..18,658, 4,715..4,798) Chunk_-3_9 | parallel soi too close |
| Jomtien Second Road x trunk_link | 2 | 108 | (24,808, 12,806), (24,772, 12,859) | slip road merge |
| Porn Prapa Nimit x Sukhumvit Road | 3 | 32 | (24,651..24,658, 392..399) | acute junction |
| Chalermphrakiat Road x secondary_link | 4 | 32 | (18,623, 3,226), (19,017, 3,182) | acute junction |
| Chalermphrakiat 5 x Chalermphrakiat Road | 1 | 20 | (23,466, -1,461) | |
| Phet Trakun Road x tertiary_link | 1 | 20 | (22,638, -2,639) | |
| Chalermphrakiat Road x Khopai Soi 4 | 2 | 20 | (20,463, 3,293), (20,534, 3,338) | |
| 11 more pairs | 1-2 each | 8-16 | Sukhumvit Road x residential (26,029, 15,167); Jomtien Second Road x tertiary_link (23,661, 13,167); Jomtien Second Road x residential (18,862, 7,391); Chalermphrakiat 7 x Chaloem Phra Kiat 7 Soi 1 (22,923, -1,249); Pattaya Nua Soi 6 x Soi Nakula 33 (22,537, -2,967); Sukhumvit Pattaya 14/1 x residential (26,023, -6,644); Jomtien Second Road x secondary_link (22,389, 11,491); Soi Chalermphrakiat 12 x 14 (22,611, 1,349); Soi Thappraya 3 x Thappraya Road (18,902, 3,717); Soi Baku x residential (21,030, 1,945); Thap Phraya Rd x residential (18,922, 4,974) | small |

What this probe does not see: two roads crossing exactly at a disc with a bad angle, kinks inside one edge, and
sidewalk problems (covered by the worldfix sidewalk probe). The pipeline audit covers those.

Luau (Edit mode, command bar): the probe is the `_G.RA` block in the session log; it runs in a `task.spawn` and is
polled with `_G.RA.state`, `_G.RA.findings`.

## After the team4/roadfix rebuild (leader, 2026-10-19, Studio)

Rebuilt with `PattayaBuilder.RebuildChunks`: central 49 chunks (+129 joint discs, Junctions 312 → 441), wide 130
chunks (16,915 parts), corridor 7 chunks; WideJunctions unchanged at 2,500. Probes after:

| probe | before | after |
|---|---|---|
| marking parts (Lane/Dash/…) lying on another road outside discs | not measured in Studio (offline: 1,331) | **0** |
| Sidewalk parts whose centre lies inside another road's slab | not measured | **58** (Thepprasit kerb inside Thep Prasit 22, Porn Prapa Nimit kerb in Sukhumvit 10, Thappraya 7, Jomtien Second Rd x links 11, misc 8) → pass 2 requested |
| end-to-end Road joints with 35–150° heading change and no disc (parts ≥ 6 studs, ends within 1.5) | 345 (looser rule: any length, 3 studs) | **90**, all wide-world residential sois at 60–77° → pass 2 requested |
| slab-overlap pairs (geometry) | 92 | unchanged by design (the fix hides overlaps: no markings/kerbs on them; dual carriageways were not pulled apart) |

Short Road parts (< 6 studs): 86 after (fillet pieces), 9 before.

## After pass 2 (leader, 2026-10-19, Studio)

Pass 2 (commit a3b8daa) changed only the three `joints` modules (+407 vertex discs: central 54, wide 346, corridor 7)
and the builder (`fresh = true`: chunk/joints modules required from a Clone(), duplicate checks). The 58 stale kerbs
were old parts that pass 1's wide rebuild had taken from Studio's require cache (the replaced module Source was not
what `require` returned), not a data gap: the fresh rebuild of the same 130 wide + 7 corridor chunks removed them.
Junctions 441 → 495, WideJunctions 2,500 → 2,853; Road parts 15,005 (438 short fillet pieces).

| probe | before any fix | after pass 1 | **after pass 2** |
|---|---|---|---|
| marking parts on another road outside discs | 1,331 (offline) | 0 | **0** |
| Sidewalk centres inside another road's slab | – | 58 | **0** |
| Road joints 35–150° with no disc (parts ≥ 6 studs) | 345 (looser rule) | 90 | **0** |
| slab-overlap pairs (geometry; hidden, not removed) | 92 | 92 | 92 |

Lesson for the install procedure: after replacing a ModuleScript's Source in Edit mode, builders must require a
Clone() (now built into RebuildChunks/Extend `fresh`), or the old module is served silently.

**Drive regression after pass 2 (Play):** Central Loop, physics autopilot at 120 studs/s over the rebuilt city chunks:
13,290 studs in 115.5 s, 227/227 probes on road, up vector min 1.00, every gate counted (lap completed, 67 nitro
bonuses), no script errors. Server probe of RacePath: 332/332 road.

## Dual carriageways rebuilt (leader, 2026-10-19, Studio)

Owner saved the place (+ a Save-As copy) first. Installed team4/dual: PattayaBuilder (hidden/cut/fill/merged),
`PattayaData.graph_part_2`, `ReplicatedStorage.PattayaTraffic`, `PattayaDataWide.joints`, 28 + 214 + 5 chunk modules
(old modules kept in `_prev_dual` folders), furniture data folder replaced (old folder renamed
`PattayaDataFurniture_prev_dual`). Rebuilt with `RebuildChunks` (fresh): central 28 chunks 7,237 parts 0.9 s; wide 214
chunks 27,100 parts 4.4 s; corridor 5 chunks 506 parts; furniture `Remove()` + f1..f35: 274 chunks 9,140 parts 5.2 s.
Road parts now 19,568 incl. 5,862 RoadFill wedges (WedgeParts named Road with attribute RoadFill).

| probe | before dual | after dual |
|---|---|---|
| slab-overlap pairs (different names, outside discs +6) | 92 (~2,300 studs) | **70 (1,096 studs)**, all 12–16-stud throats at junctions (tee class), no markings/kerbs on them |
| markings on another road | 0 | **0** |
| Sidewalk centres inside another road (real roads) | 0 | **0** |
| bare bends 35–150° (RoadFill wedges excluded) | 0 | **0** |
| furniture solid parts touching road/sidewalk/disc | 0 | **1** (NameSignPost (21589, 5644) on a Thep Prasit sidewalk → dual pass 3) |
| road-centre raycasts whose top hit is not road | 0 | **2** (fill wedges under shophouses osm 311941409 at (19062, 3225) and 311061457/311061340 at (24670, 640)) → dual pass 3 |
| crossing bars | 4,906 | 4,321, all thin/non-solid |
