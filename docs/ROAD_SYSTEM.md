# Road system

Builder: `roblox/src/ServerStorage/PattayaBuilder.luau` (copy in Studio at `ServerStorage.PattayaBuilder`).

- One anchored Part per simplified centreline segment, lengthened at each joint by the outer-edge gap of the bend
  (`width/2 * tan(turn/2)`), so curves have no visible gaps. Straight stretches are single long Parts (≤120 studs).
- Junctions: one flat cylinder per graph node, radius = widest incident road half-width + sidewalk.
- Markings (non-colliding, `CanQuery = false` so the car's suspension rays ignore them): double yellow centre line on
  two-way main roads, dashed lane lines, none on sois. They stop at junction discs.
- Sidewalks: offset strips, 0.6-stud curb, trimmed back from junctions.
- Road top at Y = 1 (gameplay), on a terrain ground slab with top at Y = 0.
- Each edge Model carries attributes: EdgeId, OsmWay, Tier, Lanes, Oneway, Coastal, NameTh.
- Tiers in use: main (secondary/tertiary/primary), soi (residential/unclassified/living_street). Express (trunk:
  Sukhumvit) lies just east of the first slice.

First build: 2,125 simplified segments → 7,545 Parts including markings and sidewalks, 463 junctions, 72 chunks.

Not done yet: elevation/bridges, banking, traffic signals, drive test. Overlap check between widened parallel roads:
see below (wide world; the central slice still has its known overlaps).

## Offline road check and the overlap rule (wide world, 2026-10-18)
`tools/mapgen/road_check.py <config> [--corridor] [--json out.json]` reproduces the Studio probe (a ray down every
25 studs along every new edge's centreline) without Studio: it rebuilds every road slab, sidewalk strip, junction
disc and joint disc exactly as PattayaBuilder does, from the EXPORTED chunk modules of the build, its base build and
(with `--corridor`) `build/bira/roblox_corridor`. Each probe is `road`, `sidewalk` (a strip covers it: the 0.6-stud
bump), `hairline` (only on the bare boundary where two slabs touch without overlapping) or `none`.

| pattaya_wide, 23,142 probes | road | sidewalk | hairline | none |
|---|---|---|---|---|
| before (export as imported) | 21,318 | 926 | 898 | 0 |
| after | 23,139 | 3 | 0 | 0 |

(The leader's Studio run sampled slightly differently: 24,994 probes, 966 sidewalk, 62 nothing.) The 3 left are
base-slice sidewalks lying over new roads at the seam; the base slice is not changed.

Root causes and fixes (both in `export_roblox.main_wide`, the central slice export is unchanged):
- **Sidewalks on a parallel road.** At ×0.5, dual carriageways and close parallel roads (Jomtien Second Rd 522 hits,
  Thappraya 151, Pattaya Nuea 145, Chalermphrakiat 42) are so near that one road's sidewalk strip (width/2 ..
  width/2 + sidewalk) covers the other's roadway. Rule: each sidewalk SIDE is rebuilt as the builder would (trimmed
  at junction discs) and dropped when it overlaps another edge's road slab by more than 10 studs² (the continuing edge
  at a degree-2 joint does not count). 258 of 1,022 sides dropped: 184 edges keep one side (chunk field
  `swSide = -1 | 1`, read by `buildEdge`; the outer side of a dual carriageway stays), 37 edges get `sidewalk = 0`.
  The corridor keeps its simpler rule (one-way corridor edges have no sidewalk).
- **No road under the probe.** Never a missing slab: every miss was at a node with no junction disc (degree-2
  joints where a road changes name/class or meets the seam, and dead ends). There two slabs only touch end to end, so
  a ray exactly on the node can slip between them, and a bend leaves a wedge open on the outer side. Fix: **joint
  discs** (`joints.luau`, osmNode/x/z/r, radius = narrowest incident half-width so they never stick out of the road),
  built by `Extend` into `WideJunctions` like junction discs, but they trim no markings or sidewalks, so no chunk
  module changes because of them: 1,104 in the wide world, 13 on the corridor. The same hairline can exist at a
  straight internal joint inside one edge (split_long pieces, turn 0 so no stretch); the corridor check found 1 such
  probe. Not changed, because it lives in the builder's stripe(), which the base slice also uses.
